"""Card 26: a run whose pull request is red on the gate gets one fixup phase on its own branch, invoked by the operator.

`run --run r-N --phase fixup` reads the required checks on the pull request's head and refuses `run.fixup-nothing-red`
when none is red (R1); when some are, the builder runs in the run's worktree handed each failed check's name, failed
step and log tail, read from the forge and named by hash on the record (R2), writes inside the build's surface, and its
work is committed under the run's identity with a trailer naming the fixup, the head advancing to it, its diff on its
phase row (R3). One round: a second red ends the run `failed:gate` with no model call (R4). A fixup is not reviewed
again, and close reads a run whose last phase is a fixup after a passed review as reviewed (R5). Builder v6 names the
phase and v5 is untouched (R6). A fixup on a run whose review gate did not run to its end is refused (R7).

The forge is a double that answers the three reads a fixup makes and refuses every other verb, so that "never pushed,
never opened" is the double's refusal and not only an assertion; the GitHub driver's own read is held over
`httpx.MockTransport`. The runs are the V4a tenant's, over a real store and checkout.
"""

from __future__ import annotations

import dataclasses
import difflib
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, NoReturn

import httpx
import pytest
from typer.testing import CliRunner

from isidium.factory import adapter as adapter_mod
from isidium.factory import artifacts
from isidium.factory import cli as cli_mod
from isidium.factory import close as close_mod
from isidium.factory import github as github_mod
from isidium.factory import runner as runner_mod
from isidium.factory.forge import (
    Capabilities,
    Changed,
    CheckRun,
    Checks,
    FailedJob,
    MergeableState,
    MergeState,
    PullRequest,
    PullRequestSpec,
)
from isidium.factory.github import GitHub
from isidium.factory.ledger import Ledger

from ..store.conftest import git
from .test_reviewer_is_handed_the_diff import Marking, _git_diff
from .test_v4a import INSIDE, ROOT, TENANT, Disk, _reg, disk, fresh_run, refuses
from .test_v4a_ii import PLAN, chain, led, one
from .test_v5a import Acceptance

__all__ = ["disk", "led"]  # the V4a tenant and its ledger, as test_v4a_ii builds them

_ROOT = Path(__file__).resolve().parents[2]
V5 = _ROOT / "prompts" / "builder" / "v5.md"
V6 = _ROOT / "prompts" / "builder" / "v6.md"

# v5's git blob id as ratified (card 23's build) — any byte edit to v5 changes it.
V5_BLOB = "3331eeb35e9fa20ede131683239f834b78fdf2ad"

GREEN = Checks(("green-bar",), (CheckRun("green-bar", "completed", "success"),))
RED = Checks(("green-bar",), (CheckRun("green-bar", "completed", "failure"),))
PENDING = Checks(("green-bar",), (CheckRun("green-bar", "in_progress", None),))
FAILED = FailedJob("green-bar", "Run ruff", "E501 line too long (121 > 120)\nFound 1 error.")
PR = 7


def _never(verb: str) -> NoReturn:
    raise AssertionError(f"a fixup never calls {verb}")


@dataclass
class Gate:
    """The whole `Forge` protocol, answered for the three reads a fixup makes and refused for the rest. `reads` is the
    scripted answer to `checks`, one per call, the last one repeating."""

    head: str = ""
    reads: list[Checks] = field(default_factory=lambda: [RED])
    jobs: tuple[FailedJob, ...] = (FAILED,)
    merged: bool = False
    merge: str | None = None
    seen: list[tuple[Any, ...]] = field(default_factory=list)

    def merge_state(self, number: int) -> MergeState:
        self.seen.append(("merge_state", number))
        return MergeState(self.head, True, MergeableState.CLEAN, self.merged, self.merge)

    def checks(self, sha: str) -> Checks:
        self.seen.append(("checks", sha))
        return self.reads.pop(0) if len(self.reads) > 1 else self.reads[0]

    def failed_jobs(self, sha: str, names: tuple[str, ...]) -> tuple[FailedJob, ...]:
        self.seen.append(("failed_jobs", sha, names))
        return self.jobs

    def fetch(self, ref: str) -> str:
        _never("fetch")

    def branch(self, name: str, at: str) -> None:
        _never("branch")

    def changed(self, base: str, head: str) -> Changed:
        _never("changed")

    def push(self, name: str) -> Changed:
        _never("push")

    def open_pr(self, spec: PullRequestSpec) -> PullRequest:
        _never("open_pr")

    def rerun_failed(self, sha: str) -> tuple[int, ...]:
        _never("rerun_failed")

    def capabilities(self) -> Capabilities:
        _never("capabilities")


def _row(led: Ledger, run_id: str) -> dict[str, Any]:
    row = led.run(run_id)
    assert row is not None
    return row


def reviewed_run(disk: Disk, led: Ledger, **gate: Any) -> tuple[Marking, str, Gate]:
    """A run driven through the chain to the end of its review gate (plan, refute, judge, build, a clean review), its
    pull request recorded and the forge double at its head, red unless `gate` says otherwise."""
    run_id = fresh_run(disk, led)
    drv = Marking(home=disk.home, marks={"build": "built-by-the-build\n", "fixup": "fixed-by-the-fixup\n"})
    chain(disk, led, run_id, drv)
    led.set_pr(run_id, PR)
    return drv, run_id, Gate(head=str(_row(led, run_id)["head_sha"]), **gate)


def fixup(disk: Disk, led: Ledger, run_id: str, drv: Marking, forge: Gate, ctx: Any = None) -> dict[str, Any]:
    return runner_mod.run_fixup(
        ctx or disk.ctx, _reg(disk), led, disk.call, forge, run_id=run_id, factory=lambda h, r: drv
    )


def _fixups(drv: Marking) -> list[adapter_mod.RunJob]:
    return [j for j in drv.seen if j.phase == "fixup"]


def _phase_event(led: Ledger, run_id: str, phase: str) -> dict[str, Any]:
    (event,) = [e for e in led.events_of(run_id) if e["kind"] == "phase" and e["data"]["phase"] == phase]
    return dict(event["data"])


def _artifact(home: Path, event: dict[str, Any], name: str) -> tuple[dict[str, str], bytes]:
    (made,) = [a for a in event["artifacts"] if a["name"] == name]
    return made, (home / made["path"]).read_bytes()


# ------------------------------------------------------------------------------------------------------- R1 / S1


def test_a_green_head_refuses_and_spends_nothing(disk: Disk, led: Ledger, monkeypatch: pytest.MonkeyPatch) -> None:
    drv, run_id, forge = reviewed_run(disk, led, reads=[GREEN, PENDING])
    before = len(drv.seen)
    refuses("run.fixup-nothing-red", lambda: fixup(disk, led, run_id, drv, forge))
    refuses("run.fixup-nothing-red", lambda: fixup(disk, led, run_id, drv, forge))  # pending is not red either
    assert len(drv.seen) == before, "no adapter job: the refusal spent nothing"
    assert [s[0] for s in forge.seen if s[0] == "failed_jobs"] == [], (
        "the logs were not read for a head that is not red"
    )
    assert not [p for p in led.phases_of(run_id) if p["phase"] == "fixup"]
    assert _row(led, run_id)["ended_at"] is None, "the run stays in flight"

    # The verb: `run --run r-N --phase fixup`, the forge driver swapped for the double.
    monkeypatch.setattr(github_mod, "GitHub", lambda ctx: forge)
    monkeypatch.setattr(cli_mod, "Transport", lambda cfg, home: SimpleNamespace(call=disk.call))  # no mTLS channel here
    forge.reads = [GREEN]
    argv = [
        "run",
        "--tenant",
        TENANT,
        "--checkout",
        str(disk.work),
        "--root",
        ROOT,
        "--run",
        run_id,
        "--phase",
        "fixup",
    ]
    out = CliRunner().invoke(cli_mod.app, argv)
    assert out.exit_code == 2 and "run.fixup-nothing-red" in out.output, out.output


# ------------------------------------------------------------------------------------------------------- R2 / S2


def test_a_red_head_runs_the_fixup_with_the_failures_as_inputs(disk: Disk, led: Ledger) -> None:
    drv, run_id, forge = reviewed_run(disk, led)
    row = fixup(disk, led, run_id, drv, forge)
    (job,) = _fixups(drv)
    assert job.identity.agent == "builder"
    assert job.prompt_version == job.policy.agent("builder").prompt
    (given,) = job.inputs
    content = {
        "head": forge.head,
        "checks": [{"name": FAILED.name, "step": FAILED.step, "tail": FAILED.tail}],
    }
    assert given.name == "failures" and dict(given.content) == content
    assert given.sha256 == artifacts.sha256(artifacts.canonical(content))
    assert ("failed_jobs", forge.head, ("green-bar",)) in forge.seen
    assert row["ended_at"] is None, "a fixup that ran leaves the run in flight, for the operator to push"

    # Named by hash on the record: the phase event carries it, and the bytes at its path hash to it.
    made, data = _artifact(disk.home, _phase_event(led, run_id, "fixup"), "failures")
    assert made["sha256"] == given.sha256 and artifacts.sha256(data) == given.sha256
    assert json.loads(data) == content


def _log(lines: list[str]) -> str:
    return "\n".join(lines) + "\n"


def test_the_github_driver_reads_the_failed_steps_last_200_lines(disk: Disk) -> None:
    repo = f"/repos/{disk.ctx.forge.owner}/{disk.ctx.forge.repo}"
    before = [f"2026-10-02T12:00:05.{i:07d}Z earlier step {i}" for i in range(20)]
    inside = [f"2026-10-02T12:00:12.{i:07d}Z failing step {i}" for i in range(250)]
    inside.append("    a continuation line the runner stamped no time on")
    after = [f"2026-10-02T12:00:30.{i:07d}Z later step {i}" for i in range(20)]
    seen: list[httpx.Request] = []

    def answer(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        if req.url.host == "logs.example.test":
            return httpx.Response(200, text="﻿" + _log([*before, *inside, *after]))
        match req.url.path:
            case p if p == f"{repo}/commits/abc/check-runs":
                actions = {"slug": "github-actions"}
                return httpx.Response(
                    200,
                    json={
                        "check_runs": [
                            {
                                "name": "green-bar",
                                "status": "completed",
                                "conclusion": "failure",
                                "id": 555,
                                "app": actions,
                            },
                            {"name": "docs", "status": "completed", "conclusion": "success", "id": 556, "app": actions},
                            {
                                "name": "green-bar",
                                "status": "completed",
                                "conclusion": "success",
                                "id": 400,
                                "app": actions,
                            },
                        ]
                    },
                )
            case p if p == f"{repo}/actions/jobs/555":
                steps = [
                    {
                        "name": "Set up",
                        "conclusion": "success",
                        "started_at": "2026-10-02T12:00:00Z",
                        "completed_at": "2026-10-02T12:00:09Z",
                    },
                    {
                        "name": "Run ruff",
                        "conclusion": "failure",
                        "started_at": "2026-10-02T12:00:10Z",
                        "completed_at": "2026-10-02T12:00:20Z",
                    },
                ]
                return httpx.Response(200, json={"run_id": 77, "run_attempt": 1, "steps": steps})
            case p if p == f"{repo}/actions/runs/77/attempts/1/jobs":
                jobs = [
                    {"id": 555, "name": "green-bar", "status": "completed", "conclusion": "failure"},
                    {"id": 556, "name": "docs", "status": "completed", "conclusion": "success"},
                ]
                return httpx.Response(200, json={"jobs": jobs})
            case p if p == f"{repo}/actions/jobs/555/logs":
                return httpx.Response(302, headers={"Location": "https://logs.example.test/blob/555"})
        return httpx.Response(404, json={"message": "not found: " + req.url.path})

    drv = GitHub(disk.ctx, transport=httpx.MockTransport(answer), sleep=lambda s: None)
    got = drv.failed_jobs("abc", ("green-bar",))
    assert got == (FailedJob("green-bar", "Run ruff", "\n".join(inside[-200:])),)
    assert len(got[0].tail.splitlines()) == 200
    assert any(r.url.path == f"{repo}/actions/runs/77/attempts/1/jobs" for r in seen), "the run's jobs were read"
    logs = [r for r in seen if r.url.host == "logs.example.test"]
    assert len(logs) == 1 and "authorization" not in logs[0].headers, "the token does not follow the redirect"
    assert all("authorization" in r.headers for r in seen if r.url.host == "api.github.com")

    # A check that is not an Actions job is named, with nothing to read; a job with no failed step has its log's tail.
    def other(req: httpx.Request) -> httpx.Response:
        runs = [
            {"name": "external", "status": "completed", "conclusion": "failure", "id": 9, "app": {"slug": "elsewhere"}}
        ]
        return httpx.Response(200, json={"check_runs": runs})

    odd = GitHub(disk.ctx, transport=httpx.MockTransport(other), sleep=lambda s: None)
    assert odd.failed_jobs("abc", ("external",)) == (FailedJob("external", None, ""),)


# ------------------------------------------------------------------------------------------------------- R3 / S3


def test_the_fixups_work_is_committed_under_the_run(disk: Disk, led: Ledger) -> None:
    drv, run_id, forge = reviewed_run(disk, led)
    before = str(_row(led, run_id)["head_sha"])
    row = fixup(disk, led, run_id, drv, forge)
    (job,) = _fixups(drv)
    assert job.allowed_writes == (*PLAN["touched"], "tests/"), "the build's surface: the plan's touched and the tests"

    after = git(disk.work, "rev-parse", f"story/{run_id}").strip()
    assert after != before and row["head_sha"] == after, "the run's head advanced to the fixup's commit"
    assert git(disk.work, "log", "-1", "--format=%P", after).strip() == before, "one commit on the prior head"
    ident = disk.ctx.identity
    assert git(disk.work, "log", "-1", "--format=%an <%ae>|%cn <%ce>", after).strip() == (
        f"{ident.name} <{ident.email}>|{ident.name} <{ident.email}>"
    )
    body = git(disk.work, "log", "-1", "--format=%B", after).splitlines()
    assert f"Factory-Run: {run_id}" in body and "Factory-Agent: builder (fixup)" in body
    assert body[0] == f"builder (fixup): {run_id}"

    # Its diff is on its phase row, byte for byte what git says the fixup changed.
    event = _phase_event(led, run_id, "fixup")
    assert event["touched"] == [INSIDE]
    made, data = _artifact(disk.home, event, "diff")
    assert artifacts.sha256(data) == made["sha256"]
    want = {"base": before, "head": after, "diff": _git_diff(disk.work, before, after)}
    assert json.loads(data) == want and "+fixed-by-the-fixup" in want["diff"]
    assert [a["name"] for a in event["artifacts"]] == ["failures", "diff"], "failures first"

    assert {s[0] for s in forge.seen} <= {"merge_state", "checks", "failed_jobs"}, "nothing pushed, nothing opened"


# ------------------------------------------------------------------------------------------------------- R4 / S4


def test_a_second_red_ends_the_run_failed_gate(disk: Disk, led: Ledger) -> None:
    drv, run_id, forge = reviewed_run(disk, led)
    fixup(disk, led, run_id, drv, forge)
    forge.head = str(_row(led, run_id)["head_sha"])  # the operator pushed the fixup; the gate is red again
    spent, reads = len(drv.seen), len([s for s in forge.seen if s[0] == "failed_jobs"])

    row = fixup(disk, led, run_id, drv, forge)
    assert row["outcome"] == "failed:gate" and row["ended_at"]
    assert row["head_sha"] == forge.head == git(disk.work, "rev-parse", f"story/{run_id}").strip(), "work kept"
    assert len(drv.seen) == spent, "no model call"
    assert len([s for s in forge.seen if s[0] == "failed_jobs"]) == reads, "the logs were not read again"
    failed = [e["data"] for e in led.events_of(run_id) if e["kind"] == "failed"]
    assert failed and failed[-1]["class"] == "gate"
    ended = [e["data"] for e in led.events_of(run_id) if e["kind"] == "ended"][-1]
    assert ended["fixup"] == "still-red" and ended["failed"] == ["green-bar"]
    refuses("run.ended", lambda: fixup(disk, led, run_id, drv, forge))


def test_a_fixup_waits_for_the_push_it_asks_the_operator_for(disk: Disk, led: Ledger) -> None:
    """A head that is not the run's — the previous fixup not yet pushed — is refused and spends nothing, rather than
    read as a second red and end the run; so is a run with no pull request."""
    drv, run_id, forge = reviewed_run(disk, led)
    fixup(disk, led, run_id, drv, forge)  # the forge still reports the pre-fixup head
    spent = len(drv.seen)
    refuses("run.fixup-pr-mismatch", lambda: fixup(disk, led, run_id, drv, forge))
    assert len(drv.seen) == spent and _row(led, run_id)["ended_at"] is None
    bare, bare_id, _ = reviewed_run(disk, led)
    led.db.execute("UPDATE runs SET pr = NULL WHERE run_id = ?", (bare_id,))
    refuses("run.fixup-no-pr", lambda: fixup(disk, led, bare_id, bare, Gate()))


# ------------------------------------------------------------------------------------------------------- R5 / S5


def test_close_treats_a_fixup_after_review_as_reviewed(disk: Disk, led: Ledger) -> None:
    drv, run_id, forge = reviewed_run(disk, led)
    fixup(disk, led, run_id, drv, forge)
    head = str(_row(led, run_id)["head_sha"])
    spent = len(drv.seen)
    chain(disk, led, run_id, drv)
    assert len(drv.seen) == spent, "the chain runs no further phase after a fixup: the review stands"

    git(disk.work, "merge", "--no-ff", "-q", "-m", f"Merge story/{run_id}", f"story/{run_id}")
    merge = git(disk.work, "rev-parse", "HEAD").strip()
    done = Gate(head=head, reads=[GREEN], merged=True, merge=merge)
    out = close_mod.close(disk.ctx, led, disk.call, done, run_id=run_id, pr=PR, accept=Acceptance())
    assert out["outcome"] == "closed", "not close.review-skipped, and the identity walk passes over the fixup commit"
    ended = [e["data"] for e in led.events_of(run_id) if e["kind"] == "ended"][-1]
    assert ended["phases"][-1] == "fixup"


# ------------------------------------------------------------------------------------------------------- R6 / S6


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


_TITLE = "# The builder — v"
_STATUS = "> **Status:**"
_INPUTS = "- `inputs` — in **reconcile** only"
_FINISH = "## 7. How you finish"


def _allowed(v5_lines: list[str]) -> list[tuple[int, int]]:
    """The half-open ranges of v5 lines v6 may change: provenance, title, Status, §1's inputs bullet and the heading
    of the section that follows the insertion — plus, as pure insertions, the v6 changelog before the Status and the
    fixup section before `How you finish`."""

    def at(prefix: str) -> int:
        return next(i for i, line in enumerate(v5_lines) if line.startswith(prefix))

    return [
        (0, 1),
        (at(_TITLE), at(_TITLE) + 1),
        (at(_STATUS), at(_STATUS) + 1),
        (at(_INPUTS), at(_INPUTS) + 1),
        (at(_FINISH), at(_FINISH) + 1),
    ]


def _inside(i1: int, i2: int, allowed: list[tuple[int, int]]) -> bool:
    if i1 == i2:
        return any(lo <= i1 <= hi for lo, hi in allowed)
    return any(lo <= i1 and i2 <= hi for lo, hi in allowed)


def test_builder_v6_names_the_fixup_section() -> None:
    v5_bytes, v6_bytes = V5.read_bytes(), V6.read_bytes()
    assert hashlib.sha1(b"blob %d\0" % len(v5_bytes) + v5_bytes).hexdigest() == V5_BLOB, "v5 is unedited"
    assert b"\r" not in v6_bytes and v6_bytes != v5_bytes
    v5, v6 = v5_bytes.decode("utf-8"), v6_bytes.decode("utf-8")
    assert "version=6" in v6.splitlines()[0]
    assert "# The builder — v6" in v6 and "What changed in v6" in v6
    assert "**What changed in v5, and why.**" in v6, "v5's changelog is kept"
    assert "fixup" not in v5.lower(), "the phase is v6's"

    start = v6.index("## 7. If the gate is red — fixup")
    section = _flat(v6[start : v6.index("## 8. How you finish", start)]).lower()
    for phrase in (
        "`failures`",
        "inside the surfaces",
        "change nothing else",
        "`ruff check`",
        "`ruff format --check`",
        "`mypy --strict`",
        "by path",
        "do not push",
    ):
        assert phrase in section, phrase
    assert "`failures`" in _flat(v6[v6.index("## 1. ") : v6.index("## 2. ")]), "§1 names the input"

    v5_lines = v5.splitlines()
    allowed = _allowed(v5_lines)
    ops = difflib.SequenceMatcher(None, v5_lines, v6.splitlines(), autojunk=False).get_opcodes()
    for tag, i1, i2, _j1, _j2 in ops:
        if tag != "equal":
            assert _inside(i1, i2, allowed), (tag, v5_lines[i1:i2])


# ------------------------------------------------------------------------------------------------------- R7 / S7


def test_a_fixup_on_an_unreviewed_run_is_refused(disk: Disk, led: Ledger) -> None:
    run_id = fresh_run(disk, led)
    drv = Marking(home=disk.home, marks={"build": "built-by-the-build\n", "fixup": "fixed-by-the-fixup\n"})
    one(disk, led, run_id, "build", drv)  # a build with no review behind it
    led.set_pr(run_id, PR)
    forge = Gate(head=str(_row(led, run_id)["head_sha"]))
    spent = len(drv.seen)
    refuses("run.fixup-unreviewed", lambda: fixup(disk, led, run_id, drv, forge))
    assert forge.seen == [], "refused before the forge is asked anything"
    assert len(drv.seen) == spent and _row(led, run_id)["ended_at"] is None

    # The complement: a tenant that declares no reviewer is owed none (close's own rule), and its fixup runs.
    agents = {k: v for k, v in dict(disk.ctx.eff["agents"]).items() if k != "reviewer"}
    bare = dataclasses.replace(disk.ctx, eff={**disk.ctx.eff, "agents": agents})
    fixup(disk, led, run_id, drv, forge, ctx=bare)
    assert len(_fixups(drv)) == 1
