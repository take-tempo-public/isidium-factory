```toml
schema = 1
id = 37
kind = "story"
status = "ratified"
source = "session"
title = "An idle watcher pass reads the ledger and stops: no tenant context, no fetch, no forge, when no open run has a pull request"
shape = "bdd"
effort = "default"
refs = ["packages/isidium-factory/src/isidium/factory/cli.py", "packages/isidium-factory/src/isidium/factory/watch.py", "packages/isidium-factory/src/isidium/factory/context.py"]
surfaces = ["packages/isidium-factory/src/isidium/factory/cli.py", "packages/isidium-factory/src/isidium/factory/watch.py", "tests/factory/test_watch_idle_pass.py"]
priority = "P2"

[narrative]
feature = "the watcher costs a ledger read every fifteen minutes when there is nothing to watch, not a network fetch and a full tenant load"

[[rules]]
id = "R1"
text = "`watch --once` opens the ledger first and reads the in-flight runs; when none has a pull request it prints the pass summary (open=0) and exits 0 without calling context.load, fetching the checkout's remote, or constructing the forge driver"

[[rules]]
id = "R2"
text = "when at least one in-flight run has a pull request, the pass proceeds exactly as today"

[[rules]]
id = "R3"
text = "the idle pass still emits its isidium.factory.watch.pass span, with the open-run count"

[[guidance.avoid]]
id = "A1"
option = "caching the tenant context or the fetch across passes"
because = "each pass is a fresh process (the host timer, card 30); laziness, not a cache, is the fix (C-13)"

[[guidance.constraints]]
id = "C1"
text = "the reason is written at the site, with the measurement: an idle pass took 12-18 s and ~115 MB on the workstation, about 7 s of it in context.load's two git subprocesses (2026-10-07), against ~2 s for imports and a ledger read"
because = "C-13: lazy by default, and the site carries the evidence"

[[guidance.constraints]]
id = "C2"
text = "where the deploy home and ledger are found without context.load uses the same resolution context.load uses (registration.deploy_home / tenant_client), not a second copy of it"
because = "one home for the rule"

[[guidance.constraints]]
id = "C3"
text = "every file this card changes passes ruff check, ruff format --check and mypy --strict, by path"
because = "r-38 and r-39 each lost a whole run to a one-line style miss"

[[acceptance.scenarios]]
id = "S1"
kind = "test-marker"
title = "an idle pass never loads the tenant context or the forge"
rule = "R1"
observable = { test = "tests/factory/test_watch_idle_pass.py::test_an_idle_pass_never_loads_the_context" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "a pass with an open pull request proceeds as before"
rule = "R2"
observable = { test = "tests/factory/test_watch_idle_pass.py::test_a_pass_with_an_open_pr_proceeds" }

[[acceptance.scenarios]]
id = "S3"
kind = "test-marker"
title = "an idle pass still emits its pass span"
rule = "R3"
observable = { test = "tests/factory/test_watch_idle_pass.py::test_an_idle_pass_emits_its_span" }
```

## Scope

Measured 2026-10-07 at the owner's question ('how many resources does it use?'): three idle passes, 12-18 s, ~115 MB peak tree; cProfile: imports ~1.5-1.8 s, context.load ~7.3 s (git fetch of the remote), all before the ledger is opened. At the ruled 15-minute cadence that is ~96 fetches and ~20-25 min of process time a day for nothing. Owner: 'yes'.

## History

```toml
history = [
  { seq = 1, at = "2026-10-07T19:57:52Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:581915a44dc3208834614f86e5557202a40c47c5ecf927b5a94bdf9305665d4a", h = "sha256:f1a9925088fa989d6779e9ee58c8e9bea04102c62d695f070218f146b9a445bf" },
  { seq = 2, at = "2026-10-07T22:23:09Z", by = "amodal1@users.noreply.github.com", act = "ratified", fields = ["status"], build = "sha256:581915a44dc3208834614f86e5557202a40c47c5ecf927b5a94bdf9305665d4a", h = "sha256:0b95c0339015c023379ede50f97e31594fabf88482708b626ec6e4f1c07dfdb7", batch = 70 },
]
```
