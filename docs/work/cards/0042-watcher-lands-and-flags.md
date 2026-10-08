```toml
schema = 1
id = 42
kind = "story"
status = "draft"
source = "session"
title = "The PR watcher lands what the store holds unlanded, and flags a store image or schema registry that is behind"
shape = "bdd"
depends_on = [40]
effort = "default"
refs = ["packages/isidium-store/src/isidium/store/server/store.py", "packages/isidium-store/src/isidium/store/server/api.py", "packages/isidium-factory/src/isidium/factory/watch.py", "packages/isidium-factory/src/isidium/factory/cli.py", "packages/isidium-factory/src/isidium/factory/lander.py", "packages/isidium-factory/src/isidium/factory/dispatch.py"]
surfaces = ["packages/isidium-store/src/isidium/store/server/store.py", "packages/isidium-store/src/isidium/store/server/api.py", "packages/isidium-factory/src/isidium/factory/watch.py", "packages/isidium-factory/src/isidium/factory/cli.py", "tests/factory/test_watch_lands_and_flags.py", "tests/factory/test_watch_idle_pass.py", "tests/factory/test_watch.py", "tests/store/test_queue_counts_pending_ingest.py"]
priority = "P1"

[narrative]
feature = "a signed card becomes dispatchable and a merge becomes landed without anyone running an empty land by hand"

[[rules]]
id = "R1"
text = "the store's queue view gains pending_ingest: the number of cards whose newest signed act is not yet ingested (the label ratified (pending-ingest)), beside merged_not_landed"

[[rules]]
id = "R2"
text = "every pass, before its idle check, reads the queue (one lander call); when merged_not_landed or pending_ingest is above zero it sends one empty-report land, the same call `isidium-factory land` makes, and logs it"

[[rules]]
id = "R3"
text = "a pass flags store-behind when the store's dispatch view carries no in_flight key (dispatch.store-behind's test), and registry-behind when the checkout's installed registry lacks the config schema the working tree's config.toml adopts (the hook's registry_current, without a fetch); each flag is logged once per kind until it clears"

[[rules]]
id = "R4"
text = "an idle pass stays lazy: the queue read and the land are the only store calls it adds; it still never calls context.load or the forge"

[[guidance.avoid]]
id = "A1"
option = "landing on every pass whatever the queue says"
because = "the store's land syncs to main and walks the range each time (store.py:1374-1492); only a land with something to land is worth that"

[[guidance.avoid]]
id = "A2"
option = "swapping the store image or running isidium install from the watcher"
because = "a store swap was refused as a production deploy and is the owner's; the watcher flags, it does not deploy"

[[guidance.constraints]]
id = "C1"
text = "tenant-level flags (store-behind, registry-behind) are watch.jsonl entries with an empty run id and the store or checkout as the head field; FlagKind gains the two kinds; decide's signature is unchanged"
because = "checked when filing: test_watch.py:632 pins decide's parameters; Flag requires run_id and head"

[[guidance.constraints]]
id = "C2"
text = "test_watch_idle_pass.py's idle home gains what the queue read needs (or the read is injected), and its assertions that the idle pass never loads the context or the forge are kept"
because = "checked when filing: the idle home has no client certificate and a store call raises client.channel"

[[guidance.constraints]]
id = "C3"
text = "refusals stay in existing namespaces (dispatch, hook, run, land); no new namespace"
because = "core/disclosure.py stays untouched"

[[guidance.constraints]]
id = "C4"
text = "the reason for the per-pass queue read is written at the site with its cost (C-13)"
because = "card 37 made the idle pass lazy; this adds one call back, with the reason"

[[guidance.constraints]]
id = "C9"
text = "every file this card changes passes ruff check, ruff format --check and mypy --strict, by path"
because = "r-38 and r-39 each lost a whole run to a one-line style miss"

[[acceptance.scenarios]]
id = "S1"
kind = "test-marker"
title = "a pass lands when a merge is unlanded"
rule = "R2"
observable = { test = "tests/factory/test_watch_lands_and_flags.py::test_a_pass_lands_when_a_merge_is_unlanded" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "a pass lands when a signed card is not ingested"
rule = "R2"
observable = { test = "tests/factory/test_watch_lands_and_flags.py::test_a_pass_lands_when_a_card_is_pending_ingest" }

[[acceptance.scenarios]]
id = "S3"
kind = "test-marker"
title = "nothing to land, no land"
rule = "R2"
observable = { test = "tests/factory/test_watch_lands_and_flags.py::test_nothing_to_land_no_land" }

[[acceptance.scenarios]]
id = "S4"
kind = "test-marker"
title = "store-behind and registry-behind are flagged once"
rule = "R3"
observable = { test = "tests/factory/test_watch_lands_and_flags.py::test_store_and_registry_behind_are_flagged_once" }

[[acceptance.scenarios]]
id = "S5"
kind = "test-marker"
title = "an idle pass still never loads the context"
rule = "R4"
observable = { test = "tests/factory/test_watch_lands_and_flags.py::test_an_idle_pass_still_never_loads_the_context" }

[[acceptance.scenarios]]
id = "S6"
kind = "test-marker"
title = "the queue counts pending-ingest cards"
rule = "R1"
observable = { test = "tests/store/test_queue_counts_pending_ingest.py::test_the_queue_counts_pending_ingest_cards" }
```

## Scope

Ruled [owner, 2026-10-07]: 'Watcher lands + flags'. Today every signature and every merge needs a hand empty-report land before dispatch or a card write works (dispatch.pending-land, git.push-rejected), and a store image or registry that is behind surfaces only as a refusal mid-operation (dispatch.store-behind, hook.registry-behind). Surveyed: show queue has merged_not_landed but no pending-ingest count.

## History

```toml
history = [
  { seq = 1, at = "2026-10-08T01:37:45Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "depends_on", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:8a618f4aca499316529f15d4147fd5124a8b1aaec6953421cbd8156a8a3f777c", h = "sha256:d5606f6a98be321902f988a4735d42ef196ea5f955edd040ab34f5c2c80f2910" },
]
```
