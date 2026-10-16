"""Disk-store isolation for evals (fixes 963 orphan_events, 15 Oct 2026).

Problem: tests/evals created real sessions in the production store (`store/sessions/`,
`store/events/`), while cleanup only deleted snapshots — leftover event JSONL without a
snapshot kept piling up. On every restart, `_scan_orphan_events` logged them as
`orphan_events` (963+).

Solution: `isolate_store()` redirects `SessionStore.PERSIST_DIR` and `events.EVENTS_DIR`
to a tmp directory that is rmtree'd when the process ends. The production store is
never touched by evals.

Usage (AFTER `sys.path.insert` of the repo root, BEFORE creating sessions):

    from evals._store_isolation import isolate_store  # noqa: E402

    isolate_store()

Safe to call many times (idempotent per process); the first call allocates the tmp dir.
"""

from __future__ import annotations

import atexit
import shutil
import tempfile
from pathlib import Path

_DONE = False
_BASE: Path | None = None


def isolate_store() -> Path:
    """Redirect the snapshot & event store to this process's tmp dir. Idempotent.

    Fix of 15 Oct 2026 (regression `a86721c`): a second call now returns the SAME tmp dir
    instead of raising RuntimeError. Reason: layered harnesses are legitimate —
    `test_recovery_adaptive` calls `isolate_store()` and then imports `test_recovery_semantic`,
    which calls it too; the strict version made EVERY suite importing those harnesses crash
    at import time ("called twice"), including `evals/test_recovery_dsc_v1.py`. The correct
    "duplicate wiring" check is a store that is NOT isolated (PERSIST_DIR still pointing at
    production), not the call count."""
    global _DONE, _BASE
    if _DONE:
        assert _BASE is not None
        return _BASE
    _DONE = True

    from store import events as event_store
    from store.memory import SessionStore

    base = Path(tempfile.mkdtemp(prefix="nvl_eval_store_"))
    persist_dir = base / "sessions"
    events_dir = base / "events"
    persist_dir.mkdir(parents=True)
    events_dir.mkdir(parents=True)

    SessionStore.PERSIST_DIR = persist_dir
    event_store.EVENTS_DIR = events_dir

    # Neutralize import leakage (regression a86721c, caught by gate-fast 15 Oct):
    # `store.memory` pulls `domains.revenue.schema.artifact` (only the type hint
    # DiagnosisArtifact) into sys.modules. The domain-isolation guard of test_candidate_golden
    # §E asserts sys.modules ABSOLUTELY — purging keeps the eval process clean again without
    # breaking existing object references; suites that genuinely need Revenue will re-import
    # it normally (pyc cache, no meaningful cost).
    import sys as _sys
    for _m in [m for m in list(_sys.modules)
               if m == "domains.revenue" or m.startswith("domains.revenue.")]:
        del _sys.modules[_m]

    atexit.register(lambda: shutil.rmtree(base, ignore_errors=True))
    _BASE = base
    return base
