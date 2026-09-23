"""The plan gate — T-B4, as functions of the run's history [V4a-ii-a, PR 3 of 3].

The gate decides nothing a model decides and runs no model. Given what the run's phases have produced so far — the
plans, the refutations, the verdicts, in the order the ledger holds them — and the card's payload, `next_step` names
what happens next: a phase to run, a park, or nothing (the line's end so far). The same history gives the same step,
so a chain resumed from the ledger takes the path it would have taken uninterrupted.

The rules, each where it was ruled:

* **The lint is a function, before any refuter or judge call** (05 §3 M-3): the plan's `touched` ⊆ the card's
  `surfaces` (T-B4 (2)); every acceptance scenario mapped to a step or a test (T-B4 (3)); every `avoid` and
  `constraint` guidance id referenced (T-B4's since-note); every `covered_by` naming a step or a planned test. A
  refused plan goes back to its author **once** — the same one revision a blocking finding buys — and a second refused
  plan parks. A plan reaching outside the card's surfaces is one of these refusals, not an immediate park [owner,
  2026-09-23].
* **A plan with `questions` parks at once**, before any refuter or judge call, `card-ambiguity` [owner, 2026-09-23]:
  the author saying the card cannot be planned without the owner (the plan author's prompt §4).
* **The floor** (T-B4 (5), 7bd.13): any `blocking` finding ⇒ revise, whatever the judge said. The judge is still
  called on a blocked round [owner, 2026-09-23] — its `revise` tells the author what must change — and its verdict is
  recorded as it said it; the floor is applied here, not written over its verdict.
* **Exactly one revision.** On the second round the judge's `approve` proceeds to the build and anything else parks
  (7bd.10: the second failure parks, the judge's reasoning its `why_blocked`). There is no third plan.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, Literal

from . import artifacts

PLAN_FAILED: Final = "plan-failed"
CARD_AMBIGUITY: Final = "card-ambiguity"
SURFACE: Final = "L-surface"  # the lint finding id prefix for a touched path outside the card's surfaces


@dataclass(frozen=True)
class Done:
    """One phase the ledger holds, with the artifact it answered with (already re-hashed by the caller)."""

    phase: str
    artifact: Mapping[str, Any] | None


@dataclass(frozen=True)
class Step:
    kind: Literal["phase", "park", "done"]
    phase: str | None = None
    source_tag: str = ""
    question: str = ""
    why_blocked: str = ""


def lint(plan: artifacts.Plan, payload: Mapping[str, Any]) -> tuple[artifacts.Finding, ...]:
    """The plan's mechanical checks, every refusal at once, each a `blocking` finding the author can answer."""
    gated: Mapping[str, Any] = payload.get("gated") or {}
    surfaces = set((payload.get("constraints") or {}).get("surfaces") or ())
    scenarios = [str(s["id"]) for s in (gated.get("acceptance") or {}).get("scenarios") or ()]
    guidance: Mapping[str, Any] = gated.get("guidance") or {}
    guided = [str(g["id"]) for key in ("avoid", "constraints") for g in guidance.get(key) or ()]
    out: list[artifacts.Finding] = []

    def refuse(fid: str, claim: str, location: str, why: str) -> None:
        out.append(artifacts.Finding(id=fid, severity="blocking", claim=claim, location=location, why=why))

    for i, path in enumerate(p for p in plan.touched if p not in surfaces):
        refuse(
            f"{SURFACE}-{i + 1}",
            f"the plan touches {path}, which the card does not declare",
            path,
            f"touched must be a subset of the card's surfaces {sorted(surfaces)}; a card that cannot be built inside "
            "them is a question, never a wider plan (T-B4 (2))",
        )
    names = {s.id for s in plan.steps} | {t.path for t in plan.tests}
    rows = {t.id: t for t in plan.traceability}
    for sid in scenarios:
        row = rows.get(sid)
        if row is None or not row.covered_by:
            refuse(
                f"L-scenario-{sid}", f"scenario {sid} maps to no step or test", sid, "T-B4 (3): traceability complete"
            )
    for gid in guided:
        if gid not in rows:
            refuse(
                f"L-guidance-{gid}",
                f"guidance {gid} is not referenced",
                gid,
                "every avoid and constraint guidance id is answered — followed, or said not to bite and why",
            )
    for row in plan.traceability:
        for ref in row.covered_by:
            if ref not in names:
                refuse(
                    f"L-ref-{row.id}-{ref}",
                    f"{row.id} is covered by {ref}, which is no step id and no planned test path",
                    row.id,
                    "a matrix row must point at something the plan contains",
                )
    return tuple(out)


def next_step(history: Sequence[Done], payload: Mapping[str, Any]) -> Step:
    """What happens next, from what has happened. See the module docstring for the rules."""
    if not history:
        return Step("phase", "plan")
    last = history[-1]
    rounds = sum(1 for d in history if d.phase == "plan")
    if last.phase == "plan":
        plan = artifacts.Plan.model_validate(last.artifact)
        if plan.questions:
            return Step(
                "park",
                source_tag=CARD_AMBIGUITY,
                question="; ".join(plan.questions),
                why_blocked="the plan author found questions the card does not answer",
            )
        refused = lint(plan, payload)
        if not refused:
            return Step("phase", "refute")
        if rounds == 1:
            return Step("phase", "plan")
        outside = any(f.id.startswith(SURFACE) for f in refused)
        return Step(
            "park",
            source_tag=CARD_AMBIGUITY if outside else PLAN_FAILED,
            question="the revised plan still fails the plan check: " + "; ".join(f.claim for f in refused),
            why_blocked="the plan failed its mechanical check twice",
        )
    if last.phase == "refute":
        return Step("phase", "judge")
    if last.phase == "judge":
        verdict = artifacts.Verdict.model_validate(last.artifact)
        refutation = _latest(history, "refute")
        blocked = refutation is not None and any(
            f.severity == "blocking" for f in artifacts.Refutation.model_validate(refutation).findings
        )
        if verdict.verdict == "approve" and not blocked:
            return Step("phase", "build")
        if rounds == 1 and verdict.verdict != "park":
            return Step("phase", "plan")
        return Step(
            "park",
            source_tag=PLAN_FAILED,
            question="the plan did not pass the gate; the judge's account is attached",
            why_blocked=verdict.reasoning,
        )
    return Step("done")  # the build ran: the review gate is V4a-ii-b's


def inputs_for(phase: str, history: Sequence[Done], payload: Mapping[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """What each phase reads, by name — the plan to the refuter; the plan and its refutation to the judge; the plan to
    the builder; and to the plan author's one revision, its own plan with whatever sent it back: the lint's findings, or
    the refutation and the verdict. A judge on the second round also sees what the revision was answering."""
    plan = _latest(history, "plan")
    named: list[tuple[str, dict[str, Any] | None]] = []
    if phase == "refute" or phase == "build":
        named = [("plan", plan)]
    elif phase == "judge":
        named = [("plan", plan), ("refutation", _latest(history, "refute"))]
        earlier = _answered(history, payload)
        if earlier is not None:
            named.append(earlier)
    elif phase == "plan" and plan is not None:
        named = [("plan", plan)]
        if _latest(history, "judge") is not None:
            named += [("refutation", _latest(history, "refute")), ("verdict", _latest(history, "judge"))]
        else:
            named.append(("lint", _lint_doc(plan, payload)))
    return [(n, v) for n, v in named if v is not None]


def _answered(history: Sequence[Done], payload: Mapping[str, Any]) -> tuple[str, dict[str, Any]] | None:
    """On the second round, what the revision answered: round one's refutation, or its lint (recomputed — it is a
    function of the first plan and the card, both on the record)."""
    plans = [i for i, d in enumerate(history) if d.phase == "plan"]
    if len(plans) < 2:
        return None
    first = history[: plans[1]]
    refuted = _latest(first, "refute")
    if refuted is not None:
        return ("answered-refutation", refuted)
    first_plan = _latest(first, "plan")
    return None if first_plan is None else ("answered-lint", _lint_doc(first_plan, payload))


def _lint_doc(plan: Mapping[str, Any], payload: Mapping[str, Any]) -> dict[str, Any]:
    found = lint(artifacts.Plan.model_validate(plan), payload)
    return {"findings": [f.model_dump(mode="json") for f in found]}


def _latest(history: Sequence[Done], phase: str) -> dict[str, Any] | None:
    for d in reversed(history):
        if d.phase == phase and d.artifact is not None:
            return dict(d.artifact)
    return None
