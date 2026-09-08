"""K12's own properties (ruled 2026-09-08 in the sartor bridge's first exchange, *"One chunk first"*): **the doors
that resolve `refs` read `main` first**, and the two small things the bridge's first turn found beside them.

**The condition, measured on tenant #0 (2026-09-07).** The container's clone was at the owner's `config@3` act; one
pull request had merged since, adding `AGENTS.md`; a dry run of a draft with `refs = ["AGENTS.md#for-the-planner"]`
answered `ref.unresolved … no such path` while the terminal's pre-flight — which reads the working tree — had
passed the heading. `_sync_to_main` had one call site, the top of `_apply`, which the dry run never reaches and the
signed sitting reaches only after its members are composed. The planner is told to present nothing the dry run has
not passed, so a ref to anything merged since the store's last write could not pass.

**Read K9's traps before changing one of these.** The fixture's store is a fresh clone, so a running store that must
see a remote move has the remote moved under it (`stranger_pushes`), never a second store opened. A ref here points
*outside* the tracking root (`ref.inside-root` refuses the other case), and the file the stranger pushes is exactly
that: ungoverned, outside the root, and absent from the clone the store started with.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import typer

from isidium.store.client import cli as cli_mod
from isidium.store.core.grammar import Document
from isidium.store.core.refusal import Refusal, ValidationRefusal
from isidium.store.server.gitrepo import GitCli
from isidium.store.server.store import NewCard, Store, WriteRequest

from .conftest import BASE_SCOPE, OWNER, PLANNER, base_head, git, store_on_disk, tenant_checkout
from .test_k9 import ROOT, stranger_pushes

MERGED = "docs/dev/merged-after-the-store-started.md"


@pytest.fixture
def store(tmp_path: Path) -> Store:
    """K9's fixture, restated: a fresh clone of a tenant's remote, `init` run — the restarted container."""
    tenant_checkout(tmp_path)
    st = store_on_disk(tmp_path / "tenant", tmp_path / "journal.sqlite", root=ROOT)
    st.init(OWNER, software_key_ack="ok for K12", root=ROOT)
    return st


def born_ratified(ref: str) -> Document:
    """A card born `ratified` whose one extra ref is the file a stranger merged: the profile's other refs are the
    seeded targets every on-disk checkout carries (`conftest.REF_FILES`)."""
    head = base_head(0, "ratified")
    head["refs"] = [*head["refs"], ref]
    return Document(head, {"Scope": BASE_SCOPE})


def rules(verdicts: list[Refusal]) -> list[str]:
    return [r.rule for r in verdicts]


# ---- the sitting reads `main` before it composes -----------------------------------------------------------------


def test_a_dry_run_after_a_merge_resolves_a_ref_to_the_merged_file(store: Store, tmp_path: Path) -> None:
    """The dry run's tree is `main`'s, not the clone's at start. The discriminator is the ref: before the dry run
    the store's head is behind the remote; after it, the head is the merged tip and no `ref.*` verdict names the
    file. Without the sync at this door the ref is `ref.unresolved: … no such path` — the mutation that removes it
    dies here."""
    repo = store.repo
    assert isinstance(repo, GitCli)
    tip = stranger_pushes(tmp_path, MERGED, b"merged through a pull request after the store cloned\n")
    assert repo.head != tip, "the fixture's premise: the running store has not seen the merge"

    result = store.ratify([WriteRequest(NewCard("sees-main"), born_ratified(MERGED), None)], PLANNER, dry_run=True)

    assert repo.head == tip, "the dry run did not fast-forward onto the merged tip"
    (pid,) = result["verdicts"]
    assert not [v for v in result["verdicts"][pid] if str(v["rule"]).startswith("ref.")], result["verdicts"]


def test_a_signed_sitting_after_a_merge_lands_on_the_merged_tip_with_its_ref_resolved(
    store: Store, tmp_path: Path
) -> None:
    """The signed run is the same function: the member composes against `main`, the sitting lands, and its commit's
    parent is the stranger's tip — built on what the remote holds, with the ref it cites in that tree."""
    repo = store.repo
    assert isinstance(repo, GitCli)
    tip = stranger_pushes(tmp_path, MERGED, b"merged before the sitting\n")
    assert repo.head != tip

    result = store.ratify([WriteRequest(NewCard("born-on-main"), born_ratified(MERGED), None)], OWNER)

    assert result["landed"] is True and result["ids"], result
    assert repo.parents(result["commit"]) == [tip], "the sitting was built on the store's stale base"


def test_an_ordinary_dry_run_pays_one_fetch_and_fast_forwards_nothing(store: Store) -> None:
    """The steady state at this door: the remote has not moved, so the dry run is one fetch and no fast-forward —
    counted, not timed. Zero fetches is the defect this chunk closes; two would be a fetch nobody asked for."""
    repo = store.repo
    assert isinstance(repo, GitCli)
    fetches: list[str | None] = []
    moves: list[str] = []
    original_fetch, original_ff = GitCli.fetch, GitCli.fast_forward

    def counted_fetch(self: GitCli) -> str | None:
        tip = original_fetch(self)
        fetches.append(tip)
        return tip

    def counted_ff(self: GitCli, to: str) -> bool:
        moves.append(to)
        return original_ff(self, to)

    GitCli.fetch = counted_fetch  # type: ignore[method-assign]
    GitCli.fast_forward = counted_ff  # type: ignore[method-assign]
    try:
        store.ratify([WriteRequest(NewCard("quiet"), born_ratified("README.md"), None)], PLANNER, dry_run=True)
    finally:
        GitCli.fetch, GitCli.fast_forward = original_fetch, original_ff  # type: ignore[method-assign]
    assert len(fetches) == 1, f"the dry run fetched {len(fetches)} times"
    assert moves == [], "the dry run fast-forwarded onto a remote that had not moved"


def test_a_dry_run_after_a_bypass_on_the_remote_is_refused_before_it_composes(store: Store, tmp_path: Path) -> None:
    """A governed path moved on the remote — the bypass `check` exists for — is `git.push-rejected` at the dry run
    now, one sitting earlier than the write would have said it. The ref does not move: the store never
    fast-forwards over a governed change."""
    repo = store.repo
    assert isinstance(repo, GitCli)
    before = repo.head
    stranger_pushes(tmp_path, f"{ROOT}cards/0009-bypass.md", b"# a bypass\n")
    with pytest.raises(Refusal) as ei:
        store.ratify([WriteRequest(NewCard("after-a-bypass"), born_ratified("README.md"), None)], PLANNER, dry_run=True)
    assert ei.value.rule == "git.push-rejected"
    assert repo.head == before


def test_a_dry_run_that_cannot_reach_the_origin_is_a_typed_refusal(store: Store, tmp_path: Path) -> None:
    """A dry run against a tree it cannot see is not a dry run: `git.fetch-failed`, the same id the write answers."""
    repo = store.repo
    assert isinstance(repo, GitCli)
    git(repo.gitdir, "config", "remote.origin.url", str(tmp_path / "no-such-origin.git"))
    with pytest.raises(Refusal) as ei:
        store.ratify([WriteRequest(NewCard("with-no-origin"), born_ratified("README.md"), None)], PLANNER, dry_run=True)
    assert ei.value.rule == "git.fetch-failed"


# ---- a card born `ratified` through `write` reads `main` before its refs ------------------------------------------


def test_a_born_ratified_write_after_a_merge_resolves_its_ref_and_lands_on_the_tip(
    store: Store, tmp_path: Path
) -> None:
    """`write` resolves refs only for a card born `ratified`, and did so against the clone at start. Now it syncs
    first: the ref to the merged file resolves, and the commit's parent is the stranger's tip."""
    repo = store.repo
    assert isinstance(repo, GitCli)
    tip = stranger_pushes(tmp_path, MERGED, b"merged before a born-ratified write\n")
    assert repo.head != tip

    r = store.write(NewCard("born-ratified-on-main"), born_ratified(MERGED), None, None, OWNER)

    assert repo.parents(r.commit) == [tip], "the write was built on the store's stale base"


def test_a_born_ratified_write_still_refuses_a_ref_main_does_not_hold(store: Store) -> None:
    """The control: the sync does not make a ref resolve that `main` never held. The refusal is the validation's,
    naming the ref, and nothing is committed."""
    repo = store.repo
    assert isinstance(repo, GitCli)
    before = repo.head
    with pytest.raises(ValidationRefusal) as ei:
        store.write(NewCard("phantom"), born_ratified("docs/dev/never-merged.md"), None, None, OWNER)
    assert [(v.rule, v.detail) for v in ei.value.verdicts] == [
        ("ref.unresolved", "docs/dev/never-merged.md: no such path")
    ]
    assert repo.head == before


# ---- the `mcp` verb refuses the way every verb does --------------------------------------------------------------


def test_the_mcp_verb_refuses_where_there_is_no_client_file_on_one_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The bridge's finding 1: opened outside a checkout, the verb answered `client.not-configured` as a typer
    traceback with exit 1, and the harness reading its stderr saw "Connection closed". Now: one line, exit 2."""
    monkeypatch.delenv("ISIDIUM_CLIENT", raising=False)
    nowhere = tmp_path / "nowhere"
    nowhere.mkdir()
    monkeypatch.chdir(nowhere)
    with pytest.raises(typer.Exit) as ex:
        cli_mod.mcp()
    assert ex.value.exit_code == 2
    err = capsys.readouterr().err
    assert "client.not-configured @ .isidium/client.toml" in err, err
    assert "Traceback" not in err, err
