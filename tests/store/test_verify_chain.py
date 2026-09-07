"""The tripwire (K8): `tools/verify_chain.py` over a real tenant checkout the store wrote.

Every failing case here asserts the **line that names the path and its verdict**, never just a non-zero exit — a
script that exits 1 for the wrong reason (a missing root, a crash) would otherwise pass every one of these. The
intact case asserts the count of `ok` documents, so a run that verified nothing cannot pass it either.
"""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from isidium.store.core.grammar import Document
from isidium.store.server.store import NewCard, Store

from .conftest import BASE_SCOPE, OWNER, PLANNER, base_head, git, store_on_disk, tenant_checkout

ROOT = "docs/work/"
REPO = Path(__file__).resolve().parents[2]
TOOL = REPO / "tools" / "verify_chain.py"
SRC = REPO / "packages" / "isidium-store" / "src"


def load_tool() -> ModuleType:
    spec = importlib.util.spec_from_file_location("verify_chain", TOOL)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    # `dataclasses` resolves a module's string annotations through `sys.modules[cls.__module__]`, so a module executed
    # from a spec without being registered there fails at its first `@dataclass` under `from __future__ import
    # annotations`. Registering it is what `importlib.import_module` would have done.
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def run(repo: Path, *args: str) -> tuple[int, str]:
    """The script through its own door — the way CI runs it — so the exit code is what is asserted."""
    # The child finds the package the way pytest does (pyproject's `pythonpath`), so this does not depend on an
    # install; CI installs the package and needs no such thing.
    # **Both ends of this pipe say UTF-8** [K5, 2026-09-04]. The assertions below match on an em dash, and
    # `text=True` alone decodes with whatever the ambient locale is -- cp1252 on a Windows workstation, UTF-8
    # on the runner. This passed only because the child happened to guess the same codec as the parent, which
    # is a coincidence and not a property: anything that sets `PYTHONIOENCODING` in the environment breaks the
    # match while changing nothing about the script under test, and something did. Said at both ends, the test
    # asserts what the script printed rather than what this machine's locale made of it. Deliberately no
    # `errors=`: a byte this cannot decode should fail loudly here, which is the opposite of the harness.
    r = subprocess.run(
        [sys.executable, str(TOOL), "--repo", str(repo), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        env={**os.environ, "PYTHONPATH": str(SRC), "PYTHONIOENCODING": "utf-8"},
    )
    return r.returncode, r.stdout + r.stderr


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Store]:
    """A checkout holding what the store wrote: `config.toml` (the policy chain) and one card, pulled from the
    remote the store pushed to. **Built once per module** — a clone, a store, `init`, a write and a pull cost more
    than every assertion here put together, and nothing below needs a second store (measured 2026-09-03: nine
    per-test builds took the file past five minutes)."""
    base = tmp_path_factory.mktemp("k8")
    work = tenant_checkout(base)
    st = store_on_disk(work, base / "journal.sqlite", root=ROOT)
    st.init(OWNER, software_key_ack="ok for the gate", root=ROOT)
    st.write(NewCard("tripwire"), Document(base_head(0, "draft"), {"Scope": BASE_SCOPE}), None, None, PLANNER)
    git(work, "pull", "-q", "origin", "main")
    return work, st


@pytest.fixture
def tenant(built: tuple[Path, Store], tmp_path: Path) -> tuple[Path, Store]:
    """Each test gets its own copy of the built checkout to edit, branch and commit in; the store is shared and only
    read (`doc_schema`, `registry`)."""
    work, st = built
    copy = tmp_path / "tenant"
    shutil.copytree(work, copy)
    return copy, st


def card_file(work: Path) -> Path:
    files = sorted((work / ROOT / "cards").glob("*-tripwire.md"))
    assert len(files) == 1, files
    return files[0]


def test_an_intact_checkout_passes_and_every_document_is_named(tenant: tuple[Path, Store]) -> None:
    work, _ = tenant
    rc, out = run(work)
    assert rc == 0, out
    assert re.search(r"^ok\s+config\.toml\s+\[config@3\]\s+1 entries$", out, re.M), out  # `init` adopts the newest
    assert re.search(r"^ok\s+cards/\d+-tripwire\.md\s+\[card@1\]\s+1 entries$", out, re.M), out
    assert "isidium: 2 ok, 0 tampered," in out, out


def test_a_hand_edit_to_a_history_link_is_tampered(tenant: tuple[Path, Store]) -> None:
    work, _ = tenant
    p = card_file(work)
    text = p.read_text(encoding="utf-8")
    m = list(re.finditer(r'h = "sha256:([0-9a-f]{64})"', text))
    assert m, text
    last = m[-1]
    digest = last.group(1)
    # The flip decides on the character it replaces [K7a, F11 — the flake]. It decided on the LAST character and
    # replaced the FIRST, which is a no-op whenever they disagree the wrong way: one run in sixteen wrote the file
    # back unchanged, the tool rightly said `ok`, and the record carried "1 in 7", "2 in 17", "1 in 15" for three
    # chunks as a mechanism nobody had established. The assertion below is the positive discriminator: a hand edit
    # that edits nothing fails here, loudly, instead of failing the tool's verdict on a coin.
    flipped = ("0" if digest[0] != "0" else "1") + digest[1:]
    edited = text[: last.start(1)] + flipped + text[last.end(1) :]
    assert edited != text, "the hand edit changed nothing"
    p.write_text(edited, encoding="utf-8")
    rc, out = run(work)
    assert rc == 1, out
    assert re.search(r"^tampered\s+cards/\d+-tripwire\.md", out, re.M), out
    # and the policy chain, untouched, is still reported intact — the verdict is per document
    assert re.search(r"^ok\s+config\.toml", out, re.M), out


def test_a_hand_appended_entry_is_tampered(tenant: tuple[Path, Store]) -> None:
    """An entry copied and appended by hand carries the previous link's `h`, which cannot be the link over itself."""
    work, _ = tenant
    p = card_file(work)
    lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
    entry = [ln for ln in lines if ln.lstrip().startswith("{") and "seq = " in ln]
    assert entry, lines
    idx = lines.index(entry[-1])
    m = re.search(r"seq = (\d+)", entry[-1])
    assert m is not None, entry[-1]
    copied = entry[-1].replace(m.group(0), f"seq = {int(m.group(1)) + 1}", 1)
    lines.insert(idx + 1, copied)
    p.write_text("".join(lines), encoding="utf-8")
    rc, out = run(work)
    assert rc == 1, out
    assert re.search(r"^tampered\s+cards/\d+-tripwire\.md", out, re.M), out


def test_the_policy_chain_in_config_toml_is_verified(tenant: tuple[Path, Store]) -> None:
    work, _ = tenant
    p = work / ROOT / "config.toml"
    text = p.read_text(encoding="utf-8")
    m = list(re.finditer(r'h = "sha256:([0-9a-f]{64})"', text))
    assert m, text
    last = m[-1]
    digest = last.group(1)
    flipped = ("0" if digest[0] != "0" else "1") + digest[1:]
    p.write_text(text[: last.start(1)] + flipped + text[last.end(1) :], encoding="utf-8")
    rc, out = run(work)
    assert rc == 1, out
    assert re.search(r"^tampered\s+config\.toml", out, re.M), out


def test_a_governed_path_that_does_not_parse_is_tampered(tenant: tuple[Path, Store]) -> None:
    work, _ = tenant
    (work / ROOT / "cards" / "0999-dropped-here.md").write_text("not a card\n", encoding="utf-8")
    rc, out = run(work)
    assert rc == 1, out
    assert re.search(r"^tampered\s+cards/0999-dropped-here\.md\s+\[card@1\]\s+does not parse", out, re.M), out


def test_a_governed_change_off_main_fails_with_a_diff_base(tenant: tuple[Path, Store]) -> None:
    """7bg.6's check: a branch that touches a governed path fails; one that touches only code passes. The edit
    leaves the chain intact (the Scope, not the history) so the failure is the diff check and nothing else."""
    work, _ = tenant
    git(work, "checkout", "-q", "-b", "feature")
    p = card_file(work)
    original = p.read_text(encoding="utf-8")
    assert BASE_SCOPE in original, original
    p.write_text(original.replace(BASE_SCOPE, BASE_SCOPE + " and a word", 1), encoding="utf-8")
    (work / "README.md").write_text("a tenant, edited\n", encoding="utf-8")
    git(work, "commit", "-q", "-am", "a branch that touches a card")
    rc, out = run(work, "--diff-base", "main")
    assert rc == 1, out
    assert re.search(r"^changed\s+docs/work/cards/\d+-tripwire\.md", out, re.M), out
    assert "changed  README.md" not in out, out
    # put the card back in a second commit: the branch's net diff against main is now the README alone
    p.write_text(original, encoding="utf-8")
    git(work, "commit", "-q", "-am", "the card restored; only the README differs from main")
    rc, out = run(work, "--diff-base", "main")
    assert rc == 0, out
    assert re.search(r"^ok\s+cards/", out, re.M), out


def test_a_checkout_with_no_root_is_refused_not_passed(tmp_path: Path) -> None:
    repo = tmp_path / "bare-of-tenant"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    rc, out = run(repo)
    assert rc == 1, out
    assert "refused — hook.unknown-root" in out, out


def test_a_report_with_nothing_verified_is_not_a_pass() -> None:
    mod = load_tool()
    assert mod.Report("docs/work/").passed is False
    only_parsed = mod.Report("docs/work/", lines=[mod.Line("state.json", "sidecar@1", mod.PARSED)])
    assert only_parsed.passed is False


def test_the_doc_schema_mirror_matches_the_store(tenant: tuple[Path, Store]) -> None:
    """`tools/verify_chain.doc_schema` copies `Store.doc_schema`; this is what turns that copy from a drift risk into
    a failing test. When the builder moves into `registry/`, delete the copy and this test with it."""
    _, st = tenant
    mod = load_tool()
    refs = [r for r in st.registry.installed if st.registry.get(r).get("form") == "markdown" and r != "board@1"]
    assert refs, st.registry.installed
    for ref in refs:
        assert mod.doc_schema(st.registry, ref) == st.doc_schema(ref), ref
