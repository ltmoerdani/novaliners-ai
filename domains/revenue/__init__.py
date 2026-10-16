"""Revenue domain pack — code + declarations owned by the domain (F2', internal-docs §4).

Target structure:
    domains/revenue/
        guards/        ← domain guards (population integrity, etc.)
        schema/        ← RevenueState, CausalHypothesis (to follow)
        stages/        ← extract, opportunities, validate, causal, state (to follow)
        prompts/       ← diagnosis/interview prompts (F3, to follow)

Dependency rule: domains/* may import core/*; core/* MUST NOT import
domains/* (enforced by import-linter)."""
