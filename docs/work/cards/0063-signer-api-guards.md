```toml
schema = 1
id = 63
kind = "story"
status = "draft"
source = "session"
title = "The signing service's body cap and secret-file guard are proven, and every refusal either listener answers is counted by its rule"
shape = "bdd"
depends_on = [61]
effort = "default"
refs = ["packages/isidium-signer/src/isidium/signer/http.py::_Handler", "packages/isidium-signer/src/isidium/signer/http.py::Listener", "packages/isidium-signer/src/isidium/signer/service.py::_owner_only", "packages/isidium-signer/src/isidium/signer/service.py::_refuse", "packages/isidium-store/src/isidium/store/server/http.py::classify", "packages/isidium-store/src/isidium/store/server/http.py::_refused"]
surfaces = ["packages/isidium-signer/src/isidium/signer/http.py", "packages/isidium-signer/src/isidium/signer/page.py", "packages/isidium-signer/src/isidium/signer/service.py", "tests/signer/test_api_guards.py", "tools/mutations/signer-api-guards.toml"]
priority = "P1"

[narrative]
feature = "an operator sees every probe the signing service turns away, and its two unproven guards cannot regress silently"

[[rules]]
id = "R1"
text = "a request to the API whose Content-Length exceeds max_body_bytes is answered 400 signer.malformed, and the service receives no request"

[[rules]]
id = "R2"
text = "a signing key or TOTP secret that group or other can read is refused signer.secret-permissions naming the path; the guard is given the file's mode and the platform, so its scenario runs the same way on every host"

[[rules]]
id = "R3"
text = "every refusal either listener answers (a failed handshake by a typed reason, an unknown caller, a path not found, a malformed request) adds 1 to isidium.signer.refusal with its rule id, and no attribute carries a caller, a value, a code or a secret"

[[guidance.avoid]]
id = "A1"
option = "a new counter for the listeners"
because = "isidium.signer.refusal already exists keyed by rule (service.py); a second one would split one question across two names"

[[guidance.constraints]]
id = "C1"
text = "no scenario of this card passes by skipping: a test that cannot run where it is run fails, saying why"
because = "card 61 C1: the accept runner records a skipped test as `pass`, and the factory's close runs the scenarios on the host"

[[guidance.constraints]]
id = "C2"
text = "a failed handshake's reasons are typed the way the store's edge types them (server/http.py classify and _refused), never a free string"
because = "r-55's review (card 52, PR #116), F3: the store's edge counts exactly this, by reason"

[[guidance.constraints]]
id = "C3"
text = "tools/mutations/signer-api-guards.toml commits a mutation for R1's cap, R2's group-or-other check and R3's count in each listener's refusal path; each is killed by this card's own test file alone"
because = "the card-writing checklist; r-55's review (card 52, PR #116), F2: deleting either guard leaves the suite green, confirmed by hand (the cap dropped: 7 passed)"

[[guidance.constraints]]
id = "C4"
text = "refusals stay in the signer. namespace"
because = "card 52 C5"

[[guidance.constraints]]
id = "C9"
text = "every file this card changes passes ruff check, ruff format --check and mypy --strict, by path"
because = "r-38 and r-39 each lost a whole run to a one-line style miss"

[[acceptance.scenarios]]
id = "S1"
kind = "test-marker"
title = "an oversize body is refused before the service sees it"
rule = "R1"
observable = { test = "tests/signer/test_api_guards.py::test_an_oversize_body_is_refused" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "a group- or other-readable secret is refused on every host"
rule = "R2"
observable = { test = "tests/signer/test_api_guards.py::test_a_readable_secret_is_refused" }

[[acceptance.scenarios]]
id = "S3"
kind = "test-marker"
title = "every listener refusal is counted by its rule"
rule = "R3"
observable = { test = "tests/signer/test_api_guards.py::test_every_listener_refusal_is_counted" }
```

## Scope

Ruled [owner, 2026-10-28]: 'yes, card the follow-up and continue', answering the offer to card r-55's review gaps as a small follow-up rather than hold #116. From r-55's review (card 52, PR #116): F2 (minor) the max_body_bytes cap and the POSIX owner-only check have no test and no mutation (the cap confirmed by hand mutation); F3 (minor) the listener's refusals never reach isidium.signer.refusal, so a dashboard would read zero unknown callers while the listener refuses them. Depends on 61, which changes service.py and page.py too.

## History

```toml
history = [
  { seq = 1, at = "2026-10-28T17:58:29Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "depends_on", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:0e90a89fec775c3e82170ab1e2fa19e66243362ec06520065c56fa15ddbb501f", h = "sha256:462fdd37c2793fa9ac8fd75e2c83a3887ec4275d86b5f1021bf8c52417d70218" },
]
```
