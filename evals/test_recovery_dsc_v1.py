"""dsc.v1 — Decision Sufficiency & Checkpoint Eligibility (int 18, phase B1): nm.v2 contract + S0–S5 guards + G6/G7.

EVIDENCE STATUS: DETERMINISTIC_PASS. The reasoning model here is a script/mock — this proves the CONTRACT &
GUARDS, not that the chosen questions/conclusions are useful (that is LIVE_NOT_RUN until phase D).

What is proven:
  A  nm.v2 contract: nm.v1 fields stay intact (parity); one active version (nm.v1 rejected); no fifth
     level; the schema rejects requirement-status fields (the model has no path to write them)
  B  four levels: STATE_ONLY/DISCOVERY_NEEDED/PROVISIONAL_READY/DECISION_USABLE; EVIDENCE_PENDING = an
     orthogonal condition (allowed alongside PROVISIONAL_READY), not a fifth level
  C  S1–S5: active-claim basis, traceability & uncertainty disclosure, the DECISION_USABLE bound,
     Goal/Path consistency, level ↔ evidence fit (non-material counterfactuals must not block)
  D  G7 revision: HOLD is valid with an EXPLICIT reason per need (R1 non-material · R2 needs_measurement/
     needs_external · R3 user chose to pause); `abstain=true` alone is NOT enough; fail-closed if block absent
  E  G6 revision: ACTION is valid on feasibility/measurement (not only the planner step kind), with
     `action_basis` recorded; supporting claim + measurable design still required (G10)
  H  a correction supersedes a claim ⇒ the old basis can no longer support a ready level
     (S1 meets real supersession)
  I  provider failure ⇒ honest degraded, no fabricated sufficiency, no silent finalization
  F  F1 (BC-05, decided Oct 15): EVIDENCE_REQUEST points at REAL sources (active claim/retrieved knowledge)
     + relevance; new measurement is NOT this — it is ACTION + `move_design` (one path, not two)
  G  certification label: `final` only when critical is empty AND standing SUPPORTED; otherwise provisional
     + coded reasons (ELIGIBILITY_ABSENT/STALE · CRITICAL_UNKNOWN_OPEN · EVIDENCE_WEAK/INSUFFICIENT)

Groups A–I status: ALL implemented (B1 + F1 + G). Still out of scope: phase C (checkpoint offer UX + screen
copy) and phase D (the `dsc-corpus-v1` corpus + paired metrics) — both LIVE_NOT_RUN.

CONTRACT HARDENING (Oct 15 2026, audit "dsc.v1 not yet product-complete") — group J, ids DSC-R01…R11:
  DSC-R01  measurement only via ACTION + move_design ⇒ exactly one Move PLANNED; HOLD does not store a plan
  DSC-R02  an ordinary business constraint is not a pause request (the explicit user pause marker decides)
  DSC-R03  a STOP/non-navigable path cannot be the basis of an ACTION
  DSC-R04  ACTION without a supporting claim is rejected when the snapshot carries active claims
  DSC-R05  a goal_ref pointing at another Goal is rejected (S4)
  DSC-R06  the STATE_ONLY level never yields a `final` label
  DSC-R07  the DISCOVERY_NEEDED level never yields a `final` label
  DSC-R08  active claims outside the decision snapshot must not become a hidden basis (S1)
  DSC-R09  a Goal version change without claim-node changes invalidates decision-basis freshness
  DSC-R10  no sufficiency block ⇒ honest degrade, not considered checkpoint-ready
  DSC-R11  a state change after assessment ⇒ the old certification basis is stale (primitive; the
           `/finalize` endpoint gate = phase C — not run here, see int 18 §15.3)
  DSC-R12  (LIVE_NOT_RUN) one rich opening story may yield PROVISIONAL_READY on the first turn —
           tests reasoning quality, not proposal legality ⇒ phase D

Final deep-check findings Oct 15 2026 (micro-closure):
  DSC-R13  S1 applies WITHOUT exception: a snapshot without `claim_ids` still rejects hidden bases
  DSC-R14  reuse policy: a valid assessment persists until the basis changes, but reuse is FLAGGED
           (`ELIGIBILITY_CARRIED_OVER`) + the origin turn's provenance, and is not enough for a `final` label
  DSC-R15  the latest assessment wins when present (level replacement applies) · provider failure ⇒
           flagged reuse
  DSC-R16  candidate capacity ↔ contract capacity aligned: 12/13/16 askable candidates can be
           represented & validated at the ready level; 17 is explicitly rejected by the schema
           (not silently truncated)
  DSC-R17  a `marginal_information_value` entry must accompany every `critical`/`nonblocking` classification

Run: .venv/bin/python evals/test_recovery_dsc_v1.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_recovery_adaptive as A  # noqa: E402  (harness + ScriptedLLM + sess)
import test_recovery_semantic as R  # noqa: E402

import app.turn as turn_mod  # noqa: E402
from app.moves import design_problems  # noqa: E402
from core.reasoning.contract import NM_CONTRACT_VERSION, NextMoveProposal  # noqa: E402
from core.reasoning.guard import ASK_CAP, validate  # noqa: E402

obs, cl = A.obs, A.cl
_PASS = _FAIL = 0


def check(name, cond, detail=""):
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"    OK  {name}")
    else:
        _FAIL += 1
        print(f"    GAGAL  {name}{' — ' + detail if detail else ''}")


# ── snapshot/claim fixtures (same shape as what the guard receives from the app) ──

def claim(cid, verbatim="pernyataan user", aspect=""):
    return {"id": cid, "type": "claim", "aspect": aspect, "status": "active", "tense": "now",
            "epistemic": "reported", "verbatim": verbatim, "quantity": None,
            "triple": {"subject": {"label": "s"}, "predicate": {"label": "p"}}}


def unc(uid, asked=0, askable=True, label=""):
    return {"id": uid, "label": label or uid, "asked": asked, "askable": askable, "kind": "need",
            "suggested_kind": "QUESTION"}


def snap(*, claims=(), uncertainties=(), goal=None, sid="ss-dsc"):
    claims = list(claims)
    return {"snapshot_id": sid, "goal": goal or {}, "claims": claims,
            "claim_ids": [c["id"] for c in claims], "uncertainties": list(uncertainties),
            "knowledge": [], "requirement_states": {}, "moves": [], "paths": [],
            "selection": {"active_total": len(claims), "included": len(claims), "omitted": 0,
                          "budget_chars": 9000, "used_chars": 40},
            "deterministic_hint": {"kind": "QUESTION", "text": ""}}


def graph(*claims):
    """CANONICAL nodes (same shape as the state graph): the guard reads verbatim/aspect from here, not from
    snapshot lines already rendered to text."""
    return {"nodes": {c["id"]: {"status": "active", "verbatim": c.get("verbatim") or "",
                                 "aspect": c.get("aspect") or ""} for c in claims}, "edges": {}}


def prop(s, **kw):
    d = {"contract_version": NM_CONTRACT_VERSION, "state_snapshot_ref": s["snapshot_id"],
         "proposed_move_kind": "QUESTION", "focus_type": "uncertainty",
         "proposed_focus": (s["uncertainties"] or [{"id": ""}])[0]["id"],
         "move_text": "Seberapa sering Anda menindaklanjuti calon klien yang bertanya?",
         "supporting_claim_refs": (s["claim_ids"] or [])[-1:]}
    d.update(kw)
    return d


def elig(**kw):
    d = {"level": "PROVISIONAL_READY", "basis_claim_refs": ["c1"], "critical_unknown_ids": [],
         "nonblocking_unknown_ids": ["u1"],
         "marginal_information_value": [{"uncertainty_id": "u1", "decision_impact": "langkah mana dipilih",
                                         "answerability": "now_conversation", "information_gain": "sedikit",
                                         "user_friction": "kecil", "counterfactual": ""}],
         "external_evidence_pending": False, "can_offer_checkpoint": True,
         "recommendation": "Lihat kesimpulan awal", "rationale": "gambaran pertama sudah layak"}
    d.update(kw)
    return d


def run(payload, s, g, **kw):
    """Direct guard (no model): valid/invalid + detail. This tests the CONTRACT/GUARD, not reasoning quality."""
    p = NextMoveProposal.model_validate(payload)
    kw.setdefault("knowledge_ids", set())
    kw.setdefault("action_allowed", False)
    return validate(p, snapshot=s, graph=g, hypotheses={}, **kw)


def rejects(res, prefix):
    return (not res.ok) and any(v.startswith(prefix) for v in res.violations)


# ── A: contract ────────────────────────────────────────────────────────────────

def test_contract():
    print("A — kontrak nm.v2 (parity field nm.v1, satu versi, tanpa tingkat kelima)")
    c1, u1 = claim("c1"), unc("u1")
    s, g = snap(claims=[c1], uncertainties=[u1]), graph(c1)

    r = run(prop(s), s, g)
    check("A1 usulan nm.v2 tanpa blok kecukupan tetap sah (blok OPSIONAL; parity nm.v1 utuh)",
          r.ok and r.sufficiency_violations == [] and r.action_basis == "", str(r.violations))

    r = run(prop(s, contract_version="nm.v1"), s, g)
    check("A2 nm.v1 ditolak (satu versi aktif; tanpa dual-validasi)", rejects(r, "S0"))

    for bad, label in (({"requirement_state": {"access.icp": "PRESENT"}}, "status requirement"),
                       ({"goal_confirmed": True}, "konfirmasi Goal")):
        try:
            NextMoveProposal.model_validate(prop(s, checkpoint_eligibility={**elig(), **bad}))
            rejected = False
        except Exception:  # noqa: BLE001
            rejected = True
        check(f"A3 blok menolak field {label} (model tak punya jalur menulisnya)", rejected)

    try:
        NextMoveProposal.model_validate(prop(s, checkpoint_eligibility=elig(level="EVIDENCE_PENDING")))
        rejected = False
    except Exception:  # noqa: BLE001
        rejected = True
    check("A4 tidak ada tingkat kelima (EVIDENCE_PENDING bukan level)", rejected)

    # Live finding Oct 15 2026 (session `3b69aac9157d`): the real model answered a rich story with >600-char
    # prose → schema rejected → the whole turn degraded "On hold". Prose caps = anti-DoS protection, not semantics.
    from core.reasoning.contract import (  # noqa: E402
        PROSE_CAP_DECISION_CHANGE,
        PROSE_CAP_MOVE_TEXT,
        PROSE_CAP_RATIONALE,
    )
    long_ok = prop(s, move_text="t" * (PROSE_CAP_MOVE_TEXT - 1),
                   information_value_rationale="r" * (PROSE_CAP_RATIONALE - 1),
                   expected_decision_change="d" * (PROSE_CAP_DECISION_CHANGE - 1))
    try:
        NextMoveProposal.model_validate(long_ok)
        accepted = True
    except Exception:  # noqa: BLE001
        accepted = False
    check("A5a prosa panjang-wajar (move_text/rasjon mendekati batas longgar) diterima skema — "
          "panjang teks tidak boleh mematikan giliran", accepted)
    try:
        NextMoveProposal.model_validate(prop(s, move_text="t" * (PROSE_CAP_MOVE_TEXT + 1)))
        rejected = False
    except Exception:  # noqa: BLE001
        rejected = True
    check("A5b batas anti-DoS tetap berlaku: di atas cap longgar tetap ditolak skema", rejected)


# ── B: four levels + orthogonal ─────────────────────────────────────────────

def test_levels():
    print("B — empat tingkat; EVIDENCE_PENDING ortogonal (bukan tingkat kelima)")
    c1, u1 = claim("c1"), unc("u1")
    s, g = snap(claims=[c1], uncertainties=[u1]), graph(c1)

    r = run(prop(s, checkpoint_eligibility=elig(level="STATE_ONLY", can_offer_checkpoint=False,
                                                recommendation="")), s, g)
    check("B1 STATE_ONLY tanpa tawaran sah (tetap ada langkah berikutnya)", r.ok, str(r.violations))

    r = run(prop(s, checkpoint_eligibility=elig(level="STATE_ONLY", can_offer_checkpoint=True)), s, g)
    check("B2 STATE_ONLY + can_offer_checkpoint=true ditolak (tidak menawarkan kesimpulan yang tidak ada)",
          rejects(r, "S0"))

    r = run(prop(s, checkpoint_eligibility=elig(level="DISCOVERY_NEEDED", can_offer_checkpoint=False)), s, g)
    check("B3 DISCOVERY_NEEDED sah tanpa tawaran (masih ada kebutuhan material)", r.ok, str(r.violations))

    r = run(prop(s, checkpoint_eligibility=elig(can_offer_checkpoint=False)), s, g)
    check("B4 PROVISIONAL_READY wajib ditawarkan (tingkat siap tidak boleh ditahan)", rejects(r, "S0"))

    r = run(prop(s, checkpoint_eligibility=elig(external_evidence_pending=True)), s, g)
    check("B5 EVIDENCE_PENDING ortogonal: PROVISIONAL_READY + external_evidence_pending=true SAH",
          r.ok, str(r.violations))


# ── C: S1–S5 ─────────────────────────────────────────────────────────────────

def test_sufficiency():
    print("C — S1–S5: referensi, pengungkapan, batas tingkat, konsistensi Goal/Path, kecocokan bukti")
    c1, u1 = claim("c1"), unc("u1")
    s, g = snap(claims=[c1], uncertainties=[u1]), graph(c1)

    r = run(prop(s, checkpoint_eligibility=elig(basis_claim_refs=["c1", "cl-superseded"])), s, g)
    check("C1 (S1) basis klaim tidak aktif ⇒ ditolak (tidak menghidupkan fakta lama)", rejects(r, "S1"))

    r = run(prop(s, checkpoint_eligibility=elig(nonblocking_unknown_ids=[], critical_unknown_ids=[],
                                                marginal_information_value=[])), s, g)
    check("C2 (S2) kandidat yang masih dapat ditanya disembunyikan ⇒ ditolak", rejects(r, "S2"))

    r = run(prop(s, checkpoint_eligibility=elig(critical_unknown_ids=["u1"], nonblocking_unknown_ids=["u1"])), s, g)
    check("C3 (S0/S2) id yang sama di critical DAN nonblocking ⇒ ditolak", not r.ok)

    r = run(prop(s, checkpoint_eligibility={**elig(nonblocking_unknown_ids=["u9"]),
                                            "marginal_information_value": [
                                                {"uncertainty_id": "u9", "counterfactual": ""}]}), s, g)
    check("C4 (S2) entri untuk kandidat tak dikenal ⇒ ditolak", rejects(r, "S2"))

    r = run(prop(s, checkpoint_eligibility=elig(level="DECISION_USABLE", critical_unknown_ids=["u1"],
                                                marginal_information_value=[
                                                    {"uncertainty_id": "u1", "answerability": "needs_measurement",
                                                     "counterfactual": "langkah berubah"}],
                                                nonblocking_unknown_ids=[])), s, g)
    check("C5 (S3) DECISION_USABLE dengan ketidakpastian kritikal ⇒ ditolak", rejects(r, "S3"))

    r = run(prop(s, goal_ref="gl-1", checkpoint_eligibility=elig()), s, g)
    check("C6 (S4) goal_ref diisi padahal snapshot tanpa Goal terbentuk ⇒ ditolak", rejects(r, "S4"))

    s_gl = snap(claims=[c1], uncertainties=[u1], goal={"goal_id": "gl-1", "version": 2})
    r = run(prop(s_gl, goal_ref="gl-2", checkpoint_eligibility=elig()), s_gl, g)
    check("C6b (S4) goal_ref menunjuk Goal LAIN ⇒ ditolak (hardening P0-05)", rejects(r, "S4"),
          str(r.violations))

    r = run(prop(s_gl, goal_ref="gl-1", checkpoint_eligibility=elig()), s_gl, g)
    check("C6c (S4) goal_ref cocok dengan Goal snapshot ⇒ lolos", r.ok, str(r.violations))

    r = run(prop(s, checkpoint_eligibility=elig(basis_claim_refs=["c1", "p-1"])), s, g, path_ids={"p-1"},
            paths=[{"path_id": "p-1", "feasibility": "SUPPORTED", "navigable": True, "status": "OPEN"}])
    check("C7 (S4) id path menyamar sebagai klaim basis ⇒ ditolak", rejects(r, "S4"))

    c_ng = claim("c1", verbatim="")
    s_ng, g_ng = snap(claims=[c_ng], uncertainties=[u1]), graph(c_ng)
    r = run(prop(s_ng, checkpoint_eligibility=elig()), s_ng, g_ng)
    check("C8 (S5) tingkat siap tanpa klaim basis berkutipan (grounded) ⇒ ditolak", rejects(r, "S5"))

    r = run(prop(s, checkpoint_eligibility=elig(level="DECISION_USABLE", nonblocking_unknown_ids=[],
                                                marginal_information_value=[])), s, g)
    check("C9 (S5) DECISION_USABLE saat kandidat material masih dapat dijawab sekarang ⇒ ditolak", not r.ok)

    r = run(prop(s, checkpoint_eligibility=elig(nonblocking_unknown_ids=["u1"], critical_unknown_ids=[],
                                                marginal_information_value=[
                                                    {"uncertainty_id": "u1", "answerability": "now_conversation",
                                                     "counterfactual": "jawaban mengubah langkah"}])), s, g)
    check("C10 (S5) material & masih dapat dijawab sekarang tidak boleh didaftarkan nonblocking ⇒ ditolak",
          rejects(r, "S5"))

    m = {"uncertainty_id": "u1", "answerability": "needs_measurement", "decision_impact": "pilihan langkah",
         "counterfactual": "kalau angkanya besar, langkah berubah"}
    r = run(prop(s, checkpoint_eligibility=elig(level="DISCOVERY_NEEDED", can_offer_checkpoint=False,
                                                nonblocking_unknown_ids=[], critical_unknown_ids=["u1"],
                                                marginal_information_value=[m])), s, g)
    check("C11 (S5) id critical yang tidak dapat dijawab sekarang ⇒ ditolak (tempatnya nonblocking)",
          rejects(r, "S5"))

    r = run(prop(s, checkpoint_eligibility=elig(level="DECISION_USABLE", critical_unknown_ids=[],
                                                nonblocking_unknown_ids=["u1"],
                                                marginal_information_value=[m])), s, g)
    check("C12 positif: DECISION_USABLE + kebutuhan tersisa yang butuh pengukuran (terungkap, tidak memblokir) ⇒ SAH",
          r.ok, str(r.violations))


# ── D: G7 revision ─────────────────────────────────────────────────────────────

def test_g7():
    print("D — G7 revisi: HOLD sah hanya dengan alasan eksplisit per kebutuhan")
    c1, u1 = claim("c1"), unc("u1")
    s, g = snap(claims=[c1], uncertainties=[u1]), graph(c1)
    hold = {"proposed_move_kind": "HOLD", "abstain": True, "focus_type": "uncertainty", "proposed_focus": "",
            "move_text": "Ceritanya sudah saya pahami; kita jeda dulu di sini.",
            "conditions_for_abstention": "satu pengukuran perlu dijalankan sebelum lanjut"}

    r = run(prop(s, **hold, checkpoint_eligibility=elig(level="DISCOVERY_NEEDED", can_offer_checkpoint=False)),
            s, g)
    check("D1 HOLD dengan R1 (non-material, kontrafaktual kosong) SAH — dulu dilarang total",
          r.ok and any(x.startswith("R1") for x in r.hold_reasons), str(r.violations))

    design = {"objective": "ukur berapa yang ditindaklanjuti", "measurement_method": "hitung balasan <24 jam",
              "expected_evidence": ["jumlah balasan"], "completion_criteria": ["angka dilaporkan"],
              "observation_window_days": 14,
              "actions": [{"title": "Tindaklanjuti calon klien & catat balasan <24 jam"}]}  # Phase 7: action list wajib
    m = {"uncertainty_id": "u1", "answerability": "needs_measurement", "decision_impact": "langkah berubah",
         "counterfactual": "kalau bocor, fokus berubah ke tindak lanjut"}
    r = run(prop(s, **hold, move_design=design,
                 checkpoint_eligibility=elig(level="DISCOVERY_NEEDED", can_offer_checkpoint=False,
                                             nonblocking_unknown_ids=["u1"], critical_unknown_ids=[],
                                             marginal_information_value=[m])), s, g)
    check("D2 HOLD + `needs_measurement` DITOLAK (hardening P0-01): pengukuran harus lewat ACTION + move_design "
          "supaya Move PLANNED benar-benar lahir",
          rejects(r, "G7") and any("PENGUKURAN" in x for x in r.violations), str(r.violations))

    r = run(prop(s, **hold, checkpoint_eligibility=elig(level="DISCOVERY_NEEDED", can_offer_checkpoint=False,
                                                        nonblocking_unknown_ids=["u1"], critical_unknown_ids=[],
                                                        marginal_information_value=[m])), s, g)
    check("D3 HOLD + `needs_measurement` tanpa move_design tetap ditolak (tidak ada jalur jeda-ukur)",
          rejects(r, "G7"))

    m_ext = {"uncertainty_id": "u1", "answerability": "needs_external", "decision_impact": "langkah berubah",
             "counterfactual": "kalau data luar berbeda, langkah berubah"}
    r = run(prop(s, **hold, checkpoint_eligibility=elig(level="DISCOVERY_NEEDED", can_offer_checkpoint=False,
                                                        nonblocking_unknown_ids=["u1"], critical_unknown_ids=[],
                                                        marginal_information_value=[m_ext])), s, g)
    check("D3b R2 `needs_external` tetap SAH untuk jeda (menunggu data luar; tidak menuntut aksi baru dari user)",
          r.ok and any(x.startswith("R2") for x in r.hold_reasons), str(r.violations))

    r = run(prop(s, **hold), s, g)
    check("D4 fail-closed: HOLD tanpa blok kecukupan + masih ada kebutuhan ⇒ ditolak",
          rejects(r, "G7"))

    r = run(prop(s, **hold, checkpoint_eligibility=elig(level="DISCOVERY_NEEDED", can_offer_checkpoint=False,
                                                        nonblocking_unknown_ids=[], critical_unknown_ids=["u1"],
                                                        marginal_information_value=[
                                                            {"uncertainty_id": "u1",
                                                             "answerability": "now_conversation",
                                                             "counterfactual": "jawaban mengubah langkah"}])) , s, g)
    check("D5 kebutuhan material yang masih bisa dijawab ⇒ HOLD ditolak (bukan janji bertanya)",
          rejects(r, "G7"))

    c_pr = claim("c2", verbatim="Saya tidak mau menambah jam kerja", aspect="constraint")
    s_pr, g_pr = snap(claims=[c1, c_pr], uncertainties=[u1]), graph(c1, c_pr)
    r = run(prop(s_pr, **hold, supporting_claim_refs=["c1", "c2"],
                 checkpoint_eligibility=elig(level="DISCOVERY_NEEDED", can_offer_checkpoint=False,
                                             basis_claim_refs=["c1", "c2"],
                                             nonblocking_unknown_ids=[], critical_unknown_ids=["u1"],
                                             marginal_information_value=[
                                                 {"uncertainty_id": "u1", "answerability": "now_conversation",
                                                  "counterfactual": "jawaban mengubah langkah"}])), s_pr, g_pr)
    check("D6 constraint bisnis biasa TIDAK lagi menjadi alasan jeda (hardening P0-02) — "
          "'tidak mau menambah jam kerja' = batasan tindakan, bukan permintaan berhenti",
          rejects(r, "G7"), str(r.violations))

    c_pause = claim("c3", verbatim="Sepertinya cukup dulu sampai di sini, saya mau jeda", aspect="preference")
    s_pz, g_pz = snap(claims=[c1, c_pause], uncertainties=[u1]), graph(c1, c_pause)
    r = run(prop(s_pz, **hold, supporting_claim_refs=["c1", "c3"],
                 checkpoint_eligibility=elig(level="DISCOVERY_NEEDED", can_offer_checkpoint=False,
                                             basis_claim_refs=["c1", "c3"],
                                             nonblocking_unknown_ids=[], critical_unknown_ids=["u1"],
                                             marginal_information_value=[
                                                 {"uncertainty_id": "u1", "answerability": "now_conversation",
                                                  "counterfactual": "jawaban mengubah langkah"}])), s_pz, g_pz)
    check("D6b permintaan jeda EKSPLISIT user (penanda jeda pada kata user) SAH sebagai R3",
          r.ok and any(x.startswith("R3") for x in r.hold_reasons), str(r.violations))

    r = run(prop(s, **hold, move_design=design,
                 checkpoint_eligibility=elig(level="DISCOVERY_NEEDED", can_offer_checkpoint=False)), s, g)
    check("D9 HOLD yang membawa move_design ditolak (jeda tidak boleh menyembunyikan rencana eksperimen)",
          rejects(r, "G7"), str(r.violations))

    r = run(prop(s, **{**hold, "conditions_for_abstention": ""},
                 checkpoint_eligibility=elig(level="DISCOVERY_NEEDED", can_offer_checkpoint=False)), s, g)
    check("D7 conditions_for_abstention tetap wajib (regresi tidak hilang)", rejects(r, "G7"))


# ── E: G6 revision ─────────────────────────────────────────────────────────────

def test_g6():
    print("E — G6 revisi: ACTION atas feasibility/pengukuran, tetap wajib desain + klaim pendukung")
    c1, u1 = claim("c1"), unc("u1")
    s, g = snap(claims=[c1], uncertainties=[u1]), graph(c1)
    design = {"objective": "uji penawaran ke 5 calon klien", "measurement_method": "catat balasan",
              "expected_evidence": ["jumlah balasan"], "completion_criteria": ["angka dilaporkan"],
              "observation_window_days": 7,
              "actions": [{"title": "Kirim penawaran ke 5 calon klien & catat balasan"}]}  # Phase 7
    act = {"proposed_move_kind": "ACTION", "focus_type": "uncertainty", "proposed_focus": "",
           "move_text": "Kirim penawaran ke lima calon klien lalu catat balasannya.",
           "supporting_claim_refs": ["c1"], "move_design": design}

    r = run(prop(s, **act), s, g, action_allowed=False, design_problems=design_problems,
            path_ids={"p-1"}, paths=[{"path_id": "p-1", "feasibility": "CONDITIONAL",
                                     "navigable": True, "status": "TEST_FIRST"}])
    check("E1 ACTION sah atas feasibility CONDITIONAL walau jenis langkah planner bukan ACTION",
          r.ok and r.action_basis == "feasibility_supported", f"{r.action_basis} {r.violations}")

    mmeas = {"uncertainty_id": "u1", "answerability": "needs_measurement", "decision_impact": "langkah berubah",
             "counterfactual": "kalau bocor, fokus berubah"}
    r = run(prop(s, **act, checkpoint_eligibility=elig(level="DISCOVERY_NEEDED", can_offer_checkpoint=False,
                                                       critical_unknown_ids=[], nonblocking_unknown_ids=["u1"],
                                                       marginal_information_value=[mmeas])),
            s, g, action_allowed=False, design_problems=design_problems, paths=[])
    check("E2 ACTION pengukuran sah tanpa path bila kebutuhan butuh diukur (basis=measurement_move)",
          r.ok and r.action_basis == "measurement_move", f"{r.action_basis} {r.violations}")

    r = run(prop(s, **act), s, g, action_allowed=False, design_problems=design_problems, paths=[])
    check("E3a baseline: tanpa blok kecukupan pengukuran → tidak ada basis pengukuran",
          r.action_basis == "" and rejects(r, "G6"))

    r = run(prop(s, **{**act, "move_design": None}), s, g, action_allowed=True, design_problems=design_problems)
    check("E3b ACTION tanpa desain terukur tetap ditolak (G10 dipertahankan)", rejects(r, "G10"))

    r = run(prop(s, **act), s, g, action_allowed=True, design_problems=design_problems)
    check("E3c ACTION dari jenis langkah planner: basis=planner_kind_action (kompatibel hari ini)",
          r.ok and r.action_basis == "planner_kind_action", str(r.violations))

    linked = {**design, "linked_path_id": "p-1"}
    r = run(prop(s, **{**act, "move_design": linked}), s, g, action_allowed=False,
            design_problems=design_problems, path_ids={"p-1"},
            paths=[{"path_id": "p-1", "feasibility": "CONDITIONAL", "navigable": True,
                    "status": "TEST_FIRST"}, {"path_id": "p-2", "feasibility": "SUPPORTED", "navigable": True,
                                        "status": "OPEN"}])
    check("E4 ACTION atas path yang DITAUTKAN ⇒ basis feasibility_supported + path tercatat (bukan path lain)",
          r.ok and r.action_basis == "feasibility_supported" and r.action_basis_path == "p-1",
          f"{r.action_basis}/{r.action_basis_path} {r.violations}")

    r = run(prop(s, **{**act, "move_design": linked}), s, g, action_allowed=False,
            design_problems=design_problems, path_ids={"p-1"},
            paths=[{"path_id": "p-1", "feasibility": "SUPPORTED", "navigable": False, "status": "STOP"}])
    check("E5 path STOP/tidak navigable TIDAK boleh menjadi basis tindakan (hardening P0-03) ⇒ ditolak",
          rejects(r, "G6"), str(r.violations))

    r = run(prop(s, **{**act, "supporting_claim_refs": []}), s, g, action_allowed=True,
            design_problems=design_problems)
    check("E6 ACTION tanpa klaim pendukung ditolak saat snapshot membawa klaim aktif (grounding wajib)",
          rejects(r, "G8"), str(r.violations))

    s2, g2 = snap(claims=[c1, claim("c2")], uncertainties=[u1]), graph(c1, claim("c2"))
    s2["claim_ids"] = ["c1"]
    s2["claims"] = s2["claims"][:1]
    r = run(prop(s2, checkpoint_eligibility=elig(basis_claim_refs=["c2"])), s2, g2)
    check("E7 (S1) klaim AKTIF tetapi TIDAK ada di snapshot keputusan tidak boleh jadi basis tersembunyi",
          rejects(r, "S1"), str(r.violations))


# ── F: BC-05 — EVIDENCE_REQUEST = evidence that already exists (F1) ───────────────────

def test_evidence_request():
    print("F — F1: permintaan bukti menunjuk sumber NYATA; pengukuran baru = ACTION + move_design")
    c1, u1 = claim("c1"), unc("u1")
    s, g = snap(claims=[c1], uncertainties=[u1]), graph(c1)
    ev = {"proposed_move_kind": "EVIDENCE_REQUEST", "focus_type": "uncertainty", "proposed_focus": "u1",
          "move_text": "Kirimkan tangkapan percakapan follow-up yang sudah Anda punya.",
          "supporting_claim_refs": ["c1"]}

    r = run(prop(s, **ev), s, g)
    check("F1 EVIDENCE_REQUEST tanpa sumber ⇒ ditolak (bukan permintaan bukti yang dapat diperiksa)",
          rejects(r, "W-F1"))

    r = run(prop(s, **ev, evidence_source_refs=["cl-karangan"], information_value_rationale="relevan"), s, g)
    check("F2 sumber di luar klaim aktif/pengetahuan ⇒ ditolak (tidak mengarang sumber)", rejects(r, "W-F1"))

    r = run(prop(s, **ev, evidence_source_refs=["c1"], information_value_rationale="menunjukkan follow-up bocor"),
            s, g)
    check("F3 sumber = klaim aktif + relevansi ⇒ SAH", r.ok, str(r.violations))

    r = run(prop(s, **ev, evidence_source_refs=["KB-1"], information_value_rationale="kerangka relevan"),
            s, g, knowledge_ids={"KB-1"})
    check("F4 sumber boleh menunjuk pengetahuan yang benar-benar terambil ⇒ SAH", r.ok, str(r.violations))

    s2, g2 = snap(claims=[c1], uncertainties=[unc("u1", askable=False)]), graph(c1)
    r = run(prop(s2, **{**ev, "evidence_source_refs": ["c1"], "information_value_rationale": "x"}), s2, g2)
    check("F5 kebutuhan yang butuh pengukuran tetap DITOLAK di sini (diarahkan ke ACTION + move_design)",
          rejects(r, "G4"))

    try:
        NextMoveProposal.model_validate(prop(s, **ev, new_measurement={"objective": "ukur"}))
        rejected = False
    except Exception:  # noqa: BLE001
        rejected = True
    check("F6 tidak ada jalur kedua: field `new_measurement` ditolak skema (pengukuran hanya lewat ACTION)",
          rejected)


# ── G: certification label — two conditions, fail-closed ───────────────────────────

def test_certification_rules():
    print("G — `final` = critical kosong DAN standing SUPPORTED; selain itu provisional + alasan berkode")
    from app.finalization import (
        CRITICAL_UNKNOWN_OPEN,
        ELIGIBILITY_ABSENT,
        ELIGIBILITY_LEVEL_NOT_READY,
        ELIGIBILITY_STALE,
        EVIDENCE_INSUFFICIENT,
        EVIDENCE_WEAK,
        certification,
    )

    got = certification(evidence_standing="SUPPORTED",
                        eligibility={"critical_unknown_ids": [], "level": "PROVISIONAL_READY"}, freshness="fresh")
    check("G1 seluruh syarat (termasuk tingkat siap) terpenuhi ⇒ label final tanpa alasan",
          got == ("final", []), str(got))

    for standing, code in (("WEAK", EVIDENCE_WEAK), ("INSUFFICIENT", EVIDENCE_INSUFFICIENT)):
        label, reasons = certification(evidence_standing=standing,
                                       eligibility={"critical_unknown_ids": [], "level": "PROVISIONAL_READY"},
                                       freshness="fresh")
        check(f"G2 standing {standing} ⇒ HANYA provisional (kode {code})",
              label == "provisional" and reasons == [code], f"{label} {reasons}")

    label, reasons = certification(evidence_standing="SUPPORTED",
                                   eligibility={"critical_unknown_ids": ["u1"], "level": "PROVISIONAL_READY"},
                                   freshness="fresh")
    check("G3 masih ada ketidakpastian material yang dapat dijawab ⇒ tidak boleh final",
          label == "provisional" and CRITICAL_UNKNOWN_OPEN in reasons, f"{label} {reasons}")

    for freshness, code in (("stale", ELIGIBILITY_STALE), ("absent", ELIGIBILITY_ABSENT)):
        label, reasons = certification(evidence_standing="SUPPORTED",
                                       eligibility={"critical_unknown_ids": [], "level": "PROVISIONAL_READY"},
                                       freshness=freshness)
        check(f"G4 blok kecukupan {freshness} ⇒ tidak boleh final (kode {code})",
              label == "provisional" and code in reasons, f"{label} {reasons}")

    for level in ("STATE_ONLY", "DISCOVERY_NEEDED"):
        label, reasons = certification(evidence_standing="SUPPORTED",
                                       eligibility={"critical_unknown_ids": [], "level": level}, freshness="fresh")
        check(f"G6 tingkat {level} tidak pernah menghasilkan `final` (hardening P0-04, kode "
              f"{ELIGIBILITY_LEVEL_NOT_READY})",
              label == "provisional" and ELIGIBILITY_LEVEL_NOT_READY in reasons, f"{label} {reasons}")

    label, reasons = certification(evidence_standing="SUPPORTED", eligibility={"critical_unknown_ids": []},
                                   freshness="fresh")
    check("G7 blok tanpa tingkat siap (mis. legacy) fail-closed: bukan `final`",
          label == "provisional" and ELIGIBILITY_LEVEL_NOT_READY in reasons, f"{label} {reasons}")

    cases = (("SUPPORTED", {"critical_unknown_ids": [], "level": "PROVISIONAL_READY"}, "fresh"),
             ("SUPPORTED", {"critical_unknown_ids": ["x"], "level": "PROVISIONAL_READY"}, "fresh"),
             ("SUPPORTED", {"critical_unknown_ids": [], "level": "STATE_ONLY"}, "fresh"),
             ("WEAK", {"critical_unknown_ids": [], "level": "DECISION_USABLE"}, "fresh"),
             ("SUPPORTED", {}, "absent"),
             ("INSUFFICIENT", {"critical_unknown_ids": ["x"], "level": "DECISION_USABLE"}, "stale"))
    derived = all((certification(evidence_standing=a, eligibility=b, freshness=c)[0] == "final")
                  == (certification(evidence_standing=a, eligibility=b, freshness=c)[1] == [])
                  for a, b, c in cases)
    check("G5 label selalu turunan: `final` ⇔ tanpa alasan (fail-closed, dapat diaudit)", derived)


# ── H: corrections & superseded bases ───────────────────────────────────────

def test_correction_invalidates_basis(tmp):
    print("H — koreksi menggantikan klaim ⇒ basis lama tidak lagi menopang tingkat siap")
    s, st, _, saved = A.sess(tmp, "dsc-h-01")
    try:
        llm = A.ScriptedLLM([
            obs(claims=[cl("c1", "claim", "omzet", "is", "omzet saya 18 juta")]),
            obs(claims=[cl("c1", "claim", "omzet", "is", "ralat omzet 12 juta", supersedes="cl-e0000-001",
                           revision_kind="correction", revision_reason="ralat")]),
        ], lambda sn, a: A.base_prop(sn))
        turn_mod.run_turn(s, llm, "omzet saya 18 juta")
        first = llm.snapshots[0]["claim_ids"][0]
        turn_mod.run_turn(s, llm, "ralat omzet 12 juta")
        after = llm.snapshots[-1]
        check("H1 snapshot pasca-koreksi tidak lagi memuat klaim lama", first not in after["claim_ids"],
              f"{first} vs {after['claim_ids']}")
        rebuilt = [claim(cid, verbatim="kutipan dari transkrip") for cid in after["claim_ids"]]
        built = snap(claims=rebuilt, uncertainties=[unc("u1")], sid=after["snapshot_id"])
        gr = graph(*rebuilt)
        res = run(prop(built, checkpoint_eligibility=elig(basis_claim_refs=[first])), built, gr)
        check("H2 blok yang masih menopang tingkat siap pada klaim yang digantikan ⇒ ditolak (S1)",
              rejects(res, "S1"))
    finally:
        R._restore_real_env(st, saved)


# ── I: provider failure ────────────────────────────────────────────────────

def test_provider_failure(tmp):
    print("I — provider gagal ⇒ degraded jujur; TIDAK mengarang kecukupan dan tidak memfinalkan")
    s, st, _, saved = A.sess(tmp, "dsc-i-01")
    try:
        class RateLimitError(Exception):
            status_code = 429

        llm = A.ScriptedLLM([obs(claims=[cl("c1", "claim", "omzet", "is", "omzet saya 18 juta")])],
                            lambda sn, a: RateLimitError("kuota"))
        turn_mod.run_turn(s, llm, "omzet saya 18 juta")
        ad = s.planner_log[-1]["adaptive"]
        check("I1 kegagalan provider → degraded provider_unavailable (1 panggilan)",
              ad["status"] == "DEGRADED" and ad["reason"] == "provider_unavailable", str(ad))
        check("I2 tidak ada usulan/kecukupan yang dikarang saat degraded", "proposal" not in ad)
        check("I3 langkah yang disajikan = degraded jujur (bukan pertanyaan karangan)",
              s.planner_log[-1]["presented"].get("degraded") is True)
        check("I4 observasi tetap ter-commit walau penalaran gagal", len(s.state_graph["nodes"]) == 1)
        check("I5 tidak ada checkpoint/diagnosis yang dibuat diam-diam",
              not (s.checkpoints or []) and s.diagnosis is None)
    finally:
        R._restore_real_env(st, saved)


# ── J: regression hardening (audit Oct 15 2026: P0 gap + freshness + snapshot anchor) ──

_J_DESIGN = {"objective": "ukur berapa calon klien yang benar-benar ditindaklanjuti",
             "measurement_method": "catat balasan dalam 24 jam", "expected_evidence": ["jumlah balasan"],
             "completion_criteria": ["angka dilaporkan"], "observation_window_days": 14,
             "actions": [{"title": "Tindaklanjuti & catat balasan dalam 24 jam"}]}  # Phase 7


def _elig_block(snap, *, answerability="needs_measurement", level="PROVISIONAL_READY"):
    """Sufficiency block that FOLLOWS the snapshot candidates (deterministic harness: candidates = goal needs)."""
    ids = [u["id"] for u in snap.get("uncertainties") or []
           if u.get("askable", True) and int(u.get("asked", 0)) < ASK_CAP]
    ready = level in ("PROVISIONAL_READY", "DECISION_USABLE")
    return {"level": level, "can_offer_checkpoint": ready,
            "basis_claim_refs": list(snap.get("claim_ids") or []),
            "critical_unknown_ids": [], "nonblocking_unknown_ids": ids,
            "marginal_information_value": [
                {"uncertainty_id": i, "answerability": answerability, "decision_impact": "langkah mana aman dipilih",
                 "information_gain": "menentukan ukuran", "user_friction": "perlu mencatat",
                 "counterfactual": "kalau angkanya berbeda, langkah berubah"} for i in ids],
            "external_evidence_pending": False,
            "recommendation": "Lihat kesimpulan awal" if ready else "",
            "rationale": "gambaran pertama sudah layak" if ready else "satu pengukuran masih perlu dijalankan"}


def _hold_measurement(snap, _attempt=1):
    """A HOLD proposal that tries to store the measurement plan inside the reasoning proposal (old way)."""
    return A.base_prop(snap, proposed_move_kind="HOLD", abstain=True, focus_type="uncertainty", proposed_focus="",
                       move_text="Ceritanya sudah saya pahami; ada satu hal yang perlu Anda ukur dulu.",
                       conditions_for_abstention="satu pengukuran perlu dijalankan sebelum lanjut",
                       move_design=dict(_J_DESIGN),
                       checkpoint_eligibility=_elig_block(snap, level="DISCOVERY_NEEDED"))


def _action_measurement(snap, _attempt=1):
    """ACTION + move_design proposal: the valid way to perform a measurement (Move PLANNED)."""
    return A.base_prop(snap, proposed_move_kind="ACTION", focus_type="uncertainty", proposed_focus="",
                       move_text="Catat berapa calon klien yang benar-benar Anda tindak lanjuti minggu ini.",
                       information_value_rationale="memisahkan masalah akuisisi dari masalah tindak lanjut",
                       expected_decision_change="fokus berpindah ke tindak lanjut bila angkanya rendah",
                       move_design=dict(_J_DESIGN), checkpoint_eligibility=_elig_block(snap))


def _action_measurement_disc(snap, _attempt=1):
    """Measurement ACTION with a DISCOVERY_NEEDED sufficiency block (level replacement: latest wins)."""
    return A.base_prop(snap, proposed_move_kind="ACTION", focus_type="uncertainty", proposed_focus="",
                       move_text="Catat berapa calon klien yang benar-benar Anda tindak lanjuti minggu ini.",
                       information_value_rationale="memisahkan masalah akuisisi dari masalah tindak lanjut",
                       expected_decision_change="fokus berpindah ke tindak lanjut bila angkanya rendah",
                       move_design=dict(_J_DESIGN),
                       checkpoint_eligibility=_elig_block(snap, level="DISCOVERY_NEEDED"))


class _Artifact:
    def __init__(self, standing="SUPPORTED"):
        self.evidence_standing = standing
        self.status = "final"
        self.certification_reasons = []


def test_regression_hardening(tmp):
    print("J — regresi hardening DSC-R01…R11 (celah P0 + freshness + anchor snapshot)")
    from app import finalization as fin

    # ── R01 (integration): measurement does not stop as a plan; a Move is born only from ACTION ──
    s, st, _, saved = A.sess(tmp / "j01", "dsc-r01")
    try:
        llm = A.ScriptedLLM([obs(claims=[cl("c1", "claim", "klien", "has", "klien aktif saya 3 orang")])],
                            _hold_measurement)
        turn_mod.run_turn(s, llm, "klien aktif saya 3 orang")
        ad = s.planner_log[-1]["adaptive"]
        check("DSC-R01 HOLD + needs_measurement ditolak guard ⇒ giliran degraded jujur (bukan diterima diam-diam)",
              ad["status"] == "DEGRADED" and s.planner_log[-1]["presented"].get("degraded") is True,
              str(ad)[:200])
        check("DSC-R01 rencana pengukuran TIDAK menjadi Move (tidak ada rencana yang tak terlacak)",
              not (s.moves or []), str(s.moves))
    finally:
        R._restore_real_env(st, saved)

    s, st, _, saved = A.sess(tmp / "j01b", "dsc-r01b")
    try:
        llm = A.ScriptedLLM([obs(claims=[cl("c1", "claim", "klien", "has", "klien aktif saya 3 orang")])],
                            _action_measurement)
        turn_mod.run_turn(s, llm, "klien aktif saya 3 orang")
        mvs = s.moves or []
        check("DSC-R01 pengukuran yang DITERIMA melahirkan tepat satu Move",
              len(mvs) == 1, str(mvs)[:200])
        check("DSC-R01 Move berstatus PLANNED dan menautkan desain ukurnya",
              bool(mvs) and mvs[0]["lifecycle"] == "PLANNED"
              and mvs[0]["measurement_method"] == _J_DESIGN["measurement_method"], str(mvs)[:240])

        # ── R09: decision-basis freshness includes the Goal dimension (not only the claim fingerprint) ──
        art = _Artifact()
        fin.certify_artifact(s, art)
        blk, fresh, codes = fin.eligibility_freshness(s)
        check("DSC-R09 tanpa perubahan material basis dianggap SEGAR (tidak ada false-stale dari KB/prompt)",
              blk is not None and fresh == "fresh" and codes == [], f"{fresh} {codes}")
        check("DSC-R09 prasyarat: standing SUPPORTED + tingkat siap ⇒ dapat disertifikasi `final`",
              art.status == "final" and art.certification_reasons == [], f"{art.status} {art.certification_reasons}")

        s.goal["version"] = int(s.goal.get("version") or 1) + 1   # Goal changed; claim nodes did NOT change
        blk2, fresh2, codes2 = fin.eligibility_freshness(s)
        check("DSC-R09 perubahan Goal version (tanpa perubahan node klaim) membatalkan kesegaran basis",
              blk2 is not None and fresh2 == "stale" and fin.ELIGIBILITY_GOAL_CHANGED in codes2,
              f"{fresh2} {codes2}")
        art2 = _Artifact()
        fin.certify_artifact(s, art2)
        check("DSC-R09 label turun ke provisional karena Goal berubah (tidak dibiarkan `final`)",
              art2.status == "provisional" and fin.ELIGIBILITY_GOAL_CHANGED in art2.certification_reasons,
              f"{art2.status} {art2.certification_reasons}")

        # ── R11 (primitive): an old artifact must not appear as if it were a new result ──
        llm2 = A.ScriptedLLM([obs(claims=[cl("c2", "claim", "klien", "count", "minggu ini ada 2 klien baru")])],
                             lambda sn, _a: A.base_prop(sn))
        turn_mod.run_turn(s, llm2, "minggu ini ada 2 klien baru")
        blk3, fresh3, codes3 = fin.eligibility_freshness(s)
        check("DSC-R11 primitif: setelah state berubah, basis sertifikasi lama basi (kode state-change)",
              fresh3 == "stale" and fin.ELIGIBILITY_STATE_CHANGED in codes3, f"{fresh3} {codes3}")
        art3 = _Artifact()
        fin.certify_artifact(s, art3)
        check("DSC-R11 primitif: artefak lama tidak dapat disertifikasi `final` atas basis baru",
              art3.status == "provisional" and fin.ELIGIBILITY_STALE in art3.certification_reasons,
              f"{art3.status} {art3.certification_reasons}")
    finally:
        R._restore_real_env(st, saved)

    # ── R02 (guard): a pause = an explicit user request, not a business constraint ──
    c1, u1 = claim("c1"), unc("u1")
    m_now = {"uncertainty_id": "u1", "answerability": "now_conversation", "decision_impact": "langkah berubah",
             "counterfactual": "jawaban mengubah langkah"}
    blk_crit = elig(level="DISCOVERY_NEEDED", can_offer_checkpoint=False, critical_unknown_ids=["u1"],
                    nonblocking_unknown_ids=[], marginal_information_value=[m_now])
    hold_kw = {"proposed_move_kind": "HOLD", "abstain": True, "proposed_focus": "",
               "move_text": "Ceritanya sudah saya pahami; kita jeda dulu di sini.",
               "conditions_for_abstention": "menunggu data luar"}
    c_biz = claim("c2", verbatim="Saya tidak mau menambah jam kerja", aspect="constraint")
    s_biz, g_biz = snap(claims=[c1, c_biz], uncertainties=[u1]), graph(c1, c_biz)
    r = run(prop(s_biz, **hold_kw, supporting_claim_refs=["c1", "c2"],
                 checkpoint_eligibility={**blk_crit, "basis_claim_refs": ["c1", "c2"]}), s_biz, g_biz)
    check("DSC-R02 constraint bisnis biasa tidak menjadi permintaan jeda", rejects(r, "G7"), str(r.violations))
    c_pz = claim("c3", verbatim="Jangan tanya lagi dulu, saya mau jeda sejenak", aspect="preference")
    s_pz, g_pz = snap(claims=[c1, c_pz], uncertainties=[u1]), graph(c1, c_pz)
    r = run(prop(s_pz, **hold_kw, supporting_claim_refs=["c1", "c3"],
                 checkpoint_eligibility={**blk_crit, "basis_claim_refs": ["c1", "c3"]}), s_pz, g_pz)
    check("DSC-R02 permintaan jeda eksplisit user tetap sah sebagai R3",
          r.ok and any(x.startswith("R3") for x in r.hold_reasons), str(r.violations))

    # ── R03/R04 (guard): the action basis must be genuinely usable + grounded ──
    s1, g1 = snap(claims=[c1], uncertainties=[u1]), graph(c1)
    act_kw = {"proposed_move_kind": "ACTION", "proposed_focus": "",
              "move_text": "Kirim penawaran ke lima calon klien lalu catat balasannya."}
    r = run(prop(s1, **act_kw, move_design={**_J_DESIGN, "linked_path_id": "p-stop"}), s1, g1,
            action_allowed=False, design_problems=design_problems, path_ids={"p-stop"},
            paths=[{"path_id": "p-stop", "feasibility": "SUPPORTED", "navigable": False, "status": "STOP"}])
    check("DSC-R03 path STOP/tidak navigable tidak boleh menjadi basis ACTION",
          rejects(r, "G6"), str(r.violations))

    r = run(prop(s1, **act_kw, move_design=dict(_J_DESIGN)), s1, g1, action_allowed=False,
            design_problems=design_problems, paths=[{"path_id": "p-1", "feasibility": "SUPPORTED",
                                                     "navigable": True, "status": "STOP"}])
    check("DSC-R03 path ber-feasibility SUPPORTED tetapi STOP tetap tidak menjadi basis",
          rejects(r, "G6"), str(r.violations))

    r = run(prop(s1, **{**act_kw, "supporting_claim_refs": []}, move_design=dict(_J_DESIGN)), s1, g1,
            action_allowed=True, design_problems=design_problems)
    check("DSC-R04 ACTION tanpa supporting_claim_refs ditolak (snapshot membawa klaim aktif)",
          rejects(r, "G8"), str(r.violations))

    # ── R05/R08 (guard): Goal-scoped + anchor snapshot ──
    s_gl = snap(claims=[c1], uncertainties=[u1], goal={"goal_id": "gl-1", "version": 3})
    r = run(prop(s_gl, goal_ref="gl-2",
                 checkpoint_eligibility=elig(level="DISCOVERY_NEEDED", can_offer_checkpoint=False)), s_gl, g1)
    check("DSC-R05 goal_ref menunjuk Goal lain ⇒ ditolak", rejects(r, "S4"), str(r.violations))

    s_out, g_out = snap(claims=[c1], uncertainties=[u1]), graph(c1, claim("c9"))
    r = run(prop(s_out, checkpoint_eligibility=elig(basis_claim_refs=["c9"])), s_out, g_out)
    check("DSC-R08 klaim aktif di luar snapshot keputusan tidak boleh menjadi basis tersembunyi",
          rejects(r, "S1"), str(r.violations))

    # ── R06/R07 (certification): a not-ready level is never `final` ──
    lv, rs = fin.certification(evidence_standing="SUPPORTED", freshness="fresh",
                               eligibility={"critical_unknown_ids": [], "level": "STATE_ONLY"})
    check("DSC-R06 STATE_ONLY + standing SUPPORTED + critical kosong ⇒ bukan `final`",
          lv == "provisional" and fin.ELIGIBILITY_LEVEL_NOT_READY in rs, f"{lv} {rs}")
    lv, rs = fin.certification(evidence_standing="SUPPORTED", freshness="fresh",
                               eligibility={"critical_unknown_ids": [], "level": "DISCOVERY_NEEDED"})
    check("DSC-R07 DISCOVERY_NEEDED + standing SUPPORTED ⇒ bukan `final`",
          lv == "provisional" and fin.ELIGIBILITY_LEVEL_NOT_READY in rs, f"{lv} {rs}")

    # ── R13 (guard): S1 without exception — a snapshot carrying no claims at all ──
    s_empty, g_empty = snap(claims=[c1], uncertainties=[u1]), graph(c1)
    s_empty["claim_ids"], s_empty["claims"] = [], []
    r = run(prop(s_empty, checkpoint_eligibility=elig(basis_claim_refs=["c1"])), s_empty, g_empty)
    check("DSC-R13 snapshot tanpa claim_ids tetap menolak basis tersembunyi (S1 tanpa pengecualian)",
          rejects(r, "S1"), str(r.violations))

    # ── R14/R15 (integration): reuse policy for prior assessments + provenance + level replacement ──
    s14, st14, _, saved14 = A.sess(tmp / "j14", "dsc-r14")
    try:
        llm = A.ScriptedLLM([obs(claims=[cl("c1", "claim", "klien", "has", "klien aktif saya 3 orang")])],
                            _action_measurement)
        turn_mod.run_turn(s14, llm, "klien aktif saya 3 orang")
        prov = fin.eligibility_provenance(s14)
        art = _Artifact()
        fin.certify_artifact(s14, art)
        check("DSC-R14 prasyarat: penilaian GILIRAN INI (carried_over=false) dapat `final`",
              prov["carried_over"] is False and prov["block_turn"] == 1 and art.status == "final",
              f"{prov} {art.status} {art.certification_reasons}")

        llm2 = A.ScriptedLLM([obs()], lambda sn, _a: A.base_prop(sn))     # a turn without a sufficiency block
        turn_mod.run_turn(s14, llm2, "oke terima kasih")
        prov2 = fin.eligibility_provenance(s14)
        art2 = _Artifact()
        fin.certify_artifact(s14, art2)
        check("DSC-R14 penilaian sah BERTAHAN bila basis tidak berubah (dipakai ulang, bukan hilang)",
              prov2["freshness"] == "fresh" and prov2["carried_over"] is True, str(prov2))
        check("DSC-R14 reuse ditandai + asal giliran terekam (bukan tersembunyi)",
              prov2["block_turn"] == 1 and prov2["entries_after"] >= 1 and prov2["block_event_id"] != "",
              str(prov2))
        check("DSC-R14 label `final` TIDAK boleh berasal dari penilaian yang dipakai ulang",
              art2.status == "provisional" and fin.ELIGIBILITY_CARRIED_OVER in art2.certification_reasons,
              f"{art2.status} {art2.certification_reasons}")

        llm3 = A.ScriptedLLM([obs()], lambda sn, _a: _action_measurement_disc(sn))
        turn_mod.run_turn(s14, llm3, "oke")
        prov3 = fin.eligibility_provenance(s14)
        art3 = _Artifact()
        fin.certify_artifact(s14, art3)
        check("DSC-R15 penilaian TERBARU menang saat ada (bukan penilaian lama yang dipakai)",
              prov3["carried_over"] is False and prov3["block_turn"] == 3, str(prov3))
        check("DSC-R15 pergantian level berlaku: DISCOVERY_NEEDED tidak menghasilkan `final`, tanpa tanda reuse",
              art3.status == "provisional"
              and fin.ELIGIBILITY_LEVEL_NOT_READY in art3.certification_reasons
              and fin.ELIGIBILITY_CARRIED_OVER not in art3.certification_reasons,
              f"{art3.status} {art3.certification_reasons}")

        class RateLimitError(Exception):
            status_code = 429

        llm4 = A.ScriptedLLM([obs()], lambda _sn, _a: RateLimitError("kuota"))
        turn_mod.run_turn(s14, llm4, "oke")
        prov4 = fin.eligibility_provenance(s14)
        art4 = _Artifact()
        fin.certify_artifact(s14, art4)
        check("DSC-R15 provider gagal: penilaian sah tetap dipakai ulang — ditandai, bukan dipromosikan",
              prov4["carried_over"] is True
              and fin.ELIGIBILITY_CARRIED_OVER in art4.certification_reasons,
              f"{prov4} {art4.certification_reasons}")
    finally:
        R._restore_real_env(st14, saved14)

    # ── R16/R17 (contract): candidate capacity aligned + marginal entries must be classified ──
    for n in (12, 13, 16):
        uids = [f"u{i}" for i in range(1, n + 1)]
        c16, u16 = claim("c1"), unc(uids[0])
        s16 = snap(claims=[c16], uncertainties=[unc(u) for u in uids])
        g16 = graph(c16)
        blk16 = elig(level="PROVISIONAL_READY", basis_claim_refs=["c1"], critical_unknown_ids=[],
                     nonblocking_unknown_ids=uids,
                     marginal_information_value=[{"uncertainty_id": u, "answerability": "needs_measurement",
                                                  "decision_impact": "langkah mana aman dipilih",
                                                  "counterfactual": "kalau angkanya beda, langkah berubah"}
                                                 for u in uids])
        r = run(prop(s16, proposed_focus=u16["id"], checkpoint_eligibility=blk16), s16, g16)
        check(f"DSC-R16 {n} kandidat askable dapat diwakili & divalidasi pada tingkat siap",
              r.ok, str(r.violations)[:200])

    uids17 = [f"u{i}" for i in range(1, 18)]
    try:
        NextMoveProposal.model_validate(prop(snap(claims=[c1], uncertainties=[unc(u) for u in uids17]),
                                             checkpoint_eligibility=elig(
                                                 nonblocking_unknown_ids=uids17,
                                                 marginal_information_value=[
                                                     {"uncertainty_id": u, "counterfactual": "x"}
                                                     for u in uids17])))
        rejected = False
    except Exception:  # noqa: BLE001
        rejected = True
    check("DSC-R16 di atas batas kanonik (17) ditolak eksplisit oleh skema — bukan dipotong diam-diam", rejected)

    m_cls = {"uncertainty_id": "u1", "answerability": "now_conversation", "decision_impact": "langkah berubah",
             "counterfactual": "jawaban mengubah langkah"}
    m_extra = {"uncertainty_id": "u2", "answerability": "needs_measurement",
               "counterfactual": "kalau angkanya beda, langkah berubah"}
    s17, g17 = snap(claims=[c1], uncertainties=[unc("u1"), unc("u2")]), graph(c1)
    r = run(prop(s17, checkpoint_eligibility=elig(level="DISCOVERY_NEEDED", can_offer_checkpoint=False,
                                                 critical_unknown_ids=["u1"], nonblocking_unknown_ids=[],
                                                 marginal_information_value=[m_cls, m_extra])), s17, g17)
    check("DSC-R17 entri marginal untuk kandidat yang TIDAK diklasifikasi ditolak (S2)",
          rejects(r, "S2"), str(r.violations))

    # ── R10 (integration): no sufficiency block ⇒ honest degrade, not checkpoint-ready ──
    s10, st10, _, saved10 = A.sess(tmp / "j10", "dsc-r10")
    try:
        class RateLimitError(Exception):
            status_code = 429

        llm = A.ScriptedLLM([obs(claims=[cl("c1", "claim", "klien", "has", "klien aktif saya 3 orang")])],
                            lambda _sn, _a: RateLimitError("kuota"))
        turn_mod.run_turn(s10, llm, "klien aktif saya 3 orang")
        blk10, fresh10, _ = fin.eligibility_freshness(s10)
        art10 = _Artifact()
        fin.certify_artifact(s10, art10)
        check("DSC-R10 tanpa blok kecukupan: 'absent' dan label tidak boleh `final` (tidak checkpoint-ready)",
              blk10 is None and fresh10 == "absent" and art10.status == "provisional"
              and fin.ELIGIBILITY_ABSENT in art10.certification_reasons,
              f"{fresh10} {art10.status} {art10.certification_reasons}")
        check("DSC-R10 degraded jujur: tidak ada checkpoint/diagnosis yang dibuat diam-diam",
              not (s10.checkpoints or []) and s10.diagnosis is None)
    finally:
        R._restore_real_env(st10, saved10)


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="nvl-dsc-"))
    print("dsc.v1 (nm.v2) — kontrak + guard S0–S5 + G6/G7 + F1 + sertifikasi label (int 18 §13 A–I) + J")
    test_contract()
    test_levels()
    test_sufficiency()
    test_g7()
    test_g6()
    test_evidence_request()
    test_certification_rules()
    test_correction_invalidates_basis(tmp / "h")
    test_provider_failure(tmp / "i")
    test_regression_hardening(tmp / "j")
    print()
    print(f"HASIL dsc.v1: {_PASS}/{_PASS + _FAIL} PASS (DETERMINISTIC_PASS; DSC-R12 + fase C UX & fase D "
          f"korpus/metrik = LIVE_NOT_RUN)" + (" ✅" if _FAIL == 0 else " ❌"))
    return 0 if _FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
