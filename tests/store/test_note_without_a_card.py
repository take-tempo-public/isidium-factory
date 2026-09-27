"""R1/R2/R3 — accepting a suggestion as a note when the suggestion names no card.

Found 2026-09-23: `Store.disposition`'s `elif as_ == "note":` arm read `int(intake["proposed_for"])` first, so a
suggestion with no `proposed_for` raised a bare `KeyError` that reached the owner as a generic `service.arguments`
refusal rather than one naming the suggestion (R1). The fix reads the key before touching it and refuses
`inbox.note-no-card`, ahead of every write the disposition would otherwise make (R2).

`test_a_note_with_a_card_still_notes_it` (S3) passes on unmodified code — it is today's behavior (R3), not a
discriminator for R1's guard. Its job is the other direction: it fails if the guard is widened past the missing-key
case (a `proposed_for` that names a card must still be noted, unchanged).
"""

from __future__ import annotations

import pytest

from isidium.store.core.disclosure import RULES, Disclosure, Row, row_of
from isidium.store.core.refusal import Refusal

from .conftest import OWNER, PLANNER, fresh, path_of


def test_a_note_naming_no_card_is_refused_by_its_own_rule() -> None:
    h = fresh()
    r = h.st.suggest(PLANNER, "docs", "a suggestion with nowhere to land", "body", source="session")
    sid = r.entry["id"]
    with pytest.raises(Refusal) as ei:
        h.st.disposition(sid, "accepted", OWNER, as_="note")
    refusal = ei.value
    assert refusal.rule == "inbox.note-no-card"
    assert refusal.path == "proposed_for"
    assert sid in refusal.detail
    # C1: the id is declared in the table by name, not left to fall through to the namespace's row alone.
    assert RULES["inbox.note-no-card"] == Row(422, Disclosure.FULL)
    assert row_of("inbox.note-no-card").disclosure is Disclosure.FULL


def test_the_refused_disposition_writes_nothing() -> None:
    h = fresh()
    r = h.st.suggest(PLANNER, "docs", "a suggestion with nowhere to land", "body", source="session")
    sid = r.entry["id"]
    journal_head = h.st.journal.head
    inbox_len = len(h.st.inbox)
    suggestions_bytes = h.st.raw["suggestions.jsonl"]
    repo_head = h.st.repo.head
    with pytest.raises(Refusal):
        h.st.disposition(sid, "accepted", OWNER, as_="note")
    assert h.st.journal.head == journal_head
    assert len(h.st.inbox) == inbox_len
    assert h.st.raw["suggestions.jsonl"] == suggestions_bytes
    assert h.st.repo.head == repo_head
    assert not any(rec.get("type") == "disposition" and rec.get("on") == sid for rec in h.st.inbox)


def test_a_note_with_a_card_still_notes_it() -> None:
    h = fresh()
    cid = h.draft("noted-card")
    r = h.st.suggest(PLANNER, "docs", "a suggestion for this card", "body", source="session", proposed_for=cid)
    sid = r.entry["id"]
    out = h.st.disposition(sid, "accepted", OWNER, as_="note")
    assert out["note"].landed
    updates = h.st.docs[path_of(h.st, cid)].updates()
    assert updates[-1]["title"] == f"suggestion {sid}"
    assert updates[-1]["body"] == f"see {sid}"
    assert h.st.inbox[-1]["type"] == "disposition"
    assert h.st.inbox[-1]["on"] == sid
    assert h.st.inbox[-1]["card"] == cid
