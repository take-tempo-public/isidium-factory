"""The ordering key over the ready-view — a pure function [V3; 02-prioritization §2, design owner-ratified 2026-08-16].

*"Lexicographic tiers; within a tier, deterministic"*: **Tier 0** the expedite lane (`class_of_service = "expedite"`,
at most `[prioritization].expedite_limit` in flight — the dial is the caller's `expedite_open`); **Tier 1** the
priority class `P0 > P1 > P2 > P3`; **Tier 2** the composite over the six weighted terms — **written as zeros** here,
the seam visible in every run's `score` (the briefing: *"records the rest as the seam"*; the composite is the picker's
next chunk, not V3's); **Tier 3** *"Oldest ratification first, then card id. Always total; never random."*

The inputs are the cards' heads at `base_sha` — the substrate, never the board (T-C3 (ii)) — read by the caller in
two spawns however many cards there are (`checkout.heads`). Nothing here reads a default: a card with no
`class_of_service` is simply not in the expedite lane, and one with no `priority` (a leaf kind the profile does not
require it of) sorts after `P3` [proposed — the design names four classes and no fifth].
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Final

from isidium.store.core import telemetry
from isidium.store.core.grammar import Document

SPAN: Final = "isidium.factory.ordering"
PRIORITIES: Final[tuple[str, ...]] = ("P0", "P1", "P2", "P3")
EXPEDITE: Final = "expedite"
# 03 §6's `score.vector`, in its written order — the six terms Tier 2 will weigh.
VECTOR: Final[tuple[str, ...]] = ("time_criticality", "unblocking", "resume", "aging", "batch", "risk")


@dataclass(frozen=True)
class Head:
    """What the key reads off one card: its id, lane, class and the time of the ratification that made it ready."""

    card: int
    expedite: bool
    priority: str | None
    ratified_at: str

    @classmethod
    def of(cls, card: int, doc: Document) -> Head:
        cos = doc.head.get("class_of_service")
        pr = doc.head.get("priority")
        return cls(card, cos == EXPEDITE, pr if isinstance(pr, str) else None, ratified_at(doc))


def ratified_at(doc: Document) -> str:
    """The `at` of the card's last ratification — a `ratified` entry, or the `created` entry of a card born
    ratified in a sitting; `""` for a card with neither (none is in the ready-view)."""
    for e in reversed(doc.history):
        if e.get("act") == "ratified" or (e.get("act") == "created" and doc.head.get("status") == "ratified"):
            return str(e.get("at", ""))
    return ""


@dataclass(frozen=True, order=True)
class OrderKey:
    """The tiers as a typed tuple (C-2); smaller sorts first."""

    lane: int  # 0 = expedite (when the dial is open), 1 = otherwise
    priority: int  # the index in PRIORITIES; len(PRIORITIES) when absent
    composite: int  # Tier 2 — 0 until the composite is built (the seam); negated when it is, larger first
    ratified_at: str
    card: int


@dataclass(frozen=True)
class Ranked:
    card: int
    rank: int
    key: OrderKey
    expedite: bool

    def score(self, config_hash: str) -> dict[str, Any]:
        """03 §6's `score {rank, vector {…}, config_hash}` — the vector all zeros until Tier 2 exists."""
        return {"rank": self.rank, "vector": dict.fromkeys(VECTOR, 0), "config_hash": config_hash}


def key(h: Head, *, expedite_open: bool) -> OrderKey:
    pr = PRIORITIES.index(h.priority) if h.priority in PRIORITIES else len(PRIORITIES)
    return OrderKey(0 if h.expedite and expedite_open else 1, pr, 0, h.ratified_at, h.card)


def order(heads: Iterable[Head], *, expedite_open: bool) -> tuple[Ranked, ...]:
    """Every ready card ranked, total: the same set in any order gives the same tuple."""
    with telemetry.span(SPAN) as sp:
        keyed = sorted(((key(h, expedite_open=expedite_open), h) for h in heads), key=lambda kh: kh[0])
        sp.set_attribute("isidium.ready", len(keyed))
        return tuple(Ranked(h.card, i, k, h.expedite and expedite_open) for i, (k, h) in enumerate(keyed))


def expedite_open(in_flight: Iterable[Mapping[str, Any]], limit: int) -> bool:
    """The dial: *"at most `expedite_limit` in flight"* — open while fewer expedite runs are in flight."""
    return sum(1 for r in in_flight if r.get("lane") == EXPEDITE) < limit
