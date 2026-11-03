```toml
schema = 1
id = 81
kind = "story"
status = "draft"
source = "session"
title = "Once the service key is gated the file key stops being an owner key for later entries, and a recovery path exists that does not rest on the file key alone"
shape = "bdd"
depends_on = [77]
effort = "default"
refs = ["packages/isidium-store/src/isidium/store/server/store.py", "packages/isidium-store/src/isidium/store/core/chain.py", "tests/store/test_enrol_signer.py"]
surfaces = ["packages/isidium-store/src/isidium/store/server/store.py", "packages/isidium-store/src/isidium/store/core/chain.py", "tests/store/test_pin_retired.py", "tools/mutations/pin-retired.toml", "deploy/README.md"]
priority = "P0"

[narrative]
feature = "the code gate binds against someone holding the file key, without unverifying the history the file key already signed"

[[rules]]
id = "R1"
text = "verify_entry counts the pinned key as an owner key only for an entry whose at is before the recorded gated key's from; entries before it keep verifying, so the history already signed by the pin (130 signed entries in the live tenant, measured 2026-11-03) stays verified"

[[rules]]
id = "R2"
text = "an owner act made after that moment and signed by the pin alone reads unverified, while the same act signed by the gated service key verifies"

[[rules]]
id = "R3"
text = "a pin-only revocation of the gated key ends the key's grant and does NOT make the pin an owner key again: the retirement outlives the revocation"

[[rules]]
id = "R4"
text = "a recovery path exists for a lost or unavailable service that does not rest on the file key alone; its form is the owner's to rule before this card is signed (see C5)"

[[rules]]
id = "R5"
text = "the README states the retirement, the date rule and the recovery procedure, and says what an operator does when the phone or the service is lost"

[[guidance.constraints]]
id = "C4"
text = "tools/mutations/pin-retired.toml commits a mutation that counts the pin for every entry again and one that restores the pin on revocation; each kill is checked against this card's own test file only, and the builder does not run tools/mutate.py (the host's mutation step does)"
because = "the card-writing checklist, and r-62's two build aborts while the builder ran mutations"

[[guidance.constraints]]
id = "C5"
text = "this card is NOT signed until the owner rules R4's recovery path; the candidates are a second offline recovery key recorded in policy, or re-initialising the tenant from a signed export; the pin-only revoke (card 56 R5) must not become that path, because revoking the gate would then reopen the pin"
because = "measured and argued 2026-11-03: with no recovery a lost phone or service leaves nothing able to sign as the owner, and a pin-only recovery is the A1 gap again"

[[guidance.constraints]]
id = "C6"
text = "the factory's own acts are unchanged: the lander holds land and show only and signs no owner acts, so no run, watcher or land path starts needing the phone"
because = "measured 2026-11-03: all 130 signed entries in the live tenant are the owner principal's, signed by the pin"

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
title = "a pin-only owner act after the gated key's from reads unverified"
rule = "R2"
observable = { test = "tests/store/test_pin_retired.py::test_a_pin_only_act_after_the_gate_is_unverified" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "entries before the gate keep verifying"
rule = "R1"
observable = { test = "tests/store/test_pin_retired.py::test_entries_before_the_gate_keep_verifying" }

[[acceptance.scenarios]]
id = "S3"
kind = "test-marker"
title = "the same act signed by the service key verifies"
rule = "R2"
observable = { test = "tests/store/test_pin_retired.py::test_the_service_key_still_verifies" }

[[acceptance.scenarios]]
id = "S4"
kind = "test-marker"
title = "revoking the gated key does not restore the pin"
rule = "R3"
observable = { test = "tests/store/test_pin_retired.py::test_a_revocation_does_not_restore_the_pin" }

[[acceptance.scenarios]]
id = "S5"
kind = "test-marker"
title = "the recovery path works without the file key alone"
rule = "R4"
observable = { test = "tests/store/test_pin_retired.py::test_recovery_does_not_rest_on_the_file_key_alone" }

[[acceptance.scenarios]]
id = "S6"
kind = "test-marker"
title = "the README states the retirement and the recovery"
rule = "R5"
observable = { test = "tests/store/test_pin_retired.py::test_the_readme_states_the_retirement_and_recovery" }
```

## Scope

Owner ruling 2026-11-03: card 77 closes the enrolment path only (option C, the pin stays an owner key); this card retires the pin as an owner key for entries after the gate. Measured 2026-11-03 in a scratchpad clone: after enrol_signer, an entry signed by the pin still verifies as owner (store.py verify_entry accepts pin == fpr when identity is not enabled), so until this card the code gate does not bind against a file-key holder. Open: R4's recovery path (C5).

## History

```toml
history = [
  { seq = 1, at = "2026-11-03T14:51:20Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "depends_on", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:2729d2c79d0cf9208acf4ef0ef587cf69c841cbf399dd0d8c5f19b053b42ba5e", h = "sha256:4f5dbaaf5c95a327ced7689eaae0b3ec9e0b2fe89ae429728d96fcc6b0a1ead0" },
]
```
