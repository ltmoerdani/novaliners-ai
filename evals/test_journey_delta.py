"""Guard J3 (internal-docs §7) — cross-session identity & delta, deterministic 0-LLM.

  1. compute_delta: ADVANCED / REGRESSED / STUCK / PIVOTED / INSUFFICIENT_DATA
  2. CreateSession accepts user_id/prior_session_id; 404 when the prior is not found
  3. Persistence: user_id/prior_session_id survive a store reload
  4. GET /session/{sid}/journey: verdict from the linked session; 409 without linkage
"""
from __future__ import annotations

import sys
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
from domains.revenue.stages.journey import compute_delta  # noqa: E402
from store.memory import store  # noqa: E402

client = TestClient(app)
failed = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global failed
    print(f"  {'PASS' if ok else 'FAIL'} {name}" + (f" | {detail}" if detail and not ok else ""))
    if not ok:
        failed += 1


def _artifact(level: str, cid: str = "C6.3") -> DiagnosisArtifact:
    return DiagnosisArtifact.model_validate({
        "status": "provisional", "where_you_are": "x",
        "primary_constraint": "y", "primary_constraint_id": cid,
        "do_not": "n", "next_best_action": "a", "success_metric": "m",
        "well_know_when": "w", "pivot_rule": "p",
        "decision_spectrum": {"level": level},
    })


print("[J3-1] compute_delta — verdict deterministik", flush=True)
check("ADVANCED: TEST_FIRST → GO_SMALL",
      compute_delta(_artifact("TEST_FIRST"), _artifact("GO_SMALL"))["verdict"] == "ADVANCED")
check("REGRESSED: PROCEED → NOT_YET",
      compute_delta(_artifact("PROCEED"), _artifact("NOT_YET"))["verdict"] == "REGRESSED")
check("STUCK: level sama + constraint sama",
      compute_delta(_artifact("TEST_FIRST"), _artifact("TEST_FIRST"))["verdict"] == "STUCK")
check("PIVOTED: level sama + constraint beda",
      compute_delta(_artifact("TEST_FIRST"), _artifact("TEST_FIRST", "DM5.1"))["verdict"] == "PIVOTED")
check("INSUFFICIENT_DATA: level tak dikenal",
      compute_delta(_artifact("TEST_FIRST"), _artifact(""))["verdict"] == "INSUFFICIENT_DATA")
check("spectrum_moved terisi",
      compute_delta(_artifact("STOP"), _artifact("PROCEED"))["spectrum_moved"] == 4)

print("[J3-2] CreateSession + prior validation", flush=True)
r = client.post("/session", json={"goal_text": "uji j3", "user_id": "u-1",
                                  "prior_session_id": "tidakada"})
check("404 prior_session tak ditemukan", r.status_code == 404, str(r.status_code))
r = client.post("/session", json={"goal_text": "uji j3", "user_id": "u-1"})
sid = r.json()["session_id"]
check("200 create tanpa prior (backward compatible)", r.status_code == 200)
s = store.get(sid)
check("user_id tersimpan", s.user_id == "u-1")
check("reload store: user_id selamat", store.get(sid).user_id == "u-1")

print("[J3-3] GET /session/{sid}/journey", flush=True)
prior_sid = _make = None
r409 = client.get(f"/session/{sid}/journey")
check("409 sesi tanpa linkage+diagnosis", r409.status_code == 409, str(r409.status_code))

# Seed two fully linked sessions with diagnoses (skip LLM)
prior_s = store.create("prior", "id")
prior_s.diagnosis = _artifact("TEST_FIRST", "C6.3")
store.save(prior_s)
cur = client.post("/session", json={"goal_text": "current", "user_id": "u-1",
                                    "prior_session_id": prior_s.id}).json()
cur_sid = cur["session_id"]
cur_s = store.get(cur_sid)
cur_s.diagnosis = _artifact("GO_SMALL", "C6.3")
store.save(cur_s)

r = client.get(f"/session/{cur_sid}/journey")
check("200 journey", r.status_code == 200, str(r.status_code))
j = r.json()
check("verdict ADVANCED (TEST_FIRST → GO_SMALL)", j.get("verdict") == "ADVANCED", str(j))
check("prior_session_id tercatat", j.get("prior_session_id") == prior_s.id)
check("delta ter-persist di session",
      (store.get(cur_sid).journey_delta or {}).get("verdict") == "ADVANCED")

for sid_ in (sid, cur_sid, prior_s.id):
    p = Path(store.PERSIST_DIR / f"{sid_}.json")
    p.unlink(missing_ok=True)

print()
print(f"HASIL: {'SEMUA LULUS ✅' if failed == 0 else f'{failed} GAGAL ❌'}")
raise SystemExit(0 if failed == 0 else 1)
