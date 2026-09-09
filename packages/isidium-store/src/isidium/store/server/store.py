"""The store — one tenant namespace of the service (03 §1.2, §1.3, §1.12; 03b): the one writer `write` (validate ·
compare-and-swap · diff + derive · the predicate · journal · file · commit), `ratify(writes)` as one transaction under
one signature — the row lock held across the signer's round trip — `show`, `check`, `init`, `repair`, and the inbox
verbs `suggest` / `disposition`. `land` and `accept` arrive with v1b. Descends from the r6-d6 prototype (220
scenarios) on real components: the registry, a repo (git or the in-memory double), the SQLite journal, the signer
seam. The WP2 review's apply pass (sync 7bf.7) is folded in: refs resolve at ratification, the accepted ref binds a
real closure, the X1 display is durable, rules key to the diff, indexes replace scans, values are hashed once."""

from __future__ import annotations

import copy
import dataclasses
import datetime as _dt
import json
import re
import tomllib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .. import __version__
from ..core import board as board_mod
from ..core import canon, chain, derive, status, telemetry
from ..core import events as events_mod
from ..core.grammar import (
    DocSchema,
    Document,
    Entry,
    append_history_line,
    emit_config,
    emit_jsonl_line,
    emit_markdown,
    parse_jsonl,
    parse_markdown,
)
from ..core.refusal import Refusal, ValidationRefusal
from ..registry import card as card_mod
from ..registry import config as cfg
from ..registry import docschema
from ..registry.loader import Registry
from . import reconcile
from . import refs as refs_mod
from .gitrepo import Repo, blob_id
from .identity import Caller, allowed
from .journal import Journal
from .signer import Display, Signer

CARD_RE = re.compile(r"^cards/(\d{4,})-[a-z0-9\-]*\.md$")
Clock = Callable[[], int]
SCENARIO_RUNNER_KIND = {"test-marker": "test", "command": "command", "http": "http", "file-assert": "file"}


@dataclass(frozen=True)
class NewCard:
    """`GovernedPath::NewCard{slug}` — a creation; the id is allocated inside `write` (1.2, 1.6)."""

    slug: str


@dataclass
class WriteRequest:
    """One member of the sitting's batch (1.12 step 3, X1): `{path, document, base, ref}` — `path` may be a
    `NewCard{slug}` (C4: a card born `ratified` costs no signature of its own)."""

    path: str | NewCard
    document: Document
    base: Mapping[str, Any] | None
    ref: derive.Ref = None


@dataclass
class WriteResult:
    path: str
    entry: Entry
    head: dict[str, Any]  # {seq, h}
    journal_seq: int
    commit: str
    id: int | None = None  # `{id, path, head}` for a NewCard creation
    # K7b (Q18, ruled 2026-09-06): whether the act reached the remote's `main` in this call. `False` is a journaled
    # act whose push failed — the row is durable, memory is indexed, the local commit is held and the next push
    # carries it (K7a, F28). The caller holds the entry and the head either way; what differs is that `main` lags.
    landed: bool = True


@dataclass
class _Member:
    id: int
    path: str
    new: NewCard | None
    act: str
    fields: list[str]
    build: str
    ref: derive.Ref
    verdict: list[Refusal]  # typed, never rendered, until `_ratify_result` discloses them [K10, Q20]
    ready: bool
    before: Document | None
    after: Document
    diff: list[str]
    since_signed: dict[str, Any] | None = None


def _typed_verdicts(verdicts: Sequence[Refusal]) -> list[dict[str, Any]]:
    """One member's verdicts as disclosed records, first occurrence kept, in order (see `_ratify_result`)."""
    seen: set[tuple[str, str, str]] = set()
    out: list[dict[str, Any]] = []
    for r in verdicts:
        key = (r.rule, r.path, r.detail)
        if key in seen:
            continue
        seen.add(key)
        out.append(r.disclosed())
    return out


class Store:
    """One tenant's store: the governed copy (parsed and indexed), the policy chain, the inbox, the sidecar snapshot,
    the journal, the counter, the repo, the signer seam."""

    def __init__(
        self,
        tenant: str,
        repo: Repo,
        journal: Journal,
        registry: Registry,
        clock: Clock,
        signer: Signer | None = None,
        root: str = "",
        identity_enabled: bool = False,
        realm_principal: str = "realm",
        software_fprs: frozenset[str] = frozenset(),
    ) -> None:
        self.tenant, self.repo, self.journal, self.registry, self.clock, self.signer = (
            tenant,
            repo,
            journal,
            registry,
            clock,
            signer,
        )
        self.root = root
        self.identity = f"store@{tenant}"
        self.identity_enabled = identity_enabled
        self.realm_principal = realm_principal
        self.software_fprs = set(software_fprs)
        self.docs: dict[str, Document] = {}
        self.raw: dict[str, bytes] = {}
        self.config_tree: dict[str, Any] = {}
        # Before `load` reads the tenant's file: the newest config version this store ships, which is what `init`
        # would adopt. Its journal version is handed to the journal now so a fresh journal pins the right genesis
        # at its first row (K6); `_set_config` re-adopts from the file once there is one.
        self.eff: dict[str, Any] = cfg.resolve_effective({"schema": registry.newest("config")}, registry)
        self.journal.adopt(cfg.journal_schema(self.eff))
        self.policy: list[Entry] = []
        self.inbox: list[dict[str, Any]] = []
        self.state: dict[str, Any] = {}
        self.events: list[dict[str, Any]] = []
        self.unreadable: dict[str, Refusal] = {}  # governed paths that do not parse: reported by `check`, never fatal
        self._by_id: dict[int, str] = {}  # card id -> path (E3)
        # parent card id -> the ids whose `parent` names it [K7b, F9]: what one card's roll-up reads, kept as the
        # documents are indexed so `show card` never scans the set for them (E3's shape, for the other direction).
        self._kids: dict[int, set[int]] = {}
        self._blob: dict[str, str] = {}  # path -> the blob id of the bytes the store holds (E4)
        self._build: dict[str, str] = {}  # card path -> its build hash (E1: hashed once, cached by blob)
        self.signed_doc: dict[str, Document] = {}  # path -> the document at its last signed entry (X1, E5)
        self._doc_schemas: dict[str, DocSchema] = {}
        self.load()

    # ---- paths and schemas ---------------------------------------------------------------------------------------

    def rp(self, path: str) -> str:
        """The repo path of a root-relative governed path."""
        return self.root + path

    def is_governed_repo_path(self, repo_path: str) -> bool:
        if not repo_path.startswith(self.root):
            return False
        return cfg.governed_resolve(self.eff, repo_path[len(self.root) :]) is not None

    def row_for(self, path: str) -> Mapping[str, Any]:
        row = cfg.governed_resolve(self.eff, path)
        if row is None:
            raise Refusal("governed.unknown-path", path)
        return row

    def doc_schema(self, ref: str) -> DocSchema:
        if ref in self._doc_schemas:
            return self._doc_schemas[ref]
        # One builder, `registry/docschema.py`, shared with the forge's verifier [K12] — the mirror it kept in
        # `tools/verify_chain.py` and the test that held the two equal are gone with it.
        ds = docschema.doc_schema(self.registry, ref)
        self._doc_schemas[ref] = ds
        return ds

    @staticmethod
    def card_path(card_id: int, slug: str) -> str:
        return f"cards/{card_id:0{max(4, len(str(card_id)))}d}-{slug}.md"

    def path_of(self, card_id: int) -> str | None:
        return self._by_id.get(card_id)

    def gated_x(self) -> frozenset[str]:
        return self.card_policy().gated_x

    def policy_schema_version(self) -> int:
        v = self.config_tree.get("schema", 1)
        return int(v) if isinstance(v, int) else 1

    def policy_build(self) -> str:
        return canon.policy_build_hash(self.config_tree, self.policy_schema_version())

    def card_defaults(self) -> Mapping[str, Any]:
        """`card@1`'s own default tree — where the card's `kind` default lives (never in code)."""
        return self.registry.defaults_of("card@1")

    def card_policy(self) -> card_mod.CardPolicy:
        if self._policy_cache is None:
            self._policy_cache = card_mod.CardPolicy.from_effective(self.eff, self.card_defaults())
        return self._policy_cache

    _policy_cache: card_mod.CardPolicy | None = None

    def _set_config(self, tree: dict[str, Any]) -> None:
        self.config_tree = tree
        self.eff = cfg.resolve_effective(tree, self.registry)
        # The journal version rides the config (K6, 7bg.10): a policy write that adopts `journal@2` changes what
        # the very row recording that write carries, and a refused write that restores the previous tree restores
        # the previous version with it, because this is the one site both paths pass through.
        self.journal.adopt(cfg.journal_schema(self.eff))
        self._doc_schemas = {}
        self._policy_cache = None

    def time_skew(self) -> int:
        """From the effective config, which already carries the adopted schema version's default (04 §4.1)."""
        return int(self.eff["time_skew"])

    def build_of(self, doc: Document, ref: str) -> str:
        if ref.startswith("card@"):
            return canon.build_hash(doc.head, doc.scope(), self.gated_x())
        return canon.build_hash(
            {"schema": doc.head.get("schema", 1), "title": doc.head.get("title")}, doc.prose("Body")
        )

    # ---- load / persist ------------------------------------------------------------------------------------------

    def load(self) -> None:
        """Read the governed copy from the repo: config first (it names the manifest), then every governed path;
        build hashes come from the blob cache when warm (9.4: 0 hashes), else once.

        **Every blob under the root is fetched in one round trip before the first read** [K7b, F7]. The shipped load
        hydrated per object — two git processes and one round trip each, ~1.5 s over SSH on tenant #0 — so start-up
        grew with the tenant and a tenant of forty governed documents would have failed its own healthcheck's
        `start_period`. The governed set is not known until `config.toml` is read, and `config.toml` is under the
        root; fetching the root's whole tree first is what makes it *one* round trip rather than two, at the cost of
        also holding a file under the root the manifest does not govern — which `read` already allows, because the
        root is the footprint's boundary (`GitCli`). Eager here because the collection is the answer: this method
        reads every governed path, so a per-object fetch would be a spawn in a loop (C-13's third case).
        """
        self._replay_pending()
        under_root = [p for p in self.repo.paths() if p.startswith(self.root)]
        self.repo.prefetch(o for o in (self.repo.oid_of(p) for p in under_root) if o is not None)
        raw_cfg = self.repo.read(self.rp("config.toml"))
        if raw_cfg is not None:
            text = raw_cfg.decode("utf-8")
            tree, entries, rs = cfg.parse_and_validate(text, self.registry, self.identity_enabled)
            if rs:
                raise ValidationRefusal(rs, "config.toml")
            self.raw["config.toml"] = raw_cfg
            self._blob["config.toml"] = blob_id(raw_cfg, self.repo.object_format)
            self._set_config(tree)
            self.policy = entries
            binary = {
                "client": __version__,
                "registry": __version__,
                "unidata": canon.UNIDATA_VERSION,
                "object_format": self.repo.object_format,
            }
            rs = cfg.startup_check(self.eff, binary)
            if rs:
                raise ValidationRefusal(rs, "config.toml")
        for repo_path in under_root:
            path = repo_path[len(self.root) :]
            if path == "config.toml":
                continue
            row = cfg.governed_resolve(self.eff, path)
            if row is None:
                continue
            data = self.repo.read(repo_path)
            if data is None:
                continue
            try:
                self._ingest_file(path, str(row["schema"]), data)
            except Refusal as r:
                # A file dropped under a governed path that does not parse is `integrity:tampered` for THAT path
                # (03 §1.15) — `check` is the verb that reports it, so loading must never die on it.
                self.unreadable[path] = r
                self.raw[path] = data

    def _ingest_file(self, path: str, ref: str, data: bytes) -> None:
        self.raw[path] = data
        blob = blob_id(data, self.repo.object_format)
        self._blob[path] = blob
        form = self.registry.get(ref).get("form")
        if form == "markdown" and ref != "board@1":
            doc = parse_markdown(data.decode("utf-8"), self.doc_schema(ref))
            self.docs[path] = doc
            if ref.startswith("card@"):
                self._by_id[int(doc.head["id"])] = path
                self._build[path] = self._cached_build(blob, doc)
                self._reparent(int(doc.head["id"]), None, doc)
        elif ref.startswith("inbox@"):
            self.inbox = parse_jsonl(data.decode("utf-8"))
        elif ref.startswith("sidecar-events@"):
            self.events = parse_jsonl(data.decode("utf-8"))
        elif ref.startswith("sidecar@"):
            self.state = json.loads(data.decode("utf-8"))

    def _cached_build(self, blob: str, doc: Document) -> str:
        """The blob-sha cache (9.4): keyed by blob id, ext_schema_hash and canon."""
        ext = canon.ext_schema_hash(self.config_tree)
        c = self.journal.cache_get(blob)
        if c is not None and c[3] == ext and c[4] == canon.CANON:
            return c[0]
        build = canon.build_hash(doc.head, doc.scope(), self.gated_x())
        seq = int(doc.history[-1]["seq"]) if doc.history else 0
        h = str(doc.history[-1]["h"]) if doc.history else ""
        self.journal.cache_put(blob, build, seq, h, ext, canon.CANON)
        return build

    def _reparent(self, cid: int, old: Document | None, new: Document) -> None:
        """Keep `_kids` right across a write that sets, moves or clears a card's `parent` (F9)."""
        was, now = (old.head.get("parent") if old is not None else None), new.head.get("parent")
        if was == now:
            return
        if isinstance(was, int):
            self._kids.get(was, set()).discard(cid)
        if isinstance(now, int):
            self._kids.setdefault(now, set()).add(cid)

    def _index(self, path: str, doc: Document, data: bytes, after_blob: str, build: str | None) -> None:
        self.raw[path] = data
        previous = self.docs.get(path)
        self.docs[path] = doc
        self._blob[path] = after_blob
        if build is not None:
            self._by_id[int(doc.head["id"])] = path
            self._build[path] = build
            self._reparent(int(doc.head["id"]), previous, doc)
            self.journal.cache_put(
                after_blob,
                build,
                int(doc.history[-1]["seq"]),
                str(doc.history[-1]["h"]),
                canon.ext_schema_hash(self.config_tree),
                canon.CANON,
            )

    def _replay_pending(self) -> None:
        """A half-applied write (row written, commit never followed) replays from the journal's pending bytes."""
        pending = self.journal.pending_rows()
        if not pending:
            return
        by_seq: dict[int, dict[str, bytes]] = {}
        for seq, path, data in pending:
            by_seq.setdefault(seq, {})[path] = data
        for seq, files in sorted(by_seq.items()):
            current = {p: self.repo.read(self.rp(p)) for p in files}
            if any(current[p] != d for p, d in files.items()):
                self.repo.commit(
                    {self.rp(p): d for p, d in files.items()}, self.identity, self.now(), f"replay journal {seq}"
                )
                self.repo.push()
            self.journal.applied(seq)

    def now(self) -> str:
        return _dt.datetime.fromtimestamp(self.clock(), _dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    @staticmethod
    def _epoch(at: str) -> int:
        return int(_dt.datetime.strptime(at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=_dt.UTC).timestamp())

    def _prow(self, path: str, data: bytes) -> tuple[dict[str, Any], str]:
        """The journal's path row: `before_blob` is the blob the store already holds (never re-hashed), `after_blob`
        is hashed once and reused (E4)."""
        prow: dict[str, Any] = {"path": path}
        if path in self._blob:
            prow["before_blob"] = self._blob[path]
        after = blob_id(data, self.repo.object_format)
        prow["after_blob"] = after
        return prow, after

    # ---- re-reading `main` before a write (K9, Q14 (c), ruled 2026-09-03) -----------------------------------------

    def _first_governed_change(self, base: str, tip: str) -> str | None:
        """The first governed repo path that moved between `base` and `tip`, named, or `None` if none did.

        **This is Q14's precondition, asserted and never assumed.** The ruling is cheap only because the store's
        in-memory copy of the governed documents — loaded once at start and never re-read — stays *right* across a
        fast-forward. It stays right exactly when the commits being caught up touch no governed path, which under
        the gate (Q13) is what a merged pull request is: the forge refuses one that reaches the tracking root, and
        so does the installed hook. That is a guarantee about the gate, and a guarantee is the thing a store checks.

        The walk is first-parent, matching `touched()`, so a merge contributes the diff against the tip it landed
        on rather than the whole of the branch it merged. It stops at the first offending path: the `git` namespace
        discloses tersely (C-12), so the caller gets the rule id either way and the record gets one named path,
        and continuing would spend a `diff-tree` per commit to build a list nobody reads.

        **Cost (C-8):** one `rev-list` plus one `diff-tree` per commit the store is behind — and it is behind by
        the pull requests merged since its last write, which is one or two. It runs only when the remote actually
        moved; a store whose fetch finds its own tip pays nothing beyond the fetch.
        """
        for sha in self.repo.first_parent_walk(base, tip):
            for repo_path in self.repo.touched(sha):
                if self.is_governed_repo_path(repo_path):
                    return f"{sha[:12]} {repo_path}"
        return None

    def _sync_to_main(self) -> None:
        """**(a) of Q14's ruling: before every write, re-read `main` and fast-forward onto it** — and, since K12, at
        the two doors that resolve refs before they write: the sitting (dry or signed) and a card born `ratified`.

        Until this existed a running store never re-read `main` (K4's finding, and the entrypoint said so out loud),
        so under the gate every merged pull request left the store's clone stale and its next governed write refused
        until somebody restarted the container and let the journal replay. That was measured on tenant #0 the day
        the gate went up, and it is the whole reason for this chunk.

        Three outcomes, in the order they are cheap:

        * the remote's tip is the store's own head — the ordinary case, one fetch and nothing else;
        * the tip is ahead and no governed path moved — the ref fast-forwards, the in-memory model is still right
          by the precondition above, and the write commits on the tip the store now holds;
        * a governed path moved — **refused, and the rule id is the one K4 chose** (`git.push-rejected`). A moved
          remote whose diff reaches the tracking root still means a second writer of governed paths, which is the
          condition K4 ruled must be reported rather than merged past, and nothing in Q14 refines that. Refusing
          here rather than letting the push discover it saves a commit, a journal row and a round trip, and the
          caller cannot tell the two apart because the id and the disclosure are identical.

        A ref that has diverged — the store holding an unpushed commit of its own — is left alone by
        `fast_forward`, which never resets; the write then commits on the base it holds and the rebuild below
        refuses on its own bound. No commit is dropped by this path.

        **What (a) is actually for, learned from its own mutation.** Deleting the fast-forward here leaves a store
        that still works: the write commits on the stale base, the push is rejected, and `_push_or_rebuild` below
        rebuilds it on the same tip. The mutation survived until a test counted the pushes. So (a) is not the
        correctness path — (b) is — and what (a) buys is **the rejected round trip that never happens**, on every
        write after every merged pull request. That is the trade the ruling made when it chose (c) over (b) alone,
        and it is worth one fetch: measured in tenant #0's container against GitHub, 1568 ms median for the fetch
        against a rejected push plus a fetch plus a second push for the same write.
        """
        attrs = {telemetry.TENANT: self.tenant, telemetry.ACTION: "fetch"}
        with telemetry.span(telemetry.SYNC_SPAN, **attrs) as sp:
            try:
                tip = self.repo.fetch()
            except Refusal as r:
                telemetry.record_refusal_on(sp, r.rule)
                raise
            telemetry.record_ok()
        head = self.repo.head
        if tip is None or head is None or tip == head:
            return
        attrs = {telemetry.TENANT: self.tenant, telemetry.ACTION: "fast-forward"}
        with telemetry.span(telemetry.SYNC_SPAN, **attrs) as sp:
            moved = self._first_governed_change(head, tip)
            if moved is not None:
                telemetry.record_refusal_on(sp, "git.push-rejected")
                raise Refusal("git.push-rejected", tip[:12], f"a governed path moved on the remote: {moved}")
            # A ref that has diverged — this store holding a commit the remote does not — is left where it is
            # (`fast_forward` never resets). Since K7a that is a legitimate state: a `write` whose push failed
            # keeps its commit and its pending row, and the next push carries both. It is recorded on the span
            # rather than refused, so an operator can see a store that is journaling ahead of its forge (F17).
            sp.set_attribute(telemetry.DIVERGED, not self.repo.fast_forward(tip))
            telemetry.record_ok()

    def _push_or_rebuild(self, changes: dict[str, bytes], author: str, at: str, message: str, sha: str) -> str:
        """**(b) of Q14's ruling: one bounded rebuild on a rejected push, and only when nothing governed moved.**

        The race (a) cannot close: a pull request merges between the fetch and the push. The answer is the same
        question asked again, and the retry is bounded three ways, each of which falls back to today's refusal:

        1. the store must be **exactly one commit** ahead of the new tip, and it must be *this* commit. More than
           one means the store is carrying unpushed history — the state a governed refusal leaves behind — and
           rebuilding would drop it. This is also what makes a separate ancestry check unnecessary: if this commit
           is the only one the remote lacks, its parent is reachable from the tip by construction.
        2. **no governed path may have moved** between the store's base and the new tip, by the same walk (a) uses;
        3. the rebuilt commit is pushed **once**. A second rejection is the refusal, never another round.

        It is not a rebase and not a force. `GitCli` holds no force path at all, and none is added here: the store
        re-derives its own one commit on a parent it verified, and the compare-and-swap on its own ref plus the
        remote's own fast-forward check are what decide. `git push --force-with-lease` was measured destroying a
        concurrent writer's commit (K4, mutation M5) and is the thing this shape exists to stay away from.
        """
        try:
            self.repo.push()
            return sha
        except Refusal as r:
            if r.rule != "git.push-rejected":
                raise
            rejected = r
        attrs = {telemetry.TENANT: self.tenant, telemetry.ACTION: "rebuild"}
        with telemetry.span(telemetry.SYNC_SPAN, **attrs) as sp:
            try:
                tip = self.repo.fetch()
                if tip is None:
                    raise rejected
                ahead = self.repo.first_parent_walk(tip)
                if ahead != [sha]:
                    raise Refusal(
                        "git.push-rejected",
                        tip[:12],
                        f"the store holds {len(ahead)} commits the remote does not; only its own one is rebuilt",
                    )
                parents = self.repo.parents(sha)
                moved = self._first_governed_change(parents[0], tip) if parents else "a root commit has no base"
                if moved is not None:
                    raise rejected
                rebuilt = self.repo.commit(changes, author, at, message, parents=[tip])
                self.repo.push()
            except Refusal as e:
                telemetry.record_refusal_on(sp, e.rule)
                raise
            telemetry.record_ok()
            return rebuilt

    def _apply(
        self,
        caller: Caller,
        at: str,
        files: Mapping[str, bytes],
        message: str,
        repairs: str | None = None,
        in_txn: bool = False,
    ) -> tuple[dict[str, Any], str, dict[str, str], Refusal | None]:
        """Re-read `main` (K9) → journal write-ahead (one row) → files → one commit → one push, or one bounded
        rebuild on a rejected push → the row applied. Opens the tenant's transaction unless the caller already
        holds it (`ratify`, across the signer's round trip).

        **What a failed push means depends on where the row is, and that decides the fourth value** [K7a, F2 and
        F28]. On the `write` doors the row is committed in its own transaction *before* the commit and the push, so
        by the time a push fails the act has happened — 03b §2: *"a half-land — row written, commit never followed —
        is replayed from the row."* The old code raised there, with `raw` and `_blob` already moved and `docs` not,
        and the caller's next write then carried the orphan commit onto `main` while the orphan's row stayed pending
        for a replay that wrote its bytes back over everything since. Now a failed push on a `write` door **keeps
        the commit and the row, returns normally, and hands the refusal back as the fourth value**: the caller
        indexes the act into memory (it happened), then raises the refusal to the caller (the contract until Q18
        is ruled), and the next successful push clears every pending row it carried (`applied_through`). Inside the
        sitting (`in_txn`) the row is part of the transaction the failure rolls back, so the act did *not* happen:
        the commit is un-built, `raw` and `_blob` are restored, and the refusal is raised here — the fourth value
        is never set on that path."""
        # (a): re-read `main` first, so the commit below is built on the tip the remote holds rather than on
        # whatever this container cloned when it started. Placed ahead of the journal row on purpose — an
        # origin this store cannot reach refuses here, before a row is written and before a commit is made,
        # rather than after both. Since K12 the sitting and a born-`ratified` write have synced once already at
        # their door, so their refs resolved against `main`; this is the fetch across the signer's round trip.
        self._sync_to_main()
        prows: list[dict[str, Any]] = []
        blobs: dict[str, str] = {}
        for p, d in files.items():
            prow, after = self._prow(p, d)
            prows.append(prow)
            blobs[p] = after
        # The caller's credential and the running span's identity travel with the row (K6): the credential inside
        # the hashed content, the trace beside it (C-9). Read once here, for both branches.
        credential, trace = caller.credential, telemetry.current_trace()
        if in_txn:
            row = self.journal.append(
                at, caller.principal, prows, credential=credential, trace=trace, repairs=repairs, pending=dict(files)
            )
        else:
            with self.journal.transaction():
                row = self.journal.append(
                    at,
                    caller.principal,
                    prows,
                    credential=credential,
                    trace=trace,
                    repairs=repairs,
                    pending=dict(files),
                )
        held = {p: (self.raw.get(p), self._blob.get(p)) for p in files}  # what the sitting's rollback restores
        for p, d in files.items():
            self.raw[p] = d
            self._blob[p] = blobs[p]
        repo_files = {self.rp(p): d for p, d in files.items()}
        parent = self.repo.head
        sha = self.repo.commit(repo_files, caller.principal, at, message)
        try:
            sha = self._push_or_rebuild(repo_files, caller.principal, at, message, sha)
        except Refusal as r:
            if not in_txn:
                return row, sha, blobs, r  # journaled: the act happened; `main` lags until the next push (F28)
            head = self.repo.head
            if head is not None:
                self.repo.undo_commit(head, parent)
            for p, (raw, blob) in held.items():
                if raw is None:
                    self.raw.pop(p, None)
                    self._blob.pop(p, None)
                else:
                    self.raw[p] = raw
                    self._blob[p] = blob if blob is not None else self._blob.get(p, "")
            raise
        self.journal.applied_through(int(row["seq"]))
        return row, sha, blobs, None

    def _entry(
        self,
        seq: int,
        at: str,
        caller: Caller,
        act: str,
        fields: list[str],
        build: str,
        ref: derive.Ref = None,
        note: str | None = None,
    ) -> Entry:
        e: Entry = {"seq": seq, "at": at, "by": caller.principal}
        if caller.on_behalf_of:
            e["for"] = caller.on_behalf_of
        e.update({"act": act, "fields": fields, "build": build})
        if ref is not None:
            e["ref"] = ref
        if note is not None:
            e["note"] = note
        return e

    def _sign(self, value: str, at: str, display: Display) -> str:
        if self.signer is None:
            raise Refusal("signer.unavailable", "", "no signer configured for this store")
        r = cfg.use_backend(self.eff, self.signer.backend) if self.config_tree else None
        if r is not None:
            raise r
        return self.signer.sign(self.tenant, value, self._epoch(at), display, self.time_skew())

    def _require(self, caller: Caller, call: str) -> None:
        """The grant check — one function over a matrix value (04 §2, the G7 seam)."""
        if not allowed(caller.grant, call):
            raise Refusal("write.grant", "", f"{caller.grant} may not {call}")

    @staticmethod
    def _landing(deferred: Refusal | None) -> bool:
        """What a write door tells its caller about the push [K7b, Q18, ruled 2026-09-06: *"Result + counter + span
        attribute"*] — the one site every door passes through, so no door has to remember.

        Until Q18 was ruled a write whose row was journaled and whose push then failed was *refused* — the rule id
        alone, for an act that had happened and would land, and the caller's retry with the head they held answered
        `write.stale`. The act is not a refusal: the row is durable, memory is indexed, the local commit is kept and
        the next push carries it (K7a, F28). So the door returns its result with `landed = False`; the push
        failure's own id counts on `isidium.store.write.unlanded` and its words go to the record, and the call span
        says `landed` either way, so an operator can see a store journaling ahead of its forge."""
        if deferred is None:
            telemetry.record_landed(True)
            return True
        telemetry.record_landed(False, deferred.rule, deferred.render())
        return False

    # ---- write (1.2) ---------------------------------------------------------------------------------------------

    def write(
        self,
        path: str | NewCard,
        document: Any,
        base: Mapping[str, Any] | None,
        ref: derive.Ref,
        caller: Caller,
    ) -> WriteResult:
        self._require(caller, "write")
        if isinstance(path, NewCard):
            cid = self.journal.new_id()  # allocation precedes validation; a refused creation burns the id (1.6)
            doc = Document({**document.head, "id": cid}, document.sections)
            p = self.card_path(cid, path.slug)
            r = self._write_markdown(p, self.row_for(p), doc, base, ref, caller, allocated=True)
            r.id = cid
            return r
        row = self.row_for(path)
        if caller.grant not in row["write"]:
            raise Refusal("write.grant", path, f"{caller.grant} may not write {path} (grants: {list(row['write'])})")
        ref_name = str(row["schema"])
        form = self.registry.get(ref_name).get("form")
        if path == "config.toml":
            return self._write_policy(document, base, caller, ref)
        if form == "markdown" and ref_name != "board@1":
            return self._write_markdown(path, row, document, base, ref, caller)
        if ref_name.startswith("inbox@"):
            return self._write_record(path, document, caller, ref_name)
        # Unreachable by construction, kept as the typed statement of why [L1, 2026-09-09, finding 1]: the sidecar's
        # and the board's rows carry the `lander` grant alone, and `lander`'s matrix set has no `write` — so every
        # caller that reaches this line has already been refused `write.grant` above. `land` is their one writer.
        raise AssertionError(f"{path}: no write door for {ref_name}; the sidecar and the board are written by `land`")

    def _write_markdown(
        self,
        path: str,
        row: Mapping[str, Any],
        document: Document,
        base: Mapping[str, Any] | None,
        ref: derive.Ref,
        caller: Caller,
        allocated: bool = False,
    ) -> WriteResult:
        ref_name = str(row["schema"])
        schema = self.doc_schema(ref_name)
        is_card = ref_name.startswith("card@")
        if caller.grant not in row["write"]:
            raise Refusal("write.grant", path)
        before = self.docs.get(path)
        after = Document(
            copy.deepcopy(document.head), copy.deepcopy(document.sections), [], [], before.newline if before else "\n"
        )
        # 1. the diff first, then the rules keyed to it (1.2 step 1)
        diff = derive.diff_sets(before, after)
        if is_card:
            relations = before is None or bool(set(diff) & derive.RELATION_KEYS)
            self._validate_card(path, before, after, allocated, relations)
        else:
            self._validate_page(after, schema)
        # 2. compare-and-swap on {seq, h}
        cur = before.head_of() if before else None
        if cur != (dict(base) if base is not None else None):
            raise Refusal("write.stale", path, f"head {cur}")
        # 3. derive — the one function, refusals included
        d = derive.derive(before, after, ref, diff)
        if before is not None and not d.diff and ref is None:
            raise Refusal("write.no-change", path)
        if d.act == "repaired":
            raise Refusal("write.repair-via-repair", path, "`repaired` is reached by `repair`, never by write")
        bh = before.head if before else None
        if is_card:
            self._check_judging_ref(ref, after)
            if before is None and after.head.get("status") == "ratified":
                # A card born `ratified` resolves its refs here, before `_apply`'s own sync [K12]: the same stale-tree
                # answer the sitting gave, at this door. It fetches twice — once here, once at the commit across the
                # signer's round trip — on the rarest write there is; stated, not threaded away through eight doors.
                self._sync_to_main()
                self._resolve_refs_or_refuse(after)
        # 4. the signature predicate (+ the caller-aware clause: the diff MOVES status to closed/withdrawn — C15)
        reason = derive.needs_signature(
            bh, after.head, d.diff, ref, landed_closures=self._landed_closures(before) if before else frozenset()
        )
        if (
            reason is None
            and caller.grant == "owner"
            and derive.status_moved_to(bh, after.head, derive.OWNER_SIGNS_ALSO)
        ):
            reason = "owner-" + str(after.head.get("status"))
        if reason and caller.grant != "owner":
            raise Refusal("write.requires-owner", path, reason)
        if d.act == "closed" and caller.grant == "owner" and ref is None:
            ref = canon.closure_ref(after.head["closures"][-1])  # the owner's closed binds the closure it judges
        at = self.now()
        if before and at < str(before.history[-1]["at"]):
            raise Refusal("integrity.time", path)
        gated_touched = bool(set(d.diff) & canon.GATED_KEYS)
        build = self._build[path] if (before and not gated_touched and is_card) else self.build_of(after, ref_name)
        seq = int(before.history[-1]["seq"]) + 1 if before else 1
        h_prev = (
            str(before.history[-1]["h"])
            if before
            else chain.genesis(schema.genesis, after.head.get("id", path) if is_card else path)
        )
        entry = self._entry(seq, at, caller, d.act, d.fields, build, ref)
        entry["h"] = chain.link(h_prev, entry)
        if reason:
            # The signer is shown what it is approving, not just a hash (1.12: "the thing the owner approves is shown
            # by something the session cannot write to") — the same display the sitting shows, for the one member.
            since = self._since_signed(path, before, after) if before is not None else self._first_write_display(after)
            entry["sig"] = self._sign(entry["h"], at, [(after.head.get("id", path), d.act, build, since)])
        # 5. journal (write-ahead), write, append, commit
        after.history = [*before.history, entry] if before else [entry]
        if before is not None and not d.diff:
            data = append_history_line(self.raw[path].decode("utf-8"), entry).encode("utf-8")  # the line insertion
        else:
            data = emit_markdown(after, schema).encode("utf-8")
        jrow, sha, blobs, deferred = self._apply(caller, at, {path: data}, f"{d.act} {path}")
        self._index(path, after, data, blobs[path], build if is_card else None)
        if reason:
            self._mark_signed(path, after, blobs[path], seq)
        # after the index: the act is journaled and memory says so (F28); the caller gets the result, and whether
        # `main` has it yet (Q18)
        return WriteResult(
            path, entry, {"seq": seq, "h": entry["h"]}, int(jrow["seq"]), sha, landed=self._landing(deferred)
        )

    @staticmethod
    def _first_write_display(after: Document) -> dict[str, Any]:
        """A card born signed has no prior signed entry to diff against: the display is what is being signed."""
        return {
            "questions_removed": [],
            "answers_added": [],
            "gated": sorted(k for k in after.head if k in canon.GATED_KEYS),
            "tending": {},
            "entries_since": [],
            "created": True,
        }

    def _mark_signed(self, path: str, doc: Document, blob: str, seq: int) -> None:
        self.signed_doc[path] = doc
        self.journal.signed_put(path, blob, seq)

    def _validate_page(self, after: Document, schema: DocSchema) -> None:
        if set(after.head) - {"schema", "title", "slug"}:
            raise Refusal("head.unknown-key", "", str(sorted(set(after.head) - {"schema", "title", "slug"})))
        body = after.prose("Body") or ""
        canon.check_string(body, "body")
        if len(body.encode("utf-8")) > schema.prose_bound:
            raise Refusal("body.prose-bound", "Body")

    def _all_cards(self, except_path: str | None = None) -> dict[int, dict[str, Any]]:
        return {cid: self.docs[p].head for cid, p in self._by_id.items() if p != except_path}

    def _validate_card(
        self, path: str, before: Document | None, after: Document, allocated: bool = False, relations: bool = True
    ) -> None:
        head = after.head
        m = CARD_RE.match(path)
        if not m or int(m.group(1)) != head.get("id"):
            raise Refusal("head.id-filename", path)
        if before is None and not allocated:
            raise Refusal(
                "id.not-allocated", path, "a card is created by write(NewCard{slug}, ...) — the id is the store's (1.2)"
            )
        all_cards = self._all_cards(path) if relations else None
        if all_cards is not None:
            all_cards[int(head["id"])] = head
        failures = card_mod.validate_card(head, after.scope(), self.card_policy(), all_cards, relations)
        if failures:
            raise ValidationRefusal(failures, path)
        if before is not None:
            for k in ("schema", "id", "source"):
                if before.head.get(k) != head.get(k):
                    raise Refusal("head.meta-immutable", k)
            if (
                before.head.get("status") == "withdrawn"
                and head.get("status") != "withdrawn"
                and (chain.is_signed(before.history[-1]) or derive.replay_status(before.history[:-1]) == "draft")
            ):
                raise Refusal(
                    "status.forbidden", path, "confirmed withdrawn -> * (signed, or withdrawn from a draft — 1.5)"
                )
            if before.head.get("status") == "closed" and head.get("status") == "withdrawn":
                raise Refusal("status.forbidden", path, "closed -> withdrawn")

    def _check_judging_ref(self, ref: derive.Ref, after: Document) -> None:
        """C8 / 5.2: a judging ref `c<n>:sha256:<hash>` must name a closure (or reopen) of this card whose entry
        hash it equals — `ref.closure-mismatch` otherwise. Non-closure refs (an int, a manifest, a binding) pass."""
        parsed = derive.parse_closure_ref(ref)
        if parsed is None:
            if isinstance(ref, str):
                raise Refusal("ref.grammar", "ref", ref[:40])
            return
        cid, digest = parsed
        pool = after.head.get("closures", []) if cid.startswith("c") else after.head.get("reopens", [])
        entry = next((c for c in pool if c.get("id") == cid), None)
        if entry is None or canon.closure_ref(entry) != f"{cid}:sha256:{digest}":
            raise Refusal("ref.closure-mismatch", "ref", cid)

    def _resolve_refs(self, doc: Document) -> tuple[list[dict[str, Any]], list[Refusal]]:
        """1.14: `refs` resolve against the repo the store holds; never inside the tracking root.

        **From the tree, not from the content** [Q11, ruled 2026-08-31]. A ref always points *outside* the tracking
        root — that is what `ref.inside-root` enforces — and the store's clone holds blob content for governed paths
        only, so reading a ref's bytes is asking for exactly what the footprint forbids. What the store checks is
        what its trees can see: the path exists, its blob id, and it is outside the root. The line/anchor/symbol
        locus is `core.refs.locus_check`, run by T-B3's assembler at dispatch from the project checkout — and, since
        K4b, by the author's own terminal before the call reaches here (`client/locus.py`).
        """
        refs = doc.head.get("refs") or []
        if not refs:
            return [], []
        return refs_mod.resolve(
            [str(r) for r in refs],
            self.repo.oid_of,
            lambda p: (bool(self.root) and p.startswith(self.root)) or self.is_governed_repo_path(p),
        )

    def _resolve_refs_or_refuse(self, doc: Document) -> list[dict[str, Any]]:
        resolved, rs = self._resolve_refs(doc)
        if rs:
            raise ValidationRefusal(rs, str(doc.head.get("id", "")))
        return resolved

    def _landed_closures(self, doc: Document) -> frozenset[str]:
        """C6 (1.2 step 4): a closure is landed iff its `closed` entry's `seq` ≤ the sidecar's `history_head.seq` —
        one integer compare. Closure `c<n>` was added by the n-th `closed` act."""
        cid = doc.head.get("id")
        if not isinstance(cid, int):
            return frozenset()
        head_seq = int(self.state.get("cards", {}).get(f"{cid:04d}", {}).get("history_head", {}).get("seq", 0))
        if head_seq == 0:
            return frozenset()
        closed_seqs = [int(e["seq"]) for e in doc.history if e.get("act") == "closed"]
        landed: set[str] = set()
        for n, c in enumerate(doc.head.get("closures", []), start=1):
            seq = closed_seqs[n - 1] if n - 1 < len(closed_seqs) else (closed_seqs[-1] if closed_seqs else 0)
            if seq and seq <= head_seq:
                landed.add(str(c.get("id")))
        return frozenset(landed)

    # ---- the policy file -----------------------------------------------------------------------------------------

    def _write_policy(
        self, tree: Mapping[str, Any], base: Mapping[str, Any] | None, caller: Caller, ref: derive.Ref = None
    ) -> WriteResult:
        cur = {"seq": self.policy[-1]["seq"], "h": self.policy[-1]["h"]} if self.policy else None
        if cur != (dict(base) if base is not None else None):
            raise Refusal("write.stale", "config.toml", f"head {cur}")
        if caller.grant != "owner":
            raise Refusal("write.requires-owner", "config.toml", "policy")
        after = copy.deepcopy(dict(tree))
        if "history" in after:
            raise Refusal("log.rewritten", "history", "the policy chain is written only by write")
        rs = cfg.validate_tree(after, self.registry, self.identity_enabled)
        if self.config_tree and after.get("tenant") != self.config_tree.get("tenant"):
            rs.append(Refusal("config.tenant-immutable", "tenant"))
        if self.config_tree:
            rs.extend(cfg.immutable_changed(self.config_tree, after, self.registry))
        # **The tracking root is this store's, by construction** [K7b, Q16, ruled 2026-09-06: *"Both"* — the code
        # half here, `immutable = true` on `root` at the next schema bump]. The K7 review moved `root` by one signed
        # policy write and the store accepted it: its own root is fixed at construction (`serve --root`), so every
        # checkout that pulled the file got a hook protecting the new root while the store kept writing the old one
        # (F10; K3 had named the seam). The *effective* root is compared — a tree that omits the key names the
        # schema's default, and that default is a root too — so `init` and every later policy act pass the one gate.
        eff_root = str(cfg.resolve_effective(after, self.registry).get("root", ""))
        if not rs and eff_root != self.root:
            rs.append(
                Refusal(
                    "config.root-mismatch", "root", f"this store governs {self.root!r}; the tree names {eff_root!r}"
                )
            )
        if rs:
            raise ValidationRefusal(rs, "config.toml")
        before = self.config_tree or None
        d = derive.head_diff(before, after)
        if before is not None and not d and ref is None:
            raise Refusal("write.no-change", "config.toml")
        act, fields = derive.recompute_table(before, after, d, ref, is_policy=True)
        at = self.now()
        schema_v = int(after.get("schema", 1))
        previous = self.config_tree
        self._set_config(after)
        try:
            entry = self._entry(
                len(self.policy) + 1, at, caller, act, fields, canon.policy_build_hash(after, schema_v), ref
            )
            entry["h"] = chain.link(
                self.policy[-1]["h"] if self.policy else chain.genesis("policy", self.tenant, schema_v), entry
            )
            # the policy display: the top-level keys this act moves, so the signer sees the policy surface change
            display = {
                "gated": list(fields),
                "tending": {},
                "questions_removed": [],
                "answers_added": [],
                "entries_since": [],
            }
            entry["sig"] = self._sign(entry["h"], at, [("config.toml", act, entry["build"], display)])
            wr, _blobs, deferred = self._commit_policy(entry, caller, at)
        except Refusal:
            self._set_config(previous)  # refused before the row: nothing happened, and the tree says so
            raise
        wr.landed = self._landing(deferred)  # journaled either way: the tree and the chain keep the act (F28, Q18)
        return wr

    def _commit_policy(
        self,
        entry: Entry,
        caller: Caller,
        at: str,
        extra_files: Mapping[str, bytes] | None = None,
        in_txn: bool = False,
    ) -> tuple[WriteResult, dict[str, str], Refusal | None]:
        # **The entry joins `self.policy` after the row is durable, not before** [K7a, F3]. Appended first, a
        # refusal anywhere in `_apply` — the fetch failing before the row, the sitting's push failing inside its
        # transaction — left a phantom entry whose `h` the next policy write compared its base against, so `init`
        # after an unreachable origin answered `write.stale` until a restart.
        policy = [*self.policy, entry]
        nl = "\r\n" if b"\r\n" in self.raw.get("config.toml", b"") else "\n"
        data = emit_config(self.config_tree, policy, cfg.CONFIG_ORDERS, nl).encode("utf-8")
        files = {"config.toml": data, **(extra_files or {})}
        jrow, sha, blobs, deferred = self._apply(caller, at, files, str(entry["act"]), in_txn=in_txn)
        self.policy.append(entry)
        wr = WriteResult("config.toml", entry, {"seq": entry["seq"], "h": entry["h"]}, int(jrow["seq"]), sha)
        return wr, blobs, deferred

    def bind(self, realm_signer: Signer, key_fpr: str, grant: str, frm: str, until: str | None = None) -> Entry:
        """The realm's act (1.12, 1.15): a `binding` entry in the policy chain, `ref = Binding{...}`, signed
        `sign(realm ‖ h_binding)` with the realm's key — `by` is the realm's service principal (K-20)."""
        at = self.now()
        ref: dict[str, Any] = {"key_fpr": key_fpr, "grant": grant, "tenant": self.tenant, "from": frm}
        if until is not None:
            ref["until"] = until
        act, fields = derive.recompute_table(self.config_tree, self.config_tree, [], ref, is_policy=True)
        realm = Caller(canon.nfc(self.realm_principal).lower(), "owner")
        e = self._entry(len(self.policy) + 1, at, realm, act, fields, self.policy_build(), ref)
        e["h"] = chain.link(
            self.policy[-1]["h"] if self.policy else chain.genesis("policy", self.tenant, self.policy_schema_version()),
            e,
        )
        e["sig"] = realm_signer.sign(
            realm.principal,
            str(e["h"]),
            self._epoch(at),
            [("config.toml", "binding", e["build"], {"binding": dict(ref)})],
            self.time_skew(),
        )
        _wr, _blobs, deferred = self._commit_policy(e, realm, at)
        self._landing(deferred)  # the entry is the realm's act and is returned whole; `main` may lag (Q18)
        return e

    # ---- record-slot documents (the inbox) -----------------------------------------------------------------------

    def _write_record(self, path: str, record: Mapping[str, Any], caller: Caller, schema_ref: str) -> WriteResult:
        at = self.now()
        rec = self._build_record(path, record, caller, schema_ref, self.inbox, at)
        data = self.raw.get(path, b"") + emit_jsonl_line(rec).encode("utf-8")
        jrow, sha, _blobs, deferred = self._apply(caller, at, {path: data}, rec["type"])
        self.inbox.append(rec)
        return WriteResult(
            path, rec, {"seq": rec["seq"], "h": rec["h"]}, int(jrow["seq"]), sha, landed=self._landing(deferred)
        )

    def _build_record(
        self,
        path: str,
        record: Mapping[str, Any],
        caller: Caller,
        schema_ref: str,
        inbox: Sequence[Mapping[str, Any]],
        at: str,
    ) -> dict[str, Any]:
        """One inbox record, validated, numbered and chained onto `inbox` — the records the file holds plus any this
        call has already built [L1: `land` chains a run's suggestions in one pass, one row, one commit, where the
        prototype called `suggest` per suggestion]. Pure over its inputs: nothing is written here."""
        rec = dict(record)
        if rec.get("type") not in ("intake", "disposition"):
            raise Refusal("inbox.type", path, str(rec.get("type")))
        policy = self.card_policy()
        if rec["type"] == "intake":
            if rec.get("source") not in policy.inbox_sources:
                raise Refusal("inbox.source", path, str(rec.get("source")))
            if len(str(rec.get("title", ""))) > 120 or len(str(rec.get("body", "")).encode("utf-8")) > 2048:
                raise Refusal("inbox.bound", path)
            canon.check_string(str(rec.get("title", "")), "title")
            canon.check_string(str(rec.get("body", "")), "body")
        elif not any(r.get("id") == rec.get("on") for r in inbox):
            raise Refusal("inbox.unknown-suggestion", path, str(rec.get("on")))
        # **The record against its own schema's rows** [K7b, F13; deployment record H-5]. `inbox@1` declared `kind`
        # as an enum of seven names and `refs` as an array from the day it was written, and this method checked the
        # type, the source and the two prose bounds above and copied the rest through: the K7 review put 900 KB into
        # `kind` and watched it land on a public `main` in one commit. Same pass the policy file gets, as `record.*`;
        # after the checks above, whose ids (`inbox.bound` on the prose, in bytes) the scenarios pin.
        rs = cfg.check_record(rec, self.registry.get(schema_ref))
        if rs:
            raise ValidationRefusal(rs, path)
        if rec["type"] == "intake":
            rec["id"] = f"s{1 + sum(1 for r in inbox if r['type'] == 'intake')}"
        else:
            rec["id"] = f"d{1 + sum(1 for r in inbox if r['type'] == 'disposition')}"
        rec.update({"seq": len(inbox) + 1, "at": at, "by": caller.principal})
        if caller.on_behalf_of:
            rec["for"] = caller.on_behalf_of
        rec.pop("h", None)
        rec["h"] = chain.link(inbox[-1]["h"] if inbox else chain.genesis("inbox", self.tenant), rec)
        return rec

    # ---- init (04 §3) --------------------------------------------------------------------------------------------

    def init(
        self,
        owner: Caller,
        ratifier_fpr: str | None = None,
        software_key_ack: str | None = None,
        root: str | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> WriteResult:
        """The default `config.toml`: the template's five slots filled from the registration and the installation;
        the first entry `created` (K-1), signed — against the registration when a factory is present, else against
        the pin the same write carries (K-21). `software_key_ack` names the waiver backend and its words."""
        self._require(owner, "config-policy")
        if self.config_tree:
            raise Refusal("init.exists", "config.toml")
        tree: dict[str, Any] = {
            # The newest config version this store ships (K6): a tenant born here adopts `journal@2` with it and
            # records caller credentials from its first row. An existing tenant moves only by a signed act.
            "schema": self.registry.newest("config"),
            "tenant": self.tenant,
            "toolkit": {
                "client": __version__,
                "registry": __version__,
                "unidata": canon.UNIDATA_VERSION,
                "object_id": self.repo.object_format,
            },
        }
        # The tracking root is written, and it is this store's [K7b, Q16]: an operator's `--root` that is not the
        # root this store was started with is refused by `_write_policy`, and a tenant born with no `--root` records
        # the store's rather than inheriting the schema's default in silence.
        tree["root"] = root if root is not None else self.root
        # config@2 (K6) records the version the policy chain opens under, because a later migration moves `schema`
        # and a genesis cannot move with it. Written only when the adopted version declares the key (04 §4.1).
        if any(r["name"] == "chain_opened_under" for r in self.registry.get(f"config@{tree['schema']}")["scalars"]):
            tree["chain_opened_under"] = tree["schema"]
        if not self.identity_enabled:
            if ratifier_fpr is None:
                if self.signer is None:
                    raise Refusal("init.no-ratifier", "", "identity is disabled and no ratifier key is pinned")
                ratifier_fpr = self.signer.key_fpr
            tree["ratification"] = {"pin": "ed25519:" + ratifier_fpr}
        if software_key_ack is not None:
            tree.setdefault("ratification", {})["software_key_ack"] = software_key_ack
            tree["signer"] = {"backends": ["software_key_ack"]}
            self.software_fprs.add(ratifier_fpr or "")
        for k, v in (extra or {}).items():
            tree[k] = copy.deepcopy(v)
        # The manifest declared by the version this chain adopts, never a copy in the binary (C-1, ruled
        # 2026-08-29). `tree["schema"]` is set at the top of this same dict, so the version cannot drift from it.
        tree["governed"] = self.registry.defaults_of(f"config@{tree['schema']}")["governed"]
        return self._write_policy(tree, None, owner)

    # ---- show (1.2) ----------------------------------------------------------------------------------------------

    def show(self, target: Any) -> Any:
        """`show <target>`: `Card(id)` → (document, head) · `Inbox` → the records · `Queue` → the queue section ·
        `Board` → the rendered board · `("Schema", ref)` → the registry document. One projection per call (E1)."""
        if isinstance(target, int):
            p = self.path_of(target)
            if p is None:
                raise Refusal("show.unknown", str(target))
            d = self.docs[p]
            return d, d.head_of()
        if target == "Inbox":
            return list(self.inbox)
        if target in ("Queue", "Board"):
            projections = self.projections()
            merged = len(self.merges_pending()) if self.state else None
            q = status.queue(self._inputs(), projections, self.inbox, self.policy, merged)
            if target == "Queue":
                return q
            return board_mod.render(self.cards(), projections, q, self.inbox, int(self.eff["wip"]))
        if isinstance(target, tuple) and len(target) == 2 and target[0] == "Schema":
            return self.registry.get(str(target[1]))
        raise Refusal("show.unsupported-target", str(target))

    def cards(self) -> dict[int, Document]:
        return {cid: self.docs[p] for cid, p in sorted(self._by_id.items())}

    def _inputs(self) -> status.Inputs:
        builds = {cid: self._build[p] for cid, p in self._by_id.items() if p in self._build}
        return status.Inputs(
            self.cards(),
            self.state,
            self.gated_x(),
            self.verify_entry,
            {},
            frozenset(self.software_fprs),
            builds,
            str(self.card_defaults().get("kind", "")),
            self._kids,
        )

    def projections(self) -> dict[int, status.Projection]:
        return status.project(self._inputs())

    def projection_of(self, card_id: int) -> status.Projection:
        """One card's projection in one card's time [K7b, F9] — `status.project_one` over the same inputs, with the
        parent → members index the store keeps so the roll-up never scans the set. `show.unknown` for an id the
        store has never seen, as `show` answers it."""
        if self.path_of(card_id) is None:
            raise Refusal("show.unknown", str(card_id))
        return status.project_one(self._inputs(), card_id)

    # ---- X2: the land after the merge (the observation half; `land` itself is v1b) -----------------------------

    def merges_pending(self) -> list[str]:
        # One `rev-list --min-parents=2` [K7b, F8], where this ran a `rev-list --parents` per commit on the line —
        # inside `show queue` and `show board`, the moment a sidecar exists.
        return self.repo.merges_since(self.state.get("ledger_cursor"))

    def dispatch(self, card_id: int) -> dict[str, int]:
        """The factory's dispatch precondition on this tenant: fail-closed while a land is pending (X2 pin 2)."""
        n = len(self.merges_pending())
        if n:
            raise Refusal("dispatch.pending-land", "", f"merged, not landed: {n}")
        return {"dispatched": card_id}

    SIDECAR_PATHS = ("state.json", "state/history.jsonl")
    INBOX_PATH = "suggestions.jsonl"
    BOARD_PATH = "BOARD.md"

    def land(self, report: Mapping[str, Any], caller: Caller) -> dict[str, Any]:
        """`land` — the store's own commit on `main` after the batch PR merges (03 §1.4, §6; T-A10; X2, sync 7ba.4:
        *"A with the three pins"*) [L1, 2026-09-09]: `state.json`, `state/history.jsonl`, the inbox intake and
        `BOARD.md` in **one** journal row and **one** commit, under the `lander` grant alone.

        **The door, in order.** The grant matrix (`lander` holds exactly `land` and `show`); a half-land replayed
        (*"a half-land … replays from the journal on the next `land` call"* — T-A10's failure protocol; the load does
        it too); `main` re-read (K12: the door reads `main`, so the merge this land is for is visible); the landed
        copy readable (*"ledger unreadable ⇒ no land"*, read as the sidecar here — the ledger proper is v1c's); and
        each path's manifest row carrying the caller's grant, as `write` checks per path — *"the store refuses the
        grant, not a hasher after the fact"* (T-A10 condition 2). A card file can never be in this diff: no card
        path is assembled below, and the rows refuse the lander on them anyway.

        **The cursor** is the newest pending merge commit — the batch PR's merge, observed the way `merges_pending`
        observes it (pin 3, *"no human step between merge and land"*) — else the cursor the last land put down, else
        the head for a tenant's first land: the standalone case and the synthetic report's. `landed_at` is that
        commit's time (G11). A second
        land of the same cursor with nothing new **is an empty diff**: nothing folded, nothing journaled, nothing
        committed, the result saying so — decided on the inputs, since the previous land's own row moves
        `journal_head` and the bytes alone would never agree.

        **The fold** (`core/events.fold`) reads the event file plus this report's events, never the file it replaces —
        a hand-edited `state.json` is `integrity:unjournaled` to `check` and is overwritten here (03 §6). `journal_head`
        is the head *before* this land's row: a row cannot carry its own hash. `history_head` per card is the store's
        own last entry. **The intake** — the report's `suggestions[]`, capped at `inbox.max_per_run`, the rest counted
        as `overflow` (the ingest fact of that name is L4's) — is built by the inbox door's own record builder, chained
        in one pass, and joins the same files: one row, one commit, one push, where the prototype paid one commit per
        suggestion (C-8). **The board** joins when the effective `board.commit` is true, rendered from the projections
        over the *landed* state, so what lands is what the board would show.

        **The write** is the door's shape, not the sitting's: the row is durable before the commit, a rejected push is
        handed back as `landed = false` (Q18) and the next call or the next load replays it. The transaction is one
        row because it is one act: T-A10's *"one transaction"* is this row's `paths[]`, the four together.
        """
        self._require(caller, "land")
        self._replay_pending()
        self._sync_to_main()
        for p in self.SIDECAR_PATHS:
            if p in self.unreadable:
                raise Refusal("land.sidecar-unreadable", p, str(self.unreadable[p]))
            self._grant_on(p, caller)
        rep = events_mod.parse_report(report)
        pending = self.merges_pending()
        # The newest pending merge is the cursor (pin 3). With nothing merged since, the cursor STAYS where the last
        # land put it — the store's own commits on `main` between lands are not merges and do not move it — and
        # only the first land of a tenant takes the head. That is what keeps *"the same cursor twice"* the same.
        last = self.state.get("ledger_cursor")  # absent on a first land, and on a planted or garbled sidecar
        cursor = pending[-1] if pending else (str(last) if last else self.repo.head)
        if cursor is None:
            raise Refusal("land.no-head", "", "the store holds no commit to land on")
        at = self.now()
        landed_at = self.repo.commit_time(cursor)
        if not rep.events and not rep.suggestions and cursor == self.state.get("ledger_cursor"):
            # Nothing new at the same cursor: the empty diff of 03 §1.4, decided here rather than on bytes, because
            # the previous land's own row moved `journal_head` and the fold would differ by that one value alone.
            telemetry.record_land(0, 0, 0, cursor)
            return {
                "cursor": cursor,
                "landed_at": landed_at,
                "events": [],
                "intake": [],
                "overflow": 0,
                "commit": self.repo.head,
                "journal_seq": None,
                "landed": True,
                "empty": True,
            }
        new_events = [
            events_mod.record_of(ev, f"e{len(self.events) + n}", at) for n, ev in enumerate(rep.events, start=1)
        ]
        events = [*self.events, *new_events]
        heads = {
            f"{cid:04d}": {"seq": d.history[-1]["seq"], "h": d.history[-1]["h"]}
            for cid, d in self.cards().items()
            if d.history
        }
        jseq, jh = self.journal.head
        state = events_mod.fold(events, cursor, landed_at, {"seq": jseq, "h": jh}, heads)
        files: dict[str, bytes] = {
            "state.json": (json.dumps(state, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8"),
            "state/history.jsonl": "".join(emit_jsonl_line(e) for e in events).encode("utf-8"),
        }
        cap = int(self.eff["inbox"]["max_per_run"])
        intake: list[dict[str, Any]] = []
        if rep.suggestions:
            self._grant_on(self.INBOX_PATH, caller)
            inbox = list(self.inbox)
            data = self.raw.get(self.INBOX_PATH, b"")
            for s in rep.suggestions[:cap]:
                rec: dict[str, Any] = {
                    "type": "intake",
                    "source": "run",
                    "kind": s.kind,
                    "title": s.title,
                    "body": s.body,
                    "refs": list(s.refs),
                    "surfaces_touched": [],
                    "from": {"run": rep.run_id},
                }
                if s.proposed_for is not None:
                    rec["proposed_for"] = s.proposed_for
                rec = self._build_record(
                    self.INBOX_PATH, rec, caller, self.row_for(self.INBOX_PATH)["schema"], inbox, at
                )
                inbox.append(rec)
                intake.append(rec)
                data += emit_jsonl_line(rec).encode("utf-8")
            files[self.INBOX_PATH] = data
        overflow = max(0, len(rep.suggestions) - cap)
        if bool(self.eff["board"]["commit"]):
            self._grant_on(self.BOARD_PATH, caller)
            files[self.BOARD_PATH] = self._render_board(state, [*self.inbox, *intake]).encode("utf-8")
        telemetry.record_land(len(new_events), len(intake), overflow, cursor)
        result: dict[str, Any] = {
            "cursor": cursor,
            "landed_at": landed_at,
            "events": [e["id"] for e in new_events],
            "intake": [r["id"] for r in intake],
            "overflow": overflow,
        }
        jrow, sha, _blobs, deferred = self._apply(caller, at, files, "land")
        self.events, self.state = events, state
        self.inbox.extend(intake)
        landed = self._landing(deferred)
        return {**result, "commit": sha, "journal_seq": int(jrow["seq"]), "landed": landed, "empty": False}

    def _grant_on(self, path: str, caller: Caller) -> None:
        """The per-path half of the grant check, as `write` does it: the manifest row must carry the caller's grant."""
        row = self.row_for(path)
        if caller.grant not in row["write"]:
            raise Refusal("write.grant", path, f"{caller.grant} may not write {path} (grants: {list(row['write'])})")

    def _render_board(self, state: Mapping[str, Any], inbox: Sequence[Mapping[str, Any]]) -> str:
        """The board over a state the store does not hold yet — the landed one — through the same renderer `show`
        uses; `merged, not landed` is 0 by construction, the cursor being the newest merge."""
        inp = dataclasses.replace(self._inputs(), state=state)
        projections = status.project(inp)
        q = status.queue(inp, projections, inbox, self.policy, 0)
        return board_mod.render(self.cards(), projections, q, inbox, int(self.eff["wip"]))

    # ---- --set sugar (9.3) ---------------------------------------------------------------------------------------

    def write_set(self, card_id: int, sets: Sequence[str], caller: Caller, ref: derive.Ref = None) -> WriteResult:
        """`write --set key=value`: one gesture = one write. `key=` clears; `updates+=title|body` notes."""
        doc, head = self.show(card_id)
        new = Document(copy.deepcopy(doc.head), copy.deepcopy(doc.sections))
        for s in sets:
            if s.startswith("updates+="):
                title, _, body = s[len("updates+=") :].partition("|")
                ups = new.sections.setdefault("Updates", [])
                assert isinstance(ups, list)
                ups.append({"date": self.now()[:10], "title": title, "body": body})
                continue
            key, _, val = s.partition("=")
            parts = key.split(".")
            target: dict[str, Any] = new.head
            for p_ in parts[:-1]:
                target = target.setdefault(p_, {})
            if val == "":
                target.pop(parts[-1], None)
            else:
                try:
                    target[parts[-1]] = tomllib.loads(f"v = {val}")["v"]
                except tomllib.TOMLDecodeError:
                    target[parts[-1]] = val
        p = self.path_of(card_id)
        assert p is not None
        return self.write(p, new, head, ref, caller)

    # ---- check ---------------------------------------------------------------------------------------------------

    def unreadable_paths(self) -> dict[str, str]:
        """The governed paths that did not parse at load: `integrity:tampered`, reported, never fatal (S6)."""
        return {p: str(r) for p, r in self.unreadable.items()}

    def check(self, card_id: int, since: str | None = None) -> dict[str, Any]:
        """Chain, recompute, signatures + bindings, time, the sidecar's head, journal reconciliation, the profile with
        the whole-set rules (`id.unique`, relations) → the integrity reasons (1.15). One walk over the commits since
        the landed cursor (or `since`); each commit's touched set read once; the before-model carried (E2)."""
        p = self.path_of(card_id)
        if p is None:
            raise Refusal("show.unknown", str(card_id))
        schema = self.doc_schema("card@1")
        doc = parse_markdown(self.raw[p].decode("utf-8"), schema)  # the bytes, not the memory
        reasons: set[str] = set()
        cid = int(doc.head["id"])
        verdicts = chain.verify_chain(
            doc.history, chain.genesis("card", cid), genesis_after_repair=lambda e: chain.genesis("card", cid)
        )
        if "tampered" in verdicts:
            reasons.add("tampered")
        if doc.history[-1]["build"] != canon.build_hash(doc.head, doc.scope(), self.gated_x()):
            reasons.add("tampered")
        for a, b in zip(doc.history, doc.history[1:], strict=False):
            if str(b["at"]) < str(a["at"]):
                reasons.add("time")
        for i, e in enumerate(doc.history):
            if chain.is_signed(e) and verdicts[i] == "ok" and not self.verify_entry(e):
                reasons.add("unverified")
        hh = self.state.get("cards", {}).get(f"{card_id:04d}", {}).get("history_head")
        if hh and (int(hh["seq"]) > len(doc.history) or doc.history[int(hh["seq"]) - 1]["h"] != hh["h"]):
            reasons.add("rewritten")
        reasons |= self._walk(p, since if since is not None else self.state.get("ledger_cursor"))
        profile = self._profile_failures(cid, doc)
        return {"id": card_id, "chain": verdicts, "integrity": sorted(reasons), "profile": [str(r) for r in profile]}

    def _profile_failures(self, cid: int, doc: Document) -> list[Refusal]:
        """The whole-set rules `check` owns (1.2): `id.unique` and the profile with relations."""
        out: list[Refusal] = []
        ids = [int(d.head["id"]) for d in self.docs.values() if isinstance(d.head.get("id"), int)]
        if ids.count(cid) > 1:
            out.append(Refusal("id.unique", "id", str(cid)))
        out += card_mod.validate_card(doc.head, doc.scope(), self.card_policy(), self._all_cards(), True)
        return out

    def _walk(self, path: str, since: str | None) -> set[str]:
        """CI's / ingest's recompute + the reconciliation in ONE walk (never the hook's — 9.6): parent-blob →
        commit-blob through the SAME derive, refusals included; the journal's rows for the path read once.

        **And one git for the history, one for the blobs** [K7b, F8, F7]. The walk used to spawn a `diff-tree` per
        first-parent commit since the cursor — every commit on the tenant, of which the ones that touched this card
        are a handful — 26 processes on tenant #0 and one more per merged pull request, forever, on the verb ingest
        calls per card. `history_of` is one `log --raw` naming exactly those commits with their blob pairs, and
        `prefetch` brings every blob the walk will read in one round trip on a cold clone instead of one each."""
        out: set[str] = set()
        rp = self.rp(path)
        schema = self.doc_schema("card@1")
        rows = self.journal.rows_for(path)
        parsed: dict[str, Document] = {}

        def model(oid: str) -> Document:
            if oid not in parsed:
                parsed[oid] = parse_markdown(self.repo.blob(oid).decode("utf-8"), schema)
            return parsed[oid]

        history = self.repo.history_of(rp, since)
        self.repo.prefetch(b for _sha, bb, ab in history for b in (bb, ab) if b)
        for _sha, bb, ab in history:
            if reconcile.reconcile_path(bb, ab, rows) != "explained":
                out.add("unjournaled")
            try:
                after = model(ab) if ab else None
                before = model(bb) if bb else None
            except Refusal:
                out.add("tampered")
                continue
            if after is not None and (
                len(after.history) != (len(before.history) if before else 0) + 1
                or (before and after.history[:-1] != before.history)
            ):
                out.add("tampered")
                continue
            e = after.history[-1] if after else None
            if e is not None and e.get("act") == "repaired":
                continue
            try:
                d = derive.derive(before, after, e.get("ref") if e else None)
            except Refusal:
                out.add("tampered")
                continue
            assert after is not None and e is not None
            build = (
                str(before.history[-1]["build"])
                if (before and not (set(d.diff) & canon.GATED_KEYS))
                else canon.build_hash(after.head, after.scope(), self.gated_x())
            )
            if (d.act, d.fields, build) != (e["act"], e["fields"], e["build"]):
                out.add("tampered")
        return out

    def verify_entry(self, e: Mapping[str, Any]) -> bool:
        """Per-entry verification (5.6): recompute h (the chain); with `batch` present read the manifest, check
        h ∈ Members and the MANIFEST's one signature; otherwise the entry's own `sig`; then the binding at
        (key_fpr, at) in the policy chain, or the pin when identity is disabled."""
        value, sig = str(e["h"]), e.get("sig")
        if "batch" in e:
            man = next((m for m in self.policy if m["seq"] == e["batch"] and m["act"] == "batch-manifest"), None)
            if man is None or e["h"] not in man["ref"]:
                return False
            value, sig = chain.batch_hash(list(man["ref"])), man.get("sig")
        if not isinstance(sig, str) or not chain.verify_sig(sig, self.tenant, value):
            return False
        fpr = chain.parse_sig(sig)[1]
        pin = str((self.eff.get("ratification") or {}).get("pin", ""))
        return chain.binding_holds(self.policy, fpr, "owner", str(e["at"])) or (
            pin.split(":", 1)[-1] == fpr and not self.identity_enabled
        )

    # ---- ratify (1.12 step 3, X1) --------------------------------------------------------------------------------

    def _signed_baseline(self, path: str) -> Document | None:
        """The document at the last signed entry — in memory, else from the journal's durable blob (C2)."""
        doc = self.signed_doc.get(path)
        if doc is not None:
            return doc
        rec = self.journal.signed_get(path)
        if rec is None:
            return None
        doc = parse_markdown(self.repo.blob(rec[0]).decode("utf-8"), self.doc_schema("card@1"))
        self.signed_doc[path] = doc
        return doc

    def _since_signed(self, path: str, before: Document, after: Document) -> dict[str, Any] | None:
        """X1's display pin (1.11, 1.12): for a member with a prior signed entry — the diff against the LAST SIGNED
        document (removed questions and new answers first, the gated diff), then C1 (a) the tending state diff and
        C1 (b) the `held` / `released` / `demoted` entries since that entry — `seq · act · fields · by · at`."""
        signed = self._signed_baseline(path)
        if signed is None:
            return None
        d = derive.diff_sets(signed, after)
        sq, aq = {q["id"] for q in signed.head.get("questions", [])}, {q["id"] for q in after.head.get("questions", [])}
        sa = {a["question_id"] for a in signed.head.get("answers", [])}
        aa = {a["question_id"] for a in after.head.get("answers", [])}
        tending = {k: [signed.head.get(k), after.head.get(k)] for k in d if k in canon.TENDING_KEYS}
        since_seq = int(signed.history[-1]["seq"])
        return {
            "questions_removed": sorted(sq - aq),
            "answers_added": sorted(aa - sa),
            "gated": sorted(k for k in d if k in canon.GATED_KEYS and k not in ("questions", "answers")),
            "tending": tending,
            "entries_since": [
                (e["seq"], e["act"], e["fields"], e.get("by"), e.get("at"))
                for e in before.history
                if int(e["seq"]) > since_seq and e.get("act") in ("held", "released", "demoted")
            ],
        }

    def _compose_member(self, req: WriteRequest, caller: Caller, prospective_id: int | None) -> _Member:
        """Steps 1–3 of `write` for one batch member (dry and real runs alike); the id of a NewCard member is
        prospective on a dry run and allocated inside the transaction on the real one.

        **Every verdict is a `Refusal`, kept typed** [K10, Q20, ruled 2026-09-06: *"Yes, typed in K10"*]. The list
        used to hold rendered strings — `str(r)` for a refusal, `f"write.stale: head {…}"` and
        `"ratify.not-a-signed-act:" + act` built by hand — and the dry run answered them as strings, so a planner
        reading the sitting's verdicts parsed prose where Q7 had already given `validate.failed` typed records.
        The two hand-built verdicts are refusals now (`ratify.not-a-signed-act` carries the act as its detail), so
        the sweep sees their ids and `_ratify_result` discloses every verdict through the one filter."""
        verdict: list[Refusal] = []
        if isinstance(req.path, NewCard):
            assert prospective_id is not None
            path = self.card_path(prospective_id, req.path.slug)
            before: Document | None = None
            after = Document(
                {**copy.deepcopy(req.document.head), "id": prospective_id}, copy.deepcopy(req.document.sections)
            )
        else:
            path = req.path
            before = self.docs.get(path)
            if before is None:
                raise Refusal("ratify.unknown-path", path)
            after = Document(
                copy.deepcopy(req.document.head), copy.deepcopy(req.document.sections), [], [], before.newline
            )
        cid = int(after.head["id"])
        diff = derive.diff_sets(before, after)
        try:
            self._validate_card(
                path,
                before,
                after,
                allocated=before is None,
                relations=before is None or bool(set(diff) & derive.RELATION_KEYS),
            )
        except Refusal as r:
            verdict.append(r)
        if before is not None and (dict(req.base) if req.base is not None else None) != before.head_of():
            verdict.append(Refusal("write.stale", path, f"head {before.head_of()}"))
        try:
            d = derive.derive(before, after, req.ref, diff)
        except Refusal as r:
            verdict.append(r)
            d = derive.Derived("amended", [], diff)
        if before is not None and not d.diff and req.ref is None:
            verdict.append(Refusal("write.no-change", path))
        try:
            self._check_judging_ref(req.ref, after)
        except Refusal as r:
            verdict.append(r)
        bh = before.head if before else None
        reason = derive.needs_signature(
            bh, after.head, d.diff, req.ref, landed_closures=self._landed_closures(before) if before else frozenset()
        )
        if (
            reason is None
            and caller.grant == "owner"
            and derive.status_moved_to(bh, after.head, derive.OWNER_SIGNS_ALSO)
        ):
            reason = "owner-" + str(after.head.get("status"))
        # C7: a diff that needs no signature is `write`'s act, not the sitting's. **One arm for a creation too**
        # [K7c, F18]: `needs_signature`'s `before is None` branch already decides it -- born ratified is a signed
        # act, anything else is not -- and a creation's diff is never empty, so a second arm here
        # (`before is None and status != "ratified"`) fired on exactly the same members and appended the same
        # verdict twice (measured: a draft in the batch answered `:created` twice, on tenant #0 and in the harness).
        # One predicate, one site; a change to what a creation needs is `needs_signature`'s to make.
        if (d.diff or req.ref is not None) and reason is None:
            verdict.append(Refusal("ratify.not-a-signed-act", "", d.act))
        # refs resolve at ratification (1.14, C7) — for a creation, a ratification, or a refs change
        if after.head.get("refs") and (before is None or d.act in ("ratified", "created") or "refs" in d.diff):
            _resolved, rs = self._resolve_refs(after)
            verdict += rs
        gated_touched = before is None or bool(set(d.diff) & canon.GATED_KEYS)
        build = self._build[path] if not gated_touched else canon.build_hash(after.head, after.scope(), self.gated_x())
        ref = req.ref
        if d.act == "closed" and ref is None:
            ref = canon.closure_ref(after.head["closures"][-1])
        ready = not after.head.get("questions") and "hold" not in after.head
        since = self._since_signed(path, before, after) if before is not None else None
        return _Member(
            cid,
            path,
            req.path if isinstance(req.path, NewCard) else None,
            d.act,
            d.fields,
            build,
            ref,
            verdict,
            ready,
            before,
            after,
            d.diff,
            since,
        )

    def ratify(self, writes: Sequence[int | WriteRequest], caller: Caller, dry_run: bool = False) -> dict[str, Any]:
        """`ratify(writes: [WriteRequest], dry_run)`: the sitting's batch is a list of typed writes under one
        signature; an int member is the `ratify(ids)` shorthand. One transaction — the row lock is taken BEFORE the
        entries are composed and held across the signer's round trip (C1) — N entries with the store's `at`, one
        batch hash, one signer call, one manifest, one journal row, one commit. The dry run is the same function
        minus the signature and the writes."""
        self._require(caller, "ratify:dry-run" if dry_run else "ratify")
        # **`main` first, at this door** [K12, 2026-09-08 — the bridge's finding 2]. The members below resolve their
        # refs against the tree this clone holds, and until K12 the only sync was `_apply`'s — which the dry run
        # never reaches, and the signed run reaches only after its members are composed. Measured on tenant #0: a
        # container whose clone predated one merged pull request answered `ref.unresolved … no such path` at the
        # dry run for a file that had been on `main` for a day, while the terminal's pre-flight had passed it — and
        # the planner is told to present nothing the dry run has not passed. So the dry run pays K9's one fetch
        # (1568 ms median against GitHub) and reads the tree the sitting would sign against; the signed run keeps
        # `_apply`'s fetch as well, because the signer's round trip sits between here and the commit and it is
        # human-paced.
        #
        # **What this door now refuses that it did not, and why that is right:** `git.fetch-failed` — a dry run
        # against a tree it cannot see is not a dry run; and `git.push-rejected` when a governed path moved on the
        # remote — the bypass `check` exists for, surfaced one sitting earlier than the write would have.
        self._sync_to_main()
        reqs: list[WriteRequest] = []
        for w in writes:
            if isinstance(w, int):
                before_doc, head = self.show(w)
                after = Document(copy.deepcopy(before_doc.head), copy.deepcopy(before_doc.sections))
                if after.head["status"] == "draft":
                    after.head["status"] = "ratified"
                p = self.path_of(w)
                assert p is not None
                reqs.append(WriteRequest(p, after, head, None))
            else:
                reqs.append(w)
        if dry_run:
            next_id = self.journal.counter
            members: list[_Member] = []
            for req in reqs:
                pid = None
                if isinstance(req.path, NewCard):
                    next_id += 1
                    pid = next_id
                members.append(self._compose_member(req, caller, pid))
            kinds = sorted(
                {
                    SCENARIO_RUNNER_KIND.get(str(s.get("kind")), str(s.get("kind")))
                    for m in members
                    for s in (m.after.head.get("acceptance") or {}).get("scenarios", [])
                    if s.get("kind") != "manual-evidence"
                }
            )
            runner_rs = cfg.dry_run_check(self.eff, kinds)
            for m in members:
                m.verdict += runner_rs
            return self._ratify_result(members, True)
        if caller.grant != "owner":
            raise Refusal("write.requires-owner", "", "ratify")
        # **Allocation precedes validation, at this door too** [K7b, Q17, ruled 2026-09-06: *"Both doors burn"*].
        # The ids used to be allocated inside the transaction below, so a refused sitting rolled the counter back
        # and this door alone did not burn — where 03 §1.6 says a refused creation burns an id, and `write` does.
        # Each allocation is its own committed transaction here, exactly as `write`'s; a gap in the sequence is the
        # design's own evidence that something was refused. The dry run allocates nothing: it is not a door.
        allocated = [self.journal.new_id() if isinstance(req.path, NewCard) else None for req in reqs]
        with self.journal.transaction():
            members = [self._compose_member(req, caller, pid) for req, pid in zip(reqs, allocated, strict=True)]
            result = self._ratify_result(members, False)
            if any(m.verdict for m in members):
                # the same words the dry run renders, one line: `<id>: <rule> @ <path>: <detail>; …`
                raise Refusal(
                    "ratify.invalid", "", "; ".join(f"{m.id}: {r.render()}" for m in members for r in m.verdict)
                )
            at = self.now()
            entries: list[Entry] = []
            for m in members:
                seq = int(m.before.history[-1]["seq"]) + 1 if m.before else 1
                e = self._entry(seq, at, caller, m.act, m.fields, m.build, m.ref)
                h_prev = str(m.before.history[-1]["h"]) if m.before else chain.genesis("card", m.id)
                e["h"] = chain.link(h_prev, e)
                entries.append(e)
            hs = sorted(str(e["h"]) for e in entries)
            bh = chain.batch_hash(hs)
            man_act, man_fields = derive.recompute_table(self.config_tree, self.config_tree, [], hs, is_policy=True)
            man = self._entry(len(self.policy) + 1, at, caller, man_act, man_fields, self.policy_build(), ref=hs)
            man["h"] = chain.link(
                self.policy[-1]["h"]
                if self.policy
                else chain.genesis("policy", self.tenant, self.policy_schema_version()),
                man,
            )
            man["sig"] = self._sign(bh, at, result["display"])  # the row lock is held across this round trip
            for m in members:  # the CAS re-check after the round trip (trivially true under the lock; stated)
                if m.before is not None and self.docs.get(m.path) is not m.before:
                    raise Refusal("write.stale", m.path, "changed during the signing round trip")
            files: dict[str, bytes] = {}
            schema = self.doc_schema("card@1")
            for m, e in zip(members, entries, strict=True):
                e["batch"] = man["seq"]
                m.after.history = [*m.before.history, e] if m.before else [e]
                files[m.path] = emit_markdown(m.after, schema).encode("utf-8")
            wr, blobs, _never = self._commit_policy(man, caller, at, files, in_txn=True)  # in_txn never defers
        for m, e in zip(members, entries, strict=True):
            self._index(m.path, m.after, files[m.path], blobs[m.path], m.build)
            self._mark_signed(m.path, m.after, blobs[m.path], int(e["seq"]))
        result.update(
            {
                "batch": man["seq"],
                "batch_hash": bh,
                "entries": entries,
                "manifest": man,
                "commit": wr.commit,
                "journal_seq": wr.journal_seq,
                "ids": [m.id for m in members],
                "landed": True,  # the sitting lands or rolls back whole (K7a, F2); it never defers
            }
        )
        return result

    @staticmethod
    def _ratify_result(members: Sequence[_Member], dry_run: bool) -> dict[str, Any]:
        """The sitting's answer. `verdicts` is `{id: [{rule, path, detail}, …]}` — **typed records, the shape Q7
        gave `validate.failed`, through the same disclosure filter** [K10, Q20, ruled 2026-09-06]: each verdict is
        `Refusal.disclosed()`, so a `validate.failed` verdict carries its own `verdicts` array and a terse rule
        (none is raised here today) would contribute its id alone. The terminal prints these same words — rule,
        path, detail — as fields rather than as one rendered line.

        **Deduplicated by the whole record, not by rule id alone.** The ruling's words were *"deduplicated by rule
        id"*, written for F18's doubled `:created`, where the two verdicts were identical; two `ref.unresolved`
        verdicts on two different refs share a rule id and are two facts a planner needs both of, so the key is
        `(rule, path, detail)` — the duplicate F18 named collapses, distinct verdicts under one rule do not.
        Surfaced at K10's checkpoint as the agent's reading of the ruling."""
        display = [(m.id, m.act, m.build, m.since_signed) for m in members]
        return {
            "dry_run": dry_run,
            "verdicts": {m.id: _typed_verdicts(m.verdict) for m in members},
            "display": display,
            "ready": {m.id: m.ready for m in members},
        }

    # ---- the inbox verbs (03a) -----------------------------------------------------------------------------------

    def suggest(
        self,
        caller: Caller,
        kind: str,
        title: str,
        body: str,
        refs: Sequence[str] | None = None,
        source: str | None = None,
        proposed_for: int | None = None,
        frm: Mapping[str, Any] | None = None,
    ) -> WriteResult:
        self._require(caller, "suggest")
        # `inbox@1` declares no default for `source` and should not: every caller knows its own source (the lander
        # lands a run's, the planner its own, an interactive session `session`). Required, therefore, not defaulted.
        if source is None:
            raise Refusal("inbox.source", "source", "name the source: the schema declares no default for it")
        rec: dict[str, Any] = {
            "type": "intake",
            "source": source,
            "kind": kind,
            "title": title,
            "body": body,
            "refs": list(refs or []),
            "surfaces_touched": [],
            "from": dict(frm or {}),
        }
        if proposed_for is not None:
            rec["proposed_for"] = proposed_for
        return self.write("suggestions.jsonl", rec, None, None, caller)

    def disposition(
        self,
        s_id: str,
        outcome: str,
        caller: Caller,
        as_: str | None = None,
        reason: str | None = None,
        until: Any = None,
        slug: str = "from-suggestion",
    ) -> dict[str, Any]:
        self._require(caller, "disposition")
        intake = next((r for r in self.inbox if r.get("id") == s_id), None)
        if intake is None:
            raise Refusal("inbox.unknown-suggestion", "", s_id)
        rec: dict[str, Any] = {"type": "disposition", "on": s_id, "outcome": outcome}
        out: dict[str, Any] = {}
        if outcome == "accepted":
            rec["as"] = as_
            if as_ == "card":
                head: dict[str, Any] = {
                    "schema": 1,
                    "kind": "story",
                    "status": "draft",
                    "source": "suggestion",
                    "title": intake["title"],
                    "see": [s_id],
                }
                from_card = (intake.get("from") or {}).get("card")
                if isinstance(from_card, int) and self.path_of(from_card):
                    fc = self.docs[str(self.path_of(from_card))].head
                    if fc.get("kind") == "epic":
                        head["parent"] = fc["id"]
                    else:
                        head["see"].append(f"card:{fc['id']}")
                doc = Document(
                    head,
                    {
                        "Updates": [
                            {
                                "date": self.now()[:10],
                                "title": f"filed from the inbox ({s_id})",
                                "body": str(intake.get("body", "")),
                            }
                        ]
                    },
                )
                out["card"] = self.write(NewCard(slug), doc, None, None, caller)
                rec["card"] = out["card"].id
            elif as_ == "note":
                cid = int(intake["proposed_for"])
                out["note"] = self.write_set(cid, [f"updates+=suggestion {s_id}|see {s_id}"], caller)
                rec["card"] = cid
        elif outcome == "declined":
            if len(reason or "") > 500:
                raise Refusal("inbox.reason-bound")
            rec["reason"] = reason
        else:
            rec["until"] = until
        out["disposition"] = self.write("suggestions.jsonl", rec, None, None, caller)
        return out

    # ---- repair --------------------------------------------------------------------------------------------------

    def repair(
        self, caller: Caller, history: int | None = None, restart_from: int | None = None, journal: str | None = None
    ) -> dict[str, Any]:
        """`repair --history <id>`: a signed `repaired` entry chaining from h_restart_from (1.15, 5.5);
        `repair --journal <commit>`: the owner-signed row that explains a transition made outside the store (9.6).

        **The grant check is the seam's, not this method's** [K1b-iii]. It used to be a hand-written
        `caller.grant != "owner"`, which made the one act that can rewrite the integrity record the single verb the
        realm could not later re-authorize from policy — the opposite of what `identity.py` promises, and the worst
        verb to make the exception. The answer is unchanged today, because `owner` holds `"*"`; what changes is the
        rule id, from `write.requires-owner` to `write.grant`, which is the correct one: this is the outer matrix
        gate, not the signature predicate (7bf.6 pins that order)."""
        self._require(caller, "repair")
        at = self.now()
        if journal is not None:
            # **A commit is a full hex object id, and nothing else reaches git** [K7a, F5]. The value used to go
            # to `diff-tree`'s argv as written: `--output=<file>` truncated the file before git refused, and a ref
            # name was accepted where the design says *commit*. Checked here, at the typed boundary (C-7), against
            # the repository's own object format; `GitCli` puts `--end-of-options` before it as well.
            width = 64 if self.repo.object_format == "sha256" else 40
            if len(journal) != width or any(c not in "0123456789abcdef" for c in journal):
                raise Refusal("repair.target", "journal", f"a full {width}-character hex commit id")
            touched = self.repo.touched(journal)
            prows = []
            for rp, (b, a) in touched.items():
                if not self.is_governed_repo_path(rp):
                    continue
                prow: dict[str, Any] = {"path": rp[len(self.root) :]}
                if b:
                    prow["before_blob"] = b
                if a:
                    prow["after_blob"] = a
                prows.append(prow)
            with self.journal.transaction():
                row = self.journal.append(
                    at,
                    caller.principal,
                    prows,
                    repairs=journal,
                    credential=caller.credential,
                    trace=telemetry.current_trace(),
                )
                display = {"repairs": journal, "paths": [p["path"] for p in prows]}
                sig = self._sign(str(row["h"]), at, [("journal", "repaired", journal, display)])
                self.journal.sign_row(int(row["seq"]), sig)
            row["sig"] = sig
            for rp, (_b, a) in touched.items():
                gp = rp[len(self.root) :]
                if a and gp in self.docs:
                    data = self.repo.blob(a)
                    doc = parse_markdown(data.decode("utf-8"), self.doc_schema("card@1"))
                    self._index(
                        gp,
                        doc,
                        data,
                        a,
                        canon.build_hash(doc.head, doc.scope(), self.gated_x()) if gp in self._build else None,
                    )
            return {"journal_row": row}
        if history is None:
            raise Refusal("repair.target", "", "--history <id> or --journal <commit>")
        p = self.path_of(history)
        if p is None:
            raise Refusal("show.unknown", str(history))
        doc = parse_markdown(self.raw[p].decode("utf-8"), self.doc_schema("card@1"))
        hh = self.state.get("cards", {}).get(f"{history:04d}", {}).get("history_head", {"seq": 1})
        k = restart_from if restart_from is not None else int(hh["seq"])
        if k < int(hh["seq"]):
            raise Refusal("repair.restart-below-head", "", f"{k} < landed head {hh['seq']}")
        seq = int(doc.history[-1]["seq"]) + 1
        build = canon.build_hash(doc.head, doc.scope(), self.gated_x())
        note = f"chain restarted from seq {k}; entries {k + 1}..{seq - 1} unverifiable, covered"
        e = self._entry(seq, at, caller, "repaired", ["history"], build, ref=k, note=note)
        h_k = str(doc.history[k - 1]["h"]) if k >= 1 else chain.genesis("card", history)
        e["h"] = chain.link(h_k, e)
        e["sig"] = self._sign(str(e["h"]), at, [(history, "repaired", build, {"restart_from": k, "note": note})])
        data = append_history_line(self.raw[p].decode("utf-8"), e).encode("utf-8")
        jrow, sha, blobs, deferred = self._apply(caller, at, {p: data}, "repaired")
        doc.history.append(e)
        self._index(p, doc, data, blobs[p], build)
        self._mark_signed(p, doc, blobs[p], seq)
        return {"entry": e, "commit": sha, "journal_seq": int(jrow["seq"]), "landed": self._landing(deferred)}
