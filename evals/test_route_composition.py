"""Strategy -> Route Template -> Route (ROUTE-01..05, PATH-07/08) — strategy identity holds up to the route.

Ontology contract under test (internal-docs §7):
    Strategy 1 -> N RouteTemplate;  RouteTemplate N -> 1 Strategy (template.strategy_id).
Relations violating the contract FAIL deterministically — no "template -> path" dict overrides it.
Deterministic, 0 LLM. Run: .venv/bin/python evals/test_route_composition.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")

from evals._store_isolation import isolate_store  # noqa: E402

isolate_store()  # eval: store redirected to tmp — production store untouched

_tmp = Path(tempfile.mkdtemp(prefix="route_comp_"))
import store.adjudication_ledger as ledger  # noqa: E402
import store.path_states as path_states  # noqa: E402
import store.route_lineages as rl  # noqa: E402

rl._BASE = _tmp / "lineages"
ledger._LEDGER_ROOT = _tmp / "ledger"
path_states._STATES = _tmp / "path_states.json"
path_states._HISTORY = _tmp / "path_history.jsonl"

import tempfile as _tempfile_guard  # noqa: E402
from pathlib import Path as _PathGuard  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

import app.main as _app_main_guard  # noqa: E402
import store.events as _event_store_guard  # noqa: E402
from app.main import app  # noqa: E402
from providers.mock import MockProvider as _MockGuard  # noqa: E402

# R4: this test USED TO call real Z.ai (get_llm not patched): it burned quota on every gate-fast.
# The provider is forced to mock; conversation events go to a temporary directory.
_app_main_guard.get_llm = lambda: _MockGuard()
assert _app_main_guard.get_llm().name == "mock", "uji ini hanya boleh berjalan dengan provider mock"
_event_store_guard.EVENTS_DIR = _PathGuard(_tempfile_guard.mkdtemp(prefix="nvl-ev-"))
from core.navigation.contracts import CheckSpec, PossibilitySpace, StrategySpec, path_id_for  # noqa: E402
from core.navigation.evaluator import build_path_set  # noqa: E402
from core.navigation.readiness import build_projection  # noqa: E402
from domains.revenue.navigation.space import revenue_space  # noqa: E402
from engine.requirements import describe  # noqa: E402
from evals.navigation_fixtures import pathset, pp, reader_of, revenue_artifact, route_for  # noqa: E402
from ontology.route.plan import (  # noqa: E402
    RouteCompositionError,
    assert_route_keeps_strategy,
    plan_compositions,
)
from ontology.route.strategies import active_template_library, load_strategies  # noqa: E402
from store.memory import store  # noqa: E402

_results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _results.append((name, ok, detail))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" | {detail}" if detail else ""))


def raises(fn, exc=ValueError) -> str | None:
    try:
        fn()
    except exc as e:
        return str(e)
    return None


def path_with(strategy_id: str, *template_ids: str) -> dict:
    p = pp(strategy_id)
    p["route_substrate"] = {"template_ids": list(template_ids), "available": bool(template_ids)}
    return p


def tpl(template_id: str, strategy_id: str) -> dict:
    return {"template_id": template_id, "strategy_id": strategy_id}


LIB = active_template_library()

# ── Real Revenue: every active strategy -> exactly one path -> template whose strategy is the same ───────
FULL = dict(
    current_monthly=30.0,
    target_monthly=60.0,
    gap_monthly=30.0,
    capacity_utilization=0.5,
    willingness_to_pay="PROVEN_AT_CURRENT_PRICE",
    demand_exists=True,
    avg_deal_size=10.0,
)
art = revenue_artifact(**FULL)
paths = art.possible_paths["paths"]
space_ids = [s.strategy_id for s in revenue_space().strategies]
check(
    "PATH-08: setiap strategi ruang Revenue melahirkan path yang identitasnya path.<strategy_id>",
    sorted(p["path_id"] for p in paths) == sorted(path_id_for(s) for s in space_ids),
    str([p["path_id"] for p in paths]),
)
plan = plan_compositions(paths, LIB)
check(
    "ROUTE-01: rencana komposisi: setiap template membawa strategi path-nya",
    all(t["strategy_id"] == p["strategy_id"] for p, t in plan) and len(plan) == len(paths),
    str([(p["strategy_id"], t["template_id"]) for p, t in plan]),
)
owners = {}
for t in LIB:
    owners.setdefault(t["template_id"], set()).add(t["strategy_id"])
check(
    "ROUTE-03: pustaka Revenue — tiap template milik tepat satu strategi",
    all(len(v) == 1 for v in owners.values()),
)
per_strategy = {}
for t in LIB:
    per_strategy.setdefault(t["strategy_id"], []).append(t["template_id"])
check(
    "ROUTE: pustaka Revenue — satu template per strategi (N>1 belum didukung proyeksi)",
    all(len(v) == 1 for v in per_strategy.values()),
    str(per_strategy),
)

# ── Templates shared across strategies: fail deterministically, not 'last writer wins' ──────────────────
msg = raises(
    lambda: PossibilitySpace(
        "x",
        (
            StrategySpec("s_a", "A", emerges_when="state:a", route_template_ids=("shared_v1",)),
            StrategySpec("s_b", "B", emerges_when="state:b", route_template_ids=("shared_v1",)),
        ),
    )
)
check("ROUTE-04: ruang yang berbagi template antar-strategi ditolak saat dibentuk", bool(msg), msg or "")
msg = raises(
    lambda: plan_compositions(
        [path_with("s_a", "shared_v1"), path_with("s_b", "shared_v1")],
        [tpl("shared_v1", "s_a")],
    ),
    RouteCompositionError,
)
check(
    "ROUTE-02: path s_b tidak bisa memakai template milik s_a (route tidak berganti strategi diam-diam)",
    bool(msg) and "berganti strategi" in msg,
    msg or "",
)
msg = raises(
    lambda: plan_compositions(
        [path_with("s_a", "tpl_a"), {**path_with("s_a", "tpl_a"), "path_id": "path.duplikat"}],
        [tpl("tpl_a", "s_a")],
    ),
    RouteCompositionError,
)
check("ROUTE-04: satu template menjadi substrat dua path (entri path ganda) -> gagal", bool(msg), msg or "")
msg = raises(
    lambda: plan_compositions([path_with("s_a", "tidak_ada")], [tpl("tpl_a", "s_a")]), RouteCompositionError
)
check(
    "ROUTE-04: path merujuk template yang tidak ada di pustaka -> gagal, bukan dilewati", bool(msg), msg or ""
)
msg = raises(lambda: plan_compositions([], [tpl("t", "s"), tpl("t", "s2")]), RouteCompositionError)
check("ROUTE-04: pustaka dengan template_id ganda ditolak", bool(msg), msg or "")

# ── Task F — duplicate-template protection: one template -> one strategy, exactly once at every level ───
msg = raises(
    lambda: StrategySpec(
        "s", "S", emerges_when="state:g", route_template_ids=("t1", "t1", "t2", "t1")
    )
)
check(
    "ROUTE-04: strategi dengan route_template_ids duplikat ditolak saat dibentuk (authoring)",
    bool(msg) and "t1" in str(msg),
    msg or "",
)
msg = raises(
    lambda: plan_compositions(
        [path_with("s_a", "tpl_a", "tpl_a")], [tpl("tpl_a", "s_a")]
    ),
    RouteCompositionError,
)
check(
    "ROUTE-04: template dua kali dalam substrat SATU path -> gagal (dua route identik dilarang)",
    bool(msg),
    msg or "",
)
lib_ids = [t["template_id"] for t in active_template_library()]
check(
    "ROUTE-04: pustaka template Revenue nyata tidak memuat template_id ganda",
    len(lib_ids) == len(set(lib_ids)),
    str(sorted({t for t in lib_ids if lib_ids.count(t) > 1})),
)
reg = load_strategies()
for sid, spec in reg.items():
    tids = spec.get("route_template_ids") or []
    if len(tids) != len(set(tids)):
        check(f"ROUTE-04: strategi {sid} nyata tidak punya template duplikat", False, str(tids))
        break
else:
    check("ROUTE-04: semua strategi registry Revenue nyata bebas template duplikat", True)
    # This iteration's audit: a "live" audit MUST scan the RAW template directory — scanning
    # `active_template_library()` is a vacuum: the loader filters orphan templates (it now
    # raises ValueError, tested in ontology/route/test_templates.py §t_template_yatim_gagal_keras),
    # so orphans will never show up in the active library.
    from ontology.route.strategies import TEMPLATE_DIR

    raw = [json.loads(f.read_text(encoding="utf-8")) for f in sorted(TEMPLATE_DIR.glob("*.json"))]
    raw_ids = [t["template_id"] for t in raw]
    check(
        "ROUTE-04: direktori template mentah tidak memuat template_id ganda",
        len(raw_ids) == len(set(raw_ids)),
        str(sorted({t for t in raw_ids if raw_ids.count(t) > 1})),
    )
    check(
        "ROUTE-04: setiap file template Revenue nyata membawa strategy_id yang terdaftar",
        all(t.get("strategy_id") in reg for t in raw),
        str(sorted({t["template_id"] for t in raw if t.get("strategy_id") not in reg})),
    )

# ── A path without a template stays valid (PATH-07); a strategy with many templates is backed by the plan ──
check(
    "PATH-07: path tanpa substrat route -> tidak ada komposisi, bukan error",
    plan_compositions([path_with("s_a")], [tpl("tpl_a", "s_a")]) == [],
)
two = plan_compositions([path_with("s_a", "t2", "t1")], [tpl("t1", "s_a"), tpl("t2", "s_a")])
check(
    "ROUTE: satu strategi -> banyak template: semua hubungan legitim dipertahankan, urut template_id",
    [(p["strategy_id"], t["template_id"]) for p, t in two] == [("s_a", "t1"), ("s_a", "t2")],
)

# Readiness projection: two routes for one path have no semantics yet -> fail, does NOT overwrite ────────
r1, r2 = route_for("s_a"), {**route_for("s_a"), "route_id": "r-dua", "template_id": "t2"}
msg = raises(
    lambda: build_projection(pathset(pp("s_a")), {"routes": [r1, r2]}, lambda rid: describe(rid, "en"))
)
check(
    "ROUTE-04: readiness menolak dua route untuk satu path (tidak ada overwrite diam-diam)",
    bool(msg),
    msg or "",
)
r_wrong = {**route_for("s_a"), "path_id": "path.lain"}
msg = raises(
    lambda: build_projection(pathset(pp("s_a")), {"routes": [r_wrong]}, lambda rid: describe(rid, "en"))
)
check("ROUTE-02: route yang mengaku milik path lain ditolak proyeksi", bool(msg), msg or "")
proj = build_projection(
    pathset(pp("s_a"), pp("s_b")), {"routes": [route_for("s_b")]}, lambda rid: describe(rid, "en")
)
by = {p["strategy_id"]: p for p in proj["paths"]}
check(
    "ROUTE: route bergabung ke path lewat strategi; path tanpa route tetap muncul",
    by["s_b"]["route"] is not None and by["s_a"]["route"] is None,
)

# ROUTE-01 on lineage: a born route carries its source strategy in reconciliation_key ──────────────
ok = raises(
    lambda: assert_route_keeps_strategy(
        {"path_id": "path.s_a", "strategy_id": "s_a"}, {"reconciliation_key": {"strategy_id": "s_a"}}
    )
)
check("ROUTE-01: lineage dengan strategi yang sama lolos", ok is None)
msg = raises(
    lambda: assert_route_keeps_strategy(
        {"path_id": "path.s_a", "strategy_id": "s_a"}, {"reconciliation_key": {"strategy_id": "s_z"}}
    ),
    RouteCompositionError,
)
check("ROUTE-01: lineage yang membawa strategi lain ditolak", bool(msg), msg or "")

# ── End-to-end over HTTP (real engine): a route carries its path's strategy; route_id != revision ─────────
c = TestClient(app)
USER = "u-route-comp"
sid = c.post(
    "/session", json={"goal_text": "naik ke 20 juta per bulan", "language": "id", "user_id": USER}
).json()["session_id"]
s = store.get(sid)
s.diagnosis = art
store.save(s)
try:
    r = c.post(f"/session/{sid}/routes")
    body = r.json()
    check("E2E: POST /routes sukses atas Possible Path nyata", r.status_code == 200, str(r.status_code))
    path_by_id = {p["path_id"]: p for p in paths}
    rows = body["routes"]
    check(
        "E2E ROUTE-01: setiap route membawa strategy_id & path_id path sumbernya",
        rows and all(path_by_id[x["path_id"]]["strategy_id"] == x["strategy_id"] for x in rows),
        str([(x["path_id"], x["strategy_id"]) for x in rows]),
    )
    check(
        "E2E: setiap template aktif terkomposisi tepat sekali (tidak ada yang tertimpa)",
        sorted(x["template_id"] for x in rows) == sorted(t["template_id"] for t in LIB),
        str(sorted(x["template_id"] for x in rows)),
    )
    ids = {x["path_id"]: x["route_id"] for x in rows}
    again = {
        x["path_id"]: (x["route_id"], x["revision_no"])
        for x in c.post(f"/session/{sid}/routes").json()["routes"]
    }
    check(
        "ROUTE-05: route_id stabil antar komposisi ulang (identitas bukan revisi graph)",
        all(again[k][0] == v for k, v in ids.items()),
    )
    check("ROUTE-05: revision_no terpisah dari route_id", all(isinstance(v[1], int) for v in again.values()))
    rp = c.get(f"/session/{sid}/readiness").json()
    check(
        "E2E: readiness menggabungkan route ke path lewat strategi tanpa tabrakan",
        all((p["route"] or {}).get("template_id") for p in rp["paths"] if p["route_substrate"]["available"]),
    )
    # ── NextMove: a STOP (engine OR user) never yields a workable step ──────────────────
    stopped_engine = {
        p["path_id"]
        for p in paths
        if any(x["source"] == "ENGINE_CONTRADICTION" for x in p["stop_provenance"])
    }
    wtp_art = revenue_artifact(**{**FULL, "willingness_to_pay": "PRICE_SENSITIVE"})
    wtp_stop = {p["path_id"]: p for p in wtp_art.possible_paths["paths"] if p["status"] == "STOP"}
    check(
        "NEXTMOVE: kontradiksi engine (WtP ditolak) menghasilkan STOP dengan asal ENGINE_CONTRADICTION saja",
        wtp_stop
        and all(
            [x["source"] for x in p["stop_provenance"]] == ["ENGINE_CONTRADICTION"] for p in wtp_stop.values()
        )
        and all(p["lifecycle"] == "OPEN" for p in wtp_stop.values())
        and not stopped_engine,
        str(sorted(wtp_stop)),
    )
    s.diagnosis = wtp_art
    store.save(s)
    nm_engine = c.post(f"/session/{sid}/routes").json()
    by_path = {x["path_id"]: x for x in nm_engine["routes"]}
    nm = nm_engine["next_move"]
    check(
        "NEXTMOVE: route path STOP (engine) tetap ada (exists != surfaced) tetapi bukan sumber NextMove",
        all(pid in by_path for pid in wtp_stop)
        and (nm is None or nm.get("route_id") not in {by_path[pid]["route_id"] for pid in wtp_stop})
        and nm is not None,
        str(nm),
    )
    check(
        "NEXTMOVE: STOP engine dan STOP user tetap bisa dibedakan di proyeksi (stop_provenance)",
        all(
            [x["source"] for x in p["stop_provenance"]] == ["ENGINE_CONTRADICTION"]
            for p in c.get(f"/session/{sid}/readiness").json()["paths"]
            if p["path_id"] in wtp_stop
        ),
    )
    for pid in by_path:  # the user stops ALL paths: the STOPPED lifecycle overrides no feasibility
        path_states.apply_and_log(USER, sid, pid, "regret")
    after = c.post(f"/session/{sid}/routes").json()
    rd_after = c.get(f"/session/{sid}/readiness").json()["paths"]
    check(
        "NEXTMOVE: semua path di-STOP user -> tidak ada NextMove yang bisa dikerjakan",
        after["next_move"] is None,
    )
    check(
        "ROUTE-03: lifecycle STOPPED tidak menimpa feasibility; asal STOP tercatat LIFECYCLE",
        all(
            p["lifecycle"] == "STOPPED"
            and p["feasibility"] in ("SUPPORTED", "CONDITIONAL", "CONTRADICTED", "UNDETERMINED")
            and "LIFECYCLE" in [x["source"] for x in p["stop_provenance"]]
            for p in rd_after
        )
        and {p["path_id"]: p["feasibility"] for p in rd_after if p["path_id"] in wtp_stop}
        == {pid: "CONTRADICTED" for pid in wtp_stop},
    )
finally:
    from store.memory import store as _st

    _f = _st.PERSIST_DIR / f"{sid}.json"
    if _f.exists():
        _f.unlink()

# ── Property: any strategy declared into the space -> strategy_id survives Candidate -> Path ────────────
space = PossibilitySpace(
    "prop",
    tuple(
        StrategySpec(
            f"p{i}",
            f"P{i}",
            emerges_when=f"state:t{i}",
            checks=(CheckSpec(f"c{i}", f"state:x{i}"),),
            route_template_ids=(f"p{i}_v1",),
        )
        for i in range(12)
    ),
    goal_signal="state:goal",
)
ps = build_path_set(
    space,
    reader_of(
        {"state:goal": True, **{f"state:t{i}": True for i in range(12)}},
        {"state:goal": ("e-goal",), **{f"state:t{i}": (f"e{i}",) for i in range(12)}},
    ),
)
check(
    "PROP PATH-08: untuk 12 strategi, strategy_id dan path_id bertahan dan template mengikuti strategi",
    all(
        p["path_id"] == f"path.{p['strategy_id']}"
        and p["route_substrate"]["template_ids"] == [f"{p['strategy_id']}_v1"]
        for p in ps["paths"]
    )
    and len(ps["paths"]) == 12,
)
check(
    "PROP: strategi registry Revenue yang aktif semuanya punya template (substrat) dan motion",
    all(v["status"] != "active" or v["strategy_id"] in per_strategy for v in load_strategies().values()),
)

failed = [n for n, ok, _ in _results if not ok]
print("=" * 50)
print(
    f"HASIL: {len(_results) - len(failed)}/{len(_results)} PASS"
    + (f" — {len(failed)} GAGAL ❌" if failed else " ✅")
)
sys.exit(1 if failed else 0)
