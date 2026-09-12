"""The write guard (T-B5 (1)) — the predicate, and the hook that runs it at write time [V4a-i, 2026-09-12].

T-B5's first matching condition, verbatim: *"Writes only within the plan's touched surfaces ∪ test paths — enforced
**at write time** by a guard in the worktree (PreToolUse-class), not after"*. This module is both halves of that,
deliberately in one file: the predicate the wrapper uses to recompute and judge what a phase actually wrote, and the
entrypoint the harness calls before each write. One rule, one home — a guard whose in-container half and
out-of-container half could disagree is not a guard.

It runs **inside** the run container, where the factory package is installed, as
`python -m isidium.factory.guard`; the allowed set reaches it as a file named by `ISIDIUM_GUARD_ALLOW`, never as an
argument (an argument list is readable by anything in the container, and the set is per-run). Every denial appends
one JSON line to `ISIDIUM_GUARD_BLOCKS`, which is how `PhaseResult.guard_blocks` is counted from outside: the guard
does not report its own score.

Exit code 2 is the block — the PreToolUse contract's "deny and tell the model why", with the reason on stderr.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterable, Sequence
from pathlib import PurePosixPath
from typing import Any, Final

ALLOW_ENV: Final = "ISIDIUM_GUARD_ALLOW"
BLOCKS_ENV: Final = "ISIDIUM_GUARD_BLOCKS"

# The tools that write. A tool absent from the allowlist never reaches a hook at all (the harness denies it first),
# so this set is the belt for the ones that are allowed to write *somewhere*.
WRITING_TOOLS: Final[frozenset[str]] = frozenset({"Edit", "Write", "MultiEdit", "NotebookEdit"})

BLOCK_EXIT: Final = 2


def normalize(path: str, root: str) -> str | None:
    """A write target as a repo-relative POSIX path, or `None` when it is not inside the worktree at all.

    Absolute paths outside the root, and anything that climbs out with `..`, answer `None` — which the caller reads
    as "not allowed", because a path that is not in the worktree is not in `surfaces` either."""
    p = PurePosixPath(path.replace("\\", "/"))
    r = PurePosixPath(root.replace("\\", "/"))
    if p.is_absolute():
        try:
            p = p.relative_to(r)
        except ValueError:
            return None
    parts: list[str] = []
    for seg in p.parts:
        if seg in ("", "."):
            continue
        if seg == "..":
            if not parts:
                return None
            parts.pop()
            continue
        parts.append(seg)
    return "/".join(parts) if parts else None


def allows(path: str, allowed: Sequence[str], root: str = "") -> bool:
    """The rule: a write is allowed when its repo-relative path **is** one of the declared paths, or lies under one
    declared as a directory (a trailing `/`).

    A bare prefix match is not the rule and the distinction is the point: `surfaces = ["src/a.py"]` must not admit
    `src/a.py.bak`, and `["tests/"]` must not admit `tests-scratch/`. The card declares what it writes; the guard
    reads it literally."""
    rel = normalize(path, root)
    if rel is None:
        return False
    for entry in allowed:
        want = entry.replace("\\", "/").lstrip("./")
        if not want:
            continue
        if want.endswith("/"):
            if rel.startswith(want):
                return True
        elif rel == want or rel.startswith(want + "/"):
            return True
    return False


def outside(paths: Iterable[str], allowed: Sequence[str], root: str = "") -> tuple[str, ...]:
    """The paths a set holds that the declared surfaces do not — the wrapper's recompute check, and the reason a
    result whose claimed set differs from git's is refused before anything judges `surfaces`."""
    return tuple(sorted({p for p in paths if not allows(p, allowed, root)}))


def _target(payload: dict[str, Any]) -> str | None:
    inp = payload.get("tool_input")
    if not isinstance(inp, dict):
        return None
    for key in ("file_path", "notebook_path", "path"):
        v = inp.get(key)
        if isinstance(v, str) and v:
            return v
    return None


def main(argv: Sequence[str] | None = None) -> int:
    """The hook. Reads the PreToolUse payload on stdin; blocks with exit 2 and a reason the model can act on."""
    del argv
    allow_file = os.environ.get(ALLOW_ENV)
    if not allow_file:
        print(f"the write guard is not configured ({ALLOW_ENV} unset): refusing every write", file=sys.stderr)
        return BLOCK_EXIT
    try:
        with open(allow_file, encoding="utf-8") as fh:
            spec = json.loads(fh.read())
        payload = json.loads(sys.stdin.read() or "{}")
    except (OSError, ValueError) as e:
        print(f"the write guard could not read its inputs: {e}", file=sys.stderr)
        return BLOCK_EXIT

    tool = payload.get("tool_name")
    if isinstance(tool, str) and tool not in WRITING_TOOLS:
        return 0
    target = _target(payload)
    if target is None:
        print("the write guard could not find the write's target in the tool call: refusing", file=sys.stderr)
        _record(spec, "", "no target path in the tool call")
        return BLOCK_EXIT

    allowed = spec.get("allow") or []
    root = spec.get("root") or ""
    if allows(target, allowed, root):
        return 0
    reason = (
        f"{target} is outside this card's declared surfaces. The card says what it writes: {sorted(allowed)}. "
        "Widening the card is a question for the owner, not a write."
    )
    _record(spec, target, reason)
    print(reason, file=sys.stderr)
    return BLOCK_EXIT


def _record(spec: dict[str, Any], target: str, reason: str) -> None:
    """One line per block, appended — the count is read from outside, so a phase cannot under-report its own."""
    path = os.environ.get(BLOCKS_ENV) or spec.get("blocks")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"path": target, "reason": reason}, ensure_ascii=False) + "\n")
    except OSError:  # a guard that cannot write its own log still blocks the write
        pass


if __name__ == "__main__":  # pragma: no cover - the container's entry, exercised through `main` in tests
    raise SystemExit(main())
