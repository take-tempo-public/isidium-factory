"""The history chain (03 §5.5), the signature bytes and formats (§5.6, §1.12), the batch form, and verification
against a key ring and the policy chain's bindings. Pure: no key material lives here — the signer seam is the
server's (03 §1.12: the store never holds a ratifier key); this module only verifies.

Build pins (recorded in the sync record as build pins, not design changes):
- `key_fpr` IS the public key: lowercase hex of the raw key bytes — Ed25519 the 32-byte key (64 hex chars);
  ECDSA-P256 the SEC1 compressed point (33 bytes, 66 hex chars). No colons. So the pin in `config.toml`, a binding
  record and every signature carry the verification key itself — nothing to distribute, and "verification works from
  the tracking root alone" holds literally.
- Signature bytes inside the base64: Ed25519 the 64-byte signature; ECDSA-P256 the fixed-width `r ‖ s` (64 bytes),
  the form CNG, WebCrypto and TPMs emit — never DER.
"""

from __future__ import annotations

import base64
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, Literal

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, ed25519
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

from .canon import canonical_json, sha256_hex
from .refusal import Refusal

CHAIN_EXCLUDED: Final[tuple[str, ...]] = ("h", "sig", "batch")  # 5.5: c = every key except h, sig, batch
SIG_ALGS: Final[tuple[str, ...]] = ("ed25519", "ecdsa-p256")  # 5.6, closed
DocType = Literal["card", "inbox", "policy", "page", "journal"]
# 03b §3 / 5.5: every non-card genesis carries the document type's OWN registry schema version; the registry loader
# supplies the installed versions — these are the v1 defaults.
DEFAULT_REGISTRY: Final[dict[str, int]] = {"card": 1, "inbox": 1, "policy": 1, "page": 1, "journal": 1}
Verdict = Literal["ok", "tampered", "covered"]


def genesis(doc_type: str, ident: str | int, schema: int | None = None) -> str:
    """h_0 per document type: `card:<id>` / `inbox:<tenant>` / `policy:<tenant>` / `page:<governed path>` /
    `journal:<tenant>`, each under `schema:<n>` = that type's registry schema version."""
    if schema is None:
        schema = DEFAULT_REGISTRY[doc_type]
    return "sha256:" + sha256_hex(
        b"schema:" + str(schema).encode() + b"\n" + doc_type.encode() + b":" + str(ident).encode()
    )


def is_signed(entry: Mapping[str, Any]) -> bool:
    """1.15: an entry carries `sig` iff singly signed; a batch member carries `batch` only (the manifest signs)."""
    return "sig" in entry or "batch" in entry


def entry_content(entry: Mapping[str, Any]) -> str:
    return canonical_json({k: v for k, v in entry.items() if k not in CHAIN_EXCLUDED})


def link(h_prev: str, entry: Mapping[str, Any]) -> str:
    """h_n = sha256(utf8(h_{n-1}) + b"\\n" + canonical_json(c_n))."""
    return "sha256:" + sha256_hex(h_prev.encode("utf-8") + b"\n" + entry_content(entry).encode("utf-8"))


def verify_chain(
    entries: Sequence[Mapping[str, Any]],
    h0: str,
    genesis_after_repair: Callable[[Mapping[str, Any]], str] | None = None,
) -> list[Verdict]:
    """Recompute h_1..h_N. Per-entry verdicts: `ok` | `tampered` | `covered` (between a repair's restart point and
    the repair entry — unverifiable, covered by the repair, 5.5). `genesis_after_repair(entry) -> h0'` supports the id
    repair (a new genesis from the repaired entry on)."""
    verdicts: list[Verdict] = []
    h_by_seq: dict[int, str] = {0: h0}
    prev = h0
    for i, e in enumerate(entries):
        seq = i + 1
        if e.get("seq") != seq:
            verdicts.append("tampered")
            prev = str(e.get("h", prev))
            h_by_seq[seq] = prev
            continue
        if e.get("act") == "repaired":
            k = e.get("ref", 0)
            k = k if isinstance(k, int) and not isinstance(k, bool) else 0
            if genesis_after_repair is not None:
                h0 = genesis_after_repair(e)
                h_by_seq = {0: h0}
            base = h_by_seq.get(k, h0)
            for j in range(k, seq - 1):
                verdicts[j] = "covered"
            prev = base
        expected = link(prev, e)
        ok = e.get("h") == expected
        verdicts.append("ok" if ok else "tampered")
        prev = expected
        h_by_seq[seq] = prev
    return verdicts


# ---- signatures (5.6, 1.12) ------------------------------------------------------------------------------------


def sig_bytes(tenant: str, h: str) -> bytes:
    """The signed value: `utf8(tenant) + b"\\n" + utf8(h)` — `h` a chain hash or the batch hash."""
    return tenant.encode("utf-8") + b"\n" + h.encode("utf-8")


def batch_hash(member_hs: Sequence[str]) -> str:
    """`"sha256:" + hex(sha256("\\n".join(sorted(h_i))))` — the members' chain hashes sorted by code point."""
    return "sha256:" + sha256_hex("\n".join(sorted(member_hs)).encode("utf-8"))


def format_sig(alg: str, key_fpr: str, raw: bytes) -> str:
    """`<alg>:<key_fpr>:<base64>` — one format for every backend."""
    return f"{alg}:{key_fpr}:{base64.b64encode(raw).decode('ascii')}"


def parse_sig(sig: str) -> tuple[str, str, bytes]:
    parts = sig.split(":", 2)
    if len(parts) != 3 or parts[0] not in SIG_ALGS or not parts[1] or not parts[2]:
        raise Refusal("sig.format", "", sig[:32])
    try:
        raw = base64.b64decode(parts[2], validate=True)
    except ValueError as e:
        raise Refusal("sig.format", "", "base64") from e
    return parts[0], parts[1], raw


def fingerprint(raw_public: bytes) -> str:
    """`key_fpr`: the raw public key bytes in lowercase hex (the build pin above)."""
    return raw_public.hex()


@dataclass(frozen=True)
class PublicKey:
    """A verification key: `alg` ∈ SIG_ALGS, `raw` the public bytes (Ed25519 raw 32; P-256 SEC1 compressed 33)."""

    alg: str
    raw: bytes
    key_fpr: str = field(init=False)

    def __post_init__(self) -> None:
        if self.alg not in SIG_ALGS:
            raise Refusal("sig.alg", "", self.alg)
        if (self.alg == "ed25519" and len(self.raw) != 32) or (self.alg == "ecdsa-p256" and len(self.raw) != 33):
            raise Refusal("sig.key-bytes", "", f"{self.alg}: {len(self.raw)} bytes")
        object.__setattr__(self, "key_fpr", fingerprint(self.raw))

    @classmethod
    def from_fpr(cls, alg: str, key_fpr: str) -> PublicKey:
        try:
            return cls(alg, bytes.fromhex(key_fpr))
        except ValueError as e:
            raise Refusal("sig.format", "", "key_fpr is not hex") from e

    def verify(self, msg: bytes, signature: bytes) -> bool:
        try:
            if self.alg == "ed25519":
                ed25519.Ed25519PublicKey.from_public_bytes(self.raw).verify(signature, msg)
            else:
                if len(signature) != 64:
                    return False
                r, s = int.from_bytes(signature[:32], "big"), int.from_bytes(signature[32:], "big")
                key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), self.raw)
                key.verify(encode_dss_signature(r, s), msg, ec.ECDSA(hashes.SHA256()))
        except (InvalidSignature, ValueError):
            return False
        return True


KeyRing = Mapping[str, PublicKey]  # key_fpr -> key


def verify_sig(sig: str, tenant: str, value: str, keys: KeyRing | None = None) -> bool:
    """Verify `sig` over `tenant ‖ value` against the key its fingerprint IS (the pin above); with a key ring given,
    the fingerprint must also be in it. Membership (the binding) is the caller's next check — validity alone never
    decides (1.12)."""
    try:
        alg, fpr, raw = parse_sig(sig)
        key = keys[fpr] if keys is not None else PublicKey.from_fpr(alg, fpr)
    except (Refusal, KeyError):
        return False
    if key.alg != alg:
        return False
    return key.verify(sig_bytes(tenant, value), raw)


def binding_holds(policy_entries: Sequence[Mapping[str, Any]], key_fpr: str, grant: str, at: str) -> bool:
    """Membership, not validity (1.12): look the key up at (key_fpr, at) in the policy chain's `binding` entries —
    `act = "binding"`, the record in `ref`, `until` absent while open. A past act is judged against the binding that
    held then: the latest binding record for that key and grant whose `from` ≤ `at`, and `at` < its `until`."""
    held: Mapping[str, Any] | None = None
    for e in policy_entries:
        if e.get("act") != "binding":
            continue
        b = e.get("ref")
        if not isinstance(b, Mapping) or b.get("key_fpr") != key_fpr or b.get("grant") != grant:
            continue
        if str(b.get("from", "")) > at:
            continue
        held = b
    return held is not None and ("until" not in held or at < str(held["until"]))
