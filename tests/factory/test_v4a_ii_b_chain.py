"""V4a-ii-b PR 2 of 3: the review gate, driven — the chain past the build [owner-ruled 2026-09-25/27].

Review → nothing blocking, the end; a blocking finding → reconcile (the **builder**, inside the plan's surface) → the
reviewer's second pass, bounded to the findings → a finding still asserted parks `review-disputed`, every one concurred
and it is the end. A malformed review-gate answer ends the run `failed:malformed-review`; a parked run's work can be
carried (Q-B3 (a)).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from isidium.factory import adapter as adapter_mod
from isidium.factory import artifacts, harness
from isidium.factory import dispatch as dispatch_mod
from isidium.factory.ledger import Ledger, NewRun

from .test_v4a import INSIDE, LOGIN, TENANT, Branch, Disk, a_job, disk, fresh_run, refuses
from .test_v4a_ii import ANSWERS, CLEAN, Shaped, chain, led

__all__ = ["disk", "led"]  # the V4a tenant and its ledger, as test_v4a_ii builds them

FOUND: dict[str, Any] = {
    "traceability": [
        {"id": "S1", "evidence": "tests/test_validator.py fails without the validator"},
        {"id": "S2", "evidence": "no test shows the refusal path"},
    ],
    "findings": [
        {
            "id": "F1",
            "severity": "blocking",
            "claim": "S2 has no test that fails today",
            "location": "tests/test_validator.py",
            "why": "looked for a refusal-path assertion and found none",
            "bears_on": "S2",
        },
        {
            "id": "F2",
            "severity": "minor",
            "claim": "a docstring says validater",
            "location": "client/cards/validator.py:1",
            "why": "read it",
            "bears_on": "R1",
        },
    ],
}
REPORT: dict[str, Any] = {"rows": [{"id": "F1", "disposition": "fixed", "note": "added the refusal-path test"}]}


def ruling(r: str) -> dict[str, Any]:
    return {"rulings": [{"id": "F1", "ruling": r, "reason": f"the reviewer says {r}"}]}


def test_a_clean_review_ends_the_chain_and_reads_the_plan_writing_nothing(disk: Disk, led: Ledger) -> None:
    drv = Shaped(home=disk.home)
    row = chain(disk, led, fresh_run(disk, led), drv)
    assert [p["phase"] for p in row["phases"]][-2:] == ["build", "review"] and row["ended_at"] is None
    review = drv.seen[-1]
    assert review.identity.agent == "reviewer" and review.allowed_writes == ()
    assert [i.name for i in review.inputs] == ["plan", "diff"], "the first pass reads the plan; the diff is in the job"


def test_a_blocking_finding_runs_reconcile_then_a_bounded_second_pass(disk: Disk, led: Ledger) -> None:
    """Ruling 1: the builder reconciles, inside the plan's surface, handed the plan and the findings; the reviewer's
    second pass reads only the findings and the builder's answer, and answers a ruling — its schema passed on the argv.
    Every finding concurred, and the chain ends, in flight, for close."""
    run_id = fresh_run(disk, led)
    drv = Shaped(home=disk.home, answers={**ANSWERS, "review": [FOUND, ruling("concur")], "reconcile": REPORT})
    row = chain(disk, led, run_id, drv)
    assert [p["phase"] for p in row["phases"]][-4:] == ["build", "review", "reconcile", "review"]
    assert row["ended_at"] is None and row["outcome"] != "parked"
    reconcile, second = drv.seen[-2], drv.seen[-1]
    assert reconcile.identity.agent == "builder" and reconcile.allowed_writes == (INSIDE, "tests/")
    assert [i.name for i in reconcile.inputs] == ["plan", "findings"]
    assert second.round == 2 and [i.name for i in second.inputs] == ["findings", "reconcile-report", "diff"]
    argv = harness.argv(second, "/run/settings.json")
    assert json.loads(argv[argv.index("--json-schema") + 1]) == artifacts.schema(artifacts.Ruling)
    assert not led.verdicts_of(run_id)[2:], "the review's outcome is never a verdicts row (ruling 3)"


def test_a_finding_still_asserted_parks_review_disputed_with_both_sides(disk: Disk, led: Ledger) -> None:
    """Ruling 2: a dispute is a question for the owner — the run parks `review-disputed`, and the question carries the
    reviewer's claim and reason beside the builder's disposition."""
    run_id = fresh_run(disk, led)
    drv = Shaped(home=disk.home, answers={**ANSWERS, "review": [FOUND, ruling("still-asserted")], "reconcile": REPORT})
    row = chain(disk, led, run_id, drv)
    assert row["outcome"] == "parked"
    q = artifacts.ParkQuestion.model_validate_json((disk.home / "runs" / run_id / "question.json").read_bytes())
    assert q.source_tag == "review-disputed" and q.phase == "review"
    assert "S2 has no test that fails today" in q.question and "the reviewer says still-asserted" in q.question
    assert "fixed: added the refusal-path test" in q.question
    assert "F2" not in q.question, "only what is still asserted goes to the owner"
    assert q.tried[-3:] == ("review", "reconcile", "review")


def test_a_minor_finding_alone_does_not_reconcile(disk: Disk, led: Ledger) -> None:
    minor = {**FOUND, "findings": [FOUND["findings"][1]]}
    drv = Shaped(home=disk.home, answers={**ANSWERS, "review": minor})
    row = chain(disk, led, fresh_run(disk, led), drv)
    assert [p["phase"] for p in row["phases"]][-1] == "review" and "reconcile" not in [j.phase for j in drv.seen]


def test_a_malformed_review_ends_the_run_in_the_review_gates_class(disk: Disk, led: Ledger) -> None:
    drv = Shaped(home=disk.home, answers={**ANSWERS, "review": None})
    row = chain(disk, led, fresh_run(disk, led), drv)
    assert row["outcome"] == "failed:malformed-review" and [p["phase"] for p in row["phases"]][-1] == "review"


def test_a_review_gate_answer_that_leaves_something_out_is_malformed(disk: Disk, tmp_path: Path) -> None:
    """The completeness the schema cannot see, checked where the answer is validated: a review that skips a scenario,
    a reconcile that leaves a blocking finding unanswered, a second pass that does not rule on every reconciled row."""
    payload = {"form": "isidium-payload 1", "gated": {"acceptance": {"scenarios": [{"id": "S1"}, {"id": "S2"}]}}}
    reviewer = {"agent": "reviewer", "name": "n", "email": "e"}
    builder = {"agent": "builder", "name": "n", "email": "e"}

    def given(name: str, value: dict[str, Any]) -> adapter_mod.Input:
        return adapter_mod.Input(name=name, sha256=artifacts.sha256(artifacts.canonical(value)), content=value)

    review = a_job(disk, phase="review", identity=reviewer, allowed_writes=(), payload=payload)
    untraced = {**FOUND, "traceability": FOUND["traceability"][:1]}
    assert harness.harvest(review, {"structured_output": untraced}, tmp_path) == ("failed:malformed-review", [])
    assert harness.harvest(review, {"structured_output": FOUND}, tmp_path)[0] is None

    reconcile = a_job(disk, phase="reconcile", identity=builder, inputs=(given("findings", FOUND),))
    unanswered = {"rows": [{"id": "F9", "disposition": "fixed", "note": "x"}]}
    assert harness.harvest(reconcile, {"structured_output": unanswered}, tmp_path)[0] == "failed:malformed-review"
    assert harness.harvest(reconcile, {"structured_output": REPORT}, tmp_path)[0] is None

    second = a_job(
        disk, phase="review", identity=reviewer, allowed_writes=(), round=2, inputs=(given("reconcile-report", REPORT),)
    )
    skipped = {"rulings": [{"id": "F7", "ruling": "concur", "reason": "x"}]}
    assert harness.harvest(second, {"structured_output": skipped}, tmp_path)[0] == "failed:malformed-review"
    assert harness.harvest(second, {"structured_output": ruling("concur")}, tmp_path)[0] is None


def test_a_parked_run_with_work_can_be_carried_and_one_without_cannot(disk: Disk, tmp_path: Path) -> None:
    """Q-B3 (a): a disputed review has a build behind it, and the owner's answer should not cost that build. A parked
    run that committed nothing (every plan-gate park) is answered `carry-empty`, as a failed one with nothing is. Past
    the carry checks, the ordinary door still decides — the card is not ready here."""
    ledger = Ledger(tmp_path / "carry.sqlite", TENANT)

    def a_run(outcome: str, head: str | None) -> str:
        rid = ledger.dispatch(
            NewRun(
                card=disk.card,
                lane="standard",
                build_hash="sha256:b",
                base_sha="0" * 40,
                adapter="container",
                dispatched_at="2026-10-01T00:00:00Z",
                payload_hash="sha256:p",
                config_hash="sha256:c",
                identity=LOGIN,
            )
        )
        ledger.finish(rid, "2026-10-01T00:01:00Z", outcome, head_sha=head)
        return rid

    def dry(carry: str) -> Any:
        return dispatch_mod.pick(
            disk.ctx,
            ledger,
            lambda n, a: {"ready": [], "in_flight": []},
            Branch(disk.work),
            carry_from=carry,
            dry_run=True,
        )

    try:
        refuses("dispatch.not-ready", lambda: dry(a_run("parked", "deadbeef")))
        refuses("dispatch.carry-empty", lambda: dry(a_run("parked", None)))
        refuses("dispatch.carry-outcome", lambda: dry(a_run("closed", "deadbeef")))
    finally:
        ledger.close()


def test_the_chain_reaches_the_review_gate_with_clean_answers_by_default() -> None:
    """The shared fixtures answer the review cleanly, so every chain test in test_v4a_ii ends at the review."""
    assert ANSWERS["review"] is CLEAN
