"""Replay a recorded phase with another model or effort — the model evaluation's one instrument [owner, 2026-10-04].

    python tools/replay.py --home <deploy home> --out <eval dir> --run r-44 --phase review \
        --model claude-sonnet-5-5 --effort high

A run's `job.json` is self-contained: the payload, the policy, the identity and every input the phase read, inline.
So one phase can be run again **outside the ledger** with exactly one thing changed: the agent's `model` and
`effort`. The prompt is set to the newest version the runner image carries for that agent, for the baseline
too, so prompt drift between the recorded runs is not a second variable (vary one variable).

**What it reuses.** The container adapter itself (`container.Container.execute`): the same render, argv, retries,
watchdog and result reading a live phase gets. Two things differ, both stated here:
- its home is the eval directory, so the phase's files land at `<out>/<label>/runs/<run>/<step>/` and never beside
  the live run's;
- the token is read from the tenant's deploy home by `_ReplayContainer._token`, never copied: one secret file, one
  home.

**What it does not touch.** The ledger and the store: their writes are only in `runner._phase`, which this never
calls. Nothing is pushed.

**The tree.** Plan, refute and judge read the run's base; review reads the head the build left; build writes, so it
gets a fresh tree at the base every time. A worktree is created once per (run, commit) and reused by every
read-only replay of it: one `git worktree add`, not one per variant.

**Resumable.** A step whose `result.json` (or `refusal.json`) exists is skipped, so a batch that dies is re-run as
it is.

Everything printed is ASCII (this console is cp1252).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tomllib
from collections.abc import Sequence
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "packages" / "isidium-store" / "src"))
sys.path.insert(0, str(REPO / "packages" / "isidium-factory" / "src"))

from isidium.factory.adapter import AgentSpec, Effort, Input, RunJob  # noqa: E402
from isidium.factory.container import TOKEN_FILE, Container  # noqa: E402
from isidium.factory.tenant import Registration  # noqa: E402
from isidium.store.core.refusal import Refusal  # noqa: E402

READS_HEAD = frozenset({"review"})  # the phases that read the tree the build left, not the base
WRITES = frozenset({"build", "fixup"})  # the phases that write: a fresh tree each time
EFFORTS: tuple[Effort, ...] = ("low", "medium", "high", "xhigh", "max")


def variant(job: RunJob, *, model: str, effort: Effort, prompt: str, worktree: str) -> RunJob:
    """The recorded job with the agent's model, effort and prompt replaced, and the tree it mounts. Nothing else
    moves: the payload, its hash, the inputs, the budgets and the identity are the recorded bytes."""
    agent = job.identity.agent
    row = job.policy.agents[agent]
    agents = {**job.policy.agents, agent: AgentSpec(model=model, effort=effort, tools=row.tools, prompt=prompt)}
    policy = job.policy.model_copy(update={"agents": agents})
    return job.model_copy(update={"policy": policy, "prompt_version": prompt, "worktree": worktree})


def newest(prompts: frozenset[str], agent: str) -> str:
    """The newest prompt the image carries for an agent, from its `<agent>/<version>` label."""
    versions = [int(p.split("/v", 1)[1]) for p in prompts if p.startswith(f"{agent}/v")]
    if not versions:
        raise SystemExit(f"the image carries no prompt for {agent}")
    return f"v{max(versions)}"


def label(model: str, effort: str, tag: str = "") -> str:
    """The variant's directory name: `claude-sonnet-5-5` at `high` is `sonnet-5-5.high`, and a tag (a repeat, a
    planted defect, a chained input) rides after it: `sonnet-5-5.high+M1.2`."""
    name = f"{model.removeprefix('claude-')}.{effort}"
    return f"{name}+{tag}" if tag else name


class _ReplayContainer(Container):
    """The live adapter with its home at the eval directory and its token read from the tenant's."""

    def __init__(self, home: Path, reg: Registration, token_home: Path) -> None:
        super().__init__(home, reg)
        self._token_home = token_home

    def _token(self) -> str:
        return (self._token_home / TOKEN_FILE).read_text(encoding="utf-8").strip()


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


def tree(repo: Path, out: Path, name: str, sha: str, *, fresh: bool) -> Path:
    """A detached worktree at `sha`. The read-only phases share one per (run, commit); a build, or a planted defect,
    gets its own named tree, made again each time, so no variant reads or builds on another's work."""
    path = out / "wt" / name
    if fresh and path.exists():
        _git(repo, "worktree", "remove", "--force", str(path))
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        _git(repo, "worktree", "add", "--detach", str(path), sha)
    return path


def plant(wt: Path, spec: Path, ident: str) -> str:
    """Apply one planted defect (a `[[mutation]]` entry: file, find, replace — the repo's mutation-spec shape) to the
    tree and commit it there, so the review's diff carries it like any other line of the run's. Returns its label."""
    entries = {m["id"]: m for m in tomllib.loads(spec.read_text(encoding="utf-8"))["mutation"]}
    m = entries[ident]
    target = wt / m["file"]
    text = target.read_bytes().decode("utf-8")
    if text.count(m["find"]) != 1:
        raise SystemExit(f"{spec.name} {ident}: `find` matches {text.count(m['find'])} times in {m['file']}")
    target.write_bytes(text.replace(m["find"], m["replace"]).encode("utf-8"))
    _git(wt, "-c", "user.name=replay", "-c", "user.email=replay@localhost", "commit", "-qam", f"plant {ident}")
    return str(m["label"])


def diff_input(wt: Path, base: str) -> Input:
    """The review's `diff` input, made the way `runner._diff` makes it: base to the tree's HEAD, bytes as git printed
    them. Rebuilt for every review replay, because r-38 to r-41 reviewed before the diff was in the job (card 25)."""
    head = subprocess.run(["git", "-C", str(wt), "rev-parse", "HEAD"], check=True, capture_output=True)
    made = subprocess.run(
        ["git", "-C", str(wt), "diff", "--no-ext-diff", "--no-color", base, "HEAD"], check=True, capture_output=True
    )
    content = {
        "base": base,
        "head": head.stdout.decode("ascii").strip(),
        "diff": made.stdout.decode("utf-8", "replace"),
    }
    return Input(name="diff", sha256=_hash(content), content=content)


def _hash(content: object) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(content, sort_keys=True).encode("utf-8")).hexdigest()


def with_inputs(job: RunJob, replaced: Sequence[Input]) -> RunJob:
    """The job with named inputs replaced (or added), the rest in their recorded order."""
    by = {i.name: i for i in replaced}
    kept = [by.pop(i.name, i) for i in job.inputs]
    return job.model_copy(update={"inputs": (*kept, *by.values())})


def ledger_shas(home: Path, run: str) -> tuple[str, str]:
    import sqlite3

    with sqlite3.connect(home / "ledger.sqlite") as db:
        row = db.execute("select base_sha, head_sha from runs where run_id = ?", (run,)).fetchone()
    if row is None or not row[0]:
        raise SystemExit(f"{run}: no base_sha in the ledger")
    return str(row[0]), str(row[1] or "")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    ap.add_argument("--home", type=Path, required=True, help="the tenant's deploy home (job.json, ledger, token)")
    ap.add_argument("--out", type=Path, required=True, help="the eval directory")
    ap.add_argument("--repo", type=Path, default=REPO, help="the repository the worktrees are made from")
    ap.add_argument("--run", required=True)
    ap.add_argument("--phase", required=True, help="the recorded step: plan, refute, judge, build, review")
    ap.add_argument("--model", required=True)
    ap.add_argument("--effort", required=True, choices=EFFORTS)
    ap.add_argument("--prompt", help="the prompt version; default: the newest the image carries for the agent")
    ap.add_argument("--image", help="the runner image; default: the tenant's")
    ap.add_argument("--tag", default="", help="a repeat or condition label for the variant's directory")
    ap.add_argument("--plant", type=Path, help="a mutation-spec toml whose entry is planted before a review")
    ap.add_argument("--plant-id", help="the entry's id in --plant")
    ap.add_argument("--input", action="append", default=[], help="NAME=FILE: replace an input with an artifact JSON")
    a = ap.parse_args(argv)

    recorded = RunJob.model_validate(
        json.loads((a.home / "runs" / a.run / a.phase / "job.json").read_text(encoding="utf-8"))
    )
    reg = Registration.load(a.home)
    if reg is None:
        raise SystemExit(f"{a.home}: no tenant.toml")
    if a.image:
        reg = Registration(reg.allow_software_grade_until, reg.wip, reg.adapter, reg.max_bytes, a.image)
    name = label(a.model, a.effort, a.tag)
    home = a.out / name
    adapter = _ReplayContainer(home, reg, a.home)
    rundir = home / "runs" / a.run / recorded.step
    if (rundir / "result.json").exists() or (rundir / "refusal.json").exists():
        print(f"{a.run} {recorded.step} {name}: done already")
        return 0

    base, head = ledger_shas(a.home, a.run)
    sha = head if recorded.phase in READS_HEAD else base
    own = recorded.phase in WRITES or a.plant is not None
    wt = tree(a.repo, a.out, f"{a.run}-{name}" if own else f"{a.run}-{sha[:12]}", sha, fresh=own)
    planted = plant(wt, a.plant, a.plant_id) if a.plant is not None else ""
    replaced = [_read_input(x) for x in a.input]
    if recorded.phase == "review":
        replaced.append(diff_input(wt, base))
    prompt = a.prompt or newest(adapter.prompts(), recorded.identity.agent)
    job = with_inputs(variant(recorded, model=a.model, effort=a.effort, prompt=prompt, worktree=str(wt)), replaced)
    rundir.mkdir(parents=True, exist_ok=True)
    if planted:
        (rundir / "planted.json").write_text(json.dumps({"id": a.plant_id, "label": planted}), encoding="utf-8")
    try:
        res = adapter.execute(job)
    except Refusal as e:
        if e.rule == "adapter.environment":
            # A limit or a credential is the environment's answer, not the variant's: the harness's own result.json
            # (failed:infra, no spend) is set aside and no refusal is kept, so a resumed batch runs this step again.
            # Found live 2026-10-05, when a session limit's leftovers were read as done on resume.
            if (rundir / "result.json").exists():
                (rundir / "result.json").replace(rundir / "result.environment.json")
            print(f"{a.run} {recorded.step} {name}: refused {e.rule} (set aside for a resume)")
            return 1
        (rundir / "refusal.json").write_text(json.dumps({"rule": e.rule, "detail": str(e)}, indent=2), encoding="utf-8")
        print(f"{a.run} {recorded.step} {name}: refused {e.rule}")
        return 1
    finally:
        if recorded.phase in WRITES:
            # The build's tree is kept for scoring, and its diff (new files included: intent-to-add) is what the
            # scorer reads. The tree is the variant's own scratch worktree, so marking its files touches nothing live.
            subprocess.run(["git", "-C", str(wt), "add", "--intent-to-add", "--all"], check=False, capture_output=True)
            diff = subprocess.run(
                ["git", "-C", str(wt), "diff", sha], check=False, capture_output=True, text=True, encoding="utf-8"
            )
            (rundir / "build.diff").write_text(diff.stdout, encoding="utf-8")
    cost = "?" if res.cost_micro is None else f"{res.cost_micro / 1e6:.2f}"
    print(f"{a.run} {recorded.step} {name}: {res.outcome} ${cost} {res.duration_ms / 60000:.1f}min")
    return 0


def _read_input(arg: str) -> Input:
    name, _, path = arg.partition("=")
    content = json.loads(Path(path).read_text(encoding="utf-8"))
    return Input(name=name, sha256=_hash(content), content=content)


if __name__ == "__main__":
    sys.exit(main())
