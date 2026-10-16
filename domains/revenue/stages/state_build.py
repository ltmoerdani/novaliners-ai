"""Compatibility — contents split into dedup/state/validate (internal-docs §7 step A3).
Do NOT add new logic here."""
from domains.revenue.stages.dedup import deduplicate_evidence  # noqa: F401
from domains.revenue.stages.state import build_revenue_state  # noqa: F401
from domains.revenue.stages.validate import validate_state  # noqa: F401
