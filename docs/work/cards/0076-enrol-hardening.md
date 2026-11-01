```toml
schema = 1
id = 76
kind = "story"
status = "draft"
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
]
```
