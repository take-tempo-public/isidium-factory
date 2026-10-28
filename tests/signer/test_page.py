"""The signing service's code-entry page, driven over a real HTTPS listener on 127.0.0.1 with certificates minted here
(`test_service.py`'s helpers), and its container entrypoint, driven as a subprocess.

The page asks for no client certificate, so the page client below presents none. Every refusal is paired with a
positive control, as in `test_service.py`: no assertion here can pass on silence.
"""

from __future__ import annotations

import base64
import html
import http.client
import json
import os
import re
import shutil
import signal
import ssl
import subprocess
import sys
import time
import urllib.parse
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from isidium.signer import http as api_http
from isidium.signer import page, settings, totp
from isidium.signer.http import HttpsService, Listener
from isidium.signer.service import Service
from isidium.store.core import chain
from isidium.store.core.refusal import Refusal

from .test_service import (
    CALLER,
    SECRET,
    TENANT,
    VALUE,
    Authority,
    Clock,
    Leaf,
    _write_settings,
    authority,
    issue,
    wrong_code,
)

REPO = Path(__file__).resolve().parents[2]
ENTRYPOINT = REPO / "deploy" / "signer-entrypoint.sh"
SRC_DIRS = [REPO / "packages" / name / "src" for name in ("isidium-store", "isidium-factory", "isidium-signer")]
NASTY_TENANT = "<script>alert(1)</script>&\"'"
NASTY_VALUE = "sha256:<img src=x onerror=alert(2)>&\"'"
# A display entry no card could produce (C1): the page must show what it received, not what it could look up.
NASTY_DISPLAY: list[object] = [{"id": 99999, "act": "<b>ratify</b>", "note": "a&b \"c\" 'd' <script>x</script>"}]


PAGE_TABLE = '\n[page]\nhost = "127.0.0.1"\nport = 0\ntls_certificate = "page.crt.pem"\ntls_key = "page.key.pem"\n'


@dataclass
class PageRig:
    directory: Path
    settings_path: Path
    cfg: settings.Settings
    page_cfg: settings.PageSettings
    clock: Clock
    service: Service
    api: Listener
    web: page.PageListener
    ca: Authority
    named: Leaf
    secret_path: Path
    state_path: Path

    def client(self) -> HttpsService:
        host, port = self.api.address
        return HttpsService(host, port, self.ca.path, self.named.cert, self.named.key, timeout_s=5.0)

    def fetch(
        self, method: str, path: str, form: dict[str, str] | None = None, listener: page.PageListener | None = None
    ) -> tuple[int, http.client.HTTPMessage, str]:
        host, port = (listener or self.web).address
        context = ssl.create_default_context(cafile=str(self.ca.path))  # and no client certificate
        conn = http.client.HTTPSConnection(host, port, context=context, timeout=5.0)
        try:
            if form is None:
                conn.request(method, path)
            else:
                body = urllib.parse.urlencode(form).encode("utf-8")
                conn.request(method, path, body, {"Content-Type": "application/x-www-form-urlencoded"})
            response = conn.getresponse()
            return response.status, response.headers, response.read().decode("utf-8")
        finally:
            conn.close()

    def snapshot(self, rids: list[str]) -> tuple[object, ...]:
        """Everything a GET could change: the request table, every poll, and the bytes of both files."""

        def raw(path: Path) -> bytes | None:
            return path.read_bytes() if path.exists() else None

        polls = [self.service.poll(CALLER, r) for r in rids]
        return (self.service.pending(), polls, raw(self.state_path), raw(self.secret_path))


def _mint(directory: Path) -> tuple[Authority, Leaf, Leaf, Leaf]:
    ca = authority(directory, "signer-test-ca")
    server = issue(directory, ca, "server", "signer.example.invalid", server=True)
    page_leaf = issue(directory, ca, "page", "page.example.invalid", server=True)
    named = issue(directory, ca, "named", "store-client")
    key = directory / "signing.pem"
    key.write_bytes(
        ed25519.Ed25519PrivateKey.generate().private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
    )
    key.chmod(0o600)
    return ca, server, page_leaf, named


def _deployment(directory: Path, *, enrolled: bool) -> tuple[Path, Authority, Leaf]:
    """Every file the service needs, and a settings file naming them with a `[page]` table."""
    ca, server, _page, named = _mint(directory)
    if enrolled:
        secret = directory / "totp.base32"
        secret.write_text(base64.b32encode(SECRET).decode(), encoding="ascii")
        secret.chmod(0o600)
    path = _write_settings(directory, ca, server)
    path.write_text(path.read_text(encoding="utf-8") + PAGE_TABLE, encoding="utf-8")
    return path, ca, named


def _build(directory: Path, *, enrolled: bool) -> PageRig:
    path, ca, named = _deployment(directory, enrolled=enrolled)
    cfg, page_cfg = settings.load(path), settings.load_page(path)
    clock = Clock()
    service = Service(cfg, clock)
    api = api_http.start(service, cfg)
    web = page.start_page(service, cfg, page_cfg)
    return PageRig(directory, path, cfg, page_cfg, clock, service, api, web, ca, named, cfg.totp_secret, cfg.state)


@pytest.fixture
def enrolled_rig(tmp_path: Path) -> Iterator[PageRig]:
    rig = _build(tmp_path, enrolled=True)
    try:
        yield rig
    finally:
        rig.web.close()
        rig.api.close()


@pytest.fixture
def open_rig(tmp_path: Path) -> Iterator[PageRig]:
    """A service with no TOTP secret on disk: enrolment is open."""
    rig = _build(tmp_path, enrolled=False)
    try:
        yield rig
    finally:
        rig.web.close()
        rig.api.close()


def _wrong_for(secret: bytes, epoch: int) -> str:
    step = totp.step_of(epoch)
    taken = {totp.hotp(secret, s) for s in range(step - 2, step + 3)}
    return next(f"{n:06d}" for n in range(10**6) if f"{n:06d}" not in taken)


# ---- S1 ------------------------------------------------------------------------------------------------------------


def test_the_page_lists_escaped(enrolled_rig: PageRig) -> None:
    rig = enrolled_rig
    client = rig.client()
    first = client.submit(NASTY_TENANT, NASTY_VALUE, rig.clock.now, NASTY_DISPLAY)
    second = client.submit(TENANT, VALUE, rig.clock.now, [])
    rids = [first, second]

    before = rig.snapshot(rids)
    status, headers, body = rig.fetch("GET", "/")
    assert status == 200  # no client certificate was presented
    for rid in rids:
        assert html.escape(rid, quote=True) in body
    # every caller string appears only in its escaped form, never as markup
    assert html.escape(NASTY_TENANT, quote=True) in body
    assert html.escape(NASTY_VALUE, quote=True) in body
    assert "<script" not in body.lower() and "<img" not in body.lower() and "<b>" not in body
    # C1: the display is the object that was received, serialised, and nothing looked up
    assert html.escape(json.dumps(NASTY_DISPLAY, ensure_ascii=False, indent=2), quote=True) in body
    assert TENANT in body and VALUE in body  # the plain request is listed too
    assert "script-src" not in headers["Content-Security-Policy"]
    assert "default-src 'none'" in headers["Content-Security-Policy"]  # A1: nothing on the page may run code
    assert headers["Cache-Control"] == "no-store"

    # a GET changes nothing -- including a GET that carries a perfectly good approval in its query string
    code = totp.code_at(SECRET, rig.clock.now)
    for path in ("/", "/", f"/approve?request_id={first}&code={code}", f"/decline?request_id={first}&code={code}"):
        status, _, _ = rig.fetch("GET", path)
        assert status == (200 if path == "/" else 404)
    assert rig.snapshot(rids) == before
    # positive control: that code was never spent, so the same code now approves through a POST
    status, _, body = rig.fetch("POST", "/approve", {"request_id": first, "code": code})
    assert status == 200 and "Approved" in body
    assert rig.service.poll(CALLER, first) is not None
    assert [v.request_id for v in rig.service.pending()] == [second]


# ---- S2 ------------------------------------------------------------------------------------------------------------


def test_approve_and_decline_need_a_code(enrolled_rig: PageRig) -> None:
    rig = enrolled_rig
    client = rig.client()
    to_approve = client.submit(TENANT, VALUE, rig.clock.now, [])
    to_decline = client.submit(TENANT, VALUE, rig.clock.now, [])
    now = rig.clock.now

    # approve: no code, then a wrong one -- refused, and the request is still pending
    status, _, body = rig.fetch("POST", "/approve", {"request_id": to_approve})
    assert status == 403 and "signer.wrong-code" in body
    status, _, body = rig.fetch("POST", "/approve", {"request_id": to_approve, "code": wrong_code(now)})
    assert status == 403 and "signer.wrong-code" in body
    assert client.poll(to_approve) is None
    # a valid code approves, and the signature is the service's over tenant and value
    status, _, body = rig.fetch("POST", "/approve", {"request_id": to_approve, "code": totp.code_at(SECRET, now)})
    assert status == 200 and "Approved" in body
    sig = client.poll(to_approve)
    assert sig is not None and chain.verify_sig(sig, TENANT, VALUE)

    # decline needs a code too: without one the request stays pending
    rig.clock.now += totp.STEP_S  # the first code's step is spent
    now = rig.clock.now
    status, _, body = rig.fetch("POST", "/decline", {"request_id": to_decline})
    assert status == 403 and "signer.wrong-code" in body
    status, _, body = rig.fetch("POST", "/decline", {"request_id": to_decline, "code": wrong_code(now)})
    assert status == 403 and "signer.wrong-code" in body
    assert client.poll(to_decline) is None
    status, _, body = rig.fetch("POST", "/decline", {"request_id": to_decline, "code": totp.code_at(SECRET, now)})
    assert status == 200 and "Declined" in body
    with pytest.raises(Refusal) as err:
        client.poll(to_decline)
    assert err.value.rule == "signer.declined"

    status, _, body = rig.fetch("POST", "/approve", {"request_id": "no-such-request", "code": "000000"})
    assert status == 403 and "signer.unknown-request" in body
    status, _, _ = rig.fetch("POST", "/elsewhere", {"code": "000000"})
    assert status == 404


# ---- S3 ------------------------------------------------------------------------------------------------------------


def test_enrolment_once(open_rig: PageRig) -> None:
    rig = open_rig
    secret_file = rig.secret_path
    assert not secret_file.exists()
    pending = rig.client().submit(TENANT, VALUE, rig.clock.now, [])

    status, _, body = rig.fetch("GET", "/")
    assert status == 200
    shown = re.search(r"<code>([A-Z2-7]+)</code>", body)
    assert shown is not None
    text = shown.group(1)
    link = re.search(r'href="(otpauth://totp/[^"]+)"', body)
    assert link is not None
    assert f"secret={text}" in link.group(1) and "digits=6" in link.group(1) and "period=30" in link.group(1)
    assert "<img" not in body.lower()  # A2: no QR code
    assert rig.fetch("GET", "/")[2] == body  # the same candidate every time, and a GET wrote nothing
    assert not secret_file.exists()
    candidate = totp.secret_from_base32(text)

    # nothing can be approved while there is no secret to check a code against
    status, _, answer = rig.fetch("POST", "/approve", {"request_id": pending, "code": "000000"})
    assert status == 403 and "signer.not-enrolled" in answer

    # a code that is not the candidate's writes nothing
    status, _, answer = rig.fetch("POST", "/enrol", {"code": _wrong_for(candidate, rig.clock.now)})
    assert status == 403 and "signer.wrong-code" in answer
    assert not secret_file.exists() and not rig.state_path.exists()

    # a code from the candidate does, and only then
    status, _, answer = rig.fetch("POST", "/enrol", {"code": totp.code_at(candidate, rig.clock.now)})
    assert status == 200 and "Enrolled" in answer
    assert secret_file.exists()
    if os.name == "posix":
        assert secret_file.stat().st_mode & 0o777 == 0o600
    assert totp.secret_from_base32(secret_file.read_text(encoding="ascii")) == candidate

    # never shown again; enrolment is not reopened from the page
    status, _, body = rig.fetch("GET", "/")
    assert status == 200 and text not in body and "otpauth" not in body
    written = (secret_file.read_bytes(), secret_file.stat().st_mtime_ns)
    status, _, answer = rig.fetch("POST", "/enrol", {"code": totp.code_at(candidate, rig.clock.now + totp.STEP_S)})
    assert status == 403 and "signer.enrolled" in answer
    assert (secret_file.read_bytes(), secret_file.stat().st_mtime_ns) == written

    # the enrolment code's step is spent: it cannot also approve; the next step's code can
    status, _, answer = rig.fetch(
        "POST", "/approve", {"request_id": pending, "code": totp.code_at(candidate, rig.clock.now)}
    )
    assert status == 403 and "signer.code-reused" in answer
    rig.clock.now += totp.STEP_S
    status, _, answer = rig.fetch(
        "POST", "/approve", {"request_id": pending, "code": totp.code_at(candidate, rig.clock.now)}
    )
    assert status == 200 and "Approved" in answer

    # a restart finds the secret on disk: enrolled, and the page shows no secret
    fresh = Service(rig.cfg, rig.clock)
    assert fresh.enrolled and fresh.enrolment_secret() is None
    web = page.start_page(fresh, rig.cfg, rig.page_cfg)
    try:
        status, _, body = rig.fetch("GET", "/", listener=web)
        assert status == 200 and text not in body and "otpauth" not in body
    finally:
        web.close()


# ---- S4 ------------------------------------------------------------------------------------------------------------


def _shell_env(directory: Path, settings_path: Path | None) -> dict[str, str]:
    """`python3` on PATH is this interpreter, and the three packages' source directories are importable: the
    entrypoint runs unchanged, as it does in the image."""
    shim_dir = directory / "bin"
    shim_dir.mkdir(parents=True, exist_ok=True)
    shim = shim_dir / "python3"
    shim.write_text(f'#!/bin/sh\nexec "{Path(sys.executable).as_posix()}" "$@"\n', encoding="utf-8")
    shim.chmod(0o755)
    env = {k: v for k, v in os.environ.items() if k != "ISIDIUM_SIGNER_SETTINGS"}
    env["PATH"] = f"{shim_dir.as_posix()}{os.pathsep}{env.get('PATH', '')}"
    env["PYTHONPATH"] = os.pathsep.join(str(p) for p in SRC_DIRS)
    if settings_path is not None:
        env["ISIDIUM_SIGNER_SETTINGS"] = str(settings_path)
    return env


def _run_entrypoint(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["sh", str(ENTRYPOINT)], env=env, capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL
    )


def test_entrypoint_refuses_missing_files(tmp_path: Path) -> None:
    if shutil.which("sh") is None:
        pytest.skip("no `sh` on PATH: the entrypoint cannot run here (CI on Linux runs it)")

    def fresh(name: str) -> Path:
        directory = tmp_path / name
        directory.mkdir()
        return _deployment(directory, enrolled=False)[0]

    refusals: list[tuple[str, dict[str, str], str]] = []
    refusals.append(("unset", _shell_env(tmp_path / "u", None), "ISIDIUM_SIGNER_SETTINGS"))
    empty = {**_shell_env(tmp_path / "e", None), "ISIDIUM_SIGNER_SETTINGS": ""}
    refusals.append(("empty", empty, "ISIDIUM_SIGNER_SETTINGS"))
    absent = tmp_path / "absent" / "signer.toml"
    refusals.append(("no file", _shell_env(tmp_path / "a", absent), "signer.toml"))

    no_callers = fresh("no-callers")
    no_callers.write_text(re.sub(r"callers = \[.*\]\n", "", no_callers.read_text(encoding="utf-8")), encoding="utf-8")
    refusals.append(("callers missing", _shell_env(tmp_path / "n1", no_callers), "callers"))
    empty_callers = fresh("empty-callers")
    empty_callers.write_text(
        re.sub(r"callers = \[.*\]\n", "callers = []\n", empty_callers.read_text(encoding="utf-8")), encoding="utf-8"
    )
    refusals.append(("callers empty", _shell_env(tmp_path / "n2", empty_callers), "callers"))

    needed = (
        "signing.pem",
        "server.crt.pem",
        "server.key.pem",
        "signer-test-ca.ca.pem",
        "page.crt.pem",
        "page.key.pem",
    )
    for removed in needed:
        path = fresh(f"no-{removed}")
        (path.parent / removed).unlink()
        refusals.append((f"missing {removed}", _shell_env(path.parent, path), removed))

    for label, env, names in refusals:
        done = _run_entrypoint(env)
        assert done.returncode == 2, (label, done.returncode, done.stderr)
        assert names in done.stderr, (label, done.stderr)
        assert "Traceback" not in done.stderr, (label, done.stderr)

    # positive control: everything present and no TOTP secret -- enrolment is open, which is not a refusal
    path = fresh("all-there")
    err_file = path.parent / "stderr.txt"
    with err_file.open("wb") as err:
        proc = subprocess.Popen(
            ["sh", str(ENTRYPOINT)], env=_shell_env(path.parent, path), stdout=subprocess.DEVNULL, stderr=err
        )
        try:
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline and proc.poll() is None:
                if "enrolled=no" in err_file.read_text(encoding="utf-8"):
                    break
                time.sleep(0.1)
            assert proc.poll() is None, err_file.read_text(encoding="utf-8")
            assert re.search(r"isidium-signer: api=\S+ page=\S+ enrolled=no", err_file.read_text(encoding="utf-8"))
            proc.send_signal(signal.SIGTERM)
            assert proc.wait(timeout=30) == 0
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()


def test_a_malformed_form_is_a_rule_id(tmp_path: Path) -> None:
    """The page's refusals are rule ids, not the stdlib's HTML: a form that is not the one the endpoint takes is
    `signer.malformed`, and the request it named is untouched."""
    rig = _build(tmp_path, enrolled=True)
    try:
        rid = rig.client().submit(TENANT, VALUE, rig.clock.now, [])
        host, port = rig.web.address
        context = ssl.create_default_context(cafile=str(rig.ca.path))
        conn = http.client.HTTPSConnection(host, port, context=context, timeout=5.0)
        try:
            conn.request("POST", "/approve", b"request_id=a&request_id=b", {"Content-Type": "application/json"})
            response = conn.getresponse()
            assert response.status == 400 and "signer.malformed" in response.read().decode("utf-8")
        finally:
            conn.close()
        assert rig.client().poll(rid) is None
    finally:
        rig.web.close()
        rig.api.close()
