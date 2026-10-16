"""UI fixtures from the REAL ENGINE (not handwritten JSON): path/readiness states unreachable via the
mock provider — zero paths, one path, many paths, UNKNOWN/PARTIAL/PRESENT items, a new requirement
outside the presentation pack. Used by e2e/paths.spec.mjs (UI states) and guarded by
evals/test_ui_fixtures.py (fixtures must equal the engine's CURRENT output — not a stale copy).

Run: .venv/bin/python evals/make_ui_fixtures.py   (rewrites e2e/fixtures/*.json)
"""

from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, ".")

import engine.requirements as req_mod  # noqa: E402
from core.navigation.compat import assess_path_set  # noqa: E402
from core.navigation.contracts import CheckSpec, PossibilitySpace, Signal, StrategySpec  # noqa: E402
from core.navigation.evaluator import build_path_set  # noqa: E402
from domains.revenue.navigation.paths import build_possible_paths  # noqa: E402
from domains.revenue.projection.readiness import build_readiness_projection  # noqa: E402
from domains.revenue.schema.state import RevenueState  # noqa: E402
from evals.golden_fixtures import ui_bundle  # noqa: E402
from evals.navigation_fixtures import (  # noqa: E402
    diagnosis_with,
    growth_evidence,
    growth_reader,
    growth_space,
    growth_supports,
    hiring_path_set,
    node,
    pathset,
    pp,
    revenue_artifact,
    routes_of,
)

OUT = pathlib.Path("e2e/fixtures")
NEW_REQ = "sample.injected_condition"
NAMES = [
    "Improve activation",
    "Raise trial conversion",
    "Shorten onboarding",
    "Reduce churn",
    "Grow referrals",
    "Partner with agencies",
    "Launch a community",
    "Test annual plans",
    "Add a self-serve tier",
    "Offer setup help",
]


def _synthetic_paths(n: int) -> dict:
    """n strategies from the synthetic (non-Revenue) domain — proof that the screen assumes no fixed five,
    and that the engine returns all of them (0..N); display capping is a UI policy (present-cap.js)."""
    strategies = tuple(
        StrategySpec(
            strategy_id=f"s{i}",
            title=NAMES[i],
            basis=f"{NAMES[i].lower()} to move toward the goal",
            presentation={
                "en": {
                    "word": NAMES[i].split()[0],
                    "short": NAMES[i],
                    "basis": f"{NAMES[i]} to move toward the goal.",
                }
            },
            emerges_when="state:goal",
            checks=(
                CheckSpec(
                    f"c{i}",
                    f"state:cond{i}",
                    "prereq",
                    None,
                    f"unlock {i}",
                    f"Condition {i}",
                    {"en": {"title": f"Condition {i} is in place", "unlock": f"Do the thing for {i}."}},
                ),
            ),
        )
        for i in range(n)
    )

    def reader(sid: str) -> Signal:
        if sid == "state:goal":
            return Signal(True, "a goal is stated", (), {"en": "A goal is stated"})
        i = int(sid.removeprefix("state:cond"))
        if i % 3 == 0:
            return Signal(True, f"kondisi {i} terpenuhi", (f"ev-{i}",), {"en": f"Condition {i} is met"})
        return Signal(None, f"kondisi {i} belum terukur", (), {"en": f"Condition {i} is not measured yet"})

    return build_path_set(PossibilitySpace(f"synthetic{n}", strategies, "state:goal"), reader)


# Eight candidates from rule-derived mechanisms (synthetic SaaS domain, no StrategySpec) with MIXED
# states: UI evidence for overflow above five, including a hidden path that still carries a reason.
_MANY = [
    # (direction, title, word, basis, because, check state: present | unknown | absent_prereq | absent_hard)
    (
        "improve_activation",
        "Improve activation first",
        "Activation",
        "Help new sign-ups reach value first.",
        "Many people sign up, but too few reach the moment where the product pays off.",
        "present",
    ),
    (
        "simplify_onboarding",
        "Simplify onboarding",
        "Onboarding",
        "Cut the first session down to what leads to value.",
        "Your first session is confusing, so people give up before they see value.",
        "unknown",
    ),
    (
        "clarify_pricing",
        "Clarify the pricing page",
        "Pricing page",
        "Say plainly what each plan includes.",
        "People ask what each plan includes before they will start.",
        "absent_prereq",
    ),
    (
        "fix_early_churn",
        "Fix early churn",
        "Early churn",
        "Find why people leave in the first week.",
        "A lot of people leave within a week of starting.",
        "absent_hard",
    ),
    (
        "longer_trial",
        "Test a longer trial",
        "Longer trial",
        "Give people time to reach value.",
        "The trial ends before most people have had time to try it properly.",
        "present",
    ),
    (
        "ask_referrals",
        "Ask happy users for referrals",
        "Referrals",
        "Turn the people who like it into your next sign-ups.",
        "A few users say they like it and have told friends on their own.",
        "unknown",
    ),
    (
        "faster_support",
        "Speed up support replies",
        "Support speed",
        "Answer new users while they are still trying it.",
        "New users wait too long for an answer and drift away.",
        "present",
    ),
    (
        "track_funnel",
        "Track the funnel",
        "Funnel tracking",
        "Measure where sign-ups stop.",
        "Nobody can say exactly where new sign-ups stop.",
        "unknown",
    ),
]


def _candidates_many() -> dict:
    from core.navigation.contracts import MechanismSpec, PossibilityPattern
    from core.navigation.knowledge import rule_signal
    from core.schema.evidence import EvidenceItem
    from core.stages.knowledge_rules import evaluate_rule_tier1

    ledger = [
        EvidenceItem(id=f"ev-m{i}", signal=f"symptom {i} is present", level="behavioral", topic="MOTION")
        for i in range(len(_MANY))
    ]
    supports = {}
    for i in range(len(_MANY)):
        rule = {
            "rule_id": f"MN-R{i}",
            "evaluation": {"tier": "deterministic", "predicate": {"text_contains_any": [f"symptom {i} "]}},
        }
        m = evaluate_rule_tier1(rule, ledger, "")
        supports[f"MN-R{i}"] = m.support if m.matched else None
    patterns = []
    for i, (direction, title, word, basis, because, state) in enumerate(_MANY):
        kind = "hard" if state == "absent_hard" else "prereq"
        patterns.append(
            PossibilityPattern(
                direction=direction,
                title=title,
                mechanism_ids=(f"mech_{i}",),
                thesis=basis,
                checks=(
                    CheckSpec(
                        f"chk_{i}",
                        f"state:chk{i}",
                        kind,
                        None,
                        f"unlock {i}",
                        f"Condition {i}",
                        {"en": {"title": f"Condition {i} is in place", "unlock": f"Do the thing for {i}."}},
                    ),
                ),
                presentation={"en": {"word": word, "short": title, "basis": basis, "because": because}},
            )
        )
    space = PossibilitySpace(
        "saas_many",
        (),
        "state:goal",
        mechanisms=tuple(
            MechanismSpec(f"mech_{i}", _MANY[i][2], activated_by=f"rule:MN-R{i}") for i in range(len(_MANY))
        ),
        patterns=tuple(patterns),
    )

    def reader(sid: str) -> Signal:
        kind, _, name = sid.partition(":")
        if kind == "rule":
            return rule_signal(name, supports.get(name))
        if kind == "mechanism":  # all mechanisms are derived from knowledge, not reported directly
            return Signal(None)
        if sid == "state:goal":
            return Signal(True, "a goal is stated", ("ev-m0",), {"en": "A goal is stated"})
        i = int(sid.removeprefix("state:chk"))
        state = _MANY[i][5]
        if state == "present":
            return Signal(True, f"condition {i} met", (f"ev-m{i}",), {"en": f"Condition {i} is met"})
        if state.startswith("absent"):
            return Signal(False, f"condition {i} not met", (f"ev-m{i}",), {"en": f"Condition {i} is not met"})
        return Signal(None, f"condition {i} unknown", (), {"en": f"Condition {i} is not measured yet"})

    return build_path_set(space, reader)


def _with_projection(possible_paths: dict, path_states: dict | None = None) -> dict:
    """Bundle paths + readiness projection from the real engine (items from path checks; no routes).
    `path_states` is forwarded as-is — exactly like production: the served projection ALWAYS carries
    the latest lifecycle (this iteration's audit; a projection without lifecycle renders a user's STOP
    decision as an open path)."""
    return {
        "possible_paths": possible_paths,
        "projection": build_readiness_projection(diagnosis_with(possible_paths), None, path_states),
    }


def _with_navigation(bundle: dict) -> dict:
    """Each fixture carries `navigation` from the engine (assess_path_set); the UI reads it,
    never derives it."""
    return {**bundle, "navigation": assess_path_set(bundle.get("possible_paths"))}


# Revenue state that makes ALL Revenue strategies give birth to a Possible Path (five motions as primitives)
REVENUE_FULL = dict(
    current_monthly=30.0,
    target_monthly=60.0,
    gap_monthly=30.0,
    capacity_utilization=0.5,
    willingness_to_pay="PROVEN_AT_CURRENT_PRICE",
    demand_exists=True,
    avg_deal_size=10.0,
)

# User decision (regret) that stops one path — one source for both the raw artifact AND the projection
_USER_STOP = {"path.value_repricing": {"outcome_state": "STOPPED", "moved": 0, "regret": 1}}


def _legacy_artifact() -> dict:
    """A legacy artifact genuinely loaded via the loader: the `revenue_paths` key, no `possible_paths`."""
    from domains.revenue.schema.artifact import DiagnosisArtifact

    dump = {
        k: v
        for k, v in revenue_artifact(**REVENUE_FULL).model_dump().items()
        if k not in ("possible_paths", "navigation")
    }
    dump["revenue_paths"] = [{"path": "ACQUISITION", "gate": "ELIGIBLE"}] * 5
    art = DiagnosisArtifact(**dump)
    return {"possible_paths": art.possible_paths, "navigation": art.navigation}


def _growth(states: dict | None = None, space=None, **ev_kw) -> dict:
    """PathSet of the synthetic "growth" domain (no strategy list): ledger, rules, mechanisms,
    candidates, paths."""
    return build_path_set(
        space or growth_space(), growth_reader(growth_supports(growth_evidence(**ev_kw)), states)
    )


def _growth_unsupported() -> dict:
    """Rule GW-R1 matched but its basis cannot be formed (UNSUPPORTED): zero positive support."""
    from core.schema.provenance import RuleSupport

    sup = growth_supports(growth_evidence())
    sup["GW-R1"] = RuleSupport(rule_id="GW-R1", tier="deterministic", reason="basis tak dapat dibentuk")
    return build_path_set(growth_space(), growth_reader(sup))


def _candidate_route_bundle() -> dict:
    """Candidate with a route: the `simplify_onboarding` strategy has a template; the route
    is merged via it."""
    ps = _growth(space=growth_space(with_template=True), onboarding=True)
    routes = routes_of(
        simplify_onboarding=[
            node("access.prospect_list", "PRESENT", "Write down who has signed up", nid="a"),
            node("access.icp", "UNKNOWN", "Write who you want to reach", nid="b"),
        ]
    )
    return {
        "possible_paths": ps,
        "projection": build_readiness_projection(diagnosis_with(ps), routes),
    }


def _readiness_bundle(checks: list[dict], nodes: list[dict], feasibility: str) -> dict:
    ps = pathset(
        pp("value_repricing", feasibility, checks, title="Repricing your offer", basis="naikkan harga")
    )
    ps["paths"][0]["presentation"] = {
        "en": {
            "word": "Pricing",
            "short": "Reprice your offer",
            "basis": "Raise or restructure your prices on the demand you already have.",
        }
    }
    proj = build_readiness_projection(diagnosis_with(ps), routes_of(value_repricing=nodes))
    return {"possible_paths": ps, "projection": proj}


def build() -> dict[str, dict]:
    goal = RevenueState(target_monthly=20.0)
    out: dict[str, dict] = {
        "paths_zero": {"possible_paths": build_possible_paths(goal, None)},
        "paths_one": {
            "possible_paths": build_possible_paths(
                goal, None, mechanisms={"pricing_avoidance_loop": ["ev-1"]}
            )
        },
        # 0..N: the engine returns ALL of them; the UI caps the display (present-cap.js)
        "paths_three": {"possible_paths": _synthetic_paths(3)},
        "paths_five": {"possible_paths": _synthetic_paths(5)},
        "paths_six": {"possible_paths": _synthetic_paths(6)},
        "paths_eight": {"possible_paths": _synthetic_paths(8)},
        "paths_ten": {"possible_paths": _synthetic_paths(10)},
        "paths_candidates_many": _with_projection(_candidates_many()),
        # Real Revenue: the five motions stay live domain primitives (not a path list)
        "paths_revenue_five": _with_projection(revenue_artifact(**REVENUE_FULL).possible_paths),
        # STOP from two different origins — both STOP, but not the same thing
        "paths_engine_stop": _with_projection(
            revenue_artifact(**{**REVENUE_FULL, "willingness_to_pay": "PRICE_SENSITIVE"}).possible_paths
        ),
        "paths_user_stop": _with_projection(
            revenue_artifact(path_states=_USER_STOP, **REVENUE_FULL).possible_paths,
            path_states=_USER_STOP,
        ),
        # knowledge-driven domain: evidence -> rule -> mechanism -> strategy -> path (no Revenue)
        "paths_knowledge": _with_projection(hiring_path_set(network_large=True)),
        # Candidate Possibility (internal-docs §23): paths born from mechanisms chained
        # over evidence, WITHOUT a strategy list — route-less; one with a route; one among five Revenue.
        "paths_candidates": _with_projection(_growth(onboarding=True)),
        "paths_candidate_route": _candidate_route_bundle(),
        # GOLDEN Candidate-born (doc 14 §24.8), from the production chain: ledger -> rule -> mechanism ->
        # candidate -> path -> REAL route composer -> readiness (canonical state: ledger) -> NextMove
        "paths_candidate_golden": ui_bundle(),
        # sibling-mechanism dispute: the path stands via independent branches; the dispute stays visible
        "paths_candidate_unsettled": _with_projection(_growth(onboarding=True, retention=True)),
        "paths_candidate_revenue": _with_projection(
            revenue_artifact(
                mechanisms={"lead_leakage": ["ev-7"], "targeting_gap": ["ev-8"]}, **REVENUE_FULL
            ).possible_paths
        ),
        # an EMERGING possibility (not a path): one missing fact / conflicting evidence / hint without basis
        "paths_emerging_unknown": _with_projection(
            _growth({"state:acquisition_exists": None}, onboarding=True, signups=False, weak=False)
        ),
        "paths_emerging_conflict": _with_projection(_growth(retention=True)),
        "paths_emerging_unsupported": _with_projection(_growth_unsupported()),
        "paths_legacy": _legacy_artifact(),
        # LEGACY WITH CONTENT (audit #9): a different schema version BUT populated paths — its content
        # is still not a finding. The projection is built FROM that old-versioned pathset (exactly what
        # the server serves): paths=[], navigation LEGACY — not a projection over CURRENT-rated content.
        "paths_legacy_content": _with_navigation(
            _with_projection(
                {
                    **revenue_artifact(**REVENUE_FULL).possible_paths,
                    "version": "v0-sebelum-navigasi-universal",
                }
            )
        ),
    }
    # requirement states: UNKNOWN (not checked yet), PARTIAL, all PRESENT, and a brand-new requirement
    out["readiness_unknown"] = _readiness_bundle(
        [],
        [
            node("offering.outcome", "UNKNOWN", nid="a"),
            node("commercial.pricing_basis", "UNKNOWN", nid="b"),
            node("commercial.willingness_to_pay", "UNKNOWN", nid="c"),
        ],
        "UNDETERMINED",
    )
    out["readiness_partial"] = _readiness_bundle(
        [],
        [
            node("offering.outcome", "PARTIAL", nid="a"),
            node("commercial.pricing_basis", "ABSENT", nid="b"),
            node("commercial.willingness_to_pay", "UNKNOWN", nid="c"),
        ],
        "CONDITIONAL",
    )
    out["readiness_satisfied"] = _readiness_bundle(
        [],
        [
            node("offering.outcome", "PRESENT", nid="a"),
            node("commercial.pricing_basis", "PRESENT", nid="b"),
            node("commercial.price", "PRESENT", nid="c"),
            node("commercial.willingness_to_pay", "PRESENT", nid="d"),
        ],
        "SUPPORTED",
    )
    # DISPUTE (doc 14 §10.1, audit #7/#13): the route node (ledger adjudication) says PRESENT, the path
    # check says ABSENT — one item with `settled=false` + a conflict note; the route authority decides
    # the reading, but the item is NOT counted as proven in counts, and the path's canonical feasibility
    # becomes UNDETERMINED (not SUPPORTED). The UI must render it as not-yet-settled — not "met",
    # not "missing", and the map must not draw a STOP for its path.
    out["readiness_conflict"] = _readiness_bundle(
        [
            {
                "check_id": "c-wtp",
                "requirement_id": "commercial.willingness_to_pay",
                "state": "ABSENT",
                "i18n": {
                    "en": {
                        "reason": "No proof yet that anyone pays this price today.",
                        "unlock": "Show one paid deal at the new price.",
                    }
                },
            }
        ],
        [
            node("commercial.willingness_to_pay", "PRESENT", nid="a"),
            node("offering.outcome", "UNKNOWN", nid="b"),
        ],
        "CONDITIONAL",
    )
    saved = req_mod.load_registry
    fake = dict(saved())
    fake[NEW_REQ] = {
        "requirement_id": NEW_REQ,
        "definition": "Kondisi baru yang hanya ada di registry.",
        "observability": ["Kondisi baru dapat diamati"],
        "satisfaction_rule": {"mode": "BINARY", "sufficient": "s", "no_decisive": "n", "contradicting": "c"},
        "provenance": {
            "source_id": "tm",
            "chapters": ["ch01"],
            "knowledge_type": "source_claim",
            "confidence": "normative_only",
        },
    }
    req_mod.load_registry = lambda: fake
    try:
        out["readiness_new_requirement"] = _readiness_bundle(
            [],
            [
                node(NEW_REQ, "UNKNOWN", "Jalankan satu uji kecil untuk kondisi baru", nid="a"),
                node("offering.outcome", "PRESENT", nid="b"),
            ],
            "UNDETERMINED",
        )
    finally:
        req_mod.load_registry = saved
    return {
        name: _with_navigation(bundle) if "navigation" not in bundle else bundle
        for name, bundle in out.items()
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, data in build().items():
        (OUT / f"{name}.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"wrote {OUT / (name + '.json')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
