"""Goal-Relative navigation guard — semantics-aware Goal gate + zero-path taxonomy (int 09 §4-§5).

GR-12 Goal readiness uses its own metric semantics (not a universal target_monthly);
GR-13 a Goal category does not birth paths; GR-14 UNKNOWN stays UNKNOWN; GR-15 hard-check
contradictions persist as STOP + provenance (not discarded); GR-16 supporting-metric
relations are not claimed as causal; GR-17 unsupported metric abstains. The LIVE (provisional)
and FINALIZE (diagnosis) paths use the same semantics.

Deterministic (mock provider). Run: .venv/bin/python evals/test_goal_navigation.py
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

_TMP = Path(tempfile.mkdtemp(prefix="goal_nav_"))
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
from domains.revenue.navigation.paths import (  # noqa: E402
    GOAL_METRIC_UNSUPPORTED,
    GOAL_UNDERSPECIFIED,
    build_possible_paths,
)
from domains.revenue.navigation.signals import RevenueSignals  # noqa: E402
from domains.revenue.schema.goal import build_goal, parse_goal_text  # noqa: E402
from domains.revenue.schema.state import RevenueState  # noqa: E402
from providers.mock import MockProvider  # noqa: E402

app_main.get_llm = lambda: MockProvider()

_results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _results.append((name, ok, detail))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" | {detail}" if detail else ""))


def codes_of(result: dict) -> list[tuple[str, str | None]]:
    return [(u.get("code"), u.get("goal_code")) for u in result.get("unresolved", [])]


print("== GR-12: Goal leads valid — gate pakai semantik sendiri, bukan revenue ==")
leads = build_goal("3 qualified leads in 14 days", measurement_window_days=14,
                   success_definition="qualified = B2B booked discovery call")
sig = RevenueSignals(RevenueState(), goal=leads)("state:goal_established")
check("sinyal goal_established TRUE untuk goal leads (tanpa target_monthly)",
      sig.value is True, sig.reason)
out = build_possible_paths(RevenueState(), None, goal=leads.model_dump())
check("tidak diblok GOAL_NOT_ESTABLISHED; 0 path jujur INSUFFICIENT_VERIFIED_STATE",
      codes_of(out) == [("INSUFFICIENT_VERIFIED_STATE", None)] and len(out["paths"]) == 0,
      str(codes_of(out)))
check("konteks goal terproyeksi (metric_id + readiness)",
      (out["context"]["goal"] or {}).get("metric_id") == "qualified_leads"
      and out["context"]["goal"]["readiness"]["ready"] is True)

print("== GR-12b: revenue eksplisit via Goal — overlay provenance, bukan parse ulang ==")
rev = build_goal("grow the business", metric_id="revenue_monthly", target=60.0, baseline=30.0)
rs_rev = RevenueState(current_monthly=30.0)
out_rev = build_possible_paths(rs_rev, None, goal=rev.model_dump())
check("emergence revenue lama tetap hidup (5 path) via overlay konteks Goal",
      len(out_rev["paths"]) == 5, str([p["path_id"] for p in out_rev["paths"]]))
check("overlay membawa provenance (bukan angka dikarang)",
      rs_rev.sources.get("target_monthly", {}).get("origin") == "explicit_input"
      and rs_rev.target_monthly == 60.0 and rs_rev.gap_monthly == 30.0)
rs_norev = RevenueState()
leads_state = build_possible_paths(rs_norev, None, goal=leads.model_dump())
check("goal non-revenue TIDAK menulis slot revenue (tak ada koersi)",
      rs_norev.target_monthly is None and rs_norev.current_monthly is None)

print("== GR-13: kategori/metric Goal saja tidak melahirkan path ==")
out13 = build_possible_paths(RevenueState(), None, goal=leads.model_dump())
check("category=demand tanpa evidence demand → nol path (bukan path kategori)",
      len(out13["paths"]) == 0)
rs13 = RevenueState(current_monthly=30.0, target_monthly=60.0, gap_monthly=30.0)
out13b = build_possible_paths(rs13, None, goal=leads.model_dump())
check("path lahir dari KONDISI terverifikasi (revenue gap terbukti), bukan dari kategori Goal",
      len(out13b["paths"]) > 0 and all("path_id" in p for p in out13b["paths"]))

print("== GR-14: check UNKNOWN tetap UNKNOWN (bukan false/ABSENT) ==")
out14 = build_possible_paths(RevenueState(current_monthly=30.0, target_monthly=60.0,
                                          gap_monthly=30.0), None,
                             goal=leads.model_dump())
do = next((p for p in out14["paths"] if p["path_id"] == "path.direct_outreach"), None)
check("direct_outreach muncul dengan check capacity UNKNOWN (bukan ABSENT)",
      do is not None and any(c["state"] == "UNKNOWN" for c in do["checks"]))
check("status kata memakai kamus engine (OPEN/TEST FIRST/NOT YET/STOP)",
      do is not None and do["status"] in ("OPEN", "TEST_FIRST", "NOT_YET", "STOP"))

print("== GR-15: kontradiksi hard check → STOP + stop_provenance engine (bukan dibuang) ==")
rs15 = RevenueState(current_monthly=30.0, target_monthly=60.0, gap_monthly=30.0,
                    willingness_to_pay_new_price="REJECTED_AT_NEW_PRICE")  # D2: NEW-price contradiction
out15 = build_possible_paths(rs15, None, goal=leads.model_dump())
vp = next((p for p in out15["paths"] if p["path_id"] == "path.value_repricing"), None)
check("value_repricing bertahan sebagai STOP (CONTRADICTED), tidak dihapus",
      vp is not None and vp["status"] == "STOP" and vp["feasibility"] == "CONTRADICTED")
check("stop_provenance = ENGINE_CONTRADICTION (asal STOP terpisah dari lifecycle user)",
      vp is not None and any(s["source"] == "ENGINE_CONTRADICTION"
                             for s in vp["stop_provenance"]))

print("== GR-16: relasi supporting metric dipertahankan, tidak diklaim kausal ==")
g16 = build_goal("3 qualified leads in 14 days", measurement_window_days=14,
                 success_definition="qualified = booked call")
g16.supporting_metrics.append(
    {"metric_id": "reply_rate", "relation": "UNKNOWN_RELATION", "note": "correlation only"})
out16 = build_possible_paths(RevenueState(), None, goal=g16.model_dump())
sm = (out16["context"]["goal"] or {}).get("supporting_metrics", [])
check("relation UNKNOWN_RELATION lolos apa adanya ke konteks (tanpa klaim kausal)",
      sm and sm[0]["relation"] == "UNKNOWN_RELATION")

print("== taksonomi nol-path (int 09 §5.1) — kode Goal vs kode universal ==")
traction = parse_goal_text("I need traction")
out_t = build_possible_paths(RevenueState(), None, goal=traction.model_dump())
check("Goal underspecified → GOAL_NOT_ESTABLISHED + goal_code GOAL_UNDERSPECIFIED",
      ("GOAL_NOT_ESTABLISHED", GOAL_UNDERSPECIFIED) in codes_of(out_t))
unsup = build_goal("weird metric goal", metric_id="revenue_monthly")
unsup.metric_id = "brand_aura"  # simulate data with an unregistered metric
out_u = build_possible_paths(RevenueState(), None, goal=unsup.model_dump())
check("metric tak terdaftar → goal_code GOAL_METRIC_UNSUPPORTED (abstain, bukan path karangan)",
      ("GOAL_NOT_ESTABLISHED", GOAL_METRIC_UNSUPPORTED) in codes_of(out_u))
rs_ne = RevenueState(current_monthly=0.0, target_monthly=0.0, gap_monthly=0.0)
out_ne = build_possible_paths(rs_ne, None, goal=leads.model_dump())
check("Goal siap + bukti menolak strategi → NO_SUPPORTED_STRATEGY (bukan salah Goal)",
      any(c[0] == "NO_SUPPORTED_STRATEGY" for c in codes_of(out_ne)),
      str(codes_of(out_ne)))

print("== jalur LIVE + FINALIZE memakai semantika yang sama (HTTP, provider mock) ==")
client = TestClient(app_main.app)
r = client.post("/session", json={
    "goal_text": "I need three qualified leads in 14 days",
    "user_id": "goalnav_u1",
    "success_definition": "qualified = B2B with budget authority, booked a discovery call",
})
sid = r.json()["session_id"]
nav = client.get(f"/session/{sid}/navigation").json()
check("GET /navigation hidup (mock) — planner jalan tanpa LLM",
      "move" in nav and nav["move"] is not None)
fin = client.post(f"/session/{sid}/finalize")
check("finalize 200 dengan provider mock", fin.status_code == 200, str(fin.status_code))
diag = fin.json()
pp = diag.get("possible_paths") or {}
gctx = ((pp.get("context") or {}).get("goal")) or {}
check("diagnosis final membawa konteks Goal (metric qualified_leads, ready)",
      gctx.get("metric_id") == "qualified_leads" and gctx.get("readiness", {}).get("ready") is True)
check("diagnosis final tidak memblokir goal non-revenue (nol path = alasan jujur)",
      isinstance(pp.get("paths"), list)
      and all(u.get("code") != "GOAL_NOT_ESTABLISHED" for u in pp.get("unresolved") or []))
r2 = client.post("/session", json={
    "goal_text": "We make Rp30 million per month and want Rp60 million per month.",
    "user_id": "goalnav_u2", "target": 60.0, "baseline": 30.0})
sid2 = r2.json()["session_id"]
client.post(f"/session/{sid2}/message", json={"text": "I currently earn Rp30 juta per month from 3 clients."})
fin2 = client.post(f"/session/{sid2}/finalize").json()
pp2 = ((fin2.get("possible_paths") or {}))
check("revenue via jalur Goal-Relative tetap menghasilkan path (kompatibilitas GR-08)",
      len(pp2.get("paths") or []) > 0,
      str(len(pp2.get("paths") or [])))
check("target eksplisit Goal menggantikan fallback parse (origin kuat menang)",
      fin2["revenue_state"]["target_monthly"] == 60.0,
      str(fin2["revenue_state"]["target_monthly"]))

print("== A-04..A-07: relasi Path terhadap Primary Goal EKSPLISIT — bukan metadata senyap ==")
rs_gap = RevenueState(current_monthly=30.0, target_monthly=60.0, gap_monthly=30.0)
leads_ready = build_goal("3 qualified leads in 14 days", measurement_window_days=14,
                         success_definition="qualified = B2B booked discovery call")
out_rel = build_possible_paths(rs_gap, None, goal=leads_ready.model_dump())
check("revenue gap ada + goal leads → path revenue tetap BISA muncul (generator tidak diubah)",
      len(out_rel["paths"]) > 0, f"n={len(out_rel['paths'])}")
check("TAPI setiap path menyatakan UNKNOWN_RELATION (A-05: revenue gap ≠ relevan ke leads)",
      out_rel["paths"] and all(p.get("goal_relation") == "UNKNOWN_RELATION"
                               for p in out_rel["paths"]))
check("catatan relasi jujur: muncul dari kondisi revenue, bukan klaim kausal (A-07)",
      all("belum didukung Knowledge" in (p.get("goal_relation_note") or "")
          for p in out_rel["paths"]))
rev_ready = build_goal("grow revenue to Rp60 juta", metric_id="revenue_monthly", target=60.0)
out_rev = build_possible_paths(rs_gap, None, goal=rev_ready.model_dump())
check("goal revenue → DIRECT_CONTRIBUTION definisional di ruang revenue (A-29 kompatibel)",
      out_rev["paths"] and all(p.get("goal_relation") == "DIRECT_CONTRIBUTION"
                               for p in out_rev["paths"]))
# Relation ≠ status (round 4 Phase 4): the UNKNOWN_RELATION label must not raise, lower, or
# replace a path's status/identity - status comes from evidence & feasibility, relation from Knowledge.
out_base = build_possible_paths(rs_gap, None)  # same state, no goal context
by_id = lambda o: {p["path_id"]: (p["status"], p.get("lifecycle")) for p in o["paths"]}  # noqa: E731
check("relasi UNKNOWN tidak mengubah status/lifecycle/identitas path (sama dengan tanpa goal)",
      by_id(out_rel) == by_id(out_base) and set(by_id(out_rel)) == set(by_id(out_base)),
      f"{by_id(out_rel)} vs {by_id(out_base)}")
check("tidak ada path rekaan: himpunan path = yang dibentuk generator dari keadaan, bukan dari label relasi",
      all(p["path_id"].startswith("path.") for p in out_rel["paths"]))
out_ng = build_possible_paths(RevenueState(), None)  # no goal (legacy)
check("tanpa goal terstruktur → tanpa anotasi relasi (perilaku legacy utuh)",
      all("goal_relation" not in p for p in out_ng.get("paths") or []))

fails = [x for x in _results if not x[1]]
print(f"\n{'=' * 50}\nHASIL: {len(_results) - len(fails)}/{len(_results)} PASS"
      + (" ✅" if not fails else f" — {len(fails)} GAGAL ❌"))
sys.exit(1 if fails else 0)
