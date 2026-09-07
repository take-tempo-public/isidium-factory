"""K7b — the efficiency shapes and the counters from the K7 review (F7, F8, F9, F27, F12, F13, F14, F16), and the
code the five rulings of 2026-09-06 call for (Q15 the worker thread; Q16 the root refused; Q17 both doors burn;
Q18 `landed`; Q19 the registration is the line).

Every efficiency test here asserts a **count of the mechanism** — git processes spawned, regex passes made, labels
computed — never a clock: a clock proves the workstation was fast, a count proves the shape. Every counter test
reads the in-memory reader as a difference across the thing under test. The listener tests drive the real edge from
`test_edge.py`'s fixtures, on a real socket, because Q15 is about what the loop does while a call runs.
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import json
import re
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
import typer
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from isidium.store.client import cli as cli_mod
from isidium.store.client import locus
from isidium.store.client.mcp import McpServer
from isidium.store.core import refs as refs_mod
from isidium.store.core import status as status_mod
from isidium.store.core import telemetry
from isidium.store.core.grammar import Document
from isidium.store.core.refusal import Refusal, ValidationRefusal
from isidium.store.registry import config as cfg
from isidium.store.registry.loader import Registry
from isidium.store.server import gitrepo
from isidium.store.server.api import Api
from isidium.store.server.gitrepo import GitCli, MemGit
from isidium.store.server.http import Limits, Worker
from isidium.store.server.journal import Journal
from isidium.store.server.service import Registration, Request, Service
from isidium.store.server.store import NewCard, Store, WriteRequest

from .conftest import (
    BASE_SCOPE,
    OWNER,
    PLANNER,
    Harness,
    Telemetry,
    base_head,
    fresh,
    git,
    store_on_disk,
    tenant_checkout,
)
from .test_apply import CODE, NOTES
from .test_edge import (
    Edge,
    against,
    attempt,
    client_context,
    edge,  # noqa: F401  (the module-scoped listener fixture, by the name pytest registered)
    hold,
    payload,
    raw,
    status_of,
)
from .test_service import CLOCK, OWNER_CERT
from .test_telemetry import call as service_call

ROOT = "docs/work/"


def refuses(rule: str, fn: Callable[[], Any]) -> Refusal:
    with pytest.raises(Refusal) as ei:
        fn()
    assert ei.value.rule == rule, str(ei.value)
    return ei.value


def verdicts_of(r: Refusal) -> list[tuple[str, str]]:
    assert isinstance(r, ValidationRefusal), r
    return [(v.rule, v.path) for v in r.verdicts]


class Spawns:
    """Every git process `gitrepo` starts, by its first argument — the discriminator for F7 and F8. `subprocess.run`
    is wrapped at the module `gitrepo` reads it from; the batch reader (`Popen`) is not a per-call spawn and is not
    counted."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.calls: list[list[str]] = []
        original = subprocess.run

        def counted(args: Any, *a: Any, **k: Any) -> Any:
            self.calls.append([str(x) for x in args])
            return original(args, *a, **k)

        monkeypatch.setattr("isidium.store.server.gitrepo.subprocess.run", counted)

    def of(self, verb: str) -> int:
        return sum(1 for argv in self.calls if verb in argv[1:6])

    def reset(self) -> None:
        self.calls.clear()


# ---- F27: one pass per file, however many refs cite it -------------------------------------------------------------


class CountingPattern:
    """A regex whose `match` counts — the number of lines scanned is the discriminator, not the clock."""

    def __init__(self, pattern: re.Pattern[str]) -> None:
        self.pattern, self.calls = pattern, 0

    def match(self, s: str) -> re.Match[str] | None:
        self.calls += 1
        return self.pattern.match(s)


def test_n_refs_into_one_file_scan_it_once_and_a_range_ref_never_scans(monkeypatch: pytest.MonkeyPatch) -> None:
    """Six symbol refs and three anchor refs into one file cost one symbol pass and one heading pass over its lines;
    a file cited by line ranges alone is never scanned at all — the index is built on first use (C-13, judged).
    The verdicts are the same ones the per-ref scan gave, on the same fixture, including `ref.ambiguous`."""
    symbol = CountingPattern(refs_mod._SYMBOL_DEF)
    heading = CountingPattern(refs_mod._HEADING)
    monkeypatch.setattr(refs_mod, "_SYMBOL_DEF", symbol)
    monkeypatch.setattr(refs_mod, "_HEADING", heading)
    text = CODE + b"\n" + NOTES + b"\n" + b"x = 1\n" * 40
    lines = text.decode().split("\n")
    lc = refs_mod.Locus(text)
    refs = [
        "f::resolve_me",
        "f::Twice",
        "f::absent",
        "f::x",
        "f::resolve_me",
        "f::Twice",
        "f#the-anchor-here",
        "f#title",
        "f#missing",
    ]
    verdicts = [refs_mod.locus_check(refs_mod.Ref.parse(r), lc) for r in refs]
    assert verdicts == [
        None,
        "ref.ambiguous",
        "ref.unresolved",
        "ref.ambiguous",
        None,
        "ref.ambiguous",
        None,
        None,
        "ref.unresolved",
    ]
    assert symbol.calls == len(lines), "the symbol pass ran more than once for one file"
    assert heading.calls == len(lines), "the heading pass ran more than once for one file"
    # a range ref never asks for either index
    ranged = refs_mod.Locus(text)
    assert refs_mod.locus_check(refs_mod.Ref.parse(f"f:1-{len(lines)}"), ranged) is None
    assert refs_mod.locus_check(refs_mod.Ref.parse(f"f:1-{len(lines) + 1}"), ranged) == "ref.unresolved"
    assert (symbol.calls, heading.calls) == (len(lines), len(lines)), "a line-range ref scanned the file"


def test_the_door_builds_one_locus_per_path_per_call(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`client/locus.py` reads each cited file once and indexes it once, however many refs cite it — the same count,
    at the door, on the working tree."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src/thing.py").write_bytes(CODE)
    built: list[bytes] = []
    real = refs_mod.Locus

    class Counting(real):  # type: ignore[misc,valid-type]
        def __init__(self, data: bytes) -> None:
            built.append(data)
            super().__init__(data)

    monkeypatch.setattr(refs_mod, "Locus", Counting)
    rs, checked = locus.verdicts(["src/thing.py::resolve_me", "src/thing.py::Twice", "src/thing.py:1-2"], tmp_path)
    assert checked == 3 and [r.rule for r in rs] == ["ref.ambiguous"]
    assert built == [CODE], "the door decoded or indexed the file more than once"


# ---- F9: one card's projection in one card's time -------------------------------------------------------------------


def _family(hz: Harness) -> dict[str, int]:
    """A ratified epic with two members, a card blocked on one of them, and a held card — every input a label
    reads. The epic is ratified because a draft container never rolls up (1.5)."""
    st = hz.st
    epic = hz.draft("epic-parent", kind="epic")
    st.ratify([epic], OWNER)
    a = hz.draft("member-a", parent=epic)
    b = hz.draft("member-b", parent=epic)
    st.ratify([b], OWNER)
    blocked = hz.draft("blocked-on-a", depends_on=[a])
    held = hz.draft("held-one")
    st.write_set(held, ['hold.kind="blocked"', "hold.on.owner=true"], PLANNER)
    return {"epic": epic, "a": a, "b": b, "blocked": blocked, "held": held}


def test_project_one_agrees_with_project_on_every_card_and_reads_only_its_neighbours(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same eleven rows from the same inputs, card by card — and the discriminator: `_core_label` runs for the
    card, the cards it depends on and its members, never for the set. The container's roll-up is included: the
    parent whose members are all terminal reads `closed` through both functions."""
    hz = fresh("f9")
    st = hz.st
    ids = _family(hz)
    inp = st._inputs()
    whole = status_mod.project(inp)
    for cid in inp.cards:
        assert status_mod.project_one(inp, cid) == whole[cid], cid
    # close both members so the parent rolls up, and check the two agree on that too
    for m in ("a", "b"):
        st.write_set(ids[m], ['status="withdrawn"', 'withdrawn_reason="superseded"'], OWNER)
    inp = st._inputs()
    whole = status_mod.project(inp)
    assert whole[ids["epic"]].label.row == "closed", whole[ids["epic"]]
    assert status_mod.project_one(inp, ids["epic"]) == whole[ids["epic"]]

    counted: list[int] = []
    real = status_mod._core_label

    def counting(cid: int, doc: Document, inputs: Any) -> Any:
        counted.append(cid)
        return real(cid, doc, inputs)

    monkeypatch.setattr(status_mod, "_core_label", counting)
    status_mod.project_one(inp, ids["blocked"])
    assert sorted(counted) == sorted([ids["blocked"], ids["a"]]), counted  # itself and what it depends on
    counted.clear()
    status_mod.project_one(inp, ids["held"])
    assert counted == [ids["held"]]
    counted.clear()
    status_mod.project_one(inp, ids["epic"])
    assert sorted(counted) == sorted([ids["epic"], ids["a"], ids["b"]])  # itself and its members
    with pytest.raises(KeyError):
        status_mod.project_one(inp, 9999)


def test_show_card_costs_one_card_however_many_cards_the_tenant_holds(monkeypatch: pytest.MonkeyPatch) -> None:
    """`Api.show(card)` at 10 and at 60 cards: the number of labels computed does not grow with the set, and the
    label is the one `project` would have rendered."""
    hz = fresh("f9-scale")
    api = Api(hz.st)
    counted: list[int] = []
    real = status_mod._core_label

    def counting(cid: int, doc: Document, inputs: Any) -> Any:
        counted.append(cid)
        return real(cid, doc, inputs)

    monkeypatch.setattr(status_mod, "_core_label", counting)
    sizes: dict[int, int] = {}
    for target in (10, 60):
        while len(hz.st.cards()) < target:
            hz.draft(f"filler-{len(hz.st.cards())}")
        first = min(hz.st.cards())
        counted.clear()
        shown = api.show(PLANNER, {"target": "card", "id": first})
        sizes[target] = len(counted)
        assert shown["label"] == hz.st.projections()[first].render()
    assert sizes == {10: 1, 60: 1}, sizes


def test_the_members_index_follows_a_reparenting_write() -> None:
    """The store keeps parent → members as documents are indexed, and a write that moves a card's `parent` moves it
    in the index — the roll-up reads the index, so a stale one would roll up the wrong members."""
    hz = fresh("f9-kids")
    st = hz.st
    p1, p2 = hz.draft("parent-one", kind="epic"), hz.draft("parent-two", kind="epic")
    kid = hz.draft("kid", parent=p1)
    assert st._kids == {p1: {kid}}
    st.write_set(kid, [f"parent={p2}"], PLANNER)
    assert st._kids == {p1: set(), p2: {kid}}
    st.write_set(kid, ["parent="], PLANNER)
    assert st._kids == {p1: set(), p2: set()}
    inp = st._inputs()
    assert inp.kids is st._kids


# ---- F7: one round trip for every governed blob at load; F8: one git for a card's history ---------------------------


def _governed_tenant(tmp_path: Path, cards: int) -> Path:
    work = tenant_checkout(tmp_path)
    (work / ROOT / "cards").mkdir(parents=True)
    st = store_on_disk(work, tmp_path / "seed.sqlite", root=ROOT)
    st.init(OWNER, software_key_ack="ok for K7b", root=ROOT)
    for i in range(cards):
        st.write(NewCard(f"card-{i}"), Document(base_head(0, "draft"), {"Scope": BASE_SCOPE}), None, None, PLANNER)
    assert isinstance(st.repo, GitCli)
    st.repo.close()
    return work


def test_a_fresh_store_hydrates_its_governed_set_in_one_fetch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Seven governed documents on a fresh filtered clone: **one** `fetch` process, zero per-object `cat-file -e`,
    every document readable afterwards, and the code blob still absent — the footprint held through the batch. A
    second store over a warm clone fetches nothing at all."""
    work = _governed_tenant(tmp_path, 6)
    spawns = Spawns(monkeypatch)
    st = store_on_disk(work, tmp_path / "j1.sqlite", root=ROOT)
    assert len(st.cards()) == 6 and st.config_tree, "the governed set did not load"
    assert spawns.of("fetch") == 1, [a[1:4] for a in spawns.calls if "fetch" in a]
    assert not any("cat-file" in a and "-e" in a for a in spawns.calls), "an object was hydrated one at a time"
    repo = st.repo
    assert isinstance(repo, GitCli)
    code = repo.oid_of("client/cards/validator.py")
    assert code is not None
    with pytest.raises(Refusal) as ei:
        repo.blob(code)
    assert ei.value.rule == "git.outside-footprint", "the batch pulled a blob outside the governed set"
    # warm: the same clone, a second load, nothing to fetch
    spawns.reset()
    again = Store(
        st.tenant,
        GitCli(repo.gitdir, "isidium-store", "store@sartor", root=ROOT),
        st.journal,
        Registry.shipped(),
        st.clock,
        st.signer,
        root=ROOT,
    )
    assert len(again.cards()) == 6 and spawns.of("fetch") == 0


def test_prefetch_refuses_an_object_it_did_not_vouch(tmp_path: Path) -> None:
    """The batch door keeps `blob()`'s gate: an oid resolved from outside the root is refused before any git runs,
    and nothing else in the batch is fetched on its account."""
    work = _governed_tenant(tmp_path, 1)
    st = store_on_disk(work, tmp_path / "j.sqlite", root=ROOT)
    repo = st.repo
    assert isinstance(repo, GitCli)
    code = repo.oid_of("client/cards/validator.py")
    assert code is not None
    refuses("git.outside-footprint", lambda: repo.prefetch([code]))
    assert repo.prefetch([]) == 0


def test_check_spawns_the_same_number_of_gits_whatever_the_history_length(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`check(card)` over a 3-commit history and over a 20-commit history: the same spawn count. The history is
    grown by a stranger's ungoverned commits on `main`, which the store fast-forwards over on its next write — the
    shape the report measured as 4 and 25 processes."""
    work = _governed_tenant(tmp_path, 1)
    st = store_on_disk(
        work, tmp_path / "seed.sqlite", root=ROOT
    )  # the seeding store's journal: it explains the history
    cid = min(st.cards())
    spawns = Spawns(monkeypatch)

    def grow(n: int, priority: str) -> None:
        other = tmp_path / f"other-{n}"
        git(tmp_path, "clone", "-q", str(tmp_path / "origin.git"), str(other))
        git(other, "config", "user.email", "s@example")
        git(other, "config", "user.name", "s")
        for i in range(n):
            (other / f"notes-{n}-{i}.txt").write_bytes(b"ungoverned\n")
            git(other, "add", "-A")
            git(other, "commit", "-q", "-m", f"stranger {i}")
        git(other, "push", "-q", "origin", "HEAD:main")
        # a write fast-forwards the store over them and lands one more governed commit
        path = st.path_of(cid)
        assert path is not None
        doc = Document(dict(st.docs[path].head), dict(st.docs[path].sections))
        doc.head["priority"] = priority
        st.write(path, doc, st.docs[path].head_of(), None, PLANNER)

    grow(2, "P2")
    spawns.reset()
    assert st.check(cid)["integrity"] == []
    short = len(spawns.calls)
    grow(17, "P3")
    assert len(st.repo.first_parent_walk(None)) >= 20
    spawns.reset()
    assert st.check(cid)["integrity"] == []
    long_ = len(spawns.calls)
    assert short == long_, (short, long_, [a[1:4] for a in spawns.calls])
    assert not any("diff-tree" in a for a in spawns.calls), "the walk still spawns a diff-tree per commit"


def test_history_of_matches_the_per_commit_walk_on_both_repos(tmp_path: Path) -> None:
    """`history_of` on the double and on real git answer what `touched()` per commit answered — the same commits,
    the same blob pairs — including a card renamed away, which is a deletion at its path (K7a, F1), and a
    `since` cursor that excludes what came before it."""
    mem = MemGit()
    seed = mem.commit({"docs/work/cards/0001-a.md": b"a1\n", "src/x.py": b"x\n"}, "s", "2026-09-06T00:00:00Z", "seed")
    second = mem.commit({"docs/work/cards/0001-a.md": b"a2\n"}, "s", "2026-09-06T00:00:01Z", "edit")
    mem.commit({"src/x.py": b"y\n"}, "s", "2026-09-06T00:00:02Z", "code only")
    third = mem.commit(
        {"docs/work/cards/0001-a.md": None, "docs/work/cards/0001-b.md": b"a2\n"}, "s", "2026-09-06T00:00:03Z", "mv"
    )
    expect = [(sha, mem.touched(sha)["docs/work/cards/0001-a.md"]) for sha in (seed, second, third)]
    assert mem.history_of("docs/work/cards/0001-a.md", None) == [(s, b, a) for s, (b, a) in expect]
    assert mem.history_of("docs/work/cards/0001-a.md", seed) == [(s, b, a) for s, (b, a) in expect[1:]]
    assert mem.history_of("src/x.py", None)[-1][2] == gitrepo.blob_id(b"y\n")
    assert mem.merges_since(None) == []

    work = tenant_checkout(tmp_path)
    (work / ROOT / "cards").mkdir(parents=True)
    card = work / ROOT / "cards/0001-a.md"
    card.write_bytes(b"a1\n")
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "card")
    card.write_bytes(b"a2\n")
    git(work, "commit", "-q", "-am", "edit")
    (work / "notes.txt").write_bytes(b"n\n")
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "ungoverned")
    git(work, "mv", str(card), str(work / ROOT / "cards/0001-b.md"))
    git(work, "commit", "-q", "-m", "mv")
    git(work, "checkout", "-q", "-b", "side")
    (work / "side.txt").write_bytes(b"s\n")
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "side")
    git(work, "checkout", "-q", "main")
    git(work, "merge", "-q", "--no-ff", "-m", "merge side", "side")
    git(work, "push", "-q", "origin", "HEAD:main")
    repo = GitCli.clone(tmp_path / "origin.git", tmp_path / "hist.git", "s", "s@t", root=ROOT)
    rel = f"{ROOT}cards/0001-a.md"
    walk = [(sha, repo.touched(sha)[rel]) for sha in repo.first_parent_walk(None) if rel in repo.touched(sha)]
    assert [(s, b, a) for s, (b, a) in walk] == repo.history_of(rel, None) and len(walk) == 3
    assert repo.history_of(rel, None)[-1][2] is None, "the rename away did not read as a deletion at the path"
    assert repo.history_of(rel, walk[0][0]) == repo.history_of(rel, None)[1:]
    merges = repo.merges_since(None)
    assert len(merges) == 1 and len(repo.parents(merges[0])) == 2
    assert repo.merges_since(merges[0]) == []
    # the blobs it names are vouched: `check` reads them through `blob()`, and a restarted store must reconcile
    fresh_clone = GitCli.clone(tmp_path / "origin.git", tmp_path / "hist2.git", "s", "s@t", root=ROOT)
    first_after = fresh_clone.history_of(rel, None)[0][2]
    assert first_after is not None and first_after in fresh_clone._vouched
    assert fresh_clone.blob(first_after) == b"a1\n"


# ---- F12: a malformed body is the caller's, and it is told so ----------------------------------------------------------


@pytest.fixture(scope="module")
def svc() -> tuple[Service, Harness]:
    hz = fresh("k7b-svc")
    registration = Registration(
        {
            "CN=owner@example": ("amodal1@example", "owner"),
            "CN=sartor-planner@agents.example": ("sartor-planner@agents.example", "contributor"),
        },
        CLOCK,
    )
    return Service(Api(hz.st), registration, hz.st.tenant), hz


BODIES: list[tuple[str, dict[str, Any], str]] = [
    ("ratify", {"writes": "abc"}, "writes"),
    ("ratify", {"writes": [1]}, "writes"),
    ("ratify", {"ids": "12", "dry_run": True}, "ids"),
    ("ratify", {"ids": [True]}, "ids"),
    ("ratify", {"dry_run": "yes"}, "dry_run"),
    ("suggest", {"kind": "docs", "title": "t", "body": "b", "refs": "ab"}, "refs"),
    ("suggest", {"kind": 7, "title": "t", "body": "b"}, "kind"),
    ("write", {"document": "not a table"}, "document"),
    ("write", {"card": "1", "document": {}}, "card"),
    ("write", {"new_slug": "s", "document": {"head": []}}, "head"),
    ("show", {"target": "card", "id": "1"}, "id"),
    ("check", {"id": 1.5}, "id"),
    ("repair", {"journal": 12}, "journal"),
    ("init", {"extra": []}, "extra"),
]


@pytest.mark.parametrize(("name", "body", "key"), BODIES, ids=[f"{n}:{k}" for n, _b, k in BODIES])
def test_a_wrong_argument_type_is_service_arguments_on_its_key(
    svc: tuple[Service, Harness], caplog: pytest.LogCaptureFixture, name: str, body: dict[str, Any], key: str
) -> None:
    """Every body in the report's table, and more: 400 `service.arguments` naming the key, full disclosure (it is
    about their request), and **no `service.internal` in the record** — the bug arm never fires for data."""
    service, _hz = svc
    with caplog.at_level("WARNING", logger=telemetry.SCOPE):
        status, answer = service_call(service, name, body, OWNER_CERT)
    assert (status, answer["rule"], answer["path"]) == (400, "service.arguments", key), answer
    assert "service.internal" not in "\n".join(r.getMessage() for r in caplog.records)


def test_ids_as_a_string_ratifies_nothing_and_a_nested_body_is_the_callers(
    svc: tuple[Service, Harness], caplog: pytest.LogCaptureFixture
) -> None:
    """The two shapes the report reproduced by name: `"ids": "12"` used to ratify cards 1 and 2; a body nested past
    the parser's depth used to be `service.internal` with Python's words in the record."""
    service, hz = svc
    hz.draft("one")
    hz.draft("two")
    status, answer = service_call(service, "ratify", {"ids": "12", "dry_run": True}, OWNER_CERT)
    assert status == 400 and answer["rule"] == "service.arguments"
    nested = ("[" * 50_000 + "]" * 50_000).encode()
    with caplog.at_level("WARNING", logger=telemetry.SCOPE):
        response = service.handle(Request("POST", "/call/show", nested), service.registration.credential(OWNER_CERT))
    assert (response.status, json.loads(response.body)["rule"]) == (400, "service.arguments")
    records = "\n".join(r.getMessage() for r in caplog.records)
    assert "RecursionError" in records and "service.internal" not in records


# ---- F13: the inbox record against its own schema ----------------------------------------------------------------------


def test_an_inbox_record_is_checked_against_inbox1s_rows() -> None:
    """`kind` is the enum the schema declares; `refs` is a list of strings; a key the schema does not name is
    refused; and the 900 KB the review put through `kind` is refused on the enum before it is hashed or committed.
    The old ids stay where the scenarios pin them (`inbox.bound` on the prose, in bytes)."""
    hz = fresh("f13")
    st = hz.st
    mem = st.repo
    assert isinstance(mem, MemGit)
    pushed = mem.pushed
    r = refuses("validate.failed", lambda: st.suggest(PLANNER, "x" * 900_000, "t", "b", source="session"))
    assert verdicts_of(r) == [("record.enum", "kind")] and len(r.detail) < 400, "the 900 KB came back in the detail"
    r = refuses("validate.failed", lambda: st.suggest(PLANNER, "wish", "t", "b", source="session"))
    assert verdicts_of(r) == [("record.enum", "kind")]
    intake: dict[str, Any] = {"type": "intake", "source": "session", "kind": "docs", "title": "t", "body": "b"}
    r = refuses("validate.failed", lambda: st.write("suggestions.jsonl", intake | {"refs": [1]}, None, None, PLANNER))
    assert verdicts_of(r) == [("record.type", "refs[0]")]
    r = refuses("validate.failed", lambda: st.write("suggestions.jsonl", intake | {"shoes": 2}, None, None, PLANNER))
    assert verdicts_of(r) == [("record.unknown-key", "shoes")]
    r = refuses(
        "validate.failed", lambda: st.write("suggestions.jsonl", intake | {"proposed_for": 0}, None, None, PLANNER)
    )
    assert verdicts_of(r) == [("record.range", "proposed_for")]
    assert mem.pushed == pushed, "a refused record reached the repository"
    refuses("inbox.bound", lambda: st.suggest(PLANNER, "docs", "x" * 121, "b", source="session"))
    ok = st.suggest(PLANNER, "docs", "a title", "a body", ["src/x.py"], source="session")
    assert ok.entry["kind"] == "docs" and ok.landed is True
    # the pass itself, on strings: a `range` bounds the length in code points, which `config@*` never uses
    inbox = Registry.shipped().get("inbox@1")
    assert [(v.rule, v.path) for v in cfg.check_record({"reason": "r" * 501}, inbox)] == [("record.range", "reason")]
    assert cfg.check_record({"reason": "r" * 500, "outcome": "declined"}, inbox) == []


# ---- F14: the CLI's refusals move the counter ---------------------------------------------------------------------------


class Refusing:
    def __init__(self, rule: str) -> None:
        self.rule = rule

    def call(self, name: str, args: Any) -> Any:
        raise Refusal(self.rule, "somewhere", "the words")


@pytest.fixture
def client_here(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from isidium.store.client.install import install

    from .test_walk import client_cfg

    work = tenant_checkout(tmp_path)
    install(work, client_cfg(ROOT))
    monkeypatch.chdir(work)
    return work


def test_every_cli_refusal_site_moves_the_counter_once_and_prints_the_words(
    client_here: Path, otel: Telemetry, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Four sites (`_run`, `init`, `show`, `check`) and the pre-flight: each refusal counts once on
    `isidium.store.refusal` by rule id, and the human still gets every word — including a terse id's, which
    `payload()` would have relocated into a second line on the same terminal."""
    monkeypatch.setattr(cli_mod, "Transport", lambda _cfg, _workdir: Refusing("git.failed"))
    before = otel.count("isidium.store.refusal", **{telemetry.RULE: "git.failed"})
    with pytest.raises(typer.Exit) as ex:
        cli_mod._run("show", {"target": "queue"})
    assert ex.value.exit_code == 2
    with pytest.raises(typer.Exit):
        cli_mod.show(target="queue")
    with pytest.raises(typer.Exit):
        cli_mod.check(id=1)
    assert otel.count("isidium.store.refusal", **{telemetry.RULE: "git.failed"}) == before + 3
    err = capsys.readouterr().err
    assert err.count("git.failed @ somewhere: the words") == 3 and "withheld" not in err

    # `init`'s own site
    def refusing_init(*_a: Any, **_k: Any) -> Any:
        raise Refusal("init.exists", "config.toml")

    monkeypatch.setattr("isidium.store.client.install.init", refusing_init)
    with pytest.raises(typer.Exit):
        cli_mod.init(tenant="t", address="https://x", ca="ca", cert="c", key="k")
    assert otel.count("isidium.store.refusal", **{telemetry.RULE: "init.exists"}) >= 1
    # the pre-flight: refused at the door, counted at the door, the inner span keeps its own status
    from .test_k4b import document

    otel.clear()
    before = otel.count("isidium.store.refusal", **{telemetry.RULE: "validate.failed"})
    doc = client_here / "one.json"
    doc.write_text(json.dumps(document(["src/thing.py::nope"])), encoding="utf-8")
    (client_here / "src").mkdir()
    (client_here / "src/thing.py").write_bytes(CODE)
    with pytest.raises(typer.Exit):
        cli_mod.write(new="one", document=doc)
    assert otel.count("isidium.store.refusal", **{telemetry.RULE: "validate.failed"}) == before + 1
    assert [s.status.status_code.name for s in otel.spans(locus.PREFLIGHT_SPAN)] == ["ERROR"]
    # and the MCP door, unchanged: once
    before = otel.count("isidium.store.refusal", **{telemetry.RULE: "git.failed"})
    McpServer(Refusing("git.failed"), client_here, ROOT).handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "show", "arguments": {"target": "queue"}},
        }
    )
    assert otel.count("isidium.store.refusal", **{telemetry.RULE: "git.failed"}) == before + 1


# ---- F16: an admission refusal is one event, counted once ---------------------------------------------------------------


def test_a_per_peer_refusal_is_counted_on_its_bound_and_not_as_a_call(edge: Edge, otel: Telemetry) -> None:  # noqa: F811
    async def scenario(port: int) -> bytes | None:
        context = client_context(edge.ca, edge.owner)
        held = [await hold(port, context)]
        await asyncio.sleep(0.25)
        refused = await attempt(port, context, raw("GET", "/health"))
        for _r, w in held:
            w.close()
        return refused

    bound_before = otel.count("isidium.store.connection.refused", **{telemetry.REASON: "per-peer"})
    call_before = otel.count("isidium.store.refusal", **{telemetry.RULE: "service.too-many-connections"})
    refused = against(edge, scenario, Limits(max_connections=8, max_per_caller=1, read_timeout=30.0))
    assert status_of(refused) == 429 and payload(refused)["rule"] == "service.too-many-connections"
    assert otel.count("isidium.store.connection.refused", **{telemetry.REASON: "per-peer"}) == bound_before + 1
    assert otel.count("isidium.store.refusal", **{telemetry.RULE: "service.too-many-connections"}) == call_before, (
        "one admission refusal was counted twice"
    )


# ---- Q15: the loop is free while a call runs; the calls themselves stay one at a time ------------------------------------


@dataclass
class SlowShow:
    """`show` sleeps for `delay` on whatever thread runs it, and records that thread's name."""

    delay: float = 0.0
    threads: list[str] = field(default_factory=list)


@pytest.fixture
def slow_show(monkeypatch: pytest.MonkeyPatch) -> SlowShow:
    slow = SlowShow()

    def show(_self: Api, _caller: Any, _args: Any) -> dict[str, Any]:
        slow.threads.append(threading.current_thread().name)
        time.sleep(slow.delay)
        return {"slept": slow.delay}

    monkeypatch.setattr(Api, "show", show)
    return slow


def test_health_answers_during_a_slow_call_and_two_calls_run_one_at_a_time(edge: Edge, slow_show: SlowShow) -> None:  # noqa: F811
    """The probe: measured before K7b, `/health` behind a 3 s call answered in 2.3 s. Now the call runs on the one
    worker and the loop answers the probe at once — under half a second while a 2 s call is in flight — and the
    slow call still completes. **And one worker is one:** two 1 s calls issued together take at least 2 s end to
    end, because the second waits for the first, which is the no-new-concurrency the ruling rests on."""
    slow_show.delay = 2.0
    context = client_context(edge.ca, edge.owner)
    body = json.dumps({"target": "queue"}).encode()

    async def probe_during_a_call(port: int) -> tuple[float, bytes | None, bytes | None]:
        slow = asyncio.create_task(attempt(port, context, raw("POST", "/call/show", body)))
        await asyncio.sleep(0.3)  # the call is inside `show` by now
        t0 = time.perf_counter()
        health = await attempt(port, context, raw("GET", "/health"))
        took = time.perf_counter() - t0
        return took, health, await slow

    took, health, slow = against(edge, probe_during_a_call, Limits(read_timeout=10.0, write_timeout=10.0))
    assert status_of(health) == 200 and took < 0.5, f"/health waited {took:.2f}s behind the call"
    assert status_of(slow) == 200 and payload(slow)["result"]["slept"] == 2.0
    assert set(slow_show.threads) == {"isidium-store-calls"}, slow_show.threads

    slow_show.delay = 1.0

    async def two_calls(port: int) -> float:
        t0 = time.perf_counter()
        a, b = await asyncio.gather(
            attempt(port, context, raw("POST", "/call/show", body)),
            attempt(port, context, raw("POST", "/call/show", body)),
        )
        assert status_of(a) == 200 and status_of(b) == 200
        return time.perf_counter() - t0

    elapsed = against(edge, two_calls, Limits(read_timeout=10.0, write_timeout=10.0))
    assert elapsed >= 2.0, f"two calls overlapped: {elapsed:.2f}s"


def test_the_call_span_still_nests_under_the_request_span_from_the_worker(edge: Edge, otel: Telemetry) -> None:  # noqa: F811
    """The context crosses to the worker: the call span is a child of the request span and shares its trace, which
    is the join K6's journal row relies on. A worker that did not carry the context would make every call a root."""
    otel.clear()

    async def scenario(port: int) -> bytes | None:
        return await attempt(
            port,
            client_context(edge.ca, edge.owner),
            raw("POST", "/call/show", json.dumps({"target": "card", "id": 9999}).encode()),
        )

    answer = against(edge, scenario)
    assert status_of(answer) == 404
    (request,), (called,) = otel.spans(telemetry.REQUEST_SPAN), otel.spans(telemetry.CALL_SPAN)
    assert called.parent is not None and called.parent.span_id == request.context.span_id
    assert called.context.trace_id == request.context.trace_id


def test_the_worker_is_one_daemon_thread_that_serialises_and_ends_with_the_server() -> None:
    """The shape itself, without a socket: one named daemon thread; calls run in order, one at a time; an exception
    reaches the future; `shutdown` ends the thread. Daemon is what keeps K6b's exit-after-grace true when a call is
    blocked in the signer — a joined worker would hold the process open past podman's ten seconds."""
    worker = Worker()
    assert worker.thread.daemon is True and worker.thread.name == "isidium-store-calls"
    order: list[str] = []

    def step(name: str, wait: float) -> str:
        order.append(f"{name}:start")
        time.sleep(wait)
        order.append(f"{name}:end")
        return threading.current_thread().name

    a = worker.submit(step, "a", 0.2)
    b = worker.submit(step, "b", 0.0)
    assert a.result(5) == "isidium-store-calls" and b.result(5) == "isidium-store-calls"
    assert order == ["a:start", "a:end", "b:start", "b:end"], order
    boom = worker.submit(lambda: 1 / 0)
    with pytest.raises(ZeroDivisionError):
        boom.result(5)
    with pytest.raises(TypeError):
        worker.submit(step, name="x", wait=0.0)
    worker.shutdown(wait=True)
    assert not worker.thread.is_alive()


# ---- Q16: the tracking root is the store's, by construction ----------------------------------------------------------------


def test_a_policy_write_cannot_move_the_root_and_init_records_the_stores_own() -> None:
    """The review moved `root` by one signed policy write and the store accepted it. Now: `init` writes the store's
    root into the tree (the schema's default happens to be the same one here, and the key is written regardless);
    an `init --root` naming another root is refused; a policy write moving `root` — explicitly, or by deleting the
    key where the default would differ — is refused, and the tree in memory is unchanged.

    **Which id the policy write answers depends on the adopted version** [K10, Q16's schema half]: under `config@3`
    the key is `immutable = true`, so the schema's own gate fires first (`config.immutable`, the generic row every
    immutable key answers with) and the store's `config.root-mismatch` is what remains for `init` and for a tenant
    still on `config@2` — `tests/store/test_k10.py` asserts the `config@2` tenant's answer."""
    hz = fresh("q16")
    st = hz.st
    assert st.config_tree["root"] == "docs/work/" == st.root and st.config_tree["schema"] == 3
    tree = dict(st.config_tree)
    tree["root"] = "other/"
    base = {"seq": st.policy[-1]["seq"], "h": st.policy[-1]["h"]}
    r = refuses("validate.failed", lambda: st.write("config.toml", tree, base, None, OWNER))
    assert verdicts_of(r) == [("config.immutable", "root")]
    assert st.config_tree["root"] == "docs/work/" and st.eff["root"] == "docs/work/"
    assert st.is_governed_repo_path("docs/work/cards/0001-x.md")
    assert not st.is_governed_repo_path("other/cards/0001-x.md")
    # a store whose root is not the schema's default: init records it, and a tree without the key is refused
    other = MemGit()
    elsewhere = Store(
        "elsewhere",
        other,
        Journal(":memory:", "elsewhere"),
        Registry.shipped(),
        hz.clock,
        hz.signer,
        root="docs/tracking/",
    )
    r = refuses("validate.failed", lambda: elsewhere.init(OWNER, software_key_ack="ok", root="docs/work/"))
    assert verdicts_of(r) == [("config.root-mismatch", "root")]
    assert elsewhere.policy == [] and not elsewhere.config_tree
    elsewhere.init(OWNER, software_key_ack="ok")
    assert elsewhere.config_tree["root"] == "docs/tracking/" and other.read("docs/tracking/config.toml") is not None
    bare = dict(elsewhere.config_tree)
    del bare["root"]
    base = {"seq": elsewhere.policy[-1]["seq"], "h": elsewhere.policy[-1]["h"]}
    r = refuses("validate.failed", lambda: elsewhere.write("config.toml", bare, base, None, OWNER))
    assert verdicts_of(r) == [("config.immutable", "root")]  # deleting an immutable key is moving it (config@3)


# ---- Q17: both doors burn ---------------------------------------------------------------------------------------------------


def test_a_refused_ratify_carrying_a_new_card_burns_its_id_like_a_refused_write() -> None:
    """The report's probe, with the ruled outcome: `write(NewCard bad)` refused → the counter moved; `ratify([NewCard
    bad])` refused → the counter moved **again**; the next successful creation gets the id after both gaps. The
    dry run allocates nothing."""
    hz = fresh("q17")
    st = hz.st
    start = st.journal.counter
    bad = Document(base_head(0, "draft"), {"Scope": BASE_SCOPE})
    refuses("head.id-filename", lambda: st.write(NewCard("Bad Slug!"), bad, None, None, PLANNER))
    assert st.journal.counter == start + 1
    req = WriteRequest(NewCard("Bad Slug!"), Document(base_head(0, "ratified"), {"Scope": BASE_SCOPE}), None)
    dry = st.ratify([req], OWNER, dry_run=True)
    assert dry["dry_run"] is True and st.journal.counter == start + 1, "the dry run allocated an id"
    refuses("ratify.invalid", lambda: st.ratify([req], OWNER))
    assert st.journal.counter == start + 2, "the refused sitting un-burnt its id"
    refuses("write.grant", lambda: st.ratify([req], PLANNER))
    assert st.journal.counter == start + 2, "a grant refusal is before allocation, and burns nothing"
    r = st.write(NewCard("fine"), bad, None, None, PLANNER)
    assert r.id == start + 3


# ---- Q18: the result says whether it landed --------------------------------------------------------------------------------


def test_every_write_door_answers_landed_and_the_api_carries_it() -> None:
    """On the double every push succeeds: every door says `landed = True` through the store and through `Api`,
    which is the half of the contract the outage tests in `test_k7a.py` and `test_k9.py` do not reach."""
    hz = fresh("q18")
    api = Api(hz.st)
    head = base_head(0, "draft")
    head.pop("id")
    written = api.write(OWNER, {"new_slug": "landed", "document": {"head": head, "scope": BASE_SCOPE}})
    assert written["landed"] is True and written["id"] is not None
    assert api.write_set(OWNER, written["id"], ["priority=P2"])["landed"] is True
    ratified = api.ratify(OWNER, {"ids": [written["id"]], "dry_run": False})
    assert ratified["landed"] is True
    suggested = api.suggest(PLANNER, {"kind": "docs", "title": "t", "body": "b"})
    assert suggested["landed"] is True
    disposed = api.disposition(OWNER, {"suggestion": suggested["record"]["id"], "outcome": "declined", "reason": "no"})
    assert disposed["landed"] is True
    assert hz.st.bind(hz.realm, hz.signer.key_fpr, "owner", "2026-02-01T00:00:00Z")["act"] == "binding"


# ---- Q19: the registration is the line -------------------------------------------------------------------------------------


def test_an_unregistered_peers_target_reaches_the_span_bounded_and_never_a_row(
    edge: Edge,  # noqa: F811
    otel: Telemetry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The report's probe, over the socket: the healthcheck's class of certificate, a 6000-byte target, a 404 — and
    now zero rows carrying the target, a refusal counted by rule id, and the target on the call span cut to the
    bound."""
    target = "/" + "a" * 6000
    otel.clear()
    counted_before = otel.count("isidium.store.refusal", **{telemetry.RULE: "service.route"})

    async def scenario(port: int) -> bytes | None:
        return await attempt(port, client_context(edge.ca, edge.probe), raw("GET", target))

    with caplog.at_level("WARNING", logger=telemetry.SCOPE):
        probe = against(edge, scenario, Limits(max_header_bytes=64 * 1024))
    assert status_of(probe) == 404 and payload(probe) == {"rule": "service.route"}
    assert "aaaaaaaa" not in "\n".join(r.getMessage() for r in caplog.records), "the stranger's target became a row"
    assert otel.count("isidium.store.refusal", **{telemetry.RULE: "service.route"}) == counted_before + 1
    (routed,) = [s for s in otel.spans(telemetry.CALL_SPAN) if s.attributes.get(telemetry.RULE) == "service.route"]
    detail = routed.attributes[telemetry.DETAIL]
    assert detail == target[: telemetry.DETAIL_BOUND] and len(detail) == telemetry.DETAIL_BOUND


def _expired_der(cn: str) -> bytes:
    """A client certificate for a registered subject whose window closed a year ago — valid in every way but time.
    The handshake would refuse it, so it reaches `Service.handle` as a value: the seam the realm provider will
    hand certificates through with no handshake in front of it (K6)."""
    key = ed25519.Ed25519PrivateKey.generate()
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    then = _dt.datetime(2024, 8, 1, tzinfo=_dt.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(then)
        .not_valid_after(then + _dt.timedelta(days=365))
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False)
        .sign(key, None)
    )
    return cert.public_bytes(serialization.Encoding.DER)


def test_an_auth_refusals_diagnosis_goes_to_the_span_and_not_to_a_row(
    svc: tuple[Service, Harness], otel: Telemetry, caplog: pytest.LogCaptureFixture
) -> None:
    """The `auth.*` family is the other refusal a CA-issued, unregistered-or-defective peer can drive: the operator's
    diagnosis (the subject, the reason) goes on the call span, bounded, and never into a row — the same line."""
    service, _hz = svc
    otel.clear()
    with caplog.at_level("WARNING", logger=telemetry.SCOPE):
        status, body = service_call(service, "show", {"target": "queue"}, _expired_der("owner@example"))
    assert (status, body) == (401, {"rule": "auth.expired"})
    assert "owner@example" not in "\n".join(r.getMessage() for r in caplog.records), "the subject became a row"
    (span,) = otel.spans(telemetry.CALL_SPAN)
    assert span.attributes[telemetry.RULE] == "auth.expired"
    assert (
        "CN=owner@example" in span.attributes[telemetry.DETAIL]
        and "not valid after" in span.attributes[telemetry.DETAIL]
    )


def test_the_edge_fixture_is_still_answered_by_the_worker_after_these(edge: Edge) -> None:  # noqa: F811
    """A guard for the module-scoped edge: the slow-show patch above is undone, and an ordinary call answers."""

    async def scenario(port: int) -> bytes | None:
        return await attempt(port, client_context(edge.ca, edge.owner), raw("GET", "/health"))

    assert status_of(against(edge, scenario)) == 200
