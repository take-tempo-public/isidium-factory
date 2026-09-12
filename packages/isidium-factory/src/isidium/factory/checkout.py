"""The gatherer — the I/O half of the payload [V1, 2026-09-10]: the bytes `payload.assemble` takes, read from a project
checkout at one revision and from the tenant's store, then handed over typed.

**Two `git` spawns and one store call per payload.** A spawn costs about a second on the measured workstation
(`client/locus.py`), and the naive shape — `rev-parse`, then `show` per file, then `show` per ref — is one per object.
Here `git ls-tree` finds the card's path by its id prefix (a listing, not a parse — C-13), and **one `git cat-file
--batch` process, kept open**, answers everything else in turn: the revision (its commit id is how `base_sha` is
pinned), `config.toml`, the card, and — once the card is parsed and its refs known — every ref's blob, id and bytes
in one read each, `missing` for a path the tree does not hold. The block comes from the store, which alone holds the
sidecar the buckets read; the caller supplies that call so a test hands in a lambda and the CLI the lander's channel.

**The root is never a literal here** (C-1): it is the checkout's `.isidium/client.toml` `root` — `init` wrote it from
the adopted schema's default — or the caller's, and a checkout with neither is refused `factory.no-root`.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import IO, Any, Final

from isidium.store.client.config import CLIENT_FILE, ClientConfig
from isidium.store.core import telemetry
from isidium.store.core.grammar import Document, parse_config, parse_markdown
from isidium.store.core.refs import Ref
from isidium.store.core.refusal import Refusal
from isidium.store.registry import docschema
from isidium.store.registry.card import CardPolicy
from isidium.store.registry.config import CONFIG_ORDERS, resolve_effective
from isidium.store.registry.loader import Registry

from .payload import Caps, Identity, Inputs

SPAN: Final = "isidium.factory.payload.gather"
GIT_SPAWNS: Final = "isidium.git.spawns"
CARD_SCHEMA: Final = "card@1"
ContextOf = Callable[[int], Mapping[str, Any]]


class Cat:
    """One `git cat-file --batch` process; `get(name)` → `(oid, type, bytes)` or `None` when git says `missing`."""

    def __init__(self, repo: Path) -> None:
        pipe = subprocess.PIPE
        self._p = subprocess.Popen(["git", "cat-file", "--batch"], cwd=repo, stdin=pipe, stdout=pipe, stderr=pipe)
        assert self._p.stdin is not None and self._p.stdout is not None
        self._in: IO[bytes] = self._p.stdin
        self._out: IO[bytes] = self._p.stdout

    def get(self, name: str) -> tuple[str, str, bytes] | None:
        self._in.write(name.encode("utf-8") + b"\n")
        self._in.flush()
        header = self._out.readline()
        if not header:
            raise Refusal("factory.git", name, "cat-file ended: " + self._err())
        parts = header.rstrip(b"\n").split(b" ")
        if len(parts) == 2 and parts[1] in (b"missing", b"ambiguous"):
            return None
        if len(parts) != 3:
            raise Refusal("factory.git", name, header.decode("utf-8", "replace").strip())
        size = int(parts[2])
        data = self._out.read(size)
        self._out.read(1)  # the newline after the object
        return parts[0].decode("ascii"), parts[1].decode("ascii"), data

    def _err(self) -> str:
        assert self._p.stderr is not None
        err: bytes = self._p.stderr.read()
        return err.decode("utf-8", "replace").strip()

    def close(self) -> None:
        self._in.close()
        self._p.wait(timeout=30)

    def __enter__(self) -> Cat:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def card_path(repo: Path, rev: str, root: str, card_id: int) -> str:
    """The card's repo path at `rev` by its id prefix — `git ls-tree` over the cards directory, one spawn."""
    prefix = f"{card_id:04d}-"
    r = subprocess.run(
        ["git", "ls-tree", "--name-only", rev, f"{root}cards/"], cwd=repo, capture_output=True, text=True, check=False
    )
    if r.returncode != 0:
        raise Refusal("factory.git", rev, r.stderr.strip())
    hits = [ln for ln in r.stdout.splitlines() if ln.rsplit("/", 1)[-1].startswith(prefix)]
    if len(hits) != 1:
        raise Refusal("factory.unknown-card", str(card_id), f"{len(hits)} cards with that id at {rev}")
    return hits[0]


def heads(repo: Path, rev: str, root: str, ids: Iterable[int], registry: Registry) -> dict[int, Document]:
    """Every named card's document at `rev` — **two spawns however many cards** [V3]: one `ls-tree` of `cards/`
    (the id prefixes, not the parses — C-13) and one `cat-file --batch` for all of them. A card the tree does not
    hold is `factory.unknown-card`: the ready-view and the checkout disagree, and the fetch is what is stale."""
    want = list(dict.fromkeys(ids))
    if not want:
        return {}
    r = subprocess.run(
        ["git", "ls-tree", "--name-only", rev, f"{root}cards/"], cwd=repo, capture_output=True, text=True, check=False
    )
    if r.returncode != 0:
        raise Refusal("factory.git", rev, r.stderr.strip())
    by_prefix: dict[str, list[str]] = {}
    for ln in r.stdout.splitlines():
        by_prefix.setdefault(ln.rsplit("/", 1)[-1][:5], []).append(ln)
    schema = docschema.doc_schema(registry, CARD_SCHEMA)
    out: dict[int, Document] = {}
    with Cat(repo) as cat:
        for cid in want:
            hits = by_prefix.get(f"{cid:04d}-", [])
            got = cat.get(f"{rev}:{hits[0]}") if len(hits) == 1 else None
            if got is None:
                raise Refusal("factory.unknown-card", str(cid), f"{len(hits)} cards with that id at {rev}")
            out[cid] = parse_markdown(got[2].decode("utf-8"), schema)
    return out


def worktree(repo: Path, branch: str, at: Path) -> Path:
    """T-C1's *"a worktree per run — never a fresh clone per pick"*: one `git worktree add` on the story branch V3's
    pick already created, one spawn. The run's work happens here and nowhere else, so the checkout the operator uses
    is never the surface a model writes to."""
    at.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        ["git", "worktree", "add", str(at), branch], cwd=repo, capture_output=True, text=True, check=False
    )
    if r.returncode != 0:
        raise Refusal("factory.worktree", branch, r.stderr.strip())
    return at


def worktree_remove(repo: Path, at: Path) -> None:
    """The worktree, taken down. `--force` is the phase's own tree with its own uncommitted work in it, not a
    force push; the branch and every commit on it survive, which is the whole record of what the run did."""
    subprocess.run(
        ["git", "worktree", "remove", "--force", str(at)], cwd=repo, capture_output=True, text=True, check=False
    )


def touched(tree: Path) -> tuple[str, ...]:
    """What the working tree actually holds against its own HEAD — one `git status --porcelain`, tracked and
    untracked alike, and the belt behind the write guard: *"the ledger recomputes the run's touched set from git and
    refuses a report whose claimed set differs"* (the gajae follow-up, adopted 2026-08-21). A report is never the
    evidence for what a report claims."""
    r = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        cwd=tree,
        capture_output=True,
        text=True,
        check=False,
    )
    if r.returncode != 0:
        raise Refusal("factory.git", str(tree), r.stderr.strip())
    out: set[str] = set()
    fields = [f for f in r.stdout.split("\x00") if f]
    i = 0
    while i < len(fields):
        entry = fields[i]
        i += 1
        if len(entry) < 4:
            continue
        code, path = entry[:2], entry[3:]
        # A rename's second field is the source path; both names are part of what the phase touched.
        if ("R" in code or "C" in code) and i < len(fields):
            out.add(fields[i])
            i += 1
        out.add(path)
    return tuple(sorted(out))


def root_of(repo: Path, root: str | None) -> str:
    """The caller's root, else the checkout's client file's (`init` wrote it from the adopted schema — never a literal
    here), else refused: a factory that does not know the tracking root cannot find `config.toml`."""
    if root:
        return root
    p = repo / CLIENT_FILE
    if p.is_file():
        found = ClientConfig.load(p).root
        if found:
            return found
    raise Refusal("factory.no-root", str(repo), f"no `root` in {CLIENT_FILE}; pass --root")


def gather(
    repo: Path,
    rev: str,
    card_id: int,
    *,
    tenant: str,
    root: str | None,
    context_of: ContextOf,
    identity: Identity,
    caps: Caps,
    registry: Registry | None = None,
) -> Inputs:
    """Everything `assemble` needs, from the checkout at `rev` and one store call. `registry` is the context's when
    the caller holds one (V2's `TenantContext` builds it once per run — finding 15); the verb at a terminal, which
    holds no context, builds it here."""
    with telemetry.span(SPAN) as sp:
        root = root_of(repo, root)
        path = card_path(repo, rev, root, card_id)
        with Cat(repo) as cat:
            commit = cat.get(rev)
            if commit is None or commit[1] != "commit":
                raise Refusal("factory.git", rev, "not a commit")
            base_sha = commit[0]
            cfg = cat.get(f"{base_sha}:{root}config.toml")
            if cfg is None:
                raise Refusal("factory.no-config", f"{root}config.toml", f"not at {base_sha}")
            got = cat.get(f"{base_sha}:{path}")
            if got is None:
                raise Refusal("factory.unknown-card", str(card_id), f"{path} not at {base_sha}")
            if registry is None:
                registry = Registry.for_checkout(repo)
            tree, _entries, rs = parse_config(cfg[2].decode("utf-8"), CONFIG_ORDERS)
            fatal = [r for r in rs if r.rule == "head.toml"]
            if fatal:
                raise fatal[0]
            eff = resolve_effective(tree, registry)
            policy = CardPolicy.from_effective(eff, registry.defaults_of(CARD_SCHEMA))
            card = parse_markdown(got[2].decode("utf-8"), docschema.doc_schema(registry, CARD_SCHEMA))
            refs: dict[str, tuple[str, bytes]] = {}
            for p in _paths_cited(card.head):
                blob = cat.get(f"{base_sha}:{p}")
                if blob is not None:
                    refs[p] = (blob[0], blob[2])
        sp.set_attribute(GIT_SPAWNS, 2)
        return Inputs(
            tenant=tenant,
            card_id=card_id,
            base_sha=base_sha,
            card=card,
            gated_x=policy.gated_x,
            refs=refs,
            context=context_of(card_id),
            tree=tree,
            eff=eff,
            identity=identity,
            caps=caps,
        )


def _paths_cited(head: Mapping[str, Any]) -> list[str]:
    """Every distinct path the head's `refs` and `source_narrative` name, in the written order; a ref whose grammar
    fails is left for `assemble` to refuse by name."""
    out: list[str] = []
    seen: set[str] = set()
    texts = [str(t) for t in head.get("refs", [])]
    narrative = head.get("source_narrative")
    if isinstance(narrative, Mapping) and narrative.get("path"):
        texts.append(f"{narrative['path']}#{narrative.get('anchor', '')}")
    for text in texts:
        try:
            p = Ref.parse(text).path
        except Refusal:
            continue
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out
