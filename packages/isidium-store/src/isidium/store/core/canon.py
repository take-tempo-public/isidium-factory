"""Canonicalization and the content hashes — 03 §5.1 (the build hash), §5.2 (the closure-entry hash), §5.3 (the
canonical forms, language-neutral). Descends from the r3/r4/r5/r6 prototypes, which agree byte-for-byte; the
conformance corpus under tests/conformance is the oracle this module must match.

Every rule here cites the 5.3 row it implements. The value tree is the raw parsed TOML (`toml::Value` in Rust);
the typed model is validated elsewhere and never hashed (W10).
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import re
import unicodedata
from typing import Any, Final

from .refusal import Refusal

SCHEMA: Final = 1  # the card schema version (`schema` in a card head)
CANON: Final = 1  # the canonicalization version (the `canon:` prefix line)
UNIDATA_VERSION: Final[str] = unicodedata.unidata_version  # asserted against `[toolkit] unidata` at start-up

# 5.1 — the B rows of 2.1, in the pinned order; `scope` is the `## Scope` string.
BUILD_KEYS: Final[tuple[str, ...]] = (
    "title",
    "kind",
    "shape",
    "narrative",
    "rules",
    "questions",
    "answers",
    "parent",
    "depends_on",
    "goal",
    "effort",
    "scope_mark",
    "source_narrative",
    "refs",
    "surfaces",
    "acceptance",
    "guidance",
    "x",
    "scope",
)
GATED_KEYS: Final[frozenset[str]] = frozenset(BUILD_KEYS)  # `x` only for gated x.* (the extension schema)
SET_VALUED: Final[frozenset[str]] = frozenset({"depends_on", "surfaces", "tags"})  # 5.3 arrays row
TENDING_KEYS: Final[frozenset[str]] = frozenset(
    {
        "priority",
        "class_of_service",
        "due",
        "sprint",
        "milestone",
        "starts",
        "ends",
        "lane",
        "tags",
        "hold",
        "summary",
        "withdrawn_reason",
    }
)
CLAIMS_KEYS: Final[frozenset[str]] = frozenset({"closures", "reopens"})
LOG_KEYS: Final[frozenset[str]] = frozenset({"see", "renumbered_from"})
META_KEYS: Final[frozenset[str]] = frozenset({"schema", "id", "status", "source"})
KNOWN_HEAD_KEYS: Final[frozenset[str]] = (GATED_KEYS - {"scope"}) | TENDING_KEYS | LOG_KEYS | META_KEYS | CLAIMS_KEYS

# 5.3 strings row — forbidden code points in gated strings, inbox title/body, Updates headers and keys:
# C0/C1 controls except \n and \t; zero-width U+200B–U+200D, U+2060, U+FEFF; bidi controls U+202A–U+202E, U+2066–U+2069.
_FORBIDDEN: Final = re.compile(
    "[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u009f\u200b-\u200d\u2060\ufeff\u202a-\u202e\u2066-\u2069]"
)
_JSON_SHORT: Final[dict[int, str]] = {0x08: "\\b", 0x0C: "\\f", 0x0A: "\\n", 0x0D: "\\r", 0x09: "\\t"}
_I53: Final = 2**53
_I64_MAX: Final = 2**63 - 1


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def forbidden_codepoint(s: str) -> str | None:
    """The first forbidden code point in `s`, or None."""
    m = _FORBIDDEN.search(s)
    return m.group(0) if m else None


def check_string(s: str, path: str = "") -> str:
    """A gated string: no forbidden code points; NFC."""
    ch = forbidden_codepoint(s)
    if ch is not None:
        raise Refusal("canon.forbidden-codepoint", path, f"U+{ord(ch):04X}")
    return nfc(s)


def canon_prose(text: str) -> str:
    """5.3 prose row: CRLF and lone CR → LF; trailing [ \\t] stripped per line; leading/trailing blank lines stripped;
    no trailing newline; NFC. Declared limit (L1): Markdown hard line breaks are erased."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t]+$", "", ln) for ln in text.split("\n")]
    while lines and lines[0] == "":
        lines.pop(0)
    while lines and lines[-1] == "":
        lines.pop()
    return nfc("\n".join(lines))


def _json_string(s: str) -> str:
    """5.3 JSON-escaping row: exactly `"`, `\\`, and U+0000–U+001F (short forms, else \\u00xx lowercase); nothing
    else escaped — not `/`, not U+007F, not U+2028/9; non-ASCII emitted raw."""
    out = ['"']
    for ch in s:
        o = ord(ch)
        if ch == '"':
            out.append('\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif o < 0x20:
            out.append(_JSON_SHORT.get(o, f"\\u{o:04x}"))
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def _canon_value(v: Any, path: str, in_set: bool = False) -> str:
    if isinstance(v, bool):  # bool before int: bool is an int in Python
        if in_set:
            raise Refusal("canon.set-bool", path)
        return "true" if v else "false"
    if isinstance(v, int):
        if abs(v) > _I53 or abs(v) > _I64_MAX:
            raise Refusal("canon.int-range", path, str(v))
        return str(v)
    if isinstance(v, float):
        raise Refusal("canon.float", path)
    if isinstance(v, str):
        return _json_string(check_string(v, path))
    if isinstance(v, _dt.datetime):
        if v.tzinfo is None:
            raise Refusal("canon.datetime-local", path)
        u = v.astimezone(_dt.UTC)
        base = u.strftime("%Y-%m-%dT%H:%M:%S")
        frac = f".{u.microsecond:06d}" if u.microsecond else ""
        return _json_string(base + frac + "Z")
    if isinstance(v, _dt.date):
        return _json_string(v.strftime("%Y-%m-%d"))
    if isinstance(v, (list, tuple)):
        return _canon_array(list(v), path)
    if isinstance(v, dict):
        items = sorted(((check_string(str(k), path + ".<key>"), val) for k, val in v.items()), key=lambda kv: kv[0])
        return "{" + ",".join(_json_string(k) + ":" + _canon_value(val, f"{path}.{k}") for k, val in items) + "}"
    raise Refusal("canon.type", path, type(v).__name__)


def _canon_array(v: list[Any], path: str) -> str:
    key = path.rsplit(".", 1)[-1]
    if key in SET_VALUED:
        if not v:
            return "[]"
        kinds = {type(x) for x in v}
        if bool in kinds:
            raise Refusal("canon.set-bool", path)
        if len(kinds) != 1 or kinds - {int, str}:
            raise Refusal("canon.set-mixed", path)
        items: list[Any] = [nfc(x) if isinstance(x, str) else x for x in v]
        if len(set(items)) != len(items):
            raise Refusal("canon.set-duplicate", path)
        v = sorted(items)  # strings by code point (= UTF-8 byte order), ints by value
    return "[" + ",".join(_canon_value(x, f"{path}[{i}]") for i, x in enumerate(v)) + "]"


def canonical_json(obj: Any) -> str:
    """The canonical JSON of a value tree (5.3): sorted keys, no whitespace, the escaping row, sets sorted."""
    return _canon_value(obj, "$")


def canon_head_value(key: str, value: Any) -> str:
    """The canonical value of one head key — the diff `D` compares these (1.2 step 3)."""
    return _canon_value(value, "$." + key)


def sha256_hex(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def prefixed(schema: int, payload: str) -> bytes:
    """The 5.1 prefix lines: `schema:<n>\\ncanon:<n>\\n` + the canonical JSON."""
    return b"schema:" + str(schema).encode() + b"\ncanon:" + str(CANON).encode() + b"\n" + payload.encode("utf-8")


def build_input(head: dict[str, Any], scope: str | None, gated_x: frozenset[str] = frozenset()) -> dict[str, Any]:
    """The raw value tree before defaulting, restricted to the B keys; `scope` from `## Scope` (absent → omitted,
    empty → ''); `x` restricted to its gated keys — NFC on both sides of the lookup (the draft-6 pin) — and omitted
    when no gated key is present."""
    obj: dict[str, Any] = {k: head[k] for k in BUILD_KEYS if k in head and k not in ("scope", "x")}
    if "x" in head and isinstance(head["x"], dict):
        gated = frozenset(nfc(k) for k in gated_x)
        gx = {k: v for k, v in head["x"].items() if nfc(k) in gated}
        if gx:
            obj["x"] = gx
    if scope is not None:
        obj["scope"] = canon_prose(scope)
    return obj


def build_hash(head: dict[str, Any], scope: str | None, gated_x: frozenset[str] = frozenset()) -> str:
    """5.1: `"sha256:" + hex(sha256(prefix lines + canonical_json(obj)))`; the stored form is the prefixed string."""
    schema = head.get("schema", SCHEMA)
    if not isinstance(schema, int) or isinstance(schema, bool):
        raise Refusal("canon.type", "$.schema", "schema must be an int")
    return "sha256:" + sha256_hex(prefixed(schema, canonical_json(build_input(head, scope, gated_x))))


def policy_build_hash(tree: dict[str, Any], schema: int) -> str:
    """5.1 on a policy-chain entry: the same construction over `config.toml` minus `[history]`, with `schema` = the
    config registry version."""
    obj = {k: v for k, v in tree.items() if k != "history"}
    return "sha256:" + sha256_hex(prefixed(schema, canonical_json(obj)))


def ext_schema_hash(tree: dict[str, Any]) -> str:
    """5.3: the canonicalization over `config.toml [extensions]` without the prefix lines; absent → the bare digest
    `sha256("")` in hex; present → the prefixed string."""
    ext = tree.get("extensions")
    if not ext:
        return sha256_hex(b"")
    return "sha256:" + sha256_hex(canonical_json(ext).encode("utf-8"))


def closure_ref(entry: dict[str, Any]) -> str:
    """5.2: `sha256(canonical_json(entry))` over one closures[]/reopens[] entry as written (`retracted` present), no
    prefix lines, stored inside `ref` as `"c<n>:sha256:<hex>"` / `"o<n>:sha256:<hex>"`. The only claims hash."""
    return f"{entry['id']}:sha256:" + sha256_hex(canonical_json(entry).encode("utf-8"))


def content_address(obj: Any) -> str:
    """A content address for a registry schema document (04 §4): the prefixed digest of its canonical JSON."""
    return "sha256:" + sha256_hex(canonical_json(obj).encode("utf-8"))
