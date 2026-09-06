"""`isidium` — one command (7bf.3, ruled (b)): the store's verbs at the top level, because every tenant has the store
and nothing else is guaranteed; every other isidium part is a group that dispatches to `isidium-<part>` on PATH (the
`git-*` / `cargo-*` convention), so the umbrella never knows which language a part is written in.

    isidium init | write | show | check | ratify | suggest | disposition | repair | hook | serve | mcp
    isidium <part> <args…>        → exec isidium-<part> (memory, factory, …)

Output is JSON by default (agents and scripts read it); `--text` renders the board's human form — the board only,
today: a card and the queue answer JSON until their renderers exist (03 §1.5 pins their forms) [K7c, F23]. A refusal
prints its rule id and exits non-zero.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Annotated, Any, NoReturn

import typer

from ..core import telemetry
from ..core.refusal import Refusal
from . import locus
from .config import ClientConfig
from .transport import Transport

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="The governed store: every structured document through one typed write. `isidium <part>` runs another part.",
)


def _out(value: Any, text: bool = False) -> None:
    if text and isinstance(value, str):
        typer.echo(value)
    else:
        typer.echo(json.dumps(value, indent=2, default=str, ensure_ascii=False))


def _transport() -> tuple[Transport, ClientConfig, Path]:
    cfg, workdir = ClientConfig.find()
    return Transport(cfg, workdir), cfg, workdir


def _refuse(r: Refusal) -> NoReturn:
    """The CLI's one refusal site [K7b, F14]: recorded, printed whole, exit 2.

    **Recorded through `telemetry.record_refusal`, not through `payload()`.** K2b settled that this door prints
    `str(r)` — a human at their own terminal reads every word — and that is still right for *disclosure*; the
    *counter* is a separate fact, and four sites that printed and never recorded left `isidium.store.refusal` a lie
    about its CLI callers by exactly their share. `payload()` would move the counter too, but its filter relocates a
    terse refusal's words into a WARNING record — which at a terminal means printing them twice. So this calls the
    recorder the filter calls, once, and prints the words once."""
    telemetry.record_refusal(r.rule)
    typer.echo(str(r), err=True)  # `Refusal.render`, not a second copy of it
    raise typer.Exit(code=2) from None


def _run(name: str, args: Mapping[str, Any], text: bool = False) -> None:
    try:
        cfg, workdir = ClientConfig.find()
        # The ref pre-flight runs BEFORE the channel is opened (K4b): a ref whose locus does not land in the working
        # tree is refused here without a round trip — and without `httpx` and the certificates being loaded for a
        # call that is not going to be made. `locus.preflight` reads the working tree and calls `core.refs`'s one
        # locus function; it is the same door the MCP server runs, so the planner and the author get one answer.
        locus.preflight(name, args, workdir, cfg.root)
        _out(Transport(cfg, workdir).call(name, args), text)
    except Refusal as r:
        _refuse(r)


def config_write_args(path: Path) -> dict[str, Any]:
    """`write --config <file>` as the call's typed arguments [K6]: the file the owner edited, as a tree, with the
    chain stripped and the compare-and-swap base read off it.

    **The file's own last `[history]` entry is the base.** The store alone writes that chain, so the file the owner
    edited is the current file plus their edit, and its last entry is exactly the head the owner saw. An operator
    who edits a stale copy is refused `write.stale` by the store, which is the compare-and-swap doing its job.
    Ordering refusals are not raised here: the store emits the canonical form itself, so the owner's table order is
    theirs to leave alone. A file that is not TOML at all is refused at the terminal (`head.toml`), before a call.

    Both imports are inside the function (C-13, 7bh.1): this is the one command that parses TOML, and every other
    `isidium` invocation would otherwise pay for the registry's validator on start-up."""
    from ..core.grammar import parse_config
    from ..registry.config import CONFIG_ORDERS

    tree, entries, rs = parse_config(path.read_text(encoding="utf-8"), CONFIG_ORDERS)
    fatal = [r for r in rs if r.rule == "head.toml"]
    if fatal:
        raise fatal[0]
    args: dict[str, Any] = {"path": "config.toml", "document": tree}
    if entries:
        args["base"] = {"seq": entries[-1]["seq"], "h": entries[-1]["h"]}
    return args


# ---- the ten verbs ----------------------------------------------------------------------------------------------


@app.command()
def init(
    tenant: Annotated[str, typer.Option(help="the registered tenant name")],
    address: Annotated[str, typer.Option(help="the store container's address")],
    ca: Annotated[str, typer.Option(help="the CA the registration pins")],
    cert: Annotated[str, typer.Option(help="this client's certificate")],
    key: Annotated[str, typer.Option(help="this client's private key")],
    root: Annotated[str | None, typer.Option(help="the tracking root; default: the adopted schema version's")] = None,
    ack: Annotated[str, typer.Option(help="the owner's own words accepting software-grade signatures")] = "",
) -> None:
    """Install the client, the hook and the registry schemas here, then open the tenant's policy chain (04 §3).

    **The four channel options have no defaults and are required** (7bg.2, K3). There is one shape, so there is no
    arrangement in which a checkout has no address: `init` writes the hook and the schemas *and* opens the policy
    chain over the channel, and an `init` that could not reach the store would leave a checkout half-registered —
    a hook refusing commits with no store to make them. Refusing four missing arguments up front is the cheaper
    failure. `--principal`, `--grant` and `--signer` are gone with local mode: who the caller is comes off the
    certificate, and the signing key is the store's, in its own container.
    """
    from .install import init as do_init

    cfg = ClientConfig(
        tenant=tenant,
        root=root or "",  # blank means "unset"; `install.resolve_root` fills it from the adopted version (C-1)
        address=address,
        ca=ca,
        cert=cert,
        key=key,
    )
    repo = Path.cwd()
    try:
        _out(do_init(repo, cfg, {"software_key_ack": ack} if ack else {}))
    except Refusal as r:
        _refuse(r)


@app.command()
def write(
    card: Annotated[int, typer.Argument(help="the card id; omit with --new")] = 0,
    set_: Annotated[
        list[str] | None, typer.Option("--set", help="key=value (a tending gesture); key= clears; updates+=title|body")
    ] = None,
    new: Annotated[str, typer.Option(help="create a card with this slug — the store allocates the id")] = "",
    document: Annotated[Path | None, typer.Option(help="a JSON file: {head, scope?, updates?}")] = None,
    ref: Annotated[str, typer.Option(help="a judging ref c<n>:sha256:<hex>")] = "",
    config: Annotated[
        Path | None, typer.Option(help="the tenant's edited config.toml — one signed config-policy act (owner)")
    ] = None,
) -> None:
    """The one writer (03 §1.2): validate, compare-and-swap, derive the act from the diff, sign if the predicate says
    so, journal, write, commit. `--config <file>` is the policy door: the owner edits `config.toml` in the checkout
    and hands the file over; the store re-emits it in canonical form and signs the act.

    A ref in the document's `head.refs` (or in `--set refs=[…]`) whose line range, anchor or symbol does not land
    in this checkout's working tree is refused **here**, before the call (K4b, `client/locus.py`): the store's tree
    cannot see inside a file, and the author's terminal can."""
    if config is not None:
        _run("write", config_write_args(config))
        return
    if document is not None:
        payload = json.loads(document.read_text(encoding="utf-8"))
        args: dict[str, Any] = {"document": payload}
        if new:
            args["new_slug"] = new
        else:
            args["card"] = card
            if "base" in payload:
                args["base"] = payload["base"]
        _run("write", args | ({"ref": ref} if ref else {}))
        return
    if not set_:
        typer.echo("nothing to write: pass --set key=value or --document file.json", err=True)
        raise typer.Exit(code=2)
    _run("write_set", {"card": card, "set": set_} | ({"ref": ref} if ref else {}))


@app.command()
def show(
    target: Annotated[str, typer.Argument(help="card | board | queue | inbox | schema")] = "board",
    id: Annotated[int, typer.Argument(help="the card id, for `card`")] = 0,
    name: Annotated[str, typer.Option(help="name@version, for `schema`")] = "",
    text: Annotated[
        bool,
        typer.Option(
            "--text",
            help="render the board's human form (board only: card and queue answer JSON until their renderers exist)",
        ),
    ] = False,
) -> None:
    """The one typed read (03 §1.2)."""
    args: dict[str, Any] = {"target": target}
    if target == "card":
        args["id"] = id
    if target == "schema":
        args["name"] = name
    try:
        transport, _cfg, _wd = _transport()
        result = transport.call("show", args)
        if text and target == "board":
            _out(result["markdown"], text=True)
        else:
            _out(result)
    except Refusal as r:
        _refuse(r)


@app.command()
def check(id: Annotated[int, typer.Argument(help="the card id")]) -> None:
    """Chain, recompute, signatures and bindings, the journal reconciliation, the whole-set rules (03 §9.6).

    **Not the ref pre-flight's door** (K4b, decided): `check` is the store's integrity verdict over the channel and
    its exit code means *integrity*; the locus check is advice about a specification and belongs where a ref is
    being written — `write` and `ratify` — not folded into a verb whose `1` an operator reads as tampering."""
    try:
        transport, _cfg, _wd = _transport()
        result = transport.call("check", {"id": id})
        _out(result)
        if result["integrity"] or result.get("profile"):
            raise typer.Exit(code=1)
    except Refusal as r:
        _refuse(r)


@app.command()
def ratify(
    ids: Annotated[list[int] | None, typer.Argument(help="the cards to ratify")] = None,
    writes: Annotated[Path | None, typer.Option(help="a JSON file: [{card|new_slug, document, base?, ref?}]")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run/--sign", help="the dry run is the default (round 48)")] = True,
) -> None:
    """The sitting (03 §1.12): the batch is a list of typed writes under ONE signature. Always dry-run first.

    Every ref the sitting commits to — in each write's document, and in each id's card as this checkout holds it —
    is pre-flighted against the working tree before the call, dry run or signed (K4b, `client/locus.py`):
    ratification is where the store records the blob, so it is the moment the locus has to be right."""
    args: dict[str, Any] = {"ids": list(ids or []), "dry_run": dry_run}
    if writes is not None:
        args["writes"] = json.loads(writes.read_text(encoding="utf-8"))
    _run("ratify", args)


@app.command()
def suggest(
    kind: Annotated[str, typer.Argument(help="card | guidance | debt | docs | test | risk | question")],
    title: Annotated[str, typer.Argument()],
    body: Annotated[str, typer.Argument()],
    ref: Annotated[list[str] | None, typer.Option("--ref", help="a path (optionally :lines) at base_sha")] = None,
    for_card: Annotated[int, typer.Option("--for", help="the card a guidance suggestion is proposed for")] = 0,
) -> None:
    """Hand something noticed back to the tenant (03a) — never a card, never guidance until the owner says so."""
    args: dict[str, Any] = {"kind": kind, "title": title, "body": body, "refs": ref or []}
    if for_card:
        args["proposed_for"] = for_card
    _run("suggest", args)


@app.command()
def disposition(
    suggestion: Annotated[str, typer.Argument(help="s<n>")],
    outcome: Annotated[str, typer.Option(help="accepted | declined | deferred")],
    as_: Annotated[str, typer.Option("--as", help="card | guidance | note")] = "",
    reason: Annotated[str, typer.Option(help="declined: why (≤ 500)")] = "",
    until: Annotated[str, typer.Option(help="deferred: a date or a condition")] = "",
    slug: Annotated[str, typer.Option(help="the slug when accepting as a card")] = "from-suggestion",
) -> None:
    """Disposition one suggestion — with the owner, every time (round 28)."""
    args: dict[str, Any] = {"suggestion": suggestion, "outcome": outcome, "slug": slug}
    for k, v in (("as", as_), ("reason", reason), ("until", until)):
        if v:
            args[k] = v
    _run("disposition", args)


@app.command()
def repair(
    history: Annotated[int, typer.Option(help="repair a card's chain")] = 0,
    restart_from: Annotated[int, typer.Option(help="the seq whose h the chain resumes from")] = 0,
    journal: Annotated[str, typer.Option(help="explain a commit made outside the store")] = "",
) -> None:
    """The owner's signed repair (03 §1.15, §9.6): appends, never rewrites."""
    args: dict[str, Any] = {}
    if history:
        args["history"] = history
    if restart_from:
        args["restart_from"] = restart_from
    if journal:
        args["journal"] = journal
    _run("repair", args)


# ---- the tenant-side commands ------------------------------------------------------------------------------------


@app.command()
def hook() -> None:
    """The pre-commit check (03 §9.6): a governed path changed here? refuse. That is the whole hook.

    **This is the human's door, not the installed one** (7bh.2, built by K3b). The hook `init` writes runs
    `python -m isidium.store.client.hook`, which never loads this module; typing `isidium hook` reaches the same
    `check` through here, one behaviour with two doors, and `tests/store/test_walk.py` holds them to one function.
    The deferred import stays — it is now the only thing keeping `hook.py` out of `--help`'s cost, since the module
    that used to pull the store in from the top of this file is gone (K3).
    """
    from .hook import check as hook_check

    raise typer.Exit(code=hook_check(Path.cwd()))


@app.command()
def serve(
    tenant: Annotated[str, typer.Option(help="the tenant namespace this store serves (one store per tenant)")],
    repo: Annotated[Path, typer.Option(help="the store's own partial bare clone of the tenant repository")],
    journal: Annotated[Path, typer.Option(help="the journal database, in the store's container, outside any repo")],
    root: Annotated[str, typer.Option(help="the tracking root this tenant adopted")],
    registration: Annotated[Path, typer.Option(help="a JSON file: {certificate-subject: [principal, grant]}")],
    certificate: Annotated[Path, typer.Option(help="the store's own certificate")],
    key: Annotated[Path, typer.Option(help="the store's own private key")],
    ca: Annotated[Path, typer.Option(help="the registration's CA — every caller's certificate must chain to it")],
    host: Annotated[str, typer.Option(help="the address to listen on, e.g. 0.0.0.0 or 127.0.0.1")],
    port: Annotated[int, typer.Option()] = 8443,
    signer: Annotated[Path | None, typer.Option(help="a software key file — the waiver path")] = None,
    max_connections: Annotated[int | None, typer.Option(help="the connection ceiling, all peers together")] = None,
    max_per_caller: Annotated[
        int | None, typer.Option(help="concurrent connections one registered caller may hold")
    ] = None,
    max_per_probe: Annotated[
        int | None, typer.Option(help="concurrent connections one CA-issued peer the registration does not name")
    ] = None,
) -> None:
    """Run the store for this tenant (03b §2: one store container per tenant).

    **The store terminates its own mTLS** (ruled 7bg.8). It answers the connection itself, requires a client
    certificate this CA issued, and reads that certificate off the connection it is authorizing — there is no proxy,
    no forwarded header and no trusted hop. h11 parses; the accept-and-dispatch loop is the store's own.

    `--host` has no default: what a store listens on is a deployment's decision, and `0.0.0.0` arrived at silently
    is the wrong kind of quiet. The three admission numbers are `None` here and resolved from `server.http.Limits`,
    which carves itself out of C-1 with a stated reason and is their one home (Q4: supplied values with a named
    home, never constants in the binary) — writing them again here would be the second copy C-1 exists to prevent.
    `--port` keeps its default because the registration pins it.

    Every `server.` import is inside this function on purpose: the client half installs without the `[server]`
    extra, and h11 is only in that extra.
    """
    import asyncio
    import time

    from ..core import telemetry
    from ..registry.loader import Registry
    from ..server.api import Api
    from ..server.gitrepo import GitCli
    from ..server.http import LIMITS, Limits, serve_forever, tls_context
    from ..server.journal import Journal
    from ..server.service import Registration, Service
    from ..server.signer import Signer, SoftwareKey, SoftwareKeyAck
    from ..server.store import Store

    # Before anything is built, so the store's own start-up is inside the trace when a deployment asked for one
    # (C-11). It installs nothing unless `OTEL_TRACES_EXPORTER` / `OTEL_METRICS_EXPORTER` are set, and `console` —
    # what K2's container uses for its first start — needs no collector and no network at all.
    telemetry.configure()

    def clock() -> int:
        return int(time.time())

    # Loaded now and re-read on change (K6): a caller is revoked by editing the file, and the next connection sees
    # it. A file that will not parse at start-up stops the store here, before it listens.
    principals = Registration.from_file(registration, clock)
    ack: Signer | None = SoftwareKeyAck(SoftwareKey.load(signer)) if signer else None
    store = Store(
        tenant,
        GitCli(repo, "isidium-store", f"store@{tenant}", root=root),
        Journal(journal, tenant),
        # **The store's own installed registry, never the checkout's** (K4's second half, built 2026-08-31).
        # `Registry.for_checkout` reads `.isidium/schemas/` from a *working tree*, and `init` writes `.isidium/`
        # into `.gitignore` — so under the bare clone `--repo` now names, it would find nothing and fall back to the
        # shipped documents while looking like it had read the tenant's. That silent fallback is what would undo the
        # WP3 review's C5 (*the checkout's installed registry is what it validates against*): a store on a newer
        # toolkit would validate against the toolkit's schemas and never say so. The tracked source of the adopted
        # versions is the manifest in `config.toml`, which is governed and readable from the bare clone; the store
        # resolves each path's `schema@version` against what it has installed and refuses `config.schema-unknown`
        # when a named version is absent. `Registry.for_checkout` stays the **client's** offline path (`check`, the
        # hook), which is the half that actually has a working tree.
        Registry.shipped(),
        clock,
        ack,
        root=root,
        software_fprs=frozenset({ack.key_fpr}) if ack is not None else frozenset(),
    )
    service = Service(Api(store), principals, tenant)
    limits = Limits(
        max_connections=LIMITS.max_connections if max_connections is None else max_connections,
        max_per_caller=LIMITS.max_per_caller if max_per_caller is None else max_per_caller,
        max_per_probe=LIMITS.max_per_probe if max_per_probe is None else max_per_probe,
    )
    asyncio.run(serve_forever(service, host, port, tls_context(certificate, key, ca), limits))


@app.command()
def mcp() -> None:
    """Serve this tenant's store as MCP tools over stdio — the surface agents are meant to use (03 §1.2)."""
    from .mcp import main as mcp_main

    raise typer.Exit(code=mcp_main())


# ---- `isidium <part>` — PATH dispatch (7bf.3) ----------------------------------------------------------------------


def dispatch_part(argv: Sequence[str]) -> int | None:
    """`isidium memory recall …` → exec `isidium-memory recall …` from PATH. Returns None when the first argument is
    not a part (typer handles it), else the part's exit code. The umbrella never knows the part's language."""
    if not argv:
        return None
    name = argv[0]
    if name.startswith("-") or name in {
        c.name or (c.callback.__name__ if c.callback else "") for c in app.registered_commands
    }:
        return None
    known = {(c.name or (c.callback.__name__ if c.callback else "")).replace("_", "-") for c in app.registered_commands}
    if name in known:
        return None
    exe = shutil.which(f"isidium-{name}")
    if exe is None:
        return None
    return subprocess.run([exe, *argv[1:]], check=False).returncode


def main() -> int:
    code = dispatch_part(sys.argv[1:])
    if code is not None:
        return code
    try:
        app()
    except SystemExit as e:  # typer's own exit
        return int(e.code or 0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
