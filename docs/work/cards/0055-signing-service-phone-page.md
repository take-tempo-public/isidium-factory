```toml
schema = 1
id = 55
kind = "story"
status = "draft"
source = "session"
title = "The signing service shows each request on a phone page and takes the Aegis code there, and ships as its own container image"
shape = "bdd"
depends_on = [52]
effort = "default"
refs = ["packages/isidium-store/src/isidium/store/server/signer.py", "deploy/Containerfile.store", "deploy/entrypoint.sh", "deploy/README.md"]
surfaces = ["packages/isidium-signer/src/isidium/signer/page.py", "packages/isidium-signer/src/isidium/signer/http.py", "packages/isidium-signer/src/isidium/signer/service.py", "packages/isidium-signer/src/isidium/signer/settings.py", "tests/signer/test_page.py", "deploy/Containerfile.signer", "deploy/signer-entrypoint.sh", "deploy/README.md", "tools/mutations/signer-page.toml"]
priority = "P0"

[narrative]
feature = "the owner reads what is being signed on the phone and approves it there; nothing on the workstation is in the loop"

[[rules]]
id = "R1"
text = "a second listener serves the page over HTTPS without requiring a client certificate; GET lists every pending request with its tenant, the value's hash and the display exactly as the service received it, every caller-supplied string HTML-escaped; a GET changes nothing"

[[rules]]
id = "R2"
text = "POST approve and POST decline each take a request id and a code and call the service's approve or decline; a decline also needs a valid code; the answer page says what happened"

[[rules]]
id = "R3"
text = "with no TOTP secret on disk the page offers enrolment: a fresh secret as text and as an otpauth:// link; the secret is written only when a first code from it verifies; once enrolled the page never shows it again, and enrolment is reopened only by removing the file on the host"

[[rules]]
id = "R4"
text = "deploy/Containerfile.signer builds the service as the store's image is built (two stages, base images pinned by digest, a locked hashed install, a non-root user); its entrypoint refuses to start when the settings, key, TLS files or caller list are missing"

[[guidance.avoid]]
id = "A1"
option = "JavaScript on the page"
because = "plain forms are enough and nothing on the page should run code"

[[guidance.avoid]]
id = "A2"
option = "a QR code"
because = "the owner, 2026-10-26/27 (remote-totp, chunk plan): the owner enrols on the phone that holds Aegis, so a QR on that phone's screen cannot be scanned; the otpauth link opens Aegis"

[[guidance.constraints]]
id = "C1"
text = "the page renders the display it RECEIVED, never one recomputed or looked up"
because = "03 §1.12: the service renders 'the diff it received' in its own UI"

[[guidance.constraints]]
id = "C2"
text = "the Containerfile follows Containerfile.store's shape (uv export --locked --no-dev --package isidium-signer, pip --require-hashes)"
because = "checked when filing: deploy/Containerfile.store"

[[guidance.constraints]]
id = "C4"
text = "deploy/README.md gains the signing service's section: certificates (server, page, one client certificate per caller), the settings file, enrolment on the phone, and that it runs only in the owner-only zone"
because = "the owner deploys it on agent-station from this section"

[[guidance.constraints]]
id = "C3"
text = "tools/mutations/signer-page.toml commits a mutation for R1's escaping and one for R3's write-only-after-a-verified-code; each kill is checked against this card's own test file only"
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
title = "the page lists pending requests escaped and a GET changes nothing"
rule = "R1"
observable = { test = "tests/signer/test_page.py::test_the_page_lists_escaped" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "approve and decline each need a valid code"
rule = "R2"
observable = { test = "tests/signer/test_page.py::test_approve_and_decline_need_a_code" }

[[acceptance.scenarios]]
id = "S3"
kind = "test-marker"
title = "enrolment writes the secret only after a verified code and never shows it again"
rule = "R3"
observable = { test = "tests/signer/test_page.py::test_enrolment_once" }

[[acceptance.scenarios]]
id = "S4"
kind = "test-marker"
title = "the entrypoint refuses to start without its files"
rule = "R4"
observable = { test = "tests/signer/test_page.py::test_entrypoint_refuses_missing_files" }
```

## Scope

Ruled [owner, 2026-10-26/27]: approval on a 'Phone web page' (over WireGuard; nothing on the laptop in the loop). 03 §1.12: 'the service renders card · act · hash · the diff it received in its own UI and takes the code there'.

## History

```toml
history = [
  { seq = 1, at = "2026-10-27T16:39:46Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "depends_on", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:ab247e52d210635a622a675f9cead24e8b7d8727a69ede447beee3d95776ec11", h = "sha256:4eadb883a32d4da843dddc5a3c06ef260246254a1798d73580e7fe1653b67f2a" },
]
```
