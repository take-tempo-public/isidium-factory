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

from typing import Any

from isidium.store.core import events as events_mod

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
