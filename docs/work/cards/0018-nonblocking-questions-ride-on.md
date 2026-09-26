```toml
schema = 1
id = 18
kind = "story"
status = "draft"
source = "session"
title = "Only a blocking question parks a plan; a plan's non-blocking questions ride on to the refuter and judge"
shape = "bdd"
effort = "default"
refs = ["packages/isidium-factory/src/isidium/factory/gate.py::next_step", "packages/isidium-factory/src/isidium/factory/artifacts.py::Plan"]
surfaces = ["packages/isidium-factory/src/isidium/factory/gate.py", "packages/isidium-factory/src/isidium/factory/artifacts.py", "tests/factory/test_gate_nonblocking_questions.py"]
priority = "P2"

[narrative]
feature = "a plan author can state an assumption it made instead of stopping the run, and only a question the plan cannot be written without costs the owner a round"

[[rules]]
id = "R1"
text = "A plan's question carries its text, whether it is blocking, and, when it is not, the assumption the plan made in its place"

[[rules]]
id = "R2"
text = "A plan with any blocking question parks at once, card-ambiguity, before the lint or any refuter or judge call, as today"

[[rules]]
id = "R3"
text = "A plan whose questions are all non-blocking goes on to the lint and then the refuter, with its questions and assumptions in the plan artifact the refuter and judge read"

[[rules]]
id = "R4"
text = "A question written as a bare string, the form of every plan artifact before this card, reads as blocking, so a chain resumed over an older plan takes the path it took"

[[guidance.avoid]]
id = "A1"
option = "a separate park or verdict for non-blocking questions"
because = "the refuter and judge already gate the plan: a wrong assumption is a finding, and the judge's revise or park is the existing exit"

[[guidance.constraints]]
id = "C1"
text = "the gate stays a pure function of the run's history and the payload"
because = "the same history gives the same step; a resumed chain must take the path it would have taken"

[[guidance.constraints]]
id = "C2"
text = "the plan-author prompt is not in this card's surfaces; the prompt that tells the author to mark questions blocking or not is card 15's plan-author v2, or a following prompt version"
because = "card 15 already writes plan-author v2; two cards writing one prompt version would collide"

[[acceptance.scenarios]]
id = "S1"
kind = "test-marker"
title = "a plan's question records blocking and its assumption"
rule = "R1"
observable = { test = "tests/factory/test_gate_nonblocking_questions.py::test_a_question_records_blocking_and_its_assumption" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "a blocking question parks at once"
rule = "R2"
observable = { test = "tests/factory/test_gate_nonblocking_questions.py::test_a_blocking_question_parks_at_once" }

[[acceptance.scenarios]]
id = "S3"
kind = "test-marker"
title = "non-blocking questions go on to the refuter"
rule = "R3"
observable = { test = "tests/factory/test_gate_nonblocking_questions.py::test_non_blocking_questions_go_on_to_the_refuter" }

[[acceptance.scenarios]]
id = "S4"
kind = "test-marker"
title = "a bare-string question from an older plan reads as blocking"
rule = "R4"
observable = { test = "tests/factory/test_gate_nonblocking_questions.py::test_a_bare_string_question_reads_as_blocking" }
```

## Scope

Found on 2026-09-25/26: five plan-phase parks (r-15, r-16, r-17 on card 13; r-20 on card 14, and r-13's first round) raised questions the plan author had already answered sensibly itself, and the owner took the plan's own reading every time. r-20's single question said of itself that it does not stop the build. Each park cost a full round, about $2-4 and 7-12 minutes, and a signed demotion and ratification to answer.

The owner ruled: file a card so non-blocking questions ride on. The gate (gate.py) parks on any question today [owner, 2026-09-23]; this card narrows that to blocking ones.

In scope: the typed question, the gate's rule, the old artifacts' reading, the tests.

Not in scope: the prompt telling the plan author to mark questions (C2, card 15's prompt or a later one); surfacing a closed run's non-blocking questions to the owner, e.g. in the pull request's body (a following card if wanted); the review gate.

## History

```toml
history = [
  { seq = 1, at = "2026-09-26T16:22:33Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:0938be5a6bb066c6355e2eddbefd70ece3bc3d9e7f820a3211db2e8734c2019d", h = "sha256:61d71342329560901628dd247e77d7d63f1e511b3c0dfe93098e5310eb322fe4" },
]
```
