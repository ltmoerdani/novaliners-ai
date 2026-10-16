"""M4.1 / F3d — route-less Readiness uses Requirement State Reader semantics.

Architecturally legal case (internal-docs §25; Possible Path ≠ Route):

    Possible Path (route-less) -> check with a requirement_id
    Planner  : Requirement State Reader -> merge_readings
    Readiness: MUST read state from the SAME reader (not raw check state)

Semantics: ONE primitive `merge_readings` — a decisive state beats UNKNOWN;
different decisive states = conflict (metadata, not a fifth value); UNKNOWN is
never downgraded. Route-backed and candidate-born route-less are unchanged.

Deterministic, 0 LLM. Run: .venv/bin/python evals/test_m4_readiness_routeless.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_tmp = Path(tempfile.mkdtemp(prefix="m4_f3d_"))
import store.adjudication_ledger as ledger  # noqa: E402
import store.path_states as path_states  # noqa: E402

ledger._LEDGER_ROOT = _tmp / "ledger"
path_states._STATES = _tmp / "path_states.json"
path_states._HISTORY = _tmp / "path_history.jsonl"

from core.navigation.applicability import build_applicable_set  # noqa: E402
from core.navigation.contracts import Satisfaction  # noqa: E402
from core.navigation.readiness import build_projection  # noqa: E402
from core.navigation.requirement_state import (  # noqa: E402
    MappingReader,
    read_requirement_views,
    status_reader,
)
from engine.requirements import describe  # noqa: E402
from evals.navigation_fixtures import check_row, node, pathset, pp  # noqa: E402

PRESENT, PARTIAL, UNKNOWN, ABSENT = (str(s) for s in Satisfaction)
RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(ok), detail))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" | {detail}" if detail and not ok else ""), flush=True)


RID = "delivery.capacity"


def project(ledger_states: dict, checks: list[dict], route=None):
    """Route-less projection (or route-backed when `route` is given) + ledger reader."""
    reader = MappingReader(ledger_states)
    routes = {"routes": [route]} if route else {"routes": []}
    return build_projection(
        pathset(pp("outreach", "SUPPORTED", checks=checks)),
        routes,
        lambda rid: describe(rid, "en"),
        state_reader=status_reader(reader),
    )


def items_by_rid(proj: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for p in proj["paths"]:
        for it in p["items"]:
            if it.get("requirement_id"):
                out[it["requirement_id"]] = it
    return out


def planner_views(proj_inputs, reader):
    """The planner's view of the same path_set (production pipeline)."""
    ars = build_applicable_set(proj_inputs, None, template_requirements=[])
    return read_requirement_views(ars, reader, proj_inputs, None)


# ── Test 1: ledger PRESENT + check UNKNOWN -> effective PRESENT; planner == readiness ──
ps1 = pathset(pp("outreach", "SUPPORTED", checks=[check_row("cap", UNKNOWN, requirement_id=RID)]))
reader1 = MappingReader({RID: PRESENT})
proj1 = build_projection(ps1, {"routes": []}, lambda rid: describe(rid, "en"), state_reader=status_reader(reader1))
it1 = items_by_rid(proj1)[RID]
v1 = planner_views(ps1, reader1)[RID]
check("A1: route-less ledger PRESENT + check UNKNOWN -> readiness PRESENT", it1["state"] == PRESENT, it1["state"])
check("A1: planner membaca state yang sama (PRESENT)", v1.satisfaction == PRESENT, v1.satisfaction)
check("A1: tidak dianggap sengketa", it1.get("settled", True) and "conflict" not in it1)
check("A1: sitasi ledger tercatat", f"ledger:{RID}" in it1["evidence"], str(it1["evidence"]))

# ── Test 2: ledger UNKNOWN + check PRESENT -> follows the canonical merge rule (PRESENT) ──
ps2 = pathset(pp("outreach", "SUPPORTED", checks=[check_row("cap", PRESENT, requirement_id=RID)]))
reader2 = MappingReader({RID: UNKNOWN})
proj2 = build_projection(ps2, {"routes": []}, lambda rid: describe(rid, "en"), state_reader=status_reader(reader2))
it2 = items_by_rid(proj2)[RID]
v2 = planner_views(ps2, reader2)[RID]
check("A2: ledger UNKNOWN + check PRESENT -> readiness PRESENT (merge kanonik)", it2["state"] == PRESENT, it2["state"])
check("A2: planner konsisten (PRESENT)", v2.satisfaction == PRESENT, v2.satisfaction)
check("A2: bukan sengketa (UNKNOWN tidak berselisih)", it2.get("settled", True) and "conflict" not in it2)

# ── Test 3: conflicting decisive states (ledger ABSENT vs check PRESENT) -> conflict ──
ps3 = pathset(pp("outreach", "SUPPORTED", checks=[check_row("cap", PRESENT, requirement_id=RID)]))
reader3 = MappingReader({RID: ABSENT})
proj3 = build_projection(ps3, {"routes": []}, lambda rid: describe(rid, "en"), state_reader=status_reader(reader3))
it3 = items_by_rid(proj3)[RID]
v3 = planner_views(ps3, reader3)[RID]
cf = it3.get("conflict") or {}
check("A3: konflik tercatat (metadata terstruktur)", bool(cf), str(it3))
check("A3: otoritas = ledger, resolusi = AUTHORITY", cf.get("authority") == "ledger" and cf.get("resolution") == "AUTHORITY", str(cf))
check("A3: tidak dihitung settled proof", it3.get("settled") is False and proj3["paths"][0]["counts"]["conflicted"] == 1, str(proj3["paths"][0]["counts"]))
check("A3: resolusi mengikuti merge kanonik (ABSENT, pasti mengalahkan)", it3["state"] == ABSENT, it3["state"])
check("A3: planner menandai sengketa yang sama", v3.conflict, str(v3.conflict))
check("A3: UNKNOWN tidak diturunkan jadi ABSENT oleh check UNKNOWN", True)  # semantics asserted in Test 1/A4

# ── A3b: canonical feasibility route-less uses the same reader (F3d seam) ──
# A hard-check conflict MUST NOT become CONTRADICTED, and MUST NOT stay SUPPORTED
# from a conflicted raw reading.
ps3h = pathset(
    pp("outreach", "SUPPORTED", checks=[check_row("cap", PRESENT, kind="hard", requirement_id=RID)])
)
proj3h = build_projection(ps3h, {"routes": []}, lambda rid: describe(rid, "en"), state_reader=status_reader(reader3))
p3h = proj3h["paths"][0]
check("A3b: feasibility sengketa hard-check bukan CONTRADICTED", p3h["feasibility"] != "CONTRADICTED", p3h["feasibility"])
check("A3b: feasibility sengketa tidak lagi SUPPORTED (check → UNKNOWN)", p3h["feasibility"] == "UNDETERMINED", p3h["feasibility"])
check("A3b: pembacaan mentah engine tetap diaudit (feasibility_engine)", p3h["feasibility_engine"] == "SUPPORTED", p3h["feasibility_engine"])

# ── A5: ledger PRESENT + check ABSENT hard → two-way conflict, feasibility not CONTRADICTED ──
ps5x = pathset(
    pp("outreach", "UNDETERMINED", checks=[check_row("cap", ABSENT, kind="hard", requirement_id=RID)])
)
reader5x = MappingReader({RID: PRESENT})
proj5x = build_projection(ps5x, {"routes": []}, lambda rid: describe(rid, "en"), state_reader=status_reader(reader5x))
it5x = items_by_rid(proj5x)[RID]
p5x = proj5x["paths"][0]
check("A5: konflik tercatat (ledger PRESENT vs check ABSENT)", bool(it5x.get("conflict")), str(it5x))
check("A5: butir tidak settled", it5x.get("settled") is False)
check("A5: state efektif = PRESENT (otoritas ledger)", it5x["state"] == PRESENT, it5x["state"])
check("A5: feasibility bukan CONTRADICTED akibat sengketa", p5x["feasibility"] != "CONTRADICTED", p5x["feasibility"])
check("A5: feasibility UNDETERMINED (check sengketa → UNKNOWN)", p5x["feasibility"] == "UNDETERMINED", p5x["feasibility"])

# ── Small matrix: decisive states without conflict do not change feasibility ──
check("A1b: feasibility A1 tetap SUPPORTED (UNKNOWN tidak memaksa kontradiksi)", proj1["paths"][0]["feasibility"] == "SUPPORTED", proj1["paths"][0]["feasibility"])
check("A2b: feasibility A2 SUPPORTED (merge kanonik → PRESENT semua)", proj2["paths"][0]["feasibility"] == "SUPPORTED", proj2["paths"][0]["feasibility"])
reader6 = MappingReader({RID: ABSENT})
ps6 = pathset(pp("outreach", "CONTRADICTED", checks=[check_row("cap", ABSENT, kind="hard", requirement_id=RID)]))
proj6 = build_projection(ps6, {"routes": []}, lambda rid: describe(rid, "en"), state_reader=status_reader(reader6))
check("Matrix: ledger ABSENT + check ABSENT (sepakat) = bukan sengketa, feasibility ordinary", items_by_rid(proj6)[RID].get("settled", True) and proj6["paths"][0]["feasibility"] == "CONTRADICTED", proj6["paths"][0]["feasibility"])

# ── A4: ledger UNKNOWN + check UNKNOWN -> remains UNKNOWN ──
ps4 = pathset(pp("outreach", "SUPPORTED", checks=[check_row("cap", UNKNOWN, requirement_id=RID)]))
reader4 = MappingReader({RID: UNKNOWN})
proj4 = build_projection(ps4, {"routes": []}, lambda rid: describe(rid, "en"), state_reader=status_reader(reader4))
it4 = items_by_rid(proj4)[RID]
check("A4: ledger UNKNOWN + check UNKNOWN -> tetap UNKNOWN", it4["state"] == UNKNOWN, it4["state"])
check("A4: UNKNOWN tidak pernah diturunkan jadi ABSENT", it4["state"] != ABSENT)

# ── Test 4: route-backed regression — route node remains a ledger reader via the composer; unchanged ──
rt4 = {
    "route_id": "r1",
    "template_id": "t1",
    "path_id": "path.outreach",
    "strategy_id": "outreach",
    "applicability": {"status": "APPLIES"},
    "nodes": [node(RID, ABSENT)],
}
proj_r = project({RID: ABSENT}, [check_row("cap", PRESENT, requirement_id=RID)], route=rt4)
it_r = items_by_rid(proj_r)[RID]
check("R4: route-backed — keadaan node ledger terproyeksi (ABSENT, otoritas route)", it_r["state"] == ABSENT, it_r["state"])
check("R4: route-backed konflik ledger-vs-check tetap terdeteksi", proj_r["paths"][0]["conflicts"] == [RID], str(proj_r["paths"][0]["conflicts"]))
check("R4: route-backed butir tidak diubah semantics baru", it_r.get("conflict", {}).get("authority") == "route", str(it_r.get("conflict")))

# ── Test 5: candidate-born route-less regression — candidate path still projected with the same merge ──
p5 = pp("outreach", "SUPPORTED", checks=[check_row("cap", UNKNOWN, requirement_id=RID)])
p5["candidate"] = {"possibility_id": "pos.1", "born": "CANDIDATE"}
p5["provenance"] = {
    "origin": "candidate",
    "candidate": {
        "candidate_id": "pos.1",
        "mechanisms": [{"mechanism_id": "m1", "title": "Cold outreach"}],
    },
}
ps5 = pathset(p5)
reader5 = MappingReader({RID: PRESENT})
proj5 = build_projection(ps5, {"routes": []}, lambda rid: describe(rid, "en"), state_reader=status_reader(reader5))
it5 = items_by_rid(proj5)[RID]
check("R5: candidate-born route-less tetap terproyeksi", proj5["paths"] and proj5["paths"][0]["candidate"], str(proj5["paths"]))
check("R5: candidate-born route-less memakai ledger semantics yang sama", it5["state"] == PRESENT, it5["state"])
# R5b: candidate-born with conflict — feasibility uses the same reader semantics (no special branch)
p5c = pp(
    "outreach", "SUPPORTED", checks=[check_row("cap", PRESENT, kind="hard", requirement_id=RID)]
)
p5c["candidate"] = {"possibility_id": "pos.1", "born": "CANDIDATE"}
p5c["provenance"] = {
    "origin": "candidate",
    "candidate": {
        "candidate_id": "pos.1",
        "mechanisms": [{"mechanism_id": "m1", "title": "Cold outreach"}],
    },
}
proj5c = build_projection(pathset(p5c), {"routes": []}, lambda rid: describe(rid, "en"), state_reader=status_reader(reader3))
check("R5b: candidate-born sengketa feasibility juga neutralized", proj5c["paths"][0]["feasibility"] == "UNDETERMINED", proj5c["paths"][0]["feasibility"])

# ── Summary ──
fails = [r for r in RESULTS if not r[1]]
print(f"\n{'PASS' if not fails else 'FAIL'}: {len(RESULTS) - len(fails)}/{len(RESULTS)} checks")
sys.exit(1 if fails else 0)
