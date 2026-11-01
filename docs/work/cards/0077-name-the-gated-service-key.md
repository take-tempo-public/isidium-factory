```toml
schema = 1
id = 77
kind = "story"
status = "draft"
source = "session"
title = "A policy chain names the service key the code gate protects, owner grants count only for it, and the realm carve-out is scoped to identity mode"
shape = "bdd"
depends_on = [56]
effort = "default"
refs = ["packages/isidium-store/src/isidium/store/core/chain.py", "packages/isidium-store/src/isidium/store/server/store.py", "tests/store/test_remote_signer.py", "tests/store/test_enrol_signer.py"]
surfaces = ["packages/isidium-store/src/isidium/store/core/chain.py", "packages/isidium-store/src/isidium/store/server/store.py", "packages/isidium-store/src/isidium/store/core/grammar.py", "tests/store/test_remote_signer.py", "tests/store/test_gated_service_key.py", "tools/mutations/gated-service-key.toml", "deploy/README.md"]
priority = "P0"

[narrative]
feature = "a key enrolled with only the file key's co-signature grants nothing, and a realm binding needs identity mode"

[[rules]]
id = "R1"
text = "the policy chain records which key fingerprint is the code-gated service key, and an owner-authored grant counts only for that fingerprint (r-65 A1: the co-signature proves possession, not a code)"

[[rules]]
id = "R2"
text = "the realm carve-out in _binding_kind applies only when identity is enabled, as card 56's R4 parenthetical reads (r-65 F1)"

[[rules]]
id = "R3"
text = "tests/store/test_remote_signer.py::both() enrols the service key through enrol_signer in place of the pin-mode realm stand-in"

[[rules]]
id = "R4"
text = "the README's A1 note from the hardening card is replaced by the closed behaviour"

[[guidance.constraints]]
id = "C4"
text = "tools/mutations/gated-service-key.toml commits a mutation that counts an owner grant for an unrecorded fingerprint and one that applies the realm branch in pin mode; each kill is checked against this card's own test file only, and the builder does not run tools/mutate.py"
because = "the card-writing checklist"

[[guidance.constraints]]
id = "C5"
text = "the design is the owner's to rule before signing: where the gated fingerprint lives (policy entry, config key or binding field) changes 03 section 5.5 and 1.12; the card is not signed until the plan's open question is answered"
because = "r-65 suggestions, A1 option b"

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
title = "an owner grant for an unrecorded fingerprint grants nothing"
rule = "R1"
observable = { test = "tests/store/test_gated_service_key.py::test_an_unrecorded_fingerprint_grants_nothing" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "a realm-authored binding grants only with identity enabled"
rule = "R2"
observable = { test = "tests/store/test_gated_service_key.py::test_the_realm_carve_out_needs_identity_mode" }

[[acceptance.scenarios]]
id = "S3"
kind = "test-marker"
title = "both() enrols through enrol_signer"
rule = "R3"
observable = { test = "tests/store/test_gated_service_key.py::test_the_remote_signer_fixture_enrols_through_the_verb" }

[[acceptance.scenarios]]
id = "S4"
kind = "test-marker"
title = "the README no longer states the A1 gap"
rule = "R4"
observable = { test = "tests/store/test_gated_service_key.py::test_the_readme_drops_the_a1_note" }
```

## Scope

r-65 (card 56) review F1 and A1, owner rulings 2026-11-01: A1 accepted for now with this card as P0; F1 accepted for r-65 with the fix here (it needs tests/store/test_remote_signer.py in surfaces, which r-65 could not touch). Depends on 56 landing and on the hardening card for the README note.

## History

```toml
history = [
  { seq = 1, at = "2026-11-01T04:30:34Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "depends_on", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:6e3ec12d04fcdbed59a78a03c8157fd386de16255872b999bfbf8cb34f337cee", h = "sha256:2c7c90331571c2370318c5136b9383b992f5ead5f33c1b7ca0e8e348afd72d6d" },
]
```
