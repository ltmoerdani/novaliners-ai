"""Test harness & eval (not part of the runtime; production code must never import it).

Phase A (internal-docs §9 P0.0): a regular package (previously PEP 420) so the
import-linter can enforce the contract "no production code imports the test harness".
"""
