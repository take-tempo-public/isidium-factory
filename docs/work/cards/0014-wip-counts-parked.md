```toml
schema = 1
id = 14
kind = "story"
status = "ratified"
source = "session"
title = "The dispatcher's WIP cap counts the cards the store holds in flight, so a parked card holds the line"
shape = "bdd"
effort = "default"
refs = ["packages/isidium-store/src/isidium/store/server/store.py::Store", "packages/isidium-factory/src/isidium/factory/dispatch.py::_pick", "packages/isidium-store/src/isidium/store/core/events.py::fold"]
surfaces = ["packages/isidium-store/src/isidium/store/server/store.py", "packages/isidium-factory/src/isidium/factory/dispatch.py", "tests/factory/test_dispatch_counts_parked.py"]
priority = "P2"

[narrative]
feature = "the line does not take another card while one waits on the owner's answer, because the cap counts what the board counts"

[[rules]]
id = "R1"
text = "The store's dispatch answer names every card whose execution is in the in-flight set, with that card's execution"

[[rules]]
id = "R2"
text = "The pick refuses dispatch.wip when the cards the store names in flight, together with the cards of any run the ledger holds unended, number at the cap; a card named by both is counted once"

[[rules]]
id = "R3"
text = "The refusal names each card counted and why: the ledger's run id, the store's execution, or both"

[[rules]]
id = "R4"
text = "A store answer without the in-flight names is refused before anything is picked or written, naming the store as behind"

[[guidance.avoid]]
id = "A1"
option = "the factory deriving the in-flight set itself from the sidecar or the event file"
because = "events.IN_FLIGHT is the set's one home and the store's projection already reads it; a second derivation is a second home"

[[guidance.constraints]]
id = "C1"
text = "the in-flight names ride the dispatch call the pick already makes, with no second call"
because = "the pick's store reads are one call by design (Store.dispatch's docstring), under the lander's grant"

[[guidance.constraints]]
id = "C2"
text = "the ledger's unended runs still count"
because = "a run dispatched but not yet landed is in flight on the ledger before the store hears it"

[[acceptance.scenarios]]
id = "S1"
kind = "test-marker"
title = "the store names a parked card in flight"
rule = "R1"
observable = { test = "tests/factory/test_dispatch_counts_parked.py::test_the_store_names_a_parked_card_in_flight" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "a parked card holds the cap although its run has ended on the ledger"
rule = "R2"
observable = { test = "tests/factory/test_dispatch_counts_parked.py::test_a_parked_card_holds_the_cap" }

[[acceptance.scenarios]]
id = "S3"
kind = "test-marker"
title = "a dispatched run counted by both is counted once"
rule = "R2"
observable = { test = "tests/factory/test_dispatch_counts_parked.py::test_a_run_counted_by_both_is_counted_once" }

[[acceptance.scenarios]]
id = "S4"
kind = "test-marker"
title = "the refusal names each card and why it counts"
rule = "R3"
observable = { test = "tests/factory/test_dispatch_counts_parked.py::test_the_refusal_names_each_card_and_why" }

[[acceptance.scenarios]]
id = "S5"
kind = "test-marker"
title = "a store behind is refused before the pick"
rule = "R4"
observable = { test = "tests/factory/test_dispatch_counts_parked.py::test_a_store_behind_is_refused_before_the_pick" }
```

## Scope

Found on 2026-09-24. The dispatcher's WIP cap counts ledger.in_flight(), the runs with no end (dispatch.py:100). A parked run has ended on the ledger, so while r-13 was parked the line could have taken another card, but the board counted card 12 as WIP. The owner ruled that a parked card holds the line's WIP.

In scope: the store's dispatch answer naming the cards in flight, the pick counting them together with the ledger's unended runs, the refusal's wording, and the tests.

Not in scope: what a parked card's question becomes when the owner answers it (the fold's own card) and re-dispatch after an answer (V6). Swapping the store image after the merge is operational work, and the store must be swapped before this factory is used.

## History

```toml
history = [
  { seq = 1, at = "2026-09-24T21:21:05Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:954ba04c1fb256a29742ce798b6ec40229c0bf20737498cad4cc57832ad9014e", h = "sha256:b49efb54eddd01784fd38f29c2145bc1c2a1c0162d9954548814f3ae547e0f00" },
  { seq = 2, at = "2026-09-24T21:22:41Z", by = "amodal1@users.noreply.github.com", act = "ratified", fields = ["status"], build = "sha256:954ba04c1fb256a29742ce798b6ec40229c0bf20737498cad4cc57832ad9014e", h = "sha256:3a47f0cc069112e42e1393ec4b92b47fc4f12cec8dcfe196f32b63f90eae9b6f", batch = 26 },
  { seq = 3, at = "2026-09-26T03:57:27Z", by = "amodal1@users.noreply.github.com", act = "demoted", fields = ["status"], build = "sha256:954ba04c1fb256a29742ce798b6ec40229c0bf20737498cad4cc57832ad9014e", h = "sha256:1fd45c0f57227fc47a9241572eefb0ae2ddbcf6524c3e5e0374603e466c860b9" },
  { seq = 4, at = "2026-09-26T03:58:07Z", by = "amodal1@users.noreply.github.com", act = "ratified", fields = ["status"], build = "sha256:954ba04c1fb256a29742ce798b6ec40229c0bf20737498cad4cc57832ad9014e", h = "sha256:9959f5c350195356a3589f649eea2fd27e98856be134e9b060302e8b1199f5c9", batch = 30 },
  { seq = 5, at = "2026-09-26T05:17:33Z", by = "amodal1@users.noreply.github.com", act = "demoted", fields = ["status"], build = "sha256:954ba04c1fb256a29742ce798b6ec40229c0bf20737498cad4cc57832ad9014e", h = "sha256:59b2a453a7a6564a0f7dbd23bebb80baa0397e6e18806b9ba250cad79ad98d29" },
  { seq = 6, at = "2026-09-26T05:18:16Z", by = "amodal1@users.noreply.github.com", act = "ratified", fields = ["status"], build = "sha256:954ba04c1fb256a29742ce798b6ec40229c0bf20737498cad4cc57832ad9014e", h = "sha256:c58e5768bfea72fe85a8a52b6298b55a8680d1fc41ef7ab7b4f5be0797ebc431", batch = 31 },
]
```
