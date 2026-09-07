"""`BOARD.md` (03 §1.16) — the queue first, then the inbox, then Open / Blocked / Deferred / Watching with epics
nesting their children. Id first; caps per segment, never per line; summaries labeled, never signed; nothing reads
it. Rendered by the store at land and on demand (`show Board`)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .grammar import Document
from .status import Projection, Queue

CAP_TITLE, CAP_HOLD, CAP_SUMMARY = 120, 80, 120


def _cap(s: str, n: int) -> str:
    s = s.replace("·", "\\·")
    return s if len(s) <= n else s[: n - 1] + "…"


def _hold_on(h: Any) -> str:
    if not isinstance(h, Mapping) or "on" not in h:
        return ""
    on = h["on"]
    if not isinstance(on, Mapping) or not on:
        return ""
    k, v = next(iter(on.items()))
    return {"owner": "owner", "card": f"card {v}", "legacy": f"legacy {v}", "text": str(v)}.get(str(k), str(v))


def _line(cid: int, doc: Document, pr: Projection, changed_since: bool) -> str:
    h = doc.head
    label = pr.label.render() + ("".join(" · " + g.render() for g in pr.guards) if pr.guards else "")
    segs = [
        f"**{cid}**",
        _cap(str(h.get("title", "")), CAP_TITLE),
        label + (" · software-grade" if pr.software_grade else ""),
    ]
    if h.get("depends_on"):
        segs.append("depends_on " + ",".join(str(d) for d in h["depends_on"]))
    hold = _hold_on(h.get("hold"))
    if hold:
        segs.append(_cap(hold, CAP_HOLD))
    summary = h.get("summary")
    if isinstance(summary, str) and summary:
        by = next((str(e.get("by", "")) for e in reversed(doc.history) if e.get("act") == "summarized"), "")
        segs.append(
            _cap(summary, CAP_SUMMARY) + (f" by {by}" if by else "") + (" changed-since" if changed_since else "")
        )
    else:
        segs.append("(derived)")
    for s in h.get("see", []) or []:
        if isinstance(s, str) and s.startswith("legacy:"):
            segs.append(f"(was {s.split('/')[-1]})")
            break
    return " · ".join(x for x in segs if x)


def _changed_since_summary(doc: Document) -> bool:
    idx = next((i for i in range(len(doc.history) - 1, -1, -1) if doc.history[i].get("act") == "summarized"), None)
    if idx is None:
        return False
    return any(e.get("build") != doc.history[idx].get("build") for e in doc.history[idx + 1 :])


def queue_lines(q: Queue) -> list[str]:
    """The queue section (1.5, 1.16) — the heading and its rows, the board's first section and the whole of
    `show queue --text` [K10, item 6]: one renderer, called from both, so the two cannot say different things."""
    out = ["## Queue", ""]
    rows = [
        ("open questions", q.open_questions),
        ("holds on the owner", q.holds_on_owner),
        ("closures pending review", q.closures_pending_review),
        ("withdrawals pending", q.withdrawals_pending),
        ("blocked by any of those", q.blocked_by_those),
    ]
    for name, qids in rows:
        out.append(f"- {name}: " + (", ".join(f"**{i}**" for i in qids) or "none"))
    out.append(f"- dispositions since the last batch signature: {q.dispositions_since_batch}")
    out.append(
        "- merged, not landed: " + ("n/a (in-project)" if q.merged_not_landed is None else str(q.merged_not_landed))
    )
    return out


def render(
    cards: Mapping[int, Document],
    projections: Mapping[int, Projection],
    q: Queue,
    inbox: Sequence[Mapping[str, Any]],
    wip_ceiling: int,
    archive_line: str | None = None,
) -> str:
    in_flight = sum(
        1
        for p in projections.values()
        if p.label.row == "execution" and p.label.execution in ("dispatched", "parked", "answered", "complete")
    )
    out = [
        "# Board",
        "",
        f"WIP {in_flight}/{wip_ceiling} · inbox "
        + (", ".join(f"{k} {v}" for k, v in sorted(q.inbox_counts.items())) or "0"),
    ]
    if archive_line:
        out.append(archive_line)
    out += ["", *queue_lines(q), "", "## Inbox", ""]
    open_ids = {r["id"] for r in inbox if r.get("type") == "intake"}
    dispositioned = {
        r.get("on") for r in inbox if r.get("type") == "disposition" and r.get("outcome") in ("accepted", "declined")
    }
    for r in inbox:
        if r.get("type") == "intake" and r["id"] in open_ids and r["id"] not in dispositioned:
            out.append(
                f"- {r['id']} · {r.get('kind')} · {r.get('source')} · {_cap(str(r.get('title', '')), CAP_TITLE)}"
            )
    if len(out) and out[-1] == "":
        out.append("none")
    sections: dict[str, list[int]] = {"Open": [], "Blocked": [], "Deferred": [], "Watching": []}
    for cid, doc in cards.items():
        hold = doc.head.get("hold")
        kind = hold.get("kind") if isinstance(hold, Mapping) else None
        sections[{"blocked": "Blocked", "deferred": "Deferred", "watching": "Watching"}.get(str(kind), "Open")].append(
            cid
        )
    children: dict[int, list[int]] = {}
    for cid, doc in cards.items():
        par = doc.head.get("parent")
        if isinstance(par, int):
            children.setdefault(par, []).append(cid)
    nested = {k for ks in children.values() for k in ks}
    for name, ids in sections.items():
        out += ["", f"## {name}", ""]
        shown = 0
        for cid in sorted(ids):
            if cid in nested and cards[cid].head.get("parent") in cards:
                continue
            doc = cards[cid]
            out.append("- " + _line(cid, doc, projections[cid], _changed_since_summary(doc)))
            shown += 1
            for kid in sorted(children.get(cid, [])):
                out.append("  - " + _line(kid, cards[kid], projections[kid], _changed_since_summary(cards[kid])))
        if not shown:
            out.append("none")
    return "\n".join(out) + "\n"
