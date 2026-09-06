"""`tools/mutate.py --show` [K7c, F24]: the bytes a mutation would write, seen as a diff before a run; an empty
mutation refused. The tool is loaded the way `test_osv_scan.py` loads its own. Every spec here names a file under
`tmp_path`, and the in-flight state file is pointed there too — `main()` repairs a tree it finds mutated before it
does anything else, and a test that let it look at the repository's own state file would undo a mutation run in
progress. Nothing here touches the repository: asserted, not assumed."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[2]
TOOL = REPO / "tools" / "mutate.py"


def load_tool() -> ModuleType:
    spec = importlib.util.spec_from_file_location("mutate_under_test", TOOL)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def tool(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    mod = load_tool()
    monkeypatch.setattr(mod, "STATE", tmp_path / "in-flight.json")
    return mod


def spec_for(tmp_path: Path, target: Path, find: str, replace: str, mid: str = "M1") -> Path:
    """A one-mutation spec in `'''` literal strings, written the way a spec author writes one: a backslash stays a
    backslash and a real newline stays a newline — the two shapes F24 exists to tell apart."""
    body = (
        "[[mutation]]\n"
        f'id = "{mid}"\n'
        'label = "the probe"\n'
        f'file = "{target.as_posix()}"\n'
        f"find = '''{find}'''\n"
        f"replace = '''{replace}'''\n"
    )
    spec = tmp_path / f"{mid}.toml"
    spec.write_bytes(body.encode("utf-8"))
    return spec


def run_show(tool: ModuleType, monkeypatch: pytest.MonkeyPatch, spec: Path) -> int:
    monkeypatch.setattr(sys, "argv", ["mutate.py", str(spec), "--show"])
    code = tool.main()
    assert isinstance(code, int)
    return code


def test_show_prints_the_removed_and_the_added_line_and_writes_nothing(
    tool: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "t.py"
    original = b"a = 1\nb = 2\nc = 3\n"
    target.write_bytes(original)
    assert run_show(tool, monkeypatch, spec_for(tmp_path, target, "b = 2", "b = 20")) == 0
    out = capsys.readouterr().out
    assert "-b = 2\n" in out and "+b = 20\n" in out and " a = 1\n" in out and " c = 3" in out, out
    assert target.read_bytes() == original and not (tmp_path / "in-flight.json").exists()


def test_show_tells_a_kept_backslash_escape_from_a_real_line_break(
    tool: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The K4b trap, visible: a `\\n` a literal string kept is one added line holding two characters; a real line
    break is a second added line."""
    target = tmp_path / "t.py"
    target.write_bytes(b"x = 1\n")
    kept = spec_for(tmp_path, target, "x = 1", "x = 1\\ny = 2", mid="M1")
    assert run_show(tool, monkeypatch, kept) == 0
    out = capsys.readouterr().out
    assert "+x = 1\\ny = 2\n" in out and "+y = 2" not in out, out
    real = spec_for(tmp_path, target, "x = 1", "x = 1\ny = 2", mid="M2")
    assert run_show(tool, monkeypatch, real) == 0
    out = capsys.readouterr().out
    assert "+y = 2\n" in out and "\\n" not in out, out


def test_show_is_ascii_whatever_the_file_holds(
    tool: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """This console is cp1252; a harness that dies on its own output is worse than none (the module's own rule)."""
    target = tmp_path / "t.py"
    target.write_bytes("# a dash — here\nx = 1\n".encode())
    assert run_show(tool, monkeypatch, spec_for(tmp_path, target, "x = 1", "x = 2")) == 0
    out = capsys.readouterr().out
    assert out.isascii() and "\\u2014" in out and "+x = 2\n" in out, out


def test_an_empty_mutation_is_refused_with_the_sentence(
    tool: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "t.py"
    target.write_bytes(b"x = 1\n")
    assert run_show(tool, monkeypatch, spec_for(tmp_path, target, "x = 1", "x = 1")) == 1
    out = capsys.readouterr().out
    assert "REFUSED: its `replace` is its `find` -- an empty mutation proves nothing" in out, out
    assert "1 refused: M1" in out and "---" not in out, out


def test_a_find_that_is_not_there_is_refused_with_its_count(
    tool: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "t.py"
    target.write_bytes(b"x = 1\n")
    assert run_show(tool, monkeypatch, spec_for(tmp_path, target, "nope", "yes")) == 1
    assert "REFUSED: its `find` text appears 0 times in t.py" in capsys.readouterr().out
