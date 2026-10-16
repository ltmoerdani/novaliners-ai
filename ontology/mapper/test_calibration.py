"""CALIBRATION GATE phase-3 (review 377974b): SEMANTIC COVERAGE +
HARD-NEGATIVE. After phase-1 (predicate execution) & phase-2 (branch-
exact), phase-3 requires per sample:
  positive    = truly satisfies ALL registry propositions
  hard-neg    = very similar, ONE material condition deliberately fails
  partial     = proves BOTH unit sides (not just the word 'beberapa')
Format: (rid, text, expected_set) — branch-exact still applies.
DRAFT = calibrator; the live artifact is EMPTY until the owner's promotion verdict.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))  # mvp/

from core.schema.evidence import EvidenceItem  # noqa: E402
from core.stages.rule_predicates import evaluate_predicate  # noqa: E402

BRANCHES = ("sufficient", "partial", "contradicting")

DRAFT_PREDICATES = {
    "access.prospect_list": {
        "mode": "PARTIAL",
        # universal phrase (registry: ALL entries) rejects two-sided text
        "sufficient": {"any_of": [{"text_contains_all": [
            "seluruh entri", "nama nyata", "asal yang jelas"]}]},
        # both sides: satisfied side (name+origin) AND failed side (other entry)
        # DRIFT-2 (review 494212f): side B MUST fail — 'entri lain
        # JUGA memuat...' must be no-match (that is the sufficient direction)
        "partial": {"any_of": [{"all_of": [
            {"text_contains_all": ["nama nyata", "asal yang jelas"]},
            {"text_present_pattern": "entri lain[^.;]*(tidak|belum|tanpa)"}]}]},
        "no_decisive": {"text_present_pattern": "(?!)"},
        # empty + network WITHOUT a name (phrase variation via regex)
        "contradicting": {"any_of": [
            {"text_contains_any": ["daftar prospek kosong"]},
            {"all_of": [{"text_contains_any": ["network"]},
                         {"text_present_pattern":
                          "tanpa nama|belum punya nama|tanpa satu pun nama"}]}]},
    },
    "offering.exists": {
        "mode": "BINARY",
        # concrete + deliverable, REJECTED if a negation is present (masih/belum)
        "sufficient": {"any_of": [{"all_of": [
            {"text_contains_any": ["produk", "jasa", "penawaran"]},
            {"text_contains_any": ["konkret"]},
            {"text_contains_any": ["deliverable"]},
            {"text_absent_pattern": "belum|masih"}]}]},
        "no_decisive": {"text_present_pattern": "(?!)"},
        "contradicting": {"any_of": [
            {"text_contains_any": ["masih berupa ide", "belum konkret",
                                    "berupa rancangan"]}]},
    },
    "experiment.baseline_comparison": {
        "mode": "PARTIAL",
        # 3 registry propositions + negation rejecter ('tidak tercatat')
        # DRIFT-3 (review 494212f): the POSITIVE condition 'tercatat' is mandatory —
        # a negative rejecter alone is not enough ('baseline tersedia tetapi
        # dokumentasinya belum jelas' must be no-match)
        "sufficient": {"any_of": [{"all_of": [
            {"text_contains_any": ["setiap perubahan", "seluruh perubahan"]},
            {"text_contains_any": ["dibandingkan terhadap"]},
            {"text_contains_any": ["tercatat"]},
            {"text_absent_pattern": "tidak tercatat|belum tercatat"}]}]},
        # both full sides: some recorded + some not yet compared
        # DRIFT-1 (review 494212f): side A MUST have baseline+comparison
        # ('dibandingkan terhadap') — 'punya baseline tercatat TAPI belum
        # ada hasil dibandingkan' must be no-match
        "partial": {"any_of": [{"all_of": [
            {"text_contains_any": ["setidaknya satu", "sebagian", "beberapa"]},
            {"text_contains_any": ["tercatat"]},
            {"text_contains_any": ["dibandingkan terhadap"]},
            {"text_contains_any": ["belum dibandingkan"]}]}]},
        "no_decisive": {"text_present_pattern": "(?!)"},
        "contradicting": {"any_of": [
            {"text_contains_any": ["tanpa baseline"]}]},
    },
    # ================= BATCH-2 DRAFT (3 entries, 27 Sep) — DRAFT only;
    # promosi ke artefak = rangkaian fase + verdict review terpisah ====
    "offering.problem": {
        "mode": "BINARY",
        "sufficient": {"any_of": [{"text_contains_all": ["masalah", "dampak"]}]},
        "no_decisive": {"text_present_pattern": "(?!)"},
        "contradicting": {"any_of": [
            {"text_present_pattern": "generik|umum untuk semua"}]},
    },
    "access.icp": {
        "mode": "BINARY",
        "sufficient": {"any_of": [{"text_contains_all": [
            "icp", "jenis", "level", "dan peran"]}]},
        "no_decisive": {"text_present_pattern": "(?!)"},
        "contradicting": {"any_of": [
            {"text_contains_any": ["siapa saja"]}]},
    },
    "offering.differentiation": {
        "mode": "BINARY",
        "sufficient": {"any_of": [{"all_of": [
            {"text_contains_any": ["pembeda"]},
            {"text_contains_any": ["peduli"]},
            {"text_absent_pattern": "bukan yang dipedulikan|tidak dipedulikan"}]}]},
        "no_decisive": {"text_present_pattern": "(?!)"},
        "contradicting": {"any_of": [
            {"text_contains_any": ["kualitas kami bagus"]}]},
    },
}

# (rid, text, expected_set) — phase-3: full positive + hard-neg material
CALIBRATION = [
    # ---------- access.prospect_list
    ("access.prospect_list",  # positive: all entries + name + origin
     "Seluruh entri daftar prospek memuat nama nyata dan asal yang jelas.",
     {"sufficient"}),
    ("access.prospect_list",  # hard-neg: all entries, BUT the origin failed
     "Seluruh entri daftar prospek memuat nama, tetapi asalnya belum jelas.",
     set()),
    ("access.prospect_list",  # partial: both entry sides (A full + B not)
     "Satu entri memuat nama nyata dan asal yang jelas; entri lain tidak "
     "memuatnya sama sekali.", {"partial"}),
    ("access.prospect_list",  # hard-neg partial: 'beberapa' without the satisfied side
     "Beberapa prospek sudah punya nama, tetapi tidak ada satu pun asal "
     "yang jelas.", set()),
    ("access.prospect_list", "Daftar prospek kosong.", {"contradicting"}),
    ("access.prospect_list",  # contradicting variation: no name yet
     "Punya network luas, belum punya nama prospek.", {"contradicting"}),
    ("access.prospect_list",  # hard-neg contradicting: network WITH a name
     "Punya network luas, dengan nama dan asal prospek yang jelas.",
     set()),
    # ---------- offering.exists
    ("offering.exists",  # full positive (not an offering-only)
     "Produk konkret dengan deliverable jelas sudah tersedia.", {"sufficient"}),
    ("offering.exists",  # hard-neg: all words present, BUT a material negation
     "Produk konkret masih berupa rancangan; deliverable belum tersedia.",
     {"contradicting"}),
    ("offering.exists", "Produk kami masih berupa ide.", {"contradicting"}),
    # ---------- experiment.baseline_comparison
    ("experiment.baseline_comparison",  # 3 proposisi utuh
     "Setiap perubahan punya baseline tercatat dan hasilnya dibandingkan "
     "terhadap baseline tersebut.", {"sufficient"}),
    ("experiment.baseline_comparison",  # hard-neg: all BUT not recorded
     "Setiap perubahan dibandingkan terhadap baseline, tetapi baseline "
     "tidak tercatat.", set()),
    ("experiment.baseline_comparison",  # partial full two-sided
     "Setidaknya satu perubahan punya baseline tercatat yang hasilnya "
     "dibandingkan terhadap baseline, dan setidaknya satu perubahan "
     "belum dibandingkan.", {"partial"}),
    ("experiment.baseline_comparison",  # hard-neg partial: without the satisfied side
     "Beberapa perubahan belum dibandingkan; perubahan lainnya masih "
     "direncanakan.", set()),
    ("experiment.baseline_comparison",
     "Kami mengubah penawaran tanpa baseline sama sekali.", {"contradicting"}),
    # ---------- BATCH-2: offering.problem
    ("offering.problem",
     "Masalah pelanggan terlambat merespons prospek, dampaknya hilangnya "
     "deal besar.", {"sufficient"}),
    ("offering.problem",  # hard-neg: generik (= contradicting registry)
     "Masalahnya umum untuk semua orang.", {"contradicting"}),
    ("offering.problem",
     "Masalah yang kami sebut masih generik tanpa spesifik.", {"contradicting"}),
    # ---------- BATCH-2: access.icp
    ("access.icp",
     "ICP tertulis berisi jenis usaha, level, dan peran pembeli.",
     {"sufficient"}),
    ("access.icp",  # hard-neg: peran hilang
     "ICP tertulis berisi jenis usaha dan level, perannya belum ada.",
     set()),
    ("access.icp",
     "Kami hubungi siapa saja.", {"contradicting"}),
    ("access.icp",  # hard-neg contradicting: neutral (without needle C)
     "ICP kami sedang disusun untuk kuartal ini.", set()),
    # ---------- BATCH-2: offering.differentiation
    ("offering.differentiation",
     "Pembeda kami di dimensi yang dipedulikan customer: waktu "
     "pengiriman 2 hari.", {"sufficient"}),
    ("offering.differentiation",  # hard-neg: dimension not the one cared about
     "Kami punya pembeda, tapi dimensinya bukan yang dipedulikan "
     "customer.", set()),
    ("offering.differentiation",
     "Kualitas kami bagus.", {"contradicting"}),
    ("offering.differentiation",  # hard-neg contradicting: netral
     "Kami punya pembeda pada dimensi waktu.", set()),
]


def main() -> int:
    failures: list[str] = []
    for rid, text, expected in CALIBRATION:
        ev = EvidenceItem(id="cal.1", signal=text, source_quote=text,
                          level="self_reported", topic="REVENUE_STATE")
        pred = DRAFT_PREDICATES[rid]
        branches = BRANCHES if pred["mode"] == "PARTIAL" \
            else ("sufficient", "contradicting")
        got = {b for b in branches
               if evaluate_predicate(pred[b], [ev], negation_aware=True)[0]}
        if got != set(expected):
            failures.append(
                f"{rid}: {text[:55]!r} -> {sorted(got)} "
                f"(harus {sorted(expected)})")
    ev = EvidenceItem(id="cal.x", signal="apapun", source_quote="apapun",
                      level="self_reported", topic="REVENUE_STATE")
    for rid, pred in DRAFT_PREDICATES.items():
        if evaluate_predicate(pred["no_decisive"], [ev],
                              negation_aware=True)[0]:
            failures.append(f"{rid}.no_decisive: sentinel match — dilarang")
    total = len(CALIBRATION) + len(DRAFT_PREDICATES)
    for f in failures:
        print(f"  ❌ {f}")
    print(f"\nCALIBRATION(fase-3 branch-exact): "
          f"{total - len(failures)}/{total} PASS")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
