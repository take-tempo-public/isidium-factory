```toml
schema = 1
id = 48
kind = "story"
status = "ratified"
source = "session"
title = "The run owns its life to closed: it ships when its review gate passes, and each resume re-reads its card and takes its own next step"
shape = "bdd"
depends_on = [47, 43]
effort = "default"
refs = ["packages/isidium-factory/src/isidium/factory/runner.py", "packages/isidium-factory/src/isidium/factory/close.py", "packages/isidium-factory/src/isidium/factory/cli.py", "packages/isidium-factory/src/isidium/factory/forge.py", "packages/isidium-factory/src/isidium/factory/github.py", "packages/isidium-factory/src/isidium/factory/watch.py"]
surfaces = ["packages/isidium-factory/src/isidium/factory/runner.py", "packages/isidium-factory/src/isidium/factory/cli.py", "packages/isidium-factory/src/isidium/factory/lifecycle.py", "packages/isidium-factory/src/isidium/factory/forge.py", "packages/isidium-factory/src/isidium/factory/github.py", "tests/factory/test_run_lifecycle.py", "tests/factory/test_v2.py", "tools/mutations/lifecycle.toml"]
priority = "P1"

[narrative]
feature = "a run goes from reviewed to closed with no one pushing, rerunning, fixing up or closing it by hand"

[[rules]]
id = "R1"
text = "when `run --run r-N` ends with the review gate done and no pull request yet, the run ships in the same process: it pushes its story branch and opens its pull request through the same functions the push and pr-open verbs use (the governed-path refusal and the failed-run refusal unchanged) and records the PR number"

[[rules]]
id = "R2"
text = "`run --run r-N --resume` takes the run's lease (holder run), then reads the card's signed state first; withdrawn or draft (the existing ABANDONING set) ends the run abandoned with its work kept and its pull request closed with a note, and nothing else happens"

[[rules]]
id = "R3"
text = "otherwise it reads the run's newest unconsumed observation: pr-merged → fast-forward the tenant checkout (a clean checkout only; dirty or diverged refuses run.checkout-dirty or run.checkout-diverged and does nothing else) → close; pr-red at a head with no rerun yet → rerun the failed checks; pr-red after the rerun with no fixup → the fixup, if [watcher].fixup is on and fewer fixups than fixup_per_day were started since the day's start (UTC); otherwise nothing; pr-red after the fixup → the fixup verb, which ends the run failed:gate"

[[rules]]
id = "R4"
text = "the observation is marked consumed by the run whatever the step's outcome, refusals included, so a step is never retried at the same head until a new observation arrives"

[[rules]]
id = "R5"
text = "the fixup count is every fixup phase started since the day's start, the operator's included, read from the ledger's phase rows"

[[guidance.avoid]]
id = "A1"
option = "shipping from inside run_chain, or changing run_chain's signature"
because = "checked when filing: a dozen chain tests call run_chain without a forge; the ship is the run's next step in the same process, after the chain"

[[guidance.avoid]]
id = "A2"
option = "merging"
because = "auto-merge is held (the owner, 2026-10-07); the merge stays the owner's button"

[[guidance.avoid]]
id = "A3"
option = "the witness choosing the step"
because = "the owner, 2026-10-23/25 (the actor design, chunk plan): the run reads its own state plus the observation"

[[guidance.constraints]]
id = "C1"
text = "the pull request close is a narrow Protocol of its own (as close.Reader and watch.Watched are), implemented by github.py; forge.Forge's existing doubles are unchanged; the capability matrix declares it"
because = "the card-writing checklist; Forge doubles live in six test files"

[[guidance.constraints]]
id = "C2"
text = "cli.py's _never_pushed and _record_pr move to where both the verbs and the run use them, unchanged in behaviour"
because = "one home for each rule"

[[guidance.constraints]]
id = "C3"
text = "spans are isidium.factory.lifecycle.*, never isidium.factory.run.*"
because = "test_v4a_ii.py:318-331 pins the run.* span list exactly"

[[guidance.constraints]]
id = "C4"
text = "tools/mutations/lifecycle.toml commits a mutation for R2 (a withdrawn card proceeds), one for R3's cap (a fixup past the cap), one for R4 (an observation left unconsumed on a refusal); each kill is checked against this card's own test file only; tools/mutate.py is --show only"
because = "the card-writing checklist"

[[guidance.constraints]]
id = "C5"
text = "refusals use the run. and forge. namespaces"
because = "core/disclosure.py stays untouched"

[[guidance.constraints]]
id = "C6"
text = "the reason the fixup count includes the operator's fixups is written at the site"
because = "the ledger records no invoker on a phase; counting all of them is conservative"

[[guidance.constraints]]
id = "C9"
text = "every file this card changes passes ruff check, ruff format --check and mypy --strict, by path"
because = "r-38 and r-39 each lost a whole run to a one-line style miss"

[[acceptance.scenarios]]
id = "S1"
kind = "test-marker"
title = "a run whose gate passes ships and records its PR"
rule = "R1"
observable = { test = "tests/factory/test_run_lifecycle.py::test_a_run_whose_gate_passes_ships" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "a resume on a withdrawn card abandons and closes the PR"
rule = "R2"
observable = { test = "tests/factory/test_run_lifecycle.py::test_a_resume_on_a_withdrawn_card_abandons" }

[[acceptance.scenarios]]
id = "S3"
kind = "test-marker"
title = "a merged observation fast-forwards and closes"
rule = "R3"
observable = { test = "tests/factory/test_run_lifecycle.py::test_a_merged_observation_fast_forwards_and_closes" }

[[acceptance.scenarios]]
id = "S4"
kind = "test-marker"
title = "a dirty checkout refuses and does nothing else"
rule = "R3"
observable = { test = "tests/factory/test_run_lifecycle.py::test_a_dirty_checkout_refuses" }

[[acceptance.scenarios]]
id = "S5"
kind = "test-marker"
title = "red is rerun, then fixed up under the cap, then ended"
rule = "R3"
observable = { test = "tests/factory/test_run_lifecycle.py::test_red_is_rerun_then_fixed_up_then_ended" }

[[acceptance.scenarios]]
id = "S6"
kind = "test-marker"
title = "a refused step consumes its observation"
rule = "R4"
observable = { test = "tests/factory/test_run_lifecycle.py::test_a_refused_step_consumes_its_observation" }

[[acceptance.scenarios]]
id = "S7"
kind = "test-marker"
title = "the fixup cap counts every fixup started today"
rule = "R5"
observable = { test = "tests/factory/test_run_lifecycle.py::test_the_fixup_cap_counts_every_fixup" }
```

## Scope

Ruled [owner, 2026-10-23/25]: 'The run owns it to closed'; 'Re-read the card first'; spend guards 'By the spending actor'. Folds in withdrawn card 40 (fast-forward before close) and card 35's no-retry rule (R4).

## History

```toml
history = [
  { seq = 1, at = "2026-10-25T21:44:34Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "depends_on", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:f97c3526a3546bcbe0983a5bf64d8a18aee4c48cbfcb70fa46a79d56e7fca2e1", h = "sha256:63d0c61af4da5bd4b401f5c2bb87097dff7c9a72c50b7a30039ccd0392adcae9" },
  { seq = 2, at = "2026-10-26T13:43:32Z", by = "amodal1@users.noreply.github.com", act = "ratified", fields = ["status"], build = "sha256:f97c3526a3546bcbe0983a5bf64d8a18aee4c48cbfcb70fa46a79d56e7fca2e1", h = "sha256:73138aba2a0c18af7e0aa499da4de69761c9774663024fe39d5a4068218daec7", batch = 73 },
]
```
