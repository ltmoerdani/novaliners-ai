"""D-A2 LAYER C — second-pass verifier for PROSE requirements (int 04/09 §6.7, LOCKED 26 Sep).

The contract implemented (not invented) here:

    PROPOSED mapping (from the deterministic mapper, path B failed because the rule is still PROSE)
      -> SECOND-PASS VERIFIER (LLM provider-agnostic, independent of the mapper)
      -> verdict per claim: citation + rule branch (sufficient/partial/contradicting/none)
      -> deterministic grounding check (citation MUST be an exact substring of the evidence)
      -> VERIFIED mapping with verification_method='second_pass_verified'
      -> (unit-requirement) B1-exact unit_context sidecar
      -> rule_evaluation + citations per branch -> adjudicate() REMAINS the status authority (RR7/D6)

What is DELIBERATELY not done (epistemic honesty, not a shortcoming):
  - The verifier NEVER writes status (PRESENT/PARTIAL/UNKNOWN/ABSENT). It only verifies the
    RELATION claim->requirement + which branch the citation contains. Status remains the output of
    `core/stages/adjudicate.adjudicate` via the D-A1b resolution table (expected_status).
  - Total degradation: LLM failure/timeout/refusal/invalid output -> UNRESOLVED; the requirement
    falls to UNKNOWN; the turn does NOT crash (CP-25). Never a 500 from this layer.
  - Desire / assumption / gap / superseded are NEVER sent to the verifier (the admissibility gate
    R4 already filters up front; this layer re-checks defensively — negative example BC-01).
  - NO keyword/synonym/regex as a meaning gate (RC-06, BC-07): the only deterministic text check
    here is CITATION GROUNDING (provenance: the citation must be an exact substring of the
    referenced evidence — the same pattern as the so.v1 verifier), not meaning matching.
  - Bilingual by design: rule prose is Indonesian, citations may be ID/EN/mixed. Language never
    lowers a claim's entitlement (BC-07).

Audit (BC-03): every verdict records claim_id + event_id + exact citation + requirement_id +
registry fingerprint + prompt contract version + provider/model + timestamp. The audit does NOT live
in the VERIFIED mapping object (AD9: exact-key) — it is passed through to the
`run_live_adjudication` summary (stored in `session.last_adjudication`).

Call budget: one call per prose requirement with >=1 admissible candidate;
cache per (registry fingerprint, rid, candidate digest) so replay + the next turn are cheap
(new evidence only invalidates the cache of requirements whose candidates changed).
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from ontology.mapper.contract import UNIT_DOMAINS

SPV_CONTRACT_VERSION = "spv.v1"
PROPOSED_BY = "second_pass_v1"

# Roles that are NOT state evidence (BC-01 negative test): desire and assumption are recognized
# semantically but must not satisfy any requirement through this path.
_NON_EVIDENCE_ROLES = frozenset({"desire", "assumption"})

# ── LLM output contract (Pydantic; free field NAMES except reasoning/thinking) ──────


class ClaimCheck(BaseModel):
    """Verdict for one candidate claim. `basis` = short reason WITH CITATION (not 'reasoning')."""

    evidence_ref: str = Field(description="id of the evidence examined (verbatim from input)")
    quote: str = Field(default="", description="EXACT substring of the claim quote the verdict rests on")
    branch: Literal["sufficient", "partial", "contradicting", "none"] = "none"
    unit_key: Optional[str] = Field(
        default=None, description="for multi-unit requirements: the 'kind:id' unit the claim refers to")
    basis: str = Field(default="", max_length=400, description="short reason naming a word from the quote")


class SecondPassCheck(BaseModel):
    contract_version: str = SPV_CONTRACT_VERSION
    requirement_id: str
    claim_checks: list[ClaimCheck] = Field(default_factory=list)


# ── prompt (bilingual by design; strict grounding) ─────────────────────────────────────────────

SPV_SYSTEM = """You are the SECOND-PASS VERIFIER of the evidence-to-requirement mapping layer
(contract spv.v1). A deterministic mapper PROPOSED that certain recorded claims may relate to one
requirement of a registry. You independently verify each proposal against the requirement's rule.

YOUR ROLE: verify the proposed claim->requirement mapping ONLY. You are NOT an interviewer, NOT a
diagnoser, and you NEVER decide a requirement status (PRESENT/PARTIAL/UNKNOWN/ABSENT). Status is
computed later by a deterministic adjudicator from the branches you confirm.

INPUT per call: one requirement (id, definition, observability, and the full satisfaction_rule text
in Indonesian) plus the candidate claims (semantic role, aspect, tense, epistemic grade, typed
quantity, and the claim's verbatim quote).

GROUNDING RULES (absolute):
1. Judge ONLY from the verbatim quote of each claim, word for word. No outside knowledge about the
   business, no assumptions, no inference beyond what the quote itself states.
2. The rule text is Indonesian; quotes may be Indonesian, English, or mixed (code-switch). Language
   NEVER affects the verdict: judge MEANING, never keywords. Do not look for literal words from the
   rule inside the quote.
3. A wish/desire ("I want to...", "I wish...") or an untested assumption/guess is NOT evidence of a
   present condition. A statement of missing data ("I don't have / I don't know") is NOT evidence
   either. A past event only counts when the branch is explicitly about history or what happened.
4. Approximate quantities ("about", "around", "sekitar") still count as quantities: approximate is
   not absent.
5. For each claim choose exactly one branch:
   - "sufficient": the quote, on its own, fully establishes the branch's condition.
   - "partial": the quote establishes part of the condition and the requirement's mode is PARTIAL.
   - "contradicting": the quote establishes the branch's negative condition (evidence AGAINST).
   - "none": ONLY when the quote genuinely does not address the condition — it is about something
     else, too vague to establish anything, or merely a wish/assumption/gap.
   CALIBRATION (insiden 17 Okt, sesi c913b0b51579: 46/48 verdict "none" padahal kutipan polos
   mendeskripsikan kondisi rule): "none" is NOT a safe default and must NOT be used to avoid
   deciding. If the quote plainly DESCRIBES or ESTABLISHES the branch's condition — even in
   different words, another language, or informal phrasing — you MUST choose sufficient/partial
   decisively. Example: for a rule about recurring outreach cadence, "every time I try, a client
   emergency pulls me off and the routine dies by Wednesday" plainly establishes the condition
   (attempted cadence repeatedly collapses) — that is sufficient/partial territory, NOT "none".
   MONEY-COMMITMENT CALIBRATION (insiden 18 Okt, sesi EN 756ad4667095: "4 active clients per
   month" + "revenue around Rp12 million per month" judged "none" against a real-money-commitment
   rule): for rules about willingness to pay / money already committed at a price, a plainly
   stated running-business fact — active or recurring paying clients, monthly revenue from
   clients, a deposit/payment already received, work currently being delivered for pay — IS a
   real money commitment at the current price: that is sufficient territory, NOT "none". What
   remains "none": hypotheticals ("if even one of them pays"), wishes, plans never offered, or
   price inquiries that never converted.
   CONTRADICTION DISAMBIGUATION (insiden 18 Okt, sesi 7f2e13b1fcbe: "Nobody has ever paid a
   deposit for it" — a NEW untested package — was judged 'contradicting' for the CURRENT-price
   willingness-to-pay rule, flipping PRESENT→ABSENT→UNKNOWN+conflict across turns):
   'contradicting' requires the quote to DENY THE SAME OBJECT the rule is about. For
   willingness to pay at the CURRENT price, only evidence that buyers refuse, stop, or never
   started paying the CURRENT price contradicts. Statements about a DIFFERENT object (a new
   untested package, a different price point, a hypothetical) are 'none' for this rule, never
   'contradicting'. When the object differs, choose 'none'.
   Judgment is your job: the deterministic grounding gate after you already discards any verdict
   whose quote is not verbatim, so you never create a false fact by choosing a positive branch on
   a real quote. What remains forbidden: stretching a quote BEYOND what it says, treating a
   wish/assumption/gap as a present condition, or inventing conditions the quote never mentions.
6. For unit-multiplexed requirements (a unit kind list is provided), also say which unit the claim
   is about, as unit_key "<kind>:<short-id>" (short stable id from the quote, e.g.
   "kesepakatan:office-subscription"). A claim that does not identify any single unit gets
   unit_key null and can only support a "none" verdict.
7. Copy into `quote` the exact words (substring) of that claim's quote that your verdict rests on.
   A verdict whose quote is not found verbatim in the claim WILL BE DISCARDED by the deterministic
   gate.
8. `basis` is max 30 words and must quote the user's own words, not your paraphrase.

OUTPUT CONTRACT: JSON only, matching spv.v1:
{"contract_version":"spv.v1","requirement_id":"<same id as input>","claim_checks":[
 {"evidence_ref":"<id>","quote":"<exact substring>","branch":"sufficient|partial|contradicting|none",
  "unit_key":null,"basis":"<short, quoted>"}]}

If you cannot verify anything (unclear, insufficient, or you decline), return claim_checks: [] or
all branches "none". That is a valid, expected answer. Never invent evidence_ref values that were
not in the input."""

MAX_CANDIDATES_PER_REQUIREMENT = 8  # context budget: max candidates per prose requirement

# PARALLEL PREFETCH (16 Oct 2026, second_pass_s=49s incident): the per-requirement LLM call
# is pure independent I/O (different requirements, different candidates, different cache keys;
# the grounding gate & verdict aggregation still run SEQUENTIALLY below). Parallelization
# only speeds up network waiting — ALL contracts (spv.v1, cache key, adjudicator as the
# single status authority, BC-03 audit per verdict) are unchanged.
# Rate-limit safe: Gemini/Vertex quotas are far above 4 RPM for a small burst;
# `NOVALINERS_SPV_PARALLEL=1` restores the old sequential behavior (1-env-var rollback).
SPV_MAX_PARALLEL = max(1, int(os.environ.get("NOVALINERS_SPV_PARALLEL", "4")))


def _claim_line(eid: str, ev: Any, node: dict[str, Any]) -> str:
    qty = node.get("quantity")
    qty_txt = ""
    if isinstance(qty, dict):
        qty_txt = (f" | quantity={json.dumps(qty, ensure_ascii=False)}")
    role = getattr(ev, "claim_role", "") or node.get("type", "") or "claim"
    aspect = node.get("aspect") or ""
    tense = node.get("tense") or ""
    epi = getattr(ev, "epistemic", "") or node.get("epistemic", "") or ""
    quote = (getattr(ev, "source_quote", None) or getattr(ev, "signal", "") or "")
    sig = getattr(ev, "signal", "") or ""
    return (f"- evidence_ref: {eid}\n  role={role}"
            + (f" aspect={aspect}" if aspect else "")
            + (f" tense={tense}" if tense else "")
            + (f" epistemic={epi}" if epi else "")
            + qty_txt
            + f"\n  summary: {sig[:200]}\n  quote: \"{quote[:600]}\"")


def build_user_prompt(entry: dict[str, Any], candidates: list[tuple[str, Any, dict[str, Any]]]) -> str:
    rule = entry.get("satisfaction_rule") or {}
    rid = entry["requirement_id"]
    units = UNIT_DOMAINS.get(rid)
    unit_line = (f"\nUNIT KINDS (this requirement is unit-multiplexed; each verdict needs a unit_key): "
                 f"{sorted(units)}" if units else "")
    return f"""REQUIREMENT {rid}
definition: {entry.get('definition', '')}
observability:
{chr(10).join('- ' + o for o in (entry.get('observability') or []))}
satisfaction_rule (Indonesian prose; mode={rule.get('mode', 'BINARY')}):
- sufficient: {rule.get('sufficient', '')}
- partial: {rule.get('partial', '') or '(none — BINARY mode)'}
- no_decisive: {rule.get('no_decisive', '')}
- contradicting: {rule.get('contradicting', '')}{unit_line}

CANDIDATE CLAIMS ({len(candidates)}):
{chr(10).join(_claim_line(eid, ev, node) for eid, ev, node in candidates)}

Verify each candidate claim against this requirement's rule now. Quote exact substrings."""


# ── cache (budget: replay + the next turn are cheap) ──────────────────────────────────────

# MC-06 (18 Oct, session 7f2e13b1fcbe — ABSENT→UNKNOWN→PRESENT→UNKNOWN+conflict oscillation on
# commercial.willingness_to_pay): the old cache was keyed per candidate SET; the set changes every
# turn (new claims arrive) → ALL claims are re-judged by a non-deterministic model → verdicts
# change between turns for the SAME (requirement, claim) pair → adjudicate writes a new entry →
# counts jump up and down (the "key questions" chip rises again after falling).
# Verdicts are now STICKY PER CLAIM: key = (registry fingerprint, rid, evidence_ref, provider/model
# identity, prompt digest). A claim that has been verified is not re-judged just because other
# candidates changed; the adjudicator still re-merges all verdicts deterministically per turn
# (contracts AD9/RR7/D6 unchanged).
_CACHE: "OrderedDict[tuple[str, str, str, str, str], dict[str, Any]]" = OrderedDict()
_CACHE_MAX = 256


def _claim_cache_key(fingerprint: str, rid: str, evidence_ref: str, model_identity: str,
                     prompt_digest: str) -> tuple[str, str, str, str, str]:
    return (fingerprint, rid, evidence_ref, model_identity, prompt_digest)


def _prompt_digest() -> str:
    return hashlib.sha256(SPV_SYSTEM.encode("utf-8")).hexdigest()[:8]


def llm_identity(llm: Any) -> str:
    """Provider/model identity (not just for audit): a model/provider change MUST NOT
    serve another model's verdict from a warm cache. Format "name:model" (stable, no secrets)."""
    if llm is None:
        return ""
    name = getattr(llm, "name", None) or type(llm).__name__
    model = getattr(llm, "model", "") or ""
    return f"{name}:{model}"


def clear_cache() -> None:
    _CACHE.clear()


# ── verdict -> contract object (deterministic; status is NEVER touched) ────────────────────


def _admissible_for_verification(ev: Any) -> Optional[str]:
    """Defensive admissibility gate (R4): candidates that are not state evidence are NOT sent.
    Return None = may be verified; string = rejection reason."""
    if getattr(ev, "superseded", False):
        return "claim_not_current"
    if getattr(ev, "is_gap", False):
        return "gap_is_absence_not_fact"
    role = (getattr(ev, "claim_role", "") or "").lower()
    if role in _NON_EVIDENCE_ROLES:
        return f"role_{role}_not_evidence_of_state"
    if not getattr(ev, "admissible", True):
        return getattr(ev, "inadmissible_reason", "") or "not_admissible"
    return None


def _quote_grounded(check: ClaimCheck, ev: Any) -> bool:
    """A verdict's citation MUST be an exact substring of the claim's quote/summary (provenance, not
    meaning)."""
    q = (check.quote or "").strip()
    if not q:
        return False
    source = (getattr(ev, "source_quote", None) or "") or ""
    signal = getattr(ev, "signal", "") or ""
    return q in source or q in signal


def _node_of(graph: dict[str, Any] | None, ev: Any) -> dict[str, Any]:
    cid = getattr(ev, "claim_id", "") or ""
    return ((graph or {}).get("nodes") or {}).get(cid) or {}


def verify_second_pass(
    proposals: list[dict[str, Any]],
    registry_entries: list[dict[str, Any]],
    evidence_index: dict[str, Any],
    *,
    llm: Any,
    fingerprint: str,
    now: int | None = None,
    goal: dict[str, Any] | None = None,
    session_id: str = "",
    user_id: str = "",
    graph: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Verify PROSE proposals (path B failed because the rule is still prose / unit without context).

    Input `proposals` = 4-field PROPOSED mapping from the deterministic mapper (ONLY prose/unit rids,
    already past gate B and known UNRESOLVED). Output:
      verified_mappings  — 5-field VERIFIED mapping, verification_method='second_pass_verified'
      unit_contexts      — B1 sidecar for multi-unit requirements
      rule_evaluations   — {rid: {sufficient, partial, no_decisive, contradicting}} (for
                           adjudicate(precomputed_rule_evaluation=...) — status STILL from
                           adjudicate, not from here)
      citations          — {rid: {sufficient: [refs], partial: [refs], contradicting: [refs]}}
      unresolved         — [{requirement_id, evidence_refs, reason}] (stable code)
      audit              — BC-03 record per verdict (claim/event/quote/rid/fingerprint/model/ts)
      llm_calls          — number of actual LLM calls (cache hit = 0)
    """
    t = int(now if now is not None else time.time())
    entry_by_rid = {r["requirement_id"]: r for r in registry_entries}
    by_rid: dict[str, dict[str, str]] = {}
    for p in proposals:
        rid = p.get("requirement_id", "")
        for ref in p.get("evidence_refs", []):
            by_rid.setdefault(rid, {})[ref] = ""

    verified: list[dict[str, Any]] = []
    unit_contexts: list[dict[str, Any]] = []
    rule_evaluations: dict[str, dict[str, bool]] = {}
    citations: dict[str, dict[str, list[str]]] = {}
    unresolved: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []
    llm_calls = 0

    provider_model = llm_identity(llm) or type(llm).__name__
    # S1 telemetry: elapsed_s = wall time of the whole verification (including cache lookup +
    # aggregation); llm_elapsed_s = sum of actual LLM call durations only. The two are mutually
    # exclusive (the second is NESTED inside the first) — do not add them up again as a total.
    _t_verify0 = time.perf_counter()
    llm_elapsed_s = 0.0

    # ── PHASE 1: per-rid plan — admissible candidates, split STICKY (per-claim verdict already in
    # cache) vs FRESH (needs judging). The single source of truth for admissibility/cap stays here.
    pdig = _prompt_digest()
    _plan: list[dict[str, Any]] = []
    for rid in sorted(by_rid):
        entry = entry_by_rid.get(rid)
        if entry is None:
            continue  # defensive: the registry filters in _sem_base on path B
        cand: list[tuple[str, Any, dict[str, Any]]] = []
        rejected_here: list[tuple[str, str]] = []
        for ref in by_rid[rid]:
            ev = evidence_index.get(ref)
            if ev is None:
                continue
            reason = _admissible_for_verification(ev)
            if reason is not None:
                rejected_here.append((ref, reason))
                continue
            cand.append((ref, ev, _node_of(graph, ev)))
        for ref, reason in rejected_here:
            unresolved.append({"requirement_id": rid, "evidence_refs": [ref], "reason": reason})
        if not cand:
            continue
        cand = cand[:MAX_CANDIDATES_PER_REQUIREMENT]
        sticky: list[tuple[str, Any, dict[str, Any]]] = []
        fresh: list[tuple[str, Any, dict[str, Any]]] = []
        sticky_checks: dict[str, dict[str, Any]] = {}
        for item in cand:
            key = _claim_cache_key(fingerprint, rid, item[0], provider_model, pdig)
            hit = _CACHE.get(key)
            if hit is not None:
                sticky.append(item)
                sticky_checks[item[0]] = hit
            else:
                fresh.append(item)
        _plan.append({"rid": rid, "entry": entry, "cand": cand, "sticky": sticky,
                      "fresh": fresh, "sticky_checks": sticky_checks})

    # ── PHASE 2: PARALLEL PREFETCH of LLM calls for FRESH claims only (concurrent I/O, bounded).
    # Sticky claims are NOT re-asked (MC-06: per-claim verdicts are stable across turns). Each
    # call is still a whole `structured_call`; the prompt only carries new claims. One rid's
    # failure does not bring down another rid (CP-25).
    _todo = [p for p in _plan if p["fresh"]]
    _prefetched: dict[str, tuple[str, Any, float]] = {}
    if _todo:
        def _fetch(item: dict[str, Any]) -> tuple[str, str, Any, float]:
            _t0 = time.perf_counter()
            try:
                chk = llm.structured_call(
                    SecondPassCheck, SPV_SYSTEM, build_user_prompt(item["entry"], item["fresh"]))
                return item["rid"], "ok", chk, time.perf_counter() - _t0
            except Exception as exc:  # noqa: BLE001 — per-rid degradation, NOT a 500 error
                return item["rid"], "err", exc, time.perf_counter() - _t0

        if SPV_MAX_PARALLEL > 1 and len(_todo) > 1:
            with ThreadPoolExecutor(max_workers=min(SPV_MAX_PARALLEL, len(_todo))) as pool:
                for rid, outcome, payload, dur in pool.map(_fetch, _todo):
                    _prefetched[rid] = (outcome, payload, dur)
        else:
            for rid, outcome, payload, dur in (_fetch(i) for i in _todo):
                _prefetched[rid] = (outcome, payload, dur)

    # ── PHASE 3: SEQUENTIAL verdict aggregation — sticky + fresh merged (MC-06); the grounding gate
    # still runs for FRESH verdicts (sticky ones already passed when first judged). Fresh verdicts
    # that pass grounding enter the per-claim cache.
    for step in _plan:
        rid = step["rid"]
        entry = step["entry"]
        cand = step["cand"]
        mode = (entry.get("satisfaction_rule") or {}).get("mode", "BINARY")
        fresh_checks: list[dict[str, Any]] = []
        if step["fresh"]:
            llm_calls += 1
            outcome, payload, _dur = _prefetched[rid]
            llm_elapsed_s += _dur
            if outcome == "err":
                exc = payload
                unresolved.append({"requirement_id": rid,
                                   "evidence_refs": [c[0] for c in step["fresh"]],
                                   "reason": f"SECOND_PASS_FAILED: {type(exc).__name__}"})
                audit.append({"requirement_id": rid, "provider_model": provider_model,
                              "fingerprint": fingerprint, "prompt_contract": SPV_CONTRACT_VERSION,
                              "verified_at": t, "outcome": "llm_failure",
                              "detail": f"{type(exc).__name__}: {str(exc)[:160]}"})
            else:
                check = payload
                cv_ok = getattr(check, "contract_version", "") == SPV_CONTRACT_VERSION
                if not cv_ok or check.requirement_id != rid:
                    unresolved.append({"requirement_id": rid, "evidence_refs": [c[0] for c in step["fresh"]],
                                       "reason": "SECOND_PASS_FAILED: contract_mismatch"})
                else:
                    fresh_checks = [c.model_dump() for c in check.claim_checks]

        ev_by_ref = {eid: ev for eid, ev, _n in cand}
        checked_refs: set[str] = set()
        s_refs: list[str] = []
        p_refs: list[str] = []
        c_refs: list[str] = []
        ucs: dict[tuple[str, ...], dict[str, Any]] = {}
        raw_all: list[tuple[dict[str, Any], str]] = \
            [(raw, "sticky") for raw in step["sticky_checks"].values()] \
            + [(raw, "fresh") for raw in fresh_checks]
        for raw, source in raw_all:
            try:
                chk = ClaimCheck.model_validate(raw)
            except Exception:  # noqa: BLE001 — defective verdict = not counted (not a crash)
                continue
            ev = ev_by_ref.get(chk.evidence_ref)
            if ev is None:
                continue  # verdict for a ref that was not sent: discarded (anti-injection)
            checked_refs.add(chk.evidence_ref)
            if source == "fresh" and chk.branch != "none" and not _quote_grounded(chk, ev):
                # Citation grounding = provenance, not a meaning gate: a verdict that CLAIMS a branch
                # must stand on the user's exact words. A "none" verdict does not
                # claim anything, so it needs no citation.
                unresolved.append({"requirement_id": rid, "evidence_refs": [chk.evidence_ref],
                                   "reason": "SECOND_PASS_QUOTE_NOT_GROUNDED"})
                audit.append({"requirement_id": rid, "evidence_id": chk.evidence_ref,
                              "canonical_claim_id": getattr(ev, "claim_id", "") or "",
                              "source_event_id": getattr(ev, "event_id", "") or "",
                              "quote": chk.quote, "fingerprint": fingerprint,
                              "prompt_contract": SPV_CONTRACT_VERSION,
                              "provider_model": provider_model, "verified_at": t,
                              "outcome": "quote_not_grounded"})
                continue
            if source == "fresh":
                _CACHE[_claim_cache_key(fingerprint, rid, chk.evidence_ref, provider_model, pdig)] = raw
                if len(_CACHE) > _CACHE_MAX:
                    _CACHE.popitem(last=False)
            outcome = "verified" if chk.branch != "none" else "no_match"
            audit.append({"requirement_id": rid, "evidence_id": chk.evidence_ref,
                          "canonical_claim_id": getattr(ev, "claim_id", "") or "",
                          "source_event_id": getattr(ev, "event_id", "") or "",
                          "source_quote": getattr(ev, "source_quote", None) or "",
                          "verdict_quote": chk.quote, "branch": chk.branch,
                          "unit_key": chk.unit_key, "basis": chk.basis,
                          "fingerprint": fingerprint, "prompt_contract": SPV_CONTRACT_VERSION,
                          "provider_model": provider_model, "verified_at": t,
                          "outcome": outcome, "verdict_source": source})
            if chk.branch == "sufficient":
                s_refs.append(chk.evidence_ref)
            elif chk.branch == "partial":
                p_refs.append(chk.evidence_ref)
            elif chk.branch == "contradicting":
                c_refs.append(chk.evidence_ref)
            else:
                unresolved.append({"requirement_id": rid, "evidence_refs": [chk.evidence_ref],
                                   "reason": "SECOND_PASS_NO_MATCH"})
            if chk.branch != "none" and rid in UNIT_DOMAINS and chk.unit_key:
                binding = (rid, chk.evidence_ref)
                ucs.setdefault(binding, {
                    "proposed_by": PROPOSED_BY, "requirement_id": rid,
                    "evidence_refs": [chk.evidence_ref], "unit_key": chk.unit_key,
                    "proposed_at": t})

        # MC-06: a FRESH claim the verifier did not answer = implicit none (old contract:
        # honest NO_MATCH) — also cached so replay/the next turn does not ask again
        # about the same claim just because the model did not mention it.
        for eid, _ev, _node in step["fresh"]:
            key = _claim_cache_key(fingerprint, rid, eid, provider_model, pdig)
            if key not in _CACHE:
                _CACHE[key] = {"evidence_ref": eid, "quote": "", "branch": "none",
                               "unit_key": None, "basis": ""}

        s = bool(s_refs)
        p = bool(p_refs) and not s and mode == "PARTIAL"  # D-A1c by construction + RR11
        c = bool(c_refs)
        # A candidate the verifier did not answer at all = honest NO_MATCH (not silently passed).
        for eid, _ev, _node in cand:
            if eid not in checked_refs:
                unresolved.append({"requirement_id": rid, "evidence_refs": [eid],
                                   "reason": "SECOND_PASS_NO_MATCH"})
        contributing = (s_refs if s else []) + (p_refs if p else []) + (c_refs if c else [])
        # unit-requirement: mapping verified only when the EXACT unit_context binding exists (B1)
        if rid in UNIT_DOMAINS:
            contributing = [r for r in contributing if (rid, r) in ucs]
            if not contributing:
                for r in set(s_refs) | set(p_refs) | set(c_refs):
                    unresolved.append({"requirement_id": rid, "evidence_refs": [r],
                                       "reason": "SECOND_PASS_UNIT_UNIDENTIFIED"})
                continue
        if not contributing:
            continue  # no branch proven -> requirement stays UNKNOWN by absence

        for ref in dict.fromkeys(contributing):
            verified.append({
                "requirement_id": rid,
                "evidence_refs": [ref],
                "verification_method": "second_pass_verified",
                "verified": True,
                "verified_at": t,
            })
        for uc in ucs.values():
            if uc["evidence_refs"][0] in contributing:
                unit_contexts.append(uc)
        rule_evaluations[rid] = {
            "sufficient": s, "partial": p, "contradicting": c,
            "no_decisive": not (s or p or c),
        }
        citations[rid] = {
            "sufficient": sorted(dict.fromkeys(s_refs)) if s else [],
            "partial": sorted(dict.fromkeys(p_refs)) if p else [],
            "contradicting": sorted(dict.fromkeys(c_refs)) if c else [],
        }

    return {
        "verified_mappings": verified,
        "unit_contexts": unit_contexts,
        "rule_evaluations": rule_evaluations,
        "citations": citations,
        "unresolved": unresolved,
        "audit": audit,
        "llm_calls": llm_calls,
        "elapsed_s": round(time.perf_counter() - _t_verify0, 2),
        "llm_elapsed_s": round(llm_elapsed_s, 2),
        "scope": {"session_id": session_id, "user_id": user_id,
                  "goal_id": (goal or {}).get("goal_id", "")},
    }
