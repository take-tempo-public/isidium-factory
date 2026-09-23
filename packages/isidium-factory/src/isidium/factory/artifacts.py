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
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field


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


class Plan(_Artifact):
    steps: tuple[Step, ...] = Field(min_length=1)
    touched: tuple[str, ...] = Field(min_length=1)  # required (T-B4): feeds the build's write guard
    tests: tuple[PlannedTest, ...] = ()
    traceability: tuple[Trace, ...] = ()
    risks: tuple[str, ...] = ()
    questions: tuple[str, ...] = ()


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


# The phase → the artifact it answers with, by name. A phase absent here answers with no artifact (the build's work is
# its commit). One table, read by the harness (which schema to pass) and the wrapper (what to expect back).
OF_PHASE: Final[Mapping[str, tuple[str, type[_Artifact]]]] = {
    "plan": ("plan", Plan),
    "refute": ("refutation", Refutation),
    "judge": ("verdict", Verdict),
}

# What each phase is handed from the phases before it, by artifact name — the plan to the refuter; the plan and its
# refutation to the judge (both prompts' "What you are given").
INPUTS: Final[Mapping[str, tuple[str, ...]]] = {
    "refute": ("plan",),
    "judge": ("plan", "refutation"),
}


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
