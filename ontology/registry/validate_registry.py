#!/usr/bin/env python
"""Load-time validator for the NOVALINERS REQUIREMENT REGISTRY SCHEMA v0.1
(PHASE 2 — GO owner 26 Sep 2026; contract: internal-docs §5).

=== BOUNDARY VALIDATOR (guardrail owner — "semantic audit validator boundary") ===
The validator MAY check (structural):
  1. required layers/fields (5 layers §5.1)
  2. closed enums (satisfaction_status · rule_mode · knowledge_type · confidence)
  3. union consistency (mode BINARY ↔ partial banned · mode PARTIAL ↔ required)
  4. unique requirement_id
  5. provenance shape (+ source_id registered in sources.json)
  6. forbidden route/activity/execution/scope/evidence_sources fields (recursive)
  7. D2 status-suffix guardrail (from the closed status vocabulary)
  8. malformed references/structure (unknown key, wrong type, empty)
  9. schema ↔ contract drift (mirrored enums/forbidden/suffixes)
 10. RR9 linguistic signal = WARNING ONLY — NEVER an error

The validator MUST NOT decide (domain audit/ontology):
  - requirement too coarse/fine (granularity = phase 4)
  - definition ontologically correct
  - observability "sufficient"
  - partial substantively meaningful
  - WHAT vs HOW based on semantic understanding → reviewer/audit = the authority

=== Phase 2 prohibitions (owner) ===
Does NOT load the 27 D4 entries — the main registry file stays optional until
phase 6; fixtures = synthetic examples (prefix sample./bad./rr9.).

Phase 2 checklist in order: JSON schema ✓ · drift check ✓ · structural validator
(this) · positive fixtures (0 errors) · negative fixtures (8 minimal cases) ·
RR9 warning fixtures (warning ≠ error) · boundary statement (above).

Usage: python validate_registry.py  (from mvp/ or the repo root)
Exit 0 = no ERROR (warnings allowed); exit 1 = an ERROR exists.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent                 # mvp/ontology/registry/
ONTO = HERE.parent                           # mvp/ontology/
SCHEMA_PATH = ONTO / "requirement_schema.json"
SOURCES_PATH = ONTO / "knowledge" / "sources.json"
REGISTRY_FILE = HERE / "requirement_registry.json"   # optional (phase 6)
FIXTURES = HERE / "fixtures"

# --- Mirror contract (int 09 §5, waves 1-3) — anti drift -----------------
CONTRACT_ENUMS = {
    "satisfaction_status": ["PRESENT", "PARTIAL", "UNKNOWN", "ABSENT"],
    "rule_mode": ["BINARY", "PARTIAL"],
    "knowledge_type": ["source_claim", "novaliners_synthesis", "empirical_outcome"],
    "confidence": ["normative_only", "expert_hypothesis", "empirical_low",
                   "empirical_high"],
}
CONTRACT_FORBIDDEN = {
    "route", "route_id", "strategy", "strategy_id", "template_id",
    "activity", "execution", "execution_view", "applicability", "frontier",
    "unlocks", "scope", "evidence_sources",
}
CONTRACT_SUFFIXES = {
    "present", "partial", "unknown", "absent",
    "ready", "done", "executed", "blocked", "proposed",
    "not_yet", "eligible", "conditional", "reopened", "retired",
}
ENTRY_LAYERS = {"requirement_id", "definition", "observability",
                "satisfaction_rule", "provenance"}
# RR9 enforcement (guardrail): Indonesian linguistic heuristic —
# WARNING SIGNAL only; the reviewer/audit = the semantic authority (still in force).
# v2 (owner 27 Sep, 3 requirements): (1) allowlist of STATE verbs — not HOW;
# (2) PROCESS phrase patterns (melalui/dengan cara/dilakukan/setelah/sebelum) =
# HOW-leak signals not caught by affixes (real case: beachhead pre-87b77a3
# 'terpilih melalui evaluasi scenario checklist'); (3) locked by fixtures.
ACTION_AFFIX = re.compile(r"\b(meng|men|mem|ber)[a-z]+", re.IGNORECASE)
# State verbs (stative verbs) — they describe the state of the world, NOT the how:
RR9_STATE_ALLOWLIST = frozenset({
    "memuat", "berupa", "menyertai", "berbentuk", "membayar", "membeli",
    "menarik", "memakai", "berfungsi", "memiliki", "berisi", "mencakup",
    "meliputi", "mengandung", "mengetahui", "mewakili", "mendukung",
    # v2.1 (rule-branch scan): evidence-reporting verbs (part of the reporting
    # language, not HOW); 'menetapkan' is NOT allowlisted — the canonical
    # no_decisive phrase is stripped whole before the scan (review 026d8b8:
    # a single-word allowlist would globally free 'menetapkan harga dengan...'):
    "menunjukkan", "menyatakan",
})
# Canonical no_decisive phrase — stripped from the text BEFORE the scan:
RR9_CANONICAL_PREFIX = re.compile(
    r"^Tidak ada informasi yang menetapkan apakah ", re.IGNORECASE)
# Process phrases = HOW signals (order/how/mechanism) — RR1/RR9:
RR9_PROCESS_PHRASE = re.compile(
    r"\b(melalui|dengan cara|dilakukan|setelah|sebelum)\b", re.IGNORECASE)
REQ_ID = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$")

errors: list[str] = []
warnings: list[str] = []


def err(msg: str) -> None:
    errors.append(msg)


def warn(msg: str) -> None:
    warnings.append(msg)


def load(p: Path):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def scan_forbidden(obj, path: str) -> None:
    """RR1/RR3/RR6: forbidden keys are BANNED anywhere in the entry tree (recursive)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in CONTRACT_FORBIDDEN:
                err(f"{path}: field terlarang {k!r} di dalam Requirement "
                    f"Registry (RR1/RR3/RR6 — layer lain / Universal State)")
            scan_forbidden(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            scan_forbidden(v, f"{path}[{i}]")


def check_rule(rule, where: str) -> None:
    """RR11 union consistency — checks SHAPE, not content (guardrail owner #1)."""
    if not isinstance(rule, dict):
        err(f"{where}: satisfaction_rule wajib objek")
        return
    unknown = set(rule) - {"mode", "sufficient", "partial", "no_decisive",
                           "contradicting"}
    if unknown:
        err(f"{where}: key tak dikenal {sorted(unknown)} (union tertutup)")
    mode = rule.get("mode")
    if mode not in CONTRACT_ENUMS["rule_mode"]:
        err(f"{where}: mode {mode!r} invalid — enum rule_mode "
            f"{CONTRACT_ENUMS['rule_mode']}")
        mode = None  # do not infer partial-consistency from a garbage mode
    for branch in ("sufficient", "no_decisive", "contradicting"):
        if not isinstance(rule.get(branch), str) or not rule.get(branch, "").strip():
            err(f"{where}: cabang rule {branch!r} wajib non-empty string "
                f"(minimal semantics 4-arah §5.1)")
    has_partial = "partial" in rule
    if mode == "BINARY" and has_partial:
        err(f"{where}: mode=BINARY tapi field 'partial' ADA — dilarang "
            f"(RR11 union: BINARY → PARTIAL tidak legal)")
    if mode == "PARTIAL":
        if not has_partial:
            err(f"{where}: mode=PARTIAL tapi field 'partial' HILANG — wajib "
                f"(RR11 union: PARTIAL → definisi kondisi partial wajib ada)")
        elif not isinstance(rule.get("partial"), str) or not rule["partial"].strip():
            err(f"{where}: mode=PARTIAL tapi 'partial' kosong — wajib non-empty")
    # The validator does NOT judge whether the partial content is substantively meaningful (phase 4)


def check_provenance(prov, where: str, sources: set[str] | None) -> None:
    if not isinstance(prov, dict):
        err(f"{where}: provenance wajib objek (5 lapisan §5.1)")
        return
    required = {"source_id", "chapters", "knowledge_type", "confidence"}
    missing = required - set(prov)
    if missing:
        err(f"{where}: provenance field hilang {sorted(missing)} (REUSE skema "
            f"KB — D5)")
    extra = set(prov) - required
    if extra:
        err(f"{where}: provenance field asing {sorted(extra)} — "
            f"evidence_sources/evidence provenance = Universal State (RR6)")
    sid = prov.get("source_id")
    if sources is not None and sid not in sources:
        err(f"{where}: source_id {sid!r} tidak terdaftar di sources.json "
            f"(authority_grade/admission ikut terwarisi via registry sumber)")
    ch = prov.get("chapters")
    if not isinstance(ch, list) or not ch or not all(
            isinstance(c, str) and c for c in ch):
        err(f"{where}: chapters wajib array non-empty string")
    _enum(prov.get("knowledge_type"), "knowledge_type",
          f"{where}.knowledge_type")
    _enum(prov.get("confidence"), "confidence", f"{where}.confidence")


def _enum(value, name: str, where: str) -> None:
    allowed = CONTRACT_ENUMS[name]
    if value not in allowed:
        err(f"{where}: {value!r} bukan enum {name} {allowed}")


def rr9_signal(entry, label: str) -> None:
    """RR9 enforcement: the linguistic heuristic = a WARNING that never
    fails an entry (guardrail owner #2). The semantic authority = the reviewer.
    v2: state verbs are allowlisted; process phrases added as signals.
    v2.1 (review 313c5a7): the scan extends to the 4 satisfaction_rule branches —
    half the process leaks were found in rule branches (icp 'sebelum',
    beachhead 'melalui', investment_sized 'harga belakangan')."""
    texts = [("definition", entry.get("definition"))]
    obs = entry.get("observability")
    if isinstance(obs, list):
        texts += [(f"observability[{i}]", t) for i, t in enumerate(obs)
                  if isinstance(t, str)]
    rule = entry.get("satisfaction_rule")
    if isinstance(rule, dict):
        for branch in ("sufficient", "partial", "no_decisive",
                       "contradicting"):
            t = rule.get(branch)
            if isinstance(t, str):
                texts.append((f"satisfaction_rule.{branch}", t))
    for field, text in texts:
        if not isinstance(text, str):
            continue
        text = RR9_CANONICAL_PREFIX.sub("", text, count=1)
        # The clitic -nya (memuatnya/memilikinya) = an allowlisted word + clitic,
        # NOT a new word — stemmed before the check (triage 27 Sep, not an
        # allowlist addition):
        def _stative(w: str) -> bool:
            stem = w[:-3] if w.endswith("nya") else w
            return w in RR9_STATE_ALLOWLIST or stem in RR9_STATE_ALLOWLIST
        hits = sorted({m.group(0).lower() for m in ACTION_AFFIX.finditer(text)}
                      - {w for w in (m.group(0).lower()
                                     for m in ACTION_AFFIX.finditer(text))
                         if _stative(w)})
        proses = sorted({m.group(0).lower()
                         for m in RR9_PROCESS_PHRASE.finditer(text)})
        if hits or proses:
            detail = []
            if hits:
                detail.append(f"kata ber-afiks tindakan {hits}")
            if proses:
                detail.append(f"frasa proses {proses}")
            warn(f"{label}.{field}: RR9 SIGNAL (bukan error!) "
                 + " · ".join(detail)
                 + " — kandidat review HOW-leak; reviewer/audit "
                 "= otoritas semantik; entry TETAP valid")


def check_entry(entry, label: str, seen: dict, sources: set[str] | None) -> None:
    if not isinstance(entry, dict):
        err(f"{label}: entry wajib objek")
        return
    # 1. required 5 layers + closed top-level
    missing = ENTRY_LAYERS - set(entry)
    if missing:
        err(f"{label}: 5-lapis §5.1 belum lengkap — hilang {sorted(missing)}")
    # forbidden first (specific message), then unknown key (generic)
    scan_forbidden(entry, label)
    extra = set(entry) - ENTRY_LAYERS
    if extra:
        err(f"{label}: key tak dikenal di top-level {sorted(extra)} — entry "
            f"persis 5 lapisan (RR1: requirement = WHAT saja)")

    # 2. identity: dotted + no status suffix + unique
    rid = entry.get("requirement_id")
    if isinstance(rid, str):
        if not REQ_ID.match(rid):
            err(f"{label}: requirement_id {rid!r} bukan pola dotted "
                f"<domain>.<name> (D2)")
        low = rid.lower()
        for suf in sorted(CONTRACT_SUFFIXES):
            if low.endswith("_" + suf) or low.endswith("." + suf):
                err(f"{label}: requirement_id {rid!r} membawa suffix status "
                    f"'_{suf}' (D2 guardrail — status = epistemic state, "
                    f"bukan identitas; RR2)")
                break
        if rid in seen:
            err(f"{label}: requirement_id {rid!r} DUPLIKAT (sudah dipakai "
                f"entry lain — unique identity)")
        else:
            seen[rid] = label

    # 3. definition + observability shape
    if "definition" in entry and (not isinstance(entry["definition"], str)
                                  or not entry["definition"].strip()):
        err(f"{label}.definition: wajib non-empty string (WHAT)")
    if "observability" in entry:
        obs = entry["observability"]
        if (not isinstance(obs, list) or not obs
                or not all(isinstance(t, str) and t.strip() for t in obs)):
            err(f"{label}.observability: wajib array non-empty string "
                f"(kondisi yang bisa diamati — bukan evidence user)")

    # 4. satisfaction_rule union (RR11)
    if "satisfaction_rule" in entry:
        check_rule(entry["satisfaction_rule"], f"{label}.satisfaction_rule")

    # 5. provenance (D5 KB schema reuse)
    if "provenance" in entry:
        check_provenance(entry["provenance"], f"{label}.provenance", sources)

    # 6. RR9 signal (warning only)
    rr9_signal(entry, label)


def iter_entries(doc, source: str):
    if isinstance(doc, dict) and isinstance(doc.get("entries"), list):
        return doc["entries"]
    if isinstance(doc, dict) and isinstance(doc.get("requirements"), list):
        return doc["requirements"]
    err(f"{source}: wajib punya 'entries' (fixtures) atau 'requirements' "
        f"(registry)")
    return []


def _run(fn, *args) -> tuple[list[str], list[str]]:
    """Run a check with clean global lists → (errors, warnings)."""
    errors.clear()
    warnings.clear()
    fn(*args)
    return list(errors), list(warnings)


def _expect_ok(expect: dict, errs: list[str], warns: list[str]) -> list[str]:
    """SELF-EXPECTING fixture: every expectation must be proven, and every
    actual result must match an expectation (both directions — anti fixture drift)."""
    fails: list[str] = []
    exp_err = expect.get("errors", [])
    if not exp_err:
        if errs:
            fails.append(f"errors padahal ekspektasi bersih: {errs}")
    else:
        for pat in exp_err:
            if not any(pat in e for e in errs):
                fails.append(f"ekspektasi error TIDAK muncul: {pat!r}")
        for e in errs:
            if not any(pat in e for pat in exp_err):
                fails.append(f"error DI LUAR ekspektasi: {e}")
    exp_warn = expect.get("warnings")
    if exp_warn == []:
        if warns:
            fails.append(f"warning padahal ekspektasi bersih: {warns}")
    elif isinstance(exp_warn, list):
        for pat in exp_warn:
            if not any(pat in w for w in warns):
                fails.append(f"ekspektasi warning TIDAK muncul: {pat!r}")
        if "warnings_min" in expect and len(warns) < expect["warnings_min"]:
            fails.append(f"warning < {expect['warnings_min']} "
                         f"(dapat {len(warns)})")
    return fails


def main() -> int:
    schema = load(SCHEMA_PATH)
    failures: list[str] = []

    # A. schema ↔ contract drift (anti silent divergence)
    if schema.get("enums") != CONTRACT_ENUMS:
        for k, v in CONTRACT_ENUMS.items():
            got = (schema.get("enums") or {}).get(k)
            if got != v:
                failures.append(f"SCHEMA DRIFT: enums.{k} = {got}, "
                                f"kontrak = {v}")
    got_f = set((schema.get("forbidden_fields") or {}).get("fields", []))
    if got_f != CONTRACT_FORBIDDEN:
        failures.append(f"SCHEMA DRIFT: forbidden_fields "
                        f"+{sorted(got_f - CONTRACT_FORBIDDEN)} "
                        f"-{sorted(CONTRACT_FORBIDDEN - got_f)}")
    got_s = set((schema.get("banned_id_suffixes") or {}).get("suffixes", []))
    if got_s != CONTRACT_SUFFIXES:
        failures.append(f"SCHEMA DRIFT: banned_id_suffixes "
                        f"+{sorted(got_s - CONTRACT_SUFFIXES)} "
                        f"-{sorted(CONTRACT_SUFFIXES - got_s)}")

    # sources.json (D5 cross-check)
    sources: set[str] | None = None
    if SOURCES_PATH.exists():
        sources = {s["source_id"] for s in load(SOURCES_PATH).get("sources", [])
                   if "source_id" in s}
    else:
        print("WARN  sources.json tidak ditemukan — cross-check source_id DITUNDA")

    # B. main registry (optional until phase 6 — D4 deferred)
    if REGISTRY_FILE.exists():
        def _reg():
            # P1 fix (review e5ad03a): `seen` is REGISTRY-LEVEL — declared
            # ONCE outside the loop, same as the _fx() pattern. An {} literal
            # as an argument is re-evaluated per iteration → duplicate ids once
            # slipped silently through the main registry path (a fixture-harness
            # bug did not catch it because this branch never ran before the file
            # existed).
            seen: dict[str, str] = {}
            for i, e in enumerate(iter_entries(load(REGISTRY_FILE),
                                               REGISTRY_FILE.name)):
                check_entry(e, f"{REGISTRY_FILE.name}[{i}]", seen, sources)
        errs, warns = _run(_reg)
        for w in warns:
            print(f"WARN  {w}")
        for e in errs:
            print(f"ERROR {e}")
        failures += [f"REGISTRY: {e}" for e in errs]
        print(f"REGISTRY {REGISTRY_FILE.name}: {len(errs)} error / "
              f"{len(warns)} warning → {'✓' if not errs else '✗'}")
    else:
        print("WARN  requirement_registry.json belum ada — ENTRIES = tahap 6 "
              "(D4 deferred by design); validator menguji fixtures")

    # C. fixtures SELF-EXPECTING (positive / negative / rr9)
    if not FIXTURES.exists():
        failures.append(f"folder fixtures tidak ada: {FIXTURES}")
        files: list[Path] = []
    else:
        files = sorted(FIXTURES.glob("*.json"))
        if not files:
            failures.append("tidak ada fixture — Tahap 2 butuh "
                            "positive/negative/RR9")
    for f in files:
        doc = load(f)

        def _fx(doc=doc, f=f):
            seen: dict[str, str] = {}
            for i, e in enumerate(iter_entries(doc, f.name)):
                check_entry(e, f"[{i}]", seen, sources)

        errs, warns = _run(_fx)
        for w in warns:
            print(f"WARN  {f.name}: {w}")
        for e in errs:
            print(f"ERROR {f.name}: {e}")
        fails = _expect_ok(doc.get("$expect", {}), errs, warns)
        for x in fails:
            print(f"FAIL  {f.name}: {x}")
        print(f"FIXTURE {f.name}: {len(errs)} error / {len(warns)} warning "
              f"→ {'✓ sesuai ekspektasi' if not fails else '✗ GAGAL'}")
        failures += [f"{f.name}: {x}" for x in fails]

    print()
    if failures:
        for x in failures:
            print(f"GAGAL {x}")
        print(f"requirement registry schema v0.1 — {len(failures)} kegagalan "
              f"→ INVALID ✗")
        return 1
    print("requirement registry schema v0.1 — semua ekspektasi fixture "
          "terpenuhi, drift bersih → VALID ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
