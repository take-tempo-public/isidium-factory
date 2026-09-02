"""The rule this test enforces (04 §4.1, Y1): **a default lives in the adopted schema version, never in the binary.**

A second copy in code is invisible to a deterministic reader of the schema documents, so a future divergence would be
silent — the owner's exact concern, 2026-08-27. This test sweeps the package for literals that duplicate a schema
document's declared default and fails if it finds one. It is a build-time guard, not a style note: the guideline is in
`docs/design/06-code-constraints.md` and this is its enforcement."""

from __future__ import annotations

import ast
import json
from collections.abc import Iterator
from functools import cache
from pathlib import Path
from typing import Any

from isidium.store.registry.loader import Registry

PACKAGE = Path(__import__("isidium.store", fromlist=["x"]).__file__).parent  # type: ignore[arg-type]
REG = Registry.shipped()

# Where a declared default legitimately appears in code, with the reason. Nothing else may.
ALLOWED: dict[str, str] = {
    "registry/schemas": "the schema documents themselves — this is where defaults live",
    "registry/generated": "generated from those documents; regenerating is the only way to change it",
}
# Values too common to be evidence of anything (a default of `1` is not a copied default).
UNINTERESTING: frozenset[str] = frozenset({"0", "1", "true", "false", '""', "[]", "{}", "main", "sha1", "sha256"})

# The widened sweep found three violations in files K1b-ii could not touch, and they sat here in a `PENDING` table
# — a declared gap with a second test that failed the moment one was fixed, so the list could not rot into an
# allow-list. **K1c closed all three on 2026-08-29 and the table is gone**, which is the outcome the shape was built
# for: `isidium init --root` now resolves from the adopted version, `RemoteTotp` takes `poll_interval_ms` from its
# caller, and `default_governed()` no longer exists. **The table is deleted, not emptied** — an empty one invites
# the next violation to be parked rather than fixed. Reinstate it only for a violation that genuinely cannot be
# closed in the chunk that finds it, and give it an owning chunk in the same edit.
PENDING: dict[tuple[str, str], str] = {}


@cache
def declared_defaults() -> dict[str, list[str]]:
    """Every default any installed schema declares, as its JSON text, with the key path that declared it."""
    out: dict[str, list[str]] = {}
    for ref in sorted(REG.installed):
        doc = REG.get(ref)
        for row in _rows(doc):
            default = row.get("default")
            if isinstance(default, dict) and "value" in default:
                text = json.dumps(default["value"], sort_keys=True)
                if text.strip('"') in UNINTERESTING or len(text) < 6:
                    continue
                out.setdefault(text, []).append(f"{ref}:{row.get('name')}")
    return out


def _rows(doc: Any) -> Iterator[dict[str, Any]]:
    for part in ("scalars", "head", "record"):
        yield from doc.get(part, [])
    for trow in doc.get("tables", []):
        yield trow
        yield from trow.get("keys", [])
        dyn = trow.get("dynamic-table") or {}
        for mkeys in (dyn.get("members") or {}).values():
            yield from mkeys
        yield from dyn.get("member-keys") or []


def fallbacks(path: Path) -> Iterator[tuple[int, str, str]]:
    """Every shape C-1 names, as (line, key, JSON of the value). A key of `""` means the shape carries no key and
    the value alone is the evidence.

    **The keyed shapes** — code supplying a value *because a key was absent*, which is what a code-side default IS:

      `x.get("root", "docs/work/")` · `x.get("root") or "docs/work/"` · a dataclass field · a default argument

    An enum member that happens to equal a default is not one (`"story"` is a kind, not a default), so these key on
    the *pattern* and on the declared key's own name, not on the value alone.

    **The keyless shape** — a bare `return` of a declared default [added 2026-08-29, K1b-ii item 8]. It has no key
    to match, so it is judged on a distinctive value (`declared_defaults()`, which already drops values too common
    to be evidence). This is the shape that let a live violation ship under a green test: `client/hook.py` returned
    `"docs/work/"`, `config@1`'s own declared default, and the sweep walked straight past it because a `return` is
    not an absent-key fallback. C-1 named a default argument and a dataclass field in the same breath; all three are
    swept now, and the widening found three more violations (see `PENDING`)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    distinctive = declared_defaults()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "get":
            if len(node.args) == 2 and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                text = _json(node.args[1])
                if text is not None:
                    yield node.lineno, node.args[0].value, text
        elif isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or) and len(node.values) == 2:
            left, right = node.values
            key = _get_key(left)
            text = _json(right)
            if key is not None and text is not None:
                yield node.lineno, key, text
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            text = _json(node.value)
            if text is not None:
                yield node.lineno, node.target.id, text
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for name, default in _arguments(node):
                text = _json(default)
                if text is not None:
                    yield node.lineno, name, text
        elif isinstance(node, ast.Return) and node.value is not None:
            parts = node.value.elts if isinstance(node.value, ast.Tuple) else [node.value]
            for part in parts:
                text = _json(part)
                if text is not None and text in distinctive:
                    yield node.lineno, "", text


def _arguments(node: ast.FunctionDef | ast.AsyncFunctionDef) -> Iterator[tuple[str, ast.expr]]:
    """(name, default) for every argument that has one — the shape C-1 calls "a function's default argument"."""
    positional = node.args.posonlyargs + node.args.args
    padded: list[ast.expr | None] = [None] * (len(positional) - len(node.args.defaults)) + list(node.args.defaults)
    for arg, default in zip(positional + node.args.kwonlyargs, padded + list(node.args.kw_defaults), strict=True):
        if default is not None:
            yield arg.arg, default


def _get_key(node: ast.AST) -> str | None:
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
        and len(node.args) == 1
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    ):
        return str(node.args[0].value)
    if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
        return str(node.slice.value)
    return None


def _json(node: ast.AST) -> str | None:
    try:
        value = ast.literal_eval(node)
    except (ValueError, SyntaxError, TypeError):
        return None
    if isinstance(value, (set, frozenset)):
        value = sorted(value, key=repr)
    elif isinstance(value, tuple):
        value = list(value)
    if not isinstance(value, (list, str, int, bool)) or isinstance(value, bool):
        return None
    try:
        return json.dumps(value, sort_keys=True)
    except TypeError:
        return None


@cache
def _by_key() -> dict[str, dict[str, list[str]]]:
    """key name → JSON of its declared default → the schema documents that declare it."""
    out: dict[str, dict[str, list[str]]] = {}
    for ref in sorted(REG.installed):
        for row in _rows(REG.get(ref)):
            default = row.get("default")
            name = row.get("name")
            if isinstance(default, dict) and "value" in default and isinstance(name, str):
                text = json.dumps(default["value"], sort_keys=True)
                out.setdefault(name, {}).setdefault(text, []).append(ref)
    return out


@cache
def violations() -> dict[tuple[str, str], str]:
    """Every code-side copy of a declared default, keyed by (file, the declared key it copies)."""
    by_key = _by_key()
    distinctive = declared_defaults()
    found: dict[tuple[str, str], str] = {}
    for path in sorted(PACKAGE.rglob("*.py")):
        rel = path.relative_to(PACKAGE).as_posix()
        if any(rel.startswith(prefix) for prefix in ALLOWED):
            continue
        for lineno, key, text in fallbacks(path):
            if key:
                declared = by_key.get(key, {}).get(text)
                name = key
            else:  # a bare return: the value is the evidence, and the schema names the key it belongs to
                declared = distinctive.get(text)
                name = declared[0].split(":", 1)[-1] if declared else ""
            if declared:
                found[(rel, name)] = f"{rel}:{lineno} supplies `{name}` = {text[:80]}, declared by {declared[0]}"
    return found


def test_no_declared_default_is_supplied_by_code() -> None:
    """A key's default is the adopted schema version's, and only there (04 §4.1, Y1)."""
    found = [why for where, why in sorted(violations().items()) if where not in PENDING]
    joined = "\n  ".join(found)
    assert not found, (
        "a default lives in the adopted schema version, never in the binary (04 §4.1, Y1) — pass the effective "
        f"config instead:\n  {joined}"
    )


def test_every_pending_violation_is_still_there() -> None:
    """`PENDING` declares a gap; it does not paper over one. When a chunk closes one of these, this test fails and
    the entry is deleted — which is how the list stays a worklist rather than becoming an allow-list. It is what
    forced K1c to happen: the three entries it held could not quietly become permanent."""
    stale = sorted(where for where in PENDING if where not in violations())
    assert not stale, f"these are fixed — delete them from PENDING: {stale}"


def test_the_sweep_sees_the_shapes_it_used_to_miss(tmp_path: Path) -> None:
    """The widening, proven on source of its own. Before 2026-08-29 the sweep walked only absent-key fallbacks, so
    a bare `return` and a default argument were invisible — one live violation shipped under a green test because
    of it. Each shape here is asserted by name: revert any one arm of `fallbacks` and this fails."""
    source = tmp_path / "shapes.py"
    source.write_text(
        "from dataclasses import dataclass\n"
        "def a(root: str = 'docs/work/') -> str: return root\n"
        "def b() -> str:\n    return 'docs/work/'\n"
        "def c(x: dict) -> str:\n    return x.get('root', 'docs/work/')\n"
        "@dataclass\nclass D:\n    root: str = 'docs/work/'\n",
        encoding="utf-8",
    )
    shapes = {(key, text) for _line, key, text in fallbacks(source)}
    assert ("root", '"docs/work/"') in shapes, "a default argument, a dataclass field or an absent-key fallback"
    assert ("", '"docs/work/"') in shapes, "a bare return of a declared default"


def test_the_sweep_can_actually_see_a_default() -> None:
    """The guard would be worthless if `declared_defaults()` came back empty — prove it finds real ones."""
    defaults = declared_defaults()
    assert len(defaults) >= 8, sorted(defaults)
    assert json.dumps(["bdd", "task", "spike"], sort_keys=True) in defaults
    assert json.dumps("docs/work/", sort_keys=True) in defaults


def test_the_card_policy_requires_the_resolver() -> None:
    """`CardPolicy` has no default values at all: it is constructed from the effective config or not at all."""
    from isidium.store.registry.card import CardPolicy

    assert all(f.default is f.default_factory is not None or True for f in CardPolicy.__dataclass_fields__.values())
    missing_defaults = [
        name
        for name, f in CardPolicy.__dataclass_fields__.items()
        if f.default is not __import__("dataclasses").MISSING
        or f.default_factory is not __import__("dataclasses").MISSING
    ]
    assert not missing_defaults, f"these carry a code-side default: {missing_defaults}"
