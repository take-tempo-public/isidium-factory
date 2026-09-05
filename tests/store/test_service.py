"""The service and the tool surface: the typed call surface authenticates the caller from the mTLS client
certificate and from nothing else; a refusal is data with a status; the MCP surface serves the generated schemas and
returns refusals as tool errors; both doors reach the same `Api` object.

`handle` is a plain function from a typed request and the peer's certificate to a typed response, so these tests are
values in and values out — no sockets and no scope dictionaries. The socket itself, and the property that the
handshake gates every byte before any of this runs, are `test_edge.py`'s."""

from __future__ import annotations

import datetime as _dt
import io
import json
from collections.abc import Mapping
from typing import Any

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from isidium.store.client.mcp import McpServer, tools
from isidium.store.core.refusal import Refusal
from isidium.store.server.api import Api
from isidium.store.server.service import Credential, Registration, Request, Service

from .conftest import BASE_SCOPE, Harness, base_head, fresh


def cert_for(cn: str) -> bytes:
    """A self-signed client certificate in DER — the channel's credential, in the encoding the connection hands
    over; the registration maps its **full subject** (`CN=<cn>`) to a principal [K6]. Issued with `clientAuth`,
    which the store requires since K6 (Q5), and valid from 2026-08-01 for a year — `CLOCK` below sits inside."""
    key = ed25519.Ed25519PrivateKey.generate()
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    now = _dt.datetime(2026, 8, 1, tzinfo=_dt.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + _dt.timedelta(days=365))
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False)
        .sign(key, None)
    )
    return cert.public_bytes(serialization.Encoding.DER)


def CLOCK() -> int:
    """2026-08-17T10:13:20Z — inside every `cert_for` window, and the instant the store's window check reads."""
    return 1_787_000_000


OWNER_CERT = cert_for("owner@example")
PLANNER_CERT = cert_for("sartor-planner@agents.example")
STRANGER_CERT = cert_for("nobody@example.com")
# A DER header that starts like a certificate and then is not one — the shape a truncated or corrupted
# credential actually has, and what the ASN.1 parser is asked to read.
GARBAGE_DER = bytes([0x30, 0x82]) + b"garbage, not a certificate"


def call(service: Service, name: str, args: Mapping[str, Any], cert: bytes | None) -> tuple[int, dict[str, Any]]:
    """One call, as the edge would deliver it: the connection's credential beside the parsed request.

    The edge resolves the certificate once, right after the handshake, and hands `handle` the resolved value
    (`Credential`) rather than the DER — so the certificate is parsed once per connection and a certificate that
    will not parse is an authentication failure at the place it is parsed, not a `ValueError` in the argument
    handler (K1b-ii item 3)."""
    request = Request("POST", f"/call/{name}", json.dumps(args).encode("utf-8"))
    response = service.handle(request, service.registration.credential(cert))
    return response.status, json.loads(response.body)


@pytest.fixture(scope="module")
def svc() -> tuple[Service, Harness]:
    hz = fresh("svc")
    registration = Registration(
        {
            "CN=owner@example": ("amodal1@example", "owner"),
            "CN=sartor-planner@agents.example": ("sartor-planner@agents.example", "contributor"),
        },
        CLOCK,
    )
    return Service(Api(hz.st), registration, hz.st.tenant), hz


def test_the_channel_is_the_only_identity(svc: tuple[Service, Harness]) -> None:
    service, _hz = svc
    status, body = call(service, "show", {"target": "queue"}, None)
    # **The rule id and nothing else** [C-12, built by K2b]. This line used to assert that the body named
    # `CERT_REQUIRED` and "misconfigured" — a diagnosis of the store's own deployment, returned to a peer with no
    # identity that could not act on it. It is not discarded: it goes to the operator, on stderr, and
    # `test_telemetry.py` asserts both that it left the response and that it arrived in the record.
    assert (status, body) == (401, {"rule": "auth.no-client-certificate"})
    status, body = call(service, "show", {"target": "queue"}, STRANGER_CERT)
    assert (status, body) == (403, {"rule": "auth.unknown-client"}), "the subject was echoed back to a stranger"
    status, body = call(service, "show", {"target": "queue"}, PLANNER_CERT)
    assert status == 200 and "open_questions" in body["result"]


def test_a_malformed_client_certificate_is_an_authentication_failure(svc: tuple[Service, Harness]) -> None:
    """Measured 2026-08-29: garbage DER was answered `400 {"rule": "service.arguments", "detail": "error parsing
    asn1 value: ParseError { kind: ShortData … }"}` — the certificate parser’s own words, to a peer with no
    identity. `caller_of` was called inside the block whose `except (KeyError, ValueError, TypeError)` becomes
    `service.arguments`, so an authentication failure was reported as a bad argument. This is the defect that
    motivated C-12, and C-12’s table as written renames it rather than closing it.

    Two arms: the rule id says authentication, and no word of the parser reaches the peer. The parser’s text is kept
    on the credential for the record (K2b lands it) — it is withheld, not discarded."""
    service, _hz = svc
    credential = service.registration.credential(GARBAGE_DER)
    status, body = call(service, "show", {"target": "queue"}, GARBAGE_DER)
    assert (status, body) == (401, {"rule": "auth.malformed-certificate"})
    assert "asn1" not in json.dumps(body).lower() and "ParseError" not in json.dumps(body)
    assert credential.parse_error is not None, "the withheld text was discarded rather than kept for the record"
    assert credential.fingerprint is not None, "a certificate that will not parse still needs an admission key"


def test_write_and_ratify_over_the_service(svc: tuple[Service, Harness]) -> None:
    service, _hz = svc
    head = base_head(0, "draft")
    head.pop("id")
    status, body = call(
        service, "write", {"new_slug": "over-the-wire", "document": {"head": head, "scope": BASE_SCOPE}}, PLANNER_CERT
    )
    assert status == 200, body
    cid = body["result"]["id"]
    assert (
        body["result"]["entry"]["act"] == "created" and body["result"]["entry"]["by"] == "sartor-planner@agents.example"
    )
    # the planner may not sign: the grant comes from the certificate, not from the request
    status, body = call(service, "ratify", {"ids": [cid], "dry_run": False}, PLANNER_CERT)
    assert status == 403 and body["rule"] == "write.grant"
    status, body = call(service, "ratify", {"ids": [cid], "dry_run": True}, PLANNER_CERT)
    assert status == 200 and body["result"]["verdicts"][str(cid)] == []
    status, body = call(service, "ratify", {"ids": [cid], "dry_run": False}, OWNER_CERT)
    assert status == 200 and body["result"]["entries"][0]["act"] == "ratified"
    status, body = call(service, "check", {"id": cid}, PLANNER_CERT)
    assert status == 200 and body["result"]["integrity"] == []
    # a typed refusal keeps its rule id and gets a status
    status, body = call(service, "show", {"target": "card", "id": 9999}, PLANNER_CERT)
    assert status == 404 and body["rule"] == "show.unknown"
    status, body = call(service, "write", {"card": cid, "document": {"head": {**head, "misc": 1}}}, PLANNER_CERT)
    assert status == 422 and body["rule"] == "head.typed"
    status, body = call(service, "nope", {}, PLANNER_CERT)
    assert status == 404 and body["rule"] == "api.unknown-call"


def test_a_bug_in_a_verb_is_answered_and_never_swallowed(svc: tuple[Service, Harness]) -> None:
    """`handle` caught five exception types; anything else — a `RuntimeError`, an `AttributeError` — escaped it and
    `_connection` both, and the caller got an opened-then-closed connection with no status and no rule id (measured
    2026-08-29). `test_edge.py` proves the peer gets an answer over a socket; this proves the *service layer* is one
    of the two places that guarantees it, so removing either one is caught.

    The discriminator is the rule id plus the absence of the exception’s own words: detail about a bug in us belongs
    to the record, never to the caller (C-12)."""
    service, _hz = svc

    class Exploding:
        def call(self, *_a: Any, **_k: Any) -> Any:
            raise RuntimeError("a bug, not a refusal")

    exploding = Service(Exploding(), service.registration, service.tenant)  # type: ignore[arg-type]
    status, body = call(exploding, "show", {"target": "queue"}, OWNER_CERT)
    assert status == 500 and body == {"rule": "service.internal"}


def test_health_and_routing(svc: tuple[Service, Harness]) -> None:
    service, _hz = svc
    owner = service.registration.credential(OWNER_CERT)
    health = service.handle(Request("GET", "/health", b""), Credential(None))
    assert health.status == 200 and json.loads(health.body)["ok"] is True
    # `HEAD` is the other way a health checker asks, and it is answered (K1b-ii item 5; the body is `_respond`'s)
    assert service.handle(Request("HEAD", "/health", b""), Credential(None)).status == 200
    # only the two routes exist, and only under their own methods
    assert service.handle(Request("GET", "/call/show", b""), owner).status == 404
    assert service.handle(Request("POST", "/health", b""), owner).status == 404


# ---- the MCP tool surface ---------------------------------------------------------------------------------------


class DirectTransport:
    def __init__(self, api: Api, caller: Any) -> None:
        self.api, self.caller = api, caller

    def call(self, name: str, args: Mapping[str, Any]) -> Any:
        return self.api.call(name, self.caller, args)


def test_mcp_serves_the_generated_schemas_and_calls(svc: tuple[Service, Harness]) -> None:
    from .conftest import OWNER

    _service, hz = svc
    server = McpServer(DirectTransport(Api(hz.st), OWNER))
    init = server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert init is not None and init["result"]["serverInfo"]["name"] == "isidium-store"
    assert server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    listed = server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert listed is not None
    names = {t["name"] for t in listed["result"]["tools"]}
    assert names == {t["name"] for t in tools()} == {"write", "ratify", "show", "check", "suggest", "disposition"}
    # every tool's input schema is the generated one — the model is constrained at the moment it writes
    write_tool = next(t for t in listed["result"]["tools"] if t["name"] == "write")
    schema = write_tool["inputSchema"]
    assert schema["properties"]["document"] == {"$ref": "#/$defs/CardDocument"}
    assert schema["$defs"]["CardHead"]["properties"]["kind"]["anyOf"]  # the card schema, spelled once
    r = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "show", "arguments": {"target": "queue"}},
        }
    )
    assert r is not None and "structuredContent" in r["result"]
    # a refusal comes back as a tool error carrying its rule id, not an exception
    r = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "show", "arguments": {"target": "card", "id": 9999}},
        }
    )
    assert r is not None and r["result"]["isError"] is True
    assert json.loads(r["result"]["content"][0]["text"])["rule"] == "show.unknown"
    r = server.handle({"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "nope", "arguments": {}}})
    assert r is not None and r["error"]["code"] == -32602


def test_mcp_stdio_loop(svc: tuple[Service, Harness]) -> None:
    from .conftest import OWNER

    _service, hz = svc
    server = McpServer(DirectTransport(Api(hz.st), OWNER))
    stdin = io.BytesIO(
        b'{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}\n'
        b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n'
        b'{"jsonrpc":"2.0","id":2,"method":"tools/list"}\n'
        b"not json\n"
    )
    stdout = io.BytesIO()
    server.serve(stdin, stdout)
    lines = [json.loads(x) for x in stdout.getvalue().splitlines()]
    assert [x.get("id") for x in lines] == [
        1,
        2,
        None,
    ]  # the notification produced nothing; the bad line, a parse error
    assert lines[2]["error"]["code"] == -32700


def test_api_refuses_an_unknown_call(svc: tuple[Service, Harness]) -> None:
    from .conftest import OWNER

    _service, hz = svc
    with pytest.raises(Refusal, match=r"api\.not-yet"):
        Api(hz.st).call("land", OWNER, {})  # v1b: the verb names itself rather than reading as unknown
    with pytest.raises(Refusal, match=r"api\.not-yet"):
        Api(hz.st).call("accept", OWNER, {})
    with pytest.raises(Refusal, match=r"api\.unknown-call"):
        Api(hz.st).call("nope", OWNER, {})
