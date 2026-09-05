"""The governed-document grammar (03b §3; 03 §9.1) — one deterministic parser and one emitter per form, parameterized
by a document schema. Forms: Markdown (a card, a page: typed head, fixed sections, the `## History` footer), TOML
(`config.toml`: scalars, tables, the trailing `[history]` table), JSONL (the inbox, the event file).

Descends from the r6 prototype's grammar.py and impl-d1's serializer; the conformance corpus is the oracle:
parse → emit must be a fixed point on every fixture, and two stores must emit byte-identical blobs (4.3).
"""

from __future__ import annotations

import datetime as _dt
import json
import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final, Literal, TypedDict

from .refusal import Refusal

Head = dict[str, Any]
Entry = dict[str, Any]

# 1.15 — the key order of a history entry on its line (the file's layout; the hash sorts keys).
ENTRY_KEY_ORDER: Final[tuple[str, ...]] = (
    "seq",
    "at",
    "by",
    "for",
    "act",
    "fields",
    "build",
    "ref",
    "note",
    "h",
    "sig",
    "batch",
)
# 2.1 — the scalar keys' mutual order (4.3: "every write emits all scalar keys first, among themselves in the
# 2.1 inventory order, so two stores emit byte-identical blobs").
SCALAR_ORDER: Final[tuple[str, ...]] = (
    "schema",
    "id",
    "kind",
    "status",
    "source",
    "scope_mark",
    "title",
    "shape",
    "parent",
    "depends_on",
    "goal",
    "effort",
    "source_narrative",
    "refs",
    "surfaces",
    "priority",
    "class_of_service",
    "due",
    "starts",
    "ends",
    "sprint",
    "milestone",
    "lane",
    "hold",
    "summary",
    "tags",
    "withdrawn_reason",
    "see",
    "renumbered_from",
)
# 1.1 — the pinned table order of a card head.
CARD_TABLE_ORDER: Final[tuple[str, ...]] = (
    "narrative",
    "rules",
    "questions",
    "answers",
    "guidance",
    "acceptance",
    "closures",
    "reopens",
    "x",
)

SectionKind = Literal["prose", "updates"]


@dataclass(frozen=True)
class SectionSpec:
    heading: str
    kind: SectionKind
    required: bool


@dataclass(frozen=True)
class DocSchema:
    """What the parser needs of a Markdown document type: its sections in order, its head's table order, whether the
    footer is required, and the prose bound. The registry loader builds these from `name@version` documents."""

    name: str
    genesis: str  # the genesis prefix: card / page
    sections: tuple[SectionSpec, ...]
    table_order: tuple[str, ...] = ()
    history_required: bool = True
    prose_bound: int = 1 << 20
    key_orders: Mapping[str, tuple[str, ...]] = field(default_factory=dict)  # table path -> pinned key order


CARD: Final = DocSchema(
    "card", "card", (SectionSpec("Scope", "prose", False), SectionSpec("Updates", "updates", False)), CARD_TABLE_ORDER
)
PAGE: Final = DocSchema("page", "page", (SectionSpec("Body", "prose", True),), (), True, 8192)


class UpdateBlock(TypedDict):
    date: str
    title: str
    body: str


@dataclass
class Document:
    """A parsed Markdown governed document. `sections` holds raw prose (Scope / Body) or the Updates blocks."""

    head: Head
    sections: dict[str, str | list[UpdateBlock]] = field(default_factory=dict)
    history: list[Entry] = field(default_factory=list)
    unclassified: list[str] = field(default_factory=list)
    newline: str = "\n"

    def scope(self) -> str | None:
        s = self.sections.get("Scope")
        return s if isinstance(s, str) else None

    def prose(self, heading: str) -> str | None:
        s = self.sections.get(heading)
        return s if isinstance(s, str) else None

    def updates(self) -> list[UpdateBlock]:
        u = self.sections.get("Updates")
        return u if isinstance(u, list) else []

    def head_of(self) -> dict[str, Any]:
        """`{seq, h}` of the last history entry — the compare-and-swap head (1.2 step 2)."""
        e = self.history[-1]
        return {"seq": e["seq"], "h": e["h"]}


# ---- Markdown: parsing --------------------------------------------------------------------------------------------

_UPDATES_HDR: Final = re.compile(r"^### (\d{4}-\d{2}-\d{2})(?: — (.*))?$")
_TABLE_HDR: Final = re.compile(r"^\[\[?([A-Za-z0-9_.\-]+)\]\]?$")
_BARE_KEY: Final = re.compile(r"^[A-Za-z0-9_\-]+$")


def split_head(raw: str) -> tuple[str, list[str], str]:
    """9.1's first half: the fence on line 1 with info string exactly `toml`, the first block is the head. Returns
    the head's text, the body lines after the closing fence, and the newline the file uses.

    Shared by `parse_markdown` and `parse_head` [K4b, 2026-09-05] so the fence grammar has one home: a reader that
    wants one key of a card must not grow its own idea of where the head ends."""
    if raw.startswith("﻿"):
        raise Refusal("head.bom")
    newline = "\r\n" if "\r\n" in raw else "\n"
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    if not lines or lines[0] != "```toml":
        raise Refusal("head.fence", "", "line 1 must be ```toml")
    try:
        close = lines.index("```", 1)
    except ValueError:
        raise Refusal("head.fence", "", "no closing fence") from None
    return "\n".join(lines[1:close]), lines[close + 1 :], newline


def load_head(head_text: str) -> Head:
    """The head's TOML, with the two refusals that name what went wrong (a fence inside a string, or not TOML)."""
    try:
        head: Head = tomllib.loads(head_text)
    except tomllib.TOMLDecodeError as e:
        if head_text.count('"""') % 2 or head_text.count("'''") % 2:
            raise Refusal("head.fence-in-string") from None
        raise Refusal("head.toml", "", str(e)) from None
    return head


def parse_head(raw: str) -> Head:
    """The head alone, for a reader that needs one key of a card and not its sections — the author's terminal
    reading a card's `refs` before `ratify <id>` (K4b). The same fence and TOML rules as `parse_markdown`, by
    construction; the table-order check needs the schema and stays the full parse's."""
    return load_head(split_head(raw)[0])


def parse_markdown(raw: str, schema: DocSchema) -> Document:
    """9.1: the fence on line 1 with info string exactly `toml`; the first block is the head; fence-aware `##`
    sections in the schema's order; `## History` last; everything else `body.unclassified`."""
    head_text, body, newline = split_head(raw)
    head = load_head(head_text)
    _check_table_order(head_text, schema.table_order)

    parts: list[tuple[str | None, list[str]]] = [(None, [])]
    in_fence = False
    for ln in body:
        if ln.startswith("```"):
            in_fence = not in_fence
        if not in_fence and ln.startswith("## "):
            parts.append((ln[3:], []))
        else:
            parts[-1][1].append(ln)
    doc = Document(head=head, newline=newline)
    wanted = [s.heading for s in schema.sections] + ["History"]
    kinds = {s.heading: s.kind for s in schema.sections}
    seen: list[str] = []
    for heading, content in parts:
        if heading is None:
            if any(x.strip() for x in content):
                doc.unclassified.append("\n".join(content))
            continue
        if heading not in wanted:
            doc.unclassified.append("## " + heading)
            continue
        if seen and seen[-1] == "History":
            raise Refusal("body.history-position", heading)
        if seen and wanted.index(heading) < wanted.index(seen[-1]):
            raise Refusal("body.section-order", heading)
        seen.append(heading)
        if heading == "History":
            doc.history = _parse_history(content)
        elif kinds[heading] == "updates":
            doc.sections[heading] = _parse_updates(content, doc)
        else:
            prose = "\n".join(content).strip("\n")
            if len(prose.encode("utf-8")) > schema.prose_bound:
                raise Refusal("body.prose-bound", heading)
            doc.sections[heading] = prose
    for spec in schema.sections:
        if spec.required and spec.heading not in doc.sections:
            raise Refusal("body.section-missing", spec.heading)
    if schema.history_required and "History" not in seen:
        raise Refusal("body.history-missing")
    if "History" in seen and seen[-1] != "History":
        raise Refusal("body.history-position")
    return doc


def _check_table_order(head_text: str, order: tuple[str, ...]) -> None:
    pos = -1
    for ln in head_text.split("\n"):
        m = _TABLE_HDR.match(ln.strip())
        if not m:
            continue
        root = m.group(1).split(".")[0]
        if root not in order:
            continue
        i = order.index(root)
        if i < pos:
            raise Refusal("head.table-order", root)
        pos = i


def _parse_history(content: list[str]) -> list[Entry]:
    body = list(content)
    while body and body[-1].strip() == "":
        body.pop()
    while body and body[0].strip() == "":
        body.pop(0)
    if len(body) < 4 or body[0] != "```toml" or body[-1] != "```" or body[1] != "history = [" or body[-2] != "]":
        raise Refusal("body.history-shape")
    entries: list[Entry] = []
    for ln in body[2:-2]:
        if not (ln.startswith("  { ") and ln.endswith(" },")):
            raise Refusal("body.history-shape", "", ln[:40])
        try:
            e = tomllib.loads("e = " + ln[2:-1])["e"]
        except tomllib.TOMLDecodeError as err:
            raise Refusal("body.history-shape", "", str(err)) from None
        keys = list(e)
        if [k for k in ENTRY_KEY_ORDER if k in keys] != keys:
            raise Refusal("body.history-shape", "", "key order")
        entries.append(e)
    return entries


def _parse_updates(content: list[str], doc: Document) -> list[UpdateBlock]:
    blocks: list[UpdateBlock] = []
    bodies: list[list[str]] = []
    pre: list[str] = []
    for ln in content:
        m = _UPDATES_HDR.match(ln)
        if m:
            blocks.append({"date": m.group(1), "title": m.group(2) or "", "body": ""})
            bodies.append([])
        elif blocks:
            bodies[-1].append(ln)
        else:
            pre.append(ln)
    if any(x.strip() for x in pre):
        doc.unclassified.append("\n".join(pre))
    for b, lines in zip(blocks, bodies, strict=True):
        b["body"] = "\n".join(lines).strip("\n")
    return blocks


# ---- TOML values: emitting ----------------------------------------------------------------------------------------


def toml_key(k: str) -> str:
    return k if _BARE_KEY.match(k) else toml_string(k)


def toml_string(s: str) -> str:
    """A TOML basic string: `"` and `\\` escaped, `\\n` and `\\t` short, other controls and U+007F as `\\uXXXX`."""
    out = ['"']
    for ch in s:
        if ch == '"':
            out.append('\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\t":
            out.append("\\t")
        elif ord(ch) < 0x20 or ch == "\x7f":
            out.append(f"\\u{ord(ch):04X}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def toml_value(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):  # never valid in a governed document; emitted only so a refused fixture can be built
        return repr(v)
    if isinstance(v, str):
        return toml_string(v)
    if isinstance(v, _dt.datetime):
        return v.isoformat().replace("+00:00", "Z")
    if isinstance(v, _dt.date):
        return v.isoformat()
    if isinstance(v, list):
        return "[" + ", ".join(toml_value(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{ " + ", ".join(f"{toml_key(k)} = {toml_value(x)}" for k, x in v.items()) + " }"
    raise Refusal("emit.type", "", type(v).__name__)


def _inline_ok(v: Any) -> bool:
    """Inline when it is a scalar, a list of scalars, or a (nested) dict of scalars — tending keys are flat (9.3)."""
    if isinstance(v, dict):
        return all(_inline_ok(x) for x in v.values())
    if isinstance(v, list):
        return all(not isinstance(x, (list, dict)) for x in v)
    return True


def _is_array_of_tables(v: Any) -> bool:
    return isinstance(v, list) and bool(v) and isinstance(v[0], dict)


def _ordered_items(
    path: str, table: Mapping[str, Any], key_orders: Mapping[str, tuple[str, ...]]
) -> list[tuple[str, Any]]:
    order = key_orders.get(path) or key_orders.get("*", ())
    known = [(k, table[k]) for k in order if k in table]
    rest = [(k, v) for k, v in table.items() if k not in order]
    return known + rest


def emit_table(
    lines: list[str],
    name: str,
    v: Any,
    key_orders: Mapping[str, tuple[str, ...]] | None = None,
    toml_doc: bool = False,
) -> None:
    """`[name]` with its scalar keys, then `[name.sub]` tables; a list of tables as `[[name]]` per item.
    Markdown-head style (default): an inline-able dict stays inline (`hold = { … }`, 9.3) and a table with only
    sub-tables emits no header (`guidance` → `[[guidance.avoid]]`). TOML-document style (`toml_doc`): every dict is a
    sub-table and the header is always emitted (`[extensions]` then `[extensions.x]`; `[payload.context]`)."""
    ko = key_orders or {}
    if isinstance(v, list):
        for item in v:
            lines.append("")
            lines.append(f"[[{name}]]")
            _emit_table_body(lines, name, item, ko, toml_doc)
        return
    if toml_doc:
        items = _ordered_items(name, v, ko)
        scalars = [(k, x) for k, x in items if not isinstance(x, dict) and not _is_array_of_tables(x)]
        subs = [(k, x) for k, x in items if isinstance(x, dict) or _is_array_of_tables(x)]
        lines.append("")
        lines.append(f"[{name}]")
        for k, x in scalars:
            lines.append(f"{toml_key(k)} = {toml_value(x)}")
        for k, x in subs:
            emit_table(lines, f"{name}.{toml_key(k)}", x, ko, True)
        return
    scalars = [
        (k, x)
        for k, x in _ordered_items(name, v, ko)
        if not _is_array_of_tables(x) and not (isinstance(x, dict) and not _inline_ok(x))
    ]
    subs = [
        (k, x)
        for k, x in _ordered_items(name, v, ko)
        if _is_array_of_tables(x) or (isinstance(x, dict) and not _inline_ok(x))
    ]
    if scalars or not subs:
        lines.append("")
        lines.append(f"[{name}]")
        for k, x in scalars:
            lines.append(f"{toml_key(k)} = {toml_value(x)}")
    for k, x in subs:
        emit_table(lines, f"{name}.{toml_key(k)}", x, ko)


def _emit_table_body(
    lines: list[str], name: str, item: Mapping[str, Any], ko: Mapping[str, tuple[str, ...]], toml_doc: bool = False
) -> None:
    for k, x in _ordered_items(name, item, ko):
        if _is_array_of_tables(x) or (toml_doc and isinstance(x, dict)):
            emit_table(lines, f"{name}.{toml_key(k)}", x, ko, toml_doc)
        else:
            lines.append(f"{toml_key(k)} = {toml_value(x)}")


def emit_head(head: Head, table_order: tuple[str, ...], key_orders: Mapping[str, tuple[str, ...]] | None = None) -> str:
    """4.3: scalars first (the 2.1 mutual order; unknown keys after, sorted), then the tables in the pinned order."""
    ko = key_orders or {}
    lines: list[str] = []
    tables: list[str] = []
    order = {k: i for i, k in enumerate(SCALAR_ORDER)}
    for k in sorted(head, key=lambda k: (order.get(k, len(order)), k)):
        v = head[k]
        is_table = (
            (isinstance(v, dict) and not _inline_ok(v))
            or _is_array_of_tables(v)
            or (isinstance(v, dict) and k in table_order)
        )
        if is_table:
            tables.append(k)
        else:
            lines.append(f"{k} = {toml_value(v)}")
    for k in sorted(tables, key=lambda k: (table_order.index(k) if k in table_order else len(table_order), k)):
        emit_table(lines, k, head[k], ko)
    return "\n".join(lines)


def emit_entry(e: Mapping[str, Any]) -> str:
    return "  { " + ", ".join(f"{k} = {toml_value(e[k])}" for k in ENTRY_KEY_ORDER if k in e) + " },"


def emit_markdown(doc: Document, schema: DocSchema) -> str:
    out = ["```toml", emit_head(doc.head, schema.table_order, schema.key_orders), "```"]
    for spec in schema.sections:
        if spec.heading not in doc.sections:
            continue
        out += ["", f"## {spec.heading}", ""]
        if spec.kind == "updates":
            for b in doc.updates():
                hdr = f"### {b['date']} — {b['title']}" if b["title"] else f"### {b['date']}"
                out += [hdr, "", b["body"], ""]
        else:
            out.append(doc.prose(spec.heading) or "")
    out += ["", "## History", "", "```toml", "history = ["]
    out += [emit_entry(e) for e in doc.history]
    out += ["]", "```", ""]
    text = "\n".join(out)
    return text if doc.newline == "\n" else text.replace("\n", doc.newline)


def append_history_line(raw: str, entry: Mapping[str, Any]) -> str:
    """1.1 / 1.15: the append is a line insertion before the `]` at end-of-file; the file's own line endings kept."""
    nl = "\r\n" if "\r\n" in raw else "\n"
    tail = nl + "]" + nl + "```" + nl
    if not raw.endswith(tail):
        raise Refusal("body.history-shape", "", "tail")
    return raw[: -len(tail)] + nl + emit_entry(entry) + tail


# ---- TOML document type (config.toml): the chain in the trailing [history] table ----------------------------------


@dataclass(frozen=True)
class TomlOrders:
    """The pinned orders of a TOML document type (04 §1): scalars, tables (dotted headers as pinned), per-table key
    orders, and the key order of array-of-tables rows."""

    scalar_order: tuple[str, ...]
    table_order: tuple[str, ...]
    key_orders: Mapping[str, tuple[str, ...]] = field(default_factory=dict)


_CFG_HEADER: Final = re.compile(r"^\[(\[)?\s*([A-Za-z0-9_.\"'-]+?)\s*\]?\]\s*(#.*)?$")
_CFG_KEY: Final = re.compile(r"^([A-Za-z0-9_-]+)\s*=")


def config_grammar_refusals(text: str, orders: TomlOrders) -> list[Refusal]:
    """03b §3 / 04 §1 / K-8: scalars first in inventory order, tables in the pinned order, `[history]` last with
    `entries = [ … ]`, one inline table per line, `]` alone. Collected, never raised — the validator reports all."""
    rs: list[Refusal] = []
    if text.startswith("﻿"):
        rs.append(Refusal("head.toml", "", "BOM rejected"))
        text = text.lstrip("﻿")
    lines = [ln.rstrip("\r") for ln in text.split("\n")]
    scalars: list[str] = []
    headers: list[tuple[int, str]] = []
    for i, ln in enumerate(lines):
        m = _CFG_HEADER.match(ln)
        if m:
            headers.append((i, m.group(2).strip("\"'")))
        elif not headers:
            km = _CFG_KEY.match(ln)
            if km:
                scalars.append(km.group(1))
    order = [orders.scalar_order.index(k) for k in scalars if k in orders.scalar_order]
    if order != sorted(order):
        rs.append(Refusal("head.scalar-order", "", "scalars out of the inventory order"))
    roots = [n.split(".")[0] for _i, n in headers]
    idxs = [orders.table_order.index(r) for r in roots if r in orders.table_order]
    if idxs != sorted(idxs):
        rs.append(Refusal("head.table-order", "", "tables out of the pinned order"))
    hist = [i for i, n in headers if n == "history"]
    if not hist:
        if headers or scalars:
            rs.append(Refusal("head.history-position", "history", "[history] absent (the last table in the file)"))
        return rs
    if any(i > hist[0] for i, _n in headers):
        rs.append(Refusal("head.history-position", "history", "[history] is not the last table"))
    return rs + _config_history_shape(lines[hist[0] + 1 :])


def _config_history_shape(body: list[str]) -> list[Refusal]:
    sig = [ln for ln in body if ln.strip()]
    if not sig or sig[0].replace(" ", "") != "entries=[":
        return [Refusal("head.history-shape", "history.entries", "expected 'entries = [' with ']' alone on its line")]
    closed = False
    for ln in sig[1:]:
        st = ln.strip()
        if closed:
            return [Refusal("head.history-position", "history", "content after the entries array")]
        if st == "]":
            closed = True
        elif not (st.startswith("{") and st.endswith("},")):
            return [Refusal("head.history-shape", "history.entries", f"not one inline table per line: {st[:40]!r}")]
    if not closed:
        return [Refusal("head.history-shape", "history.entries", "']' never closes entries")]
    return []


def parse_config(raw: str, orders: TomlOrders) -> tuple[dict[str, Any], list[Entry], list[Refusal]]:
    """The tree (without `history`), the policy chain's entries, and the grammar refusals. A bare parse failure is one
    `head.toml` refusal with an empty tree."""
    rs = config_grammar_refusals(raw, orders)
    try:
        tree = tomllib.loads(raw.lstrip("﻿"))
    except tomllib.TOMLDecodeError as e:
        return {}, [], [*rs, Refusal("head.toml", "", str(e))]
    hist = tree.pop("history", None)
    entries: list[Entry] = list(hist.get("entries", [])) if isinstance(hist, dict) else []
    for ent in entries:
        if isinstance(ent, dict) and [k for k in ENTRY_KEY_ORDER if k in ent] != list(ent):
            rs.append(Refusal("head.history-shape", "history.entries", "key order"))
    return tree, entries, rs


def emit_config(tree: Mapping[str, Any], history: list[Entry], orders: TomlOrders, newline: str = "\n") -> str:
    """04 §1 / 03b §3: scalars in inventory order (unknown after), tables in the pinned order, array-of-tables rows,
    `[history]` last with `entries = [ … ]`, one inline table per line, `]` alone on its line."""
    lines: list[str] = []
    known = set(orders.scalar_order) | set(orders.table_order)
    for k in orders.scalar_order:
        if k in tree and not isinstance(tree[k], (dict, list)):
            lines.append(f"{toml_key(k)} = {toml_value(tree[k])}")
    for k, v in tree.items():
        if k not in known and not isinstance(v, (dict, list)):
            lines.append(f"{toml_key(k)} = {toml_value(v)}")
    for name in orders.table_order:
        if name == "history" or name not in tree:
            continue
        emit_table(lines, name, tree[name], orders.key_orders, toml_doc=True)
    for k, v in tree.items():
        if k not in known and k != "history" and isinstance(v, (dict, list)):
            emit_table(lines, k, v, orders.key_orders, toml_doc=True)
    lines += ["", "[history]", "entries = ["]
    lines += [emit_entry(e) for e in history]
    lines += ["]", ""]
    return newline.join(lines)


# ---- JSONL record-slot documents (the inbox, the event file) --------------------------------------------------------


def parse_jsonl(raw: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for ln in raw.replace("\r\n", "\n").split("\n"):
        if ln.strip():
            rec = json.loads(ln)
            if not isinstance(rec, dict):
                raise Refusal("record.shape", "", "one JSON object per line")
            out.append(rec)
    return out


def emit_jsonl_line(rec: Mapping[str, Any]) -> str:
    return json.dumps(rec, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n"
