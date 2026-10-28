"""The code-entry page: the owner reads what is being signed on the phone and approves it there (card 55).

A second HTTPS listener beside the API's (`http.py`), and the process that starts both (`python -m isidium.signer.page
--settings PATH`, what the container's entrypoint execs). It asks for **no client certificate**: the phone has none, and
the owner's Aegis code is the authority. So the page can be reached by anything that can reach its address, which is
why the deployment keeps it inside the owner-only zone, and why every string a caller supplied is HTML-escaped (`_e`,
the one escaping point) before it is shown.

- `GET /` lists the pending requests, each with its tenant, the value's hash and the display exactly as the service
  received it (never recomputed or looked up, C1), or -- while no TOTP secret is enrolled -- the enrolment form. **A GET
  changes nothing**; any other GET path is a 404.
- `POST /approve` and `POST /decline` take a request id and a code; `POST /enrol` takes a code. The answer page says
  what happened, or the rule that refused.
- No script, no style, no image and no QR code (A1, A2): plain forms, and the response's CSP forbids script outright.
"""

from __future__ import annotations

import argparse
import html
import json
import signal
import socketserver
import ssl
import sys
import threading
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlsplit

from isidium.store.core.refusal import Refusal

from . import http, settings, totp
from .service import PendingView, Service
from .settings import PageSettings, Settings

_HTML = "text/html; charset=utf-8"
_FORM = "application/x-www-form-urlencoded"
# Script is forbidden outright (A1); a form may only submit back to this origin.
_CSP = "default-src 'none'; form-action 'self'; frame-ancestors 'none'"
_ISSUER = "isidium-signer"
_ROUTES = {"/approve": "approved", "/decline": "declined", "/enrol": "enrolled"}
_OUTCOME = {
    "approved": "Approved. The request was signed.",
    "declined": "Declined. The request will not be signed.",
    "enrolled": "Enrolled. The secret is saved and will not be shown again.",
}


def _e(text: str) -> str:
    """The one escaping point: everything a caller (or the owner's own typing) supplied passes through here."""
    return html.escape(text, quote=True)


# ---- rendering: each returns the page's bytes ----------------------------------------------------------------------


def _document(title: str, body: str) -> bytes:
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{_e(title)}</title></head><body><h1>{_e(title)}</h1>{body}</body></html>"
    ).encode()


def _otpauth(secret: str, key_fpr: str) -> str:
    """The link that opens Aegis (A2). The parameters are the ones `totp` computes with, so what the app derives is
    what the service checks."""
    label = quote(f"{_ISSUER}:{key_fpr}", safe=":")
    query = f"secret={secret}&issuer={_ISSUER}&algorithm=SHA1&digits={totp.DIGITS}&period={totp.STEP_S}"
    return f"otpauth://totp/{label}?{query}"


def render_enrolment(secret: str, key_fpr: str) -> bytes:
    return _document(
        "Enrol the authenticator",
        "<p>No authenticator is enrolled. Add this secret to Aegis, then enter the code it shows. "
        "The secret is saved only when that code verifies, and it is never shown again.</p>"
        f"<p>Secret: <code>{_e(secret)}</code></p>"
        f'<p><a href="{_e(_otpauth(secret, key_fpr))}">Open in the authenticator app</a></p>'
        '<form method="post" action="/enrol">'
        '<label>Code <input name="code" inputmode="numeric" autocomplete="off"></label> '
        '<button type="submit">Enrol</button></form>',
    )


def _request(view: PendingView) -> str:
    received = datetime.fromtimestamp(view.created, UTC).isoformat()
    # C1: the display the service received, as it received it -- the stored object, serialised, never recomputed.
    shown = json.dumps(view.display, ensure_ascii=False, indent=2)
    return (
        "<section>"
        f"<p>Request <code>{_e(view.request_id)}</code>, received {_e(received)}</p>"
        f"<p>Tenant: <code>{_e(view.tenant)}</code></p>"
        f"<p>Hash: <code>{_e(view.value)}</code></p>"
        f"<pre>{_e(shown)}</pre>"
        '<form method="post" action="/approve">'
        f'<input type="hidden" name="request_id" value="{_e(view.request_id)}">'
        '<label>Code <input name="code" inputmode="numeric" autocomplete="off"></label> '
        '<button type="submit" formaction="/approve">Approve</button> '
        '<button type="submit" formaction="/decline">Decline</button>'
        "</form></section>"
    )


def render_listing(pending: Sequence[PendingView]) -> bytes:
    body = "".join(_request(v) for v in pending) or "<p>No request is waiting.</p>"
    return _document("Signing requests", body)


def render_answer(title: str, message: str) -> bytes:
    return _document(title, f'<p>{_e(message)}</p><p><a href="/">Back to the requests</a></p>')


# ---- the listener --------------------------------------------------------------------------------------------------


class _PageHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"  # one request per connection

    def __init__(self, request: ssl.SSLSocket, client_address: Any, listener: PageListener) -> None:
        self._listener = listener
        self._consumed = False  # whether the body this request declared has been read
        super().__init__(request, client_address, listener)

    def log_message(self, format: str, *args: Any) -> None:
        """Nothing is logged here: a request line is a peer's bytes, and a form body carries the owner's code."""

    def _send(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", _HTML)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Security-Policy", _CSP)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Connection", "close")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _refuse(self, status: int, rule: str, detail: str = "") -> None:
        self._send(status, render_answer("Refused", f"{rule}: {detail}" if detail else rule))

    def send_error(self, code: int, message: str | None = None, explain: str | None = None) -> None:
        # The stdlib's own error page is HTML with words that are not ours; every refusal is a rule id.
        self.close_connection = True
        self._refuse(code, "signer.malformed", "the request is not well-formed HTTP")

    def do_GET(self) -> None:
        if urlsplit(self.path).path != "/":
            self._refuse(404, "signer.not-found")
            return
        service = self._listener.service
        secret = service.enrolment_secret()
        if secret is not None:
            self._send(200, render_enrolment(secret, service.key_fpr))
        else:
            self._send(200, render_listing(service.pending()))

    do_PUT = do_DELETE = do_PATCH = do_OPTIONS = do_GET

    def do_HEAD(self) -> None:
        self._refuse(404, "signer.not-found")

    def do_POST(self) -> None:
        action = _ROUTES.get(self.path)
        if action is None:
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
            if self.headers.get_content_type() != _FORM:
                raise ValueError
            form = parse_qs(body.decode("utf-8"), keep_blank_values=True)
            if any(len(v) != 1 for v in form.values()):
                raise ValueError
            fields = {k: v[0] for k, v in form.items()}
            # An absent code is the empty code: it is refused as a wrong one and spends the request's budget.
            code = fields.get("code", "")
            service = self._listener.service
            if action == "approved":
                service.approve(fields.get("request_id", ""), code)
            elif action == "declined":
                service.decline(fields.get("request_id", ""), code)
            else:
                service.enrol(code)
        except ValueError:
            self._refuse(400, "signer.malformed", "the form is not the one this endpoint takes")
            return
        except Refusal as r:
            self._refuse(403, r.rule, r.detail)
            return
        self._send(200, render_answer(action.capitalize(), _OUTCOME[action]))

    def finish(self) -> None:
        """Discard the body a refusal never read, then close (the reason is `http._Handler.finish`'s: closing a socket
        that holds unread bytes resets the connection and can destroy the answer in flight). Bounded by the body cap
        and the read timeout; nothing read here is parsed."""
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
        headers = getattr(self, "headers", None)
        if self._consumed or headers is None:
            return 0
        try:
            return max(0, int(headers.get("Content-Length", "0")))
        except ValueError:
            return 0


def page_tls_context(page: PageSettings) -> ssl.SSLContext:
    """The page proves it is the service and asks nothing of the peer: a phone browser has no client certificate.
    TLS 1.3 only, as the API's context is -- a browser from this decade negotiates it."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.verify_mode = ssl.CERT_NONE
    context.load_cert_chain(certfile=str(page.tls_certificate), keyfile=str(page.tls_key))
    return context


class PageListener(socketserver.ThreadingTCPServer):
    """As `http.Listener`: connections are wrapped in TLS inside their own thread, so a slow peer stalls its own
    thread and not the accept loop. Not a subclass of it: that listener's context and caller check are the API's."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, service: Service, cfg: Settings, page: PageSettings) -> None:
        self.service, self.settings = service, cfg
        self._context = page_tls_context(page)
        super().__init__((page.host, page.port), socketserver.BaseRequestHandler)

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
            tls.settimeout(self.settings.read_timeout_s)
            _PageHandler(tls, client_address, self)
        except (OSError, ValueError):
            return  # the peer's connection dies with the peer's mistake
        finally:
            tls.close()

    def close(self) -> None:
        self.shutdown()
        self.server_close()


def start_page(service: Service, cfg: Settings, page: PageSettings) -> PageListener:
    """Bind and serve in a daemon thread. The caller owns the listener and `close()`s it."""
    listener = PageListener(service, cfg, page)
    threading.Thread(target=listener.serve_forever, name="isidium-signer-page", daemon=True).start()
    return listener


# ---- the process ---------------------------------------------------------------------------------------------------


def _preflight(cfg: Settings, page: PageSettings) -> None:
    """Every file the listeners need is there, named when it is not. The TOTP secret and the state file are not
    checked: an absent secret opens enrolment, and an absent state is a first start."""
    for path in (cfg.tls_certificate, cfg.tls_key, cfg.ca, cfg.signing_key, page.tls_certificate, page.tls_key):
        if not path.is_file():
            raise Refusal("signer.missing-file", str(path), "the service cannot start without it")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="isidium-signer", description="The signing service and its code-entry page.")
    parser.add_argument("--settings", type=Path, required=True, help="the settings TOML file")
    args = parser.parse_args(argv)
    stop = threading.Event()
    api: http.Listener | None = None
    web: PageListener | None = None
    try:
        cfg = settings.load(args.settings)
        page = settings.load_page(args.settings)
        _preflight(cfg, page)
        service = Service(cfg, lambda: int(time.time()))
        api = http.start(service, cfg)
        web = start_page(service, cfg, page)
    except Refusal as r:
        if api is not None:
            api.close()
        print(f"isidium-signer: {r.rule} @ {r.path}: {r.detail}", file=sys.stderr)
        return 2
    except OSError as e:  # a certificate that does not load, a port that cannot be bound
        if api is not None:
            api.close()
        print(f"isidium-signer: signer.start @ : {type(e).__name__}: {e.strerror or ''}", file=sys.stderr)
        return 2
    enrolled = "yes" if service.enrolled else "no"
    listening = f"api={api.address[0]}:{api.address[1]} page={web.address[0]}:{web.address[1]}"
    print(f"isidium-signer: {listening} enrolled={enrolled}", file=sys.stderr, flush=True)
    signal.signal(signal.SIGTERM, lambda _s, _f: stop.set())
    signal.signal(signal.SIGINT, lambda _s, _f: stop.set())
    stop.wait()
    web.close()
    api.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
