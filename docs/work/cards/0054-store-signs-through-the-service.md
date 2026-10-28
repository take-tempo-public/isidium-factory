```toml
schema = 1
id = 54
kind = "story"
status = "draft"
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
text = "tools/mutations/remote-signer.toml commits a mutation for R2's default backend and one for R2's use_backend check; each kill is checked against this card's own test file only"
because = "the card-writing checklist"

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
```

## Scope

Ruled [owner, 2026-10-26/27]: the waiver 'Keep it, no allowance' (the file key a fallback, never dispatched unattended). Today serve builds only SoftwareKeyAck (cli.py:485); RemoteTotp is constructed nowhere.

## History

```toml
history = [
  { seq = 1, at = "2026-10-27T16:39:27Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "depends_on", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:1f21710c8a2e0d2475ab50ed8f4ad4ee124b9f87593b7044c0a6a9160ae6f24e", h = "sha256:5f3abda7ced315d608f8481888dc6de6f7db44b2c9e5107fb51e2bd48663dbd1" },
  { seq = 2, at = "2026-10-28T05:06:12Z", by = "amodal1@users.noreply.github.com", act = "ratified", fields = ["status"], build = "sha256:1f21710c8a2e0d2475ab50ed8f4ad4ee124b9f87593b7044c0a6a9160ae6f24e", h = "sha256:169429f07a600645663bfacff4a62267618d3aaec1d4607c9875debec4b84911", batch = 74 },
  { seq = 3, at = "2026-10-28T15:00:13Z", by = "amodal1@users.noreply.github.com", act = "ratified", fields = ["refs"], build = "sha256:43f23f0359c842a05e00dc9c31cc4be2cb00770d545d93d1f01a3283153ee3f2", h = "sha256:4a7d588cc92e21bb558a99c8e250b49b71eb172145dd7c96661d59308e7fab78", sig = "ed25519:5a6c85e20ab2a6eecc5d6df4f873f9af746b98a33d923c3302a900c365984ae8:X0M1J9jlY6ALer97BwoKzor4Unq8uOrQKQMG0Ehd+408HrfntjTtiTSa71Ot53362UXgCzjDB3I3UQAGY3ixCw==" },
  { seq = 4, at = "2026-10-28T17:20:26Z", by = "amodal1@users.noreply.github.com", act = "demoted", fields = ["status"], build = "sha256:43f23f0359c842a05e00dc9c31cc4be2cb00770d545d93d1f01a3283153ee3f2", h = "sha256:f881061d30ee395a0ad587f69de0f55502820c1ab3354af4796024ef21ceb243" },
]
```
