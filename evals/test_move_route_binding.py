"""R1.5 gate — typed RouteNode↔Move binding (route_node_ref) + lineage guard.

Contract: internal-docs §3 (v0.2): the NEW TYPED
binding {route_id, node_id, route_revision}; `binding_id` stays the decision-basis fingerprint
(bd-<hash>) and is NOT reused. Pure unit.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # mvp/

from app.moves import MoveError, create_move, design_problems, route_ref_problems  # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, fn) -> None:
    try:
        fn()
        RESULTS.append((name, True, ""))
    except AssertionError as exc:
        RESULTS.append((name, False, str(exc)))


# Phase 7 (internal-docs): Move wajib memiliki ACTION LIST;
# observasi tetap diberi window 1..180 hari.
DESIGN = {
    "objective": "Hubungi 10 calon klien",
    "measurement_method": "jumlah kontak terkirim",
    "expected_evidence": ["log kontak"],
    "completion_criteria": ["10 kontak"],
    "observation_window_days": 7,
    "actions": [{"title": "Hubungi 10 calon klien via WhatsApp"}],
}


def _sess():
    return SimpleNamespace(id="s1", goal={"goal_id": "g1", "version": 1})


def _rows(revision_no: int = 2, node_ids=("n1", "n2")):
    return [{"lineage": {"route_id": "r1", "revisions": [
        {"revision_no": 1, "nodes": [{"node_id": "n0"}]},
        {"revision_no": revision_no, "nodes": [{"node_id": n} for n in node_ids]},
    ]}}]


REF = {"route_id": "r1", "node_id": "n1", "route_revision": 2}


def t_shape() -> None:
    for bad in (
        {"route_id": "r1", "node_id": "n1"},                       # missing key
        {**REF, "extra": 1},                                       # foreign key
        {"route_id": "", "node_id": "n1", "route_revision": 1},    # empty
        {"route_id": "r1", "node_id": "n1", "route_revision": "2"},  # wrong type
        {"route_id": "r1", "node_id": "n1", "route_revision": 0},  # < 1
        "r1/n1",                                                   # free string forbidden
    ):
        try:
            create_move(_sess(), design={**DESIGN, "route_node_ref": bad}, text="t", event_id="e1")
            raise AssertionError(f"shape {bad!r} harusnya MoveError")
        except MoveError:
            pass


def t_stored_and_independent_from_binding_id() -> None:
    mv = create_move(_sess(), design={**DESIGN, "route_node_ref": REF},
                     text="t", event_id="e1", binding_id="bd-abc123")
    assert mv["route_node_ref"] == REF, mv["route_node_ref"]
    assert mv["binding_id"] == "bd-abc123", "binding_id tetap hidup apa adanya (fingerprint)"
    mv2 = create_move(_sess(), design=DESIGN, text="t", event_id="e2")
    assert mv2["route_node_ref"] is None, "tanpa ref = sah (node boleh hidup tanpa Move)"


def t_guard_problems() -> None:
    ok = create_move(_sess(), design={**DESIGN, "route_node_ref": REF}, text="t", event_id="e3")
    assert route_ref_problems(ok, _rows()) == []
    missing = create_move(_sess(), design={**DESIGN, "route_node_ref": {**REF, "route_id": "r?"}},
                          text="t", event_id="e4")
    assert any("tidak ada di workspace" in p for p in route_ref_problems(missing, _rows()))
    stale = create_move(_sess(), design={**DESIGN, "route_node_ref": {**REF, "route_revision": 1}},
                        text="t", event_id="e5")
    assert any("basi" in p for p in route_ref_problems(stale, _rows()))
    ghost_node = create_move(_sess(), design={**DESIGN, "route_node_ref": {**REF, "node_id": "n?"}},
                             text="t", event_id="e6")
    assert any("tidak ada di revisi" in p for p in route_ref_problems(ghost_node, _rows()))
    no_ref = create_move(_sess(), design=DESIGN, text="t", event_id="e7")
    assert route_ref_problems(no_ref, []) == []


def t_design_contract_untouched() -> None:
    assert design_problems({"objective": "x"}) != [], "kontrak desain lama tetap berlaku"
    assert design_problems({**DESIGN}) == [], DESIGN


def main() -> int:
    for name, fn in [("shape tervalidasi", t_shape),
                     ("disimpan & independen dari binding_id", t_stored_and_independent_from_binding_id),
                     ("guard lineage (ada/basi/node)", t_guard_problems),
                     ("kontrak desain Phase 7 utuh (dengan action list)", t_design_contract_untouched)]:
        check(name, fn)
    ok = all(r for _, r, _ in RESULTS)
    for name, r, why in RESULTS:
        print(("PASS " if r else "FAIL ") + name + (f" — {why}" if why else ""))
    print("HASIL:", "SEMUA LULUS" if ok else "ADA GAGAL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
