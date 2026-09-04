#!/bin/sh
# The store's container: **one process**, and it is the store. Caddy is gone (7bg.8 — the store terminates its own
# mTLS), so there is no socket to wait for, no socket to chmod, no second PID to trap and no `wait -n`. This script
# checks what the store cannot check for itself, builds the store's clone, and `exec`s — so the store is PID 1 and a
# `podman stop` reaches it directly.
set -eu

fail() { echo "isidium: $1" >&2; exit 2; }

# ---- what the deployment must say ---------------------------------------------------------------------------------
# No default for any of these: what tenant this is, what it clones and what it tracks are decisions, and a decision
# arrived at silently is the wrong kind of quiet (the same reason `serve --host` has no default). The paths below
# them are the image's own layout and come from the Containerfile's ENV.
[ -n "${TENANT:-}" ] || fail "set TENANT — the tenant namespace this store serves (one store per tenant)"
[ -n "${ISIDIUM_ORIGIN:-}" ] || fail "set ISIDIUM_ORIGIN — the tenant repository this store clones and pushes to"
[ -n "${ISIDIUM_ROOT:-}" ] || fail "set ISIDIUM_ROOT — the tracking root this tenant adopted, e.g. docs/work/"

# `0.0.0.0` is written here rather than defaulted in the store because in a container it *is* the deployment's
# answer: the container's network namespace is the boundary and the runtime publishes the port. Written down, in the
# file an operator reads, is the difference between a decision and an accident.
HOST="${ISIDIUM_HOST:-0.0.0.0}"
PORT="${ISIDIUM_PORT:-8443}"   # the registration pins it; `serve --port` carries the same default for that reason

CA="$ISIDIUM_TLS_DIR/ca.pem"
CERT="$ISIDIUM_TLS_DIR/store.cert.pem"
KEY="$ISIDIUM_TLS_DIR/store.key.pem"

[ -f "$ISIDIUM_REGISTRATION" ] || fail "no registration at $ISIDIUM_REGISTRATION — it maps each client certificate subject to a principal and a grant (S-4)"
[ -f "$CA" ] || fail "no CA at $CA — every caller's certificate must chain to it (S-1)"
[ -f "$CERT" ] || fail "no certificate at $CERT — the store proves it is the store with it (S-2)"
[ -f "$KEY" ] || fail "no key at $KEY"
[ -z "${ISIDIUM_SIGNER:-}" ] || [ -f "$ISIDIUM_SIGNER" ] || fail "ISIDIUM_SIGNER names $ISIDIUM_SIGNER, which is not there"
mkdir -p "$ISIDIUM_STATE_DIR" || fail "$ISIDIUM_STATE_DIR is not writable — the journal and the signing material live there"

# ---- the deploy key, when the origin is reached over SSH -----------------------------------------------------------
# Whether a key is needed is not a new decision: ISIDIUM_ORIGIN already made it. An origin of the form `git@host:…`
# or `ssh://…` needs the deploy key at $ISIDIUM_SSH_DIR/store-deploy-key; any other origin (a `file://` URL, https)
# needs none and a key present is ignored — so the same image and the same compose file serve both.
#
# **Copied, not used in place.** ssh refuses a private key that anyone but its owner can read, and a bind mount
# arrives with the host's owner and mode — so the mounted file is installed into the store's own ~/.ssh at 0600 and
# ssh is pointed at that copy. The host keys are the image's pinned file, and nothing else: `StrictHostKeyChecking=yes`
# with an explicit `UserKnownHostsFile` means a host that does not match a pinned line is refused, never prompted
# for and never learned. The two failures this produces look alike on the git side — a rejected key and a rejected
# host key both end the push — so the README's diagnosis step says how to tell them apart from the ssh line each
# prints.
case "$ISIDIUM_ORIGIN" in
  git@*|ssh://*)
    DEPLOY_KEY="$ISIDIUM_SSH_DIR/store-deploy-key"
    [ -f "$DEPLOY_KEY" ] || fail "ISIDIUM_ORIGIN is an SSH origin and there is no deploy key at $DEPLOY_KEY — mount the private half there (deploy/README.md, the deploy key)"
    install -m 0600 "$DEPLOY_KEY" "$HOME/.ssh/id_ed25519" || fail "could not install the deploy key into $HOME/.ssh"
    export GIT_SSH_COMMAND="ssh -i $HOME/.ssh/id_ed25519 -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=$ISIDIUM_KNOWN_HOSTS"
    ;;
esac

# ---- the store's clone, rebuilt at every start ----------------------------------------------------------------------
# **Rebuilt, not reused.** Since K9 a running store fast-forwards its own ref onto `main` before every write, so it
# no longer goes stale between restarts — but it does **not** re-parse the documents it loaded at start, and it
# refuses rather than fast-forwards when the catch-up touches a governed path. So a bypass commit somebody pushed
# straight to the branch is still invisible to the store's *model* until it restarts, which is what `check` reads,
# and a restart is still how one comes to be seen. That sentence is only true if a restart re-reads the branch, and
# this is where it becomes true. The clone is derived: everything the store writes is pushed before it is
# acknowledged, so there is nothing in here to keep.
#
# **The cost, stated rather than discovered** (C-8, and K4's second finding): a fresh clone is cold, and a filtered
# clone holds no governed blob either, so the store's first load hydrates its governed set one object at a time —
# N round trips to the origin on every start. That is the price of a store that cannot serve a stale branch, and it
# is paid at start-up rather than on a call path. Batching those fetches is K4's recorded finding, not this file's.
#
# **`GitCli.clone`, not `git clone`.** It converts a local path source to a `file://` URL, because `--filter` is
# *ignored outright* for local path clones (S-9's second trap, measured twice) — a hand-written `git clone` here
# would silently take a full clone against a `file://`-less origin and nothing downstream would say so.
if [ -e "$ISIDIUM_REPO_DIR" ] && [ -n "$(ls -A "$ISIDIUM_REPO_DIR" 2>/dev/null)" ]; then
  # Only ever delete something that is already a bare git repository this script made. If a deployment bind-mounted
  # something here against the Containerfile's warning, refuse rather than `rm -rf` an operator's data.
  if [ -f "$ISIDIUM_REPO_DIR/HEAD" ] && [ -d "$ISIDIUM_REPO_DIR/objects" ]; then
    rm -rf "${ISIDIUM_REPO_DIR:?}/"* "${ISIDIUM_REPO_DIR:?}/".[!.]* 2>/dev/null || true
  else
    fail "$ISIDIUM_REPO_DIR holds something that is not the store's bare clone — it is the container's own writable directory and must not be a bind mount"
  fi
fi

# One python invocation: it clones and reports the footprint, because it has the object in hand and a second start-up
# interpreter to ask the same question again would be the wasteful shape. `footprint` is a `cached_property` that
# walks the object graph, so this is also the only place that walk is paid for.
python3 - <<'PY' || exit $?
import os
import sys

from isidium.store.core.refusal import Refusal
from isidium.store.server.gitrepo import GitCli

tenant, into = os.environ["TENANT"], os.environ["ISIDIUM_REPO_DIR"]
try:
    git = GitCli.clone(os.environ["ISIDIUM_ORIGIN"], into, "isidium-store", f"store@{tenant}",
                       root=os.environ["ISIDIUM_ROOT"])
except Refusal as r:
    print(f"isidium: the store could not clone {os.environ['ISIDIUM_ORIGIN']} — {r}", file=sys.stderr)
    raise SystemExit(2) from None
# S-9's declared degradation is reported, not refused: a forge without `uploadpack.allowFilter` yields `full`, whose
# footprint is the history's blobs — still no working tree and no index, so the class of defect this shape exists to
# remove stays impossible either way. It is COUNTED, never read off the config, because both clones write the same
# config (S-9's first trap).
print(f"isidium: tenant={tenant} footprint={git.footprint.value} root={os.environ['ISIDIUM_ROOT']}", file=sys.stderr)
PY

# ---- the store ------------------------------------------------------------------------------------------------------
# Eight options with no defaults, and `--host`. The previous version of this file passed two.
set -- serve \
  --tenant "$TENANT" \
  --repo "$ISIDIUM_REPO_DIR" \
  --journal "$ISIDIUM_STATE_DIR/journal.sqlite" \
  --root "$ISIDIUM_ROOT" \
  --registration "$ISIDIUM_REGISTRATION" \
  --certificate "$CERT" \
  --key "$KEY" \
  --ca "$CA" \
  --host "$HOST" \
  --port "$PORT"
[ -z "${ISIDIUM_SIGNER:-}" ] || set -- "$@" --signer "$ISIDIUM_SIGNER"

# The admission numbers (`--max-connections`, `--max-per-caller`, `--max-per-probe`) are deliberately not passed:
# `server/http.Limits` is their one home (Q4, C-1), and writing them here would be the second copy.
exec isidium "$@"
