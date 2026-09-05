"""The G4 corpus (03 §5.3): equal pairs hash equal, differ pairs differ — and every fixture card file's recorded
`build` (written by the r6 oracle) is reproduced byte-for-byte from the parsed file."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from isidium.store.core import canon, grammar

from .conftest import R6


def read_untranslated(path: Path) -> str:
    """The fixture's own line endings, exactly as they sit on disk. This corpus is about bytes — a CRLF fixture
    that arrives as LF proves nothing. `read_text(newline="")` says the same thing, but it is 3.13+ while the
    package declares `>=3.12` and the container ships 3.12; decoding the bytes translates nothing on any version
    [K5, 2026-09-04, the Python pin ruled to a 3.12/3.13 matrix].

    **An earlier draft of this docstring claimed two tests below turn on that difference. They do not**, and a
    mutation putting `read_text` back survived the whole suite to prove it: the build hash is CRLF-invariant by
    design, the fixed-point test *skips* the mixed CRLF fixture (and the mutation removes the mixedness that
    triggers the skip), and `test_file_level_equalities` reads an all-LF file and makes its own CRLF. The one
    test that can see it is the next one, written because the mutation survived."""
    return path.read_bytes().decode("utf-8")


def test_the_reader_hands_back_the_bytes_the_fixture_actually_holds() -> None:
    """**The discriminator for `read_untranslated`.** Universal-newline decoding is invisible everywhere else in
    this file, so without this the reader could quietly go back to translating CRLF into LF and nothing would
    fail. The fixture is asserted to hold CRLF *on disk* first: if it ever lost it, this test would otherwise
    pass while proving nothing, which is the failure mode this project refuses."""
    path = R6 / "corpus-crlf-vs-lf-b.md"
    on_disk = path.read_bytes()
    assert b"\r\n" in on_disk, f"{path.name} is the CRLF fixture; with no CRLF on disk this proves nothing"

    raw = read_untranslated(path)
    assert raw.count("\r\n") == on_disk.count(b"\r\n"), "a CRLF was translated away on the way in"
    assert raw.encode("utf-8") == on_disk, "the reader did not hand back the file's own bytes"


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
        raw = read_untranslated(path)
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
        raw = read_untranslated(path)
        if "\r\n" in raw and raw.count("\r\n") != raw.count("\n"):
            continue
        doc = grammar.parse_markdown(raw, grammar.CARD)
        if grammar.emit_markdown(doc, grammar.CARD) != raw:
            failures.append(path.name)
    assert not failures, "not a fixed point: " + ", ".join(failures)


def test_file_level_equalities() -> None:
    """A TOML comment, an Updates append and CRLF never move the build hash (5.3 corpus minimum)."""
    raw = read_untranslated(R6 / "corpus-key-order-a.md")
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
