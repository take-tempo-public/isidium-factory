```toml
schema = 1
id = 41
kind = "story"
status = "draft"
source = "session"
title = "The watcher task's health is read from its own log: a -Status switch reports the last pass's exit, since the headless launch hides it"
shape = "bdd"
effort = "default"
refs = ["deploy/watch-task.ps1", "deploy/README.md", "tests/unit/test_watch_timer.py"]
surfaces = ["deploy/watch-task.ps1", "deploy/README.md", "tests/unit/test_watch_timer.py"]
priority = "P2"

[narrative]
feature = "an operator can tell at a glance whether the watcher's last pass failed, without trusting Task Scheduler's result"

[[rules]]
id = "R1"
text = "`watch-task.ps1 -Tenant <t> -Status` reads watch-task.log and prints the last pass's START time, its EXIT code and time, and the next run time; it exits with that pass's code, or 1 when the last START has no EXIT (a pass the limit ended or whose host went down) or there is no pass yet"

[[rules]]
id = "R2"
text = "the README's Check section says LastTaskResult is conhost.exe's code and is 0 whatever the pass did, and names -Status (and the log's EXIT line) as the pass's result"

[[guidance.avoid]]
id = "A1"
option = "dropping the headless launch, or running the task whether the user is logged on or not"
because = "the owner asked for no window (card 38); a non-interactive logon is its own change with podman and profile risks"

[[guidance.constraints]]
id = "C1"
text = "the script still parses (the pwsh parser test), and every existing argument pin still holds"
because = "cards 36 and 38"

[[guidance.constraints]]
id = "C2"
text = "the test drives -Status against log fixtures written to a temporary directory, never a registered task"
because = "CI runs on Linux; card 30's C2"

[[acceptance.scenarios]]
id = "S1"
kind = "test-marker"
title = "status reports the last pass and exits with its code"
rule = "R1"
observable = { test = "tests/unit/test_watch_timer.py::test_status_reports_the_last_pass_and_its_code" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "a start with no exit is reported as a failed pass"
rule = "R1"
observable = { test = "tests/unit/test_watch_timer.py::test_status_flags_a_start_with_no_exit" }

[[acceptance.scenarios]]
id = "S3"
kind = "test-marker"
title = "the README names status, not LastTaskResult"
rule = "R2"
observable = { test = "tests/unit/test_watch_timer.py::test_the_readme_names_status_not_last_task_result" }
```

## Scope

Found by r-53's review (card 38) and verified by hand 2026-10-07: `conhost.exe --headless powershell -Command 'exit 3'` exits 0, so with the headless launch Task Scheduler's LastTaskResult always reads success. The log's EXIT lines, written by the pass script, stay true. Owner: 'draft the card for 2nd'.

## History

```toml
history = [
  { seq = 1, at = "2026-10-08T00:28:26Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:c4cc4ce53531584422fc702589cafd9735bd4af5d3d898d67b73ebf839f40ce6", h = "sha256:b94b41f9e6cd47e39c48fb3a8533fcf511ee4dfcd54f12cb9b7920dd74f449dc" },
]
```
