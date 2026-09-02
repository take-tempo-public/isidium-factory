```toml
schema = 1
id = 42
kind = "story"
status = "ratified"
source = "suggestion"
title = "cards check refuses a ratified card with no acceptance block"
shape = "bdd"
effort = "default"
refs = ["client/cards/validator.py::validate_profile", "docs/dev/work/items/0060-cards-check-no-acceptance.md"]
surfaces = ["client/cards/validator.py", "client/tests/test_validator.py"]
priority = "P1"
see = ["legacy:sartor/0060", "s12"]

[narrative]
feature = "cards check refuses a ratified card with no acceptance block"

[[rules]]
id = "R1"
text = "A ratified story without a runnable-shaped scenario is a validation error, not a warning"

[[acceptance.scenarios]]
id = "S1"
kind = "command"
rule = "R1"
title = "cards check refuses a ratified card with no acceptance block"
context = { fixture = "client/tests/fixtures/no-acceptance" }
action = { run = ["python", "-m", "cards", "check"] }
observable = { exit_code = 1, stdout_matches = "S-3\\.story\\.acceptance" }
tests = ["client/tests/test_validator.py::test_refuses_missing_acceptance"]

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
rule = "R1"
title = "build hash is key-order independent"
observable = { test = "client/tests/test_hasher.py::test_key_order_invariant" }
```

## Scope

`cards check` must treat a ratified story with no runnable-shaped
scenario as an error (`S-3.story.acceptance`), not a warning. Legacy
context: sartor item 0060 (see `refs`).

## Updates

### 2026-08-20 — filed from the inbox (s12)

Re-authored from legacy 0060 under the bridge.


## History

```toml
history = [
  { seq = 1, at = "2026-08-20T14:02:11Z", by = "amodal1@example", act = "created", fields = ["title"], build = "sha256:049f5bfe945b5f95a36af15c1b74792c0ca9e1a4a9e2fdd0be86310f02ff91c8", h = "sha256:0" },
]
```
