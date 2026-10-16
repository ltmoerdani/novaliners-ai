"""Guard for canonical Move event idempotency (D-10/N27) + lifecycle.
Run: cd mvp && .venv/bin/python evals/test_move_event_idempotency.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")

from evals._store_isolation import isolate_store  # noqa: E402

isolate_store()

import store.checkins as ci  # noqa: E402
import store.navigation_links as nl  # noqa: E402
import store.route_execution as rex  # noqa: E402
import store.route_lineages as rl  # noqa: E402

tmp = Path(tempfile.mkdtemp())
for mod in (ci, nl, rex, rl):
    mod._BASE = tmp / "workspaces"

from fastapi.testclient import TestClient  # noqa: E402

from app import moves as mvmod  # noqa: E402
from app.main import app  # noqa: E402
from store import memory  # noqa: E402

FAILED: list[str] = []


def check(cond: bool, label: str) -> None:
    print(("PASS " if cond else "FAIL ") + label)
    if not cond:
        FAILED.append(label)


s = memory.store.create("t", "id", user_id="u-mv", goal={"goal_id": "g-mv", "version": 1})
m = mvmod.create_move(
    s,
    design={"objective": "Kirim 10 pesan", "measurement_method": "hitung balasan",
            "expected_evidence": ["balasan"], "completion_criteria": ["terkirim"],
            "observation_window_days": 7},
    text="kirim 10 pesan", event_id="ce-seed")
memory.store.save(s)
mid = m["move_id"]
c = TestClient(app)
url = f"/session/{s.id}/moves/{mid}/events"

r1 = c.post(url, json={"event": "EXECUTED", "operation_id": "op-mv-1"})
check(r1.status_code == 200 and r1.json()["move"]["lifecycle"] == "EXECUTED", "EXECUTED pertama diterima")
ev1 = r1.json()["event_id"]

r2 = c.post(url, json={"event": "EXECUTED", "operation_id": "op-mv-1"})
check(r2.status_code == 200 and r2.json().get("replayed") is True, "N27: op_id sama -> replay, bukan 409")
check(r2.json()["event_id"] == ev1, "N27: replay memakai event_id yang sama")

r3 = c.post(url, json={"event": "ABANDONED", "operation_id": "op-mv-1"})
check(r3.status_code == 409, "op_id sama + payload beda -> 409 deterministik")

r4 = c.post(url, json={"event": "EXECUTED", "operation_id": "op-mv-2"})
check(r4.status_code == 409, "transisi tak sah EXECUTED->EXECUTED -> 409")

events = [e for e in s.events if e.get("kind") == "move_event"]
check(len(events) == 1, "tepat SATU event move tahan-lama (tidak ada efek ganda)")
check(events[0].get("idempotency_key") == "op-mv-1", "kunci operasi tersimpan pada event")

# a different, valid transition still works and is idempotent on its own key
r5 = c.post(url, json={"event": "ABANDONED", "operation_id": "op-mv-3"})
check(r5.status_code == 200 and r5.json()["move"]["lifecycle"] == "ABANDONED",
      "transisi sah berikutnya diterima")
r6 = c.post(url, json={"event": "ABANDONED", "operation_id": "op-mv-3"})
check(r6.status_code == 200 and r6.json().get("replayed") is True, "replay transisi berikutnya idempoten")

# P1-01: replay equality is TYPED — a non-empty note must not make a legitimate replay fail
m2 = mvmod.create_move(
    s,
    design={"objective": "Kirim 5 sampel", "measurement_method": "hitung respons",
            "expected_evidence": ["respons"], "completion_criteria": ["terkirim"],
            "observation_window_days": 7},
    text="kirim 5 sampel", event_id="ce-seed-2")
memory.store.save(s)
url2 = f"/session/{s.id}/moves/{m2['move_id']}/events"
n1 = c.post(url2, json={"event": "EXECUTED", "note": "catatan penting", "operation_id": "op-note-1"})
check(n1.status_code == 200, "P1-01: EXECUTED dengan catatan diterima")
n2 = c.post(url2, json={"event": "EXECUTED", "note": "catatan penting", "operation_id": "op-note-1"})
check(n2.status_code == 200 and n2.json().get("replayed") is True,
      "P1-01: replay dengan catatan non-kosong tetap replay (bukan 409)")
n3 = c.post(url2, json={"event": "EXECUTED", "note": "catatan BERBEDA", "operation_id": "op-note-1"})
check(n3.status_code == 409, "P1-01: catatan berbeda di op_id sama -> 409")

n_total = 12
print()
if FAILED:
    print(f"{n_total - len(FAILED)}/{n_total} PASS - move event idempotency ({len(FAILED)} FAIL)")
    for f in FAILED:
        print("  - " + f)
    sys.exit(1)
print(f"{n_total}/{n_total} PASS - move event idempotency")
