```toml
schema = 1
id = 75
kind = "story"
status = "draft"
source = "session"
title = "The signing service's remaining gaps: init pins the file key, the timeout leaves a post-signature margin, the entrypoint refuses a partial setting, and the docs say what waits"
shape = "bdd"
effort = "default"
refs = ["packages/isidium-store/src/isidium/store/server/store.py:1229-1236", "packages/isidium-store/src/isidium/store/client/cli.py", "packages/isidium-store/src/isidium/store/server/signer.py", "deploy/entrypoint.sh", "deploy/compose.yaml", "deploy/README.md"]
surfaces = ["packages/isidium-store/src/isidium/store/server/store.py", "packages/isidium-store/src/isidium/store/client/cli.py", "packages/isidium-store/src/isidium/store/server/signer.py", "deploy/entrypoint.sh", "deploy/compose.yaml", "deploy/README.md", "tests/store/test_remote_signer_followups.py", "tools/mutations/remote-signer-followups.toml"]
priority = "P1"

[narrative]
feature = "the signing service's wiring fails loudly and its documentation says what it does"

[[rules]]
id = "R1"
text = "`isidium init` signs the genesis act with the pinned file key (the held software-key signer), never with the remote-totp default, so a store holding the signing service still initialises without the phone and without pinning the service's key (r-63 F2)"

[[rules]]
id = "R2"
text = "serve refuses a --signing-service-timeout-s whose bound plus the store's post-signature work (the fetch, commit and push of the ratify's apply) can outlast the client channel's 660 s: the accepted maximum leaves a stated margin for that work, and the margin is a named constant (r-63 F3)"

[[rules]]
id = "R3"
text = "no help text, docstring or entrypoint message calls --signing-service-timeout-s a bound on one call; each says the setting bounds the wait for the owner and that a single round trip is only held by the per-call timeout, and a test fails when a source file under packages/ or deploy/ says 'one call's bound' or 'one call's timeout' about it (the ratchet: r-57 F2, r-61 F2 and r-63 F4 are one class) (r-63 F4)"

[[rules]]
id = "R4"
text = "the deployment entrypoint refuses to start when any of ISIDIUM_SIGNING_SERVICE_PORT, _FPR or _TIMEOUT is set and ISIDIUM_SIGNING_SERVICE_HOST is not, naming the missing variable, and compose.yaml's comment matches (r-63 F5)"

[[rules]]
id = "R5"
text = "the README lists every act that waits for the phone code once the service is configured: a born-ratified write, a config-policy write, a repair, and every owner-signed write (closing a card with accept --close, releasing a hold, an owner status move, a gated edit to a ratified card), and says they read unverified until card 56 (r-63 F6)"

[[guidance.constraints]]
id = "C1"
text = "the 660 s client channel and the 600 s default wait are unchanged; the margin comes out of the accepted maximum for --signing-service-timeout-s, not out of the channel"
because = "card 54 R5"

[[guidance.constraints]]
id = "C4"
text = "tools/mutations/remote-signer-followups.toml commits a mutation for R1 (init back on the default signer), R2 (the margin check dropped) and R4 (the partial-setting refusal dropped); each is killed by this card's test file alone, and the builder does not run tools/mutate.py (the host's mutation step does)"
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
title = "init signs genesis with the file key on a store holding the service"
rule = "R1"
observable = { test = "tests/store/test_remote_signer_followups.py::test_init_signs_with_the_pinned_file_key" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "a timeout past the margin is refused at serve"
rule = "R2"
observable = { test = "tests/store/test_remote_signer_followups.py::test_serve_refuses_a_timeout_that_leaves_no_margin" }

[[acceptance.scenarios]]
id = "S3"
kind = "test-marker"
title = "no source says one call's bound about the timeout, and the checker names a planted one"
rule = "R3"
observable = { test = "tests/store/test_remote_signer_followups.py::test_no_source_calls_the_timeout_a_one_call_bound" }

[[acceptance.scenarios]]
id = "S4"
kind = "test-marker"
title = "the entrypoint refuses PORT without HOST"
rule = "R4"
observable = { test = "tests/store/test_remote_signer_followups.py::test_the_entrypoint_refuses_a_partial_service_setting" }

[[acceptance.scenarios]]
id = "S5"
kind = "test-marker"
title = "the README names the owner's close among the acts that wait"
rule = "R5"
observable = { test = "tests/store/test_remote_signer_followups.py::test_the_readme_lists_every_act_that_waits" }
```

## Scope

r-63 (card 54, PR #121, merged 2026-10-31): review findings F2-F6 left open by the owner's ruling 'address the f2-f6 as one p1 followup card'. F1 (the unignored deploy/signing-service/ mount) was fixed by hand in PR #122. F2 and F3 are behaviour gaps (found by reading, not by a run); F4 is the third appearance of one class (r-57 F2, r-61 F2), so it is a mechanical check; F5 and F6 are the entrypoint and the README. Depends on card 54 landing; card 56 (enrolment) is separate.

## History

```toml
history = [
  { seq = 1, at = "2026-10-31T19:32:10Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:746e4b211d5aab2b4e97d23d87aab5012ea56e4fc9368bfc94d07f156d25b161", h = "sha256:5e482a641e225348e1a779038778ed0e8e54e25c823e3ff7c713bcd1f81b1ce7" },
]
```
