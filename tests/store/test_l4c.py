"""L4c (2026-09-10) — two of the owner's rulings on `land`, after the live step on tenant #0.

**Q-W9:** `land` alone passes K4's door when a governed path moved on the remote: it fast-forwards, re-reads the
moved paths, and lands the bypass as its reason at once, where every other door stays `git.push-rejected`.
**Q-W10 (a):** the cursor advances to the head at every land whose range is clean — tenant #0's forge squash-merges,
so no merge commit ever moved it and every land re-walked the whole range since the first — and a land of nothing
after a land of nothing is still the empty diff, or the moved cursor would commit itself forever.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from isidium.store.core.grammar import Document
from isidium.store.core.refusal import Refusal
from isidium.store.server.gitrepo import GitCli, blob_id
from isidium.store.server.store import NewCard, Store

from .conftest import BASE_SCOPE, LANDER, OWNER, PLANNER, base_head, fresh, git, store_on_disk, tenant_checkout
from .test_l4 import bypass, ratified

ROOT = "docs/work/"
NOTHING = {"run_id": "r-nothing", "events": []}


def stranger_pushes(tmp_path: Path, rel: str, body: bytes, name: str = "other") -> str:
    """K9's second writer, with a clone per call so the same path can move twice."""
    work = tmp_path / f"stranger-{name}"
    git(tmp_path, "clone", "-q", str(tmp_path / "origin.git"), str(work))
    git(work, "config", "user.name", "stranger")
    git(work, "config", "user.email", "stranger@example")
    (work / rel).parent.mkdir(parents=True, exist_ok=True)
    (work / rel).write_bytes(body)
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", f"a second writer touched {rel}")
    git(work, "push", "-q", "origin", "HEAD:main")
    return git(tmp_path / "origin.git", "rev-parse", "main").strip()


# ---- Q-W10 (a): the cursor at a clean land ----------------------------------------------------------------------


def test_the_cursor_advances_to_the_head_at_a_land_whose_range_is_clean() -> None:
    """A store commit between two lands (a ratification) is journaled — the range is clean — and the second land
    puts the cursor on the head it walked to, not where the first land left it. The next range is then the land's
    own commit alone: bounded, where before it grew by every commit since the first land."""
    hz = fresh()
    st = hz.st
    ratified(hz, "a")
    first = st.land({"run_id": "r-0", "events": []}, LANDER)
    ratified(hz, "b")
    head = st.repo.head
    r = st.land({"run_id": "r-1", "events": []}, LANDER)
    assert r["empty"] is False, "a new card's history head lands"
    assert r["cursor"] == head != first["cursor"], "the cursor did not advance to the head the walk reached"
    assert st.state["ledger_cursor"] == head
    assert st.repo.first_parent_walk(st.state["ledger_cursor"]) == [r["commit"]], "the next range is not bounded"


def test_a_land_of_nothing_after_a_land_of_nothing_is_the_empty_diff_and_the_cursor_does_not_drift() -> None:
    """The cursor would advance over the previous land's own commit — a clean range — and, were that alone a
    diff, every land of nothing would commit the moved cursor and the next land the moved cursor again. It is
    bookkeeping: nothing is written, the head stays, and the third land says the same."""
    hz = fresh()
    st = hz.st
    ratified(hz, "a")
    st.land({"run_id": "r-0", "events": []}, LANDER)
    head, cursor = st.repo.head, st.state["ledger_cursor"]
    for n in range(3):
        r = st.land({"run_id": f"r-{n + 1}", "events": []}, LANDER)
        assert r["empty"] is True, f"land {n + 1} of nothing wrote"
        assert st.repo.head == head and st.state["ledger_cursor"] == cursor, "the cursor drifted"


def test_a_flagged_commit_in_the_range_holds_the_cursor_until_it_is_repaired() -> None:
    """The ruling's other half: a range that is not clean keeps the cursor where the last land left it, so the
    flagged commit stays in the range; the owner's repair explains it, and the next land advances. The board is
    the path, as in L4's repair test: a card hand-edited without an entry stays `tampered` past a journal repair."""
    hz = fresh()
    st = hz.st
    ratified(hz, "a")
    st.land({"run_id": "r-0", "events": []}, LANDER)
    cursor = st.state["ledger_cursor"]
    sha = bypass(st, "BOARD.md", st.raw.get("BOARD.md", b"") + b"\nhand-written\n")
    r = st.land({"run_id": "r-1", "events": []}, LANDER)
    assert r["empty"] is False and r["cursor"] == cursor != st.repo.head, "an unclean range moved the cursor"
    assert sha in st.repo.first_parent_walk(st.state["ledger_cursor"]), "the flagged commit left the range"
    st.repair(OWNER, journal=sha)
    head = st.repo.head
    r = st.land({"run_id": "r-2", "events": []}, LANDER)
    assert st.state["integrity"] == {} and r["cursor"] == head, "the repaired range did not advance the cursor"


def test_a_pending_merge_is_the_cursor_over_a_clean_head_and_lands_by_itself() -> None:
    """Pin 3 first: when a merge commit exists on the first-parent line it is the cursor, ahead of the clean-range
    rule, and a land with nothing else is not empty — the merge is what X2's land is for."""
    hz = fresh()
    st = hz.st
    ratified(hz, "a")
    st.land({"run_id": "r-0", "events": []}, LANDER)
    main = st.repo.head
    assert main is not None
    branch = st.repo.commit({"src/f.py": b"x\n"}, "builder", st.now(), "batch", parents=[main])
    st.repo.head = main  # type: ignore[misc]
    merge = st.repo.commit({"src/f.py": b"x\n"}, "forge", st.now(), "merge", parents=[main, branch])
    r = st.land(NOTHING, LANDER)
    assert r["empty"] is False and r["cursor"] == merge == st.state["ledger_cursor"]
    assert st.land(NOTHING, LANDER)["empty"] is True, "the landed merge is the empty diff again"


# ---- Q-W9: `land` alone passes K4's door ----------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path: Path) -> Store:
    tenant_checkout(tmp_path)
    st = store_on_disk(tmp_path / "tenant", tmp_path / "journal.sqlite", root=ROOT)
    st.init(OWNER, software_key_ack="ok for L4c", root=ROOT)
    return st


def draft(st: Store, slug: str) -> str:
    r = st.write(NewCard(slug), Document(base_head(0, "draft"), {"Scope": BASE_SCOPE}), None, None, PLANNER)
    return r.commit


def test_land_alone_passes_the_door_when_a_governed_path_moved_and_lands_the_bypass_at_once(
    store: Store, tmp_path: Path
) -> None:
    """A stranger hand-edits a card on `main` behind the store. `land` is not refused: it fast-forwards onto the
    stranger's tip, re-reads the card, and the landed map names the stranger's commit at the card's path; the
    store's commit sits on the stranger's, and the store holds the stranger's bytes. Then the same bypass again,
    and the planner's `write` is still `git.push-rejected` — the door opened for `land` alone."""
    repo = store.repo
    assert isinstance(repo, GitCli)
    draft(store, "hand-edited-later")
    p = next(iter(store.docs))
    edited = store.raw[p].replace(b"## Scope\n", b"## Scope\n\nA line written by hand, outside the store.\n", 1)
    assert edited != store.raw[p]
    tip = stranger_pushes(tmp_path, f"{ROOT}{p}", edited, "first")
    assert repo.head != tip, "the fixture's premise: the running store has not seen the bypass"

    r = store.land({"run_id": "r-0", "events": []}, LANDER)

    assert r["landed"] is True and r["empty"] is False
    assert repo.parents(r["commit"]) == [tip], "the land was not built on the stranger's tip"
    assert git(tmp_path / "origin.git", "rev-parse", "main").strip() == r["commit"], "the land did not push"
    assert store.raw[p] == edited, "the store still holds the blob it remembered"
    assert store.state["integrity"].get(p, {}).get("unjournaled") == [tip], store.state["integrity"]

    again = stranger_pushes(tmp_path, f"{ROOT}{p}", edited.replace(b"hand,", b"hand, again,", 1), "second")
    before = repo.head
    with pytest.raises(Refusal) as ei:
        draft(store, "against-a-bypass")
    assert ei.value.rule == "git.push-rejected"
    assert repo.head == before and git(tmp_path / "origin.git", "rev-parse", "main").strip() == again


def test_the_row_land_journals_names_the_blob_main_holds_not_the_one_the_store_remembered(
    store: Store, tmp_path: Path
) -> None:
    """The L4 finding behind Q-W9: a bypass to a sidecar path, then `land` — its journal row's `before_blob` for
    `state.json` is the stranger's blob, because the door re-read it; the remembered one would have been wrong."""
    repo = store.repo
    assert isinstance(repo, GitCli)
    draft(store, "a")
    store.land({"run_id": "r-0", "events": []}, LANDER)
    remembered = blob_id(store.raw["state.json"], repo.object_format)
    planted = store.raw["state.json"].replace(b'"schema": 2', b'"schema": 2, "planted": true', 1)
    assert planted != store.raw["state.json"]
    tip = stranger_pushes(tmp_path, f"{ROOT}state.json", planted)

    r = store.land({"run_id": "r-1", "events": []}, LANDER)

    assert r["empty"] is False
    rows = store.journal.rows_for("state.json")
    prow = rows[-1]["paths"][0]
    assert prow["before_blob"] == blob_id(planted, repo.object_format) != remembered, prow
    assert tip in store.state["integrity"].get("state.json", {}).get("unjournaled", []), store.state["integrity"]


def test_a_moved_config_is_the_refusal_at_land_too(store: Store, tmp_path: Path) -> None:
    """The one path `land` does not re-read past: a hand-edited manifest is a hand-edited policy."""
    repo = store.repo
    assert isinstance(repo, GitCli)
    before = repo.head
    stranger_pushes(tmp_path, f"{ROOT}config.toml", store.raw["config.toml"] + b"\n# hand-written\n")
    with pytest.raises(Refusal) as ei:
        store.land({"run_id": "r-0", "events": []}, LANDER)
    assert ei.value.rule == "git.push-rejected" and repo.head == before


def test_a_governed_path_deleted_on_main_is_forgotten_by_the_re_read(store: Store, tmp_path: Path) -> None:
    """A card removed behind the store: after `land`, the store no longer projects it, and the walk landed the
    deletion at its path."""
    repo = store.repo
    assert isinstance(repo, GitCli)
    draft(store, "deleted-later")
    p = next(iter(store.docs))
    cid = int(store.docs[p].head["id"])
    work = tmp_path / "deleter"
    git(tmp_path, "clone", "-q", str(tmp_path / "origin.git"), str(work))
    git(work, "config", "user.name", "stranger")
    git(work, "config", "user.email", "stranger@example")
    git(work, "rm", "-q", f"{ROOT}{p}")
    git(work, "commit", "-q", "-m", "a second writer removed a card")
    git(work, "push", "-q", "origin", "HEAD:main")
    tip = git(tmp_path / "origin.git", "rev-parse", "main").strip()

    r = store.land({"run_id": "r-0", "events": []}, LANDER)

    assert r["landed"] is True and repo.parents(r["commit"]) == [tip]
    assert p not in store.docs and store.path_of(cid) is None and p not in store.raw
    assert tip in {sha for by in store.state["integrity"].get(p, {}).values() for sha in by}, store.state["integrity"]
