"""The store signs a ratification through the remote-totp service, and the file key stays a named fallback (card 54).

Six scenarios, on the real components: `serve` is driven through the CLI runner with its listener replaced, its
signing-service options pointed at a real `isidium-signer` listener on 127.0.0.1 (certificates minted by
`tests/signer/test_service.py`, hosts `*.example.invalid`); the rest hold both signers on the in-memory harness, the
service stood in for by `DevStubService`, which signs with its own key. That key is bound by the realm, which stands
in for the owner's enrolment of the service's key (card 56) — the pin stays the file key (A1).
"""

from __future__ import annotations

import copy
import inspect
import socket
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from isidium.store.client import cli as cli_mod
from isidium.store.client.transport import Transport
from isidium.store.core import chain
from isidium.store.core.refusal import Refusal
from isidium.store.server import http as http_mod
from isidium.store.server.api import Api
from isidium.store.server.gitrepo import GitCli, MemGit
from isidium.store.server.journal import Journal
from isidium.store.server.service import Service
from isidium.store.server.signer import (
    DevStubService,
    HttpsService,
    RemoteTotp,
    SoftwareKey,
    SoftwareKeyAck,
)
from isidium.store.server.store import Store

from ..signer.test_service import VALUE
from ..signer.test_service import Rig as ServiceRig
from ..signer.test_service import rig as rig  # the fixture, re-exported: a real listener with minted certificates
from .conftest import OWNER, REF_FILES, REGISTRY, Clock, Harness, store_on_disk, tenant_checkout

TENANT = "sartor"
ROOT = "docs/work/"
WAIVER = "software-grade signatures are acceptable for this tenant for now"
BOTH = ["remote-totp", "software_key_ack"]
POLL_MS = 750  # not the schema's 2000: a serve that passed a constant reads 2000, not this
SERVICE_FPR = "ab" * 32  # the fingerprint serve is told; the real one is the service's, by pointer
EXTRA: dict[str, Any] = {
    "shapes": {"allowed": ["bdd", "task", "spike", "ears"], "default": "bdd"},
    "effort": {"tiers": ["default"]},
    "time_skew": 600,
    "inbox": {"max_per_run": 10},
    "signer": {"backends": BOTH, "remote-totp": {"poll_interval_ms": POLL_MS}},
}


# ---- the harness: a store holding the file key and the service ----------------------------------------------------


class Ticker:
    """A clock that only the code under test moves: `sleep` records its argument and advances `now`, and a service
    stand-in advances it for the time a call takes. No test here waits on, or reads, the real clock."""

    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def sleep(self, s: float) -> None:
        self.slept.append(s)
        self.now += s

    def monotonic(self) -> float:
        return self.now


@dataclass
class Both:
    h: Harness  # `h.signer` is the file key, `h.st` the store
    remote: RemoteTotp
    stub: DevStubService

    @property
    def st(self) -> Store:
        return self.h.st

    @property
    def file(self) -> SoftwareKeyAck:
        return self.h.signer


def both(*, decline: bool = False, approve_after: int = 0, timeout_s: int = 600) -> Both:
    """`serve`'s construction, in memory: the file key as the store's signer and the pin, `software_fprs` its
    fingerprint, the service then added by `use_signer`, and its key bound so a remote-totp signature verifies."""
    clock = Clock(1_787_000_000)
    key, realm_key, service_key = SoftwareKey.generate(), SoftwareKey.generate(), SoftwareKey.generate()
    file = SoftwareKeyAck(key, clock, time_skew_s=600)
    realm = SoftwareKeyAck(realm_key, clock, time_skew_s=600)
    repo = MemGit()
    repo.commit(dict(REF_FILES), "seed@example", "2026-08-01T00:00:00Z", "seed the ref targets")
    st = Store(
        TENANT,
        repo,
        Journal(":memory:", TENANT),
        REGISTRY,
        clock,
        file,
        root=ROOT,
        realm_principal="realm-svc@agents.example",
        software_fprs=frozenset({file.key_fpr}),
    )
    st.init(OWNER, software_key_ack=WAIVER, extra=EXTRA)
    st.bind(realm, file.key_fpr, "owner", "2026-01-01T00:00:00Z")
    stub = DevStubService(service_key, clock, approve_after=approve_after, decline=decline)
    ticker = Ticker()
    remote = RemoteTotp(
        stub,
        service_key.public.key_fpr,
        POLL_MS,
        timeout_s=timeout_s,
        sleep=ticker.sleep,
        monotonic=ticker.monotonic,
    )
    st.use_signer(remote)
    st.monotonic = ticker.monotonic  # the store's start and the signer's clock are one clock, as in production
    st.bind(realm, remote.key_fpr, "owner", "2026-01-01T00:00:00Z")
    return Both(Harness(st, file, realm, clock, key), remote, stub)


def ratify(b: Both, card: int, backend: str | None = None) -> dict[str, Any]:
    """A signed sitting through `Api.call`, the door the channel reaches."""
    args: dict[str, Any] = {"ids": [card], "dry_run": False}
    if backend is not None:
        args["backend"] = backend
    result: dict[str, Any] = Api(b.st).call("ratify", OWNER, args)
    return result


def signed_by(st: Store) -> str:
    """The key fingerprint on the newest signature the policy chain holds."""
    sig = st.policy[-1]["sig"]
    return chain.parse_sig(sig)[1]


def declare(st: Store, backends: list[str]) -> None:
    """A config-policy write that changes `signer.backends`, as the owner would make it."""
    tree = copy.deepcopy(st.config_tree)
    tree["signer"]["backends"] = backends
    st.write("config.toml", tree, {"seq": st.policy[-1]["seq"], "h": st.policy[-1]["h"]}, None, OWNER)


# ---- S1: serve builds the remote signer from its options -----------------------------------------------------------


def serve_args(
    tmp_path: Path,
    rig: ServiceRig,
    journal: Path,
    bare: Path,
    key_file: Path,
    *,
    whole: bool,
    call_timeout: str = "5.0",
) -> list[str]:
    host, port = rig.listener.address
    registration = tmp_path / "registration.json"
    registration.write_text('{"CN=owner": ["amodal1@example", "owner"]}', encoding="utf-8")
    args = [
        *("serve", "--tenant", TENANT, "--repo", str(bare), "--journal", str(journal), "--root", ROOT),
        *("--registration", str(registration), "--certificate", str(rig.named.cert), "--key", str(rig.named.key)),
        *("--ca", str(rig.ca.path), "--host", "127.0.0.1", "--signer", str(key_file)),
        *("--signing-service-host", host),
    ]
    if whole:
        args += [
            *("--signing-service-port", str(port), "--signing-service-ca", str(rig.ca.path)),
            *("--signing-service-cert", str(rig.named.cert), "--signing-service-key", str(rig.named.key)),
            *("--signing-service-fpr", SERVICE_FPR, "--signing-service-timeout-s", call_timeout),
        ]
    return args


def test_serve_builds_the_remote_signer(tmp_path: Path, rig: ServiceRig, monkeypatch: pytest.MonkeyPatch) -> None:
    checkout = tenant_checkout(tmp_path)
    journal = tmp_path / "journal.db"
    store_on_disk(checkout, journal).init(OWNER, software_key_ack=WAIVER, extra=EXTRA)
    bare = tmp_path / "serve.git"
    GitCli.clone(tmp_path / "origin.git", bare, "isidium-store", f"store@{TENANT}", root=ROOT)
    key_file = tmp_path / "file-key.pem"
    file_key = SoftwareKey.generate()
    file_key.save(key_file)

    built: list[Service] = []

    async def serve_forever(service: Service, *_: Any) -> None:
        built.append(service)

    monkeypatch.setattr(http_mod, "serve_forever", serve_forever)
    monkeypatch.setattr(http_mod, "tls_context", lambda *_: None)

    # a partial set is refused at start, naming what is missing, before anything listens
    res = CliRunner().invoke(cli_mod.app, serve_args(tmp_path, rig, journal, bare, key_file, whole=False))
    assert res.exit_code == 2 and "signer.service-options" in res.output and "--signing-service-port" in res.output
    assert built == []

    # R5: one call's bound that would push the owner's wait past the client channel's timeout is refused at start, as
    # every other bad option is (exit 2, a named rule), and the store never listens
    for call_timeout in ("60", "0"):
        res = CliRunner().invoke(
            cli_mod.app, serve_args(tmp_path, rig, journal, bare, key_file, whole=True, call_timeout=call_timeout)
        )
        assert res.exit_code == 2 and "signer.service-options" in res.output, (call_timeout, res.output)
        assert built == []

    res = CliRunner().invoke(cli_mod.app, serve_args(tmp_path, rig, journal, bare, key_file, whole=True))
    assert res.exit_code == 0, res.output
    (service,) = built
    store = service.api.store
    remote = store.signer
    assert isinstance(remote, RemoteTotp) and remote.backend == "remote-totp"
    assert remote.poll_interval_ms == POLL_MS and remote.key_fpr == SERVICE_FPR
    https = remote.service
    assert isinstance(https, HttpsService)
    assert (https.host, https.port, https.timeout_s) == (*rig.listener.address, 5.0)
    # C2: the signer's wait plus one call stays under the client channel's timeout, so the store gives up before its
    # caller does
    assert remote.timeout_s + https.timeout_s < inspect.signature(Transport.__init__).parameters["timeout"].default
    # the file key is held, by name, and is the only key graded software
    held = store.signers["software_key_ack"]
    assert isinstance(held, SoftwareKeyAck) and held.key_fpr == file_key.public.key_fpr
    assert store.software_fprs == {file_key.public.key_fpr}

    # the client the store built speaks the service's wire: a submit reaches the real listener, and is pending
    assert rig.service.entered == 0
    rid = https.submit(TENANT, VALUE, rig.clock.now, [("1", "ratified", VALUE, "")])
    assert rig.service.entered == 1 and https.poll(rid) is None


# ---- S2: remote-totp by default, the file key by name, an undeclared backend refused -------------------------------


def test_backend_choice(monkeypatch: pytest.MonkeyPatch) -> None:
    b = both()
    st, service_fpr, file_fpr = b.st, b.remote.key_fpr, b.file.key_fpr
    assert st.signer is b.remote  # remote-totp is the default once the store holds it

    # (a) no backend named: the service signs, the file key does not
    a, c1, c2 = b.h.draft("a"), b.h.draft("b"), b.h.draft("c")
    filed = b.file.calls
    ratify(b, a)
    assert signed_by(st) == service_fpr and len(b.stub.requests) == 1 and b.file.calls == filed

    # (b) the file key by name: the service is not asked
    ratify(b, c1, "software_key_ack")
    assert signed_by(st) == file_fpr and len(b.stub.requests) == 1 and b.file.calls == filed + 1

    # (c) held but undeclared is refused by `use_backend`, and the signer it names is never called
    declare(st, ["remote-totp"])
    asked, filed, rows = len(b.stub.requests), b.file.calls, st.journal.head
    with pytest.raises(Refusal) as err:
        ratify(b, c2, "software_key_ack")
    assert err.value.rule == "signer.backend-unavailable" and "not declared" in err.value.detail
    assert b.file.calls == filed and len(b.stub.requests) == asked and st.journal.head == rows
    st.signer = b.file  # the write that drops remote-totp from the declaration cannot itself be signed by it
    declare(st, ["software_key_ack"])
    st.signer = b.remote
    asked = len(b.stub.requests)
    with pytest.raises(Refusal) as err:
        ratify(b, c2)
    assert err.value.rule == "signer.backend-unavailable" and "'remote-totp'" in err.value.detail
    assert len(b.stub.requests) == asked
    ratify(b, c2, "software_key_ack")  # the positive control: the declared one signs
    assert signed_by(st) == file_fpr

    # a backend the config declares and this store does not hold is refused too, naming what it holds
    declare(st, [*BOTH])
    del st.signers["software_key_ack"]
    with pytest.raises(Refusal) as err:
        ratify(b, b.h.draft("d"), "software_key_ack")
    assert err.value.rule == "signer.backend-unavailable" and "holds no signer" in err.value.detail

    # (d) the terminal carries the name
    seen: list[tuple[str, Mapping[str, Any]]] = []
    monkeypatch.setattr(cli_mod, "_run", lambda name, args, text=False: seen.append((name, dict(args))))
    CliRunner().invoke(cli_mod.app, ["ratify", "5", "--sign", "--backend", "software_key_ack"])
    CliRunner().invoke(cli_mod.app, ["ratify", "5", "--sign"])
    assert seen == [
        ("ratify", {"ids": [5], "dry_run": False, "backend": "software_key_ack"}),
        ("ratify", {"ids": [5], "dry_run": False}),
    ]


# ---- S3: a remote-totp signature is not software-grade and a file-key one is --------------------------------------


def test_software_grade_by_backend() -> None:
    b = both()
    st = b.st
    assert list(st.eff["signer"]["backends"]) == BOTH
    a, c = b.h.draft("a"), b.h.draft("b")
    ratify(b, a)
    ratify(b, c, "software_key_ack")
    assert st.dispatch()["ready"] == [{"id": a, "software_grade": False}, {"id": c, "software_grade": True}]
    # C3: with two backends the grading is the pin alone — the service's key is not in the software set
    assert st._software_fprs() == frozenset({b.file.key_fpr})


# ---- S4: a declined or timed-out signature leaves nothing signed --------------------------------------------------


def state_of(st: Store, card: int) -> tuple[Any, ...]:
    """Everything a signed ratification would move: the card's history and status, the policy, the journal, the repo."""
    doc, _ = st.show(card)
    return (
        [e["act"] for e in doc.history],
        doc.head["status"],
        len(st.policy),
        st.journal.head,
        len(st.journal.rows()),
        st.repo.head,
    )


def test_a_declined_signature_leaves_nothing() -> None:
    for rule, stand_in in (
        ("signer.declined", {"decline": True}),
        ("signer.timeout", {"approve_after": 10**6, "timeout_s": 1}),
    ):
        b = both(**stand_in)
        st = b.st
        a = b.h.draft("a")
        before = state_of(st, a)
        with pytest.raises(Refusal) as err:
            ratify(b, a)
        assert err.value.rule == rule
        assert state_of(st, a) == before and st.dispatch()["ready"] == []
        # the positive control: the refusal wedged nothing — the file key, named, signs the same card
        ratify(b, a, "software_key_ack")
        assert st.dispatch()["ready"] == [{"id": a, "software_grade": True}]


def test_a_transport_failure_is_named_and_leaves_nothing(rig: ServiceRig) -> None:
    """The real `HttpsService`: a refused connection and a service that accepts and never answers each surface as a
    `signer.*` refusal through ratify (R4, C-5) — not as the bare `OSError` the service layer calls `service.internal`."""
    ca, cert, key = rig.ca.path, rig.named.cert, rig.named.key
    # `closed` stays bound, never listening, for the whole test: a connect to it is refused, and the port cannot be
    # handed to `silent` (a freed ephemeral port can be, and then the "refused" case would time out instead).
    with socket.socket() as closed, socket.socket() as silent:
        closed.bind(("127.0.0.1", 0))
        closed_port = closed.getsockname()[1]
        silent.bind(("127.0.0.1", 0))  # listens, so the connect succeeds; nothing ever completes the handshake
        silent.listen(1)
        silent_port = silent.getsockname()[1]
        for rule, service in (
            # a refused connection is immediate on Linux and takes about 2 s on Windows: the client's timeout is set above
            # that, so the platform's refusal timing cannot read as `signer.timeout` (C5)
            ("signer.unreachable", HttpsService("127.0.0.1", closed_port, ca, cert, key, 10.0)),
            ("signer.timeout", HttpsService("127.0.0.1", silent_port, ca, cert, key, 0.3)),
        ):
            b = both()
            b.st.use_signer(
                RemoteTotp(service, b.remote.key_fpr, POLL_MS, sleep=lambda _: None, monotonic=b.st.monotonic)
            )  # the store's clock: its start and the signer's are one clock
            a = b.h.draft("a")
            head, rows = b.st.journal.head, len(b.st.journal.rows())
            with pytest.raises(Refusal) as err:
                ratify(b, a)
            assert err.value.rule == rule
            assert (b.st.journal.head, len(b.st.journal.rows())) == (head, rows) and b.st.dispatch()["ready"] == []


# ---- S5: the wait is bounded by the clock, not by the sleeps ------------------------------------------------------


class SlowService:
    """A service whose every call takes time on the `Ticker`: `submit_cost` and `poll_cost` seconds. It never approves
    unless told to (`approve_after` polls, signing with `key`), and it raises past `POLL_CAP` polls, so a wait that
    does not end fails the test instead of hanging it."""

    POLL_CAP = 1000

    def __init__(
        self,
        ticker: Ticker,
        submit_cost: float,
        poll_cost: float,
        key: SoftwareKey | None = None,
        approve_after: int | None = None,
    ) -> None:
        self.ticker, self.submit_cost, self.poll_cost = ticker, submit_cost, poll_cost
        self.key, self.approve_after = key, approve_after
        self.polls = 0
        self.signed: tuple[str, str] | None = None

    def submit(self, tenant: str, value: str, at_epoch: int, display: Any, time_skew_s: int | None = None) -> str:
        self.ticker.now += self.submit_cost
        self.signed = (tenant, value)
        return "r1"

    def poll(self, request_id: str) -> str | None:
        self.polls += 1
        if self.polls > self.POLL_CAP:
            raise AssertionError("the wait outlasted its bound")
        self.ticker.now += self.poll_cost
        if self.key is not None and self.approve_after is not None and self.polls > self.approve_after:
            assert self.signed is not None
            return chain.format_sig(
                "ed25519", self.key.public.key_fpr, self.key.sign_raw(chain.sig_bytes(*self.signed))
            )
        return None


def test_the_wait_is_bounded_by_the_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    channel = inspect.signature(Transport.__init__).parameters["timeout"].default
    interval_s = 0.25
    # (i) every poll is slow; (ii) the submit is slow too. `c` is the service's per-call bound in each case.
    for c, submit_cost, poll_cost in ((10.0, 9.0, 9.0), (50.0, 49.0, 49.0)):
        ticker = Ticker()
        service = SlowService(ticker, submit_cost, poll_cost)
        remote = RemoteTotp(
            service, SERVICE_FPR, int(interval_s * 1000), timeout_s=600, sleep=ticker.sleep, monotonic=ticker.monotonic
        )
        with pytest.raises(Refusal) as err:
            remote.sign(TENANT, VALUE, 0, [])
        assert err.value.rule == "signer.timeout"
        # the sum of the sleeps would let 600 / 0.25 polls run whatever each cost; the clock stops it at the deadline
        # plus the one call that began before it, and the serve-time check keeps `600 + c` under the channel's timeout
        assert ticker.now <= 600 + c < channel
        assert max(ticker.slept) <= interval_s
        assert service.polls < SlowService.POLL_CAP

    # the positive control: a slow service that does approve returns a signature that verifies
    key = SoftwareKey.generate()
    ticker = Ticker()
    service = SlowService(ticker, 9.0, 9.0, key=key, approve_after=3)
    remote = RemoteTotp(service, key.public.key_fpr, 250, timeout_s=600, sleep=ticker.sleep, monotonic=ticker.monotonic)
    assert chain.verify_sig(remote.sign(TENANT, VALUE, 0, []), TENANT, VALUE) and service.polls == 4

    # The store-level case, through `Api.call` (C10): the wait counts from the moment the call reached the store, so
    # the store's own work before the signer is inside the bound. Numbers: the store spends 5 s before the signer, the
    # submit takes 3.75 s, each poll 59 s (within serve's per-call 60 s), the interval is 0.25 s.
    #   counted from the call (0): poll 9 ends at 601, the sleep is clipped to 601.25 (left -1.25) -> raises at 601.25.
    #   counted from the submit (5): poll 10 begins at 601.25 (left 3.75), ends at 660.25, sleeps to 660.5 >= 660.
    # (A 59 s submit and 59 s polls end at 656.5 on both loops and cannot tell them apart.)
    b = both()
    card = b.h.draft("the-store-level-wait")
    ticker = Ticker()
    b.st.monotonic = ticker.monotonic

    def store_work(**_: Any) -> None:
        ticker.now += 5.0

    monkeypatch.setattr(b.st, "_sync_to_main", store_work)  # the store's own work, as time on the ticker
    slow = SlowService(ticker, 3.75, 59.0)
    b.st.use_signer(
        RemoteTotp(slow, b.remote.key_fpr, 250, timeout_s=600, sleep=ticker.sleep, monotonic=ticker.monotonic)
    )
    before = state_of(b.st, card)
    with pytest.raises(Refusal) as err:
        ratify(b, card)
    assert err.value.rule == "signer.timeout"
    assert ticker.now == 601.25 < channel
    assert state_of(b.st, card) == before and b.st.dispatch()["ready"] == []
    assert b.st.began is None


# ---- S6: a signature that does not verify, or is by another key, is refused ---------------------------------------


class Canned:
    """A service that approves at once with whatever `make(tenant, value)` returns."""

    def __init__(self, make: Callable[[str, str], str]) -> None:
        self.make, self.asked = make, 0

    def submit(self, tenant: str, value: str, at_epoch: int, display: Any, time_skew_s: int | None = None) -> str:
        self.asked += 1
        self.pending = (tenant, value)
        return "r1"

    def poll(self, request_id: str) -> str | None:
        return self.make(*self.pending)


def test_a_wrong_signature_is_refused() -> None:
    b = both()
    st, fpr = b.st, b.remote.key_fpr  # the configured service key; `b.stub.key` holds it
    other = SoftwareKey.generate()

    def signed(key: SoftwareKey, as_fpr: str, value_of: Callable[[str], str]) -> Callable[[str, str], str]:
        return lambda tenant, value: chain.format_sig(
            "ed25519", as_fpr, key.sign_raw(chain.sig_bytes(tenant, value_of(value)))
        )

    cases = (
        # (a) a valid signature by a key other than the configured one
        ("signer.wrong-key", signed(other, other.public.key_fpr, lambda v: v)),
        # (b) the configured key's fingerprint on a signature over a different value
        ("signer.bad-signature", signed(b.stub.key, fpr, lambda v: v + "x")),
        # (c) a string that is not a signature at all
        ("signer.bad-signature", lambda tenant, value: "not-a-signature"),
    )
    for n, (rule, make) in enumerate(cases):
        a = b.h.draft(f"wrong-signature-{n}")
        st.use_signer(RemoteTotp(Canned(make), fpr, POLL_MS, sleep=lambda _: None, monotonic=st.monotonic))
        before = state_of(st, a)
        with pytest.raises(Refusal) as err:
            ratify(b, a)
        assert err.value.rule == rule
        assert state_of(st, a) == before and st.dispatch()["ready"] == []

    # the positive control: the correctly keyed service signs, and the card is ready and not software-grade
    st.use_signer(RemoteTotp(b.stub, fpr, POLL_MS, sleep=lambda _: None, monotonic=st.monotonic))
    ok = b.h.draft("control")
    ratify(b, ok)
    assert st.dispatch()["ready"] == [{"id": ok, "software_grade": False}]
