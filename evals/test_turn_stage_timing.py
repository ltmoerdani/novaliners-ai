"""S1 — per-stage turn telemetry: complete, inclusive/exclusive correct, and NON-INTERFERING.

Contract proven (audit int 20 §S1; int 16 latency-economics units):
  T1  the first /session turn uses the same spans (semantic/persist/navigation/reasoner +
      session_init_s) — not just /message.
  T2  /message records semantic_s, navigation_s, reasoner_s, total_s, persist_s, request_total_s.
  T3  spans consistent: request_total_s >= total_s; navigation_s + reasoner_s <= reason_s (inclusive);
      second_pass_s (if present) NESTED inside navigation_s.
  T4  NON-INTERFERING: running a turn with a constant perf_counter (all spans zero) yields
      decisions + canonical evidence IDENTICAL to a normal turn — instrumentation does not change
      inference semantics.
  T5  replay stays valid after timing was added (timing does not change input/decision).

Provider = deterministic mock (no LLM, no quota). Run:
  .venv/bin/python evals/test_turn_stage_timing.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # mvp/

from evals._store_isolation import isolate_store  # noqa: E402

isolate_store()

import time as _time  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

import app.main as app_main  # noqa: E402
from core.navigation.planner import replay  # noqa: E402
from providers.mock import MockProvider  # noqa: E402
from store.memory import store  # noqa: E402

app_main.get_llm = lambda: MockProvider()  # deterministic: the live key in .env is NOT used
assert app_main.get_llm().name == "mock", "uji ini hanya boleh berjalan dengan provider mock"
client = TestClient(app_main.app)

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(ok), detail))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" | {detail}" if detail and not ok else ""), flush=True)


GOAL = "Saya konsultan marketing, mau Rp20 juta per bulan dalam 90 hari."
STORY = "Pendapatan saya sekarang Rp8 juta per bulan dari 2 klien aktif, harga Rp3 juta per klien."
MSG = "Ada 3 orang yang bertanya soal jasa saya bulan ini."


def new_session(user: str) -> str:
    r = client.post("/session", json={"goal_text": GOAL, "language": "en", "user_id": user,
                                      "desire": STORY})
    assert r.status_code == 200, r.text
    return r.json()["session_id"]


def say(sid: str, text: str) -> dict:
    r = client.post(f"/session/{sid}/message", json={"text": text})
    assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
    return r.json()


def last_entry(sid: str) -> dict:
    s = store.get(sid)
    assert s is not None and s.planner_log, "planner_log kosong"
    return s.planner_log[-1]


def is_num(x) -> bool:
    return isinstance(x, (int, float)) and x >= 0


# ── T1/T2 · stage spans exist on /session and /message ──────────────────────────────────────────
print("T1 · span giliran pertama (/session)")
sid1 = new_session("u-timing-1")
t_init = last_entry(sid1).get("timing") or {}
for key in ("semantic_s", "persist_s", "navigation_s", "reasoner_s", "session_init_s"):
    check(f"T1 {key} ada & numerik", is_num(t_init.get(key)), str(t_init))
check("T1b session_init_s >= semantic_s + persist_s (mencakup seluruh inisialisasi)",
      is_num(t_init.get("session_init_s")) and is_num(t_init.get("semantic_s"))
      and is_num(t_init.get("persist_s"))
      and t_init["session_init_s"] + 0.02 >= t_init["semantic_s"] + t_init["persist_s"], str(t_init))

print("T2 · span giliran biasa (/message)")
say(sid1, MSG)
t_msg = last_entry(sid1).get("timing") or {}
for key in ("semantic_s", "navigation_s", "reasoner_s", "total_s", "persist_s", "request_total_s"):
    check(f"T2 {key} ada & numerik", is_num(t_msg.get(key)), str(t_msg))

# ── T3 · inclusive/exclusive span consistency ──────────────────────────────────────────────────────
print("T3 · konsistensi span")
check("T3a request_total_s >= total_s (persist terjadi setelah total_s dihitung)",
      t_msg["request_total_s"] + 0.02 >= t_msg["total_s"], str(t_msg))
check("T3b navigation_s + reasoner_s <= reason_s (reason inklusif, tak dijumlah dua kali)",
      t_msg["navigation_s"] + t_msg["reasoner_s"] <= t_msg["reason_s"] + 0.05, str(t_msg))
if t_msg.get("second_pass_s") is not None:
    check("T3c second_pass_s NESTED di navigation_s (bukan span sejajar)",
          t_msg["second_pass_s"] <= t_msg["navigation_s"] + 0.05, str(t_msg))
else:
    check("T3c second_pass_s tidak ada -> tidak dipaksakan (jujur)", True)

# ── T4 · non-interference: constant perf_counter -> identical decisions ─────────────────────────
print("T4 · non-interferensi instrumentasi")
sid_normal = new_session("u-timing-normal")
say(sid_normal, MSG)
e_norm = last_entry(sid_normal)

sid_frozen = new_session("u-timing-frozen")
_real = _time.perf_counter
_time.perf_counter = lambda: 4242.0  # all spans = 0; must NOT change decisions/evidence
try:
    say(sid_frozen, MSG)
finally:
    _time.perf_counter = _real
e_frozen = last_entry(sid_frozen)

d_norm = (e_norm["decision"]["kind"], e_norm["decision"]["intent"],
          e_norm["decision"]["focus"], e_norm["decision"]["stop"])
d_frozen = (e_frozen["decision"]["kind"], e_frozen["decision"]["intent"],
            e_frozen["decision"]["focus"], e_frozen["decision"]["stop"])
check("T4a keputusan deterministik identik dengan/ tanpa timing", d_norm == d_frozen,
      f"normal={d_norm} frozen={d_frozen}")
sig_norm = [e.signal for e in (store.get(sid_normal).evidence or [])]
sig_frozen = [e.signal for e in (store.get(sid_frozen).evidence or [])]
check("T4b evidence kanonik identik dengan/ tanpa timing", sig_norm == sig_frozen,
      f"normal={sig_norm} frozen={sig_frozen}")
check("T4c timing frozen ternyata nol (bukti perf_counter benar-benar dibekukan)",
      (e_frozen.get("timing") or {}).get("navigation_s") == 0.0
      and (e_frozen.get("timing") or {}).get("total_s") == 0.0, str(e_frozen.get("timing")))

# ── T5 · timing does not break replay ─────────────────────────────────────────────────────────
print("T5 · replay tetap sah")
check("T5 replay keputusan tetap ok dengan timing ditambahkan", bool(replay(e_norm)["ok"]),
      str(replay(e_norm)))

print()
failed = [r for r in RESULTS if not r[1]]
print(f"{'❌ FAIL' if failed else '✅ PASS'} · {len(RESULTS) - len(failed)}/{len(RESULTS)}")
for name, _ok, detail in failed:
    print(f"   ❌ {name}: {detail[:200]}")
sys.exit(1 if failed else 0)
