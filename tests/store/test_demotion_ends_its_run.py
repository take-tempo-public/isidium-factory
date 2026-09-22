"""Card 10 — a demotion that ends a run in flight is a signed act, so the sidecar hears it.

`derive.needs_signature` had no rule for a bare `ratified -> draft` demotion: the "more-active" clause exempts
every retreat from ratified by design (R2), and nothing else in the predicate looked at whether the card's sidecar
held a run in flight. So the one demotion an owner would actually reach for — pulling a stuck run's card back to
draft, nothing else touched — landed unsigned. `Store._act_events` gates every act event on `chain.is_signed`, so
an unsigned `demoted` entry is never observed at land, and the sidecar kept the run `dispatched` for good (card 9's
wreckage, found live 2026-09-22). The workaround that happened to work — a demotion carrying a gated edit alongside
the status flip — is `test_fold_abandons.py`'s own tests; R1 makes the bare gesture work the same way, by handing
the predicate the one fact `_landed_closures` already models: a fact of the sidecar the caller computes and hands in.

What each test discriminates:

- **S1** (`test_a_bare_demotion_with_a_run_in_flight_is_signed`): a demotion touching only `status`, of a card
  whose sidecar reads a run in flight, is signed — where before this card it was not.
- **S2** (`test_the_landed_demotion_abandons_the_run`): that same demotion, landed, is observed and folds the run
  to `abandoned` — the whole reason R1 exists.
- **S3** (`test_a_demotion_with_nothing_in_flight_stays_unsigned`): a demotion of a card with nothing dispatched
  stays free, exactly as every other retreat from ratified always has (R2).
"""

from __future__ import annotations

from isidium.store.core import chain

from .conftest import LANDER, OWNER, Harness, fresh, path_of


def ratified(hz: Harness, slug: str) -> int:
    cid = hz.draft(slug)
    hz.st.ratify([cid], OWNER)
    return cid


def test_a_bare_demotion_with_a_run_in_flight_is_signed() -> None:
    hz = fresh()
    st = hz.st
    a = ratified(hz, "a")
    st.land({"run_id": "r-0", "events": [{"kind": "dispatched", "card": a, "run_id": "r-0"}]}, LANDER)
    r = st.write_set(a, ['status="draft"'], OWNER)
    assert r.entry["act"] == "demoted"
    assert chain.is_signed(r.entry), "a bare demotion with a run in flight must be signed so the land observes it"


def test_the_landed_demotion_abandons_the_run() -> None:
    hz = fresh()
    st = hz.st
    a = ratified(hz, "a")
    st.land({"run_id": "r-0", "events": [{"kind": "dispatched", "card": a, "run_id": "r-0"}]}, LANDER)
    st.write_set(a, ['status="draft"'], OWNER)
    st.land({"run_id": "r-1", "events": []}, LANDER)
    demoted_at = st.docs[path_of(st, a)].history[-1]["at"]
    card = st.state["cards"][f"{a:04d}"]
    assert card["execution"] == "abandoned"
    assert card["runs"] == [{"run_id": "r-0", "outcome": "abandoned", "ended_at": demoted_at}]


def test_a_demotion_with_nothing_in_flight_stays_unsigned() -> None:
    hz = fresh()
    st = hz.st
    a = ratified(hz, "a")
    r = st.write_set(a, ['status="draft"'], OWNER)
    assert r.entry["act"] == "demoted"
    assert not chain.is_signed(r.entry), "a retreat from ratified with nothing in flight has never needed a signature"
