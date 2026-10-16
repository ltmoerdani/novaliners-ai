"""D4 (int 08 §8.4) — production RouteTemplate library.

Locks:
1. every contract motion has >=1 `active` template (strategy registry D5);
   the `proof_only` specimen (landing_first_v1) does NOT enter the library;
2. hazard §7.10 per template: every vacuous-capable requirement used
   has a population provider — `depends_on` to a provider node in the same
   route, OR (when it cannot be provided in the route) an `applies_when` that
   requires the population context. The AUDIT table below = the written decision;
   the validator does not read prose (INV-R16), so the check lives here;
3. every template is really composed through the bridge with a REAL Session:
   APPLIES -> lineage + frontier pass the validator with 0 errors; without
   evidence -> UNDETERMINED + RESOLVE_APPLICABILITY; negation -> not
   evidence; positive not_applicable evidence -> not born.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))  # mvp/

import store.adjudication_ledger as ledger  # noqa: E402

_tmp = Path(tempfile.mkdtemp())
ledger._LEDGER_ROOT = _tmp / "ledger"  # non-destruktif

from core.schema.evidence import EvidenceItem  # noqa: E402
from ontology.route import validate_route as vr  # noqa: E402
from ontology.route.session_bridge import run_session_route  # noqa: E402
from ontology.route.strategies import (  # noqa: E402
    active_template_library,
    load_motion_vocabulary,
    load_strategies,
)
from store.memory import Session  # noqa: E402

MOTIONS = set(load_motion_vocabulary())
LIB = {t["template_id"]: t for t in active_template_library()}

# §7.10 AUDIT — vacuous-capable requirement -> population provider.
# ("depends_on", provider key)  : population is provided by another node in this route
# ("applies_when", None)        : cannot be provided in the route -> context
#                                 populasi dituntut applicability template
VACUUM_AUDIT = {
    "direct_outreach_v1": {
        "conversion.commitment_obtained": ("depends_on", "prospects"),
        "access.decision_maker": ("depends_on", "prospects"),
    },
    "value_repricing_v1": {
        "commercial.value_linked_to_explicit_need": ("applies_when", None),
    },
    "client_expansion_v1": {
        "retention.repeat_purchase": ("applies_when", None),
    },
    "referral_partnership_v1": {
        "gtm.reference_customer_secured": ("applies_when", None),
    },
    "paid_channel_test_v1": {
        "experiment.baseline_comparison": ("depends_on", "landing"),
    },
}
# evidence that triggers each template's applies (strategy context, not status)
APPLIES_TEXT = {
    "direct_outreach_v1": "Saya konsultan, jual jasa ke klien bisnis.",
    "value_repricing_v1": "Klien bilang harga kami kemurahan untuk hasilnya.",
    "client_expansion_v1": "Ada 8 klien aktif yang puas dengan hasilnya.",
    "referral_partnership_v1": "Beberapa pelanggan datang dari rekomendasi komunitas.",
    "paid_channel_test_v1": "Kami siap alokasikan budget iklan bulan depan.",
}


def _vacuum_capable() -> set[str]:
    reg = json.loads(vr.REGISTRY_PATH.read_text(encoding="utf-8"))
    return {r["requirement_id"] for r in reg["requirements"]
            if "vakum" in r["satisfaction_rule"]["no_decisive"].lower()}


def _session(uid: str, texts: list[str]) -> Session:
    s = Session.__new__(Session)
    s.user_id = uid
    s.evidence = [EvidenceItem(id=f"e{i}", signal=t, source_quote=t,
                               level="self_reported", topic="REVENUE_STATE")
                  for i, t in enumerate(texts)]
    return s


def _validate(result: dict) -> list[str]:
    vr.errors.clear()
    vr.warnings.clear()
    vr.check_lineage(result["lineage"], "L", vr.load_registry())
    vr.check_frontier(result["frontier"], [result["lineage"]], "F")
    return list(vr.errors)


def t_setiap_motion_punya_template_aktif() -> None:
    strategies = load_strategies()
    covered = {strategies[t["strategy_id"]]["motion"] for t in LIB.values()}
    assert covered == MOTIONS, f"motion tanpa template aktif: {MOTIONS - covered}"
    assert "landing_first_v1" not in LIB, "spesimen proof_only masuk pustaka"
    assert set(LIB) == set(VACUUM_AUDIT), \
        f"template tanpa audit §7.10: {set(LIB) ^ set(VACUUM_AUDIT)}"


def t_audit_hazard_7_10() -> None:
    vac = _vacuum_capable()
    for tid, tpl in LIB.items():
        by_key = {n["candidate_key"]: n for n in tpl["node_candidates"]}
        used_vac = {n["resolves"][0] for n in tpl["node_candidates"]} & vac
        audit = VACUUM_AUDIT[tid]
        assert used_vac == set(audit), \
            f"{tid}: vakum dipakai {sorted(used_vac)} != diaudit {sorted(audit)}"
        for rid, (how, provider) in audit.items():
            node = next(n for n in tpl["node_candidates"]
                        if n["resolves"][0] == rid)
            if how == "depends_on":
                assert provider in node["depends_on"], \
                    f"{tid}.{rid}: tak bergantung pada penyedia {provider!r}"
                assert provider in by_key
            else:
                assert tpl["applies_when"]["applies"], \
                    f"{tid}.{rid}: populasi via applies_when tapi applies kosong"


def t_setiap_template_terkomposisi_valid() -> None:
    strategies = load_strategies()
    for tid, tpl in LIB.items():
        r = run_session_route(_session(f"u-{tid[:12]}", [APPLIES_TEXT[tid]]),
                              tpl, base_dir=_tmp)
        assert r["outcome"] == "ROUTE_CREATED", (tid, r["outcome"], r.get("reason"))
        lin = r["lineage"]
        assert lin["applicability"]["status"] == "APPLIES", (tid, lin["applicability"])
        assert lin["motion"] == strategies[tpl["strategy_id"]]["motion"]
        assert lin["reconciliation_key"]["goal_anchor"] == tpl["goal_anchor"]
        assert any(f["kind"] == "EXECUTE" for f in r["frontier"]), (tid, r["frontier"])
        errs = _validate(r)
        assert not errs, (tid, errs)


def t_setiap_aktivitas_node_punya_versi_en() -> None:
    """EN UI language policy (docs/03 §7): node activities appear in Today/Readiness/ACTION turns.
    Without i18n.en, ID machine sentences leak into the EN session UI (incident 18 Oct 2026)."""
    for tid, tpl in LIB.items():
        for n in tpl["node_candidates"]:
            en = ((n.get("i18n") or {}).get("en") or {}).get("activity")
            assert isinstance(en, str) and en.strip(), \
                f"{tid}.{n['candidate_key']}: node_candidates tanpa i18n.en.activity"


def t_tanpa_bukti_undetermined() -> None:
    for tid, tpl in LIB.items():
        r = run_session_route(_session(f"n-{tid[:12]}", ["Halo, saya mau mulai."]),
                              tpl, base_dir=_tmp)
        assert r["lineage"]["applicability"]["status"] == "UNDETERMINED", tid
        assert [f["kind"] for f in r["frontier"]] == ["RESOLVE_APPLICABILITY"], tid
        assert not _validate(r), tid


def t_negasi_dan_not_applicable_paid() -> None:
    tpl = LIB["paid_channel_test_v1"]
    r = run_session_route(_session("neg-paid", ["Saya tidak pakai iklan."]),
                          tpl, base_dir=_tmp)
    assert r["lineage"]["applicability"]["status"] == "UNDETERMINED", \
        "negasi dihitung sebagai bukti applicability (B1)"
    r2 = run_session_route(_session("na-paid", ["Kami tidak punya budget iklan."]),
                           tpl, base_dir=_tmp)
    assert r2["outcome"] == "NO_ROUTE_NOT_APPLICABLE", r2["outcome"]


def t_template_yatim_gagal_keras() -> None:
    """Audit of this iteration: template files whose strategy_id is NOT registered in strategies.json
    = orphan artifacts → ValueError (not silently skipped — such invisible templates are precisely
    invalid composition candidates). Skipping `proof_only` remains deliberate and valid."""
    import shutil
    import tempfile

    from ontology.route.strategies import TEMPLATE_DIR

    with tempfile.TemporaryDirectory() as td:
        for f in TEMPLATE_DIR.glob("*.json"):
            shutil.copy2(f, Path(td) / f.name)
        orphan = json.loads((Path(td) / "direct_outreach_v1.json").read_text(encoding="utf-8"))
        orphan["template_id"] = "orphan_v1"
        orphan["strategy_id"] = "strategi_tidak_terdaftar"
        (Path(td) / "orphan_v1.json").write_text(json.dumps(orphan), encoding="utf-8")
        try:
            active_template_library(template_dir=Path(td))
            raised = None
        except ValueError as exc:
            raised = exc
        assert raised is not None and "orphan_v1.json" in str(raised) \
            and "strategi_tidak_terdaftar" in str(raised), str(raised)


TESTS = [t_setiap_motion_punya_template_aktif, t_audit_hazard_7_10,
         t_setiap_aktivitas_node_punya_versi_en,
         t_setiap_template_terkomposisi_valid, t_tanpa_bukti_undetermined,
         t_negasi_dan_not_applicable_paid, t_template_yatim_gagal_keras]


def main() -> int:
    fails = 0
    for fn in TESTS:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
        except AssertionError as exc:
            fails += 1
            print(f"  FAIL  {fn.__name__}: {exc}")
    print(f"\n{len(TESTS) - fails}/{len(TESTS)} template tests passed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
