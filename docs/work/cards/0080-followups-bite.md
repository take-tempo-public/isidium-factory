```toml
schema = 1
id = 80
kind = "story"
status = "ratified"
source = "session"
title = "The signing-service follow-up checks bite: the one-call-bound checker sees wrapped lines, the README lists the judging-ref write, S5 fails on the base README, init respects identity mode, and the revoke guard is described as it is"
shape = "bdd"
depends_on = []
effort = "default"
refs = ["tests/store/test_remote_signer_followups.py", "deploy/README.md", "packages/isidium-store/src/isidium/store/server/store.py", "packages/isidium-store/src/isidium/store/core/chain.py"]
surfaces = ["tests/store/test_remote_signer_followups.py", "deploy/README.md", "packages/isidium-store/src/isidium/store/server/store.py", "packages/isidium-store/src/isidium/store/core/chain.py", "tests/store/test_followups_bite.py", "tools/mutations/followups-bite.toml"]
priority = "P2"

[narrative]
feature = "the checks r-66 added fail on the defects they name, and the docs say what the code does"

[[rules]]
id = "R1"
text = "the S3 checker in tests/store/test_remote_signer_followups.py matches a forbidden phrase across a hard-wrapped line break, and a test plants a wrapped one and names it (r-66 F2)"

[[rules]]
id = "R2"
text = "the README's list of owner-signed writes that wait for the phone includes the owner's judging-ref write (isidium write <id> --document ...) (r-66 F3)"

[[rules]]
id = "R3"
text = "S5's 'unverified' assertion fails on the base README and passes only with the sentence saying the listed acts read unverified until card 56's enrolment (r-66 F4)"

[[rules]]
id = "R4"
text = "init switches the genesis to the file key only on a store with no identity enabled; on an identity-enabled store it keeps the default signer (r-66 F5)"

[[rules]]
id = "R5"
text = "the docstring and the code comment on the pin-only revoke guard say what the guard does: it refuses an until earlier than the entry's own at, and does not claim a revocation cannot reach back past the moment it was made (r-68 F1)"

[[guidance.constraints]]
id = "C4"
text = "tools/mutations/followups-bite.toml commits a mutation that reverts the checker to line-at-a-time matching and one that makes init switch the genesis on an identity-enabled store; each kill is checked against this card's own test file only, and the builder does not run tools/mutate.py (the host's mutation step does)"
because = "the card-writing checklist, and r-62's two build aborts while the builder ran mutations"

[[guidance.constraints]]
id = "C8"
text = "no scenario passes by skipping"
because = "card 61's rule"

[[guidance.constraints]]
id = "C9"
text = "every file this card changes passes ruff check, ruff format --check and mypy --strict, by path"
because = "r-38 and r-39 each lost a whole run to a one-line style miss"

[[guidance.constraints]]
id = "C11"
text = "every fact the plan cites about the worktree (a line number, a line length, how many times a helper reads the clock) is measured in the worktree and the measurement named in the plan"
because = "r-67 parked twice at the plan gate on unmeasured worktree facts"

[[acceptance.scenarios]]
id = "S1"
kind = "test-marker"
title = "a hard-wrapped forbidden phrase is named"
rule = "R1"
observable = { test = "tests/store/test_followups_bite.py::test_the_checker_sees_a_wrapped_phrase" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "the README lists the judging-ref write"
rule = "R2"
observable = { test = "tests/store/test_followups_bite.py::test_the_readme_lists_the_judging_ref_write" }

[[acceptance.scenarios]]
id = "S3"
kind = "test-marker"
title = "the unverified assertion fails on the base README"
rule = "R3"
observable = { test = "tests/store/test_followups_bite.py::test_the_unverified_sentence_is_what_the_assertion_reads" }

[[acceptance.scenarios]]
id = "S4"
kind = "test-marker"
title = "init keeps the default signer on an identity-enabled store"
rule = "R4"
observable = { test = "tests/store/test_followups_bite.py::test_init_respects_identity_mode" }

[[acceptance.scenarios]]
id = "S5"
kind = "test-marker"
title = "the guard's description matches what it compares"
rule = "R5"
observable = { test = "tests/store/test_followups_bite.py::test_the_revoke_guard_is_described_as_it_is" }
```

## Scope

r-66 (card 75, PR #124) review F2-F5 left open by the owner's ruling to merge as is, and r-68 (card 76, PR #125) F1, a wording overstatement. F2 is a real checker gap; F3-F5 are minor. Owner ruling 2026-11-01.

## History

```toml
history = [
  { seq = 1, at = "2026-11-02T03:14:54Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "depends_on", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:3d0c6b2d9e430d935357b0cf969b6018b68170a89b6e0f8ad69bcf569bd27747", h = "sha256:2297b64dd905c205412c32c48aff6a348a7d7b4a0e8b89defe25d14a974c0099" },
  { seq = 2, at = "2026-11-02T03:19:00Z", by = "amodal1@users.noreply.github.com", act = "ratified", fields = ["status"], build = "sha256:3d0c6b2d9e430d935357b0cf969b6018b68170a89b6e0f8ad69bcf569bd27747", h = "sha256:870fbfa6237263eee1bd02dbde4dd2f0e07ccc7f07dc9de0a220ab1f7306e6cf", batch = 90 },
]
```
