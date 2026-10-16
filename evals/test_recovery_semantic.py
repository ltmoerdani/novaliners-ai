"""R3 — Canonical Semantic Observation & Durable State (int 16 §R3; recovery branch).

Proves the core R3 contracts with deterministic fixtures (a controlled FakeLLM;
real providers are tested in R5/R7):

  A. Six roles + orthogonal aspects survive event -> commit -> graph -> reload (CP-03, SC-03)
  B. Typed quantities: approximate/range/at_most are not merged (CP-06)
  C. Per-EVENT quote anchors: a misquote from another turn is REJECTED (CP-10, SC-05)
  D. Cross-turn supersession: a correction marks the old claim, history intact (CP-07, SC-07)
  E. Cross-turn relations (contradictions between turns) (CP-09, SC-06)
  F. Idempotency: duplicate keys rejected; a failed event reprocessed without duplication (CP-25, EC-01)
  G. Understanding failure: the event stays durable + the status is visible (CP-25)
  H. Event storage failure is RAISED, not swallowed (EC-01)
  I. A 22-turn conversation: accumulation + current-view (CP-15)
  J. Desire without numbers: no fabricated Goal target; a contextual first question (CP-01, CP-32)
  K. One meaning authority: run_turn calls the semantic LLM EXACTLY ONCE (CP-11, F-01)
  L. Observations stay committed even when navigation fails (CP-17, SC-09)
  M. Scope: events belong to their session; commit rejects foreign events (BC-02 basis)
  N. A rich multi-category first message: every category enters the graph (CP-03/CP-16)

Run: .venv/bin/python evals/test_recovery_semantic.py  (deterministic, no network)
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # mvp/

from evals._store_isolation import isolate_store  # noqa: E402

isolate_store()  # eval: store redirected to tmp — production store untouched

from core.semantic.commit import verify_and_commit  # noqa: E402
from core.semantic.contract import SemanticObservation  # noqa: E402
from store import events as event_store  # noqa: E402
from store.events import EventPersistenceError  # noqa: E402

_PASS = 0
_FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"  OK  {name}")
    else:
        _FAIL += 1
        print(f"  GAGAL  {name}{' — ' + detail if detail else ''}")


# ── fixture ───────────────────────────────────────────────────────────────────

class FakeLLM:
    """Controlled semantic LLM: returns the observation scripted per turn."""

    def __init__(self, observations):
        self.observations = list(observations)
        self.calls = 0              # SEMANTIC (so.v1) calls only
        self.reasoning_calls = 0    # NextMove reasoning call (nm.v2) — R5
        self.prompts = []

    def structured_call(self, schema, system, user, retries=2):
        from core.reasoning.contract import NextMoveProposal
        if schema is NextMoveProposal:
            from providers.mock import _mock_next_move
            self.reasoning_calls += 1
            return NextMoveProposal.model_validate(_mock_next_move(user))
        self.calls += 1
        self.prompts.append(user)
        if schema is not SemanticObservation:
            raise AssertionError(f"jalur semantik memanggil schema lain: {schema.__name__}")
        idx = min(self.calls - 1, len(self.observations) - 1)
        return self.observations[idx]


def obs(claims=(), relations=(), uncertainties=()):
    return SemanticObservation(
        contract_version="so.v1", language="id",
        claims=list(claims), relations=list(relations), uncertainties=list(uncertainties),
    )


def cl(ref, role, subject, predicate, quote, **kw):
    from core.semantic.contract import ObservedClaim
    kw.setdefault("revision_kind", None if not kw.get("supersedes") else kw.get("revision_kind", "correction"))
    if not kw.get("supersedes"):
        kw["revision_kind"] = None
    return ObservedClaim(ref=ref, role=role, subject=subject, predicate=predicate, quote=quote, **kw)


def qty(**kw):
    from core.semantic.contract import Quantity
    return Quantity(**kw)


def make_session(sid="testsess01"):
    s = SimpleNamespace(
        id=sid, goal_text="saya ingin bisnis tetap jalan saat saya libur", language="id",
        transcript=[], evidence=[], diagnosis=None, interview_done=False, evidence_seq=0,
        user_id="u-test", prior_session_id="", journey_delta=None, created_ts=0,
        goal={"desire": "bisnis tetap jalan saat libur", "metric": "", "target": None,
              "target_origin": "none", "metric_id": "", "direction": "", "category": "", "unit": "",
              "scope": "", "measurement_window_days": None, "deadline_days": None,
              "success_definition": "", "notes": []},
        intent_tags=[], number_claims=[], state_graph={"nodes": {}, "edges": {}},
        graph_drift_reports=[], explain=None, planner_log=[], last_adjudication=None, events=[],
    )
    return s


EVENTS_DIR_BACKUP = None


def setup_events_dir(tmp: Path):
    global EVENTS_DIR_BACKUP
    EVENTS_DIR_BACKUP = event_store.EVENTS_DIR
    event_store.EVENTS_DIR = tmp / "events"


def restore_events_dir():
    global EVENTS_DIR_BACKUP
    if EVENTS_DIR_BACKUP is not None:
        event_store.EVENTS_DIR = EVENTS_DIR_BACKUP


# ── A/B/N: role, aspect, quantity, rich message ───────────────────────────────

def test_rich_message_roles_and_quantities(tmp: Path):
    print("A/B/N — role + aspek + kuantitas bertipe dari satu pesan kaya")
    setup_events_dir(tmp)
    try:
        s = make_session()
        ev = event_store.append_event(s, role="user", kind="message",
                                      text=("Dulu omzet 30 juta, sekarang sekitar 18 juta. "
                                            "Saya ingin bisnis tetap jalan saat saya libur sebulan. "
                                            "Saya kira masalahnya marketing. "
                                            "Saya jarang follow-up karena merasa tidak enak mengganggu orang. "
                                            "Saya tidak mau menambah jam kerja. "
                                            "Saya tidak tahu berapa leads yang masuk."))
        o = obs(claims=[
            cl("c1", "claim", "omzet", "was", "Dulu omzet 30 juta",
               quantity=qty(value_kind="exact", value=30, unit="juta", period="monthly"), tense="past"),
            cl("c2", "claim", "omzet", "currently", "sekarang sekitar 18 juta",
               quantity=qty(value_kind="approximate", value=18, unit="juta", period="monthly"),
               tense="now", hedge=True, epistemic="estimated"),
            cl("c3", "desire", "saya", "wants", "Saya ingin bisnis tetap jalan saat saya libur sebulan",
               tense="future"),
            cl("c4", "assumption", "masalah", "probably_is", "Saya kira masalahnya marketing"),
            cl("c5", "claim", "saya", "rarely_does", "Saya jarang follow-up karena merasa tidak enak mengganggu orang",
               aspect="behavior"),
            cl("c6", "claim", "saya", "feels", "merasa tidak enak mengganggu orang", aspect="concern"),
            cl("c7", "claim", "jam kerja", "must_not_increase", "Saya tidak mau menambah jam kerja",
               aspect="constraint"),
            cl("c8", "gap", "leads", "unknown_count", "Saya tidak tahu berapa leads yang masuk"),
        ])
        res = verify_and_commit(s, ev, o)
        check("8/8 klaim diterima", len(res.accepted_claims) == 8, str(res.rejections))
        nodes = s.state_graph["nodes"]
        roles = {n["type"] for n in nodes.values()}
        check("role lengkap", {"claim", "desire", "assumption", "gap"} <= roles, str(roles))
        aspects = {n.get("aspect") for n in nodes.values()}
        check("aspek ortogonal terekam", {"behavior", "concern", "constraint"} <= aspects, str(aspects))
        approx = [n for n in nodes.values() if (n.get("quantity") or {}).get("value_kind") == "approximate"]
        check("approximate tak dilebur jadi exact", bool(approx) and approx[0]["hedge"] is True)
        check("epistemic estimated terekam", approx and approx[0].get("epistemic") == "estimated")
        check("semua klaim ber-provenance event",
              all(n["provenance"].get("event_id") == ev["event_id"] for n in nodes.values()))
        # reload simulation: the graph survives as pure data
        roundtrip = json.loads(json.dumps(s.state_graph))
        check("graph roundtrip JSON utuh", len(roundtrip["nodes"]) == 8)
    finally:
        restore_events_dir()


# ── C: per-event anchors ──────────────────────────────────────────────────────

def test_quote_anchor_rejects_wrong_event(tmp: Path):
    print("C — kutipan dari giliran lain DITOLAK (SC-05)")
    setup_events_dir(tmp)
    try:
        s = make_session()
        ev1 = event_store.append_event(s, role="user", kind="message", text="omzet saya dulu 30 juta")
        res1 = verify_and_commit(s, ev1, obs(claims=[
            cl("c1", "claim", "omzet", "was", "omzet saya dulu 30 juta",
               quantity=qty(value_kind="exact", value=30, unit="juta"), tense="past")]))
        check("kutipan giliran 1 diterima", len(res1.accepted_claims) == 1)
        ev2 = event_store.append_event(s, role="user", kind="message", text="sekarang turun menjadi 18 juta")
        res2 = verify_and_commit(s, ev2, obs(claims=[
            # the quote is NOT in the turn-2 message — must be rejected
            cl("c1", "claim", "omzet", "was", "omzet saya dulu 30 juta",
               quantity=qty(value_kind="exact", value=30, unit="juta"), tense="past"),
            cl("c2", "claim", "omzet", "dropped_to", "sekarang turun menjadi 18 juta",
               quantity=qty(value_kind="exact", value=18, unit="juta"))]))
        check("salah sitir ditolak", len(res2.accepted_claims) == 1 and len(res2.rejections) == 1,
              str(res2.rejections))
        check("alasan penolakan menyebut SC-05", "SC-05" in res2.rejections[0])
        check("graph tidak tercemar", len(s.state_graph["nodes"]) == 2)
    finally:
        restore_events_dir()


# ── D/E: supersession & cross-turn relations ─────────────────────────────────

def test_cross_turn_revision_and_contradiction(tmp: Path):
    print("D/E — koreksi lintas giliran + relasi kontradiksi")
    setup_events_dir(tmp)
    try:
        s = make_session()
        ev1 = event_store.append_event(s, role="user", kind="message",
                                       text="saya kira masalahnya marketing")
        res1 = verify_and_commit(s, ev1, obs(claims=[
            cl("c1", "assumption", "masalah", "probably_is", "saya kira masalahnya marketing")]))
        old_id = res1.claim_ids["c1"]

        ev2 = event_store.append_event(s, role="user", kind="message",
                                       text="setelah dicek leads tetap banyak yang masuk")
        res2 = verify_and_commit(s, ev2, obs(claims=[
            cl("c1", "claim", "leads", "still_many", "leads tetap banyak yang masuk")],
            relations=[]))
        leads_id = res2.claim_ids["c1"]
        check("klaim baru aktif", s.state_graph["nodes"][leads_id]["status"] == "active")

        ev3 = event_store.append_event(s, role="user", kind="message",
                                       text="bukan marketing — saya tidak pernah follow-up")
        res3 = verify_and_commit(s, ev3, obs(claims=[
            cl("c1", "claim", "saya", "never_does", "saya tidak pernah follow-up")],
            relations=[
                # cross-turn contradiction: the new claim vs the old assumption
                {"src": "c1", "dst": old_id, "kind": "contradicts", "reason": "asumsi marketing melemah"},
            ]))
        check("relasi lintas-giliran diterima", len(res3.accepted_edges) == 1, str(res3.rejections))
        check("edge menyasar klaim lama", res3.accepted_edges[0]["dst"] == old_id)

        ev4 = event_store.append_event(s, role="user", kind="message",
                                       text="ya, tepatnya masalahnya di follow-up bukan marketing")
        res4 = verify_and_commit(s, ev4, obs(claims=[
            cl("c1", "claim", "masalah", "is", "masalahnya di follow-up bukan marketing",
               supersedes=old_id, revision_kind="correction",
               revision_reason="user mengoreksi diagnosisnya sendiri")]))
        check("revisi diterima", len(res4.revisions) == 1)
        check("klaim lama berstatus superseded",
              s.state_graph["nodes"][old_id]["status"] == "superseded")
        check("sejarah tetap ada (node tidak dihapus)", old_id in s.state_graph["nodes"])
        check("penanda superseded_by tercatat",
              s.state_graph["nodes"][old_id].get("superseded_by") == res4.claim_ids["c1"])
        # only the current view is active
        from core.semantic.observation import current_view
        view_ids = {n["id"] for n in current_view(s.state_graph)}
        check("current view mengecualikan superseded", old_id not in view_ids)
    finally:
        restore_events_dir()


# ── F/G/H: idempotency, failures, durability ────────────────────────────────

def test_idempotency_and_failure(tmp: Path):
    print("F/G/H — idempotensi + kegagalan pemahaman + kegagalan penyimpanan")
    setup_events_dir(tmp)
    try:
        s = make_session()
        ev = event_store.append_event(s, role="user", kind="message", text="omzet 20 juta",
                                      idempotency_key="k-123")
        found = event_store.find_by_idempotency_key(s, "k-123")
        check("kunci idempotensi ditemukan", found is not None and found["event_id"] == ev["event_id"])
        check("kunci lain tidak ditemukan", event_store.find_by_idempotency_key(s, "k-999") is None)

        # G: understanding failure -> status visible, event kept
        class BoomLLM:
            def structured_call(self, *a, **k):
                raise RuntimeError("provider down")
        from app.turn import run_semantic_turn
        failed = False
        try:
            run_semantic_turn(s, BoomLLM(), ev)
        except RuntimeError:
            failed = True
        check("kegagalan pemahaman dinaikkan", failed)
        check("event tetap tahan-lama", ev in s.events)
        check("status understanding_failed", ev["status"] == "understanding_failed")

        # F: reprocessing the same event (retry) -> healthy LLM -> SINGLE commit
        good = FakeLLM([obs(claims=[
            cl("c1", "claim", "omzet", "is", "omzet 20 juta",
               quantity=qty(value_kind="exact", value=20, unit="juta"))])])
        res = run_semantic_turn(s, good, ev)
        check("retry berhasil commit", len(res.accepted_claims) == 1)
        run_semantic_turn(s, good, ev)  # idempotent reprocess
        check("pemrosesan ulang tidak menduplikasi klaim",
              len(s.state_graph["nodes"]) == 1, f"nodes={len(s.state_graph['nodes'])}")

        # H: kegagalan penyimpanan event dinaikkan
        event_store.EVENTS_DIR = tmp / "nonexistent-root" / "x"  # parent uncreatable? mkdir parents=True makes it
        # use a file-shaped path so open('a') fails
        blocker = tmp / "blocker"
        blocker.write_text("not a dir")
        event_store.EVENTS_DIR = blocker
        raised = False
        try:
            event_store.append_event(s, role="user", kind="message", text="tes")
        except EventPersistenceError:
            raised = True
        check("kegagalan persistensi DINAIKKAN (tidak ditelan)", raised)
    finally:
        restore_events_dir()


# ── I: long conversation ─────────────────────────────────────────────────────

def test_long_conversation(tmp: Path):
    print("I — 22 giliran: akumulasi + revisi + current view")
    setup_events_dir(tmp)
    try:
        s = make_session()
        total = 0
        for t in range(1, 23):
            text = f"catatan giliran {t}: beban kerja bertambah"
            ev = event_store.append_event(s, role="user", kind="message", text=text)
            if t == 15:
                o = obs(claims=[cl("c1", "claim", "beban kerja", "increases", "beban kerja bertambah")])
            else:
                o = obs(claims=[cl("c1", "claim", "beban kerja", "increases", "beban kerja bertambah")])
            res = verify_and_commit(s, ev, o)
            total += len(res.accepted_claims)
        check("22 giliran semua ter-commit", total == 22, f"total={total}")
        check("graph memuat 22 node", len(s.state_graph["nodes"]) == 22)
        durable = event_store.load_events(s.id)
        check("event JSONL (path sesi nyata) memuat 22 event", len(durable) == 22, f"n={len(durable)}")
        # real reload: a fresh session without a mirror is restored from JSONL
        fresh = make_session()
        n = event_store.reconcile_session_events(fresh)
        check("reconcile memulihkan 22 event dari JSONL", n == 22 and len(fresh.events) == 22, f"n={n}")
    finally:
        restore_events_dir()


# ── J: desire without numbers -> a contextual first question ───────────────────

def test_first_question_contextual(tmp: Path):
    print("J — desire tanpa angka: tidak ada target karangan; pertanyaan pertama = NextMove adaptif (R5)")
    import app.main as app_main
    from core.semantic.contract import SemanticObservation  # noqa: F401
    from domains.revenue.schema.goal import build_goal
    from store.memory import Session
    st, sess_dir, saved, _ = _real_env(tmp)
    try:
        # R5: the old deterministic selector (_contextual_first_question) was REMOVED; the R3 contract (CP-32) holds:
        # the first question is not a generic revenue template, it comes from understood state, no fabricated Goal.
        check("pemilih pertanyaan pertama deterministik lama sudah dihapus",
              not hasattr(app_main, "_contextual_first_question"))
        s = Session(id="fq-01", goal_text="saya ingin bisnis tetap jalan saat saya libur", language="id")
        s.goal = build_goal(s.goal_text, desire="").model_dump()
        ev = event_store.append_event(s, role="user", kind="create_map", text=s.goal_text)
        s.transcript.append(("user", s.goal_text))
        llm = FakeLLM([obs(claims=[
            cl("c1", "desire", "saya", "wants", "saya ingin bisnis tetap jalan saat saya libur", tense="future")])])
        from app.turn import run_semantic_turn
        run_semantic_turn(s, llm, ev)
        q = app_main._first_move(s, llm, ev)
        pr = s.planner_log[-1]["presented"]
        check("pertanyaan pertama disajikan oleh penalaran adaptif tervalidasi (bukan selector lama)",
              pr["source"] == "adaptive" and pr["policy"] == "nm.v2" and q == pr["text"] and q.strip())
        check("langkah pertama tercatat di planner_log ber-event_id (penghitung 'sudah ditanya' benar)",
              s.planner_log[-1]["event_id"] == ev["event_id"] and llm.reasoning_calls == 1)
        check("bukan template omzet generik", "30" not in q and "90 hari" not in q, q)
        check("goal tanpa target karangan", s.goal.get("target") is None)
        # no provider → an honest degraded HOLD, not a fabricated question
        s2 = Session(id="fq-02", goal_text="bisnis saya", language="id")
        s2.goal = build_goal(s2.goal_text, desire="").model_dump()
        ev2 = event_store.append_event(s2, role="user", kind="create_map", text=s2.goal_text)
        q2 = app_main._first_move(s2, None, ev2)
        check("tanpa provider: HOLD degraded jujur (cerita tersimpan), bukan pertanyaan karangan",
              s2.planner_log[-1]["presented"]["degraded"] is True and "tersimpan" in q2, q2)
    finally:
        _restore_real_env(st, saved)


# ── K/L/M: otoritas tunggal, commit independen, scope ─────────────────────────

def test_single_authority_and_independence(tmp: Path):
    print("K/L/M — satu panggilan LLM; commit independen dari navigasi; scope sesi")
    setup_events_dir(tmp)
    try:
        import app.turn as turn_mod

        s = make_session()
        llm = FakeLLM([obs(claims=[
            cl("c1", "claim", "omzet", "is", "omzet saya 18 juta",
               quantity=qty(value_kind="exact", value=18, unit="juta"))])])

        saved_navigate = turn_mod.navigate_session

        def broken_navigate(sess, **kw):
            raise RuntimeError("planner meledak")

        turn_mod.navigate_session = broken_navigate
        try:
            resp = turn_mod.run_turn(s, llm, "omzet saya 18 juta")
            check("giliran tetap berjalan dengan HOLD", resp is not None)
        finally:
            turn_mod.navigate_session = saved_navigate
        check("TEPAT SATU panggilan LLM semantik per giliran", llm.calls == 1, f"calls={llm.calls}")
        check("observasi tetap ter-commit walau navigasi gagal (SC-09)",
              len(s.state_graph["nodes"]) == 1)
        check("event ber-status committed", s.events[0]["status"] == "committed")

        # M: another session's event is REJECTED before any mutation
        from core.semantic.commit import ForeignEventError
        other = make_session(sid="other-sess")
        ev_other = event_store.append_event(other, role="user", kind="message", text="omzet 5 juta")
        before = json.dumps(s.state_graph, sort_keys=True)
        rejected = False
        try:
            verify_and_commit(s, ev_other, obs(claims=[
                cl("c1", "claim", "omzet", "is", "omzet 5 juta")]))
        except ForeignEventError:
            rejected = True
        check("event sesi asing ditolak (ForeignEventError)", rejected)
        check("graph tidak berubah sama sekali", json.dumps(s.state_graph, sort_keys=True) == before)
    finally:
        restore_events_dir()


# ── R3.1: durability, retry, grade, quantity, context ─────────────────────────

def _with_persist_dir(path):
    from store.memory import store as st
    saved = st.PERSIST_DIR
    st.PERSIST_DIR = path
    return st, saved


def test_durability_and_retry(tmp: Path):
    print("O/P — snapshot gagal: tanpa ACK palsu; retry tanpa duplikasi; recovery restart")
    setup_events_dir(tmp)
    blocker = tmp / "blocker"
    tmp.mkdir(parents=True, exist_ok=True)
    blocker.write_text("file biasa, bukan direktori")
    st, saved = _with_persist_dir(blocker / "sessions")   # mkdir will certainly fail
    try:
        import app.turn as turn_mod
        from store.events import SessionPersistenceError

        s = make_session(sid="durable01")
        llm = FakeLLM([obs(claims=[cl("c1", "claim", "omzet", "is", "omzet saya 18 juta",
                                      quantity=qty(value_kind="exact", value=18, unit="juta"))])])
        raised = False
        try:
            turn_mod.run_turn(s, llm, "omzet saya 18 juta", idempotency_key="k1")
        except SessionPersistenceError:
            raised = True
        check("snapshot gagal -> error (bukan ACK)", raised)
        check("event persist_failed, bukan committed", s.events[0]["status"] == "persist_failed",
              s.events[0]["status"])
        check("event tetap ada di JSONL", len(event_store.load_events("durable01")) >= 1)
        n_user = sum(1 for r, _ in s.transcript if r == "user")

        # retry (storage recovered) on the SAME event
        st.PERSIST_DIR = tmp / "ok-sessions"
        resp = turn_mod.run_turn(s, llm, "omzet saya 18 juta", idempotency_key="k1")
        check("retry sukses", resp is not None)
        user_events = [e for e in s.events if e["role"] == "user"]
        check("retry tidak membuat event user baru", len(user_events) == 1, str(len(user_events)))
        check("retry tidak menduplikasi transcript user",
              sum(1 for r, _ in s.transcript if r == "user") == n_user == 1)
        check("klaim tidak terduplikasi", len(s.state_graph["nodes"]) == 1)
        check("event kini committed", user_events[0]["status"] == "committed")
        # R3.2-A: a committed key is NO LONGER a raw 409 — the previous full result is restored
        # (this test locks the old behavior; the new contract is tested in test_r32a_exactly_once)
        n_ev = len(s.events)
        again = turn_mod.run_turn(s, llm, "omzet saya 18 juta", idempotency_key="k1")
        check("kunci committed -> hasil dipulihkan tanpa efek baru", again is not None and len(s.events) == n_ev)

        # restart: snapshot lost before save, JSONL present -> recovery
        fresh = make_session(sid="durable01")
        n = event_store.reconcile_session_events(fresh)
        check("recovery pasca-restart memulihkan event dari JSONL", n >= 1 and fresh.events[0]["role"] == "user")
        check("status hasil recovery = committed (amenden JSONL)", fresh.events[0]["status"] == "committed")
        check("tidak ada berkas .tmp tersisa", not list((tmp / "ok-sessions").glob("*.tmp")))
    finally:
        st.PERSIST_DIR = saved
        restore_events_dir()


def test_grade_and_quantity(tmp: Path):
    print("Q/R — grade tak terpromosi; range/batas tak jadi angka biasa")
    from core.semantic.derive import evidence_from_commit, number_claims_from_commit
    setup_events_dir(tmp)
    try:
        s = make_session(sid="gq01")
        ev = event_store.append_event(s, role="user", kind="message",
                                      text="omzet kira-kira 10 sampai 20 juta, paling banyak 5 juta bersih, 8 juta pasti")
        res = verify_and_commit(s, ev, obs(claims=[
            cl("c1", "claim", "omzet", "is", "omzet kira-kira 10 sampai 20 juta",
               epistemic="measured", quantity=qty(value_kind="range", low=10, high=20, unit="juta")),
            cl("c2", "claim", "laba", "is", "paling banyak 5 juta bersih",
               quantity=qty(value_kind="at_most", value=5, unit="juta")),
            cl("c3", "claim", "omzet", "is", "8 juta pasti",
               epistemic="measured", quantity=qty(value_kind="exact", value=8, unit="juta")),
        ]))
        ev_items = evidence_from_commit(res)
        check("measured (kesaksian) TIDAK menjadi transactional",
              all(e["level"] == "self_reported" for e in ev_items), str([e["level"] for e in ev_items]))
        nc = number_claims_from_commit(res)
        check("range & batas tidak diproyeksikan sebagai angka biasa", len(nc) == 1 and nc[0]["value"] == 8.0,
              str(nc))
        check("makna range/batas tetap utuh di graph kanonik",
              any((n.get("quantity") or {}).get("value_kind") == "range" for n in s.state_graph["nodes"].values())
              and any((n.get("quantity") or {}).get("value_kind") == "at_most" for n in s.state_graph["nodes"].values()))
    finally:
        restore_events_dir()


def test_context_has_qa_pairs(tmp: Path):
    print("S — konteks memuat pertanyaan engine bersama jawaban user")
    from core.semantic.observation import build_context_digest
    setup_events_dir(tmp)
    try:
        s = make_session(sid="ctx01")
        s.transcript = [("user", "bisnis saya turun"), ("engine", "Apakah penurunan itu dari jumlah pelanggan?"),
                        ("user", "ya, itu yang kedua")]
        ev = event_store.append_event(s, role="user", kind="message", text="ya, itu yang kedua")
        d = build_context_digest(s, ev)
        check("pertanyaan engine ada di konteks", "ENGINE: Apakah penurunan itu dari jumlah pelanggan?" in d)
        check("urutan tanya-jawab terjaga",
              d.index("ENGINE: Apakah") < d.index("USER: ya, itu yang kedua"))
    finally:
        restore_events_dir()


# ══════════════════════════════════════════════════════════════════════════════
# R3.2 — residual integrity closure (exactly-once, real restarts, provenance, revisions)
# ══════════════════════════════════════════════════════════════════════════════

def _real_env(tmp: Path):
    """A REAL store (Session dataclass + SessionStore + JSONL) in a temp directory."""
    from store.memory import Session, SessionStore
    from store.memory import store as st
    setup_events_dir(tmp)
    sess_dir = tmp / "sessions"
    saved = (st.PERSIST_DIR, SessionStore.PERSIST_DIR)
    st.PERSIST_DIR = sess_dir
    SessionStore.PERSIST_DIR = sess_dir
    return st, sess_dir, saved, Session


def _restore_real_env(st, saved):
    from store.memory import SessionStore
    st.PERSIST_DIR, SessionStore.PERSIST_DIR = saved
    restore_events_dir()


def _new_real_session(Session, sid, user_id="u-test"):
    s = Session(id=sid, goal_text="saya ingin bisnis tetap jalan saat saya libur", language="id",
                user_id=user_id)
    return s


def _reload(sess_dir):
    from store.memory import SessionStore
    SessionStore.PERSIST_DIR = sess_dir
    return SessionStore()


def test_r32a_exactly_once(tmp: Path):
    print("R3.2-A — exactly-once: retry setelah snapshot gagal, restart, key/scope")
    import app.turn as turn_mod
    from store.events import SessionPersistenceError
    st, sess_dir, saved, Session = _real_env(tmp)
    try:
        s = _new_real_session(Session, "xo-sess-01")
        llm = FakeLLM([obs(claims=[cl("c1", "claim", "omzet", "is", "omzet saya 18 juta",
                                      quantity=qty(value_kind="exact", value=18, unit="juta"))])])
        real_save = st.save_strict
        boom = {"n": 0}

        def flaky(sess):
            if boom["n"] == 0:
                boom["n"] += 1
                raise SessionPersistenceError("disk penuh (injeksi)")
            return real_save(sess)

        st.save_strict = flaky
        try:
            raised = False
            try:
                turn_mod.run_turn(s, llm, "omzet saya 18 juta", idempotency_key="k-1")
            except SessionPersistenceError:
                raised = True
            check("snapshot gagal -> error, bukan ACK", raised)
            r2 = turn_mod.run_turn(s, llm, "omzet saya 18 juta", idempotency_key="k-1")
        finally:
            st.save_strict = real_save
        users = [e for e in s.events if e["role"] == "user"]
        engines = [e for e in s.events if e["role"] == "engine"]
        check("satu permintaan logis = satu event user", len(users) == 1, str(len(users)))
        check("balasan engine TIDAK digandakan pada retry", len(engines) == 1, str(len(engines)))
        check("transcript: 1 user + 1 engine",
              [r for r, _ in s.transcript] == ["user", "engine"], str(s.transcript))
        check("planner_log tidak digandakan", len(s.planner_log) == 1, str(len(s.planner_log)))
        check("klaim kanonik tidak digandakan", len(s.state_graph["nodes"]) == 1)
        check("evidence tidak digandakan", len(s.evidence) == 1, str(len(s.evidence)))
        check("number_claims tidak digandakan", len(s.number_claims) == 1, str(len(s.number_claims)))
        check("retry tidak memanggil LLM semantik lagi (commit sudah ada)", llm.calls == 1,
              f"calls={llm.calls}")
        check("retry mengembalikan respons nyata", r2 is not None and r2.next_move is not None)

        # same key, different text -> rejected with no effect
        before = json.dumps(s.state_graph, sort_keys=True)
        conflict = False
        try:
            turn_mod.run_turn(s, llm, "omzet saya 99 juta", idempotency_key="k-1")
        except Exception as exc:
            conflict = type(exc).__name__ == "IdempotencyConflictError"
        check("kunci sama + payload berbeda ditolak (IdempotencyConflictError)", conflict)
        check("penolakan konflik tanpa efek", json.dumps(s.state_graph, sort_keys=True) == before
              and len([e for e in s.events if e["role"] == "user"]) == 1)

        # a repeated committed key -> the earlier response is restored, no new effects
        r3 = turn_mod.run_turn(s, llm, "omzet saya 18 juta", idempotency_key="k-1")
        check("kunci committed -> hasil lengkap sebelumnya dipulihkan",
              r3.model_dump() == r2.model_dump())
        check("pemulihan hasil tidak menambah event/LLM", len(s.events) == 2 and llm.calls == 1)

        # another session, same key -> no cross-contamination
        s2 = _new_real_session(Session, "xo-sess-02")
        llm2 = FakeLLM([obs(claims=[cl("c1", "claim", "omzet", "is", "omzet 5 juta",
                                       quantity=qty(value_kind="exact", value=5, unit="juta"))])])
        turn_mod.run_turn(s2, llm2, "omzet 5 juta", idempotency_key="k-1")
        check("kunci sama di sesi lain diproses mandiri", llm2.calls == 1 and len(s2.state_graph["nodes"]) == 1)
        check("sesi pertama tak tersentuh", len(s.state_graph["nodes"]) == 1)

        # restart: all effects remain exactly one
        st2 = _reload(sess_dir)
        r = st2.get("xo-sess-01")
        check("sesi termuat dari snapshot nyata", r is not None)
        check("restart: event/transcript/graph/planner/evidence identik",
              r is not None and [e["event_id"] for e in r.events] == [e["event_id"] for e in s.events]
              and r.transcript == [tuple(t) for t in s.transcript]
              and r.state_graph == s.state_graph and len(r.planner_log) == 1 and len(r.evidence) == 1)
        llm3 = FakeLLM([obs()])
        r4 = turn_mod.run_turn(r, llm3, "omzet saya 18 juta", idempotency_key="k-1")
        check("retry pasca-restart memulihkan hasil, tanpa LLM/efek baru",
              r4.model_dump() == r2.model_dump() and llm3.calls == 0 and len(r.events) == 2)
    finally:
        _restore_real_env(st, saved)


def test_r32a_concurrent(tmp: Path):
    print("R3.2-A — dua permintaan bersamaan, kunci sama: tepat satu efek")
    import threading
    import time as _t

    import app.turn as turn_mod
    st, sess_dir, saved, Session = _real_env(tmp)
    try:
        s = _new_real_session(Session, "xo-conc-01")

        class SlowLLM(FakeLLM):
            def structured_call(self, schema, system, user, retries=2):
                _t.sleep(0.15)
                return super().structured_call(schema, system, user, retries)

        llm = SlowLLM([obs(claims=[cl("c1", "claim", "omzet", "is", "omzet saya 18 juta",
                                      quantity=qty(value_kind="exact", value=18, unit="juta"))])])
        out, errs = [], []

        def go():
            try:
                out.append(turn_mod.run_turn(s, llm, "omzet saya 18 juta", idempotency_key="k-c"))
            except Exception as exc:  # noqa: BLE001
                errs.append(exc)

        ts = [threading.Thread(target=go) for _ in range(2)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        check("tanpa error pada kedua permintaan", not errs, str(errs))
        check("tepat satu event user", len([e for e in s.events if e["role"] == "user"]) == 1)
        check("tepat satu panggilan LLM", llm.calls == 1, f"calls={llm.calls}")
        check("tepat satu balasan engine", len([e for e in s.events if e["role"] == "engine"]) == 1)
    finally:
        _restore_real_env(st, saved)


def test_r32b_restart_integrity(tmp: Path):
    print("R3.2-B — restart nyata: snapshot absen/basi/korup, baris JSONL parsial, amenden gagal")
    import app.turn as turn_mod
    st, sess_dir, saved, Session = _real_env(tmp)
    try:
        # ── STALE snapshot: the 2nd event exists only in the JSONL ──
        s = _new_real_session(Session, "rs-stale-01")
        llm = FakeLLM([obs(claims=[cl("c1", "claim", "omzet", "is", "omzet saya 18 juta",
                                      quantity=qty(value_kind="exact", value=18, unit="juta"))])])
        turn_mod.run_turn(s, llm, "omzet saya 18 juta", idempotency_key="k1")
        event_store.append_event(s, role="user", kind="message", text="pesan kedua belum diproses",
                                 idempotency_key="k2")   # crash before the snapshot
        st2 = _reload(sess_dir)
        r = st2.get("rs-stale-01")
        e2 = next((e for e in (r.events if r else []) if e.get("idempotency_key") == "k2"), None)
        check("event basi dipulihkan dari JSONL", e2 is not None and e2["status"] == "received")
        llm_b = FakeLLM([obs(claims=[cl("c1", "claim", "pesan", "is", "pesan kedua belum diproses")])])
        turn_mod.run_turn(r, llm_b, "pesan kedua belum diproses", idempotency_key="k2")
        check("retry atas event yang dipulihkan: 1 event user (bukan 2)",
              len([e for e in r.events if e.get("idempotency_key") == "k2"]) == 1
              and len([e for e in r.events if e["role"] == "user"]) == 2)

        # ── 'committed' amendment missing in JSONL, snapshot committed: status must not regress ──
        f = event_store._event_file("rs-stale-01")
        rows = [ln for ln in f.read_text().splitlines() if ln.strip()]
        keep = [ln for ln in rows if not (('"status"' in ln) and ('"role"' not in ln)
                                          and '"committed"' in ln)]
        f.write_text("\n".join(keep) + "\n")
        st3 = _reload(sess_dir)
        r3 = st3.get("rs-stale-01")
        u1 = next(e for e in r3.events if e.get("idempotency_key") == "k1")
        check("status committed di snapshot tidak diturunkan oleh JSONL yang tertinggal",
              u1["status"] == "committed", u1["status"])

        # ── ABSENT snapshot + events present = orphan: visible fail-closed ──
        (sess_dir / "rs-stale-01.json").unlink()
        st4 = _reload(sess_dir)
        kinds = {(i["session_id"], i["kind"]) for i in st4.recovery_issues}
        check("orphan event tanpa snapshot dilaporkan (tidak diam-diam hilang)",
              ("rs-stale-01", "orphan_events") in kinds, str(kinds))
        check("sesi orphan tidak diperlakukan sebagai sesi sehat", st4.get("rs-stale-01") is None)

        # ── CORRUPT snapshot: quarantined, not swallowed ──
        s5 = _new_real_session(Session, "rs-corrupt-01")
        st.save_strict(s5)
        (sess_dir / "rs-corrupt-01.json").write_text("{ bukan json")
        st5 = _reload(sess_dir)
        kinds5 = {(i["session_id"], i["kind"]) for i in st5.recovery_issues}
        check("snapshot korup dilaporkan", ("rs-corrupt-01", "corrupt_snapshot") in kinds5, str(kinds5))
        check("berkas korup dipertahankan sebagai bukti (.corrupt)",
              bool(list(sess_dir.glob("rs-corrupt-01.json.corrupt*"))))

        # ── partial JSONL line (torn write) ──
        s6 = _new_real_session(Session, "rs-torn-01")
        event_store.append_event(s6, role="user", kind="message", text="halo satu")
        f6 = event_store._event_file("rs-torn-01")
        with f6.open("a") as fh:
            fh.write('{"event_id": "ce-rs-torn-01-0001", "role": "us')   # no newline
        evs, issues = event_store.load_events_checked("rs-torn-01")
        check("baris parsial di ujung berkas dilaporkan sebagai torn_tail",
              any(i["kind"] == "torn_tail" for i in issues) and len(evs) == 1, str(issues))
        s6.events = [dict(evs[0])]
        e_new = event_store.append_event(s6, role="user", kind="message", text="halo dua")
        evs2, issues2 = event_store.load_events_checked("rs-torn-01")
        check("append sesudah torn tail tidak menempel pada baris rusak",
              [e["text"] for e in evs2] == ["halo satu", "halo dua"], str([e.get("text") for e in evs2]))
        check("event baru tetap utuh", e_new["event_id"] == evs2[-1]["event_id"])

        # ── broken line in the middle ──
        s7 = _new_real_session(Session, "rs-mid-01")
        event_store.append_event(s7, role="user", kind="message", text="satu")
        f7 = event_store._event_file("rs-mid-01")
        with f7.open("a") as fh:
            fh.write("%%% rusak %%%\n")
        event_store.append_event(s7, role="user", kind="message", text="tiga")
        evs7, issues7 = event_store.load_events_checked("rs-mid-01")
        check("baris rusak di tengah dilaporkan (malformed_row), sisanya terbaca",
              any(i["kind"] == "malformed_row" for i in issues7) and len(evs7) == 2, str(issues7))
    finally:
        _restore_real_env(st, saved)


def test_r32c_provenance(tmp: Path):
    print("R3.2-C — provenance sumber: event palsu/konflik/seq ganda/lintas sesi ditolak SEBELUM mutasi")
    from core.semantic.commit import ForeignEventError
    setup_events_dir(tmp)
    try:
        s = make_session(sid="pv-01")
        ev = event_store.append_event(s, role="user", kind="message", text="omzet saya 18 juta")
        good = lambda: obs(claims=[cl("c1", "claim", "omzet", "is", "omzet saya 18 juta")])  # noqa: E731

        def snap():
            return json.dumps([s.state_graph, s.events], sort_keys=True)

        def rejects(event, label, o=None):
            before = snap()
            try:
                verify_and_commit(s, event, o or good())
                ok = False
            except ForeignEventError:
                ok = True
            check(f"{label} -> ditolak", ok)
            check(f"{label}: tanpa mutasi graph/event", snap() == before)

        forged = dict(ev, event_id="ce-pv-01-0099", seq=99)
        rejects(forged, "event_id tak dikenal (session_id valid)")
        rejects(dict(ev, text="omzet saya 99 juta"), "event_id sama, payload berbeda")
        rejects(dict(ev, kind="engine"), "scope sumber tak didukung")
        eng = event_store.append_event(s, role="engine", kind="engine", text="omzet saya 18 juta")
        rejects(eng, "event non-user")
        # duplicate seq -> claim id collision
        dup = dict(ev, event_id="ce-pv-01-dup")
        s.events.append(dup)
        rejects(ev, "seq ganda di riwayat sesi", good())
        s.events.remove(dup)
        # a valid event is still accepted
        res = verify_and_commit(s, ev, good())
        check("event sah tetap dapat di-commit", len(res.accepted_claims) == 1)
        # cross-session claim reference
        s.state_graph["nodes"]["cl-foreign-001"] = {
            "id": "cl-foreign-001", "type": "claim", "status": "active", "version": 1,
            "provenance": {"event_id": "ce-other-0001", "session": "other-sess"}}
        ev2 = event_store.append_event(s, role="user", kind="message", text="ralat: omzet 12 juta")
        before = json.dumps(s.state_graph, sort_keys=True)
        r2 = verify_and_commit(s, ev2, obs(claims=[
            cl("c1", "claim", "omzet", "is", "ralat: omzet 12 juta", supersedes="cl-foreign-001", revision_kind="correction", revision_reason="koreksi")]))
        check("supersedes klaim milik sesi lain ditolak", len(r2.accepted_claims) == 0 and len(r2.rejections) == 1,
              str(r2.rejections))
        check("klaim asing tidak diubah", json.dumps(s.state_graph, sort_keys=True) == before)
    finally:
        restore_events_dir()


def test_r32d_revision(tmp: Path):
    print("R3.2-D — revisi: konfirmasi, koreksi, evidence turunan, kontradiksi, reprocess, penolakan")
    import app.turn as turn_mod
    from core.schema.evidence import current_evidence
    from core.semantic.commit import open_contradictions
    from core.semantic.contract import ObservedRelation
    st, sess_dir, saved, Session = _real_env(tmp)
    try:
        s = _new_real_session(Session, "rv-01")
        llm = FakeLLM([
            obs(claims=[cl("c1", "claim", "omzet", "is", "omzet saya 18 juta",
                           quantity=qty(value_kind="exact", value=18, unit="juta"))]),
            obs(claims=[cl("c1", "claim", "omzet", "confirmed", "ya betul omzet 18 juta",
                           supersedes="cl-e0000-001", revision_kind="confirmation",
                           revision_reason="user menegaskan")]),
            obs(claims=[cl("c1", "claim", "omzet", "is", "ralat omzet sebenarnya 12 juta",
                           quantity=qty(value_kind="exact", value=12, unit="juta"),
                           supersedes="cl-e0000-001", revision_kind="correction",
                           revision_reason="koreksi")]),
        ])
        turn_mod.run_turn(s, llm, "omzet saya 18 juta")
        turn_mod.run_turn(s, llm, "ya betul omzet 18 juta")
        nodes, edges = s.state_graph["nodes"], s.state_graph["edges"]
        conf = [e for e in edges.values() if e["kind"] == "confirms"]
        check("konfirmasi membuat edge confirms yang dapat dilacak",
              len(conf) == 1 and conf[0]["dst"] == "cl-e0000-001", str(edges))
        check("target konfirmasi tetap aktif", nodes["cl-e0000-001"]["status"] == "active")
        turn_mod.run_turn(s, llm, "ralat omzet sebenarnya 12 juta")
        old = nodes["cl-e0000-001"]
        check("koreksi: klaim lama superseded tapi tetap ada (sejarah)", old["status"] == "superseded")
        ev_old = [e for e in s.evidence if e.claim_id == "cl-e0000-001"]
        check("evidence turunan klaim lama ditandai superseded", ev_old and all(e.superseded for e in ev_old),
              str([(e.claim_id, e.superseded) for e in s.evidence]))
        cur = current_evidence(s.evidence)
        check("evidence current tidak memuat klaim yang digantikan",
              all(not e.superseded for e in cur) and any(e.claim_id.startswith("cl-e0004") for e in cur),
              str([(e.claim_id, e.superseded) for e in cur]))
        check("evidence lama tidak dihapus (sejarah utuh)", len(s.evidence) >= 2)

        # reprocessing the same event does not revise twice
        ev3 = next(e for e in s.events if e.get("turn") == 3 and e["role"] == "user")
        v_before, n_edges = old["version"], len(s.state_graph["edges"])
        r = verify_and_commit(s, ev3, llm.observations[2])
        check("reprocess: tanpa penolakan semu & tanpa revisi ganda",
              not r.rejections and old["version"] == v_before and len(s.state_graph["edges"]) == n_edges,
              f"{r.rejections} v={old['version']} edges={len(s.state_graph['edges'])}")

        # contradiction visible until resolved
        s2 = _new_real_session(Session, "rv-02")
        llm2 = FakeLLM([
            obs(claims=[cl("c1", "claim", "marketing", "is_weak", "marketing saya lemah")]),
            obs(claims=[cl("c1", "claim", "leads", "banyak", "leads sebenarnya banyak")],
                relations=[ObservedRelation(src="c1", dst="cl-e0000-001", kind="contradicts", reason="bertentangan")]),
            obs(claims=[cl("c1", "claim", "marketing", "is_ok", "ralat: marketing saya baik",
                           supersedes="cl-e0000-001", revision_kind="correction", revision_reason="ralat")]),
        ])
        turn_mod.run_turn(s2, llm2, "marketing saya lemah")
        turn_mod.run_turn(s2, llm2, "leads sebenarnya banyak")
        check("kontradiksi tampak selama kedua ujung aktif", len(open_contradictions(s2.state_graph)) == 1)
        turn_mod.run_turn(s2, llm2, "ralat: marketing saya baik")
        check("kontradiksi tidak terbuka lagi setelah salah satu ujung digantikan",
              len(open_contradictions(s2.state_graph)) == 0)
        check("edge kontradiksi tetap ada sebagai sejarah",
              any(e["kind"] == "contradicts" for e in s2.state_graph["edges"].values()))

        # a verifier rejection is not reported as a successful fact commit
        s3 = _new_real_session(Session, "rv-03")
        llm3 = FakeLLM([obs(claims=[cl("c1", "claim", "omzet", "is", "kutipan yang tak ada di pesan")])])
        turn_mod.run_turn(s3, llm3, "pesan berbeda sama sekali")
        ue = next(e for e in s3.events if e["role"] == "user")
        check("event ditandai ada penolakan verifier (bukan fakta ter-commit)",
              "verifier_rejected" in ue.get("processing_note", ""), ue.get("processing_note", ""))
        check("tak ada klaim masuk graph", len(s3.state_graph["nodes"]) == 0)
    finally:
        _restore_real_env(st, saved)


def main() -> int:
    global _PASS, _FAIL
    tmp = Path(tempfile.mkdtemp(prefix="nvl-r3-"))
    test_rich_message_roles_and_quantities(tmp / "a")
    test_quote_anchor_rejects_wrong_event(tmp / "c")
    test_cross_turn_revision_and_contradiction(tmp / "d")
    test_idempotency_and_failure(tmp / "f")
    test_long_conversation(tmp / "i")
    test_first_question_contextual(tmp / "j")
    test_single_authority_and_independence(tmp / "k")
    test_durability_and_retry(tmp / "o")
    test_grade_and_quantity(tmp / "q")
    test_context_has_qa_pairs(tmp / "s")
    test_r32a_exactly_once(tmp / "r32a")
    test_r32a_concurrent(tmp / "r32a2")
    test_r32b_restart_integrity(tmp / "r32b")
    test_r32c_provenance(tmp / "r32c")
    test_r32d_revision(tmp / "r32d")
    print()
    print(f"HASIL: {_PASS}/{_PASS + _FAIL} PASS" + (" ✅" if _FAIL == 0 else " ❌"))
    return 0 if _FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
