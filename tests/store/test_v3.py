"""V3 (2026-09-11) — the store's share of the ledger-and-dispatch chunk.

Three things the brief assumed and the code did not have (the v1c chunk plan's V3 findings): the dispatchable leaf is
policy (`config@5`'s `[ladder].leaf`, Q-V11 (a)), not the projection's literal; a store loaded from disk knows which
signatures are software-grade (F-b), because the policy says so rather than `init`'s memory; and the sidecar's
fingerprint is born at the land after a ratification with the blob of every ref at the ratifying commit (F-c, ruled
2026-09-11), so `dispatch.ref-drifted` has something to compare. And the one call the factory's pick makes over its
channel (F-a): the pending-land precondition and the ready view, then one card's check and fingerprint.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from isidium.store.core.grammar import Document, parse_jsonl
from isidium.store.core.refusal import Refusal
from isidium.store.server.api import Api
from isidium.store.server.gitrepo import MemGit
from isidium.store.server.journal import Journal
from isidium.store.server.signer import SoftwareKey, SoftwareKeyAck
from isidium.store.server.store import NewCard, Store

from .conftest import (
    BASE_SCOPE,
    LANDER,
    OWNER,
    PLANNER,
    REF_FILES,
    REGISTRY,
    Clock,
    Harness,
    base_head,
    fresh,
    git,
    path_of,
    store_on_disk,
    tenant_checkout,
)
from .test_k6 import registry_without

ROOT = "docs/work/"
EMPTY: dict[str, Any] = {"run_id": "r-0", "events": [], "suggestions": []}


def refuses(rule: str, fn: Any) -> Refusal:
    with pytest.raises(Refusal) as ei:
        fn()
    assert ei.value.rule == rule, str(ei.value)
    return ei.value


def ratified(hz: Harness, slug: str, **over: Any) -> int:
    cid = hz.draft(slug, **over)
    hz.st.ratify([cid], OWNER)
    return cid


def policy_write(st: Store, edit: Any) -> None:
    tree = copy.deepcopy(st.config_tree)
    edit(tree)
    st.write("config.toml", tree, {"seq": st.policy[-1]["seq"], "h": st.policy[-1]["h"]}, None, OWNER)


def fingerprint(st: Store, cid: int) -> Any:
    return st.state.get("cards", {}).get(f"{cid:04d}", {}).get("fingerprint")


def last_seq(st: Store, cid: int) -> int:
    return int(st.docs[path_of(st, cid)].history[-1]["seq"])


# ---- the leaf (Q-V6, Q-V11 (a)) ----------------------------------------------------------------------------------------


def test_the_schema_default_leaf_is_story_and_labels_a_ratified_story_ready() -> None:
    hz = fresh()
    a = ratified(hz, "a")
    assert hz.st.eff["ladder"]["leaf"] == "story", "config@5's declared default, through the effective config"
    assert hz.st.projection_of(a).ready and hz.st.projection_of(a).render() == "ready"


def test_a_declared_leaf_labels_its_own_kind_ready_and_a_story_no_longer() -> None:
    """The positive discriminator both ways: the leaf's kind turns `ready`, and the story that was `ready` a moment
    ago is `ratified` — the literal is gone, not supplemented."""
    hz = fresh()
    st = hz.st
    story = ratified(hz, "story")
    assert st.projection_of(story).ready

    def leaf_is_feature(tree: dict[str, Any]) -> None:
        tree["ladder"] = {"levels": ["feature"], "leaf": "feature"}

    policy_write(st, leaf_is_feature)
    feature = ratified(hz, "feature", kind="feature")
    assert st.projection_of(feature).ready, st.projection_of(feature).render()
    assert not st.projection_of(story).ready and st.projection_of(story).render() == "ratified"


def test_a_leaf_the_ladder_does_not_have_is_refused_config_enum() -> None:
    hz = fresh()
    st = hz.st
    seq = st.policy[-1]["seq"]

    def undeclared(tree: dict[str, Any]) -> None:
        tree["ladder"] = {"leaf": "feature"}

    with pytest.raises(Refusal) as ei:
        policy_write(st, undeclared)
    verdicts = list(getattr(ei.value, "verdicts", None) or [ei.value])
    assert [(v.rule, v.path) for v in verdicts] == [("config.enum", "ladder.leaf")], verdicts
    assert st.policy[-1]["seq"] == seq, "a refused policy write moved the chain"


# ---- software-grade from the policy (F-b) -------------------------------------------------------------------------------


def test_a_store_that_never_ran_init_still_reads_the_software_grade_from_the_policy() -> None:
    """Before V3 only `init()` added the ratifier's key to the software-grade set, on the instance that ran it; a
    store loaded from disk (every container restart) read `software_grade = False` for every card. Clearing that
    memory is the restart; the policy's `software_key_ack` + `pin` still say it."""
    hz = fresh()
    st = hz.st
    a = ratified(hz, "a")
    st.software_fprs.clear()
    assert st.eff["ratification"].get("software_key_ack") and st.eff["signer"]["backends"] == ["software_key_ack"]
    assert st.projection_of(a).software_grade is True, "the bound owner key signs software-grade (identity enabled)"
    assert st.dispatch()["ready"] == [{"id": a, "software_grade": True}]


# ---- the fingerprint at the land after a ratification (F-c) -------------------------------------------------------------


def test_the_land_after_a_ratification_folds_the_fingerprint_with_every_refs_blob_at_that_commit() -> None:
    hz = fresh()
    st = hz.st
    a = ratified(hz, "a")
    ratifying = st.repo.head
    assert fingerprint(st, a) is None
    r = st.land(EMPTY, LANDER)
    lines = parse_jsonl(st.raw["state/history.jsonl"].decode("utf-8"))
    assert [e["kind"] for e in lines] == ["ratified"] and r["events"] == ["e1"]
    fp = fingerprint(st, a)
    assert fp["ratified_seq"] == last_seq(st, a) and fp["commit"] == ratifying and fp["validator_version"] == "v3"
    assert fp["refs_resolved"] == [{"path": p, "blob": st.repo.oid_of(p)} for p in REF_FILES], "the written order"
    again = st.land(EMPTY, LANDER)
    assert again["empty"] is True and len(st.events) == 1, "a re-walk of the range emits the ratification once"


def test_a_re_ratification_after_a_ref_moved_replaces_the_fingerprint() -> None:
    hz = fresh()
    st = hz.st
    a = ratified(hz, "a")
    st.land(EMPTY, LANDER)
    first = fingerprint(st, a)
    head = st.repo.head
    assert head is not None
    moved_bytes = b"def validate_profile(head):\n    return ['moved']\n"
    st.repo.commit({"client/cards/validator.py": moved_bytes}, "dev", st.now(), "edit")
    moved = st.repo.oid_of("client/cards/validator.py")
    assert moved != first["refs_resolved"][0]["blob"]
    # the owner's gated edit of a ratified card is itself a signed `ratified` entry (no sitting needed)
    st.write_set(a, ['title="cards check refuses a ratified card with no acceptance block, re-read"'], OWNER)
    assert st.docs[path_of(st, a)].history[-1]["act"] == "ratified"
    st.land(EMPTY, LANDER)
    second = fingerprint(st, a)
    assert second["ratified_seq"] == last_seq(st, a) > first["ratified_seq"]
    assert second["refs_resolved"][0] == {"path": "client/cards/validator.py", "blob": moved}


def test_a_run_report_cannot_carry_a_ratification() -> None:
    hz = fresh()
    st = hz.st
    a = ratified(hz, "a")
    forged = {"kind": "ratified", "card": a, "seq": 1, "commit": "0" * 40, "refs_resolved": []}
    refuses("event.kind", lambda: st.land({"run_id": "r-1", "events": [forged], "suggestions": []}, LANDER))
    assert st.events == [] and fingerprint(st, a) is None


def test_a_config4_tenant_is_handed_no_ratified_line_and_keeps_its_story_leaf(tmp_path: Path) -> None:
    """Tenant #0 between the image swap and the owner's config@5 act: a V3 store over a tenant whose event file is
    still `sidecar-events@2` emits no `ratified` (that schema would refuse the line), and its projection keeps the
    leaf it always had, read from the newest shipped schema's default. After the act, a ratification that landed
    before it has no fingerprint (its entry is behind the landed head) — a new ratification is the way in."""
    clock = Clock(1_787_000_000)
    signer = SoftwareKeyAck(SoftwareKey.generate(), clock, time_skew_s=600)
    repo = MemGit()
    repo.commit(dict(REF_FILES), "seed@example", "2026-08-01T00:00:00Z", "seed")
    path = tmp_path / "journal.sqlite"
    v1 = Store("v3mig", repo, Journal(path, "v3mig"), registry_without(tmp_path, "config@5", "config@6"), clock, signer, root=ROOT)
    v1.init(OWNER, software_key_ack="ok for the migration test")
    r = v1.write(NewCard("before"), Document(base_head(0, "draft"), {"Scope": BASE_SCOPE}), None, None, PLANNER)
    assert r.id is not None
    v1.ratify([r.id], OWNER)
    st = Store("v3mig", repo, Journal(path, "v3mig"), REGISTRY, clock, signer, root=ROOT)
    assert st.config_tree["schema"] == 4 and st.row_for("state/history.jsonl")["schema"] == "sidecar-events@2"
    assert st.projection_of(r.id).ready, "config@4 has no leaf key: the newest shipped schema's default holds"
    st.land(EMPTY, LANDER)
    assert all(e["kind"] != "ratified" for e in st.events) and fingerprint(st, r.id) is None

    def adopt5(tree: dict[str, Any]) -> None:
        tree["schema"] = 5
        for row in tree.get("governed", []):
            if row["path"] == "config.toml":
                row["schema"] = "config@5"
            if row["path"] == "state/history.jsonl":
                row["schema"] = "sidecar-events@3"

    policy_write(st, adopt5)
    assert st.row_for("state/history.jsonl")["schema"] == "sidecar-events@3"
    st.land(EMPTY, LANDER)
    assert fingerprint(st, r.id) is None, "a ratification landed before config@5 is behind the head: no fingerprint"
    n = st.write(NewCard("after"), Document(base_head(0, "draft"), {"Scope": BASE_SCOPE}), None, None, PLANNER)
    assert n.id is not None
    st.ratify([n.id], OWNER)
    st.land(EMPTY, LANDER)
    assert fingerprint(st, n.id)["ratified_seq"] == last_seq(st, n.id)


def test_on_real_git_the_fingerprints_blobs_come_from_one_ls_tree_of_the_ratifying_commit(tmp_path: Path) -> None:
    work = tenant_checkout(tmp_path)
    st = store_on_disk(work, tmp_path / "journal.sqlite", root=ROOT)
    st.init(OWNER, software_key_ack="ok for V3 on disk", root=ROOT)
    r = st.write(NewCard("on-disk"), Document(base_head(0, "draft"), {"Scope": BASE_SCOPE}), None, None, PLANNER)
    assert r.id is not None
    st.ratify([r.id], OWNER)
    ratifying = st.repo.head
    st.land(EMPTY, LANDER)
    fp = fingerprint(st, r.id)
    assert fp["commit"] == ratifying
    git(work, "fetch", "-q", "origin")
    for row in fp["refs_resolved"]:
        assert row["blob"] == git(work, "rev-parse", f"{ratifying}:{row['path']}").strip(), row
    assert [row["path"] for row in fp["refs_resolved"]] == list(REF_FILES)


# ---- row 11 is per card, not by clock (V3b) ------------------------------------------------------------------------


def test_a_ratification_made_after_the_merge_the_land_lands_on_is_ready() -> None:
    """V3b, found live on tenant #0 at V3's live step. The cursor is the batch pull request's merge (X2 pin 3), so
    `landed_at` is **that merge's** time — older than a ratification made after it. Row 11 used to compare the two,
    and answered `pending-ingest` for a card the same land had ingested and fingerprinted; no later land could clear
    it, a land with nothing new being an empty diff (Q-W10). The question is per card, and the sidecar's
    `history_head` is the fact that answers it."""
    hz = fresh()
    st = hz.st
    main = st.repo.head
    assert main is not None
    branch = st.repo.commit({"src/f.py": b"print('built')\n"}, "builder", st.now(), "batch b1: code", parents=[main])
    st.repo.head = main  # type: ignore[misc]
    merge = st.repo.commit({"src/f.py": b"print('built')\n"}, "forge", st.now(), "merge b1", parents=[main, branch])
    a = ratified(hz, "after-the-merge")  # the ratification is later than the merge, as it was live
    r = st.land(EMPTY, LANDER)
    assert r["cursor"] == merge and st.state["landed_at"] == st.repo.commit_time(merge)
    entry = st.docs[path_of(st, a)].history[-1]
    assert str(entry["at"]) > str(st.state["landed_at"]), "the ratification is newer than the cursor's commit"
    assert st.state["cards"][f"{a:04d}"]["history_head"]["seq"] == int(entry["seq"]), "and this land ingested it"
    assert st.projection_of(a).render() == "ready" and st.projection_of(a).ready
    assert st.dispatch()["ready"] == [{"id": a, "software_grade": True}]
    assert fingerprint(st, a)["ratified_seq"] == int(entry["seq"])


def test_a_ratification_no_land_has_seen_is_pending_ingest() -> None:
    """The other side, unchanged: until a land records the card's head, the card is not the factory's to pick."""
    hz = fresh()
    st = hz.st
    a = ratified(hz, "landed")
    st.land(EMPTY, LANDER)
    assert st.projection_of(a).ready
    b = ratified(hz, "not-landed-yet")
    assert st.projection_of(b).render() == "ratified (pending-ingest)" and not st.projection_of(b).ready
    assert st.dispatch()["ready"] == [{"id": a, "software_grade": True}], "only the ingested card is pickable"


def test_a_tenant_with_no_sidecar_reads_ratified() -> None:
    """Before the first land, and the standalone case: no sidecar, no per-card head, and the label is `ratified` —
    what the timestamp guard (`if landed_at and …`) gave and what the new one keeps."""
    hz = fresh()
    a = ratified(hz, "no-sidecar-yet")
    assert hz.st.state == {} and hz.st.projection_of(a).render() == "ready"


# ---- the dispatch call (F-a) --------------------------------------------------------------------------------------------


def test_the_dispatch_call_answers_the_ready_view_and_one_cards_check_and_fingerprint() -> None:
    hz = fresh()
    st = hz.st
    a = ratified(hz, "a")
    hz.draft("still-a-draft")
    view = st.dispatch()
    assert view == {"ready": [{"id": a, "software_grade": True}]}, view
    one = st.dispatch(a)
    assert one["card"] == a and one["check"]["id"] == a and one["check"]["integrity"] == []
    assert one["fingerprint"] is None, "not landed yet"
    st.land(EMPTY, LANDER)
    assert st.dispatch(a)["fingerprint"]["ratified_seq"] == last_seq(st, a)


def test_the_lander_may_call_dispatch_over_the_api_and_a_contributor_may_not() -> None:
    hz = fresh()
    a = ratified(hz, "a")
    api = Api(hz.st)
    assert "dispatch" in Api.CALLS
    assert api.call("dispatch", LANDER, {})["ready"] == [{"id": a, "software_grade": True}]
    assert api.call("dispatch", LANDER, {"card": a})["card"] == a
    refuses("write.grant", lambda: api.call("dispatch", PLANNER, {}))
    refuses("write.grant", lambda: api.call("check", LANDER, {"id": a}))  # the reasons ride `dispatch`, not `check`
