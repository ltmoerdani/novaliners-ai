"""Route execution ledger + execution_view overlay + action done_at (Today: order-free).

No LLM. Store redirected to a temporary directory; test sessions deleted at the end.
  1. Ledger: the last event per node wins · invalid event/user_id rejected
  2. Overlay: EXECUTE -> VERIFY for EXECUTED nodes; ABANDONED stays EXECUTE;
     satisfaction/executability UNCHANGED (INV-R8) · lineage saved intact
  3. Endpoint: 404/409 · happy path · NextMove becomes EVIDENCE_REQUEST · RESET
  4. The stored instance document still passes validate_route (view is not state)
  5. ActionItem.done_at: set on DONE, cleared when back to TODO; two actions may
     finish consecutively in any order
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
import store.route_execution as rex  # noqa: E402
import store.route_lineages as rl  # noqa: E402

_tmp = Path(tempfile.mkdtemp(prefix="route_exec_"))
rl._BASE = _tmp / "lineages"
rex._BASE = _tmp / "exec"
ledger._LEDGER_ROOT = _tmp / "ledger"

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
from domains.revenue.schema.artifact import DiagnosisArtifact  # noqa: E402
from evals.navigation_fixtures import revenue_artifact  # noqa: E402
from ontology.route import validate_route as vr  # noqa: E402
from store.memory import store  # noqa: E402

c = TestClient(app)
USER = "u-route-exec"
_created: list[str] = []


def _session(user_id: str) -> str:
    r = c.post("/session", json={"goal_text": "naik ke 20 juta per bulan", "language": "id",
                                 "user_id": user_id})
    sid = r.json()["session_id"]
    _created.append(sid)
    s = store.get(sid)
    t = "Saya konsultan, jual jasa ke klien bisnis."
    s.evidence = [EvidenceItem(id="e0", signal=t, source_quote=t, level="self_reported",
                               topic="REVENUE_STATE")]
    # routes are composed from Possible Paths that survive diagnosis
    s.diagnosis = revenue_artifact(current_monthly=30.0, target_monthly=60.0, gap_monthly=30.0,
                                   capacity_utilization=0.5, demand_exists=True, avg_deal_size=10.0)
    store.save(s)
    return sid


def _direct(body: dict) -> dict:
    return next(x for x in body["routes"] if x["template_id"] == "direct_outreach_v1")


def _execute_nodes(route: dict) -> list[str]:
    return [e["node"] for e in route["frontier"] if e["kind"] == "EXECUTE"]


def t_ledger() -> None:
    u = "u-ledger-unit"
    assert rex.latest_views(u) == {}
    rex.record(u, "r1", "n1", "EXECUTED", ts=1)
    rex.record(u, "r1", "n2", "ABANDONED", ts=2)
    rex.record(u, "r1", "n1", "RESET", ts=3)
    v = rex.latest_views(u)
    assert v["n1"]["view"] == "NOT_STARTED" and v["n2"]["view"] == "ABANDONED", v
    for bad in ("DONE", "executed", ""):
        try:
            rex.record(u, "r1", "n1", bad)
            raise AssertionError(f"event {bad!r} harusnya ditolak")
        except ValueError:
            pass
    try:
        rex.record("../x", "r1", "n1", "EXECUTED")
        raise AssertionError("user_id traversal harusnya ditolak")
    except ValueError:
        pass
    assert rex.latest_views("u-other-user") == {}, "ledger bocor lintas user"


def t_endpoint_dan_overlay() -> None:
    sid = _session(USER)
    b = c.post(f"/session/{sid}/routes").json()
    d = _direct(b)
    assert d["applicability"]["status"] == "APPLIES"
    roots = _execute_nodes(d)
    assert roots, d["frontier"]
    node, rid = roots[0], d["route_id"]
    sat_before = {n["node_id"]: (n["satisfaction"], n["executability"]) for n in d["nodes"]}
    url = f"/session/{sid}/routes/{rid}/nodes/{node}/execution"

    # 404: route/node/session absent
    ev = {"event": "EXECUTED"}
    assert c.post(f"/session/{sid}/routes/nope/nodes/{node}/execution", json=ev).status_code == 404
    assert c.post(f"/session/{sid}/routes/{rid}/nodes/nope/execution", json=ev).status_code == 404
    assert c.post(f"/session/tidak-ada/routes/{rid}/nodes/{node}/execution", json=ev).status_code == 404
    # 422: event outside the enum · 409: RESET without a report
    assert c.post(url, json={"event": "DONE"}).status_code == 422
    assert c.post(url, json={"event": "RESET"}).status_code == 409

    # ABANDONED: stays on the EXECUTE frontier (may be retried)
    assert c.post(url, json={"event": "ABANDONED"}).status_code == 200
    d2 = _direct(c.post(f"/session/{sid}/routes").json())
    assert node in _execute_nodes(d2)
    assert next(n for n in d2["nodes"] if n["node_id"] == node)["execution_view"] == "ABANDONED"

    # EXECUTED: EXECUTE -> VERIFY, NextMove = EVIDENCE_REQUEST, satisfaction unchanged
    assert c.post(url, json={"event": "EXECUTED"}).status_code == 200
    b3 = c.post(f"/session/{sid}/routes").json()
    d3 = _direct(b3)
    assert node not in _execute_nodes(d3)
    assert {"kind": "VERIFY", "route_id": rid, "node": node} in d3["frontier"], d3["frontier"]
    assert next(n for n in d3["nodes"] if n["node_id"] == node)["execution_view"] == "EXECUTED"
    sat_after = {n["node_id"]: (n["satisfaction"], n["executability"]) for n in d3["nodes"]}
    assert sat_after == sat_before, "laporan eksekusi tidak boleh mengubah satisfaction/executability"
    nm = b3["next_move"]
    assert nm["output"] == "EVIDENCE_REQUEST" and nm["frontier_ref"] == node, nm
    # already VERIFY -> must not be reported EXECUTED again
    assert c.post(url, json={"event": "EXECUTED"}).status_code == 409

    # the stored document (view is not state) still passes the validator
    doc = rl.build_instance_document(rl.list_rows(USER))
    dd = Path(tempfile.mkdtemp())
    (dd / "doc.json").write_text(json.dumps(doc), encoding="utf-8")
    old, vr.INSTANCES = vr.INSTANCES, dd
    vr.errors.clear()
    try:
        with redirect_stdout(io.StringIO()):
            rc = vr.main()
    finally:
        vr.INSTANCES = old
    assert rc == 0, list(vr.errors)

    # RESET: back to EXECUTE
    assert c.post(url, json={"event": "RESET"}).status_code == 200
    d4 = _direct(c.post(f"/session/{sid}/routes").json())
    assert node in _execute_nodes(d4)


def t_isolasi_user() -> None:
    sid_a = _session("u-exec-a")
    sid_b = _session("u-exec-b")
    a = _direct(c.post(f"/session/{sid_a}/routes").json())
    b = _direct(c.post(f"/session/{sid_b}/routes").json())
    node_a = _execute_nodes(a)[0]
    assert c.post(f"/session/{sid_a}/routes/{a['route_id']}/nodes/{node_a}/execution",
                  json={"event": "EXECUTED"}).status_code == 200
    # user B must not report a node owned by user A's route
    assert c.post(f"/session/{sid_b}/routes/{a['route_id']}/nodes/{node_a}/execution",
                  json={"event": "EXECUTED"}).status_code == 404
    b2 = _direct(c.post(f"/session/{sid_b}/routes").json())
    assert _execute_nodes(b2) == _execute_nodes(b), "laporan user A bocor ke user B"


def t_done_at() -> None:
    art = DiagnosisArtifact.model_validate({
        "status": "provisional", "where_you_are": "x", "primary_constraint": "y",
        "primary_constraint_id": "C6.3", "do_not": "n", "next_best_action": "a",
        "success_metric": "m", "well_know_when": "w", "pivot_rule": "p",
        "day_by_day": ["H1: tulis penawaran", "H2: kirim ke 2 kontak", "H3: follow up"],
    })
    s = store.create("uji done_at", "id")
    s.diagnosis = art
    store.save(s)
    _created.append(s.id)
    sid = s.id
    assert all(i.done_at is None for i in store.get(sid).diagnosis.day_by_day)
    # order-free: the 3rd action finishes first, then the 1st; all on the same day
    r3 = c.post(f"/session/{sid}/action/2/report", json={"status": "DONE"}).json()["action"]
    r1 = c.post(f"/session/{sid}/action/0/report", json={"status": "DONE"}).json()["action"]
    assert r3["done_at"] and r1["done_at"] and r3["done_at"] <= r1["done_at"]
    assert store.get(sid).diagnosis.day_by_day[1].done_at is None
    # back to TODO -> done_at cleared; re-reporting DONE does not move the old timestamp
    again = c.post(f"/session/{sid}/action/0/report", json={"status": "DONE"}).json()["action"]
    assert again["done_at"] == r1["done_at"]
    back = c.post(f"/session/{sid}/action/0/report", json={"status": "TODO"}).json()["action"]
    assert back["done_at"] is None and back["status"] == "TODO"
    # outcome only (no status) does not touch done_at
    c.post(f"/session/{sid}/action/2/report", json={"outcome": "moved"})
    assert store.get(sid).diagnosis.day_by_day[2].done_at == r3["done_at"]


TESTS = [t_ledger, t_endpoint_dan_overlay, t_isolasi_user, t_done_at]


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
        for sid in _created:
            f = store.PERSIST_DIR / f"{sid}.json"
            if f.exists():
                f.unlink()
    print(f"\n{passed}/{len(TESTS)} route-execution tests passed")
    return 0 if passed == len(TESTS) else 1


if __name__ == "__main__":
    sys.exit(main())
