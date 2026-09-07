"""One call surface and **one transport** (7bg.2, owner verbatim: *"yes on getting rid of loopback and local mode"*):
the pinned mTLS channel to the store service, verifying the store's certificate against the CA the registration pins
and presenting this client's certificate.

There was a second one. `LocalTransport` built a `Store`, a `Journal` and a `GitCli` in the caller's own process and
took its caller's identity from `.isidium/client.toml` — a `principal` and a `grant` the file asserted about itself,
with no channel to authenticate them and nothing able to refuse them. It is deleted, and with it the only path on
which a caller saw an unfiltered refusal. **What a caller may do is now decided in exactly one place**: the
certificate on the connection, against the tenant registration the store holds (03b §2).

The store-side imports went with it, and they were the expensive half of this module: `Store`, `Api`, `GitCli`,
`Journal` and `Signer` dragged `cryptography.x509` and the generated pydantic models into every process that imported
a transport — including, through `client/cli.py`, the pre-commit hook. See the K3 handoff for what that measured.
"""

from __future__ import annotations

import ssl
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol

from ..core.refusal import Refusal, ValidationRefusal
from .config import ClientConfig


class Channel(Protocol):
    """What `McpServer` needs of its channel: one call. `Transport` is the real one; a test hands in a double
    that answers `call` and nothing else, which is all the server ever asks of it [K5b, 2026-09-04, type-only:
    no runtime path changed, the contract the doubles already satisfied is now named]."""

    def call(self, name: str, args: Mapping[str, Any]) -> Any: ...


class Transport:
    """The pinned channel (03 §1.3): mTLS to the store container's address, the CA from the registration."""

    def __init__(self, cfg: ClientConfig, workdir: Path, timeout: float = 660.0) -> None:
        # `httpx` is imported here and not at module scope, deliberately (C-13, which reaches code as well as data,
        # ruled 2026-08-30). Every process that opens a channel pays this import inside a call it is already making
        # over a network; a process that merely imports this module to name the type does not. That is the whole of
        # what makes `client/cli.py` importable without the channel's own dependency tree.
        import httpx

        if not (cfg.address and cfg.ca and cfg.cert and cfg.key):
            raise Refusal("client.channel", "", "the channel needs address, ca, cert and key (the registration's half)")
        ctx = channel_context(workdir / cfg.ca, workdir / cfg.cert, workdir / cfg.key)
        self.http = httpx.Client(base_url=cfg.address, verify=ctx, timeout=timeout)  # the signer's round trip is long

    def call(self, name: str, args: Mapping[str, Any]) -> Any:
        r = self.http.post(f"/call/{name}", json=dict(args))
        payload = r.json()
        if r.status_code != 200:
            raise refusal_from(payload)
        return payload["result"]


def channel_context(ca: Path, cert: Path, key: Path) -> ssl.SSLContext:
    """The client's TLS context: the store's certificate verified against the registration's CA and nothing else,
    this client's certificate presented [K10, item 4].

    Built by the standard library, not by `httpx.create_ssl_context(verify=<path>)`: httpx 0.28 deprecates that
    door (nine `DeprecationWarning`s across the suite, all of them this one line) and the next major removes it,
    at which point every client stops connecting — and the failure would surface at the forge on Renovate's bump,
    nowhere sooner. `ssl.create_default_context(cafile=…)` is the same context the deprecated call built from a
    file path: `CERT_REQUIRED`, hostname checking on, the system store *not* loaded, so the pin holds
    (`tests/store/test_channel.py`'s pinning test is the discriminator, and `tests/store/test_k10.py` builds this
    with warnings as errors)."""
    ctx = ssl.create_default_context(cafile=str(ca))
    ctx.load_cert_chain(str(cert), str(key))
    return ctx


def refusal_from(payload: Mapping[str, Any]) -> Refusal:
    """The refusal the store sent, rebuilt as the typed value it was raised as (Q7, ruled 2026-08-29).

    A payload carrying `verdicts` came from a gate that reports every failure, so it rebuilds as a
    `ValidationRefusal` whose `verdicts` are typed `Refusal`s — the caller reads the failed field names off the
    list rather than parsing them back out of `detail`. Without the array it rebuilds as a plain `Refusal`, which
    is what every non-validation gate sends and what an older store sends for a validation one; that arm is what
    makes the wire change additive rather than a break.
    """
    rows = payload.get("verdicts")
    path = str(payload.get("path", ""))
    if isinstance(rows, list):
        return ValidationRefusal(
            [
                Refusal(str(v.get("rule", "")), str(v.get("path", "")), str(v.get("detail", "")))
                for v in rows
                if isinstance(v, dict)
            ],
            path,
        )
    return Refusal(str(payload.get("rule", "service.error")), path, str(payload.get("detail", "")))
