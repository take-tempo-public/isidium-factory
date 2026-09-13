"""V5a (2026-09-12) — the run's end, and the store told: every run reaches an outcome, and the ledger's report lands
once (Q-V18–Q-V23).

The properties, and what each test discriminates:

- **A run that succeeds ends** — the defect V5a exists for: a good run left `ended_at` empty and held the WIP cap for
  ever. The positive discriminator is `in_flight()` empty *and* the row's outcome, not either alone.
- **The outcome set is closed and a run ends once**: an outcome outside it, or a second end, changes nothing.
- **The report is sent once**: nothing past the watermark means no call at all, and a refused land's events go next
  time — which is what distinguishes a watermark advanced after the answer from one advanced before it.
- **The store hears every end**: a pick's `dispatched` (Q-V19), a phase's failure, a close's failure class (Q-V22) —
  each asserted on the store's own sidecar, never on what the factory believes it sent.
- **Close refuses what it cannot answer yet and fails what it can**, each branch with the acceptance double's
  `seen` proving how far it got; green verifies the human's closure when there is one — the label leaves `closed
  (unverified)` — and writes the factory's own when there is not.

The close tests run over a real store and a real checkout: the run's commit is made in a worktree by the run's
identity, merged into the checkout with `--no-ff`, and the merge is what the forge double answers. The forge and the
acceptance run are the two doubles — the first because there is no GitHub here, the second because the scenario
runners are L3's and the property under test is what close does with their answer.
"""

from __future__ import annotations

import dataclasses
import os
import sqlite3
import subprocess
from collections.abc import Iterator, Mapping
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from isidium.factory import checkout as checkout_mod
from isidium.factory import cli as cli_mod
from isidium.factory import close as close_mod
from isidium.factory import context as context_mod
from isidium.factory import dispatch as dispatch_mod
from isidium.factory import lander
from isidium.factory import ledger as ledger_mod
from isidium.factory import runner as runner_mod
from isidium.factory.context import TenantContext
from isidium.factory.forge import CheckRun, Checks, MergeableState, MergeState
from isidium.factory.ledger import Ledger, NewRun
from isidium.store.client.config import ClientConfig
from isidium.store.core.grammar import Document
from isidium.store.core.refusal import Refusal
from isidium.store.server.api import Api
from isidium.store.server.store import NewCard, Store

from ..store.conftest import BASE_SCOPE, LANDER, OWNER, PLANNER, base_head, git, store_on_disk, tenant_checkout
from .test_v4a import Branch, Fake, _harness_result

ROOT = "docs/work/"
TENANT = "sartor"
URL = "https://github.com/acme/widgets.git"
LOGIN = "isdm-fac-lander[bot]"
NAME = "isdm-fac-lander"
EMAIL = "1+x@users.noreply.github.com"
EMPTY: dict[str, Any] = {"run_id": "r-0", "events": [], "suggestions": []}
AT = "2026-09-12T12:00:00Z"
MANIFEST = "sha256:" + "a" * 64


def refuses(rule: str, fn: Any) -> Refusal:
    with pytest.raises(Refusal) as ei:
        fn()
    assert ei.value.rule == rule, str(ei.value)
    return ei.value


# ------------------------------------------------------------------------------------------- the on-disk harness


@dataclass
class Disk:
    work: Path
    home: Path
    store: Store
    ctx: TenantContext
    picked: int  # dispatched by the pick test
    phased: int  # dispatched and failed by the runner test
    human: int  # closed by a human before its run closes
    factory: int  # closed by the factory alone
    refused: int  # every refusal and failure lands here

    def call(self, name: str, args: Any) -> Any:
        return Api(self.store).call(name, LANDER, args)


def _card(st: Store, slug: str) -> int:
    r = st.write(NewCard(slug), Document(base_head(0, "draft"), {"Scope": BASE_SCOPE}), None, None, PLANNER)
    assert r.id is not None
    return r.id


def _human_close(st: Store, cid: int) -> None:
    """What `accept --close` writes (L3), written the same way: the card's document with a human closure appended and
    `status = closed`, one `write` over the planner's channel."""
    api = Api(st)
    shown = api.call("show", PLANNER, {"target": "card", "id": cid})
    head = dict(shown["head"])
    head["closures"] = [
        {
            "id": "c1",
            "kind": "human",
            "outcome": "met",
            "verdicts": {"S1": "pass", "S2": "pass"},
            "evidence": ["sha256:" + "c" * 64],
            "retracted": False,
        }
    ]
    head["status"] = "closed"
    document: dict[str, Any] = {"head": head, "scope": shown["scope"]}
    if shown.get("updates"):
        document["updates"] = shown["updates"]
    api.call("write", PLANNER, {"card": cid, "document": document, "base": shown["cas"]})


@pytest.fixture(scope="module")
def disk(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Disk]:
    tmp = tmp_path_factory.mktemp("v5a")
    work = tenant_checkout(tmp)
    st = store_on_disk(work, tmp / "journal.sqlite", root=ROOT)
    st.init(OWNER, software_key_ack="ok for V5a", root=ROOT)
    ids = [_card(st, slug) for slug in ("picked", "phased", "human-closed", "factory-closed", "refused")]
    st.ratify(ids, OWNER)
    st.land(EMPTY, LANDER)
    _human_close(st, ids[2])
    bare = (tmp / "origin.git").as_posix()
    git(work, "remote", "set-url", "origin", URL)
    git(work, "config", f"url.{bare}.insteadOf", URL)
    home = tmp / "deploy"
    fd = home / TENANT / "factory"
    fd.mkdir(parents=True)
    (fd / "client.toml").write_text(ClientConfig(tenant=TENANT).render(), encoding="utf-8")
    (fd / "forge.toml").write_text(
        f'kind = "token"\nlogin = "{LOGIN}"\nname = "{NAME}"\nemail = "{EMAIL}"\ntoken = "forge.token"\n',
        encoding="utf-8",
    )
    (fd / "forge.token").write_text("ghp_test\n", encoding="utf-8")
    (fd / "tenant.toml").write_text(
        'allow_software_grade_until = 2999-01-01\nwip = 1\nadapter = "container"\n\n'
        '[payload]\nmax_bytes = 1000000\n\n[runner]\nimage = "isidium-runner:test"\n',
        encoding="utf-8",
    )
    mp = pytest.MonkeyPatch()
    mp.setenv("ISIDIUM_DEPLOY", str(home))
    ctx = context_mod.load(TENANT, work, base="main", root=ROOT)
    yield Disk(work, fd, st, ctx, *ids)
    mp.undo()


@pytest.fixture
def led(disk: Disk) -> Iterator[Ledger]:
    ledger = Ledger(disk.home / ledger_mod.LEDGER_FILE, TENANT)
    yield ledger
    ledger.close()


@pytest.fixture
def fresh(tmp_path: Path) -> Iterator[Ledger]:
    ledger = Ledger(tmp_path / ledger_mod.LEDGER_FILE, TENANT)
    yield ledger
    ledger.close()


def numbered(tmp_path: Path, first: int) -> Ledger:
    """A ledger of its own whose ids start at `first` — a pick's story branch is `story/<run-id>`, and the checkout
    already holds the module ledger's."""
    ledger = Ledger(tmp_path / ledger_mod.LEDGER_FILE, TENANT)
    ledger.db.execute("UPDATE meta SET value = ? WHERE key = 'next_run'", (str(first),))
    return ledger


def new_run(cid: int = 1) -> NewRun:
    return NewRun(
        card=cid,
        lane="standard",
        build_hash="sha256:" + "b" * 64,
        base_sha="c" * 40,
        adapter="container",
        dispatched_at=AT,
        payload_hash="sha256:" + "d" * 64,
        config_hash="sha256:" + "e" * 64,
        identity=LOGIN,
    )


def build_of(disk: Disk, cid: int) -> str:
    return str(disk.call("show", {"target": "card", "id": cid})["history"][-1]["build"])


def label_of(disk: Disk, cid: int) -> str:
    return disk.store.projection_of(cid).render()


def execution_of(disk: Disk, cid: int) -> Any:
    return disk.store.state["cards"].get(f"{cid:04d}", {}).get("execution")


# ------------------------------------------------------------------------------------------------- the doubles


GREEN = Checks(("green-bar",), (CheckRun("green-bar", "completed", "success"),))
RED = Checks(("green-bar",), (CheckRun("green-bar", "completed", "failure"),))
PENDING = Checks(("green-bar",), ())


@dataclass(frozen=True)
class Run:
    run_id: str
    head: str
    merge: str | None


@dataclass
class Forge:
    """The two reads close makes, answered and recorded."""

    head: str
    merge: str | None
    merged: bool = True
    gate: Checks = GREEN
    seen: list[tuple[str, Any]] = field(default_factory=list)

    def merge_state(self, number: int) -> MergeState:
        self.seen.append(("merge_state", number))
        return MergeState(self.head, True, MergeableState.CLEAN, self.merged, self.merge)

    def checks(self, sha: str) -> Checks:
        self.seen.append(("checks", sha))
        return self.gate


def forge_for(run: Run, **over: Any) -> Forge:
    return Forge(run.head, run.merge, **over)


@dataclass
class Acceptance:
    """`accept` without `--close`, answered: what close does with the verdicts is the property, not the runners."""

    passed: bool = True
    verdicts: tuple[tuple[str, str], ...] = (("S1", "pass"), ("S2", "pass"))
    seen: list[tuple[Path, str, int]] = field(default_factory=list)

    def __call__(self, call: Any, workdir: Path, root: str, card_id: int) -> Mapping[str, Any]:
        self.seen.append((workdir, root, card_id))
        return {
            "passed": self.passed,
            "manifest_hash": MANIFEST,
            "verdicts": [{"scenario_id": s, "verdict": v, "detail": ""} for s, v in self.verdicts],
        }


def a_run(
    disk: Disk,
    led: Ledger,
    cid: int,
    *,
    email: str = EMAIL,
    trailer: bool = True,
    merge: bool = True,
    build: str | None = None,
) -> Run:
    """A run as the line leaves one: dispatched at the checkout's head, its `dispatched` landed, one commit by the
    wrapper's identity in a worktree on its story branch, one `build` phase on the row — and, unless `merge` is
    false, its story branch merged into the checkout the way the forge's button merges it."""
    base = git(disk.work, "rev-parse", "HEAD").strip()
    run_id = led.dispatch(dataclasses.replace(new_run(cid), build_hash=build or build_of(disk, cid), base_sha=base))
    branch = f"story/{run_id}"
    git(disk.work, "branch", branch, base)
    tree = disk.home / "worktrees" / run_id
    checkout_mod.worktree(disk.work, branch, tree)
    try:
        (tree / "src").mkdir(exist_ok=True)
        (tree / "src" / f"{run_id}.txt").write_text(run_id + "\n", encoding="utf-8")
        git(tree, "add", "-A")
        message = f"builder: {run_id}\n\n" + (f"{runner_mod.TRAILER_RUN}: {run_id}\n" if trailer else "")
        who = {
            "GIT_AUTHOR_NAME": NAME,
            "GIT_AUTHOR_EMAIL": email,
            "GIT_COMMITTER_NAME": NAME,
            "GIT_COMMITTER_EMAIL": email,
        }
        subprocess.run(["git", "commit", "-q", "-m", message], cwd=tree, check=True, env={**os.environ, **who})
        head = git(tree, "rev-parse", "HEAD").strip()
    finally:
        checkout_mod.worktree_remove(disk.work, tree)
    led.advance(run_id, head, [f"src/{run_id}.txt"], "plan")
    led.phase(
        run_id,
        AT,
        {"phase": "build", "agent": "builder", "tokens": 10, "cost_micro": 300, "duration_ms": 2000, "outcome": "ok"},
    )
    assert lander.land_run(led, disk.call, run_id)["sent"] == 1
    if not merge:
        return Run(run_id, head, None)
    git(disk.work, "merge", "--no-ff", "-q", "-m", f"Merge {branch}", branch)
    return Run(run_id, head, git(disk.work, "rev-parse", "HEAD").strip())


def close_run(
    disk: Disk,
    led: Ledger,
    run: Run,
    forge: Forge | None = None,
    accept: Acceptance | None = None,
    *,
    pr: int | None = 7,
    call: Any = None,
) -> dict[str, Any]:
    return close_mod.close(
        disk.ctx,
        led,
        call or disk.call,
        forge or forge_for(run),
        run_id=run.run_id,
        pr=pr,
        accept=accept or Acceptance(),
    )


# ------------------------------------------------------------------------------------------------ the ledger's end


def test_a_run_that_succeeds_ends_and_frees_the_cap(fresh: Ledger) -> None:
    rid = fresh.dispatch(new_run())
    assert [r["run_id"] for r in fresh.in_flight()] == [rid]
    b = "sha256:" + "b" * 64
    fresh.end(
        rid,
        AT,
        "closed",
        store_events=(
            ("complete", {"run_id": rid, "build_hash": b, "cost_micro": 1, "duration_ms": 2}),
            ("closed", {"closure_id": f"f-{rid}", "build_hash": b}),
        ),
        detail={"phases": ["build"]},
    )
    row = fresh.run(rid)
    assert row is not None and row["ended_at"] == AT and row["outcome"] == "closed"
    assert fresh.in_flight() == []
    assert [e["kind"] for e in fresh.events_of(rid)] == ["dispatched", "complete", "closed", "ended"]
    assert [e.kind for e in fresh.report(rid).events] == ["dispatched", "complete", "closed"]


def test_an_outcome_outside_the_closed_set_is_refused_and_the_run_stays_in_flight(fresh: Ledger) -> None:
    rid = fresh.dispatch(new_run())
    refuses("ledger.outcome", lambda: fresh.end(rid, AT, "complete"))
    refuses("ledger.outcome", lambda: fresh.end(rid, AT, "failed:bored"))
    assert [r["run_id"] for r in fresh.in_flight()] == [rid] and len(fresh.events_of(rid)) == 1


def test_a_run_ends_once(fresh: Ledger) -> None:
    rid = fresh.dispatch(new_run())
    fresh.end(rid, AT, "failed:gate")
    refuses("ledger.ended", lambda: fresh.end(rid, AT, "closed"))
    row = fresh.run(rid)
    assert row is not None and row["outcome"] == "failed:gate"
    refuses("ledger.unknown-run", lambda: fresh.end("r-99", AT, "closed"))


def test_every_failure_writes_the_stores_failed_event_beside_the_ledgers(fresh: Ledger) -> None:
    a = fresh.dispatch(new_run())
    fresh.fail(a, AT, "environment", "a branch of that name exists")
    b = fresh.dispatch(new_run())
    fresh.finish(b, AT, "failed:infra")
    for rid, cls in ((a, "environment"), (b, "infra")):
        failed = [e for e in fresh.report(rid).events if e.kind == "failed"]
        assert [(e.class_, e.run_id) for e in failed] == [(cls, rid)]
    assert fresh.events_of(a)[-1]["kind"] == "interrupt", "the ledger's own detail stays the ledger's"


def test_the_watermark_sends_each_event_once_and_a_refused_land_sends_it_again(fresh: Ledger) -> None:
    sent: list[list[str]] = []

    def store(name: str, args: Any) -> Any:
        assert name == "land"
        sent.append([e["kind"] for e in args["events"]])
        return {"events": ["e1"], "landed": True}

    def refusing(name: str, args: Any) -> Any:
        raise Refusal("land.sidecar-unreadable", "state.json", "planted")

    rid = fresh.dispatch(new_run())
    assert lander.land_run(fresh, store, rid)["sent"] == 1
    assert lander.land_run(fresh, store, rid) == {"sent": 0} and sent == [["dispatched"]], "nothing new, no call"
    fresh.end(rid, AT, "failed:gate")
    out = lander.land_run(fresh, refusing, rid)
    assert out["refused"] == "land.sidecar-unreadable" and out["sent"] == 0
    assert lander.land_run(fresh, store, rid)["sent"] == 1 and sent[-1] == ["failed"], "the refused land's event, next"


def test_a_schema_1_ledger_gains_its_two_columns_at_open_and_keeps_its_rows(tmp_path: Path) -> None:
    path = tmp_path / ledger_mod.LEDGER_FILE
    old = ledger_mod._DDL[1].replace(",\n        pr INTEGER, landed_through INTEGER", "")
    assert old != ledger_mod._DDL[1], "the V3 table, as tenant #0's ledger holds it"
    with closing(sqlite3.connect(path)) as db:
        db.execute(ledger_mod._DDL[0])
        db.execute(old)
        db.executemany("INSERT INTO meta VALUES (?, ?)", [("schema", "1"), ("tenant", TENANT), ("next_run", "2")])
        db.execute(
            "INSERT INTO runs (run_id, card, outcome, lane, build_hash, base_sha, story_branch, adapter,"
            " dispatched_at, payload_hash, config_hash, context, score, refs_resolved, identity)"
            " VALUES ('r-1', 5, 'dispatched', 'standard', 'b', 'c', 'story/r-1', 'container', ?, 'p', 'h', '{}',"
            " '{}', '[]', ?)",
            (AT, LOGIN),
        )
        db.commit()
    ledger = Ledger(path, TENANT)
    try:
        row = ledger.run("r-1")
        assert row is not None and row["card"] == 5 and row["pr"] is None and row["landed_through"] is None
        assert ledger._meta("schema") == str(ledger_mod.SCHEMA) == "2"
        ledger.set_pr("r-1", 57)
        again = ledger.run("r-1")
        assert again is not None and again["pr"] == 57
    finally:
        ledger.close()


# --------------------------------------------------------------------------------------------- the store hears it


def test_a_pick_lands_its_dispatched_and_the_store_counts_the_run(disk: Disk, tmp_path: Path) -> None:
    ledger = numbered(tmp_path, 101)
    try:
        row = dispatch_mod.pick(disk.ctx, ledger, disk.call, Branch(disk.work), card=disk.picked)
        assert row["land"]["sent"] == 1 and row["landed_through"] == ledger.events_of(row["run_id"])[-1]["seq"]
        assert execution_of(disk, disk.picked) == "dispatched" and label_of(disk, disk.picked) == "dispatched"
        assert disk.picked not in {int(r["id"]) for r in disk.call("dispatch", {})["ready"]}, "not dispatchable twice"
    finally:
        ledger.close()


def test_a_phase_that_fails_lands_its_failure_on_the_store(disk: Disk, tmp_path: Path) -> None:
    ledger = numbered(tmp_path, 201)
    try:
        row = dispatch_mod.pick(disk.ctx, ledger, disk.call, Branch(disk.work), card=disk.phased)
        reg = disk.ctx.registration
        assert reg is not None
        broken = Fake(result=_harness_result(outcome="failed:infra"))
        out = runner_mod.run_phase(
            disk.ctx, reg, ledger, disk.call, run_id=str(row["run_id"]), factory=lambda h, r: broken
        )
        assert out["outcome"] == "failed:infra" and out["ended_at"]
        assert execution_of(disk, disk.phased) == "failed(infra)" and label_of(disk, disk.phased) == "failed(infra)"
    finally:
        ledger.close()


# ---------------------------------------------------------------------------------------- close: what it refuses


def test_close_refuses_a_pull_request_that_has_not_merged_and_the_run_stays_in_flight(disk: Disk, led: Ledger) -> None:
    run = a_run(disk, led, disk.refused)
    acc = Acceptance()
    # GitHub answers a merge_commit_sha for an open pull request too — its test merge — so `merged` is the fact.
    refuses("close.not-merged", lambda: close_run(disk, led, run, forge_for(run, merged=False), acc))
    row = led.run(run.run_id)
    assert row is not None and row["ended_at"] is None and acc.seen == []


def test_close_refuses_a_pull_request_that_is_not_the_runs(disk: Disk, led: Ledger) -> None:
    run = a_run(disk, led, disk.refused)
    refuses("close.pr-mismatch", lambda: close_run(disk, led, run, Forge("f" * 40, run.merge)))
    row = led.run(run.run_id)
    assert row is not None and row["ended_at"] is None and row["pr"] is None, "another run's pull request is not kept"


def test_close_refuses_a_dirty_checkout_and_one_that_does_not_hold_the_merge(disk: Disk, led: Ledger) -> None:
    run = a_run(disk, led, disk.refused)
    (disk.work / "README.md").write_text("changed under the close\n", encoding="utf-8")
    try:
        refuses("close.checkout", lambda: close_run(disk, led, run))
    finally:
        git(disk.work, "checkout", "--", "README.md")
    apart = a_run(disk, led, disk.refused, merge=False)
    acc = Acceptance()
    r = refuses("close.checkout", lambda: close_run(disk, led, apart, Forge(apart.head, apart.head), acc))
    assert "does not contain the merge commit" in r.detail and acc.seen == []
    assert all((led.run(x.run_id) or {}).get("ended_at") is None for x in (run, apart))


def test_close_refuses_while_the_gate_is_still_running(disk: Disk, led: Ledger) -> None:
    run = a_run(disk, led, disk.refused)
    acc = Acceptance()
    refuses("close.gate-pending", lambda: close_run(disk, led, run, forge_for(run, gate=PENDING), acc))
    row = led.run(run.run_id)
    assert row is not None and row["ended_at"] is None and acc.seen == []


def test_a_run_already_ended_is_refused_by_close_and_one_with_no_pr_is_refused_too(disk: Disk, led: Ledger) -> None:
    ended = a_run(disk, led, disk.refused)
    led.end(ended.run_id, AT, "failed:infra")
    refuses("close.ended", lambda: close_run(disk, led, ended))
    bare = a_run(disk, led, disk.refused)
    refuses("close.no-pr", lambda: close_run(disk, led, bare, pr=None))


# ------------------------------------------------------------------------------------------ close: what it fails


def test_a_card_that_changed_since_dispatch_fails_the_run_card_drift_and_the_store_hears_it(
    disk: Disk, led: Ledger
) -> None:
    run = a_run(disk, led, disk.refused, build="sha256:" + "0" * 64)
    acc = Acceptance()
    out = close_run(disk, led, run, accept=acc)
    assert out["outcome"] == "failed:card-drift" and out["ended_at"] and acc.seen == []
    assert out["land"]["sent"] == 1 and execution_of(disk, disk.refused) == "failed(card-drift)"


def test_a_commit_the_run_did_not_author_fails_the_run_identity(disk: Disk, led: Ledger) -> None:
    run = a_run(disk, led, disk.refused, email="someone@example")
    acc = Acceptance()
    out = close_run(disk, led, run, accept=acc)
    assert out["outcome"] == "failed:identity" and acc.seen == []
    [ended] = [e for e in led.events_of(run.run_id) if e["kind"] == "ended"]
    assert ended["data"]["commits"] == [run.head]
    trailerless = a_run(disk, led, disk.refused, trailer=False)
    assert close_run(disk, led, trailerless)["outcome"] == "failed:identity"
    assert execution_of(disk, disk.refused) == "failed(identity)"


def test_a_red_gate_fails_the_run_gate(disk: Disk, led: Ledger) -> None:
    run = a_run(disk, led, disk.refused)
    acc = Acceptance()
    forge = forge_for(run, gate=RED)
    out = close_run(disk, led, run, forge, acc)
    assert out["outcome"] == "failed:gate" and acc.seen == [] and ("checks", run.merge) in forge.seen
    assert execution_of(disk, disk.refused) == "failed(gate)"


def test_acceptance_that_is_not_all_pass_fails_the_run_and_so_does_none_at_all(disk: Disk, led: Ledger) -> None:
    run = a_run(disk, led, disk.refused)
    acc = Acceptance(passed=False, verdicts=(("S1", "pass"), ("S2", "fail")))
    out = close_run(disk, led, run, accept=acc)
    assert out["outcome"] == "failed:acceptance" and acc.seen == [(disk.work, ROOT, disk.refused)]
    assert execution_of(disk, disk.refused) == "failed(acceptance)"
    empty = a_run(disk, led, disk.refused)
    assert close_run(disk, led, empty, accept=Acceptance(verdicts=()))["outcome"] == "failed:acceptance"


def test_a_withdrawn_card_abandons_its_run_and_nothing_lands(disk: Disk, led: Ledger) -> None:
    run = a_run(disk, led, disk.refused)
    held = len(disk.store.events)

    def withdrawn(name: str, args: Any) -> Any:
        out = disk.call(name, args)
        if name == "show":
            out = {**out, "head": {**out["head"], "status": "withdrawn"}}
        return out

    forge, acc = forge_for(run), Acceptance()
    out = close_run(disk, led, run, forge, acc, call=withdrawn)
    assert out["outcome"] == "abandoned" and out["ended_at"] and out["land"]["sent"] == 0
    assert len(disk.store.events) == held and forge.seen == [] and acc.seen == []


# --------------------------------------------------------------------------------------------- close: green


def test_a_green_close_verifies_the_humans_closure_and_the_label_leaves_unverified(disk: Disk, led: Ledger) -> None:
    before = label_of(disk, disk.human)
    assert before.startswith("closed (") and before != "closed", before
    run = a_run(disk, led, disk.human)
    acc = Acceptance()
    out = close_run(disk, led, run, accept=acc)
    assert out["outcome"] == "closed" and out["pr"] == 7 and out["land"]["sent"] == 2
    assert run.run_id not in {r["run_id"] for r in led.in_flight()}
    assert label_of(disk, disk.human) == "closed"
    [closed] = [e for e in disk.store.events if e["kind"] == "closed" and int(e["card"]) == disk.human]
    assert closed["closure_kind"] == "human" and closed["closure_id"] == "c1" and closed["verified"] is True
    assert closed["evidence"] == [MANIFEST, run.merge] and closed["verdicts"] == {"S1": "pass", "S2": "pass"}


def test_a_green_close_with_no_human_closure_lands_the_factorys_own(disk: Disk, led: Ledger, otel: Any) -> None:
    run = a_run(disk, led, disk.factory)
    otel.clear()
    out = close_run(disk, led, run)
    assert out["outcome"] == "closed" and label_of(disk, disk.factory) == "closed"
    closure = disk.store.state["cards"][f"{disk.factory:04d}"]["closures"][-1]
    assert closure["closure_id"] == f"f-{run.run_id}" and closure["kind"] == "factory"
    assert closure["verified_against"] == build_of(disk, disk.factory)
    [complete] = [e for e in disk.store.events if e["kind"] == "complete" and int(e["card"]) == disk.factory]
    assert complete["run_id"] == run.run_id and complete["cost_micro"] == 300 and complete["duration_ms"] == 2000
    [ended] = [e for e in led.events_of(run.run_id) if e["kind"] == "ended"]
    assert ended["data"]["phases"] == ["build"], "a build-only close, declared (Q-V18)"
    [sp] = otel.spans(close_mod.SPAN)
    assert sp.attributes["isidium.run_id"] == run.run_id and sp.attributes["isidium.outcome"] == "closed"


def test_the_pull_request_pr_open_records_is_the_one_close_reads(disk: Disk, led: Ledger, tmp_path: Path) -> None:
    run = a_run(disk, led, disk.refused)
    cli_mod._record_pr(disk.ctx, TENANT, f"story/{run.run_id}", 57)
    cli_mod._record_pr(disk.ctx, TENANT, "feature/not-a-run", 58)
    row = led.run(run.run_id)
    assert row is not None and row["pr"] == 57
    cli_mod._record_pr(dataclasses.replace(disk.ctx, home=tmp_path), TENANT, f"story/{run.run_id}", 59)
    assert not (tmp_path / ledger_mod.LEDGER_FILE).exists(), "a deploy home with no ledger is not given one"
    forge = forge_for(run, gate=RED)
    assert close_run(disk, led, run, forge, pr=None)["outcome"] == "failed:gate"
    assert forge.seen[0] == ("merge_state", 57)
