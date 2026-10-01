"""Card 22 — found 2026-09-27 → 2026-10-01: four red CI runs (#85's merge commit, #88 twice, #91's merge commit)
on `test_verify_chain.py::test_an_intact_checkout_passes_and_every_document_is_named` and
`test_k7a.py::test_a_governed_card_cannot_leave_the_root_by_rename_at_either_door`, both through
`test_verify_chain`'s `tenant` fixture, whose `shutil.copytree` copies a checkout right after a git pull. A pull
can start git's detached auto-maintenance, which creates and removes `.git/objects/maintenance.lock` (and
`tmp_pack_*` files) while the copy enumerates them.

R1: `tenant_checkout` sets `maintenance.auto` to `false` and `gc.auto` to `0` in the checkout it creates, before any
later git command there. R2: after a pull in such a checkout, no git process is left running in it, so a copy of the
directory meets no lock and no temporary pack.

The probe below is git's own trace2 `child_start` events, scoped to the checkout by its `def_repo` event, rather
than a scan of live processes: the parent git process writes `child_start` *before* it spawns the detached
maintenance child, so the assertion is race-free. A process scan taken after a pull returns is the very race the
card is about — it would see nothing if the child had already finished, and the whole point is that the window
where it has not finished is the window the flake lived in.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from .conftest import git, tenant_checkout


def tracing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point git's trace2 at a fresh directory. Git writes one file per process only when the target already
    exists as a directory — a target that is a plain file is opened in append mode instead, and concurrent
    processes would interleave their lines into it, which is a race in the very test built to prove one is gone."""
    trace = tmp_path / "trace"
    trace.mkdir()
    monkeypatch.setenv("GIT_TRACE2_EVENT", str(trace))
    return trace


def traces(trace_dir: Path) -> list[list[dict[str, Any]]]:
    """Every trace2 file's events, one list per file. A detached child may still be writing its own file while this
    reads, so a line that does not yet parse as JSON is skipped rather than raised."""
    assert trace_dir.is_dir(), (
        f"the trace2 target {trace_dir} is not a directory; git wrote one file instead of one per process"
    )
    files: list[list[dict[str, Any]]] = []
    for p in sorted(trace_dir.iterdir()):
        if not p.is_file():
            continue
        events: list[dict[str, Any]] = []
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                events.append(parsed)
        files.append(events)
    return files


def of_checkout(files: list[list[dict[str, Any]]], work: Path) -> list[list[dict[str, Any]]]:
    """Only the files holding a `def_repo` event whose worktree resolves to `work` — git emits `def_repo` only
    where a worktree is set, so a bare repository's processes (the fixture's own remote, and anything
    `receive-pack` spawns there) are excluded, whether they name the bare path or emit no such event at all."""
    target = work.resolve()
    mine: list[list[dict[str, Any]]] = []
    for events in files:
        for ev in events:
            if ev.get("event") != "def_repo":
                continue
            worktree = str(ev.get("worktree", ""))
            if worktree and Path(worktree).resolve() == target:
                mine.append(events)
                break
    return mine


def started(files: list[list[dict[str, Any]]]) -> list[list[str]]:
    """Every `child_start` event's argv, across the given files."""
    out: list[list[str]] = []
    for events in files:
        for ev in events:
            if ev.get("event") == "child_start":
                out.append([str(t) for t in ev.get("argv", [])])
    return out


def config(work: Path, key: str) -> str:
    """A checkout's own local config value for `key`, or `""` when unset — a named assertion on the value rather
    than a `CalledProcessError` out of conftest's `git`, which checks its exit code."""
    r = subprocess.run(
        ["git", "config", "--local", "--get", key], cwd=work, check=False, capture_output=True, text=True
    )
    return r.stdout.strip()


def test_the_checkout_disables_automatic_maintenance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    trace = tracing(tmp_path, monkeypatch)
    work = tenant_checkout(tmp_path)
    mine = of_checkout(traces(trace), work)
    assert mine, f"the trace2 probe attributed no git process to {work}"

    problems: list[str] = []
    if (got := config(work, "maintenance.auto")) != "false":
        problems.append(f"maintenance.auto in {work} is {got!r}, not 'false'")
    if (got := config(work, "gc.auto")) != "0":
        problems.append(f"gc.auto in {work} is {got!r}, not '0'")
    for argv in started(mine):
        if "maintenance" in argv or "gc" in argv:
            problems.append(f"a maintenance/gc child was started in {work}: {argv}")
    assert not problems, "\n".join(problems)


def test_a_pull_leaves_no_git_process_behind(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    work = tenant_checkout(tmp_path)

    # give the pull something to transfer, the way `built` does when the store pushes
    other = tmp_path / "other"
    git(tmp_path, "clone", "-q", str(tmp_path / "origin.git"), str(other))
    git(other, "config", "user.name", "seed2")
    git(other, "config", "user.email", "seed2@example")
    (other / "more.md").write_text("more\n", encoding="utf-8")
    git(other, "add", "-A")
    git(other, "commit", "-q", "-m", "more")
    git(other, "push", "-q", "origin", "HEAD:main")

    trace = tracing(tmp_path, monkeypatch)
    git(work, "pull", "-q", "--ff-only", "origin", "main")
    mine = of_checkout(traces(trace), work)
    assert mine, f"the trace2 probe attributed no git process to {work}"

    problems: list[str] = []
    for argv in started(mine):
        if "maintenance" in argv or "gc" in argv:
            problems.append(f"a maintenance/gc child was started in {work}: {argv}")

    copy = tmp_path / "copy"
    shutil.copytree(work, copy)
    assert (copy / ".git").is_dir()
    leftover = [
        p.name
        for p in (copy / ".git").rglob("*")
        if p.name in {"maintenance.lock", "gc.log", "gc.pid"} or p.name.startswith("tmp_pack_")
    ]
    if leftover:
        problems.append(f"the copy of {work} still holds: {leftover}")
    assert not problems, "\n".join(problems)
