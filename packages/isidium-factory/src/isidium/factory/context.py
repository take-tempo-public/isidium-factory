"""The tenant context (T-C1) — one typed value built once per run, which everything downstream reads instead of the
repo [V2, 2026-09-10].

T-C1: *"This is the crossing every run starts with; everything downstream reads a typed `TenantContext` from it, never
the repo ad hoc."* What is here is the context's own share of that row's nine matching conditions: (1) the tenant is
registered — the deploy home names it (L2's refusals); (2) the remote is reachable and the base ref exists on it — one
delta fetch, never a fresh clone (T-C1's efficiency line: *"fetched by delta on each trigger"*); (3) the tenant's
toolkit pin is inside the range this factory release reads — `TOOLKIT_RANGE`, refused *"naming the upgrade (T-C2)"*.
Conditions (4)–(7) resolve against the store at dispatch and (8) is the ledger's — they are V3's preconditions and are
not run here; (9), egress, is agent-station's by pointer, and the driver only **declares** the hosts it needs
(`forge.Capabilities.hosts`).

**Three `git` spawns per load** — the remote's url, the fetch, and one `cat-file --batch` that answers the fetched tip
and the config at it — held by a test. The config is read **at the fetched tip**, not from the working tree: the
context is a fact about `base`, and a working tree can be anywhere.

**The forge identity is a file beside the lander's** (Q-V9 (a), Q-V10, ruled 2026-09-10): `forge.toml` under the
tenant's `factory/` directory names the account — `login`, `name`, `email` — and the path of the token file, whose
one line is the secret. The token is in the context's value **nowhere** — not in `value()`, not in `hash` — and
reaches git and the API only through the driver. On the local tier a human writes both files (the recipe in
`deploy/README.md`); on the realm tier the realm does; nothing here reads differently.
"""

from __future__ import annotations

import re
import subprocess
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Final

from isidium.store.client.config import ClientConfig
from isidium.store.client.hook import registry_current
from isidium.store.core import canon, telemetry
from isidium.store.core.grammar import parse_config
from isidium.store.core.refusal import Refusal
from isidium.store.registry.config import CONFIG_ORDERS, SEMVER_CORE, resolve_effective, semver_tuple
from isidium.store.registry.loader import Registry

from .checkout import Cat, root_of
from .registration import tenant_client
from .tenant import Registration

SPAN: Final = "isidium.factory.context.load"
GIT_SPAWNS: Final = "isidium.git.spawns"
FORGE_FILE: Final = "forge.toml"

# The `[toolkit].client` versions this factory release reads: `[floor, ceiling)`. T-C1 (3): *"Toolkit version
# supported by this factory release (compat range); else refuse and say so, naming the upgrade (T-C2)."* Written
# where it bites (C-10) and nowhere else; a pin outside it is `factory.toolkit`. The range is the factory's own fact
# about itself — not a default for the tenant (C-1) — and moves when the factory learns a new client's shape.
TOOLKIT_RANGE: Final = ("0.1.0", "0.2.0")

# The remote url grammars the coords are parsed from — the two forms a forge hands out and the ssh:// spelling of
# the second. Anything else is `factory.forge-url`: the driver would not know which API to call.
_HTTPS: Final = re.compile(r"^https://([^/]+)/([^/]+)/([^/]+?)(?:\.git)?/?$")
_SCP: Final = re.compile(r"^(?:[^@]+@)?([^:/]+):([^/]+)/([^/]+?)(?:\.git)?$")
_SSH: Final = re.compile(r"^ssh://(?:[^@]+@)?([^/:]+)(?::\d+)?/([^/]+)/([^/]+?)(?:\.git)?$")


@dataclass(frozen=True)
class ForgeCoords:
    """Where the tenant's repository is: `host`, `owner`, `repo`, and the `remote` name the checkout knows it by."""

    host: str
    owner: str
    repo: str
    remote: str

    @classmethod
    def parse(cls, url: str, remote: str) -> ForgeCoords:
        for pat in (_HTTPS, _SSH, _SCP):
            m = pat.match(url.strip())
            if m:
                return cls(m.group(1), m.group(2), m.group(3), remote)
        raise Refusal("factory.forge-url", remote, f"not a forge url this factory can parse: {url!r}")


class ForgeKind(Enum):
    """How the identity authenticates — the two credential shapes a forge offers [V2b, ruled 2026-09-10 after the
    Terms finding]. `APP`: a GitHub App — an org-owned registration, no account, no email, no 2FA, no Terms count;
    the secret is the App's private key and the driver mints one-hour installation tokens from it. `TOKEN`: an
    account with a static token — a Gitea/Forgejo user (no App concept there), or the one free machine account
    GitHub's Terms allow a person; the secret is the token itself."""

    APP = "app"
    TOKEN = "token"


@dataclass(frozen=True)
class ForgeIdentity:
    """The principal the factory pushes and opens pull requests as (7f [owner]: *"its own git identifier and github
    account"*), read from `forge.toml` beside the lander's certificate: `kind`, `login`, `name`, `email`, and the
    secret file (`key` for an App, `token` for an account). `email` is the form the forge attributes commits by — on
    GitHub the bot user's `noreply` address — because a pull request whose commits no account claims is held for
    extra approval by tenant #0's ruleset. An App carries `app_id` and `installation_id` too; the tenant binding is
    the installation, the name is the function (the agent identity scheme's App row)."""

    kind: ForgeKind
    login: str
    name: str
    email: str
    secret: str = field(repr=False)
    app_id: int | None = None
    installation_id: int | None = None

    @classmethod
    def load(cls, directory: Path) -> ForgeIdentity:
        path = directory / FORGE_FILE
        if not path.is_file():
            raise Refusal("factory.no-forge", str(path), "no forge identity for this tenant; see deploy/README.md")
        try:
            data: dict[str, Any] = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise Refusal("factory.no-forge", str(path), str(e)) from None
        try:
            kind = ForgeKind(str(data.get("kind", "")))
        except ValueError:
            raise Refusal("factory.no-forge", str(path), 'kind must be "app" or "token"') from None
        secret_key = "key" if kind is ForgeKind.APP else "token"
        need = ["login", "name", "email", secret_key]
        missing = [k for k in need if not isinstance(data.get(k), str) or not data[k]]
        if kind is ForgeKind.APP:
            missing += [k for k in ("app_id", "installation_id") if not isinstance(data.get(k), int)]
        if missing:
            raise Refusal("factory.no-forge", str(path), f"missing {', '.join(missing)}")
        secret_path = directory / str(data[secret_key])
        try:
            secret = secret_path.read_text(encoding="utf-8").strip()
        except OSError as e:
            raise Refusal("factory.no-forge", str(secret_path), str(e)) from None
        if not secret:
            raise Refusal("factory.no-forge", str(secret_path), f"the {secret_key} file is empty")
        return cls(
            kind,
            str(data["login"]),
            str(data["name"]),
            str(data["email"]),
            secret,
            int(data["app_id"]) if kind is ForgeKind.APP else None,
            int(data["installation_id"]) if kind is ForgeKind.APP else None,
        )


@dataclass(frozen=True)
class ToolkitPins:
    """The tenant's four `[toolkit]` pins at `base`."""

    client: str
    registry: str
    unidata: str
    object_id: str

    @classmethod
    def of(cls, tree: Mapping[str, Any]) -> ToolkitPins:
        tk = tree.get("toolkit")
        if not isinstance(tk, Mapping):
            raise Refusal("factory.no-config", "[toolkit]", "the four pins are absent")
        return cls(
            str(tk.get("client", "")),
            str(tk.get("registry", "")),
            str(tk.get("unidata", "")),
            str(tk.get("object_id", "")),
        )


@dataclass(frozen=True)
class TenantContext:
    """T-C1's value at the amplitude v1c reads. `registry` is the checkout's installed registry, built **once** here
    (V1's finding 15: `gather` used to build one per payload); it is not part of the value, being a fact about the
    workstation and not the tenant."""

    tenant: str
    home: Path
    client: ClientConfig
    checkout: Path
    root: str
    base: str
    base_sha: str
    forge: ForgeCoords
    identity: ForgeIdentity
    toolkit: ToolkitPins
    governed: tuple[Mapping[str, Any], ...]
    registry: Registry = field(repr=False, compare=False)
    # V3: the factory's registration (`tenant.toml`, Q-V12) — `None` for a tenant the factory does not dispatch on —
    # and the effective config at `base` (the ordering's `[prioritization]`; not in the value: `governed` is its part
    # the context already names, and the rest is the payload's, hashed there as `config_hash`).
    registration: Registration | None = None
    eff: Mapping[str, Any] = field(default_factory=dict, repr=False, compare=False)

    def value(self) -> dict[str, Any]:
        """The context as data — everything a reader may compare, and **not the token**."""
        return {
            **({"registration": self.registration.value()} if self.registration is not None else {}),
            "form": "isidium-tenant-context 1",
            "tenant": self.tenant,
            "root": self.root,
            "base": self.base,
            "base_sha": self.base_sha,
            "forge": {"host": self.forge.host, "owner": self.forge.owner, "repo": self.forge.repo},
            "identity": {"login": self.identity.login, "name": self.identity.name, "email": self.identity.email},
            "toolkit": {
                "client": self.toolkit.client,
                "registry": self.toolkit.registry,
                "unidata": self.toolkit.unidata,
                "object_id": self.toolkit.object_id,
            },
            "governed": [dict(r) for r in self.governed],
        }

    @property
    def hash(self) -> str:
        """T-C1's observable: *"TenantContext hash (re-read and compare = round-trip)"*."""
        return canon.content_address(self.value())


def _remote_url(repo: Path, remote: str) -> str:
    r = subprocess.run(
        ["git", "config", "--get", f"remote.{remote}.url"], cwd=repo, capture_output=True, text=True, check=False
    )
    if r.returncode != 0 or not r.stdout.strip():
        raise Refusal("factory.forge-url", remote, f"the checkout has no remote named {remote}")
    return r.stdout.strip()


def _fetch(repo: Path, remote: str, ref: str) -> None:
    """One delta fetch of `ref`; the tip lands in `FETCH_HEAD` and the objects in the checkout."""
    r = subprocess.run(["git", "fetch", "-q", remote, ref], cwd=repo, capture_output=True, text=True, check=False)
    if r.returncode != 0:
        err = r.stderr.strip()
        absent = "couldn't find remote ref" in err or "invalid refspec" in err
        rule = "factory.no-base" if absent else "factory.unreachable"
        raise Refusal(rule, f"{remote}/{ref}", err.splitlines()[-1] if err else f"git fetch exited {r.returncode}")


def toolkit_check(pins: ToolkitPins) -> None:
    """T-C1 (3): the tenant's `[toolkit].client` inside `TOOLKIT_RANGE`, or `factory.toolkit` naming the upgrade."""
    floor, ceiling = TOOLKIT_RANGE
    pin = pins.client
    if not SEMVER_CORE.fullmatch(pin):
        raise Refusal("factory.toolkit", "[toolkit].client", f"not a version: {pin!r}")
    if not (semver_tuple(floor) <= semver_tuple(pin) < semver_tuple(ceiling)):
        raise Refusal(
            "factory.toolkit",
            "[toolkit].client",
            f"the tenant pins {pin}; this factory reads [{floor}, {ceiling}) — upgrade the factory to a release "
            f"that reads {pin}, or the tenant's pin into the range (T-C2)",
        )


def load(tenant: str, checkout: Path, *, base: str, root: str | None = None, remote: str = "origin") -> TenantContext:
    """The one constructor: the deploy home's two files, the checkout's remote fetched at `base`, the config read at
    the fetched tip, the toolkit pin checked, the governed rows resolved — and a frozen value back."""
    with telemetry.span(SPAN, **{"isidium.tenant": tenant, "isidium.base": base}) as sp:
        cfg, home = tenant_client(tenant)
        identity = ForgeIdentity.load(home)
        registration = Registration.load(home)
        root = root_of(checkout, root)
        coords = ForgeCoords.parse(_remote_url(checkout, remote), remote)
        _fetch(checkout, remote, base)
        with Cat(checkout) as cat:
            tip = cat.get("FETCH_HEAD")
            if tip is None or tip[1] != "commit":
                raise Refusal("factory.no-base", f"{remote}/{base}", "FETCH_HEAD is not a commit")
            base_sha = tip[0]
            got = cat.get(f"{base_sha}:{root}config.toml")
            if got is None:
                raise Refusal("factory.no-config", f"{root}config.toml", f"not at {base_sha}")
        tree, _entries, rs = parse_config(got[2].decode("utf-8"), CONFIG_ORDERS)
        fatal = [r for r in rs if r.rule == "head.toml"]
        if fatal:
            raise fatal[0]
        pins = ToolkitPins.of(tree)
        toolkit_check(pins)
        registry = Registry.for_checkout(checkout)
        registry_current(tree, registry)
        eff = resolve_effective(tree, registry)
        sp.set_attribute("isidium.base_sha", base_sha)
        sp.set_attribute("isidium.toolkit.client", pins.client)
        sp.set_attribute(GIT_SPAWNS, 3)
        return TenantContext(
            tenant=tenant,
            home=home,
            client=cfg,
            checkout=checkout,
            root=root,
            base=base,
            base_sha=base_sha,
            forge=coords,
            identity=identity,
            toolkit=pins,
            governed=tuple(dict(r) for r in eff["governed"]),
            registry=registry,
            registration=registration,
            eff=eff,
        )
