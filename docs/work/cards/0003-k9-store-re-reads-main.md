```toml
schema = 1
id = 3
kind = "story"
status = "draft"
source = "session"
title = "K9 — the store re-reads main before it writes"
effort = "default"
refs = ["docs/build/2026-08-27-deployment-setup-and-open-items.md"]
surfaces = ["packages/isidium-store/src/isidium/store/server/"]
priority = "P2"

[narrative]
feature = "a running store fast-forwards onto main before every governed write, so a merged pull request no longer leaves it stale"
```

## Scope

Under the gate on main every merged pull request left the store's clone behind, and its next governed write was refused until somebody restarted the container and let the journal replay. Q14 (c) ruled that the store fetch main and fast-forward its own ref before every write, and that a rejected push be answered by one bounded rebuild when no governed path moved. This card is the first write after that landed: it was written with no restart, onto a main the store had never seen, which is the whole of the demonstration.

## History

```toml
history = [
  { seq = 1, at = "2026-09-04T04:56:56Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["effort", "id", "kind", "narrative", "priority", "refs", "schema", "scope", "source", "status", "surfaces", "title"], build = "sha256:4f6a8f19dd9f6d0376be8c910df6183148df74aa626cf2327691d23c8aade290", h = "sha256:d734494b2d62181a3e58472cdf108c0535c2b34995da58b700538a10478f5211" },
]
```
