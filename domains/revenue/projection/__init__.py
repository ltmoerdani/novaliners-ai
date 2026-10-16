"""Revenue Projection — adapter plugin (M3, int 11 §10.13–10.14).

User review principle (25 Sep): **projection may be semantic, projection MUST NOT
diagnose.** The mapper translates graph nodes → revenue roles and
operational signals; it NEVER produces constraint/mechanism names
(capacity bottleneck etc.) — that is the domain of hypothesis/applicability (M4)."""
from domains.revenue.projection.mapper import map_claim
from domains.revenue.projection.view import apply_view, build_revenue_view

__all__ = ["map_claim", "build_revenue_view", "apply_view"]
