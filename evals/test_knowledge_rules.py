"""Unit tests for internal-docs §8.4 (T1-T4): tier-1 predicates, single pipeline, consequences.

Deterministic — the LLM is replaced by a controlled FakeMatcher.
Run: .venv/bin/python evals/test_knowledge_rules.py   (from mvp/)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.schema.constraints import HypothesisState
from core.schema.evidence import EvidenceItem
from core.stages.knowledge_rules import (
    SOURCE_GROUPS,
    RuleMatch,
    RuleMatchSet,
    apply_rule_consequences,
    candidate_anti_patterns,
    candidate_rules,
    match_tier1,
    run_knowledge_rules,
)
from core.stages.rule_predicates import evaluate_predicate
from providers.base import LLMProvider


class FakeMatcher(LLMProvider):
    """structured_call returns a RuleMatchSet built from a controlled JSON payload."""

    name = "fake-matcher"

    def __init__(self, payload: str = '{"matches": [], "anti_patterns": []}'):
        self.payload = payload

    def raw_json(self, system: str, user: str) -> str:  # pragma: no cover
        return "{}"

    def structured_call(self, schema, system, user, retries=0):
        import json

        return schema.model_validate(json.loads(self.payload))


def _ranking():
    return [
        HypothesisState(constraint_id="R7.2", score=0.70, effective_score=0.70),
        HypothesisState(constraint_id="C6.3", score=0.55, effective_score=0.55),
        HypothesisState(constraint_id="C6.1", score=0.40, effective_score=0.40),
    ]


def _ev(signals):
    return [
        EvidenceItem(id=f"ev-{i}", signal=s, level="self_reported", topic="GOAL")
        for i, s in enumerate(signals, 1)
    ]


# --- 1. Predicate evaluator (T1) ---------------------------------------------

def test_predicate_operators():
    ev = _ev(["onboarding 8 langkah sebelum user lihat nilai", "churn 10 persen bulanan"])
    hay = "onboarding 8 langkah sebelum user lihat nilai"
    ok, cited, _ = evaluate_predicate({"text_contains_any": ["churn"]}, ev, hay)
    assert ok and cited == ["ev-2"]
    # absence-only → rejected (nothing can be cited, T3)
    ok, cited, reason = evaluate_predicate({"text_absent_pattern": "tidak ada frasa ini"}, ev, hay)
    assert not ok and "sitasi" in reason
    ok, _, _ = evaluate_predicate({"all_of": [
        {"text_contains_any": ["churn"]}, {"text_contains_any": ["onboarding"]}]}, ev, hay)
    assert ok
    ok, _, _ = evaluate_predicate({"none_of": [{"text_contains_any": ["churn"]}]}, ev, hay)
    assert not ok
    ok, _, _ = evaluate_predicate({"min_evidence_count": 3}, ev, hay)
    assert not ok  # only 2 evidence items
    # absence-only alone CANNOT pass (citation required) — combined with a positive branch it can
    ok, _, _ = evaluate_predicate({"evidence_level_absent": ["transactional"]}, ev, hay)
    assert not ok
    ok, cited, _ = evaluate_predicate({"all_of": [
        {"text_contains_any": ["churn"]},
        {"evidence_level_absent": ["transactional"]}]}, ev, hay)
    assert ok and cited == ["ev-2"]


def test_predicate_error_not_silently_false():
    ok, cited, reason = evaluate_predicate({"operator_tidak_ada": []}, _ev(["x"]), "")
    assert not ok and "predicate error" in reason


def test_match_without_citation_rejected():
    """T3: condition satisfied but nothing can be cited → rejected."""
    ok, cited, reason = evaluate_predicate({"text_absent_pattern": "apa pun"}, _ev(["x"]), "")
    assert not ok and "sitasi" in reason


# --- 2. Real tier-1 rules (T1) ------------------------------------------------

def test_tier1_tm_r04_does_not_fire_when_implications_quantified():
    """RC1 regression: TM-R04 used to be 'active' via a proxy even with quantified implications."""
    ev = _ev([
        "masalah utama adalah follow-up yang bocor",
        "proyeksi darurat keuangan dalam 3-6 bulan jika 0 lead baru, rugi Rp8 juta/bulan",
    ])
    out = {m.rule_id: m for m in match_tier1(ev, "")}
    assert out["TM-R04"].matched is False


def test_tier1_tm_r04_fires_when_no_quantification():
    ev = _ev(["masalah saya banyak keluhan dari user tapi saya tidak ukur apapun"])
    out = {m.rule_id: m for m in match_tier1(ev, "")}
    assert out["TM-R04"].matched is True
    assert out["TM-R04"].applied_to


def test_tier1_no_false_positive_on_fear_of_churn():
    """HK-R03 → judgment: 'takut klien churn' (afraid clients churn) is not actual churn."""
    ev = _ev(["alasan tidak menawarkan harga: takut klien churn"])
    ids = {m.rule_id for m in match_tier1(ev, "")}
    assert "HK-R03" not in ids  # no longer tier-1


def test_tier1_cs_r03_verification_foil():
    ev = _ev(["RFP dari staf purchasing, belum pernah bicara dengan direksi"])
    out = {m.rule_id: m for m in match_tier1(ev, "")}
    assert out["CS-R03"].matched is True


# --- 3. Coverage & source activation (T2/T4) ---------------------------------

def test_all_sources_active_for_diagnosis():
    from engine.knowledge import active_rule_sources

    # 10 sources since iter-22 (internal-docs Phase 1b):
    # TM,VP,CS,HK,PR,HG,SP,SF(none),LC,EM
    assert active_rule_sources() == {"TM", "VP", "CS", "HK", "PR", "HG", "SP", "LC", "EM"}


def test_no_ranking_gate_all_rules_are_candidates():
    """T2: candidates are no longer restricted to targets ∩ ranking."""
    from engine.knowledge import get_kb

    # every rule from every active source = a candidate (dynamic, survives book #7+)
    assert len(candidate_rules()) == len(get_kb()["rules"])  # 34 per Phase-0
    # CS/HK/PR/HG are active even though the ranking only touches R7.2 — previously CS failed the gate
    assert any(r["rule_id"].startswith("CS-") for r in candidate_rules())
    assert any(r["rule_id"].startswith(("PR-", "HG-")) for r in candidate_rules())


def test_candidate_group_filter():
    g = candidate_rules(("CS", "HK"))
    assert g and all(r["rule_id"].split("-")[0] in {"CS", "HK"} for r in g)
    assert candidate_anti_patterns(("CS",)) != []


def test_split_groups_partition_sources():
    flat = [s for grp in SOURCE_GROUPS for s in grp]
    assert flat.count("TM") == 1 and flat.count("HK") == 1


# --- 4. Infer map (T2) --------------------------------------------------------

def test_no_evidence_map_from_consequence_targets():
    """S1 regression guard: `consequence.targets` = MODULATION, not PRESENCE.

    TM-R08 (user has real commitment: a paid trial, testimonials) targets
    V2.4 "Value-Proof Gap" as a RAISE target — yet real commitment means the gap
    is SMALL. Lowering the presence of that target once pushed V2.4 up to
    ranking[0] and collapsed separation (S1: conf 0.635 -> 0.193).
    """
    from engine.knowledge import get_kb

    rule = get_kb()["rules"]["TM-R08"]
    assert rule["consequence"]["targets"], "rule ini memang punya targets"
    assert not (rule.get("evaluation") or {}).get("indicates"), "default: tanpa indicates"

    payload = RuleMatchSet(matches=[
        RuleMatch(rule_id="TM-R08", matched=True, applied_to="ev-1"),
    ]).model_dump_json()
    out = run_knowledge_rules(FakeMatcher(payload), _ev(["trial 2 minggu berbayar"]), "")
    assert "TM-R08" in out.matched_ids
    assert out.rule_evidence_map == {}, "modulasi tidak boleh dipetakan menjadi bukti"


def test_indicates_declaration_contributes_evidence_map():
    """Presence semantics must be DECLARED explicitly, not guessed."""
    from engine.knowledge import get_kb

    rule = get_kb()["rules"]["CS-R03"]
    before = dict(rule.get("evaluation") or {})
    rule["evaluation"] = {**before, "indicates": ["C6.1"]}
    try:
        ev = _ev(["RFP dari staf purchasing, belum pernah bicara dengan direksi"])
        out = run_knowledge_rules(FakeMatcher(), ev, "")
        assert "CS-R03" in out.matched_ids
        assert out.rule_evidence_map.get("C6.1"), "indicates eksplisit boleh memetakan bukti"
    finally:
        rule["evaluation"] = before


# --- 5. Tier-2 (LLM) + verification ------------------------------------------

def test_tier2_rejects_unknown_rule_id():
    payload = RuleMatchSet(matches=[
        RuleMatch(rule_id="FAKE-R99", matched=True, applied_to="ev-1"),
        RuleMatch(rule_id="CS-R01", matched=True, applied_to="ev-1"),
    ]).model_dump_json()
    out = run_knowledge_rules(FakeMatcher(payload), _ev(["klien manggut-manggut setuju"]), "")
    assert "FAKE-R99" not in out.matched_ids
    assert "CS-R01" in out.matched_ids


def test_tier2_match_without_citation_rejected():
    payload = RuleMatchSet(matches=[
        RuleMatch(rule_id="CS-R01", matched=True, applied_to=""),
    ]).model_dump_json()
    out = run_knowledge_rules(FakeMatcher(payload), _ev(["klien jadi"]), "")
    assert "CS-R01" not in out.matched_ids


def test_llm_failure_degrades_but_tier1_survives():
    class Boom(FakeMatcher):
        def structured_call(self, schema, system, user, retries=0):
            raise RuntimeError("provider down")

    ev = _ev(["RFP dari staf purchasing, belum pernah bicara dengan direksi"])
    out = run_knowledge_rules(Boom(), ev, "")
    assert out.degraded is True
    assert "CS-R03" in out.matched_ids, "tier-1 harus tetap jalan saat LLM mati"
    assert out.coverage.get("llm_failed_groups")


def test_coverage_reports_evaluated_and_matched():
    """Coverage must be FALSIFIABLE: 'requested' ≠ 'returned'.

    FakeMatcher returns 0 entries → tier-2 must not be counted as evaluated,
    and missing rules must be visible in tier2_missing.
    """
    from engine.knowledge import get_kb

    out = run_knowledge_rules(FakeMatcher(), _ev(["hal biasa"]), "")
    cov = out.coverage
    all_rules = get_kb()["rules"]
    det = [r for r in all_rules.values() if (r.get("evaluation") or {}).get("tier") == "deterministic"]
    jud = [r for r in all_rules.values() if (r.get("evaluation") or {}).get("tier") == "judgment"]
    assert cov["rules_enabled"] == len(all_rules)
    assert cov["tier1_evaluated"] == len(det)
    assert cov["tier2_requested"] == len(jud)
    assert cov["tier2_returned"] == 0     # the fake returns nothing
    assert len(cov["tier2_missing"]) == len(jud)
    assert cov["rules_evaluated"] == len(det)  # only the ones actually evaluated
    assert cov["by_source"]["HK"]["enabled"] == 4
    # iter-22: SP/LC/EM active — new sources must appear in by_source
    # F2 (internal-docs): SP deepened 4 → 10 rules; F2b: PR 4→8, HG 4→6, LC 4→6, VP 6→7
    assert cov["by_source"]["SP"]["enabled"] == 10
    assert cov["by_source"]["LC"]["enabled"] == 6
    assert cov["by_source"]["EM"]["enabled"] == 4
    assert det and jud, "KB harus punya kedua tier"


# --- 6. Consequences (deterministic) -----------------------------------------

def test_consequences_lower_and_resort():
    payload = RuleMatchSet(matches=[
        RuleMatch(rule_id="TM-R04", matched=True, applied_to="ev-1"),
    ]).model_dump_json()
    ev = _ev(["masalah tanpa implikasi terukur"])
    out = run_knowledge_rules(FakeMatcher(payload), ev, "")
    r = _ranking()
    apply_rule_consequences(r, out)
    c63 = next(h for h in r if h.constraint_id == "C6.3")
    assert c63.effective_score < 0.55
    assert "TM-R04" in out.extra_rule_ids


def test_consequences_block_verdict_recorded():
    payload = RuleMatchSet(matches=[
        RuleMatch(rule_id="HK-R02", matched=True, applied_to="ev-1"),
    ]).model_dump_json()
    out = run_knowledge_rules(FakeMatcher(payload), _ev(["onboarding berat"]), "")
    apply_rule_consequences(_ranking(), out)
    assert out.blocked  # R7.2 is blocked
    assert "VERDICT DIBLOKIR" in out.note


def test_consequences_max_one_penalty_per_target():
    payload = RuleMatchSet(matches=[
        RuleMatch(rule_id="TM-R04", matched=True, applied_to="ev-1"),
        RuleMatch(rule_id="TM-R01", matched=True, applied_to="ev-1"),
    ]).model_dump_json()
    out = run_knowledge_rules(FakeMatcher(payload), _ev(["masalah"]), "")
    r = _ranking()
    apply_rule_consequences(r, out)
    for h in r:
        assert h.effective_score >= 0.40 * 0.7 - 1e-9


def test_anti_pattern_note_requires_citation():
    payload = RuleMatchSet(anti_patterns=[
        {"pattern_id": "CS-A01", "matched": True, "applied_to": "ev-1", "reason": "pasif"},
        {"pattern_id": "CS-A03", "matched": True, "applied_to": "", "reason": "tanpa sitasi"},
    ]).model_dump_json()
    out = run_knowledge_rules(FakeMatcher(payload), _ev(["x"]), "")
    matched_ap = {a.pattern_id for a in out.anti_patterns if a.matched}
    assert matched_ap == {"CS-A01"}


def test_trace_has_no_proxy_attribution():
    """T3: the proxy attribution path was removed — no rule ID appears without a match."""
    from core.stages.confidence import applied_knowledge_rules

    assert applied_knowledge_rules(_ranking(), _ev(["x"])) == []


def test_matcher_hint_present_for_cs_hk_rules():
    from engine.knowledge import get_kb

    hinted = [r for r in get_kb()["rules"].values() if r.get("matcher_hint")]
    allr = get_kb()["rules"]
    # every rule must carry a matcher_hint (iter-22 convention)
    assert len(hinted) == len(allr)
    assert all("RECOUNTS" in r["matcher_hint"] for r in hinted)


def test_every_rule_declares_tier():
    from engine.knowledge import get_kb

    for rid, r in get_kb()["rules"].items():
        ev = r.get("evaluation") or {}
        assert ev.get("tier") in ("deterministic", "judgment"), rid
        if ev["tier"] == "deterministic":
            assert isinstance(ev.get("predicate"), dict), rid


def test_interventions_for_multiple_constraints():
    from engine.knowledge import interventions_for

    assert interventions_for("R7.2"), "HK interventions harus ter-lookup"
    assert interventions_for("DS4.2"), "TM interventions harus ter-lookup"


def test_tier1_cites_transcript_when_fact_not_extracted():
    """A fact can live in the user's own words without being extracted into an evidence item.

    The rule must still match citing a TRANSCRIPT QUOTE (auditable), and INFER
    must not use a transcript citation as an evidence id.
    """
    ev = [EvidenceItem(id="ev-1", signal="klien bayar bulanan", level="outcome", topic="GOAL")]
    tr = "Saya tidak tahu berapa margin bersih, model untungnya belum pasti."
    out = run_knowledge_rules(FakeMatcher(), ev, tr)
    assert "VP-R06" in out.matched_ids
    cite = next(m.applied_to for m in out.matched if m.rule_id == "VP-R06")
    assert cite.startswith('transcript:"')
    assert "D1.2" not in out.rule_evidence_map, "tanpa evidence id → tanpa bucket"


# --- 7. Guard robustness provider (iter-20c) ---------------------------------


def test_provider_coerces_string_into_list_field():
    """LLM sends a single string for a list field → do not fail the finalize.

    Proven to kill the whole finalize twice during the iter-20c eval (the `why` field).
    """
    from agents.diagnosis import DiagnosisDraft

    d = DiagnosisDraft.model_validate({
        "where_you_are": "x", "primary_constraint": "y", "primary_constraint_id": "V2.1",
        "why": "Empat bukti menunjuk arah yang sama.",
        "next_best_action": "a", "success_metric": "m", "well_know_when": "w",
        "pivot_rule": "p", "evidence_map": {},
        "secondary_constraints": "satu", "day_by_day": "H1: a\nH2: b",
    })
    assert d.why == ["Empat bukti menunjuk arah yang sama."]
    # J1 (internal-docs): string items are coerced into ActionItem(text=…)
    assert [it.text for it in d.day_by_day] == ["H1: a", "H2: b"]
    assert all(it.status == "TODO" for it in d.day_by_day)


def test_kb_validator_menangkap_predicate_deterministic_yang_cacat():
    """Audit of this iteration: the structural validator (validate_predicate_tree) now applies ALSO to
    deterministic rules' `evaluation.predicate` — not only disqualifiers. Broken operands/regex/types
    are caught at authoring time instead of being swallowed by the runtime evaluator and disguising
    themselves as "insufficient evidence"."""
    import json
    import shutil
    import tempfile
    from contextlib import redirect_stdout
    from io import StringIO

    import ontology.knowledge.validate_knowledge as vk
    from core.stages.rule_predicates import validate_predicate_tree

    # (a) unit: a wrongly-typed operand is caught by the structural validator
    errs = validate_predicate_tree({"text_contains_any": 42}, "u.predicate")
    assert errs and "text_contains_any" in errs[0], errs

    # (b) wiring: copy the KB to tmp, stick ONE broken predicate into a deterministic rule —
    # the KB validator must fail with an error pointing at that rule's `.predicate`
    tmp = Path(tempfile.mkdtemp(prefix="kb_predicate_cacat_"))
    real_kb = vk.KB
    try:
        shutil.copytree(real_kb, tmp / "knowledge")
        for f_parent in ("knowledge_schema.json", "constraints.json"):
            shutil.copy2(real_kb.parent / f_parent, tmp / f_parent)  # main() reads KB.parent too
        vk.KB = tmp / "knowledge"
        f_kb = next(vk.KB.glob("*_evidence_rules.json"))
        data = json.loads(f_kb.read_text(encoding="utf-8"))
        target = next(
            r for r in data["evidence_rules"]
            if (r.get("evaluation") or {}).get("tier") == "deterministic"
        )
        target["evaluation"]["predicate"] = {"all_of": [{"text_contains_any": 42}]}
        f_kb.write_text(json.dumps(data), encoding="utf-8")
        buf = StringIO()
        try:
            with redirect_stdout(buf):
                vk.main()
            raised = None
        except SystemExit as exc:
            raised = exc
        out = buf.getvalue()
        assert raised is not None and raised.code == 1, "KB tusbol harus gagal validasi"
        assert f"rule {target['rule_id']}" in out and ".predicate" in out, out[:400]
    finally:
        vk.KB = real_kb
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    import inspect

    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                failed += 1
                print(f"FAIL {name}: {e}")
    print("ALL PASS" if not failed else f"{failed} FAILED")
    sys.exit(1 if failed else 0)
