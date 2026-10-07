"""Card 35: the PR watcher never retries a refused action at the same head.

A fixup or a rerun a verb refused (or that raised) at a head is not chosen again at that head: the run is flagged once,
naming the rule, so one stuck run is one take of the day's fixup ceiling and not one every pass (S1, S2). Red after a
fixup ends through the fixup verb whether or not `[watcher].fixup` is on (S3). Every watcher action that refuses or
raises releases its lease with the rule or the raised marker (S4). The helpers are `test_watch.py`'s, imported -- never
one of its tests, so nothing is collected twice. Times are explicit aware datetimes, a whole second or more from every
boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from isidium.factory import ledger as ledger_mod
from isidium.factory import watch
from isidium.factory.watch import Fixup, Flag, Policy, Refused, Rerun, Verb, Verbs
from isidium.store.core.refusal import Refusal

from .test_watch import (
    CAN_FIXUP,
    F1,
    H1,
    H2,
    RED,
    Forged,
    Spy,
    T,
    _leases,
    _ledger,
    _log,
    _open_run,
    _pass,
    _past,
    _state,
    _taken,
    _view,
)

DAY = datetime(2026, 10, 4, 0, 0, 0, tzinfo=UTC)
FIXUP_RULE, RERUN_RULE, CLOSE_RULE = "run.fixup-unreviewed", "forge.rate-limited", "close.not-merged"


@dataclass
class Refusing(Forged):
    """A `Forged` whose rerun is refused, as a forge that rate-limits would."""

    def rerun_failed(self, sha: str) -> tuple[int, ...]:
        self.calls.append(("rerun_failed", sha))
        raise Refusal(RERUN_RULE, sha, "refused by the forge")


def _flags(tmp_path: Path) -> list[dict[str, Any]]:
    return [r for r in _log(tmp_path) if r["action"] == "flag"]


# ------------------------------------------------------------------------------------------------------- R1 / S1


def test_a_refused_fixup_is_not_chosen_again(tmp_path: Path) -> None:
    reran = _past()
    refused = _past("fixup", H1, FIXUP_RULE)
    assert watch.decide([_view(past=(reran, refused))], 0, CAN_FIXUP, T) == (
        Refused("r-1", H1, "fixup-refused", FIXUP_RULE),
    )
    raised = _past("fixup", H1, ledger_mod.LEASE_RAISED)
    assert watch.decide([_view(past=(reran, raised))], 0, CAN_FIXUP, T) == (
        Refused("r-1", H1, "fixup-refused", ledger_mod.LEASE_RAISED),
    )
    assert watch.decide([_view(past=(reran, _past("fixup", H1, FIXUP_RULE, holder="operator")))], 0, CAN_FIXUP, T) == (
        Fixup("r-1", H1),
    ), "an operator's refusal is not the watcher's"
    assert watch.decide([_view(past=(reran, _past("fixup", H2, FIXUP_RULE)))], 0, CAN_FIXUP, T) == (
        Fixup("r-1", H1),
    ), "a refusal at another head is not this head's"
    assert watch.decide([_view(past=(reran, refused))], 0, Policy(False, 5), T) == (
        Refused("r-1", H1, "fixup-refused", FIXUP_RULE),
    ), "the refusal is flagged whether or not the opt-in is on"

    led_ = _ledger(tmp_path)
    try:
        run_id, pr = _open_run(led_)
        _taken(led_, run_id, "close", "watcher", H1, T - timedelta(hours=1), watch.RERUN)
        forge = Forged(states={pr: _state(H1)}, checks_of={H1: RED})
        fixup = Spy("dispatched", refuse={run_id: FIXUP_RULE})

        for minutes in (0, 15, 30):
            _pass(led_, forge, tmp_path, fixup=fixup, at=T + timedelta(minutes=minutes))

        assert fixup.calls == [run_id], "taken once, then not again at this head"
        assert led_.leases_taken("watcher", "fixup", DAY) == 1
        (row,) = _flags(tmp_path)
        assert (row["run"], row["head"], row["kind"], row["rule"]) == (run_id, H1, "fixup-refused", FIXUP_RULE)
    finally:
        led_.close()


# ------------------------------------------------------------------------------------------------------- R2 / S2


def test_a_refused_rerun_is_not_chosen_again(tmp_path: Path) -> None:
    refused = _past("close", H1, RERUN_RULE)
    assert watch.decide([_view(past=(refused,))], 0, CAN_FIXUP, T) == (Refused("r-1", H1, "rerun-refused", RERUN_RULE),)
    assert watch.decide([_view(past=(_past("close", H1, RERUN_RULE, holder="operator"),))], 0, CAN_FIXUP, T) == (
        Rerun("r-1", H1),
    ), "an operator's refusal is not the watcher's"

    led_ = _ledger(tmp_path)
    try:
        run_id, pr = _open_run(led_)
        forge = Refusing(states={pr: _state(H1)}, checks_of={H1: RED})
        fixup = Spy("dispatched")

        for minutes in (0, 15, 30):
            _pass(led_, forge, tmp_path, fixup=fixup, at=T + timedelta(minutes=minutes))

        assert forge.named("rerun_failed") == [H1], "asked once, then not again at this head"
        assert fixup.calls == [], "no fixup on a head whose checks were never rerun"
        (lease,) = _leases(led_, run_id)
        assert (lease["action"], lease["head_sha"], lease["outcome"]) == ("close", H1, RERUN_RULE)
        (row,) = _flags(tmp_path)
        assert (row["run"], row["head"], row["kind"], row["rule"]) == (run_id, H1, "rerun-refused", RERUN_RULE)
    finally:
        led_.close()


# ------------------------------------------------------------------------------------------------------- R3 / S3


def test_red_after_fixup_ends_with_fixup_off(tmp_path: Path) -> None:
    ran = _past("fixup", H1, ledger_mod.DISPATCHED, holder="operator")
    again = _view(state=_state(H2), head=H2, past=(ran, _past(head=H2)))
    want = (Fixup("r-1", H2), Flag("r-1", H2, "red-after-fixup"))
    for policy in (Policy(False, 0), None, CAN_FIXUP):
        assert watch.decide([again], 9, policy, T) == want, policy
    stuck = _view(state=_state(H2), head=H2, past=(ran, _past(head=H2), _past("fixup", H2, FIXUP_RULE)))
    assert watch.decide([stuck], 0, Policy(False, 0), T) == (
        Refused("r-1", H2, "fixup-refused", FIXUP_RULE),
        Flag("r-1", H2, "red-after-fixup"),
    ), "a refused one is still not taken again"

    for name, policy in (("off", Policy(False, 0)), ("absent", None)):
        home = tmp_path / name
        home.mkdir()
        led_ = _ledger(home)
        try:
            run_id, pr = _open_run(led_, H2)
            _taken(led_, run_id, "fixup", "operator", H1, T - timedelta(hours=3), ledger_mod.DISPATCHED)
            _taken(led_, run_id, "close", "watcher", H2, T - timedelta(hours=1), watch.RERUN)
            fixup = Spy("failed:gate")

            _pass(led_, Forged(states={pr: _state(H2)}, checks_of={H2: RED}), home, fixup=fixup, policy=policy)

            assert fixup.calls == [run_id], name
            (mine,) = [r for r in _leases(led_, run_id) if r["holder"] == "watcher" and r["action"] == "fixup"]
            assert (mine["outcome"], mine["head_sha"]) == ("failed:gate", H2), name
            assert [(r["action"], r.get("kind")) for r in _log(home)] == [("fixup", None), ("flag", "red-after-fixup")]
        finally:
            led_.close()


# ------------------------------------------------------------------------------------------------------- R4 / S4


def test_a_refused_action_releases_its_lease(tmp_path: Path) -> None:
    led_ = _ledger(tmp_path)
    try:
        merged, pm = _open_run(led_, H1)
        stuck, ps = _open_run(led_, H2)
        fresh, pf = _open_run(led_, F1)
        _taken(led_, stuck, "close", "watcher", H2, T - timedelta(hours=1), watch.RERUN)

        class RefusingFresh(Refusing):
            def rerun_failed(self, sha: str) -> tuple[int, ...]:
                if sha != F1:
                    raise AssertionError("only the fresh run's head is rerun")
                return super().rerun_failed(sha)

        forge = RefusingFresh(
            states={pm: _state(H1, merged=True), ps: _state(H2), pf: _state(F1)}, checks_of={H2: RED, F1: RED}
        )
        close = Spy("closed", refuse={merged: CLOSE_RULE})
        fixup = Spy("dispatched", refuse={stuck: FIXUP_RULE})

        summary = _pass(led_, forge, tmp_path, close, fixup)

        assert close.calls == [merged] and fixup.calls == [stuck] and summary.refused == 3
        (closing,) = _leases(led_, merged)
        (fixing,) = [r for r in _leases(led_, stuck) if r["action"] == "fixup"]
        (rerunning,) = _leases(led_, fresh)
        for lease, rule in ((closing, CLOSE_RULE), (fixing, FIXUP_RULE), (rerunning, RERUN_RULE)):
            assert lease["holder"] == "watcher" and lease["released_at"] is not None, rule
            assert lease["outcome"] == rule
    finally:
        led_.close()

    home = tmp_path / "raised"
    home.mkdir()
    led_ = _ledger(home)
    try:
        run_id, pr = _open_run(led_, H1)

        def boom(run: str) -> Any:
            raise RuntimeError(run)

        verbs = Verbs(Verb(boom, lambda: 3600.0), Verb(Spy("dispatched").run, lambda: 7200.0))
        driver = Forged(states={pr: _state(H1, merged=True)})
        with pytest.raises(RuntimeError):
            watch.watch_once(led_, driver, CAN_FIXUP, verbs, home / watch.LOG_FILE, lambda: T)
        (lease,) = _leases(led_, run_id)
        assert lease["released_at"] is not None and lease["outcome"] == ledger_mod.LEASE_RAISED
    finally:
        led_.close()
