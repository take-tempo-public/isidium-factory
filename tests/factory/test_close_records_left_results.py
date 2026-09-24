"""Card 12 — a phase's result left on disk reaches the ledger when its run ends, so a crashed host's spend is
recorded [2026-09-24].

The properties, and what each test discriminates:

- **R1**: a readable, unrecorded result in the run directory becomes that phase's row before the end, with the six
  values the row takes, and the `ended` detail names it `recorded`. The artifact path frame (run-directory-relative
  on disk, deploy-home-relative on the record), the guard's own block count and an empty `touched` are all asserted,
  not merely that a row exists.
- **R2**: the end takes the recorded result's billing class only when the row held none; a row that already holds
  one keeps it, even though the result underneath it is still recorded.
- **R3**: a result that will not parse, and one that parses but does not validate, are both named in the `ended`
  detail's `unreadable`, and the run still ends — beside a valid neighbour that IS recorded, so the two paths are
  told apart.
- **R4**: a phase name the ledger already holds a row for is skipped unopened; a later round of the same phase
  (`plan-2`) is not, because the dedupe is by occurrence and the `phases` table holds no round column.
- **Every end close writes recovers first**, not only the abandoning one: a failing close and a green close both
  gain the left phase's row before their own write, and the green close's `complete` event sums the recovered spend
  in with what was already on the ledger.
- **A recovered `judge` carries its verdict**, re-hashed before it is trusted: a verdict artifact whose bytes moved
  after the result named its hash is not recorded, named instead, and the run still ends.

The abandoning end is the cheap harness for the manifest's rule tests (S1, S2, S5, S3, S4): no forge, no merge, no
acceptance, just a dispatched run and a card the store answers as withdrawn. The two tests beyond the manifest reuse
V5a's `a_run` / `close_run` for the failed and green ends, and for the judge's verdict row.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

from isidium.factory import artifacts as artifacts_mod
from isidium.factory import close as close_mod
from isidium.factory.ledger import Ledger
from isidium.store.core.refusal import Refusal

from ..store.conftest import git
from . import test_v5a
from .test_v4a import _harness_result
from .test_v5a import Disk

# V5a's module-scoped harness, aliased rather than imported by name (an `import` alone is F401 under this repo's
# ruff select): this module gets its own store-on-disk and checkout, one per test module by pytest's own scoping —
# the cost of reuse over hand-building a `TenantContext`, which cannot reach the failed and closed ends at all.
disk = test_v5a.disk
led = test_v5a.led


class NoForge:
    """A close that abandons a run reads no forge at all — a double that fails the test if it is wrong."""

    def merge_state(self, number: int) -> Any:
        raise AssertionError("an abandoning close reads no forge")

    def checks(self, sha: str) -> Any:
        raise AssertionError("an abandoning close reads no forge")


def _withdrawn(disk: Disk) -> Any:
    """`close`'s one `show` read, answered as a withdrawn card — the abandoning end, needing no forge, no merge and
    no acceptance."""

    def call(name: str, args: Any) -> Any:
        out = disk.call(name, args)
        if name == "show":
            out = {**out, "head": {**out["head"], "status": "withdrawn"}}
        return out

    return call


def _bare_run(disk: Disk, led: Ledger, cid: int) -> str:
    """A run dispatched and never advanced — everything the abandoning end needs, and nothing this card's recovery
    does not exercise."""
    base = git(disk.work, "rev-parse", "HEAD").strip()
    return led.dispatch(
        dataclasses.replace(test_v5a.new_run(cid), build_hash=test_v5a.build_of(disk, cid), base_sha=base)
    )


def _write_left(disk: Disk, run_id: str, step: str, blocks: int = 0, **over: Any) -> Path:
    """A step directory holding a `result.json` as the container adapter would have left it, and — when `blocks` is
    given — a `blocks.jsonl` the guard's own count reads."""
    rundir = disk.home / "runs" / run_id / step
    rundir.mkdir(parents=True, exist_ok=True)
    (rundir / close_mod.RESULT).write_text(json.dumps(_harness_result(**over)), encoding="utf-8")
    if blocks:
        lines = "".join(json.dumps({"path": "outside", "reason": "outside"}) + "\n" for _ in range(blocks))
        (rundir / close_mod.BLOCKS).write_text(lines, encoding="utf-8")
    return rundir


def _write_verdict(rundir: Path, verdict: str = "revise", reasoning: str = "because") -> dict[str, str]:
    """A judge's verdict artifact, on disk at its own hash — the entry a result names it by, run-directory-relative
    as the container writes one."""
    data = artifacts_mod.canonical({"verdict": verdict, "reasoning": reasoning})
    (rundir / "verdict.json").write_bytes(data)
    return {"name": "verdict", "sha256": artifacts_mod.sha256(data), "path": "verdict.json"}


# --------------------------------------------------------------------------------------- the manifest's five tests


def test_an_abandoned_run_records_the_result_its_host_left(disk: Disk, led: Ledger) -> None:
    run_id = _bare_run(disk, led, disk.refused)
    _write_left(
        disk,
        run_id,
        "plan",
        blocks=2,
        phase="plan",
        agent="plan-author",
        effort="high",
        tokens=23312,
        cost_micro=1428893,
        duration_ms=21 * 60 * 1000,
        artifacts=[{"name": "plan", "sha256": "sha256:" + "a" * 64, "path": "plan.json"}],
    )
    out = close_mod.close(disk.ctx, led, _withdrawn(disk), NoForge(), run_id=run_id)
    assert out["outcome"] == "abandoned" and out["land"]["sent"] == 0

    [row] = led.phases_of(run_id)
    assert row["phase"] == "plan" and row["agent"] == "plan-author" and row["effort"] == "high"
    assert row["prompt_version"] == "v1"
    assert (row["tokens"], row["cost_micro"], row["duration_ms"]) == (23312, 1428893, 21 * 60 * 1000)

    [ended] = [e for e in led.events_of(run_id) if e["kind"] == "ended"]
    assert ended["data"]["recorded"] == ["plan"] and "unreadable" not in ended["data"]

    [phase_ev] = [e for e in led.events_of(run_id) if e["kind"] == "phase"]
    assert phase_ev["data"]["artifacts"] == [
        {"name": "plan", "sha256": "sha256:" + "a" * 64, "path": f"runs/{run_id}/plan/plan.json"}
    ]
    assert phase_ev["data"]["guard_blocks"] == 2
    assert phase_ev["data"]["touched"] == []


def test_the_end_takes_the_recorded_results_billing_class(disk: Disk, led: Ledger) -> None:
    run_id = _bare_run(disk, led, disk.refused)
    _write_left(disk, run_id, "plan", phase="plan", agent="plan-author", billing_class="metered")
    close_mod.close(disk.ctx, led, _withdrawn(disk), NoForge(), run_id=run_id)
    row = led.run(run_id)
    assert row is not None and row["billing_class"] == "metered"
    assert [p["phase"] for p in led.phases_of(run_id)] == ["plan"]


def test_a_row_that_holds_a_billing_class_keeps_it(disk: Disk, led: Ledger) -> None:
    run_id = _bare_run(disk, led, disk.refused)
    led.advance(run_id, "f" * 40, [], "metered")
    _write_left(disk, run_id, "plan", phase="plan", agent="plan-author", billing_class="plan")
    close_mod.close(disk.ctx, led, _withdrawn(disk), NoForge(), run_id=run_id)
    row = led.run(run_id)
    # The discriminator is both halves: a fix that passed the recorded class unconditionally fails the first, and one
    # that recorded nothing at all fails the second.
    assert row is not None and row["billing_class"] == "metered"
    assert [p["phase"] for p in led.phases_of(run_id)] == ["plan"]


def test_an_unreadable_result_is_named_and_the_run_still_ends(disk: Disk, led: Ledger) -> None:
    run_id = _bare_run(disk, led, disk.refused)
    truncated = disk.home / "runs" / run_id / "plan"
    truncated.mkdir(parents=True)
    (truncated / close_mod.RESULT).write_text("{not json", encoding="utf-8")
    invalid = disk.home / "runs" / run_id / "refute"
    invalid.mkdir(parents=True)
    (invalid / close_mod.RESULT).write_text(
        json.dumps(_harness_result(phase="refute", agent="plan-refuter", effort="not-a-real-effort")),
        encoding="utf-8",
    )
    _write_left(disk, run_id, "build")  # the valid neighbour: recorded, told apart from the two that are not

    out = close_mod.close(disk.ctx, led, _withdrawn(disk), NoForge(), run_id=run_id)
    assert out["outcome"] == "abandoned" and out["ended_at"]

    [ended] = [e for e in led.events_of(run_id) if e["kind"] == "ended"]
    assert sorted(ended["data"]["unreadable"]) == [
        f"runs/{run_id}/plan/result.json",
        f"runs/{run_id}/refute/result.json",
    ]
    assert [p["phase"] for p in led.phases_of(run_id)] == ["build"]


def test_a_phase_already_recorded_is_not_recorded_twice(disk: Disk, led: Ledger) -> None:
    run_id = _bare_run(disk, led, disk.refused)
    led.phase(run_id, test_v5a.AT, _harness_result(phase="plan", agent="plan-author", cost_micro=100))
    _write_left(disk, run_id, "plan", phase="plan", agent="plan-author", cost_micro=999)  # already held: skipped
    _write_left(disk, run_id, "plan-2", phase="plan", agent="plan-author", cost_micro=222)  # a revision: not held

    close_mod.close(disk.ctx, led, _withdrawn(disk), NoForge(), run_id=run_id)
    rows = led.phases_of(run_id)
    assert [r["cost_micro"] for r in rows] == [100, 222], "the held row untouched, the revision recorded beside it"

    r = test_v5a.refuses(
        "close.ended", lambda: close_mod.close(disk.ctx, led, _withdrawn(disk), NoForge(), run_id=run_id)
    )
    assert isinstance(r, Refusal)
    assert len(led.phases_of(run_id)) == 2, "no further row from a close that itself refused"


# ------------------------------------------------------------------------------------- beyond the manifest: F2, A1


def test_the_failed_and_the_green_end_record_what_was_left_too(disk: Disk, led: Ledger) -> None:
    """The card's own scope line: *"on every end it writes (abandoned, failed, closed)"*. Without this, a fix wired
    only into the abandoning end passes every test above."""
    failing = test_v5a.a_run(disk, led, disk.refused, build="sha256:" + "0" * 64)
    _write_left(disk, failing.run_id, "plan", phase="plan", agent="plan-author", cost_micro=50, duration_ms=0)
    out = test_v5a.close_run(disk, led, failing, accept=test_v5a.Acceptance())
    assert out["outcome"] == "failed:card-drift"
    [ended] = [e for e in led.events_of(failing.run_id) if e["kind"] == "ended"]
    assert sorted(ended["data"]["phases"]) == ["build", "plan"]
    assert sorted(p["phase"] for p in led.phases_of(failing.run_id)) == ["build", "plan"]

    green = test_v5a.a_run(disk, led, disk.factory)
    _write_left(disk, green.run_id, "plan", phase="plan", agent="plan-author", cost_micro=50, duration_ms=0)
    out2 = test_v5a.close_run(disk, led, green)
    assert out2["outcome"] == "closed"
    [complete] = [e for e in disk.store.events if e["kind"] == "complete" and int(e["card"]) == disk.factory]
    # The load-bearing half: 350, not 300 — the recovered row was written *before* the sum was taken, which is R1's
    # own "first" (a fix that recorded after summing would still read 300 here).
    assert complete["cost_micro"] == 350


def test_a_recovered_judge_carries_its_verdict_and_one_whose_artifact_moved_is_named(disk: Disk, led: Ledger) -> None:
    ok_run = _bare_run(disk, led, disk.refused)
    ok_dir = disk.home / "runs" / ok_run / "judge"
    ok_dir.mkdir(parents=True)
    art = _write_verdict(ok_dir, verdict="revise", reasoning="the plan misses the concurrent case")
    _write_left(disk, ok_run, "judge", phase="judge", agent="judge", artifacts=[art])

    close_mod.close(disk.ctx, led, _withdrawn(disk), NoForge(), run_id=ok_run)
    assert [p["phase"] for p in led.phases_of(ok_run)] == ["judge"]
    [verdict_row] = led.verdicts_of(ok_run)
    assert verdict_row["verdict"] == "revise" and verdict_row["reasoning"] == art["sha256"]

    bad_run = _bare_run(disk, led, disk.refused)
    bad_dir = disk.home / "runs" / bad_run / "judge"
    bad_dir.mkdir(parents=True)
    art2 = _write_verdict(bad_dir, verdict="approve", reasoning="looks fine")
    _write_left(disk, bad_run, "judge", phase="judge", agent="judge", artifacts=[art2])
    (bad_dir / "verdict.json").write_bytes(b"tampered bytes, not what the hash names")

    out = close_mod.close(disk.ctx, led, _withdrawn(disk), NoForge(), run_id=bad_run)
    assert out["outcome"] == "abandoned"
    assert led.phases_of(bad_run) == [] and led.verdicts_of(bad_run) == []
    [ended] = [e for e in led.events_of(bad_run) if e["kind"] == "ended"]
    assert ended["data"]["unreadable"] == [f"runs/{bad_run}/judge/verdict.json"]
