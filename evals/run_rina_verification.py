"""Verification of the predictions in internal-docs §8.4 on the Rina case (manual test persona).

Tests the 7 predictions made BEFORE the T1-T4 implementation:

  P1  TM-R04 does NOT match (quantified implication)     — it used to be "active" via proxy
  P2  TM-R01 matches (hypothetical intention)            — it used to never match
  P3  Coverage: rules_evaluated == rules_enabled         — used to be 12/25 (48%)
  P4  Every matched rule has a citation (applied_to)     — used to be CS-R06 without citation
  P5  Interventions from >1 constraint (multi-tier)      — used to be PRIMARY only
  P6  applied_to is not the `_KA_EFFECT` template        — used to be overwritten by a ready sentence
  P7  Tier-1 (0 LLM) really executes the rule

Run: .venv/bin/python evals/run_rina_verification.py
"""
import sys

sys.path.insert(0, ".")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

c = TestClient(app)
_h = c.get("/health").json()
print(f"[ENGINE] {_h['provider']} / {_h['model']}", flush=True)

TURNS = [
    # T1 - context + baseline (contains "harga kemahalan" = "prices too high", capacity, margin)
    "Saya Rina, freelance web designer. Revenue sekarang stabil Rp30 juta per bulan "
    "dari 3 klien retainer: klinik kecantikan Rp12 juta per bulan sudah 8 bulan, "
    "restoran Rp10 juta per bulan sudah 6 bulan, sekolah Rp8 juta per bulan kontrak "
    "per semester nilainya sekitar Rp48 juta. Target Rp60 juta per bulan dalam 90 hari. "
    "Tiga hal yang sedang saya perbaiki: follow up, karena saya pernah telat balas 5 hari "
    "dan lead klinik hilang ke kompetitor; pricing, price anchors ada di kepala Rp8jt "
    "focus dan Rp12jt scope penuh tapi tidak pernah ditulis, zero templates; akuisisi pasif, "
    "cuma 3 sampai 4 jam per minggu untuk prospect, sisanya delivery 34.5 jam per minggu.",
    # T2 - growth plan (contains the hypothetical "kalau bisa" = "if I could" + margin not yet certain)
    "Belum ada angka pisahan yang jelas. Tambahan Rp30 juta itu kalau bisa semuanya dari "
    "klien baru, karena klien lama sudah merasa cukup dengan paket mereka. Tapi saya tidak "
    "tahu berapa margin bersih, model untungnya belum pasti karena semuanya habis untuk "
    "delivery. Saya juga tidak pernah menawarkan tambahan layanan ke klien lama.",
    # T3 - real pipeline
    "Dalam 6 bulan terakhir yang masuk itu 4 lead. 2 dari rekomendasi klien klinik warm, "
    "1 dari Instagram DM, dan 1 dari acara networking. Yang jadi klien cuma 1 yaitu restoran. "
    "Yang 3 lainnya ditolak karena merasa harganya kemahalan atau tidak cocok dengan scope. "
    "Jadi conversion rate 25 persen.",
    # T4 - follow-up behavior (zero behavioral evidence)
    "Setelah kirim proposal saya diam saja. Tidak ada follow up sama sekali. Saya tidak tahu "
    "harus follow up seperti apa, takut terkesan pushy atau memaksa. Jadi saya menunggu saja "
    "mereka yang hubungi saya. Dan memang tidak ada yang pernah hubungi balik.",
    # T5 - price-objection handling
    "Tidak pernah coba hal lain. Begitu ada yang bilang kemahalan atau minta cicilan saya "
    "langsung berasumsi deal sudah gagal dan tidak saya tindak lanjuti lagi. Tidak pernah "
    "mencoba menawarkan paket yang lebih kecil atau termin pembayaran berbeda. Jadi memang "
    "zero attempt untuk menangani price objection.",
    # T6 - references & content (zero proactive)
    "Tidak pernah sama sekali meminta referensi atau minta dikenalkan. Alasannya sama, takut "
    "terkesan memaksa. Instagram hanya saya pakai upload portofolio, tidak pernah posting "
    "konten yang menawarkan jasa. Saya ikut satu acara networking bulan lalu, dapat 3 kartu "
    "nama, tapi tidak ada yang saya hubungi.",
    # T7 - consequences
    "Kalau tetap 0 lead baru, klien sekolah hilang duluan akhir tahun, itu Rp8 juta per bulan "
    "hilang. Klinik juga mulai bosan. Kalau klinik pergi tinggal restoran Rp10 juta. Jadi "
    "sebenarnya darurat keuangan dalam 3 sampai 6 bulan, tapi saya belum merasa mendesak.",
]

r = c.post("/session", json={
    "goal_text": "Rp60 juta per bulan dalam 90 hari dari baseline Rp30 juta retainer web design",
    "language": "id",
})
sid = r.json()["session_id"]
print(f"session: {sid}", flush=True)
for i, t in enumerate(TURNS, 1):
    j = c.post(f"/session/{sid}/message", json={"text": t}).json()
    print(f"  turn {i}: kind={j.get('kind')} ev+={len(j.get('evidence_delta') or [])}", flush=True)

d = c.post(f"/session/{sid}/finalize").json()
ka = d.get("knowledge_activation") or {}
cov = ka.get("coverage") or {}
t1 = set(ka.get("tier1_matched") or [])
t2 = set(ka.get("tier2_matched") or [])
matched = t1 | t2

print("\n=== DIAGNOSIS ===")
print("PRIMARY :", d["primary_constraint_id"], "| conf:", d["confidence"])
print("SPECTRUM:", (d.get("decision_spectrum") or {}).get("level"))
print("TIER-1  :", sorted(t1))
print("TIER-2  :", sorted(t2))
print("BLOCKED :", ka.get("blocked_verdicts"))
print("COVERAGE:", {k: cov.get(k) for k in ("rules_enabled", "tier1_evaluated",
                                             "rules_evaluated", "tier2_requested",
                                             "tier2_returned")})
print("tier2_missing:", cov.get("tier2_missing"))
print("IVN     :", [(i["id"], i.get("for_constraint")) for i in ka.get("interventions") or []])
print("\napplied_to per matched rule:")
for k in (d.get("reasoning_trace") or {}).get("knowledge_activated") or []:
    print(f"  {k['item_id']:8s} «{(k.get('applied_to') or '')[:70]}»")

# ---------------------------- PREDICTIONS ----------------------------
print("\n=== VERIFIKASI PREDIKSI ===")
checks = []
checks.append(("P1 TM-R04 TIDAK match (implikasi terkuantifikasi)", "TM-R04" not in matched))
checks.append(("P2 TM-R01 match (hypothetical intention)", "TM-R01" in matched))
checks.append((
    f"P3 coverage penuh ({cov.get('rules_evaluated')}/{cov.get('rules_enabled')})",
    bool(cov.get("rules_enabled")) and cov.get("rules_evaluated") == cov.get("rules_enabled"),
))
k_rows = (d.get("reasoning_trace") or {}).get("knowledge_activated") or []
checks.append(("P4 setiap matched rule punya sitasi",
               all((k.get("applied_to") or "").strip() for k in k_rows) and bool(k_rows)))
ivn_scope = {i.get("for_constraint") for i in ka.get("interventions") or []}
checks.append((f"P5 intervensi multi-tier ({sorted(x for x in ivn_scope if x)})", len(ivn_scope) > 1))
_canned = ("keluhan tanpa implikasi biaya terukur", "meeting/balasan tanpa komitmen behavioral")
checks.append(("P6 applied_to bukan template _KA_EFFECT",
               not any(c in (k.get("applied_to") or "") for k in k_rows for c in _canned)))
checks.append((f"P7 tier-1 dievaluasi tanpa LLM ({cov.get('tier1_evaluated')} rule, "
               f"{len(t1)} match)", cov.get("tier1_evaluated", 0) >= 8))

failed = 0
for label, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}")
    failed += 0 if ok else 1
print(f"\n{len(checks) - failed}/{len(checks)} prediksi terpenuhi")
sys.exit(1 if failed else 0)
