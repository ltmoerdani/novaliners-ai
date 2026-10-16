"""P0-02 guard: a read-only route projection must NEVER append a lineage row.

Regression this locks: GET /session/{sid}/routes and GET /experience used to call the composer,
whose re-projection appends a last-row-wins lineage row on EVERY call (route lineage grew on read).
Run: python evals/test_routes_read_only_no_write.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ontology.route.compose import compose_route  # noqa: E402
from ontology.route.test_compose import (  # noqa: E402
    E_APPLIES,
    GOAL,
    SCOPE,
    TEMPLATE,
    reader,
)
from store import route_lineages as rl  # noqa: E402

FAILED: list[str] = []


def check(cond: bool, label: str) -> None:
    print(("PASS " if cond else "FAIL ") + label)
    if not cond:
        FAILED.append(label)


def _compose(tmp, *, read_only):
    return compose_route(TEMPLATE, goal_anchor=GOAL, scope_anchor=SCOPE, evidence=E_APPLIES,
                         requirement_status_reader=reader({}), motion="ACQUISITION",
                         user_id="u-ro", base_dir=tmp, read_only=read_only)


with tempfile.TemporaryDirectory() as d:
    r0 = _compose(d, read_only=True)
    check(r0["outcome"] == "NO_ROUTE_READ_ONLY" and r0.get("lineage") is None,
          "read-only tanpa lineage OPEN -> tidak melahirkan route")
    check(rl.list_rows("u-ro", d) == [], "read-only tanpa lineage OPEN -> 0 baris ditulis")

    r1 = _compose(d, read_only=False)
    check(r1["outcome"] == "ROUTE_CREATED", "write mode melahirkan route")
    n1 = len(rl.list_rows("u-ro", d))
    check(n1 == 1, f"write mode menulis 1 baris (dapat {n1})")

    r2 = _compose(d, read_only=True)
    check(r2["outcome"] == "ROUTE_REUSED", "read-only memakai lineage OPEN -> ROUTE_REUSED")
    check(r2["lineage"]["route_id"] == r1["lineage"]["route_id"],
          "route_id dipertahankan (INV-R13)")
    n2 = len(rl.list_rows("u-ro", d))
    check(n2 == n1, f"P0-02: read-only TIDAK menambah baris lineage (tetap {n1}, dapat {n2})")

    r3 = _compose(d, read_only=False)
    n3 = len(rl.list_rows("u-ro", d))
    check(r3["outcome"] == "ROUTE_REUSED" and n3 == n1 + 1,
          f"write mode tetap append (bukti guard bermakna: {n1} -> {n3})")

print()
if FAILED:
    print(f"FAIL - routes read-only no-write ({len(FAILED)} FAIL)")
    for f in FAILED:
        print("  - " + f)
    sys.exit(1)
print("PASS - routes read-only no-write (8 checks)")
