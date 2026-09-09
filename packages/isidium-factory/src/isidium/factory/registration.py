"""The factory's side of the tenant registration (04 §5) — one deploy home, one directory per tenant [L2, 2026-09-09].

**The seam this stands on.** A store knows a caller by two files it is handed — the CA it pins and the registration
(`subject → (principal, grant)`) — and a client knows a store by one: the `client.toml` shape, address and CA and its
own certificate and key. The two identity tiers the owner ruled (the WP5 plan's §5, 2026-09-09) differ only in *who
writes those files*: on the **local tier** — the default for a project without identity-management infrastructure —
a human runs the recipe in `deploy/README.md` and edits the rows; on the **realm tier** the realm on agent-station
issues and writes them. Nothing here reads differently between the two, which is what makes the local tier a durable
default rather than an interim: it is the realm tier with a person where the realm will be.

**The home is `$ISIDIUM_DEPLOY/<tenant>/factory/`** — one parent, one directory per tenant, the factory's material
for that tenant inside the tenant's own directory (owner, 2026-09-08 / 2026-09-09: *"isidium-deploy as the proper home
for this in its tenant directory"*), mirroring a future vault's per-tenant namespaces. The root is the environment's
and never a literal here (C-1): a factory that does not know its deploy home refuses to guess one. Paths inside a
tenant's `client.toml` are relative to that file, as the store client's are to the checkout.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Final

from isidium.store.client.config import ClientConfig
from isidium.store.core.refusal import Refusal

ENV: Final = "ISIDIUM_DEPLOY"
CLIENT: Final = "factory/client.toml"
# 04 §2.1's `tenant` grammar, and the reason a name is checked before it becomes a path: a tenant name is a
# directory under the deploy home, and `..` is not a tenant.
TENANT: Final = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def deploy_home() -> Path:
    """`$ISIDIUM_DEPLOY`, and nothing when it is unset — `factory.not-configured` names the variable to set."""
    home = os.environ.get(ENV)
    if not home:
        raise Refusal("factory.not-configured", ENV, "set it to the deploy home: one directory per tenant")
    return Path(home)


def tenant_client(tenant: str) -> tuple[ClientConfig, Path]:
    """The named tenant's client file and the directory its paths are relative to."""
    if not TENANT.match(tenant):
        raise Refusal("factory.tenant-name", tenant, "a tenant is [a-z0-9-], 1..63, no leading or trailing -")
    path = deploy_home() / tenant / CLIENT
    if not path.is_file():
        raise Refusal("factory.unknown-tenant", tenant, f"no {CLIENT} under the deploy home for it")
    return ClientConfig.load(path), path.parent
