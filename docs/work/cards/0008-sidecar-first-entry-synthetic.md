```toml
schema = 1
id = 8
kind = "story"
status = "ratified"
source = "session"
title = "The sidecar's first entry says it is synthetic where the sidecar is read"
shape = "bdd"
effort = "default"
refs = ["deploy/README.md"]
surfaces = ["deploy/README.md"]
priority = "P3"

[narrative]
feature = "a reader who opens this tenant's sidecar learns that its first entry was landed by hand and is not a run, instead of reading e1 as something that happened"

[[rules]]
id = "R1"
text = "Where deploy/README.md describes this tenant's first land, it names e1 and says in the same sentence that it is not a run"

[[acceptance.scenarios]]
id = "S1"
kind = "file-assert"
title = "the README names e1 and says it is not a run"
rule = "R1"
observable = { path = "deploy/README.md", matches = "(?i)e1\\b[^\\n]{0,300}not a run" }
```

## Scope

From `s1`, landed by the synthetic run `r-synthetic-1` on 2026-09-09 and deferred by the owner on 2026-09-14. This tenant's `docs/work/state.json` and `docs/work/state/history.jsonl` begin with a report that no run produced: it was landed by hand through `isidium factory land` as L2's done-criterion. A reader who opens the sidecar and starts at `e1` has nothing telling them so, and `deploy/README.md` — the file the suggestion names, and where the standing-up of this tenant is recorded — describes the land without saying what it leaves behind.

In scope: a sentence or short paragraph in `deploy/README.md`, where a reader of the sidecar would meet it, naming `e1` as the synthetic first land and saying it is not a run. The acceptance check is a regular expression over the file and it is written out in the scenario below; satisfy it with a sentence that reads naturally, not by pasting the pattern.

Not in scope: editing `state.json` or `state/history.jsonl`, which are the store's own output and not writable by hand; creating a new file beside the sidecar, since `docs/work/` is the tracking root and a new file there is a governed-path question rather than a documentation edit; re-landing or repairing the synthetic report; and the four duplicate suggestions `s2`–`s5`, which are a landed fact and not this card's business.

If the right place for the sentence seems to be somewhere other than `deploy/README.md`, say so as a question rather than widening the plan.

## History

```toml
history = [
  { seq = 1, at = "2026-09-21T21:40:31Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "effort", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:3064ef768788b9f4b5ac963e3f27d4e77008d1b92f80541c7df8515c075c8867", h = "sha256:121cb19ebaa6e0bd70a9ed89eb39876b0ea89e491a5a945c31b3bf7342e398ba", batch = 16 },
]
```
