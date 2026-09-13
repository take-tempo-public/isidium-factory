"""Close — T-A9 over the chain that ran, and the run's end told to the store [V5a, 2026-09-12].

Q-V18 [owner, 2026-09-12]: V5a before V4a-ii, and a card may close over a build-only chain — **declared, not
refused**: the run record's `phases[]` already names every phase that ran, and the close's own record repeats it.

**What is refused, and never ends a run** — a read that cannot answer yet is not a failure of the run:

* the run already ended (`close.ended`); no pull request recorded or given (`close.no-pr`);
* a pull request whose head is not the run's `head_sha` (`close.pr-mismatch`) — it is not this run's work;
* not merged (`close.not-merged`) — the run stays in flight until the merge, which is the owner's button (X2);
* a checkout that is dirty or whose `HEAD` does not contain the merge commit (`close.checkout`) [Q-V23 (a)] —
  acceptance runs **in the tenant's checkout**, because a runner is the tenant's toolchain and, in a worktree, an
  editable install imports the checkout's source rather than the merge's (the finding that ruled it);
* the gate still running, or a required check absent (`close.gate-pending`) — the gate is **the ruleset's required
  checks on the merge commit, read from the forge** [Q-V21 (a)].

**What fails the run, in the catalog's order** — T-A9's hard conditions, each a typed class the store holds since
Q-V22 (a), each ending the run and landing its end: **drift** — the card's build now is not the build dispatched
(condition 4, `failed:card-drift`); **identity** — a commit in `base_sha..head_sha` not authored by the run's
identity or without its `Factory-Run` trailer (condition 3, `failed:identity`); **the gate red** (condition 2,
`failed:gate`); **acceptance** — no scenario ran, or one did not `pass` (condition 1, *"none skipped"*,
`failed:acceptance`). Each is checked only when the one before it held.

**Green is `complete` then `closed`**, in one ledger transaction and one land. Whose closure it verifies is the card's:
a human who closed it (T-A12, *"the human raced the line"*) has their newest closure verified — `closure_kind: human`
and that closure's id, the only record that moves the label from `closed (unverified)` to `closed`; a card nobody
closed gets the factory's own, `f-<run-id>`.

**A withdrawn or demoted card abandons its run, and nothing lands** [Q-V20 (b)]: the card's own label already says
so, and for a run whose `dispatched` the store holds, the store's walk has emitted its own `withdrawn`.

**Declared, not checked:** condition 3's *signed* (the wrapper does not sign commits — V4a-i); condition 5 is on the
row already (`surfaces_actual`); condition 6's close-report template does not exist yet.
"""

from __future__ import annotations

import datetime as _dt
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Final, Protocol

from isidium.store.client import accept as accept_mod
from isidium.store.core import telemetry
from isidium.store.core.refusal import Refusal

from . import lander
from .context import TenantContext
from .forge import Checks, MergeState, Verdict
from .ledger import ABANDONED, CLOSED, Ledger
from .runner import TRAILER_RUN

SPAN: Final = "isidium.factory.close"
# The card statuses that take a dispatched run's reason away: withdrawn, and demoted back to draft.
ABANDONING: Final[frozenset[str]] = frozenset({"withdrawn", "draft"})
FACTORY_CLOSURE: Final = "f-"

Call = Callable[[str, Mapping[str, Any]], Any]
Accept = Callable[[Call, Path, str, int], Mapping[str, Any]]


class Reader(Protocol):
    """The two forge reads a close makes (`forge.Forge`'s own): nothing written, and nothing merged."""

    def merge_state(self, number: int) -> MergeState: ...
    def checks(self, sha: str) -> Checks: ...


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.UTC)


def _stamp(t: _dt.datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _accept(call: Call, workdir: Path, root: str, card_id: int) -> Mapping[str, Any]:
    """`accept` without `--close`: the scenarios run and their verdicts come back; the factory writes no card."""
    return accept_mod.accept(call, workdir, root, card_id)


def close(
    ctx: TenantContext,
    ledger: Ledger,
    call: Call,
    forge: Reader,
    *,
    run_id: str,
    pr: int | None = None,
    accept: Accept = _accept,
    now: Callable[[], _dt.datetime] = _now,
) -> dict[str, Any]:
    """One run, closed or failed or abandoned — or refused, and still in flight. The run's row back, its phases, and
    what the land answered."""
    with telemetry.span(SPAN, **{"isidium.tenant": ctx.tenant, "isidium.run_id": run_id}) as sp:
        try:
            out = _close(ctx, ledger, call, forge, run_id, pr, accept, now)
        except Refusal as r:
            telemetry.record_refusal_on(sp, r.rule)
            raise
        sp.set_attribute("isidium.outcome", str(out["outcome"]))
        telemetry.record_ok()
        return out


def _close(
    ctx: TenantContext,
    ledger: Ledger,
    call: Call,
    forge: Reader,
    run_id: str,
    pr: int | None,
    accept: Accept,
    now: Callable[[], _dt.datetime],
) -> dict[str, Any]:
    row = ledger.run(run_id)
    if row is None:
        raise Refusal("ledger.unknown-run", run_id, "no such run in this ledger")
    if row["ended_at"]:
        raise Refusal("close.ended", run_id, f"this run ended {row['ended_at']} as {row['outcome']}")
    cid = int(row["card"])
    card = call("show", {"target": "card", "id": cid})
    status = str(card["head"].get("status"))
    if status in ABANDONING:
        ledger.end(run_id, _stamp(now()), ABANDONED, detail={"card_status": status})
        return _result(ledger, run_id, {"sent": 0, "abandoned": status})

    number = pr if pr is not None else row["pr"]
    if number is None:
        raise Refusal("close.no-pr", run_id, "no pull request is recorded for this run; --pr names it")
    state = forge.merge_state(int(number))
    if state.head != row["head_sha"]:
        raise Refusal("close.pr-mismatch", f"#{number}", f"its head is {state.head}; this run's is {row['head_sha']}")
    if pr is not None and row["pr"] != pr:
        ledger.set_pr(run_id, pr)
    if not state.merged or state.merge_commit is None:
        raise Refusal("close.not-merged", f"#{number}", "the run stays in flight until its pull request merges")
    at_head = _checkout_at(ctx.checkout, state.merge_commit)
    gate = forge.checks(state.merge_commit)
    if gate.verdict is Verdict.PENDING:
        raise Refusal(
            "close.gate-pending",
            state.merge_commit,
            "required checks not all completed on the merge commit: " + (", ".join(gate.required) or "(none named)"),
        )

    history = card.get("history") or []
    build = str(history[-1].get("build", "")) if history else ""
    detail: dict[str, Any] = {
        "pr": int(number),
        "merge_commit": state.merge_commit,
        "checkout": at_head,
        "phases": [str(p["phase"]) for p in ledger.phases_of(run_id)],
    }
    failure: str | None = None
    verdicts: dict[str, str] = {}
    if build != row["build_hash"]:
        failure = "card-drift"
        detail["build"] = build
    elif foreign := _foreign(ctx.checkout, str(row["base_sha"]), str(row["head_sha"]), run_id, ctx.identity.email):
        failure = "identity"
        detail["commits"] = foreign
    elif gate.verdict is Verdict.RED:
        failure = "gate"
    else:
        res = accept(call, ctx.checkout, ctx.root, cid)
        verdicts = {str(v["scenario_id"]): str(v["verdict"]) for v in res["verdicts"]}
        detail["verdicts"] = verdicts
        detail["manifest_hash"] = str(res["manifest_hash"])
        if not verdicts or not res["passed"]:
            failure = "acceptance"
    at = _stamp(now())
    if failure is not None:
        ledger.end(run_id, at, f"failed:{failure}", detail=detail)
        return _result(ledger, run_id, lander.land_run(ledger, call, run_id))

    closures = card["head"].get("closures") or []
    newest = closures[-1] if closures else None
    human = newest is not None and newest.get("kind") == "human" and not newest.get("retracted")
    phases = ledger.phases_of(run_id)
    complete = {
        "run_id": run_id,
        "build_hash": build,
        "cost_micro": sum(int(p["cost_micro"] or 0) for p in phases),
        "duration_ms": sum(int(p["duration_ms"] or 0) for p in phases),
    }
    closed = {
        "closure_id": str(newest["id"]) if human and newest is not None else FACTORY_CLOSURE + run_id,
        "build_hash": build,
        "closure_kind": "human" if human else "factory",
        "verdicts": verdicts,
        "evidence": [detail["manifest_hash"], at_head],
        "verified": True,
    }
    ledger.end(run_id, at, CLOSED, store_events=(("complete", complete), ("closed", closed)), detail=detail)
    return _result(ledger, run_id, lander.land_run(ledger, call, run_id))


def _result(ledger: Ledger, run_id: str, land: Mapping[str, Any]) -> dict[str, Any]:
    row = ledger.run(run_id)
    assert row is not None
    return {**row, "phases": ledger.phases_of(run_id), "land": dict(land)}


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=False)


def _checkout_at(repo: Path, merge: str) -> str:
    """Q-V23 (a): the checkout clean — tracked files only; an untracked file is not what a scenario imports — and its
    `HEAD` containing the merge commit. Three spawns; the `HEAD` it answers is the close's evidence."""
    dirty = _git(repo, "status", "--porcelain=v1", "--untracked-files=no")
    if dirty.returncode != 0:
        raise Refusal("factory.git", str(repo), dirty.stderr.strip())
    if dirty.stdout.strip():
        raise Refusal("close.checkout", str(repo), "uncommitted changes: acceptance would run against them")
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    contains = _git(repo, "merge-base", "--is-ancestor", merge, "HEAD")
    if contains.returncode != 0:
        raise Refusal("close.checkout", merge, f"the checkout's HEAD {head} does not contain the merge commit: pull it")
    return head


def _foreign(repo: Path, base: str, head: str, run_id: str, email: str) -> list[str]:
    """T-A9 condition 3, one `git log`: every commit the run's range holds that the run's identity did not author, or
    that does not carry this run's `Factory-Run` trailer."""
    fmt = f"--format=%H%x1f%ae%x1f%(trailers:key={TRAILER_RUN},valueonly,separator=%x2C)%x1e"
    r = _git(repo, "log", fmt, f"{base}..{head}")
    if r.returncode != 0:
        raise Refusal("factory.git", f"{base}..{head}", r.stderr.strip())
    bad: list[str] = []
    for record in r.stdout.split("\x1e"):
        # Newlines only: `str.strip()` counts the unit separator as whitespace, and a commit with no trailer ends its
        # record in one — stripping it made that commit a two-field record that was skipped, and so passed [found by
        # the trailerless test, 2026-09-12]. A record that does not parse is foreign, never skipped.
        record = record.strip("\r\n")
        if not record:
            continue
        fields = record.split("\x1f")
        if len(fields) != 3:
            bad.append(fields[0])
            continue
        sha, author, runs = fields
        if author != email or run_id not in {x.strip() for x in runs.split(",")}:
            bad.append(sha)
    return bad
