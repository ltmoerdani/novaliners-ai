"""TEST-LOCK M4 Route Lifecycle (owner verdict 27 Sep: M4 before
bridge installation; DEBT-M4 T1.17 paid off).

LOCKED:
 1. Goal PRESENT → lineage CLOSED close_reason=goal_achieved; derived
    COMPLETED; empty frontier; NEW row (last-row-wins).
 2. Applicability fails by positive evidence → CLOSED close_reason=
    not_applicable; derived CLOSED.
 3. APPLIES → UNDETERMINED is NOT terminal: lineage stays OPEN, frontier
    RESOLVE_APPLICABILITY, applicability_before/after recorded.
 4. Model B: a terminal lineage is NEVER reopened — the next reconcile returns
    None, WITHOUT a new row; find_closed_by_key still finds it
    (reopened_from remains possible for a new episode).
 5. lineage_status enum does NOT change (OPEN|CLOSED) — COMPLETED is derived.

Run: cd mvp && python ontology/route/test_lifecycle.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))  # mvp/

import tempfile as _tempfile  # noqa: E402

import store.adjudication_ledger as ledger  # noqa: E402
from core.schema.evidence import EvidenceItem  # noqa: E402
from ontology.route.compose import compose_route  # noqa: E402
from ontology.route.lifecycle import (  # noqa: E402
    CLOSE_GOAL_ACHIEVED,
    CLOSE_NOT_APPLICABLE,
    derived_route_status,
    reconcile,
)
from store import route_lineages as rl  # noqa: E402

ledger._LEDGER_ROOT = Path(_tempfile.mkdtemp(prefix="m4_adj_"))
_tmp = Path(_tempfile.mkdtemp(prefix="m4_lin_"))

GOAL = "conversion.landing_page"

TEMPLATE = {
    "template_id": "m4-min", "strategy_id": "template_led",
    "applies_when": {
        "applies": [{"text_contains_any": ["website"]}],
        "not_applicable": [{"text_contains_any": ["offline saja"]}]},
    "requires": ["conversion.copy_composition",
                 "conversion.landing_page"],
    "node_candidates": [
        {"candidate_key": "copy_main",
         "resolves": ["conversion.copy_composition"],
         "strength": "hard", "depends_on": [], "activity": "Tulis copy"},
        {"candidate_key": "landing", "resolves": ["conversion.landing_page"],
         "strength": "hard", "depends_on": ["copy_main"],
         "activity": "Bangun halaman"},
    ],
    "provenance": [{"source_id": "vp", "chapters": ["ch05"],
                    "knowledge_type": "source_claim",
                    "confidence": "normative_only"}],
}

RULE_PARTIAL = {
    "mode": "PARTIAL",
    "sufficient": {"any_of": [{"text_contains_any": ["sudah ada landing"]}]},
    "partial": {"any_of": [{"text_contains_any": ["__never__"]}]},
    "no_decisive": {"any_of": [{"text_contains_any": ["__never__"]}]},
    "contradicting": {"any_of": [{"text_contains_any": ["__never__"]}]},
}


def _ev(text: str, eid: str = "e1", gap: bool = False) -> EvidenceItem:
    return EvidenceItem(id=eid, signal=text, source_quote=text,
                        level="self_reported", topic="REVENUE_STATE",
                        is_gap=gap)


def _mark_present(user_id: str, rid: str) -> None:
    row = ledger.adjudicate_and_persist(
        user_id, rid, RULE_PARTIAL,
        [_ev("sudah ada landing", f"ev-{rid}")],
        [{"requirement_id": rid, "evidence_refs": [f"ev-{rid}"],
          "verification_method": "deterministic_predicate",
          "verified": True, "verified_at": 1}],
        evaluation_time=100,
    )
    assert "entry_id" in row, row


def _reader(user_id: str):
    return lambda rid: ledger.latest_status(user_id, rid)


def _birth(user_id: str, scope: list[str],
           evidence: list[EvidenceItem]) -> dict:
    """Birth through the composer — reconcile does NOT give birth to a route (not
    its job; birth = compose_route, contract T1)."""
    return compose_route(TEMPLATE, goal_anchor=GOAL, scope_anchor=scope,
                         evidence=evidence,
                         requirement_status_reader=_reader(user_id),
                         motion="ACQUISITION", user_id=user_id, base_dir=_tmp)


def _reconcile(user_id: str, scope: list[str], evidence: list[EvidenceItem]):
    return reconcile(user_id, TEMPLATE, goal_anchor=GOAL, scope_anchor=scope,
                     evidence=evidence,
                     requirement_status_reader=_reader(user_id), base_dir=_tmp)


RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, fn) -> None:
    try:
        fn()
        RESULTS.append((name, True, ""))
    except Exception as exc:  # noqa: BLE001
        RESULTS.append((name, False, f"{type(exc).__name__}: {exc}"))


def t_goal_present_completed() -> None:
    """INV 1+4+5: goal PRESENT → CLOSED goal_achieved, derived COMPLETED,
    new row, empty frontier; a terminal is not opened again."""
    scope = ["state:claim-m4a"]
    ev = [_ev("jual online via website kami")]
    r = _birth("userA", scope, ev)
    assert r["outcome"] == "ROUTE_CREATED"
    n_rows = len(rl.list_rows("userA", _tmp))
    _mark_present("userA", GOAL)
    r2 = _reconcile("userA", scope, ev)
    assert r2["outcome"] == "LINEAGE_COMPLETED", r2
    lin = r2["lineage"]
    assert lin["lineage_status"] == "CLOSED" \
        and lin["close_reason"] == CLOSE_GOAL_ACHIEVED
    assert derived_route_status(lin) == "COMPLETED"  # enum does not change
    assert r2["frontier"] == []
    assert len(rl.list_rows("userA", _tmp)) == n_rows + 1, "bukan baris baru"
    # Model B: OPEN hilang, CLOSED ditemukan (bahan reopened_from)
    key = {"goal_anchor": GOAL, "strategy_id": TEMPLATE["strategy_id"],
           "scope_anchor": scope}
    assert rl.find_open_by_key("userA", key, _tmp) is None
    assert rl.find_closed_by_key("userA", key, _tmp) is not None
    # reconcile again → None, WITHOUT a new row (terminal stays terminal)
    assert _reconcile("userA", scope, ev) is None
    assert len(rl.list_rows("userA", _tmp)) == n_rows + 1


def t_not_applicable_closed() -> None:
    """INV 2: positive not-applicable evidence → CLOSED not_applicable."""
    scope = ["state:claim-m4b"]
    _birth("userB", scope, [_ev("jual online via website kami")])
    r = _reconcile("userB", scope, [_ev("operasi kami offline saja")])
    assert r["outcome"] == "LINEAGE_CLOSED", r
    lin = r["lineage"]
    assert lin["lineage_status"] == "CLOSED" \
        and lin["close_reason"] == CLOSE_NOT_APPLICABLE
    assert derived_route_status(lin) == "CLOSED"
    assert lin["close_basis"]["evidence"], "transisi tanpa alasan/bukti"
    assert r["frontier"] == []
    # CORRECTIVE review 7de3e73: the record MUST be consistent — applicability
    # in the same record also becomes NOT_APPLICABLE + positive evidence (INV-R2),
    # rather than leaving the old APPLIES beside the close_reason.
    assert lin["applicability"]["status"] == "NOT_APPLICABLE", lin["applicability"]
    assert lin["applicability"]["evidence"], "NOT_APPLICABLE tanpa bukti positif"
    # validator rules close both directions (hole-5 + its converse)
    from ontology.route import validate_route as vr
    vr.errors.clear()
    vr.check_lineage(lin, "t", None)
    assert not vr.errors, vr.errors
    bad = {**lin, "applicability": {"status": "APPLIES", "evidence": ["e1"]}}
    vr.errors.clear()
    vr.check_lineage(bad, "t", None)
    assert any("close_reason=not_applicable" in e for e in vr.errors), vr.errors


def t_negasi_non_gap_parity_mirror_compose() -> None:
    """B1 (D3 int 08 §8.4): negation on NON-gap evidence is no longer
    applicability evidence. 'saya tidak pakai website' -> UNDETERMINED (neither
    APPLIES nor NOT_APPLICABLE: negation != positive evidence INV-R2) in the
    mirror AND compose — parallelism stays locked; the route stays OPEN."""
    scope = ["state:claim-m4d"]
    _birth("userD2", scope, [_ev("jual online via website kami")])
    r = _reconcile("userD2", scope, [_ev("saya tidak pakai website")])
    assert r["outcome"] == "ROUTE_REUSED"
    app_after = r["lineage"]["applicability"]["status"]
    assert app_after == "UNDETERMINED", app_after  # utang 4f3e9ac LUNAS
    assert r["transition"]["applicability_after"] == app_after, \
        "mirror dan compose tidak sejajar"
    assert r["lineage"]["lineage_status"] == "OPEN"
    assert r["frontier"][0]["kind"] == "RESOLVE_APPLICABILITY"


def t_applies_ke_undetermined_nonterminal() -> None:
    """INV 3: APPLIES → UNDETERMINED is not terminal — OPEN stays,
    frontier RESOLVE_APPLICABILITY, before/after recorded, new row."""
    scope = ["state:claim-m4c"]
    r1 = _birth("userC", scope, [_ev("jual online via website kami")])
    assert r1["lineage"]["applicability"]["status"] == "APPLIES"
    before = len(rl.list_rows("userC", _tmp))
    r2 = _reconcile("userC", scope, [_ev("katalog cetak dikirim ke pelanggan")])
    assert r2["outcome"] == "ROUTE_REUSED", r2
    tr = r2["transition"]
    assert tr["kind"] == "APPLICABILITY_RESOLVED" \
        and tr["applicability_before"] == "APPLIES" \
        and tr["applicability_after"] == "UNDETERMINED" \
        and tr["terminal"] is False
    assert r2["lineage"]["lineage_status"] == "OPEN", "tidak terminal kok CLOSED"
    assert r2["lineage"]["applicability"]["status"] == "UNDETERMINED"
    assert r2["frontier"] and r2["frontier"][0]["kind"] == "RESOLVE_APPLICABILITY"
    assert len(rl.list_rows("userC", _tmp)) == before + 1
    # gap does not matter: gap-only → stays UNDETERMINED, not CLOSED
    r3 = _reconcile("userC", scope, [_ev("belum punya website", "g9", gap=True)])
    assert r3["lineage"]["applicability"]["status"] == "UNDETERMINED"
    assert r3["lineage"]["lineage_status"] == "OPEN"


def t_derived_status_unit() -> None:
    """INV 5: derived_route_status — OPEN None; CLOSED→CLOSED;
    goal_achieved→COMPLETED; the lineage_status enum is untouched."""
    assert derived_route_status({"lineage_status": "OPEN"}) is None
    assert derived_route_status({"lineage_status": "CLOSED"}) == "CLOSED"
    assert derived_route_status({"lineage_status": "CLOSED",
                                 "close_reason": "not_applicable"}) == "CLOSED"
    assert derived_route_status({"lineage_status": "CLOSED",
                                 "close_reason": "goal_achieved"}) == "COMPLETED"


TESTS = [t_goal_present_completed, t_not_applicable_closed,
         t_negasi_non_gap_parity_mirror_compose,
         t_applies_ke_undetermined_nonterminal, t_derived_status_unit]


def main() -> int:
    for fn in TESTS:
        check(fn.__name__, fn)
    ok = True
    for name, passed, err in RESULTS:
        print(f"  {'PASS' if passed else 'FAIL'}  {name}" + (f"  — {err}" if err else ""))
        ok = ok and passed
    print(f"\n{sum(p for _, p, _ in RESULTS)}/{len(RESULTS)} lifecycle tests passed")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
