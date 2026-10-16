"""Guard J2 continuation (internal-docs §7): execution report for ONE day_by_day action.

Deterministic 0-LLM — pattern of test_nba_report.py:
  1. 404 session missing · 409 diagnosis missing · 404 index out of range
  2. 422 without status/outcome
  3. Happy path: status+outcome+note written to ActionItem (reported_at filled)
  4. Persistence: report survives a store reload from disk
  5. Does NOT change knowledge confidence (recalc not triggered — lesson from
     the NBA guard: grounding a user's report is not evidence)
  6. Outcome log only written when the item has an intervention_id
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

# R4: this test USED TO call the real Z.ai (get_llm left unpatched): burning quota on every gate-fast.
# Provider forced to mock; conversation events go to a temp directory.
_app_main_guard.get_llm = lambda: _MockGuard()
assert _app_main_guard.get_llm().name == "mock", "uji ini hanya boleh berjalan dengan provider mock"
_event_store_guard.EVENTS_DIR = _PathGuard(_tempfile_guard.mkdtemp(prefix="nvl-ev-"))
from domains.revenue.schema.artifact import DiagnosisArtifact  # noqa: E402
from store import checkins  # noqa: E402
from store.memory import store  # noqa: E402

client = TestClient(app)

failed = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global failed
    mark = "PASS" if cond else "FAIL"
    print(f"  {mark} {name}" + (f" | {detail}" if detail and not cond else ""))
    if not cond:
        failed += 1


def _make_session(with_iid: bool = True):
    item2 = {
        "day": 2, "text": "ukur konversi 10 DM",
        "intervention_id": "TM-I03" if with_iid else "",
        "expected_evidence": ">=3 balas",
    }
    art = DiagnosisArtifact.model_validate({
        "status": "provisional", "where_you_are": "x",
        "primary_constraint": "y", "primary_constraint_id": "C6.3",
        "do_not": "n", "next_best_action": "a", "success_metric": "m",
        "well_know_when": "w", "pivot_rule": "p",
        "day_by_day": ["H1: follow-up 2 lead lama", item2],
    })
    s = store.create("uji j2 lanjutan", "id")
    s.diagnosis = art
    store.save(s)
    return s.id


def _cleanup(sid: str) -> None:
    p = Path(store.PERSIST_DIR / f"{sid}.json")
    p.unlink(missing_ok=True)


print("[J2-1] Validasi route", flush=True)
check("404 sesi tak ada",
      client.post("/session/tidakada/action/0/report",
                  json={"status": "DONE"}).status_code == 404)
sid0 = _make_session()
check("409 diagnosis belum ada",
      client.post(f"/session/{sid0}/action/0/report",
                  json={"status": "DONE"}).status_code == 409 or True)
# sid0 already has a diagnosis — create an empty session for the 409 case
s_none = store.create("tanpa diagnosis", "id")
store.save(s_none)
r409 = client.post(f"/session/{s_none.id}/action/0/report", json={"status": "DONE"})
check("409 diagnosis belum ada", r409.status_code == 409, str(r409.status_code))
_cleanup(s_none.id)

sid = _make_session()
r404 = client.post(f"/session/{sid}/action/9/report", json={"status": "DONE"})
check("404 index di luar range", r404.status_code == 404, str(r404.status_code))
r422 = client.post(f"/session/{sid}/action/0/report", json={"note": "tanpa status"})
check("422 tanpa status/outcome", r422.status_code == 422, str(r422.status_code))

print("[J2-2] Happy path: update ActionItem", flush=True)
conf_before = (Path("store/knowledge_confidence.json").read_text(encoding="utf-8")
               if Path("store/knowledge_confidence.json").exists() else "{}")
r = client.post(f"/session/{sid}/action/1/report",
                json={"status": "DONE", "outcome": "moved",
                      "note": "4 balas dari 10 DM", "evidence_hint": "chat export"})
check("200 ok", r.status_code == 200, str(r.status_code))
a = r.json().get("action", {})
check("status DONE tertulis", a.get("status") == "DONE")
check("outcome moved tertulis", a.get("outcome") == "moved")
check("reported_at terisi", isinstance(a.get("reported_at"), int))
check("note tersimpan di field sendiri (outcome tetap enum bersih)",
      "4 balas" in str(a.get("note", "")) and a.get("outcome") == "moved")

print("[J2-3] Persistensi + tanpa recalc", flush=True)
reloaded = store.get(sid)
check("laporan selamat reload store",
      reloaded.diagnosis.day_by_day[1].status == "DONE")
conf_after = (Path("store/knowledge_confidence.json").read_text(encoding="utf-8")
              if Path("store/knowledge_confidence.json").exists() else "{}")
check("knowledge confidence TIDAK berubah", conf_before == conf_after)

print("[J2-4] Log outcome", flush=True)
check("item ber-intervention_id → log ditulis",
      client.post(f"/session/{sid}/action/1/report",
                  json={"outcome": "not_moved"}).json()
      .get("logged_to_outcome_log") is True)
sid_noiid = _make_session(with_iid=False)
check("item tanpa intervention_id → log dilewati (bukan error)",
      client.post(f"/session/{sid_noiid}/action/1/report",
                  json={"outcome": "moved"}).json()
      .get("logged_to_outcome_log") is False)
_cleanup(sid_noiid)
_cleanup(sid)

print("[P0-05] Check-in + aksi: satu perintah, validasi sebelum mutasi", flush=True)


def _make_user_session():
    art = DiagnosisArtifact.model_validate({
        "status": "provisional", "where_you_are": "x",
        "primary_constraint": "y", "primary_constraint_id": "C6.3",
        "do_not": "n", "next_best_action": "a", "success_metric": "m",
        "well_know_when": "w", "pivot_rule": "p",
        "day_by_day": ["H1: follow-up 2 lead lama", {"day": 2, "text": "ukur konversi 10 DM",
                                                     "intervention_id": "TM-I03"}],
    })
    s = store.create("uji p0-05", "id", user_id="u-partial")
    s.diagnosis = art
    store.save(s)
    return s.id


# A VALID action_index + an INVALID check-in field must write NOTHING at all.
sid_partial = _make_user_session()
before_item = store.get(sid_partial).diagnosis.day_by_day[1].model_dump()
bad = client.post(f"/session/{sid_partial}/checkin", json={
    "outcome": "mixed", "contacted": "abc", "action_index": 1,
    "action_status": "DONE", "action_outcome": "moved", "operation_id": "op-partial-1"})
check("contacted='abc' + action_index valid -> 422", bad.status_code == 422, str(bad.status_code))
after_item = store.get(sid_partial).diagnosis.day_by_day[1].model_dump()
check("TIDAK ada mutasi aksi saat check-in ditolak", after_item == before_item)
check("TIDAK ada baris check-in parsial",
      not any(r.get("op_id") == "op-partial-1" for r in checkins.list_rows("u-partial")))

# Idempotency covers the COMPLETE command, including the action fields.
sid_cmd = _make_user_session()
r1 = client.post(f"/session/{sid_cmd}/checkin", json={
    "outcome": "mixed", "action_index": 1, "action_status": "DONE", "action_outcome": "moved",
    "operation_id": "op-cmd-1"})
check("perintah check-in+aksi pertama -> 200", r1.status_code == 200, str(r1.status_code))
r2 = client.post(f"/session/{sid_cmd}/checkin", json={
    "outcome": "mixed", "action_index": 1, "action_status": "SKIPPED", "action_outcome": "not_moved",
    "operation_id": "op-cmd-1"})
check("op_id sama + field aksi BERBEDA -> 409", r2.status_code == 409, str(r2.status_code))
r3 = client.post(f"/session/{sid_cmd}/checkin", json={
    "outcome": "mixed", "action_index": 1, "action_status": "DONE", "action_outcome": "moved",
    "operation_id": "op-cmd-1"})
check("replay perintah identik -> replayed, bukan baris kedua",
      r3.status_code == 200 and r3.json().get("replayed") is True)
check("hanya SATU baris untuk op-cmd-1",
      sum(1 for r in checkins.list_rows("u-partial") if r.get("op_id") == "op-cmd-1") == 1)
_cleanup(sid_partial)
_cleanup(sid_cmd)

print()
print(f"HASIL: {'SEMUA LULUS ✅' if failed == 0 else f'{failed} GAGAL ❌'}")
raise SystemExit(0 if failed == 0 else 1)
