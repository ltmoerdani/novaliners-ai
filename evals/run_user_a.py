"""Z.AI E2E test: User A trajectory (freelancer who resigned after 8 years).
Output to stdout (unbuffered) — run from the mvp/ folder."""
import json
import sys
import time

sys.path.insert(0, ".")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

c = TestClient(app)

_h = c.get("/health").json()
print(
    f"[ENGINE] provider={_h['provider']} model={_h['model']} "
    f"status={_h['status']} {_h.get('detail', '')}",
    flush=True,
)

r = c.post("/session", json={"goal_text": "Rp20 juta/bulan dari freelance", "language": "id"})
sid = r.json()["session_id"]
print(f"[t=0] session={sid}", flush=True)

turns = [
    "Saya baru resign setelah bekerja 8 tahun sebagai marketing manager. "
    "Saya belum punya client sama sekali.",
    "Saya bisa bikin strategi marketing, konten, dan kelola iklan. "
    "Belum pernah packaging jadi jasa, belum tahu harus charge berapa.",
    "Belum pernah outreach. Saya mikir harus bikin website dan Instagram dulu biar kelihatan profesional.",
]

t0 = time.time()
for i, t in enumerate(turns, 1):
    r2 = c.post(f"/session/{sid}/message", json={"text": t}, timeout=120)
    j = r2.json()
    print(f"\n--- TURN {i} (+{time.time()-t0:.1f}s) kind={j['kind']}", flush=True)
    for tag in j["intent_tags"]:
        print(
            f"    TAG {tag['kind']:10s} conf={tag['confidence']:.2f} "
            f"| {tag['normalized'][:70]}",
            flush=True,
        )
    for ev in j["evidence_delta"]:
        print(f"    EV  {ev['level']:14s} | {ev['signal'][:70]}", flush=True)
    print(f"    Q: {(j['next_question'] or '')[:120]}", flush=True)

r3 = c.post(f"/session/{sid}/finalize", timeout=180)
d = r3.json()
print(f"\n=== DIAGNOSIS (final, total {time.time()-t0:.1f}s) ===", flush=True)
print("WHERE   :", d["where_you_are"], flush=True)
print("BLOCKING:", d["primary_constraint"], f"({d['primary_constraint_id']})", flush=True)
print("SECONDARY:", d["secondary_constraints"], flush=True)
print("DO NOT  :", d["do_not"], flush=True)
print("NBA     :", d["next_best_action"], flush=True)
print("METRIC  :", d["success_metric"], flush=True)
print("KNOW-WHEN:", d["well_know_when"], flush=True)
print(
    "CONFIDENCE:", d["confidence"], "| ranking:",
    [(h["constraint_id"], h["score"]) for h in d["hypothesis_ranking"]],
    flush=True,
)

with open("eval_user_a_result.json", "w") as f:
    json.dump(d, f, indent=2, ensure_ascii=False)
print("\nSaved -> eval_user_a_result.json", flush=True)
