"""The one shape, end to end (7bg.2, owner verbatim: *"yes on getting rid of loopback and local mode"*).

The WP3 acceptance walk used to run through `LocalTransport` — a `Store` built in the test's own process, with a
caller the client file asserted about itself. That transport is deleted, so this file runs the same walk over the
**channel**: the client's real `Transport`, over a real mTLS socket, to a real `Store` on a real git checkout, with
the caller resolved from the certificate on the connection. What the bridge session types is what is tested, and
now the boundary it crosses is the only one there is.

**Nothing had ever opened the channel.** `refusal_from` is a pure function in the same module and `test_k1b_iii.py`
covers it, but no test had ever constructed a `Transport` — on either side of `init` — which is why the defect in
`install.init` (the operator's `--root` dropped on the https path and passed on the local one) could sit there
through two chunks. The gap was in the shape of the tests, not in anyone's care: the arm that was easy to drive was
the arm that was driven, and it was the arm that did not ship.

The certificate machinery is `test_edge.py`'s (`authority`, `issue`), imported rather than copied — three
certificate builders in one suite is three things to keep in agreement. What is new here is the listener running in
a thread while a **synchronous** `httpx` client calls it from the test: `Transport` is sync by design (a CLI and an
MCP server are), and `server/http.py` is asyncio, so the two cannot share one thread. `test_edge.py` drives the
socket from inside the loop and never needs this.
"""

from __future__ import annotations

import asyncio
import importlib.resources
import os
import subprocess
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import httpx
import pytest

from isidium.store.client import hook as hook_mod
from isidium.store.client.config import CLIENT_FILE, ClientConfig
from isidium.store.client.install import init as client_init
from isidium.store.client.transport import Transport
from isidium.store.core.refusal import Refusal, ValidationRefusal
from isidium.store.registry.loader import Registry
from isidium.store.server.api import Api
from isidium.store.server.http import Limits, start, tls_context
from isidium.store.server.service import Registration, Service
from isidium.store.server.store import Store

from .conftest import BASE_SCOPE, base_head, store_on_disk, tenant_checkout
from .test_edge import authority, issue

OWNER_NAME = "owner@example"  # the certificate's common name
OWNER_SUBJECT = "CN=owner@example"  # the registration's key: the whole subject (K6)
OWNER_PRINCIPAL = "amodal1@example"


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, check=True, text=True).stdout


@dataclass(frozen=True)
class Channel:
    """A tenant checkout, and the client file that reaches the store serving it."""

    checkout: Path
    cfg: ClientConfig
    store: Store


@pytest.fixture
def open_channel(tmp_path: Path) -> Iterator[Callable[..., Channel]]:
    """Start a store serving one tenant checkout over mTLS, and hand back the client file that reaches it.

    A factory rather than a plain fixture because **the tracking root is the store's, set when it is built** — the
    same value `serve --root` supplies — and a test that chooses a root has to build a store serving that root. In
    local mode the two agreed by construction: `LocalTransport` built the store out of the client file. Over the
    channel they are two settings that must be made to agree, which is a seam this chunk names and does not close.

    The store is **not** `init`ed here: opening the policy chain is the first thing a walk does, over the channel,
    and that is the half of `install.init` this fixture exists to make testable. `push` is left at its default,
    which is what `serve` builds, so the walk's push step is the real one against the checkout's own bare remote.
    """
    checkout = tenant_checkout(tmp_path)
    certs = tmp_path / "pki"
    certs.mkdir()
    ca = authority(certs, "tenant-ca")
    server_cert, server_key = issue(ca, certs, "store.sartor", "store", server=True)
    client_cert, client_key = issue(ca, certs, OWNER_NAME, "owner")
    context = tls_context(server_cert, server_key, ca.path)
    opened: list[tuple[asyncio.AbstractEventLoop, asyncio.AbstractServer, threading.Thread]] = []

    def here(path: Path) -> str:
        """A path as a client file names one: relative to the checkout (`workdir / cfg.ca`), forward slashes."""
        return os.path.relpath(path, checkout).replace("\\", "/")

    def open_at(root: str = "docs/work/") -> Channel:
        ready = threading.Event()
        state: dict[str, Any] = {}

        def serve() -> None:
            # **The store is built in the serving thread, and it has to be.** `Journal` opens its SQLite connection
            # at construction and sqlite3 refuses a connection used off the thread that made it — building the store
            # in the fixture and serving it here failed every call with `service.internal`. It is also the honest
            # shape: in a deployment the store is built by the process that serves it.
            store = store_on_disk(checkout, tmp_path / "journal.sqlite", root=root)
            registration = Registration({OWNER_SUBJECT: (OWNER_PRINCIPAL, "owner")}, lambda: int(time.time()))
            service = Service(Api(store), registration, "sartor")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.set_exception_handler(lambda _loop, _context: None)  # a refused handshake is data, not a crash
            server = loop.run_until_complete(start(service, "127.0.0.1", 0, context, Limits()))
            state["loop"], state["server"], state["store"] = loop, server, store
            state["port"] = int(server.sockets[0].getsockname()[1])
            ready.set()
            loop.run_forever()

        thread = threading.Thread(target=serve, name="store-edge", daemon=True)
        thread.start()
        assert ready.wait(30), "the listener never bound"
        opened.append((state["loop"], state["server"], thread))
        return Channel(
            checkout=checkout,
            cfg=ClientConfig(
                tenant="sartor",
                address=f"https://localhost:{state['port']}",
                ca=here(ca.path),
                cert=here(client_cert),
                key=here(client_key),
            ),
            store=state["store"],
        )

    yield open_at

    for loop, server, thread in opened:
        loop.call_soon_threadsafe(server.close)
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=30)
        assert not thread.is_alive(), "the listener thread outlived the test"


def pull(tenant: Path) -> None:
    """Bring the store's commits into the tenant's checkout.

    **New with K4, and it is a property rather than test plumbing.** The store used to write into this very working
    tree, so its commits appeared here the instant it made them. It now holds its own partial bare clone, commits
    there and pushes to the shared remote — so a governed file reaches the tenant's checkout the way any other
    commit does, by fetching it. Every `is_file()` below that used to be free now costs a pull, and that is the
    honest shape: the store is the writer, this checkout is a reader.
    """
    git(tenant, "pull", "-q", "--ff-only", "origin", "main")


def test_the_walk_runs_over_the_channel(open_channel: Callable[..., Channel]) -> None:
    """`init` → write → dry run → ratify → push → check → the board → the hook, every store call over mTLS."""
    channel = open_channel()
    tenant = channel.checkout

    # 1. `isidium init`: the local half (client file, hook, schemas) and then the policy chain, over the channel
    out = client_init(tenant, channel.cfg, {"software_key_ack": "software-grade is acceptable for the bridge"})
    assert (tenant / CLIENT_FILE).is_file()
    assert (tenant / ".git" / "hooks" / "pre-commit").is_file()
    assert (tenant / ".isidium" / "schemas" / "card@1.toml").is_file()
    assert ".isidium/" in (tenant / ".gitignore").read_text(encoding="utf-8")
    assert out["config"]["entry"]["act"] == "created" and "sig" in out["config"]["entry"]
    assert not (tenant / "docs" / "work" / "config.toml").exists(), "the store does not write into this checkout"
    pull(tenant)
    assert (tenant / "docs" / "work" / "config.toml").is_file()

    # the installed schemas are the store's own bytes — a local check and the store cannot disagree (03b §4)
    shipped = importlib.resources.files("isidium.store.registry").joinpath("schemas", "card@1.toml")
    assert (tenant / ".isidium" / "schemas" / "card@1.toml").read_bytes() == shipped.read_bytes()

    # 2. a card, written through the client's transport (what `isidium write --new` does)
    transport = Transport(*ClientConfig.find(tenant))
    head = base_head(0, "draft")
    head.pop("id")
    r = transport.call("write", {"new_slug": "first-bridged-card", "document": {"head": head, "scope": BASE_SCOPE}})
    cid = r["id"]
    pull(tenant)
    assert cid == 1 and (tenant / "docs/work/cards/0001-first-bridged-card.md").is_file()
    assert r["entry"]["act"] == "created" and "sig" not in r["entry"]

    # 3. the dry run — always, before presenting (round 48). The verdict map's keys arrived as JSON object keys, so
    # they are strings here and were `int`s in the in-process walk: the wire is a real boundary and this is where it
    # shows. (The `verdicts` map is `{id: [{rule, path, detail}]}` since K10 — Q20, ruled 2026-09-06 — where it had
    # been `list[str]` of rendered refusals, a finding carried since K1b-iii; `tests/store/test_k10.py` asserts the
    # typed shape over the service, this walk asserts the empty case over the real channel.)
    dry = transport.call("ratify", {"ids": [cid], "dry_run": True})
    assert dry["verdicts"][str(cid)] == [] and dry["display"][0][1] == "ratified"

    # 4. the sitting: one signature
    signed = transport.call("ratify", {"ids": [cid], "dry_run": False})
    assert len(signed["entries"]) == 1 and "sig" in signed["manifest"]
    assert all("sig" not in e and e["batch"] == signed["manifest"]["seq"] for e in signed["entries"])

    # 5. **The author is the CERTIFICATE's principal**, and this is the assertion the whole chunk turns on: nothing
    # in this checkout names `amodal1@example`. The client file carries no principal any more; the only place
    # that name exists is the registration the store holds, keyed by the subject of the certificate on the
    # connection. A walk that still read its caller out of a local file would pass every other line here.
    pull(tenant)
    log = git(tenant, "log", "-1", "--format=%an <%ae>|%cn <%ce>|%s").strip()
    assert log == f"amodal1 <{OWNER_PRINCIPAL}>|isidium-store <store@sartor>|batch-manifest"
    assert OWNER_PRINCIPAL not in (tenant / CLIENT_FILE).read_text(encoding="utf-8")
    assert git(tenant, "rev-parse", "HEAD").strip() == git(tenant, "rev-parse", "origin/main").strip()

    # 6. `check` — chain, recompute, signatures, the journal reconciliation, the whole-set rules
    res = transport.call("check", {"id": cid})
    assert res["integrity"] == [] and res["profile"] == []

    # 7. the board and the queue render
    board = transport.call("show", {"target": "board"})["markdown"]
    assert board.startswith("# Board") and "**1**" in board
    q = transport.call("show", {"target": "queue"})
    assert q["open_questions"] == [] and q["merged_not_landed"] is None

    # 8. the hook: offline by design, and unchanged by any of this — a governed path staged here is refused
    card = tenant / "docs/work/cards/0001-first-bridged-card.md"
    card.write_bytes(card.read_bytes() + b"\n")
    git(tenant, "add", "docs/work/cards/0001-first-bridged-card.md")
    assert hook_mod.offending(tenant) == ["docs/work/cards/0001-first-bridged-card.md"]
    assert hook_mod.check(tenant) == 1
    env = {**os.environ, "PYTHONPATH": str(Path("packages/isidium-store/src").resolve())}  # `isidium` is not on PATH
    proc = subprocess.run(
        ["git", "commit", "-q", "-m", "hand edit"], cwd=tenant, capture_output=True, text=True, env=env
    )
    assert proc.returncode != 0 and "governed paths are written by the store" in (proc.stdout + proc.stderr)
    git(tenant, "restore", "--staged", "--worktree", "docs/work/cards/0001-first-bridged-card.md")
    (tenant / "src").mkdir(exist_ok=True)
    (tenant / "src" / "feature.py").write_text("x = 1\n", encoding="utf-8")
    git(tenant, "add", "src/feature.py")
    assert hook_mod.offending(tenant) == [] and hook_mod.check(tenant) == 0
    ok = subprocess.run(
        ["git", "commit", "-q", "-m", "code, not governed"], cwd=tenant, capture_output=True, text=True, env=env
    )
    assert ok.returncode == 0, ok.stdout + ok.stderr


def test_the_chosen_root_reaches_the_store_over_the_channel(open_channel: Callable[..., Channel]) -> None:
    """The defect this chunk found and fixed. `install.init`'s local arm passed `root=chosen_root` to `Store.init`;
    its https arm passed only `store_args` and dropped it. So an operator who ran `isidium init --root work/` over
    the channel got a governed `config.toml` naming no root at all while `.isidium/client.toml` named `work/` — the
    hook and the store disagreeing about which paths are governed, which is what 03b §4 exists to forbid.

    The discriminator is the **governed file's** own text, not the client file's: writing the root locally is what
    the broken version already did, so asserting that alone would pass on the defect.
    """
    channel = open_channel("work/")  # the store serves `work/`; the operator asks for it too
    client_init(channel.checkout, replace(channel.cfg, root="work/"), {"software_key_ack": "ok for the bridge"})
    pull(channel.checkout)  # the store writes in its own clone now (K4)
    governed = (channel.checkout / "work" / "config.toml").read_text(encoding="utf-8")
    assert 'root = "work/"' in governed, "the operator's --root never reached the store"
    assert 'root = "work/"' in (channel.checkout / CLIENT_FILE).read_text(encoding="utf-8")


def test_only_the_root_the_operator_chose_reaches_the_governed_file(open_channel: Callable[..., Channel]) -> None:
    """The other side of that coin, moved here from `test_wp3_apply.py` with K3 because it is a property of
    `install.init`, which runs over the channel now.

    `.isidium/client.toml` is the CLIENT's file and must hold a concrete root — a blank one sends the hook to the
    repo root, silently (S5). `config.toml` is GOVERNED, and a key written there is the tenant's adopted policy.

    **What the governed file names is the store's own root, and nothing the client resolved** [K7b, Q16, ruled
    2026-09-06]. Until K7b the client passed on only a real operator choice and the file stayed silent otherwise,
    so that no copy of `config@1`'s default reached the tenant's file (C-1 one layer out); the K7 review then moved
    `root` by one signed policy write and the store accepted it. Now the store writes the root it was started with
    (`serve --root`) into every tenant it initialises and refuses a tree naming another, so the file's `root` is
    the store's by construction — and the client's resolved root agrees with it because both are the one value
    the operator gave the deployment. The client still passes on only a real choice: this test's client sends
    none, and the file carries the store's.

    Paired with the test above, which is what stops this one passing by sending nothing at all.
    """
    channel = open_channel()
    client_init(channel.checkout, channel.cfg, {"software_key_ack": "ok for the bridge"})
    pull(channel.checkout)  # the store writes in its own clone now (K4)

    declared = str(Registry.for_checkout(channel.checkout).defaults_of("config@1")["root"])
    governed = (channel.checkout / declared / "config.toml").read_text(encoding="utf-8")
    assert f'root = "{channel.store.root}"' in governed, "the tenant's governed file does not name the store's root"
    assert channel.store.root == declared
    assert f'root = "{declared}"' in (channel.checkout / CLIENT_FILE).read_text(encoding="utf-8")


def test_a_refusal_crosses_the_channel_as_the_value_it_was_raised_as(open_channel: Callable[..., Channel]) -> None:
    """The channel is where Q7's typed rebuild has to hold, and the deleted transport was the path where it never
    had to: local mode handed the caller the `Refusal` object itself, so `refusal_from` was never exercised.

    Two shapes, because one alone cannot tell a working rebuild from a wrong one: a plain refusal comes back as a
    `Refusal` with the store's own rule id, and a validation refusal comes back as a `ValidationRefusal` whose
    `verdicts` are typed and name their own failed field."""
    channel = open_channel()
    client_init(channel.checkout, channel.cfg, {"software_key_ack": "ok for the bridge"})
    transport = Transport(*ClientConfig.find(channel.checkout))

    with pytest.raises(Refusal) as unknown:
        transport.call("show", {"target": "card", "id": 4242})
    assert unknown.value.rule == "show.unknown" and not isinstance(unknown.value, ValidationRefusal)

    # a ratified story with neither an acceptance block nor a priority: the gate that reports EVERY failure
    bad = base_head(0, "ratified")
    bad.pop("id")
    bad.pop("acceptance")
    bad.pop("priority")
    with pytest.raises(ValidationRefusal) as failed:
        transport.call("write", {"new_slug": "malformed", "document": {"head": bad, "scope": BASE_SCOPE}})
    assert failed.value.rule == "validate.failed"
    assert all(isinstance(v, Refusal) and v.rule for v in failed.value.verdicts)
    # the field names arrive as DATA, off the array — never parsed back out of `detail` (Q7, C-12)
    assert {"acceptance", "priority"} <= {v.path for v in failed.value.verdicts}, failed.value.verdicts


def test_the_client_pins_the_store_to_the_registrations_authority(open_channel: Callable[..., Channel]) -> None:
    """**The other half of the pin, and nothing asserted it before.** 03 §1.3 has two claims: the store verifies the
    caller's certificate against the registration's CA — proved over a socket in `test_edge.py` — and the client
    verifies the *store's* against the same CA. Only the first had a test; local mode was the reason the second was
    easy to leave, because the transport that mattered was the one with no TLS in it at all.

    A client pointed at a different authority must not complete the call. The discriminator is the pair: the same
    call over the same socket **succeeds** with the pinned CA and **fails** with another, so this cannot pass
    because the store was down, the port was wrong, or the request was never made.
    """
    channel = open_channel()
    client_init(channel.checkout, channel.cfg, {"software_key_ack": "ok for the bridge"})
    assert Transport(*ClientConfig.find(channel.checkout)).call("show", {"target": "queue"}) is not None

    stranger = authority(channel.checkout / ".isidium", "some-other-ca")
    wrong = replace(channel.cfg, ca=os.path.relpath(stranger.path, channel.checkout).replace("\\", "/"))
    with pytest.raises(httpx.ConnectError):  # the TLS verification failure, before any HTTP is written
        Transport(wrong, channel.checkout).call("show", {"target": "queue"})


def test_a_client_file_with_no_channel_is_a_typed_refusal(tmp_path: Path) -> None:
    """There is no second shape to fall back to, so a client file that cannot name the channel says so with a rule
    id rather than quietly opening something else. This is the arm `open_transport`'s `client.mode` used to reach,
    and `client.channel` is now the whole of it."""
    with pytest.raises(Refusal, match=r"client\.channel"):
        Transport(ClientConfig(tenant="sartor"), tmp_path)
