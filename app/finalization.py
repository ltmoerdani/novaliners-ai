"""Diagnosis label certification (int 18 §12.5, dsc.v1) — "synthesis status" ≠ "certification".

Owner decision #4 (tie-break 15 Oct 2026, implemented per the recommendation): label `final` only if ALL
conditions are met at once:
  (i) the adequacy level supporting it is genuinely "ready" (`PROVISIONAL_READY`/`DECISION_USABLE`), AND
  (ii) there is no material uncertainty that can still be answered now (critical_unknown_ids empty), AND
  (iii) the artifact's epistemic standing == SUPPORTED — `WEAK`/`INSUFFICIENT` may only be `provisional`, AND
  (iv) the decision basis is still FRESH — no material change since the block was computed
Otherwise `provisional` + **coded reasons**. Those reason codes are what make the label always
explainable and auditable (phase D reads this fact for `premature_closure_rate`, rather than
interpreting text).

Condition (i) was added in the 15 Oct 2026 hardening (audit finding P0-04): previously a `STATE_ONLY` /
`DISCOVERY_NEEDED` block that happened to have no critical unknown could be promoted to `final`.

Freshness (important, audit finding §4A): the adequacy block is computed over the snapshot of ONE
turn. What is compared is not only `state_version` (claims), but **the dimensions material to the
decision**: state, Goal (id + version), knowledge version, and decision-contract version. A Goal/KB
change that does not alter the claim fingerprint now invalidates the old assessment, and it gets its
own coded reason so it can be audited.

Reuse policy (finding 2 of the final 15 Oct 2026 deep check, stated explicitly in `_latest_assessment`):
a valid assessment **persists until its decision basis changes materially** — not "latest assessment
wins". A block from an earlier turn remains in use if the latest turn did not carry a block
(including when the provider failed), but that reuse is **flagged** (`ELIGIBILITY_CARRIED_OVER` + provenance
via `eligibility_provenance`) and **is not enough for the `final` label**: `final` is a claim to the user
now, so its basis must be the current assessment.

Deterministic, 0-LLM: purely a function of facts already computed by the engine. It never runs synthesis.
"""
from __future__ import annotations

from typing import Any, Literal

from core.reasoning.contract import LEVELS_READY

Label = Literal["final", "provisional"]

ELIGIBILITY_ABSENT = "ELIGIBILITY_ABSENT"
ELIGIBILITY_STALE = "ELIGIBILITY_STALE"                       # umbrella: a material dimension changed
ELIGIBILITY_STATE_CHANGED = "ELIGIBILITY_STATE_CHANGED"       # active claim changed (correction/new message)
ELIGIBILITY_GOAL_CHANGED = "ELIGIBILITY_GOAL_CHANGED"         # Goal changed or its version moved up
ELIGIBILITY_KNOWLEDGE_CHANGED = "ELIGIBILITY_KNOWLEDGE_CHANGED"   # knowledge base changed
ELIGIBILITY_CONTRACT_CHANGED = "ELIGIBILITY_CONTRACT_CHANGED"     # decision contract changed
ELIGIBILITY_LEVEL_NOT_READY = "ELIGIBILITY_LEVEL_NOT_READY"   # adequacy level not yet "ready" (P0-04)
ELIGIBILITY_CARRIED_OVER = "ELIGIBILITY_CARRIED_OVER"   # prior assessment reused (not the current one)
CRITICAL_UNKNOWN_OPEN = "CRITICAL_UNKNOWN_OPEN"
EVIDENCE_WEAK = "EVIDENCE_WEAK"
EVIDENCE_INSUFFICIENT = "EVIDENCE_INSUFFICIENT"


def certification(*, evidence_standing: str, eligibility: dict | None, freshness: str,
                  level: str | None = None,
                  stale_reasons: list[str] | None = None,
                  carried_over: bool = False) -> tuple[Label, list[str]]:
    """(label, reasons). `final` only if there is NO reason at all — fail-closed by construction."""
    reasons: list[str] = []
    if freshness == "absent":
        reasons.append(ELIGIBILITY_ABSENT)
    elif freshness != "fresh":
        reasons.append(ELIGIBILITY_STALE)
    for code in stale_reasons or []:            # dimension-specific reasons (state/goal/KB/contract)
        if code not in reasons:
            reasons.append(code)
    # Reuse policy (final 15 Oct deep check, finding 2): a prior assessment may be REUSED as long as
    # its decision basis has not changed, BUT that reuse is flagged and is NOT enough for the `final` label —
    # the `final` label is a claim to the user now, so its basis must be the current assessment.
    if carried_over:
        reasons.append(ELIGIBILITY_CARRIED_OVER)
    lvl = level if level is not None else (eligibility or {}).get("level")
    if lvl not in LEVELS_READY:
        reasons.append(ELIGIBILITY_LEVEL_NOT_READY)
    if list((eligibility or {}).get("critical_unknown_ids") or []):
        reasons.append(CRITICAL_UNKNOWN_OPEN)
    if evidence_standing == "INSUFFICIENT":
        reasons.append(EVIDENCE_INSUFFICIENT)
    elif evidence_standing != "SUPPORTED":
        reasons.append(EVIDENCE_WEAK)
    return ("final" if not reasons else "provisional"), reasons


def _material_dimensions(binding: dict) -> dict:
    """Binding dimensions MATERIAL to the adequacy decision (audit finding §4A, 15 Oct).

    Previously only `state_version` was compared, so a Goal or knowledge-base change that did not
    alter the active claim fingerprint never invalidated the old adequacy block."""
    return {
        "state_version": binding.get("state_version"),
        "goal_id": binding.get("goal_id"),
        "goal_version": binding.get("goal_version"),
        "knowledge": binding.get("knowledge") or {},
        "decision_contract": (binding.get("contracts") or {}).get("decision"),
    }


def _latest_assessment(s: Any) -> dict:
    """The last valid adequacy assessment + provenance + freshness of material dimensions.

    POLICY STATED HERE (final 15 Oct 2026 deep check, finding 2): **a valid assessment
    persists until its decision basis changes materially** — not "latest assessment wins".
    Therefore a block from an earlier turn remains in use when the latest turn does NOT carry a
    block (the model did not send one, the provider failed, the turn recovered without re-reasoning)
    AS LONG AS state, Goal, knowledge base, and decision contract are unchanged.

    That reuse MUST be visible, not hidden: `carried_over` + source turn (`block_turn`,
    `block_event_id`) + coded reasons (§ `eligibility_provenance`). For certification, reuse is NOT enough
    for `final` (see `certification`); for the checkpoint offer in the UI (phase C) this reuse is validly used
    with a visible marker.
    """
    from app.binding import build_binding

    log = list(getattr(s, "planner_log", None) or [])
    now = _material_dimensions(build_binding(s))
    for i in range(len(log) - 1, -1, -1):
        adaptive = (log[i] or {}).get("adaptive") or {}
        block = (adaptive.get("proposal") or {}).get("checkpoint_eligibility")
        if not block:
            continue
        recorded = _material_dimensions(adaptive.get("binding") or {})
        codes: list[str] = []
        if recorded["state_version"] != now["state_version"]:
            codes.append(ELIGIBILITY_STATE_CHANGED)
        if (recorded["goal_id"], recorded["goal_version"]) != (now["goal_id"], now["goal_version"]):
            codes.append(ELIGIBILITY_GOAL_CHANGED)
        if recorded["knowledge"] != now["knowledge"]:
            codes.append(ELIGIBILITY_KNOWLEDGE_CHANGED)
        if recorded["decision_contract"] != now["decision_contract"]:
            codes.append(ELIGIBILITY_CONTRACT_CHANGED)
        after = len(log) - 1 - i
        return {"block": block, "freshness": ("fresh" if not codes else "stale"), "codes": codes,
                "carried_over": after > 0, "block_entry": i, "block_turn": (log[i] or {}).get("turn"),
                "block_event_id": str((log[i] or {}).get("event_id") or ""),
                "entries_after": after, "entries_total": len(log)}
    return {"block": None, "freshness": "absent", "codes": [], "carried_over": False, "block_entry": None,
            "block_turn": None, "block_event_id": "", "entries_after": 0, "entries_total": len(log)}


def eligibility_freshness(s: Any) -> tuple[dict | None, str, list[str]]:
    """(adequacy block used, freshness, coded reasons). 'absent' = no block yet (mock/legacy).

    'fresh' only if ALL material dimensions are the same as when the block was computed; otherwise 'stale' + a
    dimension-specific code. Not time-based, not "already worked on". Reuse policy: see
    `_latest_assessment`."""
    rec = _latest_assessment(s)
    return rec["block"], rec["freshness"], rec["codes"]


def eligibility_provenance(s: Any) -> dict:
    """Provenance of the adequacy assessment USED right now — so that "reused from which turn" can
    be traced, not inferred (final 15 Oct 2026 deep check, finding 2).

    `carried_over=true` = the block comes from an EARLIER turn than the last reasoning entry. `block_turn`
    is the source turn number recorded in `planner_log` (stored, not recomputed),
    `block_event_id` the event id of that turn, and `entries_after` the number of entries after it.
    Old entries can be trimmed by `PLANNER_LOG_CAP`, so the only guarantee is the source while it is
    still in the trace; if the block itself is trimmed the result is 'absent' (not an invented source)."""
    rec = _latest_assessment(s)
    return {k: rec[k] for k in ("freshness", "codes", "carried_over", "block_entry", "block_turn",
                                "block_event_id", "entries_after", "entries_total")}


def last_eligibility(s: Any) -> tuple[dict | None, str]:
    """Last adequacy block + its freshness (old shape kept for existing callers/tests)."""
    block, freshness, _ = eligibility_freshness(s)
    return block, freshness


def certify_artifact(s: Any, artifact: Any) -> Any:
    """Certification is applied AFTER the artifact is computed (standing comes from synthesis, not here)."""
    rec = _latest_assessment(s)
    label, reasons = certification(evidence_standing=str(getattr(artifact, "evidence_standing", "")),
                                   eligibility=rec["block"], freshness=rec["freshness"],
                                   stale_reasons=rec["codes"], carried_over=rec["carried_over"])
    artifact.status = label
    artifact.certification_reasons = reasons
    return artifact
