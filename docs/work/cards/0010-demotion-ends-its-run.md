```toml
schema = 1
id = 10
kind = "story"
status = "ratified"
source = "session"
title = "A demotion that ends a run in flight is a signed act, so the sidecar hears it"
shape = "bdd"
effort = "default"
refs = ["packages/isidium-store/src/isidium/store/core/derive.py::needs_signature", "packages/isidium-store/src/isidium/store/server/store.py"]
surfaces = ["packages/isidium-store/src/isidium/store/core/derive.py", "packages/isidium-store/src/isidium/store/server/store.py", "tests/store/test_demotion_ends_its_run.py"]
priority = "P1"

[narrative]
feature = "the gesture that takes a dispatched run's reason away is one the store observes, so a card and its run can never disagree about whether work is still in flight"

[[rules]]
id = "R1"
text = "A demotion of a card whose sidecar holds a run in flight needs a signature, whatever else the write touches, so the land that walks it abandons the run"

[[rules]]
id = "R2"
text = "A demotion of a card with nothing in flight needs no signature, as a retreat from ratified never has"

[[acceptance.scenarios]]
id = "S1"
kind = "test-marker"
title = "a bare demotion of a card with a run in flight is signed"
rule = "R1"
observable = { test = "tests/store/test_demotion_ends_its_run.py::test_a_bare_demotion_with_a_run_in_flight_is_signed" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "that demotion, landed, abandons the run in the sidecar"
rule = "R1"
observable = { test = "tests/store/test_demotion_ends_its_run.py::test_the_landed_demotion_abandons_the_run" }

[[acceptance.scenarios]]
id = "S3"
kind = "test-marker"
title = "a demotion with nothing in flight stays unsigned"
rule = "R2"
observable = { test = "tests/store/test_demotion_ends_its_run.py::test_a_demotion_with_nothing_in_flight_stays_unsigned" }
```

## Scope

Found live on this tenant on 2026-09-22, in the wreckage of `r-9`. A red gate left card 9's run with no
way to end but a demotion, the card was demoted back to draft, and `close --run r-9` ended it `abandoned` — correctly,
since `close` reads the card's status (`ABANDONING = {"withdrawn", "draft"}`) before it ever looks at the pull
request. The store never heard. Card 9's sidecar still read `execution: dispatched`, `runs: []`, hours after the run
was over.

Two readers of one chain disagree about the same entry. `derive.replay_status` honours an unsigned `demoted` act —
which is why the board rendered card 9 as a draft and why `close` was right to abandon its run. `Store._card_events`
does not: it gates every act event on `chain.is_signed(e)`, and `derive.needs_signature` has no rule for
`ratified → draft`, a retreat from ratified being free by design. So the act moved the card's status for one reader
and emitted nothing for the other, and the sidecar kept a run in flight that had already ended.

What that costs is not cosmetic. The fold clears a stale execution on a re-ratification only when it reads `failed`
or `abandoned` (card 7 R3). A card stranded this way reads `dispatched` for ever: re-ratifying it does not return it
to the ready-view, `dispatch --card N` answers `dispatch.not-ready`, and the WIP cap stays pinned by a run that
ended hours ago. Card 9 was stranded exactly so, and nothing in the board, the queue or the ledger said why.

The door that does work is the one `tests/store/test_fold_abandons.py` documents and exercises: a demotion carrying a
gated edit alongside the status flip is signed by `gated-on-ratified`, is observed at the land, and does abandon the
run. That is how card 9 was freed — and it proved card 7 R1's demotion half live for the first time, `e30`, the
sidecar's `runs[]` naming `r-9` abandoned. But it is a trap dressed as a workaround: the owner's natural gesture,
demoting a card to take a stuck run's reason away, is the one that silently fails, and only the gesture that happens
to edit something else succeeds.

In scope: a demotion of a card whose sidecar says a run is in flight is a signed act, whatever else the write
touches — the reason plumbed to `derive.needs_signature` the way `landed_closures` already is, the caller computing
the fact it holds; and tests pinning the signature, the landed abandon, and the free retreat where nothing is in
flight.

Not in scope: the signature predicate's rule for every other retreat, which stays free; `close`'s abandon branch,
which lands nothing by design and is right not to — the store learns a card act from the card's own chain, never
from the factory's say-so; the withdrawal path, already signed and already observed; a new event kind, since
`demoted` is in `sidecar-events@3` and the fold's rule is on `main`; whether a red gate should be able to end its run
as `failed:gate` without a demotion at all, which is the owner's open question and a larger change; and rescuing a
card already stranded — the walk emits only for entries newer than the sidecar's `history_head`, so no fix reaches
backwards, and the remedy for one is the gated-edit demotion above.

## History

```toml
history = [
  { seq = 1, at = "2026-09-22T19:49:50Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "effort", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:ad158965f6a951b5954b6d099648cb8c759882c6199da2088c2fe9512a86fdda", h = "sha256:2e892cd3b56aee006a73e942521a79e1e3082ecc9433382c7ca2052e820ec4be", batch = 20 },
]
```
