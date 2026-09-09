"""The rule this test enforces (Q2b, ruled 2026-08-29): **a rule id always begins with a namespace and a dot.**

Two ids were neither — `validate` had no namespace at all and `integrity:time` used a colon. C-12's disclosure table
is keyed by namespace with per-id overrides, so an id with no namespace has no row to inherit from and an id with a
colon has a namespace nothing else shares. Both would be permanent exceptions in the table and again in the Rust
port's `Namespace` enum. K1b-iii normalised them (`validate.failed`, `integrity.time`); this sweep is what stops a
third from arriving, and it runs **before** K2b writes the table, so the table is written against final ids.

**Deeper structure is allowed and used**: `profile.head.status`, `profile.ears.weak-word`, `scenario.command.argv`.
The invariant is about the FIRST segment — the namespace the table keys on — not about the number of segments; the
`profile` family alone is why the ruling counted 34 namespaces across 150 ids rather than 150 namespaces.

It reads the package's source, not a registry of ids, because a rule id is a literal at its raise site. It reads every
literal in a rule-id position:

  * `Refusal("<rule>", …)` and any subclass of it, first positional argument;
  * `_r(rs, "<rule>", …)` — the collector helper, second positional argument, which is most of the validation
    surface and is what both earlier hand-counts missed;
  * `super().__init__("<rule>", …)` inside a `Refusal` subclass — a subclass that fixes its own id, which is where
    `validate.failed` lives and which the first draft of this sweep could not see;
  * a `"rule"` key in a dict literal — how the service used to build a refusal payload without the type. **That arm
    now finds nothing in the package, and a test below asserts so**: K2b's item 0 routed the last nine of those
    through `Refusal`, so the arm has become the guard that stops a tenth from being added.

**And it reads what a rule id's namespace is even when the id itself is computed.** A handful of ids are built from
an f-string (`f"profile.head.{k}"`), so the *id* is not a literal anywhere — but the **namespace** is, and the
namespace is what C-12's table keys on. `namespaces()` collects both, which is what makes "every namespace the code
can raise has a row" a claim about the whole surface rather than about the literal part of it.

**This file is C-12's enforcement as well as C-5's** [K2b]. Four things are asserted here that live nowhere else:
that a rule id is `<namespace>.<name>`; that every namespace the code can raise has a row in the disclosure table;
that every id in a declare-explicitly namespace has its own row; and that the table names nothing the code cannot
raise.
"""

from __future__ import annotations

import ast
import re
import sys
from collections.abc import Iterator, Sequence
from pathlib import Path

import pytest

import isidium.factory
import isidium.store
from isidium.store.core.disclosure import DECLARED, NAMESPACES, RULES, Disclosure, namespace_of

PACKAGE = Path(isidium.store.__file__).parent
# The factory package is swept too [L2]: its client raises `factory.*`, classified in the store's table like `client.*`.
FACTORY = Path(isidium.factory.__file__).parent
# **The tools are swept too** [K10, Q21, ruled 2026-09-06: *"Sweep reads tools, unclassified fails"*].
# `tools/verify_chain.py` raised `verify.shallow` (K7a, F1) — the first rule id outside the package — and this sweep
# read `packages/` alone, so the id was classified nowhere and a second one would not have been seen. A tool's ids
# join the table like the package's: a tool speaks to the operator at the forge and the terminal, never to a peer,
# so its namespace is `full`; an unclassified tool id fails the build exactly as a package id does. The repository
# root is the second source root, so a tool's site reads `tools/<file>:<line>`.
REPO = Path(__file__).resolve().parents[2]
TOOLS = REPO / "tools"

# `<namespace>.<name>[.<name>…]`: lower-case, hyphens inside a segment, at least one dot, never a colon.
# Deliberately strict about the alphabet — this is the shape C-12's table keys on and the port's enum encodes.
RULE_ID = re.compile(r"^[a-z][a-z0-9-]*(\.[a-z][a-z0-9-]*)+$")


def _is_refusal_name(node: ast.expr) -> bool:
    name = node.id if isinstance(node, ast.Name) else node.attr if isinstance(node, ast.Attribute) else ""
    return name.endswith("Refusal")


def _string_arg(node: ast.Call, index: int = 0) -> tuple[int, str] | None:
    if len(node.args) <= index:
        return None
    a = node.args[index]
    return (a.lineno, a.value) if isinstance(a, ast.Constant) and isinstance(a.value, str) else None


def _computed_namespace(node: ast.Call, index: int) -> tuple[int, str] | None:
    """The namespace of a rule id built by an f-string, e.g. `f"profile.head.{k}"` → `profile`.

    The id is not a literal, so `_string_arg` cannot see it — but the table keys on the namespace and the namespace
    *is* a literal, in the f-string's first constant part. Without this, `f"profile.{key}.shape"` would be a rule id
    the coverage claim below silently did not cover."""
    if len(node.args) <= index:
        return None
    a = node.args[index]
    if not isinstance(a, ast.JoinedStr) or not a.values:
        return None
    first = a.values[0]
    if not isinstance(first, ast.Constant) or not isinstance(first.value, str) or "." not in first.value:
        return None
    return a.lineno, first.value.split(".", 1)[0]


# The four forms a rule id is written in. `dict` is the one K2b's item 0 emptied: it stays swept so that adding a
# tenth bare payload fails a test rather than quietly bypassing `Refusal` and C-12's filter with it.
FORMS = ("refusal", "collector", "super", "dict")


def rule_ids(path: Path) -> Iterator[tuple[int, str, str]]:
    """Every string literal in a rule-id position in one module, as `(line, id, form)`."""
    tree = ast.parse(path.read_bytes())
    # a `Refusal` subclass fixes its own id in `super().__init__(...)`; that call names no Refusal, so it needs the
    # enclosing class to identify it
    in_refusal_subclass = {
        id(n)
        for cls in ast.walk(tree)
        if isinstance(cls, ast.ClassDef) and any(_is_refusal_name(b) for b in cls.bases)
        for n in ast.walk(cls)
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            if _is_refusal_name(fn):
                found, form = _string_arg(node), "refusal"
            elif isinstance(fn, ast.Name) and fn.id == "_r":
                found, form = _string_arg(node, 1), "collector"  # `_r(rs, "<rule>", path, detail)`
            elif isinstance(fn, ast.Attribute) and fn.attr == "__init__" and id(node) in in_refusal_subclass:
                found, form = _string_arg(node), "super"
            else:
                found, form = None, ""
            if found is not None:
                yield found[0], found[1], form
        elif isinstance(node, ast.Dict):
            for k, v in zip(node.keys, node.values, strict=True):
                key_is_rule = isinstance(k, ast.Constant) and k.value == "rule"
                if key_is_rule and isinstance(v, ast.Constant) and isinstance(v.value, str):
                    yield v.lineno, v.value, "dict"


def computed_namespaces(path: Path) -> Iterator[tuple[int, str]]:
    """The namespaces of the rule ids in one module that are built rather than written."""
    tree = ast.parse(path.read_bytes())
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if _is_refusal_name(fn):
            found = _computed_namespace(node, 0)
        elif isinstance(fn, ast.Name) and fn.id == "_r":
            found = _computed_namespace(node, 1)
        else:
            found = None
        if found is not None:
            yield found


def _sources(paths: Sequence[Path] | None) -> list[tuple[Path, Path]]:
    """The files to read, each with the root its name is shown against: the package's modules against the package,
    the tools against the repository (Q21). `paths` exists so a test can run the sweep over a source it planted: two
    of the four arms have no discriminator inside the package — the bare-payload arm because K2b emptied it, the
    computed-namespace arm because every f-string namespace is also a literal somewhere — and an arm with no
    discriminator is an arm a mutation walks straight through."""
    if paths is None:
        package = [(p, PACKAGE) for p in sorted(PACKAGE.rglob("*.py"))]
        package += [(p, FACTORY) for p in sorted(FACTORY.rglob("*.py"))]
        tools = [(p, TOOLS.parent) for p in sorted(TOOLS.glob("*.py"))]
        return package + tools
    listed = list(paths)
    return [(p, listed[0].parent) for p in listed]


def swept(paths: Sequence[Path] | None = None) -> dict[str, list[str]]:
    """id -> the `file:line` sites that raise it."""
    out: dict[str, list[str]] = {}
    for path, root in _sources(paths):
        for line, rid, _form in rule_ids(path):
            out.setdefault(rid, []).append(f"{path.relative_to(root).as_posix()}:{line}")
    return out


def swept_by_form() -> dict[str, list[str]]:
    """form -> the `file:line` sites written in it."""
    out: dict[str, list[str]] = {form: [] for form in FORMS}
    for path, root in _sources(None):
        for line, _rid, form in rule_ids(path):
            out[form].append(f"{path.relative_to(root).as_posix()}:{line}")
    return out


def namespaces(paths: Sequence[Path] | None = None) -> dict[str, list[str]]:
    """namespace -> the `file:line` sites that raise something in it, computed ids included."""
    out: dict[str, list[str]] = {}
    for rid, sites in swept(paths).items():
        out.setdefault(namespace_of(rid), []).extend(sites)
    for path, root in _sources(paths):
        for line, ns in computed_namespaces(path):
            out.setdefault(ns, []).append(f"{path.relative_to(root).as_posix()}:{line}")
    return out


def test_every_rule_id_is_a_namespace_and_a_name() -> None:
    """The invariant itself. `validate` and `integrity:time` are the two this was written for."""
    ids = swept()
    bad = {rid: sites for rid, sites in ids.items() if not RULE_ID.match(rid)}
    assert not bad, "rule ids that are not `<namespace>.<name>`: " + "; ".join(
        f"{rid!r} at {', '.join(sites)}" for rid, sites in sorted(bad.items())
    )


def test_the_two_normalised_ids_are_gone_and_their_replacements_are_raised() -> None:
    """A positive discriminator for the rename, not just the absence of the old ids: an empty sweep would satisfy
    the absence half on its own, and a sweep that silently stopped reading the package is exactly the "nothing came
    back" pass this round exists to forbid."""
    ids = swept()
    assert "validate" not in ids and "integrity:time" not in ids
    sites = ids.get("validate.failed") or []
    assert [s.split(":")[0] for s in sites] == ["core/refusal.py"], sites  # its one raiser, and the file not the line
    assert len(ids.get("integrity.time", [])) == 2, ids.get("integrity.time")


def test_the_sweep_sees_the_whole_surface(tmp_path: Path) -> None:
    """The sweep's own floor. Both earlier hand-counts of this surface were wrong (150 ids, not the 130 the plan
    claimed or the 91 the review claimed) because they missed the `_r(rs, "<rule>", …)` helper form — most of the
    validation surface. If a future edit breaks one arm, this fails rather than the coverage silently halving.

    **The computed-namespace arm is proven against a planted source, not against the package**, and that is a
    correction: the first version of this line asserted `"profile" in namespaces()`, which every literal
    `profile.*` id satisfies on its own. Disabling the computed arm entirely left it green — the mutation SURVIVED,
    and it survived because the assertion could not see the property, not because the property was missing (K1b-ii's
    lesson, met again here). No namespace in the package today is reachable **only** through an f-string, so there is
    nothing in the package that can discriminate; the arm has to be run over a source that needs it."""
    ids = swept()
    assert len(ids) > 120, f"only {len(ids)} rule ids found — the sweep stopped seeing part of the package"
    # one id per literal position the sweep reads, each produced by that position and no other
    assert "write.grant" in ids, "the `Refusal(...)` arm"
    assert "config.type" in ids, "the `_r(rs, ...)` collector arm"
    assert "validate.failed" in ids, "the `super().__init__(...)` arm inside a Refusal subclass"
    # the bare-payload arm is asserted by its emptiness — see the next test — because K2b removed its last producer
    planted = tmp_path / "computed.py"
    planted.write_text('_r(rs, f"profile.head.{k}", k)\nRefusal(f"invented.{k}", "")\n', encoding="utf-8")
    # Neither line writes a rule id as a literal, so a sweep without the computed arm sees nothing here at all —
    # which is what makes this the discriminator the package itself cannot supply.
    assert sorted(namespaces([planted])) == ["invented", "profile"], namespaces([planted])
    assert "invented" not in namespaces(), "the planted source leaked into the sweep of the package"


def test_no_rule_id_reaches_a_caller_without_passing_through_refusal(tmp_path: Path) -> None:
    """**K2b's item 0, as a standing guard.** Nine rule ids were built straight into a response body and never
    passed through `Refusal` at all — five named by C-12 plus four K1b-ii added — so C-12's disclosure filter, which
    lives on `Refusal.payload()`, could not reach them and the sweep that enforces the table was blind to exactly
    the surface the table governs.

    They are gone, and this asserts the fact rather than trusting it: the bare-`{"rule": …}` arm of the sweep now
    finds nothing in the package. A tenth bare payload fails here, at the moment it is written, instead of at the
    next review.

    **An empty arm and a broken arm look identical**, which is the "nothing came back" pass this round exists to
    forbid — so the second half runs the same arm over a source that *does* contain one and requires it to be
    found. Without that, deleting the arm would make this test pass."""
    assert swept_by_form()["dict"] == [], "a rule id is built into a response body without passing through Refusal"
    planted = tmp_path / "planted.py"
    planted.write_text('x = {"rule": "service.route", "detail": "t"}\n', encoding="utf-8")
    assert [(rid, form) for _line, rid, form in rule_ids(planted)] == [("service.route", "dict")]


def test_every_namespace_the_code_can_raise_is_classified() -> None:
    """**C-12's enforcement, in the shape Q2's ruling made satisfiable.** The original wording — "every rule id
    appears in the table" — cannot hold against a namespace-keyed table, because no rule id appears in one. This is
    what it becomes: a namespace the code can raise and the table does not name is a build failure, not a silent
    fall-through to terse.

    It reads computed namespaces too, so the `profile.*` ids built from an f-string are inside the claim."""
    raised = namespaces()
    missing = {ns: sites[:3] for ns, sites in raised.items() if ns not in NAMESPACES}
    assert not missing, f"namespaces the code raises and `core/disclosure.py` does not classify: {missing}"


def test_the_verifiers_rule_id_moved_into_the_package_and_stays_full() -> None:
    """Q21 (c)'s positive half was `verify.shallow` at its site under `tools/`. K12 (2026-09-08) moved the verifier
    into the package as `isidium verify`, so the id's one site is `client/verify.py` now, its row is still `full`
    (the verb speaks to the operator at the forge and the terminal, never to a peer), and the real `tools/` raises
    no rule id at all today — the sweep still reads it, which the planted-tool test below is the proof of."""
    ids = swept()
    assert [s.split(":")[0] for s in ids["verify.shallow"]] == ["client/verify.py"], ids.get("verify.shallow")
    assert NAMESPACES[namespace_of("verify.shallow")].disclosure is Disclosure.FULL
    from_tools = sorted(s for sites in ids.values() for s in sites if s.startswith("tools/"))
    assert from_tools == [], f"a rule id under tools/ again — classify it, and say so here: {from_tools}"


def test_an_unclassified_tool_id_fails_the_sweep_like_a_package_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Q21 (c), the failing half — proven against a planted tool, because the real `tools/` holds nothing
    unclassified: with the tools directory pointed at one file raising `invented.tool`, the classification test
    fails naming the namespace, and the site reads `tools/<file>:<line>`."""
    planted = tmp_path / "tools"
    planted.mkdir()
    (planted / "probe.py").write_text('raise Refusal("invented.tool", "", "planted")\n', encoding="utf-8")
    monkeypatch.setattr(sys.modules[__name__], "TOOLS", planted)
    assert namespaces()["invented"] == ["tools/probe.py:1"]
    with pytest.raises(AssertionError, match="invented"):
        test_every_namespace_the_code_can_raise_is_classified()


def test_every_rule_id_in_a_declare_explicitly_namespace_is_classified() -> None:
    """Q2a's other half. The validation families inherit `full` freely — a forgotten row there would go **terse**,
    handing an agent a bare rule id it cannot self-correct from, which is the hazard C-12 exists to prevent. The
    `full` namespaces that live in *server* code are the ones where a new id could name something internal, so
    there a new id is a build failure until someone classifies it."""
    ids = swept()
    undeclared = sorted(rid for rid in ids if namespace_of(rid) in DECLARED and rid not in RULES)
    assert not undeclared, (
        f"rule ids in a declare-explicitly namespace ({sorted(DECLARED)}) with no row of their own: {undeclared}"
    )


def test_the_table_classifies_nothing_the_code_cannot_raise() -> None:
    """A stale key in the table is invisible: it never matches, the refusal falls through to terse/422, and the
    table still claims otherwise. Both halves are checked — a rule id nothing raises, and a namespace nothing
    raises — because the table now carries two kinds of key and either can go stale on its own."""
    ids = swept()
    raised = namespaces()
    stale_rules = sorted(k for k in RULES if k not in ids)
    stale_namespaces = sorted(k for k in NAMESPACES if k not in raised)
    assert not stale_rules, f"rows for rule ids no code raises: {stale_rules}"
    assert not stale_namespaces, f"rows for namespaces no code raises: {stale_namespaces}"
    assert all(RULE_ID.match(k) for k in RULES), sorted(k for k in RULES if not RULE_ID.match(k))
