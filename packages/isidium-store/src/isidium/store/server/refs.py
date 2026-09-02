"""`refs` resolution (03 §1.14): a discriminated shape — `Path(p)` · `Lines{p, l1, l2}` · `Anchor{p, a}` ·
`Symbol{p, s}` — written `"p"`, `"p:12-14"`, `"p#a"`, `"p::s"` (the symbol form takes `::`, so `p:12-14` is
unambiguous). Must resolve at ratification; `refs_resolved` (the blob per ref) is recorded in the fingerprint and a
differing blob is `ref-drifted`. Never inside the tracking root; may point at the legacy archive.

**The check has two halves and they are performed by two parties** [Q11, ruled 2026-08-31]. `resolve` below is the
store's half: the path exists in the tree, its blob id, and it is outside the tracking root — **from the tree
alone, reading no content**, because the store holds a partial bare clone with blob content for governed paths only
and a ref always points outside that set. Those three facts are the whole input to `refs_resolved`, to `ref-drifted`
and to the dispatch gate, so nothing about detection depends on the other half. `locus_check` is the other half —
does the line range, the anchor or the symbol land on anything — and it needs the file's text, so it runs where a
working tree exists: T-B3's assembler at dispatch, whose first matching condition is already *"every ref resolves at
`base_sha`"*, and (K4b) the author's own terminal. It is **one function with two callers**, never two
implementations; a second copy is how the two halves would drift apart."""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Final, Literal

from ..core.refusal import Refusal

Kind = Literal["path", "lines", "anchor", "symbol"]
_SYMBOL_DEF: Final = re.compile(
    r"^\s*(?:pub(?:\(crate\))?\s+)?(?:async\s+)?(?:def|class|fn|struct|enum|trait|impl|function|const|let|static|type|interface|mod)\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)"
)
_ASSIGN_DEF: Final = re.compile(r"^(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*(?::[^=]*)?=")
_HEADING: Final = re.compile(r"^#{1,6}\s+(?P<text>.+?)\s*(?:\{#(?P<explicit>[^}]+)\})?\s*#*\s*$")


@dataclass(frozen=True)
class Ref:
    kind: Kind
    path: str
    l1: int = 0
    l2: int = 0
    anchor: str = ""
    symbol: str = ""

    @classmethod
    def parse(cls, text: str) -> Ref:
        if "::" in text:
            p, s = text.split("::", 1)
            if not p or not s:
                raise Refusal("ref.grammar", "refs", text)
            return cls("symbol", p, symbol=s)
        if "#" in text:
            p, a = text.split("#", 1)
            if not p or not a:
                raise Refusal("ref.grammar", "refs", text)
            return cls("anchor", p, anchor=a)
        m = re.match(r"^(.+?):(\d+)-(\d+)$", text)
        if m:
            l1, l2 = int(m.group(2)), int(m.group(3))
            if l1 < 1 or l2 < l1:
                raise Refusal("ref.grammar", "refs", text)
            return cls("lines", m.group(1), l1, l2)
        if not text or text.endswith(":"):
            raise Refusal("ref.grammar", "refs", text)
        return cls("path", text)


def github_slug(text: str) -> str:
    """The GitHub heading slug: lower-case, spaces to `-`, other punctuation stripped, an em/en dash → `--`."""
    t = text.strip().lower().replace("—", "--").replace("–", "--")
    t = re.sub(r"[^\w\- ]", "", t)
    return t.replace(" ", "-")


ObjectId = Callable[[str], str | None]


def resolve(
    refs: Sequence[str], oid_of: ObjectId, inside_root: Callable[[str], bool]
) -> tuple[list[dict[str, Any]], list[Refusal]]:
    """The store's half: resolve every ref against the **tree** (`oid_of(repo_path) -> blob id | None`).

    Returns `refs_resolved` rows `{path, blob}` in the written order and the refusals (`ref.grammar` ·
    `ref.inside-root` · `ref.unresolved`), collected — the dry run shows every cell.

    **No content is read** [Q11]. The blob id is what the fingerprint records and the only input to `ref-drifted`,
    and git's tree already holds it, so asking for the bytes would both duplicate work the tree has done and reach
    for content the store's footprint forbids it to hold. `ref.ambiguous` is not raised here and cannot be: it is
    `locus_check`'s verdict, and `locus_check` runs where the text is.
    """
    resolved: list[dict[str, Any]] = []
    refusals: list[Refusal] = []
    for text in refs:
        try:
            ref = Ref.parse(str(text))
        except Refusal as r:
            refusals.append(r)
            continue
        if inside_root(ref.path):
            refusals.append(Refusal("ref.inside-root", "refs", text))
            continue
        oid = oid_of(ref.path)
        if oid is None:
            refusals.append(Refusal("ref.unresolved", "refs", f"{text}: no such path"))
            continue
        resolved.append({"path": ref.path, "blob": oid})
    return resolved, refusals


def locus_check(ref: Ref, data: bytes) -> str | None:
    """The other half [Q11]: does the line range, the anchor or the symbol land on anything in these bytes?

    `None` when it does, else the rule id — `ref.unresolved` or `ref.ambiguous`. A whole-file `Path` ref has no
    locus, so it always passes; the tree already proved the file exists.

    **Pure, and public because it has callers outside this package's server half.** It takes the bytes rather than a
    reader precisely so the caller supplies them from wherever it legitimately has them: the assembler from the
    project checkout at dispatch, the author's terminal from the working tree (K4b). The store is the one
    participant that cannot call it, which is why the check is not here any more — not because it stopped mattering.
    """
    if ref.kind == "path":
        return None
    lines = data.decode("utf-8", "replace").split("\n")
    if ref.kind == "lines":
        return None if ref.l2 <= len(lines) else "ref.unresolved"
    if ref.kind == "anchor":
        for ln in lines:
            m = _HEADING.match(ln)
            if m and (m.group("explicit") == ref.anchor or github_slug(m.group("text")) == ref.anchor):
                return None
        return "ref.unresolved"
    hits = 0
    for ln in lines:
        m = _SYMBOL_DEF.match(ln) or _ASSIGN_DEF.match(ln)
        if m and m.group("name") == ref.symbol:
            hits += 1
    if hits == 0:
        return "ref.unresolved"
    return None if hits == 1 else "ref.ambiguous"
