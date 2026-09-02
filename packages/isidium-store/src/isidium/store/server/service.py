"""The store as a service (03b §2): one typed call surface over `Api`, one store container per tenant. The caller is
**authenticated by the credential the channel carries** — the client certificate of the mTLS connection, mapped to
`(principal, grant)` by the tenant registration; there is no header-carried identity and no anonymous call.

**The store terminates its own mTLS** (ruled 7bg.8). The certificate this module maps to a caller is read off the
very connection being authorized (`server/http.py`), never forwarded by a proxy: an identity that arrives as one
process's say-so is a perimeter in miniature, which is the shape the owner refused. There is no trusted hop, no
`X-Verified-Client-Cert`, and no ASGI server — neither uvicorn nor hypercorn 0.18 implements the ASGI TLS extension
(both verified by reading their source, 2026-08-27), and after 7bg.8 the store no longer asks one to.

This module is transport-free on purpose: `handle` is a plain function from a typed `Request` and the peer's
certificate to a typed `Response`, so the tests drive it with values and no socket, and the Rust port maps it one to
one. `server/http.py` is the only thing that knows about sockets.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from cryptography import x509

from ..core import telemetry
from ..core.disclosure import status_of
from ..core.refusal import Refusal
from .api import Api
from .identity import Caller, Grant

JSON: Final = "application/json"

# The refusal → HTTP status map used to live here, as fifteen rows beside nothing else. It is now one half of
# `core/disclosure.py`: a rule id's status and its disclosure are two facts about one thing, and kept in two maps
# they drift (C-4, C-12). Read the status off that table; do not grow a second one here.


@dataclass(frozen=True)
class Request:
    """One request, already parsed. `body` is the raw bytes; this layer does no protocol work."""

    method: str
    target: str
    body: bytes


@dataclass(frozen=True)
class Response:
    """One response. Always JSON — the store has no other representation."""

    status: int
    body: bytes

    @classmethod
    def json(cls, status: int, payload: Mapping[str, Any]) -> Response:
        return cls(status, json.dumps(payload, default=str, ensure_ascii=False).encode("utf-8"))

    @classmethod
    def refusal(cls, r: Refusal) -> Response:
        """The status from the table, the body from the refusal's own `payload()`.

        The body is **not** built here [K1b-iii]. `Refusal.payload` is the one constructor all three doors share
        (C-12's ruling, and the reason `McpServer._call` no longer builds its own dict), so a `ValidationRefusal`
        carries its typed verdicts through this door and the tool-call door alike, and the disclosure filter K2b
        added holds at every door at once instead of one of them. **Both halves come off the same row**: the status
        and the disclosure are one fact about one rule id (`core/disclosure.py`).
        """
        return cls.json(status_of(r.rule), r.payload())


@dataclass(frozen=True)
class Credential:
    """**What the connection presented, resolved exactly once** — at the edge, right after the handshake and before
    anything is parsed (Q1, Q4, ruled 2026-08-29).

    Three consumers need three different things from one certificate and none of them should re-parse it:
    `server/http.py` needs an admission key before it will read a byte; `caller_of` needs the principal and the
    grant; K2b needs the withheld parser text for the record. So the parse happens here, once, and everything
    downstream reads a field.

    `fingerprint` is SHA-256 **over the bytes the peer presented**, never over a re-encoding of them (the round trip
    through `x509` is the defect K6's trap names — a certificate that did not re-encode byte-identically would key
    two connections to two different peers). It is therefore available even when the certificate will not parse,
    which is the case that most needs a per-peer bound.

    `parse_error` is the certificate parser's own words. It is carried, never returned: C-12 says we ship no words we
    did not write, and an unidentified peer is exactly who this one would be shipped to. **K2b puts it in the
    record** — as a counter keyed on the class, not a row per connection (C-11: a record per hostile connection is a
    denial of service through the logging)."""

    fingerprint: str | None
    principal: str | None = None
    grant: Grant | None = None
    parse_error: str | None = None

    @property
    def present(self) -> bool:
        """A certificate arrived. The handshake should have guaranteed it; `caller_of` refuses if it did not."""
        return self.fingerprint is not None

    @property
    def registered(self) -> bool:
        """The registration names this certificate's subject. The CA-issued peer it does not name is its own class
        — the container's healthcheck, an orchestrator probe — with its own allowance (Q4)."""
        return self.principal is not None


class Registration:
    """The factory-side registration's client half (04 §5), by value: subject → (principal, grant). Nothing in a
    tenant repo names it.

    The certificate arrives as DER, which is what the connection hands over — no PEM round trip, no URL-decoding of
    a header, no encoding to get wrong."""

    def __init__(self, principals: Mapping[str, tuple[str, Grant]]) -> None:
        self.principals = dict(principals)

    def credential(self, cert_der: bytes | None) -> Credential:
        """One parse per connection, and the only one. A certificate that will not parse still gets a fingerprint,
        because the peer holding it still needs a per-peer allowance (Q4)."""
        if not cert_der:
            return Credential(None)
        fingerprint = hashlib.sha256(cert_der).hexdigest()
        try:
            cert = x509.load_der_x509_certificate(cert_der)
        except Exception as e:  # the parser names no closed set of failures, so neither can we
            return Credential(fingerprint, parse_error=f"{type(e).__name__}: {e}")
        subject = cert.subject.rfc4514_string()
        cn = next((a.value for a in cert.subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME)), None)
        for key in (subject, str(cn or "")):
            named = self.principals.get(key)
            if named is not None:
                return Credential(fingerprint, named[0], named[1])
        return Credential(fingerprint)


def _resource_of(args: Mapping[str, Any]) -> str:
    """The *resource* half of the journal's `subject / action / resource / context` vocabulary (03b §2), read off the
    call's typed arguments: the governed path when the call names one, else the card.

    **A path is an identifier, not content.** The journal already records paths as the resource; what C-11 keeps out
    of attributes is the document's *content*, its prose and key material, none of which is read here."""
    path = args.get("path")
    if isinstance(path, str):
        return path
    card = args.get("card", args.get("id"))
    return f"card:{card}" if isinstance(card, int) else ""


class Service:
    """The typed call surface. `POST /call/<name>` with a JSON body of the call's typed arguments; `GET /health`."""

    def __init__(self, api: Api, registration: Registration, tenant: str) -> None:
        self.api, self.registration, self.tenant = api, registration, tenant

    def caller_of(self, credential: Credential) -> Caller:
        """The caller is the credential the connection carries, and nothing else (03b §2).

        **Three authentication failures, and each is answered as one.** A certificate that would not parse used to
        reach the peer as `400 service.arguments` carrying the ASN.1 parser’s own text, because `caller_of` was
        called inside the block that catches `ValueError` — measured 2026-08-29, and the defect that motivated C-12.
        A certificate that will not parse is an *authentication* failure, and it is raised where it is parsed."""
        if not credential.present:
            raise Refusal(
                "auth.no-client-certificate",
                "",
                # This sentence is a **deployment diagnosis** and it does not go to the caller: `auth.*` is terse
                # (C-12), so it reaches the operator on stderr, where the operator is, via `telemetry.withheld`.
                "no client certificate on this connection: the store requires one issued by the CA named in the "
                "tenant registration, and the TLS handshake gates every byte before it. Reaching this refusal means "
                "the listener was built without CERT_REQUIRED — the store is misconfigured, not the caller.",
            )
        if credential.parse_error is not None:
            # Authored. The parser’s own words never reach the peer; they reach the record here (C-12), which is the
            # half K1b-ii left for this chunk — carried on the credential, and now landed.
            telemetry.note("auth.malformed-certificate", credential.parse_error)
            raise Refusal("auth.malformed-certificate", "", "the client certificate is not a certificate")
        if credential.principal is None or credential.grant is None:
            raise Refusal("auth.unknown-client", "", "no registration entry for this certificate")
        return Caller(credential.principal, credential.grant)

    def handle(self, request: Request, credential: Credential) -> Response:
        """One call, and **one span** — the second of C-11's two phases (`server/http.py` opens the first).

        The span's attributes are the journal's own vocabulary (03b §2): the principal is the *subject*, the verb is
        the *action*, the path or card the arguments name is the *resource*. The outcome is the span's status and the
        rule id is an attribute (C-11) — both set by `Refusal.payload()`, which every refusal passes through, so no
        branch below has to remember to record itself."""
        call = request.target[len("/call/") :] if request.target.startswith("/call/") else ""
        with telemetry.span(telemetry.CALL_SPAN, **{telemetry.TENANT: self.tenant, telemetry.ACTION: call}) as sp:
            if request.method in ("GET", "HEAD") and request.target == "/health":
                # liveness only: the tenant’s name is not published, even to a peer the CA vouched for (the review’s
                # S8). `HEAD` gets the same status and the same headers and no body — the framing is `_respond`’s.
                telemetry.record_ok()
                return Response.json(200, {"ok": True})
            if not request.target.startswith("/call/") or request.method != "POST":
                # The target is the caller's own string and it does not come back: `service.route` is terse, so the
                # target reaches the record and not the response (C-12).
                return Response.refusal(Refusal("service.route", "", request.target))
            try:
                caller = self.caller_of(credential)
                sp.set_attribute(telemetry.SUBJECT, caller.principal)
                sp.set_attribute(telemetry.GRANT, caller.grant)
                args = json.loads(request.body or b"{}")
                if not isinstance(args, dict):
                    raise Refusal("service.body", "", "a JSON object of typed arguments")
                sp.set_attribute(telemetry.RESOURCE, _resource_of(args))
                result = self.api.call(call, caller, args)
                telemetry.record_ok()
                return Response.json(200, {"result": result})
            except Refusal as r:
                return Response.refusal(r)
            except (KeyError, ValueError, TypeError) as e:  # a malformed call is data too
                # **Authored, then full** (C-12). What went back was `str(e)[:200]` — Python's words, not ours, and
                # the only responses whose content we did not write. The exception goes to the record; the caller
                # gets a sentence we wrote, about their own request, which is the half that is theirs.
                telemetry.note("service.arguments", f"{type(e).__name__}: {e}")
                return Response.refusal(
                    Refusal("service.arguments", "", "the arguments are not the typed arguments this call takes")
                )
            except Exception as e:
                # A bug is not a refusal, and it is not silence either. Before this, anything outside the five types
                # above escaped `handle` *and* `_connection`, and the caller got an opened-then-closed connection
                # with no status and no rule id — indistinguishable on the wire from a refused handshake (measured
                # 2026-08-29). The caller gets a rule id (C-5) and nothing else; the exception belongs to the record
                # (C-12), where it now lands, and to the failing span's status.
                telemetry.note("service.internal", f"{type(e).__name__}: {e}")
                return Response.refusal(Refusal("service.internal"))
