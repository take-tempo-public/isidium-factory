"""One schema, three consumers (03b §4): the generated model and the tool schemas must be exactly what the registry
renders — drift is a failing test, not a hope. And the typed model must not change what the hasher sees (W10, T6)."""

from __future__ import annotations

from typing import Any

import pytest

from isidium.store.core import canon
from isidium.store.registry import codegen
from isidium.store.registry.generated.models import CardHead, InboxRecord
from isidium.store.registry.loader import Registry

REG = Registry.shipped()


def test_no_drift() -> None:
    stale = codegen.drift(REG)
    assert not stale, "regenerate: python -m isidium.store.registry.codegen — " + ", ".join(p.name for p in stale)


def test_absent_stays_absent_through_the_typed_model() -> None:
    """The one dump: `exclude_unset=True, by_alias=True`. A defaulted key the caller did not set must not appear —
    the build hash of the dumped tree equals the hash of what the caller wrote (T6's explicit-vs-absent pair)."""
    raw: dict[str, Any] = {"schema": 1, "id": 42, "status": "draft", "source": "session", "title": "t"}
    dumped = CardHead.model_validate(raw).model_dump(exclude_unset=True, by_alias=True)
    assert dumped == raw
    assert canon.build_hash(dumped, "scope") == canon.build_hash(raw, "scope")
    with_effort = {**raw, "effort": "default"}
    assert canon.build_hash(
        CardHead.model_validate(with_effort).model_dump(exclude_unset=True, by_alias=True), "scope"
    ) != canon.build_hash(raw, "scope")


def test_keyword_and_reserved_names_are_aliased() -> None:
    """`for` and `from` are Python keywords, `schema` shadows a pydantic attribute — all three keep their wire name."""
    rec = InboxRecord.model_validate(
        {
            "type": "intake",
            "seq": 1,
            "at": "2026-08-27T00:00:00Z",
            "id": "s1",
            "by": "a@b",
            "for": "c@d",
            "from": {"run": "r-1"},
            "h": "sha256:" + "ab" * 32,  # the store computes it; the record schema requires it
        }
    )
    dumped = rec.model_dump(exclude_unset=True, by_alias=True)
    assert dumped["for"] == "c@d" and dumped["from"] == {"run": "r-1"}
    head = CardHead.model_validate({"schema": 1, "id": 1, "status": "draft", "source": "session", "title": "t"})
    assert head.model_dump(exclude_unset=True, by_alias=True)["schema"] == 1


def test_the_model_is_closed_and_typed() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        CardHead.model_validate({"schema": 1, "id": 1, "status": "draft", "source": "session", "title": "t", "misc": 1})
    with pytest.raises(ValidationError):
        CardHead.model_validate({"schema": 1, "id": 1, "status": "nope", "source": "session", "title": "t"})
    with pytest.raises(ValidationError):  # the scenario union is discriminated on `kind`
        CardHead.model_validate(
            {
                "schema": 1,
                "id": 1,
                "status": "draft",
                "source": "session",
                "title": "t",
                "acceptance": {"scenarios": [{"id": "S1", "kind": "command", "title": "t", "observable": {}}]},
            }
        )
    ok = CardHead.model_validate(
        {
            "schema": 1,
            "id": 1,
            "status": "draft",
            "source": "session",
            "title": "t",
            "acceptance": {
                "scenarios": [
                    {
                        "id": "S1",
                        "kind": "command",
                        "title": "t",
                        "action": {"run": ["x"]},
                        "observable": {"exit_code": 0},
                    }
                ]
            },
        }
    )
    assert ok.acceptance is not None and ok.acceptance.scenarios[0].kind == "command"


def test_tool_schemas_cover_the_surface() -> None:
    schemas = codegen.tool_schemas()
    assert set(schemas) == {"write", "ratify", "show", "check", "suggest", "disposition"}
    for name, spec in schemas.items():
        assert spec["description"] and spec["inputSchema"]["type"] == "object", name
        assert spec["inputSchema"].get("additionalProperties") is False, name
    # E2: the card schema is spelled once, on `write`; `ratify` references the shape by description, not by copy
    defs = schemas["write"]["inputSchema"]["$defs"]
    assert defs["CardHead"]["properties"]["status"]["enum"] == ["draft", "ratified", "closed", "withdrawn"]
    assert schemas["write"]["inputSchema"]["properties"]["document"] == {"$ref": "#/$defs/CardDocument"}
    assert "$defs" not in schemas["ratify"]["inputSchema"]
    import json as _json

    assert len(_json.dumps(schemas)) < 30_000, "the planner pays tools/list on every invocation (round 42)"
