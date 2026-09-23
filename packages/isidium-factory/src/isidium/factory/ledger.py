"""The ledger — the factory's own sqlite, one per tenant, at the deploy home [V3; Q-V1 ruled 2026-09-10].

Q-V1 [owner]: *"the factory's own sqlite in its state directory, one per tenant; the run record as rows, the run
report generated from it."* 03 §1.15: the ledger is *"authority for factory facts"*. T-A6 (7): *"ledger record written
before the run starts — no record, no run"*; its failure protocol: *"Ledger write fails ⇒ no dispatch (fail-closed)"*.

**The store's `Journal` posture** (`server/journal.py`): one file, `journal_mode=WAL`, `synchronous=NORMAL`, every
write inside one `BEGIN IMMEDIATE` transaction, a `meta` table holding the schema version, the tenant and the counter.
**The run id is `r-<n>` from that counter** (Q-V13): allocated inside the transaction that writes the row, so an id
is never handed out for a row that was not written. A run id already held is `ledger.duplicate-run` and the table is
unchanged (finding 18: *"idempotence by run id is the ledger's"* — made mechanical by the primary key).

Tables are 03 §6's run record as rows: `runs` (the entry; `phases` / `verdicts` its two lists, V4/V5's to write), the
ledger's own `events` (`dispatched` is a run's first), and `heads` (03 §1.15's history heads and journal head at every
land — still unwritten after V5a: the store's `land` answers neither the journal head's hash nor the history heads,
and the table's key, `landed_at`, is the cursor commit's time, which two lands at one cursor share). `report(run_id)`
folds a run's events into the store's `RunReport`: *"the run report generated from it"* — since V5a
(`lander.land_run`) the land hands the store what the ledger says, never a hand-written file, and once.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, get_args

from isidium.store.core import events as events_mod
from isidium.store.core import telemetry
from isidium.store.core.refusal import Refusal

LEDGER_FILE: Final = "ledger.sqlite"
# Schema 2 [V5a]: `runs.pr` (the pull request `close` reads) and `runs.landed_through` (the watermark: the last event
# `seq` of the run the store has been sent).
# Schema 3 [2026-09-20]: `runs.carried_from` — the failed run whose work this one carries (Q-V31 (c)).
#
# **`carried_from`, not `resumes`** [Q-V34, owner 2026-09-20]. `resume` is already taken: `score.vector.resume` is a
# card-level ordering boost meaning *"this card has partly-done work — finish before starting"*. The owner ruled
# that the new thing takes its own name and the ordering term is left alone, so nothing in the ratified schema and
# none of the records already written has to move. The particular word is the briefer's, within that ruling, and
# says what happens: a failed run's work is carried onto this run's branch.
SCHEMA: Final = 3
# Every column `runs` gained after schema 1, and what to declare it as. One list, read by the migration and by
# nothing else: a column added to `_DDL` below and forgotten here would exist on a fresh ledger and never appear on
# an upgraded one, which is the drift this pairs against.
ADDED_COLUMNS: Final[Mapping[str, str]] = {"pr": "INTEGER", "landed_through": "INTEGER", "carried_from": "TEXT"}
SPAN: Final = "isidium.factory.ledger.write"
DISPATCHED: Final = "dispatched"
# The ledger's own transitions, beside `interrupt`: neither is a store event kind, so `report()`
# filters them out and `runs --run` is where they are read.
PHASE: Final = "phase"
ENDED: Final = "ended"
# The outcomes a run ends as — a closed set since V5a (T-A7: `complete` | `failed:<class>` | `parked`; T-A9's
# `closed`; 03 §6's *abandon the run*). `complete` is not among them: T-A9 runs straight after it, so the ledger writes
# the store's `complete` event and ends the run `closed` in one transaction. The classes are the store's own union.
CLOSED: Final = "closed"
ABANDONED: Final = "abandoned"
PARKED: Final = "parked"
FAILED: Final = "failed:"
ENDS: Final[frozenset[str]] = frozenset(
    {CLOSED, ABANDONED, PARKED, *(FAILED + c for c in get_args(events_mod.FailureClass))}
)

_DDL: Final = (
    "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
    """CREATE TABLE IF NOT EXISTS runs (
        run_id TEXT PRIMARY KEY, card INTEGER NOT NULL, batch TEXT, outcome TEXT NOT NULL, lane TEXT NOT NULL,
        build_hash TEXT NOT NULL, base_sha TEXT NOT NULL, head_sha TEXT, story_branch TEXT NOT NULL,
        adapter TEXT NOT NULL, billing_class TEXT, dispatched_at TEXT NOT NULL, ended_at TEXT,
        payload_hash TEXT NOT NULL, config_hash TEXT NOT NULL, context TEXT NOT NULL, score TEXT NOT NULL,
        refs_resolved TEXT NOT NULL, surfaces_actual TEXT, price_table TEXT, identity TEXT NOT NULL,
        pr INTEGER, landed_through INTEGER, carried_from TEXT)""",
    """CREATE TABLE IF NOT EXISTS phases (
        run_id TEXT NOT NULL REFERENCES runs(run_id), phase TEXT NOT NULL, agent TEXT, model TEXT, effort TEXT,
        prompt_version TEXT, tokens INTEGER, cost_micro INTEGER, duration_ms INTEGER)""",
    """CREATE TABLE IF NOT EXISTS verdicts (
        run_id TEXT NOT NULL REFERENCES runs(run_id), phase TEXT NOT NULL, verdict TEXT NOT NULL, reasoning TEXT)""",
    """CREATE TABLE IF NOT EXISTS events (
        seq INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL REFERENCES runs(run_id), at TEXT NOT NULL,
        kind TEXT NOT NULL, data TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS heads (
        landed_at TEXT PRIMARY KEY, cursor TEXT NOT NULL, journal_head TEXT NOT NULL, history_heads TEXT NOT NULL)""",
)
_JSON_COLUMNS: Final = frozenset({"context", "score", "refs_resolved", "surfaces_actual", "price_table"})


@dataclass(frozen=True)
class NewRun:
    """The `dispatched` record of T-A6, before its id: everything the pick knows when it writes."""

    card: int
    lane: str  # `expedite` or `standard` — the expedite dial counts it (02-prioritization, Tier 0)
    build_hash: str
    base_sha: str
    adapter: str
    dispatched_at: str
    payload_hash: str
    config_hash: str
    identity: str  # the bot's login, never a credential (03 §6, round 34)
    context: Mapping[str, Any] = field(default_factory=dict)
    score: Mapping[str, Any] = field(default_factory=dict)
    refs_resolved: tuple[Mapping[str, str], ...] = ()
    carried_from: str | None = None  # the failed run whose work this one carries (Q-V31 (c))


class Ledger:
    """One tenant's ledger. `open` is the constructor a verb uses; the file is created on first open."""

    def __init__(self, path: Path, tenant: str) -> None:
        self.path = path
        self.db = sqlite3.connect(str(path), isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        with self.transaction():
            for ddl in _DDL:
                self.db.execute(ddl)
            self.db.execute("INSERT OR IGNORE INTO meta VALUES ('schema', ?)", (str(SCHEMA),))
            self.db.execute("INSERT OR IGNORE INTO meta VALUES ('tenant', ?)", (tenant,))
            self.db.execute("INSERT OR IGNORE INTO meta VALUES ('next_run', '1')")
        held = self._meta("tenant")
        if held != tenant:
            self.db.close()
            raise Refusal("ledger.tenant", str(path), f"this ledger is {held!r}'s, not {tenant!r}'s")
        if int(self._meta("schema") or SCHEMA) < SCHEMA:
            # Eager, at open [V5a]: every verb reads these columns, and a live tenant's ledger is a version behind
            # with its runs in it. `ADD COLUMN` only (no table rebuild, the rows untouched), and the version, in one
            # transaction — after the tenant check, so another tenant's file is refused before it is changed.
            #
            # **The version says WHETHER to migrate; the table says WHAT is missing** [2026-09-20]. Two findings put
            # it this way round. (1) It read `if self._meta("schema") == "1"` — an equality against the only older
            # version there was, true exactly once; tenant #0's ledger is schema 2, so that shape would have left
            # `carried_from` unadded and every read of it an `OperationalError` on the live tenant. (2) Its
            # replacement asked the version which columns to add, and CI refused it: a file's recorded version and
            # its actual shape **can disagree** — V5a's own test builds a "schema 1" table out of the current DDL —
            # and a migration that believes the number over the table adds a column that is already there. Reading
            # `table_info` costs one query and makes this idempotent, which a migration should be anyway.
            have = {str(r[1]) for r in self.db.execute("PRAGMA table_info(runs)")}
            with self.transaction():
                for column, decl in ADDED_COLUMNS.items():  # names from this module, never from input
                    if column not in have:
                        self.db.execute(f"ALTER TABLE runs ADD COLUMN {column} {decl}")
                self.db.execute("UPDATE meta SET value = ? WHERE key = 'schema'", (str(SCHEMA),))

    @classmethod
    @contextmanager
    def open(cls, home: Path, tenant: str) -> Iterator[Ledger]:
        led = cls(home / LEDGER_FILE, tenant)
        try:
            yield led
        finally:
            led.close()

    def close(self) -> None:
        self.db.close()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        self.db.execute("COMMIT")

    def _meta(self, key: str) -> str:
        row = self.db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return str(row["value"]) if row else ""

    # ---- the one write T-A6 names ------------------------------------------------------------------------------

    def dispatch(self, run: NewRun) -> str:
        """The run row and its `dispatched` event in ONE transaction, the id allocated inside it: `r-<n>`. A held
        id is `ledger.duplicate-run` and nothing is written — the counter included."""
        with telemetry.span(SPAN, **{"isidium.card": run.card}) as sp:
            try:
                with self.transaction():
                    n = int(self._meta("next_run"))
                    run_id = f"r-{n}"
                    self.db.execute(
                        "INSERT INTO runs (run_id, card, outcome, lane, build_hash, base_sha, story_branch, adapter,"
                        " dispatched_at, payload_hash, config_hash, context, score, refs_resolved, identity,"
                        " carried_from) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            run_id,
                            run.card,
                            DISPATCHED,
                            run.lane,
                            run.build_hash,
                            run.base_sha,
                            f"story/{run_id}",
                            run.adapter,
                            run.dispatched_at,
                            run.payload_hash,
                            run.config_hash,
                            _dump(run.context),
                            _dump(run.score),
                            _dump([dict(r) for r in run.refs_resolved]),
                            run.identity,
                            run.carried_from,
                        ),
                    )
                    self._event(run_id, run.dispatched_at, DISPATCHED, {"card": run.card})
                    self.db.execute("UPDATE meta SET value = ? WHERE key = 'next_run'", (str(n + 1),))
            except sqlite3.IntegrityError as e:
                refusal = Refusal("ledger.duplicate-run", f"r-{self._meta('next_run')}", str(e))
                telemetry.record_refusal_on(sp, refusal.rule)
                raise refusal from None
            sp.set_attribute("isidium.run_id", run_id)
            return run_id

    def fail(self, run_id: str, at: str, reason: str, detail: str) -> None:
        """What happened after the record, told truthfully (T-A6's failure protocol): the run ends
        `failed:<reason>` — with the store's `failed` event beside it since V5a — and the detail as an event of the
        ledger's own."""
        with telemetry.span(SPAN, **{"isidium.run_id": run_id}), self.transaction():
            self._end(run_id, at, FAILED + reason)
            self._event(run_id, at, "interrupt", {"reason": reason, "detail": detail})

    def phase(self, run_id: str, at: str, result: Mapping[str, Any]) -> None:
        """A phase's record, written the way `dispatch` writes a run's: the `phases` row and the ledger's own
        `phase` event in ONE transaction (the card's R2 — *"the same transaction discipline dispatch used"*).

        The row is 03 §6's `phases[]` entry exactly — agent kind, effort and prompt version beside model, tokens,
        cost and duration — and nothing more. What the phase also produced (its artifacts by hash, the writes the
        guard denied, the set git says it touched, how it ended) rides the **event**, because the run record's
        shape is ratified and the ledger's own transition log is where a fact without a column belongs."""
        if self.run(run_id) is None:
            raise Refusal("ledger.unknown-run", run_id, "no such run in this ledger")
        with telemetry.span(SPAN, **{"isidium.run_id": run_id}), self.transaction():
            self.db.execute(
                "INSERT INTO phases (run_id, phase, agent, model, effort, prompt_version, tokens, cost_micro,"
                " duration_ms) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    result["phase"],
                    result.get("agent"),
                    result.get("model"),
                    result.get("effort"),
                    result.get("prompt_version"),
                    result.get("tokens"),
                    result.get("cost_micro"),
                    result.get("duration_ms"),
                ),
            )
            self._event(
                run_id,
                at,
                PHASE,
                {
                    "phase": result["phase"],
                    "outcome": result.get("outcome"),
                    "artifacts": result.get("artifacts", []),
                    "guard_blocks": result.get("guard_blocks", 0),
                    "touched": result.get("touched", []),
                    "cache_read_tokens": result.get("cache_read_tokens", 0),
                    "cache_write_tokens": result.get("cache_write_tokens", 0),
                    "harness": result.get("harness"),
                    "harness_version": result.get("harness_version"),
                    "billing_class": result.get("billing_class"),
                },
            )

    def finish(
        self,
        run_id: str,
        at: str,
        outcome: str,
        *,
        head_sha: str | None = None,
        surfaces_actual: Any = None,
        billing_class: str | None = None,
        price_table: Any = None,
    ) -> None:
        """The run, ended. 03 §6's tail of the record in one write: what it ended as, at which head, what it
        actually touched (T-B7 (4): *"surfaces actual computed from the diff, not from the plan"*), and the
        billing lane the run drew on — the measurement the ruled harness swap reads (7bdb.4(5)). `end` with nothing
        of the caller's to add."""
        self.end(
            run_id,
            at,
            outcome,
            head_sha=head_sha,
            surfaces_actual=surfaces_actual,
            billing_class=billing_class,
            price_table=price_table,
        )

    def end(
        self,
        run_id: str,
        at: str,
        outcome: str,
        *,
        head_sha: str | None = None,
        surfaces_actual: Any = None,
        billing_class: str | None = None,
        price_table: Any = None,
        store_events: Sequence[tuple[str, Mapping[str, Any]]] = (),
        detail: Mapping[str, Any] | None = None,
    ) -> None:
        """**The one writer of `ended_at`** [V5a]. Until V5a a run that succeeded was never ended — `advance` moved
        its head and nothing else — so `wip = 1` meant one card, ever. Now every end is this: the outcome from the
        closed set (`ledger.outcome` outside it), a run already ended refused (`ledger.ended`), the caller's store
        events (`complete`, `closed`), the store's own event for the outcome (`failed{class}`, `parked`), and the
        ledger's `ended` with the detail — one transaction, so `report()` carries the end without translating it at
        land time."""
        with telemetry.span(SPAN, **{"isidium.run_id": run_id, "isidium.outcome": outcome}), self.transaction():
            self._end(
                run_id,
                at,
                outcome,
                head_sha=head_sha,
                surfaces_actual=surfaces_actual,
                billing_class=billing_class,
                price_table=price_table,
                store_events=store_events,
            )
            self._event(run_id, at, ENDED, {"outcome": outcome, **(detail or {})})

    def _end(
        self,
        run_id: str,
        at: str,
        outcome: str,
        *,
        head_sha: str | None = None,
        surfaces_actual: Any = None,
        billing_class: str | None = None,
        price_table: Any = None,
        store_events: Sequence[tuple[str, Mapping[str, Any]]] = (),
    ) -> None:
        if outcome not in ENDS:
            raise Refusal("ledger.outcome", outcome, "not an outcome a run ends as: " + ", ".join(sorted(ENDS)))
        cur = self.db.execute(
            "UPDATE runs SET outcome = ?, ended_at = ?, head_sha = COALESCE(?, head_sha),"
            " surfaces_actual = COALESCE(?, surfaces_actual), billing_class = COALESCE(?, billing_class),"
            " price_table = COALESCE(?, price_table) WHERE run_id = ? AND ended_at IS NULL",
            (
                outcome,
                at,
                head_sha,
                None if surfaces_actual is None else _dump(surfaces_actual),
                billing_class,
                None if price_table is None else _dump(price_table),
                run_id,
            ),
        )
        if cur.rowcount == 0:
            was = self.db.execute("SELECT outcome, ended_at FROM runs WHERE run_id = ?", (run_id,)).fetchone()
            if was is None:
                raise Refusal("ledger.unknown-run", run_id, "no such run in this ledger")
            raise Refusal("ledger.ended", run_id, f"this run ended {was['ended_at']} as {was['outcome']}")
        for kind, data in store_events:
            self._event(run_id, at, kind, data)
        if outcome.startswith(FAILED):
            self._event(run_id, at, "failed", {"class": outcome[len(FAILED) :], "run_id": run_id})
        elif outcome == PARKED:
            self._event(run_id, at, PARKED, {"run_id": run_id})

    def set_pr(self, run_id: str, number: int) -> None:
        """The run's pull request, on its row [V5a] — `pr-open` writes it; `close --pr` names one the ledger missed."""
        with self.transaction():
            cur = self.db.execute("UPDATE runs SET pr = ? WHERE run_id = ?", (number, run_id))
            if cur.rowcount == 0:
                raise Refusal("ledger.unknown-run", run_id, "no such run in this ledger")

    def landed(self, run_id: str, through: int) -> None:
        """The watermark advanced, after the store answered [V5a] — and never backwards."""
        with self.transaction():
            self.db.execute(
                "UPDATE runs SET landed_through = ? WHERE run_id = ? AND COALESCE(landed_through, 0) < ?",
                (through, run_id, through),
            )

    def advance(self, run_id: str, head_sha: str, surfaces_actual: Any, billing_class: str | None) -> None:
        """A run that is further along but not over: the head its last phase committed, what it has touched so far
        (T-B7 (4): from the diff, never the plan), and the lane it drew on. `ended_at` is untouched — V5's close is
        what ends a run, and a run that a phase merely advanced is still in flight for the WIP cap."""
        with self.transaction():
            cur = self.db.execute(
                "UPDATE runs SET head_sha = ?, surfaces_actual = ?, billing_class = COALESCE(?, billing_class)"
                " WHERE run_id = ?",
                (head_sha, _dump(surfaces_actual), billing_class, run_id),
            )
            if cur.rowcount == 0:
                raise Refusal("ledger.unknown-run", run_id, "no such run in this ledger")

    def _event(self, run_id: str, at: str, kind: str, data: Mapping[str, Any]) -> None:
        self.db.execute(
            "INSERT INTO events (run_id, at, kind, data) VALUES (?, ?, ?, ?)", (run_id, at, kind, _dump(data))
        )

    # ---- reads ------------------------------------------------------------------------------------------------------

    def in_flight(self) -> list[dict[str, Any]]:
        """Runs dispatched and not ended — the WIP cap's count and the expedite dial's."""
        rows = self.db.execute("SELECT * FROM runs WHERE ended_at IS NULL ORDER BY dispatched_at, run_id").fetchall()
        return [_row(r) for r in rows]

    def run(self, run_id: str) -> dict[str, Any] | None:
        r = self.db.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        return _row(r) if r else None

    def runs(self) -> list[dict[str, Any]]:
        return [_row(r) for r in self.db.execute("SELECT * FROM runs ORDER BY dispatched_at, run_id").fetchall()]

    def phases_of(self, run_id: str) -> list[dict[str, Any]]:
        """03 §6's `phases[]` for one run, in the order they ran."""
        rows = self.db.execute("SELECT * FROM phases WHERE run_id = ? ORDER BY rowid", (run_id,)).fetchall()
        return [{k: r[k] for k in r.keys() if k != "run_id"} for r in rows]  # noqa: SIM118

    def artifacts_of(self, run_id: str) -> dict[str, dict[str, Any]]:
        """The run's artifacts by name, from its `phase` events — the newest of a name wins, so a revised plan is the
        plan a later phase reads. One query over the run's own events; the bytes stay in the run directory."""
        rows = self.db.execute(
            "SELECT data FROM events WHERE run_id = ? AND kind = ? ORDER BY seq", (run_id, PHASE)
        ).fetchall()
        out: dict[str, dict[str, Any]] = {}
        for r in rows:
            for a in json.loads(r["data"]).get("artifacts") or []:
                out[str(a["name"])] = dict(a)
        return out

    def events_of(self, run_id: str, *, since: int = 0) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT * FROM events WHERE run_id = ? AND seq > ? ORDER BY seq", (run_id, since)
        ).fetchall()
        return [{"seq": r["seq"], "at": r["at"], "kind": r["kind"], "data": json.loads(r["data"])} for r in rows]

    def report(self, run_id: str) -> events_mod.RunReport:
        """The run report generated from the ledger (Q-V1): the run's events that are the store's union, as the
        store parses them. The ledger's own `interrupt` is not a store event (the union has no such kind) and stays
        here, where `runs --run` shows it."""
        run = self._need(run_id)
        return _report(run, self.events_of(run_id))

    def unlanded(self, run_id: str) -> tuple[events_mod.RunReport, int | None]:
        """What the store has not been sent [V5a]: the run's store events past its watermark, and the `seq` the
        watermark moves to once the store has answered — `None` when there is nothing to send. The events past the
        watermark are the query's to find, not a scan of the run's whole history."""
        run = self._need(run_id)
        fresh = self.events_of(run_id, since=int(run["landed_through"] or 0))
        report = _report(run, fresh)
        return report, (int(fresh[-1]["seq"]) if report.events else None)

    def _need(self, run_id: str) -> dict[str, Any]:
        run = self.run(run_id)
        if run is None:
            raise Refusal("ledger.unknown-run", run_id, "no such run in this ledger")
        return run


def _report(run: Mapping[str, Any], events: Sequence[Mapping[str, Any]]) -> events_mod.RunReport:
    evs = [
        {"kind": e["kind"], "card": run["card"], "at": e["at"], "run_id": run["run_id"]}
        if e["kind"] == DISPATCHED
        else {"kind": e["kind"], "card": run["card"], "at": e["at"], **e["data"]}
        for e in events
        if e["kind"] in events_mod.KINDS and e["kind"] not in events_mod.OBSERVED_KINDS
    ]
    return events_mod.parse_report({"run_id": run["run_id"], "events": evs, "suggestions": []})


def _dump(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _row(r: sqlite3.Row) -> dict[str, Any]:
    return {k: (json.loads(r[k]) if k in _JSON_COLUMNS and r[k] is not None else r[k]) for k in r.keys()}  # noqa: SIM118
