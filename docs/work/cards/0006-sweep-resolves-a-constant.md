```toml
schema = 1
id = 6
kind = "story"
status = "draft"
source = "session"
title = "The rule-id sweep resolves a module constant, not only a literal"
shape = "bdd"
effort = "default"
refs = ["tests/unit/test_rule_ids.py", "packages/isidium-store/src/isidium/store/core/disclosure.py"]
surfaces = ["tests/unit/test_rule_ids.py"]
priority = "P2"

[narrative]
feature = "the sweep that fails the build on an unclassified rule namespace sees a rule id raised through a module-level constant, so a namespace cannot slip past C-12's table by being given a name"

[[rules]]
id = "R1"
text = "A rule id the code can raise is swept whatever form it is written in: a literal, an f-string, or a module-level constant bound to a string in the same module"

[[rules]]
id = "R2"
text = "A form the sweep cannot resolve is refused rather than skipped: an unresolvable first argument to Refusal fails the sweep, so silence is never the answer"

[[acceptance.scenarios]]
id = "S1"
kind = "test-marker"
title = "a rule id raised through a module constant is swept and must be classified"
rule = "R1"
observable = { test = "tests/unit/test_rule_ids.py::test_a_rule_id_raised_through_a_constant_is_swept" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "a first argument the sweep cannot resolve fails the sweep"
rule = "R2"
observable = { test = "tests/unit/test_rule_ids.py::test_an_unresolvable_rule_id_fails_the_sweep" }
```

## Scope

Found building V4a-i (2026-09-12). `tests/unit/test_rule_ids.py` fails the build on any rule namespace `core/disclosure.py` does not classify (C-12) — and it reads the first argument of `Refusal(...)` as an `ast.Constant` (a literal) or an `ast.JoinedStr` (an f-string, via `_computed_namespace`). It resolves no other form. The first draft of `adapter.py` and `container.py` raised through module-level constants (`Refusal(RULE_IMAGE, ...)`), and the whole `adapter.*` namespace was invisible to the one gate that exists to classify it: the sweep reported only `run`, whose ids happened to be written as literals. Nothing was unclassified in the end — the ids were made literals and the reason written at both sites — but the gate would not have caught it.

In scope: a fifth form in `rule_ids`/`computed_namespaces` that resolves an `ast.Name` bound to a string constant at module level in the same module; and R2's refusal, so that a form the sweep still cannot resolve fails rather than passes in silence. A planted-probe test for each, in the shape `test_the_sweep_sees_the_whole_surface` already uses.

Not in scope: changing how any package raises its refusals; the disclosure table's own rows; resolving a constant imported from another module (name it as a limit if the fix cannot reach it, rather than passing it silently — R2 covers that case by refusing).

## History

```toml
history = [
  { seq = 1, at = "2026-09-12T15:34:36Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "effort", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:ee67fd4a85c481b1547eeec4a915dd7cbb5518d5703717f3e517018d8c37a1d2", h = "sha256:8636f6762a89f09d7d0060340d00f7f800c44520346efe3701f0f8ce402819cd" },
]
```
