"""The signer seam (03 §1.12; W10; 7bc.3; 7bf.4 B3). The store asks the seam for a signature over `tenant ‖ h` (or the
batch hash) and gets bytes back — it never holds a ratifier key. Each signature is an un-cacheable act shown by
something the session cannot write to; every backend records `at` against its own clock ± `time_skew`.

Built backends (v1): `software_key_ack` — a client-side Ed25519 key file under the owner's user, a visible waiver
(`ratification.software_key_ack = "<the owner's words>"`), every signature software-grade; `remote-totp` — the client
half: submit `{tenant, hash, display}` to the signing service in the owner-only zone (agent-station, by pointer),
poll for the signature the service produced after the owner entered an Aegis code in the service's own UI, and
verify that signature against the configured service key before it is used. The service contract is
`RemoteTotpContract` below; `DevStubService` is the in-process stand-in the tests drive.

**The HTTPS transport (`HttpsService`) lives here, beside `RemoteTotp`**, and not in `isidium-signer` (card 54, C1):
the store's image must not carry the signing service, so the store neither depends on nor imports that package. The
wire is `isidium.signer.http`'s, kept compatible by a test that drives this client against the service's real
listener (`tests/store/test_remote_signer.py`).
Declared-but-unbuilt backends refuse with the available set (`signer.backend-unavailable`, registry/config.py).
"""

from __future__ import annotations

import time  # module scope: `RemoteTotp`'s defaults (`time.sleep`, `time.monotonic`) read it at definition (C-13)
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

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


@runtime_checkable
class KeyedService(Protocol):
    """A service that can announce the key it signs with (card 56, R1). Kept apart from `RemoteTotpContract` so a
    stand-in that only submits and polls still satisfies the contract."""

    def announce_key(self) -> str: ...


class RemoteTotp:
    def __init__(
        self,
        service: RemoteTotpContract,
        key_fpr: str,
        poll_interval_ms: int,
        timeout_s: int = 600,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        """`poll_interval_ms` is **supplied, never defaulted here** — `config@1` declares it under
        `signer.remote-totp` and a second copy in the binary is what C-1 forbids. The caller reads it from the
        effective config and passes it in. `timeout_s` is NOT the same case and is deliberately left: the declared
        key is `time_skew`, a different key that happens to share the number 600.

        `timeout_s` bounds the owner's wait **by the clock**, every round trip included, and not by a sum of the sleeps
        (R5): a service that is slow to answer each poll would otherwise stretch the wait without limit. The clock
        runs from `started` — the moment the store received the call, which `Store._sign` passes in, so the store's own
        work before the submit counts — or from the submit when no start is given. Every poll, the first included,
        starts before the deadline. So for a service that answers each call within c in total (R5's condition) the
        whole wait is at most `timeout_s` plus c, and `serve` keeps that sum plus the store's post-signature margin
        (`store.POST_SIGNATURE_MARGIN_S`: the fetch, commit and push after the signature) under the client channel's
        timeout: the store answers `signer.timeout` before its caller's channel gives up. A service that trickles a
        single call past c is outside that bound. `sleep` and `monotonic` are seams for the tests, not policy."""
        self.backend = "remote-totp"
        self.service, self.key_fpr = service, key_fpr
        self.poll_interval_ms, self.timeout_s, self._sleep = poll_interval_ms, timeout_s, sleep
        self._monotonic = monotonic
        self.calls = 0
        self.shown: list[Display] = []

    def sign(
        self,
        tenant: str,
        value: str,
        at_epoch: int,
        display: Display,
        time_skew_s: int | None = None,
        started: float | None = None,
    ) -> str:
        self.calls += 1
        self.shown.append(display)
        start = self._monotonic() if started is None else started
        rid = self.service.submit(tenant, value, at_epoch, display, time_skew_s)
        while (left := self.timeout_s - (self._monotonic() - start)) > 0:
            sig = self.service.poll(rid)
            if sig is not None:
                return self._verified(sig, tenant, value)
            self._sleep(min(self.poll_interval_ms / 1000, left))
        raise Refusal("signer.timeout", "", f"remote-totp request {rid} not approved within {self.timeout_s}s")

    def service_key(self) -> str:
        """The key fingerprint the service announces, checked against the configured one before anything is
        submitted (card 56, R1): an enrolment binds the key the service holds, so a service that announces another
        key than `--signing-service-fpr` is refused here and no request reaches its page."""
        if not isinstance(self.service, KeyedService):
            raise Refusal("signer.backend-unavailable", "", "this service cannot announce its key")
        fpr = self.service.announce_key()
        if fpr != self.key_fpr:
            raise Refusal("signer.wrong-key", "", f"the service announces key {fpr}, not the configured {self.key_fpr}")
        return fpr

    def _verified(self, sig: str, tenant: str, value: str) -> str:
        """A signature the service produced is checked before it is used (R6): it parses, it is by the configured
        service key (`--signing-service-fpr`), and it verifies over `tenant ‖ value`. A failure is refused in the
        `signer.` namespace — raised inside the ratify's transaction, before anything is emitted, so nothing is signed
        or journaled. `verify_sig` checks against the key the fingerprint IS, so the two checks together mean exactly
        the configured key signed exactly this value."""
        try:
            _, fpr, _ = chain.parse_sig(sig)
        except Refusal as e:
            raise Refusal("signer.bad-signature", "", f"the service's signature does not parse: {e.detail}") from e
        if fpr != self.key_fpr:
            raise Refusal("signer.wrong-key", "", f"the signature is by key {fpr}, not the configured {self.key_fpr}")
        if not chain.verify_sig(sig, tenant, value):
            raise Refusal("signer.bad-signature", "", f"the signature by {fpr} does not verify over this value")
        return sig


class HttpsService:
    """`RemoteTotpContract` over HTTPS: one connection per call, the service's certificate verified against `ca`
    (hostname checking on, TLS 1.3 floor) and this client's certificate presented. Every argument is required.

    The wire is `isidium.signer.http.HttpsService`'s: `POST /key {}` answers `{key_fpr}`;
    `POST /submit {tenant, value, at_epoch, display, time_skew_s}` answers `{request_id}`;
    `POST /poll {request_id}` answers `{sig}`, `null` while pending. A non-200 carrying a `rule` is rebuilt as that
    `Refusal`; anything else is `signer.malformed`. `timeout_s` is http.client's per-socket-operation timeout
    (connect, each send, each receive), not a whole-call deadline, and not the owner's whole wait: that is
    `RemoteTotp`'s."""

    def __init__(self, host: str, port: int, ca: Path, cert: Path, key: Path, timeout_s: float) -> None:
        import ssl  # C-13: only a store given a signing service pays for `ssl`, `http.client` and `json`

        self.host, self.port, self.timeout_s = host, port, timeout_s
        self._context = ssl.create_default_context(cafile=str(ca))
        self._context.minimum_version = ssl.TLSVersion.TLSv1_3
        self._context.load_cert_chain(str(cert), str(key))

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        import http.client  # C-13, as in `__init__`
        import json

        conn = http.client.HTTPSConnection(self.host, self.port, context=self._context, timeout=self.timeout_s)
        # A transport failure is a typed refusal, not a bare OSError: ratify's answer must name it (R4, C-5), and
        # `Service.handle` would otherwise answer a timeout `service.internal` and a certificate that does not verify
        # (an `ssl.SSLCertVerificationError` is also a `ValueError`) `service.arguments`, blaming the owner's request.
        # `TimeoutError` is an `OSError`, so it is caught first.
        try:
            conn.request("POST", path, json.dumps(body).encode("utf-8"), {"Content-Type": "application/json"})
            response = conn.getresponse()
            status, data = response.status, response.read()
        except TimeoutError as e:
            raise Refusal("signer.timeout", "", f"the service did not answer {path} within {self.timeout_s}s") from e
        except (OSError, http.client.HTTPException) as e:
            detail = f"the service at {self.host}:{self.port} failed {path}: {e!r}"
            raise Refusal("signer.unreachable", "", detail) from e
        finally:
            conn.close()
        try:
            payload = json.loads(data)
        except ValueError:
            payload = None
        if status != 200:
            if isinstance(payload, dict) and isinstance(payload.get("rule"), str):
                raise Refusal(payload["rule"], "", str(payload.get("detail", "")))
            raise Refusal("signer.malformed", "", f"the service answered {status} with no refusal")
        if not isinstance(payload, dict):
            raise Refusal("signer.malformed", "", "the service's answer is not an object")
        return payload

    def announce_key(self) -> str:
        payload = self._post("/key", {})
        if not isinstance(payload.get("key_fpr"), str):
            raise Refusal("signer.malformed", "", "the service's answer to /key carries no key_fpr")
        return str(payload["key_fpr"])

    def submit(self, tenant: str, value: str, at_epoch: int, display: Display, time_skew_s: int | None = None) -> str:
        payload = self._post(
            "/submit",
            {
                "tenant": tenant,
                "value": value,
                "at_epoch": at_epoch,
                "display": list(display),
                "time_skew_s": time_skew_s,
            },
        )
        if not isinstance(payload.get("request_id"), str):
            raise Refusal("signer.malformed", "", "the service's answer to /submit carries no request_id")
        return str(payload["request_id"])

    def poll(self, request_id: str) -> str | None:
        payload = self._post("/poll", {"request_id": request_id})
        if "sig" not in payload:
            raise Refusal("signer.malformed", "", "the service's answer to /poll carries no sig")
        sig = payload["sig"]
        return None if sig is None else str(sig)


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
        self.key_public_fpr = key.public.key_fpr
        self.approve_after, self.decline = approve_after, decline
        self.requests: dict[str, tuple[str, str, Display, int]] = {}
        self.received: list[Display] = []

    def submit(self, tenant: str, value: str, at_epoch: int, display: Display, time_skew_s: int | None = None) -> str:
        _check_skew(at_epoch, self.clock, self.time_skew_s if time_skew_s is None else time_skew_s)
        rid = f"r{len(self.requests) + 1}"
        self.requests[rid] = (tenant, value, display, 0)
        self.received.append(display)
        return rid

    def announce_key(self) -> str:
        return self.key_public_fpr

    def poll(self, request_id: str) -> str | None:
        tenant, value, display, polls = self.requests[request_id]
        if self.decline:
            raise Refusal("signer.declined", "", request_id)
        self.requests[request_id] = (tenant, value, display, polls + 1)
        if polls < self.approve_after:
            return None
        return chain.format_sig("ed25519", self.key.public.key_fpr, self.key.sign_raw(chain.sig_bytes(tenant, value)))
