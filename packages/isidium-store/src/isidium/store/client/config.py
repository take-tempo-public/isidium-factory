"""The client's own configuration — `.isidium/client.toml` in the tenant repo (or `$ISIDIUM_CLIENT`): the store's
address and the channel's credentials. **This file is not governed** — it carries an address and key paths, which
`config.toml` may never (04 §2.2, K-7); it is the registration's client half, per checkout.

**It no longer says who the caller is** (7bg.2, applied by K3). It used to carry `principal` and `grant`, which local
mode read straight back as the caller's identity — a claim the file made about itself, with no channel to
authenticate it. Identity now has one home: the certificate on the connection, resolved against the registration the
store holds (03b §2). What is left here is where the store is and which key material reaches it.

`root` stays: the pre-commit hook is offline by design and reads it to know which paths this checkout governs.
`repo` did not — its one reader in the package was the local transport, and `render` writes it into every client
file, so keeping it would leave a key in every checkout that nothing consults and `load` still insists on knowing.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from ..core.refusal import Refusal

CLIENT_FILE: Final = ".isidium/client.toml"
ENV: Final = "ISIDIUM_CLIENT"


@dataclass(frozen=True)
class ClientConfig:
    tenant: str = ""
    root: str = ""  # filled by `init` from the adopted schema version's default; never a literal here
    address: str = ""  # https://host:port
    ca: str = ""  # the CA bundle that signs the store's certificate (the pin's home)
    cert: str = ""  # this client's certificate
    key: str = ""  # this client's private key

    @classmethod
    def find(cls, start: str | Path = ".") -> tuple[ClientConfig, Path]:
        """The client file for this checkout: `$ISIDIUM_CLIENT`, else the nearest `.isidium/client.toml` upward."""
        env = os.environ.get(ENV)
        if env:
            p = Path(env)
            return cls.load(p), p.parent.parent
        here = Path(start).resolve()
        for d in [here, *here.parents]:
            p = d / CLIENT_FILE
            if p.is_file():
                return cls.load(p), d
        raise Refusal("client.not-configured", CLIENT_FILE, "run `isidium init` in the tenant checkout")

    @classmethod
    def load(cls, path: str | Path) -> ClientConfig:
        data: dict[str, Any] = tomllib.loads(Path(path).read_text(encoding="utf-8"))
        known = set(cls.__dataclass_fields__)
        unknown = set(data) - known
        if unknown:
            raise Refusal("client.unknown-key", str(path), ", ".join(sorted(unknown)))
        return cls(**data)

    def render(self) -> str:
        lines = [
            "# The client half of the tenant registration (03b §2): where this checkout's store is and how this",
            "# caller authenticates to it. NOT a governed file — it carries the address and key paths config.toml",
            "# may never hold (04 §2.2). Per checkout; never committed.",
            "#",
            "# There is one shape and one boundary (7bg.2): the store is reached over mTLS and the caller is the",
            "# certificate on that connection. This file names no principal and no grant — an identity a file",
            "# asserts about itself is not one the store can refuse.",
            "",
        ]
        for f in self.__dataclass_fields__:
            v = getattr(self, f)
            if v != "" and v is not None:
                lines.append(f'{f} = "{v}"' if isinstance(v, str) else f"{f} = {v}")
        return "\n".join(lines) + "\n"
