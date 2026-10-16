"""Actor authentication test (BC-02/CP-30, int 16 DR-17) — deterministic, no LLM.

What is proven:
  T1  TOKEN mode: missing/wrong bearer → 401; /health exempt → 200.
  T2  actor + user_id match → session created; someone else's user_id → 403 (DR-17:
      client-provided user_id is not authority).
  T3  cross-actor negative: actor B cannot read actor A's session (403) —
      state & navigation endpoints; someone else's workspace → 403.
  T4  /sessions is actor-scoped: actor B does not see actor A's sessions; actor A does.
  T5  LOCAL mode (empty env): legacy MVP behavior intact — no header still 200
      (deployment boundary: NOT for public multi-user; documented).
  T6  broken env JSON → fail-closed: TOKEN mode with all requests 401.

Isolation: sessions/workspaces created by the test are DELETED (the per-user store is
a real folder); LLM is patched at module level so POST /session is deterministic.
Run: .venv/bin/python evals/test_actor_auth.py
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, ".")

from evals._store_isolation import isolate_store  # noqa: E402

isolate_store()  # eval: store redirected to tmp — production store untouched

FAILS: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"{'✅' if ok else '❌'} {label}" + (f" | {detail}" if detail else ""))
    if not ok:
        FAILS.append(label)


os.environ["NOVALINERS_ACTOR_TOKENS"] = json.dumps({"tok-alice": "alice", "tok-bob": "bob"})

from fastapi.testclient import TestClient  # noqa: E402

from app import auth as app_auth  # noqa: E402
from app import main as appmain  # noqa: E402

# LLM patched at module level — POST /session must not touch the provider
# (this test is deterministic; the live provider is tested by a separate R7 runner).
appmain._ingest_initial_story = lambda s: "Pertanyaan awal (mock test auth)."

client = TestClient(appmain.app)
ALICE = {"Authorization": "Bearer tok-alice"}
BOB = {"Authorization": "Bearer tok-bob"}

_CREATED_SESS: list[str] = []
_GOALS_DIR = Path("store/goals")
_BEFORE_GOALS = set(p.name for p in _GOALS_DIR.glob("*")) if _GOALS_DIR.exists() else set()


def _mk_session(headers: dict, user_id: str = "alice") -> object:
    body = {"goal_text": "bisnis catering saya sepi", "language": "id", "user_id": user_id}
    return client.post("/session", json=body, headers=headers)


try:
    # ── T1: bearer required, health exempt ──
    check("T1a /health exempt tanpa bearer", client.get("/health").status_code == 200)
    r = client.post("/session", json={"goal_text": "x"})
    check("T1b POST /session tanpa bearer → 401", r.status_code == 401, str(r.status_code))
    r = client.post("/session", json={"goal_text": "x"}, headers={"Authorization": "Bearer tok-salah"})
    check("T1c token salah → 401", r.status_code == 401, str(r.status_code))

    # ── T2: actor from token, not from body ──
    r = _mk_session(ALICE, user_id="alice")
    check("T2a alice buat sesi user_id=alice → 200", r.status_code == 200, r.text[:120])
    sid_a = r.json().get("session_id", "")
    _CREATED_SESS.append(sid_a)
    check("T2b sesi tercatat milik alice", bool(sid_a))
    r = _mk_session(ALICE, user_id="bob")
    check("T2c alice mengklaim user_id=bob → 403", r.status_code == 403, str(r.status_code))
    r = _mk_session(ALICE, user_id="")  # anonymous is valid (read via sid; MVP boundary documented)
    check("T2d sesi anonim oleh actor sah → 200", r.status_code == 200, str(r.status_code))

    # ── T3: cross-actor isolation (core BC-02 negative) ──
    r = client.get(f"/session/{sid_a}/state", headers=BOB)
    check("T3a bob baca state sesi alice → 403", r.status_code == 403, str(r.status_code))
    r = client.get(f"/session/{sid_a}/navigation", headers=BOB)
    check("T3b bob baca navigation sesi alice → 403", r.status_code == 403, str(r.status_code))
    r = client.get(f"/session/{sid_a}/state", headers=ALICE)
    check("T3c alice baca sesinya sendiri → 200", r.status_code == 200, str(r.status_code))
    r = client.get("/workspace/alice", headers=BOB)
    check("T3d bob baca workspace alice → 403", r.status_code == 403, str(r.status_code))
    r = client.get("/workspace/alice", headers=ALICE)
    check("T3e alice baca workspace sendiri → 200", r.status_code == 200, str(r.status_code))

    # ── T4: /sessions actor-scoped ──
    ids_bob = {x["session_id"] for x in client.get("/sessions", headers=BOB).json()}
    ids_alice = {x["session_id"] for x in client.get("/sessions", headers=ALICE).json()}
    check("T4a bob TIDAK melihat sesi alice", sid_a not in ids_bob)
    check("T4b alice melihat sesinya sendiri", sid_a in ids_alice)

    # ── unit helper auth ──
    check("T4c authenticate benar", app_auth.authenticate("Bearer tok-alice") == "alice")
    check("T4d authenticate header asing → None", app_auth.authenticate("Basic abc") is None)
finally:
    # ── T5: LOCAL mode — env emptied; legacy behavior intact ──
    os.environ.pop("NOVALINERS_ACTOR_TOKENS", None)
    try:
        r = client.post("/session", json={"goal_text": "x tanpa auth"})
        check("T5a LOCAL mode tanpa header → 200", r.status_code == 200, str(r.status_code))
        if r.status_code == 200:
            _CREATED_SESS.append(r.json().get("session_id", ""))
        if sid_a:
            # no header at all
            r = client.get(f"/session/{sid_a}/state")
            # LOCAL mode boundary is documented (not a multi-user claim)
            check("T5b LOCAL mode baca lintas-user → 200", r.status_code == 200, str(r.status_code))
    finally:
        # ── T6: broken env JSON → fail-closed ──
        os.environ["NOVALINERS_ACTOR_TOKENS"] = "{rusak"
        check("T6a mode rusak = token", app_auth.auth_mode() == "token")
        r = client.post("/session", json={"goal_text": "x"})
        check("T6b JSON rusak → 401 (fail-closed)", r.status_code == 401, str(r.status_code))
        os.environ.pop("NOVALINERS_ACTOR_TOKENS", None)

    # ── cleanup: remove store artifacts created by the test ──
    for sid in filter(None, _CREATED_SESS):
        for p in (Path("store/sessions") / f"{sid}.json", Path("store/events") / f"{sid}.jsonl"):
            p.unlink(missing_ok=True)
    if _GOALS_DIR.exists():
        for p in _GOALS_DIR.glob("*"):
            if p.name not in _BEFORE_GOALS:
                if p.is_dir():
                    shutil.rmtree(p, ignore_errors=True)
                else:
                    p.unlink(missing_ok=True)

print(f"\nHASIL test_actor_auth: {len(FAILS)} gagal")
sys.exit(1 if FAILS else 0)
