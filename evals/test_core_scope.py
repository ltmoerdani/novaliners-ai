"""Class-S1 guard: `core/` generic stays free of domain identity (Phase J, internal-docs §10).

Background: the S1 sweep (P5a) stopped instances that NAMED themselves
(`startswith("L8")`), while sibling instances (`startswith("DS4")`,
MATERIAL_GAP_KEYWORDS, channel vocabulary) kept living in the same files — and
all gates stayed green, because existing guards test BEHAVIOR (catalog/lexicon
read from the pack), not the ABSENCE of vocabulary in `core/`. This guard closes
the CLASS, with detection sources DERIVED from the pack declarations (not a manual
list that can go stale):

  K1  constraint-id literal — prefix drawn from ontology/constraints.json.
      Applies to ALL of core/ (class S1 must not exist anywhere).
  K2  lexicon token ALREADY declared in the pack (domain_pack.json,
      mechanisms.json, knowledge/*.json, rule_activation.json) but hardcoded in modules
categorized as `generic` in ontology/core_scope.json.
  TOTALITY  every .py file in core/ must be listed in core_scope.json —
      a new file without a category = failure (F1 pattern: completeness at load).

The negative test is inline (the guard must actually be able to reject, not be vacuous).
Deterministic, no LLM. Run: .venv/bin/python evals/test_core_scope.py
"""
from __future__ import annotations

import ast
import json
import pathlib
import sys

sys.path.insert(0, ".")

ROOT = pathlib.Path(".")
SCOPE_PATH = ROOT / "ontology/core_scope.json"
FAILS: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"{'✅' if ok else '❌'} {label}" + (f" | {detail}" if detail else ""))
    if not ok:
        FAILS.append(label)


# ---------------------------------------------------------------- detection source

def declared_constraint_prefixes() -> set[str]:
    data = json.loads((ROOT / "ontology/constraints.json").read_text(encoding="utf-8"))
    return {cid.split(".")[0] for cid in data["constraints"]}


def declared_lexicon_tokens() -> set[str]:
    tokens: set[str] = set()

    def add(value) -> None:
        if isinstance(value, str):
            v = value.strip().lower()
            if 2 <= len(v) <= 40 and " " not in v:
                tokens.add(v)

    pack = json.loads((ROOT / "ontology/domain_pack.json").read_text(encoding="utf-8"))
    for group in pack.get("evidence_markers", {}).values():
        if isinstance(group, list):
            for t in group:
                add(t)
    for t in pack.get("material_gap_keywords", []):
        add(t)
    for t in pack.get("unmapped_distribution_note", {}).get("signals", []):
        add(t)

    mech = json.loads((ROOT / "ontology/mechanisms.json").read_text(encoding="utf-8"))
    for m in mech.get("mechanisms", []):
        add(m.get("id"))
        add(m.get("name"))
        for s in m.get("signals", []):
            add(s)

    for path in sorted((ROOT / "ontology/knowledge").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for cat in ("probes", "evidence_rules", "anti_patterns", "interventions"):
            for item in data.get(cat, []):
                for key in ("keyword", "keywords", "signal", "signals",
                            "pattern", "patterns", "terms", "phrases"):
                    v = item.get(key)
                    if isinstance(v, list):
                        for t in v:
                            add(t)
                    else:
                        add(v)
    return tokens


# ---------------------------------------------------------------- AST scanning

def _docstring_ids(tree: ast.AST) -> set[int]:
    """Constant node ids belonging to docstrings (module/func/class) — excluded."""
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", None)
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                ids.add(id(body[0].value))
    return ids


def string_literals(path: pathlib.Path):
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError as e:
        raise RuntimeError(f"{path}: gagal parse — {e}") from e
    docstrings = _docstring_ids(tree)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
        ):
            yield node.lineno, node.value


def _scan(files: list[str], prefixes: set[str], tokens: set[str]):
    """Return (k1_hits, k2_hits) — pairs of (file, line, literal)."""
    k1: list[str] = []
    k2: list[str] = []
    for rel in files:
        path = ROOT / rel
        for lineno, lit in string_literals(path):
            s = lit.strip()
            head = s.split(".")[0]
            dotted = "." in s and s.split(".")[-1].isdigit()
            if head in prefixes and (dotted or s in prefixes):
                k1.append(f"{rel}:{lineno}: {s!r}")
            if len(s) > 2 and s in tokens:
                k2.append(f"{rel}:{lineno}: {s!r}")
    return k1, k2


# ---------------------------------------------------------------- main

def main() -> int:
    scope = json.loads(SCOPE_PATH.read_text(encoding="utf-8"))
    generic: list[str] = scope["generic"]
    domain_bound: list[str] = scope["domain_bound"]

    # 0. TOTALITY — every core/ file listed under exactly one category.
    actual = {str(p) for p in (ROOT / "core").rglob("*.py")}
    listed = set(generic) | set(domain_bound)
    both = sorted(set(generic) & set(domain_bound))
    check(
        "core_scope.json TOTALITY (setiap file core/ terkategori)",
        not both and actual == listed,
        f"tak terkategori={sorted(actual - listed)} dobel={both} hantu={sorted(listed - actual)}",
    )

    prefixes = declared_constraint_prefixes()
    tokens = declared_lexicon_tokens()

    # 1. K1 — constraint-id literals FORBIDDEN across ALL of core/ (class S1).
    all_files = sorted(actual)
    k1_all, _ = _scan(all_files, prefixes, set())  # empty tokens: focus K1
    check(
        "K1: nol literal constraint-id di seluruh core/ (kelas S1)",
        not k1_all,
        "; ".join(k1_all[:6]) or "bersih",
    )

    # 2. K2 — pack lexicon tokens FORBIDDEN in `generic`-category modules.
    #    Case-sensitive EXACT match against declarations (taxonomy enum 'CONVERSION' ≠
    #    signal 'conversion'); explicit allowlist in core_scope.json (documented,
    #    shrinks as F1 closes — not a silent heuristic).
    allow = scope.get("k2_allowlist", {})
    _, k2_generic = _scan(generic, set(), tokens)
    k2_generic = [h for h in k2_generic if h.split(": ")[0].rsplit(":", 1)[0] not in allow
                  or h.split(": ")[1].strip("'") not in allow[h.split(": ")[0].rsplit(":", 1)[0]]]
    check(
        "K2: nol token lexicon pack yang di-hardcode di modul generic",
        not k2_generic,
        "; ".join(k2_generic[:6]) or f"bersih ({len(tokens)} token dipantau)",
    )

    # 3. Negative test — the guard really rejects (not vacuous): a synthetic snippet
    #    containing a K1 violation class (bare prefix) MUST be caught.
    probe_dir = ROOT / "evals/_core_scope_probe"
    probe_dir.mkdir(exist_ok=True)
    (probe_dir / "k1_probe.py").write_text(
        'NOTE = "penjaga: instance kelas S1"\nLEAK = "DS4"\n', encoding="utf-8"
    )
    try:
        k1_probe, _ = _scan([str(probe_dir / "k1_probe.py")], prefixes, set())
        check(
            "uji negatif K1: literal prefix telanjang tertangkap",
            any("'DS4'" in h for h in k1_probe),
            "; ".join(k1_probe) or "detector vacuous!",
        )
    finally:
        (probe_dir / "k1_probe.py").unlink(missing_ok=True)
        probe_dir.rmdir()

    print()
    if FAILS:
        print(f"❌ CORE SCOPE GAGAL — {len(FAILS)} pelanggaran")
        return 1
    print("✅ CORE SCOPE PASS — core/ generic bebas identitas domain")
    return 0


if __name__ == "__main__":
    sys.exit(main())
