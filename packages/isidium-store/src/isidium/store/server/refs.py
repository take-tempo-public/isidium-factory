"""`refs` resolution — **the store's half** (03 §1.14; Q11, ruled 2026-08-31): the path exists in the tree, its blob
id, and it is outside the tracking root, from the tree alone and reading no content. The grammar (`Ref.parse`) and
the sub-file locus (`locus_check`) are the pure half and live in `core/refs.py`, where the client can reach them
without importing anything under `server/` [moved by K4b, 2026-09-05]; this module keeps the one function that
needs a tree.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from ..core.refs import Ref
from ..core.refusal import Refusal

ObjectId = Callable[[str], str | None]


def resolve(
    refs: Sequence[str], oid_of: ObjectId, inside_root: Callable[[str], bool]
) -> tuple[list[dict[str, Any]], list[Refusal]]:
    """The store's half: resolve every ref against the **tree** (`oid_of(repo_path) -> blob id | None`).

    Returns `refs_resolved` rows `{path, blob}` in the written order and the refusals (`ref.grammar` ·
    `ref.inside-root` · `ref.unresolved`), collected — the dry run shows every cell.

    **No content is read** [Q11]. The blob id is what the fingerprint records and the only input to `ref-drifted`,
    and git's tree already holds it, so asking for the bytes would both duplicate work the tree has done and reach
    for content the store's footprint forbids it to hold. `ref.ambiguous` is not raised here and cannot be: it is
    `core.refs.locus_check`'s verdict, and `locus_check` runs where the text is.
    """
    resolved: list[dict[str, Any]] = []
    refusals: list[Refusal] = []
    for text in refs:
        try:
            ref = Ref.parse(str(text))
        except Refusal as r:
            refusals.append(r)
            continue
        if inside_root(ref.path):
            refusals.append(Refusal("ref.inside-root", "refs", text))
            continue
        oid = oid_of(ref.path)
        if oid is None:
            refusals.append(Refusal("ref.unresolved", "refs", f"{text}: no such path"))
            continue
        resolved.append({"path": ref.path, "blob": oid})
    return resolved, refusals
