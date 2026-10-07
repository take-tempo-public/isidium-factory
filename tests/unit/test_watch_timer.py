"""The PR watcher's timer (card 30): `deploy/watch-task.ps1` and the README section that describes it.

CI runs on Linux and a test may not touch the host's scheduler, so every test here reads the script as text and pins what
it says. A pin is matched against the script's **code** -- `<# #>` blocks and full-line `#` comments removed -- so a
comment that still names a behaviour cannot hold up a test for code that no longer does it. The one thing read from
comments is the reason the execution limit carries beside it (card 30, C1)."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from isidium.factory import cli, container, registration
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
UNBRACED_COLON = re.compile(r"\$[A-Za-z_]\w*:(?![\w{:])")
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
    # PowerShell parses the whole file before it runs a line, and `"$name: ..."` is a parse error (the colon reads as a
    # scope qualifier), which no text pin on behaviour can see. Text cannot prove the file parses, but it can refuse
    # this one shape, which is the one this script met.
    assert not [ln for ln in code if UNBRACED_COLON.search(ln)], "a variable followed by a colon needs ${braces}"

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
    assert "wall_clock_s" in reason
    assert "ATTEMPTS" in reason
    assert re.search(r"(each|every) tenant", reason), "the one limit is said to cover each tenant's own bound"


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


def _watch_section() -> str:
    """The README's one section for the watcher's timer, up to the next `## ` heading."""
    text = README.read_text(encoding="utf-8")
    starts = [m.start() for m in re.finditer(re.escape(SECTION), text)]
    assert len(starts) == 1, "the README has one section for the watcher's timer"
    rest = text[starts[0] + len(SECTION) :]
    end = rest.find("\n## ")
    return rest if end == -1 else rest[:end]


def test_the_readme_names_install_check_remove() -> None:
    section = _watch_section()

    assert "watch-task.ps1 -Tenant" in section, "install"
    assert "Get-ScheduledTaskInfo" in section and "watch-task.log" in section, "check"
    assert "-Remove" in section, "remove"
    assert "owner" in section and "2026-10-04" in section, "the cadence is the owner's ruling"


def _stripped(code: list[str]) -> list[str]:
    return [ln.strip() for ln in code]


def _index_of(code: list[str], prefix: str) -> int:
    """The index of the one code line that starts with `prefix`."""
    found = [i for i, ln in enumerate(_stripped(code)) if ln.startswith(prefix)]
    assert len(found) == 1, f"{prefix!r}: expected one code line, found {len(found)}"
    return found[0]


def test_the_task_runs_on_battery() -> None:
    code = _script_code()
    settings = _lines_with(code, "New-ScheduledTaskSettingsSet")
    assert len(settings) == 1
    assert "-AllowStartIfOnBatteries" in settings[0]
    assert "-DontStopIfGoingOnBatteries" in settings[0]
    assert not _lines_with(code, "-DisallowStartIfOnBatteries")
    assert not [ln for ln in code if re.search(r"(?<!Dont)StopIfGoingOnBatteries", ln)]


def test_paths_are_absolute_and_must_exist() -> None:
    code = _script_code()
    stripped = _stripped(code)
    registers = _index_of(code, "Register-ScheduledTask")
    action = _index_of(code, "$action = New-ScheduledTaskAction")

    # Each parameter is checked, then resolved; a refusal is a throw, and it comes before anything is built or registered.
    for param, resolved in (("Checkout", "checkoutPath"), ("Deploy", "deployPath")):
        check = _index_of(code, f"if (-not (Test-Path -LiteralPath ${param} -PathType Container))")
        assert stripped[check + 1].startswith("throw "), f"-{param} missing refuses with a message"
        assert stripped[check + 2] == "}"
        resolve = _index_of(code, f"${resolved} = (Resolve-Path -LiteralPath ${param}).ProviderPath")
        assert check < resolve < action < registers
    exe_check = _index_of(code, "if (-not (Test-Path -LiteralPath $found.Source -PathType Leaf))")
    assert stripped[exe_check + 1].startswith("throw ")
    exe_resolve = _index_of(code, "$exePath = (Resolve-Path -LiteralPath $found.Source).ProviderPath")
    assert exe_check < exe_resolve < action < registers

    assert "-WorkingDirectory $checkoutPath" in stripped[action]
    arg_line = code[_index_of(code, "$argLine =")]
    assert not re.search(r"\$(Checkout|Deploy)\b", arg_line.split(" -f ", 1)[1]), "the raw parameters are not passed on"


def test_a_failed_registration_prints_no_success() -> None:
    code = _script_code()
    stripped = _stripped(code)
    for verb in ("Register-ScheduledTask", "Unregister-ScheduledTask"):
        calls = _lines_with(code, verb)
        assert len(calls) == 1
        assert "-ErrorAction Stop" in calls[0], f"{verb} stops on an error"
    assert "-ErrorAction Stop" in _lines_with(code, "Get-ScheduledTask")[0], (
        "-Remove's probe does not hide a scheduler error"
    )

    # A script-wide preference covers what -ErrorAction does not; it sits after the pass, which keeps its own 'Continue'.
    pref = [i for i, ln in enumerate(stripped) if ln == "$ErrorActionPreference = 'Stop'"]
    assert len(pref) == 1
    assert stripped.index("exit $code") < pref[0] < stripped.index("if ($Remove) {")
    assert not [ln for ln in code if "SilentlyContinue" in ln and "Scheduled" in ln]
    assert not [ln for ln in code if re.match(r"\s*(try|catch)\b", ln, re.IGNORECASE)], "nothing swallows the error"

    # The success line is the very next statement after the call, so nothing runs between a failure and the abort.
    register = _index_of(code, "Register-ScheduledTask")
    assert stripped[register + 1].startswith('Write-Output "registered ')
    unregister = _index_of(code, "Unregister-ScheduledTask")
    assert stripped[unregister + 1].startswith('Write-Output "removed ')


def test_the_tenant_is_case_sensitive() -> None:
    code = _script_code()
    attrs = _lines_with(code, "ValidatePattern")
    assert len(attrs) == 1
    attr = attrs[0]
    assert re.search(r"Options\s*=\s*'None'", attr), "ValidatePattern is IgnoreCase unless Options says otherwise"
    assert "IgnoreCase" not in attr
    quoted = re.search(r"\('((?:[^']|'')*)'", attr)
    assert quoted
    grammar = re.compile(quoted.group(1))  # no flags: PowerShell's default is the only thing that ignores case
    for name in (
        "isidium-factory",
        "sartor",
        "a",
        "ISIDIUM-FACTORY",
        "Sartor",
        "-a",
        "a-",
        "",
        "a" * 63,
        "a" * 64,
        "a..b",
    ):
        assert bool(grammar.match(name)) == bool(registration.TENANT.match(name)), name


def _action_template(code: list[str]) -> tuple[str, list[str]]:
    """The action's argument template and the variables it is formatted with, from the one `$argLine =` code line."""
    lines = _lines_with(code, "$argLine =")
    assert len(lines) == 1
    parsed = re.fullmatch(r"\s*\$argLine = '(?P<template>.*)' -f (?P<args>.*?)\s*", lines[0])
    assert parsed, "one template, formatted with a list of variables"
    return parsed["template"], [a.strip() for a in parsed["args"].split(",")]


def test_the_actions_arguments_are_pinned() -> None:
    code = _script_code()
    template, args = _action_template(code)
    assert template.startswith("--headless powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass ")
    assert re.search(r"\s-Pass\s+-Tenant\b", template), "the pass switch is bare and precedes the tenant"
    assert sorted(int(n) for n in re.findall(r"\{(\d+)\}", template)) == list(range(len(args)))

    def bound(flag: str) -> str:
        m = re.search(rf'\s{flag}\s+"\{{(\d+)\}}"', template)
        assert m, flag
        return args[int(m.group(1))]

    assert bound("-File") == "$scriptPath"
    assert bound("-Tenant") == "$Tenant"
    assert bound("-Checkout") == "$checkoutPath"
    assert bound("-Deploy") == "$deployPath"
    assert bound("-Exe") == "$exePath"

    actions = _lines_with(code, "New-ScheduledTaskAction")
    assert len(actions) == 1
    assert "-Execute 'conhost.exe'" in actions[0]
    assert "-Argument $argLine" in actions[0]


def test_the_pass_runs_in_a_headless_console() -> None:
    code = _script_code()
    actions = _lines_with(code, "New-ScheduledTaskAction")
    assert len(actions) == 1
    assert "-Execute 'conhost.exe'" in actions[0]
    assert "-Argument $argLine" in actions[0]
    assert not _lines_with(code, "-Execute 'powershell.exe'"), "nothing launches powershell.exe directly"

    # --headless is conhost's first argument, and today's powershell invocation follows it unchanged.
    template, _args = _action_template(code)
    tokens = template.split()
    assert tokens[0] == "--headless"
    assert tokens[1] == "powershell.exe"
    assert " ".join(tokens[2:8]) == "-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden"
    assert tokens[8] == "-File"

    # The avoid list (A1, A2): no script launcher, and the logon stays Interactive with no stored password.
    assert not [ln for ln in code if re.search(r"(?i)wscript|cscript|\.vbs\b", ln)]
    principals = _lines_with(code, "New-ScheduledTaskPrincipal")
    assert len(principals) == 1
    assert "-LogonType Interactive" in principals[0]
    assert not [ln for ln in code if "S4U" in ln or "-Password" in ln]


def test_the_readme_says_the_pass_is_headless() -> None:
    section = _watch_section()
    starts = [m.start() for m in re.finditer(re.escape("**Install**"), section)]
    ends = [m.start() for m in re.finditer(re.escape("**Check:**"), section)]
    assert len(starts) == 1 and len(ends) == 1 and starts[0] < ends[0], "the install part sits before the check part"
    install = section[starts[0] : ends[0]]
    flat = " ".join(install.split())
    for needle in ("conhost.exe --headless", "-WindowStyle Hidden", "window", "focus"):
        assert needle in flat, f"the install part does not say {needle!r}"

    # The reason sits in the same paragraph as the mechanism it explains.
    paragraphs = [" ".join(p.split()) for p in re.split(r"\n\s*\n", install)]
    reasons = [p for p in paragraphs if "-WindowStyle Hidden" in p and "before" in p.lower()]
    assert reasons, "a paragraph says -WindowStyle Hidden applies only after powershell.exe has made its window"


_PARSE = (
    "$errors = $null; $tokens = $null; "
    "[System.Management.Automation.Language.Parser]::ParseFile($env:ISIDIUM_PS1, [ref]$tokens, [ref]$errors) | Out-Null; "
    "$errors | ForEach-Object { '{0}:{1} {2}' -f $_.Extent.StartLineNumber, $_.Extent.StartColumnNumber, $_.Message }; "
    "if ($errors.Count -gt 0) { exit 1 }"
)


def test_the_script_parses() -> None:
    pwsh = shutil.which("pwsh")
    if pwsh is None:
        pytest.skip("pwsh is not on PATH: the script cannot be parsed here; the text pins still run")
    # ParseFile reads and never runs the script, so no task is registered (card 36, A1). The path travels in the
    # environment rather than being spliced into the command.
    done = subprocess.run(
        [pwsh, "-NoProfile", "-NonInteractive", "-Command", _PARSE],
        env={**os.environ, "ISIDIUM_PS1": str(SCRIPT)},
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert done.returncode == 0, f"{SCRIPT.name} does not parse:\n{done.stdout}{done.stderr}"
