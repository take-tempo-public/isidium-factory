```toml
schema = 1
id = 52
kind = "story"
status = "ratified"
source = "session"
title = "The signing service signs a request only after the owner's Aegis code for that request, and answers only callers holding a named client certificate"
shape = "bdd"
effort = "default"
refs = ["packages/isidium-store/src/isidium/store/server/signer.py", "packages/isidium-store/src/isidium/store/server/http.py", "packages/isidium-store/src/isidium/store/client/transport.py", "packages/isidium-store/src/isidium/store/core/chain.py", "pyproject.toml", ".github/workflows/ci.yml"]
surfaces = ["packages/isidium-signer/pyproject.toml", "packages/isidium-signer/src/isidium/signer/__init__.py", "packages/isidium-signer/src/isidium/signer/totp.py", "packages/isidium-signer/src/isidium/signer/service.py", "packages/isidium-signer/src/isidium/signer/http.py", "packages/isidium-signer/src/isidium/signer/settings.py", "pyproject.toml", "uv.lock", "tests/signer/__init__.py", "tests/signer/test_service.py", "tests/signer/test_totp.py", "tools/mutations/signer.toml"]
priority = "P0"

[narrative]
feature = "a signature over a card needs a code from the owner's phone, which no session on the workstation can produce"

[[rules]]
id = "R1"
text = "a TOTP check per RFC 6238 (HMAC-SHA1, 30-second step, 6 digits) accepts a code for the current step or one step either side and nothing else; it reproduces RFC 6238 Appendix B's SHA1 rows truncated to 6 digits"

[[rules]]
id = "R2"
text = "submit(tenant, value, at_epoch, display, time_skew_s) from a caller whose client certificate subject is named in the service's settings returns a request id; at_epoch outside the service's clock plus or minus the skew is refused signer.time-skew; a caller over its settings' limit of pending requests is refused signer.rate-limited"

[[rules]]
id = "R3"
text = "approve(request_id, code) with a valid code for a pending, unexpired request signs chain.sig_bytes(tenant, value) with the service's Ed25519 key; the next poll returns the signature in chain.format_sig form; a code's time step, once used, is refused for every later approval (each code consumed once, bound to its request)"

[[rules]]
id = "R4"
text = "a wrong code is refused and counted; at the settings' limit of wrong codes the request is declined; poll of a declined or expired request raises signer.declined; poll of a pending one returns None"

[[rules]]
id = "R5"
text = "the API listener (submit, poll) speaks HTTPS with TLS 1.3 and requires a client certificate, as the store's tls_context does; a connection without a named certificate gets no answer but a refusal"

[[rules]]
id = "R6"
text = "an HTTPS client in the service package implements RemoteTotpContract against this API, so RemoteTotp signs through a running service end to end in the tests"

[[guidance.avoid]]
id = "A1"
option = "a new TOTP or QR dependency"
because = "checked when filing: none is in uv.lock; RFC 6238 is a few lines over the stdlib's hmac, testable against the RFC's own vectors, and the owner enrols on the phone that holds Aegis, so a QR cannot be scanned"

[[guidance.avoid]]
id = "A2"
option = "putting the service inside isidium-store"
because = "the owner, 2026-10-26/27 (remote-totp, chunk plan): it runs only on agent-station, never where the store or a session runs; its own package keeps the store's image free of it"

[[guidance.constraints]]
id = "C1"
text = "the service is a new workspace package, packages/isidium-signer (namespace isidium.signer, PEP 420 for isidium); its src joins the root pyproject's ruff src, mypy_path, pyright extraPaths and pytest pythonpath, and uv.lock; CI's mypy command (ci.yml) is outside the card's reach and the operator adds the new src there by hand"
because = "checked when filing: root pyproject.toml [tool.uv.workspace] members = packages/*; ci.yml:50-59 names each src for mypy, and .github/ is in the deny set"

[[guidance.constraints]]
id = "C2"
text = "every limit (skew, pending per caller, wrong codes, request lifetime) and every path (key, TOTP secret, state) comes from the service's settings file, none defaulted in code"
because = "C-1 (tests/unit/test_no_code_defaults.py)"

[[guidance.constraints]]
id = "C3"
text = "the key and the TOTP secret are read from files only the service's user can read; neither is ever logged, returned or rendered by this card"
because = "the session must not be able to sign"

[[guidance.constraints]]
id = "C4"
text = "the signer depends on isidium-store only for chain (sig_bytes, format_sig) and the contract; nothing in isidium-store imports isidium.signer"
because = "the store's image must not carry the service"

[[guidance.constraints]]
id = "C5"
text = "refusals stay in the signer. namespace"
because = "signer.time-skew, signer.declined and signer.timeout already live there (signer.py)"

[[guidance.constraints]]
id = "C6"
text = "tools/mutations/signer.toml commits a mutation for R1's step window, R3's consumed-once check and R4's wrong-code limit; each kill is checked against this card's own test files only; tools/mutate.py is --show only"
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
title = "the TOTP check reproduces RFC 6238's vectors and its window"
rule = "R1"
observable = { test = "tests/signer/test_totp.py::test_rfc6238_vectors_and_window" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "an unnamed caller, a skewed request and a caller over its limit are refused"
rule = "R2"
observable = { test = "tests/signer/test_service.py::test_submit_refusals" }

[[acceptance.scenarios]]
id = "S3"
kind = "test-marker"
title = "a valid code signs and a reused code is refused"
rule = "R3"
observable = { test = "tests/signer/test_service.py::test_a_code_signs_once" }

[[acceptance.scenarios]]
id = "S4"
kind = "test-marker"
title = "wrong codes decline the request at the limit"
rule = "R4"
observable = { test = "tests/signer/test_service.py::test_wrong_codes_decline" }

[[acceptance.scenarios]]
id = "S5"
kind = "test-marker"
title = "a connection without a named client certificate is refused"
rule = "R5"
observable = { test = "tests/signer/test_service.py::test_mtls_required" }

[[acceptance.scenarios]]
id = "S6"
kind = "test-marker"
title = "RemoteTotp signs through a running service"
rule = "R6"
observable = { test = "tests/signer/test_service.py::test_remote_totp_end_to_end" }
```

## Scope

Ruled [owner, 2026-10-26/27]: 'use aegis keys (or some remote-totp) for signing'; host 'Wait for agent-station'; 'Cards through the factory'; 'mTLS client cert'; 'Service first'. The client half exists (signer.py: RemoteTotp, RemoteTotpContract, DevStubService); the service does not.

## History

```toml
history = [
  { seq = 1, at = "2026-10-27T16:39:06Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:2e543fdf17fbe26191a6bb0e70593dde442e00f4438f683d130839971622c18c", h = "sha256:556775274a7cf766021426d8b667a1e22650d9c32214f9cc04d03742579bb73c" },
  { seq = 2, at = "2026-10-28T05:06:12Z", by = "amodal1@users.noreply.github.com", act = "ratified", fields = ["status"], build = "sha256:2e543fdf17fbe26191a6bb0e70593dde442e00f4438f683d130839971622c18c", h = "sha256:3182a8816f68687b137243a107255a79d87ad5b21280a3ca4ff208ee1149abec", batch = 74 },
]
```
