```toml
schema = 1
id = 26
kind = "story"
status = "ratified"
source = "session"
title = "A run whose pull request is red on the gate gets one fixup phase on its own branch, invoked by the operator"
shape = "bdd"
effort = "default"
refs = ["packages/isidium-factory/src/isidium/factory/runner.py::run_phase", "packages/isidium-factory/src/isidium/factory/forge.py::Forge", "packages/isidium-factory/src/isidium/factory/github.py", "packages/isidium-factory/src/isidium/factory/cli.py", "packages/isidium-factory/src/isidium/factory/adapter.py"]
surfaces = ["packages/isidium-factory/src/isidium/factory/runner.py", "packages/isidium-factory/src/isidium/factory/forge.py", "packages/isidium-factory/src/isidium/factory/github.py", "packages/isidium-factory/src/isidium/factory/cli.py", "packages/isidium-factory/src/isidium/factory/adapter.py", "prompts/builder/v6.md", "tests/factory/test_fixup_repairs_a_red_pr.py", "tools/mutations/fixup.toml"]
priority = "P1"

[narrative]
feature = "a one-line lint or type miss costs one bounded fixup on the same run, not a whole fresh run"

[[rules]]
id = "R1"
text = "`run --run r-N --phase fixup` reads the required checks on the run's pull request head; when none is red it refuses fixup.nothing-red and spends nothing"

[[rules]]
id = "R2"
text = "When some are red, the builder runs a fixup phase in the run's worktree, handed each failed required check's name and the last 200 lines of its failed step's log, read from the forge and named by hash on the record"

[[rules]]
id = "R3"
text = "The fixup writes inside the build's surface (the plan's touched and the test paths); its work is committed under the run's identity with a Factory-Agent trailer naming the fixup, the run's head advances to it, and its diff is on its phase row"

[[rules]]
id = "R4"
text = "One fixup round: a fixup invoked when the run already has one and its pull request head is still red ends the run failed:gate, its work kept, and spends no model call"

[[rules]]
id = "R5"
text = "A fixup is not reviewed again: the review gate's verdict stands, and close treats a run whose last phase is a fixup after a passed review as reviewed"

[[rules]]
id = "R6"
text = "Builder prompt v6 is v5 plus a section for the fixup phase: make the failing checks pass inside the surfaces, change nothing else, and run the v5 per-file checks on what it touched; v5 is not edited"

[[guidance.avoid]]
id = "A1"
option = "pushing or opening a pull request from the fixup"
because = "the owner, 2026-10-02: push and PR stay the operator's verbs; the operator pushes after the fixup, and a later PR watcher invokes the same verbs"

[[guidance.avoid]]
id = "A2"
option = "a fixup that widens the surface or changes logic beyond what the failing checks name"
because = "no re-review is the ruled trade (owner, 2026-10-02): it is safe only while the fixup is bounded"

[[guidance.constraints]]
id = "C1"
text = "the forge seam gains one read on the full Forge protocol for a commit's failed required jobs and their log tails; close's narrower Reader protocol is not changed, so its test doubles are untouched"
because = "checked when filing: only github.py implements Forge; the doubles in test_v5a, test_close_reruns_a_red_gate and test_close_records_left_results implement Reader"

[[guidance.constraints]]
id = "C2"
text = "adapter.Phase gains fixup; AGENT_OF maps it to the builder; no other enumeration of phases changes"
because = "checked when filing: Phase is enumerated only in adapter.py"

[[guidance.constraints]]
id = "C3"
text = "tools/mutations/fixup.toml commits a mutation for R1 (fixup on a green head), one for R4 (a second round allowed); each kill is checked against this card's own test file only, applied in place and restored; tools/mutate.py is --show only"
because = "the card-writing checklist"

[[guidance.constraints]]
id = "C4"
text = "every file this card changes passes ruff check, ruff format --check and mypy --strict, by path"
because = "r-38 and r-39 each lost a whole run to a one-line style miss"

[[guidance.constraints]]
id = "C5"
text = "selecting builder v6 is a signed config act and a runner rebuild after the merge, not this card"
because = "7bd.11: a new version is a new file; the image carries prompts"

[[acceptance.scenarios]]
id = "S1"
kind = "test-marker"
title = "a green head refuses and spends nothing"
rule = "R1"
observable = { test = "tests/factory/test_fixup_repairs_a_red_pr.py::test_a_green_head_refuses_and_spends_nothing" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "a red head runs the fixup with the failed checks and log tails as inputs"
rule = "R2"
observable = { test = "tests/factory/test_fixup_repairs_a_red_pr.py::test_a_red_head_runs_the_fixup_with_the_failures_as_inputs" }

[[acceptance.scenarios]]
id = "S3"
kind = "test-marker"
title = "the fixup's work is committed under the run and advances its head"
rule = "R3"
observable = { test = "tests/factory/test_fixup_repairs_a_red_pr.py::test_the_fixups_work_is_committed_under_the_run" }

[[acceptance.scenarios]]
id = "S4"
kind = "test-marker"
title = "a second red after a fixup ends the run failed gate with no model call"
rule = "R4"
observable = { test = "tests/factory/test_fixup_repairs_a_red_pr.py::test_a_second_red_ends_the_run_failed_gate" }

[[acceptance.scenarios]]
id = "S5"
kind = "test-marker"
title = "close treats a fixup after a passed review as reviewed"
rule = "R5"
observable = { test = "tests/factory/test_fixup_repairs_a_red_pr.py::test_close_treats_a_fixup_after_review_as_reviewed" }

[[acceptance.scenarios]]
id = "S6"
kind = "test-marker"
title = "builder v6 names the fixup section and v5 is unedited"
rule = "R6"
observable = { test = "tests/factory/test_fixup_repairs_a_red_pr.py::test_builder_v6_names_the_fixup_section" }
```

## Scope

Found 2026-10-02: r-38 (card 23) and r-39 (card 24) each passed their tests and the review gate and would have gone red on one style line in their own test file; a red pull request has no repair path but a fresh run (a hand commit on the run's branch makes close refuse pr-mismatch; a red PR cannot merge). Gap recorded since 2026-09-22.

The owner ruled the flow (2026-10-02): a fixup phase on the same run; input the failed checks and bounded log tails; one round, still red ends failed:gate with work kept; no re-review; invoked by the operator now, so no verb owner changes — a PR watcher, designed next as its own component on the forge seam, will invoke it.

Not in scope: the watcher; pushing (the operator's verb); selecting builder v6.

## History

```toml
history = [
  { seq = 1, at = "2026-10-02T21:36:06Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:cc214f46845426b4e814b21243b0570341dc473aa3ab2fc323002bacc30ae38c", h = "sha256:d21b051d608669be4f5160d6a4bafd161d06b7df523395497c80ab767fd447b0" },
  { seq = 2, at = "2026-10-02T22:04:01Z", by = "amodal1@users.noreply.github.com", act = "ratified", fields = ["status"], build = "sha256:cc214f46845426b4e814b21243b0570341dc473aa3ab2fc323002bacc30ae38c", h = "sha256:24f4e7bc52c0c69d72ced59f5e70ea25fd7f552a630a64fd2cd28f0d49a0e430", batch = 58 },
  { seq = 3, at = "2026-10-02T23:34:37Z", by = "amodal1@users.noreply.github.com", act = "demoted", fields = ["status"], build = "sha256:cc214f46845426b4e814b21243b0570341dc473aa3ab2fc323002bacc30ae38c", h = "sha256:fce96f874422693d356c15da7b06e7a42ce18de46362f0f80acd9cd5f72e3522" },
  { seq = 4, at = "2026-10-02T23:35:02Z", by = "amodal1@users.noreply.github.com", act = "ratified", fields = ["status"], build = "sha256:cc214f46845426b4e814b21243b0570341dc473aa3ab2fc323002bacc30ae38c", h = "sha256:d6223bbe08786f3f67136cee7ed0532fbbb4ff3c56b25178fcf4d2d5d0aeefa2", batch = 59 },
]
```
