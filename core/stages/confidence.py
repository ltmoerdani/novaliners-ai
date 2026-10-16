"""Two-layer confidence — PURE DETERMINISTIC, no LLM (internal-docs §5, §04 §11.1).

Layer 1: Gemini/GLM provides the structured assessment (evidence level, hypothesis map)
Layer 2: this module aggregates weight × strength → score per constraint + ranking.

The judges' answer: the demo confidence is reproducible because this layer is pure computation.
"""
from __future__ import annotations

import re
from collections import defaultdict

from core.schema.constraints import ConstraintMapEntry, HypothesisState
from core.schema.evidence import EvidenceItem, HypothesisResolution, KnowledgeActivation
from core.schema.ontology import disqualifier_entries
from core.stages.mechanisms import detect_mechanisms
from core.stages.rule_predicates import evaluate_predicate
from engine.domain_pack import (
    evidence_markers,
    has_decision_priority,
    has_experiment_priority,
    is_systemic_risk,
    material_gap_keywords,
    reversibility_weight,
    unmapped_distribution_note,
    upstream_rank,
)

# Weight per evidence level — transactional strongest, self_reported weakest
LEVEL_WEIGHT: dict[str, float] = {
    "transactional": 1.0,
    "outcome": 0.9,
    "behavioral": 0.6,
    "self_reported": 0.3,
}

CONTRADICTION_PENALTY = 0.25

# Domain upstream-ness order (iter-3 #3): tied scores → the more upstream wins
# (the root bottleneck furthest upstream). P5a (internal-docs §9): the domain prefix list is
# no longer written here — declared in ontology/domain_pack.json, resolved by
# engine/domain_pack.py (`upstream_rank`).

# P1 (eval 15 Sep): upstream ≠ most important right now. The LLM may only override
# ranking[0] when the score gap ≤ this margin. Above the margin → evidence-first wins.
TRANSPARENCY_MARGIN = 0.05

# P2 (eval 15 Sep): unknown must have consequences. A gap touching decision numbers
# (conversion, capacity, price, timeline, the reason for the target) is a MATERIAL
# gap — it lowers confidence and triggers probes, not just a log note.
# Phase J (internal-docs): the vocabulary belongs to the domain — declared in
# ontology/domain_pack.json (`material_gap_keywords`), fail-fast at load.
# The module-level name is kept so consumers (evals) do not change.
MATERIAL_GAP_KEYWORDS: tuple[str, ...] = material_gap_keywords()


def gap_consequences(evidence: list[EvidenceItem]) -> tuple[float, list[str]]:
    """P2: classify material gaps vs ordinary gaps.
    Returns: (a confidence penalty 0–0.15, the list of material-gap signals for probes).
    Deterministic: keyword match on the signal, ID/EN language."""
    probes: list[str] = []
    for e in evidence:
        if not getattr(e, "is_gap", False):
            continue
        text = (e.signal or "").lower()
        if any(k in text for k in MATERIAL_GAP_KEYWORDS):
            probes.append(e.signal)
    penalty = min(0.15, 0.05 * len(probes))
    return penalty, probes


# A2 (iter-8, internal-docs §5.2): the hard rule OBSERVED > INFERRED — inferred must not
# override observed unless its causal evidence is far stronger (the escape gap below).
STATUS_WEIGHT: dict[str, float] = {
    "OBSERVED": 1.0,
    "INFERRED": 0.85,
    "CAUSAL_HYPOTHESIS": 0.7,
    "SYSTEMIC_RISK": 0.8,
    "UNRESOLVED": 0.5,
}
STATUS_RANK: dict[str, int] = {s: i for i, s in enumerate(
    ["OBSERVED", "SYSTEMIC_RISK", "INFERRED", "CAUSAL_HYPOTHESIS", "UNRESOLVED"]
)}
INFERRED_ESCAPE_GAP = 0.15  # inferred may beat observed when its raw score leads by more than this

# Tier-2 stage 2 (iter-12): per-domain reversibility — how fast the user can change
# this constraint themselves. Used as a small multiplier on the effective score
# (full Impact & Actionability still waits for a richer Revenue State).
# P5a (internal-docs §9): the domain table MOVED to ontology/domain_pack.json — the
# `reversibility_weight(cid)` resolver (engine/domain_pack.py) reads the weights.


# Tier-1 #1 (iter-11): OBSERVED only for hard evidence that is an EVENT of
# failure — not any hard evidence whatsoever (the v4 run bug: a client's routine
# payments became evidence of a "value framing failure" → C6.3 looked OBSERVED).
#
# Phase E: the word list moved out of this module → `evidence_markers` in
# ontology/domain_pack.json. The generic layer only knows HOW to use it; the
# domain vocabulary (the user's language) stays in the pack.
def _is_event_evidence(e: EvidenceItem) -> bool:
    markers = evidence_markers()
    t = f"{getattr(e, 'signal', '') or ''} {getattr(e, 'source_quote', '') or ''}".lower()
    if any(k in t for k in markers.contrast):
        return True
    # Negation voids the marker: "tanpa telat", "tidak pernah telat",
    # "lancar, tanpa komplain" are not failure events.
    t_neg = re.sub(r"(?:tanpa|tidak pernah|tidak|nggak|gak)\s+\w+", " ", t)
    return any(k in t_neg for k in markers.event)


def _mechanism_evidence_ids(supporting_ids: list[str], evidence: list[EvidenceItem]) -> list[str]:
    """Expand the `mech:A+B` tag on supporting_ids → the detector's original evidence ids.

    Phase C (finding F4): the tag was written `f"mech:{'+'.join(sorted(m))}"` over STRING
    mechanism ids, so `sorted()` sorted CHARACTERS — the payload became
    `mech:_+c+e+e+...`. The consumer loop (`tag[5:].split("+")` → `mech_ev.get("c")`)
    therefore never found anything, and the D6 fix (iter-9) was inert.

    The expansion sits at the `constraint_status` caller (not only inside
    `score_hypotheses`) so the status is identical on EVERY path — ranking, `constraint_map`,
    `split_confidences`, `diagnosis`. Previously only ranking expanded it, so artifacts could
    display a status different from the one that actually determined the score.
    """
    mech_ev: dict[str, list[str]] = {}
    extra: list[str] = []
    for tag in supporting_ids:
        if isinstance(tag, str) and tag.startswith("mech:"):
            if not mech_ev:
                mech_ev = detect_mechanisms(evidence)  # computed once, only when needed
            for mid in tag[5:].split("+"):
                extra.extend(mech_ev.get(mid, []))
    return extra


def constraint_status(
    cid: str,
    supporting_ids: list[str],
    evidence: list[EvidenceItem],
    revenue_state=None,
) -> str:
    """A1: the deterministic epistemic status from evidence composition + state.
    - OBSERVED: transactional/outcome evidence that is an EVENT
      (loss/stall/delay/reject/ghost) or a natural historical contrast
    - INFERRED: only behavioral/self-reported evidence, OR hard evidence that is
      not an event (e.g. routine payments, client counts) — a "state" status
    - CAUSAL_HYPOTHESIS: no direct evidence (mechanism-only)
    - SYSTEMIC_RISK: a constraint in a pack-declared domain (systemic_risk)
      while state shows capacity stuck vs a gap
    - UNRESOLVED: no evidence at all"""
    ev_by_id = {e.id: e for e in evidence}
    ids = supporting_ids + _mechanism_evidence_ids(supporting_ids, evidence)
    real = [ev_by_id[i] for i in ids if i in ev_by_id]
    real = [e for e in real if not getattr(e, "is_gap", False)]
    if not real:
        # P5a (internal-docs §9 / internal-docs §3.4 S1): domain + state =
        # a pack declaration (ontology/domain_pack.json → engine/domain_pack.py),
        # not `cid.startswith("L8")` in the engine layer.
        if is_systemic_risk(cid, revenue_state):
            return "SYSTEMIC_RISK"
        return "UNRESOLVED"
    hard = [e for e in real if e.level in ("transactional", "outcome")]
    if any(_is_event_evidence(e) for e in hard):
        return "OBSERVED"
    return "INFERRED"


def score_hypotheses(
    evidence_map: dict[str, list[str]],  # constraint_id -> [evidence_id]
    evidence: list[EvidenceItem],
    mech_boost: dict[str, set[str]] | None = None,  # D: mechanism → constraint
    mech_weights: dict[str, float] | None = None,    # D: bobot bonus per constraint
) -> list[HypothesisState]:
    """Deterministic aggregation: score(c) = Σ w(e) for e supporting c,
    minus the contradiction penalty (evidence supporting other constraints in a different domain).
    D (internal-docs §2): constraints supported by a detected mechanism cluster
    get a mechanism score (0.15 × the number of EVIDENCE per mechanism, cap +0.4; across
    mechanisms the LARGEST weight wins — see mechanism_boost) — evidence→mechanism→constraint,
    not just the LLM's claim map."""
    ev_by_id = {e.id: e for e in evidence}

    # iter-16 (Batch A — ACH diagnosticity, Heuer): evidence supporting MANY
    # constraints at once is NON-DIAGNOSTIC — its weight drops. This stops
    # 'no outreach' from inflating DS4.2+DM5.1+L8.3 simultaneously.
    ev_usage: dict[str, int] = defaultdict(int)
    for _ids in evidence_map.values():
        for _eid in _ids:
            ev_usage[_eid] += 1

    def _diag_w(ev_id: str) -> float:
        n = ev_usage.get(ev_id, 1)
        return 1.0 if n <= 1 else (0.6 if n == 2 else 0.4)

    # total evidence per constraint — is_gap evidence (missing data) does NOT enter scoring:
    # a gap is context, not convergent evidence (fix iter-3 #2)
    scores: dict[str, float] = defaultdict(float)
    supporting: dict[str, list[str]] = defaultdict(list)

    for cid, ev_ids in evidence_map.items():
        for ev_id in ev_ids:
            ev = ev_by_id.get(ev_id)
            if ev is None or getattr(ev, "is_gap", False):
                continue
            scores[cid] += LEVEL_WEIGHT.get(ev.level, 0.3) * _diag_w(ev_id)
            supporting[cid].append(ev_id)

    # D: mechanism boost — added AFTER normalization (cap +0.4) so it is not
    # diluted by the growing count of supporting pseudo-evidence.
    # Mechanism-only constraints (not LLM-mapped) still enter the ranking from here.
    # Phase A (F5): `sorted(...)` is MANDATORY — previously `set(...)` made the iteration
    # order depend on PYTHONHASHSEED, so results differed across processes (violating
    # the "PURE DETERMINISTIC" claim in this module's docstring).
    all_cids = sorted(set(scores) | set(mech_boost or {}))
    ranking: list[HypothesisState] = []
    for cid in all_cids:
        raw = scores.get(cid, 0.0)
        real_ids = supporting.get(cid, [])
        n_real = len(real_ids)
        real_raw = sum(
            LEVEL_WEIGHT.get(ev_by_id[i].level, 0.3) * _diag_w(i)
            for i in real_ids if i in ev_by_id
        ) if real_ids else 0.0
        base = 0.0
        if n_real:
            # iter-6: convergence beats the average. 8 behavioral evidence items must count
            # more than 1 behavioral item (run Rina: C6.4 scored 1.00 from 3 items
            # = an artifact of the averaging formula). Components: level quality (45%),
            # hard transactional/outcome evidence (35%, cap 2), evidence volume (20%, cap 4).
            mean_level = real_raw / n_real
            n_hard = sum(
                1 for i in real_ids
                if i in ev_by_id and ev_by_id[i].level in ("transactional", "outcome")
            )
            base = min(
                1.0,
                0.45 * mean_level
                + 0.35 * min(1.0, n_hard / 2.0)
                + 0.20 * min(1.0, n_real / 4.0),
            )
        # E4 (iter-7, internal-docs §4.4): the mechanism bonus is SCALED, not fully stacked —
        # preventing a 1.00 score through the back door when base is already high
        # (run Rina v2: C6.4 = 1.00 from high base + the cap bonus).
        bonus = min(0.4, (mech_weights or {}).get(cid, 0.0))
        norm = min(1.0, base * 0.75 + bonus * 0.5)
        # iter-16 (Batch A): three separate dimensions — Evidence Strength / Diagnostic
        # Fit / Decision Relevance. Phase A (finding F5): the first two MUST be
        # computed HERE, where `base`/`real_ids` belong to this constraint. Previously
        # both were assigned in the second loop — there `base`/`real_ids` were the leftovers
        # of the first loop's last iteration, so EVERY hypothesis inherited one constraint's
        # values (in the artifact: identical evidence_strength everywhere), and because
        # `all_cids` used to be a `set`, the values changed across processes.
        diag_fit = 0.0
        if real_ids:
            unique = sum(1 for i in real_ids if ev_usage.get(i, 1) <= 1)
            diag_fit = round(unique / len(real_ids), 3)
        # Fase C (F4): ONE tag `mech:id1+id2`, payload = the ORIGINAL mechanism id. The
        # consumer (`_mechanism_evidence_ids`) splits it with `split("+")` then looks up each
        # id in the detector's result; previously one tag per CHARACTER was built, so
        # mechanism evidence expansion never worked.
        mech_ids = sorted((mech_boost or {}).get(cid, ()))
        mech_tags = [f"mech:{'+'.join(mech_ids)}"] if mech_ids else []
        ranking.append(
            HypothesisState(
                constraint_id=cid,
                score=round(norm, 3),
                supporting_evidence_ids=real_ids + mech_tags,
                evidence_strength=round(base, 3),
                diagnostic_fit=diag_fit,
            )
        )
    # A2: the epistemic status is computed BEFORE the sort — then the final score = raw score ×
    # status-weight, with an escape clause: inferred may win when its raw score leads
    # by more than INFERRED_ESCAPE_GAP over the best observed (its causal evidence is far stronger).
    # D6 (iter-9, fix collapse run v5): a constraint whose support comes from a
    # MECHANISM (tag 'mech:') must be judged with the real evidence of that mechanism —
    # without this everything falls to UNRESOLVED (weight 0.5) and the score is cut in half
    # (run v5: 3 constraints tied at 15%, no PRIMARY).
    # Fase C: tag expansion now lives INSIDE `constraint_status` (one place) so that
    # `constraint_map`, `split_confidences`, and `diagnosis` see the same status.
    statuses: dict[str, str] = {}
    for h in ranking:
        statuses[h.constraint_id] = constraint_status(
            h.constraint_id, h.supporting_evidence_ids, evidence
        )
    top_observed_raw = max(
        (h.score for h in ranking if statuses[h.constraint_id] == "OBSERVED"), default=0.0
    )
    final: list[tuple[HypothesisState, float]] = []
    for h in ranking:
        st = statuses[h.constraint_id]
        raw = h.score
        if st == "INFERRED" and top_observed_raw > 0 and raw <= top_observed_raw + INFERRED_ESCAPE_GAP:
            eff = raw * STATUS_WEIGHT["INFERRED"]
        else:
            eff = raw * STATUS_WEIGHT.get(st, 1.0)
        # Tier-2 stage 2 (iter-12): two additional deterministic factors.
        # - REVERSIBILITY: a constraint that can be fixed quickly is a better candidate
        #   as the driver of the first action (structural/slow domains weigh less;
        #   per-domain weights live in ontology/domain_pack.json).
        # - DIAGNOSTIC_VALUE: a constraint with evidence from MULTIPLE levels
        #   (behavioral + hard) is more informative to test — a small bonus.
        eff *= reversibility_weight(h.constraint_id)
        _levels = {ev_by_id[i].level for i in h.supporting_evidence_ids if i in ev_by_id}
        if len(_levels) >= 2:
            eff *= 1.03
        h.effective_score = round(min(1.0, eff), 3)
        # iter-16 (Batch A): three separate dimensions — Evidence Strength /
        # Diagnostic Fit / Decision Relevance. One effective number is not
        # enough to explain why a constraint wins.
        # Fase A (F5): evidence_strength & diagnostic_fit are computed in the FIRST loop,
        # where `base`/`real_ids` belong to this constraint (previously here = stale values).
        h.decision_relevance = round(
            reversibility_weight(h.constraint_id)
            * (1.0 if has_decision_priority(h.constraint_id) else 0.8),
            3,
        )
        final.append((h, eff))
    final.sort(
        key=lambda x: (
            -x[1],
            STATUS_RANK.get(statuses[x[0].constraint_id], 9),
            upstream_rank(x[0].constraint_id),
            # Fase A (F5): an explicit tiebreaker. Without it, constraints TIED on
            # all three keys above are ordered by set-iteration order → not
            # stable across processes. PRIMARY/top order could shift on its own.
            x[0].constraint_id,
        )
    )
    ranking = [h for h, _ in final]
    return ranking


def overall_confidence(ranking: list[HypothesisState], evidence: list[EvidenceItem] | None = None) -> float:
    """Main diagnosis confidence: the top hypothesis's score minus the gap to the runner-up.
    A small gap = hypotheses compete = less certain.

    Guard iter-6 #2: confidence 1.0 is epistemically impossible for a business diagnosis.
    - Absolute cap 0.95.
    - If NONE of the top hypothesis's supporting evidence is transactional/outcome → cap 0.6
      (evidence that is all 'a person talking about themselves' cannot yield 100% certainty).
    """
    if not ranking:
        return 0.0

    # Fix (iter-20c): the ranking is ordered by the EFFECTIVE score (knowledge
    # consequences can reorder it), while `.score` is the raw score.
    # The old code assumed ranking[0].score >= ranking[1].score — that assumption
    # collapsed once rule consequences ran, producing a NEGATIVE separation
    # (real S1 regression: ranking[0].score 0.571 < ranking[1].score 0.595 →
    # separation -0.048 → confidence wrongly dropped).
    # Now: take the top two by EFFECTIVE score (the one that actually determines
    # the diagnosis) and keep the separation from ever going negative.
    def _eff(h: HypothesisState) -> float:
        return h.effective_score if h.effective_score is not None else h.score

    eff = sorted((_eff(h) for h in ranking), reverse=True)
    top = eff[0]
    second = eff[1] if len(eff) > 1 else 0.0
    separation = max(0.0, min(1.0, (top - second) * 2))  # gap 0.5+ → full separation
    conf = top * 0.7 + separation * 0.3

    if evidence is not None:
        ev_by_id = {e.id: e for e in evidence}
        supporting = [ev_by_id[i] for i in ranking[0].supporting_evidence_ids if i in ev_by_id]
        hard = [e for e in supporting if not getattr(e, "is_gap", False)
                and e.level in ("transactional", "outcome")]
        if supporting and not hard:
            conf = min(conf, 0.6)
        # If most of the supporting evidence is self_reported → proportional penalty
        elif supporting:
            weak = [e for e in supporting if e.level == "self_reported"]
            weak_ratio = len(weak) / len(supporting)
            if weak_ratio >= 0.5:
                conf *= (1.0 - 0.3 * (weak_ratio - 0.5) * 2)  # up to -30% when all self_reported

    # P2: material gaps lower confidence — unknown has consequences.
    if evidence is not None:
        gap_penalty, _ = gap_consequences(evidence)
        conf = max(0.0, conf - gap_penalty)

    return round(min(conf, 0.95), 3)


def applied_knowledge_rules(
    ranking: list[HypothesisState],
    evidence: list[EvidenceItem] | None = None,
) -> list[str]:
    """DEPRECATED (internal-docs §8.4 T3) — DO NOT USE.

    This function attributes rule IDs (TM-R01/R07/R04) from a STATISTICAL PROXY of
    evidence levels, not from the rule's actual condition. A measurable failure:
    TM-R04 ("implication = zero") was reported active on a case that in fact
    quantified the implication (Rp8jt, 3–6 month runway).

    Replacement: `core.stages.knowledge_rules.run_knowledge_rules()` — evaluates
    the actual condition (tier-1 predicate / tier-2 LLM) with mandatory citation.

    Kept temporarily only so old imports do not crash; it always returns
    an empty list so NO fake attribution leaks.
    """
    return []


# ---------------------------------------------------------------------------
# P1 — Reasoning trace builders (internal-docs §2.10). Deterministic, 0 LLM.
# ---------------------------------------------------------------------------

def knowledge_activation_log(
    rows: list[dict],
) -> list["KnowledgeActivation"]:
    """KnowledgeActivation from the MATCH RESULTS (internal-docs §8.4 T3) — full provenance:
    rule_id → book/chapter → rationale → citation of this case's evidence.

    `rows` = [{"rule_id", "applied_to", "tier", "reason"}]. Only rules that were
    actually evaluated & matched may appear. No "compiled guard" fallback —
    the proxy-attribution path has been removed.
    """
    from core.schema.evidence import KnowledgeActivation  # noqa: F401  (explicit documentation)
    out: list[KnowledgeActivation] = []
    try:
        from engine.knowledge import get_kb
        kb = get_kb()
    except Exception:
        kb = {}
    for row in rows:
        rid = row.get("rule_id") or ""
        if not rid:
            continue
        rule = kb.get("rules", {}).get(rid)
        if not rule:
            continue  # not in the KB = not claimed (previously: an "internal" fallback)
        cons = rule.get("consequence", {})
        out.append(KnowledgeActivation(
            item_id=rid,
            source=rule.get("provenance", {}).get("source_id", "internal"),
            principle=cons.get("rationale", ""),
            confidence_impact=cons.get("action", "NEUTRAL"),
            applied_to=(row.get("applied_to") or "")[:200],
            decision_effect=f"tier={row.get('tier', '?')} → {cons.get('action', 'NEUTRAL')} "
                            f"pada {', '.join(cons.get('targets', []))}",
        ))
    return out


def hypothesis_resolution_trace(
    ranking: list[HypothesisState],
    evidence: list[EvidenceItem],
    final_id: str,
    llm_pick: str | None = None,
    arbitration: str | None = None,  # "agree" | "transparency" | "veto" | None
) -> "HypothesisResolution | None":
    """Why the final decision wins & why the runner-up loses — from deterministic numbers.
    `final_id` = the FINAL decision (after arbitration), not always ranking[0]."""
    from core.schema.evidence import HypothesisResolution  # noqa: F401  (explicit documentation)
    if not ranking:
        return None
    ev_by_id = {e.id: e for e in evidence}

    def _hard_count(h: HypothesisState) -> int:
        return sum(
            1 for i in h.supporting_evidence_ids
            if (e := ev_by_id.get(i)) and not e.is_gap and e.level in ("transactional", "outcome")
        )

    final = next((h for h in ranking if h.constraint_id == final_id), ranking[0])
    n_ev = sum(1 for i in final.supporting_evidence_ids
               if (e := ev_by_id.get(i)) and not e.is_gap)
    reason = (
        f"Skor tertimbang {final.score:.2f} (evidence level-weighted), "
        f"{n_ev} bukti pendukung non-gap ({_hard_count(final)} hard: transactional/outcome), "
        f"upstream rank {upstream_rank(final.constraint_id)} (lebih upstream menang saat skor seri)."
    )
    if arbitration == "veto":
        reason = f"ENGINE VETO: LLM memilih {llm_pick}, bukti mendukung {final_id}. {reason}"
    elif arbitration == "transparency":
        top = ranking[0]
        reason = (
            f"Pilihan diagnostisiawan ({final_id}) dipertahankan — selisih skor terhadap "
            f"ranking[0] dalam margin toleransi ({TRANSPARENCY_MARGIN}), keduanya kompatibel "
            f"dengan bukti. Catatan: bukti tertimbang tertinggi sebenarnya {top.constraint_id} "
            f"({top.score:.2f}). {reason}"
        )

    runner_up = []
    for h in ranking[:4]:
        if h.constraint_id == final_id:
            continue
        why = f"Skor {h.score:.2f} (vs final {_round(final.score)}), {_hard_count(h)} hard evidence."
        if arbitration == "transparency" and h.constraint_id == ranking[0].constraint_id:
            why += " Skor tertinggi menurut engine — pantau saat reassess."
        runner_up.append({"constraint_id": h.constraint_id, "why_lower": why})
    return HypothesisResolution(
        winner={"constraint_id": final.constraint_id, "reason": reason},
        runner_up=runner_up,
    )


def _round(x: float) -> str:
    return f"{x:.2f}"


# ---------------------------------------------------------------------------
# D — Mechanism layer & Constraint Map (internal-docs §2)
# ---------------------------------------------------------------------------

def mechanism_boost(
    evidence_map: dict[str, list[str]],
    evidence: list[EvidenceItem],
) -> tuple[dict[str, set[str]], dict[str, float]]:
    """Evidence→Mechanism→Constraint: constraints supported by a DETECTED MECHANISM
    (not just an LLM claim) get a score bonus from the mechanism cluster.
    Return: (constraint_id -> set(mechanism_id), constraint_id -> bonus weight 0-0.4)."""
    from core.stages.mechanisms import MECHANISMS, detect_mechanisms
    mech_ev = detect_mechanisms(evidence)
    boost: dict[str, set[str]] = {}
    mech_weights: dict[str, float] = {}
    for mech_id, ev_ids in mech_ev.items():
        # A mechanism is valid when at least 1 of its evidence items is also LLM-mapped
        # to a constraint in that mechanism cluster (two-source convergence), OR >=2
        # mechanism-only evidence items (a repeated signal).
        cluster = set(MECHANISMS[mech_id]["constraints"])
        llm_mapped = any(cid in cluster for cid in evidence_map)
        if not llm_mapped and len(ev_ids) < 2:
            continue
        # Weight proportional to evidence count: 1 item 0.15, 2 items 0.30, ≥3 items 0.40 (cap)
        weight = min(0.4, 0.15 * len(ev_ids))
        for cid in cluster:
            if cid in evidence_map or len(ev_ids) >= 2:
                boost.setdefault(cid, set()).add(mech_id)
                mech_weights.setdefault(cid, 0.0)
                mech_weights[cid] = max(mech_weights.get(cid, 0.0), weight)
    return boost, mech_weights


def disqualifier_check(
    constraint_id: str,
    ontology: dict,
    evidence: list[EvidenceItem],
) -> str | None:
    """Disqualifying signals (internal-docs §4): signals that CANCEL a constraint.

    Phase E (ontology v0.3): the rules are now DECLARATIVE in ontology/constraints.json,
    evaluated with the same generic predicate language as KB rules
    (`core/stages/rule_predicates.py`, including the mandatory-citation rules). The generic
    layer no longer knows any specific constraint — previously this lived as
    `if constraint_id == "DM5.5"` here, while its declarative prose bound nothing
    and one of its clauses never ran.

    `executable: false` entries are EXPLICITLY SKIPPED (not treated as active), so a
    declaration that cannot be executed yet does not masquerade as a working rule.
    """
    body = ontology["constraints"].get(constraint_id, {})
    for dq in disqualifier_entries(body):
        if not dq.executable:
            continue
        matched, _cited, _reason = evaluate_predicate(dq.predicate or {}, evidence)
        if matched:
            return dq.note
    return None


def build_constraint_map(
    ranking: list[HypothesisState],
    evidence: list[EvidenceItem],
    ontology: dict,
    revenue_state=None,
) -> list["ConstraintMapEntry"]:
    """Ranking → tiered Constraint Map (internal-docs §2):
    PRIMARY ≥0.6 · SECONDARY ≥0.4 · UNPROVEN <0.4 · UNKNOWN = a constraint
    that has not been probed at all."""
    from core.schema.constraints import TIER_THRESHOLDS, ConstraintMapEntry
    out: list[ConstraintMapEntry] = []
    for i, h in enumerate(ranking):
        # iter-6 (internal-docs §4.4 finding #2): ONLY ONE PRIMARY — the ranking must answer
        # "which constraint drives the next action", not "which ones are true".
        if i == 0 and h.score >= TIER_THRESHOLDS["SECONDARY"]:
            tier = "PRIMARY"
        elif i == 0:
            tier = "UNPROVEN"
        elif h.score >= TIER_THRESHOLDS["CONTRIBUTING"]:
            tier = "CONTRIBUTING"
        elif h.score >= TIER_THRESHOLDS["SECONDARY"]:
            tier = "SECONDARY"
        else:
            tier = "UNPROVEN"
        note = disqualifier_check(h.constraint_id, ontology, evidence) or ""
        name = ontology["constraints"].get(h.constraint_id, {}).get("name", h.constraint_id)
        status = constraint_status(h.constraint_id, h.supporting_evidence_ids, evidence, revenue_state)
        out.append(ConstraintMapEntry(
            constraint_id=h.constraint_id, name=name, tier=tier, status=status,
            score=h.score, supporting_evidence_ids=h.supporting_evidence_ids, note=note,
            effective_score=h.effective_score,
            evidence_strength=h.evidence_strength, diagnostic_fit=h.diagnostic_fit,
            decision_relevance=h.decision_relevance,
        ))
    # UNKNOWN: ontology constraints that never appear in the ranking at all
    ranked = {h.constraint_id for h in ranking}
    # E5 (iter-7, internal-docs §4.4): evidence EXISTS but the LLM mapping dropped it → not
    # "unprobed" UNKNOWN. Detect the distribution from evidence signals; DS4.* gets an honest label.
    ev_texts = " ".join((getattr(e, "signal", "") or "").lower() for e in evidence)
    # Phase J: the channel vocabulary + the note-issuing domain are declared in the pack
    # (`unmapped_distribution_note`) — the engine only knows how to use them.
    _udn = unmapped_distribution_note()
    has_distribution_evidence = any(k in ev_texts for k in _udn.signals)
    _udn_prefixes = tuple(_udn.applies_to_constraint_domains)
    for cid, c in ontology["constraints"].items():
        if cid not in ranked:
            note = "Belum ter-probe — tidak ada bukti apapun arah ini"
            if cid.startswith(_udn_prefixes) and has_distribution_evidence:
                note = (
                    "Bukti distribusi ADA (inquiry/channel terlihat di evidence) tapi tidak ter-mapping "
                    "ke constraint ini oleh diagnostisiawan — cek saat reassess, "
                    "jangan dianggap belum ter-probe"
                )
            out.append(ConstraintMapEntry(
                constraint_id=cid, name=c.get("name", cid), tier="UNKNOWN", score=0.0,
                status="UNRESOLVED",
                note=note,
            ))
    return out


# ---------------------------------------------------------------------------
# iter-14: Split confidence — Constraint ≠ Diagnosis ≠ Revenue Impact.
# C6.4 can carry high confidence as an OBSERVED leakage, while the belief that
# fixing it moves revenue to the target is far lower
# (demand/capacity/pricing still UNKNOWN). Three numbers, three different claims.
# ---------------------------------------------------------------------------

# F7: an IMPACT-certainty ceiling while there is no measured effect evidence yet.
#
# `revenue_impact_confidence` is a CAUSAL claim ("fixing X moves revenue").
# Estimating an effect needs past outcomes or an explicit causal mechanism — not
# a more complete case description. Research: GRADE judges certainty of EFFECT ESTIMATES
# through the effect-evidence domains (bias, indirectness, imprecision), not case-description
# completeness; the Overconfidence effect (Oskamp 1965) — more case info → confidence
# 33%→53% while accuracy stays <30%.
#
# There is no effect-evidence source yet (Outcome Learning Store,
# internal-docs §15 P9), so the ceiling stays low. Raise it ONLY when effect
# evidence actually exists — NOT when the state gets more complete.
IMPACT_CAP_NO_EFFECT_EVIDENCE = 0.45


def split_confidences(
    ranking: list[HypothesisState],
    evidence: list[EvidenceItem],
    revenue_state=None,
    diagnosis_confidence: float | None = None,
) -> dict[str, float]:
    """Return {constraint, diagnosis, revenue_impact, decision, experiment}_confidence.
    Deterministic, 0 LLM.
    - constraint_confidence : how certain the main constraint REALLY EXISTS (the hard/
      behavioral composition of top-1), also bounded by state completeness — a clearer
      state makes the constraint more readable.
    - diagnosis_confidence  : the overall number already in use (ranking + gap +
      penalty). Passed in from synthesize to stay consistent with what is displayed.
    - revenue_impact_confidence : how certain FIXING this constraint moves revenue
      significantly. A CAUSAL claim → its basis is evidence about EFFECTS; bounded by a
      structural ceiling while there is no measured effect evidence. Only MATERIAL gaps
      (information that could flip the diagnosis) discount it. State completeness NO
      longer enters here — see F7 + IMPACT_CAP_NO_EFFECT_EVIDENCE above.
    """
    # Phase B: `RevenueState` (domain, core.schema.state) is NO LONGER imported here —
    # that type is domain-specific; `revenue_state` is accepted duck-typed until the
    # DomainPack protocol (F1) provides it via the pack.

    if not ranking:
        return {"constraint_confidence": 0.0,
                "diagnosis_confidence": 0.0,
                "revenue_impact_confidence": 0.0}

    ev_by_id = {e.id: e for e in evidence}
    supporting = [ev_by_id[i] for i in ranking[0].supporting_evidence_ids if i in ev_by_id]
    hard = [e for e in supporting if not getattr(e, "is_gap", False)
            and e.level in ("transactional", "outcome")]
    # constraint exists: hard event evidence → high; behavioral → medium;
    # self_reported only → low.
    n_hard = len(hard)
    n_behavioral = sum(1 for e in supporting if e.level == "behavioral")
    constraint_conf = min(0.95, 0.30 + 0.25 * min(2, n_hard) + 0.08 * min(3, n_behavioral))
    if not supporting:
        constraint_conf = 0.0
    # iter-15 (P1 user §7): top-1 status is not OBSERVED → cap 0.6 — being 'sure the
    # condition exists' must not equal the status of a directly observed event.
    if supporting:
        st = constraint_status(ranking[0].constraint_id, ranking[0].supporting_evidence_ids, evidence)
        if st != "OBSERVED":
            constraint_conf = min(constraint_conf, 0.6)

    diag_conf = (
        diagnosis_confidence
        if diagnosis_confidence is not None
        else overall_confidence(ranking, evidence)
    )

    # --- F7: TWO UNCERTAINTY SOURCES WITH DIFFERENT OBJECTS ------------------
    # (1) STATE completeness = how CLEAR the situation is. This is about whether
    #     the constraint is readable → it lowers the certainty capacity of the CONSTRAINT,
    #     not the IMPACT certainty. Previously all four fields were discounted into `impact`,
    #     so more complete case info raised effect certainty with no basis
    #     (the overconfidence pattern).
    rs = revenue_state
    state_unknowns = 0
    if rs is not None:
        state_unknowns += getattr(rs, "demand_sufficiency", "UNKNOWN") == "UNKNOWN"
        state_unknowns += getattr(rs, "pricing_architecture", "UNKNOWN") == "UNKNOWN"
        state_unknowns += getattr(rs, "response_latency_days", None) is None
        state_unknowns += getattr(rs, "acquisition_hours_per_week", None) is None
    if state_unknowns:
        constraint_conf = min(constraint_conf, max(0.30, 0.95 - 0.15 * state_unknowns))

    # (2) A MATERIAL gap = missing information that could FLIP the diagnosis. It still
    #     discounts `impact`: a diagnosis that could flip changes the expected effect
    #     (causal inference: the effect = the outcome response when the cause is changed).
    gap_penalty, _probes = gap_consequences(evidence)
    gap_unknowns = round(gap_penalty / 0.05)  # number of material probes
    impact = max(
        0.05,
        min(IMPACT_CAP_NO_EFFECT_EVIDENCE, diag_conf) * (0.85 ** min(8, gap_unknowns)),
    )
    # iter-16 (Batch B — VoI/Howard 1966): the diagnosis may be very uncertain, yet
    # the 'gather information first' decision can still be very confident — because
    # the Value of Information from a small probe exceeds the EV of executing the
    # full plan under high uncertainty.
    decision_conf = 0.5
    if rs is not None:
        if getattr(rs, "capacity_utilization", None) is not None:
            decision_conf += 0.1  # a computed boundary exists — a more informed decision
        if getattr(rs, "demand_sufficiency", "UNKNOWN") != "UNKNOWN":
            decision_conf += 0.1
        if getattr(rs, "avg_deal_size", None) is not None:
            decision_conf += 0.1
    decision_conf = min(0.9, decision_conf)
    # experiment confidence: p(the probe can be executed & yields information
    # whatever the outcome) — from reversibility + a small scope
    top_dom_experiment = has_experiment_priority(ranking[0].constraint_id)
    experiment_conf = 0.45 + 0.25 * top_dom_experiment + 0.1 * (decision_conf >= 0.6)
    return {
        "constraint_confidence": round(min(0.95, constraint_conf), 3),
        "diagnosis_confidence": round(diag_conf, 3),
        "revenue_impact_confidence": round(min(0.9, impact), 3),
        "decision_confidence": round(decision_conf, 3),
        "experiment_confidence": round(min(0.9, experiment_conf), 3),
    }
