```toml
schema = 1
id = 20
kind = "story"
status = "draft"
source = "session"
title = "Close ends a run failed:gate only when the merge commit's required checks are still red after one rerun of the failed jobs"
shape = "bdd"
effort = "default"
refs = ["packages/isidium-factory/src/isidium/factory/close.py", "packages/isidium-factory/src/isidium/factory/forge.py::Forge", "packages/isidium-factory/src/isidium/factory/github.py"]
surfaces = ["packages/isidium-factory/src/isidium/factory/close.py", "packages/isidium-factory/src/isidium/factory/forge.py", "packages/isidium-factory/src/isidium/factory/github.py", "tests/factory/test_close_reruns_a_red_gate.py", "tests/factory/test_v5a.py", "tests/factory/test_close_records_left_results.py", "tools/mutations/close-rerun.toml"]
priority = "P1"

[narrative]
feature = "a flaky test on the merge commit costs a rerun of the failed jobs, not the factory's closure"

[[rules]]
id = "R1"
text = "When the merge commit's required checks are red, close asks the forge to rerun the failed jobs once and waits for them to complete, polling with a bounded backoff"

[[rules]]
id = "R2"
text = "Green after the rerun: close goes on to its later checks as it would have on green; the rerun is recorded on the run's close report (which jobs, their first and second conclusions)"

[[rules]]
id = "R3"
text = "Still red after the rerun: the run ends failed:gate as today, with both conclusions recorded"

[[rules]]
id = "R4"
text = "A rerun the forge refuses, or one that has not completed within the bound, makes close refuse (close.gate-rerun) without ending the run, naming why, so close can be run again"

[[rules]]
id = "R5"
text = "A merge commit already green, or still pending, is handled exactly as today: no rerun is asked for"

[[guidance.avoid]]
id = "A1"
option = "rerunning more than once, or rerunning green or pending checks"
because = "one rerun separates a flake from a failure; more would hide a real regression behind retries"

[[guidance.constraints]]
id = "C1"
text = "the forge protocol gains one method for rerunning a commit's failed jobs; the GitHub driver implements it through the Actions API, and every test fake implementing the protocol gains it"
because = "close reaches the forge only through the seam (V2)"

[[guidance.constraints]]
id = "C2"
text = "the wait is bounded by one named constant and polls with backoff; it never polls faster than every 15 seconds"
because = "a close that waits must not hammer the forge's API; the bound keeps a stuck rerun from holding close for ever"

[[guidance.constraints]]
id = "C3"
text = "if the forge identity lacks permission to rerun, that is R4's refusal, never failed:gate"
because = "a missing permission says nothing about the work"

[[guidance.constraints]]
id = "C4"
text = "the two test doubles close() is handed as its Reader (test_v5a.py's Forge double, test_close_records_left_results.py's NoForge) each gain the rerun method as one stub; no other line of those files changes"
because = "the owner, on r-31's question: mypy --strict runs over tests on green-bar, and a Protocol member is required whether or not it has a body"

[[guidance.constraints]]
id = "C5"
text = "tools/mutations/close-rerun.toml commits one mutation for the single-rerun bound (a second rerun allowed) and one for the wait's bound (the wait never ending), ids M1 and M2. Each kill is checked against this card's own test file only: apply the mutation in place, run tests/factory/test_close_reruns_a_red_gate.py, restore. tools/mutate.py is run with --show only and never runs a mutation inside the container"
because = "the owner, on r-31's question: AGENTS.md requires a committed spec for a limit; and card 19's r-27: mutate.py runs the whole suite per mutation, which the guard now blocks and which starved two builds"

[[acceptance.scenarios]]
id = "S1"
kind = "test-marker"
title = "a red gate is rerun once and waited for"
rule = "R1"
observable = { test = "tests/factory/test_close_reruns_a_red_gate.py::test_a_red_gate_is_rerun_once_and_waited_for" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "green after the rerun closes and records the rerun"
rule = "R2"
observable = { test = "tests/factory/test_close_reruns_a_red_gate.py::test_green_after_the_rerun_closes_and_records_it" }

[[acceptance.scenarios]]
id = "S3"
kind = "test-marker"
title = "still red after the rerun ends failed gate"
rule = "R3"
observable = { test = "tests/factory/test_close_reruns_a_red_gate.py::test_still_red_after_the_rerun_ends_failed_gate" }

[[acceptance.scenarios]]
id = "S4"
kind = "test-marker"
title = "a refused or unfinished rerun refuses without ending the run"
rule = "R4"
observable = { test = "tests/factory/test_close_reruns_a_red_gate.py::test_a_refused_or_unfinished_rerun_refuses_without_ending_the_run" }

[[acceptance.scenarios]]
id = "S5"
kind = "test-marker"
title = "green or pending is handled as today"
rule = "R5"
observable = { test = "tests/factory/test_close_reruns_a_red_gate.py::test_green_or_pending_is_handled_as_today" }
```

## Scope

Found on 2026-09-27 with r-24 (card 16): #85 merged green on its head, the merge commit's ci went red on one flaky test in a file the card did not touch (tests/store/test_verify_chain.py: copytree met a .git maintenance.lock git removed mid-copy, the class of the known test_k7a flake), and close ended the run failed:gate. A rerun of the failed jobs was green minutes later, but a failed:gate is final: card 16 could only be closed by the owner's accept --close, which reads closed (unverified).

The owner ruled (2026-09-27): close waits out one rerun.

Not in scope: fixing the copytree flakes themselves (their own card); rerunning checks on a pull request's head.

## History

```toml
history = [
  { seq = 1, at = "2026-09-28T01:03:52Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:c9657172169a4016d2f1487c76729c283b06370029a40d3acbd42c5f148122bb", h = "sha256:da526c753a7df8c3c54a55da803e0ba0584de573079dd13003a9c598e0eab606" },
  { seq = 2, at = "2026-09-29T00:43:41Z", by = "amodal1@users.noreply.github.com", act = "ratified", fields = ["status"], build = "sha256:c9657172169a4016d2f1487c76729c283b06370029a40d3acbd42c5f148122bb", h = "sha256:d23c3f58b330091380c4660eddaf1ceb6b0c6aaba3214a9a4477705de6a5001a", batch = 42 },
  { seq = 3, at = "2026-09-29T03:00:51Z", by = "amodal1@users.noreply.github.com", act = "demoted", fields = ["guidance", "status", "surfaces"], build = "sha256:1b5dfb4cc357d16aefb82f3eeec69e38eb766fcd5c0d52c34ed6dc19a76346c0", h = "sha256:ea317674dfbe9e6a9742952672151d0c31a89c0cd130bf55e450f9c3b1d807cd", sig = "ed25519:5a6c85e20ab2a6eecc5d6df4f873f9af746b98a33d923c3302a900c365984ae8:n9ScClZMl+6+B9t1TlC6akJ1ZR840O1ynpn46pSm7KwGtum2yIcZDDvRmcOBvg40bvUUisscZijb3JG6PaekAQ==" },
  { seq = 4, at = "2026-09-29T03:01:34Z", by = "amodal1@users.noreply.github.com", act = "ratified", fields = ["status"], build = "sha256:1b5dfb4cc357d16aefb82f3eeec69e38eb766fcd5c0d52c34ed6dc19a76346c0", h = "sha256:26841c1349f6a7ad3eeb71afb0ae0b4352d2bf40957cfe3150dcb864e8153b30", batch = 44 },
  { seq = 5, at = "2026-09-30T14:59:38Z", by = "amodal1@users.noreply.github.com", act = "demoted", fields = ["status"], build = "sha256:1b5dfb4cc357d16aefb82f3eeec69e38eb766fcd5c0d52c34ed6dc19a76346c0", h = "sha256:bd94ef9d5a50b2d17345895a5d96bed44f77ae2fb63a6a45009d73e423f68457" },
  { seq = 6, at = "2026-09-30T15:00:25Z", by = "amodal1@users.noreply.github.com", act = "ratified", fields = ["status"], build = "sha256:1b5dfb4cc357d16aefb82f3eeec69e38eb766fcd5c0d52c34ed6dc19a76346c0", h = "sha256:7381afbf1c7013cefdb8c6d7fcc7f273876c6e0c998cf612a5cb78193c3674cb", batch = 45 },
  { seq = 7, at = "2026-09-30T16:52:51Z", by = "amodal1@users.noreply.github.com", act = "demoted", fields = ["status"], build = "sha256:1b5dfb4cc357d16aefb82f3eeec69e38eb766fcd5c0d52c34ed6dc19a76346c0", h = "sha256:cdd709cf5d01a27e51b71a1357500e0384ae635dfa8ad01aaa00a7bcb9696f52", sig = "ed25519:5a6c85e20ab2a6eecc5d6df4f873f9af746b98a33d923c3302a900c365984ae8:1ZTsATWWpjBdp6b6tJmcfOB203Lz3MnqbESrebDJi07MsW9q9IMYfv18dWTEExXDxAjFdGHGrpduKYle+4jIAQ==" },
]
```
