```toml
schema = 1
id = 61
kind = "story"
status = "draft"
source = "session"
title = "The signing service starts from a read-only key mount, says plainly who can cancel a request, stops cleanly on its first signal and names the file it cannot read"
shape = "bdd"
depends_on = [55]
effort = "default"
refs = ["deploy/signer-entrypoint.sh", "deploy/entrypoint.sh", "packages/isidium-signer/src/isidium/signer/page.py::main", "packages/isidium-signer/src/isidium/signer/service.py::decline", "packages/isidium-signer/src/isidium/signer/service.py::_owner_only"]
surfaces = ["deploy/signer-entrypoint.sh", "deploy/Containerfile.signer", "deploy/README.md", "packages/isidium-signer/src/isidium/signer/page.py", "packages/isidium-signer/src/isidium/signer/service.py", "packages/isidium-signer/src/isidium/signer/settings.py", "tests/signer/test_page_hardening.py", "tools/mutations/signer-hardening.toml"]
priority = "P0"

[narrative]
feature = "the README's deployment recipe for the signing service works as written, and its claims about the page are true"

[[rules]]
id = "R1"
text = "the signing service starts when its signing key is bind-mounted read-only with the host's owner and mode, as under rootless podman: the entrypoint installs the key into a file the service's user owns at mode 0600 (the store entrypoint's `install -m 0600` shape) and the service signs with that copy; the README's recipe says this and no longer has the operator chmod the host file for the container's sake"

[[rules]]
id = "R2"
text = "a peer who reaches the page and enters max_wrong_codes wrong codes declines that request and never signs it; decline's docstring and the README say exactly this, and that the network the page is bound to (WireGuard) is what keeps strangers off it"

[[rules]]
id = "R3"
text = "main installs its SIGTERM and SIGINT handlers before it prints its readiness line, so a signal sent on seeing that line stops the service with exit 0"

[[rules]]
id = "R4"
text = "every start-up refusal names the file it is about: an OSError carries its filename, and a signing key that cannot be parsed (malformed, or encrypted) is refused in the signer. namespace naming the key's path, exit 2 and one line, never a traceback"

[[guidance.avoid]]
id = "A1"
option = "dropping or loosening the per-request wrong-code limit so that the page cannot cancel"
because = "the owner, 2026-10-28 (F3): 'Keep it, fix the docs'; the limit is what stops a code being guessed"

[[guidance.avoid]]
id = "A2"
option = "running the service as root, or with --userns=keep-id, so that it can read the host file"
because = "the store's entrypoint solved the same mount by installing a copy (deploy/entrypoint.sh); the service's user stays unprivileged"

[[guidance.constraints]]
id = "C1"
text = "no scenario of this card passes by skipping: a test that cannot run where it is run fails, saying why"
because = "r-56's review (card 55, PR #118), F4: the accept runner records a skipped test as `pass`, and the factory's close runs the scenarios on the host"

[[guidance.constraints]]
id = "C2"
text = "the service is pointed at the key's copy by the deployment, never by a path defaulted in code; the plan says how"
because = "C-1 (tests/unit/test_no_code_defaults.py)"

[[guidance.constraints]]
id = "C3"
text = "tools/mutations/signer-hardening.toml commits a mutation for R1's install mode, R3's handler order and R4's unparseable-key refusal; each is killed by this card's own test file alone"
because = "the card-writing checklist"

[[guidance.constraints]]
id = "C4"
text = "refusals stay in the signer. namespace"
because = "card 52 C5"

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
title = "a key mounted read-only with the host's mode starts the service from an owner-only copy"
rule = "R1"
observable = { test = "tests/signer/test_page_hardening.py::test_a_read_only_key_mount_starts_the_service" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "wrong codes on the page decline a request and never sign it"
rule = "R2"
observable = { test = "tests/signer/test_page_hardening.py::test_wrong_codes_on_the_page_decline_but_never_sign" }

[[acceptance.scenarios]]
id = "S3"
kind = "test-marker"
title = "the signal handlers are in place before the readiness line"
rule = "R3"
observable = { test = "tests/signer/test_page_hardening.py::test_handlers_are_installed_before_the_ready_line" }

[[acceptance.scenarios]]
id = "S4"
kind = "test-marker"
title = "start-up refusals name the file, and an unparseable key is refused without a traceback"
rule = "R4"
observable = { test = "tests/signer/test_page_hardening.py::test_start_up_refusals_name_the_file" }
```

## Scope

Ruled [owner, 2026-10-28]: 'Push + P0 follow-up card (Recommended)', answering how card 55's remaining findings are handled after fixup proved to repair only a red CI head; and on F3, 'Keep it, fix the docs (Recommended)'. From r-56's review (card 55, PR #118): F2 (major) a 0600 key bind-mounted under rootless podman is unreadable by the image's system user, and any looser mode is refused signer.secret-permissions, so the README's recipe fails at first start (confirmed by reading); F3 (major) the README and decline's docstring say a stranger who reaches the page cannot cancel a request, yet wrong codes spend the request's budget (confirmed); F5 (minor) handlers after the ready line; F6 (minor) `signer.start @ :` names no file, and an unparseable key escapes as a traceback.

## History

```toml
history = [
  { seq = 1, at = "2026-10-28T16:10:27Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "depends_on", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:0ca6937a11e75f35233e413c5c0ec4645bdbf2b8baedee0dcb18f742f367d2b0", h = "sha256:235fbd973edb503818eea8f30f852e1dd85a6027fd47643c10ff1ccf5b29d7a9" },
]
```
