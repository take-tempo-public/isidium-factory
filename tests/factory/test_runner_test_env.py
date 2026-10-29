"""Card 65 — the runner image carries the lock's test environments on both CI Pythons (R1, R2), and builder v7 tells
the phase to use them and never to install (R4). `r-58` lacked `pytest`, `ruff` and `mypy`, made a venv and installed
them, and a wheel landed in /work.

These tests read files as text and bytes only: no podman, no subprocess, and no skip of any kind (card 61: a scenario
does not pass by skipping, and the image-level properties are scenario S4, which builds the image).
"""

from __future__ import annotations

import hashlib
import re
import shlex
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
CONTAINERFILE = _ROOT / "deploy" / "Containerfile.runner"
CI = _ROOT / ".github" / "workflows" / "ci.yml"
V6 = _ROOT / "prompts" / "builder" / "v6.md"
V7 = _ROOT / "prompts" / "builder" / "v7.md"

# v6's git blob id as ratified (card 65's ref) — any byte edit to v6 changes it; a new version is a new file.
V6_BLOB = "262d399d461eb6892d92856ce682b519a43724b2"

PY312 = "/opt/isidium/py312"
PY313 = "/opt/isidium/py313"


def _instructions() -> list[str]:
    """The Containerfile's instructions, backslash continuations joined and comment lines dropped — so a comment that
    merely names a flag cannot satisfy an assertion about an instruction."""
    text = CONTAINERFILE.read_text(encoding="utf-8").replace("\\\n", " ")
    return [" ".join(ln.split()) for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]


def _flags(line: str) -> set[str]:
    return {t for t in shlex.split(line) if t.startswith("--")}


def _blob(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def test_the_containerfile_installs_the_locked_dev_group_for_both_pythons() -> None:
    lines = _instructions()

    # R1: the resolution CI installs, plus the dev group, without the workspace packages.
    ci_lines = CI.read_text(encoding="utf-8").splitlines()
    (ci_sync,) = [ln for ln in ci_lines if ln.strip().startswith("run: uv sync --locked")]
    exports = [ln for ln in lines if "uv export" in ln and "--group dev" in ln]
    assert len(exports) == 1, exports
    export = exports[0]
    assert {"--locked", "--all-packages", "--all-extras", "--group", "--no-emit-workspace"} <= set(shlex.split(export))
    assert _flags(ci_sync) <= _flags(export), "every flag of CI's `uv sync` is in the export"

    # The test environments are their own stage, copied into the final one, with an exactly pinned 3.13 (C1, C2).
    assert any(re.fullmatch(r"FROM build AS test-env", ln) for ln in lines)
    assert any(ln.startswith("COPY --from=test-env ") for ln in lines)
    assert sum(1 for ln in lines if re.search(r"\buv python install 3\.13\.\d+\b", ln)) == 1
    assert any(ln.startswith("ENV ") and "UV_NO_CACHE=1" in ln for ln in lines), "no wheel cache is shipped"

    # Each environment is installed from the exported requirements with their hashes required.
    for venv in (PY312, PY313):
        installs = [ln for ln in lines if "uv pip install" in ln and f"--python {venv}/bin/" in ln]
        assert len(installs) == 1, (venv, installs)
        assert "--require-hashes" in installs[0] and "-r /tests/requirements.txt" in installs[0], installs[0]
        assert any(ln.startswith("COPY --from=test-env ") and f" {venv} " in f"{ln} " for ln in lines), venv

    # R2: the 3.12 environment's bin is first on PATH, and the image names the 3.13 environment.
    (env_line,) = [ln for ln in lines if ln.startswith("ENV PATH=")]
    env = {k: v for k, _, v in (t.partition("=") for t in shlex.split(env_line)[1:])}
    assert env["PATH"].split(":")[0] == f"{PY312}/bin", env["PATH"]
    assert env["ISIDIUM_PY313"] == PY313

    # A1: the runtime install is unchanged — no dev group in it, and the system interpreter stays the runtime's.
    (runtime_export,) = [ln for ln in lines if "uv export" in ln and "--no-dev" in ln]
    assert "--group" not in runtime_export and "--package isidium-factory" in runtime_export
    runtime_install = "pip install --no-cache-dir --require-hashes -r /wheels/requirements.txt"
    (runtime_pip,) = [ln for ln in lines if runtime_install in ln]
    assert "--group" not in runtime_pip and "/tests/" not in runtime_pip
    (removal,) = [ln for ln in lines if f"rm {PY312}/bin/python {PY312}/bin/python3" in ln]
    # `uv venv` links `python3.12` to `python`; removing `python` first would leave the kept name (and every console
    # script's shebang) dangling, so the kept name is re-pointed at the base interpreter before the removal.
    repoint = f"ln -sfn /usr/local/bin/python3.12 {PY312}/bin/python3.12"
    assert repoint in removal and removal.index(repoint) < removal.index(f"rm {PY312}/bin/python "), removal

    # The build-time check: a PATH that hid the guard's interpreter, or a missing tool, fails the build.
    (check,) = [ln for ln in lines if ln.startswith("RUN ") and "command -v python3" in ln]
    for need in (
        "= /usr/local/bin/python3",
        "import isidium.factory.guard",
        "pytest --version",
        "ruff --version",
        "mypy --version",
        '"$ISIDIUM_PY313/bin/python" -m pytest --version',
    ):
        assert need in check, (need, check)


def test_builder_v7_names_both_pythons_and_never_installs() -> None:
    v6_bytes, v7_bytes = V6.read_bytes(), V7.read_bytes()
    assert _blob(v6_bytes) == V6_BLOB, "v6 is unedited"
    assert b"\r" not in v7_bytes and v7_bytes != v6_bytes
    v7 = v7_bytes.decode("utf-8")
    assert "version=7" in v7.splitlines()[0]
    assert "# The builder — v7" in v7 and "What changed in v7" in v7
    assert "**What changed in v6, and why.**" in v7, "v6's changelog is kept"
    assert "## 7. If the gate is red — fixup" in v7, "v6's phases are kept"

    flat = " ".join(v7.replace("**", "").split())
    for phrase in (
        "ISIDIUM_PY313",
        "3.12",
        "3.13",
        "ruff check",
        "ruff format --check",
        "mypy --strict",
        "by path",
        "never the whole tree",
        "Never `pip install`",
        "you install nothing",
        "a line in your report, not an install",
        "A check you could not run is a line in the report",
        "uv.lock",
        "the lock as of the image's build",
    ):
        assert phrase in flat, phrase
    assert "python -m pytest` reaches the runtime interpreter, which has no pytest" in flat
