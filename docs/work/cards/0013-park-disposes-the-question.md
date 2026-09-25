```toml
schema = 1
id = 13
kind = "story"
status = "draft"
source = "session"
title = "A park is a run's end and a question on its card; the owner's response disposes of the question and abandons no run"
shape = "bdd"
effort = "default"
refs = ["packages/isidium-store/src/isidium/store/core/events.py::fold", "tests/store/test_fold_abandons.py"]
surfaces = ["packages/isidium-store/src/isidium/store/core/events.py", "tests/store/test_fold_abandons.py", "tests/store/test_fold_parks.py", "docs/design/03-card-schema.md"]
priority = "P2"

[narrative]
feature = "the sidecar records a parked run as ended parked, the way the ledger does, and records how the owner left its question, so the two records agree about every run"

[[rules]]
id = "R1"
text = "A parked event adds its run to the card's runs as an entry with outcome parked and ended_at the event's time; the run is the event's own run_id, and the card's last dispatched run only when the event names none; the card's execution reads parked"

[[rules]]
id = "R2"
text = "A demoted or withdrawn event on a card whose execution is parked or answered abandons no run: it appends a response {act, card_seq, at}: act the event's kind, card_seq the card entry's seq (required), at the event's time, to the parked run's entry, and the card's execution clears"

[[rules]]
id = "R3"
text = "An answered event on a parked card appends a response with act answered, the card entry's seq as card_seq and the event's time as at, to the parked run's entry; the card's execution reads answered"

[[rules]]
id = "R4"
text = "A demoted or withdrawn event on a card whose execution is dispatched abandons that run, as it does today"

[[rules]]
id = "R5"
text = "A card whose question was left by a demotion reads ready once it is re-ratified"

[[rules]]
id = "R6"
text = "A parked run's responses are appended in order and never rewritten or removed: a later act on the card adds a response after the ones already there, and the first response is the one that disposed of the question"

[[guidance.avoid]]
id = "A1"
option = "re-ending or annotating the parked run in the factory's ledger"
because = "the ledger already holds the run ended parked, which is the truth, and refuses a second end by design (ledger.ended)"

[[guidance.avoid]]
id = "A2"
option = "removing parked or answered from the in-flight set"
because = "the owner ruled that a parked card holds the line's WIP until its question is disposed of; the set has one home and it stays as it is"

[[guidance.constraints]]
id = "C1"
text = "the fold stays pure: the same event file gives the same bytes, and nothing but the events is read"
because = "every land re-folds the whole file, which is also how the tenant's own r-13 entry is corrected once this is deployed"

[[guidance.constraints]]
id = "C2"
text = "test_a_run_in_flight_with_no_dispatched_line_is_abandoned_without_a_run_id changes with R2: a parked card reported alone and then withdrawn records a parked entry with a withdrawn response, not an abandoned one"
because = "that test pins the behavior this card replaces; it is rewritten, not deleted, and keeps its no-run-id case"

[[guidance.constraints]]
id = "C3"
text = "the parked run's entry links to its question by its run_id alone; no question hash is added to the entry or to the parked event"
because = "a run parks at most once, so its run_id names one question.json and the ledger's detail holds that file's hash; the parked event carries no structured hash, and widening it would reach the factory's land path"

[[guidance.constraints]]
id = "C4"
text = "docs/design/03-card-schema.md changes only where it states the behavior this card replaces: §1.5's row 9, the `ratified → draft` and `ratified → withdrawn` transition rows, and §6's `state/history.jsonl` paragraph (an act on a card in flight abandons the run), restated to: only a dispatched run is abandoned; a parked run's entry gains responses"
because = "the design record must not contradict the merged code, and it is owner-ratified: no other line of it is this card's to change"

[[guidance.constraints]]
id = "C5"
text = "an act event that names no seq still appends its response, with the card_seq key omitted, never null and never a raise"
because = "history is preserved regardless and the fold stays pure over any file; the store's own emission always names seq, so card_seq is present on every response the store writes"

[[acceptance.scenarios]]
id = "S1"
kind = "test-marker"
title = "a parked run is recorded as ended parked"
rule = "R1"
observable = { test = "tests/store/test_fold_parks.py::test_a_parked_run_is_recorded_as_ended_parked" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "a demotion of a parked card leaves the question and abandons nothing"
rule = "R2"
observable = { test = "tests/store/test_fold_parks.py::test_a_demotion_of_a_parked_card_leaves_the_question_and_abandons_nothing" }

[[acceptance.scenarios]]
id = "S3"
kind = "test-marker"
title = "a withdrawal of a parked card leaves the question and abandons nothing"
rule = "R2"
observable = { test = "tests/store/test_fold_parks.py::test_a_withdrawal_of_a_parked_card_leaves_the_question_and_abandons_nothing" }

[[acceptance.scenarios]]
id = "S4"
kind = "test-marker"
title = "an answer is recorded on the parked run"
rule = "R3"
observable = { test = "tests/store/test_fold_parks.py::test_an_answer_is_recorded_on_the_parked_run" }

[[acceptance.scenarios]]
id = "S5"
kind = "test-marker"
title = "a demoted dispatched card still folds to abandoned"
rule = "R4"
observable = { test = "tests/store/test_fold_abandons.py::test_a_demoted_dispatched_card_folds_to_abandoned" }

[[acceptance.scenarios]]
id = "S6"
kind = "test-marker"
title = "card 12's own history folds to r-13 parked and its question left by the demotion, then ready"
rule = "R5"
observable = { test = "tests/store/test_fold_parks.py::test_card_12s_history_folds_to_a_parked_run_whose_question_was_left" }

[[acceptance.scenarios]]
id = "S7"
kind = "test-marker"
title = "a park answered and then demoted keeps both responses in order"
rule = "R6"
observable = { test = "tests/store/test_fold_parks.py::test_a_park_answered_then_demoted_keeps_both_responses_in_order" }
```

## Scope

Found on 2026-09-24 with run r-13. It parked at 03:34:21 and the ledger ended it parked. When card 12 was demoted at 14:38:31 to answer that park, the fold recorded r-13 as abandoned, because it treats parked and answered as in flight and a demotion of an in-flight card abandons its run. The ledger and the sidecar now disagree about one run.

The owner ruled the flow: a park ends the run and opens a question on the card. The owner's response (answering it, changing the card, or withdrawing it) disposes of the question and never abandons a run; only a run still dispatched is abandoned. The owner ruled the record's shape (2026-09-25, from r-15's park): history is preserved regardless, so a parked run's entry carries responses appended in order and never rewritten, each {act, card_seq, at} with card_seq required, and it links to its question by its run_id. The fold also never writes a runs entry for a park, so today the demotion's abandoned line is the only trace a parked run leaves.

In scope: the fold recording parked runs and how their questions were left, dispatched runs abandoned as before, the re-ratification path back to ready, and the tests.

Not in scope: re-dispatch after an answer (V6); the dispatcher's WIP count (its own card); handing the question to the next plan (its own card); the factory's ledger. Swapping the store image after the merge is operational work, not part of this card.

## History

```toml
history = [
  { seq = 1, at = "2026-09-24T21:20:58Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:340b5ab4da03b917d427074d72a4a10569e3874a77c2c80c0e756022b7a3210c", h = "sha256:7174f5d124702d2670adf320688fc5ded9a13a6c332224ed785b2dcc2b09e1da" },
  { seq = 2, at = "2026-09-24T21:22:41Z", by = "amodal1@users.noreply.github.com", act = "ratified", fields = ["status"], build = "sha256:340b5ab4da03b917d427074d72a4a10569e3874a77c2c80c0e756022b7a3210c", h = "sha256:9dee2849e404d2a658bc8520c4ac5690ef6845fcd319e6de6dc472320b8cd657", batch = 26 },
  { seq = 3, at = "2026-09-25T17:01:56Z", by = "amodal1@users.noreply.github.com", act = "demoted", fields = ["acceptance", "guidance", "rules", "scope", "status"], build = "sha256:35b165b4e17670e72b4f62e932a064c99938c2a5865ec234f96bbb724467ce5a", h = "sha256:257b6e4553ae000e9f144c478b1342e4b50f50be069b6b0db00a92fc1239dced", sig = "ed25519:5a6c85e20ab2a6eecc5d6df4f873f9af746b98a33d923c3302a900c365984ae8:SYLVJTOfaL9ZAcY3ILgDERG/T/RZDhSRkvQHSsasprIAh5tJhcee7NUm6UGAet4tycYFZchRupr7/XvPlqhlDA==" },
  { seq = 4, at = "2026-09-25T17:03:14Z", by = "amodal1@users.noreply.github.com", act = "ratified", fields = ["status"], build = "sha256:35b165b4e17670e72b4f62e932a064c99938c2a5865ec234f96bbb724467ce5a", h = "sha256:5f41ee3944741882389c575aec381c22950c4bc36f84d0c6634ad50c964d3212", batch = 27 },
  { seq = 5, at = "2026-09-25T20:00:58Z", by = "amodal1@users.noreply.github.com", act = "demoted", fields = ["guidance", "rules", "status", "surfaces"], build = "sha256:72482ece92d1fa3d1130dc12c04c43aa312684899e369bd6c95e08da4cb570e3", h = "sha256:ee9d78ba02b8c7267c836091b5abe02752a422f054199bb3e22313e6e4042ce4", sig = "ed25519:5a6c85e20ab2a6eecc5d6df4f873f9af746b98a33d923c3302a900c365984ae8:A9ERHSqkOv95CLX59gwdDtG12shDb5CFAZM3IZWhKbWBOVtkLWZW+oqLGPbKPoCOzgFdVniY3qnVnggYluNDCA==" },
]
```
