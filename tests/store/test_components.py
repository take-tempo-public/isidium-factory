"""The store's components on their own: the real git repo (a throwaway clone with a bare remote), the journal's
crash replay, the remote-totp client half against the dev stub, and the software key's persistence."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from isidium.store.core import chain
from isidium.store.core.grammar import Document
from isidium.store.core.refusal import Refusal
from isidium.store.server.gitrepo import GitCli, blob_id
from isidium.store.server.journal import Journal
from isidium.store.server.signer import DevStubService, RemoteTotp, SoftwareKey, SoftwareKeyAck
from isidium.store.server.store import NewCard, Store

from .conftest import BASE_SCOPE, OWNER, PLANNER, REGISTRY, Clock, base_head, tenant_checkout


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, check=True, text=True).stdout


@pytest.fixture
def repo(tmp_path: Path) -> GitCli:
    """The store's own repository: a **partial bare clone** of the tenant's remote (K4).

    The seeding still happens through a working tree, because that is how a tenant's repository comes to exist; what
    changed is that the store no longer holds one. It clones the bare remote, filtered.
    """
    tenant_checkout(tmp_path)
    return GitCli.clone(
        tmp_path / "origin.git", tmp_path / "store.git", "isidium-store", "store@sartor", root="docs/work/"
    )


def test_gitcli_end_to_end(repo: GitCli, tmp_path: Path) -> None:
    """A real store over a real bare clone: init, a draft, a signed ratification — every write one commit on main,
    pushed; the blob ids the journal recorded are git's; the reconciliation explains every commit.

    **Every assertion that used to read the working tree now reads the tree object**, which is the K4 change stated
    as a test: `repo.read(path)` and `ls-tree` replace `Path.is_file()` and `hash-object` on a file, because there
    is no file. The properties asserted are the same ones.
    """
    clock = Clock(1_787_000_000)
    key = SoftwareKey.generate()
    signer = SoftwareKeyAck(key, clock)
    journal = Journal(tmp_path / "journal.sqlite", "sartor")
    st = Store("sartor", repo, journal, REGISTRY, clock, signer, root="docs/work/")
    st.init(OWNER, software_key_ack="ok for now", root="docs/work/")
    assert repo.read("docs/work/config.toml") is not None
    r = st.write(NewCard("first"), Document(base_head(0, "draft"), {"Scope": BASE_SCOPE}), None, None, PLANNER)
    assert r.id == 1 and repo.read("docs/work/cards/0001-first.md") is not None
    st.ratify([1], OWNER)
    # git's own object id for the committed blob equals the journal's after_blob
    git_oid = repo.oid_of("docs/work/cards/0001-first.md")
    card_row = next(p for p in journal.rows()[-1]["paths"] if p["path"] == "cards/0001-first.md")
    assert card_row["after_blob"] == git_oid == blob_id(st.raw["cards/0001-first.md"], repo.object_format)
    # author = the caller, committer = the store identity — `commit-tree` carries both by environment now
    log = _git(repo.gitdir, "log", "-1", "--format=%an <%ae>|%cn <%ce>|%s")
    assert log.strip() == "amodal1 <amodal1@example>|isidium-store <store@sartor>|batch-manifest"
    # pushed to the remote's main
    assert _git(repo.gitdir, "rev-parse", "HEAD").strip() == _git(tmp_path / "origin.git", "rev-parse", "main").strip()
    assert st.check(1)["integrity"] == []
    assert repo.first_parent_walk(None)[-1] == repo.head
    # a second store over the same clone and journal reloads the same state
    st2 = Store(
        "sartor",
        GitCli(repo.gitdir, "isidium-store", "store@sartor", push=True, root="docs/work/"),
        Journal(tmp_path / "journal.sqlite", "sartor"),
        REGISTRY,
        clock,
        signer,
        root="docs/work/",
    )
    assert st2.show(1)[1] == st.show(1)[1] and st2.policy[-1]["h"] == st.policy[-1]["h"]


def test_journal_replays_a_half_applied_write(tmp_path: Path) -> None:
    from isidium.store.server.gitrepo import MemGit

    clock = Clock(1_787_000_000)
    signer = SoftwareKeyAck(SoftwareKey.generate(), clock)
    journal = Journal(tmp_path / "j.sqlite", "t")
    repo = MemGit()
    st = Store("t", repo, journal, REGISTRY, clock, signer, root="docs/work/")
    st.init(OWNER, software_key_ack="ok")
    # simulate the crash: a row with pending bytes whose commit never happened
    current = repo.read("docs/work/config.toml")
    assert current is not None
    replayed = b"# replayed after a crash" + bytes([10]) + current  # a leading comment: legal, byte-different
    with journal.transaction():
        row = journal.append(
            st.now(),
            OWNER.principal,
            [{"path": "config.toml", "after_blob": "x"}],
            credential=None,
            trace=None,
            pending={"config.toml": replayed},
        )
    assert journal.pending_rows()[0][0] == row["seq"]
    Store("t", repo, journal, REGISTRY, clock, signer, root="docs/work/")  # loading replays
    assert journal.pending_rows() == [] and repo.read("docs/work/config.toml") == replayed


def test_remote_totp_client_half() -> None:
    clock = Clock(1_787_000_000)
    key = SoftwareKey.generate()
    service = DevStubService(key, clock, approve_after=2)
    sleeps: list[float] = []
    client = RemoteTotp(service, key.public.key_fpr, poll_interval_ms=250, timeout_s=10, sleep=sleeps.append)
    sig = client.sign("sartor", "sha256:" + "ab" * 32, clock.t, [(1, "ratified", "sha256:00", None)])
    assert chain.verify_sig(sig, "sartor", "sha256:" + "ab" * 32) and len(sleeps) == 2
    assert service.received[-1] == [(1, "ratified", "sha256:00", None)]  # the service renders what it RECEIVED
    declined = DevStubService(key, clock, decline=True)
    with pytest.raises(Refusal, match=r"signer\.declined"):
        RemoteTotp(declined, key.public.key_fpr, poll_interval_ms=250, sleep=sleeps.append).sign(
            "sartor", "v", clock.t, []
        )
    skewed = DevStubService(key, lambda: clock.t + 100_000)
    # `poll_interval_ms` has no code-side default any more (C-1, K1c) — a caller supplies it, and the honest
    # source for a caller that wants "whatever is declared" is the registry, not a literal repeated here.
    declared_ms = REGISTRY.defaults_of("config@1")["signer"]["remote-totp"]["poll_interval_ms"]
    with pytest.raises(Refusal, match=r"signer\.time-skew"):
        RemoteTotp(skewed, key.public.key_fpr, declared_ms, sleep=sleeps.append).sign("sartor", "v", clock.t, [])


def test_software_key_round_trips_and_fpr_is_the_key(tmp_path: Path) -> None:
    key = SoftwareKey.generate()
    key.save(tmp_path / "owner.pem")
    again = SoftwareKey.load(tmp_path / "owner.pem")
    assert again.public.key_fpr == key.public.key_fpr and len(key.public.key_fpr) == 64
    assert chain.PublicKey.from_fpr("ed25519", key.public.key_fpr) == key.public
    sig = SoftwareKeyAck(again).sign("t", "sha256:00", SoftwareKeyAck(again).clock(), [])
    assert chain.verify_sig(sig, "t", "sha256:00")
