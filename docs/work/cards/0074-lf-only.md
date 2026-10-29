```toml
schema = 1
id = 74
kind = "story"
status = "draft"
source = "session"
title = "No tracked text file holds CRLF: a rule, a CI check, and the one-time normalisation"
shape = "bdd"
effort = "default"
refs = [".gitattributes", ".github/workflows/ci.yml"]
surfaces = [".gitattributes", "tools/check_lf.py", "tests/unit/test_check_lf.py"]
priority = "P1"

[narrative]
feature = "line endings cannot differ between hosts"

[[rules]]
id = "R1"
text = "`.gitattributes` declares `* text=auto eol=lf`"

[[rules]]
id = "R2"
text = "tools/check_lf.py exits 1 and names every tracked text file holding CRLF; the suite runs it, so CI checks it with no workflow change"

[[rules]]
id = "R3"
text = "isidium-factory's 26 CRLF and 1 mixed tracked files are normalised to LF in one commit"

[[guidance.constraints]]
id = "C1"
text = "the checker reads `git ls-files` once and each file once"
because = "O(files), no per-file git call"

[[guidance.constraints]]
id = "C9"
text = "every file the card changes passes ruff check, ruff format --check and mypy --strict, by path"
because = "r-38 and r-39 each lost a whole run to a one-line style miss"

[[guidance.constraints]]
id = "C8"
text = "no scenario passes by skipping"
because = "card 61's rule"

[[acceptance.scenarios]]
id = "S1"
kind = "test-marker"
title = "the attribute rule is present"
rule = "R1"
observable = { test = "tests/unit/test_check_lf.py::test_gitattributes_declares_lf" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "the checker names a CRLF file and passes a clean tree"
rule = "R2"
observable = { test = "tests/unit/test_check_lf.py::test_the_checker_names_crlf_files" }

[[acceptance.scenarios]]
id = "S3"
kind = "test-marker"
title = "no tracked text file in this repository holds CRLF"
rule = "R3"
observable = { test = "tests/unit/test_check_lf.py::test_this_repository_holds_no_crlf" }
```

## Scope

H4. Measured 2026-10-28: the-factory 82 CRLF and 2 mixed, isidium-factory 26 CRLF and 1 mixed. Store-governed files (docs/work/cards, state) are normalised through the store, not by this card; the checker excludes them until that is done. the-factory's own normalisation is a separate commit in that repository.

## History

```toml
history = [
  { seq = 1, at = "2026-10-29T21:07:07Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:c840e64f057fd43e8608bf4c2d120d36d7018235cbd10ed066d3a6819a9433b9", h = "sha256:7f218cfb611610501d758428a9106e5823d263017204d786d700690d98d88178" },
]
```
