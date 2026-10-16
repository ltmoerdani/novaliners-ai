"""Verify Gate — §10.3b (int 11 Rev 11.1): "Understanding may propose
structure; only verified state becomes state."

Purely deterministic. Checks: provenance (verbatim present in the transcript), schema,
basic temporal consistency, relation validity (correct edge class, may_indicate
only from the KB). A failing delta is rejected + noted — demand evidence, never guess.
"""
from __future__ import annotations

import re

from core.state_graph.models import (
    EVIDENCE_EDGES,
    EdgeKind,
    GraphDelta,
    UniversalClaim,
)


def _normalize_text(t: str) -> str:
    return re.sub(r"\s+", " ", (t or "").lower()).strip()


def _transcript_blob(transcript: list[tuple[str, str]] | None) -> str:
    if not transcript:
        return ""
    return _normalize_text(" ".join(text for role, text in transcript if role == "user"))


def _claim_provenance_ok(c: UniversalClaim, blob: str, notes: list[str]) -> bool:
    ok = True
    if not c.verbatim or not _normalize_text(c.verbatim):
        notes.append(f"{c.id}: verbatim kosong — node ditolak (INV-3)")
        return False
    if blob and _normalize_text(c.verbatim) not in blob:
        # substring-based grounding; verbatim trimmed/paraphrased by the LLM is rejected
        notes.append(f"{c.id}: verbatim tidak ditemukan di transcript — ditolak (INV-3)")
        ok = False
    if not c.provenance.get("turn"):
        notes.append(f"{c.id}: provenance.turn kosong — ditolak (INV-3)")
        ok = False
    return ok


def _claim_schema_ok(c: UniversalClaim, notes: list[str]) -> bool:
    if not c.triple.subject.label or not c.triple.predicate.label:
        notes.append(f"{c.id}: triple subject/predicate kosong — ditolak (schema)")
        return False
    # Rev 11.1 #1: normalized may exist, but must NOT replace the raw label
    if c.triple.predicate.normalized and not c.triple.predicate.label:
        notes.append(f"{c.id}: normalized tanpa label mentah — ditolak (extraction != interpretation)")
        return False
    return True


def _claim_temporal_ok(c: UniversalClaim, notes: list[str]) -> bool:
    # basic INV-4: a valid tense enum is already enforced by pydantic; check signal consistency
    if c.hedge and c.modality.value == "factual":
        notes.append(f"{c.id}: hedge=true tapi modality=factual — didemote ke hedged")
        c.modality = "hedged"  # type: ignore[assignment]
    return True


def verify_delta(
    delta: GraphDelta,
    transcript: list[tuple[str, str]] | None = None,
    existing_claim_ids: set[str] | None = None,
) -> tuple[GraphDelta, list[str]]:
    """Return (accepted_delta, notes). Notes carry the reason for every rejection/demotion."""
    notes: list[str] = list(delta.notes)
    blob = _transcript_blob(transcript)
    existing = existing_claim_ids or set()
    accepted_claims: list[UniversalClaim] = []
    accepted_ids: set[str] = set()

    for c in delta.claims:
        if _claim_schema_ok(c, notes) and _claim_provenance_ok(c, blob, notes):
            _claim_temporal_ok(c, notes)
            if c.id in existing:
                notes.append(f"{c.id}: duplikat id — dilewati (idempotent)")
                continue
            accepted_claims.append(c)
            accepted_ids.add(c.id)

    accepted_edges = []
    for e in delta.edges:
        # relation validity (Rev 11.1 #2)
        if e.kind == EdgeKind.may_indicate:
            notes.append(
                f"{e.id}: may_indicate hanya boleh dari KB-match — M1 belum punya jalur itu, edge ditolak"
            )
            continue
        if e.kind not in EVIDENCE_EDGES:
            notes.append(f"{e.id}: kelas edge tidak dikenal — ditolak")
            continue
        if e.src not in accepted_ids and e.src not in existing:
            notes.append(f"{e.id}: src {e.src} tidak lolos/eksisting — edge ditolak")
            continue
        dst_known = e.dst in accepted_ids or e.dst in existing
        if e.kind != EdgeKind.derived_from and not dst_known:
            notes.append(f"{e.id}: dst {e.dst} tidak lolos/eksisting — edge ditolak")
            continue
        accepted_edges.append(e)

    accepted = GraphDelta(claims=accepted_claims, edges=accepted_edges, notes=notes)
    return accepted, notes
