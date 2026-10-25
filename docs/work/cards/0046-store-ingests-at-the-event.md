```toml
schema = 1
id = 46
kind = "story"
status = "draft"
source = "session"
title = "The store ingests at the event: a signed ratification and a pending merge are landed by the store itself, not by an empty report"
shape = "bdd"
effort = "default"
refs = ["packages/isidium-store/src/isidium/store/server/store.py", "packages/isidium-store/src/isidium/store/server/api.py", "packages/isidium-store/src/isidium/store/server/identity.py"]
surfaces = ["packages/isidium-store/src/isidium/store/server/store.py", "packages/isidium-store/src/isidium/store/server/api.py", "tests/store/test_ingest_at_the_event.py", "tests/store/test_v3.py", "tests/store/test_l1.py", "tests/store/test_scenarios.py", "tests/factory/test_v3.py"]
priority = "P1"

[narrative]
feature = "a signed card is ready at once, and a merge is landed before anyone reads the ready view"

[[rules]]
id = "R1"
text = "after ratify --sign commits its batch, the store ingests it in a second journal row and commit, the same fold and fingerprint an empty-report land makes (the `ratified` event with the ratifying commit's sha and refs at it); the card reads ready, not ratified (pending-ingest), when ratify returns"

[[rules]]
id = "R2"
text = "the dispatch view, when merges are pending, fast-forwards and ingests them first (what an empty-report land does) and then answers; dispatch.pending-land is no longer raised"

[[rules]]
id = "R3"
text = "an empty-report land still works and is still idempotent; nothing that lands today stops landing"

[[rules]]
id = "R4"
text = "a failed ingest after a successful ratify leaves the signed batch in place and the card pending-ingest, as today, and the ratify's answer says the ingest did not happen"

[[guidance.avoid]]
id = "A1"
option = "folding the ingest into the ratify commit"
because = "checked when filing: the `ratified` event needs the ratifying commit's sha and its tree (oids_at), which exist only after the commit"

[[guidance.avoid]]
id = "A2"
option = "widening the manifest rows so the owner may write the sidecar"
because = "the sidecar is the lander's (config.toml [[governed]] write = [lander]); the ingest is written under the lander's grant by the store, as a land is, not under the signer's"

[[guidance.constraints]]
id = "C1"
text = "the ingest after ratify runs after the journal transaction that signs (store.py ratify's `with self.journal.transaction()` block) has ended, never inside it"
because = "checked when filing: the transaction is held across the signing round trip and rolls back on a push failure"

[[guidance.constraints]]
id = "C2"
text = "the tests that assert a fresh ratification is pending-ingest, and that dispatch refuses pending-land, move to the new behaviour; the tests that use an empty land as an ingest tick keep passing unchanged"
because = "checked when filing: tests/store/test_v3.py:254-284, test_l1.py:217-238, test_scenarios.py:830-843, tests/factory/test_v3.py:331-334"

[[guidance.constraints]]
id = "C3"
text = "no new refusal namespace"
because = "core/disclosure.py stays untouched"

[[guidance.constraints]]
id = "C9"
text = "every file this card changes passes ruff check, ruff format --check and mypy --strict, by path"
because = "r-38 and r-39 each lost a whole run to a one-line style miss"

[[acceptance.scenarios]]
id = "S1"
kind = "test-marker"
title = "a signed card is ready when ratify returns"
rule = "R1"
observable = { test = "tests/store/test_ingest_at_the_event.py::test_a_signed_card_is_ready_when_ratify_returns" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "the dispatch view ingests a pending merge and answers"
rule = "R2"
observable = { test = "tests/store/test_ingest_at_the_event.py::test_the_dispatch_view_ingests_a_pending_merge" }

[[acceptance.scenarios]]
id = "S3"
kind = "test-marker"
title = "an empty-report land still lands idempotently"
rule = "R3"
observable = { test = "tests/store/test_ingest_at_the_event.py::test_an_empty_land_still_lands" }

[[acceptance.scenarios]]
id = "S4"
kind = "test-marker"
title = "a failed ingest leaves the batch signed and says so"
rule = "R4"
observable = { test = "tests/store/test_ingest_at_the_event.py::test_a_failed_ingest_leaves_the_batch_signed" }
```

## Scope

Ruled [owner, 2026-10-23]: ingest is 'The store, at the event'. Every signature and every merge this session needed a hand empty-report land before dispatch or a card write worked (dispatch.pending-land, git.push-rejected, ratified (pending-ingest)). Surveyed: ratify writes no sidecar; the dispatch view is a read that refuses pending merges.

## History

```toml
history = [
  { seq = 1, at = "2026-10-25T21:44:17Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:697c9b586cb421862cb8147b0806b05889f50ac5fc9c9ec008d2d5f5b946e4a3", h = "sha256:16e721b4e1e7f678f27b1bbc6397b8a4e670544826101b0c59aec13c61658802" },
]
```
