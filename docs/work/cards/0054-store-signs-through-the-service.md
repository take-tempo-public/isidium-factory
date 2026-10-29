```toml
schema = 1
id = 54
kind = "story"
status = "ratified"
source = "session"
title = "The store signs a ratification through the remote-totp service, and the file key stays as a named fallback"
shape = "bdd"
depends_on = [52]
effort = "default"
refs = ["packages/isidium-store/src/isidium/store/client/cli.py::ratify", "packages/isidium-store/src/isidium/store/client/cli.py::serve", "packages/isidium-store/src/isidium/store/server/store.py::_sign", "packages/isidium-store/src/isidium/store/server/store.py::_software_fprs", "packages/isidium-store/src/isidium/store/server/signer.py", "packages/isidium-store/src/isidium/store/registry/config.py::BUILT_BACKENDS", "packages/isidium-store/src/isidium/store/registry/config.py::SIGNER_BACKEND_KEYS", "packages/isidium-store/src/isidium/store/registry/config.py::use_backend", "packages/isidium-store/src/isidium/store/server/http.py::Worker", "packages/isidium-store/src/isidium/store/client/transport.py", "packages/isidium-signer/src/isidium/signer/http.py::HttpsService"]
surfaces = ["packages/isidium-store/src/isidium/store/client/cli.py", "packages/isidium-store/src/isidium/store/server/store.py", "packages/isidium-store/src/isidium/store/server/signer.py", "packages/isidium-store/src/isidium/store/server/api.py", "deploy/compose.yaml", "deploy/entrypoint.sh", "deploy/README.md", "tests/store/test_remote_signer.py", "tools/mutations/remote-signer.toml"]
priority = "P0"

[narrative]
feature = "a ratify waits for the owner's code on the phone, and a card it signs is not software-grade"

[[rules]]
id = "R1"
text = "serve takes the signing service's address, its CA and the store's client certificate and key; with them it builds RemoteTotp over the service package's HTTPS client, with poll_interval_ms read from the effective config"

[[rules]]
id = "R2"
text = "a store given both a remote-totp signer and the file key signs with remote-totp by default; ratify --sign --backend software_key_ack signs with the file key; each is checked by cfg.use_backend against the effective signer.backends, so an undeclared backend is refused signer.backend-unavailable"

[[rules]]
id = "R3"
text = "a card signed through remote-totp is not software-grade and a card signed by the file key is, read from the dispatch view, with signer.backends = [remote-totp, software_key_ack]"

[[rules]]
id = "R4"
text = "a service that declines or times out leaves nothing signed and nothing journaled, and ratify's answer names the refusal"

[[rules]]
id = "R5"
text = "RemoteTotp's wait for the owner is bounded by the clock (monotonic time since the submit, every round trip included), not by a sum of its sleeps; the store answers signer.timeout before the client channel's own timeout can fire, however slowly the service answers each poll within its per-call timeout"

[[rules]]
id = "R6"
text = "before a remote signature is used, the store verifies it over tenant and value and checks that its key is the configured service key (--signing-service-fpr); a signature that fails either is refused in the signer. namespace, and nothing is signed or journaled"

[[guidance.avoid]]
id = "A1"
option = "replacing ratification.pin with the service's key"
because = "checked when filing: _owner_signed checks against the CURRENT pin (store.py:1887), so a swap unverifies every past signature; the owner, 2026-10-26/27 (remote-totp, chunk plan): the file key stays pinned"

[[guidance.constraints]]
id = "C1"
text = "isidium-store imports the service's HTTPS client lazily, only when serve is given a signing service, and does not depend on isidium-signer at install; or the client lives in isidium-store beside RemoteTotp; the plan says which and why"
because = "the store's image must not carry the service"

[[guidance.constraints]]
id = "C2"
text = "the store keeps signing on its one worker thread while the owner enters the code; the client's timeout stays above the signer's"
because = "checked when filing: http.py's Worker docstring and transport.py:48 already provide for a ten-minute signer round trip"

[[guidance.constraints]]
id = "C3"
text = "_software_fprs is unchanged unless a test proves it must change: with two backends it grades only the pin, which is the file key"
because = "checked when filing: store.py:1301-1319"

[[guidance.constraints]]
id = "C4"
text = "tools/mutations/remote-signer.toml commits a mutation for R2's default backend, R2's use_backend check, R5's clock bound and R6's signature check; each kill is checked against this card's own test file only"
because = "the card-writing checklist"

[[guidance.constraints]]
id = "C5"
text = "this card's test file passes on Linux and on a Windows host alike: no test depends on the platform's TCP refusal timing (a connection to a bound, non-listening port is refused at once on Linux and after about 2 s on Windows, measured 2.06 s), so a test of an unreachable service gives its client a timeout above that or reaches unreachable another way"
because = "r-57 ended failed:gate on exactly this: the host's mutation check ran the file red (signer.timeout read where signer.unreachable was meant, with a 1.0 s client timeout), and the build container, Linux and without pytest, could not see it"

[[guidance.constraints]]
id = "C6"
text = "the README gives the true reason for its backend order (a write declaring remote-totp is signed through a service key no binding holds until card 56, so it reads unverified), server/signer.py's docstring says the HTTPS transport now lives there and why, and any module-level import there carries its C-13 reason"
because = "r-57's review F6, F3, F5"

[[guidance.constraints]]
id = "C8"
text = "no address, host name, certificate or secret of any real deployment appears in the repository; examples use example.invalid and test-minted certificates"
because = "the repository is public"

[[guidance.constraints]]
id = "C9"
text = "every file this card changes passes ruff check, ruff format --check and mypy --strict, by path"
because = "r-38 and r-39 each lost a whole run to a one-line style miss"

[[acceptance.scenarios]]
id = "S1"
kind = "test-marker"
title = "serve builds the remote signer from its options"
rule = "R1"
observable = { test = "tests/store/test_remote_signer.py::test_serve_builds_the_remote_signer" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "remote-totp by default, the file key by name, an undeclared backend refused"
rule = "R2"
observable = { test = "tests/store/test_remote_signer.py::test_backend_choice" }

[[acceptance.scenarios]]
id = "S3"
kind = "test-marker"
title = "a remote-totp signature is not software-grade and a file-key one is"
rule = "R3"
observable = { test = "tests/store/test_remote_signer.py::test_software_grade_by_backend" }

[[acceptance.scenarios]]
id = "S4"
kind = "test-marker"
title = "a declined or timed-out signature leaves nothing signed"
rule = "R4"
observable = { test = "tests/store/test_remote_signer.py::test_a_declined_signature_leaves_nothing" }

[[acceptance.scenarios]]
id = "S5"
kind = "test-marker"
title = "the wait is bounded by the clock, not by the sleeps"
rule = "R5"
observable = { test = "tests/store/test_remote_signer.py::test_the_wait_is_bounded_by_the_clock" }

[[acceptance.scenarios]]
id = "S6"
kind = "test-marker"
title = "a signature that does not verify, or is by another key, is refused"
rule = "R6"
observable = { test = "tests/store/test_remote_signer.py::test_a_wrong_signature_is_refused" }
```

## Scope

Ruled [owner, 2026-10-26/27]: the waiver 'Keep it, no allowance' (the file key a fallback, never dispatched unattended). Today serve builds only SoftwareKeyAck (cli.py:485); RemoteTotp is constructed nowhere.

Amended [owner, 2026-10-28]: 'amend AND RE-DISPATCH', after r-57 ended failed:gate. Its own test file was red on the host only: Windows refuses a connection to a bound, non-listening port after about 2 s, and the test's 1.0 s client timeout read that as signer.timeout (C5). The review's F2 (major: the wait bound sums sleeps, so a slow service outlasts the 660 s channel) becomes R5, and F4 (the returned signature is never verified against the configured key) becomes R6. Re-dispatched carrying r-57's work.

## History

```toml
history = [
  { seq = 1, at = "2026-10-27T16:39:27Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "depends_on", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:1f21710c8a2e0d2475ab50ed8f4ad4ee124b9f87593b7044c0a6a9160ae6f24e", h = "sha256:5f3abda7ced315d608f8481888dc6de6f7db44b2c9e5107fb51e2bd48663dbd1" },
  { seq = 2, at = "2026-10-28T05:06:12Z", by = "amodal1@users.noreply.github.com", act = "ratified", fields = ["status"], build = "sha256:1f21710c8a2e0d2475ab50ed8f4ad4ee124b9f87593b7044c0a6a9160ae6f24e", h = "sha256:169429f07a600645663bfacff4a62267618d3aaec1d4607c9875debec4b84911", batch = 74 },
  { seq = 3, at = "2026-10-28T15:00:13Z", by = "amodal1@users.noreply.github.com", act = "ratified", fields = ["refs"], build = "sha256:43f23f0359c842a05e00dc9c31cc4be2cb00770d545d93d1f01a3283153ee3f2", h = "sha256:4a7d588cc92e21bb558a99c8e250b49b71eb172145dd7c96661d59308e7fab78", sig = "ed25519:5a6c85e20ab2a6eecc5d6df4f873f9af746b98a33d923c3302a900c365984ae8:X0M1J9jlY6ALer97BwoKzor4Unq8uOrQKQMG0Ehd+408HrfntjTtiTSa71Ot53362UXgCzjDB3I3UQAGY3ixCw==" },
  { seq = 4, at = "2026-10-28T17:20:26Z", by = "amodal1@users.noreply.github.com", act = "demoted", fields = ["status"], build = "sha256:43f23f0359c842a05e00dc9c31cc4be2cb00770d545d93d1f01a3283153ee3f2", h = "sha256:f881061d30ee395a0ad587f69de0f55502820c1ab3354af4796024ef21ceb243" },
  { seq = 5, at = "2026-10-28T17:20:45Z", by = "amodal1@users.noreply.github.com", act = "ratified", fields = ["status"], build = "sha256:43f23f0359c842a05e00dc9c31cc4be2cb00770d545d93d1f01a3283153ee3f2", h = "sha256:e63e2e28fabdd17f32d6fbbac3e53004af1c49967fd2f009d7004486d3f4b740", batch = 76 },
  { seq = 6, at = "2026-10-28T21:21:16Z", by = "amodal1@users.noreply.github.com", act = "demoted", fields = ["status"], build = "sha256:43f23f0359c842a05e00dc9c31cc4be2cb00770d545d93d1f01a3283153ee3f2", h = "sha256:7ee45464966d6f6279848aaa2ace2521969e739c2ac1b462c288e9d2d7913e66" },
  { seq = 7, at = "2026-10-28T21:23:21Z", by = "amodal1@users.noreply.github.com", act = "amended", fields = ["acceptance", "guidance", "rules", "scope"], build = "sha256:8828c0b0c313a32dff48c20ca9634284ab0a52328844d08f66d414febca910eb", h = "sha256:694768fff72079ed6b3fb2242cb5c1ba35dd3d6cdd733bc6d8f3a060598747bf" },
  { seq = 8, at = "2026-10-28T21:24:28Z", by = "amodal1@users.noreply.github.com", act = "ratified", fields = ["status"], build = "sha256:8828c0b0c313a32dff48c20ca9634284ab0a52328844d08f66d414febca910eb", h = "sha256:aa94bc82d776d001875cf3808d46dd14660704b0f85d2229b498d2b1b1f8830d", batch = 77 },
  { seq = 9, at = "2026-10-29T21:14:01Z", by = "amodal1@users.noreply.github.com", act = "demoted", fields = ["status"], build = "sha256:8828c0b0c313a32dff48c20ca9634284ab0a52328844d08f66d414febca910eb", h = "sha256:3e42c9a5a073ab4f3be3e292ebd184a031fad914520a28b192aa25991cbe68c0" },
  { seq = 10, at = "2026-10-29T21:14:18Z", by = "amodal1@users.noreply.github.com", act = "ratified", fields = ["status"], build = "sha256:8828c0b0c313a32dff48c20ca9634284ab0a52328844d08f66d414febca910eb", h = "sha256:7bb3530c3d88b6c5bdb35b608f5f90dc3bd9f80dd175e89aff586b0ecc711226", batch = 81 },
]
```
