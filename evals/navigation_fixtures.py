"""Synthetic domain FOR TESTING (not production): proof that the universal navigation pipeline is not
locked to a single domain.

Two fictional plugin domains — SaaS and B2B — declare strategies, signals, and checks WITHOUT touching
core/. Not a single one of the five Revenue motions appears here; path identity comes from each
domain's own strategies.
"""

from __future__ import annotations

from core.navigation.contracts import (
    CheckSpec,
    MechanismSpec,
    PossibilityPattern,
    PossibilitySpace,
    Signal,
    StrategySpec,
)
from core.navigation.evaluator import PATHSET_VERSION


def reader_of(values: dict[str, bool | None], refs: dict[str, tuple[str, ...]] | None = None):
    """SignalReader built from a plain dict; an unlisted id = unknown (None), not False."""
    refs = refs or {}
    return lambda sid: Signal(values.get(sid), f"reason:{sid}", refs.get(sid, ()))


SAAS_SPACE = PossibilitySpace(
    space_id="saas",
    goal_signal="state:revenue_goal_set",
    strategies=(
        StrategySpec(
            strategy_id="activation_first",
            title="Improve activation before increasing acquisition",
            basis="perbaiki aktivasi sebelum menambah sign-up baru",
            emerges_when={"all_of": ["state:many_signups", "state:weak_activation"]},
            not_applicable_when="state:activation_already_strong",
            checks=(
                CheckSpec(
                    "activation_defined",
                    "state:aha_moment_defined",
                    "prereq",
                    "retention.aha_moment_defined",
                    "definisikan aha moment",
                ),
                CheckSpec("funnel_measured", "state:funnel_measured", "prereq", None, "ukur funnel sign-up"),
            ),
        ),
        StrategySpec(
            strategy_id="scale_acquisition",
            title="Scale acquisition",
            basis="tambah sign-up baru",
            emerges_when={"all_of": ["state:many_signups", {"not": "state:weak_activation"}]},
            checks=(CheckSpec("activation_strong", "state:activation_already_strong", "hard"),),
        ),
    ),
)

B2B_SPACE = PossibilitySpace(
    space_id="b2b",
    goal_signal="state:revenue_goal_set",
    strategies=(
        StrategySpec(
            strategy_id="decision_maker_access",
            title="Improve decision-maker access",
            basis="dapatkan akses ke pengambil keputusan",
            emerges_when={"all_of": ["state:many_leads", "state:poor_decision_maker_access"]},
            checks=(
                CheckSpec(
                    "dm_named",
                    "state:decision_maker_named",
                    "prereq",
                    "access.decision_maker",
                    "sebut pengambil keputusan per deal",
                ),
            ),
            route_template_ids=("dm_access_v1",),
        ),
        StrategySpec(
            strategy_id="lead_qualification",
            title="Qualify leads harder",
            emerges_when={"any_of": ["mechanism:lead_noise", "state:poor_decision_maker_access"]},
            checks=(),
        ),
    ),
)


def synthetic_space(n: int) -> PossibilitySpace:
    """A space with n strategies that can all be born — to test dynamic candidate counts (0/1/2/5/10)."""
    return PossibilitySpace(
        space_id=f"synthetic{n}",
        goal_signal="state:goal",
        strategies=tuple(
            StrategySpec(
                strategy_id=f"s{i}",
                title=f"Strategy {i}",
                emerges_when=f"state:trigger_{i}",
                checks=(CheckSpec(f"c{i}", f"state:cond_{i}", "prereq", None, f"unlock {i}"),),
            )
            for i in range(n)
        ),
    )


# ── Revenue fixture (uses the REAL Revenue plugin, not a handwritten path list) ─────────────────────────────


def revenue_artifact(
    level: str | None = "TEST_FIRST", mechanisms: dict | None = None, path_states: dict | None = None, **rs_kw
):
    """DiagnosisArtifact with `possible_paths` from the Revenue engine over a synthetic RevenueState.

    The number and content of paths follow the state passed in — tests using this fixture must not
    assume a fixed path count; use `strategy_ids(art)` to read what actually emerged."""
    from agents.diagnosis import DiagnosisDraft
    from domains.revenue.navigation.paths import build_possible_paths
    from domains.revenue.schema.artifact import DiagnosisArtifact
    from domains.revenue.schema.state import RevenueState
    from providers.mock import _mock_for

    rs = RevenueState(**rs_kw)
    art = _mock_for(DiagnosisDraft)
    return DiagnosisArtifact(
        status="final",
        where_you_are=art["where_you_are"],
        primary_constraint=art["primary_constraint"],
        primary_constraint_id="V2.1",
        do_not=art["do_not"],
        next_best_action=art["next_best_action"],
        success_metric=art["success_metric"],
        well_know_when=art["well_know_when"],
        pivot_rule=art["pivot_rule"],
        revenue_state=rs,
        possible_paths=build_possible_paths(
            rs, {"level": level}, mechanisms=mechanisms, path_states=path_states
        ),
    )


def strategy_ids(art) -> list[str]:
    return [p["strategy_id"] for p in (art.possible_paths or {}).get("paths", [])]


def route_for(
    strategy_id: str,
    *,
    applies: bool = True,
    states: dict[str, str] | None = None,
    nodes: list[tuple[str, str, str]] | None = None,
) -> dict:
    """Route fixture for one strategy: nodes = [(requirement_id, satisfaction, activity)]."""
    nodes = nodes or [
        ("access.prospect_list", "PRESENT", "Tulis daftar orang yang bisa dihubungi"),
        ("access.icp", "ABSENT", "Tulis siapa yang Anda jual kepada"),
        ("access.cadence", "UNKNOWN", "Catat jumlah orang yang Anda hubungi tiap minggu"),
        ("access.outreach_asset", "UNKNOWN", "Tulis pesan pembuka pendek"),
    ]
    out = []
    for i, (rid, sat, act) in enumerate(nodes):
        out.append(
            {
                "node_id": f"{strategy_id}-n{i}",
                "resolves": [rid],
                "activity": act,
                "satisfaction": {"status": (states or {}).get(rid, sat)},
                "strength": "hard" if i < 2 else "soft",
                "depends_on": [],
                "executability": "TRUE",
            }
        )
    return {
        "strategy_id": strategy_id,
        "route_id": f"r-{strategy_id}",
        "template_id": f"{strategy_id}_v1",
        "applicability": {"status": "APPLIES" if applies else "UNDETERMINED"},
        "lineage_status": "OPEN",
        "revision_no": 1,
        "nodes": out,
    }


# ── Projection fixture: handwritten PathSet & routes with EXACTLY controlled states ──────────


def check_row(
    check_id: str,
    state: str,
    *,
    kind: str = "prereq",
    requirement_id: str | None = None,
    title: str = "",
    reason: str = "",
    unlock: str = "",
    refs: tuple[str, ...] = (),
) -> dict:
    return {
        "check_id": check_id,
        "requirement_id": requirement_id,
        "title": title,
        "state": state,
        "kind": kind,
        "reason": reason,
        "unlock": unlock,
        "refs": list(refs),
    }


def pp(
    strategy_id: str,
    feasibility: str = "SUPPORTED",
    checks: list[dict] | None = None,
    title: str = "",
    basis: str = "",
) -> dict:
    """One minimal-valid Possible Path (used by projections); status is recomputed by the projection."""
    from core.navigation.contracts import display_status

    return {
        "path_id": f"path.{strategy_id}",
        "strategy_id": strategy_id,
        "motion": None,
        "title": title or strategy_id.replace("_", " ").title(),
        "basis": basis,
        "presentation": {},
        "applicability": "APPLIES",
        "feasibility": feasibility,
        "lifecycle": "OPEN",
        "status": display_status(feasibility, "OPEN"),
        "stop_provenance": [],
        "checks": checks or [],
        "unlock_conditions": [],
        "missing_evidence": [],
        "advisory": "",
        "provenance": {"support": [{"signal": "state:x", "reason": "", "refs": []}]},
        "route_substrate": {"template_ids": [], "available": False},
    }


def pathset(*paths: dict, unresolved: list[dict] | None = None) -> dict:
    return {
        "version": PATHSET_VERSION,
        "space_id": "test",
        "paths": list(paths),
        "generation": {},
        "unresolved": unresolved or [],
    }


def node(
    req: str,
    state: str,
    activity: str = "Tulis dulu",
    strength: str = "hard",
    depends: list[str] | None = None,
    nid: str = "",
    executability: str = "TRUE",
    executed: bool = False,
) -> dict:
    return {
        "node_id": nid or f"n-{req}",
        "resolves": [req],
        "activity": activity,
        "satisfaction": {"status": state},
        "strength": strength,
        "depends_on": depends or [],
        "executability": executability,
        "execution_view": "EXECUTED" if executed else "NOT_STARTED",
    }


def routes_of(**by_strategy: list[dict]) -> dict:
    return {
        "routes": [
            {
                "strategy_id": sid,
                "route_id": f"r-{sid}",
                "template_id": f"{sid}_v1",
                "applicability": {"status": "APPLIES"},
                "lineage_status": "OPEN",
                "revision_no": 1,
                "nodes": nodes,
            }
            for sid, nodes in by_strategy.items()
        ]
    }


def diagnosis_with(pset: dict):
    """DiagnosisArtifact with a handwritten possible_paths."""
    from agents.diagnosis import DiagnosisDraft
    from domains.revenue.schema.artifact import DiagnosisArtifact
    from providers.mock import _mock_for

    art = _mock_for(DiagnosisDraft)
    return DiagnosisArtifact(
        status="final",
        where_you_are=art["where_you_are"],
        primary_constraint=art["primary_constraint"],
        primary_constraint_id="V2.1",
        do_not=art["do_not"],
        next_best_action=art["next_best_action"],
        success_metric=art["success_metric"],
        well_know_when=art["well_know_when"],
        pivot_rule=art["pivot_rule"],
        possible_paths=pset,
    )


# ── Synthetic knowledge-driven domain ("hiring"): evidence → rule → mechanism → strategy → path ──────────
# Everything here is DOMAIN DATA; the full chain runs through generic rule interpreter, generator, evaluator.
HIRING_REQ = "hiring.interview_rubric"  # used by tests that inject a registry-only requirement
HIRING_RULE = {
    "rule_id": "HR-R1",
    "evaluation": {
        "tier": "deterministic",
        "predicate": {
            "all_of": [{"text_contains_any": ["tanpa rubrik"]}, {"text_contains_any": ["nilai subjektif"]}]
        },
    },
}
HIRING_MECHANISMS = {"inconsistent_hiring_bar": ["ev-hr-2"]}  # mechanism detected from evidence


def hiring_evidence():
    from core.schema.evidence import EvidenceItem

    return [
        EvidenceItem(
            id="ev-hr-1", signal="wawancara dilakukan tanpa rubrik", level="behavioral", topic="MOTION"
        ),
        EvidenceItem(
            id="ev-hr-2", signal="penilaian kandidat nilai subjektif", level="behavioral", topic="MOTION"
        ),
        EvidenceItem(id="ev-hr-3", signal="kantor ada di lantai dua", level="behavioral", topic="MOTION"),
    ]


def hiring_space(with_requirement: bool = True) -> PossibilitySpace:
    """`with_requirement=False`: a check without a registry anchor (hiring.* does not exist in the
    real registry)."""
    return PossibilitySpace(
        space_id="hiring",
        goal_signal="state:hiring_goal",
        strategies=(
            StrategySpec(
                strategy_id="structured_interviews",
                title="Structured interviews",
                basis="interview every candidate against the same written rubric",
                presentation={
                    "en": {
                        "word": "Interviews",
                        "short": "Structured interviews",
                        "basis": "Interview every candidate against the same written rubric.",
                    }
                },
                # knowledge (rule) + mechanism -> strategy: EXPLICIT mapping in data (KNOW-03)
                emerges_when={"all_of": ["rule:HR-R1", "mechanism:inconsistent_hiring_bar"]},
                checks=(
                    CheckSpec(
                        "rubric",
                        "state:rubric_exists",
                        "prereq",
                        HIRING_REQ if with_requirement else None,
                        "write the interview rubric",
                        "Interview rubric",
                        {
                            "en": {
                                "title": "A written interview rubric exists",
                                "unlock": "Write a one-page rubric.",
                            }
                        },
                    ),
                ),
                route_template_ids=("structured_interviews_v1",),
            ),
            StrategySpec(
                strategy_id="referral_hiring",
                title="Referral hiring",
                emerges_when="state:network_large",
                no_preconditions=True,
            ),
        ),
    )


def hiring_reader(rule_support, *, network_large: bool = False, detect_mechanisms: bool = True):
    from core.navigation.knowledge import rule_signal

    def read(sid: str) -> Signal:
        kind, _, name = sid.partition(":")
        if kind == "rule":
            return rule_signal(name, {"HR-R1": rule_support}.get(name))
        if kind == "mechanism":
            hits = HIRING_MECHANISMS.get(name) if detect_mechanisms else None
            return (
                Signal(True, f"mechanism {name}", tuple(hits), {"en": f"Mechanism {name} was detected"})
                if hits
                else Signal(None)
            )
        if sid == "state:hiring_goal":
            return Signal(True, "goal", ("ev-hr-goal",), {"en": "A hiring goal is stated"})
        if sid == "state:network_large":
            return Signal(True, "jaringan besar", ("ev-hr-net",)) if network_large else Signal(False)
        return Signal(None, "belum terukur", (), {"en": "Not measured yet"})

    return read


def hiring_path_set(*, network_large: bool = False, with_requirement: bool = False) -> dict:
    """PathSet from the REAL chain: ledger -> rule interpreter -> signals -> generator -> evaluator."""
    from core.navigation.evaluator import build_path_set
    from core.stages.knowledge_rules import evaluate_rule_tier1

    m = evaluate_rule_tier1(HIRING_RULE, hiring_evidence(), "")
    return build_path_set(
        hiring_space(with_requirement), hiring_reader(m.support, network_large=network_large)
    )


# ── Knowledge -> Mechanism -> Candidate Possibility layer (internal-docs §23) ──────────────
# Two synthetic domains WITHOUT a strategy list: directions are born from knowledge-activated mechanisms.


def hiring_candidate_space() -> PossibilitySpace:
    """Hiring without a `StrategySpec`: rule HR-R1 -> derived mechanism -> candidate -> path."""
    return PossibilitySpace(
        space_id="hiring_candidates",
        goal_signal="state:hiring_goal",
        strategies=(),
        mechanisms=(
            MechanismSpec(
                "inconsistent_hiring_bar",
                "An inconsistent hiring bar",
                activated_by="rule:HR-R1",
            ),
        ),
        patterns=(
            PossibilityPattern(
                direction="calibrate_hiring_bar",
                title="Calibrate the hiring bar before opening more roles",
                mechanism_ids=("inconsistent_hiring_bar",),
                thesis="candidates are judged differently, so more volume only multiplies the noise",
                checks=(
                    CheckSpec("rubric", "state:rubric_exists", "prereq", None, "write the interview rubric"),
                ),
            ),
        ),
    )


GROWTH_RULES = {
    # nested + all_of + none_of: many sign-ups AND (weak activation OR early churn), no explicit rebuttal
    "GW-R1": {
        "rule_id": "GW-R1",
        "evaluation": {
            "tier": "deterministic",
            "predicate": {
                "all_of": [
                    {"text_contains_any": ["sign-up banyak"]},
                    {
                        "any_of": [
                            {"text_contains_any": ["tidak mencapai aha"]},
                            {"text_contains_any": ["churn awal"]},
                        ]
                    },
                    {"none_of": [{"text_contains_any": ["aktivasi sudah kuat"]}]},
                ]
            },
        },
    },
    "GW-R2": {
        "rule_id": "GW-R2",
        "evaluation": {
            "tier": "deterministic",
            "predicate": {"text_contains_any": ["onboarding membingungkan"]},
        },
    },
    # EXPLICIT counter-evidence against the activation bottleneck
    "GW-R3": {
        "rule_id": "GW-R3",
        "evaluation": {
            "tier": "deterministic",
            "predicate": {"text_contains_any": ["retensi hari-7 tinggi"]},
        },
    },
    # pure none_of: absence is not support (no positive anchor -> UNSUPPORTED)
    "GW-R4": {
        "rule_id": "GW-R4",
        "evaluation": {
            "tier": "deterministic",
            "predicate": {"none_of": [{"text_contains_any": ["aktivasi sudah kuat"]}]},
        },
    },
}


def growth_evidence(*, signups=True, weak=True, onboarding=False, strong=False, churn=False, retention=False):
    from core.schema.evidence import EvidenceItem

    items = []
    if signups:
        items.append(
            EvidenceItem(id="ev-g-1", signal="sign-up banyak tiap minggu", level="behavioral", topic="MOTION")
        )
    if weak:
        items.append(
            EvidenceItem(
                id="ev-g-2", signal="pengguna baru tidak mencapai aha", level="behavioral", topic="MOTION"
            )
        )
    if churn:
        items.append(
            EvidenceItem(
                id="ev-g-5", signal="churn awal di minggu pertama", level="behavioral", topic="MOTION"
            )
        )
    if onboarding:
        items.append(
            EvidenceItem(id="ev-g-3", signal="onboarding membingungkan", level="behavioral", topic="MOTION")
        )
    if strong:
        items.append(
            EvidenceItem(id="ev-g-4", signal="aktivasi sudah kuat", level="behavioral", topic="MOTION")
        )
    if retention:
        items.append(
            EvidenceItem(id="ev-g-6", signal="retensi hari-7 tinggi", level="behavioral", topic="MOTION")
        )
    items.append(EvidenceItem(id="ev-g-9", signal="kantor di lantai dua", level="behavioral", topic="MOTION"))
    return items


def growth_supports(evidence, transcript: str = "") -> dict:
    """rule_id -> RuleSupport (or None when the rule did not match) from the REAL rule interpreter."""
    from core.stages.knowledge_rules import evaluate_rule_tier1

    out = {}
    for rid, rule in GROWTH_RULES.items():
        m = evaluate_rule_tier1(rule, evidence, transcript)
        out[rid] = m.support if m.matched else None
    return out


def _pres(word: str, short: str, basis: str, because: "str | dict[str, str]") -> dict:
    """`because` = the pattern text, or {mechanism_id: text} when the pattern has multiple causal
    mechanisms (only the ACTIVE mechanism's sentence is used: the reason must not narrate a disputed
    mechanism)."""
    return {"en": {"word": word, "short": short, "basis": basis, "because": because}}


def growth_space(*, with_declared_strategy: bool = False, with_template: bool = False) -> PossibilitySpace:
    """The "growth" domain: no strategy list. Two rule-derived mechanisms; three directions.

    activation_bottleneck <- GW-R1 (contradicted by GW-R3)     onboarding_friction <- GW-R2
    improve_activation_before_acquisition <- {activation_bottleneck | onboarding_friction}  (one candidate
                                             even though two mechanisms point at it)
    define_aha_moment <- activation_bottleneck            (same mechanism, different candidate)
    simplify_onboarding <- onboarding_friction
    """
    strategies = ()
    if with_declared_strategy:
        strategies = (
            StrategySpec(
                strategy_id="define_aha_moment",
                title="Define the aha moment",
                emerges_when="state:aha_undefined",
                no_preconditions=True,
            ),
        )
    return PossibilitySpace(
        space_id="growth",
        goal_signal="state:revenue_goal",
        strategies=strategies,
        mechanisms=(
            MechanismSpec(
                "activation_bottleneck",
                "Activation bottleneck",
                activated_by="rule:GW-R1",
                contradicted_by="rule:GW-R3",
            ),
            MechanismSpec("onboarding_friction", "Onboarding friction", activated_by="rule:GW-R2"),
        ),
        patterns=(
            PossibilityPattern(
                direction="improve_activation_before_acquisition",
                title="Improve activation before increasing acquisition",
                mechanism_ids=("activation_bottleneck", "onboarding_friction"),
                thesis="acquiring more people into a weak activation only multiplies the leak",
                context_when="state:acquisition_exists",
                checks=(
                    CheckSpec(
                        "aha_defined",
                        "state:aha_defined",
                        "prereq",
                        None,
                        "define the aha moment",
                        "The aha moment is defined",
                        {
                            "en": {
                                "title": "The aha moment is defined",
                                "unlock": "Name the moment a user first gets value.",
                            }
                        },
                    ),
                ),
                presentation=_pres(
                    "Activation",
                    "Improve activation first",
                    "Help new sign-ups reach value before you bring in more of them.",
                    {
                        "activation_bottleneck": "Many people sign up, but too few reach the moment where "
                        "the product pays off.",
                        "onboarding_friction": "Your first session is confusing, so people give up before "
                        "they see value.",
                    },
                ),
            ),
            PossibilityPattern(
                direction="define_aha_moment",
                title="Define the aha moment",
                mechanism_ids=("activation_bottleneck",),
                thesis="without a named aha moment nobody can tell if activation improves",
                presentation=_pres(
                    "Aha moment",
                    "Define the aha moment",
                    "Name the moment a user first gets value, so you can tell if activation improves.",
                    "New users are not reaching value, and nobody has named what value looks like.",
                ),
                **({} if with_declared_strategy else {"no_preconditions": True}),
            ),
            PossibilityPattern(
                direction="simplify_onboarding",
                title="Simplify onboarding",
                mechanism_ids=("onboarding_friction",),
                thesis="friction in the first session keeps people from reaching value",
                no_preconditions=True,
                presentation=_pres(
                    "Onboarding",
                    "Simplify onboarding",
                    "Cut the first session down to the steps that lead to value.",
                    "Your first session is confusing, so people give up before they see value.",
                ),
                route_template_ids=("simplify_onboarding_v1",) if with_template else (),
            ),
        ),
    )


def growth_reader(
    supports: dict,
    states: dict[str, bool | None] | None = None,
    refs: dict[str, tuple[str, ...]] | None = None,
):
    """The growth domain reader: `rule:` via the generic bridge; `state:` from a dict; mechanisms are
    NOT reported directly (all are derived from knowledge). `refs` overrides the state-signal evidence
    anchors (defaults: invented ids `ev-g-goal`/`ev-g-acq`; lineage tests use real ledger ids)."""
    from core.navigation.knowledge import rule_signal

    base = {"state:revenue_goal": True, "state:acquisition_exists": True}
    base.update(states or {})
    refs = {"state:revenue_goal": ("ev-g-goal",), "state:acquisition_exists": ("ev-g-acq",), **(refs or {})}

    def read(sid: str) -> Signal:
        kind, _, name = sid.partition(":")
        if kind == "rule":
            return rule_signal(name, supports.get(name)) if name in supports else Signal(None)
        if kind == "mechanism":
            return Signal(None)
        val = base.get(sid)
        name = sid.partition(":")[2].replace("_", " ")
        en = f"{name.capitalize()} is confirmed" if val else f"{name.capitalize()} is not measured yet"
        return Signal(
            val,
            f"{name}: {'terbukti' if val else 'belum terukur'}",
            refs.get(sid, ()) if val else (),
            {"en": en},
        )

    return read


# ── Synthetic domain #3 ("signals"): N directions, all born from knowledge — no StrategySpec ──────────
# Proves 0..N cardinality on the evidence -> rule -> mechanism -> candidate -> path chain without fixed
# numbers: the path count = the number of symptoms actually proven in the ledger. Rules run through the
# REAL tier-1 interpreter.


def signals_rule(i: int) -> dict:
    return {
        "rule_id": f"SG-R{i}",
        "evaluation": {"tier": "deterministic", "predicate": {"text_contains_any": [f"gejala nomor {i}"]}},
    }


def signals_space(n: int, *, templates: dict[int, str] | None = None) -> PossibilitySpace:
    """n directions (`direction_i`), each from one derived mechanism `mech_i <- rule:SG-Ri`.
    `templates` = {i: template_id} for directions with a route substrate; the rest are route-less."""
    templates = templates or {}
    return PossibilitySpace(
        space_id=f"signals{n}",
        goal_signal="state:goal",
        strategies=(),
        mechanisms=tuple(
            MechanismSpec(f"mech_{i}", f"Mechanism {i}", activated_by=f"rule:SG-R{i}") for i in range(n)
        ),
        patterns=tuple(
            PossibilityPattern(
                direction=f"direction_{i}",
                title=f"Direction {i}",
                mechanism_ids=(f"mech_{i}",),
                thesis=f"gejala nomor {i} menyiratkan arah {i}",
                no_preconditions=True,
                route_template_ids=(templates[i],) if i in templates else (),
            )
            for i in range(n)
        ),
    )


def signals_ledger(active) -> list:
    """One evidence per active symptom — id `ev-sg-i`, text contains exactly one rule phrase."""
    from core.schema.evidence import EvidenceItem

    items = [
        EvidenceItem(
            id=f"ev-sg-{i}", signal=f"ada gejala nomor {i} di bisnis", level="behavioral", topic="MOTION"
        )
        for i in sorted(active)
    ]
    items.append(
        EvidenceItem(id="ev-sg-noise", signal="kantor di lantai dua", level="behavioral", topic="MOTION")
    )
    return items


def signals_reader(n: int, ledger, *, goal: bool = True):
    from core.navigation.knowledge import rule_signal
    from core.stages.knowledge_rules import evaluate_rule_tier1

    supports = {}
    for i in range(n):
        m = evaluate_rule_tier1(signals_rule(i), ledger, "")
        supports[f"SG-R{i}"] = m.support if m.matched else None

    def read(sid: str) -> Signal:
        kind, _, name = sid.partition(":")
        if kind == "rule":
            return rule_signal(name, supports.get(name)) if name in supports else Signal(None)
        if sid == "state:goal" and goal:
            return Signal(True, "tujuan dinyatakan", ("ev-sg-goal",), {"en": "A goal is stated"})
        return Signal(None)

    return read


def signals_path_set(n: int, active, **kw) -> dict:
    """PathSet from the REAL chain for the 'signals' domain:
    ledger -> rule interpreter -> mechanism -> path."""
    from core.navigation.evaluator import build_path_set

    return build_path_set(signals_space(n, **kw), signals_reader(n, signals_ledger(active)))
