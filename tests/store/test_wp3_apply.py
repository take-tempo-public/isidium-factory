"""The WP3 review's apply pass (sync 7bf.9): every finding that had no test gets one — S1 the two supported
deployment shapes and no third, S3 the store's commit carries a pathspec, S4 the signer sees what it approves,
S5 the hook uses the root `init` recorded, S6 a malformed governed file is reported not fatal, C4 dispositions are
the owner's, C5 the installed registry is what a checkout validates against."""

from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path

import pytest

from isidium.store.client import hook as hook_mod
from isidium.store.client.config import ClientConfig
from isidium.store.client.install import install
from isidium.store.core.grammar import parse_config
from isidium.store.core.refusal import Refusal
from isidium.store.registry.config import CONFIG_ORDERS, resolve_effective
from isidium.store.registry.loader import Registry
from isidium.store.server.api import Api
from isidium.store.server.gitrepo import GitCli
from isidium.store.server.identity import GRANT_MATRIX, allowed
from isidium.store.server.service import Registration, Request, Service
from isidium.store.server.signer import SoftwareKeyAck
from isidium.store.server.store import Store

from .conftest import BASE_SCOPE, OWNER, PLANNER, Harness, base_head, store_on_disk, tenant_checkout
from .test_service import CLOCK, OWNER_CERT, PLANNER_CERT, call, cert_for


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, check=True, text=True).stdout


@pytest.fixture
def tenant(tmp_path: Path) -> Path:
    return tenant_checkout(tmp_path)


def owner_cfg(root: str = "docs/work/") -> ClientConfig:
    """The client file `install` writes. It names no principal, no grant and no signing key since K3: the caller is
    the certificate on the connection, and the key is the store's."""
    return ClientConfig(
        tenant="sartor",
        root=root,
        address="https://store.sartor:8443",
        ca=".isidium/tenant-ca.pem",
        cert=".isidium/owner.crt.pem",
        key=".isidium/owner.key.pem",
    )


def initialized(tenant: Path, root: str = "docs/work/") -> Store:
    """The client-side install, and a store over the same checkout with its policy chain opened (7bg.2: *"tests
    construct `Store` directly"*).

    These tests are about what the **store** does — the pathspec on its commit, what its signer is shown, a planted
    file under a governed path — and they used to reach it by asking `open_transport` for a local one. That door is
    gone; `install.init` opens the chain over the channel now, which `test_channel.py` proves end to end.
    """
    install(tenant, owner_cfg(root))
    store = store_on_disk(tenant, tenant.parent / "journal.sqlite", root=root)
    store.init(OWNER, software_key_ack="ok for the bridge", root=root)
    return store


# ---- S1: the caller is the certificate on the connection, and nothing else ---------------------------------------


def test_s1_the_caller_is_the_connection_certificate(svc_pair: tuple[Service, Harness]) -> None:
    """After 7bg.8 the store terminates its own mTLS, so there is one shape and no third: the certificate comes off
    the connection. A call with none is the store's own misconfiguration (the handshake should have refused first);
    a certificate the registration does not name is a refused caller, not an anonymous one.

    That the handshake actually refuses an uncertificated, wrong-CA or expired peer *before* any of this runs is
    proved over a real socket in `test_edge.py` — it cannot be proved here, and is not claimed here."""
    service, _hz = svc_pair
    status, body = call(service, "show", {"target": "queue"}, None)
    # The rule id and nothing else: `auth.*` is pre-identification and therefore terse (C-12, built by K2b). The
    # `CERT_REQUIRED` sentence this line used to read out of `detail` is a deployment diagnosis and now reaches the
    # operator on stderr instead of the peer — `test_telemetry.py` holds both halves of that.
    assert (status, body) == (401, {"rule": "auth.no-client-certificate"})
    status, body = call(service, "show", {"target": "queue"}, cert_for("stranger@example.com"))
    assert (status, body) == (403, {"rule": "auth.unknown-client"})
    assert call(service, "show", {"target": "queue"}, PLANNER_CERT)[0] == 200


def test_s8_health_publishes_nothing(svc_pair: tuple[Service, Harness]) -> None:
    service, hz = svc_pair
    response = service.handle(Request("GET", "/health", b""), service.registration.credential(None))
    assert json.loads(response.body) == {"ok": True} and hz.st.tenant not in response.body.decode()


@pytest.fixture(scope="module")
def svc_pair() -> tuple[Service, Harness]:
    from .conftest import fresh

    hz = fresh("wp3")
    reg = Registration(
        {
            "CN=owner@example": ("amodal1@example", "owner"),
            "CN=sartor-planner@agents.example": ("sartor-planner@agents.example", "contributor"),
        },
        CLOCK,
    )
    return Service(Api(hz.st), reg, hz.st.tenant), hz


# ---- S3: the store's commit carries a pathspec -------------------------------------------------------------------


def test_s3_a_staged_file_does_not_ride_the_stores_commit(tenant: Path) -> None:
    """Anything a caller had staged must NOT reach `main` inside the store's own commit.

    **K4 turned this from guarded into impossible, and the test says which.** The old store shared this working
    tree, so `git commit` without a pathspec would have swept the caller's staged `evil.py` onto `main` past the
    hook, the batch PR and CI; `--only -- <paths>` was the guard. The store now holds a partial bare clone: there is
    no index to leak into and no working tree to stage from, and the commit is a tree the store composed itself out
    of `HEAD`'s entries plus exactly the blobs this write hashed. So the assertion moves to the store's own
    repository — the commit touches exactly the written path — and gains the structural half beneath it.
    """
    store = initialized(tenant)
    (tenant / "evil.py").write_text("import os\n", encoding="utf-8")
    git(tenant, "add", "evil.py")
    head = base_head(0, "draft")
    head.pop("id")
    Api(store).call("write", OWNER, {"new_slug": "a-card", "document": {"head": head, "scope": BASE_SCOPE}})
    sha = store.repo.head
    assert sha is not None and sorted(store.repo.touched(sha)) == ["docs/work/cards/0001-a-card.md"]
    assert "evil.py" in git(tenant, "diff", "--cached", "--name-only")  # still staged, still the caller's business
    # the structural half: nothing to sweep, because there is no index and no working tree in the store's repository
    assert isinstance(store.repo, GitCli)
    assert not (store.repo.gitdir / "index").exists()
    assert git(store.repo.gitdir, "rev-parse", "--is-bare-repository").strip() == "true"


# ---- S4: the signer is shown what it is approving ----------------------------------------------------------------


def test_s4_a_single_signed_act_shows_the_diff(tenant: Path) -> None:
    store = initialized(tenant)
    api = Api(store)
    signer = store.signer
    assert isinstance(signer, SoftwareKeyAck)
    head = base_head(0, "draft")
    head.pop("id")
    cid = api.call("write", OWNER, {"new_slug": "held-card", "document": {"head": head, "scope": BASE_SCOPE}})["id"]
    api.call("ratify", OWNER, {"ids": [cid], "dry_run": False})
    store.write_set(cid, ['hold.kind="blocked"', "hold.on.owner=true"], OWNER)
    store.write_set(cid, ["hold="], OWNER)  # a signed `released` — an act on an already-signed card
    shown = signer.shown[-1][0]
    assert shown[1] == "released" and shown[3] is not None, shown
    # C1(b): the acts since the signature — the signer sees the hold that was set and is now being released
    assert [e[1] for e in shown[3]["entries_since"]] == ["held"], shown[3]
    # a policy act shows the keys it moves
    tree = copy.deepcopy(store.config_tree)
    tree["wip"] = 2
    store.write("config.toml", tree, {"seq": store.policy[-1]["seq"], "h": store.policy[-1]["h"]}, None, OWNER)
    assert signer.shown[-1][0][3]["gated"] == ["wip"]


# ---- S5: the hook uses the root `init` recorded -------------------------------------------------------------------


def test_s5_the_hook_follows_a_tenant_chosen_root(tenant: Path) -> None:
    initialized(tenant, root="work/")
    root, rows = hook_mod.governed_paths(tenant)
    assert root == "work/" and any(r["path"] == "cards/*.md" for r in rows)
    assert hook_mod.offending(tenant, ["work/cards/0001-x.md", "src/a.py"]) == ["work/cards/0001-x.md"]
    (tenant / "work" / "cards").mkdir(parents=True, exist_ok=True)
    (tenant / "work" / "cards" / "0001-x.md").write_text("planted\n", encoding="utf-8")
    git(tenant, "add", "-f", "work/cards/0001-x.md")
    assert hook_mod.check(tenant) == 1


def test_the_hook_refuses_rather_than_guessing_a_root(tmp_path: Path) -> None:
    """S5 again, and C-1 with it. The hook used to return `"docs/work/"` when it could find no configured root —
    `config@1`’s own declared default, written a second time in the binary, and invisible to the C-1 sweep because a
    bare `return` is not an absent-key fallback (measured 2026-08-29). The consequence was the defect S5 named: a
    checkout whose root is elsewhere got a hook that protected nothing, and said nothing about it.

    The discriminator is the rule id and a non-zero exit — not merely "no offending paths", which is what a hook
    that had silently guessed the wrong root would also report."""
    with pytest.raises(Refusal) as caught:
        hook_mod.governed_paths(tmp_path)
    assert caught.value.rule == "hook.unknown-root"
    assert hook_mod.check(tmp_path) == 1, "a hook that cannot tell what is governed let the commit through"


def test_init_records_a_concrete_root_when_none_was_chosen(tenant: Path) -> None:
    """S5's other half, and C-1 with it [K1c, 2026-08-29]. `isidium init --root` used to carry `"docs/work/"` as its
    own option default — `config@1`'s declared value, written a second time in the binary. Removing it is only half
    a fix: `ClientConfig.render` omits an empty string, and `governed_paths` reads a MISSING root back as `""`, which
    is an answer, not "unknown". So `hook.unknown-root` never fires and the hook silently guards the repo root
    instead of the tracking root — exactly the S5 silence, reached by a different door.

    So `install` resolves the root from the adopted schema version and RECORDS it. The expected value is read from
    the registry here, not written as a literal: a test that hard-codes `"docs/work/"` would keep passing after the
    declared default changed, which is the drift C-1 exists to prevent.

    The discriminator is `root == declared`, not merely that the hook runs. A hook pointed at the repo root also
    runs, reports no offending paths, and exits 0.

    It is `install` and not `init` since K3, because the resolution this is about is entirely local: `init`'s other
    half now goes over the channel, and the governed half of the same rule is asserted there
    (`test_channel.py::test_only_the_root_the_operator_chose_reaches_the_governed_file`)."""
    install(tenant, owner_cfg(root=""))

    declared = Registry.for_checkout(tenant).defaults_of("config@1")["root"]
    text = (tenant / ".isidium" / "client.toml").read_text(encoding="utf-8")
    assert f'root = "{declared}"' in text, 'init recorded no root; the hook will read `""` and guard the wrong tree'

    root, rows = hook_mod.governed_paths(tenant)
    assert root == declared and any(r["path"] == "cards/*.md" for r in rows)
    assert hook_mod.offending(tenant, [f"{declared}cards/0001-x.md", "src/a.py"]) == [f"{declared}cards/0001-x.md"]


# The other side of that coin — that the GOVERNED `config.toml` names only a root the operator actually chose —
# moved to `test_channel.py` with K3. It is a property of `install.init`, which runs over the channel now, and
# asserting it against a `Store` built here would have tested a call this code no longer makes.


def test_the_hook_and_the_store_read_the_same_manifest(tmp_path: Path) -> None:
    """C5's rule — *"a local check and the store's check cannot disagree"* — applied to the manifest itself
    [K1c, 2026-08-29]. The hook now resolves the EFFECTIVE config, which is the same call the store makes, so the
    two cannot drift apart by construction rather than by care.

    **This closes a disagreement that was live.** The hook used to read `tree.get("governed") or <the manifest
    written in the binary>`, so a `config.toml` declaring `governed = []` — *"nothing here is governed"* — got the
    full default manifest from the hook and an empty one from the store: the local check refused commits the store
    did not consider governed at all. That is a behaviour change and it is deliberate; the tenant's stated policy
    wins, and the two halves now answer the same thing.

    The third row is the one that matters and the one nothing covered before: an empty table is not an absent one."""
    reg = Registry.shipped()
    shapes = {
        "no config.toml at all": None,
        "a table of its own": 'schema = 1\ntenant = "t"\n[[governed]]\npath = "only/*.md"\nschema = "card@1"\n',
        "an explicitly empty table": 'schema = 1\ntenant = "t"\ngoverned = []\n',
    }
    seen: dict[str, list[str]] = {}
    for label, text in shapes.items():
        target = tmp_path / "config.toml"
        if text is None:
            target.unlink(missing_ok=True)
            expected = [str(r["path"]) for r in reg.defaults_of("config@1")["governed"]]
        else:
            target.write_text(text, encoding="utf-8")
            tree, _entries, _rs = parse_config(text, CONFIG_ORDERS)
            expected = [str(r["path"]) for r in resolve_effective(tree, reg)["governed"]]
        _root, rows = hook_mod.governed_paths(tmp_path, root="")
        assert [str(r["path"]) for r in rows] == expected, label
        seen[label] = expected

    assert seen["an explicitly empty table"] == [], "an empty manifest must mean empty, as it does for the store"
    assert seen["a table of its own"] == ["only/*.md"], "the tenant's own table replaces the declared default"
    assert len(seen["no config.toml at all"]) == 6, "an absent file falls back to the declared manifest"


# ---- S6: a malformed governed file is reported, never fatal --------------------------------------------------------


def test_s6_a_planted_file_does_not_brick_the_store(tenant: Path) -> None:
    store = initialized(tenant)
    head = base_head(0, "draft")
    head.pop("id")
    cid = Api(store).call("write", OWNER, {"new_slug": "real", "document": {"head": head, "scope": BASE_SCOPE}})["id"]
    # a bypass that landed: a malformed file committed under a governed path (the hook refused it, hence
    # --no-verify) and **pushed**, because with K4 "landed" means it reached the remote's `main` — the store holds
    # its own clone and a commit that never left this checkout is not a bypass it could ever see.
    git(tenant, "pull", "-q", "--ff-only", "origin", "main")
    (tenant / "docs/work/cards").mkdir(parents=True, exist_ok=True)
    (tenant / "docs/work/cards/9999-planted.md").write_text("not a card at all\n", encoding="utf-8")
    git(tenant, "add", "-f", "docs/work/cards/9999-planted.md")
    git(tenant, "commit", "-q", "--no-verify", "-m", "planted")
    git(tenant, "push", "-q", "origin", "HEAD:main")
    # a fresh store over the same REMOTE and the same journal — a restarted container, not the same object told
    # to re-read. The journal path matters: over a fresh one the card's own write is `unjournaled` and this test
    # fails for a reason that has nothing to do with the planted file.
    reopened = store_on_disk(tenant, tenant.parent / "journal.sqlite")
    assert "cards/9999-planted.md" in reopened.unreadable_paths()
    assert reopened.check(cid)["integrity"] == []  # the diagnosis still works — that is the point of `check`
    assert Api(reopened).call("show", OWNER, {"target": "board"})["markdown"].startswith("# Board")


# ---- C4 / C5 -------------------------------------------------------------------------------------------------------


def test_c4_dispositions_are_the_owners(svc_pair: tuple[Service, Harness]) -> None:
    service, hz = svc_pair
    assert not allowed("contributor", "disposition") and allowed("owner", "disposition")
    assert "disposition" not in GRANT_MATRIX["contributor"]
    r = hz.st.suggest(PLANNER, "docs", "a note", "body", source="session")
    status, body = call(
        service, "disposition", {"suggestion": r.entry["id"], "outcome": "declined", "reason": "no"}, PLANNER_CERT
    )
    assert status == 403 and body["rule"] == "write.grant"
    status, body = call(
        service, "disposition", {"suggestion": r.entry["id"], "outcome": "declined", "reason": "no"}, OWNER_CERT
    )
    assert status == 200


def test_c5_a_checkout_validates_against_the_registry_it_installed(tenant: Path) -> None:
    initialized(tenant)
    schemas = tenant / ".isidium" / "schemas"
    assert Registry.for_checkout(tenant).installed == Registry.from_directory(schemas).installed
    # the installed copy is what the client reads: remove one and the checkout's registry loses it
    (schemas / "page@1.toml").unlink()
    assert "page@1" not in Registry.for_checkout(tenant).installed
    assert "page@1" in Registry.shipped().installed
    # a checkout with no install falls back to the shipped registry (a fresh clone before `init`)
    fresh_clone = tenant.parent / "unclaimed"
    fresh_clone.mkdir()
    assert Registry.for_checkout(fresh_clone).installed == Registry.shipped().installed
    with pytest.raises(Refusal, match=r"registry\.not-installed"):
        Registry.from_directory(fresh_clone)


def test_c1_the_v1b_verbs_name_themselves(hz: Harness) -> None:
    api = Api(hz.st)
    with pytest.raises(Refusal, match=r"api\.not-yet") as e:
        api.call("accept", OWNER, {})  # `land` left this table in L1
    assert "v1b" in str(e.value)
    with pytest.raises(Refusal, match=r"api\.unknown-call") as e2:
        api.call("teleport", OWNER, {})
    assert "the surface carries" in str(e2.value)


# S2 — *"local mode's grant and principal are self-asserted, so the file says so"* — is **closed by deletion**
# (7bg.2, K3). The finding was that the boundary could only be stated, never enforced: a file cannot enforce who is
# reading it. There is no such file any more, so there is nothing to state. The test that asserted the wording is
# replaced by `test_walk.py::test_the_client_file_no_longer_carries_an_identity`, which asserts the keys are gone
# and that a pre-K3 file is refused by name rather than loaded with its identity quietly ignored.
