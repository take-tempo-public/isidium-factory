"""The neighborhood projection (03 §1.17) [L5, 2026-09-10] — one deterministic function of (the card graph, the
sidecar, the caps): the parent chain, the siblings, the direct dependencies and dependents, the bound milestone and
sprint, over the cards a builder may take as settled — `ratified` or `closed`, and their build hash equal to the
reference the store would fingerprint them against. Delivered as a typed, delimited block labeled as context; its
canonical bytes are what `payload.context.max_bytes` measures and what v1c's `payload_hash` will cover.

**The block is a typed value; `render()` is the only place the delivered text exists** — status's shape, for the
same reason: the Rust port transcribes it, and nothing matches on a formatted string.

**Eligibility** (the schema's *"whose build hash equals their fingerprint"*, read through H7): a card no run has
dispatched has no fingerprint and is still in — its ratified `build` is what it would be fingerprinted against; a
card that drifted since (row 2 `unratified`) and a card row 1 flags are out. The subject card is never a member and
need not be eligible: a draft's neighborhood is a planner's preview, and dispatch's readiness is v1c's door.

**Buckets**, one table, precedence top to bottom: `held` — a `held`/`held_by` guard, or row `disputed` (a human's
verdict pending); `in-flight` — execution `dispatched` / `parked` / `answered`, or `closed` with a pending modifier;
`built` — `closed` without one, or execution `complete`; `planned` — everything else (`ratified`, `ready`,
`reopened`, execution `failed` / `reverted`).

**Eviction**, in the schema's order, one member a step, until the bytes fit or nothing is left: dependencies then
dependents (highest id first); the parent chain from the farthest level — its Scope to its first paragraph, then to
nothing, then the member —; milestone then sprint the same way; siblings (highest id first). An evicted member's
stub (`id`, `title`, `evicted`) stays in its list, so the builder sees what was dropped with a handle
[owner-ratified 2026-08-27 (7be.3)]; `truncated` is true the moment a step ran. The loop is bounded — each member
evicted once, each Scope truncated twice — and a block whose stubs alone exceed the cap is delivered as it is:
the projection *"never fails readiness"*.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from typing import Any, Final, Literal

from . import canon, status
from .grammar import Document

Bucket = Literal["planned", "in-flight", "built", "held"]

EVICTED: Final = "max_bytes"
FORM: Final = "isidium-context 1"


@dataclass(frozen=True)
class Caps:
    """`[payload.context]` of the effective config: `depth` levels of parent chain, `max_bytes` of canonical block."""

    depth: int
    max_bytes: int


@dataclass(frozen=True)
class Member:
    """One card in the block. Which fields are set says which list it came from: `scope` and `label` for the parent
    chain, `scope` alone for the milestone and sprint, `bucket` for siblings, `bucket` and `surfaces` for the
    dependencies and dependents; `evicted` replaces everything but the handle."""

    id: int
    title: str
    scope: str | None = None
    scope_truncated: bool = False
    label: str | None = None
    bucket: Bucket | None = None
    surfaces: tuple[str, ...] | None = None
    evicted: str | None = None

    def as_dict(self) -> dict[str, Any]:
        if self.evicted is not None:
            return {"id": self.id, "title": self.title, "evicted": self.evicted}
        d: dict[str, Any] = {"id": self.id, "title": self.title}
        if self.label is not None:
            d["label"] = self.label
        if self.bucket is not None:
            d["bucket"] = self.bucket
        if self.surfaces is not None:
            d["surfaces"] = list(self.surfaces)
        if self.scope is not None:
            d["scope"] = self.scope
        if self.scope_truncated:
            d["scope_truncated"] = True
        return d


@dataclass(frozen=True)
class Block:
    card: int
    parents: tuple[Member, ...] = ()  # nearest first
    siblings: tuple[Member, ...] = ()
    depends_on: tuple[Member, ...] = ()
    dependents: tuple[Member, ...] = ()
    milestone: Member | None = None
    sprint: Member | None = None
    truncated: bool = False

    def as_dict(self) -> dict[str, Any]:
        """The value form. The keys are the block's own — `dependencies`, not the card head's `depends_on`, which
        the canonical serializer reads as a set of ids — and an absent milestone or sprint is an absent key: the
        serializer has no null, and a builder reads absence the same way."""
        d: dict[str, Any] = {
            "card": self.card,
            "parents": [m.as_dict() for m in self.parents],
            "siblings": [m.as_dict() for m in self.siblings],
            "dependencies": [m.as_dict() for m in self.depends_on],
            "dependents": [m.as_dict() for m in self.dependents],
            "truncated": self.truncated,
        }
        if self.milestone is not None:
            d["milestone"] = self.milestone.as_dict()
        if self.sprint is not None:
            d["sprint"] = self.sprint.as_dict()
        return d

    def canonical(self) -> bytes:
        """The bytes the cap measures and the payload hash covers: one canonical serialization, the store's own."""
        return canon.canonical_json(self.as_dict()).encode("utf-8")

    def render(self) -> str:
        """The delivered form: the canonical bytes between two lines that type and delimit them. The delimiters are
        constant and outside the measure."""
        flag = "true" if self.truncated else "false"
        return f"<<<{FORM} card={self.card} truncated={flag}\n{self.canonical().decode('utf-8')}\n>>>{FORM}\n"


def bucket_of(pr: status.Projection) -> Bucket:
    lab = pr.label
    if lab.row == "disputed" or any(g.kind in ("held", "held_by") for g in pr.guards):
        return "held"
    if lab.row == "execution" and lab.execution in ("dispatched", "parked", "answered"):
        return "in-flight"
    if lab.row == "closed":
        return "in-flight" if lab.modifier is not None else "built"
    if lab.row == "execution" and lab.execution == "complete":
        return "built"
    return "planned"


def _title(doc: Document) -> str:
    return str(doc.head.get("title", ""))


def _first_paragraph(scope: str) -> str:
    return scope.strip().split("\n\n", 1)[0]


def project(inp: status.Inputs, card_id: int, caps: Caps, projection_of: Callable[[int], status.Projection]) -> Block:
    """The block for `card_id` over `inp.cards`, labels through `projection_of` (one card's projection in one
    card's time — bounded by the neighborhood, never the tenant), then fitted to the caps."""
    cards = inp.cards
    doc = cards[card_id]
    head = doc.head

    def eligible(cid: Any) -> bool:
        if not isinstance(cid, int) or cid == card_id or cid not in cards:
            return False
        d = cards[cid]
        return d.head.get("status") in ("ratified", "closed") and status.build_matches_reference(cid, d, inp)

    def with_bucket(cid: int, surfaces: bool) -> Member:
        d = cards[cid]
        m = Member(cid, _title(d), bucket=bucket_of(projection_of(cid)))
        if surfaces:
            m = replace(m, surfaces=tuple(str(s) for s in d.head.get("surfaces", [])))
        return m

    parents: list[Member] = []
    cur, seen = head.get("parent"), set()
    for _ in range(caps.depth):
        if not isinstance(cur, int) or cur in seen or cur not in cards:
            break
        seen.add(cur)
        if eligible(cur):
            d = cards[cur]
            parents.append(Member(cur, _title(d), scope=d.scope(), label=projection_of(cur).render()))
        cur = cards[cur].head.get("parent")

    parent = head.get("parent")
    siblings: list[int] = []
    if isinstance(parent, int):
        members = inp.kids.get(parent, ()) if inp.kids is not None else status.members_of(cards).get(parent, ())
        siblings = sorted(c for c in members if eligible(c))
    depends_on = sorted(c for c in status.depends_on_of(doc) if eligible(c))
    dependents = sorted(c for c, d in cards.items() if card_id in status.depends_on_of(d) and eligible(c))

    def bound(key: str) -> Member | None:
        cid = head.get(key)
        if not isinstance(cid, int) or not eligible(cid):
            return None
        d = cards[cid]
        return Member(cid, _title(d), scope=d.scope())

    block = Block(
        card_id,
        tuple(parents),
        tuple(with_bucket(c, False) for c in siblings),
        tuple(with_bucket(c, True) for c in depends_on),
        tuple(with_bucket(c, True) for c in dependents),
        bound("milestone"),
        bound("sprint"),
    )
    return fit(block, caps.max_bytes)


def _evict(m: Member) -> Member:
    return Member(m.id, m.title, evicted=EVICTED)


def _shrink(m: Member) -> Member | None:
    """The next step down for a Scope-bearing member: first paragraph → nothing → evicted; `None` when there is no
    further step (already a stub)."""
    if m.evicted is not None:
        return None
    if m.scope is not None and not m.scope_truncated:
        first = _first_paragraph(m.scope)
        if first != m.scope:
            return replace(m, scope=first, scope_truncated=True)
        return replace(m, scope=None, scope_truncated=True)
    if m.scope is not None:
        return replace(m, scope=None, scope_truncated=True)
    return _evict(m)


def _with(b: Block, field: str, value: Any) -> Block:
    kw: dict[str, Any] = {field: value}
    return replace(b, **kw)


def _steps(block: Block) -> list[Callable[[Block], Block]]:
    """Every eviction step in the schema's order, as functions of a block; each returns the block one step smaller
    (or unchanged when that step has nothing left to take)."""
    steps: list[Callable[[Block], Block]] = []

    def evict_in(field: str) -> None:
        ids = sorted((m.id for m in getattr(block, field) if m.evicted is None), reverse=True)
        for cid in ids:

            def step(b: Block, cid: int = cid, field: str = field) -> Block:
                ms = tuple(_evict(m) if m.id == cid and m.evicted is None else m for m in getattr(b, field))
                return _with(b, field, ms)

            steps.append(step)

    def shrink_parents() -> None:
        for i in range(len(block.parents) - 1, -1, -1):
            for _ in range(3):

                def step(b: Block, i: int = i) -> Block:
                    m = b.parents[i]
                    nxt = _shrink(m)
                    if nxt is None:
                        return b
                    ps = tuple(nxt if j == i else p for j, p in enumerate(b.parents))
                    return replace(b, parents=ps)

                steps.append(step)

    def shrink_one(field: str) -> None:
        for _ in range(3):

            def step(b: Block, field: str = field) -> Block:
                m = getattr(b, field)
                nxt = _shrink(m) if m is not None else None
                return b if nxt is None else _with(b, field, nxt)

            steps.append(step)

    evict_in("depends_on")
    evict_in("dependents")
    shrink_parents()
    shrink_one("milestone")
    shrink_one("sprint")
    evict_in("siblings")
    return steps


def fit(block: Block, max_bytes: int) -> Block:
    """The block within `max_bytes` by the written order, or as small as the order can make it."""
    if len(block.canonical()) <= max_bytes:
        return block
    out = block
    for step in _steps(block):
        nxt = step(out)
        if nxt == out:
            continue
        out = replace(nxt, truncated=True)
        if len(out.canonical()) <= max_bytes:
            break
    return out


def caps_of(eff: Mapping[str, Any]) -> Caps:
    """The caps from the effective config's `[payload.context]` — the adopted schema's defaults are already in it,
    and none is supplied here (04 §4.1, Y1)."""
    ctx = eff["payload"]["context"]
    return Caps(int(ctx["depth"]), int(ctx["max_bytes"]))
