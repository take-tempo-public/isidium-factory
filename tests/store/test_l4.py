"""L4 (2026-09-09) — ingest's land-time half: the reconciliation walk runs inside `land` over `(last cursor, head]`,
its six reasons land in `state.json` where row 1 reads them, the overflow lands, and the card acts the walk sees
become the ledger's own transitions (Q-W8). Every test names the property and asserts its positive discriminator.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from isidium.store.core import events as events_mod
from isidium.store.core.grammar import parse_jsonl
from isidium.store.server import reconcile
from isidium.store.server.gitrepo import CommitChange, coauthors_of
from isidium.store.server.store import Store

from .conftest import LANDER, OWNER, PLANNER, Harness, fresh, store_on_disk
from .test_k7b import Spawns, _governed_tenant

ROOT = "docs/work/"


def ratified(hz: Harness, slug: str) -> int:
    cid = hz.draft(slug)
    hz.st.ratify([cid], OWNER)
    return cid


def path_of(st: Store, cid: int) -> str:
    p = st.path_of(cid)
    assert p is not None
    return p


def bypass(st: Store, path: str, data: bytes, author: str = "stranger@example", message: str = "hand edit") -> str:
    """A commit on `main` made outside the store — no journal row, a stranger's author — **and the store re-reading
    the path**, as a restarted container would: the double's `fetch` is a no-op, so without this the store's own
    next row would name the blob it remembers, not the one on `main` (the L4 finding recorded in the chunk plan;
    on real git the K4 door refuses the write instead — `git.push-rejected` on a governed path moved)."""
    sha = st.repo.commit({st.rp(path): data}, author, st.now(), message)
    st._ingest_file(path, str(st.row_for(path)["schema"]), data)
    return sha


# ---- the briefing's two oracles -------------------------------------------------------------------------------------


def test_a_bypass_commit_between_two_lands_lands_unjournaled_and_row_1_reads_it() -> None:
    """9.5 / F7: a hand edit to a card between two lands is `integrity:unjournaled` in the landed state — and,
    since it added no entry, `tampered` too (a commit carries exactly one entry). The second land is not empty
    though nothing was reported and the cursor did not move; the board's row 1 reads the landed reasons; a third
    land with nothing new is the empty diff again (the reasons equal the landed ones)."""
    hz = fresh()
    st = hz.st
    a = ratified(hz, "a")
    st.land({"run_id": "r-0", "events": []}, LANDER)
    assert st.state["integrity"] == {} and st.projections()[a].label.row != "integrity"
    p = path_of(st, a)
    edited = st.raw[p].replace(b"## Scope\n", b"## Scope\n\nA line written by hand, outside the store.\n", 1)
    assert edited != st.raw[p]
    sha = bypass(st, p, edited)
    r = st.land({"run_id": "r-1", "events": []}, LANDER)
    assert r["empty"] is False and r["cursor"] == st.state["ledger_cursor"], "a bypass lands even at the same cursor"
    s = json.loads(st.raw["state.json"].decode("utf-8"))
    assert s["schema"] == 2 and s["integrity"] == {p: {"tampered": [sha], "unjournaled": [sha]}}, s["integrity"]
    label = st.projections()[a].label
    assert label.row == "integrity" and "unjournaled" in label.reasons, label
    assert "unjournaled" in st.check(a)["integrity"], "check and land disagree on the same repo state"
    again = st.land({"run_id": "r-2", "events": []}, LANDER)
    assert again["empty"] is True, "the same reasons at the same cursor are the empty diff"
    assert sha in st.repo.first_parent_walk(st.state["ledger_cursor"]), "the bypass sits after the cursor"


def test_a_suggestion_over_the_inbox_bound_lands_as_overflow() -> None:
    """9.5: `suggestion-overflow` is an ingest fact the sidecar carries (`ingest.overflow`), not the result's alone."""
    hz = fresh()
    st = hz.st
    a = ratified(hz, "a")
    cap = int(st.eff["inbox"]["max_per_run"])
    suggestions = [{"kind": "debt", "title": f"s{i}", "body": "x", "refs": []} for i in range(cap + 2)]
    r = st.land(
        {"run_id": "r-1", "events": [{"kind": "dispatched", "card": a, "run_id": "r-1"}], "suggestions": suggestions},
        LANDER,
    )
    assert r["overflow"] == 2 and st.state["ingest"] == {"run_id": "r-1", "overflow": 2}
    assert len(r["intake"]) == cap


# ---- the six reasons, one variable each -----------------------------------------------------------------------------


def test_each_reason_from_one_transition_with_one_variable_moved() -> None:
    """`reconcile.reasons` over a real ratification (draft → ratified, one signed entry): clean against the store's
    own verifier and the caller as author; then one input moved at a time — the verifier says no (`unverified`),
    a stranger authored the commit (`attribution`, cleared by a `Co-Authored-By` trailer), the entry is stamped
    after the commit beyond `time_skew` (`time`), the landed head names another `h` (`rewritten`), the rows are
    gone (`unjournaled`)."""
    hz = fresh()
    st = hz.st
    cid = hz.draft("a")
    p = path_of(st, cid)
    before, bb = copy.deepcopy(st.docs[p]), st._blob[p]
    st.ratify([cid], OWNER)
    after, ab = st.docs[p], st._blob[p]
    rows = st.journal.rows_for(p)
    e = after.history[-1]
    ctx = reconcile.Context(st.gated_x(), st.verify_entry, st.time_skew())
    commit = CommitChange("x" * 40, OWNER.principal, (), str(e["at"]), {})

    def run(**over: Any) -> set[str]:
        kw: dict[str, Any] = {"landed_head": None, "commit": commit, **over}
        c = kw.pop("ctx", ctx)
        return set(reconcile.reasons(before, after, bb, ab, kw.pop("rows", rows), c, **kw))

    assert run() == set(), "the control is clean"
    assert run(ctx=reconcile.Context(st.gated_x(), lambda _e: False, st.time_skew())) == {"unverified"}
    stranger = CommitChange("x" * 40, "stranger@example", (), str(e["at"]), {})
    assert run(commit=stranger) == {"attribution"}
    vouched = CommitChange("x" * 40, "stranger@example", (OWNER.principal,), str(e["at"]), {})
    assert run(commit=vouched) == set(), "a Co-Authored-By trailer corroborates `by`"
    early = CommitChange("x" * 40, OWNER.principal, (), "2020-01-01T00:00:00Z", {})
    assert run(commit=early) == {"time"}
    assert run(landed_head={"seq": 1, "h": "sha256:" + "0" * 64}) == {"rewritten"}
    assert run(landed_head={"seq": 1, "h": after.history[0]["h"]}) == set(), "the landed head is the entry landed"
    assert run(rows=[]) == {"unjournaled"}
    assert run(commit=None) == set(), "without a commit the two commit-borne reasons are not computed"


def test_the_stores_own_commits_carry_the_caller_and_a_replayed_one_by_a_stranger_is_attribution() -> None:
    """1.15: `by` is corroborated by the commit's author. The store commits as the caller, so a land over its own
    ratification flags nothing; the same blob committed by a stranger in its place is `attribution` — and only
    that, the rows explaining the blob and the signature verifying."""
    hz = fresh()
    st = hz.st
    cid = hz.draft("a")
    st.land({"run_id": "r-0", "events": []}, LANDER)
    p = path_of(st, cid)
    st.ratify([cid], OWNER)
    ratify_commit = st.repo.head
    assert ratify_commit is not None
    st.land({"run_id": "r-1", "events": []}, LANDER)
    assert st.state["integrity"] == {}, "the store's own commit is authored by the caller"
    parent = st.repo.parents(ratify_commit)[0]
    st.repo.head = parent  # type: ignore[misc]
    sha = st.repo.commit({st.rp(p): st.raw[p]}, "stranger@example", st.now(), "the same bytes, someone else's commit")
    st.land({"run_id": "r-2", "events": []}, LANDER)
    assert st.state["integrity"] == {p: {"attribution": [sha]}}


def test_a_rewritten_entry_below_the_landed_head_is_rewritten() -> None:
    """A bypass that alters the `h` of an entry the sidecar already landed: `rewritten` beside the others."""
    hz = fresh()
    st = hz.st
    a = ratified(hz, "a")
    st.land({"run_id": "r-0", "events": []}, LANDER)
    p = path_of(st, a)
    h = str(st.docs[p].history[-1]["h"])
    forged = st.raw[p].replace(h.encode(), ("sha256:" + "f" * 64).encode(), 1)
    assert forged != st.raw[p]
    sha = bypass(st, p, forged)
    st.land({"run_id": "r-1", "events": []}, LANDER)
    assert "rewritten" in st.state["integrity"][p] and st.state["integrity"][p]["rewritten"] == [sha]


def test_a_hand_written_entry_on_a_real_change_is_tampered_by_the_recompute() -> None:
    """1.15: *"an entry that matches is byte-identical to what `write` would have produced"* — a bypass that edits
    the Scope and appends its own entry claiming `created` with the old build: exactly one entry added, the author
    the owner, so neither the entry-count rule nor attribution fires — the recompute alone says `tampered`."""
    hz = fresh()
    st = hz.st
    a = ratified(hz, "a")
    st.land({"run_id": "r-0", "events": []}, LANDER)
    p = path_of(st, a)
    last = st.docs[p].history[-1]
    line = (
        f'  {{ seq = {int(last["seq"]) + 1}, at = "{st.now()}", by = "{OWNER.principal}", act = "created", '
        f'fields = ["scope"], build = "{last["build"]}", h = "sha256:{"0" * 64}" }},\n'
    )
    raw = st.raw[p].replace(b"## Scope\n", b"## Scope\n\nEdited by hand.\n", 1)
    idx = raw.rindex(b"]\n```")
    forged = raw[:idx] + line.encode("utf-8") + raw[idx:]
    assert forged != st.raw[p]
    sha = bypass(st, p, forged, author=OWNER.principal)
    st.land({"run_id": "r-1", "events": []}, LANDER)
    assert st.state["integrity"][p] == {"tampered": [sha], "unjournaled": [sha]}, st.state["integrity"]


def test_a_commit_older_than_the_landed_head_is_not_rewritten_when_the_range_walks_it_again() -> None:
    """Live on tenant #0 (2026-09-10): the cursor stays behind the head while nothing merges, so every land walks
    the same commits again — and a card's draft commit, holding one entry, read `rewritten` against the head its
    close had landed. An older commit has fewer entries; only an entry AT the landed seq with another `h` is a
    rewrite."""
    hz = fresh()
    st = hz.st
    st.land({"run_id": "r-0", "events": []}, LANDER)
    cursor = st.state["ledger_cursor"]
    a = ratified(hz, "a")  # two commits after the cursor: the draft (one entry) and the ratification (two)
    r = st.land({"run_id": "r-1", "events": []}, LANDER)
    assert r["empty"] is False, "a new head is an input of the empty diff: the ratification lands its head"
    assert st.state["cards"][f"{a:04d}"]["history_head"]["seq"] == 2 and st.state["integrity"] == {}
    assert st.land({"run_id": "r-1b", "events": []}, LANDER)["empty"] is True, "and the same heads again are empty"
    r = st.land({"run_id": "r-2", "events": [{"kind": "question", "card": a, "text": "again"}]}, LANDER)
    assert r["cursor"] != cursor, "the clean range advanced the cursor [Q-W10 (a)]"
    # the same range walked again from the first cursor, as every land did before Q-W10: not a rewrite
    integrity, _acts, clean = st._reconcile_range(cursor)
    assert integrity == {} and clean, "the draft commit is older than the landed head, not a rewrite"
    assert st.state["integrity"] == {}
    assert st.check(a)["integrity"] == []


def test_a_non_card_governed_path_is_reconciled_by_the_chain_alone_and_a_repair_clears_it() -> None:
    """The board is governed; a hand commit to it is `unjournaled` at the next land under its own path (Q-W7 (a):
    the home is the path, a card being not the only governed document). `repair --journal` writes the missing row
    and the next land clears it — reasons are recomputed, never accumulated."""
    hz = fresh()
    st = hz.st
    a = ratified(hz, "a")
    st.land({"run_id": "r-0", "events": [{"kind": "dispatched", "card": a, "run_id": "r-0"}]}, LANDER)
    assert "BOARD.md" in st.raw
    sha = bypass(st, "BOARD.md", st.raw["BOARD.md"] + b"\nhand-written line\n")
    st.land({"run_id": "r-1", "events": []}, LANDER)
    assert st.state["integrity"] == {"BOARD.md": {"unjournaled": [sha]}}
    assert st.projections()[a].label.row != "integrity", "a board reason is not a card's"
    st.repair(OWNER, journal=sha)
    st.land({"run_id": "r-2", "events": []}, LANDER)
    assert st.state["integrity"] == {}, "the repairing row explains the transition"


def test_a_flagged_commit_behind_a_moved_cursor_keeps_its_reason_until_repaired() -> None:
    """The cursor moves at a merge; a bypass flagged before it leaves the range `(cursor, head]` — and is walked
    again from the landed map, so its reason stays until `repair --journal` explains it (the L4 finding)."""
    hz = fresh()
    st = hz.st
    ratified(hz, "a")
    st.land({"run_id": "r-0", "events": []}, LANDER)
    sha = bypass(st, "BOARD.md", st.raw.get("BOARD.md", b"") + b"\nhand-written\n")
    st.land({"run_id": "r-1", "events": []}, LANDER)
    assert st.state["integrity"] == {"BOARD.md": {"unjournaled": [sha]}}
    main = st.repo.head
    assert main is not None
    branch = st.repo.commit({"src/f.py": b"x\n"}, "builder", st.now(), "batch", parents=[main])
    st.repo.head = main  # type: ignore[misc]
    merge = st.repo.commit({"src/f.py": b"x\n"}, "forge", st.now(), "merge", parents=[main, branch])
    r = st.land({"run_id": "r-2", "events": []}, LANDER)
    assert r["cursor"] == merge and sha not in st.repo.first_parent_walk(merge), "the bypass is behind the cursor"
    assert st.state["integrity"] == {"BOARD.md": {"unjournaled": [sha]}}, "still in this land's range"
    # the next land's range is `(merge, head]` — the bypass is outside it and only the flagged re-walk keeps it
    before = st.repo.head
    r = st.land({"run_id": "r-3", "events": [{"kind": "question", "card": 1, "text": "keep going"}]}, LANDER)
    # the range `(merge, head]` is clean — the flagged commit behind it does not hold the cursor [Q-W10 (a)]
    assert r["empty"] is False and st.state["ledger_cursor"] == before != merge
    assert st.state["integrity"] == {"BOARD.md": {"unjournaled": [sha]}}, "the reason survived leaving the range"
    st.repair(OWNER, journal=sha)
    st.land({"run_id": "r-4", "events": []}, LANDER)
    assert st.state["integrity"] == {}


# ---- where the first land starts, and what the walk costs ----------------------------------------------------------


def test_the_first_land_walks_from_inits_commit_not_the_root() -> None:
    """A tenant's first land starts at the parent of the commit that wrote `config.toml` — `init`'s, the first
    journaled act; the seed commit before it is not walked."""
    hz = fresh()
    st = hz.st
    walk = st.repo.first_parent_walk(None)
    init_commit = st.repo.history_of(st.rp("config.toml"), None)[0][0]
    start = st._chain_start()
    assert start == walk[0] and st.repo.parents(init_commit) == [start], "the start is init's parent, the seed"
    assert st.state.get("ledger_cursor") is None
    st.land({"run_id": "r-0", "events": []}, LANDER)
    assert st.state["integrity"] == {}


def test_the_range_walk_is_one_git_however_many_commits_and_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """K7b's rule at land: the walk over `(last cursor, head]` is ONE `log` for the whole range and no `diff-tree`
    per commit, whatever the range holds — three governed cards written, then twenty ungoverned commits."""
    from .conftest import git

    work = _governed_tenant(tmp_path, 3)
    st = store_on_disk(work, tmp_path / "seed.sqlite", root=ROOT)  # the seeding store's journal explains the history
    st.land({"run_id": "r-0", "events": []}, LANDER)
    other = tmp_path / "other"
    git(tmp_path, "clone", "-q", str(tmp_path / "origin.git"), str(other))
    git(other, "config", "user.email", "s@example")
    git(other, "config", "user.name", "s")
    for i in range(20):
        (other / f"notes-{i}.txt").write_bytes(b"ungoverned\n")
        git(other, "add", "-A")
        git(other, "commit", "-q", "-m", f"stranger {i}")
    git(other, "push", "-q", "origin", "HEAD:main")
    st._sync_to_main()  # K9's fast-forward, outside the count: it spends one diff-tree per commit behind (C-8, recorded)
    spawns = Spawns(monkeypatch)
    integrity, acts, clean = st._reconcile_range(st.state["ledger_cursor"])
    assert clean
    assert integrity == {} and acts == []
    assert spawns.of("log") == 1, [a[1:5] for a in spawns.calls if Spawns.verb_of(a) == "log"]
    assert spawns.of("diff-tree") == 0, "the walk spawns a diff-tree per commit"
    r = st.land({"run_id": "r-1", "events": []}, LANDER)
    assert r["empty"] is True and st.state["integrity"] == {}


# ---- the act events (Q-W8) ------------------------------------------------------------------------------------------


def test_a_withdrawal_of_a_dispatched_card_is_the_ledgers_own_transition_once() -> None:
    """03 §6: a `withdrawn` act on a card with a run in flight is the ledger's own `withdrawn` carrying the entry's
    `seq`, ahead of the report's events, at the entry's time; a re-walk of the same range emits it once; the same
    act on a card nothing dispatched transitions nothing and emits nothing."""
    hz = fresh()
    st = hz.st
    a, b = ratified(hz, "a"), ratified(hz, "b")
    st.land({"run_id": "r-0", "events": [{"kind": "dispatched", "card": a, "run_id": "r-0"}]}, LANDER)
    for cid in (a, b):
        st.write_set(cid, ['status="withdrawn"', 'withdrawn_reason="superseded"'], OWNER)
    seq = int(st.docs[path_of(st, a)].history[-1]["seq"])
    r = st.land({"run_id": "r-1", "events": [{"kind": "question", "card": b, "text": "still?"}]}, LANDER)
    lines = parse_jsonl(st.raw["state/history.jsonl"].decode("utf-8"))
    assert r["events"] == ["e2", "e3"] and lines[1]["kind"] == "withdrawn" and lines[1]["card"] == a
    assert lines[1]["seq"] == seq and lines[1]["at"] == st.docs[path_of(st, a)].history[-1]["at"]
    assert lines[2]["kind"] == "question", "the walk's events go ahead of the report's"
    assert not any(e["kind"] == "withdrawn" and e["card"] == b for e in lines), "nothing in flight on b"
    again = st.land({"run_id": "r-2", "events": []}, LANDER)
    assert again["empty"] is True and len(st.events) == 3, "the same range emits nothing twice"
    assert "closed" not in Store.ACT_EVENTS, "a human closure is never emitted (row 5 reads verified=false as disputed)"


# ---- the fold, alone -------------------------------------------------------------------------------------------------


def test_the_fold_lands_the_reasons_by_path_sorted_and_the_ingest_block() -> None:
    s = events_mod.fold(
        [],
        "c",
        "2026-01-01T00:00:00Z",
        {"seq": 1, "h": "h"},
        {},
        integrity={"z": {"unjournaled": ["b", "a"], "tampered": ["a"]}, "a": {"time": []}, "m": {"time": ["c"]}},
        ingest={"run_id": "r", "overflow": 3},
    )
    assert s["schema"] == 2 and list(s["integrity"]) == ["m", "z"], "sorted by path; a path with no commit is out"
    assert s["integrity"]["z"] == {"tampered": ["a"], "unjournaled": ["a", "b"]}, "reason → the commits, sorted"
    assert s["ingest"] == {"run_id": "r", "overflow": 3}
    bare = events_mod.fold([], "c", "2026-01-01T00:00:00Z", {"seq": 1, "h": "h"}, {})
    assert bare["integrity"] == {} and bare["ingest"] == {}


def test_coauthor_trailers_are_read_as_lower_cased_emails() -> None:
    msg = "land\n\nCo-Authored-By: Some One <Some.One@Example>\nco-authored-by: bare@example\nCo-Authored-By:\n"
    assert coauthors_of(msg) == ("some.one@example", "bare@example")
    assert coauthors_of("no trailers") == ()


def test_the_projection_maps_a_landed_path_reason_to_its_card_and_planner_cannot_see_the_walk() -> None:
    """`Store._inputs` keys the landed reasons by card id for row 1; `show Board` reads the same."""
    hz = fresh()
    st = hz.st
    a = ratified(hz, "a")
    p = path_of(st, a)
    st.state = {**st.state, "integrity": {p: {"time": ["abc"]}}}
    assert st.projections()[a].label.reasons == ("time",)
    assert st._inputs().integrity == {a: ("time",)}
    st.state = {**st.state, "integrity": {}}
    assert st._inputs().integrity == {}
    assert PLANNER.grant != "lander"
