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
from .store import NewCard, Store, WriteRequest, WriteResult

# ---- the typed readers [K7b, F12] --------------------------------------------------------------------------------
#
# Every argument this surface reads comes through one of these, and a value of the wrong JSON type is
# `service.arguments` on the key that carried it — full disclosure, because it is about the caller's own request.
# Before K7b the arguments were read with `.get` and iterated: `{"ids": "12"}` ratified cards 1 and 2 (a string
# iterates as characters, the C-2 shape at the boundary), `{"refs": "ab"}` cited `a` and `b`, and a table where a
# list was expected fell through `Service.handle`'s last arm as `service.internal` — a bug in us, with Python's own
# words in the record, for a planner's typo. `bool` is refused where an `int` is expected (it is one, to Python).


def _wrong(key: str, expected: str, got: Any) -> Refusal:
    return Refusal("service.arguments", key, f"expected {expected}, got {type(got).__name__}")


def _int(args: Mapping[str, Any], key: str) -> int | None:
    v = args.get(key)
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, int):
        raise _wrong(key, "an integer", v)
    return v


def _need_int(args: Mapping[str, Any], key: str) -> int:
    v = _int(args, key)
    if v is None:
        raise Refusal("service.arguments", key, "required: an integer")
    return v


def _str(args: Mapping[str, Any], key: str) -> str | None:
    v = args.get(key)
    if v is None:
        return None
    if not isinstance(v, str):
        raise _wrong(key, "a string", v)
    return v


def _need_str(args: Mapping[str, Any], key: str) -> str:
    v = _str(args, key)
    if v is None:
        raise Refusal("service.arguments", key, "required: a string")
    return v


def _bool(args: Mapping[str, Any], key: str, default: bool) -> bool:
    v = args.get(key)
    if v is None:
        return default
    if not isinstance(v, bool):
        raise _wrong(key, "a boolean", v)
    return v


def _table(args: Mapping[str, Any], key: str) -> dict[str, Any] | None:
    v = args.get(key)
    if v is None:
        return None
    if not isinstance(v, dict):
        raise _wrong(key, "a table", v)
    return v


def _list_of_int(args: Mapping[str, Any], key: str) -> list[int]:
    v = args.get(key)
    if v is None:
        return []
    if not isinstance(v, list) or any(isinstance(x, bool) or not isinstance(x, int) for x in v):
        raise _wrong(key, "a list of integers", v)
    return v


def _list_of_str(args: Mapping[str, Any], key: str) -> list[str]:
    v = args.get(key)
    if v is None:
        return []
    if not isinstance(v, list) or any(not isinstance(x, str) for x in v):
        raise _wrong(key, "a list of strings", v)
    return v


def _list_of_table(args: Mapping[str, Any], key: str) -> list[dict[str, Any]]:
    v = args.get(key)
    if v is None:
        return []
    if not isinstance(v, list) or any(not isinstance(x, dict) for x in v):
        raise _wrong(key, "a list of tables", v)
    return v


def _document(payload: Mapping[str, Any], *, allocated_id: int = 0) -> Document:
    """A typed card document from the tool-call form `{head, scope?, updates?}`: the head is validated against the
    generated model, then dumped back to the raw value tree (never the model) for the hasher."""
    head_in = dict(_table(payload, "head") or {})
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
    scope = _str(payload, "scope")
    if scope is not None:
        sections["Scope"] = scope
    ups = _list_of_table(payload, "updates")
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

    @staticmethod
    def _written(r: WriteResult) -> dict[str, Any]:
        """One write's result, as the caller receives it. `landed` [K7b, Q18]: `False` is a journaled act whose push
        failed — the entry and the head are the caller's to keep, and `main` lags until the store's next push."""
        return {
            "path": r.path,
            "id": r.id,
            "entry": r.entry,
            "head": r.head,
            "commit": r.commit,
            "journal_seq": r.journal_seq,
            "landed": r.landed,
        }

    def write(self, caller: Caller, args: Mapping[str, Any]) -> dict[str, Any]:
        doc_in = _table(args, "document") or {}
        ref = args.get("ref")
        base = _table(args, "base")
        if _str(args, "path") == "config.toml":
            # **The `config-policy` act's door** [K6]. Every change to `config.toml` is a signed policy act performed
            # through `write` (04 §1, V5) — and until this arm existed the only such act reachable over the channel
            # was `init`: this method read the card arguments only, so a tenant could adopt nothing after its first
            # write. The document is the TOML tree without `[history]`, and `base` is the policy head the caller
            # last saw; `Store._write_policy` owns the grant, the compare-and-swap and the validation.
            return self._written(self.store.write("config.toml", doc_in, base, ref, caller))
        new_slug = _str(args, "new_slug")
        if new_slug:
            return self._written(self.store.write(NewCard(new_slug), _document(doc_in), None, ref, caller))
        cid = _need_int(args, "card")
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
        return self._written(self.store.write(path, doc, base, ref, caller))

    def write_set(self, caller: Caller, card: int, sets: Sequence[str], ref: Any = None) -> dict[str, Any]:
        return self._written(self.store.write_set(card, list(sets), caller, ref))

    def ratify(self, caller: Caller, args: Mapping[str, Any]) -> dict[str, Any]:
        dry = _bool(args, "dry_run", True)
        writes: list[int | WriteRequest] = list(_list_of_int(args, "ids"))
        for w in _list_of_table(args, "writes"):
            doc_in = _table(w, "document") or {}
            new_slug = _str(w, "new_slug")
            if new_slug:
                writes.append(WriteRequest(NewCard(new_slug), _document(doc_in), None, w.get("ref")))
            else:
                cid = _need_int(w, "card")
                path = self.store.path_of(cid)
                if path is None:
                    raise Refusal("show.unknown", str(cid))
                writes.append(WriteRequest(path, _document(doc_in, allocated_id=cid), _table(w, "base"), w.get("ref")))
        return self.store.ratify(writes, caller, dry_run=dry)

    # ---- reads ---------------------------------------------------------------------------------------------------

    def show(self, caller: Caller, args: Mapping[str, Any]) -> dict[str, Any]:
        self.store._require(caller, "show")
        target = _str(args, "target") or "card"
        if target == "card":
            cid = _need_int(args, "id")
            doc, head = self.store.show(cid)
            return {
                "head": doc.head,
                "scope": doc.scope(),
                "updates": doc.updates(),
                "history": doc.history,
                "cas": head,
                # One card's projection, not every card's [K7b, F9]: the label the planner reads most often used to
                # cost the whole tenant — a chain and a signature verification per card — to render one word.
                "label": self.store.projection_of(cid).render(),
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
            return {"schema": self.store.show(("Schema", _need_str(args, "name")))}
        raise Refusal("show.unsupported-target", target)

    def check(self, caller: Caller, args: Mapping[str, Any]) -> dict[str, Any]:
        self.store._require(caller, "check")
        return self.store.check(_need_int(args, "id"))

    # ---- the inbox ------------------------------------------------------------------------------------------------

    def suggest(self, caller: Caller, args: Mapping[str, Any]) -> dict[str, Any]:
        """`source` is optional: the store fills the schema's default when the caller does not name one."""
        r = self.store.suggest(
            caller,
            _need_str(args, "kind"),
            _need_str(args, "title"),
            _need_str(args, "body"),
            _list_of_str(args, "refs"),
            _str(args, "source") or "session",  # this API call IS a session
            _int(args, "proposed_for"),
        )
        return {"record": r.entry, "commit": r.commit, "landed": r.landed}

    def disposition(self, caller: Caller, args: Mapping[str, Any]) -> dict[str, Any]:
        out = self.store.disposition(
            _need_str(args, "suggestion"),
            _need_str(args, "outcome"),
            caller,
            as_=_str(args, "as"),
            reason=_str(args, "reason"),
            until=args.get(
                "until"
            ),  # a date or a condition (03a): the schema types it as a string, the store reads it as one
            slug=_str(args, "slug") or "from-suggestion",
        )
        return {k: (v.entry if hasattr(v, "entry") else v) for k, v in out.items()} | {
            "card": out["card"].id if "card" in out else None,
            "landed": all(v.landed for v in out.values() if isinstance(v, WriteResult)),
        }

    # ---- repair ---------------------------------------------------------------------------------------------------

    def repair(self, caller: Caller, args: Mapping[str, Any]) -> dict[str, Any]:
        return self.store.repair(
            caller,
            history=_int(args, "history"),
            restart_from=_int(args, "restart_from"),
            journal=_str(args, "journal"),
        )

    # ---- init (04 §3) ---------------------------------------------------------------------------------------------

    def init(self, caller: Caller, args: Mapping[str, Any]) -> dict[str, Any]:
        r = self.store.init(
            caller,
            ratifier_fpr=_str(args, "ratifier_fpr"),
            software_key_ack=_str(args, "software_key_ack"),
            root=_str(args, "root"),
            extra=_table(args, "extra") or {},
        )
        return {"entry": r.entry, "commit": r.commit, "journal_seq": r.journal_seq, "landed": r.landed}

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
            return self.write_set(caller, _need_int(args, "card"), _list_of_str(args, "set"), args.get("ref"))
        return getattr(self, name)(caller, args)
