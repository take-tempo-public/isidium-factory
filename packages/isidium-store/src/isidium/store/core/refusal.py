"""One refusal type for the whole core — the `Result<_, RuleId>` of the Rust port.

Every rule the design names (`head.toml`, `canon.float`, `write.stale`, `log.rewritten`, `config.enum`, …) is raised or
collected as a `Refusal(rule, path, detail)`. Gates that must report *every* failure collect a `list[Refusal]`
(validate, config); the one writer raises the first (write). A gate of the first kind raises `ValidationRefusal`,
which keeps that list as **data** all the way to the caller (Q7).

A rule id is always `<namespace>.<name>` — never bare, never colon-separated (Q2b, ruled 2026-08-29).
`tests/unit/test_rule_ids.py` sweeps the package and fails the build on an id that is not, so C-12's disclosure
table has one key shape and the Rust port encodes one invariant instead of a set of exceptions.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from . import telemetry
from .disclosure import Disclosure, row_of


class Refusal(Exception):
    """A typed refusal. `rule` is the rule id; `path` the key path it fired on (empty at the top); `detail` one line."""

    __slots__ = ("detail", "path", "rule")

    def __init__(self, rule: str, path: str = "", detail: str = "") -> None:
        self.rule = rule
        self.path = path
        self.detail = detail
        super().__init__(self.render())

    def render(self) -> str:
        loc = f" @ {self.path}" if self.path else ""
        tail = f": {self.detail}" if self.detail else ""
        return f"{self.rule}{loc}{tail}"

    def __str__(self) -> str:
        return self.render()

    def __repr__(self) -> str:
        return f"Refusal({self.rule!r}, {self.path!r}, {self.detail!r})"

    def unidentified(self) -> dict[str, Any]:
        """The refusal as the value a peer the registration does **not** name receives [K7b, Q19, ruled 2026-09-06]:
        the rule id and nothing else, recorded on the running span and the counter like any refusal — and the
        detail put on the span as a bounded attribute, **never written as a row**.

        `payload()` above relocates a terse refusal's words into a log record, and that is right for a caller the
        registration names: the row is bounded by the registration. Before `caller_of` has named a principal the
        peer is a certificate this CA issued and nothing more — the container's healthcheck, a leaked probe
        certificate — and the K7 review measured a 6 KB request target written whole into a WARNING row by such a
        peer, twice per connection allowance, forever. The ruling draws the line at the registration: the two
        refusals reachable before it, `service.route` and the `auth.*` family, come through here."""
        telemetry.record_refusal(self.rule)
        telemetry.detail_on_span(self.detail)
        return {"rule": self.rule}

    def payload(self) -> dict[str, Any]:
        """The refusal as the value a caller receives, built in ONE place — **and filtered here** (C-12, K2b).

        A refusal reaches a caller through three doors — `Response.refusal` over HTTP, `McpServer._call` into a
        model's context, and the CLI — and each used to build its own dict. C-12's ruling is that the disclosure
        filter belongs on the constructor all three share, so it is here rather than on the HTTP response, where it
        would hold at one door and miss the one that writes into a model's context window.

        **Terse means the rule id and nothing else** — not an empty `path` and an empty `detail`, which would still
        say we had a path and a detail. `core/disclosure.py` decides which; the words that do not go are not
        discarded but relocated (`telemetry.withheld`), because trimming a response only relocates information if
        something catches it, and the log record is the one sink that runs with nothing configured at all.

        The refusal is also recorded on the running span here, for the same reason the filter is: this is the one
        place every door passes through, so no door has to remember (C-11)."""
        telemetry.record_refusal(self.rule)
        return self.disclosed()

    def disclosed(self) -> dict[str, Any]:
        """The filter alone, without recording an outcome. A `ValidationRefusal`'s verdicts are disclosed through
        this rather than through `payload()`: they are **parts of one refusal**, not refusals of their own, and
        recording each of them would overwrite the span's rule id with the last verdict's and count one call as
        N+1."""
        if row_of(self.rule).disclosure is Disclosure.TERSE:
            telemetry.withheld(self.rule, self.path, self.detail)
            return {"rule": self.rule}
        return {"rule": self.rule, "path": self.path, "detail": self.detail}


class ValidationRefusal(Refusal):
    """A gate that reports EVERY failure, carried whole — the typed verdicts stay a list.

    **The list is the truth; `detail` is only its rendering** [Q7, ruled 2026-08-29]. `detail` used to be the only
    thing that crossed the wire, so a caller — a language model — received the failed field names inside prose
    and had to parse them back apart, which is the shape C-2 forbids, and it lands exactly where C-12 is strongest:
    naming the field is what lets an agent self-correct instead of escalating. `Response.refusal` now sends
    `verdicts` beside the three existing fields and the client's `Transport` rebuilds this object from them.

    It lives here rather than beside its one raiser because both ends of the wire need it: the server raises it and
    the client reconstructs it, and neither should import the other's module to name the type.
    """

    __slots__ = ("verdicts",)

    def __init__(self, verdicts: Sequence[Refusal], path: str = "") -> None:
        self.verdicts = list(verdicts)
        super().__init__("validate.failed", path, "; ".join(str(r) for r in verdicts))

    def disclosed(self) -> dict[str, Any]:
        """The three fields, plus the verdicts as an array. **Additive** — a caller reading only
        `{rule, path, detail}` keeps working, and `detail` stays a rendered summary, so nothing has to parse it
        apart. **Each verdict is filtered by its own rule id** (C-12's row for the `verdicts` array): a terse verdict
        contributes its rule id and nothing more.

        **And `detail` is re-rendered from the disclosed verdicts, not read off `self.detail`.** `self.detail` is
        the whole rendering — every verdict's words, for the record and for the CLI, which is a human at their own
        terminal. Sending it here would carry a terse verdict's withheld sentence to the caller inside the
        aggregate's prose, past a filter that had just removed it from the verdict's own row: the array would say
        `{"rule": "git.failed"}` while the string beside it said what git's stderr was. Measured against the first
        version of this method, which did exactly that.

        An aggregate that is itself terse contributes no array at all — a terse wrapper shipping its own contents
        would disclose by the back door what its row said to withhold. `validate.failed` is `full`, so the branch is
        unexercised today; the filter must not have the other shape."""
        base = super().disclosed()
        if row_of(self.rule).disclosure is Disclosure.TERSE:
            return base
        disclosed = [v.disclosed() for v in self.verdicts]
        base["detail"] = "; ".join(_render(d) for d in disclosed)
        return {**base, "verdicts": disclosed}


def _render(disclosed: dict[str, Any]) -> str:
    """One disclosed verdict as the line it contributes to the aggregate's `detail` — the same shape `render()`
    produces, over the fields that survived the filter rather than over the fields the refusal was built with."""
    loc = f" @ {disclosed['path']}" if disclosed.get("path") else ""
    tail = f": {disclosed['detail']}" if disclosed.get("detail") else ""
    return f"{disclosed['rule']}{loc}{tail}"
