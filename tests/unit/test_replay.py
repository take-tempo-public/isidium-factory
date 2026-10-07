"""tools/replay.py: a replayed job is the recorded job with one thing changed — the agent's model and effort (and
the prompt and tree the replay names). Everything the phase reads otherwise is the recorded bytes, or the
evaluation compares two variables at once."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

TOOL = Path(__file__).resolve().parents[2] / "tools" / "replay.py"


def _tool() -> ModuleType:
    spec = importlib.util.spec_from_file_location("replay_under_test", TOOL)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _job(agent: str = "reviewer") -> dict[str, Any]:
    row = {"model": "claude-opus-5-5", "effort": "xhigh", "tools": ["Read", "Grep"], "prompt": "v2"}
    other = {"model": "claude-sonnet-5-5", "effort": "high", "tools": ["Read"], "prompt": "v1"}
    return {
        "run_id": "r-44",
        "card": 26,
        "phase": "review",
        "payload": {"card": {"id": 26}, "base_sha": "ad27"},
        "payload_hash": "sha256:p",
        "worktree": "C:/live/worktrees/r-44",
        "allowed_writes": [],
        "policy": {
            "allowlist": ["Read", "Grep"],
            "budgets": {"max_turns": 100, "wall_clock_s": 3600, "max_tokens": None},
            "guard": "write-time",
            "agents": {agent: row, "plan-refuter": other},
        },
        "identity": {"agent": agent, "name": "isdm-fac-lander", "email": "x@users.noreply.github.com"},
        "prompt_version": "v2",
        "inputs": [{"name": "diff", "sha256": "sha256:d", "content": {"text": "+a"}}],
        "round": 1,
    }


def test_a_variant_changes_the_agent_s_model_effort_prompt_and_tree_and_nothing_else() -> None:
    tool = _tool()
    from isidium.factory.adapter import RunJob

    recorded = RunJob.model_validate(_job())
    out = tool.variant(recorded, model="claude-sonnet-5-5", effort="medium", prompt="v3", worktree="E:/wt")

    row = out.policy.agents["reviewer"]
    assert (row.model, row.effort, row.prompt) == ("claude-sonnet-5-5", "medium", "v3")
    assert row.tools == recorded.policy.agents["reviewer"].tools
    assert out.prompt_version == "v3" and out.worktree == "E:/wt"

    # Every other byte is the recorded one: blank the four fields on both sides and the dumps are equal.
    def rest(job: Any) -> dict[str, Any]:
        d: dict[str, Any] = job.model_dump(mode="json")
        d["policy"]["agents"]["reviewer"] = None
        d["prompt_version"] = d["worktree"] = None
        return d

    assert rest(out) == rest(recorded)
    assert out.policy.agents["plan-refuter"] == recorded.policy.agents["plan-refuter"]


def test_the_prompt_is_the_newest_the_image_carries_for_that_agent() -> None:
    tool = _tool()
    label = frozenset({"reviewer/v2", "reviewer/v3", "reviewer/v10", "builder/v6"})
    assert tool.newest(label, "reviewer") == "v10"
    with pytest.raises(SystemExit):
        tool.newest(label, "judge")


def test_a_variant_s_directory_names_its_model_and_effort() -> None:
    assert _tool().label("claude-haiku-4-5", "high") == "haiku-4-5.high"
