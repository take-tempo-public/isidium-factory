"""9.6 — the per-commit reconciliation, a pure function: for each governed file a commit touches, the journal rows
for that path must form an unbroken chain from the parent's blob to the commit's blob; otherwise
`integrity:unjournaled`. Never "some state seen before": every link must be a row."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, Literal

from .gitrepo import Repo

Verdict = Literal["explained", "unjournaled"]


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
