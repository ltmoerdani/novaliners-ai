#!/usr/bin/env python
"""Load-time validator for the NOVALINERS KNOWLEDGE SCHEMA v0.1.

Enforces the rules of docs/knowledge/schema/knowledge-schema-v0.1.md §4:
1. IDs unique globally across all knowledge files
2. targets[] only holds constraint IDs present in constraints.json
3. probes must have signal_interpretation.positive & .negative
4. items without provenance → hard fail
5. lifecycle valid
6. ID prefix must be registered in sources.json
7. probes with empty targets only allowed if evidence_type == 'meta'

Usage: python validate_knowledge.py  (run from the repo root)
Exit 0 = all knowledge files valid; exit 1 = violations found.
"""
import json
import sys
from pathlib import Path

KB = Path(__file__).parent
ROOT = KB.parent.parent
# Phase E: the validator uses the contract & operator whitelist from `core` — a single
# source of truth, so there is no second operator list that can drift.
sys.path.insert(0, str(ROOT))
from core.schema.ontology import validate_disqualifiers  # noqa: E402
from core.stages.rule_predicates import OPERATORS  # noqa: E402


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


# Predicate operators that yield evidence citations (internal-docs §8.4 T1). A
# tier-1 predicate must contain at least one so its claim stays auditable.
CITABLE_OPERATORS = {
    "text_contains_any", "text_contains_all", "text_present_pattern", "evidence_level_present",
}


def _has_citable_operator(pred) -> bool:
    if not isinstance(pred, dict):
        return False
    if CITABLE_OPERATORS & set(pred.keys()):
        return True
    for key in ("all_of", "any_of", "none_of"):
        for sub in pred.get(key) or []:
            if _has_citable_operator(sub):
                return True
    return False


def _predicate_ops(pred) -> set[str]:
    """All operator keys inside the predicate tree (for authoring-time validation)."""
    ops: set[str] = set()
    if not isinstance(pred, dict):
        return ops
    for key, value in pred.items():
        if key in ("all_of", "any_of", "none_of"):
            for sub in value or []:
                ops |= _predicate_ops(sub)
        else:
            ops.add(key)
    return ops


def main():
    schema = load(KB.parent / "knowledge_schema.json")
    constraints = load(KB.parent / "constraints.json")
    valid_cids = set(constraints["constraints"].keys())
    errors = []
    seen_ids = {}
    # PHASE 3 (internal-docs §6.2e, /04): the source registry must fill in
    # authority_grade + admission — the basis for tier-2 pre-rerank & the admission test.
    _GRADES = {"empirical_research", "practitioner_playbook", "conceptual_framework"}
    _ADMISSION = {"primary", "reinforcing"}
    sources_raw = load(KB / "sources.json")["sources"]
    sources = {s["source_id"] for s in sources_raw}
    for s in sources_raw:
        sid = s.get("source_id", "?")
        if s.get("authority_grade") not in _GRADES:
            errors.append(
                f"sources.json: '{sid}' authority_grade '{s.get('authority_grade')}' "
                f"tidak valid — wajib salah satu dari {sorted(_GRADES)}"
            )
        if s.get("admission") not in _ADMISSION:
            errors.append(
                f"sources.json: '{sid}' admission '{s.get('admission')}' tidak valid — "
                f"wajib 'primary' atau 'reinforcing' (admission test internal-docs §6.3)"
            )
    # reinforcing sources MUST NOT own their own rules — only provenance/
    # confidence upgrades (collector fallacy, internal-docs §7)
    reinforcing = {s["source_id"] for s in sources_raw if s.get("admission") == "reinforcing"}
    for f_kb in sorted(KB.glob("*_evidence_rules.json")):
        data = load(f_kb)
        for r in data.get("evidence_rules", []):
            src = (r.get("provenance") or {}).get("source_id")
            if src in reinforcing:
                errors.append(
                    f"{r['rule_id']}: sumber '{src}' ber-admission 'reinforcing' "
                    f"tidak boleh menambah rule baru — cukup provenance/confidence "
                    f"upgrade ke rule sumber primary (internal-docs §6.3)"
                )
    enums = schema["enums"]
    seen_ids = {}

    # Phase E (ontology v0.3): the `disqualifiers` block must satisfy the contract — bare
    # prose is a declaration that binds nothing (the knowledge version of
    # "confidence theater"). Predicate operators are also checked HERE (authoring time):
    # an operator typo would be caught by `evaluate_predicate` as a "predicate error" and
    # silently never match.
    # Review 640680d BLOCKER-2: the engine-layer structural validator
    # (validate_predicate_tree — operand/type/regex) is used HERE too —
    # one source for both the KB validator and the gate-2 mapper.
    from core.stages.rule_predicates import validate_predicate_tree  # noqa: E402
    errors.extend(validate_disqualifiers(constraints["constraints"]))
    for _cid, _body in constraints["constraints"].items():
        for _dq in _body.get("disqualifiers") or []:
            if isinstance(_dq, dict) and _dq.get("predicate"):
                _unknown = _predicate_ops(_dq["predicate"]) - OPERATORS
                if _unknown:
                    errors.append(
                        f"{_cid}: disqualifier '{_dq.get('id')}' memakai operator predikat "
                        f"tak dikenal: {sorted(_unknown)}"
                    )
                for _perr in validate_predicate_tree(
                        _dq["predicate"],
                        f"{_cid}:{_dq.get('id')}.predicate"):
                    errors.append(_perr)

    def check_provenance(item, label):
        prov = item.get("provenance")
        if not isinstance(prov, dict):  # rule 4
            errors.append(f"{label}: provenance HILANG (hard fail)")
            return
        if prov.get("source_id") not in sources:  # rule 6
            errors.append(f"{label}: source_id '{prov.get('source_id')}' tidak terdaftar di sources.json")
        if not prov.get("chapters"):
            errors.append(f"{label}: provenance.chapters kosong")
        kt = prov.get("knowledge_type")
        if kt and kt not in enums["knowledge_type"]:
            errors.append(f"{label}: knowledge_type '{kt}' tidak valid")
        if prov.get("confidence") and prov["confidence"] not in [
            "normative_only", "expert_hypothesis", "empirical_low", "empirical_high",
        ]:
            errors.append(f"{label}: confidence '{prov['confidence']}' tidak valid")

    def check_lifecycle(item, label):
        lc = item.get("lifecycle")
        if lc not in enums["lifecycle"]:  # rule 5
            errors.append(f"{label}: lifecycle '{lc}' tidak valid")
        # B1b (internal-docs §364): the CHALLENGED trigger — a challenged item must
        # carry a justification; without it the freeze is not auditable.
        if lc == "CHALLENGED" and not (item.get("challenge") or "").strip():
            errors.append(
                f"{label}: lifecycle CHALLENGED wajib disertai field 'challenge' "
                f"(klaster kontradiksi + status adjudikasinya)"
            )

    def check_id(item, id_field, label):
        iid = item.get(id_field)
        if not iid:
            errors.append(f"{label}: {id_field} hilang")
            return
        if iid in seen_ids:  # rule 1
            errors.append(f"{label}: ID '{iid}' DUPLIKAT dengan {seen_ids[iid]}")
        seen_ids[iid] = label

    def check_targets(item, label, allow_empty_meta=False):
        targets = item.get("targets")
        if not isinstance(targets, list):
            errors.append(f"{label}: targets bukan list")
            return
        if allow_empty_meta and item.get("evidence_type") == "meta":
            targets = []
        else:
            bad = [t for t in targets if t not in valid_cids]  # rule 2
            if bad:
                errors.append(f"{label}: constraint target tidak valid: {bad}")
            if not targets:
                errors.append(f"{label}: targets kosong")

    files = sorted(set(KB.glob("*.json")) - {KB / "sources.json"})
    for f in files:
        data = load(f)
        for item in data.get("probes", []):
            label = f"probe {item.get('probe_id')}"
            check_id(item, "probe_id", label)
            if not item.get("text"):
                errors.append(f"{label}: text hilang")
            sig = item.get("signal_interpretation") or {}
            if not sig.get("positive") or not sig.get("negative"):  # rule 3
                errors.append(f"{label}: signal_interpretation.positive/negative wajib")
            et = item.get("evidence_type")
            if et not in enums["evidence_type"]:
                errors.append(f"{label}: evidence_type '{et}' tidak valid")
            check_targets(item, label, allow_empty_meta=True)
            check_provenance(item, label)
            check_lifecycle(item, label)
        for item in data.get("evidence_rules", []):
            label = f"rule {item.get('rule_id')}"
            check_id(item, "rule_id", label)
            cons = item.get("consequence") or {}
            if cons.get("action") not in [
                "RAISE_CONFIDENCE", "LOWER_CONFIDENCE", "BLOCK_VERDICT", "FLAG_SEGMENT",
                "IGNORE_SIGNAL",
            ]:
                errors.append(f"{label}: consequence.action tidak valid")
            if not item.get("condition"):
                errors.append(f"{label}: condition hilang")
            # schema v0.3: evaluation tier is required (internal-docs §8.4 T1)
            ev = item.get("evaluation")
            if not isinstance(ev, dict):
                errors.append(f"{label}: evaluation wajib (schema v0.3) — tier deterministic|judgment")
            else:
                tier = ev.get("tier")
                if tier not in ("deterministic", "judgment"):
                    errors.append(f"{label}: evaluation.tier '{tier}' tidak valid")
                if tier == "deterministic" and not isinstance(ev.get("predicate"), dict):
                    errors.append(f"{label}: tier=deterministic wajib punya evaluation.predicate")
                if tier == "deterministic" and isinstance(ev.get("predicate"), dict):
                    if not _has_citable_operator(ev["predicate"]):
                        errors.append(
                            f"{label}: predicate tanpa operator positif yang bisa disitasi "
                            f"(text_contains_*/text_present_pattern/evidence_level_present) — "
                            f"klaim negatif murni tidak auditabel"
                        )
                    # This iteration's audit: the same structural validator is used for deterministic
                    # rule predicates (not only disqualifiers) — broken operand/type/regex gets caught
                    # at authoring time, instead of being swallowed by the evaluator at runtime as
                    # "not enough evidence".
                    for _rerr in validate_predicate_tree(
                            ev["predicate"], f"{label}.predicate"):
                        errors.append(_rerr)
                if tier == "judgment" and ev.get("predicate"):
                    errors.append(f"{label}: tier=judgment tidak boleh punya predicate")
            check_targets(cons, label)
            check_provenance(item, label)
            check_lifecycle(item, label)
        for item in data.get("anti_patterns", []):
            label = f"anti_pattern {item.get('pattern_id')}"
            check_id(item, "pattern_id", label)
            if not item.get("symptom"):
                errors.append(f"{label}: symptom hilang")
            check_targets({"targets": item.get("constraint_link")}, label)
            check_provenance(item, label)
            check_lifecycle(item, label)
        for item in data.get("interventions", []):
            label = f"intervention {item.get('intervention_id')}"
            check_id(item, "intervention_id", label)
            if not item.get("expected_evidence"):
                errors.append(f"{label}: expected_evidence wajib (hook Outcome Store)")
            check_targets(item, label)
            check_provenance(item, label)
            check_lifecycle(item, label)

    # M5: rule source activation (rule_activation.json) — every prefix must be registered in
    # sources.json. A mistyped prefix would silently leave its rules never evaluated; now an ERROR.
    activation_file = KB / "rule_activation.json"
    if not activation_file.exists():
        errors.append("rule_activation.json HILANG — diagnosis butuh deklarasi sumber rule aktif")
    else:
        activation = load(activation_file)
        active = activation.get("active_rule_sources") or []
        if not active:
            errors.append("rule_activation.json: active_rule_sources kosong")
        for src in active:
            if src.lower() not in sources:
                errors.append(f"rule_activation: '{src}' tidak terdaftar di sources.json")

    # PHASE 1 (internal-docs §5.1): compiled_rubrics.json must exist, cover ALL
    # rules, and contain no orphan IDs — so the tier-2 prompt never silently falls back to
    # verbose mode (KB depth must always be compiled, never left to memory).
    rubric_file = KB / "compiled_rubrics.json"
    if not rubric_file.exists():
        errors.append(
            "compiled_rubrics.json HILANG — jalankan compile_rubrics.py "
            "(internal-docs Gate 2: rubrik wajib segar)"
        )
    else:
        compiled = set(load(rubric_file).get("rubric_lines") or {})
        # rules frozen as CHALLENGED from runtime — also exempt from the rubric requirement
        frozen = set()
        for f_kb in sorted(KB.glob("*_evidence_rules.json")):
            for r in load(f_kb).get("evidence_rules", []):
                if r.get("lifecycle") == "CHALLENGED":
                    frozen.add(r["rule_id"])
        rule_ids = {i for i, label in seen_ids.items() if label.startswith("rule")} - frozen
        missing = sorted(rule_ids - compiled)
        stale = sorted(compiled - set(seen_ids))
        if missing:
            errors.append(
                f"compiled_rubrics.json STALE — rule tanpa rubrik: {missing} "
                f"(regenerasi: python ontology/knowledge/compile_rubrics.py)"
            )
        if stale:
            errors.append(f"compiled_rubrics.json YATIM — rubrik tanpa rule: {stale}")

    # PHASE 0 (internal-docs §7, internal-docs Gate 2(e)): density guard.
    # Cross-file aggregate — runs AFTER the per-item loop finishes, keeping the validator on
    # one philosophy (per-item checks, then aggregate invariants).
    # Thresholds & the allowlist are declared in density_policy.json (the P5b pattern:
    # declarations live outside the engine), part of the KB fingerprint.
    policy_file = KB / "density_policy.json"
    if not policy_file.exists():
        errors.append(
            "density_policy.json HILANG — density guard butuh deklarasi "
            "threshold + known_thin (internal-docs Gate 2(e))"
        )
    else:
        policy = load(policy_file)
        th = policy.get("thresholds") or {}
        min_p, min_r, min_s = th.get("min_probes", 3), th.get("min_rules", 3), th.get("min_sources", 2)
        known_thin: dict = policy.get("known_thin") or {}

        cap_probes: dict[str, int] = {}
        cap_rules: dict[str, int] = {}
        cap_sources: dict[str, set] = {}
        for f in sorted(set(KB.glob("*.json")) - {KB / "sources.json", policy_file}):
            data = load(f)
            src_of_file = None
            probes = data.get("probes", [])
            if probes:
                src_of_file = probes[0].get("provenance", {}).get("source_id")
            for item in probes:
                for t in item.get("targets") or []:
                    cap_probes[t] = cap_probes.get(t, 0) + 1
                    if src_of_file:
                        cap_sources.setdefault(t, set()).add(src_of_file)
            rules = data.get("evidence_rules", [])
            if rules and not src_of_file:
                src_of_file = rules[0].get("provenance", {}).get("source_id")
            for item in rules:
                for t in (item.get("consequence") or {}).get("targets") or []:
                    cap_rules[t] = cap_rules.get(t, 0) + 1
                    if src_of_file:
                        cap_sources.setdefault(t, set()).add(src_of_file)

        # every constraint must be touched by the KB at least once (never zero total)
        for cid in sorted(valid_cids):
            p, r = cap_probes.get(cid, 0), cap_rules.get(cid, 0)
            s = len(cap_sources.get(cid) or set())
            if p == 0 and r == 0:
                errors.append(
                    f"density: capability '{cid}' NOL total (tidak punya probe/rule) "
                    f"— daftarkan di known_thin TIDAK berlaku untuk nol total; "
                    f"ekstrak dulu (internal-docs §6.3 zona emas)"
                )
                continue
            thin_reasons = []
            if p < min_p:
                thin_reasons.append(f"probes={p}<{min_p}")
            if r < min_r:
                thin_reasons.append(f"rules={r}<{min_r}")
            if s < min_s:
                thin_reasons.append(f"sources={s}<{min_s}")
            if thin_reasons:
                if cid not in known_thin:
                    errors.append(
                        f"density: capability '{cid}' THIN ({', '.join(thin_reasons)}) "
                        f"tapi tidak terdaftar di density_policy.json:known_thin — "
                        f"tambahkan entri (alasan + closing_source) ATAU perdalam KB "
                        f"(internal-docs Gate 2(e): known_thin ratchet mengecil, butuh alasan)"
                    )
            elif cid in known_thin:
                errors.append(
                    f"density: capability '{cid}' sudah memenuhi threshold "
                    f"(probes={p}, rules={r}, sources={s}) tapi masih di known_thin — "
                    f"HAPUS entrinya (ratchet hanya boleh menyusut)"
                )
        # known_thin entries pointing at unknown constraints = typos
        for cid in known_thin:
            if cid not in valid_cids:
                errors.append(f"density: known_thin '{cid}' bukan constraint ID valid")

    total = len(seen_ids)
    if errors:
        print(f"✗ VALIDATION FAILED — {len(errors)} pelanggaran:")
        for e in errors:
            print("  -", e)
        sys.exit(1)
    thin_n, th_txt = 0, "off"
    if policy_file.exists():
        policy = load(policy_file)
        thin_n = len(policy.get("known_thin") or {})
        th = policy.get("thresholds") or {}
        th_txt = "/".join(str(th.get(k, "?")) for k in ("min_probes", "min_rules", "min_sources"))
    print(
        f"✅ {total} knowledge items valid (schema v{schema['$schema_version']}, "
        f"sources: {sorted(sources)}); density guard: {len(valid_cids)} capability, "
        f"known_thin={thin_n} (threshold p/r/s ≥ {th_txt})"
    )
    by_prefix: dict = {}
    for iid in seen_ids:
        by_prefix.setdefault(iid[:2], []).append(iid)
    for pfx, ids in sorted(by_prefix.items()):
        print(f"   {pfx}: {len(ids)} items")

if __name__ == "__main__":
    main()
