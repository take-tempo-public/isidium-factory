```toml
schema = 1
id = 28
kind = "story"
status = "ratified"
source = "session"
title = "A run's actions take a lease in the ledger, so the operator and the PR watcher never act on one run at once"
shape = "bdd"
effort = "default"
refs = ["packages/isidium-factory/src/isidium/factory/ledger.py::Ledger", "packages/isidium-factory/src/isidium/factory/cli.py", "packages/isidium-factory/src/isidium/factory/close.py::close", "packages/isidium-factory/src/isidium/factory/runner.py::run_fixup"]
surfaces = ["packages/isidium-factory/src/isidium/factory/ledger.py", "packages/isidium-factory/src/isidium/factory/cli.py", "tests/factory/test_leases.py", "tests/factory/test_v5a.py", "tools/mutations/leases.toml"]
priority = "P2"

[narrative]
feature = "two callers of close or a fixup on the same run cannot overlap, and the record says who acted and when"

[[rules]]
id = "R1"
text = "the ledger gains a leases table: run_id, action, head_sha, holder (watcher or operator), taken_at, expires_at, released_at, outcome; rows are never deleted"

[[rules]]
id = "R2"
text = "taking a lease is one BEGIN IMMEDIATE transaction that fails when an unreleased lease for the same (run, action) has not expired; it refuses run.lease-held naming the holder and its expiry"

[[rules]]
id = "R3"
text = "a lease is released with the action's outcome when the action ends, refusal and exception included; a holder that dies leaves it to expire"

[[rules]]
id = "R4"
text = "the close verb takes a close lease and `run --phase fixup` takes a fixup lease, both as holder operator, at the CLI boundary; close() and run_fixup() themselves are unchanged"

[[rules]]
id = "R5"
text = "the ledger answers how many leases a holder took for an action since a given instant, which is the PR watcher's daily ceiling count"

[[rules]]
id = "R6"
text = "the ledger's SCHEMA becomes 4 and an existing schema-3 ledger gains the table at open, its rows kept"

[[guidance.avoid]]
id = "A1"
option = "changing close() or run_fixup() signatures, or taking the lease inside them"
because = "the owner is 'hesitant to change the verb structure' (2026-10-02); at the CLI boundary the lease is one wrapper, and the dozen test files that call close() and run_fixup() directly are untouched"

[[guidance.avoid]]
id = "A2"
option = "a lock file or an in-memory lock"
because = "the owner, 2026-10-04 (the watcher design, chunk plan: 'The PR watcher'): 'Per-run lease in the ledger', so a human and the watcher see one lock"

[[guidance.constraints]]
id = "C1"
text = "expiry: a fixup lease expires after the policy's wall_clock_s times container.ATTEMPTS; a close lease after a named constant CLOSE_LEASE_S = 3600, whose comment states the measurement: close.RERUN_BOUND_S is 1800 s and acceptance took 2 to 15 min on this workstation"
because = "close has no acceptance timeout of its own (checked when filing), so its bound is declared, not derived (C-13: the reason at the site)"

[[guidance.constraints]]
id = "C2"
text = "the table is appended to _DDL (created IF NOT EXISTS at every open); _DDL's order is not changed"
because = "tests index _DDL[0] and _DDL[1]"

[[guidance.constraints]]
id = "C3"
text = "tests/factory/test_v5a.py:448's literal \"3\" moves to the new schema; a schema-3-to-4 open test follows test_v4a.py's schema-2-to-3 one"
because = "checked when filing"

[[guidance.constraints]]
id = "C4"
text = "refusals use the run. namespace (run.lease-held); no new namespace"
because = "run is classified (422 TERSE) in core/disclosure.py; a new one is a store change"

[[guidance.constraints]]
id = "C5"
text = "tools/mutations/leases.toml commits a mutation for R2 (an unexpired lease taken twice) and one for R3 (a refusal leaves the lease held); each kill is checked against this card's own test file only, applied in place and restored; tools/mutate.py is --show only"
because = "the card-writing checklist"

[[guidance.constraints]]
id = "C6"
text = "each lease take and release is inside the ledger's existing isidium.factory.ledger.write span, with the action and holder as attributes"
because = "C-11; no span is added under isidium.factory.run.*, which test_v4a_ii pins"

[[guidance.constraints]]
id = "C9"
text = "every file this card changes passes ruff check, ruff format --check and mypy --strict, by path"
because = "r-38 and r-39 each lost a whole run to a one-line style miss"

[[acceptance.scenarios]]
id = "S1"
kind = "test-marker"
title = "a lease table is created and its rows are kept"
rule = "R1"
observable = { test = "tests/factory/test_leases.py::test_the_lease_table_keeps_every_row" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "an unexpired lease refuses a second taker"
rule = "R2"
observable = { test = "tests/factory/test_leases.py::test_an_unexpired_lease_refuses_a_second_taker" }

[[acceptance.scenarios]]
id = "S3"
kind = "test-marker"
title = "a refusal inside the action releases the lease with its outcome"
rule = "R3"
observable = { test = "tests/factory/test_leases.py::test_a_refusal_releases_the_lease_with_its_outcome" }

[[acceptance.scenarios]]
id = "S4"
kind = "test-marker"
title = "an expired lease can be taken again"
rule = "R2"
observable = { test = "tests/factory/test_leases.py::test_an_expired_lease_can_be_taken_again" }

[[acceptance.scenarios]]
id = "S5"
kind = "test-marker"
title = "the close and fixup verbs take their lease as the operator"
rule = "R4"
observable = { test = "tests/factory/test_leases.py::test_the_verbs_take_their_lease_as_the_operator" }

[[acceptance.scenarios]]
id = "S6"
kind = "test-marker"
title = "the ceiling count is the holder's leases since an instant"
rule = "R5"
observable = { test = "tests/factory/test_leases.py::test_the_ceiling_count_is_the_holders_leases_since" }

[[acceptance.scenarios]]
id = "S7"
kind = "test-marker"
title = "a schema-3 ledger gains the lease table at open"
rule = "R6"
observable = { test = "tests/factory/test_leases.py::test_a_schema_3_ledger_gains_the_lease_table" }
```

## Scope

Ruled 2026-10-04 [owner]: 'Per-run lease in the ledger' (every caller, human or watcher), and the shape 'As proposed': keyed (run, action, head_sha); holder; expiry from the action's own bound so a crashed holder frees itself; rows never deleted, so the table is the lock, the history and the watcher's ceiling count.

Not in scope: the watcher (card 31) and its holder; land, which is idempotent by its watermark and is only called inside close and the runner.

## History

```toml
history = [
  { seq = 1, at = "2026-10-05T14:21:28Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:e409483c7300953acb09e6e14b10e3738b5c04c81bdf3047569a724b5ae8e3a3", h = "sha256:729ee08ab8a64981fb8626e0df520952c733751798a020f13f2d4ee5c327826a" },
  { seq = 2, at = "2026-10-05T14:24:16Z", by = "amodal1@users.noreply.github.com", act = "amended", fields = ["scope"], build = "sha256:53b208a19f0f5a060ef6c48a318e42dc90bef7f2c27b31a34a9784707026d20c", h = "sha256:faa78f5b803e6cbfb358d6a83390c639dbfa2f64fdff3b4e2654f0bca53c8235" },
  { seq = 3, at = "2026-10-05T18:49:13Z", by = "amodal1@users.noreply.github.com", act = "ratified", fields = ["status"], build = "sha256:53b208a19f0f5a060ef6c48a318e42dc90bef7f2c27b31a34a9784707026d20c", h = "sha256:b6eb454d1a2bc70a1fd7e5596e710003c355f05282640f84548a92b54cafccfd", batch = 63 },
]
```
