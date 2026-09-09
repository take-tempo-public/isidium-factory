"""`accept <id> [--close]` (03 §1.13) — the acceptance block compiled, run at the owner's terminal, and the one write
that closes [L3, 2026-09-09; Q-W2 ruled: a client verb].

**One read, the runs, at most one write.** `show card` answers the store's copy of the card — the ratified content,
its projected `label` and its compare-and-swap head — in one round trip; the checkout's `config.toml` answers the
`[runners]` bindings and the standalone dial through the registry's effective overlay, locally; the manifest is
`core.manifest`'s pure compile; the scenarios run in the checkout's working tree through `client.runners`; and
`--close` is one `write` of that same document with a `[[closures]]` entry appended and `status = "closed"`, which
the store derives as `closed` (03 §1.13). Nothing here writes inside the tracking root.

**The refusal before anything runs** is the store's label, not a guess of this module's: a `draft` row is
`accept.draft` (*"a planted draft's `command` scenarios must not run in the owner's shell"*) unless `--unsafe-draft`,
which prints each argv and asks; `unratified`, `integrity(…)`, `withdrawn` and `unknown` are `accept.unratified` —
*"no verifiable ratification signature"* is what those rows mean, and the store computes them with the bindings it
holds. The dial: `ratification.verdicts_required` (G13) — with it true a card with no runnable scenario cannot close
(`accept.no-verdicts`); with it false it may.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Final

from ..core import manifest as manifest_mod
from ..core.grammar import parse_config
from ..core.refusal import Refusal
from ..registry.config import CONFIG_ORDERS, resolve_effective
from ..registry.loader import Registry
from . import runners as runners_mod

Call = Callable[[str, Mapping[str, Any]], Any]
Confirm = Callable[[str], bool]

# The label rows that refuse before anything runs (03 §1.5's rows 1–4 and the two the projection names for a card it
# cannot place). `draft` is its own refusal because `--unsafe-draft` lifts it and nothing lifts the others.
REFUSED_ROWS: Final[frozenset[str]] = frozenset({"unratified", "integrity", "withdrawn", "unknown"})
ASKS: Final[frozenset[str]] = frozenset({"command", "file-assert"})


def _row(label: str) -> str:
    return label.split(" ", 1)[0].split("(", 1)[0]


def _effective(workdir: Path, root: str) -> dict[str, Any]:
    cfg = workdir / root / "config.toml"
    try:
        raw = cfg.read_text(encoding="utf-8")
    except OSError as e:
        raise Refusal("accept.no-config", str(cfg), str(e)) from None
    tree, _entries, rs = parse_config(raw, CONFIG_ORDERS)
    fatal = [r for r in rs if r.rule == "head.toml"]
    if fatal:
        raise fatal[0]
    return resolve_effective(tree, Registry.for_checkout(workdir))


def accept(
    call: Call,
    workdir: Path,
    root: str,
    card_id: int,
    *,
    close: bool = False,
    unsafe_draft: bool = False,
    deviated: str | None = None,
    confirm: Confirm | None = None,
) -> dict[str, Any]:
    """The verb. `call` is the channel (`Transport.call`, or the api itself in a test); `confirm` asks a human."""
    card = call("show", {"target": "card", "id": card_id})
    label = str(card["label"])
    row = _row(label)
    if row == "draft" and not unsafe_draft:
        raise Refusal(
            "accept.draft", str(card_id), "a draft's scenarios do not run here; --unsafe-draft prints and asks"
        )
    if row in REFUSED_ROWS:
        raise Refusal("accept.unratified", str(card_id), f"the store projects {label!r}: no verifiable ratification")
    eff = _effective(workdir, root)
    manifest = manifest_mod.compile_acceptance(
        card["head"].get("acceptance") or {}, eff["runners"], runners_mod.RUNNERS
    )
    required = bool(eff["ratification"]["verdicts_required"])
    verdicts: list[runners_mod.Verdict] = []
    for entry in manifest.entries:
        if isinstance(entry, manifest_mod.Manual):
            verdicts.append(runners_mod.Verdict(entry.scenario_id, "manual", entry.evidence))
            continue
        if row == "draft" and entry.kind in ASKS:
            argv = (entry.params.get("action") or {}).get("run") or []
            asked = f"{entry.scenario_id} ({entry.kind}) would run: {' '.join(str(a) for a in argv) or '<no command>'}"
            if confirm is None or not confirm(asked):
                verdicts.append(
                    runners_mod.Verdict(entry.scenario_id, "fail", "declined at the terminal (--unsafe-draft)")
                )
                continue
        verdicts.append(runners_mod.RUNNERS[entry.runner](entry, workdir))
    # Vacuously true with no scenario: what that may close is the dial's question, asked below, not this line's.
    passed = all(v.verdict == "pass" for v in verdicts)
    result: dict[str, Any] = {
        "id": card_id,
        "label": label,
        "manifest_hash": manifest.hash,
        "verdicts": [{"scenario_id": v.scenario_id, "verdict": v.verdict, "detail": v.detail} for v in verdicts],
        "passed": passed,
    }
    if not close:
        return result
    if not verdicts and required:
        raise Refusal("accept.no-verdicts", str(card_id), "verdicts_required is true and the card has no scenario")
    if passed:
        outcome: Any = "met"
    elif deviated:
        outcome = {"deviated": {"description": deviated}}
    else:
        failed = ", ".join(v.scenario_id for v in verdicts if v.verdict != "pass")
        raise Refusal("accept.failed", str(card_id), f"not met: {failed}; --deviated <why> closes as deviated")
    head = dict(card["head"])
    closures = list(head.get("closures") or [])
    closures.append(
        {
            "id": f"c{len(closures) + 1}",
            "kind": "human",
            "outcome": outcome,
            "verdicts": {v.scenario_id: v.verdict for v in verdicts},
            "evidence": [manifest.hash],
            "retracted": False,
        }
    )
    head["closures"] = closures
    head["status"] = "closed"
    document: dict[str, Any] = {"head": head}
    if card.get("scope") is not None:
        document["scope"] = card["scope"]
    if card.get("updates"):
        document["updates"] = card["updates"]
    result["closed"] = call("write", {"card": card_id, "document": document, "base": card["cas"]})
    return result
