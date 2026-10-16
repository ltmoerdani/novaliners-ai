"""Domain pack loader — manifest + lexicon (P5a, internal-docs §9).

The only place the engine may learn a domain's *identity*: constraint prefixes
(D1..L8), upstream order, reversibility weights, and the systemic-risk rule. All
declarations live in `ontology/domain_pack.json`; this module evaluates them
GENERICALLY — no domain prefix is written in code.

Rationale: internal-docs §3.4 flagged `if cid.startswith("L8")` in
`core/stages/confidence.py` as S1 — "domain rules in the engine layer". After P5a the generic layer knows
*shapes* (prefix, order, weights), not the revenue domain.

Pre-image of `core/registry.py` + `domains/<id>/pack.json` (F1, internal-docs §4).

Phase B / P0.4: the manifest is validated against the TYPED contract `DomainPackManifest`
(`core/schema/domain.py`) — no longer a loose dict + manual validation. A foreign value
(e.g. a new `op`) = ValidationError at load, not an `if` a human must remember.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from core.schema.domain import DomainPackManifest, MechanismCatalog, UnmappedDistributionNote

PACK_PATH = Path(__file__).resolve().parent.parent / "ontology" / "domain_pack.json"
CONSTRAINTS_PATH = PACK_PATH.parent / "constraints.json"

# Lexicon resolution: PER-DOMAIN (`constraint_id.split('.')[0]`). Historically the code
# took the first 2 letters, so 3-letter domains (DS4, DM5) never matched and
# silently fell back to defaults — see `$resolved_legacy_gap` in domain_pack.json
# (closed in the Phase D contract, internal-docs §9).

@lru_cache(maxsize=1)
def load_pack() -> DomainPackManifest:
    """Read + validate the manifest once (fail-fast, same pattern as the KB loader).

    Two layers of guarding:
    1. SHAPE — `DomainPackManifest.model_validate` (pydantic). Malformed → ValidationError.
    2. COMPLETENESS — `_assert_lexicon_total`: every prefix used by
       `ontology/constraints.json` MUST have a lexicon entry (and idle
       entries are not allowed).

    Layer 2 closes the ROOT of findings F1/F4: a lookup miss used to fall
    silently to a default value, so a scoring factor could die without a trace — exactly
    the "confidence theater" banned by the locked principle internal-docs §6.2 #4. Research:
    fail-fast systems check the immutable initial configuration AT startup;
    parse-don't-validate makes illegal states unrepresentable.
    """
    data = json.loads(PACK_PATH.read_text(encoding="utf-8"))
    manifest = DomainPackManifest.model_validate(data)
    _assert_lexicon_total(
        declared={d.prefix for d in manifest.constraint_domains},
        used=set(_ontology_prefixes()),
    )
    return manifest


@lru_cache(maxsize=1)
def _ontology_prefixes() -> frozenset[str]:
    """Domain prefixes ACTUALLY used by the ontology (measured, not assumed)."""
    data = json.loads(CONSTRAINTS_PATH.read_text(encoding="utf-8"))
    return frozenset(cid.split(".", 1)[0] for cid in data["constraints"])


def _assert_lexicon_total(declared: set[str], used: set[str]) -> None:
    """Fail-fast when the lexicon does not cover the ontology — or vice versa.

    Pure function so it can be tested without touching files.
    """
    missing, unused = sorted(used - declared), sorted(declared - used)
    if missing or unused:
        raise RuntimeError(
            "lexicon domain TIDAK TOTAL — "
            f"ontology memakai {len(used)} prefix, lexicon mendeklarasikan {len(declared)}. "
            f"tanpa entri lexicon: {missing or '—'}; entri menganggur: {unused or '—'}. "
            "Setiap constraint baru di ontology/constraints.json WAJIB punya entri di "
            "ontology/domain_pack.json — jangan biarkan lookup jatuh ke default senyap."
        )


def pack_id() -> str:
    return load_pack().pack_id


def pack_version() -> str:
    return load_pack().version


def domains() -> list:
    """Domain lexicon sorted upstream (most upstream first)."""
    return sorted(load_pack().constraint_domains, key=lambda d: d.upstream_order)


def domain_order() -> list[str]:
    """Domain prefixes in upstream-ness order."""
    return load_pack().domain_order()


MECHANISMS_PATH = PACK_PATH.parent / "mechanisms.json"


@lru_cache(maxsize=1)
def load_mechanisms() -> MechanismCatalog:
    """Read + validate the pack's mechanism catalog (Phase F, internal-docs §9).

    Two layers of guarding, same pattern as the lexicon:
    1. SHAPE — `MechanismCatalog.model_validate` (pydantic) + unique ids.
    2. REFERENCE — every constraint a mechanism references MUST exist in
       `ontology/constraints.json`. Without this, a mechanism could support a
       nonexistent constraint and grant a bonus to a vacuum.
    """
    data = json.loads(MECHANISMS_PATH.read_text(encoding="utf-8"))
    catalog = MechanismCatalog.model_validate(data)
    _assert_mechanism_constraints_known(
        used={c for m in catalog.mechanisms for c in m.constraints},
        known=set(ontology_constraint_ids()),
    )
    return catalog


@lru_cache(maxsize=1)
def ontology_constraint_ids() -> frozenset[str]:
    """Constraint IDs that actually exist in the ontology (measured, not assumed)."""
    data = json.loads(CONSTRAINTS_PATH.read_text(encoding="utf-8"))
    return frozenset(data["constraints"])


def _assert_mechanism_constraints_known(used: set[str], known: set[str]) -> None:
    """Fail-fast when a mechanism references a constraint outside the ontology (pure function)."""
    unknown = sorted(used - known)
    if unknown:
        raise RuntimeError(
            f"mechanisms.json merujuk constraint yang TIDAK ADA di ontology: {unknown}. "
            "Setiap constraint mekanisme harus terdaftar di ontology/constraints.json."
        )


def mechanisms() -> dict[str, dict]:
    """Mechanism catalog in the shape the engine consumes (id → name/description/constraints)."""
    return load_mechanisms().as_engine_map()


def mechanism_signals() -> dict[str, tuple[str, ...]]:
    """Keyword signals per mechanism (deterministic, no LLM)."""
    return load_mechanisms().signal_map()


def evidence_markers():
    """Lexicon phrase table for evidence classification (occurrence vs historical contrast).

    Phase E: the domain word table moved from `core/stages/confidence.py` into the pack — the
    generic layer must not store domain vocabulary.
    """
    return load_pack().evidence_markers


def material_gap_keywords() -> tuple[str, ...]:
    """MATERIAL gap vocabulary (P2) — Phase J: moved from MATERIAL_GAP_KEYWORDS in confidence.py."""
    return tuple(load_pack().material_gap_keywords)


def unmapped_distribution_note() -> UnmappedDistributionNote:
    """Distribution signal + issuing domains of the E5 note — Phase J: moved out of confidence.py."""
    return load_pack().unmapped_distribution_note


def upstream_rank(constraint_id: str) -> int:
    """The constraint's upstream-ness position; smaller = more upstream.

    On a tie → the more upstream one wins (root bottleneck furthest upstream).
    Constraints outside the lexicon get the last rank.
    """
    order = domain_order()
    for i, prefix in enumerate(order):
        if constraint_id.startswith(prefix):
            return i
    return len(order)


# ---------------------------------------------------------------------------
# Lexicon resolution — one rule, no modes (mode + seam shadows removed in the
# Phase D contract per the retire-flag discipline: never leave two live paths).
# ---------------------------------------------------------------------------


def _domain_of(constraint_id: str) -> str:
    """Domain prefix of a constraint ID (`'DM5.1'` → `'DM5'`).

    The single lexicon-resolution rule.
    """
    return constraint_id.split(".", 1)[0]


@lru_cache(maxsize=1)
def _reversibility_by_prefix() -> dict[str, float]:
    # Key = FULL prefix — mirrors the pre-P5a table as-is. What differed between
    # modes was only the LOOKUP KEY (`_lookup_key`), not the table's shape.
    return {d.prefix: d.reversibility for d in domains()}


@lru_cache(maxsize=1)
def _decision_priority_prefixes() -> frozenset[str]:
    return frozenset(d.prefix for d in domains() if d.decision_priority)


@lru_cache(maxsize=1)
def _experiment_priority_prefixes() -> frozenset[str]:
    return frozenset(d.prefix for d in domains() if d.experiment_priority)


def reversibility_weight(constraint_id: str) -> float:
    """How quickly the user themselves can fix this constraint (1.0 = today).

    The per-domain `reversibility` declaration (the owner's PRIMARY 6-factor formula,
    internal-docs §4) now ACTUALLY applies — lexicon completeness is guaranteed at load.
    """
    return _reversibility_by_prefix().get(_domain_of(constraint_id), 1.0)


def has_decision_priority(constraint_id: str) -> bool:
    """True when the constraint touches decision numbers (full relevance, not 0.8)."""
    return _domain_of(constraint_id) in _decision_priority_prefixes()


def has_experiment_priority(constraint_id: str) -> bool:
    """True when a test for this constraint is fast & informative (experiment_confidence).

    Phase D: the `("C6", "DS4", "V2")` tuple once hardcoded in `confidence.py`
    moved into the lexicon pack (`experiment_priority`).
    """
    return _domain_of(constraint_id) in _experiment_priority_prefixes()


@lru_cache(maxsize=1)
def _systemic_risk_rule():
    return load_pack().systemic_risk


def systemic_risk_domains() -> list[str]:
    return list(_systemic_risk_rule().applies_to_constraint_domains)


def is_systemic_risk(constraint_id: str, state=None) -> bool:
    """Special-domain constraints that become SYSTEMIC_RISK when the state is stuck.

    Replaces `if cid.startswith("L8") and revenue_state is not None: ...` —
    domain identity + state conditions are now pack declarations, evaluated generically.
    `state` None → False (state not yet built = not yet assessable).
    """
    if state is None:
        return False
    if not any(constraint_id.startswith(p) for p in systemic_risk_domains()):
        return False
    for cond in _systemic_risk_rule().when_state.all_of:
        value = getattr(state, cond.field, None)
        if cond.op == "is_not_null" and value is None:
            return False
        if cond.op == "gte" and (value or 0) < cond.value:
            return False
    return True
