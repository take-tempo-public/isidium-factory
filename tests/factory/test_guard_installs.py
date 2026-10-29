"""Card 65 — a build or reconcile phase installs nothing: the image carries the lock's test environments, so the guard
refuses a `Bash` segment that installs packages or makes an environment (R3), whatever runs beside it on the line.

`r-58` (card 54) lacked its tools, ran `python3 -m venv /tmp/v && pip install ruff mypy pytest`, and a wheel landed
in /work. The rule is card 19's sibling in `guard.main`, reading a command with the same `_SEPARATORS` and
`_tokens`; the tests call the hook in-process with a spec written straight to `tmp_path`, so no tenant fixture is built.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

from isidium.factory import guard, render

# This card's own declared surfaces.
SURFACES = (
    "deploy/Containerfile.runner",
    "packages/isidium-factory/src/isidium/factory/guard.py",
    "prompts/builder/v7.md",
    "tests/factory/test_runner_test_env.py",
    "tests/factory/test_guard_installs.py",
    "tools/mutations/runner-test-env.toml",
    "tests/",
)

# Every install form R3 names, bare. `pip install pytest` and `uv pip install pytest` also read as a whole-suite run
# (they name pytest and no test file), so they discriminate the order of the two rules: read second, they would be
# answered with card 19's reason.
FORMS = (
    "pip install ruff",
    "pip3 install ruff",
    "pip download ruff",
    "python -m pip install ruff",
    "python3 -m pip download ruff",
    '"$ISIDIUM_PY313/bin/python" -m pip install ruff',
    "uv pip install ruff",
    "uv add ruff",
    "uv sync",
    "uv tool install ruff",
    "python -m venv /tmp/v",
    "virtualenv /tmp/v",
    "pip install pytest",
    "uv pip install pytest",
)
R58 = "python3 -m venv /tmp/v && pip install ruff mypy pytest"

PY = "packages/isidium-factory/src/isidium/factory/guard.py"
THIS_TEST = "tests/factory/test_guard_installs.py"


def _bash(command: str) -> int:
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    old, sys.stdin = sys.stdin, io.StringIO(payload)
    try:
        return guard.main([])
    finally:
        sys.stdin = old


def _configure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    spec, blocks = tmp_path / "allow.json", tmp_path / "blocks.jsonl"
    spec.write_text(json.dumps({"root": "/work", "allow": list(SURFACES), "blocks": str(blocks)}), encoding="utf-8")
    blocks.write_text("", encoding="utf-8")
    monkeypatch.setenv(guard.ALLOW_ENV, str(spec))
    monkeypatch.setenv(guard.BLOCKS_ENV, str(blocks))
    return blocks


def test_every_install_form_is_blocked_and_recorded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    blocks = _configure(tmp_path, monkeypatch)
    commands = [*FORMS, *(f"cd x && {form}" for form in FORMS), R58]
    for command in commands:
        assert guard.installs(command), command
        assert _bash(command) == guard.BLOCK_EXIT, command
    lines = blocks.read_text(encoding="utf-8").splitlines()
    assert render.count_blocks(lines) == len(commands), "each block is recorded once, the way every block is counted"
    for line in lines:
        reason = json.loads(line)["reason"]
        for word in ("pytest", "ruff", "mypy", "ISIDIUM_PY313", "not an install"):
            assert word in reason, (word, reason)
        assert "green-bar" not in reason, "an install that names pytest is answered with the install reason"


def test_the_tools_by_path_pass_and_the_whole_suite_is_still_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    blocks = _configure(tmp_path, monkeypatch)
    allowed = (
        f"pytest {THIS_TEST}",
        f"python -m pytest {THIS_TEST}::test_x",
        f'"$ISIDIUM_PY313/bin/python" -m pytest {THIS_TEST}',
        f"ruff check {PY}",
        f"ruff format --check {PY}",
        f"mypy --strict {PY}",
        "cd /work && pytest tests/factory/test_runner_test_env.py",
        "pip list",
        "uv run python -m pytest tests/factory/test_runner_test_env.py",
        "grep 'pip install' deploy/Containerfile.runner",
    )
    for command in allowed:
        assert not guard.installs(command), command
        assert _bash(command) == 0, command
    assert blocks.read_text(encoding="utf-8") == "", "nothing allowed is recorded"

    assert _bash("pytest tests") == guard.BLOCK_EXIT
    (line,) = blocks.read_text(encoding="utf-8").splitlines()
    reason = json.loads(line)["reason"]
    assert "green-bar" in reason and "ISIDIUM_PY313" not in reason, "card 19's rule, and its reason, are unchanged"
