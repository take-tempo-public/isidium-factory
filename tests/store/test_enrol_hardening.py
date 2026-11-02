"""The enrolment card 56 built, held by what its review (r-65) found missing (card 76).

F2: the pinned key's signature on a binding was checked by a line no test noticed -- deleting it left every test green.
F5: a pin-only revocation dated before its own `at` ended a grant in the past. F3, F6 and A1 are the README's: the
`STORE_COMMIT` bump, the wrap of the enrolment section, and what the code gate does and does not protect.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from isidium.store.core import chain
from isidium.store.server.signer import SoftwareKey

from .conftest import OWNER
from .test_enrol_signer import TENANT, Enrolling, stub_enrolling

README = Path(__file__).resolve().parents[2] / "deploy" / "README.md"
WIDTH = 120
SECTION_START = "### The store's half: signing a ratification through the service (card 54)"
SECTION_END = "## What is not here yet"
ENROL_START = "### Enrolling the service's key (card 56)"


def bind(
    e: Enrolling,
    key: SoftwareKey,
    *,
    at: str,
    frm: str,
    sig_key: SoftwareKey,
    until: str | None = None,
    sig_as: str | None = None,
    cosig_by: SoftwareKey | None = None,
) -> dict[str, Any]:
    """Append an owner-authored binding for `key` made at exactly `at`, with `until` as given.

    `test_enrol_signer.forge` reads the clock for its own `at` and the test clock moves 7 s per call, so a revocation
    whose `until` has to equal or precede that `at` cannot be built with it; this takes `at` once, from the caller."""
    ref: dict[str, Any] = {"key_fpr": key.public.key_fpr, "grant": "owner", "tenant": TENANT, "from": frm}
    if until is not None:
        ref["until"] = until
    entry: dict[str, Any] = dict(e.st._binding_entry(OWNER, ref, at))
    h = str(entry["h"])
    label = sig_as or sig_key.public.key_fpr
    entry["sig"] = chain.format_sig("ed25519", label, sig_key.sign_raw(chain.sig_bytes(TENANT, h)))
    if cosig_by is not None:
        entry["cosig"] = chain.format_sig(
            "ed25519", cosig_by.public.key_fpr, cosig_by.sign_raw(chain.sig_bytes(TENANT, h))
        )
    e.st.policy.append(entry)
    return entry


def signs_at(e: Enrolling, key: SoftwareKey, at: str) -> bool:
    """Whether an entry made by `key` at `at` verifies: the question the bindings exist to answer."""
    h = "sha256:" + "ab" * 32
    entry = {
        "h": h,
        "at": at,
        "sig": chain.format_sig("ed25519", key.public.key_fpr, key.sign_raw(chain.sig_bytes(TENANT, h))),
    }
    return e.st.verify_entry(entry)


def kind_of_last(e: Enrolling) -> chain.BindingKind | None:
    return chain.binding_kind(e.st.policy[-1], e.st.policy[-2]["h"], TENANT, e.file.key_fpr)


# ---- S1 (R1, r-65 F2): the pinned key's signature is verified, not only its label -------------------------------------


def test_a_binding_with_a_bad_pin_signature_grants_nothing() -> None:
    k, other = SoftwareKey.generate(), SoftwareKey.generate()
    e, _stub = stub_enrolling()
    t = e.st.now()
    # signed by another key but labelled with the pin's fingerprint: it passes the label check, and only the
    # signature check refuses it. The co-signature is genuine, so nothing else stands in the way.
    bind(e, k, at=t, frm=t, sig_key=other, sig_as=e.file.key_fpr, cosig_by=k)
    assert kind_of_last(e) is None
    assert not signs_at(e, k, e.st.now())

    # the control: the same binding signed by the real pin is a grant
    c, _stub = stub_enrolling()
    t = c.st.now()
    bind(c, k, at=t, frm=t, sig_key=c.pin_key, cosig_by=k)
    assert kind_of_last(c) == "grant"
    assert signs_at(c, k, c.st.now())


# ---- S2 (R2, r-65 F5): a revocation cannot reach back past the moment it was made ---------------------------------------


def test_a_backdated_pin_only_revoke_is_not_taken() -> None:
    k = SoftwareKey.generate()
    e, _stub = stub_enrolling()
    t0 = e.st.now()
    bind(e, k, at=t0, frm=t0, sig_key=e.pin_key, cosig_by=k)
    t1 = e.st.now()
    assert signs_at(e, k, t1)
    t2 = e.st.now()
    # `until` is t0, earlier than this entry's own `at`: taken, it would end the grant at t0 and unverify t1
    revoke = bind(e, k, at=t2, frm=t0, until=t0, sig_key=e.pin_key)
    assert t0 < t1 < t2 and revoke["at"] == t2
    assert kind_of_last(e) is None
    assert signs_at(e, k, t1)

    # the control, through the store's own path: `until` equals the entry's `at`, and it ends the grant
    c, _stub = stub_enrolling()
    c.enrol()
    c.clock.t += 100
    revoked = c.enrol(revoke=c.remote.key_fpr)["entry"]
    assert revoked["ref"]["until"] == revoked["at"]
    assert kind_of_last(c) == "revoke"
    c.clock.t += 100
    b = c.h.draft("b")
    c.ratify(b)
    assert not c.st.verify_entry(c.entry_of(b))


# ---- S3..S5 (R3..R5): the README -----------------------------------------------------------------------------------------


def enrolment_section() -> str:
    text = README.read_text(encoding="utf-8")
    start, end = text.index(ENROL_START), text.index(SECTION_END)
    assert start < end
    return " ".join(text[start:end].split())


def test_the_readme_names_the_store_commit_bump() -> None:
    section = enrolment_section()
    bump = "Bump `STORE_COMMIT` before the first `isidium enrol-signer`."
    assert bump in section
    assert "an older store image cannot read a `config.toml` that holds one" in section
    assert section.index(bump) < section.index("```sh isidium enrol-signer ```")


def test_the_readme_states_what_the_code_gate_protects() -> None:
    section = enrolment_section()
    assert "proves possession of the bound key, not that an Aegis code was entered for this key" in section
    assert (
        "Anything that can read the file key and append to the policy chain can still enrol a key of its own" in section
    )
    assert "names the gated key" in section


def test_the_enrolment_section_is_wrapped() -> None:
    lines = README.read_text(encoding="utf-8").split("\n")
    start, end = lines.index(SECTION_START), lines.index(SECTION_END)
    span = lines[start:end]
    assert start < end and span
    fenced = False
    long: list[tuple[int, int]] = []
    for n, line in enumerate(span, start + 1):
        if line.startswith("```"):
            fenced = not fenced
            continue
        if fenced or line.startswith("|"):  # a table row cannot be wrapped
            continue
        if len(line) > WIDTH:
            long.append((n, len(line)))
    assert long == []
