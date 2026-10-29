```toml
schema = 1
id = 72
kind = "story"
status = "draft"
source = "session"
title = "The ratify dry run refuses what the signed act refuses"
shape = "bdd"
effort = "default"
refs = ["packages/isidium-store/src/isidium/store/client/locus.py::preflight", "packages/isidium-store/src/isidium/store/server/refs.py"]
surfaces = ["packages/isidium-store/src/isidium/store/client/locus.py", "tests/store/test_dry_run_parity.py"]
priority = "P1"

[narrative]
feature = "ready: true means the signature will be accepted"

[[rules]]
id = "R1"
text = "a card whose refs include a path the signed act refuses (ref.inside-root, ref.unresolved) is refused by the dry run with the same rule id and path"

[[guidance.constraints]]
id = "C9"
text = "every file the card changes passes ruff check, ruff format --check and mypy --strict, by path"
because = "r-38 and r-39 each lost a whole run to a one-line style miss"

[[guidance.constraints]]
id = "C8"
text = "no scenario passes by skipping"
because = "card 61's rule"

[[acceptance.scenarios]]
id = "S1"
kind = "test-marker"
title = "the dry run and the signed act agree on a ref the signer refuses"
rule = "R1"
observable = { test = "tests/store/test_dry_run_parity.py::test_the_dry_run_refuses_what_the_signed_act_refuses" }
```

## Scope

Found 2026-10-27: the first --sign of card 57 refused `ref.inside-root @ refs: docs/work/cards/0043-...` after the dry run said `ready: true` for the same card. Recorded then as 'not yet carded'.

## History

```toml
history = [
  { seq = 1, at = "2026-10-29T21:06:52Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:0a472c7c2bb071fa42e7e55acb5686955588304b909bef18b0c17df1ecca20bd", h = "sha256:20b3bc1e0a4be1ea55eae3945e1aa66b34b6fc32c666f04af6178299bc70ed84" },
]
```
