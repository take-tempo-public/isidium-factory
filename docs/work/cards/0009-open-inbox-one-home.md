```toml
schema = 1
id = 9
kind = "story"
status = "ratified"
source = "session"
title = "The open-inbox rule has one home, so the board's inbox count and its inbox list cannot disagree"
shape = "bdd"
effort = "default"
refs = ["packages/isidium-store/src/isidium/store/core/status.py::queue", "packages/isidium-store/src/isidium/store/core/board.py::render"]
surfaces = ["packages/isidium-store/src/isidium/store/core/status.py", "packages/isidium-store/src/isidium/store/core/board.py", "tests/store/"]
priority = "P2"

[narrative]
feature = "the rule that decides whether a suggestion is still open is written once, so BOARD.md's inbox count and its inbox list are always answers to the same question"

[[rules]]
id = "R1"
text = "Which intake records are still open is decided by one function, and both BOARD.md's inbox counts and its rendered inbox list read that one answer"

[[rules]]
id = "R2"
text = "A disposition whose outcome is neither accepted nor declined leaves its intake open in the count and in the list alike"

[[acceptance.scenarios]]
id = "S1"
kind = "test-marker"
title = "the board's inbox list and its inbox counts read one open set"
rule = "R1"
observable = { test = "tests/store/test_open_inbox_one_home.py::test_the_board_list_and_the_inbox_counts_read_one_open_set" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "a deferred disposition leaves its intake open in both"
rule = "R2"
observable = { test = "tests/store/test_open_inbox_one_home.py::test_a_deferred_disposition_leaves_its_intake_open_in_both" }
```

## Scope

Found surveying this tenant's inbox on 2026-09-21. Whether an intake record is still open — an intake with no `accepted` or `declined` disposition naming it — is decided twice, in two forms, in two modules. `status.queue` builds the id set and discards the dispositioned ones to produce `inbox_counts`; `board.render` rebuilds the same set and filters it again to print the `## Inbox` list.

Both answers are printed in the same document. `BOARD.md`'s header line reads `inbox run 1` from the counts, and the list directly below it comes from the board's own filter. A change to either one — adding an outcome to the terminal set, say — makes those two adjacent lines contradict each other, and no test would fail.

The file already carries the precedent: `board.py` re-exports `IN_FLIGHT` from `events` with the note that it is card 7 R5's one home, checked by identity in its tests. This is the same move for the same kind of rule.

Write that re-export explicitly — `from .status import Projection, Queue, open_intake_ids as open_intake_ids` — and not as a plain import. A test that imports the symbol from `board` to check by identity that the two sites are one object makes `board` part of its own public surface, and under mypy `--strict` a plainly-imported name is not exported: the check answers `error: Module "isidium.store.core.board" does not explicitly export attribute "open_intake_ids" [attr-defined]`. `IN_FLIGHT as IN_FLIGHT` two lines above is the form to copy. Every pytest leg passes without the `as`; the type-checker leg is the only one that fails, so a green local test run is not evidence here.

In scope: one function answering "which intake ids are open" over the inbox records, in `core/status.py` beside the queue that needs it; `status.queue` and `board.render` both reading it; and tests pinning the rendered `## Inbox` list and the `inbox_counts` header to that one answer.

Not in scope: changing which outcomes close an intake — `accepted` and `declined` today, with `deferred` deliberately leaving the item open, which R2 pins rather than changes; adding a field to `Queue`, which would move the wire contract in `server/api.py` and cost more than the drift does; the inbox's own schema; and the duplicate suggestions `s2`–`s5` on this tenant, which are a landed fact and not a defect to clean up.

## History

```toml
history = [
  { seq = 1, at = "2026-09-21T21:40:31Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "effort", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:a2eb910ed1d47c63156f920b03df15a569e096224cc9927c74bc8cf0c034d676", h = "sha256:0b8b6df03108703aeba500a520c8c2eb0e7d97fb2fded58641854551633e88c3", batch = 16 },
  { seq = 2, at = "2026-09-22T00:28:24Z", by = "amodal1@users.noreply.github.com", act = "demoted", fields = ["status"], build = "sha256:a2eb910ed1d47c63156f920b03df15a569e096224cc9927c74bc8cf0c034d676", h = "sha256:d8eece5144839244566468ccc218e22f71406bd337c747bb4b58a4f940a5aff9" },
  { seq = 3, at = "2026-09-22T02:21:20Z", by = "amodal1@users.noreply.github.com", act = "amended", fields = ["scope"], build = "sha256:ac02793a029091122d6da3d80fc29e492892d188095cb5b093d610d38b82b7e6", h = "sha256:74b9ead1d99d3c4ad10b622ada250bd8377dd67ba028182406c7382d96589054" },
  { seq = 4, at = "2026-09-22T02:21:51Z", by = "amodal1@users.noreply.github.com", act = "ratified", fields = ["status"], build = "sha256:ac02793a029091122d6da3d80fc29e492892d188095cb5b093d610d38b82b7e6", h = "sha256:e1255ab96ee18d7096f34c27435f1305f190526748d9900b0e60c1bcad6138a3", batch = 18 },
]
```
