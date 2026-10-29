```toml
schema = 1
id = 67
kind = "story"
status = "draft"
source = "session"
title = "The container runtime is a registration setting with a start-up git-version check, and the phase's identity mapping follows it"
shape = "bdd"
effort = "default"
refs = ["packages/isidium-factory/src/isidium/factory/container.py::Container", "packages/isidium-factory/src/isidium/factory/tenant.py", "packages/isidium-factory/src/isidium/factory/registration.py"]
surfaces = ["packages/isidium-factory/src/isidium/factory/container.py", "packages/isidium-factory/src/isidium/factory/tenant.py", "tests/factory/test_runtime_setting.py"]
priority = "P1"

[narrative]
feature = "podman or Docker is chosen by the tenant's registration, and a host with too old a git is refused at start-up"

[[rules]]
id = "R1"
text = "the tenant registration's [runner] table may name the runtime binary (`podman` or `docker`, default `podman`); container.py reads it and no longer holds the binary as a constant"

[[rules]]
id = "R2"
text = "the phase's identity mapping is chosen by the setting's value (podman: --userns keep-id; docker: --user host uid:gid), not by the binary's file name as PR #119 did"

[[rules]]
id = "R3"
text = "at start-up the factory runs `git --version` and refuses with a named rule when it is below 2.47, the floor measured on 2026-10-28 (2.43 fails 20 store tests)"

[[guidance.constraints]]
id = "C1"
text = "the start-up git check runs once per process, not per phase"
because = "one spawn per run, not per call"

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
title = "a registration naming docker spawns with docker and --user"
rule = "R1"
observable = { test = "tests/factory/test_runtime_setting.py::test_the_registration_names_the_runtime" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "an unknown runtime value is refused with a named rule"
rule = "R2"
observable = { test = "tests/factory/test_runtime_setting.py::test_an_unknown_runtime_is_refused" }

[[acceptance.scenarios]]
id = "S3"
kind = "test-marker"
title = "git 2.43 is refused and 2.47 passes"
rule = "R3"
observable = { test = "tests/factory/test_runtime_setting.py::test_the_git_floor_is_enforced_at_startup" }
```

## Scope

H2 of the Linux host design (approved 2026-10-28). PR #119 chose the identity mapping by the binary's name as a stopgap; this card replaces that with the setting. The git floor is 2.47 (measured 2.43 failing); the exact boundary between 2.43 and 2.47 is unmeasured.

## History

```toml
history = [
  { seq = 1, at = "2026-10-29T21:06:41Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:ed4e25a9c645d3d57f171fc36478848e8290abab5e87868756a0f82eb3982627", h = "sha256:1b2b147fa521747f44822683834f5e464898f99076cb044e314796ea236493a6" },
]
```
