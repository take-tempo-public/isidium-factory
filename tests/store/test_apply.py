"""The WP2 review's apply pass (sync 7bf.7): each finding that had no test gets one — C1 the row lock across the
signer's round trip; C2 the X1 display durable across a restart; C3 the entries-since shape; C4 a NewCard member in
the batch; C5/C6 the landed-closure compare; C7 refs resolve at ratification; C8 the accepted ref binds a closure;
C9 check's whole-set rules; C10 line endings preserved; C12 time_skew from config; C15 the caller-aware clause on a
status MOVE; E1 one projection per show; E3 the id index."""

from __future__ import annotations

import copy
from typing import Any

import pytest

from isidium.store.core import canon, chain
from isidium.store.core import refs as refs_mod  # the pure half lives under core/ since K4b; the store keeps `resolve`
from isidium.store.core.grammar import CARD, Document, emit_markdown, parse_markdown
from isidium.store.core.refusal import Refusal
from isidium.store.registry.loader import Registry
from isidium.store.server.gitrepo import MemGit, blob_id
from isidium.store.server.journal import Journal
from isidium.store.server.signer import SoftwareKeyAck
from isidium.store.server.store import NewCard, Store, WriteRequest

from .conftest import BASE_SCOPE, OWNER, PLANNER, REF_FILES, Clock, Harness, base_head, fresh, path_of


def refuses(rule: str, fn: Any) -> Refusal:
    with pytest.raises(Refusal) as ei:
        fn()
    assert ei.value.rule == rule, str(ei.value)
    return ei.value


def test_c1_row_lock_held_across_the_signing_round_trip() -> None:
    hz = fresh()
    st = hz.st
    a = hz.draft("locked")
    seen: list[str] = []

    class ReentrantSigner(SoftwareKeyAck):
        def sign(self, tenant: str, value: str, at_epoch: int, display: Any, time_skew_s: int | None = None) -> str:
            try:
                st.write_set(a, ['summary="sneaked in"'], PLANNER)
            except Refusal as r:
                seen.append(r.rule)
            return super().sign(tenant, value, at_epoch, display, time_skew_s)

    st.signer = ReentrantSigner(hz.key, hz.clock)
    r = st.ratify([a], OWNER)
    assert seen == ["write.locked"]
    doc, _ = st.show(a)
    assert [e["act"] for e in doc.history] == ["created", "ratified"] and "summary" not in doc.head
    assert st.check(a)["integrity"] == [] and r["ids"] == [a]


def test_c2_x1_display_is_durable_across_a_restart(tmp_path: Any) -> None:
    clock = Clock(1_787_000_000)
    from isidium.store.server.signer import SoftwareKey

    key = SoftwareKey.generate()
    signer = SoftwareKeyAck(key, clock)
    repo = MemGit()
    repo.commit(dict(REF_FILES), "seed@example", "2026-08-01T00:00:00Z", "seed the ref targets")
    jpath = tmp_path / "j.sqlite"
    st = Store("t", repo, Journal(jpath, "t"), Registry.shipped(), clock, signer, root="docs/work/")
    st.init(OWNER, software_key_ack="ok")
    r = st.write(NewCard("durable"), Document(base_head(0, "draft"), {"Scope": BASE_SCOPE}), None, None, PLANNER)
    cid = r.id
    assert cid is not None
    st.ratify([cid], OWNER)
    st.write_set(cid, ['hold.kind="blocked"', "hold.on.owner=true"], PLANNER)
    # a fresh store over the same repo + journal: the last-signed baseline comes from the journal, not memory
    st2 = Store("t", repo, Journal(jpath, "t"), Registry.shipped(), clock, signer, root="docs/work/")
    doc, head = st2.show(cid)
    after = Document(copy.deepcopy(doc.head), copy.deepcopy(doc.sections))
    after.head.pop("hold")
    dry = st2.ratify([WriteRequest(str(st2.path_of(cid)), after, head)], OWNER, dry_run=True)
    since = dry["display"][0][3]
    # the hold was set AFTER the signature and cleared here: the state diff is empty (C1 a) and the entries carry it
    assert since is not None and since["tending"] == {} and st2.journal.signed_get(str(st2.path_of(cid))) is not None
    # C3: entries since the signed entry are the held/released/demoted ones, with by and at
    assert [(e[1], e[3]) for e in since["entries_since"]] == [("held", PLANNER.principal)] and since["entries_since"][
        0
    ][4]


def test_c4_newcard_rides_the_batch(hz: Harness) -> None:
    st, signer = hz.st, hz.signer
    calls = signer.calls
    born = WriteRequest(NewCard("born-in-batch"), Document(base_head(0, "ratified"), {"Scope": BASE_SCOPE}), None)
    dry = st.ratify([born], OWNER, dry_run=True)
    pid = next(iter(dry["verdicts"]))
    assert dry["verdicts"][pid] == [] and dry["display"][0][1] == "created" and signer.calls == calls
    assert st.journal.counter + 1 == pid  # prospective on the dry run, not allocated
    r = st.ratify([born], OWNER)
    cid = r["ids"][0]
    assert cid == pid and signer.calls == calls + 1
    doc, _ = st.show(cid)
    assert (
        doc.head["status"] == "ratified"
        and doc.history[0]["act"] == "created"
        and doc.history[0]["batch"] == r["batch"]
    )
    assert "sig" not in doc.history[0] and st.verify_entry(doc.history[0]) and st.check(cid)["integrity"] == []
    # a NewCard draft may not ride the batch (a creation that needs no signature is write's)
    bad = WriteRequest(NewCard("draft-in-batch"), Document(base_head(0, "draft"), {"Scope": BASE_SCOPE}), None)
    assert any(
        v["rule"] == "ratify.not-a-signed-act"
        for v in next(iter(st.ratify([bad], OWNER, dry_run=True)["verdicts"].values()))
    )


def test_c5_landed_closure_by_seq_compare(hz: Harness) -> None:
    st = hz.st
    g = hz.draft("landed-seq")
    st.ratify([g], OWNER)
    doc, head = st.show(g)
    cl = Document(copy.deepcopy(doc.head), copy.deepcopy(doc.sections))
    cl.head["closures"] = [
        {
            "id": "c1",
            "kind": "human",
            "outcome": "met",
            "verdicts": {"S1": "pass", "S2": "pass"},
            "evidence": [],
            "retracted": False,
        }
    ]
    cl.head["status"] = "closed"
    r = st.write(path_of(st, g), cl, head, None, PLANNER)
    closed_seq = r.entry["seq"]
    doc, head = st.show(g)
    rt = Document(copy.deepcopy(doc.head), copy.deepcopy(doc.sections))
    rt.head["closures"][0]["retracted"] = True
    rt.head["status"] = "ratified"
    # the sidecar's head BELOW the closed entry: not landed → the contributor may retract
    st.state = {"cards": {f"{g:04d}": {"history_head": {"seq": closed_seq - 1, "h": "x"}}}}
    dry = st.ratify([WriteRequest(str(st.path_of(g)), rt, head)], PLANNER, dry_run=True)
    assert any(v["rule"] == "ratify.not-a-signed-act" for v in dry["verdicts"][g])  # unsigned = write's, not ratify's
    # the sidecar's head AT the closed entry: landed → the owner's
    st.state = {"cards": {f"{g:04d}": {"history_head": {"seq": closed_seq, "h": "x"}}}}
    refuses("write.requires-owner", lambda: st.write(path_of(st, g), rt, head, None, PLANNER))
    st.state = {}


CODE = b"def resolve_me():\n    pass\n\nclass Twice:\n    pass\nclass Twice:\n    pass\n"
NOTES = b"# Title\n\n## The Anchor Here\n\ntext\n"


def test_c7_refs_resolve_at_ratification(hz: Harness) -> None:
    """**The store's half** [Q11, ruled 2026-08-31]: the path exists in the tree, its blob id, and it is outside the
    tracking root — from the tree, reading no content, because the store's clone holds none for a ref's target.

    What the store can still refuse is what its trees can see, so `ref.unresolved` on a path that is not there and
    `ref.inside-root` both hold. What it no longer refuses is the *locus* — the line range, the anchor, the symbol —
    and the companion test below is what stops that from being a silent loss.
    """
    st = hz.st
    st.repo.commit({"src/thing.py": CODE, "docs/notes.md": NOTES}, "someone", st.now(), "code")
    good = hz.draft(
        "refs-good",
        refs=["src/thing.py", "src/thing.py:1-2", "docs/notes.md#the-anchor-here", "src/thing.py::resolve_me"],
    )
    assert st.ratify([good], PLANNER, dry_run=True)["verdicts"][good] == []
    # the four whose locus is wrong now pass the store: their *paths* are in the tree, which is all the store sees
    locus_only = hz.draft(
        "refs-bad-locus",
        refs=["src/thing.py:1-99", "docs/notes.md#missing", "src/thing.py::Twice", "src/thing.py::absent"],
    )
    assert st.ratify([locus_only], PLANNER, dry_run=True)["verdicts"][locus_only] == []
    # and the one whose path is absent is still refused, by the store, at ratification
    gone = hz.draft("refs-gone", refs=["nope.md"])
    verdicts = st.ratify([gone], PLANNER, dry_run=True)["verdicts"][gone]
    assert [v["rule"] for v in verdicts] == ["ref.unresolved"]
    refuses("ratify.invalid", lambda: st.ratify([gone], OWNER))
    inside = hz.draft("refs-inside", refs=["docs/work/cards/0001-x.md"])  # a repo path, under the harness's root
    assert st.ratify([inside], PLANNER, dry_run=True)["verdicts"][inside][0]["rule"] == "ref.inside-root"
    # **the store recorded the blob the tree names** — the fingerprint's input, and drift's, is unchanged by any of
    # this, which is the claim Q11 turns on
    resolved, _rs = st._resolve_refs(st.docs[str(st.path_of(good))])
    assert {r["path"]: r["blob"] for r in resolved}["src/thing.py"] == blob_id(CODE, st.repo.object_format)
    # a card born ratified still resolves at the write, and still refuses on a path that is not there
    head = base_head(0, "ratified")
    head["refs"] = ["nope.md"]
    r = refuses(
        "validate.failed",
        lambda: st.write(NewCard("born-bad-ref"), Document(head, {"Scope": BASE_SCOPE}), None, None, OWNER),
    )
    assert "ref.unresolved" in r.detail


def test_c7_the_locus_check_still_catches_what_the_store_no_longer_can(hz: Harness) -> None:
    """**The other half of Q11, and the reason the ruling is a move rather than a loss.**

    `locus_check` is the function T-B3's assembler runs at dispatch, from the project checkout, and it is the one
    K4b will run at the author's terminal. Exactly one implementation exists and this is it — a second copy is how
    the two halves would drift apart, so this test calls the same function the assembler will.

    The refs are the four the store above accepted. Every one of them is still caught, and `ref.ambiguous` — which
    the store can no longer raise at all — is still raised here.
    """
    # one `Locus` per file — the text indexed once for every ref that cites it (K7b, F27)
    locus_of = {"src/thing.py": refs_mod.Locus(CODE), "docs/notes.md": refs_mod.Locus(NOTES)}
    verdicts = [
        refs_mod.locus_check(refs_mod.Ref.parse(text), locus_of[text.split(":")[0].split("#")[0]])
        for text in ["src/thing.py:1-99", "docs/notes.md#missing", "src/thing.py::Twice", "src/thing.py::absent"]
    ]
    assert verdicts == ["ref.unresolved", "ref.unresolved", "ref.ambiguous", "ref.unresolved"]
    # and the four the store accepted for real reasons still pass here, so this is not a check that refuses anything
    good = ["src/thing.py", "src/thing.py:1-2", "docs/notes.md#the-anchor-here", "src/thing.py::resolve_me"]
    assert [refs_mod.locus_check(refs_mod.Ref.parse(t), locus_of[t.split(":")[0].split("#")[0]]) for t in good] == [
        None,
        None,
        None,
        None,
    ]


def test_c8_accepted_ref_binds_a_real_closure(hz: Harness) -> None:
    st = hz.st
    c = hz.draft("accept-bind")
    st.ratify([c], OWNER)
    doc, head = st.show(c)
    closed = Document(copy.deepcopy(doc.head), copy.deepcopy(doc.sections))
    closure = {
        "id": "c1",
        "kind": "human",
        "outcome": {"deviated": {"description": "x"}},
        "verdicts": {"S1": "pass", "S2": "manual"},
        "evidence": [],
        "retracted": False,
    }
    closed.head["closures"] = [closure]
    closed.head["status"] = "closed"
    st.write(path_of(st, c), closed, head, None, PLANNER)
    doc, head = st.show(c)
    same = Document(copy.deepcopy(doc.head), copy.deepcopy(doc.sections))
    refuses("ref.closure-mismatch", lambda: st.write(path_of(st, c), same, head, "c9:sha256:" + "de" * 32, OWNER))
    refuses("ref.closure-mismatch", lambda: st.write(path_of(st, c), same, head, "c1:sha256:" + "de" * 32, OWNER))
    refuses("ref.grammar", lambda: st.write(path_of(st, c), same, head, "garbage", OWNER))
    r = st.write(path_of(st, c), same, head, canon.closure_ref(closure), OWNER)
    assert r.entry["act"] == "accepted" and "sig" in r.entry


def test_c9_check_runs_the_whole_set_rules(hz: Harness) -> None:
    st = hz.st
    a = hz.draft("dup-a")
    p = str(st.path_of(a))
    # a second file claiming the same id, committed outside the store
    dup_path = st.card_path(a, "dup-b")
    st.repo.commit({st.rp(dup_path): st.raw[p]}, "someone", st.now(), "duplicate id")
    st.load()  # a CI checkout: the store re-reads the tree
    res = st.check(a)
    assert any(r.startswith("id.unique") for r in res["profile"])


def test_c10_writes_preserve_the_files_line_endings(hz: Harness) -> None:
    st = hz.st
    cid = hz.draft("crlf")
    p = str(st.path_of(cid))
    raw = st.raw[p].decode("utf-8")
    crlf = raw.replace("\n", "\r\n")
    doc = parse_markdown(crlf, CARD)
    out = emit_markdown(doc, CARD)
    assert "\r\n" in out and out.count("\r\n") == out.count("\n")
    # a hand-committed CRLF card (e.g. checked out by a Windows client): the store keeps CRLF on its next write
    st.repo.commit({st.rp(p): crlf.encode("utf-8")}, "someone", st.now(), "crlf checkout")
    st.load()
    r = st.write_set(cid, ['summary="kept"'], PLANNER)
    data = st.raw[p]
    assert data.count(b"\r\n") == data.count(b"\n") and r.entry["act"] == "summarized"


def test_c12_time_skew_comes_from_config(hz: Harness) -> None:
    st, signer = hz.st, hz.signer
    cid = hz.draft("skew")
    tree = copy.deepcopy(st.config_tree)
    tree["time_skew"] = 30
    st.write("config.toml", tree, {"seq": st.policy[-1]["seq"], "h": st.policy[-1]["h"]}, None, OWNER)
    saved = signer.clock
    signer.clock = lambda: hz.clock.t + 120  # inside the signer's own default (600), outside the tenant's 30
    refuses("signer.time-skew", lambda: st.ratify([cid], OWNER))
    signer.clock = saved
    tree = copy.deepcopy(st.config_tree)
    tree["time_skew"] = 600
    st.write("config.toml", tree, {"seq": st.policy[-1]["seq"], "h": st.policy[-1]["h"]}, None, OWNER)


def test_c15_caller_aware_clause_needs_a_status_move(hz: Harness) -> None:
    st = hz.st
    h = hz.draft("second-closure")
    st.ratify([h], OWNER)
    doc, head = st.show(h)
    cl = Document(copy.deepcopy(doc.head), copy.deepcopy(doc.sections))
    cl.head["closures"] = [
        {
            "id": "c1",
            "kind": "human",
            "outcome": "met",
            "verdicts": {"S1": "pass", "S2": "pass"},
            "evidence": [],
            "retracted": False,
        }
    ]
    cl.head["status"] = "closed"
    r = st.write(path_of(st, h), cl, head, None, OWNER)
    assert "sig" in r.entry  # status moved to closed: the owner's close
    doc, head = st.show(h)
    cl2 = Document(copy.deepcopy(doc.head), copy.deepcopy(doc.sections))
    cl2.head["closures"].append(
        {
            "id": "c2",
            "kind": "human",
            "outcome": "met",
            "verdicts": {"S1": "pass", "S2": "pass"},
            "evidence": [],
            "retracted": False,
        }
    )
    r = st.write(path_of(st, h), cl2, head, None, OWNER)
    assert r.entry["act"] == "closed" and "sig" not in r.entry  # status unchanged: a claim, not the owner's close


def test_e1_e3_one_projection_per_show_and_the_id_index(hz: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    st = hz.st
    from isidium.store.core import status as status_mod

    calls = {"project": 0, "hash": 0}
    orig_project, orig_hash = status_mod.project, canon.build_hash

    def counted_project(inp: Any) -> Any:
        calls["project"] += 1
        return orig_project(inp)

    def counted_hash(*a: Any, **k: Any) -> str:
        calls["hash"] += 1
        return orig_hash(*a, **k)

    monkeypatch.setattr(status_mod, "project", counted_project)
    monkeypatch.setattr(canon, "build_hash", counted_hash)
    st.show("Board")
    assert calls["project"] == 1 and calls["hash"] == 0  # every card's build hash came from the cache
    assert st.path_of(1) is not None and st._by_id[1] == st.path_of(1)
    # the chain is what the projection verified; a signature never re-hashed the file
    assert chain.verify_chain(st.show(1)[0].history, chain.genesis("card", 1))[0] == "ok"
