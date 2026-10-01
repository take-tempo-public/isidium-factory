"""The plan gate's artifacts, typed — the plan, the refutation and the verdict [V4a-ii-a, T-B4].

T-B4 (the catalog's 2.19): *"A **plan** through its template: steps; **touched surfaces** (required …); tests to
add/modify (from the manifest); a **traceability matrix** scenario → step/test; risks; questions"*, the matrix also
*"reference[s] every `avoid` and `constraint` guidance id in the payload"*; *"A **refutation** through its template:
typed findings {severity: blocking / major / minor, claim, location, why}"*; and 03 §6's verdict *"∈ {approve,
revise, park}"* with its reasoning.

**Each is the answer to one structured model call.** The JSON Schema rendered here is handed to the harness
(`--json-schema`), which validates the answer itself and re-asks the model inside the call when it does not conform
(measured 2026-09-23). A call that ends with no conforming answer ends the run `failed:malformed-plan` — T-B4 (1)'s
class for every model call of the plan gate, the in-call re-asking being its one retry [owner, 2026-09-23]. The model
here validates the answer a second time on the wrapper's side of the seam, because a schema the harness enforced is
still the harness's claim.

An artifact lands in the run directory as `<name>.json`, canonical bytes, and is referenced by its `sha256` (T-B7
(3): *"every artifact referenced exists at its hash"*). It is handed to the next phase inline in the job and
re-hashed before it is — never copied into the store.

T-B4's `questions` is typed from card 18 (`Question`): a question carries whether it is blocking and, when it is
not, the assumption the plan made in its place. A bare string — every plan artifact's form before card 18 — reads
as blocking, so a chain resumed over an older plan takes the path it took.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Artifact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Step(_Artifact):
    id: str = Field(min_length=1)
    action: str = Field(min_length=1)
    purpose: str = Field(min_length=1)  # "a step whose purpose is not written is a step the refuter cannot check"


class PlannedTest(_Artifact):
    path: str = Field(min_length=1)
    scenario: str = Field(min_length=1)
    fails_today: str = Field(min_length=1)  # what makes it fail on the code as it stands — or it proves nothing


class Trace(_Artifact):
    """One row of the matrix: an acceptance scenario, or an `avoid` / `constraint` guidance id, and the steps or
    tests that answer it. `note` carries why a constraint does not bite, when that is the answer."""

    id: str = Field(min_length=1)
    covered_by: tuple[str, ...] = ()
    note: str = ""


class Question(_Artifact):
    """A plan's question, typed since card 18 (T-B4's `questions`): what it asks, whether the card cannot be
    planned without the owner's answer, and — when it can — the reading the plan took in its place. `blocking` is
    required (a default would put the policy in the binary, C-1); `assumption` is required exactly when the
    question is not blocking (R1). A bare string, every plan artifact's form before this card, reads as `blocking`
    with no assumption (R4), so a chain resumed over an older plan takes the path it took."""

    text: str = Field(min_length=1)
    blocking: bool = Field(description="whether the card cannot be planned without the owner's answer")
    assumption: str = Field(
        default="",
        description="the reading the plan took in place of an answer; required exactly when blocking is false",
    )

    @model_validator(mode="before")
    @classmethod
    def _bare_string_reads_as_blocking(cls, value: Any) -> Any:
        """R4: a question written as a bare string is an older plan's, and it parked at once before this card — so
        it still does, and a chain resumed over it takes the path it took."""
        return {"text": value, "blocking": True, "assumption": ""} if isinstance(value, str) else value

    @model_validator(mode="after")
    def _non_blocking_carries_its_assumption(self) -> Question:
        if not self.blocking and not self.assumption:
            raise ValueError("a non-blocking question must carry the assumption the plan made in its place (R1)")
        return self


class Plan(_Artifact):
    steps: tuple[Step, ...] = Field(min_length=1)
    touched: tuple[str, ...] = Field(min_length=1)  # required (T-B4): feeds the build's write guard
    tests: tuple[PlannedTest, ...] = ()
    traceability: tuple[Trace, ...] = ()
    risks: tuple[str, ...] = ()
    questions: tuple[Question, ...] = ()


class Finding(_Artifact):
    id: str = Field(min_length=1)
    severity: Literal["blocking", "major", "minor"]
    claim: str = Field(min_length=1)
    location: str = Field(min_length=1)
    why: str = Field(min_length=1)


class Refutation(_Artifact):
    findings: tuple[Finding, ...] = ()  # the empty set is a real answer: "tried, and could not"


class Verdict(_Artifact):
    verdict: Literal["approve", "revise", "park"]
    reasoning: str = Field(min_length=1)


# ---- the review gate [V4a-ii-b, owner-ruled 2026-09-25/27] -------------------------------------------------------
#
# The flow, ruled: the **reviewer** reads the build and files `Findings`, writing nothing; any `blocking` finding sends
# the run to **reconcile**, where the **builder** fixes or refutes each one and answers a `ReconcileReport`; the
# reviewer's **second pass**, bounded to those findings, answers a `Ruling` per finding. A finding still asserted after
# it parks the run (`review-disputed`); none does → the chain goes on to its end. The review's outcome lives on these
# artifacts and the run's outcome, never in `verdicts[]`, which stays the judge's (ruling 3).


class ReviewFinding(Finding):
    """A reviewer's finding: the refuter's shape plus what it bears on (T-B6 (1)–(2)) — the scenario, rule or guidance
    id it reads against, so a finding is traceable to the card the way a plan's matrix row is."""

    bears_on: str = Field(min_length=1, description="the card's scenario, rule or guidance id it reads against")


class Findings(_Artifact):
    findings: tuple[ReviewFinding, ...] = ()  # empty is a real answer: reviewed, nothing found — reconcile skipped

    @property
    def blocking(self) -> tuple[ReviewFinding, ...]:
        return tuple(f for f in self.findings if f.severity == "blocking")


class Reconciled(_Artifact):
    id: str = Field(min_length=1, description="the finding's id, as the reviewer filed it")
    disposition: Literal["fixed", "refuted", "deferred-as-suggestion"]
    note: str = Field(min_length=1, description="what was changed, why the finding is wrong, or what is deferred")


class ReconcileReport(_Artifact):
    """The builder's answer in reconcile: one row per blocking finding it was handed (T-B6: *"fixed | refuted |
    deferred-as-suggestion"*). That every blocking finding is answered is checked against the findings by
    `unanswered`, a function — the schema cannot see the findings."""

    rows: tuple[Reconciled, ...] = Field(min_length=1)

    def unanswered(self, findings: Findings) -> tuple[str, ...]:
        answered = {r.id for r in self.rows}
        return tuple(f.id for f in findings.blocking if f.id not in answered)


class Ruled(_Artifact):
    id: str = Field(min_length=1, description="the finding's id")
    ruling: Literal["concur", "still-asserted"]
    reason: str = Field(min_length=1)


class Ruling(_Artifact):
    """The reviewer's second pass, bounded to the reconciled findings: concur with each fix or refutation, or say the
    finding still stands. Any `still-asserted` parks the run `review-disputed` [owner, 2026-09-25]."""

    rulings: tuple[Ruled, ...] = Field(min_length=1)

    @property
    def disputed(self) -> tuple[str, ...]:
        return tuple(r.id for r in self.rulings if r.ruling == "still-asserted")


# The phase → the artifact it answers with, by name. A phase absent here answers with no artifact (the build's work is
# its commit). One table, read by the harness (which schema to pass) and the wrapper (what to expect back).
OF_PHASE: Final[Mapping[str, tuple[str, type[_Artifact]]]] = {
    "plan": ("plan", Plan),
    "refute": ("refutation", Refutation),
    "judge": ("verdict", Verdict),
}

# The review gate's answers, by phase — **not yet read by the harness or the wrapper** (V4a-ii-b PR 1 of 3 types them;
# PR 2 drives the chain past the build and switches both readers to `artifact_of`). Kept out of `OF_PHASE` until then,
# because the wrapper refuses an `ok` phase that does not answer with the artifact `OF_PHASE` names, and the review
# phase reachable today (`run_phase(phase="review")`) answers with none.
OF_REVIEW_GATE: Final[Mapping[str, tuple[str, type[_Artifact]]]] = {
    "review": ("findings", Findings),
    "reconcile": ("reconcile-report", ReconcileReport),
}

# A phase whose later round answers with a different artifact than its first: the review's second pass is the same
# agent, phase and prompt, bounded to the reconciled findings, and it rules rather than finds.
OF_LATER_ROUND: Final[Mapping[str, tuple[str, type[_Artifact]]]] = {
    "review": ("ruling", Ruling),
}


def artifact_of(phase: str, round_: int = 1) -> tuple[str, type[_Artifact]] | None:
    """The artifact a phase answers with in this round, or None for a phase that answers with its commit."""
    if round_ > 1 and phase in OF_LATER_ROUND:
        return OF_LATER_ROUND[phase]
    return OF_PHASE.get(phase) or OF_REVIEW_GATE.get(phase)


# What a phase cannot run without, by artifact name — the plan for the refuter; the plan and its refutation for the
# judge (both prompts' "What you are given"). What each is actually handed is `gate.inputs_for`'s, from the history.
INPUTS: Final[Mapping[str, tuple[str, ...]]] = {
    "refute": ("plan",),
    "judge": ("plan", "refutation"),
}


class ParkQuestion(_Artifact):
    """T-C5's typed question, all nine fields: `{run_id, card_id, phase, question, options?, tried, why_blocked,
    source_tag, artifacts_so_far}` — assembled by the wrapper when the plan gate parks, the reasoning in
    `why_blocked` and the run's artifacts by hash in `artifacts_so_far`."""

    run_id: str = Field(min_length=1)
    card_id: int = Field(ge=1)
    phase: str = Field(min_length=1)
    question: str = Field(min_length=1)
    options: tuple[str, ...] = ()
    tried: tuple[str, ...] = ()
    why_blocked: str = Field(min_length=1)
    source_tag: str = Field(min_length=1)
    artifacts_so_far: tuple[str, ...] = ()


def schema(model: type[_Artifact]) -> dict[str, Any]:
    """The model's JSON Schema with every `$ref` inlined. Deterministic, so the same model is the same argument on
    every run; inlined because the harness's acceptance of `$defs` was never measured, and a schema without references
    cannot depend on it."""
    raw = model.model_json_schema()
    defs: Mapping[str, Any] = raw.pop("$defs", {})

    def inline(node: Any) -> Any:
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/$defs/"):
                return inline(defs[ref.removeprefix("#/$defs/")])
            return {k: inline(v) for k, v in node.items()}
        if isinstance(node, list):
            return [inline(v) for v in node]
        return node

    out: dict[str, Any] = inline(raw)
    return out


def canonical(value: Mapping[str, Any]) -> bytes:
    """The bytes an artifact is stored and hashed as: sorted keys, no insignificant whitespace, UTF-8, a final LF."""
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()
