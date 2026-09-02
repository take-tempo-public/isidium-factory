"""The discriminated shapes the nine-member constraint vocabulary deliberately cannot say (04 §4: *"what the nine
cannot say, a schema cannot require"*) — authored here, once, as the source the three targets share: `narrative`
per shape (03 §1.11), the acceptance scenarios per kind (§4.2), `guidance` (§1.10), `closures` / `reopens` (§2.1),
`hold` (§1.8) and the `Ref` act payload (§1.15).

Two models, stated (W10): these typed models are **validated, never hashed** — the raw value tree is what the hasher
sees, so absent-vs-default and absent-vs-empty survive (`model_dump(exclude_unset=True)` is the one dump used).
Pydantic v2 here; the same shapes are the Rust enums and the TypeScript unions.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel

Id = Annotated[int, Field(ge=1)]


class Strict(BaseModel):
    """Every shape is closed: an unknown key is a refusal, not a silent carry (1.7's closed membership)."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


# ---- narrative, per shape (1.11) -----------------------------------------------------------------------------------


class BddNarrative(Strict):
    feature: str
    as_a: str | None = None
    i_want: str | None = None
    so_that: str | None = None


class EarsNarrative(Strict):
    system: str


class ClassicNarrative(Strict):
    as_a: str
    i_want: str
    so_that: str


class TaskNarrative(Strict):
    pass


class SpikeNarrative(Strict):
    question: str
    timebox: str  # `Sessions(n)` as "3 sessions" | ISO-8601 duration — the two forms of 1.11
    deliverable: str


# ---- acceptance scenarios, per kind (4.2) ---------------------------------------------------------------------------


class FileCheck(Strict):
    """Exactly one check beside `path` (4.2)."""

    path: str
    exists: bool | None = None
    contains: str | None = None
    matches: str | None = None
    sha256: str | None = None
    equals_file: str | None = None


class TestMarkerObservable(Strict):
    test: str | None = None
    marker: str | None = None


class CommandContext(Strict):
    fixture: str | None = None
    cwd: str | None = None
    env: dict[str, str] | None = None


class CommandAction(Strict):
    run: list[str]  # an argv array only (4.2); a string is a typed error


class CommandObservable(Strict):
    exit_code: int | None = None
    stdout_matches: str | None = None
    stderr_matches: str | None = None
    files: list[FileCheck] | None = None


class HttpContext(Strict):
    fixture: str | None = None
    base_url: str | None = None


class HttpAction(Strict):
    method: str
    path: str
    body: str | dict[str, Any] | None = None


class HttpObservable(Strict):
    status: int | None = None
    body_matches: str | None = None
    headers: dict[str, str] | None = None


class FileAssertContext(Strict):
    fixture: str | None = None


class FileAssertAction(Strict):
    run: list[str] | None = None


class ManualObservable(Strict):
    evidence: str


class TestMarkerScenario(Strict):
    id: str
    kind: Literal["test-marker"]
    title: str
    rule: str | None = None
    traces: str | None = None
    observable: TestMarkerObservable
    tests: list[str] | None = None


class CommandScenario(Strict):
    id: str
    kind: Literal["command"]
    title: str
    rule: str | None = None
    traces: str | None = None
    context: CommandContext | None = None
    action: CommandAction
    observable: CommandObservable
    tests: list[str] | None = None


class HttpScenario(Strict):
    id: str
    kind: Literal["http"]
    title: str
    rule: str | None = None
    traces: str | None = None
    context: HttpContext | None = None
    action: HttpAction
    observable: HttpObservable
    tests: list[str] | None = None


class FileAssertScenario(Strict):
    id: str
    kind: Literal["file-assert"]
    title: str
    rule: str | None = None
    traces: str | None = None
    context: FileAssertContext | None = None
    action: FileAssertAction | None = None
    observable: FileCheck
    tests: list[str] | None = None


class ManualScenario(Strict):
    id: str
    kind: Literal["manual-evidence"]
    title: str
    rule: str | None = None
    traces: str | None = None
    context: str | None = None
    action: str | None = None
    observable: ManualObservable
    tests: list[str] | None = None


Scenario = Annotated[
    TestMarkerScenario | CommandScenario | HttpScenario | FileAssertScenario | ManualScenario,
    Field(discriminator="kind"),
]


class Acceptance(Strict):
    scenarios: list[Scenario]
    manual_attestation: Literal["interrupt", "human-closure-only"] | None = None


# ---- guidance (1.10), rules and questions ---------------------------------------------------------------------------


class ConstraintCheck(Strict):
    kind: Literal["test-marker", "command", "http", "file-assert", "manual-evidence"]
    context: dict[str, Any] | None = None
    action: dict[str, Any] | None = None
    observable: dict[str, Any]


class Avoid(Strict):
    id: str
    option: str
    because: str


class Risk(Strict):
    id: str
    risk: str
    mitigation: str


class Constraint(Strict):
    id: str
    text: str
    because: str | None = None
    check: ConstraintCheck | None = None


class Guidance(Strict):
    avoid: list[Avoid] | None = None
    risks: list[Risk] | None = None
    constraints: list[Constraint] | None = None


class Rule(Strict):
    id: str
    text: str


class Question(Strict):
    id: str
    text: str


class Answer(Strict):
    question_id: str
    text: str


# ---- claims (2.1) ----------------------------------------------------------------------------------------------------


class Deviated(Strict):
    description: str


class DeviatedOutcome(Strict):
    deviated: Deviated


class Closure(Strict):
    id: str
    kind: Literal["human"]  # `factory` exists only in the sidecar; `migrated` reserved, rejected in v1
    outcome: Literal["met"] | DeviatedOutcome
    verdicts: dict[str, Literal["pass", "fail", "manual"]] | None = None
    evidence: list[str] = Field(default_factory=list)
    retracted: bool  # always written (§11 decision 11)


class Reopen(Strict):
    id: str
    closure_id: str
    reason: str


# ---- hold (1.8): a one-key table, never a string with a grammar inside ---------------------------------------------


class HoldOnOwner(Strict):
    owner: Literal[True]


class HoldOnCard(Strict):
    card: Id


class HoldOnLegacy(Strict):
    legacy: str


class HoldOnText(Strict):
    text: str


HoldOn = HoldOnOwner | HoldOnCard | HoldOnLegacy | HoldOnText


class Hold(Strict):
    kind: Literal["blocked", "deferred", "watching"]
    on: HoldOn | None = None  # optional for `watching` only (the profile checks it)


class SourceNarrative(Strict):
    path: str
    anchor: str


# ---- the act payload `ref` (1.15) — the discriminated shape behind the written forms ---------------------------------


class ClosureRef(Strict):
    """`"c<n>:sha256:<hex>"` / `"o<n>:sha256:<hex>"` — a judging entry binds the one claim it judges (5.2)."""

    id: str
    hash: str

    def written(self) -> str:
        return f"{self.id}:sha256:{self.hash}"


class RestartFrom(RootModel[int]):
    """`repaired` — the `seq` whose `h` the chain resumes from (5.5)."""


class Members(RootModel[list[str]]):
    """`batch-manifest` — the sitting's sorted member chain hashes (5.6)."""


class Binding(Strict):
    """The realm's record (1.12); `until` absent while the binding is open, never null."""

    key_fpr: str
    grant: Literal["owner", "contributor", "lander"]
    tenant: str
    from_: str = Field(alias="from")
    until: str | None = None
