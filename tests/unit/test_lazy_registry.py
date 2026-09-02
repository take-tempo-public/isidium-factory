"""**C-13, enforced by counting** [K1d]. `Registry` loads what it was asked for; the four places that want the whole
collection are carve-outs with notes at their own sites.

Every assertion here counts **parses**, not milliseconds. A timing assertion on this workstation would be a test
that cannot see its own property — the machine's run-to-run noise is around 3x the median — and "it got faster" is
the "nothing came back" pass this round forbids anyway: a registry that had quietly stopped finding its documents
would also be fast. The parse count is the discriminator, and every count is paired with an assertion about *what
came back*, so an empty registry fails both halves.

The second half of the file is the seam lazy loading opens: the ref now comes from the **filename**, so a filename
and a document that disagree are a rule (`registry.filename-mismatch`), and so is a `*.toml` whose name is not a ref
at all (`registry.filename`). `install_schemas` writes `<ref>.toml` from the document's own `name` and `version`, so
an installed checkout satisfies this by construction — these fire for a directory edited by hand.
"""

from __future__ import annotations

import tomllib
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from isidium.store.client.install import install_schemas
from isidium.store.core.refusal import Refusal
from isidium.store.registry import config as cfg
from isidium.store.registry.loader import Registry


@contextmanager
def counted() -> Iterator[list[str]]:
    """Every TOML document parsed inside the block, named `<name>@<version>`, in the order they were parsed.

    It patches `tomllib.loads` itself rather than a name the loader happens to hold, so an edit that reaches TOML by
    another route is still counted."""
    parsed: list[str] = []
    real = tomllib.loads

    def counting(s, **kw):  # type: ignore[no-untyped-def]
        doc = real(s, **kw)
        parsed.append(f"{doc.get('name', '?')}@{doc.get('version', '?')}")
        return doc

    tomllib.loads = counting
    try:
        yield parsed
    finally:
        tomllib.loads = real


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    """A checkout with the registry installed the way `init` installs it: `<ref>.toml`, bytes for bytes."""
    install_schemas(tmp_path)
    return tmp_path


@pytest.fixture
def schemas(checkout: Path) -> Path:
    return checkout / ".isidium" / "schemas"


def test_opening_a_registry_reads_nothing_and_installed_costs_no_parse(schemas: Path) -> None:
    """C-13's first claim, and the one the brief said to assert rather than assume.

    Both halves matter: the count is 0, **and** the refs that come back are the eight the directory holds. A
    registry that had quietly stopped finding documents would satisfy the count on its own."""
    with counted() as parsed:
        reg = Registry.from_directory(schemas)
        refs = reg.installed
        held = {ref for ref in refs if reg.has(ref)}
    assert parsed == [], f"opening a registry parsed {parsed}"
    on_disk = {p.name.removesuffix(".toml") for p in schemas.glob("*.toml")}
    assert refs == frozenset(on_disk) == held and len(refs) == 8, sorted(refs)


def test_the_shipped_registry_is_opened_the_same_way() -> None:
    """The package's own registry, which is what `for_checkout` falls back to in a fresh clone and what every
    codegen path opens. Same claim, different source: an `importlib.resources` traversal rather than a directory."""
    with counted() as parsed:
        reg = Registry.shipped()
        refs = reg.installed
    assert parsed == [], f"opening the shipped registry parsed {parsed}"
    assert {"registry@1", "config@1", "card@1"} <= refs and len(refs) == 8, sorted(refs)


def test_one_question_parses_one_document_and_asking_twice_parses_none(schemas: Path) -> None:
    """The whole chunk in one test: the hook's question costs one document, not the collection it belongs to.

    The second block is the cache — a slot forced twice reads and parses once — without which "lazy" would be
    "lazy and then repeated", which is worse than eager for anything asked more than once."""
    reg = Registry.from_directory(schemas)
    with counted() as first:
        doc = reg.get("config@1")
    assert first == ["config@1"], first
    assert doc["name"] == "config" and doc["version"] == 1

    with counted() as again:
        assert reg.get("config@1") is doc
        assert reg.defaults_of("config@1")["root"] == "docs/work/"
    assert again == [], again

    # a second, different document is one more parse — not eight, and not zero
    with counted() as second:
        assert reg.get("card@1")["name"] == "card"
    assert second == ["card@1"], second


def test_the_hooks_question_parses_one_document(checkout: Path) -> None:
    """`resolve_effective` over `for_checkout` is the registry half of `governed_paths`, which is the whole
    pre-commit hook. It reads the adopted version's declared defaults — one document — and that is the cost this
    chunk exists to repay."""
    with counted() as parsed:
        eff = cfg.resolve_effective({"schema": 1, "tenant": "t"}, Registry.for_checkout(checkout))
    assert parsed == ["config@1"], parsed
    assert eff["root"] == "docs/work/" and eff["governed"], "the manifest came back empty"


def test_the_collection_is_forced_only_where_it_is_the_answer(schemas: Path) -> None:
    """The four carve-outs, asserted as carve-outs — each on its own registry, so no earlier force can pay for a
    later one. `source()` is the one that reads without parsing: `init` copies bytes, and a registry that has only
    been asked for one document still owes no parse here."""
    reg = Registry.from_directory(schemas)
    with counted() as bytes_only:
        raw = reg.source()
    assert bytes_only == [], f"source() parsed {bytes_only}"
    assert set(raw) == set(reg.installed) and raw["config@1"].startswith(b'name = "config"')

    reg = Registry.from_directory(schemas)
    with counted() as addressed:
        addresses = reg.addresses
    assert sorted(addressed) == sorted(reg.installed), addressed
    assert set(addresses) == set(reg.installed) and addresses["registry@1"].startswith("sha256:")

    reg = Registry.from_directory(schemas)
    with counted() as checked:
        report = reg.check_all()
    assert sorted(checked) == sorted(reg.installed), checked
    assert set(report) == set(reg.installed) and not any(report.values())


def test_the_startup_contract_still_fails_at_startup(tmp_path: Path) -> None:
    """C-13 carve-out 1. A checkout with no registry refuses **when the registry is opened**, not when a document
    is later asked for — deferring it would move a boot-time refusal into the middle of a write."""
    (tmp_path / "empty").mkdir()
    with pytest.raises(Refusal) as e:
        Registry.from_directory(tmp_path / "empty")
    assert e.value.rule == "registry.not-installed"


def test_a_document_that_disagrees_with_its_filename_is_refused_when_it_is_forced(schemas: Path) -> None:
    """The seam lazy loading opens, named. Keyed by contents this file is `config@2`; keyed by its filename it is
    `config@1` and says otherwise, so the two facts have to be made to agree somewhere — here, at the force.

    **The refusal is late on purpose, and that is asserted too**: opening the registry and listing it still cost no
    parse. Without that half, moving the check back to load time would leave this green and the chunk undone."""
    doc = schemas / "config@1.toml"
    doc.write_bytes(doc.read_bytes().replace(b"version = 1", b"version = 2", 1))

    with counted() as opening:
        reg = Registry.from_directory(schemas)
        assert "config@1" in reg.installed and reg.has("config@1")
    assert opening == [], opening

    with pytest.raises(Refusal) as e:
        reg.get("config@1")
    assert e.value.rule == "registry.filename-mismatch"
    assert "config@2" in e.value.detail and e.value.path.endswith("config@1.toml")

    # and a carve-out that forces the whole collection meets it too, rather than stepping over the file
    with pytest.raises(Refusal, match=r"registry\.filename-mismatch"):
        _ = Registry.from_directory(schemas).addresses


def test_a_toml_the_registry_cannot_name_is_refused_when_the_directory_is_listed(schemas: Path) -> None:
    """The other half of the seam: a ref is read off a filename now, so a filename that is not a ref has no answer.

    This one is eager — it costs the listing that already happened and nothing more — because a directory that
    cannot be keyed is not a fact about any one document, which is `registry.not-installed`'s shape."""
    (schemas / "notes.toml").write_bytes(b'name = "notes"\nversion = 1\n')
    with counted() as parsed, pytest.raises(Refusal) as e:
        Registry.from_directory(schemas)
    assert parsed == [], parsed
    assert e.value.rule == "registry.filename" and "notes.toml" in e.value.detail

    # `INSTALLED` is not a `*.toml`, so the file `init` writes beside the schemas is not caught by this
    (schemas / "notes.toml").unlink()
    assert (schemas / "INSTALLED").is_file() and len(Registry.from_directory(schemas).installed) == 8


def test_the_eager_constructor_still_refuses_a_registry_with_no_bytes() -> None:
    """`Registry(docs, source)` keeps its own invariant. It is the one constructor whose caller has already done the
    reading, so nothing is deferred there and `registry.source-mismatch` still fires at construction."""
    shipped = Registry.shipped()
    docs = {ref: shipped.get(ref) for ref in ("config@1", "card@1")}
    with pytest.raises(Refusal) as e:
        Registry(docs, {"config@1": shipped.source()["config@1"]})
    assert e.value.rule == "registry.source-mismatch" and "card@1" in e.value.detail
