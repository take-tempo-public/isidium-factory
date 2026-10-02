"""Card 23 — a phase that ends with a mutation still held restores the pristine file before its work is committed
[2026-10-02].

Found 2026-09-28 on `r-27` and `r-28` (card 19): `r-27`'s build died twice inside `tools/mutate.py`'s mutation run, the
kept patch captured `guard.py` with M1 still applied, and the carry replayed it into `r-28`, whose builder answered ok.
`mutate.py` holds the pristine bytes in a git-ignored `.mutation-in-flight.json`, so the marker is in the worktree at
the phase's end and never in the patch. Amended after `r-38`'s review: F1 (attempt 1's marker survives `set_aside` into
attempt 2) and F2 (a refusal carrying a result was never tried with a marker).

The properties, and what each test discriminates:

- **R1** (S1, S2): a failed phase and a finished phase each commit the file as it was pristine, and the marker is gone
  when the phase ends. Both read the committed bytes at the row's head, so a repair that ran after the commit fails.
- **R2** (S3, the escape test, the malformed test): a marker whose bytes do not hash to its own digest, that names a
  path outside the tree, or that does not parse, restores nothing, is left where it is, is named, and does not fail the
  run. The mutated bytes staying committed is the discriminator -- a restore that ignores the digest writes over them.
- **R3** (S1, S4, S6): the repair is on the phase event, or on the ended event's detail when no phase row was written
  (and not on both when one was).
- **R4** (S5): a worktree with no marker is recorded exactly as before -- the event's keys are today's, and no journal
  is left. It passes on the code before this card by design: it is the over-reach guard.
- **R5** (S7): a marker the first attempt left is repaired before the second attempt starts, so the patch holds the
  pristine file and the second attempt never meets it.

The tenant here git-ignores the marker, as tenant #0 does (`.gitignore`): without that, `set_aside`'s `add -A` and
`reset --hard` would sweep the marker away and S7 could not fail on the code before this card.
"""

from __future__ import annotations

import base64
import hashlib
import json
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from isidium.factory import adapter as adapter_mod
from isidium.factory import checkout as checkout_mod
from isidium.factory import runner as runner_mod
from isidium.factory.adapter import PhaseResult, RunJob
from isidium.factory.container import Container
from isidium.factory.ledger import Ledger

from ..store.conftest import git
from .test_v4a import INSIDE, Disk, Fake, Podman, _harness_result, _reg, disk, fresh_run, led, refuses

__all__ = ["disk", "led"]  # the V4a tenant and its ledger fixture, re-exported so pytest can resolve them

PRISTINE = b"def ok() -> bool:\n    return True\n"
MUTATED = b"def ok() -> bool:\n    return False\n"
MARKER = checkout_mod.MARKER

# The keys a phase's event carries when nothing was repaired -- today's, and R4's claim.
EVENT_KEYS = {
    "phase",
    "outcome",
    "artifacts",
    "guard_blocks",
    "touched",
    "cache_read_tokens",
    "cache_write_tokens",
    "harness",
    "harness_version",
    "billing_class",
}


@pytest.fixture(scope="module", autouse=True)
def _marker_is_ignored(disk: Disk) -> None:
    """Tenant #0 git-ignores the marker. Written to the repository's shared `info/exclude`, which every worktree reads."""
    common = Path(git(disk.work, "rev-parse", "--path-format=absolute", "--git-common-dir").strip())
    exclude = common / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    held = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
    exclude.write_text(held + f"\n{MARKER}\n", encoding="utf-8")


def marker(tree: Path, rel: str, pristine: bytes, *, ident: str = "M1", digest: str | None = None) -> None:
    """What `tools/mutate.py`'s `hold()` writes -- the marker in its own four-key format."""
    saved = {
        "id": ident,
        "file": rel,
        "sha256": digest or hashlib.sha256(pristine).hexdigest(),
        "pristine": base64.b64encode(pristine).decode("ascii"),
    }
    (tree / MARKER).write_text(json.dumps(saved), encoding="utf-8")


def hold(tree: Path, rel: str, pristine: bytes, mutated: bytes, *, digest: str | None = None) -> None:
    """The marker, then the mutation: a mutation check that was killed while its change was applied."""
    marker(tree, rel, pristine, digest=digest)
    (tree / rel).write_bytes(mutated)


def edit(tree: Path, rel: str, data: bytes) -> None:
    (tree / rel).parent.mkdir(parents=True, exist_ok=True)
    (tree / rel).write_bytes(data)


@dataclass
class Holding(Fake):
    """A builder that edits `INSIDE`, starts a mutation check on it, and ends with the mutation still applied.
    `then` is how the phase ends: `ok`, `crash` (a refusal with no result) or `spent` (a refusal carrying one -- the
    shape a retry exhaustion produces)."""

    then: str = "ok"
    marked: str = "valid"  # `valid`, `digest` (a digest that is not its bytes's), `junk`, `escape` or `none`

    def execute(self, job: RunJob) -> PhaseResult:
        tree = Path(job.worktree)
        edit(tree, INSIDE, PRISTINE)
        if self.marked == "valid":
            hold(tree, INSIDE, PRISTINE, MUTATED)
        elif self.marked == "digest":
            hold(tree, INSIDE, PRISTINE, MUTATED, digest="0" * 64)
        elif self.marked == "junk":
            (tree / MARKER).write_text("not json {", encoding="utf-8")
        elif self.marked == "escape":
            marker(tree, "../escape.py", b"escaped = True\n")  # self-consistent, and naming a file beside the tree
        if self.then == "ok":
            return super().execute(job)
        spent = adapter_mod.result({**_harness_result(outcome="failed:infra"), "run_id": job.run_id})
        result = spent if self.then == "spent" else None
        raise adapter_mod.PhaseRefusal("adapter.infra", job.run_id, "the harness died", result)


@pytest.fixture
def at_end(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[bool]]:
    """Whether the marker was still in the tree when the phase ended -- read as the worktree is taken down."""
    seen: list[bool] = []
    real = checkout_mod.worktree_remove

    def spy(repo: Path, at: Path) -> None:
        seen.append((at / MARKER).exists())
        real(repo, at)

    monkeypatch.setattr(checkout_mod, "worktree_remove", spy)
    yield seen


def build(disk: Disk, led: Ledger, run_id: str, drv: Any, *, ends: str | None = None) -> dict[str, Any]:
    """The build phase, through the wrapper. `ends` is the rule the phase is expected to refuse with, if it does."""

    def go() -> dict[str, Any]:
        return runner_mod.run_phase(
            disk.ctx, _reg(disk), led, disk.call, run_id=run_id, phase="build", factory=lambda h, r: drv
        )

    if ends is None:
        return go()
    refuses(ends, go)
    row = led.run(run_id)
    assert row is not None
    return row


def committed(disk: Disk, sha: str | None, rel: str = INSIDE) -> bytes:
    assert sha, "nothing was committed"
    return subprocess.run(["git", "show", f"{sha}:{rel}"], cwd=disk.work, capture_output=True, check=True).stdout


def event(led: Ledger, run_id: str, kind: str) -> dict[str, Any]:
    found = [e["data"] for e in led.events_of(run_id) if e["kind"] == kind]
    assert found, f"no {kind} event"
    return dict(found[-1])


def journal(disk: Disk, run_id: str) -> Path:
    return disk.home / "worktrees" / f"{run_id}{checkout_mod.JOURNAL_SUFFIX}"


NAMED = [{"file": INSIDE, "id": "M1"}]


def test_a_failed_phase_with_a_held_mutation_keeps_the_pristine_file(
    disk: Disk, led: Ledger, at_end: list[bool]
) -> None:
    run_id = fresh_run(disk, led)
    row = build(disk, led, run_id, Holding(then="crash"), ends="adapter.infra")
    assert row["outcome"] == "failed:infra"  # the marker is not a new way for a run to end
    assert committed(disk, row["head_sha"]) == PRISTINE
    assert row["surfaces_actual"] == [INSIDE]
    assert at_end == [False]
    ended = event(led, run_id, "ended")
    assert ended["repaired"] == NAMED
    assert "repair_unverified" not in ended


def test_a_finished_phase_with_a_held_mutation_commits_the_pristine_file(
    disk: Disk, led: Ledger, at_end: list[bool]
) -> None:
    run_id = fresh_run(disk, led)
    row = build(disk, led, run_id, Holding())
    assert row["outcome"] == "dispatched"
    assert committed(disk, row["head_sha"]) == PRISTINE
    assert row["surfaces_actual"] == [INSIDE]
    assert at_end == [False]


def test_an_unverifiable_marker_restores_nothing_and_is_named(disk: Disk, led: Ledger, at_end: list[bool]) -> None:
    run_id = fresh_run(disk, led)
    row = build(disk, led, run_id, Holding(marked="digest"))
    assert committed(disk, row["head_sha"]) == MUTATED, "a restore that ignores the digest wrote over the file"
    assert at_end == [True], "an unverified marker is left where it is"
    data = event(led, run_id, "phase")
    assert data["repair_unverified"] == [INSIDE] and "repaired" not in data
    assert row["outcome"] == "dispatched"  # named, not failed


def test_the_repair_is_named_on_the_phases_row(disk: Disk, led: Ledger) -> None:
    run_id = fresh_run(disk, led)
    build(disk, led, run_id, Holding())
    data = event(led, run_id, "phase")
    assert data["repaired"] == NAMED and "repair_unverified" not in data
    assert set(data) == EVENT_KEYS | {"repaired"}
    phases = led.phases_of(run_id)
    assert [p["phase"] for p in phases] == ["build"]
    assert set(phases[0]) == {
        "phase",
        "agent",
        "model",
        "effort",
        "prompt_version",
        "tokens",
        "cost_micro",
        "duration_ms",
    }


def test_no_marker_nothing_changes(disk: Disk, led: Ledger) -> None:
    run_id = fresh_run(disk, led)
    row = build(disk, led, run_id, Holding(marked="none"))
    assert committed(disk, row["head_sha"]) == PRISTINE
    assert set(event(led, run_id, "phase")) == EVENT_KEYS
    assert not journal(disk, run_id).exists()


def test_a_refusal_carrying_a_result_records_the_repair_on_its_phase_row(disk: Disk, led: Ledger) -> None:
    run_id = fresh_run(disk, led)
    row = build(disk, led, run_id, Holding(then="spent"), ends="adapter.infra")
    assert row["outcome"] == "failed:infra"
    assert committed(disk, row["head_sha"]) == PRISTINE
    assert event(led, run_id, "phase")["repaired"] == NAMED
    ended = event(led, run_id, "ended")
    assert "repaired" not in ended, "a row was written, so the repair is named on the row and not twice"


def test_a_marker_left_by_a_first_attempt_is_repaired_before_the_second(disk: Disk, led: Ledger) -> None:
    run_id = fresh_run(disk, led)

    @dataclass
    class Marking(Podman):
        """Attempt 1 edits, starts a mutation check and dies with it applied; attempt 2 records what it found."""

        def __call__(self, argv: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
            if argv[1] == "run":
                tree = Path(next(a for a in argv if a.endswith(":/work:rw")).rsplit(":", 2)[0])
                self.found.append((tree / MARKER).exists())
                if not any(a[1] == "run" for a in self.seen):
                    edit(tree, INSIDE, PRISTINE)
                    hold(tree, INSIDE, PRISTINE, MUTATED)
            return super().__call__(argv, **kw)

    pod = Marking(fail="the harness crashed", once=True)
    row = build(disk, led, run_id, Container(disk.home, _reg(disk), run=pod))
    assert row["outcome"] == "dispatched"
    assert pod.found == [False, False], "the second attempt met the first attempt's marker"
    patch = (disk.home / "runs" / run_id / "build" / "attempt-1.patch").read_text(encoding="utf-8")
    assert "return True" in patch and "return False" not in patch, "the kept patch holds the mutated file"
    assert event(led, run_id, "phase")["repaired"] == NAMED
    assert not journal(disk, run_id).exists()


def test_a_marker_naming_a_path_outside_the_tree_restores_nothing(disk: Disk, led: Ledger, at_end: list[bool]) -> None:
    run_id = fresh_run(disk, led)
    row = build(disk, led, run_id, Holding(marked="escape"))
    assert not (disk.home / "worktrees" / "escape.py").exists(), "a marker wrote outside the worktree"
    assert at_end == [True]
    assert event(led, run_id, "phase")["repair_unverified"] == ["../escape.py"]
    assert row["outcome"] == "dispatched"


def test_a_marker_that_does_not_parse_is_named_by_its_own_name_and_fails_nothing(
    disk: Disk, led: Ledger, at_end: list[bool]
) -> None:
    run_id = fresh_run(disk, led)
    row = build(disk, led, run_id, Holding(marked="junk"))
    assert at_end == [True]
    assert event(led, run_id, "phase")["repair_unverified"] == [MARKER]
    assert row["outcome"] == "dispatched"
