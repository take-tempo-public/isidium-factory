"""The factory's per-tenant registration on the local tier — `tenant.toml` at the deploy home [V3, Q-V12 ruled
2026-09-11].

04 §5 names the tenant registration *"factory-side, out of the repo"* and leaves its home to agent-station by pointer;
on the local tier (L2's ruling) a human writes the files at `$ISIDIUM_DEPLOY/<tenant>/factory/`, and this is the third
beside `client.toml` (the lander's store half) and `forge.toml` (its forge half). On the realm tier the realm writes it;
nothing here reads differently.

**Every key is required, none is defaulted in code** (C-1): `wip` (T-A6's *"tenant-specializable"* cap), `adapter`
(the payload's identity half until V4 declares the adapter's own config), `[payload].max_bytes` (Q-V8 (a): the byte
cap the payload must fit). `allow_software_grade_until` is the one optional key, and its absence *is* the answer: a
software-grade ratification is not dispatched unattended (03 §1.12, Q-V5).
"""

from __future__ import annotations

import datetime as _dt
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from isidium.store.core.refusal import Refusal

REGISTRATION_FILE: Final = "tenant.toml"
RULE: Final = "factory.registration"


@dataclass(frozen=True)
class Registration:
    """04 §5's registration at the amplitude V3 reads."""

    allow_software_grade_until: _dt.date | None
    wip: int
    adapter: str
    max_bytes: int

    def allows_software_grade(self, today: _dt.date) -> bool:
        """03 §1.12: *"the factory refuses unattended dispatch of software-grade ratifications unless the registration
        carries `allow_software_grade_until`"* — through that date, inclusive."""
        return self.allow_software_grade_until is not None and today <= self.allow_software_grade_until

    def value(self) -> dict[str, Any]:
        out: dict[str, Any] = {"wip": self.wip, "adapter": self.adapter, "max_bytes": self.max_bytes}
        if self.allow_software_grade_until is not None:
            out["allow_software_grade_until"] = self.allow_software_grade_until.isoformat()
        return out

    @classmethod
    def load(cls, directory: Path) -> Registration | None:
        """`None` when the tenant has no `tenant.toml` (a tenant the factory pushes for but does not dispatch on:
        the V2 verbs need none); a file that is there is read whole or refused."""
        path = directory / REGISTRATION_FILE
        if not path.is_file():
            return None
        try:
            data: dict[str, Any] = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise Refusal(RULE, str(path), str(e)) from None
        wip = data.get("wip")
        adapter = data.get("adapter")
        payload = data.get("payload")
        max_bytes = payload.get("max_bytes") if isinstance(payload, dict) else None
        until = data.get("allow_software_grade_until")
        bad: list[str] = []
        if not isinstance(wip, int) or isinstance(wip, bool) or wip < 1:
            bad.append("wip (an integer >= 1)")
        if not isinstance(adapter, str) or not adapter:
            bad.append("adapter (a name)")
        if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes < 1:
            bad.append("[payload].max_bytes (an integer >= 1)")
        # A TOML date, never a datetime: the allowance is a calendar day, and a time would invite a zone.
        if until is not None and (not isinstance(until, _dt.date) or isinstance(until, _dt.datetime)):
            bad.append("allow_software_grade_until (a TOML date, YYYY-MM-DD)")
        unknown = sorted(set(data) - {"wip", "adapter", "payload", "allow_software_grade_until"})
        if unknown:
            bad.append("unknown keys " + ", ".join(unknown))
        if bad:
            raise Refusal(RULE, str(path), "; ".join(bad))
        assert isinstance(wip, int) and isinstance(adapter, str) and isinstance(max_bytes, int)
        return cls(until, wip, adapter, max_bytes)


def require(reg: Registration | None, home: Path) -> Registration:
    """The dispatch verbs' precondition: a tenant with no registration is not one the factory dispatches on."""
    if reg is None:
        raise Refusal(RULE, str(home / REGISTRATION_FILE), "no registration for this tenant; see deploy/README.md")
    return reg
