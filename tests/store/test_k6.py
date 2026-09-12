"""K6 — H-1: caller identity in the journal row, and Q5 (2026-09-05).

Four caller-identity properties the deployment record §1 says must be right *now* because they cannot be backfilled,
plus the ruling that carries them (7bg.10): the certificate **fingerprint** in the journal row beside the principal;
the certificate's **validity window** checked by the store itself; **full-subject** matching, never a bare common
name; the registration read from a **file the store re-reads**; and the row shape bumped to `journal@2` through the
tenant's own `config-policy` act — adopting `config@2`, which declares `[journal].schema` — with every row recording
the version it was written under, so the chain a tenant opened under `journal@1` continues unbroken.

Every test here is a value in and a value out against `Service.handle` or the `Journal` on a real SQLite file; the
socket in front of them is `test_edge.py`'s. Mutation-checked with `tools/mutations/k6.toml`.
"""

from __future__ import annotations

import copy
import datetime as _dt
import hashlib
import json
import logging
import os
import sqlite3
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from isidium.store.client.cli import config_write_args
from isidium.store.core import chain, telemetry
from isidium.store.core.grammar import Document
from isidium.store.core.refusal import Refusal
from isidium.store.registry import config as cfg
from isidium.store.registry.loader import Registry
from isidium.store.server import http
from isidium.store.server.api import Api
from isidium.store.server.gitrepo import MemGit
from isidium.store.server.journal import BESIDE, Journal
from isidium.store.server.service import Registration, Service, parse_registration
from isidium.store.server.signer import SoftwareKey, SoftwareKeyAck
from isidium.store.server.store import NewCard, Store

from .conftest import BASE_SCOPE, OWNER, PLANNER, REF_FILES, REGISTRY, Clock, Harness, Telemetry, base_head, fresh
from .test_service import CLOCK, OWNER_CERT, PLANNER_CERT, call

EPOCH = _dt.datetime(2026, 8, 1, tzinfo=_dt.UTC)
DAY = _dt.timedelta(days=1)


def cert(
    subject: Sequence[tuple[x509.ObjectIdentifier, str]],
    *,
    eku: Sequence[x509.ObjectIdentifier] | None = (ExtendedKeyUsageOID.CLIENT_AUTH,),
    not_before: _dt.datetime = EPOCH,
    not_after: _dt.datetime = EPOCH + 365 * DAY,
) -> bytes:
    """A self-signed leaf in DER with every knob these tests turn: the subject's attributes in order, the extended
    key usage (`None` = no extension at all), and the window."""
    key = ed25519.Ed25519PrivateKey.generate()
    name = x509.Name([x509.NameAttribute(oid, value) for oid, value in subject])
    builder = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
    )
    if eku is not None:
        builder = builder.add_extension(x509.ExtendedKeyUsage(list(eku)), critical=False)
    return builder.sign(key, None).public_bytes(serialization.Encoding.DER)


def at(t: _dt.datetime) -> int:
    return int(t.timestamp())


def registration(clock: Any = CLOCK) -> Registration:
    return Registration({"CN=owner@example": ("amodal1@example", "owner")}, clock)


# ---- full-subject matching ---------------------------------------------------------------------------------------


def test_the_full_subject_is_the_key_and_a_bare_common_name_is_not() -> None:
    """H-1 item 3. The registration's key is the whole subject in RFC 4514 form. The pre-K6 fallback matched the
    common name alone, so *anything* the CA issued with a registered name in any position was a store credential.

    Positive discriminator first: the exact subject resolves. Then the three ways the old fallback would have said
    yes — an extra attribute beside the registered name, the name in a non-CN attribute, a bare-name registration
    key — and each is a stranger now."""
    reg = registration()
    exact = reg.credential(cert([(NameOID.COMMON_NAME, "owner@example")]))
    assert (exact.principal, exact.grant) == ("amodal1@example", "owner")

    beside = reg.credential(cert([(NameOID.ORGANIZATION_NAME, "evil"), (NameOID.COMMON_NAME, "owner@example")]))
    assert beside.principal is None and beside.refusal is None, "a registered CN beside another attribute matched"
    elsewhere = reg.credential(cert([(NameOID.ORGANIZATIONAL_UNIT_NAME, "owner@example")]))
    assert elsewhere.principal is None
    bare = Registration({"owner@example": ("amodal1@example", "owner")}, CLOCK)
    assert bare.credential(cert([(NameOID.COMMON_NAME, "owner@example")])).principal is None, "bare-CN key matched"

    # the key for a multi-attribute subject is the whole name, in RFC 4514 order — the form an operator can produce
    # with `openssl x509 -noout -subject -nameopt RFC2253`
    two = Registration({"CN=owner@example,O=Take Tempo": ("amodal1@example", "owner")}, CLOCK)
    both = two.credential(cert([(NameOID.ORGANIZATION_NAME, "Take Tempo"), (NameOID.COMMON_NAME, "owner@example")]))
    assert both.principal == "amodal1@example"


# ---- the validity window and clientAuth, checked by the store itself ---------------------------------------------


@pytest.fixture(scope="module")
def svc() -> tuple[Service, Harness]:
    hz = fresh("k6")
    reg = Registration(
        {
            "CN=owner@example": ("amodal1@example", "owner"),
            "CN=sartor-planner@agents.example": ("sartor-planner@agents.example", "contributor"),
        },
        hz.clock,
    )
    return Service(Api(hz.st), reg, hz.st.tenant), hz


def test_a_certificate_outside_its_window_is_refused_by_the_store_itself() -> None:
    """H-1 item 2, and K6's second trap: TLS checked this at the handshake, and the store checks it again because
    the check is what makes the seam portable to a realm that hands over a certificate with no handshake in front of
    it. Proven with a clock the test controls, on a certificate whose only defect is the time.

    The refusal is terse (`auth.*`, C-12): the rule id and nothing else reaches the peer; the subject and the date go
    to the record. And a certificate outside its window resolves **no principal** — the edge keys its allowance on
    the fingerprint, as for any unregistered peer."""
    valid = cert([(NameOID.COMMON_NAME, "owner@example")], not_before=EPOCH, not_after=EPOCH + 10 * DAY)
    hz = fresh("k6-window")
    for now, rule in ((at(EPOCH - DAY), "auth.not-yet-valid"), (at(EPOCH + 11 * DAY), "auth.expired")):
        service = Service(Api(hz.st), registration(lambda now=now: now), hz.st.tenant)
        credential = service.registration.credential(valid)
        assert credential.principal is None and credential.grant is None, "a defective certificate kept its name"
        assert credential.refusal is not None and credential.refusal.rule == rule
        assert http.allowance_for(credential, http.Limits(max_per_probe=2))[1] == 2  # the probe class, by key
        status, body = call(service, "show", {"target": "queue"}, valid)
        assert (status, body) == (401, {"rule": rule}), body
    # the same certificate, the same registration, a clock inside the window: the positive discriminator
    inside = Service(Api(hz.st), registration(lambda: at(EPOCH + 5 * DAY)), hz.st.tenant)
    status, body = call(inside, "show", {"target": "queue"}, valid)
    assert status == 200 and "open_questions" in body["result"]
    # RFC 5280's window is inclusive at both ends: the two boundary instants are inside it
    for edge in (at(EPOCH), at(EPOCH + 10 * DAY)):
        assert registration(lambda edge=edge: edge).credential(valid).principal == "amodal1@example", edge


def test_a_certificate_without_client_auth_is_not_a_credential() -> None:
    """Q5, ruled 2026-08-29: the store requires the `clientAuth` extended key usage. Measured then: a leaf with no
    EKU at all authenticated, so any leaf the tenant CA issued for a registered name — a web server's, say — was a
    store credential. An absent extension is an absent `clientAuth`; a `serverAuth`-only extension is refused; an
    extension that carries `clientAuth` among others is accepted."""
    reg = registration()
    subject = [(NameOID.COMMON_NAME, "owner@example")]
    none = reg.credential(cert(subject, eku=None))
    server = reg.credential(cert(subject, eku=(ExtendedKeyUsageOID.SERVER_AUTH,)))
    for c in (none, server):
        assert c.principal is None and c.refusal is not None and c.refusal.rule == "auth.no-client-auth"
    both = reg.credential(cert(subject, eku=(ExtendedKeyUsageOID.SERVER_AUTH, ExtendedKeyUsageOID.CLIENT_AUTH)))
    assert both.principal == "amodal1@example" and both.refusal is None
    hz = fresh("k6-eku")
    service = Service(Api(hz.st), reg, hz.st.tenant)
    status, body = call(service, "show", {"target": "queue"}, cert(subject, eku=None))
    assert (status, body) == (401, {"rule": "auth.no-client-auth"})  # `auth`'s terse row, inherited (Q2a)


# ---- the journal row: the credential, the version, and the trace beside it ----------------------------------------


def test_the_journal_row_records_the_credential_and_the_version(svc: tuple[Service, Harness]) -> None:
    """H-1 item 1, and the ruling's third clause. A tenant born on this toolkit is on the newest config version from
    `init` (`config@4` since L4; `config@3` since K10; `config@2` when this was written) and every one of them
    declares `journal@2`, so every row it writes is `journal@2`: it carries `schema = 2` and the credential —
    `sha256:` over the DER bytes the peer presented, the same digest the edge keys admission on — inside the hashed
    content, and the chain verifies."""
    service, hz = svc
    head = base_head(0, "draft")
    head.pop("id")
    status, body = call(
        service, "write", {"new_slug": "k6-credential", "document": {"head": head, "scope": BASE_SCOPE}}, PLANNER_CERT
    )
    assert status == 200, body
    row = hz.st.journal.rows()[-1]
    assert row["seq"] == body["result"]["journal_seq"]
    assert row["schema"] == 2 and row["caller"] == "sartor-planner@agents.example"
    assert row["credential"] == "sha256:" + hashlib.sha256(PLANNER_CERT).hexdigest()
    assert hz.st.journal.verify()
    # the credential and the version are INSIDE `c`: recomputing the link without either does not reproduce `h`
    prev = hz.st.journal.rows()[-2]["h"]
    content = {k: v for k, v in row.items() if k not in BESIDE}
    assert chain.link(prev, content) == row["h"]
    for dropped in ("credential", "schema"):
        assert chain.link(prev, {k: v for k, v in content.items() if k != dropped}) != row["h"], dropped
    # `init` adopted the newest config version, and with it the journal version, from the first row
    assert hz.st.config_tree["schema"] == REGISTRY.newest("config") == 6 and cfg.journal_schema(hz.st.eff) == 2
    assert hz.st.journal.rows()[0]["schema"] == 2  # the harness's `init` is a direct call: a version, no channel
    assert hz.st.journal.genesis == chain.genesis("journal", hz.st.tenant, 2)


def test_the_trace_sits_beside_the_row_and_never_inside_it(svc: tuple[Service, Harness], otel: Telemetry) -> None:
    """K6's first trap (C-9, 7bg.12): the row joins telemetry on trace context — the call span's own ids, beside the
    content where `sig` sits — and never inside the hashed content, so the chain hashes the same bytes whether or
    not a deployment configured an exporter. With the in-memory SDK installed, the row's pointer is the span's."""
    service, hz = svc
    otel.clear()
    head = base_head(0, "draft")
    head.pop("id")
    status, body = call(
        service, "write", {"new_slug": "k6-trace", "document": {"head": head, "scope": BASE_SCOPE}}, PLANNER_CERT
    )
    assert status == 200, body
    span = otel.spans(telemetry.CALL_SPAN)[-1]
    row = hz.st.journal.rows()[-1]
    assert row["trace_id"] == format(span.context.trace_id, "032x")
    assert row["span_id"] == format(span.context.span_id, "016x")
    prev = hz.st.journal.rows()[-2]["h"]
    without = {k: v for k, v in row.items() if k not in BESIDE}
    assert chain.link(prev, without) == row["h"], "the trace is inside the hashed content"
    assert chain.link(prev, {**without, "trace_id": row["trace_id"]}) != row["h"]
    assert hz.st.journal.verify()
    # a store driven directly runs inside no span: no pointer, and the row is still whole
    r = hz.st.write(NewCard("k6-direct"), Document(base_head(0, "draft"), {"Scope": BASE_SCOPE}), None, None, PLANNER)
    direct = hz.st.journal.rows()[-1]
    assert direct["seq"] == r.journal_seq and "trace_id" not in direct and "credential" not in direct
    assert hz.st.journal.verify()


# ---- a journal that opened under journal@1 keeps its genesis across the bump: tenant #0's shape -------------------

PRE_K6_SQL = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE journal (
  seq INTEGER PRIMARY KEY, at TEXT NOT NULL, caller TEXT NOT NULL, paths TEXT NOT NULL,
  repairs TEXT, h TEXT NOT NULL, sig TEXT);
CREATE TABLE journal_paths (seq INTEGER NOT NULL, path TEXT NOT NULL, PRIMARY KEY (path, seq));
CREATE TABLE pending (seq INTEGER NOT NULL, path TEXT NOT NULL, data BLOB, PRIMARY KEY (seq, path));
CREATE TABLE blobs (
  blob TEXT PRIMARY KEY, build TEXT NOT NULL, head_seq INTEGER NOT NULL, head_h TEXT NOT NULL,
  ext_hash TEXT NOT NULL, canon INTEGER NOT NULL);
CREATE TABLE signed (path TEXT PRIMARY KEY, blob TEXT NOT NULL, seq INTEGER NOT NULL);
"""


def pre_k6_journal(path: Path, tenant: str, rows: int) -> list[dict[str, Any]]:
    """A journal file exactly as a store older than K6 wrote it: the seven-column table, no `meta.schema`, rows
    chained from the `journal@1` genesis in the `journal@1` shape. Tenant #0's file has three such rows."""
    db = sqlite3.connect(str(path))
    db.executescript(PRE_K6_SQL)
    db.execute("INSERT INTO meta VALUES ('tenant', ?)", (tenant,))
    db.execute("INSERT INTO meta VALUES ('counter', ?)", (str(rows),))
    h = chain.genesis("journal", tenant)  # schema 1: the only version such a store could write
    written: list[dict[str, Any]] = []
    for seq in range(1, rows + 1):
        row: dict[str, Any] = {
            "seq": seq,
            "at": f"2026-09-0{seq}T00:00:00Z",
            "caller": "amodal1@example",
            "paths": [{"path": f"cards/000{seq}-x.md", "after_blob": "ab" * 20}],
        }
        row["h"] = h = chain.link(h, row)
        db.execute(
            "INSERT INTO journal (seq, at, caller, paths, repairs, h) VALUES (?, ?, ?, ?, NULL, ?)",
            (seq, row["at"], row["caller"], json.dumps(row["paths"], sort_keys=True), row["h"]),
        )
        db.execute("INSERT INTO journal_paths VALUES (?, ?)", (seq, row["paths"][0]["path"]))
        written.append(row)
    db.commit()
    db.close()
    return written


def test_a_journal_that_opened_under_v1_keeps_its_genesis_across_the_bump(tmp_path: Path) -> None:
    """The ruling said *done now while no real journal rows exist*; three real rows existed on tenant #0 by the time
    this was built. So the bump is additive: opening a pre-K6 file adds the four columns, pins the genesis it was
    built from, and the next row — written under `journal@2` — links to the last `journal@1` row and carries the
    new keys. The whole chain verifies from the original genesis, and the file's first three rows are byte-for-byte
    what they were."""
    path = tmp_path / "journal.sqlite"
    before = pre_k6_journal(path, "t0", 3)
    journal = Journal(path, "t0")
    journal.adopt(2)
    assert journal.genesis == chain.genesis("journal", "t0", 1) != chain.genesis("journal", "t0", 2)
    assert journal.head == (3, before[-1]["h"]) and journal.verify()
    assert journal.rows() == before, "the pre-K6 rows read back differently"
    with journal.transaction():
        row = journal.append(
            "2026-09-05T00:00:00Z",
            "amodal1@example",
            [{"path": "cards/0004-x.md", "after_blob": "cd" * 20}],
            credential="sha256:" + "ef" * 32,
            trace=("ab" * 16, "cd" * 8),
        )
    assert row["seq"] == 4 and row["schema"] == 2 and row["credential"] == "sha256:" + "ef" * 32
    assert chain.link(before[-1]["h"], {k: v for k, v in row.items() if k not in BESIDE}) == row["h"]
    assert journal.verify()
    assert journal.rows()[:3] == before and journal.rows()[3] == row
    # a second open sees the pin, not a guess: the genesis is a stored fact now
    again = Journal(path, "t0")
    again.adopt(2)
    assert again.genesis == chain.genesis("journal", "t0", 1) and again.verify()
    # and a journal that was EMPTY when it was opened pins the version its first row is written under
    empty = Journal(tmp_path / "empty.sqlite", "t1")
    empty.adopt(2)
    assert empty.genesis == chain.genesis("journal", "t1", 2)
    with empty.transaction():
        empty.append("2026-09-05T00:00:00Z", "a@example", [], credential=None, trace=None)
    empty.adopt(1)  # an adoption after the first row changes what rows carry, never the genesis
    assert empty.genesis == chain.genesis("journal", "t1", 2) and empty.verify()


# ---- the migration act: a config@1 tenant adopts config@2, and its next row is journal@2 ------------------------


def registry_without(tmp_path: Path, *refs: str) -> Registry:
    """The shipped registry minus the named documents — a toolkit that predates them."""
    d = tmp_path / "registry"
    d.mkdir()
    for name, raw in REGISTRY.source().items():
        if name not in refs:
            (d / f"{name}.toml").write_bytes(raw)
    return Registry.from_directory(d)


def test_a_config1_tenant_writes_v1_rows_until_the_policy_act_moves_it(tmp_path: Path) -> None:
    """The ruling, end to end (7bg.10): the bump rides the normal `config-policy` act. A tenant initialised by a
    toolkit that shipped only `config@1` writes `journal@1` rows; a K6 store over the same repository and the same
    journal keeps writing `journal@1` — a tenant is not affected by a version it has not adopted (04 §4.1) — and the
    owner's signed adoption of `config@2`, through the channel, is the first row that carries the new keys. That
    row's own version is 2, because the store re-adopts before it journals the act."""
    clock = Clock(1_787_000_000)
    signer = SoftwareKeyAck(SoftwareKey.generate(), clock, time_skew_s=600)
    repo = MemGit()
    repo.commit(dict(REF_FILES), "seed@example", "2026-08-01T00:00:00Z", "seed")
    path = tmp_path / "journal.sqlite"
    ack = "software-grade signatures are acceptable for this tenant for now"

    v1 = Store(
        "k6mig",
        repo,
        Journal(path, "k6mig"),
        # a pre-K6 toolkit: `init` adopts the newest it has
        registry_without(tmp_path, "config@2", "config@3", "config@4", "config@5", "config@6"),
        clock,
        signer,
        root="docs/work/",
    )
    v1.init(OWNER, software_key_ack=ack)
    assert v1.config_tree["schema"] == 1 and cfg.journal_schema(v1.eff) == 1
    v1.write(NewCard("before"), Document(base_head(0, "draft"), {"Scope": BASE_SCOPE}), None, None, PLANNER)
    old = v1.journal.rows()
    assert len(old) == 2 and all(set(r) == {"seq", "at", "caller", "paths", "h"} for r in old), old

    # the K6 store over the same tenant: config@1 is what the file adopts, so the rows stay journal@1
    st = Store("k6mig", repo, Journal(path, "k6mig"), REGISTRY, clock, signer, root="docs/work/")
    assert st.config_tree["schema"] == 1 and cfg.journal_schema(st.eff) == 1
    assert st.journal.genesis == chain.genesis("journal", "k6mig", 1)
    service = Service(Api(st), registration(clock), "k6mig")
    head = base_head(0, "draft")
    head.pop("id")
    status, body = call(service, "write", {"new_slug": "still-v1", "document": {"head": head}}, OWNER_CERT)
    assert status == 200, body
    still = st.journal.rows()[-1]
    assert set(still) == {"seq", "at", "caller", "paths", "h"}, "a journal@2 key reached a config@1 tenant"

    # the migration: the owner's file, edited to adopt config@2, handed over as one config-policy act
    tree = copy.deepcopy(st.config_tree)
    tree["schema"] = 2
    next(r for r in tree["governed"] if r["path"] == "config.toml")["schema"] = "config@2"
    base = {"seq": st.policy[-1]["seq"], "h": st.policy[-1]["h"]}
    # the chain opened under config@1 and the genesis cannot move: config@2 requires the file to say so
    status, body = call(service, "write", {"path": "config.toml", "document": tree, "base": base}, OWNER_CERT)
    assert status == 422 and [(v["rule"], v["path"]) for v in body["verdicts"]] == [
        ("config.type", "chain_opened_under")
    ]
    tree["chain_opened_under"] = 1
    status, body = call(service, "write", {"path": "config.toml", "document": tree, "base": base}, OWNER_CERT)
    assert status == 200, body
    assert body["result"]["entry"]["act"] == "config-policy" and sorted(body["result"]["entry"]["fields"]) == [
        "chain_opened_under",
        "governed",
        "schema",
    ]
    moved = st.journal.rows()[-1]
    assert moved["seq"] == body["result"]["journal_seq"] and moved["schema"] == 2
    assert moved["credential"] == "sha256:" + hashlib.sha256(OWNER_CERT).hexdigest()
    assert cfg.journal_schema(st.eff) == 2 and st.config_tree["schema"] == 2
    assert st.journal.verify() and st.journal.genesis == chain.genesis("journal", "k6mig", 1)
    assert st.journal.rows()[: len(old) + 1] == [*old, still], "the migration rewrote a row behind it"
    # the planner may not perform the act; a stale base is refused; and the tenant's own rows carry on as journal@2
    status, body = call(service, "write", {"new_slug": "after", "document": {"head": head}}, OWNER_CERT)
    assert status == 200 and st.journal.rows()[-1]["schema"] == 2
    status, body = call(service, "write", {"path": "config.toml", "document": tree, "base": base}, OWNER_CERT)
    assert (status, body["rule"]) == (409, "write.stale")
    # the opening version is immutable, and the CI gate verifies the migrated chain from it, not from the head
    moved_tree = copy.deepcopy(st.config_tree)
    moved_tree["chain_opened_under"] = 2
    head = {"seq": st.policy[-1]["seq"], "h": st.policy[-1]["h"]}
    status, body = call(service, "write", {"path": "config.toml", "document": moved_tree, "base": head}, OWNER_CERT)
    assert status == 422 and [(v["rule"], v["path"]) for v in body["verdicts"]] == [
        ("config.immutable", "chain_opened_under")
    ]
    from isidium.store.client.verify import _policy  # the forge's verifier, a verb of the package since K12

    migrated = tmp_path / "config.toml"
    migrated.write_bytes(st.raw["config.toml"])
    line = _policy(migrated)
    assert (line.schema, line.verdict) == ("config@2", "ok") and line.detail == f"{len(st.policy)} entries", line


def test_the_cli_hands_the_owners_file_over_with_its_own_head_as_the_base(tmp_path: Path) -> None:
    """`isidium write --config <file>`: the door the act needs at a terminal. The file's last `[history]` entry is
    the compare-and-swap base and the chain itself never travels — the store alone writes it (`log.rewritten`)."""
    hz = fresh("k6-cli")
    raw = hz.st.raw["config.toml"]
    f = tmp_path / "config.toml"
    f.write_bytes(raw)
    args = config_write_args(f)
    assert args["path"] == "config.toml" and "history" not in args["document"]
    assert args["base"] == {"seq": hz.st.policy[-1]["seq"], "h": hz.st.policy[-1]["h"]}
    assert args["document"]["schema"] == REGISTRY.newest("config") == 6 and args["document"]["tenant"] == "k6-cli"
    (tmp_path / "bad.toml").write_text("this = [is not\n", encoding="utf-8")
    with pytest.raises(Refusal) as refused:
        config_write_args(tmp_path / "bad.toml")
    assert refused.value.rule == "head.toml"


# ---- the config schema: a config@1 file cannot carry the key; an unshipped journal version is refused -----------


def test_the_journal_key_is_config2s_and_a_version_this_store_cannot_write_is_refused() -> None:
    """04 §4.1: a tenant on `config@1` cannot set, and is not affected by, a `config@2` key — so `[journal]` in a
    config@1 file is an unknown key, not a silent adoption. Under config@2 the key defaults to `journal@2` and a
    version outside the installed registry is `config.schema-unknown`, exactly as a `[[governed]]` row's would be."""
    base = {
        "schema": 1,
        "tenant": "t",
        "toolkit": {"client": "0.1.0", "registry": "0.1.0", "unidata": "15.0.0", "object_id": "sha1"},
    }
    rs = cfg.validate_tree({**base, "journal": {"schema": "journal@2"}}, REGISTRY)
    assert [(r.rule, r.path) for r in rs] == [("config.enum", "journal.schema")], rs
    v2 = {**base, "schema": 2, "chain_opened_under": 2, "governed": REGISTRY.defaults_of("config@2")["governed"]}
    assert cfg.validate_tree(v2, REGISTRY) == []
    assert cfg.journal_schema(cfg.resolve_effective(v2, REGISTRY)) == 2
    assert cfg.journal_schema(cfg.resolve_effective({**v2, "journal": {"schema": "journal@1"}}, REGISTRY)) == 1
    rs = cfg.validate_tree({**v2, "journal": {"schema": "journal@9"}}, REGISTRY)
    assert [(r.rule, r.path) for r in rs] == [("config.schema-unknown", "journal.schema")], rs
    rs = cfg.validate_tree({**v2, "journal": {"schema": "card@1"}}, REGISTRY)
    assert [r.rule for r in rs] == ["config.pattern"], rs
    rs = cfg.validate_tree({**v2, "chain_opened_under": 3}, REGISTRY)
    assert [(r.rule, r.path) for r in rs] == [("config.range", "chain_opened_under")], rs
    # `config@6` since V4a-i; `config@5` since V3; `config@4` since L4; `config@3` since K10; still journal@2
    assert REGISTRY.newest("config") == 6 and REGISTRY.newest("journal") == 2


# ---- the registration file: re-read on change, fail closed when it will not parse --------------------------------


def test_the_registration_file_is_re_read_and_a_revocation_is_an_edit(tmp_path: Path, caplog: Any) -> None:
    """H-1 item 4: revoking is an edit, not a rebuild. The store stats the file once per connection and re-parses
    only when the stamp moved. A file that stops parsing names **nobody** — the store fails closed, because the row
    the operator just mistyped may be the revocation — and says so in the record."""
    owner = cert([(NameOID.COMMON_NAME, "owner@example")])
    f = tmp_path / "registration.json"

    def write(text: str, tick: int) -> None:
        f.write_text(text, encoding="utf-8")
        os.utime(f, ns=(tick * 10**9, tick * 10**9))  # a stamp that moves even inside one timestamp tick

    write('{"CN=owner@example": ["amodal1@example", "owner"]}', 1_787_000_000)
    reg = Registration.from_file(f, CLOCK)
    assert reg.credential(owner).principal == "amodal1@example"

    write('{"CN=someone-else@example": ["else@example", "owner"]}', 1_787_000_001)  # revoked by omission
    assert reg.credential(owner).principal is None, "the edit was not seen"
    write('{"CN=owner@example": ["amodal1@example", "contributor"]}', 1_787_000_002)  # re-registered, demoted
    assert reg.credential(owner).grant == "contributor"

    with caplog.at_level(logging.WARNING, logger="isidium.store"):
        write('{"CN=owner@example": ["amodal1@example", "contributor"', 1_787_000_003)  # a torn edit
        assert reg.credential(owner).principal is None, "an unreadable registration kept serving the old mapping"
    assert any("registration" in r.getMessage() and "names nobody" in r.getMessage() for r in caplog.records)
    write('{"CN=owner@example": ["amodal1@example", "owner"]}', 1_787_000_004)
    assert reg.credential(owner).grant == "owner"

    # a start-up read that does not parse stops the store before it listens, with the reason
    (tmp_path / "bad-grant.json").write_text('{"CN=owner@example": ["amodal1@example", "root"]}', encoding="utf-8")
    with pytest.raises(ValueError, match="root"):
        Registration.from_file(tmp_path / "bad-grant.json", CLOCK)
    for bad in ('["a"]', '{"": ["a", "owner"]}', '{"CN=x": ["", "owner"]}', '{"CN=x": ["a"]}', '{"CN=x": "a"}'):
        with pytest.raises(ValueError):
            parse_registration(bad)
