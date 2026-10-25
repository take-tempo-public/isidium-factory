```toml
schema = 1
id = 47
kind = "story"
status = "draft"
source = "session"
title = "The ledger records typed observations, and a launcher named in the registration starts an actor's one-shot task"
shape = "bdd"
depends_on = [41]
effort = "default"
refs = ["packages/isidium-factory/src/isidium/factory/ledger.py", "packages/isidium-factory/src/isidium/factory/tenant.py", "deploy/watch-task.ps1", "deploy/README.md"]
surfaces = ["packages/isidium-factory/src/isidium/factory/ledger.py", "packages/isidium-factory/src/isidium/factory/tenant.py", "packages/isidium-factory/src/isidium/factory/launcher.py", "deploy/run-task.ps1", "deploy/README.md", "tests/factory/test_observations_and_launcher.py", "tests/unit/test_run_task.py", "tests/factory/test_leases.py", "tests/factory/test_v5a.py"]
priority = "P1"

[narrative]
feature = "what the witness saw is on the record, and waking an actor is one call to a host script"

[[rules]]
id = "R1"
text = "the ledger gains an observations table: seq, at, kind (pr-red, pr-merged, pr-stale, pr-conflicted, line-free), run_id (null for line-free), pr, head, detail, consumed_at, consumed_by; rows are never deleted; an observation identical to the newest unconsumed one for the same (kind, run, head) is not written twice"

[[rules]]
id = "R2"
text = "the ledger answers the newest unconsumed observation for a run, and marks an observation consumed by an actor in one transaction"

[[rules]]
id = "R3"
text = "the leases table accepts the holder `run` (a resuming run) beside watcher and operator; the existing rows survive the rebuild"

[[rules]]
id = "R4"
text = "tenant.toml may declare `[launcher] command = <path>`; launcher.wake(registration, actor, arg) runs it with (actor, arg) and returns at once; with no launcher declared, wake refuses run.no-launcher and starts nothing"

[[rules]]
id = "R5"
text = "deploy/run-task.ps1 is that launcher on Windows: for (run, r-N), (resume, r-N) or (dispatch, -) it registers and starts a one-shot headless task (conhost --headless, as card 38) named isidium-<actor>-<tenant>[-<run>], with its own execution limit, that runs `isidium-factory run --run r-N`, `isidium-factory run --run r-N --resume` or `isidium-factory dispatch --next`, appends START/EXIT lines to its log, and unregisters itself when it ends; a task of that name already running is left alone"

[[guidance.avoid]]
id = "A1"
option = "naming any scheduler in the factory's Python"
because = "the launcher is the host's; the next host's is a systemd unit or a cron line, behind the same seam"

[[guidance.avoid]]
id = "A2"
option = "the witness interpreting an observation"
because = "the owner, 2026-10-23/25 (the actor design, chunk plan): the witness never interprets what to do; the actor reads its own state plus the observation"

[[guidance.constraints]]
id = "C1"
text = "the ledger's SCHEMA becomes 5; the leases CHECK change is a table rebuild in the migration (SQLite cannot alter a CHECK), rows copied; the two `== \"4\"` assertions (test_leases.py:307, test_v5a.py:448) and test_leases.py:95's `\"leases\" in _DDL[-1]` move with it"
because = "checked when filing"

[[guidance.constraints]]
id = "C2"
text = "Registration gains `launcher: str | None = None` last and tenant.toml's allowed keys gain `launcher`; positional constructions elsewhere keep working"
because = "checked when filing: tenant.py:86-92; Registration is built positionally in five test files"

[[guidance.constraints]]
id = "C3"
text = "run-task.ps1 has its own test file reading it as text (its arguments, headless launch, self-removal, log lines) and a pwsh parse test skipped with a reason when pwsh is absent; no test registers a task; the README gains its own section, not a second watcher heading"
because = "cards 30, 36, 38; test_watch_timer.py reads only watch-task.ps1"

[[guidance.constraints]]
id = "C4"
text = "refusals use the run. and ledger. namespaces"
because = "core/disclosure.py stays untouched"

[[guidance.constraints]]
id = "C9"
text = "every file this card changes passes ruff check, ruff format --check and mypy --strict, by path"
because = "r-38 and r-39 each lost a whole run to a one-line style miss"

[[acceptance.scenarios]]
id = "S1"
kind = "test-marker"
title = "an observation is written once and kept"
rule = "R1"
observable = { test = "tests/factory/test_observations_and_launcher.py::test_an_observation_is_written_once_and_kept" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "the newest unconsumed observation is answered and consumed"
rule = "R2"
observable = { test = "tests/factory/test_observations_and_launcher.py::test_the_newest_observation_is_answered_and_consumed" }

[[acceptance.scenarios]]
id = "S3"
kind = "test-marker"
title = "the leases table accepts a run holder after the rebuild"
rule = "R3"
observable = { test = "tests/factory/test_observations_and_launcher.py::test_leases_accept_a_run_holder_after_the_rebuild" }

[[acceptance.scenarios]]
id = "S4"
kind = "test-marker"
title = "wake runs the registered launcher, or refuses without one"
rule = "R4"
observable = { test = "tests/factory/test_observations_and_launcher.py::test_wake_runs_the_launcher_or_refuses" }

[[acceptance.scenarios]]
id = "S5"
kind = "test-marker"
title = "the run task is one-shot, headless and self-removing"
rule = "R5"
observable = { test = "tests/unit/test_run_task.py::test_the_run_task_is_one_shot_headless_and_self_removing" }
```

## Scope

Ruled [owner, 2026-10-23/25]: wake by 'Observation + run task' (the witness writes a typed observation to the ledger and starts the actor's one-shot task through the launcher); 'Separate run task' (2026-10-07). Surveyed: the leases CHECK allows only close|fixup and watcher|operator; Registration refuses unknown tenant.toml keys.

## History

```toml
history = [
  { seq = 1, at = "2026-10-25T21:44:25Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "depends_on", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:139c292e2d7fff6baccf10c9bfa2a43b096234a4e025ad1b2b25cf2cac5ad731", h = "sha256:2c82effaee1d2e6ae9e172622f1ea65516de49cb9a3dd2d6070bd345f231bcff" },
]
```
