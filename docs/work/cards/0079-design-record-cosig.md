```toml
schema = 1
id = 79
kind = "story"
status = "draft"
source = "session"
title = "The design record describes cosig, the grant and revoke binding kinds, and the rule that a pin-only binding can only end a grant"
shape = "bdd"
depends_on = [56]
effort = "default"
refs = ["docs/design/03-card-schema.md", "packages/isidium-store/src/isidium/store/core/chain.py"]
surfaces = ["docs/design/03-card-schema.md", "tests/unit/test_design_record_cosig.py"]
priority = "P2"

[narrative]
feature = "03 section 5.5 and 1.12 say what the code does"

[[rules]]
id = "R1"
text = "03 section 5.5 reads 'every key except h, sig, cosig, batch', matching chain.CHAIN_EXCLUDED"

[[rules]]
id = "R2"
text = "03 section 1.12's binding semantics describe cosig, the grant and revoke kinds, and that a pin-only binding can only end a grant"

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
title = "5.5 names cosig among the excluded keys"
rule = "R1"
observable = { test = "tests/unit/test_design_record_cosig.py::test_section_5_5_names_cosig" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "1.12 describes the binding kinds"
rule = "R2"
observable = { test = "tests/unit/test_design_record_cosig.py::test_section_1_12_describes_the_binding_kinds" }
```

## Scope

r-65 (card 56) review suggestion 3: the code comment at chain.py:29-32 is the only statement of the binding semantics. Docs card; owner said yes to drafting 2026-11-01.

## History

```toml
history = [
  { seq = 1, at = "2026-11-01T04:30:48Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "depends_on", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:23a12152ec38d187b92d1759424fde70272523c345f38f623533bf0cd0703529", h = "sha256:0f8a0895a6edd7c215326b8a6732dfc06dcb4759026718ee5d90ee611f51fe8b" },
]
```
