```toml
schema = 1
id = 15
kind = "story"
status = "ratified"
source = "session"
title = "A card's next plan is handed the question its last run parked on"
shape = "bdd"
effort = "default"
refs = ["packages/isidium-factory/src/isidium/factory/gate.py::inputs_for", "packages/isidium-factory/src/isidium/factory/runner.py::_park", "packages/isidium-factory/src/isidium/factory/artifacts.py::ParkQuestion", "prompts/plan-author/v1.md"]
surfaces = ["packages/isidium-factory/src/isidium/factory/gate.py", "packages/isidium-factory/src/isidium/factory/runner.py", "prompts/plan-author/v2.md", "tests/factory/test_plan_is_handed_the_previous_park.py"]
priority = "P2"

[narrative]
feature = "a run on a card whose last run parked starts from what the gate already found, so the plan author does not pay again for a finding the owner has answered"

[[rules]]
id = "R1"
text = "When the latest run the ledger holds for the card ended parked and its question.json is readable, the first round's plan phase of the next run on that card is handed that question, named previous-park"

[[rules]]
id = "R2"
text = "A question.json that is missing, cannot be read or does not validate as a park question is not handed; the plan phase runs without it and the run's telemetry names the path"

[[rules]]
id = "R3"
text = "Only round one's plan is handed the previous park; the refuter, the judge, the builder and a revision are handed what they are handed today"

[[rules]]
id = "R4"
text = "A card whose latest run did not park is handed nothing new"

[[rules]]
id = "R5"
text = "The plan author's prompt says what previous-park is and that the card as ratified now is the specification, the previous park being context for why it changed"

[[rules]]
id = "R6"
text = "The plan author's prompt v2 also says that each question is marked blocking or not: blocking only when the plan cannot be written without the owner's answer, and otherwise the plan states the assumption it made in the question's place and carries on"

[[guidance.avoid]]
id = "A1"
option = "carrying the parked run's plan or story branch into the new run"
because = "the card changed after the park; the question is context for why, and the ratified card is the specification"

[[guidance.avoid]]
id = "A2"
option = "editing prompts/plan-author/v1.md"
because = "a prompt is versioned and signed as policy; v1 stays for the runs that ran on it"

[[guidance.constraints]]
id = "C1"
text = "the question is found at <deploy home>/runs/<run>/question.json, the path runner._park writes it to, and validated through artifacts.ParkQuestion"
because = "question.json is produced and hashed but has no reader today; this is its first, and it reads the typed model rather than a dict"

[[guidance.constraints]]
id = "C2"
text = "gate.inputs_for stays a function of its arguments: the previous park is found by the runner and passed in"
because = "the gate decides from what it is given, and its tests call it with no ledger or disk"

[[guidance.constraints]]
id = "C3"
text = "this card is built after card 18 merges: v2 names the question's fields as card 18's artifacts.Plan declares them, and changes no artifact or gate code of its own for R6"
because = "the owner, 2026-09-27: card 18's prompt instruction rides in this card's v2, so one prompt version, one runner rebuild and one config act carry both; the plan author's answer schema is rendered from artifacts.Plan, so the fields must exist before the prompt asks for them"

[[acceptance.scenarios]]
id = "S1"
kind = "test-marker"
title = "the first plan after a park is handed the parked question"
rule = "R1"
observable = { test = "tests/factory/test_plan_is_handed_the_previous_park.py::test_the_first_plan_after_a_park_is_handed_its_question" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "an unreadable question is not handed and is named"
rule = "R2"
observable = { test = "tests/factory/test_plan_is_handed_the_previous_park.py::test_an_unreadable_question_is_not_handed_and_is_named" }

[[acceptance.scenarios]]
id = "S3"
kind = "test-marker"
title = "later phases and the revision are handed what they were"
rule = "R3"
observable = { test = "tests/factory/test_plan_is_handed_the_previous_park.py::test_only_round_ones_plan_is_handed_the_previous_park" }

[[acceptance.scenarios]]
id = "S4"
kind = "test-marker"
title = "a card whose last run did not park is handed nothing new"
rule = "R4"
observable = { test = "tests/factory/test_plan_is_handed_the_previous_park.py::test_a_card_whose_last_run_did_not_park_is_handed_nothing_new" }

[[acceptance.scenarios]]
id = "S5"
kind = "test-marker"
title = "the plan author's v2 prompt names previous-park"
rule = "R5"
observable = { test = "tests/factory/test_plan_is_handed_the_previous_park.py::test_the_v2_prompt_names_previous_park" }

[[acceptance.scenarios]]
id = "S6"
kind = "test-marker"
title = "the v2 prompt asks for blocking and an assumption"
rule = "R6"
observable = { test = "tests/factory/test_plan_is_handed_the_previous_park.py::test_the_v2_prompt_asks_for_blocking_and_an_assumption" }
```

## Scope

Found on 2026-09-24. r-13 parked card 12 on a real finding. After the owner restated the card, r-14's first plan was handed nothing about that finding and paid for another round of revision before approval. The design record has an open dial, "reuse plan-as-context", and the owner ruled it on by default: a run dispatched after a question was disposed of gets the parked run's question and the judge's account as plan context. The park question's why_blocked carries the judge's account.

In scope: finding the card's latest parked run and its question, handing it to round one's plan, the plan author's v2 prompt, and the tests.

Not in scope: re-dispatch after an answer (V6); carrying work. After the merge, rebuilding the runner image and a signed config act setting [agents].plan-author.prompt to v2 are operational work, and the image label check refuses v2 until the image carries it.

## History

```toml
history = [
  { seq = 1, at = "2026-09-24T21:21:11Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:ea14bb67f76eb2ad0117f436e5441c2f86df130243a21af4a6a44a4ead0272a6", h = "sha256:2ed4c5d4ed2828506354a8bac8e22db423f6fda798a2ce9418e937314f2fc4ee" },
  { seq = 2, at = "2026-09-24T21:22:41Z", by = "amodal1@users.noreply.github.com", act = "ratified", fields = ["status"], build = "sha256:ea14bb67f76eb2ad0117f436e5441c2f86df130243a21af4a6a44a4ead0272a6", h = "sha256:866f82b4990867242d1522d11aa5bc78e7acbfb7d4d05dbcf89a2bd6ac4d8f85", batch = 26 },
  { seq = 3, at = "2026-09-27T22:54:32Z", by = "amodal1@users.noreply.github.com", act = "demoted", fields = ["acceptance", "guidance", "rules", "status"], build = "sha256:b860366050b28bd46806a0549cdcad0973032889d8b13db38130120b561c4506", h = "sha256:bbb62214909f2f8957674e258c264067faa4eee33ea81b5247075b499d006e53", sig = "ed25519:5a6c85e20ab2a6eecc5d6df4f873f9af746b98a33d923c3302a900c365984ae8:bT/y4jSzbNIS+RWwyprWmo+mDuMgaS+/qxKGEq0lP4fYwAU+W1PbW5002S+FuiJPx9HJpHOkrgOMoYN2a3qXAg==" },
  { seq = 4, at = "2026-09-27T22:54:52Z", by = "amodal1@users.noreply.github.com", act = "ratified", fields = ["status"], build = "sha256:b860366050b28bd46806a0549cdcad0973032889d8b13db38130120b561c4506", h = "sha256:52e86d69b05baf021a3bdc4aca80d7cc97f482b3aeda11c9b95d89c0d50140cb", batch = 36 },
]
```
