"""Card 19 — a build phase cannot run the whole test suite, a harness that dies with no result records what it
spent honestly, and the container's process limit is podman's own default, named rather than inherited.

`r-18` and `r-19` both ran the whole suite inside the build container (`pytest tests`); it outlived their tool
timeout, kept running in the background, and exhausted the container's process table (`signal 6`, `Cannot fork`)
before either could write a result — and both attempts' records read `cost 0`, `duration 0`. Three fixes, three
groups of tests here: `guard.whole_suite` blocks a whole-suite pytest at write time and counts the block (R1, R2),
the rendered settings route `Bash` through the same hook (R3), a harness that dies with no result records its real
duration and an unknown (never zero) cost (R4, R5), and the container adapter states podman's own `--pids-limit`
explicitly (R6).
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from isidium.factory import adapter as adapter_mod
from isidium.factory import container as container_mod
from isidium.factory import guard, harness, render
from isidium.factory.container import Container

from .test_v4a import Child, Disk, Podman, _reg, a_job, disk

__all__ = ["disk"]  # the V4a tenant, built once for this module too

# This card's own declared surfaces (a subset, enough to discriminate a match from a miss): the guard module itself
# is not a test path, the test file and the test directory both are.
SURFACES = (
    "packages/isidium-factory/src/isidium/factory/guard.py",
    "tests/factory/test_build_resource_guards.py",
    "tests/",
)


def _bash(command: str) -> int:
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    old, sys.stdin = sys.stdin, io.StringIO(payload)
    try:
        return guard.main([])
    finally:
        sys.stdin = old


def _configure(job: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    spec, blocks = tmp_path / "allow.json", tmp_path / "blocks.jsonl"
    spec.write_text(json.dumps(render.allow_spec(job)), encoding="utf-8")
    blocks.write_text("", encoding="utf-8")
    monkeypatch.setenv(guard.ALLOW_ENV, str(spec))
    monkeypatch.setenv(guard.BLOCKS_ENV, str(blocks))
    return blocks


# ------------------------------------------------------------------------------------------------- R1, R2: the hook


def test_a_whole_suite_pytest_is_blocked_and_counted(
    disk: Disk, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    blocks = _configure(a_job(disk, allowed_writes=SURFACES), tmp_path, monkeypatch)
    commands = ("pytest tests", "uv run python -m pytest tests -q", "cd x && pytest")
    for command in commands:
        assert _bash(command) == guard.BLOCK_EXIT, command
    lines = blocks.read_text(encoding="utf-8").splitlines()
    assert render.count_blocks(lines) == len(commands), "each block is counted the way the write guard's are"
    for line in lines:
        reason = json.loads(line)["reason"]
        assert "tests/factory/test_build_resource_guards.py" in reason, reason
        assert "green-bar" in reason, reason


def test_a_pytest_naming_a_test_file_or_node_passes(
    disk: Disk, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    blocks = _configure(a_job(disk), tmp_path, monkeypatch)
    commands = (
        "pytest tests/factory/test_x.py",
        "python -m pytest tests/factory/test_x.py::test_y",
        "git status",
    )
    for command in commands:
        assert not guard.whole_suite(command), command
        assert _bash(command) == 0, command
    assert blocks.read_text(encoding="utf-8") == ""


# --------------------------------------------------------------------------------------------------- R3: the render


def test_the_settings_route_bash_through_the_guard(disk: Disk, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    policy = adapter_mod.ExecutorPolicy.from_effective(disk.ctx.eff)
    s = render.settings(policy, "builder")
    matcher = s["hooks"]["PreToolUse"][0]["matcher"].split("|")
    assert "Bash" in matcher
    assert set(guard.WRITING_TOOLS) <= set(matcher)

    degraded = policy.model_copy(update={"guard": "post-hoc"})
    assert "hooks" not in render.settings(degraded, "builder"), "declared degradation renders no hook at all"

    _configure(a_job(disk), tmp_path, monkeypatch)
    assert _bash("git status") == 0, "a Bash call with no file_path is not refused by the write rule"


# ------------------------------------------------------------------------------------------- R4, R5: the no-result exit

_MSG1: dict[str, Any] = {
    "type": "assistant",
    "message": {"id": "m1", "model": "claude-sonnet-5", "usage": {"input_tokens": 10, "output_tokens": 20}},
}
_MSG2: dict[str, Any] = {
    "type": "assistant",
    "message": {"id": "m2", "model": "claude-sonnet-5", "usage": {"input_tokens": 5, "output_tokens": 7}},
}


def _died_with_no_result(disk: Disk, tmp_path: Path) -> dict[str, Any]:
    """`r-18`'s and `r-19`'s own shape, replayed through `harness.run`: two messages streamed, then the harness dies
    with no result line, under an injected clock and spawn double."""
    prompts = tmp_path / "prompts"
    (prompts / "builder").mkdir(parents=True)
    (prompts / "builder" / "v1.md").write_text("# the builder", encoding="utf-8")
    rundir = tmp_path / "run"
    rundir.mkdir()

    def spawn(args: list[str], **kw: Any) -> Child:
        for msg in (_MSG1, _MSG2):
            kw["stdout"].write((json.dumps(msg) + "\n").encode("utf-8"))
        child = Child({})
        child.sent = [1]  # so wait() answers a non-zero code with no result line ever written
        return child

    ticks = iter([100.0, 103.5])
    code = harness.run(
        a_job(disk),
        rundir,
        prompts,
        harness_version="2.1.269",
        spawn=spawn,
        install=lambda s, h: None,
        work=tmp_path,
        clock=lambda: next(ticks),
    )
    assert code == 1, "a died harness is not ok"
    return dict(json.loads((rundir / "result.json").read_text(encoding="utf-8")))


def test_a_no_result_exit_records_its_duration(disk: Disk, tmp_path: Path) -> None:
    result = _died_with_no_result(disk, tmp_path)
    assert result["duration_ms"] == 3500, "the measured span from spawn to exit, not 0"
    assert adapter_mod.result(result).duration_ms == 3500


def test_a_no_result_exit_records_its_cost_as_unknown(disk: Disk, tmp_path: Path) -> None:
    result = _died_with_no_result(disk, tmp_path)
    assert result["cost_micro"] is None, "unknown, never 0"
    assert result["tokens"] == 42, "the token counts the stream already carried ride beside the unknown cost"
    assert adapter_mod.result(result).cost_micro is None


# ------------------------------------------------------------------------------------------------ R6: the container


def test_the_adapter_passes_an_explicit_pids_limit(disk: Disk) -> None:
    pod = Podman()
    Container(disk.home, _reg(disk), run=pod).execute(a_job(disk))
    run_argv = next(a for a in pod.seen if a[1] == "run")
    assert "--pids-limit" in run_argv
    assert run_argv[run_argv.index("--pids-limit") + 1] == str(container_mod.PIDS_LIMIT)
    assert container_mod.PIDS_LIMIT == 2048, "podman's own default, named rather than inherited"
