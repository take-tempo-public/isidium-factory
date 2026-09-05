"""K4's own properties: the store's repository is a **partial bare clone**, and the footprint is enforced rather
than assumed.

Every test here would have passed vacuously before K4 or asserts something that could not be stated at all, so read
the traps before changing one — three of them were measured, and each makes a test lie rather than fail.

**Trap 1: `--filter` is ignored outright for local *path* clones** (`warning: --filter is ignored in local clones;
use file:// instead.`). `GitCli.clone` converts a local directory to a `file://` URL for exactly this reason, and
`conftest.tenant_checkout` sets `uploadpack.allowFilter` on the remote — without both, every clone here is a full
one and the absence assertions assert nothing.

**Trap 2: `git cat-file` is not a read-only probe.** It *fetches* the blob it is asked for and keeps it, so a test
that checks absence with `cat-file` makes the property false in the act of measuring it, and passes. Absence is
checked with `cat-file --batch-all-objects --batch-check`, which lists what is held without resolving anything.

**Trap 3: a refused filter is indistinguishable from an accepted one in the clone's config** — both write
`promisor=true` and `partialclonefilter=blob:none`. The footprint is therefore counted, never read off the config.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from isidium.store.core.grammar import Document
from isidium.store.core.refusal import Refusal
from isidium.store.registry.loader import Registry
from isidium.store.server.gitrepo import Footprint, GitCli, blob_id
from isidium.store.server.journal import Journal
from isidium.store.server.signer import SoftwareKey, SoftwareKeyAck
from isidium.store.server.store import NewCard, Store

from .conftest import BASE_SCOPE, OWNER, PLANNER, REGISTRY, base_head, git, store_on_disk, tenant_checkout

ROOT = "docs/work/"


def held(repo: GitCli) -> set[str]:
    """Every object this clone actually holds, by id — **without resolving any of them** (trap 2)."""
    out = subprocess.run(
        ["git", "cat-file", "--batch-all-objects", "--batch-check"],
        cwd=repo.gitdir,
        capture_output=True,
        check=True,
        text=True,
        env={**os.environ, "GIT_NO_LAZY_FETCH": "1"},
    ).stdout
    return {ln.split()[0] for ln in out.splitlines() if ln.strip() and not ln.startswith("warning")}


@pytest.fixture
def store(tmp_path: Path) -> Store:
    tenant_checkout(tmp_path)
    st = store_on_disk(tmp_path / "tenant", tmp_path / "journal.sqlite", root=ROOT)
    st.init(OWNER, software_key_ack="ok for the bare clone", root=ROOT)
    return st


# ---- done-when 1: no working tree, no index ----------------------------------------------------------------------


def test_the_stores_repository_has_no_working_tree_and_no_index(store: Store) -> None:
    """The defect class K4 removes is *structural*, so this asserts the structure and not a behaviour.

    A store that shared a working tree could sweep a caller's staged file onto `main`; one with an index could leak
    into it. Neither exists to guard any more, and after a real governed write — which is when a porcelain
    implementation would have created an index — they still do not.
    """
    repo = store.repo
    assert isinstance(repo, GitCli)
    assert git(repo.gitdir, "rev-parse", "--is-bare-repository").strip() == "true"
    assert not (repo.gitdir / "index").exists()
    store.write(NewCard("no-index"), Document(base_head(0, "draft"), {"Scope": BASE_SCOPE}), None, None, PLANNER)
    assert not (repo.gitdir / "index").exists()
    # and git itself says there is no working tree: `--show-toplevel` is an error in a bare repository, not an
    # empty answer, which is the difference between "no tree" and "a tree at the root"
    toplevel = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], cwd=repo.gitdir, capture_output=True, check=False, text=True
    )
    assert toplevel.returncode != 0 and "must be run in a work tree" in toplevel.stderr


# ---- done-when 2: the footprint, and that it is enforced rather than implied -------------------------------------


def test_a_code_blob_is_absent_while_a_governed_blob_is_held(store: Store) -> None:
    """The footprint, stated as the two facts that make it one: what the clone holds and what it does not.

    The governed blob is present because the store wrote it and then read it back; the code blob is absent because
    nothing legitimately asked for it and nothing may. Asserting only the first would pass on a full clone, and
    asserting only the second would pass on an empty one.
    """
    repo = store.repo
    assert isinstance(repo, GitCli)
    assert repo.footprint is Footprint.FILTERED, "the remote refused the filter — the rest of this test is vacuous"
    governed = repo.oid_of(f"{ROOT}config.toml")
    code = repo.oid_of("client/cards/validator.py")
    assert governed is not None and code is not None, "both paths are in the tree — this is about blobs, not paths"
    objects = held(repo)
    assert governed in objects, "the store cannot read its own governed document"
    assert code not in objects, "a code blob reached the store's clone"


def test_a_read_outside_the_tracking_root_is_refused_and_the_clone_does_not_grow(store: Store) -> None:
    """Q3's ruling, as the test it asked for: *"a read of a non-governed path is refused and the clone does not
    grow"*.

    **The second half is the half that matters and the one a careless test drops.** `--filter=blob:none` is lazy,
    not restrictive: before K4 this exact read *succeeded* and pulled the code blob in permanently, which is how
    *"no code, no media, ever"* turned out not to be a property of the clone mode at all. So the assertion is not
    only that the call refused — it is that the object store is **byte-for-byte the same set** afterwards.

    Mutation-checked: remove the root gate in `GitCli.read` and this fails on the refusal; remove
    `GIT_NO_LAZY_FETCH` from the environment as well and it fails on the growth.
    """
    repo = store.repo
    assert isinstance(repo, GitCli)
    before = held(repo)
    with pytest.raises(Refusal) as ei:
        repo.read("client/cards/validator.py")
    assert ei.value.rule == "git.outside-footprint"
    assert held(repo) == before, "asking for a code blob grew the store's clone"


def test_naming_a_code_blob_by_its_object_id_does_not_fetch_it(store: Store) -> None:
    """**The guard underneath the gate, and the reason there are two.**

    `read` refuses on the path, before git runs. But `oid_of` is deliberately *ungated* — a card's `refs` point
    outside the tracking root by definition (Q11), so resolving one to a blob id is legitimate and must stay so.
    That hands any caller an object id for a code blob, and `blob()` is what turns an id into bytes. Without the
    guard this is the way a code blob enters the store's clone, past a gate that only ever looked at paths.

    Two mutations live here and each kills a different half: removing `GIT_NO_LAZY_FETCH` (the batch reader would
    *fetch* rather than answer `missing` — measured 2026-08-31), and removing the vouching set (`blob` would hydrate
    an id it never resolved from a governed path). The clone-does-not-grow assertion is what sees both.
    """
    repo = store.repo
    assert isinstance(repo, GitCli)
    code_oid = repo.oid_of("client/cards/validator.py")
    assert code_oid is not None, "the ref target is in the tree — that is the point"
    before = held(repo)
    with pytest.raises(Refusal) as ei:
        repo.blob(code_oid)
    assert ei.value.rule == "git.outside-footprint"
    assert held(repo) == before, "naming a code blob by its id pulled it into the store's clone"
    # and the batch reader itself answers `missing` rather than fetching — the guard, with the gate stepped around
    assert repo._reader().read(code_oid) is None
    assert held(repo) == before, "the batch reader fetched a blob the clone is not supposed to hold"


def test_the_footprint_is_counted_and_not_read_off_the_config(tmp_path: Path) -> None:
    """S-9's report, and its first trap: **both** clones write `promisor=true` and `partialclonefilter=blob:none`,
    so the config cannot tell them apart and neither may the report.

    The degradation is the interesting half — a forge that refuses the filter still gives a bare clone with no
    working tree and no index, so the working-tree defect class stays impossible; what grows is the footprint, and
    an operator is entitled to know which one they are running. Here the two are produced deliberately: one remote
    allows the filter and one does not.
    """
    tenant_checkout(tmp_path)
    allowed = GitCli.clone(tmp_path / "origin.git", tmp_path / "a.git", "s", "s@t", root=ROOT)
    git(tmp_path / "origin.git", "config", "uploadpack.allowFilter", "false")
    refused = GitCli.clone(tmp_path / "origin.git", tmp_path / "b.git", "s", "s@t", root=ROOT)
    assert allowed.footprint is Footprint.FILTERED
    assert refused.footprint is Footprint.FULL
    # the config is identical in both, which is why it is not the signal
    for repo in (allowed, refused):
        assert git(repo.gitdir, "config", "remote.origin.promisor").strip() == "true"
        assert git(repo.gitdir, "config", "remote.origin.partialclonefilter").strip() == "blob:none"
    # and the degradation is only ever a footprint: neither clone has a working tree
    assert not (refused.gitdir / "index").exists()


def test_a_governed_write_round_trips_bytes_that_are_not_utf8(store: Store) -> None:
    """The latent bug the brief named, now load-bearing. `GitCli.read` used to run `cat-file` through `str` and
    re-encode the result, so any byte that is not valid UTF-8 came back as U+FFFD — silently, and identically to
    the correct answer for every file that happened to be text.

    It was survivable while the working tree was the source, because that read was already binary. It is not
    survivable now that `cat-file` is the **only** reader, and the store content-addresses what it reads: a
    corrupted byte changes the blob id, which changes `before_blob`, which breaks the journal's own reconciliation.

    The discriminator is a **round trip through git**, not through the store's memory: the bytes are committed and
    read back out of the object store, which is the path that used to translate them.
    """
    repo = store.repo
    assert isinstance(repo, GitCli)
    raw = bytes([0x00, 0xC3, 0x28, 0xFF, 0xFE, 0x80, 0x0A])  # invalid UTF-8, a BOM fragment, a lone continuation
    assert raw.decode("utf-8", "replace").encode("utf-8") != raw, "this fixture is not actually a round-trip hazard"
    repo.commit({f"{ROOT}blob.bin": raw}, "someone@example", store.now(), "bytes that are not text")
    assert repo.read(f"{ROOT}blob.bin") == raw
    assert repo.oid_of(f"{ROOT}blob.bin") == blob_id(raw, repo.object_format)


# ---- done-when 3 and 4: the commit is exact, and a moved ref is refused -------------------------------------------


def test_a_governed_write_is_one_commit_touching_exactly_the_written_paths(store: Store) -> None:
    repo = store.repo
    before = repo.head
    store.write(NewCard("exactly-one"), Document(base_head(0, "draft"), {"Scope": BASE_SCOPE}), None, None, PLANNER)
    after = repo.head
    assert after is not None and before is not None
    assert repo.parents(after) == [before], "a governed write is one commit on HEAD"
    assert sorted(repo.touched(after)) == [f"{ROOT}cards/0001-exactly-one.md"]


def test_a_commit_onto_a_ref_that_moved_locally_is_refused(store: Store, monkeypatch: pytest.MonkeyPatch) -> None:
    """`update-ref`'s **expected old value** is the compare-and-swap, and this is the test that can see it.

    The push lease below is a different property against a different actor — that one is about the *remote* moving.
    This one is about the store's own repository: two writers over one clone, which is what a restarted container
    beside a still-running one looks like, and what `store_on_disk` produces whenever a test opens a second store.
    Without the old value in the `update-ref` call the second writer silently overwrites the first, and every
    assertion about the journal still passes, because the journal row was written before the commit.

    The discriminator is the ref itself: after the refusal, `HEAD` is the *other* writer's commit and not this
    one's, which is what says the swap was compared rather than merely attempted.
    """
    repo = store.repo
    assert isinstance(repo, GitCli)
    stale = repo.head  # this writer's view of the ref, before the other one moves it
    assert stale is not None
    other = GitCli(repo.gitdir, "isidium-store", "store@sartor", push=False, root=ROOT)
    moved = other.commit({f"{ROOT}cards/0009-other.md": b"# other\n"}, "other@example", store.now(), "the other one")
    assert moved != stale

    # The race made deterministic: `commit` reads `head` immediately before `update-ref`, so the window a real
    # concurrent writer would land in is microseconds wide. Pinning `head` to the value this writer already held is
    # that window, held open — the state the compare-and-swap exists for and the only way to observe it on purpose.
    monkeypatch.setattr(GitCli, "head", property(lambda _self: stale))
    with pytest.raises(Refusal) as ei:
        repo.commit({f"{ROOT}cards/0010-mine.md": b"# mine\n"}, "mine@example", "2026-08-31T00:00:00Z", "a write")
    assert ei.value.rule == "git.ref-moved"
    monkeypatch.undo()
    # the discriminator: the other writer's commit is still what the ref holds, so the swap was compared and not
    # merely attempted — without the expected old value this writer's commit would be sitting here instead
    assert git(repo.gitdir, "rev-parse", "HEAD").strip() == moved


def test_a_push_onto_a_moved_ref_is_refused_and_never_rebased(store: Store, tmp_path: Path) -> None:
    """The old shape answered a rejected push with `pull --rebase` and one retry. There is no working tree to
    rebase in — and the store's own compare-and-swap on the document head sits upstream of this, so a remote that
    moved means a **second writer**, which is a condition to report rather than to merge past.

    The discriminator is that the remote is left alone: a rebase-and-retry would have landed the store's commit on
    top of the stranger's, which is the silent outcome this refusal exists to prevent.

    **Its subject split when Q14 was ruled (2026-09-03), and this half is the one that did not move.** `GitCli`
    knows nothing about which paths are governed, so a plain push onto a moved ref is rejected here whatever moved
    — that is K4's property, unrefined, and it is what the store's own answer is built on top of. What Q14 refines
    is the *store's* answer to this rejection, which needs the tenant's manifest: an ungoverned move is now
    fast-forwarded and the write lands, a governed one is still `git.push-rejected`. Both halves are in
    `tests/store/test_k9.py`, and neither can be seen from here, because a test that calls `repo.push()` directly
    never reaches the code that decides.
    """
    repo = store.repo
    assert isinstance(repo, GitCli)
    store.write(NewCard("first"), Document(base_head(0, "draft"), {"Scope": BASE_SCOPE}), None, None, PLANNER)
    # a stranger pushes to the remote's `main` between the store's commit and its push
    stranger = tmp_path / "stranger"
    git(tmp_path, "clone", "-q", str(tmp_path / "origin.git"), str(stranger))
    git(stranger, "config", "user.name", "stranger")
    git(stranger, "config", "user.email", "stranger@example")
    (stranger / "unrelated.txt").write_text("elsewhere\n", encoding="utf-8")
    git(stranger, "add", "unrelated.txt")
    git(stranger, "commit", "-q", "-m", "a second writer")
    git(stranger, "push", "-q", "origin", "HEAD:main")
    remote_head = git(tmp_path / "origin.git", "rev-parse", "main").strip()

    repo.commit({f"{ROOT}cards/0002-x.md": b"# x\n"}, "someone@example", store.now(), "a write")
    with pytest.raises(Refusal) as ei:
        repo.push()
    assert ei.value.rule == "git.push-rejected"
    assert git(tmp_path / "origin.git", "rev-parse", "main").strip() == remote_head, "the store rebased onto a stranger"


# ---- done-when 5: the store's registry is its own, resolved through the manifest ----------------------------------


def test_the_store_validates_against_its_own_installed_registry(store: Store) -> None:
    """K4's second half. `Registry.for_checkout` reads `.isidium/schemas/` from a working tree and `init` gitignores
    that directory — so under a bare clone it would find nothing and fall back to the shipped documents *while
    looking like it had read the tenant's*, undoing the WP3 review's C5 silently rather than loudly.

    The positive discriminator is the second assertion: the schemas are genuinely not in the store's tree, so the
    registry it holds cannot have come from there.
    """
    assert store.registry.installed == Registry.shipped().installed
    assert not [p for p in store.repo.paths() if p.startswith(".isidium/")], "the schemas reached the store's clone"
    assert store.eff["governed"], "the manifest is what the store resolves a path's schema against"


def test_a_manifest_naming_an_uninstalled_version_is_refused(store: Store, tmp_path: Path) -> None:
    """*"A path may not reference a version the installed registry lacks"* — `config.schema-unknown`, raised against
    the store's own registry, which after K4 is the only registry in the question."""
    repo = store.repo
    raw = repo.read(f"{ROOT}config.toml")
    assert raw is not None
    doctored = raw.decode("utf-8").replace('schema = "card@1"', 'schema = "card@7"', 1).encode("utf-8")
    assert doctored != raw, "the manifest row this test doctors was not found"
    repo.commit({f"{ROOT}config.toml": doctored}, "someone@example", store.now(), "name a version nobody has")
    with pytest.raises(Refusal) as ei:
        Store(
            "sartor",
            repo,
            Journal(tmp_path / "journal.sqlite", "sartor"),
            REGISTRY,
            lambda: 1_787_000_000,
            SoftwareKeyAck(SoftwareKey.generate()),
            root=ROOT,
        )
    assert "config.schema-unknown" in str(ei.value)


# ---- done-when 6: reads are batched ------------------------------------------------------------------------------


def test_reads_go_through_one_long_lived_process_and_not_one_spawn_each(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The efficiency rule landing on the chunk that touches it (C-8), asserted as **process count** rather than as
    a clock: a timing assertion cannot tell a fast answer from an empty one.

    Measured 2026-08-31 on this workstation, 40 reads of a bare clone, medians of 5: one subprocess per read is
    13129 ms against 593 ms through one batch process — 22x, and the ratio is the file count on any machine. The
    store's load walks every governed path, so the naive shape turns N cheap reads into N process spawns.
    """
    repo = store.repo
    assert isinstance(repo, GitCli)
    for i in range(6):  # warm the batch process and give the clone something to read
        store.write(
            NewCard(f"batched-{i}"), Document(base_head(0, "draft"), {"Scope": BASE_SCOPE}), None, None, PLANNER
        )
    paths = [p for p in repo.paths() if p.startswith(ROOT)]
    assert len(paths) >= 6, paths

    spawned: list[list[str]] = []
    real = subprocess.run

    def counting(args: Any, **kw: Any) -> Any:
        spawned.append(list(args))
        return real(args, **kw)

    monkeypatch.setattr(subprocess, "run", counting)
    for p in paths:
        assert repo.read(p) is not None
    assert spawned == [], f"{len(paths)} reads spawned {len(spawned)} processes: {spawned[:3]}"
