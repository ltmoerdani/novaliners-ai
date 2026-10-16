"""LIVE ADJUDICATION PRODUCER — session evidence -> proposal -> verification -> adjudication ->
user-scoped ledger.

internal-docs §25 (M4). Before M4 this chain lived only in tests; the live session flow never
filled the ledger, so route node satisfaction was always UNKNOWN. This module wires it up WITHOUT changing
a single locked contract (int 09 §6, int 08):

    EvidenceItem (Universal State; raw transcript FORBIDDEN)
      -> MAPPER (`contract.propose_deterministic`, proposer v1 single-evidence): PROPOSAL only, not status
      -> deterministic VERIFICATION (`contract.verify_batch`, TWO-GATE D-A2 A+B): VERIFIED only when evidence
         truly satisfies >= 1 branch of a reviewed FORMAL rule
      -> D-A2 LAYER C (`second_pass.verify_second_pass`, optional via `llm`): proposals for PROSE requirements
         that failed path B are verified by an independent second pass (LLM provider-agnostic) ->
         VERIFIED mapping
         with verification_method='second_pass_verified' + rule_evaluation/citations for the adjudicator.
         The LLM never writes status; LLM failure = UNRESOLVED (honest degradation, the turn does not crash).
      -> ADJUDICATION (`core/stages/adjudicate`): the ONLY status authority (D-A1d)
      -> user-scoped LEDGER (`adjudicate_and_persist`: the only write path)
      -> Requirement State Reader (`store/requirement_state.py`)

What is DELIBERATELY not done (epistemic honesty, not a shortcoming):

  - The mapper is never the status authority. A proposal without verification never touches the ledger.
  - The second-pass verifier does NOT reinterpret claims, does NOT produce new claims, does NOT write status:
    it verifies mapping proposals against prose rules and returns the branch + citation; status remains
    adjudicate()'s output via the D-A1b resolution table (RR7/D6; SC-01: the one meaning authority remains
    semantic observation).
  - Requirements WITHOUT formal rules (the majority of the registry: 44 of 49) are never adjudicated and their
    predicates are never invented: they stay UNKNOWN by absence. Their verification failure is recorded as
    `NO_FORMAL_RULE` — that is a fact about COVERAGE, not about the user's state.
  - Multi-unit requirements (needing `unit_context`) cannot be verified deterministically from conversation:
    `UNIT_CONTEXT_REQUIRED`, stays UNKNOWN. Unit identity is never guessed.
  - `is_gap` evidence (MISSING data / declined to answer; not a fact) is NEVER admitted on the live
    path: a gap sentence that happens to contain a predicate literal ("declines to discuss the prospect
    list") can satisfy or contradict a rule branch even though it only marks absent information
    (is_gap != NEGATIVE, the mapper hazard 7.11 flagged in test_mapper.py as upstream debt). Same as the
    route composer (T2 corrective): gaps are filtered at the boundary, not patched inside the
    mapper/adjudicator.
  - No verified evidence for a requirement -> NO ledger entry (not an UNKNOWN entry): absence of
    adjudication is not fabricated into a record, and is never downgraded to ABSENT.
  - Proposer v1 proposes ONE evidence per proposal, so rule satisfaction spread across several sentences
    is not bundled (bundling injects irrelevant sentences into the admitted set, and the
    `text_absent_pattern` predicate is global over that set: silent false negatives). That is a known
    coverage limit, not a user state.
  - IDEMPOTENT writing: a new entry is written only when the result differs from the last entry (status,
    citations, rule_evaluation). The ledger becomes a history of state CHANGES, not a per-turn log;
    `last_updated` is meaningful.

Without an LLM (llm=None, default), fully deterministic: behavior identical to the A+B era. Sessions without a
user have no ledger: the caller does not call this module."""
from __future__ import annotations

import time
from functools import lru_cache
from typing import Any

from core.navigation.requirement_state import (
    SUPPORT_FORMAL,
    SUPPORT_NONE,
    SUPPORT_SECOND_PASS,
    SUPPORT_UNIT,
)
from core.schema.evidence import EvidenceItem
from core.semantic.candidate import (
    V_ADMITTED,
    V_NOT_ADMISSIBLE,
    V_RECOGNIZED_ONLY,
    V_UNRESOLVED,
    candidate_record,
)
from core.stages.adjudicate import adjudicate
from engine.requirements import load_registry
from ontology.mapper import contract, second_pass
from ontology.mapper.contract import UNIT_DOMAINS, MalformedMapping
from ontology.mapper.formal_compiler import compile_from_repo_artifact
from store import adjudication_ledger as ledger

PROPOSED_BY = "mapper_deterministic_v1"

# MC-02 (18 Oct, session e1704203f327 EN): context-directed PROSE candidates from the question focus. The v1
# mapper narrowing is SINGLE-LANGUAGE token overlap (EN claim vs ID registry hay) — cross-language recall
# ~0, so a user answer that directly meets a need is never verified, the same need is asked again until
# ASK_CAP runs out, and the "key questions left" chip never moves. This path proposes prose requirements
# that were ONCE THE FOCUS OF ASKING and are still UNKNOWN in the goal context, with the LATEST admissible
# claim as second-pass candidate.
# This is CANDIDATE UNIVERSE EXPANSION only (D6): the verdict remains the second-pass verifier's output (quote
# grounding is still enforced), status remains adjudicate()'s output — one authority does not shift.
PROPOSED_BY_FOCUS = "context_focus_v1"
# MC-03 (18 Oct, continuation of session e1704203f327): the focus universe is now = rids that were asked
# about + ALL still-UNKNOWN requirements of the live context (from the last planner entry input) — once
# reasoning moves to semantic unknowns (su-*), context rids are never asked about again yet the "key
# questions left" chip is still promised; the cap of 12 preserves the SPV budget per turn (1 call/rid,
# 4 parallel, cache per candidate digest).
MAX_FOCUS_REQUIREMENTS = 12
# MC-03 iteration-2: the last-8 window was too narrow — the session's early fundamental claims (e.g. "4 active
# clients paying Rp12m/month" = willingness_to_pay evidence at the current price) get pushed out as the
# conversation proceeds, so requirements whose answers were ALREADY given early are never verified and the
# chip jams again. Candidates = quantity-bearing claims first + the latest 8, cap 16.
FOCUS_CANDIDATE_CAP = 16
FOCUS_RECENT_CAP = 8

# Stable (machine-readable) UNRESOLVED reason codes. The verifier's original text is preserved in `reason`.
_REASON_CODES = (
    ("tidak terdaftar registry", "UNREGISTERED"),
    ("tak dikenal di Universal State", "UNKNOWN_EVIDENCE_REF"),
    ("unit-berlipak", "UNIT_CONTEXT_REQUIRED"),
    ("STALE", "STALE_FORMAL_RULES"),
    ("NO_FORMAL_RULE", "NO_FORMAL_RULE"),
    ("masih PROSA", "NO_FORMAL_RULE"),
    ("tak memenuhi cabang rule", "EVIDENCE_NOT_MEETING_RULE"),
)


def reason_code(reason: str) -> str:
    """Verifier UNRESOLVED reason text -> stable code; unrecognized = OTHER (never invented)."""
    return next((code for needle, code in _REASON_CODES if needle in (reason or "")), "OTHER")


@lru_cache(maxsize=4)
def _envelope_for(fingerprint: str) -> dict[str, Any]:
    entries = list(load_registry().values())
    return compile_from_repo_artifact(entries)


def formal_envelope() -> dict[str, Any]:
    """Reviewed formal rules for the LIVE registry (repo artifact; no other runtime path). Cached per registry
    fingerprint: a registry change evicts the cache and stale compilation is caught by gate-2."""
    entries = list(load_registry().values())
    return _envelope_for(contract.registry_fingerprint(entries))


def adjudication_support(requirement_id: str, envelope: dict[str, Any] | None = None,
                          registry_ids: set[str] | None = None) -> str:
    """Can conversation evidence shift this requirement's state? FORMAL / UNIT / SECOND_PASS / NONE.

    Gate A (15 Oct, conditional — owner decision): registered PROSE requirements now have a mapper ->
    second-pass verifier path (D-A2 C), hence SECOND_PASS — a POTENTIAL shift, not a guarantee of mapper
    recall or verifier outcome. A STATIC property of registry+envelope (not LLM availability at call
    time) so that inspection/replay without a provider yields identical planner decisions."""
    env = envelope if envelope is not None else formal_envelope()
    if requirement_id in (env.get("rules") or {}):
        return SUPPORT_UNIT if requirement_id in UNIT_DOMAINS else SUPPORT_FORMAL
    if registry_ids is None:
        registry_ids = set(load_registry())  # keys = requirement_id (dict rid -> entri)
    return SUPPORT_SECOND_PASS if requirement_id in registry_ids else SUPPORT_NONE


def support_of(envelope: dict[str, Any] | None = None):
    """Function `requirement_id -> support` for `LedgerRequirementReader(support_of=...)`."""
    env = envelope if envelope is not None else formal_envelope()
    registry_ids = set(load_registry())
    return lambda rid: adjudication_support(rid, env, registry_ids)


def _same(prev: dict[str, Any] | None, new: dict[str, Any]) -> bool:
    if prev is None:
        return False
    a = prev["adjudication"]
    return (
        a["status"] == new["status"]
        and sorted(a.get("evidence_refs") or []) == sorted(new.get("evidence_refs") or [])
        and a.get("rule_evaluation") == new.get("rule_evaluation")
    )


def _focus_candidates(facts: list[Any], graph: dict[str, Any] | None,
                     already: set[str]) -> list[str]:
    """Focus-path claim candidates (MC-03 iteration-2/3): QUANTITY-bearing claims first (numbers, prices,
    amounts — fundamental evidence that usually appears early in the story and is easily displaced by the
    last window), then the latest 8 claims (most likely to answer the last question).
    Dedup by id; excludes refs already proposed by the mapper for the same rid."""
    nodes = (graph or {}).get("nodes") or {}

    def _qty(e: Any) -> bool:
        node = nodes.get(getattr(e, "claim_id", "") or "") or {}
        return bool(node.get("quantity"))

    seen: set[str] = set(already)
    out: list[str] = []
    for e in ([x for x in facts if _qty(x)] + list(facts[-FOCUS_RECENT_CAP:])):
        if e.id in seen:
            continue
        seen.add(e.id)
        out.append(e.id)
        if len(out) >= FOCUS_CANDIDATE_CAP:
            break
    return out


def _focus_proposals(
    focus_requirement_ids: list[str] | None,
    *,
    index: dict[str, Any],
    facts: list[Any],
    graph: dict[str, Any] | None,
    formal_ids: set[str],
    registry_ids: set[str],
    mapper_refs_by_rid: dict[str, set[str]],
    user_id: str,
    goal_id: str | None,
    now: int,
) -> list[dict[str, Any]]:
    """Context-DIRECTED prose candidate proposals (MC-02/MC-03). Rid conditions: registered in the
    registry, PROSE (not formal/unit), and still without a verified state in this goal context (ledger
    None/UNKNOWN). Rids ALREADY proposed by the mapper this turn are NOT skipped — focus proposals ADD claim
    candidates beyond the mapper's token overlap (early fundamental claims / cross-language); SPV merges all
    candidates per rid. Deterministic; without `focus_requirement_ids` this path is inactive (A+B-era
    behavior intact)."""
    if not focus_requirement_ids or not index or not facts:
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in focus_requirement_ids:
        rid = str(raw or "").strip()
        if not rid or rid in seen:
            continue
        seen.add(rid)
        if rid not in registry_ids or rid in formal_ids:
            continue
        # only needs still OPEN in this business context — ones that already have a verified state are no
        # longer a "key question" (weighing them again is not this path's job).
        if ledger.latest_status(user_id, rid, goal_id=goal_id) not in (None, "UNKNOWN"):
            continue
        refs = _focus_candidates(facts, graph, mapper_refs_by_rid.get(rid) or set())
        if not refs:
            continue
        out.append({"proposed_by": PROPOSED_BY_FOCUS, "requirement_id": rid,
                    "evidence_refs": refs, "proposed_at": now})
        if len(out) >= MAX_FOCUS_REQUIREMENTS:
            break
    return out


def run_live_adjudication(
    user_id: str,
    evidence: list[EvidenceItem],
    *,
    now: int | None = None,
    envelope: dict[str, Any] | None = None,
    goal: dict[str, Any] | None = None,
    session_id: str = "",
    graph: dict[str, Any] | None = None,
    llm: Any = None,
    focus_requirement_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Session evidence -> adjudication -> ledger `user_id`. Returns an audit summary (JSON-safe).

    `focus_requirement_ids` (optional, MC-02): rids of requirements that were once the focus of asking
    (planner_log) — for prose rids still UNKNOWN, the latest admissible claim is proposed as a second-pass
    candidate SO THAT cross-language user answers can be verified (candidate universe only; verdict remains
    second-pass, status remains the adjudicator's). None = path inactive.

    The mapper only PROPOSES; verification decides whether a proposal is admitted; the adjudicator decides
    status. `user_id` must be valid (`validate_user_id` in the ledger — fail closed, not a shared file).

    `llm` (optional): enables D-A2 LAYER C — proposals for PROSE requirements (no compiled formal rule) that
    failed path B are verified by a second pass BEFORE being declared UNRESOLVED (int 04/09 §6.7). Without llm
    (default; pure deterministic path/test) layer C is skipped: behavior identical to the A+B era. Any LLM
    failure (timeout/refusal/defective output) = UNRESOLVED (honest degradation, the turn does not crash),
    NOT an exception."""
    entries = list(load_registry().values())
    registry_ids = {e["requirement_id"] for e in entries}
    reg_by_rid = {e["requirement_id"]: e for e in entries}
    env = envelope if envelope is not None else formal_envelope()
    formal_ids = set(env.get("rules") or {})
    t = int(now if now is not None else time.time())
    # R4 admissibility (deterministic, BEFORE the mapper): gap = missing data; evidence whose source claim was
    # replaced/negated is not the current state; roles that are not state evidence (assumptions/wishes) are
    # recognized but must not satisfy a requirement. What is filtered out is STILL recorded as a candidate.
    candidates: list[dict[str, Any]] = []

    def _reject(e, reason: str) -> None:
        candidates.append(candidate_record(
            e, requirement_id="", verdict=V_NOT_ADMISSIBLE, reason=reason,
            mapping_rule="admissibility_gate_v1", goal=goal, session_id=session_id,
            user_id=user_id, graph=graph))

    facts = []
    superseded_ids = {e.id for e in evidence if getattr(e, "superseded", False)}
    for e in evidence:
        if getattr(e, "superseded", False):
            _reject(e, "claim_not_current")
        elif getattr(e, "is_gap", False):
            _reject(e, "gap_is_absence_not_fact")
        elif not getattr(e, "admissible", True):
            _reject(e, getattr(e, "inadmissible_reason", "") or "not_admissible")
        else:
            facts.append(e)
    index = {e.id: e for e in facts}

    # R1-remediation Probe A applied earlier: business-context scope for the focus filter (MC-02) and the
    # ledger write below — one definition, not recomputed.
    ctx_goal_id = (goal or {}).get("goal_id") or None

    all_proposals = contract.propose_deterministic(index, entries) if index else []
    # MC-02: prose candidates directed by the question context — EN claims (vs ID hay) are unreachable by
    # token-overlap narrowing; without this path the user's answer is never adjudicated and the same need is
    # asked again until ASK_CAP runs out (frozen "key questions left" chip — session e1704203f327).
    mapper_rids = {p["requirement_id"] for p in all_proposals}   # `proposed_rids` keeps mapper meaning
    mapper_refs_by_rid: dict[str, set[str]] = {}
    for p in all_proposals:
        mapper_refs_by_rid.setdefault(p["requirement_id"], set()).update(p.get("evidence_refs") or [])
    focused_rids: list[str] = []
    focus_props = _focus_proposals(
        focus_requirement_ids, index=index, facts=facts, graph=graph, formal_ids=formal_ids,
        registry_ids=registry_ids, mapper_refs_by_rid=mapper_refs_by_rid,
        user_id=user_id, goal_id=ctx_goal_id, now=t)
    if focus_props:
        focused_rids = [p["requirement_id"] for p in focus_props]
        all_proposals = all_proposals + focus_props

    verified: list[dict[str, Any]] = []
    unresolved: dict[str, int] = {}
    malformed = 0
    # D-A2 layer C input: PROSE proposals (uncompiled rule) that failed path B, with their original code.
    prose_pending: dict[str, dict[str, str]] = {}
    cand_at: dict[tuple[str, str], int] = {}
    for p in all_proposals:
        try:
            batch = contract.verify_batch([p], [], index, registry_ids, env, live_registry=entries)
        except MalformedMapping:
            malformed += 1  # proposer bug: visible in the audit, does not bring down the conversation flow
            continue
        verified.extend(batch["verified_mappings"])
        for u in batch["unresolved"]:
            code = reason_code(u.get("reason", ""))
            unresolved[code] = unresolved.get(code, 0) + 1
        for ref in p["evidence_refs"]:
            ok = bool(batch["verified_mappings"])
            first_reason = reason_code((batch["unresolved"] or [{}])[0].get("reason", ""))
            candidates.append(candidate_record(
                index[ref], requirement_id=p["requirement_id"],
                verdict=V_ADMITTED if ok else V_UNRESOLVED,
                reason="verified" if ok else first_reason,
                mapping_rule=p.get("proposed_by", PROPOSED_BY),
                goal=goal, session_id=session_id, user_id=user_id, graph=graph))
            if not ok and p["requirement_id"] not in formal_ids and first_reason == "NO_FORMAL_RULE":
                prose_pending.setdefault(p["requirement_id"], {})[ref] = first_reason
                cand_at[(p["requirement_id"], ref)] = len(candidates) - 1
    proposed_refs = {r for p in all_proposals for r in p["evidence_refs"]}
    for e in facts:
        if e.id not in proposed_refs:
            candidates.append(candidate_record(
                e, requirement_id="", verdict=V_RECOGNIZED_ONLY, reason="no_requirement_proposal",
                mapping_rule=PROPOSED_BY, goal=goal, session_id=session_id, user_id=user_id, graph=graph))

    # ── D-A2 LAYER C (second-pass; only when an LLM is available AND the envelope is not stale) ─────────────
    second_pass_out: dict[str, Any] | None = None
    fp = env.get("fingerprint", "")
    env_not_stale = fp == "" or fp == contract.registry_fingerprint(entries)
    if llm is not None and prose_pending and env_not_stale:
        sp_proposals = [
            {"proposed_by": PROPOSED_BY, "requirement_id": rid,
             "evidence_refs": sorted(refs), "proposed_at": t}
            for rid, refs in prose_pending.items()
        ]
        second_pass_out = second_pass.verify_second_pass(
            sp_proposals, entries, index, llm=llm, fingerprint=contract.registry_fingerprint(entries),
            now=t, goal=goal, session_id=session_id, user_id=user_id, graph=graph)
        verified.extend(second_pass_out["verified_mappings"])
        sp_verified_pairs = {(vm["requirement_id"], ref)
                             for vm in second_pass_out["verified_mappings"]
                             for ref in vm["evidence_refs"]}
        for rid, refs in prose_pending.items():
            for ref, orig_code in refs.items():
                if (rid, ref) in sp_verified_pairs:
                    unresolved[orig_code] = max(0, unresolved.get(orig_code, 0) - 1)
                    at = cand_at.get((rid, ref))
                    if at is not None:
                        candidates[at]["admissibility_verdict"] = V_ADMITTED
                        candidates[at]["reason"] = "second_pass_verified"
                        candidates[at]["mapping_rule"] = second_pass.PROPOSED_BY
        for u in second_pass_out["unresolved"]:
            code = u.get("reason", "OTHER")[:48]
            unresolved[code] = unresolved.get(code, 0) + 1
            at = cand_at.get((u.get("requirement_id", ""), (u.get("evidence_refs") or [""])[0]))
            if at is not None:
                candidates[at]["reason"] = code[:48]

    by_rid: dict[str, list[dict[str, Any]]] = {}
    for vm in verified:
        by_rid.setdefault(vm["requirement_id"], []).append(vm)

    sp_evaluations = (second_pass_out or {}).get("rule_evaluations") or {}
    sp_citations = (second_pass_out or {}).get("citations") or {}

    adjudicated: list[dict[str, Any]] = []
    anomalies: list[dict[str, Any]] = []
    for rid in sorted(by_rid):
        if rid in formal_ids and rid not in UNIT_DOMAINS:
            rule = {"mode": env["modes"][rid], **env["rules"][rid]}
            pre_rev = pre_cit = None
            method = "deterministic_predicate"
        elif rid in sp_evaluations:
            # D-A2 C: PROSE rule from the registry; branch evaluation + citations from the VERIFIED second
            # pass; status remains adjudicate()'s output through the same D-A1b/D-A1d gates.
            rule = dict(reg_by_rid[rid]["satisfaction_rule"])
            pre_rev = sp_evaluations[rid]
            pre_cit = sp_citations.get(rid)
            method = "second_pass_verified"
        else:
            continue  # defensive: verification should not let either through
        try:
            result = adjudicate(rid, rule, facts, by_rid[rid], t,
                                precomputed_rule_evaluation=pre_rev, precomputed_citations=pre_cit)
        except ValueError as exc:  # malformed input (structural gate A): not the user's state
            anomalies.append({"requirement_id": rid, "reason": f"malformed: {exc}"})
            continue
        if "anomaly_id" in result:
            # the same atomic door routes invalid results to the anomaly channel (no ledger entry)
            ledger.adjudicate_and_persist(user_id, rid, rule, facts, by_rid[rid], t, adjudicated_at=t,
                                          precomputed_rule_evaluation=pre_rev,
                                          precomputed_citations=pre_cit, goal_id=ctx_goal_id)
            anomalies.append({"requirement_id": rid, "reason": result["reason"]})
            continue
        written = False
        # dedupe reads context-FILTERED rows: rows from another context do not block
        # this context's write (and vice versa) — Probe A remediation.
        if not _same(ledger.latest_entry(user_id, rid, goal_id=ctx_goal_id), result):
            ledger.adjudicate_and_persist(user_id, rid, rule, facts, by_rid[rid], t, adjudicated_at=t,
                                          precomputed_rule_evaluation=pre_rev,
                                          precomputed_citations=pre_cit, goal_id=ctx_goal_id)
            written = True
        adjudicated.append(
            {
                "requirement_id": rid,
                "status": result["status"],
                "evidence_refs": list(result["evidence_refs"]),
                "written": written,
                "method": method,
            }
        )

    # R4-E: a ledger entry that still cites evidence now REPLACED must not keep asserting PRESENT.
    # Recompute with the valid evidence (without mapping) -> new entry (old history intact).
    # Gate A (15 Oct, external audit P0): invalidation candidates NOW also sweep PROSE rids that were once
    # adjudicated (user-scoped ledger enumeration) — without this, a PRESENT rid that loses ALL proposals
    # due to supersession is never visited (repro: pricing_basis PRESENT -> correction -> stale PRESENT).
    # Rids that STILL have active support this turn are in by_rid (normal re-adjudication, not
    # invalidation) so they do not automatically drop. Formal units remain excluded (they need a
    # unit_context that cannot be reconstructed without mapping — the same boundary as before).
    # Gate A micro-closure (external audit 15 Oct, second iteration): distinguish "evidence no longer
    # valid" from "verification temporarily unavailable". Active refs of the last entry that this turn are
    # NOT DEFINITIVELY re-evaluated by the second pass (provider absent `llm=None`, provider FAILED
    # `SECOND_PASS_FAILED:*` = transient degradation NOT a verdict, or mapper recall did not propose
    # them) keep standing on the previous turn's verification: NO new entry, the last entry intact.
    # Normal re-adjudication happens once the verifier is available again (by_rid path). Definitive
    # rejections (NO_MATCH / QUOTE_NOT_GROUNDED / admissibility) ARE recomputed — the fix does not
    # over-preserve and never revives claims that have been superseded (S1 still holds).
    invalidated: list[dict[str, Any]] = []
    sp_rids = set(sp_evaluations)
    sp_definitive: dict[str, set[str]] = {}
    for u in (second_pass_out or {}).get("unresolved", []):
        if str(u.get("reason", "")).startswith("SECOND_PASS_FAILED"):
            continue  # provider failure = transient degradation, not a verdict on the claim
        sp_definitive.setdefault(u.get("requirement_id", ""), set()).update(u.get("evidence_refs") or [])
    ledger_rids = set(ledger.requirement_ids_with_entries(user_id))
    formal_unit = formal_ids & set(UNIT_DOMAINS)  # UNIT_DOMAINS: dict rid -> unit kinds
    for rid in sorted(((formal_ids | sp_rids | ledger_rids) - set(by_rid)) - formal_unit):
        if rid not in registry_ids:
            continue  # rid unknown to the registry (defensive; legacy-era ledger) — no rule to recompute
        prev = ledger.latest_entry(user_id, rid)
        refs = (prev or {}).get("adjudication", {}).get("evidence_refs") or []
        if not prev or not (set(refs) & superseded_ids):
            continue
        if rid not in formal_ids and (set(refs) - superseded_ids) - sp_definitive.get(rid, set()):
            continue  # partial correction + verification unavailable: the last entry keeps standing
        if rid in formal_ids:
            rule = {"mode": env["modes"][rid], **env["rules"][rid]}
            pre_rev = pre_cit = None
        else:
            rule = dict(reg_by_rid[rid]["satisfaction_rule"])
            pre_rev = {"sufficient": False, "partial": False, "contradicting": False,
                       "no_decisive": True}
            pre_cit = {"sufficient": [], "partial": [], "contradicting": []}
        result = adjudicate(rid, rule, facts, [], t,
                            precomputed_rule_evaluation=pre_rev, precomputed_citations=pre_cit)
        if "anomaly_id" in result or _same(prev, result):
            continue
        ledger.adjudicate_and_persist(user_id, rid, rule, facts, [], t, adjudicated_at=t,
                                      precomputed_rule_evaluation=pre_rev,
                                      precomputed_citations=pre_cit, goal_id=ctx_goal_id)
        invalidated.append({"requirement_id": rid, "was": prev["adjudication"]["status"],
                            "now": result["status"], "reason": "evidence_claim_superseded"})

    summary = {
        "scoped": True,
        "candidates": candidates,
        "invalidated": invalidated,
        "evidence": len(index),
        "gaps_excluded": len(evidence) - len(facts),
        "proposed": len(all_proposals),
        # Gate A (15 Oct): rids the deterministic mapper proposed this turn — basis for SECOND_PASS
        # askability recall-gating (owner contract: path available != recall guarantee).
        "proposed_rids": sorted(mapper_rids),
        "verified": len(verified),
        # MC-02: rids proposed by the focus path this turn — visible in the response/UI audit,
        # not a silent decision (no invisible supplement).
        "focused": focused_rids,
        "unresolved": dict(sorted(unresolved.items())),
        "malformed": malformed,
        "adjudicated": adjudicated,
        "anomalies": anomalies,
    }
    if second_pass_out is not None:
        summary["second_pass"] = {
            "contract": second_pass.SPV_CONTRACT_VERSION,
            "llm_calls": second_pass_out["llm_calls"],
            "verified": len(second_pass_out["verified_mappings"]),
            "unit_contexts": len(second_pass_out["unit_contexts"]),
            "audit": second_pass_out["audit"],
            "scope": second_pass_out["scope"],
            # S1 telemetry: elapsed_s = the whole verification; llm_elapsed_s = actual LLM calls
            # (NESTED, do not add up again). cache_hit is used for cold/warm strata.
            "elapsed_s": second_pass_out.get("elapsed_s"),
            "llm_elapsed_s": second_pass_out.get("llm_elapsed_s"),
        }
    return summary
