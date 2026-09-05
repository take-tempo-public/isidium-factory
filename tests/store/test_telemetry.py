"""**C-11's and C-12's enforcement** (K2b). Both rules were admitted to `06-code-constraints.md` on the promise of
this file, and until it existed neither was enforced by anything.

What is proven here, and what is proven elsewhere:

* **here** — the spans and their outcome for one call at the service layer; the disclosure filter at the constructor
  every door shares; the authored messages that replaced the two responses whose words were not ours; and, in a
  **subprocess**, the two claims this process cannot make about itself — that with no SDK configured the store
  reaches no network, and that with the console exporter it prints spans to stderr;
* **`test_edge.py`** — the counters, which need a real socket and a real refused handshake, and the two spans of a
  full call over TLS;
* **`tests/unit/test_rule_ids.py`** — the sweep: every namespace the code can raise has a row, every id in a
  declare-explicitly namespace has its own, and no rule id reaches a caller without passing through `Refusal`.

**Why the subprocess.** `tests/store/conftest.py` installs a real SDK for the whole session, because the providers
are process-global and two test files read them. An absence therefore cannot be observed in this process at all: a
test here asserting "no SDK is configured" would be asserting something the fixture had already made false, and it
would pass for the wrong reason if the fixture were removed. The two claims that are *about* the unconfigured store
run in a child with a clean interpreter.
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from isidium.store.core import telemetry
from isidium.store.core.disclosure import Disclosure, row_of
from isidium.store.core.refusal import Refusal, ValidationRefusal
from isidium.store.server.api import Api
from isidium.store.server.service import Registration, Request, Service

from .conftest import BASE_SCOPE, Harness, Telemetry, base_head, fresh
from .test_service import CLOCK, OWNER_CERT, PLANNER_CERT, STRANGER_CERT

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def svc() -> tuple[Service, Harness]:
    hz = fresh("telemetry")
    registration = Registration(
        {
            "CN=owner@example": ("amodal1@example", "owner"),
            "CN=sartor-planner@agents.example": ("sartor-planner@agents.example", "contributor"),
        },
        CLOCK,
    )
    return Service(Api(hz.st), registration, hz.st.tenant), hz


def call(service: Service, name: str, args: Mapping[str, Any], cert: bytes | None) -> tuple[int, dict[str, Any]]:
    request = Request("POST", f"/call/{name}", json.dumps(args).encode("utf-8"))
    response = service.handle(request, service.registration.credential(cert))
    return response.status, json.loads(response.body)


# ---- C-11: one call, its spans, its outcome and its rule id ------------------------------------------------------


def test_one_call_carries_a_span_with_its_outcome_and_its_rule_id(
    svc: tuple[Service, Harness], otel: Telemetry
) -> None:
    """**The test C-11 was admitted on.** One call through the surface, against the SDK's in-memory span exporter:
    the span exists, the outcome is the span's *status*, and the refusal's rule id is an *attribute* — the two
    sentences the rule is written in.

    The discriminator is that both outcomes are asserted from the same shape. A span that merely *exists* proves
    nothing: an uninstrumented store also produces no ERROR spans, and a store whose refusals were untyped would
    produce a span with no rule id and still be a span. So the passing call must come back `OK` **and** the refused
    one `ERROR` with the id, off the same exporter, in one test."""
    service, _hz = svc
    otel.clear()

    ok_status, _ok_body = call(service, "show", {"target": "queue"}, PLANNER_CERT)
    refused_status, refused_body = call(service, "show", {"target": "card", "id": 9999}, PLANNER_CERT)
    assert (ok_status, refused_status) == (200, 404) and refused_body["rule"] == "show.unknown"

    spans = otel.spans(telemetry.CALL_SPAN)
    assert len(spans) == 2, [s.name for s in otel.spans()]
    good, bad = spans
    assert good.status.status_code.name == "OK", good.status
    assert good.attributes[telemetry.ACTION] == "show"
    assert good.attributes[telemetry.SUBJECT] == "sartor-planner@agents.example"
    assert good.attributes[telemetry.GRANT] == "contributor"
    assert good.attributes[telemetry.TENANT] == "telemetry"
    assert telemetry.RULE not in good.attributes, "a call that succeeded named a rule id"
    assert bad.status.status_code.name == "ERROR", bad.status
    assert bad.attributes[telemetry.RULE] == "show.unknown"
    assert bad.attributes[telemetry.RESOURCE] == "card:9999"


def test_the_refusal_counter_moves_for_an_identified_caller(svc: tuple[Service, Harness], otel: Telemetry) -> None:
    """A refusal to a caller the handshake admitted is counted by rule id — bounded by the registration, so it is
    not the "record per hostile connection" C-11 forbids. Read as a difference, because the reader is cumulative
    and the whole session shares it.

    **Counted once, not once per verdict.** A validation refusal carries N typed verdicts and each is disclosed
    through the same filter; if the filter also recorded, one refused call would count as N+1 and the span's rule id
    would end up being the last verdict's rather than `validate.failed`."""
    service, _hz = svc
    head = base_head(0, "draft")
    head.pop("id")
    head.pop("acceptance")
    before = otel.count("isidium.store.refusal", **{telemetry.RULE: "validate.failed"})
    before_verdict = otel.count("isidium.store.refusal", **{telemetry.RULE: "profile.bdd.rule-without-scenario"})
    status, body = call(
        service, "write", {"new_slug": "counted-once", "document": {"head": head, "scope": BASE_SCOPE}}, PLANNER_CERT
    )
    assert status == 422 and body["rule"] == "validate.failed" and body["verdicts"]
    assert otel.count("isidium.store.refusal", **{telemetry.RULE: "validate.failed"}) == before + 1
    assert (
        otel.count("isidium.store.refusal", **{telemetry.RULE: "profile.bdd.rule-without-scenario"}) == before_verdict
    ), "a verdict inside a refusal was counted as a refusal of its own"


# ---- C-12: what the caller is told -------------------------------------------------------------------------------


def test_a_pre_identification_refusal_carries_no_detail(
    svc: tuple[Service, Harness], caplog: pytest.LogCaptureFixture
) -> None:
    """C-12 rule 1: **before the caller is identified, a refusal carries its rule id and nothing else.**

    Three ids, and the assertion is on the whole body rather than on the absence of one substring — `body["detail"]`
    being empty and `detail` not being a key at all are different facts, and only the second one is the ruling. An
    empty string still says "we have a detail for you and it is nothing".

    **The discriminator is that the withheld words still exist.** A store that never had an operator message would
    pass an absence check too, so each arm also proves the sentence survived, in the log record where C-12 sends it.
    That is the floor: trimming a response only relocates information if something catches it."""
    service, _hz = svc
    with caplog.at_level("WARNING", logger=telemetry.SCOPE):
        status, body = call(service, "show", {"target": "queue"}, None)
        assert (status, body) == (401, {"rule": "auth.no-client-certificate"})
        status, body = call(service, "show", {"target": "queue"}, STRANGER_CERT)
        assert (status, body) == (403, {"rule": "auth.unknown-client"})
        routed = service.handle(Request("GET", "/call/show", b""), service.registration.credential(OWNER_CERT))
        assert (routed.status, json.loads(routed.body)) == (404, {"rule": "service.route"})
    records = "\n".join(r.getMessage() for r in caplog.records)
    assert "CERT_REQUIRED" in records and "misconfigured" in records, (
        "the deployment diagnosis was discarded rather than relocated to where the operator is"
    )
    assert "no registration entry" in records
    assert "/call/show" in records, "the route the caller asked for reached neither the caller nor the record"


def test_a_validation_refusal_still_names_its_field(svc: tuple[Service, Harness]) -> None:
    """C-12's protected set: naming the failed field is what lets an agent self-correct instead of escalating.

    **Asserted against the `verdicts` array and never against `detail`.** The rendered string names the field too, so
    a substring check on `detail` goes green against the very defect this exists to catch — a store that had
    flattened its typed verdicts back into prose would pass it. The array is the claim: a list of typed refusals,
    each with its own rule id and its own path."""
    service, _hz = svc
    head = base_head(0, "draft")
    head.pop("id")
    head.pop("acceptance")
    status, body = call(
        service, "write", {"new_slug": "names-its-field", "document": {"head": head, "scope": BASE_SCOPE}}, PLANNER_CERT
    )
    assert status == 422 and body["rule"] == "validate.failed"
    verdicts = body["verdicts"]
    assert isinstance(verdicts, list) and verdicts, body
    assert [(v["rule"], v["path"]) for v in verdicts] == [("profile.bdd.rule-without-scenario", "rules.R1")]
    assert all(row_of(v["rule"]).disclosure is Disclosure.FULL for v in verdicts)


def test_a_terse_verdict_inside_a_full_refusal_is_still_terse() -> None:
    """C-12's row for the `verdicts` array: **each entry is disclosed by its own rule id.** The aggregate being
    `full` is not a way for a terse part to travel whole.

    No such pair exists in the code today — every validation family is `full` — so it is built by hand here rather
    than left unproven, which is the difference between a filter that recurses and one that happens not to have been
    asked to yet."""
    refusal = ValidationRefusal(
        [Refusal("head.typed", "head", "title: Field required"), Refusal("git.failed", "", "fatal: bad object")]
    )
    payload = refusal.payload()
    assert payload["verdicts"] == [
        {"rule": "head.typed", "path": "head", "detail": "title: Field required"},
        {"rule": "git.failed"},
    ]
    assert "fatal: bad object" not in json.dumps(payload)


def test_the_two_responses_whose_words_were_not_ours_are_authored(
    svc: tuple[Service, Harness], caplog: pytest.LogCaptureFixture
) -> None:
    """C-12: **we ship no words we did not write.** `service.arguments` returned Python's exception text truncated
    to 200 characters; `service.malformed` returned h11's. Both are now authored, and both originals reach the
    record — which is the half that makes trimming a relocation rather than a loss.

    (`service.malformed` needs a real parser to fail, so its arm is in `test_edge.py`; this proves the shape and the
    floor at the service layer, where the argument handler is.)"""
    service, _hz = svc
    with caplog.at_level("WARNING", logger=telemetry.SCOPE):
        response = service.handle(
            Request("POST", "/call/show", b"{not json"), service.registration.credential(PLANNER_CERT)
        )
    body = json.loads(response.body)
    assert response.status == 400 and body["rule"] == "service.arguments"
    assert body["detail"] == "the arguments are not the typed arguments this call takes"
    assert "Expecting" not in json.dumps(body), "the JSON parser's own words reached the caller"
    records = "\n".join(r.getMessage() for r in caplog.records)
    assert "JSONDecodeError" in records and "Expecting" in records, "the parser's words were discarded, not recorded"


# ---- the two claims that need a clean interpreter ----------------------------------------------------------------


def _child(source: str, env: Mapping[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """Run one script in a child with this repository importable and nothing else changed."""
    import os

    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(REPO / "packages" / "isidium-store" / "src")
    environment.pop("OTEL_TRACES_EXPORTER", None)
    environment.pop("OTEL_METRICS_EXPORTER", None)
    environment.update(env or {})
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(source)], capture_output=True, text=True, env=environment, timeout=120
    )


def test_with_no_sdk_configured_the_store_reaches_no_network() -> None:
    """**C-11's load-bearing claim, and the one every other isidium part depends on.** A distribution in this
    namespace must never force an SDK, an exporter or an outbound connection on the process that embeds it. Asserted,
    not assumed.

    Three arms, because the first two on their own would pass in a process that had simply not been asked to do
    anything: a full span-and-counter cycle runs, **then** the outbound-connection count is zero, **then** neither
    the SDK nor any exporter is in `sys.modules` — a network call is not the only way to break the promise, and an
    SDK imported at module scope would break it for every embedder's start-up whether or not it ever exported."""
    result = _child(
        """
        import socket, sys
        opened = []
        for name in ("connect", "connect_ex"):
            original = getattr(socket.socket, name)
            setattr(socket.socket, name, lambda self, addr, _o=original, _n=name: (opened.append(addr), _o(self, addr))[1])
        original_create = socket.create_connection
        socket.create_connection = lambda addr, *a, **k: (opened.append(addr), original_create(addr, *a, **k))[1]

        from isidium.store.core import telemetry
        from isidium.store.core.refusal import Refusal, ValidationRefusal

        with telemetry.span(telemetry.CALL_SPAN, **{telemetry.ACTION: "show"}):
            telemetry.record_ok()
        with telemetry.span(telemetry.CALL_SPAN, **{telemetry.ACTION: "write"}):
            Refusal("write.stale", "cards/0001.md", "fetch a fresh base").payload()
            ValidationRefusal([Refusal("head.typed", "head", "title: Field required")]).payload()
        telemetry.HANDSHAKE_REFUSED.add(1, {telemetry.REASON: "expired"})
        telemetry.CONNECTION_REFUSED.add(1, {telemetry.REASON: "ceiling"})
        telemetry.CERTIFICATE_ABSENT.add(1)

        sdk = sorted(m for m in sys.modules if m.startswith("opentelemetry.sdk") or ".exporter." in m)
        print("OPENED", opened)
        print("SDK", sdk)
        """
    )
    assert result.returncode == 0, result.stderr
    assert "OPENED []" in result.stdout, result.stdout
    assert "SDK []" in result.stdout, result.stdout


def test_the_console_exporter_prints_spans_to_stderr() -> None:
    """**K2 depends on this working** — it is how the container's first start is diagnosed, and it needs no
    collector, no SigNoz and no egress. `isidium serve` calls `configure()` before it builds anything.

    Two arms: the span reaches stderr *and* it carries the attributes a diagnosis is made of. A console exporter that
    printed the span's name alone would satisfy the first and be useless for the thing it exists for."""
    result = _child(
        """
        from opentelemetry import trace
        from isidium.store.core import telemetry
        from isidium.store.core.refusal import Refusal

        assert telemetry.configure() is True, "the console exporter was asked for and not installed"
        with telemetry.span(telemetry.CALL_SPAN, **{telemetry.ACTION: "show", telemetry.TENANT: "sartor"}):
            Refusal("show.unknown", "", "no such card").payload()
        trace.get_tracer_provider().shutdown()
        """,
        env={"OTEL_TRACES_EXPORTER": "console"},
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "", f"the spans went to stdout, not stderr: {result.stdout[:200]}"
    assert telemetry.CALL_SPAN in result.stderr, result.stderr[:500]
    printed = result.stderr
    assert '"isidium.action": "show"' in printed and '"isidium.tenant": "sartor"' in printed, printed[:800]
    assert '"isidium.rule": "show.unknown"' in printed, printed[:800]
    assert '"status_code": "ERROR"' in printed, printed[:800]


def test_the_default_is_no_exporter_at_all() -> None:
    """Upstream's default for `OTEL_TRACES_EXPORTER` is `otlp`; ours is `none`. Following upstream would make
    installing the `[telemetry]` extra an egress decision taken by a wheel rather than by the deployment, and the
    store's container has an allowlisted egress (7be.2). This is that departure, asserted where it can be read."""
    result = _child(
        """
        from isidium.store.core import telemetry
        print("CONFIGURED", telemetry.configure({}))
        print("ASKED", telemetry.configure({"OTEL_TRACES_EXPORTER": "console"}))
        """
    )
    assert result.returncode == 0, result.stderr
    assert "CONFIGURED False" in result.stdout, result.stdout
    assert "ASKED True" in result.stdout, result.stdout
