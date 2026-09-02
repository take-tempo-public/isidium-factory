"""The schema of schemas (04 §4): a registry schema document is one TOML value tree discriminated on `form`
(`markdown` {head, sections, footer} · `toml` {scalars, tables, footer} · `jsonl` {record} · `json` {record});
every key row carries `name`, `type` (the closed type set), optional `class` and `required_when` (a typed membership
table — an AND of `{ field, in = […] }` tests over kind/status/shape, L2-5), and constraints from the **closed
nine-member vocabulary [owner-ratified 7bc.9, Y3]**:

    default · enum · pattern · range · subset-of · dynamic-table · array-of-tables · immutable · reserved

What the nine cannot say, a schema cannot require (the seam is a registry version bump). Serialization (D1-3): a
constraint rides its key row as an inline-table value — `default = { value }` · `enum = [ … ]` · `pattern = "re"` ·
`range = { min?, max? }` · `subset-of = { of = […] } | { ref = "<set>" }` · `dynamic-table = { … }` ·
`array-of-tables = true` · `immutable = true` · `reserved = {} | { values = […] }`; a table row nests its key rows
under `keys`. Descends from impl-d1's registry.py (the 104-check closing run).
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any, Final

from ..core.refusal import Refusal

CLOSED_TYPES: Final[tuple[str, ...]] = ("string", "int", "bool", "date", "array", "table")  # the 5.3 forms
FORMS: Final[tuple[str, ...]] = ("markdown", "toml", "jsonl", "json")
FORM_PARTS: Final[dict[str, tuple[str, ...]]] = {
    "markdown": ("head", "sections", "footer"),
    "toml": ("scalars", "tables", "footer"),
    "jsonl": ("record",),
    "json": ("record",),
}
CONSTRAINTS: Final[tuple[str, ...]] = (
    "default",
    "enum",
    "pattern",
    "range",
    "subset-of",
    "dynamic-table",
    "array-of-tables",
    "immutable",
    "reserved",
)
CLASSES: Final[tuple[str, ...]] = ("gated", "tending", "log", "claims", "meta")  # 03 §1.7 (+ ext classes ⊆)
_KEYROW_CONSTRAINTS: Final = (
    "default",
    "enum",
    "pattern",
    "range",
    "subset-of",
    "dynamic-table",
    "immutable",
    "reserved",
)
_TABLEROW_KEYS: Final = ("name", "keys", "array-of-tables", "dynamic-table", "default", "reserved")
_DYNTABLE_KEYS: Final = ("key-grammar", "over", "members", "member-keys", "declares", "value-type")
_RW_FIELDS: Final = ("kind", "status", "shape")  # L2-5: the closed field set
_SECTION_KEYS: Final = ("name", "kind", "max_bytes", "headings_allowed", "fence", "key")
_PY_TYPE: Final[dict[str, type]] = {"string": str, "int": int, "bool": bool, "array": list, "table": dict}
_NAME_RE: Final = re.compile(r"^[a-z][a-z0-9_.-]*$")
SchemaDoc = dict[str, Any]


def is_type(v: Any, t: str) -> bool:
    py = _PY_TYPE.get(t)
    if py is None:
        return t == "date"
    return isinstance(v, py) and not (t == "int" and isinstance(v, bool))


def _bad(rs: list[Refusal], path: str, msg: str) -> None:
    rs.append(Refusal("registry.form", path, msg))


def check_required_when(
    v: Any, path: str, rs: list[Refusal], rule_type: str = "registry.form", rule_enum: str = "registry.form"
) -> None:
    """L2-5: an AND of `{ field, in = […] }` tests; a string expression is refused."""
    if not isinstance(v, list):
        rs.append(
            Refusal(
                rule_type, path, "required_when must be an array of membership tests (a string expression is refused)"
            )
        )
        return
    for j, test in enumerate(v):
        p = f"{path}[{j}]"
        if not isinstance(test, dict):
            rs.append(Refusal(rule_type, p, "each test is { field, in = [...] }"))
            continue
        for k in test:
            if k not in ("field", "in"):
                rs.append(Refusal(rule_enum, f"{p}.{k}", "test keys: field, in"))
        if test.get("field") not in _RW_FIELDS:
            rs.append(Refusal(rule_enum, f"{p}.field", f"field must be in {list(_RW_FIELDS)}"))
        vin = test.get("in")
        if not isinstance(vin, list) or not vin or any(not isinstance(x, str) for x in vin):
            rs.append(Refusal(rule_type, f"{p}.in", "a non-empty array of enum member names"))


def _check_constraint(name: str, v: Any, row_type: str | None, path: str, rs: list[Refusal]) -> None:
    if name == "default":
        if not isinstance(v, dict) or set(v) != {"value"}:
            _bad(rs, path, "default = { value = <v> }")
        elif row_type in _PY_TYPE and not is_type(v["value"], row_type):
            _bad(rs, path, f"default value does not match the row type {row_type!r}")
    elif name == "enum":
        if not isinstance(v, list) or not v or any(not isinstance(x, str) for x in v):
            _bad(rs, path, "enum = a non-empty array of member names")
    elif name == "pattern":
        if not isinstance(v, str):
            _bad(rs, path, "pattern = a regex in the shared dialect")
        else:
            try:
                re.compile(v)
            except re.error as e:
                _bad(rs, path, f"pattern does not compile: {e}")
    elif name == "range":
        if (
            not isinstance(v, dict)
            or not v
            or any(k not in ("min", "max") for k in v)
            or any(isinstance(x, bool) or not isinstance(x, int) for x in v.values())
        ):
            _bad(rs, path, "range = { min?, max? } with int bounds, at least one")
    elif name == "subset-of":
        if not isinstance(v, dict) or set(v) not in ({"of"}, {"ref"}):
            _bad(rs, path, 'subset-of = { of = [...] } | { ref = "<set>" }')
        elif "of" in v and (not isinstance(v["of"], list) or not v["of"]):
            _bad(rs, path, "subset-of.of = a non-empty array")
        elif "ref" in v and not isinstance(v["ref"], str):
            _bad(rs, path, "subset-of.ref = a set name")
    elif name == "dynamic-table":
        if not isinstance(v, dict):
            _bad(rs, path, "dynamic-table = a table")
            return
        for k in v:
            if k not in _DYNTABLE_KEYS:
                _bad(rs, f"{path}.{k}", f"dynamic-table keys: {list(_DYNTABLE_KEYS)}")
        members = v.get("members") or {}
        if isinstance(members, dict):
            for mname, mkeys in members.items():
                if isinstance(mkeys, list):
                    for j, krow in enumerate(mkeys):
                        check_key_row(krow, f"{path}.members.{mname}[{j}]", rs)
        for j, krow in enumerate(v.get("member-keys") or []):
            check_key_row(krow, f"{path}.member-keys[{j}]", rs)
    elif name == "array-of-tables":
        if v is not True:
            _bad(rs, path, "array-of-tables = true")
    elif name == "immutable":
        if v is not True:
            _bad(rs, path, "immutable = true")
    elif name == "reserved" and (not isinstance(v, dict) or any(k != "values" for k in v)):
        _bad(rs, path, "reserved = {} | { values = [...] }")


def check_key_row(row: Any, path: str, rs: list[Refusal]) -> None:
    if not isinstance(row, dict):
        _bad(rs, path, "a key row is a table")
        return
    for k in row:
        if k in ("name", "type", "class", "required_when"):
            continue
        if k not in _KEYROW_CONSTRAINTS:
            _bad(rs, f"{path}.{k}", f"not in the closed constraint vocabulary {list(CONSTRAINTS)}")
    name = row.get("name")
    if not isinstance(name, str) or not _NAME_RE.match(name):
        _bad(rs, f"{path}.name", "a key row names its key")
    if row.get("type") not in CLOSED_TYPES:
        _bad(rs, f"{path}.type", f"{row.get('type')!r} not in the closed type set {list(CLOSED_TYPES)}")
    if "class" in row and row["class"] not in CLASSES:
        _bad(rs, f"{path}.class", f"class in {list(CLASSES)}")
    if "required_when" in row:
        check_required_when(row["required_when"], f"{path}.required_when", rs)
    if "dynamic-table" in row and row.get("type") != "table":
        _bad(rs, f"{path}.dynamic-table", "dynamic-table only on a table-typed key")
    for k in _KEYROW_CONSTRAINTS:
        if k in row:
            _check_constraint(k, row[k], row.get("type"), f"{path}.{k}", rs)


def check_table_row(trow: Any, path: str, rs: list[Refusal]) -> None:
    if not isinstance(trow, dict):
        _bad(rs, path, "a table row is a table")
        return
    for k in trow:
        if k not in _TABLEROW_KEYS:
            msg = (
                "a table row carries table-level members only"
                if k in ("enum", "pattern", "range", "subset-of", "immutable")
                else f"not in the closed constraint vocabulary {list(CONSTRAINTS)}"
            )
            _bad(rs, f"{path}.{k}", msg)
    name = trow.get("name")
    if not isinstance(name, str) or not _NAME_RE.match(name):
        _bad(rs, f"{path}.name", "a table row names its table")
    for k in ("array-of-tables", "dynamic-table", "default", "reserved"):
        if k in trow:
            _check_constraint(k, trow[k], "array" if k == "default" else None, f"{path}.{k}", rs)
    for j, krow in enumerate(trow.get("keys", [])):
        check_key_row(krow, f"{path}.keys[{j}]", rs)


def check_section_row(srow: Any, path: str, rs: list[Refusal]) -> None:
    if not isinstance(srow, dict):
        _bad(rs, path, "a section row is a table")
        return
    for k in srow:
        if k not in _SECTION_KEYS:
            _bad(rs, f"{path}.{k}", f"section row keys: {list(_SECTION_KEYS)}")
    if srow.get("kind") not in ("prose", "record"):
        _bad(rs, f"{path}.kind", "a prose slot or a record slot")


def _check_scalar_against_row(doc: Mapping[str, Any], row: Mapping[str, Any], rs: list[Refusal]) -> None:
    k = row["name"]
    if k not in doc:
        if row.get("required_when") == []:
            _bad(rs, k, "required scalar absent")
        return
    v = doc[k]
    if not is_type(v, row["type"]):
        _bad(rs, k, f"expected {row['type']}")
        return
    if "enum" in row and v not in row["enum"]:
        _bad(rs, k, f"{v!r} not in {row['enum']}")
    if "pattern" in row and isinstance(v, str) and not re.fullmatch(row["pattern"], v):
        _bad(rs, k, f"{v!r} does not match {row['pattern']!r}")
    if "range" in row and isinstance(v, int) and not isinstance(v, bool):
        r = row["range"]
        if ("min" in r and v < r["min"]) or ("max" in r and v > r["max"]):
            _bad(rs, k, f"{v} outside {r}")


def validate_schema_document(doc: Mapping[str, Any], registry_schema: Mapping[str, Any]) -> list[Refusal]:
    """Validate one schema document's value tree against `registry@1` (the schema of schemas). The fixed point is
    `validate_schema_document(REGISTRY, REGISTRY) == []` — over the full constraint-bearing form (Y3)."""
    rs: list[Refusal] = []
    for row in registry_schema["scalars"]:
        _check_scalar_against_row(doc, row, rs)
    form = doc.get("form")
    parts: Sequence[str] = FORM_PARTS.get(str(form), ())
    for k in doc:
        if k in ("name", "version", "form"):
            continue
        if k not in parts:
            _bad(rs, k, f"a {form!r} schema cannot declare {k!r}" if form in FORMS else "unknown part")
    for j, row in enumerate(doc.get("head", []) or []):
        check_key_row(row, f"head[{j}]", rs)
    for j, row in enumerate(doc.get("scalars", []) or []):
        check_key_row(row, f"scalars[{j}]", rs)
    for j, trow in enumerate(doc.get("tables", []) or []):
        check_table_row(trow, f"tables[{trow.get('name', j) if isinstance(trow, dict) else j}]", rs)
    for j, srow in enumerate(doc.get("sections", []) or []):
        check_section_row(srow, f"sections[{j}]", rs)
    for j, row in enumerate(doc.get("record", []) or []):
        check_key_row(row, f"record[{j}]", rs)
    return rs
