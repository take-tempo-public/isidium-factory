"""The card profile validator — 03 §3 (profiles), §1.11 (shapes and their layer rules), §1.7 (class membership),
§1.8 (kinds, relations, holds), §1.14 (surfaces vs the tracking root and the deny set — 7be.2). Verdicts are typed
per rule id (`profile.story.acceptance`-style, one dotted regime), collected — never raised — so the dry run can
show every cell. Descends from the r6 prototype's validate.py, made policy-driven (the effective config)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from ..core import canon
from ..core.refusal import Refusal
from . import config as cfg

STATUSES: Final = ("draft", "ratified", "closed", "withdrawn")
KINDS: Final = ("story", "epic", "sprint", "milestone")
SHAPES: Final = cfg.SHAPE_CORE
SCENARIO_KINDS: Final = ("test-marker", "command", "http", "file-assert", "manual-evidence")
RUNNABLE_KINDS: Final = frozenset(SCENARIO_KINDS[:4])
HOLD_KINDS: Final = ("blocked", "deferred", "watching")
HOLD_ON: Final = ("owner", "card", "legacy", "text")
ORIGIN: Final = frozenset(cfg.ORIGIN_CORE)
_EARS: Final = re.compile(
    r"^(?:The (?P<s1>.+?) shall .+|While .+?, the (?P<s2>.+?) shall .+|When .+?, the (?P<s3>.+?) shall .+"
    r"|Where .+?, the (?P<s4>.+?) shall .+|If .+?, then the (?P<s5>.+?) shall .+)\.?$"
)
_ID_RULE: Final = re.compile(r"^R[1-9][0-9]*$")
_ID_Q: Final = re.compile(r"^Q[1-9][0-9]*$")
_ID_S: Final = re.compile(r"^S[1-9][0-9]*$")


@dataclass(frozen=True)
class CardPolicy:
    """What the validator reads from the effective config (04). **No key here carries a default value**: every
    default lives in the adopted schema version and reaches this object through the resolver (04 §4.1, Y1 —
    *"never over the binary's built-ins"*). A second copy in code would be invisible to a deterministic reader of
    the schema documents, so `tests/unit/test_no_code_defaults.py` fails the build if one appears."""

    shapes_allowed: tuple[str, ...]
    shapes_default: str
    kind_default: str
    ladder_levels: tuple[str, ...]
    card_sources: frozenset[str]
    inbox_sources: frozenset[str]
    effort_tiers: tuple[str, ...]
    root: str
    deny: tuple[str, ...]
    weak_words: tuple[str, ...]
    profiles_enabled: frozenset[str]
    gated_x: frozenset[str]

    @classmethod
    def from_effective(cls, eff: Mapping[str, Any], card_defaults: Mapping[str, Any]) -> CardPolicy:
        """The effective config is already the tenant's file over the adopted schema's defaults, so every key below is
        present; a missing key means the caller skipped the resolver, which is a bug, not a default. `card_defaults`
        is `card@1`'s own default tree — the card's `kind` default is the card schema's, not the config's."""
        shapes = eff["shapes"]
        origin = eff["origin"]
        ext = eff.get("extensions") or {}
        return cls(
            shapes_allowed=tuple(shapes["allowed"]),
            shapes_default=str(shapes["default"]),
            kind_default=str(card_defaults["kind"]),
            ladder_levels=tuple(eff["ladder"]["levels"]),
            card_sources=frozenset(origin["card"]),
            inbox_sources=frozenset(origin["inbox"]),
            effort_tiers=tuple(eff["effort"]["tiers"]),
            root=str(eff["root"]),
            deny=tuple(eff["surfaces"]["deny"]),
            weak_words=tuple(shapes.get("ears", {}).get("weak_words", ())),
            profiles_enabled=frozenset(eff["profiles"]["enabled"]),
            gated_x=frozenset(
                canon.nfc(k) for k, v in ext.items() if isinstance(v, Mapping) and v.get("class") == "gated"
            ),
        )


def _r(v: list[Refusal], rule: str, path: str = "", detail: str = "") -> None:
    v.append(Refusal(rule, path, detail))


def glob_may_reach(surface: str, target: str) -> bool:
    """A conservative reachability test between a `surfaces` glob (gitwildmatch) and a protected path prefix: true
    when the glob's literal prefix lies under the target, the target lies under the glob's literal prefix, or a
    wildcard segment could span into it. Used for the tracking root and the deny set (1.14) — refuse on doubt."""
    s = surface.lstrip("/")
    t = target.lstrip("/")
    lit = re.split(r"[*?\[]", s, maxsplit=1)[0]
    if s.startswith("**") or lit == "":
        return True
    t_dir = t if t.endswith("/") else t + "/"
    lit_dir = lit if lit.endswith("/") else lit.rsplit("/", 1)[0] + "/" if "/" in lit else ""
    if lit.startswith(t_dir) or lit == t.rstrip("/"):
        return True
    return bool(lit_dir) and t_dir.startswith(lit_dir) and lit != s


def validate_card(
    head: Mapping[str, Any],
    scope: str | None,
    policy: CardPolicy,
    all_cards: Mapping[int, Mapping[str, Any]] | None = None,
    relations: bool = True,
) -> list[Refusal]:
    """The profile of the card's kind and status (03 §3), the shape's layer rules (1.11), the canonical forms (5.3),
    relations (1.8). `all_cards`: id → head, for relations; None skips them (a pure single-document check)."""
    v: list[Refusal] = []
    for k in head:
        if k not in canon.KNOWN_HEAD_KEYS:
            _r(v, "head.unknown-key", k)
    for k in ("schema", "id", "status", "title", "source"):
        if k not in head:
            _r(v, f"profile.head.{k}", k, "required")
    status = head.get("status")
    if status not in STATUSES:
        _r(v, "profile.head.status", "status", str(status))
    if "source" in head and head["source"] not in policy.card_sources:
        _r(v, "profile.head.source", "source", str(head["source"]))
    kind = head.get("kind", policy.kind_default)
    if kind not in KINDS and kind not in policy.ladder_levels:
        _r(v, "profile.head.kind", "kind", str(kind))
    elif kind in cfg.PROFILES and kind not in policy.profiles_enabled:
        _r(v, "profile.head.kind", "kind", f"{kind!r} profile is not enabled (S8)")
    if "id" in head and (not isinstance(head["id"], int) or isinstance(head["id"], bool) or head["id"] < 1):
        _r(v, "profile.head.id", "id", "an int >= 1")
    try:
        canon.canonical_json({k: x for k, x in head.items() if k not in canon.META_KEYS})
        if scope is not None:
            canon.check_string(scope, "scope")
    except Refusal as e:
        v.append(e)
    for key, rx in (("rules", _ID_RULE), ("questions", _ID_Q)):
        for item in head.get(key, []) or []:
            if (
                not isinstance(item, Mapping)
                or not rx.match(str(item.get("id", "")))
                or not isinstance(item.get("text"), str)
            ):
                _r(v, f"profile.{key}.shape", key)
    if "closures" in head:
        for c in head["closures"]:
            if "retracted" not in c:
                _r(v, "profile.closures.retracted-absent", "closures")
            if c.get("kind") != "human":
                _r(
                    v,
                    "profile.closures.kind",
                    "closures",
                    "`migrated` reserved, rejected in v1; `factory` only in the sidecar",
                )
            out = c.get("outcome")
            if not (
                out == "met" or (isinstance(out, Mapping) and "deviated" in out and out["deviated"].get("description"))
            ):
                _r(v, "profile.closures.outcome", "closures")
    if "hold" in head:
        h = head["hold"]
        if (
            not isinstance(h, Mapping)
            or h.get("kind") not in HOLD_KINDS
            or (
                "on" in h
                and (not isinstance(h["on"], Mapping) or len(h["on"]) != 1 or next(iter(h["on"])) not in HOLD_ON)
            )
        ):
            _r(v, "profile.hold.shape", "hold")
        elif h.get("kind") != "watching" and "on" not in h:
            _r(v, "profile.hold.on-required", "hold")
        if status in ("closed", "withdrawn"):
            _r(v, "profile.hold.status", "hold")
    if status == "withdrawn" and not head.get("withdrawn_reason"):
        _r(v, "profile.withdrawn.reason", "withdrawn_reason")
    if status == "closed" and not head.get("closures"):
        _r(v, "profile.closed.closures", "closures")
    # `class_of_service = "expedite"` requires a bounded `because` (7be.3, 02 §2) — the tending field's name is a
    # 03 §2.1 follow-up for the owner; not enforced until it has a home.
    for s in head.get("surfaces", []) or []:
        if glob_may_reach(str(s), policy.root):
            _r(v, "surfaces.intersects-tracking-root", "surfaces", str(s))
        for d in policy.deny:
            if glob_may_reach(str(s), d):
                _r(v, "surfaces.intersects-deny-set", "surfaces", f"{s!r} reaches {d!r}")
                break
    if status == "draft":
        if "shape" in head:
            v += _shape_rules(head, policy)
        return _relations(head, all_cards, policy, v) if relations else v
    # ratified / closed / withdrawn: the full profile of the kind
    if scope is None:
        _r(v, "profile.scope", "scope", "required")
    if kind == "story":
        v += _shape_rules(head, policy)
        sc = (head.get("acceptance") or {}).get("scenarios") or []
        if not sc or not any(s.get("kind") in RUNNABLE_KINDS for s in sc):
            _r(v, "profile.story.acceptance", "acceptance")
        if "surfaces" not in head:
            _r(v, "profile.story.surfaces", "surfaces")
        elif head["surfaces"] == [] and head.get("shape", policy.shapes_default) not in ("spike", "task"):
            _r(v, "profile.story.surfaces-empty", "surfaces")
        if "priority" not in head:
            _r(v, "profile.story.priority", "priority")
        if "effort" in head and head["effort"] not in policy.effort_tiers:
            _r(v, "profile.story.effort", "effort", str(head["effort"]))
    if kind == "sprint" and "goal" not in head:
        _r(v, "profile.sprint.goal", "goal")
    return _relations(head, all_cards, policy, v) if relations else v


def _shape_rules(head: Mapping[str, Any], policy: CardPolicy) -> list[Refusal]:
    v: list[Refusal] = []
    shape = head.get("shape", policy.shapes_default)
    if shape not in policy.shapes_allowed:
        _r(v, "profile.shape.allowed", "shape", str(shape))
    sc = (head.get("acceptance") or {}).get("scenarios") or []
    rules = head.get("rules") or []
    nar = head.get("narrative") or {}
    owner_words = head.get("scope_mark") == "owner"
    seen_ids: set[str] = set()
    for s in sc:
        sid = str(s.get("id", ""))
        if s.get("kind") not in SCENARIO_KINDS or "observable" not in s or not _ID_S.match(sid):
            _r(v, "scenario.shape", f"acceptance.scenarios.{sid or '?'}")
        if sid in seen_ids:
            _r(v, "scenario.duplicate-id", f"acceptance.scenarios.{sid}")
        seen_ids.add(sid)
        if s.get("kind") == "command" and not isinstance((s.get("action") or {}).get("run"), list):
            _r(v, "scenario.command.argv", f"acceptance.scenarios.{sid}", "`run` is an argv array")
        if s.get("kind") == "file-assert":
            for fc in (s.get("observable") or {}).get("files", []) or [s.get("observable") or {}]:
                checks = [k for k in ("exists", "contains", "matches", "sha256", "equals_file") if k in fc]
                if "path" in fc and len(checks) != 1:
                    _r(v, "scenario.file-assert.one-check", f"acceptance.scenarios.{sid}")
    rule_ids = {r.get("id") for r in rules}
    for s in sc:
        if "rule" in s and s["rule"] not in rule_ids:
            _r(v, "scenario.rule-unresolved", f"acceptance.scenarios.{s.get('id')}", str(s["rule"]))
    if shape == "bdd":
        for r in sorted(str(x) for x in rule_ids):
            if not any(s.get("rule") == r for s in sc):
                _r(v, "profile.bdd.rule-without-scenario", f"rules.{r}")
    elif shape == "ears":
        system = nar.get("system")
        if not system:
            _r(v, "profile.ears.system", "narrative.system")
        if not rules:
            _r(v, "profile.ears.rules", "rules")
        weak = (
            re.compile(r"\b(" + "|".join(re.escape(w) for w in policy.weak_words) + r")\b", flags=re.I)
            if policy.weak_words
            else None
        )
        for r in rules:
            text = str(r.get("text", ""))
            m = _EARS.match(text)
            subj = next((g for g in m.groups() if g), None) if m else None
            if not m or (system and subj and canon.nfc(subj).casefold() != canon.nfc(str(system)).casefold()):
                _r(v, "profile.ears.grammar", f"rules.{r.get('id')}")
            if weak and weak.search(text):
                _r(v, "profile.ears.weak-word", f"rules.{r.get('id')}")
            if not any(s.get("rule") == r.get("id") for s in sc):
                _r(v, "profile.ears.rule-without-scenario", f"rules.{r.get('id')}")
    elif shape == "classic" and not owner_words and not all(nar.get(k) for k in ("as_a", "i_want", "so_that")):
        _r(v, "profile.classic.narrative", "narrative")
    elif shape == "spike" and not nar.get("deliverable"):
        _r(v, "profile.spike.deliverable", "narrative.deliverable")
    return v


def _relations(
    head: Mapping[str, Any], all_cards: Mapping[int, Mapping[str, Any]] | None, policy: CardPolicy, v: list[Refusal]
) -> list[Refusal]:
    if all_cards is None:
        return v
    me = head.get("id")
    for k in ("parent", "depends_on", "sprint", "milestone", "goal"):
        if k not in head:
            continue
        targets = head[k] if isinstance(head[k], list) else [head[k]]
        for t in targets:
            tgt = all_cards.get(t)
            if tgt is None:
                _r(v, "relation.unresolved", k, str(t))
            elif k in ("parent", "depends_on") and tgt.get("status") not in ("ratified", "closed", "draft"):
                _r(v, "relation.unratified-target", k, str(t))
    if "parent" in head and head["parent"] in all_cards:
        ladder = ["story", *reversed(policy.ladder_levels), "epic"]
        pk = all_cards[head["parent"]].get("kind", policy.kind_default)
        ck = head.get("kind", policy.kind_default)
        if pk in ladder and ck in ladder and ladder.index(pk) != ladder.index(ck) + 1:
            _r(v, "relation.ladder", "parent", f"{ck} under {pk}")
    # acyclicity over depends_on (T-A5a): a DFS from the changed edges, never a full-graph pass
    graph: dict[Any, list[Any]] = {i: list(c.get("depends_on", [])) for i, c in all_cards.items()}
    graph[me] = list(head.get("depends_on", []))
    seen: set[Any] = set()
    path: set[Any] = set()

    def dfs(n: Any) -> bool:
        if n in path:
            return True
        if n in seen:
            return False
        seen.add(n)
        path.add(n)
        if any(dfs(m) for m in graph.get(n, [])):
            return True
        path.discard(n)
        return False

    if dfs(me):
        _r(v, "relation.cycle", "depends_on")
    return v
