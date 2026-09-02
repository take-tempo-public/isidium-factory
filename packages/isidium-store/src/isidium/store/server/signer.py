"""The signer seam (03 §1.12; W10; 7bc.3; 7bf.4 B3). The store asks the seam for a signature over `tenant ‖ h` (or the
batch hash) and gets bytes back — it never holds a ratifier key. Each signature is an un-cacheable act shown by
something the session cannot write to; every backend records `at` against its own clock ± `time_skew`.

Built backends (v1): `software_key_ack` — a client-side Ed25519 key file under the owner's user, a visible waiver
(`ratification.software_key_ack = "<the owner's words>"`), every signature software-grade; `remote-totp` — the client
half only: submit `{tenant, hash, display}` to the signing service in the owner-only zone (agent-station, by pointer),
poll for the signature the service produced after the owner entered an Aegis code in the service's own UI. The
service contract is `RemoteTotpContract` below; `DevStubService` is the in-process stand-in the tests drive.
Declared-but-unbuilt backends refuse with the available set (`signer.backend-unavailable`, registry/config.py).
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from ..core import chain
from ..core.refusal import Refusal

Display = Sequence[
    Any
]  # what the signer shows: per member (id · act · build hash · changes since the last signed entry)
Clock = Callable[[], int]  # epoch seconds


class Signer(Protocol):
    backend: str
    key_fpr: str

    def sign(self, tenant: str, value: str, at_epoch: int, display: Display, time_skew_s: int | None = None) -> str: ...


def _check_skew(at_epoch: int, clock: Clock, time_skew_s: int) -> None:
    if abs(at_epoch - clock()) > time_skew_s:
        raise Refusal("signer.time-skew", "", f"request at {at_epoch} outside the signer's clock ± {time_skew_s}s")


# ---- software_key_ack ---------------------------------------------------------------------------------------------


@dataclass
class SoftwareKey:
    """An Ed25519 keypair on disk (PEM, no passphrase — the waiver is the point) or in memory."""

    private: ed25519.Ed25519PrivateKey
    public: chain.PublicKey = field(init=False)

    def __post_init__(self) -> None:
        raw = self.private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        self.public = chain.PublicKey("ed25519", raw)

    @classmethod
    def generate(cls) -> SoftwareKey:
        return cls(ed25519.Ed25519PrivateKey.generate())

    @classmethod
    def load(cls, path: str | Path) -> SoftwareKey:
        key = serialization.load_pem_private_key(Path(path).read_bytes(), password=None)
        if not isinstance(key, ed25519.Ed25519PrivateKey):
            raise Refusal("signer.key-type", str(path), "an Ed25519 private key is required")
        return cls(key)

    def save(self, path: str | Path) -> None:
        pem = self.private.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
        Path(path).write_bytes(pem)

    def sign_raw(self, msg: bytes) -> bytes:
        return self.private.sign(msg)


class SoftwareKeyAck:
    """The waiver backend: signs locally, labeled software-grade. `shown` keeps what each request displayed — the
    scenarios assert the display (X1) through it."""

    def __init__(self, key: SoftwareKey, clock: Clock | None = None, time_skew_s: int = 600) -> None:
        self.backend = "software_key_ack"
        self.key = key
        self.clock: Clock = clock or (lambda: int(time.time()))
        self.time_skew_s = time_skew_s
        self.key_fpr = key.public.key_fpr
        self.calls = 0
        self.shown: list[Display] = []

    def sign(self, tenant: str, value: str, at_epoch: int, display: Display, time_skew_s: int | None = None) -> str:
        _check_skew(at_epoch, self.clock, self.time_skew_s if time_skew_s is None else time_skew_s)
        self.calls += 1
        self.shown.append(display)
        return chain.format_sig("ed25519", self.key_fpr, self.key.sign_raw(chain.sig_bytes(tenant, value)))


# ---- remote-totp: the client half + the contract + a dev stub ------------------------------------------------------


class RemoteTotpContract(Protocol):
    """What the signing service exposes (the transport — HTTPS + mTLS to the registration's address — is the
    client's; the service's UI and TOTP check are agent-station's, by pointer). Two calls:

    `submit(tenant, hash, at_epoch, display) -> request_id` — the service renders card · act · hash · the display it
    RECEIVED in its own UI and takes the Aegis code there; each code is consumed once, bound to this request.
    `poll(request_id) -> sig | None` — the `alg:key_fpr:base64` signature once approved; None while pending; a
    `Refusal("signer.declined")` when the owner declined or the request expired."""

    def submit(
        self, tenant: str, value: str, at_epoch: int, display: Display, time_skew_s: int | None = None
    ) -> str: ...
    def poll(self, request_id: str) -> str | None: ...


class RemoteTotp:
    def __init__(
        self,
        service: RemoteTotpContract,
        key_fpr: str,
        poll_interval_ms: int,
        timeout_s: int = 600,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """`poll_interval_ms` is **supplied, never defaulted here** — `config@1` declares it under
        `signer.remote-totp` and a second copy in the binary is what C-1 forbids. The caller reads it from the
        effective config and passes it in. `timeout_s` is NOT the same case and is deliberately left: the declared
        key is `time_skew`, a different key that happens to share the number 600."""
        self.backend = "remote-totp"
        self.service, self.key_fpr = service, key_fpr
        self.poll_interval_ms, self.timeout_s, self._sleep = poll_interval_ms, timeout_s, sleep
        self.calls = 0
        self.shown: list[Display] = []

    def sign(self, tenant: str, value: str, at_epoch: int, display: Display, time_skew_s: int | None = None) -> str:
        self.calls += 1
        self.shown.append(display)
        rid = self.service.submit(tenant, value, at_epoch, display, time_skew_s)
        waited = 0.0
        while waited <= self.timeout_s:
            sig = self.service.poll(rid)
            if sig is not None:
                return sig
            self._sleep(self.poll_interval_ms / 1000)
            waited += self.poll_interval_ms / 1000
        raise Refusal("signer.timeout", "", f"remote-totp request {rid} not approved within {self.timeout_s}s")


class DevStubService:
    """An in-process stand-in for the signing service: holds one software key, checks the skew against its own
    clock, approves after `approve_after` polls (0 = at once), or declines when told."""

    def __init__(
        self,
        key: SoftwareKey,
        clock: Clock | None = None,
        time_skew_s: int = 600,
        approve_after: int = 0,
        decline: bool = False,
    ) -> None:
        self.key, self.clock, self.time_skew_s = key, clock or (lambda: int(time.time())), time_skew_s
        self.approve_after, self.decline = approve_after, decline
        self.requests: dict[str, tuple[str, str, Display, int]] = {}
        self.received: list[Display] = []

    def submit(self, tenant: str, value: str, at_epoch: int, display: Display, time_skew_s: int | None = None) -> str:
        _check_skew(at_epoch, self.clock, self.time_skew_s if time_skew_s is None else time_skew_s)
        rid = f"r{len(self.requests) + 1}"
        self.requests[rid] = (tenant, value, display, 0)
        self.received.append(display)
        return rid

    def poll(self, request_id: str) -> str | None:
        tenant, value, display, polls = self.requests[request_id]
        if self.decline:
            raise Refusal("signer.declined", "", request_id)
        self.requests[request_id] = (tenant, value, display, polls + 1)
        if polls < self.approve_after:
            return None
        return chain.format_sig("ed25519", self.key.public.key_fpr, self.key.sign_raw(chain.sig_bytes(tenant, value)))
