"""Regression test — adjudication schema + deterministic adjudicator + ledger.

Contract: internal-docs §6 FINAL (D-A1a/A1b/A1c/A1d + D-A2).
Non-destructive: ledger/anomaly channel written to temporary files via monkeypatched
paths (backup/restore pattern of test_registry_path.py); production is untouched.

Run: cd mvp && python -m pytest ontology/adjudication/test_adjudication_path.py -q
     (or: python ontology/adjudication/test_adjudication_path.py)
"""
from __future__ import annotations

import sys
from pathlib import Path

MVP = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MVP))
sys.path.insert(0, str(MVP / "store"))

# PERMANENTLY NON-DESTRUCTIVE (Phase 6 wave-22): redirect both channels to tmp
# — without this the test writes to the PRODUCTION ledger/anomaly on every `make gate` run
# (waves 12-14 relied on manual deletion — not reliable in CI).
import tempfile as _tempfile  # noqa: E402

import adjudication_ledger as ledger  # noqa: E402  (from mvp/store via cwd)

_tmp = Path(_tempfile.mkdtemp(prefix="adjtest_"))
ledger._LEDGER_ROOT = _tmp  # PER-USER split 27 Sep: <root>/<user>/file
USER = "u-test"
from core.schema.evidence import EvidenceItem  # noqa: E402
from core.stages.adjudicate import adjudicate, check_precomputed  # noqa: E402
from ontology.adjudication.validate_adjudication import (  # noqa: E402
    AdjudicationValidationError,
    check_adjudication_output,
    check_rule_evaluation,
    expected_status,
)

# ------------------------------------------------------------ fixtures sinetis

RULE_PARTIAL = {
    "mode": "PARTIAL",
    "sufficient": {"any_of": [{"text_contains_any": ["sudah berlangganan", "paid customer"]}]},
    "partial": {"any_of": [{"text_contains_any": ["free trial", "demo"]}]},
    "no_decisive": {"any_of": [{"text_contains_any": ["__never__"]}]},
    "contradicting": {"any_of": [{"text_contains_any": ["belum tertarik", "cancel"]}]},
}
RULE_BINARY = {
    "mode": "BINARY",
    "sufficient": {"any_of": [{"text_contains_any": ["sudah berlangganan"]}]},
    "no_decisive": {"any_of": [{"text_contains_any": ["__never__"]}]},
    "contradicting": {"any_of": [{"text_contains_any": ["belum tertarik"]}]},
}


def _ev(eid: str, text: str) -> EvidenceItem:
    return EvidenceItem(id=eid, signal=text, source_quote=text,
                        level="self_reported", topic="REVENUE_STATE")


def _vm(requirement_id: str, refs: list[str],
        method: str = "human_reviewed") -> dict:
    """Synthetic VERIFIED mapping for the test (paste the line — E501)."""
    return {"requirement_id": requirement_id, "evidence_refs": refs,
            "verification_method": method, "verified": True, "verified_at": 1}


VM_OK = [{
    "requirement_id": "revenue.paying_customer",
    "evidence_refs": ["ev.1"],
    "verification_method": "deterministic_predicate",
    "verified": True,
    "verified_at": 1,
}]

RESULTS: list[tuple[str, bool, str]] = []


def _check(name: str, fn) -> None:
    try:
        fn()
        RESULTS.append((name, True, ""))
    except Exception as exc:  # noqa: BLE001
        RESULTS.append((name, False, f"{type(exc).__name__}: {exc}"))


# ------------------------------------------------------------ 1. totalitas (AD1)

def t_totalitas() -> None:
    ok = {"sufficient": False, "partial": False,
          "no_decisive": True, "contradicting": False}
    check_rule_evaluation(ok)
    for bad, why in (
        ({"sufficient": False, "partial": False,
          "no_decisive": False, "contradicting": False}, "all-false"),
        ({"sufficient": False, "partial": False,
          "no_decisive": True, "contradicting": True}, "no_decisive+contradicting"),
        ({"sufficient": True, "partial": False,
          "no_decisive": True, "contradicting": False}, "no_decisive+sufficient"),
    ):
        try:
            check_rule_evaluation(bad)
            raise AssertionError(f"harus ditolak: {why}")
        except AdjudicationValidationError:
            pass


# ------------------------------------------------------------ 2. exclusivity (AD2/D-A1c)

def t_exclusivity() -> None:
    try:
        bad = {"sufficient": True, "partial": True,
               "no_decisive": False, "contradicting": False}
        check_rule_evaluation(bad)
        raise AssertionError("S∧P harus INVALID (ditolak, bukan precedence)")
    except AdjudicationValidationError:
        pass
    # the evaluator NEVER produces S∧P: partial enough + sufficient enough → partial forced false
    out = adjudicate(
        "revenue.paying_customer", RULE_PARTIAL,
        [_ev("ev.1", "sudah berlangganan sejak 2024"), _ev("ev.2", "pernah free trial")],
        VM_OK + [_vm("revenue.paying_customer", ["ev.2"])],
        evaluation_time=100,
    )
    assert out["rule_evaluation"]["sufficient"] is True and out["rule_evaluation"]["partial"] is False
    assert out["status"] == "PRESENT"


# ------------------------------------------------------------ 3. full D-A1b resolution

def t_resolusi() -> None:
    cases = [
        ({"sufficient": True, "partial": False, "no_decisive": False, "contradicting": False}, "PRESENT"),
        ({"sufficient": False, "partial": True, "no_decisive": False, "contradicting": False}, "PARTIAL"),
        ({"sufficient": False, "partial": False, "no_decisive": True, "contradicting": False}, "UNKNOWN"),
        ({"sufficient": False, "partial": False, "no_decisive": False, "contradicting": True}, "ABSENT"),
        ({"sufficient": True, "partial": False,
          "no_decisive": False, "contradicting": True}, "UNKNOWN"),  # conflict
        ({"sufficient": False, "partial": True,
          "no_decisive": False, "contradicting": True}, "UNKNOWN"),  # conflict
    ]
    for rev, want in cases:
        assert expected_status(rev) == want, (rev, want)


def t_conflict_dua_sisi() -> None:
    out = adjudicate(
        "revenue.paying_customer", RULE_PARTIAL,
        [_ev("ev.1", "sudah berlangganan"), _ev("ev.2", "dia bilang cancel")],
        VM_OK + [_vm("revenue.paying_customer", ["ev.2"], "second_pass_verified")],
        evaluation_time=100,
    )
    assert out["status"] == "UNKNOWN"
    assert out["conflict"]["present_evidence_refs"] == ["ev.1"]
    assert out["conflict"]["contradicting_evidence_refs"] == ["ev.2"]


def t_conflict_101_ref_integritas() -> None:
    """BLOCKER review wave-13: the referential check applies to 101 (sufficient)
    TOO — previously only 011 (partial) was checked (asymmetry of line 116)."""
    out = adjudicate(
        "revenue.paying_customer", RULE_PARTIAL,
        [_ev("ev.1", "sudah berlangganan"), _ev("ev.2", "dia bilang cancel")],
        VM_OK + [_vm("revenue.paying_customer", ["ev.2"])],
        evaluation_time=100,
    )
    assert out["rule_evaluation"]["sufficient"] is True  # kasus 101
    # forge a 101 record with a present ref outside evidence_refs → REJECTED AD3
    forged = dict(out, conflict={
        "present_evidence_refs": ["ev.hantu"],
        "contradicting_evidence_refs": out["conflict"]["contradicting_evidence_refs"],
    })
    try:
        check_adjudication_output(forged, rule_mode="PARTIAL")
        raise AssertionError("kasus 101 dgn ref liar harus ditolak (asimetri fixed)")
    except AdjudicationValidationError as exc:
        assert "AD3" in str(exc)


# ------------------------------------------------------------ 4. RR11 + D-A2 gate

def t_rr11_partial_mode() -> None:
    out = adjudicate(
        "revenue.paying_customer", RULE_BINARY,
        [_ev("ev.1", "masih free trial doang")],
        [], evaluation_time=100,
    )
    # BINARY without a partial branch → partial is never true
    assert out["rule_evaluation"]["partial"] is False


def t_da2_gate() -> None:
    # verified=false -> not admitted -> evidence not visible to the adjudicator
    out = adjudicate(
        "revenue.paying_customer", RULE_PARTIAL,
        [_ev("ev.1", "sudah berlangganan")],
        [{**VM_OK[0], "verified": False}],
        evaluation_time=100,
    )
    assert out["status"] == "UNKNOWN"  # UNKNOWN by absence of non-admitted evidence
    # malformed: ref points to missing evidence -> ValueError (not an anomaly)
    # (requirement_id matches — mappings outside the scope are skipped first by admission)
    try:
        adjudicate("r.x", RULE_PARTIAL, [_ev("ev.1", "x")],
                   [{**VM_OK[0], "requirement_id": "r.x", "evidence_refs": ["ev.gakada"]}],
                   evaluation_time=100)
        raise AssertionError("malformed input harus ditolak")
    except ValueError:
        pass


# ------------------------------------------------------------ 5. D-A1d anomaly

def t_anomaly_channel() -> None:
    anom = check_precomputed(
        {"sufficient": True, "partial": True, "no_decisive": False, "contradicting": False},
        "revenue.paying_customer",
    )
    assert anom is not None and "INVALID" in anom["reason"] or "AD2" in anom["reason"]
    assert "status" not in anom and "rule_evaluation" not in anom or anom.get("detail")
    valid_rev = {"sufficient": True, "partial": False,
                 "no_decisive": False, "contradicting": False}
    assert check_precomputed(valid_rev, "r.x") is None


# ------------------------------------------------------------ 6. ledger (AD6/AD7, non-destruktif)

def t_ledger() -> None:
    out = adjudicate(
        "revenue.paying_customer", RULE_PARTIAL,
        [_ev("ev.1", "sudah berlangganan")], VM_OK, evaluation_time=100,
    )
    row = ledger._record_adjudication(USER, out, rule_mode="PARTIAL")
    assert row is not None and row["adjudication"]["status"] == "PRESENT"
    assert ledger.latest_status(USER, "revenue.paying_customer") == "PRESENT"
    # invalid record does NOT enter the ledger (S∧P)
    bad = dict(out, status="PARTIAL")
    bad["rule_evaluation"] = dict(out["rule_evaluation"])
    bad["rule_evaluation"]["partial"] = True  # S∧P invalid
    assert ledger._record_adjudication(USER, bad, rule_mode="PARTIAL") is None
    # anomaly channel terpisah
    anom = check_precomputed(bad["rule_evaluation"], "revenue.paying_customer")
    ledger._record_anomaly(USER, anom)
    assert ledger.read_anomalies(USER, "revenue.paying_customer")
    # UNKNOWN by absence
    assert ledger.latest_status(USER, "revenue.tidak_ada") is None


# ------------------------------------------------------------ 7. wave-13 hardening break tests

def t_scope_admission() -> None:
    """BLOCKER: SCOPED admission — a mapping owned by another requirement is not admitted."""
    # VM for another requirement carries ev.1; adjudication of the other r. must not see it
    out = adjudicate(
        "r.lain", RULE_PARTIAL,
        [_ev("ev.1", "sudah berlangganan")],
        [{**VM_OK[0], "requirement_id": "r.tujuan"}],  # owned by ANOTHER requirement
        evaluation_time=100,
    )
    assert out["status"] == "UNKNOWN", "evidence requirement lain bocor ke adjudication r.lain!"
    # sanity: with a matching requirement_id, evidence is visible
    out_ok = adjudicate(
        "r.lain", RULE_PARTIAL,
        [_ev("ev.1", "sudah berlangganan")],
        [{**VM_OK[0], "requirement_id": "r.lain"}],
        evaluation_time=100,
    )
    assert out_ok["status"] == "PRESENT"


def t_exact_keys() -> None:
    """BLOCKER: additionalProperties=false is ENFORCED — _rule_mode rejected;
    the evaluator output itself is clean of _rule_mode."""
    out = adjudicate(
        "revenue.paying_customer", RULE_PARTIAL,
        [_ev("ev.1", "sudah berlangganan")], VM_OK, evaluation_time=100,
    )
    assert "_rule_mode" not in out, "output masih memuat _rule_mode (tidak ada di schema)"
    # record with an extra field → rejected by the validator
    try:
        check_adjudication_output({**out, "_rule_mode": "PARTIAL"}, rule_mode="PARTIAL")
        raise AssertionError("_rule_mode ekstra harus ditolak (additionalProperties=false)")
    except AdjudicationValidationError:
        pass
    # the ledger also rejects (defense-in-depth)
    assert ledger._record_adjudication(USER, {**out, "_rule_mode": "PARTIAL"}, rule_mode="PARTIAL") is None


def t_da1d_atomic() -> None:
    """BLOCKER: D-A1d end-to-end — the pipeline cannot produce an adjudication
    from invalid input; anomaly route + no ledger entry are forced atomic."""
    row = ledger.adjudicate_and_persist(
        USER,
        "revenue.atomic", RULE_PARTIAL,
        [_ev("ev.1", "sudah berlangganan")], VM_OK, evaluation_time=100,
        precomputed_rule_evaluation={"sufficient": True, "partial": True,
                                      "no_decisive": False, "contradicting": False},
    )
    assert "anomaly_id" in row, "S∧P harus menghasilkan anomaly, bukan ledger entry"
    assert ledger.latest_status(USER, "revenue.atomic") is None, "anomaly tak boleh menciptakan status"
    # valid path through the same door → ledger entry
    # (the VM must scope to this requirement — scoped admission, see t_scope_admission)
    vm_atomic = {**VM_OK[0], "requirement_id": "revenue.atomic"}
    row_ok = ledger.adjudicate_and_persist(
        USER,
        "revenue.atomic", RULE_PARTIAL,
        [_ev("ev.1", "sudah berlangganan")], [vm_atomic], evaluation_time=100,
    )
    assert "entry_id" in row_ok and ledger.latest_status(USER, "revenue.atomic") == "PRESENT"


def t_malformed_sebelum_verified() -> None:
    """BLOCKER: structural = a PREREQUISITE for ALL paths — verified=false does not
    save a malformed object (method typo / missing field)."""
    for bad_vm in (
        {**VM_OK[0], "verification_method": "TYPO"},           # wrong enum
        {k: v for k, v in VM_OK[0].items() if k != "verified_at"},  # field hilang
        {**VM_OK[0], "evidence_refs": []},                      # empty refs
    ):
        try:
            adjudicate("revenue.paying_customer", RULE_PARTIAL,
                       [_ev("ev.1", "sudah berlangganan")],
                       [{**bad_vm, "verified": False}], evaluation_time=100)
            raise AssertionError(f"malformed verified=false lolos: {sorted(bad_vm)}")
        except ValueError:
            pass


def t_proposed_mapping_structural() -> None:
    """GAP: check_full_record validates the PROPOSED structure, not just the container."""
    from ontology.adjudication.validate_adjudication import check_proposed_mapping

    good = {"proposed_by": "llm:mapper-v1", "requirement_id": "r.x",
            "evidence_refs": ["ev.1"], "proposed_at": 1}
    check_proposed_mapping(good)  # valid → no exception
    for bad in (
        {k: v for k, v in good.items() if k != "proposed_by"},
        {**good, "evidence_refs": []},
        {**good, "verified": True},  # VERIFIED field leaks into PROPOSED → rejected
    ):
        try:
            check_proposed_mapping(bad)
            raise AssertionError(f"proposed_mapping malformed lolos: {sorted(bad)}")
        except AdjudicationValidationError:
            pass


# ------------------------------------------------------------ 8. wave-14 break tests

def t_rr11_konteks_ledger() -> None:
    """BLOCKER review wave-14: ledger revalidation of the KEY needs the
    rule_mode context — a BINARY+partial=true+status=PARTIAL record is REJECTED in the ledger,
    not passed without a check (regression of the _rule_mode removal)."""
    out = adjudicate(
        "revenue.biner", RULE_BINARY,
        [_ev("ev.1", "sudah berlangganan")],
        [{**VM_OK[0], "requirement_id": "revenue.biner"}], evaluation_time=100,
    )
    assert out["status"] == "PRESENT"
    # forge a BINARY record carrying partial=true + status=PARTIAL
    forged = dict(out, status="PARTIAL")
    forged["rule_evaluation"] = {"sufficient": False, "partial": True,
                                  "no_decisive": False, "contradicting": False}
    # with BINARY context → REJECTED (RR11 active in the ledger)
    assert ledger._record_adjudication(USER, forged, rule_mode="BINARY") is None
    # without context → now it CANNOT be called at all (mandatory argument)
    try:
        ledger._record_adjudication(USER, forged)  # type: ignore[call-arg]
        raise AssertionError("rule_mode wajib — default None dilarang (melumpuhkan RR11)")
    except TypeError:
        pass
    # context outside the enum → rejected by the validator
    from ontology.adjudication.validate_adjudication import check_ledger_entry
    try:
        check_ledger_entry({"entry_id": "e1", "adjudication": out}, rule_mode="TRIAGE")
        raise AssertionError("rule_mode di luar {BINARY, PARTIAL} harus ditolak")
    except AdjudicationValidationError:
        pass


def t_api_write_boundary() -> None:
    """BLOCKER review wave-14: the ledger module's public surface = 1 write
    (adjudicate_and_persist, atomic) + readers — write primitives are private.
    M4 (2 Oct 2026): `latest_entry` = a NEW reader (full entry: citations/timestamp/conflict)
    for the Requirement State Reader; READ-only access, it does not open a write door.
    The list stays EXACT: new public names must be deliberate."""
    # Gate A (15 Oct): `requirement_ids_with_entries` = NEW reader (per-user rid enumeration,
    # read-only) for post-supersession invalidation — a DELIBERATE public addition.
    assert set(ledger.__all__) == {
        "adjudicate_and_persist", "latest_entry", "latest_status", "read_anomalies",
        "requirement_ids_with_entries"}
    assert ledger.latest_entry(USER, "revenue.tidak_pernah_ditulis") is None
    assert not hasattr(ledger, "record_adjudication")
    assert not hasattr(ledger, "record_anomaly")
    # the invalid path ONLY produces an anomaly through the atomic door
    row = ledger.adjudicate_and_persist(
        USER,
        "revenue.boundary", RULE_PARTIAL,
        [_ev("ev.1", "sudah berlangganan")], VM_OK, evaluation_time=100,
        precomputed_rule_evaluation={"sufficient": False, "partial": False,
                                      "no_decisive": False, "contradicting": False},
    )
    assert "anomaly_id" in row and "entry_id" not in row
    assert ledger.latest_status(USER, "revenue.boundary") is None
    # rule without mode → malformed input (ValueError), not an anomaly, not an entry
    try:
        ledger.adjudicate_and_persist(
            USER,
            "revenue.boundary", {"sufficient": {}, "no_decisive": {}, "contradicting": {}},
            [_ev("ev.1", "x")], [], evaluation_time=100,
        )
        raise AssertionError("rule tanpa mode harus ditolak (RR11 butuh konteks)")
    except ValueError as exc:
        assert "mode" in str(exc)


# ------------------------------------------------------------ 10. spesifikasi A3b (review batch-1)

def _aggregate_a3b(units: list) -> dict:
    """PARTIAL aggregation SPECIFICATION (owner verdict 27 Sep, review f86ae3a) —
    unit: True = predicate satisfied · False = unit EXISTS but is KNOWN to fail
    (per-unit negative evidence) · None = not yet known. The predicate computed
    is the SAME in all branches; negative evidence is DERIVED from unit status, NOT a
    separate flag.

    Unit-not-yet-known policy (int 09 §8.4 A3b):
      all known & satisfied           -> sufficient
      >=1 satisfied & >=1 known failed -> partial (proven on both sides)
      all known & all failed           -> contradicting
      some not yet known (outside proven partial) -> no_decisive
    Proven PARTIAL does NOT require all units to be known: one unit
    proven failed negates PRESENT, one proven satisfied negates
    ABSENT — unknown units cannot change those two conclusions (review
    e1bb68b: [True,False,None] = PARTIAL, not UNKNOWN).
    Empty set = a PER-ENTRY decision (prospect_list: ABSENT via the rule
    entry; commitment_obtained/baseline_comparison: vacuous) — NOT this
    generic function's concern; return no_decisive.

    Honest note: the runtime adapter (mechanism [1] mapping unit -> 4-bool)
    does NOT yet exist in production — this function locks the aggregation
    SPECIFICATION as a test. Run its result through the REAL adjudication pipeline
    (adjudicate + precomputed) so the pattern is tested end-to-end.
    """
    known = [u for u in units if u is not None]
    ok = [u for u in known if u is True]
    fail = [u for u in known if u is False]
    if not known:                                # empty / all unknown
        return {"sufficient": False, "partial": False,
                "no_decisive": True, "contradicting": False}
    if len(ok) == len(units):                    # ALL units known & satisfied
        return {"sufficient": True, "partial": False,
                "no_decisive": False, "contradicting": False}
    if ok and fail:
        # PARTIAL PROVEN: >=1 satisfied & >=1 known failed — unknown units
        # do not negate these two conclusions (review e1bb68b)
        return {"sufficient": False, "partial": True,
                "no_decisive": False, "contradicting": False}
    if fail and len(fail) == len(units):         # all known, ZERO satisfied
        return {"sufficient": False, "partial": False,
                "no_decisive": False, "contradicting": True}
    return {"sufficient": False, "partial": False,   # some unknown units remain
            "no_decisive": True, "contradicting": False}


def t_a3b_aggregation_spec() -> None:
    """Break-test A3b (owner verdict 27 Sep): multi-unit aggregation -> the LOCKED
    status, end-to-end through the adjudication pipeline."""
    kasus = [
        # (units, expected_status, keterangan)
        ([True, True, True], "PRESENT", "ALL unit terpenuhi"),
        ([True, False, True], "PARTIAL", "campuran terbukti dua sisi"),
        ([False, False, False], "ABSENT", "semua diketahui, NOL memenuhi"),
        ([None, None], "UNKNOWN", "tanpa informasi memadai"),
        ([True, False], "PARTIAL", "kasus pemicu batch-1: A penuh + B DIKETAHUI gagal"),
        ([True, None], "UNKNOWN", "A terpenuhi + B belum diketahui — BUKAN PARTIAL (penghalang palsu, RR10)"),
        ([False, None], "UNKNOWN",
         "B diketahui gagal + satu unit belum diketahui — bukti negatif tunggal tak cukup ABSENT"),
        ([True, False, None], "PARTIAL",
         "PARTIAL terbukti dua sisi + sisa unknown — gagal terbukti meniadakan "
         "PRESENT, terpenuhi meniadakan ABSENT (review e1bb68b)"),
        ([], "UNKNOWN", "himpunan kosong: generik = UNKNOWN; per-entri via rule (prospect_list: ABSENT)"),
    ]
    for units, want, ket in kasus:
        rev = _aggregate_a3b(units)
        # 4-bool MUST be valid against the contract (AD1 totality + AD2 exclusivity)
        check_rule_evaluation(rev)
        assert expected_status(rev) == want, f"{ket}: {rev} -> {expected_status(rev)}, want {want}"
        # end-to-end: the adjudication pipeline produces the same status
        out = adjudicate(
            "access.prospect_list", RULE_PARTIAL,
            [_ev("ev.1", "sudah berlangganan"), _ev("ev.2", "pernah free trial"),
             _ev("ev.3", "dia bilang cancel")],
            [{**VM_OK[0], "requirement_id": "access.prospect_list",
              "evidence_refs": ["ev.1", "ev.2", "ev.3"]}],
            evaluation_time=100, precomputed_rule_evaluation=rev,
        )
        assert "anomaly_id" not in out, f"agregasi valid dianggap anomaly: {ket}"
        assert out["status"] == want, f"pipeline {ket}: {out['status']} != {want}"


# ------------------------------------------------------------ runner

def t_isolasi_per_user() -> None:
    """REVIEW 71b3c63 (conditionally green 27 Sep) CONDITION #1: cross-user
    isolation is LOCKED by test — A writes, B does not see; ledger AND
    anomaly channel. Without this test isolation could break silently during a
    refactor (the only reason the split commit exists)."""
    rid = "revenue.isolasi_a"
    vm_a = {**VM_OK[0], "requirement_id": rid}
    ledger.adjudicate_and_persist(
        "userA", rid, RULE_PARTIAL,
        [_ev("ev.1", "sudah berlangganan")], [vm_a], evaluation_time=100,
    )
    assert ledger.latest_status("userA", rid) == "PRESENT"
    # B: UNKNOWN by absence — A's status does NOT leak
    assert ledger.latest_status("userB", rid) is None, "status A bocor ke B"
    # anomaly channel: A writes an anomaly -> only A sees it
    rid_anom = "revenue.isolasi_anom"
    row = ledger.adjudicate_and_persist(
        "userA", rid_anom, RULE_PARTIAL,
        [_ev("ev.1", "sudah berlangganan")], VM_OK, evaluation_time=100,
        precomputed_rule_evaluation={"sufficient": True, "partial": True,
                                     "no_decisive": False, "contradicting": False},
    )
    assert "anomaly_id" in row, "S∧P harus anomaly, bukan entry"
    assert ledger.read_anomalies("userA", rid_anom), "A tak melihat anomalynya"
    assert ledger.read_anomalies("userB", rid_anom) == [], "anomaly A bocor ke B"
    assert ledger.latest_status("userB", rid_anom) is None


def t_d9_tanpa_transkrip_mentah() -> None:
    """D9 (int 08 §8.4): adjudication only reads the Admitted Evidence Set —
    the transcript_tail parameter NO LONGER EXISTS in adjudicate or
    adjudicate_and_persist (TypeError, mechanically closed door)."""
    import inspect

    from core.stages.adjudicate import adjudicate
    for fn in (adjudicate, ledger.adjudicate_and_persist):
        assert "transcript_tail" not in inspect.signature(fn).parameters, fn
    try:
        ledger.adjudicate_and_persist(USER, "x.y", {"mode": "BINARY"}, [], [], 1,
                                      transcript_tail="bocor")
    except TypeError:
        return
    raise AssertionError("transcript_tail masih diterima")


def main() -> int:
    for name, fn in sorted(globals().items()):
        if name.startswith("t_") and callable(fn):
            _check(name, fn)
    ok = True
    for name, passed, err in RESULTS:
        print(f"  {'PASS' if passed else 'FAIL'}  {name}" + (f"  — {err}" if err else ""))
        ok = ok and passed
    print(f"\n{sum(p for _, p, _ in RESULTS)}/{len(RESULTS)} invariant tests passed")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
