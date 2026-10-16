"""TEST-LOCK T1 Composition (spec v0 owner — 13 invariant + template/
motion boundary). Run: python ontology/route/test_compose.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))  # mvp/

from core.schema.evidence import EvidenceItem  # noqa: E402
from ontology.route.compose import compose_route  # noqa: E402
from store import route_lineages as rl  # noqa: E402

TEMPLATE = {  # minimal dict for tests (the real template file is tested in T1.12)
    "template_id": "t1-min", "strategy_id": "template_led",
    "applies_when": {
        "applies": [{"text_contains_any": ["website"]}],
        "not_applicable": [{"text_contains_any": ["offline saja"]}]},
    "requires": ["conversion.copy_composition",
                 "conversion.landing_page",
                 "experiment.baseline_comparison"],
    "node_candidates": [
        {"candidate_key": "copy_main", "resolves": ["conversion.copy_composition"],
         "strength": "hard", "depends_on": [], "activity": "Tulis copy"},
        {"candidate_key": "landing", "resolves": ["conversion.landing_page"],
         "strength": "hard", "depends_on": ["copy_main"],
         "activity": "Bangun halaman"},
        {"candidate_key": "baseline", "resolves": ["experiment.baseline_comparison"],
         "strength": "hard", "depends_on": ["landing"],
         "activity": "Jalankan uji"},
    ],
    "provenance": [{"source_id": "vp", "chapters": ["ch05"],
                    "knowledge_type": "source_claim",
                    "confidence": "normative_only"}],
}
GOAL = "conversion.landing_page"
SCOPE = ["state:claim_t1"]
E_APPLIES = [EvidenceItem(id="e1", signal="jual online via website kami",
                          source_quote="jual online via website kami",
                          level="self_reported", topic="REVENUE_STATE")]
E_NO = [EvidenceItem(id="e2", signal="target pasar kami butuh brosur fisik",
                     source_quote="target pasar kami butuh brosur fisik",
                     level="self_reported", topic="REVENUE_STATE")]
E_NA = [EvidenceItem(id="e3", signal="operasi kami offline saja",
                     source_quote="operasi kami offline saja",
                     level="self_reported", topic="REVENUE_STATE")]


def reader(status_map: dict):
    return lambda rid: status_map.get(rid)


RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, fn) -> None:
    try:
        fn()
        RESULTS.append((name, True, ""))
    except Exception as exc:  # noqa: BLE001
        RESULTS.append((name, False, f"{type(exc).__name__}: {exc}"))


def _compose(tmp, status=None, evidence=None, goal=GOAL, motion="ACQUISITION",
             template=None):
    return compose_route(template or TEMPLATE, goal_anchor=goal,
                         scope_anchor=SCOPE,
                         evidence=evidence if evidence is not None else E_APPLIES,
                         requirement_status_reader=reader(status or {}),
                         motion=motion, user_id="u1", base_dir=tmp)


def t1_1_goal_present_no_route(tmp=""):
    with tempfile.TemporaryDirectory() as d:
        r = _compose(d, status={GOAL: "PRESENT"})
        assert r["outcome"] == "NO_ROUTE_GOAL_PRESENT", r
        assert r.get("lineage") is None, r


def t1_2_undetermined_route(tmp=""):
    with tempfile.TemporaryDirectory() as d:
        r = _compose(d, evidence=E_NO)
        assert r["outcome"] == "ROUTE_CREATED", r
        lin, fr = r["lineage"], r["frontier"]
        assert lin["applicability"]["status"] == "UNDETERMINED", lin
        assert len(fr) == 1 and fr[0]["kind"] == "RESOLVE_APPLICABILITY", fr
        assert "node" not in fr[0], fr  # route-level, without a node
        assert lin["revisions"][0]["nodes"], "identity node tetap ada"


def t1_3_not_applicable_no_route(tmp=""):
    with tempfile.TemporaryDirectory() as d:
        r = _compose(d, evidence=E_NA)
        assert r["outcome"] == "NO_ROUTE_NOT_APPLICABLE", r
        assert r.get("lineage") is None, r  # birth does not create CLOSED


def t1_4_5_evidence_only_no_transcript(tmp=""):
    import inspect
    sig = inspect.signature(compose_route)
    assert "transcript" not in sig.parameters, "transcript tak boleh ada di API"
    with tempfile.TemporaryDirectory() as d:
        # needle 'website' ONLY in the evidence — without an evidence match =>
        # UNDETERMINED (the evaluator's proof eats evidence, not another source)
        r = _compose(d, evidence=E_NO)
        assert r["lineage"]["applicability"]["status"] == "UNDETERMINED", r


def t1_6_7_frontier_rules(tmp=""):
    with tempfile.TemporaryDirectory() as d:
        st = {"conversion.copy_composition": "PRESENT"}
        r = _compose(d, status=st, evidence=E_APPLIES)
        lin, fr = r["lineage"], r["frontier"]
        assert lin["applicability"]["status"] == "APPLIES", lin
        nodes = lin["revisions"][0]["nodes"]
        by = {n["node_id"]: n for n in nodes}
        copy_n = next(n for n in nodes
                      if n["resolves"] == ["conversion.copy_composition"])
        land_n = next(n for n in nodes
                      if n["resolves"] == ["conversion.landing_page"])
        base_n = next(n for n in nodes
                      if n["resolves"] == ["experiment.baseline_comparison"])
        # T1.6: APPLIES + dep satisfied -> EXECUTE for landing (copy
        # PRESENT leaves the frontier)
        kinds = {(e.get("node"), e["kind"]) for e in fr}
        assert (land_n["node_id"], "EXECUTE") in kinds, fr
        assert (copy_n["node_id"], "EXECUTE") not in kinds, "PRESENT must leave"
        # T1.7: baseline dep = landing UNKNOWN -> exec UNKNOWN -> does not enter
        assert base_n["executability"] == "UNKNOWN", base_n
        assert (base_n["node_id"], "EXECUTE") not in kinds, fr
        del by


def t1_8_satisfaction_from_reader(tmp=""):
    with tempfile.TemporaryDirectory() as d:
        st = {"conversion.copy_composition": "PRESENT",
              "conversion.landing_page": "PARTIAL"}
        r = _compose(d, status=st, evidence=E_APPLIES)
        nodes = r["lineage"]["revisions"][0]["nodes"]
        sat = {n["resolves"][0]: n["satisfaction"]["status"] for n in nodes}
        assert sat["conversion.copy_composition"] == "PRESENT"
        assert sat["conversion.landing_page"] == "PARTIAL"
        assert sat["experiment.baseline_comparison"] == "UNKNOWN"  # absence


def t1_9_reuse_open_route_id(tmp=""):
    with tempfile.TemporaryDirectory() as d:
        r1 = _compose(d, evidence=E_NO)
        r2 = _compose(d, evidence=E_APPLIES)  # same key
        assert r2["outcome"] == "ROUTE_REUSED", r2
        assert r2["lineage"]["route_id"] == r1["lineage"]["route_id"], \
            "route identity preserved (INV-R13)"


def t1_10_closed_reopened_from(tmp=""):
    with tempfile.TemporaryDirectory() as d:
        r1 = _compose(d, evidence=E_NO)
        old_id = r1["lineage"]["route_id"]
        rows = rl.list_rows("u1", d)
        rows[0]["lineage"]["lineage_status"] = "CLOSED"
        Path(d, "u1", "route_lineages.jsonl").write_text(
            "\n".join(json.dumps(x) for x in rows) + "\n", encoding="utf-8")
        r2 = _compose(d, evidence=E_NO)
        assert r2["outcome"] == "ROUTE_CREATED", r2
        assert r2["lineage"]["reopened_from"] == old_id, r2


def t1_11_goal_anchor_in_resolves(tmp=""):
    with tempfile.TemporaryDirectory() as d:
        try:
            _compose(d, goal="offering.exists")
            raise AssertionError("goal_anchor di luar resolves lolos")
        except ValueError as exc:
            assert "INV-R4" in str(exc), exc


def t1_12_persist_reload_validate(tmp=""):
    with tempfile.TemporaryDirectory() as d:
        _compose(d, status={"conversion.copy_composition": "PRESENT"},
                 evidence=E_APPLIES)
        rows = rl.list_rows("u1", d)
        rid = rows[0]["lineage"]["route_id"]
        doc = rl.build_instance_document(rows)
        f = Path(__file__).parent / "instances" / "_t1_compose_tmp.json"
        try:
            f.write_text(json.dumps(doc, ensure_ascii=False, indent=2),
                         encoding="utf-8")
            p = subprocess.run(
                [sys.executable, str(Path(__file__).parent / "validate_route.py")],
                capture_output=True, text=True)
            assert p.returncode == 0, p.stdout[-800:] + p.stderr[-400:]
        finally:
            if f.exists():
                f.unlink()
        reload_rid = rl.build_instance_document(
            rl.list_rows("u1", d))["lineages"][0]["route_id"]
        assert reload_rid == rid, "identity tetap setelah persist->reload"


def t1_13_motion_from_context_not_template(tmp=""):
    assert "motion" not in TEMPLATE, "template tak boleh membawa motion"
    with tempfile.TemporaryDirectory() as d:
        r = _compose(d, motion="EXPANSION")
        assert r["lineage"]["motion"] == "EXPANSION", r
    with tempfile.TemporaryDirectory() as d:
        try:
            _compose(d, motion="MAKANAN")
            raise AssertionError("motion di luar enum lolos")
        except ValueError:
            pass


def t1_14_real_template_composes(tmp=""):
    """Template file landing_first_v1 ASLI lolos compose + validator."""
    tpl = json.loads(
        (Path(__file__).parent / "templates" / "landing_first_v1.json")
        .read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as d:
        r = compose_route(tpl, goal_anchor="conversion.landing_page",
                          scope_anchor=SCOPE, evidence=E_APPLIES,
                          requirement_status_reader=reader({}),
                          motion="ACQUISITION", user_id="u2", base_dir=d)
        assert r["outcome"] == "ROUTE_CREATED", r
        rows = rl.list_rows("u2", d)
        doc = rl.build_instance_document(rows)
        f = Path(__file__).parent / "instances" / "_t1_tpl_tmp.json"
        try:
            f.write_text(json.dumps(doc, ensure_ascii=False, indent=2),
                         encoding="utf-8")
            p = subprocess.run(
                [sys.executable, str(Path(__file__).parent / "validate_route.py")],
                capture_output=True, text=True)
            assert p.returncode == 0, p.stdout[-800:] + p.stderr[-400:]
        finally:
            if f.exists():
                f.unlink()




def t1_15_reuse_reprojects_frontier(tmp=""):
    """RED->PATCH review 6585c32: UNDETERMINED -> APPLIES on the SAME
    route_id; the frontier is recomputed (not a stale snapshot)."""
    with tempfile.TemporaryDirectory() as d:
        r1 = _compose(d, evidence=E_NO)
        assert r1["frontier"][0]["kind"] == "RESOLVE_APPLICABILITY", r1
        rid = r1["lineage"]["route_id"]
        st = {"conversion.copy_composition": "PRESENT"}
        r2 = _compose(d, status=st, evidence=E_APPLIES)
        assert r2["outcome"] == "ROUTE_REUSED", r2
        assert r2["lineage"]["route_id"] == rid, "identity must match"
        assert r2["lineage"]["applicability"]["status"] == "APPLIES", r2
        assert r2["lineage"]["applicability"]["evidence"], \
            "APPLIES -> evidence = CITATION (not the whole input)"
        fr = r2["frontier"]
        assert fr and fr[0]["kind"] == "EXECUTE", f"frontier basi! {fr}"
        # current projection: copy PRESENT enters node satisfaction
        nodes = r2["lineage"]["revisions"][-1]["nodes"]
        copy_n = next(n for n in nodes
                      if n["resolves"] == ["conversion.copy_composition"])
        assert copy_n["satisfaction"]["status"] == "PRESENT", copy_n


def t1_16_material_graph_new_revision(tmp=""):
    """RED->PATCH: material graph change (different template, same key) ->
    SAME route_id + revision_no increases + matching node identity inherited +
    frontier from the new revision."""
    tpl2 = json.loads(json.dumps(TEMPLATE))
    tpl2["template_id"] = "t1-min-v2"  # template_id is NOT identity
    proof = {"candidate_key": "proof", "resolves": ["conversion.proof"],
             "strength": "soft", "depends_on": ["landing"],
             "activity": "Kumpulkan bukti"}
    tpl2["node_candidates"].insert(3, proof)
    with tempfile.TemporaryDirectory() as d:
        r1 = _compose(d, evidence=E_NO)
        rid, old_node = r1["lineage"]["route_id"], \
            r1["lineage"]["revisions"][0]["nodes"][0]["node_id"]
        r2 = _compose(d, evidence=E_NO, template=tpl2)
        assert r2["outcome"] == "ROUTE_REUSED", r2
        lin = r2["lineage"]
        assert lin["route_id"] == rid, "identity stays"
        # FULL HISTORY (review 568beb9): rev 1 REMAINS in
        # revisions[] — material change ADDS, does not replace
        assert [r["revision_no"] for r in lin["revisions"]] == [1, 2], \
            lin["revisions"]
        rev = lin["revisions"][-1]
        assert rev["revision_no"] == 2, rev
        assert len(rev["nodes"]) == 4, rev  # proof enters the new revision
        # old node identity INHERITED (match)
        new_first = next(n for n in rev["nodes"]
                         if n["resolves"] == ["conversion.copy_composition"])
        assert new_first["node_id"] == old_node, "identity lost"
        # dedup persist: reload = 1 lineage per route_id, rev 2
        rows = rl.list_rows("u1", d)
        doc = rl.build_instance_document(rows)
        assert len(doc["lineages"]) == 1 and \
            doc["lineages"][0]["revisions"][-1]["revision_no"] == 2, doc


def t1_17_goal_present_keeps_lineage_open(tmp=""):
    """DOCUMENTED DEBT-M4 (owner: do not fix in T1): the outcome
    refuses birth; an existing OPEN lineage is NOT closed by the composer."""
    with tempfile.TemporaryDirectory() as d:
        _compose(d, evidence=E_NO)
        r = _compose(d, status={GOAL: "PRESENT"}, evidence=E_NO)
        assert r["outcome"] == "NO_ROUTE_GOAL_PRESENT", r
        assert "DEBT-M4" in r["reason"], r  # explicit marker
        rows = rl.list_rows("u1", d)
        last = rows[-1]["lineage"]
        assert last["lineage_status"] == "OPEN", \
            "penutupan = lifecycle M4, BUKAN keputusan diam-diam T1"


def t1_18_user_id_kosong_ditolak(tmp=""):
    with tempfile.TemporaryDirectory() as d:
        try:
            compose_route(TEMPLATE, goal_anchor=GOAL, scope_anchor=SCOPE,
                          evidence=E_APPLIES,
                          requirement_status_reader=reader({}),
                          motion="ACQUISITION", user_id="", base_dir=d)
            raise AssertionError("user_id kosong lolos -> file bersama")
        except ValueError as exc:
            assert "lintas-user" in str(exc), exc


def t1_19_multi_resolves_ditolak(tmp=""):
    bad = json.loads(json.dumps(TEMPLATE))
    bad["node_candidates"][0]["resolves"] = ["conversion.proof",
                                             "conversion.landing_page"]
    with tempfile.TemporaryDirectory() as d:
        try:
            compose_route(bad, goal_anchor=GOAL, scope_anchor=SCOPE,
                          evidence=E_APPLIES,
                          requirement_status_reader=reader({}),
                          motion="ACQUISITION", user_id="u1", base_dir=d)
            raise AssertionError("multi-resolves lolos")
        except ValueError as exc:
            assert "T2+" in str(exc), exc


def t1_20_reader_enum_divalidasi(tmp=""):
    with tempfile.TemporaryDirectory() as d:
        try:
            _compose(d, status={GOAL: "LULUS"})
            raise AssertionError("nilai reader di luar enum lolos")
        except ValueError as exc:
            assert "enum satisfaction" in str(exc), exc




def t1_21_wording_change_bukan_material(tmp=""):
    """Review 568beb9: activity = contextual wording (render ≠
    revision — INV-R5 identity = (route_id, primary); position/order/
    wording = content). Change ONLY activity -> node_id STAYS,
    revision_no STAYS, the NEW activity is carried."""
    tpl2 = json.loads(json.dumps(TEMPLATE))
    for nc in tpl2["node_candidates"]:
        if nc["candidate_key"] == "landing":
            nc["activity"] = "Bangun halaman versi wording baru"
    with tempfile.TemporaryDirectory() as d:
        r1 = _compose(d, evidence=E_NO)
        rid = r1["lineage"]["route_id"]
        land_id = next(n["node_id"] for n in
                       r1["lineage"]["revisions"][0]["nodes"]
                       if n["resolves"] == ["conversion.landing_page"])
        r2 = _compose(d, evidence=E_NO, template=tpl2)
        assert r2["outcome"] == "ROUTE_REUSED", r2
        lin = r2["lineage"]
        assert lin["route_id"] == rid, "identity route"
        assert len(lin["revisions"]) == 1, \
            "wording BUKAN material — tak boleh menaikkan revision"
        assert lin["revisions"][0]["revision_no"] == 1, lin
        land2 = next(n for n in lin["revisions"][0]["nodes"]
                     if n["resolves"] == ["conversion.landing_page"])
        assert land2["node_id"] == land_id, \
            "node identity = (primary, exec_ctx) — wording bukan identitas"
        assert land2["activity"] == "Bangun halaman versi wording baru", \
            "activity baru terbawa (konten render diperbarui in-place)"


def main() -> int:
    tests = [
        ("T1.1 goal PRESENT -> tak lahir", t1_1_goal_present_no_route),
        ("T1.2 UNDETERMINED -> route + RESOLVE saja", t1_2_undetermined_route),
        ("T1.3 NOT_APPLICABLE -> tak ada active route", t1_3_not_applicable_no_route),
        ("T1.4/5 evidence-only, tanpa param transcript", t1_4_5_evidence_only_no_transcript),
        ("T1.6/7 frontier rules (EXECUTE / dep UNKNOWN menunggu)", t1_6_7_frontier_rules),
        ("T1.8 satisfaction = reader (None->UNKNOWN)", t1_8_satisfaction_from_reader),
        ("T1.9 key sama + OPEN -> route_id sama", t1_9_reuse_open_route_id),
        ("T1.10 CLOSED -> route baru + reopened_from", t1_10_closed_reopened_from),
        ("T1.11 goal_anchor wajib di resolves[] (INV-R4)", t1_11_goal_anchor_in_resolves),
        ("T1.12 persist->reload->validator 0 error + identity", t1_12_persist_reload_validate),
        ("T1.13 motion dari context, bukan template", t1_13_motion_from_context_not_template),
        ("T1.14 template asli landing_first_v1 lolos compose+validator", t1_14_real_template_composes),
        ("T1.15 reuse -> re-projection frontier (UNDET->APPLIES)", t1_15_reuse_reprojects_frontier),
        ("T1.16 material graph -> revision+1, identity diwarisi", t1_16_material_graph_new_revision),
        ("T1.17 goal PRESENT + OPEN lineage = DEBT-M4", t1_17_goal_present_keeps_lineage_open),
        ("T1.18 user_id kosong -> ValueError", t1_18_user_id_kosong_ditolak),
        ("T1.19 multi-resolves -> ValueError (T2+)", t1_19_multi_resolves_ditolak),
        ("T1.20 reader enum validated", t1_20_reader_enum_divalidasi),
        ("T1.21 wording activity BUKAN material change", t1_21_wording_change_bukan_material),
    ]
    for name, fn in tests:
        check(name, fn)
    for name, ok, why in RESULTS:
        print(f"  {'✅' if ok else '❌'} {name}" + (f" | {why}" if why else ""))
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"\nT1 COMPOSE: {passed}/{len(RESULTS)} PASS")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
