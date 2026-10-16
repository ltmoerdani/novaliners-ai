"""Candidate Path Evaluator — deterministic decisions over candidates: which survive as Possible Paths.

Judges THREE things that must never be merged (internal-docs §Axes):
  Applicability  — the strategy's `not_applicable_when` against verified state (NOT_APPLICABLE = dropped,
                   reason recorded; UNKNOWN = survives but the exclusion is not settled)
  Feasibility    — from `checks` (SUPPORTED | CONDITIONAL | CONTRADICTED | UNDETERMINED)
  Lifecycle      — process decisions/states arriving from outside (e.g. the user stops a path)

A CONTRADICTED candidate still SURVIVES: the map must show the way that is wrong for now, with its reasons
(a do-not is a navigation state). The origin split is kept in `stop_provenance`: an engine finding (ENGINE_
CONTRADICTION) is not the same as a process decision (LIFECYCLE).

Paths are NEVER formed from a fixed list: only candidates born from the generator are evaluated.
Output = a PathSet: 0..N paths, with `generation` (full audit) and `unresolved` (reasons when 0)."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable

from core.navigation.candidate import (
    candidate_block,
    possibility_audit,
    promote_possibilities,
    with_mechanisms,
)
from core.navigation.contracts import (
    KNOWLEDGE_NAMESPACES,
    Applicability,
    Feasibility,
    Lifecycle,
    PossibilitySpace,
    SignalReader,
    candidate_id_for,
    display_status,
    feasibility_basis,
    feasibility_from_checks,
    grounded,
    path_id_for,
    signal_namespace,
)
from core.navigation.generator import (
    Candidate,
    CandidateSet,
    _reason_row,
    split_support,
    unresolved_reasons,
)
from core.navigation.predicate import evaluate

# v3 (provenance hardening): `rule:` signals carry real evidence anchors (PROV-01..04), routes are composed
# per strategy, and legacy artifacts are flagged LEGACY (assess_path_set). v2 = active rules without
# evidence_refs.
PATHSET_VERSION = 3

Advisor = Callable[[dict[str, Any]], "str | dict[str, str]"]


def _check_row(spec, reader: SignalReader, ledger_state_of=None) -> dict[str, Any]:
    sig = reader(spec.signal)
    signal_state = "PRESENT" if sig.value is True else ("ABSENT" if sig.value is False else "UNKNOWN")
    state = signal_state
    merged_note: list[str] | None = None
    conflict: dict[str, Any] | None = None
    # S3 (int 20): the adjudication ledger is AUTHORITATIVE over checks anchored to a requirement_id, using
    # the SAME merge rule as Readiness/requirement_state.merge_readings — not a second evaluator.
    # A definite state beats UNKNOWN; a mismatch = a structured dispute (not ABSENT).
    # Without ledger_state_of (default) legacy behavior is UNCHANGED; state_signal keeps the raw reading so
    # Readiness conflict metadata stays intact.
    if ledger_state_of is not None and spec.requirement_id:
        # local import: requirement_state pulls applicability -> compat -> evaluator (import cycle), so
        # merge_readings is loaded at call time, not at module import.
        from core.navigation.requirement_state import merge_readings

        primary = str(ledger_state_of(spec.requirement_id) or "UNKNOWN")
        merged, bad = merge_readings(primary, [signal_state])
        if merged != signal_state:
            state = merged
            merged_note = ["ledger", "check"]
        if bad:
            merged_note = sorted(set(merged_note or ["check"]) | {"ledger"})
            conflict = {
                "requirement_id": spec.requirement_id,
                "sources": {"ledger": primary, "check": signal_state},
                "authority": "ledger",
                "resolution": "AUTHORITY",
                "resolved_to": state,
            }
    i18n: dict[str, dict[str, str]] = {lang: dict(v) for lang, v in (spec.i18n or {}).items()}
    for lang, text in (sig.i18n or {}).items():
        i18n.setdefault(lang, {})["reason"] = text
    row = {
        "i18n": i18n,
        "check_id": spec.check_id,
        "title": spec.title,
        "requirement_id": spec.requirement_id,
        "state": state,
        "kind": spec.kind,
        "reason": sig.reason,
        "unlock": spec.unlock,
        "refs": list(sig.refs),
    }
    # Audit fields appear ONLY when the ledger actually changed the reading. The default shape (no ledger)
    # is unchanged -> deterministic fixtures/goldens stay intact (backward-compatible).
    if merged_note is not None:
        row["state_signal"] = signal_state
        row["sources"] = merged_note
    if conflict is not None:
        row["conflict"] = conflict
    return row


def _stop_provenance(feasibility: Feasibility, checks: list[dict], life: dict | None) -> list[dict]:
    out: list[dict] = []
    if feasibility == Feasibility.CONTRADICTED:
        out.append(
            {
                "source": "ENGINE_CONTRADICTION",
                "checks": [c["check_id"] for c in checks if c["state"] == "ABSENT" and c["kind"] == "hard"],
            }
        )
    if life and life.get("state") in (Lifecycle.STOPPED, Lifecycle.CLOSED):
        out.append(
            {
                "source": "LIFECYCLE",
                "state": str(life["state"]),
                "cause": life.get("cause", ""),
                "cause_i18n": life.get("cause_i18n") or {},
                "origin": life.get("origin", ""),
            }
        )
    return out


def apply_lifecycle(path: dict[str, Any], life: dict | None) -> dict[str, Any]:
    """Path + current lifecycle -> a copy with the status word and STOP origin recomputed.

    Feasibility (an engine finding) is UNCHANGED; lifecycle (a process decision) is laid on top of it. Used
    when a path is formed and when the projection is read (the user can stop a path between two diagnoses)."""
    life = life or {"state": Lifecycle.OPEN}
    state = Lifecycle(life.get("state", Lifecycle.OPEN))
    out = dict(path)
    out["lifecycle"] = str(state)
    out["status"] = display_status(path["feasibility"], state)
    out["stop_provenance"] = _stop_provenance(
        Feasibility(path["feasibility"]), path["checks"], {**life, "state": state}
    )
    return out


def evaluate_candidate(
    cand: Candidate,
    reader: SignalReader,
    *,
    lifecycle: dict | None = None,
    available_templates: set[str] | None = None,
    advise: Advisor | None = None,
    ledger_state_of: Any = None,
) -> tuple[dict | None, dict | None]:
    """One candidate -> (a PossiblePath dict | None, a rejection note | None).

    ledger_state_of (optional) = the adjudicated requirement state reader (Requirement State Reader). When
    given, checks anchored to a requirement_id use the ledger state (authoritative), merged through
    merge_readings — one rule with Readiness, not a second evaluator."""
    reader = grounded(reader)
    strat = cand.strategy
    applicability = Applicability.APPLIES
    excl_missing: list[str] = []
    if strat.not_applicable_when:
        ex = evaluate(strat.not_applicable_when, reader)
        if ex.value is True:
            return None, {
                "strategy_id": strat.strategy_id,
                "reason": "NOT_APPLICABLE",
                "rule": strat.not_applicable_when,
            }
        if ex.value is None:
            applicability = Applicability.UNKNOWN
            excl_missing = [sid for sid in dict.fromkeys(ex.seen) if reader(sid).value is None]

    checks = [_check_row(c, reader, ledger_state_of) for c in strat.checks]
    # A ledger-vs-check dispute must NOT raise feasibility (SUPPORTED/OPEN) or drop it (CONTRADICTED/STOP):
    # conflicting conditions contribute UNKNOWN — the SAME rule as canonical_feasibility (readiness); not a
    # second evaluator, just one feasibility formula.
    conflicted = {c["requirement_id"] for c in checks if c.get("conflict")}
    feas_checks = ([dict(c, state="UNKNOWN") if c.get("requirement_id") in conflicted else c
                    for c in checks] if conflicted else checks)
    feas = feasibility_from_checks(feas_checks, unconditional=strat.no_preconditions)
    templates = [
        t for t in strat.route_template_ids if available_templates is None or t in available_templates
    ]
    prov = split_support(cand.support)
    path = {
        "path_id": cand.path_id,
        "strategy_id": strat.strategy_id,
        "motion": strat.motion,  # domain primitive information — NOT an identity
        "title": strat.title,
        "basis": strat.basis,
        "presentation": strat.presentation,
        "applicability": str(applicability),
        "feasibility": str(feas),
        "feasibility_basis": feasibility_basis(len(checks), strat.no_preconditions),
        "lifecycle": str(Lifecycle.OPEN),
        "status": "",
        "stop_provenance": [],
        "checks": checks,
        "unlock_conditions": [c["unlock"] for c in checks if c["state"] != "PRESENT" and c["unlock"]],
        "missing_evidence": (
            [{"check_id": c["check_id"], "need": c["unlock"]} for c in checks if c["state"] == "UNKNOWN"]
            + [{"check_id": f"applicability:{sid}", "need": ""} for sid in excl_missing]
        ),
        "advisory": "",
        "provenance": {
            **prov,
            "support": cand.support,
            "strategy_id": strat.strategy_id,
            "motion": strat.motion,
            "route_template_ids": templates,
            "knowledge_sources": list(strat.knowledge_sources),
            "emerges_when": strat.emerges_when,
        },
        "route_substrate": {"template_ids": templates, "available": bool(templates)},
    }
    block = candidate_block(cand)
    if block is not None:  # INV-14: candidate provenance survives promotion into a path
        path["provenance"]["candidate"] = block
    path = apply_lifecycle(path, lifecycle)
    if advise is not None:
        adv = advise(path) or ""
        if isinstance(adv, dict):  # {language: text}; "id" = the machine language
            path["advisory"] = adv.get("id", "")
            path["advisory_i18n"] = {k: v for k, v in adv.items() if k != "id" and v}
        else:
            path["advisory"] = adv
    return path, None


def evaluate_candidates(
    cset: CandidateSet,
    space: PossibilitySpace,
    reader: SignalReader,
    *,
    lifecycles: dict[str, dict] | None = None,
    available_templates: set[str] | None = None,
    advise: Advisor | None = None,
    ledger_state_of: Any = None,
) -> dict[str, Any]:
    """CandidateSet -> PathSet (a JSON-ready dict). Path order = the space's declaration order,
    deterministic."""
    reader = with_mechanisms(space, grounded(reader))
    # SUPPORTED candidates from the mechanism layer enter the SAME evaluation pipeline (INV-12).
    evaluable = promote_possibilities(cset, space)
    paths: list[dict] = []
    rejected: list[dict] = []
    for cand in evaluable:
        path, rej = evaluate_candidate(
            cand,
            reader,
            lifecycle=(lifecycles or {}).get(cand.path_id),
            available_templates=available_templates,
            advise=advise,
            ledger_state_of=ledger_state_of,
        )
        if path is not None:
            paths.append(path)
        elif rej is not None:
            rejected.append(rej)
    result = {
        "version": PATHSET_VERSION,
        "space_id": space.space_id,
        "paths": paths,
        "generation": {
            "considered": cset.considered,
            "emerged": [c.strategy.strategy_id for c in evaluable],
            "not_emergent": cset.not_emergent,
            "undetermined": cset.undetermined,
            "rejected": rejected,
            "unsupported_knowledge": cset.unsupported,
        },
        "unresolved": [],
    }
    audit_rows = possibility_audit(
        cset, paths, rejected
    )  # the proposals' fate: path / rejected / conflicted / sign
    if audit_rows:
        result["generation"]["possibilities"] = audit_rows
    if cset.mechanisms:
        result["generation"]["mechanisms"] = cset.mechanisms
    if not paths:
        reasons = unresolved_reasons(replace(cset, candidates=evaluable))
        if not reasons and rejected:
            reasons = [_reason_row("ALL_CANDIDATES_NOT_APPLICABLE")]
        result["unresolved"] = reasons
    validate_path_set(result)
    return result


def _validate_provenance(pid: str, prov: dict[str, Any]) -> None:
    """PROV-01..03: support from knowledge must be anchored; provenance stores the strategy + substrate."""
    for row in prov["support"]:
        if signal_namespace(row["signal"]) in KNOWLEDGE_NAMESPACES and not row.get("refs"):
            raise ValueError(f"path {pid}: dukungan {row['signal']!r} dari knowledge tanpa anchor (PROV-01)")
    rule_ids = set(prov.get("knowledge_ids") or [])
    supported_rules = {k["rule_id"] for k in prov.get("knowledge_support") or []}
    if rule_ids != supported_rules:
        raise ValueError(f"path {pid}: knowledge_ids {sorted(rule_ids)} tidak sama dengan knowledge_support")
    for k in prov.get("knowledge_support") or []:
        if not (k.get("evidence_ids") or k.get("transcript_anchors")):
            raise ValueError(f"path {pid}: rule {k['rule_id']!r} tanpa anchor (PROV-02)")
    for key in ("strategy_id", "route_template_ids", "support"):
        if key not in prov:
            raise ValueError(f"path {pid}: provenance kehilangan {key!r} (PROV-03)")
    cand = prov.get("candidate")
    if cand is not None:  # CAND-02/06: a mechanism-born candidate must be anchored down to evidence
        if cand.get("candidate_id") != candidate_id_for(prov["strategy_id"]):
            raise ValueError(f"path {pid}: candidate_id tidak kanonik terhadap strategi (CAND-06)")
        if not cand.get("mechanism_ids"):
            raise ValueError(f"path {pid}: kandidat tanpa mekanisme penyebab (CAND-02)")
        if not (cand.get("evidence_ids") or cand.get("transcript_anchors")):
            raise ValueError(f"path {pid}: kandidat tanpa anchor evidence (CAND-02)")


def validate_path_set(ps: dict[str, Any]) -> None:
    """PathSet invariants — invoked at the formation boundary. ValueError = an engine bug, not user data."""
    seen: set[str] = set()
    for p in ps.get("paths", []):
        pid = p["path_id"]
        if pid in seen:
            raise ValueError(f"path_id duplikat: {pid}")
        seen.add(pid)
        if pid != path_id_for(p["strategy_id"]):
            raise ValueError(f"path_id {pid!r} tidak diturunkan dari strategi {p['strategy_id']!r}")
        prov = p.get("provenance") or {}
        if not prov.get("support"):
            raise ValueError(f"path {pid} tanpa provenance dukungan — tidak boleh ada path tanpa dasar")
        _validate_provenance(pid, prov)
        if p["status"] not in ("OPEN", "TEST_FIRST", "NOT_YET", "STOP"):
            raise ValueError(f"path {pid}: status {p['status']!r} tidak sah")
    if not ps.get("paths") and not ps.get("unresolved"):
        raise ValueError("nol path harus menyertakan alasan `unresolved` yang eksplisit")


def build_path_set(space: PossibilitySpace, reader: SignalReader, **kw: Any) -> dict[str, Any]:
    """Generator + evaluator in one call (the two steps stay separate inside it)."""
    from core.navigation.generator import generate_candidates

    return evaluate_candidates(generate_candidates(space, reader), space, reader, **kw)
