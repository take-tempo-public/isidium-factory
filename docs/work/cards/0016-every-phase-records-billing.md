```toml
schema = 1
id = 16
kind = "story"
status = "draft"
source = "session"
title = "Every phase that ends records the billing class it drew on, so a parked or read-only run is not left unbilled"
shape = "bdd"
effort = "default"
refs = ["packages/isidium-factory/src/isidium/factory/runner.py::run_phase", "packages/isidium-factory/src/isidium/factory/ledger.py::Ledger"]
surfaces = ["packages/isidium-factory/src/isidium/factory/runner.py", "packages/isidium-factory/src/isidium/factory/ledger.py", "tests/factory/test_every_phase_records_its_billing_class.py"]
priority = "P2"

[narrative]
feature = "a run that parked after the plan gate reads the billing class its phases drew on, as a built run does"

[[rules]]
id = "R1"
text = "A phase that ends ok and commits nothing records its billing class on the run's row, as a phase that commits does through advance"

[[rules]]
id = "R2"
text = "A run the plan gate parks ends with the billing class its phases recorded"

[[rules]]
id = "R3"
text = "A read-only phase that wrote outside its surfaces ends the run with the adapter's billing class, as every other end the runner writes does"

[[rules]]
id = "R4"
text = "Recording a billing class never changes the run's head or the surfaces it touched"

[[guidance.avoid]]
id = "A1"
option = "passing a null head to advance"
because = "advance sets head_sha and surfaces_actual outright; a null would erase a head an earlier phase committed"

[[guidance.constraints]]
id = "C1"
text = "the billing class written is the phase result's own, not re-derived from the adapter's capabilities, except where the runner has no result (R3)"
because = "the result is the adapter's typed answer for that phase; it is what close's recovery reads too"

[[acceptance.scenarios]]
id = "S1"
kind = "test-marker"
title = "a read-only phase records its billing class"
rule = "R1"
observable = { test = "tests/factory/test_every_phase_records_its_billing_class.py::test_a_read_only_phase_records_its_billing_class" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "a parked run reads its phases' billing class"
rule = "R2"
observable = { test = "tests/factory/test_every_phase_records_its_billing_class.py::test_a_parked_run_reads_its_phases_billing_class" }

[[acceptance.scenarios]]
id = "S3"
kind = "test-marker"
title = "a read-only scope failure carries the billing class"
rule = "R3"
observable = { test = "tests/factory/test_every_phase_records_its_billing_class.py::test_a_read_only_scope_failure_carries_the_billing_class" }

[[acceptance.scenarios]]
id = "S4"
kind = "test-marker"
title = "recording the class leaves the head and surfaces alone"
rule = "R4"
observable = { test = "tests/factory/test_every_phase_records_its_billing_class.py::test_recording_the_class_leaves_the_head_and_surfaces_alone" }
```

## Scope

Found on 2026-09-24 with run r-13. It parked after six read-only phases ($7.05-equivalent on its phase rows), and its run row reads billing_class null. The runner records a class on the run only through advance, when a phase commits (runner.py:303-304), or at a failure's end. The plan, refute and judge phases commit nothing, and _park ends the run without a class.

In scope: the runner recording each ended phase's class, the park's end carrying it, the read-only scope failure's end, and the tests.

Not in scope: r-13's own row, which stays null as the record of the gap; close's recovery of results a dead host left (card 12, built).

## History

```toml
history = [
  { seq = 1, at = "2026-09-24T21:21:17Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:b236678f23868412d9cb9a7d8c189642709ec7c6a4ad24977a7821f3326a8904", h = "sha256:43f2ba901dda081ca4ce1f4c70dc10dae748d00dc63556db600fb33057d3b890" },
]
```
