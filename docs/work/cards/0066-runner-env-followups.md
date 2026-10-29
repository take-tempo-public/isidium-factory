```toml
schema = 1
id = 66
kind = "story"
status = "draft"
source = "session"
title = "The runner image's build proves the guard's interpreter, the hash check is told apart per environment, and the builder prompt names every tool form"
shape = "bdd"
effort = "default"
refs = ["deploy/Containerfile.runner", "tests/factory/test_runner_test_env.py", "prompts/builder/v7.md", "packages/isidium-factory/src/isidium/factory/guard.py::main", "packages/isidium-factory/src/isidium/factory/render.py"]
surfaces = ["deploy/Containerfile.runner", "tests/factory/test_runner_test_env.py", "prompts/builder/v8.md", "packages/isidium-factory/src/isidium/factory/guard.py", "tools/mutations/runner-env-followups.toml"]
priority = "P1"

[narrative]
feature = "card 65's open review findings F2-F5 are closed"

[[rules]]
id = "R1"
text = "the image build asserts that `python` (the guard hook's command, render.GUARD_COMMAND) resolves outside both test environments and imports isidium.factory.guard, so a PATH that put a test environment's python first fails the build instead of switching the guard off silently"

[[rules]]
id = "R2"
text = "S3's per-environment --require-hashes assertion selects each environment's own install, so dropping the flag from either one fails the test"

[[rules]]
id = "R3"
text = "builder v8 names `python -m pytest`, `python -m ruff`, `python -m mypy` and `uv run` as reaching the runtime interpreter, and says to call the tool directly"

[[rules]]
id = "R4"
text = "guard.py's comment on why Bash is hooked names both rules it carries: the process-limit rule and the install rule"

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
title = "the build's interpreter assertion names `python`, not only `python3`"
rule = "R1"
observable = { test = "tests/factory/test_runner_test_env.py::test_the_build_asserts_the_guard_interpreter_is_the_runtime_one" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "each environment's install line carries --require-hashes on its own"
rule = "R2"
observable = { test = "tests/factory/test_runner_test_env.py::test_each_environment_install_carries_require_hashes_alone" }

[[acceptance.scenarios]]
id = "S3"
kind = "test-marker"
title = "builder v8 names the four wrong forms"
rule = "R3"
observable = { test = "tests/factory/test_runner_test_env.py::test_builder_v8_names_every_wrong_interpreter_form" }

[[acceptance.scenarios]]
id = "S4"
kind = "test-marker"
title = "the HOOKED comment names both rules"
rule = "R4"
observable = { test = "tests/factory/test_guard_installs.py::test_the_hooked_comment_names_both_bash_rules" }
```

## Scope

Review r-60 (card 65, PR #120, merged eaf8863): F2 major, F3-F5 minor, left open by owner decision 'push it and merge'. Measured 2026-10-29 in isidium-runner:v7: python and python3 resolve to /usr/local/bin, so F2's silent-off case does not occur today; this card pins it so it cannot start.

## History

```toml
history = [
  { seq = 1, at = "2026-10-29T21:06:37Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:ece05dffcd8c405a5cee38b9ec6a68b1f6a6e414fe44c9b69467bdd474c23164", h = "sha256:26429493c9e718d2e5bf2de6e8701bfc10dc400e34b541d66926be3abe8e47b9" },
]
```
