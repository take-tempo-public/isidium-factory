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
import json
import os
import subprocess
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from isidium.store.core import telemetry
from isidium.store.core.refusal import Refusal

from . import adapter as adapter_mod
from . import artifacts as artifacts_mod
from . import checkout, gate, guard, lander
from . import payload as payload_mod
from .context import TenantContext
from .ledger import Ledger
from .tenant import Registration

SPAN: Final = "isidium.factory.run.phase"
CHAIN_SPAN: Final = "isidium.factory.run.chain"
TRAILER_RUN: Final = "Factory-Run"
TRAILER_AGENT: Final = "Factory-Agent"
# [owner, 2026-09-15] a failed phase's work is committed to its story branch and never pushed; the trailer is how the
# commit says it is a failure's, and how `push` knows without asking the ledger twice.
TRAILER_OUTCOME: Final = "Factory-Outcome"
# [Q-V31 (c), owner 2026-09-20] the commit that carries a failed run's work onto this run's branch says whose work it
# was. Without it the carried commit is indistinguishable from the phase's own, and `close`'s identity walk -- which
# reads every commit in `base..head` for a `Factory-Run` trailer -- would have no way to tell them apart either.
TRAILER_CARRIED: Final = "Factory-Carried"

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

# The phases that write nothing (05 §1: the plan-refuter and the judge write *"nothing"*; the plan author's one output
# is the plan artifact; the reviewer files findings). Their job carries no write surface, so the guard denies every
# write by construction, and a write that happened anyway ends the run uncommitted.
READ_ONLY: Final[frozenset[str]] = frozenset({"plan", "refute", "judge", "review"})

# The phases the plan gate can route a chain through (`gate.next_step`), up to the build — every one's agent row
# is checked before a chain's first phase spends. The review gate beyond the build is V4a-ii-b's.
LINE: Final[tuple[str, ...]] = ("plan", "refute", "judge", "build")

# The prompt version each agent kind runs — 7bd.11's `prompts/<agent>/<version>.md` — is the agent's signed
# `[agents].<kind>.prompt` since config@7 [owner, 2026-09-22]. It was a map here until then, kept in code on purpose
# [owner, 2026-09-19]: a signed row can name a version the running image does not carry, and `harness.prompt_input`
# would fail on it inside the container, mid-phase. The check that note said was missing is built with the move —
# `adapter.require_prompts` against the image's own label, at dispatch and again before each spawn — so the model,
# the effort and the prompt are one signature now. The builder's `v3` default carries the map's history: v2 named the
# project gate and the turn budget (`r-6` spent its last turns polling `sleep 90` and ended `failed:budget` with the
# work done); v3 says what to do with a previous attempt's work already in the tree (Q-V31 (c)).

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
    if phase not in AGENT_OF:
        raise Refusal("run.phase", phase, f"not a phase an adapter runs: {sorted(AGENT_OF)}")
    return _drive(ctx, reg, ledger, call, run_id, (phase,), factory, now)


def run_chain(
    ctx: TenantContext,
    reg: Registration,
    ledger: Ledger,
    call: Call,
    *,
    run_id: str,
    factory: adapter_mod.AdapterFactory | None = None,
    now: Now = _now,
) -> dict[str, Any]:
    """The run driven from the last phase the ledger holds to its next end or gate [V4a-ii-a, point 7] — in **one
    worktree**, created at the first phase and removed at the end, not one per phase.

    **The path is the plan gate's** (`gate.next_step`, a function of the history the ledger holds and the card): plan,
    the lint, refute, judge, at most one revision, then the build or a park. The chain ends after the build — the review
    gate is V4a-ii-b's — or at a park, or when a phase ends the run. A resumed chain takes the path it would have taken
    uninterrupted, because the step is a function of the history and nothing else."""
    with telemetry.span(CHAIN_SPAN, **{"isidium.run_id": run_id}):
        return _drive(ctx, reg, ledger, call, run_id, None, factory, now)


def _drive(
    ctx: TenantContext,
    reg: Registration,
    ledger: Ledger,
    call: Call,
    run_id: str,
    phases: Sequence[str] | None,
    factory: adapter_mod.AdapterFactory | None,
    now: Now,
) -> dict[str, Any]:
    """The phases — the named ones, or the gate's when `phases` is None — in one worktree, until one ends the run.
    Everything checked before the worktree exists spends nothing and leaves the run in flight: the run's row, every
    agent's policy row, the image's prompt set, the payload's hash and the history's artifacts."""
    row = ledger.run(run_id)
    if row is None:
        raise Refusal("ledger.unknown-run", run_id, "no such run in this ledger")
    if row["ended_at"]:
        raise Refusal("run.ended", run_id, f"this run ended {row['ended_at']} as {row['outcome']}")
    policy = adapter_mod.ExecutorPolicy.from_effective(ctx.eff)
    for phase in phases if phases is not None else LINE:  # a chain that cannot finish never starts
        policy.agent(AGENT_OF[phase])
    drv = (factory or adapter_mod.resolve(str(row["adapter"])))(ctx.home, reg)
    # Again here, not only at dispatch: the image can be swapped between the two. Before the worktree, so a miss
    # spends nothing and leaves the run in flight like the policy refusals above — swap the image, run again.
    adapter_mod.require_prompts(policy, drv.prompts(), run_id)
    # The payload once per drive, not once per phase: every phase of a run reads the same card at the same commit, and
    # re-gathering it (a store call and the git reads) for each of up to seven phases would buy nothing.
    p = _payload(ctx, reg, row, call, run_id)
    history = _history(ledger, ctx.home, run_id)
    carry = not history

    tree = ctx.home / "worktrees" / run_id
    work = checkout.worktree(ctx.checkout, str(row["story_branch"]), tree)
    try:
        carried = None
        if carry:
            first = phases[0] if phases is not None else "plan"
            try:
                carried = _carry(ledger, row, work, run_id, AGENT_OF[first], ctx)
            except Refusal as r:
                # **Its own handler, not the adapter's below.** That one writes a phase row and keeps the phase's
                # work; a carry that refused ran no phase and left a tree it had already reset, so there is neither.
                # What the two share is the rule underneath: a run that cannot go on must END. A refusal that leaves
                # one in flight holds the WIP cap for ever — the defect V5a was built to close.
                ledger.finish(run_id, now().strftime("%Y-%m-%dT%H:%M:%SZ"), _outcome_of(r))
                raise
        queue = list(phases) if phases is not None else None
        while True:
            if queue is not None:
                if not queue:
                    break
                phase = queue.pop(0)
            else:
                step = gate.next_step(history, p.value)
                if step.kind == "done":
                    break
                if step.kind == "park":
                    _park(ledger, ctx.home, row, history, step, now)
                    lander.land_run(ledger, call, run_id)
                    break
                assert step.phase is not None
                phase = step.phase
            with telemetry.span(SPAN, **{"isidium.run_id": run_id, "isidium.phase": phase}) as sp:
                sp.set_attribute("isidium.model", policy.agent(AGENT_OF[phase]).model)
                _phase(ctx, ledger, call, row, drv, policy, work, phase, p, history, carried, now)
            carried = None  # the carry is told to the phase it was replayed for, and to no later one
            history = _history(ledger, ctx.home, run_id)
            after = ledger.run(run_id)
            if after is not None and after["ended_at"]:
                break
    except Refusal:
        # [V5a] a phase that ended the run tells the store before the refusal reaches the operator: a failure the
        # store never heard of reads `dispatched` on the board for ever (Q-V22). A refusal that ended nothing
        # sends only what an earlier land missed — the watermark decides, not this line.
        lander.land_run(ledger, call, run_id)
        raise
    finally:
        checkout.worktree_remove(ctx.checkout, tree)
    after = ledger.run(run_id)
    assert after is not None
    return {**after, "phases": ledger.phases_of(run_id)}


def _phase(
    ctx: TenantContext,
    ledger: Ledger,
    call: Call,
    row: Mapping[str, Any],
    drv: adapter_mod.Adapter,
    policy: adapter_mod.ExecutorPolicy,
    work: Path,
    phase: str,
    p: payload_mod.Payload,
    history: Sequence[gate.Done],
    carried: adapter_mod.Carried | None,
    now: Now,
) -> None:
    """One phase in a worktree that already exists: the job, the adapter, the recompute, the record."""
    run_id = str(row["run_id"])
    agent = AGENT_OF[phase]
    job = _job(ctx, row, p, run_id=run_id, phase=phase, agent=agent, policy=policy, work=work, history=history)
    if carried is not None:
        job = job.model_copy(update={"carried": carried})
    try:
        res = drv.execute(job)
    except Refusal as r:
        # The end is when the adapter gave up, not when it was handed the job: `r-4`'s `ended_at` read the
        # phase's start, seventeen minutes early (2026-09-14). And what the phase spent is on the record even
        # when the adapter refused it — T-A7's *"telemetry per phase … required, not optional"*.
        at = now().strftime("%Y-%m-%dT%H:%M:%SZ")
        outcome = _outcome_of(r)
        changed = checkout.touched(work)
        if isinstance(r, adapter_mod.PhaseRefusal) and r.result is not None:
            ledger.phase(run_id, at, {**r.result.row(), "touched": list(changed)})
        # [owner, 2026-09-15] the work survives the failure: `r-5`'s builder had edited all seven surfaces
        # when its harness crashed, and the worktree was removed with nothing kept. A phase that may write nothing
        # has no work to keep — whatever it wrote is not work.
        head = None
        if phase not in READ_ONLY:
            head = _keep_work(work, run_id, agent, ctx.identity.name, ctx.identity.email, changed, outcome)
        ledger.finish(
            run_id,
            at,
            outcome,
            head_sha=head,
            surfaces_actual=list(changed) if changed else None,
            billing_class=drv.capabilities().billing_class,
        )
        raise
    touched = checkout.touched(work)
    _believe_nothing(res, touched)
    outside = guard.outside(touched, job.allowed_writes)
    at = now().strftime("%Y-%m-%dT%H:%M:%SZ")
    if outside:
        ledger.phase(run_id, at, {**res.row(), "touched": list(touched), "outcome": "failed:scope"})
        if phase in READ_ONLY:
            # [owner, 2026-09-23] a phase that may write nothing and wrote something ends the run uncommitted: there
            # is no work of its to keep, and a commit would put a read-only agent's edit on the story branch.
            ledger.finish(run_id, at, "failed:scope", surfaces_actual=list(touched))
            raise Refusal("run.read-only", outside[0], f"the {phase} phase writes nothing; it wrote {list(touched)}")
        head = _keep_work(work, run_id, agent, ctx.identity.name, ctx.identity.email, touched, "failed:scope")
        ledger.finish(run_id, at, "failed:scope", head_sha=head, surfaces_actual=list(touched))
        raise Refusal("run.scope", outside[0], "; ".join(outside) + " — outside the card's surfaces")
    verdict = None
    if res.outcome == "ok":
        _believe_artifacts(res, phase, ctx.home)
        if phase == "judge":
            # The verdict row, in the phase's own transaction (V4a-ii-a point 4): the judge's verdict as it said it —
            # the floor is applied by the gate, never written over the record — and its reasoning by the artifact's
            # hash (03 §6: *"`reasoning` a ref into the run's artifacts"*).
            art = res.artifacts[0]
            said = artifacts_mod.Verdict.model_validate_json((ctx.home / art.path).read_bytes())
            verdict = (said.verdict, art.sha256)
    failed = None if res.outcome == "ok" else res.outcome
    head = _commit(work, run_id, agent, ctx.identity.name, ctx.identity.email, touched, failed)
    ledger.phase(run_id, at, {**res.row(), "touched": list(touched)}, verdict=verdict)
    if res.outcome != "ok":
        ledger.finish(
            run_id,
            at,
            res.outcome,
            head_sha=head,
            surfaces_actual=list(touched),
            billing_class=res.billing_class,
        )
        lander.land_run(ledger, call, run_id)
    elif head is not None:
        ledger.advance(run_id, head, list(touched), res.billing_class)


def _history(ledger: Ledger, home: Path, run_id: str) -> list[gate.Done]:
    """The phases the ledger holds, in order, each with its artifact re-hashed against the ledger's record (T-B7 (3):
    *"every artifact referenced exists at its hash"*) — what the gate decides from and what later phases are handed.
    An artifact whose bytes moved is refused here, before anything spends, and the run stays in flight."""
    out: list[gate.Done] = []
    for ev in ledger.events_of(run_id):
        if ev["kind"] != "phase":
            continue
        made = ev["data"].get("artifacts") or []
        value: dict[str, Any] | None = None
        if made:
            art = made[0]
            try:
                data = (home / str(art["path"])).read_bytes()
            except OSError as e:
                raise Refusal(
                    "run.artifact-missing", str(art["path"]), f"the {art['name']} is not where the ledger says: {e}"
                ) from None
            if artifacts_mod.sha256(data) != art["sha256"]:
                raise Refusal(
                    "run.artifact-moved", str(art["path"]), f"the {art['name']} no longer hashes to {art['sha256']}"
                )
            value = json.loads(data)
        out.append(gate.Done(str(ev["data"].get("phase")), value))
    return out


def _park(
    ledger: Ledger, home: Path, row: Mapping[str, Any], history: Sequence[gate.Done], step: gate.Step, now: Now
) -> None:
    """T-C5 as far as V4a-ii reaches: the typed question — all nine fields — kept as the run's `question.json`, the
    ledger ended `parked`, and the store told `parked{run_id, text}` with the question and its hash. The answer's
    channel is the sitting; re-dispatch after it is V6's [Q-V28 (a)]."""
    run_id = str(row["run_id"])
    made = [
        str(a["sha256"])
        for ev in ledger.events_of(run_id)
        if ev["kind"] == "phase"
        for a in ev["data"].get("artifacts") or []
    ]
    question = artifacts_mod.ParkQuestion(
        run_id=run_id,
        card_id=int(row["card"]),
        phase=history[-1].phase if history else "plan",
        question=step.question,
        options=(),
        tried=tuple(d.phase for d in history),
        why_blocked=step.why_blocked,
        source_tag=step.source_tag,
        artifacts_so_far=tuple(made),
    )
    data = artifacts_mod.canonical(question.model_dump(mode="json"))
    path = home / "runs" / run_id / "question.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    sha = artifacts_mod.sha256(data)
    text = f"[{step.source_tag}] {step.question} — {step.why_blocked} (question {sha})"
    ledger.end(run_id, now().strftime("%Y-%m-%dT%H:%M:%SZ"), "parked", text=text, detail={"question": sha})


def _believe_artifacts(res: adapter_mod.PhaseResult, phase: str, home: Path) -> None:
    """A structured phase that says `ok` answered with exactly its artifact, and the bytes at the path hash to what it
    claims — the adapter's word is not taken for either (the gajae follow-up's rule, applied to artifacts). Refused
    like a change set that disagrees with git: the run stays in flight and the operator reads why."""
    shaped = artifacts_mod.OF_PHASE.get(phase)
    expected = [shaped[0]] if shaped else []
    got = [a.name for a in res.artifacts]
    if got != expected:
        raise Refusal("run.artifact", res.run_id, f"the {phase} phase answers with {expected}; the result names {got}")
    for a in res.artifacts:
        try:
            data = (home / a.path).read_bytes()
        except OSError as e:
            raise Refusal("run.artifact", a.path, f"the {a.name} the result names is not there: {e}") from None
        if artifacts_mod.sha256(data) != a.sha256:
            raise Refusal("run.artifact", a.path, f"the {a.name}'s bytes do not hash to {a.sha256}")


def _payload(
    ctx: TenantContext, reg: Registration, row: Mapping[str, Any], call: Call, run_id: str
) -> payload_mod.Payload:
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
    if not p.value["constraints"].get("surfaces"):
        raise Refusal("run.no-surfaces", str(card), "the card declares no surfaces: there is nowhere it may write")
    return p


def _job(
    ctx: TenantContext,
    row: Mapping[str, Any],
    p: payload_mod.Payload,
    *,
    run_id: str,
    phase: str,
    agent: str,
    policy: adapter_mod.ExecutorPolicy,
    work: Path,
    history: Sequence[gate.Done] = (),
) -> adapter_mod.RunJob:
    """The job for one phase: what it reads (the payload, and the earlier artifacts the gate names for it — refused if
    a phase that cannot run without one has none) and where it may write — nothing for a read-only phase; for the build,
    the approved plan's `touched` ∪ the test paths (T-B5 (1): the plan narrows, nothing widens — the lint already
    proved it ⊆ the card's), or the card's `surfaces` ∪ the test paths for a build with no plan behind it."""
    named = gate.inputs_for(phase, history, p.value)
    have = {n for n, _ in named}
    missing = [n for n in artifacts_mod.INPUTS.get(phase, ()) if n not in have]
    if missing:
        raise Refusal(
            "run.artifact-missing", run_id, f"the {phase} phase reads the {missing[0]}, and no phase made one"
        )
    inputs = tuple(
        adapter_mod.Input(name=n, sha256=artifacts_mod.sha256(artifacts_mod.canonical(v)), content=v) for n, v in named
    )
    surfaces = tuple(str(s) for s in p.value["constraints"]["surfaces"])
    plan = next((v for n, v in named if n == "plan"), None)
    if phase in READ_ONLY:
        writes: tuple[str, ...] = ()
    elif phase == "build" and plan is not None:
        writes = tuple(artifacts_mod.Plan.model_validate(plan).touched) + TEST_PATHS
    else:
        writes = surfaces + TEST_PATHS
    return adapter_mod.job(
        {
            "run_id": run_id,
            "card": int(row["card"]),
            "phase": phase,
            "payload": p.value,
            "payload_hash": p.payload_hash,
            "worktree": str(work),
            "allowed_writes": writes,
            "policy": policy,
            "identity": {"agent": agent, "name": ctx.identity.name, "email": ctx.identity.email},
            "prompt_version": policy.agent(agent).prompt,
            "inputs": inputs,
            "round": 1 + sum(1 for d in history if d.phase == phase),
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


def _commit(
    work: Path, run_id: str, agent: str, name: str, email: str, touched: Sequence[str], outcome: str | None = None
) -> str | None:
    """T-B5 (4): *"commits by the wrapper: bot identity, … `Factory-Run` trailer — one commit at phase end"*. The
    author is the wrapper's, never the model's, and the trailers say which run and which agent kind did the work.
    A phase that wrote nothing gets no commit and no head — an empty commit would be a claim of work. A failed
    phase's commit says so in a `Factory-Outcome` trailer [owner, 2026-09-15]."""
    if not touched:
        return None
    message = f"{agent}: {run_id}\n\n{TRAILER_RUN}: {run_id}\n{TRAILER_AGENT}: {agent}\n"
    if outcome is not None:
        message += f"{TRAILER_OUTCOME}: {outcome}\n"
    return _commit_message(work, message, name, email)


def _commit_message(work: Path, message: str, name: str, email: str) -> str | None:
    """Everything in the tree, committed under the given identity — the mechanics `_commit` and the carry share, so
    that a carried commit is made exactly the way a phase's is and the two cannot drift in how they author."""
    add = subprocess.run(["git", "add", "-A"], cwd=work, capture_output=True, text=True, check=False)
    if add.returncode != 0:
        raise Refusal("factory.git", str(work), add.stderr.strip())
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


def _keep_work(
    work: Path, run_id: str, agent: str, name: str, email: str, touched: Sequence[str], outcome: str
) -> str | None:
    """A failed phase's work, committed to its story branch and never pushed [owner, 2026-09-15]. The failure is the
    run's end and stays the refusal the operator sees: a commit that cannot be made (the tenant's pre-commit hook
    refusing a governed path a scope failure wrote, say) leaves the head empty on the row rather than replacing the
    reason the run ended."""
    try:
        return _commit(work, run_id, agent, name, email, touched, outcome)
    except Refusal:
        return None


def _carry(
    ledger: Ledger,
    row: Mapping[str, Any],
    work: Path,
    run_id: str,
    agent: str,
    ctx: TenantContext,
) -> adapter_mod.Carried | None:
    """A resumed run's inherited work, replayed into the worktree and committed on its own [Q-V31 (c), owner
    2026-09-20]. A run that carries nothing does nothing here and spends no spawn.

    **Committed separately, and that is what makes the record honest.** The touched set is recomputed from
    `git status` in this worktree, so work left uncommitted would read as this run's: its files would be judged
    against *this* card's surfaces (a re-ratification may have narrowed them, and the phase would fail scope for
    work it did not do), and `surfaces_actual` would claim them. Its own commit, under the run's identity with a
    trailer naming where it came from, leaves the tree clean before the agent starts — so everything after it is
    genuinely this run's.
    """
    carried_from = row.get("carried_from")
    if not carried_from:
        return None
    source = ledger.run(str(carried_from))
    if source is None:  # the pick checked this; the ledger is the same file, so it is a corruption, not a user error
        raise Refusal("run.carry-unknown", str(carried_from), "the run this one carries is not in this ledger")
    files = checkout.carry_over(work, str(source["base_sha"]), str(source["head_sha"]))
    if files:
        message = (
            f"{agent}: {run_id} carries {carried_from}\n\n"
            f"{TRAILER_RUN}: {run_id}\n{TRAILER_AGENT}: {agent}\n{TRAILER_CARRIED}: {carried_from}\n"
        )
        _commit_message(work, message, ctx.identity.name, ctx.identity.email)
    return adapter_mod.Carried(
        run_id=str(carried_from),
        outcome=str(source["outcome"]),
        head_sha=str(source["head_sha"]),
        files=tuple(files),
    )


def _outcome_of(r: Refusal) -> str:
    """An adapter's refusal, as the run record's outcome. T-C6's failure protocol names `failed:infra` for a start
    or a timeout; an environment answer (a provider limit) is `failed:environment`, the class the picker backs off
    on rather than retries; and carried work that will not apply is `failed:merge` — the catalog's own name for a
    conflict, deterministic and diagnosable, which is why it is not folded into `infra` (`r-4`'s lesson: a class
    that does not say what happened bought one retry for nothing)."""
    if r.rule.endswith(".merge"):
        return "failed:merge"
    return "failed:environment" if r.rule.endswith(".environment") else "failed:infra"
