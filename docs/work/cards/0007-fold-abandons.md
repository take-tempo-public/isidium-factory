```toml
schema = 1
id = 7
kind = "story"
status = "ratified"
source = "planner"
title = "The fold records an abandoned run when a card with a run in flight is withdrawn or demoted"
shape = "bdd"
effort = "default"
refs = ["packages/isidium-store/src/isidium/store/core/events.py::fold", "packages/isidium-store/src/isidium/store/core/status.py:311-357", "packages/isidium-store/src/isidium/store/core/board.py:90-102", "packages/isidium-store/src/isidium/store/core/neighborhood.py:125-133", "packages/isidium-store/src/isidium/store/server/store.py:1700-1710", "docs/design/03-card-schema.md:641-664", "tests/store/test_l4.py::test_a_withdrawal_of_a_dispatched_card_is_the_ledgers_own_transition_once", "tests/store/test_l1.py::test_the_fold_is_pure_and_idempotent", "tools/mutate.py:79-89"]
surfaces = ["packages/isidium-store/src/isidium/store/core/events.py", "packages/isidium-store/src/isidium/store/core/status.py", "packages/isidium-store/src/isidium/store/core/board.py", "packages/isidium-store/src/isidium/store/core/neighborhood.py", "packages/isidium-store/src/isidium/store/server/store.py", "docs/design/03-card-schema.md", "tests/store/"]
priority = "P2"

[narrative]
feature = "when the owner withdraws or demotes a card while a run is in flight, the sidecar records the run as abandoned instead of saying for ever that it is dispatched, and a card re-ratified after that can be dispatched again"

[[rules]]
id = "R1"
text = "A withdrawn or demoted event on a card whose execution is in flight (dispatched, parked or answered) sets execution to abandoned"

[[rules]]
id = "R2"
text = "The same event appends a runs[] entry {run_id, outcome: abandoned, ended_at}: run_id from the card's last dispatched event, ended_at the withdrawn or demoted event's at"

[[rules]]
id = "R3"
text = "abandoned is a typed execution state that gives no label of its own: the label comes from the card's status, so a withdrawn card reads withdrawn, a demoted card reads draft, and a card re-ratified after its run was abandoned reads ratified and is ready"

[[rules]]
id = "R4"
text = "On a card with nothing in flight a withdrawn or demoted event changes neither execution nor runs[]"

[[rules]]
id = "R5"
text = "The in-flight set is declared once, and every site that asks whether a run is in flight reads it: the fold, the land's act events, the board's WIP count and the neighborhood block"

[[guidance.avoid]]
id = "A1"
option = "editing the factory package's ledger or close"
because = "the factory's own abandoned outcome is already built (ledger.py ABANDONED, used by close); this card is the store's half"

[[guidance.risks]]
id = "K1"
risk = "folding complete into the shared in-flight constant"
mitigation = "the constant is dispatched, parked and answered only; the board's WIP count and the neighborhood block add complete on top, as they do today, or a withdrawal of a completed card would abandon a run that already finished"

[[guidance.constraints]]
id = "C1"
text = "the fold stays pure: the same events give the same bytes, with no clock, no reads and no state kept between calls; the run id is carried within the one pass"
because = "landing the same cursor twice must produce identical bytes"
check = { kind = "test-marker", observable = { test = "tests/store/test_l1.py::test_the_fold_is_pure_and_idempotent" } }

[[guidance.constraints]]
id = "C2"
text = "run the store tests with -n 2 --dist loadfile, never plain -n 2"
because = "tests/store/test_scenarios.py shares state across its own tests and five of them fail when split across workers (tools/mutate.py)"

[[guidance.constraints]]
id = "C3"
text = "no registry schema document moves"
because = "sidecar@2 declares cards as an open table keyed by card number with no shape for execution or runs[], and no schema document declares the execution states"

[[acceptance.scenarios]]
id = "S1"
kind = "test-marker"
title = "a withdrawal of a dispatched card folds to abandoned"
rule = "R1"
observable = { test = "tests/store/test_fold_abandons.py::test_a_withdrawn_dispatched_card_folds_to_abandoned" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "a demotion of a dispatched card folds to abandoned"
rule = "R1"
observable = { test = "tests/store/test_fold_abandons.py::test_a_demoted_dispatched_card_folds_to_abandoned" }

[[acceptance.scenarios]]
id = "S3"
kind = "test-marker"
title = "runs[] records the abandoned run by its id and end time"
rule = "R2"
observable = { test = "tests/store/test_fold_abandons.py::test_runs_records_the_abandoned_run" }

[[acceptance.scenarios]]
id = "S4"
kind = "test-marker"
title = "abandoned is typed and gives no label of its own"
rule = "R3"
observable = { test = "tests/store/test_fold_abandons.py::test_abandoned_is_typed_and_the_label_comes_from_status" }

[[acceptance.scenarios]]
id = "S5"
kind = "test-marker"
title = "a card re-ratified after its run was abandoned is ready"
rule = "R3"
observable = { test = "tests/store/test_fold_abandons.py::test_a_reratified_abandoned_card_is_ready" }

[[acceptance.scenarios]]
id = "S6"
kind = "test-marker"
title = "nothing in flight, nothing abandoned"
rule = "R4"
observable = { test = "tests/store/test_fold_abandons.py::test_nothing_in_flight_nothing_abandoned" }

[[acceptance.scenarios]]
id = "S7"
kind = "test-marker"
title = "the board's WIP count drops when a dispatched card is withdrawn"
rule = "R1"
observable = { test = "tests/store/test_fold_abandons.py::test_withdrawing_a_dispatched_card_frees_its_wip" }

[[acceptance.scenarios]]
id = "S8"
kind = "test-marker"
title = "the in-flight set has one home"
rule = "R5"
observable = { test = "tests/store/test_fold_abandons.py::test_the_in_flight_set_has_one_home" }
```

## Scope

When a card is withdrawn or demoted while a run is in flight on it, the store's fold records that run as abandoned: the card's `execution` becomes `abandoned`, and its `runs[]` gains an entry naming the abandoned run. In scope: the fold, the projection's typed execution state, and the card schema's text for the new state. Not in scope: the factory ledger's own `abandoned` outcome (it already exists), any other execution state, re-dispatching an abandoned card, and the per-agent allowlist planned for config@7. Also in scope: one in-flight set that the land's act events, the board's WIP count and the neighborhood block read, and a card re-ratified after its run was abandoned reading ratified and ready.

## History

```toml
history = [
  { seq = 1, at = "2026-09-14T22:56:26Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:460e30bea4fef30fa8403bdd26b7e0713379e99c3e90c358b5b9aea67a22edd0", h = "sha256:8c4776131d954dc3184f98b6963bd928f995e71a627b5e641d0cf8c03864f609", batch = 11 },
  { seq = 2, at = "2026-09-15T05:28:51Z", by = "amodal1@users.noreply.github.com", act = "demoted", fields = ["status"], build = "sha256:460e30bea4fef30fa8403bdd26b7e0713379e99c3e90c358b5b9aea67a22edd0", h = "sha256:c43ce317d310a0dc92ec98f5add7a8187aa1fff28afb4d0bd52cd78adcb86d31" },
  { seq = 3, at = "2026-09-15T05:29:21Z", by = "amodal1@users.noreply.github.com", act = "ratified", fields = ["status"], build = "sha256:460e30bea4fef30fa8403bdd26b7e0713379e99c3e90c358b5b9aea67a22edd0", h = "sha256:a32021179599d4d5a1eca67b7c92318977806ced9ccc075d7277d0a0e52e02ba", batch = 13 },
  { seq = 4, at = "2026-09-15T19:25:40Z", by = "amodal1@users.noreply.github.com", act = "demoted", fields = ["status"], build = "sha256:460e30bea4fef30fa8403bdd26b7e0713379e99c3e90c358b5b9aea67a22edd0", h = "sha256:bb3d97c2195aa9c27dcd4f514f910fd3522120ddc4691fcd4f2a0407b13ae5e3" },
  { seq = 5, at = "2026-09-15T19:30:19Z", by = "amodal1@users.noreply.github.com", act = "ratified", fields = ["status"], build = "sha256:460e30bea4fef30fa8403bdd26b7e0713379e99c3e90c358b5b9aea67a22edd0", h = "sha256:d77f238b603fe6149cbbb88bc3b14d4d0d2e45cfa61a7d0b59d1ee127945916d", batch = 14 },
]
```
