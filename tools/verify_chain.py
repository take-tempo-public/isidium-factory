"""The governed-path gate: verify every governed document in a checkout, offline, with the store's own functions.

**Where it runs, and what that makes it** (K8, ruled Q13 2026-09-03): as a *required status check* on every pull
request, where it is prevention — `main` requires a pull request, so this is where a governed change by anyone but
the store is refused; and on every push to `main`, where it re-verifies what landed, the store's own writes
included, since the store's deploy key is the one writer the pull-request gate does not see.

**What forge CI can and cannot see** (7bg.6, [proposed]): a hosted runner cannot reach the store's journal, so the
per-commit reconciliation — *does a journal row explain every governed change?* — stays on the factory side. What a
runner *can* do with a plain checkout is two things, and this script is both of them:

1. **Always:** every governed document parses, and every chained one recomputes — `core/chain.verify_chain()`
   over the policy chain in `config.toml`, over every card's history, over every page's. A hand edit that does not
   rebuild the chain is `tampered`; a governed file that does not parse is `tampered`, which is the store's own rule
   at load (`Store.load` puts it in `unreadable`; `check` reports it as `integrity:tampered`).
2. **With `--diff-base <ref>` (a pull request):** no governed path changed between the base and `HEAD`. Governed
   paths are written by the store, on `main`, or not at all — the same predicate the tenant's pre-commit hook applies
   to a staged set, called through the same function (`client/hook.offending`).

**What it does not do, said plainly.** It verifies chain *integrity*, not signatures: a well-formed entry appended by
someone holding the store's code but not its key would pass here and be caught by the store's own compare-and-swap
at its next write (`write.stale` / `git.push-rejected`). Signature verification of signed entries against the policy
chain's bindings is `Store.verify_entry`'s, and porting it here is a recorded follow-on, not this script's claim.
Inbox and sidecar-event records are parsed but their links are not recomputed: the store chains them at write time
and does not itself re-verify them at load, and this script asserts nothing the store does not.

**This is not a test that can pass on silence** (the standing rule). Every governed document is printed with its
verdict; a root with no intact chained document exits 1 — after `init` there is always `config.toml`, so "nothing
found" is a wrong root, not a clean one — and a checkout with no root at all is refused the way the hook refuses.

Exit 0: every chained document `ok`, nothing `tampered`, no governed change off main. Exit 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from isidium.store.client import hook
from isidium.store.core import chain
from isidium.store.core.grammar import (
    CARD_TABLE_ORDER,
    DocSchema,
    SectionSpec,
    parse_config,
    parse_jsonl,
    parse_markdown,
)
from isidium.store.core.refusal import Refusal
from isidium.store.registry.config import CONFIG_ORDERS, governed_resolve
from isidium.store.registry.loader import Registry

OK = "ok"
TAMPERED = "tampered"
PARSED = "parsed"
SKIPPED = "skipped"


@dataclass(frozen=True)
class Line:
    """One governed document and what was found: `ok` (parsed, chain recomputes), `tampered` (does not parse, or a
    link does not recompute), `parsed` (parsed, and this kind carries no chain this script recomputes), `skipped`
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
    ungoverned: int = 0

    def count(self, verdict: str) -> int:
        return sum(1 for ln in self.lines if ln.verdict == verdict)

    @property
    def passed(self) -> bool:
        return self.count(TAMPERED) == 0 and not self.governed_changed and self.count(OK) > 0


def doc_schema(registry: Registry, ref: str) -> DocSchema:
    """A `DocSchema` built from the registry's `name@version` document.

    **This mirrors `server/store.Store.doc_schema`, line for line, and `tests/store/test_verify_chain.py` holds the
    two equal for every Markdown schema the registry ships.** The builder belongs in `registry/` where both could
    call it; moving it there touches `packages/`, which K8 does not, so the drift is made a test instead of a hope
    (the WP3 idiom: drift is a test). A later chunk that moves it deletes this function and the test's other half.
    """
    doc = registry.get(ref)
    name = ref.split("@", 1)[0]
    sections = tuple(
        SectionSpec(str(s["name"]), "updates" if s["name"] == "Updates" else "prose", bool(s.get("required", False)))
        for s in doc.get("sections", [])
    )
    bound = max(
        [int(s.get("max_bytes", 1 << 20)) for s in doc.get("sections", []) if s.get("kind") == "prose"] or [1 << 20]
    )
    genesis = "card" if name == "card" else "page"
    return DocSchema(
        name, genesis, sections, CARD_TABLE_ORDER if name == "card" else (), doc.get("footer") == "history", bound
    )


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
    if diff_base is not None:
        out = subprocess.run(
            ["git", "diff", "--name-only", "-z", f"{diff_base}...HEAD"],
            cwd=repo,
            capture_output=True,
            check=True,
            text=True,
        )
        rep.governed_changed = hook.offending(repo, [p for p in out.stdout.split("\0") if p])
    return rep


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="verify every governed document in a checkout, offline")
    ap.add_argument("--repo", type=Path, default=Path.cwd(), help="the checkout (default: the working directory)")
    ap.add_argument(
        "--diff-base",
        default=None,
        help="a ref; any governed path changed between it and HEAD fails (forge CI off main: the store is the only "
        "writer of governed paths, and it writes on main)",
    )
    a = ap.parse_args(argv)
    try:
        rep = verify(a.repo, a.diff_base)
    except Refusal as r:
        print(f"isidium: refused — {r.rule}: {r.detail}")
        return 1
    for ln in rep.lines:
        print(f"{ln.verdict:9}{ln.path}  [{ln.schema}]  {ln.detail}")
    for p in rep.governed_changed:
        print(f"changed  {p}  — a governed path changed off main; the store is its only writer")
    print(
        f"isidium: {rep.count(OK)} ok, {rep.count(TAMPERED)} tampered, {rep.count(PARSED) + rep.count(SKIPPED)} "
        f"parsed/skipped, {rep.ungoverned} ungoverned files under {rep.root or './'}"
    )
    if rep.count(OK) == 0 and rep.count(TAMPERED) == 0 and not rep.governed_changed:
        print("isidium: nothing verified — a root with no intact chained document is not a pass")
    return 0 if rep.passed else 1


if __name__ == "__main__":
    sys.exit(main())
