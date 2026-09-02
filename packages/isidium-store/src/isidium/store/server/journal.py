"""The journal (03b §2, 03 §9.6): the store's write-ahead record of every governed transition — one row
`{seq, at, caller, paths: [{path, before_blob?, after_blob?}]}` + `h`, append-only, hash-chained from the genesis
`sha256(b"schema:<n>\\njournal:<tenant>")`; a repairing row carries `repairs = <commit>` inside the content and
`sig = sign(tenant ‖ h_row)` outside. Stored in the store's container, outside any repo — one SQLite file per tenant
(WAL) that also holds the id counter, a path index over the rows (the reconciliation's "one journal query bounded by
the files touched", 9.4), the blob-sha cache (9.4: 0 build hashes on a warm cache), the last-signed blob per path
(the X1 display's baseline, durable across restarts), and the pending-write bytes that let a half-applied write
replay after a crash. One transaction per call: `BEGIN IMMEDIATE` is the tenant's row lock.
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
  repairs TEXT, h TEXT NOT NULL, sig TEXT);
CREATE TABLE IF NOT EXISTS journal_paths (seq INTEGER NOT NULL, path TEXT NOT NULL, PRIMARY KEY (path, seq));
CREATE TABLE IF NOT EXISTS pending (seq INTEGER NOT NULL, path TEXT NOT NULL, data BLOB, PRIMARY KEY (seq, path));
CREATE TABLE IF NOT EXISTS blobs (
  blob TEXT PRIMARY KEY, build TEXT NOT NULL, head_seq INTEGER NOT NULL, head_h TEXT NOT NULL,
  ext_hash TEXT NOT NULL, canon INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS signed (path TEXT PRIMARY KEY, blob TEXT NOT NULL, seq INTEGER NOT NULL);
"""

Row = dict[str, Any]


class Journal:
    def __init__(self, path: str | Path, tenant: str, schema_version: int = 1) -> None:
        self.tenant = tenant
        self.genesis = chain.genesis("journal", tenant, schema_version)
        self.db = sqlite3.connect(str(path), isolation_level=None)  # autocommit; explicit BEGIN below
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        self.db.executescript(SCHEMA_SQL)
        self.db.execute("INSERT OR IGNORE INTO meta VALUES ('tenant', ?)", (tenant,))
        self.db.execute("INSERT OR IGNORE INTO meta VALUES ('counter', '0')")
        got = self.db.execute("SELECT value FROM meta WHERE key='tenant'").fetchone()[0]
        if got != tenant:
            raise ValueError(f"journal belongs to tenant {got!r}, not {tenant!r}")
        self._in_txn = False

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
        repairs: str | None = None,
        pending: dict[str, bytes] | None = None,
    ) -> Row:
        """Append one row inside the caller's transaction; returns the row with `h`. `pending` holds the bytes the
        write is about to put on disk, cleared by `applied()` once the commit lands."""
        seq, prev = self.head
        row: Row = {"seq": seq + 1, "at": at, "caller": caller, "paths": list(paths)}
        if repairs is not None:
            row["repairs"] = repairs
        row["h"] = chain.link(prev, row)
        self.db.execute(
            "INSERT INTO journal (seq, at, caller, paths, repairs, h) VALUES (?, ?, ?, ?, ?, ?)",
            (row["seq"], at, caller, json.dumps(row["paths"], sort_keys=True, ensure_ascii=False), repairs, row["h"]),
        )
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

    def pending_rows(self) -> list[tuple[int, str, bytes]]:
        return [
            (int(s), str(p), bytes(d))
            for s, p, d in self.db.execute("SELECT seq, path, data FROM pending ORDER BY seq")
        ]

    @staticmethod
    def _row(seq: int, at: str, caller: str, paths: str, repairs: str | None, h: str, sig: str | None) -> Row:
        row: Row = {"seq": int(seq), "at": at, "caller": caller, "paths": json.loads(paths)}
        if repairs is not None:
            row["repairs"] = repairs
        row["h"] = h
        if sig is not None:
            row["sig"] = sig
        return row

    def rows(self, since_seq: int = 0) -> list[Row]:
        return [
            self._row(*r)
            for r in self.db.execute(
                "SELECT seq, at, caller, paths, repairs, h, sig FROM journal WHERE seq > ? ORDER BY seq", (since_seq,)
            )
        ]

    def rows_for(self, path: str, since_seq: int = 0) -> list[Row]:
        """The rows touching `path` (their `paths` filtered to it) — one indexed query, bounded by the path (9.4)."""
        out: list[Row] = []
        for r in self.db.execute(
            "SELECT j.seq, j.at, j.caller, j.paths, j.repairs, j.h, j.sig FROM journal j "
            "JOIN journal_paths p ON p.seq = j.seq WHERE p.path = ? AND j.seq > ? ORDER BY j.seq",
            (path, since_seq),
        ):
            row = self._row(*r)
            out.append({"seq": row["seq"], "paths": [p for p in row["paths"] if p["path"] == path]})
        return out

    def verify(self) -> bool:
        """Recompute the chain from the genesis."""
        h = self.genesis
        for r in self.rows():
            if chain.link(h, {k: v for k, v in r.items() if k not in ("h", "sig")}) != r["h"]:
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
