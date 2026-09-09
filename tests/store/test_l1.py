"""L1 (2026-09-09) — `land`: the sidecar lands in one transaction under the lander's grant.

Every test names the property the record pins and asserts its positive discriminator: the bytes on the file, the
journal's seq, the commit's parent, the projection's label — never "nothing came back". The r6-d6 prototype's
`s_land_and_events` checks are carried here whole, against the real store (the plan's oracle for WP5).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from isidium.store.core import events as events_mod
from isidium.store.core import telemetry
from isidium.store.core.grammar import Document, parse_jsonl
from isidium.store.core.refusal import Refusal
from isidium.store.server.api import Api
from isidium.store.server.gitrepo import GitCli
from isidium.store.server.store import NewCard, Store

from .conftest import (
    BASE_SCOPE,
    LANDER,
    OWNER,
    PLANNER,
    Harness,
    Telemetry,
    base_head,
    fresh,
    store_on_disk,
    tenant_checkout,
)

ROOT = "docs/work/"


def refuses(rule: str, fn: Any) -> Refusal:
    with pytest.raises(Refusal) as ei:
        fn()
    assert ei.value.rule == rule, str(ei.value)
    return ei.value


def ratified(hz: Harness, slug: str) -> int:
    cid = hz.draft(slug)
    hz.st.ratify([cid], OWNER)
    return cid


def build_of(st: Store, cid: int) -> str:
    p = st.path_of(cid)
    assert p is not None
    return str(st.docs[p].history[-1]["build"])


def report(st: Store, a: int, b: int, c: int) -> dict[str, Any]:
    """The prototype's report, on real cards: a closes, b fails on budget, c asks a question; one suggestion."""
    return {
        "run_id": "r-1",
        "events": [
            {"kind": "dispatched", "card": a, "run_id": "r-1"},
            {
                "kind": "complete",
                "card": a,
                "run_id": "r-1",
                "batch": "b1",
                "build_hash": build_of(st, a),
                "cost_micro": 1200,
                "duration_ms": 5000,
            },
            {
                "kind": "closed",
                "card": a,
                "closure_id": "c1",
                "build_hash": build_of(st, a),
                "verdicts": {"S1": "pass", "S2": "pass"},
            },
            {"kind": "failed", "card": b, "class": "budget"},
            {"kind": "question", "card": c, "text": "which runner?"},
        ],
        "suggestions": [
            {
                "kind": "debt",
                "title": "split the validator",
                "body": "validate_profile is 300 lines",
                "refs": ["client/cards/validator.py"],
            }
        ],
    }


# ---- the door ---------------------------------------------------------------------------------------------------------


def test_the_door_is_the_landers_alone() -> None:
    """T-A10 condition 2: the grant refuses, not a hasher after the fact — the owner and the planner are `write.grant`
    at the matrix before any event is read; the lander passes the same door."""
    hz = fresh()
    a, b, c = ratified(hz, "a"), ratified(hz, "b"), ratified(hz, "c")
    rep = report(hz.st, a, b, c)
    refuses("write.grant", lambda: hz.st.land(rep, OWNER))
    refuses("write.grant", lambda: hz.st.land(rep, PLANNER))
    assert hz.st.events == [] and hz.st.state == {}, "a refused land moved the store"
    r = hz.st.land(rep, LANDER)
    assert r["events"] == ["e1", "e2", "e3", "e4", "e5"] and r["landed"] is True and r["empty"] is False


# ---- the prototype's checks, on the real store --------------------------------------------------------------------------


def test_the_land_folds_the_events_and_lands_everything_in_one_row_and_one_commit() -> None:
    """r6-d6 `s_land_and_events`, carried whole: five events appended and numbered; `execution` folded per card;
    `history_head` is each card's own last `h`; `journal_head` is the row before the land's; the intake carries
    `source = "run"` and `from.run`. And the transaction shape the prototype did not have: one journal row, one
    commit whose parent is the head before, one push."""
    hz = fresh()
    st = hz.st
    a, b, c = ratified(hz, "a"), ratified(hz, "b"), ratified(hz, "c")
    head_before = st.repo.head
    assert head_before is not None
    jseq_before, jh_before = st.journal.head
    pushed_before = st.repo.pushed  # type: ignore[attr-defined]
    r = st.land(report(st, a, b, c), LANDER)
    # the row and the commit
    assert r["journal_seq"] == jseq_before + 1, "the land is one row"
    assert st.repo.parents(r["commit"]) == [head_before] and st.repo.head == r["commit"], "the land is one commit"
    assert st.repo.pushed == pushed_before + 1, "the land is one push"  # type: ignore[attr-defined]
    landed = st.repo.touched(r["commit"])
    assert set(landed) == {st.rp(p) for p in ("state.json", "state/history.jsonl", "suggestions.jsonl", "BOARD.md")}
    # the events file
    lines = parse_jsonl(st.raw["state/history.jsonl"].decode("utf-8"))
    assert [e["id"] for e in lines] == ["e1", "e2", "e3", "e4", "e5"] and st.events == lines
    assert lines[3]["class"] == "budget" and all(e["at"] for e in lines)
    # the fold
    s = json.loads(st.raw["state.json"].decode("utf-8"))
    assert s == st.state and s["schema"] == 1 and s["ledger_cursor"] == head_before and s["batches"] == {}
    assert s["landed_at"] == st.repo.commit_time(head_before)
    assert s["cards"][f"{a:04d}"]["execution"] == "closed" and s["cards"][f"{b:04d}"]["execution"] == "failed(budget)"
    assert s["cards"][f"{c:04d}"]["execution"] is None, "a question is not an execution state"
    for cid in (a, b, c):
        p = st.path_of(cid)
        assert p is not None
        assert s["cards"][f"{cid:04d}"]["history_head"] == {
            "seq": st.docs[p].history[-1]["seq"],
            "h": st.docs[p].history[-1]["h"],
        }
    assert s["journal_head"] == {"seq": jseq_before, "h": jh_before}, "a row cannot carry its own hash"
    closure = s["cards"][f"{a:04d}"]["closures"][0]
    assert (
        closure["kind"] == "factory" and closure["verified"] is True and closure["verified_against"] == build_of(st, a)
    )
    assert s["cards"][f"{a:04d}"]["runs"][0]["cost_micro"] == 1200
    # the intake, in the same commit
    rec = st.inbox[-1]
    assert rec["type"] == "intake" and rec["source"] == "run" and rec["from"] == {"run": "r-1"}
    assert rec["id"] == "s1" and rec["by"] == LANDER.principal and r["intake"] == ["s1"] and r["overflow"] == 0
    assert st.raw["suggestions.jsonl"].endswith(json.dumps(rec, sort_keys=True, separators=(",", ":")).encode() + b"\n")
    # the bytes are the fold's canonical form
    assert st.raw["state.json"] == (json.dumps(s, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def test_the_union_is_closed_and_a_refused_report_lands_nothing() -> None:
    """`event.kind` for a kind outside the union (and for the two batch kinds the schema cannot carry a card for);
    `event.shape` naming the member for a kind missing what it carries; nothing journaled by either."""
    hz = fresh()
    a = ratified(hz, "a")
    seq_before = hz.st.journal.head[0]
    r = refuses("event.kind", lambda: hz.st.land({"run_id": "r", "events": [{"kind": "exploded", "card": a}]}, LANDER))
    assert r.path == "exploded"
    r = refuses("event.kind", lambda: hz.st.land({"run_id": "r", "events": [{"kind": "merged", "card": a}]}, LANDER))
    assert "batch" in r.detail
    r = refuses("event.shape", lambda: hz.st.land({"run_id": "r", "events": [{"kind": "failed", "card": a}]}, LANDER))
    assert r.path == "failed.class"
    r = refuses("event.shape", lambda: hz.st.land({"run_id": "r", "events": [{"kind": "question", "card": 0}]}, LANDER))
    assert r.path == "question.card"
    refuses(
        "event.shape", lambda: hz.st.land({"run_id": "r", "events": [{"kind": "closed", "card": a, "x": 1}]}, LANDER)
    )
    assert hz.st.journal.head[0] == seq_before and hz.st.events == []


def test_landing_the_same_cursor_again_is_an_empty_diff() -> None:
    """03 §1.4 (G11): nothing new at the same cursor folds to the same bytes — no row, no commit, `empty = true`."""
    hz = fresh()
    st = hz.st
    a, b, c = ratified(hz, "a"), ratified(hz, "b"), ratified(hz, "c")
    first = st.land(report(st, a, b, c), LANDER)
    bytes_before = dict(st.raw)
    again = st.land({"run_id": "r-2", "events": [], "suggestions": []}, LANDER)
    assert again["empty"] is True and again["journal_seq"] is None and again["commit"] == first["commit"]
    assert st.journal.head[0] == first["journal_seq"] and st.raw == bytes_before
    assert again["cursor"] == first["cursor"], "the cursor did not move: nothing merged since"


def test_the_cursor_is_the_pending_merge_and_the_land_opens_dispatch() -> None:
    """X2's three pins, closed: the batch PR's merge is `ledger_cursor`; after the land `merges_pending()` is empty,
    `dispatch` opens, and the queue's "merged, not landed" reads 0."""
    hz = fresh()
    st = hz.st
    a = ratified(hz, "a")
    st.land({"run_id": "r-0", "events": [{"kind": "dispatched", "card": a, "run_id": "r-0"}]}, LANDER)
    main = st.repo.head
    assert main is not None
    branch = st.repo.commit({"src/f.py": b"print('built')\n"}, "builder", st.now(), "batch b1: code", parents=[main])
    st.repo.head = main  # type: ignore[misc]
    merge = st.repo.commit({"src/f.py": b"print('built')\n"}, "forge", st.now(), "merge b1", parents=[main, branch])
    assert st.merges_pending() == [merge]
    refuses("dispatch.pending-land", lambda: st.dispatch(a))
    assert st.show("Queue").merged_not_landed == 1
    r = st.land(
        {"run_id": "r-1", "events": [{"kind": "closed", "card": a, "closure_id": "c1", "build_hash": build_of(st, a)}]},
        LANDER,
    )
    assert r["cursor"] == merge and st.state["ledger_cursor"] == merge
    assert st.state["landed_at"] == st.repo.commit_time(merge) and r["landed_at"] == st.state["landed_at"]
    assert st.merges_pending() == [] and st.dispatch(a) == {"dispatched": a}
    assert st.show("Queue").merged_not_landed == 0
    assert st.repo.parents(r["commit"]) == [merge], "the land is the store's own commit on the merged tip"


def test_a_hand_edited_sidecar_is_overwritten_by_the_fold() -> None:
    """03 §6: the lander overwrites, never merges — the fold reads the events, not the file it replaces."""
    hz = fresh()
    st = hz.st
    a = ratified(hz, "a")
    st.land({"run_id": "r-0", "events": [{"kind": "dispatched", "card": a, "run_id": "r-0"}]}, LANDER)
    st.raw["state.json"] = b'{"schema": 1, "cards": {"9999": {"execution": "closed"}}, "planted": true}\n'
    st.state = json.loads(st.raw["state.json"])
    r = st.land({"run_id": "r-1", "events": [{"kind": "parked", "card": a, "run_id": "r-1"}]}, LANDER)
    s = json.loads(st.raw["state.json"].decode("utf-8"))
    assert "planted" not in s and "9999" not in s["cards"] and s["cards"][f"{a:04d}"]["execution"] == "parked"
    assert r["empty"] is False


def test_the_board_joins_the_land_under_board_commit_and_stays_out_without() -> None:
    """03 §1.16: rendered by the store at land and committed when `board.commit = true` (W4); the landed board shows
    the landed labels. With the key false the land carries no board and the manifest row is never consulted."""
    hz = fresh()
    st = hz.st
    a, b, c = ratified(hz, "a"), ratified(hz, "b"), ratified(hz, "c")
    r = st.land(report(st, a, b, c), LANDER)
    assert st.rp("BOARD.md") in st.repo.touched(r["commit"])
    board = st.raw["BOARD.md"].decode("utf-8")
    assert f"**{a}**" in board and "closed" in board and "failed(budget)" in board, board
    assert board == st.show("Board"), "the landed board is what `show Board` renders over the landed state"
    # the same store with the key off: the next land carries no board
    tree = json.loads(json.dumps(st.config_tree))
    tree["board"] = {"commit": False}
    st.write("config.toml", tree, {"seq": st.policy[-1]["seq"], "h": st.policy[-1]["h"]}, None, OWNER)
    r2 = st.land({"run_id": "r-2", "events": [{"kind": "reverted", "card": a, "run_id": "r-1"}]}, LANDER)
    assert st.rp("BOARD.md") not in st.repo.touched(r2["commit"]) and r2["empty"] is False


def test_the_projection_reads_the_landed_state() -> None:
    """1.5 rows 7 and 9 over the sidecar `land` wrote: a verified factory closure at the build hash is `closed`; a
    budget failure is the execution row with its class; a card with no events is where it was."""
    hz = fresh()
    st = hz.st
    a, b, c = ratified(hz, "a"), ratified(hz, "b"), ratified(hz, "c")
    before = {cid: st.projection_of(cid).label.render() for cid in (a, b, c)}
    st.land(report(st, a, b, c), LANDER)
    after = {cid: st.projection_of(cid).label for cid in (a, b, c)}
    assert after[a].row == "closed" and after[a].modifier is None, after[a]
    assert after[b].row == "execution" and after[b].execution == "failed" and after[b].failure == "budget"
    assert after[c].render() == before[c]


def test_the_suggestions_are_capped_and_the_rest_counted() -> None:
    """`inbox.max_per_run` bounds the intake (03a: the anti-stash rule); the count above it is `overflow`, and the
    records that land are chained in one pass — consecutive ids, each `h` linking the one before."""
    hz = fresh()
    st = hz.st
    a = ratified(hz, "a")
    sugg = [{"kind": "debt", "title": f"t{i}", "body": "b", "refs": []} for i in range(12)]
    r = st.land(
        {"run_id": "r-1", "events": [{"kind": "dispatched", "card": a, "run_id": "r-1"}], "suggestions": sugg}, LANDER
    )
    assert r["intake"] == [f"s{i}" for i in range(1, 11)] and r["overflow"] == 2
    recs = parse_jsonl(st.raw["suggestions.jsonl"].decode("utf-8"))
    assert [x["seq"] for x in recs] == list(range(1, 11)) and len({x["h"] for x in recs}) == 10
    assert st.inbox == recs
    # a suggestion the inbox door refuses refuses the whole land, before any row
    seq = st.journal.head[0]
    bad = [{"kind": "not-a-kind", "title": "t", "body": "b", "refs": []}]
    with pytest.raises(Refusal) as ei:
        st.land({"run_id": "r-2", "events": [], "suggestions": bad}, LANDER)
    assert ei.value.rule in ("validate.failed", "record.enum"), str(ei.value)
    assert st.journal.head[0] == seq


# ---- the wire: the api, the surface, the CLI ----------------------------------------------------------------------------


def test_the_api_carries_land_and_not_yet_names_accept_alone() -> None:
    hz = fresh()
    api = Api(hz.st)
    a = ratified(hz, "a")
    assert "land" in Api.CALLS and Api.LATER == {"accept": "the acceptance runners"}
    refuses("api.not-yet", lambda: api.call("accept", LANDER, {}))
    r = api.call("land", LANDER, {"run_id": "r-1", "events": [{"kind": "dispatched", "card": a, "run_id": "r-1"}]})
    assert r["events"] == ["e1"] and r["landed"] is True
    refuses("service.arguments", lambda: api.call("land", LANDER, {"run_id": "r", "events": "not a list"}))
    refuses("service.arguments", lambda: api.call("land", LANDER, {"events": []}))


def test_land_is_not_on_the_planners_tool_surface() -> None:
    """05 §1: the lander is a credential, not a prompt — the generated tool schemas do not offer `land`."""
    from isidium.store.registry import codegen

    assert "land" not in codegen.tool_schemas()


def test_the_cli_verb_reads_the_report_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`isidium land --report <file>`: the file's object is the call's arguments; a file that is not one is refused
    at the terminal (`land.report`, exit 2) before any channel opens."""
    from typer.testing import CliRunner

    from isidium.store.client import cli as cli_mod

    sent: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(cli_mod, "_run", lambda name, args, text=False: sent.append((name, dict(args))))
    f = tmp_path / "run.json"
    f.write_text(json.dumps({"run_id": "r-9", "events": [], "suggestions": []}), encoding="utf-8")
    res = CliRunner().invoke(cli_mod.app, ["land", "--report", str(f)])
    assert res.exit_code == 0, res.output
    assert sent == [("land", {"run_id": "r-9", "events": [], "suggestions": []})]
    f.write_text("[1, 2]", encoding="utf-8")
    res = CliRunner().invoke(cli_mod.app, ["land", "--report", str(f)])
    assert res.exit_code == 2 and "land.report" in res.output, res.output


# ---- the half-land, on real git -------------------------------------------------------------------------------------------


def test_a_half_land_is_journaled_and_replayed_by_the_next_land(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, otel: Telemetry
) -> None:
    """T-A10's failure protocol: a push that fails after the row leaves the act journaled (`landed = false`, the row
    pending, the counter up by one); the next `land` replays it first and pushes once more, and the origin then holds
    both lands with the chain intact."""
    tenant_checkout(tmp_path)
    st = store_on_disk(tmp_path / "tenant", tmp_path / "journal.sqlite", root=ROOT)
    st.init(OWNER, software_key_ack="ok for L1", root=ROOT)
    r0 = st.write(NewCard("half"), Document(base_head(0, "draft"), {"Scope": BASE_SCOPE}), None, None, PLANNER)
    assert r0.id is not None and isinstance(st.repo, GitCli)
    origin = tmp_path / "origin.git"
    hidden = origin.with_name("origin.hidden")
    original = GitCli.push

    def failing(self: GitCli) -> None:
        origin.rename(hidden)
        try:
            original(self)
        finally:
            hidden.rename(origin)

    monkeypatch.setattr(GitCli, "push", failing)
    unlanded_before = otel.count("isidium.store.write.unlanded", **{telemetry.RULE: "git.failed"})
    with telemetry.span(telemetry.CALL_SPAN, **{telemetry.ACTION: "land"}) as call:
        r1 = st.land({"run_id": "r-1", "events": [{"kind": "dispatched", "card": r0.id, "run_id": "r-1"}]}, LANDER)
    assert r1["landed"] is False and r1["empty"] is False
    assert call.attributes[telemetry.LANDED] is False and call.attributes[telemetry.LAND_EVENTS] == 1  # type: ignore[attr-defined]
    assert otel.count("isidium.store.write.unlanded", **{telemetry.RULE: "git.failed"}) == unlanded_before + 1
    assert sorted({s for s, _p, _d in st.journal.pending_rows()}) == [r1["journal_seq"]], "the row is pending"
    assert st.state["ledger_cursor"] == r1["cursor"], "memory holds the act"
    monkeypatch.setattr(GitCli, "push", original)
    r2 = st.land({"run_id": "r-2", "events": [{"kind": "parked", "card": r0.id, "run_id": "r-1"}]}, LANDER)
    assert r2["landed"] is True and st.journal.pending_rows() == []
    again = store_on_disk(tmp_path / "tenant", tmp_path / "journal2.sqlite", root=ROOT)
    assert [e["id"] for e in again.events] == ["e1", "e2"], "the origin holds both lands"
    assert again.state["cards"][f"{r0.id:04d}"]["execution"] == "parked"
    assert again.check(r0.id)["integrity"] == []


# ---- the fold on its own ----------------------------------------------------------------------------------------------------


def test_the_fold_is_pure_and_idempotent() -> None:
    evs = [
        {"id": "e1", "at": "2026-09-09T00:00:00Z", "card": 7, "kind": "dispatched", "run_id": "r"},
        {
            "id": "e2",
            "at": "2026-09-09T00:00:07Z",
            "card": 7,
            "kind": "closed",
            "closure_id": "c1",
            "build_hash": "sha256:x",
        },
        {"id": "e3", "at": "2026-09-09T00:00:14Z", "card": 8, "kind": "failed", "class": "timeout"},
    ]
    heads = {"0007": {"seq": 2, "h": "sha256:h7"}, "0009": {"seq": 1, "h": "sha256:h9"}}
    a = events_mod.fold(evs, "abc", "2026-09-09T00:00:00Z", {"seq": 3, "h": "sha256:j"}, heads)
    b = events_mod.fold([dict(e) for e in evs], "abc", "2026-09-09T00:00:00Z", {"seq": 3, "h": "sha256:j"}, heads)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert list(a["cards"]) == ["0007", "0008", "0009"], "sorted, zero-padded card keys"
    assert a["cards"]["0009"] == {**events_mod._new_card(), "history_head": heads["0009"]}
    assert a["cards"]["0008"]["execution"] == "failed(timeout)" and a["cards"]["0008"]["history_head"] is None
    assert "tenant" not in a and a["batches"] == {}
