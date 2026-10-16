"""LLM port (core) — the provider-agnostic structured-output contract + plumbing.

Phase B / P0.2b (internal-docs §9): this module used to be `providers/base.py`. The generic
engine (`core/stages/knowledge_rules.py`) imports it, so core would depend on the adapter infra layer —
a layer inversion (F6) caught by the import-linter contract. The port moved inside; the adapters
(`providers/gemini.py`, `vertex.py`, `mock.py`) still extend `LLMProvider` through the
`providers/base.py` shim.

Pattern: Template Method — the port defines `raw_json()` (adapters must override) and provides
`structured_call()` (parse + validate + retry + deviation normalization) so no adapter duplicates
handling of malformed LLM output.

Rules (internal-docs §2.2):
- Always request JSON + a schema; do NOT duplicate the full schema in the prompt (field instructions suffice).
- Output MUST be validated with Pydantic; failure → retry (max 2) → raise.
- Low temperature for reproducibility.
"""
from __future__ import annotations

import copy
import hashlib
import json
import logging
import re
import threading
import typing
from collections import Counter
from dataclasses import dataclass
from typing import Type, TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)

log = logging.getLogger(__name__)

MAX_RETRIES = 2  # the 16 Oct incident (c21ccde618be turn 8): EDIT-BASED repair CONVERGED
# (9 errors → 1 error) but ran out of budget at 2 attempts. 3 attempts leave room to
# converge; fast providers (vertex ≈4-9s) make the extra cost small.

# ═══ MC01-1 (audit CIR-MC01 P0-A): NORMALIZATION AUTHORITY BOUNDARY ═══
# SHAPE_REPAIR   = mechanical fixes proven not to change meaning — applied,
#                  every change recorded as a diff with a rule name.
# MEANING_REPAIR = semantic decisions (role inference, relation-kind mapping, revision-kind
#                  filling, critical↔nonblocking moves, focus selection, cross-vocabulary
#                  intent/evidence) — NEVER applied by the normalizer; detected as a
#                  SemanticDefect and returned to the MODEL via targeted repair (int 19 §12.3).
#                  Repair exhausted = honest failure, no tricks.
NORM_STATS: Counter = Counter()
_NORM_LOCK = threading.Lock()


def _stat(key: str) -> None:
    with _NORM_LOCK:
        NORM_STATS[key] += 1


@dataclass(frozen=True)
class SemanticDefect:
    """A semantic decision that must be returned to the model (not the normalizer)."""

    code: str          # MC01-M01 etc.
    path: str          # location in the payload (claims.0.role)
    detail: str        # what was observed
    instruction: str   # the decision the MODEL must make


class _DefectError(Exception):
    """Internal signal: the payload contains semantic decisions outside the normalizer's authority."""

    def __init__(self, defects: list[SemanticDefect]):
        super().__init__("; ".join(f"{d.code}@{d.path}" for d in defects))
        self.defects = defects


_INTROSPECT_CACHE: dict[tuple[str, str], tuple[str, ...] | None] = {}


def _literal_values(model_cls: type[BaseModel] | None, field: str) -> tuple[str, ...] | None:
    """The Literal values of a Pydantic model field (introspection — no domain contract imports)."""
    if model_cls is None:
        return None
    key = (f"{model_cls.__module__}.{model_cls.__qualname__}", field)
    if key not in _INTROSPECT_CACHE:
        try:
            args = [a for a in typing.get_args(model_cls.model_fields[field].annotation)
                    if isinstance(a, str)]
            _INTROSPECT_CACHE[key] = tuple(args) if args else None
        except (KeyError, AttributeError):
            _INTROSPECT_CACHE[key] = None
    return _INTROSPECT_CACHE[key]


def _item_model(schema: type[BaseModel] | None, field: str) -> type[BaseModel] | None:
    """list[X] → X when X is a BaseModel (e.g. claims → ObservedClaim)."""
    if schema is None:
        return None
    try:
        ann = schema.model_fields[field].annotation
    except KeyError:
        return None
    for a in typing.get_args(ann):
        if isinstance(a, type) and issubclass(a, BaseModel):
            return a
    return None


def _nested_model(model_cls: type[BaseModel] | None, field: str) -> type[BaseModel] | None:
    """X / Optional[X] → X when X is a BaseModel (e.g. quantity → Quantity)."""
    if model_cls is None:
        return None
    try:
        ann = model_cls.model_fields[field].annotation
    except KeyError:
        return None
    if isinstance(ann, type) and issubclass(ann, BaseModel):
        return ann
    for a in typing.get_args(ann):
        if isinstance(a, type) and issubclass(a, BaseModel):
            return a
    return None


def _case_value(value: str, allowed: tuple[str, ...] | None) -> str | None:
    """Capitalization/whitespace correction ONLY ('Claim'→'claim', 'fact'→'FACT'): the canonical
    form is returned when it matches case-insensitively with EXACTLY ONE literal.
    Synonyms/other vocabulary → None (a MEANING_REPAIR matter, not the normalizer's)."""
    if not allowed or not isinstance(value, str) or not value.strip():
        return None
    v = value.strip()
    if v != value and v in allowed:
        return v
    hits = [a for a in allowed if a.casefold() == v.casefold()]
    return hits[0] if len(hits) == 1 and hits[0] != value else None


def _norm_tls(provider: "LLMProvider") -> threading.local:
    """Per-instance threading.local for normalization telemetry (the _sid_tls pattern)."""
    tls = getattr(provider, "_norm_tls_obj", None)
    if tls is None:
        tls = threading.local()
        setattr(provider, "_norm_tls_obj", tls)
    return tls


_FENCE_RE = re.compile(r"^\s*```[A-Za-z]*\s*\n?(.*?)\n?\s*```\s*$", re.DOTALL)


def strip_code_fences(raw: str) -> str:
    """Strip markdown fences (```json ... ```) that gateways often add.

    Not a retry: `json.loads("```json\\n{...}\\n```")` FAILS, then the base retry runs once
    with a "fix it" prompt — wasting one call per turn. Cheaper to clean here.
    """
    s = (raw or "").strip()
    if not s.startswith("```"):
        return s
    m = _FENCE_RE.match(s)
    return m.group(1).strip() if m else s.strip("`").strip()


def _sid_tls(provider: "LLMProvider") -> threading.local:
    """Per-instance threading.local, lazy.

    Deliberately does not require adapters to call `super().__init__()` — some
    providers (and the evals fakes) have their own __init__.
    """
    tls = getattr(provider, "_sid_tls_obj", None)
    if tls is None:
        tls = threading.local()
        setattr(provider, "_sid_tls_obj", tls)
    return tls


class LLMProvider:
    name: str = "base"
    # era-7 (internal-docs §10): determinism_mode — when True, the provider uses
    # the lowest possible temperature (ideally 0) for the core calls (evidence
    # extraction + diagnosis). Goal: reduce cross-run variance that moved the
    # DoD between 17/19 and 19/19 on identical input.
    # Default False = the old behavior (LLM_TEMPERATURE env).
    determinism_mode: bool = False

    def set_determinism(self, on: bool = True) -> None:
        """Enable/disable deterministic mode (temperature ~0)."""
        self.determinism_mode = on

    def raw_json(self, system: str, user: str) -> str:
        raise NotImplementedError

    def use_session(self, session_id: str | None) -> None:
        """Mark the active conversation session FOR THE CALLING THREAD.

        G2a (23 Sep 2026): adapters used to store the session id in INSTANCE state
        while the client is a process singleton (`llm/runtime.py::_ACTIVE`). Two overlapping
        requests for different sessions could swap session headers — and KB group
        parallelization (E2) widened that window. Thread-local closes it and lets
        each worker set its own session.
        """
        if session_id:
            _sid_tls(self).value = str(session_id)

    def current_session_id(self) -> str:
        """The effective session id for THIS thread ('' when never set)."""
        return getattr(_sid_tls(self), "value", "") or ""

    def structured_call(self, schema: Type[T], system: str, user: str, retries: int = MAX_RETRIES) -> T:
        """Call the LLM, parse JSON, validate into `schema`. Mechanical SHAPE_REPAIR pre-validation;
        semantic decisions (MEANING_REPAIR) are NEVER made by the normalizer — they go back to the
        model via targeted repair (MC01-1). Repair exhausted = honest failure, no silent meaning change."""
        tls = _norm_tls(self)
        prompt = user
        last_err: Exception | None = None
        last_fixed: dict | None = None   # the 16 Oct incident: the model repeated the same error
        # because repair regenerates the whole output — keep the last output for EDIT-BASED repair
        for attempt in range(retries + 1):
            raw = self.raw_json(system, prompt)
            try:
                data = self._parse_json_payload(raw)
            except json.JSONDecodeError as e:
                last_err = e
                log.warning(
                    "structured_call RETRY penuh (JSON invalid) attempt %d/%d schema=%s raw_len=%d err=%s",
                    attempt + 1, retries + 1, schema.__name__, len(raw or ""), str(e)[:200])
                tls.telemetry = self._norm_telemetry(schema, raw, [], [], attempt + 1, "repairing")
                prompt = self._repair_prompt(user, schema, [f"- output bukan JSON valid: {str(e)[:200]}"])
                continue
            fixed, shape_diffs = self._shape_repair(schema, data)
            if isinstance(fixed, dict):
                last_fixed = fixed
            defects = self._semantic_defects(schema, fixed)
            tls.telemetry = self._norm_telemetry(schema, raw, shape_diffs, defects, attempt + 1, "pending")
            for d in shape_diffs:
                _stat(f"shape:{d['rule']}")
            if defects:
                last_err = _DefectError(defects)
                for d in defects:
                    _stat(f"defect:{d.code}")
                log.warning(
                    "structured_call MEANING_DEFECT → repair terarah attempt %d/%d schema=%s codes=%s",
                    attempt + 1, retries + 1, schema.__name__, [d.code for d in defects])
                prompt = self._repair_prompt(user, schema, [
                    f"- {d.path}: {d.detail} — WAJIB diputuskan Anda: {d.instruction}" for d in defects],
                    previous=last_fixed)
                continue
            try:
                out = schema.model_validate(fixed)
                tls.telemetry["outcome"] = "accepted" if attempt == 0 else "repaired"
                return out
            except ValidationError as e:
                last_err = e
                log.warning(
                    "structured_call RETRY penuh (validasi gagal) attempt %d/%d schema=%s tipe=%s "
                    "raw_len=%d err=%s",
                    attempt + 1, retries + 1, schema.__name__, type(e).__name__,
                    len(raw or ""), str(e)[:200])
                prompt = self._repair_prompt(user, schema, self._pydantic_details(e), previous=last_fixed)
        _stat("outcome:failed")
        raise RuntimeError(f"[{self.name}] structured_call gagal setelah {retries + 1} percobaan: {last_err}")

    # ─────────────────────────────────────────────────────────────────────────────
    # MC01-1: SHAPE_REPAIR (mechanical fixes + diff) & MEANING_REPAIR (detecting
    # semantic decisions → SemanticDefect → targeted repair back to the model).
    # ─────────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _shape_repair(schema: Type[BaseModel], data: dict) -> tuple[dict, list[dict]]:
        """SHAPE_REPAIR — mechanical fixes proven not to change meaning.

        Works on a deepcopy copy (the raw payload is NEVER mutated); every change is
        recorded as a diff {rule, path, before, after}. No semantic decisions here —
        see _semantic_defects."""
        if not isinstance(data, dict):
            return data, []          # a non-object payload → honest validation rejection
        fixed = copy.deepcopy(data)
        diffs: list[dict] = []

        def _d(rule: str, path: str, before, after) -> None:  # noqa: ANN001
            diffs.append({"rule": rule, "path": path,
                          "before": json.dumps(before, ensure_ascii=False, default=str)[:120],
                          "after": json.dumps(after, ensure_ascii=False, default=str)[:120]})

        # (j) list fields sent as a string → wrapped into [string] (move_design nested + root)
        def _wrap_list(d: dict, base: str) -> None:
            if not isinstance(d, dict):
                return
            for k in ("preconditions", "expected_evidence", "completion_criteria", "constraints"):
                v = d.get(k)
                if isinstance(v, str):
                    d[k] = [v] if v.strip() else []
                    _d("wrap_list", f"{base}.{k}".lstrip("."), v, d[k])
        _wrap_list(fixed.get("move_design"), "move_design")
        _wrap_list(fixed, "")

        # MC02-RC01: a boundless 'range' label is no longer "fixed" by the normalizer — `value_kind`
        # states PRECISION (meaning), not shape. Detection → defect MC02-M10; the MODEL chooses
        # (fill low+high, or switch to 'approximate'), see _semantic_defects.

        # OPEN-L3: None keys on defaulting string fields (period/unit) → pop, the contract default applies
        for cl in (fixed.get("claims") or []):
            q = cl.get("quantity") if isinstance(cl, dict) else None
            if isinstance(q, dict):
                for k in ("period", "unit"):
                    if q.get(k) is None and k in q:
                        q.pop(k)
                        _d("pop_null_default", f"claims.quantity.{k}", None, "<contract-default>")

        # (c) the ghost `proposed_move` field (an extra=forbid contract). Dropped ONLY when proven
        # REDUNDANT — its value equals `proposed_focus` or one of the candidate ids declared by the
        # proposal itself (RC-01: lossless evidence, not an assumption). When its value differs,
        # the field is LEFT so the contract rejects honestly via targeted repair naming the valid
        # field (deleting it could discard an intent not yet represented in `proposed_focus`).
        if "proposed_move" in fixed:
            _ghost = fixed.get("proposed_move")
            _known_ids = {str(fixed.get("proposed_focus") or "")} | {
                c for c in (fixed.get("candidate_uncertainty_ids") or []) if isinstance(c, str)}
            if isinstance(_ghost, str) and _ghost and _ghost in _known_ids:
                _d("drop_redundant_ghost_field", "proposed_move", _ghost, None)
                fixed.pop("proposed_move")

        # MC02-RC01: a `goal_ref` placeholder (e.g. the literal "goal") is NOT silently blanked —
        # a Goal reference is a meaning decision. Detection → defect MC02-M11 (the model echoes
        # the real id or blanks it), see _semantic_defects.

        elig = fixed.get("checkpoint_eligibility")
        if isinstance(elig, dict):
            # (a) unknown ids shaped {"id": ...} → str (contract: list of str)
            for k in ("critical_unknown_ids", "nonblocking_unknown_ids"):
                ids = elig.get(k)
                if isinstance(ids, list):
                    new = [x.get("id") if isinstance(x, dict) and isinstance(x.get("id"), str) else x
                           for x in ids]
                    if new != ids:
                        elig[k] = new
                        _d("id_obj_to_str", f"checkpoint_eligibility.{k}", ids, new)
            # (b) decision_imp* key typos → decision_impact (key name only; values untouched)
            margs = elig.get("marginal_information_value")
            if isinstance(margs, list):
                for m in margs:
                    if not isinstance(m, dict):
                        continue
                    for bad in [k for k in list(m)
                                if k.startswith("decision_imp") and k != "decision_impact"]:
                        if "decision_impact" not in m:
                            m["decision_impact"] = m.pop(bad)
                            _d("key_typo", f"marginal.{bad}", bad, "decision_impact")
                        else:
                            m.pop(bad)
                            _d("drop_dup_typo_key", f"marginal.{bad}", bad, None)
            # MC02-RC01: `STATE_ONLY` inconsistency + offers/recommendations are no longer
            # silently downgraded (the level = a sufficiency claim, not shape). Detection → defect
            # MC02-M12 in _semantic_defects; the model decides the correct level.

        # applied_to ARRAY/null → a string joined with ", " (content serialization preserved;
        # the citation parser expects the string form — observed A/B deviation 23 Sep)
        for _key in ("matches", "anti_patterns"):
            for _item in fixed.get(_key) or []:
                if isinstance(_item, dict) and "applied_to" in _item:
                    _ao = _item["applied_to"]
                    if isinstance(_ao, list):
                        _item["applied_to"] = ", ".join(str(_x) for _x in _ao)
                        _d("join_applied_to", f"{_key}.applied_to", _ao, _item["applied_to"])
                    elif _ao is None:
                        _item["applied_to"] = ""
                        _d("null_applied_to", f"{_key}.applied_to", None, "")

        # CAPITALIZATION/whitespace correction for Literal fields (purely mechanical;
        # synonyms/cross-vocabulary are NOT case-fixes → the _semantic_defects path)
        claim_cls = _item_model(schema, "claims")
        qty_cls = _nested_model(claim_cls, "quantity")
        rel_cls = _item_model(schema, "relations")
        tag_cls = _item_model(schema, "intent_tags")
        ev_cls = _item_model(schema, "evidence")

        def _fix_literal(container: dict, base: str, field: str,
                         allowed: tuple[str, ...] | None) -> None:
            if not isinstance(container, dict) or allowed is None:
                return
            v = container.get(field)
            if isinstance(v, str):
                cv = _case_value(v, allowed)
                if cv is not None and cv != v:
                    container[field] = cv
                    _d("case_fix", f"{base}.{field}", v, cv)

        for i, cl in enumerate(fixed.get("claims") or []):
            if not isinstance(cl, dict):
                continue
            for fld in ("role", "aspect", "tense", "epistemic", "revision_kind"):
                _fix_literal(cl, f"claims.{i}", fld, _literal_values(claim_cls, fld))
            if isinstance(cl.get("quantity"), dict):
                _fix_literal(cl["quantity"], f"claims.{i}.quantity", "value_kind",
                             _literal_values(qty_cls, "value_kind"))
        for i, rel in enumerate(fixed.get("relations") or []):
            _fix_literal(rel, f"relations.{i}", "kind", _literal_values(rel_cls, "kind"))
        for i, t in enumerate(fixed.get("intent_tags") or []):
            _fix_literal(t, f"intent_tags.{i}", "kind", _literal_values(tag_cls, "kind"))
        for i, ev in enumerate(fixed.get("evidence") or []):
            _fix_literal(ev, f"evidence.{i}", "level", _literal_values(ev_cls, "level"))
        return fixed, diffs

    @staticmethod
    def _semantic_defects(schema: Type[BaseModel], data: dict) -> list[SemanticDefect]:
        """MEANING_REPAIR — detect semantic decisions the normalizer must NOT make
        (audit CIR-MC01 P0-A). Defects go back to the model via targeted repair;
        never applied silently. Failed repair = honest failure."""
        if not isinstance(data, dict):
            return []
        defects: list[SemanticDefect] = []
        claims = [c for c in (data.get("claims") or []) if isinstance(c, dict)]
        claim_cls = _item_model(schema, "claims")
        roles = _literal_values(claim_cls, "role")
        for i, cl in enumerate(claims):
            r = cl.get("role")
            if not isinstance(r, str) or not r.strip() or (roles and r.strip() not in roles):
                defects.append(SemanticDefect(
                    "MC01-M01", f"claims.{i}.role", f"role {r!r} bukan nilai sah {list(roles or [])}",
                    "pilih role sah yang sesuai maksud klaim; NEGASI/pembatalan klaim lama TIDAK lewat "
                    "role — gunakan supersedes='<id kanonik lama>' + revision_kind='negation' "
                    "+ revision_reason pada klaim pengganti"))
        rel_cls = _item_model(schema, "relations")
        kinds = _literal_values(rel_cls, "kind")
        for i, rel in enumerate(data.get("relations") or []):
            if not isinstance(rel, dict):
                continue
            k = rel.get("kind")
            if not isinstance(k, str) or not k.strip() or (kinds and k.strip() not in kinds):
                defects.append(SemanticDefect(
                    "MC01-M02", f"relations.{i}.kind", f"kind {k!r} di luar enum sah {list(kinds or [])}",
                    "pilih relasi sah yang sesuai makna (pertentangan → 'contradicts', asal-usul → "
                    "'derived_from'); jangan kirim sinonim di luar enum"))
        _rk_fallback = ("correction", "refinement", "confirmation", "negation")
        revs = _literal_values(claim_cls, "revision_kind") or _rk_fallback
        for i, cl in enumerate(claims):
            sup, rk = cl.get("supersedes"), cl.get("revision_kind")
            if (sup and not rk) or (not sup and rk):
                defects.append(SemanticDefect(
                    "MC01-M03", f"claims.{i}.supersedes",
                    f"supersedes={sup!r} revision_kind={rk!r} (kontrak: keduanya bersama-sama)",
                    f"isi revision_kind dari {list(revs)} sesuai maksud revisi (pembatalan='negation', "
                    "perbaikan nilai='correction', penajaman='refinement', penegasan='confirmation') "
                    "beserta revision_reason — atau kosongkan keduanya bila bukan revisi"))
        ft = str(data.get("focus_type") or "")
        pf = str(data.get("proposed_focus") or "").strip()
        if ft == "uncertainty" and not pf:
            cands = [c for c in (data.get("candidate_uncertainty_ids") or []) if isinstance(c, str) and c]
            if cands:
                defects.append(SemanticDefect(
                    "MC01-M04", "proposed_focus",
                    "kosong padahal proposal membawa kandidat ketidakpastian",
                    f"pilih SATU id yang paling bernilai keputusan dari {cands} (jangan dikosongkan)"))
        if ft == "hypothesis" and not pf:
            hyps = [h.get("id") for h in (data.get("competing_hypotheses") or [])
                    if isinstance(h, dict) and h.get("id")]
            if hyps:
                defects.append(SemanticDefect(
                    "MC01-M04", "proposed_focus", "kosong padahal proposal membawa hipotesis bersaing",
                    f"pilih SATU id hipotesis dari {hyps}"))
        elig = data.get("checkpoint_eligibility")
        if isinstance(elig, dict):
            margs = [m for m in (elig.get("marginal_information_value") or []) if isinstance(m, dict)]
            by_id = {m.get("uncertainty_id"): m for m in margs}

            def _cf(i: str) -> str:
                m = by_id.get(i)
                return str(m.get("counterfactual") or "").strip() if m else ""

            def _now(i: str) -> bool:
                m = by_id.get(i)
                return bool(m) and m.get("answerability") == "now_conversation"

            crit = [i for i in (elig.get("critical_unknown_ids") or []) if isinstance(i, str)]
            nonb = [i for i in (elig.get("nonblocking_unknown_ids") or []) if isinstance(i, str)]
            # MC02-RC01: separate the TWO causes so the proven root cause comes from telemetry, not
            # interpretation. M05a = registered `critical` while not material-answerable-now
            # (per-id reason recorded: no entry / empty counterfactual / whatever answerability);
            # M05b = registered `nonblocking` while material & answerable now (must be critical).
            a = []
            for i in crit:
                if not by_id.get(i):
                    a.append(f"{i}(no marginal entry)")
                elif not _cf(i):
                    a.append(f"{i}(empty counterfactual)")
                elif not _now(i):
                    a.append(f"{i}(answerability={by_id[i].get('answerability')})")
            b = [i for i in nonb if _cf(i) and _now(i)]
            if a:
                meas = [i for i in crit if by_id.get(i)
                        and by_id[i].get("answerability") == "needs_measurement"]
                defects.append(SemanticDefect(
                    "MC02-M05a", "checkpoint_eligibility.critical_unknown_ids",
                    "didaftarkan critical padahal bukan material-yang-dapat-dijawab-sekarang: "
                    + "; ".join(a)
                    + (f" · butuh pengukuran: {meas}" if meas else ""),
                    "critical HANYA untuk kebutuhan yang material DAN dapat dijawab sekarang "
                    "(answerability=now_conversation). Kebutuhan MATERIAL yang butuh pengukuran/data luar "
                    "masuk `nonblocking_unknown_ids` dengan counterfactual TETAP terisi (materialitas tidak "
                    "hilang — yang berubah hanya answerability), dan langkahnya ACTION + move_design, "
                    "bukan QUESTION pada kebutuhan itu"))
            if b:
                defects.append(SemanticDefect(
                    "MC02-M05b", "checkpoint_eligibility.nonblocking_unknown_ids",
                    f"didaftarkan nonblocking padahal material & dapat dijawab sekarang: {b}",
                    "pindahkan id tersebut ke `critical_unknown_ids` — keduanya material-yang-dapat-dijawab-"
                    "sekarang — dan pastikan entri marginal-nya menyebut keputusan yang benar-benar berubah"))
        # MC02-RC01 — ID fields must contain IDs, not sentences; quantity/level shape deviations
        # are no longer "fixed" by the normalizer (moved to the authoritative defect path).
        _ft = str(data.get("focus_type") or "").strip()
        _pf = str(data.get("proposed_focus") or "").strip()
        if _ft == "uncertainty":
            _decl = [c for c in (data.get("candidate_uncertainty_ids") or [])
                     if isinstance(c, str) and c]
        elif _ft == "hypothesis":
            _decl = [h.get("id") for h in (data.get("competing_hypotheses") or [])
                     if isinstance(h, dict) and h.get("id")]
        else:
            _decl = []
        if _pf and _ft in ("uncertainty", "hypothesis"):
            if _decl and _pf not in _decl:
                defects.append(SemanticDefect(
                    "MC02-M09", "proposed_focus",
                    f"{_pf[:60]!r} bukan salah satu id yang Anda deklarasikan {_decl}",
                    "isi TEPAT SATU id dari daftar itu — bukan gabungan dua id, bukan kalimat penalaran; "
                    "alasan/pertimbangan masuk ke move_text atau information_value_rationale"))
            elif not _decl and len(_pf.split()) > 1:
                defects.append(SemanticDefect(
                    "MC02-M09", "proposed_focus", f"{_pf[:60]!r} memuat lebih dari satu kata",
                    "isi TEPAT SATU id legal — fokus adalah id, bukan kalimat"))
        for _i, _cl in enumerate(claims):
            _q = _cl.get("quantity")
            if isinstance(_q, dict) and _q.get("value_kind") == "range" \
                    and (_q.get("low") is None or _q.get("high") is None):
                defects.append(SemanticDefect(
                    "MC02-M10", f"claims.{_i}.quantity",
                    f"value_kind='range' tanpa batas lengkap (low={_q.get('low')!r}, "
                    f"high={_q.get('high')!r})",
                    "isi low DAN high (batas bawah/atas), atau ubah value_kind ke 'approximate' dengan satu "
                    "`value` — 'range' tanpa batas bukan pernyataan yang dapat disimpan"))
            # MC02-M10b (the 16 Oct incident, sessions 3a16a9c3b6ce/7989259580af): a 'range' CARRYING
            # `value` passed the old M10 then died in the pydantic validator with a short message
            # ("range requires low+high without value") — generic repair had no idea what to remove.
            if isinstance(_q, dict) and _q.get("value_kind") == "range" \
                    and _q.get("value") is not None:
                defects.append(SemanticDefect(
                    "MC02-M10b", f"claims.{_i}.quantity",
                    f"value_kind='range' tidak boleh memuat 'value' (value={_q.get('value')!r}, "
                    f"low={_q.get('low')!r}, high={_q.get('high')!r})",
                    "HAPUS field 'value' dan biarkan hanya low+high — atau bila user hanya menyebut SATU "
                    "angka, ubah value_kind ke 'approximate' dengan 'value' itu dan hapus low/high"))
            # MC02-M19: exact/approximate/bound carrying low/high — the pydantic validator
            # rejects it ("... requires value without low/high"); an explicit instruction
            # so repair knows the direction.
            if isinstance(_q, dict) and _q.get("value_kind") != "range" \
                    and (_q.get("low") is not None or _q.get("high") is not None):
                defects.append(SemanticDefect(
                    "MC02-M19", f"claims.{_i}.quantity",
                    f"value_kind={_q.get('value_kind')!r} hanya boleh satu 'value' "
                    f"(value={_q.get('value')!r}, low={_q.get('low')!r}, high={_q.get('high')!r})",
                    "pilih SATU angka sebagai 'value' dan HAPUS low/high — bila user benar-benar "
                    "menyebut rentang, ubah value_kind ke 'range' dengan low+high tanpa value"))
            # MC02-M18 (the 16 Oct incident, session 3b12b44f8891 turn 22:13): a role='gap' claim
            # with a quantity was rejected by the validator ("gap carries no quantity") —
            # a gap = the ABSENCE of data.
            if str(_cl.get("role") or "") == "gap" and _q is not None:
                defects.append(SemanticDefect(
                    "MC02-M18", f"claims.{_i}",
                    f"role='gap' tidak boleh membawa quantity (quantity={_q!r})",
                    "HAPUS field quantity dari klaim gap ini — ATAU bila user benar-benar MENYATAKAN "
                    "sebuah angka (bukan ketidaktahuan), ubah role-nya menjadi 'claim' dan pertahankan "
                    "quantity-nya; keduanya keputusan Anda dari kutipan user"))
            # MC02-M20 (the 16 Oct incident, 7989259580af & c21ccde618be turn 8): an `aspect` value outside
            # the enum escaped pydantic with only a literal message — flash-tier models kept it
            # even after edit-based repair (9 errors → exactly 1 error left, right here).
            _ASPECTS = ("", "preference", "concern", "constraint",
                        "intention", "plan", "behavior", "conflict")
            _asp = _cl.get("aspect")
            if _asp is not None and _asp not in _ASPECTS:
                defects.append(SemanticDefect(
                    "MC02-M20", f"claims.{_i}.aspect",
                    "aspect=" + repr(_asp) + " BUKAN nilai sah — hanya: "
                    + " | ".join((a or "''(kosong)") for a in _ASPECTS),
                    "GANTI nilai aspect menjadi salah satu nilai sah di atas — atau KOSONGKAN ("
                    "string kosong) bila tidak ada yang pas; aspect adalah pengayaan opsional, "
                    "bukan wajib"))
        _gr = str(data.get("goal_ref") or "").strip()
        if _gr and (_gr.lower() in ("goal", "goals", "none", "null", "n/a", "-")
                    or len(_gr.split()) > 1):
            defects.append(SemanticDefect(
                "MC02-M11", "goal_ref", f"{_gr[:60]!r} bukan id Goal",
                "echo TEPAT `goal_id` dari snapshot, atau kosongkan bila tidak ada Goal aktif — "
                "jangan kirim placeholder"))
        if isinstance(elig, dict) and str(elig.get("level") or "") == "STATE_ONLY" \
                and (elig.get("can_offer_checkpoint")
                     or str(elig.get("recommendation") or "").strip()):
            defects.append(SemanticDefect(
                "MC02-M12", "checkpoint_eligibility",
                f"level=STATE_ONLY tetapi can_offer_checkpoint={elig.get('can_offer_checkpoint')!r} / "
                "recommendation terisi",
                "putuskan salah satu: STATE_ONLY (can_offer_checkpoint=false, recommendation kosong) "
                "atau naikkan level bila lima syarat PROVISIONAL_READY benar-benar terpenuhi"))
        tags = data.get("intent_tags")
        if isinstance(tags, list) and tags and isinstance(tags[0], str):
            defects.append(SemanticDefect(
                "MC01-M08", "intent_tags", "berupa list of string (kontrak: objek per tag)",
                "kirim objek lengkap (kind/quote/normalized/confidence); kind hanya "
                "FACT|GOAL|ASSUMPTION|PREFERENCE — bukan kosakata level evidence"))
        else:
            tag_kinds = _literal_values(_item_model(schema, "intent_tags"), "kind")
            for i, t in enumerate(tags or []):
                if not isinstance(t, dict):
                    continue
                k = t.get("kind")
                if not isinstance(k, str) or not k.strip() or (tag_kinds and k.strip() not in tag_kinds):
                    defects.append(SemanticDefect(
                        "MC01-M06", f"intent_tags.{i}.kind",
                        f"kind {k!r} di luar {list(tag_kinds or [])}",
                        "pilih jenis niat yang sah — tidak dipetakan otomatis dari kosakata lain"))
        evs = data.get("evidence")
        if isinstance(evs, list) and evs and isinstance(evs[0], str):
            defects.append(SemanticDefect(
                "MC01-M08", "evidence", "berupa list of string (kontrak: objek per evidence)",
                "kirim objek lengkap (id/signal/level/topic); level hanya "
                "transactional|behavioral|self_reported|outcome"))
        else:
            ev_levels = _literal_values(_item_model(schema, "evidence"), "level")
            for i, ev in enumerate(evs or []):
                if not isinstance(ev, dict):
                    continue
                lv = ev.get("level")
                if not isinstance(lv, str) or not lv.strip() or (ev_levels and lv.strip() not in ev_levels):
                    defects.append(SemanticDefect(
                        "MC01-M07", f"evidence.{i}.level", f"level {lv!r} di luar {list(ev_levels or [])}",
                        "pilih level evidence yang sah — tidak dipetakan otomatis dari kosakata lain"))
        return defects

    def _norm_telemetry(self, schema: Type[BaseModel], raw: str, shape_diffs: list[dict],
                        defects: list[SemanticDefect], attempts: int, outcome: str) -> dict:
        """Per-attempt record (thread-local): the raw payload is NOT copied (privacy) —
        only a short SHA-256 + diff + defect codes: auditable without storing content."""
        return {"schema": schema.__name__,
                "raw_sha": hashlib.sha256((raw or "").encode("utf-8", "ignore")).hexdigest()[:16],
                "shape_diffs": copy.deepcopy(shape_diffs),
                "defects": [{"code": d.code, "path": d.path} for d in defects],
                "attempts": attempts, "outcome": outcome}

    def last_norm_telemetry(self) -> dict | None:
        """The normalization telemetry of the LAST structured_call on this thread."""
        return copy.deepcopy(getattr(_norm_tls(self), "telemetry", None))

    @staticmethod
    def _parse_json_payload(raw: str) -> dict:
        """json.loads + raw_decode salvage (iter-19: prose/trailing data around the JSON)."""
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            dec = json.JSONDecoder()
            raw_s = (raw or "").strip()
            for start in (i for i, ch in enumerate(raw_s) if ch in "{"):
                try:
                    data, _ = dec.raw_decode(raw_s[start:])
                    data = json.loads(raw)  # unused-placeholder
                    return data
                except json.JSONDecodeError:
                    continue
            raise

    @staticmethod
    def _repair_prompt(user: str, schema: Type[BaseModel], details: list[str],
                       previous: dict | None = None) -> str:
        """TARGETED repair: field + rejected value + valid choices (L3 stage-2; MC01-1
        adds the semantic-defect instructions so decisions stay with the model).

        EDIT-BASED (the 16 Oct 2026 incident, session 7989259580af): when the previous
        output is available, the model COPIES IT AS IS and changes ONLY the rejected fields —
        not a full regeneration (which provably repeated the `claims.8.aspect` error twice
        and fell into UNDERSTANDING_FAILED). The fix-value decision stays with the
        model — no silent normalization (the MC01-1 discipline holds)."""
        fields = ", ".join(schema.model_fields.keys())
        base = (f"{user}\n\n---\nOutput sebelumnya INVALID. "
                f"Kembalikan HANYA JSON valid dengan field: {fields}. "
                f"Perbaiki tepat titik ini (field wajib sesuai skema; enum hanya boleh nilai sah):\n"
                + "\n".join(details))
        if previous is not None:
            try:
                prev_json = json.dumps(previous, ensure_ascii=False)
            except (TypeError, ValueError):
                return base
            base += (f"\n\n---\nOutput sebelumnya (JSON) — SALIN APA ADANYA, "
                     f"UBAH HANYA field yang ditolak di atas, JANGAN ubah bagian lain, "
                     f"JANGAN menambah/menghapus item array lain:\n{prev_json}")
        return base

    @staticmethod
    def _pydantic_details(e: ValidationError) -> list[str]:
        detail = []
        for er in e.errors()[:12]:
            loc = ".".join(str(x) for x in er.get("loc", ()))
            inp = str(er.get("input"))[:60]
            detail.append(f"- field {loc!r}: {er.get('msg')} (diterima: {inp!r})")
        return detail or [f"- {str(e)[:500]}"]



def schema_hint(schema_cls: Type[BaseModel]) -> str:
    """Compact schema-field instructions for prompts (not a full schema dump)."""
    lines = []
    for name, f in schema_cls.model_fields.items():
        desc = f.description or ""
        lines.append(f"- {name}: {desc}" if desc else f"- {name}")
    return "\n".join(lines)
