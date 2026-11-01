```toml
schema = 1
id = 76
kind = "story"
status = "ratified"
source = "session"
title = "Enrolment hardening: the pin signature is guarded by a test and a mutation, a pin-only revoke cannot be backdated, and the README says what the code gate does and does not protect"
shape = "bdd"
depends_on = [56]
effort = "default"
refs = ["packages/isidium-store/src/isidium/store/core/chain.py", "tests/store/test_enrol_signer.py", "deploy/README.md"]
surfaces = ["packages/isidium-store/src/isidium/store/core/chain.py", "packages/isidium-store/src/isidium/store/server/store.py", "tests/store/test_enrol_hardening.py", "tools/mutations/enrol-hardening.toml", "deploy/README.md"]
priority = "P0"

[narrative]
feature = "the enrolment r-65 built holds under the reviewer's F2, F3, F5 and F6, and the README states the A1 limit"

[[rules]]
id = "R1"
text = "binding_kind's check of the pinned key's signature is guarded: a test fails when it is deleted, and tools/mutations/enrol-hardening.toml commits that mutation (r-65 F2)"

[[rules]]
id = "R2"
text = "a pin-only revocation whose until is earlier than the revocation entry's own at is refused or ignored, never taken as an earlier end (r-65 F5)"

[[rules]]
id = "R3"
text = "the README's enrolment section tells the operator to bump STORE_COMMIT before the first enrol-signer, because cosig makes an older store image unable to read config.toml (r-65 F3)"

[[rules]]
id = "R4"
text = "the README says plainly that the co-signature proves possession of the bound key and not that an Aegis code was entered for this key: anything that can read the file key and append to the policy chain can still enrol a key of its own until card B names the gated key (r-65 A1, the owner's ruling 2026-11-01 option a)"

[[rules]]
id = "R5"
text = "no README line in the section this card edits exceeds the paragraph's 120-column wrap (r-65 F6)"

[[guidance.constraints]]
id = "C4"
text = "tools/mutations/enrol-hardening.toml commits a mutation that drops the pinned-key signature check in binding_kind and one that accepts a backdated pin-only revoke; each kill is checked against this card's own test file only, and the builder does not run tools/mutate.py (the host's mutation step does)"
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
id = "C10"
text = "S2's legitimate pin-only revoke control writes until equal to the entry's own at: through the store's own path (enrol() then enrol(revoke=fpr)) or a hand-built _binding_entry whose ref until is the at it is given; it is never built from forge(..., until=st.now()), because the test clock advances 7 s per call (tests/store/conftest.py:41-43) and forge reads it again for its own at"
because = "r-67 parked at the plan gate (round 2, judge): the control's until fell 7 s before its at, so the new guard rejected a correct revoke and S2 was red on correct code"

[[guidance.constraints]]
id = "C11"
text = "every fact the plan cites about the worktree (a line number, a line length, how many times a helper reads the clock) is measured in the worktree and the measurement named in the plan"
because = "r-67 round 1 assumed the overlong README line was in the enrolment section (it is line 1550, in 'The order matters'); round 2 assumed forge reads the clock once"

[[acceptance.scenarios]]
id = "S1"
kind = "test-marker"
title = "deleting the pin signature check fails a test"
rule = "R1"
observable = { test = "tests/store/test_enrol_hardening.py::test_a_binding_with_a_bad_pin_signature_grants_nothing" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "a backdated pin-only revoke does not end a grant earlier"
rule = "R2"
observable = { test = "tests/store/test_enrol_hardening.py::test_a_backdated_pin_only_revoke_is_not_taken" }

[[acceptance.scenarios]]
id = "S3"
kind = "test-marker"
title = "the README tells the operator to bump STORE_COMMIT first"
rule = "R3"
observable = { test = "tests/store/test_enrol_hardening.py::test_the_readme_names_the_store_commit_bump" }

[[acceptance.scenarios]]
id = "S4"
kind = "test-marker"
title = "the README states the A1 limit"
rule = "R4"
observable = { test = "tests/store/test_enrol_hardening.py::test_the_readme_states_what_the_code_gate_protects" }

[[acceptance.scenarios]]
id = "S5"
kind = "test-marker"
title = "no line in the edited section exceeds 120 columns"
rule = "R5"
observable = { test = "tests/store/test_enrol_hardening.py::test_the_enrolment_section_is_wrapped" }
```

## Scope

r-65 (card 56) review, owner ruling 2026-11-01: push r-65 as is; F2, F3, F5, F6 and the A1 README note go in this follow-up (fixup cannot take review findings: it reads red checks only). F2 is the reason this is P0: with the pinned-key check deleted every test passes.

## History

```toml
history = [
  { seq = 1, at = "2026-11-01T04:30:26Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "depends_on", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:89db35ef0dfa8f00c291f52cc1c8aad3ab88475ac6b8faa04e8ce35436d5920a", h = "sha256:ee2ddc13ead5c01510dadd64b593b69772e97741ea44315aca9190d1571509c3" },
  { seq = 2, at = "2026-11-01T04:37:33Z", by = "amodal1@users.noreply.github.com", act = "ratified", fields = ["status"], build = "sha256:89db35ef0dfa8f00c291f52cc1c8aad3ab88475ac6b8faa04e8ce35436d5920a", h = "sha256:957c85d5324ccc4fa9ffa3d838855281949be8d7918cf43143a4d93a7cab26e0", batch = 87 },
  { seq = 3, at = "2026-11-01T05:44:47Z", by = "amodal1@users.noreply.github.com", act = "demoted", fields = ["status"], build = "sha256:89db35ef0dfa8f00c291f52cc1c8aad3ab88475ac6b8faa04e8ce35436d5920a", h = "sha256:14f38b884da3f7ef33653f178a9495bc204cf4a15bc163354975b1d40591bf4b" },
  { seq = 4, at = "2026-11-01T05:45:13Z", by = "amodal1@users.noreply.github.com", act = "ratified", fields = ["status"], build = "sha256:89db35ef0dfa8f00c291f52cc1c8aad3ab88475ac6b8faa04e8ce35436d5920a", h = "sha256:3ee95c93da6b055d8430d7150bfbffb44edac41d89512499c62010d662d0974d", batch = 88 },
  { seq = 5, at = "2026-11-01T06:51:41Z", by = "amodal1@users.noreply.github.com", act = "demoted", fields = ["guidance", "status"], build = "sha256:a7c044d34c2026c2d458adad37932f16e7078578c288ad771c29f2a1b7105674", h = "sha256:80c40da0dbf597bf187e17d55b44bc7704dc8978985810b83ea09ad028f702c1", sig = "ed25519:5a6c85e20ab2a6eecc5d6df4f873f9af746b98a33d923c3302a900c365984ae8:yafmiKcDZbOqo9shev/FINlIPBQ2jBCJ4r1DdodT9K4xSuGDgfsoQFXTasvU+S4LbkFcZhbdY7UDNrrcGXcBBg==" },
  { seq = 6, at = "2026-11-01T06:52:06Z", by = "amodal1@users.noreply.github.com", act = "ratified", fields = ["status"], build = "sha256:a7c044d34c2026c2d458adad37932f16e7078578c288ad771c29f2a1b7105674", h = "sha256:ced305bde39ef1a72d7b1dabe44181bb60477c25d53591968d44393f32eb624f", batch = 89 },
]
```
