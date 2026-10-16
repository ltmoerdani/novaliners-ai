"""Guard for the GET /session/{sid}/experience + /timeline contract (V4 section 4; D-04/D-05/D-08).
Run: cd mvp && .venv/bin/python evals/test_experience_endpoint.py
Deterministic, no LLM/network (TestClient + tmp store).
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")

from evals._store_isolation import isolate_store  # noqa: E402

base = isolate_store()

import store.checkins as ci  # noqa: E402
import store.navigation_links as nl  # noqa: E402
import store.route_execution as rex  # noqa: E402
import store.route_lineages as rl  # noqa: E402
import store.workspace as ws  # noqa: E402

tmp = Path(tempfile.mkdtemp())
for mod in (ci, nl, rex, rl, ws):
    mod._BASE = tmp / "workspaces"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from store import events as event_store  # noqa: E402
from store import memory  # noqa: E402

FAILED: list[str] = []


def check(cond: bool, label: str) -> None:
    print(("PASS " if cond else "FAIL ") + label)
    if not cond:
        FAILED.append(label)


c = TestClient(app)
s = memory.store.create("catering 12jt -> 25jt", "id", user_id="u-exp",
                        goal={"goal_id": "g-exp", "version": 1})
event_store.append_event(s, role="user", kind=event_store.KIND_CREATE_MAP, text=s.goal_text)
memory.store.save(s)

snaps_before = len(getattr(s, "experience_snapshots", []) or [])
r = c.get(f"/session/{s.id}/experience")
check(r.status_code == 200, "GET /experience -> 200")
d = r.json()
check(d["version"] == 1 and d["source"] == "LIVE", "version + source LIVE")
rev = d["revision"]
check(bool(rev.get("projection_revision")), "revision.projection_revision ada")
check(all(k in rev for k in ("state_version", "execution_revision", "outcome_revision",
                             "link_revision", "graph_revision")),
      "komponen revisi lengkap")
ids = {n["graph_id"] for n in d["graph"]["nodes"]}
check("here" in ids, "graph punya node HERE")
check("goal:g-exp:1" in ids, "graph punya landmark GOAL terpisah")
check("change_set" in d["graph"] and "no_material_change" in d["graph"]["change_set"], "graph.change_set ada")
check(d["integrity"]["compatible"] is True, "integrity compatible")
check(any(e.get("kind") == "map_created" for e in d["journey_events"]), "journey_events memuat map_created")
check(len(getattr(s, "experience_snapshots", []) or []) == snaps_before,
      "P0-03: GET /experience TIDAK menulis snapshot (baca murni)")
check(d["integrity"].get("route_projection_status") in ("ok", "not_born", "degraded"),
      "P1-04: status proyeksi route dilaporkan eksplisit")

# P1-06: a REJECTED operation must not advance the accepted snapshot baseline.
snaps_pre = len(getattr(s, "experience_snapshots", []) or [])
bad_ck = c.post(f"/session/{s.id}/checkin", json={"outcome": "mixed", "contacted": "abc",
                                                  "operation_id": "op-bad-1"})
check(bad_ck.status_code == 422, "P1-06: contacted='abc' -> 422")
check(len(getattr(s, "experience_snapshots", []) or []) == snaps_pre,
      "P1-06: operasi ditolak TIDAK memajukan baseline snapshot")

# same reality on another surface
st = c.get(f"/session/{s.id}/state").json()
check(st["reality"]["projection_revision"] == rev["projection_revision"],
      "STATE membawa projection_revision yang SAMA dengan /experience")
mv = c.get(f"/session/{s.id}/moves").json()
check(mv["reality"]["projection_revision"] == rev["projection_revision"],
      "MOVES membawa projection_revision yang SAMA (satu realitas lintas destinasi)")
nv = c.get(f"/session/{s.id}/navigation")
check(nv.status_code == 200 and nv.json()["reality"]["projection_revision"] == rev["projection_revision"],
      "NAVIGATION membawa projection_revision yang SAMA")
rt = c.get(f"/session/{s.id}/routes").json()
check(rt["reality"]["projection_revision"] == rev["projection_revision"],
      "GET /routes (Rebuild View) membawa projection_revision yang SAMA")

# stable read: second call identical, no material change
d2 = c.get(f"/session/{s.id}/experience").json()
check(d2["revision"]["projection_revision"] == rev["projection_revision"], "revisi stabil antar panggilan")
check(d2["graph"]["change_set"]["no_material_change"] is True, "change_set: tidak ada perubahan material")

# an accepted check-in must move the composite revision (D-02 x D-05)
ck = c.post(f"/session/{s.id}/checkin", json={"outcome": "mixed", "contacted": 5, "operation_id": "op-x"})
check(ck.status_code == 200, "POST /checkin -> 200")
d3 = c.get(f"/session/{s.id}/experience").json()
check(d3["revision"]["projection_revision"] != rev["projection_revision"],
      "check-in mengubah projection_revision (D-02 x D-05)")
check(d3["revision"]["state_version"] == rev["state_version"],
      "klaim state_version TIDAK berubah oleh check-in (N24)")
st3 = c.get(f"/session/{s.id}/state").json()
check(st3["reality"]["projection_revision"] == d3["revision"]["projection_revision"],
      "STATE tetap sinkron dengan /experience SETELAH mutasi check-in")
check("outcome_revision" in (d3["graph"]["change_set"].get("causes") or []),
      "P1-05: change_set.causes menjelaskan perubahan outcome dari peristiwa kanonik")
check("outcome" in (d3["graph"]["change_set"].get("cause_classes") or {}),
      "P1-06: cause_classes menandai perubahan sebagai outcome")
check(d3["graph"]["change_set"].get("topology_changed") is False,
      "P1-06: check-in TIDAK dilaporkan sebagai perubahan topologi")

# an admitted cross-route link must move projection_revision CHEAPLY (link_revision), without the
# read surface building a graph or re-composing routes
import store.navigation_links as _nl  # noqa: E402

_nl.append_link("u-exp", {"kind": "BRANCH_FROM", "from": {"move_id": "mv-x"},
                          "to": {"route_id": "rt-x", "node_id": "n1", "route_revision": 1},
                          "declaration_ref": "decl:x", "source_event_refs": ["ce-1"],
                          "evidence_refs": [], "context_id": "g-exp"})
d4 = c.get(f"/session/{s.id}/experience").json()
check(d4["revision"]["link_revision"] != d3["revision"]["link_revision"],
      "link_revision berubah saat link diterima")
check(d4["revision"]["projection_revision"] != d3["revision"]["projection_revision"],
      "link diterima -> projection_revision berubah tanpa membangun graph")
check(any("LINK_ENDPOINT_NOT_IN_GRAPH" in u["reason"] for u in d4["graph"]["unsupported_edges"]),
      "link dengan endpoint di luar graph -> unsupported (N20), bukan edge hantu")

# timeline endpoint
tl = c.get(f"/session/{s.id}/timeline")
check(tl.status_code == 200 and len(tl.json().get("events", [])) >= 1, "GET /timeline -> 200 + event")

n_total = 30
print()
if FAILED:
    print(f"{n_total - len(FAILED)}/{n_total} PASS - experience endpoint ({len(FAILED)} FAIL)")
    for f in FAILED:
        print("  - " + f)
    sys.exit(1)
print(f"{n_total}/{n_total} PASS - experience endpoint")
