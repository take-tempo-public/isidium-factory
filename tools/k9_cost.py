"""K9's C-8 measurement: what one fetch-and-fast-forward per write actually costs.

    python tools/k9_cost.py                                              # a governed write, before and after
    python tools/k9_cost.py --origin git@github.com:owner/repo.git       # the added round trip, against a real forge

Two measurements, because they answer two different questions and only the first can be made locally.

**The write, before and after.** Against the test harness's own bare origin, one governed write is timed with K9's
sync in place and again with it stubbed out, **interleaved** — K9 write, pre-K9 write, K9 write, … — so a machine
that drifts between the halves drifts through both. The pre-K9 shape is reconstructed by stubbing the two methods
K9 added rather than by checking out the old code, so both halves run on one interpreter, one clone and one origin,
and the difference is the fetch instead of the machine.

**The round trip, against a real forge.** A local origin's fetch is a file copy; a container's is SSH to GitHub, and
that is the number an operator feels. `--origin` clones the named remote filtered and bare into a temporary
directory and times `GitCli.fetch()` alone. It writes nothing and pushes nothing, so it is safe to point at a live
tenant's repository.

**The median, not the minimum** [`project-factory-long-runs`, K3's correction of K1d]. `subprocess` timing is
two-sided noise: a lucky spawn is as far from the truth as an unlucky one. The median is the answer; the min and
max are printed beside it so a reader can see the spread rather than take the number on faith.

Everything printed is ASCII (this console is cp1252) — the prose lives in this docstring, which nothing prints.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "packages" / "isidium-store" / "src"))

from tests.store.conftest import BASE_SCOPE, OWNER, PLANNER, base_head, store_on_disk, tenant_checkout  # noqa: E402

from isidium.store.core.grammar import Document  # noqa: E402
from isidium.store.server.gitrepo import GitCli  # noqa: E402
from isidium.store.server.store import NewCard, Store  # noqa: E402

ROOT = "docs/work/"


def report(name: str, xs: list[float]) -> float:
    median = statistics.median(xs)
    print(f"  {name:<30} median {median:8.1f} ms   min {min(xs):8.1f}   max {max(xs):8.1f}   n={len(xs)}")
    return median


def the_write(reps: int) -> None:
    with tempfile.TemporaryDirectory(prefix="k9-cost-", ignore_cleanup_errors=True) as tmp:
        parent = Path(tmp)
        tenant_checkout(parent)
        st = store_on_disk(parent / "tenant", parent / "journal.sqlite", root=ROOT)
        st.init(OWNER, software_key_ack="ok for the cost run", root=ROOT)

        sync, wrap = Store._sync_to_main, Store._push_or_rebuild

        def no_sync(_self: Store) -> None:
            return None

        def plain_push(self: Store, _changes: Any, _author: str, _at: str, _message: str, sha: str) -> str:
            self.repo.push()
            return sha

        def one(n: int) -> float:
            doc = Document(base_head(0, "draft"), {"Scope": BASE_SCOPE})
            start = time.perf_counter()
            st.write(NewCard(f"cost-{n}"), doc, None, None, PLANNER)
            return (time.perf_counter() - start) * 1000.0

        with_k9: list[float] = []
        without: list[float] = []
        n = 0
        try:
            for _ in range(reps):
                Store._sync_to_main, Store._push_or_rebuild = sync, wrap  # type: ignore[method-assign]
                n += 1
                with_k9.append(one(n))
                Store._sync_to_main = no_sync  # type: ignore[method-assign,assignment]
                Store._push_or_rebuild = plain_push  # type: ignore[method-assign,assignment]
                n += 1
                without.append(one(n))
        finally:
            Store._sync_to_main, Store._push_or_rebuild = sync, wrap  # type: ignore[method-assign]

        # **The sync alone, and it is the number to quote.** A whole write spawns a dozen gits, so the difference
        # of two write medians at n=7 carries every one of their spreads; measured that way here it read 1554 ms
        # against a 503 ms sum of its own parts. The sync is idempotent against an unmoved remote and touches
        # nothing, so it can be run on its own as many times as the answer needs.
        direct: list[float] = []
        for _ in range(reps * 3):
            start = time.perf_counter()
            st._sync_to_main()
            direct.append((time.perf_counter() - start) * 1000.0)

        print("one governed write, against the harness's local bare origin:")
        a = report("with K9 (a fetch per write)", with_k9)
        b = report("pre-K9 (no fetch)", without)
        print(f"  the difference of the two write medians: {a - b:.1f} ms -- noisy, see the sync's own row")
        print("what K9 actually adds, timed on its own:")
        report("the sync (fetch + rev-parse)", direct)
        # the batch reader and the journal hold handles into the temporary directory; Windows will not
        # delete a file another process has open, and an unclosed one turns a finished run into a traceback
        assert isinstance(st.repo, GitCli)
        st.repo.close()
        st.journal.db.close()


def the_round_trip(origin: str, reps: int) -> None:
    with tempfile.TemporaryDirectory(prefix="k9-fetch-", ignore_cleanup_errors=True) as tmp:
        clone = Path(tmp) / "store.git"
        start = time.perf_counter()
        repo = GitCli.clone(origin, clone, "isidium-store", "store@cost", root=ROOT)
        print(f"clone (filtered, bare): {(time.perf_counter() - start) * 1000.0:8.1f} ms   footprint={repo.footprint}")
        times: list[float] = []
        for _ in range(reps):
            start = time.perf_counter()
            repo.fetch()
            times.append((time.perf_counter() - start) * 1000.0)
        print(f"one fetch of an unmoved `main`, against {origin}:")
        report("fetch", times)
        repo.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--origin", default=None, help="a real remote to time a fetch against; nothing is written to it")
    ap.add_argument("--reps", type=int, default=7)
    args = ap.parse_args()
    if args.origin is None:
        the_write(args.reps)
    else:
        the_round_trip(args.origin, args.reps)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
