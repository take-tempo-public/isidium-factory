```toml
schema = 1
id = 38
kind = "story"
status = "ratified"
source = "session"
title = "The watcher's scheduled task runs its pass in a headless console, so no window opens and nothing takes focus"
shape = "bdd"
effort = "default"
refs = ["deploy/watch-task.ps1", "deploy/README.md", "tests/unit/test_watch_timer.py"]
surfaces = ["deploy/watch-task.ps1", "deploy/README.md", "tests/unit/test_watch_timer.py"]
priority = "P2"

[narrative]
feature = "a pass every fifteen minutes is invisible to the person using the machine"

[[rules]]
id = "R1"
text = "the registered action's executable is conhost.exe with --headless as its first argument, followed by the same powershell.exe invocation as today (-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File <script> -Pass and its parameters)"

[[rules]]
id = "R2"
text = "the README's install section says the pass runs headless and why: powershell.exe creates its console window before -WindowStyle Hidden applies, so a direct launch flashes a window and takes focus"

[[guidance.avoid]]
id = "A1"
option = "running the task whether the user is logged on or not (S4U or a stored password)"
because = "the pass's close and fixup reach podman and the user's profile; a non-interactive logon is a separate change with its own risks, not this card"

[[guidance.avoid]]
id = "A2"
option = "a VBScript or wscript launcher"
because = "VBScript is deprecated on Windows 11; conhost --headless needs no extra file"

[[guidance.constraints]]
id = "C1"
text = "card 36's pinned argument test still pins the pass switch, the tenant, the deploy home and the executable, now inside the conhost arguments; the script still parses (the pwsh parser test)"
because = "card 36's R5 and C1"

[[guidance.constraints]]
id = "C2"
text = "every file this card changes passes ruff check, ruff format --check and mypy --strict, by path"
because = "r-38 and r-39 each lost a whole run to a one-line style miss"

[[acceptance.scenarios]]
id = "S1"
kind = "test-marker"
title = "the task launches its pass through a headless console"
rule = "R1"
observable = { test = "tests/unit/test_watch_timer.py::test_the_pass_runs_in_a_headless_console" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "the README says the pass runs headless and why"
rule = "R2"
observable = { test = "tests/unit/test_watch_timer.py::test_the_readme_says_the_pass_is_headless" }
```

## Scope

Owner, 2026-10-07: 'can you set that cron to NOT open a window and grab control of the screen when it runs?' The installed task was switched by hand to `conhost.exe --headless powershell.exe ...` and a triggered pass exited 0 (9 s); re-running watch-task.ps1 would revert it, so the script carries the change. Owner: 'yes draft it and sign it'.

## History

```toml
history = [
  { seq = 1, at = "2026-10-07T21:39:20Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:62fec378124aa925391c101c10fc4cf03bcbfcbd94c9d3556ad72e5176f23fd6", h = "sha256:409385a46eb719b088f5068ac720add4cf5521c08fa90bdefb0f58ff8671cf57" },
  { seq = 2, at = "2026-10-07T21:39:55Z", by = "amodal1@users.noreply.github.com", act = "ratified", fields = ["status"], build = "sha256:62fec378124aa925391c101c10fc4cf03bcbfcbd94c9d3556ad72e5176f23fd6", h = "sha256:4e9c114e09ad33841367e09758cba2cc3b55329155c6e4a749457eaa7e7a2aaa", batch = 69 },
]
```
