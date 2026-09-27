"""Card 14 — the dispatcher's WIP cap counts the cards the store holds in flight, so a parked card holds the line.

Found on 2026-09-24: the cap counted `ledger.in_flight()` alone, the runs with no end, and a parked run has ended on
the ledger — so while a card sat parked awaiting the owner's answer, the line could take another card, although the
board still counted it. This file exercises `Store.dispatch()`'s new `in_flight` answer (R1) and `_pick`'s union of
it with the ledger's own unended runs (R2/R3), plus the fail-closed refusal for a store whose answer cannot be
counted (R4).

**All five pick-level scenarios refuse at (a) or (b)** — before the ready-view's ordering, the card re-read, or the
payload are ever reached — so the checkout, the registry and `ctx.eff` are never read here: a `TenantContext` is
built as data, its `checkout` a bare `tmp_path` nothing ever touches, and the forge double raises if `branch` is
ever called. A completed pick over a real checkout is `test_v3.py`'s and `test_v5a.py`'s property, not this file's.

The store is the real thing (`..store.conftest.fresh`, the in-memory double), and the ledger is a real `Ledger` over
a fresh sqlite per test — both isolated per test function, so one test's in-flight state cannot leak into another's.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Any

import pytest

from isidium.factory import dispatch as dispatch_mod
from isidium.factory import ledger as ledger_mod
from isidium.factory.context import ForgeCoords, ForgeIdentity, ForgeKind, TenantContext, ToolkitPins
from isidium.factory.ledger import Ledger, NewRun
from isidium.factory.tenant import Registration
from isidium.store.client.config import ClientConfig
from isidium.store.core.refusal import Refusal
from isidium.store.registry.loader import Registry
from isidium.store.server.api import Api
from isidium.store.server.store import Store

from ..store.conftest import LANDER, OWNER, Harness, fresh

TENANT = "sartor"
ROOT = "docs/work/"
ADAPTER = "container"
LOGIN = "isdm-fac-lander[bot]"
AT = "2026-09-25T00:00:00Z"


def refuses(rule: str, fn: Any) -> Refusal:
    with pytest.raises(Refusal) as ei:
        fn()
    assert ei.value.rule == rule, str(ei.value)
    return ei.value


def ratified(hz: Harness, slug: str) -> int:
    cid = hz.draft(slug)
    hz.st.ratify([cid], OWNER)
    return cid


def new_run(cid: int) -> NewRun:
    return NewRun(
        card=cid,
        lane="standard",
        build_hash="sha256:" + "b" * 64,
        base_sha="c" * 40,
        adapter=ADAPTER,
        dispatched_at=AT,
        payload_hash="sha256:" + "d" * 64,
        config_hash="sha256:" + "e" * 64,
        identity=LOGIN,
    )


def base_ctx(tmp_path: Path) -> TenantContext:
    """A `TenantContext` as data: nothing here is read by a pick that refuses at (a)/(b), so `checkout` is a bare
    directory and the toolkit pins and `eff` are placeholders."""
    return TenantContext(
        tenant=TENANT,
        home=tmp_path,
        client=ClientConfig(tenant=TENANT),
        checkout=tmp_path,
        root=ROOT,
        base="main",
        base_sha="0" * 40,
        forge=ForgeCoords("github.com", "acme", "widgets", "origin"),
        identity=ForgeIdentity(ForgeKind.TOKEN, LOGIN, "isdm-fac-lander", "1+x@users.noreply.github.com", "tok"),
        toolkit=ToolkitPins("0.1.0", "0.1.0", "1", "sha1"),
        governed=(),
        registry=Registry.shipped(),
        registration=Registration(None, 1, ADAPTER, 1_000_000),
        eff={"prioritization": {"expedite_limit": 1}},
    )


def with_wip(ctx: TenantContext, wip: int) -> TenantContext:
    assert ctx.registration is not None
    return dataclasses.replace(ctx, registration=dataclasses.replace(ctx.registration, wip=wip))


class NoForge:
    """The pick's one forge call — never reached by a refusal at (a)/(b); a call here is the test's own bug."""

    def branch(self, name: str, at: str) -> None:
        raise AssertionError(f"the pick refused before branching, and yet asked to branch {name}")


def channel(
    st: Store, calls: list[str], patch: Callable[[dict[str, Any]], dict[str, Any]] | None = None
) -> dispatch_mod.Call:
    """The pick's one channel, over the real store's `Api` under the lander's grant — every call name recorded in
    order (C1's discriminator: one `dispatch` call, never a second), with an optional patch of the `dispatch` answer
    for S5's behind-store arm."""

    def call(name: str, args: Mapping[str, Any]) -> Any:
        calls.append(name)
        out = Api(st).call(name, LANDER, dict(args))
        if name == "dispatch" and patch is not None:
            out = patch(dict(out))
        return out

    return call


@pytest.fixture
def led(tmp_path: Path) -> Iterator[Ledger]:
    ledger = Ledger(tmp_path / "ledger.sqlite", TENANT)
    yield ledger
    ledger.close()


# ---- S1: the store names a parked card in flight -------------------------------------------------------------------


def test_the_store_names_a_parked_card_in_flight() -> None:
    hz = fresh()
    st = hz.st
    a, b = ratified(hz, "parked-card"), ratified(hz, "ready-card")
    st.land(
        {
            "run_id": "r-1",
            "events": [
                {"kind": "dispatched", "card": a, "run_id": "r-1"},
                {"kind": "parked", "card": a, "run_id": "r-1", "text": "which flow does this mean?"},
            ],
        },
        LANDER,
    )
    view = st.dispatch()
    assert view["in_flight"] == [{"card": a, "execution": "parked"}]
    assert view["ready"] == [{"id": b, "software_grade": True}], "the parked card is off the ready view too"


# ---- S2: a parked card holds the cap although its run has ended on the ledger ---------------------------------------


def test_a_parked_card_holds_the_cap(tmp_path: Path, led: Ledger) -> None:
    hz = fresh()
    st = hz.st
    a, _b = ratified(hz, "parked-card"), ratified(hz, "ready-card")
    st.land(
        {
            "run_id": "r-1",
            "events": [
                {"kind": "dispatched", "card": a, "run_id": "r-1"},
                {"kind": "parked", "card": a, "run_id": "r-1", "text": "which flow?"},
            ],
        },
        LANDER,
    )
    run_id = led.dispatch(new_run(a))
    led.end(run_id, AT, ledger_mod.PARKED)  # the ledger's own half has already ended
    before = led.runs()
    calls: list[str] = []
    ctx = with_wip(base_ctx(tmp_path), 1)
    r = refuses("dispatch.wip", lambda: dispatch_mod.pick(ctx, led, channel(st, calls), NoForge()))
    assert f"card {a} (parked)" in r.path and r.detail == "1 in flight, the cap is 1"
    assert calls == ["dispatch"], "one store call: the pick's own precondition read, and nothing past the cap"
    assert led.runs() == before, "the ledger is unchanged: no new row for a pick that never wrote one"


# ---- S3: a run counted by both halves is counted once ----------------------------------------------------------------


def test_a_run_counted_by_both_is_counted_once(tmp_path: Path, led: Ledger) -> None:
    hz = fresh()
    st = hz.st
    a, b = ratified(hz, "both-halves"), ratified(hz, "store-only-parked")
    st.land(
        {
            "run_id": "r-1",
            "events": [
                {"kind": "dispatched", "card": a, "run_id": "r-9"},
                {"kind": "dispatched", "card": b, "run_id": "r-2"},
                {"kind": "parked", "card": b, "run_id": "r-2", "text": "which flow?"},
            ],
        },
        LANDER,
    )
    run_id = led.dispatch(new_run(a))  # a's ledger run is still unended: the same card, both halves
    before = led.runs()
    calls: list[str] = []
    ctx = with_wip(base_ctx(tmp_path), 2)
    r = refuses("dispatch.wip", lambda: dispatch_mod.pick(ctx, led, channel(st, calls), NoForge()))
    assert r.detail == "2 in flight, the cap is 2"
    assert r.path.count(f"card {a} (") == 1, "the union counts card a once although both halves name it"
    assert f"card {a} ({run_id}, dispatched)" in r.path
    assert f"card {b} (parked)" in r.path
    assert calls == ["dispatch"] and led.runs() == before


# ---- S4: the refusal names each card and why -------------------------------------------------------------------------


def test_the_refusal_names_each_card_and_why(tmp_path: Path, led: Ledger) -> None:
    hz = fresh()
    st = hz.st
    ledger_only = ratified(hz, "ledger-only")
    store_only = ratified(hz, "store-only")
    both = ratified(hz, "both")
    st.land(
        {
            "run_id": "r-1",
            "events": [
                {"kind": "dispatched", "card": store_only, "run_id": "r-9"},
                {"kind": "parked", "card": store_only, "run_id": "r-9", "text": "which flow?"},
                {"kind": "dispatched", "card": both, "run_id": "r-3"},
            ],
        },
        LANDER,
    )
    r1 = led.dispatch(new_run(ledger_only))
    r2 = led.dispatch(new_run(both))
    calls: list[str] = []
    ctx = with_wip(base_ctx(tmp_path), 1)
    r = refuses("dispatch.wip", lambda: dispatch_mod.pick(ctx, led, channel(st, calls), NoForge()))
    assert r.detail == "3 in flight, the cap is 1"
    assert r.path == (f"card {ledger_only} ({r1}); card {store_only} (parked); card {both} ({r2}, dispatched)"), (
        "id order, each with why it counts: the run id, the execution, or both"
    )
    assert calls == ["dispatch"]


# ---- S5: a store behind is refused before the pick ---------------------------------------------------------------


def test_a_store_behind_is_refused_before_the_pick(tmp_path: Path, led: Ledger) -> None:
    hz = fresh()
    st = hz.st
    ratified(hz, "a")
    st.land({"run_id": "r-1", "events": []}, LANDER)

    def drop_in_flight(view: dict[str, Any]) -> dict[str, Any]:
        del view["in_flight"]
        return view

    calls: list[str] = []
    ctx = with_wip(base_ctx(tmp_path), 1)
    refuses("dispatch.store-behind", lambda: dispatch_mod.pick(ctx, led, channel(st, calls, drop_in_flight), NoForge()))
    assert calls == ["dispatch"] and led.runs() == []

    # a second arm: `in_flight: []` is a healthy, present answer — nothing behind about it. With a ledger run
    # already at the cap, the pick still refuses `dispatch.wip`, never `store-behind`.
    led.dispatch(new_run(1))
    calls.clear()
    refuses("dispatch.wip", lambda: dispatch_mod.pick(ctx, led, channel(st, calls), NoForge()))
    assert calls == ["dispatch"]
