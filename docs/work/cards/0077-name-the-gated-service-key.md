```toml
schema = 1
id = 77
kind = "story"
status = "draft"
source = "session"
title = "A policy entry names the service key the code gate protects, owner grants count only for it, and the realm carve-out needs identity mode"
shape = "bdd"
depends_on = [56]
effort = "default"
refs = ["packages/isidium-store/src/isidium/store/core/chain.py", "packages/isidium-store/src/isidium/store/server/store.py", "packages/isidium-store/src/isidium/store/core/derive.py", "packages/isidium-store/src/isidium/store/registry/config.py", "tests/store/test_remote_signer.py", "tests/store/test_enrol_signer.py"]
surfaces = ["packages/isidium-store/src/isidium/store/core/chain.py", "packages/isidium-store/src/isidium/store/server/store.py", "packages/isidium-store/src/isidium/store/core/derive.py", "packages/isidium-store/src/isidium/store/registry/config.py", "tests/store/test_remote_signer.py", "tests/store/test_gated_service_key.py", "tools/mutations/gated-service-key.toml", "deploy/README.md"]
priority = "P0"

[narrative]
feature = "a key enrolled with only the file key's co-signature grants nothing, and a realm binding needs identity mode"

[[rules]]
id = "R1"
text = "the policy chain records the code-gated service key as its own policy act (the plan names it; its ref is {key_fpr, tenant, from}, as the binding's is), signed by the pinned key and co-signed by that key, and written only by enrol_signer; a chain with no such entry keeps today's meaning (r-65 A1)"

[[rules]]
id = "R2"
text = "once that entry holds, an owner-authored grant (a binding that is not the realm's) counts only for the recorded fingerprint, so a key enrolled with the file key's own co-signature grants nothing (r-65 A1)"

[[rules]]
id = "R3"
text = "the realm carve-out in _binding_kind applies only when identity is enabled, as card 56's R4 parenthetical reads (r-65 F1)"

[[rules]]
id = "R4"
text = "tests/store/test_remote_signer.py::both() enrols the service key through enrol_signer in place of the pin-mode realm stand-in"

[[rules]]
id = "R5"
text = "the README replaces the hardening card's A1 note with the closed behaviour and says in one sentence what is NOT closed: in pin mode the file key still verifies as an owner key (measured 2026-11-03), so this card does not make the code gate bind against someone holding the file key; the owner's ruling is that the allowance's lapse limits the pin for dispatch and card 81 retires it as an owner key"

[[guidance.constraints]]
id = "C4"
text = "tools/mutations/gated-service-key.toml commits a mutation that counts an owner grant for an unrecorded fingerprint and one that applies the realm branch in pin mode; each kill is checked against this card's own test file only, and the builder does not run tools/mutate.py (the host's mutation step does)"
because = "the card-writing checklist, and r-62's two build aborts while the builder ran mutations"

[[guidance.constraints]]
id = "C5"
text = "the new act is added wherever the policy acts are listed (core/derive.py and registry/config.py POLICY_ACTS); a test fails when the two lists disagree"
because = "measured 2026-11-03: POLICY_ACTS is declared in both, plus two lists in derive.py"

[[guidance.constraints]]
id = "C6"
text = "the pin is NOT retired here: verify_entry's pin clause is unchanged, and a scenario asserts it so (the retirement is card 81)"
because = "owner ruling 2026-11-03: Part 2 option C, the pin stays an owner key and its limit is the allowance; measured 2026-11-03 that the pin verifies as owner after enrolment"

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
title = "an owner grant for an unrecorded fingerprint grants nothing once the entry holds"
rule = "R2"
observable = { test = "tests/store/test_gated_service_key.py::test_an_unrecorded_fingerprint_grants_nothing" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "the gated-key entry is written only by enrol_signer, signed by the pin and co-signed by the key"
rule = "R1"
observable = { test = "tests/store/test_gated_service_key.py::test_the_entry_is_written_by_enrol_signer_and_signed_twice" }

[[acceptance.scenarios]]
id = "S3"
kind = "test-marker"
title = "a chain with no gated-key entry keeps today's meaning"
rule = "R1"
observable = { test = "tests/store/test_gated_service_key.py::test_a_chain_without_the_entry_is_unchanged" }

[[acceptance.scenarios]]
id = "S4"
kind = "test-marker"
title = "a realm-authored binding grants only with identity enabled"
rule = "R3"
observable = { test = "tests/store/test_gated_service_key.py::test_the_realm_carve_out_needs_identity_mode" }

[[acceptance.scenarios]]
id = "S5"
kind = "test-marker"
title = "both() enrols through enrol_signer"
rule = "R4"
observable = { test = "tests/store/test_gated_service_key.py::test_the_remote_signer_fixture_enrols_through_the_verb" }

[[acceptance.scenarios]]
id = "S6"
kind = "test-marker"
title = "the README states what is not closed"
rule = "R5"
observable = { test = "tests/store/test_gated_service_key.py::test_the_readme_states_that_the_file_key_is_still_an_owner_key" }
```

## Scope

r-65 (card 56) review F1 and A1. Owner rulings 2026-11-03: Part 1 the fingerprint lives in a policy entry; Part 2 option C (the pin stays an owner key; card 81 retires it). Re-scoped from the 2026-11-01 draft, whose title promised that the code gate binds; measured 2026-11-03 that it would not, because verify_entry accepts the pin in pin mode with or without a binding.

## History

```toml
history = [
  { seq = 1, at = "2026-11-01T04:30:34Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "depends_on", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:6e3ec12d04fcdbed59a78a03c8157fd386de16255872b999bfbf8cb34f337cee", h = "sha256:2c7c90331571c2370318c5136b9383b992f5ead5f33c1b7ca0e8e348afd72d6d" },
  { seq = 2, at = "2026-11-03T14:50:40Z", by = "amodal1@users.noreply.github.com", act = "amended", fields = ["acceptance", "guidance", "refs", "rules", "scope", "surfaces", "title"], build = "sha256:bb920690693aa2a6d29f7a79c1938cdec2413dd3ccfb655d084dec9fad4f09bc", h = "sha256:4a878544332c866d156df726121c28259174eedc40d8f5b1f5481bc62b63451b" },
]
```
