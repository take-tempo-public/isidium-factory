"""The wrapper — everything around a phase that the phase is not allowed to do [V4a-i, 2026-09-12].

T-B5 and T-C6 between them put four things on this side of the seam and none on the other: the worktree the phase
writes in, the **identity the commit is authored under** (*"the model never holds git credentials"* — 7j.5), the
**recompute** that refuses a result whose claimed change set differs from git's (the gajae follow-up, adopted
2026-08-21), and the **record** — the phase row and, when a phase ends the run, the run's outcome, written with the
transaction discipline `dispatch` used (the card's R2: *"no row, no run, and what happened after the row is on the
row"*).

The adapter does one thing: it runs the phase. Everything here is what makes the result trustworthy.

**Two facts are re-derived rather than believed.** The payload is re-assembled at the run's own `base_sha` and its
hash compared with the one the ledger wrote at dispatch — a substrate that moved under a dispatched run is an
environment fault, not a build. And the touched set comes from `git status` in the worktree, never from the
result's `touched`, which is kept only so that a disagreement is visible.

**Who the commit is authored by, and what is not decided here.** V4a-i commits under the tenant's existing forge
identity — the lander's, the one the forge actually attributes — with a `Factory-Agent` trailer naming the agent
kind that did the work. 7f [owner, 2026-08-16] gives *"each bot writing code its own git identifier and github
account"*, and the builder is a bot writing code; but the Terms finding of 2026-09-10 (one free machine account per
person, already spent) is why the factory runs as an App at all, and whether the builder gets a second App identity
is the owner's call, not this chunk's. The trailer is the seam: the record says which agent wrote it either way.
"""

from __future__ import annotations

import datetime as _dt
import os
import subprocess
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from isidium.store.core import telemetry
from isidium.store.core.refusal import Refusal

from . import adapter as adapter_mod
from . import checkout, guard
from . import payload as payload_mod
from .context import TenantContext
from .ledger import Ledger
from .tenant import Registration

SPAN: Final = "isidium.factory.run.phase"
TRAILER_RUN: Final = "Factory-Run"
TRAILER_AGENT: Final = "Factory-Agent"

# The agent kind each phase runs as (05 §1's roster). V4a-i runs `build`; the other rows are here because the map is
# the roster's, not this chunk's, and a phase whose agent is unnamed could not find its model.
AGENT_OF: Final[Mapping[str, str]] = {
    "plan": "plan-author",
    "refute": "plan-refuter",
    "judge": "judge",
    "build": "builder",
    "review": "reviewer",
    "reconcile": "reviewer",
}

# The test paths a card may always write, beside its declared `surfaces` — T-B5 (1)'s *"surfaces ∪ test paths"*.
# A card that declares its own test file gets it through `surfaces` as well; this is the floor, not the ceiling.
TEST_PATHS: Final[tuple[str, ...]] = ("tests/",)

PROMPT_VERSION: Final = "v1"

Call = Callable[[str, Mapping[str, Any]], Mapping[str, Any]]
Now = Callable[[], _dt.datetime]


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.UTC)


def run_phase(
    ctx: TenantContext,
    reg: Registration,
    ledger: Ledger,
    call: Call,
    *,
    run_id: str,
    phase: str = "build",
    factory: adapter_mod.AdapterFactory | None = None,
    now: Now = _now,
) -> dict[str, Any]:
    """One phase of one dispatched run, end to end. Returns the run's row as the ledger holds it afterwards."""
    with telemetry.span(SPAN, **{"isidium.run_id": run_id, "isidium.phase": phase}) as sp:
        row = ledger.run(run_id)
        if row is None:
            raise Refusal("ledger.unknown-run", run_id, "no such run in this ledger")
        if row["ended_at"]:
            raise Refusal("run.ended", run_id, f"this run ended {row['ended_at']} as {row['outcome']}")
        agent = AGENT_OF.get(phase)
        if agent is None:
            raise Refusal("run.phase", phase, f"not a phase an adapter runs: {sorted(AGENT_OF)}")

        policy = adapter_mod.ExecutorPolicy.from_effective(ctx.eff)
        spec = policy.agent(agent)
        sp.set_attribute("isidium.model", spec.model)
        drv = (factory or adapter_mod.resolve(str(row["adapter"])))(ctx.home, reg)

        tree = ctx.home / "worktrees" / run_id
        work = checkout.worktree(ctx.checkout, str(row["story_branch"]), tree)
        try:
            job = _job(ctx, reg, row, call, run_id=run_id, phase=phase, agent=agent, policy=policy, work=work)
            at = now().strftime("%Y-%m-%dT%H:%M:%SZ")
            try:
                res = drv.execute(job)
            except Refusal as r:
                ledger.finish(run_id, at, _outcome_of(r), billing_class=drv.capabilities().billing_class)
                raise
            touched = checkout.touched(work)
            _believe_nothing(res, touched)
            outside = guard.outside(touched, job.allowed_writes)
            at = now().strftime("%Y-%m-%dT%H:%M:%SZ")
            if outside:
                ledger.phase(run_id, at, {**res.row(), "touched": list(touched), "outcome": "failed:scope"})
                ledger.finish(run_id, at, "failed:scope", surfaces_actual=list(touched))
                raise Refusal("run.scope", outside[0], "; ".join(outside) + " — outside the card's surfaces")
            head = _commit(work, run_id, agent, ctx.identity.name, ctx.identity.email, touched)
            ledger.phase(run_id, at, {**res.row(), "touched": list(touched)})
            if res.outcome != "ok":
                ledger.finish(
                    run_id,
                    at,
                    res.outcome,
                    head_sha=head,
                    surfaces_actual=list(touched),
                    billing_class=res.billing_class,
                )
            elif head is not None:
                ledger.advance(run_id, head, list(touched), res.billing_class)
        finally:
            checkout.worktree_remove(ctx.checkout, tree)
        after = ledger.run(run_id)
        assert after is not None
        return {**after, "phases": ledger.phases_of(run_id)}


def _job(
    ctx: TenantContext,
    reg: Registration,
    row: Mapping[str, Any],
    call: Call,
    *,
    run_id: str,
    phase: str,
    agent: str,
    policy: adapter_mod.ExecutorPolicy,
    work: Path,
) -> adapter_mod.RunJob:
    """The payload, re-assembled at the run's own `base_sha` — and checked against the hash the ledger wrote at
    dispatch. Same inputs, same hash (T-B3 (4)); a different one means the substrate moved under a dispatched run,
    which is an environment fault and not something to build on."""
    card = int(row["card"])
    inp = checkout.gather(
        ctx.checkout,
        str(row["base_sha"]),
        card,
        tenant=ctx.tenant,
        root=ctx.root,
        context_of=lambda cid: call("show", {"target": "neighborhood", "id": cid}),
        identity=payload_mod.Identity(ctx.identity.login, reg.adapter),
        caps=payload_mod.Caps(reg.max_bytes),
        registry=ctx.registry,
    )
    p = payload_mod.assemble(inp)
    if p.payload_hash != row["payload_hash"]:
        raise Refusal(
            "run.payload-moved",
            run_id,
            f"the payload at {row['base_sha']} hashes {p.payload_hash}, the ledger wrote {row['payload_hash']}",
        )
    surfaces = tuple(str(s) for s in (p.value["constraints"].get("surfaces") or ()))
    if not surfaces:
        raise Refusal("run.no-surfaces", str(card), "the card declares no surfaces: there is nowhere it may write")
    return adapter_mod.job(
        {
            "run_id": run_id,
            "card": card,
            "phase": phase,
            "payload": p.value,
            "payload_hash": p.payload_hash,
            "worktree": str(work),
            "allowed_writes": surfaces + TEST_PATHS,
            "policy": policy,
            "identity": {"agent": agent, "name": ctx.identity.name, "email": ctx.identity.email},
            "prompt_version": PROMPT_VERSION,
        }
    )


def _believe_nothing(res: adapter_mod.PhaseResult, touched: Sequence[str]) -> None:
    """*"The report's claimed change set is never trusted"* — the ledger recomputes it from git and refuses a report
    whose claimed set differs, **before** judging `surfaces` (the gajae follow-up, with T-C3). A result that claims
    nothing is not claiming something false, and passes: the recompute is what the record keeps either way."""
    if not res.touched:
        return
    claimed, actual = set(res.touched), set(touched)
    if claimed != actual:
        over = sorted(claimed - actual) or ["(none)"]
        under = sorted(actual - claimed) or ["(none)"]
        raise Refusal(
            "run.change-set",
            res.run_id,
            f"the result claims {over} git does not have, and git has {under} it does not claim",
        )


def _commit(work: Path, run_id: str, agent: str, name: str, email: str, touched: Sequence[str]) -> str | None:
    """T-B5 (4): *"commits by the wrapper: bot identity, … `Factory-Run` trailer — one commit at phase end"*. The
    author is the wrapper's, never the model's, and the trailers say which run and which agent kind did the work.
    A phase that wrote nothing gets no commit and no head — an empty commit would be a claim of work."""
    if not touched:
        return None
    add = subprocess.run(["git", "add", "-A"], cwd=work, capture_output=True, text=True, check=False)
    if add.returncode != 0:
        raise Refusal("factory.git", str(work), add.stderr.strip())
    message = f"{agent}: {run_id}\n\n{TRAILER_RUN}: {run_id}\n{TRAILER_AGENT}: {agent}\n"
    env = {"GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": email, "GIT_COMMITTER_NAME": name, "GIT_COMMITTER_EMAIL": email}
    made = subprocess.run(
        ["git", "commit", "-m", message],
        cwd=work,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, **env},
    )
    if made.returncode != 0:
        raise Refusal("factory.git", str(work), made.stderr.strip() or made.stdout.strip())
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=work, capture_output=True, text=True, check=False)
    return head.stdout.strip() or None


def _outcome_of(r: Refusal) -> str:
    """An adapter's refusal, as the run record's outcome. T-C6's failure protocol names `failed:infra` for a start
    or a timeout; an environment answer (a provider limit) is `failed:environment`, the class the picker backs off
    on rather than retries."""
    return "failed:environment" if r.rule.endswith(".environment") else "failed:infra"
