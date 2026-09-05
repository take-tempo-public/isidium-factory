"""The tool-call surface (03 §1.2: *"for agents the tool-call surface is the intended one"*) — an MCP server over
stdio, JSON-RPC 2.0: `initialize`, `tools/list`, `tools/call`. The tool input schemas are **generated from the
registry** (registry/codegen.py), so the model is constrained to the schema's form at the moment it writes — that is
what makes "no freehand" cheap rather than bureaucratic (round 57).

No SDK dependency: the protocol subset the planner needs is a read loop and three methods (the efficiency lens,
round 42). A refusal is returned as a tool result with `isError`, carrying its rule id — the planner reads rule ids,
not prose.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, BinaryIO, Final

from ..core.refusal import Refusal
from ..registry.codegen import tool_schemas
from . import locus
from .config import ClientConfig
from .transport import Channel, Transport

PROTOCOL: Final = "2025-06-18"
SERVER: Final = {"name": "isidium-store", "version": "0.1.0"}


def tools() -> list[dict[str, Any]]:
    return [
        {"name": name, "description": spec["description"], "inputSchema": spec["inputSchema"]}
        for name, spec in sorted(tool_schemas().items())
    ]


class McpServer:
    """One tenant's store as tools. `transport` is the same object the CLI uses: the pinned channel (7bg.2).

    `workdir` and `root` are the checkout this server runs in and its tracking root — for the ref pre-flight the
    CLI's `write` and `ratify` also run (K4b, `client/locus.py`). The planner drafts most cards, so this is the door
    where a ref whose locus does not land is most often written; it learns here, at draft time, what the assembler
    would otherwise refuse at dispatch. Both are required: a server that could be built without a checkout would be
    one that silently ran no pre-flight."""

    def __init__(self, transport: Channel, workdir: Path, root: str) -> None:
        self.transport = transport
        self.workdir = workdir
        self.root = root
        self.tools = {t["name"]: t for t in tools()}

    def handle(self, request: Mapping[str, Any]) -> dict[str, Any] | None:
        method, rid = str(request.get("method", "")), request.get("id")
        params = request.get("params") or {}
        if method == "initialize":
            return self._ok(rid, {"protocolVersion": PROTOCOL, "capabilities": {"tools": {}}, "serverInfo": SERVER})
        if method in ("notifications/initialized", "notifications/cancelled"):
            return None
        if method == "tools/list":
            return self._ok(rid, {"tools": list(self.tools.values())})
        if method == "tools/call":
            return self._call(rid, str(params.get("name", "")), params.get("arguments") or {})
        if method == "ping":
            return self._ok(rid, {})
        return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"unknown method {method!r}"}}

    def _call(self, rid: Any, name: str, args: Mapping[str, Any]) -> dict[str, Any]:
        if name not in self.tools:
            return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32602, "message": f"unknown tool {name!r}"}}
        try:
            locus.preflight(name, args, self.workdir, self.root)  # the same door as the CLI's, before the channel
            result = self.transport.call(name, args)
        except Refusal as r:
            # `r.payload()`, not a dict built here: a validation refusal reaches the model as an ARRAY of typed
            # verdicts, each naming its own failed field, which is what lets the planner self-correct instead of
            # parsing them back out of prose (Q7, C-12). This door is the one Q7 was argued from, and C-12's
            # disclosure filter has to hold here as much as at the HTTP door — which it does, because the filter
            # lives inside `payload()`. **Called once**: `payload()` also records the refusal on the running span
            # and on the counter, so calling it twice would count one refusal as two.
            disclosed = r.payload()
            return self._ok(
                rid,
                {
                    "content": [{"type": "text", "text": json.dumps(disclosed, ensure_ascii=False)}],
                    "structuredContent": disclosed,
                    "isError": True,
                },
            )
        return self._ok(
            rid,
            {
                "content": [{"type": "text", "text": json.dumps(result, default=str, ensure_ascii=False)}],
                "structuredContent": {"result": result},
            },
        )

    @staticmethod
    def _ok(rid: Any, result: Mapping[str, Any]) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": rid, "result": dict(result)}

    def serve(self, stdin: BinaryIO | None = None, stdout: BinaryIO | None = None) -> None:
        """The stdio loop: one JSON-RPC message per line (the newline-delimited framing MCP stdio uses)."""
        rin = stdin or sys.stdin.buffer
        rout = stdout or sys.stdout.buffer
        for raw in rin:
            line = raw.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
            except ValueError:
                rout.write(
                    json.dumps(
                        {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
                    ).encode()
                    + b"\n"
                )
                rout.flush()
                continue
            response = self.handle(request)
            if response is not None:
                rout.write(json.dumps(response, default=str, ensure_ascii=False).encode("utf-8") + b"\n")
                rout.flush()


def main() -> int:
    cfg, workdir = ClientConfig.find()
    McpServer(Transport(cfg, workdir), workdir, cfg.root).serve()
    return 0
