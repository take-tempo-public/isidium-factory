"""The tenant's pre-commit hook (03 §9.6, W4): *"a governed path changed in this commit → refuse. That is the whole
hook in a tenant container; the store is the only writer."* One check, no recompute, no store call — the guarantee is
the store's identity and its journal (1.2); this is prevention of the obvious.

The governed paths come from the checkout's own `config.toml` (root + the `[[governed]]` manifest) overlaid on the
declared defaults of the version it adopts, so the hook is correct offline. It costs one file read and **one schema
document** — the registry is lazy since K1d, so this reads `config@1` and not the seven documents beside it (C-13;
`governed_paths` re-measured 2026-08-30 at 24.6 ms against 78.0 ms, three TOML parses against ten).

**What that repaid is 1% of what this hook cost, and the rest was imports** — K1d's finding, ruled 7bh.2 and built
here (K3b). The installed hook script runs **this module**, `python -m isidium.store.client.hook`, so a commit never
loads `client/cli.py`. K3 had already taken `cryptography` and the generated pydantic models out of that graph by
deleting the local transport; this takes `typer` out as well and — the half that lasts — makes the coupling
impossible rather than merely absent: `tests/store/test_walk.py` asserts the module set of a child interpreter that
imports this file, so a later chunk cannot put the store back into the hook's graph unnoticed.

**Measured 2026-08-30/31, one sitting.** Two levels, and they are not the same number. At the import level
(`tools/import_cost.py`, medians net of a bare interpreter re-measured interleaved) `client.cli` costs **792 ms**
against this module's **543 ms**. At the door — the two real command lines, in a real checkout, nothing staged,
interleaved, fifteen runs each, twice — the old door is **1684 / 1701 ms** net and this one **1258 / 1122 ms**:
**~0.4–0.6 s off every commit**. The old door's two runs agree to within 1%, which is what says the difference is a
door and not a lucky spawn; this one's disagree by 136 ms, which is why nothing here asserts a clock. What remains
is a floor this chunk cannot reach: Python's own start-up, plus the OpenTelemetry API arriving through
`core/refusal.py`, which every path needs (C-11). Below it is 7bh.3's, not this chunk's.

`isidium hook` stays for a human typing it and calls the same `check()` — one behaviour, two doors.
"""

from __future__ import annotations

import shlex
import subprocess
import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from ..core.grammar import parse_config
from ..core.refusal import Refusal
from ..registry.config import CONFIG_ORDERS, governed_resolve, named_version, resolve_effective
from ..registry.loader import Registry, adopted_version
from .config import ClientConfig

HOOK_SCRIPT = """#!/bin/sh
# isidium-store: the tenant's one pre-commit check (03 §9.6) — a governed path changed here? refuse; that is not
# where those change. Installed by `isidium init`; chains to any hook that was already here. The store's own commits
# carry `--no-verify`: it is the writer, and its commits are journaled.
if [ -x "$(git rev-parse --git-dir)/hooks/pre-commit.local" ]; then
  "$(git rev-parse --git-dir)/hooks/pre-commit.local" || exit $?
fi
# The module, not the CLI and not an `isidium` on PATH (7bh.2): both of those import `client/cli.py`, and every
# commit would pay for its graph. The interpreter below is written out absolute — it is the one `init` ran under,
# so this needs no PATH lookup and cannot pick up another checkout's `isidium`.
exec {python} -m isidium.store.client.hook
"""


def governed_paths(repo: Path, root: str | None = None) -> tuple[str, list[dict[str, object]]]:
    """(root, manifest rows) for this checkout. The root is **the one `init` recorded** in `.isidium/client.toml`
    (the review's S5: guessing `docs/work/` silenced the hook for every tenant that chose another root); the manifest
    is the checkout's own `config.toml`. Both reads are local and offline.

    **When no root can be found, this refuses rather than guessing** [2026-08-29, K1b-ii item 8]. It used to return
    `"docs/work/"` — `config@1`'s own declared default, written a second time in the binary, which is what C-1
    forbids, and invisible to the C-1 sweep because a bare `return` is not an absent-key fallback. It also re-opened
    S5 eight lines below the docstring that names S5: a checkout whose root is elsewhere got a hook that protected
    nothing, silently. A hook that cannot tell what is governed refuses the commit and says why; that is loud, and
    loud is the whole point of a pre-commit check."""
    if root is None:
        try:
            cfg, workdir = ClientConfig.find(repo)
            if workdir == repo or repo.is_relative_to(workdir):
                root = cfg.root
        except Refusal:
            root = None
    if root is None:
        for candidate in (repo / "docs/work/config.toml", repo / "config.toml"):
            if candidate.is_file():
                rel = str(candidate.parent.relative_to(repo)).replace("\\", "/")
                root = "" if rel == "." else rel + "/"
                break
        else:
            raise Refusal(
                "hook.unknown-root",
                "",
                "this checkout has no `.isidium/client.toml` and no `config.toml` at a root the hook can find, so "
                "it cannot tell which paths are governed. Run `isidium init` here, or remove the hook.",
            )
    cfg_path = repo / (root + "config.toml")
    tree: Mapping[str, Any] = {}
    if cfg_path.is_file():
        tree, _entries, _rs = parse_config(cfg_path.read_text(encoding="utf-8"), CONFIG_ORDERS)
    # The manifest is the EFFECTIVE one — the checkout's own `[[governed]]` over its adopted version's declared
    # default, never a copy in the binary (C-1, ruled 2026-08-29). `for_checkout` reads the registry `init`
    # installed here, falling back to the shipped one in a clone that has not run `init` yet. It is one registry
    # load per commit, and since K1d that load is a directory listing plus the one document `resolve_effective`
    # asks for (C-13). **Since K11 it opens two refusal paths, on purpose** — see `registry_current`.
    registry = Registry.for_checkout(repo)
    registry_current(tree, registry)
    eff = resolve_effective(tree, registry)
    return str(tree.get("root", root)), list(eff["governed"])


def registry_current(tree: Mapping[str, Any], registry: Registry) -> None:
    """Refuse, naming the remedy, when the file adopts a `config@<n>` this checkout's installed registry lacks
    [K11, 2026-09-07; ruled at K10's checkpoint: *"Fold it into the planner prompt chunk"*].

    **What went wrong.** `init` installs the registry that ships that day and nothing refreshed it: tenant #0's
    checkout held K8's eight documents through K6's `config@2` and K10's `config@3`, `Registry.for_checkout` read
    that directory alone, and `resolve_effective` fell back to `config@1`'s defaults in silence — so this hook
    computed the governed manifest from the wrong version for two chunks and nothing said so. The manifest is this
    hook's **whole input**; a manifest from the wrong version is a hook protecting the wrong set of paths.

    **Refuse — not warn, not refresh — and why, at the site (the judgment the ruling left here).** A *warning* is
    the silent fallback with a footnote: the commit still passes on a manifest the hook knows is the wrong
    version's. *Refreshing itself* makes a pre-commit check into a thing with two jobs, writing into the checkout
    in the middle of somebody's commit — and it cannot serve the second case below at all, where the toolkit
    itself lacks the version. *Refusing* is the posture `hook.unknown-root` already takes (S5, K1b-ii item 8): a
    hook that cannot tell what is governed refuses and says why, and the remedy is one command, once per bump.

    **Two ids because two remedies** (C-2, C-5): the package ships the version and the checkout does not have it →
    `hook.registry-behind`, run `isidium install`; the package lacks it too → `hook.toolkit-behind`, upgrade
    `isidium-store` first. Both carry the version as their path. `Registry.shipped()` is opened only on the refusal
    path — a directory listing, no parse (K1d) — so a current checkout pays nothing here. A tree that names no
    version is not behind; it is a checkout before `init` wrote the file, and `resolve_effective` says what it does
    with that."""
    v = adopted_version(tree, registry)
    if v is None:
        v = named_version(tree)
    if v is None or registry.has(f"config@{v}"):
        return
    ref = f"config@{v}"
    if Registry.shipped().has(ref):
        raise Refusal(
            "hook.registry-behind",
            ref,
            "config.toml adopts a schema version this checkout's installed registry (`.isidium/schemas/`) does not "
            "hold, and this toolkit ships it. Run `isidium install` here, then commit again.",
        )
    raise Refusal(
        "hook.toolkit-behind",
        ref,
        "config.toml adopts a schema version this toolkit does not ship, so no local install can supply it. "
        "Upgrade `isidium-store`, run `isidium install` here, then commit again.",
    )


def staged(repo: Path) -> list[str]:
    """The staged paths — **both ends of a rename** [K7a, F1]. Git's rename detection is on by default and
    `--name-only` then prints a rename's destination alone, so `git mv` of a card out of the tracking root was a
    change to an ungoverned path as far as this predicate could see, and the commit passed. `--no-renames` lists
    the source as a deletion and the destination as an addition, which is what they are to the store."""
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--no-renames", "-z"],
        cwd=repo,
        capture_output=True,
        check=False,
        text=True,
    )
    return [p for p in out.stdout.split("\0") if p]


def governed_in(root: str, rows: Sequence[Mapping[str, object]], paths: Iterable[str]) -> list[str]:
    """The governed paths among `paths` (repo-relative): under `root` and matching a manifest row — **the one
    predicate three doors run** [V2, 2026-09-10]: this hook over the index, `verify --diff-base` over a pull request's
    diff, and the factory's forge driver over a branch before it is pushed (X2: *"the PR carries code only"*). One
    matcher, three callers, so they agree by construction; a row set the caller already holds is passed in rather
    than read again (C-13)."""
    eff = {"governed": list(rows)}
    out: list[str] = []
    for p in paths:
        if root and not p.startswith(root):
            continue
        if governed_resolve(eff, p[len(root) :] if root else p) is not None:
            out.append(p)
    return out


def offending(repo: Path, paths: Sequence[str] | None = None) -> list[str]:
    """The staged governed paths — the whole hook."""
    root, rows = governed_paths(repo)
    return governed_in(root, rows, paths if paths is not None else staged(repo))


def check(repo: Path) -> int:
    try:
        bad = offending(repo)
    except Refusal as r:
        # Fail closed and say so: the alternative was guessing a root and protecting nothing (S5, C-1).
        print(f"isidium: refused — {r.rule}: {r.detail}")
        return 1
    if not bad:
        return 0
    print("isidium: refused — governed paths are written by the store, not by a commit here (03 §9.6):")
    for p in bad:
        print(f"  {p}")
    print("  use `isidium write` / `isidium ratify`; `isidium repair --journal <commit>` explains a bypass.")
    return 1


def install(repo: Path) -> Path:
    """Write `.git/hooks/pre-commit`, chaining any hook already there to `pre-commit.local`."""
    hooks = repo / ".git" / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    target = hooks / "pre-commit"
    if target.is_file() and "isidium" not in target.read_text(encoding="utf-8", errors="replace"):
        target.replace(hooks / "pre-commit.local")
    target.write_text(HOOK_SCRIPT.format(python=shlex.quote(sys.executable)), encoding="utf-8", newline="\n")
    target.chmod(0o755)
    return target


def main() -> int:
    """The installed hook's own door (7bh.2, ruled 2026-08-30), and the reason this module is worth running directly:
    reaching `check` through `client/cli.py` imports `typer` and everything `cli.py` will ever import, to answer a
    question that needs one TOML file and `git diff --cached`.

    It resolves the repo the way the CLI command does — `Path.cwd()` — because `git` runs a pre-commit hook from the
    top of the working tree. The two doors therefore cannot disagree about which checkout they answer for, and
    `tests/store/test_walk.py` holds them to the same `check`."""
    return check(Path.cwd())


if __name__ == "__main__":
    raise SystemExit(main())
