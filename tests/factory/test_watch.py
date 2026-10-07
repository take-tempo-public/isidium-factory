"""Card 31: the PR watcher -- one pass that reads every open run's pull request and acts through the existing verbs,
never merging.

`decide` is tested directly for its table (it is pure); `watch_once` for what a pass does around it -- the leases, the
log, the verbs, the spans -- over a real ledger, a scripted `Watched` double that also *refuses* every forge call the
watcher must never make, and verbs that record their calls. One test drives the CLI over the V4a tenant, as card 28's do.
Times are explicit aware datetimes, a whole second or more from every boundary.
"""

from __future__ import annotations

import builtins
import inspect
import json
import socket
import sqlite3
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from typer.testing import CliRunner

from isidium.factory import cli as cli_mod
from isidium.factory import close as close_mod
from isidium.factory import github as github_mod
from isidium.factory import ledger as ledger_mod
from isidium.factory import runner as runner_mod
from isidium.factory import watch
from isidium.factory.forge import CheckRun, Checks, MergeableState, MergeState
from isidium.factory.ledger import Ledger, NewRun
from isidium.factory.watch import Close, Fixup, Flag, Past, Policy, Rerun, Verb, Verbs, View
from isidium.store.core.refusal import Refusal

from .test_v4a import ROOT, TENANT, Disk, disk, fresh_run
from .test_v4a_ii import led

__all__ = ["disk", "led"]  # the V4a tenant and its ledger, as test_v4a_ii builds them

T = datetime(2026, 10, 4, 12, 0, 0, tzinfo=UTC)
LATER = T + timedelta(hours=2)
H1, H2, F1 = "1" * 40, "2" * 40, "f" * 40
NEEDED = ("green-bar",)
CAN_FIXUP = Policy(fixup=True, fixup_per_day=5)


# ------------------------------------------------------------------------------------------------ fixtures and doubles


def _stamp(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _state(
    head: str, state: MergeableState = MergeableState.CLEAN, merged: bool = False, mergeable: bool | None = True
) -> MergeState:
    return MergeState(head, mergeable, state, merged, "m" * 40 if merged else None)


def _checks(conclusion: str | None) -> Checks:
    """The one required check, completed with `conclusion` -- `None` is still running."""
    if conclusion is None:
        return Checks(NEEDED, (CheckRun("green-bar", "in_progress", None),))
    return Checks(NEEDED, (CheckRun("green-bar", "completed", conclusion),))


RED, GREEN = _checks("failure"), _checks("success")


def _past(
    action: str = "close",
    head: str | None = H1,
    outcome: str | None = watch.RERUN,
    holder: str = "watcher",
    expires: datetime = T - timedelta(hours=1),
    released: bool = True,
) -> Past:
    return Past(action, head, holder, expires, "released" if released else None, outcome)


def _view(
    run_id: str = "r-1",
    state: MergeState | None = None,
    checks: Checks | None = RED,
    head: str | None = H1,
    past: tuple[Past, ...] = (),
) -> View:
    return View(run_id, head, 7, state or _state(H1), checks, past)


def _new() -> NewRun:
    return NewRun(
        card=31,
        lane="standard",
        build_hash="sha256:b",
        base_sha="a" * 40,
        adapter="container",
        dispatched_at="2026-10-04T11:00:00Z",
        payload_hash="sha256:p",
        config_hash="sha256:c",
        identity="isdm-fac-lander[bot]",
    )


def _ledger(tmp_path: Path) -> Ledger:
    return Ledger(tmp_path / "ledger.sqlite", "tenant-x")


_PRS = iter(range(100, 10_000))


def _open_run(led_: Ledger, head: str = H1) -> tuple[str, int]:
    """An in-flight run with a pull request and a head, the way `pr-open` and a phase leave one."""
    run_id = led_.dispatch(_new())
    number = next(_PRS)
    led_.set_pr(run_id, number)
    led_.advance(run_id, head, [], None)
    return run_id, number


def _taken(led_: Ledger, run_id: str, action: Any, holder: Any, head: str | None, at: datetime, outcome: str) -> None:
    """A lease on record, taken at `at` and released with `outcome` -- the history `decide` reads back."""
    lease = led_.take_lease(run_id, action, holder, head, at, 60)
    led_.release_lease(lease, at + timedelta(seconds=5), outcome)


def _leases(led_: Ledger, run_id: str) -> list[dict[str, Any]]:
    rows = led_.db.execute("SELECT * FROM leases WHERE run_id = ? ORDER BY rowid", (run_id,)).fetchall()
    return [dict(r) for r in rows]


@dataclass
class Forged:
    """A `Watched` that answers from scripts and records every call; and, as a real `Forge` would, offers every call the
    watcher must never make -- each of which fails the test it is made in."""

    states: dict[int, MergeState] = field(default_factory=dict)
    checks_of: dict[str, Checks] = field(default_factory=dict)
    calls: list[tuple[str, Any]] = field(default_factory=list)
    on_read: Callable[[int], None] | None = None

    def merge_state(self, number: int) -> MergeState:
        self.calls.append(("merge_state", number))
        if self.on_read is not None:
            self.on_read(number)
        return self.states[number]

    def checks(self, sha: str) -> Checks:
        self.calls.append(("checks", sha))
        return self.checks_of[sha]

    def rerun_failed(self, sha: str) -> tuple[int, ...]:
        self.calls.append(("rerun_failed", sha))
        return (1,)

    def named(self, call: str) -> list[Any]:
        return [arg for name, arg in self.calls if name == call]

    def _never(self, name: str) -> Any:
        raise AssertionError(f"the watcher called the forge's {name}")

    def push(self, *a: Any, **k: Any) -> Any:
        return self._never("push")

    def open_pr(self, *a: Any, **k: Any) -> Any:
        return self._never("open_pr")

    def branch(self, *a: Any, **k: Any) -> Any:
        return self._never("branch")

    def fetch(self, *a: Any, **k: Any) -> Any:
        return self._never("fetch")

    def merge(self, *a: Any, **k: Any) -> Any:
        return self._never("merge")

    def failed_jobs(self, *a: Any, **k: Any) -> Any:
        return self._never("failed_jobs")

    def changed(self, *a: Any, **k: Any) -> Any:
        return self._never("changed")

    def capabilities(self, *a: Any, **k: Any) -> Any:
        return self._never("capabilities")


@dataclass
class Spy:
    """A verb that records the runs it was called for. `refuse` maps a run to the rule it refuses with."""

    outcome: str
    calls: list[str] = field(default_factory=list)
    refuse: dict[str, str] = field(default_factory=dict)

    def run(self, run_id: str) -> Mapping[str, Any]:
        self.calls.append(run_id)
        if run_id in self.refuse:
            raise Refusal(self.refuse[run_id], run_id, "refused by the verb")
        return {"outcome": self.outcome}


def _verbs(close: Spy, fixup: Spy) -> Verbs:
    return Verbs(Verb(close.run, lambda: 3600.0), Verb(fixup.run, lambda: 7200.0))


def _pass(
    led_: Ledger,
    forge: Forged,
    tmp_path: Path,
    close: Spy | None = None,
    fixup: Spy | None = None,
    policy: Policy | None = CAN_FIXUP,
    at: datetime = T,
) -> watch.Summary:
    verbs = _verbs(close or Spy("closed"), fixup or Spy("dispatched"))
    return watch.watch_once(led_, forge, policy, verbs, tmp_path / watch.LOG_FILE, lambda: at)


def _log(tmp_path: Path) -> list[dict[str, Any]]:
    path = tmp_path / watch.LOG_FILE
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


# --------------------------------------------------------------------------------------------------------- R2 / S1


def test_a_merged_pr_is_closed(tmp_path: Path) -> None:
    assert watch.decide([_view(state=_state(H1, merged=True))], 0, CAN_FIXUP, T) == (Close("r-1", H1),)
    assert watch.decide([_view(state=_state(H1), checks=GREEN)], 0, CAN_FIXUP, T) == (), "green and open: nothing"

    led_ = _ledger(tmp_path)
    try:
        run_id, pr = _open_run(led_)
        forge = Forged(states={pr: _state(H1, merged=True)})
        close, fixup = Spy("closed"), Spy("dispatched")
        summary = _pass(led_, forge, tmp_path, close, fixup)

        assert close.calls == [run_id] and fixup.calls == []
        (lease,) = _leases(led_, run_id)
        assert (lease["action"], lease["holder"], lease["head_sha"]) == ("close", "watcher", H1)
        assert lease["outcome"] == "closed" and lease["released_at"] is not None
        assert lease["expires_at"] == _stamp(T + timedelta(seconds=3600)), "the verb's own bound"
        assert forge.named("checks") == [], "a merged pull request's checks are not read"
        assert [(r["run"], r["action"], r["outcome"]) for r in _log(tmp_path)] == [(run_id, "close", "closed")]
        assert summary.closed == 1 and summary.open == 1
    finally:
        led_.close()


# --------------------------------------------------------------------------------------------------------- R2 / S2


def test_stale_or_conflicted_is_flagged(tmp_path: Path) -> None:
    behind = _view("r-1", _state(H1, MergeableState.BEHIND, mergeable=True))
    dirty = _view("r-2", _state(H2, MergeableState.DIRTY, mergeable=False))
    assert watch.decide([behind], 0, CAN_FIXUP, T) == (Flag("r-1", H1, "stale"),), (
        "red, no rerun yet, and still just a flag"
    )
    assert watch.decide([dirty], 0, CAN_FIXUP, T) == (Flag("r-2", H2, "conflicted"),)

    led_ = _ledger(tmp_path)
    try:
        a, pa = _open_run(led_, H1)
        b, pb = _open_run(led_, H2)
        forge = Forged(
            states={pa: _state(H1, MergeableState.BEHIND), pb: _state(H2, MergeableState.DIRTY, mergeable=False)}
        )
        close, fixup = Spy("closed"), Spy("dispatched")
        summary = _pass(led_, forge, tmp_path, close, fixup)

        assert close.calls == [] and fixup.calls == [] and forge.named("rerun_failed") == []
        assert forge.named("checks") == [] and _leases(led_, a) == [] and _leases(led_, b) == []
        assert [(r["run"], r["head"], r["action"], r["kind"]) for r in _log(tmp_path)] == [
            (a, H1, "flag", "stale"),
            (b, H2, "flag", "conflicted"),
        ]
        assert summary.flags == 2
    finally:
        led_.close()


# --------------------------------------------------------------------------------------------------------- R3 / S3


def test_a_red_head_is_rerun_once_first(tmp_path: Path) -> None:
    assert watch.decide([_view()], 0, CAN_FIXUP, T) == (Rerun("r-1", H1),)
    older = (_past(head=H2),)
    assert watch.decide([_view(past=older)], 0, CAN_FIXUP, T) == (Rerun("r-1", H1),), (
        "a rerun at another head is not this head's"
    )
    assert watch.decide([_view(past=(_past(outcome="closed"),))], 0, CAN_FIXUP, T) == (Rerun("r-1", H1),), (
        "only a rerun is a rerun"
    )
    assert watch.decide([_view(past=(_past(),))], 0, CAN_FIXUP, T) == (Fixup("r-1", H1),)

    led_ = _ledger(tmp_path)
    try:
        run_id, pr = _open_run(led_)
        forge = Forged(states={pr: _state(H1)}, checks_of={H1: RED})
        fixup = Spy("dispatched")

        first = _pass(led_, forge, tmp_path, fixup=fixup)
        assert forge.named("rerun_failed") == [H1] and fixup.calls == [] and first.reran == 1
        (lease,) = _leases(led_, run_id)
        assert (lease["action"], lease["holder"], lease["head_sha"], lease["outcome"]) == (
            "close",
            "watcher",
            H1,
            "rerun",
        )

        second = _pass(led_, forge, tmp_path, fixup=fixup, at=T + timedelta(minutes=15))
        assert forge.named("rerun_failed") == [H1], "one rerun per head"
        assert fixup.calls == [run_id] and second.fixed == 1
        assert [r["action"] for r in _log(tmp_path)] == ["rerun", "fixup"]
    finally:
        led_.close()


# --------------------------------------------------------------------------------------------------------- R3 / S4


def test_a_fixup_past_the_ceiling_is_flagged(tmp_path: Path) -> None:
    one = Policy(fixup=True, fixup_per_day=1)
    reran = (_past(),)
    assert watch.decide([_view(past=reran)], 1, one, T) == (Flag("r-1", H1, "red"),), "the day's ceiling is met"
    assert watch.decide([_view(past=reran)], 0, one, T) == (Fixup("r-1", H1),)
    two = [_view("r-1", past=reran), _view("r-2", past=reran)]
    assert watch.decide(two, 0, one, T) == (Fixup("r-1", H1), Flag("r-2", H1, "red")), (
        "one pass cannot pass the ceiling"
    )
    assert watch.decide([_view(past=reran)], 0, Policy(False, 5), T) == (Flag("r-1", H1, "red"),)

    for name, taken_at, chosen in (
        ("yesterday", datetime(2026, 10, 3, 23, 59, 30, tzinfo=UTC), True),
        ("today", datetime(2026, 10, 4, 0, 0, 30, tzinfo=UTC), False),
    ):
        home = tmp_path / name
        home.mkdir()
        led_ = _ledger(home)
        try:
            run_id, pr = _open_run(led_)
            _taken(led_, run_id, "close", "watcher", H1, T - timedelta(hours=1), watch.RERUN)
            other = led_.dispatch(_new())  # holds the day's other take; no pull request, so it is not an open run
            _taken(led_, other, "fixup", "watcher", None, taken_at, "run.fixup-nothing-red")
            fixup = Spy("dispatched")

            _pass(led_, Forged(states={pr: _state(H1)}, checks_of={H1: RED}), home, fixup=fixup, policy=one)
            assert fixup.calls == ([run_id] if chosen else []), name
            assert [r["kind"] for r in _log(home) if r["action"] == "flag"] == ([] if chosen else ["red"]), name
        finally:
            led_.close()


# --------------------------------------------------------------------------------------------------------- R3 / S5


def test_red_after_the_fixup_ends_and_is_flagged(tmp_path: Path) -> None:
    ran = _past("fixup", H1, ledger_mod.DISPATCHED, holder="operator")
    pushed = _view(state=_state(H2), head=H2, past=(ran,))
    assert watch.decide([pushed], 0, CAN_FIXUP, T) == (Rerun("r-1", H2),), "a new head is rerun first"
    rerun = (ran, _past(head=H2))
    again = _view(state=_state(H2), head=H2, past=rerun)
    assert watch.decide([again], 9, CAN_FIXUP, T) == (Fixup("r-1", H2), Flag("r-1", H2, "red-after-fixup")), (
        "no ceiling"
    )
    assert watch.decide([again], 0, Policy(False, 0), T) == (Fixup("r-1", H2), Flag("r-1", H2, "red-after-fixup")), (
        "the verb spends nothing, so the opt-in does not ration it (card 35 R3)"
    )
    unpushed = _view(state=_state(H1), head=F1, past=(ran, _past(head=H1)))
    assert watch.decide([unpushed], 0, CAN_FIXUP, T) == (Flag("r-1", H1, "unpushed"),)
    refused = _past("fixup", H1, "run.fixup-nothing-red", holder="operator")
    assert watch.decide([_view(past=(refused, _past()))], 0, CAN_FIXUP, T) == (Fixup("r-1", H1),), (
        "a refused fixup is not a fixup"
    )

    led_ = _ledger(tmp_path)
    try:
        run_id, pr = _open_run(led_, H2)
        _taken(led_, run_id, "fixup", "operator", H1, T - timedelta(hours=3), ledger_mod.DISPATCHED)
        _taken(led_, run_id, "close", "watcher", H2, T - timedelta(hours=1), watch.RERUN)
        forge = Forged(states={pr: _state(H2)}, checks_of={H2: RED})
        fixup = Spy("failed:gate")

        _pass(led_, forge, tmp_path, fixup=fixup)
        assert fixup.calls == [run_id] and forge.named("rerun_failed") == []
        mine = [r for r in _leases(led_, run_id) if r["holder"] == "watcher" and r["action"] == "fixup"]
        assert len(mine) == 1 and mine[0]["outcome"] == "failed:gate" and mine[0]["head_sha"] == H2
        assert [(r["action"], r.get("kind")) for r in _log(tmp_path)] == [("fixup", None), ("flag", "red-after-fixup")]

        led_.advance(run_id, F1, [], None)  # the fixup's commit is the run's head and is not pushed: the PR reads H2
        unpushed_run = Spy("dispatched")
        _pass(led_, forge, tmp_path, fixup=unpushed_run, at=T + timedelta(hours=1))
        assert unpushed_run.calls == [] and _log(tmp_path)[-1]["kind"] == "unpushed"
    finally:
        led_.close()


# --------------------------------------------------------------------------------------------------------- R4 / S6


def test_a_held_lease_skips_the_run(tmp_path: Path) -> None:
    held_lease = _past("fixup", None, None, holder="operator", expires=T + timedelta(minutes=5), released=False)
    assert watch.decide([_view(past=(held_lease,))], 0, CAN_FIXUP, T) == ()
    expired = _past("fixup", None, None, holder="operator", expires=T - timedelta(minutes=5), released=False)
    assert watch.decide([_view(past=(expired,))], 0, CAN_FIXUP, T) == (Rerun("r-1", H1),), (
        "an expired lease holds nothing"
    )

    led_ = _ledger(tmp_path)
    try:
        a, pa = _open_run(led_, H1)
        b, pb = _open_run(led_, H2)
        led_.take_lease(a, "fixup", "operator", H1, T - timedelta(minutes=1), 600)  # unreleased, unexpired at T
        forge = Forged(states={pa: _state(H1), pb: _state(H2, merged=True)}, checks_of={H1: RED})
        close = Spy("closed")

        summary = _pass(led_, forge, tmp_path, close)
        assert forge.named("merge_state") == [pb], "no forge read for the held run"
        assert close.calls == [b] and summary.held == 1 and summary.open == 2

        later = _pass(led_, forge, tmp_path, close, at=T + timedelta(hours=1))
        assert pa in forge.named("merge_state") and forge.named("rerun_failed") == [H1], "expired: read and acted on"
        assert later.held == 0
    finally:
        led_.close()

    # taken between the read and the act: the take refuses, which is a skip and not the end of the pass
    home = tmp_path / "race"
    home.mkdir()
    led_ = _ledger(home)
    try:
        c, pc = _open_run(led_, H1)
        d, pd = _open_run(led_, H2)

        def take(number: int) -> None:
            if number == pc:
                led_.take_lease(c, "close", "operator", H1, T, 600)

        racing = Forged(states={pc: _state(H1, merged=True), pd: _state(H2, merged=True)}, on_read=take)
        closer = Spy("closed")
        summary = _pass(led_, racing, home, closer)
        assert closer.calls == [d] and summary.skipped == 1 and summary.refused == 0
        assert [r["outcome"] for r in _log(home) if r["run"] == c] == ["skipped"]
    finally:
        led_.close()


# --------------------------------------------------------------------------------------------------------- R5 / S7


def test_the_pass_never_merges_or_pushes(
    tmp_path: Path, disk: Disk, led: Ledger, monkeypatch: pytest.MonkeyPatch
) -> None:
    members = {n for n, v in vars(watch.Watched).items() if not n.startswith("_") and callable(v)}
    assert members == {"merge_state", "checks", "rerun_failed"}

    led_ = _ledger(tmp_path)
    try:
        _, pm = _open_run(led_, H1)
        _, pr = _open_run(led_, H2)
        _, ps = _open_run(led_, F1)
        forge = Forged(
            states={pm: _state(H1, merged=True), pr: _state(H2), ps: _state(F1, MergeableState.BEHIND)},
            checks_of={H2: RED},
        )
        _pass(led_, forge, tmp_path)  # a Forged call to anything outside the protocol raises AssertionError
        assert {name for name, _ in forge.calls} <= members
    finally:
        led_.close()

    # through the verb, on the V4a tenant: the forge driver and the channel are doubles, `close` and `run_fixup` recorders
    a = fresh_run(disk, led)
    b = fresh_run(disk, led)
    pa, pb = next(_PRS), next(_PRS)
    for run_id, number, head in ((a, pa, H1), (b, pb, H2)):
        led.set_pr(run_id, number)
        led.advance(run_id, head, [], None)
    driver = Forged(states={pa: _state(H1, merged=True), pb: _state(H2)}, checks_of={H2: RED})
    closed: list[str] = []

    def close_stub(ctx: Any, ledger: Ledger, call: Any, forge_: Any, *, run_id: str, pr: int | None = None) -> Any:
        closed.append(run_id)
        return {"outcome": "closed"}

    def no_channel(name: str, args: Any) -> Any:
        raise AssertionError(f"the pass called the store directly: {name}")

    monkeypatch.setattr(github_mod, "GitHub", lambda ctx: driver)
    monkeypatch.setattr(cli_mod, "Transport", lambda cfg, home: SimpleNamespace(call=no_channel))
    monkeypatch.setattr(close_mod, "close", close_stub)
    monkeypatch.setattr(runner_mod, "run_fixup", lambda *a, **k: pytest.fail("a fixup before any rerun"))

    argv = ["watch", "--tenant", TENANT, "--checkout", str(disk.work), "--root", ROOT]
    out = CliRunner().invoke(cli_mod.app, [*argv, "--once"])
    assert out.exit_code == 0, out.output
    assert len(out.output.strip().splitlines()) == 1 and out.output.startswith("watch: ")
    assert closed == [a] and driver.named("rerun_failed") == [H2]

    bare = CliRunner().invoke(cli_mod.app, argv)
    assert bare.exit_code == 2 and "run.watch-once" in bare.output


# --------------------------------------------------------------------------------------------------------- R6 / S8


def test_a_flag_is_logged_once(tmp_path: Path) -> None:
    led_ = _ledger(tmp_path)
    try:
        run_id, pr = _open_run(led_, H1)
        _taken(led_, run_id, "close", "watcher", H1, T - timedelta(hours=1), watch.RERUN)
        forge = Forged(states={pr: _state(H1)}, checks_of={H1: RED, H2: RED})

        first = _pass(led_, forge, tmp_path, policy=None)
        second = _pass(led_, forge, tmp_path, policy=None, at=T + timedelta(minutes=15))
        assert [(r["run"], r["head"], r["kind"]) for r in _log(tmp_path)] == [(run_id, H1, "red")]
        assert (first.flags, first.flags_seen, second.flags, second.flags_seen) == (1, 0, 0, 1)

        led_.advance(run_id, H2, [], None)  # a new head, red: rerun, then a flag of its own
        forge.states[pr] = _state(H2)
        _pass(led_, forge, tmp_path, policy=None, at=T + timedelta(minutes=30))
        _pass(led_, forge, tmp_path, policy=None, at=T + timedelta(minutes=45))
        assert [(r["head"], r["kind"]) for r in _log(tmp_path) if r["action"] == "flag"] == [(H1, "red"), (H2, "red")]
        assert len(_log(tmp_path)) == 3, "the flags and the one rerun"
        for s in (first, second):
            assert "\n" not in s.line()
    finally:
        led_.close()


# --------------------------------------------------------------------------------------------------------- R7 / S9


def test_below_config8_no_fixup(tmp_path: Path) -> None:
    assert Policy.from_effective({"schema": 7, "watcher": {"fixup": True, "fixup_per_day": 3}}) is None
    assert Policy.from_effective({"schema": 8}) is None
    assert Policy.from_effective({"schema": 8, "watcher": {"fixup": True, "fixup_per_day": 2}}) == Policy(True, 2)
    assert Policy.from_effective({"schema": 8, "watcher": {"fixup": False, "fixup_per_day": 0}}) == Policy(False, 0)

    reran = (_past(),)
    after = (_past(), _past("fixup", H2, ledger_mod.DISPATCHED))
    assert watch.decide([_view(past=reran)], 0, None, T) == (Flag("r-1", H1, "red"),)
    assert watch.decide([_view(past=after)], 0, None, T) == (Fixup("r-1", H1), Flag("r-1", H1, "red-after-fixup")), (
        "red after a fixup ends through the verb below config@8 too (card 35 R3)"
    )
    assert watch.decide([_view()], 0, None, T) == (Rerun("r-1", H1),), "rerun is still chosen"
    assert watch.decide([_view(state=_state(H1, merged=True))], 0, None, T) == (Close("r-1", H1),)

    led_ = _ledger(tmp_path)
    try:
        run_id, pr = _open_run(led_)
        _taken(led_, run_id, "close", "watcher", H1, T - timedelta(hours=1), watch.RERUN)
        fixup = Spy("dispatched")
        summary = _pass(led_, Forged(states={pr: _state(H1)}, checks_of={H1: RED}), tmp_path, fixup=fixup, policy=None)
        assert fixup.calls == [] and "opt-in absent" in summary.line()
        enabled = _pass(led_, Forged(states={pr: _state(H1)}, checks_of={H1: RED}), tmp_path, policy=CAN_FIXUP)
        assert "opt-in absent" not in enabled.line()
    finally:
        led_.close()


# -------------------------------------------------------------------------------------------------------- R8 / S10


def test_a_pass_emits_its_spans(tmp_path: Path, otel: Any) -> None:
    led_ = _ledger(tmp_path)
    try:
        ok, p_ok = _open_run(led_, H1)
        bad, p_bad = _open_run(led_, H2)
        red, p_red = _open_run(led_, F1)
        stale, p_stale = _open_run(led_, "3" * 40)
        forge = Forged(
            states={
                p_ok: _state(H1, merged=True),
                p_bad: _state(H2, merged=True),
                p_red: _state(F1),
                p_stale: _state("3" * 40, MergeableState.BEHIND),
            },
            checks_of={F1: RED},
        )
        close = Spy("closed", refuse={bad: "close.not-merged"})

        def counted(name: str, **attrs: str) -> int:
            return int(otel.count(f"isidium.factory.watch.{name}", **attrs))

        before = {
            "closed": counted("actions", **{"isidium.watch.action": "close", "isidium.outcome": "closed"}),
            "rerun": counted("actions", **{"isidium.watch.action": "rerun", "isidium.outcome": "rerun"}),
            "stale": counted("flags", **{"isidium.watch.kind": "stale"}),
            "refused": counted("refusals", **{"isidium.rule": "close.not-merged"}),
        }
        otel.clear()
        _pass(led_, forge, tmp_path, close)

        (pass_span,) = otel.spans(watch.PASS_SPAN)
        assert pass_span.attributes["isidium.watch.open"] == 4
        reads = otel.spans(watch.READ_SPAN)
        assert sorted((s.attributes["isidium.run_id"], s.attributes["isidium.watch.read"]) for s in reads) == sorted(
            [(ok, "merge_state"), (bad, "merge_state"), (red, "merge_state"), (red, "checks"), (stale, "merge_state")]
        ), "a read per forge call: the merged and the stale have no checks read"
        acts = {
            (s.attributes["isidium.run_id"], s.attributes["isidium.watch.action"]): s
            for s in otel.spans(watch.ACTION_SPAN)
        }
        assert set(acts) == {(ok, "close"), (bad, "close"), (red, "rerun"), (stale, "flag")}
        assert acts[(ok, "close")].attributes["isidium.outcome"] == "closed"
        refused = acts[(bad, "close")]
        assert refused.attributes["isidium.rule"] == "close.not-merged" and refused.status.status_code.name == "ERROR"
        assert acts[(red, "rerun")].attributes["isidium.outcome"] == "rerun"
        assert not [s for s in otel.spans() if s.name.startswith("isidium.factory.run")]

        assert (
            counted("actions", **{"isidium.watch.action": "close", "isidium.outcome": "closed"}) - before["closed"] == 1
        )
        assert (
            counted("actions", **{"isidium.watch.action": "rerun", "isidium.outcome": "rerun"}) - before["rerun"] == 1
        )
        assert counted("flags", **{"isidium.watch.kind": "stale"}) - before["stale"] == 1
        assert counted("refusals", **{"isidium.rule": "close.not-merged"}) - before["refused"] == 1
        assert [r["rule"] for r in _log(tmp_path) if "rule" in r] == ["close.not-merged"]
    finally:
        led_.close()


# -------------------------------------------------------------------------------------------------------- R1 / S11


def test_decide_is_a_pure_function_of_its_inputs(monkeypatch: pytest.MonkeyPatch) -> None:
    assert list(inspect.signature(watch.decide).parameters) == ["views", "taken_today", "policy", "now"]

    lease = _past("fixup", None, None, holder="operator", expires=T + timedelta(minutes=5), released=False)
    views = [
        _view("r-1", _state(H1, merged=True)),
        _view("r-2", _state(H1, MergeableState.BEHIND)),
        _view("r-3"),
        _view("r-4", past=(_past(),)),
        _view("r-5", past=(lease,)),
    ]
    snapshot = list(views)
    want = (Close("r-1", H1), Flag("r-2", H1, "stale"), Rerun("r-3", H1), Fixup("r-4", H1))

    with monkeypatch.context() as m:

        def forbidden(*a: Any, **k: Any) -> Any:
            raise AssertionError("decide reached outside its arguments")

        m.setattr(builtins, "open", forbidden)
        m.setattr(sqlite3, "connect", forbidden)
        m.setattr(socket, "socket", forbidden)
        first = watch.decide(views, 0, CAN_FIXUP, T)
        second = watch.decide(views, 0, CAN_FIXUP, T)
        later = watch.decide(views, 0, CAN_FIXUP, T + timedelta(minutes=10))

    assert first == second == want and views == snapshot
    assert all(isinstance(a, Close | Rerun | Fixup | Flag) for a in first)
    assert later == (*want, Rerun("r-5", H1)), "only the run whose lease expired changes"
