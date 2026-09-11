"""V1 (2026-09-10) — the run payload: one pure function over typed inputs (`isidium.factory.payload`), the gatherer
that reads them from a checkout at one revision (`isidium.factory.checkout`), and the `payload` verb.

The pure half is tested over the harness double (L5's graph, so the block has members) and over hand-built
documents (the refusals need refs the store would never ratify); the gatherer over a real checkout and a real store
on disk (K3's shape). Every refusal asserted is the typed one.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from isidium.factory import checkout as checkout_mod
from isidium.factory import cli as cli_mod
from isidium.factory import payload as payload_mod
from isidium.factory.payload import Caps, Identity, Inputs, assemble
from isidium.store.core import canon
from isidium.store.core.grammar import Document, parse_markdown
from isidium.store.core.refs import Locus, Ref
from isidium.store.core.refusal import Refusal
from isidium.store.server.store import NewCard, Store

from ..store.conftest import (
    BASE_SCOPE,
    OWNER,
    PLANNER,
    REF_FILES,
    Harness,
    base_head,
    fresh,
    git,
    path_of,
    store_on_disk,
    tenant_checkout,
)
from ..store.test_l5 import graph

ROOT = "docs/work/"
WHO = Identity("factory-bot@agents.example", "container")
WIDE = Caps(1 << 20)


def refuses(rule: str, fn: Callable[[], Any]) -> Refusal:
    with pytest.raises(Refusal) as ei:
        fn()
    assert ei.value.rule == rule, str(ei.value)
    return ei.value


def answer_of(st: Store, cid: int) -> dict[str, Any]:
    """The api's `show neighborhood` answer, as the CLI's channel returns it."""
    block = st.show(("Neighborhood", cid))
    return {"context": block.as_dict(), "text": block.render()}


def inputs_of(hz: Harness, cid: int, **over: Any) -> Inputs:
    """The pure inputs for a card the harness store holds: its bytes, the ref targets the double seeded, the
    block, the config and its overlay."""
    st = hz.st
    p = path_of(st, cid)
    card = parse_markdown(st.raw[p].decode("utf-8"), st.doc_schema("card@1"))
    refs = {rel: (st.repo.oid_of(rel) or "", data) for rel, data in REF_FILES.items()}
    kw: dict[str, Any] = {
        "tenant": st.tenant,
        "card_id": cid,
        "base_sha": st.repo.head or "",
        "card": card,
        "gated_x": st.gated_x(),
        "refs": refs,
        "context": answer_of(st, cid),
        "tree": st.config_tree,
        "eff": st.eff,
        "identity": WHO,
        "caps": WIDE,
    }
    kw.update(over)
    return Inputs(**kw)


def bare_inputs(head: dict[str, Any], refs: dict[str, tuple[str, bytes]], hz: Harness, **over: Any) -> Inputs:
    """Inputs over a hand-built document — for refs the store would never ratify — with an empty block."""
    empty = {
        "context": {
            "card": head["id"],
            "parents": [],
            "siblings": [],
            "dependencies": [],
            "dependents": [],
            "truncated": False,
        },
        "text": "",
    }
    kw: dict[str, Any] = {
        "tenant": "t",
        "card_id": int(head["id"]),
        "base_sha": "0" * 40,
        "card": Document(head, {"Scope": BASE_SCOPE}),
        "gated_x": frozenset(),
        "refs": refs,
        "context": empty,
        "tree": hz.st.config_tree,
        "eff": hz.st.eff,
        "identity": WHO,
        "caps": WIDE,
    }
    kw.update(over)
    return Inputs(**kw)


# ---- the pure function -------------------------------------------------------------------------------------------------

GOLDEN = "cad63a82"  # the first eight hex digits of the payload hash over L5's graph — pinned by the first run


def test_the_same_inputs_give_the_same_hash_and_the_value_round_trips_the_card() -> None:
    """Same inputs ⇒ same payload hash (T-B3 (4)), pinned; `build_hash` is the card's own ratified `build` (the round
    trip, T-B3's fidelity); `config_hash` is the policy chain's `build`; the refs in the written order with the blob
    the tree holds; the block byte for byte and every member id in `context.cards`."""
    hz = fresh()
    st = hz.st
    g = graph(hz)
    # the golden is over fixed inputs: the double's commit ids and its signer's key (in `config.toml`) are fresh per
    # harness, so `base_sha` and the tree are pinned here and the live tree is asserted below
    pinned = inputs_of(hz, g.subject, base_sha="0" * 40, tree={"schema": st.config_tree["schema"], "tenant": "sartor"})
    assert assemble(pinned).payload_hash == assemble(pinned).payload_hash
    assert assemble(pinned).payload_hash.removeprefix("sha256:")[:8] == GOLDEN, assemble(pinned).payload_hash
    inp = inputs_of(hz, g.subject)
    once, twice = assemble(inp), assemble(inp)
    assert once.payload_hash == twice.payload_hash and once.value == twice.value
    v = once.value
    assert v["form"] == payload_mod.FORM and v["card"] == g.subject and v["tenant"] == st.tenant
    assert v["build_hash"] == inp.card.history[-1]["build"] == st.cards()[g.subject].history[-1]["build"]
    assert v["gated"]["title"] == inp.card.head["title"] and v["gated"]["scope"] == BASE_SCOPE
    assert once.config_hash == v["config_hash"] == st.policy_build()
    assert [r["ref"] for r in v["refs"]] == list(inp.card.head["refs"]), "the written order"
    assert once.refs_resolved == [
        {"path": Ref.parse(t).path, "blob": st.repo.oid_of(Ref.parse(t).path)} for t in inp.card.head["refs"]
    ]
    assert v["refs"][0]["excerpt"] == "def validate_profile(head):\n    return []\n", "the definition, to the end"
    block = st.show(("Neighborhood", g.subject))
    assert v["context"]["text"] == block.render() and v["context"]["truncated"] is False
    members = {m.id for m in (*block.parents, *block.siblings, *block.depends_on, *block.dependents)}
    assert block.milestone is not None
    members.add(block.milestone.id)
    assert once.context["cards"] == sorted(members) and once.context["depth"] == st.eff["payload"]["context"]["depth"]
    assert once.context["bytes"] == len(block.canonical())
    assert v["constraints"]["surfaces"] == inp.card.head["surfaces"] and v["constraints"]["effort"] == "default"
    assert v["constraints"]["deny"] == list(st.eff["surfaces"]["deny"]) and "budget_tokens" not in v["constraints"]
    assert (
        set(v["constraints"]["config"]) <= set(payload_mod.CONFIG_SUBSET) and v["constraints"]["config"]["root"] == ROOT
    )
    assert v["identity"] == {"bot": WHO.bot, "adapter": WHO.adapter}
    assert once.bytes == len(canon.canonical_json(v).encode("utf-8"))
    rec = once.record()
    assert set(rec) == {"payload_hash", "config_hash", "bytes", "base_sha", "refs_resolved", "context"}


def test_the_hash_covers_the_block_the_identity_and_the_config() -> None:
    """Payload ⊇ hash: a different block text, a different bot, a different config tree each move the hash."""
    hz = fresh()
    g = graph(hz)
    base = assemble(inputs_of(hz, g.subject)).payload_hash
    other_text = dict(inputs_of(hz, g.subject).context)
    other_text["text"] = other_text["text"].replace("truncated=false", "truncated=false ")
    assert assemble(inputs_of(hz, g.subject, context=other_text)).payload_hash != base
    assert assemble(inputs_of(hz, g.subject, identity=Identity("other", WHO.adapter))).payload_hash != base
    tree = dict(hz.st.config_tree)
    tree["wip"] = int(tree.get("wip", 1)) + 1
    moved = assemble(inputs_of(hz, g.subject, tree=tree))
    assert moved.payload_hash != base and moved.config_hash != hz.st.policy_build()
    with_history = dict(tree)
    with_history["history"] = {"entries": [{"seq": 99}]}
    assert assemble(inputs_of(hz, g.subject, tree=with_history)).config_hash == moved.config_hash, "minus [history]"


def test_a_budget_named_for_the_tier_enters_the_constraints() -> None:
    hz = fresh()
    g = graph(hz)
    eff = json.loads(json.dumps(hz.st.eff))
    eff["effort"]["budgets"] = {"default": 120000}
    v = assemble(inputs_of(hz, g.subject, eff=eff)).value
    assert v["constraints"]["budget_tokens"] == 120000


FIXTURE = (
    "# Title\n"
    "\n"
    "intro\n"
    "\n"
    "## Alpha section\n"
    "\n"
    "alpha body\n"
    "\n"
    "### Alpha child\n"
    "\n"
    "child body\n"
    "\n"
    "## Beta section {#beta}\n"
    "\n"
    "beta body\n"
)
CODE = (
    "import os\n\n\ndef one():\n    return 1\n\n\nclass Two:\n    def method(self):\n        return 2\n\n\nTHREE = 3\n"
)


def test_each_ref_form_excerpts_its_own_span() -> None:
    """A `Path` ref is the whole file; `Lines` the range; an `Anchor` its section through the line before the next
    heading of the same or a higher level (a child heading stays inside); a `Symbol` the definition through the
    line before the next definition at the same or a shallower indent (a method stays inside its class)."""
    doc, code = Locus(FIXTURE.encode()), Locus(CODE.encode())
    ex = payload_mod.excerpt
    assert ex(Ref.parse("d.md"), doc) == FIXTURE
    assert ex(Ref.parse("d.md:3-5"), doc) == "intro\n\n## Alpha section"
    assert (
        ex(Ref.parse("d.md#alpha-section"), doc) == "## Alpha section\n\nalpha body\n\n### Alpha child\n\nchild body\n"
    )
    assert ex(Ref.parse("d.md#beta"), doc) == "## Beta section {#beta}\n\nbeta body\n"
    assert ex(Ref.parse("c.py::one"), code) == "def one():\n    return 1\n\n"
    assert ex(Ref.parse("c.py::Two"), code) == "class Two:\n    def method(self):\n        return 2\n\n"
    assert ex(Ref.parse("c.py::method"), code) == "    def method(self):\n        return 2\n\n"
    assert ex(Ref.parse("c.py::THREE"), code) == "THREE = 3\n"


def test_incomplete_names_every_failed_ref_in_one_refusal() -> None:
    """A path the tree does not hold, a range past the end, a heading that is not there, a symbol defined twice and
    a symbol not defined at all — five verdicts, one `payload.incomplete`, the first ref in `path`, all in `detail`
    in the written order (the design queue reads every cell)."""
    hz = fresh()
    twice = b"def dup():\n    pass\n\n\ndef dup():\n    pass\n"
    head = base_head(7, "ratified")
    head["refs"] = ["gone.py", "d.md:40-99", "d.md#nowhere", "c.py::dup", "c.py::absent", "d.md#beta"]
    refs = {"d.md": ("b1", FIXTURE.encode()), "c.py": ("b2", twice)}
    r = refuses("payload.incomplete", lambda: assemble(bare_inputs(head, refs, hz)))
    assert r.path == "gone.py"
    assert r.detail.split("; ") == [
        "gone.py: ref.unresolved (no such path at base_sha)",
        "d.md:40-99: ref.unresolved",
        "d.md#nowhere: ref.unresolved",
        "c.py::dup: ref.ambiguous",
        "c.py::absent: ref.unresolved",
    ]
    head["refs"] = ["d.md#beta"]
    v = assemble(bare_inputs(head, refs, hz)).value
    assert [r["path"] for r in v["refs"]] == ["d.md"] and v["refs"][0]["blob"] == "b1"


def test_the_source_narrative_excerpt_enters_the_payload_and_its_absence_refuses() -> None:
    hz = fresh()
    head = base_head(8, "ratified")
    head["refs"] = []
    head["source_narrative"] = {"path": "d.md", "anchor": "alpha-child"}
    refs = {"d.md": ("b1", FIXTURE.encode())}
    v = assemble(bare_inputs(head, refs, hz)).value
    assert v["refs"] == [] and v["source_narrative"] == {
        "path": "d.md",
        "anchor": "alpha-child",
        "blob": "b1",
        "excerpt": "### Alpha child\n\nchild body\n",
    }
    head["source_narrative"] = {"path": "d.md", "anchor": "gone"}
    r = refuses("payload.incomplete", lambda: assemble(bare_inputs(head, refs, hz)))
    assert r.path == "d.md#gone"
    head.pop("source_narrative")
    assert "source_narrative" not in assemble(bare_inputs(head, refs, hz)).value


def test_oversize_refuses_at_the_cap_with_both_numbers() -> None:
    hz = fresh()
    g = graph(hz)
    fits = assemble(inputs_of(hz, g.subject))
    exact = assemble(inputs_of(hz, g.subject, caps=Caps(fits.bytes)))
    assert exact.payload_hash == fits.payload_hash, "the cap is inclusive"
    r = refuses("payload.oversize", lambda: assemble(inputs_of(hz, g.subject, caps=Caps(fits.bytes - 1))))
    assert r.path == f"card {g.subject}" and r.detail == f"{fits.bytes} bytes > {fits.bytes - 1}"


def test_the_assembly_is_a_span_with_the_refs_cited_and_the_bytes(otel: Any) -> None:
    hz = fresh()
    g = graph(hz)
    otel.clear()
    p = assemble(inputs_of(hz, g.subject))
    spans = otel.spans(payload_mod.SPAN)
    assert len(spans) == 1
    attrs = dict(spans[0].attributes or {})
    assert attrs[payload_mod.REFS_CITED] == 2 and attrs[payload_mod.PAYLOAD_BYTES] == p.bytes


# ---- the gatherer, over a real checkout ---------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def disk(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Store, int]:
    """A tenant checkout, a store on disk over its remote, one ratified card pushed and pulled back."""
    tmp = tmp_path_factory.mktemp("v1")
    work = tenant_checkout(tmp)
    st = store_on_disk(work, tmp / "journal.sqlite", root=ROOT)
    st.init(OWNER, software_key_ack="ok for V1", root=ROOT)
    r = st.write(
        NewCard("payload-subject"), Document(base_head(0, "draft"), {"Scope": BASE_SCOPE}), None, None, PLANNER
    )
    assert r.id is not None
    st.ratify([r.id], OWNER)
    git(work, "pull", "-q", "origin", "main")
    return work, st, r.id


def test_gather_reads_the_card_the_config_and_the_refs_at_the_revision_and_agrees_with_the_store(
    disk: tuple[Path, Store, int],
) -> None:
    work, st, cid = disk
    calls: list[int] = []

    def context_of(c: int) -> dict[str, Any]:
        calls.append(c)
        return answer_of(st, c)

    inp = checkout_mod.gather(
        work, "HEAD", cid, tenant=st.tenant, root=ROOT, context_of=context_of, identity=WHO, caps=WIDE
    )
    assert inp.base_sha == git(work, "rev-parse", "HEAD").strip() and len(inp.base_sha) == 40
    assert calls == [cid], "one store call"
    assert set(inp.refs) == set(REF_FILES) and all(inp.refs[p][1] == REF_FILES[p] for p in REF_FILES)
    assert all(len(inp.refs[p][0]) == 40 for p in REF_FILES), "the blob id git holds"
    assert inp.card.head["id"] == cid and inp.tree == st.config_tree and inp.eff == st.eff
    p = assemble(inp)
    assert p.value["build_hash"] == st.cards()[cid].history[-1]["build"]
    assert p.config_hash == st.policy_build()
    # the same bytes, handed in by hand from the store's side: the same hash
    card = parse_markdown(st.raw[path_of(st, cid)].decode("utf-8"), st.doc_schema("card@1"))
    by_hand = Inputs(
        st.tenant,
        cid,
        inp.base_sha,
        card,
        st.gated_x(),
        inp.refs,
        answer_of(st, cid),
        st.config_tree,
        st.eff,
        WHO,
        WIDE,
    )
    assert assemble(by_hand).payload_hash == p.payload_hash


def test_gather_refuses_an_unknown_card_a_bad_revision_and_a_checkout_without_a_root(
    disk: tuple[Path, Store, int], tmp_path: Path
) -> None:
    work, st, cid = disk
    ctx = lambda c: answer_of(st, c)  # noqa: E731
    r = refuses(
        "factory.unknown-card",
        lambda: checkout_mod.gather(work, "HEAD", 999, tenant="t", root=ROOT, context_of=ctx, identity=WHO, caps=WIDE),
    )
    assert r.path == "999"
    refuses(
        "factory.git",
        lambda: checkout_mod.gather(
            work, "no-such-rev", cid, tenant="t", root=ROOT, context_of=ctx, identity=WHO, caps=WIDE
        ),
    )
    r = refuses(
        "factory.no-root",
        lambda: checkout_mod.gather(work, "HEAD", cid, tenant="t", root=None, context_of=ctx, identity=WHO, caps=WIDE),
    )
    assert "--root" in r.detail
    (work / ".isidium").mkdir(exist_ok=True)
    (work / ".isidium" / "client.toml").write_text(f'tenant = "sartor"\nroot = "{ROOT}"\n', encoding="utf-8")
    assert checkout_mod.root_of(work, None) == ROOT, "the checkout's client file names it"
    assert checkout_mod.root_of(work, "other/") == "other/", "the caller's wins"


def test_the_cat_process_answers_missing_and_closes(disk: tuple[Path, Store, int]) -> None:
    work, _st, _cid = disk
    with checkout_mod.Cat(work) as cat:
        head = cat.get("HEAD")
        assert head is not None and head[1] == "commit"
        assert cat.get("HEAD:no/such/file") is None
        got = cat.get("HEAD:README.md")
        assert got is not None and got[2] == b"a tenant\n"
    assert cat._p.returncode == 0


def test_the_payload_verb_prints_the_record_and_keeps_the_value(
    disk: tuple[Path, Store, int], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from typer.testing import CliRunner

    from isidium.store.client.config import ClientConfig

    work, st, cid = disk

    class Channel:
        def __init__(self, cfg: ClientConfig, workdir: Path) -> None:
            self.calls: list[tuple[str, Any]] = []

        def call(self, name: str, args: Any) -> Any:
            assert (name, args) == ("show", {"target": "neighborhood", "id": cid})
            return answer_of(st, cid)

    monkeypatch.setattr(cli_mod, "tenant_client", lambda tenant: (ClientConfig(tenant=tenant), tmp_path))
    monkeypatch.setattr(cli_mod, "Transport", Channel)
    out = tmp_path / "payload.json"
    args = [
        "payload",
        "--tenant",
        "sartor",
        "--checkout",
        str(work),
        "--card",
        str(cid),
        "--bot",
        WHO.bot,
        "--adapter",
        WHO.adapter,
        "--max-bytes",
        str(WIDE.max_bytes),
        "--root",
        ROOT,
        "--out",
        str(out),
    ]
    res = CliRunner().invoke(cli_mod.app, args)
    assert res.exit_code == 0, res.output
    rec = json.loads(res.output)
    assert rec["payload_hash"].startswith("sha256:") and rec["config_hash"] == st.policy_build()
    value = json.loads(out.read_text(encoding="utf-8"))
    assert value["card"] == cid and value["base_sha"] == rec["base_sha"]
    res = CliRunner().invoke(cli_mod.app, [*args[:-2], "--max-bytes", "10"])
    assert res.exit_code == 2 and "payload.oversize" in res.output


def test_git_is_spawned_twice_per_gather(disk: tuple[Path, Store, int], monkeypatch: pytest.MonkeyPatch) -> None:
    """The brief's number, held: one `ls-tree`, one `cat-file --batch` — however many refs the card cites."""
    work, st, cid = disk
    spawned: list[list[str]] = []
    real_popen = subprocess.Popen

    class Popen(real_popen):  # type: ignore[type-arg]  # every spawn — `run` included — passes through here
        def __init__(self, cmd: Any, *a: Any, **kw: Any) -> None:
            spawned.append(list(cmd))
            super().__init__(cmd, *a, **kw)

    monkeypatch.setattr(subprocess, "Popen", Popen)
    checkout_mod.gather(
        work, "HEAD", cid, tenant="t", root=ROOT, context_of=lambda c: answer_of(st, c), identity=WHO, caps=WIDE
    )
    assert [c[:2] for c in spawned] == [["git", "ls-tree"], ["git", "cat-file"]]
