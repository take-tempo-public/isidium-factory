```toml
schema = 1
id = 35
kind = "story"
status = "ratified"
source = "session"
title = "The PR watcher never retries a refused action at the same head, so one stuck run cannot spend the day's fixup ceiling"
shape = "bdd"
effort = "default"
refs = ["packages/isidium-factory/src/isidium/factory/watch.py", "tests/factory/test_watch.py"]
surfaces = ["packages/isidium-factory/src/isidium/factory/watch.py", "tests/factory/test_watch_retries.py", "tests/factory/test_watch.py", "tools/mutations/watch-retries.toml"]
priority = "P1"

[narrative]
feature = "a refusal is answered once and flagged, never re-attempted every fifteen minutes against a ceiling the owner signed"

[[rules]]
id = "R1"
text = "a watcher fixup that was refused or raised at a head is not chosen again at that head; the run is flagged fixup-refused once, naming the refusal's rule"

[[rules]]
id = "R2"
text = "a watcher rerun that was refused or raised at a head is not chosen again at that head; the run is flagged rerun-refused once, naming the refusal's rule"

[[rules]]
id = "R3"
text = "red after a fixup invokes the fixup verb (which ends the run failed:gate with no model call) whether or not [watcher].fixup is on, below config@8 included, because it spends nothing; it is still flagged red-after-fixup"

[[rules]]
id = "R4"
text = "every watcher action whose verb refuses or raises releases its lease with the refusal's rule or the raised marker"

[[guidance.avoid]]
id = "A1"
option = "changing what the daily ceiling counts"
because = "the owner ruled the count as watcher-held fixup leases taken today (2026-10-04, 'As proposed'); R1 bounds a stuck run to one take, which is the fix"

[[guidance.avoid]]
id = "A2"
option = "a new table, file or column for the refusal history"
because = "the lease rows already carry action, head_sha and outcome (the owner: the lease is the history)"

[[guidance.constraints]]
id = "C1"
text = "tests/factory/test_watch.py's assertion that a Policy(False, 0) tenant only flags red-after-fixup changes to R3's behaviour; no other assertion there is weakened"
because = "checked when filing: test_watch.py pins card 31's gating, which R3 corrects"

[[guidance.constraints]]
id = "C2"
text = "tools/mutations/watch-retries.toml commits a mutation for R1 (a refused fixup chosen again) and one for R4 (a refusal leaves the lease unreleased); each kill is checked against this card's own test file only, applied in place and restored; tools/mutate.py is --show only"
because = "the card-writing checklist"

[[guidance.constraints]]
id = "C3"
text = "no new refusal and no new rule namespace"
because = "core/disclosure.py stays untouched"

[[guidance.constraints]]
id = "C4"
text = "every file this card changes passes ruff check, ruff format --check and mypy --strict, by path"
because = "r-38 and r-39 each lost a whole run to a one-line style miss"

[[acceptance.scenarios]]
id = "S1"
kind = "test-marker"
title = "a refused fixup is not chosen again at the same head and is flagged once"
rule = "R1"
observable = { test = "tests/factory/test_watch_retries.py::test_a_refused_fixup_is_not_chosen_again" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "a refused rerun is not chosen again at the same head and is flagged once"
rule = "R2"
observable = { test = "tests/factory/test_watch_retries.py::test_a_refused_rerun_is_not_chosen_again" }

[[acceptance.scenarios]]
id = "S3"
kind = "test-marker"
title = "red after a fixup ends through the verb with fixup off"
rule = "R3"
observable = { test = "tests/factory/test_watch_retries.py::test_red_after_fixup_ends_with_fixup_off" }

[[acceptance.scenarios]]
id = "S4"
kind = "test-marker"
title = "a refused action releases its lease with the rule"
rule = "R4"
observable = { test = "tests/factory/test_watch_retries.py::test_a_refused_action_releases_its_lease" }
```

## Scope

Found by r-48's review gate (card 31), verified against watch.py: `_fixup_ran` and `_rerun_at` count only actions that reached their success outcome, so a refused fixup or rerun is chosen again every pass; each fixup take is a watcher lease and counts against fixup_per_day, so one stuck run spends the day's ceiling (F1, major) and a refused rerun never escalates (F6). F2: card 31 gated red-after-fixup on the opt-in, which the ruled order (3) does not. F3: no test that a refused action releases its lease.

Not yet live: [watcher].fixup is off until the owner's config act; this lands before it.

Not in scope: F4 (UTC midnight unexplained), F5 (watch.jsonl growth), card 28's deferred UTC conversion.

## History

```toml
history = [
  { seq = 1, at = "2026-10-07T13:07:55Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:3e078b746ff4c018b4f67df1d2e8158957b4acd9f09123cc62c468bbccd2ef78", h = "sha256:078ad7d29b6eba8feccc2f5bcf69507c9912145c192c1710c12adc9222b141e9" },
  { seq = 2, at = "2026-10-07T15:01:14Z", by = "amodal1@users.noreply.github.com", act = "ratified", fields = ["status"], build = "sha256:3e078b746ff4c018b4f67df1d2e8158957b4acd9f09123cc62c468bbccd2ef78", h = "sha256:f48c424a92ea908b875d7f7cc147b3b5b7d0d981097bbfa2869d1f5b5f52201d", batch = 66 },
]
```
