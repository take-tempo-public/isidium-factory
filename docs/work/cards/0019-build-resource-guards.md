```toml
schema = 1
id = 19
kind = "story"
status = "draft"
source = "session"
title = "A phase cannot run the whole test suite, a harness that dies records what it spent, and the process limit is ours"
shape = "bdd"
effort = "default"
refs = ["packages/isidium-factory/src/isidium/factory/guard.py::main", "packages/isidium-factory/src/isidium/factory/render.py::settings", "packages/isidium-factory/src/isidium/factory/harness.py::stream_out", "packages/isidium-factory/src/isidium/factory/container.py"]
surfaces = ["packages/isidium-factory/src/isidium/factory/guard.py", "packages/isidium-factory/src/isidium/factory/render.py", "packages/isidium-factory/src/isidium/factory/harness.py", "packages/isidium-factory/src/isidium/factory/container.py", "tests/factory/test_build_resource_guards.py", "packages/isidium-factory/src/isidium/factory/adapter.py", "tools/mutations/build-guards.toml"]
priority = "P1"

[narrative]
feature = "a build phase that tries to run the project's whole gate is told no before it starves its own container, and a phase that dies anyway leaves an honest record of its spend"

[[rules]]
id = "R1"
text = "A Bash tool call that runs pytest naming no test file or test node (no argument ending in .py and none containing ::) is blocked by the guard with a reason naming the card's own tests and green-bar, and the block is counted as the write guard's are"

[[rules]]
id = "R2"
text = "A Bash tool call that runs pytest naming a test file or test node, and every Bash call that runs no pytest, is not blocked by R1"

[[rules]]
id = "R3"
text = "The rendered settings route Bash through the guard as well as the writing tools; the guard's write rule still applies to the writing tools only"

[[rules]]
id = "R4"
text = "A harness that exits with no result records the phase's wall-clock duration from spawn to exit, not 0"

[[rules]]
id = "R5"
text = "A harness that exits with no result records its cost as unknown (null), never as 0, beside the token counts its stream already carried"

[[rules]]
id = "R6"
text = "The container adapter passes an explicit --pids-limit to podman run, from one named constant whose value is podman's default the clean builds ran under, 2048"

[[guidance.avoid]]
id = "A1"
option = "relying on the builder prompt alone"
because = "builder v3 §3 already forbids the whole suite and was ignored in both crashed attempts (r-18, r-19)"

[[guidance.avoid]]
id = "A2"
option = "imputing a dollar cost here"
because = "no price table exists in code yet; an imputed cost from token counts (03 §6's versioned price_table) is its own card"

[[guidance.constraints]]
id = "C1"
text = "the guard stays one module and one hook command; its exit-2 contract and block log are unchanged"
because = "the block count is read from outside the phase and a phase must not be able to under-report it"

[[guidance.constraints]]
id = "C2"
text = "the runner image carries the guard, so the change reaches runs only after a runner image rebuild with deploy/build-runner.sh"
because = "operational, not part of this card; it rides card 15's rebuild"

[[guidance.constraints]]
id = "C3"
text = "adapter.py changes only PhaseResult.cost_micro: it becomes int | None with a comment saying None means unknown (a harness that died with no result), and every reader already tolerating a null is left as it is"
because = "the owner, on r-26's question: a null cost must cross the adapter seam or R5 loses the whole crashed-attempt record"

[[guidance.constraints]]
id = "C4"
text = "tools/mutations/build-guards.toml commits one mutation for R1's block (the whole-suite check never matching) and one for R6's limit (the --pids-limit argument dropped), ids M1 and M2. Each kill is checked against this card's own test file only: apply the mutation in place, run tests/factory/test_build_resource_guards.py, restore. tools/mutate.py is run with --show only and never runs a mutation inside the container"
because = "the owner, on r-26's question: the project's rule is that a guard is mutation-checked with a committed spec; and on r-27: mutate.py runs the whole suite per mutation, which exhausted the build container's processes twice (Cannot fork, signal 6) — the very failure this card fixes; the suite is green-bar's"

[[acceptance.scenarios]]
id = "S1"
kind = "test-marker"
title = "a whole-suite pytest is blocked and counted"
rule = "R1"
observable = { test = "tests/factory/test_build_resource_guards.py::test_a_whole_suite_pytest_is_blocked_and_counted" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "a pytest naming a test file or node passes"
rule = "R2"
observable = { test = "tests/factory/test_build_resource_guards.py::test_a_pytest_naming_a_test_file_or_node_passes" }

[[acceptance.scenarios]]
id = "S3"
kind = "test-marker"
title = "the settings route Bash through the guard"
rule = "R3"
observable = { test = "tests/factory/test_build_resource_guards.py::test_the_settings_route_bash_through_the_guard" }

[[acceptance.scenarios]]
id = "S4"
kind = "test-marker"
title = "a no-result exit records its duration"
rule = "R4"
observable = { test = "tests/factory/test_build_resource_guards.py::test_a_no_result_exit_records_its_duration" }

[[acceptance.scenarios]]
id = "S5"
kind = "test-marker"
title = "a no-result exit records its cost as unknown"
rule = "R5"
observable = { test = "tests/factory/test_build_resource_guards.py::test_a_no_result_exit_records_its_cost_as_unknown" }

[[acceptance.scenarios]]
id = "S6"
kind = "test-marker"
title = "the adapter passes an explicit pids limit"
rule = "R6"
observable = { test = "tests/factory/test_build_resource_guards.py::test_the_adapter_passes_an_explicit_pids_limit" }
```

## Scope

Found on 2026-09-25/26: r-18's and r-19's build attempt 1 both died on signal 6 with no result after the builder ran the whole suite (pytest tests), which outlived its tool timeout, went to the background and exhausted the container's processes (Cannot fork, fork: retry: Resource temporarily unavailable) at podman's default pids 2048. Both lost attempts recorded cost 0 and duration 0; r-19's lost most of its turn budget and ended failed:budget.

The owner ruled all three fixes (2026-09-27): a hook denies whole-suite runs; a no-result exit records its spend; an explicit --pids-limit.

Not in scope: an imputed dollar cost (A2, its own card); the builder prompt; the runner image rebuild (C2).

## History

```toml
history = [
  { seq = 1, at = "2026-09-27T23:10:02Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:c84eaeb9c471a91ee342cafbd953a7257861a5ca808b235b60ca1dfa59d615be", h = "sha256:1c57a32f29b655d8f589b55b1d3b14e06ed886f8b3e930591b161466c1e0763b" },
  { seq = 2, at = "2026-09-27T23:52:35Z", by = "amodal1@users.noreply.github.com", act = "ratified", fields = ["status"], build = "sha256:c84eaeb9c471a91ee342cafbd953a7257861a5ca808b235b60ca1dfa59d615be", h = "sha256:2913941ab768cccdaed2a269468a2f6d865ce1f463fbe00adf879fecfad21feb", batch = 37 },
  { seq = 3, at = "2026-09-28T19:00:51Z", by = "amodal1@users.noreply.github.com", act = "demoted", fields = ["guidance", "status", "surfaces"], build = "sha256:e211098bb59b041ed68e3134b5bd751f6a491ef87afcfcc2d0f5c15ba8df7886", h = "sha256:2b076ed1141ddafe330f66683b278230027d99cd8684d4315ac22a261866dbf4", sig = "ed25519:5a6c85e20ab2a6eecc5d6df4f873f9af746b98a33d923c3302a900c365984ae8:90Cwbl2T3EPtv834pkS/EXYgve6DAmvl8FBaq2/ULk8nzox7Hi2s+rEsiKTO3buQVSnPnDDOy/xUxou7wH3eAg==" },
  { seq = 4, at = "2026-09-28T19:01:41Z", by = "amodal1@users.noreply.github.com", act = "ratified", fields = ["status"], build = "sha256:e211098bb59b041ed68e3134b5bd751f6a491ef87afcfcc2d0f5c15ba8df7886", h = "sha256:8ebc441ee646d4fb5c5ed814eac906b1e33236e64f981e030e910e99dfd4124b", batch = 39 },
  { seq = 5, at = "2026-09-28T20:20:20Z", by = "amodal1@users.noreply.github.com", act = "demoted", fields = ["guidance", "status"], build = "sha256:5233a7f17a06a3f23d23dc5a37e8b41676cc39777c6f7708f2335031a337941d", h = "sha256:598f7c0c9ce3eb29d5542375a96aacb760918405e2aa9df609a3f31f52d747ee", sig = "ed25519:5a6c85e20ab2a6eecc5d6df4f873f9af746b98a33d923c3302a900c365984ae8:tK205E0mjBUDeqey+qy32ptugKpE8UF/en09xqbeTWNqAxpS0ei8wiDz2m4opmOXENlH32bwvEckkcil+PsXCw==" },
]
```
