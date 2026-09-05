<!-- provenance: schema=1 project=isidium-factory session=ff73f7ed-85be-43d0-8bc7-55aad4b6f440 actor=amodal1 agent=anthropic/claude-fable-5 generated_at=2026-08-27 status=draft-0 -->

> **Assumes:** the design docs; the build plan (`2026-08-27-v1-build-plan.md`); WP1–WP3 built and reviewed (sync 7bf.5–7bf.9).
> **Descends from:** the owner's direction 2026-08-27, verbatim: *"everything we bump into that isn't fixed, needs to be resolved or recorded as a step for set up"* — and the thirteen questions of that turn.
> **Expected reader:** the owner (the rulings in section 5), then whoever stands the store up, then the sartor bridge session.
> **Status:** **draft-0** — sections 1–4 are the record of what setup requires and what is unverified; section 5 is what awaits an owner ruling. Nothing here is a design change; where a mechanic is new it is marked **[proposed]**.

# Deployment, setup, and the open items — before a living tenant

## 1. The two identity layers (they were being conflated; they are not the same)

| | **A — who may sign** | **B — who may call** |
|---|---|---|
| The question | who may ratify, release, accept, change policy | who may reach the store at all, and with which grant |
| The credential | a ratifier key (software key today; Aegis/TOTP or TPM later) | a client certificate on the mTLS channel |
| Where it is decided | the **policy chain** in `config.toml`: a `binding` record — key → grant → tenant → from → *until* | the **tenant registration** (factory-side, out of the repo): certificate subject → principal + grant |
| Revocation | **designed and built.** A later `binding` entry carrying `until` closes the binding; every entry signed after that instant fails verification, and past acts stay valid because each is judged against the binding that held *then*. Tested (a revoked key's next ratification reads `unverified`). | **not built.** The mapping is a dictionary handed to the service at start-up. Revoking means editing it and restarting. No certificate-revocation check. |
| The target | unchanged: the realm holds the binding history, the policy chain carries the record | isidium G7 / the realm becomes the source; the store asks it, or realm bindings land in the policy chain the way ratifier bindings already do |

**The lift when agent-station's realm exists: one function.** `Registration.caller(certificate) -> Caller` is the whole seam — everything above it (grants, the predicate, the journal, the signature) is unchanged. That is config plus one adapter, not a redesign.

**What must be right *now* so the move costs nothing** (none of these are design changes; all are small) — **all four built as K6, 2026-09-05** (`server/service.py`, `server/journal.py`; the row shape is `journal@2`, adopted through `config@2`'s `[journal]` table by one signed `config-policy` act, 04 §2.3):

1. **Record the credential in the journal row, not just the principal.** Today a row says `amodal1@example`. After a certificate is rotated or revoked, nothing proves *which* credential asserted that name. The certificate fingerprint costs one field now and cannot be backfilled later.
2. **The store checks the certificate's own validity window.** TLS checks it during the handshake, but the store must not assume it saw a handshake (the trusted-hop shape hands it a certificate after the fact).
3. **Match the full subject, never the bare common name.** A bare-name match accepts anything the CA will issue with that name in any position.
4. **The mapping is a file the store re-reads,** so revoking is an edit, not a rebuild. *(Built: one `stat` per connection, a re-parse only when the stamp moved; a file that stops parsing names **nobody** — the store fails closed, because the row just mistyped may be the revocation — and the words go to the record.)*

## 2. What "web server" means here, and what setup requires

> **Superseded in part by 7bg.8 (owner-ratified 2026-08-27).** The store no longer runs under an ASGI server: it terminates its own mTLS and parses with **h11**, and the loop is ours. uvicorn, hypercorn and the trusted hop are all out. What stands below is the *setup* it describes — the CA, the certificates, the registration — which is unchanged. S-5 and S-6 are rewritten in place; section 3's two shapes are closed.

**Terms.** The store is a service: the tenant container, the factory, the planner and the owner's workstation call it. Serving that API needs an HTTP server; in Python that is a library running inside the store's own process. **uvicorn** and **hypercorn** are the two common ones. This is unrelated to any website, and unrelated to the certificate discussed elsewhere for agents to verify against — this certificate *is* the caller's identity to the store.

**What mTLS is doing.** Both ends present certificates. The store proves it is the store; **the client's certificate is the caller's identity**, and the registration maps it to a principal and a grant. There is no other authentication: no password, no token, no header.

### Setup steps — the network shape

| # | Step | Notes |
|---|---|---|
| S-1 | A certificate authority for the tenant (agent-station's, or a small one per tenant). | The registration pins it. **It must carry `SubjectKeyIdentifier` and a `KeyUsage` naming `keyCertSign`** — without either, every caller refuses *the store's* chain and never reaches it (measured 2026-08-29; see the note below). |
| S-2 | A server certificate for the store, issued by S-1. | The client pins the CA (leaf pinning is a later option). **It must carry `AuthorityKeyIdentifier`; a name matching the address callers dial — a `SubjectAltName`, or the Common Name when there is no SAN, because OpenSSL falls back to it; and, if it carries an Extended Key Usage at all, that EKU must include `serverAuth`.** `KeyUsage` is not required on it. All measured one variable at a time, 2026-08-29. |
| S-3 | One client certificate per caller identity — the owner, the planner, the factory's lander. | The subject is the identity; keep them distinct and long-lived enough to be revocable rather than expiring silently. **The store checks nothing else about a caller certificate** — measured 2026-08-29: one with no `AuthorityKeyIdentifier`, no `KeyUsage` and no `clientAuth` EKU authenticates, because the store's listener does not set `VERIFY_X509_STRICT`. **Ruled 2026-08-29: a caller certificate must carry the `clientAuth` Extended Key Usage, and the store will require it** (built with the other caller-identity properties). Issue caller certificates with `clientAuth` and nothing else. **Built by K6 (2026-09-05): the store refuses `auth.no-client-auth` for a caller certificate with no Extended Key Usage or one that lacks `clientAuth`, `auth.expired` / `auth.not-yet-valid` for one outside its window by the store's own clock, and matches the whole subject** — so the tenant CA is no longer the whole boundary, though it stays single-purpose by policy: a CA shared with a web server still issues leaves that *look* like credentials to whoever reads the registration. |
| S-4 | The registration file: subject → (principal, grant). | Factory-side, never in a tenant repo. **The key is the certificate's whole subject in RFC 4514 form** [K6] — `CN=owner@example`, or `CN=owner@example,O=Take Tempo` — as `openssl x509 -in <cert> -noout -subject -nameopt RFC2253` prints it after `subject=`; a bare name matches nothing. **Edits are live**: the store re-reads the file on the next connection after it changes, and a file that will not parse registers nobody until it does. **A probe is not a principal [ruled 2026-08-29].** The container's healthcheck and any monitoring agent need a certificate this CA issued — the handshake requires one — but they are **not** registered, have no grant, and may reach only `/health`. Do not add them here to make them work; they already work. They are bounded by their own small per-peer allowance at the edge, separately from registered callers. |
| S-5 | ~~Choose the termination shape~~ — **closed by 7bg.8**: the store terminates mTLS itself. Configure its listen address, the CA to verify against, and its own certificate and key. **Refined 2026-08-29 (Q1): the store starts TLS *per connection*, inside its own handler**, so a refused handshake is a value it catches with a reason rather than an event the runtime swallows — the connection ceiling then bounds handshake work as well as requests. Nothing about what is verified changes. | No proxy, no hop, no shape choice. |
| S-6 | ~~Verify that the chosen server hands the certificate to the application~~ — **closed by 7bg.8**: neither uvicorn nor hypercorn 0.18 does (both verified by reading their source), and the store no longer asks one to. The store reads the peer certificate off its own connection. | The replacement test is a boundary test, not a library claim: a client with no certificate, one from another CA, and an expired one are each refused **at the handshake**, before a byte reaches the parser. |

> **Which end is strict, and why it is a flag and not a version [corrected 2026-08-29].** The record used to say
> *"OpenSSL 3.5 enforces RFC 5280 strictly … or the store refuses every caller."* That is wrong in three ways and it
> pointed an operator at the wrong end of the connection. Measured, on this workstation, with `ssl` linked against
> **OpenSSL 3.0.21** — so the version is not the mechanism:
>
> - The strictness is the **`VERIFY_X509_STRICT` flag**, and the **client** sets it. `ssl.create_default_context()`
>   turns it on, and that is what `httpx` builds inside `HttpsTransport` (`verify_flags` = 557088, STRICT on,
>   `check_hostname` on). Clearing that one flag, with the same certificates, makes every rejected case connect.
> - The **store's listener does not set it** (`verify_flags` = 32768, `VERIFY_X509_TRUSTED_FIRST` only). The store
>   therefore enforces none of these extensions on the certificates it authenticates.
> - So the extensions are required on **S-1 and S-2, for the caller's benefit** — never on S-3.
>
> The symptom of getting any of this wrong is the same on both sides and says nothing: under TLS 1.3 the client sees a
> connection that opens and then gives nothing, and the store's handler is never invoked. That is why it is written
> where the certificates are made rather than left to be discovered.

### uvicorn vs hypercorn — the difference that matters

Both run the same application. **uvicorn** terminates TLS and verifies the client certificate, then tells the application nothing about it — which is exactly what broke: the store saw no caller and refused every call. **hypercorn** was the alternative, and was *reported* to pass the certificate through the standard ASGI extension. **Both are now verified to do neither, by reading their source (2026-08-27 and 2026-08-29):** hypercorn 0.18's scope `extensions` only ever carries `http.response.trailers` / `push` / `early_hint`, and uvicorn 0.52.4 contains no `"tls"` extension key, no `getpeercert` and no `ssl_object` anywhere in the package — it calls `is_ssl(transport)` solely to set the scheme. No ASGI server can hand an application the caller's certificate, which is why the store terminates its own TLS. The `[server]` extra is `h11` and names no ASGI server at all.

## 3. The termination shape — and whether it expands the store

> **Closed by 7bg.8 (owner-ratified 2026-08-27): neither shape.** Shape 1 depended on a library behaviour that does not exist; shape 2 is the hard-shell/gooey-centre the owner named — the identity arrives as one process's say-so. The store terminates mTLS itself and reads the certificate off the connection it is authorizing. `TrustedHop`, the forwarded header, the Caddyfile and the Unix-socket hop all go. The section is kept for the reasoning that produced the ruling.

**Shape 1 — direct.** The server terminates mTLS and hands the certificate to the store. No new concepts; depends entirely on S-6.

**Shape 2 — the trusted hop [proposed].** A small proxy inside the store's *own* container terminates mTLS, verifies the client certificate against the registration's CA, and hands the verified certificate to the store over a local connection.

**Does this expand what the store does?** No. The store is designed as a service reached over a pinned channel; where TLS terminates is deployment, not store scope. Three honest qualifications:

- The store currently holds a small piece of *deployment policy* (which local peer may be believed). **[proposed]** that moves to the store's own config file, so the shape is a configured choice — exactly as the client side already chooses local or channel.
- **The security of shape 2 is the security of the hop.** Over loopback TCP, any process on that host can impersonate the proxy. Over a **Unix socket with file permissions**, inside a container running only the store and its proxy, it is a real boundary. **[proposed]** the Unix socket is the default and loopback TCP is refused unless named explicitly.
- Shape 2 is the shape that does not depend on an unverified library behaviour, so **[proposed]** it is the primary and shape 1 is proven later.

## 4. What governs the store itself

The store's commits skip the tenant's pre-commit hook. That is not the store exempting itself:

- **The rule** is *governed files change only through the store*. The hook is a client-side belt that catches everyone who is **not** the store; running it against the store's own commit would refuse the only legitimate writer.
- **What governs the store is stricter than the hook:** every change to a governed file in every commit must be explained by an unbroken chain of journal rows written *before* the change. A commit that changes a governed file with no row is `unjournaled`, hard, and clears only by the owner's signed repair. The hook asks "is this a governed path?"; the reconciliation asks "does the journal explain this exact byte transition?".
- **It is visible** in `git log`: the store's commits carry a distinct committer (`store@<tenant>`) beside the human author.
- **Gap:** that reconciliation is not yet wired into a tenant's CI. It is a pure function and it exists; running it on every push is a setup step (S-7), not new code.

**Portability.** Git hooks are not harness-specific — a hook fires whatever made the commit, Claude Code or pi or a human. What *is* harness-specific is the in-session tool guard (Claude Code's `PreToolUse`, a pi extension), which is adapter work behind the execution seam and is not built. The order the design already ranks: the in-session guard prevents, the hook prevents, **the journal and the reconciliation guarantee**. The guarantee is built; one of the two preventions is built.

| # | Step | Notes |
|---|---|---|
| S-7 | ~~Wire the per-commit reconciliation into the tenant's CI~~ — **split by 7bg.6, and the forge half built by K8 (2026-09-03).** The reconciliation needs the journal, which a forge's runner cannot reach, so it stays the factory's (ingest, `check`). What a runner *can* enforce on a plain checkout is the governed-path rule and chain integrity — `tools/verify_chain.py`, a required check on every pull request (S-13). | Journal reconciliation: factory side, unchanged. Forge side: built, and gated (S-12). |
| S-9 | **The forge must allow partial clone** (`uploadpack.allowFilter`) so the store can fetch the graph and trees without blob content. | GitHub allows it. A self-hosted Forgejo/Gitea must have it enabled. **Degradation, stated:** where a forge refuses the filter the store falls back to a **full bare** clone — the footprint grows to the history's blobs, but there is still no working tree and no index, so the working-tree class of defect stays impossible. The store must report which of the two it is running. **Three traps, measured 2026-08-29 — read them before writing that report:** (1) a refused filter is **indistinguishable from an accepted one in the clone's config** — both write `promisor=true` and `partialclonefilter=blob:none`; the only signals are a `warning: filtering not recognized by server, ignoring` on stderr at clone time and the actual absence of blob objects, so the report must count objects, not read config. (2) `--filter` is **ignored outright for local *path* clones** (`warning: --filter is ignored in local clones; use file:// instead.`) — any test or setup step that clones from a path silently gets a full clone. (3) A partial clone is **lazy, not restricted**: see Q3 in the chunk plan's open rulings. |
| S-8 | Decide where the store's clone lives even in local mode (section 5, ruling 2). | The index-sweep defect was only possible because the store commits in a shared working tree. |
| S-10 | **A deploy key for the store** — one per tenant repository, write access, registered at the forge (K8). | **Ruled 2026-09-02: a deploy key, not a machine account.** It is a **repository-wide write credential** — no forge scopes a key to a path — so what holds the store to `docs/work/` is the store's own code, and the forge's gate (S-12) holds *everyone else* out. Two parties, two mechanisms; neither substitutes for the other. The private half is operator material (`deploy/ssh/`, gitignored, mounted read-only); the public half is not secret but is this deployment's. Generated on the workstation; the image never holds it in a layer. |
| S-11 | **The origin over SSH, with the forge's host keys pinned** (K8). | `ISIDIUM_ORIGIN` in `git@host:owner/repo.git` form. The image carries `openssh-client` and a `known_hosts` fetched from the forge's **authenticated** API with the fingerprints recorded beside each line (`deploy/known_hosts`); git is pointed at that file and nothing else with `StrictHostKeyChecking=yes`, so an unmatched host is refused — never prompted for, never learned. The entrypoint installs the mounted key at 0600 into the store's own home, only when the origin is SSH, so the same image and compose file serve a `file://` origin unchanged. **Measured 2026-09-03, tenant #0:** the container's first start cloned `git@github.com:take-tempo-public/isidium-factory.git` through the pinned host key (`footprint=filtered`), and `init` pushed the policy chain's first commit to `main` with the deploy key (`0847c85`, committer `isidium-store <store@isidium-factory>`); the identity sweep passed on it. `openssh-client` cost **5.55 MB on a 301.6 MB image** (1.9%). The egress allowlist is still untested. |
| S-12 | **`main` gated for everyone but the store** (Q13, ruled 2026-09-03). | A pull request required; the required checks of S-13; no force-push; no deletion; **the store's deploy key the one bypass** — the only direct writer of `main`, and only of governed paths, by its own code. On GitHub: one ruleset, `bypass_actors: [{actor_type: DeployKey, bypass_mode: always}]`, with `pull_request`, `required_status_checks`, `non_fast_forward` and `deletion` — every one **probed on the real repository 2026-09-02/03** (created disabled, read back, deleted) before this row was written. **Goes on last**: after the checks are green on `main` and `init` has landed `config.toml`, because a required check that cannot pass is a `main` nobody can merge to. **On since 2026-09-03 — ruleset `22217228`, and demonstrated** (`deploy/README.md`, *The gate on `main`, demonstrated*): a human's direct push refused, a force-push refused, a pull request editing `docs/work/config.toml` failed `verify` and could not be merged; `main` unchanged after each. `required_status_checks` is deliberately **not strict**: the store's own pushes to `main` would otherwise stale every open pull request and force a rebase before each merge, for commits no pull request may touch. **The store's push after the gate is measured** (`24652f2`, the first card, through the bypass) — and it exposed the converse: **every merged pull request leaves the store's clone stale, and its next write is refused until a restart replays it** (the chunk plan's **Q14**, ruled 2026-09-03: fetch-and-fast-forward before every write, plus a bounded rebuild on a rejected push when no governed path moved — built by K9). **K9 landed 2026-09-03 and the operational rule is retired**: the store fetches `main` and fast-forwards its own ref before every governed write, so a merged pull request no longer leaves it stale. Demonstrated on this repository with no restart between the merge and the write — `deploy/README.md`, *K9: a write onto a `main` the store had never seen*. A moved remote whose diff reaches the governed root is still refused, which is K4's rule and is not refined. |
| S-13 | **The required checks** (K8). | `identity-sweep` (standing). **`chain-verify`** — `tools/verify_chain.py`: on a pull request, `--diff-base` refuses any governed change (the pre-commit hook's own predicate, `client/hook.offending`); on a push to `main`, every chained document is re-verified, the store's own writes included — the one writer the pull-request gate does not see. **`ci`** — the green bar: the suite, `mypy --strict` over `packages/`, `ruff check`, `ruff format --check`; unpinned, and the file says K5 pins it. Each is checkout → install → one command, so it runs on another forge's runner unchanged. What `chain-verify` cannot see is written at the top of the script: signatures, and the journal. |
| S-14 | **The override — no standing bypass for the owner** (Q13). | Break-glass at the forge: the owner is admin — *disable the ruleset, fix, re-enable*, one audited call, deliberate and visible. Break-glass in the store: `isidium repair`, owner-signed. Revoking the store: delete its deploy key at the forge — it stops the store and stops nothing else, because everything else already lands through a pull request. **The one tension to know:** blocking force-push means the remedy for private material landing on `main` *starts* with the break-glass. **Measured 2026-09-03 by the owner:** `gh pr merge --admin` on a pull request failing `verify` → *"Repository rule violations found. Required status check "verify" is failing."* — a repository admin does not bypass the ruleset; only the listed deploy key does. |

## 5. Open items — for the owner

**Rulings needed before a living tenant:**

1. **B4 — where sartor's store runs:** agent-station as designed (the base-container work has not started: LXD is up, Ansible has never run, there are no containers), or an explicitly interim WSL2 container on the workstation.
2. ~~**Local mode's shape**~~ — **closed by 7bg.2** (owner: *"yes on getting rid of loopback and local mode"*): local mode and loopback are deleted. One shape, one boundary; `init` runs over the channel; tests construct `Store` directly.
3. ~~**The trusted hop**~~ — **closed by 7bg.8**: rejected. The store terminates its own mTLS; there is no hop to configure.
4. **The expedite `because` field's name** in the card schema (ratified as required; unnamed, therefore unenforced).
5. **The per-card deny-set override's field name** (the design says one exists; unnamed, so the refusal is currently absolute).

**Work that is decided-but-unbuilt, proposed for a hardening pass before WP4:**

| | What | Why now |
|---|---|---|
| ~~H-1~~ | ~~Caller identity: fingerprint in the journal row; validity window checked; full-subject match; mapping from a re-readable file~~ — **built as K6, 2026-09-05** (the chunk plan's K6 entry; `journal@2`, `config@2`, `tools/mutations/k6.toml`) | the fingerprint cannot be backfilled — and three real rows on tenant #0 predate it, so the bump was built additive: those rows stay `journal@1`, the chain keeps its genesis |
| H-2 | A `shapes@1` registry document generated and checked in | removes the only place a Rust port must hand-transcribe; ~an hour |
| H-3 | The projected label becomes a typed value with a renderer | it is a formatted string matched by prefix today — my shortcut, not a language limit |
| H-4 | Delete the validator's code-side defaults; a test asserting no default literal duplicates a schema document's | makes "defaults live in the adopted schema version" mechanically true, so a deterministic reader of the schemas sees them all |
| H-5 | The inbox record validated against its schema at write | a build gap, not a design gap |
| H-6 | A policy change may ride the sitting's batch | designed; unbuilt; today it costs a second signature in that sitting |
| H-7 | Local mode's parsed-document cache in the journal database | a stated cost, not a defect; do it when card counts grow |

## 6. The forge: what each posture can enforce [K8, 2026-09-03]

> **Requirement [owner, 2026-09-03]:** the tool supports public and private repositories on GitHub or GitLab, a
> self-hosted forge (Gitea/Forgejo), and *local first, pushed to a public forge* — each a viable shape. They need not
> behave identically, but each is to be understood and documented. **Which posture any particular deployment runs is
> that deployment's business and is not recorded here.**

**The shape is the same everywhere** (S-10 … S-14): `main` gated for everyone but the store, the governed-path rule
and the code gate as required checks, the store's deploy key the one direct writer. What differs per forge is which
of those the forge enforces *natively*, and therefore the **ceiling** — the strongest thing a posture can guarantee
about a governed path on `main`. Every unmeasured cell says so; only the first row has been run against a real
repository.

| Posture | PR/MR required, direct push blocked | The store's key as the exception | Checks required before merge | Force-push / deletion blocked | Native path rule | Ceiling | Source |
|---|---|---|---|---|---|---|---|
| **GitHub, public, organisation on Free** | ✓ `pull_request` | ✓ `DeployKey` bypass | ✓ `required_status_checks` | ✓ | ✗ — `file_path_restriction` refused (`422`), the whole file-metadata family with it | **prevention, by the checks** | **measured 2026-09-02/03** on this repository, five probes, every rule created disabled, read back, deleted |
| **GitHub, private, organisation on Free** | ✗ — rulesets and protected branches on private repositories need **Team or higher** | — | ✗ — CI runs, but nothing can be *required* | ✗ | ✗ | **detection only**; Actions minutes metered | GitHub's plan comparison, fetched 2026-09-03; **unmeasured** |
| **GitHub, Team or higher** | ✓ | ✓ | ✓ | ✓ | unverified — the probe's refusal did not say *why*, and the family may sit above Team | prevention, by the checks | **unmeasured** |
| **GitLab, Free** | ✓ *Allowed to push and merge: No one* | ✓ deploy keys can be added to *Allowed to push and merge* | ✓ *Pipelines must succeed* (all tiers) | ✓ force-push blocked by default on a protected branch | ✗ on Free — Code Owner approval and group-level rules are Premium | prevention, by the checks | GitLab docs, fetched 2026-09-03; **unmeasured** |
| **Gitea / Forgejo, self-hosted** | ✓ protected branch with a push allowlist | ✓ *"deploy keys that already have write access can also be allowlisted"* | status checks in branch protection — **unverified** | ✓ | ✓ **protected file patterns** — *"commits and merge attempts that touch one of the files are rejected"* | **prevention, natively and by the checks** | Gitea docs, fetched 2026-09-03; **unmeasured**; the checks need the forge's own runner |
| **Local first, pushed to a public forge** | the origin's row | the origin's | the origin's | the mirror restricts *updates* to the mirror's credential — `update` is a core GitHub rule, available where the branch rules are | the origin's | **the origin's** — the mirror can only ever hold what passed the origin's gate | Gitea push mirrors sync on push over HTTPS with a token; *"Gitea supports no ssh push mirrors"* — docs, **unmeasured**; the mirror's credential is a token, a different party from the store, and not covered by the deploy-key ruling |

**What every row shares, said once.** The store's own guarantees — compare-and-swap on the document head, a plain
push with no force path, the hash-chained signed history, the clone rebuilt at every start — do not vary by forge.
And nothing in the table stops the store from writing outside `docs/work/`: a deploy key is repository-wide, and the
store's own code is what keeps it to the governed root (S-10). A forge with a native path rule adds a second party's
enforcement of the same line; it does not replace the first.
