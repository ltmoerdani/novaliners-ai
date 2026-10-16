"""DoD Smoke Test — direct audit of internal-docs (Appendix I — Definition of Done).

Replays the Rina scenario (7 user turns, rich evidence) via TestClient — NEW CODE,
not a stale server — then audits the 5 P0 Invariants + indicators of the 5 DoD gates.
Run from the mvp/ folder: .venv/bin/python evals/run_dod_smoke.py
"""
import json
import re as _re
import sys
import time

sys.path.insert(0, ".")

from fastapi.testclient import TestClient  # noqa: E402

from agents.diagnosis import _guard_experiment_population  # noqa: E402
from app.main import app  # noqa: E402
from core.schema.evidence import EvidenceItem  # noqa: E402
from domains.revenue.schema.artifact import DiagnosisArtifact  # noqa: E402
from evals.test_artifact_integrity import (  # noqa: E402
    stamp_artifact,
    verify_artifact_fresh,
)

c = TestClient(app)

_h = c.get("/health").json()
print(f"[ENGINE] provider={_h['provider']} model={_h['model']} status={_h['status']}", flush=True)

GOAL = (
    "Saya Rina, freelance web designer. Revenue sekarang stabil Rp30 juta/bulan "
    "dari 3 klien retainer: klinik kecantikan Rp12 juta per bulan (berjalan 8 bulan), "
    "restoran Rp10 juta per bulan (berjalan 6 bulan), sekolah Rp8 juta per bulan — "
    "kontrak per semester nilainya sekitar Rp48 juta. Target Rp60 juta/bulan dalam 90 hari. "
    "3 hal yang sedang saya perbaiki: (1) follow-up — saya pernah telat balas 5 hari dan lead "
    "klinik hilang ke kompetitor; (2) pricing — price anchors ada di kepala (Rp8jt focus, "
    "Rp12jt full scope) tapi tidak pernah ditulis, zero templates; (3) akuisisi pasif — cuma "
    "3-4 hours/week untuk prospect, sisanya untuk delivery 34.5 hours per week."
)

TURNS = [
    # turn 0 (faithful to run-5): the full goal text is sent as the first message —
    # key facts (Rp30M, 34.5 hours, 3-4 hours prospecting) MUST reach the ledger.
    GOAL,
    # turn 2: funnel + eligible population
    "Dalam 90 hari terakhir sekitar 7-8 inquiry masuk — 2-3 dari Instagram (sebulan terakhir "
    "saya mulai posting lagi), sisanya referral. Yang bayar: nol. Yang eksplisit tanya harga ada "
    "5-6. Tiga titik bocor berbeda: (1) inquiry Instagram saya balas pertanyaan balik tanpa pernah "
    "sebut angka, jalan 2-3 pesan lalu menghilang — termasuk pemilik brand skincare yang mau "
    "launching, dia sendiri yang bilang deadline-nya; (2) 2 prospek LinkedIn saya kasih angka "
    "langsung (Rp9 juta dan Rp7 juta), dua-duanya diam setelah dengar harga; (3) inquiry referral "
    "saya telat balas sampai 5 hari, satu hilang ke kompetitor.",
    # turn 4: old-client vs new-lead pattern
    "Klien lama semuanya jalur pendek: sudah kenal kerja saya lewat referral orang yang percaya "
    "dan sudah lihat portofolio, jadi deal di WhatsApp cuma beberapa hari, tanpa dokumen. "
    "Bandingkan dengan inquiry baru: skincare tanya harga, saya tidak pernah sebut angka, dia "
    "hilang setelah 2-3 pesan; dua prospek LinkedIn saya kasih angka Rp9 juta dan Rp7 juta tanpa "
    "konteks apa pun, dua-duanya diam. Jadi polanya: klien lama deal karena bukti dan kepercayaan "
    "sudah ada sebelum harga; lead baru mati di percakapan komersial yang tidak pernah tuntas — "
    "entah karena angka tidak keluar, atau keluar tanpa konteks.",
    # turn 6: zero costs
    "Pengeluaran untuk sisi bisnis: praktis nol. Tidak ada iklan berbayar sama sekali. Tools yang "
    "pernah saya bayar/langgani: tidak ada yang aktif — template penawaran di Google Docs gratis, "
    "tidak pernah dipakai. Asisten/freelancer: tidak pernah. Kursus/coaching: tidak ada. "
    "Legal/kontrak: tidak ada, semua kesepakatan lewat WhatsApp tanpa dokumen.",
    # turn 8: a measurable channel
    "Yang menghasilkan respons terukur hanya Instagram aktif: waktu saya rajin posting (sekitar "
    "setahun lalu), inquiry masuk 2-3 per bulan; saya berhenti posting, inquiry ikut berhenti; "
    "bulan lalu mulai posting lagi 2 kali, dan muncul 1-2 inquiry Instagram — persis seperti dulu. "
    "LinkedIn outreach 2 kali — 0 balasan.",
    # turn 10: micro case + the number+context contrast
    "Kasus terakhir (10 hari lalu): dia DM 'kak, website toko online berapa?' — saya balas tanpa "
    "angka: 'boleh tahu produknya dan referensi desain yang disukai?' — dia jawab sekali — saya "
    "balas 'oke ditunggu' — diam sampai sekarang. Pola skincare 3 minggu lalu persis sama. Dan "
    "yang sukses kebalikannya: klien klinik minta pekerjaan out-of-scope, saya langsung sebut "
    "Rp1,5 juta dengan alasan jelas — dibayar penuh tanpa nego. Jadi kontrasnya jelas: angka + "
    "konteks + saya yang inisiatif = tuntas; angka tidak keluar = hilang; angka tanpa konteks = diam.",
    # turn 12: the lead's exact answer
    "Jawaban persisnya: 'produk skincare, mau launching akhir bulan depan, sekarang order masih "
    "lewat DM dan kacau banget. Referensi nanti saya kirim ya.' Dia menyebut deadline launching "
    "sendiri, tapi tidak menyebut budget sama sekali. Setelah janji kirim referensi itu dia hilang, "
    "sudah sekitar 3 minggu.",
]

results: list[tuple[str, str, str]] = []  # (invariant, PASS/FAIL, detail)

def check(name: str, ok: bool, detail: str = ""):
    results.append((name, "PASS" if ok else "FAIL", detail))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" | {detail}" if detail else ""), flush=True)


# ================= E2E =================
r = c.post("/session", json={"goal_text": GOAL, "language": "id"})
sid = r.json()["session_id"]
print(f"[t=0] session={sid}", flush=True)

t0 = time.time()
for i, t in enumerate(TURNS, 1):
    r2 = c.post(f"/session/{sid}/message", json={"text": t}, timeout=180)
    j = r2.json()
    print(
        f"--- TURN {i} (+{time.time()-t0:.1f}s) kind={j['kind']} "
        f"ev_delta={len(j['evidence_delta'])}",
        flush=True,
    )

r3 = c.post(f"/session/{sid}/finalize", timeout=300)
assert r3.status_code == 200, r3.text
d = r3.json()
# era-7 (internal-docs §9): stamp the KB fingerprint — an artifact without it does
# not count as verification evidence (the stale-artifact lesson 10:54 vs commit 12:12).
stamp_artifact(d)
print(f"[KB FINGERPRINT] rules={d['kb_fingerprint']['rules_enabled']} "
      f"items={d['kb_fingerprint']['item_count']} "
      f"sha={d['kb_fingerprint']['sha256']}", flush=True)
with open("eval_dod_smoke_result.json", "w") as f:
    json.dump(d, f, indent=2, ensure_ascii=False)
print(f"\n=== DIAGNOSIS done in {time.time()-t0:.1f}s — saved eval_dod_smoke_result.json ===\n", flush=True)

art = DiagnosisArtifact(**d)

# ================= INVARIANT 1: never corrupt explicit facts =================
print("\n[P0-1] Never corrupt explicit facts", flush=True)
s = art.revenue_state
check("current = 30", abs((s.current_monthly or 0) - 30) < 0.01, f"got {s.current_monthly}")
check("target = 60", abs((s.target_monthly or 0) - 60) < 0.01, f"got {s.target_monthly}")
check("gap = 30", abs((s.gap_monthly or 0) - 30) < 0.01, f"got {s.gap_monthly}")
check(
    "delivery = 34.5 (bukan 4)",
    abs((s.delivery_hours_per_week or 0) - 34.5) < 0.01,
    f"got {s.delivery_hours_per_week}",
)
acq = s.acquisition_hours_per_week
check("acquisition 3-4 (bukan 5.5 sisa kapasitas)", acq is not None and 3.0 <= acq <= 4.0, f"got {acq}")
all_notes = json.dumps(d, ensure_ascii=False)
check("tidak ada derivasi linear '±1 retainer butuh'", "±1 retainer butuh" not in all_notes)

# ================= INVARIANT 2: never manufacture evidence =================
print("\n[P0-2] Never manufacture evidence", flush=True)
nba = (art.next_best_action or "") + " " + " ".join(
    str(getattr(x, "text", x)) for x in art.day_by_day
)
# the evidence ledger lives in the session store (not in the artifact)
sess = json.load(open(f"store/sessions/{sid}.json"))
ev_items = [EvidenceItem(**e) for e in sess.get("evidence", [])]
class _D:  # duck-typed draft for the guard
    next_best_action = art.next_best_action or ""
    first_step_today = art.first_step_today or ""
    day_by_day = art.day_by_day
    outreach_script = art.outreach_script or ""
note = _guard_experiment_population(_D, ev_items)  # type: ignore[arg-type]
check("population guard tidak false-flag", note is None or not _re.search(r"DM\s+\d", note),
      (note or "BERSIH")[:120].replace("\n", " "))
stated = _re.search(r"eligible sample:\s*(\d+)", nba + " " + (art.well_know_when or ""), _re.I)
if stated:
    check("jumlah subject di NBA konsisten dengan bukti (≤2 lead eligible)", int(stated.group(1)) <= 2,
          f"stated {stated.group(1)}")
else:
    check("NBA menyebut 'eligible sample' eksplisit", "eligible" in nba.lower() or "lead" in nba.lower(),
          "tidak ada frase sample — cek manual")

# ================= INVARIANT 3: never confuse evidence with causality =================
print("\n[P0-3] Never confuse evidence with causality", flush=True)
ch = art.causal_hypothesis
check("causal_status ada", bool(getattr(ch, "causal_status", "")), getattr(ch, "causal_status", "—"))
attr = getattr(ch, "user_attributed", [])
# P0-3 passes either way: (a) attribution is separated from proven, OR (b) the ledger no
# longer contains any causal claim at all (LLM rewording removed the Indonesian causal
# word 'karena' — the keyword the checks below search for) —
# both mean evidence ≠ causality is preserved.
causal_leak = any("karena" in p.lower() for p in ch.proven)
check("insiden atribusi terpisah ATAU ledger bebas klaim kausal",
      len(attr) > 0 or not causal_leak, f"n_attributed={len(attr)}, causal_leak={causal_leak}")
proven_txt = " ".join(ch.proven)
# Phase I (17 Sep): previously `... or True` — a tautology that could not fail. Now a real check.
check("proven hanya kejadian murni (tanpa 'karena')", "karena" not in proven_txt.lower(),
      f"n_proven={len(ch.proven)}")
check("klaim kausal tetap di still_unproven", len(ch.still_unproven) > 0, f"n={len(ch.still_unproven)}")

# ================= INVARIANT 4: never violate readiness =================
print("\n[P0-4] Never recommend action violating readiness", flush=True)
check(
    "capacity_utilization > 0.8 terdeteksi",
    (s.capacity_utilization or 0) > 0.8,
    f"{s.capacity_utilization}",
)
check("readiness scale = NO", s.readiness.get("scale") == "NO", str(s.readiness.get("scale")))
check("REVENUE CEILING muncul", "CEILING" in all_notes or "REVENUE CEILING" in all_notes)
nba_low = nba.lower()
bad_scale = _re.search(
    r"(cari|reach|prospek|outreach)[^.]{0,30}(4|empat)[^.]{0,20}(klien|deal|lead)",
    nba_low,
)
check(
    "NBA TIDAK menyuruh kejar 4 klien baru",
    bad_scale is None,
    "—" if not bad_scale else bad_scale.group(0),
)
# Phase I (17 Sep): previously `... or s.capacity_utilization is not None` — practically always True.
# The correct contract (dual-track): the REVENUE CEILING warning may only appear when capacity is
# MEASURED (utilization > 0) — a warning without measurement = fabrication.
check("REVENUE CEILING (bila muncul) di-grounding kapasitas terukur",
      "REVENUE CEILING" not in all_notes.upper() or (s.capacity_utilization or 0) > 0,
      f"util={s.capacity_utilization} ceiling_note={'REVENUE CEILING' in all_notes.upper()}")

# ================= INVARIANT 5: never present hypothesis as fact =================
print("\n[P0-5] Never present hypothesis as fact", flush=True)
# Phase I (17 Sep): the old assertion was schema-field presence, and the detail printed
# `{'flat': ...}` which the assertion did not even use. Now the real behavior:
# FOUR splits + overall are all numbers — the hypothesis does not collapse into one number.
_split_keys = ("constraint_confidence", "revenue_impact_confidence",
               "decision_confidence", "experiment_confidence")
check(
    "split confidence ada (bukan satu angka)",
    all(isinstance(d.get(k), (int, float)) for k in _split_keys)
    and isinstance(art.confidence, (int, float)),
    " | ".join(f"{k.replace('_confidence', '')}={d.get(k)}" for k in _split_keys)
      + f" | overall={art.confidence}",
)
# Phase I: the split check above already ensures this field is a number — read it directly.
ric = d.get("revenue_impact_confidence")
if ric is not None:
    check("revenue impact confidence LOW (<0.5)", ric < 0.5, f"{ric}")
else:
    check("revenue impact confidence field ada", False, "tidak ditemukan di artifact")

# ===== INVARIANT 6: NBA grounding to KB (internal-docs,
# Gate 3(d) internal-docs §2.1) =====
print("\n[P0-6] NBA grounding — KB sebagai dasar rekomendasi (selection milik KB)", flush=True)
_ng = (d.get("knowledge_activation") or {}).get("nba_grounding") or {}
_ng_status = _ng.get("status")
_ng_ok = _ng_status in ("GROUNDED", "PARTIAL", "NO_FIT", "NO_KB_SCOPE") or (
    _ng_status == "UNGROUNDED" and _ng.get("alternative_id")
)
check(
    "NBA grounding ter-verify / ter-flag lengkap (internal-docs)",
    _ng_ok,
    f"status={_ng_status} claimed={_ng.get('claimed_id') or '-'} "
    f"alt={_ng.get('alternative_id') or '-'}",
)

# ================= GATES =================
print("\n=== GATE SCORE (internal-docs Lampiran I — DoD) ===")
g1 = all(
    r[1] == "PASS"
    for r in results
    if r[0].startswith(("current", "target", "gap", "delivery", "acquisition"))
)
g2 = all(
    r[1] == "PASS"
    for r in results
    if "causal" in r[0] or "attributed" in r[0] or "proven" in r[0] or "unproven" in r[0]
)
g4 = all(r[1] == "PASS" for r in results if r[0].startswith(("NBA",)))
fails = [r for r in results if r[1] == "FAIL"]
n_pass = len(results) - len(fails)
# Phase I (17 Sep): the denominator is now HARD-BOUND. Previously `{n}/{len(results)}` — one check
# lost in an edit would print "18/18 PASS", indistinguishable from a silent regression.
EXPECTED_INVARIANTS = 20  # change ONLY together with internal-docs §10.1 G5 (#20=NBA grounding)
assert len(results) == EXPECTED_INVARIANTS, (
    f"jumlah invariant = {len(results)}, ekspektasi {EXPECTED_INVARIANTS} — "
    "cek check() mana yang hilang/bertambah; jangan panen PASS diam-diam")
print(f"INVARIANTS: {n_pass}/{len(results)} PASS")
for n, st, det in fails:
    print(f"  ❌ {n}: {det}")
verdict = "DOD TERCAPAI (freeze-ready)" if not fails else f"BELUM DoD — {len(fails)} invariant gagal"
print(f"\nVERDICT: {verdict}")

# ===== internal-docs §7: assert trace per-stage =====
pt = d.get("pipeline_trace") or {}
stages = [s.get("stage") for s in pt.get("stages", [])]
print(f"PIPELINE TRACE: {pt.get('stage_count', 0)} stages — {stages}")
_required = {
    "extract_state", "mechanisms", "llm_draft", "confidence.ranking",
    "causal", "opportunities", "spectrum",
}
_missing = _required - set(stages)
errs = [s for s in pt.get("stages", []) if s.get("status") != "ok"]
print(f"TRACE CHECK: missing={_missing or 'none'} | error_stages={errs or 'none'}")
if _missing or errs:
    print("VERDICT TRACE: FAIL")
else:
    print("VERDICT TRACE: PASS")

# era-7: self-consistency verification — a freshly written artifact MUST be fresh
ok, reason = verify_artifact_fresh(d)
print(f"FRESHNESS CHECK: {'PASS' if ok else 'FAIL'} — {reason}")

with open("eval_dod_smoke_result.json") as f:
    pass

# D10 (27 Sep): the exit code MUST reflect the verdict. Previously the script always
# exited 0 -> the B2 retry in the Makefile never triggered and `make gate-smoke`
# stayed "green" even when the VERDICT was NOT DoD (exposed by the 18/20 run in e161600).
_smoke_ok = (not fails) and not (_missing or errs) and ok
print(f"SMOKE EXIT: {'0 (PASS)' if _smoke_ok else '1 (FAIL)'}")
sys.exit(0 if _smoke_ok else 1)
