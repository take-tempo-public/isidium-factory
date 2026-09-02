"""What a module costs to import, in a fresh interpreter — the measurement K3b's brief requires before and after.

    python tools/import_cost.py
    python tools/import_cost.py isidium.store.client.hook isidium.store.client.cli

Committed for the same reason `tools/mutate.py` was: every chunk that has needed this number so far has written its
own throwaway harness and rediscovered the same three traps.

**The traps, and what this does about them.**

1. *An import happens once per process*, so timing the second one in-process measures nothing. Every sample is a
   fresh child interpreter.
2. *This workstation's noise is one-sided*, so K1d took the **minimum** as the least contaminated estimate. That
   holds for an in-process microbenchmark and **did not hold here** [measured by K3, 2026-08-30]: a run is one
   process spawn, and at 7 repetitions the min of an unchanged module moved 1170 ms → 1800 ms across two runs
   while its median moved 1909 ms → 1882 ms. A lucky spawn is as far from the truth as an unlucky one. Both are
   printed; **read the median** for a before/after comparison and the min for a floor.
3. *The machine drifts, and by more than the effect.* Measuring `cli` before a change and after it, on runs an hour
   apart, compared 2805 ms against 1455 ms while the bare-interpreter baseline itself moved 1246 ms → 667 ms — so
   most of the apparent win was the machine. The baseline is therefore re-measured **interleaved with every
   repetition**, and the column that matters is `net`: the module's cost above a bare interpreter in the same run.
   Compare `net` to `net`; a raw total from another day is not evidence.

The module set each target pulls is the other half, and it is the half that does not drift: a `net` that fell
because the machine was warm looks exactly like one that fell because a dependency went away, and only the module
set can tell them apart. That is the positive discriminator the timing cannot supply on its own — which is why
K3b's brief asks for an assertion on the module set and not on a clock.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "packages" / "isidium-store" / "src"
ENV = {**os.environ, "PYTHONPATH": str(SRC)}

DEFAULT_MODULES = (
    "isidium.store.client.hook",
    "isidium.store.client.cli",
    "isidium.store.client.transport",
)
# The dependencies worth naming: each is seconds on this machine, and each has been imported at some point by a
# path that had no use for it.
HEAVY = ("cryptography", "pydantic", "typer", "httpx", "opentelemetry", "h11")
REPEATS = 15


def _run(code: str) -> float:
    at = time.perf_counter()
    subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, env=ENV)
    return (time.perf_counter() - at) * 1000


def _pulls(module: str) -> list[str]:
    """Which of `HEAVY` are in `sys.modules` after importing `module`, asked of the child that imported it."""
    out = subprocess.run(
        [sys.executable, "-c", f"import {module}, sys; print(' '.join(h for h in {HEAVY!r} if h in sys.modules))"],
        check=True,
        capture_output=True,
        text=True,
        env=ENV,
    )
    return out.stdout.split()


def main(modules: list[str]) -> int:
    samples: dict[str, list[float]] = {m: [] for m in ["(bare interpreter)", *modules]}
    for _ in range(REPEATS):  # interleaved, so drift lands on the baseline and the targets alike
        samples["(bare interpreter)"].append(_run("pass"))
        for module in modules:
            samples[module].append(_run(f"import {module}"))

    bare = sorted(samples["(bare interpreter)"])
    floor = bare[len(bare) // 2]
    print(f"{REPEATS} fresh interpreters per row; `net` is the MEDIAN over the bare floor — compare net to net")
    print(f"{'module':<38}{'min':>9}{'median':>9}{'net':>9}   pulls")
    for name, got in samples.items():
        got.sort()
        low, mid = got[0], got[len(got) // 2]
        net = "" if name.startswith("(") else f"{mid - floor:>8.0f}ms"
        pulls = "" if name.startswith("(") else ", ".join(_pulls(name)) or "(none of the heavy set)"
        print(f"{name:<38}{low:>7.0f}ms{mid:>7.0f}ms{net:>9}   {pulls}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:] or list(DEFAULT_MODULES)))
