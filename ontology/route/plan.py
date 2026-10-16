"""ROUTE COMPOSITION PLAN — Possible Path (strategy) -> which template gets composed.

internal-docs §7. The ontology contract enforced here:

    Strategy 1 ──▶ N RouteTemplate        (one strategy may own many templates)
    RouteTemplate N ──▶ 1 Strategy        (one template → exactly ONE strategy: `template.strategy_id`)

The reason: route identity = reconciliation_key {goal_anchor, strategy_id, scope_anchor} (INV-R13/R14).
A template shared across strategies has no single route meaning; "last one wins" in a dict is
forbidden hidden semantics. The composition direction is STRATEGY-FIRST (path -> template), not
template -> path.

A contract violation = a deterministic `RouteCompositionError` (ValueError), never a route that silently
switches strategy (ROUTE-02) or disappears (ROUTE-04). Pure functions: no store reads, no writes at all."""

from __future__ import annotations

from typing import Any


class RouteCompositionError(ValueError):
    """An invalid strategy/template relation, or a produced route not carrying its source strategy."""


def plan_compositions(
    paths: list[dict[str, Any]], library: list[dict[str, Any]]
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """[(path, template)] for each path's substrate templates; sorted by `template_id` (deterministic).

    - a template referenced by a path MUST exist in the library;
    - `template.strategy_id` MUST equal `path.strategy_id` (ROUTE-02);
    - one template must never be the substrate of two different paths (ROUTE-03/04);
    - a path without a substrate yields nothing (a Possible Path requires no template, PATH-07)."""
    by_id: dict[str, dict[str, Any]] = {}
    for tpl in library:
        tid = tpl["template_id"]
        if tid in by_id:
            raise RouteCompositionError(f"pustaka template memuat template_id {tid!r} dua kali")
        by_id[tid] = tpl
    plan: list[tuple[dict[str, Any], dict[str, Any]]] = []
    owner: dict[str, str] = {}
    for path in paths:
        pid, sid = path["path_id"], path["strategy_id"]
        tids = (path.get("route_substrate") or {}).get("template_ids") or []
        # Task F (doc 14 §7): the same template twice in ONE path's substrate = two identical composition
        # entries -> two identical routes for one strategy (the readiness contract rejects it). Fail here,
        # deterministically — never leak through to the projection.
        if len(tids) != len(set(tids)):
            dupes = sorted({t for t in tids if tids.count(t) > 1})
            raise RouteCompositionError(
                f"path {pid!r}: template substrat duplikat {dupes} — setiap template tepat sekali "
                "dalam satu path (entri ganda = dua route identik)"
            )
        for tid in tids:
            tpl = by_id.get(tid)
            if tpl is None:
                raise RouteCompositionError(f"path {pid!r}: template {tid!r} tidak ada di pustaka")
            if tpl["strategy_id"] != sid:
                raise RouteCompositionError(
                    f"path {pid!r} (strategi {sid!r}) merujuk template {tid!r} milik strategi "
                    f"{tpl['strategy_id']!r} — route tidak boleh berganti strategi"
                )
            if tid in owner and owner[tid] != pid:
                raise RouteCompositionError(
                    f"template {tid!r} menjadi substrat dua path ({owner[tid]!r}, {pid!r})"
                )
            owner[tid] = pid
            plan.append((path, tpl))
    return sorted(plan, key=lambda pt: pt[1]["template_id"])


def assert_route_keeps_strategy(path: dict[str, Any], lineage: dict[str, Any]) -> None:
    """ROUTE-01: a born route carries its source strategy (reconciliation key), same as the path."""
    got = ((lineage or {}).get("reconciliation_key") or {}).get("strategy_id")
    if got != path["strategy_id"]:
        raise RouteCompositionError(
            f"route untuk path {path['path_id']!r} membawa strategi {got!r}, "
            f"seharusnya {path['strategy_id']!r}"
        )
