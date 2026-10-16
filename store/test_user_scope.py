"""Per-store user identity invariant test (review 71b3c63 — conditionally green).

Condition #2 before the bridge: `user_id` is validated by the SHARED helper (store.user_scope)
in both stores so traversal ('../x', 'a/b') is rejected BEFORE the path join —
not merely non-empty. The negative test uses each store's private path builder API
exactly as production uses it (package mode, same as compose.py).

Run: cd mvp && python store/test_user_scope.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

MVP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MVP))

from store import adjudication_ledger as ledger  # noqa: E402
from store import route_lineages as rl  # noqa: E402
from store.user_scope import validate_user_id  # noqa: E402

# user_id that must be REJECTED hard (traversal / not canonical)
_BAD = ["../escape", "a/b", "../../shared", "", "..", "u ser", "..\\..\\win"]
_OK = ["u1", "u-1_test", "test-ws-user", "u-j7"]


def t_validate_tolak_traversal() -> None:
    """Shared helper: the canonical pattern is enforced — non-empty alone is NOT enough."""
    for bad in _BAD:
        try:
            validate_user_id(bad)
        except ValueError:
            continue
        raise AssertionError(f"user_id tak path-safe lolos: {bad!r}")
    for good in _OK:
        assert validate_user_id(good) == good, f"user_id sah ditolak: {good!r}"


def t_dua_store_tolak_traversal() -> None:
    """Both stores reject BEFORE the path join — the root is not infected."""
    tmp = Path(tempfile.mkdtemp(prefix="uscope_"))
    for bad in _BAD:
        try:
            ledger._channel(bad, "adjudication_ledger.jsonl")
        except ValueError:
            pass
        else:
            raise AssertionError(f"adjudication_ledger menerima {bad!r}")
        try:
            rl._path(bad, tmp)
        except ValueError:
            pass
        else:
            raise AssertionError(f"route_lineages menerima {bad!r}")
    # valid path still works — the path is exactly under the root (not outside)
    p_ok = ledger._channel("u-ok", "adjudication_ledger.jsonl")
    assert str(p_ok).startswith(str(ledger._LEDGER_ROOT.resolve()))
    assert rl._path("u-ok", tmp) == tmp / "u-ok" / "route_lineages.jsonl"
    # no directory is created by a traversal attempt
    assert not (tmp.parent / "escape").exists()


def t_d8_store_lama_workspace() -> None:
    """D8: the old path-based store (workspace) uses the shared helper;
    silent degrade for anonymous users ("") is preserved."""
    from store import workspace
    for bad in [b for b in _BAD if b]:
        try:
            workspace._user_dir(bad)
        except ValueError:
            continue
        raise AssertionError(f"workspace menerima {bad!r}")
    assert workspace._user_dir("u-ok").name == "u-ok"
    assert workspace.ensure_workspace("") is None  # anonymous: degrade, not an error
    assert workspace.workspace_exists("") is False


def t_d8_app_tolak_400() -> None:
    """D8: the app entrance rejects an unsafe user_id with 400 (not 500)."""
    from fastapi.testclient import TestClient

    from app.main import app
    c = TestClient(app)
    r = c.post("/session", json={"goal_text": "tes", "language": "id",
                                 "user_id": "../escape"})
    assert r.status_code == 400, (r.status_code, r.text[:200])
    r2 = c.get("/workspace/bad.id")
    assert r2.status_code == 400, (r2.status_code, r2.text[:200])


TESTS = [t_validate_tolak_traversal, t_dua_store_tolak_traversal,
         t_d8_store_lama_workspace, t_d8_app_tolak_400]


def main() -> int:
    passed = 0
    for fn in TESTS:
        try:
            fn()
            passed += 1
            print(f"  PASS  {fn.__name__}")
        except Exception as exc:  # noqa: BLE001
            print(f"  FAIL  {fn.__name__} — {type(exc).__name__}: {exc}")
    print(f"\n{passed}/{len(TESTS)} user-scope tests passed")
    return 0 if passed == len(TESTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
