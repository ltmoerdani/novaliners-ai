#!/usr/bin/env python
"""Structural METRIC REGISTRY validator (internal-docs §3.1; ADR-GR1).

BOUNDARY VALIDATOR — checks shape, not policy:
  1. closed enums: semantics / role / missing_handling / conflict_handling
  2. unique identity: metric_id + alias must not clash across metrics
  3. required fields per metric + their base types
  4. minimum semantic consistency: RATE_OR_RATIO ⇒ requires_denominator;
     COUNT_IN_WINDOW ⇒ window is not "none"; EVIDENCE_CRITERIA ⇒ unit "criteria"
  5. registry_version recorded (GR/UC evidence records use it)

Does NOT decide: whether a metric definition is "good enough" business-wise (the reviewer = authority).

Usage: python validate_metrics.py  (from mvp/)
Exit 0 = VALID; exit 1 = INVALID.
"""
from __future__ import annotations

import sys

sys.path.insert(0, ".")

from ontology.registry import metrics as mr  # noqa: E402

REQUIRED_FIELDS = {
    "metric_id": str, "version": int, "display_name": dict, "aliases": list,
    "category": str, "unit": str, "semantics": str, "window": str,
    "requires_denominator": bool, "requires_qualification": bool, "role": str,
    "allowed_evidence": list, "missing_handling": str, "conflict_handling": str,
    "success_example": str, "invalid_example": str,
}


def main() -> int:
    doc = mr.load_registry()
    errors: list[str] = []
    semantics = set(doc.get("semantics", []))
    roles = set(doc.get("roles", []))
    missing_values = set(doc.get("missing_handling_values", []))
    conflict_values = set(doc.get("conflict_handling_values", []))
    if not doc.get("registry_version"):
        errors.append("registry_version must be recorded (used by GR/UC evidence records)")

    seen_id: dict[str, str] = {}
    seen_alias: dict[str, str] = {}
    for i, m in enumerate(doc.get("metrics", [])):
        label = f"metrics[{i}:{m.get('metric_id', '?')}]"
        for field, typ in REQUIRED_FIELDS.items():
            if field not in m:
                errors.append(f"{label}: missing required field: {field}")
            elif not isinstance(m[field], typ):
                errors.append(f"{label}.{field}: type {type(m[field]).__name__}, expected {typ.__name__}")
        mid = m.get("metric_id", "")
        if mid:
            if mid in seen_id:
                errors.append(f"{label}: duplicate metric_id (also at {seen_id[mid]})")
            seen_id[mid] = label
        for alias in [mid, *m.get("aliases", [])]:
            a = str(alias or "").lower().strip()
            if not a:
                continue
            if a in seen_alias and seen_alias[a] != label:
                errors.append(
                    f"{label}: alias {a!r} clashes with {seen_alias[a]} — aliases unique across metrics")
            seen_alias[a] = label
        if m.get("semantics") not in semantics:
            errors.append(f"{label}: semantics {m.get('semantics')!r} is not an enum of registry.semantics")
        if m.get("role") not in roles:
            errors.append(f"{label}: role {m.get('role')!r} is not an enum of registry.roles")
        if m.get("missing_handling") not in missing_values:
            errors.append(f"{label}: missing_handling {m.get('missing_handling')!r} is not an enum")
        if m.get("conflict_handling") not in conflict_values:
            errors.append(f"{label}: conflict_handling {m.get('conflict_handling')!r} is not an enum")
        # minimum semantic consistency
        sem = m.get("semantics")
        if sem == "RATE_OR_RATIO" and not m.get("requires_denominator"):
            errors.append(f"{label}: RATE_OR_RATIO requires requires_denominator=true")
        if sem == "COUNT_IN_WINDOW" and m.get("window") == "none":
            errors.append(f"{label}: COUNT_IN_WINDOW must not have window=none")
        if sem == "EVIDENCE_CRITERIA" and m.get("unit") != "criteria":
            errors.append(f"{label}: EVIDENCE_CRITERIA requires unit=criteria")
        if m.get("requires_qualification") and not str(m.get("notes", "")).strip():
            errors.append(f"{label}: requires_qualification=true must carry criteria notes")

    for e in errors:
        print(f"ERROR {e}")
    n = len(doc.get("metrics", []))
    if errors:
        print(f"metric registry {doc.get('registry_version')}: {len(errors)} error → INVALID ✗")
        return 1
    print(f"metric registry {doc.get('registry_version')}: {n} metrics valid → VALID ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
