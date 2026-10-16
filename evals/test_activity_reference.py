"""R1.6 gate — ActivityReference: one current decision + alternatives labeled by source.

Contract: internal-docs §3.5 (no second chooser) + maps route
experience reconciliation package 02 §3 K18. Pure unit test over pure functions.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # mvp/

from core.navigation.activity_reference import (  # noqa: E402
    ALT_SOURCES,
    CURRENT_SOURCE,
    activity_references,
)

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, fn) -> None:
    try:
        fn()
        RESULTS.append((name, True, ""))
    except AssertionError as exc:
        RESULTS.append((name, False, str(exc)))


PRESENTED = {"kind": "ACTION", "move_id": "mv-1", "headline": "Hubungi 10 calon klien",
             "path_id": "p-outreach", "version": 3, "degraded": False}
FRONTIER = [{"kind": "EXECUTE", "route_id": "r1", "node": "n1", "route_revision": 2,
             "activity": "Susun daftar prospek"},
            {"kind": "VERIFY", "route_id": "r1", "node": "n2", "route_revision": 2}]
MOVES = [{"move_id": "mv-0", "objective": "Tulis penawaran", "lifecycle": "OBSERVED",
          "route_node_ref": {"route_id": "r1", "node_id": "n1", "route_revision": 2}}]
PLAN = {"version": 7, "steps": [{"id": "st1", "title": "Kirim 5 pesan hari ini"}]}


def t_current_only_from_presented() -> None:
    out = activity_references(presented_move=PRESENTED, route_frontier=FRONTIER,
                              move_ledger=MOVES, checkpoint_plan=PLAN)
    cur = out["current"]
    assert cur and cur["source"] == CURRENT_SOURCE and cur["id"] == "mv-1", cur
    assert all(a["source"] != CURRENT_SOURCE for a in out["alternatives"]), \
        "current tidak boleh dobel di alternatif"


def t_no_presented_no_current_no_promotion() -> None:
    out = activity_references(route_frontier=FRONTIER, move_ledger=MOVES, checkpoint_plan=PLAN)
    assert out["current"] is None, "tanpa otoritas -> current None, bukan dipilih dari alternatif"
    assert out["alternatives"], "alternatif tetap terlihat (peluang tak disembunyikan)"


def t_every_alternative_labeled() -> None:
    out = activity_references(route_frontier=FRONTIER, move_ledger=MOVES, checkpoint_plan=PLAN)
    by_src = {s: [a for a in out["alternatives"] if a["source"] == s] for s in ALT_SOURCES}
    assert len(by_src["route_frontier"]) == 2, by_src
    assert len(by_src["canonical_move_ledger"]) == 1 and by_src["canonical_move_ledger"][0]["id"] == "mv-0"
    assert len(by_src["checkpoint_day_by_day"]) == 1
    ck = by_src["checkpoint_day_by_day"][0]
    assert ck["version"] == 7 and ck["checkpoint_version"] == 7, "rencana checkpoint berversi, bisa stale"
    for a in out["alternatives"]:
        assert a["source"] in ALT_SOURCES and a["kind"] and a["id"], a


def t_empty_and_deterministic() -> None:
    empty = activity_references()
    assert empty == {"current": None, "alternatives": [], "sources": list((CURRENT_SOURCE, *ALT_SOURCES))}
    a = activity_references(presented_move=PRESENTED, route_frontier=FRONTIER)
    b = activity_references(presented_move=PRESENTED, route_frontier=FRONTIER)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True), "harus deterministik"


def main() -> int:
    for name, fn in [("current hanya dari presented (otoritas)", t_current_only_from_presented),
                     ("tanpa presented: current None, tanpa promosi", t_no_presented_no_current_no_promotion),
                     ("setiap alternatif berlabel sumber+versi", t_every_alternative_labeled),
                     ("kosong & deterministik", t_empty_and_deterministic)]:
        check(name, fn)
    ok = all(r for _, r, _ in RESULTS)
    for name, r, why in RESULTS:
        print(("PASS " if r else "FAIL ") + name + (f" — {why}" if why else ""))
    print("HASIL:", "SEMUA LULUS" if ok else "ADA GAGAL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
