# isidium-factory — for any agent working in this repository

This file is the one context file both harnesses read: pi reads it directly; Claude Code reads it through
`CLAUDE.md`, whose whole content is `@AGENTS.md` (its documented form). Nothing here is Claude-only or pi-only
(sync 7bdb.4). Keep it short: facts an agent needs in every session, not procedures — those are skills.

## What this repository is

Two distributions in one uv workspace, one PEP 420 namespace `isidium`:

- **the store** — `packages/isidium-store`, import `isidium.store`, CLI `isidium`. Every governed document through
  one typed `write`; registry schemas; a hash-chained journal; signatures; a pre-commit hook; an MCP tool surface.
  Every tenant installs it.
- **the factory** — `packages/isidium-factory`, import `isidium.factory`. The line (ledger, dispatch, adapters, the
  lander). A client of the store; never installed by a tenant. Mostly unbuilt today.

The design record is `docs/design/` (01 the transition catalog · 03 the card schema · 03a the inbox · 03b the
governed store · 04 the config schema · 05 the agent roster · 06 the code constraints). It cites the owner's sync
record by id (`7bg.8`, `Q11`); that record is private, the ids are stable. The build plan is
`docs/build/2026-08-27-v1-build-plan.md`; the deployment record is `deploy/README.md`.

## The one rule about writing

**`docs/work/` is the tracking root and the store is its only writer.** `docs/work/cards/*.md`,
`docs/work/config.toml` and the other governed paths are written by `isidium write`, `isidium ratify`,
`isidium suggest` and `isidium disposition` — over mTLS, journaled, committed and pushed to `main` by the store's
own identity. Never edit them by hand; the pre-commit hook refuses the commit, and a bypass that reaches `main`
is answered by a signed `repair`. This repository is **tenant #0** of its own store, and `main` is gated: every
change lands through a pull request with the checks green.

## The green bar — every change, both Pythons

```
uv sync --locked --all-packages --all-extras
uv run python -m pytest tests -q
uv run python -m ruff check packages tests tools
uv run python -m ruff format --check packages tests tools
uv run python -m mypy packages/isidium-store/src packages/isidium-factory/src tests tools
```

3.12 and 3.13 both. `docs/design/06-code-constraints.md` is in force — no default in code (C-1), typed values never
formatted strings (C-2), typed refusals naming a rule id (C-5), `mypy --strict` with no question-hiding ignores
(C-7), lazy by preference with the reason written where it is not (C-13), instrumentation in the same pass as the
code (C-11). Every security or limit assertion is mutation-checked with `python tools/mutate.py` — one mutation
per invocation, the spec committed under `tools/mutations/`.

Code is LF; `docs/` is CRLF; `.gitattributes` preserves bytes both ways. Count bytes, never trust a text-mode
round trip. The chunk plan and its findings live in the owner's record, outside this repository.

## The planner's door

The **planner** — the roster's one agent that works with the owner and writes cards — is a session model in the
owner's interactive session plus the `isidium-planner` skill, which `isidium init` and `isidium install` write into
every checkout (`.claude/skills/` and `.agents/skills/`, gitignored). Its prompt is `prompts/planner/v1.md`
(7bd.11); the skill carries a byte-identical copy. Invoke the skill to plan, author cards, triage the inbox or
prepare a sitting. The owner signs; the planner never does.

## For the planner

Where tenant #0's opens, principles and current arc are (the ceremony's first step):

- **Opens:** the queue — `isidium show queue --text` — and the owner's chunk plan (in the record, section 5,
  the open rulings; not in this repository).
- **Principles:** `docs/design/06-code-constraints.md`, and the owner's charter as the design record quotes it
  (determinism first, minimal right-sized model calls, mechanical enforcement, efficiency of construction and
  execution).
- **Current arc:** the WP4 chunk plan in the record, and its cards under `docs/work/cards/`.
