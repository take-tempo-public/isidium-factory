"""The one builder of a `DocSchema` from a registry document — shared by the store and the forge's verifier [K12].

Until K12 this lived twice: `Store.doc_schema` in the server and a line-for-line mirror in `tools/verify_chain.py`,
held equal by a test because the tool could not import the server. The tool's docstring said the chunk that moved
the builder into `registry/` would delete the mirror and the test's other half. This is that module: the registry
document says what the parser needs — the sections in order, whether the footer is required, the prose bound — and
the head's table order is the card's (`CARD_TABLE_ORDER`) or nothing.
"""

from __future__ import annotations

from ..core.grammar import CARD_TABLE_ORDER, DocSchema, SectionSpec
from .loader import Registry


def doc_schema(registry: Registry, ref: str) -> DocSchema:
    """A `DocSchema` built from the registry's `name@version` document. Uncached: the store caches per ref, the
    verifier asks once per document kind it meets."""
    doc = registry.get(ref)
    name = ref.split("@", 1)[0]
    sections = tuple(
        SectionSpec(str(s["name"]), "updates" if s["name"] == "Updates" else "prose", bool(s.get("required", False)))
        for s in doc.get("sections", [])
    )
    bound = max(
        [int(s.get("max_bytes", 1 << 20)) for s in doc.get("sections", []) if s.get("kind") == "prose"] or [1 << 20]
    )
    genesis = "card" if name == "card" else "page"
    return DocSchema(
        name, genesis, sections, CARD_TABLE_ORDER if name == "card" else (), doc.get("footer") == "history", bound
    )
