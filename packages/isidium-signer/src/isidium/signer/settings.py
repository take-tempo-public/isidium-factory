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

    [page]                                    # the page's own listener: `load_page` requires it, `load` does not
    host = "signer.example.invalid"
    port = 8444
    tls_certificate = "tls/page.crt.pem"      # a different certificate from the API's: the phone dials another name
    tls_key = "tls/page.key.pem"
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


_PAGE = "page"  # the one table; `load` knows it and leaves it to `load_page`
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


@dataclass(frozen=True)
class PageSettings:
    """Where the code-entry page listens and the certificate it proves itself with. The page asks no client
    certificate, so it has no CA of its own; its timeouts and body limit are the API's, from `Settings`."""

    host: str
    port: int
    tls_certificate: Path
    tls_key: Path


def _read(path: Path) -> dict[str, Any]:
    try:
        return tomllib.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise _bad("", f"the settings file cannot be read: {type(e).__name__}") from e


def _path_value(key: str, value: Any, here: Path) -> Path:
    if not isinstance(value, str) or not value:
        raise _bad(key, "a path string is required")
    return here / value  # an absolute path keeps itself: `here / "/x"` is "/x"


def load_page(path: Path) -> PageSettings:
    """The `[page]` table, every key required and none unknown, by the rules `load` applies to the rest. Only the
    process that serves the page calls this; a settings file without the table is still a valid `load`."""
    raw = _read(path)
    table = raw.get(_PAGE)
    if table is None:
        raise _bad(_PAGE, "missing")
    if not isinstance(table, dict):
        raise _bad(_PAGE, "a table is required")
    names = [f.name for f in fields(PageSettings)]
    for name in names:
        if name not in table:
            raise _bad(f"{_PAGE}.{name}", "missing")
    for name in table:
        if name not in names:
            raise _bad(f"{_PAGE}.{name}", "unknown")
    if not isinstance(table["host"], str) or not table["host"]:
        raise _bad(f"{_PAGE}.host", "a host string is required")
    here = Path(path).resolve().parent
    return PageSettings(
        host=table["host"],
        port=_integer(f"{_PAGE}.port", table["port"], 0),  # 0 binds an ephemeral port (tests)
        tls_certificate=_path_value(f"{_PAGE}.tls_certificate", table["tls_certificate"], here),
        tls_key=_path_value(f"{_PAGE}.tls_key", table["tls_key"], here),
    )


def load(path: Path) -> Settings:
    """Read and check the settings file; the first problem found is the refusal."""
    raw = _read(path)
    names = [f.name for f in fields(Settings)]
    for name in names:
        if name not in raw:
            raise _bad(name, "missing")
    for name in raw:
        if name not in names and name != _PAGE:
            raise _bad(name, "unknown")
    here = Path(path).resolve().parent
    values: dict[str, Any] = {}
    for name in _PATHS:
        values[name] = _path_value(name, raw[name], here)
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
    if not callers:
        raise _bad("callers", "at least one caller is required")  # a service nobody may call is a misconfiguration
    values["callers"] = frozenset(callers)
    return Settings(**values)
