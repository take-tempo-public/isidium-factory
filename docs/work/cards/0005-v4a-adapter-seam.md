```toml
schema = 1
id = 5
kind = "story"
status = "ratified"
source = "planner"
title = "V4a: the execution adapter seam, and the container adapter on the workstation's podman"
shape = "bdd"
effort = "default"
refs = ["packages/isidium-factory/src/isidium/factory/dispatch.py", "packages/isidium-factory/src/isidium/factory/payload.py"]
surfaces = ["packages/isidium-factory/src/isidium/factory/adapter.py", "packages/isidium-factory/src/isidium/factory/container.py", "tests/factory/test_v4a.py"]
priority = "P1"

[narrative]
feature = "a dispatched run reaches an execution adapter through one typed seam, and the first adapter runs it in a container on the workstation's podman, so the ledger row that says `dispatched` can say what happened next"

[[rules]]
id = "R1"
text = "The adapter seam is a typed contract with no forge, store or podman word in it; an adapter is chosen by the tenant's registration and nothing else"

[[rules]]
id = "R2"
text = "A run's outcome is written to the ledger by the same transaction discipline dispatch used: no row, no run, and what happened after the row is on the row"

[[acceptance.scenarios]]
id = "S1"
kind = "test-marker"
title = "the seam is typed and names no executor"
rule = "R1"
observable = { test = "tests/factory/test_v4a.py::test_the_seam_names_no_executor" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "a run's outcome reaches the ledger row it was dispatched under"
rule = "R2"
observable = { test = "tests/factory/test_v4a.py::test_the_outcome_lands_on_the_dispatched_row" }

[[acceptance.scenarios]]
id = "S3"
kind = "command"
title = "the adapter is reachable as a verb and says what it does"
rule = "R1"
action = { run = ["python", "-m", "isidium.factory.cli", "run", "--help"] }
observable = { exit_code = 0, stdout_matches = "--run" }

[[acceptance.scenarios]]
id = "S4"
kind = "file-assert"
title = "the ledger carries the run's phases where V3 left them empty"
rule = "R2"
observable = { path = "packages/isidium-factory/src/isidium/factory/ledger.py", contains = "phases" }
```

## Scope

The execution adapter seam (T-C6 as typed values, the executor policy declared once) and the first adapter: a container on the workstation's podman, taking the run payload V1 assembles and the ledger row V3 writes, and answering with an outcome the ledger records. In scope: the seam, the container adapter, the run verb, the ledger's phases and verdicts rows filled for the first time. Not in scope: the action adapter on the public repo's runners (V4b, against the same seam); close, accept and the run report (V5); the rolling branch and the batch PR (V6). This card is v1c's V4a as a card on tenant #0, and the first card the factory dispatched a run record for (V3's live step, 2026-09-11).

## History

```toml
history = [
  { seq = 1, at = "2026-09-12T01:22:19Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "effort", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:56a898831185d547cb31b05dfcb0f0f783c5fcc88c193f104e981d373ff97238", h = "sha256:f938239c6d2d61b4d06c1ad737f02e0834e6ad64133f69f906ea8abdea0c81dc" },
  { seq = 2, at = "2026-09-12T01:23:52Z", by = "amodal1@users.noreply.github.com", act = "ratified", fields = ["status"], build = "sha256:56a898831185d547cb31b05dfcb0f0f783c5fcc88c193f104e981d373ff97238", h = "sha256:8b731eb30a19ffa02561c07a8caf33470c75ee868643e4c7c9befdc77f70f29c", batch = 7 },
]
```
