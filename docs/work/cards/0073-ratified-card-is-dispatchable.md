```toml
schema = 1
id = 73
kind = "story"
status = "draft"
source = "session"
title = "A signed card is dispatchable without a hand land"
shape = "bdd"
effort = "default"
refs = ["packages/isidium-store/src/isidium/store/server/store.py::land", "packages/isidium-factory/src/isidium/factory/dispatch.py"]
surfaces = ["packages/isidium-factory/src/isidium/factory/dispatch.py", "tests/factory/test_ratified_dispatchable.py"]
priority = "P1"

[narrative]
feature = "after a ratification, the next dispatch sees the card as ready"

[[rules]]
id = "R1"
text = "`dispatch` lands an empty report before it reads the ready-view when a ratification is newer than the landed state, so a card the board reads `ratified (pending-ingest)` is picked, and the refusal dispatch.not-ready is kept for a card that is truly not ready"

[[guidance.constraints]]
id = "C9"
text = "every file the card changes passes ruff check, ruff format --check and mypy --strict, by path"
because = "r-38 and r-39 each lost a whole run to a one-line style miss"

[[guidance.constraints]]
id = "C8"
text = "no scenario passes by skipping"
because = "card 61's rule"

[[acceptance.scenarios]]
id = "S1"
kind = "test-marker"
title = "a card signed after the last land is picked by dispatch --card"
rule = "R1"
observable = { test = "tests/factory/test_ratified_dispatchable.py::test_a_pending_ingest_card_is_dispatched" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "a draft card is still refused dispatch.not-ready"
rule = "R1"
observable = { test = "tests/factory/test_ratified_dispatchable.py::test_a_draft_card_is_still_refused" }
```

## Scope

Found 2026-10-29 on card 65: after `ratify --sign` the board read 'ratified (pending-ingest)' and `dispatch --card 65` refused dispatch.not-ready until an empty report was landed by hand with `isidium-factory land`. The same hand land was needed to unwedge governed writes after PR #119 (card 62's defect). Interacts with card 62; does not replace it.

## History

```toml
history = [
  { seq = 1, at = "2026-10-29T21:06:55Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:8a1e7b18f74de55919c1798052890b13e746604d49799fe41385aaa47f55acfe", h = "sha256:459b7ffd752adfaec528375066a12c36d34a82c012676c092ff485bb6d3dd468" },
]
```
