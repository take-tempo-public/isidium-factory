"""The service's settings file: every limit and every path (C-1), none defaulted in code.

A TOML file, every key required, no key unknown. Relative paths resolve against the file's own directory. The file
names where the secrets are and never holds them. An example of its shape (a host here is never a real one):

    listen_host = "signer.example.invalid"
    listen_port = 8443
    tls_certificate = "tls/server.crt.pem"
    tls_key = "tls/server.key.pem"
    ca = "tls/ca.crt.pem"
    callers = ["CN=store.example.invalid"]    # RFC 4514 subjects of the client certificates that may call
    signing_key = "keys/signing.pem"
    totp_secret = "keys/totp.base32"
    state = "state/signer.json"
    time_skew_s = 600
    max_pending_per_caller = 4
    max_wrong_codes = 3
    request_lifetime_s = 600
    handshake_timeout_s = 10.0
    read_timeout_s = 30.0
    max_body_bytes = 65536
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

from isidium.store.core.refusal import Refusal


@dataclass(frozen=True)
class Settings:
    listen_host: str
    listen_port: int
    tls_certificate: Path
    tls_key: Path
    ca: Path
    callers: frozenset[str]
    signing_key: Path
    totp_secret: Path
    state: Path
    time_skew_s: int
    max_pending_per_caller: int
    max_wrong_codes: int
    request_lifetime_s: int
    handshake_timeout_s: float
    read_timeout_s: float
    max_body_bytes: int


_PATHS = ("tls_certificate", "tls_key", "ca", "signing_key", "totp_secret", "state")
_INTS = ("time_skew_s", "max_pending_per_caller", "max_wrong_codes", "request_lifetime_s", "max_body_bytes")
_FLOATS = ("handshake_timeout_s", "read_timeout_s")


def _bad(key: str, why: str) -> Refusal:
    return Refusal("signer.settings", key, why)


def _integer(key: str, value: Any, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _bad(key, "an integer is required")
    if value < minimum:
        raise _bad(key, f"at least {minimum} is required")
    return value


def load(path: Path) -> Settings:
    """Read and check the settings file; the first problem found is the refusal."""
    try:
        raw: dict[str, Any] = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise _bad("", f"the settings file cannot be read: {type(e).__name__}") from e
    names = [f.name for f in fields(Settings)]
    for name in names:
        if name not in raw:
            raise _bad(name, "missing")
    for name in raw:
        if name not in names:
            raise _bad(name, "unknown")
    here = Path(path).resolve().parent
    values: dict[str, Any] = {}
    for name in _PATHS:
        if not isinstance(raw[name], str) or not raw[name]:
            raise _bad(name, "a path string is required")
        values[name] = here / raw[name]  # an absolute path keeps itself: `here / "/x"` is "/x"
    for name in _INTS:
        values[name] = _integer(name, raw[name], 1)
    values["listen_port"] = _integer("listen_port", raw["listen_port"], 0)  # 0 binds an ephemeral port (tests)
    for name in _FLOATS:
        v = raw[name]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0:
            raise _bad(name, "a positive number is required")
        values[name] = float(v)
    if not isinstance(raw["listen_host"], str) or not raw["listen_host"]:
        raise _bad("listen_host", "a host string is required")
    values["listen_host"] = raw["listen_host"]
    callers = raw["callers"]
    if not isinstance(callers, list) or not all(isinstance(c, str) and c for c in callers):
        raise _bad("callers", "a list of subject strings is required")
    values["callers"] = frozenset(callers)
    return Settings(**values)
