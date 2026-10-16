"""`execution_view` overlay from the route execution ledger (int 08 §3.4).

execution_view = a VIEW over the ledger, not state stored in the revision.
The composer writes NOT_STARTED; on the READ path, this overlay replaces it with the
last event per node and then recomputes the frontier (EXECUTE -> VERIFY
for a node already done). The stored lineage is not touched.

The overlay does NOT change satisfaction/executability: an "already done" report
is not evidence (INV-R8) — that node's dependents do not open because of it.
"""
from __future__ import annotations

import copy
from typing import Any

from ontology.route.compose import frontier_for


def overlay_execution(result: dict[str, Any],
                      views: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """`result` = output of run_session_route ({lineage, frontier, ...}). Return
    a copy with execution_view + frontier recomputed. A result without a
    lineage (not born) is returned as is."""
    lin = result.get("lineage")
    if not lin or not views:
        return result
    out = copy.deepcopy(result)
    lin = out["lineage"]
    nodes = lin["revisions"][-1]["nodes"]
    touched = False
    for n in nodes:
        v = views.get(n["node_id"])
        if v and v["view"] != n.get("execution_view"):
            n["execution_view"] = v["view"]
            touched = True
    if touched:
        out["frontier"] = frontier_for(lin["route_id"], lin["applicability"]["status"], nodes)
    return out
