"""The container's own liveness check: `GET /health` over mTLS, against the store's real listener.

**A probe is not a principal** [S-4, ruled 2026-08-29]. This check presents a certificate the tenant's CA issued —
the handshake requires one, so there is no anonymous way to ask — but the registration does not name its subject,
it holds no grant, and `/health` is the only target it may reach. Do not add it to `registration.json` to make it
work; it already works, bounded by `Limits.max_per_probe` (2), which is its own small allowance rather than a share
of the global ceiling.

**It goes through the front door on purpose.** The previous check was `test -S /run/isidium/store.sock`, which after
7bg.8 tests a socket that no longer exists and would report the container permanently unhealthy — but it was the
wrong shape even before that: a socket file says a process opened a path, not that the store answers. This asks the
store, over the same TLS the callers use, with the same *strict* verification `httpx` builds by default. That means
this check fails when the certificates are wrong (S-1's `keyCertSign`, S-2's `AuthorityKeyIdentifier` and name),
which is the failure the deployment record says gives no diagnosis anywhere else — the connection opens and gives
nothing, on both sides.

**Stdlib only, and no isidium import.** `ssl` + `http.client` is what a healthcheck every 30 seconds should cost:
importing the store's client would pay ~0.7 s of `typer`, `pydantic` and `cryptography` per probe (K3/K3b measured
that import), for no capability this needs.
"""

import http.client
import json
import os
import ssl
import sys

TLS = os.environ.get("ISIDIUM_TLS_DIR", "/etc/isidium/tls")
HOST = os.environ.get("ISIDIUM_PROBE_HOST", "localhost")  # must match a name on the store's certificate (S-2)
PORT = int(os.environ.get("ISIDIUM_PORT", "8443"))


def main() -> int:
    context = ssl.create_default_context(cafile=f"{TLS}/ca.pem")
    context.load_cert_chain(f"{TLS}/probe.cert.pem", f"{TLS}/probe.key.pem")
    connection = http.client.HTTPSConnection(HOST, PORT, context=context, timeout=5)
    try:
        connection.request("GET", "/health")
        response = connection.getresponse()
        body = response.read(256)
    finally:
        connection.close()
    # **The positive discriminator, not "something came back."** A refusal, a 404 from a store that routed the
    # target somewhere else, and an empty body all reach this line; only a store that answered its own health route
    # produces `{"ok": true}`. A check whose assertion a broken store can also satisfy is not a check.
    if response.status != 200 or json.loads(body).get("ok") is not True:
        print(f"isidium: /health answered {response.status} {body!r}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
