"""Card 9 — the open-inbox rule has one home.

Which intake records are still open used to be decided twice: `status.queue` built the open-id set to produce
`inbox_counts`, and `board.render` rebuilt the same set, independently, to print the `## Inbox` list. Both answers
land in the same document — `BOARD.md`'s header and the list directly below it — so a change to one without the
other would make two adjacent lines disagree, and nothing would fail. `status.open_intake_ids` is now the one
function both read (R1), the same move card 7 R5 made for `IN_FLIGHT` (`test_fold_abandons.py`).

What each test discriminates:

- **R1** (`test_the_board_list_and_the_inbox_counts_read_one_open_set`): `board.open_intake_ids` is the identical
  object `status.open_intake_ids` is, not a copy — and, end to end, a mix of an open, a declined and an accepted
  intake leaves the header's count and the rendered list agreeing on the one that is still open.
- **R2** (`test_a_deferred_disposition_leaves_its_intake_open_in_both`): a `deferred` disposition is neither
  `accepted` nor `declined`, so it leaves its intake open in the count and in the list alike — the one outcome the
  card's scope calls out by name.
"""

from __future__ import annotations

from isidium.store.core import board as board_mod
from isidium.store.core import status as status_mod

from .conftest import OWNER, PLANNER, fresh


def test_the_board_list_and_the_inbox_counts_read_one_open_set() -> None:
    assert board_mod.open_intake_ids is status_mod.open_intake_ids, "board reads the same function, not its own copy"

    hz = fresh()
    st = hz.st
    st.suggest(PLANNER, "docs", "keep this one open", "body", source="planner")
    st.suggest(PLANNER, "docs", "decline this one", "body", source="planner")
    st.suggest(PLANNER, "docs", "accept this one", "body", source="planner")
    st.disposition("s2", "declined", OWNER, reason="not now")
    st.disposition("s3", "accepted", OWNER, as_="card", slug="from-s3")

    assert status_mod.open_intake_ids(st.inbox) == {"s1"}, "only the undispositioned intake is open"
    q = st.show("Queue")
    assert q.inbox_counts == {"planner": 1}, "the header counts the same one open intake"
    board = st.show("Board")
    assert "- s1 ·" in board and "- s2 ·" not in board and "- s3 ·" not in board, "the list agrees with the count"


def test_a_deferred_disposition_leaves_its_intake_open_in_both() -> None:
    hz = fresh()
    st = hz.st
    st.suggest(PLANNER, "docs", "circle back later", "body", source="planner")
    st.disposition("s1", "deferred", OWNER, until="the next audit")

    assert status_mod.open_intake_ids(st.inbox) == {"s1"}, "deferred is neither accepted nor declined"
    q = st.show("Queue")
    assert q.inbox_counts == {"planner": 1}, "a deferred intake still counts as open"
    board = st.show("Board")
    assert "- s1 ·" in board, "a deferred intake still renders in the list"
