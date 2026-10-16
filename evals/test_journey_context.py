"""Guard J7 (internal-docs §7) — cross-session delta consumption by diagnosis (closed loop).

  1. reassess_status: DUE/NOT_YET/UNKNOWN — deterministic, degrades safely
  2. compile_journey_context: prior verdict + demotion from user outcomes
  3. journey_prompt_block: compact block (≤6 lines) — not a transcript
  4. demote_interventions: final menu/scope filtered per user outcome
  5. GET /journey: enriched with reassess + prior_actions (J7-a)
  6. store: created_ts survives persistence; sessions_by_user; outcomes_by_intervention
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, ".")

from evals._store_isolation import isolate_store  # noqa: E402

isolate_store()  # eval: store redirected to tmp — production store untouched

import tempfile as _tempfile_guard  # noqa: E402
from pathlib import Path as _PathGuard  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

import app.main as _app_main_guard  # noqa: E402
import store.events as _event_store_guard  # noqa: E402
from app.main import app  # noqa: E402
from providers.mock import MockProvider as _MockGuard  # noqa: E402

# R4: this test USED to call real Z.ai (get_llm unpatched): it burned quota on every gate-fast.
# Provider forced to mock; conversation events go to a temp directory.
_app_main_guard.get_llm = lambda: _MockGuard()
assert _app_main_guard.get_llm().name == "mock", "uji ini hanya boleh berjalan dengan provider mock"
_event_store_guard.EVENTS_DIR = _PathGuard(_tempfile_guard.mkdtemp(prefix="nvl-ev-"))
from domains.revenue.schema.artifact import DiagnosisArtifact  # noqa: E402
from domains.revenue.stages.journey import (  # noqa: E402
    compile_journey_context,
    demote_interventions,
    journey_prompt_block,
    prior_action_summary,
    reassess_status,
)
from store import nba as nba_store  # noqa: E402
from store.memory import store  # noqa: E402

client = TestClient(app)
failed = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global failed
    print(f"  {'PASS' if ok else 'FAIL'} {name}" + (f" | {detail}" if detail and not ok else ""))
    if not ok:
        failed += 1


def _artifact(level: str, cid: str = "C6.3", window: int = 14) -> DiagnosisArtifact:
    return DiagnosisArtifact.model_validate({
        "status": "provisional", "where_you_are": "x",
        "primary_constraint": "y", "primary_constraint_id": cid,
        "do_not": "n", "next_best_action": "a", "success_metric": "m",
        "well_know_when": "w", "pivot_rule": "p",
        "decision_spectrum": {"level": level},
        "reassess_window_days": window,
        "day_by_day": [
            {"day": 1, "text": "t1", "intervention_id": "TM-I03",
             "status": "DONE", "outcome": "not_moved"},
            {"day": 2, "text": "t2", "status": "TODO"},
        ],
    })


class _FakeSession:
    """Duck-typed — journey.py does not import store (layer contract)."""

    def __init__(self, diagnosis, created_ts, journey_delta=None):
        self.diagnosis = diagnosis
        self.created_ts = created_ts
        self.journey_delta = journey_delta


NOW = int(time.time())  # real time — reassess_status without now_ts uses time.time()

print("[J7-1] reassess_status — deterministik + degrade-aman", flush=True)
check("DUE: umur ≥ window",
      reassess_status(_FakeSession(_artifact("TEST_FIRST"), NOW - 20 * 86400), NOW)
      == {"status": "DUE", "window_days": 14, "age_days": 20})
check("NOT_YET: umur < window",
      reassess_status(_FakeSession(_artifact("TEST_FIRST"), NOW - 3 * 86400), NOW)
      == {"status": "NOT_YET", "window_days": 14, "age_days": 3})
check("UNKNOWN: created_ts kosong (sesi lama)",
      reassess_status(_FakeSession(_artifact("TEST_FIRST"), 0), NOW)["status"] == "UNKNOWN")
check("NO_PRIOR_DIAGNOSIS",
      reassess_status(_FakeSession(None, NOW), NOW)["status"] == "NO_PRIOR_DIAGNOSIS")

print("[J7-2] compile_journey_context + prompt block", flush=True)
ctx = compile_journey_context(
    _FakeSession(_artifact("TEST_FIRST"), NOW - 20 * 86400,
                 journey_delta={"verdict": "STUCK"}),
    user_outcomes={"TM-I03": {"not_moved": 2}, "CS-I01": {"moved": 1}},
)
check("verdict prior terbawa", ctx["prior"]["verdict"] == "STUCK")
check("reassess ikut terkompilasi", ctx["reassess"]["status"] == "DUE")
check("prior_actions terisi",
      ctx["prior_actions"]["by_outcome"] == {"not_moved": 1}
      and ctx["prior_actions"]["by_status"] == {"DONE": 1, "TODO": 1})
check("demote: hanya outcome buruk (moved TIDAK ikut)",
      set(ctx["demoted_interventions"]) == {"TM-I03"})
block = journey_prompt_block(ctx)
check("blok prompt memuat verdict + demote",
      "STUCK" in block and "TM-I03" in block and "do NOT" in block)
check("blok prompt ringkas (≤7 baris)", 0 < len(block.splitlines()) <= 7)
check("ctx None → blok kosong (degrade-aman)", journey_prompt_block(None) == "")

print("[J7-3] demote_interventions — pure", flush=True)
menu = [{"intervention_id": "TM-I03", "name": "a"},
        {"intervention_id": "CS-I01", "name": "b"},
        {"intervention_id": "", "name": "tanpa id"}]
kept, removed = demote_interventions(menu, {"TM-I03": "not_movedx2"})
check("yang didemote keluar", [i["intervention_id"] for i in removed] == ["TM-I03"])
check("sisanya dipertahankan (termasuk tanpa id)",
      [i["intervention_id"] for i in kept] == ["CS-I01", ""])

print("[J7-4] store — created_ts persist + sessions_by_user + outcomes", flush=True)
prior_s = store.create("j7 prior", "id", user_id="u-j7")
check("created_ts terisi saat create", prior_s.created_ts > 0)
prior_s.created_ts = NOW - 20 * 86400
prior_s.diagnosis = _artifact("TEST_FIRST")
store.save(prior_s)
reloaded = store.get(prior_s.id)
check("created_ts selamat persist", reloaded.created_ts == NOW - 20 * 86400)
check("prior_action_summary dari artifact asli",
      prior_action_summary(reloaded)["by_outcome"] == {"not_moved": 1})
by_user = store.sessions_by_user("u-j7")
check("sessions_by_user menemukan sesi user", any(x.id == prior_s.id for x in by_user))
check("sessions_by_user kosong tanpa user_id", store.sessions_by_user("") == [])

# outcome log: reporting via nba_store.record for this user's session
_tmp_log = nba_store._PATH
_backup = _tmp_log.read_text(encoding="utf-8") if _tmp_log.exists() else ""
try:
    nba_store.record(prior_s.id, "TM-I03", "not_moved")
    nba_store.record(prior_s.id, "TM-I03", "not_moved")
    nba_store.record(prior_s.id, "CS-I01", "confounded")  # excluded
    outs = nba_store.outcomes_by_intervention({prior_s.id, "sesi-lain"})
    check("outcomes_by_intervention: not_movedx2, confounded dikecualikan",
          outs == {"TM-I03": {"not_moved": 2}}, str(outs))

    print("[J7-5] GET /session/{sid}/journey — diperkaya (J7-a)", flush=True)
    cur = client.post("/session", json={"goal_text": "j7 cur", "user_id": "u-j7",
                                        "prior_session_id": prior_s.id}).json()
    cur_sid = cur["session_id"]
    cur_s = store.get(cur_sid)
    cur_s.diagnosis = _artifact("GO_SMALL", "C6.3")
    store.save(cur_s)
    r = client.get(f"/session/{cur_sid}/journey")
    check("200 journey", r.status_code == 200, str(r.status_code))
    j = r.json()
    check("verdict tetap hidup", j.get("verdict") == "ADVANCED", str(j))
    check("reassess DUE terekspos", j.get("reassess", {}).get("status") == "DUE", str(j))
    check("prior_actions terekspos",
          j.get("prior_actions", {}).get("by_outcome") == {"not_moved": 1}, str(j))

    print("[J7-6] _journey_context — wiring loop (deterministik, tanpa LLM)", flush=True)
    from app.main import _journey_context
    jc = _journey_context(cur_s)
    check("context terbangun untuk sesi ber-user", jc is not None)
    check("demote dari outcome log user",
          set((jc or {}).get("demoted_interventions", {})) == {"TM-I03"}, str(jc))
    check("ctx None tanpa prior",
          _journey_context(store.create("tanpa prior", "id")) is None)
finally:
    if _backup or _tmp_log.exists():
        _tmp_log.write_text(_backup, encoding="utf-8")
    for sid_ in (cur_sid if "cur_sid" in dir() else "", prior_s.id):
        if sid_:
            Path(store.PERSIST_DIR / f"{sid_}.json").unlink(missing_ok=True)

print()
print(f"HASIL: {'SEMUA LULUS ✅' if failed == 0 else f'{failed} GAGAL ❌'}")
raise SystemExit(0 if failed == 0 else 1)
