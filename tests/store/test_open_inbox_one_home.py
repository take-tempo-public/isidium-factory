"""Card 9 — which intake records are still open is decided once, in `status.open_intake_ids`, and `status.queue`'s
`inbox_counts` and `board.render`'s `## Inbox` list both read that one answer instead of each re-deriving it.

R1 is the "one home" itself: `board.py` re-exports the function explicitly (`as open_intake_ids`, the same move as
`IN_FLIGHT`, card 7 R5) rather than importing it plainly, so it type-checks under mypy `--strict` and so the two
call sites are provably the same object, not two definitions that happen to agree today. A behavioral check alone
would not discriminate this — the two sites computed the same thing before this card, too — so the identity
assertion is the test that actually pins R1; the rendered board is checked alongside it because that is what a
tenant reads.

R2 is a specific input to that one function: a disposition outcome that is neither `accepted` nor `declined` (a
`deferred` disposition, or anything else the schema allows) leaves its intake open, in the count and in the list
alike.
"""

from __future__ import annotations

from typing import Any

from isidium.store.core import board as board_mod
from isidium.store.core import status as status_mod


def _inbox(*, second_outcome: str | None = "declined") -> list[dict[str, Any]]:
    """Two intake records, `s1` and `s2`; `s1` is always declined (closed), `s2`'s outcome is the case under test
    — `declined` (closed, the default) or `deferred` (R2: left open) or `None` (no disposition at all)."""
    records: list[dict[str, Any]] = [
        {"type": "intake", "id": "s1", "source": "docs", "kind": "task", "title": "one"},
        {"type": "intake", "id": "s2", "source": "docs", "kind": "task", "title": "two"},
        {"type": "disposition", "on": "s1", "outcome": "declined", "reason": "not now"},
    ]
    if second_outcome is not None:
        records.append({"type": "disposition", "on": "s2", "outcome": second_outcome, "until": "2026-10-01"})
    return records


def _board(inbox: list[dict[str, Any]]) -> str:
    inp = status_mod.Inputs(cards={})
    q = status_mod.queue(inp, {}, inbox, [])
    return board_mod.render({}, {}, q, inbox, wip_ceiling=3)


def test_the_board_list_and_the_inbox_counts_read_one_open_set() -> None:
    """`board.open_intake_ids` is the exact object `status.open_intake_ids` is (R1) — not a second definition that
    happens to agree, the same discipline `IN_FLIGHT` already carries (card 7 R5). With `s1` declined and `s2`
    left undispositioned, both the header's `inbox docs …` count and the rendered `## Inbox` list answer from that
    one function: `s2` alone is open, `s1` is not."""
    assert board_mod.open_intake_ids is status_mod.open_intake_ids
    md = _board(_inbox(second_outcome=None))
    header = md.splitlines()[2]
    section = md[md.index("## Inbox") : md.index("## Open")]
    listed = [line for line in section.splitlines() if line.startswith("- ")]
    assert header.endswith("inbox docs 1"), header
    assert len(listed) == 1 and listed[0].startswith("- s2 ·"), listed
    assert "s1" not in section, section


def test_a_deferred_disposition_leaves_its_intake_open_in_both() -> None:
    """`s2`'s disposition outcome is `deferred` — neither `accepted` nor `declined` — so R2 keeps it open: the
    header count still reads `docs 1` and the `## Inbox` list still names `s2`, not `none` in either."""
    md = _board(_inbox(second_outcome="deferred"))
    header = md.splitlines()[2]
    section = md[md.index("## Inbox") : md.index("## Open")]
    listed = [line for line in section.splitlines() if line.startswith("- ")]
    assert header.endswith("inbox docs 1"), header
    assert len(listed) == 1 and listed[0].startswith("- s2 ·"), listed


def test_declining_both_closes_the_inbox_in_both() -> None:
    """The mirror of R2: once `s2` is `declined` too, neither the count nor the list carries it — the one function
    the same rule the other two tests exercise, on the case that should close rather than the case that should
    not."""
    md = _board(_inbox(second_outcome="declined"))
    header = md.splitlines()[2]
    section = md[md.index("## Inbox") : md.index("## Open")]
    assert header.endswith("inbox 0"), header
    assert "s1" not in section and "s2" not in section, section
