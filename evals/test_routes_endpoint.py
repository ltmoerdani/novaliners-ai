"""D7 (int 08 §8.4) — POST /session/{sid}/routes end-to-end over HTTP.

Lineage + ledger stores are redirected to a temporary directory (store/workspaces
is not gitignored); test session files are deleted at the end. No LLM.
"""
from __future__ import annotations

import io
import json
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # mvp/

from evals._store_isolation import isolate_store  # noqa: E402

isolate_store()  # eval: store redirected to tmp — production store untouched

import store.adjudication_ledger as ledger  # noqa: E402
import store.path_states as path_states  # noqa: E402
import store.route_lineages as rl  # noqa: E402

_tmp = Path(tempfile.mkdtemp(prefix="routes_ep_"))
rl._BASE = _tmp / "lineages"
ledger._LEDGER_ROOT = _tmp / "ledger"
path_states._STATES = _tmp / "path_states.json"     # user outcomes must never touch committed files
path_states._HISTORY = _tmp / "path_history.jsonl"

from fastapi.testclient import TestClient  # noqa: E402

import app.main as _app_main  # noqa: E402
import store.events as _event_store  # noqa: E402
from app.main import app  # noqa: E402
from providers.mock import MockProvider  # noqa: E402

# R4: this test USED TO call real Z.ai via POST /session (get_llm not patched): it burned quota
# on every gate-fast. The provider is forced to mock; conversation events go to a temporary directory.
_app_main.get_llm = lambda: MockProvider()
assert _app_main.get_llm().name == "mock", "uji ini hanya boleh berjalan dengan provider mock"
_event_store.EVENTS_DIR = Path(tempfile.mkdtemp(prefix="nvl-ev-"))
from core.schema.evidence import EvidenceItem  # noqa: E402
from evals.navigation_fixtures import diagnosis_with, revenue_artifact, strategy_ids  # noqa: E402
from ontology.route import validate_route as vr  # noqa: E402
from ontology.route.strategies import active_template_library, load_motion_vocabulary  # noqa: E402
from store.memory import store  # noqa: E402

c = TestClient(app)
USER = "u-routes-ep"
LIB = {t["strategy_id"]: t["template_id"] for t in active_template_library()}
# a state that makes ALL Revenue strategies give birth to a Possible Path
FULL_STATE = dict(current_monthly=30.0, target_monthly=60.0, gap_monthly=30.0, capacity_utilization=0.5,
                  willingness_to_pay="PROVEN_AT_CURRENT_PRICE", demand_exists=True, avg_deal_size=10.0)
_created: list[str] = []


def _session(user_id: str, texts: list[str], state: dict | None = FULL_STATE) -> str:
    body = {"goal_text": "naik ke 20 juta per bulan", "language": "id"}
    if user_id:
        body["user_id"] = user_id
    r = c.post("/session", json=body)
    assert r.status_code == 200, r.text[:200]
    sid = r.json()["session_id"]
    _created.append(sid)
    s = store.get(sid)
    s.evidence = [EvidenceItem(id=f"e{i}", signal=t, source_quote=t,
                               level="self_reported", topic="REVENUE_STATE")
                  for i, t in enumerate(texts)]
    if state is not None:   # routes are composed from Possible Paths that survive diagnosis
        s.diagnosis = revenue_artifact(**state)
    store.save(s)
    return sid


def _validator_errors(user_id: str, next_move: dict | None) -> list[str]:
    doc = rl.build_instance_document(rl.list_rows(user_id))
    if next_move is not None:
        doc["next_move"] = {k: v for k, v in next_move.items()
                            if k in ("output", "frontier_ref")}
    d = Path(tempfile.mkdtemp())
    (d / "doc.json").write_text(json.dumps(doc), encoding="utf-8")
    old, vr.INSTANCES = vr.INSTANCES, d
    vr.errors.clear()
    vr.warnings.clear()
    try:
        with redirect_stdout(io.StringIO()):
            rc = vr.main()
    finally:
        vr.INSTANCES = old
    return [] if rc == 0 else list(vr.errors)


def t_404_dan_anonim() -> None:
    assert c.post("/session/tidak-ada/routes").status_code == 404
    sid = _session("", ["Saya konsultan jasa."])
    r = c.post(f"/session/{sid}/routes")
    assert r.status_code == 200, r.text[:200]
    body = r.json()
    assert body["routes"] == [] and body["next_move"] is None
    assert "anonim" in body["reason"]


def t_route_dari_possible_path_dan_valid() -> None:
    sid = _session(USER, ["Saya konsultan, jual jasa ke klien bisnis."])
    art = store.get(sid).diagnosis
    want = {LIB[x] for x in strategy_ids(art) if x in LIB}
    r = c.post(f"/session/{sid}/routes")
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    got = {x["template_id"] for x in body["routes"]} | {x["template_id"] for x in body["not_born"]}
    assert got == want, body
    assert {x["motion"] for x in body["routes"]} == set(load_motion_vocabulary())
    assert all(x["path_id"].startswith("path.") for x in body["routes"]), "route tak tertaut ke Possible Path"
    direct = next(x for x in body["routes"] if x["template_id"] == "direct_outreach_v1")
    assert direct["applicability"]["status"] == "APPLIES", direct["applicability"]
    # Koreksi policy 19 Okt: EXECUTE di atas QUESTION (per-route applicability) —
    # ACTION pada route APPLIES sah; route UNDETERMINED tidak dieksekusi.
    assert body["next_move"]["output"] == "ACTION", body["next_move"]
    assert body["next_move"]["route_id"] == direct["route_id"], body["next_move"]
    assert not _validator_errors(USER, body["next_move"])


def t_route_hanya_untuk_path_yang_bertahan() -> None:
    """Routes are NOT born from the entire template library: only for strategies
    that give birth to a Possible Path."""
    # a gap exists but no running revenue yet: only outreach + paid are backed by the state
    sid = _session("u-routes-subset", ["Saya konsultan, jual jasa ke klien bisnis."],
                   state=dict(target_monthly=60.0, current_monthly=0.0, gap_monthly=60.0))
    got = strategy_ids(store.get(sid).diagnosis)
    assert 0 < len(got) < len(LIB), got
    body = c.post(f"/session/{sid}/routes").json()
    composed = {x["strategy_id"] for x in body["routes"]} | {x["strategy_id"] for x in body["not_born"]}
    assert composed == set(got), (composed, got)


def t_nextmove_tidak_di_path_yang_dihentikan_user() -> None:
    """The LATEST lifecycle is used: a path the user STOPs after diagnosis is no longer a
    NextMove source, even though the diagnosis artifact still stores its old status."""
    uid = "u-routes-stop"
    sid = _session(uid, ["Saya konsultan, jual jasa ke klien bisnis."])
    before = c.post(f"/session/{sid}/routes").json()
    chosen = next(x for x in before["routes"] if x["route_id"] == before["next_move"]["route_id"])
    path_states.apply_and_log(uid, sid, chosen["path_id"], "regret")
    after = c.post(f"/session/{sid}/routes").json()
    nm = after["next_move"]
    assert nm is None or nm["route_id"] != chosen["route_id"], nm
    assert any(x["route_id"] == chosen["route_id"] for x in after["routes"]), "exists != surfaced"


def t_nol_path_tanpa_route() -> None:
    sid = _session("u-routes-zero", ["Saya konsultan."], state=dict())
    assert strategy_ids(store.get(sid).diagnosis) == []
    body = c.post(f"/session/{sid}/routes").json()
    assert body["routes"] == [] and body["next_move"] is None
    assert "Possible Path" in body["reason"], body["reason"]


def t_tanpa_diagnosis_tanpa_route() -> None:
    sid = _session("u-routes-nodiag", ["Saya konsultan."], state=None)
    body = c.post(f"/session/{sid}/routes").json()
    assert body["routes"] == [] and "Possible Path" in body["reason"]


def t_panggilan_ulang_reuse_identitas() -> None:
    sid = _session(USER, ["Saya konsultan, jual jasa ke klien bisnis."])
    b1 = c.post(f"/session/{sid}/routes").json()
    b2 = c.post(f"/session/{sid}/routes").json()
    ids1 = {x["template_id"]: x["route_id"] for x in b1["routes"]}
    ids2 = {x["template_id"]: x["route_id"] for x in b2["routes"]}
    assert ids1 == ids2, "identitas route berubah antar panggilan"
    assert all(x["outcome"] == "ROUTE_REUSED" for x in b2["routes"]), \
        [x["outcome"] for x in b2["routes"]]


def t_goal_present_menutup_lewat_endpoint() -> None:
    uid = "u-routes-goal"
    sid = _session(uid, ["Saya konsultan, jual jasa ke klien bisnis."])
    c.post(f"/session/{sid}/routes")
    # REVISED 17 Oct (D3-closure): the "goal PRESENT" simulation now writes a
    # goal_id-bearing row (production shape, same pattern as the probe A
    # revision) — legacy rows without goal_id are no longer credited to
    # context-bearing readings ("unknown ownership is not shared ownership",
    # see `store.adjudication_ledger._latest_entries`).
    _goal_id = ((store.get(sid).goal or {}).get("goal_id")) or None
    ledger._record_adjudication(uid, {
        "requirement_id": "conversion.commitment_obtained", "status": "PRESENT",
        "rule_evaluation": {"sufficient": True, "partial": False,
                            "no_decisive": False, "contradicting": False},
        "evidence_refs": ["e0"],
        "conflict": {"present_evidence_refs": [], "contradicting_evidence_refs": []},
        "evaluation_time": 1, "adjudicated_at": 1}, rule_mode="PARTIAL",
        goal_id=_goal_id)
    b = c.post(f"/session/{sid}/routes").json()
    direct = next(x for x in b["routes"] if x["template_id"] == "direct_outreach_v1")
    assert direct["outcome"] == "LINEAGE_COMPLETED", direct["outcome"]
    assert direct["derived_status"] == "COMPLETED" and direct["lineage_status"] == "CLOSED"
    assert not _validator_errors(uid, b["next_move"])


def t_pathset_rusak_tidak_500() -> None:
    """This iteration's audit (doc 14 §11): a versioned PathSet that matches but whose CONTENT is
    broken — entries without strategy_id, which downstream readiness subscripts as `p0["strategy_id"]` —
    must not 500 and must not be read as engine findings. The classification gate in compat.py answers
    LEGACY/PATHSET_MALFORMED; HTTP proves it end-to-end: readiness 200 with LEGACY navigation,
    POST /routes 200 without fabricated routes."""
    from core.navigation.evaluator import PATHSET_VERSION

    sid = _session("u-routes-rusak", ["pernah pegang 30 juta per bulan"], state=FULL_STATE)
    s = store.get(sid)
    s.diagnosis = diagnosis_with({"version": PATHSET_VERSION, "paths": [{"path_id": "path.x"}]})
    store.save(s)
    r = c.get(f"/session/{sid}/readiness")
    assert r.status_code == 200, r.text[:200]
    nav = r.json()["navigation"]
    assert nav["status"] == "LEGACY" and nav["reason_code"] == "PATHSET_MALFORMED", nav
    assert nav["needs_rediagnosis"] is True and nav["current_version"] == PATHSET_VERSION, nav
    assert r.json()["paths"] == [], "path dari artefak rusak tidak boleh dibaca sebagai temuan"
    b = c.post(f"/session/{sid}/routes")
    assert b.status_code == 200, b.text[:200]
    body = b.json()
    assert body["routes"] == [] and body["not_born"] == [], body
    assert "diagnosis ulang" in body["reason"], body["reason"]


TESTS = [t_404_dan_anonim, t_route_dari_possible_path_dan_valid, t_route_hanya_untuk_path_yang_bertahan,
         t_nextmove_tidak_di_path_yang_dihentikan_user, t_nol_path_tanpa_route, t_tanpa_diagnosis_tanpa_route,
         t_pathset_rusak_tidak_500, t_panggilan_ulang_reuse_identitas, t_goal_present_menutup_lewat_endpoint]


def main() -> int:
    passed = 0
    try:
        for fn in TESTS:
            try:
                fn()
                passed += 1
                print(f"  PASS  {fn.__name__}")
            except AssertionError as exc:
                print(f"  FAIL  {fn.__name__}: {exc}")
    finally:
        for sid in _created:  # do not leave test sessions behind in store/sessions
            f = store.PERSIST_DIR / f"{sid}.json"
            if f.exists():
                f.unlink()
    print(f"\n{passed}/{len(TESTS)} routes-endpoint tests passed")
    return 0 if passed == len(TESTS) else 1


if __name__ == "__main__":
    sys.exit(main())
