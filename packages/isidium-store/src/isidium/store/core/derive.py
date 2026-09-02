"""`derive(before, after, ref) -> Result<Entry, RuleId>` — the one function at every gate (03 §1.2 step 3): the diff
`D`, the append-only rules (`log.rewritten`, `claims.rewritten`), `questions.dropped-unanswered` (bound to cards
with a prior signed entry, 1.11), a deletion (F8), then the recompute table for `act` and `fields`. `write` runs it
and refuses on Err; CI and ingest run it and report an Err as `integrity:tampered` (1.15, 9.5).

Also here: the signature predicate over (before, after) (1.2 step 4, W3) with its two draft-6 pins — the
contributor's retraction exemption and the owner's caller-aware clause — and the status replay of 1.5 row 3.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, Literal

from . import canon
from .chain import is_signed
from .grammar import Document
from .refusal import Refusal

Act = Literal[
    "created",
    "amended",
    "ratified",
    "demoted",
    "held",
    "released",
    "closed",
    "accepted",
    "reopened",
    "retracted",
    "answered",
    "summarized",
    "noted",
    "withdrawn",
    "unwithdrawn",
    "repaired",
    "config-policy",
    "batch-manifest",
    "binding",
]
ACTS: Final[tuple[Act, ...]] = (
    "created",
    "amended",
    "ratified",
    "demoted",
    "held",
    "released",
    "closed",
    "accepted",
    "reopened",
    "retracted",
    "answered",
    "summarized",
    "noted",
    "withdrawn",
    "unwithdrawn",
    "repaired",
    "config-policy",
    "batch-manifest",
    "binding",
)
POLICY_ACTS: Final[frozenset[str]] = frozenset({"config-policy", "batch-manifest", "binding"})
# 1.2 step 4: the caller-aware clause — the caller holds `owner` and the diff moves status to closed/withdrawn ⇒ sign.
OWNER_SIGNS_ALSO: Final[frozenset[str]] = frozenset({"closed", "withdrawn"})

# `ref` as the typed act payload (1.15): a closure `"c<n>:sha256:…"` (str) · `RestartFrom(seq)` (int) ·
# `Members(H)` (list[str]) · `Binding{…}` (mapping) · absent (None). The Rust port's enum.
Ref = str | int | list[str] | Mapping[str, Any] | None


@dataclass(frozen=True)
class Derived:
    act: Act
    fields: list[str]
    diff: list[str]


def head_diff(before: Mapping[str, Any] | None, after: Mapping[str, Any]) -> list[str]:
    """`D` over the head: the keys whose canonical value changed (added / removed / changed), sorted. Canonical, so
    an NFD → NFC retype is no change (1.2 step 3)."""
    if before is None:
        return sorted(after)
    out: list[str] = []
    for k in set(before) | set(after):
        if (k in before) != (k in after) or canon.canon_head_value(k, before[k]) != canon.canon_head_value(k, after[k]):
            out.append(k)
    return sorted(out)


def diff_sets(before: Document | None, after: Document) -> list[str]:
    """`D` = the head keys whose canonical value changed + each section (by its lower-cased name) that changed."""
    d = head_diff(before.head if before else None, after.head)
    if before is None:
        return sorted(d + [s.lower() for s in after.sections])
    for s in set(before.sections) | set(after.sections):
        b, a = before.sections.get(s), after.sections.get(s)
        if isinstance(a, str) or isinstance(b, str):
            bs = canon.canon_prose(b) if isinstance(b, str) else None
            as_ = canon.canon_prose(a) if isinstance(a, str) else None
            if as_ != bs:
                d.append(s.lower())
        elif a != b:
            d.append(s.lower())
    return sorted(d)


def _unsafe(h: Any) -> bool:
    return isinstance(h, Mapping) and h.get("kind") in ("blocked", "deferred")


def recompute_table(
    before: Mapping[str, Any] | None, after: Mapping[str, Any], d: list[str], ref: Ref, is_policy: bool = False
) -> tuple[Act, list[str]]:
    """The recompute table, first match (1.2)."""
    if is_policy:
        if before is None:
            return "created", d  # K-1: the first write of config.toml opens the policy chain as `created`
        if isinstance(ref, list):
            return "batch-manifest", []
        if isinstance(ref, Mapping):
            return "binding", []
        return "config-policy", d
    if before is None:
        return "created", d
    bs, as_ = before.get("status"), after.get("status")
    if bs == "draft" and as_ == "ratified":
        return "ratified", d
    if bs == "ratified" and as_ == "ratified" and set(d) & canon.GATED_KEYS:
        return "ratified", d  # re-ratification (W2)
    if bs == "ratified" and as_ == "draft":
        return "demoted", d
    if as_ == "withdrawn" and bs != "withdrawn":
        return "withdrawn", d
    if bs == "withdrawn" and as_ == "ratified":
        return "unwithdrawn", d
    bc, ac = list(before.get("closures", [])), list(after.get("closures", []))
    if len(ac) > len(bc):
        return "closed", d
    if bc and ac and not bc[-1].get("retracted") and ac[-1].get("retracted"):
        return "retracted", d
    if len(after.get("reopens", [])) > len(before.get("reopens", [])):
        return "reopened", d
    bh, ah = before.get("hold"), after.get("hold")
    if ah is not None and (bh is None or (ah.get("kind") != bh.get("kind") and _unsafe(ah))):
        return "held", d  # added, or re-kinded toward blocked/deferred (blocked ↔ deferred is `held`, unsigned)
    if bh is not None and (ah is None or (ah.get("kind") != bh.get("kind") and not _unsafe(ah))):
        return "released", d  # removed, or re-kinded toward watching
    if len(after.get("questions", [])) < len(before.get("questions", [])) and len(after.get("answers", [])) > len(
        before.get("answers", [])
    ):
        return "answered", d
    if d == ["summary"]:
        return "summarized", ["summary"]
    if d == ["updates"]:
        return "noted", ["updates"]
    if isinstance(ref, str) and d == []:
        return "accepted", []
    if isinstance(ref, int) and not isinstance(ref, bool):
        return "repaired", ["history"]
    return "amended", d


def append_only_check(before: Document, after: Document) -> None:
    """1.7 / 9.2: the append-only rules, once, inside derive, on every structured call — no same-day amend allowance.
    Updates / History / `see` / `renumbered_from` → `log.rewritten`; closures (the retraction flip carved out, H5) and
    reopens → `claims.rewritten`."""
    bu, au = before.updates(), after.updates()
    for i, b in enumerate(bu):
        if i >= len(au) or au[i] != b:
            raise Refusal("log.rewritten", "updates")
    b_see = list(before.head.get("see", []))
    if list(after.head.get("see", []))[: len(b_see)] != b_see:
        raise Refusal("log.rewritten", "see")
    if "renumbered_from" in before.head and before.head["renumbered_from"] != after.head.get("renumbered_from"):
        raise Refusal("log.rewritten", "renumbered_from")
    bc, ac = list(before.head.get("closures", [])), list(after.head.get("closures", []))
    for i, b in enumerate(bc):
        a = ac[i] if i < len(ac) else None
        if a != b and not (i == len(bc) - 1 and {**b, "retracted": True} == a):
            raise Refusal("claims.rewritten", "closures")
    br, ar = list(before.head.get("reopens", [])), list(after.head.get("reopens", []))
    if ar[: len(br)] != br:
        raise Refusal("claims.rewritten", "reopens")


def questions_dropped_unanswered(before: Mapping[str, Any], after: Mapping[str, Any]) -> list[str]:
    """1.11: every removed questions[].id must appear in an added answers[].question_id."""
    bq = {q["id"] for q in before.get("questions", [])}
    aq = {q["id"] for q in after.get("questions", [])}
    ba = {a["question_id"] for a in before.get("answers", [])}
    aa = {a["question_id"] for a in after.get("answers", [])}
    return sorted(bq - aq - (aa - ba))


CLOSURE_REF: Final = re.compile(r"^([co][1-9][0-9]*):sha256:([0-9a-f]{64})$")
RELATION_KEYS: Final[frozenset[str]] = frozenset({"parent", "depends_on", "sprint", "milestone", "goal"})


def parse_closure_ref(ref: Ref) -> tuple[str, str] | None:
    """`Closure{id, hash}` from its written form `"c<n>:sha256:<hex>"` / `"o<n>:sha256:<hex>"`; None when `ref` is
    not that shape (the Rust enum's parser at the boundary)."""
    if not isinstance(ref, str):
        return None
    m = CLOSURE_REF.match(ref)
    return (m.group(1), m.group(2)) if m else None


def status_moved_to(before: Mapping[str, Any] | None, after: Mapping[str, Any], targets: frozenset[str]) -> bool:
    """1.2 step 4, the caller-aware clause's condition: the diff MOVES `status` into `targets`."""
    return before is not None and before.get("status") != after.get("status") and after.get("status") in targets


def derive(before: Document | None, after: Document | None, ref: Ref, diff: list[str] | None = None) -> Derived:
    """The one derive function. Raises `Refusal` (the Err): `write.deletion`, `log.rewritten`, `claims.rewritten`,
    `questions.dropped-unanswered`. `diff` may be supplied when the caller already computed it (1.2 step 1: the
    diff is taken first so the rules can be keyed to it)."""
    if after is None:
        raise Refusal("write.deletion", "", "card files are never deleted (F8)")
    d = diff_sets(before, after) if diff is None else list(diff)
    if before is not None:
        append_only_check(before, after)
        if any(is_signed(e) for e in before.history):
            dropped = questions_dropped_unanswered(before.head, after.head)
            if dropped:
                raise Refusal("questions.dropped-unanswered", "questions", ",".join(dropped))
    act, fields = recompute_table(before.head if before else None, after.head, d, ref)
    return Derived(act, fields, d)


def only_retraction(before: Mapping[str, Any], after: Mapping[str, Any]) -> bool:
    """The contributor's retraction (1.2 step 4 / 1.5): the only claims change is `closures[-1].retracted:
    false → true`, and no `reopens[]` entry was added."""
    bc, ac = list(before.get("closures", [])), list(after.get("closures", []))
    return (
        bool(bc)
        and len(ac) == len(bc)
        and ac[:-1] == bc[:-1]
        and not bc[-1].get("retracted")
        and ac[-1] == {**bc[-1], "retracted": True}
        and len(after.get("reopens", [])) == len(before.get("reopens", []))
    )


def needs_signature(
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any],
    d: Sequence[str],
    ref: Ref,
    is_policy: bool = False,
    landed_closures: frozenset[str] = frozenset(),
) -> str | None:
    """The signature predicate over (before, after) (1.2 step 4, W3) — the reason, or None. `landed_closures`: the
    closure ids the sidecar has landed for this card (C6: "not yet landed" = the closure's entry post-dates the
    landed history head — the caller computes the set)."""
    if is_policy:
        return "policy"
    if isinstance(ref, int) and not isinstance(ref, bool):
        return "repair"
    if before is None:
        return "born-ratified" if after.get("status") == "ratified" else None
    bs, as_ = before.get("status"), after.get("status")
    if bs == "ratified" and _unsafe(before.get("hold")):
        ah = after.get("hold")
        if ah is None or ah.get("kind") == "watching":
            return "hold-release"
    gated_touched = bool(set(d) & canon.GATED_KEYS)
    # C5/C6: the "more active" clause exempts a contributor's retraction — closed → ratified whose only claims change
    # is the retraction flip on a closure not yet landed, no reopens[] entry, and no gated key in D.
    if (
        bs == "closed"
        and as_ == "ratified"
        and only_retraction(before, after)
        and after["closures"][-1]["id"] not in landed_closures
        and not gated_touched
    ):
        return None
    if as_ == "ratified" and bs in ("draft", "closed", "withdrawn"):
        return "more-active"
    if bs == "ratified" and gated_touched:
        return "gated-on-ratified"
    if isinstance(ref, str) and list(d) == []:
        return "accept"
    return None


def replay_status(history: Sequence[Mapping[str, Any]]) -> str:
    """1.5 row 3: "the card was a draft (replay of the status acts before it)" — the status after these entries."""
    st = "draft"
    for e in history:
        act = e.get("act")
        st = {
            "ratified": "ratified",
            "unwithdrawn": "ratified",
            "reopened": "ratified",
            "retracted": "ratified",
            "demoted": "draft",
            "closed": "closed",
            "withdrawn": "withdrawn",
        }.get(str(act), st)
        if act == "created" and is_signed(e):
            st = "ratified"
    return st
