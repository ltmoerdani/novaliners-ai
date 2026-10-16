"""Goal measurement contract — rate scope, temporal observation, comparability, kind (round 4).

Preserves four core audit defects (Phase 0 round 4, implementation-log):
  P1  rate attainment MUST respect cohort + period (evaluator = trajectory = one contract)
  P2  historical observation does NOT use events only known after that observation
  P3  comparability follows the metric's meaning (version, unit, scope, qualification),
      not just an ID; the measurement kind must match Goal semantics
All clocks are injected (wgoals._now / as_of_ts) - no time.time() in assertions.

Run: .venv/bin/python evals/test_goal_measurement_contract.py
"""
from __future__ import annotations

import datetime as _dt
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # mvp/

from evals._store_isolation import isolate_store  # noqa: E402

isolate_store()  # eval: store redirected to tmp — production store untouched

import store.goals as wgoals  # noqa: E402
import store.workspace as workspace  # noqa: E402
from domains.revenue.schema.goal import build_goal, mint_goal_id  # noqa: E402
from domains.revenue.schema.goal_evaluation import ACHIEVED, NOT_ACHIEVED, NOT_COMPUTABLE  # noqa: E402
from domains.revenue.schema.measurement_contract import (  # noqa: E402
    normalize_period_label,
    rate_measurement_validity,
)
from domains.revenue.stages.trajectory import typed_goal_trajectory  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="goal_mc_"))
wgoals._BASE = _TMP / "workspaces"
workspace._BASE = _TMP / "workspaces"

DAY = 86400
T = 1_750_000_000  # fixed evaluation time
_results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _results.append((name, ok, detail))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" | {detail}" if detail else ""))


_n = [0]


def mk(text: str, **kw) -> tuple[str, str]:
    """New goal in a new user workspace → (user_id, goal_id)."""
    _n[0] += 1
    uid = f"mc_u{_n[0]}"
    g = build_goal(text, goal_id=mint_goal_id(), **kw).model_dump()
    wgoals.upsert_goal(uid, g)
    return uid, g["goal_id"]


def rec(uid: str, gid: str, at: int, **m) -> dict:
    """Record a measurement at RECORD TIME `at` - inject the store clock."""
    wgoals._now = lambda: at
    return wgoals.record_measurement(uid, gid, m)


# ════════════════════════════ PHASE 1 — rate must respect cohort + period ════════════════════════════
print("== P1: rate attainment = kohort + periode terbukti; evaluator & trajectory satu kontrak ==")
RATE = dict(metric_id="close_rate", target=0.25, measurement_window_days=60)
# Rate evidence VALID for a 60-day window: cohort + period with explicit bounds spanning 60 days,
# already ended at evaluation time T. (Label only - e.g. "2026-Q3" - is not period-length evidence: see P1b.)
PERIOD = {"period": "close-window-A", "period_start_ts": T - 62 * DAY, "period_end_ts": T - 2 * DAY}
SC = {"cohort": "inbound-q3", **PERIOD}


def both(uid: str, gid: str) -> tuple[dict, dict]:
    ev = wgoals.evaluate_from_measurements(uid, gid, as_of_ts=T)
    ms, _ = wgoals.split_comparable_measurements(uid, gid)
    tr = typed_goal_trajectory(wgoals.current_goal(uid, gid), ms, as_of_ts=T)
    return ev, tr


# 1. valid, target reached
u, g = mk("close rate to 25%", **RATE)
rec(u, g, T - DAY, kind="rate", numerator=6, denominator=20, **SC)
ev, tr = both(u, g)
check("1. kohort+periode valid, 30% ≥ 25% → ACHIEVED dan trajectory ON_TRACK (satu kontrak)",
      ev["status"] == ACHIEVED and tr["status"] == "ON_TRACK" and ev["values"]["cohort"] == "inbound-q3",
      f"{ev['status']}/{tr['status']}")

# valid, below target → NOT_ACHIEVED (not NOT_COMPUTABLE)
u, g = mk("close rate to 25%", **RATE)
rec(u, g, T - DAY, kind="rate", numerator=3, denominator=20, **SC)
ev, tr = both(u, g)
check("1b. valid tapi 15% < 25% → NOT_ACHIEVED (terukur, bukan tak-terhitung)",
      ev["status"] == NOT_ACHIEVED and ev["values"]["rate"] == 0.15, str(ev["values"]))

# 2-3. cohort / period missing → a figure above target does NOT become ACHIEVED
for label, extra, code in (
    ("2. kohort hilang", dict(PERIOD), "RATE_COHORT_MISSING"),
    ("3. periode hilang", {"cohort": "inbound-q3"}, "RATE_PERIOD_MISSING"),
    ("2/3. kohort dan periode hilang", {}, "RATE_COHORT_MISSING"),
):
    u, g = mk("close rate to 25%", **RATE)
    rec(u, g, T - DAY, kind="rate", numerator=10, denominator=20, **extra)
    ev, tr = both(u, g)
    check(f"{label}: 50% ≥ target tetapi scope tak terbukti → NOT_COMPUTABLE, bukan ACHIEVED",
          ev["status"] == NOT_COMPUTABLE and code in ev.get("rejection_codes", [])
          and tr["status"] == "INSUFFICIENT_DATA" and tr["skipped"] == 1,
          f"{ev['status']}/{tr['status']} {ev.get('rejection_codes')}")
    check(f"{label}: measurement tetap tersimpan (raw evidence tidak dihapus)",
          len(wgoals.measurements(u, g)) == 1
          and ev["rejected_rate_measurements"]["count"] == 1)

# 4. wrong cohort (Goal declares scope)
u, g = mk("close rate to 25%", scope="klinik gigi", **RATE)
rec(u, g, T - DAY, kind="rate", numerator=10, denominator=20, cohort="restoran", **PERIOD)
ev, tr = both(u, g)
check("4. kohort 'restoran' ≠ scope Goal 'klinik gigi' → NOT_COMPUTABLE (RATE_COHORT_MISMATCH)",
      ev["status"] == NOT_COMPUTABLE and "RATE_COHORT_MISMATCH" in ev["rejection_codes"]
      and tr["status"] == "INSUFFICIENT_DATA", str(ev.get("rejection_codes")))
rec(u, g, T - DAY // 2, kind="rate", numerator=10, denominator=20, cohort=" Klinik   Gigi ", **PERIOD)
ev, tr = both(u, g)
check("4b. kohort sama setelah normalisasi spasi/huruf → valid",
      ev["status"] == ACHIEVED and tr["status"] == "ON_TRACK")

# 5. wrong period length: 30 days vs the Goal's 60-day window
u, g = mk("close rate to 25%", **RATE)
rec(u, g, T - DAY, kind="rate", numerator=10, denominator=20, cohort="c", period="p",
    period_start_ts=T - 40 * DAY, period_end_ts=T - 10 * DAY)
ev, tr = both(u, g)
check("5. panjang periode 30 hari ≠ window Goal 60 hari → ditolak (RATE_PERIOD_MISMATCH)",
      ev["status"] == NOT_COMPUTABLE and "RATE_PERIOD_MISMATCH" in ev["rejection_codes"],
      str(ev.get("rejection_codes")))
rec(u, g, T - DAY // 2, kind="rate", numerator=10, denominator=20, cohort="c", period="p2",
    period_start_ts=T - 70 * DAY, period_end_ts=T - 10 * DAY)
ev, tr = both(u, g)
check("5b. periode 60 hari = window → valid", ev["status"] == ACHIEVED, str(ev.get("rejection_codes")))
rec(u, g, T - DAY // 4, kind="rate", numerator=10, denominator=20, cohort="c", period="p3",
    period_start_ts=T - 30 * DAY, period_end_ts=T + 30 * DAY)
ev2 = wgoals.evaluate_from_measurements(u, g, as_of_ts=T)
check("5c. periode berakhir SETELAH waktu evaluasi → ditolak (RATE_PERIOD_INVALID); nilai valid lama tetap",
      ev2["rejected_rate_measurements"]["items"][-1]["codes"][0] == "RATE_PERIOD_INVALID"
      and ev2["status"] == ACHIEVED)

# ── P1b: the period MUST be an exact interval matching the Goal window (label alone is no evidence) ──
print("== P1b: validitas periode rate - batas eksplisit atau label kanonik; selain itu tak terverifikasi ==")
_utc = lambda y, mo, d=1: int(_dt.datetime(y, mo, d, tzinfo=_dt.timezone.utc).timestamp())  # noqa: E731
LATE = _utc(2026, 10, 12)          # evaluation time AFTER 2026-Q3 ended (only for the label test)
G60 = {"metric_id": "close_rate", "unit": "ratio", "measurement_window_days": 60}
M63 = {"kind": "rate", "numerator": 6, "denominator": 20, "cohort": "inbound-q3"}


def vcodes(goal, m, as_of=LATE):
    return rate_measurement_validity(goal, m, as_of_ts=as_of)


check("P1b-0. normalisasi label: 2026-Q3 = 1 Jul..1 Okt UTC (92 hari, akhir eksklusif); 2026-02 = 28 hari",
      normalize_period_label("2026-Q3") == (_utc(2026, 7), _utc(2026, 10))
      and normalize_period_label(" 2026-q3 ") == (_utc(2026, 7), _utc(2026, 10))
      and normalize_period_label("2026-02") == (_utc(2026, 2), _utc(2026, 3))
      and normalize_period_label("2026-12") == (_utc(2026, 12), _utc(2027, 1)))
check("P1b-0b. label yang tak punya definisi tunggal TIDAK ditebak",
      all(normalize_period_label(x) is None for x in
          ("last quarter", "Q3", "2026-Q5", "2026-13", "2026-H2", "Q3 2026", "2026", "", None)))

# mandatory audit case: 15% -> 25% goal in 60 days, 6/20, inbound-q3, label 2026-Q3, no bounds
v = vcodes(G60, {**M63, "period": "2026-Q3"})
check("P1b-1. KASUS AUDIT: 6/20 inbound-q3 '2026-Q3' vs window 60 hari -> TIDAK valid (92 hari != 60): RATE_PERIOD_MISMATCH",
      not v["valid"] and v["rate"] is None and v["codes"] == ["RATE_PERIOD_MISMATCH"]
      and v["interval"]["source"] == "label", str(v["codes"]))
v = vcodes({**G60, "measurement_window_days": 92}, {**M63, "period": "2026-Q3"})
check("P1b-2. label kanonik yang dinormalkan menjadi 92 hari + window Goal 92 hari -> valid, rate terhitung",
      v["valid"] and v["rate"] == 0.3 and v["interval"]["window_checked"] is True)
v = vcodes({**G60, "measurement_window_days": 31}, {**M63, "period": "2026-07"})
check("P1b-3. label bulan 2026-07 (31 hari) vs window 31 -> valid; vs window 30 (toleransi 1 hari) -> valid; vs 28 -> ditolak",
      v["valid"] and vcodes({**G60, "measurement_window_days": 30}, {**M63, "period": "2026-07"})["valid"]
      and vcodes({**G60, "measurement_window_days": 28}, {**M63, "period": "2026-07"})["codes"] == ["RATE_PERIOD_MISMATCH"])
for lbl in ("last quarter", "Q3", "2026-H2", "terakhir"):
    v = vcodes(G60, {**M63, "period": lbl})
    check(f"P1b-4. label tak terverifikasi {lbl!r} tanpa batas -> RATE_PERIOD_UNVERIFIABLE; numerator/denominator valid TIDAK melewati periode",
          not v["valid"] and v["rate"] is None and v["codes"] == ["RATE_PERIOD_UNVERIFIABLE"] and v["interval"] is None,
          str(v["codes"]))
# unknown label but valid explicit bounds -> valid (the bounds decide)
v = vcodes(G60, {**M63, "period": "pekan promo", "period_start_ts": LATE - 70 * DAY, "period_end_ts": LATE - 10 * DAY})
check("P1b-5. label bebas + batas eksplisit 60 hari -> valid (batas, bukan label, yang diverifikasi)",
      v["valid"] and v["interval"]["source"] == "explicit")
# reversed / incomplete bounds
v = vcodes(G60, {**M63, "period": "x", "period_start_ts": LATE - 10 * DAY, "period_end_ts": LATE - 70 * DAY})
check("P1b-6. batas terbalik -> RATE_PERIOD_INVALID", not v["valid"] and v["codes"] == ["RATE_PERIOD_INVALID"], str(v["codes"]))
v = vcodes(G60, {**M63, "period": "x", "period_start_ts": LATE - 70 * DAY})
check("P1b-6b. hanya satu batas -> RATE_PERIOD_INVALID (bukan diam-diam dianggap label)", not v["valid"] and "RATE_PERIOD_INVALID" in v["codes"])
# explicit bounds contradicting the canonical label
v = vcodes({**G60, "measurement_window_days": 92}, {**M63, "period": "2026-Q3",
           "period_start_ts": _utc(2026, 4), "period_end_ts": _utc(2026, 7)})
check("P1b-7. label 2026-Q3 tetapi batas = 2026-Q2 -> RATE_PERIOD_INVALID (label tidak boleh menutupi batas lain)",
      not v["valid"] and "RATE_PERIOD_INVALID" in v["codes"], str(v["codes"]))
v = vcodes({**G60, "measurement_window_days": 92}, {**M63, "period": "2026-Q3",
           "period_start_ts": _utc(2026, 7), "period_end_ts": _utc(2026, 10) - 1})
check("P1b-7b. label 2026-Q3 + batas inklusif (akhir = 30 Sep 23:59:59) -> valid (toleransi 1 hari kalender)", v["valid"], str(v["codes"]))
# canonical label not yet ended at evaluation time = not evidence
v = vcodes({**G60, "measurement_window_days": 92}, {**M63, "period": "2026-Q3"}, as_of=_utc(2026, 8))
check("P1b-8. label 2026-Q3 dievaluasi pada 1 Agt 2026 (periode belum berakhir) -> RATE_PERIOD_INVALID", not v["valid"] and v["codes"] == ["RATE_PERIOD_INVALID"])
# cohort is still enforced alongside the period
v = vcodes({**G60, "scope": "klinik gigi"}, {**M63, "period": "pekan", "period_start_ts": LATE - 70 * DAY, "period_end_ts": LATE - 10 * DAY})
check("P1b-9. periode sah tetapi kohort != scope Goal -> tetap RATE_COHORT_MISMATCH (guard kohort utuh)", v["codes"] == ["RATE_COHORT_MISMATCH"])
v = vcodes(G60, {"kind": "rate", "numerator": 6, "denominator": 20, "period": "last quarter"})
check("P1b-9b. kohort hilang DAN periode tak terverifikasi -> keduanya dilaporkan", set(v["codes"]) == {"RATE_COHORT_MISSING", "RATE_PERIOD_UNVERIFIABLE"})
# Goal without a window: length has no yardstick, but the interval must still be exact
v = vcodes({"metric_id": "close_rate", "unit": "ratio"}, {**M63, "period": "2026-Q3"})
check("P1b-10. Goal tanpa window + label kanonik -> valid, dengan window_checked=False dilaporkan (bukan diam-diam)",
      v["valid"] and v["interval"]["window_checked"] is False)
check("P1b-10b. Goal tanpa window + label tak terverifikasi -> tetap ditolak",
      vcodes({"metric_id": "close_rate", "unit": "ratio"}, {**M63, "period": "last quarter"})["codes"] == ["RATE_PERIOD_UNVERIFIABLE"])

# RC-21 (round 5.1): a zero interval [t, t) contains no duration - rejected, WITH OR WITHOUT a Goal window
ZERO = {**M63, "period": "zero-len", "period_start_ts": LATE - 10 * DAY, "period_end_ts": LATE - 10 * DAY}
v = vcodes({"metric_id": "close_rate", "unit": "ratio"}, ZERO)
check("P1b-13. RC-21: start == end, Goal TANPA window -> RATE_PERIOD_INVALID, rate tidak diterima",
      not v["valid"] and v["rate"] is None and "RATE_PERIOD_INVALID" in v["codes"] and v["interval"] is None, str(v["codes"]))
v = vcodes(G60, ZERO)
check("P1b-13b. RC-21: start == end, Goal DENGAN window 60 hari -> tetap RATE_PERIOD_INVALID (bukan sekadar MISMATCH)",
      not v["valid"] and v["rate"] is None and "RATE_PERIOD_INVALID" in v["codes"], str(v["codes"]))
check("P1b-13c. kontrol: 1 detik lebih panjang dari nol sudah bukan 'kosong' (hanya window yang menilai panjangnya)",
      "RATE_PERIOD_INVALID" not in vcodes({"metric_id": "close_rate", "unit": "ratio"},
                                          {**ZERO, "period_end_ts": ZERO["period_end_ts"] + 1})["codes"])

# full path: a zero interval does not become ACHIEVED / a trajectory point; raw evidence kept; other valid evidence intact
for label, goal_kw in (("tanpa window", dict(metric_id="close_rate", target=0.25)), ("dengan window", RATE)):
    u, g = mk("close rate to 25%", **goal_kw)
    rec(u, g, T - DAY, kind="rate", numerator=6, denominator=20, cohort="inbound-q3",
        period="zero-len", period_start_ts=T - 10 * DAY, period_end_ts=T - 10 * DAY)
    ev, tr = both(u, g)
    check(f"P1b-14. RC-21 jalur penuh ({label}): rate 30% >= 25% pada interval nol -> NOT_COMPUTABLE, bukan ACHIEVED; "
          "trajectory tanpa titik; raw evidence tetap tersimpan",
          ev["status"] == NOT_COMPUTABLE and "RATE_PERIOD_INVALID" in ev["rejection_codes"]
          and tr["status"] == "INSUFFICIENT_DATA" and tr["skipped"] == 1 and tr.get("current") is None
          and len(wgoals.measurements(u, g)) == 1, f"{ev['status']}/{tr['status']}")
    if label == "dengan window":
        rec(u, g, T - DAY // 2, kind="rate", numerator=6, denominator=20, cohort="inbound-q3", **PERIOD)
        ev, tr = both(u, g)
        check("P1b-14b. RC-21: bukti 60 hari sah di samping interval nol -> ACHIEVED dari yang sah saja; nol tetap ditolak",
              ev["status"] == ACHIEVED and ev["rejected_rate_measurements"]["count"] == 1
              and tr["skipped"] == 1 and tr["status"] == "ON_TRACK", f"{ev['status']}/{tr['status']}")

# full path (store -> evaluator + trajectory): an unverified label is never ACHIEVED, raw evidence kept
u, g = mk("close rate to 25%", **RATE)
rec(u, g, T - DAY, kind="rate", numerator=6, denominator=20, cohort="inbound-q3", period="last quarter")
ev, tr = both(u, g)
check("P1b-11. jalur penuh: 30% >= 25% tetapi periode tak terverifikasi -> NOT_COMPUTABLE (bukan ACHIEVED); trajectory INSUFFICIENT_DATA",
      ev["status"] == NOT_COMPUTABLE and "RATE_PERIOD_UNVERIFIABLE" in ev["rejection_codes"]
      and tr["status"] == "INSUFFICIENT_DATA" and tr["skipped"] == 1 and len(wgoals.measurements(u, g)) == 1,
      f"{ev['status']}/{tr['status']}")
# control: valid 60-day bounds -> ACHIEVED, then something later unverified does not displace it
rec(u, g, T - DAY // 2, kind="rate", numerator=6, denominator=20, cohort="inbound-q3", **PERIOD)
ev, tr = both(u, g)
check("P1b-12. kontrol: bukti 60 hari sah ditambahkan -> ACHIEVED; bukti tak terverifikasi tetap dicatat sebagai ditolak",
      ev["status"] == ACHIEVED and tr["status"] == "ON_TRACK" and ev["rejected_rate_measurements"]["count"] == 1)


# 6. numerator > denominator (same cohort)
u, g = mk("close rate to 25%", **RATE)
rec(u, g, T - DAY, kind="rate", numerator=9, denominator=3, **SC)
ev, tr = both(u, g)
check("6. numerator 9 > denominator 3 pada metric rasio → ditolak, tidak ACHIEVED (rate 300%)",
      ev["status"] == NOT_COMPUTABLE and "RATE_NUMERATOR_EXCEEDS_DENOMINATOR" in ev["rejection_codes"],
      str(ev.get("rejection_codes")))

# 7. zero denominator
u, g = mk("close rate to 25%", **RATE)
rec(u, g, T - DAY, kind="rate", numerator=0, denominator=0, **SC)
ev, tr = both(u, g)
check("7. denominator 0 → NOT_COMPUTABLE (bukan 0% dan bukan gagal)",
      ev["status"] == NOT_COMPUTABLE and "RATE_DENOMINATOR_ZERO" in ev["rejection_codes"]
      and tr["status"] == "INSUFFICIENT_DATA")

# 8. incomplete measurement (injected straight into the store - the API rejects it at the boundary)
u, g = mk("close rate to 25%", **RATE)
rec(u, g, T - DAY, kind="rate", numerator=5, **SC)
ev, tr = both(u, g)
check("8. denominator hilang → NOT_COMPUTABLE (RATE_INCOMPLETE), bukan 0",
      ev["status"] == NOT_COMPUTABLE and "RATE_INCOMPLETE" in ev["rejection_codes"])

# 13. trend over comparable valid pairs
u, g = mk("close rate to 40%", metric_id="close_rate", target=0.4, measurement_window_days=60)
rec(u, g, T - 20 * DAY, kind="rate", numerator=4, denominator=20, **SC)
rec(u, g, T - 10 * DAY, kind="rate", numerator=6, denominator=20, **SC)
ev, tr = both(u, g)
check("13. dua rate sebanding 20% → 30% di bawah target 40% → IMPROVING; attainment NOT_ACHIEVED",
      tr["status"] == "IMPROVING" and tr["comparable"] and tr["prev"] == 0.2
      and ev["status"] == NOT_ACHIEVED and ev["values"]["rate"] == 0.3)
rec(u, g, T - 5 * DAY, kind="rate", numerator=2, denominator=10, cohort="walk-in", **PERIOD)
ev, tr = both(u, g)
check("14. pasangan terakhir kohort berbeda: status current faktual (NOT_ACHIEVED 20%), arah TIDAK diklaim",
      ev["status"] == NOT_ACHIEVED and ev["values"]["rate"] == 0.2
      and tr["status"] == "INSUFFICIENT_DATA" and tr["comparable"] is False
      and "sebanding" in tr["reason"], f"{ev['status']} {tr['status']}")

# evaluator is never ACHIEVED while trajectory refuses the same numbers
u, g = mk("close rate to 25%", **RATE)
rec(u, g, T - 3 * DAY, kind="rate", numerator=3, denominator=5)           # no scope: 60%
rec(u, g, T - 2 * DAY, kind="rate", numerator=2, denominator=20, **SC)    # scope valid: 10%
ev, tr = both(u, g)
check("konsistensi: rate tanpa scope (60%) diabaikan; dipakai rate valid terkini (10% → NOT_ACHIEVED)",
      ev["status"] == NOT_ACHIEVED and ev["values"]["rate"] == 0.1
      and tr["current"] == 0.1 and tr["skipped"] == 1)

# ════════════════════════ PHASE 2 — historical observation without temporal leakage ════════════════════════
print("== P2: event time ≠ record time ≠ observation ≠ as_of; bukti baru tak menulis ulang masa lalu ==")
GL = {"metric_id": "qualified_leads", "direction": "COUNT_IN_WINDOW", "target": 3.0,
      "measurement_window_days": 14}
GL5 = {**GL, "target": 5.0}


def ev(event_ts, recorded, q=True, **kw):
    return {"kind": "event", "event_ts": event_ts, "qualified": q, "ts": recorded, **kw}


# 1. three events on days 28..30, 14-day window, recorded today → current 0
ms = [ev(T - 30 * DAY, T), ev(T - 29 * DAY, T), ev(T - 28 * DAY, T)]
tr = typed_goal_trajectory(GL, ms, as_of_ts=T)
check("1. tiga event 28-30 hari lalu (window 14h): current counted=0 → OFF_TRACK, bukan ON_TRACK",
      tr["status"] == "OFF_TRACK" and tr["counted"] == 0 and tr["n_observations"] == 1, str(tr["status"]))
u, g = mk("3 qualified leads in 14 days", success_definition="q=call", measurement_window_days=14)
for m in ms:
    rec(u, g, T, **m | {"ts": None})
evc = wgoals.evaluate_from_measurements(u, g, as_of_ts=T)
check("1b. attainment dari store konsisten: counted=0 → NOT_ACHIEVED (satu implementasi hitungan)",
      evc["status"] == NOT_ACHIEVED and evc["values"]["counted"] == 0
      and evc["values"]["outside_window"] == 3, str(evc["values"]))

# 2-4. inside/outside window, exactly at cutoff, future
tr = typed_goal_trajectory(GL, [ev(T - 3 * DAY, T), ev(T - 20 * DAY, T)], as_of_ts=T)
check("2. event dalam window dihitung, event di luar window tidak", tr["counted"] == 1)
tr_in = typed_goal_trajectory(GL, [ev(T - 14 * DAY, T)], as_of_ts=T)
tr_out = typed_goal_trajectory(GL, [ev(T - 14 * DAY - 1, T)], as_of_ts=T)
check("3. tepat di cutoff (as_of − window) MASUK (inklusif); 1 detik lebih awal KELUAR",
      tr_in["counted"] == 1 and tr_out["counted"] == 0)
tr = typed_goal_trajectory(GL, [ev(T + DAY, T), ev(T - DAY, T)], as_of_ts=T)
check("4. event bertimestamp masa depan tidak dihitung", tr["counted"] == 1)

# 5/6. old events newly reported; historical observation before the report does NOT change
ms = [ev(T - 4 * DAY, T - 4 * DAY),            # old observation: only one event known then
      ev(T - 6 * DAY, T), ev(T - 7 * DAY, T)]  # backfill: happened earlier, reported today
tr = typed_goal_trajectory(GL5, ms, as_of_ts=T)
check("5. event lama yang baru dilaporkan masuk hitungan CURRENT (counted=3)", tr["counted"] == 3)
check("6. observasi historis (T−4h) hanya memakai yang saat itu diketahui → prev=1 (bukan 3)",
      tr["prev"] == 1 and tr["prev_observation_ts"] == T - 4 * DAY, f"prev={tr['prev']}")
check("6b. kenaikan 1→3 murni backfill → arah TIDAK disimpulkan (bukan IMPROVING), late_reported=2",
      tr["status"] == "INSUFFICIENT_DATA" and tr["late_reported"] == 2
      and "baru dilaporkan" in tr["reason"], tr["status"])
from domains.revenue.schema.measurement_contract import events_known_at  # noqa: E402

check("6c. events_known_at(T−4h): hanya 1 event; event_ts boleh lebih awal tetapi belum tercatat",
      len(events_known_at(ms, T - 4 * DAY, historical=True)) == 1
      and len(events_known_at(ms, T)) == 3)

# 7. next observation after the event is reported - new occurrence → IMPROVING is valid
ms2 = ms + [ev(T + DAY - 3600, T + DAY)]
tr = typed_goal_trajectory(GL5, ms2, as_of_ts=T + DAY)
check("7. observasi berikutnya: kejadian BARU sesudah observasi sebelumnya (3→4) → IMPROVING sah",
      tr["status"] == "IMPROVING" and tr["prev"] == 3 and tr["counted"] == 4 and tr["late_reported"] == 0,
      f"{tr['status']} prev={tr.get('prev')} late={tr.get('late_reported')}")

# 8. qualified / unqualified / unknown
tr = typed_goal_trajectory(
    GL, [ev(T - DAY, T, True), ev(T - DAY, T, False), ev(T - DAY, T, None)], as_of_ts=T)
check("8. hanya qualified=True dihitung; False diabaikan; None = unknown (tidak auto-qualified, dilaporkan)",
      tr["counted"] == 1 and tr["unknown_qualification"] == 1)
tr = typed_goal_trajectory(GL, [{"kind": "event", "qualified": True, "ts": T}], as_of_ts=T)
check("8b. event TANPA event_ts: waktu pencatatan bukan waktu kejadian → unknown_timestamp, tidak dihitung",
      tr["counted"] == 0 and tr["unknown_timestamp"] == 1)

# 9. other kinds do not create an observation point
ms9 = [ev(T - DAY, T - 5 * DAY), {"kind": "value", "value": 9, "ts": T - 3 * DAY},
       {"kind": "rate", "numerator": 1, "denominator": 2, "ts": T - 2 * DAY}, ev(T - 2 * DAY, T)]
tr = typed_goal_trajectory(GL5, ms9, as_of_ts=T)
check("9. measurement kind lain tidak menjadi titik observasi (n_observations=2; prev diukur di T−5h)",
      tr["n_observations"] == 2 and tr["prev_observation_ts"] == T - 5 * DAY, str(tr["n_observations"]))

# 10/11. one and two comparable observation points
tr = typed_goal_trajectory(GL5, [ev(T - 3 * DAY, T)], as_of_ts=T)
check("10. satu observasi di bawah target → OFF_TRACK faktual + arah belum bisa dinilai",
      tr["status"] == "OFF_TRACK" and "satu titik observasi" in tr["reason"])
tr = typed_goal_trajectory(GL5, [ev(T - 9 * DAY, T - 9 * DAY), ev(T - 3 * DAY, T)], as_of_ts=T)
check("11. dua observasi comparable 1→2, kejadian baru → IMPROVING",
      tr["status"] == "IMPROVING" and tr["prev"] == 1 and tr["counted"] == 2)

# 12. sliding window declining 3 → 0
ms12 = [ev(T - 30 * DAY, T - 20 * DAY), ev(T - 29 * DAY, T - 20 * DAY), ev(T - 28 * DAY, T - 20 * DAY),
        ev(T - 2 * DAY, T, False)]
tr = typed_goal_trajectory(GL, ms12, as_of_ts=T)
check("12. window bergeser: count 3 (saat itu) → 0 (kini) → DRIFTING",
      tr["status"] == "DRIFTING" and tr["prev"] == 3 and tr["counted"] == 0)

# 13. raw events grow, qualified does not
tr = typed_goal_trajectory(GL5, [ev(T - 5 * DAY, T - 5 * DAY), ev(T - DAY, T, False), ev(T - DAY, T, False)],
                           as_of_ts=T)
check("13. event mentah 1→3 tetapi qualified tetap 1 → bukan IMPROVING (datar)",
      tr["status"] == "INSUFFICIENT_DATA" and tr["counted"] == 1 and tr["prev"] == 1)

# 14. event identity: duplicates do not double; a qualification correction applies forward only
dup = [ev(T - 2 * DAY, T - 2 * DAY, True, event_id="L1"), ev(T - 2 * DAY, T - DAY, True, event_id="L1")]
tr = typed_goal_trajectory(GL5, dup, as_of_ts=T)
check("14. event_id sama dicatat dua kali → satu event (tidak dobel)", tr["counted"] == 1)
corr = [ev(T - 5 * DAY, T - 5 * DAY, None, event_id="L2"), ev(T - 5 * DAY, T, True, event_id="L2"),
        ev(T - 4 * DAY, T - 4 * DAY, False)]
tr = typed_goal_trajectory(GL5, corr, as_of_ts=T)
check("14b. koreksi kualifikasi unknown→True tercatat di T: observasi T−4h tetap 0, current 1; "
      "kenaikan = bukti terlambat → arah tak disimpulkan",
      tr["prev"] == 0 and tr["counted"] == 1 and tr["late_reported"] == 1
      and tr["status"] == "INSUFFICIENT_DATA", f"{tr['status']} prev={tr['prev']} late={tr['late_reported']}")

# 15. window revision: raw history intact, current re-evaluated under the new definition
u, g = mk("3 qualified leads in 14 days", success_definition="q=call", measurement_window_days=14)
for k in (1, 2, 3):
    rec(u, g, T - DAY, kind="event", event_ts=T - (16 + k) * DAY, qualified=True)
before = wgoals.evaluate_from_measurements(u, g, as_of_ts=T)
cur = wgoals.current_goal(u, g)
wgoals.upsert_goal(u, {**cur, "measurement_window_days": 30})
after = wgoals.evaluate_from_measurements(u, g, as_of_ts=T)
check("15. revisi window 14→30: raw event utuh (3 tersimpan), current dihitung ulang (0 → 3 = ACHIEVED)",
      before["values"]["counted"] == 0 and after["values"]["counted"] == 3 and after["status"] == ACHIEVED
      and len(wgoals.measurements(u, g)) == 3
      and all(m["goal_version"] == 1 for m in wgoals.measurements(u, g)))
hist = wgoals.goal_at_version(u, g, 1)
ms_all = wgoals.measurements(u, g)
tr_hist = typed_goal_trajectory(hist, ms_all, as_of_ts=T)
check("15b. evaluasi historis v1 (window 14) tetap counted=0 - definisi lama utuh",
      tr_hist["counted"] == 0 and tr_hist["window_days"] == 14)

# ════════════════ PHASE 3 — versioned comparability + measurement kind ↔ Goal semantics ════════════════
print("== P3: comparability mengikuti makna bukti (versi/unit/scope/kualifikasi); target/window tidak ==")
import json  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

import app.main as app_main  # noqa: E402
from domains.revenue.schema.measurement_contract import comparability, kind_check  # noqa: E402

client = TestClient(app_main.app)
LEADS = dict(success_definition="qualified = booked discovery call", measurement_window_days=14)


def leads_with_events() -> tuple[str, str]:
    u, g = mk("3 qualified leads in 14 days", **LEADS)
    rec(u, g, T - DAY, kind="event", event_ts=T - 2 * DAY, qualified=True)
    rec(u, g, T - DAY, kind="event", event_ts=T - 3 * DAY, qualified=True)
    return u, g


def revise(u: str, g: str, at: int, **chg) -> dict:
    wgoals._now = lambda: at
    return wgoals.upsert_goal(u, {**wgoals.current_goal(u, g), **chg})


def excl(u: str, g: str) -> dict:
    return wgoals.evaluate_from_measurements(u, g, as_of_ts=T).get("excluded_incomparable") or {}


# 1-5. a material dimension changed → old evidence excluded with a per-dimension reason
for label, chg, dim in (
    ("1. unit berubah", {"unit": "inquiries"}, "unit"),
    ("2. scope (populasi) berubah", {"scope": "referral-only"}, "scope"),
    ("3. metric_version berubah (registry naik versi)", {"metric_version": 2}, "metric_version"),
    ("4. definisi kualifikasi berubah", {"success_definition": "qualified = signed NDA"},
     "success_definition"),
):
    u, g = leads_with_events()
    base_ev = wgoals.evaluate_from_measurements(u, g, as_of_ts=T)
    revise(u, g, T - DAY // 2, **chg)
    ex = excl(u, g)
    now_ev = wgoals.evaluate_from_measurements(u, g, as_of_ts=T)
    check(f"{label}: 2 bukti lama excluded, dimensi '{dim}' tercatat; current NOT_COMPUTABLE",
          ex.get("count") == 2 and ex["by_dimension"].get(dim) == 2
          and any(d["dimension"] == dim for d in ex["items"][0]["differences"])
          and now_ev["status"] == NOT_COMPUTABLE and base_ev["values"]["counted"] == 2,
          str(ex.get("by_dimension")))
    check(f"{label}: raw evidence tetap tersimpan utuh (2 baris, versi 1) + evaluasi historis v1 tetap",
          len(wgoals.measurements(u, g)) == 2
          and wgoals.evaluate_from_measurements(u, g, version=1)["values"]["counted"] == 2)

# 5. numerator/denominator definition (rate success_definition) changed
u, g = mk("close rate to 25%", **RATE, success_definition="won / opportunities created")
rec(u, g, T - DAY, kind="rate", numerator=6, denominator=20, **SC)
revise(u, g, T - DAY // 2, success_definition="won / qualified opportunities only")
ex = excl(u, g)
ev_r = wgoals.evaluate_from_measurements(u, g, as_of_ts=T)
check("5. definisi numerator/denominator rate berubah → rate lama excluded, tidak ACHIEVED",
      ex.get("count") == 1 and ev_r["status"] == NOT_COMPUTABLE, str(ex.get("by_dimension")))

# 6. target changed → evidence stays comparable, current re-evaluated
u, g = leads_with_events()
revise(u, g, T - DAY // 2, target=2.0)
ev6 = wgoals.evaluate_from_measurements(u, g, as_of_ts=T)
check("6. target 3→2 TANPA mengubah makna bukti: tidak excluded; current ACHIEVED (2 ≥ 2)",
      not ev6.get("excluded_incomparable") and ev6["status"] == ACHIEVED and ev6["values"]["target"] == 2.0)
ev6h = wgoals.evaluate_from_measurements(u, g, version=1)
check("6b. evaluasi HISTORIS v1 tetap memakai target 3 (NOT_ACHIEVED) - target current tak menulis ulang",
      ev6h["status"] == NOT_ACHIEVED and ev6h["values"]["target"] == 3.0
      and ev6h["evaluation_basis"]["mode"] == "historical"
      and ev6h["evaluation_basis"]["version_ended_ts"] == T - DAY // 2
      and ev6h["evaluation_basis"]["as_of_ts"] == T - DAY // 2, str(ev6h["evaluation_basis"]))
check("6c. current vs historis dapat dibedakan lewat evaluation_basis",
      ev6["evaluation_basis"]["mode"] == "current" and ev6["evaluation_basis"]["goal_version"] == 2)

# 7. window changed with adequate raw history → comparable
u, g = leads_with_events()
revise(u, g, T - DAY // 2, measurement_window_days=30)
check("7. window 14→30: tidak excluded (raw event dihitung ulang)", not excl(u, g))

# 17. re-upserting a legacy record (metric_version None ≡ v1) creates no spurious revision
u, g = leads_with_events()
cur = wgoals.current_goal(u, g)
check("17. upsert ulang dengan metric_version None (legacy) vs 1 → TIDAK ada revisi palsu",
      wgoals.upsert_goal(u, {**cur, "metric_version": None}) == {})

# 8-12. kind measurement ↔ semantics Goal (API boundary + store)
print("== P3: kind measurement harus cocok dengan semantics Goal (boundary menolak, tidak menelan) ==")


def post(u: str, g: str, body: dict):
    return client.post(f"/workspace/{u}/goals/{g}/measurements", json=body)


u, g = leads_with_events()
before = len(wgoals.measurements(u, g))
cases = (
    ("8. rate → Goal COUNT", {"kind": "rate", "numerator": 1, "denominator": 2}),
    ("9. value → Goal COUNT", {"kind": "value", "value": 9}),
    ("9b. criteria → Goal COUNT", {"kind": "criteria", "criterion": "x", "met": True}),
)
for label, body in cases:
    r = post(u, g, body)
    d = r.json().get("detail") or {}
    check(f"{label}: 422 {d.get('code')} dengan kind yang sah disebut",
          r.status_code == 422 and d.get("code") == "MEASUREMENT_KIND_MISMATCH"
          and d.get("expected_kinds") == ["event"] and d.get("semantics") == "COUNT_IN_WINDOW", str(d))
check("8-9. penolakan tidak menulis apa pun (log utuh) dan tidak menggerakkan evaluasi",
      len(wgoals.measurements(u, g)) == before)

u2, g2 = mk("close rate to 25%", **RATE)
r = post(u2, g2, {"kind": "event", "event_ts": T, "qualified": True})
check("10. event → Goal RATE: 422", r.status_code == 422)
u3, g3 = mk("validate willingness to pay")
kc = kind_check(wgoals.current_goal(u3, g3), "value")
r = post(u3, g3, {"kind": "value", "value": 3})
check("11. value → Goal EVIDENCE_CRITERIA: 422; criteria diterima",
      r.status_code == 422 and not kc["ok"] and kc["expected"] == ["criteria"]
      and post(u3, g3, {"kind": "criteria", "criterion": "deposit", "met": True}).status_code == 200)
u4, g4 = mk("I want to reach 40 million rupiah a month", metric_id="revenue_monthly", target=40)
check("12. Goal revenue (INCREASE_TO_THRESHOLD): value diterima (kompatibilitas), event ditolak",
      post(u4, g4, {"kind": "value", "value": 12}).status_code == 200
      and post(u4, g4, {"kind": "event", "event_ts": T, "qualified": True}).status_code == 422)
r = wgoals.record_measurement(u, g, {"kind": "rate", "numerator": 1, "denominator": 2})
check("store.record_measurement juga menolak (defense in depth, bukan hanya endpoint)",
      r.get("rejected") is True and r["code"] == "MEASUREMENT_KIND_MISMATCH")
u5, g5 = mk("something vague I want")
check("Goal tanpa semantics terdaftar → tak ada bentuk bukti sah (GOAL_SEMANTICS_UNKNOWN)",
      post(u5, g5, {"kind": "value", "value": 1}).status_code == 422
      and kind_check(wgoals.current_goal(u5, g5), "value")["code"] == "GOAL_SEMANTICS_UNKNOWN")

# 13/16. legacy records: no metric version / no snapshot / wrong kind from the pre-validation era
print("== P3: data lama tetap terbaca dengan aturan eksplisit ==")
check("13. record tanpa metric_version dibaca sebagai v1: comparable dengan Goal v1",
      comparability({"metric_id": "qualified_leads", "direction": "COUNT_IN_WINDOW"},
                    {"metric_id": "qualified_leads", "metric_version": 1,
                     "direction": "COUNT_IN_WINDOW"})["comparable"])
cmpv = comparability({"metric_id": "qualified_leads", "direction": "COUNT_IN_WINDOW"},
                     {"metric_id": "qualified_leads", "metric_version": 2, "direction": "COUNT_IN_WINDOW"})
check("13b. record legacy (v1 diasumsikan) vs registry v2 → TIDAK terbukti mengikuti definisi baru: excluded",
      not cmpv["comparable"] and cmpv["differences"][0]["dimension"] == "metric_version")
check("13c. tanpa snapshot Goal sama sekali → comparable dengan basis 'no_snapshot' (dilaporkan)",
      comparability(None, {"metric_id": "x"})
      == {"comparable": True, "differences": [], "basis": "no_snapshot"})
check("13d. snapshot lama tanpa field unit/scope → dimensi itu tidak dianggap 'berbeda'",
      comparability({"metric_id": "qualified_leads"},
                    {"metric_id": "qualified_leads", "unit": "leads", "scope": "x"})["comparable"])

u, g = leads_with_events()
legacy_row = {"type": "GOAL_MEASURED", "ts": T - DAY, "goal_id": g, "version": 1,
              "goal": wgoals.current_goal(u, g),
              "payload": {"kind": "rate", "numerator": 9, "denominator": 3}}
with (wgoals._user_dir(u) / "goals.jsonl").open("a", encoding="utf-8") as fh:
    fh.write(json.dumps(legacy_row) + "\n")
evl = wgoals.evaluate_from_measurements(u, g, as_of_ts=T)
check("16. baris rate keliru dari era pra-validasi (di Goal COUNT): excluded kind, 2 event sah tetap dipakai",
      evl["values"]["counted"] == 2 and evl["excluded_incomparable"]["count"] == 1
      and evl["excluded_incomparable"]["by_dimension"].get("kind") == 1
      and len(wgoals.measurements(u, g)) == 3)
traj = client.get(f"/workspace/{u}/goals/{g}/trajectory").json()
check("16b. endpoint trajectory current melaporkan excluded + basis; baris keliru tak menggerakkan seri",
      traj["excluded_incomparable"]["count"] == 1 and traj["evaluation_basis"]["mode"] == "current"
      and traj["goal_trajectory"]["counted"] <= 2)
hist = client.get(f"/workspace/{u}/goals/{g}/trajectory", params={"version": 1}).json()
check("15/16c. endpoint historis v1 membawa evaluasi + as_of; baris kind keliru tak ikut",
      hist["historical"]["n_measurements"] == 2 and "evaluation" in hist["historical"])

print()
passed = sum(1 for _, ok, _ in _results if ok)
print(f"HASIL: {passed}/{len(_results)} PASS" + (" ✅" if passed == len(_results) else " — GAGAL ❌"))
sys.exit(0 if passed == len(_results) else 1)
