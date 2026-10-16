"""Gate A (A3) — SUPPORT_SECOND_PASS conditional + honest provenance + planner determinism.

Contract under test (owner decision 15 Oct):
  1. Registered PROSE requirement -> SUPPORT_SECOND_PASS (mapper->verifier PATH CLAIM,
     not a recall or outcome guarantee); formal -> FORMAL_RULE; formal-unit -> UNIT; foreign -> NONE.
  2. Planner _channel (anti blanket-promotion): FORMAL_RULE -> ASK by label; SECOND_PASS -> ACT
     by label ONLY (the planner ask universe is preserved; ASK only via the old check-anchored
     contexts + resolvable-signal path, see P2e); NONE/UNIT -> ACT. No new question catalog /
     priority.
  3. STATIC property: adjudication_support does not depend on LLM availability (inspection/replay
     without a provider yields identical planner input).
  4. Support != verified: SECOND_PASS without a ledger entry stays UNKNOWN (the mapper recall
     bound is not redeemed into a status).
  5. Verification label = deterministic ADJUDICATOR identity (not the evidence verification
     method; the ledger schema is NOT extended).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # mvp/

from core.navigation.planner import ACT, ASK, _channel  # noqa: E402
from core.navigation.requirement_state import (  # noqa: E402
    SUPPORT_FORMAL,
    SUPPORT_NONE,
    SUPPORT_SECOND_PASS,
    SUPPORT_UNIT,
    SUPPORT_VALUES,
    RequirementState,
    unknown_state,
)
from engine.requirements import load_registry  # noqa: E402
from ontology.mapper.contract import UNIT_DOMAINS  # noqa: E402
from ontology.mapper.live_adjudication import adjudication_support, support_of  # noqa: E402
from store.requirement_state import VERIFICATION_METHOD  # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(ok), str(detail)[:160]))
    print(("  ✅ " if ok else "  ❌ ") + name + (f" :: {detail}" if detail and not ok else ""))


def main() -> int:
    print("P1 · pemetaan support")
    env_rules = set(adjudication_support.__globals__["formal_envelope"]().get("rules") or {})
    registry_ids = {e["requirement_id"] for e in load_registry().values()}
    prose_rid = next(rid for rid in sorted(registry_ids) if rid not in env_rules)
    formal_rid = next(rid for rid in sorted(env_rules) if rid not in UNIT_DOMAINS)
    check("P1a rid prose registry -> SECOND_PASS",
          adjudication_support(prose_rid) == SUPPORT_SECOND_PASS,
          (prose_rid, adjudication_support(prose_rid)))
    check("P1b rid formal -> FORMAL_RULE", adjudication_support(formal_rid) == SUPPORT_FORMAL, formal_rid)
    formal_unit = sorted(env_rules & set(UNIT_DOMAINS))
    if formal_unit:
        check("P1c formal-unit -> UNIT_CONTEXT_REQUIRED",
              adjudication_support(formal_unit[0]) == SUPPORT_UNIT, formal_unit)
    check("P1d rid asing -> NO_FORMAL_RULE",
          adjudication_support("x.tidak.ada") == SUPPORT_NONE)
    check("P1e closure support_of konsisten",
          support_of()(prose_rid) == SUPPORT_SECOND_PASS)

    print("P2 · planner _channel: label != askability (anti blanket-promotion)")
    inp = {"signals": {}, "paths": []}
    check("P2a FORMAL_RULE -> ASK", _channel({"support": "FORMAL_RULE", "contexts": []}, inp) == ASK)
    check("P2b SECOND_PASS TIDAK askable oleh label saja (universe tanya planner dipertahankan)",
          _channel({"support": "SECOND_PASS", "contexts": []}, inp) == ACT)
    check("P2c NO_FORMAL_RULE -> ACT", _channel({"support": "NO_FORMAL_RULE", "contexts": []}, inp) == ACT)
    check("P2d UNIT_CONTEXT_REQUIRED -> ACT",
          _channel({"support": "UNIT_CONTEXT_REQUIRED", "contexts": []}, inp) == ACT)
    check("P2e jalur lama tetap hidup: check-anchored + sinyal resolvable -> ASK",
          _channel({"support": "SECOND_PASS",
                    "contexts": [{"via": "check", "id": "p1", "ref": "c1"}]},
                   {"signals": {"sig1": ASK},
                    "paths": [{"path_id": "p1", "checks": [{"check_id": "c1", "signal": "sig1"}]}]}) == ASK)

    print("P3 · determinisme / inspeksi tanpa LLM")
    check("P3a support statis: dua panggilan identik",
          adjudication_support(prose_rid) == adjudication_support(prose_rid))
    check("P3b SECOND_PASS masuk SUPPORT_VALUES (roundtrip valid)",
          SUPPORT_SECOND_PASS in SUPPORT_VALUES)

    print("P4 · support != verified (batas recall mapper tidak ditebus jadi status)")
    st = unknown_state(prose_rid, SUPPORT_SECOND_PASS)
    check("P4a tanpa entry ledger: satisfaction UNKNOWN walau jalur tersedia",
          st.satisfaction == "UNKNOWN" and st.support == SUPPORT_SECOND_PASS,
          (st.satisfaction, st.support))

    print("P5 · provenance jujur")
    check("P5a label verifikasi = identitas adjudicator deterministik",
          VERIFICATION_METHOD == "deterministic_adjudicator", VERIFICATION_METHOD)
    try:
        RequirementState("x.bogus", "PRESENT", True, (), {}, 1, support="BOGUS")
        check("P5b support di luar enum ditolak", False, "tidak raise")
    except ValueError:
        check("P5b support di luar enum ditolak", True)

    failed = [r for r in RESULTS if not r[1]]
    print()
    for name, ok, detail in RESULTS:
        if not ok:
            print(f"FAIL :: {name} :: {detail}")
    print(f"\n{'✅ PASS' if not failed else '❌ FAIL'} · {len(RESULTS) - len(failed)}/{len(RESULTS)}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
