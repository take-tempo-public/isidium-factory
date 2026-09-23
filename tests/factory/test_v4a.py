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
import signal
import sqlite3
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
from isidium.factory import guard, harness, render
from isidium.factory import ledger as ledger_mod
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
PROMPTS = Path(__file__).resolve().parents[2] / "prompts"
# What `deploy/build-runner.sh` labels an image with: the repository's own prompt set, `<agent>/<version>`.
CARRIED = frozenset(p.relative_to(PROMPTS).with_suffix("").as_posix() for p in PROMPTS.glob("*/v*.md"))
# config@7's `[agents]` rows as a tenant declares them [owner, 2026-09-22]: `tools` on every row, nothing else — the
# model, the effort and the prompt come from the adopted schema's defaults. The builder writes; the rest read.
READS = ["Read", "Glob", "Grep"]
TOOLS: dict[str, list[str]] = {
    "planner": READS,
    "plan-author": READS,
    "plan-refuter": READS,
    "judge": READS,
    "builder": ["Read", "Glob", "Grep", "Edit", "Write", "Bash", "TodoWrite"],
    "reviewer": READS,
}
INSIDE = "client/cards/validator.py"
OUTSIDE = "docs/work/cards/0001-anything.md"


# rich paints the help; the text is what this asserts, never the escapes around it.
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def declare_agents(st: Store, tools: dict[str, list[str]] | None = None) -> None:
    """One signed policy write that declares the tenant's `[agents]` rows — what tenant #0's `config-policy` act
    does live. A config@7 tenant with no declared row runs nothing: the defaults alone name no tools."""
    tree = {k: v for k, v in st.config_tree.items() if k != "history"}
    tree["agents"] = {k: {"tools": list(v)} for k, v in (TOOLS if tools is None else tools).items()}
    st.write("config.toml", tree, {"seq": st.policy[-1]["seq"], "h": st.policy[-1]["h"]}, None, OWNER)


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
    declare_agents(st)
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
    row = dispatch_mod.pick(
        ctx, led, lambda n, a: Api(st).call(n, LANDER, a), Branch(work), card=r.id, factory=lambda h, g: Fake()
    )
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
    left: dict[str, Any] | None = None  # a harness that ran, spent, and ended in failure: its result stays behind
    fail: str | None = None
    timeout: bool = False
    once: bool = False
    blocks: int = 0
    edits: dict[str, str] = field(default_factory=dict)  # what each attempt writes into the worktree before it ends
    found: list[bool] = field(default_factory=list)  # whether an attempt found the edits already there
    seen: list[list[str]] = field(default_factory=list)
    env: list[dict[str, str]] = field(default_factory=list)
    label: str = ",".join(sorted(CARRIED))  # the image's `org.isidium.prompts`; `<no value>` is podman's absent label

    def __call__(self, argv: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        self.seen.append(list(argv))
        self.env.append(dict(kw.get("env") or {}))
        if argv[1] in ("kill", "rm"):
            return subprocess.CompletedProcess(argv, 0, "", "")
        if argv[1:3] == ["image", "inspect"]:
            return subprocess.CompletedProcess(argv, 0, self.label + "\n", "")
        first = len([a for a in self.seen if a[1] == "run"]) == 1
        if self.edits:
            tree = Path(next(a for a in argv if a.endswith(f":{render.WORK}:rw")).rsplit(":", 2)[0])
            self.found.append(any((tree / rel).exists() for rel in self.edits))
            for rel, text in self.edits.items():
                (tree / rel).write_text(text, encoding="utf-8")
        if self.timeout and not (self.once and not first):
            raise subprocess.TimeoutExpired(argv, kw.get("timeout") or 0)
        if self.fail is not None and not (self.once and not first):
            return subprocess.CompletedProcess(argv, 1, "", self.fail)
        rundir = Path(next(a for a in argv if a.endswith(f":{render.RUN}:rw")).rsplit(":", 2)[0])
        if self.left is not None:
            (rundir / "result.json").write_text(json.dumps(self.left), encoding="utf-8")
            if self.harness is not None:
                (rundir / "harness.json").write_text(json.dumps(self.harness), encoding="utf-8")
            return subprocess.CompletedProcess(argv, 1, "", "")
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
        "model": "claude-opus-5",  # the image's measured answer; config@6's builder row, unless a test says otherwise
        "effort": "xhigh",
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
    ran: str | None = None  # a model other than the one the policy named — what the conformance check must catch
    seen: list[RunJob] = field(default_factory=list)
    carried: frozenset[str] = CARRIED

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

    def prompts(self) -> frozenset[str]:
        return self.carried

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
                "model": self.ran or spec.model,
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
    # `prompts` since config@7 [owner, 2026-09-23]: the executor's own answer to which prompts it carries, read before
    # any spend. It names no executor — `<agent>/<version>` is the factory's vocabulary — and it neither commits,
    # pushes nor lands, which is what this set exists to keep off the seam.
    assert names == {"capabilities", "prompts", "execute"}, names


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


def test_a_config6_tenant_is_refused_by_name_and_a_row_the_defaults_alone_supply_is_not_declared(disk: Disk) -> None:
    """[owner, 2026-09-22] config@7 or nothing: a config@6 policy has an `[executor]` and `[agents]` but signs no tools
    and no prompt, and running it would need a second copy of both in code — so it is refused, naming config@7.

    And under config@7 a row the tenant did not declare is not a row: `tools` has no default, so a kind present
    only through the schema's defaults names no tools, and asking for it fails closed like a kind with no row."""
    six = {**disk.ctx.eff, "schema": 6}
    r = refuses("adapter.policy", lambda: adapter_mod.ExecutorPolicy.from_effective(six))
    assert "config@6" in r.detail and "config@7" in r.detail
    agents = {k: v for k, v in disk.ctx.eff["agents"].items() if k != "judge"}
    undeclared = {**disk.ctx.eff, "agents": {**agents, "judge": {"model": "claude-opus-5", "effort": "high"}}}
    policy = adapter_mod.ExecutorPolicy.from_effective(undeclared)
    assert policy.agent("builder").tools and "judge" not in policy.agents
    refuses("adapter.policy", lambda: policy.agent("judge"))


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
    """config@7: the surface is the AGENT's signed `tools`, never the tenant ceiling — two agents in one test, or a
    render that ignored the agent and handed every phase the allowlist would pass."""
    policy = adapter_mod.ExecutorPolicy.from_effective(disk.ctx.eff)
    s = render.settings(policy, "builder")
    assert s["permissions"]["allow"] == TOOLS["builder"]
    assert render.settings(policy, "judge")["permissions"]["allow"] == READS != list(policy.allowlist)
    assert s["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == render.GUARD_COMMAND
    assert "Write" in s["hooks"]["PreToolUse"][0]["matcher"]


def test_a_post_hoc_guard_renders_no_hook_and_says_so(disk: Disk) -> None:
    """05 §3's declared degradation: an adapter whose runtime cannot host the hook renders none, and the capability
    row is what announces it. Silence is the thing this forbids."""
    policy = adapter_mod.ExecutorPolicy.from_effective(disk.ctx.eff)
    degraded = policy.model_copy(update={"guard": "post-hoc"})
    assert "hooks" not in render.settings(degraded, "builder")


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


def test_the_record_says_the_model_the_image_ran_and_counts_the_guards_denials(disk: Disk) -> None:
    """Q-V25: the model on the record is the image's measured answer, never the policy's written over it — the
    discriminator is an image that ran something other than the signed row, which is exactly what `r-2` and `r-3`
    did. The denials are counted from the guard's own log by this side of the mount, because a phase could report
    none."""
    policy = adapter_mod.ExecutorPolicy.from_effective(disk.ctx.eff)
    assert policy.agent("builder").model != "claude-sonnet-5", "the discriminator needs a row that is not the image's"
    pod = Podman(blocks=3, result=_harness_result(model="claude-sonnet-5"))
    res = Container(disk.home, _reg(disk), run=pod).execute(a_job(disk))
    assert res.model == "claude-sonnet-5" and res.effort == "xhigh"
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
    # Q-V25: the name is freed before the retry, or the second `run --name` meets the first container still stopping.
    verbs = [a[1] for a in pod.seen]
    assert verbs == ["run", "kill", "rm", "run", "kill", "rm"], verbs
    assert all(a[-1] == kills[0][-1] for a in pod.seen if a[1] == "rm")


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


def test_a_turn_limit_is_budget_and_is_not_retried(disk: Disk) -> None:
    """Found live on `r-4` (2026-09-14): the builder spent its forty turns, the harness said `error_max_turns`, and the
    adapter called it `failed:infra` and spent the turns a second time. T-A7: *"`infra` ⇒ one retry; …
    `budget`/`timeout` ⇒ design queue with the telemetry attached"* — so the phase's result goes back, once."""
    pod = Podman(left=_harness_result(outcome="failed:budget", tokens=26809))
    res = Container(disk.home, _reg(disk), run=pod).execute(a_job(disk, run_id="r-budget"))
    assert len([a for a in pod.seen if a[1] == "run"]) == 1, "a turn limit was retried"
    assert res.outcome == "failed:budget" and res.tokens == 26809


def test_a_retried_phase_keeps_each_attempt_and_the_refusal_carries_the_whole_spend(disk: Disk) -> None:
    """The other half of `r-4`: attempt 1 ran twelve minutes, attempt 2 overwrote its files, and the refusal carried
    nothing — the ledger's `phases` held no row for seventeen minutes of spend. Each attempt is kept under its number,
    the refusal carries both attempts' spend, and the harness's own `errors[]` is part of what the operator is told."""
    pod = Podman(
        left=_harness_result(outcome="failed:infra", tokens=100, cost_micro=7, duration_ms=5),
        harness={"is_error": True, "errors": ["the tree was unreachable"]},
    )
    r = refuses(
        "adapter.infra", lambda: Container(disk.home, _reg(disk), run=pod).execute(a_job(disk, run_id="r-twice"))
    )
    assert len([a for a in pod.seen if a[1] == "run"]) == 2
    assert isinstance(r, adapter_mod.PhaseRefusal) and r.result is not None
    assert (r.result.tokens, r.result.cost_micro, r.result.duration_ms) == (200, 14, 10)
    rundir = disk.home / "runs" / "r-twice" / "build"
    assert (rundir / "attempt-1.result.json").exists() and (rundir / "attempt-1.harness.json").exists()
    assert "the tree was unreachable" in r.detail


def test_a_retry_sets_the_first_attempts_work_aside_and_starts_clean(disk: Disk, tmp_path: Path) -> None:
    """Found live on `r-5` (2026-09-15): attempt 2 started on attempt 1's half-done edits and its core file. The first
    attempt's work is kept as a patch beside the run — untracked files included — and the second starts on the tree
    the phase started on."""
    tree = tmp_path / "tree"
    tree.mkdir()
    git(tree, "init", "-q")
    git(tree, "config", "user.email", "t@example")
    git(tree, "config", "user.name", "t")
    (tree / "kept.py").write_text("k = 1\n", encoding="utf-8")
    git(tree, "add", "-A")
    git(tree, "commit", "-q", "-m", "base")
    pod = Podman(fail="the harness crashed", edits={"half-done.py": "x = 1\n"})
    refuses(
        "adapter.infra",
        lambda: Container(disk.home, _reg(disk), run=pod).execute(a_job(disk, run_id="r-aside", worktree=str(tree))),
    )
    assert pod.found == [False, False], "the second attempt found the first attempt's edits in the tree"
    patch = (disk.home / "runs" / "r-aside" / "build" / "attempt-1.patch").read_text(encoding="utf-8")
    assert "half-done.py" in patch and "x = 1" in patch
    assert (tree / "kept.py").exists(), "the set-aside took the phase's own base with it"


def test_a_crashed_harness_is_told_by_how_it_ended_and_its_streamed_spend_is_kept(disk: Disk, tmp_path: Path) -> None:
    """`r-5`'s harness crashed twice and `--output-format json` had written nothing: no model, no tokens, and *"said
    nothing"*. From a stream, a crash still proves what finished — each message's usage once (a message is streamed
    once per content block, with the same usage on each line) — and the process's own end is named, and a core dump
    in the worktree is moved beside the run."""
    msg = {"id": "msg_1", "model": "claude-sonnet-5", "usage": {"input_tokens": 9, "output_tokens": 700}}
    other = {"id": "msg_2", "model": "claude-sonnet-5", "usage": {"input_tokens": 3, "output_tokens": 300}}
    lines = [
        json.dumps({"type": "system", "subtype": "init"}),
        json.dumps({"type": "assistant", "message": msg}),
        json.dumps({"type": "assistant", "message": msg}),  # the same message's second content block
        json.dumps({"type": "assistant", "message": other}),
        "{truncated by the crash",
    ]
    work, rundir = tmp_path / "work", tmp_path / "run"
    work.mkdir()
    rundir.mkdir()
    (work / "core.2").write_bytes(b"\x7fELF")
    (work / "core").write_text("a repository file called core", encoding="utf-8")
    cores = harness.keep_cores(work, rundir)
    assert cores == ["core.2"] and (rundir / "core.2").exists() and not (work / "core.2").exists()
    assert (work / "core").exists(), "a file merely called core is the repository's"
    out = harness.stream_out(lines, -11, cores)
    assert out["usage"]["output_tokens"] == 1000 and out["usage"]["input_tokens"] == 12
    assert "signal 11" in harness.reason_of(out) and "core.2" in harness.reason_of(out)
    got = harness.report(a_job(disk), out, False, "2.1.269")
    assert got["model"] == "claude-sonnet-5" and got["tokens"] == 1012 and got["outcome"] == "failed:infra"
    assert "status 3" in harness.reason_of(harness.stream_out([], 3))


def test_a_finished_stream_answers_with_its_result_line() -> None:
    """A stream that reached its end answers exactly as `--output-format json` did: the result line, whole."""
    result = {"type": "result", "subtype": "error_max_turns", "is_error": True, "usage": {"output_tokens": 5}}
    lines = [
        json.dumps({"type": "assistant", "message": {"id": "m", "usage": {"output_tokens": 5}}}),
        json.dumps(result),
    ]
    out = harness.stream_out(lines, 1)
    assert {k: out[k] for k in result} == result and out["exit_status"] == 1
    assert harness.outcome_of(out, False) == "failed:budget"


def test_the_harness_calls_a_turn_limit_budget_and_says_why(disk: Disk) -> None:
    """`r-4`'s own harness output, in shape: `error_max_turns` is `failed:budget` whatever the exit code, any other
    error stays `failed:infra`, and the sentence in `errors[]` is what the runner says — not *"said nothing"*."""
    out = {
        "is_error": True,
        "subtype": "error_max_turns",
        "terminal_reason": "max_turns",
        "errors": ["Reached maximum number of turns (40)"],
        "modelUsage": {"claude-sonnet-5": {"outputTokens": 26729}},
    }
    assert harness.report(a_job(disk), out, False, "2.1.269")["outcome"] == "failed:budget"
    other = {"is_error": True, "subtype": "error_during_execution"}
    assert harness.report(a_job(disk), other, False, "2.1.269")["outcome"] == "failed:infra"
    assert harness.reason_of(out) == "Reached maximum number of turns (40)"
    assert harness.reason_of({}) == "the harness failed and said nothing"


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


def test_the_prompt_version_is_the_agents_signed_row(disk: Disk, led: Ledger) -> None:
    """7bd.11's `prompts/<agent>/<version>.md`, selected per agent kind from its signed `[agents].<kind>.prompt`
    (config@7, [owner, 2026-09-22]) — the builder's `v3` and the reviewer's `v1`, config@7's defaults, which mirror the
    code map they replaced so the bump changed no run.

    **Two phases in one test is the discriminator.** Asserting the builder alone would pass on a selector that
    ignored the agent it was handed and answered `v3` to everything — which is exactly the shape the one shared
    constant had, one version for every agent kind."""
    fake = Fake()
    build = fresh_run(disk, led)
    runner_mod.run_phase(disk.ctx, _reg(disk), led, disk.call, run_id=build, phase="build", factory=lambda h, r: fake)
    review = fresh_run(disk, led)
    runner_mod.run_phase(disk.ctx, _reg(disk), led, disk.call, run_id=review, phase="review", factory=lambda h, r: fake)
    assert {j.identity.agent: j.prompt_version for j in fake.seen} == {"builder": "v3", "reviewer": "v1"}
    assert not hasattr(runner_mod, "PROMPT_VERSIONS"), "one home: the signed row, never a map beside it"


def test_every_default_prompt_is_one_the_repository_carries_and_the_build_labels_it() -> None:
    """The ground a signed version stands on [owner, 2026-09-23]. config@7's defaults name a prompt per agent kind; an
    image carries what `prompts/` held when `deploy/build-runner.sh` built it, and says so in its label. So two
    things are checked here, where a pull request sees them: **every default the schema names is a file in the
    repository**, and **the label the script would write is exactly the repository's set** — a script that dropped a
    directory, or labelled a version the build did not copy, fails here rather than at a dispatch."""
    from isidium.store.registry.loader import Registry

    reg = Registry.shipped()
    defaults = reg.defaults_of(f"config@{reg.newest('config')}")["agents"]
    asked = {f"{k}/{row['prompt']}" for k, row in defaults.items()}
    assert {a.split("/")[0] for a in asked} >= set(runner_mod.AGENT_OF.values()), "every phase's agent has a row"
    assert asked <= CARRIED, f"the image would not carry {sorted(asked - CARRIED)}"
    script = Path(__file__).resolve().parents[2] / "deploy" / "build-runner.sh"
    out = subprocess.run(["sh", str(script), "--label"], capture_output=True, text=True, check=True).stdout.strip()
    assert frozenset(out.split(",")) == CARRIED and out == ",".join(sorted(CARRIED)), out
    kept = [(PROMPTS / "builder" / f"{v}.md").read_bytes() for v in ("v1", "v2", "v3")]
    assert len({*kept}) == len(kept), "a new version is a new file, never an edit (7bd.11)"
    every = [p.read_bytes() for p in sorted(PROMPTS.rglob("*.md"))]
    assert not any(b"\r" in b for b in every), "the prompts are LF: they are read in a Linux container"


def test_a_prompt_the_executor_lacks_is_refused_before_anything_is_spent(
    disk: Disk, led: Ledger, tmp_path: Path
) -> None:
    """The check that makes a signed version safe [owner, 2026-09-23]: every miss named in one refusal, at the pick
    (no row written, so the run never starts) and again at a phase (before the worktree, the adapter never called)."""
    policy = adapter_mod.ExecutorPolicy.from_effective(disk.ctx.eff)
    short = frozenset(CARRIED - {"judge/v1", "builder/v3"})
    r = refuses("adapter.prompt-missing", lambda: adapter_mod.require_prompts(policy, short, "here"))
    assert "builder/v3" in r.detail and "judge/v1" in r.detail, "every miss at once, not the first"
    adapter_mod.require_prompts(policy, CARRIED, "here")

    lacking = Fake(carried=short)
    # A card of its own, ratified and landed, and a context loaded after it — the fixture's card is already in flight,
    # and the pick's cheaper refusals (the ready-view, the payload) must all pass for this one to be what refuses.
    r = disk.store.write(
        NewCard("prompt-check"), Document(base_head(0, "draft"), {"Scope": BASE_SCOPE}), None, None, PLANNER
    )
    assert r.id is not None
    disk.store.ratify([r.id], OWNER)
    disk.store.land(EMPTY, LANDER)
    ctx = context_mod.load(TENANT, disk.work, base="main", root=ROOT)
    with Ledger.open(tmp_path, TENANT) as empty:  # nothing in flight, so the WIP cap is not what refuses
        refuses(
            "adapter.prompt-missing",
            lambda: dispatch_mod.pick(
                ctx, empty, disk.call, Branch(disk.work), card=r.id, factory=lambda h, g: lacking
            ),
        )
        assert empty.db.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0, "no row: the run never started"

    run_id = fresh_run(disk, led)
    refuses(
        "adapter.prompt-missing",
        lambda: runner_mod.run_phase(
            disk.ctx, _reg(disk), led, disk.call, run_id=run_id, phase="build", factory=lambda h, g: lacking
        ),
    )
    assert not lacking.seen and not (disk.home / "worktrees" / run_id).exists()


def test_the_container_reads_its_images_label_once_and_refuses_an_image_without_one(disk: Disk) -> None:
    """The label is image metadata — `podman image inspect`, no container started — read once per adapter; and an
    image built by hand, with no label, is refused rather than trusted to carry anything."""
    pod = Podman()
    drv = Container(disk.home, _reg(disk), run=pod)
    assert drv.prompts() == CARRIED == drv.prompts()
    inspects = [a for a in pod.seen if a[1:3] == ["image", "inspect"]]
    assert len(inspects) == 1 and inspects[0][-1] == IMAGE and not [a for a in pod.seen if a[1] == "run"]
    bare = Container(disk.home, _reg(disk), run=Podman(label="<no value>"))
    assert "build-runner.sh" in refuses("adapter.prompt-missing", bare.prompts).detail


def _failed_with_work(disk: Disk, led: Ledger) -> str:
    """A failed run that committed work to its story branch — the thing a carry carries [owner, 2026-09-15]."""
    run_id = fresh_run(disk, led)
    spent = Fake(result=_harness_result(outcome="failed:budget"), writes=(INSIDE,))
    Path(disk.work / INSIDE).parent.mkdir(parents=True, exist_ok=True)
    runner_mod.run_phase(disk.ctx, _reg(disk), led, disk.call, run_id=run_id, phase="build", factory=lambda h, r: spent)
    row = led.run(run_id)
    assert row is not None and row["outcome"] == "failed:budget" and row["head_sha"], "nothing to carry otherwise"
    return run_id


def _carrying_run(disk: Disk, led: Ledger, source: str) -> str:
    """A dispatched run that carries `source`, written the way `dispatch --carry-from` writes one."""
    was = led.run(disk.run_id)
    assert was is not None
    run_id = led.dispatch(
        NewRun(
            card=disk.card,
            lane="standard",
            build_hash=str(was["build_hash"]),
            base_sha=str(was["base_sha"]),
            adapter="container",
            dispatched_at="2026-09-20T00:00:00Z",
            payload_hash=str(was["payload_hash"]),
            config_hash=str(was["config_hash"]),
            identity=str(was["identity"]),
            carried_from=source,
        )
    )
    git(disk.work, "branch", f"story/{run_id}", str(was["base_sha"]))
    return run_id


def test_a_carried_run_replays_the_work_commits_it_apart_and_tells_the_agent(disk: Disk, led: Ledger) -> None:
    """Q-V31 (c) + Q-V33 (c), owner 2026-09-20: the failed run's diff is replayed onto a branch cut at the current
    base, committed on its own before the phase starts, and named to the agent on the JOB.

    **The load-bearing assertion is `surfaces_actual`.** Carried work left uncommitted would be indistinguishable
    from this run's own: `touched` is recomputed from `git status` in the worktree, so the inherited files would be
    judged against this card's surfaces and claimed as this run's change set. Its own commit is what makes the
    record say who did what — so a phase that itself writes nothing must come back with nothing claimed, even
    though its tree was full when it started.

    **And the block is on the job, not in the payload** — the second half of the ruling, asserted here because the
    payload's hash is what proves the substrate did not move, and it must not start depending on the ledger."""
    source = _failed_with_work(disk, led)
    src = led.run(source)
    assert src is not None
    run_id = _carrying_run(disk, led, source)

    seen_tree: list[str] = []
    idle = Fake()
    original = Fake.execute

    def watch(self: Fake, job: RunJob) -> PhaseResult:
        seen_tree.append((Path(job.worktree) / INSIDE).read_text(encoding="utf-8"))
        return original(self, job)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(Fake, "execute", watch)
        row = runner_mod.run_phase(
            disk.ctx, _reg(disk), led, disk.call, run_id=run_id, phase="build", factory=lambda h, r: idle
        )

    assert seen_tree and "written past the guard" in seen_tree[0], "the carried work is there before the agent runs"
    job = idle.seen[0]
    assert job.carried is not None
    assert (job.carried.run_id, job.carried.outcome, job.carried.head_sha) == (source, "failed:budget", src["head_sha"])
    assert job.carried.files == (INSIDE,)
    assert "carried" not in job.payload, "the payload stays a pure function of the card at a commit (Q-V33 (c))"
    assert row["surfaces_actual"] is None, "a phase that wrote nothing claims nothing, carried tree or not"
    log = git(disk.work, "log", "--format=%s%x1f%b%x1e", f"{row['base_sha']}..story/{run_id}")
    carried_commits = [c for c in log.split("\x1e") if "Factory-Carried" in c]
    assert len(carried_commits) == 1 and source in carried_commits[0], "one commit, and it says whose work it was"


def test_carried_work_that_does_not_apply_leaves_the_tree_clean(disk: Disk, led: Ledger, tmp_path: Path) -> None:
    """The conflict half of Q-V31 (c), on `carry_over` itself: what git cannot resolve is a **clean** failure, not
    conflict markers left in the tree for the agent to commit as though they were work."""
    source = _failed_with_work(disk, led)
    src = led.run(source)
    assert src is not None
    git(disk.work, "branch", "conflicting", str(src["base_sha"]))
    tree = tmp_path / "conflicting"
    checkout_mod.worktree(disk.work, "conflicting", tree)
    (tree / INSIDE).write_text("a wholly different line here\n", encoding="utf-8")
    git(tree, "commit", "-am", "a conflicting edit to the same file")
    try:
        refuses("run.merge", lambda: checkout_mod.carry_over(tree, str(src["base_sha"]), str(src["head_sha"])))
        assert checkout_mod.touched(tree) == (), "the tree is reset, not left half-applied"
    finally:
        checkout_mod.worktree_remove(disk.work, tree)


def test_a_carry_that_refuses_ends_the_run_failed_merge(disk: Disk, led: Ledger) -> None:
    """The wiring: a refused carry ends the run with the catalog's own name for a conflict, rather than leaving it
    in flight. **A refusal that ends nothing holds the WIP cap for ever** — the defect V5a was built to close — and
    `failed:merge` rather than `failed:infra` is `r-4`'s lesson: a class that does not say what happened bought one
    retry for nothing."""
    assert runner_mod._outcome_of(Refusal("run.merge", "a..b", "no")) == "failed:merge"
    source = _failed_with_work(disk, led)
    run_id = _carrying_run(disk, led, source)

    def wont(*_a: Any, **_k: Any) -> tuple[str, ...]:
        raise Refusal("run.merge", "a..b", "the carried work does not apply here")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(checkout_mod, "carry_over", wont)
        refuses(
            "run.merge",
            lambda: runner_mod.run_phase(
                disk.ctx, _reg(disk), led, disk.call, run_id=run_id, phase="build", factory=lambda h, r: Fake()
            ),
        )
    row = led.run(run_id)
    assert row is not None and row["outcome"] == "failed:merge" and row["ended_at"], "the run ends, it does not hang"


def test_a_ledger_whose_version_and_table_disagree_migrates_anyway(tmp_path: Path) -> None:
    """The finding CI refused this change for, pinned. **A file's recorded version and its actual table can
    disagree**, and a migration that believes the number over the table adds a column that is already there and dies
    `duplicate column name`. Not hypothetical: V5a's own migration test builds its "schema 1" file out of the
    current DDL, so the moment schema 3 added a column, that file had it. Reading `table_info` and adding only what
    is missing costs one query and makes the migration idempotent, which it should be anyway."""
    path = tmp_path / "disagrees.sqlite"
    db = sqlite3.connect(str(path), isolation_level=None)
    db.execute(ledger_mod._DDL[0])
    db.execute(ledger_mod._DDL[1])  # the CURRENT table — every added column already present
    db.executemany("INSERT INTO meta VALUES (?, ?)", [("schema", "1"), ("tenant", TENANT), ("next_run", "1")])
    db.close()
    led = Ledger(path, TENANT)  # the assertion is that this does not raise
    try:
        assert led._meta("schema") == str(ledger_mod.SCHEMA), "the version is corrected to match the shape"
    finally:
        led.close()


def test_carry_from_refuses_the_runs_it_must_not_carry(disk: Disk, tmp_path: Path) -> None:
    """`--carry-from`'s four refusals, in the order `_pick` asks them — all ahead of the ready-view, so the operator
    is told which run is wrong before a pick is priced. Their own ledger and a stubbed store call, because what is
    under test is the validation and not the pick.

    **The last assertion is the point of Q-V32 (a):** a source that passes every carry check still meets the
    ordinary door. Nothing here lets a card be dispatched that is not ready."""
    led = Ledger(tmp_path / "carry.sqlite", TENANT)

    def a_run(outcome: str, head: str | None, card: int) -> str:
        rid = led.dispatch(
            NewRun(
                card=card,
                lane="standard",
                build_hash="sha256:b",
                base_sha="0" * 40,
                adapter="container",
                dispatched_at="2026-09-20T00:00:00Z",
                payload_hash="sha256:p",
                config_hash="sha256:c",
                identity=LOGIN,
            )
        )
        led.finish(rid, "2026-09-20T00:01:00Z", outcome, head_sha=head)
        return rid

    try:
        done = a_run("closed", "deadbeef", disk.card)
        empty = a_run("failed:budget", None, disk.card)
        elsewhere = a_run("failed:budget", "deadbeef", disk.card + 1)

        def dry(carry: str, card: int | None = None) -> Any:
            return dispatch_mod.pick(
                disk.ctx,
                led,
                lambda n, a: {"ready": []},
                Branch(disk.work),
                card=card,
                carry_from=carry,
                dry_run=True,
            )

        refuses("dispatch.carry-unknown", lambda: dry("r-404"))
        refuses("dispatch.carry-outcome", lambda: dry(done))
        refuses("dispatch.carry-empty", lambda: dry(empty))
        refuses("dispatch.carry-card", lambda: dry(elsewhere, card=disk.card))
        refuses("dispatch.not-ready", lambda: dry(elsewhere))
    finally:
        led.close()


def test_the_ledger_migrates_a_schema_2_file_to_3(disk: Disk, tmp_path: Path) -> None:
    """The migration reads a RANGE, not `== "1"`. It used to test equality against the only older version there
    was, which was true exactly once: tenant #0's ledger is schema 2 today, so the same shape would have left
    `carried_from` unadded and every read of it an `OperationalError` on the live tenant."""
    path = tmp_path / "old.sqlite"
    db = sqlite3.connect(str(path), isolation_level=None)
    db.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    db.execute(
        "CREATE TABLE runs (run_id TEXT PRIMARY KEY, card INTEGER NOT NULL, batch TEXT, outcome TEXT NOT NULL,"
        " lane TEXT NOT NULL, build_hash TEXT NOT NULL, base_sha TEXT NOT NULL, head_sha TEXT,"
        " story_branch TEXT NOT NULL, adapter TEXT NOT NULL, billing_class TEXT, dispatched_at TEXT NOT NULL,"
        " ended_at TEXT, payload_hash TEXT NOT NULL, config_hash TEXT NOT NULL, context TEXT NOT NULL,"
        " score TEXT NOT NULL, refs_resolved TEXT NOT NULL, surfaces_actual TEXT, price_table TEXT,"
        " identity TEXT NOT NULL, pr INTEGER, landed_through INTEGER)"
    )
    db.execute("INSERT INTO meta VALUES ('schema', '2')")
    db.execute("INSERT INTO meta VALUES ('tenant', ?)", (TENANT,))
    db.execute("INSERT INTO meta VALUES ('next_run', '1')")
    db.close()
    led = Ledger(path, TENANT)
    try:
        cols = {str(r[1]) for r in led.db.execute("PRAGMA table_info(runs)")}
        assert "carried_from" in cols, "a schema-2 ledger gains schema 3's column"
        assert led._meta("schema") == str(ledger_mod.SCHEMA)
    finally:
        led.close()


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


def test_a_budget_end_ends_the_run_failed_budget_with_its_phase(disk: Disk, led: Ledger) -> None:
    """A budget end reaches the ledger as itself: its own outcome, its phase row, and an end."""
    run_id = fresh_run(disk, led)
    spent = Fake(result=_harness_result(outcome="failed:budget"))
    row = runner_mod.run_phase(
        disk.ctx, _reg(disk), led, disk.call, run_id=run_id, phase="build", factory=lambda h, r: spent
    )
    assert row["outcome"] == "failed:budget" and row["ended_at"] and row["phases"]


def test_a_refused_phase_is_on_the_record_and_ends_when_the_adapter_gave_up(disk: Disk, led: Ledger) -> None:
    """`r-4`'s record, both defects: its `ended_at` was the phase's start (seventeen minutes early) and its `phases`
    held nothing. The clock moves while the adapter works, so an end read before the phase cannot pass."""
    run_id = fresh_run(disk, led)
    start = _dt.datetime(2026, 9, 14, 22, 59, 21, tzinfo=_dt.UTC)
    clock = [start]
    spent = adapter_mod.result(
        {**_harness_result(outcome="failed:infra", tokens=26809, cost_micro=1426187), "run_id": run_id}
    )

    @dataclass
    class Refusing(Fake):
        def execute(self, job: RunJob) -> PhaseResult:
            clock[0] = _dt.datetime(2026, 9, 14, 23, 16, 22, tzinfo=_dt.UTC)
            raise adapter_mod.PhaseRefusal("adapter.infra", job.run_id, "2 attempts", spent)

    refuses(
        "adapter.infra",
        lambda: runner_mod.run_phase(
            disk.ctx,
            _reg(disk),
            led,
            disk.call,
            run_id=run_id,
            phase="build",
            factory=lambda h, r: Refusing(),
            now=lambda: clock[0],
        ),
    )
    row = led.run(run_id)
    assert row is not None and row["outcome"] == "failed:infra" and row["ended_at"] == "2026-09-14T23:16:22Z"
    phases = led.phases_of(run_id)
    assert phases and (phases[-1]["tokens"], phases[-1]["cost_micro"]) == (26809, 1426187)


def test_a_failed_phases_work_is_committed_to_its_branch_and_the_branch_is_never_pushed(
    disk: Disk, led: Ledger
) -> None:
    """[owner, 2026-09-15] `r-5`'s builder had edited all seven surfaces when its harness crashed, and the worktree was
    removed with nothing kept. The work is committed to the story branch with a trailer naming the failure, the row
    carries that head — and `push` refuses the branch, so a failure's work never reaches the forge."""
    run_id = fresh_run(disk, led)

    @dataclass
    class Crashing(Fake):
        def execute(self, job: RunJob) -> PhaseResult:
            (Path(job.worktree) / INSIDE).parent.mkdir(parents=True, exist_ok=True)
            (Path(job.worktree) / INSIDE).write_text("half-done = True\n", encoding="utf-8")
            raise adapter_mod.PhaseRefusal("adapter.infra", job.run_id, "the harness crashed")

    refuses(
        "adapter.infra",
        lambda: runner_mod.run_phase(
            disk.ctx, _reg(disk), led, disk.call, run_id=run_id, phase="build", factory=lambda h, r: Crashing()
        ),
    )
    row = led.run(run_id)
    assert row is not None and row["head_sha"], "the failed phase's work was not committed"
    assert row["surfaces_actual"] == [INSIDE]
    message = git(disk.work, "log", "-1", "--format=%B", f"story/{run_id}")
    assert "Factory-Outcome: failed:infra" in message and f"Factory-Run: {run_id}" in message
    assert git(disk.work, "rev-parse", f"story/{run_id}").strip() == row["head_sha"]

    common = ["--tenant", TENANT, "--checkout", str(disk.work), "--root", ROOT]
    p = CliRunner().invoke(cli_mod.app, ["push", *common, "--branch", f"story/{run_id}"])
    assert p.exit_code == 2 and "forge.failed-run" in p.output, p.output


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
    assert row["head_sha"], "a scope failure's work is kept on its branch too [owner, 2026-09-15]"
    assert "Factory-Outcome: failed:scope" in git(disk.work, "log", "-1", "--format=%B", f"story/{run_id}")
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


def test_an_adapter_that_ran_another_model_fails_conformance(
    disk: Disk, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Q-V25: the model check could not fail while the container adapter copied the policy's model into its result.
    Now it reads what ran, and the suite is shown to catch an adapter that ran something the tenant did not sign —
    through the fake and through the container adapter both."""
    job = a_job(disk)
    assert any(
        "the policy named" in b for b in conformance.run(Fake(ran="claude-sonnet-5"), job, monkeypatch, tmp_path)
    )
    pod = Podman(result=_harness_result(model="claude-sonnet-5"))
    bad = conformance.run(Container(disk.home, _reg(disk), run=pod), job, monkeypatch, tmp_path / "container")
    assert any("the policy named" in b for b in bad), bad


# ------------------------------------------------------------------------------ the harness inside the image (Q-V25)


def test_the_harness_argv_carries_the_agents_signed_model_and_effort(disk: Disk) -> None:
    """The signed `[agents]` row on the harness's own command line — the fact the shell entrypoint never passed. Two
    agents with different rows, so an argv built from one fixed value cannot pass both."""
    for agent, model, effort in (("builder", "claude-opus-5", "xhigh"), ("plan-refuter", "claude-sonnet-5", "high")):
        ident = {"agent": agent, "name": "isdm-fac-lander", "email": "1+x@users.noreply.github.com"}
        args = harness.argv(a_job(disk, identity=ident), "/run/settings.json")
        assert args[0] == "claude"
        assert args[args.index("--model") + 1] == model and args[args.index("--effort") + 1] == effort, args
        assert args[args.index("--settings") + 1] == "/run/settings.json"
        assert args[args.index("--max-turns") + 1] == str(a_job(disk).policy.budgets.max_turns)
        # r-5: a streamed answer, so a crash leaves what finished; `--print` streams only with `--verbose`
        assert args[args.index("--output-format") + 1] == "stream-json" and "--verbose" in args


def test_the_result_reads_the_model_that_ran_and_counts_tokens_as_declared(disk: Disk) -> None:
    """`r-3`'s own harness output, in shape: the phase's model is the one that produced the output, not the utility
    model beside it and not the row that was asked for; `tokens` is input + output and the cache counts ride beside
    it (Q-V26 (a)); a harness that ran nothing names no model."""
    out = {
        "usage": {
            "input_tokens": 76,
            "output_tokens": 42071,
            "cache_read_input_tokens": 3689226,
            "cache_creation_input_tokens": 98477,
        },
        "modelUsage": {"claude-haiku-4-5-20251001": {"outputTokens": 14}, "claude-sonnet-5": {"outputTokens": 42071}},
        "total_cost_usd": 1.5678892,
        "duration_ms": 1009710,
    }
    got = harness.report(a_job(disk), out, True, "2.1.269")
    assert got["model"] == "claude-sonnet-5" and got["effort"] == "xhigh"
    assert (got["tokens"], got["cache_read_tokens"], got["cache_write_tokens"]) == (42147, 3689226, 98477)
    assert got["cost_micro"] == 1567889 and got["outcome"] == "ok"
    assert adapter_mod.result(got).model == "claude-sonnet-5"
    assert harness.report(a_job(disk), {}, False, "2.1.269")["model"] == harness.UNMEASURED


@dataclass
class Child:
    """A spawned harness: `wait` delivers `signals` to whatever handler PID 1 installed, as the watchdog would."""

    handlers: dict[int, Any]
    signals: tuple[int, ...] = ()
    sent: list[int] = field(default_factory=list)
    done: bool = False

    def poll(self) -> int | None:
        return 0 if self.done else None

    def send_signal(self, sig: int) -> None:
        self.sent.append(sig)

    def wait(self) -> int:
        for sig in self.signals:
            self.handlers[sig](sig, None)
        self.done = True
        return -int(self.sent[0]) if self.sent else 0


def test_pid_1_forwards_the_watchdogs_term_to_the_harness(disk: Disk, tmp_path: Path) -> None:
    """The watchdog's `TERM` reaches the harness through PID 1's handler, and the stopped phase still leaves a result
    — `failed:infra`, never `ok`. And a stop that lands before the harness exists starts no harness at all."""
    prompts = tmp_path / "prompts"
    (prompts / "builder").mkdir(parents=True)
    (prompts / "builder" / "v1.md").write_text("# the builder", encoding="utf-8")
    job = a_job(disk)

    handlers: dict[int, Any] = {}
    spawned: list[Child] = []

    def spawn(args: list[str], **_kw: Any) -> Child:
        spawned.append(Child(handlers, signals=(signal.SIGTERM,)))
        return spawned[-1]

    run1 = tmp_path / "run1"
    run1.mkdir()
    code = harness.run(
        job, run1, prompts, harness_version="2.1.269", spawn=spawn, install=handlers.__setitem__, work=tmp_path
    )
    assert spawned and spawned[0].sent == [signal.SIGTERM], "the TERM never reached the harness"
    assert code == 1 and json.loads((run1 / "result.json").read_text(encoding="utf-8"))["outcome"] == "failed:infra"
    told = json.loads((run1 / "harness.json").read_text(encoding="utf-8"))
    assert f"signal {int(signal.SIGTERM)}" in harness.reason_of(told), told
    assert (run1 / "input.md").read_text(encoding="utf-8").startswith("# the builder")

    early: list[Child] = []

    def spawn_early(args: list[str], **_kw: Any) -> Child:
        early.append(Child({}))
        return early[-1]

    def stop_now(sig: int, handler: Any) -> None:
        handler(sig, None)

    run2 = tmp_path / "run2"
    run2.mkdir()
    code = harness.run(
        job, run2, prompts, harness_version="2.1.269", spawn=spawn_early, install=stop_now, work=tmp_path
    )
    assert early == [] and code == 1, "a stop before the spawn still started the harness"


def test_the_phase_event_carries_the_cache_counts(disk: Disk, led: Ledger) -> None:
    """Q-V26 (a): no column for the cached context — it rides the ledger's own `phase` event."""
    run_id = fresh_run(disk, led)
    res = adapter_mod.result({**_harness_result(cache_read_tokens=3689226, cache_write_tokens=98477), "run_id": run_id})
    led.phase(run_id, "2026-09-13T00:00:00Z", res.row())
    ev = [e for e in led.events_of(run_id) if e["kind"] == "phase"][-1]
    assert (ev["data"]["cache_read_tokens"], ev["data"]["cache_write_tokens"]) == (3689226, 98477)
    assert led.phases_of(run_id)[-1]["tokens"] == 1234


# ------------------------------------------------------------------------------------------------------ helpers


def _reg(disk: Disk) -> Registration:
    reg = disk.ctx.registration
    assert reg is not None
    return reg
