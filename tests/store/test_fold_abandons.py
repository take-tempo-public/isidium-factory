"""Card 7 — the fold records an abandoned run when a *dispatched* card is withdrawn or demoted.

A `withdrawn` or `demoted` act observed on a card whose execution is `dispatched` used to change nothing in the
sidecar: `execution` stayed whatever the run last reported, for ever, and a card re-ratified after such a run could
never be dispatched again. R1/R2 make the fold set `execution` to `abandoned` and append a `runs[]` entry naming
the abandoned run; R3 keeps `abandoned` from ever being its own projected label (a withdrawn or demoted card's own
`status` shadows it first, at rows 3 and 4 — 03 §1.5); R4 leaves a card with nothing in flight untouched; R5 is the
one `IN_FLIGHT` set every site that asks the question reads.

Card 13 narrowed R1/R2 to a *dispatched* run only: a withdrawal or demotion of a `parked` or `answered` card
disposes of its question instead of abandoning a run that already ended. That half now lives in
`test_fold_parks.py`; this file keeps only the dispatched-run cases R4 left untouched.

What each test discriminates:

- **The fold alone** (`test_nothing_in_flight_nothing_abandoned`): a `withdrawn`/`demoted` event on a card the fold
  has never seen dispatched changes neither `execution` nor `runs[]` — R4, tested the way `test_l1.py` and
  `test_failed_returns.py` test the fold, directly and without a store.
- **End to end on a store**: a withdrawal and a demotion of a dispatched card, landed, both fold to `abandoned`
  (R1); `runs[]` names the abandoned run by the dispatched event's own `run_id` and the act's own `at` (R2); the
  projected label is `withdrawn`/`draft`, never `execution(abandoned)` (R3); a re-ratification afterward reads
  `ratified`/`ready` (R3); the board's WIP count drops with it (R5).

A demotion that only flips `status` is never signed (1.2's predicate has no rule for `ratified → draft` alone) and
so is never observed at land — the same as any other unsigned act. The demotions here carry a gated edit alongside
the status flip (an owner editing a card as they pull it back), which the predicate's `gated-on-ratified` rule
does sign, the same way an owner demoting and fixing something in one gesture would in the field.
"""

from __future__ import annotations

from typing import Any

from isidium.store.core import events as events_mod
from isidium.store.core import status

from .conftest import LANDER, OWNER, Harness, fresh, path_of


def ratified(hz: Harness, slug: str) -> int:
    cid = hz.draft(slug)
    hz.st.ratify([cid], OWNER)
    return cid


def _ev(n: int, card: int, kind: str, **more: Any) -> dict[str, Any]:
    return {"id": f"e{n}", "at": f"2026-09-15T00:00:{n:02d}Z", "card": card, "kind": kind, **more}


def _wip_line(board_text: str) -> str:
    return next(line for line in board_text.splitlines() if line.startswith("WIP "))


# ---- R1: a withdrawal or demotion of an in-flight card folds to abandoned ------------------------------------------


def test_a_withdrawn_dispatched_card_folds_to_abandoned() -> None:
    hz = fresh()
    st = hz.st
    a = ratified(hz, "a")
    st.land({"run_id": "r-0", "events": [{"kind": "dispatched", "card": a, "run_id": "r-0"}]}, LANDER)
    assert st.state["cards"][f"{a:04d}"]["execution"] == "dispatched"
    st.write_set(a, ['status="withdrawn"', 'withdrawn_reason="superseded"'], OWNER)
    st.land({"run_id": "r-1", "events": []}, LANDER)
    assert st.state["cards"][f"{a:04d}"]["execution"] == "abandoned"


def test_a_demoted_dispatched_card_folds_to_abandoned() -> None:
    hz = fresh()
    st = hz.st
    a = ratified(hz, "a")
    st.land({"run_id": "r-0", "events": [{"kind": "dispatched", "card": a, "run_id": "r-0"}]}, LANDER)
    st.write_set(a, ['status="draft"', 'title="Needs another look"'], OWNER)
    st.land({"run_id": "r-1", "events": []}, LANDER)
    assert st.state["cards"][f"{a:04d}"]["execution"] == "abandoned"


# ---- R2: runs[] names the abandoned run by its last dispatched event's id and the act's own time -------------------


def test_runs_records_the_abandoned_run() -> None:
    hz = fresh()
    st = hz.st
    a = ratified(hz, "a")
    st.land({"run_id": "r-0", "events": [{"kind": "dispatched", "card": a, "run_id": "r-7"}]}, LANDER)
    st.write_set(a, ['status="withdrawn"', 'withdrawn_reason="superseded"'], OWNER)
    st.land({"run_id": "r-1", "events": []}, LANDER)
    withdrawn_at = st.docs[path_of(st, a)].history[-1]["at"]
    assert st.state["cards"][f"{a:04d}"]["runs"] == [
        {"run_id": "r-7", "outcome": "abandoned", "ended_at": withdrawn_at}
    ], "run_id is the dispatched event's own, not the run report's envelope id"


# ---- R3: abandoned is typed, and gives no label of its own ---------------------------------------------------------


def test_abandoned_is_typed_and_the_label_comes_from_status() -> None:
    assert "abandoned" in status.EXECUTION_STATES, "a recognized member, not a fallback to `unknown`"
    hz = fresh()
    st = hz.st
    a, b = ratified(hz, "a"), ratified(hz, "b")
    st.land(
        {
            "run_id": "r-0",
            "events": [
                {"kind": "dispatched", "card": a, "run_id": "r-a"},
                {"kind": "dispatched", "card": b, "run_id": "r-b"},
            ],
        },
        LANDER,
    )
    st.write_set(a, ['status="withdrawn"', 'withdrawn_reason="superseded"'], OWNER)
    st.write_set(b, ['status="draft"', 'title="Needs another look"'], OWNER)
    st.land({"run_id": "r-1", "events": []}, LANDER)
    assert st.state["cards"][f"{a:04d}"]["execution"] == "abandoned"
    assert st.state["cards"][f"{b:04d}"]["execution"] == "abandoned"
    proj = st.projections()
    assert proj[a].label.row == "withdrawn" and proj[a].render() == "withdrawn", "row 3 shadows row 9"
    assert proj[b].label.row == "draft" and proj[b].render() == "draft", "row 4 shadows row 9"


def test_a_reratified_abandoned_card_is_ready() -> None:
    hz = fresh()
    st = hz.st
    a = ratified(hz, "a")
    st.land({"run_id": "r-0", "events": [{"kind": "dispatched", "card": a, "run_id": "r-0"}]}, LANDER)
    st.write_set(a, ['status="draft"', 'title="Needs another look"'], OWNER)
    st.land({"run_id": "r-1", "events": []}, LANDER)
    assert st.state["cards"][f"{a:04d}"]["execution"] == "abandoned"
    st.ratify([a], OWNER)
    st.land({"run_id": "r-2", "events": []}, LANDER)
    assert st.state["cards"][f"{a:04d}"]["execution"] is None, "the re-ratification clears the abandoned run"
    proj = st.projections()[a]
    assert proj.label.row == "ready" and proj.ready is True


# ---- R4: nothing in flight, nothing abandoned -----------------------------------------------------------------------


def test_nothing_in_flight_nothing_abandoned() -> None:
    heads = {"0007": {"seq": 1, "h": "sha256:h"}}
    withdrawn = events_mod.fold(
        [_ev(1, 7, "withdrawn", seq=1)], "c", "2026-09-15T00:00:00Z", {"seq": 1, "h": "j"}, heads
    )
    assert withdrawn["cards"]["0007"] == {**events_mod._new_card(), "history_head": heads["0007"]}
    complete = [_ev(1, 7, "complete", run_id="r-1", build_hash="sha256:x"), _ev(2, 7, "demoted", seq=2)]
    after_complete = events_mod.fold(complete, "c", "2026-09-15T00:00:00Z", {"seq": 1, "h": "j"}, {})
    card = after_complete["cards"]["0007"]
    assert card["execution"] == "complete" and len(card["runs"]) == 1, "K1: a finished run is not abandoned"


def test_a_parked_card_with_no_dispatched_line_is_withdrawn_without_a_run_id() -> None:
    """Found reviewing `r-6`'s work (2026-09-15): the fold read the card's last `dispatched` run id without a guard, so
    an event file holding a card in flight with no `dispatched` line for it — a `parked` reported alone — raised inside
    the fold, and every land after it would fail on the same file. That totality requirement is unchanged by card 13;
    only the outcome is — a `parked` reported alone is no longer abandoned when it is withdrawn (R2), it is recorded
    parked and gains a `withdrawn` response, and the entry still carries no `run_id` key when the file names none
    (canon has no null: an unknown id is an absent key)."""
    evs = [_ev(1, 7, "parked"), _ev(2, 7, "withdrawn", seq=2)]
    card = events_mod.fold(evs, "c", "2026-09-15T00:00:00Z", {"seq": 1, "h": "j"}, {})["cards"]["0007"]
    assert card["execution"] is None
    assert card["runs"] == [
        {
            "outcome": "parked",
            "ended_at": "2026-09-15T00:00:01Z",
            "responses": [{"act": "withdrawn", "card_seq": 2, "at": "2026-09-15T00:00:02Z"}],
        }
    ]


# ---- R5: the in-flight set has one home ------------------------------------------------------------------------------


def test_the_in_flight_set_has_one_home() -> None:
    from isidium.store.core import board as board_mod
    from isidium.store.core import neighborhood as neighborhood_mod

    assert frozenset({"dispatched", "parked", "answered"}) == events_mod.IN_FLIGHT
    assert board_mod.IN_FLIGHT is events_mod.IN_FLIGHT, "board reads the same object, not its own copy"
    assert neighborhood_mod.IN_FLIGHT is events_mod.IN_FLIGHT, "the neighborhood reads the same object too"


# ---- the board's WIP count (R1, read through the shared set) --------------------------------------------------------


def test_withdrawing_a_dispatched_card_frees_its_wip() -> None:
    hz = fresh()
    st = hz.st
    a = ratified(hz, "a")
    st.land({"run_id": "r-0", "events": [{"kind": "dispatched", "card": a, "run_id": "r-0"}]}, LANDER)
    assert _wip_line(st.raw["BOARD.md"].decode("utf-8")).startswith("WIP 1/")
    st.write_set(a, ['status="withdrawn"', 'withdrawn_reason="superseded"'], OWNER)
    st.land({"run_id": "r-1", "events": []}, LANDER)
    assert _wip_line(st.raw["BOARD.md"].decode("utf-8")).startswith("WIP 0/")
