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

# 03 §1.5's four, widened by the classes the catalog's failure protocols and the ledger already use [V5a, Q-V22 (a),
# owner 2026-09-12]: without them no failure of a run whose `dispatched` landed could ever land its end.
#
# Widened by two more [owner, 2026-09-20]. **`merge`** — Q-V31 (c) ruled that a resume replays the failed run's diff
# as a patch onto a fresh branch at the current base, and a patch that will not apply had no name. The catalog
# already named exactly this outcome — *"conflict ⇒ `failed:merge`, deterministic"* — for the merge at close, and
# one name covers both, because both are the same fact: the work no longer applies to the base it must apply to.
# Reusing `environment` was offered and refused on `r-4`'s precedent — a turn limit reported as `failed:infra` was
# retried once for nothing, and a class that does not say what happened costs exactly that.
# **`malformed-plan`** — Q-V29 (a), ruled 2026-09-13 and not yet built. It rides this widening rather than its own
# because the two would otherwise cost two store images and two recreates for one edit to one tuple.
FailureClass = Literal[
    "scope",
    "ambiguity",
    "budget",
    "timeout",
    "infra",
    "environment",
    "acceptance",
    "gate",
    "card-drift",
    "identity",
    "merge",
    "malformed-plan",
]
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

# The in-flight set, declared once (03 §6, card 7 R5): every site that asks whether a run is in flight — this
# fold, the land's act events (`Store._act_events`), the board's WIP count and the neighborhood block — reads this
# constant rather than its own copy of the tuple. `complete` is deliberately not a member: a run that already
# finished is not what a withdrawal or demotion abandons (card 7, K1) — the board and the neighborhood add
# `complete` on top of this set where their own broader notion of "still live" needs it.
IN_FLIGHT: Final[frozenset[str]] = frozenset({"dispatched", "parked", "answered"})

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


def _response(kind: str, e: Mapping[str, Any]) -> dict[str, Any]:
    """One `responses[]` row on a parked run's entry (card 13, R2/R3/R6): `act` the event's own kind, `card_seq`
    the card entry's `seq` when the event names one, `at` the event's own time. Canon has no null (C5): a `seq`-less
    act — the store never emits one, but the fold must be total over any file (the r-6 precedent) — omits the key
    rather than writing it as `None`."""
    seq = e.get("seq")
    return {"act": kind, **({"card_seq": int(seq)} if seq is not None else {}), "at": e["at"]}


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
    # The cards whose current execution is a failure, kept as a fact of this pass rather than read back out of the
    # `failed(class)` string the sidecar holds (C-2: nothing parses a rendered value apart).
    failed: set[str] = set()
    dispatched_run: dict[str, str] = {}  # card key → its last `dispatched` event's run_id (card 7 R2)
    # Card 13: the `runs[]` entry of the park whose question is still open, by card key — the same mutable dict held
    # in `c["runs"]`, so a response appended below is visible in the fold's output without a second lookup.
    # `key in open_park` holds exactly while the card's execution has read `parked`/`answered` continuously since
    # that park (R6's window); every kind that ends the window pops it in the same branch that ends it.
    open_park: dict[str, dict[str, Any]] = {}
    for e in events:
        key = f"{int(e['card']):04d}"
        c = cards.setdefault(key, _new_card())
        k = str(e["kind"])
        prior_execution = c["execution"]  # read before this event's kind can overwrite it (R1/R2/R3 all need it)
        if k in _EXECUTION:
            c["execution"] = _EXECUTION[k]
            failed.discard(key)
            if k == "dispatched":
                # A re-dispatch ends any open park outright (its question is moot once a new run starts): without
                # this pop, a later demotion of the re-dispatched run would both abandon it and append a response
                # to the stale parked entry.
                dispatched_run[key] = e["run_id"]
                open_park.pop(key, None)
            elif k == "parked":
                # Card 13, R1: the event's own run id first, the card's last dispatched run only when the event
                # names none — canon has no null, so an unknown id is an absent key, the same idiom the abandoned
                # entry below already uses.
                run_id = e.get("run_id") or dispatched_run.get(key)
                entry = {
                    **({"run_id": run_id} if run_id is not None else {}),
                    "outcome": "parked",
                    "ended_at": e["at"],
                    "responses": [],
                }
                c["runs"].append(entry)
                open_park[key] = entry
            elif k == "answered":
                # Card 13, R3: an `answered` observed while the question is still open (parked, or already
                # answered once) appends its own response and leaves the entry open; observed with no park before
                # it (C6 — the store cannot emit this, but the fold must be total over any file), it appends
                # nothing and sets `execution` regardless, without raising.
                if prior_execution in ("parked", "answered"):
                    open_entry = open_park.get(key)
                    if open_entry is not None:
                        open_entry["responses"].append(_response(k, e))
                else:
                    open_park.pop(key, None)
            else:  # complete, closed, reverted, reopened: nothing left open once execution moves on
                open_park.pop(key, None)
        elif k == "failed":
            c["execution"] = f"failed({e['class']})"
            failed.add(key)
            open_park.pop(key, None)
        elif k in ("withdrawn", "demoted") and prior_execution == "dispatched":
            # Card 7 R1/R2, reaffirmed unchanged by card 13 R4: a withdrawal or demotion observed on a *dispatched*
            # run abandons it — never on a run already `complete` (K1), never on a parked or answered run (that is
            # the next branch, card 13 R2), and never on a card with nothing in flight (where neither branch matches
            # and the card is left untouched). The run id rides only when the file names one: a card in flight with
            # no `dispatched` line (a `parked` reported alone) must not raise inside the fold, where every later
            # land would meet the same file — and canon has no null, so an unknown id is an absent key.
            run_id = dispatched_run.get(key)
            c["runs"].append(
                {**({"run_id": run_id} if run_id is not None else {}), "outcome": "abandoned", "ended_at": e["at"]}
            )
            c["execution"] = "abandoned"
        elif k in ("withdrawn", "demoted") and prior_execution in ("parked", "answered"):
            # Card 13, R2/R6: a demotion or withdrawal of a parked or answered card disposes of its question —
            # it abandons no run. It appends a response to the parked run's entry (absent an entry only in the
            # C6 case, where the fold still clears the execution and never raises) and clears the execution, which
            # is R5's whole mechanism: a card re-ratified afterward reads `ratified`/`ready` because nothing here
            # ever wrote `abandoned` for it to clear.
            open_entry = open_park.get(key)
            if open_entry is not None:
                open_entry["responses"].append(_response(k, e))
            c["execution"] = None
            open_park.pop(key, None)
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
            # A ratification landed after a failure is the owner's way back to ready [owner, 2026-09-14]: T-A7 routes
            # a failed run to the design queue and defined no step back out, so a landed failure stranded its card
            # (card 7, `r-4`). The owner's answer is a signed act that already exists — the card edited and
            # re-ratified, or demoted and re-ratified unchanged — and the failure stays in the event file.
            #
            # The same is true of an abandoned run (card 7, R3): a re-ratification after a withdrawal or demotion
            # abandoned the run in flight reads `ratified`/`ready`, not `execution(abandoned)` — the abandoned run
            # stays in the event file, only the sidecar's current field clears.
            if key in failed or c["execution"] == "abandoned":
                c["execution"] = None
                failed.discard(key)
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
