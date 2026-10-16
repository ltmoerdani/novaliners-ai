"""Shim — core_rules has moved to core/prompts/ (INV-2: universal prompt
rules belong to core, not the revenue domain). M2 25 Sep 2026."""
from core.prompts.core_rules import (  # noqa: F401
    ANTI_FABRICATION,
    JSON_CONTRACT,
    LANGUAGE_RULES,
    SYSTEM_IDENTITY,
    TONE_RULES,
)
