#!/bin/sh
# The run container's entry. This script checks what nothing past it can check for itself, then `exec`s the phase's
# PID 1 — `python3 -m isidium.factory.harness`, which spawns the harness as a child, forwards `TERM` to it, and writes
# `/run/result.json` from the harness's own output (T-B7 (1): nothing narrates).
#
# **Why the harness is not run from here (Q-V25, 2026-09-13).** It was: this script stayed PID 1 with `claude` a
# foreground child, and PID 1 ignores a signal it installed no handler for — measured in the runner image, `running`
# four seconds after `podman kill --signal TERM`, so the watchdog stopped nothing. The same script built the harness's
# argv with no `--model` and no `--effort`, so every phase ran the harness's default model under a record naming the
# signed one. Both live in `packages/isidium-factory/src/isidium/factory/harness.py` now, where the suite can test them.
set -eu

fail() { echo "isidium-runner: $1" >&2; exit 2; }

[ -n "${ISIDIUM_JOB:-}" ] || fail "set ISIDIUM_JOB — the typed job the factory mounted"
[ -f "$ISIDIUM_JOB" ] || fail "no job at $ISIDIUM_JOB"
[ -n "${ISIDIUM_PROMPTS:-}" ] || fail "set ISIDIUM_PROMPTS — the prompts this image ships"
[ -n "${CLAUDE_CODE_OAUTH_TOKEN:-}" ] || fail "no model credential in the environment — the adapter passes it by name"
[ -f /run/settings.json ] || fail "no rendered policy at /run/settings.json — the write guard would not be installed"

exec python3 -m isidium.factory.harness
