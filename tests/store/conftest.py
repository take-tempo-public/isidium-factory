"""A fresh store over the in-memory git double, the SQLite journal in memory, a fake clock and a software signer —
the r6-d6 harness on the real components.

And, since K3 deleted local mode, the two on-disk builders the tests that need a **real** checkout share: a tenant
clone with a bare remote, and a `Store` over it. Three test files had built the checkout identically and a fourth
was about to; the store builder is what "tests construct `Store` directly" (7bg.2) means in practice.
"""

from __future__ import annotations

import copy
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from isidium.store.core.grammar import Document, UpdateBlock
from isidium.store.registry.loader import Registry
from isidium.store.server.gitrepo import GitCli, MemGit
from isidium.store.server.identity import Caller
from isidium.store.server.journal import Journal
from isidium.store.server.signer import SoftwareKey, SoftwareKeyAck
from isidium.store.server.store import NewCard, Store

OWNER = Caller("amodal1@example", "owner")
PLANNER = Caller("sartor-planner@agents.example", "contributor", "amodal1@example")
LANDER = Caller("factory@example", "lander")
REGISTRY = Registry.shipped()


class Clock:
    def __init__(self, t: int) -> None:
        self.t = t

    def __call__(self) -> int:
        self.t += 7
        return self.t


def base_head(cid: int = 42, status: str = "ratified") -> dict[str, Any]:
    return {
        "schema": 1,
        "id": cid,
        "kind": "story",
        "status": status,
        "source": "suggestion",
        "title": "cards check refuses a ratified card with no acceptance block",
        "shape": "bdd",
        "effort": "default",
        "priority": "P1",
        "surfaces": ["client/cards/validator.py", "client/tests/test_validator.py"],
        "refs": [
            "client/cards/validator.py::validate_profile",
            "docs/dev/work/items/0060-cards-check-no-acceptance.md",
        ],
        "see": ["legacy:sartor/0060", "s12"],
        "narrative": {"feature": "cards check refuses a ratified card with no acceptance block"},
        "rules": [
            {
                "id": "R1",
                "text": "A ratified story without a runnable-shaped scenario is a validation error, not a warning",
            }
        ],
        "acceptance": {
            "scenarios": [
                {
                    "id": "S1",
                    "kind": "command",
                    "rule": "R1",
                    "title": "cards check refuses a ratified card with no acceptance block",
                    "context": {"fixture": "client/tests/fixtures/no-acceptance"},
                    "action": {"run": ["python", "-m", "cards", "check"]},
                    "observable": {"exit_code": 1, "stdout_matches": "S-3\\.story\\.acceptance"},
                    "tests": ["client/tests/test_validator.py::test_refuses_missing_acceptance"],
                },
                {
                    "id": "S2",
                    "kind": "test-marker",
                    "rule": "R1",
                    "title": "build hash is key-order independent",
                    "observable": {"test": "client/tests/test_hasher.py::test_key_order_invariant"},
                },
            ]
        },
    }


BASE_SCOPE = (
    "`cards check` must treat a ratified story with no runnable-shaped\n"
    "scenario as an error (`S-3.story.acceptance`), never a warning. Legacy\n"
    "context: sartor item 0060 (see `refs`)."
)
BASE_UPDATES: list[UpdateBlock] = [
    {
        "date": "2026-08-20",
        "title": "filed from the inbox (s12)",
        "body": "Re-authored from legacy 0060 under the bridge.",
    }
]


@dataclass
class Harness:
    st: Store
    signer: SoftwareKeyAck
    realm: SoftwareKeyAck
    clock: Clock
    key: SoftwareKey

    def draft(self, slug: str = "bdd-story", **over: Any) -> int:
        head = base_head(0, "draft")
        head.update(over)
        r = self.st.write(
            NewCard(slug),
            Document(head, {"Scope": BASE_SCOPE, "Updates": copy.deepcopy(BASE_UPDATES)}),
            None,
            None,
            PLANNER,
        )
        assert r.id is not None
        return r.id


# The targets of the base head's `refs` — they must resolve at ratification (1.14); seeded into every test repo.
REF_FILES: dict[str, bytes] = {
    "client/cards/validator.py": b"def validate_profile(head):" + bytes([10]) + b"    return []" + bytes([10]),
    "docs/dev/work/items/0060-cards-check-no-acceptance.md": b"# 0060 legacy item" + bytes([10]),
}


def fresh(tenant: str = "sartor") -> Harness:
    clock = Clock(1_787_000_000)
    key, realm_key = SoftwareKey.generate(), SoftwareKey.generate()
    signer = SoftwareKeyAck(key, clock, time_skew_s=600)
    realm = SoftwareKeyAck(realm_key, clock, time_skew_s=600)
    repo = MemGit()
    repo.commit(dict(REF_FILES), "seed@example", "2026-08-01T00:00:00Z", "seed the ref targets")
    st = Store(
        tenant,
        repo,
        Journal(":memory:", tenant),
        REGISTRY,
        clock,
        signer,
        root="",
        realm_principal="realm-svc@agents.example",
    )
    st.init(
        OWNER,
        software_key_ack="software-grade signatures are acceptable for this tenant for now",
        extra={
            "shapes": {"allowed": ["bdd", "task", "spike", "ears"], "default": "bdd"},
            "effort": {"tiers": ["default"]},
            "time_skew": 600,
            "inbox": {"max_per_run": 10},
        },
    )
    st.bind(realm, signer.key_fpr, "owner", "2026-01-01T00:00:00Z")
    return Harness(st, signer, realm, clock, key)


@pytest.fixture(scope="module")
def hz() -> Harness:
    return fresh()


# ---- on disk: a real checkout and a real store over it (K3) --------------------------------------------------------


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, check=True, text=True).stdout


def tenant_checkout(parent: Path) -> Path:
    """A tenant checkout with a bare remote — sartor's shape, minus sartor, with the `refs` targets seeded.

    **`uploadpack.allowFilter` is set on the remote and it is not optional** (S-9): without it the store's
    `--filter=blob:none` clone is answered with every blob and the footprint tests assert nothing while passing.
    """
    bare = parent / "origin.git"
    git(parent, "init", "--bare", "-b", "main", str(bare))
    git(bare, "config", "uploadpack.allowFilter", "true")
    work = parent / "tenant"
    git(parent, "clone", "-q", str(bare), str(work))
    git(work, "config", "user.name", "seed")
    git(work, "config", "user.email", "seed@example")
    (work / "README.md").write_text("a tenant\n", encoding="utf-8")
    for rel, data in REF_FILES.items():
        (work / rel).parent.mkdir(parents=True, exist_ok=True)
        (work / rel).write_bytes(data)
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "seed")
    git(work, "push", "-q", "origin", "HEAD:main")
    return work


def store_on_disk(checkout: Path, journal: Path, *, tenant: str = "sartor", root: str = "docs/work/") -> Store:
    """A real `Store` over its **own partial bare clone** of the tenant's remote — what `serve` builds, minus the
    socket (7bg.2: *"tests construct `Store` directly"*).

    **The store no longer shares the caller's checkout, and that is the whole of K4.** It clones the checkout's bare
    remote itself, with `--filter=blob:none`, and holds no working tree and no index. `checkout` is still the
    argument because it is what a caller has in hand; the remote is derived from it.

    **A fresh clone per call, on purpose.** It models a restarted container, which is what the deployment does —
    K2's container clones at start — and it is what makes a second `store_on_disk` over the same remote see the
    first one's pushed commits, and see a bypass commit somebody else pushed to `main`. A long-lived store does
    **not** pick such a commit up; that is a finding, recorded in the chunk plan, not something this fixture hides.

    **The registry is the store's own installed one, never the checkout's** (K4's second half). Under a bare clone
    there is no working tree to read `.isidium/schemas` from — and `init` gitignores it anyway — so
    `Registry.for_checkout` would silently fall back to the shipped documents while looking like it had read the
    tenant's. The store resolves the manifest's `schema@version` against what it has installed and refuses
    `config.schema-unknown` when a named version is absent. `Registry.for_checkout` stays the **client's** offline
    path, which is where a working tree actually exists.

    **The signer is the store's own**, generated here. It used to be a key file a client named in
    `.isidium/client.toml` and `LocalTransport` loaded into a store it built in the caller's process; the key now
    lives with the store, in its own container, which is the whole point of deleting that transport.

    `push` is left at `GitCli`'s default because that is what `serve` builds.
    """
    ack = SoftwareKeyAck(SoftwareKey.generate())
    bare = checkout.parent / f"store-{tenant}-{uuid.uuid4().hex[:8]}.git"
    repo = GitCli.clone(checkout.parent / "origin.git", bare, "isidium-store", f"store@{tenant}", root=root)
    return Store(
        tenant,
        repo,
        Journal(journal, tenant),
        REGISTRY,
        lambda: int(time.time()),
        ack,
        root=root,
        software_fprs=frozenset({ack.key_fpr}),
    )


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


def path_of(st: Store, card_id: int) -> str:
    """`Store.path_of` answers `None` for an id it has never seen. Every test that reaches for this is about a
    card it just wrote, so `None` there is the test's own mistake and is asserted rather than handed on as a
    path [K5b, 2026-09-04]."""
    path = st.path_of(card_id)
    assert path is not None, card_id
    return path
