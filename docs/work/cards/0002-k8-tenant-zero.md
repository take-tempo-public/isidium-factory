```toml
schema = 1
id = 2
kind = "story"
status = "draft"
source = "session"
title = "K8 — tenant #0: the store governs the repository its own work lives in"
effort = "default"
refs = ["docs/build/2026-08-27-deployment-setup-and-open-items.md"]
surfaces = ["deploy/", "tools/verify_chain.py"]
priority = "P2"

[narrative]
feature = "the factory's own public repository is governed by its store, and main is gated for everyone but the store"
```

## Scope

The public repository is tenant #0. Its store runs in a container with a deploy key, holds docs/work/ as the tracking root, and is the only direct writer of main; everyone else lands through a pull request with the governed-path check and the code gate required, and no one holds a standing bypass. This card is the first governed write after that gate went on, and it records the chunk that made it so (WP4, K8, 2026-09-03).

## History

```toml
history = [
  { seq = 1, at = "2026-09-03T19:37:21Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["effort", "id", "kind", "narrative", "priority", "refs", "schema", "scope", "source", "status", "surfaces", "title"], build = "sha256:738b49b58737b8702536e0c025e06190495e997624e5b3bd8fadda6dae6893ea", h = "sha256:d516d1ceb1fbe2a61bb60214823327e7ea1a6f4002dcddb84fecfc3bf34a5cc5" },
]
```
