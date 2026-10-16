#!/usr/bin/env python
"""Rubric compiler — Phase 1 (internal-docs §5.1, internal-docs).

Compiles KB rules → concise rubric per rule_id (and per capability), output
`compiled_rubrics.json`. Fully deterministic (sorted, no timestamp) so it is
safe to include in kb_sha256.

Why: KB depth grows at compile-time; the tier-2 prompt reads concise rubrics,
not the full matcher_hint. The next book extraction only regenerates
this file — prompt cost stays flat (internal-docs §5.1).

Usage: python ontology/knowledge/compile_rubrics.py  (from mvp/)
Exit 0 = compiled_rubrics.json written & consistent; exit 1 = a rule without
rubric text.
"""
import json
import re
import sys
from pathlib import Path

KB = Path(__file__).parent
OUT = KB / "compiled_rubrics.json"

SIGNS = {
    "RAISE_CONFIDENCE": "+",
    "LOWER_CONFIDENCE": "-",
    "BLOCK_VERDICT": "!",
    "FLAG_SEGMENT": "~",
    "IGNORE_SIGNAL": "~",
}
MAX_CHARS = 160


def condense(text: str, limit: int = MAX_CHARS) -> str:
    """First sentence of matcher_hint, trimmed at a word boundary."""
    text = re.sub(r"\s+", " ", (text or "").strip())
    first = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0]
    if len(first) > limit:
        first = first[: limit - 1].rsplit(" ", 1)[0] + "…"
    return first


def main() -> int:
    lines_by_rule: dict[str, str] = {}
    by_capability: dict[str, list[str]] = {}
    problems: list[str] = []
    for f in sorted(KB.glob("*_evidence_rules.json")):
        for r in json.loads(f.read_text(encoding="utf-8")).get("evidence_rules", []):
            if r.get("lifecycle") == "CHALLENGED":
                continue  # a frozen rule does not enter the runtime rubric (B1b)
            rid = r["rule_id"]
            sign = SIGNS.get((r.get("consequence") or {}).get("action"), "~")
            body = condense(r.get("matcher_hint") or r.get("condition") or "")
            if not body:
                problems.append(f"{rid}: empty matcher_hint/condition — cannot be compiled")
                continue
            lines_by_rule[rid] = f"{rid} {sign} {body}"
            for t in (r.get("consequence") or {}).get("targets") or []:
                by_capability.setdefault(t, []).append(lines_by_rule[rid])

    if problems:
        print("✗ COMPILE FAILED:")
        for p in problems:
            print("  -", p)
        return 1

    # B1a (internal-docs Phase 3 remainder): contradiction detector REPORT-ONLY.
    # RAISE vs LOWER rules on the same capability are normal (depends on
    # evidence); what humans need to see = cross-source pairs with opposite
    # signs — adjudication cluster candidates (B1b, internal-docs §364 "trigger").
    sign_of = {}
    meta = {}
    for f in sorted(KB.glob("*_evidence_rules.json")):
        for r in json.loads(f.read_text(encoding="utf-8")).get("evidence_rules", []):
            if r.get("lifecycle") == "CHALLENGED":
                continue  # a frozen rule does not enter the runtime rubric (B1b)
            sign_of[r["rule_id"]] = SIGNS.get((r.get("consequence") or {}).get("action"), "~")
            meta[r["rule_id"]] = r
    clusters = {}
    for rid, line in lines_by_rule.items():
        sign = sign_of[rid]
        src = rid.split("-")[0]
        for t in (meta[rid].get("consequence") or {}).get("targets") or []:
            clusters.setdefault(t, {}).setdefault(sign, set()).add(src)
    contradictions = []
    for cap, by_sign in sorted(clusters.items()):
        if not ({"+", "-"} <= by_sign.keys()):
            continue
        pairs = sorted(
            (a, b)
            for a in by_sign["+"]
            for b in by_sign["-"]
            if a != b
        )
        if pairs:
            contradictions.append({
                "capability": cap,
                "raise_sources": sorted(by_sign["+"]),
                "lower_sources": sorted(by_sign["-"]),
                "cross_source_pairs": pairs,
                "status": "REPORT_ONLY — adjudicate bila kedua sumber aktif di fase yang sama",
            })

    OUT.write_text(
        json.dumps(
            {
                "$comment": (
                    "FASE 1 — rubrik kompilasi KB (internal-docs §5.1). Dibuat oleh "
                    "compile_rubrics.py; JANGAN edit manual — regenerasi dengan "
                    "script. Konsumen: tier-2 matcher (core/stages/knowledge_rules.py). "
                    "Deterministik: sorted, tanpa timestamp — aman di kb_sha256."
                ),
                "rubric_lines": dict(sorted(lines_by_rule.items())),
                "by_capability": {k: sorted(v) for k, v in sorted(by_capability.items())},
                "contradiction_report": sorted(contradictions, key=lambda c: c["capability"]),
            },
            ensure_ascii=False,
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    n_pairs = sum(len(c["cross_source_pairs"]) for c in contradictions)
    print(f"✅ compiled_rubrics.json: {len(lines_by_rule)} rule lines, "
          f"{len(by_capability)} capability, "
          f"{len(contradictions)} cross-source contradiction clusters ({n_pairs} pairs) — REPORT ONLY")
    return 0


if __name__ == "__main__":
    sys.exit(main())
