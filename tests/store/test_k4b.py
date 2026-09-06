"""K4b — the author's terminal checks a ref's sub-file locus (Q11's residue; the brief in the chunk plan).

The store's half of `refs` resolution is the tree's: the path exists, its blob id, outside the root. The other half —
does the line range, the anchor or the symbol land on anything — needs the file's text, and since Q11 the store
holds none of it. That half ran only at dispatch, so a ref that was never valid on a card that is never dispatched
was never caught. Now the client runs it **before the call**, from the working tree, through the one function the
assembler runs (`core.refs.locus_check`), and every door a ref can enter by — `write` with a document, `write --set
refs=[…]`, `ratify --writes`, `ratify <id>`, and the MCP `write`/`ratify` tools — is held to it here.

What is proven, and by which discriminator:

* **refused locally, and the store is not called** — a recording transport whose `calls` stays empty, beside the
  same document passing through when its refs are right (so an empty list means refused, not broken);
* **the working tree, not `HEAD`** — the cited files are written into the checkout and never committed, so a door
  reading `HEAD:` would find nothing to check and let every bad locus through;
* **existence is left to the store** — a ref to a path that is not here passes through, with the span saying it
  looked at nothing (`checked = 0` beside `cited = 1`);
* **one function, by substitution** — replacing `core.refs.locus_check` changes what the CLI door and the MCP door
  both do; a door that grew its own copy survives the behavioural assertions and fails only that one (K3b's shape,
  `test_walk.py`), and `tools/mutations/k4b.toml`'s M5 is exactly that copy.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
import typer

from isidium.store.client import cli as cli_mod
from isidium.store.client import locus
from isidium.store.client.install import install
from isidium.store.client.mcp import McpServer
from isidium.store.core import refs as refs_mod
from isidium.store.core import telemetry
from isidium.store.core.grammar import CARD, Document, emit_markdown, parse_head, parse_markdown
from isidium.store.core.refusal import Refusal, ValidationRefusal

from .conftest import BASE_SCOPE, Telemetry, base_head, tenant_checkout
from .test_apply import CODE, NOTES
from .test_walk import client_cfg

ROOT = "docs/work/"
GOOD = ["src/thing.py", "src/thing.py:1-2", "docs/notes.md#the-anchor-here", "src/thing.py::resolve_me"]
BAD = ["src/thing.py:1-99", "docs/notes.md#missing", "src/thing.py::Twice", "src/thing.py::absent"]
BAD_RULES = ["ref.unresolved", "ref.unresolved", "ref.ambiguous", "ref.unresolved"]


class Recorder:
    """A channel that remembers every call and answers all of them — what the door must never reach on a refusal."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def call(self, name: str, args: Mapping[str, Any]) -> Any:
        self.calls.append((name, dict(args)))
        return {"answered": name}


@pytest.fixture
def tenant(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A tenant checkout with the client installed and the two cited files in the **working tree only** — written
    after the seed commit and never added, which is what makes every pass below evidence that the door reads the
    tree the author is editing rather than `HEAD`."""
    work = tenant_checkout(tmp_path)
    install(work, client_cfg(ROOT))
    (work / "src").mkdir()
    (work / "src/thing.py").write_bytes(CODE)
    (work / "docs/notes.md").write_bytes(NOTES)
    monkeypatch.chdir(work)
    return work


@pytest.fixture
def channel(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    """The CLI's transport, replaced by a recorder at the one place `_run` builds it."""
    rec = Recorder()
    monkeypatch.setattr(cli_mod, "Transport", lambda _cfg, _workdir: rec)
    return rec


def document(refs: list[str]) -> dict[str, Any]:
    head = base_head(0, "draft")
    head["refs"] = refs
    return {"head": head, "scope": BASE_SCOPE}


def document_file(path: Path, refs: list[str]) -> Path:
    path.write_text(json.dumps(document(refs)), encoding="utf-8")
    return path


def refused(err: str) -> list[str]:
    """The verdicts' rule ids as the CLI printed them — one `validate.failed` line carrying every cell."""
    line = next(ln for ln in err.splitlines() if ln.startswith("validate.failed"))
    return [part.split(" @ ")[0].strip() for part in line.split(": ", 1)[1].split("; ")]


def test_a_ref_whose_locus_does_not_land_is_refused_before_the_store_is_called(
    tenant: Path, channel: Recorder, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The four refs the store accepts (its trees see the paths) and the terminal now refuses, in one refusal
    carrying every verdict; and the four good ones going through to the channel, which is what says the empty
    `calls` above was a refusal and not a door that stopped working."""
    with pytest.raises(typer.Exit) as exited:
        cli_mod.write(new="bad-locus", document=document_file(tmp_path / "bad.json", BAD))
    assert exited.value.exit_code == 2
    assert channel.calls == [], "the store was called for a document the terminal could already refuse"
    err = capsys.readouterr().err
    assert refused(err) == BAD_RULES, err
    assert "src/thing.py:1-99: the range runs past the end of the file" in err
    assert "src/thing.py::Twice: defined more than once" in err

    cli_mod.write(new="good-locus", document=document_file(tmp_path / "good.json", GOOD))
    assert [(n, a["new_slug"], a["document"]["head"]["refs"]) for n, a in channel.calls] == [
        ("write", "good-locus", GOOD)
    ]


def test_the_door_reads_the_working_tree_and_leaves_existence_to_the_store(
    tenant: Path, channel: Recorder, tmp_path: Path
) -> None:
    """Three refs the door must let through, each for a different reason, all in one document so one call proves
    them together: a path that is not in the checkout (the store answers `ref.unresolved` from its tree, and a
    local refusal would be a false positive on a checkout that is merely behind); a path that climbs out of the
    checkout, whose target exists and would fail — the door reads nothing outside the tree; and a whole-file ref,
    which has no locus. The bytes it *does* read are the uncommitted ones (the fixture), so the same document's
    bad symbol is still refused: the pass-through is selective, not a door left open."""
    (tmp_path / "outside.py").write_bytes(b"x = 1\n")
    through = ["nope.md:1-2", "../outside.py::nothing", "src/thing.py"]
    cli_mod.write(new="through", document=document_file(tmp_path / "through.json", through))
    assert [a["document"]["head"]["refs"] for _n, a in channel.calls] == [through]

    with pytest.raises(typer.Exit):
        cli_mod.write(new="mixed", document=document_file(tmp_path / "mixed.json", [*through, "src/thing.py::Twice"]))
    assert len(channel.calls) == 1

    # The policy door carries no refs at all, whatever its document says.
    assert locus.refs_of("write", {"path": "config.toml", "document": {"head": {"refs": BAD}}}, tenant, ROOT) == []


def card_file(tenant: Path, cid: int, refs: list[str]) -> Path:
    """A card as the store writes it, in the checkout's tracking root — the head is all `ratify <id>` reads."""
    path = tenant / ROOT / "cards" / f"{cid:04d}-a-card.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    head = base_head(cid, "draft")
    head["refs"] = refs
    path.write_text(emit_markdown(Document(head, {"Scope": BASE_SCOPE}), CARD), encoding="utf-8", newline="\n")
    return path


def test_every_door_a_ref_can_enter_by_is_held_to_the_check(
    tenant: Path, channel: Recorder, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--set refs=[…]`, `ratify --writes`, `ratify <id>` (the card read from the checkout) and the MCP tool — each
    refused with the same verdict, none reaching the channel; and each passing when the ref is right."""
    bad, good = ["src/thing.py::Twice"], ["src/thing.py::resolve_me"]

    with pytest.raises(typer.Exit):
        cli_mod.write(card=7, set_=[f"refs={json.dumps(bad)}"])
    assert channel.calls == []
    assert refused(capsys.readouterr().err) == ["ref.ambiguous"]
    cli_mod.write(card=7, set_=[f"refs={json.dumps(good)}", "priority=P2"])
    assert channel.calls == [("write_set", {"card": 7, "set": [f"refs={json.dumps(good)}", "priority=P2"]})]

    writes = tmp_path / "writes.json"
    writes.write_text(json.dumps([{"new_slug": "w", "document": document(bad)}]), encoding="utf-8")
    with pytest.raises(typer.Exit):
        cli_mod.ratify(writes=writes)
    assert len(channel.calls) == 1
    writes.write_text(json.dumps([{"new_slug": "w", "document": document(good)}]), encoding="utf-8")
    cli_mod.ratify(writes=writes)
    name, sent = channel.calls[-1]
    assert name == "ratify" and sent["writes"][0]["document"]["head"]["refs"] == good

    card_file(tenant, 7, bad)
    with pytest.raises(typer.Exit):
        cli_mod.ratify(ids=[7])
    assert len(channel.calls) == 2
    assert refused(capsys.readouterr().err) == ["ref.ambiguous"]
    card_file(tenant, 7, good)
    cli_mod.ratify(ids=[7], dry_run=False)
    assert channel.calls[-1] == ("ratify", {"ids": [7], "dry_run": False})
    cli_mod.ratify(ids=[8])  # no card 8 here: nothing to check, the store answers for its own copy
    assert channel.calls[-1] == ("ratify", {"ids": [8], "dry_run": True})

    mcp = Recorder()
    server = McpServer(mcp, tenant, ROOT)
    call = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "write", "arguments": {}}}
    call["params"] = {"name": "write", "arguments": {"new_slug": "m", "document": document(bad)}}
    r = server.handle(call)
    assert r is not None and r["result"]["isError"] is True and mcp.calls == []
    body = r["result"]["structuredContent"]
    assert body["rule"] == "validate.failed"
    assert [(v["rule"], v["path"]) for v in body["verdicts"]] == [("ref.ambiguous", "refs")]
    call["params"] = {"name": "write", "arguments": {"new_slug": "m", "document": document(good)}}
    r = server.handle(call)
    assert r is not None and "isError" not in r["result"] and [n for n, _a in mcp.calls] == ["write"]


def test_the_cli_door_and_the_mcp_door_run_the_assemblers_one_function(
    tenant: Path, channel: Recorder, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """**By substitution, not by reading the source.** `core.refs.locus_check` is replaced with a function that
    refuses the one ref both doors would otherwise pass — and remembers the bytes it was handed. Both doors must
    then refuse it; a door with a copy of the check survives this. The bytes it saw are the working tree's
    uncommitted `CODE`, which is trap 2's decision proven rather than described. With the substitution undone both
    doors pass the same ref, so the assertion is about the function they share and not about a stub."""
    seen: list[bytes] = []
    the_one = refs_mod.locus_check

    def refuse_resolve_me(ref: refs_mod.Ref, locus: refs_mod.Locus) -> str | None:
        # the `Locus` is the file's text indexed once (K7b, F27); its lines re-joined are the bytes the door read
        seen.append("\n".join(locus.lines).encode("utf-8"))
        return "ref.unresolved" if ref.symbol == "resolve_me" else None

    monkeypatch.setattr(refs_mod, "locus_check", refuse_resolve_me)
    doc = document_file(tmp_path / "one.json", ["src/thing.py::resolve_me"])
    with pytest.raises(typer.Exit):
        cli_mod.write(new="one", document=doc)
    mcp = Recorder()
    r = McpServer(mcp, tenant, ROOT).handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "write", "arguments": {"new_slug": "one", "document": document(GOOD[3:])}},
        }
    )
    assert r is not None and r["result"]["isError"] is True
    assert channel.calls == [] and mcp.calls == []
    assert seen == [CODE, CODE], "the door handed the function something other than the working tree's bytes"

    monkeypatch.setattr(refs_mod, "locus_check", the_one)  # only this — `undo()` would take the channel's patch too
    cli_mod.write(new="one", document=doc)
    r = McpServer(mcp, tenant, ROOT).handle(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "write", "arguments": {"new_slug": "one", "document": document(GOOD[3:])}},
        }
    )
    assert r is not None and "isError" not in r["result"]
    assert [n for n, _a in channel.calls] == ["write"] and [n for n, _a in mcp.calls] == ["write"]


def test_the_preflight_is_a_span_that_says_what_it_looked_at(tenant: Path, otel: Telemetry) -> None:
    """C-11 at the client's door: one span per pre-flight, the outcome as its status, the rule id as an attribute
    on a refusal and absent on a pass, and — the attribute a diagnosis needs — how many refs the call carried
    beside how many loci were actually read. A ref to a path that is not here is the case the two numbers exist
    to tell apart: `cited = 1, checked = 0` is a pass that looked at nothing, and it must say so."""
    otel.clear()
    with pytest.raises(ValidationRefusal) as refused_:
        locus.preflight("write", {"new_slug": "s", "document": document(BAD)}, tenant, ROOT)
    assert [v.rule for v in refused_.value.verdicts] == BAD_RULES
    locus.preflight("write", {"new_slug": "s", "document": document(GOOD)}, tenant, ROOT)
    locus.preflight("write", {"new_slug": "s", "document": document(["nope.md::f"])}, tenant, ROOT)
    locus.preflight("show", {"target": "card", "id": 1}, tenant, ROOT)  # not a door: no span, no read

    spans = otel.spans(locus.PREFLIGHT_SPAN)
    assert [s.status.status_code.name for s in spans] == ["ERROR", "OK", "OK"]
    bad, good, absent = spans
    assert bad.attributes[telemetry.RULE] == "validate.failed" and bad.attributes[telemetry.ACTION] == "write"
    assert (bad.attributes[locus.REFS_CITED], bad.attributes[locus.REFS_CHECKED]) == (4, 4)
    assert telemetry.RULE not in good.attributes
    assert (good.attributes[locus.REFS_CITED], good.attributes[locus.REFS_CHECKED]) == (4, 3)  # the whole-file ref
    assert (absent.attributes[locus.REFS_CITED], absent.attributes[locus.REFS_CHECKED]) == (1, 0)


def test_the_head_alone_is_the_full_parses_head() -> None:
    """`parse_head` is `parse_markdown`'s first half, not a second fence grammar: the same head from the same bytes,
    and the same refusals — a BOM, a missing fence, a fence inside a string, text that is not TOML."""
    raw = emit_markdown(Document(base_head(3), {"Scope": BASE_SCOPE}), CARD)
    assert parse_head(raw) == parse_markdown(raw, CARD).head
    assert parse_head(raw.replace("\n", "\r\n")) == parse_head(raw)
    for text, rule in [
        ("﻿" + raw, "head.bom"),
        ("# no fence\n", "head.fence"),
        ("```toml\nid = 1\n", "head.fence"),
        ('```toml\ntitle = """\n```\n', "head.fence-in-string"),
        ("```toml\nnot toml\n```\n", "head.toml"),
    ]:
        with pytest.raises(Refusal) as e:
            parse_head(text)
        assert e.value.rule == rule, text
        with pytest.raises(Refusal) as e2:
            parse_markdown(text, CARD)
        assert e2.value.rule == rule, text
