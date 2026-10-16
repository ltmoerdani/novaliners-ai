"""Guard for the 7-8 path backend graph EXAMPLE (V4 section 10.2; audit D-06).
Run from mvp/:
    .venv/bin/python evals/test_experience_graph_fixture.py
Deterministic, no network, no LLM. Asserts the typed contract and the negative guards;
it does NOT claim a LIVE cross-route relation (that needs a ratified ADR).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import experience_graph_example as fx  # noqa: E402

from app import experience_contract as ec  # noqa: E402
from store import navigation_links as nl  # noqa: E402

FAILED: list[str] = []


def check(cond: bool, label: str) -> None:
    print(("PASS " if cond else "FAIL ") + label)
    if not cond:
        FAILED.append(label)


ex = fx.build_example()
g = ex["graph"]
maps = ex["maps_projection"]
nodes = {n["graph_id"]: n for n in g["nodes"]}
edges = g["edges"]
ekinds = [e["kind"] for e in edges]
by_kind = {k: ekinds.count(k) for k in set(ekinds)}

# 1-3: 8 paths, 7 routes, honest zero-route path
check(len(maps["paths"]) == 8, "8 paths present")
with_route = [p for p in maps["paths"] if p.get("route")]
check(len(with_route) == 7, "7 paths carry a route")
p8 = next(p for p in maps["paths"] if p["path_id"] == "p8")
check(p8.get("route") is None and (p8.get("route_unavailable") or {}).get("reason") == "no_route_context",
      "p8 has no route and no invented node")

# 4-5: shared condition hub vs split
check("reqshared:req-shared-ok" in nodes and "reqshared:req-shared-ok2" in nodes,
      "compatible shared requirements -> hub nodes")
check(by_kind.get("SHARED_REQUIREMENT_MEMBERSHIP") == 4, "4 shared-membership edges")
check("reqshared:req-split" not in nodes, "N23: disagreeing req-split is NOT merged")
check(any(u["id"] == "reqshared:req-split" and "INCOMPATIBLE_SCOPE" in u["reason"]
          for u in g["unsupported_edges"]), "N23: split is surfaced in unsupported_edges")

# 6: intra-route dependency only
check(by_kind.get("INTRA_ROUTE_DEPENDENCY") == 4, "4 intra-route dependency edges")

# 7-9: admitted causal links
branch = [e for e in edges if e["kind"] == "BRANCH_FROM"]
merges = [e for e in edges if e["kind"] == "MERGES_INTO"]
check(len(branch) == 1 and branch[0]["from_id"] == "move:mv-branch-point"
      and branch[0]["from_id"] and branch[0]["declaration_ref"].startswith("decl:branch:"),
      "admitted BRANCH_FROM with declaration_ref")
check(len(merges) == 2 and all(e["to_id"] == "move:mv-merge-target" for e in merges),
      "two upstream MERGES_INTO converging on one Move")
check(ex["admitted_links"] == 3 and not ex["rejected_links"], "3 typed links admitted, 0 rejected")

# 10: STOP path terminates, never touches the goal
p5_node = next(n for n in nodes.values() if n["kind"] == "PATH" and n["refs"].get("path_id") == "p5")
check(p5_node["status"] == "STOP", "STOP path carries STOP status")
goal_nodes = [n for n in nodes.values() if n["kind"] == "GOAL"]
check(len(goal_nodes) == 1, "one separate Goal landmark")
check(not any(e["to_id"] in {n["graph_id"] for n in goal_nodes} for e in edges),
      "no route/terminal edge into the Goal landmark (K2: reaching a route end is not the goal)")

# 11-12: completed-without-outcome and locked
r7n1 = nodes.get("req:r7:n1")
check(r7n1 is not None and r7n1["status"] == "Awaiting proof",
      "executed work with no outcome reads 'Awaiting proof' (not done)")
mv_done = nodes.get("move:mv-done-no-outcome")
check(mv_done is not None and mv_done["status"] == "EXECUTED" and not mv_done["history_refs"][0] == "",
      "completed Move keeps EXECUTED lifecycle (outcome still missing)")
r5n1 = nodes.get("req:r5:n1")
check(r5n1 is not None and r5n1["status"] == "Locked", "locked condition reads Locked")
check(nodes.get("move:mv-locked", {}).get("status") == "PLANNED", "locked Move stays PLANNED")

# 13: Move binding correctness (stale ref surfaced, not guessed)
stale_probe = ec.build_graph(
    type("S", (), {"id": "s", "user_id": fx.USER_ID, "goal": fx.GOAL, "evidence": [],
                   "checkpoints": [], "experience_snapshots": [],
                   "moves": [{"move_id": "mv-stale", "lifecycle": "PLANNED",
                              "route_node_ref": {"route_id": "r1", "node_id": "n1", "route_revision": 9},
                              "history": [], "linked_goal_id": fx.CONTEXT}]})(),
    maps)
check(any(u["reason"] == "STALE_ROUTE_NODE_REF" for u in stale_probe["unsupported_edges"]),
      "stale route_node_ref -> unsupported, no invented edge")

# 14-19: negative admission guards (pure, production admission)
routes = ex["routes"]
existing = ex["links"]
bad = {
    "orphan": fx._link("BRANCH_FROM", {"move_id": "mv-branch-point"},
                       {"route_id": "r2", "node_id": "n9", "route_revision": 1}, "decl:bad:orphan"),
    "stale": fx._link("BRANCH_FROM", {"move_id": "mv-branch-point"},
                      {"route_id": "r2", "node_id": "n1", "route_revision": 7}, "decl:bad:stale"),
    "closed": fx._link("BRANCH_FROM", {"move_id": "mv-branch-point"},
                       {"route_id": "r6", "node_id": "n1", "route_revision": 1}, "decl:bad:closed"),
    "selfloop": fx._link("MERGES_INTO", {"move_id": "mv-branch-point"},
                         {"move_id": "mv-branch-point"}, "decl:bad:selfloop"),
    "cycle": fx._link("MERGES_INTO", {"route_id": "r2", "node_id": "n1", "route_revision": 1},
                      {"move_id": "mv-branch-point"}, "decl:bad:cycle"),
}
bad["scope"] = dict(bad["orphan"], declaration_ref="decl:bad:scope", context_id="other-goal",
                    to={"route_id": "r2", "node_id": "n1", "route_revision": 1})
for name, cand in bad.items():
    try:
        probs = nl.admission_problems(cand, routes=routes, existing=existing, context_id=fx.CONTEXT)
    except Exception as exc:  # noqa: BLE001
        probs = ["raised:" + type(exc).__name__]
    check(bool(probs), "negative admission rejects: " + name)
bad_prov = {"kind": "BRANCH_FROM", "from": {"move_id": "mv-branch-point"},
            "to": {"route_id": "r2", "node_id": "n1", "route_revision": 1},
            "declaration_ref": "decl:with-decl", "source_event_refs": [], "evidence_refs": [],
            "context_id": fx.CONTEXT}
try:
    nl.append_link(fx.USER_ID, bad_prov, base_dir=ex["base_dir"])
    prov_ok = False
except nl.NavigationLinkError:
    prov_ok = True
check(prov_ok, "append_link raises on empty provenance")

# 20: determinism independent of list permutation
rev_a = ec.graph_revision(ec.build_graph(
    type("S", (), {"id": "s", "user_id": fx.USER_ID, "goal": fx.GOAL, "evidence": [],
                   "checkpoints": [], "experience_snapshots": [],
                   "moves": ex.get("_moves") or fx.moves_payload()})(),
    maps, links=ex["links"]))
rev_b = ec.graph_revision(ec.build_graph(
    type("S", (), {"id": "s", "user_id": fx.USER_ID, "goal": fx.GOAL, "evidence": [],
                   "checkpoints": [], "experience_snapshots": [],
                   "moves": list(reversed(fx.moves_payload()))})(),
    {"paths": list(reversed(maps["paths"])), "goal_landmark": maps["goal_landmark"]},
    links=list(reversed(ex["links"]))))
check(rev_a == rev_b, "graph_revision stable across input permutation")

# 21: provenance label is explicit
check(ex["source"] == "PROTOTYPE_FIXTURE", "example provenance labelled PROTOTYPE_FIXTURE")

n_total = 28
print()
if FAILED:
    print(f"{n_total - len(FAILED)}/{n_total} PASS - experience graph fixture ({len(FAILED)} FAIL)")
    for f in FAILED:
        print("  - " + f)
    sys.exit(1)
print(f"{n_total}/{n_total} PASS - experience graph fixture")
