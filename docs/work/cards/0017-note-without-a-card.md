```toml
schema = 1
id = 17
kind = "story"
status = "draft"
source = "session"
title = "Accepting a suggestion as a note on a suggestion that names no card is refused by its own rule, and nothing is written"
shape = "bdd"
effort = "default"
refs = ["packages/isidium-store/src/isidium/store/server/store.py::Store", "packages/isidium-store/src/isidium/store/core/disclosure.py"]
surfaces = ["packages/isidium-store/src/isidium/store/server/store.py", "packages/isidium-store/src/isidium/store/core/disclosure.py", "tests/store/test_note_without_a_card.py"]
priority = "P3"

[narrative]
feature = "the owner told why a note could not be filed gets a refusal that says so, instead of a generic arguments refusal hiding a crash"

[[rules]]
id = "R1"
text = "A disposition accepted as a note on a suggestion with no proposed_for is refused inbox.note-no-card, naming the suggestion"

[[rules]]
id = "R2"
text = "The refused disposition writes nothing: no card update and no disposition record"

[[rules]]
id = "R3"
text = "A disposition accepted as a note on a suggestion with a proposed_for notes that card, as it does today"

[[guidance.constraints]]
id = "C1"
text = "the new rule id is declared in disclosure.py's table with its status and disclosure, as every rule id is"
because = "the table spells every id so a new one cannot reach a caller undeclared"

[[guidance.constraints]]
id = "C2"
text = "the check happens before any write in the disposition"
because = "a disposition is one gesture; a half-applied one leaves a record the inbox cannot explain"

[[acceptance.scenarios]]
id = "S1"
kind = "test-marker"
title = "a note on a suggestion naming no card is refused by its own rule"
rule = "R1"
observable = { test = "tests/store/test_note_without_a_card.py::test_a_note_naming_no_card_is_refused_by_its_own_rule" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "the refused disposition writes nothing"
rule = "R2"
observable = { test = "tests/store/test_note_without_a_card.py::test_the_refused_disposition_writes_nothing" }

[[acceptance.scenarios]]
id = "S3"
kind = "test-marker"
title = "a note on a suggestion with a card still notes it"
rule = "R3"
observable = { test = "tests/store/test_note_without_a_card.py::test_a_note_with_a_card_still_notes_it" }
```

## Scope

Found on 2026-09-23. Accepting a suggestion as a note when the suggestion has no proposed_for raised KeyError at Store.disposition (store.py:2246, int(intake["proposed_for"])), which reached the owner as a generic service.arguments refusal.

In scope: the typed refusal, writing nothing when refused, keeping today's behavior for a suggestion that names a card, and the tests.

Not in scope: letting the owner name the card at disposition time. That adds an argument to the verb, the API and the generated tool schema, and would be its own card if wanted. Swapping the store image after the merge is operational work.

## History

```toml
history = [
  { seq = 1, at = "2026-09-24T21:21:24Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:92bf8dfb77020d6ccf3cb20b18798ae43b81ef7e0a0bc69ffc70be3b83065b4d", h = "sha256:98e058ae7f0d56de8c93d6e8c2a3357d5edb143c22d4c9ca0b869fcde8177e75" },
]
```
