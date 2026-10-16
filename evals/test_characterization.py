"""Characterization test (golden master) — safety net for the P5 refactor.

Purpose (internal-docs §9 P5 · research: Feathers, *Working Effectively with Legacy Code*):
record the ACTUAL behavior of the deterministic stages before the structure changes, so that any
unintended behavior change shows up immediately as a diff.

Why "characterization", not "unit test": this test does NOT claim the code is correct.
It only pins the observed behavior. If the code changes, the test fails and
someone must decide: the new behavior is right (approve) or it is a regression (fix).

Fully deterministic — no LLM, no network, no stored artifacts.
If this test needs to be approved, run:
    .venv/bin/python evals/test_characterization.py --approve
then INSPECT the golden diff — approving without reading the diff = losing the safety net.

KNOWN DEVIATIONS (pinned, not forgotten)
------------------------------------------
`test_known_deviations()` deliberately PINS known bugs so they are not "quietly fixed".
Its assertions WILL FAIL when their phase arrives — that is the point (change detector):
  - DEV-1  (*DECIDED & FIXED in Phase D contract*) a 2-letter lookup made 3-letter domains
           (DS4, DM5) always fall back to defaults, silently killing the reversibility /
           decision / experiment priority factors. Lookup is now PER-DOMAIN and lexicon
           completeness is enforced at load time (fail-fast). The `test_lexicon_*`
           assertions guard that fix — they fail if `[:2]` returns.
  - DEV-2  (*FIXED in Phase C*) the `mech:` tag used to contain ordered characters, not
           mechanism ids → mechanism evidence expansion never ran, making the D6 fix
           (iter-9) inert. The `test_f4_*` assertions now GUARD that fix: if `sorted(m)`
           over a string returns, the test fails.
  - DEV-3  (*fixed in Phase A*) tie ordering of constraints + ordering of `mech:` tags
           depended on Python `set` iteration (PYTHONHASHSEED).
  - F5     (*fixed in Phase A*) `evidence_strength` & `diagnostic_fit` were assigned from
           the first loop variable, already stale → ALL hypotheses inherited one
           constraint's values, and the values changed between processes. Found precisely
           because the first golden failed on itself. This golden is still CANONICALIZED
           (tie groups sorted by constraint_id) so only SEMANTIC order is pinned, not the
           physical list order.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import engine.domain_pack as dp  # noqa: E402
from core.schema.evidence import EvidenceItem  # noqa: E402
from core.schema.ontology import validate_disqualifiers  # noqa: E402
from core.stages.confidence import (  # noqa: E402
    IMPACT_CAP_NO_EFFECT_EVIDENCE,
    _is_event_evidence,
    build_constraint_map,
    disqualifier_check,
    gap_consequences,
    has_decision_priority,
    mechanism_boost,
    overall_confidence,
    reversibility_weight,
    score_hypotheses,
    split_confidences,
)
from core.stages.mechanisms import MECHANISMS, detect_mechanisms  # noqa: E402
from domains.revenue.stages.state import build_revenue_state  # noqa: E402
from engine.domain_pack import (  # noqa: E402
    domain_order,
    has_experiment_priority,
    is_systemic_risk,
    pack_id,
    pack_version,
    upstream_rank,
)
from engine.knowledge import active_rule_sources  # noqa: E402

GOLDEN = Path(__file__).resolve().parent / "golden" / "deterministic_stages.json"


@dataclass
class StubState:
    """Minimal (duck-typed) state — the parts read via `getattr` by the deterministic stages.

    Deliberately a stub, not RevenueState: this test pins the scoring ARITHMETIC, not
    the state schema contract (that is domain-bound and moves to the pack in F2/Phase F).
    """

    acquisition_hours_per_week: float | None = 10.0
    deals_needed: float | None = 3.0
    demand_sufficiency: str = "UNKNOWN"
    pricing_architecture: str = "GAP"
    response_latency_days: float | None = None
    capacity_utilization: float = 0.86
    avg_deal_size: float | None = 8.0


def _ev(eid: str, signal: str, level: str, topic: str, is_gap: bool = False) -> EvidenceItem:
    return EvidenceItem(id=eid, signal=signal, level=level, topic=topic,
                        source_quote=signal, is_gap=is_gap)


# One consistent story (a consultant with a thin pipeline + leaky follow-up), designed
# so that EVERY deviation and every domain-token branch in `confidence.py` fires:
#  - DM5.1 / DM5.6 → 3-letter domain (DEV-1: reversibility & decision_priority inert)
#  - DS4.2         → 3-letter domain + distribution marker (note the mapping gap)
#  - C6.1          → supported ONLY by mechanisms (DEV-2: evidence expansion inert)
#  - L8.3          → capacity state maxed out → SYSTEMIC_RISK
#  - DM5.5         → disqualifier "trust proven sufficient" (there is a new transaction)
#  - ev-gap        → material gap ("capacity") → confidence penalty + probe
SCENARIOS: dict[str, dict] = {
    "pipeline_tipis_followup_bocor": {
        "evidence": [
            _ev("ev-1", "proposal dikirim lalu saya tunggu, tidak di-follow", "transactional", "CONVERSION"),
            _ev("ev-2", "klien lama bayar retainer rutin bulan lalu", "transactional", "REVENUE_STATE"),
            _ev("ev-3", "outreach cuma 2 dm per minggu, jarang outreach", "behavioral", "MOTION"),
            _ev("ev-4", "6 dari 10 proposal jadi waktu saya rajin follow-up", "outcome", "DEMAND"),
            _ev("ev-5", "saya tidak posting, inquiry ikut berhenti", "self_reported", "MOTION"),
            _ev("ev-6", "belum ada paket dan belum tahu charge ke klien", "self_reported", "GOAL"),
            _ev("ev-7", "balasan ke prospek lambat, lead macet dan terbengkalai", "behavioral", "MOTION"),
            _ev("ev-gap", "tidak tahu kapasitas jam per minggu yang tersedia", "self_reported",
                "REVENUE_STATE", is_gap=True),
        ],
        "evidence_map": {
            "DM5.1": ["ev-2"],
            "DM5.6": ["ev-2"],
            "DM5.5": ["ev-2"],
            "DS4.2": ["ev-3"],
            "C6.4": ["ev-1"],
            "C6.3": ["ev-1"],
            "V2.4": ["ev-4"],
            "V2.1": ["ev-6"],
            "L8.3": [],
        },
        "state": StubState(),
    },
    "distribusi_mati_tanpa_outreach": {
        # Top-1 = a 3-letter domain (DS4) → exercises the `experiment_priority` flag, which used
        # to be hardcoded as the tuple ("C6", "DS4", "V2") in confidence.py. Under the legacy
        # mode, "DS" never matched; under per_domain, DS4 matches → +0.25.
        "evidence": [
            _ev("ev-d1", "tidak ada outreach sama sekali, hanya menunggu inquiry",
                "behavioral", "MOTION"),
            _ev("ev-d2", "berhenti posting sejak 4 bulan lalu", "behavioral", "MOTION"),
            _ev("ev-d3", "jarang outreach, volume rendah", "self_reported", "GOAL"),
        ],
        "evidence_map": {"DS4.2": ["ev-d1", "ev-d2"]},
        "state": None,
    },
    "tanpa_state_no_evidence": {
        # Degradation path: the LLM returned an empty mapping, state not built yet.
        "evidence": [],
        "evidence_map": {},
        "state": None,
    },
}


def _ranking_payload(ranking) -> list[dict]:
    """Ranking values, sorted by constraint_id (stable).

    SEMANTIC order is not stored here — see `_rank_order()`, which drops the `set`
    iteration noise (DEV-3) while still pinning who is above whom.
    """
    return sorted(
        (
            {
                "constraint_id": h.constraint_id,
                "score": h.score,
                "effective_score": h.effective_score,
                "evidence_strength": h.evidence_strength,
                "diagnostic_fit": h.diagnostic_fit,
                "decision_relevance": h.decision_relevance,
                "supporting_evidence_ids": sorted(h.supporting_evidence_ids),
            }
            for h in ranking
        ),
        key=lambda r: r["constraint_id"],
    )


def _rank_order(ranking, cmap) -> list[str]:
    """Semantic order: tie groups sorted by constraint_id, groups stay in order.

    The engine sorts by key (-effective_score, status_rank, upstream_rank).
    Two constraints with ALL THREE of those values equal are a true tie — their order
    depends on `set` iteration (DEV-3) and is not a contract. What is pinned: group boundaries.
    """
    status = {c.constraint_id: c.status for c in cmap}
    groups: list[list[str]] = []
    key_of: tuple | None = None
    for h in ranking:
        k = (h.effective_score, status.get(h.constraint_id), upstream_rank(h.constraint_id))
        if k != key_of:
            groups.append([])
            key_of = k
        groups[-1].append(h.constraint_id)
    return [cid for group in groups for cid in sorted(group)]


def _mechanism_payload(evidence_map, evidence) -> dict:
    boost, weights = mechanism_boost(evidence_map, evidence)
    return {
        "boost": {cid: sorted(ids) for cid, ids in sorted(boost.items())},
        "weights": dict(sorted(weights.items())),
        "detected": {m: sorted(ids) for m, ids in sorted(detect_mechanisms(evidence).items())},
    }


def build_snapshot() -> dict:
    """Deterministic portrait of every stage the P5 refactor will touch."""
    ontology = json.loads((ROOT / "ontology" / "constraints.json").read_text(encoding="utf-8"))
    out: dict = {
        "pack": {
            "id": pack_id(),
            "version": pack_version(),
            "domain_order": domain_order(),
            "mechanism_ids": sorted(MECHANISMS),
        },
        "scenarios": {},
        "rule_activation": {},
    }
    for name, spec in SCENARIOS.items():
        evidence = spec["evidence"]
        emap = spec["evidence_map"]
        state = spec["state"]
        ranking = score_hypotheses(emap, evidence, **_boost_kwargs(emap, evidence))
        cmap = build_constraint_map(ranking, evidence, ontology, state)
        penalty, probes = gap_consequences(evidence)
        out["scenarios"][name] = {
            "ranking": _ranking_payload(ranking),
            "rank_order": _rank_order(ranking, cmap),
            "status": {c.constraint_id: c.status for c in cmap},
            "tier": {c.constraint_id: c.tier for c in cmap},
            "notes": {c.constraint_id: c.note for c in cmap if c.note},
            "overall_confidence": overall_confidence(ranking, evidence),
            "split_confidences": split_confidences(ranking, evidence, state),
            "gap": {"penalty": penalty, "probes": probes},
            "systemic_risk": {
                cid: is_systemic_risk(cid, state)
                for cid in sorted(set(emap) | {"L8.3", "L8.1", "C6.1"})
            },
            "mechanisms": _mechanism_payload(emap, evidence),
        }
    # M5: rule source activation = one list for the whole ledger (no per-phase gating).
    out["rule_activation"] = {"active_rule_sources": sorted(active_rule_sources())}
    return out


def _boost_kwargs(evidence_map, evidence) -> dict:
    """mechanism_boost → score_hypotheses kwargs (mech_boost, mech_weights)."""
    mech_boost, mech_weights = mechanism_boost(evidence_map, evidence)
    return {"mech_boost": mech_boost, "mech_weights": mech_weights}


# ---------------------------------------------------------------------------
# Known deviations — deliberately pin bugs; WILL fail when their phase arrives.
# ---------------------------------------------------------------------------

def test_f7_plafon_impact_struktural() -> None:
    """F7: without measurable-effect evidence, IMPACT confidence never exceeds the cap.

    This is what makes the P0-5 invariant (`revenue impact confidence < 0.5`) true for the
    right REASON — not because extraction happens to be sparse.
    """
    for name, spec in SCENARIOS.items():
        if not spec["evidence_map"]:
            continue  # degradation path (empty ranking)
        kwargs = _boost_kwargs(spec["evidence_map"], spec["evidence"])
        rk = score_hypotheses(spec["evidence_map"], spec["evidence"], **kwargs)
        ric = split_confidences(rk, spec["evidence"], spec["state"])["revenue_impact_confidence"]
        assert ric <= IMPACT_CAP_NO_EFFECT_EVIDENCE, (
            f"{name}: ric={ric} melampaui plafon {IMPACT_CAP_NO_EFFECT_EVIDENCE} "
            "padahal belum ada bukti efek terukur"
        )


def test_f7_kelengkapan_state_tidak_menaikkan_keyakinan_dampak() -> None:
    """Overconfidence-pattern guard (Oskamp 1965): case information ≠ effect evidence.

    Two IDENTICAL fixtures except for state completeness → `revenue_impact_confidence` must
    be the SAME; only `constraint_confidence` may differ.
    """
    spec = SCENARIOS["pipeline_tipis_followup_bocor"]
    kwargs = _boost_kwargs(spec["evidence_map"], spec["evidence"])
    rk = score_hypotheses(spec["evidence_map"], spec["evidence"], **kwargs)
    lengkap = split_confidences(rk, spec["evidence"], StubState())
    kosong = split_confidences(rk, spec["evidence"], StubState(
        demand_sufficiency="UNKNOWN",
        pricing_architecture="UNKNOWN",
        response_latency_days=None,
        acquisition_hours_per_week=None,
    ))
    assert lengkap["revenue_impact_confidence"] == kosong["revenue_impact_confidence"], (
        "kelengkapan state mengubah keyakinan DAMPAK → formula kembali memakai info "
        "kasus sebagai bukti efek (pola overconfidence)"
    )
    assert lengkap["constraint_confidence"] >= kosong["constraint_confidence"], (
        "state lebih lengkap seharusnya menaikkan (atau menyamakan) keyakinan CONSTRAINT"
    )


def test_lexicon_deklarasi_per_domain_berlaku() -> None:
    """Phase D contract: per-domain lexicon declarations TAKE EFFECT (previously inert for 3 letters).

    Regression guarded: the return of the `constraint_id[:2]` lookup.
    """
    assert reversibility_weight("DM5.1") == 0.97, "deklarasi DM5 (0.97) harus berlaku"
    assert reversibility_weight("D1.2") == 0.97
    assert reversibility_weight("DS4.2") == 1.0, "DS4 deklarasi 1.0 (= default)"
    assert has_decision_priority("DS4.2") is True, "DS4 harus ikut (dulu tidak pernah)"
    assert has_decision_priority("DM5.1") is True, "DM5 harus ikut (dulu tidak pernah)"
    assert has_decision_priority("M3.1") is False
    assert has_experiment_priority("DS4.2") is True, "pengganti tuple hardcoded di confidence.py"
    assert has_experiment_priority("DM5.1") is False, "DM5 bukan domain eksperimen"


def test_lexicon_total_dan_setiap_lookup_resolve_ke_deklarasi() -> None:
    """Every ontology prefix has a lexicon entry, and lookups actually resolve.

    This guards the core F1/F4 finding: a MISS lookup used to silently fall back to the
    default, so a scoring factor could die without a trace.
    """
    constraints = json.loads((ROOT / "ontology" / "constraints.json").read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "ontology" / "domain_pack.json").read_text(encoding="utf-8"))
    used = {cid.split(".", 1)[0] for cid in constraints["constraints"]}
    entries = {d["prefix"]: d for d in manifest["constraint_domains"]}

    dp._assert_lexicon_total(declared=set(entries), used=used)  # total = no raise

    for prefix in sorted(used):
        cid = f"{prefix}.1"
        entry = entries[prefix]
        assert dp.reversibility_weight(cid) == entry["reversibility"], f"{cid} tidak resolve"
        assert dp.has_decision_priority(cid) is entry["decision_priority"], f"{cid} tidak resolve"
        assert dp.has_experiment_priority(cid) is entry.get("experiment_priority", False), \
            f"{cid} tidak resolve"


def test_guard_totality_menolak_dua_arah() -> None:
    """Negative test: the totality guard really rejects (not vacuous)."""
    cases = (
        ({"D1", "V2"}, {"D1", "V2", "L8"}, "prefix ontology tanpa entri lexicon"),
        ({"D1", "V2", "XX"}, {"D1", "V2"}, "entri lexicon menganggur"),
    )
    for declared, used, label in cases:
        try:
            dp._assert_lexicon_total(declared=set(declared), used=set(used))
        except RuntimeError as e:
            assert "TIDAK TOTAL" in str(e), f"{label}: pesan guard harus eksplisit, dapat: {e}"
        else:
            raise AssertionError(f"{label}: guard TIDAK menolak (vacuous)")


def test_f_mechanism_berasal_dari_katalog_pack() -> None:
    """Phase F: mechanism clusters + signals are read from the pack catalog, not constants in core.

    Regression guarded: domain identity (cluster id + signal vocabulary) returning to
    `core/stages/mechanisms.py`.
    """
    catalog = dp.load_mechanisms()
    assert len(catalog.mechanisms) >= 6, "katalog harus memuat klaster mekanisme"
    known = set(dp.ontology_constraint_ids())
    used = {c for m in catalog.mechanisms for c in m.constraints}
    assert used <= known, f"mekanisme merujuk constraint di luar ontology: {sorted(used - known)}"
    assert all(m.signals for m in catalog.mechanisms), "setiap mekanisme wajib punya sinyal"
    # and detection still works (behavior unchanged)
    ev = [_ev("k1", "lead macet di follow dan terbengkalai", "behavioral", "MOTION")]
    assert "lead_leakage" in detect_mechanisms(ev)


def test_f_guard_rujukan_mechanism_menolak() -> None:
    """Negative test: the mechanism↔ontology reference guard really rejects (not vacuous)."""
    try:
        dp._assert_mechanism_constraints_known(used={"C6.4", "ZZ9.9"}, known={"C6.4"})
    except RuntimeError as e:
        assert "TIDAK ADA di ontology" in str(e), f"pesan guard harus eksplisit, dapat: {e}"
    else:
        raise AssertionError("guard TIDAK menolak constraint tak dikenal (vacuous)")
    # positive side: a subset must pass without raising
    dp._assert_mechanism_constraints_known(used={"C6.4"}, known={"C6.4", "C6.3"})


def test_e2_marker_kejadian_berasal_dari_lexicon() -> None:
    """Phase E: the domain marker table is read from the lexicon, not constants in the generic layer.

    Regression guarded: the domain vocabulary (user language) returning to `core/`.
    """
    markers = dp.evidence_markers()
    assert markers.event and markers.contrast, "domain_pack harus mendeklarasikan evidence_markers"
    assert _is_event_evidence(_ev("m1", "prospek hilang ke kompetitor", "transactional", "CONVERSION"))
    assert _is_event_evidence(_ev("m2", "6/10 jadi waktu rajin follow-up", "outcome", "DEMAND"))
    assert not _is_event_evidence(
        _ev("m3", "klien membayar retainer rutin", "transactional", "REVENUE_STATE")
    )


def test_e1_kontrak_disqualifier_menolak_prosa_telanjang() -> None:
    """Phase E: disqualifiers MUST be executable, or explicitly flagged non-executable.

    Bare prose = a declaration that binds nothing (this was its original shape).
    """
    assert validate_disqualifiers({"X": {"disqualifiers": ["prosa saja"]}}), (
        "prosa telanjang harus ditolak kontrak v0.3"
    )
    assert validate_disqualifiers(
        {"X": {"disqualifiers": [{"id": "a", "source_prose": "p", "executable": False}]}}
    ), "executable=false tanpa `reason` harus ditolak"
    assert validate_disqualifiers(
        {"X": {"disqualifiers": [{"id": "a", "source_prose": "p", "predicate": {}, "note": "n"}]}}
    ), "executable tanpa `predicate` harus ditolak"
    assert not validate_disqualifiers({
        "X": {"disqualifiers": [
            {"id": "a", "source_prose": "p", "predicate": {"min_evidence_count": 1}, "note": "n"},
            {"id": "b", "source_prose": "p", "executable": False, "reason": "belum bisa"},
        ]}
    }), "bentuk yang benar harus lolos"


def test_e1_disqualifier_dm55_terpicu_dari_deklarasi() -> None:
    """Phase E: the DM5.5 rule now comes from the ontology declaration, not from `core`.

    Before: `if constraint_id == "DM5.5"` in confidence.py — domain identity in the generic
    layer. This assertion keeps the behavior identical, now via the predicate.
    """
    ontology = json.loads((ROOT / "ontology" / "constraints.json").read_text(encoding="utf-8"))
    transaksi = [_ev("d1", "klien bayar retainer", "transactional", "REVENUE_STATE")]
    selfrep = [_ev("d2", "saya rasa mereka ragu", "self_reported", "DEMAND")]
    assert disqualifier_check("DM5.5", ontology, transaksi), "transaksi nyata harus memicu disqualifier"
    assert disqualifier_check("DM5.5", ontology, selfrep) is None
    assert disqualifier_check("C6.4", ontology, transaksi) is None, "constraint tanpa disqualifier → None"


def test_f4_tag_mekanisme_memuat_id_asli() -> None:
    """F4 (fixed in Phase C): the `mech:` tag payload = the REAL mechanism id.

    Regression guarded: `f"mech:{'+'.join(sorted(m))}"` with `m` being a STRING
    mechanism id sorts CHARACTERS → payloads like `mech:_+c+e+e+...`.
    """
    emap = {"C6.4": ["ev-1", "ev-2"]}
    ev = [
        _ev("ev-1", "tidak di-follow sampai macet", "transactional", "CONVERSION"),
        _ev("ev-2", "balasan lambat, lead terbengkalai", "behavioral", "MOTION"),
    ]
    ranking = score_hypotheses(emap, ev, **_boost_kwargs(emap, ev))
    by_id = {h.constraint_id: h for h in ranking}
    assert "C6.1" in by_id, "C6.1 harus masuk ranking lewat mechanism boost (cluster lead_leakage)"
    tags = [t for t in by_id["C6.1"].supporting_evidence_ids
            if isinstance(t, str) and t.startswith("mech:")]
    assert tags, "C6.1 harus punya minimal satu tag mech:"
    resolved: set[str] = set()
    for payload in (t[5:] for t in tags):
        resolved |= set(payload.split("+"))
    assert resolved <= set(MECHANISMS), (
        f"payload tag mech: harus mechanism id asli, dapat {sorted(resolved)} — "
        "indikasi regresi F4 (sorted atas string)"
    )
    assert "lead_leakage" in resolved, f"mekanisme lead_leakage harus ter-resolve, dapat {resolved}"


def test_f4_status_mekanisme_murni_dinilai_dari_bukti_mekanisme() -> None:
    """F4 (fixed in Phase C): mechanism-pure constraints are scored from mechanism evidence.

    The D6 intent (iter-9) only truly works after the tag expansion fix: previously
    `C6.1` was always UNRESOLVED (weight 0.5), so its score was cut in half.
    """
    spec = SCENARIOS["pipeline_tipis_followup_bocor"]
    mech_kwargs = _boost_kwargs(spec["evidence_map"], spec["evidence"])
    ranking = score_hypotheses(spec["evidence_map"], spec["evidence"], **mech_kwargs)
    by_id = {h.constraint_id: h for h in ranking}
    ontology = json.loads((ROOT / "ontology" / "constraints.json").read_text(encoding="utf-8"))
    cmap = {c.constraint_id: c for c in
            build_constraint_map(ranking, spec["evidence"], ontology, spec["state"])}
    assert cmap["C6.1"].status != "UNRESOLVED", (
        "C6.1 hanya didukung mekanisme; jika UNRESOLVED lagi berarti ekspansi tag "
        "`mech:` rusak (regresi F4)"
    )
    assert by_id["C6.1"].effective_score > 0.1, (
        "skor mekanisme-murni tidak boleh terpotong STATUS_WEIGHT UNRESOLVED (0.5)"
    )


def test_levela_sum_tanpa_declared_tidak_jadi_current() -> None:
    """Level A (G7 bug 21:30, ~33% incidence): component SUM without declared must NOT become current.

    Reproduction: goal evidence contains 'Rp30jt/bulan ... per klien' → Rp30 (the restated
    total) also gets summed as a component → SUM=60 → reconcile(None, 60) used to VERIFY it
    → current=60 >= target=60 → gap=None + REVENUE CEILING lost. New rule: without a total
    statement (declared), the component SUM is rejected as current — UNKNOWN has a
    consequence (P2), it is not silently reconciled (internal-docs §5.3).
    """
    ev = [
        _ev("ev-g1", "Revenue retainer berjalan Rp30jt/bulan dengan nilai dan durasi per klien",
            "outcome", "Revenue sekarang stabil Rp30 juta/bulan dari 3 klien retainer"),
        _ev("ev-g2", "Klien klinik kecantikan: Rp12jt/bulan, berjalan 8 bulan",
            "transactional", "klinik kecantikan Rp12 juta per bulan"),
        _ev("ev-g3", "Klien restoran: Rp10jt/bulan, berjalan 6 bulan",
            "transactional", "restoran Rp10 juta per bulan"),
        _ev("ev-g4", "Sekolah Rp8jt/bulan, kontrak semester",
            "transactional", "sekolah Rp8 juta per bulan"),
    ]
    s_bug = build_revenue_state(ev, goal_text="Target Rp60 juta/bulan dalam 90 hari")
    assert s_bug.current_monthly != 60.0, (
        f"LEVEL A REGRESI: current={s_bug.current_monthly} — SUM komponen tanpa "
        "declared kembali dipakai sebagai current (total-dinyatakan-ulang ikut terjumlah)"
    )
    # and the HEALTHY case (an explicit declared exists) must not break either:
    ev_ok = ev + [_ev("ev-g0", "Total revenue stabil Rp30jt/bulan",
                      "outcome", "stabil Rp30 juta/bulan")]
    s_ok = build_revenue_state(ev_ok, goal_text="Target Rp60 juta/bulan dalam 90 hari")
    assert s_ok.current_monthly == 30.0 and s_ok.gap_monthly == 30.0, (
        f"REGRESI kasus sehat: current={s_ok.current_monthly} gap={s_ok.gap_monthly}"
    )


# ---------------------------------------------------------------------------
# Golden runner
# ---------------------------------------------------------------------------

def _dump(payload: dict) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def _diff(golden: str, received: str) -> str:
    import difflib
    lines = list(difflib.unified_diff(golden.splitlines(), received.splitlines(),
                                      "golden", "received", lineterm="", n=2))
    return "\n".join(lines[:120]) + ("\n  … (dipotong)" if len(lines) > 120 else "")


def main(argv: list[str]) -> int:
    if "--dev" in argv:
        import inspect
        failed = 0
        for name, fn in sorted(globals().items()):
            if name.startswith("test_") and inspect.isfunction(fn):
                try:
                    fn()
                    print(f"PASS {name}")
                except AssertionError as e:
                    failed += 1
                    print(f"FAIL {name}: {e}")
        print("ALL PASS" if not failed else f"{failed} FAILED")
        return 1 if failed else 0

    received = _dump(build_snapshot())
    if "--approve" in argv:
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(received, encoding="utf-8")
        print(f"✅ golden di-approve → {GOLDEN.relative_to(ROOT)}")
        print("   PERIKSA diff-nya sebelum commit.")
        return 0
    if not GOLDEN.exists():
        print(f"❌ golden belum ada: {GOLDEN.relative_to(ROOT)}")
        print("   Buat dengan: python evals/test_characterization.py --approve")
        return 1
    golden = GOLDEN.read_text(encoding="utf-8")
    if golden == received:
        print("✅ CHARACTERIZATION PASS — perilaku stage deterministik identik dengan golden")
        return 0
    print("❌ CHARACTERIZATION FAIL — perilaku berubah. Baca diff, lalu putuskan:")
    print("   (a) perubahan disengaja → --approve + commit golden; (b) regresi → perbaiki kode.")
    print(_diff(golden, received))
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
