"""The adapter conformance suite — T-C6's registration gate, as a file [V4a-i, 2026-09-12].

T-C6, verbatim: *"An adapter is **registered only after passing the conformance suite** (the same scenario runs) —
the seam is verified by conformance, never by trust"*; and 05 §3 [owner-ratified 2026-08-27]: *"every execution
adapter declares what it preserves and what degrades as capability rows the conformance suite checks — declared
degradation, never silent"*.

**This module is not a test file.** It is the scenario, written once, that every adapter's test file runs against
its own adapter — the container adapter here, `claude-code-action` in V4b, a pi adapter when the swap trigger
fires. A suite with one adapter in it is a test; what makes it a suite is that the second one changes nothing here.

A capability row is checked, never believed: an adapter that declares `write_guard_at_write_time` has to actually
deny a write outside the card's surfaces under its own rendered policy, and one that declares `post-hoc` has to
actually render no hook. Declaring the weaker row is allowed; declaring the stronger one and not having it is the
failure this file exists to catch.
"""

from __future__ import annotations

import io
import json
from collections.abc import Sequence
from contextlib import redirect_stderr
from typing import Any

from isidium.factory import guard, render
from isidium.factory.adapter import Adapter, BillingClass, PhaseResult, RunJob

BILLING: tuple[str, ...] = ("plan", "metered")


def run(adapter: Adapter, job: RunJob, monkeypatch: Any, tmp_path: Any) -> list[str]:
    """The scenario. Returns the failures it found, so a caller sees every one at once rather than the first."""
    bad: list[str] = []
    bad += _capabilities(adapter)
    bad += _execute(adapter, job)
    bad += _guard(adapter, job, monkeypatch, tmp_path)
    return bad


def _capabilities(adapter: Adapter) -> list[str]:
    """The matrix is declared, complete, and says which lane the runs bill to — the measurement that decides the
    ruled harness swap (7bdb.4(5)) is worthless if an adapter may leave it blank."""
    bad: list[str] = []
    caps = adapter.capabilities()
    if not caps.name:
        bad.append("capabilities().name is empty: an adapter with no name cannot be registered")
    if not caps.harness or not caps.harness_version:
        bad.append("capabilities() does not name its harness and version")
    if caps.billing_class not in BILLING:
        bad.append(f"capabilities().billing_class {caps.billing_class!r} is not one of {BILLING}")
    if not caps.identity_held_by_wrapper:
        bad.append("an adapter that lets the model hold the identity cannot be registered (7j.5, W9)")
    if not caps.telemetry_per_phase:
        bad.append("telemetry per phase is T-C6's contract, not an option")
    return bad


def _execute(adapter: Adapter, job: RunJob) -> list[str]:
    """One typed job in, one typed result out, for the run and phase it was handed — and the model the tenant's
    signed policy named, not one the adapter chose."""
    bad: list[str] = []
    # Typed as `object` on purpose: the declaration says `PhaseResult`, and this is the check that the adapter
    # actually returns one. An adapter is verified by conformance, never by trust — including its type.
    answered: object = adapter.execute(job)
    if not isinstance(answered, PhaseResult):
        return [f"execute() answered {type(answered).__name__}, not a PhaseResult"]
    res = answered
    spec = job.policy.agent(job.identity.agent)
    if (res.run_id, res.phase) != (job.run_id, job.phase):
        bad.append(f"the result is for {res.run_id}/{res.phase}, the job was {job.run_id}/{job.phase}")
    if (res.model, res.effort) != (spec.model, spec.effort):
        bad.append(f"the result ran {res.model}/{res.effort}; the policy named {spec.model}/{spec.effort}")
    if res.billing_class != adapter.capabilities().billing_class:
        bad.append("the result's billing class disagrees with the adapter's declared one")
    if PhaseResult.model_validate(res.row()) != res:
        bad.append("the result does not survive its own ledger row: the wire and the record have drifted")
    return bad


def _guard(adapter: Adapter, job: RunJob, monkeypatch: Any, tmp_path: Any) -> list[str]:
    """The capability row that matters most, checked against behaviour.

    `write-time` means the rendered policy installs the hook **and** the hook denies a write outside the card's
    surfaces while allowing one inside. `post-hoc` means no hook is rendered — declared degradation, visible."""
    bad: list[str] = []
    caps = adapter.capabilities()
    rendered = render.settings(job.policy)
    hooked = "hooks" in rendered
    if caps.write_guard_at_write_time != hooked:
        bad.append(f"declares write_guard_at_write_time={caps.write_guard_at_write_time} but renders hooks={hooked}")
    if not caps.write_guard_at_write_time:
        return bad

    tmp_path.mkdir(parents=True, exist_ok=True)
    spec = tmp_path / "allow.json"
    blocks = tmp_path / "blocks.jsonl"
    spec.write_text(json.dumps(render.allow_spec(job)), encoding="utf-8")
    monkeypatch.setenv(guard.ALLOW_ENV, str(spec))
    monkeypatch.setenv(guard.BLOCKS_ENV, str(blocks))

    inside = job.allowed_writes[0].rstrip("/") + ("/x.py" if job.allowed_writes[0].endswith("/") else "")
    if _hook(inside or job.allowed_writes[0]) != 0:
        bad.append(f"the guard denied {inside!r}, which the card declares")
    if _hook("docs/work/cards/0001-anything.md") == 0:
        bad.append("the guard allowed a write to a governed path outside the card's surfaces")
    if _hook("/etc/passwd") == 0:
        bad.append("the guard allowed a write outside the worktree entirely")
    return bad


def _hook(path: str, tool: str = "Write") -> int:
    """One PreToolUse call, through the same entry the container runs. stderr is captured so a pytest run is not
    littered with the reasons of the denials this scenario is deliberately provoking."""
    payload = json.dumps({"tool_name": tool, "tool_input": {"file_path": f"{render.WORK}/{path.lstrip('/')}"}})
    import sys

    old, sys.stdin = sys.stdin, io.StringIO(payload)
    try:
        with redirect_stderr(io.StringIO()):
            return guard.main([])
    finally:
        sys.stdin = old


def expected_rows(caps: Any) -> Sequence[tuple[str, bool | str]]:
    """The matrix as rows, for a test that wants to print or pin them."""
    return (
        ("write_guard_at_write_time", caps.write_guard_at_write_time),
        ("identity_held_by_wrapper", caps.identity_held_by_wrapper),
        ("budgets", caps.budgets),
        ("watchdog", caps.watchdog),
        ("end_and_resume", caps.end_and_resume),
        ("telemetry_per_phase", caps.telemetry_per_phase),
        ("billing_class", caps.billing_class),
    )


__all__ = ["BILLING", "BillingClass", "expected_rows", "run"]
