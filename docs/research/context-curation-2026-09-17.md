<!-- provenance: schema=1 project=the-factory(working-label) session=ec0dab74-2646-47e5-ae4a-43e4269db057 actor=amodal1 agent=anthropic/claude-opus-5 generated_at=2026-09-17 filed=2026-09-18 status=research -->

> **Assumes:** the pi assessment (`pi-harness-2026-08-26.md`), the 2026-08-26 harness ruling
> (Claude Code first, pi the target, harness-neutral by construction), T-C6's adapter
> contract as built in V4a-i, T-B3's payload as a deterministic function, T-B7's close
> report as a terminating typed tool call, C-13's lazy-by-default rule.
> **Descends from:** owner, this session: *"part of isidium's goal is to replace claude
> context management with our own"*; *"compaction doesn't just happen with the card. it
> happens mostly with turns and accumulated context from many reads, skill reads,
> unnecessary tool loads etc"*; and the design statement — *"each prompt is a dense,
> curated prompt (including the turn history) instead of default returning the entire
> history that compounds with each turn"*.
> **Source:** Anthropic's Agent SDK docs (agent loop, hooks, streaming input, overview) and
> the Claude Agent SDK subscription help-center article, read 2026-09-17; the bundled
> claude-api skill's pricing and prompt-caching references (model table cached 2026-06-24);
> pi's own coding-agent docs (extensions, packages, README) at `earendil-works/pi` HEAD;
> the Agent Plugins 1.0.0 specification and the `pi-agent-plugins` package page. No runtime
> measurement — nothing here was benchmarked.
> **Expected reader:** the owner (this is a design-posture question); whoever builds the
> context curator; whoever fills the pi adapter.
> **Does not cover:** a measured cost-per-story (the ledger's job, not a reading's); spolia's
> pipeline beyond its routing shape; the planner's own session hygiene.
> **Status:** research. Everything is **[proposed]** except the owner quotes and the quoted
> external facts.

# Context curation, and what each harness lets isidium own (2026-09-17)

## 1. Verdict

**The context-management goal does not need pi. It needs a curator, and the curator is
ours in every harness.** What differs between harnesses is only how much of the *residue*
they let us intervene in — and if the curator is built the way the owner described it,
there is almost no residue to intervene in.

Three findings, in order of how much they change:

1. **A dense curated prompt is billed at full input rate; a growing transcript is billed
   mostly at the cached rate.** Curation wins only when the packet is smaller than roughly
   **one tenth** of the history it replaces (§2). This is the constraint the design has to
   be built around, and it is the opposite of the intuition that motivates the design.
2. **Compaction is driven by in-run accumulation, not by payload size** — turns, tool
   outputs, file and skill reads, tool schemas (§3). The payload budget bounds the floor of
   a run's context, never the ceiling. An earlier claim made in this session — that a run
   needing compaction is a card that was too big — is wrong and is retracted here.
3. **Intercepting and replacing tool *results* is the highest-leverage control available,
   and it exists in both harnesses** (§4). It is where the curator should be built first,
   because it needs no ownership of the loop and it works on the subscription today.

## 2. The caching crossover — the load-bearing finding [proposed]

Quoted rates (claude-api skill's caching reference, current as of writing): cache reads
cost **~0.1× base input** (0.025× on Fable 5.1); cache writes cost **1.25× at the 5-minute
TTL, 2× at the 1-hour TTL**. Prefix order is `tools` → `system` → `messages`, and any byte
change anywhere in the prefix invalidates everything after it. A cache read refreshes the
entry's timer at no cost, so **requests sharing a prefix that start less than five minutes
apart keep the 5-minute cache warm indefinitely**; the 1-hour TTL buys nothing there and
costs double to write.

Per-turn cost, the two shapes:

- **Default (append to a transcript):** `0.1 × |history| + |new tail|`
- **Curated (assemble a fresh packet):** `|packet|` at full rate, less whatever stable head
  caches

So curation pays only when `|packet| < 0.1 × |history|`. Worked:

| Turn | History | Cached-equivalent | Packet must be under |
|---|---:|---:|---:|
| 5 | ~20k | ~2k | 2k — unlikely |
| 15 | ~80k | ~8k | 8k — marginal |
| 30 | ~200k | ~20k | 20k — comfortable |

**Consequence [proposed]: the curator should be adaptive, not absolute.** Let the cached
transcript run while it is cheap, and curate at the crossover, where a tenth of the history
exceeds the packet. The crossover is measurable per workload from `cache_read_input_tokens`
against uncached `input_tokens`; it is not a philosophical choice.

Two corollaries that lower the bar:

- **Give the packet its own cacheable head.** Invariants, tool list, schemas and standing
  rules first; volatile state last. Then even curated calls read most of their prefix at
  0.1×, and the crossover moves earlier.
- **Curation must not cost model tokens.** Digests should be **deterministic projections** —
  typed fields, counts, paths, named elisions — not model-written prose. A model-written
  summary is the exception, and under the house rule it carries its reason at the site. This
  is the same burden-of-proof C-13 puts on an eager load.

**Also retracted from earlier in this session:** context editing (`clear_tool_uses`) is not
a cost lever. It rewrites the cached conversation, and in Anthropic's own measured run it
cost more than it saved. It is a context-window tool; set its trigger high and clear in few
large batches.

## 3. Where a run's context actually goes [quoted]

Anthropic's own accounting for the Agent SDK, which is Claude Code's accounting:

| Source | When it loads | Cost shape |
|---|---|---|
| System prompt | every request | small, fixed |
| Context files (`CLAUDE.md` / `AGENTS.md`) | session start, via `setting_sources` | full content in **every** request, prompt-cached |
| Tool definitions | every request; MCP schemas deferred by default via tool search | built-in schemas re-billed per request |
| Conversation history | accumulates per turn | prompts, responses, tool **inputs**, tool **outputs** |
| Skill descriptions | session start | short summaries; full body only when invoked |

The docs name large tool outputs explicitly: a big read or a verbose command "can use
thousands of tokens in a single turn," and it stays in history for every subsequent turn.

**So the owner's correction is the right model:** accumulation is a property of what the
loop *does*, not of what the payload *was*. A tightly-scoped card can still fill a window
by reading thirty files. The payload budget (T-B3's *"a payload that does not fit is a card
that is too broad, not a prompt to be compressed"*) governs the floor; the tool surface,
the turn cap and the per-result size govern the ceiling.

Corollary worth recording: **the factory's phase decomposition is already the coarse-grained
form of context curation.** One container spawn per phase, fresh context each, only a typed
report crossing back — the same mechanism Anthropic recommends subagents for, except taken
at a process boundary with a typed contract instead of a model-written summary. The unit
that accumulates is a phase, not a story.

## 4. The control ladder — what each rung owns [proposed]

| Accumulator | Claude Code CLI | Agent SDK | pi | Own loop (Messages API) |
|---|---|---|---|---|
| Tool **output** size | — | `PostToolUse` → **`updatedToolOutput`** replaces the result before the model sees it, any tool, both SDKs | `tool_result` handler, modifies content/details/isError/usage | total |
| Tool **call** | settings hook | `PreToolUse` → `permissionDecision` (`allow`/`deny`/`ask`/`defer`) + `updatedInput` | `tool_call` → `{block, reason, terminate}`, `event.input` mutable | total |
| Tool schema bloat | settings | `allowed_tools`/`disallowed_tools`; `ToolSearch` defers MCP schemas | four tools by default; `--tools`, `--exclude-tools`, `--no-builtin-tools` | total |
| Context files / skills | implicit discovery | `setting_sources` (explicit) | project trust gates `.pi/`; `--no-extensions` | total |
| Turn growth | `--max-turns` | `max_turns`, `max_budget_usd` | `max_turns`, budgets | total |
| **Filter the message list before each model call** | — | — | **`context`** (deep copy in, filtered list out) | total |
| **Supply the compaction summary** | — | `PreCompact` (archive only); summarizer stays Anthropic's; free-form instructions read from `CLAUDE.md`; manual `/compact` | **`session_before_compact`** returns your summary + `firstKeptEntryId` | n/a |

Reading of the table [proposed]: the **largest** accumulator — tool output — is fully
controllable in both harnesses, and it is controllable without owning the loop. The two rows
only pi holds are the *residue* rows: they matter when a session accumulates anyway. Which is
exactly what the design in §5 removes.

**Build order that follows:** the digest-and-pointer interception first (works today, keeps
the subscription), phase/run boundaries for the coarse reset (already built), and pi's two
rows last — an upgrade to the design, not a prerequisite for it.

## 5. The owner's design, and what it implies [owner design, consequences proposed]

Owner, verbatim: *"each prompt is a dense, curated prompt (including the turn history)
instead of default returning the entire history that compounds with each turn"*, with
*"context curation packages the prompt and tool/memory results in typed key:value pairs in
compacted form with links to the temporary deep references that have been summarized with
key usable information and the full record available as queries"*.

Named precisely: **stateless model calls with an externally-owned context.** Not filtering a
history (pi's `context`), not summarizing an old part (compaction) — **no conversation state
in the harness at all.** The harness's job collapses to two things: execute tools, make one
typed model call.

Three consequences:

1. **It removes most of the reason to need pi's context hooks.** If nothing accumulates,
   there is nothing to filter and nothing to compact. What remains of pi's advantage for the
   line is provider breadth (local models, ~40 providers), which is a billing and capability
   argument — not a context-management one. The 2026-08-26 ruling's trigger conditions are
   untouched by this note; its *reasoning* narrows.
2. **It makes the Agent SDK viable in a way it was not.** Driven at one turn per invocation
   with its transcript discarded, the Agent SDK is a subscription-billed tool-executing
   model-caller. Paying for a loop we bypass is inelegant; it is also the only rung of the
   ladder above the CLI that keeps plan-limit billing (§8).
3. **The purest form is our own loop on the Messages API** — no fight at all, and no
   subscription. That is the far end of the ladder, and the note recommends against it now
   purely on billing (§8), not on design.

**The hard part, and it is not the context assembly.** Stateless calls drop the model's own
reasoning: thinking blocks are bound to the turn that produced them and other calls drop
them. If the packet carries facts but not *decisions*, the model re-derives them — and
output tokens run 5× input, so re-derivation is the expensive kind of waste.

## 6. The closing move — typed turn outputs [proposed]

The fix fits a pattern the record already ratified. T-B7's close report is *"a terminating
typed tool call"* whose schema **is** the report, so the run cannot end in prose. Take that
one level down: **every turn ends in a typed state-delta tool call.**

Then the prompt for turn *k+1* is a **deterministic fold over the accumulated deltas** —
authored by the model, validated by schema, assembled by a pure function with no model call
in the path. That is the same shape as the store's own `fold` over `state/history.jsonl`,
and it satisfies the charter's demand for a typed function rather than a flow.

The curator's signature, stated so both scales share it:

    curate(state, last_result) -> Packet      # pure, typed, no model call

At turn granularity it is the context curator; at phase granularity it is T-B3's payload
assembler. **Writing it once, as one function, is what makes the harness fungible.**

## 7. The legibility rule for digests [proposed]

**A digest is a lossy decision made without the model's participation.** If it drops the
thing that mattered, the model cannot know something is missing — it just proceeds with a
hole. Ordinary summarization has this defect and hides it.

The rule: **a digest's schema names what it elided** — counts, ranges, section headers,
`"3 of 47 matches shown"`, the reference to fetch. Then the absence is legible in the
context, and the follow-up query is discoverable rather than lucky.

This is the same rule as the ratified **evicted-card stubs** in the delivered context block,
applied one level down, at tool-result granularity. Recording it as one rule at two scales
rather than two conventions.

## 8. Billing — why the ladder's rungs are not freely interchangeable [quoted + proposed]

**Subscription-eligible surfaces** (Anthropic help centre, *"Use the Claude Agent SDK with
your Claude plan"*, read 2026-09-17): the **Claude Agent SDK** (Python/TypeScript),
**`claude -p`**, the **Claude Code GitHub Actions** integration, and third-party apps
authenticating *through the Agent SDK*. The page opens: *"Update June 15: We're pausing the
changes to Claude Agent SDK usage described below."* The paused change would have moved all
of those off plan limits onto a monthly credit ($20 Pro / $100 Max 5× / $200 Max 20×) at
standard API rates, no rollover.

**Not eligible:** a third-party harness holding a subscription OAuth token. Third-party
clients have been rejected server-side since early 2026 (*"This credential is only
authorized for use with Claude Code"*), and pi's own provider docs state third-party harness
usage *"draws from extra usage and is billed per token, not against Claude plan limits"*.
The Agent SDK docs add: *"Unless previously approved, Anthropic does not allow third party
developers to offer claude.ai login or rate limits for their products, including agents
built on the Claude Agent SDK."* — that governs offering claude.ai login to *our* users, not
our own subscription in our own containers, which is the `claude setup-token` path already in
the record.

**Recorded posture [proposed]: treat headless subscription use as a paused deprecation.**
Use it while it holds; keep `billing_class` (`plan` | `metered`) on every run as already
ratified; do not let the economics depend on it surviving. This is what the ratified
telemetry field was for, and it is now the field that decides the harness sequencing.

**Prices per MTok** (claude-api skill's table, cached 2026-06-24): Opus 5 $5 / $25 · Sonnet 5
$2 / $10 · Haiku 4.5 $1 / $5 · Fable 5.1 $10 / $50. Batch tier is 50% off but *"cache hits
inside a concurrent batch are best-effort"* — so **batching and caching pull against each
other**, and for a workload with a large shared prefix, cached-synchronous can beat
batched-uncached by roughly 5× on the prefix. That is a measurable fork per task class, not
a default.

## 9. Interrupt primitives, for the interactive seat [quoted]

- **Streaming input mode** is the persistent-session mode: queued messages processed
  sequentially *"with ability to interrupt"*, surfaced permission requests, mid-session
  control methods. Python `ClaudeSDKClient` (`query` / `receive_response`); TypeScript takes
  an async generator as `prompt`. **Single-message mode explicitly does not support
  real-time interruption or dynamic queueing.**
- **`PreToolUse` → `permissionDecision: "defer"` ends the query so it can be resumed later**
  — a first-class stop-at-a-tool-boundary primitive, and the same shape as T-C5's
  end-and-resume interrupt. Note `updatedInput` is dropped when deferring.
- **`canUseTool`** in `default` permission mode for synchronous per-call approval; no
  callback means deny.
- `session_store` / `sessionStore` mirrors transcripts to our own backend so another host
  can resume — the seam for stateless containers.

## 10. Effect on posture

**None on shape.** The execution seam, the guard, the renderer and the container adapter as
built in V4a-i are unaffected; the payload assembler is unaffected. What this note adds:

- **The curator is one typed function at two scales** (§6) — a design item with a home
  (T-B3's assembler is its coarse instance), not a new subsystem.
- **The digest legibility rule** (§7) — one rule at two scales, extending the ratified
  evicted-card stubs.
- **The caching crossover as a standing constraint** (§2) — a curated packet must beat a
  tenth of the history it replaces, measured from usage, not assumed.
- **The pi argument narrows** (§5, consequence 1): under the owner's stateless design, pi's
  remaining advantage for the line is provider breadth, not context control. The ruling
  stands; its reasoning changes, and the sequencing point still marked *awaiting owner* now
  has a cheaper answer — the container adapter can carry a first-party image and a pi image
  behind one contract, because the image, not the seam, names the harness.
- **Two rows of the ladder remain pi-only** (§4) and are the one capability wrapper code
  cannot buy back: filtering the message list before a call, and authoring the compaction
  summary. They matter most in the planner's seat, which is also the seat most expensive to
  move to pi. That asymmetry is recorded, not resolved.

## 11. Open, with a home

1. **Does a cache read count against subscription usage at the discounted rate or at full
   input cost?** Undocumented as far as this reading found. It decides whether prefix
   stability buys *window* as well as dollars. Answerable by the ledger: run one card twice.
2. **Where is the crossover on tenant #0's real runs?** `cache_read_input_tokens` against
   uncached input, per phase. The ledger already carries `tokens` and `cost_micro`.
3. **Can `PostToolUse` → `updatedToolOutput` carry a store reference that the model can then
   resolve through a `recall` tool in the same turn?** Assumed yes; unverified.
4. **Agent Plugins 1.0.0** (published 2026-08-06; root `plugin.json` + `skills/*/SKILL.md` +
   `mcp.json`) standardizes packaging only. MCP is optional for conformance, there is no
   portable credential mechanism (`env` and `headers` are declared *visible package data*),
   and hooks/commands/subagents/settings/sandboxing are all out of scope. pi supports it only
   through a community extension (`pi-agent-plugins` 0.1.8, requiring `pi-mcp-adapter`);
   Claude Code keeps `.claude-plugin/plugin.json` and does not mention the standard. **The
   portable intersection is exactly `skills/*/SKILL.md`, which the planner skill already
   is.** Watch; do not depend. Revisit when a second consumer exists.

## 12. Sources read

- Anthropic, Agent SDK docs: overview, agent loop, hooks (full event list and return
  shapes), streaming input vs single message — read 2026-09-17.
- Anthropic help centre, *"Use the Claude Agent SDK with your Claude plan"* — read
  2026-09-17 (carries the June 15 pause notice).
- The bundled `claude-api` skill: model/pricing table (cached 2026-06-24), prompt-caching
  reference (rates, TTL, prefix order, verification), cost-optimization reference (lever
  order, batch/cache interaction, context-editing finding).
- pi: coding-agent README, `docs/extensions.md` (event list, `registerTool`, compaction and
  context handlers), `docs/packages.md`, telemetry README — `earendil-works/pi`.
- Agent Plugins 1.0.0 specification; the `pi-agent-plugins` package page; Claude Code's
  `plugins/README.md`.
- Secondary, for the billing timeline only: The New Stack on the June 15 pause; VentureBeat
  on the reinstatement and its credit caps.
