"""The advisory gate: every version in `uv.lock` is asked of OSV, in one call, and a hit fails the build.

**Why this is a script and not an action** (K5, ruling 7bg.5: *"monitoring with CI for upstream updates"*). The same
reason the governed-path gate was one until K12 shipped it as `isidium verify`: checkout -> one command is the shape
that runs unchanged on another forge's runner, and this project's forge is not a settled thing. It imports nothing
outside the standard library — not even the store — so it needs no install step and cannot be broken by the very
resolution it is checking.

**What it reads.** `uv.lock`, and only the packages whose `source` is a registry. A workspace member has no upstream
to have an advisory against; a path or git source is not a PyPI name and OSV would answer about a stranger.

**One call, not one per package** (the house efficiency rule, C-8). OSV's `querybatch` takes every (name, version)
pair in a single POST and answers positionally; the per-advisory `GET /v1/vulns/{id}` that follows runs only over
the ids that actually came back, which on a clean lock is none. The naive shape here — a query per locked package —
is ~45 round trips on this lock and grows with the dependency tree.

**It cannot pass on silence** (the standing rule). Three positive discriminators, and any of them failing exits 2:
the lock must yield packages at all; OSV must answer with exactly one result per query, positionally; and the batch
carries a **control** — `h11 == 0.14.0`, which is CVE-2025-43859, the advisory this project's own `h11 >= 0.16`
floor was set for. A scanner that reports "clean" because the endpoint moved, the schema changed or the ecosystem
name was wrong reports the control clean too, and that is the failure this catches. The control is not in the lock
and is never counted as a finding.

Exit 0: every locked version clean, and the control found. Exit 1: an advisory against a locked version. Exit 2:
the scan itself could not be trusted.
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

QUERYBATCH = "https://api.osv.dev/v1/querybatch"
VULN = "https://api.osv.dev/v1/vulns/"
ECOSYSTEM = "PyPI"

# A hosted runner's job has its own timeout; this one exists so a hung socket fails the step with a readable message
# instead of a six-hour cancellation. 30 s is an order of magnitude above the measured round trip (~0.6 s for the
# whole batch, 2026-09-04) and well under any runner's patience.
HTTP_TIMEOUT_S = 30

# The proof that a "clean" answer means the scan worked. `h11 0.14.0` is chunked-terminator leniency behind a
# lenient proxy (CVE-2025-43859), fixed in 0.16.0 — which is why `[server]` declares `h11>=0.16,<1`. Asserting the
# advisory id and not merely "something came back" means a wrong-but-answering endpoint fails too.
CONTROL_NAME = "h11"
CONTROL_VERSION = "0.14.0"
CONTROL_ADVISORY = "GHSA-vqfr-h8mv-ghfj"


def locked_packages(lock_path: Path) -> list[tuple[str, str]]:
    """(name, version) for every locked package that has an upstream to have an advisory against."""
    data: dict[str, Any] = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    found: set[tuple[str, str]] = set()
    for pkg in data.get("package", []):
        if "registry" not in pkg.get("source", {}):
            continue  # a workspace member, or a path/git source: not a name OSV knows
        found.add((str(pkg["name"]), str(pkg["version"])))
    return sorted(found)


def _post(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_S) as response:
        body: dict[str, Any] = json.load(response)
    return body


def _get(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=HTTP_TIMEOUT_S) as response:
        body: dict[str, Any] = json.load(response)
    return body


def query_all(pairs: list[tuple[str, str]]) -> list[list[str]]:
    """Advisory ids per pair, positionally. One POST for the whole batch, plus one per paged-over result."""
    queries = [{"package": {"name": name, "ecosystem": ECOSYSTEM}, "version": version} for name, version in pairs]
    results = _post(QUERYBATCH, {"queries": queries}).get("results", [])
    if len(results) != len(queries):
        raise RuntimeError(f"OSV answered {len(results)} results for {len(queries)} queries; positional read unsafe")

    per_pair: list[list[str]] = []
    for query, result in zip(queries, results, strict=True):
        ids = [str(v["id"]) for v in result.get("vulns", [])]
        # OSV pages a single query only past 1000 advisories. It has never happened here; handling it is cheaper
        # than a silently truncated answer, which is the same defect as passing on silence.
        token = result.get("next_page_token")
        while token:
            page = _post(QUERYBATCH, {"queries": [{**query, "page_token": token}]}).get("results", [{}])[0]
            ids.extend(str(v["id"]) for v in page.get("vulns", []))
            token = page.get("next_page_token")
        per_pair.append(ids)
    return per_pair


def summarise(advisory_id: str) -> str:
    detail = _get(VULN + advisory_id)
    summary = str(detail.get("summary") or detail.get("details") or "").strip().splitlines()
    aliases = ", ".join(str(a) for a in detail.get("aliases", []))
    head = summary[0] if summary else "(no summary)"
    return f"{head} [{aliases}]" if aliases else head


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lock", type=Path, default=Path("uv.lock"), help="the lock to scan (default: ./uv.lock)")
    args = parser.parse_args(argv)

    if not args.lock.is_file():
        print(f"no lock at {args.lock}", file=sys.stderr)
        return 2
    pairs = locked_packages(args.lock)
    if not pairs:
        print(f"{args.lock} named no registry packages — a lock with nothing in it is a wrong lock", file=sys.stderr)
        return 2

    control = (CONTROL_NAME, CONTROL_VERSION)
    try:
        per_pair = query_all([*pairs, control])
    except (urllib.error.URLError, json.JSONDecodeError, RuntimeError, KeyError, TimeoutError) as exc:
        print(f"OSV could not be queried, so nothing was proven: {exc}", file=sys.stderr)
        return 2

    *locked_hits, control_hits = per_pair
    if CONTROL_ADVISORY not in control_hits:
        print(
            f"the control did not reproduce: {CONTROL_NAME} {CONTROL_VERSION} should carry {CONTROL_ADVISORY} and "
            f"OSV returned {control_hits or 'nothing'} — a clean report from this run would mean nothing",
            file=sys.stderr,
        )
        return 2

    findings = [(name, version, ids) for (name, version), ids in zip(pairs, locked_hits, strict=True) if ids]
    print(f"{len(pairs)} locked packages queried against OSV; control {CONTROL_ADVISORY} reproduced")
    if not findings:
        print("no advisory against any locked version")
        return 0

    for name, version, ids in findings:
        for advisory_id in ids:
            print(f"{name} {version}: {advisory_id} — {summarise(advisory_id)}", file=sys.stderr)
    print(f"{len(findings)} locked packages carry an advisory", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
