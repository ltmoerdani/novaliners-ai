"""Eval — Canonical same-session Journey timeline (audit D-08).

Tests mvp/app/experience_journey.py as a READ-ONLY projection:
the FIRST session (no prior_session_id) still has a complete timeline; user/engine
roles are mapped; move_event/outcome_observation not swapped; no duplicate event_id;
missing ts -> None (not fabricated); goal version carried; chronological order;
assessment/checkpoint/evidence merged from the authority; superseded evidence flagged;
counts consistent; timeline_summary truncates safely.

The assert/PASS harness follows mvp/evals/test_maps_projection.py. Pure unit — no
store/LLM/network.
"""
from __future__ import annotations

import copy
import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # mvp/

from app.experience_journey import (  # noqa: E402
    EVENT_KINDS,
    JOURNEY_VERSION,
    build_timeline,
    timeline_summary,
)

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, fn) -> None:
    try:
        fn()
        RESULTS.append((name, True, ""))
    except AssertionError as exc:
        RESULTS.append((name, False, str(exc)))
    except Exception as exc:  # noqa: BLE001 — unexpected failures still surface
        RESULTS.append((name, False, f"{type(exc).__name__}: {exc}"))


def _session() -> SimpleNamespace:
    """FIRST session: prior_session_id empty. Real Event, Move, checkpoint, evidence."""
    events = [
        {"event_id": "ce-s-demo-0000", "seq": 0, "session_id": "s-demo", "role": "user",
         "kind": "create_map", "text": "Bikin map", "turn": 0, "ts": 1000, "status": "committed"},
        {"event_id": "ce-s-demo-0001", "seq": 1, "session_id": "s-demo", "role": "user",
         "kind": "message", "text": "Halo", "turn": 1, "ts": 1001, "status": "committed"},
        {"event_id": "ce-s-demo-0002", "seq": 2, "session_id": "s-demo", "role": "engine",
         "kind": "engine", "text": "Balasan", "turn": 1, "ts": 1002, "status": "committed",
         "correlation_id": "ce-s-demo-0001"},
        {"event_id": "ce-s-demo-0003", "seq": 3, "session_id": "s-demo", "role": "user",
         "kind": "move_event", "text": "move mv-1 EXECUTED: sudah dijalankan", "turn": 2,
         "ts": 1003, "status": "committed", "correlation_id": "mv-1"},
        {"event_id": "ce-s-demo-0004", "seq": 4, "session_id": "s-demo", "role": "user",
         "kind": "outcome_observation", "text": "Hasil: 3 klien", "turn": 2, "ts": 1004,
         "status": "committed", "correlation_id": "mv-1"},
        # without a "ts" key -> must be None, not fabricated
        {"event_id": "ce-s-demo-0005", "seq": 5, "session_id": "s-demo", "role": "user",
         "kind": "message", "text": "pesan tanpa ts", "turn": 3, "status": "received"},
    ]
    moves = [
        {"move_id": "mv-1", "objective": "Outreach 10 klien", "lifecycle": "VALIDATED",
         "executed_ts": 1003, "observation_claim_refs": ["c-1"],
         "history": [
             # new event_id -> merged as move_started
             {"state": "STARTED", "ts": 1002, "event_id": "ce-legacy-started", "note": "mulai"},
             # SAME event_id as the spine -> must not be duplicated (spine wins)
             {"state": "EXECUTED", "ts": 1003, "event_id": "ce-s-demo-0003", "note": "sudah"},
             # verdict -> assessment
             {"state": "VALIDATED", "ts": 1005, "event_id": "ce-legacy-valid", "note": "terbukti"},
         ],
         "assessment": {"verdict": "VALIDATED", "event_id": "ce-legacy-valid"}},
    ]
    checkpoints = [
        {"checkpoint_id": "ck-s-demo-001", "version": 1, "status": "current",
         "reason": "Baseline diagnosis", "binding": {"ts": 1006}},
    ]
    evidence = [
        SimpleNamespace(id="ev-1", source="user", source_quote="Saya sudah punya 3 klien",
                        signal="3 klien", superseded=False, level="transactional"),
        # long quote -> title truncated to 160; superseded must show in detail
        SimpleNamespace(id="ev-2", source="user", source_quote="q" * 300,
                        signal="klaim lama", superseded=True, level="behavioral"),
        # duplicate id -> only one evidence entry
        SimpleNamespace(id="ev-1", source="user", source_quote="duplikat id",
                        signal="dup", superseded=False, level="transactional"),
    ]
    return SimpleNamespace(
        id="s-demo", goal_text="Rp20jt", goal={"goal_id": "g-1", "version": 2},
        events=events, moves=moves, checkpoints=checkpoints, evidence=evidence,
        prior_session_id="",  # FIRST session — must not need a prior
    )


S = _session()
T = build_timeline(S, base_dir="/tmp/tidak-dipakai")


def _by_id(timeline: dict, event_id: str) -> list[dict]:
    return [e for e in timeline["events"] if e["event_id"] == event_id]


def _kinds(timeline: dict) -> list[str]:
    return [e["kind"] for e in timeline["events"]]


def t_shape() -> None:
    assert T["version"] == JOURNEY_VERSION == 1
    assert T["session_id"] == "s-demo"
    assert T["source"] == "canonical"
    assert isinstance(T["note"], str) and T["note"]
    for e in T["events"]:
        assert set(e) == {"event_id", "seq", "ts", "kind", "title", "detail", "refs", "source"}, e
        assert e["kind"] in EVENT_KINDS, e["kind"]
        assert e["source"] == "canonical"
        assert isinstance(e["seq"], int) and not isinstance(e["seq"], bool)
        assert isinstance(e["refs"], dict)


def t_first_session_no_prior() -> None:
    assert S.prior_session_id == "", "fixture harus sesi PERTAMA (tanpa prior)"
    assert T["events"][0]["kind"] == "map_created", _kinds(T)
    assert T["events"][0]["event_id"] == "ce-s-demo-0000"
    assert T["counts"]["map_created"] == 1


def t_roles_mapped() -> None:
    um = _by_id(T, "ce-s-demo-0001")
    er = _by_id(T, "ce-s-demo-0002")
    assert len(um) == 1 and um[0]["kind"] == "user_message", um
    assert len(er) == 1 and er[0]["kind"] == "engine_reply", er
    assert er[0]["refs"]["correlation_id"] == "ce-s-demo-0001"


def t_move_executed_vs_outcome() -> None:
    me = _by_id(T, "ce-s-demo-0003")
    oo = _by_id(T, "ce-s-demo-0004")
    assert len(me) == 1 and me[0]["kind"] == "move_executed", me
    assert len(oo) == 1 and oo[0]["kind"] == "outcome_observed", oo
    assert me[0]["event_id"] != oo[0]["event_id"]
    assert me[0]["refs"]["move_id"] == "mv-1"
    assert oo[0]["refs"]["move_id"] == "mv-1"


def t_no_duplicate_event_ids() -> None:
    ids = [e["event_id"] for e in T["events"]]
    assert len(ids) == len(set(ids)), [i for i, c in Counter(ids).items() if c > 1]
    assert all(ids), "event_id tidak boleh kosong"


def t_spine_wins_dedupe() -> None:
    hits = [e for e in T["events"] if e["event_id"] == "ce-s-demo-0003"]
    assert len(hits) == 1, hits
    assert hits[0]["kind"] == "move_executed"
    assert _kinds(T).count("move_executed") == 1


def t_missing_ts_is_none() -> None:
    e = _by_id(T, "ce-s-demo-0005")
    assert len(e) == 1 and e[0]["kind"] == "user_message"
    assert e[0]["ts"] is None, e[0]["ts"]


def t_no_fabricated_ts() -> None:
    allowed = {1000.0, 1001.0, 1002.0, 1003.0, 1004.0, 1005.0, 1006.0}
    for e in T["events"]:
        assert e["ts"] is None or e["ts"] in allowed, (e["event_id"], e["ts"])


def t_goal_version_carried() -> None:
    assert T["goal"] == {"goal_id": "g-1", "version": 2}, T["goal"]


def t_chronological_order() -> None:
    ts_list = [e["ts"] for e in T["events"]]
    non_none = [t for t in ts_list if t is not None]
    assert non_none == sorted(non_none), ts_list
    first_none = ts_list.index(None) if None in ts_list else len(ts_list)
    assert all(t is None for t in ts_list[first_none:]), ts_list
    assert T["events"][0]["kind"] == "map_created"


def t_assessment_from_history() -> None:
    a = _by_id(T, "ce-legacy-valid")
    assert len(a) == 1 and a[0]["kind"] == "assessment", a
    assert a[0]["refs"]["move_id"] == "mv-1"
    assert a[0]["refs"]["state"] == "VALIDATED"
    assert a[0]["title"] == "Assessment: VALIDATED"


def t_move_started_from_history() -> None:
    s = _by_id(T, "ce-legacy-started")
    assert len(s) == 1 and s[0]["kind"] == "move_started", s
    assert s[0]["refs"]["move_id"] == "mv-1"
    assert s[0]["title"] == "Move started"


def t_checkpoint_merged() -> None:
    ck = [e for e in T["events"] if e["kind"] == "checkpoint"]
    assert len(ck) == 1, ck
    assert ck[0]["refs"] == {"checkpoint_id": "ck-s-demo-001", "version": 1}, ck[0]["refs"]
    assert ck[0]["ts"] == 1006, ck[0]["ts"]
    assert ck[0]["title"] == "Baseline diagnosis"


def t_evidence_merged_and_deduped() -> None:
    ev = [e for e in T["events"] if e["kind"] == "evidence"]
    assert len(ev) == 2, ev  # duplicate ev-1 id merged
    one = _by_id(T, "evd:ev-1")
    assert len(one) == 1 and one[0]["refs"]["evidence_id"] == "ev-1"
    assert one[0]["title"] == "Saya sudah punya 3 klien"
    two = _by_id(T, "evd:ev-2")
    assert len(two) == 1 and two[0]["refs"]["evidence_id"] == "ev-2"
    assert len(two[0]["title"]) == 160 and len(two[0]["title"]) <= 160


def t_superseded_flagged() -> None:
    two = _by_id(T, "evd:ev-2")[0]
    assert "superseded" in two["detail"], two["detail"]
    one = _by_id(T, "evd:ev-1")[0]
    assert "superseded" not in one["detail"], one["detail"]


def t_counts_consistent() -> None:
    c = Counter(e["kind"] for e in T["events"])
    assert sum(T["counts"].values()) == len(T["events"])
    assert set(T["counts"]) == set(EVENT_KINDS)
    for kind in EVENT_KINDS:
        assert T["counts"][kind] == c.get(kind, 0), (kind, T["counts"][kind], c.get(kind, 0))
    assert T["counts"]["map_created"] == 1
    assert T["counts"]["user_message"] == 2
    assert T["counts"]["move_executed"] == 1
    assert T["counts"]["outcome_observed"] == 1
    assert T["counts"]["assessment"] == 1
    assert T["counts"]["checkpoint"] == 1
    assert T["counts"]["evidence"] == 2
    assert T["counts"]["move_abandoned"] == 0


def t_summary_truncates_safely() -> None:
    s3 = timeline_summary(T, limit=3)
    assert len(s3["events"]) == 3
    assert s3["total"] == len(T["events"])
    assert s3["truncated"] is True
    assert s3["counts"] == T["counts"]
    full = timeline_summary(T, limit=10_000)
    assert full["events"] == T["events"] and full["truncated"] is False
    empty = timeline_summary(None)
    assert empty["events"] == [] and empty["total"] == 0 and empty["truncated"] is False


def t_missing_attributes_safe() -> None:
    solo = SimpleNamespace(id="solo-1")  # no events/moves/checkpoints/evidence/goal
    tl = build_timeline(solo)
    assert tl["session_id"] == "solo-1"
    assert tl["events"] == []
    assert tl["goal"] is None
    assert set(tl["counts"]) == set(EVENT_KINDS)
    assert all(v == 0 for v in tl["counts"].values())
    assert tl["source"] == "canonical"


def t_pure_no_mutation() -> None:
    snap = copy.deepcopy({"events": S.events, "moves": S.moves,
                          "checkpoints": S.checkpoints, "goal": S.goal})
    ev_ids = [id(x) for x in S.evidence]
    build_timeline(S, base_dir=None)
    assert S.events == snap["events"], "events dimutasi"
    assert S.moves == snap["moves"], "moves dimutasi"
    assert S.checkpoints == snap["checkpoints"], "checkpoints dimutasi"
    assert S.goal == snap["goal"], "goal dimutasi"
    assert [id(x) for x in S.evidence] == ev_ids, "evidence dimutasi/diganti"


def t_checkin_scope_same_session() -> None:
    """P1-03 witness: two sessions sharing ONE Goal. Each timeline must carry ONLY its own session's
    check-in (no silent map-wide mix), with real provenance, ordering and dedup."""
    import tempfile

    from store import checkins as _ci

    with tempfile.TemporaryDirectory() as d:
        goal = {"goal_id": "g-shared", "version": 1}
        a = SimpleNamespace(id="s-A", user_id="u-scope", goal=goal, events=[], moves=[],
                            checkpoints=[], evidence=[])
        b = SimpleNamespace(id="s-B", user_id="u-scope", goal=goal, events=[], moves=[],
                            checkpoints=[], evidence=[])
        _ci.record("u-scope", {"outcome": "mixed", "day": 3, "sid": "s-A", "note": "A"},
                   goal_id="g-shared", op_id="op-A", base_dir=d)
        _ci.record("u-scope", {"outcome": "worked", "day": 9, "sid": "s-B", "note": "B"},
                   goal_id="g-shared", op_id="op-B", base_dir=d)
        ta = build_timeline(a, base_dir=d)
        tb = build_timeline(b, base_dir=d)
        ca = [e for e in ta["events"] if e["kind"] == "checkin"]
        cb = [e for e in tb["events"] if e["kind"] == "checkin"]
        assert len(ca) == 1 and len(cb) == 1, (ca, cb)
        assert ca[0]["refs"]["outcome"] == "mixed" and cb[0]["refs"]["outcome"] == "worked"
        assert ca[0]["refs"]["checkin_id"] != cb[0]["refs"]["checkin_id"], "check-in lintas sesi bocor"
        assert ca[0]["ts"] is not None and cb[0]["ts"] is not None
        assert ta["scope"] == "session" and tb["scope"] == "session"
        ids = [e["event_id"] for e in ta["events"]]
        assert len(ids) == len(set(ids)), "event_id ganda"
        ts = [e["ts"] for e in ta["events"] if e["ts"] is not None]
        assert ts == sorted(ts), ts


CHECKS = [
    ("bentuk timeline + entry", t_shape),
    ("create_map pertama di sesi tanpa prior", t_first_session_no_prior),
    ("role user vs engine dipetakan", t_roles_mapped),
    ("move_executed beda dari outcome_observed", t_move_executed_vs_outcome),
    ("tidak ada event_id ganda", t_no_duplicate_event_ids),
    ("spine menang saat event_id sama", t_spine_wins_dedupe),
    ("ts hilang -> None", t_missing_ts_is_none),
    ("tidak ada ts karangan", t_no_fabricated_ts),
    ("goal version terbawa", t_goal_version_carried),
    ("urutan kronologis + None di akhir", t_chronological_order),
    ("assessment dari history Move", t_assessment_from_history),
    ("move_started dari history Move", t_move_started_from_history),
    ("checkpoint di-merge", t_checkpoint_merged),
    ("evidence di-merge + dedupe", t_evidence_merged_and_deduped),
    ("evidence superseded ditandai", t_superseded_flagged),
    ("counts konsisten", t_counts_consistent),
    ("timeline_summary memangkas aman", t_summary_truncates_safely),
    ("atribut sesi hilang aman", t_missing_attributes_safe),
    ("input tidak dimutasi (murni)", t_pure_no_mutation),
    ("P1-03: scope check-in same-session (dua sesi satu Goal)", t_checkin_scope_same_session),
]


def main() -> int:
    for name, fn in CHECKS:
        check(name, fn)
    failed = [r for r in RESULTS if not r[1]]
    for name, ok, msg in RESULTS:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f" — {msg}" if msg else ""))
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} PASS - experience journey")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
