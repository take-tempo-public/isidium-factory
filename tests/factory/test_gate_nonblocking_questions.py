"""Card 18: a plan's question, typed — R1-R4. Only a *blocking* question parks the plan gate at once; a
non-blocking one carries the assumption the plan made in its place and rides on to the refuter and judge, where a
wrong assumption is a finding rather than a park. Each rule tested where it is stated, on the fixtures `test_gate`
already builds.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from isidium.factory import artifacts, gate

from .test_gate import PAYLOAD, H, plan


def test_a_question_records_blocking_and_its_assumption() -> None:
    """R1: a question carries its text, whether it is blocking, and — when it is not — the assumption made in its
    place. `blocking` is unskippable, and a non-blocking question with no assumption is refused."""
    made = artifacts.Plan.model_validate(
        plan(questions=[{"text": "which validator?", "blocking": False, "assumption": "the registry's"}])
    )
    q = made.questions[0]
    assert (q.text, q.blocking, q.assumption) == ("which validator?", False, "the registry's")

    with pytest.raises(ValidationError):
        artifacts.Question.model_validate({"text": "which one?"})  # the author must say which

    with pytest.raises(ValidationError):
        artifacts.Question.model_validate({"text": "which one?", "blocking": False})  # no assumption made


def test_a_blocking_question_parks_at_once() -> None:
    """R2: a blocking question parks before the lint runs at all — not merely because a question is present. A plan
    that both carries a blocking question and touches `x.py` (outside `PAYLOAD`'s surfaces, which alone would route
    to a round-1 revision) must still park, with the blocking text as its question, not the lint's claim."""
    wide = plan(questions=[{"text": "which file?", "blocking": True}], touched=["x.py"])
    step = gate.next_step([H("plan", wide)], PAYLOAD)
    assert (step.kind, step.source_tag, step.question) == ("park", "card-ambiguity", "which file?")


def test_non_blocking_questions_go_on_to_the_refuter() -> None:
    """R3: a plan whose questions are all non-blocking goes on to the lint and the refuter, its questions and
    assumptions carried in the plan artifact the refuter and judge read; the lint still runs (a non-blocking
    question does not excuse a plan reaching outside its surfaces)."""
    question = {"text": "which validator?", "blocking": False, "assumption": "the registry's"}
    riding = plan(questions=[question])

    step = gate.next_step([H("plan", riding)], PAYLOAD)
    assert (step.kind, step.phase) == ("phase", "refute")

    refute_inputs = dict(gate.inputs_for("refute", [H("plan", riding)], PAYLOAD))
    assert refute_inputs["plan"]["questions"] == [question]

    judged_history = [H("plan", riding), H("refute", {"findings": []})]
    judge_inputs = dict(gate.inputs_for("judge", judged_history, PAYLOAD))
    assert judge_inputs["plan"]["questions"] == [question]

    linted = plan(questions=[question], touched=["x.py"])
    revise = gate.next_step([H("plan", linted)], PAYLOAD)
    assert (revise.kind, revise.phase) == ("phase", "plan"), "the lint still runs; round one revises, it does not park"


def test_a_bare_string_question_reads_as_blocking() -> None:
    """R4: a question written as a bare string — every plan artifact's form before card 18 — reads as blocking, so
    a chain resumed over an older plan takes the path it took."""
    made = artifacts.Plan.model_validate(plan(questions=["which file?"]))
    q = made.questions[0]
    assert (q.text, q.blocking, q.assumption) == ("which file?", True, "")

    step = gate.next_step([H("plan", plan(questions=["which file?"]))], PAYLOAD)
    assert (step.kind, step.source_tag, step.question) == ("park", "card-ambiguity", "which file?")
