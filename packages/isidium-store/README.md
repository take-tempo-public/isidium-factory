# isidium-store

The governed store: every governed document — cards, the suggestion inbox,
`config.toml`, wiki and recall pages — is written only through one typed
function, validated against a registry schema, journaled write-ahead,
chained, and (where the diff requires it) signed. Third parties install this
part alone: `pipx install isidium-store` → `isidium init`.

Design: `../../docs/design/03-card-schema.md`, `03b-governed-store.md`,
`04-config-schema.md`. Build plan: `../../docs/build/2026-08-27-v1-build-plan.md`.

Import: `isidium.store` (a PEP 420 namespace shared with the other isidium
parts). CLI: `isidium` — the store's ten verbs at the top level; other parts
as groups (`isidium memory …`, `isidium factory …`).
