```toml
schema = 1
id = 70
kind = "story"
status = "draft"
source = "session"
title = "The store's mounts name only the files it reads, and each secret reaches the container's user without a host chown"
shape = "bdd"
effort = "default"
refs = ["deploy/compose.yaml", "deploy/entrypoint.sh", "deploy/signer-entrypoint.sh", "deploy/Containerfile.store"]
surfaces = ["deploy/compose.yaml", "deploy/entrypoint.sh", "tests/factory/test_secret_mounts.py"]
priority = "P0"

[narrative]
feature = "rootless podman and Docker read the same secrets with no uid arithmetic"

[[rules]]
id = "R1"
text = "the store's tls mount holds only ca.pem, store.cert.pem, store.key.pem, probe.cert.pem and probe.key.pem; ca.key.pem and owner.key.pem are not reachable from inside"

[[rules]]
id = "R2"
text = "the store's entrypoint installs each secret it needs into a file the container's user owns with mode 0600, as the signer's entrypoint does, so no host `podman unshare chown 999` is required"

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
title = "no mount in compose.yaml reaches a CA or owner private key"
rule = "R1"
observable = { test = "tests/factory/test_secret_mounts.py::test_the_tls_mount_names_only_the_stores_files" }

[[acceptance.scenarios]]
id = "S2"
kind = "test-marker"
title = "the store entrypoint installs every key it reads with mode 0600"
rule = "R2"
observable = { test = "tests/factory/test_secret_mounts.py::test_the_entrypoint_installs_each_key_owner_only" }
```

## Scope

H6. Found live 2026-10-28 moving the store: four files needed `podman unshare chown 999` (the store key, the deploy key, the signer key, the probe key), and the tls mount also carried ca.key.pem and owner.key.pem, which the store never reads. Recorded as stopgap in the handoff; this card removes it. P0 because a private CA key sits in a container mount.

## History

```toml
history = [
  { seq = 1, at = "2026-10-29T21:06:48Z", by = "amodal1@users.noreply.github.com", act = "created", fields = ["acceptance", "effort", "guidance", "id", "kind", "narrative", "priority", "refs", "rules", "schema", "scope", "shape", "source", "status", "surfaces", "title"], build = "sha256:5d6a059b890767fe32266fd60a7b9042555deb0219a0bc3e3ea0d53e69278717", h = "sha256:03cca5b81968f0be303b529f1be23489049243838922370764526cf0e57bafc1" },
]
```
