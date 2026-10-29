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

**Card 19: a second rule rides the same hook, and it is not about paths.** `r-18` and `r-19` both ran the whole test
suite inside the build container, which outlived their tool timeout, kept running in the background, and exhausted
the container's own process table (`signal 6`, `Cannot fork`) before either could write a result — see
`container.PIDS_LIMIT` for the other half of that fix. `whole_suite` reads a `Bash` call's command the way a shell
would split it, and a pytest invocation naming no test file and no test node is blocked here, mechanically, rather
than left to a prompt a crashed run already ignored twice.

**Card 65: a third rule, the sibling of card 19's, and it is read first.** The image now carries the lock's test
environments (`pytest`, `ruff` and `mypy` on PATH, 3.13 at `ISIDIUM_PY313`), so a phase that lacks a tool has
nothing to install: `r-58` ran `python3 -m venv /tmp/v && pip install ruff mypy pytest` and a wheel landed in /work.
`installs` reads a `Bash` call with card 19's own separators and tokens and blocks a segment that installs packages
or makes an environment. It runs before the whole-suite rule because an install line that names pytest
(`pip install pytest`) reads as a whole-suite run too, and read second it would be answered with card 19's reason
instead of the one that says what to do.

Exit code 2 is the block — the PreToolUse contract's "deny and tell the model why", with the reason on stderr.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
from collections.abc import Iterable, Sequence
from pathlib import PurePosixPath
from typing import Any, Final

ALLOW_ENV: Final = "ISIDIUM_GUARD_ALLOW"
BLOCKS_ENV: Final = "ISIDIUM_GUARD_BLOCKS"

BASH: Final = "Bash"

# The tools that write. A tool absent from the allowlist never reaches a hook at all (the harness denies it first),
# so this set is the belt for the ones that are allowed to write *somewhere*.
WRITING_TOOLS: Final[frozenset[str]] = frozenset({"Edit", "Write", "MultiEdit", "NotebookEdit"})
# render.py's PreToolUse matcher: every tool this hook is asked about. Bash rides it for R1's process-limit rule,
# never for the write rule below — `main` still judges a write's target against `WRITING_TOOLS` alone (R3).
HOOKED: Final[frozenset[str]] = WRITING_TOOLS | {BASH}

BLOCK_EXIT: Final = 2

# A shell's own separators between commands, read the same way here so a whole-suite run hidden behind one — `cd x
# && pytest`, r-18's and r-19's own shape — is judged on the segment that actually runs pytest.
_SEPARATORS: Final = re.compile(r"&&|\|\||[;|\n]")
_PYTEST_NAMES: Final[frozenset[str]] = frozenset({"pytest", "py.test"})
# Card 65: what installs packages or makes an environment, as whole tokens (never substrings, so a test path that
# merely contains `install` passes). `pip`, `pip3` and `pip3.N`; the verbs that fetch; the module names after `-m`.
_PIP_NAME: Final = re.compile(r"pip(3(\.\d+)?)?")
_PIP_VERBS: Final[frozenset[str]] = frozenset({"install", "download"})
_UV_VERBS: Final[frozenset[str]] = frozenset({"add", "sync"})
_UV_SUBCOMMANDS: Final[frozenset[str]] = frozenset({"pip", "tool"})
_ENV_MAKERS: Final[frozenset[str]] = frozenset({"venv", "virtualenv"})


def whole_suite(command: str) -> bool:
    """R1: a pytest invocation that names no test file (an argument ending `.py`) and no test node (one carrying
    `::`) is the whole suite, whatever runs beside it on the line. Read per shell segment, so `cd x && pytest` and
    `pytest a || pytest b` are each judged on the segment that actually invokes pytest."""
    return any(_segment_is_whole_suite(seg) for seg in _SEPARATORS.split(command))


def _segment_is_whole_suite(segment: str) -> bool:
    tokens = _tokens(segment)
    return _invokes_pytest(tokens) and not any(t.endswith(".py") or "::" in t for t in tokens)


def installs(command: str) -> bool:
    """Card 65 R3: a shell segment that installs packages or makes an environment — `pip`/`pip3`/`python -m pip`
    with `install` or `download`, `uv pip install`, `uv add`, `uv sync`, `uv tool install`, `python -m venv`,
    `virtualenv` — whatever runs beside it on the line. Read per segment with card 19's `_SEPARATORS` and `_tokens`,
    so `cd x && pip install y` is judged on the segment that installs. This is `r-58`'s shape
    (`python3 -m venv /tmp/v && pip install ruff mypy pytest`, which left a wheel in /work).

    The limit is the whole-suite rule's, because it is the same reading of a shell line: a subshell (`(pip install
    x)`, whose first token is `(pip`), `sh -c "pip install x"` (one token) and `uv --opt value sync` (the first
    non-option token is the option's value) are not read. The run record's scope check still sees what lands in
    the worktree."""
    return any(_segment_installs(seg) for seg in _SEPARATORS.split(command))


def _segment_installs(segment: str) -> bool:
    tokens = _tokens(segment)
    for i, tok in enumerate(tokens):
        name = tok.rsplit("/", 1)[-1]
        rest = tokens[i + 1 :]
        if _PIP_NAME.fullmatch(name) and any(t in _PIP_VERBS for t in rest):
            return True
        if name == "virtualenv" or (tok == "-m" and len(rest) > 0 and rest[0] in _ENV_MAKERS):
            return True
        if name == "uv":
            words = [t for t in rest if not t.startswith("-")]
            if len(words) > 0 and words[0] in _UV_VERBS:
                return True
            if len(words) > 1 and words[0] in _UV_SUBCOMMANDS and words[1] == "install":
                return True
    return False


def _tokens(segment: str) -> list[str]:
    try:
        return shlex.split(segment)
    except ValueError:  # an unbalanced quote: a shell would refuse this too; read it word by word rather than raise
        return segment.split()


def _invokes_pytest(tokens: Sequence[str]) -> bool:
    for i, tok in enumerate(tokens):
        if tok in _PYTEST_NAMES or tok.endswith(("/pytest", "/py.test")):
            return True
        if tok == "-m" and i + 1 < len(tokens) and tokens[i + 1] == "pytest":
            return True
    return False


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


def _bash_command(payload: dict[str, Any]) -> str | None:
    inp = payload.get("tool_input")
    if not isinstance(inp, dict):
        return None
    command = inp.get("command")
    return command if isinstance(command, str) else None


def _is_test_surface(path: str) -> bool:
    p = PurePosixPath(path.replace("\\", "/"))
    return p.name.startswith("test_") or "tests" in p.parts


def _card_tests(allowed: Sequence[str]) -> list[str]:
    """The declared surfaces that are this card's own tests, for the block's reason — a basename starting `test_`,
    or a path with a `tests` segment. Falls back to the whole declared set when nothing matches, so the reason
    never names nothing."""
    matches = sorted(a for a in allowed if _is_test_surface(a))
    return matches or sorted(allowed)


def _whole_suite_reason(spec: dict[str, Any]) -> str:
    tests = _card_tests(spec.get("allow") or [])
    return (
        f"a whole-suite pytest run is not this phase's to make: this phase's own tests are {tests}, and the rest "
        "of the project's gate — the whole suite, mypy, ruff — is green-bar's, checked outside this container on "
        "the pull request. Running the whole suite here is what starved r-18's and r-19's containers (signal 6, "
        "'Cannot fork') before either could write a result. Run the tests this phase names, by file or by node."
    )


def _install_reason() -> str:
    return (
        "this phase installs nothing and makes no environment: the image already carries the tools. `pytest`, `ruff` "
        'and `mypy` are on PATH (Python 3.12, from the lock), and 3.13 is `"$ISIDIUM_PY313/bin/python" -m pytest '
        "<file or node>`. Both environments are the lock's and read-only. A tool you cannot find is a line in your "
        "report, not an install."
    )


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
    if tool == BASH:
        command = _bash_command(payload)
        if command is not None and installs(command):
            reason = _install_reason()
            _record(spec, "", reason)
            print(reason, file=sys.stderr)
            return BLOCK_EXIT
        if command is not None and whole_suite(command):
            reason = _whole_suite_reason(spec)
            _record(spec, "", reason)
            print(reason, file=sys.stderr)
            return BLOCK_EXIT
        return 0
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
