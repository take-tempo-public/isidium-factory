<!-- provenance: schema=1 project=the-factory(working-label) session=2f342ec4-8a35-4cf5-a9d8-d11d35e5db70 actor=amodal1 agent=anthropic/claude-fable-5 generated_at=2026-08-16 status=draft-0 -->

> **Assumes:** the transition catalog's readiness (T-A4) and dispatch (T-A6) rows; sync-record 7b.4 (effort: single tier + telemetry).
> **Descends from:** owner direction 2026-08-16 — "we need a multi-tier evaluation of prioritization. if we have no P0 and 5 p1, then look at other areas, urgency, dependencies blocked etc. you can help design this based on industry standards from agile history."
> **Expected reader:** the owner; the card-schema session (this fixes which fields prioritization needs); the threshold-config schema.
> **Does not cover:** cross-tenant ordering (a dashboard concern and a held seam, T-C8); the planner's recommendation model.
> **Status:** draft-0; design **[owner-ratified 2026-08-16]** incl. `class_of_service`/`due` as tending; only default weights open. Practice names are the established ones (Kanban classes of service; SAFe WSJF / Reinertsen cost of delay; Kanban aging; MoSCoW; critical-path unblocking); one-pass web grounding 2026-08-16, not a literature review.

# Prioritization — the ready-view ordering key

## 0. Constraints this design inherits

- **Deterministic and explainable.** The ordering is a pure function of
  (cards, ledger, config, clock); every rank carries its score vector so the
  board and dashboard can show *why* (I-31: emit the measure).
- **Owner sets policy in config; the factory never invents priority.**
  Weights, class definitions, and dials live in the tenant's threshold
  config, changed only through the ratification path (7b.7).
- **Priority is tending** (7d.1): the owner may re-prioritize without
  re-ratifying. Class-of-service and due date are tending too (they
  change *when*, not *what* — owner-ratified 2026-08-16).
- **Effort is one tier for now** (7b.4), so WSJF's job-size divisor is not
  available as a card field yet; the design leaves the slot and fills it
  from telemetry later.
- **Skip is dependency-safe** (7d.5): a blocked card is not *ranked low*,
  it is *not ready* — prioritization only orders what T-A4 already admits.

## 1. What the industry has tested (the pieces we borrow)

| Practice | What it contributes | Borrowed as |
|---|---|---|
| **Kanban classes of service** — expedite · fixed-date · standard · intangible, each with a cost-of-delay profile; expedite limited to 1 in flight and allowed to bump WIP | Different *shapes* of urgency, not just levels | Tier 0 (expedite lane) and the time-criticality term |
| **Cost of delay / WSJF** (Reinertsen; SAFe: (business value + time criticality + risk-reduction/opportunity-enablement) ÷ job size) | Value-per-unit-time thinking; do the small urgent thing first | Tier 2 composite; job-size divisor reserved for when effort telemetry exists |
| **Kanban aging** — items escalate as they sit | Anti-starvation | The aging term |
| **MoSCoW / P-levels** | A coarse class the owner sets by judgment | Tier 1 (P0–P3) — kept as the owner's primary lever |
| **Critical path / unblocking** (PERT-CPM lineage) | Value of finishing what others wait on | The unblocking term (transitive dependents) |
| **Stop starting, start finishing** (Kanban WIP discipline) | Finish partially done work before opening new | The resume boost for `answered` cards; WIP cap default 1 |
| **Eisenhower** (urgent × important) | Urgency and importance are different axes | Priority class ≠ time criticality — never collapsed into one number |

## 2. The ordering key [proposed]

Evaluated only over cards T-A4 admits as `ready`. Lexicographic tiers;
within a tier, deterministic.

**Tier 0 — Expedite lane.** `class_of_service: expedite` cards first, in
priority order. Tenant dial: at most **1** expedite in flight; whether it
may exceed the WIP cap (Kanban's "bump") — default yes by one. An
expedite card carries a bounded `because` (tending, ≤ 200 chars) — no
bare urgent flags **[owner-ratified 2026-08-27 (sync 7be.3)]**
(`../research/isidium-review-2026-08-27.md` §3).

**Tier 1 — Priority class.** `P0 > P1 > P2 > P3` (owner-set; tending).
Empty classes are simply skipped — "no P0 and 5 P1" lands in Tier 2 among
the P1s.

**Tier 2 — Composite score within a class** — a weighted sum of
deterministic terms, weights in tenant config, every term emitted:

| Term | Input | Default shape |
|---|---|---|
| **time criticality** | `class_of_service` + `due` (fixed-date profile: low until near due, then steep; standard: linear from ratification; intangible: 0 until an owner-set trigger) | 0–1, from days-to-due |
| **unblocking value** | count of ready-able cards transitively `depends_on` this one, weighted by their priority class | 0–1, normalized to the batch |
| **resume boost** | card is `answered` (parked, then answered) or `complete-but-demoted` — partially done work | fixed bonus (finish before starting) |
| **aging** | days since ratified (or since last un-parked) | 0–1, saturating at a tenant horizon (e.g. 30 d) |
| **batch membership** | card belongs to the current batch's epic/milestone | fixed bonus (respect the boundary) |
| **risk / opportunity** | optional tenant tag (`risk_reduction`, `enables`) — a governance-extension field | 0 unless set |
| **job size** *(reserved)* | effort telemetry per card class, once measured | divisor, WSJF-style; absent today |

**Tier 3 — Tie-breaks.** Oldest ratification first, then card id. Always
total; never random.

*(An "area balance" dial — spreading picks across epics — was considered
and **dropped 2026-08-16**: the owner's "look at other areas" meant other
*criteria*, which is what Tier 2 is.)*

## 3. What this needs from the card schema and config

- Card (tending): `priority: P0|P1|P2|P3`, `class_of_service: expedite|
  fixed-date|standard|intangible` (default standard), `due` (fixed-date
  only). Governance-extension (optional): `risk_reduction`, `enables`.
- Derived (never stored): unblocking count, age, resume state, batch
  membership.
- Threshold config: weights per term; expedite in-flight limit and bump
  allowance; aging horizon; WIP cap (default 1).
- Ready-view entry: rank + full score vector + the config version hash it
  was computed under.

## 4. How it is tuned

The planner (interactive now, staged later) recommends weight changes as
**telemetry only**; the owner changes weights on the ratification path.
Signals to watch: starvation (max age at dispatch), expedite frequency
(should be rare — a rising rate means priorities are being set by lane
abuse), unblocking realized (did finishing X actually release Y), and
batch-cycle time. Once per-story effort telemetry has enough samples per
card class, the job-size divisor turns on and Tier 2 becomes WSJF proper.

## 5. Open

Design **owner-ratified 2026-08-16** ("looks great"); `class_of_service`
and `due` as **tending fields — owner-ratified 2026-08-16**. Remaining:
1. Default weights — **owner-ratified 2026-08-26 (sync 7bc.5, "1. next")**:
   time criticality 350 · unblocking 300 · resume 150 · aging 100 · batch 100 ·
   risk 0 (integer per-mille — the config schema's no-float rule); shipped as
   the `[prioritization]` defaults in `04-config-schema.md`; tuned from the
   section-4 telemetry by signed config edit.

Sources (one-pass grounding, 2026-08-16): [Kanban classes of service](https://www.solutioneers.co.uk/kanban-classes-of-service/) · [Kanban Zone — classes of service](https://kanbanzone.com/resources/kanban/classes-of-service/) · [Kanban Tool — classes of service](https://kanbantool.com/kanban-guide/classes-of-service) · [Cost of delay & WSJF](https://selleo.com/blog/cost-of-delay-cod-how-to-calculate-delay-cost-per-week-use-wsjf-and-decide-if-buying-time-is-worth-it) · [WSJF in SAFe portfolio Kanban](https://agileseekers.com/blog/using-wsjf-to-prioritize-epics-in-the-safe-portfolio-kanban) · [Cost-of-delay urgency profiles](https://xprocess.blogspot.com/2016/04/cost-of-delay-profiles.html) · [Work item types vs classes of service](https://pawelrola.com/work-item-types-vs-classes-of-service-in-kanban-definitions-examples-practical-tips/)
