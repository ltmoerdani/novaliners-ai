"""J3 (internal-docs §7) — Cross-session delta: ADVANCED | STUCK | PIVOTED | REGRESSED.

DETERMINISTIC comparison of two DiagnosisArtifacts (session n-1 vs n):
  - main axis: decision_spectrum.level (canonical order
    STOP→NOT_YET→TEST_FIRST→GO_SMALL→PROCEED→SCALE, core/stages/spectrum)
  - primary_constraint_id: same or changed

Verdict:
  - level up              → ADVANCED
  - level down            → REGRESSED
  - same level, same constraint       → STUCK
  - same level, different constraint  → PIVOTED

0-LLM — per the philosophy "LLM proposes, engine disposes". Used by finalize
(persisted in session) + GET /session/{sid}/journey (recompute on demand)."""
from __future__ import annotations

import time

from core.schema.constraints import ConstraintMapEntry  # noqa: F401 (layer contract)
from core.stages.spectrum import SPECTRUM_ORDER
from domains.revenue.schema.artifact import DiagnosisArtifact
from domains.revenue.schema.state import RevenueState

# J4 (internal-docs §7): sumbu E2E — PRA_SALES | SALES | AFTER_SALES
E2E_PHASES = ("PRA_SALES", "SALES", "AFTER_SALES")


def infer_e2e_phases(rs: RevenueState | None) -> list[str]:
    """Derive the user's position on the pre-sales/sales/after-sales axis from
    RevenueState — deterministic, multi-label (can be more than one phase).

    Rules (evidence-based, conservative):
      - PRE_SALES : demand not yet proven (signal NONE/UNKNOWN or
                    demand_exists False) → focus discovery/prospecting
      - SALES     : demand proven OR pricing/willingness-to-pay already
                    known → need to sell/price
      - AFTER_SALES: delivery ready (readiness.delivery/acquisition YES) OR
                    measured capacity → there are active customers to nurture
    Degrade-safe: empty → return ALL phases (neutral, no filter).
    """
    if rs is None:
        return list(E2E_PHASES)
    phases: set[str] = set()

    demand_known = (rs.demand_signal == "EXISTS") or (rs.demand_exists is True)
    known_anything = (
        demand_known
        or rs.demand_signal == "NONE"
        or rs.demand_exists is False
        or rs.pricing_architecture != "UNKNOWN"
        or rs.capacity_utilization is not None
        or any(v == "YES" for v in (rs.readiness or {}).values())
    )
    if not known_anything:
        return list(E2E_PHASES)  # no signal at all — neutral, without filter
    if not demand_known:
        phases.add("PRA_SALES")
    else:
        phases.add("SALES")

    if demand_known or rs.pricing_architecture != "UNKNOWN":
        phases.add("SALES")

    readiness = rs.readiness or {}
    if (readiness.get("delivery") == "YES" or readiness.get("acquisition") == "YES"
            or rs.capacity_utilization is not None):
        phases.add("AFTER_SALES")

    return sorted(phases) if phases else list(E2E_PHASES)


def compute_delta(prior: DiagnosisArtifact, current: DiagnosisArtifact) -> dict:
    """Compare two artifacts → journey verdict + measured value."""
    prior_level = str((prior.decision_spectrum or {}).get("level") or "")
    current_level = str((current.decision_spectrum or {}).get("level") or "")
    prior_idx = SPECTRUM_ORDER.index(prior_level) if prior_level in SPECTRUM_ORDER else -1
    current_idx = (
        SPECTRUM_ORDER.index(current_level) if current_level in SPECTRUM_ORDER else -1
    )

    same_constraint = (
        prior.primary_constraint_id == current.primary_constraint_id
    )

    if prior_idx < 0 or current_idx < 0:
        verdict = "INSUFFICIENT_DATA"  # unknown level — do not guess
    elif current_idx > prior_idx:
        verdict = "ADVANCED"
    elif current_idx < prior_idx:
        verdict = "REGRESSED"
    elif same_constraint:
        verdict = "STUCK"
    else:
        verdict = "PIVOTED"

    return {
        "verdict": verdict,
        "prior": {
            "session_artifact_level": prior_level,
            "primary_constraint_id": prior.primary_constraint_id,
        },
        "current": {
            "session_artifact_level": current_level,
            "primary_constraint_id": current.primary_constraint_id,
        },
        "spectrum_moved": current_idx - prior_idx if (
            prior_idx >= 0 and current_idx >= 0
        ) else None,
        "constraint_changed": not same_constraint,
    }


# --- J7 (internal-docs §7): delta consumption — session n is aware of n-1's result ------
# All pure & deterministic (0-LLM). Two legacy principles from internal-docs §6.4:
#   1. cross-session state = compiled summary (sleep-time pattern),
#      NOT the full transcript — the prompt block stays a few lines;
#   2. the verdict does not auto-apply to the KB (anti-pattern internal-docs) — it only
#      filters the menu/demotes interventions FOR THIS USER, the global KB is untouched.

# J7-c: outcomes that cause an intervention to be demoted for the same user.
# confounded is excluded (unmeasurable result — consistent with store/nba.py P3).
DEMOTE_OUTCOMES = ("not_moved", "regret")


def reassess_status(prior, now_ts: int | None = None) -> dict:
    """J7-a (slot D): reassess window status of the prior session — deterministic.

    Compares the prior session's age (created_ts) against reassess_window_days in
    its artifact. Degrade-safe: without diagnosis/timestamp/window → UNKNOWN,
    do not guess 'due'."""
    d = getattr(prior, "diagnosis", None)
    if d is None:
        return {"status": "NO_PRIOR_DIAGNOSIS"}
    window = int(getattr(d, "reassess_window_days", 0) or 0)
    created = int(getattr(prior, "created_ts", 0) or 0)
    if not window or not created:
        return {"status": "UNKNOWN", "window_days": window or None}
    age_days = max(0, int((now_ts or time.time()) - created) // 86400)
    return {
        "status": "DUE" if age_days >= window else "NOT_YET",
        "window_days": window,
        "age_days": age_days,
    }


def prior_action_summary(prior) -> dict:
    """J7-a: action-result summary of the prior session from ActionItem (status/outcome)."""
    d = getattr(prior, "diagnosis", None)
    items = list(getattr(d, "day_by_day", None) or [])
    by_status: dict[str, int] = {}
    by_outcome: dict[str, int] = {}
    for it in items:
        st = getattr(it, "status", None)
        oc = getattr(it, "outcome", None)
        if st:
            by_status[st] = by_status.get(st, 0) + 1
        if oc:
            by_outcome[oc] = by_outcome.get(oc, 0) + 1
    return {"n_items": len(items), "by_status": by_status, "by_outcome": by_outcome}


def compile_journey_context(prior, user_outcomes: dict | None = None) -> dict:
    """J7-b: compile the cross-session compiled summary → diagnosis context.

    Built BEFORE session n's artifact exists (delta n vs n-1 cannot be computed yet);
    the journey signals available = the prior session's journey_delta (vs n-2) +
    action summary + reassess. user_outcomes = {iid: {outcome: n}} of the same user
    (from store/nba via sessions_by_user)."""
    d = getattr(prior, "diagnosis", None)
    ctx: dict = {
        "prior": {
            "primary_constraint_id": getattr(d, "primary_constraint_id", None) if d else None,
            "spectrum_level": (d.decision_spectrum or {}).get("level") if d else None,
            # prior verdict vs the session before the prior one (n-1 vs n-2)
            "verdict": (getattr(prior, "journey_delta", None) or {}).get("verdict"),
        },
        "reassess": reassess_status(prior),
        "prior_actions": prior_action_summary(prior),
    }
    demoted: dict[str, str] = {}
    for iid, outs in (user_outcomes or {}).items():
        hits = {o: n for o, n in outs.items() if o in DEMOTE_OUTCOMES and n > 0}
        if hits:
            demoted[iid] = ",".join(f"{o}x{n}" for o, n in sorted(hits.items()))
    if demoted:
        ctx["demoted_interventions"] = demoted
    return ctx


def journey_prompt_block(ctx: dict | None) -> str:
    # moved -> prompts/copilot_and_journey.py (audit 25 Sep); shim backward-compat
    from domains.revenue.prompts.copilot_and_journey import (
        journey_prompt_block as _impl,
    )

    return _impl(ctx)


def demote_interventions(items: list, demoted: dict) -> tuple[list, list]:
    """J7-c (slot B): separate interventions whose outcome was bad for this user.

    Pure: (kept, removed). Items without an intervention_id are always kept."""
    kept, removed = [], []
    for it in items:
        iid = it.get("intervention_id") if isinstance(it, dict) else None
        (removed if (iid and iid in demoted) else kept).append(it)
    return kept, removed
