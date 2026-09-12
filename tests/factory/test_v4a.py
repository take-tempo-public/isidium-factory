"""V4a-i — the execution adapter seam (T-C6), the write guard at write time (T-B5 (1)), the container adapter on
podman, and the phase on the row it was dispatched under (card 5's R2).

The properties, and what each test discriminates:

- **The seam names no executor** (R1). The module's own text is the evidence — a `Protocol` that mentions podman
  would still pass a behavioural test, which is why this one reads the source.
- **An adapter is chosen by the registration and nothing else** (R1): an unregistered name refuses, naming the set,
  and nothing falls back to a default.
- **The guard denies at write time**, and the positive discriminator is that the file on disk is unchanged *and*
  the denial was counted — either alone would pass for the wrong reason.
- **Nothing the phase claims is believed**: the change set is recomputed from git, and a result that claims
  something else is refused before `surfaces` is judged.
- **What happened after the row is on the row** (R2): a failed phase ends the run it was dispatched under.

The podman spawns are faked the way V2 faked the forge's — a recording double with an injectable failure — because
what is being tested here is the argv, the retry, the watchdog and the record, none of which needs a container.
"""

from __future__ import annotations

import datetime as _dt
import io
import json
import re
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from isidium.factory import adapter as adapter_mod
from isidium.factory import checkout as checkout_mod
from isidium.factory import cli as cli_mod
from isidium.factory import context as context_mod
from isidium.factory import dispatch as dispatch_mod
from isidium.factory import guard, render
from isidium.factory import runner as runner_mod
from isidium.factory.adapter import AdapterCapabilities, PhaseResult, RunJob
from isidium.factory.container import Container
from isidium.factory.context import TenantContext
from isidium.factory.ledger import Ledger, NewRun
from isidium.factory.tenant import Registration
from isidium.store.client.config import ClientConfig
from isidium.store.core.grammar import Document
from isidium.store.core.refusal import Refusal
from isidium.store.server.api import Api
from isidium.store.server.store import NewCard, Store

from ..store.conftest import BASE_SCOPE, LANDER, OWNER, PLANNER, base_head, git, store_on_disk, tenant_checkout
from . import conformance

ROOT = "docs/work/"
TENANT = "sartor"
URL = "https://github.com/acme/widgets.git"
LOGIN = "isdm-fac-lander[bot]"
IMAGE = "isidium-runner:test"
TOKEN = "sk-ant-oat-not-a-real-token"
EMPTY: dict[str, Any] = {"run_id": "r-0", "events": [], "suggestions": []}
TODAY = _dt.datetime.now(_dt.UTC).date()

# The card the fixture ratifies declares these (`base_head`'s own surfaces) — the guard's set, and the one place a
# phase may write.
INSIDE = "client/cards/validator.py"
OUTSIDE = "docs/work/cards/0001-anything.md"


# rich paints the help; the text is what this asserts, never the escapes around it.
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def refuses(rule: str, fn: Any) -> Refusal:
    with pytest.raises(Refusal) as ei:
        fn()
    assert ei.value.rule == rule, str(ei.value)
    return ei.value


# ------------------------------------------------------------------------------------------- the on-disk harness


@dataclass
class Disk:
    work: Path
    home: Path
    store: Store
    card: int
    ctx: TenantContext
    run_id: str

    def call(self, name: str, args: Any) -> Any:
        return Api(self.store).call(name, LANDER, args)

    def ledger(self) -> Ledger:
        return Ledger(self.home / "ledger.sqlite", TENANT)


@dataclass
class Branch:
    """`dispatch.pick`'s one forge call, made real: the test needs the branch to exist, because the worktree is cut
    from it."""

    work: Path

    def branch(self, name: str, at: str) -> None:
        git(self.work, "branch", name, at)


@pytest.fixture(scope="module")
def disk(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Disk]:
    tmp = tmp_path_factory.mktemp("v4a")
    work = tenant_checkout(tmp)
    st = store_on_disk(work, tmp / "journal.sqlite", root=ROOT)
    st.init(OWNER, software_key_ack="ok for V4a", root=ROOT)
    r = st.write(NewCard("v4a-story"), Document(base_head(0, "draft"), {"Scope": BASE_SCOPE}), None, None, PLANNER)
    assert r.id is not None
    st.ratify([r.id], OWNER)
    st.land(EMPTY, LANDER)
    bare = (tmp / "origin.git").as_posix()
    git(work, "remote", "set-url", "origin", URL)
    git(work, "config", f"url.{bare}.insteadOf", URL)
    home = tmp / "deploy"
    fd = home / TENANT / "factory"
    fd.mkdir(parents=True)
    (fd / "client.toml").write_text(ClientConfig(tenant=TENANT).render(), encoding="utf-8")
    (fd / "forge.toml").write_text(
        f'kind = "token"\nlogin = "{LOGIN}"\nname = "isdm-fac-lander"\nemail = "1+x@users.noreply.github.com"\n'
        'token = "forge.token"\n',
        encoding="utf-8",
    )
    (fd / "forge.token").write_text("ghp_test\n", encoding="utf-8")
    (fd / "claude.token").write_text(TOKEN + "\n", encoding="utf-8")
    until = (TODAY + _dt.timedelta(days=30)).isoformat()
    (fd / "tenant.toml").write_text(
        f'allow_software_grade_until = {until}\nwip = 1\nadapter = "container"\n\n'
        f'[payload]\nmax_bytes = 1000000\n\n[runner]\nimage = "{IMAGE}"\n',
        encoding="utf-8",
    )
    mp = pytest.MonkeyPatch()
    mp.setenv("ISIDIUM_DEPLOY", str(home))
    ctx = context_mod.load(TENANT, work, base="main", root=ROOT)
    led = Ledger(fd / "ledger.sqlite", TENANT)
    row = dispatch_mod.pick(ctx, led, lambda n, a: Api(st).call(n, LANDER, a), Branch(work), card=r.id)
    led.close()
    yield Disk(work, fd, st, r.id, ctx, str(row["run_id"]))
    mp.undo()


@pytest.fixture
def led(disk: Disk) -> Iterator[Ledger]:
    ledger = disk.ledger()
    yield ledger
    ledger.close()


def a_job(disk: Disk, **over: Any) -> RunJob:
    """The job the wrapper would build, without running the wrapper — so the seam's own tests do not depend on it."""
    policy = adapter_mod.ExecutorPolicy.from_effective(disk.ctx.eff)
    fields: dict[str, Any] = {
        "run_id": disk.run_id,
        "card": disk.card,
        "phase": "build",
        "payload": {"form": "isidium-payload 1"},
        "payload_hash": "sha256:" + "0" * 64,
        "worktree": str(disk.work),
        "allowed_writes": (INSIDE, "tests/"),
        "policy": policy,
        "identity": {"agent": "builder", "name": "isdm-fac-lander", "email": "1+x@users.noreply.github.com"},
        "prompt_version": "v1",
    }
    fields.update(over)
    return adapter_mod.job(fields)


# -------------------------------------------------------------------------------------------- the doubles


@dataclass
class Podman:
    """A recording `podman` — every argv kept, the image's two files written as the real entrypoint would. `fail`
    makes every attempt fail; `timeout` makes every attempt time out; `once` fails only the first."""

    result: dict[str, Any] | None = None
    harness: dict[str, Any] | None = None
    fail: str | None = None
    timeout: bool = False
    once: bool = False
    blocks: int = 0
    seen: list[list[str]] = field(default_factory=list)
    env: list[dict[str, str]] = field(default_factory=list)

    def __call__(self, argv: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        self.seen.append(list(argv))
        self.env.append(dict(kw.get("env") or {}))
        if argv[1] == "kill":
            return subprocess.CompletedProcess(argv, 0, "", "")
        first = len([a for a in self.seen if a[1] == "run"]) == 1
        if self.timeout and not (self.once and not first):
            raise subprocess.TimeoutExpired(argv, kw.get("timeout") or 0)
        if self.fail is not None and not (self.once and not first):
            return subprocess.CompletedProcess(argv, 1, "", self.fail)
        rundir = Path(next(a for a in argv if a.endswith(f":{render.RUN}:rw")).rsplit(":", 2)[0])
        if self.harness is not None:  # what the image leaves behind when the harness itself failed
            (rundir / "harness.json").write_text(json.dumps(self.harness), encoding="utf-8")
            return subprocess.CompletedProcess(argv, 1, "", "")
        (rundir / "result.json").write_text(json.dumps(self.result or _harness_result()), encoding="utf-8")
        if self.blocks:
            lines = "".join(json.dumps({"path": OUTSIDE, "reason": "outside"}) + "\n" for _ in range(self.blocks))
            (rundir / "blocks.jsonl").write_text(lines, encoding="utf-8")
        return subprocess.CompletedProcess(argv, 0, "", "")


def _harness_result(**over: Any) -> dict[str, Any]:
    out = {
        "run_id": "ignored — the adapter takes the job's",
        "phase": "build",
        "agent": "builder",
        "model": "ignored",
        "effort": "high",
        "prompt_version": "v1",
        "tokens": 1234,
        "cost_micro": 5678,
        "duration_ms": 9012,
        "outcome": "ok",
        "harness": "claude-code",
        "harness_version": "1.2.3",
        "billing_class": "plan",
    }
    out.update(over)
    return out


@dataclass
class Fake:
    """A deterministic in-process adapter — the conformance suite's second member, and what makes it a suite."""

    result: dict[str, Any] = field(default_factory=_harness_result)
    writes: tuple[str, ...] = ()
    seen: list[RunJob] = field(default_factory=list)

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            name="fake",
            harness="none",
            harness_version="0",
            write_guard_at_write_time=True,
            identity_held_by_wrapper=True,
            budgets=True,
            watchdog=True,
            end_and_resume=True,
            telemetry_per_phase=True,
            billing_class="plan",
            hosts=(),
        )

    def execute(self, job: RunJob) -> PhaseResult:
        self.seen.append(job)
        for rel in self.writes:  # a phase that wrote where the guard would not have let it
            target = Path(job.worktree) / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("written past the guard", encoding="utf-8")
        spec = job.policy.agent(job.identity.agent)
        return adapter_mod.result(
            {
                **self.result,
                "run_id": job.run_id,
                "phase": job.phase,
                "agent": job.identity.agent,
                "model": spec.model,
                "effort": spec.effort,
            }
        )


def hook(path: str, tool: str = "Write") -> int:
    payload = json.dumps({"tool_name": tool, "tool_input": {"file_path": f"{render.WORK}/{path.lstrip('/')}"}})
    old, sys.stdin = sys.stdin, io.StringIO(payload)
    try:
        return guard.main([])
    finally:
        sys.stdin = old


# ----------------------------------------------------------------------------------------------- the seam (R1)


def test_the_seam_names_no_executor() -> None:
    """Card 5's S1. The seam's own text is the evidence: a `Protocol` that mentioned podman would pass every
    behavioural test and still have broken the property, so this reads the module — code and docstrings alike —
    for every word that belongs on the other side of it."""
    import tokenize

    with tokenize.open(adapter_mod.__file__) as fh:
        code = " ".join(t.string.lower() for t in tokenize.generate_tokens(fh.readline) if t.type == tokenize.NAME)
    # The prose above may name them — that is how the property is explained. The CODE may not, which is the
    # property itself: a seam that imports podman has crossed its own line however well it is commented.
    for word in ("podman", "docker", "claude", "github", "forge", "sqlite", "subprocess"):
        assert word not in code, f"{word!r} is named by the seam's code: it belongs behind an adapter"
    assert "pydantic" in code and "protocol" in code, "the token scan read nothing: it would pass vacuously"
    names = {m for m in dir(adapter_mod.Adapter) if not m.startswith("_")}
    assert names == {"capabilities", "execute"}, names


def test_an_unregistered_adapter_is_refused_naming_the_registered_set() -> None:
    """R1: *"an adapter is chosen by the tenant's registration and nothing else"* — and nothing falls back to a
    default, because a tenant that named an adapter it does not have must not silently get another."""
    r = refuses("adapter.unknown", lambda: adapter_mod.resolve("action"))
    assert "container" in r.detail
    assert adapter_mod.resolve("container") is Container


def test_the_policy_is_the_tenants_signed_one_and_a_tenant_without_config6_is_refused(disk: Disk) -> None:
    """Q-V16 (b): `[agents]` and `[executor]` are config@6's, so the executor policy is under the owner's
    signature. A tenant whose policy predates it has no executor policy at all — and is told which version has
    one, rather than being run under a default nobody signed."""
    policy = adapter_mod.ExecutorPolicy.from_effective(disk.ctx.eff)
    assert policy.guard == "write-time" and policy.budgets.max_turns >= 1
    assert policy.agent("builder").model and policy.agent("builder").effort == "xhigh"
    assert policy.agent("plan-refuter").model != policy.agent("judge").model, "Sonnet refutes, Opus judges (7bd)"
    r = refuses("adapter.policy", lambda: adapter_mod.ExecutorPolicy.from_effective({"schema": 5}))
    assert "config@6" in r.detail


def test_an_agent_the_policy_does_not_carry_is_fail_closed(disk: Disk) -> None:
    """A guessed model is spend the owner did not sign — so an agent with no row refuses rather than defaulting."""
    policy = adapter_mod.ExecutorPolicy.from_effective(disk.ctx.eff)
    refuses("adapter.policy", lambda: policy.agent("lander"))


def test_a_malformed_result_is_one_refusal_that_names_the_field() -> None:
    """The wire is validated where it arrives, and the refusal tells the caller which field (C-12) rather than
    letting a `ValidationError` out into a caller that cannot read it."""
    r = refuses("adapter.result", lambda: adapter_mod.result({**_harness_result(), "tokens": -1}))
    assert "tokens" in r.detail


# ---------------------------------------------------------------------------- the policy, rendered (7bdb.4(2))


def test_the_rendered_policy_is_the_allowlist_and_the_guard_hook(disk: Disk) -> None:
    policy = adapter_mod.ExecutorPolicy.from_effective(disk.ctx.eff)
    s = render.settings(policy)
    assert s["permissions"]["allow"] == list(policy.allowlist)
    assert s["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == render.GUARD_COMMAND
    assert "Write" in s["hooks"]["PreToolUse"][0]["matcher"]


def test_a_post_hoc_guard_renders_no_hook_and_says_so(disk: Disk) -> None:
    """05 §3's declared degradation: an adapter whose runtime cannot host the hook renders none, and the capability
    row is what announces it. Silence is the thing this forbids."""
    policy = adapter_mod.ExecutorPolicy.from_effective(disk.ctx.eff)
    degraded = policy.model_copy(update={"guard": "post-hoc"})
    assert "hooks" not in render.settings(degraded)


# ------------------------------------------------------------------------------ the write guard, at write time


def test_the_guard_denies_a_write_outside_the_surfaces_and_the_file_is_unchanged(
    disk: Disk, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T-B5 (1). The positive discriminator is both halves: the write did not happen *and* the denial was counted.
    A guard that only counted, or only refused without a record, would pass one of them."""
    job = a_job(disk)
    spec, blocks = tmp_path / "allow.json", tmp_path / "blocks.jsonl"
    spec.write_text(json.dumps(render.allow_spec(job)), encoding="utf-8")
    monkeypatch.setenv(guard.ALLOW_ENV, str(spec))
    monkeypatch.setenv(guard.BLOCKS_ENV, str(blocks))
    target = tmp_path / "card.md"
    target.write_text("before", encoding="utf-8")

    assert hook(OUTSIDE) == guard.BLOCK_EXIT
    assert target.read_text(encoding="utf-8") == "before"
    assert len(blocks.read_text(encoding="utf-8").splitlines()) == 1
    assert json.loads(blocks.read_text(encoding="utf-8"))["path"].endswith(OUTSIDE)


def test_the_guard_allows_a_declared_path_and_counts_nothing(
    disk: Disk, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec, blocks = tmp_path / "allow.json", tmp_path / "blocks.jsonl"
    spec.write_text(json.dumps(render.allow_spec(a_job(disk))), encoding="utf-8")
    blocks.write_text("", encoding="utf-8")
    monkeypatch.setenv(guard.ALLOW_ENV, str(spec))
    monkeypatch.setenv(guard.BLOCKS_ENV, str(blocks))
    assert hook(INSIDE) == 0
    assert hook("tests/factory/test_new.py") == 0, "the test paths ride with the surfaces (T-B5 (1))"
    assert hook("anything.md", tool="Read") == 0, "a tool that does not write is not the guard's business"
    assert blocks.read_text(encoding="utf-8") == ""


def test_an_unconfigured_guard_refuses_every_write(monkeypatch: pytest.MonkeyPatch) -> None:
    """A partial mechanism misses toward caution: a guard that cannot read its own set denies, it does not pass."""
    monkeypatch.delenv(guard.ALLOW_ENV, raising=False)
    assert hook(INSIDE) == guard.BLOCK_EXIT


def test_the_rule_is_the_declared_path_not_a_prefix() -> None:
    """`surfaces = ["src/a.py"]` must not admit `src/a.py.bak`, and `["tests/"]` must not admit `tests-scratch/`.
    A bare prefix match is the bug this discriminates."""
    allow = ("src/a.py", "tests/")
    assert guard.allows("src/a.py", allow) and guard.allows("tests/x/y.py", allow)
    assert not guard.allows("src/a.py.bak", allow)
    assert not guard.allows("tests-scratch/x.py", allow)
    assert not guard.allows("/work/../etc/passwd", allow, "/work")
    assert not guard.allows("/etc/passwd", allow, "/work")
    assert guard.allows("/work/src/a.py", allow, "/work")


# ---------------------------------------------------------------------------------- the recompute, and the row


def test_the_touched_set_comes_from_git_including_untracked(disk: Disk, tmp_path: Path) -> None:
    """The belt behind the guard: the set is git's, never the report's. Untracked files count — a phase that adds a
    file has touched it — and so does the source half of a rename."""
    tree = tmp_path / "wt"
    git(disk.work, "branch", "probe", "main")
    checkout_mod.worktree(disk.work, "probe", tree)
    try:
        assert checkout_mod.touched(tree) == ()
        (tree / "new.txt").write_text("x", encoding="utf-8")
        (tree / "README.md").write_text("changed", encoding="utf-8")
        assert set(checkout_mod.touched(tree)) == {"new.txt", "README.md"}
    finally:
        checkout_mod.worktree_remove(disk.work, tree)


def test_a_result_that_claims_a_different_change_set_is_refused(disk: Disk) -> None:
    """*"The ledger recomputes the run's touched set from git and refuses a report whose claimed set differs"* —
    before `surfaces` is judged, so a false claim cannot be laundered into a scope verdict."""
    res = adapter_mod.result({**_harness_result(), "touched": ("a.py",)})
    r = refuses("run.change-set", lambda: runner_mod._believe_nothing(res, ["b.py"]))
    assert "a.py" in r.detail and "b.py" in r.detail
    runner_mod._believe_nothing(adapter_mod.result(_harness_result()), ["b.py"])  # claims nothing: not a lie


def test_the_phase_row_is_03_6s_and_its_event_carries_the_rest(disk: Disk, led: Ledger) -> None:
    """Card 5's S4, sharpened: a `phases` row exists for the run, it is 03 §6's entry exactly, and what has no
    column there (the artifacts, the denials, the touched set, the harness) rides the ledger's own event."""
    res = adapter_mod.result({**_harness_result(), "run_id": disk.run_id, "guard_blocks": 2})
    led.phase(disk.run_id, "2026-09-12T00:00:00Z", {**res.row(), "touched": ["client/cards/validator.py"]})
    rows = led.phases_of(disk.run_id)
    assert rows and rows[-1]["phase"] == "build" and rows[-1]["agent"] == "builder"
    assert set(rows[-1]) == {
        "phase",
        "agent",
        "model",
        "effort",
        "prompt_version",
        "tokens",
        "cost_micro",
        "duration_ms",
    }
    ev = [e for e in led.events_of(disk.run_id) if e["kind"] == "phase"][-1]
    assert ev["data"]["guard_blocks"] == 2 and ev["data"]["touched"] == ["client/cards/validator.py"]
    assert all(e["kind"] != "phase" for e in led.report(disk.run_id).model_dump()["events"])


def test_the_phase_row_and_its_event_are_one_transaction(
    disk: Disk, led: Ledger, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R2: *"the same transaction discipline dispatch used"*. The discriminator is a failure **between** the two
    writes — if the event cannot be written, the row must not be there either, or the ledger would hold a phase
    that no transition ever recorded."""
    run_id = fresh_run(disk, led)
    before = len(led.phases_of(run_id))

    def boom(*_a: Any, **_k: Any) -> None:
        raise RuntimeError("the event write failed")

    monkeypatch.setattr(Ledger, "_event", boom)
    with pytest.raises(RuntimeError):
        led.phase(run_id, "2026-09-12T00:00:00Z", {**_harness_result(), "run_id": run_id})
    monkeypatch.undo()
    assert len(led.phases_of(run_id)) == before, "the row survived a failed event: the two are not one transaction"


def test_an_unknown_run_is_refused_before_anything_is_written(disk: Disk, led: Ledger) -> None:
    refuses("ledger.unknown-run", lambda: led.phase("r-99", "2026-09-12T00:00:00Z", _harness_result()))
    refuses("ledger.unknown-run", lambda: led.finish("r-99", "2026-09-12T00:00:00Z", "failed:infra"))


# ------------------------------------------------------------------------------------- the container adapter


def test_the_token_reaches_the_child_by_name_and_is_in_no_argv(disk: Disk) -> None:
    """V2's discriminator, on this credential: a process list must not be able to read the subscription token."""
    pod = Podman()
    Container(disk.home, _reg(disk), run=pod).execute(a_job(disk))
    flat = " ".join(" ".join(a) for a in pod.seen)
    assert TOKEN not in flat
    assert "--env CLAUDE_CODE_OAUTH_TOKEN" in flat.replace("  ", " ")
    assert pod.env[0]["CLAUDE_CODE_OAUTH_TOKEN"] == TOKEN


def test_the_matrix_names_the_image_it_runs_not_this_process(disk: Disk) -> None:
    """Found live 2026-09-12: the matrix read `ISIDIUM_HARNESS_VERSION` from the **factory's** environment, where
    the harness is not — so it said `unknown` beside a run that knew exactly which harness it ran. The version is a
    fact about the image; the declaration names the image, and the concrete version comes back on the result from
    inside it."""
    caps = Container(disk.home, _reg(disk), run=Podman()).capabilities()
    assert caps.harness_version == IMAGE
    assert caps.harness_version not in ("", "unknown")
    res = Container(disk.home, _reg(disk), run=Podman()).execute(a_job(disk))
    assert res.harness_version == "1.2.3", "the version on the record is the image's own answer, not the matrix's"


def test_one_spawn_per_phase(disk: Disk) -> None:
    """Not one per tool call: the container starts once, does the phase and exits."""
    pod = Podman()
    Container(disk.home, _reg(disk), run=pod).execute(a_job(disk))
    assert len([a for a in pod.seen if a[1] == "run"]) == 1


def test_the_adapter_takes_the_signed_model_and_counts_the_guards_denials(disk: Disk) -> None:
    """What the tenant signed is what the record says was asked for; the denials are counted from the guard's own
    log by this side of the mount, because a phase could report none."""
    pod = Podman(blocks=3)
    res = Container(disk.home, _reg(disk), run=pod).execute(a_job(disk))
    policy = adapter_mod.ExecutorPolicy.from_effective(disk.ctx.eff)
    assert res.model == policy.agent("builder").model and res.effort == "xhigh"
    assert res.guard_blocks == 3 and res.tokens == 1234 and res.billing_class == "plan"
    assert res.run_id == disk.run_id


def test_a_start_failure_is_retried_once_and_then_failed_infra(disk: Disk) -> None:
    """T-C6: *"Adapter start/timeouts ⇒ `failed:infra`, one retry"* — one, and the second is the last."""
    pod = Podman(fail="no such image", once=True)
    Container(disk.home, _reg(disk), run=pod).execute(a_job(disk))
    assert len([a for a in pod.seen if a[1] == "run"]) == 2

    hard = Podman(fail="no such image")
    r = refuses("adapter.infra", lambda: Container(disk.home, _reg(disk), run=hard).execute(a_job(disk)))
    # The number is written here, not read from the module: a test that asks the code how many attempts it makes
    # agrees with any answer. T-C6 says **one retry**, so two attempts is the property.
    assert len([a for a in hard.seen if a[1] == "run"]) == 2
    assert "no such image" in r.detail


def test_the_watchdog_kills_the_container_and_ends_failed_infra(disk: Disk) -> None:
    pod = Podman(timeout=True)
    refuses("adapter.infra", lambda: Container(disk.home, _reg(disk), run=pod).execute(a_job(disk)))
    kills = [a for a in pod.seen if a[1] == "kill"]
    assert kills and kills[0][-1].startswith("isidium-") and "TERM" in kills[0]


def test_a_rate_limit_is_environment_and_is_not_retried(disk: Disk) -> None:
    """The adapter-auth note: *"a rate-limit hit is not `infra` to retry once"* — the windows are shared with the
    owner's own sessions, and burning the retry on a limit spends the same window twice."""
    pod = Podman(fail="429 rate limit exceeded")
    refuses("adapter.environment", lambda: Container(disk.home, _reg(disk), run=pod).execute(a_job(disk)))
    assert len([a for a in pod.seen if a[1] == "run"]) == 1


def test_a_rejected_credential_is_environment_and_is_not_retried(disk: Disk) -> None:
    """Found live 2026-09-12: the provider answered `401 Invalid bearer token`, and the adapter tried again with the
    same token and then called it `failed:infra`. A second attempt with a rejected credential is the same answer,
    and `infra` names the wrong thing to fix — the token at the deploy home is what a human has to replace."""
    pod = Podman(
        harness={
            "is_error": True,
            "result": "Failed to authenticate. API Error: 401 Invalid bearer token",
            "api_error_status": 401,
        }
    )
    r = refuses("adapter.environment", lambda: Container(disk.home, _reg(disk), run=pod).execute(a_job(disk)))
    assert len([a for a in pod.seen if a[1] == "run"]) == 1, "a rejected credential is not retried"
    assert "401" in r.detail


def test_the_refusal_carries_what_the_container_left_behind(disk: Disk) -> None:
    """The other half of the same finding: the harness writes its errors **inside** the container, so podman relays
    an empty stream. An adapter that mounts a directory and then does not read it when the run fails tells the
    operator less than it knows — `exit 1` where a sentence was available."""
    pod = Podman(harness={"is_error": True, "result": "the model could not reach the tree"})
    r = refuses("adapter.infra", lambda: Container(disk.home, _reg(disk), run=pod).execute(a_job(disk)))
    assert "the model could not reach the tree" in r.detail
    assert r.detail != "2 attempts, the last: exit 1"


def test_a_tenant_with_no_image_is_refused_rather_than_given_one(disk: Disk) -> None:
    reg = Registration(None, 1, "container", 1000, None)
    pod = Podman()
    refuses("adapter.no-image", lambda: Container(disk.home, reg, run=pod).execute(a_job(disk)))
    assert pod.seen == []


def test_a_tenant_with_no_credential_is_refused(disk: Disk, tmp_path: Path) -> None:
    refuses("adapter.no-token", lambda: Container(tmp_path, _reg(disk), run=Podman()).execute(a_job(disk)))


# ------------------------------------------------------------------------------------------ the wrapper, end to end


def fresh_run(disk: Disk, led: Ledger) -> str:
    """A second dispatched run for this card, written the way `dispatch` writes one — so each wrapper test has its
    own row and none of them depends on the order the others ran in. The picker itself is V3's and is exercised
    there; what is under test here is what happens to a row after it exists."""
    was = led.run(disk.run_id)
    assert was is not None
    run_id = led.dispatch(
        NewRun(
            card=disk.card,
            lane="standard",
            build_hash=str(was["build_hash"]),
            base_sha=str(was["base_sha"]),
            adapter="container",
            dispatched_at="2026-09-12T00:00:00Z",
            payload_hash=str(was["payload_hash"]),
            config_hash=str(was["config_hash"]),
            identity=str(was["identity"]),
        )
    )
    git(disk.work, "branch", f"story/{run_id}", str(was["base_sha"]))
    return run_id


def test_a_phase_lands_on_the_row_it_was_dispatched_under(disk: Disk, led: Ledger) -> None:
    """Card 5's S2, the happy half: the phase is recorded against the dispatched run, the worktree is taken down
    again, and the run stays in flight — V5's close is what ends a run, not a phase."""
    fake = Fake()
    run_id = fresh_run(disk, led)
    row = runner_mod.run_phase(
        disk.ctx, _reg(disk), led, disk.call, run_id=run_id, phase="build", factory=lambda h, r: fake
    )
    assert row["run_id"] == run_id and row["ended_at"] is None
    assert row["phases"] and row["phases"][-1]["agent"] == "builder"
    assert fake.seen and fake.seen[0].allowed_writes[0] == INSIDE
    assert not (disk.home / "worktrees" / run_id).exists(), "the worktree per run is taken down again"


def test_the_outcome_lands_on_the_dispatched_row(disk: Disk, led: Ledger) -> None:
    """Card 5's S2, the half that matters: *"what happened after the row is on the row"*.

    **The name is the card's, and it was not at first.** Card 5 named this test
    `test_the_outcome_lands_on_the_dispatched_row`; V4a-i built the property under another name, so the card's
    acceptance block answered `not found` for S2 and could never pass (found 2026-09-12, running `accept 5`). The
    card is the specification, so the test took its name — not the other way round. Card 5 was withdrawn the same
    day for its other defects; the name stays, because a scenario pointing at a test is a contract with the test."""
    broken = Fake(result=_harness_result(outcome="failed:infra"))
    run_id = fresh_run(disk, led)
    row = runner_mod.run_phase(
        disk.ctx, _reg(disk), led, disk.call, run_id=run_id, phase="build", factory=lambda h, r: broken
    )
    assert row["outcome"] == "failed:infra" and row["ended_at"]
    refuses(
        "run.ended",
        lambda: runner_mod.run_phase(
            disk.ctx, _reg(disk), led, disk.call, run_id=run_id, phase="build", factory=lambda h, r: Fake()
        ),
    )


def test_a_write_outside_the_surfaces_ends_the_run_failed_scope(disk: Disk, led: Ledger) -> None:
    """The belt behind the guard, at the wrapper: a phase whose worktree holds a path the card does not declare is
    `failed:scope` on its own row, and the work is not committed as though it were in scope. The guard denies at
    write time; this is what catches a phase that got past it — an adapter whose runtime could not host the hook,
    or one that wrote through a path the hook does not see."""
    run_id = fresh_run(disk, led)
    rogue = Fake(writes=("notes-from-the-builder.md",))
    r = refuses(
        "run.scope",
        lambda: runner_mod.run_phase(
            disk.ctx, _reg(disk), led, disk.call, run_id=run_id, phase="build", factory=lambda h, x: rogue
        ),
    )
    assert "notes-from-the-builder.md" in r.detail
    row = led.run(run_id)
    assert row is not None and row["outcome"] == "failed:scope" and row["ended_at"]
    assert row["surfaces_actual"] == ["notes-from-the-builder.md"]
    assert led.phases_of(run_id), "the phase is on the record even when it is the phase that failed"
    ev = [e for e in led.events_of(run_id) if e["kind"] == "phase"][-1]
    assert ev["data"]["outcome"] == "failed:scope"


def test_a_phase_that_is_not_an_adapters_is_refused(disk: Disk, led: Ledger) -> None:
    refuses(
        "run.phase",
        lambda: runner_mod.run_phase(
            disk.ctx,
            _reg(disk),
            led,
            disk.call,
            run_id=fresh_run(disk, led),
            phase="close",
            factory=lambda h, r: Fake(),
        ),
    )


def test_the_run_verb_is_the_call_and_a_refusal_is_exit_2(disk: Disk) -> None:
    """Card 5's S3: the adapter is reachable as a verb and says what it does.

    The help is rendered by rich, which wraps to the terminal's width and paints the option names — so the first
    draft of this assertion passed on a wide workstation terminal and failed on CI's 80 columns, the same class as
    V3's timing finding. The environment is pinned and the escapes are stripped, so what is asserted is the text
    the verb prints and not the shape of the terminal it printed into."""
    env = {"COLUMNS": "200", "NO_COLOR": "1", "TERM": "dumb"}
    out = CliRunner().invoke(cli_mod.app, ["run", "--help"], env=env)
    plain = _ANSI.sub("", out.stdout)
    assert out.exit_code == 0 and "--run" in plain, plain
    bad = CliRunner().invoke(cli_mod.app, ["run", "--tenant", TENANT, "--checkout", str(disk.work), "--run", "r-99"])
    assert bad.exit_code == 2


# --------------------------------------------------------------------------------------- the conformance suite


def test_the_conformance_scenario_is_green_on_both_adapters(
    disk: Disk, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T-C6's gate. Two adapters run the same scenario — that is what makes it a suite rather than one test, and it
    is the file V4b's action adapter runs unchanged."""
    job = a_job(disk)
    for name, adapter in (("fake", Fake()), ("container", Container(disk.home, _reg(disk), run=Podman()))):
        bad = conformance.run(adapter, job, monkeypatch, tmp_path / name)
        assert bad == [], f"{name}: " + "; ".join(bad)


def test_an_adapter_that_declares_more_than_it_has_fails_conformance(
    disk: Disk, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The suite is only worth running if it can fail: an adapter claiming a write-time guard under a policy that
    renders none is caught, which is what *"declared degradation, never silent"* means mechanically."""
    job = a_job(
        disk, policy=adapter_mod.ExecutorPolicy.from_effective(disk.ctx.eff).model_copy(update={"guard": "post-hoc"})
    )
    bad = conformance.run(Fake(), job, monkeypatch, tmp_path)
    assert any("write_guard_at_write_time" in b for b in bad), bad


# ------------------------------------------------------------------------------------------------------ helpers


def _reg(disk: Disk) -> Registration:
    reg = disk.ctx.registration
    assert reg is not None
    return reg
