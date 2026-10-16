"""Goal observation series for JOURNEY (Goal-relative): the Goal's own metric + unit, valid observations only.

Preserves (int 09 par 6 JOURNEY): the Goal trajectory = observed measurements in the Goal's metric; no
fabricated points, interpolation, missing -> 0, or incomparable evidence drawn as progress; the revenue
Goal does not use this path; switching Goals does not carry other Goals' data. The scoring source stays
`goal_evaluation` (the series does not compute ACHIEVED).

Run: .venv/bin/python evals/test_goal_series.py
"""
from __future__ import annotations

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

_TMP = Path(tempfile.mkdtemp(prefix="goal_series_"))
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
from domains.revenue.schema.goal import build_goal, mint_goal_id  # noqa: E402
from domains.revenue.stages.trajectory import (  # noqa: E402
    SERIES_NO_OBSERVATIONS,
    SERIES_OBSERVED,
    SERIES_UNSUPPORTED,
    goal_series,
)
from providers.mock import MockProvider  # noqa: E402

app_main.get_llm = lambda: MockProvider()
client = TestClient(app_main.app)

DAY = 86400
T = 1_750_000_000
_results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _results.append((name, ok, detail))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" | {detail}" if detail else ""))


_n = [0]


def mk(text: str, **kw) -> tuple[str, str]:
    _n[0] += 1
    uid = f"gs_u{_n[0]}"
    g = build_goal(text, goal_id=mint_goal_id(), **kw).model_dump()
    wgoals.upsert_goal(uid, g)
    return uid, g["goal_id"]


def rec(uid: str, gid: str, at: int, **m) -> None:
    wgoals._now = lambda: at
    wgoals.record_measurement(uid, gid, m)


def series(uid: str, gid: str, as_of: int = T) -> dict:
    comp, _ = wgoals.split_comparable_measurements(uid, gid)
    return goal_series(wgoals.current_goal(uid, gid), comp, as_of_ts=as_of)


RATE = dict(metric_id="close_rate", target=0.25, measurement_window_days=60)
PER = {"period_start_ts": T - 62 * DAY, "period_end_ts": T - 2 * DAY}

print("== S1: RATE - hanya observasi sah, dalam rate (bukan income) ==")
u, g = mk("close rate to 25%", baseline=0.15, **RATE)
rec(u, g, T - 20 * DAY, kind="rate", numerator=3, denominator=20, cohort="inbound", period="w1",
    period_start_ts=T - 82 * DAY, period_end_ts=T - 22 * DAY)
rec(u, g, T - 10 * DAY, kind="rate", numerator=4, denominator=20, cohort="inbound", period="w2",
    period_start_ts=T - 72 * DAY, period_end_ts=T - 12 * DAY)
rec(u, g, T - 5 * DAY, kind="rate", numerator=9, denominator=20, cohort="inbound", period="last quarter")  # tak terverifikasi
rec(u, g, T - 3 * DAY, kind="rate", numerator=9, denominator=3, cohort="inbound", period="w3", **PER)  # n > d
rec(u, g, T - 1 * DAY, kind="rate", numerator=5, denominator=20, cohort="inbound", period="w4", **PER)
s = series(u, g)
check("S1a. kind=rate, unit ratio, target 0.25, baseline 0.15, window 60 - metric Goal, bukan income",
      s["kind"] == "rate" and s["unit"] == "ratio" and s["target"] == 0.25 and s["baseline"] == 0.15
      and s["window_days"] == 60 and s["metric_id"] == "close_rate", str({k: s[k] for k in ("kind", "unit", "target")}))
check("S1b. status OBSERVED; titik = tepat tiga observasi sah (0.15, 0.20, 0.25) berurut waktu pencatatan",
      s["status"] == SERIES_OBSERVED and [p["value"] for p in s["points"]] == [0.15, 0.2, 0.25]
      and [p["ts"] for p in s["points"]] == sorted(p["ts"] for p in s["points"]), str(s["points"]))
check("S1c. dua pengukuran ditolak TIDAK menjadi titik; jumlah + kode dilaporkan",
      s["rejected"]["count"] == 2
      and {"RATE_PERIOD_UNVERIFIABLE", "RATE_NUMERATOR_EXCEEDS_DENOMINATOR"} <= set(s["rejected"]["codes"]),
      str(s["rejected"]))
check("S1d. tiap titik membawa interval periode yang terverifikasi + pembilang/penyebut (jejak bukti)",
      all(p["period_start_ts"] and p["period_end_ts"] and p["denominator"] == 20 for p in s["points"]))
check("S1e. satu segment (kohort sama): garis boleh menghubungkan titik", {p["segment"] for p in s["points"]} == {0})

u, g = mk("close rate to 25%", **RATE)
rec(u, g, T - 20 * DAY, kind="rate", numerator=3, denominator=20, cohort="inbound", period="w1",
    period_start_ts=T - 82 * DAY, period_end_ts=T - 22 * DAY)
rec(u, g, T - 10 * DAY, kind="rate", numerator=4, denominator=20, cohort="walkin", period="w2",
    period_start_ts=T - 72 * DAY, period_end_ts=T - 12 * DAY)
s = series(u, g)
check("S1f. kohort berubah di tengah seri -> segment berbeda (UI tidak menyambung garis lintas populasi)",
      [p["segment"] for p in s["points"]] == [0, 1] and s["baseline"] is None)

print("== S2: tidak ada titik karangan ==")
u, g = mk("close rate to 25%", **RATE)
s = series(u, g)
check("S2a. tanpa pengukuran: NO_OBSERVATIONS, points kosong (bukan 0)", s["status"] == SERIES_NO_OBSERVATIONS and s["points"] == [])
rec(u, g, T - DAY, kind="rate", numerator=6, denominator=20, cohort="inbound", period="2026-Q3")  # 92 days != 60 (as_of in the future -> invalid)
s = series(u, g)
check("S2b. hanya bukti tak sah: tetap NO_OBSERVATIONS, 1 ditolak (30% > target TIDAK digambar)",
      s["status"] == SERIES_NO_OBSERVATIONS and s["points"] == [] and s["rejected"]["count"] == 1, str(s["rejected"]))
rec(u, g, T - DAY // 2, kind="rate", numerator=3, denominator=20, cohort="inbound", period="w1",
    period_start_ts=T - 62 * DAY, period_end_ts=T - 2 * DAY)
s = series(u, g)
check("S2c. satu observasi sah = tepat satu titik (UI tidak boleh menggambar tren dari satu titik)",
      len(s["points"]) == 1 and s["points"][0]["value"] == 0.15)
check("S2d. observasi sesudah as_of tidak ikut", len(series(u, g, as_of=T - 3 * DAY)["points"]) == 0)

print("== S3: COUNT - observasi = waktu pencatatan, tanpa temporal leakage ==")
CNT = dict(metric_id="qualified_leads", success_definition="q=call", measurement_window_days=14, target=3)
u, g = mk("3 qualified leads in 14 days", **CNT)
rec(u, g, T - 10 * DAY, kind="event", event_id="a", event_ts=T - 11 * DAY, qualified=True)
rec(u, g, T - 5 * DAY, kind="event", event_id="b", event_ts=T - 6 * DAY, qualified=True)
s = series(u, g)
check("S3a. dua observasi count: 1 lalu 2; unit leads, window 14", s["kind"] == "count" and s["unit"] == "leads"
      and [p["value"] for p in s["points"]] == [1, 2] and s["window_days"] == 14, str(s["points"]))
rec(u, g, T - 1 * DAY, kind="event", event_id="c", event_ts=T - 12 * DAY, qualified=True)  # late evidence
s2 = series(u, g)
check("S3b. bukti yang baru dilaporkan tidak menulis ulang observasi lampau (titik 1 dan 2 tetap)",
      [p["value"] for p in s2["points"]][:2] == [1, 2] and len(s2["points"]) == 3, str(s2["points"]))
u, g = mk("leads", metric_id="qualified_leads", success_definition="q=call", target=3)
rec(u, g, T - DAY, kind="event", event_id="a", event_ts=T - 2 * DAY, qualified=True)
check("S3c. count tanpa window: NO_OBSERVATIONS dengan alasan, bukan seri tebakan",
      series(u, g)["status"] == SERIES_NO_OBSERVATIONS)

print("== S4: value, criteria, tak dikenal, revenue ==")
u, g = mk("shorten sales cycle", metric_id="sales_cycle_days", target=20)
rec(u, g, T - 9 * DAY, kind="value", value=45)
rec(u, g, T - 2 * DAY, kind="value", value=38)
s = series(u, g)
check("S4a. nilai teramati (days, arah turun): dua titik, unit days, target 20",
      s["kind"] == "value" and s["unit"] == "days" and s["direction"] == "DECREASE_TO_THRESHOLD"
      and [p["value"] for p in s["points"]] == [45.0, 38.0], str(s["points"]))
u, g = mk("validate wtp", metric_id="wtp_validated")
rec(u, g, T - DAY, kind="criteria", criterion="paid deposit", met=True)
s = series(u, g)
check("S4b. criteria: UNSUPPORTED sebagai seri numerik, kriteria dibawa bertipe (bukan skor)",
      s["status"] == SERIES_UNSUPPORTED and s["points"] == [] and s["criteria"] == [{"criterion": "paid deposit", "met": True}])
check("S4c. Goal tanpa semantics -> UNSUPPORTED (tidak ditebak ke income)",
      goal_series({"goal_id": "x", "metric": "other", "metric_id": "", "unit": "?"}, [], as_of_ts=T)["status"] == SERIES_UNSUPPORTED)
check("S4d. Goal revenue tidak memakai seri ini (None): JOURNEY memakai jalur check-in income",
      goal_series({"metric_id": "revenue_monthly", "direction": "INCREASE_TO_THRESHOLD"}, [], as_of_ts=T) is None
      and goal_series({"metric": "revenue_monthly"}, [], as_of_ts=T) is None)

print("== S5: kesebandingan - bukti dari definisi lain tidak digambar ==")
u, g = mk("close rate to 25%", scope="klinik", **RATE)
rec(u, g, T - 5 * DAY, kind="rate", numerator=3, denominator=20, cohort="klinik", period="w1", **PER)
wgoals._now = lambda: T - 4 * DAY
wgoals.upsert_goal(u, {**wgoals.current_goal(u, g), "scope": "restoran"})  # population changed: the meaning of old evidence changes
rec(u, g, T - 2 * DAY, kind="rate", numerator=5, denominator=20, cohort="restoran", period="w2", **PER)
comp, excl = wgoals.split_comparable_measurements(u, g)
s = goal_series(wgoals.current_goal(u, g), comp, as_of_ts=T)
check("S5a. bukti klinik (definisi lama) dikecualikan sebagai tak sebanding: TIDAK jadi titik; hanya restoran 0.25",
      len(excl) == 1 and [p["value"] for p in s["points"]] == [0.25], f"comp={len(comp)} excl={len(excl)} {s['points']}")

print("== S6: payload state sesi membawa seri Goal AKTIF; pergantian Goal tanpa kebocoran ==")
UID = "gs_http_user"
rA = client.post("/session", json={"goal_text": "close rate to 25%", "user_id": UID, "metric_id": "close_rate",
                                  "target": 0.25, "measurement_window_days": 60}).json()
rB = client.post("/session", json={"goal_text": "3 qualified leads in 14 days", "user_id": UID,
                                  "metric_id": "qualified_leads", "target": 3, "measurement_window_days": 14,
                                  "success_definition": "q=call"}).json()
rC = client.post("/session", json={"goal_text": "reach Rp20 million a month", "user_id": UID}).json()
gA, gB = rA["goal"]["goal_id"], rB["goal"]["goal_id"]
now = int(time.time())
wgoals._now = lambda: now  # store clock back to real time (previous part used a fixed T)
client.post(f"/workspace/{UID}/goals/{gA}/measurements",
            json={"kind": "rate", "numerator": 5, "denominator": 20, "cohort": "inbound", "period": "w",
                  "period_start_ts": now - 62 * DAY, "period_end_ts": now - 2 * DAY})
client.post(f"/workspace/{UID}/goals/{gB}/measurements",
            json={"kind": "event", "event_id": "e1", "event_ts": now - DAY, "qualified": True})
stA = client.get(f"/session/{rA['session_id']}/state").json()
stB = client.get(f"/session/{rB['session_id']}/state").json()
stC = client.get(f"/session/{rC['session_id']}/state").json()
sa, sb = stA["goal_series"], stB["goal_series"]
check("S6a. state sesi rate: seri milik Goal-nya (goal_id, ratio, 1 titik 0.25)",
      sa["goal_id"] == gA and sa["unit"] == "ratio" and [p["value"] for p in sa["points"]] == [0.25])
check("S6b. state sesi count: seri milik Goal-nya (goal_id, leads, 1 titik) - tidak membawa titik rate Goal A",
      sb["goal_id"] == gB and sb["unit"] == "leads" and [p["value"] for p in sb["points"]] == [1]
      and all("cohort" not in p for p in sb["points"]))
check("S6c. state sesi revenue: goal_series None (income tetap jalur check-in)", stC["goal_series"] is None)
check("S6d. goal_series dan goal_measured dari payload yang sama merujuk Goal yang sama",
      stA["goal_measured"]["kind"] == "rate" and stA["goal"]["goal_id"] == sa["goal_id"])

fails = [r for r in _results if not r[1]]
print(f"\nHASIL: {len(_results) - len(fails)}/{len(_results)} PASS" + (" - GAGAL ❌" if fails else " ✅"))
sys.exit(1 if fails else 0)
