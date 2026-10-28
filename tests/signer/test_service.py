"""The signing service, driven over a real HTTPS listener on 127.0.0.1 with certificates minted here (no openssl, no
network, nothing on disk beyond the temporary directory).

Every refusal below is paired with a positive control, so no assertion can pass on silence: a refused submit is
shown next to an accepted one, a refused connection next to a connection that is answered.
"""

from __future__ import annotations

import base64
import datetime as _dt
import ipaddress
import json
import socket
import ssl
import time
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from isidium.signer import http, settings, totp
from isidium.signer.http import HttpsService, Listener
from isidium.signer.service import Service
from isidium.store.core import chain
from isidium.store.core.refusal import Refusal
from isidium.store.server.signer import RemoteTotp

from ..conftest import Telemetry

NOW = _dt.datetime.now(_dt.UTC)
BASE = 1_800_000_000  # the service's fake clock; a multiple of 30, so it opens a TOTP step
SECRET = b"12345678901234567890"
TENANT = "example-tenant"
VALUE = "sha256:" + "ab" * 32
CALLER = "CN=store-client"  # the subject of the named client certificate, RFC 4514
LIMIT_PENDING, LIMIT_WRONG, SKEW, LIFETIME = 2, 3, 60, 300


# ---- certificates, made here ---------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Authority:
    key: ec.EllipticCurvePrivateKey
    certificate: x509.Certificate
    path: Path


@dataclass(frozen=True)
class Leaf:
    cert: Path
    key: Path


def _name(common_name: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])


def authority(directory: Path, common_name: str) -> Authority:
    key = ec.generate_private_key(ec.SECP256R1())
    certificate = (
        x509.CertificateBuilder()
        .subject_name(_name(common_name))
        .issuer_name(_name(common_name))
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(NOW - _dt.timedelta(days=1))
        .not_valid_after(NOW + _dt.timedelta(days=30))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    path = directory / f"{common_name}.ca.pem"
    path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    return Authority(key, certificate, path)


def issue(directory: Path, ca: Authority, label: str, common_name: str, *, server: bool = False) -> Leaf:
    key = ec.generate_private_key(ec.SECP256R1())
    builder = (
        x509.CertificateBuilder()
        .subject_name(_name(common_name))
        .issuer_name(ca.certificate.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(NOW - _dt.timedelta(days=1))
        .not_valid_after(NOW + _dt.timedelta(days=30))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH if server else ExtendedKeyUsageOID.CLIENT_AUTH]),
            critical=False,
        )
    )
    if server:
        builder = builder.add_extension(
            x509.SubjectAlternativeName(
                [x509.DNSName("localhost"), x509.IPAddress(ipaddress.IPv4Address("127.0.0.1"))]
            ),
            critical=False,
        )
    certificate = builder.sign(ca.key, hashes.SHA256())
    cert, key_path = directory / f"{label}.crt.pem", directory / f"{label}.key.pem"
    cert.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )
    return Leaf(cert, key_path)


# ---- the service under test ----------------------------------------------------------------------------------------


class Clock:
    def __init__(self) -> None:
        self.now = BASE

    def __call__(self) -> int:
        return self.now


class Recording(Service):
    """Counts the submits that reach the service, on entry and so before the service's own caller check: a request
    that got past the listener's checks shows here even if the service then refuses it."""

    entered = 0

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.rids: list[str] = []
        self.displays: list[Sequence[Any]] = []

    def submit(
        self, caller: str, tenant: str, value: str, at_epoch: int, display: Sequence[Any], time_skew_s: int | None
    ) -> str:
        self.entered += 1
        rid = super().submit(caller, tenant, value, at_epoch, display, time_skew_s)
        self.rids.append(rid)
        self.displays.append(display)
        return rid


@dataclass
class Rig:
    directory: Path
    settings_path: Path
    settings: settings.Settings
    clock: Clock
    service: Recording
    listener: Listener
    ca: Authority
    named: Leaf
    unnamed: Leaf
    stranger: Leaf  # the named subject, issued by an authority the service does not trust

    def https(self, leaf: Leaf | None = None) -> HttpsService:
        host, port = self.listener.address
        leaf = leaf or self.named
        return HttpsService(host, port, self.ca.path, leaf.cert, leaf.key, timeout_s=5.0)


def _write_settings(directory: Path, ca: Authority, server: Leaf) -> Path:
    path = directory / "signer.toml"
    path.write_text(
        f"""listen_host = "127.0.0.1"
listen_port = 0
tls_certificate = "{server.cert.name}"
tls_key = "{server.key.name}"
ca = "{ca.path.name}"
callers = ["{CALLER}"]
signing_key = "signing.pem"
totp_secret = "totp.base32"
state = "state/signer.json"
time_skew_s = {SKEW}
max_pending_per_caller = {LIMIT_PENDING}
max_wrong_codes = {LIMIT_WRONG}
request_lifetime_s = {LIFETIME}
handshake_timeout_s = 5.0
read_timeout_s = 5.0
max_body_bytes = 65536
""",
        encoding="utf-8",
    )
    return path


@pytest.fixture
def rig(tmp_path: Path) -> Iterator[Rig]:
    ca = authority(tmp_path, "signer-test-ca")
    other = authority(tmp_path, "other-test-ca")
    server = issue(tmp_path, ca, "server", "signer.example.invalid", server=True)
    named = issue(tmp_path, ca, "named", "store-client")
    unnamed = issue(tmp_path, ca, "unnamed", "intruder")
    stranger = issue(tmp_path, other, "stranger", "store-client")
    key = tmp_path / "signing.pem"
    key.write_bytes(
        ed25519.Ed25519PrivateKey.generate().private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
    )
    secret = tmp_path / "totp.base32"
    secret.write_text(base64.b32encode(SECRET).decode(), encoding="ascii")
    key.chmod(0o600)
    secret.chmod(0o600)
    path = _write_settings(tmp_path, ca, server)
    cfg = settings.load(path)
    clock = Clock()
    service = Recording(cfg, clock)
    listener = http.start(service, cfg)
    try:
        yield Rig(tmp_path, path, cfg, clock, service, listener, ca, named, unnamed, stranger)
    finally:
        listener.close()


def wrong_code(epoch: int) -> str:
    """A six-digit code that is not the code of any step the window accepts at `epoch`."""
    step = totp.step_of(epoch)
    taken = {totp.hotp(SECRET, s) for s in range(step - 2, step + 3)}
    return next(f"{n:06d}" for n in range(10**6) if f"{n:06d}" not in taken)


def rule_of(err: pytest.ExceptionInfo[Refusal]) -> str:
    return err.value.rule


# ---- the tests -----------------------------------------------------------------------------------------------------


def test_submit_refusals(rig: Rig) -> None:
    now = rig.clock.now
    client = rig.https()
    assert client.submit(TENANT, VALUE, now, []) != ""  # positive control: the named caller, in time, under the limit

    with pytest.raises(Refusal) as err:  # a CA-issued certificate the settings do not name
        rig.https(rig.unnamed).submit(TENANT, VALUE, now, [])
    assert rule_of(err) == "signer.unknown-caller"
    with pytest.raises(Refusal) as err:  # the service refuses an unnamed caller on its own, not only the listener
        rig.service.submit("CN=intruder", TENANT, VALUE, now, [], None)
    assert rule_of(err) == "signer.unknown-caller"

    assert client.submit(TENANT, VALUE, now + SKEW, []) != ""  # exactly at the bound is in time
    with pytest.raises(Refusal) as err:
        client.submit(TENANT, VALUE, now + SKEW + 1, [])
    assert rule_of(err) == "signer.time-skew"
    with pytest.raises(Refusal) as err:  # a caller can narrow the settings' skew but never widen it
        client.submit(TENANT, VALUE, now + SKEW + 1, [], time_skew_s=2 * SKEW)
    assert rule_of(err) == "signer.time-skew"
    with pytest.raises(Refusal) as err:
        client.submit(TENANT, VALUE, now - 1, [], time_skew_s=0)
    assert rule_of(err) == "signer.time-skew"

    with pytest.raises(Refusal) as err:  # two are pending (the limit); the third is refused
        client.submit(TENANT, VALUE, now, [])
    assert rule_of(err) == "signer.rate-limited"


def test_a_code_signs_once(rig: Rig) -> None:
    refusals: list[Refusal] = []
    now = rig.clock.now
    service = rig.service
    first = service.submit(CALLER, TENANT, VALUE, now, [], None)
    second = service.submit(CALLER, TENANT, VALUE, now, [], None)
    assert service.poll(CALLER, first) is None

    code = totp.code_at(SECRET, now)
    service.approve(first, code)
    sig = service.poll(CALLER, first)
    assert sig is not None
    assert chain.verify_sig(sig, TENANT, VALUE)
    alg, fpr, _ = chain.parse_sig(sig)
    assert (alg, fpr) == ("ed25519", service.key_fpr)
    with pytest.raises(Refusal) as err:  # a signed request is not approved twice
        service.approve(first, code)
    assert rule_of(err) == "signer.not-pending"

    with pytest.raises(Refusal) as err:  # the same code, a different request
        service.approve(second, code)
    refusals.append(err.value)
    assert rule_of(err) == "signer.code-reused"
    assert service.poll(CALLER, second) is None

    rig.clock.now += totp.STEP_S  # the next step's code signs
    fresh = totp.code_at(SECRET, rig.clock.now)
    service.approve(second, fresh)
    assert chain.verify_sig(service.poll(CALLER, second) or "", TENANT, VALUE)

    # a restart cannot replay: the used step is on disk, and a service built over the same settings refuses it
    again = Recording(rig.settings, rig.clock)
    third = again.submit(CALLER, TENANT, VALUE, rig.clock.now, [], None)
    with pytest.raises(Refusal) as err:
        again.approve(third, fresh)
    refusals.append(err.value)
    assert rule_of(err) == "signer.code-reused"
    # the poll is bound to the submitting caller
    with pytest.raises(Refusal) as err:
        again.poll("CN=somebody-else", third)
    assert rule_of(err) == "signer.unknown-request"

    secret_text = base64.b32encode(SECRET).decode()
    for refusal in refusals:  # C3: neither the secret nor a code is ever in what a refusal says
        assert secret_text not in repr(refusal) and code not in repr(refusal) and fresh not in repr(refusal)
    assert secret_text not in repr(service)


def test_wrong_codes_decline(rig: Rig, otel: Telemetry) -> None:
    service = rig.service
    now = rig.clock.now
    rid = service.submit(CALLER, TENANT, VALUE, now, [], None)
    before = otel.count("isidium.signer.refusal", rule="signer.wrong-code")
    for _ in range(LIMIT_WRONG - 1):
        with pytest.raises(Refusal) as err:
            service.approve(rid, wrong_code(now))
        assert rule_of(err) == "signer.wrong-code"
        assert service.poll(CALLER, rid) is None
    assert otel.count("isidium.signer.refusal", rule="signer.wrong-code") - before == LIMIT_WRONG - 1

    with pytest.raises(Refusal) as err:  # the wrong code at the limit declines the request
        service.approve(rid, wrong_code(now))
    assert rule_of(err) == "signer.declined"
    with pytest.raises(Refusal) as err:
        service.poll(CALLER, rid)
    assert rule_of(err) == "signer.declined"
    with pytest.raises(Refusal) as err:  # and a now-valid code does not revive it
        service.approve(rid, totp.code_at(SECRET, now))
    assert rule_of(err) == "signer.declined"

    # an unanswered request expires: declined for one more lifetime, then swept
    lone = service.submit(CALLER, TENANT, VALUE, now, [], None)
    rig.clock.now = now + LIFETIME - 1
    assert service.poll(CALLER, lone) is None
    rig.clock.now = now + LIFETIME
    with pytest.raises(Refusal) as err:
        service.poll(CALLER, lone)
    assert rule_of(err) == "signer.declined"
    rig.clock.now = now + 2 * LIFETIME - 1
    with pytest.raises(Refusal) as err:
        service.poll(CALLER, lone)
    assert rule_of(err) == "signer.declined"
    rig.clock.now = now + 2 * LIFETIME
    with pytest.raises(Refusal) as err:
        service.poll(CALLER, lone)
    assert rule_of(err) == "signer.unknown-request"


def _raw_submit(rig: Rig, context: ssl.SSLContext) -> bytes:
    """A well-formed POST /submit over a raw TLS client; whatever bytes came back (b"" when the connection was
    refused at connect or at the first read)."""
    body = json.dumps(
        {"tenant": TENANT, "value": VALUE, "at_epoch": rig.clock.now, "display": [], "time_skew_s": None}
    ).encode()
    head = f"POST /submit HTTP/1.1\r\nHost: localhost\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n"
    got = b""
    host, port = rig.listener.address
    try:
        with (
            socket.create_connection((host, port), timeout=5) as sock,
            context.wrap_socket(sock, server_hostname=host) as tls,
        ):
            tls.sendall(head.encode() + body)
            while chunk := tls.recv(65536):
                got += chunk
    except (ssl.SSLError, ConnectionError):
        pass
    return got


def _client_context(rig: Rig, leaf: Leaf | None, *, max_tls: ssl.TLSVersion | None = None) -> ssl.SSLContext:
    context = ssl.create_default_context(cafile=str(rig.ca.path))
    if leaf is not None:
        context.load_cert_chain(str(leaf.cert), str(leaf.key))
    if max_tls is not None:
        context.maximum_version = max_tls
    return context


def test_mtls_required(rig: Rig) -> None:
    # No bytes beginning HTTP/ may come back to a connection that is not a named caller's: nothing is answered but a
    # refusal at the handshake. (Under TLS 1.3 the client's handshake completes before the server's verdict, so the
    # refusal reaches it at its first read; either way it is not an HTTP answer.)
    assert not _raw_submit(rig, _client_context(rig, None)).startswith(b"HTTP/")  # no certificate
    assert not _raw_submit(rig, _client_context(rig, rig.stranger)).startswith(b"HTTP/")  # an authority not trusted
    old = _client_context(rig, rig.named, max_tls=ssl.TLSVersion.TLSv1_2)  # the named certificate, below TLS 1.3
    assert not _raw_submit(rig, old).startswith(b"HTTP/")

    # a certificate the CA issued but the settings do not name is answered, with a refusal and no more
    # and promptly: the body rides in the same TLS record as the headers, so the refusal must not wait out the
    # listener's read timeout for bytes it already holds (the connection closes as soon as the answer is written)
    began = time.monotonic()
    answer = _raw_submit(rig, _client_context(rig, rig.unnamed))
    assert time.monotonic() - began < 2.0
    head, _, body = answer.partition(b"\r\n\r\n")
    assert head.split(b"\r\n")[0].split()[1] == b"403"
    assert json.loads(body)["rule"] == "signer.unknown-caller"

    assert rig.service.entered == 0  # none of the four reached the service

    # positive control: the named caller, over TLS 1.3, is answered
    assert rig.https().submit(TENANT, VALUE, rig.clock.now, []) != ""
    assert rig.service.entered == 1


def test_remote_totp_end_to_end(rig: Rig) -> None:
    service = rig.service
    approved: list[str] = []

    def approve_with_the_owners_code(_seconds: float) -> None:
        if not approved:
            code = totp.code_at(SECRET, rig.clock.now)
            service.approve(service.rids[-1], code)
            approved.append(code)

    display = [{"id": 52, "act": "ratified", "build_hash": VALUE}]
    signer = RemoteTotp(
        rig.https(), service.key_fpr, poll_interval_ms=10, timeout_s=5, sleep=approve_with_the_owners_code
    )
    sig = signer.sign(TENANT, VALUE, rig.clock.now, display)
    assert chain.verify_sig(sig, TENANT, VALUE)
    assert chain.parse_sig(sig)[1] == service.key_fpr
    assert service.displays[-1] == display  # the service received what was shown
    assert len(approved) == 1

    # a declined request reaches RemoteTotp as the typed refusal. The hook swallows approve's own refusals, so the
    # signer.declined that sign() raises can only be the one HttpsService.poll rebuilt from the listener's 403.
    rules: list[str] = []

    def guess_wrong(_seconds: float) -> None:
        if rules:
            return
        for _ in range(LIMIT_WRONG):
            try:
                service.approve(service.rids[-1], wrong_code(rig.clock.now))
            except Refusal as r:
                rules.append(r.rule)

    declined = RemoteTotp(rig.https(), service.key_fpr, poll_interval_ms=10, timeout_s=5, sleep=guess_wrong)
    with pytest.raises(Refusal) as err:
        declined.sign(TENANT, VALUE, rig.clock.now, display)
    assert rule_of(err) == "signer.declined"
    assert rules == ["signer.wrong-code"] * (LIMIT_WRONG - 1) + ["signer.declined"]


def test_settings_refuse_what_is_missing_or_unknown(rig: Rig) -> None:
    text = rig.settings_path.read_text(encoding="utf-8")
    cases = {
        "max_wrong_codes": text.replace(f"max_wrong_codes = {LIMIT_WRONG}\n", ""),  # missing
        "surprise": text + "surprise = 1\n",  # unknown
        "time_skew_s": text.replace(f"time_skew_s = {SKEW}", 'time_skew_s = "60"'),  # wrongly typed
    }
    for key, broken in cases.items():
        path = rig.directory / f"broken-{key}.toml"
        path.write_text(broken, encoding="utf-8")
        with pytest.raises(Refusal) as err:
            settings.load(path)
        assert (err.value.rule, err.value.path) == ("signer.settings", key)
