"""Card 43 — a run checks its card's committed mutations against the card's own tests before it ends, and a survivor
goes to reconcile [owner, 2026-10-07: *"Mutation check in the run"*].

The card is read through the payload (a patch on `runner._payload`, after the real one has been re-assembled and its
hash checked): `tools/mutations/demo.toml` is added to its surfaces and its second scenario names `tests/test_demo.py`.
The spec, the file it mutates, the test that kills and a decoy test that no scenario names are committed onto the
run's story branch before the chain starts, so the step runs on a real worktree and a real pytest.

What each test discriminates, and what fails today (no `mutations` step exists, so the chain ends at the review):

- **S1** only the card's own file is run (the decoy's kill is not counted), each mutation is applied alone with the
  pristine bytes held on disk beforehand, and the file is byte for byte as it was afterwards.
- **S2** the results are a phase row with no agent, model, tokens or cost, named by hash, and the step's span is not
  under `isidium.factory.run.*`.
- **S3** a survivor is handed to reconcile once as a blocking finding naming the mutation; a second survivor ends the
  run `failed:gate` with its work kept; a stronger test from reconcile ends the check clean.
- **S4** a `find` that does not occur once (and an id shared by two rows) is a survivor, never skipped, and nothing is
  applied for it.
- the gate's own reading (`review_gate_done`, `next_step`) of an open mutation round, and the step's one deadline and
  red baseline, are tested directly: neither needs a chain.
"""

from __future__ import annotations

import base64
import copy
import dataclasses
import hashlib
import json
import subprocess
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from isidium.factory import artifacts, gate
from isidium.factory import checkout as checkout_mod
from isidium.factory import mutations as mutations_mod
from isidium.factory import runner as runner_mod
from isidium.factory.adapter import PhaseResult, RunJob
from isidium.factory.ledger import Ledger
from isidium.store.core import telemetry

from ..store.conftest import git
from .test_v4a import INSIDE, Disk, disk, fresh_run
from .test_v4a_ii import ANSWERS, Shaped, chain, led

__all__ = ["disk", "led"]  # the V4a tenant and its ledger, as test_v4a_ii builds them

SPEC = "tools/mutations/demo.toml"
RULE = "client/cards/demo_rule.py"
TEST = "tests/test_demo.py"
RULE_TEXT = "LIMIT = 10\n\n\ndef within(n):\n    return n <= LIMIT\n\n\ndef doubled(n):\n    return n * 2\n"
LOADER = (
    "import importlib.util\nimport pathlib\n\n\ndef load():\n"
    "    path = pathlib.Path(__file__).resolve().parents[1] / 'client' / 'cards' / 'demo_rule.py'\n"
    "    spec = importlib.util.spec_from_file_location('demo_rule', path)\n"
    "    module = importlib.util.module_from_spec(spec)\n    spec.loader.exec_module(module)\n    return module\n"
)
TEST_TEXT = LOADER + "\n\ndef test_it():\n    rule = load()\n    assert rule.within(10) and not rule.within(11)\n"
# What no scenario names: it would kill M2 if it ran, which is how S1 shows that it did not.
DECOY_TEXT = LOADER + "\n\ndef test_doubled():\n    assert load().doubled(2) == 4\n"
STRONGER = TEST_TEXT + "\n\ndef test_doubled():\n    assert load().doubled(2) == 4\n"

M1: dict[str, str] = {
    "id": "M1",
    "label": "the limit is inclusive -- lost",
    "file": RULE,
    "find": "return n <= LIMIT",
    "replace": "return n < LIMIT",
}
M2: dict[str, str] = {
    "id": "M2",
    "label": "doubled triples",
    "file": RULE,
    "find": "return n * 2",
    "replace": "return n * 3",
}


def spec(*rows: Mapping[str, str]) -> str:
    return "".join(
        "[[mutation]]\n" + "".join(f"{k} = {json.dumps(v)}\n" for k, v in row.items()) + "\n" for row in rows
    )


def seed(disk: Disk, run_id: str, files: Mapping[str, str]) -> None:
    """Files committed onto the run's story branch before the chain cuts its worktree from it."""
    tree = disk.home / "seed" / run_id
    git(disk.work, "worktree", "add", str(tree), f"story/{run_id}")
    for rel, text in files.items():
        (tree / rel).parent.mkdir(parents=True, exist_ok=True)
        (tree / rel).write_text(text, encoding="utf-8", newline="\n")
    git(tree, "add", "-A")
    git(tree, "-c", "user.name=seed", "-c", "user.email=seed@example", "commit", "-q", "-m", "seed the demo")
    git(disk.work, "worktree", "remove", "--force", str(tree))


def declare(monkeypatch: pytest.MonkeyPatch) -> None:
    """The card as the run reads it: the spec among its surfaces, and `tests/test_demo.py` named by S2."""
    real = runner_mod._payload

    def patched(*args: Any) -> Any:
        p = real(*args)
        value = copy.deepcopy(dict(p.value))
        value["constraints"]["surfaces"] = [*value["constraints"]["surfaces"], SPEC]
        for sc in value["gated"]["acceptance"]["scenarios"]:
            if sc["id"] == "S2":
                sc["observable"]["test"] = f"{TEST}::test_it"
        return dataclasses.replace(p, value=value)

    monkeypatch.setattr(runner_mod, "_payload", patched)


def started(disk: Disk, led: Ledger, monkeypatch: pytest.MonkeyPatch, *rows: Mapping[str, str]) -> str:
    run_id = fresh_run(disk, led)
    seed(disk, run_id, {SPEC: spec(*rows), RULE: RULE_TEXT, TEST: TEST_TEXT, "tests/test_decoy.py": DECOY_TEXT})
    declare(monkeypatch)
    return run_id


@dataclass
class Spy:
    """Every pytest the step starts, with the worktree as it stood while that pytest ran."""

    runs: list[dict[str, Any]] = field(default_factory=list)
    real: Any = subprocess.run

    def __call__(self, argv: Sequence[str], **kw: Any) -> Any:
        if list(argv[1:3]) == ["-m", "pytest"]:
            tree = Path(kw["cwd"])
            marker = tree / checkout_mod.MARKER
            self.runs.append(
                {
                    "argv": list(argv),
                    "file": (tree / RULE).read_bytes(),
                    "marker": json.loads(marker.read_text(encoding="utf-8")) if marker.is_file() else None,
                    "timeout": kw.get("timeout"),
                }
            )
        return self.real(argv, **kw)


@pytest.fixture
def spy(monkeypatch: pytest.MonkeyPatch) -> Iterator[Spy]:
    s = Spy()
    monkeypatch.setattr(subprocess, "run", s)
    yield s


def report(*ids: str) -> dict[str, Any]:
    return {"rows": [{"id": i, "disposition": "refuted", "note": "not this card's"} for i in ids]}


def checked_of(disk: Disk, led: Ledger, run_id: str, n: int = 1) -> mutations_mod.Checked:
    art = _rows_artifacts(led, run_id)[n - 1]
    data = (disk.home / art["path"]).read_bytes()
    assert artifacts.sha256(data) == art["sha256"]
    return mutations_mod.Checked.model_validate_json(data)


def _rows_artifacts(led: Ledger, run_id: str) -> list[dict[str, str]]:
    return [
        a
        for ev in led.events_of(run_id)
        if ev["kind"] == "phase" and ev["data"]["phase"] == mutations_mod.PHASE
        for a in ev["data"]["artifacts"]
    ]


def phases(row: Mapping[str, Any]) -> list[str]:
    return [p["phase"] for p in row["phases"]]


# ------------------------------------------------------------------------------------------------------------ S1


def test_a_cards_mutations_are_checked_against_its_own_tests(
    disk: Disk, led: Ledger, monkeypatch: pytest.MonkeyPatch, spy: Spy
) -> None:
    run_id = started(disk, led, monkeypatch, M1, M2)
    left: dict[str, Any] = {}
    real_remove = checkout_mod.worktree_remove

    def remove(repo: Path, at: Path) -> None:
        left["file"] = (at / RULE).read_bytes()
        left["marker"] = (at / checkout_mod.MARKER).exists()
        left["touched"] = checkout_mod.touched(at)
        real_remove(repo, at)

    monkeypatch.setattr(checkout_mod, "worktree_remove", remove)
    drv = Shaped(home=disk.home, answers={**ANSWERS, "reconcile": report(f"{SPEC}#M2")})
    row = chain(disk, led, run_id, drv)

    # (e) after the review gate's end, and (d) the card's file killed M1 and could not see M2
    assert phases(row)[:6] == ["plan", "refute", "judge", "build", "review", "mutations"]
    first = checked_of(disk, led, run_id)
    by_id = {r.id: r for r in first.results}
    assert by_id["M1"].status == "killed" and by_id["M2"].status == "survived" and by_id["M2"].reason == "passed"
    assert first.tests == (TEST,) and first.baseline is not None and first.baseline.exit == 0

    # (a) the card's own file, never a bare pytest and never tools/mutate.py
    assert len(spy.runs) >= 3
    assert all(r["argv"][-1:] == [TEST] and "mutate.py" not in " ".join(r["argv"]) for r in spy.runs)

    # (b) the baseline is clean; each mutation runs alone, with the pristine bytes already on disk in `hold()`'s format
    baseline, m1, m2 = spy.runs[:3]
    assert baseline["file"] == RULE_TEXT.encode() and baseline["marker"] is None
    assert m1["file"] == RULE_TEXT.replace("n <= LIMIT", "n < LIMIT").encode()
    assert m2["file"] == RULE_TEXT.replace("n * 2", "n * 3").encode()
    for ran, name in ((m1, "M1"), (m2, "M2")):
        saved = ran["marker"]
        assert saved is not None and set(saved) == {"id", "file", "sha256", "pristine"} and saved["id"] == name
        assert saved["file"] == RULE and base64.b64decode(saved["pristine"]) == RULE_TEXT.encode()
        assert saved["sha256"] == hashlib.sha256(RULE_TEXT.encode()).hexdigest()

    # (c) restored byte for byte, marker gone, nothing left for the next commit
    assert left == {"file": RULE_TEXT.encode(), "marker": False, "touched": ()}


# ------------------------------------------------------------------------------------------------------------ S2


def test_the_results_are_a_mutations_phase_row(
    disk: Disk, led: Ledger, monkeypatch: pytest.MonkeyPatch, spy: Spy
) -> None:
    run_id = started(disk, led, monkeypatch, M1)
    names: list[str] = []
    real = telemetry.span

    def spying(name: str, **attrs: Any) -> Any:
        names.append(name)
        return real(name, **attrs)

    monkeypatch.setattr(telemetry, "span", spying)
    row = chain(disk, led, run_id, Shaped(home=disk.home))

    assert phases(row)[-2:] == ["review", "mutations"] and row["ended_at"] is None
    last = row["phases"][-1]
    assert {
        k: last[k] for k in ("agent", "model", "effort", "prompt_version", "tokens", "cost_micro")
    } == dict.fromkeys(("agent", "model", "effort", "prompt_version", "tokens", "cost_micro"))
    event = [e for e in led.events_of(run_id) if e["kind"] == "phase"][-1]["data"]
    assert event["phase"] == "mutations" and event["billing_class"] is None and event["touched"] == []
    assert [a["name"] for a in event["artifacts"]] == ["mutations"]
    checked = checked_of(disk, led, run_id)  # also re-hashed against the ledger's record
    assert [(r.id, r.status) for r in checked.results] == [("M1", "killed")] and not checked.survivors
    assert row["billing_class"] == "plan", "the step neither blanks nor invents the lane the model phases drew on"
    ran = [n for n in names if n.startswith("isidium.factory.run.")]
    assert ran == [runner_mod.CHAIN_SPAN, *[runner_mod.SPAN] * 5], "the step's span is not under run.*"
    assert mutations_mod.SPAN in names and not mutations_mod.SPAN.startswith("isidium.factory.run.")


# ------------------------------------------------------------------------------------------------------------ S3


@dataclass
class Writes(Shaped):
    """Reconcile writes `files` into the worktree, as the builder would, before answering."""

    files: dict[str, str] = field(default_factory=dict)

    def execute(self, job: RunJob) -> PhaseResult:
        if job.phase == "reconcile":
            for rel, text in self.files.items():
                (Path(job.worktree) / rel).parent.mkdir(parents=True, exist_ok=True)
                (Path(job.worktree) / rel).write_text(text, encoding="utf-8", newline="\n")
        return super().execute(job)


def test_a_survivor_goes_to_reconcile_then_ends_the_run(
    disk: Disk, led: Ledger, monkeypatch: pytest.MonkeyPatch, spy: Spy
) -> None:
    run_id = started(disk, led, monkeypatch, M2)
    finding = f"{SPEC}#M2"
    drv = Writes(
        home=disk.home,
        answers={**ANSWERS, "reconcile": report(finding)},
        files={INSIDE: "# reconcile's edit\n"},
    )
    row = chain(disk, led, run_id, drv)

    assert phases(row)[-4:] == ["review", "mutations", "reconcile", "mutations"], "no review second pass between"
    reconcile = next(j for j in drv.seen if j.phase == "reconcile")
    assert reconcile.identity.agent == "builder" and reconcile.allowed_writes == (INSIDE, "tests/")
    found = artifacts.Findings.model_validate(next(i.content for i in reconcile.inputs if i.name == "findings"))
    assert [(f.id, f.severity) for f in found.findings] == [(finding, "blocking")]
    assert "M2" in found.findings[0].claim and found.findings[0].location == RULE
    assert (disk.home / "runs" / run_id).is_dir() and len(_rows_artifacts(led, run_id)) == 2

    assert row["outcome"] == "failed:gate" and row["ended_at"] is not None
    tip = git(disk.work, "rev-parse", f"story/{run_id}").strip()
    assert row["head_sha"] == tip, "the work is kept: the reconcile commit is the run's head"
    ended = [e for e in led.events_of(run_id) if e["kind"] == "ended"][-1]["data"]
    assert ended["mutations"] == "survived" and ended["survivors"] == [finding]
    assert [j.phase for j in drv.seen].count("reconcile") == 1, "one reconcile round, then the end"


def test_a_stronger_test_from_reconcile_ends_the_check_clean(
    disk: Disk, led: Ledger, monkeypatch: pytest.MonkeyPatch, spy: Spy
) -> None:
    run_id = started(disk, led, monkeypatch, M2)
    # the card's own file is now the one that sees `doubled`: the second check kills what the first could not
    drv = Writes(home=disk.home, answers={**ANSWERS, "reconcile": report(f"{SPEC}#M2")}, files={TEST: STRONGER})
    row = chain(disk, led, run_id, drv)
    assert phases(row)[-3:] == ["mutations", "reconcile", "mutations"] and row["ended_at"] is None
    assert [r.status for r in checked_of(disk, led, run_id, 1).results] == ["survived"]
    assert [r.status for r in checked_of(disk, led, run_id, 2).results] == ["killed"]


# ------------------------------------------------------------------------------------------------------------ S4


def test_an_unmatched_find_is_a_survivor(disk: Disk, led: Ledger, monkeypatch: pytest.MonkeyPatch, spy: Spy) -> None:
    gone = {**M1, "id": "M3", "find": "return n >= LIMIT"}
    twice = {**M1, "id": "M4", "find": "return n"}
    dup_a = {**M1, "id": "M5", "find": "LIMIT = 10", "replace": "LIMIT = 11"}
    dup_b = {**M1, "id": "M5", "find": "LIMIT = 10", "replace": "LIMIT = 12"}
    run_id = started(disk, led, monkeypatch, gone, twice, dup_a, dup_b)
    ids = [f"{SPEC}#M3", f"{SPEC}#M4", f"{SPEC}#M5#3", f"{SPEC}#M5#4"]
    drv = Shaped(home=disk.home, answers={**ANSWERS, "reconcile": report(*ids)})
    row = chain(disk, led, run_id, drv)

    checked = checked_of(disk, led, run_id)
    got = [(r.id, r.status, r.reason, r.occurrences) for r in checked.results]
    assert got == [
        ("M3", "survived", "find-not-once", 0),
        ("M4", "survived", "find-not-once", 2),
        ("M5", "survived", "duplicate-id", None),
        ("M5", "survived", "duplicate-id", None),
    ], "none skipped"
    assert spy.runs == [], "nothing was applied, so nothing was run, not even a baseline"
    reconcile = next(j for j in drv.seen if j.phase == "reconcile")
    found = artifacts.Findings.model_validate(next(i.content for i in reconcile.inputs if i.name == "findings"))
    assert [f.id for f in found.findings] == ids and all(f.severity == "blocking" for f in found.findings)
    assert row["outcome"] == "failed:gate", "still survivors after the one reconcile round"


# ------------------------------------------------------------------------------- the step on its own, no chain


def worktree_with(tmp_path: Path, *rows: Mapping[str, str]) -> Path:
    (tmp_path / "tools" / "mutations").mkdir(parents=True)
    (tmp_path / SPEC).write_text(spec(*rows), encoding="utf-8")
    (tmp_path / RULE).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / RULE).write_text(RULE_TEXT, encoding="utf-8")
    return tmp_path


PAYLOAD: dict[str, Any] = {
    "constraints": {"surfaces": [SPEC]},
    "gated": {"acceptance": {"scenarios": [{"id": "S2", "observable": {"test": f"{TEST}::test_it"}}]}},
}


@dataclass
class Clock:
    now: float = 0.0

    def __call__(self) -> float:
        return self.now


@dataclass
class Scripted:
    """`subprocess.run` as a script of (exit, seconds it took, timed out) -- no real pytest, no real hang."""

    clock: Clock
    script: list[tuple[int, float, bool]]
    timeouts: list[float] = field(default_factory=list)

    def __call__(self, argv: Sequence[str], **kw: Any) -> Any:
        code, took, hangs = self.script.pop(0)
        self.timeouts.append(kw["timeout"])
        self.clock.now += kw["timeout"] if hangs else took
        if hangs:
            raise subprocess.TimeoutExpired(list(argv), kw["timeout"])
        return subprocess.CompletedProcess(list(argv), code, stdout=f"exit {code}\n".encode(), stderr=b"")


def test_the_step_has_one_deadline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """R4's never-skipped: a step out of time records what it did not try as a survivor. The baseline and M1 draw on
    one deadline of 10s (4s, then the 6s that remain, which M1 spends hanging); M2 finds none left."""
    work = worktree_with(tmp_path, M1, M2)
    clock = Clock()
    run = Scripted(clock, [(0, 4.0, False), (1, 0.0, True)])
    monkeypatch.setattr(subprocess, "run", run)
    checked = mutations_mod.check(work, PAYLOAD, deadline_s=10, clock=clock)
    assert run.timeouts == [10.0, 6.0] and all(t <= 10 for t in run.timeouts)
    m1, m2 = checked.results
    assert (m1.id, m1.status, m1.exit, m1.summary) == ("M1", "killed", None, "timeout after 6s")
    assert (m2.id, m2.status, m2.reason, m2.occurrences) == ("M2", "survived", "deadline", 1)
    assert (work / RULE).read_text(encoding="utf-8") == RULE_TEXT and not (work / checkout_mod.MARKER).exists()


def test_a_red_baseline_makes_every_mutation_a_survivor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A tree whose own tests are red would read every mutation as killed; the clean run first is what stops that."""
    work = worktree_with(tmp_path, M1, M2)
    run = Scripted(Clock(), [(1, 1.0, False)])
    monkeypatch.setattr(subprocess, "run", run)
    checked = mutations_mod.check(work, PAYLOAD, deadline_s=60, clock=Clock())
    assert [(r.id, r.status, r.reason) for r in checked.results] == [
        ("M1", "survived", "baseline-red"),
        ("M2", "survived", "baseline-red"),
    ]
    assert len(run.timeouts) == 1 and (work / RULE).read_text(encoding="utf-8") == RULE_TEXT


def test_a_row_or_a_spec_that_cannot_be_read_is_a_survivor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    work = worktree_with(tmp_path, {"id": "M1", "label": "no find or replace", "file": RULE})
    outside = {**M1, "id": "M6", "file": "../elsewhere.py"}
    same = {**M1, "id": "M7", "replace": M1["find"]}
    (work / SPEC).write_text(spec(outside, same) + (work / SPEC).read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(subprocess, "run", Scripted(Clock(), []))
    checked = mutations_mod.check(work, PAYLOAD, deadline_s=60, clock=Clock())
    assert [(r.id, r.reason) for r in checked.results] == [
        ("M6", "outside"),
        ("M7", "empty"),
        ("M1", "spec-unreadable"),
    ]
    (work / SPEC).write_text("[[mutation\n", encoding="utf-8")
    bad = mutations_mod.check(work, PAYLOAD, deadline_s=60, clock=Clock())
    assert [(r.id, r.reason) for r in bad.results] == [("(spec)", "spec-unreadable")]
    assert mutations_mod.check(work, {**PAYLOAD, "gated": {}}, deadline_s=60, clock=Clock()).tests == ()


# --------------------------------------------------------------------------- the gate's reading of an open round


def done(phase: str, value: Mapping[str, Any] | None = None) -> gate.Done:
    return gate.Done(phase, value)


CLEAN_REVIEW: dict[str, Any] = {"traceability": [{"id": "S1", "evidence": "shown"}], "findings": []}


def result_doc(*statuses: str) -> dict[str, Any]:
    rows = [
        mutations_mod.Result(
            spec=SPEC,
            id=f"M{i}",
            label="x",
            file=RULE,
            position=i,
            status="killed" if s == "killed" else "survived",
            reason=None if s == "killed" else "passed",
            occurrences=1,
            exit=1 if s == "killed" else 0,
            summary="s",
        )
        for i, s in enumerate(statuses, start=1)
    ]
    return mutations_mod.Checked(tests=(TEST,), baseline=None, results=tuple(rows)).model_dump(mode="json")


def test_an_open_mutation_round_is_not_a_finished_review_gate() -> None:
    base = [done("build"), done("review", CLEAN_REVIEW)]
    survivor, clean = done("mutations", result_doc("survived")), done("mutations", result_doc("killed"))
    assert gate.review_gate_done(base), "no mutations row: the review-only reading is unchanged"
    assert not gate.review_gate_done([*base, survivor])
    assert not gate.review_gate_done([*base, survivor, done("reconcile", report("x"))])
    assert gate.review_gate_done([*base, clean])
    assert gate.review_gate_done([*base, survivor, done("reconcile", report("x")), clean])
    assert gate.review_gate_done([*base, survivor, done("reconcile", report("x")), survivor]), "ended by the runner"


def test_next_step_follows_a_finished_review_with_the_check_only_when_the_card_has_specs() -> None:
    base = [done("build"), done("review", CLEAN_REVIEW)]
    with_specs, without = {"constraints": {"surfaces": [SPEC, RULE]}}, {"constraints": {"surfaces": [RULE]}}
    assert gate.next_step(base, with_specs) == gate.Step("phase", mutations_mod.PHASE)
    assert gate.next_step(base, without).kind == "done"
    survivor = done("mutations", result_doc("killed", "survived"))
    assert gate.next_step([*base, survivor], with_specs) == gate.Step("phase", "reconcile")
    answered = [*base, survivor, done("reconcile", report("x"))]
    assert gate.next_step(answered, with_specs) == gate.Step("phase", mutations_mod.PHASE), "not a second review"
    assert gate.next_step([*answered, survivor], with_specs).kind == "done"
    assert gate.next_step([*base, done("mutations", result_doc("killed"))], with_specs).kind == "done"
