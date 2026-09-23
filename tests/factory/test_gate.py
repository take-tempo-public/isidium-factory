"""The plan gate as functions — `gate.lint`, `gate.next_step`, `gate.inputs_for` [V4a-ii-a, PR 3; ruled 2026-09-23].

Pure: no store, no ledger, no disk. Every path the gate can take is a row here, so a change to one rule fails the row
that states it rather than an end-to-end run that happens to cross it.
"""

from __future__ import annotations

from typing import Any

import pytest

from isidium.factory import artifacts, gate
from isidium.factory.gate import Done

PAYLOAD: dict[str, Any] = {
    "gated": {
        "acceptance": {"scenarios": [{"id": "S1"}, {"id": "S2"}]},
        "guidance": {"avoid": [{"id": "A1"}], "risks": [{"id": "K1"}], "constraints": [{"id": "C1"}]},
    },
    "constraints": {"surfaces": ["src/a.py", "tests/test_a.py"]},
}
PLAN: dict[str, Any] = {
    "steps": [{"id": "s1", "action": "edit a", "purpose": "R1"}],
    "touched": ["src/a.py"],
    "tests": [{"path": "tests/test_a.py", "scenario": "S1", "fails_today": "a is absent"}],
    "traceability": [
        {"id": "S1", "covered_by": ["tests/test_a.py"], "note": ""},
        {"id": "S2", "covered_by": ["s1"], "note": ""},
        {"id": "A1", "covered_by": [], "note": "nothing here edits the ledger"},
        {"id": "C1", "covered_by": ["s1"], "note": ""},
    ],
}
CLEAN: dict[str, Any] = {"findings": []}
BLOCKED: dict[str, Any] = {
    "findings": [{"id": "F1", "severity": "blocking", "claim": "S2 fails", "location": "S2", "why": "no test"}]
}
MINOR: dict[str, Any] = {"findings": [{"id": "F1", "severity": "minor", "claim": "c", "location": "l", "why": "w"}]}


def verdict(v: str) -> dict[str, Any]:
    return {"verdict": v, "reasoning": f"the judge said {v}"}


def plan(**over: Any) -> dict[str, Any]:
    return {**PLAN, **over}


def ids(p: dict[str, Any]) -> list[str]:
    return [f.id for f in gate.lint(artifacts.Plan.model_validate(p), PAYLOAD)]


def test_a_clean_plan_passes_the_lint() -> None:
    assert ids(PLAN) == []


def test_the_lint_refuses_every_mechanical_gap_at_once() -> None:
    """T-B4 (2) the surfaces subset; (3) every scenario mapped; the since-note: every `avoid` and `constraint` id
    referenced (a `risk` id need not be); and a `covered_by` that names nothing the plan contains. All at once, so
    the author's one revision answers every one."""
    rows = [r for r in PLAN["traceability"] if r["id"] not in ("S2", "C1")]
    bad = plan(
        touched=["src/a.py", "src/b.py"],
        traceability=[*rows, {"id": "S1", "covered_by": ["s9"], "note": ""}][1:],
    )
    got = ids(bad)
    assert "L-surface-1" in got and "L-scenario-S2" in got and "L-guidance-C1" in got and "L-ref-S1-s9" in got
    assert not any("K1" in g for g in got), "a risk id is not required in the matrix"
    assert all(f.severity == "blocking" for f in gate.lint(artifacts.Plan.model_validate(bad), PAYLOAD))


def test_a_scenario_in_the_matrix_with_nothing_covering_it_is_refused() -> None:
    rows = [r if r["id"] != "S2" else {**r, "covered_by": []} for r in PLAN["traceability"]]
    assert ids(plan(traceability=rows)) == ["L-scenario-S2"]


H = Done  # a shorter name for the history rows below

CASES: list[tuple[str, list[Done], tuple[str, str | None, str]]] = [
    ("nothing yet: plan", [], ("phase", "plan", "")),
    ("a clean plan: refute", [H("plan", PLAN)], ("phase", "refute", "")),
    (
        "a plan with questions parks at once",
        [H("plan", plan(questions=["which file?"]))],
        ("park", None, "card-ambiguity"),
    ),
    ("a linted plan, round 1: revise", [H("plan", plan(touched=["x.py"]))], ("phase", "plan", "")),
    (
        "a linted plan, round 2, outside the surfaces: card-ambiguity",
        [H("plan", plan(touched=["x.py"])), H("plan", plan(touched=["x.py"]))],
        ("park", None, "card-ambiguity"),
    ),
    (
        "a linted plan, round 2, inside the surfaces: plan-failed",
        [H("plan", plan(traceability=[])), H("plan", plan(traceability=[]))],
        ("park", None, "plan-failed"),
    ),
    ("refuted: judge", [H("plan", PLAN), H("refute", BLOCKED)], ("phase", "judge", "")),
    (
        "approved, nothing blocking: build",
        [H("plan", PLAN), H("refute", MINOR), H("judge", verdict("approve"))],
        ("phase", "build", ""),
    ),
    (
        "approved over a blocking finding: the floor revises",
        [H("plan", PLAN), H("refute", BLOCKED), H("judge", verdict("approve"))],
        ("phase", "plan", ""),
    ),
    (
        "revise, round 1: the one revision",
        [H("plan", PLAN), H("refute", CLEAN), H("judge", verdict("revise"))],
        ("phase", "plan", ""),
    ),
    (
        "the judge parks in round 1",
        [H("plan", PLAN), H("refute", CLEAN), H("judge", verdict("park"))],
        ("park", None, "plan-failed"),
    ),
    (
        "revise, round 2: no third plan, a park",
        [
            H("plan", PLAN),
            H("refute", CLEAN),
            H("judge", verdict("revise")),
            H("plan", PLAN),
            H("refute", CLEAN),
            H("judge", verdict("revise")),
        ],
        ("park", None, "plan-failed"),
    ),
    (
        "approved in round 2 over a blocking finding: the floor parks",
        [
            H("plan", PLAN),
            H("refute", BLOCKED),
            H("judge", verdict("revise")),
            H("plan", PLAN),
            H("refute", BLOCKED),
            H("judge", verdict("approve")),
        ],
        ("park", None, "plan-failed"),
    ),
    (
        "approved in round 2: build",
        [
            H("plan", PLAN),
            H("refute", BLOCKED),
            H("judge", verdict("revise")),
            H("plan", PLAN),
            H("refute", CLEAN),
            H("judge", verdict("approve")),
        ],
        ("phase", "build", ""),
    ),
    (
        "the build ran: done",
        [H("plan", PLAN), H("refute", CLEAN), H("judge", verdict("approve")), H("build", None)],
        ("done", None, ""),
    ),
]


@pytest.mark.parametrize(("name", "history", "want"), CASES, ids=[c[0] for c in CASES])
def test_the_gate_takes_the_ruled_path(name: str, history: list[Done], want: tuple[str, str | None, str]) -> None:
    step = gate.next_step(history, PAYLOAD)
    assert (step.kind, step.phase, step.source_tag) == want, name


def test_a_park_carries_the_judges_reasoning_as_why_blocked() -> None:
    history = [H("plan", PLAN), H("refute", CLEAN), H("judge", verdict("park"))]
    assert gate.next_step(history, PAYLOAD).why_blocked == "the judge said park"


def test_each_phase_is_handed_what_it_answers() -> None:
    """The refuter the plan; the judge the plan and its refutation; the build the plan it was approved on; the
    revision its own plan with what sent it back — the lint's findings, or the refutation and the verdict; and the
    second round's judge what the revision was answering."""

    def names(phase: str, history: list[Done]) -> list[str]:
        return [n for n, _ in gate.inputs_for(phase, history, PAYLOAD)]

    judged = [H("plan", PLAN), H("refute", BLOCKED), H("judge", verdict("revise"))]
    assert names("plan", []) == [] and names("refute", [H("plan", PLAN)]) == ["plan"]
    assert names("judge", [H("plan", PLAN), H("refute", CLEAN)]) == ["plan", "refutation"]
    assert names("plan", judged) == ["plan", "refutation", "verdict"]
    linted = [H("plan", plan(touched=["x.py"]))]
    assert names("plan", linted) == ["plan", "lint"]
    lint = dict(gate.inputs_for("plan", linted, PAYLOAD))["lint"]
    assert [f["id"] for f in lint["findings"]] == ["L-surface-1"]
    second = [*judged, H("plan", PLAN), H("refute", CLEAN)]
    assert names("judge", second) == ["plan", "refutation", "answered-refutation"]
    assert dict(gate.inputs_for("judge", second, PAYLOAD))["answered-refutation"] == BLOCKED
    assert names("build", [*second, H("judge", verdict("approve"))]) == ["plan"]
