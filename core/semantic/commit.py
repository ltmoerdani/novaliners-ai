"""Deterministic verification + canonical commit of semantic observations (int 16 §R3-D/E,
SC-05, SC-07, SC-09).

Strict separation (RC-03):
- The Verifier does NOT judge "which questions are useful" — it checks integrity:
  event ownership, EXACT quote anchors against the cited event, schema shape,
  existence of referenced claims, and dependency integrity.
- Commit applies claim status transitions (active/superseded/negated) with an
  intact history; the current-view projection only reads active status.

NextMove/planner failure NEVER cancels an observation commit (SC-09, CP-17):
this function is called BEFORE navigation and does not depend on it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from core.semantic.contract import SemanticObservation

# canonical claim status
ST_ACTIVE = "active"
ST_SUPERSEDED = "superseded"
ST_NEGATED = "negated"

_REVISION_TARGET_STATUS = {
    "correction": ST_SUPERSEDED,
    "refinement": ST_SUPERSEDED,
    "negation": ST_NEGATED,
    # confirmation: the target REMAINS active; only the edge confirms
}


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", (t or "")).strip().lower()


class ForeignEventError(ValueError):
    """Event belonging to another session — rejected BEFORE any mutation (SC-05, BC-09, CP-37)."""


class EventProvenanceError(ForeignEventError):
    """Event does not come from this session's valid event history (forged, conflicting
    payload, duplicate seq, unsupported scope). Rejected BEFORE any graph/ledger mutation.
    NOTE: this checks source INTEGRITY, not production-actor authorization (who is allowed to
    send) — that is outside the scope of R3.2."""


_SUPPORTED_SOURCE_KINDS = ("message", "create_map", "outcome_observation")


def _verify_event_provenance(session, event: dict) -> None:
    """Event must be identical to the user event durably recorded on this session."""
    known = [e for e in (getattr(session, "events", None) or [])
             if e.get("event_id") == event.get("event_id")]
    if not known:
        raise EventProvenanceError(
            f"event {event.get('event_id')!r} tidak ada di riwayat sesi {session.id!r}")
    if len(known) > 1:
        raise EventProvenanceError(f"event_id ganda di riwayat sesi: {event.get('event_id')!r}")
    rec = known[0]
    for f in ("session_id", "seq", "role", "kind", "text", "turn"):
        if rec.get(f) != event.get(f):
            raise EventProvenanceError(
                f"event {event.get('event_id')!r} konflik dengan rekaman tahan-lama pada field {f!r}")
    if rec.get("kind") not in _SUPPORTED_SOURCE_KINDS:
        raise EventProvenanceError(f"scope sumber tak didukung: kind={rec.get('kind')!r}")
    seqs = [e.get("seq") for e in session.events if e.get("seq") == rec.get("seq")]
    if len(seqs) > 1:
        raise EventProvenanceError(f"seq {rec.get('seq')} ganda di riwayat sesi (tabrakan id klaim)")


def open_contradictions(graph: dict) -> list[dict]:
    """`contradicts` edge whose both ends are still active — an unresolved contradiction."""
    nodes = (graph or {}).get("nodes") or {}
    out = []
    for e in ((graph or {}).get("edges") or {}).values():
        if e.get("kind") != "contradicts":
            continue
        a, b = nodes.get(e.get("src")), nodes.get(e.get("dst"))
        if a and b and all((n.get("status") or ST_ACTIVE) == ST_ACTIVE for n in (a, b)):
            out.append(e)
    return out


@dataclass
class CommitResult:
    event_id: str
    accepted_claims: list[dict] = field(default_factory=list)
    accepted_edges: list[dict] = field(default_factory=list)
    revisions: list[dict] = field(default_factory=list)
    rejections: list[str] = field(default_factory=list)
    claim_ids: dict[str, str] = field(default_factory=dict)  # local ref -> canonical id

    @property
    def fully_rejected(self) -> bool:
        """Claims were proposed but none passed the verifier — NOT a successful fact commit."""
        return bool(self.rejections) and not self.accepted_claims

    def drift_entry(self, turn: int) -> dict:
        return {
            "turn": turn,
            "event_id": self.event_id,
            "accepted_claims": len(self.accepted_claims),
            "accepted_edges": len(self.accepted_edges),
            "revisions": len(self.revisions),
            "rejections": list(self.rejections),
        }


def verify_and_commit(
    session,
    event: dict,
    obs: SemanticObservation,
) -> CommitResult:
    """Validate + commit ONE observation into the session state graph. Does not call an LLM.

    - Claim quotes MUST be a substring of this event's text (not the global transcript).
    - supersedes MUST be an existing canonical claim id.
    - Cross-turn relations are valid only when both ends are known.
    - Deterministic id from the event: reprocessing is idempotent (same id is skipped).
    """
    if event.get("session_id") != session.id:
        raise ForeignEventError(
            f"event {event.get('event_id')} milik sesi {event.get('session_id')!r}, "
            f"bukan {session.id!r}")
    if event.get("role") != "user":
        raise ForeignEventError(f"event {event.get('event_id')} bukan event user")
    _verify_event_provenance(session, event)   # before any mutation

    graph = getattr(session, "state_graph", None)
    if graph is None:
        graph = {"nodes": {}, "edges": {}}
        setattr(session, "state_graph", graph)
    nodes: dict = graph.setdefault("nodes", {})
    edges: dict = graph.setdefault("edges", {})

    res = CommitResult(event_id=event["event_id"])
    ev_text_norm = _norm(event.get("text", ""))

    # ── claims ───────────────────────────────────────────────────────────────
    for i, c in enumerate(obs.claims, 1):
        cid = f"cl-e{int(event.get('seq', len(nodes))):04d}-{i:03d}"
        if cid in nodes and (nodes[cid].get("provenance") or {}).get("event_id") == event["event_id"]:
            # reprocessing the same event: claims already exist -> idempotent, WITHOUT re-revision
            res.accepted_claims.append(nodes[cid])
            res.claim_ids[c.ref] = cid
            continue
        why = []
        if not (c.subject or "").strip() or not (c.predicate or "").strip():
            why.append("subject/predicate kosong")
        if _norm(c.quote) not in ev_text_norm:
            why.append("quote bukan substring event ini (SC-05)")
        target_status = None
        if c.supersedes:
            tgt = nodes.get(c.supersedes)
            if tgt is None:
                why.append(f"supersedes id tidak dikenal: {c.supersedes}")
            elif (tgt.get("provenance") or {}).get("session") != session.id:
                why.append(f"target revisi bukan milik sesi ini: {c.supersedes}")
            elif tgt.get("status") not in (None, ST_ACTIVE):
                why.append(f"target revisi sudah berstatus {tgt.get('status')}")
            else:
                target_status = _REVISION_TARGET_STATUS.get(c.revision_kind or "", "")
        if why:
            res.rejections.append(f"{c.ref} ({c.role}): " + "; ".join(why))
            continue
        res.claim_ids[c.ref] = cid

        claim = {
            "id": cid,
            "type": c.role,
            "aspect": c.aspect or "",
            "triple": {
                "subject": {"label": c.subject, "normalized": None, "vocabulary_source": None,
                            "confidence": "raw"},
                "predicate": {"label": c.predicate, "normalized": None, "vocabulary_source": None,
                              "confidence": "raw"},
                "object": ({"label": c.object, "confidence": "raw"} if c.object else None),
                "value": (c.quantity.value if c.quantity and c.quantity.value_kind != "range" else None),
                "unit": (c.quantity.unit if c.quantity else None),
            },
            "quantity": (c.quantity.model_dump() if c.quantity else None),
            "tense": c.tense,
            "temporal_context": f"turn {event.get('turn')}",
            "modality": ("hypothetical" if c.role == "assumption"
                         else "hedged" if c.hedge
                         else "aspirational" if (c.tense == "future" or c.role in ("goal", "desire"))
                         else "factual"),
            "hedge": c.hedge,
            "epistemic": c.epistemic,
            "verbatim": c.quote,
            "provenance": {"event_id": event["event_id"], "turn": event.get("turn"),
                           "session": session.id, "source": "semantic_observation"},
            "confidence": ("estimated" if c.epistemic == "estimated"
                           else "measured" if c.epistemic == "measured" else "self_reported"),
            "status": ST_ACTIVE,
            "version": 1,
        }
        if cid in nodes:
            res.rejections.append(f"{c.ref} ({c.role}): id klaim {cid} sudah dipakai event lain")
            res.claim_ids.pop(c.ref, None)
            continue
        nodes[cid] = claim
        res.accepted_claims.append(claim)

        if c.supersedes and target_status is not None:
            tgt = nodes[c.supersedes]
            if target_status:   # confirmation ("") does not change the target status; only the relation
                tgt["status"] = target_status
                tgt["superseded_by"] = cid
                tgt["version"] = int(tgt.get("version") or 1) + 1
            else:
                tgt.setdefault("confirmed_by", []).append(cid)
            eid = f"e-e{int(event.get('seq', 0)):04d}-r{i:03d}"
            edges[eid] = {
                "id": eid,
                "src": cid,
                "dst": c.supersedes,
                "kind": ("confirms" if c.revision_kind == "confirmation" else "supersede"),
                "provenance": {"event_id": event["event_id"], "reason": c.revision_reason,
                               "revision_kind": c.revision_kind},
            }
            res.accepted_edges.append(edges[eid])
            res.revisions.append({
                "new": cid, "old": c.supersedes, "kind": c.revision_kind,
                "reason": c.revision_reason, "old_status": target_status or ST_ACTIVE,
            })

    # ── relasi ──────────────────────────────────────────────────────────────
    def _resolve(ref_or_id: str) -> str | None:
        if ref_or_id in res.claim_ids:
            return res.claim_ids[ref_or_id]
        if (ref_or_id in nodes and (nodes[ref_or_id].get("status") or ST_ACTIVE) == ST_ACTIVE
                and (nodes[ref_or_id].get("provenance") or {}).get("session") == session.id):
            return ref_or_id
        return None

    for j, r in enumerate(obs.relations, 1):
        src = _resolve(r.src)
        dst = _resolve(r.dst)
        why = []
        if src is None:
            why.append(f"src tak dikenal/non-aktif: {r.src}")
        if dst is None:
            why.append(f"dst tak dikenal/non-aktif: {r.dst}")
        if src == dst and src is not None:
            why.append("self-relation")
        if why:
            res.rejections.append(f"relasi {r.src}->{r.dst} ({r.kind}): " + "; ".join(why))
            continue
        eid = f"e-e{int(event.get('seq', 0)):04d}-{j:03d}"
        if eid in edges:
            continue
        edges[eid] = {
            "id": eid, "src": src, "dst": dst, "kind": r.kind,
            "provenance": {"event_id": event["event_id"], "reason": r.reason or "llm relation"},
        }
        res.accepted_edges.append(edges[eid])

    return res
