"""The PR watcher's timer (card 30): `deploy/watch-task.ps1` and the README section that describes it.

CI runs on Linux and a test may not touch the host's scheduler, so every test here reads the script as text and pins what
it says. A pin is matched against the script's **code** -- `<# #>` blocks and full-line `#` comments removed -- so a
comment that still names a behaviour cannot hold up a test for code that no longer does it. The one thing read from
comments is the reason the execution limit carries beside it (card 30, C1)."""

from __future__ import annotations

import re
from pathlib import Path

from isidium.factory import cli, container
from isidium.factory.adapter import ExecutorPolicy
from isidium.store.registry import config as cfg
from isidium.store.registry.loader import Registry

ROOT = Path(__file__).parent.parent.parent
SCRIPT = ROOT / "deploy" / "watch-task.ps1"
README = ROOT / "deploy" / "README.md"
TENANT_ZERO_CONFIG = ROOT / "docs" / "work" / "config.toml"

BLOCK_COMMENT = re.compile(r"<#.*?#>", re.DOTALL)
CADENCE = re.compile(r"^\s*\$CadenceMinutes\s*=\s*(\d+)\s*$")
LIMIT = re.compile(r"^\s*\$LimitHours\s*=\s*(\d+)\s*$")
SECTION = "## The PR watcher's timer"


def _code(text: str) -> list[str]:
    """The script's code lines: block comments and full-line comments gone, blank lines gone."""
    lines = BLOCK_COMMENT.sub("", text).splitlines()
    return [ln for ln in lines if ln.strip() and not ln.strip().startswith("#")]


def _script_code() -> list[str]:
    return _code(SCRIPT.read_text(encoding="utf-8"))


def _only(code: list[str], pattern: re.Pattern[str]) -> int:
    """The number a whole-line assignment sets, required to be there exactly once."""
    found = [m.group(1) for ln in code if (m := pattern.match(ln))]
    assert len(found) == 1, f"{pattern.pattern}: expected one assignment among the code lines, found {found}"
    return int(found[0])


def _lines_with(code: list[str], needle: str) -> list[str]:
    return [ln for ln in code if needle in ln]


def _signed_wall_clock_s() -> int:
    """`[executor].wall_clock_s` as tenant #0's adopted config resolves it -- the figure `cli._fixup_bound` multiplies."""
    registry = Registry.shipped()
    tree, _entries, refusals = cfg.parse_and_validate(TENANT_ZERO_CONFIG.read_text(encoding="utf-8"), registry)
    assert not refusals, [str(r) for r in refusals]
    return ExecutorPolicy.from_effective(cfg.resolve_effective(tree, registry)).budgets.wall_clock_s


def test_the_task_runs_one_pass_every_15_minutes() -> None:
    code = _script_code()
    assert not [ln for ln in code if re.search(r"\s#", ln)], "a trailing comment hides in a code line from the pins"

    assert _only(code, CADENCE) == 15
    triggers = _lines_with(code, "New-ScheduledTaskTrigger")
    assert len(triggers) == 1
    assert "-RepetitionInterval (New-TimeSpan -Minutes $CadenceMinutes)" in triggers[0]

    runs = _lines_with(code, "watch --once")
    assert len(runs) == 1
    assert "& $Exe watch --once --tenant $Tenant --checkout $Checkout" in runs[0]
    assert "isidium-factory" not in runs[0], "the verb is run from the path the registration resolved"

    assert "$env:ISIDIUM_DEPLOY = $Deploy" in [ln.strip() for ln in code]
    assert "$env:PYTHONIOENCODING = 'utf-8'" in [ln.strip() for ln in code]

    registers = _lines_with(code, "Register-ScheduledTask")
    assert len(registers) == 1
    assert "-Force" in registers[0], "running it again replaces the task"
    assert '$TaskName = "isidium-watch-$Tenant"' in [ln.strip() for ln in code], "one task per tenant"


def test_no_second_instance_and_a_limit() -> None:
    code = _script_code()
    settings = _lines_with(code, "New-ScheduledTaskSettingsSet")
    assert len(settings) == 1
    assert "-MultipleInstances IgnoreNew" in settings[0]
    assert len(_lines_with(code, "-MultipleInstances")) == 1, "no other instance policy anywhere"
    assert "-ExecutionTimeLimit (New-TimeSpan -Hours $LimitHours)" in settings[0]

    # The limit outlasts a close's lease plus a fixup's bound (the same sum `cli._fixup_bound` makes), so a pass cannot
    # outlive the leases it acts under. Both halves come from the code, and the second from the signed config.
    limit_s = _only(code, LIMIT) * 3600
    bound_s = cli.CLOSE_LEASE_S + _signed_wall_clock_s() * container.ATTEMPTS
    assert limit_s > bound_s, f"the limit is {limit_s} s and a close plus a fixup can take {bound_s} s"

    # The reason sits beside the number: the full-line comment block that touches the assignment.
    raw = SCRIPT.read_text(encoding="utf-8").splitlines()
    at = [i for i, ln in enumerate(raw) if LIMIT.match(ln)]
    assert len(at) == 1
    block: list[str] = []
    for ln in reversed(raw[: at[0]]):
        if not ln.strip().startswith("#"):
            break
        block.append(ln)
    reason = "\n".join(block)
    assert "CLOSE_LEASE_S" in reason
    assert "_fixup_bound" in reason or "ATTEMPTS" in reason


def test_each_pass_is_logged_with_its_exit() -> None:
    code = _script_code()
    stripped = [ln.strip() for ln in code]
    assert '$log = Join-Path $Deploy "$Tenant\\factory\\watch-task.log"' in stripped

    runs = _lines_with(code, "watch --once")
    assert len(runs) == 1
    assert "2>&1" in runs[0], "stderr is part of the pass's output"
    assert "| Add-Content -Path $log" in runs[0], "the verb's output is appended to the log"

    on_log = _lines_with(code, "$log")
    assert not [ln for ln in on_log if "Set-Content" in ln], "a pass would overwrite the log"
    assert not [ln for ln in on_log if "Out-File" in ln and "-Append" not in ln]
    assert not [ln for ln in on_log if re.search(r">(?!>)", ln.replace("2>&1", ""))], "a redirect would overwrite"

    assert "$code = $LASTEXITCODE" in stripped
    exits = [ln for ln in code if "Add-Content" in ln and "EXIT $code" in ln]
    assert len(exits) == 1
    assert "-Path $log" in exits[0]
    assert stripped.index("exit $code") > stripped.index(exits[0].strip()), "the exit follows the EXIT line"

    unregisters = _lines_with(code, "Unregister-ScheduledTask")
    assert len(unregisters) == 1
    assert "-TaskName $TaskName" in unregisters[0], "-Remove unregisters the task the script registered"


def test_the_readme_names_install_check_remove() -> None:
    text = README.read_text(encoding="utf-8")
    starts = [m.start() for m in re.finditer(re.escape(SECTION), text)]
    assert len(starts) == 1, "the README has one section for the watcher's timer"
    rest = text[starts[0] + len(SECTION) :]
    end = rest.find("\n## ")
    section = rest if end == -1 else rest[:end]

    assert "watch-task.ps1 -Tenant" in section, "install"
    assert "Get-ScheduledTaskInfo" in section and "watch-task.log" in section, "check"
    assert "-Remove" in section, "remove"
    assert "owner" in section and "2026-10-04" in section, "the cadence is the owner's ruling"
