"""V3 (2026-09-11) — the ledger (`isidium.factory.ledger`), the ordering (`isidium.factory.ordering`), the
registration (`isidium.factory.tenant`) and the pick (`isidium.factory.dispatch`), and the two verbs.

The pick runs over a real checkout with a bare `origin` answering to a GitHub url (V2's shape) and a real store over
it, reached in process through `Api` as the lander — the same call the verb makes over the wire. Four cards: two
ratified in one sitting and landed (P1 and P0, so the order is visible), one draft, one ratified after the land (no
fingerprint yet). Every refusal asserted is the typed one; the positive discriminators are the ledger's rows, the
forge's recorded calls and the branch in the checkout.
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
import json
import sqlite3
import subprocess
from collections.abc import Iterator
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from isidium.factory import checkout as checkout_mod
from isidium.factory import cli as cli_mod
from isidium.factory import context as context_mod
from isidium.factory import dispatch as dispatch_mod
from isidium.factory import ledger as ledger_mod
from isidium.factory import ordering
from isidium.factory.context import TenantContext
from isidium.factory.github import GitHub
from isidium.factory.ledger import Ledger, NewRun
from isidium.factory.ordering import Head
from isidium.factory.tenant import Registration
from isidium.store.client.config import ClientConfig
from isidium.store.core import events as events_mod
from isidium.store.core.grammar import Document
from isidium.store.core.refusal import Refusal
from isidium.store.server.api import Api
from isidium.store.server.store import NewCard, Store

from ..store.conftest import BASE_SCOPE, LANDER, OWNER, PLANNER, base_head, git, store_on_disk, tenant_checkout

ROOT = "docs/work/"
TENANT = "sartor"
URL = "https://github.com/acme/widgets.git"
LOGIN = "isdm-fac-lander[bot]"
ADAPTER = "container"
EMPTY: dict[str, Any] = {"run_id": "r-0", "events": [], "suggestions": []}
TODAY = _dt.datetime.now(_dt.UTC).date()
AT = "2026-09-11T12:00:00Z"


def refuses(rule: str, fn: Any) -> Refusal:
    with pytest.raises(Refusal) as ei:
        fn()
    assert ei.value.rule == rule, str(ei.value)
    return ei.value


def card(st: Store, slug: str, **over: Any) -> int:
    head = base_head(0, "draft")
    head.update(over)
    r = st.write(NewCard(slug), Document(head, {"Scope": BASE_SCOPE}), None, None, PLANNER)
    assert r.id is not None
    return r.id


@dataclass
class Disk:
    work: Path
    home: Path
    store: Store
    a: int  # P1, ratified in the sitting, landed
    b: int  # P0, ratified in the sitting, landed — the head
    draft: int
    c: int  # P1, ratified after the land — no fingerprint
    ctx: TenantContext

    def call(self, name: str, args: Any) -> Any:
        return Api(self.store).call(name, LANDER, args)


@pytest.fixture(scope="module")
def disk(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Disk]:
    tmp = tmp_path_factory.mktemp("v3")
    work = tenant_checkout(tmp)
    st = store_on_disk(work, tmp / "journal.sqlite", root=ROOT)
    st.init(OWNER, software_key_ack="ok for V3", root=ROOT)
    a, b = card(st, "p1-story"), card(st, "p0-story", priority="P0")
    st.ratify([a, b], OWNER)
    d = card(st, "still-a-draft")
    st.land(EMPTY, LANDER)
    c = card(st, "ratified-after-the-land")
    st.ratify([c], OWNER)
    bare = (tmp / "origin.git").as_posix()
    git(work, "remote", "set-url", "origin", URL)
    git(work, "config", f"url.{bare}.insteadOf", URL)
    home = tmp / "deploy"
    fd = home / TENANT / "factory"
    fd.mkdir(parents=True)
    (fd / "client.toml").write_text(ClientConfig(tenant=TENANT).render(), encoding="utf-8")
    (fd / "forge.toml").write_text(
        f'kind = "token"\nlogin = "{LOGIN}"\nname = "isdm-fac-lander"\nemail = "1+x@users.noreply.github.com"\n'
        'token = "forge.token"\n',
        encoding="utf-8",
    )
    (fd / "forge.token").write_text("ghp_test\n", encoding="utf-8")
    until = (TODAY + _dt.timedelta(days=30)).isoformat()
    (fd / "tenant.toml").write_text(
        f'allow_software_grade_until = {until}\nwip = 1\nadapter = "{ADAPTER}"\n\n[payload]\nmax_bytes = 1000000\n',
        encoding="utf-8",
    )
    mp = pytest.MonkeyPatch()
    mp.setenv("ISIDIUM_DEPLOY", str(home))
    ctx = context_mod.load(TENANT, work, base="main", root=ROOT)
    yield Disk(work, fd, st, a, b, d, c, ctx)
    mp.undo()


@pytest.fixture
def led(tmp_path: Path) -> Iterator[Ledger]:
    ledger = Ledger(tmp_path / "ledger.sqlite", TENANT)
    yield ledger
    ledger.close()


@dataclass
class RecForge:
    """The pick's one forge call, recorded with the ledger's runs at the moment it is made."""

    ledger: Ledger
    fail: Refusal | None = None
    seen: list[tuple[str, str, list[str]]] = field(default_factory=list)

    def branch(self, name: str, at: str) -> None:
        self.seen.append((name, at, [r["run_id"] for r in self.ledger.runs()]))
        if self.fail is not None:
            raise self.fail


def with_reg(ctx: TenantContext, **over: Any) -> TenantContext:
    assert ctx.registration is not None
    return dataclasses.replace(ctx, registration=dataclasses.replace(ctx.registration, **over))


def new_run(cid: int = 1, lane: str = "standard") -> NewRun:
    return NewRun(
        card=cid,
        lane=lane,
        build_hash="sha256:" + "b" * 64,
        base_sha="c" * 40,
        adapter=ADAPTER,
        dispatched_at=AT,
        payload_hash="sha256:" + "d" * 64,
        config_hash="sha256:" + "e" * 64,
        identity=LOGIN,
        score={"rank": 0},
        refs_resolved=({"path": "a.py", "blob": "f" * 40},),
    )


# ---- the ledger ------------------------------------------------------------------------------------------------------


def test_a_run_is_written_with_its_dispatched_event_in_one_transaction_and_read_back(led: Ledger) -> None:
    rid = led.dispatch(new_run(7))
    assert rid == "r-1"
    row = led.run(rid)
    assert row is not None
    assert row["card"] == 7 and row["outcome"] == "dispatched" and row["story_branch"] == "story/r-1"
    assert row["refs_resolved"] == [{"path": "a.py", "blob": "f" * 40}] and row["score"] == {"rank": 0}
    assert row["batch"] is None and row["ended_at"] is None and row["identity"] == LOGIN
    assert [(e["kind"], e["data"]) for e in led.events_of(rid)] == [("dispatched", {"card": 7})]


def test_the_counter_is_monotonic_across_a_reopen(tmp_path: Path) -> None:
    first = Ledger(tmp_path / "l.sqlite", TENANT)
    assert first.dispatch(new_run()) == "r-1"
    first.close()
    again = Ledger(tmp_path / "l.sqlite", TENANT)
    assert again.dispatch(new_run()) == "r-2" and [r["run_id"] for r in again.runs()] == ["r-1", "r-2"]
    again.close()


def test_a_run_id_the_ledger_holds_is_refused_and_nothing_is_written(led: Ledger) -> None:
    led.dispatch(new_run())
    led.db.execute("UPDATE meta SET value = '1' WHERE key = 'next_run'")  # a counter that went backwards
    refuses("ledger.duplicate-run", lambda: led.dispatch(new_run(9)))
    assert [r["card"] for r in led.runs()] == [1] and len(led.events_of("r-1")) == 1
    assert led._meta("next_run") == "1", "the counter did not move for a row that was not written"


def test_in_flight_counts_until_a_run_ends(led: Ledger) -> None:
    r1, r2 = led.dispatch(new_run(1)), led.dispatch(new_run(2))
    assert [r["run_id"] for r in led.in_flight()] == [r1, r2]
    led.fail(r1, AT, "environment", "forge.branch-exists: story/r-1")
    assert [r["run_id"] for r in led.in_flight()] == [r2]
    row = led.run(r1)
    assert row is not None and row["outcome"] == "failed:environment" and row["ended_at"] == AT
    assert led.events_of(r1)[-1]["kind"] == "interrupt"


def test_the_report_is_generated_from_the_ledger(led: Ledger) -> None:
    rid = led.dispatch(new_run(4))
    want = events_mod.parse_report(
        {"run_id": rid, "events": [{"kind": "dispatched", "card": 4, "at": AT, "run_id": rid}], "suggestions": []}
    )
    assert led.report(rid) == want
    refuses("ledger.unknown-run", lambda: led.report("r-99"))


def test_the_ledger_is_wal_and_one_tenants(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "l.sqlite", TENANT)
    assert ledger.db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    ledger.close()
    refuses("ledger.tenant", lambda: Ledger(tmp_path / "l.sqlite", "someone-else"))


# ---- the ordering ----------------------------------------------------------------------------------------------------


def test_expedite_before_p0_before_p1_then_the_oldest_ratification_then_the_id() -> None:
    heads = [
        Head(5, False, "P1", "2026-08-30T00:00:00Z"),  # the oldest P1 ratification carries the largest P1 id
        Head(4, False, "P1", "2026-09-01T00:00:00Z"),
        Head(3, False, "P0", "2026-09-03T00:00:00Z"),
        Head(9, True, "P3", "2026-09-04T00:00:00Z"),
        Head(2, False, "P1", "2026-09-01T00:00:00Z"),
        Head(8, False, None, "2026-08-01T00:00:00Z"),
    ]
    got = [r.card for r in ordering.order(heads, expedite_open=True)]
    assert got == [9, 3, 5, 2, 4, 8], "expedite; P0; P1 oldest ratification first, then id; the classless last"
    for perm in (list(reversed(heads)), heads[2:] + heads[:2]):
        assert [r.card for r in ordering.order(perm, expedite_open=True)] == got, "total: any order in, one out"
    closed = [r.card for r in ordering.order(heads, expedite_open=False)]
    assert closed == [3, 5, 2, 4, 9, 8], "the dial shut: the expedite card waits in its own class"


def test_the_score_is_the_rank_the_zero_vector_and_the_config_hash() -> None:
    [r] = ordering.order([Head(1, False, "P1", AT)], expedite_open=True)
    assert r.score("sha256:x") == {"rank": 0, "vector": dict.fromkeys(ordering.VECTOR, 0), "config_hash": "sha256:x"}
    assert ordering.expedite_open([{"lane": "expedite"}], 1) is False
    assert ordering.expedite_open([{"lane": "standard"}], 1) is True


# ---- the registration -----------------------------------------------------------------------------------------------


def test_tenant_toml_is_read_whole_or_refused_naming_every_bad_key(tmp_path: Path) -> None:
    assert Registration.load(tmp_path) is None, "no file: a tenant the factory does not dispatch on"
    (tmp_path / "tenant.toml").write_text("allow_software_grade_until = 2026-09-11T00:00:00Z\nwip = 0\n", "utf-8")
    r = refuses("factory.registration", lambda: Registration.load(tmp_path))
    for key in ("wip", "adapter", "[payload].max_bytes", "allow_software_grade_until"):
        assert key in r.detail, r.detail
    (tmp_path / "tenant.toml").write_text('wip = 1\nadapter = "a"\n[payload]\nmax_bytes = 5\n', "utf-8")
    reg = Registration.load(tmp_path)
    assert reg == Registration(None, 1, "a", 5) and not reg.allows_software_grade(TODAY)


def test_the_software_grade_allowance_runs_through_its_date() -> None:
    reg = Registration(_dt.date(2026, 9, 11), 1, "a", 5)
    assert reg.allows_software_grade(_dt.date(2026, 9, 11)) and reg.allows_software_grade(_dt.date(2026, 9, 1))
    assert not reg.allows_software_grade(_dt.date(2026, 9, 12))


def test_the_context_carries_the_registration_in_its_value(disk: Disk) -> None:
    assert disk.ctx.registration is not None and disk.ctx.registration.wip == 1
    assert disk.ctx.value()["registration"]["adapter"] == ADAPTER


# ---- the pick --------------------------------------------------------------------------------------------------------


def test_the_view_is_the_ready_cards_and_a_sitting_is_software_grade(disk: Disk) -> None:
    view = disk.call("dispatch", {})
    assert view["ready"] == [{"id": i, "software_grade": True} for i in sorted((disk.a, disk.b))]
    # a ratification newer than the last land projects `pending-ingest` (row 11), so it is off the view until landed
    assert disk.store.projection_of(disk.c).render() == "ratified (pending-ingest)"


def test_the_pick_takes_the_head_and_writes_the_record_before_the_branch(disk: Disk, led: Ledger) -> None:
    forge = RecForge(led)
    row = dispatch_mod.pick(disk.ctx, led, disk.call, forge)
    assert row["run_id"] == "r-1" and row["card"] == disk.b, "P0 before P1"
    assert forge.seen == [("story/r-1", disk.ctx.base_sha, ["r-1"])], "the row existed when the branch was asked for"
    assert row["base_sha"] == disk.ctx.base_sha and row["adapter"] == ADAPTER and row["identity"] == LOGIN
    assert row["payload_hash"].startswith("sha256:") and row["score"]["rank"] == 0
    assert row["score"]["config_hash"] == row["config_hash"] and set(row["score"]["vector"].values()) == {0}
    assert [r["path"] for r in row["refs_resolved"]] == [
        "client/cards/validator.py",
        "docs/dev/work/items/0060-cards-check-no-acceptance.md",
    ]


def test_the_order_over_the_real_heads_is_p0_then_the_p1s_oldest_first(disk: Disk) -> None:
    docs = checkout_mod.heads(disk.work, disk.ctx.base_sha, ROOT, [disk.c, disk.a, disk.b], disk.ctx.registry)
    ranked = ordering.order([Head.of(i, d) for i, d in docs.items()], expedite_open=True)
    assert [r.card for r in ranked] == [disk.b, disk.a, disk.c]


def test_with_the_real_driver_the_story_branch_is_at_the_synced_head(disk: Disk, led: Ledger) -> None:
    row = dispatch_mod.pick(disk.ctx, led, disk.call, GitHub(disk.ctx))
    try:
        assert git(disk.work, "rev-parse", "refs/heads/story/r-1").strip() == disk.ctx.base_sha == row["base_sha"]
    finally:
        git(disk.work, "branch", "-D", "story/r-1")


def test_a_second_pick_is_refused_wip_naming_the_run_in_flight(disk: Disk, led: Ledger) -> None:
    dispatch_mod.pick(disk.ctx, led, disk.call, RecForge(led))
    r = refuses("dispatch.wip", lambda: dispatch_mod.pick(disk.ctx, led, disk.call, RecForge(led)))
    assert "r-1" in r.path and len(led.runs()) == 1


def test_the_stores_pending_land_passes_through_and_nothing_is_written(disk: Disk, led: Ledger) -> None:
    def pending(name: str, args: Any) -> Any:
        if name == "dispatch":
            raise Refusal("dispatch.pending-land", "", "merged, not landed: 1")
        return disk.call(name, args)

    refuses("dispatch.pending-land", lambda: dispatch_mod.pick(disk.ctx, led, pending, RecForge(led)))
    assert led.runs() == []


def test_a_card_off_the_view_is_not_ready(disk: Disk, led: Ledger) -> None:
    for off in (disk.draft, 999):
        refuses(
            "dispatch.not-ready", lambda off=off: dispatch_mod.pick(disk.ctx, led, disk.call, RecForge(led), card=off)
        )
    assert led.runs() == []


def test_a_named_card_in_the_view_is_picked_over_the_head(disk: Disk, led: Ledger) -> None:
    row = dispatch_mod.pick(disk.ctx, led, disk.call, RecForge(led), card=disk.a)
    assert row["card"] == disk.a and row["score"]["rank"] == 1


def test_a_software_grade_ratification_is_refused_without_the_date_and_picked_with_it(disk: Disk, led: Ledger) -> None:
    for until in (None, TODAY - _dt.timedelta(days=1)):
        ctx = with_reg(disk.ctx, allow_software_grade_until=until)
        refuses("dispatch.software-grade", lambda ctx=ctx: dispatch_mod.pick(ctx, led, disk.call, RecForge(led)))
    assert led.runs() == []
    today = with_reg(disk.ctx, allow_software_grade_until=TODAY)
    assert dispatch_mod.pick(today, led, disk.call, RecForge(led), dry_run=True)["card"] == disk.b


def test_a_ready_card_with_no_fingerprint_is_refused_not_landed(disk: Disk, led: Ledger) -> None:
    """Two ways to have no fingerprint. A ratification newer than the land is `pending-ingest` and never reaches the
    pick (`not-ready`). A ratification landed before `config@5` — every card tenant #0 holds today — is `ready` with no
    fingerprint (its entry is behind the landed head); the pick refuses it `not-landed`, fail-closed."""
    refuses("dispatch.not-ready", lambda: dispatch_mod.pick(disk.ctx, led, disk.call, RecForge(led), card=disk.c))

    def pre_v3(name: str, args: Any) -> Any:
        out = disk.call(name, args)
        return {**out, "fingerprint": None} if name == "dispatch" and args.get("card") is not None else out

    r = refuses("dispatch.not-landed", lambda: dispatch_mod.pick(disk.ctx, led, pre_v3, RecForge(led)))
    assert r.path == str(disk.b) and "re-ratify" in r.detail and led.runs() == []


def test_a_ref_whose_blob_moved_since_the_ratification_is_refused_ref_drifted(disk: Disk, led: Ledger) -> None:
    def drifted(name: str, args: Any) -> Any:
        out = disk.call(name, args)
        if name == "dispatch" and args.get("card") is not None:
            fp = json.loads(json.dumps(out["fingerprint"]))
            fp["refs_resolved"][0]["blob"] = "0" * 40
            out = {**out, "fingerprint": fp}
        return out

    r = refuses("dispatch.ref-drifted", lambda: dispatch_mod.pick(disk.ctx, led, drifted, RecForge(led)))
    assert r.path.startswith("client/cards/validator.py: " + "0" * 40) and led.runs() == []


def test_an_oversize_payload_writes_no_row(disk: Disk, led: Ledger) -> None:
    ctx = with_reg(disk.ctx, max_bytes=10)
    refuses("payload.oversize", lambda: dispatch_mod.pick(ctx, led, disk.call, RecForge(led)))
    assert led.runs() == []


def test_a_branch_failure_after_the_record_leaves_failed_environment_in_the_row(disk: Disk, led: Ledger) -> None:
    forge = RecForge(led, fail=Refusal("forge.branch-exists", "story/r-1", "a branch of that name exists"))
    refuses("dispatch.environment", lambda: dispatch_mod.pick(disk.ctx, led, disk.call, forge))
    row = led.run("r-1")
    assert row is not None and row["outcome"] == "failed:environment" and row["ended_at"] is not None
    assert led.in_flight() == [] and led.events_of("r-1")[-1]["data"]["reason"] == "environment"


def test_a_dry_run_answers_the_pick_and_writes_nothing(disk: Disk, led: Ledger) -> None:
    forge = RecForge(led)
    out = dispatch_mod.pick(disk.ctx, led, disk.call, forge, dry_run=True)
    assert out["dry_run"] is True and out["card"] == disk.b and out["payload_hash"].startswith("sha256:")
    assert led.runs() == [] and forge.seen == []
    assert led.db.execute("SELECT count(*) FROM events").fetchone()[0] == 0


def test_the_heads_cost_two_spawns_however_many_cards(disk: Disk, monkeypatch: pytest.MonkeyPatch) -> None:
    spawned: list[list[str]] = []

    class Counting(subprocess.Popen[bytes]):
        def __init__(self, cmd: Any, *a: Any, **kw: Any) -> None:
            spawned.append(list(cmd))
            super().__init__(cmd, *a, **kw)

    monkeypatch.setattr(subprocess, "Popen", Counting)
    for ids in ([disk.a], [disk.a, disk.b, disk.c]):
        spawned.clear()
        docs = checkout_mod.heads(disk.work, disk.ctx.base_sha, ROOT, ids, disk.ctx.registry)
        assert sorted(docs) == sorted(ids)
        assert [c[:2] for c in spawned] == [["git", "ls-tree"], ["git", "cat-file"]]


def test_the_verbs_dispatch_and_read_the_ledger(disk: Disk, monkeypatch: pytest.MonkeyPatch) -> None:
    class Channel:
        def __init__(self, cfg: Any, workdir: Any) -> None:
            pass

        def call(self, name: str, args: Any) -> Any:
            return disk.call(name, args)

    monkeypatch.setattr(cli_mod, "Transport", Channel)
    base = ["--tenant", TENANT, "--checkout", str(disk.work), "--root", ROOT]
    try:
        dry = CliRunner().invoke(cli_mod.app, ["dispatch", *base, "--dry-run"])
        assert dry.exit_code == 0, dry.output
        assert json.loads(dry.output)["dry_run"] is True
        res = CliRunner().invoke(cli_mod.app, ["dispatch", *base])
        assert res.exit_code == 0, res.output
        assert json.loads(res.output)["run_id"] == "r-1"
        again = CliRunner().invoke(cli_mod.app, ["dispatch", *base])
        assert again.exit_code == 2 and "dispatch.wip" in again.output
        runs = CliRunner().invoke(cli_mod.app, ["runs", "--tenant", TENANT, "--run", "r-1"])
        assert runs.exit_code == 0, runs.output
        got = json.loads(runs.output)
        assert [e["kind"] for e in got["report"]["events"]] == ["dispatched"] and got["run"]["card"] == disk.b
    finally:
        git(disk.work, "branch", "-D", "story/r-1")
        (disk.home / ledger_mod.LEDGER_FILE).unlink(missing_ok=True)
        for side in ("-wal", "-shm"):
            (disk.home / (ledger_mod.LEDGER_FILE + side)).unlink(missing_ok=True)


def test_the_spans_carry_the_card_the_rank_and_the_run(disk: Disk, led: Ledger, otel: Any) -> None:
    otel.clear()
    dispatch_mod.pick(disk.ctx, led, disk.call, RecForge(led))
    [sp] = otel.spans(dispatch_mod.SPAN)
    assert sp.attributes["isidium.card"] == disk.b and sp.attributes["isidium.rank"] == 0
    assert sp.attributes["isidium.run_id"] == "r-1"
    [order] = otel.spans(ordering.SPAN)
    assert order.attributes["isidium.ready"] == 2
    [write] = otel.spans(ledger_mod.SPAN)
    assert write.attributes["isidium.run_id"] == "r-1"


def test_a_ledger_file_is_one_sqlite_at_the_deploy_home(disk: Disk) -> None:
    with Ledger.open(disk.home, TENANT) as ledger:
        assert ledger.path == disk.home / "ledger.sqlite"
    with closing(sqlite3.connect(disk.home / "ledger.sqlite")) as db:
        assert db.execute("SELECT value FROM meta WHERE key='tenant'").fetchone()[0] == TENANT
    for side in ("", "-wal", "-shm"):
        (disk.home / ("ledger.sqlite" + side)).unlink(missing_ok=True)
