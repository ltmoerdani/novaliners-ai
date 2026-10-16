"""Structural validator — Adjudication Schema v0.1 (Phase 3 step 5).

Contract: internal-docs §6 (FINAL, waves 5-11).
Follows the validate_registry.py pattern: structural ONLY — enforces shape and
locked invariants (AD1-AD10 in adjudication_schema.json); does NOT judge the
semantic quality of mappings (that is the D-A2 model B/C mechanism, not this layer).

Invariants enforced (not invented — their semantics already live in the contract):
  AD1 totality      : no_decisive = complement; all-false rejected
  AD2 exclusivity   : sufficient AND partial = INVALID evaluation -> rejected
  AD3 conflict      : both sides must be complete when conflict
  AD4 resolution    : status consistent with table D-A1b (+ RR11 PARTIAL/mode)
  AD6 ledger        : valid adjudications only, append-only entry shape
  AD7 anomaly       : anomaly shape, separate from the ledger
  AD8 separation    : PROPOSED != VERIFIED != ADJUDICATION (keyed by the absence
                      of verification_method/verified fields in adjudication)
  AD9 D-A2          : verification_method closed enum + verified: bool
  AD10 boundary     : no write-to-state fields (forbidden list)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_SCHEMA_PATH = Path(__file__).resolve().parent / "adjudication_schema.json"

SATISFACTION_STATUS = ("PRESENT", "PARTIAL", "UNKNOWN", "ABSENT")
RULE_MODES = ("BINARY", "PARTIAL")  # RR11 context — MUST be passed in, not stored in the record
VERIFICATION_METHODS = (
    "deterministic_predicate",
    "second_pass_verified",
    "human_reviewed",
)
RULE_BRANCHES = ("sufficient", "partial", "no_decisive", "contradicting")

# AD10 — fields that signal write-to-state / evidence creation (RR8, boundary §6.1)
_FORBIDDEN_FIELDS = frozenset({
    "evidence_new", "evidence_items", "state_write", "state_patch",
    "universal_state", "verified", "verification_method",
})

_SCHEMA: dict[str, Any] | None = None


def load_schema() -> dict[str, Any]:
    global _SCHEMA
    if _SCHEMA is None:
        _SCHEMA = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    return _SCHEMA


class AdjudicationValidationError(ValueError):
    """Structural violation — the message names the invariant (AD*) that was violated."""


def _fail(invariant: str, msg: str) -> None:
    raise AdjudicationValidationError(f"[{invariant}] {msg}")


# ---------------------------------------------------------------- rule_evaluation

def check_rule_evaluation(rev: Any, rule_mode: str | None = None) -> None:
    """AD1 (totality) + AD2 (exclusivity). rule_mode is optional, for the RR11 check."""
    if not isinstance(rev, dict) or set(rev) != set(RULE_BRANCHES):
        got = sorted(rev) if isinstance(rev, dict) else type(rev).__name__
        _fail("AD1", f"rule_evaluation wajib tepat 4 cabang {RULE_BRANCHES}, dapat: {got}")
    if any(not isinstance(rev[b], bool) for b in RULE_BRANCHES):
        _fail("AD1", "keempat nilai cabang wajib boolean")
    s, p, nd, c = (rev[b] for b in RULE_BRANCHES)
    if not (s or p or nd or c):
        _fail("AD1", "all-false DILARANG — totalitas: no_decisive = komplemen definisional")
    if nd and (s or p or c):
        _fail("AD1", "no_decisive=true TEPAT KETIKA sufficient=partial=contradicting=false")
    if s and p:
        # AD2/D-A1c: INVALID evaluation — rejected, NOT resolved by precedence
        _fail("AD2", "sufficient AND partial = INVALID evaluation (D-A1c) — tak boleh muncul sebagai output")
    if rule_mode == "BINARY" and p:
        _fail("RR11", "rule BINARY tidak punya cabang partial — partial=true ilegal")


# ---------------------------------------------------------------- conflict + resolusi

def expected_status(rev: dict[str, bool]) -> str:
    """The D-A1b resolution table (contract §6.3) — a pure function, used by the
    validator to verify the output is consistent with rule_evaluation."""
    s, p, c = rev["sufficient"], rev["partial"], rev["contradicting"]
    conflict = (s or p) and c          # AD3 / D-A1a
    if conflict:
        return "UNKNOWN"               # conflict resolution
    if s:
        return "PRESENT"
    if p:
        return "PARTIAL"
    if c:
        return "ABSENT"                # contradicting WITHOUT competing satisfaction
    return "UNKNOWN"                   # no_decisive (AD1 guarantees this branch)


def check_conflict(rev: dict[str, bool], conflict: Any,
                   evidence_refs: list[str]) -> dict[str, list[str]] | None:
    """AD3 — the conflict object has two sides; must be complete & consistent during conflict."""
    if conflict is None:
        _fail("AD3", "field conflict wajib ada (boleh dua array kosong saat tanpa konflik)")
    if (not isinstance(conflict, dict)
            or set(conflict) != {"present_evidence_refs", "contradicting_evidence_refs"}):
        _fail("AD3", "conflict wajib tepat {present_evidence_refs, contradicting_evidence_refs}")
    if any(not isinstance(conflict[k], list) for k in conflict):
        _fail("AD3", "kedua sisi conflict wajib array")
    s, p, c = rev["sufficient"], rev["partial"], rev["contradicting"]
    conflict_expected = (s or p) and c
    if conflict_expected:
        if not conflict["present_evidence_refs"] or not conflict["contradicting_evidence_refs"]:
            _fail("AD3", "conflict terdeteksi — KEDUA sisi wajib tercatat (record tak auditabel tanpa itu)")
    else:
        if conflict["present_evidence_refs"] and conflict["contradicting_evidence_refs"]:
            _fail("AD3", "kedua sisi terisi padahal tidak ada conflict (D-A1a: conflict = (S∨P)∧C)")
    if conflict_expected:
        # Referential integrity is REQUIRED for ALL conflict cases — 101 and 011.
        # Adversarial review wave-13: the old condition (partial branch only)
        # let case 101 pass without this check; the old test suite never
        # closed the gap because it only tested 011.
        present = set(conflict["present_evidence_refs"])
        if present - set(evidence_refs):
            _fail("AD3", "present_evidence_refs merujuk evidence di luar evidence_refs output")
    return conflict if conflict_expected else None


# ---------------------------------------------------------------- entities

def _check_no_forbidden(obj: Any, path: str) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in _FORBIDDEN_FIELDS:
                _fail("AD10", f"field forbidden '{k}' di {path} — adjudicator "
                      "tidak menulis state/membuat evidence; verified/"
                      "verification_method milik VERIFIED mapping (AD8/AD9)")
            _check_no_forbidden(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _check_no_forbidden(v, f"{path}[{i}]")


def _check_additional_props(entity: str, obj: dict[str, Any]) -> None:
    """`additionalProperties: false` from the schema ENFORCED by the validator —
    wave-13 review: the schema said false but the validator never checked the exact
    key set (e.g. `_rule_mode` slipped into records the schema declared invalid)."""
    props = load_schema()["entities"][entity]["properties"]
    extra = set(obj) - set(props)
    if extra:
        _fail("SCHEMA", f"field tambahan {sorted(extra)} di {entity} — additionalProperties=false")


def check_verified_mapping(vm: Any) -> None:
    """AD9 / D-A2 — closed enum + verified: bool checked HERE (not in the output).
    Structural (option A) = the precondition of ALL paths — called before the
    `verified` gate (wave-13 review: a verified=false object must still be valid)."""
    if not isinstance(vm, dict):
        _fail("AD9", "verified_mapping wajib object")
    _check_additional_props("verified_mapping", vm)
    required = {"requirement_id", "evidence_refs", "verification_method", "verified", "verified_at"}
    missing = required - set(vm)
    if missing:
        _fail("AD9", f"verified_mapping kurang field: {sorted(missing)}")
    if not isinstance(vm["evidence_refs"], list) or not vm["evidence_refs"]:
        _fail("AD9", "verified_mapping.evidence_refs wajib array non-kosong (ref integrity §6.6)")
    if vm["verification_method"] not in VERIFICATION_METHODS:
        _fail("AD9", f"verification_method '{vm['verification_method']}' "
              f"di luar enum tertutup {VERIFICATION_METHODS}")
    if not isinstance(vm["verified"], bool):
        _fail("AD9", "verified wajib boolean")


def check_proposed_mapping(pm: Any) -> None:
    """AD8 — PROPOSED is a separate object WITH complete structure (wave-13
    review: the separate container was right, but it was never validated —
    the schema's required fields were useless without enforcement)."""
    if not isinstance(pm, dict):
        _fail("AD8", "proposed_mapping wajib object")
    _check_additional_props("proposed_mapping", pm)
    missing = {"proposed_by", "requirement_id", "evidence_refs", "proposed_at"} - set(pm)
    if missing:
        _fail("AD8", f"proposed_mapping kurang field: {sorted(missing)}")
    if not isinstance(pm["evidence_refs"], list) or not pm["evidence_refs"]:
        _fail("AD8", "proposed_mapping.evidence_refs wajib array non-kosong")


def check_adjudication_output(out: Any, rule_mode: str | None = None) -> dict[str, Any]:
    """Validate one VALID adjudication: §6.2 + AD1-AD4 + AD8 + AD10.
    `rule_mode` = ARGUMENT (wave-13 review) — the `_rule_mode` field is FORBIDDEN
    in the record (additionalProperties=false; an invalid record must not enter
    the ledger even if the evaluator itself never produces it)."""
    if not isinstance(out, dict):
        _fail("AD", "adjudication output wajib object")
    _check_additional_props("adjudication_output", out)
    _check_no_forbidden(out, "adjudication")
    required = {
        "requirement_id", "status", "rule_evaluation", "evidence_refs",
        "conflict", "evaluation_time", "adjudicated_at",
    }
    missing = required - set(out)
    if missing:
        _fail("AD", f"output kurang field: {sorted(missing)}")
    if out["status"] not in SATISFACTION_STATUS:
        _fail("RR4", f"status '{out['status']}' di luar 4-enum {SATISFACTION_STATUS}")
    check_rule_evaluation(out["rule_evaluation"], rule_mode)
    rev = out["rule_evaluation"]
    expected = expected_status(rev)
    if out["status"] != expected:
        _fail("AD4", f"status {out['status']} tidak konsisten rule_evaluation (harus {expected})")
    if out["status"] == "PARTIAL" and rule_mode is not None and rule_mode != "PARTIAL":
        _fail("RR11", "status PARTIAL hanya legal jika rule.mode = PARTIAL")
    check_conflict(rev, out["conflict"], out["evidence_refs"])
    if rev["sufficient"] and not out["evidence_refs"]:
        _fail("AD", "sufficient=true tanpa evidence_refs — hasil tanpa sitasi tak auditabel")
    return out


def check_ledger_entry(entry: Any, rule_mode: str) -> dict[str, Any]:
    """AD6 — ledger entry: shape + valid adjudications only.

    `rule_mode` is REQUIRED (wave-14 review): ledger revalidation needs the mode
    context for RR11, and the mode is NOT (and must not be) inside the record —
    hence the context is passed as an ARGUMENT from the pipeline caller,
    not a default None that silently disables the check (evidence gap: a
    BINARY record with partial=true passed the ledger without this argument).
    """
    if rule_mode not in RULE_MODES:
        _fail("RR11", f"rule_mode '{rule_mode}' wajib salah satu dari {RULE_MODES} "
              "— tanpa konteks ini RR11 tak bisa diverifikasi")
    # R1-remediation Probe A (17 Oct): the envelope may carry an optional `goal_id` —
    # business-context scope lives at the ROW level (not inside the adjudication), the
    # same pattern as route_execution carrying session_id at the row level. Rows
    # WITHOUT goal_id = legacy data — still valid & readable (historical compatibility;
    # the cross-context visibility policy lives in the reader, _latest_entries).
    if not isinstance(entry, dict) or set(entry) not in (
            {"entry_id", "adjudication"}, {"entry_id", "adjudication", "goal_id"}):
        _fail("AD6", "ledger entry wajib tepat {entry_id, adjudication} "
                     "atau {entry_id, adjudication, goal_id}")
    gid = entry.get("goal_id")
    if gid is not None and (not isinstance(gid, str) or not gid):
        _fail("AD6", "goal_id (bila ada) wajib string non-kosong")
    if not isinstance(entry["entry_id"], str) or not entry["entry_id"]:
        _fail("AD6", "entry_id wajib string non-kosong")
    check_adjudication_output(entry["adjudication"], rule_mode=rule_mode)
    return entry


def check_evaluation_anomaly(anom: Any) -> dict[str, Any]:
    """AD7 / D-A1d — the anomaly channel (not the ledger): minimal shape + forbidden to carry a result."""
    if not isinstance(anom, dict):
        _fail("AD7", "evaluation anomaly wajib object")
    required = {"anomaly_id", "requirement_id", "reason", "detected_at"}
    missing = required - set(anom)
    if missing:
        _fail("AD7", f"anomaly kurang field: {sorted(missing)}")
    forbidden = set(anom) & {"status", "rule_evaluation", "conflict", "adjudication"}
    if forbidden:
        _fail("AD7", f"anomaly DILARANG membawa field hasil: {sorted(forbidden)} "
              "— anomaly bukan adjudication result")
    _check_additional_props("evaluation_anomaly", anom)
    _check_no_forbidden(anom, "anomaly")
    return anom


def check_full_record(record: Any, rule_mode: str) -> dict[str, Any]:
    """AD8 — Phase 3 acceptance criterion: a full record must hold THREE SEPARATE
    objects (proposed_mapping, verified_mapping, adjudication). Mixed into
    one object = Phase 3 not finished. `rule_mode` is REQUIRED — the RR11
    context is passed in by the caller (see check_ledger_entry)."""
    if not isinstance(record, dict):
        _fail("AD8", "full record wajib object")
    for key, checker in (
        ("proposed_mapping", check_proposed_mapping),
        ("verified_mapping", check_verified_mapping),
        ("adjudication", None),
    ):
        if key not in record or not isinstance(record[key], dict):
            _fail("AD8", f"record wajib memuat objek terpisah '{key}'")
        if checker:
            checker(record[key])
    check_adjudication_output(record["adjudication"], rule_mode=rule_mode)
    return record


def validate_file(path: str | Path, rule_modes: dict[str, str]) -> list[dict[str, Any]]:
    """Validate a JSONL of ledger_entry / evaluation_anomaly / full records.

    `rule_modes`: requirement_id → mode (from the registry, the satisfaction_rule field).
    MUST be provided by the caller (wave-14 review) — an adjudication record whose
    requirement_id is NOT in the mapping is REJECTED, not silently passed
    without the RR11 check. Returns the list of valid records; raises on the first violation.
    """
    records: list[dict[str, Any]] = []

    def _mode_for(obj: dict[str, Any]) -> str:
        rid = obj.get("requirement_id") or obj["adjudication"]["requirement_id"]
        mode = rule_modes.get(rid)
        if mode not in RULE_MODES:
            _fail("RR11", f"rule_mode untuk requirement '{rid}' tidak diketahui — RR11 butuh konteks mode")
        return mode

    for i, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            _fail("AD", f"baris {i + 1}: JSON tidak valid ({exc})")
        if "adjudication" in obj and "verified_mapping" in obj:
            check_full_record(obj, rule_mode=_mode_for(obj))
        elif "entry_id" in obj:
            check_ledger_entry(obj, rule_mode=_mode_for(obj))
        elif "anomaly_id" in obj:
            check_evaluation_anomaly(obj)
        else:
            check_adjudication_output(obj, rule_mode=_mode_for(obj))
        records.append(obj)
    return records
