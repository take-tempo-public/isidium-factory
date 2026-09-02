<!-- provenance: schema=1 project=the-factory(working-label) session=2f342ec4-8a35-4cf5-a9d8-d11d35e5db70 actor=amodal1 agent=anthropic/claude-fable-5 generated_at=2026-08-15 status=draft-0 -->

> **Assumes:** the reader has the sync record (`00-sync-record-2026-08-14.md`) and isidium I-34 (transitions are first-rate; species adapter / transducer / held) at hand.
> **Descends from:** sync-record decision 3.9 ("the design's core artifact is a transition catalog, not a layer diagram" — owner frame, catalog [proposed]); the owner's EFT frame ("contracts and enforcers IN THE TRANSITIONS"); the round-11 ratifications (fingerprint field split, ledger-derived execution state, dependency-safe skip).
> **Expected reader:** the owner at the shape checkpoint; then the card-schema session, which consumes the vocabulary fixed here.
> **Does not cover:** field-level card schema (next doc); the per-phase agent roster (later walk); tenant-specific governance extensions.
> **Status:** draft-0, **catalog complete in first draft (2026-08-16)** — shape ratified, all 32 crossings worked (section 2), inventory reviewed against the worked rows. Rows are [proposed] except where marked; leans taken as `[proposed-default]` per the owner's 2026-08-16 "yes on all". Everything here is **[proposed]** unless it quotes a sync-record decision by number or carries its own mark. **Owner-ratified 2026-08-16:** the graph model (typed vertices, multigraph edges, one species per edge, run-time determinism firebreak, intensity as a field) and the extensibility/mutability model "c" (fixed core + transitions-as-data). Rows remain [proposed] except where marked. **Owner-ratified 2026-08-16 ("confirmed", round 15):** guard-edge conjunction; per-story branch off rolling; execution-state sidecar; answer channels by source tag; drift-during-run = fail; deps closed-on-rolling or landed-in-main; ratification path = `main` (+ `cards/**` path rule as tenant option); sync `main`→rolling before every dispatch; hotfix owner-lane default with card-lane dial; write-through board in the planning surface; in-project board committed.
> **2026-08-26:** rows reconciled with 03 draft-6, 03a, 03b, 04 (complete in first draft) — see each row's citations; sync record rounds 7ba–7bd.

# Transition catalog — the factory (working label)

## 0. Why a catalog, and what a row is

The owner's frame: layers are effective theories with their own
vocabularies; **contracts are matching conditions at scale boundaries;
enforcers sit on the crossings**; non-negotiables are relevant operators
that need a transformed representative on each side, checked at the
matching — not remembered by the agent. Isidium I-34 makes each crossing a
first-class component with a declared **species** that assigns its
verification regime, and G-SYM-3 says *no bare seams* — every seam
declares its species.

So a **row** in this catalog is one crossing, and it must answer, in fixed
order: what vocabulary is on each side; what must match; how the match is
observed; what enforces it; what species it is (and therefore how it is
verified); what it costs in model calls; what happens on failure and how
recovery is deterministic; what it emits; what it writes and who holds
authority over that write.

### 0.0 The graph model **[owner-ratified 2026-08-16]**

The catalog is a **typed multigraph**. It is the owner's "no bare edges"
rule (isidium G-SYM-3: relations carry type, direction, intensity; a graph
with one edge kind collapses) applied to the factory's crossings.

- **Vertices are typed and heterogeneous:** card **states** (draft,
  ratified, dispatched, parked, closed…), **registers** (narrative, card,
  payload, plan, findings, board, queue), and **systems** (project
  checkout, forge, notifier, owner). Declaring a new *state* is a vertex
  declaration; declaring a new *crossing* is an edge declaration — two
  different extensions.
- **Edges are transitions. A pair of vertices may carry many edges;
  each edge carries exactly one species.** The relationship between two
  vertices is the *set* of typed edges between them, never one edge whose
  type is negotiated. An edge that is "adapter or transducer depending" is
  a bare seam and is forbidden.
- **Edge identity** is at least `(from, to, direction, trigger, kind)`.
  Species does not identify an edge; the same pair may carry an adapter
  and a transducer, or a hard edge and an advisory one.
- **Run-time firebreak: one crossing follows one edge.** Given
  `(from-vertex, trigger, direction)` the registered set resolves to
  exactly one edge, whose contract, enforcer, and failure protocol fire.
  Two registered edges with the same `(from, trigger, direction)` are a
  **registration defect** — the factory refuses to load the set. At design
  time, or on a *held* edge, conflict is a typed difference (I-34), not a
  defect forcing a winner; the registered set is the stricter regime
  because the deterministic core cannot tolerate a nondeterministic pick.
- **Intensity is a field** — hard / advisory / held — not something buried
  in the enforcer prose. The dependency-safe skip is the first case: a
  hard-block adapter and an advisory transducer on the same pair.

Already-visible multi-edge pairs, for orientation: draft↔ratified (a
transducer forward, an adapter sub-crossing on the same endpoints, and a
reverse drift edge reusing the adapter's round-trip); ratified→ready
(hard block + advisory overlap); executor↔owner (a held edge for the
question, an adapter edge for the answer); cards→board and cards→queue
(one source, two targets, deliberately not composed).

### 0.1 Row shape [proposed; intensity / extensibility / change-governance fields owner-ratified 2026-08-16]

| Field | Meaning | Charter root |
|---|---|---|
| **Id / name** | `T-<family><n>` and a verb phrase | — |
| **Family** | **A** card lifecycle · **B** scale/register (SDD→BDD→TDD and the projections) · **C** boundary (factory ↔ project ↔ forge ↔ owner) | 3.9 |
| **Endpoints** | typed from/to vertices (state · register · system) and direction | 0.0 |
| **Kind** | **written** — a record changes (card save, ledger append, commit) · **derived** — a projection computes it at read time, nothing is written | 3.1–3.4 |
| **Above / Below** | the register on each side and its native vocabulary | I-34, EFT frame |
| **Trigger / actor** | who or what initiates: owner+agent session · picker · executor · batch commit · hook · projection read | 5.1 |
| **Matching conditions** | the contract: what must hold on both sides for the crossing to be legitimate — the operators that need a representative on the far side | EFT frame |
| **Matched observables** | the concrete checkables that witness the match: hashes, typed verdicts, ledger entries, file existence | 3.8, I-31 |
| **Enforcer** | mechanical (validator / hook / projection code / gate) **and** narrative (template guidance / skill checklist) — both, never narrative only | 4.2, 4.3 |
| **Intensity** | **hard** — blocks the crossing · **advisory** — emits and lets a configured cut decide (warn / defer / owner) · **held** — the seam is not crossed; the gap is the signal | 0.0, 3.8 |
| **Species (I-34)** | **adapter** — within-register; fidelity is the bar; verified by round-trip diff · **transducer** — cross-register; loss and gain constitutive; bar is a declared characteristic (preserves / colors / discards / adds); verified by characterization + conformance scenarios, never round-trip · **held** — deliberately uncrossed; a conversion appearing there is a defect | I-34 |
| **Model calls** | none · which phase, which class, wrapped how | 4.1 |
| **Failure protocol** | fail-closed direction; resulting state; typed error; the deterministic recovery step | 4.4, 5.6 |
| **Emits** | the measure(s) this crossing reports for telemetry and tuning | 4.7, I-31 |
| **Writes / authority** | which store changes (card in project · factory ledger · projection · branch) and who is authoritative for it | 7b.3, 7d.1 |
| **Extensibility** | **fixed-core** — shipped and versioned by the factory only; tenants cannot alter · **tenant-specializable** — core mechanism, tenant-configured thresholds/policy · **tenant-defined** — declared wholesale by a tenant against the transition schema | 0.2 |
| **Change governance** | the row's version; who may change it; what re-validates or re-runs on change (consumer enumeration, C-10 style); how the change reaches tenants | 0.2, 7b.7 |
| **Brownfield note** | how sartor / spolia do it today, as evidence | 2.7 |
| **Open** | unsettled points, for the checkpoint | — |

### 0.2 Extensibility and mutability — model "c" **[owner-ratified 2026-08-16]**

Transitions are **data**, with a **fixed core** the tenants cannot alter.

- **The transition schema** — the row shape above as a strictly typed
  model (pydantic, per 4.1/4.6). Every transition the factory runs is an
  instance of it; the schema is versioned; an instance that fails
  validation is not loaded (fail closed). Registration validates the
  graph rules of 0.0 (typed endpoints, one species per edge, no duplicate
  `(from, trigger, direction)`, no bare seams).
- **The fixed core** — the rows the fingerprint and ledger authority hang
  on: capture, ratification, gated drift, dispatch, attempt outcome, land,
  tending edits, human closure, the executor↔owner interrupt, and the
  cross-tenant held seam. Shipped by the factory, changed only by a
  factory schema-version bump; a tenant on an unsupported version is not
  dispatched, and is told so (the C-1 rule). *Why fixed:* these are the
  crossings a tenant must not be able to weaken from inside its own repo —
  a tenant-editable ratification edge is a self-reported fingerprint by
  another route (I-13).
- **Tenant-specializable** — core mechanism, tenant-owned dials in the
  tenant's threshold config (readiness rules, skip overlap policy, close
  criteria for non-code tenants, review effort tier, batch cadence,
  notifier channel). Changed only through the tenant's ratification path
  (7b.7); the config is versioned and committed in the project.
- **Tenant-defined** — new vertices (states) and new edges a tenant
  declares wholesale against the schema (a governance extension such as
  sartor's closure bar or spolia's merge rule; a new forge or execution
  driver). Must declare species and intensity; must not collide with a
  core edge's `(from, trigger, direction)`.
- **Mutation of any registered transition** = a version bump on that row
  + the enumerated consumers re-validated (validator, hasher, projections,
  vendored snapshot, in-flight runs). Core mutations are factory releases;
  tenant mutations are tenant commits on the ratification path.
- **This document's role over time:** during design it is the source. Once
  the schema exists, the catalog is **generated as a projection of the
  registered set** (core + each tenant's extensions), and this file's rows
  become the core's seed data. Fidelity check: regenerate and compare, the
  same discipline the board gets.

### 0.3 Actor identity **[owner directive 2026-08-16; mechanics proposed]**

Owner, verbatim: *"we need to make sure that each bot writing code has
it's own git identifier and github account if it isn't in an interactive
session with me."* Research note: `../research/agent-identity-2026-08-16.md`.

- Every written crossing names its **actor identity**, and identity is a
  first-class key on every ledger record and run, beside tenant.
- **Non-interactive bots** commit under their own git identity and forge
  account (per bot / per phase-role, never "Claude"), signed with the bot's
  own key, with a trailer naming the run (`Factory-Run: <tenant>/<run-id>`)
  so the ledger record is the commit's admission justification.
- **Interactive sessions** commit as the owner, with `Co-authored-by:` for
  the agent.
- **Ratifier lists name humans.** A bot identity can never qualify a
  ratifying commit — identity is the mechanical enforcer of "the factory
  never edits a card beyond execution state."
- **Grants vs agents — two words, never "role" [owner-ratified 2026-08-21
  (03 §1.12, round 57)].** The store's permission sets are **grants**
  (`owner` · `contributor` · `lander`); the roster's kinds are **agents**;
  the binding reads `agent → identity → grant`. An agent has a prompt; a
  credential holds a grant; **the builder holds no store credential** —
  its writes are code inside `surfaces` and a typed report (suggestions
  ride it, T-C6). Wiring each bot identity above to exactly one grant is
  the per-phase roster's mechanics [proposed]; the grant check ships as
  one function over a G7-shaped matrix (04 §2.2).
- Forge portability: a bot is "a user with a signing key" on GitHub and
  Gitea/Forgejo alike; only provisioning differs (driver seam T-C7).
  Workload identity above git (SPIFFE-class) is agent-station's layer; the
  factory carries bot identity in a shape that layer can bind to later.

### 0.4 Standalone posture — building without our factory **[owner-ratified 2026-08-16]** ("yes on standalone")

Choosing (b) makes "ratified" a property computed by **policy + validator
+ hasher at a versioned revision** — a definition, not a service. So the
dependency it creates is on the **vendored toolkit**, not on the factory.

- **The toolkit** — card template + schema, validator (`cards check`,
  pre-commit hook), hasher + canonicalization, policy reader, board
  renderer, provenance-stamped and version-pinned — is **standalone-
  capable**: a project can author, validate, project its board, and see
  ratification/drift state from `git log` alone. This is the deliverable
  7b.3 already names ("the factory holds the templates and generators that
  can instantiate tracking into any project") and is isidium's harvest
  candidate #3 (work-item schema + board) made concrete.
- **Ratification is a tenant dial, not a toolkit requirement.** Standalone
  default: *validate on commit; a validated card with `status: ratified` is
  ratified; no ratifier list.* Factory mode adds the ratifier list and the
  ledger as dispatch authority. Rationale: enforce at the crossing that has
  a consumer — the fingerprint's consumer is the dispatcher; with no
  dispatcher, emit the measure, don't gate on it (I-31).
- **Nothing factory-specific is required in a card.** Execution-state
  fields are optional and ledger-derived; a project never carries a factory
  endpoint, token, or run id to be valid.
- **Any dispatcher can ingest.** The ratifying-commit contract is git-
  native and forge-neutral, so a project using the toolkit is integrable
  with *a* factory, not only ours — the toolkit defines the contract; the
  factory is one consumer of it.
- **Should the toolkit be necessary for development outside our flow?**
  Position: *useful, not necessary.* Its value without the factory is the
  discipline itself — acceptance at filing, deterministic board, no
  projection-fidelity bugs — which is why sartor and spolia adopt it back
  regardless. Mandating it beyond that would be a ceremony without a
  consumer.
- Declared limits: needs git (or an equivalent attributable log); the
  standalone "ratified" and the factory's "ratified" agree only at the same
  toolkit revision — the version pin and provenance header carry that.

Two further shape choices worth the owner's eye before this is multiplied:

- **Written vs derived.** Several "states" the sync record names —
  *ready*, *unratified*, *blocked-by-skip* — are not written anywhere; they
  are computed by a projection from cards + ledger + threshold config at
  read time. The catalog proposes to carry them as **derived crossings** in
  their own rows (they have contracts and enforcers too) but to keep the
  distinction explicit, because it decides what the card schema must
  *store* versus what it must merely make *computable*. **[proposed]**
- **Matching conditions ≠ matched observables.** The contract (what must
  hold) and the witness (how it is checked) are kept as separate fields so
  that a contract with no observable is visible as a gap — that is
  precisely the "prose given where a contract was needed" failure the
  round-3 input named. **[proposed]**

## 1. Inventory [proposed]

Titles and one-line stubs only; each becomes a full row after the shape is
agreed. Kind, species, intensity, and extensibility are first guesses for
the owner to react to. Extensibility: **core** = fixed-core · **spec** =
tenant-specializable · **def** = tenant-defined.

### Family A — card lifecycle

| Id | Crossing | Kind | Species | Intensity | Ext | Row | Status |
|---|---|---|---|---|---|---|---|
| T-A1 | capture: observation → **draft** | written | transducer | hard (draft profile) | core; source vocab spec | 2.9 | bot drafts superseded by the suggestion inbox (03 §1.18, round 28); dashboard inbox ratified |
| T-A2 | ratification: draft → ratified | written | transducer + adapter (hash) | hard | core (+ tenant gated fields) | 2.1 | attribution (b) + path `main` ratified |
| T-A3 | gated drift → **unratified** · sidecar → **state-divergent** | derived | adapter | hard | core | 2.10 | design-queue-as-view ratified |
| T-A4 | readiness → **ready** (guard) | derived | adapter | hard | core; thresholds spec | 2.2 | guard-edge conjunction ratified |
| T-A5a | skip tier 1: transitive-deps block (guard) | derived | adapter | hard | core | 2.2 | ratified (7d.5) |
| T-A5b | skip tier 2: declared-surface overlap (guard) | derived | transducer | advisory (cut) | spec | 2.2 | ratified (7d.5) |
| T-A6 | dispatch: ready → **dispatched** | written (ledger) | adapter | hard | core; WIP/adapter/budgets spec | 2.11 | WIP 1 ratified; ordering → `02-prioritization.md` |
| T-A7 | attempt outcome → **complete / failed:<class> / parked / disputed** (disputed 2026-08-27, the roster review's disputed-exit pin — 05 §3, 03 §6) | written (ledger) | adapter | hard | core; budgets spec | 2.12 | budgets-in-config ratified |
| T-A8 | answer: parked → **answered** → re-dispatch | written | adapter | hard | core; channels spec | 2.5 | channels-by-tag ratified |
| T-A9 | close: complete → **closed** (or failed) | written (branch + ledger) | adapter | hard (+ advisory surfaces) | core; gate/close criteria spec | 2.3 | per-story branch, drift=fail ratified |
| T-A10 | land: ledger → sidecar execution state | written (store commit on `main`, post-merge) | adapter | hard | core | 2.4 | sidecar + land-on-`main` (X2 — sync 7ba.4) ratified |
| T-A11 | tending: priority, demotion | written (card) | adapter | hard (validate) | core; tenders spec | 2.13 | in-flight → `complete-but-demoted` ratified |
| T-A12 | human closure → **closed:human** (verified) | written + verified | transducer | hard | core; close criteria spec | 2.14 | mandatory acceptance + no-silent-closure ratified |
| T-A13 | reopen: closed → ratified | written | adapter | hard | core | 2.15 | id kept ratified |

### Family B — scale / register transitions

| Id | Crossing | Kind | Species | Intensity | Ext | Row | Status |
|---|---|---|---|---|---|---|---|
| T-B1 | narrative → card | written | transducer | advisory authoring / hard at T-A2 | core; narrative resolver spec | 2.16 | epics-as-cards ratified |
| T-B2 | acceptance → manifest | written (artifact), derived | transducer | hard | core dialect; runners spec; kinds def | 2.17 | proposed |
| T-B3 | consume → payload | written (artifact) | adapter | hard | core; assembly rules spec | 2.18 | proposed |
| T-B4 | plan → refutation → verdict | written (artifacts) | transducer | hard | core; models/effort spec | 2.19 | judge = model; plan author; park on 2nd failure (05; 7bd.9/.10/.13) |
| T-B5 | build → diff | written (branch) | transducer | hard (+ advisory self-run) | core; model/guard threshold spec | 2.20 | wrapper-commits (default) |
| T-B6 | review → findings → verdict → reconcile | written (artifacts) | transducer | hard | core; refuter/panels spec | 2.21 | panel trigger (default) |
| T-B7 | run → close report | written (ledger) | adapter | hard | core | 2.22 | proposed |
| T-B8 | cards → board | derived (store-rendered, committed file — 03 §1.16) | adapter | hard | core; style spec | 2.7 | write-through-in-planning-surface + committed ratified |
| T-B9 | cards + ledger → queue | derived | adapter | hard | core; thresholds spec | 2.7 | proposed |
| T-B10 | ledger → dashboard | derived | adapter | hard (no writes) | core; views spec | 2.23 | snapshots-on-volume (default) |
| T-B11 | scenario → Gherkin / EARS | derived | adapter | — | def (optional) | 2.24 | settled (1.5; isidium 0003) |
| T-B12 | substrate + ledger → memory tier (`Source` units for the tenant's and the factory's grounded assistant) | derived | adapter | hard (read-only; audience `dev`; index never author) | def (optional) | — (row to be worked; shape in `03-card-schema.md` 1.9; wiki/recall page schemas declared in `[[governed]]` now, validated when worked — 03b §3) | **owner-ratified 2026-08-16 ("land it")** with conditions; row [proposed] |

**T-B12 note (2026-08-26, since 03 §1.9 / 03b §3 — sync 7bb.1) — row still
to be worked.** The wiki and recall page schemas are **declared in the
`[[governed]]` manifest now and validated when this row is worked** — a
declared state, not a deferral (03b §3, round 57). The schema doc's
obligation to the tier is pinned [owner-ratified]: every record carries a
**stable citation anchor + a sha** (card / scenario `S<n>` / rule `R<n>` /
question `Q<n>` / closure `c<n>` / reopen `o<n>` / suggestion `s<n>` /
disposition `d<n>` / event `e<n>` ids; run, batch, Updates `#u<n>` and
history `#h<seq>` anchors; build hash, closure-entry hash, `h`, journal
hash, commit, cursor — 03 §1.9), and the integrity reasons of 03 §1.15 are
indexed — *"if there is a conflict, we need to understand why"* (owner,
round 24).

### Family C — boundary transitions

| Id | Crossing | Kind | Species | Intensity | Ext | Row | Status |
|---|---|---|---|---|---|---|---|
| T-C1 | factory ← project checkout → `TenantContext` | derived | adapter | hard | core; refs/paths spec | 2.8 | proposed |
| T-C2 | vendoring: factory release → project toolkit | written (PR) | adapter | hard | core; what-to-vendor spec | 2.25 | proposed |
| T-C3 | rolling branch lifecycle → batch PR → `main` | written (bundle) | adapter (merge: held→adapter) | hard | core; cadence/hotfix spec | 2.6 | path `main`, sync, hotfix, land-on-`main` (X2 — sync 7ba.4) ratified |
| T-C4 | line → notifier | written (event) | adapter | advisory (inbox is the record) | core vocab; channels spec/def | 2.26 | proposed |
| T-C5 | executor → owner: the question | — | **held** | held | core | 2.5 | ratified model (5.7, 7.2) |
| T-C6 | execution adapter seam | seam | adapter | hard | core contract; adapters def | 2.27 | proposed |
| T-C7 | forge driver seam | seam | adapter | hard | core contract; drivers def | 2.28 | proposed |
| T-C8 | cross-tenant view | derived | **held** | held | core; capacity instance-spec | 2.29 | proposed |

**Inventory review (2026-08-16):** guesses reconciled with the worked rows —
T-A5 split into two guard edges; T-A8 reduced to the adapter (the held
question moved to T-C5); T-A7's outcome vocabulary is `complete / failed:<class> / parked / disputed` (2026-08-27);
T-A12 became a transducer (claim → verified closure); T-B1's intensity is
advisory at authoring; T-C3's owner merge is the one held-then-adapter
step; T-C4 is advisory because the inbox, not the push, is the record.

## 2. Worked rows

### 2.1 T-A2 Ratification: draft → ratified [proposed]

Chosen first because it is the owner's gate (5.1), the crossing the
fingerprint hangs on (7c.2, 7d.1), and the most decision-dense row.

**Family / kind.** A · **written** — a card save in the project **and** a
fingerprint record in the factory ledger.

**Endpoints.** state `draft` → state `ratified`, forward. Two edges on
this pair are described here: the main **transducer** edge (trigger:
owner save in session) and the **adapter** sub-crossing (trigger: the same
save; card bytes → gated hash). The reverse edge `ratified → unratified`
is T-A3 and is not this row.

**Above.** The design session: owner + agent in VS Code + Claude CLI (5.9).
Vocabulary: *draft card*, intent in prose, acceptance scenarios in the
house dialect with TDD requirements nested (3.5), effort tier (7b.4),
`depends_on`, priority, tenant governance extension fields, the ARC-level
narrative the card points at. Register: narrative + behavior, under human
judgment.

**Below.** A **ratified card record** at the tenant's card path, well-formed
against the vendored template and schema version; a **ledger fingerprint
record** in the factory — `{tenant, card_id, schema_version, gated_hash,
ratified_at, ratified_by, validator_version}`; the board projection
regenerated. Register: typed records; the line's vocabulary.

**Trigger / actor.** The owner, in session with the agent. **The save is
the ratification** (3.7).

**Matching conditions.**
1. Produced *through* the template (4.2) — template id and version present.
2. Schema-valid: strictly typed fields; schema version pinned and supported.
3. Acceptance block present, in the house dialect, TDD requirements nested,
   and every scenario **runnable-shaped** — it names a checkable observable.
   Presence is not enough; shape is the contract.
4. Effort tier set (single tier, 7b.4).
5. `depends_on` resolves to existing card ids; no cycles.
6. Priority set.
7. Tenant governance extension fields valid against the tenant's extension
   schema.
8. Every draft-tier exemption lifted: what a draft may omit, a ratified
   card must carry.

**Matched observables.**
- The validator's **typed verdict**: per-rule pass/fail with rule ids and
  locations (never a bare boolean).
- The **gated-set hash** — over title, acceptance block, scope/body,
  effort tier, `depends_on`, governance extension (7d.1) — computed by the
  factory's hasher under a **declared, versioned canonicalization**
  (field order, whitespace, line endings). The canonicalization is part of
  the contract; two hashers that disagree are a defect at this seam.
- The ledger record exists and carries that hash.
- Card frontmatter carries `status: ratified` and `schema_version`. The
  card does **not** self-report the hash as authority (isidium I-13); it may
  carry a human-readable pointer to its ledger record — open.

**Enforcer.**
- *Mechanical:* the vendored `cards check` validator on the save path —
  **validate → save → ledger record**, in that order; a save with
  `status: ratified` is refused when validation fails; the same validator
  runs as the project's pre-commit hook so CI stays green without the
  factory (7b.3).
- *Narrative:* the card template's inline guidance and the authoring
  skill's checklist. Both together (4.3).

**Intensity.** **Hard.** A failing match blocks the ratified save; there is
no advisory tier at this edge — the owner's gate is not a dial.

**Species.** **Transducer** for the main crossing — a design conversation
becomes a typed record. Declared characteristic: *preserves* intent as
acceptance scenarios and scope as body; *discards* the conversation, the
alternatives considered, the reasoning; *adds* ids, structure, the hash.
Verified by characterization + conformance scenarios over the validator
(e.g. "a card whose acceptance block has no checkable observable does not
ratify"), never by round-trip. **Adapter sub-crossing:** card bytes →
gated hash — fidelity; verified by recompute-and-compare, which is exactly
the check T-A3 reuses.

**Model calls.** **None at the crossing.** The session upstream uses a
model (the interactive planner/authoring agent); the enforcer is
deterministic. Declared gap: the validator checks *shape*, not whether a
scenario is *meaningful* — that judgment is the owner's, and that is what
makes this the human gate.

**Failure protocol.**
- Validation fails ⇒ card stays draft; ratified save refused; typed error
  list returned to the session. Recovery: fix the listed rules, re-run.
  Deterministic.
- Ledger unreachable at save time ⇒ see Open (1) — two candidate shapes,
  both fail closed (nothing dispatches on a card with no ledger fingerprint).
- Post-save gated edit ⇒ not this row's failure — it is T-A3 (drift).

**Emits.** Validator verdict per rule (pass/fail rates over time → template
tuning); time-in-draft; ratifications per session; re-ratification count
per card (drift frequency).

**Writes / authority.** Card file — project, canonical, owner-authored.
Fingerprint — factory ledger, authoritative; read-only snapshot vendored
into the project for the local hook's *warn* (7c.2e). Board — derived,
regenerated. Queue — untouched (derived at pick time).

**Extensibility.** **Fixed-core.** Tenants may add governance-extension
*fields* to the gated set (declared in the tenant's extension schema, so
the hasher covers them), but may not alter the edge's contract, enforcer
order, or intensity — a tenant-editable ratification edge is a
self-reported fingerprint by another route (I-13).

**Change governance.** Row version tied to the factory schema version.
Changing the contract (gated-set membership, canonicalization, validator
rules) is a factory release with a schema-version bump; enumerated
consumers that re-validate: the vendored validator, the hasher, the
ledger's fingerprint record schema, the vendored ledger snapshot, the
board and queue projections, and any in-flight run's payload. Rollout is
fail-closed by T-C1: a tenant whose vendored version is unsupported is not
dispatched, and is told so. Existing fingerprints computed under the old
canonicalization are re-hashed at ingest under the new one, or the card
projects `unratified` — which is the safe direction.

**Brownfield note.** Neither sartor nor spolia has a ratification step:
items go from filed to open in one write, with `decision_owner` as the
human-gate field; the closest analogue on the *close* side is sartor's C-11
falsifiable-closure bar. Both projects' `work_items.py` schema check is the
nearest thing to the validator (exact invocation to be verified before
citation).

**Attribution — RESOLVED [owner-ratified 2026-08-16]: (b), the ratifying
commit.** The owner's save is a commit on the project's **ratification
path**; tenant policy declares allowed ratifiers (humans — bot identities
are excluded by construction, see 0.3), allowed branch/paths, and whether
signed commits are required. The factory ingests from git history at
checkout (T-C1) — walking from its ingest cursor, per card, to the latest
qualifying commit that changed the gated set — and records the gated hash
computed from content at that commit with `{commit_sha, author,
committed_at, ingested_at}`. Working-tree hash ≠ recorded hash ⇒
`unratified` (T-A3). Ingest is push-triggered where the forge allows
(Actions on push / webhook) and polled otherwise. Ingest keys on
content-at-latest-qualifying-commit, never SHA equality, so rebases do not
un-ratify. Consequences: (i) the ledger's fingerprint record is **derived**
(recomputable by re-ingest) while run outcomes stay **primary** — two
record kinds in one ledger; (ii) the vendored local hook can compute
ratification drift from `git log` + policy alone (no snapshot needed for
this); (iii) owner-writes-by-commit and factory-writes-by-batch-commit
share one channel. Rejected (a), ledger-write-at-save: it made the owner's
gate depend on the line being reachable and added a second identity system
and an inbound write surface. Declared limit: (b) needs a VCS with
attributable history; a non-git tenant needs an adapter providing an
equivalent append-only attributable log.

Two policy questions (b) forces, still open:
- **Commit = ratify collapse.** For a ratifier, any qualifying commit that
  changes the gated set is a (re-)ratification (the pre-commit hook blocks
  invalid ratified cards, so validation-then-save holds). Committing WIP on
  a ratified card without re-ratifying means demoting it to draft or
  keeping the work off the path — the tenant policy must say which.
- **Which ref is the ratification path** — `main` only, or the rolling
  branch too — **deferred by the owner (2026-08-16) to the rolling-branch
  discussion (T-C3)**; decided there, not here.

**Open — for the checkpoint.**
1. ~~Attribution~~ — resolved above.
2. Whether the card carries a human-readable `ratified_ref`.
3. The canonicalization rules for the gated-set hash — must be declared,
   versioned, and vendored with the validator.
4. Where the tenant governance extension schema lives (in the tenant's
   threshold config, per 7b.3?).
5. Mechanism for re-validation after tending edits: hook on save, or lazy
   at pick — 3.7 says re-validate; the where is open.

### 2.2 T-A4 / T-A5a / T-A5b Readiness: ratified → ready [proposed 2026-08-16]

**Family / kind.** A · **derived** — nothing is written; the ready-view
projection computes it at read time from cards + ledger + tenant threshold
config.

**Endpoints.** state `ratified` → derived state `ready`, forward. **Three
edges on this pair, all evaluated at the same trigger:**
- **T-A4 base readiness** — adapter, hard: status/ratification/in-flight
  checks and the tenant's threshold rules.
- **T-A5a transitive-dependency block** — adapter, hard: no card in the
  transitive `depends_on` closure is unclosed, parked, or attempt-failed.
- **T-A5b declared-surface overlap** — transducer, advisory: the candidate's
  predicted surfaces vs the declared surfaces of every parked story; cut
  from tenant config (`warn` / `defer` / `owner`), default `defer`.

**Graph-model refinement this row forces [owner-ratified 2026-08-16].** The run-time
firebreak (one `(from, trigger, direction)` → one edge) was written for
*written* crossings, where a traversal has effects. Derived crossings on
one pair are **guard edges** and compose by **conjunction**: every guard
evaluates; hard guards must all pass; each advisory guard emits its
measure and its configured cut applies. Conjunction is commutative and
each guard is a pure function of its inputs, so the composed verdict stays
deterministic. Registration rule: guard edges may share
`(from, trigger, direction)`; written edges may not. This is a refinement
of the ratified model, not a change to it — **ratified**.

**Above.** The substrate and its companions: card records (`status`,
`depends_on`, priority, effort, refs from which predicted surfaces are
read); the ledger (fingerprints; run states: dispatched / parked / failed /
closed; batch cursor); the tenant threshold config (readiness rules,
priority floor, WIP cap, batch membership, overlap policy); plan artifacts
of parked stories (declared touched surfaces). Register: records.

**Below.** The **ready-view** — an ordered list of dispatchable card ids,
each with a typed `ReadyVerdict` (`ready` | `unratified` | `blocked_by:
[ids]` | `parked` | `failed` | `deferred_by: [{parked_id, surfaces}]` |
`below_threshold: [rule ids]`) and an ordering key. Register: dispatch.
The board renders the same verdicts as read-only labels (T-B8).

**Trigger / actor.** The picker's pick-time evaluation (T-A6) and the board
render (T-B8) — one computation, two consumers. The vendored in-project
hook computes the *partial* view it can (drift and dependency structure
from git; not run states, which need the ledger) and says so.

**Matching conditions.**
1. Ratified: working-tree gated hash == ledger fingerprint (T-A3 result).
2. Status dispatchable: `ratified`, not closed / in-flight / parked.
3. *(A5a)* Every card in the transitive `depends_on` closure is **closed**
   (on the current rolling branch or landed in `main`); none is parked or
   attempt-failed. Cycles are a defect (prevented at ratification; if
   found, all members blocked + typed owner interrupt).
4. Not currently dispatched (ledger).
5. A previously **failed** attempt of this card ⇒ not ready until
   re-ratified — the failure's implied scope error returns it to the design
   queue (3.7). *Except* infrastructure-class failures, which retry once
   (see T-A9 failure classes).
6. Tenant threshold rules satisfied (priority floor, WIP cap, batch
   membership, allowed effort tiers…).
7. *(A5b)* Predicted-surface overlap with any parked story ⇒ flag; the cut
   decides.
8. Ledger and config **readable and valid** — otherwise nothing is ready.

**Matched observables.** The `ReadyVerdict` per card with typed reason
codes; the ready-view artifact (ordered ids + verdicts); the ledger cursor
and config version hash the verdicts were computed under (so any verdict
is reproducible); the board's ready set == the queue's ready set
(fidelity check).

**Enforcer.** *Mechanical:* the projection is a pure function
`(cards, ledger snapshot, config) → ready-view`; the picker refuses to
dispatch any card not in the ready-view; the projection refuses to run on
unreadable ledger/config; the board render asserts ready-set equality
with the queue (the header-population defect class guard). *Narrative:*
the threshold-config docs and the card template's `depends_on` guidance.

**Intensity.** A4 hard · A5a hard · A5b advisory.

**Species.** A4/A5a **adapter** — a projection of the substrate; fidelity
by recompute-and-compare, deterministic given inputs. A5b **transducer** —
declared intent → risk flag; characteristic: *preserves* declared paths,
*discards* undeclared touches (the known limit), *adds* a policy cut;
verified by conformance scenarios ("a candidate whose predicted surfaces
intersect a parked story's declared surfaces is deferred under default
policy").

**Model calls.** None.

**Failure protocol.** Ledger or config unreadable/invalid ⇒ empty
ready-view + typed error, no dispatch (fail-closed). A5b inputs missing
(a parked story with no plan artifact) ⇒ `defer` for every candidate whose
overlap cannot be evaluated. Cycle ⇒ members blocked + owner interrupt.
Recovery: repair the input, re-run — the projection is idempotent.

**Emits.** Counts by verdict; time-in-ready per card; overlap flags
(so the cut can be tuned from data); blocked-by depth; how often the
partial in-project view disagrees with the factory's (a fidelity measure).

**Writes / authority.** Nothing written; the ready-view is materialized
in the factory, ephemeral, regenerable; authority = projection version +
inputs.

**Extensibility.** A4 mechanism and A5a **fixed-core**; A4's threshold
rules and A5b's cut **tenant-specializable**.

**Change governance.** Projection function and config schema versioned;
consumers on change: picker, board renderer, dashboard, vendored hook.

**Brownfield note.** Neither project has a ready query; only sartor has
`depends_on`; the mirrored BOARD.md header population-mix bug is exactly a
board≠queue fidelity failure — this row makes that comparison a gate.

**Since 03 draft-6 (03 §1.5 rows 10–11, §1.8; sync 7bb.1) [owner-ratified;
reconciling mechanics proposed].** The guard vocabulary is pinned:
`has-questions` · `held(kind)` · `held_by(parent, kind)` · `blocked_by[ids]`
· `deferred_by[ids]` · `below_threshold` — **`has-questions` renders before
`held`** (W5); **container holds propagate** (`held_by(parent, kind)`) and
release with the container; a card whose dependency is `closed
(pending-review)` or `withdrawn (pending)` is **`blocked_by` it** —
pending-review and pending-withdrawn are not terminal and are
`held`-equivalent for their dependents (03 §1.5). `ready` is row 11's "in
the ready-view": the newest signed entry, `questions` empty (blocking for
ready, advisory for ratification — 03 §1.12), none of the guards. The
`ReadyVerdict` vocabulary above predates this and reads through it.

**Open.** ~~(1) Guard-edge conjunction~~ — ratified. ~~(2) "Dep closed" =
closed on the current rolling branch **or** landed in `main`~~ — ratified
(both count). (3) Failure
classes: which failures return to the design queue vs retry — lean: typed
classes, `scope`/`ambiguity` → design queue, `infra` → one retry.
(4) Ordering key beyond priority (age? effort?). (5) WIP cap per tenant as
a threshold rule. (6) How much the in-project hook should compute without
the ledger.

### 2.3 T-A9 Close: run complete → closed onto the rolling branch [proposed 2026-08-16]

**Family / kind.** A · **written** — branch + ledger. Phase 8 of the story
flow; no model calls.

**Endpoints.** state `dispatched` (all phases through reconcile complete,
per T-A7) → state `closed`, forward. The alternative outcome on the same
trigger is `failed` (a different target vertex, so a different edge —
T-A9-fail — sharing this row's contract).

**Above.** The executor's checkout: the story's commits (author = the run's
**bot identity**, signed, each with `Factory-Run: <tenant>/<run-id>`); the
run's artifacts (plan with declared surfaces, findings, verdict, reconcile
result, close report); the acceptance suite derived from the card's
acceptance block (T-B2); the tenant's full-gate command from threshold
config.

**Below.** The rolling branch advanced by the story's commits; a ledger
record `{run_id, card_id, outcome, head_sha, acceptance_ref, gate_ref,
surfaces_declared, surfaces_actual, models+effort per phase, cost,
duration}`. Card file **untouched** — card state lands at T-A10.

**Trigger / actor.** The executor, deterministically, after reconcile.

**Matching conditions.**
1. Acceptance suite **green** — every scenario in the card's acceptance
   block has a run record; none skipped.
2. Full project gate **green** (tenant gate command).
3. Working tree clean; every commit since dispatch is authored by the run's
   bot identity, signed, trailer present; **no commit touches a card's
   gated or tending fields** (hash before == after; the same hasher as
   ratification).
4. Card gated hash at close == hash at dispatch (**no drift during run**).
5. Declared vs actual surfaces compared; mismatch **emitted** (advisory:
   undeclared touches are listed for batch review — the known limit of
   T-A5b, made visible).
6. Close report complete against its template.

**Matched observables.** Acceptance run record (per-scenario pass/fail,
suite hash); gate run record (exit code, log hash); commit list with
verified signatures and trailers; pre/post gated hashes; surface diff;
the ledger record.

**Enforcer.** *Mechanical:* phase-8 code refuses to write `closed` without
green acceptance **and** gate records; branch protection on the rolling
branch — only bot identities push, only via the executor; the vendored
`cards check` runs in the factory checkout too (symmetric with humans).
*Narrative:* the close-report template.

**Intensity.** Hard (conditions 1–4, 6); advisory (5).

**Species.** **Adapter** — a within-register verification that the run's
outputs match the card's stated acceptance and the project's gate; fidelity
by re-running (acceptance and gate are re-runnable at any later point).

**Model calls.** None.

**Failure protocol.** Acceptance or gate red ⇒ `failed:{acceptance|gate}`
with evidence; drift ⇒ `failed:card-drift` (work preserved, owner decides
at batch review); trailer/signature/identity mismatch ⇒ `failed:identity`
(a bug in the executor, not the story). Failure classes are typed:
`scope` / `ambiguity` → design queue via T-A4 rule 5; `infra` (runner,
network, quota) → one retry. **Where the failed commits live** is Open (1).

**Emits.** Per story: acceptance pass count, gate duration, cost, model +
effort per phase (4.7), declared-vs-actual surface delta, drift flag,
close latency, failure class.

**Writes / authority.** Rolling branch (factory-owned during a batch; bot
identity); ledger (authority for outcome). No card writes.

**Extensibility.** Mechanism **fixed-core**; the gate command, acceptance
runner, and **close criteria for non-code tenants** (what "green" is when
done ≠ merged PR — e.g. a checklist artifact with evidence)
**tenant-specializable**.

**Change governance.** Factory version; consumers: land (T-A10), batch
drain, dashboard, the close-report template.

**Brownfield note.** Sartor: the C-11 falsifiable-closure bar and gate-green
before merge; spolia: autonomous merge iff the closeout cites a real open
item — the `Factory-Run` trailer + ledger record is that contract, made
mechanical and signed.

**Open.** (1) **Per-story branch off the rolling branch, merged only at
green close** — **[owner-ratified 2026-08-16]**. A failed or parked story then never
touches the rolling branch, "a parked story never blocks the line" becomes
true by construction, and the skip design simplifies to *intent* overlap
(A5b) because a later story cannot build on unclosed work at all. Cost:
merge at close can conflict — conflict ⇒ `failed:merge`, deterministic.
(2) Drift-during-run = **fail** (`failed:card-drift`, work preserved, owner
decides at batch review) — **[owner-ratified 2026-08-16]**. (3) The typed failure
classes and their routing (with T-A4). (4) Whether close writes a per-story
closure-evidence artifact into the project or only into the ledger (lean:
ledger + factory artifact store; the project gets it at land).

### 2.4 T-A10 Land: ledger outcomes → card execution state in the project [proposed 2026-08-16]

**[owner-ratified 2026-08-21 — X2, sync 7ba.4; owner: *"A with the three
pins."*]** Land = the store's post-merge write on `main` (03 §1.4, §6;
03b §2). The sentences below are corrected in place under that ruling;
reconciling mechanics [proposed].

**Family / kind.** A · **written** — the **store's commit on `main` after
the batch PR merges** (X2 — sync 7ba.4; 03 §1.4): `state.json`,
`state/history.jsonl`, the inbox intake and `BOARD.md` in **one
transaction**, under the **`lander` grant only** (03 §1.3). The factory
never writes a card; its only card-adjacent write is the suggestion
intake.

**Endpoints.** system `ledger` → register `card execution state`
(project), forward. Trigger: ingest observes the batch PR's merge commit
in its `cursor..HEAD` walk (03 §9.5) — no human step between merge and
land; actor: the store, called by the factory's **`lander` client**.

**Above.** Ledger records for the batch: per card, outcome (closed /
failed / parked-with-question), run refs, evidence refs, telemetry
summary; human closures ratified with evidence (7d.2).

**Below.** `state.json` — the current state per card (fingerprint,
history head, runs' latest, closures' verification) — plus one
`state/history.jsonl` line per event, the **event-file union** (`e<n>`,
03 §6); the inbox intake records (03a); `BOARD.md` re-rendered in the
same transaction (03 §1.16); **`history_head` and `journal_head` land
with them** (03 §1.4; 03b §2). One store commit on `main` (author =
caller, committer = store), with the merge commit as `ledger_cursor`.

**Matching conditions.**
1. Every card touched has a ledger record justifying its new state — no
   state without a ledger record (7d.1).
2. **No card file in the diff:** the land touches only the sidecar, the
   inbox and the board — governed paths whose manifest rows carry the
   `lander` grant (03 §1.3). "The factory never edits a card" is
   structural: the store refuses the grant, not a hasher after the fact.
3. Board regenerated; its ready set equals the queue's (T-A4 fidelity).
4. Snapshot == the ledger's projection at the merge-commit cursor (X2).
5. The batch PR is merged (code only — X2) and the land is pending:
   until it commits, the batch is `closed (pending-land)`, the cursor
   holds, and the next batch on the tenant does not dispatch
   (fail-closed — sync 7ba.4).
6. Idempotent and replayable: landing the same cursor twice is an empty
   diff (`landed_at` = the cursor commit's time — G11); a half-land
   replays from the journal (03b §2).

**Matched observables.** The land diff confined to sidecar/inbox/board
paths; the journal row preceding the commit (03b §2); the merge-commit
cursor (`ledger_cursor`); `history_head` + `journal_head` as landed
(03 §1.4); board-fidelity result.

**Enforcer.** *Mechanical:* the store — it authenticates the caller,
checks the `lander` grant against the manifest rows for the sidecar,
inbox and board, journals write-ahead, and commits (03 §1.3; 03b §2);
batch-PR CI refuses any governed-path diff (X2 — 03 §1.14); ingest
reconciles every commit against the journal (03 §9.6). *Narrative:* none
needed — the grant table is the rule.

**Intensity.** Hard.

**Species.** **Adapter** — ledger → card fields; fidelity by round-trip:
re-derive execution state from the ledger and compare with the card.

**Model calls.** None.

**Failure protocol.** The land is one store transaction, journaled
before the commit; a half-land (row written, commit never followed)
replays from the journal on the next `land` call (03b §2); ledger
unreadable ⇒ no land; while a land is pending the cursor does not advance
and dispatch on the tenant is closed (fail-closed — X2 pin 2). Recovery:
replay — idempotent.

**Emits.** Batch size; closed/failed/parked counts; land duration;
fidelity outcomes; drift-detected count; snapshot age at land.

**Writes / authority.** `state.json` + `state/history.jsonl`, the inbox
intake, `BOARD.md` — on `main`, by the store under the `lander` grant
(03 §1.3); the ledger remains authority. The owner's gate is the batch
PR's merge (code only), which *precedes* the land (X2 — sync 7ba.4).

**Extensibility.** **Fixed-core.** Change governance: execution-block
schema versioned with the card schema (C-10-style consumer enumeration:
validator, hasher, board renderer, dashboard, snapshot format).

**Brownfield note.** Both projects' close-outs regenerate BOARD/ledger by
hand in the closing session; the header population-mix bug lived exactly
in that regeneration — condition 3 is its guard.

**Open.** (1) **Execution state as a sidecar, not in the card file** —
`cards/<id>.state.yaml` (or one generated `execution.jsonl`) rather than
frontmatter fields — **[owner-ratified 2026-08-16]**; the file layout is
settled in 03 §1.4 (W8): `state.json` (current per card) +
`state/history.jsonl` (events). Reasons as argued then: owner tending edits
on `main` and factory landing on the rolling branch can never merge-
conflict; "the factory writes only here" becomes a **path rule** —
branch protection / CODEOWNERS grants the lander identity write on that
path only, which is identity-as-enforcer again (since 03 §1.3 this is the
store's grant table — `lander` is a grant, and two versions of a governed
file can never meet in a merge); the card file stays
wholly owner-authored, so gated-hash-unchanged is trivially true. Cost:
two files per card for humans reading raw; the board renderer joins them.
(2) Land on demand mid-batch (owner asks) — lean: allowed, same contract.
(3) Parked questions reach the owner via the notifier immediately (T-C4);
the *card note* lands at batch — confirm that split is acceptable.

### 2.5 T-C5 / T-A8 The interrupt: executor → owner (held) and answer → re-dispatch [proposed 2026-08-16]

**Family / kind.** C (question) + A (answer). The question is **held**;
the answer is **written**.

**Endpoints.** T-C5: system `executor` → system `owner` — **held**: the
executor never resolves the ambiguity; the raised question *is* the
signal. T-A8: state `parked` → state `answered` → (T-A4) `ready` — adapter,
hard.

**Above (executor).** Mid-run (phases 2–7) the executor emits a typed
`ambiguity_question` through its template: `{run_id, card_id, phase,
question, options?, tried, why_blocked, source_tag, artifacts_so_far}`;
`source_tag` from a closed vocabulary — `card-ambiguity` ·
`missing-context` · `conflicting-instruction` · `environment` · `policy`
· `plan-failed` (the judge's park after the second `revise` — 2.19
since-note; 7bd.10/7bd.14).
Then the run **ends** (headless cannot wait — 7.2): artifacts persisted,
story branch pushed, ledger `parked`, notifier pushed (T-C4), inbox entry.
The line continues (skip, T-A5).

**Below (owner).** The question in push + inbox; the owner answers in an
interactive session (VS Code + CLI; Remote Control reaches it on the phone).

**Answer channels — by source tag [owner-ratified 2026-08-16].**
- `card-ambiguity` / `missing-context` / `conflicting-instruction`: the
  answer is **a card revision on the ratification path** (T-A2). An answer
  that changes what gets built belongs in the gated set (7d.1); the
  fingerprint changes; re-dispatch carries the answer in the payload. **No
  second channel is invented** — the held seam resolves through the same
  gate everything else does, and "the factory never edits a card" holds
  (the executor's question is ledger data landed as a note at T-A10; the
  owner's answer is a card change).
- `environment`: an operator action + an operational ack via the factory
  CLI (`answer <run-id>`), written to the ledger — not a card change.
- `policy`: a threshold-config change on the ratification path, or an
  owner ack.

**Matching conditions.** *T-C5:* question complete against its template;
source tag from the vocabulary; run ended cleanly (no partial card writes,
branch pushed, ledger `parked`); notifier delivered or inbox holds it.
*T-A8:* the answer references the question id and arrived through the
channel its source tag allows; if a card revision, it re-ratified (new
fingerprint) — the factory recognizes the answer by the ratifying commit
referencing the question id (trailer `Answers: <question-id>` or a card
field — Open 2); ledger `parked` → `answered`; readiness re-evaluated by
T-A4.

**Matched observables.** The question artifact; the ledger `parked` record
with `question_id`; notifier ack; the answering commit/ack with the
question id; ledger `answered`; the re-dispatch payload containing the
answer.

**Enforcer.** *Mechanical:* the question template validator (an
incomplete question is not "parked", it is `failed:malformed-question` —
an executor defect); the ledger refuses `answered` without a channel-valid
answer; the picker never dispatches `parked`. *Narrative:* the executor's
skill text — "ask rather than spin." Verification of the *held* property
is by conformance scenario and by measure: an executor that guesses through
an ambiguity is a defect that only post-hoc review can tag ("should have
asked") — declared gap; the measure is the interrupt rate + that tag rate.

**Intensity.** T-C5 held · T-A8 hard.

**Species.** T-C5 **held** (a conversion here — the executor deciding —
is premature closure). T-A8 **adapter** (answer → payload; fidelity: the
payload carries the answer verbatim).

**Model calls.** None at the crossing (the *decision* to raise is made by
the phase agent — that is inside its phase, not this seam).

**Failure protocol.** Notifier fails ⇒ inbox still holds; run malformed
⇒ `failed:malformed-question`; unanswered at batch drain ⇒ surfaced in the
batch review with the question (5.5); wrong channel for the tag ⇒ refused,
typed; answer arrives but re-ratification fails validation ⇒ card stays
draft-with-question.

**Emits.** Interrupt rate per tenant / phase / source tag (5.1: data to
reduce over time); time-to-answer; re-dispatch success after answer;
questions per card; "should have asked" tags from review.

**Writes / authority.** Ledger (question, parked, answered); notifier;
card — only by the owner's revision; the executor writes nothing to the
card.

**Extensibility.** T-C5 **fixed-core**; the notifier channel and the
answer-channel policy **tenant-specializable**.

**Change governance.** Question template and source-tag vocabulary
versioned; consumers: executor, notifier, dashboard inbox, T-A10 note
rendering, T-A4 rule 5.

**Brownfield note.** Sartor's N=1 runs died at invocation boundaries and
"spun" on ambiguity; the owner's rule became "the agent asks rather than
spins"; the interrogative-witness hook is the existing mechanism that
*forces the pause* — this row is its factory-scale counterpart.

**Since 03 draft-6 + the gajae adoption (2026-08-21).** **Parked means
until the owner responds — by whatever channel exists [owner-ratified
2026-08-20 (03 §1.12, round 43)].** Owner, verbatim: *"they are parked
UNTIL i respond. if i respond, it can pick up and move on."* — no
timeout; today the channel is the sitting, and the future Slack-like tool
that sources questions through the day stays a **named seam on this row**
(the "answer channels by source tag" model), on which an answer and its
signature unpark the card immediately; `answers[]`, the `answered` act
and the signer seam are channel-agnostic. Adopted [proposed] (gajae
follow-up 3 — `../research/gajae-code-2026-08-21.md` §3): **blocker
classification gates the right to park** — `resolvable` does not park
(the builder resolves or fails); only `human_blocked` parks, with a
critic verdict — **the judge's** (05 §1; Z2 owner-ratified 2026-08-26
(7bd.14, "a"); the deterministic wrapper assembles this row's typed
question from that verdict) — bound to that event; a **restart remints stale questions**
rather than resuming an ambiguous parked state, with **content-addressed
question ids**. And an executor need **outside the repo** is an
owner-approved request through this channel, approved with the same
un-cacheable act [owner-ratified 2026-08-20 (03 §1.17, round 34)].

**Open.** ~~(1) Answer channels by source tag~~ — ratified. ~~(2) Where a
card answer lives~~ — ratified: `answers[]` is a gated head field (03
§1.7); an answer on a ratified card derives `ratified` with `fields ⊇
["answers", "questions"]`, and the ledger's unpark event references
whichever entry carried the answer (C2 — 03 §11). (3) Plan-artifact reuse on re-dispatch: fresh
process, but prior artifacts offered as context — a dial, default reuse
plan-as-context. (4) Whether `environment` acks should ever be automatic
(a retry policy) rather than owner acks.

### 2.6 T-C3 The rolling branch: open → integrate → sync → drain → batch PR → main → land → reset [proposed 2026-08-16; land-on-`main` owner-ratified 2026-08-21 (X2 — sync 7ba.4)]

**Family / kind.** C · **written**. Not one crossing but the lifecycle of
one system, so this row is a *bundle* of written edges with distinct
triggers (all identity-distinct under 0.0):

| Sub-edge | From → To | Trigger / actor | Species · intensity |
|---|---|---|---|
| open | `main` → `rolling/<batch-id>` (branch from `main` HEAD) | batch open; factory (lander identity) | adapter · hard |
| integrate | `story/<run-id>` → rolling (merge at green close, T-A9) | close; run's bot identity | adapter · hard |
| sync | `main` → rolling (merge `main` in before every dispatch) | pick; factory | adapter · hard |
| drain-and-freeze | rolling: dispatch closed; in-flight runs finish; parked/skip reconciled | batch boundary (epic/milestone, 5.4); factory | adapter · hard |
| batch PR | rolling → PR against `main`, **code only** (X2 — no governed path in the diff; CI refuses one), body generated from the ledger | after drain; lander identity opens | adapter · hard |
| merge | PR → `main` | **owner** (the last human gate on the batch; the merge stays the forge's button — round 14) | held-then-adapter (owner judgment, then a mechanical merge) |
| land | ledger → sidecar + inbox intake + `BOARD.md`, the store's commit **on `main` after the merge** (T-A10; 03 §1.4, X2 — sync 7ba.4) | ingest observes the merge commit (03 §9.5); the store, `lander` | adapter · hard |
| reset | new `rolling/<batch-id+1>` from the merged `main` | after merge and land; factory | adapter · hard |
| hotfix lane | `hotfix/<id>` off `main` → immediate small PR → `main` | owner (or a card flagged `lane: hotfix`, tenant dial) | adapter · hard |

**Assumes** the per-story-branch lean from T-A9 (stories build on
`story/<run-id>` off rolling, merged into rolling only at green close). If
the owner rejects that lean, "integrate" collapses into "build commits
directly on rolling" and the drain must also handle failed commits.

**Above.** `main`: the project's truth — cards (substrate), threshold
config, vendored toolkit, code; changed by owner commits, hotfix merges,
and batch merges. `story/*`: one run's work. **Below.** The rolling
branch: `main` ⊕ closed stories ⊕ landed state — always a superset of
`main` (by *sync*), never containing failed or parked work (by
*integrate*).

**The ratification path — deferred here from T-A2; [owner-ratified 2026-08-16].**
**Ratification path = `main`.** Reasons: (i) `main` is the only ref whose
history is owner-authored and stable — rolling is reset per batch and
written by bots; (ii) the factory reads the *substrate* from `main` at
every pick (cards, config, ratification ingest cursor) and works *code* on
rolling — a card ratified mid-batch is ready at the next pick with no
branch gymnastics, because *sync* has already merged `main` into rolling
before dispatch; (iii) card commits to `main` are low-risk and can be
allowed outside sartor's per-item-branch discipline by a path rule
(`cards/**` + config paths, owner identity, validator hook green) — or go
through the owner's normal branch+merge if the tenant prefers; the policy
schema carries `ratification_path: main` + `ratifiers` + `paths`. Cards
committed on rolling by anyone are **not** ratifications (bots can't; the
owner shouldn't be committing to a bot-owned branch). *Consequence for the
"commit = ratify" collapse:* WIP on a ratified card is done off `main`
(any branch) — it stays ratified and dispatchable — or by demoting to
draft on `main`; both are legitimate and mean different things (chat,
2026-08-16).

**Matching conditions.**
- *open:* rolling created from `main` HEAD; ledger records batch id +
  base SHA; no other open batch for the tenant.
- *integrate:* the story branch merges cleanly (conflict ⇒ `failed:merge`,
  deterministic); merge commit by the run's bot identity, signed, trailer;
  gate re-run on the merge result if the merge was not fast-forward.
- *sync:* `main` merges cleanly into rolling before each dispatch
  (conflict ⇒ owner interrupt, `environment`); rolling ⊇ `main` afterwards.
- *drain:* no new dispatch after drain start; in-flight runs complete or
  park; parked/skip-list reconciled — still-parked stories listed with
  their questions; anything built on a flagged overlap listed (9.3).
- *batch PR:* opened by the lander identity; body = generated batch report
  (closed / failed / parked with evidence links, cost, models per phase,
  surfaces delta, drift flags); CI = `cards check` + full gate; the PR
  touches **code only — never a governed path** (X2; 03 §1.14: batch-PR
  CI fails on any tracking-root change); the sidecar, inbox intake and
  `BOARD.md` land on `main` after the merge.
- *land:* after the merge, on `main` — T-A10's contract (X2).
- *merge:* owner identity; PR CI green; each story is one merge commit so
  the owner can **revert a story on rolling before merging** (batch-review
  granularity without per-story approval).
- *reset:* new rolling from merged `main`; previous rolling archived
  (tag), not deleted; ledger batch closed.
- *hotfix:* branch off `main`, one small PR, merged by owner; the next
  *sync* carries it into rolling.

**Matched observables.** Batch record in ledger (id, base SHA, open/drain/
land/PR/merge SHAs and times); per-story merge commit SHA + signature;
sync merge SHAs; PR number + CI verdicts; archived tag; hotfix PR numbers.

**Enforcer.** *Mechanical:* branch protection — `main`: owner merges only,
PR required, CI (validator + gate), the `cards/**` path rule for direct
card commits if the tenant enables it; rolling: bot identities + lander
only, no owner pushes; story branches: the run's bot only. Factory code
refuses dispatch when sync fails and refuses land when the branch is not
frozen. *Narrative:* the batch-report template; the tenant onboarding doc.

**Species / intensity.** All adapters (git operations; fidelity by SHA
lineage), hard — except *merge*, which is the owner's judgment (held) then
mechanical.

**Model calls.** None (the batch report is a template over the ledger).

**Failure protocol.** Merge conflicts are typed and deterministic (story:
`failed:merge`; sync: owner interrupt); PR CI red ⇒ typed failure with
the offending story identified by bisecting the merge commits (each is a
unit); owner rejects the batch ⇒ revert stories on rolling, re-run land, PR
updates; a batch left open past a tenant-configured age ⇒ notify.

**Emits.** Batch cycle time; stories per batch; owner review time (the
2026 evidence: agent PRs wait 5.3× longer — batching is the answer);
rejection/revert rate (10P-8's healthy 5–20% band); sync conflicts; hotfix
count.

**Writes / authority.** rolling and story branches (factory); PR (lander
identity); `main` (owner only). Ledger holds the batch record.

**Extensibility.** Mechanism **fixed-core**; batch boundary rule, hotfix
policy, `cards/**` path rule, story-branch naming **tenant-specializable**.

**Change governance.** Branch-protection templates vendored with the
toolkit (T-C2) and versioned; consumers: T-A9, T-A10, T-A2 policy schema,
dashboard.

**Brownfield note.** Sartor: one branch per item, ask before merge to
`main`; spolia: conditional auto-merge iff closeout cites an open item —
the trust-ladder rung above this row's owner-merge (5.3).

**Since 03 draft-6 / 03b (2026-08-21) [owner-ratified; reconciling
mechanics proposed].** X2 — sync 7ba.4, owner: *"A with the three
pins."* — the land left this branch: after the owner's merge the
**store** (its own service, **one container per tenant** — 03 §1.3, 03b
§2; sync 7ba.6, owner: *"b, one store per tenant. next"*) writes the
sidecar, the inbox intake and `BOARD.md` as its ordinary commit on
**`main`**, with the **merge commit as the ledger cursor**; ingest's
`cursor..HEAD` walk observes the merge — no human step between merge and
land (03 §9.5). The pins: `closed (pending-land)` and the queue's
"merged, not landed: N" name the interval; **fail-closed** — the cursor
does not advance and the next batch on the tenant does not dispatch while
a land is pending; land is idempotent and replayable from the journal
(03b §2). The tenant repo holds **data and policy only**; governed-path
commits on `main` are the store's, fast-forward/merge-only — a story
revert stays this row's revert-on-rolling, but a governed-file revert is
a new `write` of the prior document through the store, never a git revert
(03 §9.6). Batch-PR CI follows the untrusted-PR recipe [proposed]:
validator from the trusted base ref, PR head read as bytes only,
read-only permissions, no secrets (gajae follow-up 1 —
`../research/gajae-code-2026-08-21.md` §3).

**Open.** ~~(1) Ratification path = `main` with the `cards/**` path rule as
a tenant option~~ — ratified. ~~(2) *Sync* merges `main` before every
dispatch~~ — ratified. ~~(3) Hotfix: owner lane by default, card
`lane: hotfix` as a tenant dial~~ — ratified. (4) Archive
old rolling branches as tags (lean yes) — retention a tenant dial.

### 2.7 T-B8 / T-B9 Cards → board · cards + ledger → queue [proposed 2026-08-16]

**Family / kind.** B · **derived** — two adapters from one source,
deliberately not composed (3.3).

**Endpoints.** register `cards` (+ sidecar execution state + ledger) →
register `board` (T-B8, rendered in-project **and** in the dashboard);
register `cards` + `ledger` + config → register `queue / ready-view`
(T-B9, factory only). Forward; guard edges of T-A4 feed both.

**Above.** Card records; sidecar execution state (T-A10); ledger (run
states, fingerprints); tenant threshold config; the tenant's board **style
spec** (grouping — epic / milestone / status; columns; ordering; what the
header summarizes); ARC-level narrative the cards point at.

**Below — board.** A composite human-readable map at owner-triage scale:
every card exactly once, grouped per the style spec, each with status,
priority, effort, deps, ready verdict as a label (from T-A4), execution
state, a pointer back to the card. In-project as a rendered file
(BOARD.md-class, regenerated) and in the dashboard as a read of the same
substrate — **never a second store**. **Below — queue.** The ordered
ready-view (T-A4's verdicts + ordering key) with dispatch payload
readiness (T-B3 inputs present), typed JSON, consumed by the picker and
shown by the dashboard; per tenant, never merged across tenants (T-C8
held).

**Where "write-through, interactive" lives — reconciliation needed.**
Decision 3.2 says the board is write-through and interactive (gestures
transcribe to card edits); 4.6 says the dashboard is read-only. Both are
owner-ratified. Reading: the **planning surface** (VS Code + CLI, 5.9) is
where write-through gestures live — a board command/view whose gestures
become card edits committed by the owner's identity (tending edits →
T-A11; gated edits → T-A2); the **in-project file** and the **dashboard**
are read-only projections. **[owner-ratified 2026-08-16]**

**Matching conditions.**
- *Board:* (1) population fidelity — every card appears exactly once and
  header counts equal body counts (the mirrored brownfield defect, made a
  gate); (2) currency — committed board == regenerated board; (3) verdict
  fidelity — the board's ready set == the queue's; (4) **no board-only
  state** — every fact on the board is derivable from cards + sidecar +
  ledger; a fact that isn't is a defect; (5) style spec valid.
- *Queue:* (1) computed from cards + ledger + config only — the renderer
  has no import path from the board (a structural guard, not a rule);
  (2) T-A4's verdicts verbatim; (3) ordering deterministic; (4) each entry
  has a buildable payload (T-B3 preconditions) or is marked
  `payload_incomplete` with the missing ref.

**Matched observables.** Regenerate-and-diff result; population counts;
ready-set equality; the style-spec version and renderer version stamped
in the board header (provenance line); the queue artifact + its input
hashes (cards tree hash, ledger cursor, config hash).

**Enforcer.** *Mechanical:* both renderers are pure functions; the store
is the board's only writer — it renders at land (same transaction as
`state.json`) and on demand, and the tenant hook refuses any local
governed-path change (03 §9.6, superseding the regenerate-on-commit
hook); the land asserts fidelity before its commit; the picker consumes
only the queue artifact. *Narrative:* the style-spec docs.

**Intensity.** Hard (all fidelity checks).

**Species.** Both **adapter** — projections of the substrate; fidelity by
regenerate-and-compare, plus the population and ready-set checks that
regenerate-and-compare alone is blind to (6, sync record).

**Model calls.** None.

**Failure protocol.** Board fidelity fails ⇒ commit refused (project) or
land aborted (factory), typed with the failing check; queue inputs
unreadable ⇒ empty queue (fail-closed, T-A4); style spec invalid ⇒
renderer refuses; recovery: regenerate — idempotent.

**Emits.** Fidelity failures by check; board age vs substrate; queue
length over time; renderer duration.

**Writes / authority.** Board file (project, generated, provenance-
stamped); queue artifact (factory, ephemeral); authority = substrate +
renderer version.

**Extensibility.** Renderers **fixed-core**; style spec and threshold
labels **tenant-specializable**; extra projections (Gherkin, T-B11)
**tenant-defined**.

**Change governance.** Renderer + style-spec schema versioned with the
toolkit; consumers: hook, land, dashboard, planning-surface board.

**Brownfield note.** Schema-1 BOARD.md in both projects with the
population-mix header bug; regenerate-and-compare exists as a gate in
both; neither has a queue.

**Since 03 draft-6 (03 §1.16, §1.5; rounds 47, 52; sync 7bb.1)
[owner-ratified; reconciling mechanics proposed].** `BOARD.md` is
**rendered by the store** — at land, in the same transaction as
`state.json`, and on demand (`show Board`) — committed when
`board.commit = true` (default; the one board key — 04 §2.2); owner,
round 52: *"yes and keep the board per your caveats"*. **The queue
section opens the board** and the morning review: what the next sitting's
one signature clears — open questions, holds awaiting release, closures
pending review, withdrawals pending, cards blocked by those, the
planner's dispositions since the last batch signature, inbox counts by
source, and **"merged, not landed: N"** (X2); the **inbox section
follows** (`SUGGESTIONS.md` is gone — W4). **Nothing reads `BOARD.md`**:
every computation reads cards and the sidecar. Currency is structural —
the store is the only writer, so the committed board is the regeneration.

**Open.** ~~(1) Write-through board in the planning surface; in-project
file and dashboard read-only~~ — ratified. ~~(2) In-project board
committed~~ — ratified. ~~(3) Board style spec: tenant config vs its own
file~~ — ruled for v1 (03 §1.16; 04 §2.2): `board.commit` is the one
config key; sections, caps and precedence are pinned in the schema.

### 2.8 T-C1 Factory ← project checkout [proposed 2026-08-16]

**Family / kind.** C · **derived** (reads and validates; writes only the
ingest cursor to the ledger). This is the crossing every run starts with;
everything downstream reads a typed `TenantContext` from it, never the
repo ad hoc.

**Endpoints.** system `project repo (forge)` → system `factory
(TenantContext)`, forward. Trigger: every pick, and every ingest signal
(push webhook / Actions trigger / poll). Actor: the factory, with **read**
credentials (deploy key / App installation, read scope) — write
credentials are the bot identities' and are not used here.

**Above.** The tenant's forge repo: `main` (substrate: `cards/**`,
threshold config, tenant extension schema, vendored toolkit with its
provenance/version pin, ratification history), rolling branch (work),
sidecar state. **Below.** `TenantContext` (pydantic, strict): tenant id;
checkout SHAs; toolkit version; validated config; validated extension
schema; the card set with per-card gated hashes; ratification events since
cursor (T-A2 (b)); human closures since cursor (T-A12); ledger snapshot
handle; egress allowlist for the run.

**Matching conditions.**
1. Tenant registered in this factory instance's tenant list (7d.3).
2. Repo reachable; refs present (`main`, ratification path, rolling if a
   batch is open).
3. **Toolkit version supported** by this factory release (compat range);
   else refuse and say so, naming the upgrade (T-C2).
4. Threshold config valid against the config schema; ratification policy
   present (factory mode: non-empty `ratifiers`, `ratification_path`).
5. Tenant extension schema valid; every card's extension fields valid.
6. `cards check` **green over the whole checkout** — a project failing its
   own vendored validation is not dispatched.
7. Ratification ingest: cursor ≤ HEAD; qualifying commits parsed; gated
   hashes computed under the pinned canonicalization; fingerprints written
   to the ledger as *derived* records.
8. Ledger readable (fail-closed everywhere downstream).
9. Egress: only allowlisted hosts for this tenant (I-33).

**Matched observables.** Checkout SHAs; toolkit version string from the
provenance header; config hash; validator verdict; number of ingest events;
new fingerprints; cursor advance; TenantContext hash (re-read and compare
= round-trip).

**Enforcer.** *Mechanical:* the checkout step is the only code path that
touches the repo for reading; it refuses to emit a `TenantContext` on any
failed condition; downstream phases type-check against it. *Narrative:*
tenant onboarding doc.

**Intensity.** Hard.

**Species.** **Adapter** — a faithful typed projection of the checkout;
fidelity by re-read-and-compare.

**Model calls.** None.

**Failure protocol.** Unreachable ⇒ no dispatch, retry with backoff, then
`environment` notification; unsupported version ⇒ typed refusal +
notification with the upgrade path; validator red ⇒ refusal naming the
cards **and** flagging that the vendored hook should have caught it (a
hook-bypass signal worth surfacing); config/extension invalid ⇒ refusal;
ingest parse error on a card ⇒ that card `unratified` with reason, others
proceed.

**Emits.** Checkout duration; repo/cards size; ingest events; validator
time; **version skew** (tenant toolkit vs factory) — the trend that tells
you when to push a vendoring update.

**Writes / authority.** Ledger: cursor + derived fingerprints. Nothing in
the project.

**Efficiency (design-time, per house rule).** One **bare mirror per
tenant** in the container, fetched by delta on each trigger, with a
**worktree per run** — never a fresh clone per pick; ingest walks only
commits since the cursor; validator runs incrementally on changed cards
with a full pass at batch open. Cost is O(delta) per pick, O(cards) per
batch.

**Extensibility.** **Fixed-core** mechanism; refs, cards path, extension
schema location, egress allowlist **tenant-specializable**.

**Change governance.** Toolkit compat matrix per factory release;
consumers: T-A2 ingest, T-A4, T-B3, T-C2.

**Brownfield note.** Both projects run their vendored `work_items.py`
check in CI — the same vendored-check-run-by-both-sides symmetry this row
relies on.

**Since 03 draft-6 / 03b / 04 (2026-08-21/26) [owner-ratified; reconciling
mechanics proposed].** The tracking root is a set of **governed paths**
written only through the **store — its own service, one container per
tenant** (03 §1.3, 03b §2; round 52; sync 7ba.6, owner: *"b, one store
per tenant. next"*); the factory holds one client channel per tenant from
the registration, and its write credential at this seam is the **`lander`
grant only** (03 §1.12). **The tenant repo holds data and policy only**
(`cards/`, `state.json`, `state/history.jsonl`, `suggestions.jsonl`,
`config.toml`, optionally `BOARD.md`); the tenant container holds a thin
client and one hook. Conditions 4–7 therefore resolve against the store
and the schema docs: config validity = `config@<adopted>` resolution with
defaults from the adopted schema version (04 §4.1, Y1 — sync 7bc.7);
ingest classification = 03 §9.5; and every commit on the ratification
path is reconciled against the journal (03 §9.6) — **governed-path
commits are fast-forward/merge-only on `main`, and a revert is a new
`write` of the prior document through the store**, never a git revert.

**Open.** (1) Read credentials: deploy key per tenant vs App installation —
lean: whatever the forge driver (T-C7) offers read-scoped; per-tenant
either way. (2) Whether ingest of ratification events also runs on a
webhook independent of picks (lean yes — push-triggered, T-A2). (3) Full
validator pass cadence.

### 2.9 T-A1 Capture: observation → draft card [proposed 2026-08-16]

**Family / kind.** A · **written** (card file, `status: draft`).
**Endpoints.** register `observation` (a chat remark, a review finding, a
failed run's lesson, a digest item, a planner suggestion) → state `draft`.
Forward. **Trigger / actor.** The owner or the agent in an interactive
session (owner identity); bots — see Open (1).

**Above.** Loose language: "we should…", a finding, a stack trace, a
sourced issue. **Below.** A draft card: id, title, `source` (typed:
session / review / run / digest / planner), `captured_by`, `captured_at`,
free body, `status: draft` — and nothing else required. Non-dispatchable
by construction (T-A4 rule 2).

**Matching conditions.** (1) Produced through the template's *draft
profile* — the minimal rule set: id, title, source, status; (2) no
acceptance block required, no priority, no effort (draft-tier exemption,
3.6); (3) never in the ready-view.

**Matched observables.** Validator verdict under the draft profile; absence
from the queue; time-in-draft.

**Enforcer.** *Mechanical:* validator draft profile on save/commit; the
ready-view excludes `draft`. *Narrative:* the template's "capture cheap"
guidance (I-28) — capture is meant to cost seconds.

**Intensity.** Hard, but minimal — the point of the draft tier is that the
bar is low. **Species.** **Transducer** (observation → record; discards
context, adds id/source). **Model calls.** None at the crossing.

**Failure protocol.** Invalid draft ⇒ refused with the (short) typed error
list; recovery: fix, save. **Emits.** Drafts per source; time-in-draft;
promotion rate (draft → ratified) and abandonment rate — the planner's
telemetry.

**Writes / authority.** Card file, project, owner-authored (or agent under
owner identity in session).

**Extensibility.** Draft profile **fixed-core**; source vocabulary
**tenant-specializable** (extension). **Brownfield note.** Sartor's
"source issues" during sessions and spolia's item filing — both already
capture cheaply; both lack the draft/ratified distinction.

**Open.** (1) **Bot-filed drafts.** The factory's reviewers and the
staged planner (7b.5, review-and-suggest) will *source* drafts. Card files
are owner-authored and the factory's write path is a path rule (T-A10) —
so bot-filed drafts need a designated path the bots may write:
`cards/drafts/` (or the planner's digest file), landed by the lander
identity, still non-dispatchable, promoted by the owner through T-A2.
**[owner-ratified 2026-08-16]:** yes, a drafts path within the factory's
path rule; (2) review findings out of a story's scope auto-file drafts,
tagged `source: review`, with the run id — **ratified**; and (3) owner
extension: sourced drafts are surfaced for owner review in the
**dashboard** (a sourced-drafts inbox, read-only; promotion happens in
the planning surface).

**Superseded 2026-08-20 (03 §1.18, round 28) [owner-ratified].** (1) and
(2) above are replaced: **bots do not write drafts** and no drafts path
exists — a bot's draft-worthy observation is a **suggestion** (`suggest`,
or the run report's `suggestions[]` landed as inbox intake), turned into
a draft card only by a disposition with the owner (`--as card`,
`source = "suggestion"`, `see = ["s<n>"]`); out-of-scope review findings
follow T-B6's rule. (3) survives as the board's inbox section
(03 §1.16) and the morning review's counts by source.

### 2.10 T-A3 Gated drift: ratified → unratified (and sidecar divergence) [proposed 2026-08-16]

**Family / kind.** A · **derived** (a projection flag), resolved by a
written T-A2 re-ratification.
**Endpoints.** state `ratified` → derived state `unratified`
(gated set changed without a qualifying commit) — and its sibling
`state-divergent` (sidecar execution state ≠ ledger projection, 7d.1).
**Trigger.** Any read: T-C1 ingest, T-A4 evaluation, the vendored hook at
edit/commit time.

**Where drift actually arises under (b) + `main`.** A gated edit by a
ratifier on the path is a *re-ratification*, not drift. Drift is: (i) a
gated change on `main` that does not qualify (unsigned when signatures are
required; wrong path; author not a ratifier — reachable only if the
`cards/**` path rule is misconfigured or a PR was merged without a
ratifier); (ii) hasher/canonicalization version change (T-A2 change
governance: re-hash at ingest, else `unratified` — the safe direction);
(iii) ledger loss (recoverable by re-ingest); (iv) **bootstrapping** — the
sartor migration: imported cards have no fingerprint until first ingest;
the owner's migration commit qualifies, so ingest ratifies them in one
pass. Sidecar divergence: a human hand-edits execution state.

**Matching conditions.** `unratified` ⇔ working-tree gated hash ≠ hash at
the last qualifying commit; `state-divergent` ⇔ sidecar ≠ ledger
projection at the current cursor. Both computed by the same hasher used at
ratification/land.

**Matched observables.** The two hashes; the reason code (`no-qualifying-
commit` / `hasher-version` / `no-fingerprint` / `sidecar-edited`); board
label; design-queue entry.

**Enforcer.** *Mechanical:* T-A4 excludes both from readiness; the board
shows both with reason; the vendored hook **warns** locally (it can compute
gated drift from `git log` + policy alone, and sidecar divergence from the
vendored snapshot); T-A10 **overwrites** a hand-edited sidecar from the
ledger at the next land (ledger authority) and reports it. *Narrative:*
none needed.

**Intensity.** Hard. **Species.** **Adapter** (hash round-trip). **Model
calls.** None.

**Failure protocol.** `unratified` ⇒ visible on board, absent from queue,
in the owner's design queue; recovery = a qualifying commit (T-A2) or a
revert. `state-divergent` ⇒ same visibility; recovery = next land (auto)
or on-demand land. Ledger unreadable ⇒ everything is unratified — which is
just fail-closed dispatch by another name.

**Emits.** Drift events by reason; time-to-re-ratify; sidecar edits (a
signal that humans want to write state — worth watching).

**Writes / authority.** Nothing; ledger authority.

**Extensibility.** **Fixed-core.** **Brownfield note.** Neither project can
detect this class today — the C-11 bar detects false *closure*, not
un-approved *change*.

**Open.** ~~(1) The design queue is a filtered board view (drafts +
unratified + parked + disputed), no new store~~ — **[owner-ratified
2026-08-16]**.

### 2.11 T-A6 Pick / dispatch: ready → dispatched [proposed 2026-08-16]

**Family / kind.** A · **written** (ledger record, story branch, run
start). **Endpoints.** derived state `ready` → state `dispatched`, forward.
**Trigger / actor.** The picker loop (schedule / webhook / poll) or the
owner's "run next" command; actor = the factory; the run itself acquires
the executor's **bot identity** for its phase agents.

**Above.** The ready-view (T-A4/B9) with ordering; the rolling branch
after *sync* (T-C3); tenant config: WIP cap, adapter choice (T-C6),
model/effort plan (single tier + telemetry, 7b.4), budgets. **Below.** A
ledger `dispatched` record `{run_id, card_id, gated_hash_at_dispatch,
base_sha, story_branch, adapter, models_plan, budgets}`; a `story/<run-id>`
branch from rolling HEAD; a validated run payload (T-B3); a running
executor with the record id.

**Matching conditions.** (1) Card is at the head of the ready-view under
the ordering key; (2) WIP cap not exceeded (concurrent runs per tenant);
(3) *sync* done — rolling ⊇ `main`; (4) story branch created from rolling
HEAD; (5) payload built and validated (T-B3), carrying the gated hash it
was built from; (6) bot identity + credentials for the run resolvable from
the secrets seam; (7) **ledger record written before the run starts** —
no record, no run.

**Matched observables.** The ledger record; branch exists at `base_sha`;
payload artifact hash; the adapter's run handle stored on the record.

**Enforcer.** *Mechanical:* picker code; the adapter refuses to start
without a ledger record id; branch protection (story branches: the run's
bot only). *Narrative:* none.

**Intensity.** Hard. **Species.** **Adapter** (payload ↔ card fidelity;
record ↔ actual run). **Model calls.** None.

**Failure protocol.** Ledger write fails ⇒ no dispatch (fail-closed);
branch creation fails ⇒ `environment` interrupt; adapter start fails ⇒
`failed:infra`, one retry; payload invalid ⇒ card `payload_incomplete`
(back to the design queue with the missing ref).

**Emits.** Dispatch latency (ready → dispatched); queue depth; WIP; picks
per hour; adapter used.

**Writes / authority.** Ledger (authority); story branch (factory).

**Extensibility.** Mechanism **fixed-core**; WIP cap, ordering key,
adapter, budgets **tenant-specializable**.

**Change governance.** Payload schema versioned (T-B3); consumers: adapters,
executor phases, dashboard.

**Brownfield note.** Sartor's N=1: one story at a time by hand; every death
at the invocation boundary — condition (7) and the adapter's refusal-
without-record are that boundary made mechanical.

**Open.** ~~(1) WIP cap default **1** while trust is low, dial up on
measured rejection rate~~ — **[owner-ratified 2026-08-16]**. (2) Ordering
key — owner directed a **multi-tier prioritization**; designed in
`02-prioritization.md` [proposed] (expedite lane → priority class →
composite → deterministic tie-breaks).

### 2.12 T-A7 Attempt outcome: dispatched → complete / failed / parked [proposed 2026-08-16]

**Family / kind.** A · **written** (ledger). **Endpoints.** state
`dispatched` → `complete` (all phases through reconcile done; T-A9 close
then runs) | `failed:<class>` | `parked` (a question raised, T-C5).
**Trigger / actor.** The executor's typed **close report** at run end —
any end — or the watchdog when there is no report.

**Above.** The run: per-phase artifacts (plan, refutation, verdict, diff,
findings, reconcile), telemetry per phase (model, effort, tokens, cost,
duration), the story branch head, and either a close report or a question
artifact. **Below.** The ledger outcome record; artifacts persisted with
hashes; branch pushed.

**Matching conditions.** (1) Report validates against its template;
(2) `run_id` matches the dispatched record; (3) outcome ∈ the closed
vocabulary — `complete` · `failed:{scope|ambiguity|infra|budget|timeout|
malformed-report|malformed-question}` · `parked` (question artifact
present, T-C5 contract); (4) all artifacts persisted and hashed;
(5) branch pushed at the reported head; (6) telemetry per phase present
(4.7 — required, not optional); (7) budgets respected (token/time caps
from tenant config) — the watchdog enforces.

**Matched observables.** Report hash; ledger record; branch head; artifact
hashes; per-phase telemetry rows.

**Enforcer.** *Mechanical:* the ledger writer validates the report and
refuses an outcome without it; the watchdog writes `failed:infra:no-report`
/ `failed:timeout` / `failed:budget` when the run ends without one or
exceeds caps (fail-closed: a silent run is a failed run). *Narrative:* the
close-report and question templates.

**Intensity.** Hard. **Species.** **Adapter** (the report is a typed
self-report; the ledger record is its fidelity target and the authority).
**Model calls.** None at the crossing.

**Failure protocol.** Malformed report ⇒ `failed:malformed-report` (an
executor defect, not the story's — routed to the factory's own issue
list, and the story retried once); `infra` ⇒ one retry; `scope`/`ambiguity`
⇒ design queue (T-A4 rule 5); `budget`/`timeout` ⇒ design queue with the
telemetry attached (the card was under-scoped or the tier under-set —
data for 7b.4).

**Emits.** Outcome distribution; per-phase telemetry (the tuning dataset);
budget utilization; retry counts.

**Writes / authority.** Ledger (authority); artifact store.

**Extensibility.** Vocabulary and mechanism **fixed-core**; budgets and
retry policy **tenant-specializable**.

**Change governance.** Report/question templates and outcome vocabulary
versioned; consumers: T-A9, T-A10, dashboard, T-A4 rule 5.

**Brownfield note.** Sartor's runs reported completion in prose ("scope
reconciliation clean") that was later found false — the typed report +
mechanical close (T-A9) is the countermeasure.

**Open.** ~~(1) Budgets live in tenant config, per tier~~ — **[owner-
ratified 2026-08-16]**. ~~(2) The factory's own defects (`malformed-*`)
auto-file drafts into the factory repo~~ — **superseded [owner-ratified
2026-08-26 (sync 7bd.5, "a")]**: tenant #0 follows the same rule as every
tenant — an instance-discovered factory-self defect arrives as **suggestion
intake** (`source` tags the instance); a draft exists only after a
disposition with the owner (03 §1.18, round 28); the 2026-08-16 auto-draft
reading is superseded. Tenant-#0 posture otherwise per sync record
section 11 (one home).

### 2.13 T-A11 Tending edit: priority, demotion [proposed 2026-08-16]

**Family / kind.** A · **written** (card file on `main`). **Endpoints.**
state `ratified` → `ratified` (priority changed) or → `draft` (demotion) —
forward. **Trigger / actor.** A ratifier (or a tenant-configured *tender*)
in session, owner identity; the planning surface's write-through board
gestures land here.

**Matching conditions.** (1) Only tending fields changed — **priority**,
and status moves toward less active (`ratified → draft`); (2) gated hash
unchanged; (3) validator green; (4) commit on the ratification path by an
allowed identity (the `cards/**` path rule); (5) ingest classifies the diff
as tending (hash equal) and records a tending event — no fingerprint
change, no ceremony (3.7).

**Matched observables.** Diff confined to tending fields; hash equality;
ledger tending event.

**Enforcer.** *Mechanical:* hook re-validates; ingest diff classifier;
path rule. *Narrative:* none.

**Intensity.** Hard (validate), no ceremony. **Species.** **Adapter.**
**Model calls.** None.

**Failure protocol.** A "tending" commit that also changes gated fields is
not a failure — by a ratifier it is a re-ratification (T-A2); by a
non-ratifier it is drift (T-A3). Demotion of a card **in flight**
(dispatched/parked) ⇒ the run finishes or parks; the outcome lands as
`complete-but-demoted` for the owner's review — lean; open.

**Emits.** Priority churn; demotions; who tends.

**Writes / authority.** Card file, project, owner (tender) identity.

**Extensibility.** Which fields are tending **fixed-core** (7d.1); the
tenders list **tenant-specializable** (default = ratifiers).

**Brownfield note.** Both boards allow free-hand priority/status edits with
no distinction between tending and scope change — the distinction is new.

**Since 03 draft-6 (03 §1.7, §1.8, §9.3; sync 7bb.1) [owner-ratified;
reconciling mechanics proposed].** Tending is a class of **flat top-level
head keys** (`priority`, `class_of_service`, `due`, `sprint`, `milestone`,
`starts`, `ends`, `lane`, `tags`, `hold`, `summary`, `withdrawn_reason`,
and status moves toward less active) — validated, un-hashed, never in the
payload (`tags` never an input to a readiness rule). A gesture is one
**`write --set`** through the store — the planning surface's board
gestures land as these — deriving one entry that **carries `build`
forward unchanged** (the diff touched no hashed key, no re-hash). Clears
follow the signature predicate (the Andon asymmetry): setting any hold is
tending; clearing `blocked`/`deferred` on a ratified card is the owner's
**signed `released`**; `watching` and draft holds clear unsigned;
re-kinding `blocked ↔ deferred` is `held`, unsigned. Condition (4)'s
"commit on the ratification path by an allowed identity" is now the
store's write under the caller's grant (03 §1.3).

**Open.** ~~(1) In-flight demotion → `complete-but-demoted`~~ —
**[owner-ratified 2026-08-16]**. ~~(2) A terminal `withdrawn`
status~~ — **[owner-ratified 2026-08-16]** (card schema).

### 2.14 T-A12 Human closure: card completed by a human alone → closed [proposed 2026-08-16]

**Family / kind.** A · **written** (card on `main` by a ratifier) then
**derived/verified** (ingest) then ledger. **Endpoints.** state `ratified`
(or `dispatched` if the human raced the line) → `closed:human` — forward.
**Trigger / actor.** A ratifier commits a **closure claim** on the path:
`status: closed` + a closure block (evidence refs: commit SHAs, PR, test
run, or for non-code tenants a checklist/artifact) — this is a gated edit,
so it qualifies as a ratifying commit; the factory ingests it as a
*closure event* (T-C1) and **verifies** it.

**Matching conditions.** (1) The claim's evidence refs resolve — SHAs
reachable on `main`, PR merged, artifacts present; (2) if the card's
acceptance suite is runnable, the factory **runs it** in its checkout at
ingest and it is green (the falsifiable-closure bar, sartor C-11, made
mechanical); if not runnable (non-code), evidence-only with the tenant's
close criteria (T-A9 specialization); (3) ledger records `closed:human`
with the verification result; (4) next land writes the sidecar `closed`
from the ledger — the human never writes the sidecar.

**Matched observables.** Closure block; evidence resolution result;
acceptance run record; ledger record; sidecar after land.

**Enforcer.** *Mechanical:* ingest refuses `closed:human` when evidence
does not resolve or acceptance is red — the card projects **`disputed`**
(visible, not dispatchable, in the design queue with the failing check).
*Narrative:* the closure-block template.

**Intensity.** Hard. **Species.** **Transducer** (a claim → a verified
closure; characteristic: preserves evidence refs, adds a verification
verdict, discards the human's process). **Model calls.** None.

**Failure protocol.** `disputed` as above; a closure claim with no ledger
entry (factory hasn't ingested yet) is simply pending — the local hook
shows "closure claimed, unverified"; a hand-written sidecar `closed` with
no claim is `state-divergent` (T-A3).

**Emits.** Human closures per tenant; disputed rate; time claim→verified.

**Writes / authority.** Card (owner); ledger (authority); sidecar (factory,
at land).

**Extensibility.** Mechanism **fixed-core**; close criteria for
non-runnable acceptance **tenant-specializable**.

**Brownfield note.** Sartor C-11: closure must be falsifiable — the ledger
verifies rather than trusts; spolia's items close by hand today.

**No silent closure [owner requirement 2026-08-16].** A closure record —
human or factory — always carries the **per-scenario acceptance verdicts**.
If any scenario is not green, or the acceptance block was altered after
the work was done, the closure must state `outcome: deviated` and
describe what was actually done; the record may never read "closed,
conditions met" when they are not. A claim of `met` that verification
contradicts projects `disputed`, never `closed`. Applies to T-A9's ledger
record as well (already per-scenario) and to demoted/altered cards.

**Since 03 draft-6 + the gajae adoption (2026-08-21) [owner-ratified;
reconciling mechanics proposed].** Closure claims are card-side
`closures[]` entries with ids **`c<n>`** — claims class, never in the
build hash (03 §1.7); a `deviated` closure is **`closed
(pending-review)`**, not terminal, in the queue, until the owner's signed
`accepted` whose **`ref` binds the closure-entry hash**
(`"c<n>:sha256:<hash>"` — W6, 03 §5.2); declining is a signed `reopened`
returning the card to `ratified` with the claim retained. **Record-only
closures on drafts**: only `deviated` with a `description`, pending
review (T2). **Retraction:** before any land a contributor's unsigned
`retracted` returns `closed → ratified` (`closures[-1].retracted = true`,
no `reopens[]` entry); the exemption from the more-active clause holds
**only when the diff carries no gated key** (C5 — 03 §11). Adopted
[proposed] (gajae follow-up 2): the ledger **recomputes the change set
from git and refuses a report whose claimed set differs** — before
judging `surfaces` or any closure
(`../research/gajae-code-2026-08-21.md` §3).

**Open.** ~~(1) Acceptance run at ingest mandatory when runnable~~ —
**[owner-ratified 2026-08-16]**.
(2) Partial human work on a card that then goes to the line: the human's
commits on `main` are picked up by *sync*; the run builds on them — no
special handling needed beyond the interrupt note (7d.2) — confirm.

### 2.15 T-A13 Reopen: closed → reopened [proposed 2026-08-16]

**Family / kind.** A · **written** (card on `main` by a ratifier; ledger).
**Endpoints.** state `closed` → state `ratified` (or `draft`) with a
`reopen_reason` — forward. **Trigger / actor.** A ratifier commit on the
path changing status from `closed` and (usually) the acceptance block or
body: **a reopen is a re-ratification** — a new fingerprint; the ledger
records `reopened` linked to the prior runs and closure evidence
(append-only history retained).

**Matching conditions.** (1) The commit qualifies as a ratifying commit
(T-A2); (2) `reopen_reason` present (template); (3) the prior closure is
**landed in `main`** — if the closed work is still on an unmerged rolling
branch, reopening is not the right move: that is a *revert-story-at-batch-
review* action (T-C3); ingest refuses with that pointer; (4) the sidecar
is rewritten by the next land from the ledger (`reopened`, prior closure
retained as history).

**Matched observables.** New fingerprint; ledger `reopened` record with
links; the reopen reason; sidecar after land.

**Enforcer.** *Mechanical:* ingest rule (3); validator (2). *Narrative:*
none.

**Intensity.** Hard. **Species.** **Adapter** (a state edit under the
ratification contract). **Model calls.** None.

**Failure protocol.** Rule (3) refusal ⇒ typed pointer to the batch-review
action; otherwise T-A2's failure protocol.

**Emits.** Reopen rate per tenant (a quality signal on closures — factory
and human), reasons histogram.

**Writes / authority.** Card (owner); ledger (authority); sidecar (factory).

**Extensibility.** **Fixed-core.**

**Brownfield note.** Sartor reopened items informally by editing status;
the linkage to prior runs was narrative.

**Since 03 draft-6 (03 §1.5; sync 7bb.1) [owner-ratified; reconciling
mechanics proposed].** After the closure lands, reopen = the owner's
**signed `reopened`** entry with a `reopens[]` entry naming the card-side
closure `c<n>` (T3); a factory-closed card whose file still says
`ratified` reopens by any signed gated change — the validator requires
the `reopens[]` entry. **Before any land** the move is a retraction, not
a reopen (unsigned `retracted` — T-A12); "not yet landed" = the `closed`
entry's `seq` > the sidecar's `history_head.seq` (C6 — 03 §11). Rule
(3)'s pointer stands unchanged for unmerged rolling work.

**Open.** ~~(1) The reopened card keeps its id; runs are the versioned
thing~~ — **[owner-ratified 2026-08-16]**.

### 2.16 T-B1 Narrative → card: ARC / epic content → card body + acceptance [proposed 2026-08-16]

**Family / kind.** B · **written** (card, in the design session).
**Endpoints.** register `narrative` (ARC / epic / milestone prose — the
SDD layer) → register `card` (body + acceptance — the BDD layer), forward.
**Trigger / actor.** The owner with the planning agent, interactive
(5.9). This is the upstream of T-A2; T-A2 is where it becomes durable.

**Above.** Epic intent, rationale, alternatives, sequencing, the owner's
words. **Below.** A card whose *scope sentence is the owner's words* (or
ratified verbatim — never an agent paraphrase: sartor's scope-is-quoted
rule), a `source_narrative` ref (file + anchor), acceptance scenarios that
operationalize the intent, TDD requirements nested, `depends_on` from the
sequencing.

**Matching conditions.** (1) `source_narrative` resolves (file/anchor
exists) — mechanical; (2) the scope sentence is marked as owner-authored
or owner-ratified verbatim; (3) every acceptance scenario is traceable to
a phrase of the narrative (a `traces:` pointer per scenario — mechanical
presence, human judgment on fit); (4) narrative stays in the ARC — the
card points, it does not copy (no second home for intent).

**Matched observables.** Ref resolution; the scope-authorship mark;
per-scenario `traces:` presence; the validator's verdict.

**Enforcer.** *Mechanical:* validator checks (1)–(3)'s presence at T-A2.
*Narrative:* the authoring skill's elicitation checklist (ask, don't
assume; cross-project goals; amplitude as given).

**Intensity.** Advisory at authoring (owner judgment), hard at T-A2 for
the mechanical parts. **Species.** **Transducer** — characteristic:
*preserves* intent as scenarios and scope verbatim; *discards* rationale
and alternatives (they stay in the ARC); *adds* ids, deps, structure.
Verified by conformance scenarios ("a card whose scope sentence is not
owner-marked does not ratify"). **Model calls.** The planning agent —
interactive, human-gated; the only model at this crossing.

**Failure protocol.** T-A2's. **Emits.** Cards per epic; scenarios per
card; time from epic authoring to first card.

**Writes / authority.** Card (owner). **Extensibility.** Mechanism
**fixed-core**; the tenant's narrative structure (sartor ARC vs spolia's
release-as-epic) **tenant-specializable** via the `source_narrative`
resolver.

**Brownfield note.** Sartor: ARC → work items with `decision_owner`;
scope restatement failures (four instances) are the reason for condition
(2). Spolia: release epic with children.

**Open.** ~~(1) Epics/milestones are themselves cards (kind `epic`,
narrative body pointing at the ARC), so batch membership and deps are
substrate relations~~ — **[owner-ratified 2026-08-16]**; card schema
carries it.

### 2.17 T-B2 Acceptance (house dialect) → runnable acceptance suite [proposed 2026-08-16]

**Family / kind.** B · **written** (an artifact: the acceptance
**manifest**), **derived** deterministically from the card.
**Endpoints.** register `acceptance block` (BDD) → register `acceptance
manifest` (TDD-facing: the named checks that must pass), forward.
**Trigger / actor.** Consume (T-B3) and close (T-A9 / T-A12): the
factory, deterministically. **No model.**

**Above.** Scenarios in the house dialect — structured, typed templates:
context / action / observable, each with a **kind** (test-marker · command
· http · file-assert · manual-evidence) and parameters. **Below.** A
manifest: for each scenario, the runner binding (from tenant config:
kind → runner), the check id, and `manual` where evidence-required; plus
the nested TDD requirements as named tests the build must make pass.

**Matching conditions.** (1) Every scenario compiles to a runnable check
**or** is explicitly `manual` — never silently unrunnable; (2) the compile
is deterministic (manifest hash reproducible from card hash + config
hash); (3) runner bindings exist for every kind used; (4) the manifest is
what T-A9 runs and what T-A12 verifies — one artifact, both consumers.

**Matched observables.** Manifest artifact + hash; per-scenario binding;
count of `manual` scenarios; compile errors (typed).

**Enforcer.** *Mechanical:* the compiler refuses on an unbindable
scenario — surfaced back at T-A2 as rule 3 ("runnable-shaped");
*narrative:* the dialect guide in the card template.

**Intensity.** Hard. **Species.** **Transducer** — characteristic:
*preserves* the observable and the pass/fail semantics; *discards* prose
nuance; *adds* bindings and ids. Verified by conformance scenarios ("a
scenario without a checkable observable does not compile"). **Model
calls.** None — the *builder* implements the step code (T-B5); the
compile itself is deterministic because the dialect is structured.

**Failure protocol.** Unbindable ⇒ card `payload_incomplete` at consume,
or `unratified` at ingest if the config lost a binding; recovery: fix the
scenario or the binding. Cards with **only** `manual` scenarios cannot be
factory-closed — they close by human closure (T-A12) with evidence, or
raise an interrupt for attestation.

**Emits.** Scenarios per card by kind; `manual` share (a signal the
tenant needs a runner); compile failures.

**Writes / authority.** Manifest in the factory artifact store; the
Gherkin/EARS *projection* (T-B11) renders the same structure.

**Extensibility.** Dialect **fixed-core** (settled-for-now, 1.5); runner
bindings **tenant-specializable**; new scenario kinds **tenant-defined**
against the dialect schema.

**Brownfield note.** Neither project has acceptance at filing; the round-3
input's "point at green scenario runs, not narrate completion" is this
row.

**Since 03 draft-6 / 04 (sync 7bb.1, 7bc) [owner-ratified shape;
reconciling mechanics proposed].** The compile contract is pinned in 03
§4.4 with the dialect (03 §4): per-kind shapes a discriminated union on
`kind`; `Pattern` = the three-target regex intersection, `run` an argv
array only, `FileCheck` exactly one check (03 §11.7). Runner bindings
live in `config.toml [runners]` — kind → binding, the core four bound by
default; a tenant scenario kind is **declared by its key there** (Y2's
one-home rule — sync 7bc.8), and a binding naming an unshipped runner is
typed at dry run (`config.runner-unshipped` — 04 §6). `accept <id>` is
the standalone consumer of the same manifest (03 §1.13).

**Open.** ~~(1) The dialect's concrete grammar — card-schema doc~~ —
done (03 §4). (2)
Attestation for `manual` scenarios at factory close: interrupt (`policy`
tag) — [proposed-default 2026-08-16]. (3) Isidium 0003 compiles the
dialect to two backends, deterministic **and statistical**; this row
targets the deterministic backend only — a statistical (judge-class)
backend is a declared slot, not to be folded into `manual`.

### 2.18 T-B3 Consume: card + refs + config → typed run payload [proposed 2026-08-16]

**Family / kind.** B · **written** (artifact). Phase 1; **no model.**
**Endpoints.** registers `card` + `project checkout` + `threshold config`
+ `ledger (answers, prior artifacts)` → register `run payload`, forward.
**Trigger / actor.** Dispatch (T-A6); the factory.

**Below — the payload (pydantic, strict):** tenant, run id, the card's
gated content **verbatim** + its hash, the acceptance manifest (T-B2),
**context assembly** (the card's refs resolved at `base_sha` — contents or
paths; the tenant's conventions doc; the relevant ARC excerpt; the
threshold-config subset the run needs), **constraints** (budgets per
phase, allowed write paths = declared surfaces from card refs, privacy
roots denylist, egress allowlist), identity (which bot, which adapter),
answers from T-A8, prior artifacts on re-dispatch, models plan.

**Matching conditions.** (1) Every ref resolves at `base_sha`; (2) the
payload validates; (3) size within the context budget (decoupling *is*
the context budget — a payload that does not fit is a card that is too
broad, not a prompt to be compressed); (4) reproducible — same inputs ⇒
same payload hash; (5) nothing in the payload is derived from the board
or any projection — substrate only.

**Matched observables.** Payload hash; ref resolution list; size vs
budget; validation verdict.

**Enforcer.** *Mechanical:* the assembler; refuses on any failed
condition. *Narrative:* the context-assembly rules doc (progressive
disclosure: curated default, reach-anywhere on demand is the *planner's*
privilege, not the executor's — 5.9).

**Intensity.** Hard. **Species.** **Adapter** — fidelity by round-trip
(payload card content == card at hash). **Model calls.** None.

**Failure protocol.** Unresolved ref ⇒ `payload_incomplete` → design queue
with the missing ref; oversize ⇒ `payload_oversize` → design queue with
the size (data for effort tiers, 7b.4); config subset invalid ⇒ T-C1's
refusal.

**Emits.** Payload size, ref count, assembly duration; oversize rate.

**Writes / authority.** Artifact store. **Extensibility.** Schema
**fixed-core**; context-assembly rules and privacy roots
**tenant-specializable**.

**Brownfield note.** Sartor's N=1 payloads were prompts assembled by hand
in a session — context decay was one of the three named failure drivers.

**Since 03 draft-6 (03 §1.17; sync 7bb.1) [owner-ratified principle;
projection mechanics proposed].** The payload is **hash = required,
payload ⊇ hash**: (1) the card's gated set in canonical serialization,
plus the resolved `refs` content (`refs_resolved` recorded in the
fingerprint) and the `source_narrative` excerpt; (2) the **neighborhood
projection** — a deterministic function of (card graph at `base_sha`,
sidecar, caps) over cards with `status ∈ {ratified, closed}` at their
fingerprint: parent chain, siblings with buckets, direct
dependencies/dependents with `surfaces`, the bound milestone/sprint's
`title` + `## Scope` — delivered as a typed, delimited block labeled as
context. Caps (`payload.context.depth` = 2, `max_bytes` = 16 KiB — 04
§2.2) are **reserved out of the context budget**; the pinned eviction
order truncates and records `context.truncated`, never fails readiness.
The run record carries **`payload_hash`, `config_hash` and the `context`
block**; condition (5)'s "substrate only" now includes the sidecar as a
neighborhood input.

**Open.** (1) Where privacy roots live (tenant config, lean). ~~(2)
Whether the executor may read beyond the payload's refs~~ —
**[owner-ratified 2026-08-20 (03 §1.17, round 34)]**: restrict writes,
never reads — the builder reads everything in its checkout; writes stay
inside `surfaces`; out-of-repo needs are owner-approved requests (T-C5).

### 2.19 T-B4 Plan: payload → plan → light refutation → verdict [proposed 2026-08-16]

**Family / kind.** B · **written** (artifacts). Phases 2–4. **Model
calls: planner, refuter; judge deterministic (lean).**
**Endpoints.** register `payload` → register `plan` (→ `refutation` →
`verdict`), forward — three edges on a chain; the last is a *derived*
guard.

**Below.** A **plan** through its template: steps; **touched surfaces**
(required — feeds T-A5b and T-B5's write guard); tests to add/modify (from
the manifest); a **traceability matrix** scenario → step/test; risks;
questions (an unresolvable one ends the run as `parked`, T-C5). A
**refutation** through its template: typed findings {severity: blocking /
major / minor, claim, location, why}. A **verdict**: proceed / revise-once
/ fail:plan.

**Matching conditions.** (1) Every model call is wrapped: pydantic in →
template prompt → pydantic out, validated, one retry on schema failure,
then `failed:malformed-plan`; (2) plan touched surfaces ⊆ allowed paths
(payload constraints) — else the plan raises a question (`card-ambiguity`)
rather than widening scope; (3) traceability complete — every scenario
maps to a step or test (mechanical); (4) the refuter is prompted to
**refute** the plan's sufficiency against the acceptance manifest, not to
approve it; single Sonnet-class refuter (4.5); (5) judge rule: any
`blocking` finding ⇒ exactly one plan revision (planner call with the
findings), then proceed or `failed:plan`; no blocking ⇒ proceed;
(6) telemetry per call (model, effort, tokens, duration).

**Matched observables.** Plan / refutation / verdict artifacts + hashes;
traceability check result; per-call telemetry rows; retry counts.

**Enforcer.** *Mechanical:* the wrapper (schema validation, retry cap,
budgets, path check, traceability check, judge rule). *Narrative:* the
templates' guidance and the phase agents' skill text.

**Intensity.** Hard. **Species.** **Transducer** (payload → plan: intent
→ procedure; refutation: plan → typed doubt). Characteristic: *preserves*
the manifest coverage; *adds* sequencing and surfaces; *discards* nothing
of the card (verbatim carried). Verified by conformance scenarios ("a plan
missing a scenario in its traceability matrix does not proceed").
**Model calls.** 2 (planner, refuter) + at most 1 revision.

**Failure protocol.** Schema failure ⇒ retry once ⇒ `failed:malformed-*`
(executor defect class); scope widening ⇒ question or `failed:scope`;
budget ⇒ watchdog; question raised ⇒ `parked`.

**Emits.** Plan size; findings by severity; revision rate; models +
effort; refuter miss rate (findings later found downstream).

**Writes / authority.** Artifact store; ledger phase records.
**Extensibility.** Mechanism and templates **fixed-core**; models,
effort, whether refutation runs for a card class **tenant-specializable**
(refutation retained by default, 4.5).

**Brownfield note.** Sartor item 84: refuter/judge stages "proved their
value"; deaths were at the invocation boundary — the wrapper is that
boundary made deterministic.

**Since 03 draft-6 (03 §1.10, §1.5; sync 7bb.1) [owner-ratified guidance;
reconciling mechanics proposed].** Two conditions sharpen: the
traceability matrix must also **reference every `avoid` and `constraint`
guidance id** in the payload — a presence check (03 §1.10; a
`constraint.check` is a dialect check the close gate runs). And
**`questions` is empty at plan time**: a card with open `questions[]`
never dispatches (`has-questions`, T-A4), so a question discovered here
is raised through T-C5 — never self-answered.

**Since 05 (2026-08-26; sync 7bd.10 "a" · 7bd.13 "b" · 7bd.14 "a")
[owner-ratified rulings; mechanics proposed].** Three corrections. (1)
The plan call and the one revision are the **plan author's** — a seventh
roster agent (own bot identity, no grant — 05 §1); "planner" in this
row's model-calls line reads plan author. (2) The **judge is a model
call** (05 §1a accepted, 7bd.9) — superseding "judge deterministic
(default)"; the wrapper still enforces the mechanical floor (any
`blocking` ⇒ exactly one revision) and the judge's verdict lands in the
run record's `verdicts[]` (03 §6). (3) The second failure no longer
exits `failed:plan` — it **parks** (7bd.10 hard gate): the judge renders
the park verdict (Z2), the wrapper assembles the T-C5 typed question
(reasoning in `why_blocked`; plan, refutation, verdicts in
`artifacts_so_far`; `source_tag = plan-failed`), ledger `parked`, the
owner's queue. `failed:plan` retires for this case; the
`failed:malformed-*` defect classes stand.

**Open.** ~~(1) Judge as a deterministic rule (lean) vs a model~~ —
closed by the since-note above (a model; 7bd.9). (2) Whether
tiny cards may skip refutation by tenant class (lean: allowed, off by
default).

### 2.20 T-B5 Build: plan → diff on the story branch [proposed 2026-08-16]

**Family / kind.** B · **written** (story branch). Phase 5. **Model call:
builder.** **Endpoints.** register `plan` → register `diff`, forward.

**Above.** Plan + payload; the worktree on `story/<run-id>` at rolling
HEAD. **Below.** Commits on the story branch, **authored by the wrapper
under the run's bot identity** — the model never holds git credentials or
performs identity operations; a build report through its template
(files touched, tests added, manifest checks self-run, notes).

**Matching conditions.** (1) Writes only within the plan's touched
surfaces ∪ test paths — enforced **at write time** by a guard in the
worktree (PreToolUse-class), not after; (2) the tests named in the
acceptance manifest exist and pass in the builder's self-run (advisory —
the authoritative run is T-A9); (3) no card files, sidecars, or config
touched; (4) commits by the wrapper: bot identity, signed, `Factory-Run`
trailer — one commit at phase end (lean; Open 1); (5) build report
validates; (6) budgets.

**Matched observables.** Diff; guard-block count; self-run results;
commit signature/trailer; report hash; telemetry.

**Enforcer.** *Mechanical:* the write guard; the wrapper's commit step;
budgets/watchdog. *Narrative:* the builder skill text ("implement the
plan; ask rather than widen").

**Intensity.** Hard (1, 3, 4); advisory (2). **Species.** **Transducer**
(plan → code). **Model calls.** 1 (builder), possibly long-running.

**Failure protocol.** Path violation ⇒ blocked at write, counted;
repeated beyond a tenant threshold ⇒ `failed:scope`; budget/timeout ⇒
watchdog; a question ⇒ `parked` (the branch keeps the partial work).

**Emits.** Diff size; files touched vs declared; guard blocks; tokens;
duration; self-run pass rate.

**Writes / authority.** Story branch (factory, bot identity).
**Extensibility.** Mechanism **fixed-core**; builder model/effort and
guard threshold **tenant-specializable**.

**Brownfield note.** Sartor's plan-approved hook and edit/write
dispatchers are the ancestors of the write guard.

**Adopted 2026-08-21 (gajae follow-up 2 —
`../research/gajae-code-2026-08-21.md` §3) [proposed].** The report's
claimed change set is never trusted: the ledger **recomputes the run's
touched set from git** and refuses a report whose claimed set differs —
before judging `surfaces` or any closure (T-A12). The write guard
(condition 1) stays the at-write-time ceiling; this is the belt behind
it.

**Open.** (1) Commit granularity — one commit at build end + one at
reconcile (lean) vs many. (2) Whether the builder may run the full gate
locally (lean yes, read-only on the manifest and gate command).

### 2.21 T-B6 Review: diff → findings → verdict → one reconcile round [proposed 2026-08-16]

**Family / kind.** B · **written** (artifacts; a reconcile commit).
Phases 6–7. **Model calls: refuter (single, Sonnet-class), builder for
reconcile, refuter again bounded to the findings.**
**Endpoints.** register `diff` → register `findings` → register `verdict`
(→ `reconciled diff`), forward.

**Matching conditions.** (1) The refuter is prompted to **refute** the
claim "this diff satisfies the acceptance manifest and the plan" — and
must fill a typed **traceability field** (scenario → evidence in the
diff/tests) — a rubber-stamp is structurally impossible (MAST FM-3.1);
(2) findings typed {severity, claim, location, refutation attempted};
(3) verdict rule (deterministic): any `blocking` ⇒ **one** reconcile
round — the builder addresses each finding and returns a typed reconcile
report {finding id → fixed / refuted-with-reason /
deferred-as-suggestion — rides the run report's `suggestions[]` (cond.
6; renamed from "deferred-as-draft" 2026-08-26 — bots do not write
drafts)};
(4) second refuter pass **bounded to the findings** (no new sweep);
(5) verdict `pass` | `fail:review`; (6) out-of-scope findings ride the run
report's `suggestions[]` (T-C6) to the inbox, dispositioned with the
owner — **bots do not write drafts** (03 §1.18, round 28, superseding the
2026-08-16 auto-file-drafts lean) — never silently expand the story;
(7) telemetry per call.

**Matched observables.** Findings artifact; traceability field
completeness; reconcile report; second-pass result; suggestions filed;
the verdict; per-call telemetry.

**Enforcer.** *Mechanical:* wrapper (schemas, the one-round bound, the
traceability-field requirement, suggestions filing). *Narrative:* refuter skill
text (adversarial stance).

**Intensity.** Hard. **Species.** **Transducer** (quality → Verdict —
isidium's judge species). Characteristic: *preserves* the manifest as the
bar; *adds* severity and location; *discards* style opinions unless the
tenant's conventions doc names them. Verified by conformance scenarios and
by the **miss rate** measure. **Model calls.** 2–3.

**Failure protocol.** `fail:review` ⇒ T-A7 `failed:scope` (design queue)
with the findings attached; malformed ⇒ retry once ⇒ `failed:malformed-*`.

**Emits.** Findings by severity; reconcile outcomes; **miss rate** — a
finding the owner makes at batch review that the refuter missed
(→ triggers panels per 4.5: "panels only on measured misses"); refuter
model/effort.

**Writes / authority.** Artifact store; reconcile commit on the story
branch (wrapper, bot identity). **Extensibility.** Mechanism
**fixed-core**; refuter class, effort, panel trigger threshold
**tenant-specializable**.

**Brownfield note.** Sartor: adversarial review "significantly improved
quality"; the reviewer refutes, conflicts go to the user — the
one-bounded-round rule keeps that without an open loop.

**Since 03 draft-6 (03 §1.10, §1.18; sync 7bb.1) [owner-ratified;
reconciling mechanics proposed].** Reviewer findings **cite guidance
ids** — a diff that ignores an `avoid` or `constraint` without a stated
reason is a finding (03 §1.10, presence check). Out-of-scope findings
travel as the run report's bounded `suggestions[]` (T-C6) and land as
inbox intake, dispositioned with the owner (03 §1.18, 03a).

**Open.** (1) The panel trigger: miss-rate threshold over a window
(tenant config; lean: 2 misses in 10 stories → panel of 3 for the next
5). (2) Whether the reconcile builder is the same model as the build
(lean yes — continuity of the artifact, not the process).

### 2.22 T-B7 Run → close report [proposed 2026-08-16]

**Family / kind.** B · **written** (ledger). **Endpoints.** register `run
(phase records + artifacts)` → register `close report`, forward.
**Trigger / actor.** Run end; **the wrapper assembles the report from the
typed phase outputs — no model writes it.**

**Matching conditions.** (1) The report is generated, not narrated: every
field comes from a phase record, artifact hash, or telemetry row; there is
no free-text "what I did" field — the false-claim class ("scope
reconciliation clean") has no place to live; (2) validates (T-A7's
template); (3) every artifact referenced exists at its hash; (4) surfaces
actual computed from the diff, not from the plan.

**Matched observables.** Report hash; artifact hash check; the ledger
record.

**Enforcer.** *Mechanical:* the assembler; the ledger writer's validation.
**Intensity.** Hard. **Species.** **Adapter** (fidelity: report ↔
artifacts, verified by hash). **Model calls.** None.

**Failure protocol.** T-A7's. **Emits.** Nothing beyond T-A7's.
**Extensibility.** **Fixed-core.**

**Brownfield note.** Sartor's handoffs were narrated by the agent and
verified by hash pointers afterwards; here the report *is* the pointer set.

### 2.23 T-B10 Ledger (+ substrate) → dashboard [proposed 2026-08-16]

**Family / kind.** B · **derived**. **Endpoints.** systems `ledgers (N
instances)` + registers `board projections` + `queue artifacts` +
`sourced drafts` → system `dashboard` (TypeScript, **read-only**, 4.6 +
7i.1), forward.

**Views (ratified scope).** Jobs/runs live; per-phase stats; cost;
**interrupt inbox** (parked questions); **sourced-drafts inbox** (bot-
filed drafts awaiting owner review — 7i.1); orientation over board /
epics / sprints / cards with statuses; performance over time (trend-
spotting); cross-tenant view as a *join* of per-tenant ready-views
(T-C8 held — never one queue).

**Matching conditions.** (1) Nothing displayed that is not derivable from
ledger + substrate + config — every number traces to a query (provenance
on hover); (2) **no writes** — promotion of drafts, answers, tending all
happen in the planning surface / ratification path; the dashboard links
out; (3) freshness stamped per view (ledger cursor + snapshot time);
(4) N-ledger seam from day one (7d.3): a tenant is a first-class key on
every view; (5) unreadable source ⇒ stale banner, never fabricated.

**Matched observables.** Snapshot hashes; cursor per tenant; view →
query provenance.

**Enforcer.** *Mechanical:* the factory writes **read-only JSON snapshots
per tenant** to a volume (lean; Open 1); the dashboard serves them; no
DB, no write path exists to remove. *Narrative:* none.

**Intensity.** Hard (1, 2). **Species.** **Adapter** (fidelity: view ==
snapshot; regenerate-and-compare). **Model calls.** None.

**Failure protocol.** Stale banner; missing tenant snapshot ⇒ tenant shown
as unreachable.

**Emits.** View freshness; snapshot sizes; owner interaction telemetry
(what gets looked at — for the orientation interface's own tuning).

**Extensibility.** Core views **fixed-core**; per-tenant view config
**tenant-specializable**.

**Open.** (1) Transport: file snapshots on a volume (lean) vs a read-only
API. (2) The dashboard's own repo: inside the factory repo (lean, one
release) vs separate.

### 2.24 T-B11 House scenario → Gherkin / EARS projection [proposed 2026-08-16]

**Family / kind.** B · **derived** (rendered file, optional). Settled-for-
now (1.5): a *projection*, not a rejection — isidium decision 0003
(`docs/process/decisions/0003-practices-ratification.md`) already holds
this: the house markdown scenario dialect is the *authored* dual-register
source, compiled to two machine backends (deterministic + statistical),
and `.feature` is a one-way generated emitter, never authored. **Endpoints.** register
`acceptance block` → register `Gherkin (.feature) / EARS text`, forward.
**Species.** **Adapter** — a rendering of the same structure T-B2
compiles; fidelity by regenerate-and-compare; never edited by hand (a
hand edit is a fidelity defect, since the house dialect is the source).
**Model calls.** None. **Extensibility.** **Tenant-defined**, optional;
useful where a tenant's tooling (Cucumber-class runners) or readers want
that surface. **Enforcer.** Renderer + regenerate check when enabled.
**Open.** None beyond the dialect grammar (card schema).

### 2.25 T-C2 Vendoring: factory → project (the toolkit) [proposed 2026-08-16]

**Family / kind.** C · **written** (files in the project, by PR).
**Endpoints.** system `factory release` → system `project` (the vendored
toolkit: card template + schema, validator/`cards check` hook, hasher +
canonicalization, policy reader, board renderer, branch-protection
templates, read-only ledger snapshot), forward. **Trigger / actor.**
Tenant onboarding and every factory release: the lander identity opens a
**toolkit-upgrade PR** on the tenant repo (path-scoped to the toolkit
path); the owner merges. Also on demand (`factory vendor <tenant>`).

**Matching conditions.** (1) Every vendored file carries a provenance
header (factory revision, toolkit version, generated_at, source path) —
the sartor/spolia vendoring convention reused; (2) a pinned lock file in
the project (`toolkit.lock`-class) names the version; (3) vendored bytes
== release artifact bytes (hash); (4) the toolkit is standalone-capable
(0.4) — the project's CI runs the vendored check without the factory;
(5) the ledger snapshot is read-only, cursor-stamped, and never the
authority; (6) the upgrade PR touches only the toolkit path (never cards,
never config — a config change is a separate owner commit on the
ratification path).

**Matched observables.** Provenance headers; lock file; per-file hashes;
CI green with the vendored check; snapshot cursor.

**Enforcer.** *Mechanical:* `cards check` verifies vendored-file hashes
against the lock and **warns** on local modification; T-C1 **refuses
dispatch** on a modified or unsupported toolkit until re-vendored — or
until the local change is upstreamed as a draft into the factory repo
(section 11's loop: contributions flow up, releases flow down). *Narrative:*
the onboarding doc.

**Intensity.** Hard. **Species.** **Adapter** (fidelity by hash). **Model
calls.** None.

**Failure protocol.** Hash mismatch ⇒ warn locally, refuse factory-side;
unsupported version ⇒ T-C1's refusal naming the upgrade; PR conflicts ⇒
owner resolves (toolkit path is factory-owned; conflicts mean local
edits — upstream them).

**Emits.** Version skew per tenant; time-to-upgrade; local-modification
events (a signal the toolkit is missing something).

**Writes / authority.** Toolkit path in the project (factory-authored,
owner-merged); lock file. **Extensibility.** Mechanism **fixed-core**;
*what* is vendored (e.g. no in-project board renderer) **tenant-
specializable**.

**Brownfield note.** Spolia → sartor board vendoring with per-file
provenance headers is exactly this, done by hand.

**Open.** (1) Snapshot cadence: at every land + on demand (lean).

### 2.26 T-C4 Notifier: line → push + inbox [proposed 2026-08-16]

**Family / kind.** C · **written** (event → delivery record).
**Endpoints.** system `line` (typed events: question raised, run failed,
batch PR opened, batch drained, tenant refused, watchdog fired, toolkit
upgrade available) → system `owner` via channel(s), forward.

**Matching conditions.** (1) Event from a closed, typed vocabulary;
(2) **the dashboard inbox is the record, push is the hint** — a lost push
never loses a question (T-C5's contract holds regardless of delivery);
(3) channel per tenant/owner from config behind a seam: self-hostable
push backend (ntfy-class, I-33) as the default; the Claude Code
`PushNotification` tool during interactive sessions; email fallback;
(4) content policy per channel — full text vs summary (a phone lock screen
is a public surface); (5) one push per question id (dedup); low-severity
events digest on a tenant cadence; (6) delivery ack recorded in the
ledger when the channel supports it.

**Matched observables.** Event id; delivery record + ack; inbox entry;
digest membership.

**Enforcer.** *Mechanical:* the notifier refuses non-vocabulary events;
retry with backoff; the line **never blocks** on notification.
**Intensity.** Advisory (delivery) — the hard record is the inbox.
**Species.** **Adapter** (notification ↔ event by id). **Model calls.**
None.

**Failure protocol.** Channel down ⇒ retry, inbox holds, escalation to a
fallback channel after a tenant-set delay.

**Emits.** Notifications by type; ack latency; time-to-answer (with T-A8);
digest sizes.

**Extensibility.** Event vocabulary **fixed-core**; channels
**tenant-specializable**; new channel drivers **tenant-defined** against
the seam.

**Brownfield note.** None — neither project notifies.

**Open.** (1) First backend: ntfy-class self-hosted (lean) — verify
against the agent-station plan.

### 2.27 T-C6 Execution adapter seam: claude-code-action ↔ headless CLI-in-container [proposed 2026-08-16]

**Family / kind.** C · a **seam** (adapter contract), not a state
crossing. **Endpoints.** register `run payload` (T-B3) → system `executor
runtime` → registers `phase artifacts` + `close report` (T-B7), forward.
Ratified order (4.6): claude-code-action first (GitHub), headless
CLI-in-container second (agent-station / homelab forges).

**The contract every adapter must meet.** Same typed payload in; same
typed phase outputs and close report out; the wrapper's guarantees hold
inside it — write guard at write time (T-B5), identity held by the
wrapper not the model, budgets + watchdog, end-and-resume on questions
(T-C5), telemetry per phase (4.7). An adapter is **registered only after
passing the conformance suite** (the same scenario runs) — the seam is
verified by conformance, never by trust.

**Declared characteristics (what each preserves / costs).**
- *claude-code-action:* runs on the forge's runner (no self-hosted
  compute), GitHub-native triggers; identity via the App (API-signed, no
  rebase-class ops) or per-bot account + SSH signing key (full git);
  **risk to verify:** whether the write guard and the wrapper's hook set
  can be installed inside the action's runtime — if not, the guard
  degrades to post-hoc diff checking and the row says so.
- *headless CLI-in-container:* full control of hooks, guard, identity,
  worktrees; self-hosted compute; forge-agnostic; the natural home for
  agent-station.

**Matching conditions.** (1) Conformance suite green for the adapter
version; (2) adapter selected per tenant config; (3) the run's ledger
record names adapter + version; (4) no adapter-specific field leaks into
the payload or report schemas.

**Enforcer.** *Mechanical:* registration gate (conformance); schema
validation on both sides. **Intensity.** Hard. **Species.** **Adapter.**
**Model calls.** Inside the adapter — the phase agents; none at the seam.

**Failure protocol.** Adapter start/timeouts ⇒ `failed:infra`, one retry;
conformance regression on upgrade ⇒ adapter version not registered.

**Emits.** Per-adapter cost, duration, success rate, guard-degradation
flag — the data that decides which adapter a tenant runs.

**Extensibility.** Contract **fixed-core**; adapters **tenant-defined**
against it (conformance-gated).

**Open.** (1) The write-guard question on the action runtime — verify
before making the action the default for any tenant.

**Since 03 draft-6 / 03a + the gajae adoption (2026-08-21)
[owner-ratified; reconciling mechanics proposed].** The close report
carries a **typed, bounded `suggestions[]`** section — the builder's only
voice toward the tenant (it holds **no store credential** and never calls
the tenant): bounded by `inbox.max_per_run` (default 10) and
`max_per_actor_per_day`, overflow a count (`suggestion-overflow`); at
land the store writes each as inbox intake with **`from.run`** set
(`via = "land"` — 03a; 03 §1.18); the ledger keeps the run-report copy,
and a mismatch either way is `suggestion-mismatch`. **The signer seam
stays by pointer:** no adapter renders a signing surface — signatures
happen where the owner is (03 §1.12; agent-station by pointer). Adopted
[proposed] (gajae follow-up 1, with T-C3): the **untrusted-PR validation
recipe** — the validator checked out from the immutable trusted base ref;
the PR head read as bytes only; read-only permissions, no secrets;
tenant-controlled code never executed to validate a tenant PR
(`../research/gajae-code-2026-08-21.md` §3).

**Ruling 2026-08-26 (sync record 7bdb.3) [owner].** Initial deployment =
Claude Code on the owner's subscription (the two adapters above). Target
harness = **pi** (`earendil-works/pi-mono`), swapped in when either pi runs
Claude on plan-limit billing or homelab local models serve the phases.
**Harness-neutral by construction:** the swap must need little, preferably
no, modification above this seam. Consequences [proposed, 7bdb.4]: executor
policy (allowlist, guard paths, budgets, model per phase) is declared once
in factory config and *rendered* per adapter (Claude Code: `settings` +
`PreToolUse` hook; pi: a factory-owned extension package); skills in the
Agent Skills standard and context via `AGENTS.md`; the close report as a
terminating typed tool call; telemetry adds `harness`, `harness_version`,
`billing_class`; the pi adapter is built and conformance-green *before* the
trigger fires. Assessment: `../research/pi-harness-2026-08-26.md`.
**Open (added):** (2) the sequencing read — the container adapter (the only
one pi can fill) in the same release as the action — awaits the owner; (3)
watch: Anthropic third-party billing; homelab model capability per phase;
RFC 0015's commercial boundary; pi's `AgentHarness` runtime stabilizing.
Write-guard-on-action model: `../research/openworker-2026-08-26.md` (risk
as declared data, `EGRESS ≠ READ`).

**Since the isidium review (2026-08-27) [owner-ratified (7be.3)].** The
declared characteristics above become a **per-adapter capability matrix** —
declared-degradation rows the conformance suite checks; open (1)'s
hooks-in-runner question becomes a row, not a standing unknown (05 §3;
`../research/isidium-review-2026-08-27.md` §3).

### 2.28 T-C7 Forge driver seam: GitHub ↔ Gitea/Forgejo ↔ GitLab [proposed 2026-08-16]

**Family / kind.** C · a **seam** (adapter contract). **Endpoints.**
system `factory` → system `forge`, both directions.

**The contract.** fetch/clone (read creds); push (bot identity); branch-
protection / path-rule setup from templates; PR/MR open with generated
body, CI status read, merge status read; webhook / trigger registration
(push-triggered ingest, T-A2); bot account provisioning (or App);
signed-commit verification status; each driver publishes a **capability
matrix** (e.g. "path rules not available on this plan" — the GitHub
private-repo case from section 11) and the factory adapts: where forge
enforcement is missing, factory-side enforcement stands alone and the
tenant config must acknowledge the gap explicitly (`accept_forge_gaps`),
else fail-closed.

**Matching conditions.** (1) Conformance suite green per driver version;
(2) capability matrix declared and current; (3) required capabilities
present or explicitly accepted-as-gap in tenant config; (4) no
forge-specific field in cards, payloads, or reports.

**Enforcer.** *Mechanical:* registration gate; the capability check at
T-C1. **Intensity.** Hard. **Species.** **Adapter.** **Model calls.**
None.

**Failure protocol.** Forge API errors ⇒ retry with backoff ⇒
`environment`; capability gap unacknowledged ⇒ tenant refused with the
list.

**Emits.** API error rates; rate-limit hits; capability gaps by tenant.

**Extensibility.** Contract **fixed-core**; drivers **tenant-defined**.
GitHub first, Gitea/Forgejo second (homelab), GitLab when a tenant needs
it.

**Open.** None beyond the plan-matrix verification already noted.

### 2.29 T-C8 Cross-tenant view — a held seam [proposed 2026-08-16]

**Family / kind.** C · **derived** (dashboard join) — **held**.
**Endpoints.** systems `tenant A ready-view` … `tenant N ready-view` →
system `dashboard cross-tenant view`. Not crossed: no central queue; no
conversion of per-tenant priorities into one currency; a global priority
number appearing anywhere is premature closure (I-34 held: the gap is the
signal).

**What is allowed at the seam.** (1) A read-only join that keeps the
tenant key on every row; (2) **capacity scheduling** for a multi-tenant
instance — which tenant the picker serves next is a factory-side
threshold config (round-robin / weighted share / owner order) — this
allocates *turns*, it never ranks cards across tenants; (3) informational
`external_ref` pointers from a card to another tenant's card (context for
humans and planners) — **never** a readiness guard: readiness reads only
its own tenant's ledger.

**Matching conditions.** No code path orders two tenants' cards in one
list; the join preserves tenant on every row; capacity config is
per-instance and separate from any tenant's threshold config.

**Enforcer.** *Mechanical:* conformance scenario ("no cross-tenant
ordering exists"); type-level — the ready-view type carries tenant and the
join type is a map tenant → view, not a list. **Intensity.** Held.
**Species.** **Held.** **Model calls.** None.

**Failure protocol.** A conversion appearing here is a defect to remove,
not a feature to govern.

**Emits.** Per-tenant capacity share; cross-tenant starvation (a tenant
not served within its configured window).

**Extensibility.** **Fixed-core** (the hold); capacity policy
**instance-specializable**.

**Open.** (1) `external_ref` as informational only — lean yes; a
card-schema field.

## 3. Standing rules for this doc

Every row is [proposed] until the owner marks it. Rows quote sync-record
decisions by number for traceability inside the docs — in chat, the thing
is restated, never the number. Known limits are declared in the row, not
filled. When a row's contract has no observable, the row says so.
