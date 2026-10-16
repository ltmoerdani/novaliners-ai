"""Deterministic backend graph EXAMPLE (V4 master prompt section 10.2; audit D-06).

This is the 7-8 path example that proves the TYPED graph contract can carry shared
conditions, a genuine split, intra-route dependencies, an admitted cross-route BRANCH
and an admitted MERGE, a STOP path, a locked Move and a completed Move with no outcome.

It is assembled ONLY from production functions:
  - ontology.route.projection.project_maps  (canonical presentation projection)
  - store.navigation_links.admission_problems / append_link  (typed-link admission)
  - app.experience_contract.build_graph  (typed graph + unsupported_edges)

PROVENANCE: source = "PROTOTYPE_FIXTURE". This is EXAMPLE data for renderer/parser
completeness. It is NEVER a source of live business facts, and it must never be used to
claim that a LIVE cross-route relation exists (the live path needs a ratified ADR and a
real declaration source).
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # mvp/ on the path when run as a script

from app import experience_contract as ec  # noqa: E402
from ontology.route.projection import project_maps  # noqa: E402
from store import navigation_links as nl  # noqa: E402

SOURCE = "PROTOTYPE_FIXTURE"
USER_ID = "u-fixture"
CONTEXT = "g-fixture"

GOAL: dict[str, Any] = {
    "goal_id": "g-fixture", "version": 2, "text": "Rp25M per month within 60 days",
    "metric": {"id": "revenue_monthly"}, "horizon": "60d",
}


def _n(nid, resolves, *, deps=(), sat="UNKNOWN", exe="UNKNOWN", view="NOT_STARTED"):
    return {"node_id": nid, "activity": nid, "resolves": list(resolves),
            "depends_on": list(deps), "satisfaction": {"status": sat},
            "executability": {"status": exe}, "execution_view": view}


def _r(rid, pid, nodes, *, frontier=(), status="OPEN", applicability="APPLIES"):
    return {"route_id": rid, "path_id": pid, "revision_no": 1, "lineage_status": status,
            "derived_status": status, "applicability": {"status": applicability},
            "goal_anchor": "state:user", "nodes": list(nodes), "frontier": list(frontier)}


def routes_payload() -> list[dict]:
    """8 Paths; 7 carry a route, p8 is the honest zero-route path."""
    return [
        _r("r1", "p1", [
            _n("n1", ["req-a"], exe="TRUE"),
            _n("n2", ["req-shared-ok"], deps=("n1",)),
            _n("n3", ["req-shared-ok2"], deps=("n2",)),
        ], frontier=[{"kind": "EXECUTE", "node": "n1"}]),
        _r("r2", "p2", [
            _n("n1", ["req-b"]),
            _n("n2", ["req-shared-ok"]),
            _n("n3", ["req-shared-ok2"], deps=("n2",)),
        ]),
        _r("r3", "p3", [
            _n("n1", ["req-split"]),
            _n("n2", ["req-c"], deps=("n1",)),
        ]),
        # Same canonical requirement id as r3, but a DISAGREEING state -> must split (N23).
        _r("r4", "p4", [_n("n1", ["req-split"], sat="PRESENT")]),
        # STOP path: its route exists but is stopped by evidence (status STOP, lifecycle OPEN).
        _r("r5", "p5", [_n("n1", ["req-locked"], exe="FALSE")]),
        # CLOSED lineage: a candidate link endpoint on this route must be rejected.
        _r("r6", "p6", [_n("n1", ["req-closed"])], status="CLOSED"),
        # Completed work whose outcome has NOT come in: the node reads as awaiting proof.
        _r("r7", "p7", [_n("n1", ["req-now"], exe="TRUE", view="EXECUTED")],
           frontier=[{"kind": "VERIFY", "node": "n1"}]),
    ]


def paths_ctx() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for i in range(1, 8):
        stopped = (i == 5)
        out[f"p{i}"] = {
            "title": f"Path {i}",
            "lifecycle": "OPEN",
            "status": "STOP" if stopped else "OPEN",
            "goal_relation": "LEADS_TO_GOAL",
            "goal_relation_note": "",
        }
    out["p8"] = {"title": "Path 8 (no route yet)", "lifecycle": "OPEN", "status": "OPEN",
                 "goal_relation": "LEADS_TO_GOAL", "goal_relation_note": ""}
    return out


def moves_payload() -> list[dict]:
    def mv(mid, life, **kw):
        base = {"move_id": mid, "lifecycle": life, "linked_goal_id": CONTEXT,
                "linked_goal_version": 2, "linked_path_id": kw.pop("path", "p1"),
                "history": [{"state": life, "event_id": "ce-fx-" + mid, "ts": 1}],
                "route_node_ref": None, "observation_claim_refs": [], "assessment": None}
        base.update(kw)
        return base

    return [
        mv("mv-branch-point", "EXECUTED",
           route_node_ref={"route_id": "r1", "node_id": "n1", "route_revision": 1}),
        mv("mv-merge-target", "PLANNED",
           route_node_ref={"route_id": "r1", "node_id": "n3", "route_revision": 1}),
        # Completed Move with NO outcome yet: node must read as awaiting proof, never done/validated.
        mv("mv-done-no-outcome", "EXECUTED", path="p7",
           route_node_ref={"route_id": "r7", "node_id": "n1", "route_revision": 1}),
        # Reported zero replies: observed, assessment INCONCLUSIVE (0 != null, and not validated).
        mv("mv-zero", "OBSERVED", observation_claim_refs=["cl-zero"],
           assessment={"verdict": "INCONCLUSIVE", "event_id": "ce-fx-zero",
                       "observed_claim_refs": ["cl-zero"]}),
        # Locked: sits on a node whose executability is FALSE.
        mv("mv-locked", "PLANNED", path="p5",
           route_node_ref={"route_id": "r5", "node_id": "n1", "route_revision": 1}),
    ]


def _link(kind, frm, to, decl):
    return {"kind": kind, "from": frm, "to": to, "declaration_ref": decl,
            "source_event_refs": ["ce-fx-decl-1"], "evidence_refs": ["ev-fx-1"],
            "context_id": CONTEXT}


def link_candidates() -> list[dict]:
    """Typed causal relations. Two upstream sources genuinely converge on mv-merge-target."""
    return [
        _link("BRANCH_FROM", {"move_id": "mv-branch-point"},
              {"route_id": "r2", "node_id": "n1", "route_revision": 1},
              "decl:branch:p2-from-mv-branch-point"),
        _link("MERGES_INTO", {"route_id": "r3", "node_id": "n2", "route_revision": 1},
              {"move_id": "mv-merge-target"}, "decl:merge:mv-merge-target-from-r3"),
        _link("MERGES_INTO", {"route_id": "r2", "node_id": "n3", "route_revision": 1},
              {"move_id": "mv-merge-target"}, "decl:merge:mv-merge-target-from-r2"),
    ]


def build_example(*, base_dir: Path | str | None = None) -> dict[str, Any]:
    """Assemble the example with production functions. Returns a JSON-safe dict."""
    routes = routes_payload()
    maps = project_maps(routes, paths_ctx(), goal=GOAL)
    moves = moves_payload()
    session = SimpleNamespace(id="s-fixture", user_id=USER_ID, goal=GOAL, moves=moves,
                              evidence=[], checkpoints=[], experience_snapshots=[])

    workdir = Path(base_dir) if base_dir else Path(tempfile.mkdtemp(prefix="nv-graph-fx-"))
    existing: list[dict] = []
    admitted: list[dict] = []
    rejected: list[dict] = []
    for cand in link_candidates():
        problems = nl.admission_problems(cand, routes=routes, existing=existing, context_id=CONTEXT)
        if problems:
            rejected.append({"link": cand, "problems": problems})
            continue
        row = nl.append_link(USER_ID, cand, base_dir=workdir)
        existing.append(row)
        admitted.append(row)

    links = nl.latest_links(USER_ID, base_dir=workdir, context_id=CONTEXT)
    graph = ec.build_graph(session, maps, links=links)
    revision = ec.reality_revision(session, routes=routes, graph=graph)
    return {
        "source": SOURCE,
        "goal": GOAL,
        "base_dir": str(workdir),
        "routes": routes,
        "maps_projection": maps,
        "links": links,
        "graph": graph,
        "revision": revision,
        "admitted_links": len(admitted),
        "rejected_links": rejected,
        "notes": [
            "EXAMPLE only: provenance is PROTOTYPE_FIXTURE, never a LIVE claim.",
            "7 of 8 paths carry a route; p8 has no route and no node is invented for it.",
            "req-shared-ok / req-shared-ok2 hold on two routes with the same state -> one shared hub.",
            "req-split holds on two routes with disagreeing states -> INCOMPATIBLE_SCOPE, split.",
            "BRANCH_FROM and two MERGES_INTO come from admitted navigation_links rows with declaration_ref.",
            "A STOP path and a CLOSED lineage are present; a closed route rejects new links.",
        ],
    }


def main() -> int:
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    ex = build_example()
    g = ex["graph"]
    by_kind: dict[str, int] = {}
    for e in g["edges"]:
        by_kind[e["kind"]] = by_kind.get(e["kind"], 0) + 1
    summary = {
        "source": ex["source"],
        "paths": len(ex["maps_projection"]["paths"]),
        "nodes": len(g["nodes"]),
        "edges_by_kind": by_kind,
        "unsupported_edges": g["unsupported_edges"],
        "admitted_links": ex["admitted_links"],
        "projection_revision": ex["revision"]["projection_revision"],
        "graph_revision": ex["revision"]["graph_revision"],
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if out_path:
        out_path.write_text(json.dumps(ex, indent=2, ensure_ascii=False), encoding="utf-8")
        print("wrote " + str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
