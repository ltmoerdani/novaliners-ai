"""INV-R6 lock test — Phase 6 wave-22 (review finding 0ed2452).

Locks TWO independent mismatches found by the review between the route validator
and the registry validator:

1. PATH  : the route validator used to look for `ontology/route/requirement_registry.json`,
           the registry validator at `ontology/registry/requirement_registry.json`
           → blind cross-check while the registry did not exist (silent close).
2. KEY   : the route validator used to read `r["id"]`, contract §5.1 = `requirement_id`
           → new entries would not be read; legacy `req.*` keys passed silently.

It also proves: legacy `req.*` refs do NOT appear in the load result set — once the
first registry file exists, `example_lineage.json` (req.* ids) WILL error.
That is NOT a regression — it is the signal that INV-R6 starts working (review 0ed2452:
do not soften the validator with an alias).

Run: cd mvp && .venv/bin/python ontology/route/test_inv_r6.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

MVP = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MVP))

from ontology.registry import validate_registry as rg  # noqa: E402
from ontology.route import validate_route as vr  # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []


def _check(name: str, fn) -> None:
    try:
        fn()
        RESULTS.append((name, True, ""))
    except Exception as exc:  # noqa: BLE001
        RESULTS.append((name, False, f"{type(exc).__name__}: {exc}"))


def t_path_konvergensi() -> None:
    """TWO validators refer to ONE path — if either one moves, it goes red."""
    kanonik = MVP / "ontology" / "registry" / "requirement_registry.json"
    assert vr.REGISTRY_PATH == rg.REGISTRY_FILE, (
        f"path bercabang: route={vr.REGISTRY_PATH} registry={rg.REGISTRY_FILE}"
    )
    assert vr.REGISTRY_PATH == kanonik
    # the OLD path (silently-closed) must not come back
    assert vr.REGISTRY_PATH != vr.HERE / "requirement_registry.json"


def t_key_requirement_id() -> None:
    """Load uses requirement_id (contract §5.1); the old key 'id' is NOT read
    — no alias (review prohibition: an alias blurs the contract)."""
    tmp = Path(tempfile.mkdtemp(prefix="invr6_")) / "requirement_registry.json"
    tmp.write_text(json.dumps({"requirements": [
        {"requirement_id": "conversion.commitment_obtained"},
        {"requirement_id": "gtm.whole_product"},          # HOLD: id tunggal apa adanya
        {"id": "req.legacy_style"},                        # old key — NOT carried over
    ]}), encoding="utf-8")
    saved = vr.REGISTRY_PATH
    vr.REGISTRY_PATH = tmp
    try:
        loaded = vr.load_registry()
    finally:
        vr.REGISTRY_PATH = saved
    assert loaded == {"conversion.commitment_obtained", "gtm.whole_product"}, loaded
    assert "req.legacy_style" not in loaded


def t_ref_legacy_ditolak() -> None:
    """Legacy req.* refs are NOT in the registry set → check_node produces
    an INV-R6 error (the review's prediction for example_lineage — indeed intended)."""
    vr.errors.clear()
    node = {"resolves": ["req.landing_page_ready"], "strength": "hard",
            "depends_on": [], "activity": "x"}
    vr.check_node(node, "test", {"conversion.commitment_obtained"})
    hits = [e for e in vr.errors if "INV-R6" in e and "req.landing_page_ready" in e]
    assert hits, f"ref legacy lolos — INV-R6 tak aktif; errors={vr.errors}"
    # and with an id that is ALREADY in the registry → no INV-R6 error
    vr.errors.clear()
    node2 = dict(node, resolves=["conversion.commitment_obtained"])
    vr.check_node(node2, "test", {"conversion.commitment_obtained"})
    assert not [e for e in vr.errors if "INV-R6" in e], vr.errors


def t_registry_absen_tetap_warning() -> None:
    """Registry not yet present = warning + None (cross-check DEFERRED, not an error)
    — old behavior preserved until the first phase-6 file is written."""
    saved = vr.REGISTRY_PATH
    vr.REGISTRY_PATH = Path(tempfile.mkdtemp(prefix="invr6_")) / "absen.json"
    vr.warnings.clear()
    try:
        assert vr.load_registry() is None
    finally:
        vr.REGISTRY_PATH = saved
    assert any("DITUNDA" in w for w in vr.warnings), vr.warnings


def main() -> int:
    for name, fn in sorted(globals().items()):
        if name.startswith("t_") and callable(fn):
            _check(name, fn)
    ok = True
    for name, passed, err in RESULTS:
        print(f"  {'PASS' if passed else 'FAIL'}  {name}" + (f"  — {err}" if err else ""))
        ok = ok and passed
    print(f"\n{sum(p for _, p, _ in RESULTS)}/{len(RESULTS)} INV-R6 lock tests passed")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
