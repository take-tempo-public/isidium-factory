"""The run's own mutation check [card 43, owner 2026-10-07: *"Mutation check in the run"*, against *"The card's own
test files"*].

Every run of the last weeks was mutation-checked by hand after it ended: the clean tree, then each committed mutation
in place, the card's test file, the file restored. This is that check as a step of the run -- the wrapper's, on the
host, in the run's worktree, like the commit (A2: the phase container blocks whole-suite pytest and is the model's).

**What it runs, and what it does not.** The files the card's own scenarios name (`observable.test`, the part before
`::`), and nothing wider (A1): `tools/mutate.py`'s whole-suite principle is for human and CI runs and is not changed,
and this module neither imports nor calls it. It reads `tools/mutate.py`'s spec format and writes its crash-safety
sidecar in its format (`hold()`'s four keys), so `checkout.repair` -- which already restores a tree a killed phase left
mutated (card 23) -- restores one a killed step left too (C2).

**A mutation that cannot prove anything is a survivor, never skipped** (R4, and the same rule for every other way a
row can fail to prove): a `find` that does not occur exactly once, a file outside the worktree, a `find` equal to its
`replace`, an id shared by two rows, a spec that cannot be read, a red baseline, a step out of time. Each carries its
own closed reason. A mutation is `killed` when the card's tests fail with it applied (pytest exit 1 or 2) or time out;
exit 0 is `survived` (`passed`), and any other exit is `survived` (`runner-error`) because a runner that did not run
the tests killed nothing.

**One clean run comes first.** A tree whose own tests are red (or a host with no pytest) would read every mutation as
killed; the baseline turns that into `baseline-red` survivors instead. It runs lazily -- only when some mutation has
passed every static check and so would be applied.

**One deadline for the whole step** (C-1: the number is the signed `policy.budgets.wall_clock_s`, passed in): taken
when the step starts, and each pytest run -- the baseline too -- gets what remains of it. Anything not yet tried when
it has passed is a `deadline` survivor.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
import tomllib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from isidium.store.core.refusal import Refusal

from . import artifacts, checkout

SPAN: Final = "isidium.factory.mutations"
PHASE: Final = "mutations"
SPEC_DIR: Final = PurePosixPath("tools/mutations")
SPEC_SUFFIX: Final = ".toml"
# pytest's own exit codes: 1 tests failed, 2 interrupted (a collection error the mutation caused reads here). Those and
# a timeout are a kill; 0 is a survivor; every other code is the runner failing to run the tests.
KILLED_EXITS: Final = frozenset({1, 2})
# A run's summary is the last line pytest printed. Capped so that a pathological line cannot bloat the phase's
# artifact, which is hashed, stored and read back by every later phase; 240 holds pytest's longest summary line.
SUMMARY_MAX: Final = 240

Reason = Literal[
    "passed",
    "runner-error",
    "find-not-once",
    "baseline-red",
    "spec-unreadable",
    "outside",
    "empty",
    "duplicate-id",
    "deadline",
    "no-tests",
]
# What each reason tells the builder who is handed the survivor. One table: the finding's `why` is read from it.
WHY: Final[Mapping[str, str]] = {
    "passed": "the card's own tests passed with the mutation applied: no test of the card can see the property",
    "runner-error": "pytest did not run the card's tests (an exit that is neither a pass nor a failure)",
    "find-not-once": "its `find` text does not occur exactly once in the file, so it was not applied",
    "baseline-red": "the card's own tests were red, or did not run, before any mutation: a kill would prove nothing",
    "spec-unreadable": "the spec, or this row of it, cannot be read as tools/mutate.py reads it",
    "outside": "its `file` is not a file inside the run's worktree, so it was not applied",
    "empty": "its `replace` is its `find`: an empty mutation proves nothing",
    "duplicate-id": "its id is shared by another row of the spec, so one answer would stand for two mutations",
    "deadline": "the step's one deadline had passed before it was tried",
    "no-tests": "no scenario of the card names a test file, so there is nothing to check a mutation against",
}


class _Doc(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Run(_Doc):
    """One pytest run: how it exited (`None` for a timeout) and the last line it printed."""

    exit: int | None
    summary: str


class Result(_Doc):
    """One mutation's outcome. `position` is the row's 1-based place in its spec (0 for a spec that could not be read
    at all); `occurrences` is how often `find` occurred, set only when that was counted."""

    spec: str
    id: str
    label: str
    file: str
    position: int = Field(ge=0)
    status: Literal["killed", "survived"]
    reason: Reason | None
    occurrences: int | None
    exit: int | None
    summary: str


class Checked(_Doc):
    """The step's whole answer, and the content of the `mutations` phase row's one artifact (R2)."""

    tests: tuple[str, ...]
    baseline: Run | None
    results: tuple[Result, ...]

    @property
    def survivors(self) -> tuple[Result, ...]:
        return tuple(r for r in self.results if r.status == "survived")


def specs(payload: Mapping[str, Any]) -> tuple[str, ...]:
    """The card's mutation specs: its declared surfaces that sit directly in `tools/mutations/` and end `.toml`."""
    surfaces = (payload.get("constraints") or {}).get("surfaces") or ()
    return tuple(
        str(s)
        for s in surfaces
        if PurePosixPath(str(s)).parent == SPEC_DIR and PurePosixPath(str(s)).suffix == SPEC_SUFFIX
    )


def tests_of(payload: Mapping[str, Any]) -> tuple[str, ...]:
    """The card's own acceptance test files: the part before `::` of every scenario's `observable.test`, distinct, in
    the card's order."""
    out: dict[str, None] = {}
    for sc in ((payload.get("gated") or {}).get("acceptance") or {}).get("scenarios") or ():
        test = (sc.get("observable") or {}).get("test")
        if isinstance(test, str) and test:
            out[test.split("::", 1)[0]] = None
    return tuple(out)


def _scenario_ids(payload: Mapping[str, Any]) -> tuple[str, ...]:
    scenarios = ((payload.get("gated") or {}).get("acceptance") or {}).get("scenarios") or ()
    return tuple(str(s["id"]) for s in scenarios)


@dataclass(frozen=True)
class _Row:
    position: int
    id: str
    label: str
    file: str
    find: bytes
    replace: bytes


def check(work: Path, payload: Mapping[str, Any], *, deadline_s: int, clock: Callable[[], float]) -> Checked:
    """R1: every `[[mutation]]` of the card's specs, applied one at a time in `work`, the card's own test files run,
    the file restored byte for byte. `clock` is monotonic seconds, passed in so the deadline is testable."""
    end = clock() + deadline_s
    tests = tests_of(payload)
    results: list[Result] = []
    pending: list[tuple[str, _Row, Path, int]] = []  # (spec, row, file, occurrences): passed every static check
    for spec in specs(payload):
        rows = _rows(work, spec, results)
        ids = [r.id for r in rows]
        for row in rows:
            file = _resolve(work, row.file)
            if ids.count(row.id) > 1:
                results.append(_survived(spec, row, "duplicate-id"))
            elif file is None:
                results.append(_survived(spec, row, "outside"))
            elif row.find == row.replace:
                results.append(_survived(spec, row, "empty"))
            else:
                n = file.read_bytes().count(row.find)
                if n != 1:
                    results.append(_survived(spec, row, "find-not-once", occurrences=n))
                elif not tests:
                    results.append(_survived(spec, row, "no-tests"))
                else:
                    pending.append((spec, row, file, n))
    baseline: Run | None = None
    if pending:
        baseline = _pytest(work, tests, end - clock())
        if baseline.exit != 0:
            for spec, row, _file, n in pending:
                results.append(_survived(spec, row, "baseline-red", occurrences=n, ran=baseline))
        else:
            for spec, row, file, n in pending:
                left = end - clock()
                if left <= 0:
                    results.append(_survived(spec, row, "deadline", occurrences=n))
                else:
                    results.append(_apply(work, spec, row, file, n, tests, left))
    # Results were appended by kind; the record reads in the order the card declares its specs and the spec its rows.
    named = {s: i for i, s in enumerate(specs(payload))}
    ordered = sorted(results, key=lambda r: (named[r.spec], r.position))
    return Checked(tests=tests, baseline=baseline, results=tuple(ordered))


def _rows(work: Path, spec: str, results: list[Result]) -> list[_Row]:
    """The spec's rows, as `tools/mutate.py`'s `load_spec` reads them. A spec or a row that does not read is a
    survivor appended to `results`, and the rows that do read are returned."""

    def unreadable(position: int, ident: str, why: str) -> None:
        results.append(
            Result(
                spec=spec,
                id=ident,
                label=why,
                file="",
                position=position,
                status="survived",
                reason="spec-unreadable",
                occurrences=None,
                exit=None,
                summary=why,
            )
        )

    try:
        doc = tomllib.loads((work / spec).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:  # tomllib's decode errors are ValueErrors; so is a bad UTF-8 byte
        unreadable(0, "(spec)", f"{type(e).__name__}: {e}")
        return []
    raw = doc.get("mutation")
    if not isinstance(raw, list) or not raw:
        unreadable(0, "(spec)", "no [[mutation]] tables")
        return []
    out: list[_Row] = []
    for position, item in enumerate(raw, start=1):
        try:
            out.append(
                _Row(
                    position=position,
                    id=_text(item, "id"),
                    label=_text(item, "label"),
                    file=_text(item, "file"),
                    find=_text(item, "find").encode("utf-8"),
                    replace=_text(item, "replace").encode("utf-8"),
                )
            )
        except (KeyError, TypeError) as e:
            ident = item.get("id") if isinstance(item, dict) else None
            unreadable(position, ident if isinstance(ident, str) else f"row-{position}", f"cannot read the row: {e}")
    return out


def _text(item: Any, key: str) -> str:
    value = item[key]
    if not isinstance(value, str):
        raise TypeError(f"`{key}` is not a string")
    return value


def _resolve(work: Path, rel: str) -> Path | None:
    """The mutation's file when it is a file inside the worktree and not git's own, else `None`. The spec is
    committed work, not trusted work: its `file` is checked the way `checkout.repair` checks a marker's."""
    root = work.resolve()
    target = (work / rel).resolve()
    if not target.is_relative_to(root) or target.relative_to(root).parts[:1] in ((), (".git",)):
        return None
    return target if target.is_file() else None


def _survived(
    spec: str, row: _Row, reason: Reason, *, occurrences: int | None = None, ran: Run | None = None
) -> Result:
    return Result(
        spec=spec,
        id=row.id,
        label=row.label,
        file=row.file,
        position=row.position,
        status="survived",
        reason=reason,
        occurrences=occurrences,
        exit=None if ran is None else ran.exit,
        summary=WHY[reason] if ran is None else ran.summary,
    )


def _apply(
    work: Path, spec: str, row: _Row, file: Path, occurrences: int, tests: Sequence[str], timeout_s: float
) -> Result:
    """One mutation: the pristine bytes held on disk **before** the file is touched, the card's tests run, the file
    put back from the snapshot and the restore verified (`tools/mutate.py`'s `hold` and `release`, in its format)."""
    pristine = file.read_bytes()
    digest = hashlib.sha256(pristine).hexdigest()
    marker = work / checkout.MARKER
    marker.write_text(
        json.dumps(
            {
                "id": row.id,
                "file": file.relative_to(work.resolve()).as_posix(),
                "sha256": digest,
                "pristine": base64.b64encode(pristine).decode("ascii"),
            }
        ),
        encoding="utf-8",
    )
    try:
        file.write_bytes(pristine.replace(row.find, row.replace))
        ran = _pytest(work, tests, timeout_s)
    finally:
        file.write_bytes(pristine)
        restored = hashlib.sha256(file.read_bytes()).hexdigest()
    if restored != digest:  # the marker stays: `checkout.repair` has the pristine bytes and a digest to hold them to
        raise Refusal("run.mutation-restore", row.file, f"did not restore: {restored} != {digest}")
    marker.unlink(missing_ok=True)
    killed = ran.exit is None or ran.exit in KILLED_EXITS
    reason: Reason | None = None if killed else ("passed" if ran.exit == 0 else "runner-error")
    return Result(
        spec=spec,
        id=row.id,
        label=row.label,
        file=row.file,
        position=row.position,
        status="killed" if killed else "survived",
        reason=reason,
        occurrences=occurrences,
        exit=ran.exit,
        summary=ran.summary,
    )


def _pytest(work: Path, tests: Sequence[str], timeout_s: float) -> Run:
    """The card's own test files, in `work`. The cache provider is off and bytecode is not written so the run leaves
    nothing in a tree whose next commit is the builder's. Output is decoded as UTF-8 with replacement: a run's verdict
    is its exit, and one odd byte in a test name must not end the step."""
    argv = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--no-header", *tests]
    if timeout_s <= 0:
        return Run(exit=None, summary="timeout after 0s")
    try:
        done = subprocess.run(
            argv,
            cwd=work,
            capture_output=True,
            check=False,
            timeout=timeout_s,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
    except subprocess.TimeoutExpired:
        return Run(exit=None, summary=f"timeout after {timeout_s:.0f}s")
    except OSError as e:
        raise Refusal("run.mutations-runner", str(work), f"pytest could not be started: {e}") from None
    text = (done.stdout or b"").decode("utf-8", errors="replace") or (done.stderr or b"").decode(
        "utf-8", errors="replace"
    )
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return Run(exit=done.returncode, summary=(lines[-1] if lines else "")[:SUMMARY_MAX])


def finding_id(r: Result) -> str:
    """A survivor's finding id: the spec and the mutation, and -- for a shared id -- the row's position as well, so
    that every row is answered and `ReconcileReport.unanswered` stays exact."""
    base = f"{r.spec}#{r.id}"
    return f"{base}#{r.position}" if r.reason == "duplicate-id" else base


def findings(checked: Checked, payload: Mapping[str, Any]) -> dict[str, Any]:
    """R3: the survivors as the review gate's own `Findings` artifact -- one blocking finding per survivor, naming the
    mutation -- so reconcile's prompt, its inputs and the harness's unanswered-finding check all stay as they are."""
    scenarios = _scenario_ids(payload) or (PHASE,)
    ran = ", ".join(checked.tests) or "none"
    found = [
        artifacts.ReviewFinding(
            id=finding_id(r),
            severity="blocking",
            claim=f"mutation {r.id} ({r.label}) survives: {WHY[str(r.reason)]}",
            location=r.file or r.spec,
            why=f"{r.summary} -- checked against {ran}",
            bears_on=", ".join(scenarios),
        )
        for r in checked.survivors
    ]
    doc = artifacts.Findings(
        traceability=tuple(
            artifacts.Evidence(id=s, evidence=f"the mutation check ran the card's test files: {ran}") for s in scenarios
        ),
        findings=tuple(found),
    )
    return doc.model_dump(mode="json")


def phase_row(duration_ms: int, made: Sequence[Mapping[str, str]], named: Mapping[str, Any]) -> dict[str, Any]:
    """The `mutations` phase row (R2, C4): no agent, no model, no effort, no prompt, no tokens and no cost -- `None`
    each, never a 0 laundered in (card 19) -- and no billing class, since the step draws on no lane."""
    return {
        "phase": PHASE,
        "agent": None,
        "model": None,
        "effort": None,
        "prompt_version": None,
        "tokens": None,
        "cost_micro": None,
        "duration_ms": duration_ms,
        "outcome": "ok",
        "artifacts": [dict(a) for a in made],
        "touched": [],
        "billing_class": None,
        **named,
    }
