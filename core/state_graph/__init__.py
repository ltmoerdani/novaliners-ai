"""Universal State Graph — core package (M1, int 11 Rev 11.1 §10.3–10.6).

INV-2 (int 10): core knows no domain whatsoever. Every term here is
neutral; domain vocabulary (e.g. revenue) may only appear as raw extraction
`label` or mapper `normalized` output.

M1 scope (user-approved 25 Sep): models + verify gate + store + mapper
NumberClaim→node + session persistence. NOT YET: NextMove, VoI, applicability,
free-order, UI, graph DB.
"""
from core.state_graph.mapper import number_claims_to_delta
from core.state_graph.models import (
    Concept,
    Edge,
    EdgeKind,
    GraphDelta,
    UniversalClaim,
)
from core.state_graph.store import GraphStore
from core.state_graph.verify import verify_delta

__all__ = [
    "Concept",
    "Edge",
    "EdgeKind",
    "GraphDelta",
    "UniversalClaim",
    "GraphStore",
    "verify_delta",
    "number_claims_to_delta",
]
