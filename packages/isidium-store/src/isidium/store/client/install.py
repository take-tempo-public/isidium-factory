"""`init` installs the thin client, the hook and the registry schemas locally (03 §1.6, 03b §4: *"`init` installs the
referenced versions locally — same bytes either way, so local `check` and the store cannot disagree"*), and then
calls the store's own `init`, which writes and signs `config.toml` as the policy chain's first entry (04 §3).

Nothing here writes a governed path: the schemas land under `.isidium/schemas/` (installed, not governed), the hook
under `.git/hooks/`, the client's own configuration under `.isidium/client.toml`. `config.toml` itself is the store's
write."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

from ..registry.loader import Registry
from .config import CLIENT_FILE, ClientConfig
from .hook import install as install_hook

GITIGNORE_LINES = (
    "# isidium-store: the client's half of the registration and its local install — never committed",
    ".isidium/",
)


def install_schemas(repo: Path, registry: Registry | None = None) -> list[Path]:
    """The registry, byte-for-byte, for offline validation and CI (03b §4).

    **The bytes come from the registry it was handed** [K1b-iii]. This function took a `registry`, wrote `INSTALLED`
    from it, and then copied the schema files from `resources.files("isidium.store.registry")` — always the shipped
    package, never the argument. Latent only because every caller passes `None` today, but it sits in the one
    function whose stated purpose is byte-identity: a checkout could be handed one registry's list of installed
    versions over another registry's documents, which is the divergence the sentence in 03b §4 exists to forbid.

    Filenames are `<ref>.toml`, derived from the document's own `name` and `version` rather than from whatever the
    source file happened to be called, so a reinstall is idempotent and the filename stops being an independent
    fact that could disagree with the content.
    """
    reg = registry or Registry.shipped()
    out = repo / ".isidium" / "schemas"
    out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for ref, raw in sorted(reg.source().items()):
        p = out / f"{ref}.toml"
        p.write_bytes(raw)
        written.append(p)
    (out / "INSTALLED").write_text("\n".join(sorted(reg.installed)) + "\n", encoding="utf-8", newline="\n")
    return written


def ignore_client(repo: Path) -> None:
    """Append the client's ignore block to the tenant's `.gitignore` **in the file's own bytes** [K7c, F22].

    The file is the tenant's, not the client's: `read_text` and `write_text(newline=...)` re-ended every line of a
    CRLF file as LF (measured: three CRLF lines in, none out) -- a whole-file diff the tenant did not ask for, made
    by `init`. So the bytes are read as bytes, the ending is the one the file already uses (CRLF if any line has
    one, else LF), the block is joined with that ending, and the result is written back as bytes."""
    gi = repo / ".gitignore"
    data = gi.read_bytes() if gi.is_file() else b""
    if b".isidium/" in data:
        return
    ending = b"\r\n" if b"\r\n" in data else b"\n"
    sep = b"" if data.endswith(b"\n") or not data else ending
    gi.write_bytes(data + sep + ending.join(line.encode("utf-8") for line in GITIGNORE_LINES) + ending)


def resolve_root(cfg: ClientConfig, registry: Registry | None = None) -> ClientConfig:
    """`root` filled from the adopted schema version, never from a literal here (C-1, and `ClientConfig.root`'s own
    comment has said so since it was written; the CLI was overriding it with `config@1`'s declared value).

    **This must record a concrete root**, not leave it blank. `ClientConfig.render` omits empty strings, and
    `governed_paths` reads a missing `root` back as `""` — not as "unknown" — which sends the hook to the repo
    root and silently protects the wrong tree. That is S5 wearing a different hat, and `hook.unknown-root` does not
    catch it because a blank root is an answer.

    `config@1` is the version this client-side read stands on; `Store.init` adopts the newest installed version
    (`registry.newest("config")`, K6), and `root` carries the same declared value in every version so far.
    Version *selection* is not a declared default, which is why the literal is allowed to stand here — but it now
    stands in two places, and that is worth a single home the day a `config@2` exists."""
    if cfg.root:
        return cfg
    reg = registry or Registry.shipped()
    return replace(cfg, root=str(reg.defaults_of("config@1")["root"]))


def install_client(repo: Path, cfg: ClientConfig) -> Path:
    p = repo / CLIENT_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(cfg.render(), encoding="utf-8", newline="\n")
    return p


def install(repo: Path, cfg: ClientConfig, registry: Registry | None = None) -> dict[str, Any]:
    """The whole client-side install; idempotent. Resolves `root` first, so what lands in `.isidium/client.toml`
    is the value the hook will read back."""
    cfg = resolve_root(cfg, registry)
    written = {
        "client": str(install_client(repo, cfg)),
        "hook": str(install_hook(repo)),
        "schemas": [str(p) for p in install_schemas(repo, registry)],
    }
    ignore_client(repo)
    return written


def init(repo: Path, cfg: ClientConfig, store_args: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Install, then the store's `init` — the signed `created` entry that opens the policy chain (04 §3, K-1).

    **`init` runs over the channel** (7bg.2, applied by K3). It used to have two arms, and the local one was the
    tested one: it reached into `LocalTransport.store` and called `Store.init` in this process, with a caller the
    client file asserted. There is one arm now, and it is an ordinary `init` call over mTLS — the same door every
    other verb uses, with the same certificate deciding what the caller may do.

    **The operator's `--root` reaches the store on this path** [defect, found and fixed by K3]. The local arm passed
    `root=chosen_root`; the https arm passed `dict(store_args)` and dropped it, so an operator who chose a tracking
    root over the channel got a `config.toml` that did not name it — and then a client file that did, which is the
    two halves disagreeing about the tenant's own policy. It was latent because no test drove the https arm; the
    channel test added with this chunk is what would have caught it.
    """
    from .transport import Transport

    # What the OPERATOR asked for, captured before resolution: `config.toml` is governed, so it gets a `root` key
    # only when one was actually chosen. The resolved default belongs in the client file, not in the tenant's.
    chosen_root = cfg.root or None
    cfg = resolve_root(cfg)
    out = install(repo, cfg)
    args = dict(store_args or {})
    if chosen_root is not None:
        args["root"] = chosen_root
    out["config"] = Transport(cfg, repo).call("init", args)
    return out
