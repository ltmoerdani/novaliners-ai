"""Binding snapshot (int 16 §R6-B): every important decision/checkpoint stores its BASIS — state version, Goal,
knowledge, rules/mechanisms, model, prompt, and contract — so an old checkpoint does not silently use
newer rules, and a decision can be EXPLAINED against its basis.

What is guaranteed: the basis is recorded and comparable (did knowledge/prompts change since the checkpoint?).
What is NOT guaranteed: byte-identical replay of LLM output — not claimed.
"""
from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any

from core.reasoning.contract import NM_CONTRACT_VERSION
from core.semantic.candidate import CANDIDATE_VERSION
from core.semantic.contract import CONTRACT_VERSION as SO_VERSION

_ROOT = Path(__file__).resolve().parent.parent


def _h(data: bytes | str) -> str:
    return hashlib.sha1(data if isinstance(data, bytes) else data.encode()).hexdigest()[:12]


def _file_hash(rel: str) -> str:
    p = _ROOT / rel
    return _h(p.read_bytes()) if p.exists() else "absent"


def state_version(s: Any) -> str:
    """Fingerprint of the ACTIVE claims (id+version). Changes when a claim is new/replaced; not when only time passes."""
    nodes = (getattr(s, "state_graph", None) or {}).get("nodes") or {}
    active = sorted((n["id"], int(n.get("version") or 1)) for n in nodes.values()
                    if (n.get("status") or "active") == "active")
    return "sv-" + _h(repr(active))


def llm_identity(llm: Any) -> dict[str, str]:
    return {"provider": str(getattr(llm, "name", "") or type(llm).__name__),
            "model": str(getattr(llm, "model", "") or "")}


def prompt_versions() -> dict[str, str]:
    from core.reasoning.reasoner import REASONER_SYSTEM
    from core.semantic.observation import OBSERVATION_SYSTEM
    return {"observation": _h(OBSERVATION_SYSTEM), "reasoner": _h(REASONER_SYSTEM)}


def knowledge_versions() -> dict[str, str]:
    from engine.knowledge import kb_sha256
    return {"kb": kb_sha256(), "rule_activation": _file_hash("ontology/knowledge/rule_activation.json"),
            "mechanisms": _file_hash("ontology/mechanisms.json"),
            "registry_rules": _file_hash("ontology/registry/requirement_registry.json")}


def _observation_revision(s: Any) -> str | None:
    """The accepted-observation digest at binding time (check-ins + action outcomes + Move
    observations). Best-effort: a missing projection must not break checkpoint creation."""
    try:
        from app.experience_contract import observation_revision
        return observation_revision(s)
    except Exception:  # noqa: BLE001
        return None


def _observation_fingerprint(s: Any) -> str | None:
    try:
        from app.experience_contract import observation_fingerprint
        return observation_fingerprint(s)
    except Exception:  # noqa: BLE001
        return None


def build_binding(s: Any, llm: Any = None, *, now: int | None = None) -> dict[str, Any]:
    goal = getattr(s, "goal", None) or {}
    ev = [e.id for e in getattr(s, "evidence", []) if not getattr(e, "superseded", False)]
    # H1 (Phase 6.1 hotfix): which superseded claims were ALREADY accounted for at checkpoint time.
    # Without this snapshot the preview could only ever ask "is any evidence superseded?" - a question
    # that stays true forever - so a map kept offering (and paying for) reassessment with no new
    # correction. Checkpoints created before this field exist without it and are handled conservatively
    # in app.main._reassess_facts (never silently read as "no change").
    ev_superseded = sorted(
        getattr(e, "id", "") for e in getattr(s, "evidence", [])
        if getattr(e, "superseded", False) and getattr(e, "id", ""))
    body = {
        "state_version": state_version(s),
        "goal_id": goal.get("goal_id", ""), "goal_version": goal.get("version"),
        "knowledge": knowledge_versions(),
        "model": llm_identity(llm) if llm is not None else {"provider": "", "model": ""},
        "prompts": prompt_versions(),
        "contracts": {"semantic": SO_VERSION, "decision": NM_CONTRACT_VERSION, "candidate": CANDIDATE_VERSION},
        "source_evidence_refs": ev,
        "superseded_evidence_refs": ev_superseded,   # H1: supersessions this checkpoint already absorbed
        # P0/NC-06: a reported outcome or a durable check-in is an accepted OBSERVATION. Its
        # digest is bound here so reevaluate-preview can tell whether a material observation
        # arrived since this checkpoint — without treating a checked box as an observation.
        "observation_revision": _observation_revision(s),
        "observation_fingerprint": _observation_fingerprint(s),   # Phase 6.2.1: content-complete digest
        "ts": int(now if now is not None else time.time()),
    }
    stable = {k: v for k, v in body.items() if k not in ("ts", "model")}
    body["binding_id"] = "bd-" + _h(repr(sorted(stable.items(), key=lambda kv: kv[0])))
    return body


def knowledge_changed(binding_a: dict | None, binding_b: dict | None) -> bool:
    if not binding_a or not binding_b:
        return False
    return binding_a.get("knowledge") != binding_b.get("knowledge")
