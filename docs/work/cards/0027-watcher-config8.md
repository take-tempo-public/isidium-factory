```toml
schema = 1
id = 27
kind = "story"
status = "draft"
source = "session"
title = "The config schema gains a signed [watcher] table: whether the PR watcher may start a fixup, and how many a day"
shape = "bdd"
effort = "default"
refs = ["packages/isidium-store/src/isidium/store/registry/schemas/config@7.toml", "packages/isidium-store/src/isidium/store/registry/config.py", "docs/design/04-config-schema.md"]
surfaces = ["packages/isidium-store/src/isidium/store/registry/schemas/config@8.toml", "packages/isidium-store/src/isidium/store/registry/config.py", "docs/design/04-config-schema.md", "tests/store/test_config8.py", "tests/unit/test_lazy_registry.py", "tests/unit/test_registry.py", "tests/store/test_k6.py", "tests/store/test_k10.py", "tests/store/test_v3.py", "tests/store/test_k7b.py", "tests/store/test_verify_chain.py", "tests/store/test_config7.py", "tests/factory/test_v1.py"]
priority = "P2"

[narrative]
feature = "the owner turns automatic fixup on, and caps it, with a signature, not a flag on a host"

[[rules]]
id = "R1"
text = "config@8 is config@7 plus a [watcher] table with two keys: fixup (bool, default false) and fixup_per_day (an integer of at least 0, default 0); the defaults live in the schema, never in code"

[[rules]]
id = "R2"
text = "[watcher] is serialized in a pinned place in TABLE_ORDER with its key order in TABLE_KEY_ORDER, and validated as a plain table (no cross-key code)"

[[rules]]
id = "R3"
text = "a tenant on config@7 is still accepted by the factory, unchanged; adopting @8 is the owner's signed config-policy act, not this card"

[[rules]]
id = "R4"
text = "a [watcher] whose fixup_per_day is negative, or whose fixup is not a bool, is refused at validation under the config namespace"

[[guidance.avoid]]
id = "A1"
option = "putting the opt-in in tenant.toml or any unsigned file"
because = "the owner, 2026-10-04 (the watcher design, chunk plan: 'The PR watcher'): 'Signed opt-in + ceiling', 'New config schema row'"

[[guidance.avoid]]
id = "A2"
option = "adding the poll cadence or any host setting to [watcher]"
because = "the cadence (15 minutes, ruled) is the host timer's, card D; the signed table holds only what spends"

[[guidance.constraints]]
id = "C1"
text = "every test that pins the newest config version or the registry's schema count moves with it: test_lazy_registry (19 refs → 20, config@7 → @8), test_registry (the unshipped arm moves to @9), test_k6 (newest == 8, registry_without gains config@8), test_k10, test_v3, test_k7b, test_verify_chain, test_config7's newest pin"
because = "checked when filing: commit 6b96f2b (config@7) moved exactly these"

[[guidance.constraints]]
id = "C2"
text = "tests/factory/test_v1.py's GOLDEN moves, and the same inputs at schema 7 are pinned as a new arm beside schema 5 and 6, with the old value"
because = "payload.CONFIG_SUBSET carries the effective schema; the config@7 commit set the precedent"

[[guidance.constraints]]
id = "C3"
text = "no new refusal namespace: validation refusals are config.* (classified, 422 FULL)"
because = "the card-writing checklist; core/disclosure.py stays untouched"

[[guidance.constraints]]
id = "C4"
text = "docs/design/04-config-schema.md gains config@8's row and the pinned table order; docs/ is CRLF, count bytes"
because = "AGENTS.md: docs are CRLF and preserved byte for byte"

[[guidance.constraints]]
id = "C9"
text = "every file this card changes passes ruff check, ruff format --check and mypy --strict, by path"
because = "r-38 and r-39 each lost a whole run to a one-line style miss"

[[acceptance.scenarios]]
id = "S1"
kind = "test-marker"
title = "config@8 declares the watcher table with its defaults"
rule = "R1"
observable = { test = "tests/store/test_config8.py::test_config8_declares_the_watcher_table_with_its_defaults" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "the watcher table serializes in its pinned place"
rule = "R2"
observable = { test = "tests/store/test_config8.py::test_the_watcher_table_serializes_in_its_pinned_place" }

[[acceptance.scenarios]]
id = "S3"
kind = "test-marker"
title = "a config@7 tenant is still accepted"
rule = "R3"
observable = { test = "tests/store/test_config8.py::test_a_config7_tenant_is_still_accepted" }

[[acceptance.scenarios]]
id = "S4"
kind = "test-marker"
title = "a negative fixup_per_day is refused"
rule = "R4"
observable = { test = "tests/store/test_config8.py::test_a_negative_fixup_per_day_is_refused" }
```

## Scope

Ruled 2026-10-04 [owner], the PR watcher's spend guard: 'Signed opt-in + ceiling', placed in 'New config schema row' (config@8 [watcher]). The watcher (card C) reads it; until a tenant adopts @8 by a signed act, no automatic fixup happens.

Not in scope: the watcher; adopting @8 for tenant #0; a store image swap (the owner's, after the merge).

## History

```toml
history = [
  { seq = 1, at = "2026-10-05T14:21:16Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:8992616ece5aa36d15b5c63a4d1b19130751ebf6b474b662869f9a72effdc167", h = "sha256:f3a72c610b9bf07987bfa69ecf56ab6fa9a39d67af1edd42e2db2684ca159001" },
]
```
