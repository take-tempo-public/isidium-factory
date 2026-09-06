"""The journal (03b §2, 03 §9.6): the store's write-ahead record of every governed transition — one row
`{seq, at, caller, paths: [{path, before_blob?, after_blob?}]}` + `h`, append-only, hash-chained from the genesis
`sha256(b"schema:<n>\\njournal:<tenant>")`; a repairing row carries `repairs = <commit>` inside the content and
`sig = sign(tenant ‖ h_row)` outside. Stored in the store's container, outside any repo — one SQLite file per tenant
(WAL) that also holds the id counter, a path index over the rows (the reconciliation's "one journal query bounded by
the files touched", 9.4), the blob-sha cache (9.4: 0 build hashes on a warm cache), the last-signed blob per path
(the X1 display's baseline, durable across restarts), and the pending-write bytes that let a half-applied write
replay after a crash. One transaction per call: `BEGIN IMMEDIATE` is the tenant's row lock.

**Two versions, one chain** [K6, H-1; ruled 7bg.10]. The row's shape is a registry document, `journal@<n>`, and the
tenant adopts a version through its `config.toml` — a signed `config-policy` act, like any other schema adoption.
A row written under `journal@2` carries **the version it was written under** (`schema = 2`) and the **credential**
that asserted the principal (`sha256:<hex>` of the client certificate the channel presented); a `journal@1` row
carries neither, and its shape is byte-for-byte what it was before K6. Both are inside the hashed content. The trace
context (`trace_id`, `span_id`) sits **beside** the content where `sig` does, never inside it (C-9).

**The genesis is pinned once, at the first row, and a bump never re-genesises a live chain.** The genesis carries
the version the chain *opened* under; each row carries the version it was *written* under. So the journal of a
tenant that opened under `journal@1` and later adopted `journal@2` verifies from its original genesis, rows 1…k
in the @1 shape and k+1… in the @2 shape — which is what the ruling's *"record the version the row was written
under"* asks for, and it is the only shape that works, because tenant #0 held three real rows before this landed.
`meta.schema` holds the pinned version; a journal with rows and no pin was written by a store older than K6, and
`journal@1` is the only version such a store could write.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Final

from ..core import chain
from ..core.refusal import Refusal

SCHEMA_SQL: Final = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS journal (
  seq INTEGER PRIMARY KEY, at TEXT NOT NULL, caller TEXT NOT NULL, paths TEXT NOT NULL,
  repairs TEXT, h TEXT NOT NULL, sig TEXT,
  schema INTEGER, credential TEXT, trace_id TEXT, span_id TEXT);
CREATE TABLE IF NOT EXISTS journal_paths (seq INTEGER NOT NULL, path TEXT NOT NULL, PRIMARY KEY (path, seq));
CREATE TABLE IF NOT EXISTS pending (seq INTEGER NOT NULL, path TEXT NOT NULL, data BLOB, PRIMARY KEY (seq, path));
CREATE TABLE IF NOT EXISTS blobs (
  blob TEXT PRIMARY KEY, build TEXT NOT NULL, head_seq INTEGER NOT NULL, head_h TEXT NOT NULL,
  ext_hash TEXT NOT NULL, canon INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS signed (path TEXT PRIMARY KEY, blob TEXT NOT NULL, seq INTEGER NOT NULL);
"""
# The four columns K6 added, in the order `SCHEMA_SQL` declares them. A journal file made before K6 has none of
# them; `ALTER TABLE … ADD COLUMN` is a metadata change in SQLite (no rewrite), paid once per file on the first open.
_K6_COLUMNS: Final[tuple[tuple[str, str], ...]] = (
    ("schema", "INTEGER"),
    ("credential", "TEXT"),
    ("trace_id", "TEXT"),
    ("span_id", "TEXT"),
)
# Everything a row carries that is NOT chained content: `h` and `sig` (5.5) and, since K6, the trace pointer.
BESIDE: Final[frozenset[str]] = frozenset({"h", "sig", "trace_id", "span_id"})
# The first journal version that carries `schema` and `credential` inside its rows.
_CARRIES_IDENTITY: Final = 2

Row = dict[str, Any]


class Journal:
    def __init__(self, path: str | Path, tenant: str) -> None:
        self.tenant = tenant
        # `check_same_thread=False` [K7b, Q15]: the journal is opened by `serve` on the main thread — `Store.load`
        # replays pending rows there, before the listener exists — and every call after that runs on the store's
        # one worker thread (`server/http.py`, `Worker`). Python's default check would refuse the second thread
        # outright; SQLite itself is built serialized and is fine with two threads that never overlap, which these
        # do not: the main thread's last touch is before the first call is accepted. The row lock (`transaction`
        # below, `_in_txn`) was written for one thread at a time and that is still exactly what it gets.
        self.db = sqlite3.connect(str(path), isolation_level=None, check_same_thread=False)  # autocommit; BEGIN below
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        self.db.executescript(SCHEMA_SQL)
        present = {str(r[1]) for r in self.db.execute("PRAGMA table_info(journal)")}
        for column, kind in _K6_COLUMNS:
            if column not in present:
                self.db.execute(f"ALTER TABLE journal ADD COLUMN {column} {kind}")
        self.db.execute("INSERT OR IGNORE INTO meta VALUES ('tenant', ?)", (tenant,))
        self.db.execute("INSERT OR IGNORE INTO meta VALUES ('counter', '0')")
        got = self.db.execute("SELECT value FROM meta WHERE key='tenant'").fetchone()[0]
        if got != tenant:
            raise ValueError(f"journal belongs to tenant {got!r}, not {tenant!r}")
        if self._pinned() is None and self.db.execute("SELECT 1 FROM journal LIMIT 1").fetchone() is not None:
            # Rows and no pin: written by a store older than K6, whose only journal version was the v1 baseline.
            # Pinned now so the genesis this chain was built from is a stored fact rather than a guess at every open.
            self.db.execute("INSERT INTO meta VALUES ('schema', ?)", (str(chain.DEFAULT_REGISTRY["journal"]),))
        self._in_txn = False
        # The version rows are written under. **Supplied by the store from the tenant's adopted config**, never
        # defaulted here (C-1): `adopt` is called before the first append, and again whenever a policy write moves
        # the tenant to another journal version.
        self.schema: int | None = None

    # ---- the adopted version ------------------------------------------------------------------------------------

    def adopt(self, schema: int) -> None:
        """The journal version this tenant writes under, from its effective config (`cfg.journal_schema`). Changes
        what the next row carries; never what the chain's genesis was."""
        self.schema = schema

    def _pinned(self) -> int | None:
        r = self.db.execute("SELECT value FROM meta WHERE key='schema'").fetchone()
        return int(r[0]) if r else None

    @property
    def genesis(self) -> str:
        """The chain's h_0: under the pinned version once a row exists, else under the version the next row would
        pin — so `head` and `verify` agree with `append` on an empty journal too."""
        pinned = self._pinned()
        if pinned is None:
            pinned = self._adopted()
        return chain.genesis("journal", self.tenant, pinned)

    def _adopted(self) -> int:
        if self.schema is None:
            # A bug in the store, not a refusal a caller can act on: `Store` adopts at construction and again at
            # every config change, so reaching this means a journal was driven without a store in front of it.
            raise RuntimeError("the journal has no adopted version: call `adopt` before the first row")
        return self.schema

    # ---- transactions --------------------------------------------------------------------------------------------

    @contextmanager
    def transaction(self) -> Generator[None]:
        """The row lock (1.2 step 2; the sitting's transaction, 1.12 step 3). Held across the signer's round trip by
        `ratify`; a re-entrant call from inside it is refused (`write.locked`), never deadlocked."""
        if self._in_txn:
            raise Refusal("write.locked", "", "the tenant's row lock is held by the current transaction")
        self.db.execute("BEGIN IMMEDIATE")
        self._in_txn = True
        try:
            yield
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        else:
            self.db.execute("COMMIT")
        finally:
            self._in_txn = False

    # ---- the counter (1.6) ---------------------------------------------------------------------------------------

    def new_id(self) -> int:
        """Allocate the next card id — allocation precedes validation; a refused creation burns the id; ids are never
        reused. Inside a transaction when one is open (the sitting's NewCard member), else in its own."""
        if self._in_txn:
            return self._bump()
        with self.transaction():
            return self._bump()

    def _bump(self) -> int:
        n = int(self.db.execute("SELECT value FROM meta WHERE key='counter'").fetchone()[0]) + 1
        self.db.execute("UPDATE meta SET value=? WHERE key='counter'", (str(n),))
        return n

    @property
    def counter(self) -> int:
        return int(self.db.execute("SELECT value FROM meta WHERE key='counter'").fetchone()[0])

    # ---- the chain -----------------------------------------------------------------------------------------------

    @property
    def head(self) -> tuple[int, str]:
        """`{seq, h}` of the last row (0 and the genesis before any row) — `journal_head` in the sidecar."""
        r = self.db.execute("SELECT seq, h FROM journal ORDER BY seq DESC LIMIT 1").fetchone()
        return (int(r[0]), str(r[1])) if r else (0, self.genesis)

    def append(
        self,
        at: str,
        caller: str,
        paths: Sequence[Row],
        *,
        credential: str | None,
        trace: tuple[str, str] | None,
        repairs: str | None = None,
        pending: dict[str, bytes] | None = None,
    ) -> Row:
        """Append one row inside the caller's transaction; returns the row with `h`. `pending` holds the bytes the
        write is about to put on disk, cleared by `applied()` once the commit lands.

        `credential` and `trace` are **keyword-only and have no default**: the one way to omit either is to say so at
        the call, so a call site cannot forget the identity K6 exists to record. Under `journal@1` they are *not
        written* — a tenant that has not adopted `journal@2` is not affected by its keys (04 §4.1) — which is why an
        existing tenant migrates rather than merely upgrading its store."""
        schema = self._adopted()
        seq, prev = self.head
        if seq == 0 and self._pinned() is None:
            self.db.execute("INSERT INTO meta VALUES ('schema', ?)", (str(schema),))  # the first row pins the genesis
        row: Row = {"seq": seq + 1, "at": at}
        carries = schema >= _CARRIES_IDENTITY
        if carries:
            row["schema"] = schema
        row["caller"] = caller
        if carries and credential is not None:
            row["credential"] = credential
        row["paths"] = list(paths)
        if repairs is not None:
            row["repairs"] = repairs
        row["h"] = chain.link(prev, row)
        trace_id, span_id = trace if (carries and trace is not None) else (None, None)
        self.db.execute(
            "INSERT INTO journal (seq, at, caller, paths, repairs, h, schema, credential, trace_id, span_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                row["seq"],
                at,
                caller,
                json.dumps(row["paths"], sort_keys=True, ensure_ascii=False),
                repairs,
                row["h"],
                row.get("schema"),
                row.get("credential"),
                trace_id,
                span_id,
            ),
        )
        if trace_id is not None:
            row["trace_id"], row["span_id"] = trace_id, span_id
        self.db.executemany(
            "INSERT OR IGNORE INTO journal_paths (seq, path) VALUES (?, ?)", [(row["seq"], p["path"]) for p in paths]
        )
        for path, data in (pending or {}).items():
            self.db.execute("INSERT INTO pending (seq, path, data) VALUES (?, ?, ?)", (row["seq"], path, data))
        return row

    def sign_row(self, seq: int, sig: str) -> None:
        """A repairing row's signature — outside the chain content (9.6)."""
        self.db.execute("UPDATE journal SET sig=? WHERE seq=?", (sig, seq))

    def applied(self, seq: int) -> None:
        self.db.execute("DELETE FROM pending WHERE seq=?", (seq,))

    def applied_through(self, seq: int) -> None:
        """Every pending row up to and including `seq` has reached the remote [K7a, F28].

        The store commits on its own ref in journal order, so a push that lands `HEAD` lands every commit under it —
        including a write whose own push failed earlier and whose row was left pending for the replay. Clearing only
        the row just written left that earlier row pending, and the replay at the next restart wrote its bytes over
        everything that had landed since. One `DELETE … WHERE seq <= ?`, at the one place a push is known to have
        succeeded."""
        self.db.execute("DELETE FROM pending WHERE seq<=?", (seq,))

    def pending_rows(self) -> list[tuple[int, str, bytes]]:
        return [
            (int(s), str(p), bytes(d))
            for s, p, d in self.db.execute("SELECT seq, path, data FROM pending ORDER BY seq")
        ]

    _SELECT: Final = "SELECT seq, at, caller, paths, repairs, h, sig, schema, credential, trace_id, span_id"

    @staticmethod
    def _row(
        seq: int,
        at: str,
        caller: str,
        paths: str,
        repairs: str | None,
        h: str,
        sig: str | None,
        schema: int | None,
        credential: str | None,
        trace_id: str | None,
        span_id: str | None,
    ) -> Row:
        """The row as it was hashed: key presence is the version's, and `h`, `sig` and the trace pointer are
        beside the content (`BESIDE`)."""
        row: Row = {"seq": int(seq), "at": at}
        if schema is not None:
            row["schema"] = int(schema)
        row["caller"] = caller
        if credential is not None:
            row["credential"] = credential
        row["paths"] = json.loads(paths)
        if repairs is not None:
            row["repairs"] = repairs
        row["h"] = h
        if sig is not None:
            row["sig"] = sig
        if trace_id is not None and span_id is not None:
            row["trace_id"], row["span_id"] = trace_id, span_id
        return row

    def rows(self, since_seq: int = 0) -> list[Row]:
        return [
            self._row(*r)
            for r in self.db.execute(f"{self._SELECT} FROM journal WHERE seq > ? ORDER BY seq", (since_seq,))
        ]

    def rows_for(self, path: str, since_seq: int = 0) -> list[Row]:
        """The rows touching `path` (their `paths` filtered to it) — one indexed query, bounded by the path (9.4)."""
        out: list[Row] = []
        for r in self.db.execute(
            "SELECT j.seq, j.at, j.caller, j.paths, j.repairs, j.h, j.sig, j.schema, j.credential, j.trace_id, "
            "j.span_id FROM journal j JOIN journal_paths p ON p.seq = j.seq WHERE p.path = ? AND j.seq > ? "
            "ORDER BY j.seq",
            (path, since_seq),
        ):
            row = self._row(*r)
            out.append({"seq": row["seq"], "paths": [p for p in row["paths"] if p["path"] == path]})
        return out

    def verify(self) -> bool:
        """Recompute the chain from the genesis. Every row is hashed as it was written — its own version's keys —
        from the genesis the chain opened under, so a chain that spans a version bump verifies whole."""
        h = self.genesis
        for r in self.rows():
            if chain.link(h, {k: v for k, v in r.items() if k not in BESIDE}) != r["h"]:
                return False
            h = r["h"]
        return True

    # ---- the blob-sha cache (9.4) and the last-signed blob per path (X1, durable) ---------------------------------

    def cache_get(self, blob: str) -> tuple[str, int, str, str, int] | None:
        r = self.db.execute(
            "SELECT build, head_seq, head_h, ext_hash, canon FROM blobs WHERE blob=?", (blob,)
        ).fetchone()
        return (str(r[0]), int(r[1]), str(r[2]), str(r[3]), int(r[4])) if r else None

    def cache_put(self, blob: str, build: str, head_seq: int, head_h: str, ext_hash: str, canon: int) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO blobs (blob, build, head_seq, head_h, ext_hash, canon) VALUES (?, ?, ?, ?, ?, ?)",
            (blob, build, head_seq, head_h, ext_hash, canon),
        )

    def signed_get(self, path: str) -> tuple[str, int] | None:
        r = self.db.execute("SELECT blob, seq FROM signed WHERE path=?", (path,)).fetchone()
        return (str(r[0]), int(r[1])) if r else None

    def signed_put(self, path: str, blob: str, seq: int) -> None:
        self.db.execute("INSERT OR REPLACE INTO signed (path, blob, seq) VALUES (?, ?, ?)", (path, blob, seq))

    def close(self) -> None:
        self.db.close()
