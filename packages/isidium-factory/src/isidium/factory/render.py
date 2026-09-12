"""The executor policy, rendered into what a harness speaks [V4a-i, 2026-09-12].

7bdb.4(2), verbatim: *"Executor policy declared once, rendered per adapter: tool allowlist, write-guard paths,
budgets/watchdog, model + effort per phase live in factory config; the Claude Code adapter renders them as
`settings` + a `PreToolUse` hook, the pi adapter as a factory-owned pi extension package — **neither harness's
native form is ever the source**"*.

This module is the rendering half, and it has its own file because **two adapters speak Claude Code** — the
container adapter here and the action adapter of V4b — while the seam itself (`adapter.py`) must name no harness at
all. A pi renderer joins this file when the swap trigger fires; the policy it reads does not change.

The hook is not generated text. It is `python -m isidium.factory.guard`, one implementation, run inside whatever
the harness is — because a guard whose rendered copy could differ from the predicate the wrapper checks against is
not a guard (see `guard.py`).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

from .adapter import ExecutorPolicy, RunJob
from .guard import ALLOW_ENV, BLOCKS_ENV, WRITING_TOOLS

# Where the run's mounts land inside the container. The adapter binds to these; the rendered settings name them.
WORK: Final = "/work"
RUN: Final = "/run"
ALLOW_FILE: Final = f"{RUN}/allow.json"
BLOCKS_FILE: Final = f"{RUN}/blocks.jsonl"
JOB_FILE: Final = f"{RUN}/job.json"
RESULT_FILE: Final = f"{RUN}/result.json"

GUARD_COMMAND: Final = "python -m isidium.factory.guard"
MATCHER: Final = "|".join(sorted(WRITING_TOOLS))


def settings(policy: ExecutorPolicy) -> dict[str, Any]:
    """The harness's settings: the allowlist as the permission surface, and the guard as a PreToolUse hook.

    `deny` carries nothing: everything absent from `allow` is already denied by construction, and a deny list beside
    a closed allow list is a second home for the same fact. A policy whose `guard` is `post-hoc` renders **no hook**
    — that is what declared degradation means, and the capability row says so out loud rather than the settings
    quietly omitting it."""
    out: dict[str, Any] = {"permissions": {"allow": list(policy.allowlist)}}
    if policy.guard == "write-time":
        out["hooks"] = {"PreToolUse": [{"matcher": MATCHER, "hooks": [{"type": "command", "command": GUARD_COMMAND}]}]}
    return out


def allow_spec(job: RunJob) -> dict[str, Any]:
    """What the guard reads: the run's declared surfaces, and the root they are relative to inside the container."""
    return {"root": WORK, "allow": list(job.allowed_writes), "blocks": BLOCKS_FILE}


def environment(policy: ExecutorPolicy) -> dict[str, str]:
    """The non-secret environment the phase runs under. The model credential is **not** here: it reaches the child
    through the adapter's own environment by name, never through a rendered file (V2's rule for the forge token,
    applied to this one)."""
    env = {
        ALLOW_ENV: ALLOW_FILE,
        BLOCKS_ENV: BLOCKS_FILE,
        "ISIDIUM_JOB": JOB_FILE,
        "ISIDIUM_RESULT": RESULT_FILE,
        "ISIDIUM_MAX_TURNS": str(policy.budgets.max_turns),
    }
    if policy.budgets.max_tokens is not None:
        env["ISIDIUM_MAX_TOKENS"] = str(policy.budgets.max_tokens)
    return env


def write_run_dir(directory: Path, job: RunJob) -> None:
    """The three files a run hands its container: the job, the guard's allowed set, and an empty block log — so the
    count the adapter reads back is a count of writes denied, never a missing file read as zero."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "job.json").write_text(json.dumps(job.model_dump(mode="json"), indent=2), encoding="utf-8")
    (directory / "allow.json").write_text(json.dumps(allow_spec(job), indent=2), encoding="utf-8")
    (directory / "settings.json").write_text(json.dumps(settings(job.policy), indent=2), encoding="utf-8")
    (directory / "blocks.jsonl").write_text("", encoding="utf-8")


def count_blocks(lines: Sequence[str]) -> int:
    """`PhaseResult.guard_blocks`, counted from the guard's own log by the wrapper — the phase does not report its
    own score."""
    return sum(1 for ln in lines if ln.strip())
