"""DCP - Diagnostic Contract Parity (int 16 S1; DCP-01..06).

Proves that deep synthesis (agents/diagnosis.synthesize via /finalize) uses ONE canonical current
meaning, on par with provisional navigation, and never re-awakens a superseded claim.
Via real HTTP (TestClient) + deterministic mock provider + temp store.

Run: .venv/bin/python evals/test_recovery_diagnostic_parity.py  (deterministic, no network)
"""
from __future__ import annotations

import atexit
import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from evals._store_isolation import isolate_store  # noqa: E402

isolate_store()  # eval: store redirected to tmp — production store untouched

import store.adjudication_ledger as ledger  # noqa: E402
import store.events as event_store  # noqa: E402
import store.funnel as funnel  # noqa: E402
import store.path_states as path_states  # noqa: E402
import store.route_execution as route_execution  # noqa: E402
import store.route_lineages as rl  # noqa: E402
import store.workspace as workspace  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="nvl-dcp-"))
rl._BASE = _TMP / "lineages"
ledger._LEDGER_ROOT = _TMP / "ledger"
workspace._BASE = _TMP / "workspaces"
route_execution._BASE = _TMP / "workspaces"
funnel._PATH = _TMP / "funnel.jsonl"
path_states._BASE = _TMP
path_states._STATES = _TMP / "path_states.json"
path_states._HISTORY = _TMP / "path_history.jsonl"
event_store.EVENTS_DIR = _TMP / "events"

from fastapi.testclient import TestClient  # noqa: E402
from live_qualify import fabricated_revenue_fields  # noqa: E402

import app.main as app_main  # noqa: E402
from core.reasoning.contract import NextMoveProposal  # noqa: E402
from core.schema.evidence import current_evidence  # noqa: E402
from core.semantic.contract import SemanticObservation  # noqa: E402
from providers.mock import MockProvider  # noqa: E402
from store.memory import store  # noqa: E402

_PASS = 0
_FAIL = 0
_created = []


def check(name, cond, detail=""):
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print("  OK  " + name)
    else:
        _FAIL += 1
        print("  GAGAL  " + name + (" - " + str(detail) if detail else ""))


class Hybrid(MockProvider):
    name = "mock"

    def __init__(self):
        super().__init__()
        self.sem = []
        self.nm = None
        self.nm_calls = 0
        self.diag_prompts = []
        self.diag = None

    def structured_call(self, schema, system, user, retries=2):
        if schema is SemanticObservation and self.sem:
            return self.sem.pop(0)
        if schema is NextMoveProposal and self.nm is not None:
            from core.reasoning.reasoner import parse_snapshot_prompt
            self.nm_calls += 1
            return NextMoveProposal.model_validate(self.nm(parse_snapshot_prompt(user), self.nm_calls))
        if schema.__name__ == "DiagnosisDraft":
            self.diag_prompts.append(user)
            if self.diag is not None:
                from agents.diagnosis import DiagnosisDraft
                return DiagnosisDraft.model_validate(self.diag(user))
        return super().structured_call(schema, system, user, retries)


LLM = Hybrid()
app_main.get_llm = lambda: LLM
client = TestClient(app_main.app)
atexit.register(lambda: [(store.PERSIST_DIR / (sid + ".json")).unlink(missing_ok=True) for sid in _created])


def obs(*claims, relations=()):
    return SemanticObservation(contract_version="so.v1", language="id", claims=list(claims),
                               relations=list(relations), uncertainties=[])


def cl(*a, **kw):
    import test_recovery_semantic as R
    return R.cl(*a, **kw)


def qty(**kw):
    import test_recovery_semantic as R
    return R.qty(**kw)


def new_session(user, goal="bisnis saya", lang="id", **extra):
    body = {"goal_text": goal, "language": lang}
    body.update(extra)
    if user:
        body["user_id"] = user
    r = client.post("/session", json=body)
    assert r.status_code == 200, r.text
    sid = r.json()["session_id"]
    _created.append(sid)
    return sid


def say(sid, text, **kw):
    return client.post("/session/" + sid + "/message", json={"text": text, **kw})


def finalize(sid, force=False):
    return client.post("/session/" + sid + "/finalize" + ("?force=1" if force else ""))


def evidence_block(prompt):
    body = prompt.split("EVIDENCE (current, authoritative):", 1)[1]
    for marker in ("HISTORICAL CLAIMS", "ONTOLOGY:"):
        if marker in body:
            return body.split(marker, 1)[0]
    return body


def historical_block(prompt):
    if "HISTORICAL CLAIMS" not in prompt:
        return ""
    return prompt.split("HISTORICAL CLAIMS", 1)[1].split("ONTOLOGY:", 1)[0]


def ids_in(text):
    return re.findall(r"- \[(ev-[a-z0-9_-]+)\]", text)


def draft_for(cid, cur_ids, hist_ids=None):
    return {
        "where_you_are": "Ada indikasi pada " + cid + ".",
        "primary_constraint": "Kendala " + cid + ".",
        "primary_constraint_id": cid,
        "secondary_constraints": [],
        "why": ["bukti saat ini menunjuk " + cid],
        "next_best_action": "Uji " + cid + " lewat eksperimen kecil 7 hari.",
        "first_step_today": "Catat satu pengukuran hari ini.",
        "day_by_day": [],
        "outreach_script": "",
        "success_metric": "satu pengukuran tercatat",
        "well_know_when": "ada bukti baru",
        "pivot_rule": "bila nihil, tinjau ulang",
        "reassess_window_days": 14,
        "evidence_map": {cid: list(cur_ids) + list(hist_ids or [])},
    }


def node_with(sid, needle):
    nodes = store.get(sid).state_graph["nodes"]
    return [nid for nid, n in nodes.items() if needle in (n.get("verbatim") or "")]


# ── DCP-01 ────────────────────────────────────────────────────────────────────

def test_dcp01_canonical_source_fidelity():
    print("DCP-01 - canonical source fidelity: koreksi tidak dibangunkan kembali")
    LLM.nm = None
    LLM.diag = None
    LLM.sem = [obs(cl("c0", "desire", "saya", "wants", "saya ingin omzet naik"))]
    sid = new_session("u-dcp1", goal="saya ingin omzet naik")
    LLM.sem = [obs(cl("c1", "assumption", "masalah", "probably_is",
                      "Masalah saya marketing; saya rasa leads sangat sedikit"))]
    say(sid, "Masalah saya marketing; saya rasa leads sangat sedikit.")
    mkt = node_with(sid, "marketing")
    assert mkt, "klaim marketing tidak ter-commit"
    LLM.sem = [obs(cl("c2", "claim", "leads", "are_many", "Leads ternyata cukup banyak",
                      supersedes=mkt[0], revision_kind="correction", revision_reason="koreksi"))]
    say(sid, "Leads ternyata cukup banyak.")
    LLM.sem = [obs(cl("c3", "claim", "prospek", "not_followed_up",
                      "Masalah sebenarnya banyak prospek yang tidak di-follow-up"))]
    say(sid, "Masalah sebenarnya banyak prospek yang tidak di-follow-up.")
    s = store.get(sid)
    cur = current_evidence(s.evidence)
    hist = [e for e in s.evidence if e.superseded]
    check("koreksi menandai evidence lama superseded (sejarah tetap)", len(hist) >= 1, len(hist))
    check("evidence current tidak memuat yang superseded",
          not ({e.id for e in cur} & {e.id for e in hist}))

    def d(prompt):
        return draft_for("DS4.2", ids_in(evidence_block(prompt)), ids_in(historical_block(prompt)))

    LLM.diag = d
    fin = finalize(sid)
    check("finalize 200", fin.status_code == 200, fin.text[:200])
    art = fin.json()
    p = LLM.diag_prompts[-1]
    eb = evidence_block(p)
    eids = ids_in(eb)
    check("EVIDENCE block memuat evidence saat ini", all(e.id in eids for e in cur),
          (eids, [e.id for e in cur]))
    check("evidence superseded TIDAK ada di EVIDENCE block",
          not any(e.id in eids for e in hist), eids)
    check("evidence superseded tetap tersedia di blok HISTORICAL",
          ("HISTORICAL CLAIMS" in p) and any(e.id in historical_block(p) for e in hist))
    supp = {i for a in art.get("reasoning_trace", {}).get("evidence_activations", [])
            for i in (a.get("supports") or [])}
    check("tidak ada id historis di supports trace", not (supp & {e.id for e in hist}), sorted(supp))
    check("n_evidence_historical tercatat", art["metrics"].get("n_evidence_historical", 0) >= len(hist),
          art["metrics"].get("n_evidence_historical"))
    check("primary constraint tidak membangunkan kembali marketing lama",
          "marketing" not in (art.get("primary_constraint") or "").lower(),
          art.get("primary_constraint"))


def test_dcp01b_revenue_state_transcript_fidelity():
    print("DCP-01b - RevenueState tidak menyerap angka klaim superseded via anchor transkrip")
    from core.schema.evidence import EvidenceItem
    from domains.revenue.stages.state import build_revenue_state
    h = "30 jam per minggu untuk prospek"
    c = "sekarang waktu prospecting saya jauh lebih sedikit"
    hist = EvidenceItem(id="ev-dcp1b-h", topic="capacity", level="self_reported",
                        signal=h, source_quote=h, superseded=True)
    cur = EvidenceItem(id="ev-dcp1b-c", topic="capacity", level="self_reported",
                       signal=c, source_quote=c, superseded=False)
    transcript = h + "\n" + c
    # Without historical separation, the transcript anchor absorbs 30 (an old claim number) -> DCP-01.
    leaked = build_revenue_state([cur], "turunkan jam prospek", transcript=transcript)
    with_hist = build_revenue_state([cur], "turunkan jam prospek", transcript=transcript,
                                    historical_evidence=[hist])
    check("repro: tanpa historical_evidence angka lama bocor (alasan perbaikan)",
          leaked.acquisition_hours_per_week == 30.0, leaked.acquisition_hours_per_week)
    check("angka klaim superseded tidak menjadi state saat ini",
          with_hist.acquisition_hours_per_week is None, with_hist.acquisition_hours_per_week)


def test_dcp01c_mixed_sentence_current_fact_survives():
    print("DCP-01c - kalimat campuran (historis + fakta aktif): pembersihan bedah, bukan buang baris")
    from core.schema.evidence import EvidenceItem
    from domains.revenue.stages.state import _strip_historical_transcript, build_revenue_state
    hist_text = "Dulu saya habiskan 30 jam per minggu untuk prospek"
    # The active clause is in the TRANSCRIPT but NOT in the ledger (the fallback is what must save
    # the active fact) — exactly the audit scenario: if the row is dropped wholesale, "now only 8 hours" is lost.
    cur_text = "sekarang waktu prospek saya jauh lebih sedikit"
    line = f"{hist_text}, sekarang untuk prospek hanya 8 jam per minggu."
    hist = EvidenceItem(id="ev-mix-h", topic="capacity", level="self_reported",
                        signal=hist_text, source_quote=hist_text, superseded=True)
    cur = EvidenceItem(id="ev-mix-c", topic="capacity", level="self_reported",
                       signal=cur_text, source_quote=cur_text, superseded=False)

    stripped = _strip_historical_transcript(line, [hist])
    check("baris campuran tidak dibuang utuh - fakta aktif tersisa",
          "8 jam" in (stripped or ""), stripped)
    check("fragmen historis dibersihkan secara bedah (30 jam hilang)",
          "30 jam" not in (stripped or ""), stripped)

    leaked = build_revenue_state([cur], "turunkan jam prospek", transcript=line)
    check("repro: tanpa pemisahan historis, angka historis (30) menjadi acq anchor",
          leaked.acquisition_hours_per_week == 30.0, leaked.acquisition_hours_per_week)
    with_hist = build_revenue_state([cur], "turunkan jam prospek", transcript=line,
                                    historical_evidence=[hist])
    check("angka AKTIF (8 jam) terselamatkan sebagai acq anchor",
          with_hist.acquisition_hours_per_week == 8.0, with_hist.acquisition_hours_per_week)


# ── DCP-02 ────────────────────────────────────────────────────────────────────

def test_dcp02_hypothesis_revision():
    print("DCP-02 - revisi hipotesis: koreksi mengubah dukungan secara traceable")
    LLM.nm = None
    LLM.diag = None
    LLM.sem = [obs(cl("c0", "desire", "saya", "wants", "saya ingin omzet naik"))]
    sid = new_session("u-dcp2", goal="saya ingin omzet naik")
    LLM.sem = [obs(cl("c1", "claim", "pembeli", "says", "Kata pembeli harga saya kemahalan"))]
    say(sid, "Kata pembeli harga saya kemahalan.")

    def d(prompt):
        cur = ids_in(evidence_block(prompt))
        hist = ids_in(historical_block(prompt))
        cid = "C6.3" if "kemahalan" in evidence_block(prompt).lower() else "DS4.2"
        return draft_for(cid, cur, hist)

    LLM.diag = d
    v1 = finalize(sid).json()
    check("diagnosis v1 memilih C6.3 dari bukti value framing",
          v1["primary_constraint_id"] == "C6.3", v1["primary_constraint_id"])
    price = node_with(sid, "kemahalan")
    assert price, "klaim harga tidak ter-commit"
    LLM.sem = [obs(cl("c2", "claim", "saya", "rarely_follows_up",
                      "Ternyata masalahnya bukan harga, tapi saya tidak pernah follow-up prospek",
                      supersedes=price[0], revision_kind="correction", revision_reason="koreksi"))]
    say(sid, "Ternyata masalahnya bukan harga, tapi saya tidak pernah follow-up prospek.")
    ra = client.post("/session/" + sid + "/reassess")
    check("reassess 200", ra.status_code == 200, ra.text[:200])
    v2 = client.get("/session/" + sid + "/diagnosis").json()
    check("diagnosis v2 TIDAK mempertahankan C6.3 hanya karena dipilih sebelumnya",
          v2["primary_constraint_id"] != "C6.3", v2["primary_constraint_id"])
    check("dukungan bukti harga (superseded) tidak lagi aktif",
          not any("kemahalan" in (e.signal or "").lower() for e in current_evidence(store.get(sid).evidence)))
    cps = client.get("/session/" + sid + "/checkpoints").json()["checkpoints"]
    check("v1 dipertahankan utuh sebagai historis",
          cps[0]["status"] == "superseded"
          and store.get(sid).checkpoints[0]["diagnosis"]["primary_constraint_id"] == "C6.3")
    check("v2 punya basis sendiri dan menautkan perubahan",
          cps[1]["status"] == "current" and cps[1]["supersedes"] == cps[0]["checkpoint_id"])


# ── DCP-03 ────────────────────────────────────────────────────────────────────

def test_dcp03_provisional_deep_consistency():
    print("DCP-03 - konsistensi provisional vs deep (state/goal/evidence sama)")
    LLM.nm = None
    LLM.diag = None
    LLM.sem = [obs(cl("c0", "desire", "saya", "wants", "saya ingin omzet naik"))]
    sid = new_session("u-dcp3", goal="saya ingin omzet naik")
    turns = [
        ("Saya punya 8 tahun pengalaman marketing.",
         cl("c1", "claim", "saya", "has_experience", "Saya punya 8 tahun pengalaman marketing")),
        ("Saya belum punya penawaran tertulis.",
         cl("c2", "gap", "penawaran", "missing", "Saya belum punya penawaran tertulis")),
        ("Ada 3 orang bertanya bulan ini.",
         cl("c3", "claim", "inquiry", "count", "Ada 3 orang bertanya bulan ini")),
    ]
    for text, claim in turns:
        LLM.sem = [obs(claim)]
        say(sid, text)
    before = client.get("/session/" + sid + "/navigation").json()["reality"]
    cur_ids = sorted(e.id for e in current_evidence(store.get(sid).evidence))
    # Audit 14 Oct 2026 (DCP-03): compare DECISION DATA provisional -> deep - the path set is computed
    # with the same path as the support layer (app/navigation.py), BEFORE finalize.
    from core.navigation.requirement_state import status_reader
    from domains.revenue.navigation import live as revenue_live
    from ontology.mapper.live_adjudication import support_of
    from store.requirement_state import user_requirement_reader
    s_now = store.get(sid)
    # R5/P0-B: compare against the actual PRODUCTION path (app/navigation.py) — the authoritative ledger
    # is counted provisional too, so the provisional -> deep comparison does not compare two different contexts.
    _reader = user_requirement_reader(s_now.user_id, support_of=support_of())
    prov = revenue_live.provisional_path_set(
        current_evidence(s_now.evidence), s_now.goal_text, s_now.transcript,
        s_now.state_graph or None, None, goal=getattr(s_now, "goal", None),
        historical_evidence=[e for e in s_now.evidence if getattr(e, "superseded", False)],
        ledger_state_of=status_reader(_reader))
    prov_strategies = {_pp.get("strategy_id") for _pp in prov.get("paths") or []}
    LLM.diag = lambda p: draft_for("DS4.2", ids_in(evidence_block(p)), ids_in(historical_block(p)))
    fin = finalize(sid)
    check("finalize 200", fin.status_code == 200, fin.text[:200])
    art = fin.json()
    after = client.get("/session/" + sid + "/navigation").json()["reality"]
    check("tanpa event user baru saat finalize: state_version sama",
          before["state_version"] == after["state_version"],
          (before["state_version"], after["state_version"]))
    cps = client.get("/session/" + sid + "/checkpoints").json()["checkpoints"]
    b = cps[-1]["binding"]
    check("binding checkpoint memakai evidence saat ini",
          sorted(b["source_evidence_refs"]) == cur_ids, (b["source_evidence_refs"], cur_ids))
    check("goal_id/goal_version konsisten provisional -> deep",
          b["goal_id"] == before["goal_id"] and b["goal_version"] == before["goal_version"])
    p = LLM.diag_prompts[-1]
    check("prompt deep memakai evidence saat ini",
          sorted(ids_in(evidence_block(p))) == cur_ids, ids_in(evidence_block(p)))
    check("basis penalaran deep tercatat (knowledge_activation)",
          isinstance(art.get("knowledge_activation"), dict)
          and "rule_evidence_map" in art["knowledge_activation"])
    # - DCP-03 (audit): provisional_path_set -> deep possible_paths -> divergence explanation -
    deep = art.get("possible_paths") or {}
    gen = deep.get("generation") or {}
    deep_strategies = {_pp.get("strategy_id") for _pp in deep.get("paths") or []}
    accounted = set(deep_strategies)
    accounted |= {r.get("strategy_id") for r in gen.get("rejected") or []}
    accounted |= {r.get("strategy_id") for r in gen.get("not_emergent") or []}
    accounted |= {r.get("strategy_id") for r in gen.get("undetermined") or []}
    accounted |= {row.get("direction") for row in gen.get("possibilities") or []}
    unaccounted = sorted(x for x in (prov_strategies - accounted) if x)
    check("path provisional tidak hilang tanpa jejak di deep (path/penolakan/undetermined tercatat)",
          not unaccounted, unaccounted)
    deep_refs = set()
    for _pp in deep.get("paths") or []:
        deep_refs |= set((_pp.get("provenance") or {}).get("evidence_ids") or [])
    check("path deep hanya beranjang ke evidence CURRENT (tanpa fakta baru/historis)",
          deep_refs <= set(cur_ids), sorted(deep_refs - set(cur_ids)))
    gctx = (deep.get("context") or {}).get("goal") or {}
    check("konteks Goal path deep = Goal sesi (tanpa rewrite diam-diam)",
          gctx.get("goal_id") == (store.get(sid).goal or {}).get("goal_id"),
          (gctx.get("goal_id"), (store.get(sid).goal or {}).get("goal_id")))


# ── DCP-04 ────────────────────────────────────────────────────────────────────

def test_dcp04_non_revenue_goal():
    print("DCP-04 - Goal non-revenue tetap typed dari Create Map ke diagnosis")
    LLM.nm = None
    LLM.diag = None
    LLM.sem = [obs(cl("c0", "goal", "founder", "reduce_hours",
                      "Saya ingin memangkas jam delivery saya jadi 10 jam per minggu", tense="future",
                      quantity=qty(value_kind="exact", value=10, unit="hours/week", period="weekly")))]
    sid = new_session("u-dcp4", goal="Saya ingin memangkas jam delivery founder jadi 10 jam per minggu",
                      metric_id="founder_delivery_hours", direction="DECREASE_TO_THRESHOLD",
                      unit="hours/week", target=10, measurement_window_days=30)
    g = store.get(sid).goal
    check("Goal metric_id/direction/unit/window bertahan di Create Map",
          g.get("metric_id") == "founder_delivery_hours"
          and g.get("direction") == "DECREASE_TO_THRESHOLD"
          and g.get("unit") == "hours/week" and g.get("measurement_window_days") == 30,
          {k: g.get(k) for k in ("metric_id", "direction", "unit", "measurement_window_days")})
    LLM.sem = [obs(cl("c1", "claim", "delivery", "takes",
                      "Delivery klien menghabiskan 25 jam per minggu",
                      quantity=qty(value_kind="exact", value=25, unit="hours/week", period="weekly")))]
    say(sid, "Delivery klien menghabiskan 25 jam per minggu.")
    LLM.diag = lambda p: draft_for("M3.4", ids_in(evidence_block(p)), ids_in(historical_block(p)))
    art = finalize(sid).json()
    g2 = store.get(sid).goal
    check("Goal tetap non-revenue setelah giliran & finalize",
          g2.get("metric_id") == "founder_delivery_hours" and g2.get("unit") == "hours/week",
          g2.get("metric_id"))
    check("narrative tidak memaksa omzet bulanan",
          "revenue_monthly" not in json.dumps(art.get("success_metric", "")).lower())
    check("RevenueState tetap proyeksi (dict), bukan kebenaran universal",
          isinstance(art.get("revenue_state"), dict))
    check("standing epistemik eksplisit tersedia", art.get("evidence_standing") in
          ("INSUFFICIENT", "WEAK", "SUPPORTED"), art.get("evidence_standing"))


# ── DCP-05 ────────────────────────────────────────────────────────────────────

def test_dcp05_low_evidence_honesty():
    print("DCP-05 - low-evidence finalize tetap jujur (throttle + revenue kanonik)")
    LLM.nm = None
    LLM.diag = None
    LLM.sem = [obs(cl("c0", "desire", "saya", "wants", "Saya ingin bisnis lebih tenang"))]
    sid = new_session("u-dcp5", goal="Saya ingin bisnis lebih tenang")

    def d(prompt):
        draft = draft_for("NO_FIT", ids_in(evidence_block(prompt)), [])
        # >3 actions: locks regression D-05 - the deferral message MUST move to explanation,
        # day_by_day stays at most 3 executable items (audit 14 Oct 2026; live failed len=4).
        draft["day_by_day"] = [f"Probe kecil hari {i}" for i in range(1, 6)]
        return draft

    LLM.diag = d
    art = finalize(sid).json()
    check("standing epistemik eksplisit & bukan SUPPORTED",
          art.get("evidence_standing") in ("INSUFFICIENT", "WEAK"), art.get("evidence_standing"))
    check("requires_new_evidence True", art.get("requires_new_evidence") is True)
    # dsc.v1 (int 18 §12.5): the label is NOT a constant — certification computed from facts, with a
    # coded reason. Weak evidence must not get a final label (two conditions: critical empty AND standing SUPPORTED).
    check("label sertifikasi turunan (bukan konstanta): provisional + alasan berkode",
          art.get("status") == "provisional" and bool(art.get("certification_reasons")),
          f"{art.get('status')} {art.get('certification_reasons')}")
    check("alasan sertifikasi memuat sebab standing yang benar (konsisten dengan artefak)",
          (("EVIDENCE_INSUFFICIENT" if art.get("evidence_standing") == "INSUFFICIENT" else "EVIDENCE_WEAK")
           in (art.get("certification_reasons") or [])),
          str(art.get("certification_reasons")))
    check("confidence band rendah/menengah", art.get("confidence_band") in ("LOW", "MEDIUM"),
          art.get("confidence_band"))
    day_items = art.get("day_by_day") or []
    check("prescription throttle: maksimal 3 tindakan executable",
          len(day_items) <= 3, len(day_items))
    check("penundaan fase lanjutan TIDAK menjadi ActionItem di day_by_day",
          not any("DIGANTUNG" in (it.get("text") or "") for it in day_items), day_items)
    reason = art.get("engine_disagreement") or ""
    check("penundaan/throttle terdokumentasi di explanation (engine_disagreement)",
          "DIGANTUNG" in reason or "THROTTLE" in reason, reason[:160])
    rs = art.get("revenue_state") or {}
    check("field kanonik RevenueState terbaca (regresi field hantu 'monthly_revenue')",
          "current_monthly" in rs, sorted(rs)[:8])
    bad = fabricated_revenue_fields(rs)
    check("tidak ada nilai moneter tanpa provenance di sources",
          bad == [], (bad, rs.get("sources")))
    check("current_monthly tetap None tanpa angka revenue di percakapan",
          rs.get("current_monthly") is None, rs.get("current_monthly"))
    check("target_monthly tidak dikarang tanpa dasar",
          rs.get("target_monthly") is None, rs.get("target_monthly"))


# ── DCP-06 ────────────────────────────────────────────────────────────────────

def test_dcp06_reassess_historical_integrity():
    print("DCP-06 - checkpoint/reassess: sejarah utuh, tidak ada duplikasi")
    LLM.nm = None
    LLM.diag = None
    LLM.sem = [obs(cl("c0", "desire", "saya", "wants", "saya ingin omzet naik"))]
    sid = new_session("u-dcp6", goal="saya ingin omzet naik")
    LLM.sem = [obs(cl("c1", "claim", "klien", "has", "Saya punya 3 klien aktif"))]
    say(sid, "Saya punya 3 klien aktif.")
    LLM.diag = lambda p: draft_for("DS4.2", ids_in(evidence_block(p)), ids_in(historical_block(p)))
    finalize(sid)
    cps_full = store.get(sid).checkpoints
    v1_dump = json.dumps(cps_full[0]["diagnosis"], sort_keys=True, default=str)
    v1_binding = json.dumps(cps_full[0]["binding"], sort_keys=True, default=str)
    cl_node = node_with(sid, "3 klien aktif")
    assert cl_node, "klaim klien tidak ter-commit"
    LLM.sem = [obs(cl("c2", "claim", "klien", "has", "Ralat: klien aktif saya sebenarnya 1",
                      quantity=qty(value_kind="exact", value=1, unit="klien", period="unspecified"),
                      supersedes=cl_node[0], revision_kind="correction", revision_reason="koreksi"))]
    j = say(sid, "Ralat: klien aktif saya sebenarnya 1").json()
    check("koreksi pasca-finalize menandai checkpoint v1 stale",
          j.get("checkpoint", {}).get("status") == "stale")
    ra = client.post("/session/" + sid + "/reassess")
    check("reassess 200", ra.status_code == 200, ra.text[:200])
    cps2 = client.get("/session/" + sid + "/checkpoints").json()["checkpoints"]
    check("v2 dibuat, v1 tidak diduplikasi", len(cps2) == 2 and cps2[1]["version"] == 2, len(cps2))
    cps_full2 = store.get(sid).checkpoints
    check("v1 tidak ditulis ulang (isi + binding utuh)",
          json.dumps(cps_full2[0]["diagnosis"], sort_keys=True, default=str) == v1_dump
          and json.dumps(cps_full2[0]["binding"], sort_keys=True, default=str) == v1_binding)
    check("v2 menautkan perubahan ke v1", cps2[1]["supersedes"] == cps2[0]["checkpoint_id"])
    check("v2 memakai evidence terbaru (bukan interpretasi historis)",
          sorted(cps2[1]["binding"]["source_evidence_refs"])
          == sorted(e.id for e in current_evidence(store.get(sid).evidence)))


TESTS = [
    test_dcp01_canonical_source_fidelity,
    test_dcp01b_revenue_state_transcript_fidelity,
    test_dcp01c_mixed_sentence_current_fact_survives,
    test_dcp02_hypothesis_revision,
    test_dcp03_provisional_deep_consistency,
    test_dcp04_non_revenue_goal,
    test_dcp05_low_evidence_honesty,
    test_dcp06_reassess_historical_integrity,
]


def main():
    for t in TESTS:
        try:
            t()
        except Exception:
            import traceback
            traceback.print_exc()
            globals()["_FAIL"] += 1
    print("")
    print("DCP RESULT: " + str(_PASS) + " passed, " + str(_FAIL) + " failed")
    return 0 if _FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
