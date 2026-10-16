"""Authoritative formal-rule COMPILER (review 640680d BLOCKER-1):
the old `bind_formal_rules()` accepted FREE predicates — as long as rid/mode/
fingerprint matched, even a PWN predicate passed (the fingerprint proves
'envelope targeted at registry X', NOT 'predicate = authoritative
compilation of satisfaction_rule X').

Replacement design (owner order): Registry -> AUTHORITATIVE COMPILER ->
bound artifact -> gate-2.

Prose->predicate compilation CANNOT be verified deterministically —
its authority is REVIEW. Therefore: predicates live in the REPO ARTIFACT
`formal_rules_compiled.json` (not free runtime input), every entry
MUST carry provenance {compiled_by, review} + `source_rule_sha256`
(hash of THAT ENTRY's satisfaction_rule branch text — per-rid binding,
not just the registry-global fingerprint). The runtime API
(`compile_formal_rules`) ONLY reads the artifact & verifies;
there is no free predicate parameter. Artifact = review surface:
a predicate change = a reviewed file change (visible diff),
not silent injection.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from core.stages.rule_predicates import validate_predicate_tree
from ontology.knowledge.validate_knowledge import _has_citable_operator

_MODE_BRANCHES = {"BINARY": ("sufficient", "no_decisive", "contradicting"),
                  "PARTIAL": ("sufficient", "partial", "no_decisive",
                              "contradicting")}
_EVAL_BRANCHES = ("sufficient", "partial", "contradicting")  # no_decisive =
# adjudicator complement — structurally validated but not evaluated as
# positive evidence (mode-aware, RR11)

ARTIFACT_FIELDS = frozenset(
    {"predicates", "compiled_by", "review", "source_rule_sha256"})


class CompilationError(ValueError):
    """An invalid compilation artifact = AUTHORING/REVIEW failure (not
    unresolved 'insufficient evidence')."""


def rule_text_sha256(rule: dict[str, Any]) -> str:
    """PER-RID hash over the whole satisfaction_rule branch text of the entry —
    granular binding (review 640680d: a registry-global fingerprint alone
    does not bind the predicate to the ENTRY rule being compiled)."""
    canon = json.dumps(
        {b: str(rule.get(b, "")) for b in _MODE_BRANCHES["PARTIAL"]},
        ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(canon.encode()).hexdigest()


def _compile_artifact_file(registry_entries: list[dict[str, Any]],
                           artifact_path: Path | str,
                           ) -> dict[str, Any]:
    """INTERNAL/TEST-ONLY (review 019d1a9 end-point): a free path only
    for test fixtures — RUNTIME MUST use compile_from_repo_artifact()
    (canonical repo file ONLY; an external reviewed-looking file e.g.
    /tmp/pwn.json with a valid hash has NO runtime door).
    Per-entry verification: rid exists in the registry · mode matches · branches match
    the mode · source_rule_sha256 == hash of the ENTRY rule (per-rid stale REJECTED) ·
    provenance {compiled_by, review} non-empty · predicate PASSES
    validate_predicate_tree (full structural — operand/type/regex,
    BLOCKER-2). Return envelope {fingerprint, modes, rules}."""
    if isinstance(artifact_path, dict):
        raise CompilationError(
            "artifact dict REJECTED — valid path: a reviewed artifact file "
            "(Path/str). Injection API closed (review 9ed8d13).")
    loaded = json.loads(Path(artifact_path).read_text(encoding="utf-8"))
    return _compile_loaded_artifact(registry_entries, loaded)


def compile_formal_rules(registry_entries, artifact_path):  # noqa: ANN001
    """Backward-alias INTERNAL (test fixtures) — free file path.
    RUNTIME: compile_from_repo_artifact() (canonical repo file ONLY)."""
    return _compile_artifact_file(registry_entries, artifact_path)


def _compile_loaded_artifact(registry_entries: list[dict[str, Any]],
                             artifact: dict[str, Any],
                             ) -> dict[str, Any]:
    """INTERNAL: verify the loaded artifact (called by the loader above)."""
    reg = {r["requirement_id"]: r for r in registry_entries}
    rules: dict[str, dict[str, Any]] = {}
    modes: dict[str, str] = {}
    for rid, entry in artifact.items():
        if rid.startswith("$"):  # $comment artifact metadata — not an entry
            continue
        if rid not in reg:
            raise CompilationError(
                f"compilation artifact for {rid!r} is NOT in the registry — "
                f"foreign ontology rejected (BLOCKER-1)")
        reg_rule = reg[rid].get("satisfaction_rule") or {}
        mode = reg_rule.get("mode")
        if mode not in _MODE_BRANCHES:
            raise CompilationError(f"{rid}: unknown registry mode {mode!r}")
        if not isinstance(entry, dict) \
                or set(entry) != ARTIFACT_FIELDS:
            raise CompilationError(
                f"{rid}: artifact entry must be EXACTLY {sorted(ARTIFACT_FIELDS)}")
        for f in ("compiled_by", "review"):
            if not isinstance(entry.get(f), str) or not entry[f]:
                raise CompilationError(
                    f"{rid}: provenance '{f}' must be a non-empty string — "
                    f"compilation authority = REVIEW (not free input)")
        if entry["source_rule_sha256"] != rule_text_sha256(reg_rule):
            raise CompilationError(
                f"{rid}: source_rule_sha256 STALE — this entry's registry rule "
                f"changed after compilation; recompile + review is required "
                f"(per-rid binding, BLOCKER-1)")
        preds = entry["predicates"]
        if not isinstance(preds, dict):
            raise CompilationError(f"{rid}: predicates must be an object")
        if preds.get("mode") not in (None, mode):
            raise CompilationError(
                f"{rid}: predicate mode {preds.get('mode')!r} != registry "
                f"{mode!r}")
        want = set(_MODE_BRANCHES[mode])
        got = set(preds) - {"mode"}
        if got != want:
            raise CompilationError(
                f"{rid}: branches {sorted(got)} != mode {mode} (require "
                f"{sorted(want)} — RR11)")
        for branch in _MODE_BRANCHES[mode]:
            errs = validate_predicate_tree(preds[branch],
                                           f"{rid}.{branch}")
            if errs:
                raise CompilationError(
                    f"compiled predicate BROKEN (authoring failure, NOT "
                    f"'insufficient evidence'): {'; '.join(errs)}")
            # POINT-3 (review 9ed8d13): a PROOF branch (not no_decisive)
            # must have a citable operator — purely negative = unaudi-
            # table; without this the evaluator rejects later as 'without
            # citation' -> False -> masquerades as 'insufficient evidence'
            if branch != "no_decisive" \
                    and not _has_citable_operator(preds[branch]):
                raise CompilationError(
                    f"{rid}.{branch}: purely negative WITHOUT a "
                    f"citable operator — un-auditable claim; authoring failure "
                    f"(NOT unresolved 'insufficient evidence')")
        rules[rid] = {b: preds[b] for b in _MODE_BRANCHES[mode]}
        modes[rid] = mode
    from ontology.mapper.contract import registry_fingerprint
    return {"fingerprint": registry_fingerprint(registry_entries),
            "modes": modes, "rules": rules,
            "compiled_from": "formal_rules_compiled.json (reviewed artifact)"}


def compile_from_repo_artifact(
        registry_entries: list[dict[str, Any]]) -> dict[str, Any]:
    """THE ONLY RUNTIME DOOR (review 019d1a9): canonical repo file
    ontology/mapper/formal_rules_compiled.json ONLY — WITHOUT a path
    parameter (injection of an external 'reviewed-looking' file with a valid hash
    is fully closed). Empty/missing artifact -> fingerprint "" =
    NO_FORMAL_RULE (not STALE — epistemically different; gate-2 distinguishes)."""
    p = Path(__file__).parent / "formal_rules_compiled.json"
    if not p.exists():
        return _no_formal_rule()
    loaded = json.loads(p.read_text(encoding="utf-8"))
    if not any(not k.startswith("$") for k in loaded):
        return _no_formal_rule()
    return _compile_loaded_artifact(registry_entries, loaded)


def _no_formal_rule() -> dict[str, Any]:
    return {"fingerprint": "", "modes": {}, "rules": {},
            "compiled_from": "NO_FORMAL_RULE (kompilasi ter-review belum "
                             "tersedia — jalur PROSA/UNRESOLVED)"}
