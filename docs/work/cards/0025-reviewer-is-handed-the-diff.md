```toml
schema = 1
id = 25
kind = "story"
status = "ratified"
source = "session"
title = "The reviewer is handed the run's diff, computed by the wrapper, on both passes"
shape = "bdd"
effort = "default"
refs = ["packages/isidium-factory/src/isidium/factory/runner.py::_job", "prompts/reviewer/v2.md"]
surfaces = ["packages/isidium-factory/src/isidium/factory/runner.py", "prompts/reviewer/v3.md", "tests/factory/test_reviewer_is_handed_the_diff.py", "tests/factory/test_v4a_ii_b_chain.py"]
priority = "P2"

[narrative]
feature = "the reviewer reviews what the run changed, without a tool that could change anything"

[[rules]]
id = "R1"
text = "A review phase's job carries an input named diff: the unified diff of the run's base to the worktree's HEAD, computed by the wrapper with git before the phase starts"

[[rules]]
id = "R2"
text = "Both passes are handed it: the first with the plan, the second with the findings and the reconcile report, so the second pass sees what reconcile changed"

[[rules]]
id = "R3"
text = "The reviewer's tools are unchanged: no Bash, no write; the diff is data in its job"

[[rules]]
id = "R4"
text = "Reviewer prompt v3 says the diff is in the job, names its input, and drops v2's instruction to run git diff; it is otherwise v2's text, and v2 is not edited"

[[guidance.avoid]]
id = "A1"
option = "granting the reviewer Bash"
because = "Bash can write; the reviewer writes nothing by construction (05 §1), and a read-only tool set is the guarantee"

[[guidance.constraints]]
id = "C1"
text = "the diff is computed once per review phase from the worktree, by git, and its hash rides the Input like any artifact's"
because = "T-B7 (3): what the agent reads is named by hash on the record"

[[guidance.constraints]]
id = "C2"
text = "tests/factory/test_v4a_ii_b_chain.py changes only the two assertions on the review passes' input names (:62 and :77) to include diff"
because = "checked when filing: those assertions pin today's inputs; no other test names the review's inputs"

[[guidance.constraints]]
id = "C3"
text = "the card's own test file and every file it changes pass ruff check and ruff format --check"
because = "#96 went red on one lint error; a red PR costs a whole run"

[[acceptance.scenarios]]
id = "S1"
kind = "test-marker"
title = "the first pass is handed the plan and the diff"
rule = "R1"
observable = { test = "tests/factory/test_reviewer_is_handed_the_diff.py::test_the_first_pass_is_handed_the_plan_and_the_diff" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "the second pass is handed the diff with the findings and the report"
rule = "R2"
observable = { test = "tests/factory/test_reviewer_is_handed_the_diff.py::test_the_second_pass_is_handed_the_diff_with_the_findings_and_the_report" }

[[acceptance.scenarios]]
id = "S3"
kind = "test-marker"
title = "the reviewer's tools are unchanged"
rule = "R3"
observable = { test = "tests/factory/test_reviewer_is_handed_the_diff.py::test_the_reviewers_tools_are_unchanged" }

[[acceptance.scenarios]]
id = "S4"
kind = "test-marker"
title = "v3 names the diff input and drops git diff"
rule = "R4"
observable = { test = "tests/factory/test_reviewer_is_handed_the_diff.py::test_reviewer_v3_names_the_diff_input" }
```

## Scope

Found 2026-10-02 with r-38: the reviewer's suggestions say it could not run Bash (git diff, pytest, ruff, mypy), so it read the surfaces whole instead of the change; reviewer v2 tells it to run git diff, which its tools (Read, Glob, Grep) cannot. The owner ruled (2026-10-02): file it — hand the diff in the job, not Bash.

Not in scope: selecting v3 (a signed config act and a runner rebuild); running tests from the reviewer.

## History

```toml
history = [
  { seq = 1, at = "2026-10-02T18:15:58Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:1746481cbc78f527b6fca87299252c3337da4caa62129544b7aab1adb3535174", h = "sha256:f9386b5cec7981d34d0a113fcf82e770369b33626f1f6d4864d2aa65d744fb0f" },
  { seq = 2, at = "2026-10-02T18:41:16Z", by = "amodal1@users.noreply.github.com", act = "ratified", fields = ["status"], build = "sha256:1746481cbc78f527b6fca87299252c3337da4caa62129544b7aab1adb3535174", h = "sha256:29122abead03378a07b6751bcdca49a884414a47c23641466966050ce38f6aff", batch = 55 },
]
```
