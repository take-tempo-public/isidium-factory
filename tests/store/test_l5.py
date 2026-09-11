"""L5 (2026-09-10) — the neighborhood projection (03 §1.17): one deterministic function of (the card graph, the
sidecar, the caps), as a `show` target. Every test names the property and asserts its positive discriminator.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from isidium.store.core import neighborhood, status
from isidium.store.server.api import Api

from .conftest import LANDER, OWNER, PLANNER, Harness, fresh
from .test_l1 import build_of
from .test_l4 import bypass, path_of


@dataclass(frozen=True)
class Graph:
    epic: int
    milestone: int
    story: int
    dep: int
    drifted: int
    subject: int
    held: int
    draft: int
    withdrawn: int
    dependent: int


def ratified(hz: Harness, slug: str, **head: Any) -> int:
    cid = hz.draft(slug, **head)
    hz.st.ratify([cid], OWNER)
    return cid


def graph(hz: Harness) -> Graph:
    """Eight settled cards and one draft around a subject: an epic over a story over the subject; a dependency
    dispatched (in-flight) and one hand-edited since its ratification (drifted); a held sibling and a draft one;
    a dependent that completed (built); a milestone card."""
    st = hz.st
    tree = dict(st.config_tree)
    tree["ladder"] = {"levels": ["phase"]}  # the chain: story under phase under epic (K10's shape)
    st.write("config.toml", tree, {"seq": st.policy[-1]["seq"], "h": st.policy[-1]["h"]}, None, OWNER)
    epic = ratified(hz, "epic", kind="epic")
    milestone = ratified(hz, "milestone-q4")  # the bound card; the `milestone` profile is a tenant's to enable (S8)
    story = ratified(hz, "story", kind="phase", parent=epic)
    dep = ratified(hz, "dep-one", surfaces=["src/one/"])
    drifted = ratified(hz, "dep-drifted")
    subject = ratified(hz, "subject", parent=story, depends_on=[dep, drifted], milestone=milestone)
    held = ratified(hz, "sibling-held", parent=story)
    draft = hz.draft("sibling-draft", parent=story)
    withdrawn = ratified(hz, "sibling-withdrawn", parent=story)
    dependent = ratified(hz, "dependent", depends_on=[subject])
    st.write_set(held, ['hold.kind="blocked"', "hold.on.owner=true"], PLANNER)
    st.write_set(withdrawn, ['status="withdrawn"', 'withdrawn_reason="superseded"'], OWNER)
    p = path_of(st, drifted)
    bypass(st, p, st.raw[p].replace(b"## Scope\n", b"## Scope\n\nhand-edited since ratification\n", 1))
    st.land(
        {
            "run_id": "r-1",
            "events": [
                {"kind": "dispatched", "card": dep, "run_id": "r-1"},
                {"kind": "dispatched", "card": dependent, "run_id": "r-1"},
                {
                    "kind": "complete",
                    "card": dependent,
                    "run_id": "r-1",
                    "batch": "b1",
                    "build_hash": build_of(st, dependent),
                    "cost_micro": 1,
                    "duration_ms": 1,
                },
            ],
        },
        LANDER,
    )
    return Graph(epic, milestone, story, dep, drifted, subject, held, draft, withdrawn, dependent)


def ids(members: tuple[neighborhood.Member, ...]) -> list[int]:
    return [m.id for m in members]


def test_the_block_names_the_graph_and_only_the_settled_cards() -> None:
    """The parent chain nearest first with Scope and label; the siblings with buckets; the dependencies and
    dependents with buckets and surfaces; the milestone with its Scope; no sprint. A draft sibling and a
    dependency whose bytes drifted from its ratified build are not members (03 §1.17's eligibility, H7)."""
    hz = fresh()
    st = hz.st
    g = graph(hz)
    assert st.projection_of(g.drifted).label.row != "ratified", "the fixture's premise: the dependency drifted"
    b = st.neighborhood_of(g.subject)
    assert ids(b.parents) == [g.story, g.epic] and b.parents[0].label == "ratified" and b.parents[0].scope
    assert ids(b.siblings) == [g.held], "a draft sibling and a withdrawn one are not settled"
    assert st.projection_of(g.withdrawn).label.row == "withdrawn" and status.build_matches_reference(
        g.withdrawn, st.cards()[g.withdrawn], st._inputs()
    ), "the fixture's premise: the withdrawn sibling's build still matches — only its status excludes it"
    assert ids(b.depends_on) == [g.dep], "the drifted dependency is not settled"
    assert b.depends_on[0].surfaces == ("src/one/",)
    assert ids(b.dependents) == [g.dependent]
    assert b.milestone is not None and b.milestone.id == g.milestone and b.milestone.scope and b.milestone.label is None
    assert b.sprint is None and b.truncated is False
    assert [m.bucket for m in (b.siblings[0], b.depends_on[0], b.dependents[0])] == ["held", "in-flight", "built"]
    assert b.parents[0].bucket is None, "the chain carries the label, not a bucket"


GOLDEN = "aaa48fbc"  # the first eight hex digits of the canonical bytes' sha256 — pinned by the first run


def test_the_same_graph_answers_the_same_bytes_twice_and_across_insertion_order() -> None:
    """Byte-stable output for a fixed graph: the canonical bytes are the same on a second call, the same when
    the cards are handed over in another order, and the same as the day they were pinned."""
    hz = fresh()
    st = hz.st
    g = graph(hz)
    inp = st._inputs()
    caps = neighborhood.caps_of(st.eff)
    once = neighborhood.project(inp, g.subject, caps, lambda c: status.project_one(inp, c)).canonical()
    twice = st.neighborhood_of(g.subject).canonical()
    reversed_inp = status.Inputs(
        dict(reversed(list(inp.cards.items()))),
        inp.state,
        inp.gated_x,
        inp.verified,
        inp.integrity,
        inp.software_fprs,
        leaf=inp.leaf,
    )
    shuffled = neighborhood.project(reversed_inp, g.subject, caps, lambda c: status.project_one(reversed_inp, c))
    assert once == twice == shuffled.canonical()
    assert json.loads(once) == st.neighborhood_of(g.subject).as_dict(), "the bytes are the block"
    assert hashlib.sha256(once).hexdigest()[:8] == GOLDEN, once.decode()


def test_depth_cuts_the_parent_chain_where_stated() -> None:
    hz = fresh()
    st = hz.st
    g = graph(hz)
    inp = st._inputs()

    def chain(depth: int) -> list[int]:
        caps = neighborhood.Caps(depth, neighborhood.caps_of(st.eff).max_bytes)
        return ids(neighborhood.project(inp, g.subject, caps, lambda c: status.project_one(inp, c)).parents)

    assert chain(2) == [g.story, g.epic] and chain(1) == [g.story] and chain(0) == []


def test_eviction_follows_the_written_order_one_member_a_step_and_every_stub_keeps_its_handle() -> None:
    """Dependencies, dependents, the parent chain from the farthest level (Scope to its first paragraph, then to
    nothing, then the member), the milestone the same way, the siblings last; an evicted member is a stub with
    `id`, `title` and the reason; `truncated` is true from the first step; the whole run is bounded."""
    hz = fresh()
    st = hz.st
    g = graph(hz)
    full = st.neighborhood_of(g.subject)
    one = neighborhood.fit(full, len(full.canonical()) - 1)
    assert one.truncated and one.depends_on[0].evicted == "max_bytes" and one.depends_on[0].id == g.dep
    assert one.depends_on[0].title == full.depends_on[0].title and one.dependents == full.dependents
    assert one.parents == full.parents and one.milestone == full.milestone and one.siblings == full.siblings

    changes: list[tuple[str, int]] = []
    cur = full
    for step in neighborhood._steps(full):
        nxt = step(cur)
        if nxt == cur:
            continue
        before, after = cur.as_dict(), nxt.as_dict()
        for key in ("dependencies", "dependents", "parents", "siblings", "milestone", "sprint"):
            if before.get(key) != after.get(key):
                moved = (
                    after[key]
                    if key in ("milestone", "sprint")
                    else next(m for m, o in zip(after[key], before[key], strict=True) if m != o)
                )
                changes.append((key, int(moved["id"])))
        cur = nxt
    assert changes == [
        ("dependencies", g.dep),
        ("dependents", g.dependent),
        ("parents", g.epic),  # Scope to nothing (one paragraph has no first paragraph to keep)
        ("parents", g.epic),  # evicted
        ("parents", g.story),
        ("parents", g.story),
        ("milestone", g.milestone),
        ("milestone", g.milestone),
        ("siblings", g.held),
    ], changes
    least = neighborhood.fit(full, 1)
    assert least.truncated and all(
        m.evicted for ms in (least.parents, least.siblings, least.depends_on, least.dependents) for m in ms
    )
    assert least.milestone is not None and least.milestone.evicted == "max_bytes"
    assert len(least.canonical()) > 1, "delivered as it is: the projection never fails readiness"


def test_a_two_paragraph_scope_is_truncated_to_its_first_before_it_goes() -> None:
    m = neighborhood.Member(7, "seven", scope="first paragraph\n\nsecond paragraph")
    first = neighborhood._shrink(m)
    assert first is not None and first.scope == "first paragraph" and first.scope_truncated
    none = neighborhood._shrink(first)
    assert none is not None and none.scope is None and none.scope_truncated
    gone = neighborhood._shrink(none)
    assert gone is not None and gone.evicted == "max_bytes" and neighborhood._shrink(gone) is None
    assert first.as_dict()["scope_truncated"] is True and "scope" not in none.as_dict()


def test_show_neighborhood_answers_the_block_and_its_delivered_text_through_the_api_and_the_cli(
    monkeypatch: Any,
) -> None:
    """The api answers the value and the text; the text is the canonical bytes between the two delimiter lines
    that type it; the CLI's `--text` prints exactly that; an unknown card is `show.unknown`."""
    from typer.testing import CliRunner

    from isidium.store.client import cli as cli_mod
    from isidium.store.core.refusal import Refusal

    hz = fresh()
    st = hz.st
    g = graph(hz)
    api = Api(st)
    r = api.show(OWNER, {"target": "neighborhood", "id": g.subject})
    block = st.neighborhood_of(g.subject)
    assert r["context"] == block.as_dict()
    body = block.canonical().decode("utf-8")
    assert r["text"] == f"<<<isidium-context 1 card={g.subject} truncated=false\n{body}\n>>>isidium-context 1\n"
    try:
        api.show(OWNER, {"target": "neighborhood", "id": 99})
        raise AssertionError("an unknown card answered")
    except Refusal as e:
        assert e.rule == "show.unknown"

    class Transport:
        def call(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
            assert (name, args) == ("show", {"target": "neighborhood", "id": g.subject})
            return r

    monkeypatch.setattr(cli_mod, "_transport", lambda: (Transport(), None, None))
    res = CliRunner().invoke(cli_mod.app, ["show", "neighborhood", str(g.subject), "--text"])
    assert res.exit_code == 0 and res.output == r["text"] + "\n", res.output  # the terminal's own newline
    res = CliRunner().invoke(cli_mod.app, ["show", "neighborhood", str(g.subject)])
    assert res.exit_code == 0 and json.loads(res.output)["context"] == block.as_dict()


def test_a_subject_that_is_itself_a_draft_still_has_a_neighborhood() -> None:
    """A planner's preview: the subject is never a member and need not be settled."""
    hz = fresh()
    st = hz.st
    g = graph(hz)
    b = st.neighborhood_of(g.draft)
    assert ids(b.parents) == [g.story, g.epic] and ids(b.siblings) == [g.subject, g.held]
    assert g.draft not in ids(b.siblings)


def test_the_caps_come_from_the_effective_config() -> None:
    hz = fresh()
    caps = neighborhood.caps_of(hz.st.eff)
    assert caps == neighborhood.Caps(2, 16384), "config@4's defaults, read from the effective config, never supplied"
    assert neighborhood.caps_of({"payload": {"context": {"depth": 1, "max_bytes": 2048}}}) == neighborhood.Caps(1, 2048)
