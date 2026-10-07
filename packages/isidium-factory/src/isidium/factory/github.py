"""The GitHub driver — T-C7's *"GitHub first"* — behind `forge.Forge` [V2, 2026-09-10].

**Two halves, one identity.** The git half runs in the tenant checkout the context names, spawn-counted as V1's
gatherer is: `fetch` is two spawns (`git fetch` and the tip out of `FETCH_HEAD`), `branch` one, `changed` one (the
diff), `push` one — **five for fetch → branch → check → push**, held by a test. The API half is seven calls over one
`httpx.Client`: open a pull request, the ruleset's required contexts, a head's check runs, a pull request's state,
— through the Actions API — a commit's failed workflow runs re-requested (`GET .../actions/runs` then one
`POST .../actions/runs/{id}/rerun-failed-jobs` per failed run), and a fixup's reads of a failed job (card 26:
`GET .../actions/jobs/{id}` for its steps and `GET .../actions/jobs/{id}/logs` for its log).

**The token is never in `argv` and never in the checkout's config.** git receives it as an `http.<origin>.extraheader`
through the `GIT_CONFIG_COUNT` environment (a process list shows a command line, not an environment); the API
receives it as the `Authorization` header. `httpx` is imported inside the constructor, as the store's `Transport`
imports it: a process that names the type does not pay for the client (C-13 on code).

**Failure protocol** (T-C7: *"Forge API errors ⇒ retry with backoff ⇒ `environment`"*): a connection error or a `5xx`
waits `BACKOFF[i]` seconds and tries again, `len(BACKOFF)` waits in all, then `forge.unavailable` — the `environment`
event is V3's to emit from that refusal. `403`/`429` with the rate limit exhausted is `forge.rate-limited` naming the
reset; a `422` because a pull request for the head already exists is `forge.pr-exists` naming its number, so a
re-run opens no second one; any other `4xx` is `forge.api` with the status and the forge's message.

**The capability matrix is declared, not probed.** `path_rules` is false because it was measured false
(2026-08-02/03: `file_path_restriction` refused `422` on the Free plan); `merge` and `force_push` are false because
the seam has no such method; the rest are false because they are the recipe's or a later chunk's.
"""

from __future__ import annotations

import base64
import json
import subprocess
import time
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from typing import Any, Final

from isidium.store.core import telemetry
from isidium.store.core.refusal import Refusal

from .context import ForgeKind, TenantContext
from .forge import (
    PASSING,
    TAIL_LINES,
    Capabilities,
    Changed,
    CheckRun,
    Checks,
    FailedJob,
    MergeableState,
    MergeState,
    PullRequest,
    PullRequestSpec,
    changed_of,
)

API_HOST: Final = "api.github.com"
API_VERSION: Final = "2022-11-28"
ACTIONS_APP: Final = "github-actions"  # a check run of this app is an Actions job, and its id is the job's
USER_AGENT: Final = "isidium-factory"
# GitHub's transient classes — a dropped connection, a 5xx — clear in seconds; three waits doubling from one is the
# span its own client libraries use, and a forge down for longer than seven seconds is `environment`, not a retry.
BACKOFF: Final = (1.0, 2.0, 4.0)
# Check runs per page: tenant #0's gate has three required contexts and a head carries under ten runs; one page of
# a hundred is every run there is, so `checks` is one call and not a walk.
PAGE: Final = 100
# Extra failed jobs read per named check. One required check can aggregate a whole matrix that fans out, and every
# leg's last-`TAIL_LINES` tail rides into the fixup's prompt, so the legs are capped: twice today's two-leg fan-out
# leaves room for one more axis, and a run with more failed legs than this hands the first ones the forge lists.
MAX_LEG_JOBS: Final = 4
TIMEOUT: Final = 30.0  # seconds per API call; the calls are small reads and one small write
# A GitHub App's JWT may live ten minutes at most; nine leaves the cap untouched by a slow clock, and `iat` a minute
# back absorbs the skew GitHub itself documents. An installation token lives an hour; renewing five minutes early
# means no push or API call of a run is made with a token that expires inside it.
JWT_TTL: Final = 540
JWT_SKEW: Final = 60
RENEW: Final = 300

SPAN_PUSH: Final = "isidium.factory.forge.push"
SPAN_API: Final = "isidium.factory.forge.api"
GIT_SPAWNS: Final = "isidium.git.spawns"

GITHUB: Final = Capabilities(
    fetch=True,
    push_branch=True,
    open_pr=True,
    checks=True,
    merge_state=True,
    merge=False,
    force_push=False,
    branch_protection_setup=False,
    path_rules=False,
    webhooks=False,
    bot_provisioning=False,
    signed_commit_status=False,
    hosts=("github.com", API_HOST),
)


class GitHub:
    """One driver over one context. `transport` and `sleep` are the test's seams (an `httpx.MockTransport`; a counted
    sleep) and nothing else's."""

    def __init__(
        self,
        ctx: TenantContext,
        *,
        transport: Any = None,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], float] = time.time,
    ) -> None:
        import httpx

        if ctx.forge.host != "github.com":
            raise Refusal("forge.host", ctx.forge.host, "this driver speaks github.com; a GHES host is a second driver")
        self.ctx = ctx
        self._sleep = sleep
        self._now = now
        self._repo = f"/repos/{ctx.forge.owner}/{ctx.forge.repo}"
        self._token: str | None = None  # the installation token, minted on first use (an App) — never the key
        self._expires: float = 0.0
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": USER_AGENT,
        }
        self.http = httpx.Client(base_url=f"https://{API_HOST}", headers=headers, timeout=TIMEOUT, transport=transport)

    # ---- the credential ----------------------------------------------------------------------------------------

    def _bearer(self) -> str:
        """The token every request and every push carries: the static one (`TOKEN`), or an installation token
        minted from the App's key and renewed `RENEW` seconds before it expires — a push must not straddle the hour."""
        ident = self.ctx.identity
        if ident.kind is ForgeKind.TOKEN:
            return ident.secret
        if self._token is None or self._now() + RENEW >= self._expires:
            self._mint()
        assert self._token is not None
        return self._token

    def _jwt(self) -> str:
        """A GitHub App JWT: RS256 over `{iat, exp, iss}` — `iat` a minute back for clock skew, `exp` under GitHub's
        ten-minute cap, `iss` the App id. `cryptography` (the store's dependency) is imported here, lazily, as
        `httpx` is: only an App pays for it, and only when it mints."""
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding, rsa

        ident = self.ctx.identity
        try:
            key = serialization.load_pem_private_key(ident.secret.encode("utf-8"), password=None)
        except ValueError as e:
            raise Refusal("factory.no-forge", "key", f"the App key does not parse: {e}") from None
        if not isinstance(key, rsa.RSAPrivateKey):
            raise Refusal("factory.no-forge", "key", "the App key is not an RSA key")
        now = int(self._now())
        head = _b64(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode())
        body = _b64(
            json.dumps(
                {"iat": now - JWT_SKEW, "exp": now + JWT_TTL, "iss": ident.app_id}, separators=(",", ":")
            ).encode()
        )
        sig = key.sign(f"{head}.{body}".encode("ascii"), padding.PKCS1v15(), hashes.SHA256())
        return f"{head}.{body}.{_b64(sig)}"

    def _mint(self) -> None:
        """One installation token, narrowed to the tenant's repository — the tenant binding is the installation, and
        the token says which repository of it this run may touch."""
        ident = self.ctx.identity
        data = self._call(
            "POST",
            f"/app/installations/{ident.installation_id}/access_tokens",
            json={"repositories": [self.ctx.forge.repo]},
            auth=self._jwt(),
        )
        self._token = str(data["token"])
        self._expires = datetime.fromisoformat(str(data["expires_at"])).timestamp()

    # ---- the git half ------------------------------------------------------------------------------------------

    def _env(self) -> dict[str, str]:
        """The token as an `extraheader` for the origin's scheme and host — in the environment, not the command."""
        basic = base64.b64encode(f"x-access-token:{self._bearer()}".encode()).decode("ascii")
        return {
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": f"http.https://{self.ctx.forge.host}/.extraheader",
            "GIT_CONFIG_VALUE_0": f"Authorization: Basic {basic}",
        }

    def _git(self, *args: str, rule: str, env: Mapping[str, str] | None = None) -> str:
        import os

        full = {**os.environ, **env} if env else None
        r = subprocess.run(["git", *args], cwd=self.ctx.checkout, capture_output=True, text=True, check=False, env=full)
        if r.returncode != 0:
            err = r.stderr.strip()
            raise Refusal(rule, args[0], err.splitlines()[-1] if err else f"git exited {r.returncode}")
        return r.stdout

    def fetch(self, ref: str) -> str:
        self._git("fetch", "-q", self.ctx.forge.remote, ref, rule="forge.git", env=self._env())
        return self._git("rev-parse", "FETCH_HEAD", rule="forge.git").strip()

    def branch(self, name: str, at: str) -> None:
        """A local ref at `at` — never moved if it exists (`forge.branch-exists`): a run's branch is the run's."""
        self._git("branch", "--no-track", name, at, rule="forge.branch-exists")

    def changed(self, base: str, head: str) -> Changed:
        """`base...head`, both ends of a rename (`--no-renames`, K7a: a `git mv` out of the root must name its
        source)."""
        out = self._git("diff", "--name-only", "--no-renames", "-z", f"{base}...{head}", rule="forge.git")
        return changed_of(self.ctx, tuple(p for p in out.split("\0") if p))

    def push(self, name: str) -> Changed:
        """The code-only check, then one push — and **no push at all** when a governed path is in the diff."""
        with telemetry.span(SPAN_PUSH, **{"isidium.branch": name}) as sp:
            ch = self.changed(self.ctx.base_sha, name)
            sp.set_attribute("isidium.governed", len(ch.governed))
            if ch.governed:
                telemetry.record_refusal_on(sp, "forge.governed-path")
                raise Refusal(
                    "forge.governed-path",
                    ch.governed[0],
                    "governed paths are written by the store, never pushed by the factory (X2: code only): "
                    + ", ".join(ch.governed),
                )
            self._git(
                "push",
                "-q",
                self.ctx.forge.remote,
                f"refs/heads/{name}:refs/heads/{name}",
                rule="forge.git",
                env=self._env(),
            )
            sp.set_attribute(GIT_SPAWNS, 2)
            return ch

    # ---- the API half ------------------------------------------------------------------------------------------

    def _call(
        self,
        method: str,
        path: str,
        json: Mapping[str, Any] | None = None,
        *,
        auth: str | None = None,
        text: bool = False,
        **params: Any,
    ) -> Any:
        """One API call with the bearer set **per request** (`auth` is the mint's JWT; every other call carries the
        installation or static token), so no credential sits on the client object between calls. `text` reads a body
        that is not JSON (a job's log): the request follows the forge's redirect to the storage host, and httpx drops
        the `Authorization` header on a cross-origin hop, so the bearer never leaves GitHub."""
        import httpx

        bearer = auth if auth is not None else self._bearer()
        with telemetry.span(SPAN_API, **{"http.request.method": method, "isidium.forge.path": path}) as sp:
            for i, wait in enumerate((*BACKOFF, None)):
                try:
                    r = self.http.request(
                        method,
                        path,
                        json=json,
                        params=params or None,
                        headers={"Authorization": f"Bearer {bearer}"},
                        follow_redirects=text,
                    )
                except httpx.TransportError as e:
                    if wait is None:
                        raise Refusal(
                            "forge.unavailable", path, f"{type(e).__name__} after {len(BACKOFF)} retries"
                        ) from None
                    self._sleep(wait)
                    continue
                sp.set_attribute("http.response.status_code", r.status_code)
                remaining = r.headers.get("x-ratelimit-remaining")
                if remaining is not None:
                    sp.set_attribute("isidium.forge.ratelimit_remaining", remaining)
                if r.status_code >= 500:
                    if wait is None:
                        raise Refusal("forge.unavailable", path, f"{r.status_code} after {len(BACKOFF)} retries")
                    self._sleep(wait)
                    continue
                if r.status_code in (403, 429) and remaining == "0":
                    raise Refusal("forge.rate-limited", path, f"resets at {r.headers.get('x-ratelimit-reset', '?')}")
                if r.status_code >= 400:
                    raise Refusal("forge.api", path, f"{r.status_code}: {_message(r)}")
                sp.set_attribute("isidium.forge.tries", i + 1)
                if text:
                    return r.text
                # `rerun-failed-jobs` answers 201 with no body; every other call here answers a JSON object.
                return r.json() if r.content else None
        raise AssertionError("unreachable: the loop returns or raises")  # pragma: no cover

    def open_pr(self, spec: PullRequestSpec) -> PullRequest:
        body = {"title": spec.title, "body": spec.body, "head": spec.head, "base": spec.base}
        try:
            data = self._call("POST", f"{self._repo}/pulls", json=body)
        except Refusal as r:
            if r.rule == "forge.api" and "already exists" in r.detail:
                existing = self._call(
                    "GET", f"{self._repo}/pulls", head=f"{self.ctx.forge.owner}:{spec.head}", state="open"
                )
                number = int(existing[0]["number"]) if existing else 0
                raise Refusal("forge.pr-exists", spec.head, f"#{number}") from None
            raise
        return PullRequest(int(data["number"]), str(data["html_url"]), str(data["head"]["sha"]))

    def checks(self, sha: str) -> Checks:
        rules = self._call("GET", f"{self._repo}/rules/branches/{self.ctx.base}")
        required: list[str] = []
        for rule in rules:
            if rule.get("type") == "required_status_checks":
                required.extend(str(c["context"]) for c in rule.get("parameters", {}).get("required_status_checks", []))
        runs = self._call("GET", f"{self._repo}/commits/{sha}/check-runs", per_page=PAGE)
        return Checks(
            tuple(required),
            tuple(CheckRun(str(x["name"]), str(x["status"]), x.get("conclusion")) for x in runs.get("check_runs", [])),
        )

    def merge_state(self, number: int) -> MergeState:
        pr = self._call("GET", f"{self._repo}/pulls/{number}")
        state = str(pr.get("mergeable_state", "unknown"))
        try:
            ms = MergeableState(state)
        except ValueError:
            raise Refusal(
                "forge.api", f"pulls/{number}", f"mergeable_state {state!r} is not one this driver knows"
            ) from None
        return MergeState(
            str(pr["head"]["sha"]), pr.get("mergeable"), ms, bool(pr.get("merged")), pr.get("merge_commit_sha")
        )

    def rerun_failed(self, sha: str) -> tuple[int, ...]:
        """R1's rerun request: every completed, failed workflow run at this commit, re-requested through
        `rerun-failed-jobs`. The ids returned are the ones re-requested — `close` waits on them, not on `sha`'s
        checks again read fresh."""
        runs = self._call("GET", f"{self._repo}/actions/runs", head_sha=sha, per_page=PAGE)
        failed = tuple(
            int(r["id"])
            for r in runs.get("workflow_runs", [])
            if r.get("status") == "completed" and r.get("conclusion") not in PASSING
        )
        for run_id in failed:
            self._call("POST", f"{self._repo}/actions/runs/{run_id}/rerun-failed-jobs")
        return failed

    def failed_jobs(self, sha: str, names: tuple[str, ...]) -> tuple[FailedJob, ...]:
        """Card 26 R2: each named check at this commit, as a fixup is handed it. One call for the head's check runs
        (the newest per name, as `Checks.latest` takes it), then for each that is an Actions job two more — its steps
        and its log. A check that is not an Actions job has no log this driver can read: it is named, with no step and
        no tail, and the fixup is told that much rather than refused.

        Card 32: a named check that aggregates other jobs echoes their result and nothing more, so for an Actions job
        the other failed jobs of its workflow run attempt follow its entry — in the order the forge lists them, each
        named by its job name, at most `MAX_LEG_JOBS` of them. A run that cannot be read hands the named entry alone."""
        runs = self._call("GET", f"{self._repo}/commits/{sha}/check-runs", per_page=PAGE)
        newest: dict[str, Any] = {}
        for x in runs.get("check_runs", []):
            newest.setdefault(str(x["name"]), x)
        # A job that is itself a named check, or that an earlier named check already handed, is not handed again.
        skip = {int(newest[n]["id"]) for n in names if n in newest}
        out: list[FailedJob] = []
        for name in names:
            run = newest.get(name)
            if run is None or (run.get("app") or {}).get("slug") != ACTIONS_APP:
                out.append(FailedJob(name, None, ""))
                continue
            job = self._call("GET", f"{self._repo}/actions/jobs/{int(run['id'])}")
            out.append(self._read_job(name, int(run["id"]), job.get("steps", [])))
            out.extend(self._legs(job, skip))
        return tuple(out)

    def _read_job(self, name: str, job_id: int, steps: list[Any]) -> FailedJob:
        """One job as a fixup is handed it: its failed step's name and that step's last `TAIL_LINES` lines, or the
        job log's own tail when no step is marked failed. One logs read."""
        log = self._call("GET", f"{self._repo}/actions/jobs/{job_id}/logs", text=True)
        step = next((s for s in steps if s.get("conclusion") == "failure"), None)
        if step is None:
            return FailedJob(name, None, _tail(log.splitlines()))
        window = _window(log.splitlines(), str(step["started_at"]), str(step["completed_at"]))
        return FailedJob(name, str(step["name"]), _tail(window))

    def _legs(self, job: Mapping[str, Any], skip: set[int]) -> list[FailedJob]:
        """The other failed jobs of the named job's own workflow run attempt (the newest run of its name, so the
        latest attempt), one listing call and one logs read per leg. The cap applies before any log is read. This is
        a widening of what the fixup is told, not a gate: a run or a log that cannot be read hands no legs, and the
        refusal (already marked on its `forge.api` span by `_call`) is not raised."""
        run_id, attempt = job.get("run_id"), job.get("run_attempt")
        if run_id is None or attempt is None:
            return []
        try:
            listing = self._call(
                "GET", f"{self._repo}/actions/runs/{int(run_id)}/attempts/{int(attempt)}/jobs", per_page=PAGE
            )
            kept: list[Mapping[str, Any]] = []
            for j in listing.get("jobs", []):
                if len(kept) == MAX_LEG_JOBS:
                    break
                if j.get("status") == "completed" and j.get("conclusion") not in PASSING and int(j["id"]) not in skip:
                    kept.append(j)
            legs = [self._read_job(str(j["name"]), int(j["id"]), j.get("steps", [])) for j in kept]
        except Refusal:
            return []
        skip.update(int(j["id"]) for j in kept)
        return legs

    def capabilities(self) -> Capabilities:
        return GITHUB


def _tail(lines: list[str]) -> str:
    return "\n".join(lines[-TAIL_LINES:])


def _stamp(text: str) -> datetime | None:
    """The leading ISO timestamp of a job-log line (`2026-10-02T12:00:01.1234567Z ...`), or None for a line without
    one — a continuation of the line before it. `fromisoformat` truncates the seven fractional digits GitHub writes."""
    head = text.lstrip("\ufeff").split(" ", 1)[0]
    if not head.endswith("Z"):
        return None
    try:
        return datetime.fromisoformat(head)
    except ValueError:
        return None


def _window(lines: list[str], started: str, completed: str) -> list[str]:
    """The log lines stamped within [`started`, `completed` + 1s) — the step's own, since the jobs API stamps a step
    to the second and its last line lands inside that second. A line with no stamp belongs with the stamped line it
    follows."""
    lo = datetime.fromisoformat(started)
    hi = datetime.fromisoformat(completed) + timedelta(seconds=1)
    inside = False
    out: list[str] = []
    for line in lines:
        at = _stamp(line)
        if at is not None:
            inside = lo <= at < hi
        if inside:
            out.append(line)
    return out


def _b64(b: bytes) -> str:
    """base64url without padding — the JWT's alphabet."""
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _message(r: Any) -> str:
    try:
        data = r.json()
    except ValueError:
        return str(r.text)[:200]
    msg = str(data.get("message", ""))
    errors = data.get("errors") or []
    detail = "; ".join(str(e.get("message", e)) if isinstance(e, dict) else str(e) for e in errors)
    return f"{msg} — {detail}" if detail else msg
