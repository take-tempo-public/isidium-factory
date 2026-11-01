"""The signing service's remaining gaps (card 75; r-63 F2-F6): init pins the file key, the timeout leaves a
post-signature margin, the entrypoint refuses a partial setting, no source calls the timeout a bound on one call, and
the README says which acts wait for the phone.

Five scenarios, one test each. The store ones run on the components card 54's tests use (`test_remote_signer.py`, whose
helpers are imported rather than copied); the deploy ones read the files an operator reads, and run the entrypoint
under `sh` — there is no skip, so an environment without `sh` fails rather than passes (C8).
"""

from __future__ import annotations

import inspect
import os
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from isidium.store.client import cli as cli_mod
from isidium.store.client.transport import Transport
from isidium.store.core import chain
from isidium.store.core.refusal import Refusal
from isidium.store.server import http as http_mod
from isidium.store.server.api import Api
from isidium.store.server.gitrepo import GitCli, MemGit
from isidium.store.server.journal import Journal
from isidium.store.server.service import Service
from isidium.store.server.signer import DevStubService, HttpsService, RemoteTotp, SoftwareKey, SoftwareKeyAck
from isidium.store.server.store import POST_SIGNATURE_MARGIN_S, Store

from ..signer.test_service import Rig as ServiceRig
from ..signer.test_service import rig as rig  # the fixture, re-exported: a real listener with minted certificates
from .conftest import OWNER, REF_FILES, REGISTRY, Clock, store_on_disk, tenant_checkout
from .test_remote_signer import EXTRA, POLL_MS, ROOT, TENANT, WAIVER, Ticker, serve_args, signed_by

REPO = Path(__file__).resolve().parents[2]


# ---- S1: init signs the genesis with the pinned file key -----------------------------------------------------------


def holding_the_service() -> tuple[Store, SoftwareKeyAck, RemoteTotp, DevStubService]:
    """`serve`'s construction up to `use_signer`, with identity disabled so the pin is derived: the file key is the
    store's signer, the service is added, and only then does the tenant get initialized — the order the old README
    told an operator to avoid."""
    clock = Clock(1_787_000_000)
    file = SoftwareKeyAck(SoftwareKey.generate(), clock, time_skew_s=600)
    repo = MemGit()
    repo.commit(dict(REF_FILES), "seed@example", "2026-08-01T00:00:00Z", "seed the ref targets")
    st = Store(
        TENANT,
        repo,
        Journal(":memory:", TENANT),
        REGISTRY,
        clock,
        file,
        root=ROOT,
        software_fprs=frozenset({file.key_fpr}),
    )
    stub = DevStubService(SoftwareKey.generate(), clock)
    ticker = Ticker()
    remote = RemoteTotp(
        stub, stub.key_public_fpr, POLL_MS, timeout_s=600, sleep=ticker.sleep, monotonic=ticker.monotonic
    )
    st.use_signer(remote)
    assert st.signer is remote  # the premise: the service is the default, which is what init used to sign with
    return st, file, remote, stub


@pytest.mark.parametrize("extra", [EXTRA, None], ids=["both-backends-declared", "file-key-alone-declared"])
def test_init_signs_with_the_pinned_file_key(extra: dict[str, Any] | None) -> None:
    st, file, remote, stub = holding_the_service()
    args: dict[str, Any] = {"software_key_ack": WAIVER}
    if extra is not None:
        args["extra"] = extra
    Api(st).call("init", OWNER, args)

    assert st.config_tree["ratification"]["pin"] == "ed25519:" + file.key_fpr
    assert signed_by(st) == file.key_fpr
    assert stub.requests == {} and remote.calls == 0  # the phone was never asked
    assert file.calls == 1
    entry = st.policy[0]
    assert chain.verify_sig(entry["sig"], TENANT, entry["h"])


def test_init_refuses_rather_than_fall_back_to_the_service() -> None:
    clock = Clock(1_787_000_000)
    stub = DevStubService(SoftwareKey.generate(), clock)
    remote = RemoteTotp(stub, stub.key_public_fpr, POLL_MS)
    st = Store(TENANT, MemGit(), Journal(":memory:", TENANT), REGISTRY, clock, remote, root=ROOT)
    assert st.signer is remote
    with pytest.raises(Refusal) as e:
        st.init(OWNER, software_key_ack=WAIVER)
    assert e.value.rule == "init.no-ratifier"
    assert stub.requests == {} and remote.calls == 0


# ---- S2: a timeout past the margin is refused at serve -----------------------------------------------------------


def test_serve_refuses_a_timeout_that_leaves_no_margin(
    tmp_path: Path, rig: ServiceRig, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout = tenant_checkout(tmp_path)
    journal = tmp_path / "journal.db"
    store_on_disk(checkout, journal).init(OWNER, software_key_ack=WAIVER, extra=EXTRA)
    bare = tmp_path / "serve.git"
    GitCli.clone(tmp_path / "origin.git", bare, "isidium-store", f"store@{TENANT}", root=ROOT)
    key_file = tmp_path / "file-key.pem"
    SoftwareKey.generate().save(key_file)

    built: list[Service] = []

    async def serve_forever(service: Service, *_: Any) -> None:
        built.append(service)

    monkeypatch.setattr(http_mod, "serve_forever", serve_forever)
    monkeypatch.setattr(http_mod, "tls_context", lambda *_: None)

    # C1: the margin comes out of the accepted maximum; the channel and the owner's wait are not touched
    channel = float(inspect.signature(Transport.__init__).parameters["timeout"].default)
    wait = float(inspect.signature(RemoteTotp.__init__).parameters["timeout_s"].default)
    assert (channel, wait) == (660.0, 600.0)
    assert POST_SIGNATURE_MARGIN_S > 0
    top = channel - wait - POST_SIGNATURE_MARGIN_S

    for refused in (top + POST_SIGNATURE_MARGIN_S / 2, top):
        res = CliRunner().invoke(
            cli_mod.app, serve_args(tmp_path, rig, journal, bare, key_file, whole=True, call_timeout=str(refused))
        )
        assert res.exit_code == 2 and "signer.service-options" in res.output, (refused, res.output)
        assert built == []

    accepted = top - 1
    res = CliRunner().invoke(
        cli_mod.app, serve_args(tmp_path, rig, journal, bare, key_file, whole=True, call_timeout=str(accepted))
    )
    assert res.exit_code == 0, res.output
    (service,) = built
    remote = service.api.store.signer
    assert isinstance(remote, RemoteTotp)
    assert isinstance(remote.service, HttpsService) and remote.service.timeout_s == accepted


# ---- S3: no source calls the timeout a bound on one call -----------------------------------------------------------

ONE_CALL = re.compile(r"one call['’]s (bound|timeout)", re.IGNORECASE)


def one_call_phrases(*roots: Path) -> list[str]:
    """`path:line` of every line under the roots that calls a timeout 'one call's bound' or 'one call's timeout'.
    Every regular file is read (a help text, a docstring and a shell message are all sources); bytes that are not
    UTF-8 are replaced, not skipped, so a stray file cannot hide a phrase."""
    hits: list[str] = []
    for root in roots:
        for path in sorted(root.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            text = path.read_bytes().decode("utf-8", errors="replace")
            hits += [f"{path}:{n}" for n, line in enumerate(text.splitlines(), 1) if ONE_CALL.search(line)]
    return hits


def test_no_source_calls_the_timeout_a_one_call_bound(tmp_path: Path) -> None:
    assert one_call_phrases(REPO / "packages", REPO / "deploy") == []

    # the checker is not vacuous: it names a planted phrase in either spelling, in a Python and a shell source
    (tmp_path / "packages").mkdir()
    (tmp_path / "deploy").mkdir()
    py = tmp_path / "packages" / "x.py"
    sh = tmp_path / "deploy" / "y.sh"
    py.write_text('help="one call\'s timeout to the service"\n', encoding="utf-8")
    sh.write_text('# fine\nfail "is one call’s bound"\n', encoding="utf-8")
    hits = one_call_phrases(tmp_path / "packages", tmp_path / "deploy")
    assert hits == [f"{py}:1", f"{sh}:2"]


# ---- S4: the entrypoint refuses a partial service setting ----------------------------------------------------------


def run_entrypoint(tmp_path: Path, **service: str) -> subprocess.CompletedProcess[str]:
    """The entrypoint under `sh` with a from-scratch environment: the three decisions, paths that exist nowhere, and
    whatever `ISIDIUM_SIGNING_SERVICE_*` the caller sets. It stops at the first refusal, so nothing is cloned."""
    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(tmp_path),
        "TENANT": TENANT,
        "ISIDIUM_ORIGIN": "file:///nonexistent",
        "ISIDIUM_ROOT": ROOT,
        "ISIDIUM_TLS_DIR": str(tmp_path),
        "ISIDIUM_REGISTRATION": str(tmp_path / "absent.json"),
        "ISIDIUM_STATE_DIR": str(tmp_path / "state"),
        **{f"ISIDIUM_SIGNING_SERVICE_{k}": v for k, v in service.items()},
    }
    return subprocess.run(
        ["sh", str(REPO / "deploy" / "entrypoint.sh")],
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_the_entrypoint_refuses_a_partial_service_setting(tmp_path: Path) -> None:
    for name, value in (("PORT", "8443"), ("FPR", "ab" * 32), ("TIMEOUT_S", "10")):
        res = run_entrypoint(tmp_path, **{name: value})
        assert res.returncode == 2, (name, res.stderr)
        assert f"ISIDIUM_SIGNING_SERVICE_{name} is set" in res.stderr, res.stderr
        assert "ISIDIUM_SIGNING_SERVICE_HOST" in res.stderr, res.stderr
        assert "no registration" not in res.stderr, res.stderr  # it stopped at the check, not further on

    # positive controls: with the host, or with none of them, the run gets past the check to the next refusal
    for service in ({"HOST": "signer.example.invalid", "PORT": "8443"}, {}):
        res = run_entrypoint(tmp_path, **service)
        assert res.returncode == 2 and "no registration" in res.stderr, (service, res.stderr)

    compose = " ".join((REPO / "deploy" / "compose.yaml").read_text(encoding="utf-8").split())
    assert "without ISIDIUM_SIGNING_SERVICE_HOST" in compose


# ---- S5: the README lists every act that waits for the phone ---------------------------------------------------------

WAITING_ACTS = (
    "born-ratified write",
    "config-policy write",
    "a repair",
    "accept --close",
    "releasing a hold",
    "owner status move",
    "gated edit to a ratified card",
)


def test_the_readme_lists_every_act_that_waits() -> None:
    readme = (REPO / "deploy" / "README.md").read_text(encoding="utf-8")
    start = readme.index("### The store's half")
    end = readme.index("\n### ", start + 1)
    section = " ".join(readme[start:end].split())
    for phrase in (*WAITING_ACTS, "unverified", "card 56"):
        assert phrase in section, phrase
