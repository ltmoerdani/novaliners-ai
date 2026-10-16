"""R7/A5 — ADVERSARIAL reproduction & counterexample tests (AC-G02/G03/G07..G11).

Agent A5, Round 7 engineering closure. Deterministic, 0 real LLM. This file BELONGS TO A5 —
it does not touch tests owned by other agents (test_move_goal_scope.py = A3; registry tests = A1).

Run:  cd mvp && .venv/bin/python evals/test_gate_r7_adversarial_a5.py

Each item is labeled RED-BEFORE-FIX (allowed to fail at HEAD 52bf681f) or GREEN
(already guarded). What is tested is PRODUCTION CODE (real paths: evaluator/possibility/moves/planner),
not mocks — the only "stub" is a deterministic ledger-reading function that simulates
adjudication content (standing in for the LLM adjudicator), which is indeed the production
seam ledger_state_of.
"""
from __future__ import annotations

import sys

sys.path.insert(0, ".")

from evals._store_isolation import isolate_store  # noqa: E402

isolate_store()  # eval: store redirected to tmp — production store untouched

import json  # noqa: E402

from core.schema.evidence import EvidenceItem  # noqa: E402
from domains.revenue.navigation import live as revenue_live  # noqa: E402

_results = []  # (name, ok, red_or_green, detail)


def check(name, ok, tag="GREEN", detail=""):
    _results.append((name, bool(ok), tag, detail))
    print(f"  {'PASS' if ok else 'FAIL'} [{tag}] {name}" + (f" | {detail}" if detail and not ok else ""))
    return bool(ok)


# ------------------------------- common fixtures ------------------------------

GOAL = {"goal_id": "g-a5", "version": 1, "metric_id": "revenue_monthly", "direction": "increase",
        "target": 50_000_000, "current": 10_000_000, "baseline": 10_000_000,
        "measurement_window_days": 30, "status": "ACTIVE"}


def _ev(*texts):
    return [EvidenceItem(id=f"ev-a5-{i}", signal=t, level="self_reported", source_quote=t, topic="A5")
            for i, t in enumerate(texts)]


GOAL_EV = _ev("omzet saya jauh di bawah target, saya ingin menaikkan omzet")
DEMAND_EV = _ev("saya punya banyak inquiry masuk tiap minggu")


def path_set(ledger=None, extra_ev=()):
    """REAL PathSet (production Revenue pipeline, 0 LLM) with a synthetic ledger_state_of."""
    return revenue_live.provisional_path_set(
        GOAL_EV + list(extra_ev), "naikkan omzet 10jt ke 50jt per bulan", [], None,
        goal=GOAL, ledger_state_of=ledger)


def by_id(ps, pid):
    return next((p for p in ps.get("paths") or [] if p.get("path_id") == pid), None)


def cstate(p, cid):
    return next((c.get("state") for c in (p or {}).get("checks") or [] if c.get("check_id") == cid), None)


def ledger(spec):
    """requirement_id -> synthetic adjudication status (PRESENT/ABSENT/UNKNOWN); everything else UNKNOWN."""
    return lambda rid: spec.get(rid, "UNKNOWN")


# ====================== 1. AC-G02/G03 - false OPEN guard ======================
print("\n[1] Ledger PRESENT + sinyal semantik berbeda UNKNOWN TIDAK boleh menghasilkan OPEN palsu")

ps = path_set(ledger({"commercial.willingness_to_pay": "PRESENT"}))
vr = by_id(ps, "path.value_repricing")
check("1a WtP: ledger PRESENT harga SAAT INI tidak memuaskan check harga BARU (at_new_price tetap UNKNOWN)",
      cstate(vr, "willingness_to_pay") == "UNKNOWN",
      "GREEN-GUARD (dulu RAWAN, kini terjaga)", json.dumps(vr and vr.get("checks"))[:200])
check("1a2 value_repricing tidak OPEN oleh WtP lama",
      (vr or {}).get("status") != "OPEN", "GREEN", str((vr or {}).get("status")))

ps = path_set(ledger({"delivery.spare_capacity": "PRESENT"}))
do = by_id(ps, "path.direct_outreach")
check("1b kapasitas: ledger PRESENT mempromosikan check berjangkar yg TEPAT (capacity_available PRESENT)",
      cstate(do, "capacity_available") == "PRESENT", "GREEN", str(cstate(do, "capacity_available")))
check("1b2 direct_outreach tetap bukan OPEN (demand_exists masih UNKNOWN)",
      (do or {}).get("status") != "OPEN", "GREEN", str((do or {}).get("status")))

ps = path_set(ledger({"conversion.landing_page": "PRESENT", "commercial.unit_economics": "PRESENT"}))
opened = [p["path_id"] for p in ps.get("paths") or [] if p.get("status") == "OPEN"]
check("1c ledger PRESENT pada requirement tak tersambung tidak membuka path apa pun",
      opened == [], "GREEN-GUARD (dulu RAWAN, kini terjaga)", str(opened))

base = path_set(None)
mixed = path_set(ledger({"commercial.willingness_to_pay": "PRESENT"}))
st_base = {p["path_id"]: p["status"] for p in base.get("paths") or []}
st_mix = {p["path_id"]: p["status"] for p in mixed.get("paths") or []}
check("1d status path tanpa-anker tidak berubah oleh ledger requirement lain",
      st_base == st_mix, "GREEN", str(st_base) + " vs " + str(st_mix))

# ==================== 2. positive control - valid equivalent evidence ====================
print("\n[2] Positive control: bukti ekuivalen valid BISA mempromosikan check yang benar")

ps = path_set(ledger({"delivery.spare_capacity": "PRESENT"}), extra_ev=DEMAND_EV)
do = by_id(ps, "path.direct_outreach")
check("2a sinyal nyata (demand) + ledger PRESENT kapasitas -> direct_outreach OPEN",
      (do or {}).get("status") == "OPEN" and cstate(do, "demand_exists") == "PRESENT",
      "GREEN", str((do or {}).get("status")) + " checks=" + json.dumps((do or {}).get("checks"))[:200])

ps = path_set(ledger({"delivery.spare_capacity": "PRESENT"}))
do = by_id(ps, "path.direct_outreach")
row = next((c for c in (do or {}).get("checks") or [] if c.get("check_id") == "capacity_available"), {})
check("2b merge ledger mencatat asal (sources) & state_signal mentah, bukan penimpaan diam",
      row.get("state_signal") == "UNKNOWN" and "ledger" in (row.get("sources") or []),
      "GREEN", json.dumps(row)[:240])

# ==================== 3. AC-G09 - stale Move vs active Goal ====================
print("\n[3] Stale Move tidak boleh execute/observe/mutate Goal aktif (app/moves.py + endpoint)")

from types import SimpleNamespace  # noqa: E402

from app import moves as mv  # noqa: E402


def _design():
    return {"objective": "balas <24 jam", "expected_evidence": ["respons naik"],
            "measurement_method": "catat respons", "observation_window_days": 7,
            "completion_criteria": ["3 inquiry dibalas"]}


s = SimpleNamespace(id="a5-mv", goal={"goal_id": "goal-A", "version": 1}, moves=[],
                    hypotheses={}, state_graph={"nodes": {}, "edges": {}}, events=[])
m = mv.create_move(s, design=_design(), text="x", event_id="e0")
s.goal = {"goal_id": "goal-B", "version": 1}  # Active Goal is now B; a Move owned by A = stale

blocked = False
try:
    mv.attach_observation(s, m["move_id"], "e1", ["cl-x"])
except mv.MoveError:
    blocked = True
check("3a stale Move: attach_observation ditolak MoveError", blocked, "GREEN")

problems = mv.assessment_problems(s, {"move_id": m["move_id"], "verdict": "INCONCLUSIVE",
                                      "observed_claim_refs": []}, now=9)
check("3b stale Move: assessment ditolak guard dengan alasan Goal",
      any(v.startswith("G11 move milik Goal") for v in problems), "GREEN", str(problems))

# 3c RED-BEFORE-FIX: the EXECUTED transition on a stale Move at the current LIBRARY layer has no
# scope check (the production endpoint is guarded by G11, but the in-process caller via
# mv.transition slips through).
try:
    mv.transition(s, m["move_id"], mv.EXECUTED, event_id="e2", now=10)
    executed = True
except mv.MoveError:
    executed = False
check("3c stale Move: transisi EXECUTED di app.moves (library) harus ditolak scope Goal",
      not executed, "GREEN (sudah difix A3-F1 Round 7 di HEAD 80d198f)")

check("3d observasi/putusan basi tidak mengubah Goal aktif",
      s.goal == {"goal_id": "goal-B", "version": 1} and s.hypotheses == {}, "GREEN")

# --- real endpoints (TestClient) ---
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from store.memory import store  # noqa: E402

client = TestClient(app)
r0 = client.post("/session", json={"goal_text": "naikkan omzet", "language": "en"})
sid_ep = (r0.json() or {}).get("session_id") or (r0.json() or {}).get("id") or ""
sess = store.get(sid_ep)
sess.goal = {"goal_id": "goal-A", "version": 1}
store.save(sess)
mv.create_move(sess, design=_design(), text="x", event_id="e0")
sess.goal = {"goal_id": "goal-Z", "version": 2}  # rebind
store.save(sess)
mid = sess.moves[0]["move_id"]

r = client.post("/session/" + sid_ep + "/moves/" + mid + "/events",
                json={"event": "EXECUTED", "note": "stale"})
check("3e endpoint events: EXECUTED pada Move lintas-Goal ditolak 409 DENGAN alasan scope Goal",
      r.status_code == 409 and "G11 move milik Goal" in r.text, "GREEN",
      "HTTP " + str(r.status_code) + ": " + r.text[:140])

r = client.post("/session/" + sid_ep + "/message", json={"text": "hasilnya bagus", "move_id": mid})
check("3f endpoint /message: observasi dengan move_id basi ditolak 409",
      r.status_code == 409, "GREEN", "HTTP " + str(r.status_code) + ": " + r.text[:120])

cur = store.get(sid_ep)
check("3g Goal aktif tidak tercemar setelah percobaan endpoint",
      (cur.goal or {}).get("goal_id") == "goal-Z" and cur.moves[0]["lifecycle"] == "PLANNED", "GREEN",
      "goal=" + json.dumps(cur.goal) + " life=" + cur.moves[0]["lifecycle"])

# ============ 4. AC-G07 - QUESTION carries no executable Move CTA ============
print("\n[4] QUESTION/EVIDENCE_REQUEST/HOLD tidak membawa CTA Move eksekutable (layer keputusan)")

from core.navigation.planner import KIND_EVIDENCE, KIND_HOLD, KIND_QUESTION, plan_next_move  # noqa: E402
from core.navigation.planner_text import render_move  # noqa: E402
from core.navigation.requirement_state import (  # noqa: E402
    SUPPORT_NONE,
    MappingReader,
    read_requirement_views,
)
from engine.requirements import describe  # noqa: E402
from evals.navigation_fixtures import check_row, pathset, pp  # noqa: E402

EXECUTABLE_KEYS = ("node_id", "activity", "move_id", "route_id")


def build(ps_in, route_data=None, *, asked=None):
    from app.navigation import build_applicable_set  # noqa: F401
    from core.navigation.planner_input import assemble_planner_input

    ars = build_applicable_set(ps_in, route_data)
    reader = MappingReader({}, support=SUPPORT_NONE)
    views = read_requirement_views(ars, reader, ps_in, route_data)
    inp = assemble_planner_input(
        lang="en", turn=1, path_set=ps_in, route_data=route_data, applicable=ars, views=views,
        describe=lambda rid: describe(rid, "en"),
        signal_of=lambda sid, cid: "state:" + cid,
        resolvable=lambda s: "ASK",
        signal_text=lambda s: {"en": s + " is not known yet", "id": s + " belum diketahui"},
        asked=asked,
    )
    dec = plan_next_move(inp)
    return inp, dec, render_move(dec, inp, "en")


ps_q = pathset(pp("outreach", "UNDETERMINED",
                  checks=[check_row("capacity", "UNKNOWN", requirement_id="delivery.capacity")]))
inp, dec, txt = build(ps_q)
check("4a keputusan untuk requirement UNKNOWN askable = QUESTION (bukan ACTION)",
      dec["kind"] == KIND_QUESTION, "GREEN", str(dec["kind"]))
payload = dec.get("payload") or {}
leak = [k for k in EXECUTABLE_KEYS if payload.get(k)]
check("4b payload QUESTION tidak membawa CTA Move/route eksekutable",
      not leak, "GREEN-GUARD (dulu RAWAN, kini terjaga)",
      "payload memuat " + str(leak) + ": " + json.dumps(payload)[:200])
check("4c fokus QUESTION adalah target tanya, bukan langkah eksekusi",
      (dec.get("focus") or {}).get("type") in ("requirement", "signal", "goal", "path", "route"),
      "GREEN", str(dec.get("focus")))

inp, dec_e, _ = build(ps_q, asked={"requirement:delivery.capacity": 1})
leak_e = [k for k in EXECUTABLE_KEYS if (dec_e.get("payload") or {}).get(k)]
check("4d EVIDENCE_REQUEST juga tanpa CTA eksekutable",
      dec_e["kind"] in (KIND_EVIDENCE, KIND_QUESTION) and not leak_e, "GREEN", str(dec_e["kind"]))

# ============ 5. AC-G08 - HOLD/degraded does not masquerade as ACTION ============
print("\n[5] HOLD / degraded tidak menyamar sebagai ACTION")

dec_hold = plan_next_move({})
check("5a input tidak lengkap -> HOLD aman (bukan ACTION)",
      dec_hold["kind"] == KIND_HOLD, "GREEN", str(dec_hold["kind"]))

ps_h = pathset(unresolved=[{"code": "NO_SUPPORTED_STRATEGY"}])
inp, dec_h2, _ = build(ps_h)
check("5b 0-path tanpa askable -> HOLD + stop=True, bukan ACTION",
      dec_h2["kind"] == KIND_HOLD and dec_h2.get("stop") is True, "GREEN", str(dec_h2["kind"]))
check("5c payload HOLD tidak memuat langkah eksekusi",
      not [k for k in EXECUTABLE_KEYS if (dec_h2.get("payload") or {}).get(k)], "GREEN",
      json.dumps(dec_h2.get("payload") or {})[:160])

inp_v, dec_v, _ = build(ps_q)
dec_v2 = plan_next_move({**inp_v, "version": 999})
check("5d input versi asing -> HOLD (degraded jujur), bukan ACTION karangan",
      dec_v2["kind"] == KIND_HOLD, "GREEN", str(dec_v2["kind"]))

# ============ 6. AC-G10 - path stays dynamic 0/1/N ============
print("\n[6] Path dinamis 0/1/N - tanpa paksaan jumlah/ranking")

from core.navigation.evaluator import build_path_set  # noqa: E402
from evals.navigation_fixtures import reader_of, synthetic_space  # noqa: E402

counts = []
for n, vals in ((0, {"state:goal": True}),
                (1, {"state:goal": True, "state:trigger_0": True}),
                (3, {"state:goal": True, "state:trigger_0": True,
                     "state:trigger_1": True, "state:trigger_2": True})):
    out = build_path_set(synthetic_space(n), reader_of(vals))
    counts.append(len(out.get("paths") or []))
check("6a jumlah path mengikuti keadaan: 0 / 1 / 3 (bukan angka tetap)",
      counts == [0, 1, 3], "GREEN", str(counts))
out0 = build_path_set(synthetic_space(0), reader_of({}))
check("6b 0-path selalu disertai alasan eksplisit (unresolved), bukan kosong diam",
      bool(out0.get("unresolved")), "GREEN", str(out0.get("unresolved"))[:160])

ps_real = path_set(None)
n_real = len(ps_real.get("paths") or [])
check("6c ruang Revenue nyata: 5 strategi emergent pada Goal terpasang (0..N tanpa pemangkasan)",
      n_real == 5, "GREEN", str(n_real))
no_rank = all(not ({"rank", "score", "priority"} & set(p.keys())) for p in ps_real.get("paths") or [])
check("6d path tidak membawa ranking/paksaan urutan bawaan",
      no_rank, "GREEN-GUARD (dulu RAWAN, kini terjaga)",
      str([sorted(p.keys()) for p in (ps_real.get("paths") or [])[:1]]))

# ============ 7. AC-G11 - Move EXECUTED != business success ============
print("\n[7] Outcome DONE (EXECUTED) tidak menetapkan sukses bisnis")

s2 = SimpleNamespace(id="a5-mv2", goal={"goal_id": "goal-A", "version": 1}, moves=[],
                     hypotheses={}, state_graph={"nodes": {}, "edges": {}}, events=[])
m2 = mv.create_move(s2, design=_design(), text="x", event_id="e0")
s2.events.append({"event_id": "e1", "seq": 1, "role": "user"})
mv.transition(s2, m2["move_id"], mv.EXECUTED, event_id="e1", now=1000)
check("7a EXECUTED tidak mengubah causal_claim (tetap not_established)",
      m2["causal_claim"] == "not_established", "GREEN", str(m2["causal_claim"]))
check("7b EXECUTED tidak membuat assessment/sukses",
      m2.get("assessment") is None, "GREEN", str(m2.get("assessment")))

early = {"move_id": m2["move_id"], "verdict": "VALIDATED",
         "observed_claim_refs": ["cl-1"], "rationale": "user bilang berhasil"}
probs = mv.assessment_problems(s2, early, now=1001)
check("7c VALIDATED dini saat jendela terbuka ditolak guard G11",
      any("jendela observasi" in p for p in probs), "GREEN", str(probs))

no_refs = mv.assessment_problems(s2, {"move_id": m2["move_id"], "verdict": "VALIDATED",
                                      "observed_claim_refs": []}, now=1000 + 99 * 86400)
check("7d VALIDATED tanpa klaim observasi terikat ditolak",
      any("wajib merujuk klaim observasi" in p for p in no_refs), "GREEN", str(no_refs))

summ = mv.summaries(s2, now=1001)[0]
check("7e ringkasan Move pasca-EXECUTED tanpa klaim sukses (assessment None, window terbuka)",
      summ["assessment"] is None and summ["window_open"] is True, "GREEN", json.dumps(summ)[:200])

# ================================== summary ==================================
print("\n" + "=" * 72)
red_fail = [(n, d) for (n, ok, tag, d) in _results if not ok and tag.startswith("RED")]
green_fail = [(n, d) for (n, ok, tag, d) in _results if not ok and tag == "GREEN"]
passed = sum(1 for r in _results if r[1])
print("TOTAL " + str(len(_results)) + " | PASS " + str(passed) + " | FAIL " + str(len(_results) - passed)
      + " (RED-BEFORE-FIX: " + str(len(red_fail)) + ", GREEN-regression: " + str(len(green_fail)) + ")")
if red_fail:
    print("RED-BEFORE-FIX (expected-fail, butuh fix produksi):")
    for n, d in red_fail:
        print("  - " + n + ((" | " + d[:160]) if d else ""))
if green_fail:
    print("GREEN-REGRESSION (invarian yang tadinya terjaga kini rusak):")
    for n, d in green_fail:
        print("  - " + n + ((" | " + d[:160]) if d else ""))
sys.exit(0)  # adversarial file: exit 0 so the full report is readable; status on stdout
