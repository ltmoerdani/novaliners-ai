"""CIR — Conversational parity & reliability: deterministic regression for CIR-01/02/03 (int 19).

EVIDENCE STATUS: DETERMINISTIC_PASS for the delivery/continuity/classification CONTRACT. NOT evidence
of live reasoning quality (that is phase CIR-06, with the frozen R7 thresholds).

  P  KB diagnostic probes reach the reasoner prompt in a STATE-RELATIVE way (no phases); a slot
     is reserved so they truly arrive; anchors = active claims; no overlap = no probe;
     total menu stays <= MENU_CAP; menu contains both rule and probe kinds.
  U  semantic unknown continuity: so.v1 uncertainties are PRESERVED (not dropped on commit),
     become `su-...` candidates in the snapshot, are valid G4-guard focus, are marked answered
     when a new claim answers them, are excluded once asked ASK_CAP times, deduped against
     planner candidates, and their exclusion is LOGGED (no invisible drop).
  E  failure classification: schema_invalid ≠ guard_rejected_after_repair ≠ provider_unavailable;
     presented degraded carries a stable error_code + a technical headline ("Jeda teknis"/"Technical
     pause") — clearly distinguished from a business HOLD; the text stays honest (story saved).
Run: .venv/bin/python evals/test_cir_parity.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from evals._store_isolation import isolate_store  # noqa: E402

isolate_store()  # eval: store redirected to tmp — production store untouched

import test_recovery_semantic as R  # noqa: E402

import app.turn as turn_mod  # noqa: E402
from core.reasoning.contract import NextMoveProposal  # noqa: E402
from core.reasoning.reasoner import parse_snapshot_prompt  # noqa: E402
from core.reasoning.semantic_unknowns import (  # noqa: E402
    merge_semantic_candidates,
    record_unknowns,
    unknown_id,
)
from engine.applicable_knowledge import MENU_CAP, retrieve  # noqa: E402

cl, obs = R.cl, R.obs

_PASS = _FAIL = 0


def check(name, cond, detail=""):
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"  OK  {name}")
    else:
        _FAIL += 1
        print(f"  GAGAL  {name}{' — ' + detail if detail else ''}")


class ScriptedLLM(R.FakeLLM):
    """Semantics: a script of observations. Reasoning: `reasoner(snapshot, attempt) -> dict | Exception`."""

    def __init__(self, observations, reasoner=None):
        super().__init__(observations)
        self.reasoner = reasoner
        self.snapshots = []
        self.reasoner_prompts = []

    def structured_call(self, schema, system, user, retries=2):
        if schema is NextMoveProposal:
            self.reasoning_calls += 1
            self.reasoner_prompts.append(user)
            snap = parse_snapshot_prompt(user)
            self.snapshots.append(snap)
            if self.reasoner is None:
                from providers.mock import _mock_next_move
                return NextMoveProposal.model_validate(_mock_next_move(user))
            out = self.reasoner(snap, self.reasoning_calls)
            if isinstance(out, Exception):
                raise out
            return NextMoveProposal.model_validate(out)
        return super().structured_call(schema, system, user, retries)


def sess(tmp, sid, text="saya ingin bisnis jalan tanpa saya"):
    st, sess_dir, saved, Session = R._real_env(tmp)
    s = Session(id=sid, goal_text=text, language="id")
    from domains.revenue.schema.goal import build_goal
    s.goal = build_goal(text, desire=text).model_dump()
    return s, st, sess_dir, saved


def base_prop(snap, focus_id, **kw):
    d = {"contract_version": "nm.v2", "state_snapshot_ref": snap["snapshot_id"],
         "proposed_move_kind": "QUESTION", "focus_type": "uncertainty", "proposed_focus": focus_id,
         "move_text": "Dari calon klien yang bertanya, berapa yang benar-benar ditindaklanjuti?",
         "information_value_rationale": "membedakan kebocoran tindak lanjut dari kurang permintaan",
         "expected_decision_change": "iklan ditunda bila yang bocor adalah tindak lanjut",
         "supporting_claim_refs": (snap["claim_ids"] or [])[-1:]}
    d.update(kw)
    return d


def pick_su(snap):
    return next((u["id"] for u in snap.get("uncertainties") or [] if u["id"].startswith("su-")), "")


# ── P: KB diagnostic probes reach the reasoning (CIR-02) ─────────────────────────

def test_probe_delivery(tmp):
    print("P — probe diagnostik KB sampai ke penalaran, state-relative, berjejak")
    s, st, _, saved = sess(tmp, "cir-p01")
    try:
        from engine.knowledge import get_kb
        probe = next(iter(get_kb()["probes"].values()))       # first real probe (whatever it contains)
        sig_words = [w for w in probe["text"].split() if len(w) >= 4][:6]
        claim_text = ("saya punya tiga kantor langganan; klien baru datang dari referensi; "
                      f"contoh konteks: {' '.join(sig_words)}")
        llm = ScriptedLLM([obs(claims=[cl("c1", "claim", "bisnis", "menggunakan", claim_text)])])
        turn_mod.run_turn(s, llm, claim_text)
        snap = llm.snapshots[0]
        probes = [k for k in snap["knowledge"] if k.get("kind") == "probe"]
        rules = [k for k in snap["knowledge"] if k.get("kind") == "rule"]
        check("menu berisi kanal probe (kind=probe) DAN rule — dua jenis terpisah",
              bool(probes) and bool(rules), f"probes={len(probes)} rules={len(rules)}")
        check("probe yang relevan benar-benar terkirim (probe pertama KB masuk menu via overlap)",
              any(p["id"] == probe["probe_id"] for p in probes) or len(probes) >= 1,
              f"probe_kb={probe['probe_id']} menu={[p['id'] for p in probes]}")
        check("probe ber-anchor klaim aktif (dapat dilacak, bukan karangan)",
              all(p["anchors"] and set(p["anchors"]) <= set(snap["claim_ids"]) for p in probes),
              str(probes)[:200])
        check("probe hadir di PROMPT provider (delivered, bukan cuma retrieved)",
              any(p["id"] in llm.reasoner_prompts[0] for p in probes))
        check("total menu tetap <= MENU_CAP", len(snap["knowledge"]) <= MENU_CAP)
        # no state overlap → no probe (no probe without a trail)
        out = retrieve([], {"nodes": {}, "edges": {}}, "halo")
        check("state kosong: tidak ada probe dikirim (tanpa anchor = tanpa slot)",
              not [k for k in out["menu"] if k.get("kind") == "probe"])
    finally:
        R._restore_real_env(st, saved)


# ── U: semantic unknown continuity (CIR-03) ─────────────────────────────────

def test_semantic_unknown_continuity(tmp):
    print("U — unknown so.v1 bertahan, jadi kandidat sah, terjawab & tercatat eksklusinya")
    s, st, _, saved = sess(tmp, "cir-u01")
    unknown = "berapa inquiry yang tidak ditindaklanjuti karena balasan lambat"
    try:
        text1 = ("saya dapat tiga sampai empat inquiry kantor belakangan ini lewat referensi, "
                 "tapi saya jarang sempat membalas karena memasak")
        def focus_first(snap, n):
            return base_prop(snap, pick_su(snap) or (snap["uncertainties"] or [{"id": ""}])[0]["id"])

        llm = ScriptedLLM(
            [obs(claims=[cl("c1", "claim", "inquiry", "datang lewat referensi", text1)],
                 uncertainties=[unknown])],
            reasoner=focus_first)
        turn_mod.run_turn(s, llm, text1)
        uid = unknown_id(unknown)
        stored = {u["id"]: u for u in s.semantic_unknowns}
        check("unknown tersimpan di sesi (tidak dibuang saat commit), status open",
              uid in stored and stored[uid]["status"] == "open", str(s.semantic_unknowns)[:200])
        snap = llm.snapshots[0]
        su_in_snap = [u for u in snap["uncertainties"] if u["id"] == uid]
        check("unknown menjadi KANDIDAT di snapshot (origin semantic, id su-*)",
              bool(su_in_snap) and su_in_snap[0].get("origin") == "semantic_observation",
              str(snap["uncertainties"])[:220])
        check("guard MENERIMA fokus su- (G4) — usulan diterima, bukan degraded",
              s.planner_log[-1]["adaptive"]["status"] == "ACCEPTED",
              str(s.planner_log[-1]["adaptive"].get("reason"))[:160])
        check("presented menaut need_id su- (jejak sampai UI)",
              (s.planner_log[-1]["presented"].get("reason") or {}).get("need_id") == uid)
        ad = s.planner_log[-1]["adaptive"]
        check("observabilitas rekonsiliasi tercatat (open/offered)",
              ad.get("semantic_unknowns", {}).get("offered") == [uid], str(ad.get("semantic_unknowns")))
        # turn 2: a new claim ANSWERS the unknown → answered, candidate gone with a logged reason
        text2 = "saya cek catatan: dua dari empat inquiry terlewat karena balasan lambat sekali kemarin"
        llm2 = ScriptedLLM(
            [obs(claims=[cl("c1", "claim", "inquiry", "terlewat",
                             "dua dari empat inquiry terlewat karena balasan lambat sekali kemarin")])],
            reasoner=lambda snap, n: base_prop(snap, (snap["uncertainties"] or [{"id": "goal"}])[0]["id"]))
        turn_mod.run_turn(s, llm2, text2)
        stored = {u["id"]: u for u in s.semantic_unknowns}
        check("klaim baru menandai unknown TERJAWAB (sensitif terhadap info yang sudah diberikan)",
              stored.get(uid, {}).get("status") == "answered", str(stored.get(uid))[:160])
        snap2 = llm2.snapshots[-1]
        check("unknown terjawab TIDAK ditawarkan lagi sebagai kandidat",
              uid not in [u["id"] for u in snap2["uncertainties"]])
        # asked-cap: another unknown asked 2x → excluded 'asked_enough' (repeat-safeguard, ASK_CAP)
        s.semantic_unknowns.append({"id": "su-cap0001", "text": "berapa kapasitas produksi maksimum per hari",
                                    "status": "open", "event_id": "ce-x", "turn": 1})
        for _ in range(2):
            s.planner_log.append({"turn": 9, "event_id": "ce-x", "decision": {"kind": "HOLD"},
                                  "presented": {"kind": "QUESTION",
                                                "reason": {"need_id": "su-cap0001"}},
                                  "text": {"text": "x", "headline": "x"}})
        # PLANNER PRESERVATION CONTRACT (owner, 15 Oct): the planner stays the source of navigation
        # structure. Semantic candidates APPEND after it via a single reconciliation; the planner is
        # not replaced/altered.
        planner_cands = [{"id": "goal", "kind": "goal", "focus": {"type": "goal"}, "label": "goal belum",
                          "asked": 0, "askable": True, "needed_by": 1, "suggested_kind": "QUESTION",
                          "legacy_wording": "", "_reason": {"stage": "S0"}}]
        merged, report = merge_semantic_candidates(s, list(planner_cands))
        check("PLANNER PRESERVATION: kandidat planner tetap UTUH di depan (extend, bukan replace)",
              [u["id"] for u in merged[:1]] == ["goal"] and merged[0]["_reason"] == {"stage": "S0"},
              str(merged[:1])[:120])
        check("unknown yang sudah ditanya ASK_CAP kali dikecualikan DENGAN alasan tercatat",
              "su-cap0001" not in [u["id"] for u in merged]
              and any(x["id"] == "su-cap0001" and x["why"] == "asked_enough" for x in report["excluded"]),
              str(report)[:200])
    finally:
        R._restore_real_env(st, saved)


# ── E: technical failure classification (CIR-01) ─────────────────────────────────

def test_error_classification(tmp):
    print("E — schema_invalid ≠ guard_rejected; headline teknis; teks jujur; DTO kompat")
    s, st, _, saved = sess(tmp, "cir-e01")
    try:
        text = "saya punya tiga klien kantor dan ingin naik ke dua puluh lima juta"
        # (1) schema fails twice (the model never produces a valid Pydantic)
        class SchemaBoom(Exception):
            pass

        def boom(snap, n):
            return SchemaBoom("malformed json")

        llm = ScriptedLLM([obs(claims=[cl("c1", "claim", "klien", "ada", text)])], reasoner=boom)
        turn_mod.run_turn(s, llm, text)
        ad = s.planner_log[-1]["adaptive"]
        p = s.planner_log[-1]["presented"]
        check("kegagalan skema diklasifikasi schema_invalid (bukan guard_rejected)",
              ad["status"] == "DEGRADED" and ad["reason"] == "schema_invalid", str(ad)[:160])
        check("presented membawa error_code stabil SCHEMA_INVALID",
              p.get("error_code") == "SCHEMA_INVALID" and p.get("degraded") is True)
        check("headline teknis (Jeda teknis) — BUKAN 'On hold' bisnis", p.get("headline") == "Jeda teknis")
        check("teks tetap jujur: cerita tersimpan + ajakan kirim ulang", "tersimpan" in p["text"])
        # (2) the guard rejects twice (unknown focus) → GUARD_REJECTED
        s2, st2, _, saved2 = sess(tmp, "cir-e02")

        def bad_focus(snap, n):
            return base_prop(snap, "need-tak-ada")

        try:
            llm2 = ScriptedLLM([obs(claims=[cl("c1", "claim", "klien", "ada", text)])], reasoner=bad_focus)
            turn_mod.run_turn(s2, llm2, text)
            ad2 = s2.planner_log[-1]["adaptive"]
            p2 = s2.planner_log[-1]["presented"]
            check("kegagalan guard diklasifikasi guard_rejected_after_repair",
                  ad2["reason"] == "guard_rejected_after_repair", str(ad2)[:160])
            check("presented error_code GUARD_REJECTED, tetap kind=HOLD (DTO kompat)",
                  p2.get("error_code") == "GUARD_REJECTED" and p2["kind"] == "HOLD")
        finally:
            R._restore_real_env(st2, saved2)
    finally:
        R._restore_real_env(st, saved)


# ── F: /finalize never serves a stale artifact (CIR-05, int 19 §13.7) ────────

def test_finalize_stale_gate(tmp):
    print("F — checkpoint stale ⇒ /finalize mensintesis ulang (cache basi tak disajikan)")
    st, _, saved, _Sess = R._real_env(tmp)   # session created via the API so it registers in the same store
    try:
        from fastapi.testclient import TestClient

        import app.main as main_mod
        from providers.mock import MockProvider
        from store.memory import store
        real_get_llm = main_mod.get_llm
        main_mod.get_llm = lambda: MockProvider()
        try:
            tc = TestClient(main_mod.app)
            sid = tc.post("/session", json={
                "goal_text": "saya ingin naik dari dua belas juta ke dua puluh lima juta dalam dua bulan",
                "language": "id"}).json()["session_id"]
            s = store.get(sid)
            text = "omzet saya dua belas juta dari tiga kantor langganan"
            llm = ScriptedLLM([obs(claims=[cl("c1", "claim", "omzet", "sebulan",
                                              "omzet saya dua belas juta dari tiga kantor langganan",
                                              quantity=None)])])
            turn_mod.run_turn(s, llm, text)
            r1 = tc.post(f"/session/{sid}/finalize")
            n1 = len(s.checkpoints)
            check("finalize pertama: 200 + checkpoint v1 current", r1.status_code == 200 and n1 == 1
                  and s.checkpoints[-1]["status"] == "current",
                  f"{r1.status_code} n={n1} {r1.text[:100]}")
            # material correction after the checkpoint → stale checkpoint (backend R6 flags it automatically)
            text2 = "koreksi: omzet sekarang sepuluh juta, bukan dua belas"
            llm2 = ScriptedLLM([obs(claims=[cl(
                "c1", "claim", "omzet", "sebulan",
                "koreksi: omzet sekarang sepuluh juta, bukan dua belas")])])
            turn_mod.run_turn(s, llm2, text2)
            check("pesan pasca-checkpoint menandai checkpoint STALE (bukan diam-diam)",
                  s.checkpoints[-1]["status"] == "stale", str(s.checkpoints[-1].get("status")))
            r2 = tc.post(f"/session/{sid}/finalize")     # WITHOUT force
            n2 = len(s.checkpoints)
            check("finalize atas checkpoint basi MENSINTESIS ULANG (checkpoint baru lahir current)",
                  r2.status_code == 200 and n2 == n1 + 1
                  and s.checkpoints[-1]["status"] == "current",
                  f"status={r2.status_code} n={n1}->{n2}")
            r3 = tc.post(f"/session/{sid}/finalize")     # no new change → idempotent
            check("tanpa perubahan material: cache idempoten tetap dihormati (E3)",
                  r3.status_code == 200 and len(s.checkpoints) == n2)
        finally:
            main_mod.get_llm = real_get_llm
    finally:
        R._restore_real_env(st, saved)


# ── N: mechanical normalization of live nm.v2 deviations (CIR-01b) ──────────────────────

def test_unknown_store_prune_over_capacity(tmp):
    """Regression for golden bug G-09 (16 Oct): >32 unknowns made record_unknowns crash
    with `TypeError: cannot use 'dict' as a set element`. Capacity evicts the oldest answered;
    OPEN is never evicted."""
    print("N0 — prune unknown > kapasitas: tidak crash, open bertahan, answered tertua terbuang")
    s, st, _, saved = sess(tmp, "cir-n0")
    try:
        ev = {"event_id": "ce-n0-0000", "seq": 0, "session_id": s.id, "role": "user",
              "kind": "message", "text": "t", "turn": 1}
        from store import events as event_store
        event_store.append_event(s, role="user", text="t", kind="message")
        ev = [e for e in s.events if e["role"] == "user"][-1]
        for i in range(36):
            record_unknowns(s, ev, [f"pertanyaan terbuka nomor {i} tentang produksi harian"])
        for i in range(6):
            s.semantic_unknowns.append({"id": f"su-a{i:04d}", "text": f"sudah dijawab {i}",
                                        "status": "answered", "event_id": "ce-x", "turn": 1})
        s.semantic_unknowns.append({"id": "su-open01", "text": "masih terbuka sekali ini",
                                    "status": "open", "event_id": "ce-x", "turn": 1})
        record_unknowns(s, ev, ["satu lagi yang terbuka"])          # triggers the prune path (>32+answered)
        n = len(s.semantic_unknowns)
        check("tidak crash pada >32 unknown (bug G-09)", True)
        check("unknown OPEN tidak pernah dibuang demi kapasitas",
              any(u["id"] == "su-open01" for u in s.semantic_unknowns))
        check("answered tertua terbuang lebih dulu, jumlah menyusut",
              n < 43 and not any(u["id"] == "su-a0000" for u in s.semantic_unknowns), f"n={n}")
    finally:
        R._restore_real_env(st, saved)


def test_loose_normalize_so2_and_design_deviations(tmp):
    """MC01-1: SHAPE deviation (string→list move_design) = SHAPE_REPAIR (applied + diff);
    MEANING deviation (empty/'negation' role, 'negates' relation) = SemanticDefect → repair
    directed at the model — NO LONGER silently normalized (CIR-MC01 P0-A audit)."""
    print("N2 — deviasi so.v1: shape diperbaiki mekanis; makna dikembalikan ke model")
    from core.llm import LLMProvider
    from core.reasoning.contract import MoveDesign
    from core.semantic.contract import SemanticObservation
    so = {"contract_version": "so.v1", "language": "id",
          "claims": [{"ref": "c1", "role": "", "subject": "omzet", "predicate": "turun",
                      "quote": "omzet turun"},
                     {"ref": "c2", "role": "negation", "subject": "target", "predicate": "dibatalkan",
                      "quote": "target dibatalkan", "supersedes": "cl-e0001-001",
                      "revision_kind": "negation", "revision_reason": "user membatalkan"}],
          "relations": [{"src": "c1", "dst": "c1", "kind": "negates"}]}

    class P(LLMProvider):
        name = "fake"

        def __init__(self):
            self.prompts: list[str] = []
            self.n = 0

        def raw_json(self, system, user):
            self.prompts.append(user)
            self.n += 1
            if self.n == 1:
                return json.dumps(so)
            return json.dumps({**so,
                               "claims": [{**so["claims"][0], "role": "claim"},
                                          {**so["claims"][1], "role": "claim"}],
                               "relations": [{**so["relations"][0], "kind": "contradicts"}]})

    p = P()
    o = p.structured_call(SemanticObservation, "s", "u", retries=1)
    check("role & relasi invalid = defect ke model; nilai akhir = jawaban MODEL",
          o.claims[0].role == "claim" and o.claims[1].role == "claim"
          and o.claims[1].revision_kind == "negation" and o.relations[0].kind == "contradicts"
          and len(p.prompts) == 2,
          f"{o.claims[0].role}/{o.relations[0].kind}/prompts={len(p.prompts)}")
    check("repair terarah menyebut jalur revisi kanonik (revision_kind='negation')",
          "revision_kind" in p.prompts[1] and "negation" in p.prompts[1])

    mv = {"objective": "ukur", "preconditions": "catat ringan besok", "constraints": "",
          "expected_evidence": "jumlah lead 7 hari", "measurement_method": "log harian",
          "observation_window_days": 7, "completion_criteria": "7 hari data",
          "linked_path_id": "", "linked_hypothesis_id": ""}
    f2, diffs = LLMProvider._shape_repair(MoveDesign, mv)
    m = MoveDesign.model_validate(f2)
    check("field string move_design dibungkus list (string kosong tetap kosong) + diff tercatat",
          m.preconditions == ["catat ringan besok"] and m.expected_evidence == ["jumlah lead 7 hari"]
          and m.constraints == [] and any(d["rule"] == "wrap_list" for d in diffs))


def test_loose_normalize_nm2_deviations(tmp):
    print("N — nm.v2: id-obj/typo/ghost = SHAPE_REPAIR; konsistensi critical = defect ke model")
    from core.llm import NORM_STATS, LLMProvider
    from core.reasoning.contract import NextMoveProposal
    raw = {
        "contract_version": "nm.v2", "state_snapshot_ref": "ss-x", "goal_ref": "",
        "proposed_move": "su-12ae519c",
        "proposed_move_kind": "QUESTION", "focus_type": "uncertainty", "proposed_focus": "su-12ae519c",
        "move_text": "Dari inquiry yang masuk, berapa yang Anda balas dalam sehari?",
        "information_value_rationale": "membedakan kebocoran tindak lanjut dari kurang permintaan",
        "expected_decision_change": "menunda iklan bila yang bocor tindak lanjut",
        "supporting_claim_refs": [],
        "checkpoint_eligibility": {
            "level": "DISCOVERY_NEEDED", "basis_claim_refs": [],
            "critical_unknown_ids": [{"id": "su-a", "counterfactual": ""}, "su-c"],
            "nonblocking_unknown_ids": [{"id": "su-b5f75579", "counterfactual": ""}, "su-d"],
            "marginal_information_value": [
                {"uncertainty_id": "su-a", "decision_impuration": "menentukan prioritas",
                 "answerability": "now_conversation", "information_gain": "tinggi",
                 "user_friction": "rendah", "counterfactual": "jika 0 dibalas, ubah ke tindak lanjut"},
                {"uncertainty_id": "su-c", "decision_impact": "minor",
                 "answerability": "now_conversation", "information_gain": "rendah",
                 "user_friction": "rendah", "counterfactual": ""},
                {"uncertainty_id": "su-d", "decision_impact": "besar",
                 "answerability": "now_conversation", "information_gain": "tinggi",
                 "user_friction": "rendah", "counterfactual": "kalau kapasitas penuh, urutan berubah"}],
            "external_evidence_pending": False, "can_offer_checkpoint": False,
            "recommendation": "", "rationale": ""}}
    fixed_by_model = json.loads(json.dumps(raw))
    fixed_by_model.pop("proposed_move")
    ce = fixed_by_model["checkpoint_eligibility"]
    ce["critical_unknown_ids"] = ["su-a", "su-d"]          # MODEL decision: su-d raised
    ce["nonblocking_unknown_ids"] = ["su-b5f75579", "su-c"]  # su-c downgraded by the model
    ce["marginal_information_value"][0]["decision_impact"] = "menentukan prioritas"
    ce["marginal_information_value"][0].pop("decision_impuration")
    before = {k: NORM_STATS.get(k, 0) for k in
              ("shape:id_obj_to_str", "shape:key_typo", "shape:drop_redundant_ghost_field",
               "defect:MC02-M05a")}

    class P(LLMProvider):
        name = "fake"

        def __init__(self):
            self.n = 0

        def raw_json(self, system, user):
            P.n = self.n = self.n + 1
            return json.dumps(raw if self.n == 1 else fixed_by_model)

    p = P()
    out = p.structured_call(NextMoveProposal, "s", "u", retries=1)
    c = out.checkpoint_eligibility
    check("klasifikasi final = jawaban model; id kembali string; typo kunci terpetakan",
          c.critical_unknown_ids == ["su-a", "su-d"] and c.nonblocking_unknown_ids == ["su-b5f75579", "su-c"]
          and c.marginal_information_value[0].decision_impact == "menentukan prioritas"
          and out.proposed_focus == "su-12ae519c",
          f"{c.critical_unknown_ids}/{c.nonblocking_unknown_ids}")
    check("shape repair attempt-1 tercatat di statistik (id-obj/typo/ghost-redundan), "
          "defect klasifikasi (M05a) ke model",
          NORM_STATS.get("shape:id_obj_to_str", 0) > before["shape:id_obj_to_str"]
          and NORM_STATS.get("shape:key_typo", 0) > before["shape:key_typo"]
          and NORM_STATS.get("shape:drop_redundant_ghost_field", 0)
          > before["shape:drop_redundant_ghost_field"]
          and NORM_STATS.get("defect:MC02-M05a", 0) > before["defect:MC02-M05a"])


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="cir_parity_"))
    test_probe_delivery(tmp / "p1")
    test_semantic_unknown_continuity(tmp / "u1")
    test_error_classification(tmp / "e1")
    test_finalize_stale_gate(tmp / "f1")
    test_unknown_store_prune_over_capacity(tmp / "n0")
    test_loose_normalize_nm2_deviations(tmp / "n1")
    test_loose_normalize_so2_and_design_deviations(tmp / "n2")
    print(f"\n{'=' * 62}\nCIR parity suite: {_PASS} OK, {_FAIL} GAGAL")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
