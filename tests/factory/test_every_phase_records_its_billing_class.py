"""Card 16 — every phase that ends records the billing class it drew on, so a parked or read-only run is not left
unbilled [2026-09-27].

Found on `r-13` (2026-09-24): it parked after six read-only phases, and its run row read `billing_class` null,
because the runner only ever wrote a class through `advance`, when a phase committed. The plan, refute and judge
phases commit nothing, and `_park` ended the run with no class of its own.

The properties, and what each test discriminates:

- **R1**: a phase that ends ok and commits nothing (every read-only phase) records its class on the run's row —
  through `Ledger.bill`, the write `advance` is not, because `advance` would blank a head or a surfaces set a
  phase with no commit does not have.
- **R2**: a run the plan gate parks ends with the class its phases recorded — `_park`'s `ledger.end` passes none,
  and `_end`'s `COALESCE` preserves what an earlier phase wrote.
- **R3**: a read-only phase that wrote outside its surfaces ends the run with the *adapter's* billing class
  (`drv.capabilities().billing_class`), not the phase result's own — the one end C1 names as the exception.
- **R4**: recording a class never changes the run's head or the surfaces it touched.

`Metered` is the one fake that can tell C1's two sources apart: its result answers `metered` while its capability
row still answers `plan` (inherited from `Fake`). Every other fake in this suite agrees on both, so without this
divergence neither S1 nor S3 could show which source the runner actually read. It is not a conformance suite member
— the suite's members are the explicit list in `test_v4a.py`'s own conformance tests — so this divergence is safe.
"""

from __future__ import annotations

from dataclasses import dataclass

from isidium.factory import adapter as adapter_mod
from isidium.factory.adapter import PhaseResult, RunJob
from isidium.factory.ledger import Ledger

from .test_v4a import INSIDE, Disk, disk, fresh_run, refuses
from .test_v4a_ii import ANSWERS, Shaped, chain, led, one, verdict

__all__ = ["disk", "led"]  # the V4a tenant and its ledger fixture, re-exported so pytest can resolve them


@dataclass
class Metered(Shaped):
    """A phase that says `metered` while its capability row still says `plan` — the divergence that makes C1's rule
    and its exception tell apart from each other rather than both reading the same value by accident."""

    def execute(self, job: RunJob) -> PhaseResult:
        res = super().execute(job)
        return adapter_mod.result({**res.row(), "billing_class": "metered"})


def test_a_read_only_phase_records_its_billing_class(disk: Disk, led: Ledger) -> None:
    run_id = fresh_run(disk, led)
    one(disk, led, run_id, "plan", Metered(home=disk.home))
    row = led.run(run_id)
    assert row is not None and row["billing_class"] == "metered"
    assert [p["phase"] for p in led.phases_of(run_id)] == ["plan"]


def test_a_parked_run_reads_its_phases_billing_class(disk: Disk, led: Ledger) -> None:
    """r-13's own defect: six read-only phases and a park, and the row is billed rather than null."""
    run_id = fresh_run(disk, led)
    drv = Metered(home=disk.home, answers={**ANSWERS, "judge": [verdict("revise"), verdict("revise")]})
    row = chain(disk, led, run_id, drv)
    assert row["outcome"] == "parked" and row["billing_class"] == "metered"


def test_a_read_only_scope_failure_carries_the_billing_class(disk: Disk, led: Ledger) -> None:
    run_id = fresh_run(disk, led)
    refuses(
        "run.read-only",
        lambda: one(disk, led, run_id, "plan", Metered(home=disk.home, writes_in="plan")),
    )
    row = led.run(run_id)
    assert row is not None and row["outcome"] == "failed:scope" and row["billing_class"] == "plan"
    assert row["head_sha"] is None


def test_recording_the_class_leaves_the_head_and_surfaces_alone(disk: Disk, led: Ledger) -> None:
    run_id = fresh_run(disk, led)
    led.advance(run_id, "d" * 40, [INSIDE], None)
    one(disk, led, run_id, "plan", Metered(home=disk.home))
    row = led.run(run_id)
    assert row is not None
    assert row["head_sha"] == "d" * 40
    assert row["surfaces_actual"] == [INSIDE]
    assert row["billing_class"] == "metered"
