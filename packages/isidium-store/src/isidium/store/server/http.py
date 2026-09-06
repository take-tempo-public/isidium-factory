"""The store's own TLS edge (03b §2, ruled 7bg.8): the store answers the connection, requires a client certificate
the tenant registration's CA issued, and reads that certificate **off the very connection it is authorizing**. There
is no proxy, no forwarded header and no trusted hop — an identity that arrives by one process's say-so is a perimeter
in miniature, and the store's whole posture is that every call is authorized where it is answered.

**What is ours here is the accept-and-dispatch loop, and never a parser.** `h11` — the sans-IO HTTP/1.1 parser
uvicorn itself parses with, well fuzzed, pinned ≥ 0.16 — owns the protocol grammar. This module owns the socket, the
limits and the dispatch, which together are about two hundred lines and hold no grammar at all. That distinction is
the whole security argument: request smuggling is a disagreement between *two* parsers in a chain (h11's own
CVE-2025-43859 was h11 sitting behind a lenient proxy), and terminating here leaves exactly one parser between the
socket and the store.

**The store starts TLS itself, per connection** [ruled 2026-08-29, Q1]. The listener is a plain TCP listener and the
handler calls `start_tls`, so a refused handshake arrives as a **catchable exception carrying its reason** rather
than vanishing: measured 2026-08-29, a handshake refused inside `asyncio.start_server(ssl=…)` produced 0 handler
calls, 0 loop-exception-handler calls and 0 asyncio log records, across no-certificate, wrong-CA and expired —
because `ssl.SSLError` is an `OSError`, which asyncio logs only in debug mode and never raises to the handler. The
trust boundary is unchanged: the same context, the same `CERT_REQUIRED` against the same CA, the same OpenSSL state
machine, and no attacker-controlled byte reaches h11 or the store until the certificate verifies. What changes is
that **the connection ceiling now sits ahead of the handshake**, so an unauthenticated peer can no longer drive
unbounded concurrent handshakes without meeting a limit, and that the refusal is a value with a reason (`Refused`)
handed to exactly one call site, `_refused`, where K2b hangs the counter.

**Admission is not authorization** [ruled 2026-08-29, Q4]. Authorization asks *may this principal do this thing*,
per call, after the request is parsed; admission asks *is there capacity*, per connection, before any work is spent.
Availability is deliberately **not** in the grant matrix (`server/identity.py`). The per-peer allowance is keyed on
the credential — the principal when the registration names it, otherwise the fingerprint of the bytes the peer
presented — because both are available the instant the handshake finishes and neither needs the policy engine.

**One request per connection.** Every response carries `Connection: close` and the connection is closed after it.
That deletes the keep-alive state machine, which is where hand-written servers actually break, and the design's own
call count (≈3 store calls per card lifetime, 03 §9.6) makes the extra handshake free.
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import queue
import signal
import ssl
import threading
import weakref
from collections.abc import Callable, Mapping
from concurrent.futures import Executor, Future
from dataclasses import dataclass
from enum import Enum
from http import HTTPStatus
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final, Protocol

import h11

from ..core import telemetry
from ..core.refusal import Refusal
from .service import JSON, Credential, Request, Response, Service

_READ_CHUNK: Final = 65536

# The two admission bounds, as the values the counter is keyed on — a closed set with one name each (C-2), so a
# dashboard reads "which bound was met" and never parses a sentence. Named here rather than spelled at the two call
# sites, which is the same rule the `Refused` enum follows for the handshake.
_CEILING: Final = "ceiling"
_PER_PEER: Final = "per-peer"
# The response status on the edge's span. OpenTelemetry's own semantic convention for a server span, used verbatim
# rather than invented, because a collector that knows it can chart it with no configuration of ours.
_HTTP_STATUS: Final = "http.response.status_code"


@dataclass(frozen=True)
class Limits:
    """Deployment limits, not schema defaults (C-1 governs the latter; C-10 says a limit is written where it bites).

    Every caller is one of a handful of certificates the registration names, so these are sized to bound memory and
    to end a stalled connection, not to survive an open internet. **This dataclass is the one home for every number
    below** — `serve` supplies them, so a deployment sets them without a new build (Q4: "supplied values with a
    named home, never constants in the binary"), and no limit is enforced against a literal written at its own
    site."""

    max_connections: int = 64  # far above the registration's caller count; bounds memory under a burst
    # Per-peer, and the reason it exists: at a ceiling of 8, one authorised caller holding connections open with an
    # unterminated request line occupied all eight and the next legitimate caller was refused in 0.05 s (measured
    # 2026-08-29). A `contributor` cannot write what it should not — and could lock the `owner` out of their own
    # store. 8 is above any legitimate concurrency for a caller that makes ≈3 calls per card lifetime.
    max_per_caller: int = 8
    # The CA-issued peer the registration does not name — the container's healthcheck, an orchestrator probe. It is
    # not a grant and not a principal; its allowance is deliberately small, because a leaked probe certificate
    # otherwise participates in the global ceiling with no per-peer bound at all.
    max_per_probe: int = 2
    handshake_timeout: float = 10.0  # a TLS 1.3 handshake on a LAN is milliseconds
    read_timeout: float = 30.0  # a stalled peer is closed rather than held
    write_timeout: float = 30.0
    max_header_bytes: int = 16 * 1024  # the request line and headers, counted as they are read (see `_one_request`)
    max_body_bytes: int = 1024 * 1024  # one governed document plus its arguments; schema prose slots are far below
    # K6b: how long a stopping store waits for the calls in flight before it exits anyway. The store is PID 1 in its
    # container and, until K6b, installed no handler — and PID 1 receives no default action — so every `podman stop`
    # waited its 10 s and sent SIGKILL (measured on five chunks). 5 s is half of podman's window, leaving the other
    # half for the exit itself; a real call is milliseconds, and a peer still holding a connection past it is the
    # read timeout's problem, not the shutdown's — the journal's write-ahead makes a cut-off write replayable.
    shutdown_grace: float = 5.0


LIMITS: Final = Limits()


class Refused(Enum):
    """Why a handshake was refused — a typed value with one renderer (C-2), never a formatted string.

    The set is closed and the same six names are available in every port: in Rust `acceptor.accept()` returns a
    `Result` whose error carries these, and Node's `tlsClientError` gives the same. That is the point of Q1's shape
    — the metric K2b builds on means the same thing in all three languages."""

    NO_CERTIFICATE = "no-certificate"
    UNTRUSTED_ISSUER = "untrusted-issuer"
    EXPIRED = "expired"
    VERIFY_FAILED = "verify-failed"
    TIMEOUT = "timeout"
    PROTOCOL = "protocol"

    def render(self) -> str:
        return _REFUSED_TEXT[self]


_REFUSED_TEXT: Final[Mapping[Refused, str]] = MappingProxyType(
    {
        Refused.NO_CERTIFICATE: "the peer returned no certificate",
        Refused.UNTRUSTED_ISSUER: "the peer's certificate was not issued by the registration's CA",
        Refused.EXPIRED: "the peer's certificate is outside its validity window",
        Refused.VERIFY_FAILED: "the peer's certificate did not verify",
        Refused.TIMEOUT: "the peer did not finish the handshake in time",
        Refused.PROTOCOL: "the peer did not complete a TLS handshake",
    }
)

# OpenSSL's `X509_V_ERR_*` codes, and **only the two that were measured** (2026-08-29: a certificate from another
# authority gives 20, `unable to get local issuer certificate`; one outside its window gives 10, `certificate has
# expired`). Every other code falls to `VERIFY_FAILED` on purpose — a code guessed into a named class would be a
# claim, and the whole reason this chunk exists is that claims were recorded as measurements.
_VERIFY_CODES: Final[Mapping[int, Refused]] = MappingProxyType({10: Refused.EXPIRED, 20: Refused.UNTRUSTED_ISSUER})
# OpenSSL's own symbolic reason, not a message we format: `SSLError.reason` is an enumerated name from the library,
# and reading it here is the single place a foreign vocabulary is translated into ours (C-2's "one renderer").
_NO_CERTIFICATE: Final = "PEER_DID_NOT_RETURN_A_CERTIFICATE"


def classify(exc: BaseException) -> Refused:
    """The handshake failure, as a value. Measured 2026-08-29 for each class this store actually meets."""
    if isinstance(exc, ssl.SSLCertVerificationError):
        return _VERIFY_CODES.get(exc.verify_code, Refused.VERIFY_FAILED)
    if isinstance(exc, ssl.SSLError):
        return Refused.NO_CERTIFICATE if exc.reason == _NO_CERTIFICATE else Refused.PROTOCOL
    # asyncio aborts the transport when `ssl_handshake_timeout` expires and the handler sees `ConnectionAbortedError`
    # (measured); `TimeoutError` is what a caller-imposed deadline would raise. Both are the same fact about a peer.
    if isinstance(exc, (TimeoutError, ConnectionAbortedError)):
        return Refused.TIMEOUT
    return Refused.PROTOCOL


def _refused(reason: Refused, peer: object) -> None:
    """**The one call site for a refused handshake** (Q1: "K1b-ii leaves one call site and a typed classification of
    the failure; K2b hangs the counter on it"), and now the counter itself.

    **A counter keyed on the typed reason, and never a row.** A refused handshake is the one event in this store an
    entirely unauthenticated peer can drive at will, so a record per connection would be a denial of service through
    the logging (C-11). `peer` is deliberately *not* an attribute: a peer address is unbounded cardinality, which is
    the metrics equivalent of the same mistake. It stays a parameter because the reason a caller cannot reach the
    store is a per-peer question when an operator finally asks it, and K6 is where identity joins.

    This closes K1's instrumentation debt — the one path in the tree allowed to carry it, because K1 landed before
    C-11 existed."""
    telemetry.HANDSHAKE_REFUSED.add(1, {telemetry.REASON: reason.value})


def tls_context(certificate: Path, key: Path, ca: Path) -> ssl.SSLContext:
    """The store's listener context: it proves it is the store, and it requires a client certificate the tenant
    registration's CA issued. TLS 1.3 only — every client is ours, and it removes renegotiation and cipher-suite
    selection from the surface entirely."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.verify_mode = ssl.CERT_REQUIRED
    context.load_verify_locations(cafile=str(ca))
    context.load_cert_chain(certfile=str(certificate), keyfile=str(key))
    return context


class Admission:
    """The two bounds a peer meets before the store spends anything on it (Q4).

    `open` is the global ceiling and it is met **before the handshake**, so the elliptic-curve work of a handshake
    is inside the bound rather than ahead of it. `take` is the per-peer allowance, met after the handshake and
    before a byte is read, keyed on the credential.

    No lock: every method here is synchronous with no `await` between a test and its increment, and the event loop
    is single-threaded, so the check and the claim cannot interleave. Counting is a dict lookup per connection, not
    a scan."""

    __slots__ = ("_held", "_limits", "_live")

    def __init__(self, limits: Limits) -> None:
        self._limits = limits
        self._live = 0
        self._held: dict[str, int] = {}

    def open(self) -> bool:
        if self._live >= self._limits.max_connections:
            return False
        self._live += 1
        return True

    def close(self) -> None:
        self._live -= 1

    def take(self, key: str, allowance: int) -> bool:
        held = self._held.get(key, 0)
        if held >= allowance:
            return False
        self._held[key] = held + 1
        return True

    def give_back(self, key: str) -> None:
        held = self._held.get(key, 0) - 1
        if held > 0:
            self._held[key] = held
        else:
            self._held.pop(key, None)  # an idle peer holds no entry: the table is the live set, not a history


def allowance_for(credential: Credential, limits: Limits) -> tuple[str, int]:
    """The admission key and the allowance it is measured against (Q4).

    **Keyed on the credential, not on the grant.** The principal when the registration names it; otherwise the
    fingerprint of the bytes the peer presented, which is also the key for the certificate that will not parse. If
    per-grant budgets are ever wanted this becomes a change of where the number comes from, not of what it is keyed
    on."""
    key = credential.principal if credential.principal is not None else credential.fingerprint
    assert key is not None  # `present` is checked before this is reached
    return key, limits.max_per_caller if credential.registered else limits.max_per_probe


class Worker(Executor):
    """**One thread, and every store call runs on it** [K7b, Q15, ruled 2026-09-06: *"One worker thread, now"*].

    Until K7b every verb ran on the event loop's own thread: a write's fetch (1.5 s on tenant #0) stalled every
    other connection and the healthcheck with it — measured, `/health` answered in 10–30 ms idle and in 2.3 s
    behind a 3 s call — and a ratify through the `remote-totp` signer, which polls for up to ten minutes for the
    owner's code, would have held every caller and marked the container unhealthy for the whole sitting. Now the
    loop keeps accepting, timing out and answering the probe while the one worker runs the call.

    **One thread is the point, not a limit to raise.** The store is one writer by the journal's row lock, written
    for a single thread and re-read for this change rather than assumed: `Journal.transaction` refuses re-entry
    with a flag, `Store` keeps its in-memory copy with no lock at all, and the `cat-file --batch` pipe is one
    process with one stdin. Two workers would need every one of those to grow a lock; one worker needs none, and
    serialises calls exactly as the loop did — no new concurrency, only a loop that is free while a call runs.

    A plain `concurrent.futures.Executor`, so `loop.run_in_executor` takes it, and **a daemon thread**, which is
    what a `ThreadPoolExecutor` is not: its workers are joined at interpreter exit, so a call blocked in the signer
    would hold the process open past K6b's grace and `podman stop` would be back to SIGKILL. A daemon thread is
    abandoned with the process, which is what "a connection still open when the grace ends is abandoned by the
    process exit" already meant — the journal's write-ahead makes the cut-off write replayable.
    """

    def __init__(self) -> None:
        self._queue: queue.SimpleQueue[tuple[Future[Any], Callable[..., Any], tuple[Any, ...]] | None] = (
            queue.SimpleQueue()
        )
        self.thread = threading.Thread(target=self._run, name="isidium-store-calls", daemon=True)
        self.thread.start()

    def submit(self, fn: Callable[..., Any], /, *args: Any, **kwargs: Any) -> Future[Any]:
        if kwargs:
            raise TypeError("the store's worker takes positional arguments only")
        fut: Future[Any] = Future()
        self._queue.put((fut, fn, args))
        return fut

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                return
            fut, fn, args = item
            if not fut.set_running_or_notify_cancel():
                continue
            try:
                fut.set_result(fn(*args))
            except BaseException as e:
                fut.set_exception(e)

    def shutdown(self, wait: bool = True, *, cancel_futures: bool = False) -> None:
        self._queue.put(None)
        if wait:
            self.thread.join()


async def start(
    service: Service, host: str, port: int, context: ssl.SSLContext, limits: Limits = LIMITS
) -> asyncio.Server:
    """Bind and start accepting. The caller owns the returned server (the CLI serves forever; a test closes it).

    A **plain TCP** listener: the store starts TLS itself inside the handler (Q1), which is what makes a refused
    handshake observable and what puts the ceiling ahead of the handshake. One `Worker` per listener, ended when
    the server object goes; it is a daemon thread either way."""
    admission = Admission(limits)
    worker = Worker()

    async def on_connect(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await _connection(service, reader, writer, context, limits, admission, worker)

    server = await asyncio.start_server(on_connect, host, port)
    weakref.finalize(server, worker.shutdown, wait=False)
    return server


async def serve_forever(
    service: Service, host: str, port: int, context: ssl.SSLContext, limits: Limits = LIMITS
) -> None:
    """Serve until SIGTERM or SIGINT, then stop cleanly [K6b].

    **The store is PID 1 in its container** (`deploy/entrypoint.sh` `exec`s it), and a PID 1 with no handler never
    receives the kernel's default terminate: a `podman stop` waited its ten seconds and sent SIGKILL, on every restart
    of tenant #0 since K2. The handler sets one event; `serve_until` does the rest. Exit code 0 is the contract — an
    orchestrator that restarts on failure must not read a stop as one."""
    server = await start(service, host, port, context, limits)
    stop = asyncio.Event()
    _stop_on_signal(asyncio.get_running_loop(), stop)
    await serve_until(server, stop, limits)


def _stop_on_signal(loop: asyncio.AbstractEventLoop, stop: asyncio.Event) -> tuple[int, ...]:
    """SIGTERM and SIGINT set `stop`, on the loops that can deliver a signal. Returns what was installed.

    Windows' event loops raise `NotImplementedError` here — no signal reaches an event loop there, and Ctrl-C arrives
    as `KeyboardInterrupt` out of `asyncio.run` as it always did. The container is Linux; the property this exists
    for is proven there (`tests/store/test_k6b.py`, and `podman stop` on tenant #0)."""
    installed: list[int] = []
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            break
        installed.append(int(sig))
    return tuple(installed)


async def serve_until(server: asyncio.Server, stop: asyncio.Event, limits: Limits) -> bool:
    """Serve until `stop` is set; then stop accepting and wait for the calls in flight, up to
    `limits.shutdown_grace`. Returns whether every connection finished inside the grace.

    Closing the listener first is what makes a stop safe to begin: nothing new is admitted while the store drains.
    A connection still open when the grace ends is abandoned by the process exit — its peer sees a closed
    connection, and a governed write it was in the middle of replays from the journal's pending bytes at the next
    start (`Store._replay_pending`). One span, so an operator reading a slow stop sees the drain as its own phase."""
    await stop.wait()
    with telemetry.span(telemetry.STOP_SPAN) as sp:
        server.close()
        try:
            await asyncio.wait_for(server.wait_closed(), limits.shutdown_grace)
        except TimeoutError:
            sp.set_attribute(telemetry.DRAINED, False)
            telemetry.record_ok()  # the stop itself succeeded; what did not finish is the peer's, not the store's
            return False
        sp.set_attribute(telemetry.DRAINED, True)
        telemetry.record_ok()
        return True


def _peer_certificate(writer: asyncio.StreamWriter) -> bytes | None:
    """The client certificate of this connection, in DER — the caller's identity, read where it is authorized."""
    ssl_object = writer.get_extra_info("ssl_object")
    if ssl_object is None:
        return None
    der: bytes | None = ssl_object.getpeercert(binary_form=True)
    return der or None


async def _handshake(writer: asyncio.StreamWriter, context: ssl.SSLContext, limits: Limits) -> Refused | None:
    """`None` when the peer's certificate verified; otherwise why it did not."""
    try:
        await writer.start_tls(context, ssl_handshake_timeout=limits.handshake_timeout)
    except (ssl.SSLError, OSError, TimeoutError) as e:
        return classify(e)
    return None


async def _connection(
    service: Service,
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    context: ssl.SSLContext,
    limits: Limits,
    admission: Admission,
    worker: Worker,
) -> None:
    """One connection, one request, then closed. Nothing raised here may reach the accept loop: a peer that hangs
    up, times out or speaks nonsense ends its own connection and nothing else."""
    if not admission.open():  # at the ceiling: refuse rather than queue, so the bound is the bound
        telemetry.CONNECTION_REFUSED.add(1, {telemetry.REASON: _CEILING})
        _close(writer)
        return
    held: str | None = None
    try:
        refusal = await _handshake(writer, context, limits)
        if refusal is not None:
            _refused(refusal, writer.get_extra_info("peername"))
            return
        credential = service.registration.credential(_peer_certificate(writer))
        if not credential.present:  # the handshake required one; if it is absent, parse nothing
            # `CERT_REQUIRED` should have made this impossible, so a counter that moves is a store built without it.
            # Counted rather than logged for the same reason as the handshake: nothing here is authenticated yet.
            telemetry.CERTIFICATE_ABSENT.add(1)
            return
        key, allowance = allowance_for(credential, limits)
        if not admission.take(key, allowance):
            # No request has been read — refusing at admission is the point — so h11 has nothing to frame and
            # `_respond` writes the answer itself. The peer still gets a status and a rule id (C-5).
            telemetry.CONNECTION_REFUSED.add(1, {telemetry.REASON: _PER_PEER})
            # `Response.admission`, not `.refusal` [K7b, F16]: the line above is this event's counter, and
            # `payload()` would add a second on `isidium.store.refusal` and set the status of a span not yet open.
            await _respond(writer, None, Response.admission(Refusal("service.too-many-connections")), limits)
            return
        held = key
        connection = h11.Connection(h11.SERVER, max_incomplete_event_size=limits.max_header_bytes)
        # **The first of C-11's two phases**, and it opens here rather than at `accept`: everything above this line
        # is pre-authentication and is counted, not traced — a span per hostile connection is the same denial of
        # service as a log row per hostile connection. By this point the peer holds a certificate this CA issued and
        # is inside its own allowance, so the work the store is about to spend is worth a span.
        with telemetry.span(telemetry.REQUEST_SPAN) as sp:
            try:
                response, head = await _one_request(service, reader, connection, limits, credential, worker)
                sp.set_attribute(_HTTP_STATUS, response.status)
                await _respond(writer, connection, response, limits, head)
            except (TimeoutError, OSError, h11.ProtocolError):
                raise
            except Exception as e:
                # A bug in the framing layer, not in a verb: the caller still gets a status and a rule id, and the
                # exception is the record's (C-12) — which it now reaches, and the span's status with it.
                telemetry.note("service.internal", f"{type(e).__name__}: {e}")
                await _respond(writer, None, Response.refusal(Refusal("service.internal")), limits)
    except (TimeoutError, OSError, h11.ProtocolError):
        return  # the peer's connection dies with the peer's mistake (`ssl.SSLError` is an `OSError`)
    finally:
        if held is not None:
            admission.give_back(held)
        admission.close()
        _close(writer)


async def _one_request(
    service: Service,
    reader: asyncio.StreamReader,
    connection: h11.Connection,
    limits: Limits,
    credential: Credential,
    worker: Worker,
) -> tuple[Response, bool]:
    """The response, and whether the request was a `HEAD` (which is answered with headers and no body)."""
    body = bytearray()
    request: h11.Request | None = None
    head_bytes = 0
    while True:
        try:
            event = connection.next_event()
        except h11.RemoteProtocolError as e:
            # h11's words, and h11's status hint, both stop here. **The words** because C-12 says we ship none we did
            # not write, and this was one of the two responses whose content was not ours; they go to the record.
            # **The hint** because a rule id has one status and it comes off the table (C-4): the hint's only
            # non-400 values are 431, which our own header cap refuses ahead of h11, and 501, for a request already
            # answered 400 when it carries one `Transfer-Encoding` rather than two.
            telemetry.note("service.malformed", str(e))
            return Response.refusal(Refusal("service.malformed", "", "the request is not well-formed HTTP/1.1")), False
        if event is h11.NEED_DATA:
            if request is None:
                # **C-10: the declared header cap, enforced where it bites.** h11's `max_incomplete_event_size` is a
                # cap on an *incomplete* event, so a complete header block arriving inside one read is parsed
                # before the cap can see it: at the shipped 16 KiB, blocks of 8, 32 and 60 KiB all returned 200 and
                # only 128 KiB was refused — the real bound was `_READ_CHUNK`, an unnamed constant 4× the named one
                # (measured 2026-08-29). Counting what we feed while the request line and headers are unfinished
                # makes the declared number the true one, exactly: the edge never feeds the parser more than the
                # cap while the head is unfinished, so h11's belt cannot trip ahead of ours and the caller meets the
                # number that was declared. The count is judged only here, where h11 has just said the head is still
                # unfinished, so a body that arrived in the same read as its headers is never charged to it.
                if head_bytes >= limits.max_header_bytes:
                    # The cap is the detail, and the caller does not get it: `service.*` is terse and the rule id
                    # carries the whole meaning (C-12). The number reaches the operator through the withheld log.
                    return (
                        Response.refusal(Refusal("service.headers-too-large", "", str(limits.max_header_bytes))),
                        False,
                    )
                data = await asyncio.wait_for(
                    reader.read(min(_READ_CHUNK, limits.max_header_bytes - head_bytes)), limits.read_timeout
                )
                head_bytes += len(data)
            else:
                data = await asyncio.wait_for(reader.read(_READ_CHUNK), limits.read_timeout)
            connection.receive_data(data)  # b"" tells h11 the peer is done
            continue
        if isinstance(event, h11.Request):
            refusal = _framing(event, limits)
            if refusal is not None:
                return Response.refusal(refusal), event.method == b"HEAD"
            request = event
            continue
        if isinstance(event, h11.Data):
            # No cap here on purpose: `_framing` refuses a declared length past the cap before a byte is read, a
            # `POST` without a declared length is refused outright, and h11 delivers no more `Data` than the
            # declared length. The runtime accumulation check that used to sit here could not fire — it was the
            # only thing that looked like it enforced the body cap at runtime, and it did not (measured
            # 2026-08-29). The cap bites in `_framing`, which is where it is now written.
            body += event.data
            continue
        if isinstance(event, h11.EndOfMessage):
            break
        telemetry.note("service.malformed", f"unexpected h11 event {type(event).__name__}")
        return Response.refusal(Refusal("service.malformed", "", "the request is not well-formed HTTP/1.1")), False
    if request is None:  # the peer closed before sending anything
        raise ConnectionResetError
    parsed = Request(request.method.decode("ascii"), request.target.decode("ascii", "replace"), bytes(body))
    if service.is_liveness(parsed):
        # The probe is answered on the loop [K7b, Q15]: it reads a constant, and behind the one worker it would
        # queue behind the very call it exists to report the listener alive during.
        return service.handle(parsed, credential), request.method == b"HEAD"
    # The call runs on the one worker thread, **inside this task's context**: `copy_context().run` carries the
    # OpenTelemetry context across, so the call span nests under the request span opened above and the journal row
    # reads the same trace (K6, C-9). Without it the worker's span would be a root of its own.
    context = contextvars.copy_context()

    def call() -> Response:
        return context.run(service.handle, parsed, credential)

    return await asyncio.get_running_loop().run_in_executor(worker, call), request.method == b"HEAD"


def _framing(request: h11.Request, limits: Limits) -> Refusal | None:
    """The three framing rules. Every client is ours, so chunked transfer has no legitimate use here and refusing it
    removes a whole framing mode from the surface; a declared length past the cap is refused before the body is
    read rather than after; and a `POST` must declare its length (ruled 7bg.8).

    **Why the length is required and not merely capped:** without it h11 frames the request as bodyless and the
    body the peer sent is discarded in silence — measured 2026-08-29, a `POST /call/show` carrying arguments and no
    `Content-Length` reached the verb with `{}` and was refused for a missing field, so the framing layer passed on
    a request it had silently altered. This is also the only place the body cap bites."""
    length: int | None = None
    for name, value in request.headers:
        if name == b"transfer-encoding":
            return Refusal("service.transfer-encoding", "", "send Content-Length; chunked is refused")
        if name == b"content-length":
            length = int(value)
            if length > limits.max_body_bytes:
                return Refusal("service.body-too-large", "", str(limits.max_body_bytes))
    if request.method == b"POST" and length is None:
        return Refusal("service.length-required", "", "a POST must declare Content-Length")
    return None


def _wire(response: Response, head: bool) -> bytes:
    """One response, framed by hand — used only where h11 has no request to frame it against (an admission refusal,
    a header block that never finished, a bug). It writes a constant shape and parses nothing, so h11 remains the
    only parser on this connection."""
    phrase = HTTPStatus(response.status).phrase.encode("ascii")
    return (
        b"HTTP/1.1 "
        + str(response.status).encode("ascii")
        + b" "
        + phrase
        + b"\r\ncontent-type: "
        + JSON.encode("ascii")
        + b"\r\ncontent-length: "
        + str(len(response.body)).encode("ascii")
        + b"\r\nconnection: close\r\n\r\n"
        + (b"" if head else response.body)
    )


class ResponseWriter(Protocol):
    """What `_respond` needs of the connection's writer: `write` and `drain`, which is all it calls. Naming the
    two is what lets a test hand in a writer that never drains -- the write-timeout property -- without
    pretending to be a whole `asyncio.StreamWriter` [K5b, 2026-09-04, type-only]."""

    def write(self, data: bytes) -> None: ...

    async def drain(self) -> None: ...


async def _respond(
    writer: ResponseWriter,
    connection: h11.Connection | None,
    response: Response,
    limits: Limits,
    head: bool = False,
) -> None:
    """`head` is what makes `HEAD` answerable: h11 forbids a body on a response to `HEAD`, and sending one raised
    `LocalProtocolError` into a branch whose comment claimed the peer had never completed a request — so
    `HEAD /health` returned nothing at all and a health checker configured with it reported the store down with no
    diagnosis anywhere (measured 2026-08-29). The headers are the same as `GET`'s, including `Content-Length`,
    which is what RFC 9110 requires; only the body is omitted."""
    headers = [
        (b"content-type", JSON.encode("ascii")),
        (b"content-length", str(len(response.body)).encode("ascii")),
        (b"connection", b"close"),
    ]
    out: bytes | None = None
    if connection is not None:
        try:
            frames = [connection.send(h11.Response(status_code=response.status, headers=headers))]
            if not head:
                frames.append(connection.send(h11.Data(data=response.body)))
            frames.append(connection.send(h11.EndOfMessage()))
            out = b"".join(part for part in frames if part is not None)
        except h11.LocalProtocolError:
            out = None  # h11 will not frame a response to a request it never saw; the answer is still owed
    if out is None:
        out = _wire(response, head)
    writer.write(out)
    await asyncio.wait_for(writer.drain(), limits.write_timeout)


def _close(writer: asyncio.StreamWriter) -> None:
    with contextlib.suppress(OSError):
        writer.close()
