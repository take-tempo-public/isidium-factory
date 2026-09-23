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
import re
import shutil
import signal
import subprocess
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, Final, Protocol

from pydantic import ValidationError

from . import artifacts
from .adapter import RunJob
from .adapter import job as job_of

HARNESS: Final = "claude-code"
# What the record says when the harness output names no model at all — a phase that failed before its first call. It
# is not a model name, so a result carrying it can never pass for the row the policy signed.
UNMEASURED: Final = "unmeasured"

# The harness's own name for an end on a budget the policy set, as the outcome the record gives it. Measured live on
# `r-4` (2026-09-14): `"subtype": "error_max_turns"`, `"errors": ["Reached maximum number of turns (40)"]`. T-A7 routes
# `budget` to the design queue, never to a retry — the same turns would be spent again.
BUDGET_ENDS: Final[frozenset[str]] = frozenset({"error_max_turns"})
# T-B4 (1)'s end for a plan-gate call that answered with no conforming artifact — the plan, the refutation and the
# verdict alike [owner, 2026-09-23]. Never retried by the adapter: the harness already re-asked inside the call.
MALFORMED: Final = "failed:malformed-plan"

# A core dump the harness left in its working directory — the phase's worktree. Measured on `r-5` (2026-09-15): the
# runner VM's `core_pattern` is `core` with the pid appended, and `core.2` (the harness, PID 2) sat among the card's
# files. Only the `core.<pid>` form is moved: a repository may hold a file called `core`.
CORE: Final = re.compile(r"core\.\d+")

# The usage counts the streamed messages carry, summed when the harness dies before its result line.
USAGE_KEYS: Final[tuple[str, ...]] = (
    "input_tokens",
    "output_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
)

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
    # A phase that answers with an artifact is handed its schema: the harness validates the answer and re-asks the model
    # inside the call when it does not conform (measured 2026-09-23) — T-B4 (1)'s one retry [owner, 2026-09-23].
    shaped = artifacts.OF_PHASE.get(job.phase)
    structured = ["--json-schema", json.dumps(artifacts.schema(shaped[1]), sort_keys=True)] if shaped else []
    return [
        "claude",
        "--print",
        "--settings",
        settings,
        "--max-turns",
        str(job.policy.budgets.max_turns),
        # Streamed, not one JSON document at the end: `r-5`'s harness crashed twice and `json` had written nothing, so
        # thirty minutes of work were recorded as 0 tokens. Each message now carries its usage as it happens, and the
        # last line is the same result object `json` gave. `--print` streams only with `--verbose` (the CLI's help).
        "--output-format",
        "stream-json",
        "--verbose",
        "--permission-mode",
        "default",
        "--model",
        spec.model,
        "--effort",
        spec.effort,
        *structured,
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
        "outcome": outcome_of(out, ok),
        "harness": HARNESS,
        "harness_version": harness_version,
        "billing_class": "plan",
    }


def harvest(job: RunJob, out: Mapping[str, Any], rundir: Path) -> tuple[str | None, list[dict[str, str]]]:
    """A structured phase's artifact, from the harness's `structured_output`: validated by the artifact's own model,
    written to `<name>.json` as canonical bytes, and named by hash — or the outcome that says there is none.

    **A null `structured_output` is malformed, not `ok`.** Measured 2026-09-23: a model that never satisfied the
    schema ends the call `subtype: success`, `is_error: false`, exit 0, with `structured_output: null` and its
    explanation in `result` — so `outcome_of` alone would record it as a success. `path` is relative to the run
    directory; the adapter makes it relative to the deploy home, where the wrapper reads it."""
    shaped = artifacts.OF_PHASE.get(job.phase)
    if shaped is None:
        return None, []
    name, model = shaped
    try:
        value = model.model_validate(out.get("structured_output")).model_dump(mode="json")
    except ValidationError:
        return MALFORMED, []
    data = artifacts.canonical(value)
    (rundir / f"{name}.json").write_bytes(data)
    return None, [{"name": name, "sha256": artifacts.sha256(data), "path": f"{name}.json"}]


def outcome_of(out: Mapping[str, Any], ok: bool) -> str:
    """How the phase ended, in the record's closed set. A budget end is `failed:budget` whatever the exit code; any
    other error, or a non-zero exit, is `failed:infra` — T-A7's one class the adapter retries."""
    if out.get("subtype") in BUDGET_ENDS:
        return "failed:budget"
    return "ok" if ok and not out.get("is_error") else "failed:infra"


def stream_out(lines: Iterable[str], code: int | None, cores: Sequence[str] = ()) -> dict[str, Any]:
    """The harness's answer, from its stream. The `result` line when there is one — the object `--output-format json`
    gave. When the harness died first, what the stream proves instead: the usage of every message it finished
    (counted once each — a message is streamed once per content block, with the same usage on every line, measured
    2026-09-15), the models that produced it, and a sentence naming how the process ended. Either way the exit status
    rides along, and a core dump kept beside the run is named."""
    result: dict[str, Any] | None = None
    messages: dict[str, Mapping[str, Any]] = {}
    for line in lines:
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if not isinstance(d, dict):
            continue
        if d.get("type") == "result":
            result = d
        elif d.get("type") == "assistant" and isinstance(d.get("message"), dict):
            m = d["message"]
            messages[str(m.get("id") or d.get("request_id") or len(messages))] = m
    if result is not None:
        out = dict(result)
    else:
        usage = {k: sum(int((m.get("usage") or {}).get(k) or 0) for m in messages.values()) for k in USAGE_KEYS}
        by_model: dict[str, int] = {}
        for m in messages.values():
            name = str(m.get("model") or UNMEASURED)
            by_model[name] = by_model.get(name, 0) + int((m.get("usage") or {}).get("output_tokens") or 0)
        out = {
            "is_error": True,
            "usage": usage,
            "modelUsage": {k: {"outputTokens": v} for k, v in by_model.items()},
            "errors": [f"the harness {_ended(code)} and wrote no result"],
        }
    if cores:
        out["errors"] = [*(out.get("errors") or []), "a core dump is kept in the run directory: " + ", ".join(cores)]
    out["exit_status"] = code
    return out


def _ended(code: int | None) -> str:
    if code is None:
        return "was never started (a stop arrived first)"
    return f"exited on signal {-code}" if code < 0 else f"exited with status {code}"


def keep_cores(work: Path, rundir: Path) -> list[str]:
    """Core dumps moved out of the worktree into the run directory: evidence of the crash, and never a file the phase
    touched (on `r-5` `core.2` was in the touched set beside the card's surfaces)."""
    kept: list[str] = []
    for p in sorted(work.iterdir()):
        if p.is_file() and CORE.fullmatch(p.name):
            shutil.move(str(p), str(rundir / p.name))  # across mounts: `/work` and `/run` are two volumes
            kept.append(p.name)
    return kept


def reason_of(out: Mapping[str, Any]) -> str:
    """The harness's own sentence for why it stopped. It writes the provider's answer to `result` and its own limits to
    `errors[]` — `r-4` stopped with `errors: ["Reached maximum number of turns (40)"]` and no `result`, and the operator
    was told *"the harness failed and said nothing"* while the sentence sat in the file."""
    errors = out.get("errors")
    listed = "; ".join(str(e) for e in errors if e) if isinstance(errors, list) else ""
    return str(out.get("result") or out.get("error") or listed or "the harness failed and said nothing")


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
    work: Path | None = None,
) -> int:
    """One phase: the harness spawned once with the job on stdin, the signals forwarded while it runs, the result
    written from its output. Exit 0 for `ok`, 1 otherwise — the adapter reads the run directory either way.

    The raw stream is kept as `harness.jsonl`; `harness.json` is the answer read from it, so what the adapter reads is
    one object whether the harness finished or died."""
    (rundir / "input.md").write_text(prompt_input(job, prompts), encoding="utf-8")
    stream_path, err_path = rundir / "harness.jsonl", rundir / "harness.err"
    forward = Forward()
    for sig in FORWARDED:
        install(sig, forward)
    code: int | None = None
    with (rundir / "input.md").open("rb") as stdin, stream_path.open("wb") as stdout, err_path.open("wb") as stderr:
        if forward.stopped is None:
            child = spawn(argv(job, str(rundir / "settings.json")), stdin=stdin, stdout=stdout, stderr=stderr)
            forward.child = child
            code = child.wait()
    cores = keep_cores(work or Path.cwd(), rundir)
    try:
        lines = stream_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    out = stream_out(lines, code, cores)
    (rundir / "harness.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    result = report(job, out, code == 0, harness_version)
    if result["outcome"] == "ok":
        malformed, made = harvest(job, out, rundir)
        result["outcome"] = malformed or "ok"
        result["artifacts"] = made
    (rundir / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    if result["outcome"] == "ok":
        return 0
    # The provider's own sentence goes to stderr as well as into the run directory. Found live 2026-09-12: the harness
    # writes its errors inside the container, so podman relayed an empty stream and the adapter could only say "exit 1"
    # about a run whose reason ("401 Invalid bearer token") was sitting in a file. Say it where the operator looks.
    why = reason_of(out)
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
