"""The forge driver seam (T-C7) — the contract as types and a Protocol; one driver behind it [V2, 2026-09-10].

T-C7's contract, verbatim: *"fetch/clone (read creds); push (bot identity); … PR/MR open with generated body, CI
status read, merge status read; … each driver publishes a capability matrix"*. What v1c's line needs of it through
V6 is here as a `Protocol` of eight methods; what it does not need is **absent from the type, not refused at
runtime**: there is no `merge` (X2 [owner-ratified]: *"the PR merge stays the forge's button — round 14"*), no force
push (the store's rule, *"a store must never hold a force path at all"*, is the factory's too), no delete. A driver
that cannot merge cannot be asked to.

**The code-only check is the store's own predicate** — `client.hook.governed_in`, the matcher the pre-commit hook and
`verify --diff-base` run — so the factory and CI refuse the same path for the same diff by construction, and a
governed change never reaches the forge to be refused there.

The values are frozen dataclasses, as the payload's are: the wire is V4's seam, and pydantic wraps it there.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from isidium.store.client.hook import governed_in

from .context import TenantContext


class Verdict(Enum):
    """The required checks, read together: every one green; any one still running; any one failed."""

    GREEN = "green"
    PENDING = "pending"
    RED = "red"


class MergeableState(Enum):
    """The closed set GitHub answers for a pull request's `mergeable_state` — typed, not a string (C-2)."""

    CLEAN = "clean"
    BLOCKED = "blocked"
    BEHIND = "behind"
    DIRTY = "dirty"
    UNSTABLE = "unstable"
    UNKNOWN = "unknown"
    HAS_HOOKS = "has_hooks"
    DRAFT = "draft"


# A check-run's conclusions that count as passing the gate — GitHub's own required-check rule counts these three.
PASSING: frozenset[str] = frozenset({"success", "neutral", "skipped"})


@dataclass(frozen=True)
class CheckRun:
    name: str
    status: str  # queued | in_progress | completed
    conclusion: str | None  # success | failure | neutral | cancelled | skipped | timed_out | action_required


@dataclass(frozen=True)
class Checks:
    """The gate's required contexts and the runs that exist for the head; the verdict is over the **required** names,
    so a required check that never ran reads `PENDING`, never `GREEN`."""

    required: tuple[str, ...]
    runs: tuple[CheckRun, ...]

    @property
    def verdict(self) -> Verdict:
        latest: dict[str, CheckRun] = {}
        for run in self.runs:  # the API lists the newest first; the first seen per name is the one that counts
            latest.setdefault(run.name, run)
        pending = False
        for name in self.required:
            got = latest.get(name)
            if got is None or got.status != "completed":
                pending = True
            elif got.conclusion not in PASSING:
                return Verdict.RED
        return Verdict.PENDING if pending else Verdict.GREEN


@dataclass(frozen=True)
class MergeState:
    head: str
    mergeable: bool | None
    state: MergeableState
    merged: bool
    merge_commit: str | None


@dataclass(frozen=True)
class PullRequestSpec:
    title: str
    body: str
    head: str
    base: str


@dataclass(frozen=True)
class PullRequest:
    number: int
    url: str
    head: str


@dataclass(frozen=True)
class Changed:
    """What a branch changes against its base: every path, and the governed ones among them (the refusal's list)."""

    paths: tuple[str, ...]
    governed: tuple[str, ...]


@dataclass(frozen=True)
class Capabilities:
    """T-C7's matrix, one boolean per contract row the line reads, and the hosts the driver reaches (the egress
    allowlist is agent-station's by pointer; this is what it would list)."""

    fetch: bool
    push_branch: bool
    open_pr: bool
    checks: bool
    merge_state: bool
    merge: bool
    force_push: bool
    branch_protection_setup: bool
    path_rules: bool
    webhooks: bool
    bot_provisioning: bool
    signed_commit_status: bool
    hosts: tuple[str, ...]


class Forge(Protocol):
    """The seam. `push` refuses `forge.governed-path` before any spawn when the branch changes a governed path."""

    def fetch(self, ref: str) -> str: ...
    def branch(self, name: str, at: str) -> None: ...
    def changed(self, base: str, head: str) -> Changed: ...
    def push(self, name: str) -> Changed: ...
    def open_pr(self, spec: PullRequestSpec) -> PullRequest: ...
    def checks(self, sha: str) -> Checks: ...
    def merge_state(self, number: int) -> MergeState: ...
    def capabilities(self) -> Capabilities: ...


def changed_of(ctx: TenantContext, paths: tuple[str, ...]) -> Changed:
    """The diff's paths sorted into all and governed — the one predicate, the context's own rows (C-13)."""
    return Changed(paths, tuple(governed_in(ctx.root, ctx.governed, paths)))


TRAILER = "Isidium-Branch"


def pr_text(ctx: TenantContext, branch: str, changed: Changed) -> PullRequestSpec:
    """T-C7's *"PR/MR open with generated body"* — generated from the context and the diff, nothing narrated. The
    card and the run id enter here in V3, where they exist; the `Batch:` trailer is V6's (Q-W10 (b))."""
    files = "\n".join(f"- `{p}`" for p in changed.paths) or "- (no files)"
    body = (
        f"Tenant `{ctx.tenant}`; base `{ctx.base}` at `{ctx.base_sha}`; head `{branch}`.\n\n"
        f"Files changed:\n{files}\n\n"
        f"Opened by isidium-factory as `{ctx.identity.login}`; code only — no governed path is in this diff.\n\n"
        f"{TRAILER}: {branch}\n"
    )
    return PullRequestSpec(title=branch, body=body, head=branch, base=ctx.base)
