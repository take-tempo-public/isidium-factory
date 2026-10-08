```toml
schema = 1
id = 43
kind = "story"
status = "draft"
source = "session"
title = "A run checks its card's committed mutations against the card's own tests before it ends, and a survivor goes to reconcile"
shape = "bdd"
effort = "default"
refs = ["packages/isidium-factory/src/isidium/factory/runner.py", "packages/isidium-factory/src/isidium/factory/gate.py", "packages/isidium-factory/src/isidium/factory/ledger.py", "tools/mutate.py"]
surfaces = ["packages/isidium-factory/src/isidium/factory/runner.py", "packages/isidium-factory/src/isidium/factory/gate.py", "packages/isidium-factory/src/isidium/factory/mutations.py", "tests/factory/test_run_checks_its_mutations.py", "tests/factory/test_v4a_ii.py"]
priority = "P1"

[narrative]
feature = "the hand mutation check after every run becomes a recorded step of the run itself"

[[rules]]
id = "R1"
text = "when the review gate is done in a chain, and the card's surfaces list any tools/mutations/*.toml, the run applies each [[mutation]] in the run's worktree, runs the card's own acceptance test files (the files its scenarios' observable.test names), and restores the file byte for byte, one mutation at a time"

[[rules]]
id = "R2"
text = "the results are a phase row `mutations` with no agent and no model (each mutation's id, killed or survived, and the test summary), named by hash like any phase's artifacts"

[[rules]]
id = "R3"
text = "a survivor is handed to the builder's reconcile as a blocking finding naming the mutation; after it the mutations are checked once more; a survivor then ends the run failed:gate with its work kept"

[[rules]]
id = "R4"
text = "a mutation whose find does not occur exactly once in the worktree is a survivor with that reason, never skipped"

[[guidance.avoid]]
id = "A1"
option = "running the whole suite per mutation, or calling tools/mutate.py's run"
because = "the owner, 2026-10-07 (smoothing the line, chunk plan): 'The card's own test files'; mutate.py's whole-suite principle stays for human and CI runs and is not changed"

[[guidance.avoid]]
id = "A2"
option = "running mutations inside the phase container"
because = "the container blocks whole-suite pytest and is the model's; this step is the wrapper's, on the host, like the commit"

[[guidance.constraints]]
id = "C1"
text = "the step's span is isidium.factory.mutations, never under isidium.factory.run.*, or test_v4a_ii.py's pinned chain span list is updated in the same change with the reason"
because = "checked when filing: test_v4a_ii.py:318-331 pins the run.* spans exactly"

[[guidance.constraints]]
id = "C2"
text = "a phase that ends mid-mutation is restored by the existing checkout.repair / .mutation-in-flight.json path, which this step writes like mutate.py's hold"
because = "card 23"

[[guidance.constraints]]
id = "C3"
text = "refusals use the run. namespace"
because = "core/disclosure.py stays untouched"

[[guidance.constraints]]
id = "C4"
text = "the phase row passes Ledger.bill with no model and no cost (cost unknown is None, never 0 laundered, card 19)"
because = "tests/factory/test_every_phase_records_its_billing_class.py"

[[guidance.constraints]]
id = "C9"
text = "every file this card changes passes ruff check, ruff format --check and mypy --strict, by path"
because = "r-38 and r-39 each lost a whole run to a one-line style miss"

[[acceptance.scenarios]]
id = "S1"
kind = "test-marker"
title = "a card with specs has its mutations checked against its own tests"
rule = "R1"
observable = { test = "tests/factory/test_run_checks_its_mutations.py::test_a_cards_mutations_are_checked_against_its_own_tests" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "the results are a mutations phase row"
rule = "R2"
observable = { test = "tests/factory/test_run_checks_its_mutations.py::test_the_results_are_a_mutations_phase_row" }

[[acceptance.scenarios]]
id = "S3"
kind = "test-marker"
title = "a survivor goes to reconcile once and then ends the run"
rule = "R3"
observable = { test = "tests/factory/test_run_checks_its_mutations.py::test_a_survivor_goes_to_reconcile_then_ends_the_run" }

[[acceptance.scenarios]]
id = "S4"
kind = "test-marker"
title = "a find that does not match is a survivor"
rule = "R4"
observable = { test = "tests/factory/test_run_checks_its_mutations.py::test_an_unmatched_find_is_a_survivor" }
```

## Scope

Ruled [owner, 2026-10-07]: 'Mutation check in the run', against 'The card's own test files'. Every run this session was mutation-checked by hand after it ended (scratchpad mutcheck.py: clean, then each mutation in place, the card's test file, restore). CI does not validate committed specs. Proposed here, to rule at signing: a survivor is a blocking finding for one reconcile round (R3).

## History

```toml
history = [
  { seq = 1, at = "2026-10-08T01:38:01Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:e78edebc980de1efe535eb96958cd0a71bd8300e75f031dc5ae1de7c059102e8", h = "sha256:90e873d917b76171c701b9ad028efcce3b726816e733497ed4529168af820fb6" },
]
```
