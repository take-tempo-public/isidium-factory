# Model evaluation, 2026-10: the five agents on Claude 5.5

> **Status:** measured and **ruled 2026-10-06 [owner]: "keep it as it is with the grids saved as reference"**. No
> policy change: plan-author Opus 5.5/high, refuter Sonnet 5.5/high, judge Opus 5.5/high, builder Sonnet 5.5/high,
> reviewer Opus 5.5/xhigh. The owner had weighed a Sonnet/medium judge and noted *"we need to review these when we
> have the option of non Anthropic models"*. That is where the judge's lineage question, and every slot, is reopened.
> This document is the reference for that review and for the next model release.
> **Instrument:** `tools/replay.py`. Each replay reran a recorded first-pass `job.json` outside the ledger with only
> the agent's model and effort changed. Every variant, the baseline included, ran on the current prompt
> (plan-author v2, refuter v1, judge v1, builder v6, reviewer v3) and runner image `isidium-runner:v6`
> (claude 2.1.286).
> **Cost** is Claude Code's imputed API-equivalent figure (`cost_micro`). The lane is the subscription, so the real
> constraint is the session limit, which was hit three times. Medians are per phase.

## What was run

| grid | inputs | variants | replays |
|---|---|---|---|
| gate (plan-author, refuter, judge) | 15 cards, one run each, r-14 → r-44 | 5 / 4 / 4 | 195 |
| plan quality | each plan-author variant's plans, through the **baseline** refuter and judge | 5 | 148 |
| reviewer | 4 cards (23–26) × 2 planted defects × 2 repeats | 6 | 96 |
| builder | 4 cards (23–26), fresh tree at base, the recorded approved plan | 5 | 20 |

**Planted defects:** a realistic one-line fault, committed on a scratch tree at the run's head so that it appears in
the review diff. Per card, one fault the card's own tests catch (verified red) and one they do not.
**Builder score:** the card's **merged** test files (the reference, from the recorded head) run against the
variant's tree, plus ruff check, ruff format --check and mypy on the files it changed. The variant's own tests were
not trusted.

## Results

**Plan-author.** First-round approval by the baseline refuter and judge (/15), with blocking findings raised against
the plans:

| variant | approved | blocking | $ |
|---|---|---|---|
| **Opus 5.5 / high (live)** | **11** | 0 | 1.03 |
| Opus 5.5 / medium | 7 | 1 | 0.77 |
| Sonnet 5.5 / high | 9 | 3 | 0.39 |
| Sonnet 5.5 / medium | 3 | 7 | 0.17 |
| Haiku 4.5 | 1 of 14 (1 malformed) | 11 | 0.12 |

**Refuter.** Findings summed over 15 cards, blocking / major / minor. A blocking finding forces the plan's one
revision.

| variant | blocking / major / minor | $ |
|---|---|---|
| **Sonnet 5.5 / high (live)** | 4 / 9 / 32 | 0.38 |
| Sonnet 5.5 / medium | 7 / 4 / 13 | 0.19 |
| Opus 5.5 / high | 5 / 16 / 22 | 1.10 |
| Haiku 4.5 | **11** / 8 / 3 (over-blocks) | 0.18 |

**Judge.** Agreement /15 with the baseline repeat and with the live verdict. The repeat itself agrees with live
13/15, which is the noise floor.

| variant | = repeat | = live | $ |
|---|---|---|---|
| **Opus 5.5 / high (live)** | 15 | 13 | 0.57 |
| Opus 5.5 / medium | 14 | 12 | 0.43 |
| Sonnet 5.5 / high | 12 | 12 | 0.22 |
| Haiku 4.5 | 9 | 9 (9 of 15 revise) | 0.07 |

**Reviewer.** Planted-defect recall over 16 trials. Hits were checked by hand; one false Haiku match is excluded.

| variant | recall | findings per review | $ | min |
|---|---|---|---|---|
| **Opus 5.5 / xhigh (live)** | 16/16 | 3.7 | 2.52 | 6.4 |
| Opus 5.5 / high | 14/16 | 2.8 | 1.04 | 2.7 |
| Opus 5.5 / medium | 15/16 | 2.6 | 0.65 | 1.4 |
| Sonnet 5.5 / xhigh | 16/16 | 3.1 | 1.07 | 4.8 |
| Sonnet 5.5 / high | 16/16 | 2.7 | 0.35 | 1.0 |
| Haiku 4.5 | 7/16 (1 malformed) | 1.1 | 0.26 | 3.1 |

**The reviewer beyond the planted defect.** Every finding other than the planted one was graded on repeat 1, across
8 trials:
- **Opus/xhigh against Sonnet/high (blind):** 17 against 12 findings, and **3 real majors against 0**. Opus/xhigh's
  majors: the orphaned committed mutation M6 (the defect confirmed live and fixed in #102); "repair/drain can raise"
  despite the module's "never raises"; and the dropped diff-size telemetry. Sonnet had 2 weak findings.
- **Opus/high and Opus/medium** were checked against that graded set, not blind, since the reference was known by
  then. Opus/high found the drain-can-raise and telemetry issues (one as a major) and Opus/medium found them as
  minors. Neither found M6.
- **The cross-file class (M6) across all r-44 trials:** Opus/xhigh found it 1/4 (2/6 counting the live run and the
  smoke repeat). **Every other variant found it 0/4.**

**Builder.** Merged reference tests passing, lint/format/types clean on changed files:

| variant | cards passing /4 | lint, format, types | $ |
|---|---|---|---|
| **Sonnet 5.5 / high (live)** | **4** | clean | 1.24 |
| Sonnet 5.5 / medium | 3 | one mypy | 0.67 |
| Sonnet 5.5 / low | 3 | one ruff, one mypy | 0.47 |
| Opus 5.5 / high | 4 | clean | 1.99, 2–3× slower |
| Haiku 4.5 | 2 | several | 0.70 |

## Follow-ups (owner-requested)

**Sonnet 5.5 as judge at every effort** (= live, out of 15; Opus/high's own repeat is 13): medium 13, $0.13; high 12,
$0.22; xhigh 12, $0.44; max 11, $1.82. Higher effort does not help.

**Sonnet 5.5 / xhigh and / max as reviewer, beyond the planted defect.**
- Sonnet/xhigh: 13 findings, 2 real majors (repair-can-raise; `_diff`'s git refusals untested), $1.07.
- Sonnet/max: planted 16/16, $3.11, 15.8 min, which is above Opus/xhigh on both.

**Two natural defects on r-44, neither planted.** These separate the reviewers where planted faults do not:

| reviewer | green-bar blind spot | orphaned M6 |
|---|---|---|
| Opus/xhigh (live) | 4/6 (the live run missed it) | 2/6 |
| Opus/high | 3/4 | 0/4 |
| Opus/medium | 1/4 | 0/4 |
| Sonnet/max | 4/4 | 0/4 |
| Sonnet/xhigh | 2/4 | 0/4 |
| Sonnet/high | 1/4 | 0/4 |

**The green-bar blind spot is an open defect.** This repository's required check is `green-bar`, an aggregator whose
one step echoes `suite: <result>`. `failed_jobs` reads only required checks, so a live fixup is handed
`suite: failure` and none of the lint, type or test output. The live r-44 review missed it; the evaluation found it.

## Proposed (superseded by the ruling above: no change)

| agent | live | proposal | why |
|---|---|---|---|
| plan-author | Opus 5.5 / high | **keep** | the only variant at 11/15 first-round approval; a revise round costs more than the saving |
| refuter | Sonnet 5.5 / high | **keep** | medium raises more blocking findings; Haiku over-blocks |
| judge | Opus 5.5 / high | keep, **or** Opus / medium | medium is inside the noise floor and saves about $0.14 per run: the owner's call |
| builder | Sonnet 5.5 / high | **keep** | the only Sonnet effort that passed all four cards clean |
| reviewer | Opus 5.5 / xhigh | **keep**, **or** Opus / high | in-diff faults: every Opus and Sonnet variant matches; cross-file faults: only xhigh ever found one, 2 of 6; high costs 40 % for less depth |
| all | — | **Haiku 4.5 nowhere** | it fails every slot it was tried in |

## Declared limits

- **n is small:** 15 cards for the gate, 4 for review and build. Review recall on planted faults is an upper bound,
  since a planted fault sits in the diff, and xhigh's one cross-file find in four trials is luck-heavy either way.
- **The beyond-the-plant grading is one grader (the agent that ran the evaluation) on repeat 1.** Only the Sonnet
  pairing was blind.
- **Reference-test failures may include naming differences**, not only defects. A variant can build the right
  behaviour under another name.
- **Prompt drift was removed, but card drift was not:** older cards ran against older bases.

## Reproduce

`tools/replay.py --help`. The grid drivers and scorers lived in the tenant's eval directory, which holds personal
deploy paths and is not committed; this document records their results.
