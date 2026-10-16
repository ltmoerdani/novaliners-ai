"""Knowledge Rule Interpreter — internal-docs §8.4 (T1–T4).

ONE PIPELINE (replacing the 3 parallel paths from iter-20):

    evidence ledger + transcript          (working memory)
            │
            ├─ [TIER 1] evaluation.tier == "deterministic"
            │           predicate evaluator — 0 LLM, mandatory citation
            │
            ├─ [TIER 2] evaluation.tier == "judgment"
            │           LLM matcher (2 source groups, bounded menu, mandatory citation)
            │
            ├─ [MERGE]  one match set; deterministic wins on conflict
            │
            └─ [INDICATES] an evidence→constraint contribution ONLY if the rule
                        declares `evaluation.indicates` (explicit
                        presence) — `consequence.targets` is MODULATION,
                        not presence, so it must not be used to map evidence

Consequences (LOWER/RAISE/IGNORE/FLAG/BLOCK) are executed deterministically in
`apply_rule_consequences` AFTER scoring — separate from matching.

Enforced principles:
- **No ranking gate**: rules are evaluated against FACTS (evidence), not
  against derived artifacts (the ranking). The old `targets ∩ ranking_ids` gate
  let rules only correct what the LLM had already seen, never uncover what was
  missed (internal-docs §8.4 RC3).
- **Mandatory citation** (T3): a match without an evidence/quote reference is rejected. It
  closes the fake-provenance path & rules without an audit trail.
- **No proxy attribution**: a rule ID appears only when its condition was actually
  evaluated & satisfied. Evidence-quality signals (weak/no hard evidence)
  are a scoring concern, NOT rule attribution (internal-docs §8.4 RC1/RC2).
- **Safe degradation**: LLM down → tier-1 still runs; tier-2 is skipped and
  reported as `degraded` (not claimed active).
"""
from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from pydantic import BaseModel, Field

from core.llm import LLMProvider, schema_hint
from core.schema.constraints import HypothesisState
from core.schema.evidence import EvidenceItem
from core.schema.provenance import RuleSupport
from core.stages.rule_predicates import evaluate_predicate, trace_predicate_audit
from core.stages.rule_support import (
    strip_historical_anchors,
    support_from_branches,
    support_from_citation,
)

logger = logging.getLogger(__name__)

LOWER_FACTOR = 0.7
RAISE_FACTOR = 1.15
IGNORE_FACTOR = 0.85
BLOCK_FACTOR = 0.6
SCORE_CAP = 0.95

# Stage-2 (research 2411.10079 + 2608.20348): split the matcher per source group —
# reduces the multi-hop load per call. Semantics:
#   G1 = learning/validation/growth-experimentation (TM + VP + HG)
#   G2 = sales-interaction/retention/outbound-machine (CS + HK + PR)
# Every source MUST belong to exactly one group — judgment rules outside a group are
# never sent to the matcher (falsifiable coverage: 34/34 must be reachable).
SOURCE_GROUPS: tuple[tuple[str, ...], ...] = (("TM", "VP", "HG", "SP"), ("CS", "HK", "PR", "LC", "EM"))

# ── Tier-2 output contract (A, 23 Sep 2026) — TWO modes, default SPARSE ──────
#   KB_TIER2_SPARSE=1 (default) → only entries THAT MATCH are returned; non-matches
#     are deliberately NOT returned (absence = matched=false). The `evaluated` list
#     (rule ids claimed to be weighed) keeps coverage falsifiable.
#   KB_TIER2_SPARSE=0           → the old contract: ALL entries mandatory, 1/rule.
# Why sparse is the default: the verbose contract forces the model to name ~34–61 entries/group
# → measured 4,501–11,358 output tokens per call (30,413 tokens total / 124.2s
# wall in one run). Sparse targets a far smaller output; the recall safety net =
# evals/run_ab_tier2_contract.py (A/B on the same session's evidence).
_SYSTEM_TMPL = """You are a STRICT knowledge-rule matcher in a medical-grade diagnostic engine.
You receive: (1) an evidence ledger from a user interview, (2) a transcript tail,
(3) a numbered list of knowledge rules with natural-language conditions, and
(4) a list of known anti-patterns.

Your ONLY job: decide, per rule / anti-pattern, whether the user's ACTUAL
statements satisfy the condition. Rules:
{coverage}
- Match ONLY on what the user actually said/did — never on inference or filler.
- Many rules describe the user's OWN sales/customer interactions (how they
  pitch, how customers respond, how they handle discount requests, who they
  talk to). These apply when the user RECOUNTS such interactions — that is
  behavioral evidence, not filler. Example: "clients nod and agree it's exactly
  their problem, but deals die" MATCHES a rule about agreement-without-reframe.
- When genuinely unsure, matched = false. Silence is not evidence.
- CITE evidence: applied_to MUST contain an evidence id or a verbatim quote
  fragment. A match without a citation is discarded as invalid.
- Use ONLY the rule_id / pattern_id values given. Inventing IDs is a hard error.
Return JSON only."""

_COVERAGE_SPARSE = (
    "- SPARSE CONTRACT: only a few entries usually match. OMIT non-matching rules "
    "from `matches` entirely (absence = matched=false). List every rule_id you "
    "actually weighed in `evaluated` — ids only, no prose — so coverage stays auditable."
)
_COVERAGE_VERBOSE = "- Return an entry for EVERY rule and EVERY anti-pattern listed — no skipping."


def _tier2_sparse() -> bool:
    """Is the sparse contract active? Default yes; KB_TIER2_SPARSE=0 = the old contract (A/B/revert)."""
    return os.environ.get("KB_TIER2_SPARSE", "1") == "1"


def _system_prompt() -> str:
    """SYSTEM with the contract bullet per mode — the rest of the text is identical in both modes."""
    return _SYSTEM_TMPL.replace(
        "{coverage}", _COVERAGE_SPARSE if _tier2_sparse() else _COVERAGE_VERBOSE
    )


class RuleMatch(BaseModel):
    rule_id: str
    matched: bool = False
    applied_to: str = ""
    reason: str = ""
    tier: str = Field(default="judgment", description="deterministic | judgment (match origin)")
    # Canonical provenance (internal-docs §6.1): which evidence made this rule matched.
    # None = not computed yet / not matched. `UNSUPPORTED` = matched but the anchor cannot be verified —
    # it must NOT ground path candidates (the old scoring keeps using `matched` as-is).
    support: Optional[RuleSupport] = None


class AntiPatternMatch(BaseModel):
    pattern_id: str
    matched: bool = False
    applied_to: str = ""
    reason: str = ""


class RuleMatchSet(BaseModel):
    matches: list[RuleMatch] = Field(default_factory=list)
    anti_patterns: list[AntiPatternMatch] = Field(default_factory=list)
    # Sparse contract: rule_ids the model claims were actually weighed. Without it,
    # "not returned" has TWO meanings (no-match vs skipped) — this list is what
    # keeps coverage falsifiable when no-match entries are not returned.
    evaluated: list[str] = Field(
        default_factory=list,
        description='rule_id actually evaluated (id only, no prose)',
    )


class KnowledgeRuleOutcome:
    """Matching results + consequences. Consumed by diagnosis.py."""

    def __init__(self) -> None:
        # matching results (before scoring)
        self.matches: list[RuleMatch] = []
        self.anti_patterns: list[AntiPatternMatch] = []
        # Populated only when a rule declares `evaluation.indicates`
        # (explicit-presence semantics). Empty by default.
        self.rule_evidence_map: dict[str, list[str]] = {}
        self.coverage: dict = {}
        self.degraded: bool = False
        # filled by apply_rule_consequences (after scoring)
        self.extra_rule_ids: list[str] = []
        self.flags: list[str] = []
        self.blocked: list[str] = []
        self.anti_notes: list[str] = []
        self.note: str = ""
        # rules that matched but whose anchors are unverified (UNSUPPORTED): their consequences are NOT
        # executed (doc 14 §6.1/§22 — UNSUPPORTED = epistemic UNKNOWN, not TRUE; Kleene: a consequence
        # must not fire from an unknown state). Audit-only.
        self.unsupported_rule_ids: list[str] = []

    @property
    def matched(self) -> list[RuleMatch]:
        return [m for m in self.matches if m.matched]

    @property
    def matched_ids(self) -> list[str]:
        return [m.rule_id for m in self.matched]

    def rule_supports(self) -> dict[str, RuleSupport]:
        """rule_id -> provenance for ALL matched rules (SUPPORTED and UNSUPPORTED alike). The navigation
        consumer decides: only `anchored` rules may act as TRUE signals. A matched rule without support
        counts as UNSUPPORTED — provenance is never assumed."""
        out: dict[str, RuleSupport] = {}
        for m in self.matched:
            out[m.rule_id] = m.support or RuleSupport(
                rule_id=m.rule_id, tier=m.tier, reason="rule matched tanpa provenance yang dihitung"
            )
        return out

    @property
    def any_signal(self) -> bool:
        return bool(self.extra_rule_ids or self.flags or self.blocked or self.anti_notes)


# ---------------------------------------------------------------------------
# Candidates: ALL active-source rules (T2 — no ranking gate)
# ---------------------------------------------------------------------------

def _active_sources() -> set[str]:
    from engine.knowledge import active_rule_sources

    return active_rule_sources()


def candidate_rules(group: tuple[str, ...] | None = None) -> list[dict]:
    """Rules from activated sources (rule_activation.json), pre-reranked by the source's
    authority grade (Phase 3,
    internal-docs §6.2e): empirical_research > practitioner_playbook > conceptual_framework,
    tie-break on rule_id (deterministic). This order sets priority under the top-k cap
    (internal-docs §6.2c) and the presentation order in the tier-2 prompt."""
    from engine.knowledge import get_kb, source_grades

    allowed = _active_sources()
    if group is not None:
        allowed = allowed & set(group)
    rules = [r for rid, r in get_kb()["rules"].items() if rid.split("-")[0] in allowed]
    grades = source_grades()
    return sorted(
        rules,
        key=lambda r: (grades.get(r["rule_id"].split("-")[0], 9), r["rule_id"]),
    )


def candidate_anti_patterns(group: tuple[str, ...] | None = None) -> list[dict]:
    from engine.knowledge import get_kb

    allowed = _active_sources()
    if group is not None:
        allowed = allowed & set(group)
    return [a for aid, a in get_kb()["anti_patterns"].items() if aid.split("-")[0] in allowed]


# ---------------------------------------------------------------------------
# TIER 1 — predicate evaluator (0 LLM)
# ---------------------------------------------------------------------------

def evaluate_rule_tier1(rule: dict, evidence: list[EvidenceItem], transcript_tail: str) -> RuleMatch:
    """ONE deterministic rule -> RuleMatch with provenance. Used by `match_tier1` + the provenance tests."""
    ev = rule.get("evaluation") or {}
    predicate = ev.get("predicate") or {}
    matched, cited, reason = evaluate_predicate(predicate, evidence, transcript_tail)
    m = RuleMatch(
        rule_id=rule["rule_id"],
        matched=matched,
        applied_to=", ".join(cited[:3]),
        reason=reason,
        tier="deterministic",
    )
    if matched:
        traced, branches, un_required, assumed = trace_predicate_audit(predicate, evidence, transcript_tail)
        # the trace uses the same leaves as the evaluator; if the two disagree, no support is built.
        # `un_required` = required positive branches without a verified anchor → UNSUPPORTED (per-branch
        # provenance: aggregate evidence from sibling branches must not hide them, doc 14 §6.1).
        # `assumed` = absence conditions relied upon by the match: recorded, not anchors (absence contract).
        m.support = (
            support_from_branches(
                m.rule_id, branches, evidence, unanchored_required=un_required, assumptions=assumed
            )
            if traced
            else RuleSupport(
                rule_id=m.rule_id, tier="deterministic", reason="trace tidak sepakat dengan evaluator"
            )
        )
    return m


def match_tier1(
    evidence: list[EvidenceItem], transcript_tail: str
) -> list[RuleMatch]:
    return [
        evaluate_rule_tier1(r, evidence, transcript_tail)
        for r in candidate_rules()
        if (r.get("evaluation") or {}).get("tier") == "deterministic"
    ]


# ---------------------------------------------------------------------------
# TIER 2 — LLM matcher per group (bounded menu + verification loop)
# ---------------------------------------------------------------------------

def _build_prompt(evidence, transcript_tail, rules, anti_patterns) -> str:
    ev_lines = "\n".join(
        f"- [{e.id}] ({e.level}{' · GAP' if e.is_gap else ''}) {e.signal}" for e in evidence
    ) or "- (none)"
    # PHASE 1 (internal-docs §5.1): compilation rubric — a compact line per rule from
    # compiled_rubrics.json; verbose fallback when the rubric is missing/does not cover.
    # Valid IDs are unchanged → the verification loop still applies.
    try:
        from engine.knowledge import rubric_lines

        rubric = rubric_lines()
    except Exception:
        rubric = {}
    rule_lines = "\n".join(
        rubric.get(r["rule_id"])
        or f"- {r['rule_id']}: IF {(r.get('matcher_hint') or r['condition'])} "
        f"(targets: {', '.join(r.get('consequence', {}).get('targets', []))})"
        for r in rules
    )
    ap_lines = "\n".join(
        f"- {a['pattern_id']}: {a.get('pattern') or a.get('anti_pattern') or a.get('name', '')}"
        + (f" — symptom: {a['symptom']}" if a.get("symptom") else "")
        for a in anti_patterns
    )
    return f"""EVIDENCE LEDGER:
{ev_lines}

TRANSCRIPT TAIL:
{transcript_tail}

KNOWLEDGE RULES (match against evidence/transcript ONLY):
{rule_lines or '(none)'}

ANTI-PATTERNS (behavior patterns to detect in user's own conduct):
{ap_lines or '(none)'}

Return JSON:
{schema_hint(RuleMatchSet)}"""


def _match_group(
    llm: LLMProvider, evidence, transcript_tail, group
) -> tuple[Optional[RuleMatchSet], bool]:
    """Tier-2 matcher for one group. Return (result, had_candidates)."""
    rules = [
        r for r in candidate_rules(group)
        if (r.get("evaluation") or {}).get("tier") == "judgment"
    ]
    anti_patterns = candidate_anti_patterns(group)
    if not rules and not anti_patterns:
        return None, False

    valid_rule_ids = {r["rule_id"] for r in rules}
    valid_ap_ids = {a["pattern_id"] for a in anti_patterns}
    prompt = _build_prompt(evidence, transcript_tail, rules, anti_patterns)

    def _finalize(res):
        """Final normalization of one group's result — used by BOTH the success path and the fallback.
        Drop ids outside the group menu, set tier, and filter `evaluated` (the sparse
        contract) to valid rule_ids — ids outside the menu are not trusted."""
        res.matches = [m for m in res.matches if m.rule_id in valid_rule_ids]
        res.anti_patterns = [a for a in res.anti_patterns if a.pattern_id in valid_ap_ids]
        for m in res.matches:
            m.tier = "judgment"
        ev = getattr(res, "evaluated", None)
        if isinstance(ev, list):
            res.evaluated = [e for e in ev if e in valid_rule_ids]
        return res

    # E1 (23 Sep 2026): a corrective retry = a SECOND LLM call resending the FULL
    # prompt (including the whole rule menu). Measured on one finalize run:
    # retries hit BOTH groups → 4 calls = 124.9s of 162.2s total. The attempt-1
    # result is still kept (unknown IDs are filtered in the block below), so retry
    # is now OPT-IN via ENABLE_KB_RETRY=1. Unknown IDs are ALWAYS logged so the
    # root cause can be diagnosed from real runs — not guessed.
    retry_enabled = os.environ.get("ENABLE_KB_RETRY", "0") == "1"
    feedback = ""
    for _attempt in range(2 if retry_enabled else 1):
        try:
            result = llm.structured_call(RuleMatchSet, _system_prompt(), prompt + feedback)
        except Exception:
            return None, True
        if not isinstance(result, RuleMatchSet):
            return None, True
        bad_rules = [m.rule_id for m in result.matches if m.rule_id not in valid_rule_ids]
        bad_aps = [a.pattern_id for a in result.anti_patterns if a.pattern_id not in valid_ap_ids]
        if not bad_rules and not bad_aps:
            return _finalize(result), True
        logger.warning(
            "kb_tier2_unknown_ids group=%s attempt=%d rules=%s anti_patterns=%s",
            "+".join(group), _attempt + 1, bad_rules[:8], bad_aps[:8],
        )
        feedback = (
            f"\n\n--- VERIFICATION FAILED: ID tidak dikenal {bad_rules + bad_aps}. "
            f"Gunakan HANYA ID berikut — rules: {sorted(valid_rule_ids)}, "
            f"anti-patterns: {sorted(valid_ap_ids)}. Perbaiki output Anda."
        )
    return _finalize(result), True


def _has_citation(text: str) -> bool:
    t = (text or "").strip()
    return len(t) >= 4 and t.lower() not in {"none", "n/a", "-", "tidak ada"}


# ---------------------------------------------------------------------------
# ENTRY — matching only (called BEFORE scoring, T2)
# ---------------------------------------------------------------------------

def run_knowledge_rules(
    llm: LLMProvider,
    evidence: list[EvidenceItem],
    transcript: str,
    llm_transcript_tail: str | None = None,
    historical_evidence: list[EvidenceItem] | None = None,
) -> KnowledgeRuleOutcome:
    """Match tier-1 + tier-2 → one outcome (scores untouched). Degrade-safe.

    `transcript` = the FULL transcript. Tier-1 (predicate) sees all of it because
    there is no token cost — truncating it starves deterministic rules of facts
    (proven: TM-R01 failed to match because the relevant statement sat in an early turn).
    Only tier-2 (LLM) uses `llm_transcript_tail` for prompt budget.
    """
    out = KnowledgeRuleOutcome()
    try:
        llm_tail = (
            llm_transcript_tail
            if llm_transcript_tail is not None
            else "\n".join((transcript or "").strip().splitlines()[-12:])
        )
        enabled = candidate_rules()
        by_source: dict[str, dict[str, int]] = {}
        for r in enabled:
            src = r["rule_id"].split("-")[0]
            d = by_source.setdefault(src, {"enabled": 0, "matched": 0})
            d["enabled"] += 1

        # --- tier 1: deterministic, no LLM, FULL transcript ---
        t1 = match_tier1(evidence, transcript)
        t1_matched = {m.rule_id for m in t1 if m.matched}
        out.matches.extend(t1)

        # --- tier 2: judgment via LLM (failure → skipped, not claimed) ---
        judged_ids: set[str] = set()
        tier2_requested = 0
        llm_failed_groups: list[str] = []
        attempted_groups: list[str] = []
        # E2 (23 Sep 2026): source groups are INDEPENDENT (separate rulesets, anti-patterns,
        # prompts) → run them in parallel. Measured: 2 groups × ~22–47s when sequential.
        # Results come back via ex.map (input order preserved) and are processed below
        # in the ORIGINAL group order → the out.matches order is identical to the sequential version.
        # Snapshot the session id on this thread, then each worker sets it itself
        # (thread-local, see core/llm.py::use_session).
        _sid_getter = getattr(llm, "current_session_id", None)
        sid = _sid_getter() if callable(_sid_getter) else ""

        def _run_group(group):
            if sid and hasattr(llm, "use_session"):
                llm.use_session(sid)
            grp_judgment = [
                r["rule_id"] for r in candidate_rules(group)
                if (r.get("evaluation") or {}).get("tier") == "judgment"
            ]
            return group, grp_judgment, _match_group(llm, evidence, llm_tail, group)

        groups = list(SOURCE_GROUPS)
        if len(groups) > 1:
            with ThreadPoolExecutor(max_workers=len(groups), thread_name_prefix="kb-group") as ex:
                group_results = list(ex.map(_run_group, groups))
        else:
            group_results = [_run_group(groups[0])]

        for group, grp_judgment, (result, had) in group_results:
            if not had:
                continue
            attempted_groups.extend(grp_judgment)
            tier2_requested += len(grp_judgment)
            if result is None:
                llm_failed_groups.append("+".join(group))
                continue
            # Sparse contract: claimed-evaluated ids also mark coverage —
            # without them "not returned" cannot be told apart between
            # "evaluated, no-match" vs "skipped" (see coverage below).
            grp_ids = set(grp_judgment)
            judged_ids.update(
                e for e in (getattr(result, "evaluated", None) or []) if e in grp_ids
            )
            for m in result.matches:
                judged_ids.add(m.rule_id)
                if m.matched and not _has_citation(m.applied_to):
                    # T3: a match without a citation = not auditable → reject
                    m.matched = False
                    m.reason = (m.reason + " | ditolak: tanpa sitasi evidence").strip(" |")
                if m.matched:
                    # LLM citations are verified against the ledger/transcript;
                    # unverifiable ones = UNSUPPORTED
                    m.support = support_from_citation(m.rule_id, m.applied_to, evidence, transcript)
                out.matches.append(m)
            for a in result.anti_patterns:
                if a.matched and not _has_citation(a.applied_to):
                    a.matched = False
                    a.reason = (a.reason + " | ditolak: tanpa sitasi").strip(" |")
                out.anti_patterns.append(a)

        if llm_failed_groups:
            out.degraded = True

        # DCP-01: superseded claims must not anchor the current state through
        # transcript quotes. Evidence ids are already current-only; historical quotes are cleaned here.
        # `evidence` (current) is passed along too so MIXED quotes containing active facts are not
        # discarded (audit 14 Oct 2026).
        if historical_evidence:
            for m in out.matches:
                if m.matched:
                    m.support = strip_historical_anchors(m.support, historical_evidence, evidence)

        # --- INFER (T2): evidence→constraint contribution from matched rules ---
        #
        # IMPORTANT (eval finding S1): `consequence.targets` means MODULATION
        # ("shift this constraint's score"), NOT PRESENCE ("this evidence supports
        # this constraint"). Deriving presence from modulation is unsound:
        # TM-R08 (the user has a real commitment) targets V2.4 "Value-Proof Gap"
        # as a RAISE target — while a real commitment means the gap is SMALL.
        # Injecting evidence into V2.4 pushed it to ranking[0] and collapsed the
        # separation (S1: 0.635 -> 0.193).
        #
        # Knowledge maps evidence ONLY when the rule DECLARES
        # `evaluation.indicates` (explicit-presence semantics). Default: empty —
        # no inference from ambiguous relations.
        rules_by_id = {r["rule_id"]: r for r in enabled}
        for m in out.matches:
            if not m.matched:
                continue
            rule = rules_by_id.get(m.rule_id)
            if not rule:
                continue
            indicates = (rule.get("evaluation") or {}).get("indicates") or []
            if not indicates:
                continue
            # T2-CAUSAL (doc 14 §6.1/§22): only verified anchors (SUPPORTED support) may map evidence
            # to constraints. Raw citations are NOT used: fabricated ids or unfound quotes
            # (UNSUPPORTED) inject nothing into evidence_map — injecting them would let unverified
            # evidence shift scoring through the side door.
            sup = m.support
            if sup is None or not sup.anchored:
                continue
            for target in indicates:
                bucket = out.rule_evidence_map.setdefault(target, [])
                for c in sup.evidence_ids:
                    if c not in bucket:
                        bucket.append(c)

        # --- coverage report (T4): falsifiable, not a claim ---
        # tier-2 "requested" ≠ "returned": the LLM may skip entries. Rules that
        # are not returned do NOT count as evaluated — that is what makes the coverage
        # claim testable rather than merely trusted.
        # SPARSE contract (default): no-match entries are deliberately not returned,
        # so the `evaluated` list (ids claimed to be weighed) carries the
        # falsifiability; the `contract` field records the mode that produced this artifact.
        for m in out.matches:
            src = m.rule_id.split("-")[0]
            if m.matched:
                by_source.setdefault(src, {"enabled": 0, "matched": 0})["matched"] += 1
        tier1_ids = {m.rule_id for m in t1}
        attempted_judgment = set(attempted_groups)
        out.coverage = {
            "rules_enabled": len(enabled),
            "tier1_evaluated": len(tier1_ids),
            "tier2_requested": tier2_requested,
            "tier2_returned": len(judged_ids),
            "tier2_missing": sorted(attempted_judgment - judged_ids),
            "contract": "sparse" if _tier2_sparse() else "verbose",
            "rules_evaluated": len(tier1_ids) + len(judged_ids),
            "rules_matched": len({m.rule_id for m in out.matches if m.matched}),
            # T2-CAUSAL: matched ≠ execution-eligible — UNSUPPORTED ones are recorded as an audit fact
            # but execute no consequences (zero score/navigation causality, doc 14 §6.1/§22).
            "rules_unsupported": sorted(
                {
                    m.rule_id
                    for m in out.matches
                    if m.matched and (m.support is None or not m.support.anchored)
                }
            ),
            "rules_consequence_eligible": sorted(
                {
                    m.rule_id
                    for m in out.matches
                    if m.matched and m.support is not None and m.support.anchored
                }
            ),
            "tier1_matched": sorted(t1_matched),
            "llm_failed_groups": llm_failed_groups,
            "by_source": by_source,
            "anti_patterns_evaluated": len(out.anti_patterns),
        }
        return out
    except Exception as exc:  # never fail the diagnosis
        out.degraded = True
        out.coverage = {"error": f"{type(exc).__name__}: {exc}"}
        return out


# ---------------------------------------------------------------------------
# CONSEQUENCES — deterministic, AFTER scoring (shifts effective_score)
# ---------------------------------------------------------------------------

def _rule_by_id() -> dict:
    from engine.knowledge import get_kb

    return get_kb()["rules"]


def _anchored(m: RuleMatch) -> bool:
    """A match may execute consequences only when its basis is verified.

    doc 14 §6.1/§22: a match with `RuleSupport.status == UNSUPPORTED` means the claim is known to EXIST
    but its basis cannot be shown — epistemically UNKNOWN, not TRUE. Consequences do not fire from
    unknown states (Kleene), in either the positive direction (RAISE_CONFIDENCE) or the negative
    one (LOWER_CONFIDENCE/BLOCK/IGNORE): moving any score from an unverified anchor means treating
    UNKNOWN as fact. `support is None` (not computed yet) is treated the same — provenance is never
    assumed."""
    return m.support is not None and m.support.anchored


def apply_rule_consequences(
    ranking: list[HypothesisState], outcome: KnowledgeRuleOutcome
) -> KnowledgeRuleOutcome:
    """Execute the consequences of rules that matched AND have verified anchoring → effective_score + notes.

    UNSUPPORTED matches (unverified citations / required branches without anchors) are recorded in
    `unsupported_rule_ids` + an audit note — their consequences are NOT executed: the score does not
    move on evidence that cannot be shown (UNSUPPORTED has zero navigation causality, including via
    the legacy score — doc 14 §22)."""
    if not ranking or not outcome.matches:
        return outcome

    by_cid = {h.constraint_id: h for h in ranking}
    rules = _rule_by_id()
    penalized: set[str] = set()
    boosted: set[str] = set()

    for m in outcome.matches:
        if not m.matched:
            continue
        if not _anchored(m):
            if m.rule_id not in outcome.unsupported_rule_ids:
                outcome.unsupported_rule_ids.append(m.rule_id)
            continue
        rule = rules.get(m.rule_id)
        if rule is None:
            continue
        cons = rule.get("consequence", {})
        action = cons.get("action", "")
        targets = [t for t in cons.get("targets", []) if t in by_cid]
        if m.rule_id not in outcome.extra_rule_ids:
            outcome.extra_rule_ids.append(m.rule_id)

        for t in targets:
            h = by_cid[t]
            base = h.effective_score if h.effective_score is not None else h.score
            if action == "LOWER_CONFIDENCE" and t not in penalized:
                h.effective_score = round(base * LOWER_FACTOR, 3)
                penalized.add(t)
            elif action == "RAISE_CONFIDENCE" and t not in penalized and t not in boosted:
                h.effective_score = round(min(base * RAISE_FACTOR, SCORE_CAP), 3)
                boosted.add(t)
            elif action == "IGNORE_SIGNAL" and t not in penalized:
                h.effective_score = round(base * IGNORE_FACTOR, 3)
                penalized.add(t)
            elif action == "BLOCK_VERDICT":
                if t not in penalized:
                    h.effective_score = round(base * BLOCK_FACTOR, 3)
                    penalized.add(t)
                outcome.blocked.append(t)
            elif action == "FLAG_SEGMENT":
                outcome.flags.append(t)

    for a in outcome.anti_patterns:
        if a.matched:
            detail = a.reason or (a.applied_to or "")[:100]
            outcome.anti_notes.append(f"{a.pattern_id}: {detail}".strip(" —"))

    if outcome.any_signal:
        ranking.sort(
            key=lambda h: (
                -(h.effective_score if h.effective_score is not None else h.score),
                h.constraint_id,
            )
        )

    notes: list[str] = []
    _executed = {m.rule_id for m in outcome.matches if m.matched and _anchored(m)}
    _tier_of = {m.rule_id: m.tier for m in outcome.matches if m.matched}
    t1 = sorted(rid for rid in _executed if _tier_of.get(rid) == "deterministic")
    t2 = sorted(rid for rid in _executed if _tier_of.get(rid) != "deterministic")
    if t1:
        notes.append("TIER-1 RULES (predicate deterministik, 0 LLM): " + ", ".join(t1))
    if t2:
        notes.append("TIER-2 RULES (LLM-matched, sitasi terverifikasi): " + ", ".join(t2))
    unsup = sorted(set(outcome.unsupported_rule_ids) - _executed)
    if unsup:
        notes.append(
            "RULE MATCHED TANPA ANCHOR TERVERIFIKASI — konsekuensi TIDAK dieksekusi, skor tidak "
            "bergerak oleh anchor yang tidak dapat ditunjukkan (doc 14 §6.1): " + ", ".join(unsup)
        )
    for m in outcome.matches:
        if not m.matched or m.rule_id not in rules or m.rule_id not in _executed:
            continue
        _r = rules[m.rule_id].get("consequence", {}).get("rationale", "")
        _c = (m.applied_to or "").strip()
        if _r:
            notes.append(f"  · {m.rule_id} «{_c[:80]}» — {_r[:100]}")
    if outcome.flags:
        notes.append(
            "FLAG SEGMENT (konfirmasi sebelum intervensi): " + ", ".join(sorted(set(outcome.flags)))
        )
    if outcome.blocked:
        notes.append(
            "VERDICT DIBLOKIR knowledge rule untuk "
            + ", ".join(sorted(set(outcome.blocked)))
            + " — jangan beri GO/SCALE untuk constraint ini sampai kondisi rule terpenuhi."
        )
    if outcome.anti_notes:
        notes.append("ANTI-PATTERN terdeteksi:\n- " + "\n- ".join(outcome.anti_notes))
    if outcome.degraded:
        failed = outcome.coverage.get("llm_failed_groups") or ["error"]
        notes.append(
            "⚠ KNOWLEDGE MATCHER DEGRADED: sebagian rule tier-2 tidak dievaluasi "
            f"({', '.join(failed)}) — rule tersebut TIDAK diklaim aktif."
        )
    outcome.note = "\n\n".join(notes)
    return outcome
