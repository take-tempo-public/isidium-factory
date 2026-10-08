```toml
schema = 1
id = 45
kind = "story"
status = "draft"
source = "session"
title = "The PR watcher dispatches the next ready card when nothing is in flight, and starts its run as a separate one-shot task"
shape = "bdd"
depends_on = [42, 44, 41]
effort = "default"
refs = ["packages/isidium-factory/src/isidium/factory/watch.py", "packages/isidium-factory/src/isidium/factory/cli.py", "packages/isidium-factory/src/isidium/factory/dispatch.py", "packages/isidium-factory/src/isidium/factory/tenant.py", "deploy/watch-task.ps1", "deploy/README.md"]
surfaces = ["packages/isidium-factory/src/isidium/factory/watch.py", "packages/isidium-factory/src/isidium/factory/cli.py", "packages/isidium-factory/src/isidium/factory/tenant.py", "deploy/run-task.ps1", "deploy/README.md", "tests/factory/test_watch_dispatches.py", "tests/factory/test_watch.py", "tools/mutations/watch-dispatch.toml"]
priority = "P1"

[narrative]
feature = "a signed card goes to build without anyone dispatching or launching it"

[[rules]]
id = "R1"
text = "a pass whose tenant has [watcher].dispatch on, with nothing in flight (Ledger.in_flight empty, the WIP the registration declares), fewer runs dispatched since the day's start (UTC) than dispatch_per_day, and a non-empty store dispatch view, dispatches the top-ranked ready card through dispatch.pick"

[[rules]]
id = "R2"
text = "it then starts the run through the launcher the tenant registration names ([watcher].launcher in tenant.toml), handing it the run id; the launcher is a host script, and the factory's code names no scheduler"

[[rules]]
id = "R3"
text = "deploy/run-task.ps1 is that launcher on Windows: it registers a one-shot scheduled task isidium-run-<tenant>-<run-id>, headless (conhost --headless), with its own execution limit, that runs `isidium-factory run --run <run-id>` and appends to runs/<run-id>-host.log with an EXIT line, then removes itself"

[[rules]]
id = "R4"
text = "a run that is in flight with no phases and no running launcher task for longer than the launch bound is flagged launch-lost once; the watcher never dispatches past it"

[[rules]]
id = "R5"
text = "past the daily cap, or with dispatch off, a ready card is left alone and the pass says so in its summary"

[[guidance.avoid]]
id = "A1"
option = "running the chain inside the watcher's pass, or as a detached child process of it"
because = "the owner, 2026-10-07 (smoothing the line, chunk plan): 'Separate run task'; a pass stays short, and a child's survival under Task Scheduler is unverified"

[[guidance.avoid]]
id = "A2"
option = "a new lease action or a ledger table rebuild for launches"
because = "WIP 1 already forbids a second dispatch; the run's ledger row is the record, and the leases table's CHECK constraint would need a rebuild"

[[guidance.avoid]]
id = "A3"
option = "dispatching a card whose depends_on are not closed"
because = "the store's ready view already excludes it (status._guards, blocked_by); the watcher only reads that view"

[[guidance.constraints]]
id = "C1"
text = "the daily count is every run dispatched since the day's start, operator or watcher, read from the ledger's runs.dispatched_at; the reason is written at the site"
because = "the ledger records no invoker on a run; counting all of them is conservative"

[[guidance.constraints]]
id = "C2"
text = "the dispatch decision is a pure function beside decide (decide's own signature is pinned at test_watch.py:632); context.load and the forge are reached only when a dispatch will happen, so an idle pass with dispatch on stays a ledger read plus the store's dispatch view"
because = "card 37 (C-13)"

[[guidance.constraints]]
id = "C3"
text = "tools/mutations/watch-dispatch.toml commits a mutation for R1 (a dispatch past the cap) and one for R1's WIP condition; each kill is checked against this card's own test file only; tools/mutate.py is --show only"
because = "the card-writing checklist"

[[guidance.constraints]]
id = "C4"
text = "refusals use the run. and dispatch. namespaces; no new namespace"
because = "core/disclosure.py stays untouched"

[[guidance.constraints]]
id = "C5"
text = "the launcher script parses (a pwsh parser test, skipped with a reason when pwsh is absent) and its scheduled-task arguments are pinned as text; no test registers a task"
because = "cards 30, 36, 38"

[[guidance.constraints]]
id = "C9"
text = "every file this card changes passes ruff check, ruff format --check and mypy --strict, by path"
because = "r-38 and r-39 each lost a whole run to a one-line style miss"

[[acceptance.scenarios]]
id = "S1"
kind = "test-marker"
title = "a free line with dispatch on dispatches the top ready card and starts its launcher"
rule = "R1"
observable = { test = "tests/factory/test_watch_dispatches.py::test_a_free_line_dispatches_and_launches" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "the launcher is the registration's, and the code names no scheduler"
rule = "R2"
observable = { test = "tests/factory/test_watch_dispatches.py::test_the_launcher_is_the_registrations" }

[[acceptance.scenarios]]
id = "S3"
kind = "test-marker"
title = "the run task script registers a one-shot headless task"
rule = "R3"
observable = { test = "tests/factory/test_watch_dispatches.py::test_the_run_task_is_one_shot_and_headless" }

[[acceptance.scenarios]]
id = "S4"
kind = "test-marker"
title = "a lost launch is flagged and blocks further dispatch"
rule = "R4"
observable = { test = "tests/factory/test_watch_dispatches.py::test_a_lost_launch_is_flagged" }

[[acceptance.scenarios]]
id = "S5"
kind = "test-marker"
title = "past the cap or with dispatch off nothing is dispatched"
rule = "R5"
observable = { test = "tests/factory/test_watch_dispatches.py::test_past_the_cap_nothing_is_dispatched" }
```

## Scope

Ruled [owner, 2026-10-07]: 'Dependencies + dispatcher'; start the run as a 'Separate run task'; 'Signed opt-in + daily cap'. Dependencies need no code: card@1's depends_on already keeps a card out of the ready view until its prerequisites are terminal.

Not in scope: ship at gate-pass (the owner is weighing it) and auto-merge (held).

## History

```toml
history = [
  { seq = 1, at = "2026-10-08T01:38:33Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "depends_on", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:ed545caf5899f26633c7cfeceeef0795b13533c53b9c73f8f0aa2b8ef7803173", h = "sha256:f6bcb29475ca76fc697baab2ed15414347c15ffcd8aa97e68e50050d92f198cc" },
]
```
