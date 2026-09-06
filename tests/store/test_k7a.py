"""K7a — the gate and the write path's atomicity (the K7 review's F1, F2, F28, F3, F17, F4, F5; F11 is in
`test_verify_chain.py` itself).

Every test here reproduces the refuter's probe first and then asserts the property the fix claims, on real git and
a real bare origin where the finding was about git, and on a real TLS listener where it was about the edge. The
positive discriminators are the ones the review asked for: a rename that is *named at the source*; a journal that
*explains every transition* after a failed push and a restart; a sitting whose refusal leaves *nothing* behind; an
absent registration that answers `auth.unknown-client` while `/health` still answers; a `repair` target that never
reaches git's argv.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from isidium.store.client import hook as hook_mod
from isidium.store.core import telemetry
from isidium.store.core.grammar import Document
from isidium.store.core.refusal import Refusal
from isidium.store.server.api import Api
from isidium.store.server.gitrepo import GitCli
from isidium.store.server.http import tls_context
from isidium.store.server.service import Registration
from isidium.store.server.store import NewCard, Store

from .conftest import BASE_SCOPE, OWNER, PLANNER, Telemetry, base_head, fresh, git, store_on_disk, tenant_checkout
from .test_edge import NOW, Edge, Recording, attempt, authority, client_context, issue, raw, status_of
from .test_edge import against as against_edge
from .test_verify_chain import built, run, tenant  # noqa: F401  (pytest names an imported fixture by its attribute)

ROOT = "docs/work/"


@pytest.fixture
def store(tmp_path: Path) -> Store:
    tenant_checkout(tmp_path)
    st = store_on_disk(tmp_path / "tenant", tmp_path / "journal.sqlite", root=ROOT)
    st.init(OWNER, software_key_ack="ok for K7a", root=ROOT)
    return st


def draft(st: Store, slug: str) -> str:
    r = st.write(NewCard(slug), Document(base_head(0, "draft"), {"Scope": BASE_SCOPE}), None, None, PLANNER)
    return r.path


def amended(st: Store, path: str, priority: str) -> Document:
    doc = Document(dict(st.docs[path].head), dict(st.docs[path].sections))
    doc.head["priority"] = priority
    return doc


class Outage:
    """A transient origin failure, armed by the test: the bare origin is renamed away for the duration of the next
    push after `arm()` and put back. Any failure between the local commit and a successful push — an outage, the
    MTU black hole the record has met twice, a forge 5xx — leaves the same state; this is the cheapest one to make
    on a workstation. `fired` counts the pushes it broke, which is the assertion that the test hit its own trap."""

    def __init__(self, origin: Path) -> None:
        self.origin, self.hidden = origin, origin.with_name("origin.hidden")
        self.armed = False
        self.fired = 0

    def arm(self) -> None:
        self.armed = True


@pytest.fixture
def outage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Outage]:
    state = Outage(tmp_path / "origin.git")
    original = GitCli.push

    def failing(self: GitCli) -> None:
        if not state.armed:
            return original(self)
        state.armed = False
        state.fired += 1
        state.origin.rename(state.hidden)
        try:
            original(self)
        finally:
            state.hidden.rename(state.origin)

    monkeypatch.setattr(GitCli, "push", failing)
    yield state


def on_main(tmp_path: Path, rel: str) -> str:
    return git(tmp_path / "origin.git", "show", f"main:{rel}")


# ---- F1: a rename is a change to both paths, at both doors ---------------------------------------------------------


def test_a_governed_card_cannot_leave_the_root_by_rename_at_either_door(
    tenant: tuple[Path, Store],  # noqa: F811  (the imported fixture, by the name pytest registered it under)
) -> None:
    """The hook, the pull-request check and the push-to-main check all read `git diff --name-only`, which under
    rename detection lists a rename's destination only — so `git mv` of a card out of the root passed all three.
    Now the source is named at every door, the controls (an ungoverned rename; a checkout whose parent cannot be
    seen) answer the way they should, and a card that has already left `main` is a verdict, not a silence."""
    work, _ = tenant
    cards = sorted((work / ROOT / "cards").glob("*.md"))
    assert cards, "the built checkout carries a card"
    card = cards[0].relative_to(work).as_posix()
    (work / "docs/archive").mkdir(parents=True)
    git(work, "mv", card, "docs/archive/moved.md")
    # the hook: the source is what is governed, and it is named
    assert hook_mod.offending(work) == [card]
    assert hook_mod.check(work) == 1
    git(work, "reset", "-q", "--hard", "HEAD")
    # the control: an ungoverned rename is nobody's business
    git(work, "mv", "README.md", "docs/README-moved.md")
    assert hook_mod.offending(work) == []
    git(work, "reset", "-q", "--hard", "HEAD")

    # the pull request: the rename committed on a branch, checked against main
    git(work, "checkout", "-q", "-b", "move")
    (work / "docs/archive").mkdir(exist_ok=True)  # `reset --hard` removed it once it was empty
    git(work, "mv", card, "docs/archive/moved.md")
    git(work, "commit", "-q", "-m", "move a card out of the governed set")
    rc, out = run(work, "--diff-base", "main")
    assert rc == 1, out
    assert f"changed  {card}" in out, out
    # the push to main: merged, the parent had the card and HEAD does not
    git(work, "checkout", "-q", "main")
    git(work, "merge", "-q", "--ff-only", "move")
    rc, out = run(work)
    assert rc == 1, out
    assert f"removed  {card}" in out, out
    # the control for the push-to-main arm: the parent, where the card still exists, passes
    git(work, "checkout", "-q", "HEAD^")
    rc, out = run(work)
    assert rc == 0, out
    git(work, "checkout", "-q", "main")
    # a shallow checkout cannot compare and is refused rather than passed — the runner fetches full depth
    shallow = work.parent / "shallow"
    git(work.parent, "clone", "-q", "--depth", "1", work.as_uri(), str(shallow))
    rc, out = run(shallow)
    assert rc == 1 and "verify.shallow" in out, out


# ---- F28 / F17: the write door, a failed push, the next push and a restart ----------------------------------------


def test_a_write_whose_push_fails_is_journaled_indexed_and_carried_by_the_next_push(
    store: Store, tmp_path: Path, outage: Outage, otel: Telemetry
) -> None:
    """The row is durable before the push, so the act happened. The old code raised with `raw` moved and `docs`
    not, and left the row pending; the next write carried the orphan commit onto `main`, and the restart's replay
    wrote the orphan's bytes over everything since — `check` read `tampered, unjournaled` on a card nobody had
    bypassed anything to reach. Now: **indexed**, answered to the caller as its result with `landed = False`
    [K7b, Q18, ruled 2026-09-06 — until then a refusal, which K7a kept], counted on the unlanded counter by the
    push failure's own id (`git.failed`: absent, not moved — F17), carried by the next successful push, which clears
    the pending row and answers `landed = True`; a restart replays nothing and the chain explains itself."""
    path = draft(store, "deferred")
    before = git(tmp_path / "origin.git", "rev-parse", "main").strip()
    unlanded_before = otel.count("isidium.store.write.unlanded", **{telemetry.RULE: "git.failed"})
    outage.arm()
    with telemetry.span(telemetry.CALL_SPAN, **{telemetry.ACTION: "write"}) as call:
        r2 = store.write(path, amended(store, path, "P2"), store.docs[path].head_of(), None, PLANNER)
    assert r2.landed is False and r2.entry["seq"] == 2 and r2.head == store.docs[path].head_of()
    assert outage.fired == 1
    assert otel.count("isidium.store.write.unlanded", **{telemetry.RULE: "git.failed"}) == unlanded_before + 1
    assert call.attributes[telemetry.LANDED] is False, "the call span did not say the write had not landed"  # type: ignore[attr-defined]
    assert git(tmp_path / "origin.git", "rev-parse", "main").strip() == before, "nothing reached the origin"
    # the act happened: the row is pending, memory is indexed, the commit is held
    assert [s for s, _p, _d in store.journal.pending_rows()] == [3]
    assert store.docs[path].history[-1]["seq"] == 2 and store.docs[path].head["priority"] == "P2"
    assert store.repo.first_parent_walk(before) != [], "the store holds its own unpushed commit"

    otel.clear()
    r3 = store.write(path, amended(store, path, "P3"), store.docs[path].head_of(), None, PLANNER)
    assert r3.entry["seq"] == 3 and r3.landed is True
    sync = [s for s in otel.spans(telemetry.SYNC_SPAN) if s.attributes.get(telemetry.ACTION) == "fast-forward"]
    assert sync and sync[0].attributes[telemetry.DIVERGED] is True, "the diverged sync was not said out loud"
    assert store.journal.pending_rows() == [], "the push that carried the orphan did not clear its row"
    assert 'priority = "P3"' in on_main(tmp_path, store.rp(path))
    landed = git(tmp_path / "origin.git", "rev-parse", "main").strip()

    # a restart over the same journal: nothing to replay, main unmoved, the chain and the journal agree
    again = store_on_disk(tmp_path / "tenant", tmp_path / "journal.sqlite", root=ROOT)
    assert git(tmp_path / "origin.git", "rev-parse", "main").strip() == landed
    assert 'priority = "P3"' in on_main(tmp_path, store.rp(path))
    assert again.check(int(again.docs[path].head["id"]))["integrity"] == []


def test_a_write_whose_push_is_rejected_still_says_rejected(store: Store, tmp_path: Path) -> None:
    """F17's other half: a real non-fast-forward is `git.push-rejected`, and only that."""
    other = tmp_path / "other"
    git(tmp_path, "clone", "-q", str(tmp_path / "origin.git"), str(other))
    git(other, "config", "user.email", "s@example")
    git(other, "config", "user.name", "s")
    (other / "notes.txt").write_bytes(b"a second writer\n")
    git(other, "add", "-A")
    git(other, "commit", "-q", "-m", "moved main")
    git(other, "push", "-q", "origin", "HEAD:main")
    store.repo.commit({"docs/dev/x.md": b"x\n"}, "store", "2026-09-06T00:00:00Z", "a commit behind the move")
    with pytest.raises(Refusal) as refused:
        store.repo.push()
    assert refused.value.rule == "git.push-rejected", str(refused.value)


# ---- F2 / F3: the sitting rolls back whole; a refusal before the row leaves no phantom -----------------------------


def test_a_ratify_whose_push_fails_leaves_nothing_behind(store: Store, tmp_path: Path, outage: Outage) -> None:
    """Inside the sitting the row is part of the transaction the failure rolls back, so the act did not happen —
    and everything that had been moved before the push (the manifest in `self.policy`, `raw`, `_blob`, the local
    commit) goes back with it. The old code kept all four, and the next write pushed the rolled-back ratification as
    its own parent."""
    path = draft(store, "sitting")
    cid = int(store.docs[path].head["id"])
    rows = len(store.journal.rows())
    policy, raw, blob = len(store.policy), store.raw[path], store._blob[path]
    head_before = store.repo.head
    assert head_before == git(tmp_path / "origin.git", "rev-parse", "main").strip()

    outage.arm()
    with pytest.raises(Refusal) as refused:
        store.ratify([cid], OWNER)
    assert refused.value.rule == "git.failed", str(refused.value)
    assert outage.fired == 1
    assert (len(store.journal.rows()), store.journal.pending_rows()) == (rows, [])
    assert len(store.policy) == policy, "a phantom manifest stayed in memory"
    assert (store.raw[path], store._blob[path]) == (raw, blob)
    assert store.docs[path].head["status"] == "draft"
    assert store.repo.head == head_before, "the sitting's commit was not un-built"

    # and the sitting, retried, lands whole; a restart reads a store that agrees with its journal
    result = store.ratify([cid], OWNER)
    assert result["verdicts"][cid] == [] and store.docs[path].head["status"] == "ratified"
    again = store_on_disk(tmp_path / "tenant", tmp_path / "journal.sqlite", root=ROOT)
    assert again.check(cid)["integrity"] == []
    assert len(again.policy) == policy + 1


def test_an_init_refused_before_the_row_can_be_retried(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """F3: the first thing a new tenant does is `init`, and if the origin is unreachable at that moment the old
    code kept the entry it never wrote, so the retry was `write.stale` until a restart."""
    tenant_checkout(tmp_path)
    st = store_on_disk(tmp_path / "tenant", tmp_path / "journal.sqlite", root=ROOT)
    original = GitCli.fetch
    once: list[int] = []

    def unreachable(self: GitCli) -> str | None:
        if not once:
            once.append(1)
            raise Refusal("git.fetch-failed", "origin", "no route")
        return original(self)

    monkeypatch.setattr(GitCli, "fetch", unreachable)
    with pytest.raises(Refusal) as refused:
        st.init(OWNER, software_key_ack="ok", root=ROOT)
    assert refused.value.rule == "git.fetch-failed"
    assert st.policy == [] and not st.config_tree, "a phantom entry survived the refusal"
    r = st.init(OWNER, software_key_ack="ok", root=ROOT)
    assert r.entry["seq"] == 1 and len(st.policy) == 1


# ---- F4: an absent registration names nobody, says so, and the probe still answers ---------------------------------


def test_an_absent_registration_names_nobody_and_health_still_answers(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """`_refresh` stat-ed the file outside its `try`, so a deleted or renamed-away registration raised out of
    `credential()` into the connection handler's `except OSError` — every connection, the health probe included,
    died with nothing counted and nothing written. Now absence is the parse failure's case: nobody, one note, and
    `auth.unknown-client` at the door while `/health` keeps answering."""
    ca = authority(tmp_path, "tenant-ca")
    server_cert, server_key = issue(ca, tmp_path, "store.sartor", "store", server=True)
    owner = issue(ca, tmp_path, "owner@example", "owner")
    reg_file = tmp_path / "registration.json"
    reg_file.write_text('{"CN=owner@example": ["amodal1@example", "owner"]}', encoding="utf-8")
    registration = Registration.from_file(reg_file, lambda: int(NOW.timestamp()))
    harness = fresh("k7a-edge")
    edge = Edge(
        service=Recording(Api(harness.st), registration, harness.st.tenant),
        context=tls_context(server_cert, server_key, ca.path),
        ca=ca,
        other_ca=ca,
        owner=owner,
        stranger=owner,
        expired=owner,
        probe=owner,
        harness=harness,
    )
    ctx = client_context(ca, owner)

    async def scenario(port: int) -> list[Any]:
        seen: list[Any] = []
        seen.append(status_of(await attempt(port, ctx, raw("GET", "/health"))))
        os.remove(reg_file)
        with caplog.at_level(logging.WARNING, logger="isidium.store"):
            seen.append(await attempt(port, ctx, raw("GET", "/health")))
            seen.append(await attempt(port, ctx, raw("POST", "/call/show", b'{"target": "queue"}')))
        reg_file.write_text('{"CN=owner@example": ["amodal1@example", "owner"]}', encoding="utf-8")
        seen.append(status_of(await attempt(port, ctx, raw("POST", "/call/show", b'{"target": "queue"}'))))
        return seen

    healthy, health_absent, call_absent, restored = against_edge(edge, scenario)
    assert healthy == 200
    assert status_of(health_absent) == 200, "the probe died with the registration"
    assert status_of(call_absent) == 403 and b"auth.unknown-client" in (call_absent or b"")
    assert any("absent" in r.getMessage() and "names nobody" in r.getMessage() for r in caplog.records)
    assert restored == 200, "the registration came back and nobody noticed"


# ---- F5: `repair --journal` takes a commit id and nothing else -----------------------------------------------------


def test_repair_journal_is_a_commit_id_and_nothing_reaches_argv(store: Store, tmp_path: Path) -> None:
    """`--output=<file>` reached `diff-tree`'s argv and truncated the file before git refused; a ref name was
    accepted where the design says commit. Now the boundary refuses anything but a full hex id, and the git layer
    puts `--end-of-options` first so a value that does get through is a revision and nothing else."""
    target = tmp_path / "victim.txt"
    target.write_bytes(b"thirty-nine bytes that must not be lost\n")
    with pytest.raises(Refusal) as refused:
        store.repair(OWNER, journal=f"--output={target}")
    assert refused.value.rule == "repair.target"
    with pytest.raises(Refusal) as by_name:
        store.repair(OWNER, journal="HEAD")
    assert by_name.value.rule == "repair.target"
    assert target.read_bytes().startswith(b"thirty-nine"), "the file was truncated"
    # the git layer alone, as a caller that skipped the store would meet it
    with pytest.raises(Refusal) as at_git:
        store.repo.touched(f"--output={target}")
    assert at_git.value.rule == "git.failed"
    assert target.read_bytes().startswith(b"thirty-nine"), "argv reached git"
    # and the real thing still works: an ungoverned commit by a stranger, explained
    other = tmp_path / "other"
    git(tmp_path, "clone", "-q", str(tmp_path / "origin.git"), str(other))
    git(other, "config", "user.email", "s@example")
    git(other, "config", "user.name", "s")
    (other / "docs/dev").mkdir(parents=True, exist_ok=True)
    (other / "docs/dev/note.md").write_bytes(b"outside the root\n")
    git(other, "add", "-A")
    git(other, "commit", "-q", "-m", "a stranger's commit")
    git(other, "push", "-q", "origin", "HEAD:main")
    sha = git(tmp_path / "origin.git", "rev-parse", "main").strip()
    draft(store, "after-the-stranger")  # the write's sync brings the stranger's commit into the store's clone
    assert store.repair(OWNER, journal=sha)["journal_row"]["repairs"] == sha


def test_the_client_side_hook_names_the_source_of_a_staged_rename(tmp_path: Path) -> None:
    """`hook.staged` on its own, without the tool: the raw staged set lists both ends."""
    work = tenant_checkout(tmp_path)
    (work / "moved").mkdir()
    git(work, "mv", "README.md", "moved/README.md")
    assert sorted(hook_mod.staged(work)) == ["README.md", "moved/README.md"]
    shutil.rmtree(work / "moved", ignore_errors=True)
    subprocess.run(["git", "reset", "-q", "--hard", "HEAD"], cwd=work, check=True)
