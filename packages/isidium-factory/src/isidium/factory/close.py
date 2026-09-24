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

**Before every end it writes, close recovers what a dead host left behind** [card 12, 2026-09-22]: `r-11`'s build
finished inside its container — a readable `result.json`, its spend measured — while the host process that would
have written the ledger's phase row was killed before it could. Close is the one door every such run leaves by, so a
phase directory the ledger never recorded is picked up there, at the container adapter's own layout
(`<deploy home>/runs/<run>/<step>/result.json`) — one directory listing per run, never a walk of the deploy home.
"""

from __future__ import annotations

import datetime as _dt
import json
import subprocess
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Protocol

from isidium.store.client import accept as accept_mod
from isidium.store.core import telemetry
from isidium.store.core.refusal import Refusal

from . import adapter as adapter_mod
from . import artifacts as artifacts_mod
from . import lander, render
from .context import TenantContext
from .forge import Checks, MergeState, Verdict
from .ledger import ABANDONED, CLOSED, Ledger
from .runner import TRAILER_RUN

SPAN: Final = "isidium.factory.close"
# The card statuses that take a dispatched run's reason away: withdrawn, and demoted back to draft.
ABANDONING: Final[frozenset[str]] = frozenset({"withdrawn", "draft"})
FACTORY_CLOSURE: Final = "f-"

# The container adapter's own layout (C2) — named once, here, and nowhere inside the scan itself (C-10).
RUNS: Final = "runs"
RESULT: Final = "result.json"
BLOCKS: Final = "blocks.jsonl"
LEFT_SPAN: Final = "isidium.factory.close.left"
RECORDED: Final = "isidium.close.recorded"
UNREADABLE: Final = "isidium.close.unreadable"

Call = Callable[[str, Mapping[str, Any]], Any]
Accept = Callable[[Call, Path, str, int], Mapping[str, Any]]


@dataclass(frozen=True)
class Recovered:
    """One left-behind phase, validated and ready for the ledger: the result `ledger.phase` takes, and — for a
    recovered `judge` — the verdict pair beside it, so the two are written in the same transaction rather than the
    verdict being looked up again at write time."""

    result: adapter_mod.PhaseResult
    verdict: tuple[str, str] | None


@dataclass(frozen=True)
class Left:
    """What a run's recovery found, for the end that follows it. `billing_class` is R2's asymmetry, decided here and
    not in `Ledger._end`: its `COALESCE(?, col)` prefers what is passed, and other callers rely on that (C3), so the
    choice of *what* to pass is close's. A run has one adapter — the `runs` row carries a single `adapter` — so its
    results cannot honestly disagree, and the first one found (phase, round order) is as good a pick as any merge
    rule this card does not ask for."""

    billing_class: str | None
    recorded: tuple[str, ...]
    unreadable: tuple[str, ...]

    def detail(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.recorded:
            out["recorded"] = list(self.recorded)
        if self.unreadable:
            out["unreadable"] = list(self.unreadable)
        return out


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


def _step_of(name: str) -> tuple[str, int]:
    """A run directory entry's name, split the way `RunJob.step` built it: `plan` is round 1, `plan-2` is `plan`'s
    round 2. No phase name carries a dash (05 §1's roster), so a trailing field that does not parse as a positive
    integer is not a round at all — it stays part of the name, at round 1."""
    phase, sep, suffix = name.rpartition("-")
    if sep and suffix.isdigit() and int(suffix) > 0:
        return phase, int(suffix)
    return name, 1


def _lines(path: Path) -> Sequence[str]:
    """Mirrors `container._lines`: `adapter.resolve` defers importing an adapter's module on purpose, and close must
    not be the one thing that imports podman's."""
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ()


def _left_results(home: Path, run_id: str, held: Sequence[Mapping[str, Any]]) -> tuple[list[Recovered], list[str]]:
    """R1's readable results and R3's unreadable ones, found at C2's one listing of the run's own directory — no walk
    above it, and never the deploy home. R4's dedupe is by phase name, consumed in (phase, round) order: the `phases`
    table holds no round column, so *this occurrence* is what is skipped, not the name outright — a `plan` row
    already on the ledger is skipped unopened, and a revision's own `plan-2` result is still recorded.

    Every candidate is validated through `adapter.result` (C1), never trusted as a dict — the ledger's rows are the
    wire's own dump, and an unvalidated one would drift from it. Nothing is reconstructed from `harness.json` or the
    stream (A1): `result.json` is the adapter's typed answer already, `blocks.jsonl` is the guard's own log (counted
    exactly as `container.py` counts it, because the harness reports no such field), and a judge's verdict artifact
    is read at the home-relative path the result itself names."""
    try:
        steps = sorted((p for p in (home / RUNS / run_id).iterdir() if p.is_dir()), key=lambda p: _step_of(p.name))
    except OSError:
        return [], []
    counts = Counter(str(p["phase"]) for p in held)
    recovered: list[Recovered] = []
    unreadable: list[str] = []
    for step in steps:
        phase, _round = _step_of(step.name)
        if counts[phase] > 0:
            counts[phase] -= 1
            continue
        result_path = step / RESULT
        if not result_path.is_file():
            continue
        offending = result_path.relative_to(home).as_posix()
        try:
            raw = json.loads(result_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("the container's result is not an object")
            # The artifact path frame, rebased exactly as `container._result` rebases it: run-directory-relative on
            # disk, deploy-home-relative on the record — the seam's one frame of reference.
            made = [
                {**a, "path": (step / str(a.get("path", ""))).relative_to(home).as_posix()}
                for a in raw.get("artifacts") or []
                if isinstance(a, dict)
            ]
            res = adapter_mod.result(
                {**raw, "artifacts": made, "guard_blocks": render.count_blocks(_lines(step / BLOCKS))}
            )
            verdict = None
            if res.phase == "judge" and res.outcome == "ok":
                # `runner.py`'s own derivation [F2], with one addition: the bytes are re-hashed against the
                # artifact's claimed `sha256` before the row is written, because the `verdicts` row stores that hash
                # as its `reasoning` ref and close must not record a hash it did not check.
                if not res.artifacts:
                    raise ValueError("a judge result answering ok names no verdict artifact")
                art = res.artifacts[0]
                offending = art.path
                data = (home / art.path).read_bytes()
                if artifacts_mod.sha256(data) != art.sha256:
                    raise Refusal("close.left-unreadable", art.path, f"the {art.name} does not hash to {art.sha256}")
                said = artifacts_mod.Verdict.model_validate_json(data)
                verdict = (said.verdict, art.sha256)
            recovered.append(Recovered(result=res, verdict=verdict))
        except (OSError, ValueError, Refusal) as e:
            unreadable.append(offending)
            telemetry.note("close.left-result", f"{offending}: {e}")
    return recovered, unreadable


def _record_left(ctx: TenantContext, ledger: Ledger, row: Mapping[str, Any], at: str) -> Left:
    """The recovery, in one door: every left result found and validated, written to the ledger before any end, and
    what the end needs back. Three choices, each true of the file it belongs to:

    (1) R2's asymmetry is close's to make, not `Ledger._end`'s (C3) — see `Left`'s own docstring.
    (2) `guard_blocks` is counted from the run directory's own `blocks.jsonl`, not taken from the result: the harness
    reports no such field, and a phase that scored its own denials could score none.
    (3) `touched` stays at the result's own default, `()`: the live path computes it from git in the phase's
    worktree at the moment the phase ended, and that moment is gone by close time — the tree may already be removed,
    or a dead host's left mid-flight, or a closing run's branch has since merged — so no honest recomputation
    exists. What the run touched is on the row as `surfaces_actual`, which R1 does not ask this to change."""
    run_id = str(row["run_id"])
    with telemetry.span(LEFT_SPAN, **{"isidium.run_id": run_id}) as sp:
        recovered, unreadable = _left_results(ctx.home, run_id, ledger.phases_of(run_id))
        for rec in recovered:
            ledger.phase(run_id, at, rec.result.row(), verdict=rec.verdict)
        sp.set_attribute(RECORDED, len(recovered))
        sp.set_attribute(UNREADABLE, len(unreadable))
        billing = None if row.get("billing_class") else (recovered[0].result.billing_class if recovered else None)
        return Left(
            billing_class=billing,
            recorded=tuple(r.result.phase for r in recovered),
            unreadable=tuple(unreadable),
        )


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
        at = _stamp(now())
        left = _record_left(ctx, ledger, row, at)
        ledger.end(
            run_id, at, ABANDONED, billing_class=left.billing_class, detail={"card_status": status, **left.detail()}
        )
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
    left = _record_left(ctx, ledger, row, at)
    detail.update(left.detail())
    detail["phases"] = [str(p["phase"]) for p in ledger.phases_of(run_id)]
    if failure is not None:
        ledger.end(run_id, at, f"failed:{failure}", billing_class=left.billing_class, detail=detail)
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
    ledger.end(
        run_id,
        at,
        CLOSED,
        store_events=(("complete", complete), ("closed", closed)),
        billing_class=left.billing_class,
        detail=detail,
    )
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
