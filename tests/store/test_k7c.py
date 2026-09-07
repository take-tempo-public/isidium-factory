"""K7c — the small ones from the K7 review: F18 (one verdict for a creation in the batch), F22 (the tenant's
`.gitignore` keeps its own line ending), F23 (`--text` is the board's; a card answers JSON). Every assertion is a
positive discriminator — an exact list, a byte count, a parse, a help string — never "nothing came back".
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import typer.core
import typer.main

from isidium.store.client import cli as cli_mod
from isidium.store.client.install import ignore_client, install
from isidium.store.core.grammar import Document
from isidium.store.server.identity import Caller
from isidium.store.server.store import NewCard, Store, WriteRequest

from .conftest import BASE_SCOPE, OWNER, PLANNER, Harness, base_head, tenant_checkout
from .test_walk import client_cfg

# The typed record since K10 (Q20): the act is the verdict's detail, where K7c matched the string `…-act:created`.
CREATED: dict[str, Any] = {"rule": "ratify.not-a-signed-act", "path": "", "detail": "created"}

# ---- F18: a creation in the batch draws one verdict ------------------------------------------------------------------


def _dry(st: Store, status: str, caller: Caller) -> list[dict[str, Any]]:
    """The dry run's verdicts for one `NewCard` born with `status`; nothing is allocated (Q17's dry run)."""
    req = WriteRequest(NewCard(f"born-{status}"), Document(base_head(0, status), {"Scope": BASE_SCOPE}), None)
    verdicts = st.ratify([req], caller, dry_run=True)["verdicts"]
    assert len(verdicts) == 1
    return list(next(iter(verdicts.values())))


@pytest.mark.parametrize("caller", [OWNER, PLANNER], ids=["owner", "contributor"])
def test_a_draft_born_in_the_batch_is_refused_once_and_as_a_creation(hz: Harness, caller: Caller) -> None:
    """Exactly one `created` verdict — not two (F18: two arms fired on the same member; measured twice on tenant #0
    and in the harness), and with the creation act, which every earlier assertion (`startswith`) could not see."""
    assert _dry(hz.st, "draft", caller) == [CREATED]


def test_a_card_born_ratified_in_the_batch_is_a_signed_act_and_draws_no_verdict(hz: Harness) -> None:
    assert _dry(hz.st, "ratified", OWNER) == []


def test_a_creation_that_also_fails_validation_carries_the_creation_verdict_once(hz: Harness) -> None:
    verdicts = _dry(hz.st, "closed", OWNER)
    assert verdicts.count(CREATED) == 1, verdicts
    assert [v["rule"] for v in verdicts] == ["validate.failed", "ratify.not-a-signed-act"]


# ---- F22: the tenant's .gitignore keeps its own line ending ---------------------------------------------------------


def test_a_crlf_gitignore_keeps_every_line_crlf_and_a_second_install_changes_nothing(tmp_path: Path) -> None:
    """Three CRLF lines in, five out — the count is the discriminator (before F22: three in, none out)."""
    gi = tmp_path / ".gitignore"
    gi.write_bytes(b"# existing\r\n*.pyc\r\nbuild/\r\n")
    ignore_client(tmp_path)
    data = gi.read_bytes()
    assert data.count(b"\r\n") == 5 and data.count(b"\n") == 5, data
    assert data.startswith(b"# existing\r\n*.pyc\r\nbuild/\r\n# isidium-store: ") and data.endswith(
        b"\r\n.isidium/\r\n"
    )
    ignore_client(tmp_path)
    assert gi.read_bytes() == data


def test_an_lf_gitignore_stays_lf_and_an_absent_one_is_born_lf(tmp_path: Path) -> None:
    gi = tmp_path / ".gitignore"
    gi.write_bytes(b"*.pyc\nbuild/\n")
    ignore_client(tmp_path)
    data = gi.read_bytes()
    assert b"\r" not in data and data.count(b"\n") == 4 and data.endswith(b"\n.isidium/\n"), data
    born_in = tmp_path / "born"
    born_in.mkdir()
    ignore_client(born_in)
    born = (born_in / ".gitignore").read_bytes()
    assert b"\r" not in born and born.count(b"\n") == 2 and born.endswith(b"\n.isidium/\n"), born


def test_a_gitignore_with_no_trailing_newline_gets_one_in_its_own_ending(tmp_path: Path) -> None:
    gi = tmp_path / ".gitignore"
    gi.write_bytes(b"*.pyc\r\nbuild/")
    ignore_client(tmp_path)
    data = gi.read_bytes()
    assert data.startswith(b"*.pyc\r\nbuild/\r\n# isidium-store: ") and data.count(b"\r\n") == 4, data
    assert b"\n" not in data.replace(b"\r\n", b""), "a bare LF crept in"


def test_install_itself_keeps_a_crlf_gitignore_crlf(tmp_path: Path) -> None:
    """Through the door a tenant uses (`install`, called by `init`), not the helper alone."""
    work = tenant_checkout(tmp_path)
    (work / ".gitignore").write_bytes(b"node_modules/\r\n")
    install(work, client_cfg())
    data = (work / ".gitignore").read_bytes()
    assert data.count(b"\r\n") == 3 and data.count(b"\n") == 3 and data.endswith(b"\r\n.isidium/\r\n"), data


# ---- F23: `--text` renders the board; a card and the queue answer JSON ------------------------------------------------


@pytest.fixture
def client_here(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    work = tenant_checkout(tmp_path)
    install(work, client_cfg())
    monkeypatch.chdir(work)
    return work


class Answering:
    """A transport double: a card as the store's JSON, the board as its markdown."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def call(self, name: str, args: dict[str, Any]) -> Any:
        self.calls.append((name, dict(args)))
        if args.get("target") == "card":
            return {"id": args["id"], "label": "seven", "status": "draft"}
        return {"markdown": "# Board\n\n- 7 seven\n"}


def test_show_text_renders_the_board_and_a_card_still_answers_json(
    client_here: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    double = Answering()
    monkeypatch.setattr(cli_mod, "Transport", lambda _cfg, _workdir: double)
    cli_mod.show(target="card", id=7, text=True)
    assert json.loads(capsys.readouterr().out) == {
        "id": 7,
        "label": "seven",
        "status": "draft",
    }  # JSON, `--text` or not
    cli_mod.show(target="board", text=True)
    assert capsys.readouterr().out == "# Board\n\n- 7 seven\n\n"  # the markdown itself, plus echo's newline
    assert [args for _name, args in double.calls] == [{"target": "card", "id": 7}, {"target": "board"}]


def test_the_text_option_says_whose_it_is() -> None:
    """The help string is the contract until the card's renderer exists (F23, recorded rather than built; the queue's
    is built since K10, item 6, so the help names both)."""
    cmd = typer.main.get_command(cli_mod.app)
    assert isinstance(cmd, typer.core.TyperGroup)
    text = next(p for p in cmd.commands["show"].params if p.name == "text")
    assert isinstance(text, typer.core.TyperOption) and text.help is not None
    assert "board and queue" in text.help and "JSON" in text.help, text.help
