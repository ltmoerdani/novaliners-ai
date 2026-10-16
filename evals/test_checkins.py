"""Guard for durable check-ins (audit V4 D-02/N02/N10/N27).
Run: cd mvp && .venv/bin/python evals/test_checkins.py
Deterministic, no LLM/network (the HTTP section uses TestClient + a tmp store).
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")

from store import checkins  # noqa: E402

FAILED: list[str] = []


def check(cond: bool, label: str) -> None:
    print(("PASS " if cond else "FAIL ") + label)
    if not cond:
        FAILED.append(label)


tmp = Path(tempfile.mkdtemp())
U = "u-checkin"

# 1-3: missing != 0, explicit 0 stays 0
r1 = checkins.record(U, {"outcome": "mixed", "contacted": None, "replies": "", "calls": 3,
                         "paid": None, "rp": None, "day": 7}, goal_id="gA", base_dir=tmp)
check(r1["contacted"] is None, "N10: contacted tidak dilaporkan -> None (bukan 0)")
check(r1["replies"] is None, "N10: replies kosong -> None (bukan 0)")
check(r1["calls"] == 3 and r1["paid"] is None, "nilai dilaporkan tersimpan apa adanya")
r2 = checkins.record(U, {"outcome": "none", "contacted": 10, "replies": 0, "calls": 0},
                     goal_id="gA", base_dir=tmp)
check(r2["replies"] == 0 and r2["contacted"] == 10, "N02: 0 eksplisit tetap 0, bukan unknown")

# 4-6: validation
for bad, label in [
    ({"outcome": "maybe"}, "outcome tak dikenal ditolak"),
    ({"outcome": "worked", "contacted": True}, "boolean bukan angka -> ditolak"),
    ({"outcome": "worked", "paid": "abc"}, "string bukan angka -> ditolak"),
]:
    try:
        checkins.record(U, bad, goal_id="gA", base_dir=tmp)
        check(False, label)
    except checkins.CheckinError:
        check(True, label)

# 7: numeric string accepted (client inputs are text)
r3 = checkins.record(U, {"outcome": "worked", "contacted": "12", "paid": "1500000", "rp": "12.5"},
                     goal_id="gA", base_dir=tmp)
check(r3["contacted"] == 12 and r3["paid"] == 1500000 and r3["rp"] == 12.5,
      "angka berbentuk string dinormalkan")

# 8: idempotent per op_id -> one row, same id
a = checkins.record(U, {"outcome": "mixed", "day": 9}, goal_id="gA", op_id="op-1", base_dir=tmp)
b = checkins.record(U, {"outcome": "mixed", "day": 9}, goal_id="gA", op_id="op-1", base_dir=tmp)
rows = checkins.list_rows(U, tmp)
check(a["checkin_id"] == b["checkin_id"], "N27: op_id sama -> baris yang sama dikembalikan")
check(sum(1 for r in rows if r.get("op_id") == "op-1") == 1, "N27: tidak ada baris ganda")

# 8b: P1-02 — the SAME operation key with a DIFFERENT payload is a conflict, not a silent no-op
try:
    checkins.record(U, {"outcome": "worked", "day": 9}, goal_id="gA", op_id="op-1", base_dir=tmp)
    check(False, "P1-02: op_id sama + payload beda -> konflik")
except checkins.CheckinConflict:
    check(True, "P1-02: op_id sama + payload beda -> CheckinConflict")

# 9-10: scope isolation + legacy readability
checkins.record(U, {"outcome": "worked", "day": 2}, goal_id="gB", base_dir=tmp)
goal_a = checkins.latest(U, goal_id="gA", base_dir=tmp)
check(all(r.get("goal_id") in ("gA", None, "") for r in goal_a), "baris goal lain TIDAK bocor")
checkins.record(U, {"outcome": "mixed"}, goal_id=None, base_dir=tmp)   # legacy without goal
legacy = checkins.latest(U, goal_id="gA", base_dir=tmp)
check(any(r.get("goal_id") in (None, "") for r in legacy), "baris legacy tanpa goal tetap terbaca")

# 11: chronological order + created_ts
ts_sorted = [r.get("created_ts") for r in checkins.latest(U, goal_id="gA", base_dir=tmp)]
check(ts_sorted == sorted(ts_sorted), "riwayat urut kronologis")
check(all(isinstance(r.get("created_ts"), int) for r in goal_a), "created_ts diisi server")

# 12: user isolation (different user = different file)
check(checkins.list_rows("u-other", tmp) == [], "user lain tidak melihat check-in user ini")

# 13-16: HTTP endpoints (POST then GET), null handling over the wire
from fastapi.testclient import TestClient  # noqa: E402

from store import events as event_store  # noqa: E402
from store import memory  # noqa: E402

session_dir = tmp / "sessions"
event_dir = tmp / "events"
memory.store.PERSIST_DIR = session_dir
event_store.EVENTS_DIR = event_dir
s = memory.store.create("target 25jt", "id", user_id="u-http-c", goal={"goal_id": "gA", "version": 1})
event_store.append_event(s, role="user", kind=event_store.KIND_CREATE_MAP, text=s.goal_text)
memory.store.save(s)

# point the store's own base at the temp dir by monkeypatching the module constant
import store.checkins as _ci  # noqa: E402

_orig_base = _ci._BASE
_ci._BASE = tmp

from app.main import app  # noqa: E402

c = TestClient(app)
resp = c.post(f"/session/{s.id}/checkin", json={"outcome": "mixed", "contacted": 4, "replies": None,
                                                 "operation_id": "http-op-1"})
check(resp.status_code == 200, "POST /checkin -> 200")
body = resp.json()
check(body["checkin"]["replies"] is None, "HTTP: null tetap null (bukan 0)")
check(body["checkin"]["contacted"] == 4, "HTTP: angka tersimpan")
resp2 = c.post(f"/session/{s.id}/checkin", json={"outcome": "mixed", "contacted": 4,
                                                 "operation_id": "http-op-1"})
check(resp2.json()["checkin"]["checkin_id"] == body["checkin"]["checkin_id"],
      "HTTP: operation_id sama -> replay, bukan baris kedua")
g = c.get(f"/session/{s.id}/checkins")
check(g.status_code == 200 and len(g.json()["checkins"]) == 1, "GET /checkins -> satu baris")
bad = c.post(f"/session/{s.id}/checkin", json={"outcome": "nope"})
check(bad.status_code == 422, "HTTP: outcome tak sah -> 422")

# P0-05: a check-in carrying an action report on a session WITHOUT a diagnosis must not partially
# commit. Action validation runs BEFORE any write, so no check-in row is recorded on rejection.
before_rows = len(c.get(f"/session/{s.id}/checkins").json()["checkins"])
partial = c.post(f"/session/{s.id}/checkin", json={"outcome": "worked", "action_index": 0,
                                                   "action_status": "DONE", "operation_id": "op-partial"})
check(partial.status_code == 409, "P0-05: action report tanpa diagnosis -> 409")
after_rows = len(c.get(f"/session/{s.id}/checkins").json()["checkins"])
check(after_rows == before_rows, "P0-05: tidak ada check-in parsial saat aksi ditolak")
_ci._BASE = _orig_base

n_total = 25
print()
if FAILED:
    print(f"{n_total - len(FAILED)}/{n_total} PASS - checkins ({len(FAILED)} FAIL)")
    for f in FAILED:
        print("  - " + f)
    sys.exit(1)
print(f"{n_total}/{n_total} PASS - checkins")
