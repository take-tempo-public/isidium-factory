```toml
schema = 1
id = 36
kind = "story"
status = "draft"
source = "session"
title = "The watcher's scheduled task runs on battery, from absolute paths, and says so when registering fails"
shape = "bdd"
effort = "default"
refs = ["deploy/watch-task.ps1", "deploy/README.md", "tests/unit/test_watch_timer.py"]
surfaces = ["deploy/watch-task.ps1", "tests/unit/test_watch_timer.py", "deploy/README.md"]
priority = "P2"

[narrative]
feature = "a registered watcher task runs whenever the host is up, and a registration that failed is never reported as done"

[[rules]]
id = "R1"
text = "the task's settings allow starting on battery and do not stop a running pass when the host goes to battery"

[[rules]]
id = "R2"
text = "-Checkout, -Deploy and the executable are resolved to absolute paths and checked to exist before registering; a missing one refuses with a message and registers nothing; the action's working directory is the checkout"

[[rules]]
id = "R3"
text = "registering or removing the task stops on an error (ErrorAction Stop) and prints no success line after one"

[[rules]]
id = "R4"
text = "the tenant name is matched case-sensitively, as the registration's grammar is"

[[rules]]
id = "R5"
text = "the registered action's arguments are pinned: the pass switch, the tenant, the deploy home and the executable"

[[guidance.avoid]]
id = "A1"
option = "registering a task in any test"
because = "CI runs on Linux; the tests read the script as text (card 30's C2)"

[[guidance.constraints]]
id = "C1"
text = "the script still parses: a test parses it with PowerShell's own parser when pwsh is on the PATH, and is skipped with a reason when it is not"
because = "card 30's first build shipped a parse error its text tests could not see (r-49 review F1)"

[[guidance.constraints]]
id = "C2"
text = "the execution limit stays one value, and its comment names the per-tenant bound it must exceed (CLOSE_LEASE_S plus the tenant's wall_clock_s × ATTEMPTS)"
because = "r-49 review F4"

[[acceptance.scenarios]]
id = "S1"
kind = "test-marker"
title = "the task runs on battery"
rule = "R1"
observable = { test = "tests/unit/test_watch_timer.py::test_the_task_runs_on_battery" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "paths are absolute and must exist"
rule = "R2"
observable = { test = "tests/unit/test_watch_timer.py::test_paths_are_absolute_and_must_exist" }

[[acceptance.scenarios]]
id = "S3"
kind = "test-marker"
title = "a failed registration prints no success"
rule = "R3"
observable = { test = "tests/unit/test_watch_timer.py::test_a_failed_registration_prints_no_success" }

[[acceptance.scenarios]]
id = "S4"
kind = "test-marker"
title = "the tenant is matched case-sensitively"
rule = "R4"
observable = { test = "tests/unit/test_watch_timer.py::test_the_tenant_is_case_sensitive" }

[[acceptance.scenarios]]
id = "S5"
kind = "test-marker"
title = "the action's arguments are pinned"
rule = "R5"
observable = { test = "tests/unit/test_watch_timer.py::test_the_actions_arguments_are_pinned" }
```

## Scope

Found by r-49's review gate (card 30): F2 the battery defaults; F3 relative paths and no working directory; F4 one limit across tenants; F5 the action's arguments unpinned; F6 ValidatePattern case-insensitive; F7 errors continue to a success line. F1 (a parse error) was fixed in reconcile and the merged script was parse-checked by hand. The owner installs the task; this lands before that.

## History

```toml
history = [
  { seq = 1, at = "2026-10-07T13:44:03Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:a669c14b974d07d12cc87377f60a80868b391f94d1556eb25ebeab4887488a1f", h = "sha256:aad13227b1a94441e51faebde172a5f47fb34944e7d48339791e58a0288005ab" },
]
```
