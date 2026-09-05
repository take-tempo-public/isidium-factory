"""The r6-d6 scenarios (the closing check, 220 checks) on the real store — write / ratify / re-ratification / the
predicate / the sitting / holds / closures / withdrawal / born-ratified / the inbox / pages / policy / EARS and
validation / tamper / repair / reconciliation / NewCard / ratify(writes) and the X1 display / the retraction and the
owner's close / questions and origins / the NFC declaration / bindings / the gate refusals. Scenarios that need
`land` or `accept` arrive with v1b (WP5) and are marked so. Sequential on one store, as the oracle ran them."""

from __future__ import annotations

import copy
import json
import re
import unicodedata
from typing import Any

import pytest

from isidium.store.core import canon, chain, derive
from isidium.store.core.grammar import CARD, PAGE, Document, emit_markdown, parse_config, parse_jsonl, parse_markdown
from isidium.store.core.refusal import Refusal, ValidationRefusal
from isidium.store.registry.config import CONFIG_ORDERS
from isidium.store.server import reconcile
from isidium.store.server.store import NewCard, WriteRequest

from .conftest import BASE_SCOPE, LANDER, OWNER, PLANNER, Harness, base_head, fresh, path_of

ACTS_HIT: dict[str, str] = {"config-policy": "init", "binding": "realm", "created": "write"}
IDS: dict[str, Any] = {}


def refuses(rule: str, fn: Any) -> Refusal:
    with pytest.raises(Refusal) as ei:
        fn()
    assert ei.value.rule == rule, str(ei.value)
    return ei.value


def cells(r: Refusal) -> list[str]:
    """The rule ids a `validate.failed` refusal carries, read off the typed list rather than found inside `detail`.

    These assertions used to be `"<rule id>" in r.detail`, which passes on the flattened prose Q7 replaced — so they
    would have kept passing had the array never been built, and the same substring check is what K2b's own test must
    not do. Reading the list is what proves the verdicts survive as data (K1b-iii)."""
    assert isinstance(r, ValidationRefusal), f"{r.rule} carries no verdicts"
    return [v.rule for v in r.verdicts]


def rows_for(hz: Harness) -> Any:
    return lambda path: hz.st.journal.rows_for(path)


def test_write_basics(hz: Harness) -> None:
    st = hz.st
    cid = hz.draft()
    IDS["c1"] = cid
    doc, head = st.show(cid)
    e = doc.history[-1]
    assert e["fields"] == sorted([*doc.head, "scope", "updates"])
    assert "sig" not in e and e["for"] == "amodal1@example"
    assert chain.verify_chain(doc.history, chain.genesis("card", cid)) == ["ok"]
    refuses(
        "write.stale",
        lambda: st.write(
            path_of(st, cid),
            Document(copy.deepcopy(doc.head), copy.deepcopy(doc.sections)),
            {"seq": 0, "h": "x"},
            None,
            PLANNER,
        ),
    )
    refuses(
        "write.no-change",
        lambda: st.write(
            path_of(st, cid), Document(copy.deepcopy(doc.head), copy.deepcopy(doc.sections)), head, None, PLANNER
        ),
    )
    refuses(
        "validate.failed",
        lambda: st.write(
            path_of(st, cid),
            Document({**copy.deepcopy(doc.head), "misc": 1}, copy.deepcopy(doc.sections)),
            head,
            None,
            PLANNER,
        ),
    )
    r = st.write_set(cid, ['summary="short"'], PLANNER)
    ACTS_HIT["summarized"] = "write --set"
    assert r.entry["act"] == "summarized" and r.entry["fields"] == ["summary"] and r.entry["build"] == e["build"]
    r = st.write_set(cid, ["updates+=later|more text"], PLANNER)
    ACTS_HIT["noted"] = "write --set"
    assert r.entry["act"] == "noted" and r.entry["fields"] == ["updates"]
    r = st.write_set(cid, ['questions=[{id="Q1", text="which runner?"}]'], PLANNER)
    ACTS_HIT["amended"] = "write --set"
    assert r.entry["act"] == "amended" and r.entry["fields"] == ["questions"]
    r = st.write_set(cid, ["questions=[]"], PLANNER)  # a draft's author may delete its own question (1.11)
    assert r.entry["act"] == "amended" and r.entry["fields"] == ["questions"]
    st.write_set(cid, ['questions=[{id="Q1", text="which runner?"}]'], PLANNER)
    r = st.write_set(cid, ["questions=[]", 'answers=[{question_id="Q1", text="pytest"}]'], PLANNER)
    ACTS_HIT["answered"] = "write"
    assert r.entry["act"] == "answered" and r.entry["fields"] == ["answers", "questions"]
    raw = st.raw[str(st.path_of(cid))].decode("utf-8")
    p = parse_markdown(raw, CARD)
    assert emit_markdown(p, CARD) == raw
    assert raw.endswith("\n]\n```\n")
    # every store write is one journal row and one commit, pushed
    assert st.journal.verify() and hz.st.repo.pushed == len(st.journal.rows())  # type: ignore[attr-defined]


def test_ratify_single_with_content(hz: Harness) -> None:
    st, signer = hz.st, hz.signer
    cid = hz.draft("single")
    IDS["c2"] = cid
    doc, head = st.show(cid)
    new = Document(copy.deepcopy(doc.head), copy.deepcopy(doc.sections))
    new.head["status"] = "ratified"
    new.head["title"] = "changed in the same write"
    calls = signer.calls
    refuses("write.requires-owner", lambda: st.write(path_of(st, cid), new, head, None, PLANNER))
    r = st.write(path_of(st, cid), new, head, None, OWNER)
    ACTS_HIT["ratified"] = "write"
    assert r.entry["act"] == "ratified" and r.entry["fields"] == ["status", "title"]
    assert r.entry["build"] == canon.build_hash(new.head, BASE_SCOPE) and r.entry["build"] != doc.history[-1]["build"]
    assert "sig" in r.entry and "batch" not in r.entry and signer.calls == calls + 1
    assert signer.shown[-1] == [(cid, "ratified", r.entry["build"], None)]
    assert st.verify_entry(r.entry)
    assert st.check(cid)["integrity"] == []


def test_reratification(hz: Harness) -> None:
    st = hz.st
    cid = IDS["c2"]
    doc, head = st.show(cid)
    new = Document(copy.deepcopy(doc.head), copy.deepcopy(doc.sections))
    new.head["rules"][0]["text"] += " (clarified)"
    refuses("write.requires-owner", lambda: st.write(path_of(st, cid), new, head, None, PLANNER))
    r = st.write(path_of(st, cid), new, head, None, OWNER)
    assert r.entry["act"] == "ratified" and r.entry["fields"] == ["rules"] and "sig" in r.entry
    assert st.check(cid)["integrity"] == []
    p = st.path_of(cid)
    per_commit = []
    for sha in st.repo.first_parent_walk(None):
        for path, (bb, ab) in st.repo.touched(sha).items():
            if path == p and ab:
                n_after = len(parse_markdown(st.repo.blob(ab).decode(), CARD).history)
                n_before = len(parse_markdown(st.repo.blob(bb).decode(), CARD).history) if bb else 0
                per_commit.append(n_after - n_before)
    assert all(n == 1 for n in per_commit), per_commit
    r = st.write_set(cid, ['status="draft"'], PLANNER)
    ACTS_HIT["demoted"] = "write --set"
    assert r.entry["act"] == "demoted" and "sig" not in r.entry
    r = st.write_set(cid, ['status="ratified"'], OWNER)
    assert r.entry["act"] == "ratified" and "sig" in r.entry


def test_sitting(hz: Harness) -> None:
    st, signer = hz.st, hz.signer
    ids = [hz.draft(f"batch-{i}") for i in range(3)]
    IDS["batch"] = ids
    calls, jn = signer.calls, len(st.journal.rows())
    dry = st.ratify(ids, PLANNER, dry_run=True)
    assert signer.calls == calls and len(st.journal.rows()) == jn
    assert all(v == [] for v in dry["verdicts"].values()), dry["verdicts"]
    assert [d[1] for d in dry["display"]] == ["ratified"] * 3 and all(
        d[2].startswith("sha256:") for d in dry["display"]
    )
    refuses("write.grant", lambda: st.ratify(ids, PLANNER))  # the grant matrix, first
    r = st.ratify(ids, OWNER)
    ACTS_HIT["batch-manifest"] = "ratify"
    assert signer.calls == calls + 1
    rows = st.journal.rows()
    assert len(rows) == jn + 1 and len(rows[-1]["paths"]) == 4
    man = r["manifest"]
    assert (
        st.policy[-1] is man and man["act"] == "batch-manifest" and man["ref"] == sorted(e["h"] for e in r["entries"])
    )
    assert all("sig" not in e and e["batch"] == man["seq"] for e in r["entries"])
    assert (
        man["by"] == OWNER.principal
        and man["fields"] == []
        and man["build"] == st.policy_build()
        and "sig" in man
        and "batch" not in man
    )
    assert len({e["at"] for e in r["entries"]} | {man["at"]}) == 1
    assert r["batch_hash"] == chain.batch_hash([e["h"] for e in r["entries"]])
    assert all(chain.link(st.show(i)[0].history[-2]["h"], e) == e["h"] for i, e in zip(ids, r["entries"], strict=True))
    assert all(st.verify_entry(e) for e in r["entries"])
    keep = man["sig"]
    man["sig"] = keep[:-4] + "AAAA"
    assert not any(st.verify_entry(e) for e in r["entries"])
    man["sig"] = keep
    assert signer.shown[-1] == r["display"]
    assert all(st.check(i)["integrity"] == [] for i in ids)
    cfg_tree, hist, rs = parse_config(st.raw["config.toml"].decode(), CONFIG_ORDERS)
    assert rs == [] and hist[-1]["act"] == "batch-manifest" and "history" not in cfg_tree
    opened = cfg_tree.get("chain_opened_under", cfg_tree["schema"])  # config@2 records it (K6); the harness opens at 2
    assert all(v == "ok" for v in chain.verify_chain(hist, chain.genesis("policy", "sartor", opened)))
    # the signer refuses a request outside its clock ± time_skew
    saved = signer.clock
    signer.clock = lambda: hz.clock.t + 5000
    refuses("signer.time-skew", lambda: st.ratify([hz.draft("late")], OWNER))
    signer.clock = saved


def test_holds(hz: Harness) -> None:
    st = hz.st
    cid = IDS["batch"][0]
    r = st.write_set(cid, ['hold.kind="blocked"', "hold.on.owner=true"], PLANNER)
    ACTS_HIT["held"] = "write --set"
    assert (
        r.entry["act"] == "held" and "sig" not in r.entry and r.entry["build"] == st.show(cid)[0].history[-2]["build"]
    )
    refuses("write.requires-owner", lambda: st.write_set(cid, ['hold.kind="watching"'], PLANNER))
    refuses("write.requires-owner", lambda: st.write_set(cid, ["hold="], PLANNER))
    r = st.write_set(cid, ['hold.kind="deferred"'], PLANNER)
    assert r.entry["act"] == "held" and "sig" not in r.entry
    r = st.write_set(cid, ["hold="], OWNER)
    ACTS_HIT["released"] = "write --set"
    assert r.entry["act"] == "released" and "sig" in r.entry and r.entry["fields"] == ["hold"]
    st.write_set(cid, ['hold.kind="watching"'], PLANNER)
    r = st.write_set(cid, ["hold="], PLANNER)
    assert r.entry["act"] == "released" and "sig" not in r.entry


def test_closure_and_accept(hz: Harness) -> None:
    st = hz.st
    cid = IDS["batch"][1]
    doc, head = st.show(cid)
    new = Document(copy.deepcopy(doc.head), copy.deepcopy(doc.sections))
    closure = {
        "id": "c1",
        "kind": "human",
        "outcome": {"deviated": {"description": "S2 skipped on Windows"}},
        "verdicts": {"S1": "pass", "S2": "manual"},
        "evidence": [],
        "retracted": False,
    }
    new.head["closures"] = [closure]
    new.head["status"] = "closed"
    r = st.write(path_of(st, cid), new, head, None, PLANNER)
    ACTS_HIT["closed"] = "write"
    assert r.entry["act"] == "closed" and r.entry["fields"] == ["closures", "status"] and "sig" not in r.entry
    assert r.entry["build"] == doc.history[-1]["build"]
    assert st.projections()[cid].render() == "closed (pending-review)"
    doc2, head2 = st.show(cid)
    ret = Document(copy.deepcopy(doc2.head), copy.deepcopy(doc2.sections))
    ret.head["closures"][0]["retracted"] = True
    ret.head["status"] = "ratified"
    assert derive.needs_signature(doc2.head, ret.head, ["closures", "status"], None) is None
    ref = canon.closure_ref(closure)
    raw_before = st.raw[str(st.path_of(cid))]
    refuses(
        "write.requires-owner",
        lambda: st.write(
            path_of(st, cid), Document(copy.deepcopy(doc2.head), copy.deepcopy(doc2.sections)), head2, ref, PLANNER
        ),
    )
    r = st.write(path_of(st, cid), Document(copy.deepcopy(doc2.head), copy.deepcopy(doc2.sections)), head2, ref, OWNER)
    ACTS_HIT["accepted"] = "write --ref"
    assert r.entry["act"] == "accepted" and r.entry["fields"] == [] and r.entry["ref"] == ref and "sig" in r.entry
    assert re.fullmatch(r"c1:sha256:[0-9a-f]{64}", r.entry["ref"])
    assert st.raw[str(st.path_of(cid))].startswith(raw_before[: -len(b"]\n```\n")])
    assert st.check(cid)["integrity"] == []
    assert st.projections()[cid].render() == "closed (unverified)"
    doc3, head3 = st.show(cid)
    ro = Document(copy.deepcopy(doc3.head), copy.deepcopy(doc3.sections))
    ro.head["reopens"] = [{"id": "o1", "closure_id": "c1", "reason": "S2 must run"}]
    ro.head["status"] = "ratified"
    r = st.write(path_of(st, cid), ro, head3, ref, OWNER)
    ACTS_HIT["reopened"] = "write --ref"
    assert r.entry["act"] == "reopened" and "sig" in r.entry
    doc4, head4 = st.show(cid)
    cl2 = Document(copy.deepcopy(doc4.head), copy.deepcopy(doc4.sections))
    cl2.head["closures"].append(
        {
            "id": "c2",
            "kind": "human",
            "outcome": "met",
            "verdicts": {"S1": "pass", "S2": "pass"},
            "evidence": [],
            "retracted": False,
        }
    )
    cl2.head["status"] = "closed"
    st.write(path_of(st, cid), cl2, head4, None, PLANNER)
    assert st.projections()[cid].render() == "closed (pending-ingest)"
    doc5, head5 = st.show(cid)
    rt = Document(copy.deepcopy(doc5.head), copy.deepcopy(doc5.sections))
    rt.head["closures"][-1]["retracted"] = True
    r = st.write(path_of(st, cid), rt, head5, None, PLANNER)
    ACTS_HIT["retracted"] = "write"
    assert r.entry["act"] == "retracted" and "sig" not in r.entry
    assert st.show(cid)[0].history[-1]["build"] == doc.history[-1]["build"]


def test_withdraw(hz: Harness) -> None:
    st = hz.st
    cid = hz.draft("wd")
    st.ratify([cid], OWNER)
    r = st.write_set(cid, ['status="withdrawn"', 'withdrawn_reason="superseded"'], PLANNER)
    ACTS_HIT["withdrawn"] = "write --set"
    assert r.entry["act"] == "withdrawn" and "sig" not in r.entry
    assert st.projections()[cid].render() == "withdrawn (pending-review)"
    refuses("write.requires-owner", lambda: st.write_set(cid, ['status="ratified"', "withdrawn_reason="], PLANNER))
    r = st.write_set(cid, ['status="ratified"', "withdrawn_reason="], OWNER)
    ACTS_HIT["unwithdrawn"] = "write --set"
    assert r.entry["act"] == "unwithdrawn" and "sig" in r.entry
    r = st.write_set(cid, ['status="withdrawn"', 'withdrawn_reason="really"'], OWNER)
    assert r.entry["act"] == "withdrawn" and "sig" in r.entry
    assert st.projections()[cid].render() == "withdrawn"
    refuses("status.forbidden", lambda: st.write_set(cid, ['status="ratified"'], OWNER))
    d = hz.draft("wd-draft")
    st.write_set(d, ['status="withdrawn"', 'withdrawn_reason="never mind"'], PLANNER)
    refuses("status.forbidden", lambda: st.write_set(d, ['status="draft"', "withdrawn_reason="], OWNER))


def test_born_ratified(hz: Harness) -> None:
    st = hz.st
    r = st.write(NewCard("born"), Document(base_head(0, "ratified"), {"Scope": BASE_SCOPE}), None, None, OWNER)
    assert r.entry["act"] == "created" and "sig" in r.entry
    IDS["c3"] = r.id
    refuses(
        "write.requires-owner",
        lambda: st.write(
            NewCard("born2"), Document(base_head(0, "ratified"), {"Scope": BASE_SCOPE}), None, None, PLANNER
        ),
    )
    assert r.id is not None
    assert st.projections()[r.id].render() == "ready"


def test_inbox(hz: Harness) -> None:
    st = hz.st
    r = st.suggest(
        PLANNER,
        "card",
        "add a --json flag to show",
        "show prints TOML only; agents want JSON",
        ["client/cards/show.py"],
        source="session",
    )
    # `inbox@1` declares no default for `source`: every caller knows its own, so naming it is required
    refuses("inbox.source", lambda: st.suggest(PLANNER, "docs", "t", "b"))
    rec = r.entry
    assert rec["id"].startswith("s")
    prev = st.inbox[-2]["h"] if len(st.inbox) > 1 else chain.genesis("inbox", "sartor")
    assert chain.link(prev, rec) == rec["h"]
    # 05 §2: dispositions are mechanically the owner's — the planner composes, the owner makes it (the review's C4)
    refuses("write.grant", lambda: st.disposition(rec["id"], "accepted", PLANNER, as_="card", slug="json-flag"))
    out = st.disposition(rec["id"], "accepted", OWNER, as_="card", slug="json-flag")
    card = st.docs[out["card"].path]
    assert card.head["status"] == "draft" and card.head["source"] == "suggestion" and card.head["see"] == [rec["id"]]
    assert (
        st.inbox[-1]["type"] == "disposition"
        and st.inbox[-1]["on"] == rec["id"]
        and st.inbox[-1]["card"] == card.head["id"]
    )
    refuses("inbox.bound", lambda: st.suggest(PLANNER, "docs", "x" * 121, "b", source="session"))
    refuses("canon.forbidden-codepoint", lambda: st.suggest(PLANNER, "docs", "zero​width", "b", source="session"))
    parsed = parse_jsonl(st.raw["suggestions.jsonl"].decode())
    assert [p["h"] for p in parsed] == [x["h"] for x in st.inbox]
    q = st.show("Queue")
    assert q.inbox_counts == {} and q.dispositions_since_batch >= 1


def test_page(hz: Harness) -> None:
    st = hz.st
    doc = Document(
        {"schema": 1, "title": "Conventions", "slug": "conventions"},
        {"Body": "Write cards, not prose.\n\n### Why\n\nBecause."},
    )
    # pages are declared by the tenant: add the manifest row first (a signed config-policy act)
    tree = copy.deepcopy(st.config_tree)
    tree["governed"].append({"path": "pages/*.md", "schema": "page@1", "write": ["owner", "contributor"]})
    st.write("config.toml", tree, {"seq": st.policy[-1]["seq"], "h": st.policy[-1]["h"]}, None, OWNER)
    r = st.write("pages/conventions.md", doc, None, None, PLANNER)
    assert r.entry["act"] == "created" and r.entry["fields"] == ["body", "schema", "slug", "title"]
    raw = st.raw["pages/conventions.md"].decode()
    p = parse_markdown(raw, PAGE)
    assert emit_markdown(p, PAGE) == raw
    assert chain.verify_chain(p.history, chain.genesis("page", "pages/conventions.md")) == ["ok"]
    doc2 = Document(dict(p.head), {"Body": str(p.sections["Body"]) + "\n\nMore."})
    r = st.write("pages/conventions.md", doc2, {"seq": 1, "h": p.history[0]["h"]}, None, PLANNER)
    assert r.entry["act"] == "amended" and r.entry["fields"] == ["body"]
    refuses(
        "body.prose-bound",
        lambda: st.write(
            "pages/big.md",
            Document({"schema": 1, "title": "b", "slug": "big"}, {"Body": "x" * 9000}),
            None,
            None,
            PLANNER,
        ),
    )


def test_policy(hz: Harness) -> None:
    st = hz.st
    tree = copy.deepcopy(st.config_tree)
    tree["shapes"]["allowed"].append("classic")
    head = {"seq": st.policy[-1]["seq"], "h": st.policy[-1]["h"]}
    refuses("write.grant", lambda: st.write("config.toml", tree, head, None, PLANNER))  # the manifest gate, first
    r = st.write("config.toml", tree, head, None, OWNER)
    assert r.entry["act"] == "config-policy" and r.entry["fields"] == ["shapes"] and "sig" in r.entry
    assert st.verify_entry(r.entry)
    assert st.eff["shapes"]["allowed"][-1] == "classic" and st.eff["wip"] == 1


def test_ears_and_validation(hz: Harness) -> None:
    st = hz.st
    head = base_head(0, "draft")
    head["shape"] = "ears"
    head["narrative"] = {"system": "store"}
    head["rules"] = [{"id": "R1", "text": "When a write arrives, the store shall journal it before applying it."}]
    head["acceptance"]["scenarios"][0]["rule"] = "R1"
    head["acceptance"]["scenarios"][1]["rule"] = "R1"
    cid = st.write(NewCard("ears"), Document(head, {"Scope": BASE_SCOPE}), None, None, PLANNER).id
    assert cid is not None
    head["id"] = cid
    dry = st.ratify([cid], PLANNER, dry_run=True)
    assert dry["verdicts"][cid] == [], dry["verdicts"]
    doc, hd = st.show(cid)
    bad = copy.deepcopy(head)
    bad["rules"][0]["text"] = "The store should journal quickly."
    r = refuses(
        "validate.failed", lambda: st.write(path_of(st, cid), Document(bad, dict(doc.sections)), hd, None, PLANNER)
    )
    assert {"profile.ears.weak-word", "profile.ears.grammar"} <= set(cells(r))  # `should` fails both
    bad2 = copy.deepcopy(head)
    bad2["surfaces"] = ["docs/work/cards/0001-x.md"]
    r = refuses(
        "validate.failed", lambda: st.write(path_of(st, cid), Document(bad2, dict(doc.sections)), hd, None, PLANNER)
    )
    assert "surfaces.intersects-tracking-root" in cells(r)
    bad2b = copy.deepcopy(head)
    bad2b["surfaces"] = [".github/workflows/ci.yml"]
    r = refuses(
        "validate.failed", lambda: st.write(path_of(st, cid), Document(bad2b, dict(doc.sections)), hd, None, PLANNER)
    )
    assert "surfaces.intersects-deny-set" in cells(r)
    bad3 = copy.deepcopy(head)
    bad3["x"] = {"ratio": 0.5}
    r = refuses(
        "validate.failed", lambda: st.write(path_of(st, cid), Document(bad3, dict(doc.sections)), hd, None, PLANNER)
    )
    assert "canon.float" in cells(r)
    bad4 = copy.deepcopy(head)
    bad4["depends_on"] = [3, 3]
    r = refuses(
        "validate.failed", lambda: st.write(path_of(st, cid), Document(bad4, dict(doc.sections)), hd, None, PLANNER)
    )
    assert "canon.set-duplicate" in cells(r)


def test_tamper(hz: Harness) -> None:
    st = hz.st
    cid = IDS["c3"]
    p = str(st.path_of(cid))
    raw = st.raw[p].decode("utf-8")
    lines = raw.split("\n")
    i = next(i for i, ln in enumerate(lines) if ln.startswith("  { seq = 1,"))
    lines[i] = lines[i].replace('seq = 1, at = "2', 'seq = 1, at = "3', 1)
    st.raw[p] = "\n".join(lines).encode("utf-8")
    c = st.check(cid)
    assert "tampered" in c["integrity"] and c["chain"][0] == "tampered"
    doc = parse_markdown(raw, CARD)
    h = chain.genesis("card", cid)
    for e in doc.history:
        if e["seq"] == 1:
            e["at"] = "2026-01-01T00:00:00Z"
        e["h"] = h = chain.link(h, e)
    st.raw[p] = emit_markdown(doc, CARD).encode("utf-8")
    c = st.check(cid)
    assert all(v == "ok" for v in c["chain"]) and "unverified" in c["integrity"]
    st.raw[p] = raw.encode("utf-8")
    assert st.check(cid)["integrity"] == []


def test_repair_history(hz: Harness) -> None:
    st = hz.st
    cid = IDS["c3"]
    p = str(st.path_of(cid))
    st.write_set(cid, ['summary="to be repaired"'], PLANNER)
    st.write_set(cid, ["updates+=note|before the damage"], PLANNER)
    raw = st.raw[p].decode("utf-8")
    doc = parse_markdown(raw, CARD)
    doc.history[1]["h"] = "sha256:" + "0" * 64
    st.raw[p] = emit_markdown(doc, CARD).encode("utf-8")
    st.docs[p] = doc
    st.repo.commit({p: st.raw[p]}, "someone", st.now(), "damage outside the store")
    assert "tampered" in st.check(cid)["integrity"]
    refuses("write.grant", lambda: st.repair(PLANNER, history=cid, restart_from=1))  # the grant matrix, not a
    # hand-written owner test: `repair` moved onto the seam in K1b-iii, so the rule id is the matrix gate's
    r = st.repair(OWNER, history=cid, restart_from=1)
    ACTS_HIT["repaired"] = "repair --history"
    e = r["entry"]
    assert e["act"] == "repaired" and e["fields"] == ["history"] and e["ref"] == 1 and "sig" in e and "note" in e
    doc2 = parse_markdown(st.raw[p].decode(), CARD)
    verdicts = chain.verify_chain(doc2.history, chain.genesis("card", cid))
    assert verdicts[0] == "ok" and verdicts[-1] == "ok" and all(v == "covered" for v in verdicts[1:-1]), verdicts
    assert e["seq"] == len(doc2.history)


def test_reconcile(hz: Harness) -> None:
    st = hz.st
    cid = IDS["c3"]
    p = str(st.path_of(cid))
    rr = reconcile.reconcile_range(st.repo, None, rows_for(hz), st.is_governed_repo_path)
    unexpl = [(sha, path) for sha, m in rr.items() for path, v in m.items() if v != "explained"]
    assert all(path == p for _, path in unexpl), unexpl  # the damage commit above is the only one
    hand = st.raw[p].replace(b"## Scope", b"## Scope\n\nhand-edited")
    sha = st.repo.commit({p: hand}, "someone", st.now(), "hand edit")
    assert reconcile.reconcile_commit(st.repo, sha, rows_for(hz), st.is_governed_repo_path)[p] == "unjournaled"
    refuses("write.grant", lambda: st.repair(PLANNER, journal=sha))
    r = st.repair(OWNER, journal=sha)
    row = r["journal_row"]
    assert "sig" in row and row["repairs"] == sha
    rows = st.journal.rows()
    prev = rows[-2]["h"]
    assert chain.link(prev, {k: v for k, v in row.items() if k not in ("h", "sig")}) == row["h"]
    assert chain.link(prev, {k: v for k, v in row.items() if k not in ("h", "sig", "repairs")}) != row["h"]
    assert reconcile.reconcile_commit(st.repo, sha, rows_for(hz), st.is_governed_repo_path)[p] == "explained"
    assert st.journal.verify()
    doc, head = st.show(cid)
    prior = Document(copy.deepcopy(doc.head), copy.deepcopy(doc.sections))
    prior.sections["Scope"] = str(prior.sections["Scope"]).replace("hand-edited\n\n", "", 1)
    r2 = st.write(p, prior, head, None, OWNER)
    assert reconcile.reconcile_commit(st.repo, r2.commit, rows_for(hz), st.is_governed_repo_path)[p] == "explained"
    doc, head = st.show(cid)
    fake = copy.deepcopy(doc.history[-1])
    fake["seq"] += 1
    fake["at"] = st.now()
    fake["act"] = "noted"
    fake["fields"] = ["updates"]
    fake.pop("sig", None)
    fake["h"] = chain.link(doc.history[-1]["h"], fake)
    from isidium.store.core.grammar import append_history_line

    data = append_history_line(st.raw[p].decode(), fake).encode()
    sha = st.repo.commit({p: data}, OWNER.principal, fake["at"], "hand-written line")
    assert reconcile.reconcile_commit(st.repo, sha, rows_for(hz), st.is_governed_repo_path)[p] == "unjournaled"
    for r_ in st.journal.rows():
        # journal@2's shape (K6): `schema` inside the content; `credential` only when a channel wrote the row, and
        # this store is driven directly. `test_k6.py` covers the credential and the trace.
        assert "h_prev" not in r_ and set(r_) - {"repairs", "sig"} == {"seq", "at", "schema", "caller", "paths", "h"}


def test_d6_newcard(hz: Harness) -> None:
    st = hz.st
    before = st.journal.counter
    r = st.write(NewCard("new-card"), Document(base_head(0, "draft"), {"Scope": BASE_SCOPE}), None, None, PLANNER)
    assert r.id == before + 1 and r.path == f"cards/{r.id:04d}-new-card.md" and r.head == {"seq": 1, "h": r.entry["h"]}
    assert st.docs[r.path].head["id"] == r.id and st.raw[r.path].startswith(
        b"```toml\nschema = 1\nid = " + str(r.id).encode()
    )
    refuses(
        "validate.failed",
        lambda: st.write(
            NewCard("bad"), Document({**base_head(0, "draft"), "misc": 1}, {"Scope": BASE_SCOPE}), None, None, PLANNER
        ),
    )
    r2 = st.write(NewCard("after-burn"), Document(base_head(0, "draft"), {"Scope": BASE_SCOPE}), None, None, PLANNER)
    assert r2.id == r.id + 2  # a refused creation burns an id
    refuses(
        "id.not-allocated",
        lambda: st.write(
            st.card_path(r2.id + 5, "x"),
            Document(base_head(r2.id + 5, "draft"), {"Scope": BASE_SCOPE}),
            None,
            None,
            PLANNER,
        ),
    )
    assert isinstance(st.show("Inbox"), list)
    assert isinstance(st.show("Board"), str) and st.show("Board").startswith("# Board")
    assert st.show(("Schema", "config@1"))["name"] == "config"


def test_d6_batch_writes(hz: Harness) -> None:
    st, signer = hz.st, hz.signer
    a = hz.draft("x1-release")
    b = hz.draft("x1-answer", questions=[{"id": "Q1", "text": "which runner?"}])
    c = hz.draft("x1-accept")
    st.ratify([a, b, c], OWNER)
    st.write_set(a, ['hold.kind="blocked"', "hold.on.owner=true"], PLANNER)
    doc_c, head_c = st.show(c)
    closed = Document(copy.deepcopy(doc_c.head), copy.deepcopy(doc_c.sections))
    closure = {
        "id": "c1",
        "kind": "human",
        "outcome": {"deviated": {"description": "S2 manual"}},
        "verdicts": {"S1": "pass", "S2": "manual"},
        "evidence": [],
        "retracted": False,
    }
    closed.head["closures"] = [closure]
    closed.head["status"] = "closed"
    st.write(path_of(st, c), closed, head_c, None, PLANNER)
    q = st.show("Queue")
    assert a in q.holds_on_owner and b in q.open_questions and c in q.closures_pending_review
    da, ha = st.show(a)
    ra = Document(copy.deepcopy(da.head), copy.deepcopy(da.sections))
    ra.head.pop("hold")
    db, hb = st.show(b)
    rb = Document(copy.deepcopy(db.head), copy.deepcopy(db.sections))
    rb.head["questions"] = []
    rb.head["answers"] = [{"question_id": "Q1", "text": "pytest"}]
    dc, hc = st.show(c)
    rc = Document(copy.deepcopy(dc.head), copy.deepcopy(dc.sections))
    reqs = [
        WriteRequest(str(st.path_of(a)), ra, ha),
        WriteRequest(str(st.path_of(b)), rb, hb),
        WriteRequest(str(st.path_of(c)), rc, hc, canon.closure_ref(closure)),
    ]
    calls, jn = signer.calls, len(st.journal.rows())
    dry = st.ratify(reqs, PLANNER, dry_run=True)
    assert [d[1] for d in dry["display"]] == ["released", "ratified", "accepted"], dry["display"]
    assert all(v == [] for v in dry["verdicts"].values()) and signer.calls == calls and len(st.journal.rows()) == jn
    assert dry["display"][1][3]["questions_removed"] == ["Q1"] and dry["display"][1][3]["answers_added"] == ["Q1"]
    stale = st.ratify([WriteRequest(str(st.path_of(a)), ra, {"seq": 0, "h": "x"})], PLANNER, dry_run=True)
    assert any(v.startswith("write.stale") for v in stale["verdicts"][a])
    refuses("write.grant", lambda: st.ratify(reqs, PLANNER))  # the grant matrix, first
    r = st.ratify(reqs, OWNER)
    assert signer.calls == calls + 1 and len(st.journal.rows()) == jn + 1 and len(st.journal.rows()[-1]["paths"]) == 4
    assert [e["act"] for e in r["entries"]] == ["released", "ratified", "accepted"]
    assert [e["fields"] for e in r["entries"]] == [["hold"], ["answers", "questions"], []]
    assert r["entries"][2]["ref"] == canon.closure_ref(closure) and "ref" not in r["entries"][0]
    assert all("sig" not in e and e["batch"] == r["manifest"]["seq"] and st.verify_entry(e) for e in r["entries"])
    assert signer.shown[-1] == dry["display"]
    assert (
        "hold" not in st.show(a)[0].head and st.show(b)[0].head["answers"] and st.show(c)[0].head["status"] == "closed"
    )
    assert all(st.check(i)["integrity"] == [] for i in (a, b, c))
    d = hz.draft("x1-mix")
    dd, hd = st.show(b)
    rb2 = Document(copy.deepcopy(dd.head), copy.deepcopy(dd.sections))
    rb2.head["title"] += " (re-ratified)"
    r = st.ratify([d, WriteRequest(str(st.path_of(b)), rb2, hd)], OWNER)
    assert [e["act"] for e in r["entries"]] == ["ratified", "ratified"] and r["entries"][1]["fields"] == ["title"]
    # C7: a request whose diff needs no signature is refused as a batch member
    de, he = st.show(d)
    tend = Document(copy.deepcopy(de.head), copy.deepcopy(de.sections))
    tend.head["summary"] = "just tending"
    dry = st.ratify([WriteRequest(str(st.path_of(d)), tend, he)], OWNER, dry_run=True)
    assert any(v.startswith("ratify.not-a-signed-act") for v in dry["verdicts"][d])


def test_d6_display_pin(hz: Harness) -> None:
    st, signer = hz.st, hz.signer
    d = hz.draft("pin-hold")
    st.write_set(d, ['hold.kind="blocked"', "hold.on.owner=true"], PLANNER)
    st.ratify([d], OWNER)
    st.write_set(d, ['status="draft"'], PLANNER)
    r = st.write_set(d, ["hold="], PLANNER)
    assert r.entry["act"] == "released" and "sig" not in r.entry
    dry = st.ratify([d], OWNER, dry_run=True)
    since = dry["display"][0][3]
    assert since["tending"] == {"hold": [{"kind": "blocked", "on": {"owner": True}}, None]}, since
    assert [x[1] for x in since["entries_since"]] == ["demoted", "released"]
    st.ratify([d], OWNER)
    assert signer.shown[-1][0][3]["tending"]["hold"][0]["kind"] == "blocked"
    e = hz.draft("pin-hold-2")
    st.ratify([e], OWNER)
    st.write_set(e, ['hold.kind="blocked"', "hold.on.owner=true"], PLANNER)
    st.write_set(e, ['status="draft"'], PLANNER)
    st.write_set(e, ["hold="], PLANNER)
    since = st.ratify([e], OWNER, dry_run=True)["display"][0][3]
    assert since["tending"] == {}
    assert [x[1] for x in since["entries_since"]] == ["held", "demoted", "released"]


def test_d6_retraction_and_owner_close(hz: Harness) -> None:
    st = hz.st
    f = hz.draft("retract")
    st.ratify([f], OWNER)
    doc, head = st.show(f)
    cl = Document(copy.deepcopy(doc.head), copy.deepcopy(doc.sections))
    cl.head["closures"] = [
        {
            "id": "c1",
            "kind": "human",
            "outcome": {"deviated": {"description": "x"}},
            "verdicts": {"S1": "pass", "S2": "fail"},
            "evidence": [],
            "retracted": False,
        }
    ]
    cl.head["status"] = "closed"
    st.write(path_of(st, f), cl, head, None, PLANNER)
    doc, head = st.show(f)
    rt = Document(copy.deepcopy(doc.head), copy.deepcopy(doc.sections))
    rt.head["closures"][0]["retracted"] = True
    rt.head["status"] = "ratified"
    r = st.write(path_of(st, f), rt, head, None, PLANNER)
    assert r.entry["act"] == "retracted" and "sig" not in r.entry and r.entry["fields"] == ["closures", "status"]
    assert st.check(f)["integrity"] == []
    # after the closure LANDED (the sidecar names it — injected here; `land` is v1b), the same diff needs the owner
    g = hz.draft("retract-landed")
    st.ratify([g], OWNER)
    doc, head = st.show(g)
    cl = Document(copy.deepcopy(doc.head), copy.deepcopy(doc.sections))
    cl.head["closures"] = [
        {
            "id": "c1",
            "kind": "human",
            "outcome": "met",
            "verdicts": {"S1": "pass", "S2": "pass"},
            "evidence": [],
            "retracted": False,
        }
    ]
    cl.head["status"] = "closed"
    st.write(path_of(st, g), cl, head, None, PLANNER)
    landed = st.show(g)[0].history[-1]  # the sidecar's head AT the closed entry: landed (C6, one integer compare)
    st.state = {
        "cards": {
            f"{g:04d}": {
                "history_head": {"seq": landed["seq"], "h": landed["h"]},
                "closures": [
                    {"closure_id": "c1", "verified_against": doc.history[-1]["build"], "verified": True, "at": st.now()}
                ],
            }
        }
    }
    assert st.projections()[g].render() == "closed"
    doc, head = st.show(g)
    rt = Document(copy.deepcopy(doc.head), copy.deepcopy(doc.sections))
    rt.head["closures"][0]["retracted"] = True
    rt.head["status"] = "ratified"
    refuses("write.requires-owner", lambda: st.write(path_of(st, g), rt, head, None, PLANNER))
    st.state = {}
    h = hz.draft("owner-close")
    st.ratify([h], OWNER)
    doc, head = st.show(h)
    cl = Document(copy.deepcopy(doc.head), copy.deepcopy(doc.sections))
    closure = {
        "id": "c1",
        "kind": "human",
        "outcome": "met",
        "verdicts": {"S1": "pass", "S2": "pass"},
        "evidence": [],
        "retracted": False,
    }
    cl.head["closures"] = [closure]
    cl.head["status"] = "closed"
    r = st.write(path_of(st, h), cl, head, None, OWNER)
    assert r.entry["act"] == "closed" and "sig" in r.entry and r.entry["ref"] == canon.closure_ref(closure)
    assert derive.needs_signature(doc.head, cl.head, ["closures", "status"], None) is None
    assert st.check(h)["integrity"] == []
    assert st.projections()[h].render() == "closed (unverified)"


def test_d6_questions_and_origin(hz: Harness) -> None:
    st = hz.st
    i = hz.draft("signed-q", questions=[{"id": "Q1", "text": "which runner?"}])
    dry = st.ratify([i], OWNER, dry_run=True)
    assert dry["verdicts"][i] == [] and dry["ready"][i] is False
    st.ratify([i], OWNER)
    assert tuple(g.render() for g in st.projections()[i].guards) == ("has-questions",)
    refuses("questions.dropped-unanswered", lambda: st.write_set(i, ["questions=[]"], OWNER))
    refuses("validate.failed", lambda: hz.draft("bad-source", source="run"))
    refuses(
        "inbox.source",
        lambda: st.write(
            "suggestions.jsonl",
            {
                "type": "intake",
                "source": "suggestion",
                "kind": "docs",
                "title": "t",
                "body": "b",
                "refs": [],
                "from": {},
            },
            None,
            None,
            PLANNER,
        ),
    )


def test_d6_nfc_declaration(hz: Harness) -> None:
    st = hz.st
    nfd, nfc = unicodedata.normalize("NFD", "é"), unicodedata.normalize("NFC", "é")
    tree = copy.deepcopy(st.config_tree)
    tree["extensions"] = {nfd: {"type": "int", "class": "gated"}}
    st.write("config.toml", tree, {"seq": st.policy[-1]["seq"], "h": st.policy[-1]["h"]}, None, OWNER)
    assert st.gated_x() == frozenset({nfc})
    ha, hb = base_head(), base_head()
    ha["x"] = {nfc: 1}
    hb["x"] = {nfd: 1}
    assert canon.build_hash(ha, BASE_SCOPE, st.gated_x()) == canon.build_hash(hb, BASE_SCOPE, st.gated_x())
    assert canon.build_hash(ha, BASE_SCOPE, st.gated_x()) != canon.build_hash(base_head(), BASE_SCOPE, st.gated_x())
    bad = copy.deepcopy(st.config_tree)
    bad["extensions"] = {nfd: {"type": "int", "class": "gated"}, nfc: {"type": "int", "class": "tending"}}
    r = refuses(
        "validate.failed",
        lambda: st.write("config.toml", bad, {"seq": st.policy[-1]["seq"], "h": st.policy[-1]["h"]}, None, OWNER),
    )
    assert "ext-schema.key-collision" in cells(r)


def test_d6_binding(hz: Harness) -> None:
    st = hz.st
    b = next(e for e in st.policy if e["act"] == "binding")
    assert b["fields"] == [] and set(b["ref"]) == {"key_fpr", "grant", "tenant", "from"} and "until" not in b["ref"]
    assert chain.verify_sig(b["sig"], hz.st.realm_principal.lower(), b["h"], {hz.realm.key_fpr: hz.realm.key.public})
    assert derive.recompute_table(st.config_tree, st.config_tree, [], b["ref"], is_policy=True) == ("binding", [])
    _tree, hist, _ = parse_config(st.raw["config.toml"].decode(), CONFIG_ORDERS)
    assert next(e for e in hist if e["act"] == "binding")["ref"] == b["ref"]
    # revocation in a fresh store: a later binding carrying `until`; an entry signed after it is unverified
    hz2 = fresh("t2")
    st2 = hz2.st
    cid = hz2.draft("revoked")
    r = st2.write_set(cid, ['status="ratified"'], OWNER)
    assert st2.verify_entry(r.entry)
    tree = copy.deepcopy(st2.config_tree)
    tree["ratification"].pop("pin")
    st2.write("config.toml", tree, {"seq": st2.policy[-1]["seq"], "h": st2.policy[-1]["h"]}, None, OWNER)
    st2.bind(hz2.realm, hz2.signer.key_fpr, "owner", "2026-01-01T00:00:00Z", st2.now())
    cid2 = hz2.draft("after-revocation")
    r2 = st2.write_set(cid2, ['status="ratified"'], OWNER)
    assert not st2.verify_entry(r2.entry) and "unverified" in st2.check(cid2)["integrity"]


def test_d6_merge_observed_fail_closed(hz: Harness) -> None:
    """X2's observation half: the batch PR's merge appears in the walk; dispatch is fail-closed until the land
    (the land itself is v1b)."""
    st = hz.st
    main = st.repo.head
    assert main is not None
    branch = st.repo.commit(
        {"src/feature.py": b"print('built')\n"}, "builder", st.now(), "batch b2: code only", parents=[main]
    )
    st.repo.head = main  # type: ignore[misc]
    merge = st.repo.commit(
        {"src/feature.py": b"print('built')\n"}, "forge", st.now(), "merge batch b2", parents=[main, branch]
    )
    assert st.merges_pending() == [merge]
    refuses("dispatch.pending-land", lambda: st.dispatch(IDS["c3"]))


def test_d6_gate_refusals(hz: Harness) -> None:
    st = hz.st

    def hand_commit(cid: int, mutate: Any, act: str, fields: list[str]) -> Document:
        p = str(st.path_of(cid))
        doc = parse_markdown(st.raw[p].decode(), CARD)
        mutate(doc)
        fake = {
            "seq": doc.history[-1]["seq"] + 1,
            "at": st.now(),
            "by": PLANNER.principal,
            "act": act,
            "fields": fields,
            "build": doc.history[-1]["build"],
        }
        fake["h"] = chain.link(doc.history[-1]["h"], fake)
        doc.history.append(fake)
        st.repo.commit({p: emit_markdown(doc, CARD).encode()}, PLANNER.principal, str(fake["at"]), "outside the store")
        return doc

    def gate(cid: int) -> None:
        labels = st.check(cid)["integrity"]
        assert set(labels) <= {"tampered", "unjournaled"} and "tampered" in labels, labels

    a = hz.draft("gate-updates")
    st.ratify([a], OWNER)
    before = st.docs[str(st.path_of(a))]
    doc = hand_commit(a, lambda d: d.sections["Updates"][0].update(body="rewritten"), "noted", ["updates"])
    refuses("log.rewritten", lambda: derive.derive(before, doc, None))
    gate(a)
    b = hz.draft("gate-closure")
    st.ratify([b], OWNER)
    d0, h0 = st.show(b)
    cl = Document(copy.deepcopy(d0.head), copy.deepcopy(d0.sections))
    cl.head["closures"] = [
        {
            "id": "c1",
            "kind": "human",
            "outcome": {"deviated": {"description": "x"}},
            "verdicts": {"S1": "pass", "S2": "fail"},
            "evidence": [],
            "retracted": False,
        }
    ]
    cl.head["status"] = "closed"
    st.write(path_of(st, b), cl, h0, None, PLANNER)
    before = st.docs[str(st.path_of(b))]
    doc = hand_commit(
        b,
        lambda d: d.head["closures"][0]["outcome"].__setitem__("deviated", {"description": "edited"}),
        "amended",
        ["closures"],
    )
    refuses("claims.rewritten", lambda: derive.derive(before, doc, None))
    gate(b)
    c = hz.draft("gate-question", questions=[{"id": "Q1", "text": "?"}])
    st.ratify([c], OWNER)
    before = st.docs[str(st.path_of(c))]
    doc = hand_commit(c, lambda d: d.head.__setitem__("questions", []), "amended", ["questions"])
    refuses("questions.dropped-unanswered", lambda: derive.derive(before, doc, None))
    gate(c)
    d = hz.draft("gate-deleted")
    st.ratify([d], OWNER)
    st.repo.commit({str(st.path_of(d)): None}, "someone", st.now(), "rm")
    refuses("write.deletion", lambda: derive.derive(st.docs[str(st.path_of(d))], None, None))
    gate(d)
    e = hz.draft("gate-same-day")
    st.write_set(e, ["updates+=today|first"], PLANNER)
    de, he = st.show(e)
    am = Document(copy.deepcopy(de.head), copy.deepcopy(de.sections))
    ups = am.sections["Updates"]
    assert isinstance(ups, list)
    ups[-1]["body"] = "amended same day"
    refuses("log.rewritten", lambda: st.write(path_of(st, e), am, he, None, PLANNER))


def test_every_act_reachable(hz: Harness) -> None:
    missing = [a for a in derive.ACTS if a not in ACTS_HIT]
    assert not missing, missing
    assert all(v.split()[0] in ("write", "ratify", "repair", "init", "realm") for v in ACTS_HIT.values()), ACTS_HIT
    # the sidecar and the board are lander-only writes
    refuses("write.grant", lambda: hz.st.write("state.json", {}, None, None, OWNER))
    refuses("write.grant", lambda: hz.st.write("state.json", {}, None, None, LANDER))  # the lander calls `land`
    assert json.dumps(hz.st.show("Queue").inbox_counts) is not None
