```toml
schema = 1
id = 22
kind = "story"
status = "draft"
source = "session"
title = "A test tenant checkout runs no background git maintenance, so copying it never races a lock"
shape = "bdd"
effort = "default"
refs = ["tests/store/conftest.py::tenant_checkout", "tests/store/test_verify_chain.py::tenant"]
surfaces = ["tests/store/conftest.py", "tests/store/test_fixture_checkout_is_quiet.py"]
priority = "P2"

[narrative]
feature = "the suite's copy of a built checkout is deterministic, so a red gate means a real failure"

[[rules]]
id = "R1"
text = "tenant_checkout sets maintenance.auto to false and gc.auto to 0 in the checkout it creates, before any later git command there"

[[rules]]
id = "R2"
text = "after a pull in such a checkout, no git process is left running in it, so a copy of the directory meets no lock and no temporary pack"

[[guidance.avoid]]
id = "A1"
option = "an ignore pattern on copytree for *.lock or tmp_pack_*"
because = "it hides the race instead of removing it, and a half-written pack would still be copied"

[[guidance.avoid]]
id = "A2"
option = "retrying the copy"
because = "a retry makes the flake rarer, not gone"

[[guidance.constraints]]
id = "C1"
text = "only tenant_checkout changes in conftest.py; its signature and what it returns are unchanged, so no caller changes"
because = "the card-writing checklist: every store test that builds a checkout calls it, and none asserts on git's maintenance settings"

[[acceptance.scenarios]]
id = "S1"
kind = "test-marker"
title = "the checkout disables git's automatic maintenance"
rule = "R1"
observable = { test = "tests/store/test_fixture_checkout_is_quiet.py::test_the_checkout_disables_automatic_maintenance" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "a pull leaves no git process behind in the checkout"
rule = "R2"
observable = { test = "tests/store/test_fixture_checkout_is_quiet.py::test_a_pull_leaves_no_git_process_behind" }
```

## Scope

Found 2026-09-27 → 2026-10-01: four red CI runs (#85's merge commit, #88 twice, #91's merge commit) on tests/store/test_verify_chain.py::test_an_intact_checkout_passes_and_every_document_is_named and tests/store/test_k7a.py::test_a_governed_card_cannot_leave_the_root_by_rename_at_either_door, both through test_verify_chain's tenant fixture, whose shutil.copytree copies a checkout right after a git pull. A pull can start git's detached auto-maintenance, which creates and removes .git/objects/maintenance.lock (and tmp_pack_* files) while the copy enumerates them. One cost r-24 its factory closure before card 20.

The owner ruled (2026-10-01): file it.

Not in scope: close's rerun of a red gate (card 20, done); any change to the store's own git use.

## History

```toml
history = [
  { seq = 1, at = "2026-10-01T02:42:19Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:a12e5d1210873417fb637b37a08f0448ca7579f9ba9bf736587f8d899f51db21", h = "sha256:46604c6e4c1875af04e082a606667faa5c3c35ba29e1b2155bb0496713fc28a7" },
  { seq = 2, at = "2026-10-01T02:44:22Z", by = "amodal1@users.noreply.github.com", act = "amended", fields = ["effort"], build = "sha256:bb1e0ec6de6a20b7eb46aa029d7dae583b2643ed7640c6d070aa27c43ef117c3", h = "sha256:ac467e0c12fbf34f90fedb38a964d1b545bdef7ffb16db04524392b69116550a" },
]
```
