"""The suite-wide fixtures: the OpenTelemetry SDK, installed once per session and shared by every package's tests
[moved here by V1, 2026-09-10]. It lived in `tests/store/conftest.py`; a second package that imported the fixture
registered a second instance, whose `set_tracer_provider` the SDK ignored (the first provider stays), so its
exporter saw nothing and a span test that passed alone failed in the suite. One definition, at the root, is the
fix; the store's conftest re-exports the class for the tests that annotate with it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

# ---- OpenTelemetry, installed once for the whole session ---------------------------------------------------------
#
# The instruments in `core/telemetry.py` are created at import time against the API's proxy tracer and meter, and
# they bind to whichever provider is installed **afterwards** — verified, and the reason a test can install the SDK
# late. The providers are process-global and OpenTelemetry keeps the first one set, so they are installed here, once,
# rather than per test file: `test_edge.py` and `test_telemetry.py` both read them and neither may win a race with
# the other.
#
# This gives the suite a real SDK. The **absence** of one — C-11's "no SDK configured, no network" claim — cannot be
# asserted in this process for that reason, and is proven in a subprocess instead (`test_telemetry.py`).


@dataclass(frozen=True)
class Telemetry:
    """The spans and the counters the store emitted, read back in memory."""

    exporter: Any
    reader: Any

    def spans(self, name: str | None = None) -> list[Any]:
        got = list(self.exporter.get_finished_spans())
        return [s for s in got if name is None or s.name == name]

    def clear(self) -> None:
        self.exporter.clear()

    def count(self, instrument: str, **attributes: str) -> int:
        """The counter's total for one attribute set, or 0 when it has never been added to.

        Read as a **total**, and tests take a difference across the thing they are testing: the reader is cumulative
        and the suite shares one process, so an absolute value would be a claim about every test that ran before."""
        total = 0
        data = self.reader.get_metrics_data()
        for rm in getattr(data, "resource_metrics", ()):
            for sm in rm.scope_metrics:
                for metric in sm.metrics:
                    if metric.name != instrument:
                        continue
                    for point in metric.data.data_points:
                        if all(point.attributes.get(k) == v for k, v in attributes.items()):
                            total += int(point.value)
        return total


@pytest.fixture(scope="session")
def otel() -> Telemetry:
    from opentelemetry import metrics as _metrics
    from opentelemetry import trace as _trace
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    _trace.set_tracer_provider(provider)
    reader = InMemoryMetricReader()
    _metrics.set_meter_provider(MeterProvider(metric_readers=[reader]))
    return Telemetry(exporter, reader)
