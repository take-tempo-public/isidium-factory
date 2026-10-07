```toml
schema = 1
id = 32
kind = "story"
status = "ratified"
source = "session"
title = "A fixup behind an aggregating required check is handed the failed jobs of that check's workflow run, not only the aggregator's echo"
shape = "bdd"
effort = "default"
refs = ["packages/isidium-factory/src/isidium/factory/github.py::GitHub", "packages/isidium-factory/src/isidium/factory/forge.py::FailedJob", ".github/workflows/ci.yml"]
surfaces = ["packages/isidium-factory/src/isidium/factory/github.py", "tests/factory/test_fixup_reads_the_aggregators_failed_legs.py", "tests/factory/test_fixup_repairs_a_red_pr.py", "tools/mutations/fixup-legs.toml"]
priority = "P1"

[narrative]
feature = "a fixup on this repository sees the ruff, mypy or pytest output that turned the gate red, not the line `suite: failure`"

[[rules]]
id = "R1"
text = "for each named failed check that is an Actions job, failed_jobs also returns every other failed job of the same workflow run attempt (the latest attempt), each as a FailedJob with its failed step's name and the last 200 lines of that step"

[[rules]]
id = "R2"
text = "the named check's own entry is still returned first, unchanged; the run's other failed jobs follow in the order the forge lists them, each named by its job name"

[[rules]]
id = "R3"
text = "at most MAX_LEG_JOBS extra jobs are returned per named check; the bound is a named constant whose comment states why (a matrix can fan out, and every tail rides into the prompt)"

[[rules]]
id = "R4"
text = "a named check that is not an Actions job, or whose workflow run cannot be read, is returned as today, and nothing is refused"

[[guidance.avoid]]
id = "A1"
option = "naming green-bar, suite, or this repository's workflow anywhere in the factory's code"
because = "the forge seam is tenant- and forge-neutral (the watcher ruling, 2026-10-04); the aggregator is found by the workflow run, not by name"

[[guidance.avoid]]
id = "A2"
option = "changing forge.Forge, FailedJob or close.Reader"
because = "the shape already carries a name, a step and a tail; only the driver's reading widens, so no test double changes (the card-writing checklist)"

[[guidance.constraints]]
id = "C1"
text = "the existing driver test in tests/factory/test_fixup_repairs_a_red_pr.py answers the new workflow-run jobs call (its transport gains the route); its assertions on the named entry are not weakened"
because = "checked when filing: test_the_github_driver_reads_the_failed_steps_last_200_lines drives failed_jobs through a fake transport"

[[guidance.constraints]]
id = "C2"
text = "tools/mutations/fixup-legs.toml commits a mutation for R3 (the bound removed) and one for R1 (the legs not read); each kill is checked against this card's own test file only, applied in place and restored; tools/mutate.py is --show only"
because = "the card-writing checklist: a limit is mutation-checked"

[[guidance.constraints]]
id = "C3"
text = "no new refusal and no new rule namespace; a forge read that fails here keeps today's forge.* refusals"
because = "core/disclosure.py stays untouched"

[[guidance.constraints]]
id = "C4"
text = "each extra read goes through the driver's existing _call, so it rides the forge.api span"
because = "C-11"

[[guidance.constraints]]
id = "C5"
text = "every file this card changes passes ruff check, ruff format --check and mypy --strict, by path"
because = "r-38 and r-39 each lost a whole run to a one-line style miss"

[[acceptance.scenarios]]
id = "S1"
kind = "test-marker"
title = "an aggregator's failed legs are handed with their own failed step tails"
rule = "R1"
observable = { test = "tests/factory/test_fixup_reads_the_aggregators_failed_legs.py::test_an_aggregators_failed_legs_are_handed_with_their_tails" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "the named check's entry comes first and is unchanged"
rule = "R2"
observable = { test = "tests/factory/test_fixup_reads_the_aggregators_failed_legs.py::test_the_named_check_comes_first_unchanged" }

[[acceptance.scenarios]]
id = "S3"
kind = "test-marker"
title = "no more than the bound of extra jobs is returned"
rule = "R3"
observable = { test = "tests/factory/test_fixup_reads_the_aggregators_failed_legs.py::test_no_more_than_the_bound_of_legs" }

[[acceptance.scenarios]]
id = "S4"
kind = "test-marker"
title = "a check outside Actions, or an unreadable run, is returned as today"
rule = "R4"
observable = { test = "tests/factory/test_fixup_reads_the_aggregators_failed_legs.py::test_a_check_outside_actions_is_returned_as_today" }
```

## Scope

Found 2026-10-06 by the model evaluation (the r-44 review replays; missed by the live r-44 review and filed nowhere): this repository's required check is green-bar, an aggregator whose one step echoes the suite jobs' result. failed_jobs reads only required checks, so a live fixup would be handed `suite: failure` and none of the output it must repair (ci.yml:61-77, github.py:343-361). The PR watcher's fixup-on-red (card 31) inherits it.

Owner: 'go' (2026-10-06).

Not in scope: any change to the workflow; webhooks; a Gitea driver.

## History

```toml
history = [
  { seq = 1, at = "2026-10-07T06:16:34Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:3b40cd002dc0b94286bfd54bfe02d87031e12babb805734af0a5449b5f5952a5", h = "sha256:12afd1130b2cb02246531e38820c66f146c00bcbe5447d24c08361702689fbad" },
  { seq = 2, at = "2026-10-07T06:26:58Z", by = "amodal1@users.noreply.github.com", act = "ratified", fields = ["status"], build = "sha256:3b40cd002dc0b94286bfd54bfe02d87031e12babb805734af0a5449b5f5952a5", h = "sha256:ca339da479ee7c158a97a43270c8e5b89cdb2b2f0c36c5e75e6b3308006efae3", batch = 64 },
]
```
