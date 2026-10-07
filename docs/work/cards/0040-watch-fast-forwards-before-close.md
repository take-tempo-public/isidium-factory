```toml
schema = 1
id = 40
kind = "story"
status = "draft"
source = "session"
title = "Before it closes a merged run, the PR watcher fast-forwards a clean checkout to the base, so the close sees the merge"
shape = "bdd"
effort = "default"
refs = ["packages/isidium-factory/src/isidium/factory/watch.py", "packages/isidium-factory/src/isidium/factory/close.py", "packages/isidium-factory/src/isidium/factory/cli.py"]
surfaces = ["packages/isidium-factory/src/isidium/factory/watch.py", "tests/factory/test_watch_fast_forwards.py"]
priority = "P1"

[narrative]
feature = "the watcher's close works without a person pulling the checkout first"

[[rules]]
id = "R1"
text = "before a Close action, the watcher fast-forwards the checkout to the tenant's base ref as fetched (a fast-forward only: never a merge, a reset or a rebase)"

[[rules]]
id = "R2"
text = "a checkout with uncommitted changes, or one that cannot fast-forward (diverged), is not touched: the run is flagged checkout-dirty or checkout-diverged once, and the close is not attempted"

[[rules]]
id = "R3"
text = "the fast-forward happens at most once per pass, before the first Close, and never on a pass with no Close"

[[guidance.avoid]]
id = "A1"
option = "pushing, committing, or changing any branch other than the checkout's current one"
because = "the watcher never pushes or writes history (the owner's ruling, 2026-10-04); a fast-forward only moves the checkout to what the forge already holds"

[[guidance.avoid]]
id = "A2"
option = "changing close.py's own checkout check"
because = "close refusing a checkout that lacks the merge (close.checkout) is right for a human operator too; the watcher prepares the checkout instead"

[[guidance.constraints]]
id = "C1"
text = "refusals stay in existing namespaces (run.*); flags are watch.jsonl entries as today"
because = "core/disclosure.py stays untouched"

[[guidance.constraints]]
id = "C2"
text = "every file this card changes passes ruff check, ruff format --check and mypy --strict, by path"
because = "r-38 and r-39 each lost a whole run to a one-line style miss"

[[acceptance.scenarios]]
id = "S1"
kind = "test-marker"
title = "a behind checkout is fast-forwarded and the close proceeds"
rule = "R1"
observable = { test = "tests/factory/test_watch_fast_forwards.py::test_a_behind_checkout_is_fast_forwarded_before_close" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "a dirty or diverged checkout is flagged and left alone"
rule = "R2"
observable = { test = "tests/factory/test_watch_fast_forwards.py::test_a_dirty_or_diverged_checkout_is_flagged" }

[[acceptance.scenarios]]
id = "S3"
kind = "test-marker"
title = "no fast-forward on a pass without a close"
rule = "R3"
observable = { test = "tests/factory/test_watch_fast_forwards.py::test_no_fast_forward_without_a_close" }
```

## Scope

Found live 2026-10-07, the watcher's first action: r-52 (card 37, #111) merged, and the next pass's close was refused close.checkout because the checkout was 4 commits behind main and lacked the merge. Every manual close script pulled first; the watcher does not. The lease was taken and released with the refusal, as designed.

## History

```toml
history = [
  { seq = 1, at = "2026-10-07T23:39:10Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:6c247aca63254cbfbb3e6644d4f902ff8d09e2337bdf1bf91168d10fec06152b", h = "sha256:7167d1a574ae50f594b8e21b9a65a6bcbc5d50bff8d56b1a256424aff4d8f272" },
]
```
