"""The signing service's two HTTPS halves: the API listener (`submit`, `poll`) and the client that speaks to it.

**The listener** terminates TLS 1.3 itself and requires a client certificate the service's CA issued, as the store's
`tls_context` does (not imported: C4). The handshake runs in the per-connection thread, so a slow peer stalls its own
thread and not the accept loop, and a peer whose handshake fails is closed without one HTTP byte written to it. A peer
that passes the handshake is a caller only if its certificate's subject (RFC 4514) is named in the settings; that is
checked once the request line and headers are parsed and before any body byte is read, and an unnamed peer gets a
403 `signer.unknown-caller` and nothing reaches the service. The stdlib's `http.server` owns the HTTP grammar; one
request per connection (`Connection: close`). `approve` and `decline` are not on this listener: the code is
entered on the service's own page (`page.py`, which asks no client certificate), never over this API.

**The client**, `HttpsService`, implements `RemoteTotpContract` against it, so `RemoteTotp` signs through a running
service. A refusal the service sent is rebuilt as the typed `Refusal` it was raised as.
"""

from __future__ import annotations

import http.client
import json
import socketserver
import ssl
import threading
from collections.abc import Sequence
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

from cryptography import x509

from isidium.store.core.refusal import Refusal

from .service import Service
from .settings import Settings

_JSON = "application/json"


def tls_context(settings: Settings) -> ssl.SSLContext:
    """The listener's context: it proves it is the service, and requires a client certificate its CA issued. TLS 1.3
    only: every client is ours, and it removes renegotiation and cipher-suite selection from the surface."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.verify_mode = ssl.CERT_REQUIRED
    context.load_verify_locations(cafile=str(settings.ca))
    context.load_cert_chain(certfile=str(settings.tls_certificate), keyfile=str(settings.tls_key))
    return context


def _subject_of(tls: ssl.SSLSocket) -> str | None:
    """The peer's certificate subject, RFC 4514, or None when it presented none."""
    der = tls.getpeercert(binary_form=True)
    return None if not der else x509.load_der_x509_certificate(der).subject.rfc4514_string()


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"  # one request per connection

    def __init__(self, request: ssl.SSLSocket, client_address: Any, listener: Listener, subject: str | None) -> None:
        self._listener, self._subject = listener, subject
        self._consumed = False  # whether the body this request declared has been read
        super().__init__(request, client_address, listener)

    def log_message(self, format: str, *args: Any) -> None:
        """Nothing is logged here: a request line is a peer's bytes, and a body may carry a display."""

    def _answer(self, status: int, body: dict[str, Any]) -> None:
        data = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", _JSON)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Connection", "close")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _refuse(self, status: int, rule: str, detail: str = "") -> None:
        self._answer(status, {"rule": rule, "detail": detail})

    def send_error(self, code: int, message: str | None = None, explain: str | None = None) -> None:
        # The stdlib's own error page is HTML with words that are not ours; every refusal is a rule id.
        self.close_connection = True
        self._refuse(code, "signer.malformed", "the request is not well-formed HTTP")

    def parse_request(self) -> bool:
        if not super().parse_request():
            return False
        if self._subject is None or self._subject not in self._listener.settings.callers:
            self._refuse(403, "signer.unknown-caller")
            return False
        return True

    def do_POST(self) -> None:
        if self.path not in ("/submit", "/poll"):
            self._refuse(404, "signer.not-found")
            return
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            length = -1
        if not 0 <= length <= self._listener.settings.max_body_bytes:
            self._refuse(400, "signer.malformed", "a Content-Length within the limit is required")
            return
        body = self.rfile.read(length)
        self._consumed = True
        try:
            payload = json.loads(body)
            result = self._submit(payload) if self.path == "/submit" else self._poll(payload)
        except (ValueError, KeyError, TypeError):
            self._refuse(400, "signer.malformed", "the body is not the request this endpoint takes")
            return
        except Refusal as r:
            self._refuse(403, r.rule, r.detail)
            return
        self._answer(200, result)

    def do_GET(self) -> None:
        self._refuse(404, "signer.not-found")

    do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = do_GET

    def finish(self) -> None:
        """Discard the body a refusal never read, then close. Closing a socket that still holds unread bytes makes the
        kernel reset the connection, and the reset can destroy the answer in flight: a client that sends its headers
        and its body separately would see the connection drop instead of the 403. **Read through `rfile`**, not the
        socket: `rfile` is buffered, so a body that arrived in the same TLS record as the headers is already in it and
        the socket holds nothing more to wait for; draining the socket would block for the read timeout and hold the
        peer's EOF back until then. Bounded by the body cap and the read timeout; nothing read here is parsed."""
        try:
            left = min(self._unread(), self._listener.settings.max_body_bytes)
            while left > 0:
                chunk = self.rfile.read(min(left, 65536))
                if not chunk:
                    break
                left -= len(chunk)
        except (OSError, ValueError):
            pass  # the peer's connection dies with the peer's mistake
        finally:
            super().finish()

    def _unread(self) -> int:
        """The body bytes the peer declared and this handler never read (a refusal answers before the body)."""
        headers = getattr(self, "headers", None)
        if self._consumed or headers is None:
            return 0
        try:
            return max(0, int(headers.get("Content-Length", "0")))
        except ValueError:
            return 0

    def _caller(self) -> str:
        if self._subject is None:  # parse_request has refused this already; the type needs it said
            raise Refusal("signer.unknown-caller")
        return self._subject

    def _submit(self, p: Any) -> dict[str, Any]:
        tenant, value, at_epoch, display, skew = p["tenant"], p["value"], p["at_epoch"], p["display"], p["time_skew_s"]
        if not (isinstance(tenant, str) and isinstance(value, str) and isinstance(display, list)):
            raise TypeError
        if isinstance(at_epoch, bool) or not isinstance(at_epoch, int):
            raise TypeError
        if skew is not None and (isinstance(skew, bool) or not isinstance(skew, int)):
            raise TypeError
        rid = self._listener.service.submit(self._caller(), tenant, value, at_epoch, display, skew)
        return {"request_id": rid}

    def _poll(self, p: Any) -> dict[str, Any]:
        rid = p["request_id"]
        if not isinstance(rid, str):
            raise TypeError
        return {"sig": self._listener.service.poll(self._caller(), rid)}


class Listener(socketserver.ThreadingTCPServer):
    """A threaded TCP server whose connections are wrapped in TLS inside their own thread. The stdlib server has no
    connection ceiling; only a peer with a CA-issued certificate gets past the handshake, and the ceiling, if the
    deployment wants one, is the deployment's (the container card)."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, service: Service, settings: Settings) -> None:
        self.service, self.settings = service, settings
        self._context = tls_context(settings)
        super().__init__((settings.listen_host, settings.listen_port), socketserver.BaseRequestHandler)

    @property
    def address(self) -> tuple[str, int]:
        host, port = self.server_address[:2]
        return str(host), int(port)

    def finish_request(self, request: Any, client_address: Any) -> None:
        try:
            request.settimeout(self.settings.handshake_timeout_s)
            tls = self._context.wrap_socket(request, server_side=True)
        except (ssl.SSLError, OSError):
            return  # the handshake failed: nothing is written to this peer
        try:
            subject = _subject_of(tls)
            tls.settimeout(self.settings.read_timeout_s)
            _Handler(tls, client_address, self, subject)
        except (OSError, ValueError):
            return  # the peer's connection dies with the peer's mistake
        finally:
            tls.close()

    def close(self) -> None:
        self.shutdown()
        self.server_close()


def start(service: Service, settings: Settings) -> Listener:
    """Bind and serve in a daemon thread. The caller owns the listener and `close()`s it."""
    listener = Listener(service, settings)
    threading.Thread(target=listener.serve_forever, name="isidium-signer-listener", daemon=True).start()
    return listener


class HttpsService:
    """`RemoteTotpContract` over HTTPS: one connection per call, the service's certificate verified against `ca`
    (hostname checking on) and this client's certificate presented. Every argument is required."""

    def __init__(self, host: str, port: int, ca: Path, cert: Path, key: Path, timeout_s: float) -> None:
        self.host, self.port, self.timeout_s = host, port, timeout_s
        self._context = ssl.create_default_context(cafile=str(ca))
        self._context.minimum_version = ssl.TLSVersion.TLSv1_3
        self._context.load_cert_chain(str(cert), str(key))

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        conn = http.client.HTTPSConnection(self.host, self.port, context=self._context, timeout=self.timeout_s)
        try:
            conn.request("POST", path, json.dumps(body).encode("utf-8"), {"Content-Type": _JSON})
            response = conn.getresponse()
            status, data = response.status, response.read()
        finally:
            conn.close()
        try:
            payload = json.loads(data)
        except ValueError:
            payload = None
        if status != 200:
            if isinstance(payload, dict) and isinstance(payload.get("rule"), str):
                raise Refusal(payload["rule"], "", str(payload.get("detail", "")))
            raise Refusal("signer.malformed", "", f"the service answered {status} with no refusal")
        if not isinstance(payload, dict):
            raise Refusal("signer.malformed", "", "the service's answer is not an object")
        return payload

    def submit(
        self, tenant: str, value: str, at_epoch: int, display: Sequence[Any], time_skew_s: int | None = None
    ) -> str:
        payload = self._post(
            "/submit",
            {
                "tenant": tenant,
                "value": value,
                "at_epoch": at_epoch,
                "display": list(display),
                "time_skew_s": time_skew_s,
            },
        )
        return str(payload["request_id"])

    def poll(self, request_id: str) -> str | None:
        sig = self._post("/poll", {"request_id": request_id})["sig"]
        return None if sig is None else str(sig)
