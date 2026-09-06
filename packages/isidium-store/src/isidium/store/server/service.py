"""The store as a service (03b §2): one typed call surface over `Api`, one store container per tenant. The caller is
**authenticated by the credential the channel carries** — the client certificate of the mTLS connection, mapped to
`(principal, grant)` by the tenant registration; there is no header-carried identity and no anonymous call.

**The store terminates its own mTLS** (ruled 7bg.8). The certificate this module maps to a caller is read off the
very connection being authorized (`server/http.py`), never forwarded by a proxy: an identity that arrives as one
process's say-so is a perimeter in miniature, which is the shape the owner refused. There is no trusted hop, no
`X-Verified-Client-Cert`, and no ASGI server — neither uvicorn nor hypercorn 0.18 implements the ASGI TLS extension
(both verified by reading their source, 2026-08-27), and after 7bg.8 the store no longer asks one to.

**Four caller-identity properties, one file** [K6, H-1 — the deployment record §1, and Q5]: the store checks the
certificate's **validity window** itself, requires the **`clientAuth`** extended key usage, matches the **full
subject** and never a bare common name, and reads the registration from a **file it re-reads**, so revoking a caller
is an edit rather than a rebuild. The fingerprint the journal row records is `Credential.fingerprint`, resolved here.

This module is transport-free on purpose: `handle` is a plain function from a typed `Request` and the peer's
certificate to a typed `Response`, so the tests drive it with values and no socket, and the Rust port maps it one to
one. `server/http.py` is the only thing that knows about sockets.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from cryptography import x509
from cryptography.x509.oid import ExtendedKeyUsageOID

from ..core import telemetry
from ..core.disclosure import status_of
from ..core.refusal import Refusal
from .api import Api
from .identity import GRANTS, Caller, Grant

JSON: Final = "application/json"
Clock = Callable[[], int]

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

    @classmethod
    def unidentified(cls, r: Refusal) -> Response:
        """A refusal to a peer the registration has not named [K7b, Q19]: counted, the words on the span, no row.
        The route a stranger asked for and the `auth.*` family come through here; nothing after `caller_of`."""
        return cls.json(status_of(r.rule), r.unidentified())

    @classmethod
    def admission(cls, r: Refusal) -> Response:
        """A refusal at admission [K7b, F16]: the body through the filter and **not** through `payload()`. The event
        is already counted, on `connection.refused` by the bound that was met; `payload()` would count it a second
        time on `isidium.store.refusal` — one event, two counters, and a dashboard summing refusals double-counts
        every admission — and would set the status of a span that is not open yet, which is the invalid no-op."""
        return cls.json(status_of(r.rule), r.disclosed())


@dataclass(frozen=True)
class Credential:
    """**What the connection presented, resolved exactly once** — at the edge, right after the handshake and before
    anything is parsed (Q1, Q4, ruled 2026-08-29).

    Three consumers need three different things from one certificate and none of them should re-parse it:
    `server/http.py` needs an admission key before it will read a byte; `caller_of` needs the principal and the
    grant; K2b needs the withheld parser text for the record. So the parse happens here, once, and everything
    downstream reads a field.

    `fingerprint` is SHA-256 **over the bytes the peer presented**, never over a re-encoding of them (the round trip
    through `x509` was the defect K6's trap named — a certificate that did not re-encode byte-identically would key
    two connections to two different peers). It is therefore available even when the certificate will not parse,
    which is the case that most needs a per-peer bound. It is also what the journal row records [K6]: the row
    carries `sha256:<this>` beside the principal, so that after a rotation the record still says *which* certificate
    asserted the name.

    `parse_error` is the certificate parser's own words. It is carried, never returned: C-12 says we ship no words we
    did not write, and an unidentified peer is exactly who this one would be shipped to. **K2b puts it in the
    record** — as a counter keyed on the class, not a row per connection (C-11: a record per hostile connection is a
    denial of service through the logging).

    `refusal` [K6] is why a certificate that *did* parse is still not a credential: outside its validity window, or
    issued without `clientAuth`. It is built where the certificate is read, with a literal rule id at each site so
    the rule-id sweep sees it, and raised by `caller_of`. **Such a certificate resolves to no principal**, so nothing
    downstream can act on a name a defective certificate asserted, and the edge keys its allowance on the fingerprint
    like any other unregistered peer."""

    fingerprint: str | None
    principal: str | None = None
    grant: Grant | None = None
    parse_error: str | None = None
    refusal: Refusal | None = None

    @property
    def present(self) -> bool:
        """A certificate arrived. The handshake should have guaranteed it; `caller_of` refuses if it did not."""
        return self.fingerprint is not None

    @property
    def registered(self) -> bool:
        """The registration names this certificate's subject. The CA-issued peer it does not name is its own class
        — the container's healthcheck, an orchestrator probe — with its own allowance (Q4)."""
        return self.principal is not None


Principals = dict[str, tuple[str, Grant]]


def parse_registration(text: str) -> Principals:
    """The registration file's shape, checked: `{"<subject>": ["<principal>", "<grant>"]}` where the subject is the
    certificate's **whole** subject in RFC 4514 form (`CN=…,O=…` — what `openssl x509 -noout -subject -nameopt
    RFC2253` prints after `subject=`), the principal is non-empty and the grant is one of the three.

    Refuses the whole file on the first defect rather than keeping the well-formed rows: a registration that is
    partly readable is a registration whose revocations may be the unreadable part."""
    raw = json.loads(text)
    if not isinstance(raw, dict):
        raise ValueError("the registration is a JSON object keyed by certificate subject")
    out: Principals = {}
    for subject, named in raw.items():
        if not isinstance(subject, str) or not subject:
            raise ValueError("a registration key is the certificate's subject, a non-empty string")
        if not (isinstance(named, list) and len(named) == 2 and all(isinstance(x, str) for x in named)):
            raise ValueError(f"{subject!r}: the value is [principal, grant]")
        principal, grant = named
        if not principal:
            raise ValueError(f"{subject!r}: the principal is empty")
        typed = _GRANT_OF.get(grant)
        if typed is None:
            raise ValueError(f"{subject!r}: {grant!r} is not one of {GRANTS}")
        out[subject] = (principal, typed)
    return out


# `str` → `Grant`, so a file's string becomes the typed value at the one place it is read (C-2), with no cast.
_GRANT_OF: Final[Mapping[str, Grant]] = {g: g for g in GRANTS}


class Registration:
    """The factory-side registration's client half (04 §5), by value: subject → (principal, grant). Nothing in a
    tenant repo names it.

    The certificate arrives as DER, which is what the connection hands over — no PEM round trip, no URL-decoding of
    a header, no encoding to get wrong.

    **The clock is supplied, never read here** (C-1): the validity window is checked against it, and a test hands
    in a clock so the check is proven on a certificate the handshake would also refuse — the check exists for the
    day the seam is the realm provider and there is no handshake in front of it (K6's second trap).

    **From a file, re-read on change** [K6, H-1 item 4]. `from_file` remembers the file and its stamp; every
    `credential()` compares the stamp (one `stat`, ~10 µs, once per connection — connections are a handful a day)
    and re-parses only when it moved, so revoking a caller is an edit to `registration.json` and the next connection
    sees it. **A file that will not parse names nobody**: the store fails closed rather than serving the last good
    mapping, because the row an operator just mistyped may be the revocation, and a store that quietly kept serving
    the old mapping would have undone it. The words go to the record; every caller meets `auth.unknown-client`
    until the file parses again."""

    def __init__(self, principals: Mapping[str, tuple[str, Grant]], clock: Clock) -> None:
        self.principals = dict(principals)
        self.clock = clock
        self._path: Path | None = None
        self._stamp: tuple[int, int, int] | None = None

    @classmethod
    def from_file(cls, path: str | Path, clock: Clock) -> Registration:
        """Loaded now — a registration that will not parse at start-up stops the store before it listens — and
        re-read on change afterwards."""
        p = Path(path)
        reg = cls(parse_registration(p.read_text(encoding="utf-8")), clock)
        reg._path, reg._stamp = p, _stamp(p)
        return reg

    def _refresh(self) -> None:
        if self._path is None:
            return
        # **The stat is inside the failure arm too** [K7a, F4]. It sat outside it, so a registration that was
        # deleted or replaced by rename raised `FileNotFoundError` out of `credential()` into the connection
        # handler's `except OSError` — every connection, `/health` included, died with no counter, no span and no
        # row. An absent file is the same case as one that will not parse: it names nobody, once, in the record,
        # and every caller then meets `auth.unknown-client`, which is what `deploy/README.md` promises.
        try:
            stamp: tuple[int, int, int] | None = _stamp(self._path)
        except OSError:
            stamp = None
        if stamp == self._stamp:
            return
        self._stamp = stamp
        try:
            self.principals = parse_registration(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            self.principals = {}
            telemetry.note(
                "auth.unknown-client",
                f"the registration at {self._path} is absent or no longer parses and names nobody until it does: "
                f"{type(e).__name__}: {e}",
            )

    def credential(self, cert_der: bytes | None) -> Credential:
        """One parse per connection, and the only one. A certificate that will not parse still gets a fingerprint,
        because the peer holding it still needs a per-peer allowance (Q4)."""
        if not cert_der:
            return Credential(None)
        self._refresh()
        fingerprint = hashlib.sha256(cert_der).hexdigest()
        try:
            cert = x509.load_der_x509_certificate(cert_der)
        except Exception as e:  # the parser names no closed set of failures, so neither can we
            return Credential(fingerprint, parse_error=f"{type(e).__name__}: {e}")
        # **The full subject, never the bare common name** [K6, H-1 item 3]. The key is the RFC 4514 string of the
        # whole name, so a certificate that carries a registered common name in any other position, or beside any
        # other attribute, is a stranger. The bare-CN fallback that stood here accepted anything the CA would issue
        # with that name anywhere in the subject.
        subject = cert.subject.rfc4514_string()
        refusal = _defect(cert, subject, self.clock())
        if refusal is not None:
            return Credential(fingerprint, refusal=refusal)
        named = self.principals.get(subject)
        if named is None:
            return Credential(fingerprint)
        return Credential(fingerprint, named[0], named[1])


def _stamp(path: Path) -> tuple[int, int, int]:
    st = os.stat(path)
    return st.st_mtime_ns, st.st_size, st.st_ino


def _at(t: _dt.datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")  # spelled out: `%F`/`%T` are not portable strftime directives


def _defect(cert: x509.Certificate, subject: str, now: int) -> Refusal | None:
    """Why a certificate that parsed is not a credential — or `None`. Each detail is the operator's diagnosis and
    goes to the record, never to the peer (`auth.*` is terse, C-12)."""
    not_before = int(cert.not_valid_before_utc.timestamp())
    not_after = int(cert.not_valid_after_utc.timestamp())
    # **Checked here even though the handshake already did** [K6's second trap]: after K1 it is the same connection,
    # and the check is what keeps this seam portable to the realm provider, which hands over a certificate with no
    # handshake in front of it. RFC 5280's window is inclusive at both ends.
    if now < not_before:
        return Refusal("auth.not-yet-valid", "", f"{subject}: not valid before {_at(cert.not_valid_before_utc)}")
    if now > not_after:
        return Refusal("auth.expired", "", f"{subject}: not valid after {_at(cert.not_valid_after_utc)}")
    # **`clientAuth` is required** [Q5, ruled 2026-08-29]: a leaf the CA issued for another purpose — a web server's,
    # say — is not a store credential. An absent extension is an absent `clientAuth`. `KeyUsage` is deliberately
    # not checked (the same ruling): `clientAuth` is the extension that says what the certificate is *for*.
    try:
        eku = cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
    except x509.ExtensionNotFound:
        return Refusal("auth.no-client-auth", "", f"{subject}: no extended key usage extension")
    if ExtendedKeyUsageOID.CLIENT_AUTH not in eku:
        return Refusal("auth.no-client-auth", "", f"{subject}: extended key usage does not include clientAuth")
    return None


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
        A certificate that will not parse is an *authentication* failure, and it is raised where it is parsed.
        K6 adds the fourth and fifth — a certificate outside its window, one without `clientAuth` — built where the
        certificate is read (`_defect`) and raised here."""
        if not credential.present:
            # This sentence is a **deployment diagnosis** and it does not go to the caller: `auth.*` is terse
            # (C-12). It is the one pre-identification refusal that still writes a row [K7b, Q19]: the condition is
            # the store's own — a listener built without `CERT_REQUIRED` — and no peer can produce it against one
            # `serve` built, so it is not the peer-driven surface the ruling moves to the span, and an operator
            # with no exporter must still see it on stderr, once per connection of a store that is broken anyway.
            diagnosis = (
                "no client certificate on this connection: the store requires one issued by the CA named in the "
                "tenant registration, and the TLS handshake gates every byte before it. Reaching this refusal means "
                "the listener was built without CERT_REQUIRED — the store is misconfigured, not the caller."
            )
            telemetry.note("auth.no-client-certificate", diagnosis)
            raise Refusal("auth.no-client-certificate", "", diagnosis)
        if credential.parse_error is not None:
            # Authored. The parser’s own words never reach the peer; since K7b (Q19) they reach the **span**, cut to
            # the bound, and not the record — a peer holding a certificate this CA issued is not yet a caller, and
            # a row per attempt is what C-11 forbids. The detail is the diagnosis; `unidentified()` places it.
            raise Refusal("auth.malformed-certificate", "", credential.parse_error)
        if credential.refusal is not None:
            raise credential.refusal
        if credential.principal is None or credential.grant is None or credential.fingerprint is None:
            raise Refusal("auth.unknown-client", "", "no registration entry for this certificate")
        # `sha256:` because the row outlives the certificate: a record meant to say *which* credential asserted a
        # name after that credential is gone should also say how it was digested (the spelling `h` and `build` use).
        return Caller(credential.principal, credential.grant, credential="sha256:" + credential.fingerprint)

    @staticmethod
    def is_liveness(request: Request) -> bool:
        """`GET /health` and `HEAD /health` — the probe, answered from a constant and never from the store. Named
        once here because two layers read it: `handle` below answers it, and `server/http.py` keeps it on the event
        loop instead of queueing it behind the one call worker [K7b, Q15], which is what makes the healthcheck
        honest about the listener while a ratify waits on the signer."""
        return request.method in ("GET", "HEAD") and request.target == "/health"

    def handle(self, request: Request, credential: Credential) -> Response:
        """One call, and **one span** — the second of C-11's two phases (`server/http.py` opens the first).

        The span's attributes are the journal's own vocabulary (03b §2): the principal is the *subject*, the verb is
        the *action*, the path or card the arguments name is the *resource*. The outcome is the span's status and the
        rule id is an attribute (C-11) — both set by `Refusal.payload()`, which every refusal passes through, so no
        branch below has to remember to record itself.

        **Two refusals are answered before a principal is named, and they take the other door** [K7b, Q19, ruled
        2026-09-06]: a target that is not a call, and a credential `caller_of` will not turn into a caller. Both go
        through `Response.unidentified` — counted like any refusal, the words on the span cut to a bound, and never a
        row — because the peer at that point holds a certificate this CA issued and nothing more, which is the
        healthcheck's class and a leaked probe certificate's, and either can drive these at will."""
        call = request.target[len("/call/") :] if request.target.startswith("/call/") else ""
        with telemetry.span(telemetry.CALL_SPAN, **{telemetry.TENANT: self.tenant, telemetry.ACTION: call}) as sp:
            if self.is_liveness(request):
                # liveness only: the tenant’s name is not published, even to a peer the CA vouched for (the review’s
                # S8). `HEAD` gets the same status and the same headers and no body — the framing is `_respond`’s.
                telemetry.record_ok()
                return Response.json(200, {"ok": True})
            if not request.target.startswith("/call/") or request.method != "POST":
                # The target is the caller's own string and it does not come back: `service.route` is terse, so the
                # target reaches the span — bounded — and not the response (C-12), and not a row (Q19).
                return Response.unidentified(Refusal("service.route", "", request.target))
            try:
                caller = self.caller_of(credential)
            except Refusal as r:
                return Response.unidentified(r)
            try:
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
            except (KeyError, ValueError, TypeError, RecursionError) as e:  # a malformed call is data too
                # **Authored, then full** (C-12). What went back was `str(e)[:200]` — Python's words, not ours, and
                # the only responses whose content we did not write. The exception goes to the record; the caller
                # gets a sentence we wrote, about their own request, which is the half that is theirs.
                # `RecursionError` is a body nested past the parser's depth [K7b, F12]: the caller's, not a bug.
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
