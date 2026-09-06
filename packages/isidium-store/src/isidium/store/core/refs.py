"""A ref's grammar and its sub-file locus — the pure half of `refs` resolution (03 §1.14), with no I/O and no store.

A ref is a discriminated shape — `Path(p)` · `Lines{p, l1, l2}` · `Anchor{p, a}` · `Symbol{p, s}` — written `"p"`,
`"p:12-14"`, `"p#a"`, `"p::s"` (the symbol form takes `::`, so `p:12-14` is unambiguous). Must resolve at
ratification; `refs_resolved` (the blob per ref) is recorded in the fingerprint and a differing blob is
`ref-drifted`. Never inside the tracking root; may point at the legacy archive.

**The check has two halves and they are performed by two parties** [Q11, ruled 2026-08-31]. `server/refs.py`'s
`resolve` is the store's half: the path exists in the tree, its blob id, and it is outside the tracking root — from
the tree alone, reading no content, because the store holds a partial bare clone with blob content for governed
paths only and a ref always points outside that set. `locus_check` below is the other half — does the line range,
the anchor or the symbol land on anything — and it needs the file's text, so it runs where a working tree exists:
T-B3's assembler at dispatch, whose first matching condition is already *"every ref resolves at `base_sha`"*, and
the author's own terminal before the store is called (K4b, `client/locus.py`). It is **one function with two
callers**, never two implementations; a second copy is how the two halves would drift apart.

**Why this file is under `core/` and not `server/`** [K4b, 2026-09-05]. Both halves parse the same grammar, and the
locus half now has a caller in `client/`. The client's import graph is asserted (`tests/store/test_walk.py`) to
reach nothing under `server/`, so the pure functions live where both sides can import them without either importing
the other. `server/refs.py` keeps `resolve`, the half that needs a tree.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final, Literal

from .refusal import Refusal

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


class Locus:
    """One file's text, indexed **once** for every ref that cites it [K7b, F27].

    The cost of a locus check is a regex pass over every line — 17 ms for a symbol, 5 ms for an anchor, on a 600 KB
    file — and the shipped shape paid it *per ref*: three refs into one module scanned it three times, and a card
    that cites six functions in one file would have scanned it six. The decode (2.5 ms of 23) was the finding K4b
    recorded; the K7 reproduction found it was 11% of the bill and the passes were the rest. So the passes are here,
    one per file per kind, and a ref is then a set membership or a dict lookup.

    **Each index is built on first use and never before** (C-13, judged here): a file cited by line ranges only is
    never scanned at all; one cited by symbols pays the symbol pass and not the heading pass. Building both eagerly
    would charge every line-range ref a scan it does not need. `lines` is the decoded text, kept because every
    index reads it and the range check needs its length.
    """

    __slots__ = ("_anchors", "_symbols", "lines")

    def __init__(self, data: bytes) -> None:
        self.lines: Sequence[str] = data.decode("utf-8", "replace").split("\n")
        self._anchors: frozenset[str] | None = None
        self._symbols: Mapping[str, int] | None = None

    @property
    def anchors(self) -> frozenset[str]:
        """Every heading's GitHub slug, and its explicit `{#id}` where it has one — one pass, on first use."""
        if self._anchors is None:
            found: set[str] = set()
            for ln in self.lines:
                m = _HEADING.match(ln)
                if m:
                    if m.group("explicit"):
                        found.add(m.group("explicit"))
                    found.add(github_slug(m.group("text")))
            self._anchors = frozenset(found)
        return self._anchors

    @property
    def symbols(self) -> Mapping[str, int]:
        """Every definition's name → how many times it is defined — one pass, on first use. The count is what tells
        `ref.unresolved` from `ref.ambiguous`, and it is why this is a map and not a set."""
        if self._symbols is None:
            counts: dict[str, int] = {}
            for ln in self.lines:
                m = _SYMBOL_DEF.match(ln) or _ASSIGN_DEF.match(ln)
                if m:
                    name = m.group("name")
                    counts[name] = counts.get(name, 0) + 1
            self._symbols = counts
        return self._symbols


def locus_check(ref: Ref, locus: Locus) -> str | None:
    """The other half [Q11]: does the line range, the anchor or the symbol land on anything in this file?

    `None` when it does, else the rule id — `ref.unresolved` or `ref.ambiguous`. A whole-file `Path` ref has no
    locus, so it always passes; the tree already proved the file exists.

    **Pure, and public because it has callers outside the server half.** It takes a `Locus` — the file's text,
    indexed once — rather than a reader, precisely so the caller supplies it from wherever it legitimately has the
    bytes: the assembler from the project checkout at dispatch, the author's terminal from the working tree (K4b).
    The store is the one participant that cannot call it, which is why the check is not there any more — not
    because it stopped mattering. N refs into one file cost one `Locus` and N lookups (F27).
    """
    if ref.kind == "path":
        return None
    if ref.kind == "lines":
        return None if ref.l2 <= len(locus.lines) else "ref.unresolved"
    if ref.kind == "anchor":
        return None if ref.anchor in locus.anchors else "ref.unresolved"
    hits = locus.symbols.get(ref.symbol, 0)
    if hits == 0:
        return "ref.unresolved"
    return None if hits == 1 else "ref.ambiguous"
