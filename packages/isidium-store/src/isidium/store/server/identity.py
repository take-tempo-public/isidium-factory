"""Callers and grants (03 §1.12; 04 §2 ratified paragraph). The grant matrix is fixed in code for v1 but the check is
ONE function over a matrix VALUE shaped for isidium G7 to supply from policy later — the seam is structural."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, Literal

Grant = Literal["owner", "contributor", "lander"]
GRANTS: Final[tuple[Grant, ...]] = ("owner", "contributor", "lander")


@dataclass(frozen=True)
class Caller:
    """The authenticated principal (email-shaped, lower-cased, NFC — the store attests it on every journaled call),
    its grant, and the principal it acts on behalf of (`for`, PROV actedOnBehalfOf — the harness that injected the
    credential sets it).

    `credential` [K6, H-1] is the digest of the client certificate the channel presented — `sha256:<hex>` over the
    DER bytes as the peer sent them — and it is what the journal row records beside the principal, because after a
    rotation or a revocation the principal alone no longer says *which* certificate asserted it. `None` only for a
    caller that did not arrive over the channel: the realm's binding act, which its own key signs (`Store.bind`).
    Every caller `Service.caller_of` builds carries one."""

    principal: str
    grant: Grant
    on_behalf_of: str | None = None
    credential: str | None = None


# 03 §1.12 — what each grant may call. `write:signed` is the signature-requiring write (the predicate is write's);
# `ratify` is the non-dry sitting; `disposition` is "with the owner" — enforced by the interactive session (05 §2).
GRANT_MATRIX: Final[Mapping[str, frozenset[str]]] = {
    "owner": frozenset({"*"}),
    # `disposition` is NOT here: 05 §2 — *"'with the owner' is enforced mechanically, not by convention —
    # dispositions and the non-dry `ratify` exist only in the interactive session"*. The owner's credential is what
    # makes a session interactive, so the disposition call needs the `owner` grant: the planner composes it, the
    # owner makes it. Raising the suggestion stays the contributor's.
    "contributor": frozenset({"write", "suggest", "show", "accept", "check", "ratify:dry-run"}),
    # `show` beside `land`: reads are not restricted anywhere (03 §1.17, "restrict writes, never reads") and the
    # lander renders the board it lands. Stated here rather than left silent (the review's C7). `dispatch` [V3, F-a]:
    # the factory's pick reads — the pending-land precondition, the ready view, one card's check — as the lander.
    "lander": frozenset({"land", "show", "dispatch"}),
}
# The owner-only verbs are owner-only by ABSENCE here — `repair`, `disposition`, `config-policy` appear in no
# grant's set, so only `"*"` reaches them. They are named nowhere else: `repair` carried a hand-written
# `caller.grant != "owner"` until K1b-iii, which is the one shape this matrix cannot express and the realm cannot
# later override. If a verb needs an exception, it belongs in the matrix VALUE, never beside the call.
#
# **Recorded, not fixed here** [K1b-iii]: writes are gated at the `Store` layer (`Store._require`) and reads at the
# `Api` layer, so the authorization boundary is in two places. Not exploitable — reads are unrestricted by design
# (03 §1.17) — but a port transcribes the shape it finds, so it wants one home before the Rust port reads it.


def allowed(grant: str, call: str, matrix: Mapping[str, frozenset[str]] | None = None) -> bool:
    """`allowed(grant, call)` over a matrix value. v1 fixes the value in code; the G7 seam supplies `matrix` from
    policy later — same function, same call sites, a different value."""
    m = GRANT_MATRIX if matrix is None else matrix
    calls = m.get(grant)
    return calls is not None and ("*" in calls or call in calls)
