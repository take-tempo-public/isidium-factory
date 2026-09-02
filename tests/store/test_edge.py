"""The store's own TLS edge (K1, ruled 7bg.8; reshaped by Q1 and Q4, 2026-08-29), over a real socket.

The claim this file exists to prove is the one the whole shape rests on: **the mTLS handshake gates every byte.** A
peer without a certificate the registration's CA issued never reaches the parser, never reaches the store, and is not
merely refused politely afterwards. `test_service.py` proves what the store does with a caller it has; this proves
what never becomes a caller at all.

**Every limit here is mutation-checked and none of them may pass on silence.** Five of the six limits K1 declared
were untested and survived mutation (measured 2026-08-29), and two assertions in the first version of this file —
`assert answer is None or status_of(answer) == 431` and `assert result == b""` — accepted "nothing came back", which
is exactly what a missing limit produces. Every limit below therefore asserts something only the working property
produces: a status *and* a rule id, a refusal *and* its typed reason, an end *and* the time it took.

Everything here runs against a listener bound on `127.0.0.1`, with a certificate authority made in the fixture — no
openssl, no network, no fixtures on disk beyond the temporary directory.
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import ipaddress
import json
import ssl
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from isidium.store.core import telemetry
from isidium.store.server import http
from isidium.store.server.api import Api
from isidium.store.server.http import Limits, Refused, start, tls_context
from isidium.store.server.identity import Caller
from isidium.store.server.service import Credential, Registration, Request, Response, Service

from .conftest import Harness, Telemetry, fresh

NOW = _dt.datetime(2026, 8, 27, tzinfo=_dt.UTC)
# An absence needs a window: the server finishes its half of a refused connection after the client has
# given up, so the count is read once that half has had time to happen.
_SETTLE = 0.25
CRLF = bytes([13, 10])  # the wire's line ending, spelled as bytes so no editor can normalise it away


# ---- a certificate authority, made here --------------------------------------------------------------------------


@dataclass(frozen=True)
class Authority:
    key: ec.EllipticCurvePrivateKey
    certificate: x509.Certificate
    path: Path


def _name(common_name: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])


def _write(path: Path, certificate: x509.Certificate, key: ec.EllipticCurvePrivateKey | None = None) -> Path:
    data = certificate.public_bytes(serialization.Encoding.PEM)
    if key is not None:
        data += key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    path.write_bytes(data)
    return path


def authority(directory: Path, common_name: str) -> Authority:
    key = ec.generate_private_key(ec.SECP256R1())
    certificate = (
        x509.CertificateBuilder()
        .subject_name(_name(common_name))
        .issuer_name(_name(common_name))
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(NOW - _dt.timedelta(days=1))
        .not_valid_after(NOW + _dt.timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        # These are what a CA needs for a client running with `VERIFY_X509_STRICT` — which is a **flag the client
        # sets**, not an OpenSSL version, and the store sets it on nothing. The line that used to sit here said
        # "OpenSSL 3.5 enforces RFC 5280 strictly, so without them the chain does not verify at all"; it reached a
        # ratified record and it is wrong. Measured 2026-08-29, one variable at a time: same certificates, flag
        # cleared, everything connects. The requirements land on the CA and on the store's own certificate, for the
        # caller's benefit — the deployment record's S-1 … S-3 carry what was measured.
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .add_extension(
            x509.KeyUsage(
                digital_signature=False,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )
    return Authority(key, certificate, _write(directory / f"{common_name}.ca.pem", certificate))


def issue(
    ca: Authority, directory: Path, common_name: str, label: str, *, server: bool = False, expired: bool = False
) -> tuple[Path, Path]:
    """A leaf the authority signs. `expired` puts the whole validity window in the past — the one input that is
    valid in every way except time.

    `label` names the files, and is not the subject: three of these deliberately share one common name (the same
    caller, from the wrong authority, and out of date), and a shared filename would silently overwrite them into one
    certificate — a green test proving nothing."""
    key = ec.generate_private_key(ec.SECP256R1())
    start_at = NOW - _dt.timedelta(days=400) if expired else NOW - _dt.timedelta(days=1)
    end_at = NOW - _dt.timedelta(days=300) if expired else NOW + _dt.timedelta(days=365)
    builder = (
        x509.CertificateBuilder()
        .subject_name(_name(common_name))
        .issuer_name(ca.certificate.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(start_at)
        .not_valid_after(end_at)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca.key.public_key()), critical=False)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH if server else ExtendedKeyUsageOID.CLIENT_AUTH]),
            critical=False,
        )
    )
    if server:
        builder = builder.add_extension(
            x509.SubjectAlternativeName(
                [x509.DNSName("localhost"), x509.IPAddress(ipaddress.IPv4Address("127.0.0.1"))]
            ),
            critical=False,
        )
    certificate = builder.sign(ca.key, hashes.SHA256())
    return _write(directory / f"{label}.crt.pem", certificate), _write(directory / f"{label}.key.pem", certificate, key)


# ---- the listener under test -------------------------------------------------------------------------------------


class Recording(Service):
    """A service that counts how many requests reach it. Zero is the assertion in every refusal case here."""

    def __init__(self, api: Api, registration: Registration, tenant: str) -> None:
        super().__init__(api, registration, tenant)
        self.seen: list[Request] = []

    def handle(self, request: Request, credential: Credential) -> Response:
        self.seen.append(request)
        return super().handle(request, credential)


@dataclass(frozen=True)
class Edge:
    service: Recording
    context: ssl.SSLContext
    ca: Authority
    other_ca: Authority
    owner: tuple[Path, Path]
    stranger: tuple[Path, Path]
    expired: tuple[Path, Path]
    probe: tuple[Path, Path]
    harness: Harness


@pytest.fixture(scope="module")
def edge(tmp_path_factory: pytest.TempPathFactory) -> Edge:
    directory = tmp_path_factory.mktemp("edge")
    ca = authority(directory, "tenant-ca")
    other_ca = authority(directory, "some-other-ca")
    server_cert, server_key = issue(ca, directory, "store.sartor", "store", server=True)
    harness = fresh("edge")
    registration = Registration({"owner@example": ("amodal1@example", "owner")})
    return Edge(
        service=Recording(Api(harness.st), registration, harness.st.tenant),
        context=tls_context(server_cert, server_key, ca.path),
        ca=ca,
        other_ca=other_ca,
        owner=issue(ca, directory, "owner@example", "owner"),
        # the same subject the registration names, from the wrong authority and out of date: the two
        # inputs that are wrong in exactly one way each
        stranger=issue(other_ca, directory, "owner@example", "stranger"),
        expired=issue(ca, directory, "owner@example", "expired", expired=True),
        # the CA-issued peer the registration does not name: the healthcheck, an orchestrator probe (Q4)
        probe=issue(ca, directory, "healthcheck@probes.example", "probe"),
        harness=harness,
    )


def client_context(ca: Authority, credential: tuple[Path, Path] | None) -> ssl.SSLContext:
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=str(ca.path))
    if credential is not None:
        context.load_cert_chain(str(credential[0]), str(credential[1]))
    return context


def raw(method: str, target: str, body: bytes = b"", extra: bytes = b"") -> bytes:
    head = f"{method} {target} HTTP/1.1\r\nHost: localhost\r\n".encode()
    return head + f"Content-Length: {len(body)}\r\n".encode() + extra + b"\r\n" + body


async def attempt(port: int, context: ssl.SSLContext, request: bytes) -> bytes | None:
    """Connect, send, read. `None` means the peer never got an answer — a refused handshake or a closed connection."""
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection("127.0.0.1", port, ssl=context, server_hostname="localhost"), 10
        )
    except (ssl.SSLError, OSError, TimeoutError):
        return None
    try:
        writer.write(request)
        await writer.drain()
        answer = await asyncio.wait_for(reader.read(), 10)
        return answer or None
    except (ssl.SSLError, OSError, TimeoutError):
        return None
    finally:
        writer.close()


async def hold(port: int, context: ssl.SSLContext) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """One connection that completes the handshake and then holds a slot: a request line it never terminates, which
    is exactly what the measured outage did (Q4). The caller closes it."""
    reader, writer = await asyncio.wait_for(
        asyncio.open_connection("127.0.0.1", port, ssl=context, server_hostname="localhost"), 10
    )
    writer.write(b"GET /health HTTP/1.1\r\nHost: localhost\r\n")  # no terminating CRLF: h11 will want more
    await writer.drain()
    return reader, writer


def against(edge: Edge, body: Callable[[int], Awaitable[Any]], limits: Limits | None = None) -> Any:
    """Run one scenario against a freshly bound listener."""

    async def run() -> Any:
        asyncio.get_running_loop().set_exception_handler(lambda _loop, _context: None)  # refused handshakes are data
        server = await start(edge.service, "127.0.0.1", 0, edge.context, limits or Limits())
        port = int(server.sockets[0].getsockname()[1])
        try:
            return await body(port)
        finally:
            server.close()
            await server.wait_closed()

    return asyncio.run(run())


def status_of(answer: bytes | None) -> int:
    assert answer is not None, "the peer got no answer"
    return int(answer.split(b" ", 2)[1])


def payload(answer: bytes | None) -> dict[str, Any]:
    assert answer is not None, "the peer got no answer"
    return dict(json.loads(answer.split(b"\r\n\r\n", 1)[1]))


def refusals(monkeypatch: pytest.MonkeyPatch) -> list[Refused]:
    """The typed reasons the edge classified, read at the one call site Q1 leaves for K2b's counter."""
    seen: list[Refused] = []
    monkeypatch.setattr(http, "_refused", lambda reason, peer: seen.append(reason))
    return seen


# ---- the boundary ------------------------------------------------------------------------------------------------


def test_the_handshake_gates_every_byte(edge: Edge, monkeypatch: pytest.MonkeyPatch) -> None:
    """No certificate, the wrong authority, and an expired certificate: for each, **the handshake refuses**, the
    store's request path is never entered, and the refusal carries the reason it was refused for.

    Why the assertion is on the server and not on what the peer sees: under TLS 1.3 the client completes its own
    half of the handshake before the server has looked at the client certificate, so the server's alert arrives
    afterwards and the peer cannot tell a refused certificate from any other closed connection. Measured, not
    assumed. Asserting from the client side would therefore pass with `CERT_OPTIONAL` too — which is to say it would
    prove nothing.

    **The discriminator, and the mutation it survives** (Q1's conditions a and b): with `CERT_REQUIRED` the
    uncertificated peer produces `Refused.NO_CERTIFICATE`; with `CERT_OPTIONAL` its handshake *succeeds*, so no
    refusal is classified at all and the first assertion fails. Under the old shape this test counted invocations of
    `_connection`, which no longer distinguishes anything — the store now answers the TCP connection itself, so
    `_connection` runs for every peer. The property is re-proven under the new shape, not assumed to have survived
    it, and each class is asserted by name rather than merely counted."""
    seen = refusals(monkeypatch)
    before = len(edge.service.seen)

    async def scenario(port: int) -> tuple[list[Refused], int]:
        for credential in (None, edge.stranger, edge.expired):
            await attempt(port, client_context(edge.ca, credential), raw("GET", "/health"))
        await asyncio.sleep(_SETTLE)  # the server's half outlives the client's: give an absence room to appear
        refused = list(seen)
        answer = await attempt(port, client_context(edge.ca, edge.owner), raw("GET", "/health"))
        return refused, status_of(answer)

    refused, good = against(edge, scenario)
    assert refused == [Refused.NO_CERTIFICATE, Refused.UNTRUSTED_ISSUER, Refused.EXPIRED], refused
    assert len(edge.service.seen) - before == 1, "a peer without a certificate this CA issued reached the store"
    assert good == 200, "the listener answers a certificate the CA did issue"


def test_a_peer_that_completes_tcp_and_says_nothing_meets_the_handshake_timeout(
    edge: Edge, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Q1's third condition. asyncio applied this timeout before; the store passes it now, so it is the store's to
    prove. The discriminator is the reason **and** the clock: with the timeout not passed the connection is held
    open and the client's own five-second wait fires instead, which is a different fact and a failing one."""
    seen = refusals(monkeypatch)

    async def scenario(port: int) -> tuple[float, bytes, list[Refused]]:
        started = time.monotonic()
        reader, writer = await asyncio.open_connection("127.0.0.1", port)  # plain TCP, never a TLS byte
        try:
            got = await asyncio.wait_for(reader.read(), 5)
        finally:
            writer.close()
        await asyncio.sleep(_SETTLE)
        return time.monotonic() - started, got, list(seen)

    elapsed, got, refused = against(edge, scenario, Limits(handshake_timeout=0.5))
    assert refused == [Refused.TIMEOUT], refused
    assert got == b"" and elapsed < 3.0, f"the store held a silent peer for {elapsed:.2f}s"


def test_a_certificate_the_authority_issued_is_answered(edge: Edge) -> None:
    async def scenario(port: int) -> bytes | None:
        return await attempt(port, client_context(edge.ca, edge.owner), raw("GET", "/health"))

    answer = against(edge, scenario)
    assert status_of(answer) == 200 and payload(answer) == {"ok": True}


def test_head_health_is_answered_with_headers_and_no_body(edge: Edge) -> None:
    """A health checker configured with `HEAD` used to report the store down with no diagnosis anywhere: `_respond`
    always sent a `h11.Data` frame, h11 forbids a body on a response to `HEAD`, and the `LocalProtocolError` was
    swallowed by a branch whose comment said the peer had never completed a request (measured 2026-08-29).

    The discriminator is the pair: a 200 **with** a `Content-Length` header and **without** a body. Asserting only
    that something came back would pass on a response that carried a body h11 should have forbidden."""

    async def scenario(port: int) -> bytes | None:
        return await attempt(port, client_context(edge.ca, edge.owner), raw("HEAD", "/health"))

    answer = against(edge, scenario)
    assert answer is not None, "HEAD /health got no answer at all"
    head, _, body = answer.partition(b"\r\n\r\n")
    assert status_of(answer) == 200
    assert b"content-length: 12" in head.lower(), head
    assert body == b"", f"a response to HEAD carried a body: {body!r}"


def test_a_call_over_the_socket_is_the_call(edge: Edge) -> None:
    """The same verb, the same arguments, the same answer as the in-process call — the edge adds nothing but the
    caller's identity."""
    direct = Api(edge.harness.st).call("show", Caller("amodal1@example", "owner"), {"target": "queue"})

    async def scenario(port: int) -> bytes | None:
        body = json.dumps({"target": "queue"}).encode()
        return await attempt(port, client_context(edge.ca, edge.owner), raw("POST", "/call/show", body))

    answer = against(edge, scenario)
    assert status_of(answer) == 200
    assert json.loads(json.dumps(payload(answer)["result"], default=str)) == json.loads(json.dumps(direct, default=str))


def test_an_unexpected_exception_still_answers_with_a_rule_id(edge: Edge, monkeypatch: pytest.MonkeyPatch) -> None:
    """`_connection` caught four exception types and `handle` caught five; anything else — a `RuntimeError`, an
    `AttributeError`, a bug — escaped both and the caller got an opened-then-closed connection with no status and no
    rule id, indistinguishable on the wire from a refused handshake (measured 2026-08-29).

    The server surviving is right; the silence is not. The discriminator is a status and a rule id, and the absence
    of any word we did not write (C-12): the exception's own text belongs to the record, which is K2b's."""
    monkeypatch.setattr(Api, "call", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("a bug, not a refusal")))

    async def scenario(port: int) -> bytes | None:
        body = json.dumps({"target": "queue"}).encode()
        return await attempt(port, client_context(edge.ca, edge.owner), raw("POST", "/call/show", body))

    answer = against(edge, scenario)
    assert status_of(answer) == 500
    assert payload(answer) == {"rule": "service.internal"}
    assert b"a bug, not a refusal" not in (answer or b""), "the exception's own text reached the caller"


def test_one_request_per_connection(edge: Edge) -> None:
    """`Connection: close` on every response, and the connection really does end — there is no keep-alive state
    machine to get wrong."""

    async def scenario(port: int) -> tuple[bytes, bytes]:
        reader, writer = await asyncio.open_connection(
            "127.0.0.1", port, ssl=client_context(edge.ca, edge.owner), server_hostname="localhost"
        )
        writer.write(raw("GET", "/health"))
        await writer.drain()
        first = await asyncio.wait_for(reader.read(), 10)
        writer.write(raw("GET", "/health"))
        try:
            await writer.drain()
            second = await asyncio.wait_for(reader.read(), 5)
        except (ssl.SSLError, OSError, TimeoutError):
            second = b""
        writer.close()
        return first, second

    first, second = against(edge, scenario)
    assert b"connection: close" in first.lower()
    assert b"200" in first.split(b"\r\n", 1)[0], first
    assert second == b"", "the connection stayed open for a second request"


# ---- framing -----------------------------------------------------------------------------------------------------


def test_chunked_transfer_is_refused(edge: Edge) -> None:
    """Every client is ours and sends a length. Refusing chunked removes a whole framing mode — and with it the
    framing the smuggling class is built on — from a surface that has no use for it."""

    async def scenario(port: int) -> bytes | None:
        body = json.dumps({"target": "queue"}).encode()
        request = (
            b"POST /call/show HTTP/1.1\r\nHost: localhost\r\nTransfer-Encoding: chunked\r\n\r\n"
            + f"{len(body):x}\r\n".encode()
            + body
            + b"\r\n0\r\n\r\n"
        )
        return await attempt(port, client_context(edge.ca, edge.owner), request)

    answer = against(edge, scenario)
    assert status_of(answer) == 400 and payload(answer)["rule"] == "service.transfer-encoding"


def test_a_post_must_declare_its_length(edge: Edge) -> None:
    """Ruled in 7bg.8 and never built: `_framing` checked that a *present* `Content-Length` was within the cap and
    never required one. The consequence is worse than a missing check — h11 frames a length-less request as
    bodyless, so the arguments the peer sent are discarded in silence and the verb is called with `{}`. Measured
    2026-08-29: `POST /call/show` with a body and no length reached the verb and was refused for a missing field,
    which is the framing layer passing on a request it had silently altered.

    Two arms, because one would not tell the two outcomes apart: the length-less POST is refused with its own rule
    id, and the identical call **with** a length is answered 200 by the verb."""

    async def scenario(port: int) -> tuple[bytes | None, bytes | None]:
        body = json.dumps({"target": "queue"}).encode()
        without = await attempt(
            port,
            client_context(edge.ca, edge.owner),
            b"POST /call/show HTTP/1.1\r\nHost: localhost\r\n\r\n" + body,
        )
        with_length = await attempt(port, client_context(edge.ca, edge.owner), raw("POST", "/call/show", body))
        return without, with_length

    without, with_length = against(edge, scenario)
    assert status_of(without) == 411 and payload(without)["rule"] == "service.length-required"
    assert status_of(with_length) == 200, payload(with_length)


def test_a_declared_body_past_the_cap_is_refused_before_it_is_read(edge: Edge) -> None:
    """The length is refused on the header, not after a megabyte has been accepted into memory."""

    async def scenario(port: int) -> bytes | None:
        request = b"POST /call/show HTTP/1.1\r\nHost: localhost\r\nContent-Length: 99999\r\n\r\n"
        return await attempt(port, client_context(edge.ca, edge.owner), request)

    answer = against(edge, scenario, Limits(max_body_bytes=1024))
    assert status_of(answer) == 413 and payload(answer)["rule"] == "service.body-too-large"


def test_the_declared_header_cap_is_the_one_that_bites(edge: Edge) -> None:
    """C-10 says a declared limit is written where it bites, and this one was not. `Limits.max_header_bytes` is
    h11's `max_incomplete_event_size`, which caps an *incomplete* event — so a complete header block arriving inside
    one 64 KiB read was parsed before the cap could see it. Measured 2026-08-29 at the shipped 16 KiB: complete
    blocks of 8, 32 and 60 KiB all returned **200**, and only 128 KiB was refused. The real bound was an unnamed
    module constant, four times the named one.

    The edge now counts what it feeds the parser while the request line and headers are unfinished, so the declared
    number is the true one. Three arms, and the middle one is the whole point: a block under the cap is answered, a
    complete block over it is refused **with a status and a rule id**, and an unterminated block is refused too. The
    old assertion here was `assert answer is None or status_of(answer) == 431` — which a store that had no cap at
    all would also pass."""

    async def scenario(port: int) -> tuple[bytes | None, bytes | None, bytes | None]:
        context = client_context(edge.ca, edge.owner)
        under = await attempt(port, context, raw("GET", "/health", extra=b"X-Pad: " + b"a" * 512 + b"\r\n"))
        complete = await attempt(port, context, raw("GET", "/health", extra=b"X-Pad: " + b"a" * 8192 + b"\r\n"))
        endless = await attempt(port, context, b"GET /health HTTP/1.1\r\nHost: localhost\r\nX-Pad: " + b"a" * 8192)
        return under, complete, endless

    under, complete, endless = against(edge, scenario, Limits(max_header_bytes=2048))
    assert status_of(under) == 200, payload(under)
    assert status_of(complete) == 431 and payload(complete)["rule"] == "service.headers-too-large"
    assert status_of(endless) == 431 and payload(endless)["rule"] == "service.headers-too-large"


def test_a_stalled_peer_is_closed_by_the_read_timeout(edge: Edge) -> None:
    """A connection that completes the handshake and then says nothing is ended by the read timeout, not held.

    The discriminator is the clock, not the emptiness: `assert result == b""` was the old assertion and a store with
    no read timeout at all produces exactly the same `b""` once the *client* gives up. So the peer waits far longer
    than the timeout it is testing, and the assertion is that the end arrived well inside that window."""

    async def scenario(port: int) -> tuple[float, bytes]:
        started = time.monotonic()
        reader, writer = await asyncio.open_connection(
            "127.0.0.1", port, ssl=client_context(edge.ca, edge.owner), server_hostname="localhost"
        )
        try:
            got = await asyncio.wait_for(reader.read(), 8)
        except (ssl.SSLError, OSError, TimeoutError):
            got = b"<the client gave up first>"
        finally:
            writer.close()
        return time.monotonic() - started, got

    elapsed, got = against(edge, scenario, Limits(read_timeout=0.25))
    assert got == b"", f"the read timeout did not end the connection: {got!r}"
    assert elapsed < 4.0, f"the store held a stalled peer for {elapsed:.2f}s against a 0.25s read timeout"


def test_a_peer_that_stops_mid_body_is_closed_by_the_read_timeout(edge: Edge) -> None:
    """The read timeout is applied at two places — waiting for the head, and waiting for a declared body — and the
    stalled-peer test above only ever reaches the first. Measured by mutation: removing the timeout from the body
    read alone left every test green. So a peer that declares a length and then sends nothing is its own arm.

    The discriminator is again the clock, not the emptiness."""

    async def scenario(port: int) -> tuple[float, bytes]:
        started = time.monotonic()
        reader, writer = await asyncio.open_connection(
            "127.0.0.1", port, ssl=client_context(edge.ca, edge.owner), server_hostname="localhost"
        )
        head = b"POST /call/show HTTP/1.1" + CRLF + b"Host: localhost" + CRLF + b"Content-Length: 50" + CRLF * 2
        writer.write(head)  # the length is declared and the body never arrives
        await writer.drain()
        try:
            got = await asyncio.wait_for(reader.read(), 8)
        except (ssl.SSLError, OSError, TimeoutError):
            got = b"<the client gave up first>"
        finally:
            writer.close()
        return time.monotonic() - started, got

    elapsed, got = against(edge, scenario, Limits(read_timeout=0.25))
    assert got == b"", f"the body read was not bounded: {got!r}"
    assert elapsed < 4.0, f"the store waited {elapsed:.2f}s for a body against a 0.25s read timeout"


def test_the_write_timeout_bounds_a_peer_that_will_not_read(edge: Edge) -> None:
    """The one limit with no socket-level arm: making `drain()` block needs a peer that stops reading with the
    kernel buffer already full, which is minutes of traffic against a store whose responses are one small JSON
    object. So it is proven where it is applied, against a writer that never drains.

    The discriminator is the **clock**, and the first version of this test did not have it: it asserted only that a
    `TimeoutError` arrived, which is what the test’s own outer bound produces when the write timeout is removed
    entirely — the mutation survived. It has to end at the timeout under test, not at the one holding the test up."""

    class NeverDrains:
        def __init__(self) -> None:
            self.written = b""

        def write(self, data: bytes) -> None:
            self.written += data

        async def drain(self) -> None:
            await asyncio.sleep(3600)

    async def scenario() -> tuple[str, float]:
        writer = NeverDrains()
        started = time.monotonic()
        try:
            await asyncio.wait_for(
                http._respond(writer, None, Response.json(200, {"ok": True}), Limits(write_timeout=0.25)), 5
            )
            outcome = "returned"
        except TimeoutError:
            outcome = "timed out" if writer.written else "nothing was written"
        return outcome, time.monotonic() - started

    outcome, elapsed = asyncio.run(scenario())
    assert outcome == "timed out"
    assert elapsed < 2.0, f"the write ended after {elapsed:.2f}s, which is the test’s bound and not the store’s"


# ---- admission (Q4): the ceiling, and the per-peer allowance -----------------------------------------------------


def test_the_connection_ceiling_is_met_before_the_handshake(edge: Edge, monkeypatch: pytest.MonkeyPatch) -> None:
    """Half the point of Q1's reshape. The ceiling used to sit **inside** the post-handshake handler, so an
    unauthenticated peer could drive unbounded concurrent handshakes — elliptic-curve work per connection — without
    ever meeting the limit.

    The discriminator is a peer that never speaks TLS at all: at a ceiling of one it now holds the only slot, so a
    caller with a certificate the CA issued is refused while it is held and answered once it is released. Under the
    old shape the silent peer occupied nothing and the good caller was answered both times."""
    refusals(monkeypatch)  # the silent peer's own refusal is not the subject here; keep it off the loop handler

    async def scenario(port: int) -> tuple[bytes | None, bytes | None]:
        _reader, writer = await asyncio.open_connection("127.0.0.1", port)  # plain TCP: no handshake is attempted
        await asyncio.sleep(_SETTLE)
        while_held = await attempt(port, client_context(edge.ca, edge.owner), raw("GET", "/health"))
        writer.close()
        await asyncio.sleep(_SETTLE)
        once_free = await attempt(port, client_context(edge.ca, edge.owner), raw("GET", "/health"))
        return while_held, once_free

    while_held, once_free = against(edge, scenario, Limits(max_connections=1, handshake_timeout=10.0))
    assert while_held is None, "the ceiling did not bound a peer that had not handshaked"
    assert status_of(once_free) == 200, "the ceiling never released the slot"


def test_one_caller_cannot_hold_every_slot(edge: Edge) -> None:
    """Measured 2026-08-29: at a ceiling of 8, one authorised caller sending an unterminated request line held all
    eight and the next legitimate caller was refused in 0.05 s. At the shipped 64 with a 30 s read timeout that is a
    renewable total outage costing nothing to sustain, from a `contributor` credential held by a language model —
    inside the threat model, not outside it.

    Ruled (Q4): a per-peer allowance at the edge, keyed on the credential. The discriminator is the pair — the
    caller's own third connection is refused **with a status and a rule id**, while the global ceiling still has
    room, which is what tells a per-peer bound from an exhausted store."""

    async def scenario(port: int) -> tuple[list[Any], bytes | None]:
        context = client_context(edge.ca, edge.owner)
        held = [await hold(port, context) for _ in range(2)]
        await asyncio.sleep(_SETTLE)
        refused = await attempt(port, context, raw("GET", "/health"))
        for _reader, writer in held:
            writer.close()
        await asyncio.sleep(_SETTLE)
        after = await attempt(port, context, raw("GET", "/health"))
        return [refused], after

    (refused,), after = against(edge, scenario, Limits(max_connections=8, max_per_caller=2, read_timeout=30.0))
    assert status_of(refused) == 429 and payload(refused)["rule"] == "service.too-many-connections"
    assert status_of(after) == 200, "the allowance was never given back"


def test_the_unregistered_ca_issued_peer_is_its_own_class(edge: Edge) -> None:
    """A certificate the CA issued to a subject the registration does not name is a real and intended class — the
    container's healthcheck, an orchestrator probe. It is not a grant and not a principal, and today it participates
    in the global ceiling with no per-peer bound at all, so a leaked probe certificate can exhaust the store (Q4).

    The discriminator is that the two classes are counted separately: at a probe allowance of one the probe's second
    connection is refused while the registered caller, holding two of its own, is still answered."""

    async def scenario(port: int) -> tuple[bytes | None, bytes | None]:
        probe = client_context(edge.ca, edge.probe)
        _reader, writer = await hold(port, probe)
        held = [await hold(port, client_context(edge.ca, edge.owner)) for _ in range(2)]
        await asyncio.sleep(_SETTLE)
        second_probe = await attempt(port, probe, raw("GET", "/health"))
        owner = await attempt(port, client_context(edge.ca, edge.owner), raw("GET", "/health"))
        writer.close()
        for _r, w in held:
            w.close()
        return second_probe, owner

    second_probe, owner = against(
        edge, scenario, Limits(max_connections=16, max_per_caller=8, max_per_probe=1, read_timeout=30.0)
    )
    assert status_of(second_probe) == 429 and payload(second_probe)["rule"] == "service.too-many-connections"
    assert status_of(owner) == 200, "the registered caller was charged against the probe's allowance"


# ---- the classification, per class, without a socket -------------------------------------------------------------


def test_every_handshake_failure_class_is_classified_by_name() -> None:
    """Q1's second condition, at the function the socket tests exercise end to end. The two verify codes are the
    ones measured 2026-08-29 (20 = no local issuer, 10 = expired); an unmeasured code falls to `VERIFY_FAILED` on
    purpose rather than being guessed into a named class."""
    no_certificate = ssl.SSLError(1, "[SSL: PEER_DID_NOT_RETURN_A_CERTIFICATE] peer did not return a certificate")
    no_certificate.reason = "PEER_DID_NOT_RETURN_A_CERTIFICATE"
    wrong_ca = ssl.SSLCertVerificationError(1, "certificate verify failed")
    wrong_ca.reason, wrong_ca.verify_code = "CERTIFICATE_VERIFY_FAILED", 20
    expired = ssl.SSLCertVerificationError(1, "certificate verify failed")
    expired.reason, expired.verify_code = "CERTIFICATE_VERIFY_FAILED", 10
    unmeasured = ssl.SSLCertVerificationError(1, "certificate verify failed")
    unmeasured.reason, unmeasured.verify_code = "CERTIFICATE_VERIFY_FAILED", 7
    not_tls = ssl.SSLError(1, "[SSL: HTTP_REQUEST] http request")
    not_tls.reason = "HTTP_REQUEST"

    assert http.classify(no_certificate) is Refused.NO_CERTIFICATE
    assert http.classify(wrong_ca) is Refused.UNTRUSTED_ISSUER
    assert http.classify(expired) is Refused.EXPIRED
    assert http.classify(unmeasured) is Refused.VERIFY_FAILED
    assert http.classify(not_tls) is Refused.PROTOCOL
    assert http.classify(ConnectionAbortedError()) is Refused.TIMEOUT
    assert http.classify(TimeoutError()) is Refused.TIMEOUT
    # every reason renders, and renders differently: a typed value with one renderer is only useful if it is total
    assert len({reason.render() for reason in Refused}) == len(Refused)


def test_the_admission_key_is_the_credential_and_not_the_grant() -> None:
    """Keyed on the principal when the registration names it, otherwise on the fingerprint of the bytes the peer
    presented — both available the instant the handshake finishes, and neither needing the policy engine (Q4). A
    certificate that will not parse still gets a key, which is the peer that most needs one."""
    limits = Limits(max_per_caller=8, max_per_probe=2)
    registration = Registration({"owner@example": ("amodal1@example", "owner")})
    named = Credential("ff" * 32, "amodal1@example", "owner")
    assert http.allowance_for(named, limits) == ("amodal1@example", 8)
    probe = registration.credential(b"not a certificate at all")
    assert probe.fingerprint is not None and probe.parse_error is not None
    assert http.allowance_for(probe, limits) == (probe.fingerprint, 2)


# ---- C-11: what the edge counts, and what it traces ---------------------------------------------------------------


def test_the_handshake_counter_moves_with_the_right_reason(edge: Edge, otel: Telemetry) -> None:
    """**Q1's second condition, and K2b's done-when 5.** The incident that produced C-11 was that a sustained
    attempt to reach the boundary with bad certificates left no count, no subject and no timestamp anywhere: with
    `asyncio.start_server(ssl=…)` a refused handshake produced 0 handler calls, 0 loop-exception-handler calls and 0
    asyncio log records. The store now starts TLS itself, so the refusal is a value with a reason, and this is the
    counter hung on it.

    **The counter moves with the correct reason for each class, not merely moves.** A single total would be
    satisfied by a store that classified everything as `protocol`, which is exactly the shape Q1 refused — the
    metric has to mean the same thing in Python, Rust and Node, and the reason is the part that carries the meaning.
    Three deltas, one per class, each read against its own attribute set.

    **And nothing here is monkeypatched.** `refusals(monkeypatch)` above replaces `_refused` outright, so a test
    using it would not exercise the counter at all — it would pass against a `_refused` that counted nothing."""
    instrument = "isidium.store.handshake.refused"
    classes = (Refused.NO_CERTIFICATE, Refused.UNTRUSTED_ISSUER, Refused.EXPIRED)
    before = {cls: otel.count(instrument, **{telemetry.REASON: cls.value}) for cls in classes}

    async def scenario(port: int) -> int:
        for credential in (None, edge.stranger, edge.expired):
            await attempt(port, client_context(edge.ca, credential), raw("GET", "/health"))
        await asyncio.sleep(_SETTLE)  # the server's half outlives the client's: give the count room to appear
        answer = await attempt(port, client_context(edge.ca, edge.owner), raw("GET", "/health"))
        return status_of(answer)

    good = against(edge, scenario)
    moved = {cls: otel.count(instrument, **{telemetry.REASON: cls.value}) - was for cls, was in before.items()}
    assert moved == {Refused.NO_CERTIFICATE: 1, Refused.UNTRUSTED_ISSUER: 1, Refused.EXPIRED: 1}, moved
    assert good == 200, "the listener stopped answering a certificate the CA did issue"


def test_the_admission_counters_name_which_bound_was_met(edge: Edge, otel: Telemetry) -> None:
    """The other two pre-authentication events C-11 asks for, and they are counted rather than written as rows for
    the same reason: an unauthenticated peer drives both at will.

    The discriminator is again the reason. `ceiling` and `per-peer` are different facts about a store — one says it
    is full, the other says one caller is greedy while the store has room (Q4) — and a single "connection refused"
    total cannot tell an operator which. Each arm moves its own attribute set and leaves the other alone."""
    instrument = "isidium.store.connection.refused"
    ceiling_before = otel.count(instrument, **{telemetry.REASON: "ceiling"})
    per_peer_before = otel.count(instrument, **{telemetry.REASON: "per-peer"})

    async def at_the_ceiling(port: int) -> bytes | None:
        _reader, writer = await asyncio.open_connection("127.0.0.1", port)  # plain TCP: it holds the only slot
        await asyncio.sleep(_SETTLE)
        while_held = await attempt(port, client_context(edge.ca, edge.owner), raw("GET", "/health"))
        writer.close()
        return while_held

    async def past_the_allowance(port: int) -> bytes | None:
        context = client_context(edge.ca, edge.owner)
        held = [await hold(port, context) for _ in range(2)]
        await asyncio.sleep(_SETTLE)
        refused = await attempt(port, context, raw("GET", "/health"))
        for _reader, writer in held:
            writer.close()
        return refused

    assert against(edge, at_the_ceiling, Limits(max_connections=1)) is None
    assert otel.count(instrument, **{telemetry.REASON: "ceiling"}) == ceiling_before + 1, (
        "the connection ceiling refused a peer and counted nothing"
    )
    assert otel.count(instrument, **{telemetry.REASON: "per-peer"}) == per_peer_before, (
        "a global-ceiling refusal was counted as a per-peer one"
    )

    refused = against(edge, past_the_allowance, Limits(max_connections=8, max_per_caller=2, read_timeout=30.0))
    assert status_of(refused) == 429 and payload(refused)["rule"] == "service.too-many-connections"
    assert otel.count(instrument, **{telemetry.REASON: "per-peer"}) == per_peer_before + 1
    assert otel.count(instrument, **{telemetry.REASON: "ceiling"}) == ceiling_before + 1, (
        "the per-peer allowance was counted against the global ceiling"
    )


def test_a_call_over_the_socket_carries_both_phases_as_spans(edge: Edge, otel: Telemetry) -> None:
    """C-11's "a span per phase", end to end over TLS. Two phases exist: the edge's request and the call it
    dispatches, and the second is a child of the first — which is what makes a refusal attributable to the
    connection that carried it without inventing a correlation id (K6 joins on this).

    The edge span opens **after** the handshake and after admission, deliberately. Everything before that line is
    driven by peers holding nothing, and a span per hostile connection is the same denial of service through the
    telemetry as a log row per hostile connection (C-11) — which is why those three events are counters."""
    otel.clear()

    async def scenario(port: int) -> bytes | None:
        return await attempt(
            port,
            client_context(edge.ca, edge.owner),
            raw("POST", "/call/show", json.dumps({"target": "card", "id": 9999}).encode()),
        )

    answer = against(edge, scenario)
    assert status_of(answer) == 404 and payload(answer)["rule"] == "show.unknown"

    request_spans = otel.spans(telemetry.REQUEST_SPAN)
    call_spans = otel.spans(telemetry.CALL_SPAN)
    assert len(request_spans) == 1 and len(call_spans) == 1, [s.name for s in otel.spans()]
    request, called = request_spans[0], call_spans[0]
    assert called.parent is not None and called.parent.span_id == request.context.span_id, "the call span is an orphan"
    assert called.context.trace_id == request.context.trace_id
    assert request.attributes["http.response.status_code"] == 404
    assert called.attributes[telemetry.RULE] == "show.unknown"
    assert called.status.status_code.name == "ERROR"


def test_a_malformed_request_returns_words_the_store_wrote(edge: Edge) -> None:
    """C-12: **we ship no words we did not write.** `service.malformed` returned h11's own message, and it was one
    of the two responses whose content was not ours. h11's status hint stops here too — a rule id has one status and
    it comes off the disclosure table.

    Two `Transfer-Encoding` headers is the case that made the hint matter: h11 answers it 501, and the store answers
    a request carrying *one* such header 400 already, so the collapse makes the answer to "any transfer-encoding at
    all" uniform rather than losing a distinction. The arms are the status, the rule id, and the absence of h11's
    vocabulary."""

    async def scenario(port: int) -> bytes | None:
        request = (
            b"POST /call/show HTTP/1.1\r\nHost: localhost\r\n"
            b"Transfer-Encoding: chunked\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n"
        )
        return await attempt(port, client_context(edge.ca, edge.owner), request)

    answer = against(edge, scenario)
    assert status_of(answer) == 400, payload(answer)
    assert payload(answer) == {"rule": "service.malformed"}, "h11's words, or a path and a detail, reached the peer"


def test_a_handshake_that_yields_no_certificate_is_counted(
    edge: Edge, otel: Telemetry, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The third pre-authentication event C-11 asks for. `CERT_REQUIRED` should make it impossible — which is
    exactly why it is counted: a counter that moves here says the listener was built without it, and that is a
    diagnosis no other signal in the store gives. Before this chunk the branch returned in silence, so a store
    misconfigured this way refused every caller and said nothing on either side of the connection.

    It cannot be provoked through the CA, so it is provoked at the one seam that produces it: the certificate the
    connection hands over. The discriminator is the pair — the counter moves **and** the peer gets no answer, which
    is what tells this branch from a store that simply answered."""
    before = otel.count("isidium.store.certificate.absent")
    monkeypatch.setattr(http, "_peer_certificate", lambda _writer: None)

    async def scenario(port: int) -> bytes | None:
        return await attempt(port, client_context(edge.ca, edge.owner), raw("GET", "/health"))

    answer = against(edge, scenario)
    assert answer is None, "the store parsed a request from a connection carrying no certificate"
    assert otel.count("isidium.store.certificate.absent") == before + 1
