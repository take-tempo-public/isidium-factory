---
name: isidium-planner
description: The planner's seat in an isidium tenant — author and tend cards, triage the suggestion inbox, run the morning review and prepare a sitting for the owner's signature, all through the governed store's typed surface. Use when the owner wants to plan work, write or edit cards, disposition suggestions, or ratify; and whenever a task would touch cards/, config.toml, suggestions.jsonl or BOARD.md under the tracking root, which are written only through the store.
license: AGPL-3.0-or-later
metadata:
  isidium-store: "0.1.0"
  planner-prompt: "v1"
---

# isidium-planner — the card-authoring skill

**Read [references/planner-v1.md](references/planner-v1.md) first**: who the planner is, the seven-step ceremony,
what the planner never does. This file is the *how*: the surface, the file shapes, and how to read what the store
answers. Nothing here restates a schema — the store serves them, and the tool schemas are generated from them.

## Setup, once

- **Claude Code** — register the store's tool surface at user scope. The server finds the checkout's
  `.isidium/client.toml` from the working directory, so one registration serves every tenant on this machine:

  ```
  claude mcp add --scope user isidium-store -- <python> -m isidium.store.client.cli mcp
  ```

  `<python>` is the interpreter `isidium-store` is installed in — the one `isidium init` ran under; the installed
  hook (`.git/hooks/pre-commit`) names it.
- **pi** — its core has no MCP client: use the `isidium` CLI through the shell tool, from the checkout. Same verbs,
  same JSON.
- **Either** — the checkout must have run `isidium init` (that is what installed this skill). If the pre-commit hook
  refuses `hook.registry-behind`, run `isidium install` here: the toolkit moved, and the checkout's registry, hook
  and this skill are refreshed from it.

## The surface — six tools, one typed read and one typed write

`tools/list` carries the exact input schema of each; `write` and `ratify` carry the card head's schema, so a
document is constrained to the form at the moment it is written. The CLI form of each is beside it.

| tool | CLI | what it does |
|---|---|---|
| `show` — `target` ∈ `card` (with `id`) · `board` · `queue` · `inbox` · `schema` (with `name`, e.g. `card@1`) | `isidium show card 7` · `isidium show queue --text` · `isidium show schema --name card@1` | the one typed read, unjournaled. A card answers `head`, its sections, `history`, `cas` (`{seq, h}` — the `base` your next edit passes) and its projected label; the queue answers its fields beside its `markdown`; the board answers `markdown` |
| `write` — `new_slug` + `document`, or `card` + `document` + `base`, or `card` + `set` | `isidium write --new <slug> --document card.json` · `isidium write 7 --document card.json` · `isidium write 7 --set priority=P1` | the one writer: validate, compare-and-swap on the history head, derive the act from the diff, sign if the predicate says so, journal, write, commit, push |
| `ratify` — `ids` and/or `writes`; `dry_run` (default true) | `isidium ratify --writes sitting.json` · `isidium ratify 7 8` · `… --sign` | the sitting: a batch of typed writes under ONE signature. Dry run by default |
| `check` — `id` | `isidium check 7` | the store's integrity verdict: chain, recompute, signatures, journal reconciliation. Exit 1 means integrity, never advice |
| `suggest` — `kind`, `title`, `body`, `refs`, `proposed_for` | `isidium suggest risk "title" "body" --ref src/x.py:10-20 --for 7` | hand something noticed back to the tenant: never a card, never guidance, until the owner says so |
| `disposition` — `suggestion` (`s<n>`), `outcome`, `as`, `slug`, `reason`, `until` | `isidium disposition s12 --outcome accepted --as card --slug from-suggestion` | one suggestion's disposition — with the owner, every time |

The tenant's own policy — the allowed shapes and their default, the effort tiers, the surfaces deny set, the payload
budget — is `config.toml` at the tracking root (`docs/work/config.toml` unless the tenant chose another root;
`.isidium/client.toml` says which). A key that is absent takes the adopted schema version's default, and
`show schema config@<n>` carries every default. Read the file; do not remember it.

## A card's document

`write`'s `document` is `{head, scope, updates?}`: `head` is the card's TOML head as a JSON object; `scope` is the
`## Scope` section's text — **the owner's words, verbatim**; `updates` is an optional list of `{title, body}` blocks
the store stamps and appends. The store renders the file, computes the hashes and writes the `## History` footer.
You never write a footer.

A new card, as the store accepts it — the head's required keys are `schema`, `id`, `status`, `source` and `title`;
`id` is `0` and the store allocates it:

```json
{
  "head": {
    "schema": 1, "id": 0, "kind": "story", "status": "draft", "source": "planner",
    "title": "…", "shape": "bdd", "effort": "default", "priority": "P2",
    "narrative": {"feature": "…"},
    "refs": ["src/thing.py::Twice", "docs/spec.md#the-rule", "src/other.py:10-40", "README.md"],
    "surfaces": ["src/", "tests/"],
    "questions": [], "depends_on": []
  },
  "scope": "…"
}
```

- **`source`** — `planner` for a card you authored at the sitting; `session` for one the owner wrote themselves;
  `suggestion` is set by `disposition` when a suggestion becomes a card.
- **`shape`** — one of the tenant's `shapes.allowed`: `bdd` (a `narrative.feature` and an `acceptance` block of
  scenarios in the house dialect), `task`, `spike`; `ears` needs `rules`. `shape`, `surfaces` and `acceptance` are
  required once a story is `ratified`; a `draft` may lack them. The dialects are in the schema: `show schema card@1`.
- **`refs`** — four forms, each pre-flighted against the working tree *before* the call, at the terminal and at the
  MCP door alike: a whole file `path`; a line range `path:10-40`; a heading anchor `path#heading-slug`; a symbol
  `path::name`. A locus that does not land is refused `validate.failed` with a `ref.*` verdict per ref, and the
  store is never called.
- **`surfaces`** — where the builder may write: outside the tracking root and the tenant's deny set.
- **`questions[]`** — what you could not source. A card is never ready while any remain; a question leaves the
  list only by being answered.
- **`guidance`** — avoid / risk / constraint entries, each with an id. What is not handed to the builder is ignored.

**An edit** is `card` + `document` (the whole document as you want it) + `base` (the `cas` from `show card`). The
store derives the act from the diff and refuses `write.stale` when `base` is not the head — re-read the card. A
tending gesture alone is `set`: `key=value`; `key=` clears; `updates+=title|body` appends a block.

## The sitting

`ratify`'s `writes` is a list of `{new_slug | card, document, base?, ref?}` — the same document shape as `write`,
validated identically. **A `new_slug` in a sitting is a card born `ratified`**: its head says `status = "ratified"`
and carries what a ratified story needs. A draft creation is `write`'s door; in a sitting it answers
`ratify.not-a-signed-act` with the act (`created`) as its detail, because an unsigned write is not the sitting's to
make. `ids` are cards already in the checkout, ratified as they stand. The answer:

```json
{
  "dry_run": true,
  "verdicts": {
    "7": [],
    "8": [{"rule": "validate.failed", "path": "", "detail": "…",
           "verdicts": [{"rule": "ref.unresolved", "path": "refs", "detail": "src/x.py::gone"}]}]
  },
  "display": [[7, "ratified", "sha256:…", ["…"]], [8, "created", "sha256:…", []]],
  "ready": {"7": true, "8": true}
}
```

Read `verdicts` by `rule`. An empty list is a card the store would sign. A `validate.failed` carries its own
`verdicts`, one record per failed field: fix each and run the dry run again. Verdicts are deduplicated by the whole
record, so two bad refs are two records. **`ready` is not the verdicts' summary**: it is the readiness projection —
`true` when the card has no open `questions` and no `hold`, whatever the verdicts say (card 8 above is "ready" and
would still be refused). Read `verdicts` for whether the store would sign; `ready` for whether the factory would
dispatch. `display` is what the signer sees — card · act · build hash · what changed since the last signed entry.
Present it; the owner signs with `--sign` (`dry_run` false) under their own credential.

## Reading what the store answers

- **A refusal** is `{rule, path, detail}` — at the MCP door a tool result with `isError` and the same object in
  `structuredContent`; at the terminal one line, `rule @ path: detail`, exit 2. `validate.failed` carries
  `verdicts`, a list of the same records. Act on `rule`.
- **A write's result** carries `path`, `entry` (the history entry the store appended), `head` (`{seq, h}`),
  `journal_seq`, `commit`, `id` for a creation — and **`landed`**: `false` means the row is durable and the push
  did not reach `main` in this call; the next push carries it. Say so; read `main` after it lands.
- **`check`** is integrity, not advice: `integrity` names what is wrong with the chain, and a non-empty answer is
  exit 1.

## Ids you will meet

`write.stale` (your `base` is behind — re-read the card) · `write.no-change` · `validate.failed` (with `verdicts`)
· `ref.grammar` and `ref.unresolved` (a ref that does not parse, or does not land) · `ratify.not-a-signed-act` and
`ratify.invalid` · `hook.registry-behind` (run `isidium install`) · `hook.toolkit-behind` (upgrade `isidium-store`,
then `isidium install`) · `client.not-configured` (run `isidium init`).
