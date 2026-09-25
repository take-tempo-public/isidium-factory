"""Card 13 — a park ends a run and opens a question on its card; the owner's response disposes of the question and
abandons no run.

Found live (2026-09-24, run `r-13`): a park ends the run and the ledger records it `parked`, but the fold wrote no
`runs[]` entry for the park at all — the demotion that later answered the question was the *only* trace, and it read
`c["execution"] in IN_FLIGHT` (which held `parked`) and recorded the run **abandoned**. The ledger and the sidecar
then disagreed about the same run. R1 gives the park its own `runs[]` entry; R2/R3 record how the question was left
— a response `{act, card_seq, at}` appended to that same entry, never a fresh `abandoned` one; R4 leaves the
dispatched-run abandon path exactly as card 7 built it (see `test_fold_abandons.py`); R5 is the re-ratification
path back to `ready`; R6 is the ordering and append-only guarantee on the responses themselves.

What each test discriminates:

- **S1** (`test_a_parked_run_is_recorded_as_ended_parked`): a `dispatched`/`parked` pair gives one `runs[]` entry
  naming the park, with an empty `responses[]` — the fact this card exists to add.
- **S2** (`test_a_demotion_of_a_parked_card_leaves_the_question_and_abandons_nothing`): end to end on a harness —
  the live gesture that produced the bug — a demotion of a parked card appends a response instead of writing a
  second, `abandoned` entry, and clears `execution`.
- **S3** (`test_a_withdrawal_of_a_parked_card_leaves_the_question_and_abandons_nothing`): the same at fold level,
  for `withdrawn`.
- **S4** (`test_an_answer_is_recorded_on_the_parked_run`): an `answered` event appends its own response and leaves
  `execution` at `answered` — the entry stays open for whatever the owner does next.
- **S6** (`test_card_12s_history_folds_to_a_parked_run_whose_question_was_left`): card 12's own rows, the incident
  that found this card, folded literally; then the same shape replayed on a harness through a re-ratification,
  which is R5 — nothing here ever wrote `abandoned` for the re-ratification to clear.
- **S7** (`test_a_park_answered_then_demoted_keeps_both_responses_in_order`): an answer and then a demotion both
  land on the one entry, in order; a further act once the execution has cleared adds nothing (R6).
- **C5/C6** (`test_the_fold_is_total_over_acts_the_store_cannot_emit`): two shapes the store itself never emits —
  a `seq`-less act, and an `answered`/`demoted` pair with no park before it — that the fold must still survive
  without raising, because a raise here fails every later land over the same file (the `r-6` precedent).
"""

from __future__ import annotations

from typing import Any

from isidium.store.core import events as events_mod

from .conftest import LANDER, OWNER, Harness, fresh, path_of


def ratified(hz: Harness, slug: str) -> int:
    cid = hz.draft(slug)
    hz.st.ratify([cid], OWNER)
    return cid


def _ev(n: int, card: int, kind: str, **more: Any) -> dict[str, Any]:
    return {"id": f"e{n}", "at": f"2026-09-15T00:00:{n:02d}Z", "card": card, "kind": kind, **more}


# ---- S1: a park becomes its own runs[] entry -------------------------------------------------------------------


def test_a_parked_run_is_recorded_as_ended_parked() -> None:
    evs = [_ev(1, 7, "dispatched", run_id="r-13"), _ev(2, 7, "parked", run_id="r-13")]
    card = events_mod.fold(evs, "c", "2026-09-15T00:00:00Z", {"seq": 1, "h": "j"}, {})["cards"]["0007"]
    assert card["execution"] == "parked"
    assert card["runs"] == [
        {"run_id": "r-13", "outcome": "parked", "ended_at": "2026-09-15T00:00:02Z", "responses": []}
    ]


# ---- S2: end to end, a demotion of a parked card ---------------------------------------------------------------


def test_a_demotion_of_a_parked_card_leaves_the_question_and_abandons_nothing() -> None:
    hz = fresh()
    st = hz.st
    a = ratified(hz, "a")
    st.land({"run_id": "r-13", "events": [{"kind": "dispatched", "card": a, "run_id": "r-13"}]}, LANDER)
    st.land(
        {"run_id": "r-13", "events": [{"kind": "parked", "card": a, "run_id": "r-13", "text": "needs a call"}]},
        LANDER,
    )
    parked_at = st.state["cards"][f"{a:04d}"]["runs"][0]["ended_at"]
    st.write_set(a, ['status="draft"', 'title="Needs another look"'], OWNER)
    st.land({"run_id": "r-1", "events": []}, LANDER)
    demoted_entry = st.docs[path_of(st, a)].history[-1]
    card = st.state["cards"][f"{a:04d}"]
    assert card["execution"] is None
    assert all(r["outcome"] != "abandoned" for r in card["runs"]), "a parked run is never abandoned (R2)"
    assert card["runs"] == [
        {
            "run_id": "r-13",
            "outcome": "parked",
            "ended_at": parked_at,
            "responses": [{"act": "demoted", "card_seq": demoted_entry["seq"], "at": demoted_entry["at"]}],
        }
    ]


# ---- S3: the same at fold level, for withdrawn -----------------------------------------------------------------


def test_a_withdrawal_of_a_parked_card_leaves_the_question_and_abandons_nothing() -> None:
    evs = [_ev(1, 7, "dispatched", run_id="r-9"), _ev(2, 7, "parked", run_id="r-9"), _ev(3, 7, "withdrawn", seq=5)]
    card = events_mod.fold(evs, "c", "2026-09-15T00:00:00Z", {"seq": 1, "h": "j"}, {})["cards"]["0007"]
    assert card["execution"] is None
    assert card["runs"] == [
        {
            "run_id": "r-9",
            "outcome": "parked",
            "ended_at": "2026-09-15T00:00:02Z",
            "responses": [{"act": "withdrawn", "card_seq": 5, "at": "2026-09-15T00:00:03Z"}],
        }
    ]


# ---- S4: an answer is recorded on the parked run ----------------------------------------------------------------


def test_an_answer_is_recorded_on_the_parked_run() -> None:
    evs = [_ev(1, 7, "dispatched", run_id="r-13"), _ev(2, 7, "parked", run_id="r-13"), _ev(3, 7, "answered", seq=4)]
    card = events_mod.fold(evs, "c", "2026-09-15T00:00:00Z", {"seq": 1, "h": "j"}, {})["cards"]["0007"]
    assert card["execution"] == "answered"
    assert card["runs"] == [
        {
            "run_id": "r-13",
            "outcome": "parked",
            "ended_at": "2026-09-15T00:00:02Z",
            "responses": [{"act": "answered", "card_seq": 4, "at": "2026-09-15T00:00:03Z"}],
        }
    ]


# ---- S6: card 12's own history, and the re-ratification back to ready --------------------------------------------


def test_card_12s_history_folds_to_a_parked_run_whose_question_was_left() -> None:
    events = [
        _ev(1, 12, "ratified", seq=2, at="2026-09-24T03:09:06Z", commit="sha:base12"),
        _ev(2, 12, "dispatched", run_id="r-13", at="2026-09-24T03:10:00Z"),
        _ev(3, 12, "parked", run_id="r-13", at="2026-09-24T03:34:21Z", text="which flow does this card mean?"),
        _ev(4, 12, "demoted", seq=3, at="2026-09-24T14:38:31Z"),
        _ev(5, 12, "ratified", seq=4, at="2026-09-24T14:44:38Z", commit="sha:fix12"),
    ]
    card = events_mod.fold(events, "c", "2026-09-24T14:44:38Z", {"seq": 1, "h": "j"}, {})["cards"]["0012"]
    assert card["execution"] is None
    assert card["runs"] == [
        {
            "run_id": "r-13",
            "outcome": "parked",
            "ended_at": "2026-09-24T03:34:21Z",
            "responses": [{"act": "demoted", "card_seq": 3, "at": "2026-09-24T14:38:31Z"}],
        }
    ]

    # The same shape, replayed on a harness through the re-ratification: R5, at the projection.
    hz = fresh()
    st = hz.st
    a = ratified(hz, "a")
    st.land({"run_id": "r-13", "events": [{"kind": "dispatched", "card": a, "run_id": "r-13"}]}, LANDER)
    st.land(
        {"run_id": "r-13", "events": [{"kind": "parked", "card": a, "run_id": "r-13", "text": "which flow?"}]},
        LANDER,
    )
    st.write_set(a, ['status="draft"', 'title="Needs another look"'], OWNER)
    st.land({"run_id": "r-1", "events": []}, LANDER)
    assert st.state["cards"][f"{a:04d}"]["execution"] is None
    st.ratify([a], OWNER)
    st.land({"run_id": "r-2", "events": []}, LANDER)
    proj = st.projections()[a]
    assert proj.label.row == "ready" and proj.ready is True


# ---- S7: answered then demoted, both responses in order -----------------------------------------------------------


def test_a_park_answered_then_demoted_keeps_both_responses_in_order() -> None:
    evs = [
        _ev(1, 7, "dispatched", run_id="r-13"),
        _ev(2, 7, "parked", run_id="r-13"),
        _ev(3, 7, "answered", seq=4),
        _ev(4, 7, "demoted", seq=5),
    ]
    card = events_mod.fold(evs, "c", "2026-09-15T00:00:00Z", {"seq": 1, "h": "j"}, {})["cards"]["0007"]
    assert card["execution"] is None
    assert card["runs"] == [
        {
            "run_id": "r-13",
            "outcome": "parked",
            "ended_at": "2026-09-15T00:00:02Z",
            "responses": [
                {"act": "answered", "card_seq": 4, "at": "2026-09-15T00:00:03Z"},
                {"act": "demoted", "card_seq": 5, "at": "2026-09-15T00:00:04Z"},
            ],
        }
    ]
    # once execution clears, a later act adds no further response (R6) — the card's own history keeps it instead.
    card2 = events_mod.fold(
        [*evs, _ev(5, 7, "withdrawn", seq=6)], "c", "2026-09-15T00:00:00Z", {"seq": 1, "h": "j"}, {}
    )["cards"]["0007"]
    assert card2["execution"] is None
    assert len(card2["runs"]) == 1
    assert len(card2["runs"][0]["responses"]) == 2


# ---- C5/C6: total over the acts the store cannot itself emit -------------------------------------------------------


def test_the_fold_is_total_over_acts_the_store_cannot_emit() -> None:
    # C5: an act naming no `seq` still appends its response, with `card_seq` absent — never null, never a raise.
    seqless = [_ev(1, 9, "dispatched", run_id="r-1"), _ev(2, 9, "parked", run_id="r-1"), _ev(3, 9, "answered")]
    card = events_mod.fold(seqless, "c", "2026-09-15T00:00:00Z", {"seq": 1, "h": "j"}, {})["cards"]["0009"]
    assert card["runs"][0]["responses"] == [{"act": "answered", "at": "2026-09-15T00:00:03Z"}]
    assert "card_seq" not in card["runs"][0]["responses"][0]

    # C6: the store never emits `answered` with no park before it, but the fold must survive any file.
    unparked = [_ev(1, 10, "answered", seq=1)]
    card_a = events_mod.fold(unparked, "c", "2026-09-15T00:00:00Z", {"seq": 1, "h": "j"}, {})["cards"]["0010"]
    assert card_a["execution"] == "answered" and card_a["runs"] == []

    card_b = events_mod.fold(
        [*unparked, _ev(2, 10, "demoted", seq=2)], "c", "2026-09-15T00:00:00Z", {"seq": 1, "h": "j"}, {}
    )["cards"]["0010"]
    assert card_b["execution"] is None and card_b["runs"] == []
