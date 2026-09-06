"""OpenTelemetry, against the **API** and never the SDK — the foundation every later chunk instruments against
(C-11, ruled 7bg.12).

**The library/application split is the design, not a detail.** This module imports `opentelemetry` (the API
distribution) only. With no SDK configured the tracer and the meter are no-ops that reach **no network** — that is the
half other systems in this namespace copy, because a distribution must never force an exporter, an SDK or an outbound
connection on the process that embeds it. The SDK and the OTLP exporter are the `[telemetry]` extra, supplied by the
deployment; `configure()` below is the only place this package ever names them, and it does nothing unless the
deployment asked.

**"No egress" is the claim, not "free"** [C-11, measured 2026-08-29]. A no-op `start_as_current_span` costs about
20 µs against a 0.13 µs baseline — the context attach dominates. At this design's volume (≈3 store calls per card
lifetime, 03 §9.6) that is nil. It stops being nil the moment a span meets a loop, so **there is no span inside a loop
over governed paths or journal rows** and there must never be one.

**The vocabulary is the journal's own** — `subject / action / resource / context` (03b §2) — so isidium G7's policy
engine is a swap rather than a retrofit. The outcome is the span's *status*; the refusal's rule id is an *attribute*;
neither is a formatted string (C-2).

**Three streams stay separate.** Telemetry leaves the process; the hash-chained journal does not. Governed document
content, prose and key material are never attributes, and a telemetry id never enters hashed content (C-9) — K6 joins
on trace context rather than inventing a correlation id of its own.

**The unconditional floor.** Trimming a refusal (C-12) only relocates information if something catches it, and a span
no-ops without an SDK. So the withheld words go to a **log record**, which always runs: `logging`'s last-resort
handler puts a WARNING on stderr with nothing configured at all. `withheld()` is that floor.
"""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from typing import Any, Final

from opentelemetry import metrics, trace
from opentelemetry.trace import Span, Status, StatusCode

SCOPE: Final = "isidium.store"

# ---- the attribute vocabulary (03b §2) ---------------------------------------------------------------------------
# caller = subject, the verb = action, the paths = resource. Named once here so no call site spells a key.
SUBJECT: Final = "isidium.subject"
ACTION: Final = "isidium.action"
RESOURCE: Final = "isidium.resource"
TENANT: Final = "isidium.tenant"
GRANT: Final = "isidium.grant"
RULE: Final = "isidium.rule"  # the refusal's rule id (C-5) — an attribute, never part of the span's name
REASON: Final = "isidium.reason"  # a typed classification: `Refused` at the edge, the admission bound's own name

# ---- the span names ----------------------------------------------------------------------------------------------
# One span per phase (C-11). Three phases exist: the edge's request, the call it dispatches, and — inside a governed
# write — the store's synchronisation with the remote `main` (K9). The third is named separately rather than folded
# into the call because it is the one phase that leaves the process for a reason unrelated to the caller's request:
# an operator reading a slow write needs to see the round trip as its own span, not as time missing from the call.
REQUEST_SPAN: Final = "isidium.store.request"
CALL_SPAN: Final = "isidium.store.call"
SYNC_SPAN: Final = "isidium.store.sync"
# K6b: the stop — the listener closed, the calls in flight drained (or not) inside the grace. Its own span for the
# same reason the sync has one: an operator reading a slow stop should see the drain as a phase, not as time missing.
STOP_SPAN: Final = "isidium.store.stop"
DRAINED: Final = "isidium.drained"  # on the stop span: whether every connection finished inside the grace
# K7a (F17): on the fast-forward sync span — the store's own ref was ahead of the remote's tip and stayed where it
# was. Not a refusal: a write whose push failed leaves exactly this (its row is pending and the next push carries
# it), but an operator reading a sync that recorded `OK` could not see it, and it is the state F2 grew from.
DIVERGED: Final = "isidium.diverged"

_tracer = trace.get_tracer(SCOPE)
_meter = metrics.get_meter(SCOPE)
_log = logging.getLogger(SCOPE)

# ---- the counters ------------------------------------------------------------------------------------------------
# **Metrics, not rows, for anything an unauthenticated peer can trigger** (C-11): a record per hostile connection is a
# denial of service through the logging. The first three are exactly that surface — each fires before the store knows
# who is asking, and each can be driven at will by a peer holding nothing.
HANDSHAKE_REFUSED: Final = _meter.create_counter(
    "isidium.store.handshake.refused",
    unit="{connection}",
    description="TLS handshakes the store refused, by typed reason (Q1: the refusal is a value, in every port)",
)
CONNECTION_REFUSED: Final = _meter.create_counter(
    "isidium.store.connection.refused",
    unit="{connection}",
    description="connections refused at admission, by which bound was met (Q4)",
)
CERTIFICATE_ABSENT: Final = _meter.create_counter(
    "isidium.store.certificate.absent",
    unit="{connection}",
    description="handshakes that completed with no peer certificate — the store is misconfigured if this moves",
)
# Post-identification: the peer holds a certificate this CA issued, so this one is bounded by the registration and is
# not the denial-of-service surface the three above are.
REFUSED_CALLS: Final = _meter.create_counter(
    "isidium.store.refusal",
    unit="{call}",
    description="refusals returned to a caller the handshake admitted, by rule id",
)


@contextmanager
def span(name: str, **attributes: Any) -> Generator[Span]:
    """One phase, as a span. Attributes known at the start are passed here; the rest are set as they are learned."""
    with _tracer.start_as_current_span(name, attributes=attributes) as sp:
        yield sp


def record_refusal(rule: str) -> None:
    """The outcome of a refusal, on the span that is running and on the counter.

    Called from `Refusal.payload()` — the **one** constructor every caller-facing refusal passes through (C-12) — so
    every door records the same fact in the same shape instead of each door remembering to. The rule id is an
    attribute and the outcome is the span's status, which is C-11's own sentence about how a refusal is recorded."""
    current = trace.get_current_span()
    current.set_attribute(RULE, rule)
    current.set_status(Status(StatusCode.ERROR, rule))
    REFUSED_CALLS.add(1, {RULE: rule})


def record_refusal_on(sp: Span, rule: str) -> None:
    """A refusal on an **inner** span, without the counter — the shape `record_refusal` cannot take.

    `record_refusal` is the *door's* recorder: it fires from `Refusal.payload()`, once per call, and moves
    `isidium.store.refusal`. An inner span (K9's fetch, fast-forward and rebuild) exits before the refusal reaches
    that door, so its own status would otherwise stay unset — indistinguishable from a phase that succeeded. This
    writes the same two facts C-11 asks for, the outcome as the status and the rule id as an attribute, and
    deliberately does **not** touch the counter: the door records the call, and one refused write is one refusal.
    """
    sp.set_attribute(RULE, rule)
    sp.set_status(Status(StatusCode.ERROR, rule))


def current_trace() -> tuple[str, str] | None:
    """The running span's identity as W3C hex — `(trace_id, span_id)` — or `None` when no span is running: no SDK
    installed, or a store driven directly rather than through the edge.

    **This is how K6 joins the journal on trace context without inventing a correlation id** (C-9, 7bg.12). The
    journal never imports telemetry; the store reads this pair here and hands it to the row as data, where it is
    kept **beside** the hashed content — the column `sig` already lives in — and never inside it. The chain therefore
    hashes the same bytes whether or not a deployment configured an exporter, and an operator can go from a journal
    row to its span and back."""
    ctx = trace.get_current_span().get_span_context()
    if not ctx.is_valid:
        return None
    return format(ctx.trace_id, "032x"), format(ctx.span_id, "016x")


def record_ok() -> None:
    """The other outcome, said out loud. OpenTelemetry treats an unset status as "no error reported", which is also
    what a span that crashed before it could report anything looks like; the store knows the difference, so it says
    so — and a test can then assert the outcome rather than the absence of one."""
    trace.get_current_span().set_status(Status(StatusCode.OK))


def withheld(rule: str, path: str, detail: str) -> None:
    """**The floor under C-12.** The words a refusal does not send stay here, where the operator is.

    WARNING rather than DEBUG on purpose: `logging`'s last-resort handler emits WARNING and above to stderr with no
    configuration at all, and "the withheld detail goes to the record" is worth nothing if the record needs a
    deployment step before it exists. This is not the "record per hostile connection" C-11 forbids: a refusal only
    reaches `payload()` after the handshake, so the peer already holds a certificate this CA issued. The
    pre-handshake surface — refused handshakes, the two admission bounds — is counted and never written as rows."""
    if path or detail:
        _log.warning("%s withheld from the caller: path=%r detail=%r", rule, path, detail)


def note(rule: str, detail: str) -> None:
    """Words the store authored over and kept: a foreign parser's own message, an exception's text. Same floor as
    `withheld`, different reason — nothing was trimmed out of a payload, the payload never held it (C-12: "we ship no
    words we did not write … the original text goes to the record")."""
    _log.warning("%s: %s", rule, detail)


# ---- the deployment's half ---------------------------------------------------------------------------------------

_configured = False


def configure(environ: Mapping[str, str] | None = None) -> bool:
    """Install the SDK **only when the deployment asked for one**. Returns whether a provider was installed.

    Read from the standard `OTEL_TRACES_EXPORTER` / `OTEL_METRICS_EXPORTER` variables, with one deliberate departure
    from the OpenTelemetry default: **unset means `none`, not `otlp`**. Upstream's default would make installing the
    `[telemetry]` extra an egress decision taken by a wheel rather than by the deployment, and the store's container
    is deliberately small (7bg.8) with an allowlisted egress (7be.2). `console` is what K2's container uses for its
    first start, because it needs no collector, no SigNoz and no network at all (K2b done-when 6).

    The SDK imports live inside this function because the SDK is an extra: the client half of this distribution
    installs without it, and an import at module scope would make the store's one hard OpenTelemetry dependency the
    application half rather than the API."""
    global _configured
    env = os.environ if environ is None else environ
    traces = env.get("OTEL_TRACES_EXPORTER", "none").strip().lower()
    meters = env.get("OTEL_METRICS_EXPORTER", "none").strip().lower()
    if _configured or (traces in ("", "none") and meters in ("", "none")):
        return False
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource

    resource = Resource.create({SERVICE_NAME: env.get("OTEL_SERVICE_NAME", SCOPE)})
    if traces not in ("", "none"):
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter, SpanExporter

        exporter: SpanExporter
        if traces == "console":
            # stderr, not the default stdout: stdout is a program's answer channel and a container's
            # logs are read off stderr, where the withheld-detail records already go.
            exporter = ConsoleSpanExporter(out=sys.stderr)
        else:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            exporter = OTLPSpanExporter()
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
    if meters not in ("", "none"):
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import (
            ConsoleMetricExporter,
            MetricExporter,
            PeriodicExportingMetricReader,
        )

        metric_exporter: MetricExporter
        if meters == "console":
            metric_exporter = ConsoleMetricExporter(out=sys.stderr)
        else:
            from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter

            metric_exporter = OTLPMetricExporter()
        metrics.set_meter_provider(
            MeterProvider(resource=resource, metric_readers=[PeriodicExportingMetricReader(metric_exporter)])
        )
    _configured = True
    return True
