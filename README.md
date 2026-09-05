# isidium-factory

The factory: a card-driven, owner-gated build line for isidium projects — and the home, for v1, of
**isidium-store**, the governed store every isidium part and every third party installs.

| Part | Distribution | Import | What |
|---|---|---|---|
| the store | `isidium-store` (`packages/isidium-store`) | `isidium.store` | every governed document through one typed `write`; registry schemas; journal; signatures; the `isidium` CLI |
| the factory | `isidium-factory` (`packages/isidium-factory`) | `isidium.factory` | the line: ledger, dispatch, adapters, the lander (a store client) |

`isidium` is a PEP 420 namespace shared across parts; the CLI is `isidium` with the store's verbs at the top
level (`isidium init`, `isidium write 42 …`, `isidium ratify`) and other parts as groups.

- **Design record:** `docs/design/` (01 the transition catalog; 03 the card schema; 03a the inbox; 03b the
  governed store; 04 the config schema; 05 the agent roster; 06 the code constraints). The canonical sync record —
  the owner's ruling-by-ruling dialogue these documents cite by id (`7bg.8`, `Q11`, …) — is private; the ids are
  stable pointers into it.
- **Build plan:** `docs/build/2026-08-27-v1-build-plan.md`.
- **Conformance oracles:** `tests/conformance/` — fixtures derived from a sealed four-prototype oracle (private,
  byte-for-byte); the derivation is stated exactly in `tests/conformance/conftest.py`.

## License

AGPL-3.0-or-later — see `LICENSE`. Both distributions declare it.

## Develop

The dependencies are locked with [uv](https://docs.astral.sh/uv/): `uv.lock` pins every version by hash, and
`--locked` is an assertion rather than a resolution — it refuses a lock that no longer matches `pyproject.toml`
instead of quietly updating one. CI runs the same four commands, on 3.12 and on 3.13.

```
uv sync --locked --all-packages --all-extras
uv run python -m pytest tests -q
uv run python -m ruff check packages tests tools
uv run python -m ruff format --check packages tests tools
uv run python -m mypy packages/isidium-store/src packages/isidium-factory/src tests tools
```

To move a version: edit `pyproject.toml`, run `uv lock`, commit the lock with the change. `python tools/osv_scan.py`
asks OSV about every version in the lock, in one call. Upstream bumps arrive as pull requests (`renovate.json`).

**Python 3.12 and 3.13.** 3.12 is the floor the distributions declare and the container ships; 3.13 is tested
beside it, and both are required. Code is LF; the design docs are CRLF; `.gitattributes` preserves both.
