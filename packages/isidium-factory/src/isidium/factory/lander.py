"""The lander client (03b §2; 05 §1; T-A10) — the factory's one card-adjacent write, made over the wire [L2].

The lander is *"the factory's service identity"*, deterministic, no model call: it reads a run report, refuses at its
own terminal what the store would refuse (the report against the event union — the same pre-flight idea as the store
client's ref check: no channel is opened for a call that is not going to be made), and makes **one** call, `land`,
as the credential its tenant's `client.toml` names. What the store does with it is the store's (`Store.land`, L1);
what comes back is the store's result, unchanged.

In v1b the report is synthetic — a file the owner hands `isidium factory land`. The line that produces one (dispatch,
the execution adapters, T-C6's contract) is v1c's; this module is where it will hand it in.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

from isidium.store.client.transport import Transport
from isidium.store.core import events as events_mod
from isidium.store.core import telemetry
from isidium.store.core.refusal import Refusal

from .registration import tenant_client

if TYPE_CHECKING:
    from .ledger import Ledger

Call = Callable[[str, Mapping[str, Any]], Any]


def read_report(path: Path) -> dict[str, Any]:
    """The report file as the call's arguments, refused here — before any channel — when it is not a JSON object or
    its events are not the union's. The store parses it again at its door; the two agree by construction (one
    parser), and the first saves the round trip."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise Refusal("factory.report", str(path), str(e)) from None
    if not isinstance(raw, dict):
        raise Refusal("factory.report", str(path), "a JSON object with run_id, events and suggestions")
    events_mod.parse_report(raw)
    return raw


def land(tenant: str, report: Mapping[str, Any]) -> Any:
    """One call, as the tenant's lander: the store's `land` result, verbatim."""
    cfg, workdir = tenant_client(tenant)
    return Transport(cfg, workdir).call("land", report)


def land_run(ledger: Ledger, call: Call, run_id: str) -> dict[str, Any]:
    """The run report generated from the ledger, landed **once** [V5a]: the run's store events past its watermark, one
    `land` call, and the watermark advanced only after the store answered.

    **Once is the ledger's, because it cannot be the store's**: `Store.land` has no run-id idempotence — a repeated
    report with events appends them again — so a report is never re-sent for events the store already holds. The
    other order is the one that fails safe: a land that answered and a ledger write that did not re-sends next time
    (declared; one process writes a tenant's ledger). A refused land is answered here, not raised: the run's end is
    already on its row, and what did not reach the store is carried by the next land of this run."""
    report, through = ledger.unlanded(run_id)
    if through is None:
        return {"sent": 0}
    try:
        result = call("land", report.model_dump(by_alias=True, exclude_none=True))
    except Refusal as r:
        telemetry.record_refusal(r.rule)
        return {"sent": 0, "refused": r.rule, "detail": r.detail}
    ledger.landed(run_id, through)
    return {"sent": len(report.events), **dict(result)}
