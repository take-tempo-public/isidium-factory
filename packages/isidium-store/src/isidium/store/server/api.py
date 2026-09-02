"""The store's typed call surface — one implementation, three transports (03 §1.2: *"the CLI (`cards …`) and the
MCP / tool-call surface wrap the same schema; callers pass typed arguments"*). Every method takes and returns plain
JSON-able values validated against the generated model (registry/codegen.py), so the HTTP service, the MCP tool
surface and the in-process CLI are three thin skins over this one object.

The typed model is validated here and dumped with `exclude_unset=True, by_alias=True` into the raw value tree the
store hashes (W10, T6): absent stays absent."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, ClassVar

from pydantic import ValidationError

from ..core.grammar import Document, UpdateBlock
from ..core.refusal import Refusal
from ..registry.generated.models import CardHead
from .identity import Caller
from .store import NewCard, Store, WriteRequest


def _document(payload: Mapping[str, Any], *, allocated_id: int = 0) -> Document:
    """A typed card document from the tool-call form `{head, scope?, updates?}`: the head is validated against the
    generated model, then dumped back to the raw value tree (never the model) for the hasher."""
    head_in = dict(payload.get("head") or {})
    head_in.setdefault("id", allocated_id or 0)
    try:
        head = CardHead.model_validate(head_in).model_dump(exclude_unset=True, by_alias=True)
    except ValidationError as e:
        raise Refusal(
            "head.typed",
            "head",
            "; ".join(f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}" for err in e.errors()[:6]),
        ) from None
    sections: dict[str, str | list[UpdateBlock]] = {}
    if payload.get("scope") is not None:
        sections["Scope"] = str(payload["scope"])
    ups = payload.get("updates")
    if ups:
        sections["Updates"] = [
            {"date": "", "title": str(u.get("title", "")), "body": str(u.get("body", ""))} for u in ups
        ]
    return Document(head, sections)


class Api:
    """The verbs as typed calls. `caller` is resolved by the transport (a client certificate, the session credential,
    the CLI's configured identity) and passed per call — the store attests it on every journaled write (1.15)."""

    def __init__(self, store: Store) -> None:
        self.store = store

    # ---- write / ratify -------------------------------------------------------------------------------------------

    def write(self, caller: Caller, args: Mapping[str, Any]) -> dict[str, Any]:
        doc_in = args.get("document") or {}
        ref = args.get("ref")
        if args.get("new_slug"):
            doc = _document(doc_in)
            r = self.store.write(NewCard(str(args["new_slug"])), doc, None, ref, caller)
        else:
            cid = int(args["card"])
            path = self.store.path_of(cid)
            if path is None:
                raise Refusal("show.unknown", str(cid))
            doc = _document(doc_in, allocated_id=cid)
            incoming = doc.sections.get("Updates")
            if isinstance(incoming, list):  # the store stamps the header; the blocks the card already has stay
                existing = self.store.docs[path].updates()
                today = self.store.now()[:10]
                fresh: list[UpdateBlock] = [
                    {"date": today, "title": b["title"], "body": b["body"]} for b in incoming[len(existing) :]
                ]
                doc.sections["Updates"] = [*existing, *fresh]
            r = self.store.write(path, doc, args.get("base"), ref, caller)
        return {
            "path": r.path,
            "id": r.id,
            "entry": r.entry,
            "head": r.head,
            "commit": r.commit,
            "journal_seq": r.journal_seq,
        }

    def write_set(self, caller: Caller, card: int, sets: Sequence[str], ref: Any = None) -> dict[str, Any]:
        r = self.store.write_set(card, list(sets), caller, ref)
        return {
            "path": r.path,
            "id": r.id,
            "entry": r.entry,
            "head": r.head,
            "commit": r.commit,
            "journal_seq": r.journal_seq,
        }

    def ratify(self, caller: Caller, args: Mapping[str, Any]) -> dict[str, Any]:
        dry = bool(args.get("dry_run", True))
        writes: list[int | WriteRequest] = [int(i) for i in args.get("ids") or []]
        for w in args.get("writes") or []:
            doc_in = w.get("document") or {}
            if w.get("new_slug"):
                writes.append(WriteRequest(NewCard(str(w["new_slug"])), _document(doc_in), None, w.get("ref")))
            else:
                cid = int(w["card"])
                path = self.store.path_of(cid)
                if path is None:
                    raise Refusal("show.unknown", str(cid))
                writes.append(WriteRequest(path, _document(doc_in, allocated_id=cid), w.get("base"), w.get("ref")))
        return self.store.ratify(writes, caller, dry_run=dry)

    # ---- reads ---------------------------------------------------------------------------------------------------

    def show(self, caller: Caller, args: Mapping[str, Any]) -> dict[str, Any]:
        self.store._require(caller, "show")
        target = str(args.get("target", "card"))
        if target == "card":
            doc, head = self.store.show(int(args["id"]))
            return {
                "head": doc.head,
                "scope": doc.scope(),
                "updates": doc.updates(),
                "history": doc.history,
                "cas": head,
                "label": self.store.projections()[int(args["id"])].render(),
            }
        if target == "inbox":
            return {"records": self.store.show("Inbox")}
        if target == "queue":
            q = self.store.show("Queue")
            return {
                "open_questions": list(q.open_questions),
                "holds_on_owner": list(q.holds_on_owner),
                "closures_pending_review": list(q.closures_pending_review),
                "withdrawals_pending": list(q.withdrawals_pending),
                "blocked_by_those": list(q.blocked_by_those),
                "dispositions_since_batch": q.dispositions_since_batch,
                "inbox_counts": dict(q.inbox_counts),
                "merged_not_landed": q.merged_not_landed,
            }
        if target == "board":
            return {"markdown": self.store.show("Board")}
        if target == "schema":
            return {"schema": self.store.show(("Schema", str(args["name"])))}
        raise Refusal("show.unsupported-target", target)

    def check(self, caller: Caller, args: Mapping[str, Any]) -> dict[str, Any]:
        self.store._require(caller, "check")
        return self.store.check(int(args["id"]))

    # ---- the inbox ------------------------------------------------------------------------------------------------

    def suggest(self, caller: Caller, args: Mapping[str, Any]) -> dict[str, Any]:
        """`source` is optional: the store fills the schema's default when the caller does not name one."""
        r = self.store.suggest(
            caller,
            str(args["kind"]),
            str(args["title"]),
            str(args["body"]),
            [str(x) for x in args.get("refs") or []],
            str(args["source"]) if args.get("source") else "session",  # this API call IS a session
            int(args["proposed_for"]) if args.get("proposed_for") else None,
        )
        return {"record": r.entry, "commit": r.commit}

    def disposition(self, caller: Caller, args: Mapping[str, Any]) -> dict[str, Any]:
        out = self.store.disposition(
            str(args["suggestion"]),
            str(args["outcome"]),
            caller,
            as_=args.get("as"),
            reason=args.get("reason"),
            until=args.get("until"),
            slug=str(args.get("slug", "from-suggestion")),
        )
        return {k: (v.entry if hasattr(v, "entry") else v) for k, v in out.items()} | {
            "card": out["card"].id if "card" in out else None
        }

    # ---- repair ---------------------------------------------------------------------------------------------------

    def repair(self, caller: Caller, args: Mapping[str, Any]) -> dict[str, Any]:
        return self.store.repair(
            caller,
            history=int(args["history"]) if args.get("history") else None,
            restart_from=int(args["restart_from"]) if args.get("restart_from") else None,
            journal=args.get("journal"),
        )

    # ---- init (04 §3) ---------------------------------------------------------------------------------------------

    def init(self, caller: Caller, args: Mapping[str, Any]) -> dict[str, Any]:
        r = self.store.init(
            caller,
            ratifier_fpr=args.get("ratifier_fpr"),
            software_key_ack=args.get("software_key_ack"),
            root=args.get("root"),
            extra=args.get("extra") or {},
        )
        return {"entry": r.entry, "commit": r.commit, "journal_seq": r.journal_seq}

    # ---- dispatch by name (the transports' one entry point) --------------------------------------------------------

    CALLS = ("init", "write", "write_set", "ratify", "show", "check", "suggest", "disposition", "repair")

    # The two verbs of the ten this surface does not carry yet; they arrive with the sidecar and the runners (WP5).
    LATER: ClassVar[dict[str, str]] = {"land": "the sidecar's landing", "accept": "the acceptance runners"}

    def call(self, name: str, caller: Caller, args: Mapping[str, Any]) -> Any:
        if name in self.LATER:
            raise Refusal("api.not-yet", name, self.LATER[name] + " arrives with v1b; this build does not carry it")
        if name not in self.CALLS:
            raise Refusal("api.unknown-call", name, "the surface carries: " + ", ".join(self.CALLS))
        if name == "write_set":
            return self.write_set(caller, int(args["card"]), [str(s) for s in args.get("set") or []], args.get("ref"))
        return getattr(self, name)(caller, args)
