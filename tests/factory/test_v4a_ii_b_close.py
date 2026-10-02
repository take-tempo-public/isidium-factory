"""V4a-ii-b PR 3 of 3: close refuses a run that skipped the review gate, when the tenant declares a reviewer.

Q-B2 (a) [owner, 2026-09-27]: once the review gate exists, a tenant whose signed policy declares a reviewer is owed
one. A run whose gate did not run to its end is refused `close.review-skipped` — before the forge is asked anything —
and stays in flight, so the chain can be driven on (`run --run` resumes from the history) and close run again. A
tenant that declares no reviewer keeps Q-V18's build-only close.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from isidium.factory import adapter as adapter_mod
from isidium.factory import artifacts, gate
from isidium.factory import close as close_mod
from isidium.factory.gate import Done
from isidium.factory.ledger import Ledger

from . import test_v5a
from .test_v5a import AT, Acceptance, Disk, a_run, forge_for, refuses

disk = test_v5a.disk
led = test_v5a.led

TRACED = [{"id": "S1", "evidence": "a test"}]
CLEAN: dict[str, Any] = {"traceability": TRACED, "findings": []}
BLOCKING: dict[str, Any] = {
    "traceability": TRACED,
    "findings": [{"id": "F1", "severity": "blocking", "claim": "c", "location": "l", "why": "w", "bears_on": "S1"}],
}
REPORT: dict[str, Any] = {"rows": [{"id": "F1", "disposition": "fixed", "note": "n"}]}


def ruled(r: str) -> dict[str, Any]:
    return {"rulings": [{"id": "F1", "ruling": r, "reason": "r"}]}


def test_the_review_gate_is_done_exactly_where_the_chain_would_stop() -> None:
    """The same function as the routing: a review with nothing blocking, or a second pass that concurs, is done; a
    build alone, a review that blocked and was never reconciled, a reconcile with no second pass, a dispute, and a run
    with no build at all are not."""
    built = [Done("build", None)]
    assert gate.review_gate_done([*built, Done("review", CLEAN)])
    assert gate.review_gate_done(
        [*built, Done("review", BLOCKING), Done("reconcile", REPORT), Done("review", ruled("concur"))]
    )
    assert not gate.review_gate_done(built)
    assert not gate.review_gate_done([*built, Done("review", BLOCKING)])
    assert not gate.review_gate_done([*built, Done("review", BLOCKING), Done("reconcile", REPORT)])
    disputed = [*built, Done("review", BLOCKING), Done("reconcile", REPORT), Done("review", ruled("still-asserted"))]
    assert not gate.review_gate_done(disputed)
    assert not gate.review_gate_done([Done("review", CLEAN)]), "nothing was built for it to have read"


def test_declaring_an_agent_is_naming_its_tools() -> None:
    """One home for the rule the policy already used: a row the schema's defaults alone supply names no tools."""
    assert adapter_mod.declares({"agents": {"reviewer": {"tools": []}}}, "reviewer"), "an empty tool list is declared"
    assert not adapter_mod.declares({"agents": {"reviewer": {"model": "m", "effort": "high"}}}, "reviewer")
    assert not adapter_mod.declares({"agents": {}}, "reviewer") and not adapter_mod.declares({}, "reviewer")


def test_a_run_that_skipped_the_review_is_refused_before_the_forge_and_stays_in_flight(disk: Disk, led: Ledger) -> None:
    run = a_run(disk, led, disk.factory, reviewed=False)
    forge = forge_for(run)
    acceptance = Acceptance()
    r = refuses("close.review-skipped", lambda: test_v5a.close_run(disk, led, run, forge, acceptance))
    assert f"run --run {run.run_id}" in r.detail, "the refusal says how to go on"
    assert forge.seen == [] and acceptance.seen == [], "refused before the forge or the acceptance is asked anything"
    row = led.run(run.run_id)
    assert row is not None and row["ended_at"] is None


def test_a_run_stopped_inside_the_gate_is_refused_and_one_driven_to_its_end_closes(disk: Disk, led: Ledger) -> None:
    """A review that blocked and was never reconciled is not a review that passed. Driven on — reconcile and a second
    pass that concurs, recorded the way the chain records them — the same run closes."""
    run = a_run(disk, led, disk.factory, reviewed=False)

    def record(phase: str, name: str, value: dict[str, Any], step: str) -> None:
        data = artifacts.canonical(value)
        rel = f"runs/{run.run_id}/{step}/{name}.json"
        (disk.home / rel).parent.mkdir(parents=True, exist_ok=True)
        (disk.home / rel).write_bytes(data)
        made = [{"name": name, "sha256": artifacts.sha256(data), "path": rel}]
        led.phase(run.run_id, AT, {"phase": phase, "agent": "reviewer", "outcome": "ok", "artifacts": made})

    record("review", "findings", BLOCKING, "review")
    refuses("close.review-skipped", lambda: test_v5a.close_run(disk, led, run))
    record("reconcile", "reconcile-report", REPORT, "reconcile")
    record("review", "ruling", ruled("concur"), "review-2")
    assert test_v5a.close_run(disk, led, run)["outcome"] == "closed"


def test_a_tenant_that_declares_no_reviewer_keeps_the_build_only_close(disk: Disk, led: Ledger) -> None:
    """Q-V18's close, kept where the ruling keeps it: no declared reviewer, no review owed."""
    agents = {k: v for k, v in dict(disk.ctx.eff["agents"]).items() if k != "reviewer"}
    bare = dataclasses.replace(disk.ctx, eff={**disk.ctx.eff, "agents": agents})
    run = a_run(disk, led, disk.factory, reviewed=False)
    out = close_mod.close(bare, led, disk.call, forge_for(run), run_id=run.run_id, pr=7, accept=Acceptance())
    assert out["outcome"] == "closed"
