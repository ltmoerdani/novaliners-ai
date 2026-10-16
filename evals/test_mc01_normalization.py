"""MC01-1 — normalization authority boundary (CIR-MC01 audit P0-A, adversarial §7).

SHAPE_REPAIR  = proven mechanical repair that does not change meaning — applied, diff recorded.
MEANING_REPAIR = a semantic decision (role inference, relation-kind mapping, revision-kind
selection, focus selection, moving critical↔nonblocking, cross vocabulary) — MUST NOT
be applied silently: it must go back to the MODEL via a directed repair, or fail honestly.

Adversarial mapping of audit §7:
  A1 supersedes without revision_kind (user retracts a claim)  → MC01-M03
  A2 relation 'refines' is not assumed derived_from            → MC01-M02
  A3 empty proposed_focus with many candidates ≠ cands[0]      → MC01-M04
  A4 critical needing measurement is not silently demoted      → MC01-M05
  A6 empty role / 'negation' is not inferred as 'claim'        → MC01-M01
  A7 intent cross vocabulary ('SELF_REPORTED') is not mapped   → MC01-M06
  A8 evidence cross vocabulary ('fact') is not mapped          → MC01-M07
  (+ M08 list-of-string, shape preservation, immutability, telemetry, honest failure)
"""
import json
import sys

from core.llm import NORM_STATS, LLMProvider
from core.reasoning.contract import NextMoveProposal
from core.semantic.contract import SemanticObservation

_PASS, _FAIL = 0, 0


def check(name, ok, detail=""):
    global _PASS, _FAIL
    print(("  [OK] " if ok else "  [XX] ") + name + ("" if ok or not detail else f"  [{detail}]"))
    if ok:
        _PASS += 1
    else:
        _FAIL += 1


class _Scripted(LLMProvider):
    """Fake provider: a list of deterministic responses + a prompt recorder."""

    name = "fake"

    def __init__(self, responses):
        self.responses = [json.dumps(r) for r in responses]
        self.prompts: list[str] = []

    def raw_json(self, system, user):
        self.prompts.append(user)
        return self.responses.pop(0)


def _claim(ref="c1", role="claim", subj="omzet", pred="turun", quote="omzet turun", **kw):
    d = {"ref": ref, "role": role, "subject": subj, "predicate": pred, "quote": quote}
    d.update(kw)
    return d


def _so(claims, relations=None):
    return {"contract_version": "so.v1", "language": "id", "claims": claims,
            "relations": relations or [], "uncertainties": []}


def _nm(**kw):
    base = {"contract_version": "nm.v2", "state_snapshot_ref": "ss-x", "goal_ref": "",
            "proposed_move_kind": "QUESTION", "focus_type": "uncertainty", "proposed_focus": "su-1",
            "move_text": "Dari inquiry yang masuk, berapa yang Anda balas dalam sehari?",
            "information_value_rationale": "membedakan kebocoran tindak lanjut",
            "expected_decision_change": "menunda iklan bila yang bocor tindak lanjut",
            "supporting_claim_refs": []}
    base.update(kw)
    return base


def _marg(uid, counterfactual, answerability="now_conversation"):
    return {"uncertainty_id": uid, "decision_impact": "menentukan prioritas",
            "answerability": answerability, "information_gain": "tinggi",
            "user_friction": "rendah", "counterfactual": counterfactual}


def a1_supersedes_without_revision_kind():
    print("A1 — supersedes tanpa revision_kind (user membatalkan klaim): pilihan jenis revisi MILIK MODEL")
    bad = _so([_claim(role="claim", subj="target iklan", pred="dibatalkan",
                      quote="target iklan dibatalkan", supersedes="cl-e0001-001")])
    good = _so([_claim(role="claim", subj="target iklan", pred="dibatalkan",
                       quote="target iklan dibatalkan", supersedes="cl-e0001-001",
                       revision_kind="negation", revision_reason="user membatalkan target")])
    before = NORM_STATS.get("defect:MC01-M03", 0)
    p = _Scripted([bad, good])
    out = p.structured_call(SemanticObservation, "s", "u", retries=1)
    check("jenis revisi 'negation' berasal dari jawaban model (bukan auto-'refinement')",
          out.claims[0].revision_kind == "negation"
          and out.claims[0].revision_reason == "user membatalkan target",
          f"{out.claims[0].revision_kind}/{out.claims[0].revision_reason}")
    check("defect M03 terdeteksi & tercatat (tidak pernah diisi diam-diam)",
          NORM_STATS.get("defect:MC01-M03", 0) >= before + 1)
    check("repair terarah menyebut nilai sah revision_kind",
          "revision_kind" in p.prompts[1] and "'negation'" in p.prompts[1])


def a2_refines_not_derived_from():
    print("A2 — relasi 'refines' TIDAK diasumsikan 'derived_from'")
    bad = _so([_claim()], [{"src": "c1", "dst": "c1", "kind": "refines"}])
    good = _so([_claim()], [{"src": "c1", "dst": "c1", "kind": "derived_from"}])
    before = NORM_STATS.get("defect:MC01-M02", 0)
    p = _Scripted([bad, good])
    out = p.structured_call(SemanticObservation, "s", "u", retries=1)
    check("kind akhir = pilihan model sendiri ('derived_from' dari respons model)",
          out.relations[0].kind == "derived_from")
    check("defect M02 tercatat — pemetaan sinonim tidak lagi otomatis",
          NORM_STATS.get("defect:MC01-M02", 0) >= before + 1
          and "relations.0.kind" in p.prompts[1])


def a3_no_autofill_first_candidate():
    print("A3 — proposed_focus kosong + banyak kandidat: model MEMILIH (bukan cands[0] otomatis)")
    bad = _nm(proposed_focus="", candidate_uncertainty_ids=["su-1", "su-2"])
    good = _nm(proposed_focus="su-2", candidate_uncertainty_ids=["su-1", "su-2"])
    before = NORM_STATS.get("defect:MC01-M04", 0)
    p = _Scripted([bad, good])
    out = p.structured_call(NextMoveProposal, "s", "u", retries=1)
    check("fokus terpilih = su-2 (jawaban model), TERBUKTI bukan auto-fill cands[0]",
          out.proposed_focus == "su-2", out.proposed_focus)
    check("defect M04 tercatat + repair menawarkan daftar kandidat",
          NORM_STATS.get("defect:MC01-M04", 0) >= before + 1 and "su-2" in p.prompts[1])


def a4_no_silent_critical_reclass():
    print("A4 — critical↔nonblocking TIDAK dipindah diam-diam; reklasifikasi = keputusan model")
    bad = _nm(
        proposed_focus="su-x", candidate_uncertainty_ids=["su-x", "su-y"],
        checkpoint_eligibility={
            "level": "DISCOVERY_NEEDED", "basis_claim_refs": [],
            "critical_unknown_ids": ["su-x"],
            "nonblocking_unknown_ids": ["su-y"],
            "marginal_information_value": [
                _marg("su-x", "jika konversi nol, urutan berubah", answerability="needs_measurement"),
                _marg("su-y", "jika 0 dibalas, ubah ke tindak lanjut")],
            "external_evidence_pending": False, "can_offer_checkpoint": False,
            "recommendation": "", "rationale": ""})
    good = json.loads(json.dumps(bad))
    good["checkpoint_eligibility"]["critical_unknown_ids"] = ["su-y"]
    good["checkpoint_eligibility"]["nonblocking_unknown_ids"] = ["su-x"]
    before = NORM_STATS.get("defect:MC02-M05a", 0) + NORM_STATS.get("defect:MC02-M05b", 0)
    p = _Scripted([bad, good])
    out = p.structured_call(NextMoveProposal, "s", "u", retries=1)
    ce = out.checkpoint_eligibility
    check("klasifikasi final = jawaban model (su-y critical, su-x nonblocking)",
          ce.critical_unknown_ids == ["su-y"] and ce.nonblocking_unknown_ids == ["su-x"],
          f"{ce.critical_unknown_ids}/{ce.nonblocking_unknown_ids}")
    check("defect M05a (critical non-answerable) + M05b (nonblocking padahal material) tercatat",
          NORM_STATS.get("defect:MC02-M05a", 0) + NORM_STATS.get("defect:MC02-M05b", 0) > before
          and "su-x" in p.prompts[1] and "su-y" in p.prompts[1],
          f"a={NORM_STATS.get('defect:MC02-M05a')} b={NORM_STATS.get('defect:MC02-M05b')}")


def a6_no_role_inference():
    print("A6 — role kosong / 'negation' tidak diinferensi 'claim' oleh normalizer")
    bad = _so([_claim(ref="c1", role=""), _claim(ref="c2", role="negation", subj="target",
                                                 pred="dibatalkan", quote="target dibatalkan")])
    good = _so([_claim(ref="c1", role="claim"), _claim(ref="c2", role="claim", subj="target",
                                                       pred="dibatalkan", quote="target dibatalkan")])
    before = NORM_STATS.get("defect:MC01-M01", 0)
    p = _Scripted([bad, good])
    out = p.structured_call(SemanticObservation, "s", "u", retries=1)
    check("role final = jawaban model; tidak ada normalisasi diam-diam",
          [c.role for c in out.claims] == ["claim", "claim"])
    check("defect M01 tercatat 2x (role kosong + 'negation')",
          NORM_STATS.get("defect:MC01-M01", 0) >= before + 2)


def a7a8_no_cross_vocab_mapping():
    print("A7/A8 — kosakata silang intent/evidence tidak dipetakan; case-only tetap mekanis")
    from agents.interview import TurnExtraction
    dev = {"intent_tags": [{"kind": "fact", "quote": "q", "normalized": "n", "confidence": 0.9},
                           {"kind": "SELF_REPORTED", "quote": "q2", "normalized": "n2",
                            "confidence": 0.9}],
           "evidence": [{"id": "x", "signal": "s", "level": "fact", "topic": "DEMAND",
                         "is_gap": False}],
           "number_claims": []}
    fixed, diffs = LLMProvider._shape_repair(TurnExtraction, json.loads(json.dumps(dev)))
    defects = LLMProvider._semantic_defects(TurnExtraction, fixed)
    codes = [d.code for d in defects]
    check("case-only fix mekanis diterapkan ('fact'→FACT), tanpa menyentuh nilai lain",
          fixed["intent_tags"][0]["kind"] == "FACT"
          and fixed["intent_tags"][1]["kind"] == "SELF_REPORTED"
          and fixed["intent_tags"][1]["confidence"] == 0.9
          and any(d["rule"] == "case_fix" for d in diffs))
    check("'SELF_REPORTED' sebagai intent kind = M06 (bukan INTENT_KIND_MAP lama)",
          "MC01-M06" in codes and codes.count("MC01-M06") == 1)
    check("'fact' sebagai evidence level = M07 (bukan LEVEL_MAP lama)",
          "MC01-M07" in codes and fixed["evidence"][0]["level"] == "fact")


def m08_strings_not_objects():
    print("M08 — intent_tags/evidence list-of-string tidak difabrikasi jadi objek")
    from agents.interview import TurnExtraction
    dev = {"intent_tags": ["mau naik omzet"], "evidence": ["3 kantor langganan"],
           "number_claims": []}
    fixed, _ = LLMProvider._shape_repair(TurnExtraction, json.loads(json.dumps(dev)))
    defects = LLMProvider._semantic_defects(TurnExtraction, fixed)
    codes = [d.code for d in defects]
    check("string TIDAK dibungkus objek rekaan (level/confidence tidak difabrikasi)",
          fixed["intent_tags"] == ["mau naik omzet"] and fixed["evidence"] == ["3 kantor langganan"])
    check("dua defect M08 tercatat", codes.count("MC01-M08") == 2)


def a9_shape_repairs_preserved():
    print("A9 — SHAPE_REPAIR tetap menyelamatkan deviasi mekanis TANPA retry penuh")
    bad = _nm(
        proposed_move="su-9", candidate_uncertainty_ids=["su-9"], proposed_focus="su-9",
        checkpoint_eligibility={
            "level": "DISCOVERY_NEEDED", "basis_claim_refs": [],
            "critical_unknown_ids": [{"id": "su-9", "counterfactual": ""}],
            "nonblocking_unknown_ids": [],
            "marginal_information_value": [
                {"uncertainty_id": "su-9", "decision_impuration": "menentukan prioritas",
                 "answerability": "now_conversation", "information_gain": "tinggi",
                 "user_friction": "rendah", "counterfactual": "jika lead nol, strategi berubah"}],
            "external_evidence_pending": False, "can_offer_checkpoint": False,
            "recommendation": "", "rationale": ""},
        move_design={"objective": "ukur", "preconditions": "catat lead",
                     "constraints": "", "expected_evidence": "jumlah lead 7 hari",
                     "measurement_method": "log", "observation_window_days": 7,
                     "completion_criteria": "7 hari", "linked_path_id": "",
                     "linked_hypothesis_id": ""})
    before = {k: NORM_STATS.get(k, 0) for k in
              ("shape:wrap_list", "shape:id_obj_to_str", "shape:key_typo",
               "shape:drop_redundant_ghost_field")}
    p = _Scripted([bad])          # ONE response: must be accepted immediately
    out = p.structured_call(NextMoveProposal, "s", "u", retries=1)
    ce = out.checkpoint_eligibility
    check("1 panggilan LLM saja (tanpa retry penuh) & payload tervalidasi",
          len(p.prompts) == 1 and out.state_snapshot_ref == "ss-x", len(p.prompts))
    check("wrap/id-obj/typo/ghost-redundan semuanya bekerja (RC-01: ghost hanya bila redundan)",
          out.move_design.preconditions == ["catat lead"] and ce.critical_unknown_ids == ["su-9"]
          and ce.marginal_information_value[0].decision_impact == "menentukan prioritas"
          and NORM_STATS.get("shape:wrap_list", 0) > before["shape:wrap_list"]
          and NORM_STATS.get("shape:id_obj_to_str", 0) > before["shape:id_obj_to_str"]
          and NORM_STATS.get("shape:key_typo", 0) > before["shape:key_typo"]
          and NORM_STATS.get("shape:drop_redundant_ghost_field", 0)
          > before["shape:drop_redundant_ghost_field"])
    tel = p.last_norm_telemetry()
    check("telemetry: outcome=accepted, schema+raw_sha+diff tercatat",
          tel and tel["outcome"] == "accepted" and tel["schema"] == "NextMoveProposal"
          and len(tel["raw_sha"]) == 16 and len(tel["shape_diffs"]) >= 4
          and tel["defects"] == [])


def a12_deviasi_makna_kini_defect():
    print("A12 — RC-01: range tanpa batas / goal_ref placeholder / STATE_ONLY+offer = DEFECT (bukan shape)")
    before = {k: NORM_STATS.get(k, 0) for k in
              ("defect:MC02-M10", "defect:MC02-M11", "defect:MC02-M12",
               "defect:MC02-M05a", "defect:MC02-M09")}
    # 1) range without a bound → M10
    so = _so([_claim(quantity={"value_kind": "range", "value": 12, "unit": "juta"})])
    fixed, diffs = LLMProvider._shape_repair(SemanticObservation, json.loads(json.dumps(so)))
    codes = [d.code for d in LLMProvider._semantic_defects(SemanticObservation, fixed)]
    check("range tanpa low/high TIDAK lagi diturunkan ke 'approximate' oleh normalizer",
          "MC02-M10" in codes
          and not any(d["rule"] == "range_label_downgrade" for d in diffs)
          and fixed["claims"][0]["quantity"]["value_kind"] == "range")
    # 2) goal_ref placeholder → M11
    nm1 = _nm(goal_ref="goal", candidate_uncertainty_ids=["su-1"], proposed_focus="su-1")
    f1, _ = LLMProvider._shape_repair(NextMoveProposal, json.loads(json.dumps(nm1)))
    c1 = [d.code for d in LLMProvider._semantic_defects(NextMoveProposal, f1)]
    check("goal_ref='goal' TIDAK lagi dikosongkan diam-diam (M11)",
          "MC02-M11" in c1 and f1["goal_ref"] == "goal")
    # 3) STATE_ONLY + an offer → M12
    nm2 = _nm(candidate_uncertainty_ids=["su-1"], proposed_focus="su-1",
              checkpoint_eligibility={"level": "STATE_ONLY", "basis_claim_refs": [],
                                      "critical_unknown_ids": [], "nonblocking_unknown_ids": [],
                                      "marginal_information_value": [], "external_evidence_pending": False,
                                      "can_offer_checkpoint": True, "recommendation": "tawarkan",
                                      "rationale": ""})
    f2, _ = LLMProvider._shape_repair(NextMoveProposal, json.loads(json.dumps(nm2)))
    c2 = [d.code for d in LLMProvider._semantic_defects(NextMoveProposal, f2)]
    check("STATE_ONLY + can_offer/recommendation = M12 (level milik MODEL, bukan diturunkan normalizer)",
          "MC02-M12" in c2 and f2["checkpoint_eligibility"]["can_offer_checkpoint"] is True
          and f2["checkpoint_eligibility"]["recommendation"] == "tawarkan")
    # 4) M05 split: per-id cause recorded
    nm3 = _nm(candidate_uncertainty_ids=["su-a", "su-b"], proposed_focus="su-a",
              checkpoint_eligibility={
                  "level": "DISCOVERY_NEEDED", "basis_claim_refs": [],
                  "critical_unknown_ids": ["su-a"], "nonblocking_unknown_ids": [],
                  "marginal_information_value": [
                      {"uncertainty_id": "su-a", "decision_impact": "prioritas",
                       "answerability": "needs_measurement", "information_gain": "tinggi",
                       "user_friction": "rendah",
                       "counterfactual": "kalau kapasitas penuh, urutan berubah"}],
                  "external_evidence_pending": False, "can_offer_checkpoint": False,
                  "recommendation": "", "rationale": ""})
    f3, _ = LLMProvider._shape_repair(NextMoveProposal, json.loads(json.dumps(nm3)))
    d3 = LLMProvider._semantic_defects(NextMoveProposal, f3)
    m05a = next((d for d in d3 if d.code == "MC02-M05a"), None)
    check("M05a mencatat SEBAB per-id (answerability=needs_measurement) + arahan pengukuran",
          m05a is not None and "needs_measurement" in m05a.detail
          and "ACTION" in m05a.instruction,
          str(m05a))
    # 5) focus spanning two ids → M09 (not trimmed / auto-picked)
    nm4 = _nm(candidate_uncertainty_ids=["su-a", "su-b"],
              proposed_focus="su-a vs su-b karena kapasitas lebih penting")
    f4, _ = LLMProvider._shape_repair(NextMoveProposal, json.loads(json.dumps(nm4)))
    c4 = [d.code for d in LLMProvider._semantic_defects(NextMoveProposal, f4)]
    check("proposed_focus gabungan/naratif = M09; TIDAK dipotong & TIDAK auto-pilih hipotesis pertama",
          "MC02-M09" in c4 and f4["proposed_focus"] == "su-a vs su-b karena kapasitas lebih penting")
    # 6) stats rise via structured_call (M10 triggered → directed repair → model fixes it)
    bad_so = _so([_claim(quantity={"value_kind": "range", "value": 12, "unit": "juta"})])
    good_so = _so([_claim(quantity={"value_kind": "approximate", "value": 12, "unit": "juta"})])
    p = _Scripted([bad_so, good_so])
    out = p.structured_call(SemanticObservation, "s", "u", retries=1)
    check("M10 lewat structured_call: repair terarah (bukan potong/paksa) & statistik tercatat",
          out.claims[0].quantity.value_kind == "approximate"
          and NORM_STATS.get("defect:MC02-M10", 0) >= before["defect:MC02-M10"] + 1
          and "MC02-M10" not in p.prompts[1]
          and "low" in p.prompts[1],
          f"{out.claims[0].quantity.value_kind} / {NORM_STATS.get('defect:MC02-M10')}")


def a10_raw_payload_immutable():
    print("A10 — payload mentah TIDAK dimutasi; salinan aman dari mutasi nested")
    dev = {"contract_version": "so.v1", "language": "id",
           "claims": [_claim(role="Claim", quantity={"value_kind": "exact", "value": 12,
                                                     "unit": "juta", "period": None})]}
    frozen = json.loads(json.dumps(dev))
    fixed, diffs = LLMProvider._shape_repair(SemanticObservation, dev)
    check("input asli tidak berubah (deep-equal), output = objek berbeda",
          dev == frozen and fixed is not dev and fixed["claims"][0] is not dev["claims"][0])
    check("case-fix 'Claim'→'claim' + pop period-None tercatat sebagai diff",
          fixed["claims"][0]["role"] == "claim" and "period" not in fixed["claims"][0]["quantity"]
          and {d["rule"] for d in diffs} >= {"case_fix", "pop_null_default"})


def a11_failure_honest():
    print("A11 — model bandel mengulang defect → gagal jujur (tidak ada penyelamatan diam-diam)")
    bad = _so([_claim(role="")])
    before = NORM_STATS.get("outcome:failed", 0)
    p = _Scripted([bad, bad])
    try:
        p.structured_call(SemanticObservation, "s", "u", retries=1)
        check("harus raise setelah retry habis", False)
    except RuntimeError as exc:
        check("RuntimeError jujur + statistik outcome:failed naik",
              "structured_call gagal" in str(exc)
              and NORM_STATS.get("outcome:failed", 0) >= before + 1)


def main() -> int:
    a1_supersedes_without_revision_kind()
    a2_refines_not_derived_from()
    a3_no_autofill_first_candidate()
    a4_no_silent_critical_reclass()
    a6_no_role_inference()
    a7a8_no_cross_vocab_mapping()
    m08_strings_not_objects()
    a9_shape_repairs_preserved()
    a10_raw_payload_immutable()
    a12_deviasi_makna_kini_defect()
    a11_failure_honest()
    print(f"\n{'=' * 62}\nMC01-1 normalization authority: {_PASS} OK, {_FAIL} GAGAL")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
