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

### Every version in this image is pinned, and the pin is `uv.lock` (K5, 2026-09-04)

Three kinds of thing used to float here, and none of them does now.

1. **The base images.** Both `FROM` lines carry the digest beside the tag, and it is the digest that is fetched.
   `python:3.12-slim` is rebuilt weekly, so an unpinned base meant two builds of the same commit were two
   different images. The digest is the multi-arch index, so the same line builds on amd64 and on arm64.
2. **The store's own dependencies.** The image used to `pip install` the wheel with its extras, which resolved
   pydantic, cryptography, httpx, typer and the OpenTelemetry packages against PyPI at build time. The repository
   checked a lock in CI and the container did not use it, so the artifact that actually runs was the one place
   nothing was pinned. The build stage now exports the lock (`uv export --locked`) and the runtime stage installs
   it under `pip --require-hashes`, which refuses any artifact whose bytes do not match. The store's own wheel
   goes in afterwards with `--no-deps`. **What that guarantee is, exactly** (measured 2026-09-04): `uv`
   exports both the wheel's hash and the sdist's for each version, and pip accepts an artifact matching
   *either*. So the pin is to the set of artifacts the lock recorded for that version, not to one file.
   Corrupting one of the two hashes changes nothing; corrupting both makes pip refuse with
   `THESE PACKAGES DO NOT MATCH THE HASHES FROM THE REQUIREMENTS FILE` and exit 1, which is how this was
   checked rather than assumed.
3. **`uv` itself.** A resolver is a version too; it is copied in from `ghcr.io/astral-sh/uv`, digest-pinned, and
   it stays in the build stage.

**What this changes for you as the operator:** a build now fails if `uv.lock` and `pyproject.toml` disagree, which
is the same refusal CI makes, and it fails at the export rather than by quietly resolving something else. To move
a version, change `pyproject.toml`, run `uv lock`, and rebuild. Renovate proposes those bumps as pull requests; a
base-image bump is deliberately never grouped with anything, because it means a rebuild and a restart of every
tenant's store.

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

That is what makes a restart the way a bypass commit becomes visible. Since K9 a running store does re-read the
*branch* — it fetches and fast-forwards its own ref before every write — but it does not re-parse the documents it
loaded at start, and a catch-up that touches a governed path is refused rather than followed. So a commit somebody
pushed straight past it, which is precisely what `check` exists to detect, is still invisible to what `check` reads
until the store restarts. **Verified 2026-09-01:** with the store up, a commit pushed directly to the origin left
the store's clone at `32217bd`; after `podman restart` it was at `6b6f3ba`, the planted commit. A persistent clone
would have gone on serving whatever branch it last saw.

**The cost, stated rather than discovered:** a fresh clone is cold, and a filtered clone holds no governed blob
either, so the first load fetches every blob under the tracking root in **one** round trip before it reads
anything [K7b, 2026-09-06 — until then it hydrated one object at a time, N round trips at every start, and a
tenant of forty governed documents would have outrun its own `start_period`]. It is paid at start-up rather
than on a call path, and it no longer grows with the tenant.

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

One entry per caller identity; the subject is the certificate's **whole subject in RFC 4514 form** (K6: a bare
common name matches nothing — `openssl x509 -in <cert> -noout -subject -nameopt RFC2253` prints the key after
`subject=`), and the grant is what that caller may do (`owner`, `contributor`, `lander`).

```json
{
  "CN=amodal1@example": ["amodal1@example", "owner"],
  "CN=sartor-planner@agents.example": ["sartor-planner@agents.example", "contributor"],
  "CN=factory@example": ["factory@example", "lander"]
}
```

**The store re-reads this file** (K6): it checks the file's stamp on every connection and re-parses it when it moved,
so revoking a caller is deleting their line — the next connection is refused `auth.unknown-client`, with no restart.
A file that stops parsing — a torn edit, a grant that is not one of the three — **or that is absent** (deleted, or
replaced by a rename on a host where the old inode goes away) **registers nobody until it parses again**: the store
fails closed rather than keep serving the mapping it last read, because the line just mistyped may be the
revocation. The reason goes to stderr with the rule id, once; `/health` keeps answering, and every caller meets
`auth.unknown-client` [absence added by K7a, 2026-09-06 — before it, an absent file ended every connection
silently, the probe's included]. At start-up the same defect stops the store before
it listens. What the store checks on the certificate itself: it chains to the CA (the handshake), it is inside its
validity window by the store's own clock, and it carries the `clientAuth` extended key usage — `auth.expired`,
`auth.not-yet-valid`, `auth.no-client-auth` otherwise, each terse.

**Edit the file in place.** `compose.yaml` bind-mounts the *file*, and a bind mount follows the inode: an editor that
saves by writing a temporary file and renaming it over the original leaves the container reading the old inode, and
the store — whose change detection is the file's stamp — sees nothing until a restart. `vim` and VS Code do that by
default; `python -c` / `Set-Content` / `>` write in place. Verified on tenant #0 (below).

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

## Gating a tenant's `main` — the recipe (K12, 2026-09-08)

Tenant #0's gate is three things, walked through below: a ruleset on `main`, a required check that runs the
governed-path verifier, and the store's deploy key as that ruleset's one bypass. Until K12 the verifier was
`tools/verify_chain.py`, a tool of this repository run from a `uv sync` of the workspace — which a tenant's runner
does not have. It now ships in the package as **`isidium verify`**, so a tenant's forge gates its `main` from an
install alone.

**The workflow** is `tenant-chain-verify.yml` in this directory: copy it into the tenant's `.github/workflows/` and
set the one value it leaves open, `STORE_COMMIT` — the commit of this repository the store is installed from. Its
steps are the ones `chain-verify.yml` runs here, minus the workspace: check out at full depth (a pull request's diff
base and `HEAD^` on `main` are not in a shallow clone, and the verifier refuses a shallow checkout rather than
passing it — K7a), then run the verb from a pinned install — `isidium verify --repo .` on a push to `main`,
`--diff-base origin/<base>` on a pull request.

**The pin is the tenant's decision, and it is not free to be wrong.** At the forge a fresh clone has no `.isidium/`
(every tenant ignores it), so the verifier reads the registry of the package the workflow installed. That package
must ship the config version the tenant adopted — `config@3` for a tenant born today — or the verifier refuses the
tenant's own `config.toml` as `hook.toolkit-behind` (K11) and the check is red on every push, which is the loud
answer K11 chose over verifying against `config@1` in silence. Move the pin when the toolkit bumps the version the
tenant adopts, alongside `isidium install` in the checkout. The placeholder in the file is deliberately not a value:
left in place, the install refuses it before anything is verified against the wrong registry.

**The ruleset** is tenant #0's, with the tenant's own required checks beside `verify`: `pull_request`,
`required_status_checks` (**not strict** — the store's own pushes would otherwise stale every open pull request),
`non_fast_forward`, `deletion`; `bypass_actors: [{actor_type: DeployKey, bypass_mode: always}]`. A repository that
already carries classic branch protection with required status checks on `main` is expected to reject the store's
direct push of `docs/work/config.toml` — a deploy key is not in a classic protection's bypass — so there the ruleset
replaces the protection rather than sitting beside it. *Expected, not yet measured*: sartor's `main` is that case,
and the bridge measures it.

**Verified 2026-09-08, on this workstation, from this checkout** — the workflow's install-and-verify step with the
pin pointed at this repository on disk (`git+file:///C:/Dev/isidium-factory@k12-doors-read-main-verify-verb`,
commit `f035307`), through `uv tool run --python 3.12 --from "isidium-store @ <that spec>" isidium verify
--repo .`: uv cloned and built the package, installed 24 packages in 1.8 s, and the verb printed the three lines
tenant #0's own gate prints (`ok config.toml [config@3] 3 entries`, the two cards) and `isidium: 3 ok, 0
tampered`, exit 0 — 28.7 s end to end, nothing of this checkout's environment involved. The placeholder, left in
place, was refused by git before anything was built: `fatal: invalid refspec '+refs/tags/<the isidium-factory
commit …>'`, exit 1. Any commit of `main` from K12's merge on ships the verb; every commit since K10 ships
`config@3`.

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

**A rename is a change to both of its paths** [K7a, 2026-09-06]. Until then the diff check and the hook read
`git diff --name-only`, which under git's default rename detection lists a rename's destination alone, so
`git mv` of a card out of the tracking root passed the hook, passed `verify` on the pull request, and passed
`verify` on `main` — the card left the governed set with every check green. Both doors now read
`--no-renames` and name the source; and on a push to `main` the check refuses any governed path the parent
commit had and `HEAD` does not (`removed`), so a disappearance is a verdict rather than a silence. A shallow
checkout, which cannot see the parent, is refused rather than passed.

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
every merged pull request left the store stale, so its next write failed until a restart** — which is the chunk
plan's **Q14**, ruled the same day and **built by K9**, below. The restart is no longer the answer and is no longer
the instruction.

(Two smaller facts from the same run: a write refused at validation still consumes a card id — this card is `0002`
because an earlier attempt with an unaccepted `source` took `1`; and a replayed commit's git author is
`store <store@…>` with the message `replay journal N`, where a direct write's author is the caller — the document's
own `by` is right in both.)

### K9: a write onto a `main` the store had never seen — 2026-09-03

The condition above is closed. The store now fetches `main` and fast-forwards its own ref before every governed
write, so a merged pull request no longer leaves it behind. Demonstrated on this repository, in this order, with
**no restart between the merge and the write**:

```
$ podman exec isidium-store-isidium-factory git -C /var/lib/isidium/repo log --oneline -1
cfba6c9 The chunk plan lives in the record, not here    # the store's clone, before anything merged

$ gh pr merge 8 --rebase --delete-branch                # K9 itself; main moves to ef7cd4b
$ git log --oneline -1 origin/main
ef7cd4b K9: the store fetches and fast-forwards to `main` before every write

$ python -m isidium.store.client.cli write --new k9-store-re-reads-main --document card.json
  … "commit": "7aaa50c8b21dfdb9fdacfcdf4b0b33a7bc856c46", "journal_seq": 3

$ git fetch origin main && git log --format="%h %p %s" -1 origin/main
7aaa50c ef7cd4b created cards/0003-k9-store-re-reads-main.md   # its parent IS the merged tip
```

The card's parent is the commit the store had never seen when the write began. Under the shape this replaces, that
same write came back `git.push-rejected` and needed a container restart and a journal replay to land.

**The in-memory model was checked against `main`, not assumed.** The fast-forward is cheap only because the store
does not re-parse the documents it loaded at start, which is safe exactly when the commits it caught up on touched
no governed path. Live, after the fast-forward: `show card 2` and `git show origin/main:docs/work/cards/0002-…` agree
on all eleven head fields, on the scope prose and on the history length.

**Both spans arrived** (C-11). `isidium.store.sync` appears twice on that write, `isidium.action=fetch` and
`isidium.action=fast-forward`, both `status_code: OK`, beside the request and call spans.

**What it costs, measured in this container against GitHub over SSH** (seven repetitions): a fetch of an unmoved
`main` is **1568 ms median** (1277 min, 2708 max) and reading the tip off it is 8 ms. That is one extra round trip
per governed write. It is not the process spawns — those are single-digit milliseconds here — it is the round trip,
and there is no cheaper shape: `ls-remote` is the same conversation, and no answer about a remote's tip can be had
without asking it.

**One environment note, and it is the workstation's rather than the deployment's.** The clone at start hung for
fourteen minutes on this machine before any of the above could run. Measured: the path MTU out of the podman VM is
about 1400 while its interfaces advertise 1500, and nothing sends back the ICMP that would say so — a black hole.
Small exchanges survive it (`git ls-remote` over SSH answers in 2 s, and an HTTPS clone finishes in 1 s), and bulk
transfer over SSH does not, which is why the symptom looked like a broken deploy key and was not: the same clone
from Windows, outside the VM, takes 3 s. `ip link set eth0 mtu 1400` inside the VM fixed it immediately, and the
container needs its own interface capped too — it was run on `podman network create --opt mtu=1400 isidium-mtu1400`.
Neither is persistent and neither is part of this deployment; they are recorded here because the failure they
produce is indistinguishable from a credential problem and cost an hour once.

**Install the client; do not run `init` under `PYTHONPATH`.** The first run here did exactly that, and the hook
`init` installs — `exec <the interpreter init ran under> -m isidium.store.client.hook` — then refused the very
next commit with `ModuleNotFoundError: No module named 'isidium'`, because that interpreter had never had the
package installed. It failed **closed**, which is the designed behaviour and the right one: a hook that cannot tell
what is governed refuses rather than guesses. The fix was `pip install -e packages/isidium-store` and the same
`init` line without `PYTHONPATH`; the sequence above is the corrected one. (That the refusal reads as a raw Python
error rather than an `isidium:` line is recorded as a finding.)

### K6: the migration act, and a revocation that needed no restart — 2026-09-05

The K6 image (`e3b1e52312eb`, built from `main` at `ac81ad2`) went up the way K5's did: the container recreated from
its recorded `CreateCommand` through `podman machine ssh` (`podman stop` waited its 10 s and sent SIGKILL — still
K8's finding), healthy in about forty seconds. Its journal held three `journal@1` rows and no version pin; the first
open under K6 added the four columns and pinned `meta.schema = 1`, the version those rows were chained from.

**The act.** The owner's `config.toml`, edited to adopt `config@2` — head `schema = 2`, `chain_opened_under = 1`,
the `config.toml` manifest row → `config@2`, no `[journal]` written (the default is `journal@2`) — handed over from
the workstation checkout:

```sh
isidium write --config config-migration.toml
```

answered policy entry 2 (`act = "config-policy"`, `fields = ["chain_opened_under", "governed", "schema"]`), journal
row 4 and commit `fe050e4`, pushed to `main` through the deploy key with no restart between the merge of K6 and the
write. Inside the container afterwards: four rows, `Journal.verify()` true, the genesis still `schema:1`, rows 1–3
byte-for-byte what they were, and row 4 carrying `schema = 2`, a `credential` of
`sha256:e74d4eb11ca18fd501d729af39d59aed27ba1ce05dbcfbcd6cd0c9b9b739b04a` — the SHA-256 of the owner certificate's
DER, recomputed on the workstation with `openssl x509 -outform DER | sha256` — and a trace pointer beside it. On the
pulled checkout, `python tools/verify_chain.py --repo .` printed `ok config.toml [config@2] 2 entries`, and the forge's
`chain-verify` run on `fe050e4` passed: the check that would have gone red on `main` had the verifier still read the
genesis off the head's version.

**The revocation.** With the store running, `deploy/registration.json` was rewritten **in place** with the owner's
line replaced by a stranger's; the next `isidium show queue` from the workstation answered `auth.unknown-client`.
Rewritten in place again with the owner's line back; the next call answered the queue. No restart either way, and
the file the container reads is the bind-mounted one — which is why *in place* matters (above).

### K6b: `podman stop` reaches the store — 2026-09-05

Every `podman stop` since K2 had printed *`StopSignal SIGTERM failed to stop container … in 10 seconds, resorting
to SIGKILL`* — the store is PID 1 (the entrypoint `exec`s it) and installed no handler, and a PID 1 receives no
default action. Since K6b `serve` handles SIGTERM and SIGINT: it closes the listener, waits up to
`Limits.shutdown_grace` (5 s) for the calls in flight, and exits 0. Measured on the same evening, both ways: the
K6 container's stop took **10.95 s** and ended in the SIGKILL line; the K6b image went up the usual way (the
recorded `CreateCommand`, through `podman machine ssh`), and then:

```sh
time podman stop isidium-store-isidium-factory
```

returned in **1.15 s**, exit status 0, one `isidium.store.stop` span on stderr, no SIGKILL line — the first clean stop this
container has had. `restart=unless-stopped` treats that as what it is: a stop, not a failure. A stop with a call
in flight waits for it; one with a peer holding a connection open gives up on that peer at the grace and lets the
journal's write-ahead replay whatever it was in the middle of at the next start.

### K10: `config@3`, the second migration act — 2026-09-06

The K10 image (`4dc50755d997`, built from `main` at `99db6ea`) went up the usual way — the container recreated from
its recorded `CreateCommand` through `podman machine ssh`, the VM's MTU cap still at 1400 — healthy in **31 s**; the
running code was checked for the members-first roll-up, the queue renderer and the typed verdicts, and the image's
registry for `config@3.toml`. Then, from the workstation checkout:

- `isidium show queue --text` printed the board's queue section (eight lines, `## Queue` first), and `show queue`
  carries the same text as `markdown` beside its fields.
- `isidium ratify --writes <a new draft> --dry-run` answered in 3.4 s with prospective id 4 and **one typed
  verdict** — `{"rule": "ratify.not-a-signed-act", "path": "", "detail": "created"}` — where K7c had seen the
  rendered string; `origin/main` unmoved, no card `0004`, the counter still 3.
- **The act.** The owner's `config.toml`, edited to adopt `config@3` — head `schema = 3`, the `config.toml` manifest
  row → `config@3`, `chain_opened_under = 1` untouched — handed over with `isidium write --config`, answered in 6.7 s:
  policy entry **3** (`act = "config-policy"`, `fields = ["governed", "schema"]`), journal row **5** (`schema = 2`,
  the owner's credential), commit **`dd13fbe`** pushed to `main` through the deploy key, `landed = true`. Inside the
  container: five rows, the genesis still `schema:1`, the counter untouched. The forge's `chain-verify`,
  `identity-sweep` and `ci` on `dd13fbe` all passed.
- **The gate.** The migrated file with `root = "docs/elsewhere/"`, handed over the same way, was refused at the
  terminal — `validate.failed @ config.toml: config.immutable @ root: 'docs/work/' -> 'docs/elsewhere/': this key is
  immutable once written` — exit 2, `main` unmoved. Under `config@2` the same edit had answered the store's own
  `config.root-mismatch`; the schema's gate now answers first.
- **The checkout's installed registry was stale, and this is a finding.** `.isidium/schemas/` in the workstation
  checkout held the eight documents `init` installed at K8 — no `config@2`, no `journal@*` — and nothing had
  refreshed it since; `Registry.for_checkout` reads that directory alone (no overlay on the shipped registry) and
  `resolve_effective` falls back to `config@1`'s defaults, silently, when the adopted version is not installed. The
  pre-commit hook has been resolving tenant #0's `config.toml` that way since K6. Refreshed here with
  `install_schemas(Path("."))` from a Python prompt — twelve documents — after which `python tools/verify_chain.py
  --repo .` printed `ok config.toml [config@3] 3 entries`. There is no `isidium` verb for it yet; the chunk plan
  carries the finding.
- `isidium check 2` → chain `["ok"]`, integrity `[]`; `show card 2` → `draft`.

### K12: the door reads `main` before it resolves — finding 2 closed on a live store — 2026-09-08

The bridge's first turn (2026-09-07) found that the store resolved `refs` against the clone it held at start, and
synced to `main` only at commit time — which the dry run never reaches. A dry run answered `ref.unresolved` for a
file that had been on `main` for a day. K12 moved the fetch to the door: the sitting and a card born `ratified`
read `main` before they resolve. Demonstrated on tenant #0, on the K12 image `d0f659368880`, in the one order that
proves it:

- The container was **recreated on the K12 image before PR #32 merged**, so its clone was the pre-merge `main`,
  `2acf4619` — which does not hold `deploy/tenant-chain-verify.yml` (that file arrives with the merge). `git -C
  /var/lib/isidium/repo rev-parse HEAD` inside the container: `2acf4619`.
- **PR #32 merged**; `main` became `c1815654`, now holding the file.
- From the workstation checkout, `isidium ratify --writes <a draft with `refs = ["deploy/tenant-chain-verify.yml"]`>`
  — the default dry run — answered **one verdict, `ratify.not-a-signed-act: created`** (the draft is a `write`, not
  the sitting's to sign), and **no `ref.unresolved`**: prospective id 4, `ready` true, exit 0. Before K12 the same
  dry run against a clone at `2acf4619` answered `ref.unresolved … no such path`, which is what the mutation
  `k12.toml` M1 reproduces against the suite.
- The clone `rev-parse HEAD` **after** the dry run was `c1815654`: the door fetched and fast-forwarded onto the
  merged tip, which is why the ref resolved. Nothing was written — `show queue --text` still empty, no card `0004`,
  the counter unmoved.

`isidium verify` also ran as the forge's `verify` check **on PR #32 itself** and passed: the verb and the workflow
that calls it landed together, so the pull request shipping the verb was gated by it. The tenant recipe
(*Gating a tenant's `main`*) was exercised on this checkout from a pinned `git+file://` install, 28.7 s, exit 0;
sartor's own gate is the bridge's to stand up.

### K12b: the first cold start against the forge's bitmap — tenant #0 back up — 2026-09-08

The 2026-09-08 recreate that moved tenant #0's secrets to `isidium-deploy/isidium-factory/` crash-looped before the
store listened: `git.fetch-failed @ origin 3 objects: fatal: bad revision '163e9eac…'`, *did not send all necessary
objects*. Not the move, not MTU, not the key. `Repo.prefetch`'s one `fetch --stdin` by object id ran git's ordinary
negotiation, the fresh clone offered its own `main` as a `have`, and the forge — holding a reachability bitmap over
that tip by then — answered the wants minus the haves' closure, which is where every governed blob sits. The K7b,
K7c and K12 recreates came up on the same code because the bitmap did not yet cover the tip. K12b (PR #36) passes
`-c fetch.negotiationAlgorithm=noop` on that one fetch, as git's own lazy fetch does; the mechanism is reproduced
in the suite on a `file://` origin after `repack -adb`.

Demonstrated here on the K12b image `a63c543d5aba` (`isidium-store:0.1.0` and `:k12b`, built from the PR #36 tree,
which is byte-identical to the squash the merge makes), the container recreated from its recorded command:

- **`running/healthy` in 44 s, zero restarts** — the cold start that had crash-looped an hour earlier on the K12
  image against the same forge, the same key and the same mounts.
- Inside the clone (`main` at `dd4aaac`), the three governed blobs the failed fetch had named, under
  `GIT_NO_LAZY_FETCH=1 git cat-file --batch-check`: `163e9eac… blob 1315`, `a3de2b60… blob 1417`,
  `df4951f3… blob 2404` — present, brought by the one batch fetch, not hydrated afterwards. The container log holds
  no `fetch-failed` and no traceback.
- From the workstation checkout, `isidium show queue --text` answered the queue with every count at none, exit 0.

One workstation note for the recorded command: run from Git Bash, MSYS path conversion rewrites the `-v` targets
(`/etc/isidium/tls:ro` became a path under `Program Files\Git`); `MSYS_NO_PATHCONV=1` on the invocation, or
PowerShell, passes them through.

### The two identity tiers, and the factory's client material — 2026-09-09 (L2)

A store knows a caller by exactly two files it is handed: **the CA it pins** (the handshake refuses every certificate
that CA did not issue) and **the registration** (`subject → [principal, grant]`, re-read on change). A client knows a
store by one file, the `client.toml` shape: address, CA, its own certificate and key. The owner ruled (2026-09-09) that
the factory is designed for **two tiers**, which differ only in *who writes those files*:

| | the local tier — the default | the realm tier — agent-station |
|---|---|---|
| the CA | a key on disk under the deploy home; the recipe above | the realm's CA; its key never leaves the realm |
| a client certificate | issued by the recipe, one per caller identity | issued by the realm on binding |
| the registration row | edited by hand | written by the realm from its bindings |
| the client file | written by hand, or by `init` | written by the realm's enrolment |

Nothing in the store, the client or the factory reads differently between the two. A project without
identity-management infrastructure runs the local tier as its durable default, not as an interim; moving a tenant to
the realm tier is reissuing under the realm's CA and swapping the pin. The seam is the pair of files.

**The factory's client material lives in the tenant's own deploy directory.** The deploy home is one parent with one
directory per tenant (the owner's layout, 2026-09-08); the factory's material for a tenant is inside that tenant's
directory, under `factory/`:

```
<deploy home>/<tenant>/factory/client.toml      # the client.toml shape; paths relative to this file
<deploy home>/<tenant>/factory/lander.cert.pem  # issued by the tenant's CA, subject = the lander's principal
<deploy home>/<tenant>/factory/lander.key.pem
```

The factory finds a tenant by name under `$ISIDIUM_DEPLOY` — required, never defaulted: unset is
`factory.not-configured`, a tenant with no `factory/client.toml` is `factory.unknown-tenant`, a name outside the
tenant grammar is `factory.tenant-name` (a tenant is a directory, and `..` is not a tenant).

**Issuing the lander** (the local tier; the same recipe as S-3, with `MSYS_NO_PATHCONV=1` on Git Bash):

```sh
cd <deploy home>/<tenant> && mkdir -p factory
printf '%s\n' 'subjectKeyIdentifier=hash' 'authorityKeyIdentifier=keyid,issuer' 'extendedKeyUsage=clientAuth' > client.ext
openssl req -newkey ed25519 -nodes -keyout factory/lander.key.pem -out lander.csr -subj "/CN=lander@<tenant>"
openssl x509 -req -in lander.csr -CA tls/ca.pem -CAkey tls/ca.key.pem -CAcreateserial -days 825 \
  -out factory/lander.cert.pem -extfile client.ext
rm -f lander.csr client.ext
# registration.json gains the row; the store re-reads the file on change — no restart:
#   "CN=lander@<tenant>": ["lander@<tenant>", "lander"]
printf '%s\n' 'tenant = "<tenant>"' 'address = "https://<store>:8443"' 'ca = "../tls/ca.pem"' \
  'cert = "lander.cert.pem"' 'key = "lander.key.pem"' > factory/client.toml
```

**Landing a run report:** `ISIDIUM_DEPLOY=<deploy home> isidium factory land --tenant <tenant> --report <run.json>`
(the umbrella dispatches to `isidium-factory` on PATH). The report is `{run_id, events[], suggestions[]}`; it is parsed
against the event union at the terminal before any channel opens, and the store parses it again at its door. The
result is the store's `land` result: the cursor, the event and intake ids, `landed`, `empty`.

### L2: the first land on tenant #0, through the lander client — 2026-09-09

The lander's identity was issued on the local tier exactly as the recipe above says — `CN=lander@isidium-factory`
under tenant #0's CA, into the tenant's `factory/` directory with its `client.toml` — and its row added to
`registration.json`; the store, on the L1 image `657a4f89b079` (`isidium-store:0.1.0` and `:l1`, recreated from the
recorded command, healthy in 35 s), picked the row up on the next connection without a restart, as K6 promised.

The report was **synthetic and said so**: one `question` event on card 0002 naming the run as synthetic and claiming
no execution state, and one `docs` suggestion asking that the sidecar's first line be read that way. Landed with
`isidium factory land --tenant isidium-factory --report …` — the umbrella dispatching to `isidium-factory` on PATH —
in one call:

- The result: cursor `68ffb68` (the head before; nothing merged since — the first land takes the head), event `e1`,
  intake `s1`, `landed: true`, `empty: false`, journal seq 6, commit `c0fe8e2`.
- On `main` after, one commit `land` by the store, under the ruleset's deploy-key bypass: `docs/work/state.json`,
  `docs/work/state/history.jsonl`, `docs/work/suggestions.jsonl` and `docs/work/BOARD.md` — and **no card file**.
  The forge's `chain-verify` and `identity-sweep` both passed on it.
- `show queue --text` before: *"merged, not landed: n/a (in-project)"* — no sidecar. After: *"merged, not landed: 0"*,
  and the board's header *"inbox run 1"*: the counts moved, which was the criterion.

**Found live, fixed in the same pull request:** `landed_at` landed as `2026-09-09T10:32:09-07:00` — git's answer for
the cursor commit's time carries the author's offset, and every other time in the file is UTC `Z`. The store now
writes the cursor's time in its own form; the first sidecar on `main` carries the offset form until the next land
rewrites it (the fold overwrites; nothing merges).

### `accept` — the acceptance block, compiled and run at the owner's terminal — 2026-09-09 (L3)

`isidium accept <id>` is a **client verb** (ruled 2026-09-09): it reads the card from the store (`show card` — the
ratified content, its label, its compare-and-swap head), compiles the acceptance block to the manifest with the
checkout's `config.toml [runners]` bindings, and runs every scenario **in the checkout**, through four runners keyed
by the binding ids the schema ships: `pytest` (`test-marker`: a `path::name` or a marker, plus the scenario's
`tests[]`), `shell` (`command`: the argv, `exit_code` / `stdout_matches` / `stderr_matches` / `files`), `http`
(`method` and `path` against `context.base_url`; `status` / `body_matches` / `headers`), `file` (`file-assert`: an
optional `action.run`, then the one check). A `manual-evidence` scenario runs nothing and answers `manual`. The
store runs none of it: its image holds python, git and the store.

Exit 0 when every verdict is `pass`, 1 otherwise (a verdict), 2 on a refusal. Before anything runs the store's label
decides: a `draft` is `accept.draft` unless `--unsafe-draft`, which prints each command and asks per scenario;
`unratified`, `integrity(…)` and `withdrawn` are `accept.unratified`. A kind whose binding names a runner the toolkit
does not ship is `accept.unbindable` naming the scenario. A runner that cannot run — no program, a socket refused,
pytest collecting nothing — is `accept.runner-error`, never a `fail`.

`--close` is one `write`: the same document with a `[[closures]]` entry appended (`kind = "human"`, the verdicts, the
manifest hash as evidence) and `status = "closed"`, which the store derives as `closed`. `met` needs every verdict
`pass`; a `fail` or a `manual` refuses (`accept.failed`) unless `--deviated "<why>"` closes it as `deviated`, pending
the owner's review. Under `ratification.verdicts_required = true` (the default) a card with no scenario cannot
close (`accept.no-verdicts`). A fresh human closure projects `closed (pending-ingest)` until a land ingests it.

```sh
isidium accept 4 --text            # the verdicts, one line each; exit by verdict
isidium accept 4 --close           # met: one write, the card closed
isidium accept 4 --close --deviated "S3 needs the listener the checkout does not run"
```

### L3: the first card closed by `accept` on tenant #0 — 2026-09-09

Card 0004 — L3 itself, the first time the factory's own work is a card (ruled 2026-09-09) — was written as a draft
through the store (`ae458bc`), ratified by the owner's signed sitting (`bf43993`, `batch-manifest`; the first two
attempts were the dry run, which is the CLI's default — `--sign` is the signature), and then, from the checkout on
`main` `6eacf01`:

```
isidium accept 4 --close --text
S1     pass    3 passed in 0.67s
S2     pass    exit 0
S3     pass    packages/isidium-store/src/isidium/store/client/runners.py: contains 'accept.runner-error'
S4     pass    2 passed in 36.83s
met · closed
```

Two `test-marker` scenarios ran through pytest (one named test plus `tests[]`, one process each), the `command`
ran the client's own `--help`, the `file-assert` read the runner's source; every verdict `pass`, exit 0. The one
write appended closure `c1` (`kind = "human"`, `outcome = "met"`, the four verdicts, the manifest hash as evidence)
and set `status = "closed"`: commit **`4d8986a`** on `main`, `closed cards/0004-l3-accept-four-runners.md`. The
store projects the card **`closed (unverified)`** — a human closure under the standalone dial, which a factory
verification (T-A12, v1c) would make `closed`. Before the sitting it projected `ratified (pending-ingest)`: the
signed entry post-dated the sidecar's `landed_at`, which is what the next land ingests (L4).

### L4: the walk runs at land — `config@4` adopted, the first landed integrity map, two findings — 2026-09-10

The L4 image (`9b2950bf7223`, `isidium-store:0.1.0` and `:l4`, built from `main` at `a1e8bff`) went up from the
recorded command (`MSYS_NO_PATHCONV=1` on Git Bash, as K12b notes) — **healthy in 34 s, zero restarts**. The
checkout's registry was refreshed with `isidium install` (K11's verb, the first time it has been needed since it
shipped): `config@4`, `sidecar@2`, `sidecar-events@2` beside the twelve. Then, from the workstation checkout:

- **The act.** The owner's `config.toml` edited to adopt `config@4` — head `schema = 4`, the `state.json` row →
  `sidecar@2`, the `state/history.jsonl` row → `sidecar-events@2`, the `config.toml` row → `config@4`, everything
  else untouched — handed over with `isidium write --config`, answered in 6.7 s: policy entry **5**
  (`act = "config-policy"`, `fields = ["governed", "schema"]`), journal row **10**, commit **`f018269`** on `main`
  through the deploy key, `landed = true`. The file handed over is kept beside the tenant's client material
  (`isidium-deploy/isidium-factory/factory/config-4.toml`).
- **The land.** The same synthetic report as L2, through `isidium factory land`, in 11 s: cursor `68ffb68`
  (unchanged since the first land — see the third finding), event `e2`, intake `s2`, journal row 11, commit
  **`9aa5f64`** on `main`. `state.json` now carries `schema = 2`, **`integrity = {}`** — the walk over every commit
  since the cursor found every governed transition explained and recomputed clean: the store's own commits are
  authored by the caller, so `attribution` has nothing to say — and `ingest = {run_id, overflow = 0}`. The board's
  header reads *"inbox run 2"*; `show queue --text` unchanged.
- **Finding 1, live: `isidium check 4` answered `rewritten`** while the land's walk had found nothing. The walk
  compared the landed `history_head` (seq 3, the close) against every commit in the range — and the range holds
  card 0004's draft commit with its one entry, because the cursor sits behind the head while nothing merges. The
  land was clean only because the head it compared against predated the card. An older commit has fewer entries
  and is not a rewrite; only an entry at the landed seq with another `h` is. Fixed in **PR #43** (`l4b`), with a
  test that fails without it.
- **Finding 2, from that test: the empty diff ignored the documents.** A ratification with no run report never
  landed its head — the card would read `ratified (pending-ingest)` until an event happened to arrive. Every
  card's `history_head` is now an input of the empty diff (the same PR).
- **Finding 3, the owner's: the forge squash-merges.** X2's cursor is *"the batch PR's merge commit"*, observed as
  a merge on the first-parent line; a squash is a plain commit, so nothing has moved tenant #0's cursor since the
  first land, and every land walks the whole range since it — bounded today (a dozen commits), unbounded in
  principle. Recorded in the chunk plan as Q-W10.
- **The L4b image** (`813eb8fe339c`, `:l4b`, built from PR #43's tree as K12b's was) went up the same way — healthy
  in 32 s — and the report landed a third time: `e3`, `s3`, commit **`9fb8f37`**, the map still empty; `isidium
  check 4` now answers `integrity: []`, agreeing with the land.

### L4c, L5 and V1 live on tenant #0 in one image swap: the cursor moves at a clean land, the block is read, the first payload is assembled — 2026-09-11

- **One image for three chunks.** PRs #45 (L4c), #46 (L5) and #49 (V1) merged in that order; the image built from
  `main` at `7cadb0f` is `isidium-store:v1` (`a8737ac428ac`). Tenant #0 was recreated on it from the deploy home's
  `recreate.sh` — **which had dropped the healthcheck** the compose file carries (it was transcribed from `podman
  inspect`'s `CreateCommand`, and the health flags are not part of that line): the first recreate ran with no
  health state at all, `podman ps` showed `Up` without `(healthy)`, and the script's own `{{.State.Health.Status}}`
  template failed on the nil. The script now passes `--health-cmd python3 /usr/local/bin/isidium-healthcheck
  --health-interval 30s --health-timeout 5s --health-retries 3 --health-start-period 60s` (the compose values) and
  guards the template; the second recreate reported healthy in 35 s. The VM's `eth0` read mtu 1420 at the time and
  the clone came up regardless — the `isidium-mtu1400` network caps the container's own interface.
- **L4c's land (Q-W9, Q-W10 (a)).** The synthetic report landed as `e4`/`s4`, commit **`f70a371`**, journal seq 13,
  and the cursor moved off `68ffb68` — where it had sat since L2 — to **`7cadb0f`**, the head of `main` at a clean
  walk. A second land of the same report landed again (`e5`/`s5`, `96f3023`, seq 14) and the cursor moved to
  `f70a371`, the first land's own commit. `isidium check 4` answers `integrity: []`, chain `ok` ×3. **A finding for
  V3:** the store lands a report whose `run_id` it has already landed (`r-synthetic-1`, twice) — idempotence by
  run id is the ledger's to hold (*"no record, no run"*), not the store's, and the ledger is V3's.
- **L5's block.** `isidium show neighborhood 4 --text` answers the delimited block with every list empty and
  `truncated=false`: card 0004 has no parent, siblings or dependencies, and that is the honest answer.
- **V1's payload, the first real number.** `isidium factory payload --tenant isidium-factory --checkout
  C:/Dev/isidium-factory --card 4 --bot lander@isidium-factory --adapter none --max-bytes 1048576` at `main`
  `96f3023`: **`payload_hash sha256:e30f855f…`**, **157,288 bytes**, the same hash on a second run; two refs
  resolved (`client/accept.py` 6,412 bytes of excerpt, `docs/design/03-card-schema.md` 142,209 — a whole-file `Path`
  ref to the schema is nine tenths of the payload); `context` `{depth 2, bytes 89, cards [], truncated false}`;
  `config_hash sha256:3f4adb2c…` equal to `config.toml`'s policy-chain head `build`; the deny set the effective
  config's six paths; `effort default`, no budget (none is named). The value is kept at the deploy home
  (`factory/payload-0004.json`, outside git). Q-V8 (the byte cap's home) now has its first datum: 157 KB for a card
  citing one design document whole.
- **A forge trap, new:** PR #48 was opened with its base on #46's branch so the diff read cleanly; when #46 merged
  and its branch was deleted, GitHub **closed** #48 rather than retargeting it, and a closed PR's base cannot be
  changed. The branch was rebased onto `main` and reopened as #49 (the same two commits; green on all seven checks
  both times). Base a PR on `main`, or merge the base first.

### The factory's forge identity — a machine account, its token a file beside the lander's — 2026-09-10 (V2)

The lander is the factory's identity **to the store** (a grant on a client certificate, above). The factory's identity
**to the forge** — the account it pushes branches and opens pull requests as — is a second thing, ruled 2026-09-10
(Q-V9 (a), Q-V10): a **machine account**, one per tenant repository, a collaborator with write, and a fine-grained
token scoped to that repository; the token in a file beside the lander's, mounted read-only where the factory runs.
Two credentials, two parties, and neither is the store's deploy key: that key bypasses the gate on `main` (S-12) and
the factory must never hold it. The account's pushes are gated like a human's — `main` refuses them, a pull request
carries them, the required checks run on them — and revoking the token stops the factory's pushes and nothing else.

```
<deploy home>/<tenant>/factory/forge.toml    # login, name, email, and the token file's path (relative to this file)
<deploy home>/<tenant>/factory/forge.token   # one line: the token; 0600; never in client.toml, never in git
```

**The recipe** (the local tier; on the realm tier the realm writes the two files):

```sh
# 1. The account (a person's hand, on the forge): a GitHub user for the factory — its name is the tenant's choice —
#    then, as the repository owner, a collaborator invitation with write, which the account accepts:
gh api -X PUT repos/<owner>/<repo>/collaborators/<login> -f permission=push
# 2. The token, minted while signed in AS THE ACCOUNT: Settings → Developer settings → Fine-grained tokens; resource
#    owner = the repository's owner (an organisation must allow fine-grained tokens for it to appear); repository
#    access = only <repo>; permissions: Contents read-and-write, Pull requests read-and-write, Checks read,
#    Metadata read (automatic). Nothing else — no Administration, no Workflows.
# 3. The two files. The email is the account's noreply address — the form the forge attributes commits by; tenant
#    #0's ruleset holds a pull request whose commits no account claims (`require_extra_approval_for_unattributed_changes`):
id=$(gh api users/<login> --jq .id)
printf '%s
' 'login = "<login>"' 'name = "<login>"' "email = \"${id}+<login>@users.noreply.github.com\""   'token = "forge.token"' > <deploy home>/<tenant>/factory/forge.toml
printf '%s
' '<the token>' > <deploy home>/<tenant>/factory/forge.token && chmod 600 <deploy home>/<tenant>/factory/forge.token
```

**The verbs** (`ISIDIUM_DEPLOY=<deploy home>`, the checkout a clone of the tenant repository with `origin` the forge):

- `isidium factory context --tenant <tenant> --checkout <path>` — the tenant context (T-C1): one delta fetch of
  `main`, the config read at the fetched tip, the toolkit pin checked against the range this factory reads, the
  governed rows resolved; printed with its hash, and the same hash twice is the round trip. The token is in it nowhere.
- `isidium factory push --tenant <tenant> --checkout <path> --branch <name> [--at <sha>]` — the branch pushed as the
  account, **after** the code-only check: a governed path in `main...<name>` is refused (`forge.governed-path`, every
  path named) before any push, by the same predicate the pre-commit hook and `verify --diff-base` run. The token
  reaches git through the process environment (`GIT_CONFIG_*`, an `http.<host>.extraheader`), never the command line.
- `isidium factory pr-open --tenant <tenant> --checkout <path> --branch <name>` — the pull request, its body
  generated from the context and the diff, opened as the account; a second run answers `forge.pr-exists` with the
  number, not a second pull request.
- `isidium factory pr-status --tenant <tenant> --checkout <path> --pr <n>` — the merge state (GitHub's own closed set)
  and the checks on the head, the verdict read over the contexts **the ruleset requires**, not over whatever ran.

The driver declares what it has and has not (T-C7's capability matrix): fetch, push a branch, open a pull request,
read checks, read merge state — and **no merge** (the pull request's merge stays the forge's button, the owner's), no
force push, no branch-protection setup (this recipe's), no path rules (refused on the Free plan, measured), no
webhooks, no account provisioning, no signed-commit status. A forge API that is down is retried three times with
backoff (1, 2, 4 s) and then refused `forge.unavailable`; an exhausted rate limit is refused at once, naming the reset.

## What is not here yet

- **Compose was verified with `podman-compose` 1.6.0, not with Docker Compose.** `podman compose` needs a provider
  installed and this workstation had none, so one was used from a throwaway virtualenv. Everything it *runs* —
  the environment, the volumes, the ports, the healthcheck — was exercised; what it **builds** was not, because
  `--build` fails there for the reason above. The `docker compose` path is written down and unexercised.
- **`ISIDIUM_ORIGIN` over SSH against a real forge is now verified** (tenant #0, above): the clone through the
  pinned host key and the push with the deploy key. The `file://` path remains what the walkthrough above shows,
  and a mounted path still needs git told that the mount is trustworthy (`safe.directory`). **The egress allowlist
  is untested** — so far the container has reached whatever it asked for.
- **Revoking a caller** is editing `registration.json` — no restart since K6 (the store re-reads it). There is still no
  certificate-revocation check against the CA: the registration is the revocation list, by design, until the realm.
- **The realm.** When agent-station's identity system exists, `registration.json` is replaced by a lookup against
  it — one function in `server/service.py`. Nothing above that function changes.
