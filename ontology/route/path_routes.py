"""PATH -> ROUTE orchestration — ONE pipeline for every Possible Path.

internal-docs §7 and §23.5. A Possible Path can be born from a strategy declared by the
domain, from a promoted Candidate Possibility (the mechanism pattern), or both — and for route,
readiness, and NextMove the three are IDENTICAL: this pipeline reads only `path_id`, `strategy_id`,
`title` (the payload label), `route_substrate`, `checks`, `feasibility`, `lifecycle`. It never reads
`provenance.candidate`, the origin, or `candidate_id`. There is no second route composer for candidates.

Order (strategy-first; an invalid relation fails deterministically, not "last one wins"):

    plan_compositions(paths, library)            path -> its substrate template (ROUTE-02/04)
      -> run_session_route(session, template)    lifecycle first, then compose (bridge; no LLM)
      -> overlay_execution(result, views)        execution_view from the event ledger (satisfaction stays)
      -> assert_route_keeps_strategy(path, lin)  a born route carries its path's strategy (ROUTE-01)
      -> route payload + NextMove gate           ADJUDICATED reading (one rule with readiness)
      -> select_next_move(raw)                   the v1 selector over non-STOP path routes

A path without a template yields no route (Possible Path != Route Template, PATH-07): that is a valid
state. This function WRITES a lineage row (append-only) when a new route is born — through the bridge,
not here."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from core.navigation.contracts import display_status
from core.navigation.evaluator import apply_lifecycle
from core.navigation.readiness import canonical_feasibility
from ontology.route.execution_view import overlay_execution
from ontology.route.lifecycle import derived_route_status
from ontology.route.next_move import select_next_move
from ontology.route.plan import assert_route_keeps_strategy, plan_compositions
from ontology.route.session_bridge import run_session_route

_NODE_KEYS = (
    "node_id",
    "resolves",
    "strength",
    "depends_on",
    "activity",
    "satisfaction",
    "executability",
    "execution_view",
)


def _node_payload(n: dict[str, Any], guidance_of: Callable[[dict], dict] | None) -> dict[str, Any]:
    """Route node payload: the core-field whitelist (legacy contract) + `guidance` ONLY when its
    carrier is injected (the single-gate rule from core.navigation.readiness). No callable = a payload
    exactly as before, so the legacy consumer contract and golden payloads stay unchanged."""
    d: dict[str, Any] = {k: n.get(k) for k in _NODE_KEYS}
    if guidance_of is not None:
        d["guidance"] = guidance_of(n)
    return d


def compose_path_routes(
    session: Any,
    paths: list[dict[str, Any]],
    library: list[dict[str, Any]],
    *,
    describe_strategy: Callable[[str], str],
    lifecycles: dict[str, dict] | None = None,
    views: Any = None,
    views_by_route: dict[str, dict] | None = None,
    node_guidance: Callable[[dict], dict] | None = None,
    read_only: bool = False,
) -> dict[str, Any]:
    """Possible Path (0..N) + the template library -> `{routes, not_born, next_move}`.

    `describe_strategy(strategy_id)` = the domain registry sentence for the route payload (presentation).
    `lifecycles` = the CURRENT lifecycle per `path_id` (a user may stop a path after diagnosis): NextMove
    never suggests an action on a STOP-status path. `views` = execution views from the user's event ledger.
    `views_by_route` = {route_id: {node_id: view}} — R1-remediation Probe B (17 Oct): a per-route
    overlay, execution markers never leak across contexts; when given it WINS over `views`.
    `node_guidance(node)` = an optional per-node `guidance` carrier (single-gate rule; see _node_payload).
    Every EXISTING route is returned (exists != surfaced, INV-R17) — surfacing is the UI's decision."""
    life = lifecycles or {}
    routes: list[dict[str, Any]] = []
    not_born: list[dict[str, Any]] = []
    raw: list[dict[str, Any]] = []
    # STRATEGY-FIRST: each path determines its own substrate template; an invalid strategy/template
    # relation fails deterministically (RouteCompositionError) — not overwritten by a template lookup.
    for path, tpl in plan_compositions(paths, library):
        r = run_session_route(session, tpl, read_only=read_only)
        if r.get("lineage") is not None:
            # R1-remediation Probe B: the execution overlay is filtered to THIS route —
            # node_id is inherited from the template, a full-user overlay could attach
            # another context's markers to this context's route. views (flat, legacy)
            # is used only when views_by_route is not given.
            views_for = None
            if views_by_route is not None:
                views_for = views_by_route.get(r["lineage"]["route_id"], {})
            elif views is not None:
                views_for = views
            r = overlay_execution(r, views_for)
        lin = r.get("lineage")
        if lin is None:
            not_born.append(
                {
                    "template_id": tpl["template_id"],
                    "strategy_id": path["strategy_id"],
                    "path_id": path["path_id"],
                    "outcome": r["outcome"],
                    "reason": r["reason"],
                }
            )
            continue
        assert_route_keeps_strategy(path, lin)  # ROUTE-01
        # The NextMove gate uses the ADJUDICATED reading (Task C — one rule with readiness): a
        # disputed condition (check vs ledger) contributes UNKNOWN, so a dispute on a hard check is
        # NOT STOP — a dispute is not a finished finding; never hide a route from NextMove over a dispute.
        if (
            display_status(
                canonical_feasibility(path, lin["revisions"][-1]["nodes"]),
                apply_lifecycle(path, life.get(path["path_id"]))["lifecycle"],
            )
            != "STOP"
        ):
            raw.append(r)
        rev = lin["revisions"][-1]
        routes.append(
            {
                "template_id": tpl["template_id"],
                "strategy_id": path["strategy_id"],
                "path_id": path["path_id"],
                "path_title": path["title"],
                "strategy": describe_strategy(path["strategy_id"]),
                "motion": lin["motion"],
                "outcome": r["outcome"],
                "route_id": lin["route_id"],
                "goal_anchor": lin["reconciliation_key"]["goal_anchor"],
                "applicability": lin["applicability"],
                "lineage_status": lin["lineage_status"],
                "derived_status": derived_route_status(lin),
                "revision_no": rev["revision_no"],
                "nodes": [_node_payload(n, node_guidance) for n in rev["nodes"]],
                "frontier": r["frontier"],
            }
        )
    return {"routes": routes, "not_born": not_born, "next_move": select_next_move(raw)}
