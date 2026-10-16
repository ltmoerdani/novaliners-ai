"""Authoring-language guard (W5): Indonesian docstrings/comments must not REGRESS.

Background (Oct 2026): the project is international — Python docstrings and # comments in
production code are being translated to English in waves (internal-docs §7,
D1/D10; migration ledger in repo notes). This guard is the RATCHET for that effort:

- MANIFEST below lists every production file already translated, with the number of
  residual Indonesian-word hits allowed (docstrings + # comments, ast/tokenize scan).
  Residuals are functional: quoted Indonesian examples inside English comments, and
  regex/word-list documentation that must stay verbatim.
- FAIL when a manifest file EXCEEDS its allowance (someone re-introduced Indonesian).
- FAIL when a manifest file disappears or cannot be parsed (silent deletion = regression).
- `--report` scans ALL production files (no fail) and prints the remaining map, so the
  next wave can pick targets. Not wired to the gate; the ratchet above is.

Deterministic, no LLM, no network. Run: .venv/bin/python evals/test_authoring_language.py
"""
from __future__ import annotations

import ast
import io
import re
import sys
import tokenize
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MVP = REPO / "mvp"

ID_WORDS = re.compile(
    r"\b(yang|dengan|untuk|tidak|adalah|dari|ini|dan|atau|jika|bila|hanya|sudah|belum|boleh|harus|bisa|"
    r"akan|juga|masih|semua|setiap|ketika|karena|sebagai|tanpa|dipakai|digunakan|mengembalikan|menghasilkan|"
    r"membaca|menulis|dihapus|ditambah|tetap|sah|wajib|keluaran|berisi|memuat|berlaku|pengembalian|tergantung|"
    r"dilakukan|tersebut|layar|keputusan|ketentuan|alasan)\b",
    re.IGNORECASE,
)

# {relative-to-mvp path: allowed residual hits}. Ratchet: only ever decreases.
MANIFEST: dict[str, int] = {
    "agents/__init__.py": 0,
    "agents/ask.py": 0,
    "agents/diagnosis.py": 0,
    "agents/explain.py": 0,
    "agents/interview.py": 0,
    "app/__init__.py": 0,
    "app/adaptive.py": 0,
    "app/auth.py": 0,
    "app/binding.py": 0,
    "app/checkpoints.py": 0,
    "app/experience_contract.py": 0,
    "app/experience_journey.py": 0,
    "app/finalization.py": 0,
    "app/main.py": 0,
    "app/moves.py": 0,
    "app/navigation.py": 0,
    "app/observations.py": 0,
    "app/turn.py": 0,
    "core/__init__.py": 0,
    "core/llm.py": 1,
    "core/navigation/__init__.py": 0,
    "core/navigation/activity_reference.py": 0,
    "core/navigation/applicability.py": 0,
    "core/navigation/candidate.py": 0,
    "core/navigation/claims.py": 0,
    "core/navigation/compat.py": 0,
    "core/navigation/contracts.py": 0,
    "core/navigation/evaluator.py": 0,
    "core/navigation/generator.py": 0,
    "core/navigation/knowledge.py": 0,
    "core/navigation/narrative.py": 0,
    "core/navigation/planner.py": 0,
    "core/navigation/planner_input.py": 0,
    "core/navigation/planner_text.py": 0,
    "core/navigation/predicate.py": 0,
    "core/navigation/presentation.py": 0,
    "core/navigation/readiness.py": 0,
    "core/navigation/requirement_state.py": 0,
    "core/pipeline.py": 0,
    "core/prompts/__init__.py": 0,
    "core/prompts/core_rules.py": 0,
    "core/reasoning/__init__.py": 0,
    "core/reasoning/contract.py": 0,
    "core/reasoning/guard.py": 1,
    "core/reasoning/hypotheses.py": 0,
    "core/reasoning/reasoner.py": 0,
    "core/reasoning/semantic_unknowns.py": 0,
    "core/reasoning/snapshot.py": 0,
    "core/reasoning/uncertainties.py": 0,
    "core/schema/__init__.py": 0,
    "core/schema/constraints.py": 0,
    "core/schema/domain.py": 1,
    "core/schema/evidence.py": 0,
    "core/schema/ontology.py": 2,
    "core/schema/provenance.py": 0,
    "core/schema/rule_activation.py": 0,
    "core/semantic/__init__.py": 0,
    "core/semantic/candidate.py": 0,
    "core/semantic/commit.py": 0,
    "core/semantic/contract.py": 0,
    "core/semantic/derive.py": 0,
    "core/semantic/observation.py": 0,
    "core/stages/__init__.py": 0,
    "core/stages/adjudicate.py": 0,
    "core/stages/confidence.py": 2,
    "core/stages/knowledge_rules.py": 0,
    "core/stages/mechanisms.py": 0,
    "core/stages/rule_predicates.py": 3,
    "core/stages/rule_support.py": 0,
    "core/stages/spectrum.py": 0,
    "core/state_graph/__init__.py": 0,
    "core/state_graph/drift.py": 0,
    "core/state_graph/mapper.py": 0,
    "core/state_graph/models.py": 0,
    "core/state_graph/store.py": 0,
    "core/state_graph/understanding.py": 0,
    "core/state_graph/verify.py": 0,
    "core/trace.py": 0,
    "domains/revenue/__init__.py": 0,
    "domains/revenue/guards/__init__.py": 0,
    "domains/revenue/guards/goal_consistency.py": 0,
    "domains/revenue/guards/nba_grounding.py": 0,
    "domains/revenue/guards/plain_language.py": 0,
    "domains/revenue/guards/population.py": 0,
    "domains/revenue/guards/readiness_grounding.py": 0,
    "domains/revenue/navigation/__init__.py": 0,
    "domains/revenue/navigation/live.py": 0,
    "domains/revenue/navigation/paths.py": 0,
    "domains/revenue/navigation/signals.py": 0,
    "domains/revenue/navigation/space.py": 0,
    "domains/revenue/projection/__init__.py": 0,
    "domains/revenue/projection/compat_claims.py": 0,
    "domains/revenue/projection/mapper.py": 0,
    "domains/revenue/projection/readiness.py": 0,
    "domains/revenue/projection/view.py": 0,
    "domains/revenue/prompts/__init__.py": 0,
    "domains/revenue/prompts/ask_system.py": 0,
    "domains/revenue/prompts/copilot_and_journey.py": 0,
    "domains/revenue/prompts/core_rules.py": 0,
    "domains/revenue/prompts/diagnosis_system.py": 0,
    "domains/revenue/prompts/diagnosis_user.py": 0,
    "domains/revenue/prompts/explain_system.py": 0,
    "domains/revenue/schema/__init__.py": 0,
    "domains/revenue/schema/artifact.py": 0,
    "domains/revenue/schema/ask.py": 0,
    "domains/revenue/schema/explain.py": 0,
    "domains/revenue/schema/goal.py": 0,
    "domains/revenue/schema/goal_evaluation.py": 0,
    "domains/revenue/schema/goal_projection.py": 0,
    "domains/revenue/schema/measurement_contract.py": 0,
    "domains/revenue/schema/state.py": 0,
    "domains/revenue/stages/__init__.py": 0,
    "domains/revenue/stages/causal.py": 1,
    "domains/revenue/stages/dedup.py": 0,
    "domains/revenue/stages/extract.py": 0,
    "domains/revenue/stages/journey.py": 0,
    "domains/revenue/stages/opportunities.py": 0,
    "domains/revenue/stages/reconcile.py": 0,
    "domains/revenue/stages/reroute.py": 0,
    "domains/revenue/stages/state.py": 16,
    "domains/revenue/stages/state_build.py": 0,
    "domains/revenue/stages/trajectory.py": 1,
    "domains/revenue/stages/validate.py": 0,
    "engine/__init__.py": 0,
    "engine/applicable_knowledge.py": 0,
    "engine/domain_pack.py": 0,
    "engine/knowledge.py": 0,
    "engine/requirements.py": 0,
    "llm/runtime.py": 0,
    "ontology/adjudication/test_adjudication_path.py": 0,
    "ontology/adjudication/validate_adjudication.py": 0,
    "ontology/knowledge/compile_rubrics.py": 0,
    "ontology/knowledge/validate_knowledge.py": 0,
    "ontology/mapper/__init__.py": 0,
    "ontology/mapper/a3b_adapter.py": 0,
    "ontology/mapper/challenge_matrix.py": 0,
    "ontology/mapper/contract.py": 0,
    "ontology/mapper/formal_compiler.py": 0,
    "ontology/mapper/live_adjudication.py": 0,
    "ontology/mapper/second_pass.py": 0,
    "ontology/mapper/test_calibration.py": 5,
    "ontology/mapper/test_calibration_fase4.py": 1,
    "ontology/mapper/test_calibration_fase5a.py": 2,
    "ontology/mapper/test_mapper.py": 0,
    "ontology/possibility/validate_possibility.py": 0,
    "ontology/registry/metrics.py": 0,
    "ontology/registry/test_registry_path.py": 0,
    "ontology/registry/validate_metrics.py": 0,
    "ontology/registry/validate_presentation.py": 0,
    "ontology/registry/validate_registry.py": 2,
    "ontology/route/compose.py": 0,
    "ontology/route/execution_view.py": 0,
    "ontology/route/lifecycle.py": 0,
    "ontology/route/next_move.py": 0,
    "ontology/route/path_routes.py": 0,
    "ontology/route/plan.py": 0,
    "ontology/route/projection.py": 0,
    "ontology/route/session_bridge.py": 0,
    "ontology/route/strategies.py": 0,
    "ontology/route/test_compose.py": 0,
    "ontology/route/test_inv_r6.py": 0,
    "ontology/route/test_lifecycle.py": 1,
    "ontology/route/test_next_move.py": 0,
    "ontology/route/test_session_bridge.py": 1,
    "ontology/route/test_templates.py": 0,
    "ontology/route/validate_route.py": 0,
    "providers/__init__.py": 0,
    "providers/base.py": 0,
    "providers/gemini.py": 0,
    "providers/mock.py": 2,
    "providers/vertex.py": 0,
    "store/__init__.py": 0,
    "store/adjudication_ledger.py": 0,
    "store/checkins.py": 0,
    "store/events.py": 0,
    "store/funnel.py": 0,
    "store/goals.py": 0,
    "store/memory.py": 0,
    "store/navigation_links.py": 0,
    "store/nba.py": 0,
    "store/path_states.py": 0,
    "store/requirement_state.py": 0,
    "store/route_execution.py": 0,
    "store/route_lineages.py": 0,
    "store/test_user_scope.py": 0,
    "store/user_scope.py": 0,
    "store/workspace.py": 0,
}

FAILS: list[str] = []


def _fail(msg: str) -> None:
    FAILS.append(msg)
    print(f"FAIL {msg}")


def _scan(text: str) -> tuple[int, list[str]]:
    """Count Indonesian-word hits in docstrings + # comments. Returns (count, sample lines)."""
    try:
        tree = ast.parse(text)
    except SyntaxError as e:
        return -1, [f"syntax error: {e}"]
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)):
                doc = node.body[0].value.value
                for ln in doc.splitlines():
                    if ID_WORDS.search(ln):
                        hits.append(ln.strip()[:110])
    for tok in tokenize.generate_tokens(io.StringIO(text).readline):
        if tok.type == tokenize.COMMENT and ID_WORDS.search(tok.string):
            hits.append(tok.string.strip()[:110])
    return len(hits), hits[:6]


def main() -> None:
    report_only = "--report" in sys.argv

    # 1) Ratchet over the manifest.
    for rel, allowed in MANIFEST.items():
        path = MVP / rel
        if not path.exists():
            _fail(f"{rel}: manifest file missing (deleted or renamed without updating the guard)")
            continue
        n, samples = _scan(path.read_text(encoding="utf-8", errors="ignore"))
        if n < 0:
            _fail(f"{rel}: file does not parse")
            continue
        if n > allowed:
            _fail(f"{rel}: {n} Indonesian docstring/comment hits > allowed {allowed}; samples: {samples}")

    # 2) Full-production report (informational; never fails the gate).
    if report_only:
        rows: list[tuple[int, str]] = []
        for f in MVP.rglob("*.py"):
            rel = f.relative_to(MVP).as_posix()
            if rel in MANIFEST or rel.startswith(("evals/", "e2e/")):
                continue
            if any(part in rel for part in ("__pycache__", ".venv", "egg-info")):
                continue
            n, _ = _scan(f.read_text(encoding="utf-8", errors="ignore"))
            if n > 0:
                rows.append((n, rel))
        rows.sort(reverse=True)
        print(f"--report: {sum(n for n, _ in rows)} residual hits in {len(rows)} production files "
              f"(outside the manifest):")
        for n, rel in rows[:40]:
            print(f"  {n:4d}  {rel}")

    if FAILS:
        print(f"\nAUTHORING-LANGUAGE GUARD FAILED — {len(FAILS)} regression(s). "
              f"Docstrings/comments must stay English once translated (ratchet).")
        sys.exit(1)
    print(f"authoring-language guard OK — {len(MANIFEST)} manifest files within allowance. "
          f"Use --report for the full remaining map.")


if __name__ == "__main__":
    main()
