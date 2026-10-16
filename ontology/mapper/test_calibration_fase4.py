"""CALIBRATION GATE phase-4 (review 79c7be7 — BLOCKER before promotion):
CROSS-EVIDENCE + UNIT SEMANTICS. Two findings locked:

1. text_absent_pattern GLOBAL (evaluator: any over all items) —
   a negation in unrelated evidence rejects cross-evidence sufficient.
   Locked as ENGINE BEHAVIOR (scope = per-claim ledger); per-unit/unit-agnostic
   scoping = a separate engine decision (note).
2. all_of combines propositions from DIFFERENT evidence without unit
   binding — for UNIT requirements, the official path = per-unit evaluation
   (unit_outcomes + A3b); cross-unit bundles are REJECTED by the B1-exact sidecar.

Fixtures A–F (review):
A) positive spread over 2+ evidence (proposition conjunction = valid for a claim)
B) propositions across units MUST NOT be assembled — the unit path proves it
C) positive + unrelated negative -> global negation scope (locked)
D) conflicting evidence -> branch {S,C} -> adjudicate = UNKNOWN, never
   silently VERIFIED
E) PARTIAL: unit A SATISFIED + unit B FAILED -> A3b -> PARTIAL
F) two evidence in ONE unit -> per-unit eval combines -> SATISFIED
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))  # mvp/

from core.schema.evidence import EvidenceItem  # noqa: E402
from core.stages.adjudicate import adjudicate  # noqa: E402
from core.stages.rule_predicates import evaluate_predicate  # noqa: E402
from ontology.mapper import contract  # noqa: E402
from ontology.mapper.a3b_adapter import build_precomputed, unit_outcomes  # noqa: E402
from ontology.mapper.test_calibration import BRANCHES, DRAFT_PREDICATES  # noqa: E402


def _ev(eid: str, text: str) -> EvidenceItem:
    return EvidenceItem(id=eid, signal=text, source_quote=text,
                        level="self_reported", topic="REVENUE_STATE")


def _branch_set(rid: str, evs: list[EvidenceItem]) -> set[str]:
    pred = DRAFT_PREDICATES[rid]
    branches = BRANCHES if pred["mode"] == "PARTIAL" \
        else ("sufficient", "contradicting")
    return {b for b in branches if evaluate_predicate(pred[b], evs, negation_aware=True)[0]}


def _vm(rid: str, refs: list[str]) -> dict:
    return {"requirement_id": rid, "evidence_refs": refs,
            "verification_method": "deterministic_predicate",
            "verified": True, "verified_at": 1}


RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, fn) -> None:
    try:
        fn()
        RESULTS.append((name, True, ""))
    except Exception as exc:  # noqa: BLE001
        RESULTS.append((name, False, f"{type(exc).__name__}: {exc}"))


def a_propositions_spread() -> None:
    """A: positive spread over 2 evidence (review terminology correction):
    the raw evaluator allows cross-evidence conjunction; FOR UNIT REQUIREMENTS
    (baseline = unit 'perubahan') the official path REMAINS per-unit + A3b
    (proven by fixture B) — A = raw evaluator characterization, NOT a
    decision that baseline may be treated as non-unit."""
    e1 = _ev("e1", "Setiap perubahan punya baseline tercatat.")
    e2 = _ev("e2", "Hasil dibandingkan terhadap baseline.")
    assert _branch_set("experiment.baseline_comparison", [e1]) == set()
    assert _branch_set("experiment.baseline_comparison", [e2]) == set()
    got = _branch_set("experiment.baseline_comparison", [e1, e2])
    # inter-evidence composition = raw evaluator characterization (A);
    # official path for unit-requirement = fixture B
    assert got == {"sufficient"}, got


def b_cross_unit_not_composed() -> None:
    """B: propositions of different units MUST NOT be assembled into satisfaction —
    the official per-unit path (unit_outcomes + A3b) + B1-exact sidecar."""
    e1 = _ev("e1", "Setiap perubahan punya baseline tercatat.")
    e2 = _ev("e2", "Hasil dibandingkan terhadap baseline.")
    # raw-ledger fact: a CROSS-unit bundle can be assembled (reason for the
    # mandatory unit path) — locked as a phenomenon, not the official path:
    assert _branch_set("experiment.baseline_comparison",
                       [e1, e2]) == {"sufficient"}
    # official path: per-unit evaluation — each one does NOT satisfy
    outcomes = unit_outcomes(
        DRAFT_PREDICATES["experiment.baseline_comparison"],
        {"perubahan:X": [e1], "perubahan:Y": [e2]})
    assert outcomes == {"perubahan:X": "UNKNOWN",
                        "perubahan:Y": "UNKNOWN"}, outcomes
    pre, conflicts = build_precomputed(outcomes)
    assert conflicts == [] and pre["no_decisive"] is True, (pre, conflicts)
    # B1-exact sidecar rejects the cross-unit bundle proposal (refs-set
    # bundle without a matching per-unit unit_context)
    idx = {"e1": e1, "e2": e2}
    base = {"proposed_by": "t", "proposed_at": 1}
    bundle = {**base, "requirement_id": "experiment.baseline_comparison",
              "evidence_refs": ["e1", "e2"]}
    ucs = [{**base, "requirement_id": "experiment.baseline_comparison",
            "evidence_refs": ["e1"], "unit_key": "perubahan:X"},
           {**base, "requirement_id": "experiment.baseline_comparison",
            "evidence_refs": ["e2"], "unit_key": "perubahan:Y"}]
    rids = {"experiment.baseline_comparison"}
    batch = contract.verify_batch([bundle], ucs, idx, rids, None)
    assert not batch["verified_mappings"], batch  # B1-exact: bundle
    # cross-unit = no uc with the exact refs-set -> UNRESOLVED


def c_negation_scope_global() -> None:
    """C: positive + unrelated negative — GLOBAL NEGATION over the whole
    ledger (engine behavior locked): 'masih' in evidence B rejects
    sufficient even though B concerns another version. Note: per-unit scoping
    = engine decision (debt, recorded — NOT silenced)."""
    pos = _ev("p", "Produk konkret dengan deliverable jelas sudah tersedia.")
    neg = _ev("n", "Versi lama masih berupa ide.")
    got = _branch_set("offering.exists", [pos])
    assert got == {"sufficient"}, got
    bundle = _branch_set("offering.exists", [pos, neg])
    # GLOBAL negation: sufficient broken + contradicting active
    assert bundle == {"contradicting"}, bundle


def d_conflict_never_silent_verified() -> None:
    """D: conflict evidence -> {sufficient, contradicting} -> adjudicate
    = UNKNOWN (D-A1a), NEVER silently VERIFIED."""
    e_s = _ev("es", "Seluruh entri daftar prospek memuat nama nyata dan "
                    "asal yang jelas.")
    e_c = _ev("ec", "Daftar prospek kosong.")
    got = _branch_set("access.prospect_list", [e_s, e_c])
    assert got == {"sufficient", "contradicting"}, got
    rule = DRAFT_PREDICATES["access.prospect_list"]
    out = adjudicate("access.prospect_list", rule, [e_s, e_c],
                     [_vm("access.prospect_list", ["es"]),
                      _vm("access.prospect_list", ["ec"])],
                     evaluation_time=1)
    assert out["status"] == "UNKNOWN", out
    assert out["rule_evaluation"]["sufficient"] is True, out
    assert out["rule_evaluation"]["contradicting"] is True, out


def e_partial_unit_a_sat_unit_b_fail() -> None:
    """E: unit A SATISFIED + unit B FAILED -> A3b -> PARTIAL."""
    e_sat = _ev("s", "Setiap perubahan yang diuji punya baseline tercatat "
                     "dan hasilnya dibandingkan terhadap baseline.")
    e_fail = _ev("f", "Kami mengubah penawaran tanpa baseline sama sekali.")
    rule = DRAFT_PREDICATES["experiment.baseline_comparison"]
    outcomes = unit_outcomes(rule, {"perubahan:A": [e_sat],
                                    "perubahan:B": [e_fail]})
    assert outcomes == {"perubahan:A": "SATISFIED",
                        "perubahan:B": "FAILED"}, outcomes
    pre, conflicts = build_precomputed(outcomes)
    assert conflicts == [] and pre["partial"] is True, pre
    out = adjudicate("experiment.baseline_comparison", rule,
                     [e_sat, e_fail], [], evaluation_time=1,
                     precomputed_rule_evaluation=pre)
    assert out["status"] == "PARTIAL", out


def f_two_evidence_one_unit() -> None:
    """F: dua evidence SATU unit -> per-unit eval menggabungkan -> SATISFIED."""
    e1 = _ev("u1", "Setiap perubahan punya baseline tercatat.")
    e2 = _ev("u2", "Hasil dibandingkan terhadap baseline.")
    rule = DRAFT_PREDICATES["experiment.baseline_comparison"]
    outcomes = unit_outcomes(rule, {"perubahan:Z": [e1, e2]})
    assert outcomes == {"perubahan:Z": "SATISFIED"}, outcomes


def g_promoted_artifact_is_runtime_source() -> None:
    """PHASE-5 PROMOTION (runtime proof): formal_rules_compiled.json is now
    populated — compile_from_repo_artifact against the LIVE registry yields a
    valid envelope, and a positive verify_proposal reaches VERIFIED (not
    NO_FORMAL_RULE) — the artifact = RUNTIME SOURCE, not just a fixture."""
    import json as _json
    reg = _json.loads(
        Path(__file__).parent.parent.parent.joinpath(
            "ontology/registry/requirement_registry.json").read_text(
            encoding="utf-8"))
    entries = reg["requirements"]
    from ontology.mapper.formal_compiler import compile_from_repo_artifact
    envelope = compile_from_repo_artifact(entries)
    assert set(envelope["rules"]) == {
        "access.prospect_list", "offering.exists",
        "experiment.baseline_comparison",
        # promosi A3 (int 09 §9.8): FP=0 & MIXED=0
        "access.icp", "offering.differentiation"}, envelope["rules"]
    contract.set_live_registry(entries)
    rids = {r["requirement_id"] for r in entries}
    idx = {"e": _ev("e", "Seluruh entri daftar prospek memuat nama nyata dan "
                             "asal yang jelas.")}
    vm = contract.verify_proposal(
        {"proposed_by": "t", "requirement_id": "access.prospect_list",
         "evidence_refs": ["e"], "proposed_at": 1}, idx, rids, envelope)
    assert vm.get("verified") is True, vm  # artefak live -> VERIFIED
    # mode-aware branch for offering (BINARY) from the artifact
    idx2 = {"e": _ev("e", "Produk konkret dengan deliverable jelas sudah "
                           "tersedia.")}
    vm2 = contract.verify_proposal(
        {"proposed_by": "t", "requirement_id": "offering.exists",
         "evidence_refs": ["e"], "proposed_at": 1}, idx2, rids, envelope)
    assert vm2.get("verified") is True, vm2


def main() -> int:
    tests = [
        ("A proposisi tersebar 2+ evidence", a_propositions_spread),
        ("B lintas-unit TIDAK dirakit (jalur unit + sidecar)", b_cross_unit_not_composed),
        ("C negasi global lintas-evidence (dikunci)", c_negation_scope_global),
        ("D conflict -> UNKNOWN, tak silent-VERIFIED", d_conflict_never_silent_verified),
        ("E unit A SAT + unit B FAIL -> PARTIAL", e_partial_unit_a_sat_unit_b_fail),
        ("F dua evidence satu unit -> SATISFIED", f_two_evidence_one_unit),
        ("G artefak LIVE = sumber runtime (fase-5 promosi)",
         g_promoted_artifact_is_runtime_source),
    ]
    for name, fn in tests:
        check(name, fn)
    for name, ok, why in RESULTS:
        print(f"  {'✅' if ok else '❌'} {name}" + (f" | {why}" if why else ""))
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"\nFASE-4: {passed}/{len(RESULTS)} PASS")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
