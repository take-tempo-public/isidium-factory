"""The conformance oracles as tests (03 §5.3): the round-6 corpus and chain fixtures under fixtures/r6,
and impl-d1's config fixtures under fixtures/d1. The build is the fifth hasher; it must match.

Provenance, stated exactly [2026-09-02]: the r6 fixtures derive from the sealed four-prototype oracle
(review-artifacts/2026-08-21-round6/r6-impl-d6/fixtures, private, byte-for-byte) by ONE change — the principal
addresses were renamed to the `.example` fixture convention, and chain.json's entry hashes, batch hash and
sig-bytes were recomputed by the pinned algorithms, because `by`/`for` sit inside hash-chained content. The
corpus `build` values are untouched: the rename lives in the history footer, which `build_hash` does not cover.
The d1 fixtures — real signatures over `.example` principals — are byte-for-byte originals and still anchor the
algorithms across implementations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
R6 = FIXTURES / "r6"
D1 = FIXTURES / "d1"


@pytest.fixture(scope="session")
def corpus() -> list[dict[str, Any]]:
    data: list[dict[str, Any]] = json.loads((R6 / "corpus.json").read_text(encoding="utf-8"))
    return data


@pytest.fixture(scope="session")
def chain_fixture() -> dict[str, Any]:
    data: dict[str, Any] = json.loads((R6 / "chain.json").read_text(encoding="utf-8"))
    return data
