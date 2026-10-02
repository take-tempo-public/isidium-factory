```toml
schema = 1
id = 23
kind = "story"
status = "ratified"
source = "session"
title = "A phase that ends with a mutation still held restores the pristine file before its work is committed"
shape = "bdd"
effort = "default"
refs = ["packages/isidium-factory/src/isidium/factory/runner.py::_phase", "packages/isidium-factory/src/isidium/factory/runner.py::_keep_work", "tools/mutate.py", "packages/isidium-factory/src/isidium/factory/ledger.py::Ledger"]
surfaces = ["packages/isidium-factory/src/isidium/factory/runner.py", "tests/factory/test_phase_end_repairs_a_live_mutation.py", "tools/mutations/phase-end-repair.toml", "packages/isidium-factory/src/isidium/factory/ledger.py", "packages/isidium-factory/src/isidium/factory/checkout.py", "packages/isidium-factory/src/isidium/factory/container.py"]
priority = "P2"

[narrative]
feature = "a build that dies or finishes in the middle of a mutation check never commits, keeps or carries the mutated file"

[[rules]]
id = "R1"
text = "When a writing phase ends, ok or not, and before its change set is computed, a .mutation-in-flight.json at the worktree's root restores the file it names to its pristine bytes and is removed"

[[rules]]
id = "R2"
text = "The pristine bytes are restored only when they hash to the marker's own sha256; otherwise the file and the marker are left as they are and the run's record says the repair could not be verified"

[[rules]]
id = "R3"
text = "A repair, or a marker that could not be verified, is named on the run's record: the phase's ledger event carries repaired (the file and the mutation id) or repair_unverified (the file); when the phase that ended writes no phase row (a harness that died), the same rides the ended event's detail"

[[rules]]
id = "R4"
text = "A worktree with no marker is committed exactly as today"

[[rules]]
id = "R5"
text = "Before a container's next attempt starts, a marker the previous attempt left is dealt with the way R1-R3 deal with one at a phase's end: the named file restored (verified), the marker removed, and the repair recorded — so the attempt's kept patch holds the pristine file and the next attempt never meets a stale marker"

[[guidance.avoid]]
id = "A1"
option = "importing tools/mutate.py"
because = "tools/ is not part of the installed package the runner image carries; the marker's format is read here, not the tool"

[[guidance.avoid]]
id = "A2"
option = "refusing or failing the run over a marker"
because = "the work around the mutation is real work; restoring the one file keeps it, which is the point of keeping work at all"

[[guidance.constraints]]
id = "C1"
text = "the marker is read in tools/mutate.py's own format: a JSON object with file (repo-relative), sha256 (hex of the pristine bytes), pristine (base64) and id"
because = "one format, written by mutate.py's hold(); this reads what that writes"

[[guidance.constraints]]
id = "C2"
text = "tools/mutations/phase-end-repair.toml commits a mutation for R1 (the repair skipped) and one for R2 (the digest check skipped); each kill is checked against this card's own test file only, applied in place and restored; tools/mutate.py is --show only and never runs a mutation in the container"
because = "the card-writing checklist: a guard gets a committed spec, and mutate.py's whole-suite runs are what starved builds r-18, r-19 and r-27"

[[guidance.constraints]]
id = "C3"
text = "Ledger.phase keeps repaired and repair_unverified in the phase event beside the keys it already copies; its signature, the phases table's columns and every other key are unchanged; no other Protocol, dataclass or signature changes"
because = "the owner, on r-37's question (2026-10-02): the record must name every repair, and Ledger.phase copies a fixed key set, so a key runner.py adds is dropped silently; checked when amending: no test asserts a phase event's exact keys and Ledger.phase has one implementation"

[[guidance.constraints]]
id = "C4"
text = "checkout.set_aside's and Container.execute's signatures are unchanged; R5 is done between attempts, before set_aside clears the tree, and every test file that exercises the container's two attempts keeps passing; the card's own test file and every file it changes pass ruff check and ruff format --check"
because = "the owner, on r-38's review (2026-10-02): F1 (a marker surviving into a retry) and F2 (the refusal-with-result path untested) fold into this card; #96 went red on one ruff SIM105 in the test file"

[[acceptance.scenarios]]
id = "S1"
kind = "test-marker"
title = "a failed phase with a held mutation keeps the pristine file"
rule = "R1"
observable = { test = "tests/factory/test_phase_end_repairs_a_live_mutation.py::test_a_failed_phase_with_a_held_mutation_keeps_the_pristine_file" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "a finished phase with a held mutation commits the pristine file"
rule = "R1"
observable = { test = "tests/factory/test_phase_end_repairs_a_live_mutation.py::test_a_finished_phase_with_a_held_mutation_commits_the_pristine_file" }

[[acceptance.scenarios]]
id = "S3"
kind = "test-marker"
title = "a marker whose bytes do not match its digest restores nothing and is named"
rule = "R2"
observable = { test = "tests/factory/test_phase_end_repairs_a_live_mutation.py::test_an_unverifiable_marker_restores_nothing_and_is_named" }

[[acceptance.scenarios]]
id = "S4"
kind = "test-marker"
title = "the repair is named on the phase's row"
rule = "R3"
observable = { test = "tests/factory/test_phase_end_repairs_a_live_mutation.py::test_the_repair_is_named_on_the_phases_row" }

[[acceptance.scenarios]]
id = "S5"
kind = "test-marker"
title = "no marker, nothing changes"
rule = "R4"
observable = { test = "tests/factory/test_phase_end_repairs_a_live_mutation.py::test_no_marker_nothing_changes" }

[[acceptance.scenarios]]
id = "S6"
kind = "test-marker"
title = "a refusal carrying a result records the repair on its phase row"
rule = "R3"
observable = { test = "tests/factory/test_phase_end_repairs_a_live_mutation.py::test_a_refusal_carrying_a_result_records_the_repair_on_its_phase_row" }

[[acceptance.scenarios]]
id = "S7"
kind = "test-marker"
title = "a marker left by a first attempt is repaired before the second attempt"
rule = "R5"
observable = { test = "tests/factory/test_phase_end_repairs_a_live_mutation.py::test_a_marker_left_by_a_first_attempt_is_repaired_before_the_second" }
```

## Scope

Found 2026-09-28 with r-27 and r-28 (card 19): r-27's build died twice inside tools/mutate.py's mutation run, the kept patch captured guard.py with M1 still applied (return False for return True), and the carry replayed it into r-28, whose builder answered ok. A hand mutation check caught it before the pull request; CI's green bar would have gone red on it too, so the cost was a wasted cycle, not a bad merge. mutate.py holds the pristine bytes in a git-ignored .mutation-in-flight.json at the repository root, so the marker is in the worktree at the phase's end but never in the patch.

The owner ruled (2026-10-02): file the marker-repair card.

Not in scope, declared: a builder that mutates a file by hand, with no marker, is not caught here (CI's green bar and the review gate remain the defence); the builder prompt.

Amended 2026-10-02 after r-38, the review gate's first live run [owner: "Amend with F1/F2, rebuild fresh"]: the reviewer found F1 (attempt 1's git-ignored marker survives set_aside into attempt 2, whose phase-end repair would write attempt 1's bytes over attempt 2's work) and F2 (a PhaseRefusal carrying a result, the shape a retry exhaustion produces, was never tested with a marker); R5, S6 and S7 answer them. F3 (whether R1 may be narrowed to the write surface) is open, not ruled. #96 (r-38) is abandoned; it was red on one ruff error.

## History

```toml
history = [
  { seq = 1, at = "2026-10-02T17:16:30Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:723b4e71480b9b5544c65006637b4c5e765a229395b23d1c755bd92e3bdf02ce", h = "sha256:7ecab05b367c75aab047078a80548f2f4f620a17d0352972cea9a169a7dffd34" },
  { seq = 2, at = "2026-10-02T17:17:57Z", by = "amodal1@users.noreply.github.com", act = "ratified", fields = ["status"], build = "sha256:723b4e71480b9b5544c65006637b4c5e765a229395b23d1c755bd92e3bdf02ce", h = "sha256:fd980a79adcd661ab685af03b6a8e2b7bbc04a1e5a22c7b20fd13925986d4b59", batch = 53 },
  { seq = 3, at = "2026-10-02T17:24:42Z", by = "amodal1@users.noreply.github.com", act = "demoted", fields = ["guidance", "refs", "rules", "status", "surfaces"], build = "sha256:339e8aaddace3614a564c897cbfe4a01fd00711a0915cc155827fafcf4a51ba4", h = "sha256:7d17bf6c92f2d8e5f2a0995bf1660c54d03c317770c8372d92cff51d0c8e9e0e", sig = "ed25519:5a6c85e20ab2a6eecc5d6df4f873f9af746b98a33d923c3302a900c365984ae8:DovYuBe0N37x+pUP75OsKokXOS4cWl/EWi+ddi9h0h2x7OV6Ugo5afHyLnjb/WQkRssEg3/+ZI3YYuvUBeeCBQ==" },
  { seq = 4, at = "2026-10-02T17:25:39Z", by = "amodal1@users.noreply.github.com", act = "ratified", fields = ["status"], build = "sha256:339e8aaddace3614a564c897cbfe4a01fd00711a0915cc155827fafcf4a51ba4", h = "sha256:4a35ec1c69dcff0df751a92a1dd4a070913ebe727e8fa89e2a6e1545bfc3fb99", batch = 54 },
  { seq = 5, at = "2026-10-02T18:13:44Z", by = "amodal1@users.noreply.github.com", act = "demoted", fields = ["acceptance", "guidance", "rules", "scope", "status", "surfaces"], build = "sha256:1cf31d29569cdfbdfd109ef494a990231002d492a10dbcbd1ea8204b74b2ee0a", h = "sha256:afdf92ff86e012925d4b9bc3f3a3dc482cd83c5befd9eb7ebb8a48ca55db5f5c", sig = "ed25519:5a6c85e20ab2a6eecc5d6df4f873f9af746b98a33d923c3302a900c365984ae8:4P20yv/Cc/zpiU0oSkComrf0BmBJR6DiPag2HARFJL32B0As+H7lrcEjflSP3+eYsrhR2OZDMqRm13crBxuVCw==" },
  { seq = 6, at = "2026-10-02T18:41:16Z", by = "amodal1@users.noreply.github.com", act = "ratified", fields = ["status"], build = "sha256:1cf31d29569cdfbdfd109ef494a990231002d492a10dbcbd1ea8204b74b2ee0a", h = "sha256:507575332d6615c4b41e5d53b361cfeaf2b05ecad2c1e19a556638137a7e197c", batch = 55 },
]
```
