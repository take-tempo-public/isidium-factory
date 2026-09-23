"""V4a-ii-a, PR 2 of 3 — the plan gate's artifacts, the phases that write nothing, and the chain [2026-09-23].

The rulings this file holds the code to [owner, 2026-09-23]: the harness's in-call re-asking is T-B4 (1)'s one retry,
so a null `structured_output` ends the run `failed:malformed-plan` at once, for the plan, the refutation and the
verdict alike; the chain stops at the judge until the gate is built; the artifacts ride the job inline by hash and are
re-hashed before use; plan, refute and judge have no write surface, and a write ends the run uncommitted.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from isidium.factory import adapter as adapter_mod
from isidium.factory import artifacts, harness
from isidium.factory import checkout as checkout_mod
from isidium.factory import runner as runner_mod
from isidium.factory.adapter import PhaseResult, RunJob
from isidium.factory.container import Container
from isidium.factory.ledger import Ledger
from isidium.store.core import telemetry

from ..store.conftest import git
from .test_v4a import INSIDE, Child, Disk, Fake, Podman, _harness_result, _reg, a_job, disk, fresh_run, refuses

__all__ = ["disk"]  # the V4a tenant, built once for this module too

PLAN: dict[str, Any] = {
    "steps": [{"id": "s1", "action": "write the validator", "purpose": "R1"}],
    "touched": [INSIDE],
    "tests": [{"path": "tests/test_validator.py", "scenario": "S1", "fails_today": "the validator does not exist"}],
    "traceability": [{"id": "S1", "covered_by": ["s1"], "note": ""}],
    "risks": [],
    "questions": [],
}
REFUTATION: dict[str, Any] = {"findings": []}
VERDICT: dict[str, Any] = {"verdict": "approve", "reasoning": "every scenario maps to a test that fails today"}
ANSWERS: dict[str, Any] = {"plan": PLAN, "refute": REFUTATION, "judge": VERDICT}


@pytest.fixture
def led(disk: Disk) -> Iterator[Ledger]:
    ledger = disk.ledger()
    yield ledger
    ledger.close()


@dataclass
class Shaped(Fake):
    """The in-process adapter answering a structured phase the way the container does: the artifact's canonical bytes
    in the phase's run directory under the deploy home, named by hash on the result. `answers[phase] = None` is a
    call that ended with no conforming answer; `lie` names a hash the bytes do not have; `writes_in` makes that phase
    write a file into the worktree."""

    home: Path = Path()
    answers: dict[str, Any] = field(default_factory=lambda: dict(ANSWERS))
    lie: bool = False
    writes_in: str | None = None

    def execute(self, job: RunJob) -> PhaseResult:
        self.seen.append(job)
        spec = job.policy.agent(job.identity.agent)
        made: list[dict[str, str]] = []
        outcome = "ok"
        shaped = artifacts.OF_PHASE.get(job.phase)
        if shaped is not None:
            value = self.answers.get(job.phase)
            if value is None:
                outcome = "failed:malformed-plan"
            else:
                data = artifacts.canonical(value)
                rel = f"runs/{job.run_id}/{job.phase}/{shaped[0]}.json"
                (self.home / rel).parent.mkdir(parents=True, exist_ok=True)
                (self.home / rel).write_bytes(data)
                made.append(
                    {"name": shaped[0], "sha256": artifacts.sha256(b"not these" if self.lie else data), "path": rel}
                )
        if self.writes_in == job.phase:
            (Path(job.worktree) / INSIDE).parent.mkdir(parents=True, exist_ok=True)
            (Path(job.worktree) / INSIDE).write_text("a read-only agent's edit", encoding="utf-8")
        return adapter_mod.result(
            {
                **_harness_result(),
                "run_id": job.run_id,
                "phase": job.phase,
                "agent": job.identity.agent,
                "model": spec.model,
                "effort": spec.effort,
                "outcome": outcome,
                "artifacts": made,
            }
        )


def chain(disk: Disk, led: Ledger, run_id: str, drv: Fake) -> dict[str, Any]:
    return runner_mod.run_chain(disk.ctx, _reg(disk), led, disk.call, run_id=run_id, factory=lambda h, r: drv)


def one(disk: Disk, led: Ledger, run_id: str, phase: str, drv: Fake) -> dict[str, Any]:
    return runner_mod.run_phase(
        disk.ctx, _reg(disk), led, disk.call, run_id=run_id, phase=phase, factory=lambda h, r: drv
    )


# ----------------------------------------------------------------------------------------------- the artifacts


def test_each_schema_is_self_contained_closed_and_requires_what_t_b4_requires() -> None:
    """The harness is handed a schema with no `$ref` to resolve (its handling of `$defs` was never measured), closed
    against unknown keys at every level, and the plan's `touched` required — it feeds the build's write guard."""
    for _, model in artifacts.OF_PHASE.values():
        text = json.dumps(artifacts.schema(model), sort_keys=True)
        assert "$ref" not in text and "$defs" not in text, model.__name__
        assert json.dumps(artifacts.schema(model), sort_keys=True) == text, "deterministic"
    plan = artifacts.schema(artifacts.Plan)
    assert {"steps", "touched"} <= set(plan["required"]) and plan["additionalProperties"] is False
    step = plan["properties"]["steps"]["items"]
    assert step["additionalProperties"] is False and "purpose" in step["required"]
    finding = artifacts.schema(artifacts.Refutation)["properties"]["findings"]["items"]
    assert finding["properties"]["severity"]["enum"] == ["blocking", "major", "minor"]
    assert artifacts.schema(artifacts.Verdict)["properties"]["verdict"]["enum"] == ["approve", "revise", "park"]


def test_a_structured_phase_is_handed_its_schema_and_the_build_none(disk: Disk) -> None:
    def args(phase: str, agent: str) -> list[str]:
        ident = {"agent": agent, "name": "isdm-fac-lander", "email": "1+x@users.noreply.github.com"}
        return harness.argv(a_job(disk, phase=phase, identity=ident, allowed_writes=()), "/run/settings.json")

    judge = args("judge", "judge")
    at = judge.index("--json-schema")
    assert json.loads(judge[at + 1]) == artifacts.schema(artifacts.Verdict)
    assert "--json-schema" not in args("build", "builder")


def test_a_null_structured_output_is_malformed_not_ok_and_a_conforming_one_is_kept_by_hash(
    disk: Disk, tmp_path: Path
) -> None:
    """Measured 2026-09-23: a model that never satisfied the schema ends the call `subtype: success`, exit 0, with
    `structured_output: null` — `outcome_of` alone reads that as `ok`. So does an answer that parses but breaks the
    artifact's model (an unknown key here)."""
    job = a_job(disk, phase="plan", identity={"agent": "plan-author", "name": "n", "email": "e"}, allowed_writes=())
    assert harness.harvest(job, {"structured_output": None}, tmp_path) == (harness.MALFORMED, [])
    assert harness.harvest(job, {"structured_output": {**PLAN, "extra": 1}}, tmp_path)[0] == harness.MALFORMED
    assert not (tmp_path / "plan.json").exists()
    none, made = harness.harvest(job, {"structured_output": PLAN}, tmp_path)
    data = (tmp_path / "plan.json").read_bytes()
    assert none is None and made == [{"name": "plan", "sha256": artifacts.sha256(data), "path": "plan.json"}]
    assert data == artifacts.canonical(artifacts.Plan.model_validate(PLAN).model_dump(mode="json"))
    build = a_job(disk)
    assert harness.harvest(build, {"structured_output": None}, tmp_path) == (None, []), "the build answers with none"


def test_the_harness_writes_the_malformed_end_and_the_artifact_into_the_result(disk: Disk, tmp_path: Path) -> None:
    """Through `harness.run`, as PID 1 runs it: the stream's result line is what `--output-format stream-json` ends
    with, and the result the adapter reads says malformed — exit 1 — or carries the artifact."""
    prompts = tmp_path / "prompts"
    (prompts / "judge").mkdir(parents=True)
    (prompts / "judge" / "v1.md").write_text("# the judge", encoding="utf-8")
    job = a_job(disk, phase="judge", identity={"agent": "judge", "name": "n", "email": "e"}, allowed_writes=())

    def answering(so: Any) -> Any:
        def spawn(args: list[str], **kw: Any) -> Child:
            line = {"type": "result", "subtype": "success", "is_error": False, "structured_output": so}
            kw["stdout"].write((json.dumps(line) + "\n").encode("utf-8"))
            return Child({}, done=True)

        return spawn

    for so, want, code in ((None, "failed:malformed-plan", 1), (VERDICT, "ok", 0)):
        rundir = tmp_path / str(code)
        rundir.mkdir()
        got = harness.run(
            job,
            rundir,
            prompts,
            harness_version="2.1.269",
            spawn=answering(so),
            install=lambda s, h: None,
            work=tmp_path,
        )
        res = json.loads((rundir / "result.json").read_text(encoding="utf-8"))
        assert (got, res["outcome"]) == (code, want)
        assert [a["name"] for a in res.get("artifacts") or []] == ([] if so is None else ["verdict"])


def test_the_container_does_not_retry_a_malformed_answer_and_names_its_artifact_from_the_home(disk: Disk) -> None:
    """A malformed end was already re-asked inside the call, so a second container would pay for the same answer;
    and the artifact's path crosses the seam relative to the deploy home, the one frame both sides share."""
    job = a_job(disk, phase="judge", identity={"agent": "judge", "name": "n", "email": "e"}, allowed_writes=())
    pod = Podman(left=_harness_result(phase="judge", agent="judge", outcome="failed:malformed-plan"))
    res = Container(disk.home, _reg(disk), run=pod).execute(job)
    assert res.outcome == "failed:malformed-plan" and len([a for a in pod.seen if a[1] == "run"]) == 1
    art = {"name": "verdict", "sha256": "sha256:" + "0" * 64, "path": "verdict.json"}
    ok = Podman(result=_harness_result(phase="judge", agent="judge", artifacts=[art]))
    got = Container(disk.home, _reg(disk), run=ok).execute(job)
    assert got.artifacts[0].path == f"runs/{job.run_id}/judge/verdict.json"


# -------------------------------------------------------------------------------------- the phases that write nothing


def test_a_phase_that_writes_nothing_is_handed_no_write_surface(disk: Disk, led: Ledger) -> None:
    drv = Shaped(home=disk.home)
    one(disk, led, fresh_run(disk, led), "plan", drv)
    assert drv.seen[-1].allowed_writes == () and drv.seen[-1].phase == "plan"


def test_a_read_only_phase_that_wrote_ends_the_run_uncommitted(disk: Disk, led: Ledger) -> None:
    """[owner, 2026-09-23] a write from plan, refute or judge is not work: the run ends `failed:scope`, and nothing is
    committed to the story branch — where a builder's scope failure keeps its work, this keeps nothing."""
    run_id = fresh_run(disk, led)
    before = git(disk.work, "rev-parse", f"story/{run_id}").strip()
    r = refuses("run.read-only", lambda: one(disk, led, run_id, "plan", Shaped(home=disk.home, writes_in="plan")))
    assert INSIDE in r.detail
    row = led.run(run_id)
    assert row is not None and row["outcome"] == "failed:scope" and row["head_sha"] is None
    assert git(disk.work, "rev-parse", f"story/{run_id}").strip() == before, "a read-only agent's edit was committed"


# ------------------------------------------------------------------------------------------------------ the chain


def test_the_chain_runs_plan_refute_judge_in_one_worktree_and_stops_at_the_judge(
    disk: Disk, led: Ledger, monkeypatch: pytest.MonkeyPatch
) -> None:
    """[owner, 2026-09-23] the chain stops at the judge: the verdict recorded, not acted on, the run in flight. One
    worktree for the whole chain — V4a-i's own efficiency line, testable at last. And each later phase is handed the
    earlier artifacts by the hash the ledger holds."""
    made: list[Path] = []
    real = checkout_mod.worktree

    def counting(*a: Any, **k: Any) -> Path:
        made.append(a[2])
        return real(*a, **k)

    monkeypatch.setattr(checkout_mod, "worktree", counting)
    run_id = fresh_run(disk, led)
    drv = Shaped(home=disk.home)
    row = chain(disk, led, run_id, drv)
    assert [p["phase"] for p in row["phases"]] == ["plan", "refute", "judge"]
    assert row["ended_at"] is None, "the chain stops at the judge and the run stays in flight"
    assert len(made) == 1, f"one worktree per run, not per phase: {made}"
    have = led.artifacts_of(run_id)
    assert set(have) == {"plan", "refutation", "verdict"}
    judge = drv.seen[-1]
    assert [(i.name, i.sha256) for i in judge.inputs] == [
        ("plan", have["plan"]["sha256"]),
        ("refutation", have["refutation"]["sha256"]),
    ]
    assert judge.inputs[0].content == artifacts.Plan.model_validate(PLAN).model_dump(mode="json")
    assert [i.name for i in drv.seen[1].inputs] == ["plan"] and drv.seen[0].inputs == ()
    again = Shaped(home=disk.home)
    assert chain(disk, led, run_id, again)["phases"] == row["phases"] and not again.seen, "nothing left to drive"


def test_the_chain_resumes_from_the_last_phase_the_ledger_holds(disk: Disk, led: Ledger) -> None:
    run_id = fresh_run(disk, led)
    one(disk, led, run_id, "plan", Shaped(home=disk.home))
    drv = Shaped(home=disk.home)
    chain(disk, led, run_id, drv)
    assert [j.phase for j in drv.seen] == ["refute", "judge"]


def test_a_malformed_answer_ends_the_chain_failed_malformed_plan(disk: Disk, led: Ledger) -> None:
    run_id = fresh_run(disk, led)
    drv = Shaped(home=disk.home, answers={**ANSWERS, "refute": None})
    row = chain(disk, led, run_id, drv)
    assert row["outcome"] == "failed:malformed-plan" and [p["phase"] for p in row["phases"]] == ["plan", "refute"]
    assert [j.phase for j in drv.seen] == ["plan", "refute"], "the judge never ran"


def test_an_input_whose_bytes_moved_or_is_missing_is_refused_before_anything_spends(disk: Disk, led: Ledger) -> None:
    """T-B7 (3): the artifact the ledger names must still hash to what it recorded — or the refuter would read a plan
    no plan author wrote. Refused before the adapter is called; the run stays in flight."""
    run_id = fresh_run(disk, led)
    idle = Shaped(home=disk.home)
    refuses("run.artifact-missing", lambda: one(disk, led, run_id, "judge", idle))
    one(disk, led, run_id, "plan", Shaped(home=disk.home))
    path = disk.home / led.artifacts_of(run_id)["plan"]["path"]
    path.write_bytes(path.read_bytes().replace(b"validator", b"validated"))
    refuses("run.artifact-moved", lambda: one(disk, led, run_id, "refute", idle))
    row = led.run(run_id)
    assert not idle.seen and row is not None and row["ended_at"] is None


def test_an_artifact_the_adapter_misstates_is_refused(disk: Disk, led: Ledger) -> None:
    """The adapter's hash is a claim, re-checked against the bytes; so is its naming of the one artifact a phase
    answers with — a structured phase that says `ok` with nothing is not believed."""
    refuses("run.artifact", lambda: one(disk, led, fresh_run(disk, led), "plan", Shaped(home=disk.home, lie=True)))
    nothing = Fake()  # a structured phase answered `ok` with no artifact at all
    refuses("run.artifact", lambda: one(disk, led, fresh_run(disk, led), "plan", nothing))


def test_the_chain_span_wraps_its_phases(disk: Disk, led: Ledger, monkeypatch: pytest.MonkeyPatch) -> None:
    """C-11: `isidium.factory.run.chain` around a chain, each phase's own span inside it."""
    names: list[str] = []
    real = telemetry.span

    def spying(name: str, **attrs: Any) -> Any:
        names.append(name)
        return real(name, **attrs)

    monkeypatch.setattr(telemetry, "span", spying)
    chain(disk, led, fresh_run(disk, led), Shaped(home=disk.home))
    ran = [n for n in names if n.startswith("isidium.factory.run.")]  # the ledger's own spans ride the same module
    assert ran == [runner_mod.CHAIN_SPAN, runner_mod.SPAN, runner_mod.SPAN, runner_mod.SPAN], ran
