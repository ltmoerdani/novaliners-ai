"""M2 DoD — shadow/parallel (user review 25 Sep, strict scope):

One turn in -> old pipeline AND universal understanding run in parallel
-> both are verified -> a structured drift report is stored.

Deterministic (no LLM): delta_from_understanding + verify + drift report.
Real-LLM evidence lives in the live-server test (see commit message).
"""
import dataclasses
import sys

sys.path.insert(0, ".")

from evals._store_isolation import isolate_store  # noqa: E402

isolate_store()  # eval: store redirected to tmp — production store untouched

from core.state_graph import GraphStore, verify_delta  # noqa: E402
from core.state_graph.drift import build_drift_report  # noqa: E402
from core.state_graph.understanding import (  # noqa: E402
    UClaim,
    UEdge,
    UniversalUnderstanding,
    delta_from_understanding,
)
from store.memory import Session  # noqa: E402

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


print("[M2-1] skenario reviewer: omzet turun + beban pribadi (angka DAN non-angka)")
USER = ("Dulu omzet saya 30 juta, sekarang sekitar 18 juta. "
        "Saya juga merasa makin banyak pekerjaan yang harus saya handle sendiri.")
u = UniversalUnderstanding(
    claims=[
        UClaim(type="claim", subject="omzet", predicate="was", value=30.0, unit="juta",
               tense="past", hedge=False, verbatim="Dulu omzet saya 30 juta"),
        UClaim(type="claim", subject="omzet", predicate="currently", value=18.0, unit="juta",
               tense="now", hedge=True, verbatim="sekarang sekitar 18 juta"),
        UClaim(type="claim", subject="semua pekerjaan", predicate="passes_through",
               object="saya", tense="now", hedge=False,
               verbatim="pekerjaan yang harus saya handle sendiri"),
    ],
    edges=[
        UEdge(src_index=0, dst_index=1, kind="related_to", reason="same subject omzet"),
        UEdge(src_index=5, dst_index=0, kind="related_to", reason="index liar"),
    ],
)
delta = delta_from_understanding(u, turn=1, session_id="m2")
accepted, notes = verify_delta(delta, [("user", USER)], set())
gs = GraphStore()
gs.apply_delta(accepted)

check("3 klaim diterima (2 angka + 1 NON-angka — inilah nilai M2)", len(gs) == 3)
check("klaim non-numerik masuk graph (beban pribadi)",
      any(n["triple"]["predicate"]["label"] == "passes_through" for n in gs.nodes.values()))
check("edge index liar dibuang", len(accepted.edges) == 1)
check("id engine-empu (cl-t1-###)", all(i.startswith("cl-t1-") for i in gs.nodes))
check("hedge → modality hedged (18 juta 'sekitar')",
      any(n["modality"] == "hedged" for n in gs.nodes.values() if n["triple"]["value"] == 18.0))
check("predicate raw — tanpa kosakata domain",
      all(not n["triple"]["predicate"].get("normalized") for n in gs.nodes.values()))

print("[M2-2] drift report terstruktur (bukan string diff)")
OLD_CLAIMS = [
    {"value": 30.0, "tense": "past", "role": "current_revenue"},
    {"value": 18.0, "tense": "now", "role": "current_revenue"},
]
rep = build_drift_report(1, OLD_CLAIMS, accepted, notes)
check("struktur lengkap",
      all(k in rep for k in ("turn", "old", "new", "matched", "new_information",
                             "old_only", "verification", "risk")))
check("matched: 2 angka lama ditemukan di graph", len(rep["matched"]) == 2)
check("new_information: 1 klaim non-numerik (old pipeline tidak punya ini)",
      len(rep["new_information"]) == 1 and rep["new_information"][0]["predicate"] == "passes_through")
check("old_only kosong (graph tidak tertinggal dari old)", rep["old_only"] == [])
check("by_type tercatat", rep["new"]["by_type"].get("claim") == 3)

print("[M2-3] old_only terdeteksi bila graph gagal tangkap")
u_miss = UniversalUnderstanding(claims=[
    UClaim(subject="x", predicate="y", verbatim="Dulu omzet saya 30 juta", value=30.0, tense="past"),
])
acc_miss, _ = verify_delta(delta_from_understanding(u_miss, 2, "m2"), [("user", USER)], set())
rep2 = build_drift_report(2, OLD_CLAIMS, acc_miss, [])
check("old_only = 18 juta (graph tak tangkap)", len(rep2["old_only"]) == 1
      and rep2["old_only"][0]["value"] == 18.0)

print("[M2-4] may_indicate dari LLM tetap ditolak (boundary review M2)")
u_may = UniversalUnderstanding(
    claims=[UClaim(subject="pekerjaan", predicate="passes_through", object="saya",
                   verbatim="pekerjaan yang harus saya handle sendiri")],
    edges=[UEdge(src_index=0, dst_index=0, kind="may_indicate")],
)
acc3, notes3 = verify_delta(delta_from_understanding(u_may, 3, "m2"), [("user", USER)], set())
check("edge may_indicate ditolak", len(acc3.edges) == 0)
check("alasan penolakan tercatat", any("may_indicate" in n for n in notes3))

print("[M2-5] persist drift report di session")
s = Session(id="m2t", language="id", goal_text="x", graph_drift_reports=[rep])
d = dataclasses.asdict(s)
check("serialize", len(d["graph_drift_reports"]) == 1 and d["graph_drift_reports"][0]["turn"] == 1)

print("=" * 50)
print(f"HASIL: {PASS}/{PASS + FAIL} PASS — {FAIL} GAGAL")
sys.exit(0 if FAIL == 0 else 1)
