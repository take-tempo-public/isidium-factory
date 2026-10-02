"""Card 23 — a phase that ends with a mutation still held restores the pristine file before its work is committed
[2026-10-02].

Found 2026-09-28 with `r-27` and `r-28`: `r-27`'s build died twice inside `tools/mutate.py`'s mutation run, the kept
patch captured `guard.py` with M1 applied, and the carry replayed it into `r-28`, whose builder answered ok. The
mutation tool keeps the pristine bytes in a git-ignored `.mutation-in-flight.json` at the worktree's root, so the
marker is in the tree at the phase's end and never in the patch.

The properties, and what each test discriminates:

- **R1** (S1, S2): the phase ended -- by a dead harness, by finishing -- with the file mutated; what is committed
  is the pristine bytes, not the mutated ones. `WORK` and `MUTATED` both differ from each other, so a repair that
  did nothing reads differently from the right one.
- **R2** (S3): bytes that do not hash to the marker's own digest are not written. Both ends: the whole phase (the
  committed file is still the mutated one, and the record says so) and the function alone (file and marker are
  byte-for-byte what they were), plus a marker naming a path outside the tree or outside the phase's writes, and
  a marker that is not a marker.
- **R3** (S4): the repair is on the phase's event -- for a phase that ended ok and for one that ended
  `failed:budget` -- and the `phases` row gains no column. A dead harness with no phase row carries it on the
  ended event (S1).
- **R4** (S5): no marker, nothing changes: no key, no detail, the bytes as written.

The marker is git-ignored in tenant #0; the test tenant ignores it the same way, through `.git/info/exclude`, which
every worktree of the checkout shares.
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from isidium.factory import adapter as adapter_mod
from isidium.factory import runner as runner_mod
from isidium.factory.adapter import PhaseResult, RunJob
from isidium.factory.ledger import Ledger

from ..store.conftest import git
from .test_v4a import INSIDE, Disk, Fake, _harness_result, _reg, disk, fresh_run, led

__all__ = ["disk", "led"]  # the V4a tenant and its ledger fixture, re-exported so pytest can resolve them

MARKER = ".mutation-in-flight.json"
WORK = "work = 2\n"
MUTATED = "mutated = 3\n"
REPAIRED = {"file": INSIDE, "id": "M1"}


@pytest.fixture(scope="module", autouse=True)
def _ignored_marker(disk: Disk) -> None:
    """Tenant #0 git-ignores the marker (`.gitignore`); this tenant does the same, for every worktree of the checkout."""
    exclude = disk.work / ".git" / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    with exclude.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(f"\n{MARKER}\n")


def marker_for(file: str, pristine: str, *, digest: str | None = None) -> str:
    """`tools/mutate.py`'s `hold()`, in shape: id, file, sha256 of the pristine bytes, and the bytes."""
    raw = pristine.encode()
    return json.dumps(
        {
            "id": "M1",
            "file": file,
            "sha256": hashlib.sha256(raw if digest is None else digest.encode()).hexdigest(),
            "pristine": base64.b64encode(raw).decode("ascii"),
        }
    )


@dataclass
class Mutating(Fake):
    """A builder that edits `INSIDE` to `WORK`, starts a mutation (marker written, then the file mutated) and ends
    as `how` says: `ok`, `budget` (a result with `failed:budget`), or `die-bare` (a refusal with no result -- a
    harness that died). `armed` is False for the no-marker control, and `bad_digest` writes a marker whose digest is
    not its bytes'."""

    how: str = "ok"
    armed: bool = True
    bad_digest: bool = False

    def execute(self, job: RunJob) -> PhaseResult:
        self.seen.append(job)
        tree = Path(job.worktree)
        target = tree / INSIDE
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(WORK.encode())
        if self.armed:
            made = marker_for(INSIDE, WORK, digest="not these" if self.bad_digest else None)
            (tree / MARKER).write_text(made, encoding="utf-8")
            target.write_bytes(MUTATED.encode())
        if self.how == "die-bare":
            raise adapter_mod.PhaseRefusal("adapter.infra", job.run_id, "the harness died")
        spec = job.policy.agent(job.identity.agent)
        return adapter_mod.result(
            {
                **_harness_result(outcome="failed:budget" if self.how == "budget" else "ok"),
                "run_id": job.run_id,
                "phase": job.phase,
                "agent": job.identity.agent,
                "model": spec.model,
                "effort": spec.effort,
            }
        )


def build(disk: Disk, led: Ledger, drv: Mutating) -> str:
    """One build phase on a fresh run; the refusal a dead harness ends in is expected and swallowed."""
    run_id = fresh_run(disk, led)
    try:
        runner_mod.run_phase(
            disk.ctx, _reg(disk), led, disk.call, run_id=run_id, phase="build", factory=lambda h, r: drv
        )
    except adapter_mod.PhaseRefusal:
        pass
    return run_id


def head_of(led: Ledger, run_id: str) -> str:
    run = led.run(run_id)
    assert run is not None and run["head_sha"], "the phase's work was committed"
    return str(run["head_sha"])


def committed(disk: Disk, led: Ledger, run_id: str) -> str:
    return git(disk.work, "show", f"{head_of(led, run_id)}:{INSIDE}")


def event_of(led: Ledger, run_id: str, kind: str) -> dict[str, Any]:
    events = [e["data"] for e in led.events_of(run_id) if e["kind"] == kind]
    assert len(events) == 1
    return dict(events[0])


def test_a_failed_phase_with_a_held_mutation_keeps_the_pristine_file(disk: Disk, led: Ledger) -> None:
    """S1: the harness dies mid-mutation (no result, so no phase row). What `_keep_work` commits is `WORK`, not
    `MUTATED` -- `r-27`'s defect -- and the repair is on the ended event."""
    run_id = build(disk, led, Mutating(how="die-bare"))
    run = led.run(run_id)
    assert run is not None and run["outcome"] == "failed:infra"
    assert committed(disk, led, run_id) == WORK
    assert led.phases_of(run_id) == []
    assert event_of(led, run_id, "ended") == {"outcome": "failed:infra", "repaired": REPAIRED}


def test_a_finished_phase_with_a_held_mutation_commits_the_pristine_file(disk: Disk, led: Ledger) -> None:
    """S2: the phase says ok with the mutation held (`r-28`'s carry). The commit holds `WORK`, the touched set is
    the file alone, and the marker is neither in the commit nor left in the worktree."""
    run_id = build(disk, led, Mutating(how="ok"))
    assert committed(disk, led, run_id) == WORK
    run = led.run(run_id)
    assert run is not None and run["surfaces_actual"] == [INSIDE]
    assert MARKER not in git(disk.work, "ls-tree", "-r", "--name-only", head_of(led, run_id)).split()


def test_an_unverifiable_marker_restores_nothing_and_is_named(disk: Disk, led: Ledger, tmp_path: Path) -> None:
    """S3: bytes that do not hash to the marker's own digest are not written. End to end, the mutated file is what
    is committed and the event says the repair could not be verified; alone, the function leaves file and marker
    exactly as they were -- and so it does for a marker aimed outside the tree or the phase's writes."""
    run_id = build(disk, led, Mutating(how="ok", bad_digest=True))
    assert committed(disk, led, run_id) == MUTATED
    event = event_of(led, run_id, "phase")
    assert event["repair_unverified"] == {"file": INSIDE} and "repaired" not in event

    tree = tmp_path / "tree"
    (tree / "client" / "cards").mkdir(parents=True)
    victim = tree / INSIDE
    victim.write_text(MUTATED, encoding="utf-8")
    for text in (
        marker_for(INSIDE, WORK, digest="not these"),
        marker_for("../outside.py", WORK),
        marker_for(".githooks/pre-commit", WORK),
        marker_for("tests/../.githooks/pre-commit", WORK),
        "{not json",
        json.dumps({"id": "M1"}),
        json.dumps({"id": "M1", "file": INSIDE, "sha256": "0" * 64, "pristine": "!!!"}),
    ):
        (tree / MARKER).write_text(text, encoding="utf-8")
        found = runner_mod._repair_mutation(tree, (INSIDE, "tests/"))
        assert set(found) == {"repair_unverified"}, text
        assert victim.read_text(encoding="utf-8") == MUTATED and (tree / MARKER).read_text(encoding="utf-8") == text
    assert not (tmp_path / "outside.py").exists() and not (tree / ".githooks").exists()


def test_the_repair_is_named_on_the_phases_row(disk: Disk, led: Ledger) -> None:
    """S4: an ok phase and a `failed:budget` one, each with a valid marker, carry `repaired` on their phase event;
    the `phases` row has no column for it."""
    for how in ("ok", "budget"):
        run_id = build(disk, led, Mutating(how=how))
        event = event_of(led, run_id, "phase")
        assert event["repaired"] == REPAIRED and "repair_unverified" not in event, how
        assert committed(disk, led, run_id) == WORK, how
        (phase,) = led.phases_of(run_id)
        assert "repaired" not in phase and "repair_unverified" not in phase, how
        assert phase["agent"] == "builder" and phase["tokens"] == 1234, how


def test_no_marker_nothing_changes(disk: Disk, led: Ledger) -> None:
    """S5: with no marker an ok phase and a dead-harness phase are committed as they were written, the phase event
    has neither key and the ended event is the outcome alone."""
    run_id = build(disk, led, Mutating(how="ok", armed=False))
    assert committed(disk, led, run_id) == WORK
    event = event_of(led, run_id, "phase")
    assert "repaired" not in event and "repair_unverified" not in event

    run_id = build(disk, led, Mutating(how="die-bare", armed=False))
    assert committed(disk, led, run_id) == WORK
    assert event_of(led, run_id, "ended") == {"outcome": "failed:infra"}
