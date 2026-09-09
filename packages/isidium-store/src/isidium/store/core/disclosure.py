"""**One table, two facts about a rule id: the status it carries and how much of itself it discloses** (C-12, and
Q2/Q2a/Q2b ruled 2026-08-29).

A rule id's HTTP status and its disclosure are two facts about one thing; kept in two maps they drift (C-4), so they
are one row here. `server/service.py` reads the status off it and `core/refusal.py` reads the disclosure off it, and
neither holds a second copy.

**Keyed by namespace, with named rule ids overriding their namespace's default** [Q2]. A flat rule-id table with a
terse default would need roughly 120 explicit `full` rows — the safe answer would be the rare one and the table would
need auditing by eye forever. Disclosure is aligned with the namespaces almost perfectly: every validation family is
`full`, every `auth.*` and `signer.*` id is terse, and `service` is the only namespace that splits, because C-12 split
it. In the Rust port a `Namespace` enum makes the exhaustiveness below a **compiler** check rather than a test.

**A new rule id inherits its namespace's disclosure, except where the namespace says otherwise** [Q2a]. The validation
families inherit `full` freely: a new rule there is a new field check, and requiring a row would make a forgotten row
go **terse** — handing an agent a bare rule id it cannot self-correct from, which is the hazard C-12 exists to
prevent. The `declare` flag is set on the `full` namespaces that live in *server* code — `write`, `show`, `governed`,
`api` — where a new id could plausibly name something internal. There, a new id is a **build failure** until it is
classified (`tests/unit/test_rule_ids.py`).

**A namespace the code can raise and this table does not name is a build failure, not a fall-through** — again the
sweep. At *runtime* an unclassified id falls to `UNCLASSIFIED`, which discloses nothing: forgetting must be safe
(C-12, "the default is terse").

**Every status here is the status that id carries today.** This chunk classifies disclosure; it does not re-price the
statuses, because a status is a channel the clients' retry logic reads (C-12) and changing one is a wire change no
ruling asked for. Where today's status looks wrong the row says so and the finding is in the chunk plan, unfixed:
`api.not-yet` and `write.lander-only` and `show.unsupported-target` all answer 422 where 404 / 403 / 404 would read
better, and a fault in the store's own git answers 422 where 500 would.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Final


class Disclosure(Enum):
    """How much of a refusal reaches the caller — a typed value with one meaning, never a formatted string (C-2).

    `TERSE`: the rule id and nothing else. `FULL`: the rule id, the key path it fired on, and the detail — every word
    of which we wrote ourselves (C-12: "we ship no words we did not write")."""

    TERSE = "terse"
    FULL = "full"


@dataclass(frozen=True)
class Row:
    """One classification. `declare` means *a new rule id in this namespace must have its own row here* — it is set
    on a namespace, and is meaningless on a per-id override."""

    status: int
    disclosure: Disclosure
    declare: bool = False


TERSE: Final = Disclosure.TERSE
FULL: Final = Disclosure.FULL

# What an id the table does not classify gets: nothing but its rule id, and the fall-through status the service has
# always used. Reaching this at runtime means the sweep has been disabled, so it fails closed.
UNCLASSIFIED: Final = Row(422, TERSE)

# The validation surface answers 422 and discloses fully: naming the failed field is what lets an agent self-correct
# instead of escalating to the owner, which is the reason C-12 protects this set rather than trimming it.
_VALIDATION: Final = Row(422, FULL)


NAMESPACES: Final[Mapping[str, Row]] = MappingProxyType(
    {
        # ---- the caller's own request: the protected set (C-12) --------------------------------------------------
        "body": _VALIDATION,  # the governed document's sections and history block
        "canon": _VALIDATION,  # canonicalisation: floats, codepoints, set shapes
        "claims": _VALIDATION,  # a claim rewritten between entries
        "config": _VALIDATION,  # `config.toml` against `config@1`
        "dispatch": _VALIDATION,  # a dispatch refused for the card's own state
        "event": _VALIDATION,  # a run report's event against the union: its kind, its members (L1)
        "land": _VALIDATION,  # the land's own preconditions: the report's shape, the landed copy's readability (L1)
        "emit": _VALIDATION,
        "ext-schema": _VALIDATION,  # a tenant Ext schema colliding with a core key
        "head": _VALIDATION,  # the TOML head: fences, ordering, typing
        "id": _VALIDATION,  # the card id they wrote against
        "inbox": _VALIDATION,  # an inbox row's own fields
        "init": _VALIDATION,  # the repository they asked to initialise
        "integrity": _VALIDATION,  # their card's chain: timestamps out of order (Q2b renamed this id)
        "log": _VALIDATION,  # a history entry rewritten
        "profile": _VALIDATION,  # the per-kind profiles — 28 ids and every one a field check
        "questions": _VALIDATION,
        "ratify": _VALIDATION,  # the ids and paths they asked to ratify
        "record": _VALIDATION,
        "ref": _VALIDATION,  # `refs` grammar and resolution
        "relation": _VALIDATION,  # parent/depends_on cycles and ladders
        "repair": _VALIDATION,  # the repair target they named
        "scenario": _VALIDATION,  # the acceptance scenarios' own shapes
        "sig": _VALIDATION,  # a signature's algorithm, format and key bytes — theirs, not ours
        "status": _VALIDATION,  # a forbidden status transition
        "surfaces": _VALIDATION,  # a surface intersecting the tracking root or the deny set
        "validate": _VALIDATION,  # the aggregate: `validate.failed` carries the verdicts as data (Q7)
        "hook": _VALIDATION,  # client-side only: the pre-commit hook, refusing to a human at their own terminal
        "accept": _VALIDATION,  # client-side only: `accept` at the owner's terminal — its label, block and runs (L3)
        # ---- about us: terse (C-12 rule 2) ------------------------------------------------------------------------
        # Before the caller is identified, a refusal carries its rule id and nothing else. `auth` is that surface
        # exactly: no certificate, a certificate that will not parse, a certificate the registration does not name.
        "auth": Row(401, TERSE),
        # The signer's internals — which backend, what skew, whose socket. The status already says whether to retry.
        "signer": Row(503, TERSE),
        # git's own stderr is our subprocess talking, not the caller's request.
        "git": Row(422, TERSE),
        # our installed registry's state: which schema documents we hold and whether they match their bytes.
        # **K1d's two new ids inherit this deliberately.** `registry.filename` and `registry.filename-mismatch`
        # both carry a FILESYSTEM PATH as their `path` — the store's own package directory server-side, a
        # checkout's `.isidium/schemas` client-side — and neither is the caller's to fix: the store's registry
        # is ours, and a client that hits one is at its own terminal, where the CLI prints the whole refusal
        # anyway. The withheld words are relocated rather than lost (`telemetry.withheld`, C-12).
        "registry": Row(422, TERSE),
        # client-side only (`client/config.py`, `client/transport.py`): these never cross a door. They are here
        # because the sweep requires every namespace the code can raise to be classified, and terse is what an id
        # about our own configuration would get if one ever did.
        "client": Row(422, TERSE),
        # the factory's client (`isidium.factory`, L2): the deploy home, a tenant's client file, a report file at the
        # operator's own terminal — the same posture as `client`, and swept from the second package.
        "factory": Row(422, TERSE),
        # Raised by a tool, not by the package [K10, Q21, ruled 2026-09-06: *"Sweep reads tools, unclassified
        # fails"*]: `tools/verify_chain.py` refuses a shallow checkout (`verify.shallow`, K7a). A tool speaks to the
        # operator at the forge and at the terminal and never to a peer, so C-12's reason for *terse* does not reach
        # it and its words flow; the sweep reads `tools/` so a second tool id is classified or fails the build. The
        # status is nominal — a tool answers an exit code, never HTTP — and is the fall-through's, for the row to
        # carry one.
        "verify": Row(422, FULL),
        # The protocol edge. **The one namespace that splits** — C-12 split it, which is why a namespace-only table
        # could not express the ruling it exists to implement. Terse by default because every id in it fires before
        # the caller is identified and the rule id already carries the whole meaning; the two that are about the
        # caller's own request (`service.arguments`, `service.body`) override to `full` below.
        "service": Row(400, TERSE),
        # ---- about them, and in server code: full, and a new id must be declared (Q2a) ---------------------------
        "write": Row(403, FULL, declare=True),
        "show": Row(404, FULL, declare=True),
        "governed": Row(404, FULL, declare=True),
        "api": Row(404, FULL, declare=True),
    }
)


RULES: Final[Mapping[str, Row]] = MappingProxyType(
    {
        # ---- `auth` ------------------------------------------------------------------------------------------------
        # The certificate parsed and the registration does not name it: still pre-identification, and still terse —
        # we do not echo the subject back. Only the status differs from the namespace.
        "auth.unknown-client": Row(403, TERSE),
        # ---- `service`: the split C-12 made ------------------------------------------------------------------------
        "service.route": Row(404, TERSE),
        # h11's framing failures. **One status, 400, and h11's `error_status_hint` is not consulted.** The hint has
        # two non-400 values: 431 (receive buffer too long), which our own header cap refuses first — the edge never
        # feeds h11 past `max_header_bytes` while the head is unfinished (K1b-ii) — and 501 (multiple or unsupported
        # `Transfer-Encoding`), for a request the store refuses at 400 the moment it carries *one* such header. So
        # the collapse makes the answer to "any transfer-encoding at all" uniform rather than losing a distinction.
        "service.malformed": Row(400, TERSE),
        "service.transfer-encoding": Row(400, TERSE),
        "service.body-too-large": Row(413, TERSE),
        "service.headers-too-large": Row(431, TERSE),
        "service.length-required": Row(411, TERSE),
        "service.too-many-connections": Row(429, TERSE),
        # A bug in us. The exception's own words are the record's (C-12); the caller gets a rule id (C-5).
        "service.internal": Row(500, TERSE),
        # **Authored, then full** (C-12). The words are ours — the exception's own text goes to the record and never
        # to the caller — and what is left is about *their* request, so it flows.
        "service.arguments": Row(400, FULL),
        "service.body": Row(422, FULL),
        # ---- the four `declare` namespaces: every id spelled, because a new one must be ---------------------------
        "write.grant": Row(403, FULL),
        "write.requires-owner": Row(403, FULL),
        "write.stale": Row(409, FULL),  # fetch a fresh base and retry — the status is the channel
        "write.locked": Row(409, FULL),
        "write.no-change": Row(422, FULL),
        "write.deletion": Row(422, FULL),
        "write.repair-via-repair": Row(422, FULL),
        "show.unknown": Row(404, FULL),
        "show.unsupported-target": Row(422, FULL),
        "governed.unknown-path": Row(404, FULL),
        "api.unknown-call": Row(404, FULL),
    }
)

# The namespaces whose ids must each be declared above. Derived, never written twice (C-4).
DECLARED: Final[frozenset[str]] = frozenset(ns for ns, row in NAMESPACES.items() if row.declare)


def namespace_of(rule: str) -> str:
    """The first segment — the key this table is built on. A rule id is always `<namespace>.<name>` (C-5, Q2b), and
    `tests/unit/test_rule_ids.py` fails the build on one that is not."""
    return rule.split(".", 1)[0]


def row_of(rule: str) -> Row:
    """The id's own row when it has one, else its namespace's, else `UNCLASSIFIED` — which discloses nothing."""
    named = RULES.get(rule)
    if named is not None:
        return named
    return NAMESPACES.get(namespace_of(rule), UNCLASSIFIED)


def status_of(rule: str) -> int:
    return row_of(rule).status
