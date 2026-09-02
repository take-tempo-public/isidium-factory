<!-- provenance: schema=1 project=the-factory(working-label) session=ec4ace95-0672-4131-854d-4e69ae7fd1e4 actor=amodal1 agent=anthropic/claude-fable-5 generated_at=2026-08-20 status=proposal -->

> **Assumes:** `03-card-schema.md` draft-2 and the round-3 review; the catalog's T-A1 (bot drafts / sourced-drafts inbox), T-C5 (interrupt answers), T-C6 (execution adapter report contract), T-A10 (land).
> **Descends from:** owner reframe, round 27 (2026-08-20), verbatim: *"a tenant is a standalone project. it's tools for interacting with the factory are just that. tools for interacting with an independent entity that is also operating under zero-trust methods. the factory is using the tenant's tooling (enabled by it's factory MCP). the factory is an external operator of sorts. ony the planner or a human can write cards that must pass through the process we've discussed. if the builder has suggestions based upon its work, it should hand those back to the tenant as suggestions that get reviewed and approved (probably with the planner). your method seems like it would support this, bu we need something similar to a ledger where suggestions are sourced that the planner reviews one each invocation or a human can read when coding. think about that anc come back with a proposal"*
> **Draft-5 update (2026-08-21, rounds 49, 52, 57).** Three mechanics below are superseded and read as follows: (1) **drafts are cards** (W1) — `accepted as draft` creates a card in `cards/` with `status = "draft"`, `source = "suggestion"`, `see = ["s<n>"]`; there is no `drafts/` directory, no `draft_key`, no `promoted_from`; (2) the three disposition verbs are one verb — **`disposition <s> --outcome accepted|declined|deferred [--as card|guidance|note]`** (W9); (3) **`SUGGESTIONS.md` is gone** (W4) — the inbox renders as a section of `BOARD.md`, written by the store at land and on demand, bodies shown only for dispositioned items; `cards inbox` is the live view. Records carry a `type` key (`intake` | `disposition`); the inbox's `source` enum (`run` · `planner` · `session` · `review` · `digest`) is its own, distinct from a card's; `declined.reason` ≤ 500; `deferred.until` is `Date | Condition`; `inbox.max_per_run` (default 10) and `inbox.max_per_actor_per_day` bound intake, overflow recorded as a count. Everything else stands. **Draft-6 (round 6 fill):** the inbox's `source` members are the inbox's allowed subset of the one `Origin` enum shared with the card (03 §2.1); `cards inbox` is `show Inbox`; intake records are a record-slot document under the one `write` (03b §3).
> **Status:** **owner-ratified 2026-08-20 (round 28)** with three rulings — the planner works with the owner on every disposition for now ("the planner should always work with the owner for now … behavior design is my contribution to this building and i've found when i'm lax we suffer"); every invocation reviews opens / principles / ARC and reports the inbox count by source to the owner ("let the owner know that it has x items from the factory in its ledger"); one inbox for session suggestions too ("yes"). Mechanics below remain [proposed] until draft-3 carries them.

# The suggestion inbox — a tenant-owned, append-only record of what the factory (and anyone else) noticed

## 1. The frame this sits in

- **The tenant is standalone; its toolkit is the only writer of its tracking root.** Whoever calls it — the owner, a contributor, the planner, the factory's lander — writes through `cards …`, a typed call against a schema. The factory is an external operator with a tool surface (the factory MCP), not a file writer. The path rule on `state.json` becomes a *caller* rule: that record is written by `cards land`, and only the factory's identity may call it.
- **Only the planner or a human writes cards**, and every card passes the gate. The builder writes code inside its `surfaces` and returns a typed report — nothing else. What it noticed on the way is a **suggestion**, not a card, not guidance, not a note on a card.
- **Zero trust both ways.** The tenant accepts a suggestion as a suggestion only — never auto-promoted, never in any hash, payload, or readiness rule. The factory keeps its own copy of what each run reported (the run record), so the tenant's inbox and the ledger can be compared; disagreement is a typed signal, as with `history`.

## 2. The record

One append-only file under the tracking root, **`suggestions.jsonl`** — one JSON object per line, tool-written only, chained exactly like `history` (`seq`, `h`; the recompute rule applies: the tool derives everything but the authored `title`/`body`, and those are bounded). Two record types share the file:

**Intake** — `{ seq, h, at, id: "s<n>", by, for?, via, source, from: { run?, card?, commit?, adapter? }, kind, title, body, refs: [...], surfaces_touched: [...], proposed_for?: <card id> }`

- `source`: `run` (the builder, carried in the run report and landed by `cards land`) · `planner` · `session` (a human or agent in the owner's session: `cards suggest`) · `review` (a review agent) · `digest`.
- `kind`, closed set: `card` (work that should exist) · `guidance` (an avoid / risk / constraint for an existing card — `proposed_for` required) · `debt` · `docs` · `test` · `risk` · `question` (non-blocking; blocking questions stay on the interrupt channel, T-C5).
- `title` ≤ 120 chars; `body` ≤ 2 KiB; `refs` must be paths (optionally `:lines`) at the run's `base_sha` — a suggestion without a ref is still accepted but renders `unsourced`. Bounds are the anti-stash rule: the builder gets a small, typed slot, not a free page.
- The builder never calls the tenant. Its suggestions are a typed section of the **run report** (T-C6 contract); the ledger validates them; `cards land` writes the intake records with `via = "land"` and `from.run` set — the factory's identity, the tenant's tool.

**Disposition** — `{ seq, h, at, id: "d<n>", on: "s<n>", by, for?, via, outcome, ... }`

- `outcome`, closed set: `accepted` → `{ as: "draft", draft_key }` (a bot draft is created by the same call: `cards accept-suggestion s12 --as draft` → `drafts/…` with `source = "suggestion"`, `promoted_from` chain intact) · `accepted` → `{ as: "guidance", card, guidance_id }` (a **proposed gated edit** to that card — it moves the build hash, so it waits for the owner's ratification like any other content change; the planner cannot ratify) · `accepted` → `{ as: "note", card }` (a `cards note` Updates block on the card, log class) · `declined` → `{ reason }` (bounded) · `deferred` → `{ until: <condition or date> }`.
- A suggestion is never edited, only dispositioned; a second disposition on the same `s<n>` supersedes the first (both stay — append-only).

**Open inbox** = intake records with no superseding `accepted`/`declined` disposition. Derived, never stored.

## 3. Who reads it, when

- **The planner, every invocation:** step one is `cards inbox` — the open suggestions, newest first, with per-source counts. The planner must disposition what it triages and may leave the rest open (the count is shown; a planner that never triages is visible). Budget: the inbox listing is titles + kinds + sources, not bodies; bodies are fetched per item. A suggestion accepted as a draft enters the sourced-drafts inbox the owner already ratified (T-A1) and then the normal gate.
- **A human, while coding:** `cards inbox` in the terminal, or **`SUGGESTIONS.md`** regenerated beside `BOARD.md` (read-only render: open items grouped by kind, each with its source, run, refs, and age; dispositioned items in a collapsed tail). The board's header carries the open count.
- **The memory tier** indexes intake and disposition records (dev-audience tier, T-B12) — "what did the factory keep noticing about this module" becomes a recall query.
- **The ledger** keeps the run-report copy. `factory audit <tenant>` compares: a suggestion in the report that never landed, or an intake record no run reported, is `suggestion-mismatch`.

## 4. What this replaces or touches

- It sits **upstream of bot drafts**: T-A1's sourced-drafts inbox stays; a draft is now one *disposition* of a suggestion rather than something a bot writes directly. Bots stop writing drafts; they suggest, and the planner (or a human) drafts. This tightens "only the planner or a human can write cards" to the letter.
- The run report contract (T-C6) gains a `suggestions[]` section with the bounds above.
- `cards land` gains the intake write; `cards suggest`, `cards inbox`, `cards accept-suggestion`, `cards decline-suggestion`, `cards defer-suggestion` join the vendored set; `SUGGESTIONS.md` joins the regenerated files.
- The card schema is untouched except `source = "suggestion"` on drafts and the `promoted_from` chain (`s<n>` → `draft_key` → `id`), so a shipped story can be traced back to the run that first noticed it.
- Efficiency: append-only JSONL is the cheapest write and the cheapest diff; the open inbox is a single pass over the file; the planner reads titles, not bodies, until it chooses.

## 5. Open (for the owner)

1. Should a suggestion's acceptance as **guidance** require the owner's ratification (as proposed — it moves the build hash) or may the planner land guidance on its own? The proposal keeps the gate: guidance is delivered to the builder, so it is content.
2. Triage obligation: must the planner disposition *every* open suggestion per invocation (strict) or the newest N with a visible remainder (proposed)?
3. Does the human/agent in the owner's session use the same `cards suggest` for things noticed while coding (proposed: yes — one inbox, sourced by `source`)?
