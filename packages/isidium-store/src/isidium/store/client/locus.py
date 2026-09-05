"""The author's terminal checks a ref's sub-file locus before the store is called (K4b; Q11's residue).

A ref whose line range, anchor or symbol never resolved is caught at dispatch by T-B3's assembler and nowhere
earlier; on a card that is never dispatched — a spike, a `surfaces = []` task, one held indefinitely — it is never
caught at all. Nothing downstream consumes it, so the system is fail-closed without this module: it is
specification quality, not integrity. What it buys is *where* the author learns: at their own terminal, while they
are looking at the file, instead of an operator learning at the moment they wanted work to start.

**One implementation, two callers** (Q11). The check is `core.refs.locus_check`, the pure function over
`(ref, bytes)` the assembler runs at dispatch; this module supplies the bytes from the working tree and nothing
else. It reaches the function through the module attribute, never a bound name, so `tests/store/test_k4b.py` can
substitute the one function and prove this door has no copy of its own.

**The working tree, not `HEAD`** — trap 2 of the brief, decided here. The author's file may be dirty, and the store
records the blob at *its* head (the tenant's `main`, fetched before the write), which the local `HEAD` is not
either; so reading `HEAD:<path>` would buy no agreement with the store, only a `git` spawn per ref (about a second
each on the measured workstation). The working tree is what the author is editing, which is the feedback this door
exists to give, and it costs one `open()`. The residue — a locus valid against a dirty tree and invalid at the blob
the store records — is the "later broke" shape in reverse, and the assembler at dispatch is still the gate. Advice
here; the gate there.

**What is deliberately left to the store.** A path that is not in the working tree is skipped, not refused: the
checkout may simply be behind `main`, and the store refuses `ref.unresolved` from its own tree in the same call — a
local refusal would be a second implementation of existence, with a false positive the store's cannot have.
`ref.inside-root` is the store's for the same reason. A whole-file ref has no locus and nothing to check here.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from ..core import refs as refs_mod
from ..core import telemetry
from ..core.refusal import Refusal, ValidationRefusal

PREFLIGHT_SPAN: Final = "isidium.client.refs.preflight"
REFS_CITED: Final = "isidium.refs.cited"  # on the span: how many refs the call carried
REFS_CHECKED: Final = "isidium.refs.checked"  # and how many loci were actually read — the two are not the same fact

# The words for a verdict, by the ref's form. Rendering only: the rule id is `locus_check`'s, and a pair this table
# does not know is rendered as the rule id alone rather than refused a second way here.
_WHY: Final = {
    ("lines", "ref.unresolved"): "the range runs past the end of the file",
    ("anchor", "ref.unresolved"): "no such heading",
    ("symbol", "ref.unresolved"): "no such definition",
    ("symbol", "ref.ambiguous"): "defined more than once",
}


def preflight(name: str, args: Mapping[str, Any], workdir: Path, root: str) -> None:
    """Refuse, before the channel is opened, every ref this call carries whose locus does not land in the working
    tree.

    `write` carries refs in a document's `head.refs` or in a `--set refs=[…]` gesture; `ratify` in each write's
    document and in each id's card as the checkout holds it. Any other call passes through untouched. Raises
    `ValidationRefusal` — the same aggregate the store raises for a write whose refs fail its half — carrying every
    verdict, so the author fixes them in one pass rather than one per round trip.
    """
    if name not in ("write", "write_set", "ratify"):
        return
    with telemetry.span(PREFLIGHT_SPAN, **{telemetry.ACTION: name}) as sp:
        cited = refs_of(name, args, workdir, root)
        rs, checked = verdicts(cited, workdir)
        sp.set_attribute(REFS_CITED, len(cited))
        sp.set_attribute(REFS_CHECKED, checked)
        if rs:
            refusal = ValidationRefusal(rs, "refs")
            telemetry.record_refusal_on(sp, refusal.rule)
            raise refusal
        telemetry.record_ok()


def refs_of(name: str, args: Mapping[str, Any], workdir: Path, root: str) -> list[str]:
    """Every ref text the call carries, in the order it carries them."""
    if name == "write":
        return [] if args.get("path") == "config.toml" else _document_refs(args.get("document"))
    if name == "write_set":
        return [r for s in args.get("set") or [] for r in _set_refs(str(s))]
    out: list[str] = []
    for w in args.get("writes") or []:
        if isinstance(w, Mapping):
            out.extend(_document_refs(w.get("document")))
    for cid in args.get("ids") or []:
        out.extend(_card_refs(workdir, root, int(cid)))
    return out


def _document_refs(document: Any) -> list[str]:
    head = document.get("head") if isinstance(document, Mapping) else None
    refs = head.get("refs") if isinstance(head, Mapping) else None
    return [str(r) for r in refs] if isinstance(refs, list) else []


def _set_refs(gesture: str) -> list[str]:
    """`--set refs=["a.py::f", …]`: the value is TOML, which is how the store reads every `--set` value. It is read
    here only when it *is* a list of that shape — a value that is not one the store refuses on its own terms, and a
    text that fails to parse here fails the same way there, so the two cannot disagree about which refs the call
    carries."""
    key, _, val = gesture.partition("=")
    if key != "refs" or not val:
        return []
    try:
        value = tomllib.loads(f"v = {val}")["v"]
    except tomllib.TOMLDecodeError:
        return []
    return [str(r) for r in value] if isinstance(value, list) else []


def _card_refs(workdir: Path, root: str, cid: int) -> list[str]:
    """The `refs` of card `cid` as this checkout holds it — for `ratify <id>`, the one arm that reads a card.

    **From the working tree** (the module docstring): the card file is the store's own last write of it as of the
    checkout's `main`. A checkout behind `main` checks the refs it has, which are the store's at some commit; if a
    later write changed them, `git pull` is the author's fix and the store's answer is the store's. No file — the id
    is unknown here, or the checkout has never fetched it — is nothing to check, and a file the head grammar refuses
    is not a card the store wrote, so it is the store's to answer for too.

    `parse_head` is imported here and not at the top (C-13 — judged, not reflex): `core.grammar` measured 12–20 ms
    net of `core.refusal` on the workstation (2026-09-05, `-X importtime`, five runs, ~5 ms of it `tomllib`), and
    every other `isidium` command — `write`, `show`, `check`, `--help` — would pay it to answer a question only
    `ratify <id>` asks. `tomllib` itself is already in the client's graph through `client/config.py`.
    """
    from ..core.grammar import parse_head

    found = sorted((workdir / root / "cards").glob(f"{cid:04d}-*.md"))
    if len(found) != 1:
        return []
    try:
        head = parse_head(found[0].read_text(encoding="utf-8"))
    except Refusal:
        return []
    refs = head.get("refs")
    return [str(r) for r in refs] if isinstance(refs, list) else []


def verdicts(refs: Sequence[str], workdir: Path) -> tuple[list[Refusal], int]:
    """Every ref's verdict against the working tree, collected — the dry run's rule: show every cell.

    Returns the refusals and **how many loci were actually read**: the second is the span's `checked` attribute and
    a test's discriminator between "nothing was wrong" and "nothing was looked at", which no list of refusals can
    tell apart on its own."""
    out: list[Refusal] = []
    checked = 0
    bytes_of: dict[str, bytes | None] = {}  # one read per path per call, however many refs cite it
    base = workdir.resolve()
    for text in refs:
        try:
            ref = refs_mod.Ref.parse(text)
        except Refusal as r:
            out.append(r)
            continue
        if ref.kind == "path":
            continue
        if ref.path not in bytes_of:
            bytes_of[ref.path] = _read_inside(base, ref.path)
        data = bytes_of[ref.path]
        if data is None:
            continue
        checked += 1
        rule = refs_mod.locus_check(ref, data)
        if rule is not None:
            why = _WHY.get((ref.kind, rule))
            out.append(Refusal(rule, "refs", f"{text}: {why}" if why else text))
    return out, checked


def _read_inside(base: Path, rel: str) -> bytes | None:
    """The file's bytes when `rel` names a file inside the checkout; `None` otherwise. A ref's path is a repository
    path, so `..`, an absolute path or a link out of the tree name nothing the store's tree could hold — this door
    reads nothing outside the checkout on their account."""
    p = (base / rel).resolve()
    if not p.is_relative_to(base) or not p.is_file():
        return None
    return p.read_bytes()
