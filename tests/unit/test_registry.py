"""The registry (04 §4): the fixed point, every installed document valid, Y1 defaults from the document alone, the
d1 config fixtures through the validator and the resolver, and a drift check between card@1 and the card core."""

from __future__ import annotations

from pathlib import Path

from isidium.store.core import canon
from isidium.store.registry import config as cfg
from isidium.store.registry.loader import Registry, adopted_version

D1 = Path(__file__).parent.parent / "conformance" / "fixtures" / "d1"
REG = Registry.shipped()


def test_every_config_version_declares_a_manifest_that_adopts_itself() -> None:
    """The fixed point `adopted_version` stands on [C-1 ruled 2026-08-29, K1c].

    When a `config.toml` declares no `[[governed]]` table of its own, the adopted version is read from the declared
    manifest of the version its head names — which only answers the head back if every `config@N` names `config@N`
    in its own `config.toml` row. Nothing asserted that before this test. A `config@2` copied from `config@1` with
    the manifest row left at `config@1` would make `adopted_version` answer 1 for a file whose head says 2, and
    `validate_tree` would then refuse every such file with `config.schema-self-mismatch` — a build-breaking bug
    with no obvious cause, introduced by an edit that looks harmless.

    Mutation-checked: change any `config@N`'s manifest row for `config.toml` to another version and this fails."""
    versions = sorted(int(ref.split("@")[1]) for ref in REG.installed if ref.startswith("config@"))
    assert versions, "no config schema is installed at all"
    for n in versions:
        manifest = REG.defaults_of(f"config@{n}")["governed"]
        row = next((r for r in manifest if r["path"] == "config.toml"), None)
        assert row is not None, f"config@{n} declares no manifest row for config.toml"
        assert row["schema"] == f"config@{n}", f"config@{n}'s declared manifest adopts {row['schema']}"
        assert adopted_version({"schema": n}, REG) == n


def test_a_declared_manifest_beats_the_registry_and_an_unknown_head_is_not_an_error() -> None:
    """The two branches around that fixed point. A file's OWN `[[governed]]` table wins and is read without the
    registry at all; a head naming a version this registry does not have answers `None` rather than raising out of
    `defaults_of` — which is what lets `validate_tree` record `config.schema-unknown` and carry on."""
    own = {"schema": 1, "governed": [{"path": "config.toml", "schema": "config@7"}]}
    assert adopted_version(own, REG) == 7
    assert adopted_version({"schema": 99}, REG) is None
    assert adopted_version({}, REG) is None
    assert adopted_version({"schema": 1, "governed": "not a table"}, REG) is None


def test_installed_and_fixed_point() -> None:
    assert {
        "registry@1",
        "config@1",
        "card@1",
        "inbox@1",
        "sidecar@1",
        "sidecar-events@1",
        "board@1",
        "page@1",
    } <= REG.installed
    report = REG.check_all()
    bad = {ref: [str(r) for r in rs] for ref, rs in report.items() if rs}
    assert not bad, bad
    assert REG.addresses["registry@1"].startswith("sha256:")


def test_defaults_live_in_the_document() -> None:
    d = REG.defaults_of("config@1")
    assert d["root"] == "docs/work/" and d["time_skew"] == 600 and d["wip"] == 1 and d["batch_boundary"] == "epic"
    assert d["prioritization"] == {
        "time_criticality": 350,
        "unblocking": 300,
        "resume": 150,
        "aging": 100,
        "batch": 100,
        "risk": 0,
        "expedite_limit": 1,
        "expedite_bump": 1,
        "aging_horizon_days": 30,
    }
    assert d["shapes"]["allowed"] == ["bdd", "task", "spike"] and d["shapes"]["ears"]["weak_words"][0] == "should"
    assert d["signer"] == {"backends": ["remote-totp"], "remote-totp": {"poll_interval_ms": 2000}}
    assert d["payload"]["context"] == {"depth": 2, "max_bytes": 16384}
    assert "grants" not in d and "window_reserve" not in d and "job_size" not in d["prioritization"]
    assert d["surfaces"]["deny"] == list(cfg.SURFACES_DENY_DEFAULT)


def test_d1_fixtures_validate() -> None:
    text = (D1 / "config.toml").read_text(encoding="utf-8")
    tree, entries, rs = cfg.parse_and_validate(text, REG)
    assert [str(r) for r in rs] == []
    assert len(entries) == 8 and entries[0]["act"] == "created" and entries[6]["act"] == "binding"
    eff = cfg.resolve_effective(tree, REG)
    assert eff["root"] == "docs/wörk/" and eff["prioritization"]["batch"] == 50 and eff["wip"] == 1
    assert (
        cfg.declared_shapes(tree) == ["crispy"]
        and cfg.declared_kinds(tree) == ["lint"]
        and cfg.declared_origins(tree) == ["gossip"]
    )
    card = cfg.governed_resolve(eff, "cards/0042-x.md")
    wiki = cfg.governed_resolve(eff, "docs/wiki/home.md")
    assert card is not None and card["schema"] == "card@1"
    assert wiki is not None and wiki["write"] == ["owner"]
    assert cfg.governed_resolve(eff, "src/x.py") is None

    text = (D1 / "config-standalone.toml").read_text(encoding="utf-8")
    tree, entries, rs = cfg.parse_and_validate(text, REG)
    assert [str(r) for r in rs] == [] and tree["ratification"]["pin"].startswith("ed25519:")
    assert [r.rule for r in cfg.parse_and_validate(text, REG, identity_enabled=True)[2]] == [
        "config.pin-identity-enabled"
    ]

    # The Y1 adoption demo names config@2 — which **ships since K6** (the `[journal]` table rides it), so the demo's
    # own file now validates under it: what is left is the fixture's unknown `[inbox]` key, the demo's third act.
    # The fixture's bytes are the oracle's and stay; the "a version that does not ship" arm moves one number up.
    text = (D1 / "config-y1.toml").read_text(encoding="utf-8")
    tree, _, rs = cfg.parse_and_validate(text, REG)
    # `config.type`: config@2 requires `chain_opened_under`, which the 2026-08-26 demo could not have written
    assert sorted((r.rule, r.path) for r in rs) == [
        ("config.enum", "inbox.dedupe_window_days"),
        ("config.type", "chain_opened_under"),
    ]
    assert cfg.journal_schema(cfg.resolve_effective(tree, REG)) == 2  # config@2's declared default, no key written
    # the version that does not ship: `config@5` since L4 shipped `config@4` (the arm moved once more)
    unshipped = text.replace("schema = 2", "schema = 5", 1).replace('schema = "config@2"', 'schema = "config@5"', 1)
    _, _, rs = cfg.parse_and_validate(unshipped, REG)
    assert sorted(r.rule for r in rs) == ["config.enum", "config.schema-unknown", "config.schema-unknown"]


def test_write_site_refusals() -> None:
    base = {
        "schema": 1,
        "tenant": "t",
        "toolkit": {"client": "0.1.0", "registry": "0.1.0", "unidata": "16.0.0", "object_id": "sha1"},
    }

    def rules(**over: object) -> list[str]:
        return sorted(r.rule for r in cfg.validate_tree({**base, **over}, REG))

    assert rules() == []
    assert rules(grants={}) == ["config.reserved-key"]
    assert rules(window_reserve=100) == ["config.reserved-key"]
    assert rules(tenant="Bad_Name") == ["config.pattern"]
    assert rules(time_skew=5) == ["config.range"]
    assert rules(batch_boundary="sprint") == ["config.profile-required"]
    assert rules(ratification={"mode": "declared"}) == ["config.reserved-key"]
    assert rules(signer={"backends": ["software_key_ack"]}) == ["config.type"]  # the ack words are required (L2-10)
    assert rules(signer={"backends": ["remote-totp"], "remote-totp": {"address": "x"}}) == ["config.registration-only"]
    assert rules(signer={"backends": ["nope"]}) == ["config.backend-unknown"]
    assert rules(origin={"card": ["session"]}) == ["config.origin-missing-builtin"]
    assert rules(governed=[{"path": "cards/**/*.md", "schema": "card@1", "write": ["owner"]}]) == [
        "config.pattern-dialect"
    ]
    assert rules(
        governed=[
            {"path": "a.md", "schema": "card@1", "write": ["owner"]},
            {"path": "a.md", "schema": "card@1", "write": ["owner"]},
        ]
    ) == ["config.governed-overlap"]
    assert rules(governed=[{"path": "a.md", "schema": "wiki@1", "write": ["owner"]}]) == ["config.schema-unknown"]
    assert rules(governed=[{"path": "a.md", "schema": "card@1", "write": ["owner"], "read": ["contributor"]}]) == []
    assert rules(prioritization={"job_size": 3}) == ["config.reserved-key"]
    assert rules(prioritization={"aging": 1.5}) == ["canon.float", "config.type"]
    assert rules(surfaces={"deny": ["../x"]}) == ["config.pattern"]
    assert rules(shapes={"allowed": ["bdd", "nope"]}) == ["config.enum"]
    assert rules(extensions={"a": {"type": "string", "class": "gated", "required_when": "kind == story"}}) == [
        "config.type"
    ]


def test_other_rule_sites() -> None:
    eff = cfg.resolve_effective(
        {
            "schema": 1,
            "tenant": "t",
            "toolkit": {"client": "0.4.0", "registry": "0.4.0", "unidata": "16.0.0", "object_id": "sha1"},
        },
        REG,
    )
    assert [
        r.rule
        for r in cfg.startup_check(
            eff, {"client": "0.3.9", "registry": "0.4.0", "unidata": "16.0.0", "object_format": "sha256"}
        )
    ] == ["config.toolkit-incompatible", "config.object-id-mismatch"]
    assert (
        cfg.startup_check(eff, {"client": "0.5.0", "registry": "0.4.0", "unidata": "16.0.0", "object_format": "sha1"})
        == []
    )
    assert [
        r.rule
        for r in cfg.dispatch_check(
            {**eff, "ratification": {"pin": "ed25519:aa"}},
            {"ratifier_fpr": "bb", "allowed_backends": ["software_key_ack"]},
        )
    ] == ["config.pin-mismatch", "config.backend-not-allowed"]
    assert [r.rule for r in cfg.dry_run_check(eff, ["test", "lint"])] == ["config.runner-unshipped"]
    assert cfg.use_backend(eff, "remote-totp") is None
    r = cfg.use_backend(eff, "tpm-hello")
    assert r is not None and r.rule == "signer.backend-unavailable" and "available: ['remote-totp']" in r.detail


def test_card_schema_matches_the_core() -> None:
    doc = REG.get("card@1")
    names = {row["name"] for row in doc["head"]}
    assert names == set(canon.KNOWN_HEAD_KEYS)
    gated = {row["name"] for row in doc["head"] if row.get("class") == "gated"}
    assert gated == set(canon.GATED_KEYS) - {"scope", "x", "kind"}  # kind: class meta, hashed B (2.1, S9)
    assert [s["name"] for s in doc["sections"]] == ["Scope", "Updates"] and doc["footer"] == "history"
