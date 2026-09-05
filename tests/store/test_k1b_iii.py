"""K1b-iii's three defects outside the edge's files, each with the discriminator that tells the fix from the bug.

1. `repair` was authorized by a hand-written `caller.grant != "owner"` instead of the one function over the grant
   matrix, so the one act that can rewrite the integrity record was the one verb the realm could never re-authorize.
2. `install_schemas` took a `registry`, wrote `INSTALLED` from it, and copied the schema bytes from the shipped
   package regardless — a checkout could get one registry's list over another registry's documents.
3. A validation refusal flattened its typed verdicts into a `"; "`-joined string, so a caller received the failed
   field names only inside prose (Q7).

Each test's assertion is chosen so the OLD code fails it. "A non-owner is refused" was already true before item 1;
"the schemas are installed" was already true before item 2; "the refusal names the field" was already true of the
prose before item 3. The discriminators are, respectively: the gate consults the matrix VALUE, the installed bytes
are the argument's and not the package's, and the field names arrive as data.
"""

from __future__ import annotations

import json
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from isidium.store.client.install import install_schemas
from isidium.store.client.transport import refusal_from
from isidium.store.core.refusal import Refusal, ValidationRefusal
from isidium.store.registry.loader import Registry
from isidium.store.server import identity
from isidium.store.server.identity import Caller
from isidium.store.server.service import Response

from .conftest import OWNER, PLANNER, Harness, fresh

# ---- 1. `repair` goes through the grant seam -----------------------------------------------------------------


def test_repair_is_authorized_by_the_matrix_value_not_by_a_hand_written_owner_test(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**The discriminator is the matrix, not the refusal.** The old hand-written check refused a contributor too,
    so "a contributor may not repair" cannot tell the two apart. What can: supplying a matrix value that DOES grant
    `repair` to a contributor and watching the gate open. Under the old code the call still refused, because the
    owner test sat below the seam where no policy value could reach it — which is the whole failure, since 04 §2
    exists so isidium G7 can supply this value later.

    The gate opening is observed as *a different refusal*: the call gets past authorization and fails on its own
    argument (`repair.target`), which only a caller the matrix admitted can reach."""
    hz = fresh("repair-seam")
    with pytest.raises(Refusal) as e:
        hz.st.repair(PLANNER, history=1, restart_from=1)
    assert e.value.rule == "write.grant", "the outer matrix gate, not the signature predicate (7bf.6 pins the order)"

    widened = {**identity.GRANT_MATRIX, "contributor": frozenset({*identity.GRANT_MATRIX["contributor"], "repair"})}
    monkeypatch.setattr(identity, "GRANT_MATRIX", widened)
    with pytest.raises(Refusal) as e2:
        hz.st.repair(PLANNER)  # neither --history nor --journal: past the gate, refused on its argument
    assert e2.value.rule == "repair.target", "the grant check did not consult the matrix value it was given"

    # and the widening is a widening, not a hole: a lander still holds nothing that reaches `repair`
    with pytest.raises(Refusal) as e3:
        hz.st.repair(Caller("factory@example", "lander"))
    assert e3.value.rule == "write.grant"


def test_the_owner_can_still_repair(hz: Harness) -> None:
    """The other half — the seam move must not have closed the door on the grant that holds `"*"`. Without this,
    a `_require` that refused everyone would satisfy every assertion above."""
    with pytest.raises(Refusal) as e:
        hz.st.repair(OWNER)
    assert e.value.rule == "repair.target", e.value.rule


# ---- 2. `install_schemas` installs the registry it was handed -------------------------------------------------


def _forked(src: Registry, tmp: Path, marker: bytes) -> Registry:
    """A registry on disk that is NOT the shipped one: every document byte-identical except `config@1`, which
    carries a comment the package's copy does not, and with `page@1` removed so the SET differs too."""
    tmp.mkdir(parents=True, exist_ok=True)
    for ref, raw in src.source().items():
        if ref == "page@1":
            continue
        (tmp / f"{ref}.toml").write_bytes(marker + raw if ref == "config@1" else raw)
    return Registry.from_directory(tmp)


def test_install_schemas_writes_the_bytes_of_the_registry_it_was_given(tmp_path: Path) -> None:
    """The old code wrote `INSTALLED` from the argument and the FILES from
    `resources.files("isidium.store.registry")`. Both assertions below fail against it: the installed `config@1`
    would lack the marker (the package's bytes), and `page@1.toml` would be written even though the argument's
    registry has no such document.

    `Registry.from_directory` reads the fork back off disk, so the fork is a real registry and not a fixture the
    test alone can construct."""
    marker = b"# a fork of the shipped registry, installed by this test\n"
    shipped = Registry.shipped()
    forked = _forked(shipped, tmp_path / "forked-registry", marker)
    repo = tmp_path / "checkout"
    repo.mkdir()

    written = install_schemas(repo, forked)
    out = repo / ".isidium" / "schemas"

    installed = (out / "config@1.toml").read_bytes()
    assert installed == forked.source()["config@1"], "the installed bytes are not the argument's"
    assert installed.startswith(marker) and installed != shipped.source()["config@1"], "the package's bytes were used"
    assert not (out / "page@1.toml").exists(), "a document the given registry does not have was installed anyway"
    assert {p.name for p in written} == {f"{ref}.toml" for ref in forked.installed}

    # the list and the files are the same registry, which is the property the function exists for (03b §4)
    listed = (out / "INSTALLED").read_text(encoding="utf-8").split()
    assert sorted(listed) == sorted(forked.installed) == sorted(Registry.from_directory(out).installed)


def test_installing_the_shipped_registry_is_byte_identical_to_the_package(tmp_path: Path) -> None:
    """The default path, and the reason the bytes are carried rather than re-serialised: a round trip through
    `tomllib` and back would produce a valid document with a different content address."""
    repo = tmp_path / "checkout"
    repo.mkdir()
    install_schemas(repo, None)
    out = repo / ".isidium" / "schemas"
    package = Path(__import__("isidium.store.registry", fromlist=["x"]).__file__).parent / "schemas"  # type: ignore[arg-type]
    for ref, raw in Registry.shipped().source().items():
        assert (out / f"{ref}.toml").read_bytes() == raw == (package / f"{ref}.toml").read_bytes(), ref
    assert Registry.from_directory(out).addresses == Registry.shipped().addresses


def test_a_registry_cannot_be_built_without_the_bytes_it_claims_to_hold() -> None:
    """The invariant that keeps the property above from decaying: a `Registry` whose `source` disagrees with its
    documents would install a list it cannot back, which is the defect one level in."""
    shipped = Registry.shipped()
    docs = {ref: shipped.get(ref) for ref in shipped.installed}
    source = dict(shipped.source())
    source.pop("page@1")
    with pytest.raises(Refusal, match=r"registry\.source-mismatch"):
        Registry(docs, source)


# ---- 3. the typed verdicts travel as data --------------------------------------------------------------------


def _bad_story(hz: Harness) -> tuple[str, Mapping[str, Any], Mapping[str, Any]]:
    """A ratified story missing two independently-checked things, so the refusal carries MORE THAN ONE verdict —
    a one-element list is indistinguishable from the flattened string it replaces."""
    cid = hz.draft("two-verdicts")
    doc, head = hz.st.show(cid)
    bad = dict(doc.head)
    bad["status"] = "ratified"
    bad.pop("acceptance")
    bad.pop("priority")
    return hz.st.path_of(cid) or "", bad, head


def test_a_validation_refusal_keeps_its_verdicts_as_a_list() -> None:
    """`detail` stays the rendered summary — that is the additive half of Q7 — but the list is the truth."""
    hz = fresh("verdicts")
    path, bad, head = _bad_story(hz)
    from isidium.store.core.grammar import Document

    with pytest.raises(ValidationRefusal) as e:
        hz.st.write(path, Document(dict(bad), {}), head, None, OWNER)
    r = e.value
    rules = [v.rule for v in r.verdicts]
    assert r.rule == "validate.failed"
    assert "profile.story.acceptance" in rules and "profile.story.priority" in rules, rules
    assert len(r.verdicts) >= 2 and all(isinstance(v, Refusal) for v in r.verdicts)
    assert r.detail == "; ".join(str(v) for v in r.verdicts), "the summary must still render the same list"


def test_the_wire_carries_the_verdicts_and_the_client_rebuilds_them() -> None:
    """End to end over the value the service actually sends. **The discriminator is that the field names are read
    off the array**: `verdicts[i]["path"]` names the failed key with no parsing of `detail` at all, which is what
    lets an agent self-correct (C-12) instead of escalating. The old payload had no array, so every assertion on
    `payload["verdicts"]` fails against it.

    The three original fields are asserted unchanged, because Q7's ruling is that this is a wire EXTENSION: a
    client that reads only `{rule, path, detail}` keeps working."""
    hz = fresh("verdicts-wire")
    path, bad, head = _bad_story(hz)
    from isidium.store.core.grammar import Document

    with pytest.raises(ValidationRefusal) as e:
        hz.st.write(path, Document(dict(bad), {}), head, None, OWNER)

    response = Response.refusal(e.value)
    payload = json.loads(response.body)
    assert response.status == 422
    assert payload["rule"] == "validate.failed" and payload["detail"] == e.value.detail  # additive, not a break
    assert [dict(v) for v in payload["verdicts"]] == [
        {"rule": v.rule, "path": v.path, "detail": v.detail} for v in e.value.verdicts
    ]
    assert "acceptance" in {v["path"] for v in payload["verdicts"]}, "the field name is not on the wire as data"

    rebuilt = refusal_from(payload)
    assert isinstance(rebuilt, ValidationRefusal)
    assert [(v.rule, v.path, v.detail) for v in rebuilt.verdicts] == [
        (v.rule, v.path, v.detail) for v in e.value.verdicts
    ]
    assert rebuilt.detail == e.value.detail


def test_the_tool_call_door_hands_the_model_the_array_too(tmp_path: Path) -> None:
    """**The door Q7 was argued from.** The whole case for disclosing validation detail is that naming the field
    lets an agent self-correct instead of escalating, and the agent reads this surface — yet `McpServer._call` built
    its own `{rule, path, detail}` dict, so an array added to `Response.refusal` alone would have reached every
    caller except the one the ruling is about. Both doors now serialise `Refusal.payload()`, which is also where
    C-12's disclosure filter belongs ("the refusal-to-payload constructor that all three share"), so K2b writes the
    table once rather than three times.

    The discriminator is `structuredContent`, not the text blob: the verdicts arrive as structure the model can
    read a field name out of, which is the difference between this and the prose it replaces."""
    hz = fresh("verdicts-mcp")
    path, bad, head = _bad_story(hz)
    from isidium.store.client.mcp import McpServer
    from isidium.store.core.grammar import Document

    class _Refusing:
        def call(self, name: str, args: Mapping[str, Any]) -> Any:
            return hz.st.write(path, Document(dict(bad), {}), head, None, OWNER)

    r = McpServer(_Refusing(), tmp_path, "docs/work/").handle(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "write", "arguments": {}}}
    )
    assert r is not None and r["result"]["isError"] is True
    body = r["result"]["structuredContent"]
    assert body["rule"] == "validate.failed"
    assert {v["rule"] for v in body["verdicts"]} >= {"profile.story.acceptance", "profile.story.priority"}
    assert "acceptance" in {v["path"] for v in body["verdicts"]}
    assert json.loads(r["result"]["content"][0]["text"]) == body  # the two representations cannot drift


def test_a_refusal_with_no_verdicts_crosses_the_wire_unchanged() -> None:
    """The arm that makes the change additive rather than a break: every non-validation gate, and an older store
    answering a validation one, sends the three fields alone and must rebuild as a plain `Refusal`."""
    plain = Refusal("write.stale", "config.toml", "head {'seq': 3}")
    payload = json.loads(Response.refusal(plain).body)
    assert "verdicts" not in payload
    rebuilt = refusal_from(payload)
    assert type(rebuilt) is Refusal
    assert (rebuilt.rule, rebuilt.path, rebuilt.detail) == (plain.rule, plain.path, plain.detail)


def test_the_schema_documents_parse_from_the_bytes_the_registry_carries() -> None:
    """A cheap floor under item 2: the carried bytes are the document, not a stale copy of one. Without it, a
    `source` map populated with anything at all would satisfy the byte-identity assertions above."""
    reg = Registry.shipped()
    for ref, raw in reg.source().items():
        doc = tomllib.loads(raw.decode("utf-8"))
        assert f"{doc['name']}@{doc['version']}" == ref
        assert doc == reg.get(ref)
