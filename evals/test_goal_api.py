"""Goal-Relative API contract guard — CreateSession with the metric contract (int 09 §9 Phase 1).

GR-01 via API: non-revenue leads goal accepted + stable goal_id requested; GR-17: unregistered
metric_id → 422 (not silently mapped); GR-08: explicit revenue still works; GR-07: legacy
session (old goal dict without the new fields) loads without destructive migration.

Provider = mock. Run: .venv/bin/python evals/test_goal_api.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # mvp/

from evals._store_isolation import isolate_store  # noqa: E402

isolate_store()  # eval: store redirected to tmp — production store untouched

import store.adjudication_ledger as ledger  # noqa: E402
import store.funnel as funnel  # noqa: E402
import store.path_states as path_states  # noqa: E402
import store.route_execution as route_execution  # noqa: E402
import store.route_lineages as rl  # noqa: E402
import store.workspace as workspace  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="goal_api_"))
rl._BASE = _TMP / "lineages"
ledger._LEDGER_ROOT = _TMP / "ledger"
workspace._BASE = _TMP / "workspaces"
route_execution._BASE = _TMP / "workspaces"
funnel._PATH = _TMP / "funnel.jsonl"
path_states._BASE = _TMP
path_states._STATES = _TMP / "path_states.json"
path_states._HISTORY = _TMP / "path_history.jsonl"

from fastapi.testclient import TestClient  # noqa: E402

import app.main as app_main  # noqa: E402
from providers.mock import MockProvider  # noqa: E402
from store.memory import store  # noqa: E402

app_main.get_llm = lambda: MockProvider()

_results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _results.append((name, ok, detail))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" | {detail}" if detail else ""))


client = TestClient(app_main.app)

print("== GR-01 via API: 3 qualified leads / 14 hari — tanpa field revenue wajib ==")
r1 = client.post("/session", json={
    "goal_text": "I need three qualified leads in 14 days",
    "user_id": "goalapi_u1",
    "success_definition": "qualified = B2B with budget authority, booked a discovery call",
})
check("create session 200", r1.status_code == 200, str(r1.status_code))
g = r1.json()["goal"]
check("goal tersimpan: metric qualified_leads COUNT_IN_WINDOW tanpa target_monthly",
      g["metric_id"] == "qualified_leads" and g["direction"] == "COUNT_IN_WINDOW")
check("goal_id stabil dimint (identitas workspace)", g["goal_id"].startswith("goal_"))
check("window 14 hari tercatat", g["measurement_window_days"] == 14)
sid1 = r1.json()["session_id"]
s1 = store.get(sid1)
check("goal object hidup di session store (bukan cuma respons)",
      (s1.goal or {}).get("metric_id") == "qualified_leads")
st = client.get(f"/session/{sid1}/state").json()
check("GET /state mengekspos goal terstruktur", st["goal"]["metric_id"] == "qualified_leads")

print("== GR-17 via API: metric_id tak terdaftar → 422 abstain ==")
r17 = client.post("/session", json={
    "goal_text": "brand aura everywhere", "metric_id": "brand_aura"})
check("422 dengan alasan registry (bukan 500, bukan dipetakan senyap)",
      r17.status_code == 422 and "tidak terdaftar" in r17.json()["detail"])

print("== GR-08 via API: revenue eksplisit tetap kompatibel ==")
r8 = client.post("/session", json={
    "goal_text": "We make Rp30 million per month and want Rp60 million per month within 90 days.",
    "user_id": "goalapi_u2",
    "target": 60.0, "baseline": 30.0,
})
g8 = r8.json()["goal"]
check("input eksplisit menang: target 60 origin explicit_input",
      g8["target"] == 60.0 and g8["target_origin"] == "explicit_input")
check("metric revenue_monthly terresolusi registry",
      g8["metric_id"] == "revenue_monthly" and g8["direction"] == "INCREASE_TO_THRESHOLD")

print("== GR-07 via API: sesi legacy (goal dict lama) dimuat tanpa migrasi destruktif ==")
s_legacy = store.create("target Rp60 juta per bulan", "en", user_id="goalapi_u3",
                        goal={"metric": "revenue_monthly", "unit": "Rp juta/bulan",
                              "target": 60.0, "target_origin": "goal_marker",
                              "desire": "naikkan omzet"})
stl = client.get(f"/session/{s_legacy.id}/state").json()
check("legacy goal terbaca; metric_id efektif revenue_monthly via model",
      stl["goal"]["metric"] == "revenue_monthly" and stl["goal"].get("metric_id", "") == "")
check("field baru tidak ditambahkan ke data legacy saat load (migrasi non-destruktif)",
      "direction" not in stl["goal"] or stl["goal"]["direction"] == "")

print("== kontrak direction eksplisit ==")
r9 = client.post("/session", json={
    "goal_text": "cac", "metric_id": "cac", "direction": "AT_MOST", "target": 600.0})
check("direction kompatibel (AT_MOST ↔ DECREASE) diterima",
      r9.status_code == 200 and r9.json()["goal"]["direction"] == "AT_MOST")
r10 = client.post("/session", json={
    "goal_text": "leads", "metric_id": "qualified_leads", "direction": "RATE_OR_RATIO"})
check("direction tidak kompatibel → 422 (kontrak, bukan tebakan)",
      r10.status_code == 422)

fails = [x for x in _results if not x[1]]
print(f"\n{'=' * 50}\nHASIL: {len(_results) - len(fails)}/{len(_results)} PASS"
      + (" ✅" if not fails else f" — {len(fails)} GAGAL ❌"))
sys.exit(1 if fails else 0)
