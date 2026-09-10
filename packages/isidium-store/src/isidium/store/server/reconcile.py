"""9.5 / 9.6 — the per-commit reconciliation and the integrity reasons, as pure functions.

**9.6, the chain** (V6): for each governed file a commit touches, the journal rows for that path must form an unbroken
chain from the parent's blob to the commit's blob; otherwise `integrity:unjournaled`. Never "some state seen before":
every link must be a row.

**9.5, the reasons** [L4, 2026-09-09]: per (commit, path) the six of 1.15 from the same inputs — `unjournaled` (the
chain), `tampered` (the recompute through the one derive function `write` ran, refusals included — 1.15: *"CI and
ingest run the same derive function"*), `rewritten` (an entry at or below the landed `history_head` that is not the
one landed), `unverified` (a signed entry whose signature does not verify — *"each carrying whether its `sig`
verified"*, expressed as the reason), `attribution` (the entry's `by` against the commit's author email and its
`Co-Authored-By` trailers — the one reason only a walk over commits can compute) and `time` (an entry stamped later
than the commit that carries it, beyond `time_skew`). `check` runs it per card since the cursor; `land` runs it over
every governed path in `(last cursor, head]` — one function, two callers, so the two can never disagree.
"""

from __future__ import annotations

import datetime as _dt
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from ..core import canon, chain, derive
from ..core.grammar import Document
from ..core.refusal import Refusal
from .gitrepo import CommitChange, Repo

Verdict = Literal["explained", "unjournaled"]
Reason = Literal["tampered", "unjournaled", "rewritten", "unverified", "attribution", "time"]


def reconcile_path(parent_blob: str | None, commit_blob: str | None, rows: Sequence[dict[str, Any]]) -> Verdict:
    """`explained` iff the rows (in seq order) chain parent_blob → … → commit_blob."""
    steps = [
        (p.get("before_blob"), p.get("after_blob")) for r in sorted(rows, key=lambda r: r["seq"]) for p in r["paths"]
    ]
    cur = parent_blob
    if cur == commit_blob:
        return "explained"
    for b, a in steps:
        if b == cur:
            cur = a
            if cur == commit_blob:
                return "explained"
    return "unjournaled"


def reconcile_commit(
    repo: Repo, sha: str, rows_for: Callable[[str], Sequence[dict[str, Any]]], is_governed: Callable[[str], bool]
) -> dict[str, Verdict]:
    out: dict[str, Verdict] = {}
    for path, (pb, cb) in repo.touched(sha).items():
        if is_governed(path):
            out[path] = reconcile_path(pb, cb, rows_for(path))
    return out


def reconcile_range(
    repo: Repo,
    cursor: str | None,
    rows_for: Callable[[str], Sequence[dict[str, Any]]],
    is_governed: Callable[[str], bool],
    head: str | None = None,
) -> dict[str, dict[str, Verdict]]:
    """Every commit on the ratification path from the last landed cursor to head, first-parent on merges."""
    return {sha: reconcile_commit(repo, sha, rows_for, is_governed) for sha in repo.first_parent_walk(cursor, head)}


@dataclass(frozen=True)
class Context:
    """What the reason function needs beside the two documents — the store's, handed in so the function stays pure:
    the gated `x` keys the build hash covers, the signature-and-binding verifier, the tenant's `time_skew`."""

    gated_x: frozenset[str]
    verify: Callable[[Mapping[str, Any]], bool]
    time_skew: int


def _epoch(at: str) -> int:
    return int(_dt.datetime.fromisoformat(at).timestamp())


def reasons(
    before: Document | None,
    after: Document | None,
    parent_blob: str | None,
    commit_blob: str | None,
    rows: Sequence[dict[str, Any]],
    ctx: Context,
    *,
    landed_head: Mapping[str, Any] | None = None,
    commit: CommitChange | None = None,
) -> set[Reason]:
    """The integrity reasons one (commit, card path) transition earns (1.15), from the parsed documents on either
    side of it, the journal rows for the path, the sidecar's `history_head` for the card when one has landed, and
    the commit's author, trailers and time when the caller walked commits (`check`'s per-card walk and `land`'s range
    walk both do; a caller without them gets the four document-and-journal reasons).

    A deletion is a diff `write` refuses (`write.deletion`), so it is `tampered` through the same derive (round 6:
    *"a deleted card is not a fact of its own"*) beside the chain's `unjournaled`. A `repaired` entry is the owner's
    signed act and is not re-derived (1.15)."""
    out: set[Reason] = set()
    if reconcile_path(parent_blob, commit_blob, rows) != "explained":
        out.add("unjournaled")
    if after is None:
        if before is not None:
            try:
                derive.derive(before, None, None)
            except Refusal:
                out.add("tampered")
        return out
    if landed_head is not None:
        # An entry the sidecar landed must still be the entry at its seq. A commit OLDER than the landed head has
        # fewer entries and is not a rewrite — the range walks every commit since the cursor, and the cursor stays
        # behind the head for as long as nothing merges [L4 live finding, tenant #0, 2026-09-10: card 0004's draft
        # commit read `rewritten` against the head its close had landed]. A history cut short at the head is the
        # entry-count rule's (`tampered`, below) and `check`'s own comparison on the working bytes.
        seq = int(landed_head["seq"])
        if seq <= len(after.history) and after.history[seq - 1]["h"] != landed_head["h"]:
            out.add("rewritten")
    if len(after.history) != (len(before.history) if before else 0) + 1 or (
        before is not None and after.history[:-1] != before.history
    ):
        out.add("tampered")  # a commit carries exactly one entry per card (1.15, W2); anything else is a rewrite
        return out
    e = after.history[-1]
    if chain.is_signed(e) and not ctx.verify(e):
        out.add("unverified")
    if commit is not None:
        by = str(e.get("by", "")).lower()
        if by and by != commit.author and by not in commit.coauthors:
            out.add("attribution")
        if _epoch(str(e["at"])) > _epoch(commit.at) + ctx.time_skew:
            out.add("time")
    if e.get("act") == "repaired":
        return out
    try:
        d = derive.derive(before, after, e.get("ref"))
    except Refusal:
        out.add("tampered")
        return out
    build = (
        str(before.history[-1]["build"])
        if (before is not None and not (set(d.diff) & canon.GATED_KEYS))
        else canon.build_hash(after.head, after.scope(), ctx.gated_x)
    )
    if (d.act, d.fields, build) != (e["act"], e["fields"], e["build"]):
        out.add("tampered")
    return out
