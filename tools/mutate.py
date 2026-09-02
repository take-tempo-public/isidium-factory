"""The mutation harness. One mutation, the whole suite, and the pristine bytes kept **on disk**.

Every chunk of the build plan must mutation-check the security and limit assertions it writes: break the property on
purpose, confirm a test fails, restore, and record which test killed it. Every chunk so far wrote its own throwaway
harness, and each one rediscovered the same three traps. This is that harness, committed, so the traps are the
tool's problem rather than the next agent's.

**The trap this file exists for.** A harness that restores in a `finally` restores nothing when the process is
*killed* — no `finally`, no `atexit`, no signal handler runs on a hard kill. It happened three times while K1d was
being built, and each time it left a broken `Registry.installed` or a disabled agreement check sitting in the
working tree, where the next command would have built on it or committed it. So the pristine bytes are written to
`.mutation-in-flight.json` **before** the file is touched, and **every invocation repairs a tree it finds mutated
before it does anything else**. A kill costs one mutation, never the chunk.

**The other two traps, also the tool's problem now.**

- *Restoring with `git checkout --`.* While a chunk is in progress the working tree is ahead of `HEAD`, so
  `git checkout --` does not undo the mutation, it undoes the chunk. It cost three files in one step once. This
  writes back the exact bytes it snapshotted, with `write_bytes`, which translates nothing — the trap `write_text`
  sets on Windows, where the documents under `docs/` are CRLF and the code is LF.
- *Aiming a mutation at the file you just edited.* A mutation run against the chunk's own tests tells you that file
  is covered, not that your change is. One mutation survived its chunk's test file and died to a test in another.
  **There is deliberately no way to pass a test path to this script**: the target is always the whole suite.

Everything this file PRINTS is ASCII: this console is cp1252, and a harness that dies on its own output is
worse than no harness. The prose lives here in the docstring, which nothing prints.

Usage:

    python tools/mutate.py tools/mutations/k1d.toml            # every mutation in the spec
    python tools/mutate.py tools/mutations/k1d.toml M3 M4      # only these
    python tools/mutate.py --restore                           # repair a tree a killed run left mutated

A spec is TOML, one `[[mutation]]` per property, each naming the file, the exact text to find (it must appear
**once**), and what to put in its place:

    [[mutation]]
    id = "M1"
    label = "`installed` forces every document -- the lazy listing lost"
    file = "packages/isidium-store/src/isidium/store/registry/loader.py"
    find = "        return frozenset(self._slots)"
    replace = "        return frozenset(self.addresses)"

**On this repository's suite, run one mutation per invocation.** The serial suite is ~226 s and the killers usually
live in `tests/unit`, which collects last, so `-x` saves nothing: a mutation costs a whole pass either way. The
parallel default below cuts that materially.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import signal
import subprocess
import sys
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import FrameType

REPO = Path(__file__).resolve().parent.parent

# The pristine bytes of the file currently mutated, on disk rather than in this process's memory — see the module
# docstring. Gitignored; its presence means a run did not finish, and the next invocation repairs it.
STATE = REPO / ".mutation-in-flight.json"

# `--dist loadfile` is not decoration: `tests/store/test_scenarios.py` shares state across its own tests, and five
# of them fail when they are split across workers. Per-file distribution keeps each file whole on one worker, which
# is the property those tests actually depend on. Plain `-n 8` reports five failures that are the runner's, not the
# mutation's — which would read as a mutation dying to a test it never touched.
WORKERS = 8  # the author's workstation has 8 cores; more workers only add interpreter startup, which is slow here.
PARALLEL = ["-n", str(WORKERS), "--dist", "loadfile"]

FAILED = re.compile(r"^(?:FAILED|ERROR) (\S+)", re.M)


@dataclass(frozen=True)
class Mutation:
    id: str
    label: str
    path: Path
    find: bytes
    replace: bytes


def load_spec(spec: Path, only: list[str]) -> list[Mutation]:
    doc = tomllib.loads(spec.read_text(encoding="utf-8"))
    rows = doc.get("mutation") or []
    if not rows:
        raise SystemExit(f"{spec}: no [[mutation]] tables")
    out = [
        Mutation(
            id=str(r["id"]),
            label=str(r["label"]),
            path=REPO / str(r["file"]),
            find=str(r["find"]).encode("utf-8"),
            replace=str(r["replace"]).encode("utf-8"),
        )
        for r in rows
    ]
    ids = [m.id for m in out]
    if len(set(ids)) != len(ids):
        raise SystemExit(f"{spec}: duplicate mutation ids")
    if not only:
        return out
    missing = sorted(set(only) - set(ids))
    if missing:
        raise SystemExit(f"{spec}: no such mutation: {', '.join(missing)}")
    return [m for m in out if m.id in only]


def repair() -> bool:
    """Put back whatever a killed run left mutated. Runs first on **every** invocation, `--restore` included."""
    if not STATE.is_file():
        return False
    saved = json.loads(STATE.read_text(encoding="utf-8"))
    path = REPO / saved["file"]
    pristine = base64.b64decode(saved["pristine"])
    if hashlib.sha256(pristine).hexdigest() != saved["sha256"]:
        raise SystemExit(f"{STATE}: the saved bytes do not match their own digest; restore {path} by hand")
    if path.read_bytes() != pristine:
        path.write_bytes(pristine)
        print(f"repaired {saved['file']}: a previous run was killed while {saved['id']} was applied")
    STATE.unlink()
    return True


def hold(m: Mutation, pristine: bytes) -> None:
    STATE.write_text(
        json.dumps(
            {
                "id": m.id,
                "file": m.path.relative_to(REPO).as_posix(),
                "sha256": hashlib.sha256(pristine).hexdigest(),
                "pristine": base64.b64encode(pristine).decode("ascii"),
            }
        ),
        encoding="utf-8",
    )


def release(m: Mutation, pristine: bytes) -> None:
    """Restore from the snapshot, then **verify** the restore rather than assume it."""
    m.path.write_bytes(pristine)
    got = hashlib.sha256(m.path.read_bytes()).hexdigest()
    want = hashlib.sha256(pristine).hexdigest()
    if got != want:
        raise SystemExit(f"{m.path} did not restore: {got} != {want}")
    STATE.unlink(missing_ok=True)


def restorer(m: Mutation, pristine: bytes) -> Callable[[int, FrameType | None], None]:
    """A signal handler that puts this mutation back. Built here rather than in the loop so it binds the mutation
    it was made for and not whichever one the loop reached."""

    def on_signal(_sig: int, _frame: FrameType | None) -> None:
        release(m, pristine)
        raise SystemExit(130)

    return on_signal


def run_suite(serial: bool) -> tuple[int, str]:
    argv = [sys.executable, "-m", "pytest", "-q", "--no-header", "-rf", *([] if serial else PARALLEL)]
    p = subprocess.run(argv, cwd=REPO, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def main() -> int:
    ap = argparse.ArgumentParser(
        # ASCII, and deliberately not `__doc__`: this console is cp1252, and a `--help` that raises
        # `UnicodeEncodeError` on an em dash is a tool that fails at the moment it is asked for help.
        # Everything this file prints is ASCII for the same reason; the prose lives in the module docstring.
        description="Break one property on purpose, run the whole suite, restore the file from its own bytes.",
    )
    ap.add_argument("spec", nargs="?", type=Path, help="a TOML file of [[mutation]] tables")
    ap.add_argument("ids", nargs="*", help="mutation ids to run; default all of them")
    ap.add_argument("--restore", action="store_true", help="repair a tree a killed run left mutated, then stop")
    ap.add_argument("--serial", action="store_true", help="run the suite in one process (slower; for a suspect run)")
    args = ap.parse_args()

    found = repair()
    if args.restore:
        if not found:
            print("nothing to repair")
        return 0
    if args.spec is None:
        ap.error("a spec is required unless --restore is given")

    dead, survived = 0, []
    for m in load_spec(args.spec, args.ids):
        pristine = m.path.read_bytes()
        n = pristine.count(m.find)
        if n != 1:
            print(f"{m.id}  {m.label}\n     SKIPPED: its `find` text appears {n} times in {m.path.name}")
            continue

        hold(m, pristine)
        # A Ctrl-C or a SIGTERM restores; a hard kill catches nothing at all, which is what `hold` is for.
        on_signal = restorer(m, pristine)
        previous = [(s, signal.signal(s, on_signal)) for s in (signal.SIGINT, signal.SIGTERM)]
        try:
            m.path.write_bytes(pristine.replace(m.find, m.replace))
            code, out = run_suite(args.serial)
        finally:
            release(m, pristine)
            for s, handler in previous:
                signal.signal(s, handler)

        killers = sorted({k.group(1) for k in FAILED.finditer(out)})
        if code == 0:
            survived.append(m.id)
            print(f"{m.id}  {m.label}\n     *** SURVIVED *** - the property has no test that can see it")
        else:
            dead += 1
            print(f"{m.id}  {m.label}\n     DIED")
            for k in killers or ["(the suite failed but named no test — read the run by hand)"]:
                print(f"       killed by {k}")
        sys.stdout.flush()

    print(f"\n{dead} died, {len(survived)} survived" + (f": {', '.join(survived)}" if survived else ""))
    return 1 if survived else 0


if __name__ == "__main__":
    raise SystemExit(main())
