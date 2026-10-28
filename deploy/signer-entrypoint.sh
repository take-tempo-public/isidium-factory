#!/bin/sh
# The signing service's container: **one process**, and it is the service. It serves the API on one port (mTLS, a
# named caller per client certificate) and the code-entry page on another (HTTPS, no client certificate), both from
# `python -m isidium.signer.page`, which this script `exec`s -- so the service is PID 1 and a `podman stop` reaches it.
# The shape is entrypoint.sh's (the store's), and so is the refusal: exit 2, one line, the thing that is missing.
set -eu

fail() { echo "isidium-signer: $1" >&2; exit 2; }

# The one thing the deployment must say. Every limit, address and path lives in that file and none has a default here
# or in the code (C-1); the image's layout only fixes where the file is mounted (the Containerfile's ENV).
[ -n "${ISIDIUM_SIGNER_SETTINGS:-}" ] || fail "set ISIDIUM_SIGNER_SETTINGS -- the settings file this service reads"
[ -f "$ISIDIUM_SIGNER_SETTINGS" ] || fail "no settings at $ISIDIUM_SIGNER_SETTINGS -- it names the key, the TLS files and the callers"

# The files *inside* the settings -- the signing key, the API's and the page's certificates and keys, the CA, the caller
# list -- are checked by the loader the service itself uses, before anything binds. Checking them here too would be a
# second copy of the list that drifts from the first. The TOTP secret is deliberately not among them: its absence is
# not a fault, it opens enrolment on the page (R3), and the first start of a new deployment is exactly that.
exec python3 -m isidium.signer.page --settings "$ISIDIUM_SIGNER_SETTINGS"
