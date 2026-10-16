"""SEMANTIC CHALLENGE MATRIX — Batch-2 (owner order 27 Sep).

Shifts the testing unit from 'examples we made up' to 'language
variations that may appear in the real world'. 6 dimensions (owner):
exact · paraphrase · indirect · split-across-turns · negation/
qualification · ambiguous.

Metric per branch: TP (semantics satisfied -> match) · TN (not satisfied
-> no match) · FN (satisfied -> no match = FALSE UNKNOWN) · FP (not
satisfied -> match = FALSE POSITIVE).

NOT A GATE (exit always 0): this is a MEASUREMENT INSTRUMENT — output = report for the
promotion decision. Owner prohibition: DO NOT patch the predicate for each FN;
distinguish 3 FN causes: (1) narrow lexical predicate, (2) evidence
proposal not yet available, (3) multi-evidence/cross-turn need —
rough automatic classification below.

Case format: (rid, dimension, [text...] | text, expected_set_semantics).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))  # mvp/

from core.schema.evidence import EvidenceItem  # noqa: E402
from core.stages.rule_predicates import evaluate_predicate  # noqa: E402
from ontology.mapper.test_calibration import BRANCHES, DRAFT_PREDICATES  # noqa: E402

BATCH2 = ("offering.problem", "access.icp", "offering.differentiation")

CASES = [
    # ---------------- access.icp (semantics: type+level+role)
    ("access.icp", "exact",
     "ICP tertulis berisi jenis usaha, level, dan peran pembeli.",
     {"sufficient"}),
    ("access.icp", "paraphrase",
     "Target saya SaaS tahap awal, founder sebagai decision maker.",
     {"sufficient"}),
    ("access.icp", "indirect",
     "Biasanya saya menjual ke founder perusahaan SaaS kecil.",
     {"sufficient"}),
    ("access.icp", "split",
     ["Target saya perusahaan SaaS tahap awal.",
      "Decision maker-nya founder."],
     {"sufficient"}),
    ("access.icp", "negation",
     "Kami menargetkan SaaS, tapi belum tahu siapa decision maker-nya.",
     set()),
    ("access.icp", "ambiguous",
     "Target kami founder SaaS.",  # border: level not stated -> registry
     set()),                          # strict (3 elements) -> does not satisfy
    # ---------------- offering.problem (semantics: specific + impact)
    ("offering.problem", "exact",
     "Masalah pelanggan terlambat merespons prospek, dampaknya hilangnya "
     "deal besar.", {"sufficient"}),
    ("offering.problem", "paraphrase",
     "Pelanggan sering terlambat follow-up sehingga banyak peluang hilang.",
     {"sufficient"}),
    ("offering.problem", "indirect",
     "Masalah yang kami selesaikan sebenarnya bukan response time, "
     "melainkan trust.", set()),  # specific but WITHOUT impact -> not enough
    ("offering.problem", "negation",
     "Kami tahu masalahnya, tetapi belum tahu dampaknya.",
     set()),  # impact not stated -> does not satisfy (must be TN!)
    ("offering.problem", "split",
     ["Masalah: prospek hilang di tahap follow-up.",
      "Dampaknya: 40% deal batal."],
     {"sufficient"}),
    ("offering.problem", "ambiguous",
     "Ada beberapa masalah umum di bisnis kami, dampaknya kecil.",
     {"contradicting"}),  # generic -> contradicting (registry)
    # ---------------- differentiation (semantics: differentiator on a cared-about dimension)
    ("offering.differentiation", "exact",
     "Pembeda kami di dimensi yang dipedulikan customer: waktu "
     "pengiriman 2 hari.", {"sufficient"}),
    ("offering.differentiation", "paraphrase",
     "Kami unggul karena onboarding dua hari, sementara alternatif "
     "biasanya dua minggu.", {"sufficient"}),
    ("offering.differentiation", "indirect",
     "Pelanggan pilih kami karena kami bisa selesai dua minggu, "
     "kompetitor butuh dua bulan.", {"sufficient"}),
    ("offering.differentiation", "negation",
     "Kami belum bisa menyebut bedanya dengan kompetitor.",
     {"contradicting"}),  # registry: 'cannot be named' = contradicting
    ("offering.differentiation", "ambiguous",
     "Kami rasa lebih bagus dari pesaing.",  # generic claim
     {"contradicting"}),
    ("offering.differentiation", "split",
     ["Kami unggul di waktu tunggu.",
      "Yang dipedulikan customer memang waktu tunggu kami."],
     {"sufficient"}),
]


def _ev(i: int, text: str) -> EvidenceItem:
    return EvidenceItem(id=f"cm.{i}", signal=text, source_quote=text,
                        level="self_reported", topic="REVENUE_STATE")


def _got(rid: str, texts: list[str]) -> set[str]:
    pred = DRAFT_PREDICATES[rid]
    branches = BRANCHES if pred["mode"] == "PARTIAL" \
        else ("sufficient", "contradicting")
    evs = [_ev(i, t) for i, t in enumerate(texts)]
    return {b for b in branches if evaluate_predicate(pred[b], evs, negation_aware=True)[0]}


def _fn_cause(rid: str, texts: list[str]) -> str:
    """Rough classification of FN causes (owner prohibition: do not blind-
    patch — identify first): lexical-narrow vs needs cross-evidence."""
    pred = DRAFT_PREDICATES[rid]["sufficient"]
    # literal needles from the predicate tree
    needles: list[str] = []

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k in ("text_contains_any", "text_contains_all") \
                        and isinstance(v, list):
                    needles.extend(v)
                elif isinstance(v, (dict, list)):
                    walk(v)
        elif isinstance(node, list):
            for x in node:
                walk(x)
    walk(pred)
    joined = " ".join(texts).lower()
    missing = [n for n in needles if n.lower() not in joined]
    if missing:
        per = [all(n.lower() in t.lower() for n in needles)
               for t in texts]
        if not any(per) and len(texts) > 1:
            return f"cross-evidence (per-evidence insufficient; missing needle {missing})"
        return f"predicate-lexical-narrow (missing literal needle: {missing})"
    return "uncertain — all needles present but another branch rejects"


def main() -> int:
    rows = []
    for rid, dim, texts, expected in CASES:
        t = [texts] if isinstance(texts, str) else list(texts)
        got = _got(rid, t)
        fn = set(expected) - got
        fp = got - set(expected)
        if not expected and not got:
            label = "TN"
        elif not fn and not fp:
            label = "TP"
        elif fn and not fp:
            label = "FN"
        elif fp and not fn:
            label = "FP"
        else:
            label = "MIXED"
        cause = ""
        if fn and label in ("FN", "MIXED"):
            cause = _fn_cause(rid, t)
        rows.append((rid, dim, label, sorted(fn), sorted(fp), cause))
        print(f"  [{label:5}] {rid:26} {dim:10} "
              f"exp={sorted(expected)} got={sorted(got)}"
              + (f"  FN-> {cause}" if cause else ""))
    # per-entry summary
    print("\n=== SUMMARY ===")
    for rid in BATCH2:
        rs = [r for r in rows if r[0] == rid]
        c = {k: sum(1 for r in rs if r[2] == k) for k in
             ("TP", "TN", "FN", "FP", "MIXED")}
        print(f"  {rid}: TP={c['TP']} TN={c['TN']} FN={c['FN']} "
              f"FP={c['FP']} MIXED={c['MIXED']}")
    print("\nNote: MEASUREMENT INSTRUMENT, not a gate (exit 0). Owner "
          "prohibition: do not patch the predicate per FN — cause classification "
          "in the FN-> column (predicate-lexical-narrow vs cross-evidence) "
          "= decision basis, not a fix order.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
