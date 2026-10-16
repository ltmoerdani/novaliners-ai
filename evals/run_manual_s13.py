"""Manual-test automation: scenario #1 (real evidence) & #3 (future promise).

Scenario #1: a consultant with transactional evidence → confidence > 0.5,
             rules applied are small/medium (TM-R01/R07 must NOT be active together).
Scenario #3: the user speaks a future promise → the engine must demand behavioral evidence
             (questions demanding real numbers/events), TM-R01 active at the end.
"""
import json
import sys
import time

sys.path.insert(0, ".")
from fastapi.testclient import TestClient

from app.main import app

c = TestClient(app)

_h = c.get("/health").json()
print(
    f"[ENGINE] provider={_h['provider']} model={_h['model']} "
    f"status={_h['status']} {_h.get('detail', '')}",
    flush=True,
)

def run(label: str, goal: str, turns: list[str]) -> dict:
    r = c.post("/session", json={"goal_text": goal, "language": "id"})
    sid = r.json()["session_id"]
    print(f"\n########## {label} | session={sid}", flush=True)
    t0 = time.time()
    for i, t in enumerate(turns, 1):
        j = c.post(f"/session/{sid}/message", json={"text": t}).json()
        print(f"\n--- TURN {i} kind={j['kind']}", flush=True)
        for ev in j["evidence_delta"]:
            gap = " [GAP]" if ev.get("is_gap") else ""
            print(f"    EV {ev['level']:14s}{gap} | {ev['signal'][:90]}", flush=True)
        print(f"    Q: {(j['next_question'] or '')[:140]}", flush=True)
    d = c.post(f"/session/{sid}/finalize").json()
    print(f"\n=== DIAGNOSIS {label} ({time.time()-t0:.0f}s) ===", flush=True)
    print("BLOCKING :", d["primary_constraint_id"], "|", d["primary_constraint"][:110], flush=True)
    print("CONF     :", d["confidence"], "| rules:", d.get("knowledge_rules_applied"), flush=True)
    print("RANKING  :", [(h["constraint_id"], h["score"]) for h in d["hypothesis_ranking"]], flush=True)
    return d

# ---- SCENARIO 1: real transactional evidence ----
s1 = run(
    "SKENARIO 1 (bukti nyata)",
    "Rp30 juta/bulan dari jasa konsultan pemasaran",
    [
        "Saya konsultan pemasaran B2B sudah 3 tahun. Tahun lalu revenue Rp280 juta, "
        "klien tetap 4 perusahaan manufaktur, retainer rata-rata Rp5 juta/bulan per klien.",
        "Q1 lalu saya tutup 2 deal baru masing-masing Rp8 juta/bulan kontrak setahun. "
        "Cara closing: demo hasil dashboard klien lama + trial 2 minggu berbayar, 6 dari 10 proposal jadi.",
        "Untuk cari klien baru: 15 cold email per minggu, balasan sekitar 2, jadi meeting 1. "
        "Sebagian besar balasan menolak karena harga, padahal saya sudah turunkan ke Rp4 juta.",
        # F3+ (18 Sep): the old scenario never answered the target probe (asked 2×,
        # 2× material GAP) → gap_penalty destroyed the confidence (0.005) and the
        # invariant ≥0.5 failed not because the evidence was weak, but because the
        # script leaked the GAP. An explicit current + target closes it fairly.
        "Sekarang saya stabil Rp30 juta/bulan. Target 12 bulan ke depan saya Rp50 juta/bulan, "
        "rencananya revisi penawaran dan naikkan closing rate dari 6/10 jadi 8/10.",
        "Bukti paling keras: invoice retainer bulan September sudah dibayar penuh — "
        "transfer Rp30 juta masuk rekening 2 Oktober, bukti transfer dan kontrak "
        "tersimpan. Dua klien lain bayar tepat tanggal 5 setiap bulan.",
    ],
)

# ---- SCENARIO 3: future promise (hypothetical intention) ----
s3 = run(
    "SKENARIO 3 (janji masa depan)",
    "Rp10 juta/bulan dari bisnis online",
    [
        "Saya sedang mempersiapkan diri. Nanti kalau produknya sudah jadi, saya yakin akan laris. "
        "Saya berencana pasang iklan Meta Ads sebesar-besarnya begitu launching.",
        "Rencananya saya akan buat kelas online. Kalau sudah launching, target saya langsung "
        "100 pembeli di bulan pertama. Saya nanti akan posting konten setiap hari biar viral.",
        "Untuk saat ini belum ada penjualan, belum ada percakapan dengan calon pembeli. "
        "Tapi saya optimistis, karena idenya bagus dan pasar pasti butuh.",
    ],
)

print("\n================ VERDICT ================", flush=True)
ok1 = s1["confidence"] >= 0.5 and not ({"TM-R01", "TM-R07"} <= set(s1.get("knowledge_rules_applied", [])))
print(
    f"S1 bukti nyata : conf={s1['confidence']} rules={s1['knowledge_rules_applied']} "
    f"-> {'PASS' if ok1 else 'CHECK'}",
    flush=True,
)
r3 = set(s3.get("knowledge_rules_applied", []))
ok3 = s3["confidence"] < 0.6 and "TM-R01" in r3
print(
    f"S3 janji masa depan: conf={s3['confidence']} rules={s3['knowledge_rules_applied']} "
    f"-> {'PASS' if ok3 else 'CHECK'}",
    flush=True,
)
json.dump({"s1": s1, "s3": s3}, open("eval_manual_s13.json", "w"), indent=2, ensure_ascii=False)
print("Saved -> eval_manual_s13.json", flush=True)
