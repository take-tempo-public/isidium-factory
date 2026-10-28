"""The signing service's state machine: requests in, a signature out only after the owner's Aegis code.

`submit` and `poll` are what the API listener (`http.py`) exposes to a named caller; `approve` is a Python method
only, called by the code-entry page the next card builds. Three things make a signature rare:

- the key and the TOTP secret live in files only this service's user can read, and are never rendered (C3);
- each code is bound to one request and its time step is consumed once, durably, before anything is signed (R3);
- a request has a lifetime and a wrong-code budget, both from the settings (C2).

Every refusal is a `signer.*` rule (C5). Two counters (C-11), neither carrying a caller, a value or a code:
`isidium.signer.refusal` keyed by rule, and `isidium.signer.signed`.
"""

from __future__ import annotations

import json
import os
import secrets
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from opentelemetry import metrics

from isidium.store.core import chain
from isidium.store.core.refusal import Refusal

from . import totp
from .settings import Settings

_meter = metrics.get_meter("isidium.signer")
REFUSAL: Final = _meter.create_counter("isidium.signer.refusal", description="requests the signing service refused")
SIGNED: Final = _meter.create_counter("isidium.signer.signed", description="signatures the signing service produced")
_RULE: Final = "rule"

_PENDING: Final = "pending"
_SIGNED: Final = "signed"
_DECLINED: Final = "declined"
_GROUP_OTHER_BITS: Final = 0o077


@dataclass
class _Request:
    caller: str
    tenant: str
    value: str
    display: Sequence[Any]
    created: int
    wrong: int = 0
    status: str = _PENDING
    sig: str | None = None
    closed_at: int | None = None


def _refuse(rule: str, path: str = "", detail: str = "") -> Refusal:
    REFUSAL.add(1, {_RULE: rule})
    return Refusal(rule, path, detail)


def _owner_only(path: Path) -> None:
    """On POSIX a secret file readable by group or other is refused, naming the path and never the content. Windows
    has no mode bits to read, so the check cannot run there."""
    if os.name != "posix":
        return
    if path.stat().st_mode & _GROUP_OTHER_BITS:
        raise _refuse("signer.secret-permissions", str(path), "only the service's user may read this file")


class Service:
    """`clock` is required (epoch seconds): the deployment passes `lambda: int(time.time())`, a test a fake."""

    def __init__(self, settings: Settings, clock: Callable[[], int]) -> None:
        self.settings = settings
        self._clock = clock
        self._lock = threading.Lock()
        _owner_only(settings.signing_key)
        _owner_only(settings.totp_secret)
        key = serialization.load_pem_private_key(settings.signing_key.read_bytes(), password=None)
        if not isinstance(key, ed25519.Ed25519PrivateKey):
            raise _refuse("signer.key-type", str(settings.signing_key), "an Ed25519 private key is required")
        self._key = key
        self._secret = totp.secret_from_base32(settings.totp_secret.read_text(encoding="ascii"))
        raw = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        self.key_fpr = chain.fingerprint(raw)
        self._last_step = self._read_state()
        self._requests: dict[str, _Request] = {}

    def __repr__(self) -> str:  # C3: nothing secret is ever rendered
        return f"Service(key_fpr={self.key_fpr!r})"

    # ---- the state file: the last consumed step, so a restart cannot replay a code ---------------------------------

    def _read_state(self) -> int:
        path = self.settings.state
        if not path.exists():
            return -1  # no step consumed yet
        try:
            step = json.loads(path.read_text(encoding="utf-8"))["last_step"]
        except (OSError, ValueError, KeyError, TypeError) as e:
            raise _refuse("signer.state", str(path), "the state file cannot be read") from e
        if isinstance(step, bool) or not isinstance(step, int):
            raise _refuse("signer.state", str(path), "last_step must be an integer")
        return step

    def _write_state(self, step: int) -> None:
        """Atomically: a temp file in the same directory, then a rename."""
        path = self.settings.state
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps({"last_step": step}))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)

    # ---- housekeeping ----------------------------------------------------------------------------------------------

    def _housekeeping(self) -> None:
        """Under the lock, at the top of every public method: **expire, then sweep, in that order.** An expired
        request is marked declined with `closed_at = created + lifetime` and stays in the table for one more
        lifetime, so its poll reads `signer.declined` rather than `signer.unknown-request`; only then is it dropped.
        Linear in the table, which is bounded: pending by callers x max_pending_per_caller, closed ones by time."""
        now, life = self._clock(), self.settings.request_lifetime_s
        for r in self._requests.values():
            if r.status == _PENDING and now >= r.created + life:
                r.status, r.closed_at = _DECLINED, r.created + life
        for rid in [i for i, r in self._requests.items() if r.closed_at is not None and now >= r.closed_at + life]:
            del self._requests[rid]

    # ---- the contract's two calls, and the page's one --------------------------------------------------------------

    def submit(
        self, caller: str, tenant: str, value: str, at_epoch: int, display: Sequence[Any], time_skew_s: int | None
    ) -> str:
        with self._lock:
            self._housekeeping()
            if caller not in self.settings.callers:
                raise _refuse("signer.unknown-caller")
            # The settings' skew is the ceiling: a caller's own value can only narrow it, never widen it.
            skew = self.settings.time_skew_s if time_skew_s is None else min(self.settings.time_skew_s, time_skew_s)
            if abs(at_epoch - self._clock()) > skew:
                raise _refuse("signer.time-skew", "", f"request at {at_epoch} outside the signer's clock +/- {skew}s")
            pending = sum(1 for r in self._requests.values() if r.caller == caller and r.status == _PENDING)
            if pending >= self.settings.max_pending_per_caller:
                raise _refuse("signer.rate-limited", "", f"{pending} requests pending")
            rid = secrets.token_urlsafe(16)
            self._requests[rid] = _Request(caller, tenant, value, display, self._clock())
            return rid

    def poll(self, caller: str, request_id: str) -> str | None:
        with self._lock:
            self._housekeeping()
            r = self._requests.get(request_id)
            if r is None or r.caller != caller:  # another caller's request is as unknown as a swept one
                raise _refuse("signer.unknown-request")
            if r.status == _DECLINED:
                raise _refuse("signer.declined", "", request_id)
            return r.sig if r.status == _SIGNED else None

    def approve(self, request_id: str, code: str) -> None:
        with self._lock:
            self._housekeeping()
            r = self._requests.get(request_id)
            if r is None:
                raise _refuse("signer.unknown-request")
            if r.status == _DECLINED:
                raise _refuse("signer.declined", "", request_id)
            if r.status == _SIGNED:
                raise _refuse("signer.not-pending", "", request_id)
            step = totp.matching_step(self._secret, code, self._clock())
            if step is None or step <= self._last_step:
                # A replayed code spends the same budget as a guess.
                rule = "signer.wrong-code" if step is None else "signer.code-reused"
                r.wrong += 1
                if r.wrong >= self.settings.max_wrong_codes:
                    r.status, r.closed_at = _DECLINED, self._clock()
                    raise _refuse("signer.declined", "", request_id)
                raise _refuse(rule)
            # The step is made durable *before* the signature exists: a crash between the two costs the owner one
            # code, and the other order would let a restart sign twice on one code.
            self._write_state(step)
            self._last_step = step
            raw = self._key.sign(chain.sig_bytes(r.tenant, r.value))
            r.sig = chain.format_sig("ed25519", self.key_fpr, raw)
            r.status, r.closed_at = _SIGNED, self._clock()
            SIGNED.add(1)
