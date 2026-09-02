<!-- provenance: schema=1 project=isidium-factory session=cbbf40cf-dee1-4f06-a861-eccb081674f5 actor=amodal1 agent=anthropic/claude-opus-5 generated_at=2026-08-27 status=draft-0 -->

> **Assumes:** the design docs (03 §1.3, 03b §2, 06); the v1 build plan; the deployment record; sync rounds 7bg.1–7bg.8.
> **Descends from:** the owner, 2026-08-27, verbatim: *"let's take these in pieces. my experience is quality degrades rapidly when we run chains which is why this project even exists. durably record the plan somewhwere. we might be able to take them in chunks. break tjem up in sonnet sized chunks. you'll take the first chunk and then hand off to the next agent…"*
> **Expected reader:** one agent per chunk, arriving fresh. Read §0, §1, and **your chunk only**.
> **Status:** **draft-0** — the decomposition and the ordering are the author's; the rulings they implement are owner-ratified (7bg.2, 7bg.8). Nothing here is a design change.

# WP4 — the ruled reshape, in chunks

Three rulings (7bg.8) and one earlier one (7bg.2) change what the store is made of. This document breaks that work
into pieces small enough that **one agent finishes one piece in one clean context** — no chaining, no compaction, no
half-finished seam handed forward.

## 0. How to use this document

1. **One chunk per agent.** Read §0, §1 and your chunk's section. Do not read the other chunks' sections; they will
   not help you and they cost the context this is meant to protect.
2. **Read only what your chunk names.** Each chunk lists its files in scope, the record citations it needs, and the
   traps found while planning. If you find you need something not listed, that is a finding — record it in your
   handoff rather than widening silently.
3. **The green bar is the same for every chunk:** the full test suite passes, `mypy --strict` is clean **over
   `packages/`** — the tests are not under it and carry 46 pre-existing errors (K1's finding 1) — and `ruff check`
   and `ruff format --check` are clean. A chunk is not done until all four are true *and* the chunk's own new tests
   exist and pass. Where a chunk asserts a security property, **mutation-check the assertion**: break the thing on
   purpose and confirm the test fails. K1's first boundary test passed with the boundary disabled.
4. **Update the status table in §2** and **append your handoff line to §4** before you stop. That is how the next
   agent starts without reading your transcript.
5. **A question is not a work order.** If your chunk turns out to need an owner ruling, stop, record the question in
   §4, and hand back. Do not choose for the owner.

## 1. Standing constraints (every chunk)

- **`06-code-constraints.md` C-1 … C-10 apply.** In particular: no default lives in code (C-1, swept by a test); a
  value with alternatives is a typed value, never a formatted string (C-2); refusals are typed and name a rule id
  (C-5); `mypy --strict` with no question-hiding ignores (C-7); a declared limit is written where it bites (C-10).
- **Nothing in WP4 is a design change.** Every chunk implements a ruling already in the record. If the code seems to
  require a design change, that is a finding for §4, not a decision to make.
- **Efficiency is a design constraint, not a cleanup pass** (the house rule, C-8): a call that could be one call is
  one call; a loop that could be an index is an index.
- **Where a limit is chosen** (a byte cap, a timeout, a connection count), it is a named constant with a comment
  saying why that number, and it is stated in the chunk's handoff line.
- **Verify before you act — including on this document** [2026-08-29, after the adversarial round]. Three of the
  "measured" facts in the first version of this plan were false, and two were already ratified into the sync record.
  **A claim you are handed is not evidence.** A brief that says something is measured must say what was run; if it
  does not, or if it does not reproduce, that is a finding for §4 — say so plainly rather than working around it
  silently. Deleting a wrong instruction is a better outcome than following it.
- **Mutation-check every security or limit assertion you write or touch.** Break the property on purpose, confirm
  the test fails, restore, and say in your handoff which mutations you ran and what happened. The rule existed
  before and was applied to one assertion out of six: the boundary was proven and **five declared limits were not**
  — all five survived mutation until K1b-ii, which ran **seventeen** and killed all of them.
  **Use `tools/mutate.py`** [committed 2026-08-30, after K1d]: it takes a TOML spec of mutations, runs each one
  against the whole suite — there is deliberately no way to pass it a test path — names every test that killed it,
  and keeps the pristine bytes in `.mutation-in-flight.json` **on disk**, so a run that is killed mid-mutation is
  repaired by the next invocation (`--restore`) instead of leaving a broken file in the tree for the next command
  to build on. That happened three times while K1d was being built. Commit your spec beside
  `tools/mutations/k1d.toml`: a mutation set is evidence, and it is what a later edit to those files must be
  re-run against. Two of that chunk's
  three survivors were defects in its own *tests*, not gaps in the code: a timeout applied at two places and tested
  at one, and an assertion that could not tell its own timeout from the test's outer bound. **A mutation that
  survives is not always a missing test of the property; sometimes it is a test that cannot see the property.** Restore a mutated file from **its own bytes**, snapshotted before the
  mutation and written back with `Path.write_bytes` — which translates nothing, so the line endings survive (the trap
  `Path.write_text` sets on Windows). **Not `git checkout --`** [corrected 2026-08-29, K1b-ii]: while a chunk is in
  progress the working tree is ahead of `HEAD`, so `git checkout --` does not undo the mutation, it undoes the
  chunk. It cost three files in one step.
- **No test may pass on "nothing came back."** `assert answer is None or status == 431` and `assert result == b""`
  are the class defect this round was called for — and a test whose only assertion is that *something timed out* is
  the same defect wearing a clock (K1b-ii) — a missing limit produces the same silence a working one does, so
  the assertion cannot tell them apart. Every such assertion needs a **positive discriminator**: something only the
  working property produces.
- **C-11: instrumentation is written in the same pass as the code, from K2b onward.** Owner, 2026-08-28: *"it
  should be a durable principle that we log intelligently for opentelemetry across all our systems"*, and *"we
  must role model this for the other systems."* After K2b lands the foundation, a chunk is not done until the
  paths it writes carry their spans, their outcome status and their rule-id attribute. An uninstrumented path is
  treated the way an untested one is. **K1 landed before this rule and is therefore uninstrumented — that debt is
  K2b's to close, and it is the only path allowed to carry it.**

## 2. The chunks

| # | Chunk | Depends on | Size | Status |
|---|---|---|---|---|
| K1 | The edge: the store terminates its own mTLS | — | large (author's own) | **done, then reviewed** — seven findings against it (§4) |
| K1b-i | **The record and the briefs corrected after the adversarial round** | — | medium | **done 2026-08-29** (§4) — this document, the sync record, the deployment record, C-1/C-11/C-12 |
| K1b-ii | **K1's code and tests: the defects the round found** | K1b-i | medium → **large** | **done 2026-08-29** (§4) — all ten items; Q1 and Q4 built; **17 mutations, 17 died**; 141 tests |
| K1b-iii | **The defects outside the edge's files** (`repair`'s grant seam, `install_schemas`, the typed verdicts, the two rule-id renames) | K1b-i | small | **done 2026-08-29** (§4) — all four items; `Refusal.payload()` is now the one constructor **two** of C-12's three doors share; **9 mutations, 9 died**; 160 tests |
| K1c | **The three C-1 violations the widened sweep found** | — | small | **done 2026-08-29** (§4) — all three closed, `PENDING` deleted, **6 mutations, 6 died**. They were found by K1b-ii in files it could not touch, and this row exists because a finding with no owning chunk is a finding nobody does. **Its one owner question is ruled (2026-08-29): C-1 reaches the validator; the registry is threaded.** No question remains inside it |
| K1d | **Lazy registry loading (C-13)** | K1c | small–medium | **done 2026-08-30** (§4) — all four items; the loader is lazy, `installed` costs zero parses, the filename seam is two named refusals; **10 mutations, 10 died**; 186 tests. `Registry.shipped()` 62.3 ms → 1.1 ms, `governed_paths` 78.0 → 24.6 ms. C-13's known violation is closed |
| K2b | **Instrumentation (C-11): the OpenTelemetry foundation, and K1's paths retrofitted** | K1b-ii, **K1b-iii** | medium | **done 2026-08-30** (§4) — all nine items; `core/telemetry.py` (API only) and `core/disclosure.py` (C-12's two-level table); item 0 was **nine** ids, not five; **20 mutations, 19 died first pass, the survivor was a defect in the test and died once corrected**; 177 tests |
| K3 | Delete local mode and loopback | K1b-ii | small–medium | **done 2026-08-30** (§4) — one `Transport` and it is the channel; the client file carries no identity; `init` runs over the channel; **10 mutations, 10 died**. Unplanned and large: `client.cli` stopped importing `cryptography` and `pydantic`, **2529 ms → 741 ms**, which is most of K3b's win arriving early |
| K3b | **The hook stops importing the store** (Q10, ruled 2026-08-30) | K3 | small → **smaller** | **done 2026-08-31** (§4) — the installed script runs `python -m isidium.store.client.hook`; `isidium hook` is the human's door onto the same `check()`; the guard K3 left is widened to `typer` and to `cli.py` itself, and the module it probes is read out of the installed script. **~0.4–0.6 s off every commit**, measured at the door rather than at the import; **7 mutations, 7 died**; 193 tests |
| K4 | `GitCli` becomes bare and object-level; the store's registry source | K3 | medium (**wanted an Opus agent**) | **done 2026-08-31** (§4) — all eight items; a partial bare clone, plumbing writes with `update-ref`'s expected old value, one long-lived `cat-file --batch` (**328 ms → 14.8 ms per read, 22x**), and the footprint **enforced** rather than implied; the store's registry is its own. **11 mutations, 11 died — three survived their first form and one of them was a defect in the code**; 206 tests. **Q11 was raised and ruled during it** |
| K2 | `deploy/` to the one shape — **written once, for the bare clone** | K2b, K3, **K4** | medium | **done 2026-09-01** (§4) — one process and it is the store; caddy, the socket and the trusted hop are gone with the `Caddyfile`; the image installs `[server]` (it never had h11 and so could not have run `serve` at all) and `[telemetry]`; the clone is **rebuilt at every start** and the footprint is reported off it; the healthcheck goes through the front door over mTLS. **Built, started and driven end to end under podman 5.8.3** — clone → mTLS → `init` signed and pushed → `show` — and **6 live mutations, 6 died**. `deploy/healthcheck.py` is new, and `.gitignore` gained the operator's private material |
| K5 | Dependency determinism: the lock, the scan, the update PRs | K1, K2 | small | not started |
| K6 | H-1: caller identity in the journal row | K1, **K2b** | small → **medium** | not started — joins on trace context, does not invent a correlation id; **Q5 lands here** (the caller certificate must carry `clientAuth`), making it four caller-identity properties in one pass |
| K4b | **The author's terminal checks a ref's sub-file locus** | — (**Q11**'s ruling only; not K4's code) | small | not started — the store can no longer look inside a blob, so the line/anchor/symbol check moved to the assembler at dispatch. This closes the feedback gap at the terminal, where the working tree is. **Client-side only; the brief is below.** |
| K7 | Adversarial review round on the reshaped store | K1–K6 | one reviewer | not started — **the observability lens is now one of its dimensions** |

**A note on the names.** `K2b` is a historical label — it was added after K2 and then ordered ahead of it, and
`K1b` was added after the adversarial round. **The table is the order.** Read it top to bottom; never infer
sequence from the letters.

**All nine rulings are taken** (§5): **Q1** (the store starts TLS itself), **Q2** (the two-level
disclosure table), **Q3** (the footprint guarantee is enforced) and **Q6** (the container is written once, after the
bare clone exists) — all 2026-08-29, and all folded into the chunk briefs above rather than left in §5 to be
re-read. **Q5** (the store requires `clientAuth`, and the setup steps say so),
**Q6** (the container chunk moves after the bare-clone chunk), **Q7** (validation verdicts travel as data) and
**Q2b** (the two namespace-less rule ids are normalised). **Q2a** (a new id inherits its namespace's disclosure, except in the
server-side `full` namespaces, which are flagged so a new id there is a build failure) and **Q4** (availability
stays out of the grant matrix; a per-peer allowance keyed on the credential, its value supplied as configuration).
**All nine round rulings are taken, and every chunk below has a complete brief.** The one question raised since,
by K1b-ii's widened C-1 sweep — *does C-1 reach into the validator, which has no registry in hand?* — was
**ruled 2026-08-29** and is written into K1c below. **Q10, K1d's, is ruled too** (2026-08-30: C-13 reaches a module
graph, as a preference and not a prohibition; the hook gets its own entry point) and **built by K3b, 2026-08-31**.
**No question is waiting on the owner.** [Corrected by K3b: three sentences here still said Q10 was open, two of
them contradicting each other in the same paragraph, five days after §5 recorded the ruling — a chunk that reads §2
for its status would have handed the owner a question they had already answered.]

**Q8 ruled 2026-08-29 — C-1 reaches the validator; the registry is threaded.** The question's premise did not
survive measurement: `default_governed()` was read at its *definition* site, but at its five *call* sites a registry
is already in hand or one line away — `validate_tree(tree, registry, …)` and `resolve_effective(tree, registry)`
both take one as a parameter, `store.py` has `self.registry`, and the hook has `repo`, for which
`Registry.for_checkout` exists precisely because a client on a newer toolkit must validate against the versions the
tenant adopted. So there is no registry-less validator to carve out. The two shapes not taken, and why: **(b) read
the shipped registry once at import** would pin the validator to the shipped documents and defeat
`for_checkout` / `from_directory`, re-creating the divergence C-1 forbids one level up — not a duplicated value but
a duplicated registry; **(c) carve the validator out the way `Limits` does** fails its own comparison, because
`Limits` carves out numbers *no schema declares*, whereas `governed`'s manifest is declared in `config@1` itself.
**Verified, not reasoned:** `Registry.shipped().defaults_of("config@1")["governed"]` is equal to
`default_governed()`, and `adopted_version({}, …)` returns `1` from either manifest (measured 2026-08-29).

**Q9 ruled 2026-08-29 — lazy loading is the default, and it is its own chunk (K1d), not a widening of K1c.** The
46 ms `Registry.shipped()` that threading the registry into the hook would cost per commit is accepted in K1c and
repaid by K1d. The principle is recorded as **C-13** in `06-code-constraints.md` at the amplitude the owner gave it
— lazy by default, eager where it is the right *design*, with the burden of evidence on the exception.

**Why the container chunk moved to the end [ruled 2026-08-29, Q6].** `deploy/entrypoint.sh` refuses to start
unless `$TENANT_DIR/.git` exists, and **a bare clone has no `.git`** — the directory *is* the git directory. The
`WORKDIR`, `compose.yaml`'s comment and the README's `git clone <remote> tenant` all assume a working tree. Written
before K4, the deployment would pass its own definition of done against a configuration it was about to discard,
and a file we already knew to be wrong would sit in the tree waiting for a trailing edit at the end of the largest
chunk — which is the half-finished seam this plan exists to prevent. Stale `deploy/` files nobody flagged are three
of this round's findings; repeating that on purpose is worse than repeating it by accident. Q3's ruling sharpened
it further: enforcing the footprint changes the deployment's own clone command and git environment, so writing it
early would mean writing it twice for two independent reasons.

**The cost, accepted with the ruling:** the container arrives later, and the safety gap the owner named
(*"i've been running dangerously on my laptop"*) stays open longer — and if K4 slips, the container slips with it.
**The mitigation, ruled with it:** K4 runs `serve` once against a real bare clone **outside the test suite** before
it hands off (its done-when 7), so the container's first start debuts only the container. The other objection —
that the first start would debut too much new code at once — does not survive C-11: every chunk after K2b
instruments as it goes, so K4's git paths arrive carrying their spans. More code, not more blindness.

**Why this order.** K1 first because the edge is the security-critical piece and because everything else waits on it:
`serve` currently builds its store *through the client's local-mode transport*, so local mode cannot be deleted (K3)
until `serve` builds its own, and `GitCli` cannot go bare (K4) without throwing away work in the local-mode path.
Taking K1 first makes K3 and K4 pure, with no rework.

**K2b then runs before K2, ruled by the owner 2026-08-28.** Standing the container up first would mean its first
start is unobservable — and the first hour is exactly when it is needed: a wrong CA path refuses every caller
silently, on both sides of the connection. Instrumenting first costs nothing, because the SDK's console exporter
puts spans on stderr with no collector, no SigNoz and no egress. It also means K2 is the first chunk written
under C-11 rather than the second thing to need a retrofit.

---

## K1 — The edge: the store terminates its own mTLS

**Ruling (7bg.8):** the store answers its own TLS connection and reads the caller's certificate off the connection it
is authorizing. No proxy, no forwarded header, no trusted hop. **h11** parses; the accept-and-dispatch loop is ours.
HTTP stays.

**Goal.** `isidium serve` listens on TLS, requires a client certificate issued by the registration's CA, maps that
certificate to `(principal, grant)`, and dispatches to the same `Api` the tests already drive — with no ASGI server,
no Caddy, and no `X-Verified-Client-Cert`.

**Files in scope**

| File | What happens |
|---|---|
| `server/service.py` | rewritten: typed `Request`/`Response` and one `handle()`; `Registration` kept (now taking DER, not a PEM string); **`TrustedHop` deleted**; the ASGI `__call__`, the `scope` dicts and the lifespan branch deleted |
| `server/http.py` | **new**: the TLS listener and the bounded per-connection loop over h11 |
| `client/cli.py` (`serve` only) | rewritten: TLS options, and it builds its own `Store`/`Api` instead of borrowing the client's local transport |
| `client/transport.py` (`HttpsTransport` only) | plain mTLS to `host:port`; the Unix-socket path goes |
| `tests/store/test_service.py` | drives `handle()` directly instead of a synthetic ASGI scope |
| `tests/store/test_wp3_apply.py` | the `test_s1_*` hop test is replaced by the boundary test below |
| `tests/store/test_edge.py` | **new**: the handshake boundary and the loop's limits |

**Must not touch:** `server/store.py`, `server/api.py`, `server/gitrepo.py`, `server/journal.py`, `registry/`, the
client's `LocalTransport` (K3 deletes it), `deploy/` (K2).

**Record citations you need** (do not re-derive): 03b §2 first bullet (the edge, pinned 7bg.8); 03b §2 on the caller,
the grant and the refusal being data; sync 7bg.8 for the loop's required properties.

**The shape**

- One `ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)`: `minimum_version = TLSv1_3`, `verify_mode = CERT_REQUIRED`,
  `load_verify_locations(<the registration's CA>)`, `load_cert_chain(<the store's cert>, <key>)`.
- `asyncio.start_server(..., ssl=ctx, ssl_handshake_timeout=…)`. **A failed handshake never reaches the handler** —
  that is the property the boundary test proves.
- Per connection: read the peer certificate DER via `writer.get_extra_info("ssl_object").getpeercert(binary_form=True)`,
  ~~resolve the caller **before** parsing anything~~ **[corrected: you cannot — you must parse to know the route, and
  `/health` must answer a CA-issued peer the registration does not name. The gate is the handshake, which is
  stronger; the caller is resolved per route. K1 deviated here, declared it, and was right to.]**, then parse one
  request with `h11.Connection(our_role=h11.SERVER)`.
- **One request per connection.** Respond with `Connection: close` and close. There is no keep-alive state machine,
  which is where hand-written servers actually break. The call volume makes the extra handshake free (03 §9.6's own
  count is ≈3 store calls per card lifetime).
- Named limits, each with its reason: max concurrent connections (a semaphore), handshake timeout, read timeout,
  write timeout, max request-header bytes, max body bytes. **`Transfer-Encoding` is refused**; `Content-Length` is
  required on `POST` and must be within the cap. Every client is ours.
- The routes are unchanged: `GET /health` → `{"ok": true}` (liveness only, the WP3 review's S8) and
  `POST /call/<verb>` → the `Api` call. The refusal → status map moves across unchanged.

**Traps found while planning**

- `getpeercert(binary_form=True)` gives the **leaf** only. Parse it with `cryptography.x509.load_der_x509_certificate`
  (already a dependency) — one less encode/decode hop than today's URL-decoded PEM header.
- Today's `Registration.caller()` takes a PEM string. Change the parameter to DER bytes; keep the subject matching
  exactly as it is — **full-subject matching and the validity window are K6, not this chunk.** Do not half-do them.
- Generate the test CA and certificates in a fixture with `cryptography`, not by shelling out to openssl — the suite
  must run on the Windows workstation.
- Do not let a handshake failure or a client disconnect propagate into the accept loop; the server must survive both.
- `serve` needs store-side settings (repo path, journal path, tenant, root, signer, registration, TLS paths). CLI
  options are enough for this chunk; **a store-side config file is declared, not built** — record it in §4.

**Done when**

1. New `tests/store/test_edge.py` proves, over a real TLS socket on `127.0.0.1`: a client with **no** certificate, one
   from **another CA**, and an **expired** one are each refused *at the handshake* — the handler is never entered.
   — **ACHIEVED and mutation-proven** (flipping `CERT_REQUIRED` to `CERT_OPTIONAL` fails the test; re-confirmed
   2026-08-29). This is the one property in the tree that is genuinely proven.
2. The same file proves: an over-cap header is refused; an over-cap body is refused; `Transfer-Encoding` is refused;
   a stalled connection is closed by the read timeout; `GET /health` returns 200; `POST /call/<a read verb>` over TLS
   returns the same value the in-process call returns.
   — **PARTLY.** The `Transfer-Encoding` refusal and the declared-length body cap are mutation-proven. The header
   cap and the read timeout are **not**: both tests accept "nothing came back" as a pass, and both mutants survive.
   The connection ceiling, the handshake timeout and the write timeout have **no test at all**. Five of six limits
   are unproven — K1b-ii.
3. ~~`TrustedHop`, the header constant and every mention of a hop are gone from the package.~~ **[corrected: the
   symbol and the header constant are gone — verified, zero matches. Four mentions of "hop" remain, all in
   docstrings explaining its absence, and they should. The item was ticked without being read literally, which is
   the process defect this round was called to examine. The satisfiable sentence is: **no `TrustedHop` symbol and no
   forwarded-header constant survive**.]**
4. The full suite is green, `mypy --strict` clean, `ruff` clean. — **ACHIEVED**, 125 passed, re-run 2026-08-29.
5. **Ruled in 7bg.8 and never built:** `Content-Length` **required** on `POST`. Measured 2026-08-29 — a `POST` with
   neither `Content-Length` nor `Transfer-Encoding` is parsed and dispatched into the verb. K1b-ii's.

---

---

## K1b-i — The record and the briefs, corrected (done 2026-08-29)

**Why it exists.** An adversarial round (`review-artifacts/2026-08-29-design-and-plan/`) found 28 defects across the
design record, this plan and K1. Its verdict: *"the design is sound; the record is not yet trustworthy as a
specification."* Three chunks were briefed to do something wrong and none had started. This chunk fixed the words
so that the chunks after it are not sent to build against false facts.

**Every finding was reproduced before it was acted on**, per the rule this round added to §1. Two of the review's
own claims did not survive that and are corrected below — the review is not evidence either.

**What it touched:** this document; `docs/design/00-sync-record-2026-08-14.md` (7bg.11's finding 3 marked in place,
7bg.15 and 7bg.16 added); `docs/build/2026-08-27-deployment-setup-and-open-items.md` (S-1 … S-3, S-9, the
uvicorn/hypercorn section); `docs/design/06-code-constraints.md` (C-1, C-11, C-12). **No code, no tests.**

---

## K1b-ii — K1's code and tests: the defects the round found

**Goal.** Close the eight code defects in the edge and make its limits mean what they say. Nothing here is a design
change: every item is either a ruled property that was not built, or a test that does not test what it claims.

**Files in scope:** `server/http.py`, `server/service.py`, `client/cli.py` (`serve` only), `client/hook.py` (item 8
only), `tests/store/test_edge.py`, `tests/store/test_service.py`, `tests/store/test_wp3_apply.py`,
`tests/unit/test_no_code_defaults.py`.

**Must not touch:** `server/store.py`, `server/api.py`, `server/gitrepo.py`, `server/journal.py`, `registry/`,
`deploy/`, `client/transport.py`, `client/config.py`, `client/install.py`. Three findings sit against those files
and are **K1b-iii's**, not yours to widen into.

**The work, each item measured and reproducible**

1. **`Content-Length` required on `POST`** — ruled in 7bg.8, never built. `_framing()` checks that
   `transfer-encoding` is absent and that a *present* `content-length` is within the cap; it never requires one.
   Measured: a `POST` with neither header is parsed and dispatched into the verb. Conformance, not a decision.
2. **The declared header cap does not bite where it says.** `Limits.max_header_bytes` is 16 KiB, but h11's cap
   applies to an **incomplete** event, so anything arriving inside one 64 KiB `_READ_CHUNK` is parsed first.
   Measured: complete header blocks of 8, 32 and 60 KiB all return 200; 128 KiB returns 431. The real bound is an
   unnamed module constant, 4× the named one. C-10 says a declared limit is written where it bites — so either the
   declared limit becomes the true one or the constant is named and the declaration says 64 KiB. Say which, and why.
3. **A malformed client certificate leaks the parser's text to an unidentified peer.** Measured: garbage DER returns
   `400 {"rule": "service.arguments", "detail": "error parsing asn1 value: ParseError { kind: ShortData … }"}`.
   `caller_of()` is called inside the block whose `except (KeyError, ValueError, TypeError)` becomes
   `service.arguments`. A certificate that will not parse is an **authentication** failure: raise the auth refusal
   where the certificate is parsed. This is the defect that motivated C-12, and C-12's table as written renames it
   rather than closing it.
4. **An unexpected exception gives the caller nothing at all.** `_connection` catches four exception types and
   `handle` catches five; anything else — a `RuntimeError`, an `AttributeError`, a bug — escapes both, and the
   caller gets an opened-then-closed connection with no status and no rule id, indistinguishable on the wire from a
   refused handshake. The server survives, which is right. The caller must get a status and a rule id (C-5), and
   the detail must go to the record, not to the caller (C-12).
5. **`HEAD /health` answers nothing.** `_respond` always sends a `h11.Data` frame; h11 forbids a body on a response
   to `HEAD` and raises `LocalProtocolError`, which is swallowed by a branch whose comment says *"the peer never
   completed a request we may answer"* — untrue here. A health checker configured with `HEAD` reports the store down
   with no diagnosis anywhere. Measured.
6. **Three small ones.** (a) The runtime body-accumulation cap at `http.py:152` **cannot fire** — `_framing` refuses
   an over-cap declared length first and h11 delivers no more `Data` than the declared length; it is the only thing
   that looks like it enforces 1 MiB at runtime and it does not. (b) `STATUS` is a **mutable module-level dict**,
   and K2b is about to make it the disclosure table. (c) `serve`'s `host` defaults to `"0.0.0.0"` in the binary —
   `Limits` carves itself out of C-1 explicitly with a stated reason; `host` does not.
7. **Five limits are declared and untested; two tests pass on silence.** Reproduced 2026-08-29 — three positive
   controls die as they must, and the header cap, read timeout, connection ceiling, handshake timeout and write
   timeout **all survive mutation**. `test_edge.py:389` (`assert answer is None or status_of(answer) == 431`) and
   `test_edge.py:406` (`assert … == b""`) both accept "nothing came back". Give each limit a test with a
   **positive discriminator**, and mutation-check every one. This item is the reason the round happened; it is not
   optional and neither is reporting which mutations you ran.
8. **A live C-1 violation the C-1 sweep cannot see.** `client/hook.py` returns a hardcoded `"docs/work/"` when it
   finds no configured root — `config@1`'s own declared default — and `tests/unit/test_no_code_defaults.py` passes,
   because it walks only *absent-key fallbacks* and this is a bare `return`. Fix the hook (it re-opens the WP3
   review's S5 defect: a checkout whose root is elsewhere gets a hook that protects nothing) **and widen the sweep**
   so the shape is caught next time. C-1 now says it is partly enforced; this is what closes that.

9. **The edge starts TLS itself, per connection — ruled 2026-08-29 (Q1), and this chunk builds it.** Replace
   `asyncio.start_server(…, ssl=ctx, ssl_handshake_timeout=…)` with a plain TCP listener whose handler calls
   `await writer.start_tls(ctx, ssl_handshake_timeout=…)`, catching the failure. **Check the connection ceiling
   before `start_tls`, not after** — that is half the point of the ruling: today the ceiling sits behind the
   handshake, so an unauthenticated peer can drive unbounded concurrent handshakes without meeting it. Classify the
   failure into a **typed reason** (no certificate · untrusted issuer · expired · verify-failed · timeout ·
   protocol) from `ssl.SSLError.reason` / `verify_code` — a typed value with one renderer, never a formatted string
   (C-2). **Leave one call site and that typed value; K2b hangs the counter there.** Do not add the counter here.
   The ruling's three conditions are done-when items, not suggestions:
   (a) the boundary mutation check is **re-run under the new shape** and still fails when the certificate
   requirement is relaxed — the property is re-proven, not assumed to survive a reshape;
   (b) a test asserts the classification is **correct per refusal class**, not merely that something was classified;
   (c) a test asserts a peer that completes TCP and then says nothing is closed by the **handshake timeout** — the
   store passes that timeout now, so it is the store's to prove.

10. **A per-peer connection allowance — ruled 2026-08-29 (Q4).** Measured: at a ceiling of 8, one authorised
    caller sending an unterminated request line held all eight and the next legitimate caller was refused in
    0.05 s; at the shipped 64 and a 30 s read timeout that is a renewable total outage costing nothing to sustain,
    from a `contributor` credential held by a language model. Item 9's ceiling bounds the *work* an unauthenticated
    peer can cause; it does **not** stop an authenticated caller holding slots. So:
    - **Key the allowance on the credential, not the grant**: resolve the credential to a principal when the
      registration names it and key on that; otherwise key on the **fingerprint of the presented certificate
      bytes** (hash what the peer presented — do not re-encode it; that is the same defect K6's trap names).
      Both are available right after the handshake and before anything is parsed.
    - **The unregistered CA-issued peer is its own class with its own named allowance** — the healthcheck, an
      orchestrator probe. It is not a grant and not a principal, and its allowance is deliberately small. Today it
      has no per-peer bound at all, so a leaked probe certificate can exhaust the store.
    - **Both allowances are supplied values, not constants** (C-1, C-10). Availability is deliberately **not** in
      the grant matrix — the reasoning is in §5 under Q4, and a one-line comment at the matrix's site is welcome
      so a later agent does not "fix" the omission.
    - The refusal needs a rule id and a status. Its **disclosure row is K2b's** — it is about the caller's own
      usage, so `full` is defensible, but the table is written there, not here.
    - Mutation-check it like every other limit: remove the allowance and the test must fail.

**Done when.** Items 1–10 land; every security or limit assertion in `tests/store/test_edge.py` is mutation-checked
with the results in the handoff; no assertion in that file can pass on "nothing came back"; the green bar holds
(125 tests were green at the start of this chunk, re-verified 2026-08-29 — yours will be higher).

---

## K1b-iii — The three defects outside the edge's files

**Small, and it exists because K1b-ii may not touch these files.** **It runs before K2b** — K2b writes the
disclosure table, and item 4 renames two of the rule ids that table must carry. Nothing in it waits on a ruling any
more.

1. **`repair` is authorized outside the seam the design calls structural** (`server/store.py`). Every other verb
   goes through `_require(caller, call)` over `GRANT_MATRIX`; `repair` has a hand-written `if caller.grant !=
   "owner"`. `identity.py` says the check is *"ONE function over a matrix VALUE"* so the realm can supply the matrix
   later — and `repair`, the one act that can rewrite the integrity record, is the verb that would not move.
   Behaviour is identical today (`owner` holds `"*"`), so this is a pure seam fix. **Also worth recording rather
   than fixing here:** reads are gated at the `Api` layer while writes are gated at the `Store` layer, so the
   authorization boundary is in two places. Not exploitable — reads are unrestricted by design — but the Rust port
   will transcribe whichever shape it finds.
2. **`install_schemas` can write shipped bytes under a foreign manifest** (`client/install.py`). It takes a
   `registry` argument, writes `INSTALLED` from it, and then copies the schema files from
   `resources.files("isidium.store.registry")` — **always the shipped package**, never the argument. Latent: every
   caller passes `None` today. It sits in the one function whose stated purpose is byte-identity, which is where a
   latent mismatch is worth closing.
3. **Validation refusals carry their typed verdicts on the wire — ruled 2026-08-29 (Q7).** `ValidationRefusal`
   carries a list of typed `Refusal`s and flattens it into a `"; "`-joined `detail`; `Response.refusal` then drops
   the list, so the caller receives the field names only inside prose. Add an **array of typed verdicts** to the
   refusal payload — each with its own rule id, path and detail — and reconstruct it client-side. **Additive:** a
   client reading only `{rule, path, detail}` keeps working, and `detail` stays as the rendered summary so nothing
   has to parse it apart. Each verdict is subject to the disclosure table like any other refusal.
4. **The two namespace-less rule ids are normalised — ruled 2026-08-29 (Q2b).** `validate` → `validate.failed`;
   `integrity:time` → `integrity.time`. Measured before the ruling: no client or production code matches either.
   `validate` is raised once in `server/store.py` and asserted in **11 tests**; `integrity:time` is raised in
   `server/store.py` and `registry/config.py` and named once in the card schema (03) as the rule for the
   timestamp-ordering check — update that line with the code. **This chunk runs before K2b** so the disclosure
   table is written against the final ids rather than renamed underneath it.

---

## K1c — The three C-1 violations the widened sweep found

**Why this is a chunk and not a footnote.** K1b-ii widened the C-1 sweep to the shapes C-1 already named — a bare
`return` of a declared default, and a function's default argument — and it found **three violations in files that
chunk was forbidden to touch**. They were recorded in §4, in C-1, and in the sweep's own `PENDING` table, which
fails a test when one of them is fixed so the list cannot rot into an allow-list. But **§2's table is the order of
work, and nothing in it owned them**: every document said "not yours", which is how three known defects get read as
somebody else's by every agent in turn. This row is the fix for that, and the lesson generalises — *a finding
without an owning chunk is a finding nobody does.*

**Files in scope:** `client/cli.py` (`init`'s signature only), `server/signer.py` (`RemoteTotp.__init__` only),
`registry/config.py` (`default_governed` and its call sites), `tests/unit/test_no_code_defaults.py`.

**Must not touch:** `server/http.py`, `server/service.py`, `server/store.py`'s integrity core, `deploy/`.

**~~If item 3 turns out to reach into `store.py`, that is the signal to stop and hand back.~~** [**Superseded
2026-08-29.** That clause was written while item 3's question was unruled. Q8's call-site table names
`server/store.py:804` outright, so the line was built rather than handed back — one line, in the `init`
policy-chain bootstrap, not the integrity core. **The owner was shown the conflict at closeout and ruled it stands:
*"leave it, the ruling names it."*** Recorded here so the two sentences are not read against each other again.]

**The work**

1. **`isidium init --root` repeats `config@1`'s declared default** (`client/cli.py:60`, measured by the sweep
   2026-08-29). `root: Annotated[str, typer.Option(...)] = "docs/work/"` is a function default argument holding a
   value the adopted schema version declares. Conformance, not a decision: the option becomes `str | None = None`
   and the effective value is resolved from the installed registry's `config@1` where `init` already builds the
   client config. **Check what `init` writes into `.isidium/client.toml` afterwards** — the hook now *refuses*
   rather than guessing when it cannot find a root (K1b-ii item 8), so an `init` that records no root turns a
   silent failure into a loud one on the tenant's next commit. That is the right direction and it is also a
   behaviour you must not reach by accident.
2. **`RemoteTotp.__init__(poll_interval_ms=2000)` repeats `config@1`'s `remote-totp` default**
   (`server/signer.py:119`). Same shape, same fix: the constructor takes the value, the caller supplies it from the
   effective config. `timeout_s=600` beside it is *not* flagged — the declared key is `time_skew`, a different key
   that happens to share the number — so change only what the sweep names, and say so in your handoff.
3. **`default_governed()` is `config@1`'s declared manifest, written again in code** (`registry/config.py:184`) —
   **ruled 2026-08-29, and the ruling is the next paragraph; read it before you write anything.** It has five
   callers: `client/hook.py` twice (the manifest when a checkout's `config.toml` has none), `registry/config.py`
   twice (`adopted_version` fallbacks), and `server/store.py:804`. It is a live fallback path, not a stray literal.

**Item 3's ruling** [Q8, owner, 2026-08-29 — do not re-open it, and do not re-derive it]. **C-1 reaches the
validator, and the registry is threaded.** `default_governed()` is deleted; the manifest comes from
`registry.defaults_of("config@<n>")["governed"]`.

The question was raised from `default_governed()`'s *definition* site. At its *call* sites the registry is already
in hand or one line away — **measure this yourself before you start, because the whole ruling rests on it**:

| call site | the registry it already has |
|---|---|
| `registry/config.py:312` | inside `validate_tree(tree, `**`registry`**`, …)` — a parameter |
| `registry/config.py:784` | inside `resolve_effective(tree, `**`registry`**`)` — a parameter |
| `server/store.py:804` | `self.registry` |
| `client/hook.py:67, 69` | none today — `Registry.for_checkout(repo)`, and `repo` is in hand |

**The circularity dissolves; do not build a fixed-point resolver for it.** `adopted_version` consults the manifest
**only** when the file has no `[[governed]]` table, and in that case the version is whatever the head `schema` key
names. `config@N`'s own default manifest names `config@N` for `config.toml`, so the answer is the head key. That is
a fixed point, not a loop — and **nothing asserts it today**. Add the invariant test: for every installed
`config@N`, its declared default manifest's `config.toml` row names `config@N`. Without it, a future `config@2`
whose default manifest still says `config@1` would break the resolution silently.

**One guard you must add.** At `registry/config.py:312` the code has *already* recorded `config.schema-unknown`
just above and then calls on. `defaults_of` on an uninstalled ref raises, so that branch must be skipped when the
version is not installed — a validator that raises where it meant to record a refusal is a worse defect than the
one you are fixing.

**What the hook's registry costs, and why you pay it anyway.** `Registry.for_checkout` adds **46 ms per commit**
(measured 2026-08-29: 24 ms reading and parsing eight documents, 10 ms content-addressing them; `governed_paths` is
called once per hook run, so it is once per commit, not once per path). `for_checkout` falls back to the shipped
registry when a checkout has none, so **this opens no new refusal path**. The cost is accepted here and repaid by
**K1d**, which makes the loader lazy — that is a separate chunk by the owner's ruling (Q9) and **is not yours**.
Record the 46 ms in your handoff as a measured, scheduled debt.

**Two things not to touch while you are in there.** `resolve_effective`'s `v = s if … else 1` is a schema-version
*selection*, not a declared default — the sweep judges the keyless shape on a distinctive value and `1` is not one.
Leave it, and say in your handoff that you looked. And `Registry.__init__`'s eager content-addressing is C-13's
concern and K1d's work; do not start it.

**Done when.** **All three** items land and **all three** `PENDING` entries are **deleted** (the sweep's second
test fails until they are) — item 3 is ruled now, so there is nothing left here to hand back. `default_governed()`
no longer exists. The `config@N`-names-itself invariant test is added and passing, and the uninstalled-version guard
at `registry/config.py:312` is in place. The green bar holds — full suite, `mypy --strict` over `packages/`,
`ruff check` and `ruff format --check`. There is no security or limit assertion in this chunk, so there is nothing
here to mutation-check; say that in your handoff rather than leaving the question open. Report the hook's measured
46 ms as K1d's scheduled debt, not as an open question.

## K1d — Lazy registry loading (C-13) (done 2026-08-30)

**Why this is its own chunk** [Q9, owner, 2026-08-29]. K1c threads a registry into the pre-commit hook, which makes
the hook pay **46 ms on every commit** to read the one document it needs. Making the loader lazy repays that and
more — parsing `config@1` alone costs **8.4 ms** against `Registry.shipped()`'s 46 — and it repays it for *every*
registry consumer, not just the hook: `for_checkout` runs on every client transport call, and `shipped()` on every
codegen path. It was offered as a widening of K1c and the owner **declined the widening and kept the work**, because
it opens a behaviour seam (below) that has no business being a trailing edit inside someone else's chunk. The owner's
frame, verbatim: *"lazy loading is an important principle for us as this system increases in complexity and all the
systems begin to run on the same machines with limited cmpute and memory."*

**Where the 46 ms actually goes** [measured 2026-08-29 — and the first measurement of this was **wrong**, so
reproduce it]: **24 ms** reading and parsing the eight schema documents (52%), **10 ms** content-addressing them
(23%). The session that raised this first reported content-addressing as "most of it" from *reading* the
constructor; measuring split it the other way round. **Lazy documents are the win; lazy addressing is a rider.**

**Files in scope:** `registry/loader.py`, its callers, and the tests that read `Registry.installed` / `.addresses`.

**Must not touch:** `server/store.py`'s integrity core, `deploy/`, anything K1c is mid-flight on.

**The work**

1. **`_docs` becomes ref → thunk**; `get()` forces one document. `check_all()` and codegen force all, which is
   correct and is C-13's second carve-out — **write the carve-out note at those sites**, since C-13 is enforced by
   the shape of the exception and an eager load with no note is the finding.
2. **`installed` comes from the filenames**, which already encode `name@version` (`config@1.toml`), so the ref set
   costs a directory listing and **zero parses**.
3. **`addresses` becomes a `cached_property`** returning the full dict. Its only consumers are `install.py`'s
   `INSTALLED` file and one test, neither in a hot path, so forcing everything on first touch is right and the
   public shape does not change.
4. **`from_directory`'s eager `not docs` check stays eager** — `registry.not-installed` is C-13's first carve-out,
   a startup contract that must fail at startup. Note it at the site.

**The behaviour seam, and it is the reason this is not a footnote.** `from_directory` today keys documents by their
**parsed contents** (`f"{doc['name']}@{doc['version']}"`), deliberately not trusting the filename. Lazy loading must
key by **filename** to avoid parsing. A file named `config@1.toml` declaring `version = 2` keys as `config@2` today
and as `config@1` lazily. That divergence needs a rule — **the filename must agree with the contents, checked when
the document is forced** — which means a **new refusal id** and a test for it. Name it, do not leave it implied.

**Done when.** The loader is lazy; the three carve-out notes are written at their sites with their reason; the
filename-agreement refusal exists with a test; `installed` performs zero parses (assert it, do not assume it); the
hook's per-commit cost is **re-measured** and both numbers appear in the handoff; the green bar holds. C-13's
recorded open violation is closed and that line in `06-code-constraints.md` is updated.

## K2b — Instrumentation (C-11): the OpenTelemetry foundation (done 2026-08-30)

**Ruling (7bg.12, C-11):** everything built is exposed to OpenTelemetry; SigNoz and LangGraph consume it; **this
repository is the role model other systems copy**, so the pattern matters as much as the coverage.

**Goal.** The foundation every later chunk instruments against, plus K1's existing paths retrofitted — the one
uninstrumented debt in the tree.

**The library/application split is the design, not a detail.** Instrument against **`opentelemetry-api`**, which is
small, stable, and returns no-op tracers and meters when no SDK is configured: **zero egress** by default — measured
2026-08-29, 0 outbound connection attempts through a full span-and-counter cycle, with neither the SDK nor any
exporter imported. ~~zero overhead~~ **[corrected: a no-op `start_as_current_span` costs ~20 µs against a 0.13 µs
baseline — the context attach dominates; `start_span` without it is ~2.6 µs. Negligible at three store calls per
card lifetime; **not** negligible if a span goes inside a loop over governed paths or journal rows. Since this
repository is the pattern others copy, copy the corrected sentence: negligible per call, not free per iteration.]** The **SDK and the OTLP exporter are a `[telemetry]` extra**, supplied by the deployment. The store's
container is deliberately small (7bg.8) and its egress is allowlisted (7be.2) — a distribution in this namespace
must never force an exporter or a network call on the process that embeds it. This is the half other systems copy.

**In scope:** one small module holding the tracer/meter accessors and the attribute vocabulary; spans and metrics
through `server/http.py` and `server/service.py`; the `[telemetry]` extra; a test using the SDK's **in-memory span
exporter** that asserts the expected spans, statuses and attributes — that test is C-11's enforcement and the reason
the rule was allowed into `06-code-constraints.md` at all.

**The vocabulary is already chosen — do not invent one.** The journal and the refusals are named
`subject / action / resource / context` so isidium G7's policy engine is a swap rather than a retrofit (03b §2), and
every refusal already carries a **rule id** (C-5). Attributes use those. The outcome is the span's status; the rule
id is an attribute; neither is a formatted string (C-2).

**Traps found while planning**

- **A refused handshake cannot be counted at all in the shape K1 built — and the replacement is a ruling, not a
  trap.** The first half stands: with `CERT_REQUIRED`, a peer with no certificate, the wrong CA or an expired one
  **never invokes the connection callback**, so anything counted inside `_connection` is by definition a peer that
  already passed the boundary. ~~To see those at all you must install an exception handler on the serving event
  loop, which is where asyncio reports them.~~ **[FALSIFIED — measured twice, independently, 2026-08-29: across all
  three refusal classes the loop exception handler is invoked **0** times and the `asyncio` logger emits **0**
  records at DEBUG. The cause is in the stdlib and is not going to change: `ssl.SSLError` subclasses `OSError`, and
  `asyncio.sslproto._fatal_error` logs an `OSError` only when the loop is in debug mode — it never calls the
  exception handler. `tests/store/test_edge.py` installs a silencing handler commented *"refused handshakes are
  data"*; it has been silencing nothing.]** **Three replacements were measured. Choosing between them is Q1 (§5)
  and it is the owner's. Do not pick one.**
- **Metrics, not rows, for anything an unauthenticated peer can trigger.** A record per hostile connection is a
  denial of service through the logging. Counters before authentication; spans with identity after it.
- **A telemetry id never enters hashed content.** A trace id inside a journal row's `c` would make the chain depend
  on whether telemetry was configured — C-9 forbids that. It belongs beside the hashed content, where `sig` already
  sits. K6 joins on trace context; it does not invent a correlation id, which is why this chunk precedes it.
- **Three streams stay separate.** The hash-chained **journal** is evidence and must not absorb telemetry, or the
  reconciliation's invariant — every row explains a byte transition — dies. Telemetry leaves the process; the
  journal does not. Governed content, prose and key material are never attributes.
- **K5 must pin the new dependency**, API and extra alike, in the lock with hashes.

**Ruled by the owner 2026-08-28 (C-12) — the question is closed, do not re-ask it.** What a refused caller is told
versus what only the record keeps: **before the caller is identified, the rule id and nothing else; after, detail
about them and their request but never about us.** The reasoning and the enforcement are in the code-constraints
document; what follows is that ruling applied to the rule ids that exist today, so you do not re-derive it.

| Rule id | Disclosure | Why |
|---|---|---|
| `auth.no-client-certificate` | terse | pre-identification. The operator message it carries today is a *deployment* diagnosis and belongs on stderr, where the operator is — not in a response the caller cannot act on |
| `auth.unknown-client` | terse | pre-identification: the certificate parsed, the registration does not name it, so we do not know who is asking. Stop echoing the subject back |
| `service.route`, `service.malformed`, `service.transfer-encoding`, `service.body-too-large` | terse | pre-identification, and the rule id already carries the whole meaning |
| `write.grant`, `write.requires-owner` | full | about them: which grant they hold and what it does not reach |
| `write.stale`, `write.locked`, `write.no-change` | full | about their request, and directly actionable |
| every validation refusal (`head.typed`, `config.schema-unknown`, the grammar and profile rules) | full | **the protected set.** Naming the field is what lets an agent self-correct instead of escalating |
| each entry of a `validate.failed` payload's `verdicts` array | by its own rule id | built by K1b-iii. A verdict is a refusal and takes its own row here; a terse one contributes its rule id and nothing more. **Assert against the array, never against `detail`** — the rendered string names the field too, so a substring check goes green over the defect |
| `show.unknown`, `api.unknown-call`, `governed.unknown-path` | full | about what they asked for; reads are unrestricted anyway, so an authorized caller could learn it by listing |
| `signer.*` | terse | about us. The status already says whether to retry (502 / 503 / 504); which backend and what skew go to the record |
| `service.arguments`, `service.body` | **authored, then full** | about their request, but the text today is a raw Python exception — author it, and send the original to the record |

**Build it as one table.** A rule id's status and its disclosure are two facts about one thing; two maps drift. The
existing status map is the natural home. **The default for an unclassified rule is terse** — forgetting must be
safe. The sweep that enforces it is the same shape as the no-code-defaults sweep already in the tests.

**This is why the withheld detail needs the unconditional floor.** Trimming a response only relocates information if
something catches it. Plain logging to stderr always runs; a span no-ops without an SDK. The withheld detail goes to
the log record, and the span carries the structure.

**Three things measured before this chunk was handed over — do not rediscover them.**

1. **OpenTelemetry is not installed on this workstation.** `opentelemetry-api` becomes a hard dependency of
   `isidium-store`; `opentelemetry-sdk` is needed by the tests and by the console exporter. Prefer the **HTTP** OTLP
   exporter over gRPC in the `[telemetry]` extra — gRPC drags in a large binary wheel for no gain here.
2. ~~**Classify by namespace, not by rule id.** A sweep finds roughly 130 rule ids across 28 namespaces … the
   disclosure table therefore keys on the namespace.~~ **[WITHDRAWN 2026-08-29. It contradicts C-12's ratified
   "one table, keyed by rule id", and the count behind it is wrong. The key is now Q2 (§5) and it is the owner's.
   Three measurements bear on it, none of which existed when this line was written:**
   **(i)** C-12's own table **splits the `service` namespace** — `service.route` / `.malformed` /
   `.transfer-encoding` / `.body-too-large` are terse while `service.arguments` / `.body` are authored-then-full —
   so a namespace key cannot express the ruling it exists to implement.
   ~~**(ii)** **Two rule ids have no namespace at all**: `validate` (no separator, raised by `ValidationRefusal`) and
   `integrity:time` (a colon, not a dot).~~ **[CLOSED 2026-08-29 by K1b-iii — `validate.failed` and
   `integrity.time`. `tests/unit/test_rule_ids.py` fails the build on a third, so your table is written against
   final ids. Its `swept()` is also the sweep this chunk needs; extend it rather than writing a second one.]**
   **(iii)** The real counts, from a sweep that follows the `_r(rs, "<rule>", …)` helper form as well as
   `Refusal(…)`: **150 distinct rule ids across 34 namespaces** — not "roughly 130"/28, and not the review's 91/28.
   What both earlier scans missed is most of the validation surface: `profile.*` (28), `config.*` (20),
   `relation.*`, `scenario.*`, `surfaces.*`, `ext-schema.*`. Re-run the sweep; do not trust any of the three
   numbers, this one included.**

   **Whichever key is ruled, the sweep cannot exist until every rule id has one constructor.** Five ids are built
   straight into a response body and never pass through `Refusal` at all — `service.route` and `service.arguments`
   in `server/service.py`, `service.malformed`, `service.body-too-large` and `service.transfer-encoding` in
   `server/http.py` — and two more reach a caller indirectly (one returned from a helper in `server/refs.py`, one
   built by concatenation in `server/store.py`). A sweep keyed on the refusal type is blind to exactly the surface
   C-12 governs. **Building that one constructor is this chunk's first piece of work, before any table.**

   **Half of it exists [K1b-iii, 2026-08-29] — read this before you start it.** `Refusal.payload()` is now the one
   serialisation of a refusal, and **two of the three doors call it**: `Response.refusal` and `McpServer._call`
   (which used to build its own dict, so a change made at the HTTP door alone would have missed the tool surface —
   the door C-12 and Q7 are both argued from). **Your disclosure filter goes there, once.** What is still open is
   the other half of the sentence above: the five ids that never become a `Refusal` at all, and the two that reach
   a caller indirectly. Those are yours. The CLI door prints `str(r)` and is a human surface, so it needs no
   payload — but it is the third door the ruling counts, and it must not grow one.
3. **This chunk ripples into two existing test files** — three was one too many. `test_service.py` and
   `test_wp3_apply.py` assert on the *detail text* of pre-identification refusals, exactly the text C-12 removes.
   Budget for those; they are not incidental. ~~and `test_edge.py` installs a silencing exception handler that the
   counter must replace~~ **[void — the handler catches nothing (see the trap above), so there is nothing to
   replace. **Q1 is ruled, so `test_edge.py` does gain a counter assertion** — K1b-ii reshapes the edge and
   leaves a typed classification of the refusal; this chunk hangs the counter on it and asserts that it moves with
   the right reason for each refusal class.]**
4. **`server/signer.py` was read for this chunk** [2026-08-29]. No earlier pass had opened it, and C-12 classifies
   `signer.*` terse without anyone having looked. It raises four ids — `signer.time-skew`, `signer.key-type`,
   `signer.timeout`, `signer.declined` — and two more, `signer.unavailable` and `signer.backend-unavailable`, are
   raised elsewhere. **The terse classification holds, with two cases its rationale does not actually cover.**
   `signer.key-type` is raised by `SoftwareKey.load()` at **start-up**, from `serve`'s `--signer` option, and
   carries the **filesystem path of the private key** in its `path` field: it is not a call refusal at all, and it
   must never appear in a caller-facing table — it belongs on stderr with the other operator diagnoses.
   `signer.time-skew` is the one `signer.*` id that is genuinely **actionable by the caller** (their `at` is outside
   the signing service's window); trimmed to a bare rule id behind a 502 it reads as "retry later", which is the
   wrong advice. Neither re-opens the ruling; both are for whoever fills in the table.
5. **A validation refusal does not currently carry its fields as data**, which matters because that is the one class
   C-12 *protects*. `ValidationRefusal` collects typed `Refusal`s and then sets `detail` to
   `"; ".join(str(r) for r in refusals)`; `Response.refusal` sends `{rule, path, detail}` and drops the list. So the
   field names reach the caller only inside prose, to be regexed apart — the shape C-2 forbids — and this chunk's
   done-when 2 would go green against the joined string. The value is built in `server/store.py`, which K2b may not
   touch; **carrying the typed verdicts to the caller is a wire-format change and is Q7 (§5).**

**Done when**

0. **One constructor for every refusal a caller can receive**, before any table exists — see measured item 2
   below. Until that lands, items 2 and 3 cannot be honestly asserted.
0b. **The table has its ruled shape (Q2):** one table carrying status *and* disclosure, keyed by namespace, with
   named rule ids overriding their namespace's default; a namespace the code can raise and the table does not name
   is a **build failure**, not a fall-through. **Q2a and Q2b are ruled too, so the shape is fully specified:** a
   new rule id **inherits** its namespace's disclosure, except in the `full` namespaces that live in server code
   (`write`, `show`, `governed`, `api`), which carry a **declare-explicitly** flag making a new id there a build
   failure; and the two ids that had no namespace are already normalised by K1b-iii (`validate.failed`,
   `integrity.time`), so write the table against those. Read §5's Q2, Q2a and Q2b once — the reasoning is there and
   you should not re-derive it.
1. A test using the SDK's in-memory span exporter asserts the expected spans exist for one full call, with the
   outcome as the span's status and the rule id as an attribute. **That test is C-11's enforcement** — the rule was
   admitted to the code-constraints document on the promise of it. *(Verified achievable: instruments created at
   import time bind to a provider configured afterwards, so a test may install the in-memory exporter late.)*
2. A test asserts a pre-identification refusal carries no detail, and that a validation refusal still names its
   field. Plus the sweep: every rule id the code can raise appears in the table (C-12's enforcement).
   **Two conditions on this item, or it goes green over a live defect.** (a) The sweep asserts that **every
   namespace the code can raise appears in the table**, and that **every rule id in a declare-explicitly namespace
   appears too** — that is the satisfiable form of the original "every rule id appears in the table", which was
   unsatisfiable against a namespace-keyed table because no rule id appears in one. Re-run the rule-id sweep
   yourself; three different numbers have been recorded and the most recent (150 ids, 34 namespaces) is the only
   one that followed the `_r(rs, "<rule>", …)` helper form. (b) The refusal a **malformed client certificate**
   produces must be an **authentication** refusal, not `service.arguments`: today it returns the ASN.1 parser's own
   text to a peer with no identity, and C-12 classifies `service.arguments` as post-identification, so implementing
   the table verbatim renames the leak instead of closing it. Fixing that is **K1b-ii's** (it is a two-line change
   in `server/service.py`); this chunk's test must prove it stayed fixed.
3. `service.arguments` and `service.malformed` return authored messages; the original text appears in the record.
4. With **no SDK configured**, the store behaves exactly as it does today and reaches no network: assert it, do not
   assume it. This is the property that lets every other isidium part depend on us.
5. Counters move for the pre-authentication events that *can* be seen from inside the process — the connection
   ceiling, an absent peer certificate, and **the refused handshake**. ~~the refused-handshake counter is wired to
   the event loop's exception handler, because that is the only place those appear~~ **[UNBUILDABLE as written —
   there is no such place; see the corrected trap. RULED 2026-08-29 (Q1): the store starts TLS itself per
   connection, so the refusal is a catchable exception carrying its reason. **K1b-ii builds that shape and leaves
   one call site with a typed reason; you hang the counter there.** Assert the counter moves with the **correct
   reason** for each of no-certificate, untrusted-issuer and expired — not merely that it moved.]**
6. Running `isidium serve` with the console exporter prints spans to stderr. **K2 depends on this working** — it is
   how the container's first start is diagnosed.
7. The full suite is green; `mypy --strict` clean over the packages; ruff clean.

---

## K2 — `deploy/` to the one shape

> **This chunk runs after K4, not before it — ruled 2026-08-29 (Q6). The table in §2 is the order.** It is written
> **once, for the bare clone**, because by the time it runs that is the only shape the store has. Everything below
> that refers to a working tree is therefore a thing to *remove*, not to preserve.

**Goal.** The container image holds python + git + the store, and nothing else. No proxy binary, no proxy config.

**Files in scope — the work list, rewritten 2026-08-29.** The previous version of this line was a file list with
one parenthetical each, and every file held more than the parenthetical named. The review opened them; this is what
is in them.

| File | What must change |
|---|---|
| `deploy/Containerfile.store` | drop the caddy stage **and the `COPY --from=…caddy:2-alpine` binary**; drop `ENV ISIDIUM_SOCKET`; **remove the `pip install … "uvicorn>=0.30,<1"`** — 7bg.8 removed uvicorn from the design and K1 removed it from the distribution, but it is still installed directly into the image, where K5's lock cannot see it; and `WORKDIR /var/lib/isidium/tenant` assumes a working tree (see Q6) |
| `deploy/compose.yaml` | publish the TLS port (**already published**); mount the CA, the store certificate and key read-only; **replace the healthcheck** — it is `test -S /run/isidium/store.sock` and will report the container permanently unhealthy the moment the socket is gone; **drop `ISIDIUM_CLIENT`**, which points at `.isidium/client.toml` *inside the store's own clone* — client config in the server's container, and K3 is deleting the mode it belongs to |
| `deploy/entrypoint.sh` | **rewritten, not edited.** It starts caddy, waits for the socket, `chmod`s it, traps two PIDs and `wait -n`s on both, and passes `serve` **two** options. `serve` now takes **eight** with no defaults: `--tenant --repo --journal --root --registration --certificate --key --ca`. There is almost no overlap between the old invocation and the new signature. It also refuses to start unless `$TENANT_DIR/.git` exists — see Q6 |
| `deploy/README.md` | rewritten to the one shape. Its `git clone <remote> tenant` makes a **working-tree** clone and must become the bare, filtered clone K4 built — from a remote that allows the filter (a `file://` URL or a forge with `uploadpack.allowFilter`; a local *path* remote silently ignores `--filter`), with the store's git configured for **no lazy fetching** per the footprint ruling. Its certificate steps are the ones the operator will actually follow, so they carry the corrected requirements below |
| `deploy/Caddyfile` | **deleted**, with its `.gitattributes` line |

**Caddy is stale but owned; uvicorn was stale and unowned.** Every surviving caddy reference is in this list. The
uvicorn install was in nobody's list — K5's trap pointed at the two places uvicorn is *already* gone (the `[server]`
extra and the mypy override, both done by K1) while the one place it survives went unnamed for three passes. That
asymmetry is why the table above exists.

**Must not touch:** any file under `packages/`.

**What K4 hands you.** A store that holds a **bare, filtered clone with no working tree and no index**, whose git
refuses to fetch blob content outside the governed set. Three consequences for these files, and they are the whole
reason this chunk moved: the `[ ! -d "$TENANT_DIR/.git" ]` guard is **wrong** for a bare clone and must become a
bare-repository check (`git rev-parse --is-bare-repository`, or the presence of `HEAD` and `objects/`); nothing may
`cd` into a working tree that does not exist, so `WORKDIR` is a data directory rather than a checkout; and the
README's clone step and the container's git environment carry the footprint enforcement. K4's done-when 7 means a
human has already run `serve` against exactly this shape outside the suite before you start — **ask for those
commands and start from them.**

**Record citations:** the deployment record §2's setup table — S-1 … S-4 unchanged, **S-5 and S-6 rewritten**, and
**S-9** (the forge must allow partial clone; the full-bare fallback). 03b §2's edge bullet.

**K2b went first, so this is the first chunk written under C-11.** The `[telemetry]` extra exists: the README says
how to start the container **with the console exporter** so the first start is diagnosable without a collector, and
how to point it at a real one later. A wrong CA path refuses every caller silently on both sides — the spans on
stderr are how you find that in minutes instead of an afternoon.

**Done when:** the image builds under podman; a container starts and answers `GET /health` over mTLS from the host
using a client certificate the mounted CA issued; **the same start, run with the console exporter, prints the spans
for that call**; the README's steps are the ones that were actually run, in order, with nothing assumed. Record the
exact commands.

**Traps:** `deploy/*` files are `eol=lf` in `.gitattributes` — they run in Linux, keep them LF.

**The certificate trap, corrected 2026-08-29 — the previous version pointed the operator at the wrong end of the
connection.** It said the extensions are enforced by OpenSSL 3.5 and that without them *the store* refuses every
caller. All three parts were wrong. Measured on OpenSSL **3.0.21**, one variable at a time — so it is not a version
— and confirmed against the production `HttpsTransport`'s own context:

- The strictness is the **`VERIFY_X509_STRICT` flag**, and **the client sets it**: `ssl.create_default_context()`
  turns it on, which is what `httpx` builds. Clear that one flag and every case below connects.
- The **store's listener does not set it**, and enforces none of it: a caller certificate with no
  `AuthorityKeyIdentifier`, no `KeyUsage` and no `clientAuth` EKU **authenticates**.
- So the requirements land on the CA and on the store's own certificate, **for the caller's benefit**:
  **S-1 (the CA)** needs `SubjectKeyIdentifier` **and** `KeyUsage(keyCertSign)`; **S-2 (the store's certificate)**
  needs `AuthorityKeyIdentifier`, a name matching the address callers dial — a `SubjectAltName`, **or** the Common
  Name when there is no SAN, because OpenSSL falls back to it — and, if it carries an EKU at all, that EKU must
  include `serverAuth`. `KeyUsage` is not required on S-2. **S-3 (caller certificates) need none of it.**
- The symptom of getting any of it wrong is the same and says nothing: the client sees a connection that opens and
  gives nothing, and the store's handler is never invoked. Which is precisely why K2b runs first.

The deployment record's S-1 … S-3 now carry this; the README should copy it from there, not from here.

---

## K3 — Delete local mode and loopback (done 2026-08-30)

**Ruling (7bg.2):** owner, verbatim — *"yes on getting rid of loopback and local mode."* One shape, one boundary.

**Goal.** The client has exactly one transport: the pinned mTLS channel. Tests construct `Store` directly.

**Files in scope:** `client/transport.py` (delete `LocalTransport`; `Transport` is the channel), `client/config.py`
(drop `mode`, `principal`, `grant`, `journal`, `signer` and the local-mode header text), `client/cli.py` (drop
`--principal`, `--grant`, `--signer`, `--allow-loopback`, `--host`/`--socket` remnants), `client/install.py` (the
client-file template), `tests/store/test_walk.py` and `tests/store/conftest.py` (construct `Store` directly).

**Must not touch:** `server/` (K1 already gave `serve` its own construction), `gitrepo.py` (K4).

**Traps**

- `check` and the pre-commit hook are **offline by design** — they read the checkout and its installed schemas, not
  the store. Confirm they never went through `LocalTransport`; if they do, that path stays, renamed for what it is.
- `client/config.py`'s `repo` and `root` are the *checkout's* paths and are still needed by the hook and by `check`.
  Do not delete them with the local-mode fields.
- `.isidium/client.toml` is ungoverned by design (it carries the address and key paths `config.toml` may never). Its
  header comment about self-asserted local identity goes with the mode.

**Done when:** ~~no symbol named `local`, `loopback` or `hop` survives in the package~~ **[corrected 2026-08-29 —
unachievable as written, and it contradicts this chunk's own trap list. `client/hook.py` uses `pre-commit.local`,
the filename the installer chains an operator's pre-existing hook to; it has nothing to do with local mode and must
survive. The satisfiable sentence: **no local-*mode* symbol survives — `LocalTransport`, the `mode` field and its
`local` value, `--allow-loopback`, and the loopback host path.** An agent applying the old sentence literally
deletes a working mechanism; one applying it sensibly deviates from its brief in silence. Both are the failure the
chunk structure exists to prevent.]**; the acceptance walk still runs end to end (now against a
directly-constructed `Store`); the suite is green.

---

## K3b — The hook stops importing the store (C-13 for code)

**Ruling (Q10, owner, 2026-08-30):** *"b sounds like the right fit"*, framed by *"this machine is very slow and the
machines these will run on are older… let's plan for minimal power and tr to make things fast with low latency but
not sacrifice performance at runtime for paying for a seconds at build time."*

**Goal.** The pre-commit hook stops paying for the whole store. The installed hook script calls
`python -m isidium.store.client.hook`; `isidium hook` stays for a human typing it and calls the same `check()`.

**Why it is a chunk and not a trailing edit.** `cli.py`'s `hook` command already defers its own import
(`from .hook import check` inside the function body) and it buys nothing, because the module-level
`from .transport import …` twenty lines above has already pulled the store in. That is the failure this chunk exists
to make impossible rather than to patch: the hook's cost is coupled to `cli.py`'s import graph, so **every chunk
that adds to that graph makes every commit slower and nobody counts**. K3 and K4 both rewrite files in it.

**The numbers below were superseded by K3 before this chunk started, and the correction is the first thing to read**
[K3, 2026-08-30]. Deleting `LocalTransport` deleted the module-level store imports in `client/transport.py`, and
those were what pulled `cryptography` and `pydantic` into `client/cli.py`. Measured on `tools/import_cost.py`
(committed by K3), medians net of a bare interpreter re-measured in the same run: **`client.cli` 2529 ms → 741 ms**,
`client.transport` 1920 ms → 683 ms, `client.hook` 724 ms → 772 ms (the control — unchanged, as it should be).
`client.cli` now pulls **`typer` and `opentelemetry`**, not four packages. **So most of this chunk's expected win has
already landed**, and what is left of it is `typer` plus the structural half. **Re-measure before you start** rather
than trusting either set of numbers; the older ones (`isidium hook` **5.5–7.7 s per commit**, and an expectation of
~1.5–2.5 s after) were taken on a machine whose bare-interpreter floor has since been seen to move by 2x between
runs an hour apart.

**What has not changed is why this chunk exists.** The win above is real and unprotected by structure: it survives
only as long as nobody adds a module-level import to `cli.py`, which K4 and K2 both open. K3 left a guard
(`tests/store/test_walk.py::test_the_client_no_longer_drags_the_store_into_every_import`, asserting the module set
rather than a clock) — **widen that test, do not write a second one.** **The floor is declared, not hidden:** Python's own interpreter startup is ~1.3 s on this machine and the
OpenTelemetry API another ~0.5 s, reached through `core/refusal.py`, which every path needs. Going below that means
making the telemetry import lazy — which collides with C-11 and is **not this chunk's to decide** — or the Rust port
(sync record, round 67).

**Files in scope:** `client/hook.py` (a `main()` and a `__main__` guard; the `HOOK_SCRIPT` template), `client/cli.py`
(the `hook` command keeps working and keeps calling the same function), `pyproject.toml` if a second console script
is wanted, and a test asserting the two doors call one function.

**Must not touch:** `server/`, the registry, anything K3 is mid-flight on. **Run after K3**, which rewrites
`cli.py`'s transport use — doing this first means writing it twice.

**The work**

1. **`hook.py` gets a `main()`** that resolves the repo the way the CLI command does and returns `check()`'s code,
   plus `if __name__ == "__main__": raise SystemExit(main())`.
2. **`HOOK_SCRIPT` calls the module, not the CLI.** Today it prefers the `isidium` binary and falls back to
   `{python} -m isidium.store.client.cli hook`; both routes import `cli.py`. The installed script should reach
   `isidium.store.client.hook` directly. **An installed hook from before this chunk keeps working** — the old script
   still calls a command that still exists — so nothing breaks in a checkout that has not re-run `init`; say so in
   the handoff rather than assuming it.
3. **`isidium hook` stays**, calling the same `check()`. One behaviour, two doors.
4. **A test asserts the two doors are one function** — that `cli`'s command and `hook.main` reach the same
   `check`, so they cannot drift into two behaviours.
5. **A test asserts the import graph**, which is the property this chunk is actually about and the only one that
   stops it regrowing: importing `isidium.store.client.hook` in a child interpreter must leave `cryptography`,
   `pydantic` and `typer` unimported. **A timing assertion would be the defect this round keeps naming** — it
   cannot tell a fast hook from a broken one, and this machine's noise is 3x its median. Assert the module set, and
   pair it with a positive discriminator: the hook still answers correctly on a real checkout.

**Done when.** The installed hook script reaches `hook.py` without importing `cli.py`; the module-set test exists
and fails if a future edit reintroduces the coupling; `isidium hook` still works and shares one function with it;
the before/after cost is re-measured and both numbers are in the handoff; the green bar holds. **Mutation-check the
import assertion** with `tools/mutate.py` — put the eager import back and confirm the test fails.

---

## K4 — `GitCli` becomes bare and object-level; the store's registry source

**Ruling (7bg.8):** the store speaks git directly, holding a **partial bare clone** — commit graph and trees, blob
content for governed paths only. No working tree, no index, no code, no media, ever. Pinned in 03 §1.3.

> **The second half of that pin is delivered by this chunk or not at all — ruled 2026-08-29 (Q3): enforce it, and
> the pin now says so.** `--filter=blob:none` makes a clone **lazy, not restricted**: blobs are absent until
> something asks, and then git fetches them from the promisor remote, transparently and permanently. Measured — an
> ordinary `git cat-file -p` of a **non-governed** path pulled a code blob into the clone and kept it. So
> *"no code, no media, ever"* is **not** a property of the clone mode, and left alone it would rest on the
> discipline of every present and future call site, including `read(path, sha)`, whose signature accepts any path
> and which this chunk rewrites. **The store therefore runs its git with `GIT_NO_LAZY_FETCH=1`**, which turns that
> read into a refusal, and a test proves it. 03 §1.3 is reworded to state the enforcement rather than imply the
> clone mode delivers it.
>
> **Two consequences to build deliberately, not discover.** (a) A refused lazy fetch surfaces as a git failure, so
> `GitCli` must translate it into a **named refusal** rather than letting `git.failed` carry a promisor error — an
> agent that reads *"unable to load blob"* learns nothing; one that reads *"this path is outside the governed
> set"* learns everything. (b) Anything that legitimately needs content outside the governed set must **ask
> explicitly** — a separate, named call, not a flag on `read`. If you find such a caller, that is a finding for
> §4, because none is expected.

**Goal.** The `Repo` protocol is unchanged, `MemGit` is unchanged, `store.py` and `api.py` are unchanged — only
`GitCli` changes, and the defect class that started this becomes structurally impossible.

**Files in scope:** `server/gitrepo.py` (**the `GitCli` class only**), `tests/store/test_components.py` (its GitCli
fixture and tests), a new test file for the bare properties.

**Must not touch:** the `Repo` protocol, `MemGit`, `blob_id`, `store.py`, `api.py`, `journal.py`, anything in
`client/`.

**What changes inside `GitCli`**

| Method | Today | Becomes |
|---|---|---|
| construction | a clone with a working tree | `git clone --bare --filter=blob:none`; **detect filter support and fall back to a full bare clone**, and report which of the two is running (S-9) |
| `read(path, None)` | reads the working tree | reads `HEAD`'s tree |
| `read(path, sha)` | `cat-file` decoded to `str` then re-encoded | **binary** `cat-file`; the current round trip corrupts any non-UTF-8 byte — a latent bug, fix it here |
| `commit()` | write files → `add` → `commit --only` | `hash-object -w` → a temporary index (`GIT_INDEX_FILE`) → `read-tree`/`update-index` → `write-tree` → `commit-tree` → `update-ref` **with the expected old value** as the compare-and-swap |
| `push()` | on rejection, `pull --rebase` and retry | push with the expected old value; on rejection **refuse** — there is no working tree to rebase, and the store's own compare-and-swap on the document head sits upstream of this |
| `paths()` | `ls-files` (the index) | `ls-tree -r --name-only HEAD` |
| `parents`, `commit_time`, `touched`, `first_parent_walk` | already object-level | unchanged |

**The second half of this chunk — the store's registry source.** `Registry.for_checkout(<workdir>)` reads
`.isidium/schemas/` **from a working tree**, and `init` writes `.isidium/` into `.gitignore` — so under a bare clone
it would silently fall back to the toolkit's shipped schemas, quietly undoing the WP3 review's C5 (*the checkout's
installed registry is what it validates against*). The store must instead resolve each path's `schema@version` from
the **manifest in `config.toml`** — which is governed, tracked, and readable from the bare clone — against its own
installed registry, refusing `config.schema-unknown` when a named version is absent. `Registry.for_checkout` stays,
unchanged, as the **client's** offline path (`check`, the hook).

**Done when**

1. A test asserts the store's repository directory **has no working tree and no index**.
2. A test asserts that after cloning from a filter-supporting local remote, a **code** blob is absent locally while a
   **governed** blob is present. **Two traps, both measured, either of which makes this test lie:**
   (a) **`--filter` is ignored outright for local *path* clones** — `warning: --filter is ignored in local clones;
   use file:// instead.` The test must clone from a `file://` URL, and the remote must have
   `uploadpack.allowFilter` set, or it silently gets a full clone and asserts nothing.
   (b) **`git cat-file` is not a read-only probe** — it *fetches* the blob it is asked for, so a test that checks
   absence with `cat-file` makes the property false in the act of measuring it, and passes. Check absence with
   `cat-file --batch-all-objects --batch-check`.
   **And a second test, from the Q3 ruling:** with the store's own git settings, a read of a **non-governed** path
   is **refused** and the clone does not grow — measured as the shape to build, `GIT_NO_LAZY_FETCH=1` refuses and
   the repository stays byte-identical. Mutation-check it: remove the setting and the test must fail.
3. A test asserts a governed write produces exactly one commit touching exactly the written paths.
4. A test asserts that when the ref moved underneath, the push is **refused**, not silently rebased.
5. A test asserts the store validates against the manifest's named version, and refuses when it is not installed.
6. **Reads are batched, and a test or a measurement says so.** `store.py` loops over every governed path calling
   `repo.read(...)`; today that is a working-tree file read, and this chunk turns it into `git cat-file` — which
   `GitCli` runs as **one subprocess per call**. That converts N cheap reads into N process spawns on the load path.
   Measured 2026-08-29 on this workstation: 319 ms per spawn against 315 ms for **one** `git cat-file --batch` run
   covering all 40 blobs — the ratio is essentially the file count, and it is the file count on any machine; only
   the constant changes (the container's spawn cost will be nearer 5–10 ms, so ~1–2 s for 200 files instead of ~64 s
   here, and still one spawn instead of 200). **`git cat-file --batch` over one long-lived process is the shape.**
   This is the standing efficiency rule landing on the chunk that touches it, before the first slow run rather than
   after (C-8).
7. **`serve` has been run once against a real bare clone, outside the test suite**, and the commands are in the
   handoff — ruled with Q6, 2026-08-29. K2 comes after this chunk and its container's first start should debut
   only the container; the git path must have been exercised on a real repository, not only in pytest. A `GET
   /health` and one read verb over the real socket is enough. If it does not work outside pytest, that is the
   finding this item exists to surface.
8. The full suite is green.

**Note for whoever assigns this:** this is the chunk that most rewards a stronger model. Git plumbing and
compare-and-swap semantics are where a plausible-looking implementation is silently wrong.

---

## K5 — Dependency determinism

**Ruling (7bg.5):** owner, verbatim — *"be sure to include a deterministic way of tracking all dependencies and
monitoring with CI for upstream updates."*

**Goal.** Every dependency is pinned by hash, the pin is checked in CI, upstream advisories are seen, and upstream
updates arrive as reviewable PRs.

**In scope:** install `uv` on the workstation (it is not installed); `uv.lock` with hashes; `uv sync --locked` in CI
so a stale lock fails; an **OSV scan of the lock** in CI; **Renovate** (forge-agnostic — it runs on GitHub and on
Forgejo) for upstream update PRs; container base images pinned **by digest**; the same for every distribution in the
namespace.

**Traps:** ~~the `[server]` extra becomes **`h11`** — uvicorn and hypercorn come out of the extra *and* out of
`pyproject.toml`'s mypy override block. h11 must be ≥ 0.16.~~ **[All three were already done by K1 and this section
was not updated — verified 2026-08-29: `server = ["h11>=0.16,<1"]`, the only mypy override module is `h11.*`, h11
0.16.0 installed. Worse than harmless: it sends this chunk's agent looking for uvicorn in the two places it is
already gone, which is the one place the *surviving* uvicorn install would naturally have been caught. It is in the
container image, and it is **K2's** (see K2's file table).]** The h11 floor claim itself **is** verified: the
CVE-2025-43859 advisory states that exploitation requires the combination of h11 with a buggy proxy or parser, and
that it is fixed in 0.16.0 — so the floor is right and the reason given for it is right. CI here is the belt only: hosted
runners cannot reach a homelab store, so forge CI enforces *no governed-path diff off `main`* — a pure diff check —
and journal reconciliation stays ingest's, on the factory side (7bg.6).

**Done when:** a fresh checkout installs from the lock with hashes; CI fails on a stale lock; the OSV job runs and
reports; Renovate's config is checked in; every image reference is a digest.

---

## K6 — H-1: caller identity in the journal row

**Goal.** The four things the deployment record §1 says must be right *now* because they cannot be backfilled: the
**certificate fingerprint** in the journal row beside the principal; the certificate's **validity window** checked by
the store; **full-subject** matching, never a bare common name; the registration read from a **file the store
re-reads**, so revoking is an edit rather than a rebuild.

**Ruled by the owner 2026-08-27 (7bg.10) — the question is closed, do not re-ask it.** The journal row's shape is a
registry schema (03b §2), so adding the fingerprint field is a schema version change, and *a schema change is policy*
(03b §4). Owner: **yes on the policy act** — the journal schema bump rides the normal `config-policy` act, signed into
the policy chain like any other change to `config.toml`. It is cheapest now because no real journal rows exist yet.
Build it that way: bump the journal document type's registry schema version, carry the change as a signed
`config-policy` act, and record the version the row was written under.

**Trap:** K2b lands first, so the journal row joins telemetry on **trace context** — do not invent a correlation
id, and do not put a trace id inside the row's hashed content (C-9; it sits beside it, where `sig` does).

**Trap:** the validity-window check must not be skipped on the grounds that TLS already did it — after K1 it *is* the
same connection, but the check is what makes the seam portable to the realm provider later.

**Trap — now closed ahead of you, and this is where the value moved** [2026-08-29, K1b-ii].
`Registration.fingerprint` **no longer exists**: it parsed the DER it was given and re-serialised it back to DER
before hashing, which was a full X.509 parse per call for nothing and defined the fingerprint as *the hash of our
re-encoding* rather than *the hash of the bytes the peer presented* — normally identical, which is exactly what
would have made a divergence a bad day. It had no callers, so it was deleted rather than left beside a correct
one. **Use `Credential.fingerprint`** (`server/service.py`): SHA-256 over the presented bytes, resolved once per
connection at the edge and carried, so the journal row costs no parse at all.

---

## K4b — The author's terminal checks a ref's sub-file locus

**Descends from Q11 (ruled 2026-08-31), and exists because that ruling left a residue rather than a hole.** Read
**Q11 in §5 before this section** — it carries why the store no longer looks inside a blob, and you must not
"fix" that on the way past.

**The gap, precisely.** A ref whose line range, anchor or symbol **never** resolved is caught at dispatch by
T-B3's assembler and nowhere earlier. On a card that is never dispatched — a spike, a `surfaces = []` task, one
held indefinitely — it is never caught at all. Nothing downstream consumes it, so this is **specification
quality, not integrity**: the system is fail-closed without this chunk. Rank it accordingly.

**Goal.** The author learns at their own terminal, while they are looking at it, instead of an operator learning
at the moment they wanted work to start. `write` and `ratify` are typed **in the tenant checkout**, which has the
working tree with the code in it — the one place the answer is free.

**The one thing that must not happen: a second implementation.** The check is already a pure function over
`(ref, bytes)` — `server/refs.py`'s `_check`, with `Ref.parse` beside it, no I/O and no store. **One
implementation, two callers:** advice at the terminal, the gate at dispatch. This is the shape the record already
uses for the pre-commit hook and CI (*"the same bytes either way, so a local check and the store's check cannot
disagree"*), and two copies of a resolution rule is exactly how they drift apart.

**Files in scope:** `client/` (the door — decide whether this is `write`/`ratify` pre-flight, `check`, or both),
and **a move**: `Ref.parse` and `_check` are pure and both sides now need them, so they want to live under `core/`
rather than `server/`, with `server/refs.py` keeping `resolve` (which is the I/O half). Tests for whichever door
you choose.

**Must not touch:** `server/store.py`'s `_resolve_refs` and what the store checks — that is Q11's ruling, not a
defect. The `Repo` protocol. `GitCli`. The disclosure table's `ref` row (`ref` is already a full-disclosure
validation namespace, so a refusal here needs no new classification).

**Traps, found while ruling Q11 rather than while building this:**

1. **`check` is a pass-through.** `client/cli.py`'s `check` calls the store over the channel and renders the
   answer; it validates nothing locally today. So there is **no client-side ref checking at all** and this is
   additive — but it also means `check` is not automatically the right door: it currently needs a reachable store,
   and the value of this chunk is feedback **before** the call.
2. **The working tree is not `HEAD`.** The author's file may be dirty. Say which one you check against and why;
   the store's recorded blob id comes from `HEAD`, so a check against a dirty tree can pass while the ratified
   `refs_resolved` names different bytes. Neither answer is obviously right — decide it and write the reason.
3. **C-13 reaches this door** (and it is the door K3b just made expensive). Whatever you add to `client/hook.py`'s
   or `client/cli.py`'s import graph is paid on every commit or every command. `tests/store/test_walk.py`'s import
   guard asserts the module set and **will fail you** — widen it, do not write a second one.
4. **Refs may point at the legacy archive**, which is frozen and can be large. A local check reads those bytes;
   that is fine at a terminal and would not have been fine in the store.

**Done when**

1. A ref whose symbol/anchor/line range does not resolve is refused **locally**, before the store is called, with
   the existing `ref.*` rule ids and no new ones.
2. A test proves the local door and the assembler's rule are **one function** — by substitution, not by reading
   the source. K3b's `test_the_installed_hook_and_the_typed_command_are_one_function` is the worked example: a
   re-implementation passes every behavioural assertion and fails only that one.
3. The import guard still holds, widened rather than duplicated.
4. Mutation-checked with `tools/mutate.py`, spec committed beside `tools/mutations/k3b.toml`.
5. The full suite is green, `mypy --strict` clean over `packages/`, `ruff` clean.

---
## K7 — Adversarial review round on the reshaped store

The standing practice after every work package: one fresh refuter, security/trust-boundary + conformance +
efficiency, report under `review-artifacts/`, then an apply pass. The store's edge and its git mechanism are both new
in WP4; neither has been reviewed by anyone.

---

## 3. Deliberately not in WP4

- The **tenant dev container** (the thin client and the in-session tool guard) — named as the open gap in the
  2026-08-27 handoff; it is not built and WP4 does not build it.
- The **forge driver seam** (T-C7) — the factory's contract, not the store's.
- `land` / `accept` and the runners — WP5; the surface already names them (`api.not-yet`).
- Leaf-certificate pinning beyond the CA, and certificate **revocation** — declared open; today neither shape checks
  it (deployment record §1, column B).
- The identity **provider seam** (local file → SPIFFE → OIDC → LDAP → SCIM) — recorded as the G7-consumer shape.

## 4. Handoffs and findings

> One line per chunk as it completes: what landed, what was declared, what the next agent needs. Findings that are
> not this chunk's work go here too, so nothing is discovered twice.

### K2 — done (2026-09-01). One process, a clone that is rebuilt rather than kept, and a container that was actually run.

**Every done-when item landed, and the container stopped being a document.** The image builds under podman 5.8.3;
a container starts, clones, and answers `GET /health` over mTLS from the host with a certificate the mounted CA
issued; the same start prints the spans for that call on stderr; and the README's steps are the ones that were
run, in order, in a torn-down clean room — `podman volume rm`, fresh certificates, fresh origin, fresh checkout.
Beyond the done-when, the whole channel was driven through it: `isidium init` opened the tenant's policy chain
**over the connection**, the store signed the first entry with the mounted key, committed `docs/work/config.toml`
and pushed it to the origin, and `show board` came back. 206 tests, `mypy --strict` clean over `packages/`, `ruff
check` and `ruff format --check` clean.

**The shape: one process.** Caddy is deleted, and with it the Unix socket, the `X-Verified-Client-Cert` hop, the
socket `chmod`, the two trapped PIDs and the `wait -n`. `entrypoint.sh` checks, clones, and `exec`s, so the store
is PID 1 and `podman stop` reaches it directly. `serve` is given its **ten** arguments where it used to get two.

**Two defects in the image that nobody's list had.** The brief caught the `uvicorn>=0.30,<1` install — a version
constraint in a Containerfile where K5's lock cannot see it, for a dependency 7bg.8 removed from the design and K1
removed from the distribution. What it did not catch is that the same line installed the wheel with **no extras at
all**, so `h11` was absent and **this image could never have run `serve`**: the first `import h11` in
`server/http.py` would have ended the container. It installs `[server,telemetry]` now. The second defect is
outside `deploy/` entirely: **there was no `.gitignore` line for anything the README tells an operator to create.**
Following it produced a CA private key, three leaf keys, the store's signing key and the registration inside a
tracked working tree, one `git add -A` away from being committed. Both are recorded here rather than fixed in
silence.

**The clone is rebuilt at every start, and that is this chunk's one design decision.** K4 recorded that a running
store never re-reads `main`, so a bypass commit is *"invisible to a long-lived store until it restarts"* — and
that sentence is only true if a restart re-reads the branch. A clone kept on a persistent volume would have gone
on serving whatever branch it last saw, and would have quietly falsified it. So `ISIDIUM_REPO_DIR` lives in the
container's own writable layer, nothing mounts it, and the entrypoint rebuilds it from `ISIDIUM_ORIGIN` each
start. **Verified, not reasoned:** a commit pushed straight to the origin left the running store's clone at
`32217bd`; after `podman restart` it was at `6b6f3ba`, the planted commit. **The cost is written at the site**
(C-8): a fresh clone is cold and holds no governed blob either, so the first load hydrates the governed set one
object at a time — N round trips to the origin at every start, paid at start-up rather than on a call path. That
is K4's recorded batching finding, now with a second caller and a second reason.

**`GitCli.clone` is called, never reimplemented** — one `python3` heredoc that clones *and* reports the footprint,
because it has the object in hand and a second start-up interpreter to ask the same question again would be the
wasteful shape. It also means `--filter` cannot be silently dropped on a path source (S-9's second trap). The
footprint line is the first thing the store prints.

**The healthcheck stopped being a lie.** It was `test -S /run/isidium/store.sock` — after 7bg.8 that socket does
not exist, so the container would have been reported permanently unhealthy forever; and even before, a socket file
said a process had opened a path, not that the store answers. It is now `deploy/healthcheck.py`: `GET /health` over
mTLS to the real listener, asserting `{"ok": true}` rather than merely that something came back. **stdlib only, and
no isidium import** — `ssl` + `http.client`, because importing the client half would pay ~0.7 s of `typer`,
`pydantic` and `cryptography` every 30 seconds for nothing this needs (K3/K3b measured that import). Its
certificate is CA-issued and deliberately absent from the registration: **a probe is not a principal** (S-4).

**The failure a first start will actually meet, and it is not TLS.** A store with no `--signer` cannot open the
policy chain: `init` comes back `init.no-ratifier: identity is disabled and no ratifier key is pinned`, from a
container that is otherwise entirely healthy — and nothing in `deploy/` had a signing key at all. `openssl genpkey
-algorithm ed25519` produces exactly what `SoftwareKey.load` accepts (verified), and it is mounted on its own,
beside the TLS material rather than inside it, so it reads as what it is.

**Six mutations, six died — run live against the container, because `tools/mutate.py` cannot see this chunk.**
Every assertion K2 writes lives in a shell script, a YAML healthcheck or a Containerfile; the suite covers none of
them, so a TOML spec here would have killed nothing and **reported success**, which is precisely the failure the
mutation rule exists to prevent. They were run instead by breaking the property in the running container and
observing the check.

| # | mutation | what happened |
|---|---|---|
| D0 | none — the healthcheck, unmutated | exit 0 |
| D1 | the healthcheck's certificate taken away (`ISIDIUM_TLS_DIR=/tmp`) | exit 1 — it is really doing mTLS, not merely connecting |
| D2 | `/health` → a target the store routes elsewhere | exit 1, printing the store's own `{"rule": "service.route"}` — the discriminator is the *answer*, not the arrival |
| D3 | a non-bare directory bind-mounted at `ISIDIUM_REPO_DIR` | refused by name, and **the directory was intact afterwards** — the rebuild never `rm -rf`s something it did not make |
| D4 | each required decision removed in turn (`TENANT`, `ISIDIUM_ORIGIN`, the registration) | three distinct named refusals, exit 2 |
| D5 | `uploadpack.allowFilter=false` on the origin | the start-up line changed to `footprint=full`, and back to `filtered` when restored — S-9's degradation is **counted**, not claimed |

**What this chunk did not do, and what a reader must not assume from it.**

- **`podman compose up --build` was not exercised.** podman-compose 1.6.0 against podman's Windows client fails
  with `no Containerfile or Dockerfile specified or found in context directory` — identically when the
  Containerfile is named by an absolute path, so it is the tool and not `compose.yaml`, whose `build:` block is
  spec-correct. The image was built with `podman build` and compose ran everything else. **`docker compose` is
  written down and unexercised.**
- **The origin was a bare repository mounted into the container over `file://`, not a forge over ssh or https.**
  The clone, the filter, the degradation, the push and the hydration are all real; **forge authentication and the
  egress allowlist are not tested at all**, and a real remote is the one thing standing between this and a live
  tenant.
- **The store's own start-up does not report the footprint — the entrypoint does**, because `serve` is under
  `packages/`, which this chunk's brief forbids touching. A `serve` started by hand therefore reports nothing.
  That is a seam, and it is named here rather than left to be found.
- **`deploy/healthcheck.py` is a file the brief's list did not name**, and `.gitignore` is outside `deploy/`
  entirely. Both are recorded as widenings under §0 rule 2. The alternative to the first was a twelve-line python
  program inside a YAML string.
- **No `packages/` file was touched**, so the 206 tests and the type check are K4's, unchanged. **This chunk adds
  no test to the suite** — the honest consequence of its subject matter, and the reason the mutation table above
  is live rather than scripted.
- **The sync record is still untouched** and still owes **three** lines — 7bg.2, 7bh.2 and Q11. Unchanged by this
  chunk; it is the owner's line to author.

**Findings with no owning chunk.** All of K4's carried forward unchanged, including its three. **Two are new:**
(i) `serve` cannot report its own footprint and nothing outside a container does it, so the one deployment fact
S-9 requires be surfaced is surfaced by a shell script; (ii) the healthcheck's probe certificate is issued by the
tenant CA, so that CA now mints two *kinds* of credential — a registered caller's and an unregistered probe's —
distinguished only by whether the registration names the subject, which makes S-3's *"treat the tenant CA as
single-purpose"* carry more weight than it looks like it carries.

### K4 — done (2026-08-31). The store speaks git as objects, and the footprint stopped being a claim.

**All eight done-when items landed.** `GitCli` holds a partial bare clone — no working tree, no index — and
builds every write from plumbing (`hash-object` → a temporary index → `write-tree` → `commit-tree` →
`update-ref` with the expected old value). A rejected push is a refusal, not a rebase and a retry. Reads go
through **one long-lived `cat-file --batch` process**: measured here, 40 reads of a bare clone, medians of 5,
**13129 ms one-spawn-per-read (328 ms each) against 593 ms batched (14.8 ms each) — 22x**, and the ratio is the
file count on any machine. `serve` was run against a real bare clone **outside pytest** (done-when 7, ruled with
Q6): `GET /health` → 200, `POST /call/show` → 200, footprint `filtered`. **206 tests** (193 before),
`mypy --strict` clean over `packages/` (39 files), `ruff` clean.

**The footprint is enforced, not implied** [Q3]. Every git this class runs carries `GIT_NO_LAZY_FETCH=1`; a read
outside the tracking root is refused **before any subprocess starts**, so the object store cannot grow by the act
of asking, and a test asserts the byte-identical object set rather than only the refusal. `git.outside-footprint`
is the named refusal Q3's consequence (a) asked for — terse, because the `git` namespace is, so the rule id
carries the whole meaning.

**Two things the brief did not anticipate, and the second is load-bearing.** `git write-tree` verifies that every
object in the index exists, which is exactly the check a partial clone is built to fail — the first governed
write died with `could not fetch <oid> from promisor remote`, the enforcement refusing the store's own commit;
`--missing-ok` is the answer, safe *here* only because every id in that tree came from `ls-tree` or from a
`hash-object` just checked against `blob_id`. And **a filtered clone holds no *governed* blob either** — found by
the planted-file test, not by reading. A restarted store could not read its own `config.toml`, nor a bypass
commit somebody pushed to `main`, which is what `check` exists to detect. Git has no filter meaning *"blobs under
this path"*, and the governed set is declared by a manifest **inside** the repository, so it cannot be named at
clone time. Content is therefore hydrated on demand through one named door, and the **tracking root** is the
boundary that decides who gets one — the design's own boundary, since `refs` are refused inside the root and a
`surfaces` glob that reaches it is refused too.

**The second half — the store's registry source — landed in `client/cli.py`, which the brief's *must not touch*
list forbids.** The line already carried a comment from an earlier chunk saying K4 would reshape it, and there is
nowhere else it can live: the registry is constructed by `serve` and passed in. `server/store.py` had to change
too, at `_resolve_refs`, for Q11. Both are recorded here rather than widened in silence, per §0 rule 2 — and the
`Repo` protocol gained `oid_of`, which the same list forbids, because Q11 makes the blob id the only thing the
store may ask about a path outside the governed set and `read` cannot answer it under a footprint holding no such
content.

**Q11 was raised and ruled inside this chunk** (§5). The brief predicted a caller needing content outside the
governed set and said *"none is expected"*; there is exactly one, `refs` resolution, and the contradiction is
inside a single ratified sentence of 03b §2. The owner ruled the same day. The store now resolves a ref from the
**tree** — path, blob id, outside-root — and the line/anchor/symbol locus is T-B3's assembler's, at dispatch,
which already refuses on it mechanically. `refs_mod.locus_check` is that one function, kept and tested, with no
second implementation. **K4b** is the residue: the same check at the author's terminal, so a never-dispatched
card does not keep a pointer nobody ever validates.

**What this chunk did not do.** `deploy/` still never run, and three files there are now known-wrong — K2's, and
the reason Q6 put K2 after this. `server/store.py` otherwise untouched. **The store does not re-read `main` while
it runs**, so a bypass commit is invisible to a long-lived store until it restarts. **Hydration is one fetch per
object**, declared at the site (C-10); batching needs the governed set before the first read, which is
`store.py`'s to give. **`serve`'s own store construction has no test** — the tests construct `Store` directly, as
7bg.2 says they should, so a mutation in that line would survive. No status was re-priced. `mypy --strict` over
`tests/` is still 46 pre-existing errors. The sync record is untouched and now owes **three** lines: 7bg.2, 7bh.2
and **Q11**, which the owner ruled in session and which is recorded only here.

**Findings with no owning chunk.** Carried forward unchanged. **Three are new, all this chunk's:** (i) a
long-lived store never picks up a commit it did not write, so `check`'s bypass detection depends on a restart;
(ii) hydration is per object rather than batched, and the seam is between `store.py` and `GitCli`; (iii) `serve`'s
store construction — including which registry it passes — is untested, which is the one place this chunk's second
half could regress in silence.

### K3b — done (2026-08-31). The hook's own door, and the guard that now reads the door's own name.

**All five done-when items landed.** `client/hook.py` has a `main()` and a `__main__` guard; `HOOK_SCRIPT` runs
`{python} -m isidium.store.client.hook` and nothing else — the `command -v isidium` arm is gone along with the CLI
fallback, because that arm was the one that made a commit import `cli.py`. `isidium hook` still works and reaches
the same `check()`. **193 tests** (191 before), `mypy --strict` clean over `packages/` (39 files), `ruff check` and
`ruff format --check` clean. **7 mutations run; 7 died**, first pass, no survivors and no equivalent mutants.

**No second console script, and that is a decision rather than an omission.** The brief left it open
(*"`pyproject.toml` if a second console script is wanted"*). It is not wanted: the installed script writes the
interpreter out **absolute** — `shlex.quote(sys.executable)` at `init` time — so it needs no PATH lookup, and a
console script would reintroduce exactly the resolution the removed arm performed, in which an `isidium-hook`
earlier on PATH answers for a checkout it was not installed by. 7bh.2's own words are *one behaviour, two doors*;
a third door that resolves differently is not that shape.

**The measurement, and the two levels are not the same number.** The brief asked for a re-measure before starting
and both numbers in the handoff. `tools/import_cost.py` (medians net of a bare interpreter re-measured interleaved)
reads `client.cli` **792 ms** against `client.hook`'s **543 ms** — K3's run of the same harness read 741 and 772,
so the machine moved further between two runs than the door is worth, and only the module set survives that. But an
import is not a commit, so the door was also measured **as a commit meets it**: the two real command lines, in a
real checkout with nothing staged, interleaved with a bare interpreter, 15 runs each, twice.

| door | run 1 (net) | run 2 (net) |
|---|---|---|
| `python -m isidium.store.client.cli hook` — the old one | 1684 ms | 1701 ms |
| `python -m isidium.store.client.hook` — the new one | **1258 ms** | **1122 ms** |

**~0.4–0.6 s off every commit.** The old door's two runs agree to within 1%, which is what says the difference is a
door and not a lucky spawn; the new door's disagree by 136 ms, which is the noise this machine has and the reason
no test asserts a clock. **The floor is declared, not hidden:** ~1.1 s of what remains is Python's own start-up
plus the OpenTelemetry API, reached through `core/refusal.py`, which every path needs (C-11). Below that is 7bh.3.

**The guard reads the door's own name, and that is the part worth copying.** K3's test named
`isidium.store.client.hook` as a literal. Such a test keeps passing after a later edit points the installed script
back at `cli.py`: it asserts that a clean module *exists*, not that the hook *runs* it.
`_hook_module_the_installed_script_runs()` now parses the rendered `HOOK_SCRIPT` — one `exec` line, an absolute
interpreter, `-m`, one module — and hands that module to the probe, so the guard and the door cannot drift. The
probe's set gained **`typer`** and **`isidium.store.client.cli` itself**, because the property is not *"the hook's
dependencies are light"*: a future `cli.py` importing nothing at all would still be a module the hook has no use
for. `client.cli` is the positive discriminator for `typer` the way `server.api` already was for the store's two.

**A property nothing had asserted: the exit code of the process git actually runs.** The in-process test holds the
two doors to one function; it cannot see a `__main__` guard that drops `main()`'s return value, and every
in-process assertion would still pass while every commit sailed through.
`test_the_installed_door_answers_the_commit_from_its_own_module` runs `-m` on the module the script names, in a
real checkout, and asserts **both** codes — 0 with nothing staged, 1 with a governed path staged — because a hook
that refuses everything and one that refuses nothing are equally broken, and only the pair tells them apart.

| # | mutation | died to |
|---|---|---|
| M1 | the installed script runs the CLI again — every commit pays for `cli.py`'s graph | `test_walk.py::test_install_is_idempotent_and_chains_an_existing_hook`, `::test_the_client_no_longer_drags_the_store_into_every_import`, `::test_the_installed_door_answers_the_commit_from_its_own_module` |
| M2 | the `isidium`-on-PATH arm comes back, preferred over the module | `test_walk.py::test_the_client_no_longer_drags_the_store_into_every_import`, `::test_the_installed_door_answers_the_commit_from_its_own_module` |
| M3 | `hook.py` imports the CLI at module scope — the coupling this chunk makes impossible | `test_walk.py::test_the_client_no_longer_drags_the_store_into_every_import` |
| M4 | `main()` answers for a different repo than the CLI door does | `test_channel.py::test_the_walk_runs_over_the_channel`, `test_walk.py::test_the_installed_door_answers_the_commit_from_its_own_module`, `::test_the_installed_hook_and_the_typed_command_are_one_function` |
| M5 | `main()` drops `check`'s code — the hook runs and every commit passes | the same three |
| M6 | the two doors stop being one function — `isidium hook` grows its own copy of the check | `test_walk.py::test_the_installed_hook_and_the_typed_command_are_one_function` |
| M7 | the `__main__` guard drops the exit code — `main()` is right and the commit sails through | `test_channel.py::test_the_walk_runs_over_the_channel`, `test_walk.py::test_the_installed_door_answers_the_commit_from_its_own_module` |

**M3 and M6 are the two worth reading.** Each dies to exactly one test, and in both cases it is a property nothing
else in the suite can see: that the hook's module graph stays clean, and that the two doors are one *function*
rather than two implementations that happen to agree today. M6 is why the one-function test asserts by
**substitution** — it replaces `hook.check` and requires *both* doors to change — rather than by reading the
source: a re-implementation of `check` behind `isidium hook` passes every behavioural assertion and fails only that
one.

**What the mutations found that this chunk did not plan for.** M4, M5 and M7 were each killed by
`test_channel.py::test_the_walk_runs_over_the_channel` as well. K3 wrote that walk to run a **real `git commit`** in
a real checkout with `isidium` deliberately off PATH, so it has been executing the installed hook script through
`sh` all along. That is the strongest evidence this chunk has that the new `exec` line works in the configuration
that ships — and it was already there, found by asking why those three mutations died rather than assuming the
attribution was noise.

**One correction to this document, in §2.** Three sentences in the paragraph under the chunk table still said Q10
was open and waiting on the owner — two of them in the same paragraph, contradicting each other — five days after
§5 recorded the ruling this chunk implements. Corrected here. A chunk reading §2 for its status would have handed
the owner a question they had already answered, which is §0 rule 5's failure wearing its other face.

**What this chunk did not do.** `server/` untouched. `deploy/` still never run, no container runtime invoked; K2
owns it, and nothing there names the hook script. **`pyproject.toml` untouched** — see the console-script decision
above. **An installed hook from before this chunk keeps working**, checked rather than assumed: the old script's
`exec {python} -m isidium.store.client.cli hook` calls a command that still exists and still reaches the same
`check()`, so a checkout that has not re-run `init` refuses exactly the same commits — it simply keeps paying the
~0.5 s. Nothing forces a re-`init`; the win arrives when one happens. **The sync record is untouched** and 7bh.2
still reads *"[owner-ratified]; scheduled as K3b [proposed position]"* — marking a ruling applied in the canonical
record is the owner's line to author, and no chunk in this plan has written to that file. **`mypy --strict` over
`tests/` is still 46 pre-existing errors.** No status was re-priced. **The hook still emits no span**, which is
deliberate and not new: `telemetry.configure()` is called only by `serve`, the CLI door prints `str(r)` unfiltered
by design (K2b's own closing line), and a span in a process with no SDK configured reaches nothing. The client half
of C-11 is larger than this chunk; it is not raised as a finding because K2b settled the CLI door on the same
reasoning and the hook is the same kind of door.

**Findings with no owning chunk.** Carried forward unchanged, none of them touched here: the store-root /
client-root disagreement that nothing refuses (K3, and it is the one with a named fix, in `Store.init`);
`client/transport.py` invents `service.error` for a client-side condition; `Transport` builds its SSL context with
the `verify=<str>` form httpx deprecates; the authorization boundary sits in two layers; the ratify dry run's
`verdicts` map is `list[str]` of rendered refusals and is keyed by string over the wire and by `int` in process;
`config@1` is written in two places; the four mispriced statuses; the order-dependent tests in `test_scenarios.py`
under bare `-n 8`. **Nothing new was found** — worth recording after three consecutive chunks that each added to
this list. The files in scope were two, and both had been read closely by the two chunks immediately before.

### K3 — done (2026-08-30). One transport, a client file that names nobody, and most of K3b's win arriving early.

**All the done-when items landed, against the corrected sentence.** No local-*mode* symbol survives: `LocalTransport`,
the `mode` field and its `"local"` value, the `Transport` protocol it existed to satisfy, `open_transport` and the
`client.mode` refusal are gone. `client/transport.py` holds one class, `Transport`, and it is the channel.
`client/config.py` no longer carries `mode`, `principal`, `grant`, `journal`, `signer` or `repo`. `install.init` runs
over the channel. The acceptance walk still runs end to end — **over the channel**, not against a directly-constructed
`Store`, for the reason below. `client/hook.py`'s `pre-commit.local` is untouched, which is what the corrected
sentence exists to protect. **191 tests** (186 before), `mypy --strict` clean over `packages/` (39 files),
`ruff check` and `ruff format --check` clean. **10 mutations run; 10 died** — nine on the first pass, and M4 only
after its first form turned out to be an equivalent mutant rather than a coverage gap (below).

**The walk runs over the channel rather than against a `Store`, and that is more than the ruling asked for.** 7bg.2
says *"tests construct `Store` directly"*, and `test_wp3_apply.py`'s S3, S4 and S6 now do — they are about what
the store does and used `open_transport` only to reach one. The walk is different: its whole stated purpose is
*"what the bridge session will type is what is tested"*, and after this chunk what the bridge session types crosses mTLS. So
`tests/store/test_channel.py` runs a real listener in a thread, drives it with the real `Transport`, and the caller
is the certificate on the connection. **No test had ever constructed a `Transport`** — `refusal_from` is a pure
function in the same module and K1b-iii covers it, but the class itself was untouched on either side of `init`,
which is exactly why the defect below could sit there through two chunks. The certificate machinery is imported
from `test_edge.py` rather than copied.

**The defect this chunk found and fixed.** `install.init` had two arms. The local one passed `root=chosen_root` into
`Store.init`; the https one passed `dict(store_args)` and **dropped it**. So an operator running `isidium init --root
work/` over the channel got a governed `config.toml` that named no root, and a `.isidium/client.toml` that named
`work/` — the hook and the store disagreeing about which paths are governed, which is the disagreement 03b §4 exists
to forbid. It was invisible because no test drove the https arm. Both halves are now asserted on the channel: the
chosen root reaches the governed file, and a root the operator did *not* choose does not.

**The seam this chunk opened and could not close — the one thing to hand to K4 or K2.** The store's tracking root is
set when the store is built (`serve --root`) and decides where `config.toml` is written; the `root` `Store.init`
records is whatever the caller sent. **Local mode made them agree by construction** — `LocalTransport` built the
store out of the client file — and the https arm made the question unreachable by never sending `root` at all. With
the defect fixed, they are two independently-set values that must agree and **nothing refuses a disagreement**: a
client asking for `work/` against a store serving `docs/work/` gets its file written at the store's root and its own
root recorded inside it. The refusal belongs in `Store.init` (*if `root` is not `self.root`, refuse*), which is
`server/`, which this chunk must not touch. Named, not worked around.

**The unplanned result, and it is the largest number this plan has moved.** `client/transport.py`'s module-level
`Store`, `Api`, `GitCli`, `Journal` and `Signer` imports went with `LocalTransport`, and those were what pulled
`cryptography.x509` and the generated pydantic models into **`client/cli.py`** — the module the installed pre-commit
hook runs on every commit to answer a question that needs one TOML file and `git diff --cached`. Measured on
`tools/import_cost.py` (committed with this chunk), medians net of a bare interpreter re-measured interleaved:

| module | before | after | pulls, before → after |
|---|---|---|---|
| `client.cli` | 2529 ms | **741 ms** | cryptography, pydantic, typer, opentelemetry → **typer, opentelemetry** |
| `client.transport` | 1920 ms | **683 ms** | cryptography, pydantic, opentelemetry → **opentelemetry** |
| `client.hook` — the control | 724 ms | 772 ms | opentelemetry → opentelemetry (unchanged, as it should be) |

**That is most of K3b's expected win, arriving from a chunk whose brief never mentions it**, and K3b's measured
paragraph has been corrected in place rather than left to mislead. K3 also left the guard, in
`test_walk.py::test_the_client_no_longer_drags_the_store_into_every_import`: the win is real, it is unprotected by
structure, and both K4 and K2 open `cli.py`'s import graph. **K3b widens that test rather than writing a second
one.** It asserts the **module set** of a child interpreter and not a clock, because this machine's per-run spread
is wider than the effect on any single row — a timing assertion could not tell a fast import from a broken one, and
it is paired with a positive control (`server.api`, which does pull both, so an empty answer means absent rather
than "the probe stopped working").

**The other property nothing had ever asserted: the client half of the pin.** 03 §1.3 has two claims — the store
verifies the caller's certificate against the registration's CA (proved over a socket by K1) and the client verifies
the **store's** against the same CA. Only the first had a test. Local mode is why that was easy to leave: the
transport that mattered had no TLS in it. `test_channel.py::test_the_client_pins_the_store_to_the_registrations_authority`
now runs the same call over the same socket twice, succeeding with the pinned CA and failing with another, so it
cannot pass because the store was down or the request was never made.

**Three claims in the brief did not survive checking**, and the first is the one worth reading.

1. *"`repo` and `root` … are still needed by the hook and by `check`. Do not delete them with the local-mode
   fields."* **True of `root`, false of `repo`.** `root` is read by `hook.governed_paths`; `repo`'s only reader in
   `packages/` was `LocalTransport`. `render` writes it into every client file and `load` refuses unknown keys, so
   keeping it would leave a key in every checkout that nothing consults and the loader still insists on knowing. It
   is deleted — the one place this chunk deviated from an explicit instruction — and the deviation is recorded here
   rather than taken in silence. **A well-aimed trap with a wrong reason is the more dangerous shape:** an agent
   taking it on trust keeps a dead field and never learns why.
2. *"drop `--allow-loopback`, `--host`/`--socket` remnants."* **None existed.** `grep -rn loopback packages/`
   returns nothing and returned nothing before this chunk — K1 removed the trusted-hop shape when it gave the store
   its own TLS termination. Half of what this chunk's title names had already been carried out elsewhere; only the
   file list still said otherwise.
3. *"Files in scope: … `test_walk.py` and `conftest.py`."* **`test_wp3_apply.py` and `client/mcp.py` had to change
   too** — three of that file's tests reached the store through `open_transport`, at four call sites, and `mcp.py`
   called it in `main`.

**And one of this chunk's own measurements did not survive its own re-run.** The first before/after used **min of
7** and reported `client.hook` — a module this chunk does not touch — getting *slower*, 528 → 1178 ms net. At 15
repetitions the same control reads 724 → 772 ms. A run is one process spawn and a lucky spawn is as far from the
truth as an unlucky one; K1d's *"the minimum is the least contaminated estimate"* is right about an in-process
microbenchmark and wrong here. `tools/import_cost.py` carries the correction, prints both statistics, and
re-measures the bare interpreter interleaved with every repetition — because between two runs an hour apart in this
session the bare floor itself moved by 2x, which is more than the effect.

| # | mutation | died to |
|---|---|---|
| M1 | the client file carries an identity again -- `grant`, self-asserted, back in the dataclass | `test_walk.py::test_the_client_file_no_longer_carries_an_identity` |
| M2 | a pre-K3 client file loads instead of being refused: unknown keys ignored | `test_walk.py::test_the_client_file_is_the_registrations_half` (and the identity test) |
| M3 | `init` drops the operator's chosen root again -- the defect this chunk found | `test_channel.py::test_the_chosen_root_reaches_the_store_over_the_channel` |
| M4 | `init` captures the root AFTER resolution: the governed file names one the tenant never chose | `test_channel.py::test_only_the_root_the_operator_chose_reaches_the_governed_file` |
| M5 | the channel opens with no credentials -- `client.channel` never fires | `test_channel.py::test_a_client_file_with_no_channel_is_a_typed_refusal` |
| M6 | the client stops presenting its certificate: the caller has no identity to resolve | all five channel tests |
| M7 | the client stops pinning the store to the registration's CA -- any authority will do | `test_channel.py::test_the_client_pins_the_store_to_the_registrations_authority` |
| M8 | a validation refusal comes back as prose, not as typed verdicts (Q7) | `test_channel.py::test_a_refusal_crosses_the_channel_as_the_value_it_was_raised_as`, `test_k1b_iii.py::test_the_wire_carries_the_verdicts_and_the_client_rebuilds_them` |
| M9 | the transport imports the store at module scope again -- K3's import win undone | `test_walk.py::test_the_client_no_longer_drags_the_store_into_every_import` |
| M10 | a refusal crossing the wire loses its status: every response reads as success | `test_channel.py::test_a_refusal_crosses_the_channel_as_the_value_it_was_raised_as` |

**M7 and M9 are the two worth reading.** Each dies to exactly one test, and in both cases that test is one this
chunk added because the property had nothing watching it: disabling the client's CA pin was invisible to the whole
suite before, and so was putting the store's imports back into the transport. A mutation that dies to one test is
a property held up by one test.

**One mutation survived its first form, and it was a third thing.** K1b-ii established that a survivor is sometimes
a missing test and sometimes a test that cannot see the property. M4 was neither: `args["root"] = cfg.root` in place
of `chosen_root` **could not change behaviour under any input**, because `chosen_root = cfg.root or None` is captured
*before* `resolve_root`, so reaching that line at all means `cfg.root` was already truthy and `resolve_root` returned
`cfg` unchanged. An equivalent mutant. The fix is not a new test but a mutation that is actually a change: capture
the root on the **wrong side of resolution**, which is the real defect shape — a blank root becomes the declared
default and is then written into the tenant's governed file as though they had chosen it. The first form and the
reasoning are kept in `tools/mutations/k3.toml` above the replacement, because **the three ways a survivor happens
are worth telling apart and only two of them are findings about the code.**

**A note on cost, for whoever runs mutations next.** One mutation is **~3m15s** here under `-n 8 --dist loadfile`,
because the channel tests are real sockets, real git and real signing. A ten-mutation set is over half an hour, and
no more than two fit in a ten-minute window. That is a property of the suite this chunk made slower on purpose, and
it is the price of testing the transport that actually ships.

**What this chunk did not do.** `deploy/` still never run — one line of `deploy/README.md` was corrected because K3
made it wrong (its example client file carried `mode = "https"`, now a `client.unknown-key` refusal); K2 owns the
rest. `server/` untouched, including `store.py`, which is where the root-disagreement refusal belongs. The
integrity core untouched. No status was re-priced. `mypy --strict` over `tests/` is still 46 pre-existing errors.
The sync record still reads *"[owner-ratified]; to apply"* for 7bg.2 — marking a ruling applied in the canonical
record is the owner's line to author, and no chunk in this plan has written to that file.

**Findings with no owning chunk.** Carried forward unchanged: `client/transport.py` invents `service.error` for a
client-side condition (**considered and deliberately not taken here**: it changes a rule id a caller reads, C-12's
table is K2b's, and K2b weighed this exact change and recorded it rather than making it — but K3 makes it the *only*
transport's fallback, which raises its priority); the authorization boundary sits in two layers; the ratify dry
run's `verdicts` map is `list[str]` of rendered refusals on the `result` path; `config@1` is written in two places;
the four mispriced statuses; the order-dependent tests in `test_scenarios.py` under bare `-n 8`. **Three are new:**
(i) the store-root/client-root disagreement above, which is the only one with a named fix; (ii) `Transport` builds
its SSL context with `httpx.create_ssl_context(verify=<str>)`, which httpx deprecates — the replacement it names is
`ssl.create_default_context(cafile=…)`, and it was left alone because changing how the one surviving transport
builds its TLS context is not a change to make without measuring what else that call sets; (iii) the ratify dry
run's `verdicts` map is keyed by **string** over the wire and by `int` in process, which the walk had to accommodate
when it moved onto the channel — a smaller face of the same finding, and the first evidence for it that came from a
test rather than a reading.

### K1d — done (2026-08-30). The lazy loader, the filename seam, and the 46 ms that turned out to be 1% of the bill.

**All four done-when items landed.** `registry/loader.py` reads and parses a document when it is asked for; a
`_Slot` holds one ref's bytes and its parsed form and forces on first touch. `installed` is a `cached_property` over
the slot keys — **the filenames, so it performs zero parses**, asserted by counting rather than assumed. `addresses`
is a `cached_property` that forces everything, with its carve-out note. `from_directory`'s empty-directory refusal
stays eager, with its carve-out note. **186 tests** (177 before), `mypy --strict` clean over `packages/` (39 files),
`ruff check` and `ruff format --check` clean. **10 mutations run; 10 died on the first pass.**

**Measured before and after on one harness, on the same tenant checkout.** The `min` is the headline: this
workstation's noise is one-sided (max is 3x median on every sample), so the minimum is the least contaminated
estimate. A CPU baseline is printed with each run — it drifted **+24% slower** between the two, so the after column
is understated, not flattered.

| | before | after | TOML parses |
|---|---|---|---|
| `Registry.shipped()` | 62.3 ms | **1.1 ms** | 8 → 0 |
| `Registry.for_checkout(tenant)` | 54.4 ms | **1.9 ms** | 8 → 0 |
| `.installed` | 68.1 ms | **1.9 ms** | 8 → 0 |
| `.get("config@1")` | 74.0 ms | **17.8 ms** | 8 → 1 |
| `governed_paths(tenant)` — the hook | 78.0 ms | **24.6 ms** | 10 → 3 |
| `.addresses` — the carve-out | 69.3 ms | 78.5 ms | 8 → 8 |

**The three claims in the brief that did not survive re-measurement.**

1. *"`Registry.shipped()` costs 46 ms."* It costs **62.3 ms (min) / 91.6 ms (median)** here, measured warm and
   in-process before any change. The **shape** the brief gave held exactly — parsing the eight documents is ~52% of
   it and content-addressing them ~23% — so the diagnosis was right and only the absolute was low. The brief said to
   reproduce it, and that instruction earned its place.
2. *"`addresses`' only consumers are `install.py`'s `INSTALLED` file and one test."* `INSTALLED` is written from
   **`installed`**, not `addresses`. `addresses` has **no consumer in `packages/` at all** — two tests read it. It
   is still a correct carve-out (both readers want every address at once), but for a different reason than the brief
   gave, and the note at the site says the real one.
3. *"The hook pays 46 ms per commit."* It pays that **inside** `governed_paths`. The **process** pays **5.5–7.7 s**.
   See the finding below; this is the one that changes what the number means.

**The finding this chunk could not close, and it is larger than the chunk.** `isidium hook` — the whole point of the
46 ms — costs **5,543 ms (min) / 7,381 ms (median)** per commit on the author's workstation. Measured breakdown, in a
fresh interpreter each time: bare interpreter startup **1,277 ms**; importing `isidium.store.client.hook` **976 ms**;
importing `isidium.store.client.cli`, which is what the installed hook script actually runs, **6,053 ms**. The parts:
`cryptography.x509` 1,233 ms, the generated pydantic models 2,382 ms, `opentelemetry.trace` 474 ms — all of it
imported through `client/cli.py`'s `from .transport import …`, which builds a `Store`, to answer a question that
needs one TOML file and `git diff --cached`. **K1d repaid ~1% of this hook's real cost.** That is C-13's own
principle one level up — a module graph is a collection too — and **it is filed as Q10, an open ruling, not as a
finding with no owning chunk** [corrected 2026-08-30, before the chunk closed]. The two are different things in this
record: a finding with no owning chunk is something nobody does; an open ruling is something waiting on the owner.
Whether C-13 covers module graphs is an amendment to a rule the owner authored, and no agent may take it. **The machine matters to the reading and is stated rather than assumed:** it is
genuinely slow at imports (`site` alone costs 528 ms, `import json` 40 ms), reproduced outside the tool sandbox, so
these are real seconds the owner pays per commit rather than a harness artifact.

**The behaviour seam, ruled and named as the brief required.** The ref now comes from the filename, so the filename
and the contents can disagree, and two rules make them agree:

- **`registry.filename`** — a `*.toml` in the registry directory whose name is not `<name>@<version>`. Raised **when
  the directory is listed**, because a directory that cannot be keyed is not a fact about any one document; it is
  `registry.not-installed`'s shape, and it costs the listing that already happened. It replaces a `KeyError` that
  the eager loader raised on the same file, so this is a typed refusal where there was a crash.
- **`registry.filename-mismatch`** — the document declares a different `name@version` than the ref it is filed
  under. Raised **when the document is forced**, and the test asserts the lateness as well as the refusal: opening
  the registry and listing it still cost zero parses, so moving the check back to load time fails a test rather than
  silently undoing the chunk.

Both **inherit `registry`'s terse row** rather than taking an explicit one, and `core/disclosure.py` now says why at
the row: each carries a **filesystem path** — the store's own package directory server-side, a checkout's
`.isidium/schemas` client-side — and neither is the caller's to fix. `install_schemas` has always written
`<ref>.toml` from the document's own `name` and `version`, so an installed checkout satisfies both by construction;
these fire for a directory edited by hand.

| # | mutation | died to |
|---|---|---|
| M1 | `installed` forces every document — the lazy listing lost | `test_lazy_registry.py::test_opening_a_registry_reads_nothing_and_installed_costs_no_parse` |
| M2 | `get()` forces the whole collection to answer one question | `test_lazy_registry.py::test_one_question_parses_one_document_and_asking_twice_parses_none` |
| M3 | the filename-agreement check is gone: contents may say anything | `test_lazy_registry.py::test_a_document_that_disagrees_with_its_filename_is_refused_when_it_is_forced` |
| M4 | the filename grammar check is gone: any `*.toml` is a ref | `test_lazy_registry.py::test_a_toml_the_registry_cannot_name_is_refused_when_the_directory_is_listed` |
| M5 | the startup contract is deferred — C-13 carve-out 1 removed | `test_lazy_registry.py::test_the_startup_contract_still_fails_at_startup` |
| M6 | a forced slot is not held: lazy becomes lazy-and-repeated | `test_lazy_registry.py::test_one_question_parses_one_document_and_asking_twice_parses_none` |
| M7 | `source()` parses every document to hand back bytes it already had | `test_lazy_registry.py::test_the_collection_is_forced_only_where_it_is_the_answer` |
| M8 | `for_checkout` ignores the checkout's own registry | `test_wp3_apply.py::test_c5_a_checkout_validates_against_the_registry_it_installed` |
| M9 | the directory listing silently truncates to one document | `test_lazy_registry.py::test_opening_a_registry_reads_nothing_and_installed_costs_no_parse` |
| M10 | `addresses` comes back empty — a carve-out that answers nothing | `test_registry.py::test_installed_and_fixed_point` |

**M8 and M9 are the two worth reading.** M8 died in a file the mutation did not touch, which is the rule about
aiming at the whole suite meeting its own case again. M9 is the "nothing came back" guard doing its job: a listing
truncated to one document is *faster* and parses *fewer* documents, so every count assertion in the new file passes
on it — it dies only to the positive discriminator paired with each count (`refs == the filenames on disk`, and
`len(refs) == 8`). A parse-count test without that pairing would have shipped a registry that had quietly stopped
finding documents.

**Two things about running the mutations that the next agent should not rediscover.** (i) **The full suite is ~226 s
serial and the killers live in `tests/unit`, which runs last**, so `-x` saves nothing here — a mutation costs a
whole pass either way. `pytest -n 8 --dist loadfile` cuts that materially and the suite is green under it;
**`-n 8` alone is not** — `tests/store/test_scenarios.py` shares state across its own tests and five of them fail
when they are split across workers. That is a property of the suite, not of any mutation, and it is a finding with
no owning chunk. (ii) **A killed mutation run leaves the mutation in the tree.** The harness restores in a `finally`,
which never runs if the process is killed; it happened three times here and each time `installed` or the agreement
check was left broken. The harness now writes the pristine bytes back **before** each mutation as well as after, and
asserts the file is unmutated before it starts. Check `git diff` after any interrupted run.

**What this chunk did not do.** `deploy/` still never run. The integrity core untouched — `journal.py`,
`reconcile.py`, `core/` except the comment added to `disclosure.py`'s `registry` row. `mypy --strict` over `tests/`
is still 46 pre-existing errors. No status was re-priced. Local mode still exists (K3). The `Registry(docs, source)`
eager constructor is unchanged and still eager, deliberately: its caller has already done the reading, so there is
nothing left to defer, and `registry.source-mismatch` still fires at construction.

**Findings with no owning chunk, carried forward.** K2b's are unchanged: `client/transport.py` invents
`service.error` for a client-side condition; the authorization boundary sits in two layers (`Api` for reads, `Store`
for writes); the ratify dry run's `verdicts` map is still `list[str]` of rendered refusals on the `result` path;
`config@1` is still written in two places; the four mispriced statuses are still mispriced. **Two are new here:** the
order-dependent tests in `test_scenarios.py` that fail under `pytest -n 8` without `--dist loadfile`. **The hook's
~6 s of eager imports is NOT among them — it is Q10, an open ruling.**

### K2b — done (2026-08-30). The OpenTelemetry foundation, C-12's table, and the nine ids that bypassed `Refusal`.

**All nine done-when items landed** (0, 0b and 1 through 7). `core/telemetry.py` is the foundation (the OpenTelemetry **API** only, the SDK
and the OTLP-over-HTTP exporter a `[telemetry]` extra); `core/disclosure.py` is C-12's table in its ruled two-level
shape; the disclosure filter is on `Refusal.payload()`, so it holds at every door at once; the three
pre-authentication counters move with their typed reasons; and the two phases of a call carry spans, the second a
child of the first. **177 tests** (160 before), `mypy --strict` clean over `packages/` (39 files), `ruff check` and
`ruff format --check` clean. **20 mutations run; 19 died on the first pass, 1 survived, and the survivor was a
defect in the test rather than a gap in the code — corrected, re-run, dead.**

**Item 0 was nine ids, not five, and one of the two "indirect" ones was in a different file than the record said.**
C-12 counted five bare payloads; K1b-ii then added four more (`service.headers-too-large`, `service.length-required`,
`service.too-many-connections`, `service.internal`) after the count was taken. All nine now build a `Refusal` and
answer through `Response.refusal`. Of the two indirect cases: `server/refs.py`'s `_check` returned a rule id as a
bare **string** for its caller to wrap, which made `ref.ambiguous` the one id in the package appearing in no rule-id
position anywhere — invisible to the sweep, unclassifiable by a table — and it now returns the `Refusal` itself. The
other was recorded as "built by concatenation in `server/store.py`" and **is not there**: the computed ids are
`f"profile.head.{k}"` and `f"profile.{key}.shape"` in `registry/card.py`. They stay computed, and the sweep reads the
**namespace** out of the f-string's literal prefix instead — which is the key the table uses anyway.

| # | mutation | died to |
|---|---|---|
| M1 | the disclosure filter never trims | `test_edge.py::test_an_unexpected_exception_still_answers_with_a_rule_id` |
| M2 | the `auth` namespace is reclassified `full` — the table, not the filter | `test_service.py::test_the_channel_is_the_only_identity` |
| M3 | `service.arguments` ships Python's own words again | `test_telemetry.py::test_the_two_responses_whose_words_were_not_ours_are_authored` |
| M4 | the withheld detail is trimmed and then dropped — the floor removed | `test_telemetry.py::test_a_pre_identification_refusal_carries_no_detail` |
| M5 | a refused handshake is classified and counted nowhere (K1's own debt) | `test_edge.py::test_the_handshake_counter_moves_with_the_right_reason` |
| M6 | the handshake counter moves, always with the same reason | `test_edge.py::test_the_handshake_counter_moves_with_the_right_reason` |
| M7 | the per-peer bound is counted as the global ceiling | `test_edge.py::test_the_admission_counters_name_which_bound_was_met` |
| M8 | a handshake that yielded no certificate is silent again | `test_edge.py::test_a_handshake_that_yields_no_certificate_is_counted` |
| M9 | a successful call reports no outcome | `test_telemetry.py::test_one_call_carries_a_span_with_its_outcome_and_its_rule_id` |
| M10 | the rule id never reaches the span | `test_edge.py::test_a_call_over_the_socket_carries_both_phases_as_spans` |
| M11 | the outcome is not the span's status | `test_edge.py::test_a_call_over_the_socket_carries_both_phases_as_spans` |
| M12 | `configure()` follows upstream's `otlp` default | `test_telemetry.py::test_the_default_is_no_exporter_at_all` |
| M13 | the SDK is imported at module scope | `test_telemetry.py::test_with_no_sdk_configured_the_store_reaches_no_network` |
| M14 | the aggregate's `detail` is the full rendering again | `test_telemetry.py::test_a_terse_verdict_inside_a_full_refusal_is_still_terse` |
| M15 | each verdict records itself: one call counts as N+1 | `test_telemetry.py::test_the_refusal_counter_moves_for_an_identified_caller` |
| M16 | an id in a declare-explicitly namespace loses its row | `test_rule_ids.py::test_every_rule_id_in_a_declare_explicitly_namespace_is_classified` |
| M17 | a namespace the code can raise loses its row | `test_rule_ids.py::test_every_namespace_the_code_can_raise_is_classified` |
| M18 | a rule id is built into a response body again | `test_telemetry.py::test_a_pre_identification_refusal_carries_no_detail` |
| M19 | the sweep loses its bare-payload arm — the TEST's coverage claim | `test_rule_ids.py::test_no_rule_id_reaches_a_caller_without_passing_through_refusal` |
| M20 | the sweep stops seeing f-string rule ids — the TEST's coverage claim | `test_rule_ids.py::test_the_sweep_sees_the_whole_surface` **(survived the first pass)** |

**The one survivor, and why it is the same lesson twice.** M20 disables the sweep's computed-namespace arm. It
survived because the assertion was `"profile" in namespaces()` — and every literal `profile.*` id satisfies that on
its own, so the arm could be deleted entirely with the test still green. **No namespace in the package is reachable
only through an f-string**, so the package cannot discriminate here at all; the arm has to be run over a source that
needs it. `swept()` and `namespaces()` therefore take an optional list of files, and the test plants two lines that
write **no** literal rule id and requires both namespaces to come back. The same shape had already been needed for
the bare-payload arm, whose last producer this chunk removed: an empty arm and a deleted arm are indistinguishable,
which is the "nothing came back" pass this round exists to forbid. K1b-ii's rule, met again: *a mutation that
survives is not always a missing test of the property; sometimes it is a test that cannot see the property.*

**Two defects found inside the filter while building it, both by tests written before the code was believed.**
(i) A **terse verdict inside a `full` aggregate** had its withheld words carried out anyway, in the aggregate's
rendered `detail` — the array said `{"rule": "git.failed"}` while the string beside it printed git's stderr. `detail`
is now re-rendered from the *disclosed* verdicts rather than read off the refusal. No such pair exists in the code
today (every validation family is `full`), so the case is built by hand in the test rather than left unproven.
(ii) `payload()` records the refusal on the span and the counter, so disclosing N verdicts through it counted one
refused call as **N+1** and left the span carrying the last verdict's rule id instead of `validate.failed`. The
filter and the recording are now split — `disclosed()` from `payload()` — and M15 is the mutation that proves it.

**Three of the brief's "do not rediscover" measurements did not survive re-measurement.** (i) *"OpenTelemetry is not
installed on this workstation"* — it is: `opentelemetry-api` and `opentelemetry-sdk` 1.44.0 are both present, which
is why the in-memory-exporter test could be written at all. The OTLP exporter is **not** installed, which is why
`opentelemetry.exporter.*` needed a mypy override beside `h11.*` (an extra that is not installed, not a
question-hidden away). (ii) The sweep now finds **158 distinct rule ids across 36 namespaces**, not the 150/34 the
ruling recorded — and the brief's own instruction was to trust none of the earlier numbers, *"this one included"*.
(iii) The concatenated rule id is in `registry/card.py`, not `server/store.py`, as above.

**What changed on the wire, and it is more than the table.** Every terse id's body is now `{"rule": …}` and nothing
else — not an empty `path` and an empty `detail`, which would still say we had one. That is C-12, ruled. Beyond it,
one status changed: **`service.malformed` is always 400**, because h11's `error_status_hint` is no longer consulted
— a rule id has one status and it comes off the table (C-4). The hint's only two non-400 values are 431, which the
store's own header cap refuses ahead of h11, and 501, for a request the store already answers 400 when it carries
*one* `Transfer-Encoding` header rather than two. `test_edge.py` sends two and asserts the 400.

**What the table deliberately did NOT do: re-price a status.** Every status in `core/disclosure.py` is the status
that id carries today, because a status is a channel the clients' retry logic reads (C-12) and changing one is a
wire change no ruling asked for. Four look wrong and are left alone, **as a finding with no owning chunk**:
`api.not-yet` answers 422 where 404 or 501 would read better; `write.lander-only` answers 422 where 403 would;
`show.unsupported-target` answers 422 where 404 would; and a fault in the store's own git (`git.failed`,
`git.unsupported`) answers 422 where 500 would — 422 tells a caller their request was unprocessable, which is false
when our subprocess broke.

**Two `signer.*` cases the ruling's rationale does not cover, recorded and not fixed** (the brief named both and
said they were for whoever filled in the table). `signer.key-type` is raised by `SoftwareKey.load()` at **start-up**
from `serve --signer` and carries the **filesystem path of the private key**: it is not a call refusal at all and
never reaches a door, so it inherits `signer`'s terse row harmlessly — but a future change that made it reachable
would ship a key path to a caller, and nothing in the table says so. `signer.time-skew` is the one `signer.*` id
genuinely actionable by the caller (their `at` is outside the signing window); trimmed to a bare rule id behind a
502 it reads as "retry later", which is the wrong advice. Neither re-opens the ruling.

**The gap this chunk declares.** `isidium serve` calls `telemetry.configure()` and that call is **not covered end to
end**: `configure()` itself, the console exporter and the stderr destination are all proven in a child interpreter,
but the CLI path from `serve` to a running listener is not, because `serve` needs a real git checkout and the test
harness runs on the in-memory git double. It is one line, at the top of `serve`, before anything else is built —
and `deploy/` is still never run, so K2 is where it is first exercised for real.

**Two more findings with no owning chunk.** (i) `client/transport.py` invents the rule id `service.error` when a
response carries no `rule` key — a **client-side** condition wearing a server namespace, and an id the sweep cannot
see because it is an argument to `str()`. `client.malformed-response` would be the honest name. (ii) The
authorization boundary is still in two layers (`Api` for reads, `Store` for writes), inherited from K1b-iii and
still proposed rather than scheduled; so is the ratify dry run's `verdicts` map, still `list[str]` of *rendered*
refusals on the `result` path — the same prose-flattening Q7 removed from the `refusal` path.

**For K6, which joins on this.** The trace context exists and the two phases are parent and child, so a caller's
identity attaches to a span rather than to an invented correlation id. `isidium.subject` / `isidium.action` /
`isidium.resource` are already set from the journal's own vocabulary (03b §2) and are named once, in
`core/telemetry.py`. **Nothing about telemetry enters hashed content** (C-9): the journal is untouched by this chunk.

**What this chunk did not do.** `deploy/` still never run, no container runtime invoked. The integrity core
untouched — `journal.py`, `reconcile.py`, `core/` except `refusal.py` and the two new modules. `mypy --strict` over
`tests/` still 46 pre-existing errors, still nobody's chunk. Local mode still exists (K3). And the CLI door still
prints `str(r)`, unfiltered, **by design** — it is a human at their own terminal, it grew no payload, and over the
network it reads a body the filter has already trimmed.

### K1b-i — done (2026-08-29). The triage of all 29 findings.

**Every finding was reproduced before it was acted on.** Where a measurement did not reproduce, or reproduced
differently, that is recorded below as a finding about the review — it is not evidence either.

**Buckets.** **(a)** record correction, the code is right and the words are wrong · **(b)** code fix in K1's files
(→ K1b-ii) · **(c)** a later chunk's brief amended so its agent is not sent to do something wrong · **(d)** an owner
ruling (→ §5).

| # | Reproduced? | Bucket | Where it landed |
|---|---|---|---|
| F1 certificate finding backwards | **yes, and the mechanism corrected** — it is the client's `VERIFY_X509_STRICT` flag, not an OpenSSL version: same certificates, flag cleared, all connect | a | 7bg.11 marked in place; deployment record S-1 … S-3; K2's trap |
| F2 partial clone ≠ "no code, ever" | yes — an ordinary read fetched a code blob and kept it; `GIT_NO_LAZY_FETCH=1` refuses it | **d** | **Q3**; K4's ruling block |
| F3 counter has no home | yes — 0 handler calls, 0 log records, ×3 classes | a + **d** | K2b's trap corrected; done-when 5 rewritten; **Q1** |
| F4 limits untested | yes, and **worse: five survive, not two** — ceiling, handshake, read, write, header cap; 3 controls died | b | K1b-ii item 7; §1 gains the mutation rule and the "nothing came back" rule |
| F5a table cannot key on namespace | yes, **and two more reasons found** — two ids have no namespace; the counts in *both* records are wrong (150/34) | **d** | **Q2**; C-12 amended; K2b's item 2 withdrawn |
| F5b malformed cert leaks parser text | yes — found independently before the review was read | b | K1b-ii item 3; C-12 amended |
| F6 one caller denies the store | yes — 8/8 held, next caller refused in 0.05 s | **d** | **Q4** |
| F7 header cap bites at ~64 KiB | yes — 60 KiB → 200, 128 KiB → 431 | b | K1b-ii item 2 |
| F8 `Content-Length` not required | **yes in substance, not in output** — the review showed a 200; I get a 400 from the *verb*, which still proves the framing layer passed it through | b | K1b-ii item 1; K1's done-when gains item 5 |
| F9 "mutation-checked" over-reads | yes | a | K1's done-when annotated per item |
| F10 degradation undetectable from config | yes — both clones write `promisor=true filter=blob:none`; path clones ignore `--filter` | c | K4 done-when 2; deployment record S-9 |
| F11 "zero overhead" false | yes — ~20 µs vs 0.13 µs baseline; egress genuinely 0 | a | C-11; K2b |
| F12 counts not reproducible | yes — **and the review's own "28 exact" is also wrong**; 150 ids / 34 namespaces | a | K2b item 2; C-12 |
| F13 done-when 3 false as written | yes — 4 docstring mentions, symbol and constant gone | a | K1 done-when 3 |
| F14 K3's done-when unachievable | yes — `pre-commit.local` | c | K3 done-when |
| F15 `HEAD` answers nothing | yes | b | K1b-ii item 5 |
| F16 unexpected exception → nothing | yes — caller gets no bytes; server survives | b | K1b-ii item 4 |
| F17 typed verdicts flattened | yes | **d** (+ c) | **Q7**; K1b-iii item 3; K2b's done-when 2 warned |
| F18 fingerprint re-encodes | yes | c | K6 trap |
| F19 three small ones | yes | b | K1b-ii item 6 |
| F20 uvicorn in the image | yes — `Containerfile.store:24` | c | K2's file table |
| F21 K2's work list incomplete | yes — socket healthcheck, `ISIDIUM_CLIENT`, 2 options vs 8 | c | K2's file table (rewritten) |
| F22 `deploy/` ↔ K4 seam unowned | yes — `[ ! -d "$TENANT_DIR/.git" ]` | **d** | **Q6** |
| F23 K5's trap is done work | yes | c | K5's trap struck; the h11 floor claim **verified** by fetching the advisory |
| F24 store cert needs a SAN | **substance yes, mechanism NO** — varying *only* the SAN, the client still connects: OpenSSL falls back to the Common Name. The review's probe changed the EKU at the same time | a | deployment record S-2, with the requirement stated as measured |
| F25 `repair` outside the seam | yes | c | K1b-iii item 1 |
| F26 C-1 violation the sweep can't see | yes | b | K1b-ii item 8; C-1 downgraded to partly-enforced |
| F27 which surface enforces C-12 | yes | a + c | C-12 gains the answer: the shared constructor, not the HTTP response |
| F28 `install_schemas` foreign manifest | yes | c | K1b-iii item 2 |
| E1 K4's N subprocess spawns | **yes in direction, not in number** — the ~126× is machine- and N-specific; the true statement is *N spawns vs one* | c | K4 done-when 6 |

**Two corrections to the review, and one thing it could not check that now is checked.**

1. **F24's mechanism is wrong.** Varying only the `SubjectAltName` on the store's certificate, the client connects
   fine — OpenSSL falls back to the Common Name when there is no SAN. The review's two arms also differed in EKU,
   so it measured something else. The requirement, established one variable at a time, is in the deployment record.
2. **F12's "28 namespaces, exact" is not exact.** Both the plan's scan and the review's missed the
   `_r(rs, "<rule>", …)` helper form; the real figures are **150 ids across 34 namespaces**. Since the count was
   the stated justification for the namespace key, whoever takes Q2 should re-run the sweep rather than trust any
   of the three numbers, this one included.
3. **The uvicorn blind spot is closed.** In a throwaway venv, since deleted: uvicorn **0.52.4** contains no `"tls"`
   extension key, no `getpeercert` and no `ssl_object` anywhere in the package — it calls `is_ssl(transport)` only
   to set the scheme. With hypercorn 0.18 already read, **no ASGI server can hand an application the caller's
   certificate**, which is the claim 7bg.8 rests on and it is now verified rather than asserted. The h11 CVE claim
   is verified too: the advisory states exploitation requires h11 *plus* a buggy proxy, fixed in 0.16.0.

**What I did not do, and what it would take.**

- **No code and no tests were changed.** The whole of bucket (b) is K1b-ii's; the tree is untouched except for
  documentation. The mutation run that produced item 7 restored `server/http.py` with `git checkout --` and the
  suite is green at 125.
- **I did not run `deploy/`.** No container runtime was invoked. F20–F22 are from reading the files; whether the
  image builds is still unchecked and is K2's.
- **I did not re-review what the review declared out of scope** — `store.py`'s `write`/`ratify`/`_apply`,
  `journal.py`, `reconcile.py`, `core/`. Those carry the integrity guarantee and were last reviewed at WP2/WP3.
  K7 is where they come back. `signer.py` **was** read, because C-12 classifies it (see K2b's measured item 4).
- **The review's own method caveat stands and applies to my mutation run too:** mutations were checked against
  `tests/store/test_edge.py`, not the full suite, because they are local to `server/http.py`. "Survived" means
  "not caught by the file where the property is supposed to be proven."

### K1c — done (2026-08-29). The three C-1 violations, and the question that turned out not to be one.

**All three landed together and the `PENDING` table is deleted, not emptied.** `default_governed()` no longer
exists; `adopted_version` takes a `Registry`; `isidium init --root` resolves from the adopted version;
`RemoteTotp` takes `poll_interval_ms` from its caller. **146 tests** (143 before this chunk's tests, 141 before the
rulings), `mypy --strict` clean over `packages/` (37 files), `ruff` clean.

**Six mutations run, six died** — each named by the test that caught it, since a mutation that dies to an unnamed
test proves less than it looks:

| # | mutation | died to |
|---|---|---|
| M1 | `resolve_root` becomes a no-op | `test_init_records_a_concrete_root_when_none_was_chosen` |
| M2 | `init` writes the resolved root into the governed file | `test_the_tenant_config_carries_no_root_it_did_not_choose` |
| M3 | `config@1`'s manifest adopts `config@2` | `test_every_config_version_declares_a_manifest_that_adopts_itself` |
| M4 | `adopted_version` stops consulting the registry | `test_every_config_version_declares_a_manifest_that_adopts_itself` |
| M5 | the hook stops overlaying the declared manifest | `test_the_hook_and_the_store_read_the_same_manifest` |
| M6 | `poll_interval_ms` gets its code-side default back | `test_no_declared_default_is_supplied_by_code` |

**M5 survived its first run and that is the most useful thing here.** Aimed at `test_wp3_apply.py` it lived; aimed
at the whole suite it died, to a test in a different file. Both facts matter: the coverage existed, and **the
chunk's own tests did not have it** — every test in that file initialises a store, so every `config.toml` it sees
already has a `[[governed]]` table, and the fallback arm was never reached. Widening the target found the killer;
writing the missing test made the chunk self-supporting. **A mutation aimed only at the file you edited will tell
you your file is covered, not that your change is.**

**One behaviour change, deliberate, and it was found by that same gap.** The hook used to read
`tree.get("governed") or <the manifest in the binary>`. A `config.toml` declaring `governed = []` — reachable, we
checked — therefore got the **full default manifest** from the hook and an **empty** one from the store: the local
check refused commits the store did not consider governed at all, which is precisely the disagreement C5 forbids.
Resolving the effective config in the hook makes the two agree, and the tenant's stated policy wins.
`test_the_hook_and_the_store_read_the_same_manifest` asserts all three shapes.

**Two things the brief told me to look at and leave, and I did.** `resolve_effective`'s `v = s if … else 1` is a
schema-version *selection*, not a declared default. `RemoteTotp`'s `timeout_s = 600` shares its number with
`time_skew` but is a different key, and the sweep keys on the declared name.

**Item 3 touched `server/store.py`, one line** (`store.py:804`, the `init` policy-chain bootstrap — not the
integrity core). The brief's older "if item 3 reaches into `store.py`, hand back" clause was conditioned on the
question being unruled; Q8's call-site table names that line, so it was built rather than handed back. **Flagging
it because the two sentences could be read against each other.**

**What this chunk did not do.** No security or limit assertion lives here, so there was nothing of that kind to
mutation-check beyond the six above. `deploy/` still never run. `mypy --strict` over `tests/` still 46 pre-existing
errors. The schema version a fresh `init` adopts (`config@1`) is now written in **two** places — `store.py`'s
`"schema": 1` and `install.resolve_root` — which is a version selection rather than a declared default and so is
outside C-1, but it wants a single home the day a `config@2` exists. **Proposed, not built, and not scheduled.**

**Corrected while here:** `test_walk.py`'s hook test claimed the hook "costs one file read" (it now costs a
registry load too) and carried `assert root == "docs/work/" or root == "docs/work/"`, a tautology. Both fixed — the
first because this chunk falsified it, the second because leaving a defect I had just relied on for a mutation kill
is the exact pattern K1c exists to end.

### K1b-iii — done (2026-08-29). Four items, one of them wider than its brief, and nine mutations.

**All four landed.** `repair` is authorized by the grant matrix like every other verb; `install_schemas` writes the
bytes of the registry it was handed; a validation refusal carries its typed verdicts as an array; `validate` and
`integrity:time` are `validate.failed` and `integrity.time`. **160 tests** (146 before), `mypy --strict` clean over
`packages/` (37 files), `ruff` clean.

**Nine mutations run, nine died** — each aimed at the WHOLE suite and named by the test that caught it, because a
mutation that dies to an unnamed test proves less than it looks (K1c's lesson, applied from the start rather than
discovered):

| # | mutation | died to |
|---|---|---|
| M1 | `repair` gets its hand-written owner check back, below the seam | `test_repair_is_authorized_by_the_matrix_value_not_by_a_hand_written_owner_test` |
| M2 | `install_schemas` copies from the shipped package instead of the registry it was given | `test_install_schemas_writes_the_bytes_of_the_registry_it_was_given` |
| M3 | `ValidationRefusal.payload` stops putting the verdicts on the wire (both doors at once) | `test_the_wire_carries_the_verdicts_and_the_client_rebuilds_them` |
| M4 | `refusal_from` ignores the array and rebuilds a plain `Refusal` | `test_the_wire_carries_the_verdicts_and_the_client_rebuilds_them` |
| M5 | the collector's rule id goes back to the namespace-less `validate` | `test_apply.py::test_c7_refs_resolve_at_ratification` |
| M6 | `integrity.time` goes back to the colon form | `test_rule_ids.py::test_every_rule_id_is_a_namespace_and_a_name` |
| M7 | `Registry` stops checking that its bytes cover its documents | `test_a_registry_cannot_be_built_without_the_bytes_it_claims_to_hold` |
| M8 | `install_schemas` writes `INSTALLED` from the shipped registry, not the one it was handed | `test_install_schemas_writes_the_bytes_of_the_registry_it_was_given` |
| M9 | the rule-id sweep loses its `_r(…)` collector arm — a mutation of the TEST's own coverage claim | `test_rule_ids.py::test_the_two_normalised_ids_are_gone_and_their_replacements_are_raised` |

**One item went wider than its brief, deliberately, and here is the reason.** Item 3 said to put the verdicts on the
refusal payload. There are **three** doors a refusal reaches a caller through, not one — C-12 says so in its own
words — and `McpServer._call` was building its own `{rule, path, detail}` dict. Adding the array to
`Response.refusal` alone would have delivered it to every caller **except the tool surface**, which is the caller
Q7's entire argument is about: *naming the field lets an agent self-correct instead of escalating*. So the payload
is built once, by `Refusal.payload()`, and both doors call it. That is also C-12's own ruling about where its
disclosure filter belongs — so K2b now writes that filter in one place instead of three. **Said plainly because it
is more than the brief asked for.**

**Two rule ids on the wire changed, and one of them is `repair`'s.** Moving `repair` onto the seam changes its
refusal from `write.requires-owner` to `write.grant`. That is the correct id — this is the outer matrix gate, not
the signature predicate, and 7bf.6 pins that order — and both map to 403, so the status a caller sees is unchanged.
The disclosure table already carries both ids in the same row. **The behaviour is unchanged today** because `owner`
holds `"*"`; what changed is that a policy value can now reach the decision, which is what 04 §2 exists for and
what `repair`, alone among the verbs, did not have.

**The discriminator that made item 1 provable.** "A contributor may not repair" was true of the old code too, so it
cannot tell the fix from the bug. The test instead **supplies a matrix value that grants `repair` to a contributor
and watches the gate open** — observed as a *different* refusal (`repair.target`), which only a caller the matrix
admitted can reach. Under the old hand-written check the call still refused. A test that only asserts a refusal
would have passed against the defect.

**Two defects the sweep found in itself before it found any in the code**, and both are worth carrying forward:
(i) rule ids are **not** two segments — `profile.head.status`, `scenario.command.argv` — so the invariant is about
the first segment, the namespace the table keys on, not the segment count; (ii) a `Refusal` subclass that fixes its
own id does it in `super().__init__(…)`, a call that names no `Refusal` at all, so the first draft of the sweep
could not see `validate.failed`. **A sweep is a claim about coverage and needs its own mutation** — M9 disables
one arm and dies, which is what stops the sweep from silently halving.

**Recorded, not fixed — the authorization boundary is in two places.** Writes are gated at the `Store` layer
(`Store._require`) and reads at the `Api` layer. Not exploitable: reads are unrestricted by design (03 §1.17). But
a port transcribes the shape it finds, so it wants one home before the Rust port reads it. Written at the site, in
`identity.py`. **No owning chunk — proposed, not scheduled.**

**Two more found and left, with the reason.** (i) The ratify dry run's `verdicts` map is `list[str]` of *rendered*
refusals — the same prose-flattening Q7 just removed from the refusal path, reaching the caller through `result`
rather than through `refusal`. It is a different path than item 3 names and widening into it uninvited is what §0.2
forbids; **it wants an owning chunk.** (ii) `RULE_ID`'s alphabet is asserted, but nothing asserts that a rule id's
namespace is one C-12's table knows — that test cannot exist until the table does, so it is K2b's.

**What this chunk did not do.** `deploy/` still never run. The integrity core untouched — `journal.py`,
`reconcile.py`, `core/` except `refusal.py`, which gained `ValidationRefusal` (moved from `store.py`, because both
ends of the wire now name the type) and `payload()`. `mypy --strict` over `tests/` still 46 pre-existing errors,
still nobody's chunk. `config@1` still written in two places (K1c's finding, still proposed and unscheduled).

### K1b-ii — done (2026-08-29). The edge's ten items, and seventeen mutations.

**What landed.** All ten items. The store now **starts TLS itself per connection** (Q1): a plain TCP listener, a
handler that calls `start_tls`, and a refused handshake that arrives as a value — `Refused`, six names, one
renderer (C-2) — handed to exactly one call site, `_refused`, which is a documented no-op waiting for **K2b's
counter**. The **connection ceiling moved ahead of the handshake**, and a **per-peer allowance keyed on the
credential** (Q4) sits behind it: the principal when the registration names it, otherwise SHA-256 over the bytes
the peer presented, with the unregistered CA-issued peer as its own class and its own small allowance. `Admission`
holds both; both numbers live in `Limits` and are settable on `serve`. **141 tests green** (125 at the start);
`mypy --strict` clean over `packages/`; `ruff check` and `ruff format --check` clean.

**The seventeen mutations, and what they found.** Every security and limit assertion was broken on purpose and the
test that proves it had to fail. **17 ran, 17 died** — but not on the first pass, and the three that survived are
the useful part of the record:

| mutation | result |
|---|---|
| `CERT_REQUIRED` → `CERT_OPTIONAL` | died — Q1's condition (a): the boundary is **re-proven under the new shape**, not assumed to have survived it |
| the two measured verify codes swapped | died — Q1's condition (b) |
| the ceiling never full · the per-caller allowance never reached · the probe charged the caller's allowance | died |
| the handshake timeout not passed | died — Q1's condition (c) |
| the read timeout removed from the **head** read · from the **body** read | died — *the second survived at first* |
| the write timeout removed | died — *survived at first* |
| the header cap never judged · the body cap · `Content-Length` on `POST` · `HEAD`'s method not carried | died |
| the service layer's catch-all · **both** catch-alls | died — *the single-layer mutation survived at first* |
| the malformed certificate falling through to the argument handler | died |
| the hook guessing `docs/work/` again | died — which is what proves the widened C-1 sweep sees the shape |

**Three survivors, and each was a defect in my own tests rather than in the code:** (1) the read timeout is applied
at **two** places and the stalled-peer test only ever reached the first — a peer that declares a length and then
sends no body is now its own arm; (2) the write-timeout test asserted only that a `TimeoutError` arrived, which is
also what the *test's own* outer bound produces when the timeout is removed — it now asserts the clock, and this is
the same "passes on silence" shape §1 names, in a test written to close it; (3) the unexpected-exception property
is held in **two** layers, so removing either one left it intact — the service layer now has an independent arm of
its own, and the end-to-end mutation removes both. **A mutation that survives is not always a missing test of the
property; sometimes it is a test that cannot see the property. Both are findings.**

**Decisions taken inside the brief, each with its reason at the site:**

- **The header cap became the true one** (item 2's "say which, and why"): the edge never feeds the parser more than
  the declared cap while the request line and headers are unfinished, so h11's incomplete-event belt cannot trip
  ahead of ours and the number the caller meets is the number declared — exactly, not to within a read. It is
  judged only where h11 has just said the head is unfinished, so a body arriving in the same read as its headers is
  never charged to the header cap (the first version of this got that wrong and would have refused a legitimate
  20 KiB body).
- **Two new answers are framed by hand**, because refusing at admission means deliberately not having read a
  request and h11's server state machine will not frame a response to a request it never saw. `_respond` falls back
  to a constant shape; it parses nothing, so h11 is still the only parser on the connection.
- **The global ceiling still answers nothing**, and now it cannot: it is met before the handshake, so there is no
  TLS to answer over. That is a consequence of Q1, not an oversight.
- **`serve --host` lost its default** (item 6c). What a store listens on is a deployment's decision and `0.0.0.0`
  arrived at silently is the wrong kind of quiet. `--port` keeps its default because the registration pins it. The
  three admission numbers are `None` on the CLI and resolved from `Limits`, so the number has one home.
- **The hook refuses rather than guessing** (item 8). `governed_paths` raises `hook.unknown-root` when it can find
  no configured root, and `check` prints it and exits non-zero. **This is a behaviour change:** a checkout whose
  `.isidium/client.toml` has been removed now has every commit refused until `isidium init` runs again. That is
  loud, and the alternative was S5's silence — a hook that protects nothing and says so to nobody.
- **`Registration.fingerprint` was deleted**, not fixed (F18, K6's trap). It had no callers; `Credential.fingerprint`
  hashes the presented bytes and is resolved once per connection. K6's trap is rewritten to point at it.

**New rule ids — for K2b, whose disclosure table must carry them.** `auth.malformed-certificate` (401),
`service.length-required` (411), `service.headers-too-large` (431), `service.too-many-connections` (429),
`service.internal` (500), and `hook.unknown-root` (never crosses the wire — it prints on the tenant's terminal).
The first is a `Refusal` and is in `STATUS`, which is now a read-only mapping; the rest are built at their sites
like the framing ids already were, which is C-12's "one constructor" item and is **not** closed by this chunk.
`service.malformed` still returns h11's own words and `service.arguments` still returns Python's — both are named
in C-12's consequences and both are still open.

**Findings for other chunks, and one declared gap.**

1. **C-1's gap is four violations, not one.** The sweep now walks a bare `return` and a function's default argument
   as well as absent-key fallbacks. It closed `client/hook.py` and found **three more, all in files this chunk may
   not touch**: `client/cli.py:60` (`isidium init --root` repeats `config@1`'s declared default),
   `server/signer.py:119` (`RemoteTotp.__init__(poll_interval_ms=2000)`), and `registry/config.py:184`
   (`default_governed()` *is* `config@1`'s declared manifest, written again in code). They sit in a `PENDING` table
   in `tests/unit/test_no_code_defaults.py` with the reason for each, and `test_every_pending_violation_is_still_there`
   fails when one is fixed — so the list is a worklist that cannot rot into an allow-list. **They are now
   `K1c`'s** — added to §2 the same day, because a finding with no owning chunk is a finding nobody does, and every
   document I had written said "not yours". Items 1 and 2 are one-line fixes. The third is not: `default_governed()`
   is a live fallback path with five callers, and moving it to the registry raised a question about whether C-1
   reaches into the validator — which I recorded as having no registry in hand. **That question was ruled by the
   owner 2026-08-29 (Q8): it does, and the registry is threaded.** My framing of it was wrong and the correction is
   worth carrying: I read `default_governed()` at its *definition* site and concluded the validator had no registry,
   when four of its five call sites already hold one and the fifth is one constructor away. **Locate a violation by
   its call sites, not by where the value is written.**
2. **`server/http.py`'s own catch-all has no independently reachable trigger today.** It is a belt on the service
   layer's, and mutating it alone changes nothing a test can see, because everything that can currently raise inside
   `_one_request` is either an `OSError`, a `h11.ProtocolError`, or already caught in `handle`. It is kept because
   the framing layer is where a future bug would land unanswered, and it is recorded here rather than given a
   contrived test.
3. **`mypy --strict` over `tests/` is still 46 pre-existing errors** (K1's finding 1) and this chunk added none it
   could see, but the tests are not under the bar so nothing checked. Still nobody's chunk.
4. **The `Refused` value is not yet counted anywhere.** That is by design (Q1 splits it that way) and it is the one
   thing K2b must not skip: today a refused handshake is classified and then forgotten.

**Method, stated plainly.** Items 1, 2, 3 and 5 were **reproduced against the pre-change code before anything was
written** — a length-less `POST` reached the verb with `{}`, complete header blocks of 8, 32 and 60 KiB all returned
200 against a declared 16 KiB cap while 128 KiB returned 431, and `HEAD /health` returned nothing at all. The
handshake classification was measured the same way, one class at a time, against a real `start_tls` listener: no
certificate gives `ssl.SSLError` with reason `PEER_DID_NOT_RETURN_A_CERTIFICATE`; the wrong authority gives
`SSLCertVerificationError` with `verify_code` 20; an expired certificate gives 10; a peer that completes TCP and
says nothing gives `ConnectionAbortedError` at the handshake timeout. **Only those verify codes are mapped**;
everything else falls to `verify-failed` deliberately, because a code guessed into a named class would be exactly
the kind of claim this round was called for.

**One thing that cost an hour and is worth carrying forward.** The first mutation run restored each file with
`git checkout --`, per the rule carried in from the last session. **That rule is wrong when the working tree is
ahead of `HEAD`:** it did not undo the mutation, it undid the chunk — three files reverted to `HEAD` in one step.
The correct restore is the file's own bytes, snapshotted before the mutation and written back with `write_bytes`,
which translates nothing and so cannot re-end the lines either. §1's wording is corrected accordingly.

### K1 — done (2026-08-27)

**What landed.** The store terminates its own mTLS. `server/service.py` is a typed surface — `Request` → `Response`,
one `handle`, `Registration` on DER — with `TrustedHop`, the forwarded header and the whole ASGI shape deleted.
`server/http.py` is new: the TLS listener and a bounded, one-request-per-connection loop over h11, ~180 lines
holding no protocol grammar. `serve` builds its own `Store`/`Api` from TLS and store-side options instead of
borrowing the client's local transport. The `[server]` extra is `h11>=0.16` and the mypy override follows.
`tests/store/test_edge.py` is new (8 tests over a real socket); `test_service.py` and `test_wp3_apply.py` drive the
typed surface. **125 tests green; `mypy --strict` clean over the packages; ruff clean.**

**Not touched, as scoped:** `store.py`, `api.py`, `gitrepo.py`, `journal.py`, `registry/`, `LocalTransport`.
`client/transport.py` needed no change at all — `HttpsTransport` was already plain mTLS to an address.

**Limits chosen** (`http.Limits`, each with its reason at the site): 64 connections, 10 s handshake, 30 s read and
write, 16 KiB headers, 1 MiB body. `Transfer-Encoding` refused outright; `Content-Length` past the cap refused on
the header rather than after the body.

**Findings — read these before your chunk:**

1. **The type-check bar is the packages, not the tests.** `mypy --strict` over `packages/` is clean (37 files). Over
   `tests/` there are **46 pre-existing errors** (36 `arg-type`, mostly `Store.path_of` returning `str | None` fed
   to `write`). They predate K1 — 50 before, 46 after — and §1's green bar is corrected to say which. Bringing the
   tests under the bar is worth doing and is nobody's chunk yet.
2. **TLS 1.3 hides client-authentication failure from the client, measured.** With `CERT_REQUIRED`, a peer with no
   certificate, one from another CA, and an expired one all see the same thing: a connection that opens and then
   gives nothing — indistinguishable from any other close. **So a client-side assertion proves nothing**; the
   boundary test asserts the *server's* connection handler is never invoked, which is the thing that is actually
   true and actually distinguishing. It was mutation-checked: flipping the listener to `CERT_OPTIONAL` makes it
   fail. Do that check on any security assertion you add.
3. **The first version of that test passed for the wrong reason.** Three certificates deliberately sharing one
   common name were written to filenames derived from that name, so each overwrote the last and all three clients
   used the same certificate. `issue()` now takes an explicit file label, and says why in its docstring.
4. **OpenSSL 3.5 enforces RFC 5280 strictly — this is a *setup* consequence, not a test detail.** A CA without a
   `SubjectKeyIdentifier` and a `KeyUsage` naming `keyCertSign`, or a leaf without an `AuthorityKeyIdentifier`,
   fails verification outright with `CERTIFICATE_VERIFY_FAILED`. **S-1 … S-3's certificates need these extensions
   or the store refuses every caller.** K2's README must say so.
5. **h11's header cap is on the *incomplete* event, not on total header size.** A complete request that arrives
   inside one read is parsed even when larger than the cap; an unterminated header block trips it. That is the
   parser's contract and it does bound memory — the test asserts the real property rather than the assumed one.
6. **One deviation from this chunk's own brief, deliberate.** The brief said resolve the caller before parsing
   anything. You cannot: you must parse to know the route, and `/health` has to answer a CA-issued peer the
   registration does not name. The gate is the handshake — which is stronger, and is what the boundary test proves
   — and the caller is resolved per route.

**What the next agent must know:**

- **`deploy/` is stale and the container will not start.** `entrypoint.sh` passes `--socket`, which `serve` no
  longer has. That is K2's whole job.
- **`serve` takes store-side settings as CLI options.** A store-side config file is **declared, not built**.
- `serve` still passes `Registry.for_checkout(repo)`, unchanged and marked at the site — K4 reshapes it.

## 5. Open rulings — the owner's

> Each carries the measurement behind it, the options as they actually are, and what it costs to defer.
> **No agent may choose one of these.** Where a chunk is gated, its row in §2 says so.
>
> **Q1–Q11 are all ruled and closed.** Q1–Q9 came from the 2026-08-29 adversarial round and the two questions
> K1b-ii's widened sweep raised; **Q10** was raised 2026-08-30 by K1d and ruled the same day; **Q11** was raised
> 2026-08-31 by K4, before it wrote anything, and ruled the same day. **Nothing in this plan is waiting on the
> owner.**

### Q11 — **RULED 2026-08-31: the store checks what its trees can see; a ref's sub-file locus is the assembler's, before dispatch.** *(closed)*

**Owner, 2026-08-31, verbatim:** ***"confirmed. good find."*** — on option (d) below. The two questions that got
there are the ruling's real content and are kept: *"what are the implications of this for our design, for the sot
across multiple tenants, of our secuoty posture of both zero-trust and lotl"*, and then *"are you confident in the
whole-file refs solution beng portable to a growing more complex tenancy while maintaining our design and secruoty
postures?"* — which is what killed the option recommended before it.

**The collision, and it sits inside one ratified sentence.** 03b §2 says the store holds, per tenant, *"the
tenant's repository (**it resolves `refs` outside the tracking root** and commits to `main`) … the repository as a
**partial bare clone**, governed blobs and the tree graph only, no working tree and **no code**."* Resolve refs
outside the root, and hold no code, in one clause. Q3's enforcement (`GIT_NO_LAZY_FETCH=1`) is what makes the
latent contradiction load-bearing: without it the store silently fetched the code blob and the clause stayed
comfortable. K4's brief predicted a caller like this and said *"none is expected"* — there is exactly one, and it
is `store.py`'s `_resolve_refs`, at two call sites (`write` on a born-ratified card, and the `ratify` dry run).
**Verified, not reasoned:** every other reader of repo content in `server/` reads a governed path — the three
`repo.blob(oid)` callers are all governed documents.

**What a ref needs, split apart — and this is the part that makes the ruling cheap.** Resolving a ref does two
things and only one needs the file's bytes:

- **The blob id**, which is what `refs_resolved` records and the *only* input to `ref-drifted`. Git's tree already
  holds it: `ls-tree` / `rev-parse HEAD:<path>` hand it over with **no blob and no fetch** (measured 2026-08-31,
  under `GIT_NO_LAZY_FETCH=1`, on a filtered bare clone). The store reads the file and re-hashes it today, which is
  redundant work even before the footprint question.
- **The sub-file locus** — does the file have 14 lines, does that heading exist, is `validate_profile` defined
  exactly once. Only this needs the text.

**And drift does not depend on the ref's form.** `refs_resolved` is `{path, blob-of-the-whole-file}` for all four
forms, so `ref-drifted` — the ingest event *and* the dispatch precondition — is identical whichever is written.
**No option here can weaken detection or the gate.** Say this out loud before weighing options; the first pass at
this ruling assumed the symbol form carried detection value, and it does not.

**The four options, and why three lost.**

**(a) Fetch the cited blob on demand.** Declined on three grounds, any one sufficient. It makes the store open an
**outbound connection whose target is derived from caller-supplied path strings**, inside the write transaction —
a server-side-request-forgery shape in the one container holding the write bit, and caller-influenced egress where
there was none. It makes the forge's availability the store's, which is the exact trade 7bg.8 **declined** when it
ruled against driving the store through the forge's API. And fetched blobs are permanent and monotonic, so each
tenant's store converges on a growing slice of its tenant's code — which, against 03b §2's *"keyed by tenant
namespace, so a shared deployment stays available later"*, quietly closes the shared-deployment option by putting
several tenants' code in one process. Under living-off-the-land it is the worst of the four: the fetch is
legitimate traffic on the store's own allowlisted route to the forge, which is the technique's definition.

**(b) Whole-file refs only** (the store resolves `Path` from the tree and refuses the other three). Safe forever,
and it was the recommendation until the owner asked whether it was **portable to a growing tenancy**. It is not.
03 §5.3's payload carries *"the resolved `refs` content"* under a byte budget whose meaning is pinned in T-B3:
*"decoupling **is** the context budget — a payload that does not fit is a card that is too broad, not a prompt to
be compressed."* Sub-file refs are the mechanism by which a card cites a function instead of a 3000-line file and
still fits. Remove them and the budget stops measuring what it was built to measure; the pressure lands on
splitting cards that are not too broad, or on not citing large files at all. That degrades monotonically as repos
grow, as monorepos and generated files arrive, and as tenants get more heterogeneous. **Safe forever and degrading
forever is the wrong shape to grow a tenancy on.**

**(c) The client attests the sub-file locus**, bound to a blob id the store computes itself. Sound — a bound,
signed, attributable claim is deferred-verifiable rather than trusted — but it is strictly more machinery than (d)
for the same outcome, it needs a wire change to `ratify`, and it introduces a believed claim where (d) needs none.

**(d) RULED — defer the sub-file check to the enforcer that already performs it.** At ratification the store
checks, for **all four** forms, everything its trees can see: the path exists at `HEAD`, its blob id, and that it
is outside the tracking root. Those three are the whole input to `refs_resolved`, to drift and to the dispatch
gate, so none of them weakens. The sub-file locus is verified at dispatch by **T-B3's assembler**, whose first
mechanical matching condition is already *"every ref resolves at `base_sha`"*, refused hard, before any model runs
— from the **project checkout**, which is where the payload is assembled and which has a working tree.

**Why this is not a delegation and adds no trust.** The assembler resolves refs itself; it does not read a claim.
So the store's copy of the sub-file check was the **duplicate** — a second implementation of one check, held by
the one participant that structurally cannot perform it under the ruled footprint. Removing it is C-4, not a
concession. Two parties check; each checks what it can see; neither takes the other's word.

**What it costs, stated.** *"Must resolve at ratification"* becomes *"resolves as far as the store can see at
ratification, and fully before dispatch."* That is a reword of an owner-ratified phrase (03 §1.14, and 03b §2's
clause above), **owed to the record and the owner's line to author** — no chunk in this plan writes to the sync
record. And a ref whose sub-file locus was **never valid** now survives until dispatch. Two of the three ways a
ref goes bad are still covered: one that *later* breaks changes the file, so drift catches it; one on a card that
is ever dispatched hits the assembler. What escapes is only *never valid* **and** *never dispatched* — a spike, a
`surfaces = []` task, something held indefinitely — where the pointer is decoration nothing downstream consumes.
**That residue is K4b**, which closes it at the author's terminal rather than by giving the store back a capability
the footprint forbids.

### Q10 — **RULED 2026-08-30: C-13 reaches code too, as a default and not a prohibition; the hook gets its own entry point.** *(closed)*

**Owner, 2026-08-30, verbatim** — on the first half: *"if this is about lazy loading, that was a default and not a
hard rule. but i do encourage it as it reduces cpu and ram usage"*, then *"it applies to code too. and yes on the
moving. hence my show of default but without zealotry. it's a judgment call, but it should be a judgment call and
not something that just does or dos not happen. that means thining it through. we get better result that way
anyway."* On the second: ***"b sounds like the right fit"***, framed by *"this machine is very slow and the
machines these will run on are older… let's plan for minimal power and tr to make things fast with low latency but
not sacrifice performance at runtime for paying for a seconds at build time."* **C-13 is revised to cover code**,
with the avoids-versus-moves asymmetry ruled in and the deliberation named as the rule's actual object; the hook's
entry point is **K3b** below. The owner added a third thing with the ruling — that the floor underneath both is the
**Rust port, arriving piecemeal and called from Python, each piece differentially tested against the Python it
replaces**. Recorded as direction in the sync record (round 67), not as a chunk.

**The question as it was asked, kept because the measurements are the evidence:**

**Measured 2026-08-30, and the measurement is why this is a question rather than a finding.** K1d made the registry
lazy and took the pre-commit hook's registry work from **78.0 ms to 24.6 ms**, ten TOML parses down to three. Then
the whole hook was measured for the first time: **`isidium hook` costs 5.5–7.7 s per commit** on the author's
workstation. The registry was ~90 ms of it. **K1d repaid about 1% of the cost of the path it was written for.**

**Where the rest goes, traced rather than guessed.** The `isidium` console script points at `client/cli.py:main`.
That module, at its top, does `from .transport import Transport, open_transport`; `transport.py` imports
`server/api.py`, `server/store.py` and `server/signer.py`, which pull in pydantic through the generated models and
`cryptography.x509` through the signing chain. So importing the CLI imports the whole store. Cold, one fresh
interpreter each: `client/hook.py` alone **~1.0–1.5 s**; `client/cli.py` **~4.7–6.1 s**. Roughly **3.5–5 s per
commit** is the server arriving to answer a question that needs one TOML file and `git diff --cached`.

**The detail that makes this the owner's and not an agent's.** `cli.py`'s `hook` command *already* defers its own
import — `from .hook import check` sits inside the function body. Someone already had the instinct. It buys nothing,
because the module-level `from .transport import …` twenty lines above has already pulled the server in before any
command body runs. **A deferral at the leaf, defeated by an eager import at the root** — which is C-13's shape
exactly, one level up from the documents C-13 was written about. That is the first half of the question.

**Two halves, and the second is the one that outlives the hook.**

**(i) Does C-13 cover module graphs, or only data?** C-13 says *a component loads what it was asked for, not the
collection it belongs to*, and its enforcement is the shape of the exception: an eager load of a collection carries
a note at its site naming which carve-out it is, and **an eager load with no note is the finding**. A module graph
is a collection by that sentence's plain reading. If the rule covers it, then the reviewer looks for eager imports
the way they now look for eager document loads, this stops being one hook's defect, and every part isidium builds
inherits it — which is what "this repository is the exemplar the others copy" would mean here. If the rule is about
data only, that is a smaller and perfectly coherent rule, and it should say so, because right now it does not say
either. **K1d recorded the observation "a module graph is a collection too" in C-13's own text; that is an agent's
reading of the owner's rule and it is marked as such rather than folded in.**

**(ii) Does the hook's import cost get scheduled, and in which shape?**

- **(a) Move `from .transport import …` into the command bodies that need it.** Smallest diff. But nearly every
  other verb — `write`, `show`, `check`, `ratify`, `init` — opens a transport anyway, so this helps the hook and
  `--help` and nothing else. And it moves an import failure from start-up into the middle of a command, which is
  precisely what C-13's own first carve-out exists to prevent. The tension is real and needs a decision.
- **(b) A separate entry point for the hook** — the installed hook script calls `python -m isidium.store.client.hook`
  and never touches `cli.py`. Targets the measured cost directly. Costs a second console script, and makes the
  installed hook script depend on a module path rather than on the `isidium` binary being on PATH.
- **(c) Leave it.** It is a developer's pre-commit hook on their own machine, not a server path, and the store's
  container never runs it.

**What it costs to defer:** nothing breaks. Every commit in every tenant checkout pays the seconds, and each chunk
after this one adds to `cli.py`'s import graph without anyone counting.

**One thing the owner should weigh that the measurement cannot settle.** These are *this workstation's* seconds, and
it is genuinely slow at imports — `site` alone costs **528 ms** here, `import json` **40 ms** — reproduced outside
the tool sandbox, so it is the machine and not the harness. On a faster machine the same hook might be 1–2 s.
Whether 6 s or 2 s is worth a chunk is a judgement about the owner's own workflow, not a number.

**Why this is filed here and not as a finding with no owning chunk** [correction, 2026-08-30]. K1d first recorded
it as the latter, and the K1d handoff said *"nothing in the plan waits on the owner"* on the strength of that. A
finding with no owning chunk is something **nobody does**; an open ruling is something **waiting on the owner**.
Half (ii) might have been either; half (i) is an amendment to a rule the owner authored and could never have been
an agent's. Both are moved here so the answer has a durable home in the record rather than in one session.

### Q1 — **RULED 2026-08-29: the store starts TLS itself, per connection.** *(closed)*

**Measured.** A handshake refused by `CERT_REQUIRED` inside `asyncio.start_server(ssl=…)` is invisible to the
process: 0 connection-callback invocations, 0 loop-exception-handler calls, 0 `asyncio` log records at DEBUG, across
no-certificate, wrong-CA and expired. The cause is structural — `ssl.SSLError` is an `OSError`, and asyncio's SSL
layer logs those only in debug mode and never raises them to the handler. **This is the incident that produced the
observability principle in the first place:** a sustained attempt to reach the boundary with bad certificates leaves
no count, no subject and no timestamp anywhere.

**Owner, 2026-08-29: A.** The store accepts the TCP connection and calls `start_tls` itself inside the handler, so
a refused handshake arrives as a **catchable exception carrying its reason** — measured: *peer did not return a
certificate*, *unable to get local issuer certificate*, *certificate has expired* — with the peer's address.

**What this does and does not change to the trust boundary.** *Unchanged, and it is the part that matters:* the same
context, `CERT_REQUIRED` against the same CA, the same OpenSSL state machine. No attacker-controlled byte reaches
h11 or the store until the certificate verifies; the handshake still gates every byte. *Improved:* the connection
ceiling moves **ahead** of the handshake. Today it is checked inside the post-handshake handler, so an
unauthenticated peer can make the store perform **unbounded concurrent handshakes** — elliptic-curve work per
connection — without ever meeting the limit. Under this shape the ceiling bounds handshake work too, which closes a
pre-authentication work path that exists today and is the same surface as Q4. *Cost:* one reader/writer pair per
unauthenticated TCP connection, now bounded by the ceiling that arrives earlier; and one more line of the security
path is ours rather than the standard library's.

**Why this shape and not a cleverer one — continuity across Python, TypeScript and Rust.** In Rust with tokio and
rustls the idiomatic listener *is* this shape: accept a `TcpStream`, then `acceptor.accept(stream).await` returns a
`Result` — **the handshake failure is a value you handle**, and there is no mode in which the runtime swallows it.
Node's `tls.createServer` raises a first-class `tlsClientError` event with the error and the socket. Python's
`start_server(ssl=…)` is the odd one out: it is the only one of the three that makes a refused handshake
unobservable. Counting attempts at the TLS name callback and subtracting the ones that got through would have been a
**Python-only workaround with no counterpart in either port** — it would become the semantics the dashboards are
built on, and then change meaning when the port lands. Under the ruled shape the metric is identical in all three
languages: **a refusal counter with a typed reason, emitted from the same place in the flow.**

**Who builds which half.** The **shape change is K1b-ii's**, not K2b's: it is an edge and limits change, it moves the
ceiling, and it must be mutation-checked alongside the other five limits that chunk is already fixing. K1b-ii leaves
**one call site and a typed classification of the failure**; **K2b hangs the counter on it.** Splitting it the other
way would put a TLS reshape inside an instrumentation chunk.

**Three conditions, ruled with the option.**

1. The boundary test's mutation check is **re-run under the new shape** and must still fail when the certificate
   requirement is relaxed. The property is not assumed to survive a reshape — it is re-proven.
2. A test asserts the counter moves with the **correct reason** for each of the three refusal classes — not merely
   that it moved.
3. A test asserts a peer that completes TCP and then says nothing is still closed by the **handshake timeout**
   (asyncio was applying it before; now the store passes it, so it is the store's to prove).

### Q2 — **RULED 2026-08-29: namespace default, per-rule exception, in one table.** *(closed, with two sub-items open)*

**The contradiction is between two of your own rulings.** C-12, ratified: *"One table, keyed by rule id."* The
chunk plan's later handover finding: *"The disclosure table therefore keys on the namespace."* They cannot both
hold — **C-12's own table splits the `service` namespace** (four terse ids, two authored-then-full).

**Three measurements, all new since either was written.** Two rule ids have **no namespace at all** (`validate`,
`integrity:time`). The real count is **150 rule ids across 34 namespaces**, not the 130/28 the plan claimed or the
91/28 the review claimed — both scans missed the `_r(rs, "<rule>", …)` helper form, which is most of the validation
surface. And **five rule ids never pass through `Refusal` at all**, so no sweep of the refusal type can see them.

**Owner, 2026-08-29: the two-level table.** One table holding both facts (status and disclosure), keyed by
namespace, with named rule ids overriding their namespace's default.

**Why the data wants it.** The sweep showed the disclosure split is **almost perfectly aligned with the
namespaces, with exactly one exception — the ruling's own**. Every validation family is `full` (`profile.*`,
`config.*`, `head.*`, `canon.*`, `body.*`, `ref.*`, `scenario.*`, `relation.*`, `surfaces.*`, `ext-schema.*`);
every `auth.*` and `signer.*` id is terse; only `service` splits, and it splits because C-12 split it. A flat
rule-id table with a terse default would need roughly **120 explicit `full` rows** — the safe default would be the
rare answer, and the table would need auditing by eye forever.

**What it preserves.** One table, so status and disclosure cannot drift (C-4's concern, and C-12's). A **new
namespace is a build failure** rather than a silent fall-through. And it ports *better* than the flat form: in Rust
a `Namespace` enum makes "a new namespace must be classified" a **compiler error**, free, instead of a test someone
has to remember to keep.

**Two sub-items the ruling does not settle — declared, not filled.**

- **Q2a — does a new rule id inside a `full` namespace auto-disclose? RULED 2026-08-29: inherit, except where the
  namespace says otherwise.** A namespace row carries its disclosure **and a flag meaning *new ids here must be
  declared explicitly***. The validation families (`profile`, `config`, `head`, `canon`, `body`, `ref`, `scenario`,
  `relation`, `surfaces`, `ext-schema`, `sig`) inherit `full` freely — they are about the caller's own request, a
  new rule there is a new field check, and requiring a row would make **forgetting one go terse**, which hands an
  agent a bare rule id it cannot self-correct from and sends it to the owner. That is the outcome C-12 exists to
  prevent, so fail-closed on disclosure would be failing toward the wrong hazard.

  **The flag is set on the `full` namespaces that live in server code rather than the validation surface** —
  `write`, `show`, `governed`, `api` — because those are where a new id could plausibly name something internal.
  A new id there is a **build failure** until it is classified. This is the targeted form of "declare everything":
  the protection lands where the risk is, and the table stays 34 rows plus a handful of overrides instead of ~138
  rows saying `full` for the same reason. **Why not require every `full` id to be declared:** about **138 of the
  150** ids would need a row; the table stops being reviewable (the dozen meaningful exceptions buried in 138
  identical ones); and the build failure moves from the meaningful event (*a new namespace nobody has classified*)
  to a constant one (*a new rule id*), which trains people to add the row mechanically and is how a
  classification table rots.
- **Q2b — the two rule ids with no namespace**, `validate` and `integrity:time`. **RULED 2026-08-29: normalise
  them** — `validate` becomes `validate.failed`, `integrity:time` becomes `integrity.time`. A rule id is then
  **always** a namespace and a name, the table has one key shape, and the Rust port encodes one invariant instead
  of two permanent exceptions. `integrity.time` reads correctly against the existing vocabulary — `time` is
  already one of the projected integrity reasons. **The cost was measured before the ruling, not assumed:** no
  client or production code matches either string. `validate` is raised once (`server/store.py`) and asserted in
  **11 tests**; `integrity:time` is raised twice (`server/store.py`, `registry/config.py`) and named once in the
  card schema as the rule for the timestamp-ordering check. **Built in K1b-iii, which therefore runs before K2b**
  — the table should be written against the final ids, not renamed underneath it.

**Independent of the key, and first:** every refusal a caller can receive must be built by **one constructor**, or
the enforcing sweep cannot exist — five ids bypass `Refusal` entirely today. Written into K2b as its item 0.

### Q3 — **RULED 2026-08-29: enforce it, and reword the pin.** *(closed)*

**Measured.** `--filter=blob:none` is **lazy, not restricted**: an ordinary `git cat-file` of a non-governed path
fetched a code blob into the clone and kept it. The pinned guarantee is currently a property of call-site
discipline, not of the mechanism — and K4 rewrites the call site whose signature accepts any path.
`GIT_NO_LAZY_FETCH=1` makes the same read **refuse**, measured.

**Owner, 2026-08-29: enforce it and reword the pin.** The store's git runs with lazy fetching disabled, a test
proves a non-governed read is refused, and 03 §1.3 now states *how* the guarantee is delivered instead of implying
the clone mode delivers it. The footprint stays one of the two published reasons the git-direct mechanism beat the
forge API — and now it is true of the mechanism rather than of everyone's future discipline. **Landed in K4's
brief** (the ruling block and done-when 2), and in 03 §1.3.

### Q4 — **RULED 2026-08-29: no. A per-peer allowance at the edge, keyed on the credential, with its value supplied as configuration.** *(closed)*

**Measured.** At a ceiling of 8, one authorised caller holding connections open with an unterminated request line
occupied all eight; the next legitimate caller was refused in 0.05 s. At the shipped 64 with a 30 s read timeout,
that is a renewable total outage that costs the attacker nothing. **This is inside the threat model, not outside
it:** the harness-injected session credential carries `contributor` and is held by a language model in a tenant
session. A `contributor` cannot write what it should not — and can lock the `owner` out of their own store.

**Owner, 2026-08-29: the per-peer allowance, at the edge.** Availability does **not** enter the grant matrix.

**Why this is the better design and not merely the smaller one.** Authorization and admission are different
questions asked at different times. Authorization asks *may this principal do this thing*, per call, after the
request is parsed. Admission asks *is there capacity*, per connection, before any work is spent. They must be
enforceable independently — the cap has to hold **even when authorization succeeds**, and it has to apply before
you have paid to decide. Folding capacity into the permission matrix couples a fast admission check to a policy
lookup and hands the policy engine a lever that denies service by accident rather than by intent. The separation
is the common one for good reason: Kubernetes keeps RBAC and ResourceQuota as separate objects, and nginx keeps
`limit_conn` separate from auth.

**What keeps the other design reachable.** The allowance is keyed on the **credential**, not on the grant:
**resolve the credential to a principal when the registration names it and key on that; otherwise key on the
certificate's fingerprint over the presented bytes.** Both are available immediately after the handshake and
before anything is parsed. If per-grant budgets are ever wanted, that becomes a change of *where the number comes
from*, not of *what it is keyed on* — a widening, not a rework. Keying on the principal alone would have been the
trap: it has no key for the class below.

**The CA-issued peer that is not a principal — answered here rather than left to be discovered.** The handshake
requires a certificate the CA issued; the registration is a separate thing. So there is a real and intended class
that holds a valid certificate, is **not** in the registration, and may reach exactly one endpoint — the
container's healthcheck, an orchestrator probe, a monitoring agent. It is **its own class with its own named,
deliberately small allowance**: not a grant, not a principal, not an authorization subject at all. Making that
explicit is better than a synthetic `probe` grant (which would put a non-grant in the matrix that every policy
consumer in three languages must know about) or a fallback constant (the one limit policy could not set, which
defeats the point of moving budgets to policy in the first place).

**A hole this closes that neither option was proposed to fix:** today an unregistered CA-issued peer participates
in the global ceiling with **no per-peer bound at all**, so a leaked probe certificate can exhaust the store.

**Both allowances are supplied values with a named home, never constants in the binary** (C-1 governs the shape;
C-10 says a declared limit is written where it bites). That is what earns the "policy can set limits" property
without putting limits inside the verb matrix.

**Ports cleanly, which is half the reason.** In Rust the peer certificate is on the `TlsStream` the moment
`accept()` returns; Node gives the same off the TLS socket. A grant-keyed budget would instead require the
authorization matrix to be reachable **from the accept loop** in all three languages.

### Q5 — **RULED 2026-08-29: both — the store requires `clientAuth`, and the issuance requirement is written where certificates are made.** *(closed)*

**Measured.** The store's listener does not set `VERIFY_X509_STRICT` and checks nothing beyond "this CA issued it
and it is in date": a caller certificate with **no `clientAuth` EKU**, no `KeyUsage` and no `AuthorityKeyIdentifier`
authenticates. Combined with today's common-name matching, **any leaf the tenant CA issues for a registered name is
a valid store credential** — a web-server certificate, say. Nothing in the store constrains that; the CA's issuance
policy was the whole boundary, and it was unwritten.

**Owner, 2026-08-29: both halves.** Enforcement alone would silently lock out an operator whose certificates lack
the extension — the exact failure this round corrected. Documentation alone is unenforced, and a CA shared with
anything else re-opens it. So:

- **The store requires `clientAuth` on a caller certificate**, and refuses with an authentication rule id when it
  is absent. **This is K6's**, not the edge chunk's: K6 is already tightening full-subject matching and the
  validity window on the same certificate, in the same file, so it is nearly free there and it keeps all four
  caller-identity properties in one reviewable pass.
- **The deployment record's S-3 carries the requirement** where certificates are made, alongside the S-1 and S-2
  requirements corrected this round. An operator reads one place.

**Deliberately not ruled with it:** `KeyUsage(digitalSignature)` on caller certificates. `clientAuth` is the
extension that says what the certificate is *for*; adding a second check buys little and adds a second way to be
locked out. If a later round wants it, it arrives the same way — enforcement plus the setup line, together.

### Q6 — **RULED 2026-08-29: the container chunk moves after the bare-clone chunk and is written once.** *(closed)*

`deploy/entrypoint.sh` refuses to start unless `$TENANT_DIR/.git` exists; a **bare clone has no `.git`** — the
directory *is* the git directory. The Containerfile's `WORKDIR`, `compose.yaml`'s comment and the README's
`git clone <remote> tenant` all assume a working tree. K2 ran before K4 and rewrote all of them; K4 makes the clone
bare and may not touch `deploy/`. So K2 would correctly write a working-tree deployment, K4 would correctly remove
the working tree, and the container would stop starting — with the fix in a file K4 is forbidden to edit and a
chunk already marked done.

**Owner, 2026-08-29: add the dependency edge and move the container chunk after the bare-clone chunk.** It is
written **once**, against a store shape that exists. The reasoning is in §2 under *"Why the container chunk moved
to the end"*, and the accepted cost — the container arrives later, and slips if K4 slips — is stated there with
the mitigation ruled alongside it: **K4 runs `serve` against a real bare clone outside the test suite before it
hands off**, so the container's first start debuts only the container.

**The rejected alternatives, for the record.** *K2 writes for bare now:* its own definition of done ("a container
starts and answers `/health` over mTLS") could not be met, because the store cannot produce a bare clone yet — the
gate would be spent on a configuration about to be discarded. *K4 gains `deploy/`:* keeps the container early, but
commits a file we already know to be wrong and leaves the flip as a trailing edit at the end of the largest chunk,
when the agent's context is thinnest.

### Q7 — **RULED 2026-08-29: yes — the verdicts travel as data, additively.** *(closed)*

`ValidationRefusal` collects typed `Refusal`s and flattens them into a `"; "`-joined `detail`; `Response.refusal`
sends `{rule, path, detail}` and drops the list. So the caller — a language model — receives the failed field names
only inside prose, to be parsed back apart. That is the shape C-2 forbids, and it lands exactly where C-12 is
strongest: the entire argument for disclosing validation detail is that **naming the field lets an agent
self-correct instead of escalating**.

**Owner, 2026-08-29: carry the verdicts as data.** The refusal payload gains an array of typed verdicts, each with
its own rule id, path and detail, and the client reconstructs the list. **Additive** — a client reading only
`{rule, path, detail}` keeps working, so this is a wire *extension*, not a break. `detail` stays as the rendered
summary; the array is the truth, and nothing parses `detail` apart.

**Consequences to build deliberately.** The array is subject to the disclosure table like any other refusal — a
verdict whose own rule id is terse contributes its rule id and nothing more. The tool surface passes the array into
the model's context as structure rather than prose, which is the point. And **K2b's test that "a validation
refusal still names its field" must assert against the array, not the string**, or it goes green over the defect.
**Built in K1b-iii** (the value is constructed in `server/store.py`, which the edge chunks may not touch).
