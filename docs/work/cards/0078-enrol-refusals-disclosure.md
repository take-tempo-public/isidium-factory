```toml
schema = 1
id = 78
kind = "story"
status = "ratified"
source = "session"
title = "The enrolment refusals have disclosure rows, so a caller's own bad argument is not reported as a retryable 503"
shape = "bdd"
depends_on = [56]
effort = "default"
refs = ["packages/isidium-store/src/isidium/store/core/disclosure.py", "packages/isidium-store/src/isidium/store/server/store.py"]
surfaces = ["packages/isidium-store/src/isidium/store/core/disclosure.py", "packages/isidium-store/src/isidium/store/server/store.py", "tests/store/test_enrol_disclosure.py"]
priority = "P2"

[narrative]
feature = "a bad --revoke is a 422 the caller can read"

[[rules]]
id = "R1"
text = "signer.not-bound, signer.no-pin and signer.pin-mismatch have disclosure rows with a caller-visible detail, and an enrolment refusal is not a 503 (r-65 F4)"

[[rules]]
id = "R2"
text = "the namespace choice (signer. against the planned enrol.) is stated at the site with its reason"

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
title = "a revoke of an unbound fingerprint is a 422 with its detail"
rule = "R1"
observable = { test = "tests/store/test_enrol_disclosure.py::test_a_bad_revoke_is_a_422_with_its_detail" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "the namespace reason is written at the site"
rule = "R2"
observable = { test = "tests/store/test_enrol_disclosure.py::test_the_namespace_reason_is_at_the_site" }
```

## Scope

r-65 (card 56) review F4, owner ruling 2026-11-01: schedule a follow-up card.

## History

```toml
history = [
  { seq = 1, at = "2026-11-01T04:30:41Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "depends_on", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:c1bd4d6efa33c3bbc509fc65561ff221e6577347d6dc1549ab3b91b41ebbb2e8", h = "sha256:a56ef9059f470ee921b6c5a47a0c86ec7dfac8d2b3357b3bd53823971347becb" },
  { seq = 2, at = "2026-11-02T03:19:00Z", by = "amodal1@users.noreply.github.com", act = "ratified", fields = ["status"], build = "sha256:c1bd4d6efa33c3bbc509fc65561ff221e6577347d6dc1549ab3b91b41ebbb2e8", h = "sha256:696c80e6bf388de3401c54f8087bb0b08e020cd1ac0c850c11501a41ede802e4", batch = 90 },
]
```
