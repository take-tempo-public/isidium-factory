```toml
schema = 1
id = 69
kind = "story"
status = "draft"
source = "session"
title = "The watcher timer, a run's transient unit and the store's quadlet are product files the tenant installs, replacing the PowerShell scripts"
shape = "bdd"
effort = "default"
refs = ["deploy/watch-task.ps1", "deploy/compose.yaml", "deploy/README.md", "packages/isidium-factory/src/isidium/factory/watch.py"]
surfaces = ["deploy/systemd/isidium-watch@.service", "deploy/systemd/isidium-watch@.timer", "deploy/systemd/isidium-store.container", "deploy/README.md", "tests/factory/test_systemd_units.py"]
priority = "P1"

[narrative]
feature = "the Linux host's schedule and restart behaviour ships from the repository"

[[rules]]
id = "R1"
text = "deploy/systemd/ holds the watcher service and timer (15 minutes, one pass, no overlap) as the units running on the owner's host today, parameterised by tenant"

[[rules]]
id = "R2"
text = "deploy/systemd/ holds a quadlet unit that starts the store at boot and restarts it on failure"

[[rules]]
id = "R3"
text = "deploy/watch-task.ps1 and the other PowerShell launch scripts are removed, and the README documents `systemd-run --user` for a run"

[[rules]]
id = "R4"
text = "`systemd-analyze verify` passes on every shipped unit"

[[guidance.constraints]]
id = "C9"
text = "every file the card changes passes ruff check, ruff format --check and mypy --strict, by path"
because = "r-38 and r-39 each lost a whole run to a one-line style miss"

[[guidance.constraints]]
id = "C8"
text = "no scenario passes by skipping"
because = "card 61's rule"

[[acceptance.scenarios]]
id = "S1"
kind = "test-marker"
title = "the timer's interval and no-overlap are pinned"
rule = "R1"
observable = { test = "tests/factory/test_systemd_units.py::test_the_watcher_timer_is_fifteen_minutes_one_pass" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "the store quadlet restarts on failure and starts at boot"
rule = "R2"
observable = { test = "tests/factory/test_systemd_units.py::test_the_store_quadlet_starts_at_boot" }

[[acceptance.scenarios]]
id = "S3"
kind = "test-marker"
title = "no PowerShell script remains under deploy/"
rule = "R3"
observable = { test = "tests/factory/test_systemd_units.py::test_no_powershell_remains" }

[[acceptance.scenarios]]
id = "S4"
kind = "test-marker"
title = "every shipped unit verifies"
rule = "R4"
observable = { test = "tests/factory/test_systemd_units.py::test_every_unit_verifies" }
```

## Scope

H5. The units already run on the owner's WSL host (isidium-watch@isidium-factory.timer; container-isidium-store-isidium-factory.service), written by hand during the move. WSL's idle shutdown with every terminal closed is still unmeasured (open (ii)); this card must not claim it.

## History

```toml
history = [
  { seq = 1, at = "2026-10-29T21:06:44Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:a55fc7fed1284b9f88073d4840acb82bb13734e43dc844281c90e7d6d5a29ce9", h = "sha256:5228f8c2db510c3b8860321ab6562a0fe8d4a36221c188b168837f90fb7e9749" },
]
```
