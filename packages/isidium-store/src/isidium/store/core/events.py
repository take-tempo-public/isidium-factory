"""03 §6 — `state/history.jsonl` as a tagged union of events, and `state.json` as its fold [L1, 2026-09-09].

**The union is closed and typed, one model per kind** (C-2, C-5): a kind outside it is `event.kind`; a member the
kind does not carry, or carries in the wrong type, is `event.shape` naming the member. The set of kinds is the one
`sidecar-events@2` declares; the per-kind members are this module's — the schema document's own comment names it
as their home. Two of the schema's kinds, `merged` and `landed`, are the batch record's lifecycle and are **not** in
the union yet: the schema requires `card` on every row, and a batch event has no card. Batches open with T-C3 (v1c);
until then a report carrying one is refused `event.kind` with the reason in its detail (the WP5 plan's L1, finding 2).

**The fold is a pure function and idempotent**: the same events, cursor and heads produce the same bytes, which is
what makes *"landing the same cursor twice is an empty diff"* (03 §1.4, G11) a property of the store rather than a
check it performs. It reads only what it is handed — never the working tree, never the file it is about to replace —
so a hand-edited `state.json` is overwritten by the fold, not merged with (03 §6: *"the lander overwrites it"*).

The prototype this ports is `review-artifacts/2026-08-21-round6/r6-impl-d6/events.py` in the record; its checks are
K7b-era conformance and are carried by `tests/store/test_l1.py`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Annotated, Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from .refusal import Refusal

FailureClass = Literal["scope", "ambiguity", "budget", "timeout"]
Verdict = Literal["pass", "fail", "manual"]


class _Event(BaseModel):
    """Every event names its card and may carry its own time; the store stamps `id` and a missing `at`."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    card: int = Field(ge=1)
    at: str | None = None


class Dispatched(_Event):
    kind: Literal["dispatched"]
    run_id: str


class Parked(_Event):
    kind: Literal["parked"]
    run_id: str | None = None
    text: str | None = None


class Answered(_Event):
    kind: Literal["answered"]
    seq: int | None = Field(default=None, ge=1)  # the card entry's seq — the ledger's own transition (03 §6)


class Failed(_Event):
    kind: Literal["failed"]
    class_: FailureClass = Field(alias="class")
    run_id: str | None = None


class Disputed(_Event):
    kind: Literal["disputed"]
    closure_id: str | None = None


class Complete(_Event):
    kind: Literal["complete"]
    run_id: str
    build_hash: str
    batch: str | None = None
    cost_micro: int = Field(default=0, ge=0)
    duration_ms: int = Field(default=0, ge=0)


class Closed(_Event):
    kind: Literal["closed"]
    closure_id: str
    build_hash: str
    closure_kind: Literal["factory", "human"] = "factory"
    verdicts: dict[str, Verdict] = Field(default_factory=dict)
    evidence: list[str] = Field(default_factory=list)
    verified: bool = True


class Reverted(_Event):
    kind: Literal["reverted"]
    run_id: str | None = None


class Demoted(_Event):
    kind: Literal["demoted"]
    seq: int | None = Field(default=None, ge=1)


class Withdrawn(_Event):
    kind: Literal["withdrawn"]
    seq: int | None = Field(default=None, ge=1)


class Acked(_Event):
    kind: Literal["acked"]
    seq: int | None = Field(default=None, ge=1)


class Accepted(_Event):
    kind: Literal["accepted"]
    seq: int | None = Field(default=None, ge=1)
    ratified_seq: int | None = Field(default=None, ge=1)
    commit: str | None = None
    ext_schema_hash: str | None = None


class RefResolved(BaseModel):
    """One `refs_resolved` row (03 §1.14): the ref's path and its blob id at the ratifying commit."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    blob: str


class Ratified(_Event):
    """The fingerprint's birth [V3, 2026-09-11, F-c ruled]: observed by the land's walk at a verified ratification —
    a `ratified` entry, or a card born ratified in a sitting — carrying the entry's `seq`, the commit that wrote it
    and the blob of every ref at that commit. Never a run report's to carry (`parse_report` refuses it): what the
    fingerprint records is what the owner signed, and the lander does not get to say what that was."""

    kind: Literal["ratified"]
    seq: int = Field(ge=1)
    commit: str
    refs_resolved: list[RefResolved] = Field(default_factory=list)
    ext_schema_hash: str | None = None


class Reopened(_Event):
    kind: Literal["reopened"]
    seq: int | None = Field(default=None, ge=1)


class Question(_Event):
    kind: Literal["question"]
    text: str


Event = Annotated[
    Dispatched
    | Parked
    | Answered
    | Failed
    | Disputed
    | Complete
    | Closed
    | Reverted
    | Demoted
    | Withdrawn
    | Acked
    | Accepted
    | Reopened
    | Question
    | Ratified,
    Field(discriminator="kind"),
]

KINDS: Final[tuple[str, ...]] = (
    "dispatched",
    "parked",
    "answered",
    "failed",
    "disputed",
    "complete",
    "closed",
    "reverted",
    "demoted",
    "withdrawn",
    "acked",
    "accepted",
    "reopened",
    "question",
    "ratified",
)
BATCH_KINDS: Final[tuple[str, ...]] = ("merged", "landed")  # in the schema's enum, not in the union — see the docstring
# Kinds only the land's own walk emits (V3): a run report carrying one is refused `event.kind`.
OBSERVED_KINDS: Final[tuple[str, ...]] = ("ratified",)

# Which kinds set the current execution status — one field, not a list (03 §6). `failed` sets it with its class.
_EXECUTION: Final[Mapping[str, str]] = {
    "dispatched": "dispatched",
    "parked": "parked",
    "answered": "answered",
    "complete": "complete",
    "closed": "closed",
    "reverted": "reverted",
    "reopened": "reopened",
}

_ADAPTER: Final[TypeAdapter[Event]] = TypeAdapter(Event)


class Suggestion(BaseModel):
    """One entry of the run report's bounded `suggestions[]` (03a §2): the builder's typed slot, not a free page.
    The bounds themselves (120 / 2 KiB) are the inbox door's, applied when the intake record is built."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: str
    title: str
    body: str
    refs: list[str] = Field(default_factory=list)
    proposed_for: int | None = Field(default=None, ge=1)


class RunReport(BaseModel):
    """What the lander hands `land` (T-C6's contract, typed here as the prototype shaped it — [proposed] until the
    adapter seam confirms it)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    events: list[Event] = Field(default_factory=list)
    suggestions: list[Suggestion] = Field(default_factory=list)


def parse_event(raw: Mapping[str, Any]) -> Event:
    """One event against the union: `event.kind` for a kind outside it, `event.shape` naming the member otherwise."""
    kind = raw.get("kind")
    if kind in BATCH_KINDS:
        raise Refusal("event.kind", str(kind), "a batch event; batches arrive with T-C3, and the schema wants a card")
    if kind not in KINDS:
        raise Refusal("event.kind", str(kind), "not a kind of the union: " + ", ".join(KINDS))
    try:
        event: Event = _ADAPTER.validate_python(dict(raw))
        return event
    except ValidationError as e:
        first = e.errors()[0]
        member = ".".join(str(x) for x in first["loc"] if x != kind) or "event"
        raise Refusal("event.shape", f"{kind}.{member}", first["msg"]) from None


def parse_report(raw: Mapping[str, Any]) -> RunReport:
    """The report as a whole; events are parsed one by one first so their refusals name the event, not the list."""
    for e in raw.get("events", []):
        if isinstance(e, Mapping) and e.get("kind") in OBSERVED_KINDS:
            raise Refusal("event.kind", str(e["kind"]), "observed by the land's walk at a signed act, never reported")
    events = [parse_event(e) for e in raw.get("events", []) if isinstance(e, Mapping)]
    try:
        return RunReport(run_id=str(raw.get("run_id", "")), events=events, suggestions=raw.get("suggestions", []))
    except ValidationError as e:
        first = e.errors()[0]
        raise Refusal("land.report", ".".join(str(x) for x in first["loc"]), first["msg"]) from None


def record_of(event: Event, event_id: str, at: str) -> dict[str, Any]:
    """The event as the line the file holds: `id`, `at`, `card`, `kind` and the kind's own members, by alias."""
    body = event.model_dump(by_alias=True, exclude_none=True)
    body["id"] = event_id
    body["at"] = event.at or at
    return body


def _new_card() -> dict[str, Any]:
    return {"execution": None, "runs": [], "closures": [], "fingerprint": None, "history_head": None}


def fold(
    events: Sequence[Mapping[str, Any]],
    cursor: str | None,
    landed_at: str,
    journal_head: Mapping[str, Any],
    heads: Mapping[str, Mapping[str, Any]],
    integrity: Mapping[str, Mapping[str, Sequence[str]]] | None = None,
    ingest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """`state.json` as the fold of the event file as of the cursor (03 §6). `heads` is `{"0042": {seq, h}}` — each
    card's last history entry as the store holds it, which is the sidecar's `history_head` (03 §1.4). Batches are
    empty until T-C3 (v1c) opens them.

    **Two more non-event inputs since L4 (`sidecar@2`, Q-W7 (a))**: `integrity` — the reasons the land's walk
    computed, `{path: {reason: [commit, …]}}`, keyed by governed path (`config.toml` and the inbox have no card, so
    the key is the path, and the projection maps a card's path to its id) and naming the commits that earned each
    reason (what `repair --journal <commit>` needs); and `ingest` — the land-time facts no card names (9.5): the
    run and its `suggestion-overflow`. Both are recomputed at every land, never accumulated: a repaired commit drops
    out at the next land. Still pure — the same inputs give the same bytes."""
    cards: dict[str, dict[str, Any]] = {}
    for e in events:
        key = f"{int(e['card']):04d}"
        c = cards.setdefault(key, _new_card())
        k = str(e["kind"])
        if k in _EXECUTION:
            c["execution"] = _EXECUTION[k]
        elif k == "failed":
            c["execution"] = f"failed({e['class']})"
        if k == "complete":
            c["runs"].append(
                {
                    "run_id": e["run_id"],
                    "batch": e.get("batch"),
                    "outcome": "complete",
                    "build_hash": e["build_hash"],
                    "cost_micro": int(e.get("cost_micro", 0)),
                    "duration_ms": int(e.get("duration_ms", 0)),
                }
            )
        elif k == "closed":
            if e.get("closure_kind", "factory") == "factory":
                c["closures"].append(
                    {
                        "closure_id": e["closure_id"],
                        "kind": "factory",
                        "outcome": "met",
                        "verified_against": e["build_hash"],
                        "verdicts": dict(e.get("verdicts", {})),
                        "evidence": list(e.get("evidence", [])),
                        "at": e["at"],
                        "verified": True,
                    }
                )
            else:  # a human closure appears only as verification (03 §6)
                c["closures"].append(
                    {
                        "closure_id": e["closure_id"],
                        "verified_against": e["build_hash"],
                        "verified": bool(e.get("verified", False)),
                        "at": e["at"],
                    }
                )
        elif k == "ratified":
            # The fingerprint's birth [V3, F-c]: a re-ratification replaces it whole.
            c["fingerprint"] = {
                "ratified_seq": int(e["seq"]),
                "commit": e["commit"],
                "refs_resolved": [dict(r) for r in e.get("refs_resolved", [])],
                "ext_schema_hash": e.get("ext_schema_hash"),
                "validator_version": "v3",
            }
        elif k == "accepted" and e.get("ratified_seq"):
            # An acceptance of the ratification the fingerprint already records keeps its `refs_resolved` — the
            # blobs are the ratification's, not the acceptance's; one of another ratification starts over (L1's).
            prior = c["fingerprint"] or {}
            same = prior.get("ratified_seq") == int(e["ratified_seq"])
            c["fingerprint"] = {
                "ratified_seq": int(e["ratified_seq"]),
                "commit": e.get("commit") or (prior.get("commit") if same else None),
                "refs_resolved": list(prior.get("refs_resolved", [])) if same else [],
                "ext_schema_hash": e.get("ext_schema_hash") or (prior.get("ext_schema_hash") if same else None),
                "validator_version": prior.get("validator_version", "l1") if same else "l1",
            }
    for key, h in heads.items():
        cards.setdefault(key, _new_card())["history_head"] = dict(h)
    return {
        "schema": 2,
        "ledger_cursor": cursor,
        "landed_at": landed_at,
        "journal_head": dict(journal_head),
        "batches": {},
        "cards": dict(sorted(cards.items())),
        "integrity": {
            p: {r: sorted(set(shas)) for r, shas in sorted(by.items()) if shas}
            for p, by in sorted((integrity or {}).items())
            if any(by.values())
        },
        "ingest": dict(ingest) if ingest else {},
    }
