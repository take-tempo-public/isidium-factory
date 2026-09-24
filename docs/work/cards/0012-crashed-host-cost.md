```toml
schema = 1
id = 12
kind = "story"
status = "ratified"
source = "session"
title = "A phase's result left on disk reaches the ledger when its run ends, so a crashed host's spend is recorded"
shape = "bdd"
effort = "default"
refs = ["packages/isidium-factory/src/isidium/factory/close.py::close", "packages/isidium-factory/src/isidium/factory/ledger.py::Ledger"]
surfaces = ["packages/isidium-factory/src/isidium/factory/close.py", "tests/factory/test_close_records_left_results.py"]
priority = "P2"

[narrative]
feature = "a run whose host died after its phase finished still has that phase's spend on the ledger once the run is closed, because close records the result the phase left behind"

[[rules]]
id = "R1"
text = "When close ends a run, every phase whose run directory holds a readable result.json and that the ledger has no row for is recorded as that phase's row first, with the model, effort, prompt version, tokens, cost and duration the result gives"

[[rules]]
id = "R2"
text = "When the run's row holds no billing class, the end takes the billing class of the results it recorded"

[[rules]]
id = "R3"
text = "A result.json that cannot be read or does not validate as a phase result is not recorded, the end's detail names its path, and the end itself still happens"

[[rules]]
id = "R4"
text = "A phase the ledger already holds a row for is never recorded a second time"

[[guidance.avoid]]
id = "A1"
option = "reconstructing a result from harness.json or the harness stream"
because = "result.json is the adapter's typed answer already; a second reading of the raw stream is a second home for the same fact"

[[guidance.constraints]]
id = "C1"
text = "a left-behind result is validated through adapter.result before it is recorded"
because = "the ledger's phase rows are the wire's own dump, and an unvalidated dict would let the two drift"

[[guidance.constraints]]
id = "C2"
text = "the run directory is found as the container adapter lays it out, <deploy home>/runs/<run>/<step>/result.json, and one directory listing per run is the whole cost"
because = "close runs on every run end; it must not walk the deploy home"

[[acceptance.scenarios]]
id = "S1"
kind = "test-marker"
title = "an abandoned run records the phase result its dead host left behind"
rule = "R1"
observable = { test = "tests/factory/test_close_records_left_results.py::test_an_abandoned_run_records_the_result_its_host_left" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "the end takes the recorded result's billing class"
rule = "R2"
observable = { test = "tests/factory/test_close_records_left_results.py::test_the_end_takes_the_recorded_results_billing_class" }

[[acceptance.scenarios]]
id = "S3"
kind = "test-marker"
title = "an unreadable result is named in the end's detail and the run still ends"
rule = "R3"
observable = { test = "tests/factory/test_close_records_left_results.py::test_an_unreadable_result_is_named_and_the_run_still_ends" }

[[acceptance.scenarios]]
id = "S4"
kind = "test-marker"
title = "a phase already on the ledger is not recorded twice"
rule = "R4"
observable = { test = "tests/factory/test_close_records_left_results.py::test_a_phase_already_recorded_is_not_recorded_twice" }
```

## Scope

Found on 2026-09-22 with run r-11. Its build finished inside the container (result.json: outcome ok, 23,312 tokens, 1,428,893 micro-dollars, 21 minutes, billing class plan), but the host process that would have recorded it was killed between the adapter returning and the ledger's phase row. The run was later ended abandoned by close, and the ledger still holds no phase row for it and a null billing class: the spend happened and the record says it did not.

The result is on disk, typed, and validated by the same model the ledger's rows are dumped from. Close is the one door every such run leaves by, so that is where it is picked up: before the end is written, a phase directory holding a result the ledger never recorded becomes that phase's row.

In scope: close recording left-behind phase results before it ends a run, on every end it writes (abandoned, failed, closed); the end taking their billing class when the row has none; and the tests.

Not in scope: r-11 itself, which has already ended and is not re-opened; an outcome class for a phase that succeeded while its host died (a store-side union change, its own card); handing a crashed run's work back to a new run; and the runner's own path, which records a result the moment the adapter returns.

## History

```toml
history = [
  { seq = 1, at = "2026-09-24T02:52:09Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:2dbaae7bb7122275382b740b77f4c766b1bbb399f4242f007117e676c60bf251", h = "sha256:a625a59f7b88193ad3be2b24e8f5c81047b14fa8da417290e6e3a31bea96d641" },
  { seq = 2, at = "2026-09-24T03:09:06Z", by = "amodal1@users.noreply.github.com", act = "ratified", fields = ["status"], build = "sha256:2dbaae7bb7122275382b740b77f4c766b1bbb399f4242f007117e676c60bf251", h = "sha256:28ccaea7740753f9787b6689cee7dfce0d2ec6593ae658411bfaae285ececa52", batch = 24 },
]
```
