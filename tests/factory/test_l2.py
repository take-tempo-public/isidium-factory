"""L2 (2026-09-09) — the lander client: the factory's one write, over the wire, as the credential its tenant's
`client.toml` names; and the seam it stands on — the deploy home, one directory per tenant.

The listener is the real edge (the edge test's authority issues every certificate), the store is the harness's, the
client is `isidium.factory.lander` through the store client's own `Transport`. Every refusal asserted is the typed
one and the recording service's count is the discriminator for "before any channel".
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest

from isidium.factory import lander, registration
from isidium.store.client.config import ClientConfig
from isidium.store.core.refusal import Refusal
from isidium.store.server.api import Api
from isidium.store.server.http import Limits, start, tls_context
from isidium.store.server.service import Registration

from ..store.conftest import OWNER, Harness, fresh
from ..store.test_edge import NOW, Recording, authority, issue


def refuses(rule: str, fn: Callable[[], Any]) -> Refusal:
    with pytest.raises(Refusal) as ei:
        fn()
    assert ei.value.rule == rule, str(ei.value)
    return ei.value


def serve(service: Recording, context: Any, body: Callable[[int], Awaitable[Any]]) -> Any:
    """One scenario against a freshly bound listener — the edge test's `against`, without its fixture."""

    async def run() -> Any:
        asyncio.get_running_loop().set_exception_handler(lambda _loop, _context: None)
        server = await start(service, "127.0.0.1", 0, context, Limits())
        port = int(server.sockets[0].getsockname()[1])
        try:
            return await body(port)
        finally:
            server.close()
            await server.wait_closed()

    return asyncio.run(run())


def client_file(home: Path, tenant: str, address: str, ca: Path, credential: tuple[Path, Path]) -> Path:
    d = home / tenant / "factory"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "client.toml"
    cfg = ClientConfig(tenant=tenant, address=address, ca=str(ca), cert=str(credential[0]), key=str(credential[1]))
    p.write_text(cfg.render(), encoding="utf-8")
    return p


def ratified(hz: Harness, slug: str) -> int:
    cid = hz.draft(slug)
    hz.st.ratify([cid], OWNER)
    return cid


def test_the_lander_lands_over_the_wire_as_its_credential(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The whole of L2's done-criterion, short of the live store: a run report through the factory client, over mTLS,
    as the subject the registration binds to `lander`; the store's state moves and the store's result comes back
    unchanged. The owner's certificate through the same client is `write.grant`; a subject the registration does not
    name is `auth.unknown-client`; a malformed report never opens the channel."""
    ca = authority(tmp_path, "tenant-ca")
    server_cert, server_key = issue(ca, tmp_path, "store.l2", "store", server=True)
    hz = fresh("l2")
    cid = ratified(hz, "landed")
    reg = Registration(
        {
            "CN=lander@l2": ("lander@l2", "lander"),
            "CN=owner@example": ("amodal1@example", "owner"),
        },
        lambda: int(NOW.timestamp()),
    )
    service = Recording(Api(hz.st), reg, hz.st.tenant)
    context = tls_context(server_cert, server_key, ca.path)
    lander_cred = issue(ca, tmp_path, "lander@l2", "lander")
    owner_cred = issue(ca, tmp_path, "owner@example", "owner")
    stranger = issue(ca, tmp_path, "nobody@example", "nobody")
    home = tmp_path / "deploy"
    monkeypatch.setenv(registration.ENV, str(home))
    build = str(hz.st.docs[hz.st.path_of(cid) or ""].history[-1]["build"])
    report = {
        "run_id": "r-l2",
        "events": [
            {"kind": "dispatched", "card": cid, "run_id": "r-l2"},
            {"kind": "closed", "card": cid, "closure_id": "c1", "build_hash": build, "verdicts": {"S1": "pass"}},
        ],
        "suggestions": [{"kind": "docs", "title": "say how the lander lands", "body": "one call", "refs": []}],
    }
    report_file = tmp_path / "run.json"
    report_file.write_text(json.dumps(report), encoding="utf-8")

    async def body(port: int) -> None:
        address = f"https://127.0.0.1:{port}"
        client_file(home, "l2", address, ca.path, lander_cred)
        # the land, as the lander
        r = await asyncio.to_thread(lander.land, "l2", lander.read_report(report_file))
        # e1: the walk's `ratified` for the card (V3 — its fingerprint's birth), ahead of the report's e2, e3
        assert r["events"] == ["e1", "e2", "e3"] and r["intake"] == ["s1"] and r["landed"] is True and not r["empty"]
        assert hz.st.state["cards"][f"{cid:04d}"]["execution"] == "closed"
        assert hz.st.projection_of(cid).label.row == "closed"
        assert hz.st.inbox[-1]["by"] == "lander@l2" and hz.st.inbox[-1]["source"] == "run"
        assert len(service.seen) == 1
        # the owner's credential through the same client: the store's grant refuses, over the wire
        client_file(home, "l2", address, ca.path, owner_cred)
        r1 = await asyncio.to_thread(lambda: refuses("write.grant", lambda: lander.land("l2", report)))
        # the owner's matrix set is `*`; the sidecar's row is the refusal (L1 finding 5)
        assert "owner may not write state.json" in r1.detail and len(service.seen) == 2
        # a CA-issued subject the registration does not name: not a caller
        client_file(home, "l2", address, ca.path, stranger)
        await asyncio.to_thread(lambda: refuses("auth.unknown-client", lambda: lander.land("l2", report)))
        # a malformed report is refused at the terminal and opens no channel
        client_file(home, "l2", address, ca.path, lander_cred)
        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps({"run_id": "r", "events": [{"kind": "exploded", "card": cid}]}), encoding="utf-8")
        seen = len(service.seen)
        await asyncio.to_thread(lambda: refuses("event.kind", lambda: lander.land("l2", lander.read_report(bad))))
        assert len(service.seen) == seen, "a report the union refuses reached the store"

    serve(service, context, body)


def test_the_deploy_home_names_the_tenant_and_nothing_else(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`$ISIDIUM_DEPLOY/<tenant>/factory/client.toml`, and the three refusals around it: the home unset, a tenant with
    no client file, a name that is not a tenant (and would be a path)."""
    monkeypatch.delenv(registration.ENV, raising=False)
    refuses("factory.not-configured", lambda: registration.tenant_client("l2"))
    home = tmp_path / "deploy"
    monkeypatch.setenv(registration.ENV, str(home))
    ca = authority(tmp_path, "ca")
    cred = issue(ca, tmp_path, "lander@l2", "lander")
    p = client_file(home, "l2", "https://127.0.0.1:1", ca.path, cred)
    cfg, workdir = registration.tenant_client("l2")
    assert cfg.tenant == "l2" and cfg.address == "https://127.0.0.1:1" and workdir == p.parent
    refuses("factory.unknown-tenant", lambda: registration.tenant_client("other"))
    r = refuses("factory.tenant-name", lambda: registration.tenant_client("../l2"))
    assert r.path == "../l2"
    refuses("factory.tenant-name", lambda: registration.tenant_client("L2"))


def test_a_report_that_is_not_one_is_refused_at_the_terminal(tmp_path: Path) -> None:
    f = tmp_path / "r.json"
    f.write_text("[1]", encoding="utf-8")
    refuses("factory.report", lambda: lander.read_report(f))
    f.write_text("{not json", encoding="utf-8")
    refuses("factory.report", lambda: lander.read_report(f))
    refuses("factory.report", lambda: lander.read_report(tmp_path / "absent.json"))
    f.write_text(json.dumps({"run_id": "r", "events": [{"kind": "failed", "card": 1}]}), encoding="utf-8")
    r = refuses("event.shape", lambda: lander.read_report(f))
    assert r.path == "failed.class"
    f.write_text(json.dumps({"run_id": "r", "events": [], "suggestions": []}), encoding="utf-8")
    assert lander.read_report(f) == {"run_id": "r", "events": [], "suggestions": []}


def test_the_cli_verb_is_the_call_and_a_refusal_is_exit_2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from typer.testing import CliRunner

    from isidium.factory import cli as cli_mod

    f = tmp_path / "run.json"
    f.write_text(json.dumps({"run_id": "r-9", "events": [], "suggestions": []}), encoding="utf-8")
    sent: list[tuple[str, dict[str, Any]]] = []

    def fake(tenant: str, report: Any) -> dict[str, int]:
        sent.append((tenant, dict(report)))
        return {"ok": 1}

    monkeypatch.setattr(lander, "land", fake)  # the CLI reaches `land` through the module, at call time
    res = CliRunner().invoke(cli_mod.app, ["land", "--tenant", "l2", "--report", str(f)])
    assert res.exit_code == 0 and sent == [("l2", {"run_id": "r-9", "events": [], "suggestions": []})], res.output
    assert json.loads(res.output) == {"ok": 1}
    monkeypatch.delenv(registration.ENV, raising=False)
    monkeypatch.undo()
    monkeypatch.delenv(registration.ENV, raising=False)
    res = CliRunner().invoke(cli_mod.app, ["land", "--tenant", "l2", "--report", str(f)])
    assert res.exit_code == 2 and "factory.not-configured" in res.output, res.output
