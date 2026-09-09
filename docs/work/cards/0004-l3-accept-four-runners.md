```toml
schema = 1
id = 4
kind = "story"
status = "ratified"
source = "planner"
title = "L3: accept compiles the acceptance block and runs it through four runners at the owner's terminal"
shape = "bdd"
effort = "default"
refs = ["packages/isidium-store/src/isidium/store/client/accept.py", "docs/design/03-card-schema.md"]
surfaces = ["packages/isidium-store/src/isidium/store/core/manifest.py", "packages/isidium-store/src/isidium/store/client/runners.py", "packages/isidium-store/src/isidium/store/client/accept.py", "tests/store/test_l3.py"]
priority = "P1"

[narrative]
feature = "accept compiles the card's acceptance block to the manifest and runs it in the checkout, writing nothing inside the tracking root; --close is the one write"

[[rules]]
id = "R1"
text = "The manifest is a deterministic function of the card and the config; every scenario compiles to a runnable check or is manual, never silently unrunnable"

[[rules]]
id = "R2"
text = "A runner answers pass or fail with its reason; what it cannot do is a refusal, never a fail"

[[acceptance.scenarios]]
id = "S1"
kind = "test-marker"
title = "the compile is deterministic and its hash reads the params"
rule = "R1"
observable = { test = "tests/store/test_l3.py::test_the_compile_is_deterministic_and_its_hash_reads_the_params" }
tests = ["tests/store/test_l3.py::test_the_compile_binds_every_kind_and_names_the_manual_ones", "tests/store/test_l3.py::test_an_unbindable_scenario_is_a_typed_compile_error_naming_it"]

[[acceptance.scenarios]]
id = "S2"
kind = "command"
title = "the verb is on the client and says what it does"
rule = "R2"
action = { run = ["python", "-m", "isidium.store.client.cli", "accept", "--help"] }
observable = { exit_code = 0, stdout_matches = "--unsafe-draft" }

[[acceptance.scenarios]]
id = "S3"
kind = "file-assert"
title = "a runner that cannot run is a refusal, never a fail"
rule = "R2"
observable = { path = "packages/isidium-store/src/isidium/store/client/runners.py", contains = "accept.runner-error" }

[[acceptance.scenarios]]
id = "S4"
kind = "test-marker"
title = "each runner answers pass and fail on a real checkout"
rule = "R2"
observable = { test = "tests/store/test_l3.py::test_a_runner_that_cannot_run_is_an_error_not_a_verdict" }
tests = ["tests/store/test_l3.py::test_each_runner_answers_pass_and_fail_on_a_real_checkout"]
```

## Scope

The verb `accept <id> [--close] [--unsafe-draft] [--deviated <why>]` on the store's client; `core/manifest.py` (the compile, shared with the factory's run and verification when v1c opens); `client/runners.py` (pytest, shell, http, file); `client/accept.py`. Not in scope: the factory-side verification of a human closure (T-A12, v1c); `constraint.check` and `manual_attestation`'s interrupt (first dispatch). This card is WP5's L3 as a card on tenant #0 — the first time the factory's own work is one (Q-W4, ruled 2026-09-09).

## History

```toml
history = [
  { seq = 1, at = "2026-09-09T20:03:26Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "effort", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:f44629d9435c4000f728f39c5d9a6d66adb869b7e0ff70a60bfbbbf4c5c1bcb6", h = "sha256:fcc2fb5e707b4d66cf5e2fc2b39f245c517793d0416a729fc2c2a2bb5adc1889" },
  { seq = 2, at = "2026-09-09T21:27:52Z", by = "amodal1@users.noreply.github.com", act = "ratified", fields = ["status"], build = "sha256:f44629d9435c4000f728f39c5d9a6d66adb869b7e0ff70a60bfbbbf4c5c1bcb6", h = "sha256:e1f678e328dda5781909a69e5b7b4a0e7283196879668103b1fa3114d7aa7942", batch = 4 },
]
```
