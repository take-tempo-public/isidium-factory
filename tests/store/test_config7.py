"""config@7 — each `[agents]` row signs its `tools` and its `prompt` [V4a-ii-a, ruled 2026-09-22].

The owner's rulings, verbatim where they were given: `tools` **required, no default**; a row's tools a subset of
`[executor].allowlist` — *"1 is the way"*, the allowlist kept as the tenant's ceiling with the cost named (every tool
written twice); `prompt` defaulting to what the code named, so the bump changes no run. Each rule is refused **by the
store, before a signature** — the one place a policy is validated — never discovered at a run.
"""

from __future__ import annotations

from typing import Any

import pytest

from isidium.store.registry import config as cfg
from isidium.store.server.store import Store

from .conftest import OWNER, REGISTRY, store_on_disk, tenant_checkout

ROOT = "docs/work/"


@pytest.fixture(scope="module")
def st(tmp_path_factory: pytest.TempPathFactory) -> Store:
    tmp = tmp_path_factory.mktemp("config7")
    store = store_on_disk(tenant_checkout(tmp), tmp / "journal.sqlite", root=ROOT)
    store.init(OWNER, software_key_ack="ok for config@7", root=ROOT)
    return store


def tree_with(st: Store, agents: Any, **top: Any) -> dict[str, Any]:
    tree = {k: v for k, v in st.config_tree.items() if k != "history"}
    return {**tree, "agents": agents, **top}


def rules(tree: dict[str, Any]) -> list[tuple[str, str]]:
    return sorted((r.rule, r.path) for r in cfg.validate_tree(tree, REGISTRY))


def test_init_adopts_config7_and_the_defaults_mirror_the_code_they_replaced(st: Store) -> None:
    """`init` adopts the newest, and config@7's prompt defaults are the map `runner.PROMPT_VERSIONS` held — builder
    `v3`, every other kind `v1` — so moving the version under the signature changes no run. No default names tools."""
    assert st.config_tree["schema"] == REGISTRY.newest("config") == 7
    rows = REGISTRY.defaults_of("config@7")["agents"]
    assert {k: r["prompt"] for k, r in rows.items()} == {
        "planner": "v1",
        "plan-author": "v1",
        "plan-refuter": "v1",
        "judge": "v1",
        "builder": "v3",
        "reviewer": "v1",
    }
    assert not any("tools" in r for r in rows.values()), "`tools` has no default: a declared row names its own"
    six = REGISTRY.defaults_of("config@6")["agents"]
    assert {k: (r["model"], r["effort"]) for k, r in rows.items()} == {
        k: (r["model"], r["effort"]) for k, r in six.items()
    }


def test_a_declared_row_names_its_tools_and_one_that_does_is_accepted(st: Store) -> None:
    """Required on every row the tenant declares — and only there: a kind the tenant leaves out is not refused here
    (the factory refuses it at dispatch, fail-closed). An empty list is a row that may call no tool at all."""
    assert rules(tree_with(st, {"judge": {"model": "claude-opus-5"}})) == [("config.type", "agents.judge.tools")]
    assert rules(tree_with(st, {"judge": {"tools": []}, "builder": {"tools": ["Read", "Edit"], "prompt": "v2"}})) == []


def test_a_rows_tools_sit_under_the_executor_allowlist(st: Store) -> None:
    """The ceiling, read from the tenant's own `[executor]` when it writes one and from the adopted defaults when it
    does not — both arms, because a check that read only one would pass the other's over-reach."""
    over = {"judge": {"tools": ["Read", "WebFetch"]}}
    assert rules(tree_with(st, over)) == [("config.agents-tools", "agents.judge.tools")]
    narrow = {**st.config_tree.get("executor", {}), "allowlist": ["Read"]}
    assert rules(tree_with(st, {"judge": {"tools": ["Read", "Grep"]}}, executor=narrow)) == [
        ("config.agents-tools", "agents.judge.tools")
    ]
    assert rules(tree_with(st, {"judge": {"tools": ["Read"]}}, executor=narrow)) == []


def test_a_tool_named_twice_a_bad_prompt_and_a_config6_row_that_names_either_are_refused(st: Store) -> None:
    assert rules(tree_with(st, {"judge": {"tools": ["Read", "Read"]}})) == [
        ("canon.set-duplicate", "agents.judge.tools")
    ]
    assert rules(tree_with(st, {"judge": {"tools": [], "prompt": "latest"}})) == [
        ("config.pattern", "agents.judge.prompt")
    ]
    six = tree_with(st, {"judge": {"tools": ["Read"], "prompt": "v1"}}, schema=6)
    six["governed"] = [{**g, "schema": "config@6"} if g.get("path") == "config.toml" else g for g in six["governed"]]
    assert ("config.enum", "agents.judge.prompt") in rules(six) and ("config.enum", "agents.judge.tools") in rules(six)


def test_the_policy_act_declares_the_rows_and_the_effective_row_carries_all_four(st: Store) -> None:
    """Through the store's own write, as tenant #0's `config-policy` act will: the row the tenant wrote (`tools`)
    and the three the schema supplies (`model`, `effort`, `prompt`) are one row in the effective config."""
    tree = tree_with(st, {"builder": {"tools": ["Read", "Edit"]}})
    st.write("config.toml", tree, {"seq": st.policy[-1]["seq"], "h": st.policy[-1]["h"]}, None, OWNER)
    eff = cfg.resolve_effective(st.config_tree, REGISTRY)
    assert eff["agents"]["builder"] == {
        "model": "claude-opus-5",
        "effort": "xhigh",
        "tools": ["Read", "Edit"],
        "prompt": "v3",
    }
    assert "tools" not in eff["agents"]["judge"], "a kind the act did not declare is still undeclared"
