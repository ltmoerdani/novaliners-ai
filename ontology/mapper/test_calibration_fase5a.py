"""PHASE-5A — ARTIFACT SEMANTIC FIDELITY AUDIT (review 494212f): 3 live
drifts. The regression MUST read the predicate FROM formal_rules_compiled.json
(not DRAFT_PREDICATES) — the gate tests the artifact that the runtime will use.

Drifts:
1. baseline.partial: side A MUST have baseline+comparison
2. prospect.partial : side B MUST fail (negative regex)
3. baseline.sufficient: POSITIVE condition 'tercatat' (absent alone is not enough)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))  # mvp/

import json as _json

from core.schema.evidence import EvidenceItem  # noqa: E402
from core.stages.rule_predicates import evaluate_predicate  # noqa: E402
from ontology.mapper.formal_compiler import compile_from_repo_artifact  # noqa: E402

_REG = _json.loads(
    (Path(__file__).parent.parent.parent /
     "ontology/registry/requirement_registry.json").read_text(encoding="utf-8"))
_ENVELOPE = compile_from_repo_artifact(_REG["requirements"])
ART = _ENVELOPE["rules"]  # predicate FROM the live artifact
MODES = _ENVELOPE["modes"]


def _ev(text: str) -> EvidenceItem:
    return EvidenceItem(id="a.1", signal=text, source_quote=text,
                        level="self_reported", topic="REVENUE_STATE")


def _branch(rid: str, text: str) -> set[str]:
    pred = ART[rid]
    branches = ("sufficient", "partial", "contradicting") \
        if MODES[rid] == "PARTIAL" else ("sufficient", "contradicting")
    ev = _ev(text)
    return {b for b in branches if evaluate_predicate(pred[b], [ev], negation_aware=True)[0]}


CASES = [
    # DRIFT-1: baseline.partial — full two-sided positive vs side-A-only hard-neg
    ("experiment.baseline_comparison", "partial",
     "Setidaknya satu perubahan punya baseline tercatat yang hasilnya "
     "dibandingkan terhadap baseline, dan setidaknya satu perubahan "
     "belum dibandingkan.", {"partial"}),
    ("experiment.baseline_comparison", "partial",
     "Beberapa perubahan punya baseline tercatat, tetapi belum ada hasil "
     "yang dibandingkan; perubahan lain belum dibandingkan.", set()),
    # DRIFT-2: prospect.partial — positive two-sided vs 'entri lain JUGA'
    ("access.prospect_list", "partial",
     "Satu entri memuat nama nyata dan asal yang jelas; entri lain tidak "
     "memuatnya sama sekali.", {"partial"}),
    ("access.prospect_list", "partial",
     "Satu entri memuat nama nyata dan asal yang jelas; entri lain juga "
     "memuat nama nyata dan asal yang jelas.", set()),
    # DRIFT-3: baseline.sufficient — positif tercatat vs 'tersedia tapi
    # dokumentasinya belum jelas' (absent needle does not catch it)
    ("experiment.baseline_comparison", "sufficient",
     "Setiap perubahan punya baseline tercatat dan hasilnya dibandingkan "
     "terhadap baseline tersebut.", {"sufficient"}),
    ("experiment.baseline_comparison", "sufficient",
     "Setiap perubahan dibandingkan terhadap baseline, tetapi baseline "
     "tersedia dan dokumentasinya belum jelas.", set()),
    # A3 PROMOTION (int 09 §9.8) — the regression reads the ARTIFACT, not DRAFT
    ("access.icp", "sufficient",
     "ICP tertulis berisi jenis usaha, level, dan peran pembeli.",
     {"sufficient"}),
    ("access.icp", "sufficient",
     "ICP tertulis berisi jenis usaha dan level, perannya belum ada.", set()),
    ("access.icp", "contradicting", "Kami hubungi siapa saja.",
     {"contradicting"}),
    ("offering.differentiation", "sufficient",
     "Pembeda kami di dimensi yang dipedulikan customer: waktu "
     "pengiriman 2 hari.", {"sufficient"}),
    ("offering.differentiation", "sufficient",
     "Kami punya pembeda, tapi dimensinya bukan yang dipedulikan "
     "customer.", set()),
    ("offering.differentiation", "contradicting", "Kualitas kami bagus.",
     {"contradicting"}),
]


def main() -> int:
    failures: list[str] = []
    # ensure the predicate really comes from the artifact (not DRAFT import)
    assert "access.prospect_list" in ART and ART, "artefak kosong?"
    for rid, branch, text, expected in CASES:
        got = _branch(rid, text)
        # evaluation only the branch branch + other branches must not be wrong
        # (branch-exact intact: compare against ALL branches)
        if branch not in expected and branch in got:
            got = got  # already covered by the set comparison
        if got != set(expected) and branch in set(expected):
            failures.append(f"{rid}.{branch}: {text[:55]!r} -> {sorted(got)} "
                            f"(harus {sorted(expected)})")
        elif branch not in set(expected) and branch in got:
            failures.append(f"{rid}.{branch} OVER-ADMIT: {text[:55]!r} "
                            f"-> {sorted(got)} (harus tak mengandung {branch})")
    # additionally: make sure other branches in hard-neg do not leak for cases
    # those with expected = set()
    for rid, branch, text, expected in CASES:
        if expected == set():
            got = _branch(rid, text)
            if got:
                failures.append(f"{rid}: hard-neg {text[:55]!r} bocor cabang "
                                f"{sorted(got)}")
    uniq = {f for f in failures}
    for f in sorted(uniq):
        print(f"  ❌ {f}")
    total = len(CASES)
    print(f"\nFASE-5A(artefact fidelity): {total - len(uniq)}/{total} PASS")
    return 0 if not uniq else 1


if __name__ == "__main__":
    raise SystemExit(main())
