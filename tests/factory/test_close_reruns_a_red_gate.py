"""Card 20 — a flaky check on the merge commit costs close one rerun of the failed jobs, not the run's closure
[2026-09-27].

The properties, and what each test discriminates:

- **R1**: a red gate is rerun once, and close waits for the rerun with a bounded, doubling backoff — the floor
  first, then the doubling, under the cap — never trusting a read taken before the wait.
- **R2**: green after the rerun lets close go on to its later checks exactly as it would on green, and both the
  rerun's conclusions ride on the run's end.
- **R3**: still red after the rerun ends the run `failed:gate` exactly as today, and the two cases that reach it —
  a rerun that stayed red, and a red gate the forge could rerun nothing for — are both told apart on the record.
- **R4**: a rerun the forge refuses, or one that does not finish inside the bound, refuses `close.gate-rerun` and
  leaves the run in flight, so close can be run again.
- **R5**: a green or a pending merge commit asks for no rerun at all, exactly as today.

The forge is a local double scripted to answer `checks()` in order (its last answer repeating), so a poll past the
bound is a lost property, not a hang: it is checked against an allowance rather than trusted to terminate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from isidium.factory import close as close_mod
from isidium.factory.forge import Checks, MergeableState, MergeState
from isidium.factory.ledger import Ledger
from isidium.store.core.refusal import Refusal

from . import test_v5a
from .test_v5a import GREEN, PENDING, RED, Acceptance, Disk, a_run, execution_of, refuses

disk = test_v5a.disk
led = test_v5a.led

# A poll past this many `checks()` reads is a lost bound, not a slow forge — the test fails rather than hangs.
POLL_ALLOWANCE = 64


@dataclass
class ScriptedForge:
    """close's `Reader`, scripted rather than recorded live: `checks()` answers `checks_script` in order, its last
    entry repeating past the end (an unbounded PENDING needs no infinite tuple); `rerun_failed()` records the sha it
    was asked about, then answers `rerun_answer` or raises it when it is a `Refusal`."""

    head: str
    merge: str | None
    checks_script: tuple[Checks, ...]
    rerun_answer: tuple[int, ...] | Refusal = ()
    merged: bool = True
    rerun_calls: list[str] = field(default_factory=list)
    checks_calls: list[str] = field(default_factory=list)

    def merge_state(self, number: int) -> MergeState:
        return MergeState(self.head, True, MergeableState.CLEAN, self.merged, self.merge)

    def checks(self, sha: str) -> Checks:
        self.checks_calls.append(sha)
        if len(self.checks_calls) > POLL_ALLOWANCE:
            raise AssertionError("polled past the test's allowance: the bound was not honoured")
        return self.checks_script[min(len(self.checks_calls) - 1, len(self.checks_script) - 1)]

    def rerun_failed(self, sha: str) -> tuple[int, ...]:
        self.rerun_calls.append(sha)
        if isinstance(self.rerun_answer, Refusal):
            raise self.rerun_answer
        return self.rerun_answer


def _sleep() -> tuple[list[float], Any]:
    slept: list[float] = []

    def sleep(seconds: float) -> None:
        slept.append(seconds)

    return slept, sleep


def test_a_red_gate_is_rerun_once_and_waited_for(disk: Disk, led: Ledger, otel: Any) -> None:
    run = a_run(disk, led, disk.refused)
    forge = ScriptedForge(run.head, run.merge, checks_script=(RED, PENDING, PENDING, GREEN), rerun_answer=(9001,))
    slept, sleep = _sleep()
    acc = Acceptance()
    otel.clear()
    out = close_mod.close(disk.ctx, led, disk.call, forge, run_id=run.run_id, pr=7, accept=acc, sleep=sleep)
    assert out["outcome"] == "closed"
    assert forge.rerun_calls == [run.merge]
    assert slept == [15.0, 30.0, 60.0]
    assert len(forge.checks_calls) == 4, "the initial read, plus one poll per scripted answer"
    [sp] = otel.spans(close_mod.RERUN_SPAN)
    assert sp.attributes[close_mod.RERUN_WORKFLOWS] == 1
    assert sp.attributes[close_mod.RERUN_JOBS] == 1
    assert sp.attributes[close_mod.RERUN_POLLS] == 3


def test_green_after_the_rerun_closes_and_records_it(disk: Disk, led: Ledger) -> None:
    run = a_run(disk, led, disk.refused)
    forge = ScriptedForge(run.head, run.merge, checks_script=(RED, GREEN), rerun_answer=(4242,))
    slept, sleep = _sleep()
    acc = Acceptance()
    out = close_mod.close(disk.ctx, led, disk.call, forge, run_id=run.run_id, pr=7, accept=acc, sleep=sleep)
    assert out["outcome"] == "closed" and acc.seen != [], "close went on to its later checks"
    assert slept == [15.0]
    [ended] = [e for e in led.events_of(run.run_id) if e["kind"] == "ended"]
    rerun = ended["data"]["rerun"]
    assert rerun["workflows"] == [4242]
    assert rerun["jobs"] == [{"job": "green-bar", "first": "failure", "second": "success"}]


def test_still_red_after_the_rerun_ends_failed_gate(disk: Disk, led: Ledger) -> None:
    stayed_red = a_run(disk, led, disk.refused)
    forge_a = ScriptedForge(stayed_red.head, stayed_red.merge, checks_script=(RED, RED), rerun_answer=(777,))
    acc_a = Acceptance()
    out_a = close_mod.close(
        disk.ctx, led, disk.call, forge_a, run_id=stayed_red.run_id, pr=7, accept=acc_a, sleep=_sleep()[1]
    )
    assert out_a["outcome"] == "failed:gate" and acc_a.seen == []
    assert forge_a.rerun_calls == [stayed_red.merge]
    assert execution_of(disk, disk.refused) == "failed(gate)"
    [ended_a] = [e for e in led.events_of(stayed_red.run_id) if e["kind"] == "ended"]
    assert ended_a["data"]["rerun"]["jobs"] == [{"job": "green-bar", "first": "failure", "second": "failure"}]

    unrerunnable = a_run(disk, led, disk.refused)
    forge_b = ScriptedForge(unrerunnable.head, unrerunnable.merge, checks_script=(RED,), rerun_answer=())
    slept_b, sleep_b = _sleep()
    acc_b = Acceptance()
    out_b = close_mod.close(
        disk.ctx, led, disk.call, forge_b, run_id=unrerunnable.run_id, pr=7, accept=acc_b, sleep=sleep_b
    )
    assert out_b["outcome"] == "failed:gate" and slept_b == [] and len(forge_b.checks_calls) == 1
    [ended_b] = [e for e in led.events_of(unrerunnable.run_id) if e["kind"] == "ended"]
    assert ended_b["data"]["rerun"] == {
        "workflows": [],
        "jobs": [{"job": "green-bar", "first": "failure", "second": None}],
    }


def test_a_refused_or_unfinished_rerun_refuses_without_ending_the_run(disk: Disk, led: Ledger) -> None:
    forbidden = a_run(disk, led, disk.refused)
    refusal = Refusal("forge.api", "actions/runs", "403: Resource not accessible by integration")
    forge_a = ScriptedForge(forbidden.head, forbidden.merge, checks_script=(RED,), rerun_answer=refusal)
    slept_a, sleep_a = _sleep()
    acc_a = Acceptance()
    refuses(
        "close.gate-rerun",
        lambda: close_mod.close(
            disk.ctx, led, disk.call, forge_a, run_id=forbidden.run_id, pr=7, accept=acc_a, sleep=sleep_a
        ),
    )
    row_a = led.run(forbidden.run_id)
    assert row_a is not None and row_a["ended_at"] is None and acc_a.seen == [] and slept_a == []
    assert len(led.phases_of(forbidden.run_id)) == 1, "no recovered phase row from a refused rerun"

    stuck = a_run(disk, led, disk.refused)
    forge_b = ScriptedForge(stuck.head, stuck.merge, checks_script=(RED, PENDING), rerun_answer=(555,))
    slept_b, sleep_b = _sleep()
    acc_b = Acceptance()
    refuses(
        "close.gate-rerun",
        lambda: close_mod.close(
            disk.ctx, led, disk.call, forge_b, run_id=stuck.run_id, pr=7, accept=acc_b, sleep=sleep_b
        ),
    )
    row_b = led.run(stuck.run_id)
    assert row_b is not None and row_b["ended_at"] is None and acc_b.seen == []
    assert sum(slept_b) <= close_mod.RERUN_BOUND_S
    assert len(forge_b.checks_calls) <= POLL_ALLOWANCE


def test_green_or_pending_is_handled_as_today(disk: Disk, led: Ledger) -> None:
    green = a_run(disk, led, disk.refused)
    forge_green = ScriptedForge(green.head, green.merge, checks_script=(GREEN,))
    slept_g, sleep_g = _sleep()
    out = close_mod.close(
        disk.ctx, led, disk.call, forge_green, run_id=green.run_id, pr=7, accept=Acceptance(), sleep=sleep_g
    )
    assert out["outcome"] == "closed" and forge_green.rerun_calls == [] and slept_g == []

    pending = a_run(disk, led, disk.refused)
    forge_pending = ScriptedForge(pending.head, pending.merge, checks_script=(PENDING,))
    slept_p, sleep_p = _sleep()
    refuses(
        "close.gate-pending",
        lambda: close_mod.close(
            disk.ctx, led, disk.call, forge_pending, run_id=pending.run_id, pr=7, accept=Acceptance(), sleep=sleep_p
        ),
    )
    assert forge_pending.rerun_calls == [] and slept_p == []
