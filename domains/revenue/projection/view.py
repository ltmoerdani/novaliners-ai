"""Revenue View — derived view from the Universal State Graph (M3).

View = a READ-ONLY projection (INV-1/INV-6). It answers the three user-review DoD
questions: projection completeness, projection loss, and the source of each field
(provenance node id) for diagnosis regression tests."""
from __future__ import annotations

from domains.revenue.projection.mapper import map_claim

_ROLE_PRECEDENCE = ("current_revenue", "target", "client_rate")


def build_revenue_view(graph: dict) -> dict:
    """graph {nodes, edges} → view {fields, signals, desires, loss, sources}.

    - fields are filled from roles with precedence: tense now > past; the newest value
      (higher turn) wins on ties.
    - loss = graph nodes that were NOT mapped (material for the projection-loss report).
    """
    nodes = list((graph.get("nodes") or {}).values())
    fields: dict[str, dict] = {}
    signals: list[dict] = []
    desires: list[dict] = []
    loss: list[dict] = []
    withheld: list[dict] = []

    for node in nodes:
        if (node.get("status") or "active") != "active":
            continue   # R4-C: a replaced/negated claim is not the current state (history lives in the graph)
        mapping = map_claim(node)
        if mapping is not None and mapping["kind"] == "withheld":
            withheld.append(mapping)
            loss.append({"node_id": node.get("id"), "withheld": mapping["reason"],
                         "subject": (node.get("triple") or {}).get("subject", {}).get("label"),
                         "predicate": (node.get("triple") or {}).get("predicate", {}).get("label")})
            continue
        if mapping is None:
            loss.append({"node_id": node.get("id"),
                         "subject": (node.get("triple") or {}).get("subject", {}).get("label"),
                         "predicate": (node.get("triple") or {}).get("predicate", {}).get("label")})
            continue
        if mapping["kind"] == "role":
            role = mapping["role"]
            cand = {"value": mapping.get("value"), "tense": mapping.get("tense"),
                    "node_id": mapping.get("node_id"), "precision": mapping.get("precision", "exact"),
                    "epistemic": mapping.get("epistemic", "reported")}
            prev = fields.get(role)
            if prev is None or _better(cand, prev):
                fields[role] = cand
        elif mapping["kind"] == "signal":
            signals.append(mapping)
        elif mapping["kind"] == "desire":
            desires.append(mapping)

    # R4-C: roles that the canonical state ALREADY states but that produce no active point (replaced claims,
    # ranges/bounds, personal income) are WITHHELD: the old regex fallback must not recover them.
    for m in withheld:
        fields.setdefault(m["role"], {"value": None, "suppressed": m["reason"], "node_id": m["node_id"]})
    for node in nodes:
        if (node.get("status") or "active") == "active":
            continue
        m = map_claim(dict(node, status="active"))
        if m and m["kind"] == "role" and m["role"] not in fields:
            fields[m["role"]] = {"value": None, "suppressed": "claim_not_current", "node_id": node.get("id")}

    return {
        "fields": fields,          # role → {value, tense, node_id}
        "signals": signals,        # founder_dependency / operational_load_increase
        "desires": desires,        # motivasi mentah
        "loss": loss,              # node tak terpetakan (projection loss)
        "node_count": len(nodes),
    }


def _better(cand: dict, prev: dict) -> bool:
    """now > past/future; a newer turn wins ties."""
    if cand.get("tense") == "now" and prev.get("tense") != "now":
        return True
    if cand.get("tense") != "now" and prev.get("tense") == "now":
        return False
    c_id, p_id = str(cand.get("node_id") or ""), str(prev.get("node_id") or "")
    return c_id > p_id  # cl-t<turn>-<n> lexicographic: a newer turn is larger


def apply_view(state, view: dict) -> None:
    """Apply the Revenue View to RevenueState (M3). Mapped fields override the
    regex; the provenance node id is recorded. Signals/desires/loss ride along in the artifact
    through state.notes so diagnosis has material without a new interpreter."""
    role_to_field = {
        "current_revenue": "current_monthly",
        "target": "target_monthly",
        "client_rate": "avg_deal_size",
    }
    for role, field in role_to_field.items():
        entry = view.get("fields", {}).get(role)
        if entry and entry.get("suppressed"):
            setattr(state, field, None)
            state.sources.pop(field, None)
            if field == "target_monthly":
                state.target_origin = None
            state.notes.append(f"{field} ditahan: {entry['suppressed']} (regex lama tidak dipulihkan)")
            continue
        if entry and entry.get("value") is not None:
            setattr(state, field, round(float(entry["value"]), 1))
            state.sources[field] = {
                "evidence_id": entry.get("node_id"),
                "derivation": f"graph view role={role} tense={entry.get('tense')}",
                "confidence": "measured",
                # R4-C: an estimate/hedge is not promoted to an exact number — the kind is still recorded
                "precision": entry.get("precision", "exact"),
                "epistemic": entry.get("epistemic", "reported"),
            }
    signals = view.get("signals") or []
    desires = view.get("desires") or []
    loss = view.get("loss") or []
    if signals:
        kinds = sorted({sg.get("signal") for sg in signals})
        state.notes.append(
            f"Graph view signals: {', '.join(kinds)} "
            f"({len(signals)} node; sinyal semantik, bukan diagnosis)"
        )
    if desires:
        state.notes.append(f"Graph view desires: {len(desires)} node motivasi tercatat")
    if loss:
        state.notes.append(
            f"Graph view projection loss: {len(loss)}/{view.get('node_count')} node "
            "belum terpetakan role/sinyal revenue"
        )
