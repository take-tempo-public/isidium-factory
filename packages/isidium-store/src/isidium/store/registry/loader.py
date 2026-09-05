"""The installed registry: schema documents `name@version` loaded from `schemas/*.toml`, content-addressed (04 §4);
Y1 — a config version's defaults are read from its document alone (`defaults_of`), the effective config is the
tenant's file overlaid on the ADOPTED version's defaults (the version the file's own `[[governed]]` row names), and
adopting a newer version is one signed manifest edit whose default diff is shown at signing (`default_diff`).

**A document is read and parsed when it is asked for, not when the registry is opened** [C-13, K1d]. Asking for
`config@1` — which is what the pre-commit hook does on every commit, and what every `resolve_effective` does —
parses one document instead of eight. The four places that genuinely want the whole collection force it and say so
at their own site: C-13 is enforced by the shape of the exception, so an eager load here without a note is the
defect, not the eager load itself.

**The ref comes from the filename, and the document must agree with it.** Keying by contents would mean parsing
every document to learn its name, which is the cost this change exists to remove — so `config@1.toml` is filed as
`config@1` before anything reads it. A file whose contents then declare something else is refused when it is forced
(`registry.filename-mismatch`), and a `*.toml` whose name is not `<name>@<version>` is refused when the directory is
listed (`registry.filename`). `install_schemas` has always written `<ref>.toml` from the document's own `name` and
`version`, so an installed checkout satisfies this by construction; the rule exists for a directory edited by hand,
and for the day the two facts disagree in the package itself.
"""

from __future__ import annotations

import copy
import re
import tomllib
from collections.abc import Callable, Mapping
from functools import cached_property
from importlib import resources
from pathlib import Path
from typing import Any, Final

from ..core import canon
from ..core.refusal import Refusal
from .vocabulary import SchemaDoc, validate_schema_document

SCHEMA_REF: Final = re.compile(r"^([a-z][a-z0-9-]*)@([1-9][0-9]*)$")


def parse_ref(ref: str) -> tuple[str, int]:
    m = SCHEMA_REF.match(ref)
    if not m:
        raise Refusal("config.pattern", "schema", f"{ref!r} is not <name>@<version>")
    return m.group(1), int(m.group(2))


class _Slot:
    """One installed document: read on first touch, parsed on first use, then held.

    `read` is the entry's own bound `read_bytes` — a `Path`'s or an `importlib.resources` `Traversable`'s — so the
    slot never learns which kind of source it came from and no closure has to capture a loop variable. `where` is
    what a refusal names: the file, not the directory, because the fix is to that file."""

    __slots__ = ("_doc", "_raw", "_read", "_ref", "_where")

    def __init__(self, ref: str, read: Callable[[], bytes], where: str) -> None:
        self._ref = ref
        self._read = read
        self._where = where
        self._raw: bytes | None = None
        self._doc: SchemaDoc | None = None

    @classmethod
    def loaded(cls, ref: str, doc: SchemaDoc, raw: bytes) -> _Slot:
        """A document already in hand — the eager constructor's path. Nothing is deferred because nothing is left
        to defer, and the filename rule does not apply: this ref came from a caller, not from a directory."""
        slot = cls(ref, lambda: raw, ref)
        slot._raw, slot._doc = raw, doc
        return slot

    def raw(self) -> bytes:
        """The bytes the document was read from — read once, then held.

        **Carried because `init`'s whole purpose is byte-identity** (03b §4: *"the same bytes either way, so local
        `check` and the store cannot disagree"*), and a registry can no longer be asked for bytes it does not have.
        Before this, `install_schemas` took a registry and then copied from the package regardless, so a checkout
        could be handed one registry's `INSTALLED` list over another registry's bytes. Under C-13 a registry asked
        for one document now holds one document's bytes rather than the ~20 KB of the whole shipped set."""
        if self._raw is None:
            self._raw = self._read()
        return self._raw

    def doc(self) -> SchemaDoc:
        """The parsed document, and the one place the filename is checked against what the document says it is."""
        if self._doc is None:
            doc: SchemaDoc = tomllib.loads(self.raw().decode("utf-8"))
            declared = f"{doc.get('name')}@{doc.get('version')}"
            if declared != self._ref:
                raise Refusal(
                    "registry.filename-mismatch",
                    self._where,
                    f"filed as {self._ref!r} by its filename but declares {declared!r}",
                )
            self._doc = doc
        return self._doc


def _slot_for(ref: str, name: str, read: Callable[[], bytes], where: str) -> _Slot:
    """One slot, with the filename grammar checked before anything is read."""
    if not SCHEMA_REF.match(ref):
        raise Refusal("registry.filename", where, f"{name!r} is not <name>@<version>.toml")
    return _Slot(ref, read, where)


def _slots_in(directory: Path) -> dict[str, _Slot]:
    """Every `*.toml` in one directory, keyed by the ref its filename spells. **A directory listing and no reads** —
    which is the point, and `tests/unit/test_registry.py` counts the parses rather than trusting this sentence."""
    return {
        path.name.removesuffix(".toml"): _slot_for(
            path.name.removesuffix(".toml"), path.name, path.read_bytes, str(path)
        )
        for path in sorted(directory.glob("*.toml"))
    }


class Registry:
    """The installed, content-addressed schema store. Old versions stay resolvable forever."""

    _slots: dict[str, _Slot]

    def __init__(self, docs: Mapping[str, SchemaDoc], source: Mapping[str, bytes]) -> None:
        """Documents already parsed, with the bytes each was read from under the same ref.

        This is the eager constructor and it stays eager: its caller has already done the reading, so there is
        nothing left for a thunk to defer. The lazy constructors (`shipped`, `from_directory`, `for_checkout`) go
        through `_over` instead."""
        if source.keys() != docs.keys():
            missing = sorted(docs.keys() ^ source.keys())
            raise Refusal("registry.source-mismatch", "", f"no bytes for {missing}")
        self._slots = {ref: _Slot.loaded(ref, doc, source[ref]) for ref, doc in docs.items()}

    @classmethod
    def _over(cls, slots: dict[str, _Slot]) -> Registry:
        """A registry over slots nothing has forced yet — the one path that skips `__init__`'s eager mappings."""
        reg = cls.__new__(cls)
        reg._slots = slots
        return reg

    @classmethod
    def shipped(cls) -> Registry:
        """The registry shipped with the toolkit: every `schemas/*.toml` in this package.

        A listing, no reads and no parses (C-13). When a document is read it is read as **bytes**, not `read_text`:
        the bytes ARE the artifact `init` installs, and text mode would translate the line endings on the way
        through (the Windows trap C-9 names)."""
        schemas = resources.files(__package__).joinpath("schemas")
        return cls._over(
            {
                entry.name.removesuffix(".toml"): _slot_for(
                    entry.name.removesuffix(".toml"), entry.name, entry.read_bytes, f"schemas/{entry.name}"
                )
                for entry in schemas.iterdir()
                if entry.name.endswith(".toml")
            }
        )

    @classmethod
    def from_directory(cls, directory: str | Path) -> Registry:
        """The registry `init` installed into a checkout (03b §4: *"`init` installs the referenced versions locally
        for offline validation and CI: the same bytes either way, so a local check and the store's check cannot
        disagree"*). Read from disk, so a client on a newer toolkit still validates against the versions the tenant
        adopted — which is the case the sentence exists for (the review's C5)."""
        d = Path(directory)
        slots = _slots_in(d)
        # **C-13 carve-out 1 of 4 — a startup contract that must fail at startup.** "This checkout has no registry
        # at all" is not a fact about any one document, so no thunk can carry it; deferring it moves a boot-time
        # refusal into the middle of a write, which is strictly worse for the operator. What stays eager here is
        # the CHECK, and it costs a directory listing rather than eight parses.
        if not slots:
            raise Refusal("registry.not-installed", str(d), "run `isidium init` to install the registry schemas")
        return cls._over(slots)

    @classmethod
    def for_checkout(cls, repo: str | Path) -> Registry:
        """The checkout's installed registry when there is one, else the shipped one (a fresh clone before `init`).

        **One directory scan, not two** (C-8): "is there anything here?" and "what is here?" are the same listing,
        and this runs on every client transport call and every commit."""
        local = Path(repo) / ".isidium" / "schemas"
        slots = _slots_in(local) if local.is_dir() else {}
        return cls._over(slots) if slots else cls.shipped()

    @cached_property
    def installed(self) -> frozenset[str]:
        """Every installed ref — **from the filenames, so no document is read to answer it** (C-13, K1d)."""
        return frozenset(self._slots)

    @cached_property
    def addresses(self) -> dict[str, str]:
        """The content address of every installed document, keyed by ref.

        **C-13 carve-out 2 of 4 — the collection is the answer.** Both consumers want every address at once (the
        registry's own identity check, and the byte-identity assertion that a checkout's install matches the
        package's), and neither is on a call path: nothing in `packages/` reads this. A per-ref address method would
        buy nothing and cost a layer, so this forces every document on first touch and holds the result — which is
        the C-1 discipline `Limits` uses, the exception written where it bites."""
        return {ref: canon.content_address(slot.doc()) for ref, slot in self._slots.items()}

    def get(self, ref: str) -> SchemaDoc:
        """One document — read and parsed here if this is the first time anything asked for it."""
        try:
            slot = self._slots[ref]
        except KeyError:
            raise Refusal("config.schema-unknown", "schema", f"{ref!r} not in the installed registry") from None
        return slot.doc()

    def has(self, ref: str) -> bool:
        """Whether this registry holds `ref` — a key lookup, and never a read or a parse."""
        return ref in self._slots

    def newest(self, name: str) -> int:
        """The highest installed version of the document type `name` — from the filenames, no parse (C-13).

        What `init` adopts for a new tenant [K6]: a store initialising a tenant writes the newest `config@<n>` it
        ships, so a tenant born on a K6 toolkit records caller credentials from its first journal row rather than
        migrating to them later. An existing tenant is untouched by this — its adopted version is the one its own
        `[[governed]]` row names (04 §4.1), and moving it is a signed `config-policy` act, never a toolkit upgrade."""
        versions = [parse_ref(ref)[1] for ref in self._slots if ref.startswith(name + "@")]
        if not versions:
            raise Refusal("config.schema-unknown", "schema", f"no {name}@<n> in the installed registry")
        return max(versions)

    def source(self) -> dict[str, bytes]:
        """Every installed document as the bytes it was read from, keyed by ref. What `init` writes into a
        checkout, so the installed registry and the `INSTALLED` list are the same registry by construction.

        **C-13 carve-out 3 of 4 — the collection is the answer.** `install_schemas` writes every document into the
        checkout; there is no subset of this question. It reads bytes and parses nothing, so a registry that has
        only ever been asked for `config@1` still pays no parse here."""
        return {ref: slot.raw() for ref, slot in self._slots.items()}

    def check_all(self) -> dict[str, list[Refusal]]:
        """Every installed document validated against `registry@1` — `registry@1` against itself (the fixed point).

        **C-13 carve-out 4 of 4 — the collection is the answer, by name.** `check_all` and codegen are the two
        callers C-13 names for this shape: a thunk per member buys nothing when every member is forced one line
        later."""
        reg = self.get("registry@1")
        return {ref: validate_schema_document(slot.doc(), reg) for ref, slot in self._slots.items()}

    # ---- Y1: defaults live in the adopted schema version ------------------------------------------------------

    def defaults_of(self, ref: str) -> dict[str, Any]:
        """The default tree a schema version carries — from its `default` members alone, whatever its form: a TOML
        document's scalars and tables, a Markdown document's head, a record document's rows. This is the ONLY place a
        default comes from (04 §4.1, Y1); `tests/unit/test_no_code_defaults.py` fails the build if code supplies one."""
        doc = self.get(ref)
        tree: dict[str, Any] = {}
        for row in [*doc.get("scalars", []), *doc.get("head", []), *doc.get("record", [])]:
            if "default" in row:
                tree[row["name"]] = copy.deepcopy(row["default"]["value"])
        for trow in doc.get("tables", []):
            name = trow["name"]
            if "reserved" in trow:
                continue
            table: dict[str, Any] = {}
            for krow in trow.get("keys", []):
                if "default" in krow:
                    table[krow["name"]] = copy.deepcopy(krow["default"]["value"])
            dyn = trow.get("dynamic-table") or {}
            for mname, mkeys in (dyn.get("members") or {}).items():
                member = {k["name"]: copy.deepcopy(k["default"]["value"]) for k in mkeys if "default" in k}
                if member:
                    table[mname] = member
            if "default" in trow:
                tree[name] = copy.deepcopy(trow["default"]["value"])
            elif table:
                _put(tree, name, table)
        return tree

    def default_diff(self, ref_old: str, ref_new: str) -> list[tuple[str, Any, Any]]:
        """The default diff shown at signing when adoption changes versions: [(dotted path, old, new)]."""
        a, b = _flatten(self.defaults_of(ref_old)), _flatten(self.defaults_of(ref_new))
        return [(k, a.get(k), b.get(k)) for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k)]


def _put(tree: dict[str, Any], dotted: str, value: dict[str, Any]) -> None:
    parts = dotted.split(".")
    t = tree
    for seg in parts[:-1]:
        t = t.setdefault(seg, {})
    t[parts[-1]] = value


def _flatten(tree: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in tree.items():
        p = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(_flatten(v, p))
        else:
            out[p] = v
    return out


def adopted_version(tree: Mapping[str, Any], registry: Registry) -> int | None:
    """The `config@<n>` the file's OWN `[[governed]]` row names (first match on `config.toml`).

    **Where the manifest comes from when the file has no `[[governed]]` table** [C-1, ruled by the owner 2026-08-29]:
    the adopted version's own declared manifest, read from `registry` — never a copy in the binary. This is not the
    circularity it looks like. The manifest is consulted ONLY when the file declares no table of its own, and in that
    case the adopted version is whatever the head `schema` key names; `config@N`'s declared manifest names `config@N`
    for `config.toml`, so the answer is the head key. That fixed point is asserted for every installed version by
    `test_every_config_version_declares_a_manifest_that_adopts_itself` — a future `config@2` whose declared manifest
    still said `config@1` would break this silently, and that test is the only thing that would catch it.

    Returns `None` when there is no answer: no head, a head naming a version this registry does not have, a manifest
    with no `config.toml` row, or a `governed` value that is not a table at all. A caller that has already recorded
    `config.schema-unknown` therefore gets `None` here rather than an exception."""
    rows = tree.get("governed")
    if not rows:
        head = tree.get("schema")
        ref = f"config@{head}" if isinstance(head, int) and not isinstance(head, bool) else ""
        if not registry.has(ref):
            return None
        rows = registry.defaults_of(ref).get("governed") or []
    if not isinstance(rows, list):
        return None
    for r in rows:
        if isinstance(r, dict) and r.get("path") == "config.toml":
            ref = str(r.get("schema", ""))
            m = SCHEMA_REF.match(ref)
            return int(m.group(2)) if m and m.group(1) == "config" else None
    return None
