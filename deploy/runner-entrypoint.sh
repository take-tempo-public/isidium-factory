#!/bin/sh
# The run container: **one process**, and it is the harness. This script checks what the harness cannot check for
# itself, composes the phase's input from the job the factory mounted, and `exec`s — so the harness is PID 1 and the
# watchdog's `podman kill --signal TERM` reaches it directly (K6b).
#
# It writes no result of its own. `isidium-runner-report` (below, one python invocation) turns the harness's own
# JSON output into `/run/result.json` — the typed `PhaseResult` the adapter validates on the other side. Nothing
# here narrates: every field comes from the harness's output or from the job (T-B7 (1)).
set -eu

fail() { echo "isidium-runner: $1" >&2; exit 2; }

[ -n "${ISIDIUM_JOB:-}" ] || fail "set ISIDIUM_JOB — the typed job the factory mounted"
[ -n "${ISIDIUM_RESULT:-}" ] || fail "set ISIDIUM_RESULT — where the typed result is written"
[ -f "$ISIDIUM_JOB" ] || fail "no job at $ISIDIUM_JOB"
[ -n "${CLAUDE_CODE_OAUTH_TOKEN:-}" ] || fail "no model credential in the environment — the adapter passes it by name"
[ -f /run/settings.json ] || fail "no rendered policy at /run/settings.json — the write guard would not be installed"

PHASE="$(python3 -c 'import json,os;print(json.load(open(os.environ["ISIDIUM_JOB"]))["phase"])')"
AGENT="$(python3 -c 'import json,os;print(json.load(open(os.environ["ISIDIUM_JOB"]))["identity"]["agent"])')"
PROMPT="$ISIDIUM_PROMPTS/$AGENT/v1.md"
[ -f "$PROMPT" ] || fail "no prompt at $PROMPT — the image and the prompt version ship together"

# The prompt is the agent's, verbatim; the job is the card, its refs, its neighborhood block and its constraints,
# already assembled by V1 and hashed into the run record. The phase reads both and nothing else — there is no
# instruction composed here, because a prompt assembled at run time is a prompt no pull request reviewed.
INPUT="$(mktemp)"
{
  cat "$PROMPT"
  printf '\n\n---\n\n## The job\n\n```json\n'
  cat "$ISIDIUM_JOB"
  printf '\n```\n'
} > "$INPUT"

# `--max-turns` is the policy's budget; the wall clock is the adapter's watchdog outside, because a process cannot
# be trusted to enforce its own deadline. `--settings` carries the permission surface and the PreToolUse guard.
# Bare mode is never used: it does not read CLAUDE_CODE_OAUTH_TOKEN (the adapter-auth note, 2026-08-17), which is
# the whole billing lane this tenant runs on.
set -- --print \
  --settings /run/settings.json \
  --max-turns "${ISIDIUM_MAX_TURNS:-40}" \
  --output-format json \
  --permission-mode default

OUT="/run/harness.json"
if claude "$@" < "$INPUT" > "$OUT" 2> /run/harness.err; then
  STATUS=ok
else
  STATUS=failed
fi

exec python3 - "$PHASE" "$AGENT" "$STATUS" <<'PY'
"""The harness's output, as the typed result. Generated, never narrated (T-B7 (1)): every field is read from the
harness's own JSON or from the job, and a field neither of them carries is left at the model's default rather than
invented here."""
import json
import os
import sys

phase, agent, status = sys.argv[1], sys.argv[2], sys.argv[3]
job = json.load(open(os.environ["ISIDIUM_JOB"], encoding="utf-8"))
try:
    out = json.load(open("/run/harness.json", encoding="utf-8"))
except (OSError, ValueError):
    out = {}
usage = out.get("usage") or {}
tokens = int(usage.get("input_tokens", 0)) + int(usage.get("output_tokens", 0))
result = {
    "run_id": job["run_id"],
    "phase": phase,
    "agent": agent,
    "model": job["policy"]["agents"][agent]["model"],
    "effort": job["policy"]["agents"][agent]["effort"],
    "prompt_version": job["prompt_version"],
    "tokens": tokens,
    "cost_micro": int(round(float(out.get("total_cost_usd") or 0.0) * 1_000_000)),
    "duration_ms": int(out.get("duration_ms") or 0),
    "outcome": "ok" if status == "ok" and not out.get("is_error") else "failed:infra",
    "harness": "claude-code",
    "harness_version": os.environ.get("ISIDIUM_HARNESS_VERSION", "unknown"),
    "billing_class": "plan",
}
with open(os.environ["ISIDIUM_RESULT"], "w", encoding="utf-8") as fh:
    json.dump(result, fh, indent=2)
raise SystemExit(0 if result["outcome"] == "ok" else 1)
PY
