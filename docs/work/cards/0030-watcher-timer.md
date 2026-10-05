```toml
schema = 1
id = 30
kind = "story"
status = "draft"
source = "session"
title = "The PR watcher runs every 15 minutes from a host scheduled task, one pass at a time, logged"
shape = "bdd"
effort = "default"
refs = ["deploy/README.md", "deploy/build-runner.sh"]
surfaces = ["deploy/watch-task.ps1", "deploy/README.md", "tests/unit/test_watch_timer.py"]
priority = "P2"

[narrative]
feature = "the watcher runs without a session open and without a long-lived process the memory guard can reap"

[[rules]]
id = "R1"
text = "deploy/watch-task.ps1 registers (or replaces) one Windows scheduled task per tenant that runs `isidium-factory watch --once --tenant T --checkout C` every 15 minutes, with ISIDIUM_DEPLOY and PYTHONIOENCODING set as the run launch scripts set them"

[[rules]]
id = "R2"
text = "the task never starts a second instance while one runs (MultipleInstances IgnoreNew) and has an execution limit, so a hung pass ends"

[[rules]]
id = "R3"
text = "each pass appends its output and an EXIT line to a log at the deploy home; `-Remove` unregisters the task"

[[rules]]
id = "R4"
text = "deploy/README.md says how to install, check and remove it, and that the cadence is the owner's ruling"

[[guidance.avoid]]
id = "A1"
option = "a container or a service supervisor"
because = "the owner, 2026-10-04 (the watcher design, chunk plan: 'The PR watcher'): 'Host timer, one pass' first; the store's restart policy is no and the VPN breaks WSL DNS"

[[guidance.constraints]]
id = "C1"
text = "the execution limit is named in the script with its reason: longer than a close's lease (card 28's CLOSE_LEASE_S) plus a fixup's bound"
because = "a pass that outlives its leases would act without them"

[[guidance.constraints]]
id = "C2"
text = "the test reads the script as text and pins the cadence, the instance policy, the limit and the verb; it does not register a task"
because = "CI runs on Linux; a test may not touch the host's scheduler"

[[guidance.constraints]]
id = "C3"
text = "needs card 31 merged first"
because = "it runs watch --once"

[[guidance.constraints]]
id = "C9"
text = "every file this card changes passes ruff check, ruff format --check and mypy --strict, by path"
because = "r-38 and r-39 each lost a whole run to a one-line style miss"

[[acceptance.scenarios]]
id = "S1"
kind = "test-marker"
title = "the task runs one watch pass every 15 minutes"
rule = "R1"
observable = { test = "tests/unit/test_watch_timer.py::test_the_task_runs_one_pass_every_15_minutes" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "a second instance is never started and a hung pass is ended"
rule = "R2"
observable = { test = "tests/unit/test_watch_timer.py::test_no_second_instance_and_a_limit" }

[[acceptance.scenarios]]
id = "S3"
kind = "test-marker"
title = "each pass appends to the log with its exit"
rule = "R3"
observable = { test = "tests/unit/test_watch_timer.py::test_each_pass_is_logged_with_its_exit" }

[[acceptance.scenarios]]
id = "S4"
kind = "test-marker"
title = "the README says how to install, check and remove it"
rule = "R4"
observable = { test = "tests/unit/test_watch_timer.py::test_the_readme_names_install_check_remove" }
```

## Scope

Ruled 2026-10-04 [owner]: 'Host timer, one pass', 'Every 15 minutes'. Polling first, webhooks later (the homelab may need an endpoint the forge can reach).

Not in scope: installing it on tenant #0 (the owner's, after the merge); webhooks.

## History

```toml
history = [
  { seq = 1, at = "2026-10-05T14:21:42Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:e15fc04e7c64f84a2778c9958317e4d4941a878bbe7e5a59ee5af9828ab5abcb", h = "sha256:566b7554c937f90111bb3cdd95547f768a70e22090b34273e799e48e581e4ec3" },
  { seq = 2, at = "2026-10-05T14:24:53Z", by = "amodal1@users.noreply.github.com", act = "amended", fields = ["guidance"], build = "sha256:df78ed749f1071324a6dfd9638d02f82ff51e955ec09b3a4038c4076f3b8f5e4", h = "sha256:b7dbcb74ac753bd48c4d8dab63dd0408b9832faad84556d3fa503f4563823c3e" },
]
```
