"""Test-lock mapper (LOCK contract 27 Sep + review revision 86f4299 B1-B4/H1-H2).
T6 (applicability -> RESOLVE_APPLICABILITY -> NextMove) = integration phase.

Run: python ontology/mapper/test_mapper.py  (exit 0 = PASS)
"""
from __future__ import annotations

import json
import sys
import tempfile as _tf  # noqa: E402
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))  # mvp/

from core.schema.evidence import EvidenceItem  # noqa: E402
from core.stages.adjudicate import adjudicate  # noqa: E402
from ontology.mapper import contract  # noqa: E402
from ontology.mapper.a3b_adapter import aggregate_a3b, build_precomputed, unit_outcomes  # noqa: E402

RULE_PARTIAL = {
    "mode": "PARTIAL",
    "sufficient": {"any_of": [{"text_contains_any": ["daftar prospek", "punya prospek"]}]},
    "partial": {"any_of": [{"text_contains_any": ["beberapa prospek"]}]},
    "no_decisive": {"any_of": [{"text_contains_any": ["__never__"]}]},
    "contradicting": {"any_of": [{"text_contains_any": ["tidak ada prospek"]}]},
}

REGISTRY = [
    {"requirement_id": "access.prospect_list",
     "definition": "Daftar prospek aktif memuat nama nyata beserta asal tiap entri.",
     "observability": ["Daftar prospek tersedia", "Entri memuat nama dan asal"],
     "satisfaction_rule": {"mode": "PARTIAL",
                           "sufficient": "Seluruh entri daftar prospek memuat "
                              "nama nyata dan asal yang jelas."}},
    {"requirement_id": "offering.exists",
     "definition": "Penawaran jasa atau produk dinyatakan.",
     "observability": ["Penawaran dinyatakan"],
     "satisfaction_rule": {"mode": "BINARY",
                           "sufficient": "Penawaran dinyatakan."}},
]
RIDS = {r["requirement_id"] for r in REGISTRY}
# BLOCKER-1 final (review 640680d): formal rules = ARTEFAK KOMPILASI
# REVIEWED (formal_compiler), NOT a free input predicate. bind_formal_
# rules (free input) are DEPRECATED — no path uses them anymore.
from ontology.mapper import formal_compiler  # noqa: E402


def _make_artifact(preds, compiled_by="test-compiler", review="test-review"):
    return {"access.prospect_list": {
        "predicates": preds, "compiled_by": compiled_by, "review": review,
        "source_rule_sha256": formal_compiler.rule_text_sha256(
            REGISTRY[0]["satisfaction_rule"])}}


def _artifact_file(artifact):
    f = _tf.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump(artifact, f)
    f.close()
    return f.name


ARTIFACT = _make_artifact(RULE_PARTIAL)
FORMAL_RULES = formal_compiler.compile_formal_rules(
    REGISTRY, _artifact_file(ARTIFACT))
contract.set_live_registry(REGISTRY)


def _ev(eid: str, text: str, is_gap: bool = False) -> EvidenceItem:
    return EvidenceItem(id=eid, signal=text, source_quote=text,
                        level="self_reported", topic="REVENUE_STATE",
                        is_gap=is_gap)


RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, fn) -> None:
    try:
        fn()
        RESULTS.append((name, True, ""))
    except Exception as exc:  # noqa: BLE001
        RESULTS.append((name, False, f"{type(exc).__name__}: {exc}"))


def t1_positive_mapping() -> None:
    ev = _ev("ev.1", "punya daftar prospek dari networking komunitas")
    idx = {ev.id: ev}
    props = contract.propose_deterministic(idx, REGISTRY)
    # B3 recall: WITHOUT cutoff — 5 candidates sharing a token ALL become proposals
    reg5 = [{"requirement_id": f"x.{i}",
             "definition": f"prospek variasi {i}", "observability": [],
             "satisfaction_rule": {"sufficient": "prospek"}} for i in range(5)]
    assert len(contract.narrow_candidates("prospek", reg5)) == 5, "B3 cutoff!"
    p = next(p for p in props if p["requirement_id"] == "access.prospect_list")
    vm = contract.verify_proposal(p, idx, RIDS, FORMAL_RULES)
    assert vm.get("verified") is True, vm
    assert set(vm) == {"requirement_id", "evidence_refs",
                       "verification_method", "verified", "verified_at"}, vm
    out = adjudicate("access.prospect_list", RULE_PARTIAL, [ev], [vm],
                     evaluation_time=1)
    assert out["status"] == "PRESENT", out  # by the RULE, not the mapper


def t2_no_match_unknown() -> None:
    ev = _ev("ev.9", "suka mendaki gunung akhir pekan")
    idx = {ev.id: ev}
    assert contract.propose_deterministic(idx, REGISTRY) == []
    out = adjudicate("access.prospect_list", RULE_PARTIAL, [ev], [],
                     evaluation_time=1)
    assert out["status"] == "UNKNOWN", out


def t3_gap_not_negative() -> None:
    ev = _ev("ev.2", "menolak menjawab pertanyaan itu", is_gap=True)
    idx = {ev.id: ev}
    vms = [contract.verify_proposal(p, idx, RIDS, FORMAL_RULES)
           for p in contract.propose_deterministic(idx, REGISTRY)]
    vms = [v for v in vms if v.get("verified")]
    out = adjudicate("access.prospect_list", RULE_PARTIAL, [ev], vms,
                     evaluation_time=1)
    assert out["status"] == "UNKNOWN", out  # gap != evidence of absence


def t3b_hazard_characterization() -> None:
    """KNOWN-HAZARD characterization (H1, upstream 7.11 debt — NOT patched
    in the mapper): gap text containing a predicate literal ('daftar prospek') can
    wrongly satisfy the sufficient branch -> PRESENT.
    CANARY: when upstream evidence-semantics is fixed, this test is
    PREDICTED TO FAIL — switch the expectation to UNKNOWN then (do not
    'fix' it with an allowlist in the mapper)."""
    ev = _ev("ev.2b", "menolak membicarakan daftar prospek", is_gap=True)
    idx = {ev.id: ev}
    vms = [contract.verify_proposal(p, idx, RIDS, FORMAL_RULES)
           for p in contract.propose_deterministic(idx, REGISTRY)]
    vms = [v for v in vms if v.get("verified")]
    assert vms, "kolisi harus lewat jalur ADMITTED (verified mapping)"
    out = adjudicate("access.prospect_list", RULE_PARTIAL, [ev], vms,
                     evaluation_time=1)
    assert out["status"] == "PRESENT", \
        f"kolisi substring §7.11 berubah perilaku — update canary ini: {out}"


def t4_structural_vs_unresolved() -> None:
    idx = {"ev.1": _ev("ev.1", "daftar prospek ada")}
    base = {"proposed_by": "t", "proposed_at": 1}
    # MALFORMED: field hilang / asing (status/polarity/unit_key) -> ValueError
    for bad in ({}, {"requirement_id": "x"},
                {**base, "requirement_id": "x", "evidence_refs": []},
                {**base, "requirement_id": "access.prospect_list",
                 "evidence_refs": ["ev.1"], "status": "PRESENT"},
                {**base, "requirement_id": "access.prospect_list",
                 "evidence_refs": ["ev.1"], "polarity": "NEGATIVE"},
                {**base, "requirement_id": "access.prospect_list",
                 "evidence_refs": ["ev.1"], "unit_key": "prospect:A"}):
        try:
            contract.verify_proposal(bad, idx, RIDS)
            raise AssertionError(f"malformed tak tertangkap: {bad!r}")
        except contract.MalformedMapping:
            pass
    # UNRESOLVED semantic = record
    u1 = contract.verify_proposal(
        {**base, "requirement_id": "tidak.ada", "evidence_refs": ["ev.1"]},
        idx, RIDS)
    assert u1.get("unresolved") and "INV-R6" in u1["reason"], u1
    u2 = contract.verify_proposal(
        {**base, "requirement_id": "access.prospect_list",
         "evidence_refs": ["hantu.99"]}, idx, RIDS, FORMAL_RULES)
    assert u2.get("unresolved") and "tak dikenal" in u2["reason"], u2
    # MICRO-GAP (review 019d1a9): empty envelope (the live artifact now
    # POPULATED phase-5) -> NO_FORMAL_RULE — NOT STALE. Tested via an envelope
    # INDEPENDENT sentinel from the state file (live-artifact per-rid binding
    # rejects the registry fixture — tested separately in phase-5 G).
    empty_env = {"fingerprint": "", "modes": {}, "rules": {},
                 "compiled_from": "NO_FORMAL_RULE"}
    u2b = contract.verify_proposal(
        {**base, "requirement_id": "access.prospect_list",
         "evidence_refs": ["ev.1"]}, idx, RIDS, empty_env)
    assert u2b.get("unresolved") and "NO_FORMAL_RULE" in u2b["reason"], u2b
    assert "STALE" not in u2b["reason"], u2b
    # T4c D-A2 TWO-GATE (review a602666 blocker-2): structural PASSES but
    # PROSE rule (without a formal predicate) -> UNRESOLVED, NOT VERIFIED
    u3 = contract.verify_proposal(
        {**base, "requirement_id": "offering.exists",
         "evidence_refs": ["ev.1"]}, idx, RIDS, FORMAL_RULES)
    assert u3.get("unresolved") and "PROSA" in u3["reason"], u3
    # T4d BLOCKER-1 (review e8951cb): an ARBITRARY rule (raw dict, not an
    # envelope) is REJECTED; a STALE fingerprint is rejected; a foreign rid is rejected
    raw = {"access.prospect_list": RULE_PARTIAL}
    u5 = contract.verify_proposal(
        {**base, "requirement_id": "access.prospect_list",
         "evidence_refs": ["ev.1"]}, idx, RIDS, raw)
    assert u5.get("unresolved") and "ENVELOPE" in u5["reason"], u5
    stale = FORMAL_RULES  # envelope valid; stale-ness via registry live
    reg_changed = json.loads(json.dumps(REGISTRY))  # DEEP copy (shallow
    # would mutate the REGISTRY satisfaction_rule via a shared dict)
    reg_changed[0]["satisfaction_rule"]["sufficient"] += " (diubah)"
    contract.set_live_registry(reg_changed)
    u6 = contract.verify_proposal(
        {**base, "requirement_id": "access.prospect_list",
         "evidence_refs": ["ev.1"]}, idx, RIDS, stale)
    assert u6.get("unresolved") and "STALE" in u6["reason"], u6
    contract.set_live_registry(REGISTRY)  # restore
    try:
        formal_compiler.compile_formal_rules(
            REGISTRY, _artifact_file({"asing.x": _make_artifact(
                RULE_PARTIAL)["access.prospect_list"]}))
        raise AssertionError("rid asing tak tertangkap")
    except formal_compiler.CompilationError:
        pass
    # POINT-1 (review 9ed8d13): dict injection REJECTED in the public API
    try:
        formal_compiler.compile_formal_rules(REGISTRY, ARTIFACT)
        raise AssertionError("dict injection lolos")
    except formal_compiler.CompilationError:
        pass
    # T4f PWN-STYLE (review 640680d): a PWN predicate can only enter via
    # the ARTIFACT — and an artifact without review provenance is REJECTED (authority
    # compilation = review, not free input)
    try:
        formal_compiler.compile_formal_rules(
            REGISTRY, _artifact_file(_make_artifact(
                RULE_PARTIAL | {"sufficient": {"any_of": [
                    {"text_contains_any": ["PWN"]}]}},
                compiled_by="", review="")))
        raise AssertionError("artefak tanpa provenance lolos")
    except formal_compiler.CompilationError:
        pass
    # PER-RID stale: the entry rule text changes -> the entry hash does not match
    reg2 = json.loads(json.dumps(REGISTRY))
    reg2[0]["satisfaction_rule"]["sufficient"] += " (revisi)"
    try:
        formal_compiler.compile_formal_rules(reg2, _artifact_file(ARTIFACT))
        raise AssertionError("stale per-rid tak tertangkap")
    except formal_compiler.CompilationError:
        pass
    # malformed operand (BLOCKER-2 final): regex int / operand wrong type
    bad_operand = {"sufficient": {"text_present_pattern": 123},
                   "partial": {"any_of": [{"text_contains_any": ["x"]}]},
                   "no_decisive": {"any_of": [{"text_contains_any": ["y"]}]},
                   "contradicting": {"any_of": [
                       {"text_contains_any": ["z"]}]}}
    try:
        formal_compiler.compile_formal_rules(
            REGISTRY, _artifact_file(_make_artifact(bad_operand)))
        raise AssertionError("malformed operand passed as a formal rule")
    except formal_compiler.CompilationError:
        pass
    # POINT-2 (review 9ed8d13): VALID operator + foreign sibling key
    # (previously ignored because a valid sibling existed) -> MALFORMED
    sibling = {"sufficient": {"any_of": [{"text_contains_any": ["x"]}],
                              "operator_typo": ["y"]},
               "partial": {"any_of": [{"text_contains_any": ["x"]}]},
               "no_decisive": {"any_of": [{"text_contains_any": ["y"]}]},
               "contradicting": {"any_of": [
                   {"text_contains_any": ["z"]}]}}
    try:
        formal_compiler.compile_formal_rules(
            REGISTRY, _artifact_file(_make_artifact(sibling)))
        raise AssertionError("unknown sibling key lolos")
    except formal_compiler.CompilationError:
        pass
    # POINT-3: purely-negative proof branch (none_of only) -> unauditable
    neg = {"sufficient": {"none_of": [{"min_evidence_count": 1}]},
           "partial": {"any_of": [{"text_contains_any": ["x"]}]},
           "no_decisive": {"any_of": [{"text_contains_any": ["y"]}]},
           "contradicting": {"any_of": [
               {"text_contains_any": ["z"]}]}}
    try:
        formal_compiler.compile_formal_rules(
            REGISTRY, _artifact_file(_make_artifact(neg)))
        raise AssertionError("proof murni-negatif lolos compilation")
    except formal_compiler.CompilationError:
        pass
    # T4e BLOCKER-2: broken predicate / branch not matching the mode -> authoring
    # failure (Malformed), NOT unresolved 'insufficient evidence'
    bad_pred = {"sufficient": {"operator_typo": ["x"]},
                "partial": {"any_of": [{"text_contains_any": ["x"]}]},
                "no_decisive": {"any_of": [{"text_contains_any": ["y"]}]},
                "contradicting": {"any_of": [{"text_contains_any": ["z"]}]}}
    try:
        formal_compiler.compile_formal_rules(
            REGISTRY, _artifact_file(_make_artifact(bad_pred)))
        raise AssertionError("operator rusak tak tertangkap")
    except formal_compiler.CompilationError:
        pass
    bin_rule = {"sufficient": {"any_of": [{"text_contains_any": ["x"]}]},
                "no_decisive": {"any_of": [{"text_contains_any": ["y"]}]},
                "contradicting": {"any_of": [{"text_contains_any": ["z"]}]}}
    try:  # REGISTRY prospect_list = PARTIAL; rule without partial -> mode-mismatch
        formal_compiler.compile_formal_rules(
            REGISTRY, _artifact_file(_make_artifact(bin_rule)))
        raise AssertionError("mode-mismatch tak tertangkap")
    except formal_compiler.CompilationError:
        pass
    # evidence does not satisfy any rule branch -> unresolved (gate B)
    never = {"sufficient": {"any_of": [{"text_contains_any": ["__never__"]}]},
             "partial": {"any_of": [{"text_contains_any": ["__never2__"]}]},
             "no_decisive": {"any_of": [{"text_contains_any": ["y"]}]},
             "contradicting": {"any_of": [{"text_contains_any": ["z"]}]}}
    env4 = formal_compiler.compile_formal_rules(
        REGISTRY, _artifact_file(_make_artifact(never)))
    u4 = contract.verify_proposal(
        {**base, "requirement_id": "access.prospect_list",
         "evidence_refs": ["ev.1"]}, idx, RIDS, env4)
    assert u4.get("unresolved") and "TIDAK terbukti" in u4["reason"], u4


def t4b_unit_sidecar_contract() -> None:
    """B1/B2: unit identity lives via a SIDECAR; a batch without a sidecar for a
    unit-requirement -> mapping UNRESOLVED; exact-key unit_context."""
    idx = {"ev.1": _ev("ev.1", "daftar prospek prospect A jelas")}
    base = {"proposed_by": "t", "proposed_at": 1}
    p_ok = {**base, "requirement_id": "access.prospect_list",
            "evidence_refs": ["ev.1"]}
    # WITHOUT sidecar -> unresolved (B1)
    batch = contract.verify_batch([p_ok], [], idx, RIDS, FORMAL_RULES)
    assert not batch["verified_mappings"] and len(batch["unresolved"]) == 1 \
        and "B1" in batch["unresolved"][0]["reason"], batch
    # WITH a valid sidecar -> mapping verified + live unit_context
    uc_ok = {**base, "requirement_id": "access.prospect_list",
             "evidence_refs": ["ev.1"], "unit_key": "prospect:A"}
    batch = contract.verify_batch([p_ok], [uc_ok], idx, RIDS, FORMAL_RULES)
    assert len(batch["verified_mappings"]) == 1, batch
    assert batch["unit_contexts"] == [{"requirement_id":
                                       "access.prospect_list",
                                       "unit_key": "prospect:A",
                                       "evidence_refs": ["ev.1"]}], batch
    # sidecar unit_key wrong domain -> unresolved
    uc_bad = {**uc_ok, "unit_key": "kesepakatan:K1"}
    batch = contract.verify_batch([p_ok], [uc_bad], idx, RIDS, FORMAL_RULES)
    assert batch["unresolved"] and not batch["verified_mappings"], batch
    # non-unit requirement + unit_key sidecar -> unresolved
    uc_nu = {**base, "requirement_id": "offering.exists",
             "evidence_refs": ["ev.1"], "unit_key": "prospect:A"}
    r = contract.verify_unit_context(uc_nu, idx, RIDS)
    assert r.get("unresolved"), r
    # ADVERSARIAL B1-exact: sidecar for ev.A MUST NOT verify
    # mapping ev.B (binding = requirement_id + refs-set EKSAK)
    evB = _ev("ev.B", "prospect B tidak ada prospek sama sekali")
    idx2 = {"ev.A": idx["ev.1"], "ev.B": evB}
    ucA = {**base, "requirement_id": "access.prospect_list",
           "evidence_refs": ["ev.A"], "unit_key": "prospect:A"}
    pB = {**base, "requirement_id": "access.prospect_list",
          "evidence_refs": ["ev.B"]}
    batch = contract.verify_batch([pB], [ucA], idx2, RIDS, FORMAL_RULES)
    assert not batch["verified_mappings"] and batch["unresolved"] \
        and "B1-exact" in batch["unresolved"][0]["reason"], batch


def t5_adapter_and_drift_lock() -> None:
    """T5 (honest label, review): 'A3b adapter + adjudicator precomputed
    integration' — NOT end-to-end unit mapping (that is T7).
    Drift-lock vs the CANONICAL FIXTURE a3b_cases.json (H2: not the old private fn
    test) + the old test must also == the fixture."""
    cases = json.loads(
        (Path(__file__).parent / "a3b_cases.json").read_text())["cases"]
    from ontology.adjudication.test_adjudication_path import _aggregate_a3b
    for c in cases:
        got_rt = aggregate_a3b(c["units"])
        got_spec = _aggregate_a3b(c["units"])
        assert got_rt == c["expected"], f"runtime != fixture: {c['ket']}"
        assert got_spec == c["expected"], f"spec-test != fixture: {c['ket']}"
    pre, conflicts = build_precomputed({"prospect:A": True,
                                        "prospect:B": False,
                                        "prospect:C": None})
    assert conflicts == [], conflicts
    ev = _ev("ev.3", "beberapa prospek sudah jelas")
    out = adjudicate("access.prospect_list", RULE_PARTIAL, [ev], [],
                     evaluation_time=1, precomputed_rule_evaluation=pre)
    assert out["status"] == "PARTIAL", out


def t7_unit_flow_end_to_end() -> None:
    """END-TO-END unit (B1 tertutup): evidence -> proposal -> batch(sidecar)
    -> unit grouping -> unit_outcomes (deterministik) -> A3b -> adjudicate."""
    evs = {
        "ev.A": _ev("ev.A", "prospect A punya daftar prospek jelas"),
        "ev.B": _ev("ev.B", "prospect B tidak ada prospek sama sekali"),
    }
    base = {"proposed_by": "t", "proposed_at": 1}
    # proposals = output of the REAL PROPONER (review 282cd29: not manual)
    proposals = [p for p in contract.propose_deterministic(evs, REGISTRY)
                 if p["requirement_id"] == "access.prospect_list"]
    assert len(proposals) == 2, proposals
    ucs = [
        {**base, "requirement_id": "access.prospect_list",
         "evidence_refs": ["ev.A"], "unit_key": "prospect:A"},
        {**base, "requirement_id": "access.prospect_list",
         "evidence_refs": ["ev.B"], "unit_key": "prospect:B"},
    ]
    batch = contract.verify_batch(proposals, ucs, evs, RIDS, FORMAL_RULES)
    assert len(batch["verified_mappings"]) == 2, batch
    uc_map = {u["unit_key"]: u["evidence_refs"] for u in batch["unit_contexts"]}
    unit_ev = {uk: [evs[r] for r in refs] for uk, refs in uc_map.items()}
    unit_ev["prospect:C"] = []  # unit without info -> None
    outcomes = unit_outcomes(RULE_PARTIAL, unit_ev)
    assert outcomes == {"prospect:A": "SATISFIED", "prospect:B": "FAILED",
                        "prospect:C": "UNKNOWN"}, outcomes
    pre, conflicts = build_precomputed(outcomes)
    assert conflicts == [], conflicts
    out = adjudicate("access.prospect_list", RULE_PARTIAL,
                     list(evs.values()), batch["verified_mappings"],
                     evaluation_time=1, precomputed_rule_evaluation=pre)
    assert out["status"] == "PARTIAL", out


def t8_unit_conflict_contract() -> None:
    """CONFLICT CONTRACT per-unit (review 282cd29 + test-proof review
    a602666): unit S-match AND C-match = CONFLICT — forbidden from entering A3b;
    build_precomputed -> (None, conflicts) FORCES fallback; the fallback
    is proven by ADMITTED verified mappings: S=true AND C=true +
    conflict refs populated (UNKNOWN by D-A1a CONFLICT, NOT by
    the absence of admitted evidence)."""
    evc = _ev("ev.X", "punya daftar prospek tapi tidak ada prospek jelas")
    evy = _ev("ev.Y", "prospect B punya daftar prospek jelas")
    uc = {"prospect:A": [evc], "prospect:B": [evy]}
    outcomes = unit_outcomes(RULE_PARTIAL, uc)
    assert outcomes["prospect:A"] == "CONFLICT", outcomes
    assert outcomes["prospect:B"] == "SATISFIED", outcomes
    pre, conflicts = build_precomputed(outcomes)
    assert conflicts == ["prospect:A"], conflicts
    assert pre is None, "GUARD: precomputed WAJIB None saat conflict"
    # fallback: real proposals -> verified mappings DI-ADMIT ->
    # requirement-level conflict PROVEN (not UNKNOWN-by-absence)
    idx = {"ev.X": evc, "ev.Y": evy}
    base = {"proposed_by": "t", "proposed_at": 1}
    proposals = [p for p in contract.propose_deterministic(idx, REGISTRY)
                 if p["requirement_id"] == "access.prospect_list"]
    ucs = [{**base, "requirement_id": "access.prospect_list",
            "evidence_refs": [k], "unit_key": f"prospect:{k[-1]}"}
           for k in idx]
    batch = contract.verify_batch(proposals, ucs, idx, RIDS, FORMAL_RULES)
    vms = batch["verified_mappings"]
    assert len(vms) == 2, batch  # kedua evidence DI-ADMIT
    out = adjudicate("access.prospect_list", RULE_PARTIAL,
                     list(idx.values()), vms, evaluation_time=1)
    assert out["status"] == "UNKNOWN", out
    assert out["rule_evaluation"]["sufficient"] is True, out
    assert out["rule_evaluation"]["contradicting"] is True, out
    assert out["conflict"]["present_evidence_refs"], out
    assert out["conflict"]["contradicting_evidence_refs"], out


def main() -> int:
    tests = [
        ("T1 positive-mapping (status oleh rule; recall no-cutoff)", t1_positive_mapping),
        ("T2 no-match -> UNKNOWN (!= ABSENT)", t2_no_match_unknown),
        ("T3 is_gap != NEGATIVE -> UNKNOWN", t3_gap_not_negative),
        ("T3b hazard-canary kolisi substring 7.11", t3b_hazard_characterization),
        ("T4 malformed(ValueError) vs unresolved", t4_structural_vs_unresolved),
        ("T4b unit sidecar contract (B1/B2 + B1-exact adversarial)", t4b_unit_sidecar_contract),
        ("T5 A3b adapter + precomputed + drift-lock fixture", t5_adapter_and_drift_lock),
        ("T7 unit flow end-to-end (proposer nyata, B1-exact)", t7_unit_flow_end_to_end),
        ("T8 unit-conflict S^C = CONFLICT (D-A1a)", t8_unit_conflict_contract),
    ]
    for name, fn in tests:
        check(name, fn)
    for name, ok, why in RESULTS:
        print(f"  {'✅' if ok else '❌'} {name}" + (f" | {why}" if why else ""))
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"\nMAPPER TEST: {passed}/{len(RESULTS)} PASS")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
