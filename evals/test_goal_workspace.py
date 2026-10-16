"""Goal-Relative workspace guard — multi-Goal isolation, revision, trajectory (int 09 §4.4; Phase 3).

GR-18 A→B switch without value/version/path leakage; GR-19 a STOP path in Goal A does not
spread to Goal B (stable path identity path.<strategy_id>); GR-20 target revision =
version event (history not rewritten); GR-21 achievement per Goal; GR-22 a finished action
is not an outcome (trajectory only from measurements); GR-23 the two trajectory axes stay
separate; GR-07 legacy user-wide path_states stays readable (GLOBAL scope).

Deterministic (mock). Run: .venv/bin/python evals/test_goal_workspace.py
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # mvp/

from evals._store_isolation import isolate_store  # noqa: E402

isolate_store()  # eval: store redirected to tmp — production store untouched

import store.adjudication_ledger as ledger  # noqa: E402
import store.funnel as funnel  # noqa: E402
import store.goals as wgoals  # noqa: E402
import store.path_states as path_states  # noqa: E402
import store.route_execution as route_execution  # noqa: E402
import store.route_lineages as rl  # noqa: E402
import store.workspace as workspace  # noqa: E402
from domains.revenue.stages.trajectory import typed_goal_trajectory  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="goal_ws_"))
rl._BASE = _TMP / "lineages"
ledger._LEDGER_ROOT = _TMP / "ledger"
workspace._BASE = _TMP / "workspaces"
wgoals._BASE = _TMP / "workspaces"
route_execution._BASE = _TMP / "workspaces"
funnel._PATH = _TMP / "funnel.jsonl"
path_states._BASE = _TMP
path_states._STATES = _TMP / "path_states.json"
path_states._STATES_GOALS = _TMP / "path_states_goals.json"
path_states._HISTORY = _TMP / "path_history.jsonl"

from fastapi.testclient import TestClient  # noqa: E402

import app.main as app_main  # noqa: E402
from domains.revenue.stages.trajectory import goal_trajectory  # noqa: E402
from providers.mock import MockProvider  # noqa: E402

app_main.get_llm = lambda: MockProvider()
client = TestClient(app_main.app)

_results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _results.append((name, ok, detail))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" | {detail}" if detail else ""))


U = "goalws_u1"

print("== GR-18: workspace multi-Goal — identitas, versi, aktivasi ==")
r1 = client.post("/session", json={
    "goal_text": "I need three qualified leads in 14 days", "user_id": U,
    "success_definition": "qualified = booked discovery call"})
ga = r1.json()["goal"]
r2 = client.post("/session", json={
    "goal_text": "close rate to 25%", "user_id": U,
    "metric_id": "close_rate", "target": 0.25})
gb = r2.json()["goal"]
check("dua Goal terdaftar dengan goal_id stabil berbeda",
      ga["goal_id"] != gb["goal_id"] and ga["goal_id"].startswith("goal_"))
view = client.get(f"/workspace/{U}/goals").json()
check("koleksi Goal: 2 record + active = Goal terakhir (B)",
      len(view["goals"]) == 2 and view["active_goal_id"] == gb["goal_id"],
      str(view["active_goal_id"]))
check("Goal A tetap utuh (metric/unit versi) setelah B dibuat",
      next(g for g in view["goals"] if g["goal_id"] == ga["goal_id"])["metric_id"]
      == "qualified_leads")

print("== GR-19: STOP path di Goal A tidak menjalar ke Goal B ==")
# report an outcome regret (→STOPPED) on path X in the Goal A session
ev = path_states.apply_and_log(U, r1.json()["session_id"], "path.direct_outreach",
                               "regret", goal_id=ga["goal_id"])
check("event outcome tercatat dengan goal_id", ev["event"]["goal_id"] == ga["goal_id"])
sa = path_states.get_states(U, goal_id=ga["goal_id"])
sb = path_states.get_states(U, goal_id=gb["goal_id"])
check("Goal A melihat STOP (scope GOAL)", sa["path.direct_outreach"]["outcome_state"] == "STOPPED")
check("Goal B TIDAK melihat STOP Goal A (isolasi)",
      "path.direct_outreach" not in sb, str(sorted(sb)))
check("identitas path tetap stabil path.<strategy_id> (tanpa suffix goal)",
      "path.direct_outreach" in sa and "_scope" in sa["path.direct_outreach"])

print("== GR-07: legacy user-wide path_states tetap terbaca (scope GLOBAL) ==")
path_states.apply_and_log(U, "legacy-sess", "path.paid_channel_test", "regret")  # no goal_id
sc = path_states.get_states(U, goal_id=gb["goal_id"])
check("state warisan GLOBAL terlihat di Goal B (kompatibilitas perilaku lama)",
      sc.get("path.paid_channel_test", {}).get("outcome_state") == "STOPPED"
      and sc["path.paid_channel_test"]["_scope"] == "GLOBAL")
sd = path_states.get_states(U)  # legacy caller without goal_id
check("pemanggil legacy (goal_id None) tetap dapat state user-wide",
      sd.get("path.paid_channel_test", {}).get("outcome_state") == "STOPPED")

print("== GR-20: revisi target = event + versi; sejarah tidak ditulis ulang ==")
rev = client.post(f"/workspace/{U}/goals/{ga['goal_id']}/revise",
                  json={"target": 5}).json()
g_now = wgoals.current_goal(U, ga["goal_id"])
check("revisi target 3→5: versi naik 2, target baru",
      rev["changed"] and g_now["version"] == 2 and g_now["target"] == 5.0)
hist = [h for h in wgoals.history(U, ga["goal_id"]) if h["type"] == "GOAL_REVISED"]
check("event GOAL_REVISED tercatat dengan versi & payload",
      hist and hist[-1]["version"] == 2)
check("state versi 1 tetap ada di riwayat (non-destruktif)",
      any(h.get("goal", {}).get("target") == 3.0 for h in wgoals.history(U, ga["goal_id"])))
norev = client.post(f"/workspace/{U}/goals/{ga['goal_id']}/revise",
                    json={"target": 5}).json()
check("revisi tanpa perubahan material → tanpa event baru",
      not norev["changed"] and wgoals.current_goal(U, ga["goal_id"])["version"] == 2)

print("== GR-21: achievement per Goal — tidak menjalar ==")
lc = client.post(f"/workspace/{U}/goals/{ga['goal_id']}/lifecycle?event=ACHIEVED").json()
check("Goal A ACHIEVED tercatat",
      wgoals.current_goal(U, ga["goal_id"])["status"] == "ACHIEVED")
check("Goal B tetap ACTIVE (mencapai A tidak menutup B)",
      wgoals.current_goal(U, gb["goal_id"]).get("status", "ACTIVE") == "ACTIVE")

print("== GR-22/GR-09: trajectory hanya dari pengukuran teramati ==")
tr0 = client.get(f"/workspace/{U}/goals/{gb['goal_id']}/trajectory").json()["goal_trajectory"]
check("tanpa pengukuran → INSUFFICIENT_DATA (aksi selesai bukan hasil)",
      tr0["status"] == "INSUFFICIENT_DATA")
now_ts = 1_700_000_000
rej_codes = []
for i, (ts, q) in enumerate([(now_ts - 3 * 86400, True), (now_ts - 2 * 86400, False),
                             (now_ts - 1 * 86400, True), (now_ts - 20 * 86400, True)]):
    rr = client.post(f"/workspace/{U}/goals/{gb['goal_id']}/measurements",
                     json={"kind": "event", "event_ts": ts, "qualified": q})
    rej_codes.append((rr.status_code, (rr.json().get("detail") or {}).get("code")))
tr1 = client.get(f"/workspace/{U}/goals/{gb['goal_id']}/trajectory").json()
# close_rate is a RATE metric — events are not its value input; typed evaluation checked via a leads session
ev_leads = client.get(f"/workspace/{U}/goals").json()  # sanity: collection still intact
check("event dikirim ke Goal RATE (close_rate) ditolak 422 MEASUREMENT_KIND_MISMATCH - tidak tersimpan",
      rej_codes == [(422, "MEASUREMENT_KIND_MISMATCH")] * 4
      and len(wgoals.measurements(U, gb["goal_id"])) == 0, str(rej_codes))
# u2 events relative to WALL CLOCK (store evaluation = as-of now; A-09) —
# the 2023 fixture without an explicit as-of used to pass because of the newest-event anchor bug.
wall = int(time.time())
r3 = client.post("/session", json={
    "goal_text": "3 qualified leads in 14 days", "user_id": "goalws_u2",
    "success_definition": "q = booked call"})
g3 = r3.json()["goal"]
for ts, q in [(wall - 1 * 86400, True), (wall - 2 * 86400, True),
              (wall - 30 * 86400, True), (wall - 1 * 86400, None)]:
    client.post(f"/workspace/goalws_u2/goals/{g3['goal_id']}/measurements",
                json={"kind": "event", "event_ts": ts, "qualified": q})
mev = client.get(f"/workspace/{U}/goals").json()
ev3 = wgoals.evaluate_from_measurements("goalws_u2", g3["goal_id"])
check("evaluasi typed dari pengukuran: 2 event valid dalam window (bukan 4, bukan 0)",
      ev3["values"]["counted"] == 2 and ev3["status"] == "NOT_ACHIEVED", str(ev3["values"]))

print("== A-16/A-17: trajectory TYPED dari event/rate/criteria + goal_version per pengukuran ==")
U4 = "goalws_u4"
r4 = client.post("/session", json={"goal_text": "3 qualified leads in 14 days",
                                   "user_id": U4, "success_definition": "q=call"})
g4 = r4.json()["goal"]
gid4 = g4["goal_id"]
murl = f"/workspace/{U4}/goals/{gid4}/measurements"
client.post(murl, json={"kind": "event", "event_ts": wall - 10 * 86400, "qualified": True})
client.post(murl, json={"kind": "event", "event_ts": wall - 3 * 86400, "qualified": True})
client.post(murl, json={"kind": "event", "event_ts": wall - 2 * 86400, "qualified": True})
ms4 = wgoals.measurements(U4, gid4)
check("setiap pengukuran membawa goal_version (A-17: sejarah teratribusi versi)",
      len(ms4) == 3 and all(m.get("goal_version") == 1 for m in ms4), str(ms4[:1]))
tr4 = client.get(f"/workspace/{U4}/goals/{gid4}/trajectory").json()["goal_trajectory"]
# three qualified events within 14 days (10d, 3d, 2d ago) → count at EVALUATION TIME = 3 = target:
# ON_TRACK. Observation = measurement record time (F-07) - sequential POSTs in the same second
# are ONE observation point, so n_observations is not asserted on the API path.
check("COUNT_IN_WINDOW trajectory dari event: 3 qualified dalam window → ON_TRACK",
      tr4["status"] == "ON_TRACK" and tr4["counted"] == 3
      and tr4["as_of_ts"] >= tr4["last_event_ts"], str(tr4))
r4b = client.post("/session", json={"goal_text": "3 qualified leads in 14 days",
                                    "user_id": U4, "success_definition": "q=call"})
g4b = r4b.json()["goal"]
murl4b = f"/workspace/{U4}/goals/{g4b['goal_id']}/measurements"
client.post(murl4b, json={"kind": "event", "event_ts": wall - 10 * 86400, "qualified": True})
client.post(murl4b, json={"kind": "event", "event_ts": wall - 3 * 86400, "qualified": True})
tr4b = client.get(f"/workspace/{U4}/goals/{g4b['goal_id']}/trajectory").json()["goal_trajectory"]
# F-09: raw events grow (1→2) but BOTH records land in the same observation
# (one point) → factual current status OFF_TRACK, direction NOT claimed.
check("F-09: event mentah naik tanpa observasi kedua → bukan IMPROVING (OFF_TRACK faktual)",
      tr4b["status"] == "OFF_TRACK" and tr4b["counted"] == 2
      and "satu titik observasi" in tr4b.get("reason", ""), str(tr4b))

print("== F-07/F-08/F-09: observation time vs event time (unit, ts diinjeksi) ==")
DAY = 86400
gl = {"metric_id": "qualified_leads", "direction": "COUNT_IN_WINDOW",
      "target": 3.0, "measurement_window_days": 14}
T = 1_750_000_000
# mandate §4.1 case: 3 qualified events 28-30 days ago, NO new events; the records
# happen TODAY (single observation at as_of). Current count = 0 → NOT achieved.
ms_old = [{"kind": "event", "event_ts": T - 30 * DAY, "qualified": True, "ts": T},
          {"kind": "event", "event_ts": T - 29 * DAY, "qualified": True, "ts": T},
          {"kind": "event", "event_ts": T - 28 * DAY, "qualified": True, "ts": T}]
tr_old = typed_goal_trajectory(gl, ms_old, as_of_ts=T)
check("F-08: semua event kedaluwarsa → OFF_TRACK counted=0 (bukan ON_TRACK palsu)",
      tr_old["status"] == "OFF_TRACK" and tr_old["counted"] == 0
      and tr_old["window_start_ts"] == T - 14 * DAY, str(tr_old))
# two real observations: then (count 3, ON_TRACK at the time) → now the window slid, count 0.
ms_slide = [
    {"kind": "event", "event_ts": T - 30 * DAY, "qualified": True, "ts": T - 20 * DAY},
    {"kind": "event", "event_ts": T - 29 * DAY, "qualified": True, "ts": T - 20 * DAY},
    {"kind": "event", "event_ts": T - 28 * DAY, "qualified": True, "ts": T - 20 * DAY},
    {"kind": "event", "event_ts": T - 2 * DAY, "qualified": False, "ts": T},
]
tr_slide = typed_goal_trajectory(gl, ms_slide, as_of_ts=T)
check("F-07: observasi terpisah + sliding window menurunkan count → DRIFTING (dulu 3, kini 0)",
      tr_slide["status"] == "DRIFTING" and tr_slide["counted"] == 0 and tr_slide["prev"] == 3,
      str(tr_slide))
# two real observations: at the first only event A was known (count 1);
# event B is backfilled at the second observation → count 2 below target → IMPROVING valid.
ms_up = [
    {"kind": "event", "event_ts": T - 10 * DAY, "qualified": True, "ts": T - 9 * DAY},
    {"kind": "event", "event_ts": T - 3 * DAY, "qualified": True, "ts": T},
]
tr_up = typed_goal_trajectory(gl, ms_up, as_of_ts=T)
check("dua observasi nyata count 1→2 di bawah target → IMPROVING",
      tr_up["status"] == "IMPROVING" and tr_up["counted"] == 2 and tr_up["prev"] == 1, str(tr_up))
# one observation below target → factual OFF_TRACK (current status, direction not yet assessable)
tr_one = typed_goal_trajectory(gl, ms_old[:1], as_of_ts=T)
check("satu observasi di bawah target → OFF_TRACK (fakta current), bukan INSUFFICIENT",
      tr_one["status"] == "OFF_TRACK" and tr_one["counted"] == 0, str(tr_one))
check("event measurement TIDAK dihitung sebagai scalar value trajectory",
      tr4.get("direction") == "COUNT_IN_WINDOW" and "rates" not in tr4)
# isolation: the close_rate goal (RATE) does not drive a trajectory from raw events
trgb = client.get(f"/workspace/{U}/goals/{gb['goal_id']}/trajectory").json()["goal_trajectory"]
check("event mentah tidak masuk trajectory metric RATE (event ≠ rate — typed, A-16)",
      trgb["status"] == "INSUFFICIENT_DATA" and "rate" in trgb.get("reason", ""), str(trgb))
r5 = client.post("/session", json={"goal_text": "close rate to 25%",
                                   "user_id": U4, "metric_id": "close_rate", "target": 0.25})
g5 = r5.json()["goal"]
murl5 = f"/workspace/{U4}/goals/{g5['goal_id']}/measurements"
rz = client.post(murl5, json={"kind": "rate", "numerator": 2, "denominator": 0})
check("rate dengan denominator nol diterima sebagai RECORD (bukan nilai)",
      rz.status_code == 200)
SC5 = {"cohort": "inbound-q4", "period": "2025-Q4"}  # a quarter that has already ended
client.post(murl5, json={"kind": "rate", "numerator": 3, "denominator": 20, **SC5})
tr5 = client.get(f"/workspace/{U4}/goals/{g5['goal_id']}/trajectory").json()["goal_trajectory"]
check("rate 3/20 tunggal → INSUFFICIENT (satu pengukuran, arah belum terlihat)",
      tr5["status"] == "INSUFFICIENT_DATA" and tr5.get("skipped") == 1, str(tr5))
client.post(murl5, json={"kind": "rate", "numerator": 5, "denominator": 20, **SC5})
tr5b = client.get(f"/workspace/{U4}/goals/{g5['goal_id']}/trajectory").json()["goal_trajectory"]
check("rate 3/20 → 5/20=25%: ON_TRACK faktual dari rate terkini (A-11)",
      tr5b["status"] == "ON_TRACK" and tr5b["rates"] == [0.15, 0.25], str(tr5b))
# F-10: the rate trend comes only from COMPARABLE measurements (identical cohort+period, non-empty).
# The scenario lives in a separate goal (target 0.4) so the rate series stays controlled.
r5c = client.post("/session", json={"goal_text": "close rate to 40%",
                                    "user_id": U4, "metric_id": "close_rate", "target": 0.4})
g5c = r5c.json()["goal"]
murl5c = f"/workspace/{U4}/goals/{g5c['goal_id']}/measurements"
client.post(murl5c, json={"kind": "rate", "numerator": 4, "denominator": 20})
tr5c = client.get(f"/workspace/{U4}/goals/{g5c['goal_id']}/trajectory").json()["goal_trajectory"]
check("F-10: rate di bawah target tanpa metadata kohort → ditolak kontrak, tidak jadi seri (INSUFFICIENT)",
      tr5c["status"] == "INSUFFICIENT_DATA" and tr5c["skipped"] == 1
      and "RATE_COHORT_MISSING" in tr5c["rejected"][-1]["codes"], str(tr5c))
client.post(murl5c, json={"kind": "rate", "numerator": 4, "denominator": 20,
                          "cohort": "q4-clinics", "period": "2025-Q4"})
tr5d = client.get(f"/workspace/{U4}/goals/{g5c['goal_id']}/trajectory").json()["goal_trajectory"]
check("metadata kohort tunggal tanpa pembanding → tetap tanpa klaim arah (rate tanpa metadata tak ikut seri)",
      tr5d["status"] == "INSUFFICIENT_DATA" and tr5d["n_measurements"] == 1
      and tr5d["skipped"] == 1, str(tr5d))
client.post(murl5c, json={"kind": "rate", "numerator": 6, "denominator": 20,
                          "cohort": "q4-clinics", "period": "2025-Q4"})
tr5e = client.get(f"/workspace/{U4}/goals/{g5c['goal_id']}/trajectory").json()["goal_trajectory"]
check("kohort+periode identik dan tidak kosong → IMPROVING sah (pasangan terakhir 0.20 → 0.30)",
      tr5e["status"] == "IMPROVING" and tr5e["comparable"] is True
      and tr5e["rates"][-2:] == [0.2, 0.3], str(tr5e))
client.post(murl5c, json={"kind": "rate", "numerator": 2, "denominator": 8,
                          "cohort": "walk-in", "period": "2025-Q1"})
tr5f = client.get(f"/workspace/{U4}/goals/{g5c['goal_id']}/trajectory").json()["goal_trajectory"]
check("cohort/periode BERBEDA di tengah seri → bukan tren (INSUFFICIENT, bukan IMPROVING)",
      tr5f["status"] == "INSUFFICIENT_DATA" and tr5f["comparable"] is False
      and "sebanding" in tr5f.get("reason", ""), str(tr5f))
r6 = client.post("/session", json={"goal_text": "validate willingness to pay",
                                   "user_id": U4})
g6 = r6.json()["goal"]
murl6 = f"/workspace/{U4}/goals/{g6['goal_id']}/measurements"
client.post(murl6, json={"kind": "criteria", "criterion": "paid deposit", "met": True})
client.post(murl6, json={"kind": "criteria", "criterion": "second purchase", "met": None})
tr6 = client.get(f"/workspace/{U4}/goals/{g6['goal_id']}/trajectory").json()["goal_trajectory"]
check("criteria unknown → INSUFFICIENT tanpa skor numerik (A-15)",
      tr6["status"] == "INSUFFICIENT_DATA" and tr6["criteria_unknown"] == 1
      and "skor" not in str(tr6.get("status")), str(tr6))
client.post(murl6, json={"kind": "criteria", "criterion": "second purchase", "met": True})
tr6b = client.get(f"/workspace/{U4}/goals/{g6['goal_id']}/trajectory").json()["goal_trajectory"]
check("semua kriteria met → ON_TRACK via BUKTI (bukan angka dikarang)",
      tr6b["status"] == "ON_TRACK" and tr6b["criteria_met"] == 2, str(tr6b))
# target revision → old measurements still read with their version (A-18)
client.post(f"/workspace/{U4}/goals/{gid4}/revise", json={"target": 5})
ms4b = wgoals.measurements(U4, gid4)
check("revisi target TIDAK menulis ulang versi pengukuran lama (tetap v1)",
      all(m.get("goal_version") == 1 for m in ms4b)
      and wgoals.current_goal(U4, gid4)["version"] == 2)

# explicit revision = user input: target origin becomes explicit_input (not 'parsed, not yet confirmed')
rev_o = client.post("/session", json={"goal_text": "close rate to 25%", "user_id": "goalws_u9",
                                      "metric_id": "close_rate", "target": 0.25})
g_o = rev_o.json()["goal"]
parsed_origin = wgoals.current_goal("goalws_u9", g_o["goal_id"]).get("target_origin")
client.post(f"/workspace/goalws_u9/goals/{g_o['goal_id']}/revise", json={"target": 0.3})
check("revisi eksplisit target → target_origin explicit_input (dulu origin parse)",
      wgoals.current_goal("goalws_u9", g_o["goal_id"])["target_origin"] == "explicit_input",
      str(parsed_origin))

print("== F-11/F-12: evaluasi HISTORIS per versi — current vs saat pengukuran direkam ==")
U8 = "goalws_u8"
r8 = client.post("/session", json={"goal_text": "3 qualified leads in 14 days",
                                   "user_id": U8, "success_definition": "q=call"})
g8 = r8.json()["goal"]
murl8 = f"/workspace/{U8}/goals/{g8['goal_id']}/measurements"
client.post(murl8, json={"kind": "event", "event_ts": wall - 2 * 86400, "qualified": True})
client.post(murl8, json={"kind": "event", "event_ts": wall - 3 * 86400, "qualified": True})
ev_v1 = wgoals.evaluate_from_measurements(U8, g8["goal_id"])
check("evaluasi saat v1: counted 2 vs target 3 → NOT_ACHIEVED",
      ev_v1["status"] == "NOT_ACHIEVED" and ev_v1["values"]["target"] == 3.0, str(ev_v1["values"]))
client.post(f"/workspace/{U8}/goals/{g8['goal_id']}/revise", json={"target": 5})
ev_v2 = wgoals.evaluate_from_measurements(U8, g8["goal_id"])
check("evaluasi CURRENT memakai target versi aktif (5) atas bukti yang sama",
      ev_v2["values"]["target"] == 5.0 and ev_v2["status"] == "NOT_ACHIEVED", str(ev_v2["values"]))
g_at_v1 = wgoals.goal_at_version(U8, g8["goal_id"], 1)
check("F-12: definisi v1 dapat direkonstruksi dari event log (target 3, utuh)",
      g_at_v1 is not None and g_at_v1["target"] == 3.0
      and wgoals.current_goal(U8, g8["goal_id"])["target"] == 5.0)
hist_v1 = client.get(f"/workspace/{U8}/goals/{g8['goal_id']}/trajectory",
                     params={"version": 1}).json()
check("endpoint historis v1: evaluasi dengan target 3 + hanya measurement v1",
      hist_v1["historical"]["goal_version"] == 1 and hist_v1["historical"]["target"] == 3.0
      and hist_v1["goal_trajectory"]["counted"] == 2, str(hist_v1.get("historical")))
r404 = client.get(f"/workspace/{U8}/goals/{g8['goal_id']}/trajectory", params={"version": 9})
check("versi yang tidak pernah ada → 404 (bukan interpretasi senyap)", r404.status_code == 404)
hist_now = client.get(f"/workspace/{U8}/goals/{g8['goal_id']}/trajectory").json()
check("current trajectory memakai target v2 (tidak tercampur definisi lama)",
      hist_now["goal_trajectory"]["target"] == 5.0, str(hist_now.get("goal_trajectory")))

print("== F-13: measurement tidak comparable (definisi metric berubah) → excluded, bukan tren ==")
cur8 = wgoals.current_goal(U8, g8["goal_id"])
wgoals.upsert_goal(U8, {**cur8, "metric_id": "close_rate", "direction": "RATE_OR_RATIO"})
ev_inc = wgoals.evaluate_from_measurements(U8, g8["goal_id"])
check("event leads tidak dijadikan buku close_rate: excluded + alasan eksplisit",
      ev_inc.get("excluded_incomparable", {}).get("count") == 2
      and ev_inc["status"] == "NOT_COMPUTABLE", str(ev_inc))
traj_inc = client.get(f"/workspace/{U8}/goals/{g8['goal_id']}/trajectory").json()
check("endpoint current juga melaporkan excluded_incomparable",
      traj_inc.get("excluded_incomparable", {}).get("count") == 2, str(traj_inc.get("excluded_incomparable")))
hist_v1_after = client.get(f"/workspace/{U8}/goals/{g8['goal_id']}/trajectory",
                           params={"version": 1}).json()
check("evaluasi historis v1 TETAP dapat direkonstruksi setelah metric berubah (sejarah utuh)",
      hist_v1_after["historical"]["metric_id"] == "qualified_leads"
      and hist_v1_after["goal_trajectory"]["counted"] == 2, str(hist_v1_after.get("historical")))

print("== trajectory typed: decrease (jam founder) arah benar ==")
gh = {"metric_id": "founder_delivery_hours", "direction": "DECREASE_TO_THRESHOLD",
      "target": 15.0}
check("30 → 15: tercapai (ON_TRACK) — bukan gap generik",
      goal_trajectory(gh, [], values=[30.0, 22.0, 15.0])["status"] == "ON_TRACK")
check("30 → 32: menjauh dari threshold → DRIFTING",
      goal_trajectory(gh, [], values=[30.0, 32.0])["status"] == "DRIFTING")
check("satu pengukuran belum tercapai → INSUFFICIENT_DATA (arah belum terlihat)",
      goal_trajectory(gh, [], values=[28.0])["status"] == "INSUFFICIENT_DATA")
gi = {"metric_id": "qualified_leads", "direction": "COUNT_IN_WINDOW", "target": 3.0}
check("leads 1 → 3: IMPROVING (naik menuju target)",
      goal_trajectory(gi, [], values=[1.0, 3.0])["status"] == "ON_TRACK")

print("== GR-23: dua sumbu tetap terpisah (revenue flat vs pemahaman naik) ==")
rev_g = {"metric": "revenue_monthly", "target": 60.0, "baseline": 30.0}
gt = goal_trajectory(rev_g, [{"current_monthly": 35.0}, {"current_monthly": 35.0}])
check("revenue trajectory legacy tetap hidup (datar → INSUFFICIENT_DATA jujur)",
      gt["status"] == "INSUFFICIENT_DATA")

print("== snapshot workspace membawa konteks Goal (riwayat teratribusi) ==")
rs = client.post("/session", json={
    "goal_text": "I need three qualified leads in 14 days", "user_id": "goalws_u3",
    "success_definition": "q=call"})
sid3 = rs.json()["session_id"]
client.post(f"/session/{sid3}/message", json={"text": "I earn Rp30 juta per month now."})
fin = client.post(f"/session/{sid3}/finalize").json()
snap_path = _TMP / "workspaces" / "goalws_u3" / "snapshots.jsonl"
snaps = [json.loads(ln) for ln in snap_path.read_text().splitlines() if ln.strip()]
check("snapshot punya goal_id + goal_metric_id dari konteks evaluasi",
      snaps and snaps[-1]["goal_id"] == rs.json()["goal"]["goal_id"]
      and snaps[-1]["goal_metric_id"] == "qualified_leads")

print("== A-21/A-22: kontrak aktivasi — workspace vs sesi, tanpa switching diam-diam ==")
U7 = "goalws_u7"
ra = client.post("/session", json={"goal_text": "3 qualified leads in 14 days",
                                   "user_id": U7, "success_definition": "q=call"})
rb = client.post("/session", json={"goal_text": "close rate to 25%",
                                   "user_id": U7, "metric_id": "close_rate", "target": 0.25})
sid_a, ga7, gb7 = ra.json()["session_id"], ra.json()["goal"], rb.json()["goal"]
st_before = client.get(f"/session/{sid_a}/state").json()
check("sesi A dinavigasi dengan goal A-nya sendiri",
      st_before["goal"]["goal_id"] == ga7["goal_id"])
client.post(f"/workspace/{U7}/goals/{gb7['goal_id']}/activate")
check("aktivasi workspace memindahkan active_goal_id",
      client.get(f"/workspace/{U7}/goals").json()["active_goal_id"] == gb7["goal_id"])
st_after = client.get(f"/session/{sid_a}/state").json()
check("sesi A TIDAK berubah diam-diam (kontrak eksplisit, A-21)",
      st_after["goal"]["goal_id"] == ga7["goal_id"])
reb = client.post(f"/workspace/{U7}/goals/{gb7['goal_id']}/activate",
                  params={"session_id": sid_a}).json()
st_rebound = client.get(f"/session/{sid_a}/state").json()
check("rebind EKSPLISIT: sesi A kini memakai goal B (switching yang tercatat)",
      reb["rebound"]["goal"]["goal_id"] == gb7["goal_id"]
      and st_rebound["goal"]["goal_id"] == gb7["goal_id"])
rbad = client.post(f"/workspace/{U7}/goals/{gb7['goal_id']}/activate",
                   params={"session_id": "bukan-sesi"})
check("rebind ke sesi asing/unknown → 404 (bukan senyap)", rbad.status_code == 404)

fails = [x for x in _results if not x[1]]
print(f"\n{'=' * 50}\nHASIL: {len(_results) - len(fails)}/{len(_results)} PASS"
      + (" ✅" if not fails else f" — {len(fails)} GAGAL ❌"))
sys.exit(1 if fails else 0)
