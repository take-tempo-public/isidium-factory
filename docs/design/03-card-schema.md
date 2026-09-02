<!-- provenance: schema=1 project=the-factory(working-label) session=e2b0ba9f-40d2-4bee-aa18-685ce2c8f428 actor=amodal1 agent=anthropic/claude-fable-5 generated_at=2026-08-21 status=draft-6 -->

> **Assumes:** the sync record (`00-sync-record-2026-08-14.md`) and the transition catalog (`01-transition-catalog.md`) — this doc gives fields to vocabulary the catalog already fixed; it does not re-argue the catalog. Six reviews are applied: `../reviews/2026-08-16-card-schema-shape-review.md` (S1–S12, F1–F23), `../reviews/2026-08-17-card-schema-draft1-review.md` (T1–T9 as ruled, G1–G15), `../reviews/2026-08-20-card-schema-draft2-review.md` (U1–U12 as ruled), `../reviews/2026-08-20-card-schema-draft3-review.md` (V1–V8 as ruled; V9 and its section 4 are the bridge session's inputs), `../reviews/2026-08-21-card-schema-draft4-review.md` (**W1–W10 as ruled in rounds 49–58**, and its section-2 fill), and `../reviews/2026-08-21-card-schema-draft5-review.md` (**X1–X2 as ruled in round 7ba**, and its section-2 fill; its section 4 is a v1 sequencing proposal this schema does not apply — section 11). Companion notes this draft points at rather than restates: `03a-suggestion-inbox.md` (owner-ratified round 28), `03b-governed-store.md` (owner-ratified round 31; the governed-document grammar, the schema registry and the store-as-a-service live there since draft-5), `../research/story-shapes-2026-08-20.md` (section 1.11).
> **Descends from:** the sync-record decisions on the substrate (cards are the substrate; acceptance lives at filing; draft tier; ratification = validated save; fingerprint field split; execution state ledger-derived), rounds 15–48, and **rounds 49–58**: a draft is a card; one write per act and the sitting as one call; the signature predicate; the store as its own service; `needs` folded into `hold`; the claims hash only where it judges; a journal of writes only; one copy of each fact; grants vs agents and the schema principle; the strictness decisions for three targets — and **round 7ba** (X1, X2): the sitting's batch is a list of typed writes under one signature; the store lands on `main` after the batch PR merges, fail-closed while a land is pending.
> **Expected reader:** the owner (the closing check after review round 6), then the store-server implementer (typed library + CLI client + tool-call surface; validator, hasher, renderer; the one writer `write`), the config-schema doc, the signing service's and the realm's implementers (by pointer), and the sartor / spolia bridge sessions.
> **Does not cover:** the tenant config schema (own doc, next — keys in section 10); the ledger record schema (factory-internal; `state.json` in section 6 is its landed projection); the per-phase agent roster (owns the planner's interview and invocation protocol — 1.11 and 1.18 hand it the question list, the morning review and the dry run); the transition catalog's rows (cited by id); the memory tier's own design (T-B12); the secrets layer and the signing service (agent-station, by pointer — `../research/execution-adapter-auth-2026-08-17.md` section 2a); the grant *system* (isidium G7 — this doc names the three grants and what each may call, 1.12); the inbox's and the store's mechanics beyond what a card must carry (03a, 03b); the bridge session's cut-over (the round-4 review, section 4).
> **Status:** **draft-6** (2026-08-21) — a **pinning pass**. Review round 6 — the narrowest — found the core dry (four independent hashers agree byte-for-byte; every oracle disagreement but one explained by a named ruling, and that one a pin) and the periphery buildable from the document alone (153/153 checks); two calls were shape-changing and the owner ruled both in round 7ba — X1, what rides the sitting's batch (*"b with the display pin. next"*), and X2, where the land commits (*"A with the three pins."*); the rest was fill — 17 implementer pins and 28 bloat pins — applied here where each lives. Draft-5's subtraction stands (the store as a service; every structured document in a registry schema's form). Marks: **[owner]** / **[owner-ratified]** are binding at the amplitude quoted; **[proposed]** is mechanics written to realize a ratified call, not decided; **[proposed-default]** is a lean the owner said "yes on all" to. **The schema is complete in first draft** — the closing check (the round-6 scenarios re-run against this draft: 220/220, no contradiction, no shape-changing call; `../../review-artifacts/2026-08-21-round6/r6-closing-check.md`) is applied as seven pins (C1–C7, section 11).

# Card schema — the factory (working label)

## 0. What this doc must fit (inherited, not re-decided)

One line each; the ratified home of each is the sync-record round or catalog row named.

- **Three standing rules for how this doc is written (rounds 41–43).** *Deterministic functions, literally* — owner, verbatim (round 41): *"when i say determinsitic functions, i mean it. we don;t need an llm most of the time and if there was no llm involved in the development, this is what the story would have required. a function that takes these inputs in these typed forms and does some processing and outputs the specific desired output"*. *Efficiency of construction and execution* — owner, verbatim (round 42): *"ths is the biggest complaint about llm code. bloated and slow because it writes too many things. 3 calls when one would have worked. focus on efficiency of construction and efficiency of execution"* — one call when one would work; every mechanism pays for itself; values already computed are reused, never re-packaged. *"Not now" is never "never"* — owner, verbatim (round 43): *"i've been bitten by hinderances i didn;t understand and foudn that you asked a question i said no, and you transslated as this is a universal application always and forever and we were runnign into all kinds of problems because of that misunderstanding. i'm just saying, not now."* — deferred things are recorded as deferred with the future option named.
- **Three targets — Rust, Python, TypeScript.** Owner, verbatim (round 42): *"we are going to move to rust and much will need to be rebuilt to fit rust's strict construction. it would be nice if we built strict and efficient now and have less time in migration."* and (round 58) *"remember that we are rust/pyton/typescript targeted."* — every type in this doc is a closed enum or a discriminated shape; every byte layout is stated language-neutrally; canonical JSON and hashing are done by the Rust and Python cores, TypeScript parses and renders (section 5).
- **No migration code.** Owner, verbatim (round 40): *"we were designing migration code and flows that we'd spend more time building than migrating manually in an interactive session. the tests are good because they source where our blockers would have been. it's better to resolve those structural challneges that remain (as you pointed out) with care and design and not while trying to land a bunch of items ina  migration. let's continue, but assume that we wil migrate in an interactive session like this, but solve for everything that would block us on the way."* — the bridge is an interactive session (section 3).
- **Cards are the substrate; board and queue are deterministic projections that point back at cards** (3.1–3.4). The schema *stores* only what no projection can compute.
- **The schema principle (round 57).** Owner, verbatim: *"templates are to enforce writing form (no freehand). we should be moving to a schema-bsed structure for everyhwere we would want a template and those schema will probably end up being availabel via the store or locally installed, i would think."* and *"2.yes. even the wiki-docs. and it makes it typed and structured when written in the schemas' forms for even deterministic parsing."* — every governed document is authored in a registry schema's typed form and validated by the one write function; prose exists only in schema-bounded slots; code is the exception. The card is one document type under the governed-document grammar (03b).
- **The store is a service (round 52).** Owner, verbatim: *"i'm suggesting that the tool server not run in the tenant's container, but that it runs in its own container and the tenant's container is pointed at it."* — one store server in its own container is the only writer of every tenant's governed paths; tenant containers, the factory's container, the planner and the workstation are clients (1.3).
- **The zero-trust tenant frame (round 27, verbatim):** *"a tenant is a standalone project. it's tools for interacting with the factory are just that. tools for interacting with an independent entity that is also operating under zero-trust methods. the factory is using the tenant's tooling (enabled by it's factory MCP). the factory is an external operator of sorts. ony the planner or a human can write cards that must pass through the process we've discussed."* — **the factory never writes a card** (round 27).
- **Field classes** (7d.1, S9, rounds 20–25): **gated** — hashed at ratification; **claims** — closure and reopen assertions, hashed per entry only where judged (S1, W6); **tending** — scheduling preference; **log** — append-only record, never in the payload, including the document's own **history footer** (round 26); **execution** — the sidecar, written only at land. One stated criterion, 1.7.
- **Ratification = the owner's signature, once per planning sitting** (rounds 24, 29, 32, 33, 42, 43, 48, 50 — 1.12); the ledger's fingerprint record is *derived* — the card never self-reports the hash as authority (I-13).
- **Acceptance lives at filing, BDD-shaped, TDD requirements nested** (3.5); the house scenario dialect compiles deterministically (T-B2); the shape *above* scenarios is a tenant choice (1.11).
- **Scope is the owner's words** — authored or ratified verbatim, never an agent paraphrase (T-B1). No shape rule ever pattern-matches `## Scope`.
- **No silent closure** (7j.1); a contributor's `deviated` closure waits for the owner (round 35).
- **Owner condition (round 19, verbatim):** *"so long as this never creates a dependency of development on the factory for the project (sartor/spolia/anything)"* — section 8.
- **Owner condition (round 19, verbatim):** *"we have to be careful that this does not lose history on edits. Git maintained of course."* — the sidecar's append-only history (1.4) **and** the document's history footer (1.15).
- **Owner challenge (round 24, verbatim):** *"this makes us git brittle. in the entire design, a corrupt or damaged git means all history is lost. we gamble that no rebase, git issues, etc. will ever happen."* — git is corroboration, never the sole carrier (1.15).
- **Owner condition (round 25, verbatim):** *"we need to make sure that teh agent NEVER reqrites the past history. this should be a deterministic call that appends a single line. no hand-written line by an llm."* — entries are computed outputs of the one write function, chained, recomputed from the diff at every gate, journaled out-of-band (1.2, 1.15, 5.5, 03b).
- **Authority (round 24, verbatim):** *"humans and agents should follow the same rules here with only one human (me for these projects) having the authority to over-ride ratifiaction etc."* — one `owner` grant, bound in the identity realm; everyone else a `contributor` (1.12).
- **Builders read everything (round 34, verbatim):** *"the builder needs to read almost everything in the repo, because they alter almost everything in the repo: code, wiki, governance, guiding docs, history..."* — the card is the specification; the repo, the neighborhood and `guidance` are the context; **restrict writes, never reads** (1.17).
- **The bridge (round 38):** no bulk import; legacy trees are frozen archives; new cards point back (section 3).
- **Efficiency at design time** (house rule): stated per operation in 9.4; hash over the parsed model, not bytes; ids from a counter; no per-card git walks; one write call per touch; the history append is an end-of-file line insertion.
- **Brownfield continuity where it costs nothing** (2.6, 2.7): schema-1 (`docs/dev/work/SCHEMA.md`) stays readable as the archive; departures say why (2.3).

## 1. Shape — ratified, with five reviews applied

### 1.1 One card = one Markdown file: a typed head, fixed sections, a tool-only footer — **[owner-ratified 2026-08-17 (review S2)]**; footer **[owner-ratified 2026-08-20 (round 26)]**; drafts are cards **[owner-ratified 2026-08-21 (round 49)]**

```
<root>/cards/<NNNN>-<slug>.md
```

A card is one **governed document** under the grammar of 03b: a fenced ` ```toml ` head (scalar keys first, then the tables in the pinned order `[narrative]`, `[[rules]]`, `[[questions]]`, `[[answers]]`, `[[guidance.*]]`, `[[acceptance.scenarios]]`, `[[closures]]`, `[[reopens]]`, `[x]` — 4.3), then the body: `## Scope` (**gated**; the owner's words verbatim plus any elaboration the builder must read; optional on drafts), `## Updates` (**log**; append-only dated blocks, authored prose, headers tool-stamped; optional), and **`## History`** (**log, tool-only; required on every card**: one fenced ` ```toml ` block holding `history = [ … ]`, one inline table per line, `]` alone on its line, the fence closing the file — 1.15). Owner, verbatim (round 26): *"that's going to make that file unreadable as history gets incredibly long. can the history  exist in a footer?"* — it does; **the append is a line insertion before that `]` at end-of-file**. Any text outside these sections, or any other `##` heading, is `body.unclassified` (S2/F23); `###` / `####` are allowed under Scope and Updates, never under History. Grammar in 9.1.

**Drafts are cards** (W1 — round 49: *"yes."*): a draft is a card in `cards/` with `status = "draft"` and an id allocated by the store inside the creating `write` (`NewCard{slug}`, 1.2) from its counter (1.6). There is no second directory, no draft key, no promotion. Provenance from a suggestion is `source = "suggestion"` + `see = ["s12"]`.

Filename: `NNNN` = zero-padded `id`, width `max(4, digits(id))` — one legal name per id; it must match the head; `<slug>` is a mutable label. Card files are never deleted (F8).

**What the line sees is made true, not claimed** (S2, revised rounds 24 and 34): the run payload carries the **canonical serialization of this card's gated set** (section 5) plus the **derived neighborhood projection** (1.17); what the builder may *read* is the whole checkout.

### 1.2 The typed surface and the one write function — **[owner-ratified 2026-08-16; rounds 26, 41, 50, 51]**

TOML head, chosen for: a stdlib parse in Python, a standard crate in Rust, a parser in TypeScript; typed literals; zero-cost reading of the brownfield archive. **The hashes are over the parsed value tree under a declared canonicalization (section 5), never over bytes.** Two models, stated (W10): the **raw value tree**, filtered to the gated keys, is what is hashed; the **typed model** (generated from the registry schema for all three targets) is validated, never hashed — so absent-vs-default and absent-vs-empty survive.

**The store is a typed library with clients.** Owner, verbatim (round 26): *"but calling the command means they pass it typed structured sata that the tool writes, correwct? so it's a function call and not a bash command?"* — yes: the CLI (`cards …`) and the MCP / tool-call surface wrap the same schema; callers pass typed arguments; the history entry, the journal row, the board and every other generated artifact are **computed outputs, never inputs**. For agents the tool-call surface is the intended one; the harness denies direct file edits under governed paths as prevention of the obvious — the guarantee is the store's identity and its journal (1.3, 03b).

**`write` — the one writer (V1, round 41).** Owner, verbatim: *"why a working copy path? why doesn't the function that writes cards have a function for writing this? this seems like extra work instead of one robuts function that handles the task and the model hands it evetything it needs in structured form and the function writes it? what am i missing?"* — nothing:

```
write(path: GovernedPath, document: Document, base: Option<HistoryHead>, ref: Option<ActRef>) -> WriteResult
```

`GovernedPath` is a path under the manifest (03b) or **`NewCard{slug}`** — a creation: `write(NewCard{slug}, document, None, None)` allocates the id inside the call from the store's counter and `WriteResult` returns `{id, path, head}` (`head` = the new `{seq, h}`); `disposition --as card` uses the same. There is no `new` verb. A refused creation burns an id — allocation precedes validation and ids are never reused (1.6); harmless, stated.

1. **Validate** `document` against the registry schema for `path` (for a card: the profile of its `kind` and the layer rules of its `shape`, 1.11) — a typed refusal names the rule id. **Rules declare their input keys:** `write` runs the rules whose inputs intersect `D` (step 3 — the diff is taken first) plus the `id`/`status`-class invariants; whole-set rules (`id.unique`, acyclicity, the ladder, `relation.unratified-target`) run when `D` touches a relation key — acyclicity as a DFS from the changed edges, never a full-graph pass — and always under `ratify` and `check`; a tending edit never re-resolves `refs` or re-walks the graph. `write` never runs `id.unique` (the counter is authoritative); `check` does, in CI.
2. **Compare-and-swap:** `base` must equal the document's current history head `{seq, h}` (`None` for a creation); otherwise `write.stale` — the caller re-reads (`show`) and retries. `seq` is assigned by the store inside this call (a row lock).
3. **Diff** against the governed copy — `D` in the same canonical JSON (5.3) for tending keys as for hashed ones, so an NFD→NFC retype of `summary` is no change; **derive** the entry: **`derive(before, after, ref) -> Result<Entry, RuleId>`** — the table below for `act` and `fields`, and inside the same function, on every structured call (not only `--set updates+=`), the append-only rules: `log.rewritten` (Updates, History, `see`, extension lists), `claims.rewritten` (`closures`, `reopens`), `questions.dropped-unanswered` (1.11), and `write.deletion` (an absent `after` — card files are never deleted, F8). `write.no-change` iff `D == []` and `ref` is `None`. **On a ratified card an answer is a gated change and derives `ratified`** (row 3 precedes the `answered` row) with `fields ⊇ ["answers", "questions"]`; `answered` is reachable on drafts; the ledger's `answered` unpark event (section 6) references whichever entry carried the answer (C2).
4. **Decide the signature by the predicate** (W3, round 51: *"yes."*) — over (before, after), independent of the act's name. A signature is required iff the diff: removes or relaxes a `blocked`/`deferred` hold on a ratified card (including re-kinding it toward `watching`); moves `status` toward more active (`draft → ratified`, `closed → ratified`, `withdrawn → ratified`); touches a gated key on a `ratified` card; accepts a closure; repairs a chain or the journal; reverses a withdrawal; changes the policy surface. A caller without the `owner` grant whose diff needs a signature is refused (`write.requires-owner`); an `owner` call invokes the signer **inside this call** (1.12) — no signature, no write — or rides the sitting's batch as a `WriteRequest` (X1). Two pins on the predicate (round 6): the "more active" clause **exempts a contributor's retraction** — `closed → ratified` whose only claims change is `closures[-1].retracted: false → true` on a closure not yet landed (the `closed` entry's `seq` > the sidecar's `history_head.seq` — one integer compare, C6), with no `reopens[]` entry (1.5), and **only when `D` has no gated key** — tending may ride the retraction, a gated edit may not (C5); the owner's own `closed` and `withdrawn` are signed by **one caller-aware clause** — the caller holds `owner` and the diff moves `status` to `closed` or `withdrawn` ⇒ sign — so for exactly that clause the predicate is over (before, after) plus the caller's grant; recompute is unaffected (`sig` presence is verification's, not recompute's).
5. **Journal** the transition write-ahead (03b), **write** the file, **append** the one history entry (1.15), **commit and push** to `main` (9.4). One call, one entry, one journal row, one commit.

**Record-slot documents** (the inbox, 03b §3) skip steps 2–4: no compare-and-swap (`base` is ignored — append-only, one writer), no diff, no act; the record is the entry — validated (bounds, forbidden code points), chained, journaled, appended.

**The recompute table — `act` and `fields` as a function of (before, after, ref)** (H1, W2). `D` = the head keys whose canonical value changed, plus `scope` / `updates` when those sections changed; sorted.

| Condition (first match) | `act` | `fields` |
|---|---|---|
| no `before` | `created` | every key present in `after`, sorted, + `scope` / `updates` if present |
| `status` `draft → ratified` | `ratified` | `D` (includes `status`) |
| `status = "ratified"` in both, `D` ∩ gated keys ≠ ∅ | `ratified` (re-ratification — W2) | `D` |
| `status` `ratified → draft` | `demoted` | `D` |
| `status → withdrawn` | `withdrawn` | `D` |
| `status` `withdrawn → ratified` | `unwithdrawn` | `D` |
| `closures` grew by k ≥ 1 | `closed` (for the owner's close the store fills `ref` from `closures[-1]` of `after`) | `D` |
| `closures[-1].retracted` `false → true` | `retracted` | `D` |
| `reopens` grew | `reopened` (`ref` = the closure) | `D` |
| `hold` added, re-kinded toward `blocked`/`deferred`, or re-kinded `blocked ↔ deferred` | `held` (unsigned for the re-kind) | `D` |
| `hold` removed or re-kinded toward `watching` | `released` | `D` |
| `questions` shrank and `answers` grew | `answered` | `D` |
| `D == ["summary"]` | `summarized` | `["summary"]` |
| `D == ["updates"]` | `noted` | `["updates"]` |
| `ref` is a closure and `D == []` | `accepted` | `[]` |
| `ref` is a `restart_from` | `repaired` | `["history"]` |
| the policy file and `ref` is `Members(H)` (written by `ratify` at signing, 1.12) | `batch-manifest` | `[]` |
| the policy file and `ref` is a `Binding{…}` (the realm's act, 1.12) | `binding` | `[]` |
| the document is the policy file | `config-policy` | `D` |
| anything else | `amended` | `D` |

**One write, one entry** (W2 — round 50: *"yes."*): a document that both changes content and flips `status` to `ratified` is **one** `ratified` entry whose `build` is the content signed; a card born `ratified` is one `created` entry carrying `sig`. A commit therefore never carries two entries for one card, and the gates' recompute is always parent-blob → commit-blob. **One derive function at every gate, refusals included** (round 6): CI and ingest run the same `derive(before, after, ref)` that `write` ran and compare `act`, `fields`, `build`; a mismatch — or an `Err`, since no entry can match a diff `write` would refuse — is `integrity:tampered`. The hook never recomputes; it is one check (9.6). **The hook refuses; it never appends** (V1): a staged change to a governed file with no journal row is `integrity:unjournaled`; the only way such a change enters `main` is the owner's `repair --journal` (V6).

**Verbs — ten** (W9): `write` (with `--set key=value` sugar; `NewCard{slug}` for a creation), `show <target>` (the one typed read, unjournaled — round 55 — with `Target = Card(id) | Board | Queue | Inbox | Schema(name@version)`: the board, the queue, the inbox and a registry schema are targets, not verbs), `check`, `ratify` (`writes: [WriteRequest]`, `ids` as the shorthand; `--dry-run`; 1.12), `accept` (run the suite; `--close`), `suggest`, `disposition <s> --outcome …` (03a), `land` (the `lander` grant only), `init`, `repair` (`--history`, `--journal`). Act-named verbs were removed: the act is derived from the diff, so a verb that names it names nothing; `cards write 42 --set hold.kind=blocked --set hold.on=owner` is the gesture. The planner never uses verbs; it calls `write` with the structured document.

### 1.3 The tracking root, and the store as a service — **[owner-ratified 2026-08-17 (S10)]**; writer = the store **[rounds 27, 31]**; **the store in its own container [owner-ratified 2026-08-21 (round 52)]**

Root path is tenant-chosen (default `docs/work/`), named in the factory's tenant registration and in `config.toml`. Everything under it is on the ratification path (`main`). **Every path below is a governed path** (`[governed]` in `config.toml`, 03b): read and written only through the **store**, which authenticates the caller, checks its grant (1.12), validates the request against the path's registry schema, and journals the write before applying it.

| Path (under root) | What | Who may call the writer (grant) | Notes |
|---|---|---|---|
| `cards/<NNNN>-<slug>.md` | every card, drafts included (W1) | `owner`, `contributor` via `write`; signature-requiring diffs (1.2) only under `owner` | **the factory never writes a card** |
| `suggestions.jsonl` | the suggestion inbox (1.18, 03a): intake and disposition records, append-only, chained | intake: `lander` (from run reports, via `land`), `contributor` (`suggest`); dispositions: `contributor` *with the owner*, `owner` | the factory's only card-adjacent write |
| `state.json` + `state/history.jsonl` | the execution-state sidecar = the vendored ledger snapshot (1.4): **current per card** in `state.json`, the append-only history in `state/history.jsonl` (W8) | `lander` only (`land`); the hotfix lane never writes it (F6) | a caller rule (round 27); landed on `main` after the batch PR merges (X2, 1.4) |
| `BOARD.md` | the rendered board with its queue and inbox sections (1.16) — a projection **nothing reads** | the store, at land (same transaction as `state.json`) and on demand (`show Board`) | committed when `board.commit = true` (default); owner, round 52: *"yes and keep the board per your caveats"* |
| `config.toml` | the policy surface, **one file**: tenant config (section 10), the governed-path manifest `[governed]`, and its own history as a trailing `[history]` table (W8) | `owner` via `write`; every change is a `config-policy` act, signed (V5) | carries no secret, no address, no key |

**The store is a service (W4, round 52).** One store server runs in **its own container** — the database-server model — and holds, per tenant (a namespace): the tenant's repository (it resolves `refs` outside the root and commits to `main`), the journal, the id counter, and the write bit. **The store's footprint is pinned [owner-ratified 2026-08-27 (7bg.8); how it is delivered ruled 2026-08-29]: a partial bare clone — the commit graph and the trees, and blob content only for governed paths. No working tree, no index, no code, no media, ever — and *ever* is enforced, not merely intended.** The two halves are delivered by different things and the difference is load-bearing. **No working tree and no index** is a property of `--bare`, and it is true by construction. **No code and no media** is *not* a property of `--filter=blob:none`, which makes a clone **lazy rather than restricted**: blobs are absent until something asks, and then git fetches them from the promisor remote, transparently and permanently — measured 2026-08-29, an ordinary read of a non-governed path pulled a code blob into the store and kept it. So the store runs its git with **lazy fetching disabled** (`GIT_NO_LAZY_FETCH=1`), which turns that read into a refusal, and a test proves the refusal. Anything that legitimately needs content outside the governed set must then **ask for it explicitly**, which is the point: the footprint is bounded by the mechanism rather than by the discipline of every present and future call site. Resolving a `ref` outside the root is a tree lookup and needs no file content; the commit is built with plumbing (`hash-object` · a temporary index · `write-tree` · `commit-tree`) and `update-ref` carries the expected old value as the compare-and-swap. The store holds the rows, not the app; the forge's API was weighed as the alternative mechanism and declined (a driver per forge, a round trip per write, the forge's availability becoming the store's) — the forge seam stays the factory's (T-C7). **One store container per tenant** (round 7ba.6 — owner: *"b, one store per tenant. next"*): the deployment default for the owner's projects; the server is keyed by tenant namespace, so one server may serve several tenants where that is wanted later — not now is not never; the factory holds one client channel per tenant from its registration (address, pin); cross-tenant `tenant:<t>/<id>` pointers stay `see` (log, need not resolve). It commits governed writes to `main` under the store's identity, authored on behalf of the caller (author = caller, committer = store — pinned at build). The tenant's container, the factory's container (`lander`), the planner and the owner's workstation are **clients** over a channel pinned in the tenant registration (mTLS; realm credentials). The signer stays in the owner-only zone — **the store never holds a ratifier key** (1.12). Consequences: two versions of a governed file can never meet in a merge, so there are no merge drivers and no merge tool; CI refuses governed-path diffs on any branch but `main` as a belt; the tenant's pre-commit hook reduces to one check — a governed path changed here? refuse, that is not where those change; CI and ingest reconciliation (9.6) query the store; **the tenant repo holds data and policy only** — `cards/`, `state.json`, `state/history.jsonl`, `suggestions.jsonl`, `config.toml`, optionally `BOARD.md` — and **the tenant container holds a thin client and that hook**. Extrication of development plumbing from tenants is therefore done on day one; the sartor and spolia sequence becomes "point the container at the store, install the client" (section 3). This supersedes V4's placement of the store inside the tenant's container (round 44); the identity boundary is the container. The harness-injected session credential carries the `contributor` grant, never `owner`.

### 1.4 Sidecar: the vendored ledger snapshot, history-complete — **[owner-ratified 2026-08-16]** ("option A but we have to be careful that this does not lose history on edits. Git maintained of course.")

- **Two files, from day one** (W8): `state.json` — the **current** state per card (fingerprint, history head, runs' latest, closures' verification) — and `state/history.jsonl` — one append-only line per event (`events[]` of section 6). The land commit on `main` shows every landed change in one diff (X2 — the batch PR carries code only); the renderer and `check` read the current file only; nothing is O(total history) on the common path.
- **The land is a store write on `main` after the merge (X2 — round 7ba, owner: *"A with the three pins."*).** The batch PR carries code only; its merge stays the forge's button (round 14); the merge commit is the ledger cursor; the factory observes the merge through ingest's `cursor..HEAD` walk (9.5) — **no human step between merge and land** — and the store lands the sidecar, the inbox intake and `BOARD.md` as its ordinary commit on `main`. The owner's question that produced the pins, verbatim: *"if we do A, then what happens if the merge to main happens and the scond write event for state.json etc never happens"* — three pins: (1) **a named state** — while the cursor is behind `main`'s merge commit, the factory-side projection shows `closed (pending-land)` (1.5, ledger-only) and the queue carries "merged, not landed: N"; (2) **fail-closed** — the cursor does not advance and the next batch on that tenant does not dispatch while a land is pending; land is idempotent and replayable (section 6) and a half-land replays from the journal (03b); (3) the merge is observed, never reported — the walk of 9.5 is the trigger.
- **Monotone against the ledger's cursor, not the working tree** (F7): a hand edit or a replay is a governed-file transition the journal does not explain — `integrity:unjournaled` — and the lander overwrites it; a shrink relative to the last land is `land.shrink`. `landed_at` = the cursor commit's time, so a re-land of the same cursor is an empty diff (G11).
- Per card the snapshot carries the **history head** — `{seq, h}` of the card's last history entry as of the land (1.15) — and the tenant's **journal head** (03b). No full mirrors anywhere: the chain makes the prefix pointer sufficient and the journal holds every transition.
- **Nothing sensitive lands here** (round 34). Net property: everything the factory ever landed for a tenant is in the tenant's own git; the factory can be discarded without the project losing its own history (section 8).

### 1.5 The state split — the card's `status` is the owner's; done-ness is the sidecar's — **[owner-ratified 2026-08-16]** ("copy on doneness and sidecar. on the same page. so long as this never creates a dependency of development on the factory for the project (sartor/spolia/anything)"); the factory never writes a card **[round 27]**

`show Card(id)` and the board render the merged timeline — the card's `## History` (tenant acts) interleaved by time with `state/history.jsonl` (factory acts). Two records, two writers, one view; neither copies the other.

| Vocabulary | Values | Home |
|---|---|---|
| **card `status`** (owner intent) | `draft` · `ratified` · `closed` (a human closure claim) · `withdrawn` | card head; more-active moves and confirmations carry `sig` (1.2, 1.12) |
| **execution status** (line state) | `dispatched` · `parked` · `answered` · `failed(class)` with `class ∈ {scope, ambiguity, budget, timeout}` · `complete` · `closed` · `reverted` · `disputed` · `reopened` | `state.json` (from the ledger), `lander` only |
| **projected label** (never stored) | owner status × execution status × **one modifier** — `pending-ingest` · `pending-review` · `pending-land` (†, X2) · `integrity(reason)` — plus the readiness guards | projection (T-A3/A4) |

**Projected status — eleven rows, precedence top to bottom** (W9; T7, U7, U9, V7; round 6: `claims-drift` retired into row 1, `closure-invalidated` into the `pending-ingest` modifier). One function, two inputs (T7): the factory-side renderer reads the live ledger; the in-project renderer reads (cards, `state.json`, `config.toml`); rows marked † need the live ledger and fall through in-project. **Container roll-up** is evaluated after row 3: a container showing row 1–3 shows that; otherwise `closed` when every member is terminal and there is ≥ 1 member; zero members → `ratified` unless the container is held or has questions; head `closed` with a non-terminal member → `disputed`; mixed members → the most actionable member label by this order.

| # | Label | When |
|---|---|---|
| 1 | `integrity(reason)` | any integrity reason (1.15) — blocks dispatch; rendered with the reason |
| 2 | `unratified` | `status ∈ {ratified, closed}` and the working-tree build hash ≠ the reference hash — the fingerprint when one exists; standalone, the `build` of the last **verified** `ratified` entry (H7); `unknown` when there is neither (pre-`git init`) |
| 3 | `withdrawn` / `withdrawn (pending-review)` | `status = "withdrawn"`: final when the `withdrawn` entry carries `sig` or the card was a draft (replay of the status acts before it); pending otherwise (U9) — off the ready-view, reversible by a signed `unwithdrawn`; in flight, a pending withdrawal holds the merge, only a signed one discards |
| 4 | `draft` | `status = "draft"` (sectioned by `source` / `hold` / `tags`) |
| 5 | `disputed` | a human claim contradicted by verification, or `met` claimed with red verdicts |
| 6 | `closed (pending-review)` | the newest closure is `deviated`, unsigned, and no signed `accepted` entry's `ref` names it (U7) — **not terminal**; in the queue |
| 7 | `closed` · `closed (pending-ingest)` · `closed (pending-land)` † · `closed (unverified)` | factory `closed` with the sidecar's newest closure `verified_against == build hash`; a human claim on `main` not yet ingested; factory `closed` whose batch PR merged and whose land is not yet on `main` (X2 — the cursor is behind the merge commit; ledger-only); a validated claim under the standalone dial (S7) or after the owner's signed `accepted` |
| 8 | `reopened` · `reopened (pending-ingest)` † | execution `closed` but the build hash moved (landed → `reopened`; un-landed → `reopened (pending-ingest)` — the card already carries the `reopens[]` entry the validator requires) |
| 9 | execution status | `complete` · `reverted` · `parked` · `answered` · `dispatched` · `failed(class)` (`complete` = run finished, batch not merged) |
| 10 | `has-questions` · `held(kind)` · `held_by(parent, kind)` · `blocked_by[ids]` · `deferred_by[ids]` · `below_threshold` | the readiness guards — **`has-questions` before `held`** (W5); a card blocked by a pending-review or pending-withdrawn dependency is `blocked_by` it |
| 11 | `ratified (pending-ingest)` · `ready` · `ratified` | the newest signed entry post-dates `landed_at` (document-based); in the ready-view; none of the above |

`terminal(card)` is defined once over projected labels — `closed`, `closed (unverified)`, final `withdrawn`, `reverted` — and used by the container roll-up and the batch drain predicate (G7). Pending-review and pending-withdrawn cards are not terminal and are `held`-equivalent for their dependents. Human `closed` on a card the factory already closed → a note at ingest, never a second closure (F14).

**Legal `status` transitions** (F15; T2–T4, U7, U9, U12, V8, W3, W5 applied):

| From → To | Who | Rule |
|---|---|---|
| `draft → ratified` | `owner` (signed) | profile passes; `questions` empty is required to be *ready*, not to ratify |
| `ratified → draft` | contributor (`demoted`) | in flight → `complete-but-demoted` event |
| `draft → withdrawn` | contributor, final | `withdrawn_reason` required |
| `ratified → withdrawn` | contributor → pending; `owner` → final | off the ready-view at once |
| `withdrawn (pending) → ratified` | `owner` (signed `unwithdrawn`) | same id, anchors intact |
| `ratified → closed` | contributor (claim) | `met` terminal on verification; `deviated` pending review |
| `ratified → closed` | `owner` (signed — the caller-aware clause, 1.2; the store fills `ref`) | terminal on the spot |
| `closed (pending-review)` → terminal | `owner` (signed `accepted`, `ref` = the closure) | declining = a signed `reopened` entry returning the card to `ratified` with the claim retained |
| `draft → closed` (record-only, T2) | contributor (claim) | only `deviated` with a `description` ⇒ pending review; `withdrawn` stays for won't-do |
| `closed → ratified` after the closure landed | `owner` (signed `reopened`) | `reopens[]` entry naming the card-side closure (T3) |
| `closed → ratified` before any land | contributor (`retracted`, unsigned — exempt from the more-active clause, 1.2) | `closures[-1].retracted = true`; no `reopens[]` entry |
| `hold` set (any kind); re-kinded `blocked ↔ deferred` | contributor (`held`, unsigned) | any card not `closed`/`withdrawn`; the safe direction |
| `blocked`/`deferred` hold cleared on a ratified card | `owner` (signed `released`) | the Andon asymmetry (T4) |
| `watching` hold cleared; any hold cleared on a draft | contributor | V8, U12 |
| confirmed `withdrawn → *`; `closed → withdrawn` | — | forbidden |

**Reopen without a status flip** (a factory-closed card whose file still says `ratified`): a signed gated change to a card whose sidecar says `closed` **is** the reopen; the validator requires a `reopens[]` entry naming that closure. **Retry without change** (F15, G8): `factory retry <tenant>/<id>` writes an owner ack that lands as an `acked` event and clears the failed-attempt block for one dispatch.

**The queue section (rounds 35, 37, 47).** Owner, verbatim (round 35): *"yes and include these in the dashboard and morning review"*. The board, the dashboard and the planner's invocation report open with what the next sitting's one signature will clear: open questions · `blocked`/`deferred` holds on the owner awaiting release · closures pending review · withdrawals pending · cards blocked by any of those · the planner's dispositions since the last batch signature · the inbox counts by source · **merged, not landed: N** (X2 — batches whose PR merged and whose land is pending; dispatch on the tenant is closed until it lands).

### 1.6 Ids — from the store's counter; never reused — **[owner-ratified 2026-08-16; round 49]**

- `id` = integer, one namespace per tenant for every kind, immutable, never reused; allocated by the store inside the creating `write` (`NewCard{slug}`, 1.2) from its counter (the store is the sole writer, so allocation is a field, not a scan — W1); a refused creation burns an id — allocation precedes validation, and a burnt id is never reused. Drafts have ids (1.1). Bridged cards take fresh ids; the legacy id lives in `see = ["legacy:<tenant>/<id>"]` (section 3).
- **Repair (F8, G6):** `id.unique` over the whole set runs under `check` (CI, on the merge result), never inside `write` — the counter is authoritative; a duplicate that reaches `main` is repaired by `repair`, run by the owner (signed): the later card is renumbered to the next free id with `renumbered_from = <old>` (log, set once); its chain continues under the new genesis from the `repaired` entry on (5.5); the factory refuses dispatch until the repair lands.
- Greenfield: first id `1`; standalone dial until factory mode; `init` installs the thin client, the hook, the default `config.toml` and the registry schemas locally (03b).

### 1.7 The five classes and the one gating criterion — **[owner-ratified 2026-08-17 (S9)]**; `scope_mark` gated **[round 36]**; `needs` removed **[round 53]**

**Criterion:** a field is **gated** if changing it changes *what is built*, *what the validator requires*, or *the dependency structure*; **claims** if it asserts an outcome (closure, reopen); **tending** if it is a scheduling preference; **log** if it is an append-only record that must never steer the build; **execution** if the factory derives it from the ledger. Identity plumbing (`schema`, `id`, `status`, `source`) is **meta** — `kind` is hashed (S9), `schema` is the hash prefix, the rest are not. Every field is exactly one class; the extension schema may declare only gated or tending fields, plus append-only log lists (7).

- **Gated** → build hash · payload · drift · re-ratification: `kind`, `shape`, `narrative`, `rules`, `questions`, `answers`, `parent`, `depends_on`, `goal`, `effort`, `scope_mark`, `source_narrative`, `refs`, `surfaces`, `acceptance`, `guidance`, gated `x.*`, `title`, `## Scope`. **`scope_mark` is gated** (U8) — it records whose words the Scope is and exempts `narrative` under 1.11; the owner's sourcing discipline reads it (kept against the round-5 refuter, W9).
- **Claims** (S1) — `closures` (a list, T3), `reopens`; **never in the build hash**, so a claim never moves the hash the acceptance suite ran against; no whole-set claims hash exists (round 6 — nothing consumed one). A judging entry (`accepted`, the owner's `closed`, `reopened`) binds the one closure it judges through `ref = "c<n>:sha256:<hash of that closure entry>"` (W6 — round 54: *"yes."*; the bytes in 5.2); an edit to a landed closure or reopen entry is refused inside `write` by the append-only rule and, outside the store, is `integrity:tampered` (1.5 row 1) — never decided by a hash.
- **Tending** → validated, un-hashed, not in the payload: `priority`, `class_of_service`, `due`, `sprint`, `milestone`, `starts`, `ends`, `lane`, `tags`, `hold` (set; clear per 1.8), `summary`, `withdrawn_reason`, and status moves toward less active. `tags` is never an input to a readiness rule (F12). Relations some tending keys name reach the builder through the neighborhood projection (1.17).
- **Log** — closed membership: `## Updates`, `## History`, `see`, `renumbered_from`, plus tenant extension lists declared append-only. Append-only checked once, inside `write`'s derive function, on every structured call; CI and ingest run the same function and see a violation only as `integrity:tampered`; the hook does not run it (9.2); `## History` is computed by `write` only, chained, recomputed, journaled, hard everywhere (1.15). Owner's warning, verbatim (round 20): *"prvent a future llm seeing free and packing that class (personal experince of llms leveraging looseness to catch and stash what they can't elsewhere)"* and *"it should remina append only though. we don;t want altered cards losing provenanve and history."* — closed membership, no "misc", unknown top-level keys rejected.
- **Execution** → the sidecar only (section 6).

### 1.8 Kinds, relations and holds — **[owner-ratified 2026-08-16; S8; rounds 24, 39, 48, 53]**

*Scope axis — `kind` + `parent` (gated).* Fixed-core kinds **`epic`** (grouping; never dispatched) → **`story`** (the dispatchable unit; bugs, chores, spikes and research are stories — `shape` says how they are written). Optional ladder levels are tenant-declared in `config.toml` and typed as `Kind::Ext(name)` (W10); the ladder check is "parent is exactly one level up". Members of a container are always derived. A draft container is a legal parent.

*Cadence axis — `sprint` (tending).* Owner, verbatim (round 21): *"i wonder if we even need sprints. let's keep them as they will be useful to the crowd on those cyeles, but i suspect we will not and will be ona rolling flow. and use stories and epics and milesontes but seldom sprints. good to have for others and in case we find need."* — `sprint` and `milestone` are **tenant-enabled profiles, off by default** (S8); a sprint card (`kind = "sprint"`, `goal` = the epic or milestone that drains it) binds to a **batch** (a ledger record, `batches{}`); `batch_boundary ∈ {epic (default), milestone, sprint, on-demand}`; batch lifecycle beyond that is T-C3's, using the single `terminal` of 1.5.

*Relations:* `parent` (scope, gated) · `depends_on` (sequencing, gated) · `sprint` / `milestone` (tending) · `see` (log — informal pointers, the bridge's `legacy:` and cross-tenant `tenant:` pointers). A binding to an unratified card is `relation.unratified-target` — hard for `parent` / `depends_on`, advisory for `sprint` / `milestone`.

*Holds — the only parking besides questions* (S3; T4; U12; V8; W5 — round 53: *"yes."*). `hold = { kind, on }` with `kind ∈ {blocked, deferred, watching}` and `on` a typed value: `{ owner = true }` (the hold is on the owner), `{ card = 3 }`, `{ legacy = "sartor/39" }`, or `{ text = "…" }` (W10 — a discriminated shape, never a string with a grammar inside); `on` optional for `watching`. **Setting** a hold is tending. **Clearing** is three-way: `blocked`/`deferred` on a ratified card only by the owner's signed `released` (the Andon asymmetry); `watching` by any contributor (legacy "watching" meant *anyone may pick this up*); anything on a draft by anyone. Re-kinding `blocked ↔ deferred` is neither a clear nor a relaxation: `held`, unsigned (round 6). A held ratified card is not ready; **container holds propagate** (`held_by(parent, kind)`) and release with the container. `needs` is gone: "waiting on the owner" is `hold = { kind = "blocked", on = { owner = true } }`. `questions[]` (1.11) is the other parking — a specification gap, gated.

### 1.9 The memory tier — **[owner-ratified 2026-08-16]** ("land it") — schema obligation only

T-B12 owns the tier. This doc's obligation: every record has a **stable citation anchor + a sha** — card id, scenario id `S<n>`, rule id `R<n>`, question id `Q<n>`, closure id `c<n>`, reopen id `o<n>`, suggestion `s<n>`, disposition `d<n>`, event id `e<n>` (section 6), run id, batch id, Updates anchor `#u<n>`, history entry `#h<seq>`; build hash, the closure-entry hash (`ref`'s form, 5.2), `h`, journal hash, commit, cursor. The integrity reasons of 1.15 are indexed — *"if there is a conflict, we need to understand why"* (owner, round 24). The bridge's archives are indexed as-is (section 3). No `audience` field on cards.

### 1.10 Builder guidance — **[owner-ratified 2026-08-17]**

Owner, verbatim (round 21): *"so where does the planner and anyone else put information that is important to the agent buiding this code that isnt in the short fields. thigs like known risks, options to avoid with becauses, etc. If it isnt handed to an agent, it will be ignored. if it is handed to an agent often it is ignored."* — that information is **gated**: hashed and in the payload. Two homes: prose under `## Scope`, and typed guidance in the head, addressable by id:

```toml
[[guidance.avoid]]
id = "A1"
option = "adding a second SSH connection per file"
because = "spolia's first publish opened 3 connections per file; batch and reuse"

[[guidance.risks]]
id = "R1"
risk = "the vendored validator diverges from the factory hasher"
mitigation = "run both against the conformance fixture corpus"

[[guidance.constraints]]
id = "C1"
text = "stdlib only inside the client"
because = "the client must run in a tenant's CI without a venv"
check = { kind = "command", action = { run = ["python", "scripts/check_stdlib_only.py"] }, observable = { exit_code = 0 } }
```

The plan's traceability matrix must reference every `avoid` and `constraint` id (T-B4); reviewer findings cite guidance ids (T-B6) — a presence check (declared limit L2). A `constraint.check` is a scenario-dialect check the close gate runs (4.4). What a builder learns and wants the tenant to know goes back as a **suggestion** (1.18), never as an edit to a card.

### 1.11 Story shapes — a tenant-allowed set, chosen per card, enforced once chosen — **[owner-ratified 2026-08-20 (rounds 23–25)]**

Owner, verbatim (round 23): *"We should have options for story shapes. selection of what type this tenant prefers (story shape, BDD shape, etc.). Research the options that are industry standard and make them options for enforcement for the card writing agent. For Take Tempo Projects, we will use a BDD template. do not just accept this. Show me the options in shapes, which you think should be in the templates, and whether you see a challenge to using a BDD shape for Take Tempo projects."* The research (`../research/story-shapes-2026-08-20.md`) found the resolution: **shape is enforced on typed head fields, never on prose**. Round 24, verbatim: *"i like the tempates and planner chooses without enforcement on shape. my concern is how ot ake sure the planner asks the right questions so that the builder understands expectations. we've run into this miss on several occasions because the details were never sourced and assumed at each level."*

- **Choice is the planner's:** `shape ∈ shapes.allowed` (a closed enum with `Shape::Ext(name)` for tenant-declared shapes — W10); `shapes.default` applies when unsaid.
- **Conformance is enforced** by `write` and `check`: the shape's layer rules below.

`shape` and `narrative` are one discriminated shape (W10): `Bdd { feature, as_a?, i_want?, so_that? }` · `Ears { system }` (required regardless of `scope_mark`) · `Classic { as_a, i_want, so_that }` · `Task` · `Spike { question, timebox: Sessions(n) | Iso8601(d), deliverable: path }` · `Ext(name, table)`. `narrative` is optional when `scope_mark = "owner"` except `ears.system`. `rules = [{id: "R<n>", text}]` (gated); `questions = [{id: "Q<n>", text}]` (gated); scenarios may bind to a rule (section 4).

| Shape | Rules | Scenarios | `check` adds |
|---|---|---|---|
| `bdd` | optional groups | ≥ 1; rendered as Given / When / Then from `context` / `action` / `observable` — never stored twice | every rule has ≥ 1 scenario |
| `ears` | required; each `text` matches exactly one of `The <system> shall <response>` · `While <state>, the <system> shall …` · `When <trigger>, the <system> shall …` · `Where <feature>, the <system> shall …` · `If <trigger>, then the <system> shall …` | ≥ 1 per rule | a grammar: case-sensitive keywords; non-greedy split on `, the `; subject = `narrative.system` NFC-casefolded; whole-word case-insensitive weak-word list (`should`, `may`, `quickly`, …); optional trailing period |
| `classic` | checklist sentences | ≥ 1 | all three narrative fields non-empty unless `scope_mark = "owner"` |
| `task` | optional | ≥ 1 | nothing beyond the story profile |
| `spike` | — | ≥ 1, typically `file-assert` on the deliverable | `deliverable` under `surfaces`; `surfaces = []` is legal exactly for `spike` / `task` with the deliverable inside the card |

Ship those five; `job` is a documented tenant extension. Declared limits (v1): Gherkin `Scenario Outline`, `Background`, tags, doc-strings are not carried; no Cucumber tooling — the kinds are the executable binding.

**Sourcing — the owner's concern.** `questions[]` is the planner's sanctioned "I don't know": a card may be ratified with open questions but is never ready while any remain. **A question leaves only by being answered:** `write` checks, over (before, after), that every removed `questions[].id` appears in an added `answers[].question_id` — `questions.dropped-unanswered`, refused inside `write` (once; the outer gates see only `integrity:tampered`/`unjournaled` — W9); the rule binds cards with a prior signed entry — a draft's author may delete its own question. An answer is a gated change → re-ratification at the next sitting, riding the batch as a `WriteRequest` (X1, 1.12); for every member with a prior signed entry, the dry run and the signer display show the diff against the last signed build with removed questions and new answers first, **then the tending and hold changes since that entry beside the gated diff** (X1's display pin — a cleared hold is shown as a release whichever path it took), non-ASCII escaped. "Changes since that entry" is two lists (closing check C1): **(a)** the state diff of the tending keys against the last signed document, and **(b)** the entries since that entry whose act is `held`, `released` or `demoted` — `seq · act · fields · by · at`, read from the footer, no old blob — so a hold set after the signature and cleared on the demote path appears as `held → released`. **A parked card is parked until the owner responds, by whatever channel exists** (round 43, 1.12). `traces` stays optional (owner, round 20) with per-card untraced-count telemetry. The interview protocol is the per-phase roster's; this schema hands it the shape's required fields, the morning review and the dry run.

**The BDD-for-Take-Tempo challenge, recorded:** BDD fits observable behaviour and not refactors, spikes, migrations or infra; the default config allows `bdd`, `task`, `spike` with `bdd` default; `ears` for pipeline/infra tenants. **Re-authoring guidance for the bridge:** legacy decision items re-author as `spike` with `surfaces = []`, never as a story with fictional acceptance. INVEST is borrowed only where mechanical: Testable = ≥ 1 runnable-shaped scenario (T-A2 rule 3); Small = the payload fits the budget (T-B3); Independent = `depends_on` acyclic (T-A5a); Estimable = `effort` resolvable; Valuable / Negotiable = owner judgment (declared gap).

### 1.12 Ratification authority — grants, the sitting, the signature, the signer — **[owner-ratified 2026-08-20/21 (rounds 24, 32, 33, 42, 43, 45, 48, 50, 51, 57, 58)]**

Owner, verbatim (round 24): *"humans and agents should follow the same rules here with only one human (me for these projects) having the authority to over-ride ratifiaction etc. If other humans contribute, they should follow same rules as agents. enforcement by design with only product owner able to over-ride"*.

**Grants and agents — two words, never "role" (W9, round 57).** Owner, verbatim: *"1. let's be aure that thos eare named i  clear, undrstandablew ways of what they are and how they are different. easier for grepping files as well."* — the store's permission sets are **grants**; the roster's kinds are **agents**; the binding reads `agent → identity → grant`. An agent has a prompt; a credential holds a grant; the builder holds none.

| Grant | May call |
|---|---|
| `owner` | everything; every signature-requiring write (1.2); `config-policy`; bindings in the realm |
| `contributor` | `write` on drafts, tending and claims; `suggest`; `show` (every target, the inbox included) and dispositions *with the owner* (round 28); `accept`; `check`; `ratify --dry-run`; no signature-requiring write |
| `lander` | `land` only — the sidecar, suggestion intake, the board |

The builder has **no store credential** — code inside `surfaces`, a typed report (suggestions ride in it). Finer grants — a reviewer that may `suggest` but not draft — are isidium G7's to split, with the per-phase roster enumerating each agent's grant; not now is not never.

**The flow, as occasions (V3, round 43).** Owner, verbatim: *"i thought it needed my signing with the planner at the point of ratification. so i can plan a ilesonte flow or a sbody of work and it gest processed into a plan and we digest that into individual cards (as we did the board) and then it asks, are you ready to ratify these cards. i say yes, i sign it does the ratification, the cards are daved and i'm done until they've landed unless something goes wrong. what else do i need to sign on except VERY RARE exceptions that overrde flows"* — that is the flow:

1. **Planning sitting.** Owner and planner take a body of work → a plan → cards. The planner sources details in the conversation; what is still unanswered is a `questions[]` entry. Holds to lift are part of the digest.
2. **The dry run (round 48).** Owner, verbatim: *"to avoid discovering a flw issue later. we should be able to runa  test ratify session o cards without owner signature before the signoff so we have the opporuntity to identify and solve issues in a design session rather than discover them at ratify time for the first time. this way the agent can run a quick check to see if cards ae going to throw issues as written before prresenting them for signature and final ratification as a batch"* — `ratify(writes, dry_run = true)` is the same function without the signature and the write: per-card typed verdicts (the profile cells, shape rules, `surfaces` disjoint from the root, `refs` resolve, acyclicity, readiness, the build hash — 0 build hashes on a warm blob cache, N cold, 9.4) and the exact display the signer would show (card · act · **build hash**, and for every member with a prior signed entry the tending and hold changes since that entry beside the gated diff — X1's display pin, the two lists of 1.11). The dry run diffs the same documents the sitting signs. `questions` non-empty is advisory for ratification, blocking for ready. The sitting's question is asked only on a clean dry run. **Gate-rejection measures [owner-ratified 2026-08-27 (7be.3)]:** the dry run's failure and decline counts persist as measures (I-31: emit the measure) — a gate that never rejects is decorative, and the verdicts already exist (`../research/isidium-review-2026-08-27.md` §3).
3. **"Ready to ratify these N cards?"** — yes → **one call, one signature** (W2, round 50; X1 — round 7ba, owner: *"b with the display pin. next"*): **`ratify(writes: [WriteRequest], dry_run)` with `WriteRequest = {path, document, base, ref}` — the sitting's batch is a list of typed writes under one signature**; `ratify(ids)` is the shorthand for "these, `status → ratified`, otherwise unchanged". It is one store transaction — the store takes the row locks, runs each request through `write`'s steps 1–3 (the per-member `act` still derives from the recompute table), composes the N entries with its own `at`, presents the batch to the signer, and writes on success; a `NewCard{slug}` request may ride the batch — the transaction allocates the id and the `created` member carries `batch` like any other, so a card born `ratified` costs no signature of its own (C4); a request whose diff needs no signature is refused (`ratify.not-a-signed-act`) — an unsigned write is `write`'s (C7); `time_skew` is sized for a human (minutes); a timeout recomposes and re-presents. Ratifications, hold releases, answers, accepted closures (with `ref`), withdrawal reversals, guidance edits and re-ratifications ride the same batch as `WriteRequest`s; the planner composes them, the owner signs once.
4. **Done.** The factory dispatches unattended, runs acceptance mechanically, **closes `met` cards itself — no signature**, opens the batch PR (code only); the PR merge is the forge's button (round 14); the store then lands into the sidecar and drops suggestions in the inbox on `main` (X2, 1.4).
5. **Exceptions — rare, and they ride the next sitting's batch as `WriteRequest`s (X1):** a parked question; an agent's `deviated` closure; a reopen, repair, withdrawal reversal, policy change.
6. **Morning review (1.18)** reports the queue (1.5); nothing pending, nothing to sign.

**Parked means until the owner responds — by whatever channel exists** (round 43). Owner, verbatim: *"i actually would like to integrate this eventually with a slack-like tool so that those questions could be sourced to me over the course of the day. they are parked UNTIL i respond. if i respond, it can pick up and move on. that isn't being buol today, but it will be and you should be prepared for it."* and *"later we will have communication to unlblock these with questions, but your current proposal is good for now with the caveat that we will want communications as an option in the future."* Today the channel is the sitting; the catalog's interrupt row (T-C5, "answer channels by source tag") is the seam for a channel that sources questions through the day, on which an answer and its signature unpark the card immediately. `answers[]`, the `answered` act and the signer seam are channel-agnostic.

**Where authority lives (U5, round 33).** Owner, verbatim: *"does creating a unique identity in an authentication system (as we are building on agent station) satisfy this? each agent is acting as a unique idntifiabe agent with permissions and authorizations? i want to move to this for all applications (if agent dentity is enabled). i believe we've already noted this in either sartor or spolia. i don;t recall"* — it is isidium's open **G7** and spolia's **O-116**; this doc is G7's first consumer. `config.toml` names **grants, never keys**; the tenant registration (factory-side, out of the repo) names the identity realm, the signing service's address and TLS pin, and the ratifier fingerprint. Who holds `owner` for a tenant is a **binding** in the realm with an append-only binding history, changed only by the product owner's own authenticated act there. **The binding is one record in the policy chain** (W8): a `binding` entry (`act = "binding"`, policy file only, 1.15) whose `ref = Binding{key_fpr, grant, tenant, from, until}` — `until` absent while the binding is open, never null (canonical JSON has no null) — signed by the realm with the same scheme as every other signature (`sign(realm ‖ h_binding)` — W10); a signed entry is verified by looking the key up at `(key_fpr, at)`; a past ratification is judged against the binding that held then; revocation is a binding entry, and entries signed after it are `integrity:unverified`. Verification works from the tracking root alone — the policy chain travels with it.

**The policy surface is signed (V5, round 45).** `config.toml` is a governed document: every change is a `config-policy` act whose entry lives in the file's own trailing `[history]` table (W8) and is signed under the **parent commit's** policy. No git-commit signature is part of the gate anywhere. An unsigned policy change does not take effect; an `[extensions]` reclassification without one sends the affected cards `unratified` (`ext-schema-changed`). When identity is disabled (a standalone tenant with no realm), `init` pins the ratifier key into `config.toml [ratification].pin` — its one home — as a `config-policy` act signed by that key; the pin must equal the registration's fingerprint when a factory is present, or the factory refuses dispatch.

**The signature (V2, round 42; W2, W6, rounds 50, 54).** Owner, verbatim (round 42): *"ths is the biggest complaint about llm code. bloated and slow because it writes too many things. 3 calls when one would have worked. focus on efficiency of construction and efficiency of execution"* — the chain hash `h` already binds the card, `seq`, `at`, `act`, `fields`, `build`, `ref` and the whole history before it, so:

- **`sig = sign(tenant ‖ h)`** — one value. `tenant` is the registered name (`[a-z0-9-]`, mirrored read-only into `config.toml` so standalone verification can form it); `‖` = the UTF-8 bytes of `tenant`, one `\n`, the bytes of the stored `h`.
- **Batch form** (V8, W2): the signer signs one value over the sitting's sorted chain hashes — `sign(tenant ‖ batch_hash)`, `batch_hash = "sha256:" + sha256("\n".join(sorted(h_i)))`. **The sorted member list and the one batch signature are written once into the policy chain** as a `batch-manifest` entry at signing — its keys: `by` = the signer's principal, `fields = []`, `build` = the policy build hash (5.1), `ref = Members(H)`, `sig` = the batch signature; every member entry carries `batch = <that entry's seq>` **only** — the member's signature is the manifest's; an entry carries `sig` iff it is singly signed. `sig` and `batch` are **outside the chain content** (5.5). Per-entry verification is two reads: recompute `h`, read the manifest, check its one signature. Document-only; the tarball test holds.
- `at` is the **store's clock**; the signer refuses a request outside its own clock ± `time_skew`. `seq` is the store's.
- **Format, one for every backend:** `sig = "<alg>:<key_fpr>:<base64>"` — `alg ∈ {ed25519, ecdsa-p256}`, `key_fpr` lowercase hex with no colons, standard padded base64. **Membership, not validity:** the ledger checks the binding, not merely that some key signed.

**The signer seam — the signer runs where the owner is, never where the store is (U4, V3, W10; rounds 32, 43, 58).** Owner, verbatim (round 32): *"i have no hardware key"* and *"1 & 2. i can use the windows TPM on this machine and I already use aegis on my phone. perhaps we can leverage that with the auth on the agent station to generate a code that constantly resets"*; (round 58): *"what do we do for signing when this is inside a linux container and moves to a linux box? is this wehere the 2fa/aegis connection comes in? will this work ina linux container on windows even? this signing needs multiple methods that we can set-up."* The requirement: each signature needs an un-cacheable act the session cannot perform, and **the thing the owner approves is shown by something the session cannot write to**. The store asks the signer seam for a signature over `tenant ‖ h` (or the batch hash) and gets bytes back; it never holds a key. Backends, a closed set with declared placement; the tenant registration names the allowed ones; at least one is configured; every signature records its backend:

| Backend | Runs | Second factor | Works from |
|---|---|---|---|
| `remote-totp` | a signing service in the owner-only zone (agent-station, by pointer) | **Aegis TOTP on the owner's phone** | anywhere — **the portable default**: the CLI submits `{tenant, hash, diffs}` and polls; the service renders card · act · hash · the diff *it received* in **its own UI** and takes the code **there**; each code consumed once, bound to its request; ±1 step; rate limits per caller identity; address and pin from the registration |
| `tpm-hello` | a client-side signer on the Windows workstation, under its own identity, with its own window (diff + a phrase derived from the hash) | Windows Hello on the secure desktop | only when the owner's CLI runs on Windows; **not** from a Linux container; signs via **CNG directly** — raw ECDSA-P256 over the value, no WebAuthn carrier (W10); labeled *presence-grade* |
| `yubikey` | a client-side signer wherever the token is plugged in | touch | Windows, a Linux box, a container with USB passthrough |
| `signal-approve` | the owner-only zone | a reply on Signal | anywhere, like `remote-totp` |
| `software_key_ack` | anywhere | none — a visible waiver, `ratification.software_key_ack = "<the owner's own words>"` | every such signature is labeled software-grade; **the factory refuses unattended dispatch of software-grade ratifications** unless the registration carries `allow_software_grade_until` |

**(c) Declared** — only where no key and no realm can exist: `ratification.mode = "declared"`; the board says "unsigned" on every ratified row.

**At each step:**

| Step | Who | The gate | Ingest's view |
|---|---|---|---|
| Draft written | anyone with `contributor` | validator only | never dispatched |
| `draft → ratified`; re-ratification; born `ratified` | `owner` | the entry carries `sig`, or `batch` naming a manifest that does, by a key bound to `owner` at `at` | recomputes `h`, verifies `sig` and the binding — **the gate bites here** |
| Closure / reopen claims | `contributor` | `deviated` waits for a signed `accepted` whose `ref` binds the closure's hash (W6) | append-only diff |
| `blocked`/`deferred` clear on a ratified card; withdrawal reversal; accept | `owner` | signed `released` / `unwithdrawn` / `accepted` | unsigned → refused by `write`; outside the store → `integrity:unjournaled` |
| Policy change | `owner` | `config-policy` entry signed under the parent's policy | unsigned → no effect |
| Standalone (no factory) | the client | `check --verify` verifies `sig` + the binding (or the pin) in CI | no ledger — honesty label only |
| Land | the ledger | — | the only place authority is *decided* |

### 1.13 Standalone acceptance and close — `accept <id> [--close]` — **[owner-ratified 2026-08-17 (S7); T8; round 35]**

`accept` compiles the card's acceptance block to the manifest (T-B2), runs it through the tenant's runner bindings (pytest, shell, http, file — the defaults bind all four), prints per-scenario verdicts, and writes nothing inside the tracking root. It refuses a card whose current build hash has no verifiable ratification signature (a planted draft's `command` scenarios must not run in the owner's shell; `--unsafe-draft` prints each command and asks). `--close` is one `write` that appends a `[[closures]]` entry (`kind = "human"`, the verdicts, `c<n>` = last + 1) and derives `closed`. Verdicts are required in factory mode, optional under the standalone dial (G13). Owner, verbatim (round 35): *"i am the only contrbutor, who else would sign?"* — the non-ratifier contributors are the agents in the owner's session; a `deviated` closure without the owner's signature waits for it; `met` closures need no one. Only-manual cards close by a human closure or by factory close after a `policy` attestation when `acceptance.manual_attestation = "interrupt"` ([proposed-default]).

### 1.14 Refs, surfaces, and `see` — **[owner-ratified 2026-08-17 (S5)]**; grammar pinned (G10, H11, H21, W10)

- `refs` (gated) — read-only context for the specification; a discriminated shape (W10): `Path(p)` · `Lines{p, l1, l2}` (1-based, inclusive) · `Anchor{p, a}` (an explicit `{#id}` or the GitHub slug: lower-case, spaces → `-`, other punctuation stripped, an em/en-dash collapses to `--`) · `Symbol{p, s}` (a textual unique-definition search at `base_sha`; ambiguous ⇒ `ref.ambiguous`) — written as `"p"`, `"p:12-14"`, `"p#a"`, `"p::s"` (the symbol form takes `::`, so `p:12-14` is unambiguous). Must resolve at ratification; order hashed as written; may point at the legacy archive; never inside the tracking root. `refs_resolved` (the blob per ref) is recorded in the fingerprint, and a differing blob is `ref-drifted` — one name: ingest emits it as an event so the board shows it; dispatch re-checks it as its own precondition under the same name (9.5).
- `surfaces` (gated) — required on ratified stories: gitwildmatch globs the story may **write**; the write guard's ceiling (T-B5) and the overlap guard's input (T-A5b); the plan's touched surfaces ⊆ `surfaces` (T-B4). `surfaces` never intersects the tracking root (`surfaces.intersects-tracking-root`, hard); batch-PR CI fails on **any** tracking-root change — the batch PR carries code only; the sidecar, `BOARD.md` and inbox intake land on `main` after the merge (X2, 1.4). **The deny-set [owner-ratified 2026-08-27 (7be.2)]:** `surfaces` is also refused when it intersects the default deny list — forge workflow dirs (e.g. `.github/`), hook paths, the vendored validator/toolkit, config-adjacent scripts — by the same mechanism as the tracking-root refusal (`surfaces.intersects-deny-set`, hard): an in-scope diff must not be able to rewrite the gates that judge it — the builder's half of living-off-the-land (`../research/isidium-review-2026-08-27.md` §2). The list is a config key (`[surfaces] deny`, 04 §2.2); a per-card explicit override exists, and the dry-run/signer display shows the override before signing. `surfaces = []` is legal under `spike` / `task`. Shared globs count as overlap (advisory co-dispatch conflict).
- `see` (log, append-only) — informational pointers that need not resolve: `"RELEASE_ARC.md step 17"`, URLs, `legacy:<tenant>/<id>` (renders **(was N)**), `tenant:<t>/<id>` (cross-tenant — `external_ref` merged here, W8), `s<n>` (the suggestion a card came from).

### 1.15 History is the document's own record — **[owner-ratified 2026-08-20/21 (rounds 24–26, 29–31, 41–42, 50, 54)]**; format [proposed]

Supersedes review S12 ("timestamps and attribution come from git") and the round-21 drop of `ratified_ref`, both reopened by the owner's round-24 challenge, verbatim: *"this makes us git brittle. in the entire design, a corrupt or damaged git means all history is lost. we gamble that no rebase, git issues, etc. will ever happen. think through this and how every touch is recorded in other projects of who acted where when in multiple memory forms. if we have a tenant that uses any non-git source management, memory will have no access to this kind of history in the documents. also, we are sourcing relations in different forms of memory. if there is a conflict, we need to understand why. without this sort of information, we lose information about the system's behavior. think this through and come back to me with thoughts"* — and the ruling, verbatim: *"and never editable always appended for the writes on the history. created by: x @ timestamp amended by w @ timestamp. a stack of history of who edited when. not usre of cleanest way to do this or if there is an industry standard."*

**Four witnesses.** The **document** (travels with the file; complete without a factory), the **journal** (03b; the store's write-ahead record of every transition, outside the repo), the **ledger** (authority for factory facts; holds the history heads and the journal head at every land), **git** (corroboration). Agreement is confidence; **disagreement is one integrity reason** (the closed enum, W9): `tampered` (the chain or the recompute fails) · `unjournaled` (a governed-file transition the journal does not explain — V6) · `rewritten` (a landed prefix changed) · `unverified` (a signed act whose `sig` or binding does not verify) · `attribution` (git author ≠ entry `by`/`for`) · `time` (`at` non-monotone). A card showing one is `integrity(reason)` (1.5) and blocks dispatch. `attribution` and `time` never fire alone when the journal is present — a bypass is already `unjournaled`; they are the git-only and document-only belts for the non-git and tarball cases (L5). The memory tier indexes them. **The tarball test:** export the tracking root with no `.git`; every card's who/when/what must reconstruct from the documents plus the sidecar plus the journal.

**The stack — the `## History` footer.** One entry per write, one inline table per line:

```toml
history = [
  { seq = 1, at = "2026-08-20T14:02:11Z", by = "amodal1@example", act = "created", fields = ["scope", "shape", "surfaces", "title"], build = "sha256:3f9c…", h = "sha256:a1b2…" },
  { seq = 2, at = "2026-08-20T15:10:40Z", by = "sartor-planner@agents.example", for = "amodal1@example", act = "amended", fields = ["acceptance", "surfaces"], build = "sha256:ab12…", h = "sha256:c3d4…" },
  { seq = 3, at = "2026-08-20T15:12:03Z", by = "amodal1@example", act = "ratified", fields = ["status"], build = "sha256:ab12…", h = "sha256:e5f6…", batch = 412 },
  { seq = 4, at = "2026-08-22T09:00:00Z", by = "sartor-planner@agents.example", for = "amodal1@example", act = "closed", fields = ["closures", "status"], build = "sha256:ab12…", h = "sha256:0718…" },
  { seq = 5, at = "2026-08-23T09:30:00Z", by = "amodal1@example", act = "accepted", fields = [], ref = "c1:sha256:77aa…", build = "sha256:ab12…", h = "sha256:9a9b…", sig = "ed25519:9f3a…:…" },
]
```

| Key | Type | Meaning | Written |
|---|---|---|---|
| `seq` | int | 1-based, dense, == position in the array; continues across a `repaired` entry | the store |
| `at` | string | RFC 3339, UTC `Z`, seconds; ≥ the previous entry's (`integrity.time`) | the store's clock; checked by the signer ± `time_skew` |
| `by` | string | the store's authenticated principal (email-shaped, lower-cased, NFC); if git's author differs, `by` stands and ingest emits `integrity:attribution` | the store |
| `for` | string? | the principal acted on behalf of (PROV `actedOnBehalfOf`); absent when the owner runs the client directly | the harness that injected the credential |
| `act` | enum | `created` · `amended` · `ratified` · `demoted` · `held` · `released` · `closed` · `accepted` · `reopened` · `retracted` · `answered` · `summarized` · `noted` · `withdrawn` · `unwithdrawn` · `repaired` · `config-policy` · `batch-manifest` · `binding` (the last three in the policy file only) | derived (1.2) |
| `fields` | [string] | head keys by name; `scope` / `updates` / `history`; for the policy file, its keys; sorted | diff (1.2) |
| `build` | string | the build hash after the write (stored prefixed); on a policy-chain entry, the 5.1 construction over `config.toml` minus `[history]` | computed |
| `ref` | typed? | per act: `Closure{id, hash}` written `"c<n>:sha256:<hash of that closure entry>"` (5.2) for `accepted` / `reopened` / the owner's `closed`; `RestartFrom(seq)` written as an int for `repaired`; `Members[h…]` for `batch-manifest`; `Binding{key_fpr, grant, tenant, from, until?}` written as an inline table for `binding` (`until` absent while open, never null); absent otherwise | the caller (`accept`, `repair`), the realm (`binding`), or the store (the owner's `closed` from `closures[-1]` of `after`; `Members` at signing) |
| `note` | string? | `repaired` only: the tool-composed note | `repair` |
| `h` | string | the chain hash (5.5) | computed |
| `sig` | string? | singly signed acts: `sign(tenant ‖ h)`; on the `batch-manifest` entry, the batch form `sign(tenant ‖ batch_hash)` (1.12); absent on a batch member | the signer backend |
| `batch` | int? | present when signed as part of a batch: the `seq` of the `batch-manifest` entry in the policy chain; the member's signature is the manifest's | the store |

`sig` and `batch` are **outside the chain content** (5.5) — the chain is integrity; the signature is authority; a batch position cannot be inside the hash it is derived from (W2).

**The owner's hard condition, verbatim (round 25):** *"we need to make sure that teh agent NEVER reqrites the past history. this should be a deterministic call that appends a single line. no hand-written line by an llm. this has beena disaster in the past.."* And the extension, verbatim (round 30): *"i'd argue that all structured files (wiki pages, cards, etc) must use specific writers/readers that return structured/typed responses and accept the same (except code). those fcuntions are guarded by zero-trust mechanisms that identify who has access and who altered (as we have already established). if the file is accessed or written via bash commands, it is caught at commit time by some tool call history/database line not matching the commit tool chain checks (or similar)."* Made true, and said exactly:

- **What the chain proves:** integrity — careless edits, reorderings, and (with the ledger's head) any rewrite of the landed prefix. It has no secret; it does not prove authorship.
- **Content is deterministic from the diff — and recomputed.** `act`, `fields`, `build` are the recompute table's function of (before, after, ref); CI and ingest run the same derive function — refusals included — and compare; a mismatch or a refusal is `integrity:tampered`; the hook never recomputes (9.6). An entry that matches is byte-identical to what `write` would have produced. The only authored text in any entry is the repair `note`, inside the signed content.
- **The access path is journaled and reconciled per commit** (03b, 9.6): for every governed file a commit touches, the journal must hold the unbroken chain from the parent's blob to the commit's blob, or the transition is `integrity:unjournaled`. A byte-perfect hand-written line is still caught: no journal row produced it.
- **One git-free check:** `history[-1].build == build_hash(now)`; `at` monotone.
- **Only `write` writes entries; the hook refuses, never appends** (V1).
- **Repair appends, never rewrites:** `repair --history <id>` appends a signed `repaired` entry with `ref = restart_from` (the `seq` whose `h` the chain resumes from; `≥ history_head.seq`, or 1 with no land) and a tool-composed `note`; the repair entry chains from `h_restart_from`; `seq` continues; the unverifiable entries stay, marked.
- **`## History` is log class** — un-hashed, outside the payload; a hand edit is `integrity:tampered`.
- **`## Updates`** stays authored prose, append-only; `write` with `--set updates+=…` appends the block `### YYYY-MM-DD — <title>` with the body passed and derives `noted`; a hand-written header is a bypass, `integrity:unjournaled`.

**Declared limits.** `by` / `for` are attested by the store for every journaled call (L4). A never-landed card on a non-git tenant has integrity checks only — chain, recompute, journal — and no authenticity beyond `sig` (L5). The `software_key_ack` waiver makes every signature software-grade. `Co-Authored-By` trailers are read at ingest for the `attribution` check only; nothing stores them — author and trailers are derivable from `commit`.

### 1.16 Ceremony trims and the board — **[owner-ratified 2026-08-17 (S11)]**; board **[rounds 24, 38, 47, 52]**

`scope_mark` optional, default `owner-ratified` (hashed, U8); `effort` optional while `config.toml` declares one tier (filled **after** hashing — the hash is over the raw, absent value, T6); no cap on `title` (warn above 200).

**The board — the queue first (V7, round 47), rendered by the store at land and on demand (`show Board`), committed when `board.commit = true` (W4) — the one `board` config key; its manifest row is grant-only, since no caller submits a board document (03b §4).**

- **The queue section opens the board and the morning review** (1.5).
- **Precedence shows the most actionable label:** `has-questions` > `held` (W5).
- **Sections keep the owner's reading:** Open / Blocked / Deferred / Watching, epics nesting their children; containers carry their roll-up.
- **Id first**, always — `**50**`. **Caps per segment, never per line:** title 120 · `hold.on` 80 (wraps when it carries a pointer) · summary 120; empty segments omitted; `·` in a title is escaped.
- Line = `id · title · projected label · depends_on · hold.on · <summary | derived> · (was N)`.
- **Summaries are labeled, never signed (V3).** Owner (round 24): *"good with note that summaries should always be verified never assumed"* — an authored summary renders `by <who>` and `changed-since` when the build hash moved after its `summarized` entry; the derived fallback renders `(derived)`.
- **Header:** WIP against the ceiling (ratified, not held, no questions, not pending) · inbox counts by source (the inbox section follows the queue; `SUGGESTIONS.md` is gone — W4) · the archive line (section 3).
- Nothing reads `BOARD.md`; every computation reads cards and the sidecar.

### 1.17 What the builder sees and what it may read — **[owner-ratified 2026-08-20 (rounds 24, 34)]**; projection [proposed]

Owner, verbatim (round 24): *"all good but wondering why sprint/milestone the builder never sees. this sems important information to consider when planning how to build the parts and what they are relevant and are coming but have not been built but have been planned. repeatedly, because i watch at times and tell the agent to remember that this is related to... the agent changes the shape of the thing they bul=ild with more elgance. is this a miscommunication or would the agent really have no awareness of these? i think we have gone the route of everything important needs to be in the hash vs everything required needs to be in the hash and there are important things the builder needs to know that are not in the hash, it can build without them but it will build better with them. does this makes sense?"* And round 34, verbatim — review S2's read-deny reversed: *"i donlt understand. doesn;t the builder need access to all of this? are we currently enforcing auth across the system?"* — *"the builder needs to read almost everything in the repo, because they alter almost everything in the repo: code, wiki, governance, guiding docs, history... to understand how to build what they will build and the context, they need access to everything that is in the git (that is not git ignored), and sometimes they have needed that, though i am ok with that being a requested owner auth from the builder). am i missing something?"* — *"that was the argument i had about small scoped cards. the user wouldn;t have enough information to build"*.

**The principle:** the card is the **specification** the builder is accountable to; the repo, the ratified neighborhood and `guidance` are its **context**; **restrict writes, never reads.** The builder reads everything in its checkout, history intact; the boundary is the write side — no store credential, `surfaces` as its ceiling, suggestions to the inbox; anything outside the repo is a request through the interrupt channel, owner-approved with the same un-cacheable act; nothing in the repo is sensitive. **The accepted channel, named (L8):** a later run can read an earlier run's suggestions, drafts and Updates — builder-authored text reaching a builder without the gate; round 34 accepted it; the inbox bounds and the board's render rule (bodies only for dispositioned items) keep it small. A remaining gap in what the builder needed is a planner miss and must surface as a question or a suggestion.

**The payload — hash = required, payload ⊇ hash:** (1) this card's gated set, canonical serialization, plus the resolved `refs` content and the `source_narrative` excerpt; (2) the **neighborhood projection** — a deterministic function of (the card graph at `base_sha`, the sidecar, the caps), over cards with `status ∈ {ratified, closed}` whose build hash equals their fingerprint, delivered as a typed, delimited data block labeled as context: the parent chain (`id`, `title`, `## Scope`, label), siblings under the same parent (`id`, `title`, bucket `planned` · `in-flight` · `built` · `held`), direct dependencies and dependents (`id`, `title`, bucket, `surfaces`), and the bound milestone / sprint card's `title` and `## Scope`. Caps (`payload.context.depth` default 2, `max_bytes` default 16 KiB) are reserved out of the budget; eviction order dependencies/dependents → parent chain (Scope truncated per level) → milestone → siblings; the projection truncates and records `context.truncated`, never fails readiness. **Eviction is visible to the builder [owner-ratified 2026-08-27 (7be.3)]:** each evicted card leaves a stub inside the delivered context block — `id` + `title` + `evicted: <reason>` — the builder sees what was dropped, with a handle; `context.truncated` stays the operator's flag (`../research/isidium-review-2026-08-27.md` §3). Its canonical bytes are covered by the run's `payload_hash`.

### 1.18 The suggestion inbox — **[owner-ratified 2026-08-20 (round 28)]**; design in `03a-suggestion-inbox.md`

Owner, verbatim (round 27): *"if the builder has suggestions based upon its work, it should hand those back to the tenant as suggestions that get reviewed and approved (probably with the planner). your method seems like it would support this, bu we need something similar to a ledger where suggestions are sourced that the planner reviews one each invocation or a human can read when coding."* What a card must know of it:

- **`suggestions.jsonl`** under the root: append-only, tool-written, chained like `## History` (genesis `sha256(b"schema:<n>\ninbox:<tenant>")`, `c` = every key but `h`). Records carry a `type` key (`intake` | `disposition`); intake `s<n>` (`source` ∈ the inbox's allowed subset `{run, planner, session, review, digest}` of the one `Origin` enum — one type for the card's and the inbox's `source`, each schema declaring its allowed subset (2.1); `kind`; `title` ≤ 120, `body` ≤ 2 KiB, both subject to the forbidden-codepoint rule; `refs` at `base_sha`; `proposed_for`); disposition `d<n>` on `s<n>` with `outcome ∈ {accepted(as: card | guidance | note), declined(reason ≤ 500), deferred(until: Date | Condition)}`. Count bounds: `inbox.max_per_run` (default 10), `inbox.max_per_actor_per_day`; overflow is a count (`suggestion-overflow`).
- **The builder never calls the tenant.** Its suggestions are a typed, bounded section of the run report (T-C6); `land` writes the intake records under the `lander` grant.
- **Bots do not write drafts.** A draft is one disposition: `disposition s12 --outcome accepted --as card` creates the card (`status = "draft"`, `source = "suggestion"`, `see = ["s12"]`; the body into `## Updates`; `## Scope` empty until the owner speaks; `from.card` → `parent` when it is an epic, else `see`); `--as guidance` is a proposed gated edit to a card (re-ratification — it rides the next sitting's batch as a `WriteRequest`, X1); `--as note` writes a `noted` block carrying the `s<n>` reference, never the body.
- **The planner works with the owner.** Owner, verbatim (round 28): *"the planner should always work with the owner for now. we may go the route of spolia and begin to learn from these interactions in the future, but for now, i do not trust any llm enough to not miss obvious things that an experienced design engineer would source as possibiities and prefeences (like the history as footer). behavior design is my contribution to this building and i've found when i'm lax we suffer."* — every disposition with the owner; the morning review lists the planner's dispositions since the last batch signature (L9).
- **The invocation protocol — the morning review.** Owner, verbatim (round 28): *"every planner invocation, it shoud review it's list of opens, priniples, arc, etc. and let the owner know that it has x items from the factory in its ledger"* — review opens, principles and the ARC; report the queue (1.5); run the dry run on anything proposed; present the batch. The roster owns the detail.
- **One inbox** (round 28: *"yes"*); `source` tells session suggestions apart. The ledger keeps the run-report copy; a mismatch either way is `suggestion-mismatch`.

## 2. Field inventory — draft-6 [classes owner-ratified per 1.7; per-field mechanics [proposed]]

Class: **G** gated · **C** claims · **T** tending · **L** log · **M** meta · **X** execution (never in the head). **Hashed:** **B** build · **Cl** bound by `ref` when judged (5.2) · **—** neither. Required-at: **D** draft · **S** ratified story · **E** epic · **Sp** sprint · **Mi** milestone. Section 5.1's build-hash list is generated from the **B** rows of this table by the toolkit at release (F1, G3). Every type below is a closed enum or a discriminated shape; `Ext(name)` variants are validated against `config.toml`.

### 2.1 Card head

| Field | Type | Class | Hashed | Req | Note |
|---|---|---|---|---|---|
| `schema` | int | M | prefix | all | card-schema version |
| `id` | int ≥ 1 | M | — | all | from the store's counter; never reused |
| `kind` | `story` \| `epic` \| `sprint` \| `milestone` \| `Ext(ladder level)` | M | **B** | all (draft defaults `story`) | dispatch = `story` only |
| `status` | `draft` \| `ratified` \| `closed` \| `withdrawn` | M | — | all | more-active moves carry `sig` |
| `source` | `Origin` — the card's allowed subset `session` \| `review` \| `planner` \| `suggestion` \| `digest` \| `Ext(name)` of the one `Origin` enum (the inbox declares its own subset, 1.18) | M | — | D (default `session`) | provenance; set once |
| `scope_mark` | `owner` \| `owner-ratified` | **G** | B | optional (default `owner-ratified`) | exempts `narrative` (1.11); hashed (U8) |
| `title` | string | **G** | B | all | no cap; board segment truncates at 120 |
| `shape` + `narrative` | the discriminated shape of 1.11 | **G** | B | S (default `shapes.default`) | choice free; conformance enforced |
| `rules` | [{`id` `R<n>`, `text`}] | **G** | B | `ears`: required | grammar by shape |
| `questions` | [{`id` `Q<n>`, `text`}] | **G** | B | — | non-empty ⇒ never ready; removable only by an answer |
| `answers` | [{`question_id`, `text`}] | **G** | B | — | by any channel (1.12) |
| `parent` | int | **G** | B | — | scope parent; ladder-validated; holds propagate down |
| `depends_on` | [int] (set) | **G** | B | — | acyclic; blocks readiness; a board segment |
| `goal` | int | **G** | B | Sp | the epic or milestone that drains the sprint's batch |
| `effort` | tier id | **G** | B (raw) | S (defaulted after hashing while one tier) | budgets per tier in config |
| `source_narrative` | `Anchor{path, anchor}` | **G** | B | when narrative-sourced | the excerpt enters the payload |
| `refs` | [`Ref`] (1.14) | **G** | B | — | order hashed as written |
| `surfaces` | [glob] (set) | **G** | B | **S** (`[]` legal under `spike` / `task`) | write ceiling; never intersects the root |
| `acceptance` | section 4 | **G** | B | S; optional E | scenarios may bind to rules |
| `guidance` | `avoid[]` · `risks[]` · `constraints[]` (1.10) | **G** | B | — | ids explicit |
| `closures` | [{`id` `c<n>`, `kind` = `human`, `outcome`: `Met` \| `Deviated{description}`, `verdicts`?: {`S<n>`: `pass` \| `fail` \| `manual`}, `evidence` [`Ref`], `retracted`: bool (always written)}] | **C** | Cl | when `status = closed` | append-only; `kind = "factory"` exists only in the sidecar; `migrated` reserved, rejected in v1 |
| `reopens` | [{`id` `o<n>`, `closure_id`, `reason`}] | **C** | Cl | on reopen | append-only |
| `priority` | `P0`–`P3` | **T** | — | S | |
| `class_of_service` | `expedite` \| `fixed-date` \| `standard` \| `intangible` | **T** | — | — (default `standard`) | `expedite` requires a bounded `because` (tending, ≤ 200 chars) — no bare urgent flags **[owner-ratified 2026-08-27 (7be.3)]** (`../research/isidium-review-2026-08-27.md` §3) |
| `due`, `starts`, `ends` | TOML local date | **T** | — | — | |
| `sprint`, `milestone` | int | **T** | — | — | bindings; the bound card's Scope reaches the builder via 1.17 |
| `lane` | `hotfix` | **T** | — | — | absent = batch lane |
| `hold` | `{kind: blocked \| deferred \| watching, on?: Owner \| Card(id) \| Legacy(tenant, id) \| Text}` | **T** (set) / signed (clear of `blocked`/`deferred` on ratified) | — | — | 1.8 |
| `summary` | string ≤ 120 | **T** | — | — | labeled, never signed |
| `tags` | [string] (set) | **T** | — | — | board filtering only (F12) |
| `withdrawn_reason` | string | **T** | — | when `withdrawn` | required |
| `see` | [string] | **L** | — | — | `legacy:`, `tenant:`, `s<n>`, free pointers |
| `renumbered_from` | int | **L** | — | after an id repair | set once |
| `x` | table per the extension schema | per schema | per schema | per schema | section 7 |

**Not stored (derived):** ready verdict, blocked-by, held-by, batch membership, age, resume state, projected label, ratified-at/by and closed-at/by (from `## History`), the build hash (ledger; `state.json`), closure-entry hashes (`ref`), members of any container, last-touched (newest entry), the neighborhood projection, untraced count, the open inbox, the queue.

**Removed in draft-5:** `template` (the schema is named by composition — `schema`, `kind`, `shape`, the extension schema), `draft_key`, `promoted_from`, `needs`, `external_ref` (→ `see`), per-entry `claims`, `via`, `att`.

### 2.2 Body sections

| Section | Class | Required | Content rule |
|---|---|---|---|
| `## Scope` | **G** | S E Sp Mi (optional on drafts) | the owner's words verbatim (`scope_mark`); never pattern-matched by any shape rule; an empty section hashes as `""`, an absent section omits the key |
| `## Updates` | **L** | optional | append-only dated blocks (`### YYYY-MM-DD` prefix) via `write`; anchors `#u<n>`; never amended — a correction is a later block carrying `corrects = "#u<n>"`; text before the first block is `body.unclassified` |
| `## History` | **L, tool-only** | every card, ≥ 1 entry | the last section; one fenced ```toml block, `history = [ … ]`, one inline table per line, `]` alone on its line, the closing fence ends the file |

### 2.3 Schema-1 fields under the bridge — where each goes when a legacy item is re-authored (round 38)

Nothing is imported; the legacy item stays in the archive; a new card pointing at it is written by the owner and the planner in session. `decision_owner = user` → `hold = {kind = "blocked", on = {owner = true}}` · legacy `blocked | deferred | watching` → `hold.kind` · `blocked_on` → a `depends_on` when the predecessor is already a card, else `hold.on = {legacy = "<tenant>/<id>"}` · spolia `awaiting_confirmation` → `hold = {kind = "blocked", on = {owner = true}}` · `resolution` / `verified_by` / `closure_exception` / `guardrail` → stay in the archive item, which `refs` carries into the payload · `branches`, informal refs, `summary` → `see`, gated `refs`, tending `summary` as the author chooses · `epic` → `parent` (the legacy epic re-authored first) · the legacy id → `see = ["legacy:<tenant>/<id>"]`.

## 3. Profiles and the bridge [profiles proposed; the bridge owner-ratified 2026-08-20 (rounds 38, 40)]

| Rule | `draft` | `story` | `epic` | `sprint` | `milestone` |
|---|---|---|---|---|---|
| head parses; `schema`, `id`, `status`, `title`, `source` present; `## History` present with ≥ 1 entry | ✓ | ✓ | ✓ | ✓ | ✓ |
| `kind` | (default `story`) | `story` | `epic` | `sprint` | `milestone` |
| `## Scope` (with `scope_mark` defaulted) | — | ✓ | ✓ | ✓ | ✓ |
| `shape` ∈ `shapes.allowed`; the shape's layer rules (1.11) | if present | ✓ | — | — | — |
| `acceptance` runnable-shaped, ≥ 1 scenario | — | ✓ | optional | — | — |
| `surfaces` (may be `[]` under `spike` / `task`) | — | ✓ | — | — | — |
| `effort` (defaulted while one tier), `priority` | — | ✓ | `priority` optional | — | — |
| `goal` resolves to an epic/milestone | — | — | — | ✓ | — |
| `depends_on` / `parent` / `sprint` / `milestone` resolve; acyclic; ladder | if present | ✓ | ✓ | ✓ | ✓ |
| `x` valid against the extension schema | if present | ✓ | ✓ | ✓ | ✓ |
| `closures` ≥ 1 when `closed`; `reopens` on reopen; `withdrawn_reason` when withdrawn | ✓ | ✓ | ✓ | ✓ | ✓ |
| chain verifies; entries recompute; the journal reconciles | ✓ | ✓ | ✓ | ✓ | ✓ |
| in the ready-view | never | when T-A4 admits and `questions` empty | never | never | never |

Verdicts are typed per rule id (`profile.story.acceptance`-style — one naming regime with the dotted rule ids); `ratify --dry-run` returns exactly these plus the readiness projection and the batch display.

**The bridge — no import, no migration code.** Owner, verbatim (round 38): *"could we make a temporary bridge for this migration wherein we write new cards in the new system derived from the old boad and point the card to the board item for more context?"* — *"yes to both."* — and (round 40) *"assume that we wil migrate in an interactive session like this, but solve for everything that would block us on the way."*

- **The legacy tree is frozen as an archive**, read-only; nothing imported, nothing rewritten. How the freeze is done in sartor and spolia is the **bridge session's** work, with the round-4 review's section 4 as its input; this schema requires only that a `refs` entry into the archive resolves at ratification and is recorded (`refs_resolved`), so a later archive change is `ref-drifted` at dispatch.
- **New cards point back** — written through `write`, the dry run and the sitting's signature, with `refs = ["docs/dev/work/items/<NNNN>-<slug>.md"]` and `see = ["legacy:<tenant>/<NNNN>"]`; fresh id; `## History` starts at `created`. Closed legacy items stay closed in the archive; reopening one is a new card. Legacy epics are re-authored first as epic cards.
- **Lazy, and interactive.** Owner, verbatim (round 38): *"we'll need to incorprate the tooling into sartor and then i can reauthor the board epics into cards for proper prioritization in an interactive session"* and *"and spolia"*. Per tenant, each in its own session: (1) point the tenant's container at the store and install the thin client (`init`); (2) the owner re-authors the board epics as cards with the planner, one batch signature per sitting; (3) sartor C/D/E runs as the factory's first test on bridged cards.
- **Deferred: bulk import.** The migration-via-drafts path (T2), the `migrated` closure kind (S4), an import command and the round-3/4 migration findings stay designed in the record for a tenant that needs a bulk import someday; none is in v1 — the validator knows `migrated` only as a reserved, rejected value.

## 4. The acceptance block — house scenario dialect — shape **[owner-ratified 2026-08-16]** ("yes"); per-kind shapes [proposed; W10]

### 4.1 Shape

`acceptance.scenarios` — an ordered list; each scenario: `id` (`S<n>`, never renumbered — verdicts key on it) · `kind` (closed enum `test-marker` · `command` · `http` · `file-assert` · `manual-evidence` · `Ext(name)` against the dialect schema; `judged` reserved) · `title` · `rule?` (the `R<n>` it exemplifies) · `traces?` (an anchor into the narrative; optional — owner, round 20, verbatim: "traces: yes, optional which we can track and evaluate later for the things without it") · `context` / `action` / `observable` per kind (below; `observable` always required; rendered as Given / When / Then under `bdd`, never duplicated as prose) · `tests` (nested TDD requirements `path::name`). `acceptance.manual_attestation` — `interrupt` (default, `policy` tag — [proposed-default]) or `human-closure-only`. **Open-standards trajectory [owner-ratified 2026-08-27 (7be.3)]:** the scenario dialect is authored here, then donated — author-then-donate, as the hook dialect records (`../research/isidium-review-2026-08-27.md` §3).

### 4.2 Per-kind shapes — a discriminated union on `kind` [proposed]

| kind | `context` | `action` | `observable` | runner binding |
|---|---|---|---|---|
| `test-marker` | forbidden | forbidden | `Test(path::name)` \| `Marker(expr)` — written `{ test = "…" }` or `{ marker = "…" }` | test runner (default `pytest`) |
| `command` | `{ fixture?: path, cwd?: path, env?: {k: v} }` | `{ run: [argv] }` (an argv array; a string is a typed error) | ≥ 1 of `exit_code: int`, `stdout_matches: Pattern`, `stderr_matches: Pattern`, `files: [FileCheck]` | shell runner in the checkout |
| `http` | `{ fixture?: path, base_url?: ref }` | `{ method, path, body?: string \| table }` | ≥ 1 of `status: int`, `body_matches: Pattern`, `headers: {k: v}` | http runner |
| `file-assert` | `{ fixture?: path }` | `{ run?: [argv] }` | `FileCheck` = `{ path }` + **exactly one** of `exists: bool` · `contains: string` · `matches: Pattern` · `sha256: hash` · `equals_file: path` | file runner |
| `manual-evidence` | prose | prose | `{ evidence: string }` | none → `manual` |

`Pattern` is the regex dialect all three targets share (5.3). Cards with only `manual-evidence` scenarios cannot be factory-closed without a `policy` attestation (1.13) — a typed note, not an error. `guidance.constraints[].check` is `{ kind, action, observable }` in the same shapes.

### 4.3 Example — a complete, validating `bdd` story — and the authoring order rule (F19, H1)

````markdown
```toml
schema = 1
id = 42
kind = "story"
status = "ratified"
source = "suggestion"
title = "cards check refuses a ratified card with no acceptance block"
shape = "bdd"
effort = "default"
priority = "P1"
surfaces = ["client/cards/validator.py", "client/tests/test_validator.py"]
refs = ["client/cards/validator.py::validate_profile", "docs/dev/work/items/0060-cards-check-no-acceptance.md"]
see = ["legacy:sartor/0060", "s12"]

[narrative]
feature = "cards check refuses a ratified card with no acceptance block"

[[rules]]
id = "R1"
text = "A ratified story without a runnable-shaped scenario is a validation error, not a warning"

[[acceptance.scenarios]]
id = "S1"
kind = "command"
rule = "R1"
title = "cards check refuses a ratified card with no acceptance block"
context = { fixture = "client/tests/fixtures/no-acceptance" }
action = { run = ["python", "-m", "cards", "check"] }
observable = { exit_code = 1, stdout_matches = "profile\\.story\\.acceptance" }
tests = ["client/tests/test_validator.py::test_refuses_missing_acceptance"]

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
rule = "R1"
title = "build hash is key-order independent"
observable = { test = "client/tests/test_hasher.py::test_key_order_invariant" }
```

## Scope

`cards check` must treat a ratified story with no runnable-shaped
scenario as an error (`profile.story.acceptance`), never a warning. Legacy
context: sartor item 0060 (see `refs`).

## Updates

### 2026-08-20 — filed from the inbox (s12)

Re-authored from legacy 0060 under the bridge.

## History

```toml
history = [
  { seq = 1, at = "2026-08-20T14:02:11Z", by = "amodal1@example", act = "created", fields = ["acceptance", "effort", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "see", "shape", "source", "status", "surfaces", "title"], build = "sha256:3f9c…", h = "sha256:a1b2…" },
  { seq = 2, at = "2026-08-20T14:03:40Z", by = "amodal1@example", act = "noted", fields = ["updates"], build = "sha256:3f9c…", h = "sha256:c3d4…" },
  { seq = 3, at = "2026-08-20T14:05:03Z", by = "amodal1@example", act = "ratified", fields = ["status"], build = "sha256:3f9c…", h = "sha256:e5f6…", batch = 412 },
]
```
````

The card was created as a draft from suggestion s12 (`source`, `see`), noted, then ratified in a sitting whose manifest — policy-chain entry 412 — carries the batch signature. `show Card(42)` renders S1 as *Given* the fixture, *When* the command runs, *Then* exit code 1 and stdout matches; `effort = "default"` is the single tier, hashed raw (absent would also be legal and hashes differently — T6).

**Authoring order (F19):** every `write` emits all scalar keys first — among themselves in the 2.1 inventory order, so two stores emit byte-identical blobs — then the tables in the pinned order of 1.1; the validator checks each table against its own key inventory (`id`, `kind`, `title` are legal inside scenarios and rules; `[x]` is exempt); a table out of order is `head.table-order`; the footer is the last section (`body.history-position`).

### 4.4 Compile contract (T-B2)

Manifest = a deterministic function of (build hash, config hash): per scenario → `{scenario_id, rule_id?, kind, runner, params, tests[]}` or `manual`; `guidance.constraints[].check` entries compile alongside as `{constraint_id, …}`. Unbindable ⇒ a typed compile error naming the scenario, surfaced at T-A2 as "runnable-shaped". `accept` runs the same manifest. The `.feature` projection (T-B11) maps context/action/observable → Given/When/Then and `rules` → `Rule:`, and never reads back.

## 5. Canonicalization, the hashes, the chain, the signature — **[owner-ratified (S1; T6; U8; rounds 42, 48, 50, 54, 58)]**; mechanics [proposed]

### 5.1 The build hash — generated from section 2.1

Input `obj` = the **raw value tree before any defaulting** (T6), restricted to the keys marked **B**: `title` · `kind` · `shape` · `narrative` · `rules` · `questions` · `answers` · `parent` · `depends_on` (set) · `goal` · `effort` (raw; absent when defaulted) · `scope_mark` (raw) · `source_narrative` · `refs` (as written) · `surfaces` (set) · `acceptance` (scenario order matters) · `guidance` · gated `x.*` (as declared; the `x` key omitted when no gated key is present) · `scope` = the `## Scope` string.

```
build_hash = "sha256:" + hex(sha256(
    b"schema:" + ascii(schema) + b"\n" +
    b"canon:"  + ascii(canon)  + b"\n" +
    canonical_json(obj)))
```

`canon = 1`. The stored form is the prefixed string everywhere. On a policy-chain entry (`config-policy`, `batch-manifest`, `binding`) `build` is the same construction over `config.toml` minus `[history]`, with the prefix lines (`schema` = the config schema's registry version).

### 5.2 The closure-entry hash

`sha256(canonical_json(entry))` over one `closures[]` or `reopens[]` entry as written (`retracted` present), **no prefix lines**, stored prefixed inside `ref` as `"c<n>:sha256:<hex>"` / `"o<n>:sha256:<hex>"`. It is the only claims hash: a judging entry binds the one closure it judges through `ref` (W6); there is no whole-set claims hash — nothing consumed one (round 6), and 2.1's **Cl** means "bound by `ref` when judged". Drift in a landed claim is not a hash question: `write` refuses the edit (append-only, inside `derive`; the retraction flip carved out, H5) and outside the store it is `integrity:tampered` (1.5 row 1). On a canonicalization bump ingest re-hashes and re-binds closures to the new build hash of the same content (F4); a re-hash that fails ⇒ `unratified`.

### 5.3 Canonical forms — language-neutral (F2, G2, H17, W10)

| Type | Canonical form |
|---|---|
| strings | UTF-8, **NFC** (values and quoted keys); the Unicode database version pinned in `config.toml [toolkit]` and asserted at start-up (`canon.unicode-db`). **Forbidden code points** in gated strings, inbox `title` / `body`, Updates headers and keys: C0/C1 controls except `\n` and `\t`, zero-width (U+200B–U+200D, U+2060, U+FEFF), bidi controls (U+202A–U+202E, U+2066–U+2069) → `canon.forbidden-codepoint` |
| prose (`## Scope`) | line endings → `\n` (CRLF and lone CR first); trailing `[ \t]` stripped per line; leading/trailing blank lines stripped; no trailing newline. Declared limit (L1): Markdown hard line breaks are erased |
| integers | JSON number; `i64`, and **≤ 2⁵³ in magnitude** wherever TypeScript reads it (`canon.int-range`) |
| floats | **rejected in every hashed input** (`canon.float`) — cost in integer micro-units, durations in milliseconds; `x` keys may not hold floats |
| dates | TOML local date → `"YYYY-MM-DD"`; datetimes in gated fields must carry an offset → UTC `YYYY-MM-DDTHH:MM:SS[.ffffff]Z`, the fraction present iff microseconds ≠ 0, more than six digits rejected (`canon.datetime-precision`); local date-times rejected |
| booleans | `true` / `false`; rejected inside set-valued arrays (`canon.set-bool`) |
| arrays | as written unless set-valued (`depends_on`, `surfaces`, `tags`) → homogeneous int or NFC string (`canon.set-mixed`), sorted by value (strings by code point), duplicates rejected (`canon.set-duplicate`) |
| tables | keys sorted by code point (= UTF-8 byte order); `{"k":v,…}` with no whitespace |
| JSON escaping | exactly `"`, `\`, and U+0000–U+001F (`\b \f \n \r \t`, else `\u00xx` lowercase); nothing else escaped (not `/`, not U+007F, not U+2028/9); non-ASCII emitted raw |
| absent vs empty | absent key omitted; empty array/table serialized as such; an absent `## Scope` omits `scope`, an empty one is `""` |
| `Pattern` | the regex dialect **all three targets share**: no lookaround, no backreferences, no atomic or possessive groups, Unicode classes at the basic level — validated at write (`canon.regex-dialect`) |
| `[extensions]` key lookup | **NFC before the lookup** — both the document's `x.*` key and the declaration are NFC before matching; a declaration that is not NFC-unique is `ext-schema.key-collision` (the one corpus pair where the round-3/4/5 oracles split from round 6; pinned) |

`ext_schema_hash` = the same canonicalization over `config.toml [extensions]` at the parent commit's policy, without the prefix lines; when `[extensions]` is absent, the bare digest `sha256("")` in hex; when present, the stored prefixed string. **Hashing is done by the Rust and Python cores only; TypeScript parses and renders.** Vendored hasher == factory hasher, verified by the **conformance corpus** shipped with every release: the round-3, -4, -5 and -6 prototypes (`review-artifacts/…/r3-impl`, `r4-impl`, `r5-impl`, `r6-impl`) agree byte-for-byte on it (the NFC-key pair under the lookup pin above; r3's footer-position and `scope_mark` differences are ruled) and are the oracles a fifth hasher must match. Corpus minimum (G4): equal — CRLF vs LF; key order; a comment; a slug rename; a tending edit; an Updates append; a history append; NFC vs NFD (values and keys); differ — one scenario character; one `depends_on` element; one `## Scope` word; one gated `x` value; empty vs absent array; a `rules` edit; a `questions` entry; explicit single-tier `effort` vs absent (*deliberate*, T6); `scope_mark = "owner"` vs absent.

### 5.4 Fingerprint record (ledger; mirrored in `state.json`)

`{ratified_seq, commit, refs_resolved: [{path, blob}], ext_schema_hash, validator_version}` (W8) — everything else is inside the entry `ratified_seq` names. Reclassifying an `x` key G↔T is `ext-schema-changed`: a re-hash of every card authorized only by a signed `config-policy` act; without it, affected cards go `unratified`.

### 5.5 The history chain

For entry *n*, canonical content *c* = the sorted-key JSON of all its keys **except `h`, `sig` and `batch`**:

```
h_0 = "sha256:" + hex(sha256(b"schema:" + ascii(schema) + b"\ncard:" + ascii(id)))
h_n = "sha256:" + hex(sha256(utf8(h_{n-1}) + b"\n" + canonical_json(c_n)))
```

`id` as decimal digits. The inbox chain uses `b"\ninbox:" + tenant`; the policy chain `b"\npolicy:" + tenant`; a page's `b"\npage:" + <its governed path>`; the journal's `b"\njournal:" + tenant` (03b). In every non-card genesis `schema` is the document's own registry schema version (`inbox@n`, `policy@n`, `page@n`, `journal@n`), never the card's. **Repair:** a `repaired` entry with `ref = k` chains from `h_k`; `seq` continues; `k ≥ history_head.seq` (1 with no land); the entries between `k` and the repair are unverifiable, covered. **Id repair:** from the `repaired` entry on, the genesis is the new `id`; the entries before it verify under the old. Verification recomputes `h_1 … h_N`; the sidecar's `history_head` must equal entry `seq`'s `h` (a mismatch is `integrity:rewritten` even when the chain verifies). One SHA-256 per entry; cached by blob.

### 5.6 The signature

Single: `sig = alg + ":" + key_fpr + ":" + base64(sign(utf8(tenant) + b"\n" + utf8(h_n)))`. Batch: `H` = the members' `h` sorted by code point; `batch_hash = "sha256:" + hex(sha256("\n".join(H)))`; `sig = … sign(utf8(tenant) + b"\n" + utf8(batch_hash))`; the `batch-manifest` policy entry carries `ref = Members(H)` and the one `sig`; each member carries `batch = <manifest seq>` only. The verifier recomputes `h_n`; with `batch` present it reads the manifest, checks `h_n ∈ Members` and the manifest's signature against its `key_fpr`, otherwise the entry's own `sig`; then the binding at `(key_fpr, at)` in the policy chain. The realm's binding entries are signed the same way with the realm's key (`sign(realm ‖ h_binding)`).

## 6. The sidecar — `state.json` (current) and `state/history.jsonl` (events) [proposed; rounds 34, 56]

Written only by `land` under the `lander` grant, as the store's own commit on `main` after the batch PR merges (X2, 1.4) — the merge commit is `ledger_cursor`; a batch merged and not yet landed is `pending-land`: the cursor does not advance and dispatch on the tenant is closed until the land commits; land is idempotent and replayable, and a half-land replays from its journal row (03b). Never hand-edited — a hand edit or a replay is `integrity:unjournaled` and the lander overwrites it. Sorted keys, indent 2, `ensure_ascii = false`, trailing newline; the card key is the zero-padded id. Missing file = empty snapshot (`unknown` rows); unparseable = `sidecar.unreadable`, rendered with a banner.

```json
{
  "schema": 1,
  "ledger_cursor": "…",
  "landed_at": "<cursor commit time>",
  "journal_head": {"seq": 1187, "h": "sha256:…"},
  "batches": {"b12": {"boundary": "epic", "goal": 7, "sprint_card": null, "opened": "…", "drained": null, "landed": null, "merged": null}},
  "cards": {
    "0042": {
      "fingerprint": {"ratified_seq": 3, "commit": "…", "refs_resolved": [{"path": "…", "blob": "…"}], "ext_schema_hash": "sha256:…", "validator_version": "…"},
      "history_head": {"seq": 5, "h": "sha256:…"},
      "execution": "closed",
      "runs": [{"run_id": "r-…", "batch": "b12", "outcome": "complete", "build_hash": "sha256:…", "base_sha": "…", "head_sha": "…", "adapter": "…", "billing_class": "plan", "dispatched_at": "…", "score": {"rank": 3, "vector": {"time_criticality": 0, "unblocking": 0, "resume": 0, "aging": 0, "batch": 0, "risk": 0}, "config_hash": "sha256:…"}, "ended_at": "…", "payload_hash": "sha256:…", "config_hash": "sha256:…", "context": {"depth": 2, "bytes": 9120, "cards": [7, 41, 43], "truncated": false}, "surfaces_actual": ["…"], "phases": [{"phase": "plan", "agent": "plan-author", "model": "…", "effort": "high", "prompt_version": "…", "tokens": 0, "cost_micro": 0, "duration_ms": 0}], "verdicts": [{"phase": "plan", "verdict": "approve", "reasoning": "sha256:…"}], "price_table": "…"}],
      "closures": [{"closure_id": "c1", "kind": "factory", "outcome": "met", "verified_against": "sha256:…", "verdicts": {"S1": "pass", "S2": "pass"}, "evidence": ["…"], "at": "…", "verified": true}]
    }
  }
}
```

`state/history.jsonl` — one event per line, `{id: "e<n>", at, card, kind, …}` with `kind ∈ {dispatched, parked, answered, failed, disputed, complete, closed, reverted, demoted, withdrawn, acked, accepted, reopened, question}` — a tagged union; the batch record's lifecycle events likewise (`merged` then `landed`). The kinds that share a card act's name (`demoted`, `withdrawn`, `accepted`, `reopened`, `answered`) are the ledger's **own** transition (abandon the run, mark verified, unpark) carrying the card entry's `seq` as its reference — never the entry's content. The current file is the fold of the event file as of the cursor; `execution` is the current execution status (one field, not a list). Human closures appear in `closures[]` only as **verification** — `{closure_id, verified_against, verified, at}`; factory closures in full (they exist only here). Each `phases[]` entry names the **agent kind, effort and prompt version** beside model/tokens/cost/duration — who ran, at what effort, under which prompt (05 §1a; reconcile carries one entry per agent, so phase→agent is explicit). `verdicts[]` records the judge's verdicts for the line's two gates — the plan gate and the park gate — as `{phase, verdict ∈ {approve, revise, park}, reasoning}` with `reasoning` a ref into the run's artifacts; verdict-vs-outcome telemetry folds from it (7bd.10). A reviewer findings record references the producing phase's model, so findings-per-model — the owner's builder-swap signal — is computable from the record alone. Each run records `billing_class` ∈ {`plan`, `metered`} — the plan-vs-metered telemetry that decides the ruled harness swap (7bdb.3–7bdb.4) **[owner-ratified 2026-08-27 (7be.3)]** (`../research/isidium-review-2026-08-27.md` §3). `cost_micro` is **metered** on the API lane and **imputed** on the subscription lane — tokens × a versioned price table, `price_table` recorded once per run so cross-time comparison survives a price change; tokens stay the primary tuning metric. `runs[]` carries no credential name (round 34); `cost_micro` and `duration_ms` are integers (5.3). Idempotency: landing the same cursor twice produces identical bytes.

## 7. Extension namespace `[x]` [proposed; F18]

The tenant's extension schema (`config.toml [extensions]`, a registry schema) declares each key's type, `class = "gated" | "tending"` (tending only for fields the board or prioritization consumes) or `class = "log"` for append lists and set-once scalars, `required_when` transition conditions, enums. Unknown keys under `x` are errors; keys are NFC on both sides before the lookup, and a declaration that is not NFC-unique is `ext-schema.key-collision` (5.3). Gated `x` keys enter the build hash; the extension schema's own hash is in the fingerprint record. A change to `[extensions]` is a `config-policy` act. **[owner-ratified 2026-08-26 (7bc.8, Y2)]** `[extensions]` declares only `x.*` field schemas; tenant shape, scenario-kind, source and ladder-level `Ext(name)` declarations live in their own `config.toml` tables (`[shapes]` / `[runners]` / `[origin]` / `[ladder]` — 04 §2.2) and never enter `ext_schema_hash` (W10). The bridge needs no extension (the archive keeps sartor's `guardrail`).

## 8. Standalone posture — the check the owner's condition sets

A project on the store and the client alone (no factory; the factory deleted) can: initialize (`init` — the client, the hook, the default `config.toml`, the registry schemas installed locally); author (`write`); validate (`check` in CI — chain, recompute, reconciliation against the store's journal; the hook is one check); dry-run and **ratify** (the standalone dial — `sig` verified against the pinned key when identity is disabled); read ratification and drift state from `## History`; verify and close (`accept --close`); suggest and triage; read every card's owner status, every history entry and every landed execution history from its own sidecar + git ("as of cursor"); repair (under the owner); render its board. Not computable locally: run states newer than the snapshot; ledger-only rows (†). A **non-git tenant** keeps everything here except the git corroboration — the tarball test (1.15). Nothing about *doing development* waits on the factory; the factory only adds dispatch.

## 9. Grammar, append-only, gestures, efficiency, ingest, reconciliation

### 9.1 Head/body grammar, pinned (F23, G9, H16, H18)

Fence = three backticks at column 0 with info string exactly `toml`, on line 1 (a BOM is rejected); closing fence at column 0; only the first such block is the head; only fences at column 0 count (`~~~` and indented blocks are text); a ``` at column 0 inside a TOML multi-line string ends the head (`head.fence-in-string`); heading detection is fence-aware. Line endings are normalized to `\n` for matching and hashing only; writes preserve the file's own (H2). `## Scope`, `## Updates`, `## History` are matched exactly (ATX, single space, case-sensitive), in that order; Scope optional on drafts, Updates optional, History required; `###` / `####` allowed under Scope and Updates; text between `## Updates` and its first dated block is `body.unclassified`; anything else is `body.unclassified`. Updates blocks are `### YYYY-MM-DD` prefix; newest = last by position (inserting earlier is `log.rewritten`); anchors `#u<n>` by file order. `## History` is the last section: exactly one ```toml fence holding one top-level key `history` (an array of inline tables, one per line, key order as the table of 1.15, a trailing comma on every line, `]` alone on its line); the closing fence is the last non-blank line (`body.history-position`, `body.history-shape`). TOML 1.0.0; integers `i64`; a bare parse failure is `head.toml`; an unknown top-level key is `head.unknown-key`.

### 9.2 `log` append-only — where it is enforced (F9)

Over the parsed, newline-normalized model, keyed by card id: existing blocks and list entries must be present, in place, and equal after normalization; only additions pass. **Checked once, inside `write`'s derive function, on every structured call** (round 6): a rewrite is `log.rewritten`, refused. CI (against the merge-base) and ingest (since the cursor) run the same function and see a violation only as `integrity:tampered`; the hook does not run it (9.6). No allowance anywhere — the same-day amend of the newest Updates block is gone; a correction is a later block carrying `corrects = "#u<n>"`; `## History` likewise.

### 9.3 Tending gestures — `write --set` (F22, V1)

Tending keys are top-level single-line `key = value` (`head.tending-flat`); a gesture is one `write` that changes one such key, derives its entry (`held` / `released` / `summarized` / `amended` with `fields = [key]`), and **carries `build` forward** — the diff touched no hashed key, so no re-hash (W8), and only the rules whose inputs include that key run (1.2). Clearing a `blocked`/`deferred` hold on a ratified card meets the signature predicate and invokes the signer; clearing `watching`, re-kinding `blocked ↔ deferred`, or anything on a draft, does not.

### 9.4 Efficiency, stated (F13, W-series)

Per operation, store calls and hashes — the journal row's chain hash counted on every write, and every `write` one commit + one push to `main` (a fetch and a clean rebase on a rejected push; governed paths cannot conflict; the sitting batches N into one): **create a card** — 1 call (`write(NewCard{slug}, …)`), 3 hashes (build, `h`, the journal row's `h`; `h_0` is a constant per id); **ratify a batch of N** — 1 dry-run call (0 build hashes on a warm blob cache, N cold — the store computed every `build` at the write that made the blob) + 1 `ratify` call (one transaction: N entries, N `h`, 1 batch hash, the manifest's policy-chain `h`, the journal row's `h`, 1 signer round trip; `ratify` never re-hashes a blob the dry run verified); **a tending edit** — 1 call, 2 hashes (`h`, journal `h`); **a met closure at land** — 1 `land` call (the store's commit on `main` after the merge), one journal transaction (sidecar current + event append + inbox intake + board), k+1 hashes; **a suggestion to a shipped story** — intake (shared) + `disposition` + `ratify` = 2 calls, + 1 amend when the disposition's draft needs its Scope, shape and acceptance before the profile passes; **morning review** — 1 call (`show Queue`); **dry run** — 1 call; **board** — at land and on demand (`show Board`), one pass over the parsed set; **ingest of one commit** — one shared `git log --name-status`, per governed file one blob read (the parent's model is cached from the previous commit), build + `h` recompute through the one derive function, one journal query bounded by the files touched, per signed entry one signature verify + one binding lookup (+ one manifest read when `batch` is present, cached by blob), per `ratified` entry the `refs` blob reads that fill `refs_resolved`. Per card lifetime ≈ 3 store calls of its own + 2/N of the sitting + 1/batch of the land, ≈ 7 card-side hashes + 4 journal + 3/N batch, ≈ 3 journal rows, 0 per-commit renders (the round-6 re-count). Id uniqueness, acyclicity, ladder checks, hold propagation and the board need the full card set: O(N) parses (≈ 0.5 ms/card), O(delta) via a blob-sha → (model, build hash, chain head) cache keyed also by `ext_schema_hash` and canon; no `git log` per card anywhere; no per-card git walks (the board reads cards and `state.json` only — the claims-drift row is gone); the neighborhood projection is one pass per dispatched card, cached per `base_sha`; the history and inbox appends are end-of-file line insertions; one signature per sitting.

### 9.5 Ingest classification, pinned (G5, H6, V5, W9)

Walk `--first-parent` over `cursor..HEAD` on the ratification ref. Identity = the card's `history[].by/for`, corroborated by the commit's author email and `Co-Authored-By` trailers. Policy = the `config-policy` entries in `config.toml [history]` as of the commit's first parent. Per (commit, card) compute (before, after) and emit the set of events: **the recomputed acts** (`created` … `config-policy`, each carrying whether its `sig` verified) · the **integrity reasons** (`tampered` · `unjournaled` · `rewritten` · `unverified` · `attribution` · `time`) · and the few derived facts no act names: `ext-schema-changed` · `ref-drifted` (dispatch re-checks it under the same name, 1.14) · `suggestion-intake` · `suggestion-overflow` · `suggestion-mismatch` · `id-repair`. A rewritten log, an edited closure or a deleted card is not a fact of its own (round 6): the derive function refuses the diff ⇒ `integrity:tampered`; an absent after-blob with no journal row is already `integrity:unjournaled`. **The walk is also how the factory observes a batch PR's merge (X2):** the merge commit appears in `cursor..HEAD`; the store then lands on `main` with that commit as `ledger_cursor`; until the land commits the batch is `pending-land`, the cursor stays, and dispatch on the tenant is closed — no human step between merge and land. A ratification is a signed `ratified` entry whether or not the build hash moved; a gated change on a ratified card with no signed entry is `unratified` at projection, not an event of its own. When a commit signature and an entry signature disagree, the entry decides.

### 9.6 What the hook does, and the per-commit reconciliation (T7, V1, V6)

**The tenant's pre-commit hook** (W4): a governed path changed in this commit → refuse. That is the whole hook in a tenant container; the store is the only writer.

**Reconciliation — a pure function (V6; owner, round 46: *"this is deterministic?"* — yes).** Inputs: for each governed file a commit touches, the parent's blob id, the commit's blob id, and the journal rows for that path (`{seq, at, caller, paths: [{path, before_blob, after_blob}]}` + `h` — no `h_prev`, the chain binds it (5.5); `before_blob` absent for a creation, `after_blob` absent for a deletion; blob id = the repository's object id, SHA-1 or SHA-256 as the repo hashes, stated in `config.toml [toolkit]`; governed paths carry `-text` in `.gitattributes` so the committed blob equals the bytes the store hashed). Output per file: *explained* iff the rows form an unbroken chain from the parent's blob to the commit's blob; *unexplained* (`integrity:unjournaled`) otherwise — never "some state seen before". Commits checked: every commit on the ratification path from the last landed cursor to head, in topological order; on a merge commit the first parent. Consequences: governed-path commits are fast-forward or merge only; a revert is a new commit through the store (`write` of the prior document); `repair --journal <commit>` is the owner-signed act that writes the missing row — a repairing row carries `sig = sign(tenant ‖ h_row)` outside `c` and `repairs = <commit>` inside. CI runs the function against the merge-base, asking the store; ingest runs it against the cursor.

## 10. Config keys this schema references (handed to the config-schema doc)

One file, `config.toml`, **a governed document** (W8): `[toolkit]` (client version, registry version, Unicode database version, the repo's object-id algorithm) · `effort.tiers` (default one) · `ladder` · `profiles.enabled` (`sprint`, `milestone`) · `batch_boundary` · `ratification` (`mode = signed | declared`, `software_key_ack`, `path`, the standalone dial, **`pin`** — the ratifier pin when identity is disabled, its one home — **grants, never keys**) · `signer` (`backends`: the closed set of 1.12; per-backend settings excluding any address or pin) · `time_skew` (seconds) · `grants` (which calls each grant may make — the table of 1.12) · `shapes` (`allowed`, `default`; per-shape lint options such as `ears.weak_words`) · `payload.context` (`depth`, `max_bytes`) · `runners` (kind → binding; defaults) · `extensions` (the extension schema, a registry schema) · `board` (`commit` — the one key; the caps are pinned in 1.16) · `inbox` (`max_per_run`, `max_per_actor_per_day`) · `wip`, prioritization weights (02 §3) · **`[governed]`** (the manifest: path patterns → registry schema → grants; the default covers every row of 1.3; tenants add wiki and recall pages — declared now, their schemas designed under T-B12) · **`[history]`** (the policy chain — `entries = [ … ]`, one inline table per line, `]` alone on its line: `config-policy`, `batch-manifest` and `binding` entries) · **`Origin`** (the one enum; the card's and the inbox's allowed subsets, 2.1 / 1.18). **Every key is policy: a change is a `config-policy` act, signed.** Not in the repo: the identity realm, the tenant's store container (address, pin — one per tenant, 1.3), the secrets source, the signing service's address and pin, the ratifier key fingerprints (except the pin), `allow_software_grade_until` — all in the tenant registration.

## 11. Open — after applying round 6 as ruled

**Removed or pinned in draft-6** (round 7ba: X1, X2; the round-6 fill). Removed: the two `source` enums (one `Origin` with per-schema subsets); the whole-set `claims_hash` (5.2 is the closure-entry hash); `claims-drift`, `log-rewritten`, `deletion` and `closure-invalidated` as outer labels (the gates run `write`'s derive function, refusals included); the hook's recompute (the hook is one check); the same-day Updates amend; `new`, `board`, `inbox`, `queue`, `schema` as verbs (`NewCard{slug}` and `show <target>`); `sig` on batch members (once, on the manifest); journal `h_prev`; `state.json.tenant`; `runs[].surfaces_declared`; the ratifier pin's second home; `Co-Authored-By` in the fingerprint; `S-3.`-style verdict ids; `ref.drifted` beside `ref-drifted`; "the canonical clone of the tracking root"; the 1.14 exemption for the batch PR; `ratify(ids)` as the only batch form. Pinned: `NewCard{slug}` and `WriteResult {id, path, head}`; `derive(before, after, ref) -> Result<Entry, RuleId>` at every gate; rules keyed to `D`; the predicate's retraction exemption and caller-aware clause; `write.no-change`; the store-filled `ref`; `blocked ↔ deferred` = `held`; NFC before the `[extensions]` lookup; the scalars' emitted order; `D` over canonical JSON; the manifest entry's keys; `build` on policy entries; `binding` as an act with `until` absent; the non-card geneses and the `page:` ident; `[history].entries`; the repairing journal row; record-slot documents; `questions.dropped-unanswered` bound to signed cards; a refused creation burns an id; `pending-land` and the fail-closed cursor; the per-write commit + push.

**Decisions this draft had to make (all [proposed] — for the owner):**
1. **`config.toml [toolkit]`** replaces `toolkit.lock`: client and registry versions, the Unicode database version, the repo's object-id algorithm — one policy file; the ratifier pin lives in `[ratification].pin`.
2. **`ref` as a typed act payload** written as `"c<n>:sha256:<hash>"` for closure judgments (the bytes in 5.2), an int for `restart_from`, the member list for `batch-manifest`, an inline table for `binding`.
3. **The `batch-manifest` entry** lives in the policy chain and carries the one batch `sig`; `batch` on a member = that entry's `seq`; both `sig` and `batch` outside the chain content.
4. **The realm's binding record** as the `binding` act in the policy chain, signed `sign(realm ‖ h_binding)`; lookup by `(key_fpr, at)`.
5. **`write` takes `path`, not `card`**: the policy file and the inbox are written by the same function; the genesis prefix per document type (`card:` / `inbox:` / `policy:` / `page:` / `journal:`), each under its own registry schema version.
6. **`ratify(writes)` holds the row locks** for the signer's round trip; `time_skew` default 10 minutes; recompose on timeout; the display lists tending and hold changes since the last signed entry beside the gated diff.
7. **`Pattern` = the three-target regex intersection**; `run` is an argv array only; `FileCheck` exactly one check.
8. **Integer cost and duration** units (`cost_micro`, `duration_ms`).
9. **The execution event union** (`e<n>`) and `execution` as one current field; an event kind that shares a card act's name carries the entry's `seq`, never its content.
10. **`hold.on` as a one-key table** (`{owner = true}` / `{card = n}` / `{legacy = "…"}` / `{text = "…"}`).
11. **`retracted` always written**; `Deviated{description}` as a payload; `verdicts` optional only under the standalone dial.
12. **`GovernedPath::NewCard{slug}`** as the creation form; `show <target>` as the one read verb.
13. **`closed (pending-land)`** as a ledger-only modifier and "merged, not landed: N" in the queue; the land commit as the store's ordinary write on `main`.
14. **Kept:** `scope_mark` (hashed); `history_head` only; `cards note` semantics via `write --set updates+=`; `questions` gated; `refs` `::symbol` form; parked members do not hold the drain (T-C3 to confirm); shared-glob overlap counts; `ratification.mode = "declared"`; the neighborhood eviction order; the five `amended`-equivalent acts (round 57, grep-ability); `time` and `attribution` as belts; every enum member the round-6 review's section 4 calls deferrable (the seams stand; nothing is dropped).

**Still open from before:** default prioritization weights (02); the `judged` slot; the conformance corpus beyond the G4 minimum; `## Scope` vs `## Brief` naming; the memory tier row T-B12 (archive indexing; the integrity reasons; the wiki-page schemas, seeded from sartor's and spolia's page conventions — declared in the manifest now, not yet validated).

**The closing check — done (2026-08-21).** The round-6 scenarios re-run against this draft (`review-artifacts/2026-08-21-round6/r6-impl-d6/`, `r6-closing-check.md`): 220/220 — 148 re-run verbatim, 5 re-expressed by the pin they exercise, 67 new; every draft-5 pin landed as stated; the core unchanged (every corpus hash byte-identical to r6; four hashers agree); no contradiction, no shape-changing call. Seven pins applied in place [proposed]: **C1** the display's "changes since the last signed entry" = the tending state diff **plus** the `held`/`released`/`demoted` entries since that entry (1.11); **C2** an answer on a ratified card derives `ratified` with `fields ⊇ ["answers", "questions"]`, `answered` is a draft's act, the ledger's unpark event references whichever entry carried the answer (1.2); **C3** rule ids `log.rewritten` (Updates, History, `see`, extension lists), `claims.rewritten` (`closures`, `reopens`), `write.deletion` (1.2); **C4** a `NewCard{slug}` request may ride the batch — a card born `ratified` costs no signature of its own (1.12); **C5** the retraction exemption holds only when `D` has no gated key (1.2); **C6** "not yet landed" = the `closed` entry's `seq` > the sidecar's `history_head.seq` (1.2); **C7** a batch request whose diff needs no signature is `ratify.not-a-signed-act` (1.12). **The schema is complete in first draft.** No round 7 is planned; the next adversarial pass is the config-schema doc's.

**Follow-ups for other docs:** the config-schema doc (`04-config-schema.md` — section 10: `[toolkit]`, `[governed]`, `[history].entries`, `ratification.pin`, the `Origin` subsets, `board.commit`, `grants`, `signer.*`, the registry); 03b (the governed-document grammar, the registry, the store-as-service; the journal row, the geneses and the land pinned there in draft-6); T-C1 and T-C3 (the store as a service: the factory container as `lander` client; governed-path commits ff/merge-only; reverts through the store); **T-A10 and T-C3 (X2): land = the store's write on `main` after the batch PR merges, with the merge commit as cursor; `closed (pending-land)` and "merged, not landed: N"; fail-closed — the cursor does not advance and the next batch does not dispatch while a land is pending; land idempotent and replayable, a half-land replayed from the journal**; T-C5 (answers by any channel — a Slack-like channel later; out-of-repo access requests); T-B8/B9 (`show Board`; the queue section; the inbox section in `BOARD.md`); T-B3 (payload = canonical serialization + the neighborhood projection; `refs_resolved`, `payload_hash`, `config_hash`, `context` in the run record); T-B4/T-B6 (guidance-id coverage; `questions` empty at plan time); T-C2 (the conformance corpus incl. chain, batch-manifest and journal fixtures; the ten verbs; the NFC-key pair); T-A4 (`held` / `held_by` / `has-questions` guards); T-A12/A13 (card-side closure ids, retraction, pending review, record-only closures); T-A11 (tending keys; signed clears; the act enum with `binding`); T-C6 (the run report's bounded `suggestions[]`; the signer seam by pointer); isidium G7 (the grant system); agent-station (by pointer only — the signing service's UI, the store service, the realm); the sartor and spolia bridge sessions (the round-4 review's section 4 and V9 as inputs; "point the container at the store, install the client"); T-B12 (archives, integrity reasons, anchors, the wiki-page schemas); the per-phase agent roster (agents → grants; the interview protocol fed by the shape's required fields and `questions[]`; the morning review as the queue; the dry run before any batch; the efficiency rule as the planner's own discipline); **the v1 sequencing list** — the round-6 review's section 4, by pointer: deferrable with the seam named per row; it removes nothing from this schema's enums or mechanisms.
