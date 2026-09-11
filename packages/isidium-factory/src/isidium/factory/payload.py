"""The run payload (03 §1.17; T-B3) — one pure function of (the card at `base_sha`, its refs' bytes, the neighborhood
block, the config, identity) [V1, 2026-09-10].

*"Hash = required, payload ⊇ hash"*: the value below carries the card's gated set canonical — the specification, and
the round trip T-B3 names (*"payload card content == card at hash"*: `build_hash` is recomputed here through the
store's own construction) — the resolved `refs` with their excerpts, the `source_narrative` excerpt, the neighborhood
block byte for byte, the constraints and the identity. `payload_hash` is the prefixed digest of the value's canonical
bytes; `config_hash` is the policy chain's own `build` at `base_sha`, so a reader checks it against `config.toml`'s
history without a second construction.

**Nothing here touches git or the store.** The bytes come in typed (`Inputs`); `checkout.py` is the half that reads
them. That split is what makes *"same inputs ⇒ same payload hash"* a property a test can hold rather than a hope,
and what the Rust port transcribes.

**Excerpts, one rule per ref form** — the content half `server/refs.resolve` declined to hold (Q11: the store reads
no content; *"the assembler runs it at dispatch"*): a `Path` ref is the whole file; `Lines` the range; an `Anchor` the
section from its heading through the line before the next heading of the same or a higher level; a `Symbol` the
definition through the line before the next definition at the same or a shallower indent. The locus is checked
first, on a `Locus` built once per file (F27); every verdict is collected in the written order and raised as **one**
`payload.incomplete` — the design queue reads every cell from one refusal.

**Oversize refuses; nothing compresses.** *"A payload that does not fit is a card that is too broad, not a prompt to
be compressed."* The block's own eviction already ran in the store. The cap is the caller's (`Caps`): the record homes
the budget in tokens (`[effort].budgets`) and the bytes↔tokens relation is unmeasured (Q-V8, the v1c chunk plan).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from isidium.store.core import canon, telemetry
from isidium.store.core.grammar import Document
from isidium.store.core.refs import _ASSIGN_DEF, _HEADING, _SYMBOL_DEF, Locus, Ref, github_slug, locus_check
from isidium.store.core.refusal import Refusal

FORM: Final = "isidium-payload 1"
SPAN: Final = "isidium.factory.payload.assemble"
REFS_CITED: Final = "isidium.refs.cited"
PAYLOAD_BYTES: Final = "isidium.payload.bytes"

# The config tables the run reads (T-B3: *"the threshold-config subset the run needs"*). `payload` for the caps the
# block was fitted to, `effort` for the tier's budget, `surfaces` for the deny set, `runners` for close, `ladder` for
# the dispatchable leaf (Q-V6). A table absent from the effective config is absent here, never defaulted (C-1).
CONFIG_SUBSET: Final[tuple[str, ...]] = ("root", "schema", "payload", "effort", "surfaces", "runners", "ladder")


@dataclass(frozen=True)
class Identity:
    """Which bot, which adapter (T-B3). In V1 the CLI's options; V3's dispatch fills them from the factory's config."""

    bot: str
    adapter: str


@dataclass(frozen=True)
class Caps:
    """The byte cap the value must fit — the caller's, until Q-V8 homes it."""

    max_bytes: int


@dataclass(frozen=True)
class Inputs:
    tenant: str
    card_id: int
    base_sha: str
    card: Document
    gated_x: frozenset[str]
    refs: Mapping[str, tuple[str, bytes]]  # repo path → (blob id, bytes) at `base_sha`, every path the card cites
    context: Mapping[str, Any]  # the store's `show neighborhood` answer: {context: <value>, text: <delivered>}
    tree: Mapping[str, Any]  # `config.toml` at `base_sha`, parsed
    eff: Mapping[str, Any]  # its effective overlay (the adopted schema's defaults under it)
    identity: Identity
    caps: Caps


@dataclass(frozen=True)
class Payload:
    value: Mapping[str, Any]
    payload_hash: str
    config_hash: str
    bytes: int

    @property
    def refs_resolved(self) -> list[dict[str, str]]:
        """The fingerprint's shape (03 §5.4): `{path, blob}` per ref, in the written order."""
        return [{"path": r["path"], "blob": r["blob"]} for r in self.value["refs"]]

    @property
    def context(self) -> dict[str, Any]:
        """The run record's four fields (03 §6)."""
        c = self.value["context"]
        return {"depth": c["depth"], "bytes": c["bytes"], "cards": list(c["cards"]), "truncated": c["truncated"]}

    def record(self) -> dict[str, Any]:
        """What the ledger row will carry (V3) and what the CLI prints: the hashes, the size, the resolution list."""
        return {
            "payload_hash": self.payload_hash,
            "config_hash": self.config_hash,
            "bytes": self.bytes,
            "base_sha": self.value["base_sha"],
            "refs_resolved": self.refs_resolved,
            "context": self.context,
        }


# ---- excerpts -----------------------------------------------------------------------------------------------------


def _heading_level(line: str) -> int:
    n = 0
    while n < len(line) and line[n] == "#":
        n += 1
    return n


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" \t"))


def excerpt(ref: Ref, locus: Locus) -> str:
    """The lines a ref names, after `locus_check` said they exist. `lines` are `Locus`'s (decoded once, split on
    newlines); the result is those lines joined by newlines, the whole file for a `Path` ref."""
    lines = locus.lines
    if ref.kind == "path":
        return "\n".join(lines)
    if ref.kind == "lines":
        return "\n".join(lines[ref.l1 - 1 : ref.l2])
    if ref.kind == "anchor":
        start = _anchor_line(ref.anchor, lines)
        level = _heading_level(lines[start])
        end = len(lines)
        for i in range(start + 1, len(lines)):
            m = _HEADING.match(lines[i])
            if m and _heading_level(lines[i]) <= level:
                end = i
                break
        return "\n".join(lines[start:end])
    start = _symbol_line(ref.symbol, lines)
    indent = _indent(lines[start])
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if _is_definition(lines[i]) and _indent(lines[i]) <= indent:
            end = i
            break
    return "\n".join(lines[start:end])


def _is_definition(line: str) -> bool:
    """`Locus.symbols`' own test — a keyword definition or a top-level assignment — so an excerpt ends where the
    index would count the next symbol."""
    return bool(_SYMBOL_DEF.match(line) or _ASSIGN_DEF.match(line))


def _anchor_line(anchor: str, lines: Sequence[str]) -> int:
    for i, ln in enumerate(lines):
        m = _HEADING.match(ln)
        if m and (m.group("explicit") == anchor or github_slug(m.group("text")) == anchor):
            return i
    raise AssertionError(anchor)  # `locus_check` passed: the heading is there


def _symbol_line(symbol: str, lines: Sequence[str]) -> int:
    for i, ln in enumerate(lines):
        m = _SYMBOL_DEF.match(ln) or _ASSIGN_DEF.match(ln)
        if m and m.group("name") == symbol:
            return i
    raise AssertionError(symbol)  # `locus_check` counted exactly one


# ---- the function -------------------------------------------------------------------------------------------------


@dataclass
class _Resolver:
    """Every cited ref against the bytes handed in — one `Locus` per file however many refs cite it (F27); the
    verdicts that failed collected in the written order."""

    refs: Mapping[str, tuple[str, bytes]]
    loci: dict[str, Locus]
    failed: list[str]

    def row(self, text: str) -> dict[str, str] | None:
        try:
            ref = Ref.parse(text)
        except Refusal as r:
            self.failed.append(f"{text}: {r.rule}")
            return None
        got = self.refs.get(ref.path)
        if got is None:
            self.failed.append(f"{text}: ref.unresolved (no such path at base_sha)")
            return None
        blob, data = got
        locus = self.loci.get(ref.path)
        if locus is None:
            locus = self.loci[ref.path] = Locus(data)
        why = locus_check(ref, locus)
        if why is not None:
            self.failed.append(f"{text}: {why}")
            return None
        return {"ref": text, "path": ref.path, "blob": blob, "excerpt": excerpt(ref, locus)}


def assemble(inp: Inputs) -> Payload:
    """The payload for one card at one `base_sha`, or `payload.incomplete` / `payload.oversize`."""
    head = inp.card.head
    scope = inp.card.scope()
    with telemetry.span(SPAN) as sp:
        rs = _Resolver(inp.refs, {}, [])
        cited = [str(t) for t in head.get("refs", [])]
        rows = [r for r in (rs.row(t) for t in cited) if r is not None]
        narrative = head.get("source_narrative")
        sourced: dict[str, str] | None = None
        if isinstance(narrative, Mapping) and narrative:
            anchor = str(narrative.get("anchor", ""))
            sourced = rs.row(f"{narrative.get('path', '')}#{anchor}")
            if sourced is not None:
                sourced = {k: sourced[k] for k in ("path", "blob", "excerpt")} | {"anchor": anchor}
        sp.set_attribute(REFS_CITED, len(cited) + (1 if narrative else 0))
        if rs.failed:
            refusal = Refusal("payload.incomplete", rs.failed[0].split(":", 1)[0], "; ".join(rs.failed))
            telemetry.record_refusal_on(sp, refusal.rule)
            raise refusal

        value: dict[str, Any] = {
            "form": FORM,
            "tenant": inp.tenant,
            "card": inp.card_id,
            "base_sha": inp.base_sha,
            "build_hash": canon.build_hash(head, scope, inp.gated_x),
            "gated": canon.build_input(head, scope, inp.gated_x),
            "refs": rows,
            "context": _context(inp.context, inp.eff),
            "constraints": _constraints(head, inp.eff),
            "identity": {"bot": inp.identity.bot, "adapter": inp.identity.adapter},
            "config_hash": _config_hash(inp.tree),
        }
        if sourced is not None:
            value["source_narrative"] = sourced
        data = canon.canonical_json(value).encode("utf-8")
        sp.set_attribute(PAYLOAD_BYTES, len(data))
        if len(data) > inp.caps.max_bytes:
            refusal = Refusal("payload.oversize", f"card {inp.card_id}", f"{len(data)} bytes > {inp.caps.max_bytes}")
            telemetry.record_refusal_on(sp, refusal.rule)
            raise refusal
        telemetry.record_ok()
        return Payload(value, "sha256:" + canon.sha256_hex(data), value["config_hash"], len(data))


def _config_hash(tree: Mapping[str, Any]) -> str:
    """The policy chain's own `build` (03 §5.1): `config.toml` minus `[history]` under the schema version the file
    names — the same string the config's history carries at `base_sha`."""
    v = tree.get("schema", 1)
    return canon.policy_build_hash(dict(tree), v if isinstance(v, int) and not isinstance(v, bool) else 1)


def _context(answer: Mapping[str, Any], eff: Mapping[str, Any]) -> dict[str, Any]:
    """The block as delivered (`text`, byte for byte) beside the run record's four fields, read off the value the
    store returned with it: every member id — stubs included, a handle the builder holds — and the block's canonical
    size, which is what `max_bytes` measured."""
    block = answer["context"]
    ids: list[int] = []
    for key in ("parents", "siblings", "dependencies", "dependents"):
        ids.extend(int(m["id"]) for m in block.get(key, []))
    for key in ("milestone", "sprint"):
        m = block.get(key)
        if m is not None:
            ids.append(int(m["id"]))
    return {
        "text": str(answer["text"]),
        "depth": int(eff["payload"]["context"]["depth"]),
        "bytes": len(canon.canonical_json(block).encode("utf-8")),
        "cards": sorted(set(ids)),
        "truncated": bool(block.get("truncated", False)),
    }


def _constraints(head: Mapping[str, Any], eff: Mapping[str, Any]) -> dict[str, Any]:
    """The card's `surfaces` (its write ceiling), the effective deny set, its effort tier and that tier's budget when
    `[effort].budgets` names one — absent otherwise: the *"factory default"* the schema mentions is declared nowhere
    yet, and a number here would be the code default C-1 forbids — and the config subset the run reads."""
    out: dict[str, Any] = {
        "surfaces": [str(s) for s in head.get("surfaces", [])],
        "deny": [str(d) for d in eff["surfaces"]["deny"]],
        "config": {k: eff[k] for k in CONFIG_SUBSET if k in eff},
    }
    if "effort" in head:
        tier = str(head["effort"])
        out["effort"] = tier
        budgets = eff["effort"].get("budgets")
        if isinstance(budgets, Mapping) and tier in budgets:
            out["budget_tokens"] = int(budgets[tier])
    return out
