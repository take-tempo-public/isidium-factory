"""The chain (5.5), the closure-entry hash (5.2), the signed bytes and the batch form (5.6), the non-card geneses
(03b §3) — against the r6 oracle's chain.json, byte-for-byte."""

from __future__ import annotations

from typing import Any

from isidium.store.core import canon, chain


def test_genesis_per_document_type(chain_fixture: dict[str, Any]) -> None:
    assert chain.genesis("card", 42) == chain_fixture["genesis"]
    assert chain.genesis("inbox", "sartor") == chain_fixture["inbox_genesis"]
    assert chain.genesis("policy", "sartor") == chain_fixture["policy_genesis"]
    assert chain.genesis("journal", "sartor") == chain_fixture["journal_genesis"]
    assert chain.genesis("page", "pages/conventions.md") == chain_fixture["page_genesis"]


def test_links_recompute(chain_fixture: dict[str, Any]) -> None:
    prev = chain_fixture["genesis"]
    for entry in chain_fixture["entries"]:
        assert chain.link(prev, entry) == entry["h"], entry["seq"]
        prev = entry["h"]
    assert chain.verify_chain(chain_fixture["entries"], chain_fixture["genesis"]) == ["ok"] * 4


def test_batch_member_carries_batch_only(chain_fixture: dict[str, Any]) -> None:
    e3 = chain_fixture["entries"][2]
    assert "batch" in e3 and "sig" not in e3
    # sig and batch are outside the chain content: the link ignores them
    assert chain.link(chain_fixture["entries"][1]["h"], {k: v for k, v in e3.items() if k != "batch"}) == e3["h"]


def test_closure_ref(chain_fixture: dict[str, Any]) -> None:
    assert canon.closure_ref(chain_fixture["closure"]) == chain_fixture["closure_ref"]
    assert chain_fixture["entries"][3]["ref"] == chain_fixture["closure_ref"]


def test_signed_bytes_and_batch_hash(chain_fixture: dict[str, Any]) -> None:
    hs = [e["h"] for e in chain_fixture["entries"][:3]]
    assert chain.sig_bytes("sartor", chain_fixture["entries"][2]["h"]).decode() == chain_fixture["sig_bytes_single"]
    assert chain.batch_hash(hs) == chain_fixture["batch_hash"]
    assert chain.sig_bytes("sartor", chain.batch_hash(hs)).decode() == chain_fixture["sig_bytes_batch"]
