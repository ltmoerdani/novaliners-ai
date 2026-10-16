"""TEST-LOCK Session Runtime Bridge (T2 — owner verdict 27 Sep: f15309c
GREEN, the bridge may start).

INVARIANTS locked (owner 27 Sep):
 1. Session(userA) → bridge → compose → ALL status lookups = userA;
    Session(userB) with IDENTICAL evidence → status lookup = userB
    (the bridge does NOT take identity from evidence/goal/metadata —
    user identity is explicit from the session boundary).
 2. user_id is validated ONCE at the bridge entrance BEFORE any store
    is touched — traversal/empty rejected hard (ValueError), no wild
    directory is created.
 3. Route reuse does NOT cross users: same key, different user → ROUTE_CREATED
    with a different route_id (not ROUTE_REUSED).
 4. Bridge = orchestration only: it does not diagnose, does not judge status
    itself (values come purely from the per-user ledger).

Run: cd mvp && python ontology/route/test_session_bridge.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))  # mvp/

import tempfile as _tempfile  # noqa: E402

# non-destruktif: ledger + lineage ke tmp (pola test_adjudication_path)
import store.adjudication_ledger as ledger  # noqa: E402
from core.schema.evidence import EvidenceItem  # noqa: E402
from ontology.route.lifecycle import derived_route_status  # noqa: E402
from ontology.route.session_bridge import (  # noqa: E402
    run_session_route,
    user_status_reader,
)
from store.memory import Session  # Session ASLI — bug gap lolos via tiruan
from store.route_lineages import find_open_by_key as rl_find_open  # noqa: E402
from store.user_scope import validate_user_id  # noqa: E402

ledger._LEDGER_ROOT = Path(_tempfile.mkdtemp(prefix="bridge_adj_"))
_tmp = Path(_tempfile.mkdtemp(prefix="bridge_lin_"))

GOAL = "conversion.landing_page"

TEMPLATE = {  # test_compose fixture pattern (minimal, valid for composition)
    "template_id": "t2-min", "strategy_id": "template_led",
    "goal_anchor": GOAL,
    "applies_when": {
        "applies": [{"text_contains_any": ["website"]}],
        "not_applicable": [{"text_contains_any": ["offline saja"]}]},
    "requires": ["conversion.copy_composition",
                 "conversion.landing_page",
                 "experiment.baseline_comparison"],
    "node_candidates": [
        {"candidate_key": "copy_main",
         "resolves": ["conversion.copy_composition"],
         "strength": "hard", "depends_on": [], "activity": "Tulis copy"},
        {"candidate_key": "landing", "resolves": ["conversion.landing_page"],
         "strength": "hard", "depends_on": ["copy_main"],
         "activity": "Bangun halaman"},
        {"candidate_key": "baseline",
         "resolves": ["experiment.baseline_comparison"],
         "strength": "hard", "depends_on": ["landing"],
         "activity": "Jalankan uji"},
    ],
    "provenance": [{"source_id": "vp", "chapters": ["ch05"],
                    "knowledge_type": "source_claim",
                    "confidence": "normative_only"}],
}
RULE_PARTIAL = {
    "mode": "PARTIAL",
    "sufficient": {"any_of": [{"text_contains_any": ["sudah ada copy"]}]},
    "partial": {"any_of": [{"text_contains_any": ["__never__"]}]},
    "no_decisive": {"any_of": [{"text_contains_any": ["__never__"]}]},
    "contradicting": {"any_of": [{"text_contains_any": ["__never__"]}]},
}


def _session(user_id: str, evidence: list[EvidenceItem]) -> Session:
    """REAL store.memory Session (review note 4a1a4e8: a test using a
    fake = gap bugs slip through). Direct construction — without SessionStore
    so it does not write production session files."""
    return Session(id="s-t2", goal_text="naikkan penjualan online",
                   language="id", user_id=user_id, evidence=evidence)


def _ev(text: str, eid: str = "e1") -> EvidenceItem:
    return EvidenceItem(id=eid, signal=text, source_quote=text,
                        level="self_reported", topic="REVENUE_STATE")


def _mark_present(user_id: str, rid: str) -> None:
    """Write PRESENT for (user, requirement) through the public ledger door —
    proof that the bridge reader really reads that user's channel."""
    row = ledger.adjudicate_and_persist(
        user_id, rid, RULE_PARTIAL,
        [_ev("sudah ada copy", f"ev-{user_id}")],
        [{"requirement_id": rid, "evidence_refs": [f"ev-{user_id}"],
          "verification_method": "deterministic_predicate",
          "verified": True, "verified_at": 1}],
        evaluation_time=100,
    )
    assert "entry_id" in row, f"adjudication tak masuk ledger: {row}"


def _satisfaction_by_resolve(result: dict) -> dict[str, str]:
    out = {}
    for n in result["lineage"]["revisions"][0]["nodes"]:
        for r in n["resolves"]:
            out[r] = n["satisfaction"]["status"]
    return out


RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, fn) -> None:
    try:
        fn()
        RESULTS.append((name, True, ""))
    except Exception as exc:  # noqa: BLE001
        RESULTS.append((name, False, f"{type(exc).__name__}: {exc}"))


def t_identitas_eksplisit_isolasi_ab() -> None:
    """INVARIANT 1+4: A and B, IDENTICAL evidence — status lookup results
    follow session.user_id, NOT the evidence."""
    _mark_present("userA", "conversion.copy_composition")
    ev = [_ev("jual online via website kami")]
    r_a = run_session_route(_session("userA", ev), TEMPLATE,
                            base_dir=_tmp)
    r_b = run_session_route(_session("userB", ev), TEMPLATE,
                            base_dir=_tmp)
    sat_a = _satisfaction_by_resolve(r_a)
    sat_b = _satisfaction_by_resolve(r_b)
    assert sat_a["conversion.copy_composition"] == "PRESENT", sat_a
    assert sat_b["conversion.copy_composition"] == "UNKNOWN", \
        "status A bocor ke B — bridge ambil identitas dr luar session"
    assert sat_b["conversion.landing_page"] == sat_a["conversion.landing_page"]


def t_reuse_tidak_lintas_user() -> None:
    """INVARIANT 3: same key, different user → different route_id (not reuse)."""
    ev = [_ev("jual online via website kami")]
    r1 = run_session_route(_session("userR1", ev), TEMPLATE,
                           base_dir=_tmp)
    r2 = run_session_route(_session("userR1", ev), TEMPLATE,
                           base_dir=_tmp)
    assert r1["outcome"] == "ROUTE_CREATED" and r2["outcome"] == "ROUTE_REUSED"
    assert r2["lineage"]["route_id"] == r1["lineage"]["route_id"]
    r3 = run_session_route(_session("userR2", ev), TEMPLATE,
                           base_dir=_tmp)
    assert r3["outcome"] == "ROUTE_CREATED", \
        "userB mereuse route userA — bocoran lintas-user di reconciliation"
    assert r3["lineage"]["route_id"] != r1["lineage"]["route_id"]


def t_user_id_divalidasi_di_pintu_masuk() -> None:
    """INVARIANT 2: traversal/empty rejected BEFORE evidence is read &
    before the store is touched — no wild directory outside the root."""
    before = {p.name for p in ledger._LEDGER_ROOT.rglob("*")}
    for bad in ("../escape", "a/b", "", "u ser"):
        try:
            run_session_route(_session(bad, [_ev("website")]), TEMPLATE,
                              base_dir=_tmp)
        except ValueError:
            continue
        raise AssertionError(f"bridge menerima user_id tak sah: {bad!r}")
    after = {p.name for p in ledger._LEDGER_ROOT.rglob("*")}
    assert before == after, "attempt traversal meninggalkan artefak storage"
    try:
        user_status_reader("../x")
        raise AssertionError("reader global-set menerima traversal")
    except ValueError:
        pass
    # valid path still works
    assert user_status_reader("u-ok") is not None
    assert validate_user_id("u-ok") == "u-ok"


def t_gap_bukan_bukti_applicability() -> None:
    """BLOCKER review 4a1a4e8 (bug proven with a real Session): evidence
    GAP = information not yet available, NOT a fact. Gap-only ('belum punya
    website') MUST NOT produce APPLIES — it must be UNDETERMINED —
    and MUST NOT be cited. Fix in the composer (filter is_gap before
    evaluation), NOT in the bridge (invariant #1: no semantic decisions)."""
    gap = EvidenceItem(id="g1", signal="belum punya website",
                       source_quote="belum punya website",
                       level="self_reported", topic="REVENUE_STATE",
                       is_gap=True)
    r = run_session_route(_session("userG", [gap]), TEMPLATE,
                          base_dir=_tmp)
    assert r["lineage"]["applicability"]["status"] == "UNDETERMINED", r["lineage"]["applicability"]
    assert r["lineage"]["applicability"]["evidence"] == [], \
        "gap ikut disitasi sbg bukti applicability"
    # mixed: gap does NOT add evidence — non-gap still decides
    r2 = run_session_route(
        _session("userG", [gap, _ev("kami jual online via website")]),
        TEMPLATE, base_dir=_tmp)
    app2 = r2["lineage"]["applicability"]
    assert app2["status"] == "APPLIES"
    assert "g1" not in app2["evidence"], "gap masuk sitasi APPLIES"
    # frontier UNDETERMINED = RESOLVE_APPLICABILITY (semangat §3.5)
    fr = r["frontier"]
    assert fr and fr[0]["kind"] == "RESOLVE_APPLICABILITY", fr


def t_bridge_menjalankan_lifecycle() -> None:
    """CORRECTIVE review 7de3e73: DEBT-M4 must be active on the RUNTIME path.
    Previously the bridge composed directly — goal PRESENT produced
    NO_ROUTE_GOAL_PRESENT but the lineage STAYED OPEN (exactly DEBT-M4
    T1.17). Now the bridge reconciles first: goal PRESENT → LINEAGE_COMPLETED
    and the lineage is NO longer OPEN."""
    ev = [_ev("jual online via website kami")]
    r1 = run_session_route(_session("userD", ev), TEMPLATE,
                           base_dir=_tmp)
    assert r1["outcome"] == "ROUTE_CREATED"
    _mark_present("userD", GOAL)
    r2 = run_session_route(_session("userD", ev), TEMPLATE,
                           base_dir=_tmp)
    assert r2["outcome"] == "LINEAGE_COMPLETED", r2
    assert r2["lineage"]["lineage_status"] == "CLOSED" \
        and r2["lineage"]["close_reason"] == "goal_achieved"
    assert derived_route_status(r2["lineage"]) == "COMPLETED"
    key = {"goal_anchor": GOAL, "strategy_id": TEMPLATE["strategy_id"],
           "scope_anchor": ["state:user"]}
    assert rl_find_open("userD", key) is None, "lineage masih OPEN setelah COMPLETED"


def t_a1_goal_anchor_dari_template_scope_per_user() -> None:
    """DECISION A1 (owner 27 Sep): goal_anchor = template declaration
    (the bridge only READS the field — orchestration, not a semantic
    decision); scope default ["state:user"] — one scope per user
    (granularity debt recorded; per-session scope = INV-R13 broken)."""
    from ontology.route.session_bridge import SCOPE_PER_USER
    assert SCOPE_PER_USER == ["state:user"]
    # without goal_anchor/scope_anchor params — both come from the template/constant
    r = run_session_route(_session("userE", [_ev("jual online via website")]),
                          TEMPLATE, base_dir=_tmp)
    assert r["lineage"]["reconciliation_key"]["goal_anchor"] == GOAL
    assert r["lineage"]["reconciliation_key"]["scope_anchor"] == ["state:user"]
    # CORRECTIVE review 5611993: the override was REMOVED from the signature —
    # the caller CANNOT override the route goal/scope (owner test:
    # the copy_composition override gave birth to a second lineage whose goal is
    # never declared by the template). TypeError = a permanently
    # closed door that cannot be opened silently.
    for kw in ({"goal_anchor": GOAL}, {"scope_anchor": ["state:claim-x"]},
               {"motion": "PAID_ACQUISITION"}):  # D5: motion pun tertutup
        try:
            run_session_route(_session("userE", [_ev("website")]), TEMPLATE,
                              base_dir=_tmp, **kw)
        except TypeError:
            continue
        raise AssertionError(f"override {list(kw)} masih diterima bridge")
    # template without goal_anchor → ValueError (not guessing)
    bad = {k: v for k, v in TEMPLATE.items() if k != "goal_anchor"}
    try:
        run_session_route(_session("userF", [_ev("website")]), bad,
                          base_dir=_tmp)
    except ValueError as e:
        assert "goal_anchor" in str(e)
    else:
        raise AssertionError("template tanpa goal_anchor lolos bridge")


TESTS = [t_identitas_eksplisit_isolasi_ab, t_reuse_tidak_lintas_user,
         t_user_id_divalidasi_di_pintu_masuk,
         t_gap_bukan_bukti_applicability, t_bridge_menjalankan_lifecycle,
         t_a1_goal_anchor_dari_template_scope_per_user]


def t_d5_motion_dari_strategy_registry() -> None:
    """D5: motion lineage = strategies.json[strategy_id].motion; strategi
    not registered -> ValueError (not a silent default)."""
    from ontology.route.strategies import load_strategies
    r = run_session_route(_session("userS", [_ev("jual online via website")]),
                          TEMPLATE, base_dir=_tmp)
    want = load_strategies()[TEMPLATE["strategy_id"]]["motion"]
    assert r["lineage"]["motion"] == want, (r["lineage"]["motion"], want)
    bad = dict(TEMPLATE, strategy_id="strategi_hantu")
    try:
        run_session_route(_session("userS2", [_ev("website")]), bad,
                          base_dir=_tmp)
    except ValueError as exc:
        assert "tidak terdaftar" in str(exc), exc
        return
    raise AssertionError("strategi tak terdaftar lolos")


TESTS.append(t_d5_motion_dari_strategy_registry)


def main() -> int:
    for fn in TESTS:
        check(fn.__name__, fn)
    ok = True
    for name, passed, err in RESULTS:
        print(f"  {'PASS' if passed else 'FAIL'}  {name}" + (f"  — {err}" if err else ""))
        ok = ok and passed
    print(f"\n{sum(p for _, p, _ in RESULTS)}/{len(RESULTS)} bridge tests passed")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
