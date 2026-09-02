"""The grammar's rejections and invariants (03 §9.1) — the r6 `s_grammar_rejections` scenarios as unit tests."""

from __future__ import annotations

from typing import Any

import pytest

from isidium.store.core import grammar
from isidium.store.core.grammar import CARD, PAGE, Document
from isidium.store.core.refusal import Refusal

ENTRY: dict[str, Any] = {
    "seq": 1,
    "at": "t",
    "by": "b",
    "act": "created",
    "fields": [],
    "build": "sha256:0",
    "h": "sha256:0",
}


def base_doc() -> str:
    head = {
        "schema": 1,
        "id": 42,
        "kind": "story",
        "status": "ratified",
        "source": "session",
        "title": "cards check",
        "shape": "bdd",
        "narrative": {"feature": "x"},
        "rules": [{"id": "R1", "text": "a rule"}],
        "acceptance": {
            "scenarios": [
                {
                    "id": "S1",
                    "kind": "command",
                    "rule": "R1",
                    "title": "t",
                    "action": {"run": ["x"]},
                    "observable": {"exit_code": 0},
                }
            ]
        },
    }
    return grammar.emit_markdown(Document(head, {"Scope": "the scope"}, [dict(ENTRY)]), CARD)


def expect(rule: str, fn: Any) -> None:
    with pytest.raises(Refusal) as ei:
        fn()
    assert ei.value.rule == rule, str(ei.value)


def test_rejections() -> None:
    base = base_doc()
    expect("head.bom", lambda: grammar.parse_markdown("﻿" + base, CARD))
    expect("head.fence", lambda: grammar.parse_markdown("\n" + base, CARD))
    expect("body.history-position", lambda: grammar.parse_markdown(base + "\n## Scope\n\nlate\n", CARD))
    expect("body.history-shape", lambda: grammar.parse_markdown(base.replace("]\n```\n", "]\n```\ntrailing\n"), CARD))
    expect(
        "head.fence-in-string",
        lambda: grammar.parse_markdown(
            base.replace('title = "cards check"', 'title = """cards\n```\nx"""\nt = "', 1), CARD
        ),
    )
    expect(
        "body.section-missing",
        lambda: grammar.parse_markdown(
            "```toml\nschema = 1\n```\n\n## History\n\n```toml\nhistory = [\n]\n```\n", PAGE
        ),
    )
    expect("body.history-missing", lambda: grammar.parse_markdown("```toml\nschema = 1\n```\n\n## Scope\n\nx\n", CARD))


def test_table_order_is_pinned() -> None:
    base = base_doc()
    # [narrative] after [[acceptance.scenarios]] is out of the pinned order (1.1)
    tail_moved = base.replace('\n[narrative]\nfeature = "x"\n', "", 1)
    tail_moved = tail_moved.replace("```\n\n## Scope", '\n[narrative]\nfeature = "x"\n```\n\n## Scope', 1)
    expect("head.table-order", lambda: grammar.parse_markdown(tail_moved, CARD))
    assert grammar.parse_markdown(base, CARD).head["narrative"] == {"feature": "x"}


def test_other_heading_is_unclassified() -> None:
    p = grammar.parse_markdown(base_doc().replace("## Scope", "## Brief"), CARD)
    assert "## Brief" in p.unclassified and p.scope() is None


def test_crlf_preserved_on_append_and_ignored_for_parse() -> None:
    base = base_doc()
    crlf = base.replace("\n", "\r\n")
    appended = grammar.append_history_line(
        crlf, {**ENTRY, "seq": 2, "act": "noted", "fields": ["updates"], "h": "sha256:1"}
    )
    assert "\n" not in appended.replace("\r\n", "") and appended.count("\r\n") == crlf.count("\r\n") + 1
    assert grammar.parse_markdown(crlf, CARD).head == grammar.parse_markdown(base, CARD).head
    assert grammar.parse_markdown(crlf, CARD).newline == "\r\n"


def test_fixed_point_and_line_insertion() -> None:
    base = base_doc()
    doc = grammar.parse_markdown(base, CARD)
    assert grammar.emit_markdown(doc, CARD) == base
    assert base.endswith("\n]\n```\n")
    e2 = {**ENTRY, "seq": 2, "act": "noted", "fields": ["updates"], "h": "sha256:1"}
    appended = grammar.append_history_line(base, e2)
    assert grammar.parse_markdown(appended, CARD).history == [ENTRY, e2]
    assert appended.startswith(base[: -len("]\n```\n")])


def test_history_entry_key_order_enforced() -> None:
    base = base_doc()
    bad = base.replace('{ seq = 1, at = "t", by = "b"', '{ at = "t", seq = 1, by = "b"', 1)
    expect("body.history-shape", lambda: grammar.parse_markdown(bad, CARD))


def test_updates_blocks_parse_and_emit() -> None:
    head = {"schema": 1, "id": 1, "kind": "story", "status": "draft", "source": "session", "title": "t"}
    doc = Document(
        head,
        {
            "Updates": [
                {"date": "2026-08-20", "title": "filed", "body": "first"},
                {"date": "2026-08-21", "title": "", "body": "second\n\nmore"},
            ]
        },
        [dict(ENTRY)],
    )
    raw = grammar.emit_markdown(doc, CARD)
    p = grammar.parse_markdown(raw, CARD)
    assert p.updates() == doc.updates()
    assert grammar.emit_markdown(p, CARD) == raw


def test_config_round_trip_and_grammar() -> None:
    from isidium.store.registry.config import CONFIG_ORDERS

    tree = {
        "schema": 1,
        "tenant": "t",
        "toolkit": {"client": "0.1.0", "registry": "0.1.0", "unidata": "16.0.0", "object_id": "sha1"},
        "payload": {"context": {"depth": 3}},
        "governed": [{"path": "cards/*.md", "schema": "card@1", "write": ["owner"]}],
    }
    hist = [dict(ENTRY)]
    text = grammar.emit_config(tree, hist, CONFIG_ORDERS)
    assert "[payload.context]" in text and text.rstrip().endswith("]")
    back, entries, rs = grammar.parse_config(text, CONFIG_ORDERS)
    assert rs == [] and back == tree and entries == hist
    # scalars out of order; [history] not last; a bad entries line
    _, _, rs = grammar.parse_config(text.replace('schema = 1\ntenant = "t"', 'tenant = "t"\nschema = 1'), CONFIG_ORDERS)
    assert [r.rule for r in rs] == ["head.scalar-order"]
    _, _, rs = grammar.parse_config(text + "\n[board]\ncommit = true\n", CONFIG_ORDERS)
    assert "head.history-position" in [r.rule for r in rs]
