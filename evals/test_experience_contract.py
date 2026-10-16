"""Focused guard for the V4 Experience read model (D-04/D-05/D-06/N23/N24).

Deterministic, no network, no LLM. Runs from mvp/:
    .venv/bin/python evals/test_experience_contract.py
"""
from __future__ import annotations

import copy
import sys
import types

sys.path.insert(0, ".")

from app import experience_contract as ec  # noqa: E402
from app.binding import state_version  # noqa: E402

FAILED: list[str] = []


def check(cond: bool, label: str) -> None:
    print(("PASS " if cond else "FAIL ") + label)
    if not cond:
        FAILED.append(label)


def mk_session(**kw):
    base = dict(id="s1", user_id="", moves=[], evidence=[], goal=None,
                checkpoints=[], experience_snapshots=[], state_graph={"nodes": {}, "edges": {}})
    base.update(kw)
    return types.SimpleNamespace(**base)


def mk_node(nid, resolves, deps=(), word="Open", rev=1, rid="rt-1", path=None):
    return {"node_id": nid, "resolves": list(resolves), "depends_on": list(deps),
            "presentation": {"word": word}, "satisfaction": {"status": "UNKNOWN"},
            "executability": {"status": "UNKNOWN"}, "execution": {"view": "NOT_STARTED"},
            "ref": {"path_id": path, "route_id": rid, "route_revision": rev}}


def mk_proj(paths):
    return {"paths": paths, "goal_landmark": {"goal_id": "g1", "version": 1}}


def mk_path(path_id, rid, nodes, rev=1, status="OPEN"):
    return {"path_id": path_id, "status_display": status, "status": status,
            "route": {"route_id": rid, "revision_no": rev, "lineage_status": "OPEN",
                      "applicability": {"status": "APPLIES"}, "nodes": nodes,
                      "frontier": [], "edges": [], "terminals": []}}


def mk_move(mid, life="PLANNED", ref=None, hist=None):
    return {"move_id": mid, "lifecycle": life, "linked_goal_id": "g1", "linked_goal_version": 1,
            "linked_path_id": "p1", "history": hist or [{"state": life, "event_id": "ce-x", "ts": 1}],
            "route_node_ref": ref, "observation_claim_refs": [], "assessment": None}


# 1 - deterministic composite revision
s = mk_session(goal={"goal_id": "g1", "version": 1})
r1 = ec.reality_revision(s, routes=[], graph={"nodes": [], "edges": []})
r2 = ec.reality_revision(s, routes=[], graph={"nodes": [], "edges": []})
check(r1["projection_revision"] == r2["projection_revision"], "projection_revision deterministik")
check(r1["projection_revision"].startswith("pr-"), "projection_revision ber-prefix pr-")

# 2 - N24: execution changes execution/projection revision while claims state_version does not
s0 = mk_session(goal={"goal_id": "g1", "version": 1})
s1 = mk_session(goal={"goal_id": "g1", "version": 1},
                moves=[mk_move("mv-1", "EXECUTED", hist=[{"state": "PLANNED", "event_id": "e1", "ts": 1},
                                                         {"state": "EXECUTED", "event_id": "e2", "ts": 2}])])
check(state_version(s0) == state_version(s1), "state_version klaim TIDAK berubah oleh eksekusi (asumsi N24)")
check(ec.execution_revision(s0) != ec.execution_revision(s1),
      "execution_revision BERUBAH oleh eksekusi (N24)")
pr0 = ec.reality_revision(s0, routes=[], graph={"nodes": [], "edges": []})
pr1 = ec.reality_revision(s1, routes=[], graph={"nodes": [], "edges": []})
check(pr0["projection_revision"] != pr1["projection_revision"], "projection_revision BERUBAH oleh eksekusi")

# 2b - legacy action report changes execution_revision (no claim changes)
sA = mk_session(goal={"goal_id": "g1", "version": 1},
                diagnosis=types.SimpleNamespace(day_by_day=[types.SimpleNamespace(
                    status="DONE", outcome=None, done_at=1, reported_at=None)]))
sB = mk_session(goal={"goal_id": "g1", "version": 1},
                diagnosis=types.SimpleNamespace(day_by_day=[types.SimpleNamespace(
                    status="DONE", outcome="moved", done_at=1, reported_at=2)]))
check(ec.execution_revision(sA) != ec.execution_revision(sB),
      "laporan aksi legacy -> execution_revision berubah (D-05)")

# 3 - shared requirement compatible -> single shared hub + membership edges
n_a = mk_node("n1", ["req-shared"], path="p1")
n_b = mk_node("n2", ["req-shared"], path="p2", rid="rt-2", word="Open")
proj_shared = mk_proj([mk_path("p1", "rt-1", [n_a]), mk_path("p2", "rt-2", [n_b])])
g = ec.build_graph(s, proj_shared)
ids = {n["graph_id"] for n in g["nodes"]}
shared_edges = [e for e in g["edges"] if e["kind"] == "SHARED_REQUIREMENT_MEMBERSHIP"]
check("reqshared:req-shared" in ids, "requirement id sama & kompatibel -> hub bersama")
check(len(shared_edges) == 2, "dua edge keanggotaan shared")
check(not [u for u in g["unsupported_edges"] if "req-shared" in u["id"]], "kompatibel: tanpa unsupported")

# 4 - N23: same requirement id, disagreeing state -> split, never merged
n_b2 = mk_node("n2", ["req-shared"], path="p2", rid="rt-2", word="Now")
proj_split = mk_proj([mk_path("p1", "rt-1", [n_a]), mk_path("p2", "rt-2", [n_b2])])
g2 = ec.build_graph(s, proj_split)
check("reqshared:req-shared" not in {n["graph_id"] for n in g2["nodes"]},
      "N23: state berbeda -> TIDAK digabung jadi hub")
check(any("INCOMPATIBLE_SCOPE" in u["reason"] for u in g2["unsupported_edges"]),
      "N23: ketidakcocokan dilaporkan, bukan dipilih diam-diam")

# 5 - intra-route dependency edges + missing endpoint surfaced
n_dep = mk_node("n3", ["req-c"], deps=("n1",), path="p1")
n_orphan = mk_node("n4", ["req-d"], deps=("ghost",), path="p1")
proj_dep = mk_proj([mk_path("p1", "rt-1", [n_a, n_dep, n_orphan])])
g3 = ec.build_graph(s, proj_dep)
intra = [e for e in g3["edges"] if e["kind"] == "INTRA_ROUTE_DEPENDENCY"]
check(any(e["to_id"] == "req:rt-1:n3" for e in intra), "edge dependensi intra-route ada")
check(any(u["reason"] == "DEPENDENCY_ENDPOINT_MISSING" for u in g3["unsupported_edges"]),
      "dependensi menggantung -> unsupported, tidak digambar")

# 6 - Move route_node_ref binding: match -> edge, stale rev -> unsupported (N19/N28)
mv_ok = mk_move("mv-ok", "EXECUTED", ref={"route_id": "rt-1", "node_id": "n1", "route_revision": 1})
g4 = ec.build_graph(mk_session(moves=[mv_ok]), proj_dep)
check(any(e["kind"] == "MOVE_OF_NODE" and e["from_id"] == "move:mv-ok" for e in g4["edges"]),
      "route_node_ref cocok -> edge MOVE_OF_NODE")
mv_stale = mk_move("mv-stale", "EXECUTED", ref={"route_id": "rt-1", "node_id": "n1", "route_revision": 9})
g5 = ec.build_graph(mk_session(moves=[mv_stale]), proj_dep)
check(any(u["reason"] == "STALE_ROUTE_NODE_REF" for u in g5["unsupported_edges"]),
      "route_node_ref revisi basi -> unsupported")

# 7 - determinism independent of input permutation
proj_perm = mk_proj([mk_path("p2", "rt-2", [n_b]), mk_path("p1", "rt-1", [n_a])])
gb = ec.build_graph(s, proj_shared)
gc = ec.build_graph(s, proj_perm)
check(ec.graph_revision(gb) == ec.graph_revision(gc), "graph_revision stabil atas permutasi input")

# 8 - change_set
cur_snap = ec.snapshot_of(ec.reality_revision(s, graph=gb), gb)
cs_same = ec.change_set(cur_snap, cur_snap)
check(cs_same["no_material_change"] is True, "change_set: identik -> no_material_change")
gb_plus = copy.deepcopy(gb)
gb_plus["nodes"].append({"graph_id": "move:x", "kind": "MOVE", "status": "PLANNED", "refs": {}})
cur2 = ec.snapshot_of(ec.reality_revision(s, graph=gb_plus), gb_plus)
cs_add = ec.change_set(cur_snap, cur2)
check("move:x" in cs_add["added"], "change_set: node baru -> ADDED")

# 9 - causal links: admitted BROK from link row; unknown kind surfaced
link = {"link_id": "nl-1", "kind": "BRANCH_FROM", "status": "ACCEPTED",
        "from": {"route_id": "rt-1", "node_id": "n1"}, "to": {"route_id": "rt-2", "node_id": "n2"},
        "declaration_ref": "decl:1", "source_event_refs": ["ce-1"], "evidence_refs": []}
g6 = ec.build_graph(s, proj_shared, links=[link])
check(any(e["kind"] == "BRANCH_FROM" and e["edge_id"] == "nl-1" for e in g6["edges"]),
      "link row ADMITTED -> edge kausal BRANCH_FROM")
g7 = ec.build_graph(s, proj_shared, links=[{**link, "kind": "SHARED_LABEL"}])
check(any("UNKNOWN_LINK_KIND" in u["reason"] for u in g7["unsupported_edges"]),
      "kind link tak dikenal -> unsupported, bukan edge")
ghost = {**link, "link_id": "nl-ghost", "from": {"move_id": "mv-does-not-exist"},
         "to": {"route_id": "rt-1", "node_id": "n1"}}
g8 = ec.build_graph(s, proj_shared, links=[ghost])
check(any("LINK_ENDPOINT_NOT_IN_GRAPH" in u["reason"] for u in g8["unsupported_edges"]),
      "N20: endpoint link di luar graph -> unsupported, bukan edge hantu")
check(not any(e["edge_id"] == "nl-ghost" for e in g8["edges"]), "N20: edge hantu TIDAK digambar")

# 10 - build_experience shape + integrity
exp = ec.build_experience(s, routes=[], maps_projection=proj_shared, links=[link],
                          timeline={"events": [{"event_id": "ce-1"}]}, state={"goal_text": "x"},
                          degraded_sources=["route_compose_failed"])
check(exp["source"] == "LIVE", "build_experience source LIVE")
check(exp["revision"]["projection_revision"], "build_experience membawa projection_revision")
check("change_set" in exp["graph"], "graph membawa change_set")
check(exp["integrity"]["compatible"] is False
      and "route_compose_failed" in exp["integrity"]["degraded_sources"],
      "integrity jujur saat sumber degradasi")
check(exp["journey_events"] == [{"event_id": "ce-1"}], "journey_events diteruskan")

n_total = 26
print()
if FAILED:
    print(f"{n_total - len(FAILED)}/{n_total} PASS - experience contract ({len(FAILED)} FAIL)")
    for f in FAILED:
        print("  - " + f)
    sys.exit(1)
print(f"{n_total}/{n_total} PASS - experience contract")
