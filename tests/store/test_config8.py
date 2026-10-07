"""config@8 — the signed `[watcher]` table: whether the PR watcher may start a fixup, and how many a day [card 27, ruled
2026-10-04 [owner]: *"Signed opt-in + ceiling"*, in *"New config schema row"*].

The opt-in lives in the signed policy file and nowhere else (A1), and the table holds only what spends — no cadence,
no host setting (A2: the cadence is the host timer's). Every default is the adopted schema document's (Y1), never
code's; a tenant on config@7 is not affected by a table it has not adopted (04 §4.1).
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from isidium.factory.adapter import ExecutorPolicy
from isidium.store.core.grammar import config_grammar_refusals, emit_config
from isidium.store.core.refusal import ValidationRefusal
from isidium.store.registry import config as cfg
from isidium.store.server.store import Store

from .conftest import OWNER, REGISTRY, store_on_disk, tenant_checkout

ROOT = "docs/work/"
DEFAULTS = {"fixup": False, "fixup_per_day": 0}


@pytest.fixture(scope="module")
def st(tmp_path_factory: pytest.TempPathFactory) -> Store:
    tmp = tmp_path_factory.mktemp("config8")
    store = store_on_disk(tenant_checkout(tmp), tmp / "journal.sqlite", root=ROOT)
    store.init(OWNER, software_key_ack="ok for config@8", root=ROOT)
    return store


def tree_with(st: Store, **top: Any) -> dict[str, Any]:
    tree = {k: v for k, v in st.config_tree.items() if k != "history"}
    return {**tree, **top}


def rules(tree: dict[str, Any]) -> list[tuple[str, str]]:
    return sorted((r.rule, r.path) for r in cfg.validate_tree(tree, REGISTRY))


def as_config7(tree: dict[str, Any]) -> dict[str, Any]:
    """The same tenant as a config@7 file: the head, the file's own `config.toml` row, and the version its chain
    opened under — `init` under config@8 wrote that as 8, and a chain cannot open under a version above the head."""
    governed = [{**g, "schema": "config@7"} if g.get("path") == "config.toml" else g for g in tree["governed"]]
    return {**tree, "schema": 7, "chain_opened_under": 7, "governed": governed}


def watcher_rows() -> list[dict[str, Any]]:
    (table,) = [t for t in REGISTRY.get("config@8")["tables"] if t["name"] == "watcher"]
    return list(table["keys"])


def test_config8_declares_the_watcher_table_with_its_defaults(st: Store) -> None:
    """`init` adopts the newest, and config@8 is config@7 plus the one table: its two keys, their types and bounds,
    and nothing that names a cadence or a host (A2). The defaults are the document's — the tenant's own file does not
    carry the table, and the effective config still has it, which is what 'the defaults live in the schema' means."""
    assert st.config_tree["schema"] == REGISTRY.newest("config") == 8
    assert REGISTRY.defaults_of("config@8")["watcher"] == DEFAULTS
    rows = {r["name"]: r for r in watcher_rows()}
    assert list(rows) == ["fixup", "fixup_per_day"], "the table holds what spends and nothing else (A2)"
    assert rows["fixup"]["type"] == "bool" and rows["fixup_per_day"]["type"] == "int"
    assert rows["fixup_per_day"]["range"] == {"min": 0} and "range" not in rows["fixup"]
    assert not any("required_when" in r for r in rows.values()), "absent is its default"

    # config@8 is config@7 plus the named deltas, structurally: remove them and the documents are equal
    seven, eight = copy.deepcopy(dict(REGISTRY.get("config@7"))), copy.deepcopy(dict(REGISTRY.get("config@8")))
    eight["version"] = 7
    eight["tables"] = [t for t in eight["tables"] if t["name"] != "watcher"]
    (manifest,) = [t for t in eight["tables"] if t["name"] == "governed"]
    row = next(r for r in manifest["default"]["value"] if r["path"] == "config.toml")
    assert row["schema"] == "config@8", "the default manifest names the version it ships in"
    row["schema"] = "config@7"
    assert eight == seven

    assert "watcher" not in st.config_tree and "watcher" not in REGISTRY.defaults_of("config@7")
    assert cfg.resolve_effective(st.config_tree, REGISTRY)["watcher"] == DEFAULTS


def test_the_watcher_table_serializes_in_its_pinned_place(st: Store) -> None:
    """Pinned directly after `[inbox]`, its keys in the pinned order — whatever order the tree was built in, and
    wherever the tree holds the table."""
    assert cfg.TABLE_ORDER.index("watcher") == cfg.TABLE_ORDER.index("inbox") + 1
    assert cfg.TABLE_KEY_ORDER["watcher"] == ("fixup", "fixup_per_day")
    tree = tree_with(st, inbox={"max_per_run": 10})
    tree["watcher"] = {"fixup_per_day": 2, "fixup": True}  # reversed, and the dict's last key
    text = emit_config(tree, [], cfg.CONFIG_ORDERS)
    at = {h: text.index(h) for h in ("[inbox]", "[watcher]", "[[governed]]", "[history]")}
    assert at["[inbox]"] < at["[watcher]"] < at["[[governed]]"] < at["[history]"], at
    assert "[prioritization]" not in text
    assert text.index("fixup = true") < text.index("fixup_per_day = 2")
    assert cfg.parse_and_validate(text, REGISTRY)[2] == []

    # a prioritization table is the neighbour the pin is written against
    with_prio = emit_config({**tree, "prioritization": {"risk": 5}}, [], cfg.CONFIG_ORDERS)
    assert with_prio.index("[inbox]") < with_prio.index("[watcher]") < with_prio.index("[prioritization]")

    block = text[at["[watcher]"] : at["[[governed]]"]]
    moved = text.replace(block, "", 1).replace("[history]", block + "[history]", 1)
    assert [r.rule for r in config_grammar_refusals(moved, cfg.CONFIG_ORDERS)] == ["head.table-order"]


def test_a_config7_tenant_is_still_accepted(st: Store) -> None:
    """R3: a file that adopted config@7 validates exactly as it did, the factory's own gate (`MIN_CONFIG = 7`) takes
    its effective config, and the table is invisible until the owner adopts @8 by a signed act — a `[watcher]` in a
    config@7 file is `config.enum` on its key, not a mis-ordered or unknown table."""
    tree7 = as_config7(tree_with(st))
    assert rules(tree7) == []
    eff7 = cfg.resolve_effective(tree7, REGISTRY)
    assert eff7["schema"] == 7 and "watcher" not in eff7
    declared = cfg.resolve_effective({**tree7, "agents": {"builder": {"tools": ["Read"]}}}, REGISTRY)
    ExecutorPolicy.from_effective(declared)  # no refusal: the factory's floor is unchanged
    assert rules({**tree7, "watcher": {"fixup": True}}) == [("config.enum", "watcher.fixup")]
    # the store itself did not move: adopting @8 is a signed act, and this tree was never written
    assert st.config_tree["schema"] == 8 and "watcher" not in st.config_tree


def test_a_negative_fixup_per_day_is_refused(st: Store) -> None:
    """R4, under the config namespace only (C3): the range and the type come from the adopted document's rows, and a
    key the table does not declare — a cadence, say — is `config.enum` (A2)."""

    def watcher(**keys: Any) -> list[tuple[str, str]]:
        return rules(tree_with(st, watcher=keys))

    assert watcher(fixup=True, fixup_per_day=-1) == [("config.range", "watcher.fixup_per_day")]
    assert watcher(fixup=1) == [("config.type", "watcher.fixup")]
    assert watcher(fixup="true") == [("config.type", "watcher.fixup")]
    assert watcher(fixup_per_day=True) == [("config.type", "watcher.fixup_per_day")]
    assert watcher(fixup_per_day="3") == [("config.type", "watcher.fixup_per_day")]
    assert watcher(fixup=True, fixup_per_day=0) == []
    assert watcher(fixup=True, fixup_per_day=3) == []
    assert watcher() == []
    assert watcher(cadence_minutes=15) == [("config.enum", "watcher.cadence_minutes")]
    for tree in (
        tree_with(st, watcher={"fixup_per_day": -1}),
        tree_with(st, watcher={"fixup": "yes"}),
        tree_with(st, watcher={"cadence_minutes": 15}),
    ):
        assert all(r.rule.startswith("config.") for r in cfg.validate_tree(tree, REGISTRY))

    # through the store's own write: refused before a signature, and the policy it holds does not move
    before = (st.policy[-1]["seq"], st.config_tree["schema"])
    bad = tree_with(st, watcher={"fixup": True, "fixup_per_day": -1})
    with pytest.raises(ValidationRefusal) as refused:
        st.write("config.toml", bad, {"seq": st.policy[-1]["seq"], "h": st.policy[-1]["h"]}, None, OWNER)
    assert [(v.rule, v.path) for v in refused.value.verdicts] == [("config.range", "watcher.fixup_per_day")]
    assert (st.policy[-1]["seq"], st.config_tree["schema"]) == before and "watcher" not in st.config_tree
