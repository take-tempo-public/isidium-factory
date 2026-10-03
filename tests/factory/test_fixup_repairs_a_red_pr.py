"""Card 26 [owner, 2026-10-02]: a run whose pull request is red on the gate gets one bounded fixup phase on its own
branch, invoked by the operator — so a one-line lint or type miss (`r-38`, `r-39`) costs a fixup, not a fresh run.

What each test discriminates:

- **R1 / S1** — a head with no red required check refuses `fixup.nothing-red` and spends nothing. The positive
  discriminators are the adapter never built, the forge's failure read never made, and the ledger unchanged — a refusal
  alone would pass for a fixup that ran and then refused.
- **R2 / S2** — the builder is handed exactly the failed *required* checks (a non-required red one is not the gate's),
  each with a 200-line tail cut at the failing step's last `##[error]` line, named by hash on the record; and the
  GitHub driver reads the newest run's job log, following the redirect, without the bearer on the second host.
- **R3 / S3** — the work is one commit under the run's identity with `Factory-Agent: builder (fixup)`, the head moves
  to it, its diff is on the phase's record by hash, and nothing in the path pushes or opens a pull request (A1); a write
  outside the plan's surface is `failed:scope` (A2).
- **R4 / S4** — a second round on a still-red head ends the run `failed:gate`, its work kept, with no adapter built.
- **R5 / S5** — close reads 'build, review, fixup' as reviewed, and 'build, fixup' as not.
- **R6 / S6** — v6 is v5 plus the fixup section, and v5 is the bytes it was.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, get_args

import httpx
import pytest
from typer.testing import CliRunner

from isidium.factory import adapter as adapter_mod
from isidium.factory import artifacts
from isidium.factory import cli as cli_mod
from isidium.factory import github as github_mod
from isidium.factory import runner as runner_mod
from isidium.factory.adapter import PhaseResult, RunJob
from isidium.factory.forge import (
    Capabilities,
    Changed,
    CheckRun,
    Checks,
    Failure,
    MergeableState,
    MergeState,
    PullRequest,
    PullRequestSpec,
    tail_of,
)
from isidium.factory.github import GITHUB
from isidium.factory.ledger import LEDGER_FILE, Ledger
from isidium.store.core.refusal import Refusal

from ..store.conftest import git
from . import test_v2, test_v5a
from .test_v4a import INSIDE, ROOT, TENANT, Disk, _reg, disk, fresh_run, refuses
from .test_v4a_ii import PLAN, Shaped, chain, led

__all__ = ["disk", "led"]  # the V4a tenant and its ledger, built once for this module

v2_disk = test_v2.disk  # the GitHub driver's own tenant (S2's unit check)
v5_disk = test_v5a.disk  # close's tenant (S5)

PR = 7
ERROR = "##[error]Process completed with exit code 1."
# 300 lines of a step's output, its failing line, then the post-job cleanup a job log carries after the step.
BODY = [f"line {i}" for i in range(300)]
LOG = "\n".join([*BODY, ERROR, "Post job cleanup.", "Cleaning up orphan processes"]) + "\n"


# ------------------------------------------------------------------------------------------------------ the doubles


@dataclass
class Fixer(Shaped):
    """The in-process adapter, as `Shaped`, whose fixup phase writes `edits` into the worktree."""

    edits: dict[str, str] = field(default_factory=dict)

    def execute(self, job: RunJob) -> PhaseResult:
        if job.phase == "fixup":
            for rel, text in self.edits.items():
                target = Path(job.worktree) / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text, encoding="utf-8")
        return super().execute(job)


@dataclass
class RedForge:
    """The forge a fixup reads — `merge_state`, `checks` and `failures` — answering for one pull request, every call
    kept. `lint` and `test` are required; `extra` fails and is not. `push` and `open_pr` are A1: the fixup never makes
    them, so a call is an `AssertionError` as well as a name in `seen`."""

    head: str
    required: Mapping[str, tuple[str, str | None]]
    seen: list[str] = field(default_factory=list)

    def merge_state(self, number: int) -> MergeState:
        self.seen.append("merge_state")
        assert number == PR
        return MergeState(self.head, True, MergeableState.CLEAN, False, None)

    def checks(self, sha: str) -> Checks:
        self.seen.append("checks")
        runs = [CheckRun(n, s, c) for n, (s, c) in self.required.items()]
        return Checks(tuple(self.required), (*runs, CheckRun("extra", "completed", "failure")))

    def failures(self, sha: str) -> tuple[Failure, ...]:
        self.seen.append("failures")
        return tuple(
            Failure(n, tail_of(LOG))
            for n, (s, c) in self.required.items()
            if s == "completed" and c not in {"success", "neutral", "skipped"}
        )

    def push(self, name: str) -> Changed:
        self.seen.append("push")
        raise AssertionError("A1: the fixup never pushes")

    def open_pr(self, spec: PullRequestSpec) -> PullRequest:
        self.seen.append("open_pr")
        raise AssertionError("A1: the fixup never opens a pull request")

    def fetch(self, ref: str) -> str:
        raise AssertionError("the fixup does not fetch")

    def branch(self, name: str, at: str) -> None:
        raise AssertionError("the fixup does not branch")

    def changed(self, base: str, head: str) -> Changed:
        raise AssertionError("the fixup does not read the diff from the forge")

    def rerun_failed(self, sha: str) -> tuple[int, ...]:
        raise AssertionError("the fixup does not rerun")

    def capabilities(self) -> Capabilities:
        return GITHUB


RED: Mapping[str, tuple[str, str | None]] = {"lint": ("completed", "failure"), "test": ("completed", "success")}
GREEN: Mapping[str, tuple[str, str | None]] = {"lint": ("completed", "success"), "test": ("completed", "success")}


def reviewed_run(disk: Disk, led: Ledger) -> tuple[str, str]:
    """A run as the chain leaves it — plan, refute, judge, a build that wrote a file, a clean review — with a pull
    request recorded on its row. Returns the run and the head the build committed."""
    run_id = fresh_run(disk, led)
    row = chain(disk, led, run_id, Shaped(home=disk.home, writes_in="build"))
    assert [p["phase"] for p in row["phases"]] == ["plan", "refute", "judge", "build", "review"]
    head = str(row["head_sha"])
    led.set_pr(run_id, PR)
    return run_id, head


def fixup(
    disk: Disk, led: Ledger, run_id: str, forge: RedForge, drv: Fixer, built: list[Fixer] | None = None
) -> dict[str, Any]:
    def factory(home: Path, reg: Any) -> Fixer:
        if built is not None:
            built.append(drv)
        return drv

    return runner_mod.run_fixup(disk.ctx, _reg(disk), led, disk.call, forge, run_id=run_id, factory=factory)


def fixups(drv: Fixer) -> list[RunJob]:
    return [j for j in drv.seen if j.phase == "fixup"]


def bytes_at(disk: Disk, artifact: dict[str, Any]) -> bytes:
    data = (disk.home / str(artifact["path"])).read_bytes()
    assert artifacts.sha256(data) == artifact["sha256"], "the bytes the record names are the bytes that are there"
    return data


# ----------------------------------------------------------------------------------------------------- R1 — S1


def test_a_green_head_refuses_and_spends_nothing(disk: Disk, led: Ledger) -> None:
    run_id, head = reviewed_run(disk, led)
    events = len(led.events_of(run_id))
    phases = len(led.phases_of(run_id))
    waiting: Mapping[str, tuple[str, str | None]] = {"lint": ("in_progress", None), "test": ("completed", "success")}
    for state in (GREEN, waiting):  # green, and merely not finished: neither is red
        forge = RedForge(head, state)
        built: list[Fixer] = []
        drv = Fixer(home=disk.home)
        r = refuses("fixup.nothing-red", lambda f=forge, d=drv, b=built: fixup(disk, led, run_id, f, d, b))
        assert head in r.path
        assert built == [] and drv.seen == [], "no adapter was built, no model call was made"
        assert "failures" not in forge.seen, "the logs were not read: nothing was red"
        assert len(led.events_of(run_id)) == events and len(led.phases_of(run_id)) == phases
        row = led.run(run_id)
        assert row is not None and row["ended_at"] is None


# ----------------------------------------------------------------------------------------------------- R2 — S2


def test_a_red_head_runs_the_fixup_with_the_failures_as_inputs(disk: Disk, led: Ledger) -> None:
    run_id, head = reviewed_run(disk, led)
    forge = RedForge(head, RED)
    drv = Fixer(home=disk.home)
    row = fixup(disk, led, run_id, forge, drv)
    assert row["ended_at"] is None and row["phases"][-1]["phase"] == "fixup"
    (job,) = fixups(drv)
    assert job.identity.agent == "builder" and job.phase == "fixup"
    assert job.allowed_writes == (INSIDE, "tests/"), "the plan's touched plus the test paths: the build's surface"
    inputs = {i.name: i for i in job.inputs}
    assert list(inputs) == ["plan", "failures"]
    assert inputs["plan"].content == artifacts.Plan.model_validate(PLAN).model_dump(mode="json")
    (failed,) = inputs["failures"].content["checks"]  # `lint` only: `test` is green and `extra` is not required
    assert failed["name"] == "lint" and inputs["failures"].content["head"] == head
    tail = failed["tail"].splitlines()
    assert len(tail) == 200 and tail[-1] == ERROR and tail[0] == "line 101"
    assert "Post job cleanup." not in failed["tail"], "the cleanup steps after the failing step are not its tail"
    # Named by hash on the record: the phase event's artifact, whose bytes are the Input's content.
    named = led.artifacts_of(run_id)["failures"]
    assert named["sha256"] == inputs["failures"].sha256
    assert json.loads(bytes_at(disk, named)) == dict(inputs["failures"].content)
    event = [e for e in led.events_of(run_id) if e["kind"] == "phase"][-1]
    assert [a["name"] for a in event["data"]["artifacts"]] == ["failures"] and event["data"]["phase"] == "fixup"
    assert forge.seen == ["merge_state", "checks", "failures"]


def test_the_github_driver_reads_the_newest_runs_job_log_and_follows_the_redirect(v2_disk: test_v2.Disk) -> None:
    """R2's read, against the driver's own wire: the newest `lint` run (902) is the one whose log is read, the older
    green one (901), the green `test` and the non-required `extra` are not, and the log's redirect to storage is followed
    with no bearer on the second host."""
    rules = [
        {
            "type": "required_status_checks",
            "parameters": {"required_status_checks": [{"context": c} for c in ("lint", "test")]},
        }
    ]

    def run(i: int, name: str, conclusion: str) -> dict[str, Any]:
        return {"id": i, "name": name, "status": "completed", "conclusion": conclusion}

    listed = {
        "total_count": 4,
        "check_runs": [
            run(902, "lint", "failure"),
            run(901, "lint", "success"),
            run(903, "test", "success"),
            run(904, "extra", "failure"),
        ],
    }
    storage = "https://logs.example.com/blob/902"

    def to_storage(req: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": storage})

    fake = test_v2.Fake(
        {
            ("GET", f"{test_v2.REPO}/rules/branches/main"): [test_v2.ok(200, rules)],
            ("GET", f"{test_v2.REPO}/commits/h1/check-runs"): [test_v2.ok(200, listed)],
            ("GET", f"{test_v2.REPO}/actions/jobs/902/logs"): [to_storage],
            ("GET", "/blob/902"): [lambda req: httpx.Response(200, text=LOG)],
        }
    )
    drv = fake.driver(test_v2.load(v2_disk))
    assert drv.failures("h1") == (Failure("lint", tail_of(LOG)),)
    paths = [r.url.path for r in fake.seen]
    assert paths == [
        f"{test_v2.REPO}/rules/branches/main",
        f"{test_v2.REPO}/commits/h1/check-runs",
        f"{test_v2.REPO}/actions/jobs/902/logs",
        "/blob/902",
    ], "one log read, for the newest failed required run, and its redirect"
    assert fake.seen[2].headers["authorization"].startswith("Bearer ")
    assert fake.seen[3].url.host == "logs.example.com" and "authorization" not in fake.seen[3].headers
    before = len(fake.seen)
    assert drv.checks("h1").runs[0].name == "lint"
    assert len(fake.seen) - before == 2, "`checks` is still the two calls it was"
    assert tail_of("a\nb") == "a\nb", "a log with no error line is its own tail"


# ----------------------------------------------------------------------------------------------------- R3 — S3


def test_the_fixups_work_is_committed_under_the_run(disk: Disk, led: Ledger) -> None:
    run_id, head = reviewed_run(disk, led)
    forge = RedForge(head, RED)
    drv = Fixer(home=disk.home, edits={INSIDE: "the line the lint named, fixed\n"})
    row = fixup(disk, led, run_id, forge, drv)
    branch = f"story/{run_id}"
    new = git(disk.work, "rev-parse", branch).strip()
    assert new != head and row["head_sha"] == new and row["ended_at"] is None, "the run's head advanced to the fixup"
    assert git(disk.work, "rev-parse", f"{new}^").strip() == head, "one commit, on top of the build's"
    who, message = git(disk.work, "log", "-1", "--format=%an <%ae>|%cn <%ce>%x00%B", new).split("\0")
    ident = f"{disk.ctx.identity.name} <{disk.ctx.identity.email}>"
    assert who.strip() == f"{ident}|{ident}"
    assert f"Factory-Run: {run_id}" in message and "Factory-Agent: builder (fixup)" in message
    assert "Factory-Outcome" not in message
    have = led.artifacts_of(run_id)
    shown = json.loads(bytes_at(disk, have["diff"]))
    assert (shown["base"], shown["head"]) == (head, new)
    assert shown["diff"] == git(disk.work, "diff", "--no-ext-diff", "--no-color", head, new)
    assert INSIDE in shown["diff"]
    event = [e for e in led.events_of(run_id) if e["kind"] == "phase"][-1]
    assert [a["name"] for a in event["data"]["artifacts"]] == ["failures", "diff"]
    assert event["data"]["touched"] == [INSIDE]
    assert "push" not in forge.seen and "open_pr" not in forge.seen, "push and the pull request stay the operator's"


def test_a_fixup_that_writes_outside_the_build_surface_ends_the_run_failed_scope(disk: Disk, led: Ledger) -> None:
    """A2, held by the write guard's recompute: a file outside the plan's touched set and the test paths is a scope
    failure, its work kept; the failures it was handed are still on its record."""
    run_id, head = reviewed_run(disk, led)
    drv = Fixer(home=disk.home, edits={"client/cards/other.py": "wider than the failing check\n"})
    refuses("run.scope", lambda: fixup(disk, led, run_id, RedForge(head, RED), drv))
    row = led.run(run_id)
    assert row is not None and row["outcome"] == "failed:scope" and row["head_sha"] != head
    assert "failures" in led.artifacts_of(run_id)


# ----------------------------------------------------------------------------------------------------- R4 — S4


def test_a_second_red_ends_the_run_failed_gate(disk: Disk, led: Ledger) -> None:
    run_id, head = reviewed_run(disk, led)
    forge = RedForge(head, RED)
    built: list[Fixer] = []
    drv = Fixer(home=disk.home, edits={INSIDE: "a fix that did not satisfy the gate\n"})
    first = fixup(disk, led, run_id, forge, drv, built)
    after = str(first["head_sha"])
    # Not yet pushed: the pull request's head is still the build's, and the run's is the fixup's.
    refuses("fixup.pr-mismatch", lambda: fixup(disk, led, run_id, forge, drv, built))
    row = led.run(run_id)
    assert row is not None and row["ended_at"] is None and len(built) == 1, "refused, still in flight, nothing spent"
    # The operator pushed it and it is still red.
    forge.head = after
    ended = fixup(disk, led, run_id, forge, drv, built)
    assert ended["outcome"] == "failed:gate" and ended["ended_at"]
    assert ended["head_sha"] == after, "the work is kept"
    assert len(built) == 1 and len(fixups(drv)) == 1, "no adapter was built and no model call made for the second"
    assert forge.seen.count("failures") == 1, "the logs were not read again"
    failed = [e for e in led.events_of(run_id) if e["kind"] == "failed"]
    assert [e["data"]["class"] for e in failed] == ["gate"]
    refuses("run.ended", lambda: fixup(disk, led, run_id, forge, drv, built))


def test_a_run_with_no_pull_request_and_the_phase_through_run_phase_are_refused(disk: Disk, led: Ledger) -> None:
    run_id = fresh_run(disk, led)
    forge = RedForge("h", RED)
    refuses("fixup.no-pr", lambda: fixup(disk, led, run_id, forge, Fixer(home=disk.home)))
    assert forge.seen == [], "refused before any forge read"
    refuses(
        "run.phase",
        lambda: runner_mod.run_phase(
            disk.ctx, _reg(disk), led, disk.call, run_id=run_id, phase="fixup", factory=lambda h, r: Fixer()
        ),
    )
    assert "fixup" in get_args(adapter_mod.Phase) and runner_mod.AGENT_OF["fixup"] == "builder"


def test_the_run_verb_reads_the_forge_for_a_fixup(disk: Disk, led: Ledger, monkeypatch: pytest.MonkeyPatch) -> None:
    """`run --run r-N --phase fixup` is the operator's door: through the verb, a green head is exit 2 naming the rule."""
    run_id, head = reviewed_run(disk, led)
    forge = RedForge(head, GREEN)
    monkeypatch.setattr(github_mod, "GitHub", lambda ctx: forge)
    # This module holds three tenants' fixtures at once and each set the deploy root; the verb reads this tenant's.
    monkeypatch.setenv("ISIDIUM_DEPLOY", str(disk.home.parents[1]))
    monkeypatch.setattr(cli_mod, "Transport", lambda cfg, home: SimpleNamespace(call=disk.call))  # no mTLS channel here
    out = CliRunner().invoke(
        cli_mod.app,
        ["run", "--tenant", TENANT, "--checkout", str(disk.work), "--root", ROOT, "--run", run_id, "--phase", "fixup"],
    )
    assert out.exit_code == 2 and "fixup.nothing-red" in out.output, out.output
    assert forge.seen == ["merge_state", "checks"]


# ----------------------------------------------------------------------------------------------------- R5 — S5


@pytest.fixture
def v5_led(v5_disk: test_v5a.Disk) -> Any:
    ledger = Ledger(v5_disk.home / LEDGER_FILE, TENANT)
    yield ledger
    ledger.close()


def add_fixup(disk: test_v5a.Disk, led: Ledger, run: test_v5a.Run) -> None:
    """The fixup phase as the wrapper records it: a `phase` event whose artifact is the failures, bytes on disk."""
    data = artifacts.canonical({"head": run.head, "checks": [{"name": "lint", "tail": ERROR}]})
    rel = f"runs/{run.run_id}/fixup/failures.json"
    (disk.home / rel).parent.mkdir(parents=True, exist_ok=True)
    (disk.home / rel).write_bytes(data)
    made = [{"name": "failures", "sha256": artifacts.sha256(data), "path": rel}]
    led.phase(run.run_id, test_v5a.AT, {"phase": "fixup", "agent": "builder", "outcome": "ok", "artifacts": made})


def test_close_treats_a_fixup_after_review_as_reviewed(v5_disk: test_v5a.Disk, v5_led: Ledger) -> None:
    reviewed = test_v5a.a_run(v5_disk, v5_led, v5_disk.factory)
    add_fixup(v5_disk, v5_led, reviewed)
    phases = [d.phase for d in runner_mod.history_of(v5_led, v5_disk.home, reviewed.run_id)]
    assert phases == ["build", "review"], "the fixup is not part of the history the review gate reads"
    assert test_v5a.close_run(v5_disk, v5_led, reviewed)["outcome"] == "closed"
    # The negative: a fixup is not a review. Without one, 'build, fixup' is still refused.
    unreviewed = test_v5a.a_run(v5_disk, v5_led, v5_disk.refused, reviewed=False)
    add_fixup(v5_disk, v5_led, unreviewed)
    forge = test_v5a.forge_for(unreviewed)
    r = refuses("close.review-skipped", lambda: test_v5a.close_run(v5_disk, v5_led, unreviewed, forge))
    assert isinstance(r, Refusal) and forge.seen == []


# ----------------------------------------------------------------------------------------------------- R6 — S6

_PROMPTS = Path(__file__).resolve().parents[2] / "prompts" / "builder"
V5 = _PROMPTS / "v5.md"
V6 = _PROMPTS / "v6.md"
# v5's git blob id at the base commit — any byte edit to v5 changes it.
V5_BLOB = "3331eeb35e9fa20ede131683239f834b78fdf2ad"
_WHOLE_TREE = ("ruff check .", "ruff format --check .", "mypy packages", "pytest tests", "mypy .")
_REQUIRED = (
    "failures",
    "inside the surfaces",
    "change nothing else",
    "ruff check",
    "ruff format --check",
    "mypy --strict",
    "every file you changed",
    "by path",
    "never the whole tree",
)


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def test_builder_v6_names_the_fixup_section() -> None:
    raw = V5.read_bytes()
    assert hashlib.sha1(b"blob %d\0" % len(raw) + raw).hexdigest() == V5_BLOB, "v5 is not edited"
    v5, v6 = raw.decode("utf-8"), V6.read_text(encoding="utf-8")
    heading = next(h for h in re.findall(r"^## .*$", v6, re.MULTILINE) if "fixup" in h)
    start = v6.index(heading)
    section = _flat(v6[start : v6.index("\n## ", start + 1)])
    for phrase in _REQUIRED:
        assert phrase in section, phrase
    assert not any(invocation in _flat(v6) for invocation in _WHOLE_TREE)
    # Outside the header, the change note, the new section and the renumbered last heading, v6 is v5.
    old, new = v5.split("\n"), v6.split("\n")

    def at(prefix: str) -> int:
        return next(i for i, line in enumerate(old) if line.startswith(prefix))

    allowed = [
        (0, 1),
        (at("# The builder"), at("# The builder") + 1),
        (at("> **Status:**"), at("> **Status:**") + 1),
        (at("## 7. How you finish"), at("## 7. How you finish") + 1),
    ]
    for tag, i1, i2, _j1, _j2 in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        inside = (
            any(lo <= i1 <= hi for lo, hi in allowed) if i1 == i2 else any(lo <= i1 and i2 <= hi for lo, hi in allowed)
        )
        assert inside, f"v6 changes v5 lines {i1}..{i2} ({tag})"
    assert "## 8. How you finish" in v6 and "# The builder — v6" in v6
