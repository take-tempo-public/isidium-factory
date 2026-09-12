"""The execution adapter seam (T-C6) — the contract as types, the policy that crosses it, and the registry that
picks the one adapter a tenant's registration names [V4a-i, 2026-09-12].

T-C6's contract, verbatim: *"Same typed payload in; same typed phase outputs and close report out; the wrapper's
guarantees hold inside it — write guard at write time (T-B5), identity held by the wrapper not the model, budgets +
watchdog, end-and-resume on questions (T-C5), telemetry per phase"*; and its gate: *"An adapter is **registered only
after passing the conformance suite** (the same scenario runs) — the seam is verified by conformance, never by
trust."*

**Nothing in this module names an executor.** No forge, no store, no podman, no harness — the card's R1, and the
property the seam exists to have: what an adapter runs on is the adapter's business, and everything above the seam
is written once for all of them (7bdb.4(1): *"nothing above the seam names a harness"*). The absence is tested, not
asserted.

**Pydantic starts here.** `forge.py` said where: *"The values are frozen dataclasses, as the payload's are: the wire
is V4's seam, and pydantic wraps it there."* A `RunJob` leaves this process and a `PhaseResult` comes back from
another one, so both are closed pydantic models under the store's own convention — `extra="forbid"`, frozen, a
`ValidationError` caught at the boundary and re-raised as a `Refusal` naming what failed. The capability matrix and
the adapter's own handle stay frozen dataclasses: they never cross.

**The executor policy is declared once and rendered per adapter** (7bdb.4(2), and Q-V16 (b) ruled 2026-09-12): it
lives in the tenant's signed `config.toml` under `[agents]` and `[executor]` (config@6), is read here into one
`ExecutorPolicy`, and each adapter renders it into whatever its harness speaks. Neither harness's native form is
ever the source.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from isidium.store.core.refusal import Refusal

if TYPE_CHECKING:  # C-13: the registration is a type here, not a runtime import this module needs
    from .tenant import Registration

# The rule ids are written as literals at each raise, not as constants: the repo-wide sweep that fails the
# build on an unclassified namespace (C-12, `core/disclosure.py`) reads the literal at the raise site, so a
# constant here would hide the id from the one gate that exists to classify it. Found building V4a-i.

# The ratified story flow's phases (05's descends-from line: pick → consume → plan → light plan-refutation → judge →
# build → adversarial review → reconcile → close). `pick`, `consume` and `close` make no model calls and are not
# adapter work, so they are not here. V4a-i runs `build`; V4a-ii adds the other four.
Phase = Literal["plan", "refute", "judge", "build", "review", "reconcile"]

# What a phase can end as, at the amplitude V4a-i writes. `ok` is the phase done; `failed:infra` is T-C6's
# *"Adapter start/timeouts ⇒ `failed:infra`, one retry"*; `failed:scope` is T-B5's *"repeated beyond a tenant
# threshold"*; `parked` is T-C5's question. The close report's own outcomes (`met`, `disputed`) are V5's — a phase
# does not close a card.
Outcome = Literal["ok", "failed:infra", "failed:scope", "parked"]

Effort = Literal["low", "medium", "high", "xhigh", "max"]

# 7bdb.4(5): *"Telemetry carries `harness`, `harness_version`, `billing_class` (`plan` | `metered`) per run"* — the
# measurement that decides the ruled harness swap, so it is a field, not a guess.
BillingClass = Literal["plan", "metered"]

# T-C6 open (1), as data rather than a standing unknown (05 §3, owner-ratified 2026-08-27): `write-time` is the
# ceiling — the guard denies the write as it is attempted; `post-hoc` is the declared degradation for a runtime that
# cannot host the hook, and a tenant whose signed policy says so has said so out loud.
GuardMode = Literal["write-time", "post-hoc"]

CONTAINER: Final = "container"
REGISTERED: Final[frozenset[str]] = frozenset({CONTAINER})


class _Wire(BaseModel):
    """Closed, frozen, and aliased the way the store's own events are: an unknown key is a refusal, not a silent
    carry. Everything that crosses the seam inherits it."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class Budgets(_Wire):
    """T-A6's *"budgets"* and T-B5's *"budgets/watchdog"*, from `[executor]`. `max_tokens` absent is no ceiling —
    the run's own tokens are recorded either way (03 §6)."""

    max_turns: int = Field(ge=1)
    wall_clock_s: int = Field(ge=1)
    max_tokens: int | None = Field(default=None, ge=1)


class AgentSpec(_Wire):
    """One row of 05 §1a's table: which model runs this agent kind, at what effort."""

    model: str = Field(min_length=1)
    effort: Effort


class ExecutorPolicy(_Wire):
    """The executor policy, read once from the tenant's signed policy and rendered per adapter."""

    allowlist: tuple[str, ...] = Field(min_length=1)
    budgets: Budgets
    guard: GuardMode
    agents: Mapping[str, AgentSpec]

    @classmethod
    def from_effective(cls, eff: Mapping[str, Any]) -> ExecutorPolicy:
        """From the effective config — the tenant's file over its adopted schema's defaults. Every value here comes
        from that overlay and none from this code (Y1, C-1); a tenant still on config@5 has no `[executor]` table at
        all, and the refusal says which version declares one."""
        ex = eff.get("executor")
        agents = eff.get("agents")
        if not isinstance(ex, dict) or not isinstance(agents, dict):
            raise Refusal(
                "adapter.policy",
                "executor",
                "no [executor]/[agents] in the effective config: the tenant's policy adopts a config schema older "
                "than config@6, which is where the executor policy is declared",
            )
        try:
            return cls.model_validate(
                {
                    "allowlist": ex.get("allowlist", ()),
                    "budgets": {k: ex.get(k) for k in ("max_turns", "wall_clock_s", "max_tokens")},
                    "guard": ex.get("guard"),
                    "agents": agents,
                }
            )
        except ValidationError as e:
            raise Refusal("adapter.policy", "executor", _why(e)) from None

    def agent(self, kind: str) -> AgentSpec:
        """The row for one agent kind. A kind the policy does not carry is fail-closed: the run does not guess a
        model, because a guessed model is spend the owner did not sign."""
        spec = self.agents.get(kind)
        if spec is None:
            carried = sorted(self.agents)
            raise Refusal("adapter.policy", f"agents.{kind}", f"no row for {kind!r}; the policy carries {carried}")
        return spec


class RunIdentity(_Wire):
    """Who the phase runs as. The git author the **wrapper** commits under (T-B5 (4)) and the agent kind whose row
    in the policy names the model — and **no credential**: *"the model never holds git credentials"* (7j.5), and the
    builder holds no store credential at all (W9)."""

    agent: str = Field(min_length=1)
    name: str = Field(min_length=1)
    email: str = Field(min_length=1)


class RunJob(_Wire):
    """What crosses the seam inwards: one phase of one run, everything it may read, and the only paths it may write.

    `payload` is V1's assembled value verbatim — the card's gated set, its refs' excerpts, the neighborhood block,
    the constraints and the identity. `allowed_writes` is the guard's data: the card's `surfaces` ∪ the test paths
    (T-B5 (1)), resolved here and enforced at write time inside."""

    run_id: str = Field(min_length=1)
    card: int = Field(ge=1)
    phase: Phase
    payload: Mapping[str, Any]
    payload_hash: str = Field(min_length=1)
    worktree: str = Field(min_length=1)
    allowed_writes: tuple[str, ...] = Field(min_length=1)
    policy: ExecutorPolicy
    identity: RunIdentity
    prompt_version: str = Field(min_length=1)


class Artifact(_Wire):
    """A phase's output, by hash. T-B7 (3): *"every artifact referenced exists at its hash"* — so the hash is the
    reference, and a name without one has no place to live."""

    name: str = Field(min_length=1)
    sha256: str = Field(min_length=1)
    path: str = Field(min_length=1)


class Question(_Wire):
    """T-C5's typed question, assembled by the deterministic wrapper — the parked run's whole voice."""

    why_blocked: str = Field(min_length=1)
    source_tag: str = Field(min_length=1)
    artifacts_so_far: tuple[str, ...] = ()


class PhaseResult(_Wire):
    """What crosses the seam outwards: 03 §6's `phases[]` entry, plus what the harness measurement needs.

    `touched` is the adapter's claim about what the phase wrote; the wrapper does not believe it — it recomputes the
    set from git and refuses a result whose claim differs (the gajae follow-up, adopted 2026-08-21). Keeping the
    claim on the record is what makes the disagreement visible."""

    run_id: str = Field(min_length=1)
    phase: Phase
    agent: str = Field(min_length=1)
    model: str = Field(min_length=1)
    effort: Effort
    prompt_version: str = Field(min_length=1)
    tokens: int = Field(default=0, ge=0)
    cost_micro: int = Field(default=0, ge=0)
    duration_ms: int = Field(default=0, ge=0)
    artifacts: tuple[Artifact, ...] = ()
    guard_blocks: int = Field(default=0, ge=0)
    touched: tuple[str, ...] = ()
    outcome: Outcome
    question: Question | None = None
    harness: str = Field(min_length=1)
    harness_version: str = Field(min_length=1)
    billing_class: BillingClass

    def row(self) -> dict[str, Any]:
        """The ledger's `phases` row — the model's own dump, so the record and the wire cannot drift apart."""
        return self.model_dump(mode="json")


@dataclass(frozen=True)
class AdapterCapabilities:
    """The per-adapter capability matrix [owner-ratified 2026-08-27 (7be.3)]: *"every execution adapter declares what
    it preserves and what degrades as capability rows the conformance suite checks — declared degradation, never
    silent"*. Declared, never probed; the conformance suite is what checks a declaration against behaviour."""

    name: str
    harness: str
    harness_version: str
    write_guard_at_write_time: bool
    identity_held_by_wrapper: bool
    budgets: bool
    watchdog: bool
    end_and_resume: bool
    telemetry_per_phase: bool
    billing_class: BillingClass
    hosts: tuple[str, ...]


class Adapter(Protocol):
    """The seam: one call in, one typed result out, and a matrix that says what it preserves.

    There is no `close`, no `commit`, no `push` and no `land` — a phase produces a result and the wrapper does
    everything that touches the record, the branch or the forge. An adapter that cannot commit cannot be asked to.
    """

    def capabilities(self) -> AdapterCapabilities: ...
    def execute(self, job: RunJob) -> PhaseResult: ...


AdapterFactory = Callable[[Path, "Registration"], Adapter]


def resolve(name: str) -> AdapterFactory:
    """The card's R1: *"an adapter is chosen by the tenant's registration and nothing else"* — and T-C6's
    registration gate made mechanical, *"registered only after passing the conformance suite"*: an adapter that is
    not in `REGISTERED` cannot be selected, so passing conformance is what puts it here.

    The import is inside the branch on purpose (C-13): resolving a name must not drag in the machinery of an adapter
    this tenant does not run.
    """
    if name == CONTAINER:
        from .container import Container

        return Container
    known = sorted(REGISTERED)
    raise Refusal("adapter.unknown", "adapter", f"{name!r} is not a registered adapter; registered: {known}")


def job(raw: Mapping[str, Any]) -> RunJob:
    """One constructor for the inbound value, so a bad job is one refusal with the offending field named rather than
    a `ValidationError` escaping into a caller that cannot read it."""
    try:
        return RunJob.model_validate(dict(raw))
    except ValidationError as e:
        raise Refusal("adapter.job", "job", _why(e)) from None


def result(raw: Mapping[str, Any]) -> PhaseResult:
    """The outbound value, validated at the boundary it arrives at — the store's own posture for a wire union."""
    try:
        return PhaseResult.model_validate(dict(raw))
    except ValidationError as e:
        raise Refusal("adapter.result", "result", _why(e)) from None


def _why(e: ValidationError) -> str:
    """The offending fields, named — the refusal tells the caller about itself (C-12)."""
    return "; ".join(f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors())
