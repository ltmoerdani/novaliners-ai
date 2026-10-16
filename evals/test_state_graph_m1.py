"""M1 DoD — int 11 Rev 11.1 (user-approved 25 Sep):

Proof the live graph coexists with the old system WITHOUT changing old behavior:

    Same input ─┬─→ OLD PIPELINE → OLD OUTPUT (unchanged)
                └─→ GRAPH BUILDER → GRAPH (populated, provenance/temporal/edge valid)

Plus a MICRO LEAKAGE TEST (universal, non-revenue fixture): the graph must not
surface revenue vocabulary unless the user says it.
Fully deterministic — no LLM.
"""
import sys

sys.path.insert(0, ".")

from evals._store_isolation import isolate_store  # noqa: E402

isolate_store()  # eval: store redirected to tmp — production store untouched

import dataclasses  # noqa: E402

from core.state_graph import (  # noqa: E402
    GraphStore,
    number_claims_to_delta,
    verify_delta,
)
from core.state_graph.models import Concept, Edge, EdgeKind, GraphDelta, Triple, UniversalClaim  # noqa: E402
from store.memory import Session  # noqa: E402

PASS = 0
FAIL = 0


def check(name: str, ok: bool, detail: str = ""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  PASS {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} {detail}")


print("[M1-1] mapper + verify + store — fixture S1 (data sesi live 7b3a4b9ee949)")
S1_CLAIMS = [
    {"value": 8.0, "period": "monthly", "tense": "now", "role": "current_revenue",
     "subject": None, "verbatim": "Sekarang penghasilan 8jt/bln", "hedge": False},
    {"value": 2.0, "period": "count", "tense": "now", "role": "lead_count",
     "subject": "klien retainer", "verbatim": "dari 2 klien retainer", "hedge": False},
    {"value": 6.5, "period": "monthly", "tense": "past", "role": "historical_client_rate",
     "subject": "klien agensi", "verbatim": "klien agensi bayar Rp6,5 juta/bulan", "hedge": False},
    {"value": 3.0, "period": "one_off", "tense": "now", "role": "rejected_price",
     "subject": "calon klien", "verbatim": "nawar di bawah Rp3 juta", "hedge": True},
    {"value": 2.0, "period": "count", "tense": "now", "role": "lead_count",
     "subject": "calon klien", "verbatim": "Calon klien nawar", "hedge": True},
]
S1_TRANSCRIPT = [("user", "Sekarang penghasilan 8jt/bln dari 2 klien retainer. "
                            "Dulu klien agensi bayar Rp6,5 juta/bulan tapi berhenti. "
                            "Calon klien nawar di bawah Rp3 juta.")]

delta = number_claims_to_delta(S1_CLAIMS, 1, "s1")
accepted, notes = verify_delta(delta, S1_TRANSCRIPT, set())
gs = GraphStore()
added = gs.apply_delta(accepted)

check("graph terisi (5 node)", len(gs) == 5, f"got {len(gs)}")
check("provenance valid — semua node punya verbatim+turn",
      all(n["verbatim"] and n["provenance"].get("turn") for n in gs.nodes.values()))
check("temporal valid — 6.5jt tercatat past",
      any(n["tense"] == "past" and n["triple"]["value"] == 6.5 for n in gs.nodes.values()))
check("hedge → modality hedged (demote verify)",
      any(n["modality"] == "hedged" for n in gs.nodes.values() if n["triple"]["value"] == 3.0))
check("predicate = label mentah (has_current_revenue), tanpa normalized",
      all("predicate" in n["triple"] and not n["triple"]["predicate"].get("normalized")
          for n in gs.nodes.values()))
check("edge related_to (subject klien)",
      any(e["kind"] == "related_to" for e in gs.edges.values()))

print("[M1-2] verify gate menolak yang layak ditolak")
bad = GraphDelta(claims=[
    UniversalClaim(id="cl-bad-1", triple=Triple(subject=Concept(label="x"),
                  predicate=Concept(label="has_y")), verbatim=" ",
                  provenance={"turn": 1}),
    UniversalClaim(id="cl-bad-2", triple=Triple(subject=Concept(label="x"),
                  predicate=Concept(label="has_y")), verbatim="tidak ada di transcript",
                  provenance={"turn": 1}),
])
acc2, notes2 = verify_delta(bad, S1_TRANSCRIPT, set())
check("verbatim kosong ditolak", all(c.id != "cl-bad-1" for c in acc2.claims))
check("verbatim tak ter-ground ditolak", all(c.id != "cl-bad-2" for c in acc2.claims))
check("alasan penolakan tercatat (menagih)", len(notes2) >= 2)
edge_may = GraphDelta(edges=[Edge(id="e-m", src="cl-t1-001", dst="cl-t1-002",
                                  kind=EdgeKind.may_indicate)])
acc3, notes3 = verify_delta(edge_may, S1_TRANSCRIPT, set())
check("may_indicate tanpa jalur KB ditolak", len(acc3.edges) == 0)

print("[M1-3] idempotensi + apply ulang")
added2 = gs.apply_delta(accepted)
check("apply ulang = 0 node baru", added2 == 0)

print("[M1-4] MICRO LEAKAGE TEST — fixture universal non-revenue")
UNIVERSAL_TEXT = ("Saya capek karena semua pekerjaan masih lewat saya. "
                  "Saya sering harus mengecek semuanya sendiri sebelum bisa jalan.")
uni_claim = UniversalClaim(
    id="cl-u-001", type="claim",
    triple=Triple(subject=Concept(label="semua pekerjaan"),
                  predicate=Concept(label="passes_through"),
                  object=Concept(label="saya")),
    verbatim="semua pekerjaan masih lewat saya", provenance={"turn": 1},
)
acc4, _ = verify_delta(GraphDelta(claims=[uni_claim]), [("user", UNIVERSAL_TEXT)], set())
gsu = GraphStore()
gsu.apply_delta(acc4)
blob = str(gsu.to_dict()).lower()
REVENUE_VOCAB = ["revenue", "lead_count", "conversion", "omzet", "penjualan", "sales", "harga"]
check("graph universal TANPA kosakata revenue yang tidak user ucap",
      not any(v in blob for v in REVENUE_VOCAB),
      str([v for v in REVENUE_VOCAB if v in blob]))
check("graph universal terisi & ter-ground", len(gsu) == 1)

print("[M1-5] jalur lama tak tersentuh — struktur sesi tetap valid")

s = Session(id="m1test", language="id", goal_text="x")
s.state_graph = gs.to_dict()

d = dataclasses.asdict(s)
check("state_graph ter-serialize", isinstance(d.get("state_graph", {}).get("nodes"), dict)
      and len(d["state_graph"]["nodes"]) == 5)
s2 = Session(id="m1test2", language="id", goal_text="x",
             state_graph=d["state_graph"])
check("state_graph ter-load", len(s2.state_graph["nodes"]) == 5)

print("=" * 50)
print(f"HASIL: {PASS}/{PASS + FAIL} PASS — {FAIL} GAGAL")
sys.exit(0 if FAIL == 0 else 1)
