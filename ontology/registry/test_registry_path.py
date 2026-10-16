#!/usr/bin/env python
"""Phase 2 regression (review finding `e5ad03a`): duplicate detection on the
MAIN REGISTRY PATH (`requirement_registry.json`), not just the fixture path.

Bug P1 prevented from returning: a `seen={}` literal as an argument
is evaluated anew on every iteration in `_reg()` → a duplicate `requirement_id` in the
production registry passes silently, even though the fixture path (correct pattern:
`seen` declared once outside the loop) catches the identical case.

This test writes a TEMPORARY registry at the production path, runs the validator
as a subprocess, then cleans up after itself (finally). Two phases:

  PHASE 1 — the registry contains duplicate ids → the validator MUST fail + mention
           "DUPLIKAT" (duplicate detected on the main registry path)
  PHASE 2 — valid registry (2 unique ids)    → the validator MUST be green
           (no false positive from the `seen` lifetime change)

Usage: python test_registry_path.py
Exit 0 = both phases pass; exit 1 = fail.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
REGISTRY = HERE / "requirement_registry.json"
VALIDATOR = HERE / "validate_registry.py"


def _entry(rid: str) -> dict:
    return {
        "requirement_id": rid,
        "definition": "Kondisi uji jalur registry utama.",
        "observability": ["Pengamatan uji tercatat"],
        "satisfaction_rule": {
            "mode": "BINARY",
            "sufficient": "Terpenuhi.",
            "no_decisive": "Tidak pasti.",
            "contradicting": "Tertolak.",
        },
        "provenance": {
            "source_id": "tm",
            "chapters": ["ch01"],
            "knowledge_type": "source_claim",
            "confidence": "normative_only",
        },
    }


def run() -> tuple[int, str]:
    p = subprocess.run([sys.executable, str(VALIDATOR)],
                       capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def main() -> int:
    failures: list[str] = []
    # BACKUP/RESTORE (review finding c1e72f3): this test writes to the PRODUCTION
    # PATH — once phase 6 fills requirement_registry.json with real
    # entries, an old version without a backup would OVERWRITE and then DELETE the
    # production registry. Save the old content (if any); restore it in finally. While
    # the file genuinely does not exist (D4), the path still unlinks as before.
    backup: str | None = None
    if REGISTRY.exists():
        backup = REGISTRY.read_text(encoding="utf-8")
    try:
        # PHASE 1: duplicate ids in the main registry MUST be detected
        REGISTRY.write_text(json.dumps(
            {"requirements": [_entry("dup.test_a"), _entry("dup.test_a")]},
            ensure_ascii=False, indent=1), encoding="utf-8")
        code, out = run()
        if code == 0:
            failures.append("PHASE 1: duplicate-id registry PASSED (exit 0) "
                            "— duplicate detection is dead on the main registry path")
        elif "DUPLIKAT" not in out:
            failures.append(f"PHASE 1: exit {code} but without a DUPLICATE "
                            f"error — output:\n{out}")

        # PHASE 2: a valid registry MUST be green (anti false positive)
        REGISTRY.write_text(json.dumps(
            {"requirements": [_entry("valid.satu"), _entry("valid.dua")]},
            ensure_ascii=False, indent=1), encoding="utf-8")
        code, out = run()
        if code != 0:
            failures.append(f"PHASE 2: valid registry FAILED (exit {code}):"
                            f"\n{out}")
    finally:
        if backup is not None:
            REGISTRY.write_text(backup, encoding="utf-8")  # restore the old content
        elif REGISTRY.exists():
            REGISTRY.unlink()  # it indeed does not exist before the test — clean up

    for f in failures:
        print(f"GAGAL {f}")
    if failures:
        print(f"\ntest_registry_path — {len(failures)} kegagalan → ✗")
        return 1
    print("test_registry_path — duplikat terdeteksi di jalur registry UTAMA "
          "& registry valid hijau → ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
