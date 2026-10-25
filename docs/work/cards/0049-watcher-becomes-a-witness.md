```toml
schema = 1
id = 49
kind = "story"
status = "draft"
source = "session"
title = "The PR watcher becomes a witness: it records what it sees and wakes the owning run, and acts on nothing"
shape = "bdd"
depends_on = [48]
effort = "default"
refs = ["packages/isidium-factory/src/isidium/factory/watch.py", "packages/isidium-factory/src/isidium/factory/cli.py"]
surfaces = ["packages/isidium-factory/src/isidium/factory/watch.py", "packages/isidium-factory/src/isidium/factory/cli.py", "tests/factory/test_witness.py", "tests/factory/test_watch.py", "tests/factory/test_watch_retries.py", "tests/factory/test_watch_idle_pass.py", "tools/mutations/watch.toml", "tools/mutations/watch-retries.toml"]
priority = "P1"

[narrative]
feature = "the witness never closes, reruns or fixes up; the run it wakes does"

[[rules]]
id = "R1"
text = "a pass reads each open run's pull request (merge state and checks, nothing else) and writes the matching observation (pr-merged, pr-red, pr-stale, pr-conflicted) through the ledger; an observation already written for the same (kind, run, head) is not written again"

[[rules]]
id = "R2"
text = "for each run that received a new observation it calls launcher.wake(resume, r-N), and nothing else"

[[rules]]
id = "R3"
text = "the pass never closes, reruns, fixes up, pushes, merges, takes a lease, or calls the store; its forge Protocol is merge_state and checks only"

[[rules]]
id = "R4"
text = "the idle pass is unchanged: with no open run it reads the ledger and stops"

[[rules]]
id = "R5"
text = "the summary line reports observations written and wakes made, and watch.jsonl keeps one line per observation"

[[guidance.avoid]]
id = "A1"
option = "deciding a step, checking a cap, or reading the card"
because = "the owner, 2026-10-23/25 (the actor design, chunk plan): 'the witness should witness'; the run decides, checks its caps and re-reads its card"

[[guidance.constraints]]
id = "C1"
text = "the action classes (Close, Rerun, Fixup), Verbs, _leased and Policy leave watch.py; the tests that asserted the watcher executed them (test_watch.py's close/rerun/fixup/ceiling/held-lease cases, all of test_watch_retries.py, test_watch_idle_pass.py's open-PR case) are rewritten to assert the observation and the wake, or removed where the behaviour now lives in the run (card 3's tests)"
because = "checked when filing"

[[guidance.constraints]]
id = "C2"
text = "tools/mutations/watch.toml and watch-retries.toml target code this card removes: each is re-anchored to the witness's own limits (an observation written twice; a wake without a new observation) or deleted, and `tools/mutate.py --show` passes on every spec"
because = "a rewrite orphaned v2.toml M6 once (#102); CI does not validate specs"

[[guidance.constraints]]
id = "C3"
text = "the watch.* span names stay, and the pass still emits no isidium.factory.run* span"
because = "test_watch.py:598-613"

[[guidance.constraints]]
id = "C4"
text = "refusals use the run. namespace"
because = "core/disclosure.py stays untouched"

[[guidance.constraints]]
id = "C9"
text = "every file this card changes passes ruff check, ruff format --check and mypy --strict, by path"
because = "r-38 and r-39 each lost a whole run to a one-line style miss"

[[acceptance.scenarios]]
id = "S1"
kind = "test-marker"
title = "a merged PR is observed once and its run woken"
rule = "R1"
observable = { test = "tests/factory/test_witness.py::test_a_merged_pr_is_observed_and_woken" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "a red head is observed and its run woken"
rule = "R2"
observable = { test = "tests/factory/test_witness.py::test_a_red_head_is_observed_and_woken" }

[[acceptance.scenarios]]
id = "S3"
kind = "test-marker"
title = "the pass acts on nothing"
rule = "R3"
observable = { test = "tests/factory/test_witness.py::test_the_pass_acts_on_nothing" }

[[acceptance.scenarios]]
id = "S4"
kind = "test-marker"
title = "an idle pass still reads only the ledger"
rule = "R4"
observable = { test = "tests/factory/test_witness.py::test_an_idle_pass_reads_only_the_ledger" }

[[acceptance.scenarios]]
id = "S5"
kind = "test-marker"
title = "the summary reports observations and wakes"
rule = "R5"
observable = { test = "tests/factory/test_witness.py::test_the_summary_reports_observations_and_wakes" }
```

## Scope

Ruled [owner, 2026-10-07/23]: 'the watcher shoudn't ship. it should watch. and tell something else to ship'; 'the witness should witness'. Migration 'Card by card, line kept running': this card lands after the run can take its own steps (card 3).

## History

```toml
history = [
  { seq = 1, at = "2026-10-25T21:44:41Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "depends_on", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:b844c585bb0b3e05a8bdab4f6a78a465c28b0b186b5f31ada4ba61d4cc1b6d00", h = "sha256:4cb4dca160fd937f39f7a90670a5bfa27e107ebe7f19d5b8f323ef38bbfd4f24" },
]
```
