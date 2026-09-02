"""The tenant repository as the store holds it (03 §1.3, 03b §2): a **partial bare clone** — the commit graph and
the trees, with blob content for governed paths only, and no working tree, no index, no code, no media (7bg.8).
Every governed write is one commit on `main` — author = the caller, committer = the store identity — and one push.

Two implementations of one protocol: `GitCli` (the real thing: git via subprocess, built from plumbing) and `MemGit`
(an in-memory double with the same first-parent semantics, kept from the r6 prototype, for the conformance
scenarios). Blob ids are computed locally under the repo's object format (`[toolkit] object_id`) — no subprocess.

**What K4 changed and why it is not cosmetic.** The working tree was the governed copy, so a read was a file read
and a write was `add` + `commit --only`. Under a bare clone there is no working tree to read, no index to stage
into, and — because `--filter=blob:none` is lazy rather than restrictive — no guarantee at all that the footprint
holds unless the store refuses the fetch itself. `GIT_NO_LAZY_FETCH=1` on every invocation is that refusal, and
`git.outside-footprint` is what it says out loud.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
import weakref
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from functools import cached_property
from pathlib import Path
from typing import Protocol

from ..core.refusal import Refusal

Changes = Mapping[str, bytes | None]  # path -> new bytes, or None for a deletion


def blob_id(data: bytes, object_format: str = "sha1") -> str:
    """git's object id of a blob: `sha(b"blob <len>\\0" + data)` under the repo's object format."""
    h = hashlib.sha1(usedforsecurity=False) if object_format == "sha1" else hashlib.sha256()
    h.update(b"blob " + str(len(data)).encode() + b"\0" + data)
    return h.hexdigest()


class Repo(Protocol):
    object_format: str

    @property
    def head(self) -> str | None: ...
    def read(self, path: str, sha: str | None = None) -> bytes | None: ...
    # The blob id at a path **without reading the blob** — the tree already holds it. Added by K4 because Q11 makes
    # it the only thing the store may ask about a path outside the governed set, and `read` cannot answer it under
    # a footprint that holds no such content.
    def oid_of(self, path: str, sha: str | None = None) -> str | None: ...
    def blob(self, oid: str) -> bytes: ...
    def commit(self, changes: Changes, author: str, at: str, message: str, parents: list[str] | None = None) -> str: ...
    def push(self) -> None: ...
    def parents(self, sha: str) -> list[str]: ...
    def commit_time(self, sha: str) -> str: ...
    def touched(self, sha: str) -> dict[str, tuple[str | None, str | None]]: ...
    def first_parent_walk(self, since: str | None, until: str | None = None) -> list[str]: ...
    def paths(self) -> list[str]: ...


# ---- the in-memory double ---------------------------------------------------------------------------------------


@dataclass
class Commit:
    sha: str
    parents: list[str]
    tree: dict[str, str]  # path -> blob id
    author: str
    committer: str
    at: str
    message: str = ""


@dataclass
class MemGit:
    """An in-memory git: blobs by object id, commits with first-parent order. Enough for the per-commit
    reconciliation (9.6), the gates' recompute (parent-blob → commit-blob) and the X2 merge observation."""

    object_format: str = "sha1"
    identity: str = "store@memgit"
    blobs: dict[str, bytes] = field(default_factory=dict)
    commits: dict[str, Commit] = field(default_factory=dict)
    _head: str | None = None
    pushed: int = 0

    @property
    def head(self) -> str | None:
        return self._head

    @head.setter
    def head(self, sha: str | None) -> None:
        self._head = sha

    def tree(self, sha: str | None) -> dict[str, str]:
        return dict(self.commits[sha].tree) if sha else {}

    def commit(self, changes: Changes, author: str, at: str, message: str, parents: list[str] | None = None) -> str:
        parents = parents if parents is not None else ([self._head] if self._head else [])
        tree = self.tree(parents[0]) if parents else {}
        for path, data in changes.items():
            if data is None:
                tree.pop(path, None)
            else:
                b = blob_id(data, self.object_format)
                self.blobs[b] = data
                tree[path] = b
        payload = "\n".join(
            [",".join(parents), author, self.identity, at, message] + [f"{p} {b}" for p, b in sorted(tree.items())]
        )
        sha = hashlib.sha1(payload.encode("utf-8"), usedforsecurity=False).hexdigest()
        self.commits[sha] = Commit(sha, parents, tree, author, self.identity, at, message)
        self._head = sha
        return sha

    def push(self) -> None:
        self.pushed += 1

    def read(self, path: str, sha: str | None = None) -> bytes | None:
        b = self.tree(sha or self._head).get(path)
        return self.blobs[b] if b else None

    def oid_of(self, path: str, sha: str | None = None) -> str | None:
        """The double's tree is already `path -> blob id`, so this is the lookup `GitCli` spends an `ls-tree` on."""
        return self.tree(sha or self._head).get(path)

    def blob(self, oid: str) -> bytes:
        return self.blobs[oid]

    def parents(self, sha: str) -> list[str]:
        return list(self.commits[sha].parents)

    def commit_time(self, sha: str) -> str:
        return self.commits[sha].at

    def first_parent_walk(self, since: str | None, until: str | None = None) -> list[str]:
        """Commits on the first-parent line after `since` up to `until` (head), oldest first."""
        out: list[str] = []
        cur = until or self._head
        while cur and cur != since:
            out.append(cur)
            c = self.commits[cur]
            cur = c.parents[0] if c.parents else None
        return list(reversed(out))

    def paths(self) -> list[str]:
        return sorted(self.tree(self._head))

    def touched(self, sha: str) -> dict[str, tuple[str | None, str | None]]:
        c = self.commits[sha]
        parent = self.tree(c.parents[0]) if c.parents else {}
        paths = set(parent) | set(c.tree)
        return {p: (parent.get(p), c.tree.get(p)) for p in sorted(paths) if parent.get(p) != c.tree.get(p)}


# ---- git via subprocess ----------------------------------------------------------------------------------------


class Footprint(Enum):
    """Which of S-9's two clones is running — a typed value with one meaning, never a formatted string (C-2).

    `FILTERED` is the ruled shape (7bg.8): `--filter=blob:none` was accepted, so the clone holds the commit graph and
    the trees and holds no blob it was not asked for. `FULL` is S-9's **declared degradation**: a forge that refuses
    the filter yields a full bare clone — the footprint grows to the history's blobs, but there is still no working
    tree and no index, so the working-tree class of defect stays impossible either way.
    """

    FILTERED = "filtered"
    FULL = "full"


def _terminate(p: subprocess.Popen[bytes]) -> None:
    """Shut the batch process down. Module-level, taking the process as an argument, because `weakref.finalize` must
    not hold a reference to the object it finalizes."""
    if p.poll() is not None:
        return
    try:
        if p.stdin is not None:
            p.stdin.close()
        p.wait(timeout=5)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        p.kill()


class _CatFileBatch:
    """One long-lived `git cat-file --batch`, which is the shape K4's done-when 6 names.

    Everywhere else `GitCli` runs one subprocess per call, and everywhere else that is a handful per write. Reads are
    different: `store.py`'s load walks every governed path, so one spawn per read turns N cheap reads into N process
    spawns. **Measured 2026-08-31 on this workstation** — 40 reads of a bare clone, medians of 5 runs — one
    subprocess per read is **13129 ms (328 ms per read)** against **593 ms (14.8 ms per read)** through one batch
    process: **22x**, and the ratio is the file count on any machine, only the constant changes. This is C-8 landing
    on the chunk that touches it, before the first slow run rather than after.

    **A long-lived batch process sees objects written after it started** — verified 2026-08-31, including across a
    `git gc` — so a write does not have to restart it, and `commit` does not.
    """

    def __init__(self, gitdir: Path, env: Mapping[str, str]) -> None:
        self._p: subprocess.Popen[bytes] = subprocess.Popen(
            ["git", "cat-file", "--batch"],
            cwd=gitdir,
            env=dict(env),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        self._finalize = weakref.finalize(self, _terminate, self._p)

    def read(self, spec: str) -> bytes | None:
        """The object's bytes, or `None` when git answers `missing`.

        **`missing` conflates two conditions** — the spec names nothing, and the blob is absent from a partial clone
        — measured 2026-08-31: `--batch` prints `<spec> missing` for both. `GitCli` therefore disambiguates on the
        miss path, where the cost is paid only by the exception, rather than here."""
        p = self._p
        if p.stdin is None or p.stdout is None or p.poll() is not None:
            raise Refusal("git.failed", "cat-file", "the batch reader is not running")
        p.stdin.write(spec.encode("utf-8") + b"\n")
        p.stdin.flush()
        header = p.stdout.readline().decode("utf-8", "replace").strip()
        if header.endswith(" missing"):
            return None
        parts = header.split()
        if len(parts) != 3:
            raise Refusal("git.failed", "cat-file", f"unreadable batch header {header[:60]!r}")
        body: bytes = p.stdout.read(int(parts[2]))
        p.stdout.read(1)  # the newline git writes after every object
        return body

    def close(self) -> None:
        self._finalize()


class GitCli:
    """The tenant repository as the store holds it: a **partial bare clone** — the commit graph and the trees, with
    blob content for governed paths only. No working tree, no index, no code, no media (7bg.8, pinned in 03 §1.3).

    Every write is built with plumbing — `hash-object` → a temporary index → `write-tree` → `commit-tree` →
    `update-ref` **with the expected old value as the compare-and-swap** — and pushed once. There is no working tree
    to `add` from and none to rebase onto, so a rejected push is a refusal rather than a retry.

    **The footprint is enforced, not assumed** [Q3, ruled 2026-08-29]. `--filter=blob:none` makes a clone *lazy, not
    restricted*: a blob is absent until something asks, and then git fetches it from the promisor remote,
    transparently and **permanently** — measured, an ordinary `cat-file` of a non-governed path pulled a code blob
    in and kept it. So every git this class runs carries `GIT_NO_LAZY_FETCH=1`, which turns that read into a
    refusal, and `git.outside-footprint` is what a caller gets instead of git's own words about a promisor.
    """

    def __init__(
        self,
        gitdir: str | Path,
        identity_name: str,
        identity_email: str,
        remote: str = "origin",
        branch: str = "main",
        push: bool = True,
        root: str = "",
    ) -> None:
        self.gitdir = Path(gitdir)
        self.identity_name, self.identity_email = identity_name, identity_email
        self.remote, self.branch, self.do_push = remote, branch, push
        # **The tracking root is the footprint's boundary, and this class is where it becomes structural.** Governed
        # documents live under it; a card's `refs` are refused *inside* it (03 §1.14) and a `surfaces` glob that
        # reaches it is refused too — so "under the root" and "content the store may hold" are the same set, stated
        # once. `read` hydrates under it and refuses outside it, which is what makes *no code, no media, ever* a
        # property of this class rather than of every present and future call site.
        self.root = root
        # **The one setting this whole class exists to carry** (Q3). It is on the environment rather than on each
        # command because a single invocation that forgets it re-opens the hole permanently: the blob it fetches
        # stays. `os.environ` is copied once here rather than read per call.
        self._env: dict[str, str] = {**os.environ, "GIT_NO_LAZY_FETCH": "1"}
        # The same environment **without** the guard — the one named door through which a blob may be fetched from
        # the promisor remote, reached only from `_hydrate` and only for content inside the root.
        self._fetch_env: dict[str, str] = {k: v for k, v in self._env.items() if k != "GIT_NO_LAZY_FETCH"}
        self._batch: _CatFileBatch | None = None
        self._tree_cache: dict[str, tuple[str, str]] | None = None  # path -> (mode, oid)
        # Oids this instance has itself resolved from a path **inside the root**. `blob` may hydrate one of these and
        # nothing else, which is what stops `oid_of` — which is deliberately ungated, because a card's `refs` point
        # outside the root by definition (Q11) — from being the way a code blob is named and then pulled in.
        self._vouched: set[str] = set()
        self.object_format = self._git("rev-parse", "--show-object-format").strip() or "sha1"

    # ---- construction (S-9) --------------------------------------------------------------------------------------

    @classmethod
    def clone(
        cls,
        source: str | Path,
        into: str | Path,
        identity_name: str,
        identity_email: str,
        remote: str = "origin",
        branch: str = "main",
        push: bool = True,
        root: str = "",
    ) -> GitCli:
        """`git clone --bare --filter=blob:none`, with S-9's fallback to a full bare clone.

        **A local *path* source is converted to a `file://` URL** — `--filter` is *ignored outright* for path clones
        (`warning: --filter is ignored in local clones; use file:// instead.`, measured 2026-08-29 and again
        2026-08-31), and a path clone also hardlinks the remote's objects, which is not a footprint at all. Silently
        taking a full clone is the failure this conversion removes permanently, for the deployment as much as for
        the tests; `footprint` still reports what happened rather than what was asked for.

        There is no filter *detection* before the fact and there cannot be: a refused filter is indistinguishable
        from an accepted one in the clone's config — both write `promisor=true` and `partialclonefilter=blob:none`
        (S-9's first trap). The clone is attempted with the filter and `footprint` counts objects afterwards.
        """
        src = Path(source)
        url = src.resolve().as_uri() if src.is_dir() else str(source)
        r = subprocess.run(
            ["git", "clone", "--bare", "--filter=blob:none", "-b", branch, url, str(into)],
            capture_output=True,
            check=False,
            env={**os.environ, "GIT_NO_LAZY_FETCH": "1"},
        )
        if r.returncode != 0:
            raise Refusal("git.failed", "clone", r.stderr.decode("utf-8", "replace").strip()[:300])
        return cls(into, identity_name, identity_email, remote, branch, push, root)

    @cached_property
    def footprint(self) -> Footprint:
        """Which of S-9's two clones this is — **counted, never read off the config**.

        S-9's first trap is that the config cannot tell you: a refused filter and an accepted one both leave
        `promisor=true` and `partialclonefilter=blob:none` behind. The only honest signals are a warning on stderr at
        clone time, which is long gone by the time anyone asks, and **the actual absence of blob objects**.

        `--missing=print` answers it directly: a promisor clone prints every absent object with a `?` prefix and a
        full clone prints none (measured 2026-08-31, both shapes). It walks the object graph, so it is a
        `cached_property` — asked once, when a deployment wants the report, never on a call path. **C-13's answer
        here is lazy** precisely because a store that never asks should never pay for the walk.
        """
        for line in self._git("rev-list", "--objects", "--all", "--missing=print").splitlines():
            if line.startswith("?"):
                return Footprint.FILTERED
        return Footprint.FULL

    # ---- the subprocess seam -------------------------------------------------------------------------------------

    def _git(self, *args: str, data: bytes | None = None) -> str:
        return self._run(list(args), data=data, env=self._env, rule_path=" ".join(args[:2]))

    def _run(self, args: list[str], data: bytes | None, env: Mapping[str, str], rule_path: str) -> str:
        r = subprocess.run(
            ["git", "-c", f"user.name={self.identity_name}", "-c", f"user.email={self.identity_email}", *args],
            cwd=self.gitdir,
            input=data,
            capture_output=True,
            check=False,
            env=dict(env),
        )
        if r.returncode != 0:
            raise Refusal("git.failed", rule_path, r.stderr.decode("utf-8", "replace").strip()[:300])
        return r.stdout.decode("utf-8", "replace")

    def _reader(self) -> _CatFileBatch:
        if self._batch is None:
            self._batch = _CatFileBatch(self.gitdir, self._env)
        return self._batch

    def close(self) -> None:
        """Shut the batch reader down. The finalizer does this too; this is for a caller that wants it now."""
        if self._batch is not None:
            self._batch.close()
            self._batch = None

    # ---- the tree ------------------------------------------------------------------------------------------------

    def _tree(self) -> dict[str, tuple[str, str]]:
        """`HEAD`'s tree as `path -> (mode, oid)`, from **one** `ls-tree -r`, cached until a commit moves the ref.

        **C-13, and the answer is eager for the reason C-13's second worked shape names: the collection is the
        answer.** The first caller is always `paths()` — `store.py`'s load walks the whole listing before it reads
        anything — so a thunk per path would buy nothing and cost a layer. Holding it then makes every subsequent
        `read(path, None)` a dict lookup rather than a `rev-parse`, which is the difference between one spawn per
        store and one per governed file. Trees are the part of a partial clone that is always present, so this never
        triggers a fetch.
        """
        if self._tree_cache is None:
            out: dict[str, tuple[str, str]] = {}
            if self.head is not None:
                for entry in self._git("ls-tree", "-r", "-z", "HEAD").split("\0"):
                    if not entry:
                        continue
                    meta, path = entry.split("\t", 1)
                    mode, _kind, oid = meta.split(" ", 2)
                    out[path] = (mode, oid)
                    if path.startswith(self.root):
                        self._vouched.add(oid)
            self._tree_cache = out
        return self._tree_cache

    @property
    def head(self) -> str | None:
        try:
            return self._git("rev-parse", "--verify", "HEAD").strip()
        except Refusal:
            return None

    def paths(self) -> list[str]:
        """Every path in `HEAD`'s tree. The index is gone, so this reads the tree and not `ls-files`."""
        return sorted(self._tree())

    # ---- reads ---------------------------------------------------------------------------------------------------

    def read(self, path: str, sha: str | None = None) -> bytes | None:
        """The bytes at `path`, in `HEAD`'s tree or in `sha`'s. `None` when that tree has no such path.

        **The footprint is enforced here, before any git runs** [Q3]. A path outside the tracking root is refused
        without a subprocess at all, so the repository cannot grow by the act of asking — which is exactly the
        property done-when 2 asserts, and it is stronger than leaving `GIT_NO_LAZY_FETCH` to refuse afterwards. The
        guard stays on every git invocation underneath regardless, because a refusal that rests on one check in one
        method is a refusal that one future call site removes by accident.

        **Binary throughout.** The previous shape ran `cat-file` through `str` and re-encoded it, which silently
        corrupted every non-UTF-8 byte — latent while the working tree was the source, load-bearing now that this is
        the only reader.
        """
        if not path.startswith(self.root):
            raise Refusal("git.outside-footprint", path, "this path is outside the governed set")
        oid = self.oid_of(path, sha)
        if oid is None:
            return None
        self._vouched.add(oid)
        return self.blob(oid)

    def oid_of(self, path: str, sha: str | None = None) -> str | None:
        """The blob id at `path`, **from the tree** — no content, and so no fetch to refuse (Q11).

        At `HEAD` this is a dict lookup in the cached tree and costs nothing. At another commit it is one
        `rev-parse`, which resolves through trees alone: verified 2026-08-31 that `rev-parse <sha>:<path>` succeeds
        under `GIT_NO_LAZY_FETCH=1` on a filtered clone whose blob for that path is absent.
        """
        if sha is None:
            entry = self._tree().get(path)
            return None if entry is None else entry[1]
        try:
            return self._git("rev-parse", "--verify", f"{sha}:{path}").strip()
        except Refusal:
            return None

    def blob(self, oid: str) -> bytes:
        """One object by id, hydrating it from the promisor remote if this clone does not hold it yet.

        **Why this door may fetch and `read` may not.** An oid only reaches here after a caller resolved it from a
        path inside the tracking root — `read` above, or `touched()`'s governed rows on the reconciliation walk — so
        by the time it is asked for, the footprint question has already been answered.

        **And it is what makes the clone usable at all** [found by the planted-file test, 2026-08-31, not
        anticipated by the brief]. A filtered clone holds **no** blob it did not write itself, governed ones
        included, so without this a restarted store could not read one governed document — not its own
        `config.toml`, and not a bypass commit somebody else pushed to `main`, which is the very thing `check`
        exists to detect. Holding the governed set from the moment of cloning is not available: `blob:none`
        withholds all of them, and the governed set is defined by a manifest that lives *inside* the repository, so
        it cannot be named at clone time.

        **`git.outside-footprint` rather than `git.failed`** [Q3's consequence (a)]. A refused fetch surfaces as an
        ordinary git failure, and an agent that reads *"bad file"* learns nothing. The `git` namespace discloses
        tersely (C-12), so the rule id carries the whole meaning, and this one does.

        **Declared limit (C-10):** hydration is per object and lazy — N fetches on a cold clone for N governed
        paths, none on a warm one. Batching them into a single fetch needs the whole governed set in hand before the
        first read, which is `store.py`'s to give and not this class's to take; recorded as a finding rather than
        guessed at here.
        """
        data = self._reader().read(oid)
        if data is None:
            if oid not in self._vouched:
                raise Refusal("git.outside-footprint", oid, "this object was not resolved from a governed path")
            self._hydrate(oid)
            data = self._reader().read(oid)
        if data is None:
            raise Refusal("git.outside-footprint", oid, "the store's clone holds no content for this object")
        return data

    def _hydrate(self, oid: str) -> None:
        """Fetch one object from the promisor remote — **the only place in this class that runs git without the
        guard**, which is why it is one line in one method rather than a flag on `read`.

        `cat-file -e` is the cheapest way to ask git to materialise an object: it resolves it, fetching if it must,
        and prints nothing. A failure is deliberately not raised here — the caller re-reads and raises
        `git.outside-footprint`, whose words mean something, rather than this one surfacing git's promisor error.
        """
        subprocess.run(
            ["git", "cat-file", "-e", oid],
            cwd=self.gitdir,
            capture_output=True,
            check=False,
            env=self._fetch_env,
        )

    # ---- the write -----------------------------------------------------------------------------------------------

    def commit(self, changes: Changes, author: str, at: str, message: str, parents: list[str] | None = None) -> str:
        """One commit built from plumbing, with `update-ref`'s expected old value as the compare-and-swap.

        There is no index to leak into and no working tree to stage from, so the defect the old `--only` pathspec
        guarded against — a caller's staged change riding the store's commit onto `main` — is now structurally
        impossible rather than guarded. `--no-verify` goes with the porcelain for the same reason: plumbing runs no
        hooks, so there is nothing to tell not to run.
        """
        if parents is not None:
            raise Refusal(
                "git.unsupported", "commit", "explicit parents are the test double's; the store commits on HEAD"
            )
        old = self.head
        tree = dict(self._tree())
        oids = self._hash_objects({p: d for p, d in changes.items() if d is not None})
        for path, data in changes.items():
            if data is None:
                tree.pop(path, None)
            else:
                tree[path] = (tree[path][0] if path in tree else "100644", oids[path])
        commit_oid = self._commit_tree(self._write_tree(tree), old, author, at, message)
        ref = f"refs/heads/{self.branch}"
        try:
            # The third argument is the compare-and-swap. An empty string is git's own spelling of "and it must not
            # exist yet", which is the right test for the first commit rather than omitting the check entirely.
            self._git("update-ref", ref, commit_oid, old if old else "")
        except Refusal as r:
            raise Refusal("git.ref-moved", ref, "the ref moved under the store between read and write") from r
        self._tree_cache = None
        return commit_oid

    def _hash_objects(self, writes: Mapping[str, bytes]) -> dict[str, str]:
        """Write every new blob in **one** `hash-object` call.

        `--stdin-paths` is the only batching form git offers, so the bytes go through a temporary directory: that is
        local file I/O against one process spawn, and a spawn costs 328 ms here (measured 2026-08-31) against a few
        hundred microseconds for a temp write. `--no-filters` because the bytes **are** the artifact — a filter
        would translate line endings on the way in, which is C-9's determinism and the Windows trap this codebase
        already names twice. Each returned id is checked against `blob_id`'s own computation: the two must agree,
        and a disagreement means git applied something to bytes we handed it verbatim.
        """
        if not writes:
            return {}
        order = list(writes)
        with tempfile.TemporaryDirectory(prefix="isidium-blob-") as tmp:
            files = []
            for i, path in enumerate(order):
                f = Path(tmp) / f"{i:06d}"
                f.write_bytes(writes[path])
                files.append(str(f))
            out = self._git("hash-object", "-w", "--no-filters", "--stdin-paths", data="\n".join(files).encode())
        got = out.split()
        if len(got) != len(order):
            raise Refusal("git.failed", "hash-object", f"wrote {len(got)} objects for {len(order)} paths")
        oids: dict[str, str] = {}
        for path, oid in zip(order, got, strict=True):
            expected = blob_id(writes[path], self.object_format)
            if oid != expected:
                raise Refusal("git.failed", "hash-object", f"{path}: git wrote {oid[:12]}, bytes hash {expected[:12]}")
            oids[path] = oid
        return oids

    def _write_tree(self, tree: Mapping[str, tuple[str, str]]) -> str:
        """The tree object for a whole path→(mode, oid) mapping, through a temporary index.

        `GIT_INDEX_FILE` keeps the repository index-free: the index exists for the length of this call, in a
        temporary directory, and never in the git directory. `--index-info` takes the entire mapping on stdin, so
        this is one `update-index` for N paths rather than N.

        **`--missing-ok` is required here and is not a loosening** [found by the first run, 2026-08-31].
        `write-tree` normally verifies that every object the index names is present, which is exactly the check a
        partial clone is built to fail: the tree carries every path in the repository, and the blobs for the
        non-governed ones are deliberately absent. Without the flag the very first governed write dies with
        `could not fetch <oid> from promisor remote` — the enforcement refusing the store's own commit. The flag is
        safe *here* because of where these ids come from and nowhere else would be: every one is either git's own
        (`ls-tree`, which read it out of the tree it is rebuilding) or one `hash-object` just wrote and
        `_hash_objects` checked against `blob_id`. A tree built from ids of unknown provenance would need the check.
        """
        with tempfile.TemporaryDirectory(prefix="isidium-index-") as tmp:
            env = {**self._env, "GIT_INDEX_FILE": str(Path(tmp) / "index")}
            lines = "".join(f"{mode} {oid}\t{path}\n" for path, (mode, oid) in sorted(tree.items()))
            self._run(["update-index", "--index-info"], lines.encode("utf-8"), env, "update-index")
            return self._run(["write-tree", "--missing-ok"], None, env, "write-tree").strip()

    def _commit_tree(self, tree_oid: str, parent: str | None, author: str, at: str, message: str) -> str:
        """`commit-tree`: author = the caller, committer = the store identity (03b §2) — both by environment,
        because plumbing takes no `--author`."""
        env = {
            **self._env,
            "GIT_AUTHOR_NAME": author.split("@", 1)[0],
            "GIT_AUTHOR_EMAIL": author,
            "GIT_AUTHOR_DATE": at,
            "GIT_COMMITTER_NAME": self.identity_name,
            "GIT_COMMITTER_EMAIL": self.identity_email,
            "GIT_COMMITTER_DATE": at,
        }
        args = ["commit-tree", tree_oid, *(["-p", parent] if parent else []), "-m", message]
        return self._run(args, None, env, "commit-tree").strip()

    def push(self) -> None:
        """One **plain** push; a rejection is a refusal, never a rebase and a retry.

        The old shape answered a rejection with `pull --rebase` and one retry. There is no working tree to rebase
        in, and — more to the point — the store's own compare-and-swap on the document head sits upstream of this,
        so a remote that moved means a second writer, which is a condition to report rather than to merge past.

        **It is a plain push, and that is the correction rather than the obvious reading of the brief** [found by
        mutation M5, 2026-08-31]. *"Push with the expected old value"* reads like `--force-with-lease`, and this
        method used it. **`--force-with-lease` is a safer `--force`, not a safer push** — measured: with the lease
        naming the value the remote actually held, a divergent push **succeeded as a forced update and destroyed
        the other writer's commit**, where the plain push was rejected. The lease could only ever help if it named
        the value the store built on, and in that case the push is a fast-forward and needs no help; so it added a
        force path for a case that cannot arise and removed nothing. The expected old value is carried where it
        belongs — `update-ref`'s third argument, on this store's own ref, before anything leaves the process — and
        the remote's own fast-forward check does the rest. **A store must never hold a force path at all.**
        """
        if not self.do_push:
            return
        try:
            self._git("push", "--quiet", self.remote, f"HEAD:{self.branch}")
        except Refusal as r:
            raise Refusal(
                "git.push-rejected", f"{self.remote}/{self.branch}", "the remote moved under the store"
            ) from r

    # ---- the walk (object-level already) -------------------------------------------------------------------------

    def parents(self, sha: str) -> list[str]:
        return self._git("rev-list", "--parents", "-n", "1", sha).split()[1:]

    def commit_time(self, sha: str) -> str:
        return self._git("show", "-s", "--format=%cI", sha).strip()

    def touched(self, sha: str) -> dict[str, tuple[str | None, str | None]]:
        out: dict[str, tuple[str | None, str | None]] = {}
        zero = "0" * (64 if self.object_format == "sha256" else 40)
        for ln in self._git("diff-tree", "--no-commit-id", "-r", "--root", "-m", "--first-parent", sha).splitlines():
            if not ln.startswith(":"):
                continue
            meta, path = ln.split("\t", 1)
            _m1, _m2, b1, b2, _status = meta[1:].split(" ", 4)
            out[path] = (None if b1 == zero else b1, None if b2 == zero else b2)
            if path.startswith(self.root):
                # `check` reads these back through `blob()`; they are governed by the path they sit at, and this is
                # where that is known. Without it a restarted store cannot reconcile its own history.
                self._vouched.update(b for b in out[path] if b)
        return out

    def first_parent_walk(self, since: str | None, until: str | None = None) -> list[str]:
        rng = f"{since}..{until or 'HEAD'}" if since else (until or "HEAD")
        return self._git("rev-list", "--first-parent", "--reverse", rng).split()
