<!-- provenance: schema=1 project=the-factory(working-label) session=e2b0ba9f-40d2-4bee-aa18-685ce2c8f428 actor=amodal1 agent=anthropic/claude-fable-5 generated_at=2026-08-21 status=ratified-with-proposed-mechanics -->

> **Assumes:** `03-card-schema.md` draft-6, `03a-suggestion-inbox.md` (ratified round 28), the round-4, round-5 and round-6 reviews; agent-station only by pointer (its witness layer, its identity realm, its signing service).
> **Descends from:** owner, round 30 (2026-08-20), verbatim: *"i'd argue that all structured files (wiki pages, cards, etc) must use specific writers/readers that return structured/typed responses and accept the same (except code). those fcuntions are guarded by zero-trust mechanisms that identify who has access and who altered (as we have already established). if the file is accessed or written via bash commands, it is caught at commit time by some tool call history/database line not matching the commit tool chain checks (or similar). There must be some existing tooling that we can draw from here for inspiration. Is that what you're proposing in #2 — i think your soluton is close to this though I think I've added some extras. come back to me with thoughts"* — and the rulings that followed: round 31 (*"yes"*), round 52 (the store as its own service), round 55 (the journal holds writes only), round 57 (every structured document in a registry schema's form).
> **Status:** **owner-ratified 2026-08-20 (round 31: "yes")**; **revised by rounds 52, 55, 56 and 57 (2026-08-21)** — the store runs in its own container, reads are not journaled, one config file holds the manifest and the policy chain, and the governed-document grammar and the schema registry generalize the card. Mechanics remain [proposed] until the config-schema doc and the build carry them. **Pinned by review round 6 (2026-08-21, draft-6):** the journal row shape and its repairing form, the non-card geneses and the `page:` ident, `[history].entries`, record-slot documents under `write`, the board's grant-only manifest row, and the land on `main` after the batch PR merges (X2).

# The governed store — a service that is the only writer of every structured file, with a schema for each and an out-of-band witness

## 1. What the owner added to U3, named

U3 as presented had one half: **content** — every history entry is recomputed from the diff, so a hand-written line cannot *differ* from the tool's line and survive. It left a gap it declared honestly: a hand-written line that is byte-identical to the tool's line is indistinguishable from the tool's line.

The owner's extras close that gap and widen the scope:

1. **A witness outside the file.** Every legitimate write leaves a record somewhere the writer's caller does not control. At commit time the staged diff is reconciled against that record; a change with no record is a bypass — caught even when its bytes are perfect. Detection by *access path*, not by content.
2. **All structured files, not just cards.** Wiki / recall pages, cards, the board, the inbox, config — anything with a schema — is read and written only through typed functions that accept and return typed values. Code is exempt: its record is the git diff itself.
3. **The boundary is a process and an identity, not a file format.** The typed functions run where the caller cannot reach their internals.

And two structures the owner added afterwards: **the store is its own service** (round 52) and **every governed document is written in a registry schema's form** (round 57).

## 2. The store — a service (round 52)

Owner, verbatim: *"i'm suggesting that the tool server not run in the tenant's container, but that it runs in its own container and the tenant's container is pointed at it. does that change the shape of your advice here?"* — and *"yes and keep the board per your caveats"*.

**One store server in its own container, one container per tenant** (round 7ba.6 — owner: *"b, one store per tenant. next"*; the server is keyed by tenant namespace, so a shared deployment stays available later) — the database-server model. Per tenant (a namespace) it holds: the tenant's repository (it resolves `refs` outside the tracking root and commits to `main`), the journal, the id counter, the write bit — the repository as a **partial bare clone**, governed blobs and the tree graph only, no working tree and no code (the footprint is pinned in 03 §1.3). It is **the only writer** of every governed path. It:

- **terminates its own mTLS** [owner-ratified 2026-08-27 (7bg.8)] — there is no proxy and no trusted hop: the store answers the connection (stdlib `ssl`, `CERT_REQUIRED` against the registration's CA, TLS 1.3 floor) and reads the peer certificate off the very connection it is authorizing, so the identity is never a forwarded assertion; authenticates the **caller** by that credential (mTLS pinned in the tenant registration; realm credentials) and resolves the caller's **grant** (`owner` | `contributor` | `lander` — 03 §1.12); the harness-injected session credential is `contributor`, never `owner`;
- validates the typed request against the **registry schema** for the path (section 4);
- **journals the transition write-ahead** — one row `{seq, at, caller, paths: [{path, before_blob, after_blob}]}` + `h`, append-only, hash-chained (genesis `sha256(b"schema:<n>\njournal:<tenant>")` with `<n>` = the journal's own registry schema version; `c` = every key but `h` and `sig`; no `h_prev` — the chain binds it); **`journal@2` [K6, 2026-09-05, under 7bg.10]** adds `schema` (the version the row was written under) and `credential` (`sha256:<hex>` over the client certificate the channel presented — the fingerprint beside the principal, H-1) inside `c`, and the running span's `trace_id`/`span_id` **beside** `c` where `sig` sits (C-9); the genesis carries the version the chain *opened* under and a bump never re-genesises a live chain — rows record their own version, so a chain that spans the bump verifies whole; the tenant adopts the version through `[journal].schema` in `config@2` (04 §2.3), a signed `config-policy` act; a repairing row (`repair --journal <commit>`) carries `sig = sign(tenant ‖ h_row)` outside `c` and `repairs = <commit>` inside; stored in the store's container, outside any repo; emitted to the witness layer too (by pointer); journal and refusal field naming follows **subject / action / resource / context** (caller = subject, the verb = action, paths = resource) so isidium G7's policy engine is a swap, not a retrofit — with the email-principal ↔ SPIFFE-identity mapping settled before real records land, a named open, G7's **[owner-ratified 2026-08-27 (7be.3)]** (`../research/isidium-review-2026-08-27.md` §3);
- applies the write and **commits to `main`** of the tenant's repo under the store's identity, authored on behalf of the caller (author = caller, committer = store — pinned at build) — one commit and one push per call;
- **lands on `main` after the batch PR merges** (03 §1.4, X2): the batch PR carries code only; ingest observes the merge commit in its `cursor..HEAD` walk and the store writes the sidecar, the inbox intake and the board as its ordinary commit with the merge commit as `ledger_cursor`; the row is journaled before the commit, so a half-land — row written, commit never followed — is replayed from the row by the next `land` call (idempotent); until it lands the batch is `pending-land`, the cursor does not advance and dispatch on the tenant is closed;
- **does not journal reads** (round 55): reads are tool-call events in the witness layer; a path with an explicit read policy may be read-journaled. The manifest row's optional `read` grant member (04 §2.2) is that policy's declared home **[owner-ratified 2026-08-27 (7be.2)]**: absent = reads ungoverned (today's posture); present = the read posture wiki/recall pages land with (`../research/isidium-review-2026-08-27.md` §2).

**Clients:** the tenant's container (a thin client + one pre-commit hook that refuses any governed-path change made locally), the factory's container (the `lander` grant), the planner, the owner's workstation. The signer is a separate component in the owner-only zone; **the store never holds a ratifier key.** Two versions of a governed file can never meet in a merge — there are no merge drivers. The board is rendered by the store at land (in the same transaction as the sidecar) and on demand; committed when `board.commit = true`; nothing reads it. **The tenant repo holds data and policy only**; extrication of development plumbing from tenants is done on day one.

**Reconciliation — a pure function, per commit** (03 §9.6): for each governed file a commit touches, the journal rows for that path must form an unbroken chain from the parent's blob to the commit's blob; otherwise `integrity:unjournaled`, hard. CI asks the store; ingest asks the store; the journal head lands into the sidecar as `journal_head` and into the ledger, so the journal's landed prefix is protected by the same mirror that protects the card chains. Governed-path commits are fast-forward or merge only; a revert is a new `write` of the prior document; `repair --journal <commit>` is the owner-signed act that explains a transition made outside the store.

## 3. The governed-document grammar — the card generalized (round 57)

Owner, verbatim: *"2.yes. even the wiki-docs. and it makes it typed and structured when written in the schemas' forms for even deterministic parsing. are we on the same page?"* — same page. Every governed document is one Markdown file of this shape, parsed deterministically into a typed model:

- a **typed head**: one fenced ` ```toml ` block on line 1 — scalar keys first (among themselves in the schema's inventory order, so two stores emit byte-identical blobs), then tables in the order the document's schema pins; integers `i64`; TOML 1.0.0; unknown top-level keys rejected;
- **fixed `##` sections** the schema names, in a pinned order, each a **prose slot** with a bound (size; forbidden code points; optional `###` / `####` structure) or a **record slot** (a fenced typed block); no other `##` heading; nothing outside the sections;
- an optional **`## History` footer** — one fenced ` ```toml ` block holding `history = [ … ]`, one inline table per line, `]` alone on its line, the closing fence the last non-blank line; chained (`h`), recomputed from the diff, written only by `write`;
- **one writer** (`write`, 03 §1.2), **one chain per document**, **one genesis prefix per document type** (`card:<id>` / `inbox:<tenant>` / `policy:<tenant>` / `page:<the governed path>` / `journal:<tenant>`), each with `schema:<n>` = that document type's own registry schema version (03 §5.5).

The card is the first document type under it (head: 03 §2; sections `## Scope`, `## Updates`, `## History`). The inbox is a JSONL document type (no head, one record per line, chained) — a **record-slot** document: `write` skips its steps 2–4 (no compare-and-swap, `base` ignored — append-only, one writer; no diff; no act; the record is the entry), validates the bounds and the forbidden code points, chains, journals, appends. `config.toml` is a TOML document type whose footer is its trailing `[history]` table — `entries = [ … ]`, one inline table per line, `]` alone on its line, the same line layout as a card footer (a TOML document cannot return to its root after a table, so the chain sits in the last table). Wiki and recall pages are document types whose schemas are designed under the memory-tier row T-B12, seeded from sartor's and spolia's page conventions; **their paths are declared in the manifest now and are not yet validated** — that is a declared state, not a deferral. **Open-standards trajectory [owner-ratified 2026-08-27 (7be.3)]:** the governed-document grammar is authored here, then donated — author-then-donate, as the hook dialect records (`../research/isidium-review-2026-08-27.md` §3).

## 4. The schema registry

Owner, verbatim (round 57): *"templates are to enforce writing form (no freehand). we should be moving to a schema-bsed structure for everyhwere we would want a template and those schema will probably end up being availabel via the store or locally installed, i would think. talk me thhrough your thougts here and what I'm suggesting. almost all writes (hard for me to say always) shoulkd be governed bya  typed schema"*.

- **A schema is a versioned artifact** — `name@version` — in the registry the store serves (`show Schema(name@version)`) and that `init` installs locally for offline validation and CI: the same bytes either way, so a local check and the store's check cannot disagree.
- **The manifest maps every governed path to a schema:** `config.toml [governed]` — path pattern → `schema@version` → the grants that may call `write` on it. The default manifest covers cards, the inbox, the sidecar, the board (a grant-only row — the store renders it, no caller submits a board document, so no schema validates one; `board.commit` is the one board key) and `config.toml` itself; a tenant adds its wiki and recall pages.
- **A schema change is policy:** schemas are signed into the policy chain as `config-policy` acts like any other change to `config.toml`; a document records the schema version it was validated under (the card's `schema`; the composition `schema` + `kind` + `shape` + the extension schema names a card's full schema — there is no `template` field).
- **One schema, three consumers:** the validator inside `write`; the planner's **tool-call input schema** — the model is constrained to the form at the moment it writes, which is what makes "no freehand" cheap rather than bureaucratic; and the source the **Rust, Python and TypeScript types are generated from**. One source; nothing to drift.
- **Prose exists only in schema-bounded slots**; code is the exception — its record is git's diff. "Almost all writes" is therefore exact.

## 5. Existing tooling drawn from

| Source | What is taken |
|---|---|
| **in-toto** (supply-chain attestation; CNCF) | the model: a **layout** names which functionary may perform which **step** on which materials; each step emits a **link** recording materials → products; verification fails when a product is not explained by an authorized link. Manifest = layout; journal row = link; reconciliation = verification. |
| **Sigstore / Rekor** | the log is what is trusted, not the artifact — the ledger mirror's role. |
| **Database WAL + audit triggers** | journal before apply; recovery by replay; every row change carries the session principal. |
| **Event sourcing** | state is a fold over events; a complete journal reproduces every governed file (the tarball test); files stay the git-maintained record, the journal is the witness. |
| **Wiki engines** | edit only through an API with a revision table; structured pages never edited raw. |
| **Harness hooks** (PreToolUse) | deny the obvious in-session; prevention of the obvious, never the guarantee. |
| **OS and container identity** | the store's container is the boundary; a shell write to a governed path outside it is impossible, not merely detected. |

## 6. Consequences for the documents

- `03-card-schema.md` draft-6 carries `write` (with `NewCard{slug}` and `ratify(writes)`), the journal reconciliation, `journal_head`, the integrity reasons, the ten verbs, the grants, the card as a document type.
- The config-schema doc: `[governed]`, `[history].entries`, `[toolkit]`, `ratification.pin`, the `Origin` subsets, `board.commit`, `grants`, the registry's versioning and signing.
- T-B12: the wiki and recall page schemas; their existing wiki-updating checks become `write` validations of the same layer.
- T-C1 / T-C3 / T-C6: the factory container as `lander` client; commits ff/merge-only on governed paths; the run report contract.
- The per-phase roster: agents → identities → grants; every agent's credential is a store credential, never a shell path into governed files.

## 7. Rulings on the three openings (rounds 31, 55, 57)

1. The manifest is declared now; wiki and recall pages come under it when T-B12 is worked — **declared, not yet validated** (round 57 confirmed the scope includes them).
2. Journal storage: under the store's identity in the store's container, mirrored to the witness layer.
3. Reads: **not journaled** (round 55 reversed the round-31 answer with the cost visible); a path with an explicit read policy may be.
