"""Card 32: a fixup behind an aggregating required check is handed the failed jobs of that check's workflow run
attempt, not only the aggregator's echo. Every test drives `GitHub.failed_jobs` through a fake transport."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from isidium.factory.forge import FailedJob
from isidium.factory.github import BACKOFF, MAX_LEG_JOBS, GitHub

from .test_v4a import Disk, disk

__all__ = ["disk"]  # the V4a tenant, built once for this module too

NAMED = 555  # the aggregating check's job id
RUN = 77
ATTEMPT = 2
STEP_START = "2026-10-02T12:00:10Z"
STEP_END = "2026-10-02T12:00:20Z"


def _inside(job_id: int) -> list[str]:
    return [f"2026-10-02T12:00:12.{i:07d}Z job {job_id} failing step {i}" for i in range(250)]


def _log(job_id: int) -> str:
    before = [f"2026-10-02T12:00:05.{i:07d}Z job {job_id} earlier step {i}" for i in range(5)]
    after = [f"2026-10-02T12:00:30.{i:07d}Z job {job_id} later step {i}" for i in range(5)]
    return "\n".join([*before, *_inside(job_id), *after]) + "\n"


def _want(name: str, job_id: int) -> FailedJob:
    return FailedJob(name, f"step of {job_id}", "\n".join(_inside(job_id)[-200:]))


def _steps(job_id: int) -> list[dict[str, str]]:
    return [
        {
            "name": "set up",
            "conclusion": "success",
            "started_at": "2026-10-02T12:00:00Z",
            "completed_at": "2026-10-02T12:00:09Z",
        },
        {"name": f"step of {job_id}", "conclusion": "failure", "started_at": STEP_START, "completed_at": STEP_END},
    ]


def _job(job_id: int, name: str, conclusion: str = "failure") -> dict[str, Any]:
    return {"id": job_id, "name": name, "status": "completed", "conclusion": conclusion, "steps": _steps(job_id)}


class Forge:
    """The fake: one aggregating Actions check at `abc`, its run's listing per attempt, and a log per job id."""

    def __init__(
        self,
        repo: str,
        listing: list[dict[str, Any]],
        *,
        runs_status: int = 200,
        named: dict[str, Any] | None = None,
    ):
        self.repo = repo
        self.listing = listing
        self.runs_status = runs_status
        self.named = named if named is not None else {"run_id": RUN, "run_attempt": ATTEMPT, "steps": _steps(NAMED)}
        self.seen: list[str] = []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        path, repo = req.url.path, self.repo
        self.seen.append(path)
        if path == f"{repo}/commits/abc/check-runs":
            actions = {"slug": "github-actions"}
            runs = [{"name": "gate", "status": "completed", "conclusion": "failure", "id": NAMED, "app": actions}]
            return httpx.Response(200, json={"check_runs": runs})
        if path == f"{repo}/actions/jobs/{NAMED}":
            return httpx.Response(200, json=self.named)
        if path == f"{repo}/actions/runs/{RUN}/attempts/{ATTEMPT}/jobs":
            if self.runs_status != 200:
                return httpx.Response(self.runs_status, json={"message": "no"})
            return httpx.Response(200, json={"jobs": self.listing})
        if path == f"{repo}/actions/runs/{RUN}/attempts/1/jobs":
            return httpx.Response(200, json={"jobs": [_job(900, "stale leg")]})
        if path.startswith(f"{repo}/actions/jobs/") and path.endswith("/logs"):
            return httpx.Response(200, text=_log(int(path.split("/")[-2])))
        return httpx.Response(404, json={"message": "not found: " + path})

    def logs(self) -> list[str]:
        return [p for p in self.seen if p.endswith("/logs")]


def _driver(
    disk: Disk, fake: Callable[[httpx.Request], httpx.Response], sleep: Callable[[float], None] = lambda s: None
) -> GitHub:
    return GitHub(disk.ctx, transport=httpx.MockTransport(fake), sleep=sleep)


def _forge(disk: Disk, listing: list[dict[str, Any]], **kw: Any) -> Forge:
    return Forge(f"/repos/{disk.ctx.forge.owner}/{disk.ctx.forge.repo}", listing, **kw)


def test_an_aggregators_failed_legs_are_handed_with_their_tails(disk: Disk) -> None:
    fake = _forge(
        disk,
        [_job(NAMED, "gate"), _job(601, "leg (3.12)"), _job(602, "leg (3.13) ok", "success"), _job(603, "leg (3.14)")],
    )
    got = _driver(disk, fake).failed_jobs("abc", ("gate",))
    assert got[1:] == (_want("leg (3.12)", 601), _want("leg (3.14)", 603))
    assert len(got[1].tail.splitlines()) == 200
    assert not any("/attempts/1/" in p for p in fake.seen), "the named job's own attempt is the one read"
    assert not any(p.endswith("/602/logs") for p in fake.seen), "a passing leg's log is not fetched"
    assert fake.logs().count(f"{fake.repo}/actions/jobs/{NAMED}/logs") == 1, "the named job is not read twice"


def test_the_named_check_comes_first_unchanged(disk: Disk) -> None:
    listing = [_job(NAMED, "gate"), _job(611, "z leg"), _job(612, "a leg")]
    alone = _driver(disk, _forge(disk, [], runs_status=404)).failed_jobs("abc", ("gate",))
    assert alone == (_want("gate", NAMED),)
    got = _driver(disk, _forge(disk, listing)).failed_jobs("abc", ("gate",))
    assert got[0] == alone[0]
    assert got == (_want("gate", NAMED), _want("z leg", 611), _want("a leg", 612)), "the forge's order, not sorted"


def test_no_more_than_the_bound_of_legs(disk: Disk) -> None:
    assert MAX_LEG_JOBS >= 1
    listing = [_job(700 + i, f"leg {i}") for i in range(MAX_LEG_JOBS + 3)]
    fake = _forge(disk, listing)
    got = _driver(disk, fake).failed_jobs("abc", ("gate",))
    assert len(got) == 1 + MAX_LEG_JOBS
    assert [j.name for j in got[1:]] == [f"leg {i}" for i in range(MAX_LEG_JOBS)]
    assert len(fake.logs()) == 1 + MAX_LEG_JOBS, "no log is read for a leg past the bound"


def test_a_check_outside_actions_is_returned_as_today(disk: Disk) -> None:
    repo = f"/repos/{disk.ctx.forge.owner}/{disk.ctx.forge.repo}"
    seen: list[str] = []

    def other(req: httpx.Request) -> httpx.Response:
        seen.append(req.url.path)
        runs = [{"name": "ext", "status": "completed", "conclusion": "failure", "id": 9, "app": {"slug": "elsewhere"}}]
        return httpx.Response(200, json={"check_runs": runs})

    assert _driver(disk, other).failed_jobs("abc", ("ext",)) == (FailedJob("ext", None, ""),)
    assert not any(p.startswith(f"{repo}/actions/") for p in seen)

    # (b) the run's listing is not there: the named entry alone, nothing raised, and the run was asked for.
    gone = _forge(disk, [], runs_status=404)
    assert _driver(disk, gone).failed_jobs("abc", ("gate",)) == (_want("gate", NAMED),)
    assert f"{repo}/actions/runs/{RUN}/attempts/{ATTEMPT}/jobs" in gone.seen

    # (c) the forge is down for it: the same, after the driver's own retries.
    waits: list[float] = []
    down = _forge(disk, [], runs_status=500)
    assert _driver(disk, down, waits.append).failed_jobs("abc", ("gate",)) == (_want("gate", NAMED),)
    assert waits == list(BACKOFF)

    # (d) a job that does not say which run it belongs to: nothing to read.
    bare = _forge(disk, [_job(621, "leg")], named={"steps": _steps(NAMED)})
    assert _driver(disk, bare).failed_jobs("abc", ("gate",)) == (_want("gate", NAMED),)
    assert not any("/actions/runs/" in p for p in bare.seen)
