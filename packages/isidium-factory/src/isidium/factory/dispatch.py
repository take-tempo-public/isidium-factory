"""The pick — T-A6 as one function: the run record written before anything runs [V3, 2026-09-11].

T-A6's seven matching conditions, in order, each a typed refusal:

* **(a)** the store's precondition over the lander's channel — `dispatch.pending-land` fail-closed first — and the
  ready-view in the same answer (the projection's `ready`: the tenant's leaf, ratified, unguarded; Q-V6, Q-V11);
* **(b)** the WIP cap — `dispatch.wip` naming the runs in flight (the registration's `wip`, no code default);
* **(c)** the head of the ready-view under the ordering key (`ordering`), or `--card N` accepted **only if it is in
  the view** — `dispatch.not-ready` otherwise: the owner's *"run next"* is the head, never an override;
* **(d)** the chosen card re-read on the store: its live `check` clean (`dispatch.integrity`), its ratification
  landed (`dispatch.not-landed` — no fingerprint yet, ruled 2026-09-11: fail-closed like `pending-land`), and the
  software-grade refusal (03 §1.12, Q-V5): `dispatch.software-grade` unless the registration's
  `allow_software_grade_until` is today or later;
* **(e)** *sync*: `ctx.base_sha` **is** the synced head — the context fetched `base`; the rolling branch is V6's, so
  the story branch bases on `main` and `runs.batch` is null until then (finding 17: the gatherer is handed this sha);
* **(f)** the payload (T-B3) at `base_sha` — `payload.incomplete` / `payload.oversize` pass through as T-A6's
  *"back to the design queue"*, no row written — then its `refs_resolved` against the fingerprint's
  (`dispatch.ref-drifted` naming every path whose blob moved: 03 §9.5, *"dispatch re-checks it under the same name"*);
* **(g)** **the record first**: the ledger row and its `dispatched` event in one transaction, then the story branch
  `story/<run-id>` at `base_sha` (local). A branch failure after the record ends the run `failed:environment` and
  refuses `dispatch.environment` — the record tells the truth about what happened after it.

Nothing starts an executor: *"a running executor with the record id"* is V4's; V3 ends with the record, the branch
and the payload's hash in the row. `dry_run` answers (a)–(f) and writes nothing — the picker's answer without the
commitment, for a human at the terminal.
"""

from __future__ import annotations

import datetime as _dt
from collections.abc import Callable, Mapping
from typing import Any, Final, Protocol

from isidium.store.core import telemetry
from isidium.store.core.refusal import Refusal

from . import checkout, ordering
from . import payload as payload_mod
from .context import TenantContext
from .ledger import Ledger, NewRun
from .tenant import require

SPAN: Final = "isidium.factory.dispatch.pick"
Call = Callable[[str, Mapping[str, Any]], Any]


class Brancher(Protocol):
    """The one forge call the pick makes (`forge.Forge.branch`): a local ref, no push — the push is V4's."""

    def branch(self, name: str, at: str) -> None: ...


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.UTC)


def pick(
    ctx: TenantContext,
    ledger: Ledger,
    call: Call,
    forge: Brancher,
    *,
    card: int | None = None,
    dry_run: bool = False,
    now: Callable[[], _dt.datetime] = _now,
) -> dict[str, Any]:
    """One pick on one tenant; the run row back (or, dry, what it would be)."""
    with telemetry.span(SPAN, **{"isidium.tenant": ctx.tenant, "isidium.dry_run": dry_run}) as sp:
        try:
            out = _pick(ctx, ledger, call, forge, card, dry_run, now, sp)
        except Refusal as r:
            telemetry.record_refusal_on(sp, r.rule)
            raise
        telemetry.record_ok()
        return out


def _pick(
    ctx: TenantContext,
    ledger: Ledger,
    call: Call,
    forge: Brancher,
    card: int | None,
    dry_run: bool,
    now: Callable[[], _dt.datetime],
    sp: Any,
) -> dict[str, Any]:
    reg = require(ctx.registration, ctx.home)
    # (a) the store's precondition and the ready-view, one call
    view = call("dispatch", {})
    ready: dict[int, bool] = {int(r["id"]): bool(r["software_grade"]) for r in view["ready"]}
    # (b) the WIP cap
    flying = ledger.in_flight()
    if len(flying) >= reg.wip:
        names = ", ".join(f"{r['run_id']} (card {r['card']})" for r in flying)
        raise Refusal("dispatch.wip", names, f"{len(flying)} in flight, the cap is {reg.wip}")
    # (c) the ordering over the ready-view, from the cards' heads at base_sha — two spawns however many
    if card is not None and card not in ready:
        raise Refusal("dispatch.not-ready", str(card), "not in the ready-view; `--card` picks from it, never past it")
    if not ready:
        raise Refusal("dispatch.nothing-ready", "", "the ready-view is empty")
    docs = checkout.heads(ctx.checkout, ctx.base_sha, ctx.root, sorted(ready), ctx.registry)
    limit = int(ctx.eff["prioritization"]["expedite_limit"])
    ranked = ordering.order(
        [ordering.Head.of(cid, d) for cid, d in docs.items()], expedite_open=ordering.expedite_open(flying, limit)
    )
    chosen = next(r for r in ranked if card is None or r.card == card)
    sp.set_attribute("isidium.card", chosen.card)
    sp.set_attribute("isidium.rank", chosen.rank)
    # (d) the chosen card re-read on the store
    one = call("dispatch", {"card": chosen.card})
    if one["check"]["integrity"]:
        raise Refusal("dispatch.integrity", str(chosen.card), ", ".join(one["check"]["integrity"]))
    fp = one.get("fingerprint")
    if not fp:
        # A ratification newer than the land never gets here (the projection says `pending-ingest`); a `ready` card
        # with no fingerprint was ratified before `config@5` gave the land its `ratified` event — re-ratify it.
        raise Refusal(
            "dispatch.not-landed",
            str(chosen.card),
            "no fingerprint: its ratification landed before config@5 recorded refs_resolved — re-ratify, then land",
        )
    at = now()
    if ready[chosen.card] and not reg.allows_software_grade(at.date()):
        until = reg.allow_software_grade_until
        raise Refusal(
            "dispatch.software-grade",
            str(chosen.card),
            f"a software-grade ratification; allow_software_grade_until is {until.isoformat() if until else 'absent'}",
        )
    # (e) + (f) the payload at the synced head, then the drift check against the fingerprint
    inp = checkout.gather(
        ctx.checkout,
        ctx.base_sha,
        chosen.card,
        tenant=ctx.tenant,
        root=ctx.root,
        context_of=lambda cid: call("show", {"target": "neighborhood", "id": cid}),
        identity=payload_mod.Identity(ctx.identity.login, reg.adapter),
        caps=payload_mod.Caps(reg.max_bytes),
        registry=ctx.registry,
    )
    p = payload_mod.assemble(inp)
    drifted = _drifted(fp.get("refs_resolved", []), p.refs_resolved)
    if drifted:
        raise Refusal("dispatch.ref-drifted", drifted[0], "; ".join(drifted))
    run = NewRun(
        card=chosen.card,
        lane=ordering.EXPEDITE if chosen.expedite else "standard",
        build_hash=str(p.value["build_hash"]),
        base_sha=ctx.base_sha,
        adapter=reg.adapter,
        dispatched_at=at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        payload_hash=p.payload_hash,
        config_hash=p.config_hash,
        identity=ctx.identity.login,
        context=p.context,
        score=chosen.score(p.config_hash),
        refs_resolved=tuple(p.refs_resolved),
    )
    if dry_run:
        return {"dry_run": True, "card": run.card, "rank": chosen.rank, "base_sha": run.base_sha, **p.record()}
    # (g) the record first, then the branch
    run_id = ledger.dispatch(run)
    sp.set_attribute("isidium.run_id", run_id)
    branch = f"story/{run_id}"
    try:
        forge.branch(branch, ctx.base_sha)
    except Refusal as r:
        ledger.fail(run_id, now().strftime("%Y-%m-%dT%H:%M:%SZ"), "environment", f"{r.rule}: {r.detail}")
        raise Refusal("dispatch.environment", branch, f"{r.rule}: {r.detail}") from None
    row = ledger.run(run_id)
    assert row is not None
    return row


def _drifted(recorded: list[Mapping[str, str]], now: list[dict[str, str]]) -> list[str]:
    """Every path whose blob at `base_sha` is not the blob the ratification recorded — or that one side cites and
    the other does not — in the payload's written order, then the fingerprint's leftovers."""
    was = {str(r["path"]): str(r["blob"]) for r in recorded}
    is_ = {r["path"]: r["blob"] for r in now}
    out = [f"{p}: {was.get(p, 'absent')} -> {b}" for p, b in is_.items() if was.get(p) != b]
    out += [f"{p}: {b} -> absent" for p, b in was.items() if p not in is_]
    return out
