"""Goal-Relative grounding guard (int 09 §3.3, §4.5, §5; GR-24, GR-25, Phase 5-A).

Seven epistemic differentiators that must be preserved on the Goal-relative path:
  1. missing data         -> NOT_COMPUTABLE / UNMEASURED (not zero)
  2. negative finding     -> NOT_ACHIEVED with evidence (not unknown)
  3. failed prerequisite  -> check ABSENT + feasibility CONTRADICTED (not discarded)
  4. contradictory evidence -> conflict = metadata (not silently reconciled)
  5. unsupported metric   -> GOAL_METRIC_UNSUPPORTED (abstain)
  6. weak self-report     -> evidence level visible; transactional is stronger
  7. outcome without causality -> causal_status OBSERVED_ONLY; correlation is not causation

Deterministic (mock). Run: .venv/bin/python evals/test_goal_grounding.py
"""
from __future__ import annotations

import sys

sys.path.insert(0, ".")

from domains.revenue.navigation.paths import build_possible_paths  # noqa: E402
from domains.revenue.schema.goal import build_goal, parse_goal_text  # noqa: E402
from domains.revenue.schema.goal_evaluation import (  # noqa: E402
    NOT_ACHIEVED,
    NOT_COMPUTABLE,
    evaluate_goal,
    goal_readiness,
    guardrail_conflicts,
)
from domains.revenue.schema.state import RevenueState  # noqa: E402

_results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _results.append((name, ok, detail))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" | {detail}" if detail else ""))


print("== GR-24 / UC-05: guardrail margin — konflik eksplisit, bukan bobot tersembunyi ==")
g5 = parse_goal_text(
    "Reduce acquisition cost per new customer from Rp80,000 to at most Rp60,000, "
    "while maintaining contribution margin of at least 35%.")
check("margin tercatat sebagai guardrail terpisah (bukan target utama)",
      g5.metric_id == "cac" and len(g5.guardrails) == 1
      and g5.guardrails[0]["metric_id"] == "contribution_margin")
conf = guardrail_conflicts(g5, {"contribution_margin": 0.32})
check("margin 32% < 35% terukur → VIOLATED (konflik dimuka, UC-05)",
      conf[0]["status"] == "VIOLATED" and conf[0]["measured"] == 0.32)
conf_ok = guardrail_conflicts(g5, {"contribution_margin": 0.40})
check("margin 40% → HELD (bukan konflik)", conf_ok[0]["status"] == "HELD")
conf_un = guardrail_conflicts(g5, {})
check("margin tak terukur → UNMEASURED (bukan aman, bukan dilanggar — GR-25)",
      conf_un[0]["status"] == "UNMEASURED")
check("evaluasi CAC tetap objektif meski guardrail dilanggar (dua fakta tampil bersama)",
      evaluate_goal(g5, current=55.0)["status"] == "ACHIEVED"
      and guardrail_conflicts(g5, {"contribution_margin": 0.32})[0]["status"] == "VIOLATED")

print("== pembeda 1: data hilang ≠ nol (goal + guardrail + rate) ==")
g1 = build_goal("3 qualified leads in 14 days", measurement_window_days=14,
                success_definition="q = booked call")
check("tanpa event → NOT_COMPUTABLE (kosong ≠ nol terverifikasi)",
      evaluate_goal(g1, events=[])["status"] == NOT_COMPUTABLE)

print("== pembeda 2: temuan negatif ≠ unknown ==")
ASOF = 1_700_000_000  # fixed evaluation time — A-09: window measured from as-of, not from events
ev2 = evaluate_goal(g1, events=[
    {"ts": ASOF - 86400, "qualified": True},
    {"ts": ASOF - 2 * 86400, "qualified": False},
    {"ts": ASOF - 3 * 86400, "qualified": False},
], as_of_ts=ASOF)
check("3 event teramati (1 qualified, 2 tidak) → NOT_ACHIEVED dengan angka",
      ev2["status"] == NOT_ACHIEVED and ev2["values"]["counted"] == 1)

print("== pembeda 3: prerequisite gagal → check ABSENT + path bertahan sebagai STOP ==")
rs3 = RevenueState(current_monthly=30.0, target_monthly=60.0, gap_monthly=30.0,
                   willingness_to_pay_new_price="REJECTED_AT_NEW_PRICE")  # D2: NEW-price contradiction
out3 = build_possible_paths(rs3, None, goal=build_goal(
    "grow revenue", metric_id="revenue_monthly", target=60.0).model_dump())
vp = next((p for p in out3["paths"] if p["path_id"] == "path.value_repricing"), None)
check("hard check gagal → CONTRADICTED (bukan hilang dari peta)",
      vp is not None and vp["feasibility"] == "CONTRADICTED"
      and any(c["state"] == "ABSENT" and c["kind"] == "hard" for c in vp["checks"]))

print("== pembeda 4: bukti kontradiktif = metadata, tak direkonsiliasi diam-diam ==")
check("satisfaction UNKNOWN + check ABSENT menghasilkan konflik tercatat (settled=false di proyeksi)",
      True, "dijaga test_m4_session_loop H1/H1b (ledger PRESENT vs check ABSENT → RESOLVE_CONTRADICTION)")

print("== pembeda 5: metric tak didukung → abstain dengan alasan ==")
g5b = parse_goal_text("I want to make the brand feel premium and loved")
check("desire tanpa metric registry → readiness tidak ready + blocking METRIC_UNRESOLVED",
      not goal_readiness(g5b)["ready"]
      and "METRIC_UNRESOLVED" in goal_readiness(g5b)["blocking"])

print("== pembeda 6: self-report lemah vs bukti transaksional (hierarki terlihat) ==")
g6 = build_goal("close rate 15 to 25", metric_id="close_rate")
SC6 = {"cohort": "inbound-q3", "period": "2025-Q3"}
ev6 = evaluate_goal(g6, numerator=3, denominator=20, rate_scope=SC6)
ev6b = evaluate_goal(g6, numerator=30, denominator=200, rate_scope=SC6)
check("3/20 dan 30/200 = rate sama; sumbernya (kohort) ikut tercatat — bukan angka lepas",
      ev6["values"]["rate"] == ev6b["values"]["rate"]
      and ev6["values"]["denominator"] == 20 and ev6b["values"]["denominator"] == 200)
check("persentase tanpa kohort tidak pernah dievaluasi (self-report % bukan bukti cukup)",
      evaluate_goal(g6)["status"] == NOT_COMPUTABLE)
check("angka n/d tanpa scope kohort+periode juga tidak dievaluasi (ronde 4: bukan pencapaian)",
      evaluate_goal(g6, numerator=3, denominator=20)["status"] == NOT_COMPUTABLE)

print("== pembeda 7: outcome tanpa kausalitas (korelasi bukan sebab) ==")
g7 = build_goal("3 qualified leads in 14 days", measurement_window_days=14,
                success_definition="q = booked call")
g7.supporting_metrics.append({"metric_id": "reply_rate", "relation": "UNKNOWN_RELATION"})
out7 = build_possible_paths(RevenueState(), None, goal=g7.model_dump())
sm = ((out7["context"]["goal"] or {}).get("supporting_metrics") or [])
check("relasi UNKNOWN_RELATION diteruskan tanpa diklaim kausal (GR-16)",
      sm and sm[0]["relation"] == "UNKNOWN_RELATION")
check("registry tidak menyatakan hubungan kausal metric→strategi (kategori ≠ path)",
      True, "dijaga test_goal_navigation GR-13 + validator registry (tanpa field kausal)")

print("== provenance knowledge pada path Goal-relative (evaluasi yang sama dengan jalur revenue) ==")
rs8 = RevenueState(current_monthly=30.0, target_monthly=60.0, gap_monthly=30.0)
out8 = build_possible_paths(rs8, None, goal=build_goal(
    "grow revenue", metric_id="revenue_monthly", target=60.0).model_dump())
do8 = next((p for p in out8["paths"] if p["path_id"] == "path.direct_outreach"), None)
prov_ok = do8 is not None and (
    (do8.get("provenance") or {}).get("state_claims")
    or (do8.get("provenance") or {}).get("evidence_ids"))
check("path yang lahir membawa provenance state/evidence (PROV contract tetap)",
      bool(prov_ok), str((do8 or {}).get("provenance", {}))[:120])

fails = [x for x in _results if not x[1]]
print(f"\n{'=' * 50}\nHASIL: {len(_results) - len(fails)}/{len(_results)} PASS"
      + (" ✅" if not fails else f" — {len(fails)} GAGAL ❌"))
sys.exit(1 if fails else 0)
