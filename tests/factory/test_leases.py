"""Card 28: a run's close and fixup take a lease in the ledger, so the operator and the PR watcher never act on one run
at once, and the record says who acted and when.

The lease is a row in the ledger's own sqlite, taken under `BEGIN IMMEDIATE` (R1, R2), released with the action's
outcome when it ends (R3), taken by the verbs and not by `close()` / `run_fixup()` (R4), and counted per holder (R5).
The ledger-level tests pass explicit aware datetimes a whole second or more from every boundary; the verb-level ones run
over the V4a tenant through the CLI with the forge and the channel swapped for doubles, as card 26's do.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from typer.testing import CliRunner

from isidium.factory import adapter as adapter_mod
from isidium.factory import cli as cli_mod
from isidium.factory import close as close_mod
from isidium.factory import container
from isidium.factory import github as github_mod
from isidium.factory import ledger as ledger_mod
from isidium.factory import runner as runner_mod
from isidium.factory.ledger import Ledger, NewRun

from .test_v4a import ROOT, TENANT, Disk, disk, fresh_run, refuses
from .test_v4a_ii import led

__all__ = ["disk", "led"]  # the V4a tenant and its ledger, as test_v4a_ii builds them

T = datetime(2026, 10, 4, 12, 0, 0, tzinfo=UTC)
FAR = datetime(2026, 10, 4, 14, 0, 0, tzinfo=UTC)


def _stamp(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _new(card: int = 28) -> NewRun:
    return NewRun(
        card=card,
        lane="standard",
        build_hash="sha256:b",
        base_sha="a" * 40,
        adapter="container",
        dispatched_at="2026-10-04T11:00:00Z",
        payload_hash="sha256:p",
        config_hash="sha256:c",
        identity="isdm-fac-lander[bot]",
    )


def _ledger(tmp_path: Path) -> Ledger:
    return Ledger(tmp_path / "ledger.sqlite", TENANT)


def _leases(led_: Ledger, run_id: str | None = None) -> list[dict[str, Any]]:
    """Every lease row, or one run's. `disk` is module-scoped, so a test that reads through it asks by run."""
    rows = led_.db.execute("SELECT * FROM leases ORDER BY rowid").fetchall()
    return [dict(r) for r in rows if run_id is None or r["run_id"] == run_id]


def _argv(disk_: Disk, verb: str, run_id: str, *more: str) -> list[str]:
    return [verb, "--tenant", TENANT, "--checkout", str(disk_.work), "--root", ROOT, "--run", run_id, *more]


def _doubles(disk_: Disk, monkeypatch: pytest.MonkeyPatch) -> None:
    """No mTLS channel and no forge: the verbs under test are the lease's wrapper around the action."""
    monkeypatch.setattr(github_mod, "GitHub", lambda ctx: SimpleNamespace())
    monkeypatch.setattr(cli_mod, "Transport", lambda cfg, home: SimpleNamespace(call=disk_.call))


# ------------------------------------------------------------------------------------------------------- R1 / S1


def test_the_lease_table_keeps_every_row(tmp_path: Path) -> None:
    led_ = _ledger(tmp_path)
    try:
        cols = [str(r[1]) for r in led_.db.execute("PRAGMA table_info(leases)")]
        assert cols == [
            "run_id",
            "action",
            "head_sha",
            "holder",
            "taken_at",
            "expires_at",
            "released_at",
            "outcome",
        ]
        assert "meta" in ledger_mod._DDL[0] and "runs" in ledger_mod._DDL[1], "the DDL's order is not changed"
        assert "leases" in ledger_mod._DDL[-1]

        run_id = led_.dispatch(_new())
        first = led_.take_lease(run_id, "close", "operator", "h1", T, 60)
        led_.release_lease(first, T + timedelta(seconds=5), "closed")
        dead = led_.take_lease(run_id, "close", "operator", None, T + timedelta(seconds=10), 60)  # never released
        third = led_.take_lease(run_id, "close", "watcher", None, T + timedelta(seconds=100), 60)  # past `dead`
        led_.release_lease(third, T + timedelta(seconds=110), "failed:gate")

        rows = _leases(led_)
        assert len(rows) == 3 and led_.db.execute("SELECT COUNT(*) FROM leases").fetchone()[0] == 3
        assert [r["outcome"] for r in rows] == ["closed", None, "failed:gate"]
        assert rows[0]["released_at"] == _stamp(T + timedelta(seconds=5))
        assert rows[1]["released_at"] is None and rows[1]["expires_at"] == _stamp(T + timedelta(seconds=70))
        assert [first.id, dead.id, third.id] == [1, 2, 3]
        assert [r["holder"] for r in rows] == ["operator", "operator", "watcher"]

        with pytest.raises(sqlite3.IntegrityError):
            led_.db.execute(
                "INSERT INTO leases (run_id, action, holder, taken_at, expires_at) VALUES (?, 'close', 'nobody', 'a', 'b')",
                (run_id,),
            )
    finally:
        led_.close()


# ------------------------------------------------------------------------------------------------------- R2 / S2


def test_an_unexpired_lease_refuses_a_second_taker(tmp_path: Path) -> None:
    a = _ledger(tmp_path)
    b = Ledger(a.path, TENANT)  # a second connection to one file, as a second process would be
    try:
        run_id = a.dispatch(_new())
        other = a.dispatch(_new())
        held = a.take_lease(run_id, "close", "operator", None, T, 60)

        r = refuses(
            "run.lease-held", lambda: b.take_lease(run_id, "close", "watcher", None, T + timedelta(seconds=1), 60)
        )
        assert "operator" in str(r) and held.expires_at in str(r)
        assert len(_leases(a)) == 1, "the refused take wrote nothing"

        b.take_lease(run_id, "fixup", "watcher", None, T + timedelta(seconds=1), 60)  # the key is the action
        b.take_lease(other, "close", "watcher", None, T + timedelta(seconds=1), 60)  # and the run

        a.release_lease(held, T + timedelta(seconds=2), "closed")
        b.take_lease(run_id, "close", "watcher", None, T + timedelta(seconds=3), 60)

        refuses("ledger.unknown-run", lambda: b.take_lease("r-999", "close", "operator", None, T, 60))
    finally:
        a.close()
        b.close()


# ------------------------------------------------------------------------------------------------------- R3 / S3


def test_a_refusal_releases_the_lease_with_its_outcome(
    disk: Disk, led: Ledger, monkeypatch: pytest.MonkeyPatch
) -> None:
    _doubles(disk, monkeypatch)
    run_id = fresh_run(disk, led)
    argv = _argv(disk, "run", run_id, "--phase", "fixup")

    out = CliRunner().invoke(cli_mod.app, argv)
    assert out.exit_code == 2, out.output  # run_fixup's own refusal: this run has no review and no pull request
    (row,) = _leases(led, run_id)
    assert row["action"] == "fixup" and row["released_at"] is not None
    assert row["outcome"] and row["outcome"].startswith("run.") and row["outcome"] in out.output
    assert row["outcome"] != "run.lease-held"

    again = CliRunner().invoke(cli_mod.app, argv)
    assert again.exit_code == 2 and row["outcome"] in again.output and "run.lease-held" not in again.output, (
        "the lease was released, so the second invocation reaches the action and is refused by it"
    )

    def boom(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("the action died")

    monkeypatch.setattr(close_mod, "close", boom)
    died = CliRunner().invoke(cli_mod.app, _argv(disk, "close", run_id))
    assert died.exit_code != 0 and isinstance(died.exception, RuntimeError)
    held = [r for r in _leases(led, run_id) if r["action"] == "close"]
    assert len(held) == 1 and held[0]["released_at"] is not None
    assert held[0]["outcome"] == ledger_mod.LEASE_RAISED


# ------------------------------------------------------------------------------------------------------- R2 / S4


def test_an_expired_lease_can_be_taken_again(tmp_path: Path) -> None:
    led_ = _ledger(tmp_path)
    try:
        run_id = led_.dispatch(_new())
        led_.take_lease(run_id, "fixup", "operator", None, T, 60)  # never released: its holder died
        refuses(
            "run.lease-held", lambda: led_.take_lease(run_id, "fixup", "watcher", None, T + timedelta(seconds=59), 60)
        )
        again = led_.take_lease(run_id, "fixup", "watcher", None, T + timedelta(seconds=61), 60)
        rows = _leases(led_)
        assert len(rows) == 2 and rows[0]["released_at"] is None, "both rows remain, the dead one as written"
        assert rows[1]["holder"] == "watcher" and again.taken_at == _stamp(T + timedelta(seconds=61))
    finally:
        led_.close()


# ------------------------------------------------------------------------------------------------------- R4 / S5


def test_the_verbs_take_their_lease_as_the_operator(
    disk: Disk, led: Ledger, monkeypatch: pytest.MonkeyPatch, otel: Any
) -> None:
    _doubles(disk, monkeypatch)
    run_id = fresh_run(disk, led)
    led.advance(run_id, "f" * 40, [], None)
    seen: dict[str, list[dict[str, Any]]] = {}

    def held(action: str) -> None:
        # Read through the ledger the verb opened: the lease must be taken before the action starts.
        seen[action] = [r for r in _leases(led, run_id) if r["action"] == action]

    def close_stub(ctx: Any, ledger: Ledger, call: Any, forge: Any, *, run_id: str, pr: int | None = None) -> Any:
        held("close")
        return {"outcome": "closed"}

    def fixup_stub(ctx: Any, reg: Any, ledger: Ledger, call: Any, forge: Any, *, run_id: str) -> Any:
        held("fixup")
        return {"outcome": "dispatched"}

    monkeypatch.setattr(close_mod, "close", close_stub)
    monkeypatch.setattr(runner_mod, "run_fixup", fixup_stub)
    otel.clear()
    closed = CliRunner().invoke(cli_mod.app, _argv(disk, "close", run_id))
    fixed = CliRunner().invoke(cli_mod.app, _argv(disk, "run", run_id, "--phase", "fixup"))
    assert closed.exit_code == 0 and fixed.exit_code == 0, closed.output + fixed.output

    for action, outcome in (("close", "closed"), ("fixup", "dispatched")):
        (during,) = seen[action]
        assert during["holder"] == "operator" and during["released_at"] is None, "held while the action runs"
        (after,) = [r for r in _leases(led, run_id) if r["action"] == action]
        assert after["outcome"] == outcome and after["released_at"] is not None
        assert after["head_sha"] == "f" * 40, "the run row's head"

    def span_of(taken: dict[str, Any]) -> timedelta:
        fmt = "%Y-%m-%dT%H:%M:%SZ"
        return datetime.strptime(taken["expires_at"], fmt) - datetime.strptime(taken["taken_at"], fmt)

    by = {r["action"]: r for r in _leases(led, run_id)}
    assert span_of(by["close"]) == timedelta(seconds=cli_mod.CLOSE_LEASE_S)
    policy = adapter_mod.ExecutorPolicy.from_effective(disk.ctx.eff)
    assert span_of(by["fixup"]) == timedelta(seconds=policy.budgets.wall_clock_s * container.ATTEMPTS)

    spans = otel.spans(ledger_mod.SPAN)
    for action in ("close", "fixup"):
        ours = [s for s in spans if s.attributes.get("isidium.lease.action") == action]
        assert len(ours) == 2, "the take and the release, each inside the ledger's write span"
        assert {s.attributes.get("isidium.lease.holder") for s in ours} == {"operator"}


# ------------------------------------------------------------------------------------------------------- R5 / S6


def test_the_ceiling_count_is_the_holders_leases_since(tmp_path: Path) -> None:
    led_ = _ledger(tmp_path)
    try:
        run_id = led_.dispatch(_new())
        hour = timedelta(hours=1)
        w = [
            led_.take_lease(run_id, "fixup", "watcher", None, T - 2 * hour, 60),
            led_.take_lease(run_id, "fixup", "watcher", None, T - hour / 2, 60),
            led_.take_lease(run_id, "fixup", "watcher", None, T, 60),
            led_.take_lease(run_id, "fixup", "watcher", None, T + hour / 6, 60),
        ]
        led_.release_lease(w[0], T - 2 * hour + timedelta(seconds=5), "done")
        led_.release_lease(w[2], T + timedelta(seconds=5), "done")  # w[1] and w[3] are left to expire
        led_.take_lease(run_id, "fixup", "operator", None, T + hour, 60)
        led_.take_lease(run_id, "close", "watcher", None, T + hour, 60)

        assert led_.leases_taken("watcher", "fixup", T - hour) == 3
        assert led_.leases_taken("watcher", "fixup", T) == 2, "inclusive at the boundary"
        assert led_.leases_taken("operator", "fixup", T - hour) == 1
        assert led_.leases_taken("watcher", "close", T - 3 * hour) == 1
    finally:
        led_.close()


# ------------------------------------------------------------------------------------------------------- R6 / S7


def test_a_schema_3_ledger_gains_the_lease_table(tmp_path: Path) -> None:
    path = tmp_path / "old.sqlite"
    old = ledger_mod._DDL[:-1]
    assert not any("leases" in ddl for ddl in old)
    db = sqlite3.connect(str(path), isolation_level=None)
    for ddl in old:
        db.execute(ddl)
    db.execute("INSERT INTO meta VALUES ('schema', '3')")
    db.execute("INSERT INTO meta VALUES ('tenant', ?)", (TENANT,))
    db.execute("INSERT INTO meta VALUES ('next_run', '2')")
    db.execute(
        "INSERT INTO runs (run_id, card, outcome, lane, build_hash, base_sha, dispatched_at, story_branch, adapter,"
        " payload_hash, config_hash, context, score, refs_resolved, identity)"
        " VALUES ('r-1', 5, 'dispatched', 'standard', 'b', 'a', '2026-09-20T00:00:00Z', 'story/r-1', 'container',"
        " 'p', 'c', '{}', '{}', '[]', 'bot')"
    )
    db.close()

    led_ = Ledger(path, TENANT)
    try:
        tables = {str(r[0]) for r in led_.db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert "leases" in tables
        assert led_._meta("schema") == str(ledger_mod.SCHEMA) == "4"
        row = led_.run("r-1")
        assert row is not None and row["card"] == 5 and row["story_branch"] == "story/r-1", "its rows are kept"
        assert led_.take_lease("r-1", "close", "operator", None, T, 60).run_id == "r-1"
    finally:
        led_.close()
