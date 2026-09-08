"""The governed-path gate: verify every governed document in a checkout, offline, with the store's own functions.
**Shipped as `isidium verify`** [K12, 2026-09-08] so a tenant's forge — which holds the tenant's checkout and
whatever it installs, never this repository's tools — can gate its `main` the way tenant #0's is gated. It was
`tools/verify_chain.py` from K8 to K11; the module is the tool whole, minus the `DocSchema` mirror that
`registry/docschema.py` now serves to the store and to this alike.

**Where it runs, and what that makes it** (K8, ruled Q13 2026-09-03): as a *required status check* on every pull
request, where it is prevention — `main` requires a pull request, so this is where a governed change by anyone but
the store is refused; and on every push to `main`, where it re-verifies what landed, the store's own writes
included, since the store's deploy key is the one writer the pull-request gate does not see.

**What forge CI can and cannot see** (7bg.6, [proposed]): a hosted runner cannot reach the store's journal, so the
per-commit reconciliation — *does a journal row explain every governed change?* — stays on the factory side. What a
runner *can* do with a plain checkout is two things, and this module is both of them:

1. **Always:** every governed document parses, and every chained one recomputes — `core/chain.verify_chain()`
   over the policy chain in `config.toml`, over every card's history, over every page's. A hand edit that does not
   rebuild the chain is `tampered`; a governed file that does not parse is `tampered`, which is the store's own rule
   at load (`Store.load` puts it in `unreadable`; `check` reports it as `integrity:tampered`).
2. **With `diff_base` (a pull request):** no governed path changed between the base and `HEAD`. Governed paths are
   written by the store, on `main`, or not at all — the same predicate the tenant's pre-commit hook applies to a
   staged set, called through the same function (`client/hook.offending`).

**What it does not do, said plainly.** It verifies chain *integrity*, not signatures: a well-formed entry appended by
someone holding the store's code but not its key would pass here and be caught by the store's own compare-and-swap
at its next write (`write.stale` / `git.push-rejected`). Signature verification of signed entries against the policy
chain's bindings is `Store.verify_entry`'s, and porting it here is a recorded follow-on, not this module's claim.
Inbox and sidecar-event records are parsed but their links are not recomputed: the store chains them at write time
and does not itself re-verify them at load, and this asserts nothing the store does not.

**Which registry.** `Registry.for_checkout`: the checkout's installed one when `.isidium/schemas` is there, else the
package's. At a forge a fresh clone has no `.isidium/` (every tenant ignores it), so the verifier reads the registry
of the package the workflow installed — which must therefore be at or after the commit that shipped the version the
tenant adopted, or a `config@N` the package lacks is refused `hook.toolkit-behind` (K11) rather than verified against
`config@1`. The tenant recipe in `deploy/README.md` says so where the pin is chosen.

**This is not a test that can pass on silence** (the standing rule). Every governed document is reported with its
verdict; a root with no intact chained document fails — after `init` there is always `config.toml`, so "nothing
found" is a wrong root, not a clean one — and a checkout with no root at all is refused the way the hook refuses.

The verb prints one line per document and a summary, and exits 0 when every chained document is `ok`, nothing is
`tampered` and no governed change is off `main`; exit 1 otherwise — a verdict. A `Refusal` (`verify.shallow`, a
checkout with no root) is the CLI's, exit 2: two exits, two meanings, `check`'s shape.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from ..core import chain
from ..core.grammar import parse_config, parse_jsonl, parse_markdown
from ..core.refusal import Refusal
from ..registry.config import CONFIG_ORDERS, governed_resolve
from ..registry.docschema import doc_schema
from ..registry.loader import Registry
from . import hook

OK = "ok"
TAMPERED = "tampered"
PARSED = "parsed"
SKIPPED = "skipped"


@dataclass(frozen=True)
class Line:
    """One governed document and what was found: `ok` (parsed, chain recomputes), `tampered` (does not parse, or a
    link does not recompute), `parsed` (parsed, and this kind carries no chain this module recomputes), `skipped`
    (a kind the store does not parse at load either)."""

    path: str
    schema: str
    verdict: str
    detail: str = ""


@dataclass
class Report:
    root: str
    lines: list[Line] = field(default_factory=list)
    governed_changed: list[str] = field(default_factory=list)
    governed_removed: list[str] = field(default_factory=list)  # on `main`: governed paths the parent had (K7a)
    ungoverned: int = 0

    def count(self, verdict: str) -> int:
        return sum(1 for ln in self.lines if ln.verdict == verdict)

    @property
    def passed(self) -> bool:
        return (
            self.count(TAMPERED) == 0 and not self.governed_changed and not self.governed_removed and self.count(OK) > 0
        )

    def rendered(self) -> list[str]:
        """The verb's output, one string per line: every document with its verdict, every governed change or
        disappearance, the summary — and the sentence that says a report with nothing verified is not a pass."""
        out = [f"{ln.verdict:9}{ln.path}  [{ln.schema}]  {ln.detail}" for ln in self.lines]
        for p in self.governed_changed:
            out.append(f"changed  {p}  — a governed path changed off main; the store is its only writer")
        for p in self.governed_removed:
            out.append(f"removed  {p}  — a governed path left main; the store never deletes one")
        ok, tampered = self.count(OK), self.count(TAMPERED)
        other = self.count(PARSED) + self.count(SKIPPED)
        out.append(
            f"isidium: {ok} ok, {tampered} tampered, {other} parsed/skipped, {self.ungoverned} ungoverned files "
            f"under {self.root or './'}"
        )
        if ok == 0 and tampered == 0 and not self.governed_changed and not self.governed_removed:
            out.append("isidium: nothing verified — a root with no intact chained document is not a pass")
        return out


def _verdict(verdicts: Sequence[str]) -> str:
    # An empty chain is not intact — it is nothing, and nothing is not a pass.
    return TAMPERED if not verdicts or TAMPERED in verdicts else OK


def _policy(cfg_path: Path) -> Line:
    """`config.toml`: the grammar (a refusal is `tampered` — the store would refuse to start on it) and the policy
    chain from the genesis the store links from (`Store._write_policy`)."""
    tree, entries, rs = parse_config(cfg_path.read_text(encoding="utf-8"), CONFIG_ORDERS)
    if rs:
        return Line("config.toml", "config@1", TAMPERED, "; ".join(str(r) for r in rs))
    tenant = str(tree.get("tenant", ""))
    schema_v = int(tree.get("schema", 1))
    # The genesis carries the version the chain OPENED under, not the head's: a file migrated to config@2 records
    # its opening version in `chain_opened_under` (K6); a config@1 file opened under its own head version.
    opened = int(tree.get("chain_opened_under", schema_v))
    verdicts = chain.verify_chain(entries, chain.genesis("policy", tenant, opened))
    return Line("config.toml", f"config@{schema_v}", _verdict(verdicts), f"{len(verdicts)} entries")


def _one(p: Path, rel: str, ref: str, registry: Registry) -> Line:
    """One governed path other than `config.toml`, by the kind the registry says it is — the same dispatch as
    `Store._ingest_file`, minus the store."""
    data = p.read_bytes()
    try:
        form = registry.get(ref).get("form")
    except Refusal as r:
        # The manifest names a version this registry does not hold: the store refuses `config.schema-unknown`.
        return Line(rel, ref, TAMPERED, str(r))
    try:
        if form == "markdown" and ref != "board@1":
            ds = doc_schema(registry, ref)
            doc = parse_markdown(data.decode("utf-8"), ds)
            if not ds.history_required:
                return Line(rel, ref, PARSED, "no history footer in this schema")
            if ref.startswith("card@"):
                cid = int(doc.head["id"])
                g = chain.genesis("card", cid)
                # the same callable the store passes in `check`: an id repair restarts from the card's own genesis
                verdicts = chain.verify_chain(doc.history, g, genesis_after_repair=lambda entry: g)
            else:
                verdicts = chain.verify_chain(doc.history, chain.genesis("page", rel))
            return Line(rel, ref, _verdict(verdicts), f"{len(verdicts)} entries")
        if ref.startswith(("inbox@", "sidecar-events@")):
            n = len(parse_jsonl(data.decode("utf-8")))
            return Line(rel, ref, PARSED, f"{n} records; links not recomputed here")
        if ref.startswith("sidecar@"):
            json.loads(data.decode("utf-8"))
            return Line(rel, ref, PARSED, "no chain")
        return Line(rel, ref, SKIPPED, "the store does not parse this kind at load")
    except (Refusal, UnicodeDecodeError, ValueError) as e:
        return Line(rel, ref, TAMPERED, f"does not parse: {e}")


def verify(repo: Path, diff_base: str | None = None) -> Report:
    """Every governed document under the checkout's root, and — with a base — every governed path changed since it.
    Raises `Refusal` when the checkout has no root the hook could find (fail closed, as the hook does)."""
    root, rows = hook.governed_paths(repo)
    eff = {"governed": rows}
    registry = Registry.for_checkout(repo)
    base = repo / root if root else repo
    rep = Report(root)
    cfg_path = base / "config.toml"
    if cfg_path.is_file():
        rep.lines.append(_policy(cfg_path))
    for p in sorted(base.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(base).as_posix()
        if rel == "config.toml":
            continue
        row = governed_resolve(eff, rel)
        if row is None:
            rep.ungoverned += 1
            continue
        rep.lines.append(_one(p, rel, str(row["schema"]), registry))
    # **Both ends of a rename, at both doors** [K7a, F1]. `--name-only` under git's default rename detection prints
    # a rename's destination alone, so `git mv` of a card out of the tracking root was invisible here and in the
    # hook: it passed the pull request, merged, and passed the push-to-`main` run, and the card was gone from the
    # governed set with every check green. `--no-renames` lists the source as a deletion and the destination as
    # an addition — the hook's predicate then names the source.
    if diff_base is not None:
        out = subprocess.run(
            ["git", "diff", "--name-only", "--no-renames", "-z", f"{diff_base}...HEAD"],
            cwd=repo,
            capture_output=True,
            check=True,
            text=True,
        )
        rep.governed_changed = hook.offending(repo, [p for p in out.stdout.split("\0") if p])
    else:
        rep.governed_removed = _removed_since_parent(repo)
    return rep


def _removed_since_parent(repo: Path) -> list[str]:
    """On `main`: every governed path the first parent had and `HEAD` does not — a disappearance is a verdict, not
    a silence [K7a, F1]. The walk over the root can only see what is there; a card that left the governed set
    by rename or deletion is caught nowhere else on this branch, because the store never deletes a governed
    document and the pull request's diff check runs off `main`. A root commit has no parent and nothing to
    compare; a **shallow** checkout has a parent it cannot see, and that is refused rather than passed — the
    forge's own workflow fetches full depth, and a pass on a truncated history would be the silence this exists
    to close."""
    parent = subprocess.run(
        ["git", "rev-parse", "--verify", "-q", "HEAD^"], cwd=repo, capture_output=True, check=False, text=True
    )
    if parent.returncode != 0:
        shallow = subprocess.run(
            ["git", "rev-parse", "--is-shallow-repository"], cwd=repo, capture_output=True, check=False, text=True
        )
        if shallow.stdout.strip() == "true":
            raise Refusal("verify.shallow", "HEAD^", "a shallow checkout cannot compare against the parent")
        return []
    out = subprocess.run(
        ["git", "diff", "--name-only", "--no-renames", "--diff-filter=D", "-z", "HEAD^", "HEAD"],
        cwd=repo,
        capture_output=True,
        check=True,
        text=True,
    )
    return hook.offending(repo, [p for p in out.stdout.split("\0") if p])
