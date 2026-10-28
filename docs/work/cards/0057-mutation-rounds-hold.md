```toml
schema = 1
id = 57
kind = "story"
status = "draft"
source = "session"
title = "A run's second mutation check holds the first one's mutations: none withdrawn, none weakened, and no kill read off a deadline"
shape = "bdd"
effort = "default"
refs = ["packages/isidium-factory/src/isidium/factory/mutations.py", "packages/isidium-factory/src/isidium/factory/runner.py", "packages/isidium-factory/src/isidium/factory/gate.py", "tests/factory/test_v4a.py", "tests/factory/test_run_checks_its_mutations.py", "docs/work/cards/0043-run-checks-its-mutations.md"]
surfaces = ["packages/isidium-factory/src/isidium/factory/mutations.py", "packages/isidium-factory/src/isidium/factory/runner.py", "tests/factory/test_mutation_rounds_hold.py", "tests/factory/test_run_checks_its_mutations.py", "tests/factory/test_v4a.py", "tools/mutations/mutation-rounds.toml"]
priority = "P0"

[narrative]
feature = "the reconcile a surviving mutation buys cannot pass by editing the mutation instead of the tests"

[[rules]]
id = "R1"
text = "on a run's second mutation check, every mutation the first check recorded (by its finding id) that has no result in the second is a survivor with reason `withdrawn`"

[[rules]]
id = "R2"
text = "on a run's second mutation check, a mutation that survived the first with reason `passed` and whose file, find or replace differ from the first check's is a survivor with reason `changed`; a first-round survivor for any other reason (the row itself was the defect) may change its row"

[[rules]]
id = "R3"
text = "a mutation whose test run times out is killed only when the time it was given was at least the clean baseline run's own duration; given less, it is a survivor with reason `deadline`"

[[rules]]
id = "R4"
text = "each mutation's test run stops at its first failure (pytest -x); the clean baseline run does not, and the exit codes read as killed are unchanged"

[[rules]]
id = "R5"
text = "the tests' shared temporary run tree (tests/factory/test_v4a.py, where it is git-initialised) sets core.autocrlf=false in that repository, so a test's files keep their line endings whatever the host's global git config says"

[[guidance.avoid]]
id = "A1"
option = "refusing reconcile any write to a tools/mutations/*.toml"
because = "a survivor whose own row is the defect (find-not-once, outside, empty, duplicate-id) is fixed by editing the row; R1 and R2 hold only what would weaken a check"

[[guidance.avoid]]
id = "A2"
option = "a per-mutation timeout of its own in policy or code"
because = "C-1 and card 43: the step has one deadline, the signed wall_clock_s; R3 measures against the baseline the step already runs"

[[guidance.constraints]]
id = "C1"
text = "the first check's results are read back from the run's own recorded mutations.1.json, its bytes verified against the sha256 on that phase row; a missing or mismatched record refuses run.mutation-record, never reads as an empty first round"
because = "the record is the run's evidence; a lost one must not let round 2 pass unchecked"

[[guidance.constraints]]
id = "C2"
text = "a result records a digest of its row's file, find and replace, so round 2 compares rows without the first round's spec bytes; `withdrawn` and `changed` join Reason and WHY, each with the sentence the builder is handed"
because = "WHY is the one table a finding's why is read from (mutations.py)"

[[guidance.constraints]]
id = "C3"
text = "the -x choice is written at the pytest call with its reason: the card's own files, where tools/mutate.py's whole-suite reason for omitting it does not hold"
because = "r-54's review (card 43, PR #114), F9: no reason for the omission was written at the site"

[[guidance.constraints]]
id = "C4"
text = "tools/mutations/mutation-rounds.toml commits a mutation for each of R1's missing-result check, R2's changed-row check, R3's baseline comparison and R5's autocrlf setting; each is killed by this card's own test file alone"
because = "the card-writing checklist; card 43 checks this spec in the run itself"

[[guidance.constraints]]
id = "C5"
text = "the span, the phase row's shape and the refusal namespace stay as card 43 left them (isidium.factory.mutations; no model, no cost; run.)"
because = "card 43 C1, C3, C4"

[[guidance.constraints]]
id = "C9"
text = "every file this card changes passes ruff check, ruff format --check and mypy --strict, by path"
because = "r-38 and r-39 each lost a whole run to a one-line style miss"

[[acceptance.scenarios]]
id = "S1"
kind = "test-marker"
title = "a mutation removed between the checks survives as withdrawn"
rule = "R1"
observable = { test = "tests/factory/test_mutation_rounds_hold.py::test_a_withdrawn_mutation_survives" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "a passed survivor whose row changed survives as changed, and a fixed find-not-once row does not"
rule = "R2"
observable = { test = "tests/factory/test_mutation_rounds_hold.py::test_a_weakened_survivor_survives" }

[[acceptance.scenarios]]
id = "S3"
kind = "test-marker"
title = "a timeout given less than the baseline's time is a deadline survivor, not a kill"
rule = "R3"
observable = { test = "tests/factory/test_mutation_rounds_hold.py::test_a_short_timeout_is_not_a_kill" }

[[acceptance.scenarios]]
id = "S4"
kind = "test-marker"
title = "a mutation's test run stops at its first failure"
rule = "R4"
observable = { test = "tests/factory/test_mutation_rounds_hold.py::test_a_mutation_run_stops_at_its_first_failure" }

[[acceptance.scenarios]]
id = "S5"
kind = "test-marker"
title = "the shared run tree keeps LF under a global core.autocrlf=true"
rule = "R5"
observable = { test = "tests/factory/test_mutation_rounds_hold.py::test_the_run_tree_ignores_a_global_autocrlf" }
```

## Scope

Ruled [owner, 2026-10-27]: '1', answering the option 'merge once green and card a small P0 follow-up for F1 (round 2 compares round-1 survivors by id; a missing or weakened one still survives) plus F2 and F9'. From r-54's review (card 43, PR #114): F1 (major) round 2 re-reads the spec from the tree and never compares with round 1, and reconcile's writes include the card's spec; F2 (minor) a timeout counts as a kill, so a cut-off last mutation reads clean; F9 (minor) no -x. Confirmed by reading runner.py `_mutations` and mutations.py `check`/`_apply`/`_pytest`. R5 ruled [owner, 2026-10-27]: 'r5', answering whether to add the fixture fix to this card: r-54's close failed S1 (failed:acceptance) on a host with global core.autocrlf=true and passed with it false, varied alone; card 43 was closed unverified by accept with the override for that one call (owner: 'Close now'). The scenario sets the global value through the environment, so it fails on any host before the fix.

## History

```toml
history = [
  { seq = 1, at = "2026-10-28T06:09:01Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:2ae4ca70a37f87bac4b569cccca0db700b1dd155e45c485f8ed5a6d54724c36c", h = "sha256:c015bd783c3f53d23c97aa8d0ecee92ca2644618894f25b719e30b4325ac3f99" },
]
```
