```toml
schema = 1
id = 21
kind = "story"
status = "ratified"
source = "session"
title = "A carried run records the carry commit as its head, so a carry whose later phases write nothing can still be closed"
shape = "bdd"
effort = "default"
refs = ["packages/isidium-factory/src/isidium/factory/runner.py::_carry", "packages/isidium-factory/src/isidium/factory/runner.py::run_phase", "packages/isidium-factory/src/isidium/factory/ledger.py::Ledger"]
surfaces = ["packages/isidium-factory/src/isidium/factory/runner.py", "tests/factory/test_carry_records_its_head.py", "tests/factory/test_v4a.py"]
priority = "P1"

[narrative]
feature = "a run that carried finished work and found nothing left to do closes like any other run"

[[rules]]
id = "R1"
text = "When a carry commits the carried work, the run's head_sha becomes that commit and its surfaces_actual the carried files, in the ledger, before any phase runs"

[[rules]]
id = "R2"
text = "A carried run whose later phases commit nothing ends with the carry commit as its head, so close finds the pull request's head equal to the run's"

[[rules]]
id = "R3"
text = "A carried run whose build commits more advances its head past the carry commit, as today"

[[rules]]
id = "R4"
text = "A carry that replays no files commits nothing and leaves the run's head as it was"

[[guidance.avoid]]
id = "A1"
option = "changing close to accept a run with no head"
because = "close.pr-mismatch is right: the run's own record must name the head it produced"

[[guidance.constraints]]
id = "C1"
text = "the head is recorded through Ledger.advance, whose signature is unchanged; the billing class passed is None, so an earlier or later phase's class stands (COALESCE)"
because = "advance is the one write for a run further along but not over; the carry draws on no lane"

[[guidance.constraints]]
id = "C2"
text = "only runner.py, this card's test file and tests/factory/test_v4a.py change; no Protocol, dataclass or signature changes, so no test double elsewhere is touched"
because = "checked when filing (the card-writing checklist): _carry's callers and ledger.advance's signature stay as they are"

[[guidance.constraints]]
id = "C3"
text = "tests/factory/test_v4a.py changes only the carried-run test whose assertion reads surfaces_actual is None (around line 991) and its docstring: they now say a run claims the files its carry commit carried, the carried-from run named on that commit, and a phase that wrote nothing still adds nothing of its own"
because = "the owner, on r-34's question (2026-09-30): the carry commit carries the run's own Factory-Run and Factory-Carried trailers and the pull request holds those files, so the run produced them on its branch"

[[acceptance.scenarios]]
id = "S1"
kind = "test-marker"
title = "the carry commit becomes the run's head"
rule = "R1"
observable = { test = "tests/factory/test_carry_records_its_head.py::test_the_carry_commit_becomes_the_runs_head" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "a carry whose build writes nothing ends with the carry commit as head"
rule = "R2"
observable = { test = "tests/factory/test_carry_records_its_head.py::test_a_carry_whose_build_writes_nothing_ends_with_the_carry_head" }

[[acceptance.scenarios]]
id = "S3"
kind = "test-marker"
title = "a build that commits more advances past the carry commit"
rule = "R3"
observable = { test = "tests/factory/test_carry_records_its_head.py::test_a_build_that_commits_more_advances_past_the_carry" }

[[acceptance.scenarios]]
id = "S4"
kind = "test-marker"
title = "a carry with no files leaves the head alone"
rule = "R4"
observable = { test = "tests/factory/test_carry_records_its_head.py::test_a_carry_with_no_files_leaves_the_head_alone" }
```

## Scope

Found on 2026-09-30 with r-33 (card 20), the first carry whose success path had nothing left to build: r-32 ended failed:budget with its work complete, r-33 carried it (commit 60db3b6, plan-author: r-33 carries r-32), its build wrote nothing, and the ledger's head_sha stayed None because runner._carry commits without advancing the head. #89 merged, close refused close.pr-mismatch (PR head 60db3b6, run head None), and card 20 had to be closed by the owner's accept --close after a demotion abandoned r-33.

The owner ruled (2026-09-30): file it, P1.

Not in scope: the carry of a parked run (V4a-ii-b Q-B3); a carried patch that carries a live mutation (a finding recorded 2026-09-28).

## History

```toml
history = [
  { seq = 1, at = "2026-09-30T17:12:14Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:e71c8581ac0789a2a7f32a596d9b44f0eac7a28efcd8d02cba2bd9bb6c08953a", h = "sha256:c8fd9bdfe50ddfc14e03df60e33905a547b562a97267228b193d381f8ede4d40" },
  { seq = 2, at = "2026-09-30T17:12:40Z", by = "amodal1@users.noreply.github.com", act = "ratified", fields = ["status"], build = "sha256:e71c8581ac0789a2a7f32a596d9b44f0eac7a28efcd8d02cba2bd9bb6c08953a", h = "sha256:bc0cfa8752c4b05241d4fcf591b8920be79d9de2b406bfecf94bd8ee78d0a821", batch = 47 },
  { seq = 3, at = "2026-10-01T00:05:43Z", by = "amodal1@users.noreply.github.com", act = "demoted", fields = ["guidance", "status", "surfaces"], build = "sha256:2b835597b5747b53489b54dffbc7b84ab5a083d664a24738aaa6804f0c779f47", h = "sha256:dec178e162adedd6d61f9df2b6090cbfbd09dc84692f9811f5a3a7646545bc2b", sig = "ed25519:5a6c85e20ab2a6eecc5d6df4f873f9af746b98a33d923c3302a900c365984ae8:KBM1/4mcR6x1Aa7qsTYRXGsCDxD0i1EMusSeDwworX6t1K/t9WPJtIrLvhGbfBVneNxV+EqnqArxMvpMrNbNCw==" },
  { seq = 4, at = "2026-10-01T00:06:06Z", by = "amodal1@users.noreply.github.com", act = "ratified", fields = ["status"], build = "sha256:2b835597b5747b53489b54dffbc7b84ab5a083d664a24738aaa6804f0c779f47", h = "sha256:e113b84d0f1b851ee0e73bb5dc34e00b51b5b47b6c8642a72fabc1496c8898b4", batch = 48 },
]
```
