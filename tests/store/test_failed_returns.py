"""A failed run's way back [owner, 2026-09-14] — found live on `r-4`.

A landed failure put card 7 at `failed(infra)`, and nothing in the fold ever moved a card off a failure: the ready view
needs the plain `ratified` label, so `dispatch` answered nothing to dispatch and `dispatch --card 7` refused. T-A7
routes a failed run to the design queue and defined no step back out. The owner's ruling: **a signed ratification
landed after the failure returns the card to ready** — the card edited and re-ratified, or demoted and re-ratified
unchanged — and the morning review names the cards waiting on that.

What each test discriminates:

- **The fold alone**: a ratification after a failure clears it; the same ratification without a failure before it,
  or on another card, or after a later dispatch superseded the failure, changes nothing.
- **End to end on a store**: the failed card is not ready and sits in the queue's failed runs; a demotion and an
  unchanged re-ratification, landed, make it ready and take it out of the queue.
"""

from __future__ import annotations

from typing import Any, get_args

import pytest

from isidium.store.core import events as events_mod
from isidium.store.core import status as status_mod
from isidium.store.core.refusal import Refusal

from .conftest import LANDER, OWNER, Harness, fresh


def ratified(hz: Harness, slug: str) -> int:
    cid = hz.draft(slug)
    hz.st.ratify([cid], OWNER)
    return cid


def _ev(n: int, card: int, kind: str, **more: Any) -> dict[str, Any]:
    return {"id": f"e{n}", "at": f"2026-09-14T00:00:{n:02d}Z", "card": card, "kind": kind, **more}


def _execution(events: list[dict[str, Any]], card: int) -> Any:
    state = events_mod.fold(events, "abc", "2026-09-14T00:00:00Z", {"seq": 1, "h": "sha256:j"}, {})
    return state["cards"][f"{card:04d}"]["execution"]


def test_a_ratification_after_a_failure_clears_it_and_nothing_else_does() -> None:
    failed = [_ev(1, 7, "dispatched", run_id="r-4"), _ev(2, 7, "failed", **{"class": "budget", "run_id": "r-4"})]
    again = _ev(3, 7, "ratified", seq=3, commit="c3")
    assert _execution(failed, 7) == "failed(budget)"
    assert _execution([*failed, again], 7) is None, "a newer ratification is the way back"
    assert _execution([*failed, _ev(3, 8, "ratified", seq=1, commit="c3")], 7) == "failed(budget)", "another card's"
    assert _execution([_ev(1, 7, "dispatched", run_id="r-4"), again], 7) == "dispatched", "no failure, nothing cleared"
    superseded = [*failed, _ev(3, 7, "dispatched", run_id="r-5"), _ev(4, 7, "ratified", seq=4, commit="c4")]
    assert _execution(superseded, 7) == "dispatched", "a failure a later run superseded is not cleared twice"


def test_the_failure_classes_are_one_closed_set_and_merge_is_in_it() -> None:
    """The class set widened by `merge` and `malformed-plan` [owner, 2026-09-20], and pinned as ONE set.

    **The discriminator is `parse_event`, not the fold.** `fold` reads `e["class"]` straight out of a mapping and
    would render `failed(merge)` for any string at all, widened or not — so a fold assertion would pass on the
    unwidened set and prove nothing. What the widening actually changes is the door: the class is a `Literal` on the
    `Failed` model, so an event carrying a class outside the set is refused `event.shape` before it can land.

    **And the two copies are pinned equal here** rather than trusted to a comment. `core.events.FailureClass` and
    `core.status.FailureClass` are one closed set written twice, deliberately — `status` does not import `events`,
    which would pull pydantic onto paths that do not want it — so nothing but this assertion stops them drifting.
    `status.FAILURE_CLASSES` is derived from its own `Literal`, so that third copy cannot drift at all.
    """
    assert get_args(events_mod.FailureClass) == get_args(status_mod.FailureClass), "one set, written twice"
    assert get_args(status_mod.FailureClass) == status_mod.FAILURE_CLASSES, "the tuple is derived, not retyped"
    assert {"merge", "malformed-plan"} <= set(status_mod.FAILURE_CLASSES)

    for cls in ("merge", "malformed-plan"):
        ev = events_mod.parse_event({"card": 7, "kind": "failed", "class": cls, "run_id": "r-7"})
        assert isinstance(ev, events_mod.Failed) and ev.class_ == cls
    with pytest.raises(Refusal) as ei:
        events_mod.parse_event({"card": 7, "kind": "failed", "class": "conflict", "run_id": "r-7"})
    assert ei.value.rule == "event.shape", "a class outside the set is refused at the door"


def test_a_failed_card_waits_in_the_queue_and_a_newer_ratification_makes_it_ready() -> None:
    hz = fresh()
    st = hz.st
    a = ratified(hz, "a")
    events = [
        {"kind": "dispatched", "card": a, "run_id": "r-1"},
        {"kind": "failed", "card": a, "class": "budget", "run_id": "r-1"},
    ]
    st.land({"run_id": "r-1", "events": events}, LANDER)
    p = st.projection_of(a)
    assert p.label.row == "execution" and p.label.execution == "failed" and not p.ready
    assert st.show("Queue").failed_runs == (a,)

    st.write_set(a, ['status="draft"'], OWNER)
    st.ratify([a], OWNER)
    st.land({"run_id": "r-2", "events": []}, LANDER)
    p = st.projection_of(a)
    assert p.ready, p.label.render()
    assert st.show("Queue").failed_runs == ()
