"""The four runners `accept` runs a manifest through, in the checkout (03 §1.13, §4.2; Q-W1 ruled 2026-09-09: four)
[L3].

One protocol, four implementations keyed by the runner ids the schema's `[runners]` defaults name — `pytest`,
`shell`, `http`, `file` — and one verdict shape. A runner answers **`pass` or `fail`** with a detail a human can read;
what it cannot do — no pytest on the path, a socket refused, an argv that names no program — is `accept.runner-error`,
never a `fail`: silence is not a verdict (the plan's standing rule about tests that pass on nothing).

`Pattern` (03 §5.3, *"the regex dialect all three targets share"*) is realised here as Python's `re.search`. The
`context.fixture` path the design leaves unspecified is the working directory when `cwd` is absent [proposed]. Every
path in a check is resolved inside the checkout; nothing here writes into the tracking root.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal

from ..core.manifest import Check
from ..core.refusal import Refusal

VerdictWord = Literal["pass", "fail", "manual"]


@dataclass(frozen=True)
class Verdict:
    scenario_id: str
    verdict: VerdictWord
    detail: str


Runner = Callable[[Check, Path], Verdict]

# The bound on what a detail carries of a process's output: a verdict is read at a terminal and written into a
# closure's evidence, and a test suite's whole stdout is neither.
DETAIL_BOUND: Final = 2000


def _tail(s: str) -> str:
    s = s.strip()
    return s if len(s) <= DETAIL_BOUND else "…" + s[-DETAIL_BOUND:]


def _matches(pattern: str, text: str) -> bool:
    return re.search(pattern, text) is not None


def _inside(checkout: Path, rel: str) -> Path:
    p = (checkout / rel).resolve()
    if checkout.resolve() not in (p, *p.parents):
        raise Refusal("accept.runner-error", rel, "a path outside the checkout")
    return p


def file_check(checkout: Path, fc: Mapping[str, Any]) -> tuple[bool, str]:
    """One `FileCheck` (03 §4.2): `path` plus exactly one of the five, judged."""
    p = _inside(checkout, str(fc["path"]))
    if "exists" in fc:
        ok = p.exists() is bool(fc["exists"])
        return ok, f"{fc['path']}: exists={p.exists()}"
    if not p.is_file():
        return False, f"{fc['path']}: no such file"
    data = p.read_bytes()
    if "contains" in fc:
        return str(fc["contains"]).encode("utf-8") in data, f"{fc['path']}: contains {fc['contains']!r}"
    if "matches" in fc:
        # the text form, line endings normalised: a pattern's `$` means the line's end on every platform
        text = data.decode("utf-8", "replace").replace("\r\n", "\n")
        return _matches(str(fc["matches"]), text), f"{fc['path']}: matches {fc['matches']!r}"
    if "sha256" in fc:
        got = hashlib.sha256(data).hexdigest()
        return got == str(fc["sha256"]).removeprefix("sha256:"), f"{fc['path']}: sha256 {got[:12]}…"
    if "equals_file" in fc:
        other = _inside(checkout, str(fc["equals_file"]))
        return other.is_file() and other.read_bytes() == data, f"{fc['path']}: equals {fc['equals_file']}"
    raise Refusal("accept.runner-error", str(fc.get("path")), "a FileCheck with no check")


def _run(argv: list[str], cwd: Path, env: Mapping[str, str] | None) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            argv,
            cwd=cwd,
            env={**os.environ, **(env or {})},
            capture_output=True,
            text=True,
            check=False,
        )
    except (FileNotFoundError, PermissionError, OSError) as e:
        raise Refusal("accept.runner-error", argv[0] if argv else "", str(e)) from None


def _cwd(checkout: Path, context: Mapping[str, Any] | None) -> Path:
    ctx = context or {}
    rel = ctx.get("cwd") or ctx.get("fixture")
    return _inside(checkout, str(rel)) if rel else checkout


def run_pytest(check: Check, checkout: Path) -> Verdict:
    """`test-marker` through pytest: the named test (`path::name`) or the marker, and the scenario's `tests[]` node
    ids. A named test and the `tests[]` share one process; a marker selects over the whole checkout and cannot share
    one with node ids (pytest collects only the ids it is given, then filters them by the marker), so a marker with
    `tests[]` is two processes. Exit 0 is `pass`, 1 (tests failed) is `fail`; any other exit is pytest saying it
    could not run — a usage error, nothing collected, an interrupted session — and that is the runner's error, not a
    verdict."""
    obs = check.params.get("observable") or {}
    runs: list[list[str]] = []
    if obs.get("test"):
        runs.append([str(obs["test"]), *check.tests])
    elif obs.get("marker"):
        runs.append(["-m", str(obs["marker"])])
        if check.tests:
            runs.append(list(check.tests))
    details: list[str] = []
    for args in runs:
        r = _run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--no-header", *args], checkout, None)
        if r.returncode == 1:
            return Verdict(check.scenario_id, "fail", _tail(r.stdout))
        if r.returncode != 0:
            raise Refusal(
                "accept.runner-error", check.scenario_id, f"pytest exit {r.returncode}: {_tail(r.stderr or r.stdout)}"
            )
        details.append(r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "passed")
    return Verdict(check.scenario_id, "pass", _tail("; ".join(details)))


def run_shell(check: Check, checkout: Path) -> Verdict:
    """`command`: the argv in the checkout (or `context.cwd`), then every observable the scenario names."""
    action = check.params.get("action") or {}
    obs = check.params.get("observable") or {}
    ctx = check.params.get("context") or {}
    r = _run([str(a) for a in action.get("run", [])], _cwd(checkout, ctx), ctx.get("env"))
    failures: list[str] = []
    if "exit_code" in obs and r.returncode != int(obs["exit_code"]):
        failures.append(f"exit {r.returncode}, expected {obs['exit_code']}")
    if "stdout_matches" in obs and not _matches(str(obs["stdout_matches"]), r.stdout):
        failures.append(f"stdout does not match {obs['stdout_matches']!r}")
    if "stderr_matches" in obs and not _matches(str(obs["stderr_matches"]), r.stderr):
        failures.append(f"stderr does not match {obs['stderr_matches']!r}")
    for fc in obs.get("files") or []:
        ok, why = file_check(checkout, fc)
        if not ok:
            failures.append(why)
    if failures:
        return Verdict(check.scenario_id, "fail", "; ".join(failures) + " | " + _tail(r.stdout + r.stderr))
    return Verdict(check.scenario_id, "pass", f"exit {r.returncode}")


def run_http(check: Check, checkout: Path) -> Verdict:
    """`http`: one request against `context.base_url`, then `status`, `body_matches`, `headers`."""
    import httpx  # the channel's own dependency, imported where a request is actually made (C-13)

    action = check.params.get("action") or {}
    obs = check.params.get("observable") or {}
    ctx = check.params.get("context") or {}
    body = action.get("body")
    try:
        with httpx.Client(base_url=str(ctx["base_url"]), timeout=30.0) as http:
            r = http.request(
                str(action["method"]).upper(),
                str(action["path"]),
                content=body if isinstance(body, str) else None,
                json=body if isinstance(body, dict) else None,
            )
    except httpx.HTTPError as e:
        raise Refusal("accept.runner-error", check.scenario_id, f"{type(e).__name__}: {e}") from None
    failures: list[str] = []
    if "status" in obs and r.status_code != int(obs["status"]):
        failures.append(f"status {r.status_code}, expected {obs['status']}")
    if "body_matches" in obs and not _matches(str(obs["body_matches"]), r.text):
        failures.append(f"body does not match {obs['body_matches']!r}")
    for k, v in (obs.get("headers") or {}).items():
        if r.headers.get(k) != v:
            failures.append(f"header {k}: {r.headers.get(k)!r}, expected {v!r}")
    if failures:
        return Verdict(check.scenario_id, "fail", "; ".join(failures))
    return Verdict(check.scenario_id, "pass", f"status {r.status_code}")


def run_file(check: Check, checkout: Path) -> Verdict:
    """`file-assert`: `action.run` first when present (its exit is part of the verdict), then the one check."""
    action = check.params.get("action") or {}
    ctx = check.params.get("context") or {}
    if action.get("run"):
        r = _run([str(a) for a in action["run"]], _cwd(checkout, ctx), None)
        if r.returncode != 0:
            return Verdict(check.scenario_id, "fail", f"run exit {r.returncode} | {_tail(r.stdout + r.stderr)}")
    ok, why = file_check(checkout, check.params.get("observable") or {})
    return Verdict(check.scenario_id, "pass" if ok else "fail", why)


RUNNERS: Final[Mapping[str, Runner]] = {"pytest": run_pytest, "shell": run_shell, "http": run_http, "file": run_file}
