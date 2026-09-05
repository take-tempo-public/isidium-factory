"""K6b — `serve` stops on SIGTERM (ruled at K6's checkpoint, 2026-09-05).

The store is PID 1 in its container and installed no signal handler, and a PID 1 receives no default action — so
every `podman stop` since K2 waited its ten seconds and sent SIGKILL. Two properties, proven two ways:

* **the stop itself** — the listener closes, the calls in flight are waited for up to a grace, the return says which,
  and the process exits 0 — is proven **in this process on every platform** against a real TLS listener, with a
  peer that stalls and a peer that finishes;
* **that a signal reaches it** is proven by a **subprocess on Linux** (the container's platform; CI's runner), because
  Windows delivers no signal to an event loop and `os.kill` there is `TerminateProcess`. The test is skipped here
  with that reason, not passed — and `podman stop` on tenant #0 is the measurement on the target.

Mutation-checked with `tools/mutations/k6b.toml`; the spec header says which mutation only Linux can kill.
"""

from __future__ import annotations

import asyncio
import os
import signal
import socket
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from isidium.store.core import telemetry
from isidium.store.server import http
from isidium.store.server.http import Limits, serve_until, start

from .conftest import Telemetry
from .test_edge import Edge, authority, client_context, edge, hold, issue

__all__ = ["edge"]  # the fixture is imported for its name; ruff would otherwise call the import unused

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "packages" / "isidium-store" / "src"


def test_a_stop_closes_the_listener_and_drains_inside_the_grace(edge: Edge, otel: Telemetry) -> None:
    """Three stops against real listeners. (1) A peer holding an unterminated request line: the stop returns when the
    **grace** ends — after it, and well before the read timeout that would otherwise have ended the peer — reports
    `False`, and the listener is already closed, so a new connection is refused. (2) A peer that finishes its call
    after the stop began: waited for, answered, and the stop returns `True` **before** the grace ends — the positive
    discriminator that the drain waits for connections rather than sleeping the grace. (3) Nothing in flight: `True`,
    at once. Each stop is a span carrying whether it drained."""
    limits = Limits(read_timeout=3.0, shutdown_grace=0.5)
    ctx = client_context(edge.ca, edge.owner)

    async def run() -> None:
        asyncio.get_running_loop().set_exception_handler(lambda _loop, _context: None)

        async def serving() -> tuple[asyncio.Server, int, asyncio.Event, asyncio.Task[bool]]:
            server = await start(edge.service, "127.0.0.1", 0, edge.context, limits)
            port = int(server.sockets[0].getsockname()[1])
            stop = asyncio.Event()
            return server, port, stop, asyncio.create_task(serve_until(server, stop, limits))

        # (1) a stalled peer holds a slot; the stop is bounded by the grace, not by the peer
        _server, port, stop, task = await serving()
        _reader, writer = await hold(port, ctx)
        otel.clear()
        t0 = time.perf_counter()
        stop.set()
        drained = await asyncio.wait_for(task, 10)
        elapsed = time.perf_counter() - t0
        assert drained is False
        assert limits.shutdown_grace <= elapsed < limits.read_timeout, elapsed
        with pytest.raises(OSError):  # the listener closed the instant the stop began
            await asyncio.wait_for(asyncio.open_connection("127.0.0.1", port), 2)
        writer.close()
        spans = otel.spans(telemetry.STOP_SPAN)
        assert len(spans) == 1 and spans[0].attributes[telemetry.DRAINED] is False
        assert spans[0].status.status_code.name == "OK"

        # (2) a peer that finishes after the stop began is waited for and answered
        _server, port, stop, task = await serving()
        reader, writer = await hold(port, ctx)
        stop.set()
        await asyncio.sleep(0.05)  # the listener is closing; the held connection is still served
        writer.write(b"\r\n")  # the request line's missing terminator: `GET /health` completes
        await writer.drain()
        t0 = time.perf_counter()
        answer = await asyncio.wait_for(reader.read(), 5)
        assert answer.split(b" ", 2)[1] == b"200", answer
        drained = await asyncio.wait_for(task, 10)
        assert drained is True and time.perf_counter() - t0 < limits.shutdown_grace
        writer.close()
        assert otel.spans(telemetry.STOP_SPAN)[-1].attributes[telemetry.DRAINED] is True

        # (3) nothing in flight
        _server, _port, stop, task = await serving()
        t0 = time.perf_counter()
        stop.set()
        assert await asyncio.wait_for(task, 10) is True and time.perf_counter() - t0 < limits.shutdown_grace

    asyncio.run(run())


def test_the_handler_is_installed_where_a_loop_can_deliver_a_signal() -> None:
    """`_stop_on_signal` says what it installed. On Linux, both signals; on Windows, nothing — and it says so rather
    than raising, because `serve` must still start there for the tests that drive it in-process."""

    async def run() -> tuple[int, ...]:
        return http._stop_on_signal(asyncio.get_running_loop(), asyncio.Event())

    installed = asyncio.run(run())
    if sys.platform == "win32":
        assert installed == ()
    else:
        assert installed == (int(signal.SIGTERM), int(signal.SIGINT))


SCRIPT = textwrap.dedent(
    """
    import asyncio, sys, time
    from pathlib import Path

    from isidium.store.registry.loader import Registry
    from isidium.store.server.api import Api
    from isidium.store.server.gitrepo import MemGit
    from isidium.store.server.http import serve_forever, tls_context
    from isidium.store.server.journal import Journal
    from isidium.store.server.service import Registration, Service
    from isidium.store.server.store import Store

    cert, key, ca, port = sys.argv[1:5]
    clock = lambda: int(time.time())  # noqa: E731
    store = Store("t", MemGit(), Journal(":memory:", "t"), Registry.shipped(), clock)
    service = Service(Api(store), Registration({}, clock), "t")
    asyncio.run(serve_forever(service, "127.0.0.1", int(port), tls_context(Path(cert), Path(key), Path(ca))))
    print("stopped cleanly", flush=True)
    """
)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="no signal reaches an event loop on Windows and os.kill is TerminateProcess; the container is Linux, "
    "CI's runner proves this, and `podman stop` on tenant #0 measured it",
)
@pytest.mark.parametrize("sig", [signal.SIGTERM, signal.SIGINT])
def test_a_signal_ends_the_serving_process_cleanly(tmp_path: Path, sig: signal.Signals) -> None:
    """The whole path a `podman stop` takes: a process serving over the real listener receives the signal and exits
    0, inside a second, having printed the line after `asyncio.run` — which it only reaches if `serve_forever`
    returned rather than the process being killed."""
    ca = authority(tmp_path, "tenant-ca")
    cert, key = issue(ca, tmp_path, "store.sartor", "store", server=True)
    port = _free_port()
    script = tmp_path / "serve.py"
    script.write_text(SCRIPT, encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, str(script), str(cert), str(key), str(ca.path), str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONPATH": str(SRC)},
    )
    try:
        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=1):
                    break
            except OSError:
                if proc.poll() is not None:
                    died = proc.stderr.read() if proc.stderr else "the server died before it listened"
                    raise AssertionError(died) from None
                time.sleep(0.1)
        else:
            raise AssertionError("the server never listened")
        t0 = time.perf_counter()
        proc.send_signal(sig)
        out, err = proc.communicate(timeout=5)
        elapsed = time.perf_counter() - t0
    finally:
        if proc.poll() is None:
            proc.kill()
    assert proc.returncode == 0, (proc.returncode, err)
    assert "stopped cleanly" in out and "Traceback" not in err, (out, err)
    assert elapsed < 2.0, elapsed
