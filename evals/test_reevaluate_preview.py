"""Guard for MAP-06 Re-evaluate Preview (C08/D-11) - non-mutating, deterministic.
Run: cd mvp && .venv/bin/python evals/test_reevaluate_preview.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")

FAILED: list[str] = []


def check(cond: bool, label: str) -> None:
    print(("PASS " if cond else "FAIL ") + label)
    if not cond:
        FAILED.append(label)


tmp = Path(tempfile.mkdtemp())
from core.schema.evidence import EvidenceItem  # noqa: E402
from store import events as event_store  # noqa: E402
from store import memory  # noqa: E402

memory.store.PERSIST_DIR = tmp / "sessions"
event_store.EVENTS_DIR = tmp / "events"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

c = TestClient(app)

# --- session with a checkpoint basis and a superseded + new evidence item
s = memory.store.create("target 25jt", "id", user_id="u-prev", goal={"goal_id": "g1", "version": 1})
s.evidence = [
    EvidenceItem(id="ev-1", signal="a", level="self_reported", topic="t"),
    EvidenceItem(id="ev-2", signal="b", level="self_reported", topic="t"),
    EvidenceItem(id="ev-3", signal="c", level="self_reported", topic="t", superseded=True),
]
s.checkpoints = [{
    "checkpoint_id": "ck-prev-1", "version": 1, "status": "current", "reason": "diagnosis",
    "binding": {"state_version": "sv-old", "goal_version": 1, "knowledge": {}, "prompts": {},
                "source_evidence_refs": ["ev-1"]},
}]
memory.store.save(s)

r = c.get(f"/session/{s.id}/reevaluate-preview")
check(r.status_code == 200, "GET /reevaluate-preview -> 200")
d = r.json()
check(d["mutating"] is False, "preview TIDAK memutasi")
check(d["checkpoint"]["checkpoint_id"] == "ck-prev-1", "checkpoint terakhir dibawa")
check("ev-2" in d["basis"]["evidence_added_since_checkpoint"], "bukti baru sejak checkpoint terlihat")
check("ev-1" not in d["basis"]["evidence_added_since_checkpoint"], "bukti basis tidak dihitung baru")
check("ev-3" in d["basis"]["evidence_superseded"], "bukti superseded dilaporkan, tidak dihapus")
check(d["material_change"] is True, "perubahan material terdeteksi")
check(d["would_supersede_checkpoint"] is True and d["next_checkpoint_version"] == 2,
      "versi checkpoint berikutnya dihitung")

# --- no checkpoint: honest, no fabricated material change
s2 = memory.store.create("peta baru", "id", user_id="u-prev2", goal={"goal_id": "g2", "version": 1})
memory.store.save(s2)
d2 = c.get(f"/session/{s2.id}/reevaluate-preview").json()
check(d2["checkpoint"] is None, "tanpa checkpoint -> checkpoint null")
check(d2["material_change"] is False, "tanpa checkpoint -> tidak mengarang perubahan material")
check(d2["would_supersede_checkpoint"] is False and d2["next_checkpoint_version"] == 1,
      "tanpa checkpoint -> versi berikutnya 1")

# --- non-mutation proof: the session file/state is unchanged by the preview
before = dict(s.checkpoints[0]["binding"])
c.get(f"/session/{s.id}/reevaluate-preview")
check(s.checkpoints[0]["binding"] == before, "preview tidak mengubah checkpoint (in-memory)")
check(s.checkpoints[0]["version"] == 1, "preview tidak menaikkan versi checkpoint")

n_total = 12
print()
if FAILED:
    print(f"{n_total - len(FAILED)}/{n_total} PASS - reevaluate preview ({len(FAILED)} FAIL)")
    for f in FAILED:
        print("  - " + f)
    sys.exit(1)
print(f"{n_total}/{n_total} PASS - reevaluate preview")
