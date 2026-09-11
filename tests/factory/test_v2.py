"""V2 (2026-09-10) — the tenant context (`isidium.factory.context`), the forge seam (`isidium.factory.forge`) and the
GitHub driver (`isidium.factory.github`), and the four verbs.

The context and the driver's git half run over a real checkout with a bare `origin` on disk (K3's shape), whose
`origin` url is a GitHub url rewritten to the bare path by `url.<path>.insteadOf` — so the coords parse as the forge's
and the fetch and push land on disk. The API half runs over `httpx.MockTransport`, every request recorded. Every
refusal asserted is the typed one; the positive discriminators are the remote's refs and the recorded requests.
"""

from __future__ import annotations

import functools
import json
import subprocess
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from isidium.factory import checkout as checkout_mod
from isidium.factory import cli as cli_mod
from isidium.factory import context as context_mod
from isidium.factory import forge as forge_mod
from isidium.factory import github as github_mod
from isidium.factory.context import ForgeCoords, ForgeIdentity, ForgeKind, TenantContext, ToolkitPins, toolkit_check
from isidium.factory.forge import Capabilities, CheckRun, Checks, Forge, MergeableState, Verdict, pr_text
from isidium.factory.github import GITHUB, GitHub
from isidium.factory.payload import Caps, Identity
from isidium.store.client.config import ClientConfig
from isidium.store.client.verify import verify
from isidium.store.core.grammar import Document
from isidium.store.core.refusal import Refusal
from isidium.store.registry.loader import Registry
from isidium.store.server.store import NewCard, Store

from ..store.conftest import BASE_SCOPE, OWNER, PLANNER, base_head, git, path_of, store_on_disk, tenant_checkout

ROOT = "docs/work/"
TENANT = "sartor"
URL = "https://github.com/acme/widgets.git"
TOKEN = "ghp_test_secret_token_0123456789"
LOGIN = "widgets-factory"


def refuses(rule: str, fn: Callable[[], Any]) -> Refusal:
    with pytest.raises(Refusal) as e:
        fn()
    assert e.value.rule == rule, str(e.value)
    return e.value


@dataclass
class Disk:
    work: Path
    home: Path
    store: Store
    card: int
    card_path: str
    bare: str


@pytest.fixture(scope="module")
def disk(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Disk]:
    """A tenant checkout with a bare remote that answers to a GitHub url; a store over it; one ratified card pulled
    back; the deploy home with the lander's client file and the forge identity."""
    tmp = tmp_path_factory.mktemp("v2")
    work = tenant_checkout(tmp)
    st = store_on_disk(work, tmp / "journal.sqlite", root=ROOT)
    st.init(OWNER, software_key_ack="ok for V2", root=ROOT)
    r = st.write(NewCard("forge-subject"), Document(base_head(0, "draft"), {"Scope": BASE_SCOPE}), None, None, PLANNER)
    assert r.id is not None
    st.ratify([r.id], OWNER)
    git(work, "pull", "-q", "origin", "main")
    bare = (tmp / "origin.git").as_posix()
    git(work, "remote", "set-url", "origin", URL)
    git(work, "config", f"url.{bare}.insteadOf", URL)
    home = tmp / "deploy"
    d = home / TENANT / "factory"
    d.mkdir(parents=True)
    (d / "client.toml").write_text(ClientConfig(tenant=TENANT).render(), encoding="utf-8")
    (d / "forge.toml").write_text(
        f'kind = "token"\nlogin = "{LOGIN}"\nname = "isidium-factory"\n'
        f'email = "1234+{LOGIN}@users.noreply.github.com"\ntoken = "forge.token"\n',
        encoding="utf-8",
    )
    (d / "forge.token").write_text(TOKEN + "\n", encoding="utf-8")
    mp = pytest.MonkeyPatch()
    mp.setenv("ISIDIUM_DEPLOY", str(home))
    yield Disk(work, home, st, r.id, ROOT + path_of(st, r.id), bare)
    mp.undo()


def load(d: Disk, **over: Any) -> TenantContext:
    kw: dict[str, Any] = {"base": "main", "root": ROOT}
    kw.update(over)
    return context_mod.load(TENANT, d.work, **kw)


def commit_on(work: Path, branch: str, files: dict[str, str | None], *, mv: tuple[str, str] | None = None) -> str:
    """A commit on a new local branch off `main`: `files` written (`None` = deleted), `mv` a rename; `main` checked
    out again after. The sha comes back."""
    git(work, "checkout", "-q", "-b", branch, "main")
    try:
        if mv:
            git(work, "mv", mv[0], mv[1])
        for rel, text in files.items():
            p = work / rel
            if text is None:
                p.unlink()
            else:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(text, encoding="utf-8")
        git(work, "add", "-A")
        git(work, "commit", "-q", "--no-verify", "-m", f"on {branch}")
        return git(work, "rev-parse", "HEAD").strip()
    finally:
        git(work, "checkout", "-q", "main")


def remote_ref(work: Path, name: str) -> str | None:
    out = git(work, "ls-remote", "origin", f"refs/heads/{name}")
    return out.split()[0] if out.strip() else None


# ---- the context ---------------------------------------------------------------------------------------------------


def test_the_context_loads_the_same_value_and_hash_twice_and_the_token_is_outside_both(disk: Disk) -> None:
    a, b = load(disk), load(disk)
    assert a.hash == b.hash and a.value() == b.value() and a.hash.startswith("sha256:")
    assert a.base_sha == git(disk.work, "ls-remote", "origin", "refs/heads/main").split()[0]
    assert a.forge == ForgeCoords("github.com", "acme", "widgets", "origin")
    assert a.identity.login == LOGIN and a.identity.secret == TOKEN and a.identity.kind is ForgeKind.TOKEN
    assert TOKEN not in json.dumps(a.value()) and TOKEN not in repr(a)
    assert a.toolkit.client == "0.1.0" and a.root == ROOT
    assert any(str(r["path"]) == "cards/*.md" for r in a.governed)


def test_forge_coords_parse_the_three_url_forms_and_refuse_the_rest() -> None:
    want = ForgeCoords("github.com", "acme", "widgets", "origin")
    for url in (
        URL,
        "https://github.com/acme/widgets",
        "git@github.com:acme/widgets.git",
        "ssh://git@github.com/acme/widgets.git",
    ):
        assert ForgeCoords.parse(url, "origin") == want, url
    assert ForgeCoords.parse("ssh://git@gitea.lan:2222/acme/widgets.git", "up") == ForgeCoords(
        "gitea.lan", "acme", "widgets", "up"
    )
    for bad in ("C:/Dev/widgets", "/srv/git/widgets.git", "https://github.com/widgets"):
        refuses("factory.forge-url", functools.partial(ForgeCoords.parse, bad, "origin"))


def test_the_context_refuses_an_unreachable_remote_a_missing_base_and_a_missing_identity(
    disk: Disk, tmp_path: Path
) -> None:
    refuses("factory.no-base", lambda: load(disk, base="no-such-branch"))
    gone = (tmp_path / "gone.git").as_posix()
    git(disk.work, "config", "--unset", f"url.{disk.bare}.insteadOf")
    git(disk.work, "config", f"url.{gone}.insteadOf", URL)
    try:
        r = refuses("factory.unreachable", lambda: load(disk))
        assert r.path == "origin/main"
    finally:
        git(disk.work, "config", "--unset", f"url.{gone}.insteadOf")
        git(disk.work, "config", f"url.{disk.bare}.insteadOf", URL)
    refuses("factory.no-forge", lambda: ForgeIdentity.load(tmp_path))
    (tmp_path / "forge.toml").write_text('login = "x"\nname = "x"\n', encoding="utf-8")
    assert "kind" in refuses("factory.no-forge", lambda: ForgeIdentity.load(tmp_path)).detail  # no default kind (C-1)
    (tmp_path / "forge.toml").write_text('kind = "token"\nlogin = "x"\nname = "x"\n', encoding="utf-8")
    assert "email, token" in refuses("factory.no-forge", lambda: ForgeIdentity.load(tmp_path)).detail
    (tmp_path / "forge.toml").write_text(
        'kind = "app"\nlogin = "x"\nname = "x"\nemail = "x@y"\nkey = "k"\n', encoding="utf-8"
    )
    assert "app_id, installation_id" in refuses("factory.no-forge", lambda: ForgeIdentity.load(tmp_path)).detail
    (tmp_path / "forge.toml").write_text(
        'kind = "token"\nlogin = "x"\nname = "x"\nemail = "x@y"\ntoken = "t"\n', encoding="utf-8"
    )
    refuses("factory.no-forge", lambda: ForgeIdentity.load(tmp_path))  # no token file
    (tmp_path / "t").write_text("\n", encoding="utf-8")
    assert "empty" in refuses("factory.no-forge", lambda: ForgeIdentity.load(tmp_path)).detail
    (tmp_path / "t").write_text("tok\n", encoding="utf-8")
    assert ForgeIdentity.load(tmp_path).secret == "tok"


def test_a_toolkit_pin_outside_the_range_is_refused_naming_the_upgrade(disk: Disk) -> None:
    floor, ceiling = context_mod.TOOLKIT_RANGE
    # at the door: a base whose config pins a client this factory does not read is refused by `load` itself
    cfg = disk.work / ROOT / "config.toml"
    text = cfg.read_text(encoding="utf-8")
    assert f'client = "{floor}"' in text
    commit_on(
        disk.work, "toolkit/ahead", {ROOT + "config.toml": text.replace(f'client = "{floor}"', f'client = "{ceiling}"')}
    )
    git(
        disk.work, "push", "-q", "origin", "toolkit/ahead"
    )  # the test's bare has no gate; the factory's push would refuse
    r = refuses("factory.toolkit", lambda: load(disk, base="toolkit/ahead"))
    assert ceiling in r.detail
    toolkit_check(ToolkitPins(floor, "0.1.0", "15.0.0", "sha1"))
    r = refuses("factory.toolkit", lambda: toolkit_check(ToolkitPins(ceiling, "0.1.0", "15.0.0", "sha1")))
    assert ceiling in r.detail and f"[{floor}, {ceiling})" in r.detail and "T-C2" in r.detail
    refuses("factory.toolkit", lambda: toolkit_check(ToolkitPins("0.0.9", "0.1.0", "15.0.0", "sha1")))
    assert "not a version" in refuses("factory.toolkit", lambda: toolkit_check(ToolkitPins("v1", "", "", ""))).detail


def test_git_is_spawned_three_times_per_load_and_the_registry_built_once(
    disk: Disk, monkeypatch: pytest.MonkeyPatch
) -> None:
    spawned: list[list[str]] = []
    built: list[Path] = []

    class Counting(subprocess.Popen[bytes]):
        def __init__(self, cmd: Any, *a: Any, **kw: Any) -> None:
            spawned.append(list(cmd))
            super().__init__(cmd, *a, **kw)

    real = Registry.for_checkout

    def counted(repo: str | Path) -> Registry:
        built.append(Path(repo))
        return real(repo)

    monkeypatch.setattr(subprocess, "Popen", Counting)
    monkeypatch.setattr(Registry, "for_checkout", counted)
    ctx = load(disk)
    assert [c[:2] for c in spawned] == [["git", "config"], ["git", "fetch"], ["git", "cat-file"]]
    assert built == [disk.work]
    # V1's finding 15 closed: a gather handed the context's registry builds none of its own.
    built.clear()
    spawned.clear()
    checkout_mod.gather(
        disk.work,
        ctx.base_sha,
        disk.card,
        tenant=TENANT,
        root=ROOT,
        context_of=lambda c: {"context": {"depth": 2, "bytes": 0, "cards": [], "truncated": False}, "text": ""},
        identity=Identity("bot@x", "none"),
        caps=Caps(1 << 20),
        registry=ctx.registry,
    )
    assert built == [] and len(spawned) == 2


# ---- the git half ---------------------------------------------------------------------------------------------------


def test_fetch_branch_check_push_are_five_spawns_the_remote_holds_the_branch_and_the_token_is_in_no_argv(
    disk: Disk, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = load(disk)
    sha = commit_on(disk.work, "tmp/code", {"src/widget.py": "def widget():\n    return 1\n"})
    spawned: list[tuple[list[str], dict[str, str] | None]] = []

    class Recording(subprocess.Popen[bytes]):
        def __init__(self, cmd: Any, *a: Any, **kw: Any) -> None:
            spawned.append((list(cmd), kw.get("env")))
            super().__init__(cmd, *a, **kw)

    monkeypatch.setattr(subprocess, "Popen", Recording)
    drv = GitHub(ctx, transport=httpx.MockTransport(lambda req: httpx.Response(500)))
    seam: Forge = drv  # the driver satisfies the Protocol (mypy holds this line)
    assert seam.fetch("main") == ctx.base_sha
    drv.branch("story/code", sha)
    ch = drv.push("story/code")
    assert ch.paths == ("src/widget.py",) and ch.governed == ()
    assert [c[:2] for c, _ in spawned] == [
        ["git", "fetch"],
        ["git", "rev-parse"],
        ["git", "branch"],
        ["git", "diff"],
        ["git", "push"],
    ]
    push_env = spawned[4][1]  # before `remote_ref` below spawns a sixth
    assert remote_ref(disk.work, "story/code") == sha
    for cmd, _ in spawned:
        assert all(TOKEN not in part for part in cmd), cmd
    assert push_env is not None and push_env["GIT_CONFIG_KEY_0"] == "http.https://github.com/.extraheader"
    assert TOKEN not in push_env["GIT_CONFIG_VALUE_0"] and push_env["GIT_CONFIG_VALUE_0"].startswith(
        "Authorization: Basic "
    )
    refuses("forge.branch-exists", lambda: drv.branch("story/code", sha))


def test_a_governed_path_in_the_diff_is_refused_before_any_push_and_verify_names_the_same_path(
    disk: Disk, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = load(disk)
    drv = GitHub(ctx, transport=httpx.MockTransport(lambda req: httpx.Response(500)))
    card = disk.card_path
    commit_on(disk.work, "story/governed", {"src/ok.py": "x = 1\n", card: "# tampered\n"})
    spawned: list[list[str]] = []

    class Counting(subprocess.Popen[bytes]):
        def __init__(self, cmd: Any, *a: Any, **kw: Any) -> None:
            spawned.append(list(cmd))
            super().__init__(cmd, *a, **kw)

    monkeypatch.setattr(subprocess, "Popen", Counting)
    r = refuses("forge.governed-path", lambda: drv.push("story/governed"))
    assert r.path == card and card in r.detail and "src/ok.py" not in r.detail
    assert [c[:2] for c in spawned] == [["git", "diff"]]  # the check, and nothing after it
    assert remote_ref(disk.work, "story/governed") is None
    # a rename out of the root names its source (--no-renames, K7a)
    commit_on(disk.work, "story/moved", {}, mv=(card, "moved.md"))
    r = refuses("forge.governed-path", lambda: drv.push("story/moved"))
    assert r.path == card and remote_ref(disk.work, "story/moved") is None
    # a path outside the root that happens to match a row is code (M2's discriminator)
    commit_on(disk.work, "story/outside", {"cards/0001-not-governed.md": "# outside the root\n"})
    assert drv.push("story/outside").governed == ()
    # CI's own verdict over the same diff, on the same checkout, names the same path
    git(disk.work, "checkout", "-q", "story/governed")
    try:
        rep = verify(disk.work, diff_base=ctx.base_sha)
        assert rep.governed_changed == [card] and not rep.passed
    finally:
        git(disk.work, "checkout", "-q", "main")


# ---- the API half ---------------------------------------------------------------------------------------------------


@dataclass
class Fake:
    """A scripted forge: `(method, path)` → the responses in order (the last one repeats); every request kept."""

    routes: dict[tuple[str, str], list[Callable[[httpx.Request], httpx.Response]]]
    seen: list[httpx.Request] = field(default_factory=list)

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.seen.append(req)
        key = (req.method, req.url.path)
        answers = self.routes.get(key)
        if not answers:
            return httpx.Response(404, json={"message": f"no route {key}"})
        fn = answers.pop(0) if len(answers) > 1 else answers[0]
        return fn(req)

    def driver(self, ctx: TenantContext, sleeps: list[float] | None = None) -> GitHub:
        return GitHub(
            ctx, transport=httpx.MockTransport(self), sleep=(sleeps.append if sleeps is not None else lambda s: None)
        )


def ok(status: int, body: Any, **headers: str) -> Callable[[httpx.Request], httpx.Response]:
    return lambda req: httpx.Response(status, json=body, headers=headers)


def down(req: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("refused", request=req)


REPO = "/repos/acme/widgets"
PR = {"number": 12, "html_url": "https://github.com/acme/widgets/pull/12", "head": {"sha": "abc123"}}


def test_the_pull_request_is_opened_with_the_generated_body_as_the_identity(disk: Disk) -> None:
    ctx = load(disk)
    fake = Fake({("POST", f"{REPO}/pulls"): [ok(201, PR)]})
    drv = fake.driver(ctx)
    ch = forge_mod.Changed(("src/a.py", "src/b.py"), ())
    spec = pr_text(ctx, "story/x", ch)
    pr = drv.open_pr(spec)
    assert (pr.number, pr.url, pr.head) == (12, PR["html_url"], "abc123")
    [req] = fake.seen
    assert (
        req.headers["authorization"] == f"Bearer {TOKEN}"
        and req.headers["x-github-api-version"] == github_mod.API_VERSION
    )
    sent = json.loads(req.content)
    assert sent == {"title": "story/x", "body": spec.body, "head": "story/x", "base": "main"}
    assert spec.body == (
        f"Tenant `{TENANT}`; base `main` at `{ctx.base_sha}`; head `story/x`.\n\n"
        "Files changed:\n- `src/a.py`\n- `src/b.py`\n\n"
        f"Opened by isidium-factory as `{LOGIN}`; code only — no governed path is in this diff.\n\n"
        "Isidium-Branch: story/x\n"
    )


RULES = [
    {"type": "pull_request"},
    {
        "type": "required_status_checks",
        "parameters": {"required_status_checks": [{"context": c} for c in ("sweep", "verify", "green-bar")]},
    },
]


def runs(*rows: tuple[str, str, str | None]) -> dict[str, Any]:
    return {"total_count": len(rows), "check_runs": [{"name": n, "status": s, "conclusion": c} for n, s, c in rows]}


def test_checks_read_the_gate_s_required_contexts_and_the_verdict_is_over_them(disk: Disk) -> None:
    ctx = load(disk)
    green = runs(
        ("sweep", "completed", "success"), ("verify", "completed", "success"), ("green-bar", "completed", "skipped")
    )
    pending = runs(("sweep", "completed", "success"), ("green-bar", "in_progress", None))  # verify never ran
    red = runs(("sweep", "completed", "success"), ("verify", "completed", "failure"), ("green-bar", "queued", None))
    extra = runs(
        *[(r["name"], r["status"], r["conclusion"]) for r in green["check_runs"]],
        ("advisories", "completed", "failure"),
    )
    fake = Fake(
        {
            ("GET", f"{REPO}/rules/branches/main"): [ok(200, RULES)],
            ("GET", f"{REPO}/commits/h1/check-runs"): [ok(200, green)],
            ("GET", f"{REPO}/commits/h2/check-runs"): [ok(200, pending)],
            ("GET", f"{REPO}/commits/h3/check-runs"): [ok(200, red)],
            ("GET", f"{REPO}/commits/h4/check-runs"): [ok(200, extra)],
        }
    )
    drv = fake.driver(ctx)
    c1 = drv.checks("h1")
    assert c1.required == ("sweep", "verify", "green-bar") and c1.verdict is Verdict.GREEN
    assert drv.checks("h2").verdict is Verdict.PENDING
    assert drv.checks("h3").verdict is Verdict.RED
    assert drv.checks("h4").verdict is Verdict.GREEN  # a failing run the gate does not require is not the gate's
    assert fake.seen[1].url.params["per_page"] == str(github_mod.PAGE)
    # newest first: the first run seen per name is the one that counts
    assert (
        Checks(("a",), (CheckRun("a", "completed", "success"), CheckRun("a", "completed", "failure"))).verdict
        is Verdict.GREEN
    )
    assert Checks(("a",), ()).verdict is Verdict.PENDING


def test_merge_state_reads_the_enum_and_refuses_a_state_it_does_not_know(disk: Disk) -> None:
    ctx = load(disk)
    fake = Fake(
        {
            ("GET", f"{REPO}/pulls/1"): [
                ok(
                    200,
                    {
                        "head": {"sha": "h1"},
                        "mergeable": True,
                        "mergeable_state": "clean",
                        "merged": False,
                        "merge_commit_sha": None,
                    },
                )
            ],
            ("GET", f"{REPO}/pulls/2"): [
                ok(
                    200,
                    {
                        "head": {"sha": "h2"},
                        "mergeable": True,
                        "mergeable_state": "blocked",
                        "merged": False,
                        "merge_commit_sha": "m2",
                    },
                )
            ],
            ("GET", f"{REPO}/pulls/3"): [
                ok(
                    200,
                    {
                        "head": {"sha": "h3"},
                        "mergeable": None,
                        "mergeable_state": "unknown",
                        "merged": True,
                        "merge_commit_sha": "m3",
                    },
                )
            ],
            ("GET", f"{REPO}/pulls/4"): [
                ok(
                    200,
                    {
                        "head": {"sha": "h4"},
                        "mergeable": True,
                        "mergeable_state": "novel",
                        "merged": False,
                        "merge_commit_sha": None,
                    },
                )
            ],
        }
    )
    drv = fake.driver(ctx)
    s1 = drv.merge_state(1)
    assert (s1.head, s1.mergeable, s1.state, s1.merged, s1.merge_commit) == (
        "h1",
        True,
        MergeableState.CLEAN,
        False,
        None,
    )
    assert drv.merge_state(2).state is MergeableState.BLOCKED
    s3 = drv.merge_state(3)
    assert s3.merged and s3.merge_commit == "m3" and s3.state is MergeableState.UNKNOWN
    assert "novel" in refuses("forge.api", lambda: drv.merge_state(4)).detail


def test_a_transient_failure_retries_with_backoff_and_a_persistent_one_is_unavailable(disk: Disk) -> None:
    ctx = load(disk)
    sleeps: list[float] = []
    fake = Fake({("POST", f"{REPO}/pulls"): [ok(503, {"message": "down"}), down, ok(201, PR)]})
    pr = fake.driver(ctx, sleeps).open_pr(pr_text(ctx, "story/x", forge_mod.Changed((), ())))
    assert pr.number == 12 and sleeps == [1.0, 2.0] and len(fake.seen) == 3
    sleeps.clear()
    fake = Fake({("POST", f"{REPO}/pulls"): [ok(502, {"message": "bad gateway"})]})
    r = refuses(
        "forge.unavailable",
        lambda: fake.driver(ctx, sleeps).open_pr(pr_text(ctx, "story/x", forge_mod.Changed((), ()))),
    )
    assert sleeps == list(github_mod.BACKOFF) and len(fake.seen) == len(github_mod.BACKOFF) + 1 and "502" in r.detail
    sleeps.clear()
    fake = Fake({("GET", f"{REPO}/pulls/1"): [down]})
    r = refuses("forge.unavailable", lambda: fake.driver(ctx, sleeps).merge_state(1))
    assert "ConnectError" in r.detail and sleeps == list(github_mod.BACKOFF)


def test_the_rate_limit_and_an_existing_pull_request_are_named(disk: Disk) -> None:
    ctx = load(disk)
    fake = Fake(
        {
            ("GET", f"{REPO}/pulls/1"): [
                ok(403, {"message": "rate"}, **{"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1787000000"})
            ]
        }
    )
    r = refuses("forge.rate-limited", lambda: fake.driver(ctx).merge_state(1))
    assert "1787000000" in r.detail and len(fake.seen) == 1  # exhausted is not transient: no retry
    exists = {
        "message": "Validation Failed",
        "errors": [{"message": "A pull request already exists for acme:story/x."}],
    }
    fake = Fake({("POST", f"{REPO}/pulls"): [ok(422, exists)], ("GET", f"{REPO}/pulls"): [ok(200, [{"number": 7}])]})
    r = refuses("forge.pr-exists", lambda: fake.driver(ctx).open_pr(pr_text(ctx, "story/x", forge_mod.Changed((), ()))))
    assert r.detail == "#7" and r.path == "story/x"
    assert [q.method for q in fake.seen] == ["POST", "GET"] and fake.seen[1].url.params["head"] == "acme:story/x"
    fake = Fake(
        {
            ("POST", f"{REPO}/pulls"): [
                ok(
                    422,
                    {"message": "Validation Failed", "errors": [{"message": "No commits between main and story/x"}]},
                )
            ]
        }
    )
    r = refuses("forge.api", lambda: fake.driver(ctx).open_pr(pr_text(ctx, "story/x", forge_mod.Changed((), ()))))
    assert "422" in r.detail and "No commits" in r.detail
    fake = Fake({("GET", f"{REPO}/pulls/1"): [ok(403, {"message": "forbidden"}, **{"x-ratelimit-remaining": "40"})]})
    assert "403" in refuses("forge.api", lambda: fake.driver(ctx).merge_state(1)).detail


def test_the_capability_matrix_is_declared_and_the_seam_has_no_merge(disk: Disk) -> None:
    ctx = load(disk)
    drv = Fake({}).driver(ctx)
    assert drv.capabilities() is GITHUB
    assert (
        Capabilities(
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
            hosts=("github.com", "api.github.com"),
        )
        == GITHUB
    )
    for absent in ("merge", "force_push", "delete_branch", "delete"):
        assert not hasattr(Forge, absent) and not hasattr(GitHub, absent), absent
    bad = TenantContext(**{**ctx.__dict__, "forge": ForgeCoords("gitea.lan", "a", "b", "origin")})
    refuses("forge.host", lambda: GitHub(bad))


# ---- the verbs and the spans ---------------------------------------------------------------------------------------


def test_the_four_verbs_through_the_runner(disk: Disk, monkeypatch: pytest.MonkeyPatch) -> None:
    from typer.testing import CliRunner

    fake = Fake(
        {
            ("POST", f"{REPO}/pulls"): [ok(201, PR)],
            ("GET", f"{REPO}/pulls/12"): [
                ok(
                    200,
                    {
                        "head": {"sha": "abc123"},
                        "mergeable": True,
                        "mergeable_state": "clean",
                        "merged": False,
                        "merge_commit_sha": None,
                    },
                )
            ],
            ("GET", f"{REPO}/rules/branches/main"): [ok(200, RULES)],
            ("GET", f"{REPO}/commits/abc123/check-runs"): [
                ok(
                    200,
                    runs(
                        ("sweep", "completed", "success"),
                        ("verify", "completed", "success"),
                        ("green-bar", "completed", "success"),
                    ),
                )
            ],
        }
    )

    class Mocked(GitHub):
        def __init__(self, ctx: TenantContext, **kw: Any) -> None:
            super().__init__(ctx, transport=httpx.MockTransport(fake), sleep=lambda s: None)

    monkeypatch.setattr(github_mod, "GitHub", Mocked)
    common = ["--tenant", TENANT, "--checkout", str(disk.work), "--root", ROOT]
    run = CliRunner()
    a = run.invoke(cli_mod.app, ["context", *common])
    b = run.invoke(cli_mod.app, ["context", *common])
    assert a.exit_code == 0, a.output
    assert json.loads(a.output)["hash"] == json.loads(b.output)["hash"] and TOKEN not in a.output
    sha = commit_on(disk.work, "tmp/verb", {"src/verb.py": "v = 1\n"})
    p = run.invoke(cli_mod.app, ["push", *common, "--branch", "story/verb", "--at", sha])
    assert p.exit_code == 0, p.output
    assert json.loads(p.output)["files"] == ["src/verb.py"] and remote_ref(disk.work, "story/verb") == sha
    commit_on(disk.work, "story/verb-governed", {disk.card_path: "# no\n"})
    p = run.invoke(cli_mod.app, ["push", *common, "--branch", "story/verb-governed"])
    assert p.exit_code == 2 and "forge.governed-path" in p.output and disk.card_path in p.output
    o = run.invoke(cli_mod.app, ["pr-open", *common, "--branch", "story/verb"])
    assert o.exit_code == 0, o.output
    assert json.loads(o.output) == {"number": 12, "url": PR["html_url"], "head": "abc123"}
    assert "- `src/verb.py`" in json.loads(fake.seen[0].content)["body"]
    s = run.invoke(cli_mod.app, ["pr-status", *common, "--pr", "12"])
    assert s.exit_code == 0, s.output
    got = json.loads(s.output)
    assert (got["verdict"], got["state"], got["merged"], got["head"]) == ("green", "clean", False, "abc123")
    assert got["required"] == ["sweep", "verify", "green-bar"]


def test_the_spans_carry_the_base_the_branch_the_governed_count_and_the_status(disk: Disk, otel: Any) -> None:
    otel.clear()
    ctx = load(disk)
    [sp] = otel.spans(context_mod.SPAN)
    assert sp.attributes["isidium.base_sha"] == ctx.base_sha and sp.attributes["isidium.toolkit.client"] == "0.1.0"
    assert sp.attributes[context_mod.GIT_SPAWNS] == 3
    fake = Fake(
        {("GET", f"{REPO}/pulls/1"): [ok(200, {"head": {"sha": "h"}, "mergeable_state": "clean", "merged": False})]}
    )
    drv = fake.driver(ctx)
    drv.merge_state(1)
    [api] = otel.spans(github_mod.SPAN_API)
    assert api.attributes["http.response.status_code"] == 200 and api.attributes["isidium.forge.tries"] == 1
    commit_on(disk.work, "story/span-governed", {disk.card_path: "# no\n"})
    refuses("forge.governed-path", lambda: drv.push("story/span-governed"))
    [push] = otel.spans(github_mod.SPAN_PUSH)
    assert push.attributes["isidium.branch"] == "story/span-governed" and push.attributes["isidium.governed"] == 1
    assert push.attributes["isidium.rule"] == "forge.governed-path"


# ---- the App kind: a minted installation token, renewed before it expires --------------------------------------------


def rsa_pem() -> tuple[str, Any]:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode("ascii")
    return pem, key.public_key()


def pad(s: str) -> str:
    return s + "=" * (-len(s) % 4)


def app_identity(pem: str) -> ForgeIdentity:
    return ForgeIdentity(
        ForgeKind.APP,
        "isdm-fac-lander[bot]",
        "isdm-fac-lander",
        "9+isdm-fac-lander[bot]@users.noreply.github.com",
        pem,
        app_id=4242,
        installation_id=777,
    )


def test_an_app_mints_an_installation_token_from_a_signed_jwt_and_renews_it_before_expiry(
    disk: Disk, monkeypatch: pytest.MonkeyPatch
) -> None:
    import base64

    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    pem, public = rsa_pem()
    ctx = TenantContext(**{**load(disk).__dict__, "identity": app_identity(pem)})
    clock = [1_800_000_000.0]
    minted: list[dict[str, Any]] = []

    def mint(req: httpx.Request) -> httpx.Response:
        jwt = req.headers["authorization"].removeprefix("Bearer ")
        head, body, sig = jwt.split(".")
        try:
            public.verify(
                base64.urlsafe_b64decode(pad(sig)), f"{head}.{body}".encode(), padding.PKCS1v15(), hashes.SHA256()
            )
        except InvalidSignature:
            return httpx.Response(401, json={"message": "bad signature"})
        claims = json.loads(base64.urlsafe_b64decode(pad(body)))
        assert json.loads(base64.urlsafe_b64decode(pad(head))) == {"alg": "RS256", "typ": "JWT"}
        assert claims["iss"] == 4242 and claims["exp"] - claims["iat"] <= 600 and claims["iat"] <= clock[0]
        minted.append(json.loads(req.content))
        n = len(minted)
        expires = datetime.fromtimestamp(clock[0] + 3600, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        return httpx.Response(201, json={"token": f"ghs_minted_{n}", "expires_at": expires})

    fake = Fake(
        {
            ("POST", "/app/installations/777/access_tokens"): [mint],
            ("GET", f"{REPO}/pulls/1"): [
                ok(200, {"head": {"sha": "h"}, "mergeable_state": "clean", "merged": False, "mergeable": True})
            ],
        }
    )
    drv = GitHub(ctx, transport=httpx.MockTransport(fake), sleep=lambda s: None, now=lambda: clock[0])
    drv.merge_state(1)
    assert minted == [{"repositories": ["widgets"]}]  # narrowed to the tenant's repository
    assert [q.headers["authorization"] for q in fake.seen][1] == "Bearer ghs_minted_1"
    assert pem not in " ".join(q.headers["authorization"] for q in fake.seen)
    drv.merge_state(1)
    assert len(minted) == 1  # inside the hour: the same token
    clock[0] += 3600 - github_mod.RENEW + 1  # renewal window reached
    drv.merge_state(1)
    assert len(minted) == 2 and fake.seen[-1].headers["authorization"] == "Bearer ghs_minted_2"
    # the git half carries the minted token, never the key
    spawned: list[tuple[list[str], dict[str, str] | None]] = []

    class Recording(subprocess.Popen[bytes]):
        def __init__(self, cmd: Any, *a: Any, **kw: Any) -> None:
            spawned.append((list(cmd), kw.get("env")))
            super().__init__(cmd, *a, **kw)

    monkeypatch.setattr(subprocess, "Popen", Recording)
    drv.fetch("main")
    env = spawned[0][1]
    assert env is not None and "ghs_minted_2" in base64.b64decode(env["GIT_CONFIG_VALUE_0"].split()[-1]).decode()
    assert all("PRIVATE KEY" not in part for cmd, _ in spawned for part in cmd)
    # a key that is not RSA, or does not parse, is the identity file's defect
    bad = TenantContext(**{**ctx.__dict__, "identity": app_identity("not a pem")})
    refuses("factory.no-forge", lambda: GitHub(bad, transport=httpx.MockTransport(fake)).merge_state(1))
