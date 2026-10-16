"""MAPPER evidence->requirement — LOCK contract 27 Sep + review revision 86f4299
(B1-B4). DETERMINISTIC-FIRST pipeline:

    EvidenceItem (Universal State ONLY — raw transcript FORBIDDEN)
        -> deterministic candidate narrowing (RECALL-oriented: the whole
           semantic surface — definition+observability+ALL rule branches;
           WITHOUT status)
        -> proposal (deterministic v1; LLM = D6 propose-only plug-in)
        -> deterministic verification (EXACT-KEY contract!)
           PROPOSED mapping = authoritative schema EXACTLY 4-field
             (adjudication_schema.proposed_mapping; foreign fields
              status/polarity/unit_key = MALFORMED)
           UNIT CONTEXT = SEPARATE SIDECAR (B1/B2: unit identity lives
             beyond verification WITHOUT polluting the 5-field schema)
        -> VerifiedMappingBatch {verified_mappings, unit_contexts, unresolved}
        -> [unit grouping + A3b adapter]
        -> adjudicate_and_persist (the ONLY status authority — D-A1d)

Locked invariants (+review revision): A is_gap is not NEGATIVE · B mapper
without polarity/status + exact-key · B1 unit requirement without unit_key
(sidecar) = UNRESOLVED · B3 recall-oriented narrowing WITHOUT top-k cutoff ·
B4 hay = ALL rule branches (negative evidence must be able to become a candidate) ·
C negation = predicate work · D no-match != ABSENT · MALFORMED(ValueError)
!= UNRESOLVED(semantic) · EVIDENCE_NEED/QUESTION = NextMove.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any, Optional

UNIT_DOMAINS: dict[str, set[str]] = {
    "access.prospect_list": {"prospect"},
    "conversion.commitment_obtained": {"prospect", "tahap"},
    "experiment.baseline_comparison": {"perubahan"},
    "commercial.investment_sized": {"kesepakatan"},
    "experiment.test_card_defined": {"hipotesis"},
    "delivery.activity_tracking": {"aktivitas"},
}

PROPOSAL_FIELDS = frozenset(
    {"proposed_by", "requirement_id", "evidence_refs", "proposed_at"})
UNIT_CONTEXT_FIELDS = frozenset(
    {"proposed_by", "requirement_id", "evidence_refs", "unit_key",
     "proposed_at"})

_UNIT_KEY_RE = re.compile(r"^([a-z]+):([A-Za-z0-9_\-]+)$")
_WORD_RE = re.compile(r"[a-z0-9]{3,}")
_REQ_ID_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$")

# B2-polish (review 282cd29): structural = REUSE the AUTHORITATIVE validator
# (anti parallel-validator; pattern 25290cd):
from ontology.adjudication.validate_adjudication import (  # noqa: E402
    AdjudicationValidationError,
    check_proposed_mapping,
)

_STOP = frozenset("""
dan atau yang di ke dari untuk dengan pada adalah ada tidak belum sudah
ini itu para oleh sebagai juga akan telah bagi antara sampai kepada
the and for with that this from are was were has have not but all any
""".split())


class MalformedMapping(ValueError):
    """STRUCTURAL failure (shape/type/foreign-field) — NOT semantic unresolved."""


def _tokens(text: str) -> set[str]:
    return {m for m in _WORD_RE.findall(text.lower()) if m not in _STOP}


def narrow_candidates(evidence_text: str,
                      registry_entries: list[dict[str, Any]],
                      min_score: int = 1) -> list[tuple[str, int]]:
    """RECALL-oriented candidate narrowing (B3+B4): hay = definition +
    observability + ALL rule branches (sufficient/partial/no_decisive/
    contradicting) — even NEGATIVE evidence becomes a candidate so that
    contradicting is TESTED by the adjudicator. WITHOUT top-k cutoff. Candidate != status."""
    toks = _tokens(evidence_text)
    if not toks:
        return []
    out: list[tuple[str, int]] = []
    for r in registry_entries:
        rule = r.get("satisfaction_rule") or {}
        hay = " ".join(
            [r.get("definition", "")]
            + list(r.get("observability") or [])
            + [rule.get("sufficient", ""), rule.get("partial", ""),
               rule.get("no_decisive", ""), rule.get("contradicting", "")])
        score = len(toks & _tokens(hay))
        if score >= min_score:
            out.append((r["requirement_id"], score))
    out.sort(key=lambda t: (-t[1], t[0]))
    return out


def _check_exact_keys(obj: dict[str, Any], allowed: frozenset,
                      kind: str) -> None:
    extra = set(obj) - allowed
    if extra:
        hint = ""
        if "unit_key" in extra and kind == "proposal":
            hint = " (unit_key = unit_context SIDECAR, not a proposal field)"
        if extra & {"status", "polarity"}:
            hint = " (mapper WITHOUT polarity/status — LOCK B)"
        raise MalformedMapping(
            f"{kind}: foreign field {sorted(extra)}{hint} — exact-key "
            f"{sorted(allowed)}")


def verify_unit_key(requirement_id: str,
                    unit_key: Optional[str]) -> Optional[str]:
    """B1: multi-unit requirement WITHOUT unit_key = FAIL (unit identity
    must not disappear at the VERIFIED boundary). None=OK | reason."""
    domain = UNIT_DOMAINS.get(requirement_id)
    if domain is None:
        if unit_key is not None:
            return (f"{requirement_id} is not a multi-unit requirement "
                    f"(unit_key does not apply)")
        return None
    if unit_key is None:
        return (f"{requirement_id} is a multi-unit requirement — unit_key "
                f"MUST be in the unit_context sidecar (B1)")
    m = _UNIT_KEY_RE.match(unit_key)
    if not m:
        return f"wrong unit_key format ({unit_key!r} — must be 'kind:id')"
    if m.group(1) not in domain:
        return (f"kind {m.group(1)!r} is not a unit domain of {requirement_id} "
                f"(valid: {sorted(domain)})")
    return None


def _sem_base(p: dict[str, Any], evidence_index: dict[str, Any],
              registry_ids: set[str]) -> Optional[dict[str, Any]]:
    def unresolved(reason: str) -> dict[str, Any]:
        return {"unresolved": True, "requirement_id": p["requirement_id"],
                "evidence_refs": p["evidence_refs"], "reason": reason}
    if p["requirement_id"] not in registry_ids:
        return unresolved(f"requirement {p['requirement_id']!r} tidak "
                          f"terdaftar registry (INV-R6)")
    ghosts = [r for r in p["evidence_refs"] if r not in evidence_index]
    if ghosts:
        return unresolved(f"evidence_refs tak dikenal di Universal State: "
                          f"{ghosts}")
    return None


def _check_types(p: dict[str, Any], kind: str) -> None:
    """B2-polish: type/pattern MIRROR the authoritative schema (string /
    dotted-ref / int) — not just the field name."""
    if not isinstance(p["proposed_by"], str) or not p["proposed_by"]:
        raise MalformedMapping(f"{kind}.proposed_by must be a non-empty string")
    if not isinstance(p["proposed_at"], int) or isinstance(p["proposed_at"], bool):
        raise MalformedMapping(f"{kind}.proposed_at must be an integer")
    if not _REQ_ID_RE.match(p["requirement_id"]):
        raise MalformedMapping(
            f"{kind}.requirement_id must match the dotted-ref pattern — "
            f"{p['requirement_id']!r}")


def registry_fingerprint(registry_entries: list[dict[str, Any]]) -> str:
    """BLOCKER-1 (review e8951cb): formal rules = a COMPILED ARTIFACT
    bound to a specific registry — sha256 fingerprint over (rid, mode,
    all branch text). Stale/foreign rules are TRAPPED at gate-2."""
    canon = json.dumps(
        sorted((r["requirement_id"],
                (r.get("satisfaction_rule") or {}).get("mode", ""),
                (r.get("satisfaction_rule") or {}).get("sufficient", ""),
                (r.get("satisfaction_rule") or {}).get("partial", ""),
                (r.get("satisfaction_rule") or {}).get("no_decisive", ""),
                (r.get("satisfaction_rule") or {}).get("contradicting", ""))
               for r in registry_entries),
        ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(canon.encode()).hexdigest()


_MODE_BRANCHES = {"BINARY": ("sufficient", "no_decisive", "contradicting"),
                  "PARTIAL": ("sufficient", "partial", "no_decisive",
                              "contradicting")}


def bind_formal_rules(registry_entries, predicates):  # noqa: ANN001
    """DEPRECATED (review 640680d BLOCKER-1): accepts FREE predicates —
    the fingerprint proves 'envelope for registry X', NOT 'predicate =
    authoritative compilation of rule X' (PWN attack passed). Valid path:
    ontology.mapper.formal_compiler.compile_formal_rules (reviewed repo
    artifact + per-rid source_rule_sha256)."""
    raise MalformedMapping(
        "bind_formal_rules DEPRECATED — use formal_compiler."
        "compile_formal_rules (reviewed compilation artifact, BLOCKER-1)")


def _semantic_gate(proposal: dict[str, Any],
                   evidence_index: dict[str, Any],
                   formal_rules: dict[str, dict[str, Any]] | None,
                   ) -> Optional[dict[str, Any]]:
    """D-A2 TWO-GATE (review a602666 blocker-2): structural is NOT enough
    on its own — VERIFIED only after the semantic gate:
      - FORMAL rule (KB predicate) available -> deterministic semantic
        verification: evidence must satisfy >=1 rule branch (proof of the
        evidence->requirement RELATION, not merely a valid ref) ->
        verification_method='deterministic_predicate' HONEST (predicate
        REALLY evaluated)
      - rule still PROSE (most of the live registry) -> UNRESOLVED:
        a 'verified mapping' MUST NOT mean 'structurally valid mapping' —
        wait for the second-pass verifier (D-A2 C, not yet in v1).
    Returns: None=PASSED semantics | unresolved-record."""
    # envelope MUST be the output of bind_formal_rules (BLOCKER-1: an arbitrary
    # raw dict is REJECTED — so is a fingerprint STALE w.r.t. the live registry)
    if not isinstance(formal_rules, dict) \
            or not {"fingerprint", "modes", "rules"} <= set(formal_rules):
        return {"unresolved": True,
                "requirement_id": proposal["requirement_id"],
                "evidence_refs": proposal["evidence_refs"],
                "reason": ("formal_rules bukan ENVELOPE hasil "
                           "bind_formal_rules — rule arbitrer ditolak "
                           "(authority binding BLOCKER-1)")}
    # NO_FORMAL_RULE vs STALE (review 019d1a9 micro-gap): an empty artifact
    # = compilation not yet available (PROSE path) — NOT a stale anomaly
    if formal_rules.get("fingerprint") == "":
        return {"unresolved": True,
                "requirement_id": proposal["requirement_id"],
                "evidence_refs": proposal["evidence_refs"],
                "reason": ("NO_FORMAL_RULE — kompilasi formal ter-review "
                           "belum tersedia utk registry ini; jalur PROSA "
                           "(D-A2 C: menunggu kompilasi/second-pass)")}
    if formal_rules["fingerprint"] != registry_fingerprint(_LIVE_REGISTRY):
        return {"unresolved": True,
                "requirement_id": proposal["requirement_id"],
                "evidence_refs": proposal["evidence_refs"],
                "reason": ("formal rules STALE — fingerprint tak cocok "
                           "dgn registry live (BLOCKER-1: compiled "
                           "artifact wajib turunan registry INI)")}
    rid = proposal["requirement_id"]
    rule = formal_rules["rules"].get(rid)
    if rule is None:
        return {"unresolved": True,
                "requirement_id": rid,
                "evidence_refs": proposal["evidence_refs"],
                "reason": ("rule registry masih PROSA — deterministic "
                           "semantic verification tak tersedia; structural "
                           "TIDAK cukup utv VERIFIED (D-A2 A saja dilarang); "
                           "menunggu second-pass verifier")}
    from core.stages.rule_predicates import evaluate_predicate  # noqa: E402
    evs = [evidence_index[r] for r in proposal["evidence_refs"]]
    # mode-aware (BLOCKER-2): BINARY without partial (RR11); no_decisive =
    # adjudicator complement, not evaluated as positive evidence
    branches = ("sufficient", "contradicting") \
        if formal_rules["modes"][rid] == "BINARY" \
        else ("sufficient", "partial", "contradicting")
    for branch in branches:
        matched, _cites, _reason = evaluate_predicate(rule[branch], evs,
                                                   negation_aware=True)
        if matched:
            return None  # relation proven in >=1 branch
    return {"unresolved": True,
            "requirement_id": proposal["requirement_id"],
            "evidence_refs": proposal["evidence_refs"],
            "reason": ("evidence tak memenuhi cabang rule mana pun — "
                       "hubungan evidence->requirement TIDAK terbukti "
                       "(semantic gate D-A2 B)")}


# live registry for the fingerprint check (set by the caller; default = derived
# from the formal_rules envelope — impossible; the gate rejects if empty)
_LIVE_REGISTRY: list[dict[str, Any]] = []


def set_live_registry(registry_entries: list[dict[str, Any]]) -> None:
    """Must be called by the runtime before verification (BLOCKER-1: the formal-rules
    fingerprint is checked AGAINST the live registry, not against itself)."""
    global _LIVE_REGISTRY
    _LIVE_REGISTRY = registry_entries


def verify_proposal(proposal: dict[str, Any],
                    evidence_index: dict[str, Any],
                    registry_ids: set[str],
                    formal_rules: dict[str, dict[str, Any]] | None = None,
                    ) -> dict[str, Any]:
    """PROPOSED -> VERIFIED (runtime EXACTLY 5-field) | UNRESOLVED.
    Exact-key: foreign field = MalformedMapping (schema-forbidden must not be
    mapper-accepted). Unit requirements can still be verified here;
    unit_identity preservation = verify_batch (B1)."""
    if not isinstance(proposal, dict):
        raise MalformedMapping("proposal must be an object")
    # B2-polish: REUSE the AUTHORITATIVE check_proposed_mapping (AD8: exact-key +
    # required + array) then add schema-mirroring type/pattern:
    try:
        check_proposed_mapping(proposal)
    except AdjudicationValidationError as exc:
        raise MalformedMapping(str(exc)) from exc
    _check_types(proposal, "proposal")
    refs = proposal["evidence_refs"]
    if not all(isinstance(x, str) and x for x in refs):
        raise MalformedMapping("evidence_refs must be a non-empty array of strings")
    un = _sem_base(proposal, evidence_index, registry_ids)
    if un is not None:
        return un
    un = _semantic_gate(proposal, evidence_index, formal_rules)
    if un is not None:
        return un
    return {
        "requirement_id": proposal["requirement_id"],
        "evidence_refs": refs,
        "verification_method": "deterministic_predicate",  # HONEST:
        # the predicate is REALLY evaluated in _semantic_gate (D-A2 B)
        "verified": True,
        "verified_at": int(time.time()),
    }


def verify_unit_context(uc: dict[str, Any],
                        evidence_index: dict[str, Any],
                        registry_ids: set[str]) -> dict[str, Any]:
    """unit_context SIDECAR (B1/B2): preserves ev->requirement->unit_key
    BEYOND verification without touching the verified_mapping schema."""
    if not isinstance(uc, dict):
        raise MalformedMapping("unit_context must be an object")
    missing = UNIT_CONTEXT_FIELDS - set(uc)
    if missing:
        raise MalformedMapping(f"unit_context: missing field {sorted(missing)}")
    _check_exact_keys(uc, UNIT_CONTEXT_FIELDS, "unit_context")
    _check_types(uc, "unit_context")
    refs = uc["evidence_refs"]
    if not isinstance(refs, list) or not refs \
            or not all(isinstance(x, str) and x for x in refs):
        raise MalformedMapping("evidence_refs must be a non-empty array of strings")
    un = _sem_base(uc, evidence_index, registry_ids)
    if un is not None:
        return un
    fail = verify_unit_key(uc["requirement_id"], uc["unit_key"])
    if fail:
        return {"unresolved": True, "requirement_id": uc["requirement_id"],
                "evidence_refs": refs, "reason": fail}
    return {"requirement_id": uc["requirement_id"],
            "unit_key": uc["unit_key"], "evidence_refs": refs}


def _binding_key(requirement_id: str, refs: list[str]) -> tuple[str, ...]:
    """B1-exact: sidecar bound to the mapping via the exact
    (requirement_id, refs-SET) — SET semantics: duplicate refs normalized (review a602666)."""
    return (requirement_id,) + tuple(sorted(set(refs)))


def verify_batch(proposals: list[dict[str, Any]],
                 unit_contexts: list[dict[str, Any]],
                 evidence_index: dict[str, Any],
                 registry_ids: set[str],
                 formal_rules: dict[str, Any] | None = None,
                 live_registry: list[dict[str, Any]] | None = None,
                 ) -> dict[str, list[dict[str, Any]]]:
    """VERIFIED batch boundary (B1-exact): a unit-requirement mapping is only
    VERIFIED if a unit_context with EXACTLY the same (requirement_id, refs-set)
    binding exists. live_registry = basis for the fingerprint check (BLOCKER-1)."""
    if live_registry is not None:
        set_live_registry(live_registry)
    ucs: dict[tuple[str, ...], dict[str, Any]] = {}
    out_uc: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for uc in unit_contexts:
        r = verify_unit_context(uc, evidence_index, registry_ids)
        if r.get("unresolved"):
            unresolved.append(r)
        else:
            ucs[_binding_key(r["requirement_id"], r["evidence_refs"])] = r
            out_uc.append(r)
    verified: list[dict[str, Any]] = []
    for p in proposals:
        r = verify_proposal(p, evidence_index, registry_ids, formal_rules)
        if r.get("unresolved"):
            unresolved.append(r)
            continue
        rid = r["requirement_id"]
        if rid in UNIT_DOMAINS \
                and _binding_key(rid, r["evidence_refs"]) not in ucs:
            unresolved.append({
                "unresolved": True, "requirement_id": rid,
                "evidence_refs": r["evidence_refs"],
                "reason": ("requirement unit-berlipak TANPA unit_context "
                           "dgn binding EKSAK (requirement_id+refs-set) "
                           "— B1-exact")})
            continue
        verified.append(r)
    return {"verified_mappings": verified, "unit_contexts": out_uc,
            "unresolved": unresolved}


def propose_deterministic(evidence_index: dict[str, Any],
                          registry_entries: list[dict[str, Any]],
                          min_score: int = 1,
                          ) -> list[dict[str, Any]]:
    """Proposer v1 — RECALL-oriented (B3): ALL candidates with score>=min_score
    become proposals (no top-k). Exact-key 4-field. Unit identity cannot be
    inferred deterministically from text — unit_context proposal = the
    LLM/extractor unit pass path (noted §7.12). is_gap is still proposed (LOCK-A)."""
    now = int(time.time())
    proposals: list[dict[str, Any]] = []
    for eid, ev in evidence_index.items():
        text = f"{ev.signal} {ev.source_quote or ''}"
        for rid, _score in narrow_candidates(text, registry_entries,
                                             min_score):
            proposals.append({
                "proposed_by": "mapper_deterministic_v1",
                "requirement_id": rid,
                "evidence_refs": [eid],
                "proposed_at": now,
            })
    return proposals
