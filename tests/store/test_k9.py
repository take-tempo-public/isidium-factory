"""K9's own properties (Q14 (c), ruled 2026-09-03): **the store re-reads `main` before it writes.**

The condition these tests are about was measured on tenant #0 the day the gate went up. Three pull requests merged
after the store's container started; the store's clone stayed at its own last commit, because a running store never
re-read `main`; and the next governed write was built on that stale base and refused. The write was not lost — the
journal row replayed on the next restart — but under the gate a merged pull request is the *ordinary* event, so the
store needed an operator standing beside it.

**Read the traps before changing one.**

*Trap 1: the two halves live at different levels, and only one of them is `GitCli`'s.* A plain push onto a moved ref
is rejected no matter what moved, because `GitCli` knows nothing about which paths are governed — that property is
K4's, it is unrefined, and `test_bare.py` still owns it. What Q14 refines is the **store's** answer to that
rejection, which needs the governed manifest and therefore lives in `store.py`. A test that drives `repo.push()`
directly is testing K4 and will never see K9.

*Trap 2: the fixture's store is a fresh clone.* `conftest.store_on_disk` clones the bare origin per call, which
models the restarted container. So a test that wants a *running* store to see a remote move has to move the remote
under a store it already holds, never by opening a second one.

*Trap 3: an ungoverned path is not merely a path outside `docs/work/`.* `Store.is_governed_repo_path` asks the
tenant's own manifest, so `docs/work/notes.txt` is ungoverned and `docs/work/cards/0009-x.md` is governed. The tests
below use both, because a check written against the root prefix alone would pass the first and fail the second.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from isidium.store.core import telemetry
from isidium.store.core.grammar import Document
from isidium.store.core.refusal import Refusal
from isidium.store.server import gitrepo
from isidium.store.server.gitrepo import GitCli, MemGit, blob_id
from isidium.store.server.store import NewCard, Store

from .conftest import BASE_SCOPE, OWNER, PLANNER, Telemetry, base_head, git, store_on_disk, tenant_checkout

ROOT = "docs/work/"


@pytest.fixture
def store(tmp_path: Path) -> Store:
    tenant_checkout(tmp_path)
    st = store_on_disk(tmp_path / "tenant", tmp_path / "journal.sqlite", root=ROOT)
    st.init(OWNER, software_key_ack="ok for K9", root=ROOT)
    return st


def stranger_pushes(tmp_path: Path, rel: str, body: bytes) -> str:
    """A second writer lands one commit on the origin's `main`, behind the store's back. Returns the new tip.

    This is what a merged pull request looks like from the store's side, and — when `rel` is governed — what a
    bypass looks like. The store is not told, which is the whole condition under test.
    """
    work = tmp_path / f"other-{abs(hash(rel)) % 10000}"
    git(tmp_path, "clone", "-q", str(tmp_path / "origin.git"), str(work))
    git(work, "config", "user.name", "stranger")
    git(work, "config", "user.email", "stranger@example")
    (work / rel).parent.mkdir(parents=True, exist_ok=True)
    (work / rel).write_bytes(body)
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", f"a second writer touched {rel}")
    git(work, "push", "-q", "origin", "HEAD:main")
    return git(tmp_path / "origin.git", "rev-parse", "main").strip()


def draft(st: Store, slug: str) -> str:
    """One governed write through the store's own front door. Returns its commit."""
    r = st.write(NewCard(slug), Document(base_head(0, "draft"), {"Scope": BASE_SCOPE}), None, None, PLANNER)
    return r.commit


# ---- (a): the fetch and the fast-forward before every write --------------------------------------------------------


def test_a_write_after_an_ungoverned_merge_lands_on_the_new_tip_without_a_restart(store: Store, tmp_path: Path) -> None:
    """**The chunk, in one test.** A merged pull request moves `main` under a running store, and the store's next
    governed write lands anyway — on the merged tip, with no restart and no journal replay.

    Three discriminators, because "the write did not raise" is satisfied by a store that never noticed anything:

    * the new commit's **parent is the stranger's tip**, so it was built on what the remote holds and not on the
      base this store cloned with;
    * the store's own ref **equals the origin's `main`** afterwards, so the push landed rather than being swallowed;
    * the ungoverned file the stranger added is **still in the store's tree**, which is what says the fast-forward
      carried the merge forward instead of reverting it. Without dropping the cached tree in `fast_forward`, the
      store would commit its stale tree and this file would vanish from `main` — a silent revert of somebody's
      merged pull request, and the reason this assertion is here rather than only in the mutation set;
    * **one push, not two** — and this is the one that can see (a) at all. Without the fast-forward the write still
      lands, because (b) catches the rejected push and rebuilds on the same tip: every assertion above stays true
      and the mutation that deletes (a) **survives**. It did, on its first run. What (a) buys is the round trip
      that never happens, so the count is the property, and this is what makes (a) tested rather than merely
      present.
    """
    repo = store.repo
    assert isinstance(repo, GitCli)
    tip = stranger_pushes(tmp_path, "docs/dev/notes.md", b"merged through a pull request\n")
    assert repo.head != tip, "the fixture's premise: the running store has not seen the merge"

    pushes: list[int] = []
    original = GitCli.push

    def counted(self: GitCli) -> None:
        pushes.append(1)
        original(self)

    GitCli.push = counted  # type: ignore[method-assign]
    try:
        sha = draft(store, "after-a-merge")
    finally:
        GitCli.push = original  # type: ignore[method-assign]

    assert repo.parents(sha) == [tip], "the write was built on the store's stale base, not on the merged tip"
    assert git(tmp_path / "origin.git", "rev-parse", "main").strip() == sha, "the push did not land"
    assert repo.head == sha
    assert "docs/dev/notes.md" in repo.paths(), "the store's commit reverted the merged pull request"
    assert len(pushes) == 1, f"the write cost {len(pushes)} pushes; with the fast-forward it costs one"


def test_the_fast_forward_is_one_fetch_and_the_ordinary_write_pays_only_that(store: Store) -> None:
    """The steady state: when the remote has not moved, the sync is a fetch and nothing else.

    The discriminator is the ref, not the absence of an error: after a write with no concurrent writer the store's
    head is its own new commit and `merge-base` was never consulted, which is what the second half asserts by
    counting the fast-forwards rather than by timing anything. A store that fast-forwarded on every write would
    still pass every other test in this file.
    """
    repo = store.repo
    assert isinstance(repo, GitCli)
    moves: list[str] = []
    original = GitCli.fast_forward

    def recorded(self: GitCli, to: str) -> bool:
        moves.append(to)
        return original(self, to)

    GitCli.fast_forward = recorded  # type: ignore[method-assign]
    try:
        first = draft(store, "quiet-one")
        second = draft(store, "quiet-two")
    finally:
        GitCli.fast_forward = original  # type: ignore[method-assign]
    assert repo.parents(second) == [first]
    assert moves == [], "the store fast-forwarded onto a remote that had not moved"


def test_a_tree_cached_before_the_fast_forward_does_not_survive_it(store: Store, tmp_path: Path) -> None:
    """**The fast-forward drops the cached tree, and this is the sequence where that matters.**

    `GitCli` caches `HEAD`'s tree and `commit` builds the next one from it. Move the ref without dropping the cache
    and the store commits *the tree it cached at the old base* — which silently reverts every ungoverned path the
    merged pull request changed, on `main`, under the store's own signature. Nothing about the write looks wrong.

    **Why this needs its own test, and what it cost to learn.** The mutation that removes the invalidation
    **survived** its first run: in every other test here the cache happens to be cold when the write starts, because
    the previous commit cleared it and nothing read the repository in between, so `_tree()` re-reads the tip anyway
    and the mutant behaves identically. That is a mutation the suite could not *see*, not a property the code did
    not have. `Store.load` walks `repo.paths()` and so does a reload, so a warm cache at the start of a write is an
    ordinary state, not a contrived one — this test puts the store in it on purpose.
    """
    repo = store.repo
    assert isinstance(repo, GitCli)
    tip = stranger_pushes(tmp_path, "docs/dev/warm.md", b"merged while the store held a tree\n")
    assert "docs/dev/warm.md" not in repo.paths(), "warming the cache at the stale base — the state under test"

    sha = draft(store, "warm-cache")

    assert repo.parents(sha) == [tip]
    assert "docs/dev/warm.md" in repo.paths(), "the commit was built on the tree cached before the fast-forward"
    assert git(tmp_path / "origin.git", "rev-parse", "main").strip() == sha


def test_a_write_after_a_governed_change_on_the_remote_is_refused_and_the_ref_does_not_move(
    store: Store, tmp_path: Path
) -> None:
    """**K4's rule, unrefined.** A remote that moved *with a governed change* is a second writer of governed paths,
    and that is still a refusal — the id K4 chose, and the store's own ref left where it was.

    This is the case Q14 explicitly does not touch, so the assertions are the strong ones: the rule id, the store's
    ref unmoved, and the origin's `main` still the stranger's commit. A rebuild here would have carried the store's
    in-memory view of a document the stranger had just rewritten straight back over it.
    """
    repo = store.repo
    assert isinstance(repo, GitCli)
    before = repo.head
    tip = stranger_pushes(tmp_path, f"{ROOT}cards/0009-bypass.md", b"# a bypass\n")

    with pytest.raises(Refusal) as ei:
        draft(store, "against-a-bypass")

    assert ei.value.rule == "git.push-rejected"
    assert repo.head == before, "the store's ref moved across a governed change on the remote"
    assert git(tmp_path / "origin.git", "rev-parse", "main").strip() == tip, "the store wrote over a second writer"


def test_an_ungoverned_path_inside_the_tracking_root_is_still_ungoverned(store: Store, tmp_path: Path) -> None:
    """The manifest decides, not the root prefix (trap 3). `docs/work/notes.txt` sits **inside** the tracking root
    and is not a governed path, so a merge that touches it is fast-forwarded like any other.

    Without this the check could be written as `repo_path.startswith(self.root)` — which passes every other test in
    this file, refuses a write the ruling says must land, and would only be found by a tenant that keeps a README
    beside its cards.
    """
    repo = store.repo
    assert isinstance(repo, GitCli)
    tip = stranger_pushes(tmp_path, f"{ROOT}notes.txt", b"not a governed document\n")
    sha = draft(store, "beside-the-cards")
    assert repo.parents(sha) == [tip]
    assert git(tmp_path / "origin.git", "rev-parse", "main").strip() == sha


# ---- (b): the one bounded rebuild on a rejected push ----------------------------------------------------------------


def test_a_merge_between_the_fetch_and_the_push_is_rebuilt_once_and_lands(store: Store, tmp_path: Path) -> None:
    """**The race (a) cannot close, made deterministic.** A pull request merges *after* the store has fetched and
    *before* it pushes; the push is rejected; the store fetches again, finds nothing governed moved, rebuilds its
    one commit on the new tip and pushes once.

    The window is microseconds wide in life, so it is held open on purpose: `push` is wrapped to land the
    stranger's commit the first time it is called, which is exactly the instant the real race occupies. The
    discriminator is the parent — the landed commit's parent is the commit that raced it, which is only true if
    the store re-derived rather than retried — plus the count, which says the store pushed twice and not in a loop.
    """
    repo = store.repo
    assert isinstance(repo, GitCli)
    raced: list[str] = []
    original = GitCli.push

    def push_after_a_merge(self: GitCli) -> None:
        if not raced:
            raced.append(stranger_pushes(tmp_path, "docs/dev/raced.md", b"merged mid-write\n"))
        original(self)

    GitCli.push = push_after_a_merge  # type: ignore[method-assign]
    try:
        sha = draft(store, "raced")
    finally:
        GitCli.push = original  # type: ignore[method-assign]

    assert len(raced) == 1
    assert repo.parents(sha) == [raced[0]], "the store did not rebuild on the commit that raced it"
    assert git(tmp_path / "origin.git", "rev-parse", "main").strip() == sha
    assert "docs/dev/raced.md" in repo.paths(), "the rebuild reverted the commit it rebuilt onto"


def test_a_governed_change_that_arrives_in_the_race_is_not_landed_and_never_rebuilt(
    store: Store, tmp_path: Path, otel: Telemetry
) -> None:
    """The same race, with the one thing that must stop it: the commit that landed touched a governed path.

    The discriminator is the origin — a rebuild would have put the store's commit on top of the bypass, which is
    the silent outcome K4's rule exists to prevent — and the rule id, `git.push-rejected`, which the operator sees
    on the unlanded counter rather than a new id for the same condition seen one step later.

    **What the caller gets changed with Q18** [K7b, ruled 2026-09-06]. The row was journaled before the push, so
    the act happened; the write answers its result with `landed = False` instead of a refusal, memory holds the
    card, and the store's own ref is left where it was. The condition is then reported where it bites: the *next*
    write is refused `git.push-rejected` at the sync, before any row, because a governed path moved on the remote —
    the second-writer condition K4 ruled must be reported, now a standing one an operator has to resolve.
    """
    repo = store.repo
    assert isinstance(repo, GitCli)
    raced: list[str] = []
    original = GitCli.push
    before = otel.count("isidium.store.write.unlanded", **{telemetry.RULE: "git.push-rejected"})

    def push_after_a_bypass(self: GitCli) -> None:
        if not raced:
            raced.append(stranger_pushes(tmp_path, f"{ROOT}cards/0009-raced-bypass.md", b"# a bypass\n"))
        original(self)

    GitCli.push = push_after_a_bypass  # type: ignore[method-assign]
    try:
        r = store.write(
            NewCard("raced-by-a-bypass"), Document(base_head(0, "draft"), {"Scope": BASE_SCOPE}), None, None, PLANNER
        )
    finally:
        GitCli.push = original  # type: ignore[method-assign]

    assert r.landed is False and r.id is not None and store.path_of(r.id) == r.path
    assert otel.count("isidium.store.write.unlanded", **{telemetry.RULE: "git.push-rejected"}) == before + 1
    assert git(tmp_path / "origin.git", "rev-parse", "main").strip() == raced[0], "the store wrote over a bypass"
    assert repo.head == r.commit, "the store's own commit was rebuilt or dropped"
    with pytest.raises(Refusal) as ei:
        draft(store, "after-the-race")
    assert ei.value.rule == "git.push-rejected" and "0009-raced-bypass" in ei.value.detail


def test_the_walk_reaches_every_commit_the_store_is_behind_and_not_only_the_tip(store: Store, tmp_path: Path) -> None:
    """**The walk is a walk.** The store is two commits behind: the older one touched a governed path, the newer one
    did not. Asking only the tip's own diff — which is what a `touched(tip)` written in place of the walk does —
    reads *ungoverned* and fast-forwards straight over a bypass.

    This is the case the ruling's precondition is actually about, and no other test in this file can see it: every
    other one moves the remote by a single commit, where the tip's diff and the walk's union are the same set.
    """
    repo = store.repo
    assert isinstance(repo, GitCli)
    before = repo.head
    stranger_pushes(tmp_path, f"{ROOT}cards/0005-older-bypass.md", b"# an older bypass\n")
    tip = stranger_pushes(tmp_path, "docs/dev/newer.md", b"and an ungoverned commit on top\n")

    with pytest.raises(Refusal) as ei:
        draft(store, "two-behind")

    assert ei.value.rule == "git.push-rejected"
    assert repo.head == before, "the store fast-forwarded over a governed change one commit down"
    assert git(tmp_path / "origin.git", "rev-parse", "main").strip() == tip


def test_a_second_rejection_after_the_rebuild_is_the_refusal_and_not_another_round(
    store: Store, tmp_path: Path
) -> None:
    """**The retry is bounded at one, and this is the test that can see the bound.** A commit lands before the
    store's first push *and* before its rebuilt second one, so the rebuild is rejected too. The answer is the
    refusal, not a third attempt.

    The discriminator is the pair: exactly two pushes were attempted, and the caller was told the write did not
    land [K7b, Q18: the result with `landed = False`, where K9 refused — the row is journaled, so the act happened].
    A retry loop passes the second half by exhausting itself quietly and then returning as though the write had
    landed — which is the worse failure, because the journal row is marked applied and `main` never received the
    commit; here the row stays pending and the counter says so.
    """
    repo = store.repo
    assert isinstance(repo, GitCli)
    landed: list[str] = []
    attempts: list[int] = []
    original = GitCli.push

    def push_into_a_moving_remote(self: GitCli) -> None:
        attempts.append(1)
        if len(landed) < 2:
            landed.append(stranger_pushes(tmp_path, f"docs/dev/race-{len(landed)}.md", b"another merge\n"))
        original(self)

    GitCli.push = push_into_a_moving_remote  # type: ignore[method-assign]
    try:
        r = store.write(
            NewCard("raced-twice"), Document(base_head(0, "draft"), {"Scope": BASE_SCOPE}), None, None, PLANNER
        )
    finally:
        GitCli.push = original  # type: ignore[method-assign]

    assert r.landed is False
    assert len(attempts) == 2, f"the store pushed {len(attempts)} times; the rebuild is one round, not a loop"
    assert git(tmp_path / "origin.git", "rev-parse", "main").strip() == landed[-1]
    assert [s for s, _p, _d in store.journal.pending_rows()] == [r.journal_seq], "the unlanded row is not pending"


def test_the_rebuild_refuses_when_the_store_carries_more_than_its_own_one_commit(store: Store, tmp_path: Path) -> None:
    """**The bound on the retry, and the reason it is a bound and not a loop.** The store is made to carry an
    unpushed commit of its own — the state a governed refusal leaves behind — and then a merge lands. Rebuilding
    the newest commit alone would drop the older one, so the rebuild refuses instead.

    The discriminator is the older commit: it is still reachable from the store's own ref afterwards. A rebuild
    that ignored the bound would have replaced it with a commit built on the remote's tip, and the only evidence
    would be a card that quietly stopped existing.
    """
    repo = store.repo
    assert isinstance(repo, GitCli)
    # an unpushed commit of the store's own, made behind the push so it cannot reach the origin
    quiet = GitCli(repo.gitdir, "isidium-store", "store@sartor", push=False, root=ROOT)
    orphan = quiet.commit({f"{ROOT}cards/0008-unpushed.md": b"# unpushed\n"}, "s@e", store.now(), "never pushed")
    stranger_pushes(tmp_path, "docs/dev/late.md", b"a merge arrives\n")

    # journaled, so answered with `landed = False` rather than refused [K7b, Q18]; the bound is what is under test
    r = store.write(
        NewCard("with-history-in-hand"), Document(base_head(0, "draft"), {"Scope": BASE_SCOPE}), None, None, PLANNER
    )
    assert r.landed is False
    assert orphan in git(repo.gitdir, "rev-list", "HEAD"), "the store dropped an unpushed commit of its own"


# ---- the two failures that must be typed rather than tracebacks -----------------------------------------------------


def test_a_fetch_that_cannot_reach_the_origin_is_a_typed_refusal(store: Store, tmp_path: Path) -> None:
    """An unreachable origin refuses with a rule id of its own, before the journal row and before the commit.

    `git.fetch-failed` rather than `git.failed`: the store's answer is not *"git broke"* but *"I cannot establish
    that I am writing on the current tip"*, and the two want different things from whoever reads the log. The
    second assertion is the one that matters operationally — the store's ref has not moved, so nothing was
    committed against a base it could not check.
    """
    repo = store.repo
    assert isinstance(repo, GitCli)
    before = repo.head
    git(repo.gitdir, "config", "remote.origin.url", str(tmp_path / "no-such-origin.git"))

    with pytest.raises(Refusal) as ei:
        draft(store, "with-no-origin")

    assert ei.value.rule == "git.fetch-failed"
    assert repo.head == before, "the store committed against a base it could not verify"


def test_a_fast_forward_whose_compare_and_swap_loses_is_refused(store: Store, tmp_path: Path) -> None:
    """Two writers over one clone — a restarted container beside a still-running one — racing the fast-forward
    itself. The swap names the value this writer held, so the loser is refused rather than overwriting the winner.

    Held open the way `test_bare.py` holds the commit's own swap open: `head` is pinned to the value this writer
    read, which is the window a real second writer would land in.
    """
    repo = store.repo
    assert isinstance(repo, GitCli)
    tip = stranger_pushes(tmp_path, "docs/dev/ff.md", b"a merge\n")
    # the fetch first, as the write path does it: `fast_forward` asks git a reachability question about `tip`,
    # and a clone that has not fetched it cannot answer. Written the other way round this test passed on the
    # unanswerable question rather than on the swap it names — which is why `_git_ok` now raises on one.
    assert repo.fetch() == tip
    stale = repo.head
    assert stale is not None and stale != tip

    other = GitCli(repo.gitdir, "isidium-store", "store@sartor", push=False, root=ROOT)
    moved = other.commit({f"{ROOT}cards/0007-other.md": b"# other\n"}, "o@e", store.now(), "the other writer")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(GitCli, "head", property(lambda _self: stale))
        with pytest.raises(Refusal) as ei:
            repo.fast_forward(tip)
    assert ei.value.rule == "git.ref-moved"
    assert git(repo.gitdir, "rev-parse", "HEAD").strip() == moved, "the swap was attempted but not compared"


def test_a_ref_that_has_diverged_is_never_reset_by_the_fast_forward(store: Store, tmp_path: Path) -> None:
    """`fast_forward` is a fast-forward and not a reset: a ref holding a commit the tip does not have stays put.

    This is what stops (a) from being the way an unpushed commit is lost. The positive discriminator is the pair —
    the diverged ref declines and returns `False`, and the same store fast-forwards onto a tip it *is* behind — so
    a `fast_forward` that always declined could not pass.
    """
    repo = store.repo
    assert isinstance(repo, GitCli)
    quiet = GitCli(repo.gitdir, "isidium-store", "store@sartor", push=False, root=ROOT)
    orphan = quiet.commit({f"{ROOT}cards/0006-orphan.md": b"# orphan\n"}, "s@e", store.now(), "unpushed")
    tip = stranger_pushes(tmp_path, "docs/dev/div.md", b"a merge\n")
    assert repo.fetch() == tip  # as the write path does it — the sibling test above says why this line matters

    assert repo.fast_forward(tip) is False, "a diverged ref was reset onto the remote"
    assert repo.head == orphan

    # the other half of the discriminator: the same method does move a ref that is merely behind
    behind = GitCli(repo.gitdir, "isidium-store", "store@sartor", push=False, root=ROOT)
    git(repo.gitdir, "update-ref", "refs/heads/main", git(repo.gitdir, "rev-parse", f"{orphan}^").strip())
    assert behind.fast_forward(tip) is True
    assert behind.head == tip


# ---- K4's two properties, re-proven because K9 is the chunk that could take them away --------------------------------


def test_the_store_holds_no_force_path_at_all() -> None:
    """**K4's rule, swept over the source rather than inferred from behaviour.** `--force-with-lease` was measured
    destroying a concurrent writer's commit where a plain push was rejected, so a store must hold no force path at
    any level — not on the push K9 wraps, not on the fetch it adds, not on the ref update it swaps.

    A behavioural test can only see the paths it drives; this sees every line of the class, which is what makes it
    the guard against a force added on a path no test reaches. `+` is swept because a leading `+` on a refspec is
    git's other spelling of `--force`, and it is the one a reviewer's eye slides over.
    """
    source = Path(gitrepo.__file__).read_text(encoding="utf-8")
    lines = [
        ln.strip()
        for ln in source.splitlines()
        if not ln.strip().startswith("#") and ("--force" in ln or '"+' in ln or "'+" in ln)
    ]
    # the docstrings that explain why there is no force path are prose, not a call: only executable lines count
    calls = [ln for ln in lines if "self._git(" in ln or "subprocess.run(" in ln or '"push"' in ln]
    assert calls == [], f"a force path in the store's git: {calls}"
    assert "--force" in source, "the sweep found no mention of force at all — the docstrings that explain it are gone"


def test_the_double_refuses_a_fast_forward_rather_than_pretending_to_have_a_remote() -> None:
    """`MemGit.fetch` answers `None` — *no remote to re-read* — so the store skips the sync entirely and the 220
    conformance scenarios keep their meaning. `fast_forward` is unreachable through that path and says so rather
    than moving a head it never checked."""
    double = MemGit()
    assert double.fetch() is None
    with pytest.raises(Refusal) as ei:
        double.fast_forward("0" * 40)
    assert ei.value.rule == "git.unsupported"


def test_the_fetch_keeps_the_clone_blob_less(store: Store, tmp_path: Path) -> None:
    """**C-8 and the footprint together.** (a) adds one fetch per write, and the fetch must stay filtered: a fetch
    that pulled every blob would make the store's footprint a claim again, silently, on the ordinary path.

    Measured rather than reasoned: the clone's `partialclonefilter` is what makes the fetch blob-less, and it is
    config a future edit could drop. The discriminator is that the *commit and tree* arrive — so the fetch really
    happened — while the blob for the stranger's file does not.
    """
    repo = store.repo
    assert isinstance(repo, GitCli)
    body = b"x = 1\n" * 100
    tip = stranger_pushes(tmp_path, "src/big.py", body)
    assert repo.fetch() == tip

    # **Counted, never inferred from `rev-list --all`** — which walks *refs*, and a fetched tip is behind no ref in
    # this clone at all (`git clone --bare` writes no fetch refspec, so there is no `refs/remotes/origin/main`).
    # `--batch-all-objects --batch-check` lists what the object store holds without resolving anything, which is
    # `test_bare.py`'s trap 2: `cat-file <oid>` would fetch the very blob whose absence is the assertion.
    listed = subprocess.run(
        ["git", "cat-file", "--batch-all-objects", "--batch-check"],
        cwd=repo.gitdir,
        capture_output=True,
        check=True,
        text=True,
        env={**os.environ, "GIT_NO_LAZY_FETCH": "1"},
    ).stdout
    held = {ln.split()[0] for ln in listed.splitlines() if ln.strip() and not ln.startswith("warning")}
    assert tip in held, "the fetched commit is not in the object store — the fetch did nothing"
    assert blob_id(body, repo.object_format) not in held, "the fetch pulled a blob the footprint excludes"
