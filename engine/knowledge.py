"""Knowledge loader — RDKL phase 3 (docs/knowledge/schema/knowledge-schema-v0.1.md).

Loads the machine-readable knowledge base from mvp/ontology/knowledge/ and
provides validated access for the engine:

- get_kb()              → the whole KB (probes/rules/anti_patterns/interventions/sources)
- active_rule_sources() → rule sources active for diagnosis (AC-01), from `rule_activation.json`
- interventions_for()   → KB interventions per constraint (NEXT BEST ACTION grounding)

M5 (doc 14 §26): the interview-phase concept no longer exists in this module. Per-phase probes,
interview prompt hints, and per-phase rule-source gating were removed together with the phased
interview engine. Rule-source activation is a knowledge mechanism (one list for the whole ledger),
declared in `rule_activation.json`; this module is only a generic loader — no source prefix is
written in code.

Load-time validation runs once (fail-fast): item without provenance / duplicate ID /
unknown constraint = ERROR, not a warning (internal-docs §2 — provenance
mandatory).
"""
from __future__ import annotations

import json
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

from core.schema.rule_activation import RuleActivation
from store import nba as nba_store

KB_DIR = Path(__file__).resolve().parent.parent / "ontology" / "knowledge"

ACTIVATION_FILE = KB_DIR / "rule_activation.json"


def code_commit_hash() -> str:
    """HEAD commit at process start — anti-stale (18 Sep 2026 incident:
    a live artifact was produced by a process started 6 hours BEFORE the era-7 fix commit).
    """
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(KB_DIR.parent.parent),
            capture_output=True, text=True, timeout=3,
        ).stdout.strip() or "unknown"
    except Exception:
        return "unknown"


@lru_cache(maxsize=1)
def kb_sha256() -> str:
    """Deterministic hash of the whole KB — SEMANTICALLY IDENTICAL to
    evals/test_artifact_integrity.kb_fingerprint()["sha256"] (paths relative to mvp/,
    sorted, name-bytes + raw-bytes) so the artifact value == the eval-gate value.
    """
    import glob
    import hashlib

    h = hashlib.sha256()
    root = str(KB_DIR.parent.parent)
    for p in sorted(glob.glob(str(KB_DIR / "*.json"))):
        path = Path(p)
        h.update(str(path.relative_to(root)).encode())
        h.update(path.read_bytes())
    return h.hexdigest()[:16]


@lru_cache(maxsize=1)
def _load_activation() -> RuleActivation:
    """Active rule-source declaration. Fail-fast when malformed.

    Shape is validated by the typed contract `RuleActivation` (`core/schema/rule_activation.py`). REFERENCE
    validation (source prefixes registered in sources.json) runs in validate_knowledge.py."""
    data = json.loads(ACTIVATION_FILE.read_text(encoding="utf-8"))
    return RuleActivation.model_validate(data)


def _run_validator() -> None:
    """Fail-fast: run validate_knowledge.py at load time. Exit != 0 = raise."""
    result = subprocess.run(
        [sys.executable, str(KB_DIR / "validate_knowledge.py")],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Knowledge base INVALID — tolak load (provenance mandatory, internal-docs §2):\n"
            f"{result.stdout}{result.stderr}"
        )


@lru_cache(maxsize=1)
def _load_kb() -> dict:
    _run_validator()
    # B1b (internal-docs §364 — "lifecycle exists, the trigger does not yet"): CHALLENGED
    # items are rules/probes UNDER contestation (contradiction not yet adjudicated) —
    # frozen out of the runtime, still visible to the validator & md compilation.
    # Trigger: a human/curator sets lifecycle=CHALLENGED + the `challenge` field.
    def _live(item: dict) -> bool:
        return item.get("lifecycle") != "CHALLENGED"

    kb: dict = {"probes": {}, "rules": {}, "anti_patterns": {}, "interventions": {}, "sources": {}}
    for f in sorted(KB_DIR.glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        for p in data.get("probes", []):
            if _live(p):
                kb["probes"][p["probe_id"]] = p
        for r in data.get("evidence_rules", []):
            if _live(r):
                kb["rules"][r["rule_id"]] = r
        for a in data.get("anti_patterns", []):
            if _live(a):
                kb["anti_patterns"][a["pattern_id"]] = a
        for i in data.get("interventions", []):
            if _live(i):
                kb["interventions"][i["intervention_id"]] = i
        for s in data.get("sources", []):
            kb["sources"][s["source_id"]] = s
    return kb


@lru_cache(maxsize=1)
def rubric_lines() -> dict[str, str]:
    """Compiled rubric lines per rule_id (compiled_rubrics.json — Phase 1,
    internal-docs §5.1).

    Empty when the file has not been compiled — consumers MUST keep a verbose fallback.
    """
    f = KB_DIR / "compiled_rubrics.json"
    if not f.exists():
        return {}
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        return dict(data.get("rubric_lines") or {})
    except Exception:
        return {}


_GRADE_RANK = {"empirical_research": 0, "practitioner_playbook": 1, "conceptual_framework": 2}


@lru_cache(maxsize=1)
def source_grades() -> dict[str, int]:
    """Authority rank per source_id (Phase 3, internal-docs §6.2e) — the smaller,
    the more authoritative. A source without a grade in sources.json = lowest rank (9)."""
    try:
        raw = json.loads((KB_DIR / "sources.json").read_text(encoding="utf-8"))
        return {
            s["source_id"]: _GRADE_RANK.get(s.get("authority_grade"), 9)
            for s in raw.get("sources", [])
        }
    except Exception:
        return {}


def active_rule_sources() -> set[str]:
    """Rule-source prefixes active for diagnosis (AC-01).

    Diagnosis weighs the whole ledger, so one list applies to every call
    (including HK/Retention, internal-docs §8.5 finding #2). Returns a COPY, not the
    declaration object: callers must not be able to mutate the activation config at runtime."""
    return set(_load_activation().active_rule_sources)


def get_kb() -> dict:
    """Full KB access (probes/rules/anti_patterns/interventions/sources) for
    reasoning traces — returns a dict reference; do not mutate it."""
    return _load_kb()


# ---------------------------------------------------------------------------
# WP3 (internal-docs §2.10): interventions & anti-patterns → decision layer.
# Previously 16 interventions + 17 anti-patterns were loaded & validated but
# NEVER consumed. Now: lookup by constraint.
# ---------------------------------------------------------------------------

def interventions_for(constraint_id: str, e2e_phases: list[str] | None = None) -> list[dict]:
    """KB interventions for a given constraint (NEXT BEST ACTION grounding).

    Each item carries expected_evidence — honoring the principle in internal-docs §6.2 #11
    ("We'll know we're right when…" required on every prescription).

    P3 (internal-docs §10.8): the knowledge-confidence overlay from real outcomes
    (store/nba.py::recalc) lowers/raises ordering within the constraint —
    interventions with good field outcomes are surfaced first; without the
    overlay everything still shows (safe degradation, neutral 0.5).

    J4 (internal-docs §7): e2e_phases (PRA_SALES|SALES|AFTER_SALES, the output of
    infer_e2e_phases on RevenueState) filters out interventions irrelevant to
    the user's position in the journey. Safe degradation: no filter / items
    without an e2e_phase tag → still shown.
    """
    kb = _load_kb()
    items = [
        i for i in kb["interventions"].values()
        if constraint_id in (i.get("targets") or i.get("constraint_targets") or [])
    ]
    if e2e_phases:
        _phases = {p.upper() for p in e2e_phases}
        items = [
            i for i in items
            if not i.get("e2e_phase")
            or _phases & {p.upper() for p in i["e2e_phase"]}
        ]
    overlay = nba_store.load_confidence()
    if not overlay:
        return items
    grades = nba_store.load_grades()
    out = []
    for i in items:
        iid = i["intervention_id"]
        row = {**i, "confidence": overlay.get(iid, 0.5)}
        if iid in grades:
            # J6/K7 (internal-docs §10): interventions with real outcomes gain grade —
            # an overlay field (the frozen KB is untouched, guarded by test_knowledge_sync).
            row["confidence_grade"] = grades[iid]
        out.append(row)
    out.sort(key=lambda i: -i["confidence"])
    return out
