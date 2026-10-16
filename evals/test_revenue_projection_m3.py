"""M3 DoD — Revenue View as a projection (user review 25 Sep).

Three questions that must be answered (golden fixture = the M2 live scenario):
1. Projection completeness — the Revenue View still gets current 18jt,
   historical 30jt, temporal distinction, relevant desire.
2. Projection loss — what is lost graph→view (transparent, accounted for).
3. Diagnosis regression — RevenueState from the view: correct fields + provenance
   node; the regex fallback path still runs when the graph is empty.

Plus the principle 'a projection does not diagnose' — the view does NOT yield
constraint/mechanism names.
Fully deterministic.
"""
import sys

sys.path.insert(0, ".")

from agents.diagnosis import _apply_view
from core.schema.evidence import EvidenceItem
from domains.revenue.projection import build_revenue_view
from domains.revenue.schema.state import RevenueState
from domains.revenue.stages.state import build_revenue_state

PASS = 0
FAIL = 0


def check(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  PASS {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} {detail}")


def golden_graph() -> dict:
    data = [
        ("claim", "omzet", "was", None, 30.0, "past", "Dulu omzet saya 30 juta"),
        ("claim", "omzet", "currently", None, 18.0, "now", "sekarang sekitar 18 juta"),
        ("claim", "saya", "capek", None, None, "now", "Saya juga capek"),
        ("claim", "pekerjaan", "makin_banyak", "harus saya handle sendiri", None, "now",
         "pekerjaan yang harus saya handle sendiri"),
        ("desire", "saya", "pengen", "bisnis jalan tanpa saya", None, "future",
         "pengen bisnis jalan tanpa saya"),
    ]
    nodes = {}
    for i, (ty, s, p, o, v, t, vb) in enumerate(data, 1):
        nodes[f"cl-t2-{i:03d}"] = {
            "id": f"cl-t2-{i:03d}", "type": ty,
            "triple": {"subject": {"label": s}, "predicate": {"label": p},
                       "object": {"label": o} if o else None, "value": v,
                       "unit": "juta" if v else None},
            "tense": t, "modality": "factual", "verbatim": vb,
            "provenance": {"turn": 2},
        }
    return {"nodes": nodes, "edges": {}}


print("[M3-1] projection completeness (golden fixture M2)")
view = build_revenue_view(golden_graph())
f = view["fields"]
check("current_revenue = 18.0 (now)", f["current_revenue"]["value"] == 18.0
      and f["current_revenue"]["tense"] == "now")
check("historical_revenue = 30.0 (past) — temporal distinction utuh",
      f["historical_revenue"]["value"] == 30.0 and f["historical_revenue"]["tense"] == "past")
check("desire relevan tercatat", len(view["desires"]) == 1
      and "bisnis" in (view["desires"][0].get("object") or ""))
check("signal founder-dependency family", any(
    s["signal"] in ("founder_dependency", "operational_load_increase")
    for s in view["signals"]))

print("[M3-2] projection loss transparan")
check("loss terhitung (1/5 — 'capek' belum terpetakan)", len(view["loss"]) == 1
      and view["node_count"] == 5)
check("field punya provenance node id", all(
    e.get("node_id", "").startswith("cl-") for e in f.values()))

print("[M3-3] diagnosis regression — RevenueState dari view")
st = RevenueState()
_apply_view(st, view)
check("current_monthly = 18.0", st.current_monthly == 18.0)
check("target tak dikarang (tidak ada di graph)", st.target_monthly is None)
check("provenance tercatat di sources",
      (st.sources.get("current_monthly") or {}).get("evidence_id", "").startswith("cl-"))
blob = " ".join(st.notes).lower()
check("projection TIDAK mendiagnosis — tanpa nama constraint/mechanism",
      all(w not in blob for w in ("bottleneck", "constraint c6", "mechanism", "diagnosis:")))

print("[M3-4] fallback regex tetap jalan (graph kosong)")
ev = [EvidenceItem(id="ev-1", signal="Revenue Rp30 juta per bulan DARI 3 klien",
                   level="behavioral", topic="REVENUE_STATE")]
st_old = build_revenue_state(ev, "target Rp60 juta", transcript="Revenue Rp30 juta per bulan")
check("jalur regex lama masih mengisi current", st_old.current_monthly == 30.0)
check("jalur regex lama masih mengisi target", st_old.target_monthly == 60.0)

print("[M3-5] view menimpa regex bila keduanya jalan (switch arah benar)")
st_mix = build_revenue_state(ev, "target Rp60 juta", transcript="Revenue Rp30 juta per bulan")
_apply_view(st_mix, view)
check("graph view MENANG: current 18.0 (bukan regex 30)", st_mix.current_monthly == 18.0)
check("regex fallback mengisi yang view tak punya: target 60 tetap",
      st_mix.target_monthly == 60.0)

print("[M3-6] derivasi dihitung SETELAH view (bug laten 60ef056, gate-smoke 27 Sep)")
st_g = build_revenue_state(ev, "target Rp60 juta",
                           transcript="Revenue Rp30 juta per bulan",
                           graph=golden_graph())
check("current dari view (18) dipakai builder", st_g.current_monthly == 18.0)
check("gap = target 60 - current VIEW 18 = 42 (bukan regex basi 30)",
      st_g.gap_monthly == 42.0)
check("provenance gap menyebut angka view",
      "current 18.0" in (st_g.sources.get("gap_monthly") or {}).get("derivation", ""))
st_none = build_revenue_state([], "", graph={"nodes": {}, "edges": {}})
check("graph kosong -> tanpa override, gap None (regex fallback)",
      st_none.gap_monthly is None and st_none.current_monthly is None)
print("=" * 50)
print(f"HASIL: {PASS}/{PASS + FAIL} PASS — {FAIL} GAGAL")
sys.exit(0 if FAIL == 0 else 1)
