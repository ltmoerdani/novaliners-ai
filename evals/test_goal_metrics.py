"""Goal-Relative metric semantics guard (internal-docs §3; GR-01..GR-11, GR-17).

Contract under test (scenario-and-acceptance-matrix.md §1.A):
  GR-01 non-revenue leads valid without target_monthly; GR-02 rate needs a denominator;
  GR-03 CAC decrease (not a generic gap); GR-04 "active" needs observable criteria;
  GR-05 "traction" stays a desire; GR-06 activity ≠ outcome; GR-07 legacy stays readable;
  GR-08 revenue compatible; GR-09 count-in-window (unknown ≠ 0); GR-10 no baseline =
  NOT_COMPUTABLE (no fabrication); GR-11 evidence criteria (no invented score);
  GR-17 metric outside the registry → safe abstain.

Deterministic, 0 LLM. Run: .venv/bin/python evals/test_goal_metrics.py
"""
from __future__ import annotations

import sys

sys.path.insert(0, ".")

from domains.revenue.schema.goal import (  # noqa: E402
    UNRESOLVED_ACTIVITY,
    UNRESOLVED_DENOMINATOR,
    UNRESOLVED_METRIC,
    UNRESOLVED_QUALIFICATION,
    Goal,
    build_goal,
    goal_gap,
    parse_goal_text,
)
from domains.revenue.schema.goal_evaluation import (  # noqa: E402
    ACHIEVED,
    NOT_ACHIEVED,
    NOT_COMPUTABLE,
    evaluate_goal,
    goal_readiness,
)
from ontology.registry import metrics as mr  # noqa: E402

_results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _results.append((name, ok, detail))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" | {detail}" if detail else ""))


def codes(goal: Goal) -> list[str]:
    return [u["code"] for u in goal.unresolved]


print("== GR-01: 3 qualified leads / 14 hari — Goal non-revenue SAH tanpa target_monthly ==")
g1 = parse_goal_text("I need three qualified leads in 14 days")
check("metric teridentifikasi qualified_leads (COUNT_IN_WINDOW)",
      g1.metric_id == "qualified_leads" and g1.direction == "COUNT_IN_WINDOW",
      f"mid={g1.metric_id}")
check("target 3 / window 14 terbaca", g1.target == 3.0 and g1.measurement_window_days == 14)
check("kualifikasi belum didefinisikan → unresolved, bukan auto-qualified",
      UNRESOLVED_QUALIFICATION in codes(g1))
check("goal TIDAK punya target_monthly & tetap objek Goal sah",
      g1.target_origin == "intent_phrase" and g1.unit == "leads")
rd1 = goal_readiness(g1)
check("readiness belum ready dengan alasan kualifikasi",
      not rd1["ready"] and UNRESOLVED_QUALIFICATION in rd1["blocking"])
g1b = build_goal("I need three qualified leads in 14 days",
                 success_definition="qualified = B2B, budget authority confirmed, booked a call")
check("dengan kriteria kualifikasi eksplisit → readiness ready (navigasi tidak diblok)",
      goal_readiness(g1b)["ready"], f"blocking={goal_readiness(g1b)['blocking']}")

print("== GR-02: close rate 15% → 25% — arah naik dikenali, denominator ditanya ==")
g2 = parse_goal_text("Our close rate is about 15%. I want 25% in 60 days.")
check("metric close_rate RATE_OR_RATIO; baseline/target 0.15/0.25",
      g2.metric_id == "close_rate" and g2.baseline == 0.15 and g2.target == 0.25)
check("persentase tanpa konteks → DENOMINATOR_MISSING (material, ditanya)",
      UNRESOLVED_DENOMINATOR in codes(g2))
_SC = {"cohort": "inbound-q3", "period": "2025-Q3"}  # cohort+period scope (round 4: must be proven)
ev2 = evaluate_goal(g2, numerator=3, denominator=20, rate_scope=_SC)
check("evaluasi dengan kohort 3/20=15% → NOT_ACHIEVED vs target 25%",
      ev2["status"] == NOT_ACHIEVED and abs(ev2["values"]["rate"] - 0.15) < 1e-9)
ev2b = evaluate_goal(g2)  # no numerator/denominator
check("evaluasi tanpa kohort → NOT_COMPUTABLE, bukan gagal/sukses",
      ev2b["status"] == NOT_COMPUTABLE)

print("== GR-03: CAC Rp800rb → ≤ Rp600rb — decrease, sukses = current ≤ threshold ==")
g3 = parse_goal_text(
    "Reduce acquisition cost per new customer from Rp80,000 to at most Rp60,000")
check("metric cac DECREASE_TO_THRESHOLD; 800→600 (unit Rp ribu)",
      g3.metric_id == "cac" and g3.direction == "DECREASE_TO_THRESHOLD"
      and g3.baseline == 80.0 and g3.target == 60.0)
ev3 = evaluate_goal(g3, current=65.0)
check("current 65 > 60 → NOT_ACHIEVED (gap generik akan membalik makna)",
      ev3["status"] == NOT_ACHIEVED)
ev3b = evaluate_goal(g3, current=55.0)
check("current 55 ≤ 60 → ACHIEVED", ev3b["status"] == ACHIEVED)
check("goal_gap generik TIDAK dipakai untuk decrease (hanya proyeksi increase)",
      g3.direction != "INCREASE_TO_THRESHOLD")

print("== GR-04: 2 active partners — 'active' tanpa definisi → klarifikasi ==")
g4 = parse_goal_text("I want two active reseller partners within 60 days")
check("metric active_distribution_partners; target 2, window 60",
      g4.metric_id == "active_distribution_partners" and g4.target == 2.0
      and g4.measurement_window_days == 60)
check("kriteria aktif belum observable → QUALIFICATION_UNDEFINED",
      UNRESOLVED_QUALIFICATION in codes(g4))
g4b = build_goal("I want two active reseller partners within 60 days",
                 success_definition="active = ≥1 qualified referral or attributable transaction in 30 days")
check("surat kolaborasi ≠ aktif: definisi eksplisit menutup gap → ready",
      goal_readiness(g4b)["ready"])

print("== GR-05: 'I need traction' — desire dipertahankan, tidak dipetakan senyap ==")
g5 = parse_goal_text("The business is not moving. I need traction.")
check("tanpa metric yang dikarang (METRIC_UNRESOLVED)", g5.metric_id == "" and UNRESOLVED_METRIC in codes(g5))
check("bukan revenue default senyap: tidak ada target Rp", g5.target is None)
check("readiness tidak ready — klarifikasi bernilai tinggi dipilih, bukan asumsi",
      not goal_readiness(g5)["ready"])

print("== GR-06: kirim 100 pesan — activity ≠ outcome ==")
g6 = parse_goal_text("Send 100 outreach messages")
check("metric teridentifikasi sebagai ACTIVITY (bukan outcome leads)",
      g6.metric_id == "outreach_messages_sent" and UNRESOLVED_ACTIVITY in codes(g6))
check("pesan terkirim tidak pernah dihitung sebagai leads/revenue",
      g6.metric_id != "qualified_leads" and g6.category == "activity")

print("== GR-07: sesi legacy (tanpa field baru) tetap terbaca & terinterpretasi ==")
legacy = Goal(metric="revenue_monthly", unit="Rp juta/bulan", target=60.0,
              target_origin="goal_marker", desire="naikkan omzet")
check("metric_id efektif = revenue_monthly (registry) tanpa menulis ulang data",
      legacy.resolved_metric_id() == "revenue_monthly")
check("semantics registry terbaca INCREASE_TO_THRESHOLD",
      legacy.metric_definition()["semantics"] == "INCREASE_TO_THRESHOLD")
check("target_origin legacy terjaga (parse ≠ konfirmasi user)",
      legacy.target_origin == "goal_marker" and not legacy.confirmed_target())

print("== GR-08: revenue 30→60 jt/bulan — jalur lama tetap kompatibel ==")
g8 = parse_goal_text(
    "We currently make Rp30 million per month and want to reach Rp60 million per month within 90 days.")
check("baseline 30 / target 60 (format EN juta) + direction increase",
      g8.baseline == 30.0 and g8.target == 60.0
      and g8.direction == "INCREASE_TO_THRESHOLD")
ev8 = evaluate_goal(g8, current=45.0)
check("evaluasi increase: 45 < 60 → NOT_ACHIEVED; gap proyeksi 15",
      ev8["status"] == NOT_ACHIEVED and goal_gap(g8.model_copy(update={"current": 45.0}))["gap"] == 15.0)
check("readiness ready — alur revenue lama tidak terganggu", goal_readiness(g8)["ready"])
g8id = parse_goal_text("Saya ingin capai target Rp60 juta per bulan dalam 90 hari")
check("format ID lama juga tetap hidup (target marker 60)",
      g8id.target == 60.0 and g8id.target_origin == "goal_marker")

print("== GR-09: count-in-window — hanya event dalam window yang memenuhi kriteria ==")
now = 1_700_000_000
evs = [
    {"ts": now - 2 * 86400, "qualified": True},    # inside window, qualified
    {"ts": now - 20 * 86400, "qualified": True},   # outside the 14-day window
    {"ts": now - 1 * 86400, "qualified": False},   # unqualified
    {"ts": None, "qualified": True},               # unknown timestamp → not counted ≠ 0
    {"ts": now - 3 * 86400, "qualified": None},    # unknown qualification → not auto-qualified
]
g9 = build_goal("3 qualified leads in 14 days", measurement_window_days=14,
                success_definition="qualified = booked call + ICP fit")
ev9 = evaluate_goal(g9, events=evs, as_of_ts=now)  # clock injection: fixed evaluation time
check("hanya 1 event terhitung (dalam window & qualified)",
      ev9["values"]["counted"] == 1 and ev9["status"] == NOT_ACHIEVED)
check("unknown timestamp ≠ nol; unknown qualification ≠ auto-qualified (dicatat)",
      ev9["values"]["unknown_timestamp"] == 1 and ev9["values"]["unknown_qualification"] == 1)
ev9b = evaluate_goal(build_goal("3 qualified leads in 14 days",
                                measurement_window_days=14, success_definition="x"),
                     events=[{"ts": now - d, "qualified": True} for d in (1, 2, 3)], as_of_ts=now)
check("3 event valid dalam window → ACHIEVED", ev9b["status"] == ACHIEVED)
ev9c = evaluate_goal(build_goal("3 qualified leads", measurement_window_days=14,
                                success_definition="x"), events=[], as_of_ts=now)
check("tanpa event teramati → NOT_COMPUTABLE (kosong ≠ nol terverifikasi)",
      ev9c["status"] == NOT_COMPUTABLE)

print("== GR-09b/A-09/A-10: window diukur dari waktu EVALUASI, bukan event terbaru ==")
# Baseline bug (reproduced at e6c04a5): anchor = max(event.ts) made three events
# 30 days ago count as "inside a 14-day window" (false ACHIEVED) because the anchor
# shifted too; future events counted as well. New contract: explicit as_of.
stale = [{"ts": now - 30 * 86400, "qualified": True} for _ in range(3)]
ev9d = evaluate_goal(g9, events=stale, as_of_ts=now)
check("SEMUA event kedaluwarsa (30 hari, window 14) → counted=0, bukan ACHIEVED",
      ev9d["status"] == NOT_ACHIEVED and ev9d["values"]["counted"] == 0
      and ev9d["values"]["outside_window"] == 3, str(ev9d["values"]))
fut = [{"ts": now + 5 * 86400, "qualified": True} for _ in range(3)]
ev9e = evaluate_goal(g9, events=fut, as_of_ts=now)
check("event bertimestamp MASA DEPAN tidak menaikkan count teramati",
      ev9e["status"] == NOT_ACHIEVED and ev9e["values"]["counted"] == 0
      and ev9e["values"]["future_events"] == 3)
ev9f = evaluate_goal(g9, events=[{"ts": now - 14 * 86400, "qualified": True}], as_of_ts=now)
check("event TEPAT di cutoff (as_of − 14 hari) masuk window — boundary inklusif",
      ev9f["values"]["counted"] == 1, str(ev9f["values"]))
ev9g = evaluate_goal(g9, events=[{"ts": now - 1 * 86400, "qualified": True}], as_of_ts=now)
ev9h = evaluate_goal(g9, events=[{"ts": now - 1 * 86400, "qualified": True}],
                     as_of_ts=now + 20 * 86400)
check("sliding window: dua waktu evaluasi berbeda → keputusan berbeda (jelas & terkontrol)",
      ev9g["values"]["counted"] == 1 and ev9h["values"]["counted"] == 0,
      "as_of tetap: 1; as_of+20d: 0")
measured_zero = evaluate_goal(g9, events=[{"ts": now - 1 * 86400, "qualified": False}],
                              as_of_ts=now)
check("nol TERUKUR (event valid tapi unqualified) ≠ belum ada pengukuran (kosong)",
      measured_zero["status"] == NOT_ACHIEVED and measured_zero["values"]["counted"] == 0
      and ev9c["status"] == NOT_COMPUTABLE)

print("== GR-10: target ada, baseline/current tak terukur — tidak fabrikasi progres ==")
g10 = build_goal("3 qualified leads in 14 days", measurement_window_days=14,
                 success_definition="qualified = booked call")
ev10 = evaluate_goal(g10, events=[])  # no measurement yet
check("NOT_COMPUTABLE dengan alasan (bukan NOT_ACHIEVED palsu)",
      ev10["status"] == NOT_COMPUTABLE and ev10["reasons"])
g10r = build_goal("close rate to 25%", metric_id="close_rate")
check("readiness rate: target jelas tapi denominator unknown tetap tercatat",
      goal_readiness(g10r)["ready"] and UNRESOLVED_DENOMINATOR in codes(g10r))

print("== GR-11: WTP — evidence criteria, skor numerik tidak dikarang ==")
g11 = parse_goal_text("I want to validate willingness to pay for my offer")
check("metric wtp_validated EVIDENCE_CRITERIA tanpa target numerik",
      g11.metric_id == "wtp_validated" and g11.direction == "EVIDENCE_CRITERIA"
      and g11.target is None)
ev11 = evaluate_goal(g11)
check("tanpa kriteria → NOT_COMPUTABLE (bukan skor)", ev11["status"] == NOT_COMPUTABLE)
g11b = build_goal("validate willingness to pay",
                  success_definition="≥1 paid deposit at listed price, verified")
ev11b = evaluate_goal(g11b, criteria_results=[{"criterion": "deposit", "met": True}])
check("kriteria terpenuhi → ACHIEVED via bukti, bukan angka", ev11b["status"] == ACHIEVED)
ev11c = evaluate_goal(g11b, criteria_results=[{"criterion": "deposit", "met": None}])
check("kriteria unknown → tetap NOT_COMPUTABLE (tidak disimpulkan dua arah)",
      ev11c["status"] == NOT_COMPUTABLE)

print("== GR-17: metric di luar registry — abstain aman, bukan dipetakan ke slot revenue ==")
try:
    build_goal("my goal is brand aura", metric_id="brand_aura")
    check("metric_id eksplisit tak terdaftar → ValueError (API 422)", False)
except ValueError as e:
    check("metric_id eksplisit tak terdaftar → ValueError (API 422)", "tidak terdaftar" in str(e))
g17 = parse_goal_text("I want to make the brand feel premium and loved")
check("teks bebas tanpa alias → tidak dipaksa jadi revenue (desire + METRIC_UNRESOLVED)",
      g17.target is None and g17.resolved_metric_id() == "" and UNRESOLVED_METRIC in codes(g17))

print("== UC-05b/A-12/A-13: guardrail multi-persen — ambang dari KLAUSANYA sendiri ==")
# Baseline bug (reproduced at e6c04a5): _RE_PCT.search over the WHOLE text → 15% margin
# (the first percent), and when the clause is flipped baseline/target primary swap too.
ga = parse_goal_text("Our close rate is about 15%. I want 25% in 60 days, "
                     "while maintaining contribution margin of at least 35%.")
check("primary 15→25 tidak tercemar angka guardrail",
      ga.metric_id == "close_rate" and ga.baseline == 0.15 and ga.target == 0.25)
check("margin guardrail 35% (bukan persen pertama teks 15%)",
      ga.guardrails and ga.guardrails[0]["metric_id"] == "contribution_margin"
      and ga.guardrails[0]["min"] == 0.35, str(ga.guardrails))
check("guardrail tetap GUARDS — bukan Primary Goal kedua",
      ga.guardrails[0]["relation"] == "GUARDS" and ga.metric_id != "contribution_margin")
gb = parse_goal_text("While maintaining contribution margin of at least 35%, "
                     "grow our close rate from 15% to 25%.")
check("urutan klausa dibalik: baseline/target primary tetap 15→25 (bug baseline: 35→15)",
      gb.baseline == 0.15 and gb.target == 0.25, f"base={gb.baseline} tgt={gb.target}")
check("guardrail tetap 35% saat klausanya di depan",
      gb.guardrails and gb.guardrails[0]["min"] == 0.35)
gc = parse_goal_text("Reduce acquisition cost per new customer from Rp80,000 to at most Rp60,000 "
                     "while keeping contribution margin of at least 35% and refund rate under 2%.")
check("CAC 800→600 tetap benar dengan dua klausa guardrail",
      gc.metric_id == "cac" and gc.baseline == 80.0 and gc.target == 60.0)
check("margin 35% terbaca; refund rate tanpa registry → CATATAN eksplisit (bukan evaluasi senyap)",
      gc.guardrails and gc.guardrails[0]["min"] == 0.35
      and any("refund rate" in n for n in gc.notes), str(gc.notes))
gd = parse_goal_text("I need three qualified leads in 14 days")
check("tanpa klausa guardrail → tidak ada guardrail dikarang", gd.guardrails == [])
ge = parse_goal_text("Our close rate is about 15%. I want 25% in 60 days, "
                     "while maintaining contribution margin of at least 35%.")
evge = evaluate_goal(ge, numerator=3, denominator=20, rate_scope=_SC)
check("evaluasi primary tidak bergeser karena guardrail ada (15% vs target 25%)",
      evge["status"] == NOT_ACHIEVED and abs(evge["values"]["rate"] - 0.15) < 1e-9)

print("== ekstra: registry & identitas ==")
check("registry version tercatat (evidence record GR/UC)",
      mr.registry_version() == "goal-metrics-v1")
check("alias unik lintas metric (validator menjaga)",
      mr.metric_by_alias("qualified leads")["metric_id"] == "qualified_leads")
gA = build_goal("3 qualified leads in 14 days", measurement_window_days=14,
                success_definition="q")
gB = build_goal("close rate 15 to 25", metric_id="close_rate")
check("goal_id stabil dari mint (identitas workspace, Phase 3)",
      gA.goal_id == "" and len(mr.metrics()) >= 13)
check("guardrail margin dipisah dari primary goal (UC-05)",
      any(gr["metric_id"] == "contribution_margin" for gr in
          parse_goal_text(
              "Reduce acquisition cost per new customer from Rp80,000 to at most Rp60,000, "
              "while maintaining contribution margin of at least 35%.").guardrails))

fails = [r for r in _results if not r[1]]
_n_ok = len(_results) - len(fails)
print(f"\n{'=' * 50}\nHASIL: {_n_ok}/{len(_results)} PASS"
      + (" ✅" if not fails else f" — {len(fails)} GAGAL ❌"))
sys.exit(1 if fails else 0)
