"""K10 — the leftovers before the bridge, and the three rulings of its first exchange (2026-09-06).

1. `project()` rolls containers up members-first, whatever the ids, and `project_one` reads the same subtree.
2. Every write door under a failed push — `write_set`, `suggest`, `disposition`, `bind`, `repair` — on K7a's outage.
3. A sitting rejected *after* its rebuild is un-built to the pre-commit parent, and the next sync fast-forwards.
4. The client's TLS context is the standard library's, built without a deprecation, and still pins the CA.
5. (Q21) is in `tests/unit/test_rule_ids.py`: the sweep reads `tools/`.
6. `show queue --text` is the board's own queue section, from the one renderer.
7. (Q20) the dry run's verdicts are typed records, deduplicated by the whole record.
8. (Q16's schema half) `config@3`: `root` is `immutable`; a `config@2` tenant migrates by one signed act.

Every assertion is a positive discriminator; nothing here passes on "nothing came back".
"""

from __future__ import annotations

import copy
import dataclasses
import ssl
import warnings
from pathlib import Path
from typing import Any

import pytest

from isidium.store.client import cli as cli_mod
from isidium.store.client.transport import channel_context
from isidium.store.core import chain, telemetry
from isidium.store.core import status as status_mod
from isidium.store.core.grammar import Document
from isidium.store.core.refusal import Refusal
from isidium.store.registry.loader import adopted_version
from isidium.store.server.api import Api
from isidium.store.server.gitrepo import GitCli, MemGit
from isidium.store.server.journal import Journal
from isidium.store.server.service import Service
from isidium.store.server.signer import SoftwareKey, SoftwareKeyAck
from isidium.store.server.store import NewCard, Store, WriteRequest, _typed_verdicts

from .conftest import (
    BASE_SCOPE,
    OWNER,
    PLANNER,
    REF_FILES,
    REGISTRY,
    Clock,
    Harness,
    Telemetry,
    base_head,
    fresh,
    git,
    store_on_disk,
)
from .test_edge import authority, issue
from .test_k6 import registration, registry_without
from .test_k7a import ROOT, Outage, draft, on_main
from .test_k7a import outage as _k7a_outage
from .test_k7a import store as _k7a_store
from .test_k7c import client_here as _k7c_client_here
from .test_k9 import stranger_pushes
from .test_service import OWNER_CERT, call

# K7a's real-git store and its outage, and K7c's installed checkout, registered here under their own names: pytest
# finds a fixture by the module attribute, and a name bound by import is one ruff reads as shadowed by the parameter.
store, outage, client_here = _k7a_store, _k7a_outage, _k7c_client_here

# ---- 1. the nested roll-up is order-independent ---------------------------------------------------------------------


def _nested(descending: bool) -> tuple[Harness, dict[str, int]]:
    """An epic holding a phase holding a story — the ladder level `config.toml` declares — created in ascending id
    order (container first) or descending (member first, then re-parented); all three ratified; the story withdrawn,
    so both containers should roll up `closed`."""
    hz = fresh(f"k10-nested-{'desc' if descending else 'asc'}")
    st = hz.st
    tree = dict(st.config_tree)
    tree["ladder"] = {"levels": ["phase"]}
    st.write("config.toml", tree, {"seq": st.policy[-1]["seq"], "h": st.policy[-1]["h"]}, None, OWNER)
    if descending:
        m = hz.draft("story", kind="story")
        p = hz.draft("phase", kind="phase")
        g = hz.draft("epic", kind="epic")
        st.write_set(p, [f"parent={g}"], PLANNER)
        st.write_set(m, [f"parent={p}"], PLANNER)
    else:
        g = hz.draft("epic", kind="epic")
        p = hz.draft("phase", kind="phase", parent=g)
        m = hz.draft("story", kind="story", parent=p)
    assert (descending and m < p < g) or (not descending and g < p < m)
    st.ratify([g, p, m], OWNER)
    st.write_set(m, ['status="withdrawn"', 'withdrawn_reason="superseded"'], OWNER)
    return hz, {"g": g, "p": p, "m": m}


@pytest.mark.parametrize("descending", [False, True], ids=["container-first", "member-first"])
def test_a_container_inside_a_container_rolls_up_members_first_whatever_the_ids(descending: bool) -> None:
    """Before K10 the roll-up ran in card order: with the member created first (its id lower) the outer container
    read the inner one *before* the inner one rolled up, and stayed `ratified` while the other order said
    `closed`. Now both orders say `closed` at both levels, and `project_one` agrees on every card — with the
    store's members index and without it."""
    hz, ids = _nested(descending)
    inp = hz.st._inputs()
    whole = status_mod.project(inp)
    assert whole[ids["m"]].label.row == "withdrawn" and whole[ids["m"]].terminal
    assert whole[ids["p"]].label == status_mod.Label("closed"), whole[ids["p"]]
    assert whole[ids["g"]].label == status_mod.Label("closed"), whole[ids["g"]]
    for cid in inp.cards:
        assert status_mod.project_one(inp, cid) == whole[cid], cid
    bare = dataclasses.replace(inp, kids=None)
    assert status_mod.project_one(bare, ids["g"]) == whole[ids["g"]]


def test_both_id_orders_project_the_same_nested_set() -> None:
    labels = []
    for descending in (False, True):
        hz, ids = _nested(descending)
        whole = status_mod.project(hz.st._inputs())
        labels.append({name: whole[cid].label for name, cid in ids.items()})
    assert labels[0] == labels[1], labels


def test_a_parent_cycle_on_main_terminates_the_roll_up() -> None:
    """A bypass can put a `parent` cycle on `main` (every door refuses one). The roll-up must end, not walk it."""
    out = {
        1: status_mod.Projection(1, "epic", "ratified", status_mod.Label("ratified")),
        2: status_mod.Projection(2, "epic", "ratified", status_mod.Label("ratified")),
    }
    status_mod._roll_up(out, {1: [2], 2: [1]})
    assert {c: p.label.row for c, p in out.items()} == {1: "ratified", 2: "ratified"}


# ---- 2. every write door under a failed push ------------------------------------------------------------------------


def _pending(st: Store) -> list[int]:
    return [s for s, _p, _d in st.journal.pending_rows()]


def _main(tmp_path: Path) -> str:
    return git(tmp_path / "origin.git", "rev-parse", "main").strip()


def _restart_agrees(tmp_path: Path, landed: str, cid: int) -> None:
    """A restart over the same journal replays nothing, `main` is where the carrying push left it, `check` is clean."""
    again = store_on_disk(tmp_path / "tenant", tmp_path / "journal.sqlite", root=ROOT)
    assert _main(tmp_path) == landed, "the restart moved main"
    assert again.check(cid)["integrity"] == []


def test_write_set_under_a_failed_push_is_journaled_indexed_and_carried(
    store: Store, tmp_path: Path, outage: Outage
) -> None:
    path = draft(store, "tended")
    cid = int(store.docs[path].head["id"])
    before = _main(tmp_path)
    outage.arm()
    r = store.write_set(cid, ['priority="P2"'], PLANNER)
    assert r.landed is False and outage.fired == 1 and _main(tmp_path) == before
    assert _pending(store) == [r.journal_seq] and store.docs[path].head["priority"] == "P2"
    r2 = store.write_set(cid, ['priority="P3"'], PLANNER)
    assert r2.landed is True and _pending(store) == []
    assert 'priority = "P3"' in on_main(tmp_path, store.rp(path))
    _restart_agrees(tmp_path, _main(tmp_path), cid)


def test_suggest_under_a_failed_push_is_journaled_indexed_and_carried(
    store: Store, tmp_path: Path, outage: Outage
) -> None:
    path = draft(store, "with-an-inbox")
    cid = int(store.docs[path].head["id"])
    before = _main(tmp_path)
    outage.arm()
    r = store.suggest(PLANNER, "docs", "a suggestion", "its body", source="planner")
    assert r.landed is False and outage.fired == 1 and _main(tmp_path) == before
    assert _pending(store) == [r.journal_seq] and store.inbox[-1]["id"] == "s1"
    r2 = store.suggest(PLANNER, "docs", "a second", "its body", source="planner")
    assert r2.landed is True and _pending(store) == []
    lines = on_main(tmp_path, store.rp("suggestions.jsonl")).splitlines()
    assert ['"s1"' in lines[0], '"s2"' in lines[1]] == [True, True], lines
    again = store_on_disk(tmp_path / "tenant", tmp_path / "journal.sqlite", root=ROOT)
    assert [rec["id"] for rec in again.inbox] == ["s1", "s2"] and again.check(cid)["integrity"] == []


def test_disposition_under_a_failed_push_is_journaled_indexed_and_carried(
    store: Store, tmp_path: Path, outage: Outage
) -> None:
    path = draft(store, "with-a-disposition")
    cid = int(store.docs[path].head["id"])
    assert store.suggest(PLANNER, "docs", "a suggestion", "its body", source="planner").landed is True
    before = _main(tmp_path)
    outage.arm()
    out = store.disposition("s1", "declined", OWNER, reason="not now")
    assert out["disposition"].landed is False and outage.fired == 1 and _main(tmp_path) == before
    assert _pending(store) == [out["disposition"].journal_seq]
    assert store.inbox[-1]["type"] == "disposition" and store.inbox[-1]["on"] == "s1"
    r2 = store.suggest(PLANNER, "docs", "another", "its body", source="planner")
    assert r2.landed is True and _pending(store) == []
    lines = on_main(tmp_path, store.rp("suggestions.jsonl")).splitlines()
    assert len(lines) == 3 and '"disposition"' in lines[1] and '"declined"' in lines[1], lines
    again = store_on_disk(tmp_path / "tenant", tmp_path / "journal.sqlite", root=ROOT)
    assert [rec["id"] for rec in again.inbox] == ["s1", "d1", "s2"] and again.check(cid)["integrity"] == []


def test_bind_under_a_failed_push_is_journaled_indexed_and_carried(
    store: Store, tmp_path: Path, outage: Outage, otel: Telemetry
) -> None:
    """`bind` answers the entry, not a `WriteResult`, so its one signal is the unlanded counter (Q18)."""
    path = draft(store, "with-a-binding")
    cid = int(store.docs[path].head["id"])
    realm = SoftwareKeyAck(SoftwareKey.generate(), store.clock, time_skew_s=600)
    signer = store.signer
    assert isinstance(signer, SoftwareKeyAck)
    before = _main(tmp_path)
    unlanded = otel.count("isidium.store.write.unlanded", **{telemetry.RULE: "git.failed"})
    outage.arm()
    e = store.bind(realm, signer.key_fpr, "owner", "2026-01-01T00:00:00Z")
    assert outage.fired == 1 and _main(tmp_path) == before
    assert otel.count("isidium.store.write.unlanded", **{telemetry.RULE: "git.failed"}) == unlanded + 1
    assert store.policy[-1] is e and e["act"] == "binding"
    assert [p for _s, p, _d in store.journal.pending_rows()] == ["config.toml"]
    draft(store, "after-the-bind")
    assert _pending(store) == []
    assert 'act = "binding"' in on_main(tmp_path, store.rp("config.toml"))
    again = store_on_disk(tmp_path / "tenant", tmp_path / "journal.sqlite", root=ROOT)
    assert again.policy[-1]["act"] == "binding" and again.check(cid)["integrity"] == []


def test_repair_under_a_failed_push_is_journaled_indexed_and_carried(
    store: Store, tmp_path: Path, outage: Outage
) -> None:
    """This test found a defect beside the push: `check` read the repaired card `tampered` with no outage at all
    (the verifier's genesis hook, below). The door itself behaves like every other under a failed push."""
    path = draft(store, "to-repair")
    cid = int(store.docs[path].head["id"])
    before = _main(tmp_path)
    outage.arm()
    out = store.repair(OWNER, history=cid)
    assert out["landed"] is False and outage.fired == 1 and _main(tmp_path) == before
    assert _pending(store) == [out["journal_seq"]] and store.docs[path].history[-1]["act"] == "repaired"
    assert store.check(cid)["chain"] == ["ok", "ok"] and store.check(cid)["integrity"] == []
    r2 = store.write_set(cid, ['priority="P2"'], PLANNER)
    assert r2.landed is True and _pending(store) == []
    assert 'act = "repaired"' in on_main(tmp_path, store.rp(path))
    _restart_agrees(tmp_path, _main(tmp_path), cid)


def test_a_repair_restarting_from_a_seq_verifies_the_same_with_and_without_the_genesis_hook() -> None:
    """`Store.check` and the verifier (`client/verify.py` since K12) pass `genesis_after_repair`; the K8 scenario test did not — and
    the two disagreed on every `repair --history`: the hook replaced the hash map, so a restart from `k ≥ 1` was
    re-linked from the genesis and read `tampered`. Three entries, the third a repair restarting from 1: `ok`,
    `covered`, `ok` — both ways — and a restart from 0 under a *new* genesis still resumes from that genesis."""
    g = chain.genesis("card", 7)
    e1: dict[str, Any] = {
        "seq": 1,
        "at": "2026-09-06T00:00:00Z",
        "by": "a",
        "act": "created",
        "fields": [],
        "build": "b",
    }
    e1["h"] = chain.link(g, e1)
    e2: dict[str, Any] = {
        "seq": 2,
        "at": "2026-09-06T00:00:01Z",
        "by": "a",
        "act": "amended",
        "fields": [],
        "build": "b",
    }
    e2["h"] = chain.link(e1["h"], e2)
    e3: dict[str, Any] = {"seq": 3, "at": "2026-09-06T00:00:02Z", "by": "a", "act": "repaired", "fields": ["history"]}
    e3.update({"build": "b", "ref": 1, "note": "restart from 1"})
    e3["h"] = chain.link(e1["h"], e3)  # the repair entry chains from h_restart_from (03 §5.5)
    bare = chain.verify_chain([e1, e2, e3], g)
    hooked = chain.verify_chain([e1, e2, e3], g, genesis_after_repair=lambda _e: g)
    assert bare == hooked == ["ok", "covered", "ok"], (bare, hooked)
    # the id repair's case: a restart from 0 continues under the new genesis from the repaired entry on
    g2 = chain.genesis("card", 8)
    r0: dict[str, Any] = {"seq": 3, "at": "2026-09-06T00:00:02Z", "by": "a", "act": "repaired", "fields": ["history"]}
    r0.update({"build": "b", "ref": 0, "note": "renumbered"})
    r0["h"] = chain.link(g2, r0)
    assert chain.verify_chain([e1, e2, r0], g, genesis_after_repair=lambda _e: g2) == ["covered", "covered", "ok"]


# ---- 3. the rebuild's undo --------------------------------------------------------------------------------------------


def test_a_sitting_rejected_after_its_rebuild_is_un_built_to_the_pre_commit_parent(
    store: Store, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A merge lands between the fetch and the sitting's push; the rebuild runs; a second merge lands before the
    rebuilt push, which is rejected too (K9's bound). The rebuild left the store's ref on the rebuilt commit, whose
    parent is the *first* merge; the un-build must take the ref back to the pre-commit parent — the tip the store
    held before it committed — and not to the rebuilt commit's parent, or to the original commit. The discriminator
    is the next write: its sync fast-forwards from that parent to the *second* merge and lands on top of it, so
    nothing the store fetched is lost and nothing it un-built is carried."""
    path = draft(store, "rebuilt-then-rejected")
    cid = int(store.docs[path].head["id"])
    repo = store.repo
    assert isinstance(repo, GitCli)
    base = repo.head
    assert base == _main(tmp_path)
    landed: list[str] = []
    original = GitCli.push

    def push_into_a_moving_remote(self: GitCli) -> None:
        if len(landed) < 2:
            landed.append(stranger_pushes(tmp_path, f"docs/dev/race-{len(landed)}.md", b"a merge\n"))
        original(self)

    monkeypatch.setattr(GitCli, "push", push_into_a_moving_remote)
    with pytest.raises(Refusal) as refused:
        store.ratify([cid], OWNER)
    monkeypatch.setattr(GitCli, "push", original)
    assert refused.value.rule == "git.push-rejected" and len(landed) == 2
    assert repo.head == base, "the sitting's commit was not un-built to the pre-commit parent"
    assert _pending(store) == [] and store.docs[path].head["status"] == "draft"

    after = store.write(
        NewCard("after-the-race"), Document(base_head(0, "draft"), {"Scope": BASE_SCOPE}), None, None, PLANNER
    )
    sha = after.commit
    assert after.landed is True
    assert repo.parents(sha) == [landed[1]], "the next write did not fast-forward to the newest fetched tip"
    assert _main(tmp_path) == sha
    assert store.check(cid)["integrity"] == []
    _restart_agrees(tmp_path, sha, cid)


# ---- 4. the client's TLS context ------------------------------------------------------------------------------------


def test_the_channel_context_is_built_without_a_deprecation_and_pins_the_ca(tmp_path: Path) -> None:
    """Warnings are errors here: `httpx.create_ssl_context(verify=<path>)` would raise. And the context is the one
    the pin needs — exactly the registration's CA loaded, the peer's certificate required, its name checked."""
    ca = authority(tmp_path, "k10-ca")
    cert, key = issue(ca, tmp_path, "owner@example", "owner")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        ctx = channel_context(ca.path, cert, key)
    assert ctx.verify_mode is ssl.CERT_REQUIRED and ctx.check_hostname is True
    loaded = ctx.get_ca_certs()
    assert len(loaded) == 1, "exactly the registration's CA, and not the system store, is what pins the store"
    assert loaded[0]["subject"] == ((("commonName", "k10-ca"),),), loaded[0]["subject"]


# ---- 6. the queue's human form ---------------------------------------------------------------------------------------


def test_show_queue_answers_the_boards_queue_section_from_the_one_renderer() -> None:
    hz = fresh("k10-queue")
    st = hz.st
    held = hz.draft("held-for-the-queue")
    st.write_set(held, ['hold.kind="blocked"', "hold.on.owner=true"], PLANNER)
    api = Api(st)
    queue = api.show(OWNER, {"target": "queue"})
    board = api.show(OWNER, {"target": "board"})["markdown"]
    section = board[board.index("## Queue") : board.index("## Inbox")]
    assert section == queue["markdown"] + "\n", (section, queue["markdown"])
    assert f"- holds on the owner: **{held}**" in queue["markdown"].splitlines()
    assert queue["holds_on_owner"] == [held]  # the fields are still there beside the human form


def test_show_queue_text_prints_the_markdown(
    client_here: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class Answering:
        def call(self, name: str, args: dict[str, Any]) -> Any:
            assert (name, args) == ("show", {"target": "queue"})
            return {"open_questions": [], "markdown": "## Queue\n\n- open questions: none\n"}

    monkeypatch.setattr(cli_mod, "Transport", lambda _cfg, _workdir: Answering())
    cli_mod.show(target="queue", text=True)
    assert capsys.readouterr().out == "## Queue\n\n- open questions: none\n\n"


# ---- 7. (Q20) typed verdicts on the dry run --------------------------------------------------------------------------


def test_the_dry_runs_verdicts_are_typed_records_on_the_wire() -> None:
    """The shape Q7 gave `validate.failed`, for every verdict the sitting answers: `{rule, path, detail}`, a
    `validate.failed` verdict carrying its own `verdicts`, keyed by the card's id as a string on the wire."""
    hz = fresh("k10-typed")
    service = Service(Api(hz.st), registration(hz.clock), hz.st.tenant)
    head = base_head(0, "closed")  # born closed: a profile failure and a creation that is not a signed act
    head.pop("id")
    args = {"writes": [{"new_slug": "typed", "document": {"head": head, "scope": BASE_SCOPE}}], "dry_run": True}
    status, body = call(service, "ratify", args, OWNER_CERT)
    assert status == 200, body
    verdicts: dict[str, list[dict[str, Any]]] = body["result"]["verdicts"]
    assert list(verdicts) == [str(hz.st.journal.counter + 1)]
    pid = str(hz.st.journal.counter + 1)
    assert [v["rule"] for v in verdicts[pid]] == ["validate.failed", "ratify.not-a-signed-act"]
    failed, created = verdicts[pid]
    assert set(created) == {"rule", "path", "detail"} and created["detail"] == "created"
    assert set(failed) == {"rule", "path", "detail", "verdicts"} and failed["verdicts"][0]["rule"].startswith(
        "profile."
    )


def test_the_dry_runs_verdicts_are_deduplicated_by_the_whole_record() -> None:
    """Identical verdicts collapse (F18's doubled `:created` was the case); distinct verdicts under one rule id —
    two refs that do not resolve — are both kept, because a planner needs both."""
    same = [Refusal("ref.unresolved", "refs", "a.md"), Refusal("ref.unresolved", "refs", "a.md")]
    other = Refusal("ref.unresolved", "refs", "b.md")
    typed = _typed_verdicts([*same, other, same[0]])
    assert typed == [
        {"rule": "ref.unresolved", "path": "refs", "detail": "a.md"},
        {"rule": "ref.unresolved", "path": "refs", "detail": "b.md"},
    ]


def test_the_real_sitting_refuses_with_the_same_words_rendered() -> None:
    hz = fresh("k10-invalid")
    bad = WriteRequest(NewCard("draft-in-batch"), Document(base_head(0, "draft"), {"Scope": BASE_SCOPE}), None)
    with pytest.raises(Refusal) as refused:
        hz.st.ratify([bad], OWNER)
    assert refused.value.rule == "ratify.invalid"
    assert refused.value.detail == f"{hz.st.journal.counter}: ratify.not-a-signed-act: created"


# ---- 8. config@3: root is immutable; a config@2 tenant migrates by one act ---------------------------------------


def test_config3_makes_root_immutable_and_a_config2_tenant_moves_by_one_signed_act(tmp_path: Path) -> None:
    """Q16's schema half. A tenant born on a K7-era toolkit adopts `config@2`, where `root` is a plain default and
    only the store's own gate (`config.root-mismatch`) holds it; the owner's file, edited to adopt `config@3`,
    handed over as one `config-policy` act, lands with `schema = 3`; from then on a policy write that moves or
    deletes `root` is `config.immutable` on the key — the schema's gate, before the store's."""
    clock = Clock(1_787_000_000)
    signer = SoftwareKeyAck(SoftwareKey.generate(), clock, time_skew_s=600)
    repo = MemGit()
    repo.commit(dict(REF_FILES), "seed@example", "2026-08-01T00:00:00Z", "seed")
    path = tmp_path / "journal.sqlite"
    v2 = Store(
        "k10mig",
        repo,
        Journal(path, "k10mig"),
        registry_without(tmp_path, "config@3", "config@4", "config@5", "config@6"),
        clock,
        signer,
        root="docs/work/",
    )
    v2.init(OWNER, software_key_ack="ok for K10")
    assert v2.config_tree["schema"] == 2 and v2.config_tree["chain_opened_under"] == 2
    moved = dict(v2.config_tree)
    moved["root"] = "other/"
    base = {"seq": v2.policy[-1]["seq"], "h": v2.policy[-1]["h"]}
    with pytest.raises(Refusal) as r:
        v2.write("config.toml", moved, base, None, OWNER)
    assert [(v.rule, v.path) for v in r.value.verdicts] == [("config.root-mismatch", "root")]  # type: ignore[attr-defined]

    # the K10 store over the same tenant: still config@2 until the owner's act
    st = Store("k10mig", repo, Journal(path, "k10mig"), REGISTRY, clock, signer, root="docs/work/")
    assert st.config_tree["schema"] == 2
    tree = copy.deepcopy(st.config_tree)  # deep: the manifest row below is edited in place
    tree["schema"] = 3
    next(row for row in tree["governed"] if row["path"] == "config.toml")["schema"] = "config@3"
    base = {"seq": st.policy[-1]["seq"], "h": st.policy[-1]["h"]}
    wr = st.write("config.toml", tree, base, None, OWNER)
    assert wr.entry["act"] == "config-policy" and sorted(wr.entry["fields"]) == ["governed", "schema"]
    assert st.config_tree["schema"] == 3 and st.config_tree["chain_opened_under"] == 2
    assert adopted_version(st.config_tree, REGISTRY) == 3
    # `root` is immutable now: moving it and deleting it are both `config.immutable` on the key
    for edit in ("move", "delete"):
        after = dict(st.config_tree)
        if edit == "move":
            after["root"] = "other/"
        else:
            del after["root"]
        base = {"seq": st.policy[-1]["seq"], "h": st.policy[-1]["h"]}
        with pytest.raises(Refusal) as r:
            st.write("config.toml", after, base, None, OWNER)
        assert [(v.rule, v.path) for v in r.value.verdicts] == [("config.immutable", "root")], edit  # type: ignore[attr-defined]
    assert st.config_tree["root"] == "docs/work/"


def test_config3_is_config2_plus_the_one_flag() -> None:
    """The registry documents differ in exactly the ways the bump names: the version, `immutable` on `root`, and
    the manifest row that adopts `config@3`."""
    two, three = REGISTRY.get("config@2"), REGISTRY.get("config@3")
    assert (two["version"], three["version"]) == (2, 3)
    root2 = next(s for s in two["scalars"] if s["name"] == "root")
    root3 = next(s for s in three["scalars"] if s["name"] == "root")
    assert "immutable" not in root2 and root3["immutable"] is True and {**root3, "immutable": None} != root2
    assert {k: v for k, v in root3.items() if k != "immutable"} == root2
    gov2 = next(t for t in two["tables"] if t["name"] == "governed")["default"]["value"]
    gov3 = next(t for t in three["tables"] if t["name"] == "governed")["default"]["value"]
    assert [r["schema"] for r in gov2 if r["path"] == "config.toml"] == ["config@2"]
    assert [r["schema"] for r in gov3 if r["path"] == "config.toml"] == ["config@3"]
    assert [r for r in gov3 if r["path"] != "config.toml"] == [r for r in gov2 if r["path"] != "config.toml"]
    assert [s for s in two["scalars"] if s["name"] != "root"] == [s for s in three["scalars"] if s["name"] != "root"]
    tables2 = [t for t in two["tables"] if t["name"] != "governed"]
    tables3 = [t for t in three["tables"] if t["name"] != "governed"]
    assert tables2 == tables3
