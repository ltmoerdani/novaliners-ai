"""Agent: Diagnosis Synthesis (S6) — ONE LLM call (campaign-forge pattern:
single-call structured generation prevents angle drift between artifact blocks).

The LLM produces the narrative draft; confidence, contraindications & hypothesis ranking
are computed deterministically (engine.confidence + ontology lookup) — reproducible for demo.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

from core.schema.evidence import (  # F3+/exhaust the shim: direct import
    EvidenceActivation,
    EvidenceItem,
    ReasoningTrace,
)
from core.stages.confidence import (
    TRANSPARENCY_MARGIN,
    build_constraint_map,
    constraint_status,
    disqualifier_check,
    gap_consequences,
    hypothesis_resolution_trace,
    knowledge_activation_log,
    mechanism_boost,
    overall_confidence,
    score_hypotheses,
    split_confidences,
    upstream_rank,
)
from core.stages.knowledge_rules import apply_rule_consequences, run_knowledge_rules
from core.stages.mechanisms import MECHANISMS, detect_mechanisms
from core.stages.spectrum import decide_spectrum
from domains.revenue.guards.nba_grounding import guard_nba_grounding
from domains.revenue.navigation.paths import build_possible_paths
from domains.revenue.projection.view import apply_view as _apply_view  # M4: satu derivasi state
from domains.revenue.prompts.copilot_and_journey import journey_prompt_block  # audit 25 Sep
from domains.revenue.schema.artifact import ActionItem, DiagnosisArtifact, day_texts
from domains.revenue.stages.causal import build_causal_hypothesis
from domains.revenue.stages.dedup import deduplicate_evidence
from domains.revenue.stages.journey import (
    demote_interventions,
    infer_e2e_phases,
)
from domains.revenue.stages.opportunities import (
    FUNNEL_STAGES,
    build_opportunities,
    cluster_by_topic,
)
from domains.revenue.stages.state import build_revenue_state
from domains.revenue.stages.validate import validate_state
from engine.knowledge import code_commit_hash, interventions_for, kb_sha256
from providers.base import LLMProvider, schema_hint

ONTOLOGY = json.loads((Path(__file__).resolve().parents[1] / "ontology" / "constraints.json").read_text())


_EM_DASH = re.compile(r"\s*[—–]\s*")


def _strip_em_dash(text: str) -> str:
    """Safety net: the em-dash ban is enforced mechanically (the SYSTEM prompt
    alone does not guarantee it). 'X — Y' becomes 'X, Y' so sentences still flow."""
    if not text:
        return text
    out = _EM_DASH.sub(", ", text)
    return re.sub(r",{2,}", ",", out)


def _humanize_draft(draft: DiagnosisDraft) -> DiagnosisDraft:
    """Apply the humanized tone mechanically: strip em dashes from every string field."""
    for fname in ("where_you_are", "primary_constraint", "do_not", "next_best_action",
                  "first_step_today", "outreach_script", "success_metric",
                  "well_know_when", "pivot_rule", "engine_disagreement"):
        val = getattr(draft, fname, None)
        if isinstance(val, str) and val:
            setattr(draft, fname, _strip_em_dash(val))
    draft.secondary_constraints = [_strip_em_dash(s) for s in draft.secondary_constraints]
    draft.why = [_strip_em_dash(s) for s in draft.why]
    draft.day_by_day = [
        it.model_copy(update={"text": _strip_em_dash(it.text)}) for it in draft.day_by_day
    ]
    return draft


# E3 (iter-7, internal-docs §4.4): causal inference about the user's MENTAL STATE from
# historical self-reported/selection-biased evidence must not pass as fact.
# Rina v2 run: "a 60% win rate shows the fear of misreading scope is unfounded" —
# 6/10 historical cases prove proposal-stage CAN convert, not that the fear is irrational.
_CAUSAL_MARKERS = (
    "menunjukkan bahwa", "membuktikan", "berarti", "berarti bahwa",
    "menandakan", "bukti bahwa", "buktinya",
)
_MENTAL_STATE_MARKERS = ("takut", "khawatir", "ragu", "tidak percaya diri", "yakin", "fear")
_E3_TAG = " (asumsi — bukti historis terbatas/selection-biased, belum mengisolasi penyebab)"


def _guard_causal_narrative(draft: DiagnosisDraft) -> DiagnosisDraft:
    """Deterministic: Why sentences that draw a cause-effect conclusion (especially about
    the user's mental state) from weak evidence are explicitly tagged as an assumption."""
    guarded = []
    for w in draft.why:
        lw = (w or "").lower()
        is_causal = any(m in lw for m in _CAUSAL_MARKERS)
        is_mental = any(m in lw for m in _MENTAL_STATE_MARKERS)
        if (is_causal and is_mental) or ("membuktikan" in lw or "bukti bahwa" in lw):
            if _E3_TAG.strip(" ()").split(" ")[0] not in lw:
                w = w.rstrip(".") + "." + _E3_TAG
        guarded.append(w)
    draft.why = guarded
    return draft


def _resolve_evidence_map(
    evidence_map: dict[str, list[str]], evidence: list[EvidenceItem]
) -> dict[str, list[str]]:
    """Fuzzy-resolve evidence ids from the LLM to the real ledger ids.
    The LLM often echoes its own conventions (ev-GOAL-1) — resolve case-insensitively,
    then fall back to safe exact/partial matches; the rest is dropped.

    Inverted-map fix (iter-7 testing v3, Rina v3 run): the LLM sometimes flips the structure —
    KEYS = evidence_id (ev-goal-007), VALUES = list of constraints/strings. Without validation,
    keys become fake constraint_ids → ranking, veto, constraint map, causal hypothesis
    all display 'ev-goal-007' as a constraint. Validation:
    (1) keys MUST be ontology constraint ids; invalid keys are dropped.
    (2) If most keys are invalid but the values match constraint ids → the map is inverted:
    swap key/value, then re-resolve."""
    valid_keys = set(ONTOLOGY["constraints"].keys())
    real_ids = {e.id for e in evidence}
    lower_map = {rid.lower(): rid for rid in real_ids}

    # iter-8 regression fix (S1 0.635->0.17): strict validation dropped loose keys
    # ("C6.3 Value Framing Failure", "c6.3", "C6.3 ") that the LLM uses routinely.
    # Normalization: extract the constraint id from the key via regex — any format
    # that contains a valid id passes; only keys without any id at all
    # get dropped / treated as inverted-map candidates.
    _CID_RE = re.compile(r"(D1|V2|M3|DS4|DM5|C6|R7|L8)\s*\.\s*(\d)", re.I)

    def _norm_cid(k: str) -> str | None:
        if k in valid_keys:
            return k
        m = _CID_RE.search(k)
        cid = f"{m.group(1).upper()}.{m.group(2)}" if m else None
        return cid if cid in valid_keys else None

    # Normalize all keys first
    normalized: dict[str, list[str]] = {}
    for k, vals in evidence_map.items():
        cid = _norm_cid(k)
        if cid:
            normalized.setdefault(cid, []).extend(vals if isinstance(vals, list) else [vals])

    def _resolve(ids: list[str]) -> list[str]:
        out = []
        for ev_id in ids:
            if ev_id in real_ids:
                out.append(ev_id)
                continue
            hit = lower_map.get(ev_id.lower())
            if hit:
                out.append(hit)
        return out

    # Inverted detection: most keys cannot be normalized into a constraint id
    keys = list(evidence_map.keys())
    if keys:
        n_invalid = sum(1 for k in keys if _norm_cid(k) is None)
        if n_invalid > len(keys) / 2:
            # try the swap: values that are valid constraint ids become keys,
            # keys (evidence ids) become list members
            swapped: dict[str, list[str]] = {}
            for k, vals in evidence_map.items():
                for v in vals if isinstance(vals, list) else [vals]:
                    if isinstance(v, str):
                        cid = _norm_cid(v)
                        if cid:
                            swapped.setdefault(cid, []).append(k)
            if swapped:
                evidence_map = swapped
                normalized = {}
                for k, vals in evidence_map.items():
                    cid = _norm_cid(k)
                    if cid:
                        normalized.setdefault(cid, []).extend(vals if isinstance(vals, list) else [vals])

    resolved: dict[str, list[str]] = {}
    for cid, ev_ids in normalized.items():
        out = _resolve(ev_ids if isinstance(ev_ids, list) else [ev_ids])
        if out:
            resolved[cid] = out
    return resolved


# iter-19: guards moved out of agents; F2' (18 Sep): moved to domains/revenue/guards/
from core.trace import TraceReport  # noqa: E402
from domains.revenue.guards.population import (  # noqa: E402
    _guard_experiment_population,
    _guard_probe_population_convention,
)


def _merge_evidence_maps(
    base: dict[str, list[str]], extra: dict[str, list[str]]
) -> dict[str, list[str]]:
    """Union of two evidence_maps (internal-docs §8.4 T2). Rule contributions add,
    never overwrite — the LLM mapping must not be lost to the rule layer."""
    merged: dict[str, list[str]] = {k: list(v) for k, v in (base or {}).items()}
    for cid, ids in (extra or {}).items():
        bucket = merged.setdefault(cid, [])
        for i in ids:
            if i not in bucket:
                bucket.append(i)
    return merged


from domains.revenue.prompts.diagnosis_system import SYSTEM  # noqa: E402 — F3
from domains.revenue.prompts.diagnosis_user import build_user_prompt  # noqa: E402 — F3


def contraindication_for(constraint_id: str) -> str:
    """Deterministic lookup: constraint_id -> contraindication (prefix match). NOT an LLM.
    v0.2: verdict taxonomy — STOP / NOT_YET / TEST_FIRST explicit at the start
    (internal-docs §2: distinguish 'do not scale' vs 'test a small volume')."""
    for pattern, c in ONTOLOGY["contraindications"].items():
        if constraint_id.startswith(pattern.rstrip("*")):
            if isinstance(c, dict):
                parts = []
                verdict = c.get("verdict")
                if verdict == "TEST_FIRST":
                    parts.append("🟡 TEST FIRST — do not scale, run a small test first")
                elif verdict == "STOP":
                    parts.append("🛑 STOP")
                elif verdict == "NOT_YET":
                    parts.append("🟠 NOT YET")
                parts.append(c.get("text", ""))
                if c.get("reason"):
                    parts.append(f"Why: {c['reason']}")
                if c.get("until"):
                    parts.append(f"Until: {c['until']}")
                return " — ".join(p for p in parts if p)
            return str(c)
    return ""


def contraindication_detail_for(constraint_id: str) -> dict | None:
    """P-C (internal-docs §11): 'DON'T' as a navigation state.
    Deterministic structure from the registry — do_not (render text) stays alive for
    backward compat; this is the field the engine/UI consumes. until = unlock_condition."""
    for pattern, c in ONTOLOGY["contraindications"].items():
        if constraint_id.startswith(pattern.rstrip("*")) and isinstance(c, dict):
            return {
                "verdict": c.get("verdict"),
                "text": c.get("text", ""),
                "reason": c.get("reason", ""),
                "unlock_condition": c.get("until", ""),
                "matched_pattern": pattern,
            }
    return None
    return "No specific contraindication on record — check before spending big money."


class DiagnosisDraft(BaseModel):
    where_you_are: str = Field(description="1 block: where the user is now, one or two sentences")
    primary_constraint: str = Field(
        description="HUMAN language, no codes, e.g. 'You do not yet have a clear offer'")
    primary_constraint_id: str = Field(description="ontology code, e.g. V2.1")
    secondary_constraints: list[str] = Field(default_factory=list, description="plain human language")
    why: list[str] = Field(description="evidence convergence, singkat")
    next_best_action: str = Field(
        description=(
                    '7-day action — an EXPERIMENT that tests the diagnosis, not generic growth'
                    'advice'
                    ))
    grounded_intervention_id: str = Field(
        default="",
        description=(
                    'KB intervention ID that grounds the NBA (e.g. TM-I03) — the action choice MUST'
                    'come from the CANDIDATE INTERVENTIONS menu; wording may be adapted to the'
                    "user's context. Leave empty ONLY when no menu item is relevant."
                    ))
    first_step_today: str = Field(
        default="", description='Micro-step <30 minutes, can start TODAY, very concrete')
    day_by_day: list[ActionItem] = Field(
        default_factory=list, description="Days 1 to 7, each item ONE specific action"
    )

    @field_validator("day_by_day", mode="before")
    @classmethod
    def _coerce_day_items(cls, v):
        """Plain strings (provider output) → ActionItem(text=…) — J1 internal-docs §7."""
        if isinstance(v, list):
            return [{"text": str(x)} if isinstance(x, str) else x for x in v]
        return v
    outreach_script: str = Field(
        default="",
        description=(
                    "Ready-to-use script/template (message, offer template, etc.) from the user's"
                    'context'
                    ))
    success_metric: str
    well_know_when: str
    reassess_window_days: int = Field(default=14)
    pivot_rule: str
    evidence_map: dict[str, list[str]] = Field(description=(
                                                           'constraint_id -> [evidence_id] that'
                                                           'support it'
                                                           ))

    @field_validator(
        "where_you_are", "primary_constraint", "primary_constraint_id",
        "next_best_action", "first_step_today", "outreach_script",
        "success_metric", "well_know_when", "pivot_rule",
        mode="before",
    )
    @classmethod
    def _coerce_list_to_str(cls, v):
        """iter-19 (post-freeze, systematic evidence): 2 consecutive smoke runs failed
        because deepseek-v4.1-flash returned a LIST for a single-text field
        ('well_know_when': ['If ...']). Coerce list→string (space-joined) —
        provider robustness, not an epistemic change."""
        if isinstance(v, list):
            return " ".join(str(x) for x in v)
        return v

    @field_validator("secondary_constraints", "why", "day_by_day", mode="before")
    @classmethod
    def _coerce_str_to_list(cls, v):
        """The other direction: the LLM returns ONE string for a list field
        ('why': 'Four pieces of evidence point ...') → wrap into a list.
        Proven to break the whole finalize 2x on the iter-20c eval.
        Provider robustness, not an epistemic change."""
        if isinstance(v, str):
            parts = [p.strip(" -•\t") for p in v.splitlines() if p.strip(" -•\t")]
            return parts or ([v.strip()] if v.strip() else [])
        return v


def _draft_with_retry(llm: LLMProvider, prompt: str, evidence: list[EvidenceItem], tr) -> "DiagnosisDraft":
    """G9 (manual run 19 Sep — mapping_coverage 0): an empty evidence_map from the
    LLM = provider DEGRADATION (drift/quota/broken JSON), NOT normal variation —
    retry 1x before falling back to the iter-9 degrade path. Threshold len(evidence) >= 5:
    mini sessions (3 turns) with little evidence do not pay the retry cost."""
    draft = tr.stage("llm_draft", lambda: llm.structured_call(DiagnosisDraft, SYSTEM, prompt),
                     note="satu-satunya stage nondeterministik")
    draft.evidence_map = _resolve_evidence_map(draft.evidence_map, evidence)
    if not draft.evidence_map and len(evidence) >= 5:
        draft = tr.stage(
            "llm_draft_retry",
            lambda: llm.structured_call(DiagnosisDraft, SYSTEM, prompt),
            note="evidence_map kosong (degradasi) — retry 1x",
        )
        draft.evidence_map = _resolve_evidence_map(draft.evidence_map, evidence)
    return draft


# ── Goal consistency guard for DiagnosisDraft (round 4 Phase 5) ──────────────────────────────────────
# The prompt + ACTIVE GOAL block are not a guarantee: drafts from a real provider may name other
# targets/metrics, a current value that was never measured, or certain claims about a still-UNKNOWN
# relation. The draft is checked against the session's structured Goal
# (domains/revenue/guards/goal_consistency); violations go back to the provider ONCE, and anything
# still violating is replaced with a deterministic sentence from the Goal — not text known to be
# wrong. Only violation CODES are recorded in the trace.
def _draft_goal_violations(draft: "DiagnosisDraft", facts) -> dict[str, list[str]]:
    from domains.revenue.guards.goal_consistency import check_text_goal

    fields: dict[str, list[str]] = {
        "where_you_are": [draft.where_you_are], "primary_constraint": [draft.primary_constraint],
        "why": list(draft.why or []), "secondary_constraints": list(draft.secondary_constraints or []),
        "next_best_action": [draft.next_best_action],
        "first_step_today": [draft.first_step_today], "success_metric": [draft.success_metric],
        "well_know_when": [draft.well_know_when], "pivot_rule": [draft.pivot_rule],
        "outreach_script": [draft.outreach_script],
        "day_by_day": [a.text for a in draft.day_by_day or []],
    }
    out: dict[str, list[str]] = {}
    for name, texts in fields.items():
        errs = [f"{c}: {r}" for t in texts for c, r in check_text_goal(str(t or ""), facts)]
        if errs:
            out[name] = sorted(set(errs))
    return out


def _apply_goal_fallback(draft: "DiagnosisDraft", bad: dict[str, list[str]], facts) -> "DiagnosisDraft":
    from domains.revenue.guards.goal_consistency import goal_label, goal_line, measurement_line, target_text

    name = goal_label(facts)
    window = f" within {facts.window_days:g} days" if facts.window_days else ""
    repl = {
        "where_you_are": f"{goal_line(facts)} {measurement_line(facts)}",
        "primary_constraint": ("There is not enough measured evidence yet to name the one thing holding "
                               "this goal back."),
        "next_best_action": f"Record the first {name} measurement so the map can judge progress.",
        "first_step_today": f"Write down where your {name} stands today, or mark it not measured.",
        "success_metric": f"{name} at {target_text(facts)}{window}",
        "well_know_when": f"{name} is measured at or past the target in a recorded check-in.",
    }
    for field_name in bad:
        if field_name in repl:
            setattr(draft, field_name, repl[field_name])
        elif field_name == "why":
            draft.why = [goal_line(facts), measurement_line(facts)]
        elif field_name == "secondary_constraints":
            draft.secondary_constraints = []
        elif field_name == "day_by_day":
            from domains.revenue.guards.goal_consistency import check_text_goal

            draft.day_by_day = [a for a in draft.day_by_day if not check_text_goal(a.text, facts)]
        elif field_name in ("pivot_rule", "outreach_script"):
            setattr(draft, field_name, "")
    return draft


def _guard_goal_consistency(
    llm: LLMProvider, prompt: str, draft: "DiagnosisDraft", goal_obj: dict | None,
    evidence: list[EvidenceItem],
) -> tuple["DiagnosisDraft", dict]:
    from domains.revenue.guards.goal_consistency import codes_of, goal_facts_of

    g = goal_obj or {}
    mid = g.get("metric_id") or ("revenue_monthly" if g.get("metric") == "revenue_monthly" else "")
    # revenue: the current value is computed from evidence AFTER the draft (state) - not verifiable here yet
    facts = goal_facts_of(g, check_current=(mid != "revenue_monthly"))
    info = {"checked": bool(facts.metric_id), "violations_first_pass": [], "retried": False,
            "violations_after_repair": [], "fallback_fields": []}
    if not facts.metric_id:
        return draft, info
    bad = _draft_goal_violations(draft, facts)
    info["violations_first_pass"] = codes_of(bad)
    if not bad:
        return draft, info
    note = ("\nYour previous draft contradicted the structured goal. Rewrite it so it serves THIS goal only "
            "(its metric, unit and target), never states a current value that is not measured, and never "
            "says a path will surely move the goal:\n"
            + "\n".join(f"- {f}: {'; '.join(v)}" for f, v in bad.items()) + "\n")
    try:
        retry = llm.structured_call(DiagnosisDraft, SYSTEM, prompt + note)
        retry.evidence_map = _resolve_evidence_map(retry.evidence_map, evidence)
        retry = _guard_causal_narrative(_humanize_draft(retry))
        bad_retry = _draft_goal_violations(retry, facts)
        info["retried"] = True
        if len(bad_retry) <= len(bad):
            draft, bad = retry, bad_retry
    except Exception:  # noqa: BLE001 - retry failed = use the deterministic fallback, not wrong text
        pass
    info["violations_after_repair"] = codes_of(bad)
    if bad:
        draft = _apply_goal_fallback(draft, bad, facts)
        info["fallback_fields"] = sorted(bad)
    return draft, info


def prescription_throttle(draft: DiagnosisDraft, confidence: float) -> str:
    """LEGACY plan-depth throttle (iter-16; D-05 audit 14 Oct 2026).

    Phase 7: the diagnosis no longer authors a day-by-day plan, so this only ever trims a draft a
    legacy provider still produced (empty list = no note, no trim). It stays for compatibility and is
    never a scheduling authority.

      - confidence < 0.30  -> at most 3 truly executable actions; the later-phase postponement
        message becomes a NOTE for explanation — NOT a 4th ActionItem in `day_by_day` (live D-05
        failed `prescription_throttled` with len=4);
      - 0.30–0.59          -> at most 5 (old behavior kept; the audit asked to check and lock it
        with tests, not for a new throttle system);
      - >= 0.60            -> not trimmed.

    Returns: an extra note for `engine_note` ('' when none).
    """
    note = ""
    if confidence < 0.30:
        if len(draft.day_by_day) > 3:
            note += (
                "⚠ LATER ACTIONS DEFERRED: hold the ones beyond the first three until the first "
                "results change the picture — diagnosis confidence is still low; the rest wait "
                "until the probe outcome is known."
            )
        draft.day_by_day = draft.day_by_day[:3]
        note += ("\n\n" if note else "") + (
            f"⚠ PRESCRIPTION THROTTLE: diagnosis confidence {confidence*100:.0f}% (<30%) — "
            "rencana dipangkas ke probe + ukur + review. Prescription depth harus proporsional "
            "dengan diagnostic confidence; fase lanjutan dijadwalkan setelah informasi masuk."
        )
    elif confidence < 0.60:
        draft.day_by_day = draft.day_by_day[:5]
    return note


def synthesize(
    llm: LLMProvider,
    goal: str,
    evidence: list[EvidenceItem],
    transcript: str,
    language: str,
    status: str,
    journey_context: dict | None = None,
    graph: dict | None = None,
    on_stage=None,  # Callable[[str, int], None] — per-stage progress (E5)
    goal_obj: dict | None = None,  # Goal-Relative (int 09 §5): session's structured Goal context
    historical_evidence: list[EvidenceItem] | None = None,  # DCP-01: superseded claims (explanation only)
    # F3d/R5 (P0-2): reader of the ADJUDICATED requirement state. Passed through to build_possible_paths so
    # the FINAL diagnosis feasible set uses the same ledger as provisional navigation (semantic parity).
    ledger_state_of: Any = None,
) -> DiagnosisArtifact:
    tr = TraceReport("diagnosis", on_stage=on_stage)  # internal-docs §7: stage trace
    constraint_lines = "\n".join(
        f"{cid} {c['name']}: {c['definition'][:60]}" for cid, c in ONTOLOGY["constraints"].items()
    )
    ev_lines = "\n".join(
        f"- [{e.id}] ({e.level}{' · GAP: data hilang, BUKAN fakta' if e.is_gap else ''}) {e.signal}"
        for e in evidence
    ) or "- (none)"
    # DCP-01: claims that were already superseded are SEPARATED from EVIDENCE — they may explain change,
    # never become current-state facts (history stays intact, not a destructive filter).
    _hist = list(historical_evidence or [])
    hist_lines = "\n".join(
        f"- [{e.id}] ({e.level}) {e.signal}" for e in _hist
    ) or ""

    # Transcript trimmed: last lines only — the evidence ledger already carries the core facts.
    # A large prompt = ballooning latency (measured: 26s->85s, then timeout on glm-5.3-flash).
    transcript_tail = "\n".join(transcript.strip().splitlines()[-12:])

    # --- internal-docs §6.1 (Phase 1): pre-draft intervention menu — KB owns selection ---
    # Constraint candidates from deterministic signals (mechanism clusters, pure fn);
    # the same values are reused by the `mechanisms` stage below — zero double computation.
    # The menu is a CANDIDATE list (not the final scope): linkage validation is still done
    # by the guard against the post-arbitration final scope (internal-docs §8.3).
    mech_pre = detect_mechanisms(evidence)  # dict: mechanism_id -> [evidence_id]
    _cand_cids: list[str] = []
    for _mid, _eids in sorted(mech_pre.items(), key=lambda kv: -len(kv[1])):
        for _cid in MECHANISMS.get(_mid, {}).get("constraints", []) or []:
            if _cid not in _cand_cids:
                _cand_cids.append(_cid)
    _cand_cids = _cand_cids[:3]
    _menu: list[dict] = []
    _seen_menu: set[str] = set()
    try:
        for _cid in _cand_cids:
            for _iv in interventions_for(_cid):
                _iid = _iv.get("intervention_id", "")
                if not _iid or _iid in _seen_menu:
                    continue
                _seen_menu.add(_iid)
                _menu.append({**_iv, "for_constraint": _cid})
    except Exception:
        _menu = []  # degrade-safe: no menu → pre-fix behavior (internal-docs §6.1)
    _menu = _menu[:6]  # prompt budget (internal-docs phase 3: do not bloat)
    # J7-c (internal-docs §7): demote interventions whose outcome was bad for THIS USER
    # (not_moved/regret from the session's outcome log) — the pre-draft menu is filtered too
    # so the LLM never gets to pick them as the NBA. The global KB is untouched.
    _demoted = (journey_context or {}).get("demoted_interventions") or {}
    if _demoted:
        _menu, _menu_removed = demote_interventions(_menu, _demoted)
    else:
        _menu_removed = []
    _menu_lines = "\n".join(
        f"- [{i['intervention_id']}] ({i.get('for_constraint', '?')}) {i['name']} "
        f"→ bukti keberhasilan: {i.get('expected_evidence', '')}"
        + (f" (kontraindikasi s.d. {i['contraindicated_until']})"
           if i.get("contraindicated_until") else "")
        for i in _menu
    )

    # F3 (internal-docs §9): prompt template = domain vocabulary → domains/revenue/prompts/.
    # agents only assembles the arguments; the text no longer lives in this layer.
    # J7-b (internal-docs §7): the user journey block (compiled summary ≤6 lines,
    # sleep-time pattern — not a transcript) is appended AFTER the main template.
    from domains.revenue.prompts.diagnosis_user import goal_context_block
    prompt = build_user_prompt(
        goal=goal,
        language=language,
        ev_lines=ev_lines,
        constraint_lines=constraint_lines,
        transcript_tail=transcript_tail,
        schema_hint_str=schema_hint(DiagnosisDraft),
        intervention_menu_str=_menu_lines,
        historical_evidence_str=hist_lines,
    ) + goal_context_block(goal_obj) + journey_prompt_block(journey_context)
    draft = _draft_with_retry(llm, prompt, evidence, tr)
    draft = _humanize_draft(draft)
    draft = _guard_causal_narrative(draft)
    draft, _goal_guard = tr.stage(
        "goal_guard", lambda: _guard_goal_consistency(llm, prompt, draft, goal_obj, evidence),
        note="narasi vs Goal terstruktur: retry 1x lalu fallback deterministik (hanya kode dicatat)")
    # diagnostics inspectable in the trace: violation CODES + actions, without narrative text
    tr.stage("goal_guard.result", lambda: None, note=(
        f"checked={_goal_guard['checked']}; first_pass={_goal_guard['violations_first_pass']}; "
        f"retried={_goal_guard['retried']}; after_repair={_goal_guard['violations_after_repair']}; "
        f"fallback_fields={_goal_guard['fallback_fields']}"))

    # --- T2 (internal-docs §8.4): knowledge layer = SECOND MAPPER ------------------------
    # Rules are evaluated against FACTS (evidence), not derived artifacts (ranking).
    # The old gate `targets ∩ ranking_ids` let knowledge only correct
    # what the LLM had already seen; rule contributions now enrich the evidence_map
    # BEFORE scoring → constraints the LLM missed can still surface.
    kb_outcome = tr.stage(
        "knowledge_rules",
        lambda: run_knowledge_rules(
            llm, evidence, transcript, llm_transcript_tail=transcript_tail,
            historical_evidence=_hist,
        ),
        note="tier-1 predicate (transkrip penuh, 0 LLM) + tier-2 LLM matcher, sitasi wajib",
    )
    if kb_outcome.rule_evidence_map:
        draft.evidence_map = _merge_evidence_maps(draft.evidence_map, kb_outcome.rule_evidence_map)

    # Layer 2 (deterministic): confidence + contraindication lookup
    # D (internal-docs §2): Evidence → Mechanism → Constraint — scoring is no
    # longer blind to the LLM map; mechanisms are detected deterministically from evidence signals.
    # internal-docs §6.1: values computed pre-draft (intervention menu) and reused here —
    # pure function, output identical to a direct call.
    mech_map = tr.stage("mechanisms", lambda: mech_pre)
    m_boost, m_weights = mechanism_boost(draft.evidence_map, evidence)
    ranking = tr.stage("confidence.ranking", lambda: score_hypotheses(
        draft.evidence_map, evidence, mech_boost=m_boost, mech_weights=m_weights))
    # T3/T4: rule consequences execute deterministically AFTER scoring, BEFORE
    # confidence & arbitration — so the final ranking stays consistent with the decision.
    tr.stage(
        "knowledge.consequences",
        lambda: apply_rule_consequences(ranking, kb_outcome),
        note="LOWER/RAISE/IGNORE/FLAG/BLOCK → effective_score",
    )
    confidence = tr.stage("confidence.overall", lambda: overall_confidence(ranking, evidence))

    # LLM-vs-engine arbitration (iter-3 #3, restored iter-6): the LLM proposes, the engine decides.
    tr.stage("arbitration.begin", lambda: None, note="evidence gate / transparency")
    # C (internal-docs §2): disqualifier check — a top-ranked constraint whose
    # disqualifier is triggered (e.g. DM5.5 despite real transactions) is demoted + given a note.
    dq_note: str | None = None
    if ranking:
        dq_notes = []
        for h in ranking[:3]:
            dq = disqualifier_check(h.constraint_id, ONTOLOGY, evidence)
            if dq:
                h.score = min(h.score, 0.39)
                dq_notes.append(f"⚠ Disqualifier {h.constraint_id}: {dq} — diturunkan ke UNPROVEN.")
        if dq_notes:
            ranking = sorted(ranking, key=lambda h: (-h.score, upstream_rank(h.constraint_id)))
            dq_note = "\n".join(dq_notes)
    # WP1 (internal-docs §2.10): knowledge rule interpreter — 100% KB activation.
    # The LLM matches rule conditions (natural language) against the case;
    # consequences are executed deterministically onto effective_score. Degrade-safe.
    llm_pick = draft.primary_constraint_id
    top_ids = [h.constraint_id for h in ranking[:3]]
    engine_note: str | None = None
    arbitration: str | None = "agree"
    llm_score = next((h.score for h in ranking if h.constraint_id == llm_pick), 0.0)
    top_gap = (ranking[0].score - llm_score) if ranking else 0.0
    if ranking and llm_pick not in top_ids:
        # Tier-2 #9 (iter-11): EVIDENCE GATE (formerly "ENGINE VETO") — explain
        # based on EPISTEMIC STATUS, not a "the engine won" claim.
        arbitration = "veto"
        final_id = ranking[0].constraint_id
        _st_win = constraint_status(final_id, ranking[0].supporting_evidence_ids, evidence)
        _st_lose = constraint_status(
            llm_pick,
            next((h.supporting_evidence_ids for h in ranking if h.constraint_id == llm_pick), []),
            evidence,
        )
        c = ONTOLOGY["constraints"].get(final_id, {})
        draft.primary_constraint = f"{c.get('name', final_id)} — {c.get('definition', '')}"
        draft.primary_constraint_id = final_id
        engine_note = (
            f"EVIDENCE GATE: LLM mengusulkan {llm_pick} (status {_st_lose}), sedangkan bukti "
            f"terkuat ada pada {final_id} (status {_st_win}). Diagnosis utama diambil {final_id}. "
            f"Aturan: constraint yang buktinya OBSERVED menang atas yang INFERRED/UNRESOLVED."
        )
    elif ranking and llm_pick != ranking[0].constraint_id and top_gap > TRANSPARENCY_MARGIN:
        # P1 (eval 15 Sep): evidence-first — the LLM may only override ranking[0]
        # within the margin. Above the margin, evidence wins; 'more upstream' is not an override.
        arbitration = "veto"
        final_id = ranking[0].constraint_id
        c = ONTOLOGY["constraints"].get(final_id, {})
        draft.primary_constraint = f"{c.get('name', final_id)} — {c.get('definition', '')}"
        draft.primary_constraint_id = final_id
        engine_note = (
            f"Engine override (evidence-first): bukti tertimbang untuk {final_id} unggul "
            f"{top_gap:.2f} atas pilihan diagnostisiawan {llm_pick} — di atas margin "
            f"{TRANSPARENCY_MARGIN}. 'Lebih upstream' bukan alasan menimpa bukti yang lebih kuat."
        )
    elif ranking and llm_pick != ranking[0].constraint_id:
        # E5 (iter-10, bug v6): transparency is allowed only when the epistemic status
        # is equal/stronger. If ranking[0] is OBSERVED and the LLM pick is INFERRED →
        # the EVIDENCE GATE wins so primary_constraint_id stays consistent with the
        # Constraint Map & Layered Diagnosis (a single source of truth).
        _st_rank = constraint_status(ranking[0].constraint_id, ranking[0].supporting_evidence_ids, evidence)
        _st_llm = constraint_status(
            llm_pick,
            next((h.supporting_evidence_ids for h in ranking if h.constraint_id == llm_pick), []),
            evidence,
        )
        if _st_rank == "OBSERVED" and _st_llm != "OBSERVED":
            arbitration = "evidence_gate"
            final_id = ranking[0].constraint_id
            c = ONTOLOGY["constraints"].get(final_id, {})
            draft.primary_constraint = f"{c.get('name', final_id)} — {c.get('definition', '')}"
            draft.primary_constraint_id = final_id
            engine_note = (
                f"EVIDENCE GATE: kandidat {llm_pick} berstatus {_st_llm}, sedangkan "
                f"{final_id} berstatus {_st_rank}. Constraint yang buktinya teramati "
                f"menang atas inferensi — PRIMARY diambil {final_id}. Selisih skor mentah {top_gap:.2f} "
                f"(≤ margin) tidak cukup untuk membalik status epistemik."
            )
        else:
            arbitration = "transparency"
            engine_note = (
                f"Catatan transparansi: pilihan diagnostisiawan {llm_pick} dipertahankan — "
                f"selisih skor terhadap {ranking[0].constraint_id} hanya {top_gap:.2f} "
                f"(≤ margin {TRANSPARENCY_MARGIN}), dan status epistemik setara "
                f"({_st_llm} vs {_st_rank}). Pantau keduanya saat reassess."
            )

    do_not = contraindication_for(draft.primary_constraint_id)
    do_not_detail = contraindication_detail_for(draft.primary_constraint_id)

    # Cross-contraindication check (iter-4, fixed iter-5): word-boundary regex,
    # human constraint names, explicit 'In place until:' label, separate notes.
    RISK_KEYWORDS = {
        "V2.*": ("iklan", "ads", "berbayar", "paid", "kampanye", "meta ads"),
        "DS4.*": ("konten masif", "posting masal", "content massal"),
        "M3.*": ("tambah channel", "perluas channel", "channel baru"),
        "DM5.*": ("scale", "perbesar budget", "besarkan budget"),
    }
    action_text = " ".join(filter(None, [draft.next_best_action, draft.first_step_today,
                                         " ".join(day_texts(draft.day_by_day)), draft.outreach_script,
                                         draft.success_metric])).lower()
    cross_notes: list[str] = []
    for cid in top_ids:
        if cid == draft.primary_constraint_id:
            continue
        for pattern, banned in RISK_KEYWORDS.items():
            if cid.startswith(pattern.rstrip("*")):
                hits = [kw for kw in banned if re.search(rf"\b{re.escape(kw)}\b", action_text)]
                if hits:
                    cc = ONTOLOGY["contraindications"].get(pattern, {})
                    until = (
                        cc.get("until", "that condition is met")
                        if isinstance(cc, dict) else "that condition is met"
                    )
                    cname = ONTOLOGY["constraints"].get(cid, {}).get("name", cid)
                    cross_notes.append(
                        f"⚠ Cross-check: the step touches '{hits[0]}' — it collides with the ban "
                        f"[{cid} · {cname}]. "
                        f"In place until: {until}. Run that part ONLY once that "
                        f"condition is met."
                    )
    if cross_notes:
        base = engine_note + "\n\n" if engine_note else ""
        engine_note = base + "\n".join(cross_notes)
    if dq_note:
        base = engine_note + "\n\n" if engine_note else ""
        engine_note = base + dq_note

    # P2 (eval 15 Sep): unknowns must have consequences. Material gaps already
    # lower confidence (overall_confidence) — here they become explicit probes,
    # not just log lines in the ledger.
    gap_penalty, gap_probes = gap_consequences(evidence)
    if gap_probes:
        probe_lines = "\n".join(f"- {g}" for g in gap_probes)
        unk = (
            f"⚠ UNKNOWN dengan konsekuensi (confidence −{gap_penalty:.2f}): "
            f"pertanyaan material berikut belum terjawab. Probes ini harus ditanyakan "
            f"di sesi lanjutan / sebelum reassess — jangan dianggap selesai karena "
            f"sudah dicatat:\n{probe_lines}"
        )
        base = engine_note + "\n\n" if engine_note else ""
        engine_note = base + unk

    # --- P1: Reasoning trace (internal-docs §2.10) — structured, deterministic ---
    # T3 (internal-docs §8.4): ONE source of truth — only rules that were really evaluated
    # & matched (with citations) may appear. No proxy attribution.
    applied_rules = sorted(set(kb_outcome.matched_ids))
    _ka_rows = [
        {"rule_id": m.rule_id, "applied_to": m.applied_to, "tier": m.tier, "reason": m.reason}
        for m in kb_outcome.matched
    ]
    ev_by_id = {e.id: e for e in evidence}
    ev_supports: dict[str, list[str]] = {}
    for cid, ev_ids in draft.evidence_map.items():
        for ev_id in ev_ids:
            ev_supports.setdefault(ev_id, []).append(cid)
    # Crash fix (iter-9): ranking can be EMPTY when the LLM returns an empty
    # mapping (drift/quota degrade) — never index without a guard.
    _top_support_ids = ranking[0].supporting_evidence_ids if ranking else []
    _has_hard_support = any(
        ((ev := ev_by_id.get(i2)) and not ev.is_gap and ev.level in ("transactional", "outcome"))
        for i2 in _top_support_ids
    )
    evidence_activations = [
        EvidenceActivation(
            evidence_id=e.id, level=e.level, is_gap=e.is_gap,
            supports=ev_supports.get(e.id, []),
            activated_rules=(
                applied_rules
                if (not e.is_gap and not _has_hard_support and e.level == "self_reported")
                else []
            ),
        )
        for e in evidence
    ]
    # Primary contraindication as a structured object
    _cc: dict | None = None
    for pattern, c in ONTOLOGY["contraindications"].items():
        if draft.primary_constraint_id.startswith(pattern.rstrip("*")) and isinstance(c, dict):
            _cc = {"verdict": c.get("verdict", ""), "text": c.get("text", ""),
                   "reason": c.get("reason", ""), "until": c.get("until", "")}
            break
    # Active ACs (rule sources activated for this diagnosis; rule_activation.json)
    try:
        from engine.knowledge import active_rule_sources
        _allowed = active_rule_sources()
    except Exception:
        _allowed = {"TM", "VP", "CS"}
    ac_list = [{
        "condition_id": "AC-01",
        "active_reason": f"Diagnosis menimbang seluruh ledger → sumber rule aktif: {sorted(_allowed)}",
    }, {
        "condition_id": "AC-02",
        "active_reason": (
            "VPD-vs-HK (vitamin/painkiller): HK aktif untuk seluruh ledger "
            "— grounding domain Retention (R7.*)"
        ),
    }]
    # D: mechanism clusters for the trace (Evidence → Mechanism → Constraint)
    mechanism_clusters = [
        {
            "mechanism_id": mid,
            "name": MECHANISMS[mid]["name"],
            "description": MECHANISMS[mid]["description"],
            "evidence_ids": ev_ids,
            "constraints": MECHANISMS[mid]["constraints"],
        }
        for mid, ev_ids in mech_map.items()
    ]
    reasoning_trace = ReasoningTrace(
        trace_id=f"RT-{status.upper()}-{draft.primary_constraint_id}",
        evidence_activations=evidence_activations,
        knowledge_activated=knowledge_activation_log(_ka_rows),
        hypothesis_resolution=hypothesis_resolution_trace(
            ranking, evidence, draft.primary_constraint_id, llm_pick, arbitration
        ),
        contraindication_triggered=_cc,
        applicability_conditions=ac_list,
        mechanisms=mechanism_clusters,
    )
    # T3 (internal-docs §8.4): the `_KA_EFFECT` template was REMOVED. It used to overwrite
    # `applied_to` with a finished sentence claiming case facts (e.g. "a meeting
    # without commitment") when no meeting was guaranteed to exist. Citations now come from
    # the matcher/predicate — auditable.
    # Phase 2 (iter-6, internal-docs §4.4): Revenue State + Causal Hypothesis —
    # both DETERMINISTIC from evidence/ranking, not LLM output.
    revenue_state = tr.stage(
        "extract_state",
        # G7-S1b (internal-docs §10.3): the transcript as a deterministic anchor when
        # the LLM ledger carries no hour figures (not fabrication — literal numbers
        # from the source text; provenance recorded in revenue_state.sources).
        lambda: build_revenue_state(evidence, goal, transcript=transcript, graph=graph,
                                    historical_evidence=_hist),
    )
    # M3 (int 11 §10.14): RevenueState is now a VIEW of the Universal State Graph —
    # when a graph is available, view-mapped fields override the regex results
    # (with node-id provenance in sources). Regex remains the fallback for fields
    # not yet mapped by the adapter. Semantic projection, NOT a diagnosis.
    if graph and (graph.get("nodes") or {}):
        try:
            from domains.revenue.projection import build_revenue_view

            _view = build_revenue_view(graph)
            _apply_view(revenue_state, _view)
        except Exception:
            pass  # view failed → the old regex results stay in use
    # A1: epistemic status (needs state for SYSTEMIC_RISK L8.*) — the map is built
    # with state so statuses fill consistently with the ranking.
    constraint_map = build_constraint_map(ranking, evidence, ONTOLOGY, revenue_state)
    # Tier-2 #8 / Tier-3 #12 (iter-11): typed commercial objects + decision spectrum
    opportunities = tr.stage("opportunities", lambda: build_opportunities(evidence))
    _primary_status = next(
        (e.status for e in constraint_map if e.constraint_id == draft.primary_constraint_id), None
    )
    _verdict = None
    for _pat, _cc in ONTOLOGY["contraindications"].items():
        if draft.primary_constraint_id.startswith(_pat.rstrip("*")) and isinstance(_cc, dict):
            _verdict = _cc.get("verdict")
            break
    def _spectrum():
        return decide_spectrum(
            verdict=_verdict,
            readiness=revenue_state.readiness,
            demand_sufficiency=getattr(revenue_state, "demand_sufficiency", None),
            evidence_status=_primary_status,
            capacity_utilization=getattr(revenue_state, "capacity_utilization", None),
        )
    spectrum = tr.stage("spectrum", _spectrum)
    # Possible Paths (internal-docs): candidates are born from verified state + detected
    # mechanisms + active rules (NOT a fixed list), then evaluated deterministically; count is 0..N. Lifecycle
    # (e.g. a path the user STOPped via outcome, P-E) is layered on top of feasibility, not overriding it.
    # Deterministic, 0 LLM.
    _pstates = (journey_context or {}).get("path_states")
    possible_paths = tr.stage(
        "paths",
        lambda: build_possible_paths(
            revenue_state, spectrum,
            mechanisms=mech_pre,
            active_rules=kb_outcome.rule_supports(),
            path_states=_pstates,
            goal=goal_obj,
            ledger_state_of=ledger_state_of,
        ),
        note="possible paths — kandidat dari keadaan terverifikasi, dievaluasi deterministik (0..N); "
             "gate Goal relatif semantik metric (int 09)",
    )
    # E6 (iter-7, internal-docs §4.4): two-constraint coupling — fixing the PRIMARY
    # does not automatically make the target achievable; experiments are sequenced in 4 phases.
    if getattr(revenue_state, "gap_monthly", None):
        coupling = (
            f"Catatan keputusan: memperbaiki {draft.primary_constraint_id} TIDAK otomatis membuat "
            f"target achievable — demand sufficiency masih "
            f"{getattr(revenue_state, 'demand_sufficiency', 'UNKNOWN')} "
            f"(gap Rp{revenue_state.gap_monthly:.0f} jt belum terbukti bisa ditutup dari pipeline saat ini). "
            f"Urutan eksperimen: (1) perbaiki price-response, (2) ukur konversi, "
            f"(3) baru uji volume akuisisi, "
            f"(4) baru nilai feasibility target."
        )
        base = engine_note + "\n\n" if engine_note else ""
        engine_note = base + coupling
    # iter-16 (Batch C, user §7): DM5.1 (Demand Insufficiency) is FORBIDDEN from holding
    # the top rank while sufficiency is still UNKNOWN — insufficiency cannot yet
    # be distinguished from DS4.2 (inactivity) before exposure is measured. A
    # conditional disqualifier, not prompt-only.
    if revenue_state.demand_sufficiency == "UNKNOWN":
        demoted = [h for h in ranking if h.constraint_id == "DM5.1" and (h.effective_score or 0) > 0.39]
        if demoted:
            for h in demoted:
                h.effective_score = round((h.effective_score or 0) * 0.8, 3)
            ranking.sort(key=lambda h: (-(h.effective_score or 0), upstream_rank(h.constraint_id)))
            base = engine_note + "\n\n" if engine_note else ""
            engine_note = base + (
                "⚠ DISQUALIFIER DM5.1: demand insufficiency tidak bisa dibedakan dari "
                "distribution inactivity sebelum exposure terukur (sufficiency UNKNOWN) — "
                "skor DM5.1 didiskon. Buktikan dulu: lead yang cukup terekspos tapi tetap tidak membeli."
            )
    # E2 (iter-7): Data Integrity Check — deterministic, AFTER the extractor,
    # BEFORE diagnosis uses it. BLOCK/FLAG goes into engine_note + a confidence penalty.
    integrity_penalty, integrity_issues = tr.stage(
        "validate_state", lambda: validate_state(revenue_state, evidence)
    )
    if integrity_issues:
        revenue_state.integrity_issues = integrity_issues
        conf_lines = "\n".join(
            f"- [{i['severity']}] {i['check']}: {i['msg']}" for i in integrity_issues
        )
        integrity_note = (
            f"⚠ DATA INTEGRITY (confidence −{integrity_penalty:.2f}) — state revenue divalidasi "
            f"terhadap bukti; temuan berikut harus dicek sebelum percaya penuh pada angka "
            f"state:\n{conf_lines}"
        )
        base = engine_note + "\n\n" if engine_note else ""
        engine_note = base + integrity_note
        confidence = round(max(0.0, confidence - integrity_penalty), 3)
    causal_hypothesis = tr.stage("causal", lambda: build_causal_hypothesis(
        evidence, ranking, mech_map, draft.next_best_action, draft.primary_constraint_id
    ))

    # iter-14: SEMANTIC evidence dedup — independent evidence count for metrics.
    # Evidence Count ≠ Independent Evidence Count ('Rp30jt recurring' 4x = 1 obs).
    _reps, ev_clusters = deduplicate_evidence(evidence)
    n_independent = len(_reps)    # iter-15 (P1 user §10): topic clusters — record != observation != cluster.
    topic_counts = cluster_by_topic(evidence)
    # iter-9 guard: empty ranking = empty LLM mapping / low extraction quality.
    # Do not present the diagnosis as if valid — add a firm note + confidence 0.
    if not ranking:
        base = engine_note + "\n\n" if engine_note else ""
        engine_note = base + (
            "⚠ DATA TIDAK CUKUP: tidak ada bukti yang terpetakan ke constraint mana pun "
            "(mapping kosong atau kualitas ekstraksi rendah). Diagnosis ini PROVISIONAL — "
            "jangan ambil keputusan darinya. Lengkapi interview atau jalankan ulang sesi."
        )

    # Tier-2 #5 (iter-11): NO_FIT + fake constraint id guard.
    # The diagnostician may REJECT the whole ontology (do not force the nearest constraint).
    if (draft.primary_constraint_id or "").strip().upper() == "NO_FIT":
        draft.primary_constraint_id = "NO_FIT"
        base = engine_note + "\n\n" if engine_note else ""
        engine_note = base + (
            "NO_FIT: tidak ada constraint di ontology yang cukup menjelaskan bukti. Hipotesis bebas "
            "diagnostisiawan dipertahankan sebagai dugaan awal — kandidat constraint baru untuk "
            "ontology v0.4 (mis. Commercialization Maturity / Offer Architecture Gap)."
        )
    elif draft.primary_constraint_id not in ONTOLOGY["constraints"] and ranking:
        draft.primary_constraint_id = ranking[0].constraint_id
    # WP3 (internal-docs §2.10): KB interventions for the PRIMARY — grounding the NEXT BEST
    # ACTION + expected evidence is MANDATORY (internal-docs §6.2 #11). Deterministic lookup.
    # T4 (internal-docs §8.4): interventions are no longer limited to the PRIMARY.
    # CONTRIBUTING/SECONDARY constraints appearing high in the ranking also carry
    # grounded interventions — knowledge that was expensive to extract finally gets used.
    kb_interventions: list[dict] = []
    try:
        _scope = [h.constraint_id for h in ranking[:4]] if ranking else []
        if draft.primary_constraint_id not in _scope:
            _scope.insert(0, draft.primary_constraint_id)
        _seen: set[str] = set()
        # J4 (internal-docs §7): E2E axis gate — interventions are filtered to the
        # pre-sales/sales/after-sales phases relevant to the user's RevenueState.
        _e2e_phases = infer_e2e_phases(revenue_state)
        for _cid in _scope:
            for _iv in interventions_for(_cid, e2e_phases=_e2e_phases):
                if _iv.get("intervention_id") in _seen:
                    continue
                _seen.add(_iv.get("intervention_id"))
                kb_interventions.append({**_iv, "for_constraint": _cid})
        kb_interventions = kb_interventions[:6]  # artifact budget
    except Exception:
        kb_interventions = []
    # J7-c (internal-docs §7): demotion also at final scope — the nba_grounding guard and
    # the artifact only see interventions not yet proven failed for this user.
    _kb_removed: list = []
    if _demoted and kb_interventions:
        kb_interventions, _kb_removed = demote_interventions(kb_interventions, _demoted)
    if _kb_removed or _menu_removed:
        _dm_ids = sorted(
            {i.get("intervention_id", "?") for i in (_kb_removed + _menu_removed)}
        )
        _dm_why = "; ".join(f"{k}: {v}" for k, v in sorted(_demoted.items()))
        base = engine_note + "\n\n" if engine_note else ""
        engine_note = base + (
            "⚠ INTERVENSI DIDEMOTE (riwayat user — loop J7): intervensi berikut sudah "
            f"dijalankan user ini tanpa hasil ({_dm_why}) dan DIKELUARKAN dari menu "
            f"dan scope rekomendasi: {_dm_ids}. Pilihan NBA otomatis jatuh ke "
            "alternatif ter-grounding berikutnya — bukan pengulangan resep yang sama."
        )
    if kb_outcome.note or kb_interventions:
        base = engine_note + "\n\n" if engine_note else ""
        _iv_lines = "\n".join(
            f"- [{i['intervention_id']}] ({i.get('for_constraint', '?')}) {i['name']} "
            f"→ bukti keberhasilan: {i.get('expected_evidence', '')}"
            + (f" (kontraindikasi s.d. {i['contraindicated_until']})"
               if i.get("contraindicated_until") else "")
            for i in kb_interventions
        )
        _iv_scope = ", ".join(dict.fromkeys(i.get("for_constraint", "?") for i in kb_interventions))
        engine_note = base + (kb_outcome.note + "\n\n" if kb_outcome.note else "") + (
            f"INTERVENSI TER-GROUNDING KNOWLEDGE BASE (scope: {_iv_scope}):\n{_iv_lines}"
            if _iv_lines else ""
        )

    # --- internal-docs §6.2 (Phase 2): NBA ↔ KB linkage guard — deterministic, 0 LLM.
    # Validated against the FINAL post-arbitration scope (the pre-draft menu is only
    # a candidate list). UNGROUNDED → transparent flag + a grounded alternative for
    # the PRIMARY. Does NOT touch confidence (grounding ≠ epistemic evidence, F7).
    nba_grounding = tr.stage(
        "guard.nba_grounding",
        lambda: guard_nba_grounding(draft, _menu, kb_interventions),
        note="selection milik KB — referential integrity NBA↔intervention",
    )
    if nba_grounding["status"] == "UNGROUNDED":
        _ng_alt = (
            f"[{nba_grounding['alternative_id']}] {nba_grounding['alternative_name']} "
            f"(bukti keberhasilan: {nba_grounding['expected_evidence']})"
            if nba_grounding.get("alternative_id")
            else "tidak ada intervensi KB aktif untuk constraint ini"
        )
        base = engine_note + "\n\n" if engine_note else ""
        engine_note = base + (
            "⚠ NBA UNGROUNDED: Next Best Action tidak ter-link ke intervention knowledge base "
            f"(klaim: '{nba_grounding.get('claimed_id') or '-'}'). Alternatif ter-grounding "
            f"untuk {draft.primary_constraint_id}: {_ng_alt}. Kontrak RDKL: pilihan aksi "
            "dari KB, adaptasi wording ke konteks user."
        )
    # Phase 3 (internal-docs §10.4): seed reasoning path — the NBA↔KB linkage enters the
    # trace (partial P1 Explicit Reasoning Graph, internal-docs §14: which knowledge
    # was activated for a recommendation becomes structured data, not LLM narration).
    reasoning_trace.nba_grounding = nba_grounding
    layered = None
    try:
        by_status: dict[str, list] = {}
        for entry in constraint_map:
            by_status.setdefault(entry.status, []).append(entry)
        observed = sorted(by_status.get("OBSERVED", []), key=lambda x: -x.score)
        inferred = sorted(
            by_status.get("INFERRED", []) + by_status.get("CAUSAL_HYPOTHESIS", []), key=lambda x: -x.score
        )
        risks = by_status.get("SYSTEMIC_RISK", [])
        if observed or inferred:
            obs = observed[0] if observed else None
            und = inferred[0] if inferred else None
            # iter-15 (P1 user §1): OBSERVED CONDITION vs CONSTRAINT vs CAUSAL —
            # observed facts (can be a condition, not only a loss event)
            # are separated from constraint claims and from causal claims.
            _hard_texts = [
                (e.signal or "") for e in evidence
                if not getattr(e, "is_gap", False) and e.level in ("transactional", "outcome")
            ]
            observed_conditions = _hard_texts[:4] or [
                "(belum ada kejadian loss yang teramati langsung di level hard evidence)"
            ]
            # iter-16 (Batch A, user §3): a mechanism may only appear under a constraint it is a
            # CANDIDATE for — otherwise mechanism and diagnosis point in different directions
            # (semantic instability).
            _owned = [c for c in mechanism_clusters if draft.primary_constraint_id in c["constraints"]]
            _competing = [c for c in mechanism_clusters if c not in _owned]
            if _owned:
                likely_mech = _owned[0]["name"]
            elif mechanism_clusters:
                likely_mech = (
                    f"{mechanism_clusters[0]['name']} — TIDAK ter-cluster dengan "
                    f"{draft.primary_constraint_id} "
                    f"(kandidat: {', '.join(mechanism_clusters[0]['constraints'])}); "
                    "mechanism dan diagnosis berada di jalur berbeda — lihat competing"
                )
            else:
                likely_mech = "—"
            layered = {
                "observed_constraint": f"{obs.constraint_id} · {obs.name}" if obs else "—",
                "observed_note": (
                    "Kejadian nyata teramati (loss/stall/deal) dengan bukti transactional/outcome"
                    if obs else "Belum ada kejadian yang teramati langsung"
                ),
                "observed_conditions": observed_conditions,
                "likely_mechanism": likely_mech,
                "competing_mechanisms": "; ".join(
                    f"{c['name']} → {', '.join(c['constraints'])}" for c in _competing
                ) or "—",
                "underlying_hypothesis": (
            f"{und.constraint_id} · {und.name} — CONTRIBUTING/SYSTEMIC FACTOR, BUKAN akar terbukti "
            f"(0 hard evidence: upstream bukan otomatis akar; 'akar lebih dalam' tidak boleh "
            f"diklaim hanya karena posisi upstream)"
            if und else "—"
        ),
                "systemic_risk": f"{risks[0].constraint_id} · {risks[0].name}" if risks else "—",
                "unresolved_cause": "; ".join(
                    f"{e.constraint_id}" for e in by_status.get("UNRESOLVED", [])[:3]
                ) or "lengkap terpetakan",
            }
    except Exception:
        layered = None

    # B1 (iter-8, calibration iter-10/E6): Experiment Integrity Check — only
    # adding NEW PROSPECTS at scale (≥5) violates phase-3 sequencing.
    # Follow-up/touches to existing leads = phase-1 work (ALLOWED).
    # Bug v6: H6 'send a 3rd touch to leads who never replied' was wrongly flagged.
    _ACQ_NEW = re.compile(
        r"(?:prospek|calon|kontak)\s*(?:-\s*)?baru"
        r"|cold\s*(?:email|outreach|dm)"
        r"|outreach\s*baru", re.I)
    _ACQ_COUNT = re.compile(r"(\d+)\s*(?:orang|prospek|calon|dm|kontak)", re.I)
    acq_items = []
    for _d in day_texts(draft.day_by_day):
        if not _d or not _ACQ_NEW.search(_d):
            continue
        _m = _ACQ_COUNT.search(_d)
        if _m and int(_m.group(1)) >= 5:
            acq_items.append(_d)
    if acq_items and draft.primary_constraint_id.startswith(("C6", "DM5")):
        viol = "\n".join(f"- \"{d[:90]}\"" for d in acq_items)
        base = engine_note + "\n\n" if engine_note else ""
        engine_note = base + (
            f"⚠ EXPERIMENT INTEGRITY: item rencana berikut menambah volume akuisisi \n"
            f"sebelum fase 1-2 (price-response + ukur konversi) selesai — bertentangan dengan \n"
            f"sequencing verdict sendiri (jangan ubah dua variabel sekaligus; isolasi penyebab). \n"
            f"Jalankan HANYA setelah konversi dari lead hidup terukur:\n{viol}"
        )

    # B2 (iter-8, fix N5): Script promise guard — never promise ROI/payback
    # without measured value evidence (V2.4 proven). Deterministically reworded to a safe version.
    _PROMISE = re.compile(r"[^.]*?(balik modal|roi|payback|investasi kembali)[^.]*\.", re.I)
    _SAFE = (
        "Dari situ saya bisa lihat apakah scope dan range ini masuk akal "
        "dibanding masalah yang sedang Anda hadapi."
    )
    # Tier-1 #2 (iter-11): the guard applies to ALL string fields (previously only 3 fields,
    # so a payback promise slipped through via causal_hypothesis.diagnostic_test).
    def _apply_promise_guard(obj) -> None:
        for fname in type(obj).model_fields:
            val = getattr(obj, fname, None)
            if isinstance(val, str) and val and _PROMISE.search(val):
                setattr(obj, fname, _PROMISE.sub(_SAFE, val))
            elif isinstance(val, list):
                new = [
                    (_PROMISE.sub(_SAFE, x) if isinstance(x, str) and _PROMISE.search(x) else x)
                    for x in val
                ]
                if new != val:
                    setattr(obj, fname, new)

    _apply_promise_guard(draft)

    # iter-14 (P0 user): DETERMINISTIC post-check of experiment population —
    # subjects named by the plan must exist in the evidence; claimed N must match.
    pop_note = _guard_experiment_population(draft, evidence)
    probe_note = _guard_probe_population_convention(draft, evidence)
    if probe_note:
        pop_note = (pop_note + "\n\n" + probe_note) if pop_note else probe_note
    if pop_note:
        base = engine_note + "\n\n" if engine_note else ""
        engine_note = base + pop_note

    # iter-15 (P1 user §4): PRIMARY vs experiment alignment — PRIMARY is in the
    # distribution domain (DS4.*) but this experiment tests conversion → diagnosis and
    # experiment point in different directions. Flag it, never silently.
    _plan_l = " ".join(filter(None, [draft.next_best_action, " ".join(day_texts(draft.day_by_day))])).lower()
    _conv_hits = sum(1 for k in ("harga", "bukti", "template", "follow-up", "balas") if k in _plan_l)
    _acq_hits = sum(1 for k in ("outreach", "konten", "posting", "dm baru",
                                "cold", "channel baru") if k in _plan_l)
    if draft.primary_constraint_id.startswith("DS4") and _conv_hits >= 2 and _acq_hits == 0:
        base = engine_note + "\n\n" if engine_note else ""
        engine_note = base + (
            "⚠ DIAGNOSIS-EXPERIMENT MISALIGNMENT: PRIMARY DS4.2 (distribusi) tapi eksperimen ini "
            "menguji konversi (bukti-vs-harga). Dua kemungkinan: (a) eksperimen ini valid sebagai "
            "langkah pertama karena lead yang ada harus dikonversi dulu sebelum akuisisi bermakna — "
            "maka DS4.2 perlu eksperimen akuisisi TERPISAH sebelum boleh disebut PRIMARY; "
            "(b) PRIMARY seharusnya direview. Jangan biarkan keduanya menunjuk arah berbeda tanpa catatan."
        )

    # iter-16: split confidence — constraint vs diagnosis vs revenue impact
    # + decision/experiment confidence (VoI).
    conf_split = split_confidences(
        ranking, evidence, revenue_state, diagnosis_confidence=confidence
    )

    # iter-16 (Batch D, user §9): prescription depth ∝ diagnostic confidence.
    # Low confidence → short, reversible, diagnostic actions — not a roadmap.
    # D-05 (audit 14 Oct 2026): the rule moved into the `prescription_throttle` helper so all three
    # bands are locked by deterministic tests (<0.30 max 3 + deferral to explanation; 0.30–0.59 max 5;
    # ≥0.60 unchanged).
    _depth_note = prescription_throttle(draft, confidence)
    if _depth_note:
        base = engine_note + "\n\n" if engine_note else ""
        engine_note = base + _depth_note

    # DCP-05 (int 16 S1): explicit epistemic standing - the synthesis operation being DONE does not mean
    # the diagnosis is FINAL epistemically. Computed deterministically from existing engine signals.
    _n_hard_ev = sum(
        1 for e in evidence if not getattr(e, "is_gap", False) and e.level in ("transactional", "outcome")
    )
    if not ranking or confidence < 0.20:
        _standing = "INSUFFICIENT"
    elif confidence < 0.60 or _n_hard_ev == 0:
        _standing = "WEAK"
    else:
        _standing = "SUPPORTED"

    tr.stage("artifact.assembly", lambda: None, note="semua stage selesai")
    pipeline_trace = tr.to_dict()
    try:
        tr.save("traces")
    except Exception:
        pass  # the trace is best-effort — never let it fail the diagnosis
    return DiagnosisArtifact(
        status=status,  # type: ignore[arg-type]
        where_you_are=draft.where_you_are,
        primary_constraint=draft.primary_constraint,
        primary_constraint_id=draft.primary_constraint_id,
        secondary_constraints=draft.secondary_constraints,
        why=draft.why,
        do_not=do_not,
        do_not_detail=do_not_detail,
        next_best_action=draft.next_best_action,
        # Phase 7: the diagnosis is NOT an authoring surface for executable work any more. Whatever a
        # provider still returns for the legacy plan fields is dropped here, so no NEW day-by-day plan
        # can be created: the canonical Move (objective + action list + measurement) owns execution.
        # Existing artifacts keep their recorded plan as history (the fields stay in the schema).
        first_step_today="",
        day_by_day=[],
        outreach_script=draft.outreach_script,
        success_metric=draft.success_metric,
        well_know_when=draft.well_know_when,
        reassess_window_days=draft.reassess_window_days,
        pivot_rule=draft.pivot_rule,
        confidence=confidence,
        evidence_standing=_standing,  # type: ignore[arg-type]
        requires_new_evidence=(_standing != "SUPPORTED"),
        confidence_band=(  # F3+ (18 Sep): stable product surface across runs (G7)
            "HIGH" if confidence >= 0.65
            else "MEDIUM" if confidence >= 0.35
            else "LOW"
        ),
        constraint_confidence=conf_split["constraint_confidence"],
        revenue_impact_confidence=conf_split["revenue_impact_confidence"],
        decision_confidence=conf_split.get("decision_confidence", 0.0),
        experiment_confidence=conf_split.get("experiment_confidence", 0.0),
        hypothesis_ranking=ranking,
        knowledge_rules_applied=applied_rules,
        knowledge_activation={
            "e2e_phases": infer_e2e_phases(revenue_state),  # J4 (internal-docs §7)
            # J7 (internal-docs §7): audit trail of loop consumption — which context
            # this diagnosis consumed (prior verdict, demotion, reassess).
            "journey_context": journey_context,
            "tier1_matched": sorted({m.rule_id for m in kb_outcome.matched if m.tier == "deterministic"}),
            "tier2_matched": sorted({m.rule_id for m in kb_outcome.matched if m.tier != "deterministic"}),
            "flags": sorted(set(kb_outcome.flags)),
            "blocked_verdicts": sorted(set(kb_outcome.blocked)),
            "anti_patterns": kb_outcome.anti_notes,
            "degraded": kb_outcome.degraded,
            "coverage": kb_outcome.coverage,
            "rule_evidence_map": kb_outcome.rule_evidence_map,
            "interventions": [
                {
                    "id": i["intervention_id"],
                    "name": i["name"],
                    "for_constraint": i.get("for_constraint", ""),
                    "expected_evidence": i.get("expected_evidence", ""),
                }
                for i in kb_interventions
            ],
            # internal-docs §6.2: provenance NBA↔KB (Gate 3(d) internal-docs)
            "nba_grounding": nba_grounding,
        },
        reasoning_trace=reasoning_trace,
        provenance={
            "code_commit": code_commit_hash(),
            "kb_sha256": kb_sha256(),
        },
        constraint_map=constraint_map,
        revenue_state=revenue_state,
        possible_paths=possible_paths,
        layered_diagnosis=layered,
        causal_hypothesis=causal_hypothesis,
        opportunities=opportunities,
        decision_spectrum=spectrum,
        funnel_stages=FUNNEL_STAGES,
        metrics={
            "n_evidence_total": len(evidence),
            "n_evidence_historical": len(_hist),
            "n_hard_evidence": sum(
                1 for e in evidence
                if not getattr(e, "is_gap", False) and e.level in ("transactional", "outcome")
            ),
            "n_evidence_independent": n_independent,
            "n_evidence_clusters": len(ev_clusters),
            "n_topic_clusters": len(topic_counts),
            "topic_clusters": ", ".join(f"{k}:{v}" for k, v in topic_counts.items()),
            "n_evidence_mapped": len({i for ids in draft.evidence_map.values() for i in ids}),
            "mapping_coverage": round(
                len({i for ids in draft.evidence_map.values() for i in ids}) / max(1, len(evidence)), 2
            ),
            "constraint_confidence": conf_split["constraint_confidence"],
            "diagnosis_confidence": conf_split["diagnosis_confidence"],
            "decision_confidence": conf_split.get("decision_confidence", 0.0),
            "experiment_confidence": conf_split.get("experiment_confidence", 0.0),
            "revenue_impact_confidence": conf_split["revenue_impact_confidence"],
            "n_mechanisms": len(mech_map),
            "n_ranking": len(ranking),
        },
        engine_disagreement=engine_note,
        pipeline_trace=pipeline_trace,
    )
