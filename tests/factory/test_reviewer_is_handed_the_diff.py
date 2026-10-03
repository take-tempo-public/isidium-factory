"""Card 25: the reviewer is handed the run's diff, computed by the wrapper, on both passes. A review phase's job carries
an input named `diff` — the unified diff of the run's base to the worktree's HEAD (R1) — on the first pass beside the
plan and on the second beside the findings and the reconcile report, so the second sees what reconcile changed (R2); the
reviewer's tools are unchanged — no Bash, no write (R3); and reviewer prompt v3 names the input and drops v2's
instruction to run git, v2 itself unedited (R4).
"""

from __future__ import annotations

import difflib
import hashlib
import re
import subprocess
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from isidium.factory import artifacts, render
from isidium.factory.adapter import PhaseResult, RunJob
from isidium.factory.ledger import Ledger

from ..store.conftest import git
from .test_v4a import INSIDE, Disk, disk, fresh_run
from .test_v4a_ii import ANSWERS, Shaped, chain, led
from .test_v4a_ii_b_chain import FOUND, REPORT, ruling

__all__ = ["disk", "led"]  # the V4a tenant and its ledger, as test_v4a_ii builds them

_ROOT = Path(__file__).resolve().parents[2]
V2 = _ROOT / "prompts" / "reviewer" / "v2.md"
V3 = _ROOT / "prompts" / "reviewer" / "v3.md"

# v2's git blob id as ratified (card 25's ref) — any byte edit to v2 changes it.
V2_BLOB = "f767d3a48067f0125ab206b892831bf0149ba41a"

# The anchors of the v2 text v3 may change; each is located by its text, never by a line number.
_TITLE = "# The reviewer — v"
_STATUS = "> **Status:**"
_V2_PARAGRAPH = "> **What changed in v2, and why.**"
_ONE = "## 1. "
_TWO = "## 2. "
_DIFF_BULLET = "- **the diff**"
_AFTER_BULLETS = "You may read the whole repository"


@dataclass
class Marking(Shaped):
    """`Shaped`, with a distinct marker written into the worktree per phase. `Shaped.writes_in` writes one fixed text
    for one phase, and these tests need the build's change and reconcile's change told apart (test_v4a_ii.py is not
    this card's surface, so the field is added here). The marker is written as bytes, so no `\\r` rides in on Windows."""

    marks: dict[str, str] = field(default_factory=dict)

    def execute(self, job: RunJob) -> PhaseResult:
        mark = self.marks.get(job.phase)
        if mark is not None:
            (Path(job.worktree) / INSIDE).parent.mkdir(parents=True, exist_ok=True)
            (Path(job.worktree) / INSIDE).write_bytes(mark.encode())
        return Shaped.execute(self, job)


def _reviews(drv: Marking) -> list[RunJob]:
    return [j for j in drv.seen if j.phase == "review"]


def _diff_of(job: RunJob) -> dict[str, str]:
    (made,) = [i for i in job.inputs if i.name == "diff"]
    assert made.sha256 == artifacts.sha256(artifacts.canonical(dict(made.content))), "the hash rides the Input"
    return {k: str(v) for k, v in made.content.items()}


def _git_diff(work: Path, base: str, head: str) -> str:
    """Git's own diff, as bytes decoded the way the wrapper decodes it: the conftest `git` helper is text mode, and
    a text-mode round trip would hide a newline mismatch on the Windows host."""
    out = subprocess.run(
        ["git", "diff", "--no-ext-diff", "--no-color", base, head], cwd=work, capture_output=True, check=True
    )
    return out.stdout.decode("utf-8", errors="replace")


def _reconciling(disk: Disk, led: Ledger) -> tuple[Marking, str]:
    run_id = fresh_run(disk, led)
    drv = Marking(
        home=disk.home,
        answers={**ANSWERS, "review": [FOUND, ruling("concur")], "reconcile": REPORT},
        marks={"build": "built-by-the-build\n", "reconcile": "fixed-by-reconcile\n"},
    )
    chain(disk, led, run_id, drv)
    return drv, run_id


def test_the_first_pass_is_handed_the_plan_and_the_diff(disk: Disk, led: Ledger) -> None:
    run_id = fresh_run(disk, led)
    drv = Marking(home=disk.home, marks={"build": "built-by-the-build\n"})
    chain(disk, led, run_id, drv)
    (review,) = _reviews(drv)
    assert [i.name for i in review.inputs] == ["plan", "diff"]
    row = led.run(run_id)
    assert row is not None
    base = str(row["base_sha"])
    got = _diff_of(review)
    assert got["base"] == base
    assert got["head"] == git(disk.work, "rev-parse", f"story/{run_id}").strip(), "the build's commit"
    assert got["diff"] == _git_diff(disk.work, base, f"story/{run_id}"), "git's own diff, byte for byte"
    assert INSIDE in got["diff"] and "+built-by-the-build" in got["diff"]


def test_the_second_pass_is_handed_the_diff_with_the_findings_and_the_report(disk: Disk, led: Ledger) -> None:
    drv, run_id = _reconciling(disk, led)
    first, second = _reviews(drv)
    assert second.round == 2
    assert [i.name for i in second.inputs] == ["findings", "reconcile-report", "diff"]
    then, now = _diff_of(first), _diff_of(second)
    assert "+fixed-by-reconcile" in now["diff"], "the second pass sees what reconcile changed"
    assert "fixed-by-reconcile" not in then["diff"], "computed per review phase, not once per run"
    assert now["head"] == git(disk.work, "rev-parse", f"story/{run_id}").strip(), "reconcile's commit"
    assert now["head"] != then["head"]
    hashes = {i.sha256 for j in (first, second) for i in j.inputs if i.name == "diff"}
    assert len(hashes) == 2, "two different diffs, two different hashes"


def test_the_reviewers_tools_are_unchanged(disk: Disk, led: Ledger) -> None:
    drv, _ = _reconciling(disk, led)
    for job in _reviews(drv):
        assert job.allowed_writes == (), "the reviewer writes nothing; the diff is data in its job"
        allow = render.settings(job.policy, "reviewer")["permissions"]["allow"]
        assert allow == ["Read", "Glob", "Grep"]
        assert not {"Bash", "Edit", "Write"} & set(allow)
        assert "diff" in [i.name for i in job.inputs]
    # The signed policy of this repository itself grants the reviewer no Bash either (docs/work/config.toml).
    signed = tomllib.loads((_ROOT / "docs" / "work" / "config.toml").read_text(encoding="utf-8"))
    assert signed["agents"]["reviewer"]["tools"] == ["Read", "Glob", "Grep"]


def _flat(text: str) -> str:
    """The text with every run of whitespace — a hard-wrap included — collapsed to one space."""
    return re.sub(r"\s+", " ", text)


def _allowed(v2_lines: list[str]) -> list[tuple[int, int]]:
    """The half-open ranges of v2 lines v3 may change: provenance, title, Status, and §1's diff and second-pass
    bullets — plus, as a pure insertion, the v3 changelog paragraph after v2's own."""

    def at(prefix: str) -> int:
        return next(i for i, line in enumerate(v2_lines) if line.startswith(prefix))

    after_v2 = at(_STATUS)  # v2's changelog paragraph ends where the Status paragraph begins
    return [
        (0, 1),
        (after_v2, after_v2),
        (at(_TITLE), at(_TITLE) + 1),
        (at(_STATUS), at(_STATUS) + 1),
        (at(_DIFF_BULLET), at(_AFTER_BULLETS) - 1),
    ]


def _inside(i1: int, i2: int, allowed: list[tuple[int, int]]) -> bool:
    """A replace or delete must lie wholly inside one allowed range; a pure insertion may land anywhere in one, its
    far edge included."""
    if i1 == i2:
        return any(lo <= i1 <= hi for lo, hi in allowed)
    return any(lo <= i1 and i2 <= hi for lo, hi in allowed)


def test_reviewer_v3_names_the_diff_input() -> None:
    v2_bytes, v3_bytes = V2.read_bytes(), V3.read_bytes()
    assert hashlib.sha1(b"blob %d\0" % len(v2_bytes) + v2_bytes).hexdigest() == V2_BLOB, "v2 is unedited"
    assert b"\r" not in v3_bytes and v3_bytes != v2_bytes
    v2, v3 = v2_bytes.decode("utf-8"), v3_bytes.decode("utf-8")
    assert "version=3" in v3.splitlines()[0]
    assert "# The reviewer — v3" in v3 and "What changed in v3" in v3
    assert _V2_PARAGRAPH in v3, "v2's changelog is kept"

    # §1 says the diff is in the job and names its input.
    section = _flat(v3[v3.index(_ONE) : v3.index(_TWO)])
    assert "`diff`" in section and "in the job" in section and "`inputs`" in section
    # The discriminator: v2 tells the reviewer to run git, v3 says that nowhere — its changelog included.
    assert "git diff" in v2 and "git diff" not in v3

    # v3 is v2's text, but for the provenance, the title, the Status, the v3 changelog and §1's two bullets.
    v2_lines = v2.splitlines()
    allowed = _allowed(v2_lines)
    ops = difflib.SequenceMatcher(None, v2_lines, v3.splitlines(), autojunk=False).get_opcodes()
    for tag, i1, i2, _j1, _j2 in ops:
        if tag != "equal":
            assert _inside(i1, i2, allowed), (tag, v2_lines[i1:i2])
