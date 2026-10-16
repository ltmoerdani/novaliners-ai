"""Possible Paths for the Revenue domain: universal pipeline + Revenue hooks (lifecycle, advisory).

    RevenueState + detected mechanisms + active rules
      -> RevenueSignals (signal reader)  -> generator (candidates) -> evaluator (Possible Path 0..N)

This function does not carry a path list. The paths that appear are determined by `emerges_when` in
ontology/possibility/revenue.json against the verified state; on a thin state the result is ZERO
paths with an explicit reason.

Spectrum (decision_spectrum) still does NOT override feasibility — it only attaches as `advisory`
(doctrine: spectrum = decision surface, path = route map; do not mix them)."""

from __future__ import annotations

from typing import Any

from core.navigation.contracts import Lifecycle, path_id_for
from core.navigation.evaluator import build_path_set
from domains.revenue.navigation.signals import RevenueSignals
from domains.revenue.navigation.space import revenue_space
from domains.revenue.schema.goal import Goal
from domains.revenue.schema.goal_evaluation import goal_readiness
from domains.revenue.stages.reroute import STOPPED
from ontology.registry.metrics import known_metric as metric_known

NOTE = (
    "Peta jalur ini berdasar keadaan yang sudah terukur; seberapa besar Anda boleh melangkah tetap diatur "
    "Decision Spectrum (GO. STOP. OR DO SOMETHING ELSE). NOT YET berarti syaratnya belum terpenuhi dan bisa "
    "dibuka; STOP berarti jalur ini bertentangan dengan kondisi bisnis Anda sekarang atau sudah Anda "
    "hentikan."
)
NOTE_I18N = {
    "en": (
        "This map of paths is built from what is measured today; how big a step you may take is still "
        "governed by the Decision Spectrum (GO. STOP. OR DO SOMETHING ELSE). NOT YET means the condition "
        "is not met yet and can be opened; STOP means this path collides with your business as it stands "
        "today, or you stopped it yourself."
    )
}


_ADVISORY = {
    "STOP": {
        "id": "Jalurnya masuk akal, tapi untuk sekarang tahan dulu: ukur dan uji kecil sebelum komit.",
        "en": "This path makes sense, but hold for now: measure and test small before you commit.",
    },
    "TEST_FIRST": {
        "id": "Jalur lewat percobaan kecil dulu, bukan langsung memperbesar skala.",
        "en": "Go through a small test first, not straight to scale.",
    },
}
_ADVISORY["NOT_YET"] = _ADVISORY["STOP"]


def _advisory(level: str | None):
    """Anti-premature (internal-docs P0-4): path feasibility is not permission to scale."""
    text = _ADVISORY.get(level or "", {})
    return lambda _path: dict(text)


def lifecycles_from_states(states: dict[str, dict] | None) -> dict[str, dict[str, Any]]:
    """User-owned outcome state per path (store/path_states, key path_id) -> universal lifecycle.

    STOPPED from a `regret` outcome report = a decision/proof from the USER, recorded as lifecycle —
    separate from the engine-found contradiction (feasibility)."""
    out: dict[str, dict[str, Any]] = {}
    for pid, st in (states or {}).items():
        if (st or {}).get("outcome_state") == STOPPED:
            out[pid] = {
                "state": Lifecycle.STOPPED,
                "origin": "USER_OUTCOME",
                "cause": (
                    f"outcome=regret tercatat untuk jalur ini (moved={st.get('moved', 0)}, "
                    f"regret={st.get('regret', 0)}) — buka kembali bila bukti positif (moved) masuk"
                ),
                "cause_i18n": {
                    "en": (
                        f"You reported regret on this path (moved {st.get('moved', 0)}, regret "
                        f"{st.get('regret', 0)}). It reopens when a positive result (moved) comes in."
                    )
                },
            }
    return out


# Zero-path Goal-Relative reason taxonomy (int 09 §5.1) — mapped onto the universal generator codes
# (GOAL_NOT_ESTABLISHED etc.), NOT replacing them: the domain adapter adds `goal_code` +
# readiness detail so the cause Goal-underspecified vs metric-unsupported is visible.
GOAL_UNDERSPECIFIED = "GOAL_UNDERSPECIFIED"
GOAL_METRIC_UNSUPPORTED = "GOAL_METRIC_UNSUPPORTED"
_UNDER_SPECIFIED_CODES = {
    "METRIC_UNRESOLVED", "QUALIFICATION_UNDEFINED", "WINDOW_MISSING",
    "TARGET_MISSING", "ACTIVITY_NOT_OUTCOME", "DIRECTION_MISSING",
}


_ORIGIN_STRENGTH = {
    None: 0, "goal_fallback": 1, "transcript_marker": 2,
    "intent_phrase": 3, "goal_marker": 4, "explicit_input": 5,
}


def apply_goal_state_overlay(revenue_state: Any, goal: Any) -> None:
    """Goal -> RevenueState projection (int 09 §5 boundary; revenue metrics ONLY).

    A Goal value may appear in a derived RevenueState slot only with provenance:
    the overlay fills target_monthly/current_monthly that are absent from the Goal registry
    revenue_monthly (explicit input / traced parse), then recomputes the gap.
    A non-revenue Goal is NEVER forced into a revenue slot (rejected alternative int 09 §7.1)."""
    if revenue_state is None or goal is None:
        return
    g = goal if isinstance(goal, Goal) else Goal(
        **{k: v for k, v in (goal or {}).items() if k in Goal.model_fields})
    if g.resolved_metric_id() != "revenue_monthly":
        return
    if g.target is not None:
        state_origin = getattr(revenue_state, "target_origin", None)
        state_has = getattr(revenue_state, "target_monthly", None) is not None
        # Origin kuat menang (int 09 §2.1 target_origin): input eksplisit Goal menggantikan
        # the fallback 'Rp pertama' belongs to state parsing — not the other way around
    # (target-fallback incident).
        if not state_has or _ORIGIN_STRENGTH.get(g.target_origin, 0) > _ORIGIN_STRENGTH.get(
                state_origin, 0):
            revenue_state.target_monthly = round(float(g.target), 1)
            revenue_state.target_origin = g.target_origin
            revenue_state.sources["target_monthly"] = {
                "derivation": "goal context (registry revenue_monthly)",
                "confidence": "measured",
                "origin": g.target_origin,
            }
            if state_has:
                revenue_state.notes = list(getattr(revenue_state, "notes", [])) + [
                    "target dari konteks Goal terstruktur menggantikan fallback parse "
                    f"(origin {state_origin} < {g.target_origin})"
                ]
    if getattr(revenue_state, "current_monthly", None) is None and g.current is not None:
        revenue_state.current_monthly = round(float(g.current), 1)
        revenue_state.sources["current_monthly"] = {
            "derivation": "goal context (registry revenue_monthly)",
            "confidence": "measured",
        }
    cur, tgt = getattr(revenue_state, "current_monthly", None), getattr(
        revenue_state, "target_monthly", None)
    if cur is not None and tgt is not None and getattr(revenue_state, "gap_monthly", None) is None:
        revenue_state.gap_monthly = round(tgt - cur, 1)
        revenue_state.sources["gap_monthly"] = {
            "derivation": f"target {tgt} - current {cur} (dari konteks Goal)",
            "confidence": "derived",
        }


def goal_context_of(goal: Any) -> dict[str, Any] | None:
    """Goal context projection for PathSet/UI (int 09 §4.1): identity + semantics + readiness.
    Supporting-metric relations are preserved as they are — a relation without knowledge grounding
    stays UNKNOWN_RELATION, not turned into a causal claim (GR-16)."""
    if goal is None:
        return None
    g = goal if isinstance(goal, Goal) else Goal(**{k: v for k, v in (goal or {}).items()
                                                    if k in Goal.model_fields})
    rd = goal_readiness(g)
    mdef = g.metric_definition() or {}
    return {
        "goal_id": g.goal_id,
        "metric_id": g.resolved_metric_id(),
        "metric_version": g.metric_version,
        "metric_name": (mdef.get("display_name") or {}).get("en", g.resolved_metric_id()),
        "direction": g.direction,
        "category": g.category,
        "unit": g.unit,
        "scope": g.scope,
        "measurement_window_days": g.measurement_window_days,
        "deadline_days": g.deadline_days,
        "target_origin": g.target_origin,
        "target_confirmed": g.confirmed_target(),
        "success_definition": g.success_definition,
        "guardrails": list(g.guardrails),
        "supporting_metrics": list(g.supporting_metrics),
        "readiness": {"ready": rd["ready"], "blocking": rd["blocking"],
                      "unresolved": rd["unresolved"]},
    }


def _refine_goal_unresolved(result: dict[str, Any], goal: Any) -> None:
    """Zero-path + active Goal gate: add the goal_code code (int 09 SS5.1) to the universal
    blocker (generator codes unchanged — compatible with existing consumers)."""
    ctx = result.get("context", {}).get("goal") or {}
    for row in result.get("unresolved") or []:
        if row.get("code") not in ("GOAL_NOT_ESTABLISHED", "GOAL_ABSENT"):
            continue
        blocking = set(ctx.get("readiness", {}).get("blocking") or [])
        mid = ctx.get("metric_id") or ""
        if mid and not metric_known(mid):
            row["goal_code"] = GOAL_METRIC_UNSUPPORTED
        elif blocking:
            row["goal_code"] = GOAL_UNDERSPECIFIED
            row["goal_blocking"] = sorted(blocking & _UNDER_SPECIFIED_CODES or blocking)
        else:
            row["goal_code"] = GOAL_UNDERSPECIFIED


# ── Goal-to-Path relation (int 09 §4.2/§4.3; A-04..A-07) ────────────────────────────
# Vocabulary relation = int 09 §3.3 contract. Decision key (ADR-GR2, implementation-log):
#  - revenue_monthly metric + Revenue possibility space → DEFINITIONAL domain relation
#    (strategies in this space operate on revenue mechanics): DIRECT_CONTRIBUTION.
#  - non-revenue metric: NO Knowledge rule connects the strategy's mechanism
#    to the Goal metric on the current substrate → UNKNOWN_RELATION with an honest note.
#    Do not invent a relation just to make the path look relevant; a revenue gap alone is not proof.
UNKNOWN_RELATION = "UNKNOWN_RELATION"
DIRECT_CONTRIBUTION = "DIRECT_CONTRIBUTION"


def _goal_relation_of(metric_id: str) -> tuple[str, str]:
    """(relation, note) — a domain-adapter decision; the universal engine is unchanged."""
    if metric_id == "revenue_monthly":
        # ADR-GR2 revision (§3.4 round-2 mandate): DIRECT_CONTRIBUTION is a domain DEFINITION
        # (revenue-space strategies target income), NOT a measured-effectiveness claim —
        # effectiveness for the user's situation is judged by the path checks/status, recorded in note.
        return DIRECT_CONTRIBUTION, (
            "Relasi DIRECT_CONTRIBUTION = definisi domain ruang revenue (strategi di ruang ini "
            "menargetkan pendapatan), bukan klaim efektivitas terukur; efektivitas dinilai "
            "checks/status path ini.")
    return UNKNOWN_RELATION, (
        "Path ini muncul dari kondisi revenue terverifikasi; hubungan mekanismenya ke "
        "metric Goal ini belum didukung Knowledge — bukan klaim kausal.")


def build_possible_paths(
    revenue_state: Any,
    decision_spectrum: dict | None = None,
    *,
    mechanisms: dict[str, list[str]] | None = None,
    active_rules: dict[str, Any] | None = None,
    path_states: dict[str, dict] | None = None,
    goal: Any = None,
    ledger_state_of: Any = None,
) -> dict[str, Any]:
    level = (decision_spectrum or {}).get("level")
    gobj = None
    if goal is not None:
        gobj = goal if isinstance(goal, Goal) else Goal(
            **{k: v for k, v in (goal or {}).items() if k in Goal.model_fields})
        apply_goal_state_overlay(revenue_state, gobj)
    reader = RevenueSignals(revenue_state, mechanisms, active_rules, goal=gobj)
    result = build_path_set(
        revenue_space(), reader, lifecycles=lifecycles_from_states(path_states), advise=_advisory(level),
        ledger_state_of=ledger_state_of,
    )
    # A-05/A-07: every path carries its relation to the Primary Goal EXPLICITLY —
    # Goal context is not proof of relevance; without supporting Knowledge, a
    # non-revenue relation stays UNKNOWN_RELATION (int 09 §3.3/§4.2), not silently "relevant".
    relation, relation_note = _goal_relation_of(
        (gobj.resolved_metric_id() if gobj is not None else "") or "")
    for p in result.get("paths") or []:
        p["goal_relation"] = relation
        p["goal_relation_note"] = relation_note
    result["context"] = {
        "spectrum_level": level,
        "capacity_utilization": getattr(revenue_state, "capacity_utilization", None),
        "goal": goal_context_of(gobj),
    }
    if not result.get("paths"):
        _refine_goal_unresolved(result, gobj)
    result["note"] = NOTE
    result["note_i18n"] = dict(NOTE_I18N)
    return result


def path_id_of(strategy_id: str) -> str:
    return path_id_for(strategy_id)
