"""Card 31: the PR watcher -- one pass over every open run's pull request, acting through the existing verbs and never
merging.

The operator's waiting between a pull request opening and the run closing is done by a pass that **cannot merge, push,
open a pull request, sign or ratify** (A1, R5). Its own forge use is `Watched`, three calls; what it does to a run it
does by calling `close` and `run_fixup` (which land and which commit locally), under a lease held as `watcher` (R4).

`decide` is the policy and is pure (R1): it is handed the runs' states, the leases already on record, the day's take of
fixup leases, the signed `[watcher]` policy and the time, and returns a typed list of actions. `watch_once` is the
shell around it: the reads before, the verbs after, the log. One pass and return -- no loop and no sleep (A2); the
cadence is the host timer's (card 30).

**The history is the leases** (C3). Whether a rerun or a fixup already happened for a head is read from the run's
lease rows, not from a table of the watcher's own. The closed set of lease actions is `close` and `fixup`
(`ledger.LeaseAction`), so a rerun -- which is a request `close` already makes of the forge -- takes a `close` lease
and is released with the outcome `RERUN`: it must not take a `fixup` lease, because every watcher fixup take counts
against `fixup_per_day`. A watcher action that a verb refused or raised ended its lease with the rule or `raised`, and
is not chosen again at that head (card 35): the run is flagged once instead.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any, Final, Literal, Protocol

from opentelemetry import metrics

from isidium.store.core import telemetry
from isidium.store.core.refusal import Refusal

from .forge import Checks, MergeableState, MergeState, Verdict
from .ledger import DISPATCHED, ENDS, LEASE_HELD, LEASE_RAISED, Holder, LeaseAction, Ledger

PASS_SPAN: Final = "isidium.factory.watch.pass"
ACTION_SPAN: Final = "isidium.factory.watch.action"
READ_SPAN: Final = "isidium.factory.watch.read"
SCOPE: Final = "isidium.factory"

LOG_FILE: Final = "watch.jsonl"
HOLDER: Final[Holder] = "watcher"
# The outcome a rerun's lease is released with: the one fact `decide` reads back to know a head has been rerun.
RERUN: Final = "rerun"
# A rerun is one request to the forge (`close.RERUN_BOUND_S` is what a close waits for the *result*; the watcher does
# not wait), so its lease is declared, not derived: five minutes covers a slow API call and a retry, and a watcher
# that dies in the middle leaves a lease that frees the run again by itself (C-13).
RERUN_LEASE_S: Final = 300.0
# The config schema that introduced `[watcher]` (card 27): below it a tenant has no opt-in to read.
WATCHER_SCHEMA: Final = 8
# What a pass logs an outcome as when it did not act: a lease taken by someone else between the read and the take.
SKIPPED: Final = "skipped"
# What a verb answers with when it completes: a lease released with anything else was refused (its rule id) or raised.
_ANSWERED: Final = frozenset({DISPATCHED, RERUN, *ENDS})
LOGGED: Final = "logged"
ALREADY_LOGGED: Final = "already-logged"

# The ledger's instants, parsed back: the leases table stores UTC text in this one format (`ledger._STAMP`).
_STAMP: Final = "%Y-%m-%dT%H:%M:%SZ"

_meter = metrics.get_meter(SCOPE)
ACTIONS: Final = _meter.create_counter(
    "isidium.factory.watch.actions", unit="{action}", description="the watcher's actions, by action and outcome"
)
FLAGS: Final = _meter.create_counter(
    "isidium.factory.watch.flags", unit="{flag}", description="flags newly logged, by kind"
)
REFUSALS: Final = _meter.create_counter(
    "isidium.factory.watch.refusals", unit="{refusal}", description="refusals met by a pass, by rule id"
)

FlagKind = Literal["stale", "conflicted", "red", "red-after-fixup", "unpushed", "fixup-refused", "rerun-refused"]


class Watched(Protocol):
    """Everything the watcher itself asks of the forge -- `close.Reader`'s own three, narrower than `forge.Forge` so
    that no existing double of `Forge` changes (C1), and with no merge, push or pull-request open in the type (R5)."""

    def merge_state(self, number: int) -> MergeState: ...
    def checks(self, sha: str) -> Checks: ...
    def rerun_failed(self, sha: str) -> tuple[int, ...]: ...


@dataclass(frozen=True)
class Close:
    run_id: str
    head: str


@dataclass(frozen=True)
class Rerun:
    run_id: str
    head: str


@dataclass(frozen=True)
class Fixup:
    run_id: str
    head: str


@dataclass(frozen=True)
class Flag:
    run_id: str
    head: str
    kind: FlagKind


@dataclass(frozen=True)
class Refused(Flag):
    """A flag for an action the watcher took at this head and the verb refused or raised: `rule` is the refusal's rule
    id, or `LEASE_RAISED`. Typed, never a formatted string (C-2); the log row carries it."""

    rule: str


Action = Close | Rerun | Fixup | Flag


@dataclass(frozen=True)
class Past:
    """One lease row on a run, as `decide` reads it: what was taken, at which head, and how it ended."""

    action: str
    head_sha: str | None
    holder: str
    expires_at: datetime
    released_at: str | None
    outcome: str | None


@dataclass(frozen=True)
class View:
    """What a pass knows of one open run. `checks` is `None` when `needs_checks` said not to read them."""

    run_id: str
    head_sha: str | None  # the run's own head, in the ledger
    pr: int
    state: MergeState
    checks: Checks | None
    past: tuple[Past, ...]


@dataclass(frozen=True)
class Policy:
    """The signed `[watcher]` table. Its defaults live in config@8's schema (C-1), never here."""

    fixup: bool
    fixup_per_day: int

    @classmethod
    def from_effective(cls, eff: Mapping[str, Any]) -> Policy | None:
        """`None` -- the opt-in is absent -- for a tenant below config@8 or one whose effective config has no
        `[watcher]` table (R7); otherwise the table as the overlay of the adopted schema's defaults gave it."""
        schema = eff.get("schema")
        table = eff.get("watcher")
        if not isinstance(schema, int) or schema < WATCHER_SCHEMA or table is None:
            return None
        return cls(bool(table["fixup"]), int(table["fixup_per_day"]))


@dataclass(frozen=True)
class Verb:
    """One existing verb as the pass calls it: `run(run_id)` and the lease's bound. The bound is a callable so that a
    fixup's (the signed policy's wall clock, which loads the container module) is read only when a fixup is taken."""

    run: Callable[[str], Mapping[str, Any]]
    lease_s: Callable[[], float]


@dataclass(frozen=True)
class Verbs:
    close: Verb
    fixup: Verb


@dataclass
class Summary:
    """One pass, counted. `line()` is what the verb prints."""

    opt_in_absent: bool
    open: int = 0
    held: int = 0
    unread: int = 0
    closed: int = 0
    reran: int = 0
    fixed: int = 0
    skipped: int = 0
    refused: int = 0
    flags: int = 0
    flags_seen: int = 0

    def line(self) -> str:
        out = (
            f"watch: open={self.open} held={self.held} unread={self.unread} close={self.closed} rerun={self.reran} "
            f"fixup={self.fixed} skipped={self.skipped} refused={self.refused} flagged={self.flags} "
            f"(already logged {self.flags_seen})"
        )
        if self.opt_in_absent:
            out += "; fixup opt-in absent (the tenant is below config@8 or declares no [watcher])"
        return out


# ---- the decision -------------------------------------------------------------------------------------------------


def held(past: Sequence[Past], now: datetime) -> bool:
    """A lease not released and not yet expired: someone is acting on this run."""
    return any(p.released_at is None and p.expires_at > now for p in past)


def needs_checks(state: MergeState) -> bool:
    """Whether `decide` will look at the checks: not for a merged pull request, nor a stale or conflicted one."""
    return not state.merged and state.state not in (MergeableState.BEHIND, MergeableState.DIRTY)


def _rerun_at(past: Sequence[Past], head: str) -> bool:
    return any(p.outcome == RERUN and p.head_sha == head for p in past)


def _fixup_ran(past: Sequence[Past]) -> bool:
    # What `run_fixup` answers when the builder ran and the run is still in flight; a refused or raised one is not one.
    return any(p.action == "fixup" and p.outcome == DISPATCHED for p in past)


def _refused_at(past: Sequence[Past], action: str, head: str) -> str | None:
    """Card 35 R1/R2: how the watcher's last `action` lease at `head` ended, when it ended in a refusal's rule id or
    `LEASE_RAISED`; `None` when there is none. Only the watcher's own leases count, so an operator's refused fixup is
    still not the watcher's to read. A rerun takes a `close` lease (module docstring), so a refused rerun is read from
    one: the watcher's own `Close` is chosen only for a merged pull request, which never reaches the rerun branch."""
    refused = [
        p.outcome
        for p in past
        if p.holder == HOLDER
        and p.action == action
        and p.head_sha == head
        and p.outcome is not None
        and p.outcome not in _ANSWERED
    ]
    return refused[-1] if refused else None


def _decide_one(v: View, taken: int, policy: Policy | None) -> tuple[Action, ...]:
    s = v.state
    if s.merged:
        return (Close(v.run_id, s.head),)
    if s.state is MergeableState.BEHIND:
        return (Flag(v.run_id, s.head, "stale"),)
    if s.state is MergeableState.DIRTY:
        return (Flag(v.run_id, s.head, "conflicted"),)
    if v.checks is None or v.checks.verdict is not Verdict.RED:
        return ()
    if not _rerun_at(v.past, s.head):
        reran = _refused_at(v.past, "close", s.head)
        if reran is not None:
            # Refused or raised once at this head: not asked again (card 35 R2); the flag is the escalation.
            return (Refused(v.run_id, s.head, "rerun-refused", reran),)
        return (Rerun(v.run_id, s.head),)
    if v.head_sha != s.head:
        # The run's head is its fixup's commit and the operator has not pushed it: the pull request still reads the
        # old red head, and `run_fixup` would refuse it. Nothing the watcher may do (it never pushes) but say so.
        return (Flag(v.run_id, s.head, "unpushed"),)
    refused = _refused_at(v.past, "fixup", s.head)
    if not _fixup_ran(v.past):
        if refused is not None:
            # Refused or raised once at this head: not taken again (card 35 R1), so a stuck run is one take.
            return (Refused(v.run_id, s.head, "fixup-refused", refused),)
        if policy is not None and policy.fixup and taken < policy.fixup_per_day:
            return (Fixup(v.run_id, s.head),)
        return (Flag(v.run_id, s.head, "red"),)
    # Red after the fixup, and rerun at this head: the fixup verb ends the run `failed:gate` with no model call, so
    # neither the ceiling nor the opt-in rations it (card 35 R3) -- it is called for every tenant, below config@8 too.
    if refused is not None:
        return (Refused(v.run_id, s.head, "fixup-refused", refused), Flag(v.run_id, s.head, "red-after-fixup"))
    return (Fixup(v.run_id, s.head), Flag(v.run_id, s.head, "red-after-fixup"))


def decide(views: Sequence[View], taken_today: int, policy: Policy | None, now: datetime) -> tuple[Action, ...]:
    """R1: the actions for these runs. Reads nothing: not the ledger, the forge, the clock or the log. `taken_today`
    is the watcher fixup leases taken since the day's start; each `Fixup` chosen here counts as one more, so a single
    pass cannot go over the ceiling by choosing several."""
    out: list[Action] = []
    taken = taken_today
    for v in views:
        if held(v.past, now):
            continue
        acts = _decide_one(v, taken, policy)
        taken += sum(isinstance(a, Fixup) for a in acts)
        out.extend(acts)
    return tuple(out)


# ---- the pass -----------------------------------------------------------------------------------------------------


def _pasts(ledger: Ledger) -> dict[str, tuple[Past, ...]]:
    """Every open run's lease rows, in one query and grouped here -- the ledger has no read of them (C2: `ledger.py` is
    not this card's to change), so this is one read-only SELECT on its connection, as `test_leases` does."""
    rows = ledger.db.execute(
        "SELECT run_id, action, head_sha, holder, expires_at, released_at, outcome FROM leases"
        " WHERE run_id IN (SELECT run_id FROM runs WHERE ended_at IS NULL AND pr IS NOT NULL) ORDER BY rowid"
    ).fetchall()
    grouped: dict[str, list[Past]] = {}
    for r in rows:
        expires = datetime.strptime(str(r["expires_at"]), _STAMP).replace(tzinfo=UTC)
        grouped.setdefault(str(r["run_id"]), []).append(
            Past(str(r["action"]), r["head_sha"], str(r["holder"]), expires, r["released_at"], r["outcome"])
        )
    return {k: tuple(v) for k, v in grouped.items()}


class _Log:
    """`watch.jsonl`: a line per action and per new flag, appended as they happen so a pass that dies keeps what it did.

    The flags already logged are read once, whole, at the start of the pass. The file grows by a line per action and
    new flag -- a few a day at a 15-minute cadence -- so a whole read is cheaper than an index to keep (C-13)."""

    def __init__(self, path: Path, at: datetime) -> None:
        self.path = path
        self.at = at.strftime(_STAMP)
        self.seen: set[tuple[str, str, str]] = set()
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    row = json.loads(line)
                except ValueError:
                    continue  # a half-written line is not a flag; it must not stop the next pass
                if isinstance(row, dict) and row.get("action") == "flag":
                    self.seen.add((str(row.get("run")), str(row.get("head")), str(row.get("kind"))))

    def append(self, row: Mapping[str, Any]) -> None:
        with self.path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps({"at": self.at, **row}, ensure_ascii=False) + "\n")

    def flag(self, f: Flag) -> bool:
        """Logged now, or already logged for this (run, head, kind) and left alone."""
        key = (f.run_id, f.head, f.kind)
        if key in self.seen:
            return False
        self.seen.add(key)
        self.append(
            {
                "run": f.run_id,
                "head": f.head,
                "action": "flag",
                "kind": f.kind,
                **({"rule": f.rule} if isinstance(f, Refused) else {}),
            }
        )
        return True


def _read[T](summary: Summary, run_id: str, what: str, call: Callable[[], T]) -> T | None:
    """One forge read in its own span. A refusal is recorded and counted and the run is left for the next pass."""
    with telemetry.span(READ_SPAN, **{"isidium.run_id": run_id, "isidium.watch.read": what}) as sp:
        try:
            return call()
        except Refusal as r:
            telemetry.record_refusal_on(sp, r.rule)
            REFUSALS.add(1, {telemetry.RULE: r.rule})
            summary.refused += 1
            return None


def _leased(
    ledger: Ledger,
    now: Callable[[], datetime],
    run_id: str,
    action: LeaseAction,
    head: str,
    for_s: float,
    act: Callable[[], Mapping[str, Any]],
) -> str:
    """`act` under the run's `action` lease, held as the watcher, at the pull request's head. Released with the
    action's outcome -- the rule id of a refusal, `LEASE_RAISED` for anything else; a process that dies leaves a lease
    that expires on its own. (The CLI's own `_leased` is the operator's, and is left as it is.)"""
    lease = ledger.take_lease(run_id, action, HOLDER, head, now(), for_s)
    try:
        out = act()
    except Refusal as r:
        ledger.release_lease(lease, now(), r.rule)
        raise
    except BaseException:
        ledger.release_lease(lease, now(), LEASE_RAISED)
        raise
    outcome = str(out["outcome"])
    ledger.release_lease(lease, now(), outcome)
    return outcome


def open_runs(ledger: Ledger) -> list[dict[str, Any]]:
    """C2 (card 31): the open runs are the ledger's in-flight runs that have a pull request. The one home for that
    predicate, so the CLI's idle test and the pass cannot disagree about what counts as open."""
    return [r for r in ledger.in_flight() if r["pr"] is not None]


def idle_pass() -> Summary:
    """Card 37 R1/R3: the pass with nothing to watch -- no open run -- which reads no forge and no policy. It emits the
    same `PASS_SPAN` a busy pass does, with the same attributes at 0. The signed `[watcher]` table lives in the
    effective config, which only `context.load` reads, so this pass never knew the opt-in and does not claim it absent
    (`opt_in_absent` stays false: the line is the ordinary one with `open=0`)."""
    summary = Summary(opt_in_absent=False)
    with telemetry.span(PASS_SPAN) as sp:
        sp.set_attribute("isidium.watch.open", summary.open)
        sp.set_attribute("isidium.watch.held", summary.held)
        sp.set_attribute("isidium.watch.refused", summary.refused)
        telemetry.record_ok()
    return summary


def watch_once(
    ledger: Ledger,
    forge: Watched,
    policy: Policy | None,
    verbs: Verbs,
    log: Path,
    now: Callable[[], datetime],
) -> Summary:
    """R4: one pass. The open runs are the ledger's in-flight runs that have a pull request (C2). A run holding a
    lease is skipped before any forge read; the rest are read -- merge state, then the checks when `decide` will look at
    them -- and `decide`'s actions are executed one after another, each under its own lease and span."""
    t = now().astimezone(UTC)
    summary = Summary(opt_in_absent=policy is None)
    with telemetry.span(PASS_SPAN) as sp:
        rows = open_runs(ledger)
        summary.open = len(rows)
        pasts = _pasts(ledger)
        views: list[View] = []
        for row in rows:
            run_id = str(row["run_id"])
            past = pasts.get(run_id, ())
            if held(past, t):
                summary.held += 1
                continue
            state = _read(summary, run_id, "merge_state", partial(forge.merge_state, int(row["pr"])))
            if state is None:
                summary.unread += 1
                continue
            checks: Checks | None = None
            if needs_checks(state):
                checks = _read(summary, run_id, "checks", partial(forge.checks, state.head))
                if checks is None:
                    summary.unread += 1
                    continue
            views.append(View(run_id, row["head_sha"], int(row["pr"]), state, checks, past))

        day = t.replace(hour=0, minute=0, second=0, microsecond=0)
        taken = ledger.leases_taken(HOLDER, "fixup", day)
        entries = _Log(log, t)
        for act in decide(views, taken, policy, t):
            _execute(ledger, forge, verbs, entries, now, summary, act)

        sp.set_attribute("isidium.watch.open", summary.open)
        sp.set_attribute("isidium.watch.held", summary.held)
        sp.set_attribute("isidium.watch.refused", summary.refused)
        telemetry.record_ok()
    return summary


def _execute(
    ledger: Ledger,
    forge: Watched,
    verbs: Verbs,
    entries: _Log,
    now: Callable[[], datetime],
    summary: Summary,
    act: Action,
) -> None:
    name = type(act).__name__.lower()
    with telemetry.span(ACTION_SPAN, **{"isidium.run_id": act.run_id, "isidium.watch.action": name}) as sp:
        rule: str | None = None
        try:
            outcome = _do(ledger, forge, verbs, entries, now, summary, act)
        except Refusal as r:
            if r.rule == LEASE_HELD:  # taken by someone else after the read: this run is theirs this pass
                outcome = SKIPPED
                summary.skipped += 1
            else:
                rule = outcome = r.rule
                telemetry.record_refusal_on(sp, r.rule)
                REFUSALS.add(1, {telemetry.RULE: r.rule})
                summary.refused += 1
        sp.set_attribute("isidium.outcome", outcome)
        ACTIONS.add(1, {"isidium.watch.action": name, "isidium.outcome": outcome})
        if not isinstance(act, Flag):
            entries.append(
                {
                    "run": act.run_id,
                    "head": act.head,
                    "action": name,
                    "outcome": outcome,
                    **({"rule": rule} if rule else {}),
                }
            )


def _do(
    ledger: Ledger,
    forge: Watched,
    verbs: Verbs,
    entries: _Log,
    now: Callable[[], datetime],
    summary: Summary,
    act: Action,
) -> str:
    """The one action, through its verb, and the outcome it ended with. Counted in the summary when it completes: a
    skip and a refusal are the caller's to count."""
    if isinstance(act, Flag):
        if entries.flag(act):
            summary.flags += 1
            FLAGS.add(1, {"isidium.watch.kind": act.kind})
            return LOGGED
        summary.flags_seen += 1
        return ALREADY_LOGGED
    if isinstance(act, Close):
        out = _leased(
            ledger, now, act.run_id, "close", act.head, verbs.close.lease_s(), lambda: verbs.close.run(act.run_id)
        )
        summary.closed += 1
        return out
    if isinstance(act, Fixup):
        out = _leased(
            ledger, now, act.run_id, "fixup", act.head, verbs.fixup.lease_s(), lambda: verbs.fixup.run(act.run_id)
        )
        summary.fixed += 1
        return out

    def rerun() -> Mapping[str, Any]:
        forge.rerun_failed(act.head)
        return {"outcome": RERUN}

    out = _leased(ledger, now, act.run_id, "close", act.head, RERUN_LEASE_S, rerun)
    summary.reran += 1
    return out
