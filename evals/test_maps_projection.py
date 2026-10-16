"""R2 gate — Canonical MAPS Projection (int 03 §5 DoD).

Keys: determinism (same snapshot -> identical model), orthogonality of the three axes
(EXECUTED without PRESENT = "Awaiting proof", NOT done), fail-loud input integrity
(dangling dep / foreign enum / duplicate node / cycle / ghost frontier /
missing revision), no fabrication (a path without a route -> no nodes; no edge
to the goal; no dates), terminal = out-degree 0, multi-frontier carried intact.
Pure unit — no store/LLM.
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # mvp/

from ontology.route.projection import (  # noqa: E402
    PROJECTION_VERSION,
    ProjectionIntegrityError,
    project_maps,
)

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, fn) -> None:
    try:
        fn()
        RESULTS.append((name, True, ""))
    except AssertionError as exc:
        RESULTS.append((name, False, str(exc)))
    except Exception as exc:  # pragma: no cover — unexpected failures still surface
        RESULTS.append((name, False, f"{type(exc).__name__}: {exc}"))


def _node(nid: str, *, resolves=("req.a",), deps=(), sat="UNKNOWN",
         exe="TRUE", view="NOT_STARTED", activity=None):
    return {
        "node_id": nid,
        "resolves": list(resolves),
        "strength": "HARD",
        "depends_on": list(deps),
        "activity": activity or f"Do {nid}",
        "satisfaction": {"status": sat},
        "executability": {"status": exe},
        "execution_view": view,
    }


def _route(**over):
    r = {
        "template_id": "direct_outreach_v1",
        "strategy_id": "direct_outreach",
        "path_id": "p1",
        "path_title": "Direct outreach",
        "strategy": "Reach clients directly.",
        "motion": "MOTION_A",
        "outcome": "ROUTE_CREATED",
        "route_id": "r-1",
        "goal_anchor": "A1",
        "applicability": {"status": "APPLIES", "evidence": ["ev-1"]},
        "lineage_status": "OPEN",
        "derived_status": "OPEN",
        "revision_no": 1,
        "nodes": [
            _node("n1", sat="PRESENT", view="NOT_STARTED"),
            _node("n2", deps=["n1"], exe="TRUE"),
        ],
        "frontier": [{"kind": "EXECUTE", "route_id": "r-1", "node": "n2"}],
    }
    r.update(over)
    return r


def _ctx(**over):
    ctx = {
        "p1": {"title": "Direct outreach", "lifecycle": "OPEN", "status": "OPEN",
               "goal_relation": "PRIMARY", "goal_relation_note": "fastest honest route"},
    }
    ctx.update(over)
    return ctx


GOAL = {"text": "Rp20jt per bulan", "goal_id": "g-1", "version": 2,
        "horizon": None, "metric": {"metric_id": "mrr"}}


# ---------------------------------------------------------------- determinisme
def t_deterministic() -> None:
    a = project_maps([_route()], _ctx(), goal=GOAL)
    b = project_maps([_route()], _ctx(), goal=GOAL)
    assert a == b, "input identik harus menghasilkan model identik"
    assert a["version"] == PROJECTION_VERSION
    assert a["kind"] == "maps_projection"


def t_shape_core() -> None:
    m = project_maps([_route()], _ctx(), goal=GOAL)
    p = m["paths"][0]
    assert p["path_id"] == "p1" and p["route"], "route harus terbawa"
    r = p["route"]
    assert r["route_id"] == "r-1" and r["revision_no"] == 1 and r["lineage_status"] == "OPEN"
    assert [n["node_id"] for n in r["nodes"]] == ["n1", "n2"]
    assert r["edges"] == [{"from": "n1", "to": "n2"}], "edge HANYA dari depends_on"
    # Three axes carried intact, not merged
    n1 = r["nodes"][0]
    assert n1["satisfaction"] == {"status": "PRESENT"}
    assert n1["executability"] == {"status": "TRUE"}
    assert n1["execution"] == {"view": "NOT_STARTED"}
    # typed ref (route_node_ref)
    assert n1["ref"] == {"path_id": "p1", "route_id": "r-1", "route_revision": 1}


# ------------------------------------------------------------- ortogonalitas
def t_executed_without_present_is_awaiting_proof() -> None:
    """Key DoD: EXECUTED without PRESENT MUST be 'awaiting proof', not 'done' (INV-R8)."""
    r = _route(nodes=[_node("n1", sat="ABSENT", exe="TRUE", view="EXECUTED"),
                      _node("n2", deps=["n1"], exe="TRUE")],
               frontier=[{"kind": "VERIFY", "route_id": "r-1", "node": "n1"}])
    m = project_maps([r], _ctx(), goal=GOAL)
    n1 = m["paths"][0]["route"]["nodes"][0]
    assert n1["presentation"] == {"kind": "awaiting_proof", "word": "Awaiting proof"}, n1["presentation"]
    assert n1["satisfaction"]["status"] == "ABSENT", "satisfaction tidak boleh berubah oleh eksekusi"


def t_present_is_done_even_if_executed() -> None:
    r = _route(nodes=[_node("n1", sat="PRESENT", view="EXECUTED")], frontier=[])
    m = project_maps([r], _ctx(), goal=GOAL)
    n1 = m["paths"][0]["route"]["nodes"][0]
    assert n1["presentation"]["kind"] == "done" and n1["presentation"]["word"] == "Confirmed"


def t_frontier_execute_is_now() -> None:
    m = project_maps([_route()], _ctx(), goal=GOAL)
    n2 = m["paths"][0]["route"]["nodes"][1]
    assert n2["frontier_kind"] == "EXECUTE"
    assert n2["presentation"] == {"kind": "now", "word": "Now"}, n2["presentation"]


def t_exec_unknown_is_waiting_and_false_is_locked() -> None:
    r = _route(nodes=[_node("n1", exe="UNKNOWN"), _node("n2", deps=["n1"], exe="FALSE")], frontier=[])
    m = project_maps([r], _ctx(), goal=GOAL)
    nodes = m["paths"][0]["route"]["nodes"]
    assert nodes[0]["presentation"]["kind"] == "waiting"
    assert nodes[1]["presentation"]["kind"] == "locked"


# ----------------------------------------------------------- larangan fabricate
def t_no_route_no_fabricated_nodes() -> None:
    """G02: a path without a route -> NO invented nodes."""
    ctx = _ctx(p2={"title": "Partnership", "lifecycle": "OPEN", "status": "OPEN"})
    m = project_maps([], ctx, goal=GOAL)
    p2 = next(p for p in m["paths"] if p["path_id"] == "p2")
    assert p2["route"] is None and p2["route_unavailable"] == {"reason": "no_route_context"}


def t_stop_path_never_touches_goal() -> None:
    """STOP ends ✕ — no edge/mechanism of any kind links the path to the goal landmark."""
    ctx = _ctx(p1={"title": "Direct outreach", "lifecycle": "STOPPED", "status": "OPEN"})
    m = project_maps([_route()], ctx, goal=GOAL)
    p = m["paths"][0]
    assert p["status_display"] == "STOP" and p["stop_source"] == "you"
    assert "goal" not in [e.get("to") for r in m["paths"] if r["route"] for e in r["route"]["edges"]]


def t_no_dates_on_nodes() -> None:
    """K16: dependency is not a schedule — no date/day fields on nodes."""
    m = project_maps([_route()], _ctx(), goal=GOAL)
    for n in m["paths"][0]["route"]["nodes"]:
        for forbidden in ("day", "date", "due", "deadline", "eta", "duration_days"):
            assert forbidden not in n, f"node membawa field waktu terlarang: {forbidden}"


def t_terminal_is_outdegree_zero_not_last_array() -> None:
    """Terminal = out-degree 0 on the dependency graph, not array position."""
    # Chain n1->n2->n3: only n3 has out-degree 0, even though n3 is last in the array.
    r = _route(nodes=[_node("n1", sat="PRESENT"), _node("n2", deps=["n1"]),
                      _node("n3", deps=["n2"], sat="PRESENT")],
               frontier=[])
    m = project_maps([r], _ctx(), goal=GOAL)
    assert m["paths"][0]["route"]["terminals"] == ["n3"], m["paths"][0]["route"]["terminals"]
    # Two parallel leaves (both n2 AND n3 free) = two terminals — structure, not order.
    r2 = _route(nodes=[_node("n1", sat="PRESENT"), _node("n2", deps=["n1"]),
                       _node("n3", sat="PRESENT")], frontier=[])
    m2 = project_maps([r2], _ctx(), goal=GOAL)
    assert m2["paths"][0]["route"]["terminals"] == ["n2", "n3"]
    # goal_landmark SEPARATE — terminals do not claim the goal is achieved
    assert m["goal_landmark"]["goal_id"] == "g-1" and m["goal_landmark"]["version"] == 2
    assert "TERPISAH" in m["goal_landmark"]["note"]


def t_multi_frontier_all_carried() -> None:
    """MAP-03: every valid frontier entry is carried — not trimmed, no ranking."""
    r = _route(nodes=[_node("n1", sat="PRESENT"), _node("n2"), _node("n3")],
               frontier=[{"kind": "EXECUTE", "route_id": "r-1", "node": "n2"},
                         {"kind": "EXECUTE", "route_id": "r-1", "node": "n3"},
                         {"kind": "VERIFY", "route_id": "r-1", "node": "n1"}])
    m = project_maps([r], _ctx(), goal=GOAL)
    fr = m["paths"][0]["route"]["frontier"]
    assert len(fr) == 3, fr
    kinds = [f["kind"] for f in fr]
    assert kinds.count("EXECUTE") == 2 and kinds.count("VERIFY") == 1


def t_resolve_applicability_has_no_node() -> None:
    r = _route(frontier=[{"kind": "RESOLVE_APPLICABILITY", "route_id": "r-1"}])
    m = project_maps([r], _ctx(), goal=GOAL)
    fr = m["paths"][0]["route"]["frontier"]
    assert fr == [{"kind": "RESOLVE_APPLICABILITY", "route_id": "r-1"}]


# --------------------------------------------------------- fail-loud integrity
def _fails(fn, needle: str) -> None:
    try:
        fn()
    except ProjectionIntegrityError as exc:
        assert needle in str(exc), f"error salah sasaran: {exc}"
        return
    raise AssertionError(f"harusnya ProjectionIntegrityError ({needle})")


def t_fail_dangling_dependency() -> None:
    r = _route(nodes=[_node("n1", deps=["hantu"])], frontier=[])
    _fails(lambda: project_maps([r], _ctx(), goal=GOAL), "menggantung")


def t_fail_unknown_satisfaction_enum() -> None:
    r = _route(nodes=[_node("n1", sat="SELESAI")], frontier=[])
    _fails(lambda: project_maps([r], _ctx(), goal=GOAL), "satisfaction")


def t_fail_unknown_execution_view() -> None:
    r = _route(nodes=[_node("n1", view="DONE")], frontier=[])
    _fails(lambda: project_maps([r], _ctx(), goal=GOAL), "execution_view")


def t_fail_duplicate_node_id() -> None:
    r = _route(nodes=[_node("n1"), _node("n1", deps=["n1"])], frontier=[])
    _fails(lambda: project_maps([r], _ctx(), goal=GOAL), "duplikat")


def t_fail_cycle() -> None:
    r = _route(nodes=[_node("n1", deps=["n2"]), _node("n2", deps=["n1"])], frontier=[])
    _fails(lambda: project_maps([r], _ctx(), goal=GOAL), "siklus")


def t_fail_missing_revision() -> None:
    r = _route(revision_no=None)
    _fails(lambda: project_maps([r], _ctx(), goal=GOAL), "revision_no")


def t_fail_frontier_ghost_node() -> None:
    r = _route(frontier=[{"kind": "EXECUTE", "route_id": "r-1", "node": "hantu"}])
    _fails(lambda: project_maps([r], _ctx(), goal=GOAL), "tidak ada")


def t_fail_unknown_frontier_kind() -> None:
    r = _route(frontier=[{"kind": "MAYBE", "route_id": "r-1", "node": "n2"}])
    _fails(lambda: project_maps([r], _ctx(), goal=GOAL), "frontier kind")


def t_fail_unknown_lineage_status() -> None:
    r = _route(lineage_status="MAYBE")
    _fails(lambda: project_maps([r], _ctx(), goal=GOAL), "lineage_status")


def t_fail_unknown_applicability() -> None:
    r = _route(applicability={"status": "MAYBE"})
    _fails(lambda: project_maps([r], _ctx(), goal=GOAL), "applicability")


def t_fail_node_without_resolves() -> None:
    r = _route(nodes=[_node("n1", resolves=[])], frontier=[])
    _fails(lambda: project_maps([r], _ctx(), goal=GOAL), "resolves")


# --------------------------------------------------------------- focus & nol
def t_focus_block_empty_by_contract() -> None:
    """Projection never derives focus itself (MAP-03) — empty block + contract."""
    m = project_maps([_route()], _ctx(), goal=GOAL)
    f = m["focus"]
    assert f["activeDecisionPathId"] is None and f["selectedPathId"] is None and f["expandedRouteId"] is None
    assert "nextmove.path_id" in f["note"]


def t_zero_paths_is_valid() -> None:
    m = project_maps([], {}, goal=GOAL)
    assert m["paths"] == []


def t_goal_landmark_separate() -> None:
    m = project_maps([_route()], _ctx(), goal=GOAL)
    gl = m["goal_landmark"]
    assert gl["text"] == "Rp20jt per bulan" and gl["metric"] == {"metric_id": "mrr"}


def test_deep_copy_not_mutated() -> None:
    """Projection must not mutate its input (pure function)."""
    r = _route()
    snap = copy.deepcopy(r)
    project_maps([r], _ctx(), goal=GOAL)
    assert r == snap, "input route dimutasi"


ALL = [
    ("determinisme", t_deterministic),
    ("bentuk inti + ref bertipe", t_shape_core),
    ("EXECUTED tanpa PRESENT = awaiting proof", t_executed_without_present_is_awaiting_proof),
    ("PRESENT = done", t_present_is_done_even_if_executed),
    ("frontier EXECUTE = now", t_frontier_execute_is_now),
    ("exec UNKNOWN waiting / FALSE locked", t_exec_unknown_is_waiting_and_false_is_locked),
    ("path tanpa route -> tanpa node karangan", t_no_route_no_fabricated_nodes),
    ("STOP tidak menyentuh goal", t_stop_path_never_touches_goal),
    ("tanpa tanggal pada node", t_no_dates_on_nodes),
    ("terminal = out-degree 0", t_terminal_is_outdegree_zero_not_last_array),
    ("multi-frontier utuh", t_multi_frontier_all_carried),
    ("RESOLVE_APPLICABILITY tanpa node", t_resolve_applicability_has_no_node),
    ("FAIL dep menggantung", t_fail_dangling_dependency),
    ("FAIL enum satisfaction", t_fail_unknown_satisfaction_enum),
    ("FAIL enum execution_view", t_fail_unknown_execution_view),
    ("FAIL node duplikat", t_fail_duplicate_node_id),
    ("FAIL siklus", t_fail_cycle),
    ("FAIL revisi hilang", t_fail_missing_revision),
    ("FAIL frontier node hantu", t_fail_frontier_ghost_node),
    ("FAIL frontier kind asing", t_fail_unknown_frontier_kind),
    ("FAIL lineage_status asing", t_fail_unknown_lineage_status),
    ("FAIL applicability asing", t_fail_unknown_applicability),
    ("FAIL node tanpa resolves", t_fail_node_without_resolves),
    ("focus blok kosong (kontrak)", t_focus_block_empty_by_contract),
    ("nol path sah", t_zero_paths_is_valid),
    ("goal landmark terpisah", t_goal_landmark_separate),
    ("input tidak dimutasi", test_deep_copy_not_mutated),
]


def main() -> int:
    for name, fn in ALL:
        check(name, fn)
    failed = [r for r in RESULTS if not r[1]]
    for name, ok, msg in RESULTS:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f" — {msg}" if msg else ""))
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} PASS — R2 projection gate")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
