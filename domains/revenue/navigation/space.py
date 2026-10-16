"""Revenue possibility-space loader: ontology/possibility/revenue.json + strategy registry + route template.

One source per fact: motion from strategies.json (strategy registry), route substrate from the
templates whose strategy is `active`, knowledge provenance from the template provenance. The
possibility file only adds what neither has (when a strategy is born, feasibility checks, display text)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from core.navigation.contracts import CheckSpec, PossibilityPattern, PossibilitySpace, StrategySpec
from engine.knowledge import get_kb
from ontology.route.strategies import active_template_library, load_strategies

SPACE_PATH = Path(__file__).resolve().parents[3] / "ontology" / "possibility" / "revenue.json"


def load_space_document(path: Path = SPACE_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _pattern_sources(pattern: dict) -> tuple[dict, ...]:
    """The knowledge source of a pattern = the provenance of the KB intervention behind it (read from
    the KB, not retyped): a pattern has no source of its own, it leans on knowledge that already exists."""
    kb = get_kb()["interventions"]
    out: list[dict] = []
    for g in pattern.get("grounded_in") or []:
        pv = kb[g["intervention_id"]]["provenance"]
        row = {"source_id": pv["source_id"], "chapters": list(pv.get("chapters") or [])}
        if row not in out:
            out.append(row)
    return tuple(out)


@lru_cache(maxsize=1)
def revenue_space() -> PossibilitySpace:
    doc = load_space_document()
    registry = load_strategies()
    templates: dict[str, list[dict]] = {}
    for tpl in active_template_library():
        templates.setdefault(tpl["strategy_id"], []).append(tpl)
    strategies = []
    for s in doc["strategies"]:
        reg = registry.get(s["strategy_id"])
        if reg is None or reg.get("status") != "active":
            # a strategy not active in the registry does not join the possibility space
            # (e.g. a proof_only specimen)
            continue
        tpls = templates.get(s["strategy_id"], [])
        sources = []
        for tpl in tpls:
            for pv in tpl.get("provenance") or []:
                row = {"source_id": pv["source_id"], "chapters": list(pv.get("chapters") or [])}
                if row not in sources:
                    sources.append(row)
        strategies.append(
            StrategySpec(
                strategy_id=s["strategy_id"],
                title=s["title"],
                basis=s.get("basis", ""),
                motion=reg["motion"],
                emerges_when=s["emerges_when"],
                not_applicable_when=s.get("not_applicable_when"),
                checks=tuple(CheckSpec(**c) for c in s.get("checks", [])),
                route_template_ids=tuple(t["template_id"] for t in tpls),
                knowledge_sources=tuple(sources),
                presentation=s.get("presentation") or {},
            )
        )
    # Knowledge -> Mechanism -> Candidate Possibility: Revenue mechanisms are detected directly from evidence
    # (RevenueSignals), so a pattern only states mechanism -> direction; no strategy/path is written.
    patterns = tuple(
        PossibilityPattern(
            direction=pat["direction"],
            title=pat["title"],
            thesis=pat.get("thesis", ""),
            basis=pat.get("basis", ""),
            mechanism_ids=tuple(pat["mechanism_ids"]),
            context_when=pat.get("context_when"),
            not_applicable_when=pat.get("not_applicable_when"),
            knowledge_sources=_pattern_sources(pat),
            presentation=pat.get("presentation") or {},
        )
        for pat in doc.get("patterns", [])
    )
    return PossibilitySpace(
        space_id=doc["space_id"],
        strategies=tuple(strategies),
        goal_signal=doc.get("goal_signal"),
        patterns=patterns,
    )
