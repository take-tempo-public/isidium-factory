```toml
schema = 1
id = 24
kind = "story"
status = "ratified"
source = "session"
title = "The builder checks every file it changed with ruff and mypy before it finishes"
shape = "bdd"
effort = "default"
refs = ["prompts/builder/v4.md", "packages/isidium-factory/src/isidium/factory/runner.py::AGENT_OF"]
surfaces = ["prompts/builder/v5.md", "tests/factory/test_builder_prompt_v5.py"]
priority = "P1"

[narrative]
feature = "a run's pull request does not go red on a lint or a type error in the files its own builder wrote"

[[rules]]
id = "R1"
text = "Builder prompt v5 requires, before the builder finishes and in both build and reconcile, ruff check, ruff format --check and mypy --strict on every file it changed — by path, never the whole tree — and fixing what they report inside the surfaces"

[[rules]]
id = "R2"
text = "v5 keeps v4's rule that the project's gate is not the builder's to run: the whole suite stays green-bar's, and a whole-tree lint or type-check is not this step"

[[rules]]
id = "R3"
text = "v5 is otherwise v4's text, unchanged; v4 is not edited"

[[guidance.avoid]]
id = "A1"
option = "a wrapper-side lint that rewrites the builder's files"
because = "the wrapper commits what the phase did; fixing is the builder's work and its record"

[[guidance.constraints]]
id = "C1"
text = "the new prompt is a new file; selecting it is a signed config act and a runner rebuild after the merge, not this card"
because = "7bd.11: a new version is a new file; the image carries prompts, the policy names the version"

[[guidance.constraints]]
id = "C2"
text = "the test reads the prompt file as text and pins the per-file commands, the both-phases scope and the unchanged-v4 property; no runner or harness code changes"
because = "checked when filing: no test asserts the builder's prompt version outside test_v4a's defaults, which name config@7's default (v3) and are untouched"

[[acceptance.scenarios]]
id = "S1"
kind = "test-marker"
title = "v5 requires ruff and mypy on the changed files, by path"
rule = "R1"
observable = { test = "tests/factory/test_builder_prompt_v5.py::test_v5_requires_ruff_and_mypy_on_the_changed_files" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "v5 applies it in reconcile too"
rule = "R1"
observable = { test = "tests/factory/test_builder_prompt_v5.py::test_v5_applies_it_in_reconcile_too" }

[[acceptance.scenarios]]
id = "S3"
kind = "test-marker"
title = "v5 keeps the whole gate green-bar's"
rule = "R2"
observable = { test = "tests/factory/test_builder_prompt_v5.py::test_v5_keeps_the_whole_gate_green_bars" }

[[acceptance.scenarios]]
id = "S4"
kind = "test-marker"
title = "v5 is v4 plus the one change, and v4 is unedited"
rule = "R3"
observable = { test = "tests/factory/test_builder_prompt_v5.py::test_v5_is_v4_plus_the_change" }
```

## Scope

Found 2026-10-02 with r-38 (card 23), the review gate's first live run: the build passed its own tests and the review, and #96 went red on one ruff SIM105 in the builder's own test file. A red PR has no path but a fresh run, so a lint miss costs a whole run (~$7). Builder v4 permits linting the files being edited but does not require it. The owner ruled (2026-10-02): file it.

Not in scope: selecting v5 (a signed config act and a runner rebuild after the merge); the reviewer.

## History

```toml
history = [
  { seq = 1, at = "2026-10-02T18:15:50Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:1ec45c7b47b149e27b96d08298b718a407c82a7cef428c2c85812cd8f1d5d1be", h = "sha256:0132988dd47d3dc516d5594941e79c6c8e8c04d7de2725bd9f4cd6c3e3645aa2" },
  { seq = 2, at = "2026-10-02T18:41:16Z", by = "amodal1@users.noreply.github.com", act = "ratified", fields = ["status"], build = "sha256:1ec45c7b47b149e27b96d08298b718a407c82a7cef428c2c85812cd8f1d5d1be", h = "sha256:6183c66615b47287ce92c1d8ccf160d33bb1804105b0da10d7f9539c0c07752d", batch = 55 },
]
```
