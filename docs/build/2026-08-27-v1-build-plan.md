<!-- provenance: schema=1 project=the-factory(working-label) session=ff73f7ed-85be-43d0-8bc7-55aad4b6f440 actor=amodal1 agent=anthropic/claude-fable-5 generated_at=2026-08-27 status=draft-0 -->

> **Assumes:** every design doc complete in first draft — `03-card-schema.md` draft-6, `03a`, `03b`, `04-config-schema.md` draft-1, `05-agent-roster.md`, the reconciled catalog; the handoff `../handoffs/2026-08-27-design-complete-to-sartor-bridge.md`; the round-6 review's section 4 and the bloat re-count's section 4 (`../../review-artifacts/2026-08-21-round6/r6-bloat.md`) as the v1 sequencing inputs.
> **Descends from:** owner, 2026-08-27, verbatim: *"pickup the handoff. we need to do the building before starting the sartor bridge"* — the handoff's own rule: if the store is unbuilt, the bridge session becomes a build-planning session. The store is unbuilt. This is that plan.
> **Expected reader:** the owner (the fork checkpoint, section 5), then every build session that picks a work package up.
> **Does not cover:** the factory line proper (dispatch, the execution adapters, the roster's model calls — Family C of the catalog) beyond naming where it attaches; the bridge session's own work (the sartor cut-over list stays its input); agent-station's deployment (by pointer).
> **Status:** **draft-0** (2026-08-27) — **[proposed]** throughout. **B1 RULED 2026-08-27 (sync 7bf.3):** the project is **`isidium-factory`**; the governed store is its own part **`isidium-store`**; one CLI **`isidium`** with the store's verbs at its top level; imports `isidium.store` / `isidium.factory`. **B2–B4 proceeding as [proposed-default]** (7bf.4) — the owner's to change before WP3/WP4 consume them. Marks as in 03.

# v1 build plan — the store, the registry, the clients (isidium-factory)

## 0. What this plan fits (fixed by the design; not re-decided)

- **Python + pydantic core first, Rust-shaped strictness** (round 42; 03 §0): closed enums, discriminated shapes, `i64`, no floats, pinned bytes; every type is a port, not a redesign.
- **The store is a service in its own container, one per tenant** (W4, 7ba.6); everything else — the tenant container, the factory, the planner, the workstation — is a client (03 §1.3, 03b §2).
- **The ten verbs; `write` the one writer; one `derive` at every gate, refusals included** (03 §1.2). Verbs are thin wrappers; the act is derived from the diff.
- **The registry:** `registry@1` (the nine-member constraint vocabulary, the fixed point), `config@1`, `card@1`, `inbox@1`, `sidecar@1`, `sidecar-events@1`, `board@1` grant-only (04 §3–4); one schema = validator + tool-call input schema + generated types (round 57).
- **Signers:** `remote-totp` the only built backend; `software_key_ack` the waiver path; `tpm-hello` / `yubikey` / `signal-approve` declared in the closed enum and refusing with the available set (7bc.3; 04 §2.2).
- **v1 sequencing already ruled deferrable with the seam named** (round-6 review §4; bloat §4): three runners (`pytest`, `shell`, `file`), two backends, three shapes (`bdd`, `task`, `spike`), four document types; the neighborhood projection, `constraint.check` and `manual_attestation` arrive at **first dispatch**, not bridge authoring.
- **Conformance oracles** (03 §5.3): the r3/r4/r5/r6 prototypes agree byte-for-byte on the build and closure hashes; `r6-impl-d6` carries 220 scenarios; `impl-d1` carries 104 config checks. **A fifth hasher must match** — the build is that hasher.
- **Harness-neutral by construction** (7bdb.3–7bdb.4); **no migration code** (round 40); **agent-station and isidium by pointer**; prompts are code in this repo (7bd.11).

## 1. Two gates, in order — bridge-ready, then first-test-ready

The handoff's queue names one "build v1"; the design's own sequencing splits it at the bridge (round-6 review §4: *"needed at first dispatch, not during bridge authoring — sequence, not deferral"*).

| Gate | What must work | Verbs / components |
|---|---|---|
| **v1a — bridge-ready** | sartor's container points at its store; `init`; the owner and the planner author epics and stories; the dry run; one signature per sitting; every write journaled, committed and pushed to `main`; the hook refuses local governed-path changes | `init` · `write` (`NewCard{slug}`, edits, `--set`) · `show Card \| Board \| Queue \| Inbox \| Schema` · `check` · `ratify` (`--dry-run`, `writes: [WriteRequest]`, `ids`) · `repair --history / --journal` · the journal · the counter · git commit + push · the signer seam (`software_key_ack`, `remote-totp` client half) · grants · the thin client + hook · the planner's tool surface + prompt v1 |
| **v1b — first-test-ready** (sartor C/D/E) | the factory lands, accepts, takes suggestions; the sidecar and events; the full projected status; ingest and reconciliation | `land` · `accept` (+ three runners) · `suggest` · `disposition` · `state.json` + `state/history.jsonl` · the eleven status rows incl. † · `BOARD.md` at land · the lander client · ingest (9.5) · reconciliation (9.6) · the neighborhood projection |
| **v1c — the line** | dispatch and the execution adapters; the roster's model calls | Family C of the catalog; the Claude Code adapters (4.6), the container adapter (7bdb.4(7) awaiting the owner); **not this plan's horizon** |

## 2. Layout — one repo, one distribution, src layout [proposed]

```
pyproject.toml                       # root: tooling only (ruff, mypy, pytest); no distribution
packages/isidium-store/              # distribution `isidium-store`; console script `isidium` (7bf.3)
  pyproject.toml
  src/isidium/store/                 # PEP 420: no src/isidium/__init__.py — `isidium` is the namespace
    core/      refusal.py canon.py chain.py grammar.py derive.py status.py board.py   # pure functions, no I/O
    registry/  schemas/{registry@1,config@1,card@1,inbox@1,sidecar@1,sidecar-events@1,board@1,page@1}.toml
               vocabulary.py loader.py config.py card.py   # the validators read schema documents (built WP1)
               codegen.py generated/{models.py,tools/*.json}  # the typed model + tool-call schemas (WP3, with the tool surface)
    server/    journal.py (sqlite)  gitrepo.py  grants.py  service.py
               verbs/{write,ratify,show,check,init,repair}.py        # v1a
               verbs/{land,accept,suggest,disposition}.py           # v1b
               signer/{seam.py,software_key_ack.py,remote_totp.py}
    client/    cli.py (typer: the ten verbs at top level + `isidium <part>` PATH dispatch)  http.py (httpx)  hook.py  mcp.py
packages/isidium-factory/            # distribution `isidium-factory`; group `isidium factory …`
  pyproject.toml
  src/isidium/factory/  ingest.py lander.py …                        # v1b
tests/
  conformance/  # the oracles as tests: r6 corpus.json + chain.json, r6-d6 scenarios, impl-d1 checks
  unit/
prompts/planner/v1.md                # 7bd.11 — the seven-step invocation protocol (05 §2)
Containerfile                        # the store image; `python -m isidium.store.server` is the same process
```

- **Dependencies, minimal and named:** `pydantic` 2 (the typed model), `cryptography` (Ed25519, ECDSA-P256), `httpx` (client), `typer` (CLI), `mcp` (the tool surface — the one addition to what is installed today); stdlib `sqlite3`, `tomllib`, `hashlib`, `unicodedata`; **git via plumbing subprocess** (present in every container; the Rust port uses `gix`/`git2`). No ORM, no web framework beyond the stdlib `http.server` is **not** enough for mTLS — `uvicorn` + a minimal ASGI app, or `hypercorn`; one of the two, chosen at WP3 by what mTLS costs in each.
- **Python ≥ 3.12** (WSL Ubuntu 24.04 and agent-station's floor; `tomllib` needs 3.11+). Workstation has 3.13.
- **`ruff` + `mypy --strict` from the first file**; `pytest` with the conformance suite as the first tests. Code files LF (`ruff` `line-ending = "lf"`); design docs stay CRLF; `.gitattributes` `* -text` untouched — bytes are preserved both ways.

## 3. Technical defaults — stated so they are visible, not silently taken [proposed]

1. **Transport:** HTTP/1.1 + JSON over mTLS, the channel pinned in the registration (03b §2); one persistent connection per client; the **same pydantic request/response models on both sides**; the MCP server is a stdio wrapper over the client library whose tool input schemas are **generated from the registry** — "the model is constrained to the form at the moment it writes" (round 57).
2. **Journal, counter, blob cache:** one SQLite file per tenant inside the store container (WAL); `ratify`'s row locks and `write`'s compare-and-swap are one transaction each; the journal is append-only, hash-chained as 03b §2 pins; mirrored to the witness layer by pointer.
3. **Git:** the store holds a clone of the tenant repo; a write is plumbing (`hash-object` → `update-index` → `write-tree` → `commit-tree` → `update-ref`) + **one push per call** (9.4); author = caller, committer = the store identity — pinned at build as `store@<tenant-namespace>`; a rejected push = one fetch + a clean rebase (governed paths cannot conflict).
4. **The typed model is generated:** the registry TOML documents are the source; `codegen.py` emits the pydantic models and the tool-call JSON Schemas; both are checked in; a test regenerates and diffs — drift impossible by construction, as ratified. Rule functions (shape layer rules, relations, acyclicity, EARS) key on rule ids beside the generated model; the nine-member vocabulary is the structural half.
5. **The store runs anywhere as one process** (`python -m isidium.store.server --tenant <t>`); the Containerfile wraps that; dev and the conformance suite run it in-process with an in-memory git double (`memgit`, kept from r6) **and** against a real throwaway repo.
6. **Signer seam:** `sign(tenant ‖ h)` / the batch form, `alg:key_fpr:base64`; `software_key_ack` = a client-side Ed25519 key file under the owner's user, every signature labeled software-grade (03 §1.12); `remote-totp` = the client half only — submit `{tenant, hash, diffs}`, poll — against a **contract + a dev stub** here; the service itself is agent-station's (by pointer).

## 4. Work packages — each ends in an owner checkpoint [proposed]

| WP | Deliverable | Done when | Oracle |
|---|---|---|---|
| **WP0** | scaffold: `pyproject`, src layout, ruff/mypy config, the conformance fixtures copied under `tests/conformance/` and wired as tests | `pytest` runs, conformance red, lint green | — |
| **WP1** | the core: `canon`, `chain`, `grammar`, `derive` (diff · recompute table · append-only · predicate), the registry (vocabulary, loader, the eight schema documents, the config and card validators) | every corpus pair and chain fixture byte-agrees; `registry@1` validates itself over the full form | r6 `corpus.json`/`chain.json`; impl-d1 fixed point — **DONE 2026-08-27** (11/11 oracle checks, 47 tests, mypy strict clean; `codegen` moved to WP3 with the tool surface it serves) |
| **WP2** | the store: journal, counter, git plumbing, grants, the signer seam (+ two backends), `write` for every document type, `ratify` (dry run + batch), `show`, `check`, `init`, `repair` | r6-d6's 220 scenarios green against the real store; impl-d1's 104 green against `config.toml` through the same `write` | r6-d6 `scenarios.py`; impl-d1 `run_all.py` — **DONE 2026-08-27** (commit db82bdd; 76 tests; the `land`/`accept` scenarios move to WP5); **review applied 464cd4f — 87 tests** |
| **WP3** | the service + clients: the mTLS server, the `cards` CLI, the hook, the MCP tool surface, `init` installing client + hook + schemas into a tenant repo; the in-project board/queue renderer | end-to-end on a throwaway tenant repo: `init` → `write(NewCard)` → dry run → `ratify` → push → `check` in CI → the hook refuses a hand edit | the walk runs as a test (`tests/store/test_walk.py`); notes under `review-artifacts/2026-08-27-wp3/` — **DONE 2026-08-27** (commit a915a66; review applied adfdab9, 115 tests) |
| **WP4** | **bridge-ready:** the store deployed for sartor (fork B4); the planner prompt v1 + Agent Skills skill + `AGENTS.md`; one real card authored end-to-end with the owner | the owner signs one card in sartor's repo; `cards check` green in sartor CI | the sartor bridge session begins |
| **WP5** | **v1b:** `land`, `accept` + runners, `suggest`/`disposition`, sidecar + events, the eleven status rows, `BOARD.md` at land, the lander client, ingest + reconciliation, the neighborhood projection | the sidecar lands from a synthetic run report; `accept --close` on a bridged card | r6-d6's land/X2 scenarios; new fixtures |

**Review practice (05 §3, standing):** an adversarial round with fresh agents at the close of WP1 and WP2 (the bloat refuter rides — "one call where one would work"; the Rust-strictness lens; the efficiency lens); artifacts preserved under `review-artifacts/<date>-wp<n>/` with a README naming the oracles. Never forks (a fork cost ~800k tokens).

**Size, honestly:** the five prototypes total ≈ 5.6k lines of stdlib Python for the core and config alone; product-grade with typed models, real git, SQLite, mTLS, CLI, hook, MCP and tests is several sessions. WP1 + WP2 are the bulk and are fully pinned; WP3 is plumbing; WP4 is a deployment and a prompt.

## 5. Forks — as ruled (sync 7bf.3–7bf.4)

| # | Fork | Ruling |
|---|---|---|
| **B1** | the name | **[owner-ratified 2026-08-27 (7bf.3)]** — project `isidium-factory` (`take-tempo-public/isidium-factory`); the governed store its own part `isidium-store`; one CLI `isidium`, the store's verbs at its top level, other parts as groups; imports `isidium.store` / `isidium.factory`. The naming scheme (one name per part, ecosystem spelling, PATH dispatch) is shared with the isidium repo as a suggested adoption. |
| **B2** | the sequence | **[proposed-default]** (7bf.4) — v1a → sartor bridge → v1b → first test |
| **B3** | the bridge's signer | **[proposed-default]** (7bf.4) — `software_key_ack` now, a visible waiver; `remote-totp`'s client half against a contract + dev stub; the service on agent-station later (by pointer) |
| **B4** | where sartor's store runs | **[proposed-default]** (7bf.4) — one process + a Containerfile now; placement decided at WP4 (agent-station as designed, or a said-as-such WSL2 interim) |

## 6. Session hygiene

- Design docs CRLF (verify `count(\n) == count(\r\n)` after every write); code LF; cp1252 console — never print raw non-ASCII.
- Record every ruling in the sync record (next: 7bf) at the amplitude given; owner words verbatim; `[proposed]` on every default here until the owner says otherwise.
- The prototypes under `review-artifacts/` stay as they are — evidence, never edited; the build cites them, never imports them.
