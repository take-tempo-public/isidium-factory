```toml
schema = 1
id = 31
kind = "story"
status = "draft"
source = "session"
title = "The PR watcher: one pass reads every open run's pull request and acts through the existing verbs, never merging"
shape = "bdd"
effort = "default"
refs = ["packages/isidium-factory/src/isidium/factory/forge.py::Forge", "packages/isidium-factory/src/isidium/factory/close.py::close", "packages/isidium-factory/src/isidium/factory/runner.py::run_fixup", "packages/isidium-factory/src/isidium/factory/ledger.py::Ledger", "packages/isidium-factory/src/isidium/factory/cli.py"]
surfaces = ["packages/isidium-factory/src/isidium/factory/watch.py", "packages/isidium-factory/src/isidium/factory/cli.py", "tests/factory/test_watch.py", "tools/mutations/watch.toml"]
priority = "P1"

[narrative]
feature = "the operator's waiting between PR-open and close is done by a pass that cannot merge, push, sign or ratify"

[[rules]]
id = "R1"
text = "decide(open runs, their pull requests' merge state and checks, the leases, the [watcher] policy, now) is a pure function returning a typed list of actions: close, rerun, fixup, flag; it reads nothing itself"

[[rules]]
id = "R2"
text = "merged → close (which lands); stale (BEHIND) or conflicted (DIRTY) → flag; green and open → nothing"

[[rules]]
id = "R3"
text = "red: (1) no rerun for this head yet → rerun the failed required checks once; (2) still red and the run has had no fixup → a fixup if [watcher].fixup is true and fewer than fixup_per_day watcher fixup leases were taken since the day's start, otherwise flag; (3) red after the fixup → rerun once, then the fixup verb (which ends the run failed:gate) and flag"

[[rules]]
id = "R4"
text = "`isidium-factory watch --once --tenant T` runs one pass: reads open runs (in flight, with a PR) from the ledger and their state from the forge, calls decide, and executes each action through the existing verbs under a lease held as watcher; a held lease skips that run this pass"

[[rules]]
id = "R5"
text = "it never merges, pushes, opens a pull request, signs or ratifies: its forge use is a narrow protocol of merge_state, checks and rerun_failed"

[[rules]]
id = "R6"
text = "each pass appends its actions and flags to watch.jsonl at the deploy home and prints one summary line; a flag already logged for the same (run, head, kind) is not logged again"

[[rules]]
id = "R7"
text = "a tenant below config@8 gets close, rerun and flag but never a fixup, and the summary says the opt-in is absent"

[[rules]]
id = "R8"
text = "spans: isidium.factory.watch.pass per pass, isidium.factory.watch.action per action (run, action, outcome, refusal rule), isidium.factory.watch.read per forge read; counters for actions, flags and refusals by rule; the OpenTelemetry API only"

[[guidance.avoid]]
id = "A1"
option = "merging, pushing, opening a PR, signing, ratifying"
because = "the handoff's ruling (2026-10-02) and the owner's at the watcher's first checkpoint"

[[guidance.avoid]]
id = "A2"
option = "a long-lived loop or a sleep inside the verb"
because = "the owner, 2026-10-04 (the watcher design, chunk plan: 'The PR watcher'): 'Host timer, one pass'"

[[guidance.avoid]]
id = "A3"
option = "a PR comment or a desktop notification for flags"
because = "the owner, 2026-10-04 (the watcher design, chunk plan: 'The PR watcher'): 'Watcher log + summary' (the others deferred, not refused)"

[[guidance.constraints]]
id = "C1"
text = "the watcher's forge use is its own narrow Protocol in watch.py (as close.Reader is), so forge.Forge and every existing test double are unchanged"
because = "the card-writing checklist; doubles of Forge live in six test files"

[[guidance.constraints]]
id = "C2"
text = "open runs are Ledger.in_flight() filtered on pr; no ledger.py change"
because = "checked when filing: in_flight returns full rows with pr and head_sha"

[[guidance.constraints]]
id = "C3"
text = "whether a rerun or a fixup already happened for a head is read from the lease rows (action, head_sha), not from a new table"
because = "the lease is the history (owner, 'As proposed')"

[[guidance.constraints]]
id = "C4"
text = "refusals use the run. namespace (run.watch-*); no new namespace"
because = "a new namespace needs a row in the store's core/disclosure.py (tests/unit/test_rule_ids.py)"

[[guidance.constraints]]
id = "C5"
text = "tools/mutations/watch.toml commits a mutation for R3 (a fixup past the ceiling) and one for R2 (a merged pull request left unclosed); each kill is checked against this card's own test file only; tools/mutate.py is --show only"
because = "the card-writing checklist"

[[guidance.constraints]]
id = "C6"
text = "watch spans are named isidium.factory.watch.*, never isidium.factory.run.*"
because = "test_v4a_ii pins the run.* span list exactly"

[[guidance.constraints]]
id = "C7"
text = "needs cards A and B merged first"
because = "it reads [watcher] and takes leases"

[[guidance.constraints]]
id = "C9"
text = "every file this card changes passes ruff check, ruff format --check and mypy --strict, by path"
because = "r-38 and r-39 each lost a whole run to a one-line style miss"

[[acceptance.scenarios]]
id = "S1"
kind = "test-marker"
title = "a merged pull request is closed"
rule = "R2"
observable = { test = "tests/factory/test_watch.py::test_a_merged_pr_is_closed" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "a stale or conflicted pull request is flagged, nothing more"
rule = "R2"
observable = { test = "tests/factory/test_watch.py::test_stale_or_conflicted_is_flagged" }

[[acceptance.scenarios]]
id = "S3"
kind = "test-marker"
title = "a red head is rerun once before any fixup"
rule = "R3"
observable = { test = "tests/factory/test_watch.py::test_a_red_head_is_rerun_once_first" }

[[acceptance.scenarios]]
id = "S4"
kind = "test-marker"
title = "a fixup past the day's ceiling is flagged instead"
rule = "R3"
observable = { test = "tests/factory/test_watch.py::test_a_fixup_past_the_ceiling_is_flagged" }

[[acceptance.scenarios]]
id = "S5"
kind = "test-marker"
title = "red after the fixup ends through the fixup verb and is flagged"
rule = "R3"
observable = { test = "tests/factory/test_watch.py::test_red_after_the_fixup_ends_and_is_flagged" }

[[acceptance.scenarios]]
id = "S6"
kind = "test-marker"
title = "a held lease skips the run this pass"
rule = "R4"
observable = { test = "tests/factory/test_watch.py::test_a_held_lease_skips_the_run" }

[[acceptance.scenarios]]
id = "S7"
kind = "test-marker"
title = "the pass never merges, pushes or opens a pull request"
rule = "R5"
observable = { test = "tests/factory/test_watch.py::test_the_pass_never_merges_or_pushes" }

[[acceptance.scenarios]]
id = "S8"
kind = "test-marker"
title = "a flag is logged once per run, head and kind"
rule = "R6"
observable = { test = "tests/factory/test_watch.py::test_a_flag_is_logged_once" }

[[acceptance.scenarios]]
id = "S9"
kind = "test-marker"
title = "below config@8 no fixup is ever chosen"
rule = "R7"
observable = { test = "tests/factory/test_watch.py::test_below_config8_no_fixup" }

[[acceptance.scenarios]]
id = "S10"
kind = "test-marker"
title = "a pass emits its pass, action and read spans"
rule = "R8"
observable = { test = "tests/factory/test_watch.py::test_a_pass_emits_its_spans" }

[[acceptance.scenarios]]
id = "S11"
kind = "test-marker"
title = "decide is a pure function of what it is handed"
rule = "R1"
observable = { test = "tests/factory/test_watch.py::test_decide_is_a_pure_function_of_its_inputs" }
```

## Scope

Ruled 2026-10-04 [owner], three checkpoints: actions 'close + land after merge, fixup on red, flag stale/conflicted, rerun flaky checks'; identity 'The lander's App'; host 'Host timer, one pass'; locking 'Per-run lease'; flags 'Watcher log + summary'; the order on red 'As proposed'; telemetry 'Also per forge read'. Forge-neutral: it uses the seam only, so a Gitea driver gives it Gitea.

Not in scope: the timer (card D); webhooks (polling first); a Gitea driver.

## History

```toml
history = [
  { seq = 1, at = "2026-10-05T14:22:17Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:32b5c9c23c5da61f94b30eafa7aded8b4278572cb5f8e6f4a39bfd926addaf7d", h = "sha256:1ea28125617ddcf1a67e52aad10ee9df9f7b56189b806aa3203e1db53bba19a9" },
]
```
