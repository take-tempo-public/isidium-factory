"""Card 24: builder prompt v5 requires, before the builder finishes and in both build and reconcile, `ruff check`,
`ruff format --check` and `mypy --strict` on every file it changed — by path, never the whole tree — and fixing what
they report inside the surfaces (R1); keeps v4's rule that the project's gate is not the builder's to run (R2); and
is otherwise v4's text, with v4 itself unedited (R3). The tests read both prompt files as text and bytes only — no
runner or harness code is imported.
"""

from __future__ import annotations

import difflib
import hashlib
import re
from pathlib import Path

_PROMPTS = Path(__file__).resolve().parents[2] / "prompts" / "builder"
V4 = _PROMPTS / "v4.md"
V5 = _PROMPTS / "v5.md"

# v4's git blob id as ratified (card 24's ref) — any byte edit to v4 changes it.
V4_BLOB = "6e2d6f79ae88a1afb6c6b55296e1acb4a0e8abc9"

# The anchors of the v4 text v5 may change; each is located by its text, never by a line number.
_TITLE = "# The builder — v"
_STATUS = "> **Status:**"
_ITEM_3 = "3. **Run the card's own tests, and only those.**"
_ITEM_4 = "4. **Stay inside the surfaces.**"
_SIX = "## 6. "
_SEVEN = "## 7. "
_SIX_ITEM_3 = "3. **Run the tests that own what you changed, and only those**"
_SIX_ITEM_4 = "4. **Answer with the report.**"

# What a prompt must say, flattened, for the per-file checks to be required.
_REQUIRED = (
    "ruff check",
    "ruff format --check",
    "mypy --strict",
    "every file you changed",
    "by path",
    "never the whole tree",
    "inside the surfaces",
)

# Invocations that would make the builder run the project's gate (R2).
_WHOLE_TREE = ("ruff check .", "ruff format --check .", "mypy packages", "pytest tests", "mypy .")


def _flat(text: str) -> str:
    """The text with every run of whitespace — a hard-wrap included — collapsed to one space."""
    return re.sub(r"\s+", " ", text)


def _section(text: str, start: str, end: str) -> str:
    """The text from `start` up to `end`, flattened. A missing anchor raises, so a moved or renamed section fails
    loudly rather than passing on an empty slice."""
    first = text.index(start)
    return _flat(text[first : text.index(end, first)])


def _requires_per_file_checks(section: str) -> bool:
    return all(phrase in section for phrase in _REQUIRED)


def _item_3(text: str) -> str:
    return _section(text, _ITEM_3, _ITEM_4)


def _reconcile(text: str) -> str:
    return _section(text, _SIX, _SEVEN)


def test_v5_requires_ruff_and_mypy_on_the_changed_files() -> None:
    v5 = V5.read_text(encoding="utf-8")
    item = _item_3(v5)
    assert _requires_per_file_checks(item)
    assert "before you finish" in item
    # The discriminator: v4 names the tools only as optional, so a v5 that is a copy of v4 fails here.
    assert not _requires_per_file_checks(_item_3(V4.read_text(encoding="utf-8")))


def test_v5_applies_it_in_reconcile_too() -> None:
    v5 = V5.read_text(encoding="utf-8")
    assert _requires_per_file_checks(_reconcile(v5))
    assert "reconcile" in _item_3(v5)
    # The check sits in §6's own run-the-tests item, before the report item.
    assert _requires_per_file_checks(_section(v5, _SIX_ITEM_3, _SIX_ITEM_4))
    assert not _requires_per_file_checks(_reconcile(V4.read_text(encoding="utf-8")))


def test_v5_keeps_the_whole_gate_green_bars() -> None:
    v5 = V5.read_text(encoding="utf-8")
    item = _item_3(v5)
    assert "**The project's gate is not yours to run.**" in item
    assert "green-bar" in item
    assert "never the whole tree" in item
    flat = _flat(v5)
    for invocation in _WHOLE_TREE:
        assert invocation not in flat


def _allowed(v4_lines: list[str]) -> list[tuple[int, int]]:
    """The half-open ranges of v4 lines v5 may change: provenance, title, Status, §2 item 3, §6 item 3."""

    def at(prefix: str) -> int:
        return next(i for i, line in enumerate(v4_lines) if line.startswith(prefix))

    return [
        (0, 1),
        (at(_TITLE), at(_TITLE) + 1),
        (at(_STATUS), at(_STATUS) + 1),
        (at(_ITEM_3), at(_ITEM_4)),
        (at(_SIX_ITEM_3), at(_SIX_ITEM_4)),
    ]


def _inside(i1: int, i2: int, allowed: list[tuple[int, int]]) -> bool:
    """A replace or delete must lie wholly inside one allowed range; a pure insertion may land anywhere in one,
    its far edge included."""
    if i1 == i2:
        return any(lo <= i1 <= hi for lo, hi in allowed)
    return any(lo <= i1 and i2 <= hi for lo, hi in allowed)


def test_v5_is_v4_plus_the_change() -> None:
    v4_bytes = V4.read_bytes()
    v5_bytes = V5.read_bytes()
    # v4 is unedited: its blob id is the ratified one.
    assert hashlib.sha1(b"blob %d\0" % len(v4_bytes) + v4_bytes).hexdigest() == V4_BLOB
    assert b"\r" not in v5_bytes
    assert v5_bytes != v4_bytes

    v4 = v4_bytes.decode("utf-8")
    v5 = v5_bytes.decode("utf-8")
    assert "version=5" in v5.splitlines()[0]
    assert "# The builder — v5" in v5
    assert "What changed in v5" in v5

    v4_lines = v4.splitlines()
    allowed = _allowed(v4_lines)
    ops = difflib.SequenceMatcher(None, v4_lines, v5.splitlines(), autojunk=False).get_opcodes()
    for tag, i1, i2, _j1, _j2 in ops:
        if tag != "equal":
            assert _inside(i1, i2, allowed), (tag, v4_lines[i1:i2])
