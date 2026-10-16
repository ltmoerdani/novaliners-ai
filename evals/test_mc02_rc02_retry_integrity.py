"""MC02-RC-02 — retry & replay integrity (RC-02 audit; int 19 §12.6).

What is tested: reasoning-only recovery is genuinely durable/idempotent on scenarios never
tested before — failure → retry → next turn, CONCURRENT retries, reload/restart, persistence
failure, retry after a newer user message, and the attempt audit trail. Invariants: a retry
must not add user events / claims / relations / evidence / Moves / Outcomes — only ONE new
engine reply.
"""
from __future__ import annotations

import atexit
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # mvp/

from evals._store_isolation import isolate_store  # noqa: E402

isolate_store()

import store.adjudication_ledger as ledger  # noqa: E402
import store.funnel as funnel  # noqa: E402
import store.path_states as path_states  # noqa: E402
import store.route_execution as route_execution  # noqa: E402
import store.route_lineages as rl  # noqa: E402
import store.workspace as workspace  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="mc02_rc02_"))
rl._BASE = _TMP / "lineages"
ledger._LEDGER_ROOT = _TMP / "ledger"
workspace._BASE = _TMP / "workspaces"
route_execution._BASE = _TMP / "workspaces"
funnel._PATH = _TMP / "funnel.jsonl"
path_states._BASE = _TMP
path_states._STATES = _TMP / "path_states.json"
path_states._HISTORY = _TMP / "path_history.jsonl"

from fastapi.testclient import TestClient  # noqa: E402

import app.main as app_main  # noqa: E402
import store.events as event_store  # noqa: E402
from providers.mock import MockProvider  # noqa: E402
from store.memory import store  # noqa: E402

_PASS, _FAIL = 0, 0


def check(name, ok, detail=""):
    global _PASS, _FAIL
    print(f"  {'OK ' if ok else 'XX '} {name}" + (f" | {detail}" if detail and not ok else ""))
    if ok:
        _PASS += 1
    else:
        _FAIL += 1


class FlakyMock(MockProvider):
    """The semantic observation always succeeds; the reasoner (nm.v2) can be told to fail."""

    name = "flaky-mock"
    fail_reasoner = False
    lock = threading.Lock()

    def structured_call(self, schema, system, user, retries=2):
        with FlakyMock.lock:
            fail = FlakyMock.fail_reasoner
        if fail and schema.__name__ == "NextMoveProposal":
            raise RuntimeError("[flaky] reasoner gagal (simulasi kegagalan provider)")
        return super().structured_call(schema, system, user, retries)


class ObserveBoom(MockProvider):
    """The UNDERSTANDING stage (so.v1) always fails after repair — simulating the P1 finding:
    the model keeps sending an invalid `role` so `structured_call` runs out of attempts."""

    name = "observe-boom"

    def structured_call(self, schema, system, user, retries=2):
        if schema.__name__ == "SemanticObservation":
            raise RuntimeError("[boom] MC01-M01@claims.0.role (repair habis)")
        return super().structured_call(schema, system, user, retries)


flaky = FlakyMock()
app_main.get_llm = lambda: flaky
assert app_main.get_llm().name == "flaky-mock"
# raise_server_exceptions=False: persistence failures are tested as honest HTTP statuses (500/503),
# not raised to the test client as a traceback.
client = TestClient(app_main.app, raise_server_exceptions=False)
_CREATED: list[str] = []
GOAL = "Saya punya usaha katering, mau Rp25 juta per bulan dalam 2 bulan."


def new_session(user: str) -> str:
    r = client.post("/session", json={"goal_text": GOAL, "language": "id", "user_id": user})
    assert r.status_code == 200, r.text
    sid = r.json()["session_id"]
    _CREATED.append(sid)
    return sid


def say(sid: str, text: str) -> dict:
    r = client.post(f"/session/{sid}/message", json={"text": text})
    assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
    return r.json()


def counts(sid: str) -> dict:
    s = store.get(sid)
    moves = list(getattr(s, "moves", None) or [])
    return {"user_events": sum(1 for e in s.events if e.get("role") == "user"),
            "engine_events": sum(1 for e in s.events if e.get("role") == "engine"),
            "claims": len((s.state_graph or {}).get("nodes") or {}),
            "evidence": len(s.evidence), "moves": len(moves),
            "outcomes": sum(1 for m in moves if m.get("lifecycle") == "OBSERVED"),
            "retry_entries": sum(1 for e in s.planner_log if e.get("reasoning_retry"))}


def r1_failure_retry_next_turn():
    print("R1 — failure → retry SEGERA → giliran berikutnya (invariant exactly-once)")
    sid = new_session("u-rc02-a")
    say(sid, "Omzet sekitar Rp12 juta per bulan dari tiga kantor langganan.")
    FlakyMock.fail_reasoner = True
    j = say(sid, "Ada 3-4 inquiry kantor, tapi saya jarang sempat membalas karena di dapur.")
    check("giliran DEGRADED terdeteksi", bool(j["next_move"].get("degraded")))
    before = counts(sid)
    FlakyMock.fail_reasoner = False
    rr = client.post(f"/session/{sid}/retry_reasoning", json={})
    after = counts(sid)
    check("retry SEGERA → 200 & tidak lagi degraded",
          rr.status_code == 200 and not rr.json()["next_move"].get("degraded"),
          f"{rr.status_code}")
    check("exactly-once: hanya +1 balasan engine; user-event/klaim/evidence/Move TIDAK berubah",
          after["engine_events"] == before["engine_events"] + 1
          and all(after[k] == before[k] for k in
                  ("user_events", "claims", "evidence", "moves", "outcomes")),
          f"{before} -> {after}")
    check("jejak audit: 1 entri reasoning_retry (attempt 2)", after["retry_entries"] == 1)
    j2 = say(sid, "Kira-kira satu dari inquiry itu yang jadi pelanggan.")
    check("giliran BERIKUTNYA berjalan normal setelah recovery",
          not j2["next_move"].get("degraded") and j2["next_move"].get("kind") in
          ("QUESTION", "EVIDENCE_REQUEST", "ACTION", "HOLD"))


def r2_concurrent_retry():
    print("R2 — retry KONKUREN (2 thread): tepat satu efek, tanpa duplikasi")
    sid = new_session("u-rc02-b")
    say(sid, "Harga katering Rp35 ribu per box.")
    FlakyMock.fail_reasoner = True
    say(sid, "Saya takut kehilangan kantor terbesar.")
    FlakyMock.fail_reasoner = False
    before = counts(sid)
    with ThreadPoolExecutor(max_workers=2) as ex:
        res = list(ex.map(lambda _: client.post(f"/session/{sid}/retry_reasoning", json={}).status_code,
                          range(2)))
    after = counts(sid)
    check("status: satu 200, satu 409 (serialisasi per sesi)",
          sorted(res) == [200, 409], res)
    check("tidak ada duplikasi: +1 engine balasan saja, +1 entri retry",
          after["engine_events"] == before["engine_events"] + 1
          and after["retry_entries"] == before["retry_entries"] + 1
          and all(after[k] == before[k] for k in ("user_events", "claims", "evidence", "moves")),
          f"{before} -> {after} status={res}")


def r3_reload_durability():
    print("R3 — reload/restart: jejak retry & hasil pulih dari store (durable)")
    sid = new_session("u-rc02-c")
    say(sid, "Saya masak sendiri, dua karyawan paruh waktu.")
    FlakyMock.fail_reasoner = True
    say(sid, "Iklan Instagram pernah dicoba dua bulan, hasilnya tidak dicatat.")
    FlakyMock.fail_reasoner = False
    assert client.post(f"/session/{sid}/retry_reasoning", json={}).status_code == 200
    fresh = store.get(sid)          # fresh read from the store (reload simulation)
    retry_entries = [e for e in fresh.planner_log if e.get("reasoning_retry")]
    last_user = next(e for e in reversed(fresh.events) if e.get("role") == "user")
    latest = event_store.find_engine_event(fresh, last_user["event_id"], latest=True)
    check("planner_log retry bertahan setelah reload (attempt=2)",
          len(retry_entries) == 1 and retry_entries[0].get("reasoning_retry_attempt") == 2,
          str(retry_entries)[:160])
    check("sesi tetap konsisten: retry kedua ditolak jujur (bukan efek ganda)",
          client.post(f"/session/{sid}/retry_reasoning", json={}).status_code == 409
          and latest is not None and (latest.get("result") or {}).get("next_move") is not None,
          f"latest={bool(latest)}")


def r4_persistence_failure():
    print("R4 — kegagalan PERSISTENCE saat retry: terlihat jujur, tanpa efek ganda")
    sid = new_session("u-rc02-d")
    say(sid, "Pelanggan terbesar sebuah kantor, 15 box tiap Jumat.")
    FlakyMock.fail_reasoner = True
    say(sid, "Data pelanggan cuma di WhatsApp pribadi.")
    FlakyMock.fail_reasoner = False
    before = counts(sid)
    real_save = store.save_strict
    boom = {"n": 0}

    def _failing_save(sess):
        boom["n"] += 1
        raise event_store.SessionPersistenceError("simulasi disk penuh")

    store.save_strict = _failing_save
    try:
        r = client.post(f"/session/{sid}/retry_reasoning", json={})
        status = r.status_code
        after_fail = counts(sid)
        ev_status = next(e.get("status") for e in reversed(store.get(sid).events)
                         if e.get("role") == "user")
    finally:
        store.save_strict = real_save
    check("kegagalan persistence TIDAK dilaporkan sebagai sukses (status >= 500)",
          status >= 500, status)
    check("event user yang SUDAH committed tetap durable (retry gagal tidak merusak observasi)",
          ev_status == event_store.STATUS_COMMITTED, ev_status)
    check("tidak ada duplikasi klaim/evidence/Move; user-event tidak bertambah",
          all(after_fail[k] == before[k] for k in ("user_events", "claims", "evidence", "moves")),
          f"{before} -> {after_fail}")
    r2 = client.post(f"/session/{sid}/retry_reasoning", json={})
    after_ok = counts(sid)
    check("setelah persistence sehat: tidak ada duplikasi user-event/klaim (200 atau 409 jujur)",
          r2.status_code in (200, 409)
          and after_ok["user_events"] == before["user_events"]
          and after_ok["claims"] == before["claims"],
          f"{r2.status_code} {after_ok}")


def r5_retry_after_newer_message():
    print("R5 — pesan user lebih baru di antara attempt → retry lama ditolak (stale reasoning)")
    sid = new_session("u-rc02-e")
    say(sid, "Omzet 22 juta sebulan.")
    FlakyMock.fail_reasoner = True
    say(sid, "Saya kepikiran pasang iklan Rp5 juta.")
    ev_stale = [e for e in store.get(sid).events if e.get("role") == "user"][-1]["event_id"]
    FlakyMock.fail_reasoner = False
    say(sid, "Tapi sebenarnya saya lebih suka pelanggan langganan.")
    r = client.post(f"/session/{sid}/retry_reasoning", json={"event_id": ev_stale})
    check("409 SUPERSEDED untuk event degraded yang sudah terlampaui",
          r.status_code == 409 and "SUPERSEDED" in r.text, f"{r.status_code} {r.text[:120]}")
    check("percakapan tetap berjalan dari pesan terbaru (pesan terakhir tidak degraded)",
          store.get(sid).planner_log[-1]["adaptive"]["status"] != "DEGRADED")
    check("retry default menargetkan event TERBARU (bukan yang basi)",
          counts(sid)["retry_entries"] == 0)


def r6_audit_trail_multi_attempt():
    print("R6 — beberapa attempt pada event yang sama: gagal → gagal → sukses (jejak append-only)")
    sid = new_session("u-rc02-f")
    say(sid, "Margin kira-kira 20 persen, tapi tidak yakin.")
    FlakyMock.fail_reasoner = True
    say(sid, "Ralat, pelanggan terbesar itu 12 box, bukan 15.")
    a = client.post(f"/session/{sid}/retry_reasoning", json={})   # attempt 2: provider still fails
    b = client.post(f"/session/{sid}/retry_reasoning", json={})   # attempt 3: provider still fails
    FlakyMock.fail_reasoner = False
    c = client.post(f"/session/{sid}/retry_reasoning", json={})   # attempt 4: recovered
    entries = [e for e in store.get(sid).planner_log if e.get("reasoning_retry")]
    check("attempt yang MASIH gagal jujur (200 + degraded), lalu attempt sehat pulih",
          a.status_code == 200 and bool(a.json()["next_move"].get("degraded"))
          and b.status_code == 200 and bool(b.json()["next_move"].get("degraded"))
          and c.status_code == 200 and not c.json()["next_move"].get("degraded"),
          f"{a.status_code}/{b.status_code}/{c.status_code}")
    check("jejak append-only mencatat attempt berurutan (2,3,4) pada event yang SAMA",
          [e.get("reasoning_retry_attempt") for e in entries] == [2, 3, 4]
          and len({e.get("event_id") for e in entries}) == 1,
          str([e.get("reasoning_retry_attempt") for e in entries]))
    check("tidak ada duplikasi sepanjang 3 attempt beruntun",
          counts(sid)["user_events"] == 3 and counts(sid)["retry_entries"] == 3)


def r7_understanding_failure_is_degraded_not_500():
    print("R7 — kegagalan PEMAHAMAN = giliran DEGRADED jujur (bukan 500); event tetap tersimpan")
    sid = new_session("u-rc02-g")
    say(sid, "Omzet sekitar Rp12 juta per bulan dari tiga kantor langganan.")
    before = counts(sid)
    app_main.get_llm = lambda: ObserveBoom()
    try:
        r = client.post(f"/session/{sid}/message", json={"text": "Pesan yang gagal dibaca."})
    finally:
        app_main.get_llm = lambda: flaky
    after = counts(sid)
    j = r.json() if r.status_code == 200 else {}
    nm = j.get("next_move") or {}
    ev = next(e.get("status") for e in reversed(store.get(sid).events) if e.get("role") == "user")
    check("HTTP 200 dengan giliran DEGRADED (BUKAN 500)",
          r.status_code == 200 and nm.get("degraded") is True, f"{r.status_code} {r.text[:120]}")
    check("kode stabil UNDERSTANDING_FAILED + headline teknis (bukan HOLD bisnis)",
          nm.get("error_code") == "UNDERSTANDING_FAILED" and nm.get("headline") == "Jeda teknis"
          and nm.get("kind") == "HOLD", f"{nm.get('error_code')}/{nm.get('headline')}")
    check("pesan user tetap tersimpan sebagai understanding_failed; TIDAK ada klaim dikarang",
          ev == event_store.STATUS_UNDERSTANDING_FAILED and after["claims"] == before["claims"],
          f"{ev} claims {before['claims']}->{after['claims']}")
    check("teks jujur: menyatakan pesan tersimpan & minta kirim ulang intinya",
          "tersimpan" in (nm.get("text") or ""), (nm.get("text") or "")[:80])
    rr = client.post(f"/session/{sid}/retry_reasoning", json={})
    check("retry reasoning DITOLAK jujur (pemahaman belum selesai → kirim ulang pesan)",
          rr.status_code == 409 and ("NO_COMMITTED_EVENT" in rr.text or "EVENT_NOT_COMMITTED" in rr.text)
          and "/message" in rr.text, f"{rr.status_code} {rr.text[:120]}")
    j2 = say(sid, "Omzet saya 12 juta sebulan dari tiga kantor.")
    check("percakapan pulih di giliran berikutnya (tidak terkunci)",
          not (j2.get("next_move") or {}).get("degraded"))


def main() -> int:
    r1_failure_retry_next_turn()
    r2_concurrent_retry()
    r3_reload_durability()
    r4_persistence_failure()
    r5_retry_after_newer_message()
    r6_audit_trail_multi_attempt()
    r7_understanding_failure_is_degraded_not_500()
    print(f"\n{'=' * 62}\nMC02-RC-02 retry & replay integrity: {_PASS} OK, {_FAIL} GAGAL")
    return 1 if _FAIL else 0


@atexit.register
def _cleanup():
    for sid in _CREATED:
        try:
            store.sessions.pop(sid, None)
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    sys.exit(main())
