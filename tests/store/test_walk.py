"""What `init` installs into a checkout, and what the client file is — the offline half of the WP3 acceptance walk.

**The walk itself moved to `test_channel.py`** when K3 deleted local mode. It used to run here through
`LocalTransport`, in this process, with a caller the client file asserted about itself; there is one transport now
and the walk runs over it. What stays here is everything that never crossed a transport at all: the schemas and the
hook `install` writes, the client file's own grammar, and the hook reading the checkout's manifest offline.

The client file is where the deletion is visible, so it is asserted here rather than assumed: it no longer carries
`mode`, `principal`, `grant`, `journal` or `signer`, and a file written before K3 is **refused by name** rather than
loaded with its identity keys quietly ignored.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from isidium.store.client import hook as hook_mod
from isidium.store.client.config import CLIENT_FILE, ClientConfig
from isidium.store.client.install import install
from isidium.store.core.refusal import Refusal

from .conftest import tenant_checkout


@pytest.fixture
def tenant(tmp_path: Path) -> Path:
    return tenant_checkout(tmp_path)


def client_cfg(root: str = "docs/work/") -> ClientConfig:
    """What `isidium init` is given now: the tenant, the tracking root, and the channel. No identity — that comes
    off the certificate on the connection (7bg.2)."""
    return ClientConfig(
        tenant="sartor",
        root=root,
        address="https://store.sartor:8443",
        ca=".isidium/tenant-ca.pem",
        cert=".isidium/owner.crt.pem",
        key=".isidium/owner.key.pem",
    )


def test_install_is_idempotent_and_chains_an_existing_hook(tenant: Path) -> None:
    hooks = tenant / ".git" / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    (hooks / "pre-commit").write_text("#!/bin/sh\necho mine\n", encoding="utf-8", newline="\n")
    install(tenant, client_cfg())
    assert (hooks / "pre-commit.local").read_text(encoding="utf-8") == "#!/bin/sh\necho mine\n"
    # The installed door is the module, not `isidium hook` (7bh.2, K3b) — that string was what this asserted
    # before, and it was satisfied by the `command -v isidium` arm that made the hook import `cli.py`.
    assert "-m isidium.store.client.hook" in (hooks / "pre-commit").read_text(encoding="utf-8")
    before = (tenant / ".gitignore").read_text(encoding="utf-8")
    install(tenant, client_cfg())  # idempotent: the ignore line is not doubled, the hook is not re-chained
    assert (tenant / ".gitignore").read_text(encoding="utf-8") == before
    assert "-m isidium.store.client.hook" in (hooks / "pre-commit").read_text(encoding="utf-8")


def test_the_client_file_is_the_registrations_half(tenant: Path) -> None:
    install(tenant, client_cfg())
    found, workdir = ClientConfig.find(tenant / "docs")  # found from anywhere in the checkout
    assert workdir == tenant and found.tenant == "sartor"
    assert (found.address, found.ca, found.cert, found.key) == (
        "https://store.sartor:8443",
        ".isidium/tenant-ca.pem",
        ".isidium/owner.crt.pem",
        ".isidium/owner.key.pem",
    )
    (tenant / CLIENT_FILE).write_text('tenant = "sartor"\nnope = "x"\n', encoding="utf-8")
    with pytest.raises(Refusal, match=r"client\.unknown-key"):
        ClientConfig.find(tenant)


def test_the_client_file_no_longer_carries_an_identity(tenant: Path) -> None:
    """K3's own assertion, in the file the deletion is about.

    Two halves, because either alone is satisfied by a mistake. **The keys are gone from what is written**: a client
    file that still rendered `grant = "contributor"` would be a self-asserted identity that nothing can refuse, which
    is the S2 hazard the whole ruling closes. And **a file written before K3 is refused by name**: `load` rejects
    unknown keys, so an existing checkout is told to re-run `init` instead of being loaded with `principal` and
    `signer` silently dropped — the difference between a migration the operator can see and one they cannot.
    """
    install(tenant, client_cfg())
    text = (tenant / CLIENT_FILE).read_text(encoding="utf-8")
    assert not {"mode", "principal", "grant", "journal", "signer"} & {
        line.split("=", 1)[0].strip() for line in text.splitlines() if "=" in line and not line.startswith("#")
    }, text
    assert "SELF-ASSERTED" not in text and "single-occupant" not in text

    (tenant / CLIENT_FILE).write_text(
        'mode = "local"\ntenant = "sartor"\nprincipal = "a@b"\ngrant = "owner"\n', encoding="utf-8"
    )
    with pytest.raises(Refusal) as refused:
        ClientConfig.find(tenant)
    assert refused.value.rule == "client.unknown-key"
    assert refused.value.detail == "grant, mode, principal", refused.value.detail


def test_no_client_file_is_a_typed_refusal(tmp_path: Path) -> None:
    with pytest.raises(Refusal, match=r"client\.not-configured"):
        ClientConfig.find(tmp_path)


def test_hook_reads_the_checkouts_own_manifest(tenant: Path) -> None:
    """The hook is offline: the governed paths come from the checkout's `config.toml` over the declared defaults of
    the version it adopts. Here there is no `config.toml` yet — only the client install — so this exercises the
    fallback arm, and it is what fails if the hook stops overlaying the declared manifest (mutation-checked, K1c).

    It costs one file read and **one schema document**, the registry having been lazy since K1d: `governed_paths`
    was re-measured there at 24.6 ms against 78.0 ms, three TOML parses against ten [line corrected by K3 — it
    still claimed the 46 ms K1d repaid, and 46 ms was never the measurement here anyway]."""
    install(tenant, client_cfg())
    root, rows = hook_mod.governed_paths(tenant)
    assert root == "docs/work/"  # [was `x == v or x == v`, a tautology; corrected 2026-08-29]
    assert any(r["path"] == "cards/*.md" for r in rows)
    assert hook_mod.offending(tenant, ["docs/work/cards/0007-x.md", "src/a.py", "docs/work/config.toml"]) == [
        "docs/work/cards/0007-x.md",
        "docs/work/config.toml",
    ]


def _hook_module_the_installed_script_runs() -> str:
    """The module name is read OUT of the rendered hook script, so the guard below cannot drift from the door.

    A test that hard-coded `isidium.store.client.hook` would keep passing after an edit pointed the installed script
    back at `cli.py`: it would be asserting that a clean module exists, not that the hook runs it."""
    script = hook_mod.HOOK_SCRIPT.format(python=shlex.quote(sys.executable))
    lines = [ln for ln in script.splitlines() if ln.startswith("exec ")]
    assert len(lines) == 1, script  # one door, not a preferred one and a fallback
    words = shlex.split(lines[0])
    assert words[0] == "exec" and words[1] == sys.executable and words[2] == "-m", lines[0]
    # The commands, not the comments — this file explains itself by naming `client/cli.py`, and the property is
    # that nothing the shell RUNS reaches it, by any route: no `isidium` on PATH, no second arm, no fallback.
    ran = [ln for ln in script.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    assert not [ln for ln in ran if "client.cli" in ln or "command -v" in ln], script
    return words[3]


def test_the_client_no_longer_drags_the_store_into_every_import() -> None:
    """The hook's import graph, which is what K3b is about — widened from the guard K3 left.

    K3 deleted `client/transport.py`'s module-level `Store`, `Api`, `GitCli`, `Journal` and `Signer` imports with
    `LocalTransport`, and those were what pulled `cryptography.x509` and the generated pydantic models into
    `client/cli.py`. K3b takes the last of it: the installed hook script runs `client/hook.py` directly, so a commit
    imports neither `cli.py` nor `typer`. **`typer` is the new name in this set**, and `isidium.store.client.cli` is
    in it too, because the property is not "the hook's dependencies are light" — a future `cli.py` could import
    nothing at all and the hook would still be paying for a module it has no use for.

    **Asserted on the module set, not on a clock.** Measured on `tools/import_cost.py`, medians net of a bare
    interpreter re-measured interleaved: `client.cli` **792 ms** against `client.hook`'s **543 ms** (2026-08-30,
    K3b), and K3's own run of the same harness read 741 ms and 772 ms for the same two modules — the machine moved
    further between two runs than the door is worth, which is exactly why a timing assertion here could not tell a
    fast import from a broken one. The set can.

    Every module named is a real cost: `cryptography` and `pydantic` are seconds, `typer` is the CLI framework the
    hook never renders anything with, and `cli.py` is the module that imports all three of the store's clients'
    worth of surface. `client.cli` keeps `typer` — it is the CLI — so it is asserted against the store's two only.
    """
    env = {**os.environ, "PYTHONPATH": str(Path("packages/isidium-store/src").resolve())}
    heavy = ("cryptography", "pydantic", "typer", "isidium.store.client.cli")

    def pulled(module: str) -> list[str]:
        """Which of `heavy` are in `sys.modules` of a fresh interpreter that imported `module`, and nothing else."""
        code = f"import {module}, sys; print(' '.join(h for h in {heavy!r} if h in sys.modules))"
        return subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, check=True, env=env
        ).stdout.split()

    # The hook's own door, named by the installed script rather than by this test.
    assert pulled(_hook_module_the_installed_script_runs()) == [], "the pre-commit hook imports the store again"
    # K3's half of the property, unchanged: the transport and the CLI stop short of the store's own two. `cli.py`
    # keeps `typer` — it is the CLI — and it names itself, so this asks about the two rather than about the set.
    store_only = {"cryptography", "pydantic"}
    for module in ("isidium.store.client.transport", "isidium.store.client.cli"):
        assert not store_only & set(pulled(module)), f"{module} imports the store's dependency tree again"

    # The positive discriminators: the probe finds each name when it IS there, so an empty answer above means absent
    # rather than "the probe stopped working". `server.api` is what `transport.py` imported and pulls both of the
    # store's — `server.store` alone pulls `cryptography` and not `pydantic`, which is measured rather than assumed
    # because a control that only half fires only half discriminates. `client.cli` is the control for the other two,
    # and it is the module the hook used to run, so this row is also what the win is measured against.
    assert sorted(pulled("isidium.store.server.api")) == ["cryptography", "pydantic"]
    assert sorted(pulled("isidium.store.client.cli")) == ["isidium.store.client.cli", "typer"]


def test_the_installed_hook_and_the_typed_command_are_one_function(
    tenant: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One behaviour, two doors (7bh.2): `python -m isidium.store.client.hook` and `isidium hook` reach the same
    `check`, so they cannot drift into two answers about the same commit.

    **Asserted by substitution, not by reading the source.** Replacing `hook.check` has to change what *both* doors
    do; a second copy of the logic behind either one survives that. The CLI command resolves its `check` at call
    time (`from .hook import check` inside the body, which is what keeps `hook.py` out of `--help`'s cost), so the
    substitution reaches it the same way a divergence would.

    **And the positive discriminator, because a shared stub proves only that a stub is shared:** with nothing
    patched, both doors answer a real checkout correctly — `0` with nothing staged, `1` with a governed path staged
    — which is the property a caller has, and it is what fails if `main()` resolves a different repo than the CLI
    command does.
    """
    import typer

    from isidium.store.client import cli as cli_mod

    install(tenant, client_cfg())
    monkeypatch.chdir(tenant)

    seen: list[Path] = []

    def check_and_remember(repo: Path) -> int:
        seen.append(repo)
        return 7

    monkeypatch.setattr(hook_mod, "check", check_and_remember)
    assert hook_mod.main() == 7
    with pytest.raises(typer.Exit) as exited:
        cli_mod.hook()
    assert exited.value.exit_code == 7
    assert seen == [Path.cwd(), Path.cwd()], seen  # both doors, one function, one repo

    monkeypatch.undo()
    monkeypatch.chdir(tenant)
    assert hook_mod.main() == 0
    governed = tenant / "docs/work/cards/0007-x.md"
    governed.parent.mkdir(parents=True, exist_ok=True)
    governed.write_text("# a card" + chr(10), encoding="utf-8", newline=chr(10))
    subprocess.run(["git", "add", str(governed)], cwd=tenant, check=True, capture_output=True)
    assert hook_mod.main() == 1
    with pytest.raises(typer.Exit) as refused:
        cli_mod.hook()
    assert refused.value.exit_code == 1


def test_the_installed_door_answers_the_commit_from_its_own_module(tenant: Path) -> None:
    """The door end to end, as a commit meets it: the module the installed script names, run by `-m`, in a real
    checkout, and its **exit code** — which is the entire contract a pre-commit hook has with git.

    The in-process test above holds the two doors to one function; this one holds the process to its answer. They
    are different failures: `main()` could return the right code and the `__main__` guard drop it on the floor, and
    every in-process assertion would still pass while every commit sailed through. `-m` is also the only way to
    exercise what the hook actually pays — `runpy` and the parent packages — rather than an import this test chose.

    Both codes are asserted, not just the refusal: a hook that refuses everything and a hook that refuses nothing
    are equally broken, and only the pair can tell them apart.
    """
    install(tenant, client_cfg())
    module = _hook_module_the_installed_script_runs()
    env = {**os.environ, "PYTHONPATH": str(Path("packages/isidium-store/src").resolve())}

    def door() -> int:
        return subprocess.run([sys.executable, "-m", module], cwd=tenant, capture_output=True, env=env).returncode

    assert door() == 0, "nothing governed is staged, so the commit passes"
    governed = tenant / "docs/work/cards/0007-x.md"
    governed.parent.mkdir(parents=True, exist_ok=True)
    governed.write_text("# a card" + chr(10), encoding="utf-8", newline=chr(10))
    subprocess.run(["git", "add", str(governed)], cwd=tenant, check=True, capture_output=True)
    assert door() == 1, "a governed path is staged, so the commit is refused"


def test_tool_schemas_are_what_the_surface_serves(tenant: Path) -> None:
    """The planner's tool surface is the generated one — the same bytes the registry renders (03b §4)."""
    from isidium.store.registry import codegen

    installed = json.loads((codegen.GENERATED / "tools.json").read_text(encoding="utf-8"))
    assert set(installed) == set(codegen.tool_schemas())
    assert installed["write"]["inputSchema"]["$defs"]["CardDocument"]["required"] == ["head"]
