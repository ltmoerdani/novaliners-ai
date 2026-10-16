"""GOLDEN Candidate-born scenarios (internal-docs §24.8): ONE source for the backend test
(`test_candidate_golden.py`) and the UI fixture (`make_ui_fixtures.py`), so the visually inspected screen is
the output of the same production chain the test proves — not a handwritten copy.

    evidence ledger ─► tier-1 rules ─► mechanisms ─► candidates ─► evaluation ─► Possible Path ─►
    REAL route composer ─► readiness (canonical state = adjudication ledger) ─► NextMove

Synthetic "growth" domain (no StrategySpec, no Revenue). The only simulated part: adding the motion
label + domain strategies to the REGISTRY (the `strategies.json` data) — the documented path for a new
domain (doc 14 §7.2). All side effects (temp store, registry, ids) are restored when the context ends."""

from __future__ import annotations

import contextlib
import dataclasses
import json
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator

import engine.requirements as req_mod
import ontology.route.compose as compose
import ontology.route.strategies as strategies
import store.adjudication_ledger as ledger
import store.route_lineages as rl
from core.navigation.contracts import PossibilitySpace
from core.navigation.evaluator import build_path_set
from core.navigation.readiness import build_projection
from core.schema.evidence import EvidenceItem
from evals.navigation_fixtures import growth_evidence, growth_reader, growth_space, growth_supports
from ontology.route.path_routes import compose_path_routes

# Synthetic route template: real grammar, validated by the production route
# validator (`test_candidate_golden.py`).
TEMPLATE: dict[str, Any] = {
    "template_id": "simplify_onboarding_v1",
    "strategy_id": "simplify_onboarding",
    "goal_anchor": "retention.activation",
    "applies_when": {"applies": [{"text_contains_any": ["onboarding membingungkan"]}], "not_applicable": []},
    "requires": ["delivery.onboarding", "retention.aha_moment_defined", "retention.activation"],
    "node_candidates": [
        {
            "candidate_key": "onboarding",
            "resolves": ["delivery.onboarding"],
            "strength": "hard",
            "depends_on": [],
            "activity": "Cut the first session down to the steps that lead to value",
        },
        {
            "candidate_key": "aha",
            "resolves": ["retention.aha_moment_defined"],
            "strength": "hard",
            "depends_on": [],
            "activity": "Name the moment a user first gets value",
        },
        {
            "candidate_key": "activation",
            "resolves": ["retention.activation"],
            "strength": "hard",
            "depends_on": ["onboarding", "aha"],
            "activity": "Measure how many new users reach the aha moment",
        },
    ],
    "provenance": [
        {
            "source_id": "hg",
            "chapters": ["ch03"],
            "knowledge_type": "source_claim",
            "confidence": "normative_only",
        }
    ],
}

# Second template for path candidates born from TWO mechanisms (conflict test + real route, golden §H).
TEMPLATE_ACTIVATION: dict[str, Any] = {
    "template_id": "improve_activation_v1",
    "strategy_id": "improve_activation_before_acquisition",
    "goal_anchor": "retention.activation",
    "applies_when": {"applies": [{"text_contains_any": ["sign-up banyak"]}], "not_applicable": []},
    "requires": ["retention.aha_moment_defined", "retention.activation"],
    "node_candidates": [
        {
            "candidate_key": "aha",
            "resolves": ["retention.aha_moment_defined"],
            "strength": "hard",
            "depends_on": [],
            "activity": "Name the moment a user first gets value",
        },
        {
            "candidate_key": "activation",
            "resolves": ["retention.activation"],
            "strength": "hard",
            "depends_on": ["aha"],
            "activity": "Measure how many new users reach the aha moment",
        },
    ],
    "provenance": TEMPLATE["provenance"],
}

STRATEGY_DESCRIPTION = "Cut the first session down to the steps that lead to value."

# State-signal evidence anchors: REAL ledger ids (not invented ids).
GOAL = EvidenceItem(
    id="ev-g-0", signal="target: 1000 pengguna aktif per bulan", level="behavioral", topic="GOAL"
)
REFS = {"state:revenue_goal": ("ev-g-0",), "state:acquisition_exists": ("ev-g-1",)}
SPACE = growth_space(with_template=True)  # no StrategySpec; simplify_onboarding is templated
# Variant: ONLY improve_activation_before_acquisition (TWO causal mechanisms) is templated. A single route,
# so NextMove stays deterministic (choosing between routes would break ties via a UUID route_id).
SPACE_ACTIVATION_ROUTE = dataclasses.replace(
    SPACE,
    patterns=(
        dataclasses.replace(SPACE.patterns[0], route_template_ids=("improve_activation_v1",)),
        SPACE.patterns[1],
        dataclasses.replace(SPACE.patterns[2], route_template_ids=()),
    ),
)
ONBOARDING_PHRASE = "onboarding dipersingkat jadi tiga langkah"


def ledger_items(**kw: Any) -> list[EvidenceItem]:
    """Golden evidence ledger: the goal + growth evidence (default: "onboarding membingungkan" proven)."""
    return [GOAL, *growth_evidence(**({"onboarding": True} | kw))]


def describe(rid: str):
    return req_mod.describe(rid, "en")


def world(items: list[EvidenceItem], space: PossibilitySpace = SPACE) -> dict:
    """One world state: ledger -> REAL rules -> mechanisms -> candidates -> evaluation -> PathSet."""
    return build_path_set(space, growth_reader(growth_supports(items), refs=REFS))


def session(items: list[EvidenceItem], user: str) -> SimpleNamespace:
    """Duck-typed session for `run_session_route` (only `.user_id` and `.evidence` are read)."""
    return SimpleNamespace(user_id=user, evidence=items)


def compose_routes(
    ps: dict, items: list[EvidenceItem], user: str, library: list[dict] | None = None
) -> dict:
    """Path -> PRODUCTION route pipeline (`compose_path_routes`); library = the golden templates."""
    return compose_path_routes(
        session(items, user),
        ps["paths"],
        library or [TEMPLATE],
        describe_strategy=lambda sid: strategies.load_strategies()[sid]["description"],
    )


def projection(ps: dict, routes: dict) -> dict:
    return build_projection(ps, {"routes": routes["routes"]}, describe, lang="en")


def _rule(phrase: str) -> dict:
    never = {"any_of": [{"text_contains_any": ["__never__"]}]}
    return {
        "mode": "PARTIAL",
        "sufficient": {"any_of": [{"text_contains_any": [phrase]}]},
        "partial": never,
        "no_decisive": never,
        "contradicting": never,
    }


def adjudicate(user: str, rid: str, phrase: str, eid: str) -> dict:
    """CANONICAL state via the ledger's public door (`adjudicate_and_persist`), not by writing status."""
    ev = EvidenceItem(
        id=eid, signal=phrase, source_quote=phrase, level="self_reported", topic="REVENUE_STATE"
    )
    return ledger.adjudicate_and_persist(
        user,
        rid,
        _rule(phrase),
        [ev],
        [
            {
                "requirement_id": rid,
                "evidence_refs": [eid],
                "verification_method": "deterministic_predicate",
                "verified": True,
                "verified_at": 1,
            }
        ],
        evaluation_time=100,
    )


@contextlib.contextmanager
def temp_stores(root: Path) -> Iterator[None]:
    """Redirect the lineage store + adjudication ledger to `root` (never touches user data); restored."""
    old = (rl._BASE, ledger._LEDGER_ROOT)
    rl._BASE, ledger._LEDGER_ROOT = root / "lineages", root / "ledger"
    try:
        yield
    finally:
        rl._BASE, ledger._LEDGER_ROOT = old


@contextlib.contextmanager
def growth_registry(root: Path) -> Iterator[None]:
    """Register the "growth" domain's motion label + strategies in the registry (data), as if writing to
    `strategies.json`; the ORIGINAL registry loader reads it. Restored at the end."""
    reg = {
        "motion_vocabulary": [*strategies.load_motion_vocabulary(), "ACTIVATION"],
        "strategies": [
            {
                "strategy_id": sid,
                "motion": "ACTIVATION",
                "status": "active",
                "description": STRATEGY_DESCRIPTION,
            }
            for sid in ("simplify_onboarding", "improve_activation_before_acquisition")
        ],
    }
    path = root / "strategies_growth.json"
    path.write_text(json.dumps(reg), encoding="utf-8")
    orig_load, orig_motions = strategies.load_strategies, compose.MOTIONS
    strategies.load_strategies = lambda p=None: orig_load(path)
    compose.MOTIONS = set(strategies.load_motion_vocabulary(path))
    try:
        yield
    finally:
        strategies.load_strategies, compose.MOTIONS = orig_load, orig_motions


@contextlib.contextmanager
def deterministic_uuids() -> Iterator[None]:
    """Deterministic route/node ids (birth order) so UI fixtures from the real composer
    are stable across runs."""
    orig = uuid.uuid4
    counter = iter(range(1, 10_000))
    uuid.uuid4 = lambda: uuid.UUID(int=next(counter))
    try:
        yield
    finally:
        uuid.uuid4 = orig


def ui_bundle(user: str = "u-ui-golden") -> dict:
    """UI fixture from the real chain: paths + readiness projection (canonical state from the ledger) + route
    payload (`POST /routes`) with NextMove — exactly what the server would serve, with deterministic ids."""
    import tempfile

    from domains.revenue.projection.readiness import build_readiness_projection
    from evals.navigation_fixtures import diagnosis_with

    with tempfile.TemporaryDirectory(prefix="ui_golden_") as td:
        root = Path(td)
        with temp_stores(root), growth_registry(root), deterministic_uuids():
            items = ledger_items()
            ps = world(items)
            adjudicate(user, "delivery.onboarding", ONBOARDING_PHRASE, "ev-ui-1")
            routes = compose_routes(ps, items, user)
            payload = {"session_id": "s-ui-golden", "user_id": user, **routes}
            proj = build_readiness_projection(diagnosis_with(ps), payload, None)
    return {"possible_paths": ps, "projection": proj, "routes": payload}
