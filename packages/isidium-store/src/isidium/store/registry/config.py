"""`config.toml` — the config validator (04 §1, §2, §6), the effective-config resolver (Y1, §4.1), `[[governed]]`
first-match resolution (L2-3), and the four rule sites of §6: write / start-up / dispatch / dry run, plus the signer
seam's use-time check. Typed refusals under the twenty `config.*` ids, the shared `head.*` / `canon.*` regimes, and
`signer.backend-unavailable` (deliberately not a `config.*` id — it fires in the signer seam).

Key inventories and bounds are read from the ADOPTED schema version's document wherever the check is mechanical
(type / enum / pattern / range / subset-of / reserved / required); cross-key rules and the dynamic tables are code,
each keyed to its §6 id. Descends from impl-d1 (the 104-check closing run), plus the 7be pins: `[surfaces] deny`,
the optional `read` member on manifest rows, `window_reserve` reserved.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping, Sequence
from typing import Any, Final

from ..core import canon
from ..core.grammar import Entry, TomlOrders, parse_config
from ..core.refusal import Refusal
from .loader import Registry, adopted_version, parse_ref
from .vocabulary import CLOSED_TYPES, SchemaDoc, check_required_when, is_type

SCHEMA_VERSION: Final = (
    3  # the config schema version this module's cross-key code mirrors (K10: config@3, root immutable)
)

# 04 §2.1 — scalars first, among themselves in this inventory order
SCALAR_ORDER: Final[tuple[str, ...]] = (
    "schema",
    "chain_opened_under",  # config@2 (K6): the policy chain's genesis version; absent from a config@1 file
    "tenant",
    "root",
    "time_skew",
    "wip",
    "batch_boundary",
)
# 04 §1 — the pinned table order (`payload` orders the pinned `[payload.context]` header)
TABLE_ORDER: Final[tuple[str, ...]] = (
    "toolkit",
    "journal",  # config@2 (K6): the journal version this tenant writes under; absent from a config@1 file
    "ratification",
    "signer",
    "effort",
    "ladder",
    "profiles",
    "shapes",
    "surfaces",
    "payload",
    "runners",
    "board",
    "inbox",
    "prioritization",
    "origin",
    "extensions",
    "governed",
    "history",
)
# Per-table serialization key order (04 §2.2 column order) for the known keys
TABLE_KEY_ORDER: Final[dict[str, tuple[str, ...]]] = {
    "toolkit": ("client", "registry", "unidata", "object_id"),
    "journal": ("schema",),
    "ratification": ("mode", "software_key_ack", "path", "verdicts_required", "pin"),
    "signer": ("backends",),
    "effort": ("tiers", "budgets"),
    "ladder": ("levels",),
    "profiles": ("enabled",),
    "shapes": ("allowed", "default"),
    "surfaces": ("deny",),
    "payload.context": ("depth", "max_bytes"),
    "runners": ("test", "command", "http", "file"),
    "board": ("commit",),
    "inbox": ("max_per_run", "max_per_actor_per_day"),
    "prioritization": (
        "time_criticality",
        "unblocking",
        "resume",
        "aging",
        "batch",
        "risk",
        "expedite_limit",
        "expedite_bump",
        "aging_horizon_days",
    ),
    "origin": ("card", "inbox"),
    "governed": ("path", "schema", "write", "read"),
}
CONFIG_ORDERS: Final = TomlOrders(SCALAR_ORDER, TABLE_ORDER, TABLE_KEY_ORDER)

BATCH_BOUNDARIES: Final = ("epic", "milestone", "sprint", "on-demand")
OBJECT_IDS: Final = ("sha1", "sha256")
SIG_ALGS: Final = ("ed25519", "ecdsa-p256")  # 03 §5.6
SIGNER_CLOSED_SET: Final = ("remote-totp", "tpm-hello", "yubikey", "signal-approve", "software_key_ack")  # 03 §1.12
BUILT_BACKENDS: Final = ("remote-totp", "software_key_ack")  # 7bc.3 + 7bf.4 (B3: the waiver path for the bridge)
GRANTS: Final = ("owner", "contributor", "lander")  # 03 §1.12
PROFILES: Final = ("sprint", "milestone")
ORIGIN_CORE: Final = ("session", "review", "planner", "suggestion", "digest", "run")
SHAPE_CORE: Final = ("bdd", "ears", "classic", "task", "spike")  # 03 §1.11
KIND_CORE: Final = ("epic", "story", "sprint", "milestone")  # 03 §1.8 (the ladder collision set)
SCENARIO_KIND_CORE: Final = ("test", "command", "http", "file")  # 04 §2.2 [runners] core four
EXT_CLASSES: Final = ("gated", "tending", "log")  # 03 §7
ORIGIN_CARD_BUILTIN: Final = ("suggestion", "planner")  # L2-8
ORIGIN_INBOX_BUILTIN: Final = ("run", "planner")
SHIPPED_RUNNERS: Final[dict[str, tuple[str, ...]]] = {
    "test": ("pytest",),
    "command": ("shell",),
    "http": ("http",),
    "file": ("file",),
}  # L2-17: the closed set of runner ids the toolkit ships per kind; Ext runner ids are the named seam
WEAK_WORDS_DEFAULT: Final = (
    "should",
    "may",
    "might",
    "could",
    "quickly",
    "easily",
    "efficiently",
    "appropriate",
    "adequate",
    "sufficient",
)  # K-15 / L2-16
# 7be.2 — the default deny set, pinned at build (forge workflow dirs, hook paths); the vendored toolkit path joins
# when the vendoring layout is pinned (WP3).
SURFACES_DENY_DEFAULT: Final = (".github/", ".gitlab/", ".gitlab-ci.yml", ".githooks/", ".git/", ".isidium/")
FIRST_ACT: Final = "created"  # K-1
POLICY_ACTS: Final = ("config-policy", "batch-manifest", "binding")
RESERVED_TOP: Final = ("grants", "window_reserve")  # 04 §2 ratified paragraph; 7be.3
RESERVED_SEAMS: Final[dict[str, str]] = {
    "grants": (
        "reserved for isidium G7: the grant check is one function over a matrix value fixed in code for v1, shaped "
        "for G7 to make editable policy later (owner 7bc.2)"
    ),
    "window_reserve": (
        "reserved with its seam: the adapter-auth note's scheduling dial (the share of the provider window held back "
        "from dispatch), arriving when the adapter wires it (owner 7be.3)"
    ),
    "declared": (
        'ratification.mode = "declared" is reserved: software_key_ack is the path for a tenant without signing '
        "ceremony (owner 7bc.2)"
    ),
    "prioritization.job_size": "reserved: the job-size divisor arrives with effort telemetry (L2-7)",
}
# K-7: each [signer.<backend>] schema whitelists its behavioral keys; the unbuilt backends have EMPTY inventories.
SIGNER_BACKEND_KEYS: Final[dict[str, dict[str, tuple[int, int]]]] = {
    "remote-totp": {"poll_interval_ms": (250, 60000)},
    "tpm-hello": {},
    "yubikey": {},
    "signal-approve": {},
    "software_key_ack": {},
}

# --- grammars (L2-6, L2-15) ---------------------------------------------------------------------------------------
EXT_NAME: Final = re.compile(r"^[a-z][a-z0-9-]*$")
SEMVER_CORE: Final = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
UNIDATA_VER: Final = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
SCHEMA_REF: Final = re.compile(r"^[a-z][a-z0-9-]*@[1-9][0-9]*$")
TENANT_RE: Final = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")
PIN_RE: Final = re.compile("^(" + "|".join(SIG_ALGS) + "):[0-9a-f]+$")
_AT: Final = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_PY_TYPE: Final[dict[str, type]] = {"string": str, "int": int, "bool": bool, "array": list, "table": dict}


def semver_tuple(s: str) -> tuple[int, ...]:
    return tuple(int(x) for x in s.split("."))


def valid_root(s: Any) -> bool:
    """L2-15: relative, /-separated, no ./.. segments, trailing /."""
    if not isinstance(s, str) or not s.endswith("/") or s.startswith("/"):
        return False
    return all(seg not in ("", ".", "..") for seg in s.rstrip("/").split("/"))


def valid_git_ref(s: Any) -> bool:
    """ratification.path: a git branch name by git's ref-name rules (the practical subset, L2-15)."""
    if not isinstance(s, str) or not s or s.startswith("/") or s.endswith("/"):
        return False
    if s.endswith(".lock") or ".." in s or "@{" in s or s == "@":
        return False
    return not any(c in s for c in " ~^:?*[\\\x7f") and not any(ord(c) < 0x20 for c in s)


def valid_governed_pattern(p: Any) -> bool:
    """L2-4 — the three-target v1 dialect: /-separated literal segments, `*` within a segment only, no `**`, no `!`,
    no character classes, no escapes; case-sensitive; relative to the tracking root (archive-safe, K-17)."""
    if not isinstance(p, str) or not p or p.startswith("/") or p.endswith("/"):
        return False
    if any(c in p for c in "!?[]\\") or "**" in p:
        return False
    return all(seg not in ("", ".", "..") for seg in p.split("/"))


# ---------------------------------------------------------------------------------------------------- the tree


def _r(rs: list[Refusal], rule: str, path: str, msg: str) -> None:
    rs.append(Refusal(rule, path, msg))


def _walk(v: Any, path: str, rs: list[Refusal]) -> None:
    if isinstance(v, float):
        _r(rs, "canon.float", path, "no floats anywhere (04 §1); weights are integer per-mille")
    elif isinstance(v, str):
        ch = canon.forbidden_codepoint(v)
        if ch is not None:
            _r(rs, "canon.forbidden-codepoint", path, f"U+{ord(ch):04X}")
    elif isinstance(v, dict):
        for k, x in v.items():
            _walk(x, f"{path}.{k}" if path else str(k), rs)
    elif isinstance(v, list):
        for j, x in enumerate(v):
            _walk(x, f"{path}[{j}]", rs)


def _set_dup(rs: list[Refusal], v: Any, path: str) -> None:
    if isinstance(v, list) and len(v) != len(set(map(str, v))):
        _r(rs, "canon.set-duplicate", path, "a set; duplicates refused")


def _short(v: Any, bound: int = 80) -> str:
    """A value's repr for a refusal's detail, cut [K7b, F13]: the value is the caller's own — the review sent 900 KB
    as an enum member — and a detail that echoes it whole sends it back whole and writes it whole into the record."""
    text = repr(v)
    return text if len(text) <= bound else text[:bound] + "…"


def _check_row_value(rs: list[Refusal], v: Any, row: Mapping[str, Any], path: str, ns: str = "config") -> bool:
    """One value against one schema-document key row: the mechanical members of the Y3 vocabulary. The generic four
    ids each carry the offending key path (K-5). `ns` is the rule ids' namespace — `config` for the policy file,
    `record` for a record-slot document's rows [K7b, F13], so a caller reads which document refused it.

    **A `range` on a string bounds its length, in code points** [K7b, F13]. It bounded integers and list lengths
    only, so `inbox@1`'s `title` (max 120) and `reason` (max 500) were declared and never enforced by this pass; no
    `config@*` string key carries a range (checked, 2026-09-06), so nothing the policy file says changes."""
    t = row.get("type")
    if t in _PY_TYPE and not is_type(v, str(t)):
        _r(rs, f"{ns}.type", path, f"expected {t}, got {type(v).__name__}")
        return False
    if "enum" in row and v not in row["enum"]:
        _r(rs, f"{ns}.enum", path, f"{_short(v)} not in {row['enum']}")
    if "pattern" in row and isinstance(v, str) and not re.fullmatch(row["pattern"], v):
        _r(rs, f"{ns}.pattern", path, f"{_short(v)} does not match {row['pattern']!r}")
    if "range" in row:
        b = row["range"]
        n = len(v) if isinstance(v, (list, str)) else v
        if isinstance(n, int) and not isinstance(n, bool):
            if "min" in b and n < b["min"]:
                _r(rs, f"{ns}.range", path, f"must be >= {b['min']}, got {n}")
            if "max" in b and n > b["max"]:
                _r(rs, f"{ns}.range", path, f"must be <= {b['max']}, got {n}")
    so = row.get("subset-of")
    if so and "of" in so and isinstance(v, list):
        for x in v:
            if x not in so["of"]:
                _r(rs, f"{ns}.enum", f"{path}[]", f"{x!r} not in {so['of']}")
    return True


def check_record(rec: Mapping[str, Any], doc: SchemaDoc) -> list[Refusal]:
    """A record-slot row against the `[[record]]` rows its schema document declares [K7b, F13; deployment record
    H-5]: a closed key set, and every present key through the same mechanical pass the policy file gets. Which keys
    a given record *type* requires is the writer's (03b §3, `required_when` ranges over kind/status/shape only), so
    presence is not judged here — value shape is. `refs` is declared an array; its members are paths, so each must
    be a string: a list is the one type the Y3 vocabulary does not look inside.

    The K7 review put 900 KB into `kind` through `suggest` and watched it reach `main` in one commit: the schema had
    said `enum` all along, and nothing read it."""
    rows = {str(r["name"]): r for r in doc.get("record", [])}
    rs: list[Refusal] = []
    for k, v in rec.items():
        row = rows.get(k)
        if row is None:
            _r(rs, "record.unknown-key", k, f"not a key of {doc.get('name')}@{doc.get('version')}")
            continue
        if _check_row_value(rs, v, row, k, ns="record") and row.get("type") == "array":
            for j, x in enumerate(v):
                if not isinstance(x, str):
                    _r(rs, "record.type", f"{k}[{j}]", f"expected string, got {type(x).__name__}")
    return rs


def _table_rows(doc: SchemaDoc, name: str) -> Mapping[str, Any]:
    rows: list[Mapping[str, Any]] = doc.get("tables", [])
    for trow in rows:
        if trow["name"] == name:
            return trow
    return {"name": name, "keys": []}


def _check_plain_table(rs: list[Refusal], table: Mapping[str, Any], trow: Mapping[str, Any], prefix: str) -> None:
    """A table against its schema rows: closed key set (an unknown key is `config.enum` on that key — D1-5),
    reserved keys, required keys, then the mechanical members."""
    rows = {k["name"]: k for k in trow.get("keys", [])}
    for k in table:
        row = rows.get(k)
        if row is None:
            _r(rs, "config.enum", f"{prefix}.{k}", f"unknown key in [{prefix}]")
        elif "reserved" in row and "values" not in row["reserved"]:
            _r(
                rs,
                "config.reserved-key",
                f"{prefix}.{k}",
                RESERVED_SEAMS.get(f"{prefix}.{k}", "reserved, refused in v1"),
            )
    for k, row in rows.items():
        if "reserved" in row and "values" not in row["reserved"]:
            continue
        if k not in table:
            if row.get("required_when") == []:
                _r(rs, "config.type", f"{prefix}.{k}", "required key absent")
            continue
        _check_row_value(rs, table[k], row, f"{prefix}.{k}")


def validate_tree(tree: Mapping[str, Any], registry: Registry, identity_enabled: bool = False) -> list[Refusal]:
    """The write-site checks (§6's fifteen `config.*` ids + the shared regimes). Every default a cross-key rule
    needs is read from the ADOPTED schema version and handed to it — never written here (04 §4.1, Y1)."""
    rs: list[Refusal] = []
    _walk(tree, "", rs)
    ver = (
        tree.get("schema") if isinstance(tree.get("schema"), int) and not isinstance(tree.get("schema"), bool) else None
    )
    ref = f"config@{ver}" if ver is not None and registry.has(f"config@{ver}") else "config@1"
    doc = registry.get(ref)
    dfl = registry.defaults_of(ref)  # the adopted version's defaults: the only place a default comes from

    for k in tree:
        if k in RESERVED_TOP:
            _r(rs, "config.reserved-key", k, RESERVED_SEAMS[k])
        elif k not in SCALAR_ORDER and k not in TABLE_ORDER:
            _r(rs, "head.unknown-key", k, "unknown top-level key")

    for row in doc["scalars"]:
        k = row["name"]
        if k not in tree:
            if row.get("required_when") == []:
                _r(rs, "config.type", k, "required key absent")
            continue
        _check_row_value(rs, tree[k], row, k)
    if isinstance(tree.get("root"), str) and not valid_root(tree["root"]):
        _r(rs, "config.pattern", "root", "relative, /-separated, no ./.. segments, trailing / (L2-15)")
    opened = tree.get("chain_opened_under")
    if isinstance(opened, int) and not isinstance(opened, bool) and ver is not None and opened > ver:
        _r(rs, "config.range", "chain_opened_under", f"a chain cannot have opened under config@{opened} > config@{ver}")

    if ver is not None:
        if not registry.has(f"config@{ver}"):
            _r(rs, "config.schema-unknown", "schema", f"config@{ver} not in the installed registry")
        # Safe on the branch above: `adopted_version` answers `None` for a head this registry does not have,
        # rather than raising out of `defaults_of` where a refusal was already recorded.
        adopted = adopted_version(tree, registry)
        if adopted is not None and adopted != ver:
            _r(
                rs,
                "config.schema-self-mismatch",
                "schema",
                f"head schema = {ver} but the file's own [[governed]] row names config@{adopted}; "
                "a migration write changes both in the one write (L2-13)",
            )

    bb = tree.get("batch_boundary")
    profiles_raw = tree.get("profiles")
    profiles: Mapping[str, Any] = profiles_raw if isinstance(profiles_raw, dict) else {}
    profile_defaults: Mapping[str, Any] = dfl.get("profiles") or {}
    enabled = profiles.get("enabled") if "enabled" in profiles else profile_defaults.get("enabled")
    enabled = enabled if isinstance(enabled, list) else []
    if bb in PROFILES and bb not in enabled:
        _r(
            rs,
            "config.profile-required",
            "batch_boundary",
            f"{bb!r} names a disabled profile (profiles.enabled = {enabled})",
        )

    if "toolkit" not in tree:
        _r(rs, "config.type", "toolkit", "required table absent (the four pins)")
    for name in ("toolkit", "journal", "board", "inbox", "prioritization", "profiles", "ladder", "effort", "surfaces"):
        t = tree.get(name)
        if t is None:
            continue
        if not isinstance(t, dict):
            _r(rs, "config.type", name, "expected a table")
            continue
        _check_plain_table(rs, t, _table_rows(doc, name), name)
    _v_payload(rs, tree.get("payload"), doc)
    _v_effort_cross(rs, tree.get("effort"), dfl)
    _v_ladder_cross(rs, tree.get("ladder"))
    if isinstance(tree.get("profiles"), dict):
        _set_dup(rs, tree["profiles"].get("enabled"), "profiles.enabled")
    if isinstance(tree.get("surfaces"), dict):
        _v_surfaces(rs, tree["surfaces"])
    _v_ratification(rs, tree.get("ratification"), identity_enabled)
    _v_signer(rs, tree.get("signer"), tree, dfl)
    _v_shapes(rs, tree.get("shapes"), dfl)
    _v_runners(rs, tree.get("runners"))
    _v_origin(rs, tree.get("origin"))
    _v_extensions(rs, tree.get("extensions"))
    _v_governed(rs, tree.get("governed"), registry)
    _v_journal(rs, tree.get("journal"), registry)
    _v_history(rs, tree.get("history"))
    return rs


def _v_payload(rs: list[Refusal], t: Any, doc: SchemaDoc) -> None:
    if t is None:
        return
    if not isinstance(t, dict):
        _r(rs, "config.type", "payload", "expected a table")
        return
    for k in t:
        if k != "context":
            _r(rs, "config.enum", f"payload.{k}", "only [payload.context]")
    c = t.get("context")
    if isinstance(c, dict):
        _check_plain_table(rs, c, _table_rows(doc, "payload.context"), "payload.context")


def _v_effort_cross(rs: list[Refusal], t: Any, dfl: Mapping[str, Any]) -> None:
    if not isinstance(t, dict):
        return
    tiers = t.get("tiers", dfl.get("effort", {}).get("tiers", []))
    _set_dup(rs, tiers, "effort.tiers")
    budgets = t.get("budgets")
    if isinstance(budgets, dict):
        for k, v in budgets.items():
            if k not in tiers:
                _r(rs, "config.enum", f"effort.budgets.{k}", f"keys are a subset of tiers {tiers}")
            if isinstance(v, bool) or not isinstance(v, int):
                _r(rs, "config.type", f"effort.budgets.{k}", "an int token budget")
            elif v < 1:
                _r(rs, "config.range", f"effort.budgets.{k}", "must be >= 1")


def _v_ladder_cross(rs: list[Refusal], t: Any) -> None:
    """[ladder].levels: the one home for ladder Ext declarations (Y2) — never hashed; Ext grammar, no collision."""
    if not isinstance(t, dict):
        return
    levels = t.get("levels")
    if not isinstance(levels, list):
        return
    _set_dup(rs, levels, "ladder.levels")
    for x in levels:
        if not isinstance(x, str) or not EXT_NAME.match(x):
            _r(rs, "config.pattern", "ladder.levels[]", f"{x!r} does not match the Ext name grammar [a-z][a-z0-9-]*")
        elif x in KIND_CORE:
            _r(rs, "config.enum", "ladder.levels[]", f"{x!r} collides with a core kind member (L2-6/L2-8)")


def _v_surfaces(rs: list[Refusal], t: Mapping[str, Any]) -> None:
    """[surfaces].deny: repo-root-relative globs in the surfaces dialect (7be.2)."""
    deny = t.get("deny")
    if deny is None:
        return
    if not isinstance(deny, list) or any(not isinstance(x, str) or not x for x in deny):
        _r(rs, "config.type", "surfaces.deny", "an array of repo-root-relative globs")
        return
    _set_dup(rs, deny, "surfaces.deny")
    for x in deny:
        if x.startswith("/") or ".." in x.split("/"):
            _r(rs, "config.pattern", "surfaces.deny[]", f"{x!r} must be repo-root-relative with no .. segment")


def _v_ratification(rs: list[Refusal], t: Any, identity_enabled: bool) -> None:
    if t is None:
        return
    if not isinstance(t, dict):
        _r(rs, "config.type", "ratification", "expected a table")
        return
    for k in t:
        if k not in ("mode", "software_key_ack", "path", "verdicts_required", "pin"):
            _r(rs, "config.enum", f"ratification.{k}", "unknown key in [ratification]")
    mode = t.get("mode")
    if mode == "declared":
        _r(rs, "config.reserved-key", "ratification.mode", RESERVED_SEAMS["declared"])
    elif mode is not None and mode != "signed":
        _r(rs, "config.enum", "ratification.mode", f"{mode!r} not in ['signed'] ('declared' reserved)")
    if "path" in t and not valid_git_ref(t["path"]):
        _r(rs, "config.pattern", "ratification.path", "a git branch name, validated by git ref-name rules (L2-15)")
    if "verdicts_required" in t and not isinstance(t["verdicts_required"], bool):
        _r(rs, "config.type", "ratification.verdicts_required", "bool (L2-9)")
    if "software_key_ack" in t and (not isinstance(t["software_key_ack"], str) or not t["software_key_ack"].strip()):
        _r(rs, "config.type", "ratification.software_key_ack", "the owner's own words, non-empty")
    pin = t.get("pin")
    if pin is not None:
        if not isinstance(pin, str) or not PIN_RE.fullmatch(pin):
            _r(rs, "config.pattern", "ratification.pin", "want <alg>:<key_fpr>")
        elif identity_enabled:
            _r(
                rs,
                "config.pin-identity-enabled",
                "ratification.pin",
                "pin's one home is identity-disabled mode; a realm is enabled (K-12)",
            )


def _v_signer(rs: list[Refusal], t: Any, tree: Mapping[str, Any], dfl: Mapping[str, Any]) -> None:
    if t is None:
        return
    if not isinstance(t, dict):
        _r(rs, "config.type", "signer", "expected a table")
        return
    backends = t.get("backends", dfl.get("signer", {}).get("backends", []))
    if not isinstance(backends, list) or not backends:
        _r(rs, "config.range", "signer.backends", "a set, at least one backend")
        backends = []
    _set_dup(rs, backends, "signer.backends")
    for b in backends:
        if b not in SIGNER_CLOSED_SET:
            _r(
                rs,
                "config.backend-unknown",
                "signer.backends",
                f"{b!r} not in the closed set {list(SIGNER_CLOSED_SET)}",
            )
    rat_raw = tree.get("ratification")
    rat: Mapping[str, Any] = rat_raw if isinstance(rat_raw, dict) else {}
    if "software_key_ack" in backends and not rat.get("software_key_ack"):
        _r(
            rs,
            "config.type",
            "ratification.software_key_ack",
            "required when signer.backends contains 'software_key_ack' (L2-10)",
        )
    for k, v in t.items():
        if k == "backends":
            continue
        if k not in SIGNER_CLOSED_SET:
            _r(rs, "config.enum", f"signer.{k}", "per-backend tables only under [signer]")
            continue
        if not isinstance(v, dict):
            _r(rs, "config.type", f"signer.{k}", "expected a per-backend table")
            continue
        keys = SIGNER_BACKEND_KEYS[k]
        for kk, vv in v.items():
            spec = keys.get(kk)
            if spec is None:
                _r(
                    rs,
                    "config.registration-only",
                    f"signer.{k}.{kk}",
                    "each backend schema whitelists its behavioral keys; "
                    "anything else lives in the tenant registration (K-7)",
                )
            elif isinstance(vv, bool) or not isinstance(vv, int):
                _r(rs, "config.type", f"signer.{k}.{kk}", "expected int")
            elif not (spec[0] <= vv <= spec[1]):
                _r(rs, "config.range", f"signer.{k}.{kk}", f"in [{spec[0]}, {spec[1]}]")


def declared_shapes(tree: Mapping[str, Any]) -> list[str]:
    t = tree.get("shapes") or {}
    return [
        k
        for k, v in t.items()
        if k not in ("allowed", "default") and k not in SHAPE_CORE and isinstance(v, dict) and EXT_NAME.match(k)
    ]


def _v_shapes(rs: list[Refusal], t: Any, dfl: Mapping[str, Any]) -> None:
    """[shapes]: sub-tables over the shape enum (K-13); a core name holds lint options, any other name IS the tenant
    shape declaration — their one home (Y2), never hashed."""
    if t is None:
        return
    if not isinstance(t, dict):
        _r(rs, "config.type", "shapes", "expected a table")
        return
    shape_defaults = dfl.get("shapes", {})
    ext = declared_shapes({"shapes": t})
    allowed = t.get("allowed", shape_defaults.get("allowed", []))
    if not isinstance(allowed, list) or any(not isinstance(x, str) for x in allowed):
        _r(rs, "config.type", "shapes.allowed", "an array of shape names")
        allowed = list(shape_defaults.get("allowed", []))
    _set_dup(rs, allowed, "shapes.allowed")
    for x in allowed:
        if x not in SHAPE_CORE and x not in ext:
            _r(rs, "config.enum", "shapes.allowed[]", f"{x!r} not in the core five + declared Ext {sorted(ext)}")
    if t.get("default", shape_defaults.get("default")) not in allowed:
        _r(rs, "config.enum", "shapes.default", f"{t.get('default')!r} not in allowed (L2-15)")
    for k, v in t.items():
        if k in ("allowed", "default"):
            continue
        if not isinstance(v, dict):
            _r(rs, "config.type", f"shapes.{k}", "expected a sub-table")
            continue
        if k in SHAPE_CORE:
            if k == "ears":
                for kk in v:
                    if kk != "weak_words":
                        _r(rs, "config.enum", f"shapes.ears.{kk}", "lint keys: weak_words")
                ww = v.get("weak_words")
                if ww is not None and (not isinstance(ww, list) or any(not isinstance(x, str) for x in ww)):
                    _r(rs, "config.type", "shapes.ears.weak_words", "an array of words")
            else:
                for kk in v:
                    _r(rs, "config.enum", f"shapes.{k}.{kk}", f"no lint options pinned for {k!r} in v1")
        elif not EXT_NAME.match(k):
            _r(rs, "config.enum", f"shapes.{k}", "not a core shape and not a legal Ext name (K-5)")
        else:
            for kk in v:
                _r(rs, "config.enum", f"shapes.{k}.{kk}", "an Ext shape declaration carries no keys in v1 (D1-4)")


def declared_kinds(tree: Mapping[str, Any]) -> list[str]:
    t = tree.get("runners") or {}
    return [k for k in t if k not in SCENARIO_KIND_CORE and EXT_NAME.match(k)]


def _v_runners(rs: list[Refusal], t: Any) -> None:
    """[runners]: kind → binding; the kind key with its binding IS the Ext declaration (Y2 / K-14)."""
    if t is None:
        return
    if not isinstance(t, dict):
        _r(rs, "config.type", "runners", "expected a table")
        return
    for k, v in t.items():
        if k not in SCENARIO_KIND_CORE and not EXT_NAME.match(k):
            _r(rs, "config.enum", f"runners.{k}", "not a core scenario kind and not a legal Ext name")
        if not isinstance(v, str):
            _r(rs, "config.type", f"runners.{k}", "binding must be a runner id string")


def declared_origins(tree: Mapping[str, Any]) -> list[str]:
    t = tree.get("origin") or {}
    out: list[str] = []
    for key in ("card", "inbox"):
        for x in t.get(key, []):
            if isinstance(x, str) and x not in ORIGIN_CORE and EXT_NAME.match(x):
                out.append(x)
    return out


def _v_origin(rs: list[Refusal], t: Any) -> None:
    """[origin]: subsets of the one Origin enum; an Ext name's presence in a subset list is its declaration (D1-2);
    the subsets must contain what the built-in flows write (L2-8)."""
    if t is None:
        return
    if not isinstance(t, dict):
        _r(rs, "config.type", "origin", "expected a table")
        return
    for k in t:
        if k not in ("card", "inbox"):
            _r(rs, "config.enum", f"origin.{k}", "keys: card, inbox")
    builtin = {"card": ORIGIN_CARD_BUILTIN, "inbox": ORIGIN_INBOX_BUILTIN}
    for key in ("card", "inbox"):
        v = t.get(key)
        if v is None:
            continue
        if not isinstance(v, list) or any(not isinstance(x, str) for x in v):
            _r(rs, "config.type", f"origin.{key}", "an array of origin names")
            continue
        _set_dup(rs, v, f"origin.{key}")
        for x in v:
            if x not in ORIGIN_CORE and not EXT_NAME.match(x):
                _r(rs, "config.enum", f"origin.{key}[]", f"{x!r} is neither a core Origin member nor a legal Ext name")
        missing = [b for b in builtin[key] if b not in v]
        if missing:
            _r(
                rs,
                "config.origin-missing-builtin",
                f"origin.{key}",
                f"must contain what the built-in flows write: missing {missing} (L2-8)",
            )


def _v_extensions(rs: list[Refusal], t: Any) -> None:
    """[extensions]: x.* field schemas ONLY (Y2). NFC-unique declarations (03 §7)."""
    if t is None:
        return
    if not isinstance(t, dict):
        _r(rs, "config.type", "extensions", "expected a table")
        return
    seen: dict[str, str] = {}
    for k, v in t.items():
        nk = canon.nfc(k)
        if nk in seen:
            _r(rs, "ext-schema.key-collision", f"extensions.{k}", f"not NFC-unique against {seen[nk]!r} (03 §7)")
        seen[nk] = k
        if not isinstance(v, dict):
            _r(
                rs,
                "config.type",
                f"extensions.{k}",
                "x.* field schemas only (Y2): per-key type/class/required_when/enum",
            )
            continue
        for kk in v:
            if kk not in ("type", "class", "required_when", "enum"):
                _r(rs, "config.enum", f"extensions.{k}.{kk}", "per-key: type, class, required_when, enum")
        if v.get("type") not in CLOSED_TYPES:
            _r(rs, "config.enum", f"extensions.{k}.type", f"{v.get('type')!r} not in the closed type set")
        if v.get("class") not in EXT_CLASSES:
            _r(rs, "config.enum", f"extensions.{k}.class", f"{v.get('class')!r} not in {list(EXT_CLASSES)}")
        if "required_when" in v:
            check_required_when(v["required_when"], f"extensions.{k}.required_when", rs, "config.type", "config.enum")
        if "enum" in v and (not isinstance(v["enum"], list) or not v["enum"]):
            _r(rs, "config.type", f"extensions.{k}.enum", "a non-empty array")


def _v_journal(rs: list[Refusal], t: Any, registry: Registry) -> None:
    """`[journal].schema` [config@2, K6]: the journal version the store writes rows under. Its grammar and its name
    are the schema document's (a mechanical `pattern`, checked above); what is code is the same rule a `[[governed]]`
    row gets — the version must be one the store has installed, `config.schema-unknown` otherwise, so a tenant can
    never adopt a row shape this binary cannot write."""
    if not isinstance(t, dict):
        return
    ref = t.get("schema")
    if isinstance(ref, str) and SCHEMA_REF.fullmatch(ref) and not registry.has(ref):
        _r(rs, "config.schema-unknown", "journal.schema", f"{ref} not in the installed registry")


def immutable_changed(before: Mapping[str, Any], after: Mapping[str, Any], registry: Registry) -> list[Refusal]:
    """The vocabulary's `immutable` member, enforced at the policy write [K6]: a scalar the adopted version flags
    `immutable = true` may not change between the tree the store holds and the tree it is asked to write. `tenant`
    keeps its own older id (`config.tenant-immutable`, raised by the store); everything else flagged answers
    `config.immutable` on its key. Read from the version being ADOPTED: a key the old version did not have is
    being set for the first time, which is not a change."""
    rs: list[Refusal] = []
    ver = after.get("schema")
    ref = (
        f"config@{ver}"
        if isinstance(ver, int) and not isinstance(ver, bool) and registry.has(f"config@{ver}")
        else None
    )
    if ref is None:
        return rs
    for row in registry.get(ref)["scalars"]:
        k = row["name"]
        if row.get("immutable") and k != "tenant" and k in before and before[k] != after.get(k):
            _r(rs, "config.immutable", k, f"{before[k]!r} -> {after.get(k)!r}: this key is immutable once written")
    return rs


def journal_schema(eff: Mapping[str, Any]) -> int:
    """The journal version this tenant's store writes under (K6, ruled 7bg.10): `[journal].schema` in the
    **effective** config, which for a config@2 tenant is the file's own value or config@2's declared default (Y1).

    A config@1 tenant declares nothing — the key does not exist in its version — and every journal a store wrote
    under config@1 is `journal@1` by construction. That baseline is `chain.DEFAULT_REGISTRY`'s, read from there
    rather than written a second time here; it is the one place "which version predates the key" is recorded."""
    t = eff.get("journal")
    if isinstance(t, dict) and isinstance(t.get("schema"), str):
        return parse_ref(str(t["schema"]))[1]
    # Imported here, not at the top (C-13, 7bh.1): `core.chain` imports `cryptography`, and this module is in the
    # pre-commit hook's graph — the hook validates a manifest on every commit and never asks this question. The
    # store is the only caller, and it already holds `chain`. Measured: the top-level import put `cryptography`
    # back into the hook (K3b's guard failed), which is ~0.5 s per commit for a constant.
    from ..core.chain import DEFAULT_REGISTRY

    return DEFAULT_REGISTRY["journal"]


def _v_governed(rs: list[Refusal], rows: Any, registry: Registry) -> None:
    if rows is None:
        return
    if not isinstance(rows, list):
        _r(rs, "config.type", "governed", "expected [[governed]] rows")
        return
    seen_paths: dict[str, int] = {}
    for j, r in enumerate(rows):
        p = f"governed[{j}]"
        if not isinstance(r, dict):
            _r(rs, "config.type", p, "expected a row table")
            continue
        for k in r:
            if k not in ("path", "schema", "write", "read"):
                _r(rs, "config.enum", f"{p}.{k}", "row keys: path, schema, write, read")
        pat = r.get("path")
        if not isinstance(pat, str):
            _r(rs, "config.type", f"{p}.path", "required key absent or not a string")
        else:
            if not valid_governed_pattern(pat):
                _r(
                    rs,
                    "config.pattern-dialect",
                    f"{p}.path",
                    "the three-target v1 dialect: /-separated literal segments, * within a segment only, "
                    "no **, no !, no classes, no escapes (L2-4)",
                )
            if pat in seen_paths:
                _r(
                    rs,
                    "config.governed-overlap",
                    f"{p}.path",
                    f"byte-identical duplicate of governed[{seen_paths[pat]}].path {pat!r} "
                    "(L2-3; overlapping-but-different patterns are legal — first match wins)",
                )
            seen_paths.setdefault(pat, j)
        sch = r.get("schema")
        if not isinstance(sch, str):
            _r(rs, "config.type", f"{p}.schema", "required key absent or not a string")
        elif not SCHEMA_REF.fullmatch(sch):
            _r(rs, "config.pattern", f"{p}.schema", "the schema ref grammar [a-z][a-z0-9-]*@[1-9][0-9]* (L2-6)")
        elif not registry.has(sch):
            _r(rs, "config.schema-unknown", f"{p}.schema", f"{sch!r} not in the installed registry")
        for member in ("write", "read"):
            w = r.get(member)
            if w is None:
                if member == "write":
                    _r(rs, "config.type", f"{p}.write", "a non-empty grant list")
                continue
            if not isinstance(w, list) or (member == "write" and not w):
                _r(rs, "config.type", f"{p}.{member}", "a grant list" + (" (non-empty)" if member == "write" else ""))
                continue
            _set_dup(rs, w, f"{p}.{member}")
            for g in w:
                if g not in GRANTS:
                    _r(rs, "config.enum", f"{p}.{member}[]", f"{g!r} not in {list(GRANTS)}")


def _v_history(rs: list[Refusal], t: Any) -> None:
    """The policy chain: the first entry `created` (K-1), then config-policy / batch-manifest / binding."""
    if t is None:
        return
    entries = t.get("entries") if isinstance(t, dict) else None
    if not isinstance(entries, list):
        _r(rs, "head.history-shape", "history.entries", "entries = [ ... ] required")
        return
    prev_at = ""
    for j, e in enumerate(entries):
        p = f"history.entries[{j}]"
        if not isinstance(e, dict):
            _r(rs, "head.history-shape", p, "one inline table per line")
            continue
        for k in ("seq", "at", "by", "act", "fields", "build", "h"):
            if k not in e:
                _r(rs, "head.history-shape", f"{p}.{k}", "required entry key")
        if e.get("seq") != j + 1:
            _r(rs, "head.history-shape", f"{p}.seq", "1-based, dense")
        act = e.get("act")
        if j == 0 and act != FIRST_ACT:
            _r(
                rs,
                "head.history-shape",
                f"{p}.act",
                f"the first entry is {FIRST_ACT!r} (the recompute table's first row, K-1)",
            )
        elif j > 0 and act not in POLICY_ACTS:
            _r(rs, "head.history-shape", f"{p}.act", f"after the first entry: {list(POLICY_ACTS)} only")
        at = str(e.get("at", ""))
        if not _AT.match(at):
            _r(rs, "head.history-shape", f"{p}.at", "RFC 3339 UTC Z, seconds")
        elif at < prev_at:
            _r(rs, "integrity.time", f"{p}.at", "at non-monotone")
        prev_at = at or prev_at


# ---------------------------------------------------------------------------------------------------- the text


def parse_and_validate(
    text: str, registry: Registry, identity_enabled: bool = False
) -> tuple[dict[str, Any], list[Entry], list[Refusal]]:
    """Grammar (K-8 ids) + the tree (§6) — every refusal collected. The tree excludes `history`; the entries are
    returned beside it."""
    tree, entries, rs = parse_config(text, CONFIG_ORDERS)
    if tree or not rs:
        rs += validate_tree(tree, registry, identity_enabled)
    return tree, entries, rs


# ------------------------------------------------------------------------------------- the resolver (Y1, §4.1)


def _merge(defaults: Mapping[str, Any], over: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = copy.deepcopy(dict(defaults))
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def named_version(tree: Mapping[str, Any]) -> int | None:
    """The `config@<n>` the file NAMES, read from the file alone: its own `config.toml` row when it carries a
    `[[governed]]` table, else its head `schema` key; `None` when it names nothing — an empty tree, a checkout before
    `init` has written the file. Registry-free on purpose [K11]: this is the question a reader asks *before* it
    knows whether the version is installed, and K10's finding 1 was that nobody asked it — `adopted_version` answers
    `None` for a version the registry lacks, and the resolver below then read a `config@2` file against `config@1`."""
    rows = tree.get("governed")
    if isinstance(rows, list):
        for r in rows:
            if isinstance(r, dict) and r.get("path") == "config.toml":
                sch = str(r.get("schema", ""))
                if SCHEMA_REF.fullmatch(sch):
                    name, ver = parse_ref(sch)
                    if name == "config":
                        return ver
                break
    head = tree.get("schema")
    return head if isinstance(head, int) and not isinstance(head, bool) else None


def resolve_effective(tree: Mapping[str, Any], registry: Registry) -> dict[str, Any]:
    """The effective config: the tenant's file overlaid on the defaults of its ADOPTED schema version — never on a
    binary's built-ins (Y1). One overlay pass; 0 store calls; idempotent.

    **A version the file names and this registry lacks is refused here, not papered over** [K11, 2026-09-07; K10's
    finding 1]. This used to fall back to the head `schema` and then to `config@1` in silence, and tenant #0's
    pre-commit hook resolved a `config@2` file against `config@1`'s defaults for two chunks with nothing saying so —
    the registry under `.isidium/schemas/` had not been refreshed since K8. The id is the validator's own, with the
    validator's own words (`config.schema-unknown`), so every reader of a checkout — the hook, the forge's chain
    verifier — answers as the store would; the store itself never reaches this arm, because it validates the file
    first and refuses the same id there. A tree that names **no** version still resolves against `config@1`: that is
    a checkout before `init` has written the file, where there is nothing to be behind (the seam, named: `init`
    adopts `registry.newest("config")`; this arm does not)."""
    v = adopted_version(tree, registry)
    if v is None:
        v = named_version(tree)
    if v is None:
        v = 1
    ref = f"config@{v}"
    if not registry.has(ref):
        raise Refusal("config.schema-unknown", "schema", f"{ref} not in the installed registry")
    return _merge(registry.defaults_of(ref), tree)


# ----------------------------------------------------------------------------------- [[governed]] resolution (L2-3)


def _pat_re(pat: str) -> re.Pattern[str]:
    """The L2-4 dialect: /-separated literal segments, `*` within a segment only."""
    return re.compile("/".join("[^/]*".join(re.escape(x) for x in seg.split("*")) for seg in pat.split("/")) + r"\Z")


def governed_resolve(eff: Mapping[str, Any], path: str) -> Mapping[str, Any] | None:
    """First match wins IS the resolution rule (L2-3): specific row before general."""
    rows: list[Mapping[str, Any]] = eff.get("governed", [])
    for r in rows:
        if _pat_re(str(r["path"])).match(path):
            return r
    return None


# ---------------------------------------------------------------------------------- the other three rule sites (§6)


def startup_check(eff: Mapping[str, Any], binary: Mapping[str, str]) -> list[Refusal]:
    """At store start-up, two ids (+ the `canon.unicode-db` assert). `binary` = {client, registry, unidata,
    object_format} — the running installation and one `rev-parse` of the repo (O(1), L2-19)."""
    rs: list[Refusal] = []
    tk = eff.get("toolkit", {})
    for k in ("client", "registry"):
        floor, have = tk.get(k), binary.get(k)
        if (
            isinstance(floor, str)
            and SEMVER_CORE.fullmatch(floor)
            and have
            and semver_tuple(have) < semver_tuple(floor)
        ):
            _r(
                rs,
                "config.toolkit-incompatible",
                f"toolkit.{k}",
                f"a compatibility floor (Y1): running {have} < pinned {floor}; a newer binary runs",
            )
    if tk.get("unidata") and binary.get("unidata") and tk["unidata"] != binary["unidata"]:
        _r(rs, "canon.unicode-db", "toolkit.unidata", f"runtime UCD {binary['unidata']} != pinned {tk['unidata']}")
    if tk.get("object_id") and binary.get("object_format") and tk["object_id"] != binary["object_format"]:
        _r(
            rs,
            "config.object-id-mismatch",
            "toolkit.object_id",
            f"config says {tk['object_id']!r}, the repo's object format is {binary['object_format']!r} (L2-19)",
        )
    return rs


def dispatch_check(eff: Mapping[str, Any], registration: Mapping[str, Any]) -> list[Refusal]:
    """At dispatch (the factory, against the registration), two ids (L2-14). The store's write path never sees the
    registration."""
    rs: list[Refusal] = []
    pin = (eff.get("ratification") or {}).get("pin")
    if (
        isinstance(pin, str)
        and ":" in pin
        and registration.get("ratifier_fpr")
        and pin.split(":", 1)[1] != registration["ratifier_fpr"]
    ):
        _r(rs, "config.pin-mismatch", "ratification.pin", "pin does not equal the registration's ratifier fingerprint")
    allowed = registration.get("allowed_backends")
    if allowed is not None:
        for b in (eff.get("signer") or {}).get("backends", []):
            if b not in allowed:
                _r(
                    rs,
                    "config.backend-not-allowed",
                    "signer.backends",
                    f"{b!r} declared but outside the registration's allowed_backends {allowed}",
                )
    return rs


def dry_run_check(eff: Mapping[str, Any], kinds_needed: Sequence[str]) -> list[Refusal]:
    """At dry run, one id (L2-17): a missing binding makes a scenario kind uncompilable; a binding naming an
    unshipped runner is the same typed error."""
    rs: list[Refusal] = []
    runners = eff.get("runners", {})
    for kind in kinds_needed:
        binding = runners.get(kind)
        if binding is None:
            _r(rs, "config.runner-unshipped", f"runners.{kind}", f"no binding: scenario kind {kind!r} is uncompilable")
        elif binding not in SHIPPED_RUNNERS.get(kind, ()):
            _r(
                rs,
                "config.runner-unshipped",
                f"runners.{kind}",
                f"binding {binding!r} is not a runner the toolkit ships for {kind!r} "
                f"(shipped: {list(SHIPPED_RUNNERS.get(kind, ()))}; Ext runner ids are the named seam)",
            )
    return rs


def use_backend(eff: Mapping[str, Any], name: str) -> Refusal | None:
    """At signing (the signer seam, deliberately not a `config.*` id): a declared-but-unbuilt or unreachable backend is
    `signer.backend-unavailable`, naming the backend and the available set (7bc.3 / L2-10)."""
    declared = (eff.get("signer") or {}).get("backends", [])
    available = [b for b in declared if b in BUILT_BACKENDS]
    if name not in declared or name not in BUILT_BACKENDS:
        why = "not declared" if name not in declared else "declared but not built"
        return Refusal(
            "signer.backend-unavailable",
            "signer.backends",
            f"backend {name!r} is {why}; available: {available} (declared: {declared}, built: {list(BUILT_BACKENDS)})",
        )
    return None
