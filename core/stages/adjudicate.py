"""Deterministic satisfaction adjudicator — Phase 3 step 5 (parts [2]+[3]).

Contract FINAL: internal-docs §6 (D-A1a/A1b/A1c/A1d + D-A2).
Architecture §6.7 as IMPLEMENTED here = the deterministic part ONLY:

    State Evidence -> (semantic mapper — NOT this file) -> PROPOSED
    -> verification -> VERIFIED mapping -> Admitted Evidence Set
    -> [1] rule evaluation (here, deterministic, reuse of KB operators)
    -> [3] conflict detection (D-A1a) + resolution (D-A1b) -> 4-enum
    -> append-only ledger (store/adjudication_ledger.py)

RR7/D6: the LLM may PROPOSE a mapping; the authoritative status is ONLY the result of
the rules applied here — this file is 0 LLM, deterministic, citations mandatory.

D-A1c by construction: `partial` is evaluated as (partial condition) AND
(NOT sufficient) — matching the locked contractual meaning. Therefore S∧P is never
produced by the evaluator; if a rule_evaluation precomputed outside contains S∧P,
it is INVALID → evaluation anomaly (D-A1d), no output, no ledger entry.
"""
from __future__ import annotations

import time
from typing import Any

from core.schema.evidence import EvidenceItem
from core.stages.rule_predicates import evaluate_predicate
from ontology.adjudication.validate_adjudication import (
    AdjudicationValidationError,
    check_adjudication_output,
    check_rule_evaluation,
    check_verified_mapping,
    expected_status,
)

Anomaly = dict[str, Any]


class EvaluationInvalidError(Exception):
    """D-A1d — invalid evaluation (S∧P, all-false, inconsistent record).
    MUST be routed to the anomaly channel by the pipeline (`submit` in
    store/adjudication_ledger) — not a source of adjudication output, not an
    exception swallowed silently (wave-13 review: API convention ≠ boundary)."""

    def __init__(self, anomaly: Anomaly):
        super().__init__(anomaly["reason"])
        self.anomaly = anomaly


def _eval_branch(
    predicate: dict[str, Any] | None,
    evidence: list[EvidenceItem],
) -> tuple[bool, list[str]]:
    """One rule branch. A branch without a formal predicate (author prose) = false with no
    citation — gradual formalization D-A2 model B; prose is never counted true."""
    if not predicate:
        return False, []
    # D9 (int 08 §8.4): raw transcripts NEVER enter adjudication —
    # mapper contract: only the Admitted Evidence Set from Universal State.
    matched, cited, _reason = evaluate_predicate(predicate, evidence, "",
                                                negation_aware=True)
    return matched, cited


def _anomaly(requirement_id: str, reason: str, detail: dict[str, Any] | None = None) -> Anomaly:
    """D-A1d — evaluation anomaly: NOT a status, NOT an adjudication result,
    NOT a conflict. A channel separate from the ledger; does NOT block the pipeline."""
    return {
        "anomaly_id": f"anom.{requirement_id}.{int(time.time())}",
        "requirement_id": requirement_id,
        "reason": reason,
        "detail": detail or {},
        "detected_at": int(time.time()),
    }


def _admit(
    verified_mappings: list[dict[str, Any]],
    evidence: list[EvidenceItem],
    requirement_id: str,
) -> dict[str, EvidenceItem]:
    """Verification gate D-A2 — order MANDATORY (wave-13 review):

        structural (A = prerequisite of ALL paths) → requirement scope → verified?

    Two gaps closed:
    (1) admission SCOPED — a mapping owned by another requirement MUST NOT admit
        evidence into this requirement's adjudication (cross-requirement leak);
    (2) structural runs BEFORE the `verified` gate — an object with verified=false
        must still be structurally valid.
    Structural failure = malformed input (ValueError, NOT an anomaly — that is an
    input-construction failure, not a rule-construction failure).
    """
    admitted: dict[str, EvidenceItem] = {}
    by_id = {e.id: e for e in evidence}
    for vm in verified_mappings or []:
        check_verified_mapping(vm)  # required + enum + exact keys — all paths
        if vm["requirement_id"] != requirement_id:
            continue  # BLOCKER review: admission scoped to this requirement
        for ref in vm["evidence_refs"]:
            if ref not in by_id:
                # structural gate A: a ref pointing at missing evidence = malformed
                raise ValueError(f"malformed verified_mapping: evidence ref '{ref}' tidak ada di State")
        if vm["verified"] is not True:
            continue  # degradation rule: once structural passes, verified=false -> not admitted
        for ref in vm["evidence_refs"]:
            admitted[ref] = by_id[ref]
    return admitted


def adjudicate(
    requirement_id: str,
    rule: dict[str, Any],
    evidence: list[EvidenceItem],
    verified_mappings: list[dict[str, Any]],
    evaluation_time: int,
    adjudicated_at: int | None = None,
    precomputed_rule_evaluation: dict[str, bool] | None = None,
    precomputed_citations: dict[str, list[str]] | None = None,
) -> dict[str, Any] | Anomaly:
    """One VALID adjudication. Rule = satisfaction_rule with formally predicated
    branches ({"operator": ...} / any_of/all_of); prose branches are never true.

    `precomputed_rule_evaluation` (optional): a rule_evaluation precomputed by
    another layer (e.g. the mapping pipeline). It MUST pass the same gate as the
    internal result — D-A1d ATOMIC (wave-13 review): S∧P / all-false /
    inconsistent → return an EVALUATION ANOMALY (keyed "anomaly_id", not a
    swallowable exception), WITHOUT an AdjudicationOutput, WITHOUT a ledger entry.

    `precomputed_citations` (optional, valid ONLY together with a precomputed
    rule_evaluation): per-branch citations {sufficient: [refs], partial: [refs],
    contradicting: [refs]} from another verification layer (D-A2 layer C — prose
    rules have no deterministic predicate to produce citations). Citations pass
    the SAME output gate (citations mandatory for sufficient; conflict referential
    integrity AD3): an outer layer that fabricates empty citations yields an
    ANOMALY, not output. Status still comes ONLY from the D-A1b resolution table
    over rule_evaluation — the calling layer never supplies the status.

    Returns: a VALID AdjudicationOutput OR an anomaly dict — never both, never an
    invalid output. Malformed input (structural gate A) stays a ValueError — an
    input-construction failure, not a rule-construction failure.
    """
    admitted = _admit(verified_mappings, evidence, requirement_id)
    admitted_list = list(admitted.values())

    s, s_cited = _eval_branch(rule.get("sufficient"), admitted_list)

    # D-A1c BY CONSTRUCTION: partial only applies without sufficient
    p, p_cited = _eval_branch(rule.get("partial") if rule.get("mode") == "PARTIAL" else None,
                              admitted_list)
    p = p and not s
    if p and rule.get("mode") != "PARTIAL":
        p = False  # RR11: BINARY has no partial branch

    c, c_cited = _eval_branch(rule.get("contradicting"), admitted_list)

    if precomputed_rule_evaluation is None:
        # AD1 totality: no_decisive = definitional complement (not a predicate result)
        rule_evaluation = {
            "sufficient": s,
            "partial": p,
            "no_decisive": not (s or p or c),
            "contradicting": c,
        }
    else:
        # Precomputed outside: the gate below judges it IDENTICALLY to the internal result.
        rule_evaluation = dict(precomputed_rule_evaluation)
        if precomputed_citations is not None:
            # Citations from another verification layer (D-A2 C): used AS-IS, like the
            # internal result — the output gate still demands mandatory citations.
            s_cited = list(precomputed_citations.get("sufficient") or [])
            p_cited = list(precomputed_citations.get("partial") or [])
            c_cited = list(precomputed_citations.get("contradicting") or [])

    try:
        check_rule_evaluation(rule_evaluation, rule.get("mode"))

        # D-A1a — conflict detection (deterministic, both sides recorded)
        conflict_expected = (rule_evaluation["sufficient"] or rule_evaluation["partial"]) \
            and rule_evaluation["contradicting"]
        conflict = {
            "present_evidence_refs": (s_cited or p_cited) if conflict_expected else [],
            "contradicting_evidence_refs": c_cited if conflict_expected else [],
        }

        # D-A1b — resolution (contract table; expected_status = pure function §6.4)
        status = expected_status(rule_evaluation)

        evidence_refs = sorted(
            s_cited or p_cited
            or (c_cited if rule_evaluation["contradicting"] and not conflict_expected else [])
        )
        out: dict[str, Any] = {
            "requirement_id": requirement_id,
            "status": status,
            "rule_evaluation": rule_evaluation,
            "evidence_refs": evidence_refs,
            "conflict": conflict,
            "evaluation_time": int(evaluation_time),
            "adjudicated_at": int(adjudicated_at if adjudicated_at is not None else time.time()),
        }
        # rule_mode = validator ARGUMENT, NOT a record field (additionalProperties=false)
        check_adjudication_output(out, rule_mode=rule.get("mode"))
    except (AdjudicationValidationError, KeyError, TypeError) as exc:
        # D-A1d ATOMIC — invalid input NEVER produces output:
        # one path, one result: evaluation anomaly (no ledger, no status).
        return _anomaly(requirement_id, f"evaluasi invalid: {exc}",
                        {"rule_evaluation": rule_evaluation})
    return out


def check_precomputed(rule_evaluation: dict[str, bool], requirement_id: str,
                      rule_mode: str | None = None) -> Anomaly | None:
    """Gate for a rule_evaluation precomputed outside this evaluator (e.g. from the
    mapping layer). S∧P or all-false → D-A1d anomaly (NO output, NO ledger
    entry); valid → None (proceed to resolution)."""
    try:
        check_rule_evaluation(rule_evaluation, rule_mode)
        return None
    except ValueError as exc:
        return _anomaly(requirement_id, str(exc), {"rule_evaluation": rule_evaluation})
