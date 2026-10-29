```toml
schema = 1
id = 65
kind = "story"
status = "draft"
source = "session"
title = "The build container carries the lock's test environment on Python 3.12 and 3.13, and a phase cannot install packages"
shape = "bdd"
effort = "default"
refs = ["deploy/Containerfile.runner", "deploy/build-runner.sh", "packages/isidium-factory/src/isidium/factory/guard.py::whole_suite", "packages/isidium-factory/src/isidium/factory/guard.py::main", "pyproject.toml", ".github/workflows/ci.yml", "prompts/builder/v6.md"]
surfaces = ["deploy/Containerfile.runner", "packages/isidium-factory/src/isidium/factory/guard.py", "prompts/builder/v7.md", "tests/factory/test_runner_test_env.py", "tests/factory/test_guard_installs.py", "tools/mutations/runner-test-env.toml"]
priority = "P0"

[narrative]
feature = "the builder and reconcile run the card's tests, ruff and mypy in their own container, on both CI Pythons, and never install a tool themselves"

[[rules]]
id = "R1"
text = "the runner image holds two test environments, one per CI Python (3.12 and 3.13), each installed with --require-hashes from `uv export --locked --all-packages --all-extras --group dev --no-emit-workspace`, the resolution CI's `uv sync --locked --all-packages --all-extras` installs, without the workspace packages (pytest's pythonpath and mypy's mypy_path point at the worktree's src trees, so the code under test is the worktree's, never an installed wheel)"

[[rules]]
id = "R2"
text = "the 3.12 environment's bin is first on the phase's PATH, so pytest, ruff and mypy resolve to it; the 3.13 environment is at the path the image's ISIDIUM_PY313 names; both are root-owned and not writable by the runner user, and the runtime install the guard uses is unchanged"

[[rules]]
id = "R3"
text = "the guard refuses, exit 2 and recorded in guard_blocks, a Bash call with a shell segment that installs packages or makes an environment (pip, pip3 or python -m pip with install or download; uv pip install; uv add; uv sync; uv tool install; python -m venv; virtualenv), whatever runs beside it on the line, and the reason names the image's tools and says a missing tool is a line in the report, not an install"

[[rules]]
id = "R4"
text = "builder v7 says the tools are present, tells the phase to run the card's own tests by file or node on 3.12 and on 3.13 and ruff check, ruff format --check and mypy --strict on every changed file by path, never to install, and to say in its report any check it could not run"

[[guidance.avoid]]
id = "A1"
option = "installing the dev group into the system interpreter beside the factory's runtime"
because = "one environment would serve two masters: a card that bumps a test dependency would move the interpreter the guard and harness run on"

[[guidance.avoid]]
id = "A2"
option = "a test that passes by skipping when podman is absent"
because = "card 61's rule: no scenario may pass by skipping; the image-level checks are S4, which builds the image"

[[guidance.constraints]]
id = "C1"
text = "the 3.13 interpreter is an exact pinned version installed by the pinned uv already in the build stage, which verifies its download; no new base image"
because = "a tag is a moving name (K5, ruling 7bg.5)"

[[guidance.constraints]]
id = "C2"
text = "the test environments are built in their own stage and copied in, with no wheel cache shipped; the image grows by roughly 200 to 300 MB and the build by one install step, stated here as the cost"
because = "efficiency is declared at design time, not found live"

[[guidance.constraints]]
id = "C3"
text = "the card 19 whole-suite rule is unchanged and the install rule is its sibling in main's Bash branch, reusing _SEPARATORS and _tokens"
because = "one reading of a shell line, not two"

[[guidance.constraints]]
id = "C4"
text = "tools/mutations/runner-test-env.toml commits a mutation dropping the install rule from main; it is killed by tests/factory/test_guard_installs.py alone"
because = "the card-writing checklist"

[[guidance.constraints]]
id = "C9"
text = "every file this card changes passes ruff check, ruff format --check and mypy --strict, by path"
because = "r-38 and r-39 each lost a whole run to a one-line style miss"

[[guidance.constraints]]
id = "C10"
text = "the image's test environment is the lock at image build; a card that changes uv.lock builds against the old one until the image is rebuilt, and the scope note and builder v7 say so"
because = "CI's green-bar still checks the new lock, so the drift is bounded and named"

[[acceptance.scenarios]]
id = "S1"
kind = "test-marker"
title = "each install form is blocked and recorded, alone and behind cd x &&"
rule = "R3"
observable = { test = "tests/factory/test_guard_installs.py::test_every_install_form_is_blocked_and_recorded" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "the card's own pytest, ruff and mypy by path are allowed and a whole-suite run is still blocked"
rule = "R3"
observable = { test = "tests/factory/test_guard_installs.py::test_the_tools_by_path_pass_and_the_whole_suite_is_still_blocked" }

[[acceptance.scenarios]]
id = "S3"
kind = "test-marker"
title = "Containerfile.runner exports the locked dev group with hashes for both Pythons and sets PATH and ISIDIUM_PY313"
rule = "R1"
observable = { test = "tests/factory/test_runner_test_env.py::test_the_containerfile_installs_the_locked_dev_group_for_both_pythons" }

[[acceptance.scenarios]]
id = "S4"
kind = "command"
title = "a built image runs pytest, ruff and mypy on 3.12, pytest on 3.13, and refuses a write into either environment"
rule = "R2"
action = { run = ["sh", "-c", "deploy/build-runner.sh isidium-runner:test-env 2.1.286 >/dev/null && podman run --rm --entrypoint sh isidium-runner:test-env -c 'pytest --version && ruff --version && mypy --version && \"$ISIDIUM_PY313/bin/python\" -m pytest --version && ! touch \"$ISIDIUM_PY313/x\" && echo test-env-ok'"] }
observable = { exit_code = 0, stdout_matches = "test-env-ok" }

[[acceptance.scenarios]]
id = "S5"
kind = "file-assert"
title = "builder v7 tells the phase to run its tests on both Pythons and never to install"
rule = "R4"
observable = { path = "prompts/builder/v7.md", contains = "ISIDIUM_PY313" }
```

## Scope

Ruled [owner, 2026-10-28]: 'Move now, then fix the builder (Recommended)' and 'Card it after the move (Recommended)'. Found 2026-10-28: r-58 (card 54, carrying r-57) ended failed:scope after a build that finished ok: lacking tools the builder ran `python3 -m venv /tmp/v && pip install ruff mypy pytest`, and a wheel (ruff-0.17.3-...whl) landed in /work. The image installs `uv export --no-dev` only, so the builder and reconcile have no pytest, ruff or mypy; three of the day's four host-only escapes (Python 3.13's strict X509 on r-55, core.autocrlf on r-54, Windows' TCP refusal timing on r-57) were seen only by the host's mutation step and the close. Asked which Pythons, the owner chose '3.12 + 3.13 (Recommended)'; asked whether to refuse installs, 'Provide + refuse installs (Recommended)'. Image rebuilt after merge with deploy/build-runner.sh and adopted through a signed config act; until then runs use isidium-runner:v6.

## History

```toml
history = [
  { seq = 1, at = "2026-10-29T01:50:53Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:8ab4ac2e02264b807bfedec562caaffe906357ca3877b2da317f3aeb706d747f", h = "sha256:29a69ac24418791b3c130fd7101b756a4d4218a19b3663fd196f208d8b37f6c9" },
  { seq = 2, at = "2026-10-29T01:54:39Z", by = "amodal1@users.noreply.github.com", act = "ratified", fields = ["status"], build = "sha256:8ab4ac2e02264b807bfedec562caaffe906357ca3877b2da317f3aeb706d747f", h = "sha256:134dec7d6dd4161520b842ea985f04b1d5a7a5e158b0adebfd0584c3454e51b1", batch = 78 },
  { seq = 3, at = "2026-10-29T02:17:43Z", by = "amodal1@users.noreply.github.com", act = "demoted", fields = ["status"], build = "sha256:8ab4ac2e02264b807bfedec562caaffe906357ca3877b2da317f3aeb706d747f", h = "sha256:1989485bf2410c1228af6d170cfc032493b6482e58865fd1909527ac1c924a1f" },
]
```
