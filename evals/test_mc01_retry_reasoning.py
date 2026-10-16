"""MC01-2 — REASONING-ONLY recovery (CIR-MC01 audit P0-B; int 19 §12.6).

Contract: committed observation → reasoning failed → retry reasoning on the existing State.
Invariants tested: no second user event for the same message, no semantic re-observation
(claims/evidence unchanged), no duplicate Move, the attempt recorded append-only in
planner_log, and idempotent recovery returning the LATEST result.
"""
from __future__ import annotations

import atexit
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # mvp/

from evals._store_isolation import isolate_store  # noqa: E402

isolate_store()  # eval: store redirected to tmp — production store untouched

import store.adjudication_ledger as ledger  # noqa: E402
import store.funnel as funnel  # noqa: E402
import store.path_states as path_states  # noqa: E402
import store.route_execution as route_execution  # noqa: E402
import store.route_lineages as rl  # noqa: E402
import store.workspace as workspace  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="mc01_retry_"))
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
from providers.mock import MockProvider  # noqa: E402
from store.memory import store  # noqa: E402

_PASS, _FAIL = 0, 0


def check(name, ok, detail=""):
    global _PASS, _FAIL
    print(f"  {'✅' if ok else '❌'} {name}" + (f" | {detail}" if detail and not ok else ""), flush=True)
    if ok:
        _PASS += 1
    else:
        _FAIL += 1


class FlakyMock(MockProvider):
    """Deterministic mock that can be told to FAIL only at the reasoner stage (nm.v2) —
    the semantic observation (so.v1) still succeeds, simulating exactly P0-B:
    committed observation → reasoning failed."""

    name = "flaky-mock"
    fail_reasoner = False

    def structured_call(self, schema, system, user, retries=2):
        if self.fail_reasoner and schema.__name__ == "NextMoveProposal":
            raise RuntimeError("[flaky] reasoner gagal (simulasi kegagalan provider)")
        return super().structured_call(schema, system, user, retries)


flaky = FlakyMock()
app_main.get_llm = lambda: flaky  # deterministic: does NOT use the real provider from .env
assert app_main.get_llm().name == "flaky-mock", "uji ini hanya boleh berjalan dengan provider mock"
client = TestClient(app_main.app)

_CREATED: list[str] = []
GOAL = ("Saya punya usaha katering, mau Rp25 juta per bulan "
        "dalam 2 bulan.")


def new_session(user: str, goal: str = GOAL, lang: str = "id") -> str:
    r = client.post("/session", json={"goal_text": goal, "language": lang, "user_id": user})
    assert r.status_code == 200, r.text
    sid = r.json()["session_id"]
    _CREATED.append(sid)
    return sid


def say(sid: str, text: str, key: str = "") -> dict:
    body = {"text": text}
    if key:
        body["idempotency_key"] = key
    r = client.post(f"/session/{sid}/message", json=body)
    assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
    return r.json()


def counts(sid: str) -> dict:
    s = store.get(sid)
    return {
        "user_events": sum(1 for e in s.events if e.get("role") == "user"),
        "engine_events": sum(1 for e in s.events if e.get("role") == "engine"),
        "evidence": len(s.evidence),
        "claims": len((s.state_graph or {}).get("nodes") or {}),
        "moves": len(getattr(s, "moves", None) or []),
        "planner_log": len(s.planner_log),
        "transcript_engine": sum(1 for r, _ in s.transcript if r == "engine"),
    }


def s1_retry_recovers_without_duplicates():
    print("S1 — giliran DEGRADED dipulihkan TANPA event/evidence/klaim/Move duplikat")
    sid = new_session("u-mc01-a")
    say(sid, "Usaha katering saya omzetnya sekitar Rp12 juta per bulan dari 3 kantor langganan.")
    flaky.fail_reasoner = True
    j_bad = say(sid, "Ada sekitar 3-4 inquiry kantor masuk bulan-bulan ini, biasanya saya balas telat "
                     "karena sibuk di dapur.", key="k-s1")
    check("giliran terakhir DEGRADED (observasi tetap tersimpan)", bool(j_bad["next_move"].get("degraded")))
    before = counts(sid)
    flaky.fail_reasoner = False
    r = client.post(f"/session/{sid}/retry_reasoning", json={})
    check("retry reasoning → 200", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
    j = r.json()
    s = store.get(sid)
    after = counts(sid)
    check("TIDAK ada event user baru / re-observasi (claims+evidence identik)",
          after["user_events"] == before["user_events"]
          and after["evidence"] == before["evidence"]
          and after["claims"] == before["claims"],
          f"{before} -> {after}")
    check("balasan engine baru + langkah tidak lagi degraded",
          after["engine_events"] == before["engine_events"] + 1
          and not bool((j.get("next_move") or {}).get("degraded")),
          f"eng {before['engine_events']}->{after['engine_events']} "
          f"degraded={(j.get('next_move') or {}).get('degraded')}")
    check("Move tidak terduplikasi oleh retry",
          after["moves"] == before["moves"] + (1 if (j["next_move"].get("kind") == "ACTION") else 0),
          f"moves {before['moves']}->{after['moves']} kind={j['next_move'].get('kind')}")
    retry_entries = [e for e in s.planner_log if e.get("reasoning_retry")]
    check("attempt retry tercatat append-only di planner_log (event_id sama)",
          len(retry_entries) == 1 and retry_entries[0].get("reasoning_retry_attempt") == 2
          and retry_entries[0].get("event_id") == [e for e in s.events
                                                   if e.get("role") == "user"][-1]["event_id"])
    return sid, "k-s1"


def s2_not_degraded_refused():
    print("S2 — sesi sehat (tanpa DEGRADED) menolak retry dengan 409")
    sid = new_session("u-mc01-b")
    say(sid, "Jasa saya Rp3 juta per klien, sekarang ada 2 klien aktif.")
    r = client.post(f"/session/{sid}/retry_reasoning", json={})
    check("409 NOT_DEGRADED untuk giliran sehat", r.status_code == 409 and "NOT_DEGRADED" in r.text,
          f"{r.status_code} {r.text[:160]}")


def s3_superseded_refused(sid_a: str):
    print("S3 — pesan user lebih baru menggantikan retry lama (409 SUPERSEDED)")
    flaky.fail_reasoner = True
    say(sid_a, "Kompetitor saya viral di TikTok, jadi saya berpikir harus pasang iklan Rp5 juta.")
    flaky.fail_reasoner = False
    degraded_ev = [e for e in store.get(sid_a).events if e.get("role") == "user"][-1]["event_id"]
    say(sid_a, "Iklan masih rencana, belum jalan.")     # newer message: conversation moved on
    r = client.post(f"/session/{sid_a}/retry_reasoning", json={"event_id": degraded_ev})
    check("409 SUPERSEDED untuk event_id degraded yang sudah terlampaui pesan baru",
          r.status_code == 409 and "SUPERSEDED" in r.text, f"{r.status_code} {r.text[:160]}")
    r_default = client.post(f"/session/{sid_a}/retry_reasoning", json={})
    check("target default = event terbaru (sehat) → 409 NOT_DEGRADED, bukan retry lama",
          r_default.status_code == 409 and "NOT_DEGRADED" in r_default.text,
          f"{r_default.status_code} {r_default.text[:160]}")


def s4_double_retry_refused(sid_a: str):
    print("S4 — retry kedua setelah pemulihan sukses ditolak (bukan efek ganda)")
    flaky.fail_reasoner = True
    say(sid_a, "Data pelanggan saya cuma di WhatsApp pribadi, tidak pernah dicatat.")
    flaky.fail_reasoner = False
    r1 = client.post(f"/session/{sid_a}/retry_reasoning", json={})
    r2 = client.post(f"/session/{sid_a}/retry_reasoning", json={})
    check("retry pertama 200, retry kedua 409 NOT_DEGRADED",
          r1.status_code == 200 and r2.status_code == 409 and "NOT_DEGRADED" in r2.text,
          f"{r1.status_code}/{r2.status_code} {r2.text[:120]}")


def s5_idempotent_resend_recovers_latest(sid_a: str):
    print("S5 — kirim ulang idempoten pasca-retry memulihkan hasil TERBARU (bukan balasan degraded)")
    flaky.fail_reasoner = True
    key = "k-s5"
    j_bad = say(sid_a, "Dari inquiry itu kira-kira satu saja yang jadi pelanggan.", key=key)
    check("giliran degraded sebelum pemulihan", bool(j_bad["next_move"].get("degraded")))
    flaky.fail_reasoner = False
    r = client.post(f"/session/{sid_a}/retry_reasoning", json={})
    assert r.status_code == 200, r.text
    before = counts(sid_a)
    j2 = say(sid_a, "Dari inquiry itu kira-kira satu saja yang jadi pelanggan.", key=key)
    after = counts(sid_a)
    check("resend kunci sama → hasil TERBARU (tidak degraded), tanpa efek samping baru",
          not bool(j2["next_move"].get("degraded"))
          and after["user_events"] == before["user_events"]
          and after["engine_events"] == before["engine_events"]
          and after["claims"] == before["claims"],
          f"degraded={j2['next_move'].get('degraded')} {before}->{after}")


def s6_retry_durable_and_event_targeting():
    print("S6 — retry bertahan di sesi (reload) dan event_id eksplisit bekerja")
    sid = new_session("u-mc01-c")
    say(sid, "Saya freelancer desain, penghasilan sekitar Rp6 juta per bulan.")
    flaky.fail_reasoner = True
    say(sid, "Waktu kerja saya maksimal 4 jam sehari.")
    flaky.fail_reasoner = False
    r = client.post(f"/session/{sid}/retry_reasoning", json={})
    assert r.status_code == 200, r.text
    target = [e for e in store.get(sid).events if e.get("role") == "user"][-1]["event_id"]
    r_by_id = client.post(f"/session/{sid}/retry_reasoning", json={"event_id": target})
    check("reload dari store: planner_log retry tetap ada; event_id eksplisit ditolak jujur "
          "setelah pemulihan (409 NOT_DEGRADED)",
          any(e.get("reasoning_retry") for e in store.get(sid).planner_log)
          and r_by_id.status_code == 409 and "NOT_DEGRADED" in r_by_id.text,
          f"{r_by_id.status_code} {r_by_id.text[:120]}")
    r404 = client.post(f"/session/{sid}/retry_reasoning", json={"event_id": "ev-tidak-ada"})
    check("event_id tak dikenal → 409 EVENT_NOT_FOUND", r404.status_code == 409
          and "EVENT_NOT_FOUND" in r404.text, f"{r404.status_code}")


def main() -> int:
    sid_a, _ = s1_retry_recovers_without_duplicates()
    s2_not_degraded_refused()
    s3_superseded_refused(sid_a)
    s4_double_retry_refused(sid_a)
    s5_idempotent_resend_recovers_latest(sid_a)
    s6_retry_durable_and_event_targeting()
    print(f"\n{'=' * 62}\nMC01-2 reasoning-only recovery: {_PASS} OK, {_FAIL} GAGAL")
    return 1 if _FAIL else 0


@atexit.register
def _cleanup():
    for sid in _CREATED:
        try:
            store.delete(sid)
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    sys.exit(main())
