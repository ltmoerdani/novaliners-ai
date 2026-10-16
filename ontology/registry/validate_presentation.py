#!/usr/bin/env python
"""Requirement Presentation validator (internal-docs §Requirement Presentation).

Presentation = display text per language on top of the Requirement Registry. The registry remains the only
source of identity and semantics, so the validator enforces three things:

  1. no orphan entries: every presentation requirement_id EXISTS in the registry;
  2. shape: registered language, non-empty title/verification string, known fields only;
  3. no smuggled requirement semantics (status ids, gates, satisfaction rules, gate strings).

Inline negative test: the validator must really be able to reject (not vacuous).
Usage: python ontology/registry/validate_presentation.py (from mvp/). Exit 0 = valid.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
REGISTRY_PATH = HERE / "requirement_registry.json"
PRESENTATION_PATH = HERE / "requirement_presentation.json"

ALLOWED_FIELDS = {"title", "description", "verification"}
REQUIRED_FIELDS = ("title", "verification")
FORBIDDEN_KEYS = {
    "requirement_id",
    "satisfaction_rule",
    "observability",
    "definition",
    "provenance",
    "gate",
    "gates",
    "status",
    "state",
    "applicability",
    "route",
    "strategy_id",
}


def validate(pack: dict, registry_ids: set[str]) -> list[str]:
    errs: list[str] = []
    langs = pack.get("languages")
    if not isinstance(langs, list) or not langs or not all(isinstance(x, str) for x in langs):
        errs.append("`languages` must be a non-empty list of strings")
        langs = []
    entries = pack.get("entries")
    if not isinstance(entries, dict):
        return errs + ["`entries` must be an object"]
    for rid, per_lang in entries.items():
        if rid not in registry_ids:
            errs.append(f"{rid}: NOT present in the Requirement Registry (orphan entry)")
        if not re.fullmatch(r"[a-z][a-z0-9_]*(\.[a-z0-9_]+)+", rid):
            errs.append(
                f"{rid}: not a valid requirement_id (dotted, lowercase) — presentation is keyed by id, "
                f"not human text"
            )
        if not isinstance(per_lang, dict) or not per_lang:
            errs.append(f"{rid}: must be a non-empty language object")
            continue
        for lang, fields in per_lang.items():
            where = f"{rid}[{lang}]"
            if lang not in langs:
                errs.append(f"{where}: language not registered in `languages`")
            if not isinstance(fields, dict):
                errs.append(f"{where}: must be a field object")
                continue
            for k in fields:
                if k in FORBIDDEN_KEYS:
                    errs.append(f"{where}: field `{k}` = requirement semantics, owned by the registry")
                elif k not in ALLOWED_FIELDS:
                    errs.append(f"{where}: unknown field `{k}`")
            for k in REQUIRED_FIELDS:
                if not isinstance(fields.get(k), str) or not fields[k].strip():
                    errs.append(f"{where}: `{k}` must be a non-empty string")
            for k in ALLOWED_FIELDS & fields.keys():
                if not isinstance(fields[k], str):
                    errs.append(f"{where}: `{k}` must be a string")
    return errs


def _negative_cases(ids: set[str]) -> list[str]:
    """Every case MUST produce >=1 error; if it passes silently, the validator is vacuous."""
    good = {"languages": ["en"], "entries": {"offering.exists": {"en": {"title": "T", "verification": "V"}}}}
    bad = {
        "entri yatim": {**good, "entries": {"ghost.requirement": good["entries"]["offering.exists"]}},
        "kunci teks manusia": {**good, "entries": {"A concrete offer": good["entries"]["offering.exists"]}},
        "bahasa tak terdaftar": {
            **good,
            "entries": {"offering.exists": {"fr": {"title": "T", "verification": "V"}}},
        },
        "title kosong": {**good, "entries": {"offering.exists": {"en": {"title": " ", "verification": "V"}}}},
        "semantik diselundupkan": {
            **good,
            "entries": {
                "offering.exists": {"en": {"title": "T", "verification": "V", "satisfaction_rule": {}}}
            },
        },
        "field asing": {
            **good,
            "entries": {"offering.exists": {"en": {"title": "T", "verification": "V", "x": "y"}}},
        },
    }
    misses = [name for name, pack in bad.items() if not validate(pack, ids)]
    ok = not validate(good, ids | {"offering.exists"})
    out = [f"validator vacuous: case '{n}' passed" for n in misses]
    return out + ([] if ok else ["positive case rejected"])


def main() -> int:
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    ids = {e["requirement_id"] for e in registry["requirements"]}
    pack = json.loads(PRESENTATION_PATH.read_text(encoding="utf-8"))
    errs = validate(pack, ids) + _negative_cases(ids)
    covered = len(pack.get("entries") or {})
    for e in errs:
        print(f"ERROR {e}")
    print(
        f"PRESENTATION: {covered}/{len(ids)} requirements with curated text; the rest use the "
        f"deterministic fallback → {'VALID ✓' if not errs else 'INVALID ✗'}"
    )
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
