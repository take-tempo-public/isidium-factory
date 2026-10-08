```toml
schema = 1
id = 44
kind = "story"
status = "draft"
source = "session"
title = "The config schema's [watcher] table gains a signed dispatch opt-in and a daily dispatch cap"
shape = "bdd"
depends_on = [42]
effort = "default"
refs = ["packages/isidium-store/src/isidium/store/registry/schemas/config@8.toml", "packages/isidium-store/src/isidium/store/registry/config.py", "packages/isidium-factory/src/isidium/factory/watch.py", "docs/design/04-config-schema.md"]
surfaces = ["packages/isidium-store/src/isidium/store/registry/schemas/config@9.toml", "packages/isidium-store/src/isidium/store/registry/config.py", "packages/isidium-factory/src/isidium/factory/watch.py", "docs/design/04-config-schema.md", "tests/store/test_config9.py", "tests/unit/test_lazy_registry.py", "tests/unit/test_registry.py", "tests/store/test_k6.py", "tests/store/test_k10.py", "tests/store/test_v3.py", "tests/store/test_k7b.py", "tests/store/test_verify_chain.py", "tests/store/test_config8.py", "tests/factory/test_v1.py"]
priority = "P2"

[narrative]
feature = "the owner turns unattended dispatch on, and caps it, with a signature"

[[rules]]
id = "R1"
text = "config@9 is config@8 with [watcher] gaining dispatch (bool, default false) and dispatch_per_day (an integer of at least 0, default 0); the defaults live in the schema"

[[rules]]
id = "R2"
text = "watch.Policy reads dispatch and dispatch_per_day from a config@9 tenant, and reads them as off for config@8"

[[rules]]
id = "R3"
text = "a negative dispatch_per_day is refused at validation under the config namespace"

[[guidance.avoid]]
id = "A1"
option = "an unsigned opt-in"
because = "the owner, 2026-10-07 (smoothing the line, chunk plan): 'Signed opt-in + daily cap'"

[[guidance.constraints]]
id = "C1"
text = "every pin card 27 moved for config@8 moves the same way for config@9 (the list in this card's surfaces; test_v1's GOLDEN gains a schema-8 arm with the old value)"
because = "checked when filing: commit 10c2cf0 (card 27, #106)"

[[guidance.constraints]]
id = "C2"
text = "docs/design/04-config-schema.md gains config@9's row; docs/ is CRLF, count bytes"
because = "AGENTS.md"

[[guidance.constraints]]
id = "C9"
text = "every file this card changes passes ruff check, ruff format --check and mypy --strict, by path"
because = "r-38 and r-39 each lost a whole run to a one-line style miss"

[[acceptance.scenarios]]
id = "S1"
kind = "test-marker"
title = "config@9 declares the dispatch keys with their defaults"
rule = "R1"
observable = { test = "tests/store/test_config9.py::test_config9_declares_the_dispatch_keys" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "a config@8 tenant reads dispatch as off"
rule = "R2"
observable = { test = "tests/store/test_config9.py::test_a_config8_tenant_reads_dispatch_off" }

[[acceptance.scenarios]]
id = "S3"
kind = "test-marker"
title = "a negative dispatch_per_day is refused"
rule = "R3"
observable = { test = "tests/store/test_config9.py::test_a_negative_dispatch_per_day_is_refused" }
```

## Scope

Ruled [owner, 2026-10-07]: the dispatcher's spend guard is 'Signed opt-in + daily cap', as fixup's is (card 27).

## History

```toml
history = [
  { seq = 1, at = "2026-10-08T01:38:14Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "depends_on", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:db63bc5dcd21beb2bfe1f1fdc2fdbd8820802fe0ad5cec722dcaf5cc930ba768", h = "sha256:ddb8a1c720d7c0a109d56bd5653371221ad7e5ae0d0f64ce95f23fc374a473c3" },
]
```
