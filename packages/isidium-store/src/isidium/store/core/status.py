"""The projected status (03 §1.5) — eleven rows, precedence top to bottom, one function of (cards, the sidecar,
policy). Two inputs, one function (T7): the factory-side renderer reads the live ledger; the in-project renderer
reads (cards, `state.json`, `config.toml`) — rows marked † need the ledger and fall through here.

**The label is a typed value, never a formatted string.** The eleven rows are a closed enum and their payloads are
fields (the integrity reasons, the failure class, the blocking ids); `render()` is the only place a human-readable
form is produced, and nothing matches on it. Same for the readiness guards. This is the shape the Rust port
transcribes, and the reason `terminal` is a set membership on a typed row rather than a string comparison.

One pass over the parsed set (9.4): each card's build hash is supplied (the blob cache) or computed once; the chain
is verified once; the guards are a second, hash-free pass over the labels."""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, Literal

from . import canon, chain
from .derive import replay_status
from .grammar import Document, Entry
from .refusal import Refusal

Verifier = Callable[[Entry], bool]

# The eleven rows of 1.5, in precedence order. A row is what the card IS; a modifier is what is pending about it.
Row = Literal[
    "integrity",
    "unratified",
    "withdrawn",
    "draft",
    "disputed",
    "closed",
    "reopened",
    "execution",
    "ratified",
    "ready",
    "unknown",
]
Modifier = Literal["pending-ingest", "pending-land", "pending-review", "unverified"]
IntegrityReason = Literal["tampered", "unjournaled", "rewritten", "unverified", "attribution", "time"]
FailureClass = Literal["scope", "ambiguity", "budget", "timeout"]
ExecutionState = Literal["complete", "reverted", "parked", "answered", "dispatched", "failed"]
GuardKind = Literal["has-questions", "held", "held_by", "blocked_by", "deferred_by", "below-threshold"]
HoldKind = Literal["blocked", "deferred", "watching"]

INTEGRITY_REASONS: Final[tuple[IntegrityReason, ...]] = (
    "tampered",
    "unjournaled",
    "rewritten",
    "unverified",
    "attribution",
    "time",
)
FAILURE_CLASSES: Final[tuple[FailureClass, ...]] = ("scope", "ambiguity", "budget", "timeout")
EXECUTION_STATES: Final[tuple[ExecutionState, ...]] = (
    "complete",
    "reverted",
    "parked",
    "answered",
    "dispatched",
    "failed",
)


@dataclass(frozen=True)
class Guard:
    """One readiness guard (1.5 row 10). `has-questions` before `held` (W5) is the caller's ordering."""

    kind: GuardKind
    hold_kind: HoldKind | None = None
    parent: int | None = None
    ids: tuple[int, ...] = ()

    def render(self) -> str:
        if self.kind == "held":
            return f"held({self.hold_kind})"
        if self.kind == "held_by":
            return f"held_by({self.parent}, {self.hold_kind})"
        if self.kind in ("blocked_by", "deferred_by"):
            return f"{self.kind}{list(self.ids)}"
        return self.kind


@dataclass(frozen=True)
class Label:
    """One of the eleven rows with its payload. `render()` is the only place the human form exists."""

    row: Row
    modifier: Modifier | None = None
    reasons: tuple[IntegrityReason, ...] = ()  # row 1
    failure: FailureClass | None = None  # row 9's `failed(class)`
    execution: ExecutionState | None = None  # row 9

    def render(self) -> str:
        if self.row == "integrity":
            return f"integrity({','.join(self.reasons)})"
        if self.row == "execution":
            base = f"failed({self.failure})" if self.execution == "failed" else str(self.execution)
        else:
            base = self.row
        return f"{base} ({self.modifier})" if self.modifier else base


# `terminal(card)` is defined once over the projected rows (G7) — a typed membership, never a string compare.
def is_terminal(label: Label) -> bool:
    if label.row == "closed":
        return label.modifier in (None, "unverified")
    if label.row == "withdrawn":
        return label.modifier is None
    return label.row == "execution" and label.execution == "reverted"


@dataclass(frozen=True)
class Projection:
    id: int
    kind: str
    status: str
    label: Label
    guards: tuple[Guard, ...] = ()
    ready: bool = False
    software_grade: bool = False

    @property
    def terminal(self) -> bool:
        return is_terminal(self.label)

    def render(self) -> str:
        return self.label.render()


@dataclass
class Inputs:
    cards: Mapping[int, Document]
    state: Mapping[str, Any] = field(default_factory=dict)  # the parsed state.json, {} when absent
    gated_x: frozenset[str] = frozenset()
    verified: Verifier | None = None  # signature + binding verification; None = document-only
    integrity: Mapping[int, Sequence[IntegrityReason]] = field(default_factory=dict)  # reasons from `check`
    software_fprs: frozenset[str] = frozenset()
    builds: Mapping[int, str] = field(default_factory=dict)  # build hash per card when known (the blob cache)
    kind_default: str = ""  # `card@1`'s declared default for `kind`; supplied by the caller, never written here
    # parent id → its members, when the caller keeps that index (the store does, E3's shape); `None` means
    # `project_one` scans the heads for them — linear in the set, at a fraction of one label's cost (F9).
    kids: Mapping[int, Collection[int]] | None = None


def _state_card(st: Mapping[str, Any], cid: int) -> Mapping[str, Any]:
    cards: Mapping[str, Any] = st.get("cards", {})
    card: Mapping[str, Any] = cards.get(f"{cid:04d}", {})
    return card


def _signed_ok(e: Entry, verified: Verifier | None) -> bool:
    return chain.is_signed(e) and (verified is None or verified(e))


def _reference_build(doc: Document, sc: Mapping[str, Any], verified: Verifier | None) -> str | None:
    """Row 2's reference hash: the fingerprint when one exists, else the `build` of the last verified `ratified`
    entry (H7); None when neither (`unknown`)."""
    fp = sc.get("fingerprint")
    if fp and fp.get("ratified_seq"):
        seq = int(fp["ratified_seq"])
        if 1 <= seq <= len(doc.history):
            return str(doc.history[seq - 1]["build"])
    for e in reversed(doc.history):
        if e.get("act") in ("ratified", "created") and _signed_ok(e, verified):
            return str(e["build"])
    return None


def _execution_state(value: Any) -> tuple[ExecutionState, FailureClass | None] | None:
    """The sidecar's `execution` field as a typed pair — `failed(class)` is the one that carries a payload."""
    if not isinstance(value, str):
        return None
    if value.startswith("failed(") and value.endswith(")"):
        name = value[len("failed(") : -1]
        for cls in FAILURE_CLASSES:
            if name == cls:
                return ("failed", cls)
        return ("failed", None)
    for state in EXECUTION_STATES:
        if value == state:
            return (state, None)
    return None


def _guards(doc: Document, all_cards: Mapping[int, Document], labels: Mapping[int, Label]) -> tuple[Guard, ...]:
    h = doc.head
    g: list[Guard] = []
    if h.get("questions"):
        g.append(Guard("has-questions"))
    hold = h.get("hold")
    if isinstance(hold, Mapping):
        g.append(Guard("held", hold_kind=_hold_kind(hold)))
    parent = h.get("parent")
    if isinstance(parent, int) and parent in all_cards:
        ph = all_cards[parent].head.get("hold")
        if isinstance(ph, Mapping):
            g.append(Guard("held_by", hold_kind=_hold_kind(ph), parent=parent))
    blocked = sorted(
        d for d in h.get("depends_on", []) if isinstance(d, int) and not (labels.get(d) and is_terminal(labels[d]))
    )
    if blocked:
        g.append(Guard("blocked_by", ids=tuple(blocked)))
    return tuple(g)


def _hold_kind(hold: Mapping[str, Any]) -> HoldKind | None:
    k = hold.get("kind")
    return k if k in ("blocked", "deferred", "watching") else None


def _fpr_of(e: Entry) -> str:
    sig = e.get("sig")
    if isinstance(sig, str):
        try:
            return chain.parse_sig(sig)[1]
        except Refusal:
            return ""
    return ""


def _core_label(cid: int, doc: Document, inp: Inputs) -> tuple[Label, str]:
    """Rows 1–9 and 11's non-guard part: (label, kind), with no reference to other cards. One build hash, one chain
    verification."""
    h = doc.head
    kind, status = str(h.get("kind", inp.kind_default)), str(h.get("status"))
    sc = _state_card(inp.state, cid)
    ver = inp.verified
    build = inp.builds.get(cid) or canon.build_hash(h, doc.scope(), inp.gated_x)
    # row 1 — integrity
    reasons: list[IntegrityReason] = list(inp.integrity.get(cid, ()))
    if not reasons and doc.history:
        verdicts = chain.verify_chain(doc.history, chain.genesis("card", cid))
        if any(v == "tampered" for v in verdicts) or doc.history[-1].get("build") != build:
            reasons.append("tampered")
        if any(str(b.get("at", "")) < str(a.get("at", "")) for a, b in zip(doc.history, doc.history[1:], strict=False)):
            reasons.append("time")
    if reasons:
        ordered = tuple(r for r in INTEGRITY_REASONS if r in set(reasons))
        return Label("integrity", reasons=ordered), kind
    # row 2 — unratified
    if status in ("ratified", "closed"):
        ref = _reference_build(doc, sc, ver)
        if ref is None:
            return Label("unknown"), kind
        if ref != build:
            return Label("unratified"), kind
    # row 3 — withdrawn
    if status == "withdrawn":
        e = doc.history[-1]
        final = (e.get("act") == "withdrawn" and _signed_ok(e, ver)) or replay_status(doc.history[:-1]) == "draft"
        return Label("withdrawn", None if final else "pending-review"), kind
    # row 4 — draft
    if status == "draft":
        return Label("draft"), kind
    closures = list(h.get("closures", []))
    newest = closures[-1] if closures else None
    # row 5 — disputed
    if newest and not newest.get("retracted"):
        verdicts_ = newest.get("verdicts") or {}
        if newest.get("outcome") == "met" and any(v == "fail" for v in verdicts_.values()):
            return Label("disputed"), kind
        for c in sc.get("closures", []):
            if c.get("closure_id") == newest.get("id") and c.get("verified") is False:
                return Label("disputed"), kind
    # rows 6–7 — closed
    if status == "closed" and newest:
        closed_entry = next((e for e in reversed(doc.history) if e.get("act") == "closed"), None)
        accepted = any(
            e.get("act") == "accepted" and _signed_ok(e, ver) and str(e.get("ref", "")).startswith(newest["id"] + ":")
            for e in doc.history
        )
        deviated = isinstance(newest.get("outcome"), Mapping) and "deviated" in newest["outcome"]
        if deviated and not (closed_entry and _signed_ok(closed_entry, ver)) and not accepted:
            return Label("closed", "pending-review"), kind
        landed = next((c for c in sc.get("closures", []) if c.get("closure_id") == newest["id"]), None)
        if landed and landed.get("verified") and landed.get("verified_against") == build:
            return Label("closed"), kind
        if accepted or (closed_entry and _signed_ok(closed_entry, ver)):
            return Label("closed", "unverified"), kind
        return Label("closed", "pending-ingest"), kind
    # rows 7–9 — the factory's view of a ratified card
    execution = sc.get("execution")
    if execution == "closed":
        landed_build = next(
            (c.get("verified_against") for c in sc.get("closures", []) if c.get("kind") == "factory"), None
        )
        return (Label("reopened") if landed_build and landed_build != build else Label("closed")), kind
    state = _execution_state(execution)
    if state is not None:
        return Label("execution", execution=state[0], failure=state[1]), kind
    # row 11 (its pending-ingest half; the guards are the caller's pass)
    landed_at = str(inp.state.get("landed_at", ""))
    newest_signed = next((e for e in reversed(doc.history) if chain.is_signed(e)), None)
    if landed_at and newest_signed and str(newest_signed.get("at", "")) > landed_at:
        return Label("ratified", "pending-ingest"), kind
    return Label("ratified"), kind


def _projected(
    cid: int, doc: Document, core: tuple[Label, str], inp: Inputs, labels: Mapping[int, Label]
) -> Projection:
    """The guard pass for one card (row 10, and row 11's ready/ratified split), given its core label and the labels
    of the cards its guards read — one function for the whole-set pass and the one-card pass, so the two cannot
    drift (F9)."""
    label, kind = core
    status = str(doc.head.get("status"))
    sw = any(chain.is_signed(e) and _fpr_of(e) in inp.software_fprs for e in doc.history)
    if label.row == "draft":
        return Projection(cid, kind, status, label, _guards(doc, inp.cards, labels), False, sw)
    if label.row == "ratified" and label.modifier is None:
        guards = _guards(doc, inp.cards, labels)
        if guards:
            return Projection(cid, kind, status, label, guards, False, sw)
        if kind == "story":
            return Projection(cid, kind, status, Label("ready"), (), True, sw)
        return Projection(cid, kind, status, label, (), False, sw)
    return Projection(cid, kind, status, label, (), False, sw)


def _rolled_up(pr: Projection, kid_labels: Sequence[Label]) -> Projection:
    """The container roll-up (1.5) for one parent, given its members' labels."""
    if pr.label.row in ("integrity", "unratified", "withdrawn") or pr.status == "draft" or pr.guards:
        return pr
    if kid_labels and all(is_terminal(lbl) for lbl in kid_labels):
        return Projection(pr.id, pr.kind, pr.status, Label("closed"), (), False, pr.software_grade)
    if pr.status == "closed" and any(not is_terminal(lbl) for lbl in kid_labels):
        return Projection(pr.id, pr.kind, pr.status, Label("disputed"), (), False, pr.software_grade)
    return pr


def _depends_on(doc: Document) -> list[int]:
    return [d for d in doc.head.get("depends_on", []) if isinstance(d, int)]


def _members_of(cards: Mapping[int, Document]) -> dict[int, list[int]]:
    """parent id → its members, from the heads — one pass over the set."""
    members: dict[int, list[int]] = {}
    for cid, doc in cards.items():
        par = doc.head.get("parent")
        if isinstance(par, int):
            members.setdefault(par, []).append(cid)
    return members


def _roll_up(out: dict[int, Projection], members: Mapping[int, Sequence[int]]) -> None:
    """The container roll-up over the whole set — **members before their parents, whatever the ids** [K10, item 1;
    K7b's finding 1].

    The roll-up used to run in card order, so a container inside a container read its member's label *after* the
    member's own roll-up when the member's id was lower and *before* it otherwise: the same nested set projected
    differently depending on which card had been created first, and `project_one` — which reads the subtree beneath
    the card it is asked about — could not agree with it on a nested set. A post-order walk from each parent rolls
    the deepest containers first; a member's label is read only once it is final. Iterative rather than recursive
    so a deep ladder costs a list, not a stack frame per level; `seen` marks a card on its first visit, which is
    what makes a `parent` cycle — refused at every write door, but a bypass can put one on `main` — terminate
    instead of walking forever.
    """
    seen: set[int] = set()
    for start in members:
        if start in seen:
            continue
        stack: list[tuple[int, bool]] = [(start, False)]
        while stack:
            cid, ready = stack.pop()
            if ready:
                pr = out.get(cid)
                if pr is not None:
                    out[cid] = _rolled_up(pr, [out[k].label for k in members[cid] if k in out])
                continue
            if cid in seen:
                continue
            seen.add(cid)
            stack.append((cid, True))
            stack.extend((k, False) for k in members[cid] if k in members and k not in seen)


def project(inp: Inputs) -> dict[int, Projection]:
    """Every card's projection: one hashing pass for the core labels; one hash-free pass for the guards (row 10) and
    row 11's ready/ratified split; then the container roll-up (1.5), members before their parents."""
    core: dict[int, tuple[Label, str]] = {cid: _core_label(cid, doc, inp) for cid, doc in inp.cards.items()}
    labels = {cid: lbl for cid, (lbl, _k) in core.items()}
    out: dict[int, Projection] = {cid: _projected(cid, doc, core[cid], inp, labels) for cid, doc in inp.cards.items()}
    _roll_up(out, _members_of(inp.cards))
    return out


def project_one(inp: Inputs, cid: int) -> Projection:
    """One card's projection **in one card's time** [K7b, F9] — the same rows as `project`, computed for this card
    and the cards its verdict actually reads, and for no other.

    `show card` rendered one label by projecting every card: a chain verification and a signature verification per
    card, linear in the tenant (measured 10 → 78 ms from 10 to 200 cards, for a document that was a dict lookup).
    C-13 says asking one question about one member must not pay for every member, and the label's inputs are
    few: its own core label; the core labels of the cards it `depends_on` (the `blocked_by` guard reads whether
    they are terminal); its parent's head (the `held_by` guard, no label needed); and, for the roll-up, the
    projected label of each member whose `parent` it is. Everything else in the set is irrelevant to this card's
    row, and is not computed.

    A member's label is its *rolled-up* label when the member is itself a container — the subtree beneath the card
    is read, members before their parents, which is the order `project` rolls the whole set in since K10 (item 1);
    so the two agree on a nested set as on a flat one, and `tests/store/test_k10.py` asserts it in both id orders.
    The subtree is the cost, not the set: a container's members, their members, and nothing beside them.
    """
    if cid not in inp.cards:
        raise KeyError(cid)
    core: dict[int, tuple[Label, str]] = {}
    members = _members_of(inp.cards) if inp.kids is None else None  # one pass, only when the caller has no index

    def core_of(c: int) -> tuple[Label, str]:
        if c not in core:
            core[c] = _core_label(c, inp.cards[c], inp)
        return core[c]

    def projected(c: int) -> Projection:
        d = inp.cards[c]
        labels = {x: core_of(x)[0] for x in _depends_on(d) if x in inp.cards}
        return _projected(c, d, core_of(c), inp, labels)

    def kids_of(c: int) -> list[int]:
        return sorted(inp.kids.get(c, ())) if inp.kids is not None else (members or {}).get(c, [])

    seen: set[int] = set()  # a `parent` cycle terminates here (see `_roll_up`); the member reads as un-rolled

    def rolled(c: int) -> Projection:
        pr = projected(c)
        if c in seen:
            return pr
        seen.add(c)
        kids = kids_of(c)
        return _rolled_up(pr, [rolled(k).label for k in kids if k in inp.cards]) if kids else pr

    return rolled(cid)


@dataclass(frozen=True)
class Queue:
    """The queue section (1.5): what the next sitting's one signature will clear."""

    open_questions: tuple[int, ...]
    holds_on_owner: tuple[int, ...]
    closures_pending_review: tuple[int, ...]
    withdrawals_pending: tuple[int, ...]
    blocked_by_those: tuple[int, ...]
    dispositions_since_batch: int
    inbox_counts: Mapping[str, int]
    merged_not_landed: int | None  # ledger-only (X2); None in-project


def queue(
    inp: Inputs,
    projections: Mapping[int, Projection],
    inbox: Sequence[Mapping[str, Any]],
    policy_entries: Sequence[Entry],
    merged_not_landed: int | None = None,
) -> Queue:
    oq = tuple(
        sorted(c for c, d in inp.cards.items() if d.head.get("questions") and d.head.get("status") != "withdrawn")
    )
    ho = tuple(
        sorted(
            c
            for c, d in inp.cards.items()
            if isinstance(d.head.get("hold"), Mapping)
            and d.head["hold"].get("on") == {"owner": True}
            and d.head["hold"].get("kind") in ("blocked", "deferred")
        )
    )
    cpr = tuple(
        sorted(c for c, p in projections.items() if p.label.row == "closed" and p.label.modifier == "pending-review")
    )
    wp = tuple(
        sorted(c for c, p in projections.items() if p.label.row == "withdrawn" and p.label.modifier == "pending-review")
    )
    those = set(oq) | set(ho) | set(cpr) | set(wp)
    blocked = tuple(
        sorted(
            c for c, d in inp.cards.items() if c not in those and any(x in those for x in d.head.get("depends_on", []))
        )
    )
    last_batch_at = max((str(e.get("at", "")) for e in policy_entries if e.get("act") == "batch-manifest"), default="")
    disp = sum(1 for r in inbox if r.get("type") == "disposition" and str(r.get("at", "")) > last_batch_at)
    open_ids = {r["id"] for r in inbox if r.get("type") == "intake"}
    for r in inbox:
        if r.get("type") == "disposition" and r.get("outcome") in ("accepted", "declined"):
            open_ids.discard(r.get("on"))
    counts: dict[str, int] = {}
    for r in inbox:
        if r.get("type") == "intake" and r["id"] in open_ids:
            counts[str(r.get("source"))] = counts.get(str(r.get("source")), 0) + 1
    return Queue(oq, ho, cpr, wp, blocked, disp, counts, merged_not_landed)
