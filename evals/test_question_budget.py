"""MC-07 (Oct 18, owner decision) — MONOTONIC QUESTION BUDGET per batch.

Contract proven:
  B1  batch 1 opens on the first turn: initial = clamp(open_askable, 1..10).
  B2  MONOTONIC: every presented QUESTION/EVIDENCE_REQUEST lowers remaining by exactly 1;
      engine counts oscillating (open_askable up/down) do NOT change the number within a batch.
  B3  HOLD/ACTION do not consume budget (not questions).
  B4  remaining reaches 0 → the NEXT user turn opens a new batch automatically
      (initial = clamp(current open_askable, 1..8), batch += 1) — the "continue" option.
  B5  persist: the question_budget field is stored & reloaded from the session store.
  B6  attach_question_budget injects state into the response summary.

Run: .venv/bin/python evals/test_question_budget.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # mvp/

import json  # noqa: E402
import tempfile  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from app.navigation import (  # noqa: E402
    QB_FLOOR,
    QB_MAX_INITIAL,
    QB_MAX_NEXT,
    attach_question_budget,
    update_question_budget,
)
from store.memory import Session, SessionStore  # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(ok), detail))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" | {detail}" if detail and not ok else ""), flush=True)


def nav_of(kind: str, open_ask: int, crit=None, nonb=None):
    cp = {} if crit is None and nonb is None else {"critical_count": crit, "nonblocking_count": nonb}
    return SimpleNamespace(
        decision={"reason": {"counts": {"open_askable": open_ask}}},
        presented={"kind": kind, "checkpoint": cp},
    )


s = Session(id="s-qb", goal_text="g", language="en")

# ── B1 · first batch ──────────────────────────────────────────────────────────────────────────
qb = update_question_budget(s, nav_of("QUESTION", 6))
check("B1a batch 1 dibuka dengan initial = open_askable (6)",
      qb["batch"] == 1 and qb["initial"] == 6 and qb["remaining"] == 5, str(qb))  # that question counted

qb2 = update_question_budget(s, nav_of("QUESTION", 9))   # engine counts UP 6→9
check("B2a MONOTON: osilasi engine (open 6→9) tidak menaikkan angka",
      qb2["remaining"] == 4 and qb2["initial"] == 6, str(qb2))

qb3 = update_question_budget(s, nav_of("QUESTION", 2))   # engine down — number stays on batch track
check("B2b turun tepat 1 per pertanyaan (5→4→3)",
      qb3["remaining"] == 3, str(qb3))

qb4 = update_question_budget(s, nav_of("HOLD", 7))
check("B3 HOLD tidak mengurangi anggaran", qb4["remaining"] == 3, str(qb4))
qb4b = update_question_budget(s, nav_of("ACTION", 7))
check("B3b ACTION tidak mengurangi anggaran", qb4b["remaining"] == 3, str(qb4b))

# ── B4 · exhausted → new batch auto-opens on the next update ─────────────────────────────────
s.question_budget = {"batch": 1, "initial": 3, "answered": 3, "remaining": 0, "open_at_start": 6}
qb5 = update_question_budget(s, nav_of("QUESTION", 5))
check("B4a remaining 0 + giliran baru → batch 2 dibuka (cap QB_MAX_NEXT)",
      qb5["batch"] == 2 and qb5["initial"] == min(5, QB_MAX_NEXT) and qb5["remaining"] == qb5["initial"] - 1,
      str(qb5))
check("B4b initial batch baru dibatasi QB_MAX_NEXT (8)", QB_MAX_NEXT == 8)
check("B4c initial batch pertama dibatasi QB_MAX_INITIAL (10)", QB_MAX_INITIAL == 10)

s2 = Session(id="s-qb2", goal_text="g", language="en")
qb6 = update_question_budget(s2, nav_of("QUESTION", 25))
check("B1b clamp atas: open 25 → initial 10", qb6["initial"] == 10, str(qb6))
s3 = Session(id="s-qb3", goal_text="g", language="en")
qb7 = update_question_budget(s3, nav_of("QUESTION", 0))
check("B1c open 0 (engine belum menyatakan) → default 3; QB_FLOOR menjamin tak pernah di bawah 1",
      qb7["initial"] == 3 and QB_FLOOR == 1, str(qb7))

# ── B5 · persist ─────────────────────────────────────────────────────────────────────────────
store = SessionStore()
store.PERSIST_DIR = Path(tempfile.mkdtemp(prefix="qb_"))
s.question_budget = {"batch": 2, "initial": 5, "answered": 2, "remaining": 3, "open_at_start": 7}
store.save_strict(s)
raw = json.loads((store.PERSIST_DIR / f"{s.id}.json").read_text(encoding="utf-8"))
check("B5a question_budget tersimpan di snapshot sesi", raw.get("question_budget") == s.question_budget,
      str(raw.get("question_budget")))
store2 = SessionStore()
store2.PERSIST_DIR = store.PERSIST_DIR
store2._load_all()
loaded = store2.get(s.id)
check("B5b dimuat kembali dari disk oleh store baru",
      loaded is not None and loaded.question_budget == s.question_budget,
      str(getattr(loaded, "question_budget", None)))

# ── B6 · attach summary ──────────────────────────────────────────────────────────────────────
summary = attach_question_budget({"counts": {}}, s)
check("B6 attach_question_budget menyisipkan state ke ringkasan",
      summary["question_budget"]["batch"] == 2 and "remaining" in summary["question_budget"])

# ── B7 · MC-08: estimasi LLM (checkpoint reasoner) sebagai sumber initial ───────────────────────
print("B7 — MC-08 initial dari estimasi LLM (crit+nonb reasoner), fallback berjenjang")
s7 = Session(id="s-qb7", goal_text="g", language="en")
qbL = update_question_budget(s7, nav_of("QUESTION", 0, crit=2, nonb=5))
check("B7a estimasi LLM crit2+nonb5 → initial 7 (bukan default 3 meski open=0)",
      qbL["initial"] == 7, str(qbL))
s7b = Session(id="s-qb7b", goal_text="g", language="en")
qbL2 = update_question_budget(s7b, nav_of("QUESTION", 0, crit=1, nonb=0))
check("B7b estimasi LLM kecil (crit1) → initial 1", qbL2["initial"] == 1, str(qbL2))
s7c = Session(id="s-qb7c", goal_text="g", language="en")
qbL3 = update_question_budget(s7c, nav_of("QUESTION", 0, crit=9, nonb=8))
check("B7c clamp atas QB_MAX_INITIAL: 17 → 10", qbL3["initial"] == 10, str(qbL3))
s7d = Session(id="s-qb7d", goal_text="g", language="en")
qbL4 = update_question_budget(s7d, nav_of("QUESTION", 0, crit=0, nonb=0))
check("B7d checkpoint 0/0 (tak ada unknown dilihat) → fallback open→3",
      qbL4["initial"] == 3, str(qbL4))
s7e = Session(id="s-qb7e", goal_text="g", language="en")
qbL5 = update_question_budget(s7e, nav_of("QUESTION", 6))
check("B7e checkpoint absen → fallback open_askable (6)", qbL5["initial"] == 6, str(qbL5))

fails = [r for r in RESULTS if not r[1]]
print(f"\n{'✅' if not fails else '❌'} {len(RESULTS) - len(fails)}/{len(RESULTS)} check lulus")
sys.exit(1 if fails else 0)
