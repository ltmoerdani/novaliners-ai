"""R6/BC-02 — Goal-scoped Moves: STALE Move observations & verdicts must not contaminate another Goal.

Deterministic, 0 LLM. Run: cd mvp && .venv/bin/python evals/test_move_goal_scope.py

Contract: int 16 BC-02/BC-03 ("Goal A does not contaminate Goal B"), CP-30, CP-33; int 20 AC-G09/W-14.
Pure guard on the production module app/moves.py.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import moves as mv  # noqa: E402
from core.reasoning.hypotheses import hypothesis_id  # noqa: E402

_results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _results.append((name, ok, detail))
    print(f"  {'OK ' if ok else 'GAGAL'}  {name}" + (f" | {detail}" if detail else ""))


def _session(goal: dict, *, moves=None, hypotheses=None, nodes=None, events=None) -> SimpleNamespace:
    return SimpleNamespace(id="gs-01", goal=goal, moves=moves if moves is not None else [],
                           hypotheses=hypotheses if hypotheses is not None else {},
                           state_graph={"nodes": nodes or {}, "edges": {}},
                           events=events if events is not None else [])


def _design(hid: str = "") -> dict:
    return {"objective": "balas <24 jam", "expected_evidence": ["respons naik"],
            "measurement_method": "catat respons", "observation_window_days": 7,
            "completion_criteria": ["3 inquiry dibalas"], "linked_hypothesis_id": hid}


def _execute_and_observe(s, mid: str, claim: str, seq: int) -> None:
    ev = f"ce-e{seq:04d}"
    s.events.append({"event_id": ev, "seq": seq, "role": "user"})
    node = {"id": claim, "status": "active", "provenance": {"event_id": ev, "session": s.id}}
    s.state_graph["nodes"][claim] = node
    mv.transition(s, mid, mv.EXECUTED, event_id=ev, now=1000)
    mv.attach_observation(s, mid, ev, [claim], now=1000)


# ---------------------------------------------------------------- 1. same Goal
hid = hypothesis_id("follow-up lambat adalah penyebab prospek hilang")
s = _session({"goal_id": "goal-A", "version": 1})
s.hypotheses[hid] = {"id": hid, "statement": "follow-up lambat adalah penyebab prospek hilang",
                     "supports": [], "contradicts": [], "missing_evidence": [], "knowledge_refs": [],
                     "status": "active", "history": [], "standing": "tentative"}
m = mv.create_move(s, design=_design(hid), text="Balas cepat tiga inquiry.", event_id="ce-propose")
_execute_and_observe(s, m["move_id"], "cl-obs-1", 2)
check("Move menyimpan Goal + versi asal (BC-03)",
      m["linked_goal_id"] == "goal-A" and m["linked_goal_version"] == 1)
check("Goal sama → tidak ada pelanggaran scope", mv._goal_scope_problems(s, m) == [])
a_ok = {"move_id": m["move_id"], "verdict": "UNSUPPORTED", "observed_claim_refs": ["cl-obs-1"],
        "rationale": "tidak ada respons"}
check("Goal sama → putusan lolos guard", mv.assessment_problems(s, a_ok, now=1000 + 8 * 86400) == [])
mv.apply_assessment(s, a_ok, event_id="ce-assess", now=1000 + 8 * 86400)
check("Goal sama → putusan diterapkan + hipotesis diperbarui",
      s.moves[0]["lifecycle"] == "UNSUPPORTED" and s.hypotheses[hid]["contradicts"] == ["cl-obs-1"])

# ------------------------------------------------- 2. explicit Goal rebind A→B
s.goal = {"goal_id": "goal-B", "version": 1}
check("rebind A→B → scope Move basi terdeteksi", bool(mv._goal_scope_problems(s, m)))
try:
    mv.attach_observation(s, m["move_id"], "ce-other", ["cl-obs-2"])
    blocked = False
except mv.MoveError:
    blocked = True
check("rebind A→B → observasi pada Move lama tidak diikat (MoveError)", blocked)
check("rebind A→B → putusan Move lama ditolak guard dengan alasan Goal",
      any(v.startswith("G11 move milik Goal")
          for v in mv.assessment_problems(s, a_ok, now=1000 + 8 * 86400)))

# ------------------------------------------------------- 3. Goal revision v1→v2
s.goal = {"goal_id": "goal-A", "version": 2}
check("revisi Goal v1→v2 → Move v1 basi (pelanggaran versi)",
      any("v1" in v and "v2" in v for v in mv._goal_scope_problems(s, m)))
check("revisi Goal v1→v2 → putusan ditolak guard",
      any(v.startswith("G11 move dibuat pada Goal")
          for v in mv.assessment_problems(s, a_ok, now=1000 + 8 * 86400)))
try:
    mv.apply_assessment(s, a_ok, event_id="ce-assess-2", now=1000 + 8 * 86400)
    applied = True
except mv.MoveError:
    applied = False
check("revisi Goal → apply_assessment menolak (tidak ada promosi diam-diam)", not applied)

# ------------------------------------------------------------- 4. legacy compat
s2 = _session({"goal_id": "goal-C", "version": 1})
m2 = mv.create_move(s2, design=_design(), text="langkah lama", event_id="ce-legacy")
m2["linked_goal_id"] = ""          # Move era pra-Goal-linkage
m2["linked_goal_version"] = None
_execute_and_observe(s2, m2["move_id"], "cl-legacy-1", 2)
check("Move legacy tanpa linkage Goal tidak dipaksa (kompat)",
      mv._goal_scope_problems(s2, m2) == []
      and mv.attach_observation(s2, m2["move_id"], "ce-x", [])["lifecycle"] == mv.OBSERVED)

# ------------------------------------------------------------------ 5. summaries
sm = mv.summaries(s)
check("summaries membawa keterkaitan Goal (audit UI/reasoner)",
      sm and sm[0].get("linked_goal_id") == "goal-A" and sm[0].get("linked_goal_version") == 1)

# =====================================================================
# A3 / Round 7 (AC-G): F1 stale-Move EXECUTION + F2 stale-Move OBSERVATION.
# Contract: check_transition rejects a stale Move BEFORE the execution event; the /message
# endpoint rejects a stale move_id (goal_scope_problems) BEFORE semantic classification/commit.
# Same guard (BC-02/BC-03/CP-30), no new engine.
# =====================================================================
import copy  # noqa: E402

R7 = "R7: "

def _rejections_do_not_mutate(s, snapshot, label: str) -> None:
    cur = {"lifecycle": s.moves[0]["lifecycle"], "history": list(s.moves[0]["history"]),
           "events": len(s.events), "claims": list(s.moves[0]["observation_claim_refs"])}
    check(R7 + label + " → tanpa efek samping (lifecycle/history/event/klaim)", cur == snapshot, str(cur))

# ---------------------------------------------- (a) same Goal, valid version → passes
sA = _session({"goal_id": "goal-D", "version": 3})
mA = mv.create_move(sA, design=_design(), text="langkah sah", event_id="ce-r7-a")
check(R7 + "(a) Goal sama + versi sama → check_transition EXECUTED lolos",
      mv.check_transition(sA, mA["move_id"], mv.EXECUTED)["move_id"] == mA["move_id"])
check(R7 + "(a) check_transition murni validasi (lifecycle tetap PLANNED)",
      sA.moves[0]["lifecycle"] == mv.PLANNED and len(sA.moves[0]["history"]) == 1)
mv.transition(sA, mA["move_id"], mv.EXECUTED, event_id="ce-r7-a2", now=2000)
check(R7 + "(a) transisi EXECUTED sesungguhnya berhasil pada Goal yang sama",
      sA.moves[0]["lifecycle"] == mv.EXECUTED)

# ------------------------------------- (b) different Goal → rejected, no effects
sA.goal = {"goal_id": "goal-E", "version": 1}
_snap_b = {"lifecycle": sA.moves[0]["lifecycle"], "history": list(sA.moves[0]["history"]),
           "events": len(sA.events), "claims": list(sA.moves[0]["observation_claim_refs"])}
try:
    mv.check_transition(sA, mA["move_id"], mv.EXECUTED)
    rej_b = False
except mv.MoveError:
    rej_b = True
check(R7 + "(b) Goal berbeda → eksekusi Move ditolak (MoveError)", rej_b)
_rejections_do_not_mutate(sA, _snap_b, "(b)")

# ----------------------------------- (c) same Goal, newer version → rejected
sA.goal = {"goal_id": "goal-D", "version": 4}
try:
    mv.check_transition(sA, mA["move_id"], mv.ABANDONED)
    rej_c = False
except mv.MoveError:
    rej_c = True
check(R7 + "(c) Goal sama v3→v4 → eksekusi Move v3 ditolak (MoveError)", rej_c)
_rejections_do_not_mutate(sA, _snap_b, "(c)")

# ------------------------------------------- (d) legacy unlinked → old policy
sL = _session({"goal_id": "goal-F", "version": 1})
mL = mv.create_move(sL, design=_design(), text="legacy", event_id="ce-r7-d")
mL["linked_goal_id"] = ""
mL["linked_goal_version"] = None
check(R7 + "(d) Move legacy tanpa linkage → eksekusi tetap sah (kompat)",
      mv.check_transition(sL, mL["move_id"], mv.EXECUTED)["move_id"] == mL["move_id"])

# ------------------------------ (e) audit sweep: rejection writes nothing
n_events_before = len(sA.events)
try:
    mv.attach_observation(sA, mA["move_id"], "ce-r7-e", ["cl-r7-e"])
except mv.MoveError:
    pass
check(R7 + "(e) observasi stale juga ditolak & tidak ada event/outcome baru",
      len(sA.events) == n_events_before and sA.moves[0]["observation_claim_refs"] == []
      and sA.moves[0]["outcome_reference"] is None
      and {"lifecycle": sA.moves[0]["lifecycle"], "history": list(sA.moves[0]["history"])}
          == {"lifecycle": _snap_b["lifecycle"], "history": _snap_b["history"]})

# --------------------- (f) hypotheses of an unrelated Goal unchanged by the rejection
hid_u = hypothesis_id("hipotesis milik Goal lain")
sA.hypotheses[hid_u] = {"id": hid_u, "statement": "hipotesis milik Goal lain",
                        "supports": [], "contradicts": [], "missing_evidence": [],
                        "knowledge_refs": [], "status": "active", "history": [],
                        "standing": "tentative"}
h_before = copy.deepcopy(sA.hypotheses[hid_u])
try:
    mv.apply_assessment(sA, {"move_id": mA["move_id"], "verdict": "VALIDATED",
                             "observed_claim_refs": ["cl-x"], "rationale": "x"},
                        event_id="ce-r7-f", now=9000)
except mv.MoveError:
    pass
check(R7 + "(f) penolakan tidak mengubah hipotesis Goal lain (bita-identik)",
      sA.hypotheses[hid_u] == h_before)

# --------------------------- (g) existing success lifecycle still works normally
sG = _session({"goal_id": "goal-G", "version": 1})
mG = mv.create_move(sG, design=_design(), text="normal", event_id="ce-r7-g")
_execute_and_observe(sG, mG["move_id"], "cl-r7-g", 3)
check(R7 + "(g) siklus sukses normal tetap utuh (EXECUTED→OBSERVED)",
      sG.moves[0]["lifecycle"] == mv.OBSERVED
      and sG.moves[0]["observation_claim_refs"] == ["cl-r7-g"])

# ------------------------------------------------- (h) idempotent retry stays idempotent
mv.attach_observation(sG, mG["move_id"], "ce-r7-g", ["cl-r7-g"], now=3100)
mv.attach_observation(sG, mG["move_id"], "ce-r7-g", ["cl-r7-g"], now=3200)
check(R7 + "(h) retry observasi idempoten (klaim ter-de dup, refs & rujukan stabil)",
      sG.moves[0]["observation_claim_refs"] == ["cl-r7-g"]
      and sG.moves[0]["outcome_reference"] == "ce-r7-g"
      and sG.moves[0]["lifecycle"] == mv.OBSERVED)
check(R7 + "(h) guard scope publik setuju pada Move yang sah",
      mv.goal_scope_problems(sG, sG.moves[0]) == [])


fails = [r for r in _results if not r[1]]
print(f"\n{'=' * 50}\nHASIL Goal-scope Move: {len(_results) - len(fails)}/{len(_results)} PASS"
      + (" OK" if not fails else f" — {len(fails)} GAGAL"))
sys.exit(1 if fails else 0)
