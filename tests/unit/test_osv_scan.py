"""The advisory gate (K5): `tools/osv_scan.py` over this repository's own lock, with OSV replaced by a double.

**Every case asserts the sentence, not the exit code.** A scanner that exits 2 because it crashed and one that
exits 2 because the control did not reproduce are different findings, and only the message tells them apart.

**No test here reaches the network.** `_post` and `_get` are replaced per test; a test that quietly hit
api.osv.dev would pass on a day the endpoint was healthy and be a flake on any other, which is the same class of
defect as passing on silence. The one thing read for real is `uv.lock` — the file the tool exists to read.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
TOOL = REPO / "tools" / "osv_scan.py"
LOCK = REPO / "uv.lock"


def load_tool() -> ModuleType:
    spec = importlib.util.spec_from_file_location("osv_scan", TOOL)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def tool() -> ModuleType:
    return load_tool()


def install_double(
    tool: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    *,
    vulns: dict[tuple[str, str], list[str]] | None = None,
    control_ids: list[str] | None = None,
    drop_results: int = 0,
    page: dict[str, list[str]] | None = None,
) -> list[dict[str, Any]]:
    """A querybatch that answers positionally, so a test can hand back the wrong shape on purpose."""
    hits = vulns or {}
    posted: list[dict[str, Any]] = []

    def fake_post(url: str, payload: dict[str, Any]) -> dict[str, Any]:
        posted.append(payload)
        results: list[dict[str, Any]] = []
        for query in payload["queries"]:
            key = (query["package"]["name"], query["version"])
            if "page_token" in query:
                results.append({"vulns": [{"id": i} for i in (page or {}).get("second", [])]})
                continue
            if key == (tool.CONTROL_NAME, tool.CONTROL_VERSION):
                ids = tool.CONTROL_ADVISORY if control_ids is None else None
                found = [ids] if ids else list(control_ids or [])
                results.append({"vulns": [{"id": i} for i in found]} if found else {})
                continue
            found = list(hits.get(key, []))
            entry: dict[str, Any] = {"vulns": [{"id": i} for i in found]} if found else {}
            if page and key == page["on"]:  # type: ignore[comparison-overlap]
                entry = {"vulns": [{"id": i} for i in page["first"]], "next_page_token": "more"}
            results.append(entry)
        return {"results": results[: len(results) - drop_results] if drop_results else results}

    def fake_get(url: str) -> dict[str, Any]:
        return {"summary": "a summary the report must carry", "aliases": ["CVE-0000-0000"]}

    monkeypatch.setattr(tool, "_post", fake_post)
    monkeypatch.setattr(tool, "_get", fake_get)
    return posted


def test_the_lock_is_read_and_workspace_members_are_not_asked_about(tool: ModuleType) -> None:
    """A workspace member has no upstream to have an advisory against; asking names a stranger."""
    pairs = tool.locked_packages(LOCK)
    assert len(pairs) > 20, f"this repository's lock holds more than twenty registry packages; got {len(pairs)}"
    names = {name for name, _ in pairs}
    assert "pydantic" in names and "cryptography" in names, f"a real dependency is missing from {sorted(names)}"
    assert not names & {"isidium-store", "isidium-factory"}, "a workspace member was queued for OSV"
    assert all(version and version[0].isdigit() for _, version in pairs), "a version is not a version"


def test_one_call_carries_every_package(
    tool: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The efficiency property, asserted as a count: one POST, not one per package."""
    posted = install_double(tool, monkeypatch)
    assert tool.main(["--lock", str(LOCK)]) == 0
    assert len(posted) == 1, f"{len(posted)} POSTs for one scan"
    queried = len(posted[0]["queries"])
    assert queried == len(tool.locked_packages(LOCK)) + 1, "the batch is the lock plus the control, exactly"
    out = capsys.readouterr().out
    assert f"{queried - 1} locked packages queried" in out
    assert "no advisory against any locked version" in out


def test_an_advisory_against_a_locked_version_fails_and_names_it(
    tool: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    victim = tool.locked_packages(LOCK)[0]
    install_double(tool, monkeypatch, vulns={victim: ["GHSA-test-0001"]})
    assert tool.main(["--lock", str(LOCK)]) == 1
    err = capsys.readouterr().err
    assert f"{victim[0]} {victim[1]}: GHSA-test-0001" in err, err
    assert "a summary the report must carry" in err, "the advisory detail was never fetched"
    assert "CVE-0000-0000" in err


def test_a_control_that_does_not_reproduce_refuses_rather_than_reporting_clean(
    tool: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """**The discriminator.** Every locked version is clean here — the only thing wrong is that the known-vulnerable
    control came back clean too, which is what a moved endpoint, a renamed ecosystem or a changed schema looks
    like. Reporting 0 on this input is the defect the control exists to catch."""
    install_double(tool, monkeypatch, control_ids=[])
    assert tool.main(["--lock", str(LOCK)]) == 2
    err = capsys.readouterr().err
    assert "the control did not reproduce" in err
    assert tool.CONTROL_ADVISORY in err and tool.CONTROL_NAME in err


def test_a_control_answering_with_some_other_advisory_is_not_good_enough(
    tool: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ "Something came back" is not the property; *that* advisory is."""
    install_double(tool, monkeypatch, control_ids=["GHSA-something-else"])
    assert tool.main(["--lock", str(LOCK)]) == 2


def test_a_short_answer_is_refused_rather_than_read_positionally(
    tool: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Results are matched to queries by position, so a result count that disagrees would silently attribute one
    package's advisories to another. It refuses instead."""
    install_double(tool, monkeypatch, drop_results=1)
    assert tool.main(["--lock", str(LOCK)]) == 2
    assert "positional read unsafe" in capsys.readouterr().err


def test_a_paged_result_is_followed_to_the_end(
    tool: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    victim = tool.locked_packages(LOCK)[0]
    install_double(tool, monkeypatch, page={"on": victim, "first": ["GHSA-page-1"], "second": ["GHSA-page-2"]})
    assert tool.main(["--lock", str(LOCK)]) == 1
    err = capsys.readouterr().err
    assert "GHSA-page-1" in err and "GHSA-page-2" in err, f"a page was dropped: {err}"


def test_an_empty_lock_is_a_wrong_lock_and_not_a_clean_one(
    tool: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    empty = tmp_path / "uv.lock"
    empty.write_text('version = 1\nrequires-python = ">=3.12"\n', encoding="utf-8")
    install_double(tool, monkeypatch)
    assert tool.main(["--lock", str(empty)]) == 2
    assert "named no registry packages" in capsys.readouterr().err


def test_a_missing_lock_is_refused(tool: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert tool.main(["--lock", str(tmp_path / "absent.lock")]) == 2
    assert "no lock at" in capsys.readouterr().err


def test_an_unreachable_osv_proves_nothing_and_says_so(
    tool: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The failure mode that must never read as clean: the scan did not happen."""

    def refuse(url: str, payload: dict[str, Any]) -> dict[str, Any]:
        raise TimeoutError("the socket went nowhere")

    monkeypatch.setattr(tool, "_post", refuse)
    assert tool.main(["--lock", str(LOCK)]) == 2
    assert "nothing was proven" in capsys.readouterr().err


def test_the_control_is_never_counted_as_a_finding(
    tool: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The control is a known-vulnerable version by construction. If it leaked into the findings the gate would be
    red forever and every real advisory would arrive as noise."""
    install_double(tool, monkeypatch)
    assert tool.main(["--lock", str(LOCK)]) == 0
    captured = capsys.readouterr()
    assert tool.CONTROL_NAME not in captured.err
    assert f"{tool.CONTROL_NAME} {tool.CONTROL_VERSION}" not in captured.out


def test_the_control_version_is_not_the_version_the_lock_holds(tool: ModuleType) -> None:
    """If the lock ever pinned h11 at the control's own version the control would stop being a control and start
    being a real finding. Both would then be true and neither would be legible."""
    locked = dict(tool.locked_packages(LOCK))
    assert locked.get(tool.CONTROL_NAME) != tool.CONTROL_VERSION
