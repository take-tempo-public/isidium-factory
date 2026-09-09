"""The acceptance manifest (03 §4.4; T-B2) — the card's acceptance block compiled, deterministically, to what runs
[L3, 2026-09-09].

*"Manifest = a deterministic function of (build hash, config hash): per scenario → `{scenario_id, rule_id?, kind,
runner, params, tests[]}` or `manual`. Unbindable ⇒ a typed compile error naming the scenario."* Pure: no I/O, no
clock, no environment — the same block and the same bindings give the same manifest and the same hash, which is
T-B2's condition 2 and the reason this lives in `core/` beside the hashers rather than in the client: `accept` (the
owner's terminal, 03 §1.13) consumes it now; the factory's run (T-A9) and verification (T-A12) consume the same
function when v1c opens, *"one artifact, both consumers."*

The per-kind shapes are `registry/shapes.py`'s `Scenario` union (03 §4.2), parsed here so a scenario that does not fit
its kind is `scenario.shape` — the validator's own id — before anything is bound. The binding is `config.toml
[runners]`: scenario kind → runner id, the four the schema ships by default; a kind with no binding, or a binding
naming a runner the toolkit does not ship, is `accept.unbindable` naming the scenario — the dry run's
`config.runner-unshipped` is the same fact seen from the other door.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from typing import Any, Final

from pydantic import TypeAdapter, ValidationError

from ..registry.shapes import Scenario
from .refusal import Refusal

# scenario kind → the `[runners]` key that binds it (04 §2.2: `test`, `command`, `http`, `file`)
BINDING_KEY: Final[Mapping[str, str]] = {
    "test-marker": "test",
    "command": "command",
    "http": "http",
    "file-assert": "file",
}

_SCENARIO: Final[TypeAdapter[Scenario]] = TypeAdapter(Scenario)


@dataclass(frozen=True)
class Check:
    """One runnable scenario: what to hand the runner named."""

    scenario_id: str
    kind: str
    runner: str
    params: Mapping[str, Any]
    tests: tuple[str, ...] = ()
    rule_id: str | None = None


@dataclass(frozen=True)
class Manual:
    """A `manual-evidence` scenario: nothing runs; the verdict is a human's."""

    scenario_id: str
    evidence: str
    rule_id: str | None = None


@dataclass(frozen=True)
class Manifest:
    entries: tuple[Check | Manual, ...] = field(default_factory=tuple)

    @property
    def hash(self) -> str:
        """`sha256:` over the canonical JSON — sorted keys, no whitespace — so the hash is the manifest's content and
        nothing about how it was built."""
        return (
            "sha256:"
            + hashlib.sha256(json.dumps(self.as_json(), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        )

    def as_json(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for e in self.entries:
            if isinstance(e, Check):
                out.append(
                    {
                        "scenario_id": e.scenario_id,
                        "kind": e.kind,
                        "runner": e.runner,
                        "params": dict(e.params),
                        "tests": list(e.tests),
                        "rule_id": e.rule_id,
                    }
                )
            else:
                out.append({"scenario_id": e.scenario_id, "manual": e.evidence, "rule_id": e.rule_id})
        return out

    @property
    def runnable(self) -> tuple[Check, ...]:
        return tuple(e for e in self.entries if isinstance(e, Check))


def compile_acceptance(acceptance: Mapping[str, Any], runners: Mapping[str, Any], shipped: Collection[str]) -> Manifest:
    """The block against the bindings: `shipped` is the set of runner ids the toolkit carries."""
    entries: list[Check | Manual] = []
    for raw in acceptance.get("scenarios") or []:
        sid = str(raw.get("id", "?")) if isinstance(raw, Mapping) else "?"
        try:
            sc = _SCENARIO.validate_python(dict(raw) if isinstance(raw, Mapping) else raw)
        except ValidationError as e:
            first = e.errors()[0]
            raise Refusal("scenario.shape", f"acceptance.scenarios.{sid}", first["msg"]) from None
        if sc.kind == "manual-evidence":
            entries.append(Manual(sc.id, sc.observable.evidence, sc.rule))
            continue
        key = BINDING_KEY[sc.kind]
        runner = runners.get(key)
        if not isinstance(runner, str) or runner not in shipped:
            raise Refusal(
                "accept.unbindable",
                f"acceptance.scenarios.{sc.id}",
                f"kind {sc.kind} binds [runners].{key} = {runner!r}, and the toolkit ships {sorted(shipped)}",
            )
        params = sc.model_dump(exclude_none=True, exclude={"id", "kind", "title", "rule", "traces", "tests"})
        if sc.kind == "http" and not (sc.context and sc.context.base_url):
            raise Refusal(
                "accept.unbindable", f"acceptance.scenarios.{sc.id}", "an http scenario needs context.base_url"
            )
        if sc.kind == "command" and not any(
            getattr(sc.observable, k) is not None for k in ("exit_code", "stdout_matches", "stderr_matches", "files")
        ):
            raise Refusal("accept.unbindable", f"acceptance.scenarios.{sc.id}", "a command scenario observes nothing")
        if sc.kind == "test-marker" and sc.observable.test is None and sc.observable.marker is None:
            raise Refusal("accept.unbindable", f"acceptance.scenarios.{sc.id}", "a test-marker names no test or marker")
        entries.append(Check(sc.id, sc.kind, runner, params, tuple(sc.tests or ()), sc.rule))
    return Manifest(tuple(entries))
