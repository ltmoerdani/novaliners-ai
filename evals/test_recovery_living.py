"""R6 — LIVING navigation: revisable checkpoints, snapshot binding, measurable Moves, Outcomes,
one reality across destinations.

EVIDENCE STATUS: DETERMINISTIC_PASS (mock/script; no network). Move design & outcome-verdict quality
by the real model = LIVE_NOT_RUN (R7). Via real HTTP (TestClient) with all stores redirected to a temp
 directory.

  A  a message AFTER finalize is processed (not an ack); old checkpoints marked stale; change classes
     not swapped
  B  reassess → a new checkpoint version; old checkpoints intact (unchanged, not deleted); binding
     does not leak
  C  knowledge version changes: detected in the new checkpoint, old checkpoints stay on their old basis
  D  HTTP idempotency + payload conflicts (422); keys stay stable
  E  Move: complete measurable design; PLANNED→EXECUTED is not success; observation only after
     EXECUTED; verdicts guarded by G11 (observation window, claims born before execution), causality
     never asserted; related hypotheses updated
  F  one reality: the same state_version/checkpoint/goal in STATE, MAPS(routes), MOVES, JOURNEY(readiness), TALK
  G  Candidate/Path/Route: the reasoning layer does not change the path set; 0..N paths & lifecycle stay
"""
from __future__ import annotations

import atexit
import json
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

_TMP = Path(tempfile.mkdtemp(prefix="nvl-r6-"))
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

import app.main as app_main  # noqa: E402
from core.reasoning.contract import NextMoveProposal  # noqa: E402
from core.reasoning.hypotheses import hypothesis_id  # noqa: E402
from core.semantic.contract import SemanticObservation  # noqa: E402
from providers.mock import MockProvider  # noqa: E402
from store.memory import store  # noqa: E402

_PASS = _FAIL = 0
_created: list[str] = []


def check(name, cond, detail=""):
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"  OK  {name}")
    else:
        _FAIL += 1
        print(f"  GAGAL  {name}{' — ' + str(detail) if detail else ''}")


class Hybrid(MockProvider):
    """Mock + optional script: sequential semantic observations (`sem`) and reasoning (`nm(snapshot, n)`)."""

    def __init__(self):
        super().__init__()
        self.sem: list = []
        self.nm = None
        self.nm_calls = 0

    def structured_call(self, schema, system, user, retries=2):
        if schema is SemanticObservation and self.sem:
            return self.sem.pop(0)
        if schema is NextMoveProposal and self.nm is not None:
            from core.reasoning.reasoner import parse_snapshot_prompt
            self.nm_calls += 1
            out = self.nm(parse_snapshot_prompt(user), self.nm_calls)
            return NextMoveProposal.model_validate(out)
        return super().structured_call(schema, system, user, retries)


LLM = Hybrid()
app_main.get_llm = lambda: LLM
assert app_main.get_llm().name == "mock"
client = TestClient(app_main.app)
atexit.register(lambda: [(store.PERSIST_DIR / f"{sid}.json").unlink(missing_ok=True) for sid in _created])


def obs(*claims, relations=()):
    return SemanticObservation(contract_version="so.v1", language="id", claims=list(claims),
                               relations=list(relations), uncertainties=[])


def cl(ref, role, subject, predicate, quote, **kw):
    import test_recovery_semantic as R
    return R.cl(ref, role, subject, predicate, quote, **kw)


def qty(**kw):
    import test_recovery_semantic as R
    return R.qty(**kw)


def new_session(user, goal="bisnis saya", lang="id"):
    r = client.post("/session", json={"goal_text": goal, "language": lang, **({"user_id": user} if user else {})})
    assert r.status_code == 200, r.text
    sid = r.json()["session_id"]
    _created.append(sid)
    return sid


def say(sid, text, **kw):
    r = client.post(f"/session/{sid}/message", json={"text": text, **kw})
    return r


# ── A/B/C: checkpoint hidup ───────────────────────────────────────────────────

def test_living_checkpoints():
    print("A/B/C — checkpoint hidup: pesan pasca-finalize, kelas perubahan, reassess, versi pengetahuan")
    LLM.nm = None
    LLM.sem = [
        obs(cl("c1", "claim", "omzet", "is", "bisnis saya omzetnya 18 juta",
               quantity=qty(value_kind="exact", value=18, unit="juta", period="monthly"))),   # Create Map
        obs(cl("c1", "claim", "klien", "has", "klien aktif saya 3 orang")),
    ]
    sid = new_session("u-r6-a")
    r1 = say(sid, "klien aktif saya 3 orang")
    check("pesan sebelum finalize normal", r1.status_code == 200 and r1.json()["kind"] == "probe")
    fin = client.post(f"/session/{sid}/finalize")
    check("finalize OK (mock) dan menghasilkan checkpoint v1 current",
          fin.status_code == 200 and client.get(f"/session/{sid}/checkpoints").json()["latest"]["status"] == "current")
    cps0 = client.get(f"/session/{sid}/checkpoints").json()["checkpoints"]
    v1_ref = cps0[0]["diagnosis_ref"]
    check("checkpoint v1 membawa binding (state/goal/knowledge/model/prompt/kontrak)",
          all(k in cps0[0]["binding"] for k in ("state_version", "goal_id", "knowledge", "model", "prompts",
                                                  "contracts", "source_evidence_refs", "binding_id", "ts"))
          and cps0[0]["binding"]["model"]["provider"] == "mock"
          and cps0[0]["binding"]["contracts"] == {"semantic": "so.v1", "decision": "nm.v2", "candidate": "ec.v1"})

    # a new message after finalize
    LLM.sem = [obs(cl("c1", "claim", "tim", "has", "saya punya satu asisten paruh waktu"))]
    r = say(sid, "saya punya satu asisten paruh waktu")
    j = r.json()
    check("pasca-finalize: BUKAN ack — diproses (probe + langkah + evidence)",
          r.status_code == 200 and j["kind"] == "probe" and j["next_move"] and j["evidence_delta"])
    check("kelas perubahan = new_information; checkpoint v1 → stale dengan alasan",
          j["change_class"] == "new_information" and j["checkpoint"]["status"] == "stale"
          and j["checkpoint"]["stale_reasons"][0]["change"] == "new_information", str(j["checkpoint"]))
    first_claim = sorted(store.get(sid).state_graph["nodes"])[0]
    LLM.sem = [obs(cl("c1", "claim", "omzet", "is", "ralat omzet saya sebenarnya 12 juta",
                      quantity=qty(value_kind="exact", value=12, unit="juta", period="monthly"),
                      supersedes=first_claim, revision_kind="correction", revision_reason="koreksi"))]
    j = say(sid, "ralat omzet saya sebenarnya 12 juta").json()
    check("koreksi pasca-finalize: kelas = correction (tidak sama dengan new_information)",
          j["change_class"] == "correction" and store.get(sid).state_graph["nodes"][first_claim]["status"] == "superseded")
    LLM.sem = [obs()]
    j = say(sid, "oke terima kasih").json()
    check("pesan tanpa makna baru: no_material_change dan alasan basi TIDAK bertambah",
          j["change_class"] == "no_material_change" and len(j["checkpoint"]["stale_reasons"]) == 2)
    LLM.sem = [obs(cl("c1", "goal", "omzet", "target", "target omzet saya 40 juta per bulan", tense="future",
                      quantity=qty(value_kind="exact", value=40, unit="juta", period="monthly")))]
    j = say(sid, "target omzet saya 40 juta per bulan").json()
    check("perubahan tujuan: kelas = goal_change; Goal sesi ikut berubah (versi naik)",
          j["change_class"] == "goal_change" and store.get(sid).goal["target"] == 40.0
          and store.get(sid).goal["version"] >= 2, str(j["change_class"]))

    # B reassess
    st_before = json.dumps(store.get(sid).checkpoints[0], sort_keys=True, default=str)
    ra = client.post(f"/session/{sid}/reassess")
    cps = client.get(f"/session/{sid}/checkpoints").json()["checkpoints"]
    check("reassess → checkpoint v2 current; v1 superseded", ra.status_code == 200 and len(cps) == 2
          and cps[1]["status"] == "current" and cps[0]["status"] == "superseded" and cps[1]["supersedes"] == cps[0]["checkpoint_id"])
    c0 = json.loads(st_before)
    now0 = store.get(sid).checkpoints[0]
    check("checkpoint v1 TIDAK diubah isinya (diagnosis + binding utuh; hanya status)",
          now0["diagnosis"] == c0["diagnosis"] and now0["binding"] == c0["binding"] and now0["diagnosis_ref"] == v1_ref)
    check("v2 binding memuat klaim aktif baru (state_version berbeda dari v1)",
          cps[1]["binding"]["state_version"] != cps[0]["binding"]["state_version"])

    # C knowledge version
    import app.binding as bnd
    real = bnd.knowledge_versions
    bnd.knowledge_versions = lambda: {**real(), "kb": "kb-versi-baru-xyz"}
    try:
        client.post(f"/session/{sid}/reassess")
    finally:
        bnd.knowledge_versions = real
    cps = client.get(f"/session/{sid}/checkpoints").json()["checkpoints"]
    check("versi pengetahuan berubah terdeteksi di checkpoint v3", len(cps) == 3
          and cps[2]["knowledge_changed_since_prev"] is True and cps[2]["binding"]["knowledge"]["kb"] == "kb-versi-baru-xyz")
    check("checkpoint v1/v2 tetap pada basis pengetahuan LAMA (tidak diam-diam memakai aturan baru)",
          cps[0]["binding"]["knowledge"]["kb"] != "kb-versi-baru-xyz" and cps[1]["binding"]["knowledge"]["kb"] != "kb-versi-baru-xyz")

    # D idempotensi HTTP
    LLM.sem = [obs(cl("c1", "claim", "toko", "has", "saya punya toko online kecil"))]
    k1 = say(sid, "saya punya toko online kecil", idempotency_key="idem-1")
    n_events = len(store.get(sid).events)
    k2 = say(sid, "saya punya toko online kecil", idempotency_key="idem-1")
    check("kunci sama + teks sama: hasil identik, tanpa event/LLM baru",
          k1.status_code == k2.status_code == 200 and k1.json()["next_move"] == k2.json()["next_move"]
          and len(store.get(sid).events) == n_events)
    k3 = say(sid, "teks lain sama sekali", idempotency_key="idem-1")
    check("kunci sama + teks berbeda → 422 tanpa efek", k3.status_code == 422 and len(store.get(sid).events) == n_events)
    return sid


# ── E/F/G: Move, Outcome, satu realitas ───────────────────────────────────────

GOAL = "Saya konsultan marketing, mau Rp20 juta per bulan dalam 90 hari."
STEPS = ["Pendapatan saya sekarang Rp0 per bulan.", "Saya kerja sekitar 30 jam per minggu untuk delivery klien.",
         "Ada 3 orang yang bertanya soal jasa saya bulan ini (inquiry masuk).",
         "ICP saya berisi jenis usaha UKM, level direktur, dan peran pembeli owner."]


def test_moves_and_outcome():
    print("E/F/G — Move terukur, Outcome, hipotesis, satu realitas, path set utuh")
    LLM.sem = []

    def nm(snap, n):
        base = {"contract_version": "nm.v2", "state_snapshot_ref": snap["snapshot_id"],
                "supporting_claim_refs": snap["claim_ids"][-1:], "move_text": "Hubungi tiga calon klien yang sudah bertanya.",
                "information_value_rationale": "menguji apakah tindak lanjut cepat menghasilkan respons",
                "expected_decision_change": "mengubah prioritas dari akuisisi ke tindak lanjut"}
        if LLM.script_state.get("assess"):
            return {**base, "proposed_move_kind": "HOLD", "abstain": True,
                    "conditions_for_abstention": "menunggu bukti tambahan",
                    "outcome_assessment": LLM.script_state["assess"]}
        if snap["moves"]:
            return {**base, "proposed_move_kind": "HOLD", "abstain": True, "conditions_for_abstention": "menunggu hasil"}
        if "action_allowed: true" in LLM.script_state.get("last_user", ""):
            pass
        unc = [u for u in snap["uncertainties"] if u["asked"] < 2]
        if unc:
            return {**base, "proposed_move_kind": "QUESTION", "focus_type": "uncertainty",
                    "proposed_focus": unc[0]["id"], "move_text": "Bisa jelaskan lebih jauh?"}
        return {**base, "proposed_move_kind": "ACTION", "focus_type": "uncertainty",
                "competing_hypotheses": [{"statement": "tindak lanjut lambat membuat calon klien hilang",
                                          "supports": snap["claim_ids"][-1:], "missing_evidence": ["waktu balasan"]}],
                "move_design": {
                    "objective": "Uji apakah balasan <24 jam pada 3 inquiry menghasilkan percakapan lanjutan",
                    "preconditions": ["ada 3 inquiry yang belum dibalas"], "constraints": ["maksimal 5 jam per minggu"],
                    "expected_evidence": ["jumlah balasan dari calon klien", "jumlah percakapan lanjutan"],
                    "measurement_method": "catat per inquiry: waktu balas, ada/tidak respons, ada/tidak jadwal call",
                    "observation_window_days": 7, "completion_criteria": ["ketiga inquiry sudah dibalas dan dicatat"],
                    "actions": [{"title": "Tindaklanjuti 3 inquiry & catat waktu balas (target <24 jam)"}],  # Phase 7: action list wajib
                    "linked_path_id": (snap["paths"][0]["path_id"] if snap["paths"] else ""),
                    "linked_hypothesis_id": hypothesis_id("tindak lanjut lambat membuat calon klien hilang")}}

    LLM.script_state = {}
    LLM.nm = nm
    sid = new_session("u-r6-move", goal=GOAL, lang="en")
    for t in STEPS:
        LLM.script_state["last_user"] = t
        r = say(sid, t)
        assert r.status_code == 200, r.text
    mvs = client.get(f"/session/{sid}/moves").json()
    check("langkah ACTION diwujudkan sebagai Move PLANNED dengan desain terukur lengkap", len(mvs["moves"]) == 1, str(r.json()["next_move"])[:200])
    mv = mvs["moves"][0]
    check("Move: tujuan, Goal, path, bukti diharapkan, cara ukur, jendela, kriteria selesai, rujukan outcome",
          mv["lifecycle"] == "PLANNED" and mv["objective"] and mv["linked_goal_id"] == store.get(sid).goal["goal_id"]
          and mv["linked_path_id"].startswith("path.") and mv["expected_evidence"] and mv["measurement_method"]
          and mv["observation_window_days"] == 7 and mv["completion_criteria"] and mv["outcome_reference"] is None
          and mv["causal_claim"] == "not_established", str({k: mv[k] for k in ("lifecycle", "linked_path_id")}))
    check("hipotesis terkait lahir dari klaim aktif (jejak)", any(h["supports"] for h in mvs["hypotheses"]))
    mid = mv["move_id"]

    r = say(sid, "Klien pertama membalas dan mau jadwalkan call.", move_id=mid)
    check("observasi SEBELUM eksekusi ditolak (409)", r.status_code == 409, r.text[:120])
    bad = client.post(f"/session/{sid}/moves/{mid}/events", json={"event": "VALIDATED"})
    check("user tidak dapat melaporkan VALIDATED (hanya STARTED/EXECUTED/ABANDONED)", bad.status_code == 422)
    ledger_before = (ledger._LEDGER_ROOT / "u-r6-move" / "adjudication_ledger.jsonl")
    n_led = len(ledger_before.read_text().splitlines()) if ledger_before.exists() else 0
    ev = client.post(f"/session/{sid}/moves/{mid}/events", json={"event": "EXECUTED", "note": "sudah dibalas semua"})
    check("EXECUTED tercatat", ev.status_code == 200 and ev.json()["move"]["lifecycle"] == "EXECUTED")
    # S2-E: a Move event = durable fact (event_id + committed status), not a best-effort ack
    _evid = ev.json().get("event_id")
    _hist_exec = [h for h in ev.json()["move"]["history"] if h["state"] == "EXECUTED"]
    _durable = [e for e in store.get(sid).events
                if e.get("kind") == "move_event" and e.get("correlation_id") == mid]
    check("EXECUTED punya atribusi event tahan-lama + committed (S2-E)",
          bool(_evid) and _hist_exec and _hist_exec[-1]["event_id"] == _evid
          and any(e.get("event_id") == _evid and e.get("status") == "committed" for e in _durable),
          (_evid, _hist_exec[-1:] if _hist_exec else [], len(_durable)))
    nm_after = (ledger_before.read_text().splitlines() if ledger_before.exists() else [])
    check("eksekusi ≠ keberhasilan: assessment kosong, ledger requirement tidak berubah",
          client.get(f"/session/{sid}/moves").json()["moves"][0]["assessment"] is None and len(nm_after) == n_led)
    again = client.post(f"/session/{sid}/moves/{mid}/events", json={"event": "STARTED"})
    check("transisi mundur (EXECUTED→STARTED) ditolak 409", again.status_code == 409)

    # outcome observation (event outcome_observation) — through the same semantic pipeline
    LLM.sem = [obs(cl("c1", "claim", "klien pertama", "replied", "Klien pertama membalas dan mau jadwalkan call",
                      tense="past"))]
    r = say(sid, "Klien pertama membalas dan mau jadwalkan call.", move_id=mid)
    j = r.json()
    mv = client.get(f"/session/{sid}/moves").json()["moves"][0]
    check("observasi → Move OBSERVED + klaim terikat; kelas perubahan = outcome_observation",
          r.status_code == 200 and mv["lifecycle"] == "OBSERVED" and mv["observation_claim_refs"]
          and j["change_class"] == "outcome_observation" and mv["outcome_reference"], str(mv["lifecycle"]))
    ue = [e for e in store.get(sid).events if e["role"] == "user"][-1]
    check("event observasi bertipe outcome_observation dan terkorelasi ke Move",
          ue["kind"] == "outcome_observation" and ue["correlation_id"] == mid)

    refs = mv["observation_claim_refs"]
    # a VALIDATED verdict while the window is still open → guard-rejected → degraded (Move stays OBSERVED)
    LLM.script_state["assess"] = {"move_id": mid, "verdict": "VALIDATED", "observed_claim_refs": refs,
                                 "rationale": "klien membalas"}
    LLM.sem = [obs()]
    say(sid, "ada kabar lagi?")
    ad = store.get(sid).planner_log[-1]["adaptive"]
    check("VALIDATED selagi jendela observasi terbuka ditolak guard (G11) → degraded; Move tetap OBSERVED",
          ad["status"] == "DEGRADED" and store.get(sid).moves[0]["lifecycle"] == "OBSERVED"
          and any("jendela" in v for v in ad["attempts"][0]["guard"]["violations"]), str(ad["attempts"][:1]))
    # claims born before execution must not be used
    early = sorted(store.get(sid).state_graph["nodes"])[0]
    LLM.script_state["assess"] = {"move_id": mid, "verdict": "INCONCLUSIVE", "observed_claim_refs": [early],
                                 "rationale": "klaim lama"}
    LLM.sem = [obs()]
    say(sid, "hmm")
    ad = store.get(sid).planner_log[-1]["adaptive"]
    check("klaim yang bukan observasi Move ini / lahir sebelum eksekusi ditolak (G11)",
          ad["status"] == "DEGRADED" and any("G11" in v for v in ad["attempts"][0]["guard"]["violations"]))

    # a temporary INCONCLUSIVE verdict is valid while the window is open
    LLM.script_state["assess"] = {"move_id": mid, "verdict": "INCONCLUSIVE", "observed_claim_refs": refs,
                                  "rationale": "baru satu respons"}
    LLM.sem = [obs()]
    say(sid, "belum ada kabar lain")
    check("INCONCLUSIVE sementara sah; Move INCONCLUSIVE (dapat diobservasi lagi)",
          store.get(sid).moves[0]["lifecycle"] == "INCONCLUSIVE")
    LLM.sem = [obs(cl("c1", "claim", "klien kedua", "replied", "Klien kedua juga membalas dan minta penawaran", tense="past"))]
    LLM.script_state["assess"] = None
    say(sid, "Klien kedua juga membalas dan minta penawaran.", move_id=mid)
    check("observasi tambahan setelah INCONCLUSIVE → OBSERVED lagi", store.get(sid).moves[0]["lifecycle"] == "OBSERVED"
          and len(store.get(sid).moves[0]["observation_claim_refs"]) == 2)

    # window expired (simulated: executed 10 days ago) → VALIDATED is valid
    store.get(sid).moves[0]["executed_ts"] -= 10 * 86400
    refs = store.get(sid).moves[0]["observation_claim_refs"]
    LLM.script_state["assess"] = {"move_id": mid, "verdict": "VALIDATED", "observed_claim_refs": refs,
                                  "rationale": "dua dari tiga inquiry merespons dalam jendela", "remaining_uncertainties": ["sebab"]}
    LLM.sem = [obs()]
    say(sid, "bagaimana hasilnya sejauh ini?")
    m = store.get(sid).moves[0]
    check("setelah jendela habis VALIDATED sah; causal_claim tetap not_established; putusan menyimpan sisa ketidakpastian",
          m["lifecycle"] == "VALIDATED" and m["assessment"]["causal_claim"] == "not_established"
          and m["assessment"]["remaining_uncertainties"] == ["sebab"], str(m["lifecycle"]))
    h = store.get(sid).hypotheses.get(m["linked_hypothesis_id"])
    check("putusan VALIDATED menambah klaim observasi ke hipotesis terkait (jejak outcome, bukan klaim kausal)",
          h is not None and set(refs) <= set(h["supports"]) and h["history"][-1]["change"] == "outcome_validated"
          and h["history"][-1]["move_id"] == mid, str(h and h["history"][-1:]))
    LLM.script_state["assess"] = None

    # F0 (int 07:57) — a VERTICAL chain in ONE test: Path→Move→EXECUTED→observation→verdict→reassess.
    # Previously reassess (A/B) and Move/outcome (E) were tested separately; the combination was never enforced.
    _mv_judged = json.loads(json.dumps(store.get(sid).moves[0], default=str))
    _n_moves, _n_cp = len(store.get(sid).moves), len(store.get(sid).checkpoints)
    client.post(f"/session/{sid}/reassess")
    client.post(f"/session/{sid}/reassess")
    _cps = client.get(f"/session/{sid}/checkpoints").json()["checkpoints"]
    check("VERTIKAL Move→putusan→reassess: checkpoint baru current, lama superseded; putusan Move utuh; tanpa Move ganda",
          len(_cps) == _n_cp + 2 and _cps[-1]["status"] == "current" and _cps[-2]["status"] == "superseded"
          and store.get(sid).moves[0]["assessment"] == _mv_judged["assessment"]
          and store.get(sid).moves[0]["lifecycle"] == _mv_judged["lifecycle"]
          and len(store.get(sid).moves) == _n_moves,
          f"cps={len(_cps)} start={_n_cp}")

    # F satu realitas
    s = store.get(sid)
    st = client.get(f"/session/{sid}/state").json()["reality"]
    nv = client.get(f"/session/{sid}/navigation").json()["reality"]
    mo = client.get(f"/session/{sid}/moves").json()["reality"]
    rt = client.post(f"/session/{sid}/routes").json()["reality"]
    check("STATE/NAVIGATION/MOVES/MAPS(routes) membawa realitas yang SAMA (state_version, goal, checkpoint)",
          st == nv == mo == rt, f"{st} | {nv} | {mo} | {rt}")
    check("reality memuat jumlah Move yang konsisten dengan data", st["moves"] == len(s.moves) == 1)
    LLM.sem = [obs(cl("c1", "claim", "tim", "has", "saya merekrut satu asisten"))]
    talk = say(sid, "saya merekrut satu asisten").json()
    st2 = client.get(f"/session/{sid}/state").json()["reality"]
    check("TALK mengubah state → semua destinasi bergeser bersama (state_version baru, konsisten)",
          st2["state_version"] != st["state_version"] and talk["change_class"] == "new_information"
          and client.get(f"/session/{sid}/navigation").json()["reality"] == st2)

    # G the path set is untouched by the reasoning layer
    from app.navigation import navigate_session
    nav = navigate_session(store.get(sid))
    ps = nav.path_set
    check("path set tetap 0..N dari evaluator (lapisan penalaran tak menambah/mengurangi/menyusun ulang path)",
          bool(ps.get("paths")) and all(p["path_id"].startswith("path.") for p in ps["paths"])
          and len({p["path_id"] for p in ps["paths"]}) == len(ps["paths"]))
    check("candidate_move (planner deterministik) tetap tersedia untuk audit/replay",
          talk["candidate_move"]["policy"] == "m4.v1" and talk["next_move"]["policy"] == "nm.v2")


def test_unsupported_outcome():
    print("G-24 — outcome yang menyangkal mekanisme memperbarui hipotesis, bukan mempertahankan diagnosis lama")
    from types import SimpleNamespace

    from app import moves as mv
    from core.reasoning.hypotheses import hypothesis_id, standing_of
    s = SimpleNamespace(id="un-01", goal={"goal_id": "g1", "version": 1}, moves=[], events=[
        {"event_id": "ce-un-01-0000", "seq": 0, "role": "user"}, {"event_id": "ce-un-01-0002", "seq": 2, "role": "user"},
        {"event_id": "ce-un-01-0004", "seq": 4, "role": "user"}], hypotheses={})
    nodes = {f"cl-e000{i}-001": {"id": f"cl-e000{i}-001", "status": "active", "provenance": {"event_id": e, "session": "un-01"}}
             for i, e in ((0, "ce-un-01-0000"), (2, "ce-un-01-0002"), (4, "ce-un-01-0004"))}
    s.state_graph = {"nodes": nodes, "edges": {}}
    hid = hypothesis_id("follow-up lambat adalah penyebab prospek hilang")
    s.hypotheses[hid] = {"id": hid, "statement": "follow-up lambat adalah penyebab prospek hilang", "supports": ["cl-e0000-001"],
                         "contradicts": [], "missing_evidence": [], "knowledge_refs": [], "status": "active", "history": [],
                         "standing": "tentative"}
    m = mv.create_move(s, design={"objective": "balas <24 jam", "expected_evidence": ["respons naik"],
                                  "measurement_method": "catat respons", "observation_window_days": 7,
                                  "completion_criteria": ["3 inquiry dibalas"], "linked_hypothesis_id": hid},
                       text="Balas cepat tiga inquiry.", event_id="ce-un-01-0000", now=1000)
    mv.transition(s, m["move_id"], mv.EXECUTED, event_id="ce-un-01-0002", now=1000)
    mv.attach_observation(s, m["move_id"], "ce-un-01-0004", ["cl-e0004-001"], now=1000)
    a = {"move_id": m["move_id"], "verdict": "UNSUPPORTED", "observed_claim_refs": ["cl-e0004-001"],
         "rationale": "dibalas cepat tetapi tidak ada respons"}
    check("sebelum jendela habis, UNSUPPORTED ditolak (jendela masih terbuka)",
          any("jendela" in x for x in mv.assessment_problems(s, a, now=1000 + 86400)))
    check("setelah jendela habis, putusan UNSUPPORTED sah", mv.assessment_problems(s, a, now=1000 + 8 * 86400) == [])
    mv.apply_assessment(s, a, event_id="ce-un-01-0004", now=1000 + 8 * 86400)
    h = s.hypotheses[hid]
    check("hipotesis menerima bukti penyangkal bersumber klaim observasi", h["contradicts"] == ["cl-e0004-001"]
          and h["history"][-1]["change"] == "outcome_unsupported" and h["history"][-1]["move_id"] == m["move_id"])
    check("standing hipotesis → contested (dukungan lama tidak dipertahankan membabi buta)",
          standing_of(h, s.state_graph) == "contested" and h["standing"] == "contested")
    check("Move berakhir UNSUPPORTED tanpa klaim kausal", s.moves[0]["lifecycle"] == "UNSUPPORTED"
          and s.moves[0]["assessment"]["causal_claim"] == "not_established")


def main() -> int:
    test_living_checkpoints()
    test_moves_and_outcome()
    test_unsupported_outcome()
    print()
    print(f"HASIL R6: {_PASS}/{_PASS + _FAIL} PASS (DETERMINISTIC_PASS; LIVE_NOT_RUN)" + (" ✅" if _FAIL == 0 else " ❌"))
    return 0 if _FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
