"""Guard MAP-06 Rebuild View: GET /session/{sid}/routes READ-ONLY (C07/D-03).
Run: cd mvp && .venv/bin/python evals/test_routes_read_only.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")

from evals._store_isolation import isolate_store  # noqa: E402

isolate_store()

import store.navigation_links as nl  # noqa: E402
import store.route_execution as rex  # noqa: E402
import store.route_lineages as rl  # noqa: E402

tmp = Path(tempfile.mkdtemp())
for mod in (nl, rex, rl):
    mod._BASE = tmp / "workspaces"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from store import memory  # noqa: E402

FAILED: list[str] = []


def check(cond: bool, label: str) -> None:
    print(("PASS " if cond else "FAIL ") + label)
    if not cond:
        FAILED.append(label)


c = TestClient(app)
s = memory.store.create("peta baru", "id", user_id="u-ro", goal={"goal_id": "g-ro", "version": 1})
memory.store.save(s)

r = c.get(f"/session/{s.id}/routes")
check(r.status_code == 200, "GET /routes -> 200")
d = r.json()
check(d.get("read_only") is True, "ditandai read_only")
check(d["routes"] == [] and d["next_move"] is None, "tanpa route yang lahir -> kosong jujur")
check(bool(d.get("reason")), "ada alasan yang jujur (bukan komposisi diam-diam)")
check(bool((d.get("reality") or {}).get("projection_revision")), "membawa reality revision")
check(rl.list_rows("u-ro") == [], "GET /routes TIDAK melahirkan lineage (0 baris)")

# POST /routes without a Possible Path also births no route (composition contract)
p = c.post(f"/session/{s.id}/routes")
check(p.status_code == 200 and rl.list_rows("u-ro") == [], "POST /routes tanpa path tetap 0 baris lineage")

# anonymous session: an honest answer, not a 500
a = memory.store.create("anon", "id")
memory.store.save(a)
ra = c.get(f"/session/{a.id}/routes")
check(ra.status_code == 200 and ra.json()["user_id"] is None, "sesi anonim -> 200, user_id null")
check("anonim" in (ra.json().get("reason") or ""), "sesi anonim -> alasan anonim")

# missing session -> 404
check(c.get("/session/tidak-ada/routes").status_code == 404, "sesi tak ada -> 404")

n_total = 10
print()
if FAILED:
    print(f"{n_total - len(FAILED)}/{n_total} PASS - routes read-only ({len(FAILED)} FAIL)")
    for f in FAILED:
        print("  - " + f)
    sys.exit(1)
print(f"{n_total}/{n_total} PASS - routes read-only")
