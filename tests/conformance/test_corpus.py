"""The G4 corpus (03 §5.3): equal pairs hash equal, differ pairs differ — and every fixture card file's recorded
`build` (written by the r6 oracle) is reproduced byte-for-byte from the parsed file."""

from __future__ import annotations

from typing import Any

import pytest

from isidium.store.core import canon, grammar

from .conftest import R6


def test_corpus_pairs(corpus: list[dict[str, Any]]) -> None:
    failures = []
    for item in corpus:
        gx = frozenset(item.get("gated_x", []))
        a = canon.build_hash(item["a"]["head"], item["a"]["scope"], gx)
        b = canon.build_hash(item["b"]["head"], item["b"]["scope"], gx)
        if (a == b) != (item["expect"] == "equal"):
            failures.append(f"{item['name']}: expected {item['expect']} got {a[:19]} vs {b[:19]}")
    assert not failures, "\n".join(failures)


@pytest.mark.parametrize("side", ["a", "b"])
def test_fixture_files_reproduce_oracle_build_hash(corpus: list[dict[str, Any]], side: str) -> None:
    """Parse the oracle's card file, hash it, compare with the `build` the oracle wrote into its footer."""
    failures = []
    for item in corpus:
        path = R6 / f"corpus-{item['name']}-{side}.md"
        raw = path.read_text(encoding="utf-8", newline="")
        doc = grammar.parse_markdown(raw, grammar.CARD)
        got = canon.build_hash(doc.head, doc.scope(), frozenset(item.get("gated_x", [])))
        want = doc.history[0]["build"]
        if got != want:
            failures.append(f"{path.name}: {got} != {want}")
    assert not failures, "\n".join(failures)


@pytest.mark.parametrize("side", ["a", "b"])
def test_fixture_files_emit_fixed_point(corpus: list[dict[str, Any]], side: str) -> None:
    """parse -> emit -> the same bytes (the authoring order of 4.3; the footer shape of 9.1) — for a file whose line
    endings are uniform (H2: writes preserve the file's own; a mixed file has none — the crlf-vs-lf-b fixture carries
    CRLF inside Scope by construction and normalizes)."""
    failures = []
    for item in corpus:
        path = R6 / f"corpus-{item['name']}-{side}.md"
        raw = path.read_text(encoding="utf-8", newline="")
        if "\r\n" in raw and raw.count("\r\n") != raw.count("\n"):
            continue
        doc = grammar.parse_markdown(raw, grammar.CARD)
        if grammar.emit_markdown(doc, grammar.CARD) != raw:
            failures.append(path.name)
    assert not failures, "not a fixed point: " + ", ".join(failures)


def test_file_level_equalities() -> None:
    """A TOML comment, an Updates append and CRLF never move the build hash (5.3 corpus minimum)."""
    raw = (R6 / "corpus-key-order-a.md").read_text(encoding="utf-8", newline="")
    base = grammar.parse_markdown(raw, grammar.CARD)
    h0 = canon.build_hash(base.head, base.scope())
    with_comment = grammar.parse_markdown(raw.replace("schema = 1", "schema = 1 # a comment", 1), grammar.CARD)
    assert canon.build_hash(with_comment.head, with_comment.scope()) == h0
    crlf = grammar.parse_markdown(raw.replace("\n", "\r\n"), grammar.CARD)
    assert canon.build_hash(crlf.head, crlf.scope()) == h0
    appended = grammar.parse_markdown(
        raw.replace("## History", "## Updates\n\n### 2026-08-21 — later\n\nmore\n\n## History", 1), grammar.CARD
    )
    assert canon.build_hash(appended.head, appended.scope()) == h0
