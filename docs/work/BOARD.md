# Board

WIP 1/1 · inbox 0

## Queue

- open questions: none
- holds on the owner: none
- closures pending review: none
- withdrawals pending: none
- failed runs: none
- blocked by any of those: none
- dispositions since the last batch signature: 0
- merged, not landed: 0

## Inbox

none

## Open

- **2** · K8 — tenant #0: the store governs the repository its own work lives in · draft · (derived)
- **3** · K9 — the store re-reads main before it writes · draft · (derived)
- **4** · L3: accept compiles the acceptance block and runs it through four runners at the owner's terminal · closed (unverified) · software-grade · (derived)
- **5** · V4a: the execution adapter seam, and the container adapter on the workstation's podman · withdrawn · software-grade · (derived)
- **6** · The rule-id sweep resolves a module constant, not only a literal · closed · software-grade · (derived)
- **7** · The fold records an abandoned run when a card with a run in flight is withdrawn or demoted · closed (unverified) · software-grade · (derived)
- **8** · The sidecar's first entry says it is synthetic where the sidecar is read · closed · software-grade · (derived)
- **9** · The open-inbox rule has one home, so the board's inbox count and its inbox list cannot disagree · closed · software-grade · (derived)
- **10** · A demotion that ends a run in flight is a signed act, so the sidecar hears it · closed (unverified) · software-grade · (derived)
- **11** · the first land is synthetic: say so where the sidecar is read · draft · (derived)
- **12** · A phase's result left on disk reaches the ledger when its run ends, so a crashed host's spend is recorded · closed · software-grade · (derived)
- **13** · A park is a run's end and a question on its card; the owner's response disposes of the question and abandons no run · closed · software-grade · (derived)
- **14** · The dispatcher's WIP cap counts the cards the store holds in flight, so a parked card holds the line · closed · software-grade · (derived)
- **15** · A card's next plan is handed the question its last run parked on · closed · software-grade · (derived)
- **16** · Every phase that ends records the billing class it drew on, so a parked or read-only run is not left unbilled · closed (unverified) · software-grade · (derived)
- **17** · Accepting a suggestion as a note on a suggestion that names no card is refused by its own rule, and nothing is written · closed · software-grade · (derived)
- **18** · Only a blocking question parks a plan; a plan's non-blocking questions ride on to the refuter and judge · closed · software-grade · (derived)
- **19** · A phase cannot run the whole test suite, a harness that dies records what it spent, and the process limit is ours · closed · software-grade · (derived)
- **20** · Close ends a run failed:gate only when the merge commit's required checks are still red after one rerun of the failed j… · closed (unverified) · software-grade · (derived)
- **21** · A carried run records the carry commit as its head, so a carry whose later phases write nothing can still be closed · closed · software-grade · (derived)
- **22** · A test tenant checkout runs no background git maintenance, so copying it never races a lock · closed · software-grade · (derived)
- **23** · A phase that ends with a mutation still held restores the pristine file before its work is committed · closed · software-grade · (derived)
- **24** · The builder checks every file it changed with ruff and mypy before it finishes · closed · software-grade · (derived)
- **25** · The reviewer is handed the run's diff, computed by the wrapper, on both passes · closed · software-grade · (derived)
- **26** · A run whose pull request is red on the gate gets one fixup phase on its own branch, invoked by the operator · closed · software-grade · (derived)
- **27** · The config schema gains a signed [watcher] table: whether the PR watcher may start a fixup, and how many a day · closed · software-grade · (derived)
- **28** · A run's actions take a lease in the ledger, so the operator and the PR watcher never act on one run at once · closed · software-grade · (derived)
- **30** · The PR watcher runs every 15 minutes from a host scheduled task, one pass at a time, logged · closed · software-grade · (derived)
- **31** · The PR watcher: one pass reads every open run's pull request and acts through the existing verbs, never merging · closed · software-grade · (derived)
- **32** · A fixup behind an aggregating required check is handed the failed jobs of that check's workflow run, not only the aggre… · closed · software-grade · (derived)
- **35** · The PR watcher never retries a refused action at the same head, so one stuck run cannot spend the day's fixup ceiling · closed · software-grade · (derived)
- **36** · The watcher's scheduled task runs on battery, from absolute paths, and says so when registering fails · closed · software-grade · (derived)
- **37** · An idle watcher pass reads the ledger and stops: no tenant context, no fetch, no forge, when no open run has a pull req… · closed · software-grade · (derived)
- **38** · The watcher's scheduled task runs its pass in a headless console, so no window opens and nothing takes focus · closed · software-grade · (derived)
- **40** · Before it closes a merged run, the PR watcher fast-forwards a clean checkout to the base, so the close sees the merge · withdrawn · software-grade · (derived)
- **41** · The watcher task's health is read from its own log: a -Status switch reports the last pass's exit, since the headless l… · ready · software-grade · (derived)
- **42** · The PR watcher lands what the store holds unlanded, and flags a store image or schema registry that is behind · withdrawn · software-grade · depends_on 40 · (derived)
- **43** · A run checks its card's committed mutations against the card's own tests before it ends, and a survivor goes to reconci… · closed (unverified) · software-grade · (derived)
- **44** · The config schema's [watcher] table gains a signed dispatch opt-in and a daily dispatch cap · withdrawn · software-grade · depends_on 42 · (derived)
- **45** · The PR watcher dispatches the next ready card when nothing is in flight, and starts its run as a separate one-shot task · withdrawn · software-grade · depends_on 42,44,41 · (derived)
- **46** · The store ingests at the event: a signed ratification and a pending merge are landed by the store itself, not by an emp… · ready · software-grade · (derived)
- **47** · The ledger records typed observations, and a launcher named in the registration starts an actor's one-shot task · ratified · blocked_by[41] · software-grade · depends_on 41 · (derived)
- **48** · The run owns its life to closed: it ships when its review gate passes, and each resume re-reads its card and takes its … · ratified · blocked_by[47] · software-grade · depends_on 47,43 · (derived)
- **49** · The PR watcher becomes a witness: it records what it sees and wakes the owning run, and acts on nothing · ratified · blocked_by[48] · software-grade · depends_on 48 · (derived)
- **50** · The witness wakes the dispatcher when the line is free; the dispatcher checks its signed cap, picks, and wakes the run · ratified · blocked_by[46, 49] · software-grade · depends_on 46,49 · (derived)
- **52** · The signing service signs a request only after the owner's Aegis code for that request, and answers only callers holdin… · closed · software-grade · (derived)
- **54** · The store signs a ratification through the remote-totp service, and the file key stays as a named fallback · closed · software-grade · depends_on 52 · (derived)
- **55** · The signing service shows each request on a phone page and takes the Aegis code there, and ships as its own container i… · closed · software-grade · depends_on 52 · (derived)
- **56** · The owner enrols the signing service's key with a binding signed twice: by the pinned key, and by the service after an … · closed · software-grade · depends_on 54 · (derived)
- **57** · A run's second mutation check holds the first one's mutations: none withdrawn, none weakened, and no kill read off a de… · ready · software-grade · (derived)
- **61** · The signing service starts from a read-only key mount, says plainly who can cancel a request, stops cleanly on its firs… · ready · software-grade · depends_on 55 · (derived)
- **62** · The store reads a merge commit's changes against its first parent only, so a merged branch cut before a governed commit… · ready · software-grade · (derived)
- **63** · The signing service's body cap and secret-file guard are proven, and every refusal either listener answers is counted b… · ratified · blocked_by[61] · software-grade · depends_on 61 · (derived)
- **65** · The build container carries the lock's test environment on Python 3.12 and 3.13, and a phase cannot install packages · closed · software-grade · (derived)
- **66** · The runner image's build proves the guard's interpreter, the hash check is told apart per environment, and the builder … · draft · (derived)
- **67** · The container runtime is a registration setting with a start-up git-version check, and the phase's identity mapping fol… · draft · (derived)
- **69** · The watcher timer, a run's transient unit and the store's quadlet are product files the tenant installs, replacing the … · draft · (derived)
- **70** · The store's mounts name only the files it reads, and each secret reaches the container's user without a host chown · draft · (derived)
- **72** · The ratify dry run refuses what the signed act refuses · draft · (derived)
- **73** · A signed card is dispatchable without a hand land · draft · (derived)
- **74** · No tracked text file holds CRLF: a rule, a CI check, and the one-time normalisation · draft · (derived)
- **75** · The signing service's remaining gaps: init pins the file key, the timeout leaves a post-signature margin, the entrypoin… · closed · software-grade · (derived)
- **76** · Enrolment hardening: the pin signature is guarded by a test and a mutation, a pin-only revoke cannot be backdated, and … · dispatched · software-grade · depends_on 56 · (derived)
- **77** · A policy chain names the service key the code gate protects, owner grants count only for it, and the realm carve-out is… · draft · depends_on 56 · (derived)
- **78** · The enrolment refusals have disclosure rows, so a caller's own bad argument is not reported as a retryable 503 · ready · software-grade · depends_on 56 · (derived)
- **79** · The design record describes cosig, the grant and revoke binding kinds, and the rule that a pin-only binding can only en… · ready · software-grade · depends_on 56 · (derived)
- **80** · The signing-service follow-up checks bite: the one-call-bound checker sees wrapped lines, the README lists the judging-… · ready · software-grade · (derived)

## Blocked

none

## Deferred

none

## Watching

none
