"""The owner enrols the signing service's key with a binding signed twice (card 56).

Six tests. The store is built as `serve` builds it, the file key as the store's signer and the pin, the service added by
`use_signer` -- but with **no realm binding of the service's key**, which is what card 54's fixture put there to stand
in for this enrolment. S1 runs against the real `isidium-signer` listener and `Service` (certificates minted by
`tests/signer/test_service.py`); the rest stand the service in with `DevStubService`, which signs with its own key.
S3 builds its bindings by hand, one defect at a time, because the store's own verb can only write the good one.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pytest

from isidium.signer import page, totp
from isidium.store.core import chain
from isidium.store.core.grammar import emit_config, emit_entry, emit_markdown, parse_config, parse_markdown
from isidium.store.core.refusal import Refusal
from isidium.store.registry.config import CONFIG_ORDERS
from isidium.store.server.api import Api
from isidium.store.server.gitrepo import MemGit
from isidium.store.server.journal import Journal
from isidium.store.server.signer import (
    DevStubService,
    HttpsService,
    RemoteTotp,
    RemoteTotpContract,
    SoftwareKey,
    SoftwareKeyAck,
)
from isidium.store.server.store import Store

from ..signer.test_service import BASE, SECRET, wrong_code
from ..signer.test_service import TENANT as _SERVICE_TENANT
from ..signer.test_service import Rig as ServiceRig
from ..signer.test_service import rig as rig  # the fixture, re-exported: a real listener with minted certificates
from .conftest import OWNER, PLANNER, REF_FILES, REGISTRY, Clock, Harness

TENANT = "sartor"
ROOT = "docs/work/"
WAIVER = "software-grade signatures are acceptable for this tenant for now"
POLL_MS = 750
REALM = "realm-svc@agents.example"
EXTRA: dict[str, Any] = {
    "shapes": {"allowed": ["bdd", "task", "spike", "ears"], "default": "bdd"},
    "effort": {"tiers": ["default"]},
    "time_skew": 600,
    "inbox": {"max_per_run": 10},
    "signer": {"backends": ["remote-totp", "software_key_ack"], "remote-totp": {"poll_interval_ms": POLL_MS}},
}
assert _SERVICE_TENANT  # imported for the rig's sake only; this file's tenant is its own


class Ticker:
    """A clock only the code under test moves: `sleep` advances it, so no test here waits on the real one."""

    def __init__(self) -> None:
        self.now = 0.0

    def sleep(self, s: float) -> None:
        self.now += s

    def monotonic(self) -> float:
        return self.now


@dataclass
class Enrolling:
    """A pin-mode store holding the file key and a service, with nothing bound for the service's key."""

    st: Store
    file: SoftwareKeyAck
    pin_key: SoftwareKey
    clock: Clock
    remote: RemoteTotp
    h: Harness

    def ratify(self, card: int) -> dict[str, Any]:
        out: dict[str, Any] = Api(self.st).call("ratify", OWNER, {"ids": [card], "dry_run": False})
        return out

    def enrol(self, **args: Any) -> dict[str, Any]:
        out: dict[str, Any] = Api(self.st).call("enrol_signer", OWNER, args)
        return out

    def entry_of(self, card: int) -> dict[str, Any]:
        """The newest history entry of a card, which `verify_entry` is asked about."""
        path = self.st.path_of(card)
        assert path is not None
        return dict(self.st.docs[path].history[-1])


def enrolling(
    service: RemoteTotpContract, service_fpr: str, *, base: int = 1_787_000_000, sleep: Any = None
) -> Enrolling:
    clock = Clock(base)
    pin_key = SoftwareKey.generate()
    file = SoftwareKeyAck(pin_key, clock, time_skew_s=600)
    realm = SoftwareKeyAck(SoftwareKey.generate(), clock, time_skew_s=600)
    repo = MemGit()
    repo.commit(dict(REF_FILES), "seed@example", "2026-08-01T00:00:00Z", "seed the ref targets")
    st = Store(
        TENANT,
        repo,
        Journal(":memory:", TENANT),
        REGISTRY,
        clock,
        file,
        root=ROOT,
        realm_principal=REALM,
        software_fprs=frozenset({file.key_fpr}),
    )
    st.init(OWNER, software_key_ack=WAIVER, extra=EXTRA)
    ticker = Ticker()
    remote = RemoteTotp(
        service,
        service_fpr,
        POLL_MS,
        timeout_s=600,
        sleep=ticker.sleep if sleep is None else sleep,
        monotonic=ticker.monotonic,
    )
    st.use_signer(remote)
    st.monotonic = ticker.monotonic
    return Enrolling(st, file, pin_key, clock, remote, Harness(st, file, realm, clock, pin_key))


def stub_enrolling() -> tuple[Enrolling, DevStubService]:
    clock_for_stub = Clock(1_787_000_000)
    key = SoftwareKey.generate()
    stub = DevStubService(key, clock_for_stub)
    e = enrolling(stub, key.public.key_fpr)
    stub.clock = e.clock  # the stub's clock and the store's are one, as the skew check wants
    return e, stub


def unverified(e: Enrolling, card: int) -> bool:
    return "unverified" in e.st.check(card)["integrity"]


# ---- S1: the page shows the enrolment, and only a code co-signs it -----------------------------------------------------


def test_enrolment_needs_a_code(rig: ServiceRig) -> None:
    host, port = rig.listener.address
    service = rig.service
    https = HttpsService(host, port, rig.ca.path, rig.named.cert, rig.named.key, 5.0)
    seen: dict[str, Any] = {}
    policy_len: list[int] = []

    def the_owner(_s: float) -> None:
        if "pending" in seen:
            return
        pending = service.pending()
        seen["pending"] = pending
        seen["page"] = page.render_listing(pending)
        policy_len.append(len(e.st.policy))
        with pytest.raises(Refusal) as err:
            service.approve(pending[0].request_id, wrong_code(rig.clock.now))
        seen["wrong"] = err.value.rule
        seen["still_pending"] = len(service.pending())
        service.approve(pending[0].request_id, totp.code_at(SECRET, rig.clock.now))

    e = enrolling(https, service.key_fpr, base=BASE, sleep=the_owner)
    before = len(e.st.policy)
    rig.clock.now = e.clock.t  # the service's clock and the store's agree, inside the service's 60 s skew
    result = e.enrol()

    (request,) = seen["pending"]
    assert request.tenant == TENANT
    assert request.display[0][3] == {"enrolment": {"key_fpr": service.key_fpr, "tenant": TENANT, "grant": "owner"}}
    for fact in (service.key_fpr, TENANT, "owner", "enrolment"):
        assert fact.encode() in seen["page"]
    assert policy_len == [before]  # nothing was written while the owner had not entered a code
    assert seen["wrong"] == "signer.wrong-code" and seen["still_pending"] == 1  # a wrong code does not co-sign
    assert len(e.st.policy) == before + 1
    assert chain.parse_sig(result["entry"]["cosig"])[1] == service.key_fpr

    # the service announces another key than the one the store was told: refused before anything is submitted
    entered = service.entered
    liar = enrolling(https, "cd" * 32, base=BASE)
    with pytest.raises(Refusal) as err:
        liar.enrol()
    assert err.value.rule == "signer.wrong-key"
    assert service.entered == entered and service.pending() == []
    assert len(liar.st.policy) == 1


# ---- S2: the binding is signed by the pin and co-signed by the bound key ---------------------------------------------


def test_the_binding_is_signed_twice() -> None:
    e, stub = stub_enrolling()
    st, service_fpr = e.st, e.remote.key_fpr
    before = e.h.draft("before")
    e.ratify(before)
    assert unverified(e, before)  # nothing binds the service's key yet

    result = e.enrol()
    binding = st.policy[-1]
    assert result["entry"] == binding and binding["act"] == "binding" and binding["by"] == OWNER.principal
    assert binding["ref"] == {"key_fpr": service_fpr, "grant": "owner", "tenant": TENANT, "from": binding["at"]}
    h = binding["h"]
    assert chain.parse_sig(binding["sig"])[1] == e.file.key_fpr and chain.verify_sig(binding["sig"], TENANT, h)
    assert chain.parse_sig(binding["cosig"])[1] == service_fpr and chain.verify_sig(binding["cosig"], TENANT, h)
    assert h == chain.link(st.policy[-2]["h"], binding)  # the co-signature is outside the content `h` hashes
    assert h == chain.link(st.policy[-2]["h"], {k: v for k, v in binding.items() if k != "cosig"})
    assert len(stub.requests) == 2 and stub.received[-1][0][1] == "enrolment"  # the ratify, then the enrolment

    after = e.h.draft("after")
    e.ratify(after)
    assert st.verify_entry(e.entry_of(after)) and st.check(after)["integrity"] == []

    # it is durable: a store loaded over the same repository and journal holds the co-signature and verifies by it
    again = Store(TENANT, st.repo, st.journal, REGISTRY, e.clock, e.file, root=ROOT, realm_principal=REALM)
    assert again.policy[-2]["cosig"] == binding["cosig"]
    assert again.verify_entry(e.entry_of(after))
    assert unverified(e, before)  # the grant opens at the enrolment, not before it


# ---- S3: a binding missing either signature grants nothing -------------------------------------------------------------


def forge(
    e: Enrolling,
    key: SoftwareKey,
    *,
    sig_by: SoftwareKey | None,
    cosig_by: SoftwareKey | None,
    cosig_as: str | None = None,
    frm: str | None = None,
    until: str | None = None,
    tamper_from: str | None = None,
) -> None:
    """Append an owner-authored binding for `key` to the policy chain as built, then break it as asked."""
    st = e.st
    at = st.now()
    ref: dict[str, Any] = {"key_fpr": key.public.key_fpr, "grant": "owner", "tenant": TENANT, "from": frm or at}
    if until is not None:
        ref["until"] = until
    entry = st._binding_entry(OWNER, ref, at)
    h = str(entry["h"])
    if sig_by is not None:
        entry["sig"] = chain.format_sig("ed25519", sig_by.public.key_fpr, sig_by.sign_raw(chain.sig_bytes(TENANT, h)))
    if cosig_by is not None:
        entry["cosig"] = chain.format_sig(
            "ed25519", cosig_as or cosig_by.public.key_fpr, cosig_by.sign_raw(chain.sig_bytes(TENANT, h))
        )
    if tamper_from is not None:
        entry["ref"]["from"] = tamper_from
    st.policy.append(entry)


def signed_by(e: Enrolling, key: SoftwareKey) -> bool:
    """Whether an entry made by `key` after the binding verifies: the question every case asks."""
    at = e.st.now()
    h = "sha256:" + "ab" * 32
    entry = {
        "h": h,
        "at": at,
        "sig": chain.format_sig("ed25519", key.public.key_fpr, key.sign_raw(chain.sig_bytes(TENANT, h))),
    }
    return e.st.verify_entry(entry)


def test_a_half_signed_binding_grants_nothing() -> None:
    k, other = SoftwareKey.generate(), SoftwareKey.generate()
    far, past = "2999-01-01T00:00:00Z", "2026-01-01T00:00:00Z"
    defects: dict[str, Callable[[Enrolling], dict[str, Any]]] = {
        "no co-signature": lambda e: {"sig_by": e.pin_key, "cosig_by": None},
        "a co-signature by another key": lambda e: {"sig_by": e.pin_key, "cosig_by": other},
        "a co-signature labelled with the key but made by another": lambda e: {
            "sig_by": e.pin_key,
            "cosig_by": other,
            "cosig_as": k.public.key_fpr,
        },
        "not signed by the pin": lambda e: {"sig_by": other, "cosig_by": k},
        "not signed at all": lambda e: {"sig_by": None, "cosig_by": k},
        "edited after it was signed": lambda e: {
            "sig_by": e.pin_key,
            "cosig_by": k,
            "frm": far,
            "tamper_from": past,
        },
        "a pin-only revocation cannot open a grant": lambda e: {"sig_by": e.pin_key, "cosig_by": None, "until": far},
    }
    granted: dict[str, bool] = {}
    for name, defect in defects.items():
        e, _stub = stub_enrolling()
        assert not signed_by(e, k)
        forge(e, k, **defect(e))
        granted[name] = signed_by(e, k)
    assert granted == dict.fromkeys(defects, False)

    # the control: both signatures, by the right keys, and the key is bound
    e, _stub = stub_enrolling()
    forge(e, k, sig_by=e.pin_key, cosig_by=k)
    assert signed_by(e, k)


# ---- S4: the realm's bindings still hold ------------------------------------------------------------------------------


def test_realm_bindings_unchanged() -> None:
    k = SoftwareKey.generate()
    h = "sha256:" + "ab" * 32
    sig = chain.format_sig("ed25519", k.public.key_fpr, k.sign_raw(chain.sig_bytes(TENANT, h)))

    def at(when: str) -> dict[str, Any]:
        return {"h": h, "at": when, "sig": sig}

    # (1) identity enabled: no pin, the realm binds the key, no co-signature anywhere
    clock = Clock(1_787_000_000)
    realm = SoftwareKeyAck(SoftwareKey.generate(), clock, time_skew_s=600)
    ack = SoftwareKeyAck(SoftwareKey.generate(), clock, time_skew_s=600)
    repo = MemGit()
    repo.commit(dict(REF_FILES), "seed@example", "2026-08-01T00:00:00Z", "seed the ref targets")
    ident = Store(
        TENANT,
        repo,
        Journal(":memory:", TENANT),
        REGISTRY,
        clock,
        ack,
        root=ROOT,
        identity_enabled=True,
        realm_principal=REALM,
    )
    ident.init(OWNER, software_key_ack=WAIVER, extra=EXTRA)
    ident.bind(realm, k.public.key_fpr, "owner", "2026-01-01T00:00:00Z", until="2026-09-01T00:00:00Z")
    assert "cosig" not in ident.policy[-1]
    assert ident.verify_entry(at("2026-06-01T00:00:00Z"))
    assert not ident.verify_entry(at("2026-09-01T00:00:00Z")) and not ident.verify_entry(at("2026-12-01T00:00:00Z"))
    assert not ident.verify_entry(at("2025-12-01T00:00:00Z"))

    # (2) pin mode: the realm binds a key beside the pin and it verifies with no co-signature
    e, _stub = stub_enrolling()
    e.st.bind(e.h.realm, k.public.key_fpr, "owner", "2026-01-01T00:00:00Z")
    assert "cosig" not in e.st.policy[-1] and e.st.verify_entry(at("2026-06-01T00:00:00Z"))

    # (3) the membership-only walk, with no classifier, answers as it always did
    def binding(frm: str, until: str | None = None) -> dict[str, Any]:
        ref: dict[str, Any] = {"key_fpr": "aa", "grant": "owner", "tenant": TENANT, "from": frm}
        if until:
            ref["until"] = until
        return {"act": "binding", "ref": ref}

    entries = [{"act": "created"}, binding("2026-01-01"), binding("2026-03-01", "2026-06-01")]
    held = {
        t: chain.binding_holds(entries, "aa", "owner", t)
        for t in ("2025-12-31", "2026-02-01", "2026-04-01", "2026-06-01")
    }
    assert held == {"2025-12-31": False, "2026-02-01": True, "2026-04-01": True, "2026-06-01": False}
    assert not chain.binding_holds(entries, "bb", "owner", "2026-04-01")
    assert not chain.binding_holds(entries, "aa", "contributor", "2026-04-01")


# ---- S5: revocation ends the key's grant from then on -------------------------------------------------------------------


def test_revocation() -> None:
    e, stub = stub_enrolling()
    st, fpr = e.st, e.remote.key_fpr
    enrolment = e.enrol()["entry"]
    a = e.h.draft("a")
    e.ratify(a)
    assert st.verify_entry(e.entry_of(a))

    e.clock.t += 100
    asked = len(stub.requests)
    revoked = e.enrol(revoke=fpr)["entry"]
    assert revoked["act"] == "binding" and "cosig" not in revoked
    assert revoked["ref"] == {
        "key_fpr": fpr,
        "grant": "owner",
        "tenant": TENANT,
        "from": enrolment["ref"]["from"],
        "until": revoked["at"],
    }
    assert chain.parse_sig(revoked["sig"])[1] == e.file.key_fpr and chain.verify_sig(
        revoked["sig"], TENANT, revoked["h"]
    )
    assert len(stub.requests) == asked  # the service was not asked for a code

    assert st.verify_entry(e.entry_of(a))  # signed before the revocation: still verifies
    e.clock.t += 100
    b = e.h.draft("b")
    e.ratify(b)
    assert not st.verify_entry(e.entry_of(b)) and unverified(e, b)
    assert not unverified(e, a)

    with pytest.raises(Refusal) as err:
        e.enrol(revoke="ee" * 32)
    assert err.value.rule == "signer.not-bound"
    with pytest.raises(Refusal) as err:
        Api(st).call("enrol_signer", PLANNER, {})
    assert err.value.rule == "write.grant"


# ---- C10: the grammar carries `cosig`, and an entry without it is unchanged ----------------------------------------------


def test_cosig_round_trips_and_old_entries_unchanged() -> None:
    e, _stub = stub_enrolling()
    e.enrol()
    binding = e.st.policy[-1]
    assert "cosig" in binding

    text = emit_config(e.st.config_tree, e.st.policy, CONFIG_ORDERS)
    tree, entries, rs = parse_config(text, CONFIG_ORDERS)
    assert rs == [] and entries == e.st.policy and tree == e.st.config_tree
    assert emit_config(tree, entries, CONFIG_ORDERS) == text
    assert e.st.raw["config.toml"].decode("utf-8") == text  # what the store committed is what the grammar emits

    card = e.h.draft("round-trip")
    path = e.st.path_of(card)
    assert path is not None
    schema = e.st.doc_schema("card@1")
    doc = copy.deepcopy(e.st.docs[path])
    doc.history[-1]["cosig"] = binding["cosig"]
    parsed = parse_markdown(emit_markdown(doc, schema), schema)
    assert parsed.history == doc.history

    plain = {
        "seq": 1,
        "at": "2026-08-01T00:00:00Z",
        "by": "a@example",
        "act": "created",
        "fields": ["title"],
        "build": "sha256:ab",
        "h": "sha256:cd",
        "sig": "ed25519:ab:AAAA",
    }
    line = '  { seq = 1, at = "2026-08-01T00:00:00Z", by = "a@example", act = "created", fields = ["title"], build = "sha256:ab", h = "sha256:cd", sig = "ed25519:ab:AAAA" },'
    assert emit_entry(plain) == line
    assert emit_entry({**plain, "cosig": "ed25519:ab:BBBB"}) == line[:-3] + ', cosig = "ed25519:ab:BBBB" },'
    assert e.st.raw[path].decode("utf-8") == emit_markdown(e.st.docs[path], schema)
