"""The harness, run inside the container as PID 1 — the Claude Code half of the container adapter [Q-V25, 2026-09-13].

`render.py` turns the policy into what the harness reads; this module is the other direction and the moment between:
it composes the harness's command line **from the job**, runs it as a child it can signal, and turns the harness's own
JSON output into the typed result. It moved here out of `deploy/runner-entrypoint.sh` for two findings of one class
(the chunk plan's V4a-ii section) — a guarantee declared at one moment and never carried to where it acts:

* **The signed model row never reached the harness.** The shell built its argv with no `--model` and no `--effort`,
  and wrote the result's `model` from the job — so `r-2` and `r-3` ran `claude-sonnet-5` and their rows say
  `claude-opus-5`. Here the row is on the argv, and the result's model is **read from what ran** (`modelUsage`), never
  copied from what was asked; the asked model stays on the record through the run's `config_hash`.
* **The watchdog's `TERM` reached nothing.** The shell was PID 1 with the harness a foreground child, and PID 1
  ignores a signal it installed no handler for (measured in the runner image: `running` four seconds after `podman
  kill --signal TERM`). Here the entrypoint `exec`s this module, which installs the handler and forwards the signal.

**Nothing here narrates** (T-B7 (1)): every field of the result comes from the harness's output or from the job.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Final, Protocol

from .adapter import RunJob
from .adapter import job as job_of

HARNESS: Final = "claude-code"
# What the record says when the harness output names no model at all — a phase that failed before its first call. It
# is not a model name, so a result carrying it can never pass for the row the policy signed.
UNMEASURED: Final = "unmeasured"

# The signals a watchdog or an operator sends to stop a phase. Each is forwarded to the harness, which is the process
# doing the work; this process then reports what the harness left and exits.
FORWARDED: Final[tuple[signal.Signals, ...]] = (signal.SIGTERM, signal.SIGINT)


class Process(Protocol):
    """The three things PID 1 asks of the harness it spawned — `subprocess.Popen`'s own, and nothing more."""

    def poll(self) -> int | None: ...
    def send_signal(self, sig: int) -> None: ...
    def wait(self) -> int: ...


Spawn = Callable[..., Process]


def argv(job: RunJob, settings: str) -> list[str]:
    """The harness's command line, from the job alone. `--model` and `--effort` are the agent's row in the tenant's
    signed `[agents]` table — the fact the shell entrypoint never passed. `--max-turns` is the policy's budget; the wall
    clock is the adapter's watchdog outside, because a process cannot be trusted to enforce its own deadline.
    `--settings` carries the permission surface and the PreToolUse guard. Bare mode is never used: it does not read
    `CLAUDE_CODE_OAUTH_TOKEN` (the adapter-auth note, 2026-08-17), which is the billing lane this tenant runs on."""
    spec = job.policy.agent(job.identity.agent)
    return [
        "claude",
        "--print",
        "--settings",
        settings,
        "--max-turns",
        str(job.policy.budgets.max_turns),
        "--output-format",
        "json",
        "--permission-mode",
        "default",
        "--model",
        spec.model,
        "--effort",
        spec.effort,
    ]


def prompt_input(job: RunJob, prompts: Path) -> str:
    """The agent's prompt at the job's own version, verbatim, then the job. There is no instruction composed here: a
    prompt assembled at run time is a prompt no pull request reviewed."""
    prompt = (prompts / job.identity.agent / f"{job.prompt_version}.md").read_text(encoding="utf-8")
    body = json.dumps(job.model_dump(mode="json"), indent=2)
    return f"{prompt}\n\n---\n\n## The job\n\n```json\n{body}\n```\n"


def measured_model(out: Mapping[str, Any]) -> str:
    """The model that did the phase's work, from the harness's own accounting: of the models in `modelUsage`, the one
    that produced the most output. The harness also spends small utility calls on another model (`r-3`: 14 output
    tokens on `claude-haiku-4-5` beside 42,071 on the phase's own) — those are not the phase. Absent any usage, the
    record says so rather than naming the model it was asked for."""
    usage = out.get("modelUsage")
    if not isinstance(usage, Mapping) or not usage:
        return UNMEASURED
    return str(max(usage, key=lambda m: int((usage[m] or {}).get("outputTokens") or 0)))


def report(job: RunJob, out: Mapping[str, Any], ok: bool, harness_version: str) -> dict[str, Any]:
    """The typed result's fields, from the harness's output and the job.

    `tokens` is **input + output** — its definition, written at its writer (Q-V26 (a)); the cached context the harness
    read and wrote is not in it and rides beside it as `cache_read_tokens` and `cache_write_tokens` (`r-3`: 42,147
    against 3,689,226 read from the cache). `effort` is the row's, because the harness reports none: what the record
    holds is what was passed on the argv, which `argv` is tested to carry."""
    usage = out.get("usage") or {}
    return {
        "run_id": job.run_id,
        "phase": job.phase,
        "agent": job.identity.agent,
        "model": measured_model(out),
        "effort": job.policy.agent(job.identity.agent).effort,
        "prompt_version": job.prompt_version,
        "tokens": int(usage.get("input_tokens") or 0) + int(usage.get("output_tokens") or 0),
        "cache_read_tokens": int(usage.get("cache_read_input_tokens") or 0),
        "cache_write_tokens": int(usage.get("cache_creation_input_tokens") or 0),
        "cost_micro": round(float(out.get("total_cost_usd") or 0.0) * 1_000_000),
        "duration_ms": int(out.get("duration_ms") or 0),
        "outcome": "ok" if ok and not out.get("is_error") else "failed:infra",
        "harness": HARNESS,
        "harness_version": harness_version,
        "billing_class": "plan",
    }


class Forward:
    """The handler PID 1 installs: the signal goes to the harness, and this process keeps running long enough to write
    what the harness left behind. Without it the signal is ignored outright — PID 1 has no default disposition.

    It is installed **before** the harness is spawned, so no window exists in which a stop is ignored: a signal that
    arrives first is remembered, and the harness is then never started."""

    def __init__(self) -> None:
        self.child: Process | None = None
        self.stopped: int | None = None

    def __call__(self, signum: int, frame: Any) -> None:
        del frame
        self.stopped = signum
        if self.child is not None and self.child.poll() is None:
            self.child.send_signal(signum)


def run(
    job: RunJob,
    rundir: Path,
    prompts: Path,
    *,
    harness_version: str,
    spawn: Spawn = subprocess.Popen,
    install: Callable[[int, Callable[[int, Any], None]], Any] = signal.signal,
) -> int:
    """One phase: the harness spawned once with the job on stdin, the signals forwarded while it runs, the result
    written from its output. Exit 0 for `ok`, 1 otherwise — the adapter reads the run directory either way."""
    (rundir / "input.md").write_text(prompt_input(job, prompts), encoding="utf-8")
    out_path, err_path = rundir / "harness.json", rundir / "harness.err"
    forward = Forward()
    for sig in FORWARDED:
        install(sig, forward)
    code = 1
    with (rundir / "input.md").open("rb") as stdin, out_path.open("wb") as stdout, err_path.open("wb") as stderr:
        if forward.stopped is None:
            child = spawn(argv(job, str(rundir / "settings.json")), stdin=stdin, stdout=stdout, stderr=stderr)
            forward.child = child
            code = child.wait()
    try:
        out: Any = json.loads(out_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        out = {}
    if not isinstance(out, dict):
        out = {}
    result = report(job, out, code == 0, harness_version)
    (rundir / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    if result["outcome"] == "ok":
        return 0
    # The provider's own sentence goes to stderr as well as into the run directory. Found live 2026-09-12: the harness
    # writes its errors inside the container, so podman relayed an empty stream and the adapter could only say "exit 1"
    # about a run whose reason ("401 Invalid bearer token") was sitting in a file. Say it where the operator looks.
    why = out.get("result") or out.get("error") or "the harness failed and said nothing"
    status = out.get("api_error_status")
    print(f"isidium-runner: {why}" + (f" (status {status})" if status else ""), file=sys.stderr)
    return 1


def main() -> int:
    """The container's entry, after the shell's checks: the job from `ISIDIUM_JOB`, the run directory it sits in, the
    prompts baked into the image. A missing input is exit 2 with its name — the shell's own convention."""
    missing = [k for k in ("ISIDIUM_JOB", "ISIDIUM_PROMPTS", "ISIDIUM_HARNESS_VERSION") if not os.environ.get(k)]
    if missing:
        print(f"isidium-runner: set {', '.join(missing)}", file=sys.stderr)
        return 2
    path = Path(os.environ["ISIDIUM_JOB"])
    job = job_of(json.loads(path.read_text(encoding="utf-8")))
    return run(
        job,
        path.parent,
        Path(os.environ["ISIDIUM_PROMPTS"]),
        harness_version=os.environ["ISIDIUM_HARNESS_VERSION"],
    )


if __name__ == "__main__":  # pragma: no cover - the container's entry, exercised through `run` in tests
    raise SystemExit(main())
