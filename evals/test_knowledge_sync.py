"""Guard: knowledge source ↔ KB JSON sync (audit 18 Sep 2026).

Drift guarded: the manual compilation path (mapping md → ontology JSON) has no
automatic compiler, so an edit on one side goes undetected on the other
(a real incident: TM-I07 exists in tm_interventions.json but not in
mapping-novaliners.md — caught only via a manual audit).

Three deterministic checks (no LLM):
1. ID sync — every knowledge ID (P/R/A/I) in the mapping md must exist in the
   JSON, and conversely every JSON item for a book with a mapping must be
   listed in the md.
2. Chapter provenance — every provenance.chapters entry in the KB must point
   to a chapter file that actually exists under docs/knowledge/<book>/chapters/.
3. Coverage mapping — the 4 phase-1 books must keep their mapping md (regression
   guard against source-artifact deletion).

Books without a mapping md (phase 2+: em, hg, pr, sp, lc) are compiled directly
from chapters/patterns/cheatsheet — only check #2 applies to them.
Run: .venv/bin/python evals/test_knowledge_sync.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

MVP_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = MVP_ROOT.parent
KB_DIR = MVP_ROOT / "ontology" / "knowledge"
# Fix gate (Phase 6, wave-22): docs-restructure moved `docs/knowledge`
# → `internal-docs` without updating this test (the gate silently stayed
# red since the restructure). The `*-knowledge` glob survives future renumbering.
_KB_CANDIDATES = sorted((REPO_ROOT / "docs").glob("*-knowledge"))
KNOWLEDGE_DIR = _KB_CANDIDATES[0] if _KB_CANDIDATES else REPO_ROOT / "docs" / "knowledge"

# KB prefix ↔ book folder (spin-selling + spin-fieldbook merge → sp, per sources.json)
BOOKS: dict[str, str] = {
    "tm": "the-mom-test",
    "vp": "value-prop-design",
    "cs": "challenger-sale",
    "hk": "hooked",
    "pr": "predictable-revenue",
    "hg": "hacking-growth",
    "sp": "spin-selling",
    "em": "e-myth-revisited",
    "lc": "lost-art-of-closing",
}

# Phase-1 books that must have a mapping md (source compilation artifacts)
MAPPED_BOOKS = ("tm", "vp", "cs", "hk")

ID_KEY = {
    "probes": "probe_id",
    "evidence_rules": "rule_id",
    "anti_patterns": "pattern_id",
    "interventions": "intervention_id",
}
TYPE_SUFFIX = {"probes": "P", "evidence_rules": "R", "anti_patterns": "A", "interventions": "I"}

FAILS: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {label}{f' — {detail}' if detail and not ok else ''}")
    if not ok:
        FAILS.append(label)


def kb_ids(prefix: str) -> dict[str, set[str]]:
    """IDs per kind across all JSON files of a book prefix."""
    out: dict[str, set[str]] = {}
    for f in sorted(KB_DIR.glob(f"{prefix}_*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        for kind, key in ID_KEY.items():
            out.setdefault(kind, set()).update(i[key] for i in data.get(kind, []))
    return out


def md_ids(prefix: str) -> set[str]:
    """All <PREFIX>-<TYPE><NN>-formatted IDs mentioned in the mapping md."""
    text = (KNOWLEDGE_DIR / BOOKS[prefix] / "mapping-novaliners.md").read_text(encoding="utf-8")
    return set(re.findall(rf"\b{prefix.upper()}-(?:P|R|A|I)\d+\b", text))


def main() -> int:
    # Check #3 — phase-1 source artifacts must not go missing.
    missing = [
        p for p in MAPPED_BOOKS
        if not (KNOWLEDGE_DIR / BOOKS[p] / "mapping-novaliners.md").is_file()
    ]
    check("K3 mapping-file ada untuk buku fase-1", not missing, f"hilang: {missing}")

    # Check #1 — per-kind ID sync, both directions.
    for prefix in MAPPED_BOOKS:
        kb = kb_ids(prefix)
        md = md_ids(prefix)
        for kind, suffix in TYPE_SUFFIX.items():
            rx = re.compile(rf"{prefix.upper()}-{suffix}\d+")
            j = {i for i in kb.get(kind, set()) if rx.fullmatch(i)}
            m = {i for i in md if rx.fullmatch(i)}
            md_only = sorted(m - j)
            json_only = sorted(j - m)
            check(
                f"K1 {BOOKS[prefix]} {kind} sync md↔json",
                not md_only and not json_only,
                f"md-only={md_only} (belum dikompile), "
                f"json-only={json_only} (belum dibackfill ke md)",
            )

    # Check #2 — every provenance.chapters points to an existing chapter file.
    bad: list[str] = []
    for prefix, folder in BOOKS.items():
        available = [p.stem for p in (KNOWLEDGE_DIR / folder / "chapters").glob("*.md")]
        for f in sorted(KB_DIR.glob(f"{prefix}_*.json")):
            data = json.loads(f.read_text(encoding="utf-8"))
            for kind, key in ID_KEY.items():
                for item in data.get(kind, []):
                    for ch in item.get("provenance", {}).get("chapters", []):
                        if not any(a == ch or a.startswith(f"{ch}-") for a in available):
                            bad.append(f"{prefix}/{item[key]} -> {ch}")
    check("K2 provenance chapter resolves (semua item, 9 buku)", not bad, f"menggantung: {bad}")

    print()
    print("=" * 50)
    print(f"HASIL: {'SEMUA LULUS ✅' if not FAILS else f'{len(FAILS)} GAGAL ❌ → {FAILS}'}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())

