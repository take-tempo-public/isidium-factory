"""Card 37: an idle watcher pass reads the ledger and stops -- no tenant context, no fetch, no forge -- when no open run
has a pull request.

The idle tests build their own minimal deploy home under `tmp_path`: a `client.toml` and a ledger, with no `forge.toml`,
no `tenant.toml` and a checkout that does not exist, so any attempt to load the context fails loudly. The busy test
drives the V4a tenant as test_watch.py's CLI test does. The `disk` ledger is module-scoped and S2 gives its run a pull
request, which is why the idle tests must not share it.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from typer.testing import CliRunner

from isidium.factory import cli as cli_mod
from isidium.factory import close as close_mod
from isidium.factory import context, watch
from isidium.factory import github as github_mod
from isidium.factory import runner as runner_mod
from isidium.factory.ledger import Ledger, NewRun
from isidium.store.client.config import ClientConfig

from .test_v4a import ROOT, TENANT, Disk, disk, fresh_run
from .test_v4a_ii import led
from .test_watch import Forged, _state

__all__ = ["disk", "led"]  # the V4a tenant and its ledger, as test_v4a_ii builds them

AT = "2026-10-07T12:00:00Z"
IDLE = "idle-tenant"


def _new() -> NewRun:
    return NewRun(
        card=37,
        lane="standard",
        build_hash="sha256:b",
        base_sha="a" * 40,
        adapter="container",
        dispatched_at="2026-10-07T11:00:00Z",
        payload_hash="sha256:p",
        config_hash="sha256:c",
        identity="isdm-fac-lander[bot]",
    )


def _idle_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The smallest deploy home `tenant_client` accepts, and a ledger with two runs that are *not* open: one in flight
    with no pull request, and one with a pull request that has ended. Neither condition alone is the predicate."""
    home = tmp_path / "deploy"
    factory = home / IDLE / "factory"
    factory.mkdir(parents=True)
    (factory / "client.toml").write_text(ClientConfig(tenant=IDLE).render(), encoding="utf-8")
    monkeypatch.setenv("ISIDIUM_DEPLOY", str(home))
    with Ledger.open(factory, IDLE) as led_:
        led_.dispatch(_new())
        ended = led_.dispatch(_new())
        led_.set_pr(ended, 41)
        led_.end(ended, AT, "failed:gate")
    return factory


def _forbid(monkeypatch: pytest.MonkeyPatch) -> None:
    """Everything an idle pass must not reach: the context, its fetch, and the forge driver."""

    def no(*_a: Any, **_k: Any) -> Any:
        pytest.fail("an idle pass reached the tenant context or the forge")

    monkeypatch.setattr(context, "load", no)
    monkeypatch.setattr(context, "_fetch", no)
    monkeypatch.setattr(github_mod, "GitHub", no)


def _idle_watch(missing: Path) -> Any:
    argv = ["watch", "--tenant", IDLE, "--checkout", str(missing), "--once"]
    return CliRunner().invoke(cli_mod.app, argv)


def test_an_idle_pass_never_loads_the_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    factory = _idle_home(tmp_path, monkeypatch)
    _forbid(monkeypatch)

    out = _idle_watch(tmp_path / "no-checkout")

    assert out.exit_code == 0, out.output
    (line,) = out.output.strip().splitlines()
    assert line.startswith("watch: open=0 ") and "opt-in absent" not in line
    assert not (factory / watch.LOG_FILE).exists(), "an idle pass logs nothing"


def test_a_pass_with_an_open_pr_proceeds(disk: Disk, led: Ledger, monkeypatch: pytest.MonkeyPatch) -> None:
    run_id = fresh_run(disk, led)
    led.set_pr(run_id, 4242)
    led.advance(run_id, "1" * 40, [], None)
    driver = Forged(states={4242: _state("1" * 40, merged=True)})
    loads: list[str] = []
    closed: list[str] = []
    real_load = context.load

    def counting_load(*args: Any, **kwargs: Any) -> Any:
        loads.append(args[0])
        return real_load(*args, **kwargs)

    def close_stub(ctx: Any, ledger: Ledger, call: Any, forge_: Any, *, run_id: str, pr: int | None = None) -> Any:
        closed.append(run_id)
        return {"outcome": "closed"}

    def no_channel(name: str, args: Any) -> Any:
        raise AssertionError(f"the pass called the store directly: {name}")

    monkeypatch.setattr(context, "load", counting_load)
    monkeypatch.setattr(github_mod, "GitHub", lambda ctx: driver)
    monkeypatch.setattr(cli_mod, "Transport", lambda cfg, home: SimpleNamespace(call=no_channel))
    monkeypatch.setattr(close_mod, "close", close_stub)
    monkeypatch.setattr(runner_mod, "run_fixup", lambda *a, **k: pytest.fail("a fixup for a merged pull request"))

    argv = ["watch", "--tenant", TENANT, "--checkout", str(disk.work), "--root", ROOT, "--once"]
    out = CliRunner().invoke(cli_mod.app, argv)

    assert out.exit_code == 0, out.output
    assert loads == [TENANT], "a pass with an open pull request loads the context, once"
    assert ("merge_state", 4242) in driver.calls
    assert closed == [run_id]
    (line,) = out.output.strip().splitlines()
    assert line.startswith("watch: open=") and not line.startswith("watch: open=0 ") and "close=1" in line


def test_an_idle_pass_emits_its_span(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, otel: Any) -> None:
    _idle_home(tmp_path, monkeypatch)
    _forbid(monkeypatch)
    otel.clear()

    out = _idle_watch(tmp_path / "no-checkout")

    assert out.exit_code == 0, out.output
    (span,) = otel.spans(watch.PASS_SPAN)
    attrs = dict(span.attributes)
    assert (attrs["isidium.watch.open"], attrs["isidium.watch.held"], attrs["isidium.watch.refused"]) == (0, 0, 0)
    assert span.status.status_code.name == "OK"
    assert not otel.spans(context.SPAN) and not otel.spans(watch.READ_SPAN)


def test_an_idle_pass_still_refuses_an_unknown_tenant(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The ledger is found by `tenant_client`, so a tenant that is not registered is refused as it was before."""
    _idle_home(tmp_path, monkeypatch)
    argv = ["watch", "--tenant", "nobody", "--checkout", str(tmp_path), "--once"]
    out = CliRunner().invoke(cli_mod.app, argv)
    assert out.exit_code == 2 and "factory.unknown-tenant" in out.output
