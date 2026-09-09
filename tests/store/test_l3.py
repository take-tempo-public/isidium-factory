"""L3 (2026-09-09) — `accept`: the acceptance block compiled (core), run through the four runners in a checkout
(client), and the one write that closes. The channel is the api itself; the checkout is a throwaway under
`tmp_path` holding the harness store's `config.toml` and whatever a scenario needs to run.
"""

from __future__ import annotations

import http.server
import json
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from isidium.store.client import accept as accept_mod
from isidium.store.client import runners as runners_mod
from isidium.store.core import manifest as manifest_mod
from isidium.store.core.grammar import Document
from isidium.store.core.refusal import Refusal
from isidium.store.server.api import Api
from isidium.store.server.identity import Caller
from isidium.store.server.store import NewCard

from .conftest import BASE_SCOPE, OWNER, PLANNER, Harness, base_head, fresh

ROOT = "docs/work/"
SHIPPED = frozenset(runners_mod.RUNNERS)
BINDINGS = {"test": "pytest", "command": "shell", "http": "http", "file": "file"}


def refuses(rule: str, fn: Callable[[], Any]) -> Refusal:
    with pytest.raises(Refusal) as ei:
        fn()
    assert ei.value.rule == rule, str(ei.value)
    return ei.value


def checkout(tmp_path: Path, hz: Harness) -> Path:
    """A throwaway checkout: the store's own `config.toml` under the root, a test file, a data file."""
    work = tmp_path / "checkout"
    (work / ROOT).mkdir(parents=True)
    (work / ROOT / "config.toml").write_bytes(hz.st.raw["config.toml"])
    (work / "tests").mkdir()
    (work / "tests" / "test_probe.py").write_text(
        "import pytest\n\n\ndef test_green():\n    assert True\n\n\ndef test_red():\n    assert False\n\n\n"
        "@pytest.mark.slow\ndef test_marked():\n    assert True\n",
        encoding="utf-8",
    )
    (work / "pytest.ini").write_text("[pytest]\nmarkers = slow\n", encoding="utf-8")
    (work / "data.txt").write_bytes(b"hello isidium\n")  # bytes: text mode would write CRLF on Windows
    return work


def scenarios(*kinds: str, port: int = 0, fail: bool = False) -> list[dict[str, Any]]:
    """Scenarios of the named kinds, passing by construction unless `fail`."""
    out: list[dict[str, Any]] = []
    py = sys.executable
    for n, kind in enumerate(kinds, start=1):
        sid = f"S{n}"
        rule = {"rule": "R1"} if n == 1 else {}  # the bdd profile: every rule exemplified by a scenario
        if kind == "test-marker":
            out.append(
                {
                    "id": sid,
                    "kind": kind,
                    "title": "t",
                    **rule,
                    "observable": {
                        "test": "tests/test_probe.py::test_red" if fail else "tests/test_probe.py::test_green"
                    },
                }
            )
        elif kind == "command":
            out.append(
                {
                    "id": sid,
                    "kind": kind,
                    "title": "c",
                    **rule,
                    "action": {"run": [py, "-c", "print('ok')"]},
                    "observable": {"exit_code": 0, "stdout_matches": "nope" if fail else "^ok"},
                }
            )
        elif kind == "http":
            out.append(
                {
                    "id": sid,
                    "kind": kind,
                    "title": "h",
                    **rule,
                    "context": {"base_url": f"http://127.0.0.1:{port}"},
                    "action": {"method": "GET", "path": "/probe"},
                    "observable": {
                        "status": 500 if fail else 200,
                        "body_matches": "probe",
                        "headers": {"X-Probe": "yes"},
                    },
                }
            )
        elif kind == "file-assert":
            out.append(
                {
                    "id": sid,
                    "kind": kind,
                    "title": "f",
                    **rule,
                    "observable": {"path": "data.txt", "contains": "nothing" if fail else "isidium"},
                }
            )
        elif kind == "manual-evidence":
            out.append({"id": sid, "kind": kind, "title": "m", **rule, "observable": {"evidence": "the owner looked"}})
    return out


def card_with(hz: Harness, slug: str, sc: list[dict[str, Any]], *, ratify: bool = True) -> int:
    head = base_head(0, "draft")
    head["acceptance"] = {"scenarios": sc}
    if not sc:  # a ratified story must carry a runnable scenario (profile.story.acceptance); an epic need not
        head["kind"] = "epic"
        head.pop("rules", None)
        head.pop("narrative", None)
        head.pop("shape", None)
    r = hz.st.write(NewCard(slug), Document(head, {"Scope": BASE_SCOPE}), None, None, PLANNER)
    assert r.id is not None
    if ratify:
        hz.st.ratify([r.id], OWNER)
    return r.id


def channel(hz: Harness, caller: Caller) -> accept_mod.Call:
    api = Api(hz.st)
    return lambda name, args: api.call(name, caller, args)


class _Probe(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = b"probe answered"
        self.send_response(200)
        self.send_header("X-Probe", "yes")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_a: Any) -> None:
        return


@pytest.fixture
def probe_port() -> Any:
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Probe)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield srv.server_address[1]
    finally:
        srv.shutdown()


# ---- the compile (core) --------------------------------------------------------------------------------------------


def test_the_compile_binds_every_kind_and_names_the_manual_ones() -> None:
    m = manifest_mod.compile_acceptance(
        {"scenarios": scenarios("test-marker", "command", "http", "file-assert", "manual-evidence", port=1)},
        BINDINGS,
        SHIPPED,
    )
    kinds = [(e.scenario_id, type(e).__name__) for e in m.entries]
    assert kinds == [("S1", "Check"), ("S2", "Check"), ("S3", "Check"), ("S4", "Check"), ("S5", "Manual")]
    runners = [e.runner for e in m.runnable]
    assert runners == ["pytest", "shell", "http", "file"]
    assert m.entries[4].evidence == "the owner looked"  # type: ignore[union-attr]
    assert m.hash.startswith("sha256:") and len(m.hash) == 71


def test_the_compile_is_deterministic_and_its_hash_reads_the_params() -> None:
    a = manifest_mod.compile_acceptance({"scenarios": scenarios("command")}, BINDINGS, SHIPPED)
    sc = scenarios("command")
    sc[0] = dict(reversed(list(sc[0].items())))  # the same scenario, keys in another order
    b = manifest_mod.compile_acceptance({"scenarios": sc}, BINDINGS, SHIPPED)
    assert a.hash == b.hash and a.as_json() == b.as_json()
    sc2 = scenarios("command")
    sc2[0]["observable"]["exit_code"] = 3
    assert manifest_mod.compile_acceptance({"scenarios": sc2}, BINDINGS, SHIPPED).hash != a.hash


def test_an_unbindable_scenario_is_a_typed_compile_error_naming_it() -> None:
    r = refuses(
        "accept.unbindable",
        lambda: manifest_mod.compile_acceptance(
            {"scenarios": scenarios("http", port=1)}, {**BINDINGS, "http": "curl"}, SHIPPED
        ),
    )
    assert r.path == "acceptance.scenarios.S1" and "curl" in r.detail
    r = refuses(
        "accept.unbindable",
        lambda: manifest_mod.compile_acceptance(
            {"scenarios": scenarios("test-marker")}, {k: v for k, v in BINDINGS.items() if k != "test"}, SHIPPED
        ),
    )
    assert r.path == "acceptance.scenarios.S1"
    no_obs = [{"id": "S1", "kind": "command", "title": "c", "action": {"run": ["x"]}, "observable": {}}]
    refuses("accept.unbindable", lambda: manifest_mod.compile_acceptance({"scenarios": no_obs}, BINDINGS, SHIPPED))
    no_base = [
        {
            "id": "S1",
            "kind": "http",
            "title": "h",
            "action": {"method": "GET", "path": "/"},
            "observable": {"status": 200},
        }
    ]
    refuses("accept.unbindable", lambda: manifest_mod.compile_acceptance({"scenarios": no_base}, BINDINGS, SHIPPED))
    bad_shape = [
        {"id": "S1", "kind": "command", "title": "c", "action": {"run": "not an argv"}, "observable": {"exit_code": 0}}
    ]
    r = refuses("scenario.shape", lambda: manifest_mod.compile_acceptance({"scenarios": bad_shape}, BINDINGS, SHIPPED))
    assert r.path == "acceptance.scenarios.S1"


# ---- the runners (client), each on a real checkout -------------------------------------------------------------------


def test_each_runner_answers_pass_and_fail_on_a_real_checkout(tmp_path: Path, probe_port: int) -> None:
    hz = fresh()
    work = checkout(tmp_path, hz)
    for kind in ("test-marker", "command", "http", "file-assert"):
        for fail in (False, True):
            m = manifest_mod.compile_acceptance(
                {"scenarios": scenarios(kind, port=probe_port, fail=fail)}, BINDINGS, SHIPPED
            )
            v = runners_mod.RUNNERS[m.runnable[0].runner](m.runnable[0], work)
            assert v.verdict == ("fail" if fail else "pass"), (kind, fail, v)
            assert v.detail, "a verdict carries its reason"


def test_the_pytest_runner_takes_markers_and_the_tests_list(tmp_path: Path) -> None:
    hz = fresh()
    work = checkout(tmp_path, hz)
    marked = [
        {
            "id": "S1",
            "kind": "test-marker",
            "title": "m",
            "observable": {"marker": "slow"},
            "tests": ["tests/test_probe.py::test_green"],
        }
    ]
    m = manifest_mod.compile_acceptance({"scenarios": marked}, BINDINGS, SHIPPED)
    assert m.runnable[0].tests == ("tests/test_probe.py::test_green",)
    assert runners_mod.run_pytest(m.runnable[0], work).verdict == "pass"
    absent = [{"id": "S1", "kind": "test-marker", "title": "m", "observable": {"test": "tests/nowhere.py::test_x"}}]
    m2 = manifest_mod.compile_acceptance({"scenarios": absent}, BINDINGS, SHIPPED)
    refuses("accept.runner-error", lambda: runners_mod.run_pytest(m2.runnable[0], work))


def test_the_file_check_judges_each_of_the_five_forms_inside_the_checkout(tmp_path: Path) -> None:
    hz = fresh()
    work = checkout(tmp_path, hz)
    import hashlib

    digest = hashlib.sha256((work / "data.txt").read_bytes()).hexdigest()
    (work / "copy.txt").write_bytes((work / "data.txt").read_bytes())
    assert runners_mod.file_check(work, {"path": "data.txt", "exists": True})[0]
    assert not runners_mod.file_check(work, {"path": "absent.txt", "exists": True})[0]
    assert runners_mod.file_check(work, {"path": "absent.txt", "exists": False})[0]
    assert runners_mod.file_check(work, {"path": "data.txt", "contains": "isidium"})[0]
    assert runners_mod.file_check(work, {"path": "data.txt", "matches": "^hello\\s+isidium$"})[0]
    assert runners_mod.file_check(work, {"path": "data.txt", "sha256": "sha256:" + digest})[0]
    assert runners_mod.file_check(work, {"path": "data.txt", "equals_file": "copy.txt"})[0]
    assert not runners_mod.file_check(work, {"path": "data.txt", "equals_file": "tests/test_probe.py"})[0]
    refuses("accept.runner-error", lambda: runners_mod.file_check(work, {"path": "../outside.txt", "exists": True}))


def test_a_runner_that_cannot_run_is_an_error_not_a_verdict(tmp_path: Path) -> None:
    hz = fresh()
    work = checkout(tmp_path, hz)
    sc = [
        {
            "id": "S1",
            "kind": "command",
            "title": "c",
            "action": {"run": ["no-such-program-anywhere"]},
            "observable": {"exit_code": 0},
        }
    ]
    m = manifest_mod.compile_acceptance({"scenarios": sc}, BINDINGS, SHIPPED)
    refuses("accept.runner-error", lambda: runners_mod.run_shell(m.runnable[0], work))
    sc2 = [
        {
            "id": "S1",
            "kind": "http",
            "title": "h",
            "context": {"base_url": "http://127.0.0.1:9"},
            "action": {"method": "GET", "path": "/"},
            "observable": {"status": 200},
        }
    ]
    m2 = manifest_mod.compile_acceptance({"scenarios": sc2}, BINDINGS, SHIPPED)
    refuses("accept.runner-error", lambda: runners_mod.run_http(m2.runnable[0], work))


# ---- the verb: one read, the runs, at most one write --------------------------------------------------------------------


def test_accept_reads_the_store_runs_the_checkout_and_closes_met(tmp_path: Path, probe_port: int) -> None:
    hz = fresh()
    work = checkout(tmp_path, hz)
    cid = card_with(hz, "green", scenarios("test-marker", "command", "http", "file-assert", port=probe_port))
    r = accept_mod.accept(channel(hz, PLANNER), work, ROOT, cid)
    assert r["passed"] is True and [v["verdict"] for v in r["verdicts"]] == ["pass"] * 4 and "closed" not in r
    assert hz.st.projection_of(cid).label.row in ("ratified", "ready"), "accept without --close writes nothing"
    r2 = accept_mod.accept(channel(hz, PLANNER), work, ROOT, cid, close=True)
    assert r2["closed"]["entry"]["act"] == "closed" and r2["closed"]["landed"] is True
    doc = hz.st.docs[hz.st.path_of(cid) or ""]
    c = doc.head["closures"][-1]
    assert c["id"] == "c1" and c["kind"] == "human" and c["outcome"] == "met" and c["evidence"] == [r2["manifest_hash"]]
    assert c["verdicts"] == {"S1": "pass", "S2": "pass", "S3": "pass", "S4": "pass"} and doc.head["status"] == "closed"
    # 1.5 row 7: a human claim on `main` not yet ingested — the land (L4's ingest) is what verifies it
    assert hz.st.projection_of(cid).label.render() == "closed (pending-ingest)"


def test_a_failing_verdict_refuses_to_close_unless_deviated(tmp_path: Path) -> None:
    hz = fresh()
    work = checkout(tmp_path, hz)
    cid = card_with(hz, "red", scenarios("command", "file-assert", fail=True))
    r = accept_mod.accept(channel(hz, PLANNER), work, ROOT, cid)
    assert r["passed"] is False and [v["verdict"] for v in r["verdicts"]] == ["fail", "fail"]
    e = refuses("accept.failed", lambda: accept_mod.accept(channel(hz, PLANNER), work, ROOT, cid, close=True))
    assert "S1, S2" in e.detail and hz.st.projection_of(cid).label.row in ("ratified", "ready")
    r2 = accept_mod.accept(channel(hz, PLANNER), work, ROOT, cid, close=True, deviated="the probe is red on purpose")
    c = hz.st.docs[hz.st.path_of(cid) or ""].head["closures"][-1]
    assert (
        c["outcome"] == {"deviated": {"description": "the probe is red on purpose"}}
        and r2["closed"]["entry"]["act"] == "closed"
    )
    assert hz.st.projection_of(cid).label.render() == "closed (pending-review)"


def test_a_manual_scenario_is_a_manual_verdict_and_not_met(tmp_path: Path) -> None:
    hz = fresh()
    work = checkout(tmp_path, hz)
    cid = card_with(hz, "manual", scenarios("command", "manual-evidence"))
    r = accept_mod.accept(channel(hz, PLANNER), work, ROOT, cid)
    assert [v["verdict"] for v in r["verdicts"]] == ["pass", "manual"] and r["passed"] is False
    refuses("accept.failed", lambda: accept_mod.accept(channel(hz, PLANNER), work, ROOT, cid, close=True))


def test_a_draft_is_refused_and_unsafe_draft_asks_per_command(tmp_path: Path) -> None:
    hz = fresh()
    work = checkout(tmp_path, hz)
    cid = card_with(hz, "planted", scenarios("command", "file-assert", "test-marker"), ratify=False)
    refuses("accept.draft", lambda: accept_mod.accept(channel(hz, PLANNER), work, ROOT, cid))
    asked: list[str] = []

    def decline(q: str) -> bool:
        asked.append(q)
        return False

    r = accept_mod.accept(channel(hz, PLANNER), work, ROOT, cid, unsafe_draft=True, confirm=decline)
    assert len(asked) == 2 and "S1 (command) would run:" in asked[0] and "S2 (file-assert)" in asked[1]
    assert [v["verdict"] for v in r["verdicts"]] == ["fail", "fail", "pass"], "declined ones fail; the test ran"
    r2 = accept_mod.accept(channel(hz, PLANNER), work, ROOT, cid, unsafe_draft=True, confirm=lambda _q: True)
    assert r2["passed"] is True


def test_an_unratified_card_is_refused_before_anything_runs(tmp_path: Path) -> None:
    """The label is the store's and `accept` obeys it: `unratified` (a gated edit that reached `main` without a
    signature — a bypass, which no door of the store produces, so the channel here answers the store's word for
    it), `integrity(reason)` and `withdrawn` refuse before the block is compiled or anything runs."""
    hz = fresh()
    work = checkout(tmp_path, hz)
    sc = [
        {
            "id": "S1",
            "kind": "command",
            "title": "c",
            "rule": "R1",
            "action": {"run": ["never-run"]},
            "observable": {"exit_code": 0},
        }
    ]
    cid = card_with(hz, "drifted", sc)
    api = Api(hz.st)
    for label in ("unratified", "integrity(unverified)", "withdrawn (pending-review)"):

        def relabelled(name: str, args: Any, label: str = label) -> Any:
            r = api.call(name, PLANNER, args)
            if name == "show":
                r["label"] = label
            return r

        e = refuses("accept.unratified", lambda: accept_mod.accept(relabelled, work, ROOT, cid))
        assert label in e.detail


def test_the_dial_decides_whether_a_card_with_no_scenario_may_close(tmp_path: Path) -> None:
    hz = fresh()
    work = checkout(tmp_path, hz)
    cid = card_with(hz, "bare", [])
    refuses("accept.no-verdicts", lambda: accept_mod.accept(channel(hz, PLANNER), work, ROOT, cid, close=True))
    tree = json.loads(json.dumps(hz.st.config_tree))
    tree.setdefault("ratification", {})["verdicts_required"] = False
    hz.st.write("config.toml", tree, {"seq": hz.st.policy[-1]["seq"], "h": hz.st.policy[-1]["h"]}, None, OWNER)
    (work / ROOT / "config.toml").write_bytes(hz.st.raw["config.toml"])
    r = accept_mod.accept(channel(hz, PLANNER), work, ROOT, cid, close=True)
    assert r["closed"]["entry"]["act"] == "closed"
    assert hz.st.docs[hz.st.path_of(cid) or ""].head["closures"][-1]["verdicts"] == {}


def test_the_cli_verb_exits_by_verdict(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from typer.testing import CliRunner

    from isidium.store.client import cli as cli_mod

    calls: list[dict[str, Any]] = []

    def fake_accept(call: Any, workdir: Path, root: str, cid: int, **kw: Any) -> dict[str, Any]:
        calls.append({"cid": cid, **kw})
        return {
            "id": cid,
            "label": "ratified",
            "manifest_hash": "sha256:x",
            "verdicts": [{"scenario_id": "S1", "verdict": "fail", "detail": "red"}],
            "passed": cid == 1,
        }

    monkeypatch.setattr(accept_mod, "accept", fake_accept)
    monkeypatch.setattr(
        cli_mod,
        "_transport",
        lambda: (type("T", (), {"call": staticmethod(lambda n, a: None)})(), type("C", (), {"root": ROOT})(), tmp_path),
    )
    res = CliRunner().invoke(cli_mod.app, ["accept", "1", "--close", "--deviated", "why"])
    assert res.exit_code == 0 and calls[-1]["close"] is True and calls[-1]["deviated"] == "why", res.output
    res = CliRunner().invoke(cli_mod.app, ["accept", "2", "--text"])
    assert res.exit_code == 1 and "S1     fail" in res.output and "not met" in res.output, res.output
