"""Card 15: a run dispatched after its card's last run parked hands round one's plan phase that park's question,
named `previous-park` — so the plan author starts from a finding the owner has already seen, rather than paying
again to rediscover it (R1). Only round one reads it (R3); a card whose latest run did not park, or whose park's
question cannot be read, is handed nothing new (R2, R4). And `prompts/plan-author/v2.md` is where the plan author
is told what it means and how to answer it (R5, R6).
"""

from __future__ import annotations

import itertools
from collections.abc import Iterator
from pathlib import Path

import pytest

from isidium.factory import artifacts, gate
from isidium.factory.ledger import Ledger, NewRun
from isidium.store.core import telemetry

from ..store.conftest import git
from .test_gate import BLOCKED, CLEAN, PAYLOAD, PLAN, H, verdict
from .test_v4a import Disk, Fake, _harness_result, disk
from .test_v4a_ii import ANSWERS, Shaped, chain, one

__all__ = ["disk"]  # this module's own tenant, built once — the V4a-ii convention

PROMPT_V2 = Path(__file__).resolve().parents[2] / "prompts" / "plan-author" / "v2.md"

_SEQ = itertools.count()


def _at() -> str:
    """A `dispatched_at` strictly later than the one before it, for every run this file dispatches — never today's
    real dispatch time (`disk.run_id`'s) and never `fresh_run`'s single shared stamp elsewhere in the suite, either
    of which would leave `ledger.runs()`' own order to decide which run is "the card's latest" by accident."""
    return f"2099-01-01T00:{next(_SEQ):02d}:00Z"


@pytest.fixture
def led(disk: Disk) -> Iterator[Ledger]:
    ledger = disk.ledger()
    yield ledger
    ledger.close()


def _dispatch(disk: Disk, led: Ledger) -> str:
    """A dispatched run for the fixture's card, written the way `dispatch.pick` writes one, at the next tick of
    `_at()` — so it is unambiguously the card's newest run so far."""
    was = led.run(disk.run_id)
    assert was is not None
    run_id = led.dispatch(
        NewRun(
            card=disk.card,
            lane="standard",
            build_hash=str(was["build_hash"]),
            base_sha=str(was["base_sha"]),
            adapter="container",
            dispatched_at=_at(),
            payload_hash=str(was["payload_hash"]),
            config_hash=str(was["config_hash"]),
            identity=str(was["identity"]),
        )
    )
    git(disk.work, "branch", f"story/{run_id}", str(was["base_sha"]))
    return run_id


def _park_a_run(disk: Disk, led: Ledger) -> tuple[str, artifacts.ParkQuestion]:
    """A run on the fixture's card, driven to a second-round `revise` — 7bd.10's park — and its question read back
    the way a later run's plan phase would have to."""
    run_id = _dispatch(disk, led)
    drv = Shaped(home=disk.home, answers={**ANSWERS, "judge": [verdict("revise"), verdict("revise")]})
    row = chain(disk, led, run_id, drv)
    assert row["outcome"] == "parked", row["outcome"]
    question = artifacts.ParkQuestion.model_validate_json((disk.home / "runs" / run_id / "question.json").read_bytes())
    return run_id, question


# --------------------------------------------------------------------------------------------------------- the gate


def test_the_first_plan_after_a_park_is_handed_its_question(disk: Disk, led: Ledger) -> None:
    """R1: at the gate, round one's plan phase names `previous-park` and carries the question exactly; end to end,
    the run dispatched after a park is handed the question the ledger's own `_park` wrote for the one before it."""
    q = artifacts.ParkQuestion(
        run_id="r-parked",
        card_id=1,
        phase="judge",
        question="which reading of the card?",
        tried=("plan", "refute", "judge"),
        why_blocked="the judge said revise",
        source_tag="plan-failed",
    )
    named = dict(gate.inputs_for("plan", [], PAYLOAD, previous_park=q))
    assert named == {"previous-park": q.model_dump(mode="json")}

    _, question = _park_a_run(disk, led)
    next_run = _dispatch(disk, led)
    later = Shaped(home=disk.home)
    one(disk, led, next_run, "plan", later)
    got = {i.name: i.content for i in later.seen[0].inputs}
    assert got == {"previous-park": question.model_dump(mode="json")}


@pytest.mark.parametrize("corrupt", ["missing", "invalid"])
def test_an_unreadable_question_is_not_handed_and_is_named(
    disk: Disk, led: Ledger, caplog: pytest.LogCaptureFixture, corrupt: str
) -> None:
    """R2: a `question.json` that is gone, or present but not a park question, is not the plan phase's to fail
    over — it runs as it would with no park at all, and the path is named where the operator reads it."""
    run_id, _ = _park_a_run(disk, led)
    path = disk.home / "runs" / run_id / "question.json"
    if corrupt == "missing":
        path.unlink()
    else:
        path.write_bytes(b"{}")

    next_run = _dispatch(disk, led)
    later = Shaped(home=disk.home)
    with caplog.at_level("WARNING", logger=telemetry.SCOPE):
        row = one(disk, led, next_run, "plan", later)
    assert row["ended_at"] is None, "the phase ran ok despite the unreadable question"
    assert [i.name for i in later.seen[0].inputs] == []
    records = "\n".join(r.getMessage() for r in caplog.records)
    assert str(path) in records


def test_only_round_ones_plan_is_handed_the_previous_park(disk: Disk, led: Ledger) -> None:
    """R3: with a previous park in hand, the refuter, the judge, the build and the plan author's own revision are
    handed exactly the names they are handed with none — only round one's plan gets the extra one."""
    q = artifacts.ParkQuestion(
        run_id="r-parked",
        card_id=1,
        phase="judge",
        question="which reading?",
        tried=("plan", "refute", "judge"),
        why_blocked="the judge said revise",
        source_tag="plan-failed",
    )

    def names(phase: str, history: list[gate.Done]) -> list[str]:
        return [n for n, _ in gate.inputs_for(phase, history, PAYLOAD, previous_park=q)]

    assert names("plan", []) == ["previous-park"]
    assert names("refute", [H("plan", PLAN)]) == ["plan"]
    assert names("judge", [H("plan", PLAN), H("refute", CLEAN)]) == ["plan", "refutation"]
    assert names("build", [H("plan", PLAN), H("refute", CLEAN), H("judge", verdict("approve"))]) == ["plan"]
    judged = [H("plan", PLAN), H("refute", BLOCKED), H("judge", verdict("revise"))]
    assert names("plan", judged) == ["plan", "refutation", "verdict"], "the revision reads its own round, not the park"


def test_a_card_whose_last_run_did_not_park_is_handed_nothing_new(disk: Disk, led: Ledger) -> None:
    """R4: the same fixture twice — a previous run that ended some other way hands nothing, and a previous run that
    parked hands its question — in one test, so an implementation that hands nothing on both halves cannot pass."""
    not_parked = _dispatch(disk, led)
    row = one(disk, led, not_parked, "build", Fake(result=_harness_result(outcome="failed:budget")))
    assert row["outcome"] == "failed:budget"

    after_failure = _dispatch(disk, led)
    plain = Shaped(home=disk.home)
    one(disk, led, after_failure, "plan", plain)
    assert [i.name for i in plain.seen[0].inputs] == [], "the card's latest run did not park"

    _park_a_run(disk, led)
    after_park = _dispatch(disk, led)
    handed = Shaped(home=disk.home)
    one(disk, led, after_park, "plan", handed)
    assert [i.name for i in handed.seen[0].inputs] == ["previous-park"], "the card's latest run did park"


# ------------------------------------------------------------------------------------------------------ the prompt


def _flat(path: Path) -> str:
    """The prompt's words with markdown's own line wrapping collapsed, so a phrase this file wraps across lines is
    still found by a plain substring check."""
    return " ".join(path.read_text(encoding="utf-8").split())


def test_the_v2_prompt_names_previous_park() -> None:
    """R5: the plan author's v2 prompt says what `previous-park` is, and that the card as ratified now is the
    specification — the park being context for why it reads as it does, not a plan to resume."""
    text = _flat(PROMPT_V2)
    assert "previous-park" in text
    assert "the card as ratified is the specification" in text


def test_the_v2_prompt_asks_for_blocking_and_an_assumption() -> None:
    """R6: v2 says every question is marked `blocking` — true only when the plan cannot be written without the
    owner's answer — and that a non-blocking question carries the assumption the plan made in its place instead."""
    text = _flat(PROMPT_V2)
    assert "blocking" in text and "cannot be written" in text and "owner's answer" in text
    assert "assumption" in text
