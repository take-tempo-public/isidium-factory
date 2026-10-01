"""Card 21 — a carried run records the carry commit as its own head, so a carry whose later phases write nothing
can still be closed [owner, 2026-09-30].

Found with `r-33` (card 20): `r-32` ended `failed:budget` with its work complete, `r-33` carried it (commit
`60db3b6`), its build wrote nothing, and the ledger's `head_sha` stayed `None` because `_carry` committed the
replayed work without advancing the run's own row. `#89` merged, `close` refused `close.pr-mismatch` (the pull
request's head was `60db3b6`; the run's was `None`), and card 20 had to be closed by hand.

The properties, and what each test discriminates:

- **The carry commit becomes the run's head the moment it exists** (R1), read at the instant a phase is handed its
  job — before the phase has done anything — so the write is the carry's own and not a side effect of what the
  build happens to do afterward.
- **A build that commits nothing still leaves the carry commit as the run's head** (R2): the exact shape of r-33's
  defect, asserted against the pushed branch tip — the same equality `close.pr-mismatch` checks.
- **A build that commits more advances past the carry commit, as today** (R3): a guard against the two wrong shapes
  of R1 — recording the head only after the phase runs, or folding the carried files into the build's own claim.
- **A carry that replays no files commits nothing and leaves the run's head as it was** (R4): the `if files:` branch
  still gates the write; a pre-set head and surfaces (the suite's own probe shape) are left untouched.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from isidium.factory.adapter import PhaseResult, RunJob
from isidium.factory.ledger import Ledger

from ..store.conftest import git
from .test_v4a import INSIDE, Disk, Fake, _carrying_run, _failed_with_work, disk, fresh_run, led
from .test_v4a_ii import one

__all__ = ["disk", "led"]  # the V4a tenant and its ledger fixture, built once and reused here

# The fixture card's other declared surface (`base_head`'s own `surfaces`, `tests/store/conftest.py`) — unseeded by
# `_failed_with_work`, so a build that writes it is adding something the carry did not already carry.
ALSO = "client/tests/test_validator.py"


@dataclass
class Watching(Fake):
    """A `Fake` that reads the run's row and the worktree's own `HEAD` at the instant it is handed the job — before
    doing anything else — so R1 is checked at phase *start*, not merely by the end (where a wrong implementation
    that advances the head only when the phase itself commits would look the same as a right one that advanced it
    at the carry)."""

    led: Ledger | None = None
    at_start: dict[str, Any] | None = None
    head_at_start: str = ""

    def execute(self, job: RunJob) -> PhaseResult:
        assert self.led is not None
        self.at_start = self.led.run(job.run_id)
        self.head_at_start = git(Path(job.worktree), "rev-parse", "HEAD").strip()
        return super().execute(job)


def test_the_carry_commit_becomes_the_runs_head(disk: Disk, led: Ledger) -> None:
    """S1 (R1)."""
    source = _failed_with_work(disk, led)
    run_id = _carrying_run(disk, led, source)
    drv = Watching(led=led)

    one(disk, led, run_id, "build", drv)

    assert drv.at_start is not None
    assert drv.at_start["head_sha"] == drv.head_at_start != drv.at_start["base_sha"]
    assert drv.at_start["surfaces_actual"] == [INSIDE]


def test_a_carry_whose_build_writes_nothing_ends_with_the_carry_head(disk: Disk, led: Ledger) -> None:
    """S2 (R2) — r-33's defect, reproduced and closed: the run's `head_sha` equals the story branch's own tip, the
    equality `close.pr-mismatch` demands of a pull request against the run it came from."""
    source = _failed_with_work(disk, led)
    run_id = _carrying_run(disk, led, source)

    row = one(disk, led, run_id, "build", Fake())

    tip = git(disk.work, "rev-parse", f"story/{run_id}").strip()
    assert row["head_sha"] == tip
    assert row["ended_at"] is None, "a build with nothing of its own does not end the run"
    assert row["surfaces_actual"] == [INSIDE]
    assert len(row["phases"]) == 1 and row["phases"][0]["phase"] == "build"


def test_a_build_that_commits_more_advances_past_the_carry(disk: Disk, led: Ledger) -> None:
    """S3 (R3) — the build's own commit is a child of the carry commit, and its own files are the run's claim, not
    a union with what the carry already carried."""
    source = _failed_with_work(disk, led)
    run_id = _carrying_run(disk, led, source)
    drv = Watching(led=led, writes=(ALSO,))

    row = one(disk, led, run_id, "build", drv)

    assert row["head_sha"] != drv.head_at_start
    parent = git(disk.work, "rev-parse", f"{row['head_sha']}^").strip()
    assert parent == drv.head_at_start
    assert row["surfaces_actual"] == [ALSO]


def test_a_carry_with_no_files_leaves_the_head_alone(disk: Disk, led: Ledger) -> None:
    """S4 (R4) — a source run whose diff to itself is empty carries nothing; a pre-set head and surfaces on the
    carrying run (the suite's own probe shape, `test_every_phase_records_its_billing_class.py`) are untouched at
    phase start and at the end, the job's `Carried.files` is empty, and no `Factory-Carried` commit lands."""
    source = fresh_run(disk, led)
    was = led.run(disk.run_id)
    assert was is not None
    led.finish(source, "2026-09-20T00:00:00Z", "failed:infra", head_sha=str(was["base_sha"]))
    run_id = _carrying_run(disk, led, source)
    led.advance(run_id, "d" * 40, [INSIDE], None)
    drv = Watching(led=led)

    row = one(disk, led, run_id, "build", drv)

    assert drv.at_start is not None
    assert drv.at_start["head_sha"] == "d" * 40 and drv.at_start["surfaces_actual"] == [INSIDE]
    assert row["head_sha"] == "d" * 40 and row["surfaces_actual"] == [INSIDE]
    job = drv.seen[0]
    assert job.carried is not None and job.carried.files == ()
    log = git(disk.work, "log", "--format=%s%x1f%b%x1e", f"{row['base_sha']}..story/{run_id}")
    assert "Factory-Carried" not in log
