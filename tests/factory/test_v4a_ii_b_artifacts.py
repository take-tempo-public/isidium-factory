"""V4a-ii-b PR 1 of 3: the review gate's answers, typed, and the class its malformed answer ends with.

The flow [owner-ruled 2026-09-25/27]: the reviewer files `Findings`; any `blocking` finding sends the run to
reconcile, where the builder answers a `ReconcileReport`; the reviewer's second pass answers a `Ruling`, and a finding
still asserted parks the run. Nothing here drives that chain (PR 2 does); these tests pin the shapes it will read and
the one failure class it will end with.
"""

from __future__ import annotations

import json
from typing import get_args

import pytest
from pydantic import ValidationError

from isidium.factory import adapter as adapter_mod
from isidium.factory import artifacts
from isidium.factory import container as container_mod

FINDING = {
    "id": "F1",
    "severity": "blocking",
    "claim": "S2's test passes on an empty list",
    "location": "tests/x.py:12",
    "why": "the assertion reads the length of what it should compare",
    "bears_on": "S2",
}


def test_findings_name_their_blocking_ones_and_empty_is_a_real_answer() -> None:
    minor = {**FINDING, "id": "F2", "severity": "minor"}
    found = artifacts.Findings.model_validate({"findings": [FINDING, minor]})
    assert [f.id for f in found.blocking] == ["F1"], "only blocking findings send the run to reconcile"
    assert artifacts.Findings.model_validate({}).blocking == (), "reviewed, nothing found: reconcile is skipped"


def test_a_finding_must_say_what_it_bears_on() -> None:
    """T-B6 (1)–(2): a finding is traceable to the card — without `bears_on` it is the refuter's shape, not the
    reviewer's, and the model refuses it."""
    with pytest.raises(ValidationError):
        artifacts.ReviewFinding.model_validate({k: v for k, v in FINDING.items() if k != "bears_on"})


def test_a_reconcile_report_is_checked_against_the_blocking_findings() -> None:
    """The schema cannot see the findings, so `unanswered` is the check: every blocking finding answered, a minor one
    never required — and an extra row for a finding that does not exist is not this check's to refuse."""
    found = artifacts.Findings.model_validate(
        {"findings": [FINDING, {**FINDING, "id": "F3"}, {**FINDING, "id": "F2", "severity": "minor"}]}
    )
    report = artifacts.ReconcileReport.model_validate(
        {"rows": [{"id": "F1", "disposition": "fixed", "note": "compared the list"}]}
    )
    assert report.unanswered(found) == ("F3",)
    full = artifacts.ReconcileReport.model_validate(
        {
            "rows": [
                {"id": "F1", "disposition": "fixed", "note": "compared the list"},
                {"id": "F3", "disposition": "refuted", "note": "the length is the property S2 states"},
            ]
        }
    )
    assert full.unanswered(found) == ()
    with pytest.raises(ValidationError):
        artifacts.ReconcileReport.model_validate({"rows": []})  # a reconcile that answers nothing is malformed
    with pytest.raises(ValidationError):
        artifacts.ReconcileReport.model_validate({"rows": [{"id": "F1", "disposition": "ignored", "note": "x"}]})


def test_a_ruling_names_what_is_still_disputed() -> None:
    ruling = artifacts.Ruling.model_validate(
        {
            "rulings": [
                {"id": "F1", "ruling": "concur", "reason": "the comparison is there"},
                {"id": "F3", "ruling": "still-asserted", "reason": "S2 states equality, not length"},
            ]
        }
    )
    assert ruling.disputed == ("F3",), "a finding still asserted parks the run review-disputed"
    agreed = artifacts.Ruling.model_validate({"rulings": [{"id": "F1", "ruling": "concur", "reason": "fixed"}]})
    assert agreed.disputed == ()


def test_each_phase_and_round_answers_with_its_own_artifact() -> None:
    """The review's second pass is the same phase and agent, and it rules rather than finds — the round, not a new
    phase name, picks the artifact. The build answers with its commit."""
    assert artifacts.artifact_of("review") == ("findings", artifacts.Findings)
    assert artifacts.artifact_of("review", 2) == ("ruling", artifacts.Ruling)
    assert artifacts.artifact_of("reconcile") == ("reconcile-report", artifacts.ReconcileReport)
    assert artifacts.artifact_of("plan", 2) == ("plan", artifacts.Plan), "a revised plan is still a plan"
    assert artifacts.artifact_of("build") is None


def test_the_review_gate_is_typed_but_not_yet_read_by_the_wrapper() -> None:
    """PR 1 is inert: `OF_PHASE`, which the harness and the wrapper read, is unchanged, so the review phase reachable
    today is handled as it was. PR 2 moves both readers to `artifact_of`."""
    assert set(artifacts.OF_PHASE) == {"plan", "refute", "judge"}
    assert not set(artifacts.OF_PHASE) & set(artifacts.OF_REVIEW_GATE)


def test_each_review_gate_schema_is_self_contained_and_closed() -> None:
    """The same contract as the plan gate's schemas: no `$ref` for the harness to resolve, deterministic, closed."""
    models = [m for _, m in artifacts.OF_REVIEW_GATE.values()] + [m for _, m in artifacts.OF_LATER_ROUND.values()]
    for model in models:
        text = json.dumps(artifacts.schema(model), sort_keys=True)
        assert "$ref" not in text and "$defs" not in text, model.__name__
        assert json.dumps(artifacts.schema(model), sort_keys=True) == text, "deterministic"
        assert artifacts.schema(model)["additionalProperties"] is False, model.__name__
    item = artifacts.schema(artifacts.Findings)["properties"]["findings"]["items"]
    assert "bears_on" in item["required"] and item["additionalProperties"] is False
    ruled = artifacts.schema(artifacts.Ruling)["properties"]["rulings"]["items"]
    assert ruled["properties"]["ruling"]["enum"] == ["concur", "still-asserted"]


def test_a_malformed_review_answer_is_a_final_failure_the_ledger_can_record() -> None:
    """Q-B1 (a): `failed:malformed-review` beside `failed:malformed-plan` — an outcome a phase may end with, and a
    final one, because the harness already re-asked inside the call (a second container attempt would repeat it)."""
    assert "failed:malformed-review" in get_args(adapter_mod.Outcome)
    assert "failed:malformed-review" in container_mod.FINAL
