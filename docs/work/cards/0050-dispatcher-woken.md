```toml
schema = 1
id = 50
kind = "story"
status = "ratified"
source = "session"
title = "The witness wakes the dispatcher when the line is free; the dispatcher checks its signed cap, picks, and wakes the run"
shape = "bdd"
depends_on = [46, 49]
effort = "default"
refs = ["packages/isidium-factory/src/isidium/factory/dispatch.py", "packages/isidium-factory/src/isidium/factory/cli.py", "packages/isidium-factory/src/isidium/factory/watch.py", "packages/isidium-store/src/isidium/store/registry/schemas/config@8.toml", "packages/isidium-store/src/isidium/store/registry/config.py"]
surfaces = ["packages/isidium-factory/src/isidium/factory/dispatch.py", "packages/isidium-factory/src/isidium/factory/cli.py", "packages/isidium-factory/src/isidium/factory/watch.py", "packages/isidium-store/src/isidium/store/registry/schemas/config@9.toml", "packages/isidium-store/src/isidium/store/registry/config.py", "docs/design/04-config-schema.md", "tests/factory/test_dispatcher_woken.py", "tests/store/test_config9.py", "tests/unit/test_lazy_registry.py", "tests/unit/test_registry.py", "tests/store/test_k6.py", "tests/store/test_k10.py", "tests/store/test_v3.py", "tests/store/test_k7b.py", "tests/store/test_verify_chain.py", "tests/store/test_config7.py", "tests/store/test_config8.py", "tests/factory/test_v1.py", "tools/mutations/dispatcher.toml"]
priority = "P1"

[narrative]
feature = "a signed, ready card goes to build without anyone dispatching or launching it"

[[rules]]
id = "R1"
text = "config@9 renames [watcher] to [line] and gives it fixup, fixup_per_day, dispatch (bool, default false) and dispatch_per_day (an integer of at least 0, default 0); a config@8 tenant's [watcher] is still read, with dispatch off"

[[rules]]
id = "R2"
text = "a witness pass with no run in flight reads the store's dispatch view; when it holds a ready card and no line-free observation exists for that ready set, it writes one and calls launcher.wake(dispatch)"

[[rules]]
id = "R3"
text = "`dispatch --next` checks [line].dispatch and that fewer runs than dispatch_per_day were dispatched since the day's start (UTC), consumes the line-free observation, picks through dispatch.pick (WIP, depends_on, software-grade and ranking unchanged), and calls launcher.wake(run, r-N) to start the run's chain; past the cap or with dispatch off it consumes the observation and does nothing"

[[rules]]
id = "R4"
text = "a refused pick (dispatch.software-grade, dispatch.wip and the rest) consumes the observation and is recorded; it is not retried until the ready set changes"

[[guidance.avoid]]
id = "A1"
option = "the witness checking the cap or picking"
because = "the owner, 2026-10-23/25 (the actor design, chunk plan): spend guards 'By the spending actor'; the witness wakes, the dispatcher decides"

[[guidance.avoid]]
id = "A2"
option = "the ending run starting the next card"
because = "the owner, 2026-10-23/25 (the actor design, chunk plan): 'The witness sees it, wakes the dispatcher'"

[[guidance.constraints]]
id = "C1"
text = "every pin card 27 moved for config@8 moves for config@9 (this card's surfaces; test_v1's GOLDEN gains a schema-8 arm with the old value); readers of [watcher] (watch.Policy and the run's fixup cap) read [line] at config@9"
because = "checked when filing: commit 10c2cf0 (card 27, #106)"

[[guidance.constraints]]
id = "C2"
text = "the daily count is every run dispatched since the day's start, the operator's included, from runs.dispatched_at; the reason is written at the site"
because = "the ledger records no invoker on a run"

[[guidance.constraints]]
id = "C3"
text = "tools/mutations/dispatcher.toml commits a mutation for R3's cap and one for R2's no-run-in-flight condition; each kill is checked against this card's own test file only; tools/mutate.py is --show only"
because = "the card-writing checklist"

[[guidance.constraints]]
id = "C4"
text = "the idle pass with nothing in flight now reads the store's dispatch view once (lazy otherwise: no context.load, no forge); the reason and its cost are written at the site"
because = "card 37 (C-13)"

[[guidance.constraints]]
id = "C5"
text = "docs/design/04-config-schema.md gains config@9's row; docs/ is CRLF"
because = "AGENTS.md"

[[guidance.constraints]]
id = "C6"
text = "refusals use the dispatch., run. and config. namespaces"
because = "core/disclosure.py stays untouched"

[[guidance.constraints]]
id = "C9"
text = "every file this card changes passes ruff check, ruff format --check and mypy --strict, by path"
because = "r-38 and r-39 each lost a whole run to a one-line style miss"

[[acceptance.scenarios]]
id = "S1"
kind = "test-marker"
title = "config@9 renames the table and adds the dispatch keys"
rule = "R1"
observable = { test = "tests/factory/test_dispatcher_woken.py::test_config9_renames_the_table_and_adds_dispatch" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "a free line with a ready card is observed and the dispatcher woken"
rule = "R2"
observable = { test = "tests/factory/test_dispatcher_woken.py::test_a_free_line_wakes_the_dispatcher" }

[[acceptance.scenarios]]
id = "S3"
kind = "test-marker"
title = "the dispatcher picks under its cap and wakes the run"
rule = "R3"
observable = { test = "tests/factory/test_dispatcher_woken.py::test_the_dispatcher_picks_under_its_cap" }

[[acceptance.scenarios]]
id = "S4"
kind = "test-marker"
title = "past the cap or with dispatch off nothing is picked"
rule = "R3"
observable = { test = "tests/factory/test_dispatcher_woken.py::test_past_the_cap_nothing_is_picked" }

[[acceptance.scenarios]]
id = "S5"
kind = "test-marker"
title = "a refused pick consumes the observation"
rule = "R4"
observable = { test = "tests/factory/test_dispatcher_woken.py::test_a_refused_pick_consumes_the_observation" }
```

## Scope

Ruled [owner, 2026-10-07/23/25]: 'Dependencies + dispatcher'; 'Separate run task'; 'Signed opt-in + daily cap'; 'The witness sees it, wakes the dispatcher'; 'By the spending actor'; the signed table 'renamed in a later schema'. Supersedes withdrawn cards 44 and 45. depends_on keeps prerequisites first, in the store.

## History

```toml
history = [
  { seq = 1, at = "2026-10-25T21:44:49Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "depends_on", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:9eb95f04d5f46dd0f4bd1bc7a29e6dcaea3c21cb91960e5a27e6088538499f65", h = "sha256:8c62ccfc60f12cd143d3bd49b64d8f07e4f4bde013056117791f538428cc01b0" },
  { seq = 2, at = "2026-10-26T13:43:32Z", by = "amodal1@users.noreply.github.com", act = "ratified", fields = ["status"], build = "sha256:9eb95f04d5f46dd0f4bd1bc7a29e6dcaea3c21cb91960e5a27e6088538499f65", h = "sha256:e59267ca4988b76243786bbe6642fe7e5c52167c3ab97be892c853d6516a877e", batch = 73 },
]
```
