```toml
schema = 1
id = 56
kind = "story"
status = "draft"
source = "session"
title = "The owner enrols the signing service's key with a binding signed twice: by the pinned key, and by the service after an Aegis code"
shape = "bdd"
depends_on = [54]
effort = "default"
refs = ["packages/isidium-store/src/isidium/store/server/store.py", "packages/isidium-store/src/isidium/store/core/chain.py", "packages/isidium-store/src/isidium/store/server/api.py", "packages/isidium-store/src/isidium/store/client/cli.py", "packages/isidium-store/src/isidium/store/server/signer.py"]
surfaces = ["packages/isidium-store/src/isidium/store/server/store.py", "packages/isidium-store/src/isidium/store/core/chain.py", "packages/isidium-store/src/isidium/store/server/api.py", "packages/isidium-store/src/isidium/store/server/identity.py", "packages/isidium-store/src/isidium/store/client/cli.py", "packages/isidium-store/src/isidium/store/server/signer.py", "packages/isidium-signer/src/isidium/signer/service.py", "packages/isidium-signer/src/isidium/signer/http.py", "deploy/README.md", "tests/store/test_enrol_signer.py", "tools/mutations/enrol-signer.toml", "packages/isidium-store/src/isidium/store/core/grammar.py"]
priority = "P0"

[narrative]
feature = "the store trusts the service's key from the moment the owner enrols it, and only if both the owner's pinned key and the service's own key signed that"

[[rules]]
id = "R1"
text = "an owner verb (enrol-signer) asks the service for its key's fingerprint and a co-signature over the binding entry's chain hash; the service shows the request on the phone page as a key enrolment (the key's fingerprint, the tenant, the grant owner) and co-signs only after an Aegis code"

[[rules]]
id = "R2"
text = "the store writes a binding entry, ref = {key_fpr, grant: owner, tenant, from}, signed by the pinned key (the store's file-key signer) and carrying the service's co-signature by the bound key itself"

[[rules]]
id = "R3"
text = "a binding without a co-signature that verifies by its own key_fpr, or whose signature is not by the pinned key, grants nothing: a card signed by that key is not owner-signed"

[[rules]]
id = "R4"
text = "the realm's bindings (identity enabled, signed by the realm) keep working as today"

[[rules]]
id = "R5"
text = "enrol-signer --revoke writes a binding with until = now for that key, signed by the pinned key alone; signatures made before it still verify, later ones do not"

[[guidance.avoid]]
id = "A1"
option = "a binding signed by the file key alone"
because = "the owner, 2026-10-26/27 (remote-totp, chunk plan): 'Binding, signed twice'; anything that can read the file key could otherwise enrol a key of its own"

[[guidance.avoid]]
id = "A2"
option = "pinning a list of keys"
because = "the owner, 2026-10-26/27 (remote-totp, chunk plan): declined in favour of the binding"

[[guidance.constraints]]
id = "C1"
text = "binding_holds or its caller checks a binding's signatures before it counts; the reason and its cost are written at the site"
because = "checked when filing: chain.binding_holds (core/chain.py:205) checks membership only"

[[guidance.constraints]]
id = "C2"
text = "Store.bind's realm path is reused, not copied, where it fits"
because = "checked when filing: Store.bind (store.py:1113) is today's only binding writer, called from tests"

[[guidance.constraints]]
id = "C3"
text = "the co-signature sits outside the chain content, as sig and batch do"
because = "03 §5.5"

[[guidance.constraints]]
id = "C4"
text = "tools/mutations/enrol-signer.toml commits a mutation that counts a binding without its co-signature and one that accepts a co-signature by another key; each kill is checked against this card's own test file only"
because = "the card-writing checklist"

[[guidance.constraints]]
id = "C9"
text = "every file this card changes passes ruff check, ruff format --check and mypy --strict, by path"
because = "r-38 and r-39 each lost a whole run to a one-line style miss"

[[guidance.constraints]]
id = "C10"
text = "core/grammar.py gains exactly one change: \"cosig\" after \"sig\" in ENTRY_KEY_ORDER; tests/store/test_enrol_signer.py proves an entry carrying cosig round-trips through emit and parse, and that entries without it still parse and emit unchanged"
because = "r-64 parked (plan): ENTRY_KEY_ORDER is the whole allowlist, emit_entry drops any other key and the parsers refuse it; the owner ruled option 1 (add the surface) 2026-11-01"

[[acceptance.scenarios]]
id = "S1"
kind = "test-marker"
title = "enrolment shows on the page and co-signs after a code"
rule = "R1"
observable = { test = "tests/store/test_enrol_signer.py::test_enrolment_needs_a_code" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "the binding is signed by the pin and co-signed by the bound key"
rule = "R2"
observable = { test = "tests/store/test_enrol_signer.py::test_the_binding_is_signed_twice" }

[[acceptance.scenarios]]
id = "S3"
kind = "test-marker"
title = "a binding missing either signature grants nothing"
rule = "R3"
observable = { test = "tests/store/test_enrol_signer.py::test_a_half_signed_binding_grants_nothing" }

[[acceptance.scenarios]]
id = "S4"
kind = "test-marker"
title = "the realm's bindings still hold"
rule = "R4"
observable = { test = "tests/store/test_enrol_signer.py::test_realm_bindings_unchanged" }

[[acceptance.scenarios]]
id = "S5"
kind = "test-marker"
title = "revocation ends the key's grant from then on"
rule = "R5"
observable = { test = "tests/store/test_enrol_signer.py::test_revocation" }
```

## Scope

Ruled [owner, 2026-10-27]: enrolment by a 'Binding, signed twice'. The store checks a signature against the current pin, so the file key stays pinned and the service's key is bound beside it.

## History

```toml
history = [
  { seq = 1, at = "2026-10-27T16:39:55Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "depends_on", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:c2335b4ec4d4740e8418f41f129519f76dfdf8ab18b8063088614b1236612734", h = "sha256:869ec4d08ade04f1f0c5e380a8c2d3e8a9952714fa15048025cfb6f37ff9f98b" },
  { seq = 2, at = "2026-10-28T05:06:12Z", by = "amodal1@users.noreply.github.com", act = "ratified", fields = ["status"], build = "sha256:c2335b4ec4d4740e8418f41f129519f76dfdf8ab18b8063088614b1236612734", h = "sha256:fe69d68470cb59169c283765df228158517f7ea6507e1d0d3a6a6f0ed27173df", batch = 74 },
  { seq = 3, at = "2026-11-01T00:11:21Z", by = "amodal1@users.noreply.github.com", act = "demoted", fields = ["guidance", "status"], build = "sha256:e58388d240030d43842d10b611d2f549663013abf5e5d8ecd0244c3c6481ac32", h = "sha256:86bbdfc5875e18ccf530c8f74d0813102605e73bb6c8d859eca0589dfb547005", sig = "ed25519:5a6c85e20ab2a6eecc5d6df4f873f9af746b98a33d923c3302a900c365984ae8:IddOhuGL5XFNq6f1eJUSo7TsBPX7wTnSqsJjA8JlQf1qHMMvqT898QCucOzOq7aAL8e41WX8/yOmd3cHghtgDg==" },
  { seq = 4, at = "2026-11-01T00:11:55Z", by = "amodal1@users.noreply.github.com", act = "ratified", fields = ["status"], build = "sha256:e58388d240030d43842d10b611d2f549663013abf5e5d8ecd0244c3c6481ac32", h = "sha256:32c9b7e4ed60db918a18f8d0c76eed93befe290c8d923d2de5ad0e65aabdebc7", batch = 84 },
  { seq = 5, at = "2026-11-01T02:59:30Z", by = "amodal1@users.noreply.github.com", act = "demoted", fields = ["guidance", "refs", "status", "surfaces"], build = "sha256:2986d29428f829d055a27810ac937c6d065c65b431aa02dfb2327b604cee7bf0", h = "sha256:36dbe77ed60db22a9264f5b5f15634bd77c37006ce7e0d1a2679d0126351a247", sig = "ed25519:5a6c85e20ab2a6eecc5d6df4f873f9af746b98a33d923c3302a900c365984ae8:G9mRs6Q40gbqwcvSbyVG91uQ5GQXKr5TUWMWXVgNp9dwhWlOQ4YWTa+Pi/pR5y63qSkpFZbllvdzfqjQSVcwDw==" },
  { seq = 6, at = "2026-11-01T03:00:00Z", by = "amodal1@users.noreply.github.com", act = "ratified", fields = ["status"], build = "sha256:2986d29428f829d055a27810ac937c6d065c65b431aa02dfb2327b604cee7bf0", h = "sha256:ef684b0f860aca1365428cfa9a9fb8553e29ebf82e124c2da40b37bdef6c05af", batch = 85 },
  { seq = 7, at = "2026-11-01T03:00:42Z", by = "amodal1@users.noreply.github.com", act = "demoted", fields = ["refs", "status"], build = "sha256:990487175ddc159a0b7719c5129535874a9d10d1ae7f7bd3063ab2d4a34c0fda", h = "sha256:816a1aa2e60ccd28d9d07810116746f02a8702601e5753b82260d33ee2a7d469", sig = "ed25519:5a6c85e20ab2a6eecc5d6df4f873f9af746b98a33d923c3302a900c365984ae8:6GW/RfXWIqefltk9/vKutOl9UM2g9WT5u7u4JkrLjUNYzz6Xg3bhpga7oIo/c5LPbkh93/4FACdcUA3iEgLBAw==" },
]
```
