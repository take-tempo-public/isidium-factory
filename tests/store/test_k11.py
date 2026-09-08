"""K11 — the planner's seat, and the checkout that stays current (2026-09-07).

1. `install` writes the planner's skill into BOTH harness directories, byte-identical to the package (Q22, ruled
   (a)), and completes the ignore block line by line: a checkout `init`ed before K11 gains the two skill lines only.
2. The skill's copy of the prompt is the prompt at its ruled home (`prompts/planner/v1.md`), byte for byte; and
   `SKILL.md` conforms to the Agent Skills form — the name equal to its directory, the lengths, the body's size.
3. `isidium install` re-runs the install from the checkout's own client file, and refuses where there is none.
4. The hook refuses `hook.registry-behind` when the file adopts a version the checkout lacks and the toolkit ships,
   `hook.toolkit-behind` when the toolkit lacks it too — and `isidium install` is the first one's remedy.
5. `resolve_effective` answers `config.schema-unknown` for a version the file names and the registry lacks; a tree
   that names nothing still resolves against `config@1`; the forge's chain verifier inherits the loud answer.
6. `AGENTS.md` and `CLAUDE.md` are the documented pair.

Every assertion is a positive discriminator; nothing here passes on "nothing came back".
"""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import sys
from pathlib import Path
from types import ModuleType

import pytest
import typer

from isidium.store.client import cli as cli_mod
from isidium.store.client import hook as hook_mod
from isidium.store.client.install import GITIGNORE_LINES, SKILL, SKILL_DIRS, ignore_client, install, skill_source
from isidium.store.core.refusal import Refusal
from isidium.store.registry import config as cfg

from .conftest import REGISTRY, tenant_checkout
from .test_walk import client_cfg

REPO = Path(__file__).resolve().parents[2]
PACKAGE_SKILL = REPO / "packages/isidium-store/src/isidium/store/client/skill" / SKILL
PROMPT = REPO / "prompts/planner/v1.md"
ROOT = "docs/work/"

# agentskills.io, *Specification* (read 2026-09-07): 1–64 characters, `a-z`, `0-9` and `-`, no leading, trailing
# or doubled hyphen, equal to the parent directory's name.
SKILL_NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    work = tenant_checkout(tmp_path)
    install(work, client_cfg(ROOT))
    return work


def config_adopting(version: int) -> str:
    """A tenant `config.toml` in the shape `init` writes, adopting `config@<version>` by its own manifest row."""
    return (
        f'schema = {version}\nchain_opened_under = 1\ntenant = "sartor"\nroot = "{ROOT}"\n\n'
        '[[governed]]\npath = "cards/*.md"\nschema = "card@1"\nwrite = ["owner", "contributor"]\n\n'
        f'[[governed]]\npath = "config.toml"\nschema = "config@{version}"\nwrite = ["owner"]\n'
    )


def write_config(checkout: Path, version: int) -> Path:
    p = checkout / ROOT / "config.toml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(config_adopting(version), encoding="utf-8", newline="\n")
    return p


# ---- 1. the skill lands in both directories; the ignore block grows line by line ------------------------------------


def test_install_writes_the_skill_into_both_harness_directories_byte_for_byte(checkout: Path) -> None:
    """Q22 (a). The two directories are the two the harnesses read, verified against their own documents
    (Claude Code: `.claude/skills/`; pi: `.agents/skills/`), and both copies are the package's bytes — the
    package's, not a re-rendering, so a `SKILL.md` edited in the package is what a session reads after `install`."""
    assert SKILL_DIRS == (".claude/skills", ".agents/skills")
    src = skill_source()
    assert set(src) == {"SKILL.md", "references/planner-v1.md"}, sorted(src)
    for d in SKILL_DIRS:
        base = checkout / d / SKILL
        for rel, raw in src.items():
            assert (base / rel).read_bytes() == raw == (PACKAGE_SKILL / rel).read_bytes(), f"{d}/{rel}"
    # the ignore block: every pattern once, and a second install changes nothing
    gi = (checkout / ".gitignore").read_bytes()
    for line in GITIGNORE_LINES[1:]:
        assert gi.count(line.encode("utf-8") + b"\n") == 1, (line, gi)
    assert gi.count(b"# isidium-store") == 1
    install(checkout, client_cfg(ROOT))
    assert (checkout / ".gitignore").read_bytes() == gi


def test_a_checkout_ignoring_isidium_already_gains_the_skill_lines_only(tmp_path: Path) -> None:
    """Tenant #0's own case: `init` ran before K11, so `.isidium/` is there and the comment is there. The two skill
    lines are appended in the file's own ending; the comment is not written a second time."""
    gi = tmp_path / ".gitignore"
    before = b"*.pyc\r\n" + GITIGNORE_LINES[0].encode("utf-8") + b"\r\n.isidium/\r\n"
    gi.write_bytes(before)
    ignore_client(tmp_path)
    data = gi.read_bytes()
    assert data == before + b".claude/skills/isidium-planner/\r\n.agents/skills/isidium-planner/\r\n", data
    assert data.count(b"# isidium-store") == 1
    ignore_client(tmp_path)
    assert gi.read_bytes() == data


# ---- 2. the skill's form, and the prompt at its home -------------------------------------------------------------------


def test_the_skill_conforms_to_the_agent_skills_form_and_carries_the_prompt_byte_for_byte() -> None:
    """The reference is a COPY of `prompts/planner/v1.md` (7bd.11's home) because package data must live under the
    package for `importlib.resources` in an editable install; this is what stops the two from drifting, the way
    the installed schemas are held to the package's bytes (03b §4)."""
    text = (PACKAGE_SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---\n"), text[:40]
    front, body = text[4:].split("\n---\n", 1)
    fields = {k: v.strip() for k, v in (ln.split(":", 1) for ln in front.splitlines() if ln and ln[0] != " ")}
    assert fields["name"] == SKILL == PACKAGE_SKILL.name and SKILL_NAME.fullmatch(fields["name"])
    assert 1 <= len(fields["name"]) <= 64
    assert 1 <= len(fields["description"]) <= 1024 and "Use when" in fields["description"]
    assert body.count("\n") < 500, body.count("\n")
    assert "[references/planner-v1.md](references/planner-v1.md)" in body
    assert "isidium install" in body and "claude mcp add --scope user isidium-store" in body
    prompt = PROMPT.read_bytes()
    assert (PACKAGE_SKILL / "references/planner-v1.md").read_bytes() == prompt
    assert prompt.startswith(b"<!-- provenance:") and b"agent-kind=planner version=1" in prompt
    assert b"\r" not in prompt and b"\r" not in text.encode("utf-8")


# ---- 3. the verb --------------------------------------------------------------------------------------------------------


def test_the_install_verb_reruns_the_install_from_the_client_file(
    checkout: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A moved toolkit, modelled by deleting what it would have added: the verb puts the registry document and the
    skill back from the package, reads the address and the channel from the client file, and opens no channel."""
    monkeypatch.delenv("ISIDIUM_CLIENT", raising=False)
    schemas = checkout / ".isidium" / "schemas"
    (schemas / "config@3.toml").unlink()
    shutil.rmtree(checkout / ".agents")
    client_before = (checkout / ".isidium" / "client.toml").read_bytes()
    monkeypatch.chdir(checkout)
    monkeypatch.setattr(cli_mod, "Transport", None)  # any channel opened here is a defect, not a call
    cli_mod.install()
    answer = json.loads(capsys.readouterr().out)
    assert set(answer) == {"client", "hook", "schemas", "skill"}
    assert (schemas / "config@3.toml").read_bytes() == REGISTRY.source()["config@3"]
    assert (checkout / ".agents/skills" / SKILL / "SKILL.md").read_bytes() == skill_source()["SKILL.md"]
    assert (checkout / ".isidium" / "client.toml").read_bytes() == client_before
    assert len(answer["skill"]) == 2 * len(skill_source()) and len(answer["schemas"]) == len(REGISTRY.installed)


def test_the_install_verb_refuses_where_there_is_no_client_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`init` is the door that makes a client file; `install` guesses nothing and writes nothing without one."""
    monkeypatch.delenv("ISIDIUM_CLIENT", raising=False)
    nowhere = tmp_path / "nowhere"
    nowhere.mkdir()
    monkeypatch.chdir(nowhere)
    with pytest.raises(typer.Exit) as ex:
        cli_mod.install()
    assert ex.value.exit_code == 2
    assert "client.not-configured" in capsys.readouterr().err
    assert sorted(p.name for p in nowhere.iterdir()) == []


# ---- 4. the hook says when the checkout is behind ---------------------------------------------------------------------


def test_the_hook_refuses_a_checkout_whose_registry_is_behind_and_install_is_the_remedy(
    checkout: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """K10's finding 1, closed. The file adopts `config@3`; the checkout's install lacks it; the toolkit ships it.
    Before K11 this resolved against `config@1` in silence and the commit passed; now the commit is refused with
    the verb that fixes it, and after the verb the manifest is the file's."""
    monkeypatch.delenv("ISIDIUM_CLIENT", raising=False)
    write_config(checkout, 3)
    (checkout / ".isidium" / "schemas" / "config@3.toml").unlink()
    with pytest.raises(Refusal) as refused:
        hook_mod.governed_paths(checkout)
    r = refused.value
    assert (r.rule, r.path) == ("hook.registry-behind", "config@3") and "`isidium install`" in r.detail, r
    assert hook_mod.check(checkout) == 1
    printed = capsys.readouterr().out
    assert "hook.registry-behind" in printed and "isidium install" in printed, printed
    # the remedy, through the verb
    monkeypatch.chdir(checkout)
    cli_mod.install()
    capsys.readouterr()
    root, rows = hook_mod.governed_paths(checkout)
    assert root == ROOT and [str(row["path"]) for row in rows] == ["cards/*.md", "config.toml"], rows
    assert hook_mod.check(checkout) == 0


def test_the_hook_refuses_when_the_toolkit_itself_lacks_the_version(checkout: Path) -> None:
    """The other remedy: nothing local can supply a version the package does not ship — including in a clone that
    never ran `init`, where the shipped registry IS the checkout's."""
    write_config(checkout, 9)
    with pytest.raises(Refusal) as refused:
        hook_mod.governed_paths(checkout)
    r = refused.value
    assert (r.rule, r.path) == ("hook.toolkit-behind", "config@9") and "Upgrade `isidium-store`" in r.detail, r
    shutil.rmtree(checkout / ".isidium")
    with pytest.raises(Refusal) as again:
        hook_mod.governed_paths(checkout)
    assert (again.value.rule, again.value.path) == ("hook.toolkit-behind", "config@9")


def test_a_current_checkout_and_a_checkout_before_init_pay_nothing_here(checkout: Path) -> None:
    """The refusal paths are the only new cost: a file adopting what is installed, and no file at all, both resolve
    as before — the manifest is the file's, or `config@1`'s declared one."""
    write_config(checkout, 3)
    root, rows = hook_mod.governed_paths(checkout)
    assert root == ROOT and [str(row["path"]) for row in rows] == ["cards/*.md", "config.toml"]
    (checkout / ROOT / "config.toml").unlink()
    root, rows = hook_mod.governed_paths(checkout)
    assert root == ROOT and any(row["path"] == "cards/*.md" for row in rows) and len(rows) >= 6


# ---- 5. the resolver is loud, and the verifier inherits it -----------------------------------------------------------


def test_resolve_effective_refuses_a_named_version_the_registry_lacks() -> None:
    with pytest.raises(Refusal) as by_head:
        cfg.resolve_effective({"schema": 9, "tenant": "t"}, REGISTRY)
    assert (by_head.value.rule, by_head.value.path, by_head.value.detail) == (
        "config.schema-unknown",
        "schema",
        "config@9 not in the installed registry",
    )
    by_row = {"schema": 3, "governed": [{"path": "config.toml", "schema": "config@9", "write": ["owner"]}]}
    with pytest.raises(Refusal) as refused:
        cfg.resolve_effective(by_row, REGISTRY)
    assert refused.value.detail == "config@9 not in the installed registry"
    # a tree that names nothing still resolves against config@1 — the seam, named
    eff = cfg.resolve_effective({}, REGISTRY)
    assert eff["root"] == "docs/work/" and any(r["path"] == "cards/*.md" for r in eff["governed"])
    # and the file's own answer, registry-free
    assert cfg.named_version({}) is None and cfg.named_version({"schema": 3}) == 3 and cfg.named_version(by_row) == 9
    assert cfg.named_version({"schema": True}) is None
    assert cfg.named_version({"governed": [{"path": "config.toml", "schema": "card@1"}], "schema": 2}) == 2


def _verify_chain() -> ModuleType:
    spec = importlib.util.spec_from_file_location("verify_chain_k11", REPO / "tools" / "verify_chain.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # a dataclass under `from __future__ import annotations` resolves through here
    spec.loader.exec_module(mod)
    return mod


def test_the_forges_verifier_inherits_the_loud_answer(checkout: Path) -> None:
    """`tools/verify_chain.py` reads the checkout through the same two functions; at the forge a fresh clone has no
    `.isidium/`, so the shipped registry is the checkout's and a version the toolkit lacks is refused, never
    verified against `config@1`."""
    write_config(checkout, 9)
    shutil.rmtree(checkout / ".isidium")
    with pytest.raises(Refusal) as refused:
        _verify_chain().verify(checkout)
    assert (refused.value.rule, refused.value.path) == ("hook.toolkit-behind", "config@9")


# ---- 6. the context file pair -------------------------------------------------------------------------------------------


def test_agents_md_and_the_claude_import_are_the_documented_pair() -> None:
    """Claude Code reads `CLAUDE.md`, not `AGENTS.md` (its memory page, read 2026-09-07); the documented form is a
    `CLAUDE.md` whose content is the import. pi reads `AGENTS.md` directly. One home, one pointer."""
    assert (REPO / "CLAUDE.md").read_bytes() == b"@AGENTS.md\n"
    agents = (REPO / "AGENTS.md").read_text(encoding="utf-8")
    for needle in ("## For the planner", "isidium install", "docs/work/", "prompts/planner/v1.md", "isidium-planner"):
        assert needle in agents, needle
