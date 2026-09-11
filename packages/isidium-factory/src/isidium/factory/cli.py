"""`isidium-factory` — the factory's own verbs; reached as `isidium factory <verb>` through the umbrella's PATH
dispatch (7bf.3), or directly. v1b carries `land`; v1c's V1 adds `payload`; V2 adds `context`, `push`, `pr-open` and
`pr-status` — the tenant context printed with its hash (T-C1's observable), and the forge driver's four calls."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated, Any, NoReturn

import typer

from isidium.store.client.transport import Transport
from isidium.store.core import telemetry
from isidium.store.core.refusal import Refusal

from . import checkout, context, forge, github, lander
from . import payload as payload_mod
from .registration import tenant_client

app = typer.Typer(add_completion=False, no_args_is_help=True, help="isidium-factory — the line's own verbs.")


@app.callback()
def _verbs() -> None:
    """The factory's verbs — `isidium factory <verb>`, or `isidium-factory <verb>`: `land`, `payload`, `context`,
    `push`, `pr-open`, `pr-status`."""
    # A callback keeps `land` a subcommand: with one command and no callback typer makes it the root, and the
    # umbrella's dispatch (`isidium factory land …` → `isidium-factory land …`) would hand it its own name as an
    # argument.


def _refuse(r: Refusal) -> NoReturn:
    """The one refusal site, as the store client's: counted, printed whole (a human at their own terminal), exit 2."""
    telemetry.record_refusal(r.rule)
    typer.echo(str(r), err=True)
    raise typer.Exit(2)


def _out(value: Any) -> None:
    typer.echo(json.dumps(value, indent=2, default=str, ensure_ascii=False))


@app.command()
def land(
    tenant: Annotated[str, typer.Option("--tenant", help="the tenant, a directory under $ISIDIUM_DEPLOY")],
    report: Annotated[Path, typer.Option("--report", help="the run report: JSON {run_id, events[], suggestions[]}")],
) -> None:
    """Land a run report on the tenant's `main` as its lander (T-A10, X2): one call, the store's result back."""
    try:
        _out(lander.land(tenant, lander.read_report(report)))
    except Refusal as r:
        _refuse(r)


@app.command()
def payload(
    tenant: Annotated[str, typer.Option("--tenant", help="the tenant, a directory under $ISIDIUM_DEPLOY")],
    checkout_path: Annotated[Path, typer.Option("--checkout", help="the project checkout the payload is read from")],
    card: Annotated[int, typer.Option("--card", help="the card id")],
    bot: Annotated[str, typer.Option("--bot", help="the identity the run carries (V3 fills it from config)")],
    adapter: Annotated[str, typer.Option("--adapter", help="the execution adapter the run names (V4's)")],
    max_bytes: Annotated[int, typer.Option("--max-bytes", help="the byte cap the value must fit (Q-V8)")],
    rev: Annotated[str, typer.Option("--rev", help="the revision the payload is read at")] = "HEAD",
    root: Annotated[
        str | None, typer.Option("--root", help="the tracking root; default: the checkout's client")
    ] = None,
    out: Annotated[Path | None, typer.Option("--out", help="write the whole value here as JSON")] = None,
) -> None:
    """Assemble one card's run payload (T-B3) from the checkout at `--rev` and the tenant's store: prints the run
    record's fields; `--out` keeps the value."""
    try:
        cfg, workdir = tenant_client(tenant)
        channel = Transport(cfg, workdir)
        inp = checkout.gather(
            checkout_path,
            rev,
            card,
            tenant=tenant,
            root=root,
            context_of=lambda cid: channel.call("show", {"target": "neighborhood", "id": cid}),
            identity=payload_mod.Identity(bot, adapter),
            caps=payload_mod.Caps(max_bytes),
        )
        p = payload_mod.assemble(inp)
    except Refusal as r:
        _refuse(r)
    if out is not None:
        out.write_text(json.dumps(p.value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    _out(p.record())


TENANT = Annotated[str, typer.Option("--tenant", help="the tenant, a directory under $ISIDIUM_DEPLOY")]
CHECKOUT = Annotated[Path, typer.Option("--checkout", help="the project checkout the factory works in")]
BASE = Annotated[str, typer.Option("--base", help="the ref the line syncs from (fetched from the remote)")]
ROOT = Annotated[str | None, typer.Option("--root", help="the tracking root; default: the checkout's client")]


def _driver(
    tenant: str, checkout_path: Path, base: str, root: str | None
) -> tuple[context.TenantContext, github.GitHub]:
    ctx = context.load(tenant, checkout_path, base=base, root=root)
    return ctx, github.GitHub(ctx)


@app.command("context")
def context_verb(tenant: TENANT, checkout_path: CHECKOUT, base: BASE = "main", root: ROOT = None) -> None:
    """Load the tenant context (T-C1) and print its value and hash — the same hash twice is the round trip."""
    try:
        ctx = context.load(tenant, checkout_path, base=base, root=root)
    except Refusal as r:
        _refuse(r)
    _out({"hash": ctx.hash, "value": ctx.value()})


@app.command()
def push(
    tenant: TENANT,
    checkout_path: CHECKOUT,
    branch: Annotated[str, typer.Option("--branch", help="the local branch to push")],
    at: Annotated[str | None, typer.Option("--at", help="create the branch at this commit first")] = None,
    base: BASE = "main",
    root: ROOT = None,
) -> None:
    """Push a code-only branch as the tenant's forge identity; a governed path in the diff is refused before any
    push (exit 2, every offending path named)."""
    try:
        ctx, drv = _driver(tenant, checkout_path, base, root)
        if at is not None:
            drv.branch(branch, at)
        ch = drv.push(branch)
    except Refusal as r:
        _refuse(r)
    _out({"branch": branch, "base_sha": ctx.base_sha, "files": list(ch.paths)})


@app.command("pr-open")
def pr_open(
    tenant: TENANT,
    checkout_path: CHECKOUT,
    branch: Annotated[str, typer.Option("--branch", help="the pushed branch")],
    base: BASE = "main",
    root: ROOT = None,
) -> None:
    """Open the pull request for a pushed branch, its body generated from the context and the diff."""
    try:
        ctx, drv = _driver(tenant, checkout_path, base, root)
        spec = forge.pr_text(ctx, branch, drv.changed(ctx.base_sha, branch))
        pr = drv.open_pr(spec)
    except Refusal as r:
        _refuse(r)
    _out({"number": pr.number, "url": pr.url, "head": pr.head})


@app.command("pr-status")
def pr_status(
    tenant: TENANT,
    checkout_path: CHECKOUT,
    number: Annotated[int, typer.Option("--pr", help="the pull request number")],
    base: BASE = "main",
    root: ROOT = None,
) -> None:
    """The pull request's merge state and the required checks on its head, with the verdict."""
    try:
        _ctx, drv = _driver(tenant, checkout_path, base, root)
        state = drv.merge_state(number)
        checks = drv.checks(state.head)
    except Refusal as r:
        _refuse(r)
    _out(
        {
            "merged": state.merged,
            "mergeable": state.mergeable,
            "state": state.state.value,
            "merge_commit": state.merge_commit,
            "head": state.head,
            "verdict": checks.verdict.value,
            "required": list(checks.required),
            "runs": [{"name": c.name, "status": c.status, "conclusion": c.conclusion} for c in checks.runs],
        }
    )


def main() -> int:
    try:
        app()
    except SystemExit as e:  # typer's own exit
        return int(e.code or 0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
