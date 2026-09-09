"""`isidium-factory` — the factory's own verbs; reached as `isidium factory <verb>` through the umbrella's PATH
dispatch (7bf.3), or directly. v1b carries one: `land`."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated, Any, NoReturn

import typer

from isidium.store.core import telemetry
from isidium.store.core.refusal import Refusal

from . import lander

app = typer.Typer(add_completion=False, no_args_is_help=True, help="isidium-factory — the line's own verbs.")


@app.callback()
def _verbs() -> None:
    """The factory's verbs — `isidium factory <verb>`, or `isidium-factory <verb>`. One today: `land`."""
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


def main() -> int:
    try:
        app()
    except SystemExit as e:  # typer's own exit
        return int(e.code or 0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
