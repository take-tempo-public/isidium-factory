"""The container adapter — a run phase inside a podman container on the workstation [V4a-i, Q-V2 (c) first half].

T-C6's declared characteristics for this one, verbatim: *"headless CLI-in-container: full control of hooks, guard,
identity, worktrees; self-hosted compute; forge-agnostic; the natural home for agent-station."* Q-V15 [owner,
2026-09-12]: the factory itself stays the workstation process for this chunk and spawns the run container; Q-V3's
factory-container-beside-the-store stands and is honoured in a later chunk, with the podman socket its own question.

**The contract with the image is two files, not a command line.** The adapter mounts a run directory holding
`job.json` (the typed job), `allow.json` (the guard's set) and `settings.json` (the rendered policy), and the image
answers with `result.json`. What the image does between them — which harness, which flags — is the image's, which
is the only reason the seam above stays free of harness words.

**One spawn per phase**, never per tool call: the container is started once, does the phase, and exits. The
watchdog is the policy's wall clock; expiry and a start failure are both T-C6's *"Adapter start/timeouts ⇒
`failed:infra`, one retry"*. A rate limit is not that — the auth note's line holds: *"the picker treats a limit
response as `environment` (back off, do not burn retries — a rate-limit hit is not `infra` to retry once)"*.

The model credential reaches the child **by name through the environment** (`--env CLAUDE_CODE_OAUTH_TOKEN`, no
value in `argv`), read from `claude.token` at the deploy home — Q-V10's shape for the forge token, and Q-V17's
ruling for this one: the subscription lane, `billing_class = plan`.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Final

from isidium.store.core.refusal import Refusal

from . import render
from .adapter import AdapterCapabilities, PhaseResult, RunJob, result
from .tenant import Registration

NAME: Final = "container"
HARNESS: Final = "claude-code"
TOKEN_FILE: Final = "claude.token"
PODMAN: Final = "podman"

# Literal at every raise, never a constant: the sweep that classifies every rule namespace reads the literal
# at the raise site (C-12) and cannot follow a name. Found building V4a-i — see adapter.py.

# T-C6's *"one retry"*, named where it bites (C-10): the start and the watchdog each get one second attempt and no
# more, because a phase that died twice is an environment to fix, not a thing to keep paying a model to re-attempt.
ATTEMPTS: Final = 2

# The provider's own words for "you are out of window". A limit is `environment`: the run backs off and the picker
# does not burn its one retry on it (the adapter-auth note, 2026-08-17).
RATE_LIMIT_MARKERS: Final[tuple[str, ...]] = ("rate limit", "rate_limit", "429", "usage limit")

Runner = Callable[..., "subprocess.CompletedProcess[str]"]


class Container:
    """The adapter. Constructed from the tenant's deploy home and its registration — `resolve` hands it nothing
    else, so which adapter a tenant runs really is the registration's answer and nothing else's (R1)."""

    def __init__(self, home: Path, reg: Registration, *, run: Runner | None = None, podman: str = PODMAN) -> None:
        self._home = home
        self._reg = reg
        self._run: Runner = run or subprocess.run
        self._podman = podman

    def capabilities(self) -> AdapterCapabilities:
        """Declared, not probed — and checked against behaviour by the conformance suite, which is the only thing
        that makes a declaration worth reading (05 §3).

        **`harness_version` is the image reference, and that is the honest answer here.** The first draft read
        `ISIDIUM_HARNESS_VERSION` from *this* process's environment — the factory's, on the workstation — which is
        not where the harness is: the version is a fact about the image, and the image is the other side of a
        container boundary this method must not cross to answer a declaration. So the matrix declares **which image
        runs**, and the concrete version comes back on the `PhaseResult` from inside it, where it is true. Found
        live 2026-09-12, when the matrix said `unknown` beside a run that knew exactly which harness it ran."""
        return AdapterCapabilities(
            name=NAME,
            harness=HARNESS,
            harness_version=self._reg.runner_image or "no image declared",
            write_guard_at_write_time=True,
            identity_held_by_wrapper=True,
            budgets=True,
            watchdog=True,
            end_and_resume=True,
            telemetry_per_phase=True,
            billing_class="plan",
            hosts=("api.anthropic.com",),
        )

    def execute(self, job: RunJob) -> PhaseResult:
        rundir = self._home / "runs" / job.run_id / job.phase
        render.write_run_dir(rundir, job)
        token = self._token()
        argv = self._argv(job, rundir)
        env = {**os.environ, "CLAUDE_CODE_OAUTH_TOKEN": token}

        last = ""
        for _ in range(ATTEMPTS):
            try:
                proc = self._run(
                    argv,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=job.policy.budgets.wall_clock_s,
                    env=env,
                )
            except subprocess.TimeoutExpired:
                self._kill(job)
                last = f"the watchdog fired at {job.policy.budgets.wall_clock_s}s"
                continue
            except OSError as e:  # podman itself is not there, or cannot start
                last = str(e)
                continue
            if proc.returncode == 0:
                return self._result(job, rundir)
            detail = (proc.stderr or proc.stdout or "").strip()
            if _rate_limited(detail):
                why = f"the provider answered a limit, not a failure: {detail[:200]}"
                raise Refusal("adapter.environment", job.run_id, why)
            last = detail or f"exit {proc.returncode}"
        raise Refusal("adapter.infra", job.run_id, f"{ATTEMPTS} attempts, the last: {last[:400]}")

    # ---------------------------------------------------------------------------------------------- the mechanics

    def _argv(self, job: RunJob, rundir: Path) -> list[str]:
        """The one spawn. `--rm` because the record is the ledger's and never the container's; `--network` is left
        to the host's default because the phase must reach the provider — the egress allowlist is agent-station's
        by pointer and `capabilities().hosts` is what this adapter declares it needs."""
        image = self._reg.runner_image
        if not image:
            raise Refusal(
                "adapter.no-image",
                str(self._home / "tenant.toml"),
                "no [runner].image: this tenant names the container adapter but declares no image to run it in",
            )
        argv = [
            self._podman,
            "run",
            "--rm",
            "--name",
            _name(job),
            "--volume",
            f"{job.worktree}:{render.WORK}:rw",
            "--volume",
            f"{rundir}:{render.RUN}:rw",
            "--workdir",
            render.WORK,
            "--env",
            "CLAUDE_CODE_OAUTH_TOKEN",  # by name: the value never enters `argv`
        ]
        for k, v in render.environment(job.policy).items():
            argv += ["--env", f"{k}={v}"]
        argv.append(image)
        return argv

    def _kill(self, job: RunJob) -> None:
        """The watchdog's hand. The image's entrypoint `exec`s its process as PID 1 (K6b's lesson), so a TERM to the
        container reaches the thing that is actually running."""
        self._run(
            [self._podman, "kill", "--signal", "TERM", _name(job)],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )

    def _token(self) -> str:
        path = self._home / TOKEN_FILE
        try:
            token = path.read_text(encoding="utf-8").strip()
        except OSError as e:
            raise Refusal("adapter.no-token", str(path), f"no model credential for this tenant: {e}") from None
        if not token:
            raise Refusal("adapter.no-token", str(path), "the credential file is empty")
        return token

    def _result(self, job: RunJob, rundir: Path) -> PhaseResult:
        """The image's answer, joined to what the factory already knows.

        The run id, the phase, the agent kind, the model and the effort come from the **job** — they are what the
        tenant's signed policy asked for, and a record of what was asked is what makes a divergence visible later.
        `guard_blocks` is counted from the guard's own log by this side of the mount, because a phase that reported
        its own denials could report none."""
        spec = job.policy.agent(job.identity.agent)
        try:
            raw: Any = json.loads((rundir / "result.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise Refusal("adapter.infra", job.run_id, f"the container left no readable result: {e}") from None
        if not isinstance(raw, dict):
            raise Refusal("adapter.infra", job.run_id, "the container's result is not an object")
        blocks = render.count_blocks(_lines(rundir / "blocks.jsonl"))
        return result(
            {
                **raw,
                "run_id": job.run_id,
                "phase": job.phase,
                "agent": job.identity.agent,
                "model": spec.model,
                "effort": spec.effort,
                "prompt_version": job.prompt_version,
                "guard_blocks": blocks,
                "harness": raw.get("harness", HARNESS),
                "billing_class": "plan",
            }
        )


def _name(job: RunJob) -> str:
    """One container name per run and phase, so the watchdog can find the thing it has to kill."""
    return f"isidium-{job.run_id}-{job.phase}"


def _rate_limited(detail: str) -> bool:
    low = detail.lower()
    return any(m in low for m in RATE_LIMIT_MARKERS)


def _lines(path: Path) -> Sequence[str]:
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ()
