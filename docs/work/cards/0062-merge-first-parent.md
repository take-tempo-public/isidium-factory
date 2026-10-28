```toml
schema = 1
id = 62
kind = "story"
status = "ratified"
source = "session"
title = "The store reads a merge commit's changes against its first parent only, so a merged branch cut before a governed commit is not a second writer"
shape = "bdd"
effort = "default"
refs = ["packages/isidium-store/src/isidium/store/server/gitrepo.py:982-998", "packages/isidium-store/src/isidium/store/server/gitrepo.py:235-239", "packages/isidium-store/src/isidium/store/server/store.py::_first_governed_change", "packages/isidium-store/src/isidium/store/server/reconcile.py"]
surfaces = ["packages/isidium-store/src/isidium/store/server/gitrepo.py", "tests/store/test_merge_first_parent.py", "tools/mutations/merge-first-parent.toml"]
priority = "P0"

[narrative]
feature = "merging an older pull request no longer wedges every governed write until a land"

[[rules]]
id = "R1"
text = "GitCli.touched of a merge commit reports only the paths that differ from its first parent, each with the first parent's blob as its before, the same answer the in-memory double gives"

[[rules]]
id = "R2"
text = "after a pull request whose branch was cut before a governed commit is merged, and the merge changes no governed path against its first parent, the next governed write fast-forwards and succeeds"

[[rules]]
id = "R3"
text = "a merge that does change a governed path against its first parent is still refused git.push-rejected, naming that path"

[[guidance.avoid]]
id = "A1"
option = "proving the rules against the in-memory double alone"
because = "the double already diffs against the first parent (gitrepo.py:235-239); the defect is in GitCli's diff-tree flags, so only a real repository shows it"

[[guidance.constraints]]
id = "C1"
text = "the scenarios build real git repositories, each with core.autocrlf=false set in the repository"
because = "card 57 R5: a host's global core.autocrlf=true rewrites a test repository's files"

[[guidance.constraints]]
id = "C2"
text = "every other caller of touched() (store.py's reconciliation walk, reconcile.py, changes_under's double) keeps its behaviour for non-merge commits, and the suite stays green"
because = "checked when filing: touched() has four callers"

[[guidance.constraints]]
id = "C3"
text = "tools/mutations/merge-first-parent.toml commits a mutation restoring `-m --first-parent` in GitCli.touched; it is killed by this card's own test file alone"
because = "the card-writing checklist"

[[guidance.constraints]]
id = "C4"
text = "refusals and their rule ids are unchanged (git.push-rejected)"
because = "K4's rule id; callers cannot tell the pre-check from the push"

[[guidance.constraints]]
id = "C9"
text = "every file this card changes passes ruff check, ruff format --check and mypy --strict, by path"
because = "r-38 and r-39 each lost a whole run to a one-line style miss"

[[acceptance.scenarios]]
id = "S1"
kind = "test-marker"
title = "touched() of a merge with a stale second parent lists only its first-parent changes"
rule = "R1"
observable = { test = "tests/store/test_merge_first_parent.py::test_touched_reads_a_merge_against_its_first_parent" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "a write after merging a branch cut before a governed commit succeeds"
rule = "R2"
observable = { test = "tests/store/test_merge_first_parent.py::test_a_write_after_a_stale_branch_merge_succeeds" }

[[acceptance.scenarios]]
id = "S3"
kind = "test-marker"
title = "a merge that changes a governed path is still refused"
rule = "R3"
observable = { test = "tests/store/test_merge_first_parent.py::test_a_merge_changing_a_governed_path_is_refused" }
```

## Scope

Ruled [owner, 2026-10-28]: 'Card it, P0 (Recommended)'. Found 2026-10-28: after PR #117 (a branch cut before two land commits) merged as e47a70c, every governed write was refused `git.push-rejected @ 773012444b19: a governed path moved on the remote: e47a70c37c1a docs/work/BOARD.md`; three card writes were refused and burned ids 58-60. `git diff-tree -r -m --first-parent e47a70c` lists ci.yml and four docs/work paths (the diff against the stale second parent as well); `--diff-merges=first-parent` lists ci.yml alone. A land (which walks with log --diff-merges=first-parent) moved the store's head past the merge and unwedged it.

## History

```toml
history = [
  { seq = 1, at = "2026-10-28T17:22:34Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:c23014fa17b6e796c67eb987b610a8f054ae3f37713a7a6e3d42c396a394233a", h = "sha256:cef7f7ecbbf7c88279a5c602db0dbc5ecd486038d911b3c5ef274457c7e5dec3" },
  { seq = 2, at = "2026-10-28T21:24:28Z", by = "amodal1@users.noreply.github.com", act = "ratified", fields = ["status"], build = "sha256:c23014fa17b6e796c67eb987b610a8f054ae3f37713a7a6e3d42c396a394233a", h = "sha256:56a37687229a68a68f70f47720462f10afafd9c525f17cc575c6ea01f66910a9", batch = 77 },
]
```
