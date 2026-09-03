# Standing a tenant's store up

One store container per tenant (03b §2, ruled 7ba.6). The same files run on the workstation's WSL2 today and on
agent-station when its base is built — nothing here is workstation-specific.

**Every command below was run, in this order, on 2026-09-01** (podman 5.8.3, rootless, on a WSL2 machine;
podman-compose 1.6.0 as the compose provider). Nothing here is assumed. Where something is *not* verified, it says
so, at the end.

## What is in the container

| Process | What it does |
|---|---|
| **`isidium serve`** | the whole of it: it terminates its own mTLS on 8443, and holds the tenant's partial bare clone, the journal, the id counter and the write bit |

**That is the entire table, and it used to have two rows.** Caddy is gone (ruled 7bg.8). No ASGI server hands an
application the client certificate — neither uvicorn nor hypercorn 0.18 implements the ASGI TLS extension, both
verified by reading their source — so the store stopped asking one to and answers the connection itself. With the
proxy went the Unix socket, the forwarded `X-Verified-Client-Cert` header, the trusted hop, the second PID and the
socket permissions that used to be the boundary between them. The container runs one process and the entrypoint
`exec`s it, so `podman stop` reaches the store directly.

**The store's clone is bare, filtered, and has no working tree** (K4). It holds the commit graph and the trees;
governed blob content is fetched from the origin on demand, and a read outside the tracking root is refused before
git runs. `git clone <remote> tenant` — what an earlier version of this file told you to do — makes a working-tree
clone and is wrong now, not merely stale.

## What you provide

| Path | What |
|---|---|
| `tls/ca.pem` | the CA the registration pins — it issues every client certificate |
| `tls/store.cert.pem`, `tls/store.key.pem` | the store's own certificate, issued by that CA |
| `tls/probe.cert.pem`, `tls/probe.key.pem` | the healthcheck's certificate — CA-issued, and **not** in the registration |
| `registration.json` | `{"<client certificate subject>": ["<principal>", "<grant>"]}` |
| `signer.key.pem` | the store's own Ed25519 key: the software-grade waiver path, and what signs the policy chain |
| `.env` → `ISIDIUM_ORIGIN` | the tenant repository the store clones and pushes to |
| `ssh/store-deploy-key` | the store's deploy key, private half — only when `ISIDIUM_ORIGIN` is an SSH origin (see *The deploy key*) |

`.gitignore` covers every one of them. They are private material and this is a tracked repository.

### There is no `tenant/` directory any more, and that is the change

The store's clone is **derived, not authored**: the entrypoint rebuilds it from `ISIDIUM_ORIGIN` at every start,
inside the container's own writable layer, and nothing bind-mounts it.

That is what makes a restart the way a bypass commit becomes visible. A running store never re-reads `main` — it
sees the commits it wrote and no others — so a commit somebody pushed straight past it, which is precisely what
`check` exists to detect, stays invisible until it restarts. **Verified 2026-09-01:** with the store up, a commit
pushed directly to the origin left the store's clone at `32217bd`; after `podman restart` it was at `6b6f3ba`, the
planted commit. A persistent clone would have gone on serving whatever branch it last saw.

**The cost, stated rather than discovered:** a fresh clone is cold, and a filtered clone holds no governed blob
either, so the first load hydrates the governed set one object at a time — N round trips to the origin at every
start. It is paid at start-up rather than on a call path. Batching those fetches is a recorded finding against
`store.py`, not something this file can fix.

The journal and the id counter are **not** derived, and they live in a named volume (`isidium-state-<tenant>`) that
survives restarts — verified: one journal row before the restart above, one after. A named volume rather than a
bind mount because the container runs as an unprivileged user of its own, and a host directory arrives owned by
whoever made it, which is a first-start permission failure with no diagnosis in it.
`podman volume inspect isidium-state-sartor` finds it.

## Issuing the certificates

A small CA per tenant is enough until agent-station's realm exists; the realm replaces this file, not the shape.

**The extensions are not decoration.** The strictness is the *client's*: `ssl.create_default_context()` sets
`VERIFY_X509_STRICT`, which is what `httpx` builds, so these requirements land on the CA and on the store's own
certificate for the caller's benefit. Get any of them wrong and the symptom is the same and says nothing — the
connection opens and gives nothing back, and the store's handler is never invoked.

(On Git Bash for Windows, prefix each `openssl` with `MSYS_NO_PATHCONV=1`, or the `/CN=…` subject is rewritten into
a filesystem path before openssl sees it.)

```sh
cd deploy && mkdir -p tls && cd tls

# S-1 — the CA. `keyCertSign` and a SubjectKeyIdentifier: without either, every caller refuses the store's chain
# and never reaches it.
openssl req -x509 -newkey ed25519 -days 3650 -nodes -keyout ca.key.pem -out ca.pem \
  -subj "/CN=isidium-store CA (sartor)" \
  -addext "basicConstraints=critical,CA:TRUE" \
  -addext "keyUsage=critical,keyCertSign,cRLSign" \
  -addext "subjectKeyIdentifier=hash"

# S-2 — the store's own certificate. An AuthorityKeyIdentifier; a name matching the address callers dial (a
# SubjectAltName, or the Common Name when there is no SAN, because OpenSSL falls back to it); and, if it carries an
# Extended Key Usage at all, that EKU must include serverAuth. KeyUsage is not required on it.
printf '%s\n' \
  'subjectKeyIdentifier=hash' \
  'authorityKeyIdentifier=keyid,issuer' \
  'extendedKeyUsage=serverAuth' \
  'subjectAltName=DNS:store.sartor.internal,DNS:localhost,IP:127.0.0.1' > store.ext
openssl req -newkey ed25519 -nodes -keyout store.key.pem -out store.csr -subj "/CN=store.sartor.internal"
openssl x509 -req -in store.csr -CA ca.pem -CAkey ca.key.pem -CAcreateserial -days 825 \
  -out store.cert.pem -extfile store.ext

# S-3 — one per caller identity. The subject IS the identity. `clientAuth` and nothing else (ruled 2026-08-29).
printf '%s\n' \
  'subjectKeyIdentifier=hash' \
  'authorityKeyIdentifier=keyid,issuer' \
  'extendedKeyUsage=clientAuth' > client.ext
openssl req -newkey ed25519 -nodes -keyout owner.key.pem -out owner.csr -subj "/CN=amodal1@example"
openssl x509 -req -in owner.csr -CA ca.pem -CAkey ca.key.pem -CAcreateserial -days 825 \
  -out owner.cert.pem -extfile client.ext

# S-4 — the probe the container's own healthcheck presents. Same CA, and deliberately NOT in registration.json.
openssl req -newkey ed25519 -nodes -keyout probe.key.pem -out probe.csr \
  -subj "/CN=healthcheck@probes.sartor.internal"
openssl x509 -req -in probe.csr -CA ca.pem -CAkey ca.key.pem -CAcreateserial -days 825 \
  -out probe.cert.pem -extfile client.ext

rm -f ./*.csr ./*.ext && cd ..
```

**Treat the tenant CA as single-purpose.** Until the store checks more about a caller than its chain, any leaf this
CA issues for a registered subject is a valid store credential — so a CA shared with a web server hands out store
credentials as a side effect.

**A probe is not a principal** [S-4, ruled 2026-08-29]. The healthcheck's certificate lets it complete a handshake;
it holds no grant, is not in `registration.json`, and reaches only `/health`. Do not add it there to make it work —
it already works, bounded by its own small allowance (`Limits.max_per_probe`, 2) rather than by a share of the
global ceiling.

## The store's signing key

```sh
openssl genpkey -algorithm ed25519 -out signer.key.pem
```

**Without it the store cannot open the tenant's policy chain.** With no realm pinned, `isidium init` comes back
`init.no-ratifier: identity is disabled and no ratifier key is pinned` — measured 2026-09-01 against a container
that was otherwise entirely healthy, and it is the failure most likely to be met on a first start. Unset
`ISIDIUM_SIGNER` when the tenant's ratifier is a realm rather than a key on this disk.

## The registration

One entry per caller identity; the subject is the certificate's, and the grant is what that caller may do
(`owner`, `contributor`, `lander`).

```json
{
  "CN=amodal1@example": ["amodal1@example", "owner"],
  "CN=sartor-planner@agents.example": ["sartor-planner@agents.example", "contributor"],
  "CN=factory@example": ["factory@example", "lander"]
}
```

## The deploy key

When `ISIDIUM_ORIGIN` is a forge over SSH (`git@host:owner/repo.git`), the store needs a credential to clone and
push with, and it is a **deploy key**: one per tenant repository, registered at the forge with write access
(ruled 2026-09-02: a deploy key, not a machine account).

```sh
mkdir -p deploy/ssh
ssh-keygen -t ed25519 -N "" -C "isidium-store deploy key" -f deploy/ssh/store-deploy-key
gh api -X POST repos/<owner>/<repo>/keys -f title="isidium-store deploy key" \
  -f key="$(cat deploy/ssh/store-deploy-key.pub)" -F read_only=false
```

No passphrase — a container cannot type one. The private half stays here (`deploy/ssh/` is gitignored) and is
mounted read-only; the entrypoint copies it into the store's own home at 0600, because ssh refuses a key anyone
else can read and a bind mount arrives with the host's mode. Nothing else about the image changes: with a `file://`
or https origin the key is never looked for.

**What this credential is, so nobody assumes it the other way round.** A deploy key is a **repository-wide write
credential** — no forge scopes a key to a path. What holds the store to `docs/work/` is the store's own code; what
holds *everyone else* out of `docs/work/` is the forge's gate on `main` (the deployment record, S-12). Two parties,
two mechanisms, and neither substitutes for the other.

**The forge's host keys are pinned, never learned.** `deploy/known_hosts` carries GitHub's three host keys, fetched
from its authenticated API with the fingerprints beside each line; the image copies it to `/etc/isidium/known_hosts`
and git is told to use that file and nothing else, with `StrictHostKeyChecking=yes`. A host that does not match is
refused, never prompted for. Another forge is another line in that file, its fingerprint checked the same way.

**When the push fails, which of two things it was.** A rejected key and a rejected host key both end the push and
git's line looks the same. Run ssh's own check from the host with the same pins:

```sh
ssh -i deploy/ssh/store-deploy-key -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes \
    -o UserKnownHostsFile=deploy/known_hosts -T git@github.com
# -> Hi <owner>/<repo>! You've successfully authenticated, but GitHub does not provide shell access.
```

`Host key verification failed` is the pin — the host's key is not in `deploy/known_hosts`. `Permission denied
(publickey)` is the key — not registered, registered read-only, or the wrong repository. If this succeeds from the
host and the container still fails, the difference is the mount: the key file must be readable inside the
container, and `ISIDIUM_ORIGIN` must be the SSH form.

**Revoking the store** is deleting the key at the forge. It stops the store and nothing else.

## Standing it up

```sh
printf '%s\n' \
  'TENANT=sartor' \
  'ISIDIUM_ORIGIN=git@forge.example:sartor/tenant.git' \
  'ISIDIUM_ROOT=docs/work/' \
  'STORE_PORT=8443' > .env

podman build -f deploy/Containerfile.store -t isidium-store:0.1.0 ..   # from deploy/; context is the repo root
podman compose up -d                                                   # or: docker compose up -d
podman logs isidium-store-sartor
```

**Why the build is its own line.** `compose.yaml` carries a spec-correct `build:` block, and one command should be
enough — but `podman compose up --build` fails on this workstation with `no Containerfile or Dockerfile specified
or found in context directory, C:\Dev\the-factory`, and it fails identically with the Containerfile named by an
absolute path, so it is podman-compose 1.6.0 against podman's Windows client and not this file. On a host whose
compose provider builds, `podman compose up --build -d` is the one command and the `build:` block is what it uses.

The first line the store prints is the one to read:

```
isidium: tenant=sartor footprint=filtered root=docs/work/
```

**`footprint` is counted, never claimed.** `filtered` is the ruled shape. `full` is S-9's declared degradation — a
forge without `uploadpack.allowFilter` answers the `--filter=blob:none` clone with every blob, and the config the
clone writes is *identical either way*, so this is counted off the object graph rather than read off a setting.
There is still no working tree and no index, so the class of defect this shape exists to remove stays impossible;
the footprint just grows to the history's blobs. Verified both ways on 2026-09-01 by flipping
`uploadpack.allowFilter` on the origin and restarting: the line changed to `full`, and back.

`ISIDIUM_ORIGIN` must be a URL the container can reach, and **the forge must be on its egress allowlist** (7be.2):
the store fetches governed blob content from it while it runs, so a store cut off from the origin can read no
governed document it did not itself write.

If the entrypoint cannot reach it, that is what it says and the container stops:

```
isidium: the store could not clone file:///srv/origin.git — git.failed @ clone: fatal: detected dubious ownership …
```

## Checking it

From the host, with a certificate this CA issued:

```sh
python - <<'PY'
import http.client, ssl
ctx = ssl.create_default_context(cafile="tls/ca.pem")
ctx.load_cert_chain("tls/owner.cert.pem", "tls/owner.key.pem")
c = http.client.HTTPSConnection("localhost", 8443, context=ctx, timeout=10)
c.request("GET", "/health"); r = c.getresponse()
print(r.status, r.read().decode())
PY
# -> 200 {"ok": true}
```

The container checks itself the same way every 30 seconds, through the same front door (`deploy/healthcheck.py`):
mTLS to the real listener, and the assertion is `{"ok": true}` rather than merely that something came back.
Verified 2026-09-01 that it can tell the difference — pointed at a target the store routes elsewhere it exits 1 and
prints the store's own `service.route` refusal; with its certificate taken away it fails the handshake and exits 1;
unmutated it exits 0.

The old check was `test -S /run/isidium/store.sock`. After 7bg.8 that socket does not exist, so the container would
have been reported permanently unhealthy — and even before, a socket file said a process had opened a path, not
that the store answers.

A caller with **no** client certificate is closed at the handshake, before the parser: verified, the connection
opens and gives nothing back. Which is exactly what a *wrong certificate* also looks like — hence the spans below.

## Seeing what it did — the first start, without a collector

`OTEL_TRACES_EXPORTER=console` is `compose.yaml`'s default, and it writes spans to **stderr**: no collector, no
SigNoz, no network at all. This is not decoration on a first start. A wrong CA path refuses every caller silently on
both sides of the connection, and the spans are how that is found in minutes instead of an afternoon.

```
$ podman logs isidium-store-sartor
{
    "name": "isidium.store.call",
    "status": {"status_code": "OK"},
    "attributes": {"isidium.tenant": "sartor", "isidium.action": ""},
    ...
}
```

Point it at a real collector with `OTEL_TRACES_EXPORTER=otlp` and `OTEL_EXPORTER_OTLP_ENDPOINT=…` in `.env`; the
exporter is already in the image, so that is a restart and not a rebuild. `none` — or unset — installs no provider
and emits nothing, which keeps egress the deployment's decision rather than a wheel's.

## Pointing a checkout at it

In the tenant checkout — not the store's clone; the store has no working tree, and yours stays yours:

```sh
mkdir -p .isidium && cp <deploy>/tls/ca.pem <deploy>/tls/owner.cert.pem <deploy>/tls/owner.key.pem .isidium/
isidium init --tenant sartor --address https://localhost:8443 \
  --ca .isidium/ca.pem --cert .isidium/owner.cert.pem --key .isidium/owner.key.pem \
  --root docs/work/ --ack "software-grade signatures are acceptable for this tenant for now"
```

`init` installs the client file, the hook and the registry schemas, and opens the tenant's policy chain **over the
channel** — the store commits `docs/work/config.toml` and pushes it. Verified 2026-09-01: the chain's first entry
came back signed by the mounted `signer.key.pem`, and the commit was on the origin's `main`. The client file it
writes names no principal and no grant, because the caller is the certificate on the connection (7bg.2).

## Tenant #0 — this repository, run 2026-09-03

The store's first tenant on a real forge is the repository this file lives in: `ISIDIUM_ORIGIN` is
`git@github.com:take-tempo-public/isidium-factory.git`, the tracking root is `docs/work/`, and every command below
was run in this order (podman 5.8.3, rootless, WSL2; podman-compose 1.6.0). Where the walkthrough above and this
differ, this is the later one and the one against a forge.

```sh
# The material, under the repository's PUBLIC identity: the caller's principal is written into config.toml's
# first history entry, and that lands on a public main.
#   deploy/tls/…            as in "Issuing the certificates", with CN=amodal1@users.noreply.github.com for the owner
#   deploy/registration.json  {"CN=amodal1@users.noreply.github.com": ["amodal1@users.noreply.github.com", "owner"]}
#   deploy/signer.key.pem     as in "The store's signing key"
#   deploy/ssh/store-deploy-key (+ .pub)   as in "The deploy key"; registered at GitHub as deploy key 162206265
printf '%s\n' 'TENANT=isidium-factory' \
  'ISIDIUM_ORIGIN=git@github.com:take-tempo-public/isidium-factory.git' \
  'ISIDIUM_ROOT=docs/work/' 'STORE_PORT=8443' > deploy/.env

podman build -f deploy/Containerfile.store -t isidium-store:0.1.0 .   # 301.6 MB; openssh-client is 5.55 MB of it
cd deploy && podman-compose up -d && cd ..
podman logs isidium-store-isidium-factory
    -> isidium: tenant=isidium-factory footprint=filtered root=docs/work/    # the clone came over SSH, through the pin
podman ps --filter name=isidium-store-isidium-factory                        # -> Up … (healthy)
GET /health over mTLS from the host, as in "Checking it"                     # -> 200 {"ok": true}

mkdir -p .isidium && cp deploy/tls/ca.pem deploy/tls/owner.cert.pem deploy/tls/owner.key.pem .isidium/
python -m pip install -e packages/isidium-store        # INSTALL the client first — read the note below
python -m isidium.store.client.cli init \
  --tenant isidium-factory --address https://localhost:8443 \
  --ca .isidium/ca.pem --cert .isidium/owner.cert.pem --key .isidium/owner.key.pem \
  --root docs/work/ --ack "software-grade signatures are acceptable for this tenant for now"
    -> the policy chain's first entry: seq 1, by amodal1@users.noreply.github.com, act created, signed ed25519
    -> commit 0847c85, journal_seq 1 — pushed to main WITH THE DEPLOY KEY; the identity sweep ran on it and passed
git fetch origin main && git ls-tree -r origin/main --name-only | grep ^docs/work/
    -> docs/work/config.toml
```

`init` also installed the pre-commit hook and the registry schemas under `.isidium/` — ignored; it appended the
line itself — so this checkout refuses a governed-path commit locally, and `main` refuses one at the forge once the
gate is on (the deployment record, S-12 … S-14).

### The gate on `main`, demonstrated 2026-09-03

With the three checks green on `main`, the ruleset went on (the deployment record, S-12: a pull request required, the
checks `sweep` / `verify` / `green-bar` required, no force-push, no deletion, the store's deploy key the one bypass;
GitHub ruleset `22217228`). Then each refusal was attempted for real. `main` was `486cfe3` before and after all three.

```
$ git push origin HEAD:main                       # a human's direct push (an empty commit on top of main)
remote: error: GH013: Repository rule violations found for refs/heads/main.
remote: - Changes must be made through a pull request.
remote: - 3 of 3 required status checks are expected.
 ! [remote rejected] HEAD -> main (push declined due to repository rule violations)

$ git push --force origin e042ab8:main            # a force-push rewinding main by one commit
remote: - Cannot force-push to this branch
remote: - Changes must be made through a pull request.
 ! [remote rejected] e042ab8 -> main (push declined due to repository rule violations)

$ printf '\n# a hand edit\n' >> docs/work/config.toml && git commit -am "…"   # a human edits the governed root
isidium: refused — governed paths are written by the store, not by a commit here (03 §9.6):
  docs/work/config.toml                           # the local hook, first
$ git commit --no-verify -am "…" && git push -u origin demo-governed-edit && gh pr create …   # past the hook: PR #3
verify   fail   14s                               # the required check, on the forge:
    changed  docs/work/config.toml  — a governed path changed off main; the store is its only writer
    tampered config.toml  [config@1]  head.history-position @ history: content after the entries array
$ gh pr merge 3 --rebase
X Pull request … is not mergeable: the base branch policy prohibits the merge.
```

Two mechanisms fired on the one hand edit: the diff check (any governed change off `main`), and the grammar (a
comment after `[history]` — the store's own rule that the history is the last thing in the file). Either alone
would have blocked the merge.

**Override, and what there is not.** There is no standing bypass for the owner: `gh`'s hint that `--admin` merges a
blocked pull request is generic advice for branch protection, and a ruleset exempts nobody who is not in its bypass
list — here, the deploy key alone. The break-glass at the forge is *disable the ruleset, fix, re-enable*, one audited
call; in the store it is `isidium repair`, owner-signed. Revoking the store is deleting its deploy key. **Measured by
the owner, 2026-09-03**, on PR #3 with repository admin:

```
$ gh pr merge 3 --admin --rebase --repo take-tempo-public/isidium-factory
GraphQL: Repository rule violations found
Required status check "verify" is failing.
 (mergePullRequest)
```

Refused; `main` unchanged; PR #3 closed unmerged.

### The store's own push after the gate — and the stale clone it exposed

The last demonstration is the store writing *through* the gate: the first card, a draft written through the front
door under the owner's certificate. It landed — and not the way it was expected to, which is the finding.

```
$ python -m isidium.store.client.cli write --new k8-tenant-zero --document card.json
git.push-rejected                                 # the caller sees the rule and nothing else (C-12)
$ podman logs isidium-store-isidium-factory | grep push-rejected
git.push-rejected withheld from the caller: path='origin/main' detail='the remote moved under the store'
```

The store's clone was at its own last commit, `0847c85`; three pull requests had been merged to `main` since it
started, and **a running store never re-reads `main`** (the entrypoint says so). Its commit was a non-fast-forward
and the forge refused it. The journal row was already durable, so:

```
$ podman restart isidium-store-isidium-factory     # the clone is rebuilt at the current main …
$ podman exec isidium-store-isidium-factory git -C /var/lib/isidium/repo log --oneline -1
24652f2 replay journal 2                          # … and the pending row is replayed onto it and pushed
$ git fetch origin main && git log --oneline -1 origin/main
24652f2 replay journal 2                          # committer isidium-store <store@isidium-factory>; the bypass, live
```

`docs/work/cards/0002-k8-tenant-zero.md` is on `main`, its one history entry `by` the owner's public identity. Two
things this says. **The deploy key bypasses the gate, measured after the gate went on.** And **under a gated `main`,
every merged pull request leaves the store stale, so its next write fails until a restart** — which is the chunk
plan's **Q14**, open for the owner: the store should re-read `main` before it writes, or recover on a rejected push
when no governed path moved. Until it is ruled and built: **restart the store after merging**. The replay makes that
safe — nothing journaled is lost.

(Two smaller facts from the same run: a write refused at validation still consumes a card id — this card is `0002`
because an earlier attempt with an unaccepted `source` took `1`; and a replayed commit's git author is
`store <store@…>` with the message `replay journal N`, where a direct write's author is the caller — the document's
own `by` is right in both.)

**Install the client; do not run `init` under `PYTHONPATH`.** The first run here did exactly that, and the hook
`init` installs — `exec <the interpreter init ran under> -m isidium.store.client.hook` — then refused the very
next commit with `ModuleNotFoundError: No module named 'isidium'`, because that interpreter had never had the
package installed. It failed **closed**, which is the designed behaviour and the right one: a hook that cannot tell
what is governed refuses rather than guesses. The fix was `pip install -e packages/isidium-store` and the same
`init` line without `PYTHONPATH`; the sequence above is the corrected one. (That the refusal reads as a raw Python
error rather than an `isidium:` line is recorded as a finding.)

## What is not here yet

- **Compose was verified with `podman-compose` 1.6.0, not with Docker Compose.** `podman compose` needs a provider
  installed and this workstation had none, so one was used from a throwaway virtualenv. Everything it *runs* —
  the environment, the volumes, the ports, the healthcheck — was exercised; what it **builds** was not, because
  `--build` fails there for the reason above. The `docker compose` path is written down and unexercised.
- **`ISIDIUM_ORIGIN` over SSH against a real forge is now verified** (tenant #0, above): the clone through the
  pinned host key and the push with the deploy key. The `file://` path remains what the walkthrough above shows,
  and a mounted path still needs git told that the mount is trustworthy (`safe.directory`). **The egress allowlist
  is untested** — so far the container has reached whatever it asked for.
- **Revoking a caller** means editing `registration.json` and restarting; there is no certificate-revocation check
  and no reload. Both are named in the deployment record (H-1), and land before this listens outside a trusted
  network.
- **The realm.** When agent-station's identity system exists, `registration.json` is replaced by a lookup against
  it — one function in `server/service.py`. Nothing above that function changes.
