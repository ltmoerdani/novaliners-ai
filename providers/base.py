"""Compatibility shim — the LLM port has moved to `core.llm` (Phase B / P0.2b).

The port MUST stay inside core: the generic engine (`core/stages/*`) must not depend on the
infra adapter layer (internal-docs §9). The implementation moved first, the
adapters (`gemini.py`, `vertex.py`, `mock.py`) and the agents still use this
path so the migration is gradual — the parallel change pattern. Once all consumers move to
`core.llm`, this shim is deleted.

Do NOT add new logic here.
"""
from core.llm import (  # noqa: F401
    MAX_RETRIES,
    LLMProvider,
    schema_hint,
    strip_code_fences,
)
