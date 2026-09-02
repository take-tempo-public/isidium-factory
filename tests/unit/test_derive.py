"""`derive` — the recompute table (03 §1.2), the append-only rules, the signature predicate and its draft-6 pins."""

from __future__ import annotations

import copy
from typing import Any

import pytest

from isidium.store.core import derive
from isidium.store.core.grammar import Document
from isidium.store.core.refusal import Refusal


def head(**over: Any) -> dict[str, Any]:
    h: dict[str, Any] = {
        "schema": 1,
        "id": 7,
        "kind": "story",
        "status": "ratified",
        "source": "session",
        "title": "t",
        "shape": "bdd",
        "surfaces": ["src/a.py"],
    }
    h.update(over)
    return h


def doc(
    h: dict[str, Any], scope: str = "s", updates: list[dict[str, str]] | None = None, signed: bool = False
) -> Document:
    sections: dict[str, Any] = {"Scope": scope}
    if updates is not None:
        sections["Updates"] = copy.deepcopy(updates)
    hist = [
        {
            "seq": 1,
            "at": "t",
            "by": "b",
            "act": "created",
            "fields": [],
            "build": "sha256:0",
            "h": "sha256:0",
            **({"sig": "ed25519:f:AA=="} if signed else {}),
        }
    ]
    return Document(copy.deepcopy(h), sections, hist)


@pytest.mark.parametrize(
    ("before", "after", "ref", "act", "fields"),
    [
        (None, head(status="draft"), None, "created", None),
        (head(status="draft"), head(), None, "ratified", ["status"]),
        (head(), head(title="t2"), None, "ratified", ["title"]),  # re-ratification (W2)
        (head(), head(status="draft"), None, "demoted", ["status"]),
        (head(), head(status="withdrawn", withdrawn_reason="r"), None, "withdrawn", ["status", "withdrawn_reason"]),
        (head(status="withdrawn", withdrawn_reason="r"), head(), None, "unwithdrawn", ["status", "withdrawn_reason"]),
        (
            head(),
            head(status="closed", closures=[{"id": "c1", "kind": "human", "outcome": "met", "retracted": False}]),
            None,
            "closed",
            ["closures", "status"],
        ),
        (
            head(status="closed", closures=[{"id": "c1", "kind": "human", "outcome": "met", "retracted": False}]),
            head(status="closed", closures=[{"id": "c1", "kind": "human", "outcome": "met", "retracted": True}]),
            None,
            "retracted",
            ["closures"],
        ),
        (head(), head(hold={"kind": "blocked", "on": {"owner": True}}), None, "held", ["hold"]),
        (
            head(hold={"kind": "blocked", "on": {"owner": True}}),
            head(hold={"kind": "deferred", "on": {"owner": True}}),
            None,
            "held",
            ["hold"],
        ),
        (head(hold={"kind": "blocked", "on": {"owner": True}}), head(), None, "released", ["hold"]),
        (
            head(hold={"kind": "blocked", "on": {"owner": True}}),
            head(hold={"kind": "watching"}),
            None,
            "released",
            ["hold"],
        ),
        (
            head(status="draft", questions=[{"id": "Q1", "text": "?"}]),
            head(status="draft", questions=[], answers=[{"question_id": "Q1", "text": "a"}]),
            None,
            "answered",
            ["answers", "questions"],
        ),
        (head(), head(summary="s"), None, "summarized", ["summary"]),
        (head(), head(), "c1:sha256:00", "accepted", []),
        (head(), head(priority="P0"), None, "amended", ["priority"]),
    ],
)
def test_recompute_table(
    before: dict[str, Any] | None, after: dict[str, Any], ref: Any, act: str, fields: list[str] | None
) -> None:
    d = derive.derive(doc(before) if before else None, doc(after), ref)
    assert d.act == act
    if fields is not None:
        assert d.fields == fields
    else:
        assert "scope" in d.fields and "title" in d.fields


def test_answer_on_ratified_card_is_reratification() -> None:
    """C2: on a ratified card an answer is a gated change → `ratified`, fields ⊇ [answers, questions]."""
    b = head(questions=[{"id": "Q1", "text": "?"}])
    a = head(questions=[], answers=[{"question_id": "Q1", "text": "a"}])
    d = derive.derive(doc(b), doc(a), None)
    assert d.act == "ratified" and {"answers", "questions"} <= set(d.fields)


def test_noted_and_diff_over_canonical_prose() -> None:
    b = doc(head(), updates=[{"date": "2026-08-20", "title": "x", "body": "first"}])
    a = doc(
        head(),
        updates=[
            {"date": "2026-08-20", "title": "x", "body": "first"},
            {"date": "2026-08-21", "title": "y", "body": "second"},
        ],
    )
    assert derive.derive(b, a, None).act == "noted"
    # CRLF and trailing whitespace in Scope are no change
    assert derive.derive(doc(head(), "line one\nline two"), doc(head(), "line one  \r\nline two\n"), None).diff == []


def test_append_only_refusals() -> None:
    b = doc(head(), updates=[{"date": "2026-08-20", "title": "x", "body": "first"}])
    a = doc(head(), updates=[{"date": "2026-08-20", "title": "x", "body": "REWRITTEN"}])
    with pytest.raises(Refusal, match=r"log\.rewritten"):
        derive.derive(b, a, None)
    cb = head(status="closed", closures=[{"id": "c1", "kind": "human", "outcome": "met", "retracted": False}])
    ca = head(
        status="closed",
        closures=[{"id": "c1", "kind": "human", "outcome": {"deviated": {"description": "x"}}, "retracted": False}],
    )
    with pytest.raises(Refusal, match=r"claims\.rewritten"):
        derive.derive(doc(cb), doc(ca), None)
    with pytest.raises(Refusal, match=r"write\.deletion"):
        derive.derive(doc(head()), None, None)
    sb = doc(head(see=["a"]))
    with pytest.raises(Refusal, match=r"log\.rewritten"):
        derive.derive(sb, doc(head(see=["b"])), None)


def test_questions_dropped_bound_to_signed_cards() -> None:
    b, a = head(status="draft", questions=[{"id": "Q1", "text": "?"}]), head(status="draft", questions=[])
    assert derive.derive(doc(b), doc(a), None).act == "amended"  # a draft's author may delete its own question
    with pytest.raises(Refusal, match=r"questions\.dropped-unanswered"):
        derive.derive(doc(b, signed=True), doc(a), None)


def test_signature_predicate_pins() -> None:
    ns = derive.needs_signature
    assert ns(None, head(), [], None) == "born-ratified"
    assert ns(None, head(status="draft"), [], None) is None
    assert ns(head(status="draft"), head(), ["status"], None) == "more-active"
    assert ns(head(), head(title="x"), ["title"], None) == "gated-on-ratified"
    assert ns(head(), head(summary="x"), ["summary"], None) is None
    assert ns(head(hold={"kind": "blocked", "on": {"owner": True}}), head(), ["hold"], None) == "hold-release"
    assert (
        ns(
            head(hold={"kind": "blocked", "on": {"owner": True}}),
            head(hold={"kind": "deferred", "on": {"owner": True}}),
            ["hold"],
            None,
        )
        is None
    )
    assert ns(head(), head(), [], "c1:sha256:00") == "accept"
    assert ns(None, {}, [], 3) == "repair"
    assert ns(None, {}, [], None, is_policy=True) == "policy"
    # C5/C6: the contributor's retraction — exempt before a land, not after, and not with a gated key riding along
    cb = head(status="closed", closures=[{"id": "c1", "kind": "human", "outcome": "met", "retracted": False}])
    ca = head(closures=[{"id": "c1", "kind": "human", "outcome": "met", "retracted": True}])
    assert ns(cb, ca, ["closures", "status"], None) is None
    assert ns(cb, ca, ["closures", "status"], None, landed_closures=frozenset({"c1"})) == "more-active"
    assert ns(cb, {**ca, "title": "x"}, ["closures", "status", "title"], None) == "more-active"
    # the owner's own closed is the caller-aware clause, not the predicate
    assert ns(head(), cb, ["closures", "status"], None) is None
    assert "closed" in derive.OWNER_SIGNS_ALSO


def test_replay_status() -> None:
    rs = derive.replay_status
    assert rs([{"act": "created"}]) == "draft"
    assert rs([{"act": "created", "sig": "x"}]) == "ratified"
    assert rs([{"act": "created"}, {"act": "ratified", "batch": 3}, {"act": "demoted"}]) == "draft"
    assert rs([{"act": "created"}, {"act": "ratified"}, {"act": "closed"}, {"act": "retracted"}]) == "ratified"
