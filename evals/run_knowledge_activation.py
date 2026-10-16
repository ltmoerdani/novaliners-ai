"""Multi-context E2E eval — WP4 (research: do not single-benchmark; ERPBench 2609.04667).

3 cross-domain scenarios — each exercising a DIFFERENT knowledge branch:
  K1 SaaS Retention (HK)   : heavy onboarding before value + churn → HK-* / R7.* rules
  K2 B2B Qualification (CS): RFP + junior contact without a decision-maker → CS-R03/R06
  K3 TM regression (S3)    : a future promise → TM-R01 stays active, conf < 0.6

Needs a live LLM provider (not mock). Run: .venv/bin/python evals/run_knowledge_activation.py
"""
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
if _h.get("provider") == "mock":
    print("SKIP: provider mock — eval ini mengukur kualitas matcher, butuh LLM live.")
    sys.exit(0)


def run(label: str, goal: str, turns: list[str]) -> dict:
    r = c.post("/session", json={"goal_text": goal, "language": "id"})
    sid = r.json()["session_id"]
    t0 = time.time()
    for t in turns:
        c.post(f"/session/{sid}/message", json={"text": t})
    d = c.post(f"/session/{sid}/finalize").json()
    ka = d.get("knowledge_activation") or {}
    print(f"\n### {label} ({time.time()-t0:.0f}s)", flush=True)
    print("PRIMARY  :", d["primary_constraint_id"], "| conf:", d["confidence"], flush=True)
    print("TIER-1 (predicate, 0 LLM):", ka.get("tier1_matched"), flush=True)
    print("TIER-2 (LLM, tersitasi)  :", ka.get("tier2_matched"), flush=True)
    cov = ka.get("coverage") or {}
    print(
        f"COVERAGE: enabled={cov.get('rules_enabled')} evaluated={cov.get('rules_evaluated')} "
        f"tier1={cov.get('tier1_evaluated')} "
        f"tier2={cov.get('tier2_returned')}/{cov.get('tier2_requested')} "
        f"missing={len(cov.get('tier2_missing') or [])}",
        flush=True,
    )
    print("FLAGS    :", ka.get("flags"), "| BLOCKED:", ka.get("blocked_verdicts"), flush=True)
    print("ANTI     :", ka.get("anti_patterns"), flush=True)
    print("IVN      :", [i["id"] for i in ka.get("interventions", [])], flush=True)
    print("RANK TOP5:", [(h["constraint_id"], h["score"]) for h in d["hypothesis_ranking"][:5]], flush=True)
    return d


# K1 — SaaS retention (Hooked domain; before WP: no active source for R7.*)
k1 = run(
    "K1 SaaS Retention (HK)",
    "Menstabilkan MRR SaaS Rp25 juta/bulan",
    [
        "Saya founder SaaS tools operasional, 80 pelanggan, MRR Rp25 juta, akuisisi via Meta Ads.",
        "Masalahnya pelanggan cepat pergi: churn bulanan 10%. User baru harus lewat onboarding "
        "8 langkah + training 2 sesi sebelum bisa pakai fitur utama. Banyak yang berhenti di tengah.",
        "Bulan lalu 8 dari 80 pelanggan berhenti. Dari 20 pendaftar baru, cuma 6 yang selesai "
        "onboarding sampai dapat hasil pertama. Sisanya tidak pernah login lagi setelah minggu pertama.",
        "Tim support sibuk menjawab pertanyaan langkah-langkah setup terus. Saya pikir perlu tambah "
        "budget iklan biar pendaftar baru lebih banyak menutup yang pergi.",
    ],
)

# K2 — B2B qualification (domain Challenger Sale)
k2 = run(
    "K2 B2B Qualification (CS)",
    "Rp40 juta/bulan dari konsultasi ops manufaktur",
    [
        "Saya konsultan operasional manufaktur. Sering dapat RFP dan diajak tender oleh staf "
        "purchasing perusahaan besar. Semua RFP saya ikuti, win rate rendah.",
        "Pesan penawaran saya sama untuk semua orang — deck 'tentang kami' + fitur layanan. "
        "Saat presentasi, klien manggut-manggut setuju: 'persis masalah kami'. Tapi deal tidak jadi-jadi.",
        "Bulan lalu 5 RFP, 0 deal. Kontak saya di klien semuanya staf junior purchasing, belum "
        "pernah bicara dengan direksi atau pemilik. Deal terakhir macet katanya 'menunggu atasan'.",
        "Respons saya kalau diminta diskon: langsung saya turunkan harga biar menang tender.",
    ],
)

# K3 — TM regression (S3 from run_manual_s13, condensed)
k3 = run(
    "K3 Regresi TM (janji masa depan)",
    "Rp10 juta/bulan dari bisnis online",
    [
        "Saya sedang mempersiapkan diri. Nanti kalau produknya jadi, saya yakin laris. "
        "Berencana pasang Meta Ads besar-besaran begitu launching.",
        "Rencananya kelas online, target 100 pembeli bulan pertama. Belum ada penjualan "
        "dan belum ada percakapan dengan calon pembeli. Tapi saya optimistis.",
    ],
)

print("\n================ VERDICT (multi-konteks) ================", flush=True)
ka1 = k1.get("knowledge_activation") or {}
ka2 = k2.get("knowledge_activation") or {}
ka3 = k3.get("knowledge_activation") or {}
ok_k1 = (
    not ka1.get("degraded", True)
    and (
        bool(ka1.get("tier1_matched") or ka1.get("tier2_matched"))
        or any("R7." in f for f in (ka1.get("flags") or []) + (ka1.get("blocked_verdicts") or []))
        or any(h["constraint_id"].startswith("R7") for h in k1["hypothesis_ranking"][:5])
    )
)
ok_k2 = (
    not ka2.get("degraded", True)
    and (
        any(
            r.startswith("CS-")
            for r in (ka2.get("tier1_matched") or []) + (ka2.get("tier2_matched") or [])
        )
        or any(
            "C6.1" in f or "M3.4" in f
            for f in (ka2.get("flags") or []) + (ka2.get("blocked_verdicts") or [])
        )
    )
)
# T4: coverage must be reported & unevaluated rules must be visible
for lbl, k, ka in (("K1", k1, ka1), ("K2", k2, ka2), ("K3", k3, ka3)):
    cov = ka.get("coverage") or {}
    print(
        f"COVERAGE {lbl}: enabled={cov.get('rules_enabled')} evaluated={cov.get('rules_evaluated')} "
        f"tier2_missing={len(cov.get('tier2_missing') or [])} fail_groups={cov.get('llm_failed_groups')}",
        flush=True,
    )
ok_k3 = k3["confidence"] < 0.6 and "TM-R01" in set(k3.get("knowledge_rules_applied", []))
print(f"K1 HK retention  : {'PASS' if ok_k1 else 'CHECK'} (degraded={ka1.get('degraded')})", flush=True)
print(f"K2 CS qualif     : {'PASS' if ok_k2 else 'CHECK'} (degraded={ka2.get('degraded')})", flush=True)
print(f"K3 regresi TM-R01: {'PASS' if ok_k3 else 'CHECK'}", flush=True)
sys.exit(0 if (ok_k1 and ok_k2 and ok_k3) else 1)
