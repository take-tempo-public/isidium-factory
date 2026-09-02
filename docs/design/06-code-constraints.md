<!-- provenance: schema=1 project=isidium-factory session=ff73f7ed-85be-43d0-8bc7-55aad4b6f440 actor=amodal1 agent=anthropic/claude-fable-5 generated_at=2026-08-27 status=draft-0 -->

> **Assumes:** the design docs; that the code is Python today and **Rust later** (round 42, owner verbatim: *"we are going to move to rust and much will need to be rebuilt to fit rust's strict construction. it would be nice if we built strict and efficient now and have less time in migration"*).
> **Descends from:** the owner's direction 2026-08-27, verbatim: *"make it a guideline not to do this or we'll need to find them all as the code expands and we move to rust … i've found that you write better code when you have tight constraints … let's buckle it up now and become the role model of every other project and isidium"*.
> **Expected reader:** anyone writing code in this repository — human or agent — and the reviewer of every adversarial round.
> **Status:** **draft-0**, in force. Every rule below is **enforced by a test**, not by good intentions; a rule with no enforcement is marked as such and is a gap, not a guideline.

# Code constraints — write it now the way Rust will need it

The purpose is not tidiness. It is that the port is a **transcription, not a rewrite**, and that a deterministic reader
of the schemas sees the whole truth. Every rule names its enforcement.

## C-1 A default lives in the adopted schema version, never in the binary

Ratified as Y1 (04 §4.1). A second copy in code is invisible to anything that parses the schema documents, so a
divergence is silent. This includes the shapes a default hides in: `x.get("k", <value>)`, `x.get("k") or <value>`,
a dataclass field default, a function's default argument.

Instead: read the effective config (the tenant's file over the adopted version's defaults) and pass it in. A type
that needs policy takes policy; it does not invent it.

**Enforced:** by a sweep over **every shape this rule names** [widened 2026-08-29, K1b-ii].
`tests/unit/test_no_code_defaults.py` walks the package's syntax tree for absent-key fallbacks
(`x.get("k", v)`, `x.get("k") or v`, an annotated assignment — which is also how a dataclass field reads), for **a
function's default argument**, and for **a bare `return` of a declared default**. The keyed shapes must match the
declared key's own name as well as its value; the keyless one is judged on a distinctive value, since a `return`
has no key to match. It found ten on the day it was written.

**What the widening cost and bought.** The narrow sweep missed a live violation and shipped it green:
`client/hook.py` returned `"docs/work/"` when it could find no configured root — `config@1`'s own declared default,
and the WP3 review's S5 defect re-opened eight lines below the docstring that names S5. The hook now **refuses**
rather than guessing (`hook.unknown-root`), because a hook that cannot tell what is governed and says nothing is
the failure S5 described. The same widening found **three more violations**, all in files K1b-ii could not touch:
`client/cli.py`'s `init --root`, `server/signer.py`'s `RemoteTotp(poll_interval_ms=2000)`, and
`registry/config.py`'s `default_governed()`. They are listed in the sweep's own `PENDING` table with the reason for
each, and a second test fails when one of them is fixed — so the list is a worklist, not an allow-list. **They are
`K1c`'s** in the WP4 chunk plan.

**Does this rule reach the validator?** [asked by the third of those three; **ruled by the owner 2026-08-29**]
**Yes, and the registry is threaded to it.** The question assumed a validator with no registry in hand; that
assumption did not survive measurement. `validate_tree` and `resolve_effective` both already take a `Registry`
parameter, and the one caller that does not have one — the pre-commit hook — has `Registry.for_checkout(repo)`,
which exists precisely so a client on a newer toolkit validates against the versions the tenant adopted. So there is
no registry-less validator to carve out, and `default_governed()` is deleted rather than blessed. The alternative
of reading the shipped registry once at import was **refused**: it would pin the validator to the shipped documents
and defeat `for_checkout`, re-creating this very divergence one level up — not a duplicated value, a duplicated
registry. The carve-out alternative was refused too, on `Limits`' own terms: `Limits` carves out numbers **no schema
declares**, whereas `governed`'s manifest is declared in `config@1` itself.

## C-2 A value with alternatives is a typed value, never a formatted string

If the design says "one of these eleven, each with a payload", the code says that too: a closed set of names and a
field per payload, with **one** `render()` for the human form. Nothing matches on rendered text; nothing parses it
back. Rust gets an `enum` with variants; TypeScript gets a discriminated union; the transcription is mechanical.

Concretely, the forms to avoid: `f"integrity({reason})"` as the value; `label.startswith("closed")`;
`"failed(" + cls + ")"` parsed apart later.

**Enforced:** partly. `Label`, `Guard`, `Refusal`, `Act`, `Grant`, `Ref` and the scenario/narrative shapes are typed
today. There is no sweep that catches a new one — **a gap**, and the reviewer's standing question.

## C-3 Two models, and only two

The **raw value tree** is what the hasher sees (W10, T6): absent stays absent, `exclude_unset=True` is the one dump.
The **typed model** is validated and never hashed. Nothing else is a model — no third representation, no
convenience dict that drifts from either.

**Enforced:** `tests/unit/test_codegen.py` asserts the dump round-trips and that the build hash of the dumped tree
equals the hash of what the caller wrote.

## C-4 One source for a shape

A shape declared in a registry schema is generated, never hand-written beside it. Where the nine-member vocabulary
cannot express a shape, the shape is authored **once** (`registry/shapes.py`) and a language-neutral document is
generated **from** it, so the Rust port reads a document rather than transcribing Python.

**Enforced:** `tests/unit/test_codegen.py::test_no_drift` regenerates and byte-compares. The language-neutral shapes
document is **H-2, in progress** — until it lands, this rule is half-enforced and the port has one hand-transcription.

## C-5 Refusals are typed, and every one names a rule id

No bare `raise ValueError`, no message-only errors. A refusal carries `rule`, `path`, `detail`; the rule id is the
design's own (`write.stale`, `canon.float`, `config.enum`). Callers match on the id, never on the message.

**A rule id is always a namespace and a name** [Q2b, ruled 2026-08-29; built by K1b-iii]. The two that were not —
`validate`, with no separator, and `integrity:time`, with a colon — are now `validate.failed` and `integrity.time`,
so C-12's table has one key shape and the port encodes one invariant rather than two permanent exceptions.

**A gate that reports EVERY failure carries them as a list, not as prose** [Q7, ruled 2026-08-29; built by
K1b-iii]. `ValidationRefusal` keeps its typed verdicts in `verdicts` and renders them into `detail`; the payload
carries both, so a caller reads the failed field names off an array instead of parsing them back out of a
`"; "`-joined string — the shape C-2 forbids, at the exact place C-12 is strongest.

**One refusal, one payload constructor** [built by K1b-iii, implementing C-12's own ruling]. `Refusal.payload()` is
the single serialisation; `Response.refusal` and `McpServer._call` both call it rather than each building a dict.
That is where C-12's disclosure filter lands, and it holds at every door at once instead of one of them.

**Enforced:** every gate test asserts a rule id, not a message; `tests/unit/test_rule_ids.py` sweeps the package
and fails the build on an id that is not `<namespace>.<name>`. **A gap:** nothing forbids a new bare exception.

## C-6 No floats, ever, in anything hashed or stored

Costs are integer micro-units, durations milliseconds, weights integer per-mille. A float in a hashed input is
`canon.float`.

**Enforced:** `canon._canon_value` refuses; the config validator refuses; both are tested.

## C-7 Strict typing at the boundary and inside

`mypy --strict` passes with no ignores that hide a real question. `Any` appears where a value genuinely is a parsed
TOML tree, and nowhere else. A `# type: ignore` carries a reason.

**Enforced:** `mypy --strict` in the check gate; CI (**to build** — see the deployment record's S-7).

## C-8 One writer, one call, one commit

The efficiency rule of round 42 in code terms: a value already computed is reused, not recomputed; a loop that could
be an index is an index; a call that could be one call is one call. When a design says "one commit and one push per
call", the code does exactly that — and names the paths (the WP3 review's S3: a commit without a pathspec commits the
whole index).

**Enforced:** the scenario tests count signer calls, journal rows and commits; the WP2 review's efficiency lens is a
standing part of every adversarial round.

## C-9 Deterministic output

Sorted keys, pinned orders, no reliance on dictionary insertion order for anything serialized, no timestamps or
randomness inside a hashed value. Two runs produce identical bytes; two implementations produce identical bytes.

**Enforced:** the conformance corpus (four prototypes plus the build agree byte-for-byte); `emit` round-trips are
fixed points in the grammar tests.

## C-10 A declared limit is written down where it bites

When something is deliberately not done — a shape the vocabulary cannot say, a verb that arrives later, a check the
deployment must perform — it is stated at the site *and* in the record, with the rule id or the work-package that
carries it. "Not now" is never silent, and never "never" (round 43).

**Enforced:** by review. The two verbs the surface does not carry name themselves (`api.not-yet`).

## C-11 Every path is instrumented for OpenTelemetry, at the time it is written

**Owner, 2026-08-28, verbatim:** *"everything we are building should be logged in ways that are exposed to
opentelemetry… it should be a durable principle that we log intelligently for opentelemetry across all our systems…
this is how we prevent rather than lose time and money on fixing as best we can what could have been avoided"* — and
*"we must role model this for the other systems."* The scope is every system the owner builds; this repository is the
exemplar the others copy, so its instrumentation is the pattern, not merely enough to debug.

Instrumentation is written **in the same pass as the code**, never as a later pass. An uninstrumented path is treated
the way an untested one is. *Intelligently* means typed and semantic, not string dumps:

- a **span per phase** of a call, with the outcome as the span's status and the refusal's **rule id** as an
  attribute — the rule ids exist for this (C-5), and the journal's `subject / action / resource / context` naming is
  already the attribute vocabulary (03b §2);
- **metrics, not rows,** for anything an unauthenticated peer can trigger: a record per hostile connection is a
  denial of service through the logging;
- **logs correlated by trace context**, so a record and the call that produced it can be joined without inventing an
  id of our own.

**Two boundaries this rule does not cross.** Telemetry leaves the process; the journal does not. Governed document
content, prose, key material and journal row content are never attributes. And a telemetry identifier never enters
**hashed** content: a trace id inside a journal row's `c` would make the chain depend on whether telemetry was
configured, which C-9 forbids — it belongs beside the hashed content, where `sig` already sits.

**"No egress" is the claim, not "free"** [measured 2026-08-29]. With no SDK configured the API is a genuine no-op
and reaches **no network** — 0 outbound connection attempts through a full span-and-counter cycle, with neither the
SDK nor any exporter imported. That is the half other systems must copy. But a no-op `start_as_current_span` still
costs about **20 µs** against a 0.13 µs baseline, because attaching and detaching the context dominates
(`start_span` without the attach is ~2.6 µs). At this design's own volume — roughly three store calls per card
lifetime — the consequence is nil. It stops being nil the moment *a span per phase* meets a loop: a span per
governed path, or per journal row in reconciliation, is 20 µs × n on a machine with no SDK at all. **So: negligible
per call, not free per iteration — and never a span inside a loop over content.**

**The library/application split is part of the rule.** Instrument against the OpenTelemetry **API**; the SDK and the
exporter are the deployment's, supplied as an extra. A distribution in this namespace must not force an exporter, an
SDK, or network egress on the process that embeds it — the store's container is deliberately small (7bg.8) and its
egress is allowlisted (7be.2).

**Enforced** [built 2026-08-30 by K2b; this rule was admitted to this document on the promise of it].
`tests/store/test_telemetry.py` drives one call through the surface against the SDK's in-memory span exporter and
asserts the spans, their statuses and their attributes — a call that succeeds comes back `OK` and a refused one
`ERROR` carrying its rule id, off the same exporter in one test, because a span that merely *exists* proves nothing.
`tests/store/test_edge.py` asserts the three pre-authentication counters — refused handshake, connection ceiling,
absent peer certificate — move **with the correct reason for each class** rather than merely moving, and that none of
them writes a row. Two claims cannot be made honestly inside a process that has an SDK installed, so they run in a
child interpreter: that with none configured a full span-and-counter cycle opens **0** outbound connections and
imports neither the SDK nor an exporter, and that with `OTEL_TRACES_EXPORTER=console` the spans arrive on stderr.
`core/telemetry.py` is the only module that names the SDK, inside `configure()`, and the default when the deployment
says nothing is **no exporter at all** — upstream's default is `otlp`, and following it would make installing the
extra an egress decision taken by a wheel.

## C-12 A refusal tells the caller about itself, never about us — and says nothing at all before it is authenticated

**Owner, 2026-08-28,** ruling on what a refused caller is told versus what only the record keeps. Two rules, one
line each:

1. **Before the caller is identified, a refusal carries its rule id and nothing else.** Routing, framing, malformed
   requests, an absent certificate, a subject the registration does not name — all of these are answered with a
   status and a rule id. For most of them the rule id *is* the message (`service.transfer-encoding` says the whole
   thing), so this costs nothing; where it does cost something, the cost is paid by an unidentified peer.
2. **After the caller is identified, detail about *them and their request* flows freely; detail about *us* does
   not.** Which field failed validation, which grant they hold, that their base is stale — all of that is theirs and
   they need it. Raw exception text, the parser's own message, the signer's internals — those go to the record.

**Why the validation detail is protected rather than trimmed.** A schema refusal that names the field is what makes
"no freehand" cheap instead of bureaucratic — the same reason the schema is in the tool-call surface at all. An
agent that can self-correct does not escalate to the owner.

**Why the rest is trimmed, and it is not the usual reason.** Only a peer holding a certificate this CA issued ever
reads a refusal, so enumeration by strangers is already impossible. The real exposure is that **the callers are
language models**: detail returned to them enters a context window and from there a transcript, a card, a comment.
That is an exfiltration path with no adversary in it, and it is closed by authoring every word we return.

**Consequences at the code:**

- **We ship no words we did not write.** Today `service.arguments` returns a raw Python exception truncated to 200
  characters and `service.malformed` returns h11's message — the only two responses whose content is not ours. Both
  get an authored message; the original text goes to the record.
- **The classification lives with the status, in one table.** A rule id's HTTP status and its disclosure are two
  facts about one thing; kept in two maps they drift (C-4). One table, keyed by rule id.
  **[2026-08-29 — reopened by measurement and then RULED. The key is now: one table carrying both facts, **keyed
  by namespace, with named rule ids overriding their namespace's default**. It expresses the split below, keeps a
  new namespace a build failure rather than a silent fall-through, and in Rust a `Namespace` enum makes that
  exhaustiveness a compiler check instead of a test. Three measurements produced it:]** (i) A later handover finding directed the opposite — *key on the
  namespace* — and the two cannot both hold, because **this ruling's own table splits the `service` namespace**:
  `service.route` / `.malformed` / `.transfer-encoding` / `.body-too-large` are terse while `service.arguments` and
  `.body` are authored-then-full. (ii) **Two rule ids have no namespace at all** — `validate` (no separator) and
  `integrity:time` (a colon, not a dot). **[Closed 2026-08-29 by K1b-iii: renamed to `validate.failed` and
  `integrity.time`, and `tests/unit/test_rule_ids.py` now fails the build on a third. The table below is therefore
  written against final ids, which is why that chunk was ordered ahead of the instrumentation one.]** (iii) The count that justified the namespace key is wrong in both records:
  a sweep that follows the `_r(rs, "<rule>", …)` helper form finds **150 distinct rule ids across 34 namespaces**,
  not 91/28 or "roughly 130"/28 — the missed ones are most of the validation surface (`profile.*` 28,
  `config.*` 20, `relation.*`, `scenario.*`, `surfaces.*`, `ext-schema.*`). **And the reason the two-level shape
  won:** disclosure is aligned with the namespaces almost perfectly — every validation family is `full`, every
  `auth.*` and `signer.*` is terse, and `service` is the only namespace that splits, because this ruling split it.
  A flat rule-id table with a terse default would need roughly **120 explicit `full` rows**, making the safe
  default the rare answer and the table unauditable by eye. **Both sub-items were ruled 2026-08-29.** A new rule id
  **inherits** its namespace's disclosure, *except* in namespaces carrying a **declare-explicitly flag** — set on
  the `full` namespaces that live in server code (`write`, `show`, `governed`, `api`), where a new id could name
  something internal and is therefore a build failure until classified. The validation families inherit freely,
  because requiring a row there would make a forgotten row go **terse**, handing an agent a bare rule id it cannot
  self-correct from — failing toward the hazard this rule exists to prevent. And the two ids with no namespace are
  **normalised** (`validate` → `validate.failed`, `integrity:time` → `integrity.time`), so a rule id is always a
  namespace and a name, and the port encodes one invariant rather than two permanent exceptions.
- **The default is terse.** An unclassified rule id discloses nothing — fail-closed, so forgetting is safe.
- **The status code stays a channel and that is deliberate.** 409 means fetch a fresh base and retry; 503 means the
  signer is down and retry later. Collapsing statuses to hide coarse information would break the clients' own
  retry logic for no gain against an attacker who is already authenticated.

**One constructor, or the sweep cannot exist** [2026-08-29; **built 2026-08-30 by K2b**]. The count was **nine**,
not five: `service.route` and `service.arguments` in `server/service.py`, and `service.malformed`,
`service.headers-too-large`, `service.body-too-large`, `service.transfer-encoding`, `service.length-required`,
`service.too-many-connections` and `service.internal` in `server/http.py` — the last four arrived with K1b-ii, after
the five were counted. A sweep keyed on the refusal type was blind to every one of them, which is exactly the surface
this rule governs. All nine now build a `Refusal` and answer through `Response.refusal`, so the filter below reaches
them; `tests/unit/test_rule_ids.py` asserts the bare-payload form has **no** remaining producer, and proves the arm
still works by running it over a planted source, because an empty arm and a deleted arm look identical.

Of the two that reached a caller indirectly, one is closed and one was misfiled. `server/refs.py`'s `_check` returned
a rule id as a bare string for its caller to wrap, which made `ref.ambiguous` the one id in the package appearing in
**no** rule-id position at all — invisible to the sweep and unclassifiable by a table; it now returns the `Refusal`.
The other was recorded as "built by concatenation in `server/store.py`" and is not there: the computed ids are
`f"profile.head.{k}"` and `f"profile.{key}.shape"` in `registry/card.py`. They stay computed — the sweep reads the
**namespace** out of the f-string's literal prefix instead, which is the key this table uses anyway.

**Which surface enforces it** [2026-08-29]. A refusal reaches a caller through **three** doors, not one:
`Response.refusal` over HTTP, `McpServer._call` (which serialises `rule` / `path` / `detail` straight into a model's
context — the very exposure this rule exists to close), and the CLI. A filter written into `Response.refusal` holds
at one door. The rule is therefore: **the disclosure filter belongs on the refusal-to-payload constructor that all
three share**, not on the HTTP response.

**Enforced, and both halves are built** [K2b, 2026-08-30]. The table is `core/disclosure.py`: `NAMESPACES` (36
rows) and `RULES` (the named overrides), one row carrying the status and the disclosure together.
`tests/unit/test_rule_ids.py` sweeps the package and asserts the shape of every rule id, that **every namespace the
code can raise has a row** — the satisfiable form of "every rule id appears in the table", which a namespace-keyed
table cannot have — that every id in a declare-explicitly namespace has its own row, and that the table names
nothing the code cannot raise. `tests/store/test_telemetry.py` asserts a pre-authentication refusal is exactly
`{"rule": …}` and nothing else (an empty `detail` still says we have one), that the withheld sentence arrives in the
record, and that a validation refusal names its field **in the `verdicts` array** — never in `detail`, where the
string names the field too and a substring check would go green over the very defect it exists to catch.

Both halves land on `Refusal.payload()`, the one constructor all three doors share. Two things were found there
while building it. A terse **verdict** inside a `full` aggregate had its withheld words carried out anyway, inside
the aggregate's rendered `detail` — so `detail` is now re-rendered from the *disclosed* verdicts rather than read off
the refusal, and the case is tested by hand because no such pair exists in the code today. And `payload()` records
the refusal on the running span and the counter, which meant disclosing N verdicts through it counted one refused
call as N+1 and left the span carrying the last verdict's rule id; the filter and the recording are therefore split,
`disclosed()` from `payload()`, and a test asserts a verdict is not counted as a refusal of its own.

**One defect this ruling did not close as tabulated** [measured 2026-08-29; **closed 2026-08-29 by
K1b-ii**]. A malformed client certificate was answered `400 {"rule": "service.arguments", "detail": "error parsing
asn1 value: ParseError { kind: ShortData … }"}` — the certificate parser's own words, to a peer with no identity —
because `caller_of()` was called *inside* the block whose `except (KeyError, ValueError, TypeError)` becomes
`service.arguments`, and this ruling classifies that id **authored-then-full** on the rationale *"about their
request"*, which is false on a path with no caller. Implementing the table verbatim would have renamed the leak
instead of closing it. It is now `401 auth.malformed-certificate`, raised where the certificate is parsed, with an
authored message; the parser's text is carried on the `Credential` for the record and never returned. **The general
rule is closed too** [K2b, 2026-08-30]: `service.malformed` and `service.arguments` both answer with sentences the
store wrote, and h11's message and Python's exception go to the record instead. h11's `error_status_hint` stops there
as well — a rule id has one status and it comes off this table — which collapses its only two non-400 values: 431,
which the store's own header cap refuses ahead of h11, and 501, for a request already answered 400 when it carries
one `Transfer-Encoding` header rather than two.

## C-13 A component loads what it was asked for, not the collection it belongs to

Owner-ratified 2026-08-29. A registry, a document store, a config tree: asking one question about one member should
not pay for every member. These systems are converging onto shared machines with bounded compute and memory, so a
collection loaded eagerly is a cost paid by every process that holds one, for as long as it holds it, whether or not
it ever asks a second question. **Measured 2026-08-29:** `Registry.shipped()` costs **46 ms** — 24 ms reading and
parsing eight schema documents, 10 ms content-addressing them — to answer the pre-commit hook's single question
about `config@1`, which alone costs **8.4 ms**. The hook pays that on every commit.

**Lazy is PREFERRED — not the default, and not the law** [owner's amplitude, sharpened 2026-08-30, verbatim:
*"lazy is preferred, not default, it should be judged and if it is other than lazy, explain the thinking that led
to the eager choice being better in this case"*; and earlier, *"make it a lazy load unless the principle actually
negatively impacts the experience and that is a design question"*].

**The distinction is the rule, so read it before you use it.** A *default* is what happens when nobody thinks. A
*preference* is where you land when you do. This rule asks for the thinking; it does not ask for lazy. Two
instructions follow, and the first is the one that gets skipped:

1. **Decide it, at every site that loads a collection.** Both answers are available to you and neither is
   automatic. A lazy load nobody weighed has failed this rule exactly as much as an eager one — it just happens
   to have landed on the preferred answer.
2. **If you choose eager, write at that site the thinking that made eager better *here*.** Not which category it
   falls into — **why this case is that case**, with a measurement or a named failure mode. "It is a startup
   contract" is a label; *"deferring this moves a boot-time refusal into the middle of a write, which is strictly
   worse for the operator"* is the reasoning, and the reasoning is what a later reader needs when the situation
   has changed and they must decide whether it still holds.

Three shapes where eager has been the better answer before. They are **worked examples of reasoning, not a
checklist to tick** — citing one without saying why it applies here is the miss, not the pass:

- **A startup contract that must fail at startup.** `Registry.from_directory` refuses a directory with no documents
  (`registry.not-installed`). Deferring that check moves a boot-time refusal into the middle of a write, which is
  strictly worse for the operator. Eager.
- **When the collection is the answer.** `check_all()` and codegen want every document. A thunk per member buys
  nothing and costs a layer.
- **When the deferral lands inside a loop.** The same shape as C-11's corrected span cost: negligible per call, not
  free per iteration. One eager load beats a lazy one forced once per row.

**Enforced:** not by a sweep — whether laziness serves the experience is a design question and a sweep cannot judge
one. Enforced instead **by the shape of the exception**: an eager load of a collection carries, at its own site, the
reasoning that made eager better there, with a measurement or a named failure mode. **An eager load with no such
note is the finding**, and that is what the reviewer looks for. **The note is not paperwork — it is the evidence
that the judgment happened**, which is the only part of this rule a reader can check. This is the discipline
`Limits` already uses for its C-1 carve-out, and it is the half other systems copy: not *"always lazy"*, but
*"the exception is written down where it bites, with its reason."*

**Why the exception carries the evidence and not the rule.** *"Lazy unless it hurts"* is unenforceable as stated —
it invites every author to declare their own case the exception. Putting the burden on the carve-out keeps the rule
at the amplitude the owner gave it without letting it decay into either a prohibition or a dead letter.

**Closed** [K1d, 2026-08-30]. `registry/loader.py` is lazy: a document is read and parsed when it is asked for,
`installed` comes from the filenames and reads nothing, and the four sites that force the whole collection each
carry a note naming which shape they are — the startup contract in `from_directory`, and *the collection is the
answer* in `addresses`, `source()` and `check_all()`. **Measured 2026-08-30, before and after, on one harness:**
`Registry.shipped()` 62.3 ms → 1.1 ms; the pre-commit hook's `governed_paths` 78.0 ms → 24.6 ms, ten TOML parses
down to three, of which one is a schema document. The enforcement is what this section says it is — not a sweep,
but tests that **count parses** rather than milliseconds (`tests/unit/test_lazy_registry.py`), because a timing
assertion cannot tell a fast answer from an empty one, and each count is paired with an assertion about what came
back. Ten mutations, ten dead.

**What the change cost, and it is a rule rather than a footnote.** Keying documents by their parsed contents is
what made the old loader eager, so a ref now comes from the **filename** — and the two facts can disagree. They
are made to agree: a `*.toml` whose name is not `<name>@<version>` is refused when the directory is listed
(`registry.filename`), and a document that declares something other than the ref it is filed under is refused when
it is forced (`registry.filename-mismatch`). Both are terse and `core/disclosure.py` says why at the row: they
carry a filesystem path, and it is never the caller's to fix.

## The rule reaches code, not only data

**Owner-ratified 2026-08-30 (Q10), verbatim:** *"it applies to code too. and yes on the moving. hence my show of
default but without zealotry. it's a judgment call, but it should be a judgment call and not something that just
does or dos not happen. that means thining it through. we get better result that way anyway"* — and, on the rule's
strength, *"that was a default and not a hard rule. but i do encourage it as it reduces cpu and ram usage."*

A module graph is a collection, and the same two instructions apply to it: decide it, and if the import stays at
module scope in a program that may never use it, say at that site why. The reason the owner gave is the one to
weigh against: CPU to execute the module, and RAM to hold it resident for the process's life.
**Measured 2026-08-30, which is what raised the question:** `isidium hook` costs 5.5-7.7 s per commit on the
author's workstation and the registry it was optimised for was ~90 ms of it. `client/cli.py`'s import graph pulls
`cryptography`, `pydantic` and `typer`; `client/hook.py`'s pulls none of them. The hook was paying for the whole
store to answer a question that needs one TOML file and `git diff --cached`.

**But an import is not a document, and the difference is ruled in** (*"yes on the moving"*). For data, lazy
usually **avoids** the work: the hook never needs the other seven schema documents, so they are never parsed. For
imports it sometimes only **moves** it: `isidium write` opens a transport either way, so deferring that import
buys nothing across that command's life. The payoff is real where a process **never** needs the module, and is a
deferral where it does. Say which one you are getting, or "lazy imports" becomes a reflex that costs a layer and
returns nothing.

**Built** [K3b, 2026-08-31]. The pre-commit hook has its own door: `client/hook.py` grows a `main()` and a
`__main__` guard, and the script `init` installs runs **`python -m isidium.store.client.hook`** — no `isidium` on
PATH, no fallback arm, so there is no route by which a commit imports `client/cli.py`. `isidium hook` stays for a
human and calls the same `check()`. **The enforcement is a module set, not a clock** (`tests/store/test_walk.py`):
a child interpreter that imports the module *the installed script names* must hold none of `cryptography`,
`pydantic`, `typer` or `isidium.store.client.cli`, and the module name is read out of the script so the guard cannot
drift from the door. **Measured 2026-08-30/31, one sitting:** the two real command lines in a real checkout,
interleaved with a bare interpreter, are **1684 / 1701 ms** net for the old door against **1258 / 1122 ms** for the
new across two runs — roughly **0.4-0.6 s off every commit** — and at the import level `client.cli` is 792 ms net
against `client.hook`'s 543 ms. Seven mutations, seven dead. **What is left is the floor, and it is declared rather
than hidden:** ~1.1 s is Python's own start-up plus the OpenTelemetry API, which arrives through `core/refusal.py`
and which every path needs. Going below it means making the telemetry import lazy — which collides with C-11 and is
nobody's chunk — or the Rust port (7bh.3).

**And the rule wants the judgment, not the outcome.** *"It should be a judgment call and not something that just
does or dos not happen. that means thining it through. we get better result that way anyway."* That is the whole
of it: lazy is where this rule expects you to land, and landing there without having thought is not compliance,
it is luck. Neither half is a prohibition — the owner encourages laziness and named the reason — and the burden
of writing the reasoning sits on the eager side only because that is the half a reader can check.

---

## How a new rule gets here

A rule earns a place when an adversarial round finds the same class of defect twice, or when the owner names it. It
arrives **with its enforcement**; a rule that cannot be enforced is recorded as a gap in the deployment record's open
items, not as a guideline nobody can check.
