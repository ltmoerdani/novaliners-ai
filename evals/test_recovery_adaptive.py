"""R5 — Adaptive NextMove reasoning on state + knowledge + hypotheses, behind deterministic guards.

EVIDENCE STATUS: DETERMINISTIC_PASS (contract, guards, integration, trace). This is NOT evidence the
questions help: the reasoning model here is a script/mock. Real reasoning quality = LIVE_NOT_RUN
until R7 (Z.ai).

  K  applied knowledge actually reaches the reasoning prompt, sourced & versioned
  H  competing hypotheses: built from active claims, revised when a claim is superseded, traced to the cause
  G  guard: fake/stale refs, out-of-menu, illegal focus, excess repeats, groundless ACTION,
     premature HOLD rejected
  F  failure: dead provider / guard rejects after repair -> honest degraded HOLD; observations stay intact;
     NO deterministic question selector silently takes over
  R  bounded repair: a violation is fed back once
  L  long context (20+ turns): sourced selection within a budget; old material is not lost
  P  hypothesis persistence + "already asked" counter from PRESENTED steps
Run: .venv/bin/python evals/test_recovery_adaptive.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from evals._store_isolation import isolate_store  # noqa: E402

isolate_store()  # eval: store redirected to tmp — production store untouched

import test_recovery_semantic as R  # noqa: E402

import app.turn as turn_mod  # noqa: E402
from core.reasoning.contract import NextMoveProposal  # noqa: E402
from core.reasoning.reasoner import parse_snapshot_prompt  # noqa: E402

_PASS = _FAIL = 0


def check(name, cond, detail=""):
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"  OK  {name}")
    else:
        _FAIL += 1
        print(f"  GAGAL  {name}{' — ' + detail if detail else ''}")


cl, obs, qty = R.cl, R.obs, R.qty


class ScriptedLLM(R.FakeLLM):
    """Semantics: observation script. Reasoning: `reasoner(snapshot, attempt_no) -> dict | Exception` (skrip)."""

    def __init__(self, observations, reasoner=None):
        super().__init__(observations)
        self.reasoner = reasoner
        self.snapshots = []
        self.reasoner_prompts = []
        self.attempts = 0

    def structured_call(self, schema, system, user, retries=2):
        if schema is NextMoveProposal:
            self.reasoning_calls += 1
            self.reasoner_prompts.append(user)
            snap = parse_snapshot_prompt(user)
            self.snapshots.append(snap)
            self.attempts += 1
            if self.reasoner is None:
                from providers.mock import _mock_next_move
                return NextMoveProposal.model_validate(_mock_next_move(user))
            out = self.reasoner(snap, self.attempts)
            if isinstance(out, Exception):
                raise out
            return NextMoveProposal.model_validate(out)
        return super().structured_call(schema, system, user, retries)


def sess(tmp, sid, text="saya ingin bisnis jalan tanpa saya"):
    st, sess_dir, saved, Session = R._real_env(tmp)
    s = Session(id=sid, goal_text=text, language="id")
    from domains.revenue.schema.goal import build_goal
    s.goal = build_goal(text, desire=text).model_dump()
    return s, st, sess_dir, saved


def presented(s):
    return s.planner_log[-1]["presented"]


def base_prop(snap, **kw):
    d = {"contract_version": "nm.v2", "state_snapshot_ref": snap["snapshot_id"], "proposed_move_kind": "QUESTION",
         "focus_type": "uncertainty", "proposed_focus": (snap["uncertainties"] or [{"id": ""}])[0]["id"],
         "move_text": "Seberapa sering Anda menindaklanjuti calon klien yang bertanya?",
         "information_value_rationale": "menentukan penjelasan mana yang berlaku",
         "expected_decision_change": "mengubah dari akuisisi ke tindak lanjut",
         "supporting_claim_refs": (snap["claim_ids"] or [])[-1:]}
    d.update(kw)
    return d


# ── K: knowledge reaches the reasoning ───────────────────────────────────────

def test_knowledge_delivery(tmp):
    print("K — pengetahuan terapan sampai ke penalaran, bersumber dan berversi")
    s, st, _, saved = sess(tmp, "k-01")
    try:
        text = ("Saya sering janji tapi tidak ada bukti apa pun; calon klien bilang akan pasti beli nanti kalau "
                "bisa, rencananya saya yakin akan laris, tanpa uji demand sama sekali")
        llm = ScriptedLLM([obs(claims=[cl("c1", "claim", "calon klien", "says", text, tense="now")])])
        turn_mod.run_turn(s, llm, text)
        snap = llm.snapshots[0]
        check("snapshot membawa klaim aktif bersumber (id klaim)", snap["claim_ids"] and snap["claims"])
        check("menu pengetahuan ada & berjejak ke klaim (anchors)",
              all(k["anchors"] and set(k["anchors"]) <= set(snap["claim_ids"]) for k in snap["knowledge"]),
              json.dumps(snap["knowledge"])[:200])
        check("pengetahuan hadir di PROMPT model (bukan hanya dimuat)",
              snap["knowledge"] == [] or snap["knowledge"][0]["id"] in llm.reasoner_prompts[0])
        ad = s.planner_log[-1]["adaptive"]
        from engine.knowledge import kb_sha256
        check("versi KB tercatat di keputusan", ad["kb_version"] == kb_sha256())
        check("id pengetahuan yang ditawarkan tercatat", ad["knowledge_offered"] == [k["id"] for k in snap["knowledge"]])
    finally:
        R._restore_real_env(st, saved)


# ── H: hypotheses ──────────────────────────────────────────────────────────────

def test_hypothesis_revision(tmp):
    print("H — hipotesis: marketing lemah -> kebocoran tindak lanjut (revisi bersumber)")
    s, st, sess_dir, saved = sess(tmp, "h-01")
    try:
        state = {"n": 0}

        def reasoner(snap, attempt):
            state["n"] += 1
            ids = snap["claim_ids"]
            if state["n"] == 1:
                return base_prop(snap, competing_hypotheses=[{
                    "statement": "akuisisi (marketing) lemah", "supports": [ids[0]],
                    "missing_evidence": ["jumlah inquiry masuk"]}], proposed_move_kind="QUESTION")
            # turn 2: the old assumption claim is superseded, the new claim is active
            return base_prop(snap, competing_hypotheses=[{
                "statement": "inquiry ada tetapi tindak lanjut bocor", "supports": ids[-2:],
                "missing_evidence": ["berapa inquiry yang diberi balasan <24 jam"]}])

        llm = ScriptedLLM([
            obs(claims=[cl("c1", "assumption", "marketing", "is_weak", "kayaknya marketing saya lemah")]),
            obs(claims=[cl("c1", "claim", "inquiry", "masuk", "sebenarnya inquiry masuk tiap minggu"),
                        cl("c2", "claim", "saya", "rarely_follows_up", "tapi jarang saya follow-up", aspect="behavior"),
                        cl("c3", "claim", "marketing", "is_ok", "jadi marketing saya sebenarnya cukup",
                           supersedes="cl-e0000-001", revision_kind="correction", revision_reason="koreksi asumsi")]),
        ], reasoner)
        turn_mod.run_turn(s, llm, "kayaknya marketing saya lemah")
        h1 = next(iter(s.hypotheses.values()))
        check("hipotesis dibuat dengan dukungan klaim aktif", h1["supports"] == ["cl-e0000-001"] and h1["status"] == "active")
        check("standing dihitung deterministik (tentative; bukan klaim model)", h1["standing"] == "tentative")
        turn_mod.run_turn(s, llm, "sebenarnya inquiry masuk tiap minggu, tapi jarang saya follow-up, "
                                  "jadi marketing saya sebenarnya cukup")
        hs = list(s.hypotheses.values())
        old = next(h for h in hs if h["id"] == h1["id"])
        new = next(h for h in hs if h["id"] != h1["id"])
        check("hipotesis lama kehilangan dukungan & melemah", old["supports"] == [] and old["status"] == "weakened",
              f"{old['supports']} {old['status']}")
        lost = [x for x in old["history"] if x["change"] == "support_lost"]
        check("jejak: dukungan hilang karena klaim koreksi tertentu",
              lost and lost[0]["claims"] == ["cl-e0000-001"] and lost[0]["caused_by"] == ["cl-e0002-003"], str(lost))
        check("hipotesis baru bersumber klaim aktif & tidak mengklaim kausalitas pasti",
              new["status"] == "active" and new["standing"] in ("tentative", "supported") and new["supports"]
              and new["missing_evidence"])
        check("hipotesis baru memuat klaim perilaku tindak lanjut",
              any(c.endswith("-002") for c in new["supports"]), str(new["supports"]))
        # persistence: reload
        st2 = R._reload(sess_dir)
        r = st2.get("h-01")
        check("hipotesis + riwayat bertahan setelah restart", r and r.hypotheses == s.hypotheses)
    finally:
        R._restore_real_env(st, saved)


# ── G: guard ──────────────────────────────────────────────────────────────────

def _ask_with(tmp, sid, mutate, obs_list=None):
    s, st, _, saved = sess(tmp, sid)
    try:
        llm = ScriptedLLM(obs_list or [obs(claims=[cl("c1", "claim", "omzet", "is", "omzet saya 18 juta",
                                                      quantity=qty(value_kind="exact", value=18, unit="juta"))])],
                          lambda snap, a: mutate(snap, a))
        turn_mod.run_turn(s, llm, "omzet saya 18 juta")
        return s, llm
    finally:
        R._restore_real_env(st, saved)


def test_guard(tmp):
    print("G — guard menolak usulan tidak sah (kemudian repair/degrade)")
    cases = {
        "klaim karangan": lambda snap, a: base_prop(snap, supporting_claim_refs=["cl-karangan-999"]),
        "snapshot basi": lambda snap, a: base_prop(snap, state_snapshot_ref="ss-basi"),
        "pengetahuan di luar menu": lambda snap, a: base_prop(snap, knowledge_refs=["TM-R999"]),
        "fokus bukan kandidat": lambda snap, a: base_prop(snap, proposed_focus="requirement:tidak.ada"),
        "ACTION tanpa dasar": lambda snap, a: base_prop(snap, proposed_move_kind="ACTION"),
        "HOLD prematur": lambda snap, a: base_prop(snap, proposed_move_kind="HOLD", abstain=False),
        "teks kosong": lambda snap, a: base_prop(snap, move_text=""),
    }
    for label, mut in cases.items():
        s, llm = _ask_with(tmp / label.replace(" ", "_"), "g-" + str(abs(hash(label)) % 9999), mut)
        p = presented(s)
        ad = s.planner_log[-1]["adaptive"]
        check(f"{label}: ditolak guard (dua percobaan, repair terbatas)", llm.reasoning_calls == 2, str(llm.reasoning_calls))
        check(f"{label}: HOLD degraded jujur, bukan pertanyaan deterministik lama",
              p["kind"] == "HOLD" and p.get("degraded") and ad["status"] == "DEGRADED")
        check(f"{label}: observasi semantik tetap ter-commit", len(s.state_graph["nodes"]) == 1)
        check(f"{label}: balasan engine = teks degraded, bukan karangan", "tersimpan" in s.transcript[-1][1])

    # schema: the model tries to write requirement status -> rejected by the contract
    try:
        NextMoveProposal.model_validate({**base_prop({"snapshot_id": "x", "uncertainties": [], "claim_ids": []}),
                                         "requirement_state": {"access.icp": "PRESENT"}})
        rejected = False
    except Exception:  # noqa: BLE001
        rejected = True
    check("kontrak nm.v2 menolak field status requirement (model tak punya jalur menulisnya)", rejected)
    try:
        NextMoveProposal.model_validate({**base_prop({"snapshot_id": "x", "uncertainties": [], "claim_ids": []}),
                                         "goal_confirmed": True})
        rejected = False
    except Exception:  # noqa: BLE001
        rejected = True
    check("kontrak menolak konfirmasi goal dari model", rejected)


def test_repair_and_failure(tmp):
    print("R/F — repair terbatas berhasil; provider mati -> degraded; klaim superseded tak bisa dirujuk")
    # repair: attempt 1 wrong, attempt 2 correct
    def reasoner(snap, a):
        return base_prop(snap, supporting_claim_refs=["cl-x"]) if a == 1 else base_prop(snap)
    s, llm = _ask_with(tmp / "rep", "rp-01", reasoner)
    check("repair: percobaan kedua diterima", llm.reasoning_calls == 2 and presented(s)["kind"] == "QUESTION"
          and presented(s)["source"] == "adaptive")
    check("repair: umpan balik pelanggaran masuk prompt percobaan kedua",
          "REJECTED BY THE VALIDATOR" in llm.reasoner_prompts[1] and "G2" in llm.reasoner_prompts[1])
    check("repair: jejak percobaan tersimpan", len(s.planner_log[-1]["adaptive"]["attempts"]) == 2)

    # dead provider
    class RateLimitError(Exception):
        status_code = 429
    s, llm = _ask_with(tmp / "prov", "pv-01", lambda snap, a: RateLimitError("kuota"))
    ad = s.planner_log[-1]["adaptive"]
    check("provider mati: degraded dengan alasan provider_unavailable (1 panggilan, tanpa menghamburkan kuota)",
          ad["status"] == "DEGRADED" and ad["reason"] == "provider_unavailable" and llm.reasoning_calls == 1)
    check("provider mati: observasi utuh & event committed", len(s.state_graph["nodes"]) == 1
          and [e for e in s.events if e["role"] == "user"][0]["status"] == "committed")

    # a superseded claim must not be referenced
    s, st, _, saved = sess(tmp / "sup", "sp-01")
    try:
        seen = {}

        def rr(snap, a):
            seen["ids"] = snap["claim_ids"]
            return base_prop(snap, supporting_claim_refs=["cl-e0000-001"])   # valid turn 1, stale turn 2

        llm = ScriptedLLM([
            obs(claims=[cl("c1", "claim", "omzet", "is", "omzet saya 18 juta")]),
            obs(claims=[cl("c1", "claim", "omzet", "is", "ralat omzet 12 juta", supersedes="cl-e0000-001",
                           revision_kind="correction", revision_reason="ralat")]),
        ], rr)
        turn_mod.run_turn(s, llm, "omzet saya 18 juta")
        turn_mod.run_turn(s, llm, "ralat omzet 12 juta")
        check("snapshot tidak memuat klaim yang digantikan", "cl-e0000-001" not in seen["ids"], str(seen["ids"]))
        check("rujukan ke klaim yang digantikan ditolak guard (tidak menghidupkan fakta lama)",
              s.planner_log[-1]["adaptive"]["status"] == "DEGRADED"
              and any("G2" in v for v in s.planner_log[-1]["adaptive"]["attempts"][0]["guard"]["violations"]))
    finally:
        R._restore_real_env(st, saved)


# ── L/P: long context, counters, candidates ────────────────────────────────

def test_long_context_and_counters(tmp):
    print("L/P — 22 giliran: seleksi bersumber dgn anggaran; penghitung 'sudah ditanya' dari yang DISAJIKAN")
    from core.reasoning.snapshot import build_snapshot
    nodes = {}
    for i in range(1, 61):
        cid = f"cl-e{i * 2:04d}-001"
        role, aspect = "claim", ""
        if i == 3:
            role = "goal"
        if i == 5:
            aspect = "constraint"
        nodes[cid] = {"id": cid, "type": role, "aspect": aspect, "status": "active", "tense": "now",
                      "epistemic": "reported", "verbatim": f"pernyataan nomor {i} " + "x" * 80,
                      "triple": {"subject": {"label": f"s{i}"}, "predicate": {"label": "p"}}}
    snap = build_snapshot(graph={"nodes": nodes, "edges": {}}, goal=None, transcript=[("user", "hai")] * 10,
                          hypotheses={}, uncertainties=[], knowledge=[], requirement_states={}, budget_chars=3000)
    ids = set(snap["claim_ids"])
    check("anggaran dihormati & omisi dilaporkan", snap["selection"]["omitted"] > 0
          and snap["selection"]["used_chars"] <= 3000 and snap["selection"]["active_total"] == 60)
    check("klaim goal LAMA tetap ikut (bukan sekadar N terakhir)", "cl-e0006-001" in ids)
    check("klaim constraint LAMA tetap ikut", "cl-e0010-001" in ids)
    check("klaim terbaru ikut", "cl-e0120-001" in ids)
    again = build_snapshot(graph={"nodes": nodes, "edges": {}}, goal=None, transcript=[("user", "hai")] * 10,
                           hypotheses={}, uncertainties=[], knowledge=[], requirement_states={}, budget_chars=3000)
    check("snapshot deterministik (id sama untuk input sama)", snap["snapshot_id"] == again["snapshot_id"])

    # counter from PRESENTED steps + G5
    from app.navigation import asked_counts
    log = [{"decision": {"kind": "HOLD"}, "presented": {"kind": "QUESTION", "reason": {"need_id": "goal"}}},
           {"decision": {"kind": "HOLD"}, "presented": {"kind": "EVIDENCE_REQUEST", "reason": {"need_id": "goal"}}}]
    check("asked_counts membaca langkah yang disajikan", asked_counts(log) == {"goal": 2})
    from core.reasoning.guard import validate
    snapx = {"snapshot_id": "ss-1", "claim_ids": ["c"], "uncertainties": [
        {"id": "goal", "asked": 2, "askable": True}, {"id": "requirement:r", "asked": 0, "askable": False}]}
    graph = {"nodes": {"c": {"status": "active"}}}
    p = NextMoveProposal.model_validate(base_prop(snapx, focus_type="goal", proposed_focus="goal",
                                                  supporting_claim_refs=["c"]))
    g = validate(p, snapshot=snapx, graph=graph, hypotheses={}, knowledge_ids=set(), action_allowed=False)
    check("mengulang kebutuhan yang sudah ditanya cukup ditolak (G5)", not g.ok and any("G5" in v for v in g.violations))
    p2 = NextMoveProposal.model_validate(base_prop(snapx, proposed_focus="requirement:r", supporting_claim_refs=["c"]))
    g2 = validate(p2, snapshot=snapx, graph=graph, hypotheses={}, knowledge_ids=set(), action_allowed=False)
    check("kebutuhan yang hanya bisa digeser lewat aksi tidak ditanyakan (G4)",
          not g2.ok and any("tidak dapat dijawab" in v for v in g2.violations))


def test_candidates_and_failure_modes(tmp):
    print("C — kandidat ketidakpastian disusun dengan planner m4.v1 sendiri (bukan logika ganda)")
    from core.reasoning.uncertainties import candidate_uncertainties
    base = {"version": 1, "policy": "m4.v1", "lang": "id", "paths": [], "requirements": {}, "facts_missing": [],
            "signals": {}, "texts": {}, "history": {"asked": {}, "turn": 1}, "routes": [], "unresolved": [],
            "applicable": {}, "next_move_v1": None}
    inp = {**base, "goal": {"established": False, "code": "GOAL_NOT_ESTABLISHED", "signal": None},
           "texts": {"goal": {"reason": {"text": "tujuan?", "lang": "id"}}},
           "history": {"asked": {"goal": 1}, "turn": 1}}
    cands = {u["id"]: u for u in candidate_uncertainties(inp)}
    check("goal belum terbukti -> kandidat 'goal' (asked tercatat dari riwayat)",
          "goal" in cands and cands["goal"]["asked"] == 1, str(cands))
    inp["history"]["asked"]["goal"] = 2
    check("goal sudah ditanya ASK_CAP kali -> bukan kandidat", "goal" not in {u["id"] for u in candidate_uncertainties(inp)})
    facts = {**base, "goal": {"established": True}, "signals": {"state:x": "ASK", "state:y": "ACT"},
             "facts_missing": [
                 {"signal": "state:x", "text": {"text": "fakta x", "lang": "id"}, "needed_by": ["p1"], "source": "unresolved"},
                 {"signal": "state:y", "text": {"text": "fakta y", "lang": "id"}, "needed_by": ["p1"], "source": "unresolved"}]}
    c2 = {u["id"] for u in candidate_uncertainties(facts)}
    check("fakta yang dapat ditanya -> kandidat", "signal:state:x" in c2, str(c2))
    check("fakta yang hanya bisa lewat aksi (ACT) -> bukan kandidat", "signal:state:y" not in c2)
    check("goal terbukti -> tidak ditanyakan lagi", "goal" not in c2)
    check("enumerasi tidak mengubah input (deepcopy)", facts["history"]["asked"] == {})
    import copy
    snap_before = copy.deepcopy(facts)
    candidate_uncertainties(facts)
    check("enumerasi idempoten & bebas efek samping", snap_before == facts)


def test_kb_outage(tmp):
    print("G-16 — KB tidak tersedia: tanpa sitasi karangan, state tersimpan, keputusan jujur")
    import engine.applicable_knowledge as ak
    s, st, _, saved = sess(tmp, "kb-01")
    real = ak.retrieve
    try:
        def boom(*a, **k):
            raise RuntimeError("KB offline (injeksi)")
        import app.adaptive as adaptive_mod
        adaptive_mod.retrieve = boom

        def reasoner(snap, a):
            return base_prop(snap) if a > 1 else base_prop(snap, knowledge_refs=["TM-R01"])   # attempt 1: fake cite
        llm = ScriptedLLM([obs(claims=[cl("c1", "claim", "omzet", "is", "omzet saya 18 juta")])], reasoner)
        turn_mod.run_turn(s, llm, "omzet saya 18 juta")
        ad = s.planner_log[-1]["adaptive"]
        check("KB offline tercatat (kb_error) dan menu kosong — tidak ada pengetahuan yang bisa dikutip",
              ad["kb_error"] and ad["knowledge_offered"] == [] and ad["kb_version"] == "unavailable")
        check("sitasi pengetahuan karangan ditolak guard (G3), lalu repair tanpa sitasi diterima",
              llm.reasoning_calls == 2 and ad["status"] == "ACCEPTED"
              and any("G3" in v for v in ad["attempts"][0]["guard"]["violations"]))
        check("pesan mentah & state tetap utuh walau KB mati", len(s.state_graph["nodes"]) == 1
              and [e for e in s.events if e["role"] == "user"][0]["status"] == "committed"
              and presented(s)["reason"]["adaptive"]["knowledge_refs"] == [])
    finally:
        adaptive_mod.retrieve = real
        R._restore_real_env(st, saved)


def test_non_revenue_core(tmp):
    print("G-22 — contoh non-revenue (karier) berjalan di inti universal TANPA plugin revenue")
    import subprocess
    code = r'''
import sys
class Block:
    def find_spec(self, name, path=None, target=None):
        if name == "domains" or name.startswith("domains."):
            raise ImportError("domains diblokir: inti universal tidak boleh bergantung pada plugin domain")
sys.meta_path.insert(0, Block())
sys.path.insert(0, ".")
from types import SimpleNamespace
from core.semantic.contract import SemanticObservation, ObservedClaim
from core.semantic.commit import verify_and_commit
from core.reasoning.snapshot import build_snapshot
from core.reasoning.contract import NextMoveProposal
from core.reasoning.guard import validate
import store.events as ev
import tempfile, pathlib
ev.EVENTS_DIR = pathlib.Path(tempfile.mkdtemp())
s = SimpleNamespace(id="career-01", state_graph={"nodes": {}, "edges": {}}, events=[], transcript=[], goal=None,
                    graph_drift_reports=[])
e = ev.append_event(s, role="user", kind="message",
                    text="Saya ingin pindah dari engineer ke product manager tahun depan, tapi belum pernah memimpin tim.")
obs = SemanticObservation(contract_version="so.v1", language="id", claims=[
    ObservedClaim(ref="c1", role="goal", subject="saya", predicate="wants", tense="future",
                  quote="pindah dari engineer ke product manager tahun depan"),
    ObservedClaim(ref="c2", role="gap", subject="saya", predicate="has_not_led",
                  quote="belum pernah memimpin tim")], relations=[], uncertainties=[])
res = verify_and_commit(s, e, obs)
assert len(res.accepted_claims) == 2, res.rejections
snap = build_snapshot(graph=s.state_graph, goal=None, transcript=s.transcript, hypotheses={},
    uncertainties=[{"id": "x1", "asked": 0, "askable": True, "label": "pengalaman memimpin"}], knowledge=[],
    requirement_states={}, moves=[], paths=[])
p = NextMoveProposal(state_snapshot_ref=snap["snapshot_id"], proposed_move_kind="QUESTION", focus_type="uncertainty",
    proposed_focus="x1", move_text="Pengalaman apa yang paling dekat dengan memimpin, walau tanpa jabatan?",
    supporting_claim_refs=[res.accepted_claims[-1]["id"]])
g = validate(p, snapshot=snap, graph=s.state_graph, hypotheses={}, knowledge_ids=set(), action_allowed=False)
assert g.ok, g.violations
assert not any(m == "domains" or m.startswith("domains.") for m in sys.modules)
print("CORE_OK")
'''
    out = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True,
                         cwd=str(Path(__file__).resolve().parents[1]), timeout=60)
    check("karier: observasi → commit → snapshot → guard lulus tanpa satu pun modul `domains.*`",
          out.returncode == 0 and "CORE_OK" in out.stdout, (out.stderr or out.stdout)[-300:])


def test_knowledge_applicability(tmp):
    print("G-26 — kerangka pengetahuan yang berbeda tetap terpisah dan aktif bersyarat")
    from engine.applicable_knowledge import retrieve

    def g(*texts):
        return {"nodes": {f"cl-e0000-{i:03d}": {"id": f"cl-e0000-{i:03d}", "status": "active", "verbatim": t,
                                                "type": "claim"} for i, t in enumerate(texts, 1)}, "edges": {}}
    a = retrieve([], g("I will definitely buy, kalau bisa saya yakin akan laris, rencananya saya akan beli nanti, "
                       "tanpa bukti behavioral"), "")
    b = retrieve([], g("inquiry masuk dan banyak yang tanya, tetapi leads itu tidak ditindaklanjuti sama sekali setelah "
                       "pesan pertama, tidak ada subsequent action taken on interest"), "")
    c = retrieve([], g("cuaca hari ini cerah sekali"), "")
    sa, sb = {m["source"] for m in a["menu"]}, {m["source"] for m in b["menu"]}
    check("kerangka berbeda diaktifkan oleh ucapan yang berbeda (menu tidak sama)",
          bool(a["menu"]) and a["menu"] != b["menu"], f"{[m['id'] for m in a['menu']]} vs {[m['id'] for m in b['menu']]}")
    check("tiap butir membawa sumber (kerangka) dan anchor klaim", all(
        m["source"] and m["anchors"] for m in a["menu"] + b["menu"]))
    check("kerangka berbeda tetap terpisah: sumber yang aktif untuk ucapan A dan B tidak dilebur", bool(sb) and sa != sb,
          f"{sa} vs {sb}")
    check("ucapan tak relevan tidak mengaktifkan pengetahuan apa pun (aktif bersyarat)", c["menu"] == [])
    check("setiap butir menu dapat ditelusuri ke versi KB yang sama", a["kb_version"] == b["kb_version"] and a["kb_version"])


# ── H2: SC-09 — valid meaning survives beyond rejected steps ────────────

def test_hypothesis_survives_degraded(tmp):
    print("H2a — hipotesis valid DITERAPKAN meski Move ditolak guard (SC-09, OPEN-L1)")
    s, st, _, saved = sess(tmp, "h2a")

    def reasoner(snap, attempt):
        ids = snap["claim_ids"]
        return base_prop(snap, proposed_focus="bogus-tak-ada", competing_hypotheses=[{
            "statement": "akuisisi lemah vs tindak lanjut bocor", "supports": [ids[0]],
            "missing_evidence": ["jumlah inquiry mingguan"]}])

    llm = ScriptedLLM([obs(claims=[cl("c1", "assumption", "marketing", "is_weak",
                                      "kayaknya marketing saya lemah")])], reasoner)
    try:
        turn_mod.run_turn(s, llm, "kayaknya marketing saya lemah")
        ad = s.planner_log[-1]["adaptive"]
        check("Move memang DEGRADED (fokus tak dikenal, repair gagal)", ad["status"] == "DEGRADED")
        check("hipotesis valid TETAP diterapkan (bukan ikut dibuang)", len(s.hypotheses) == 1,
              str(list(s.hypotheses.values())[:1]))
        created = [c for c in ad.get("hypothesis_changes", []) if c.get("change") == "created"]
        check("jejak pembuatan hipotesis tercatat di planner_log", bool(created))
        check("presented = degraded jujur (bukan pertanyaan karangan)",
              "belum" in presented(s)["text"].lower() or presented(s)["kind"] == "HOLD",
              presented(s)["text"][:60])
    finally:
        R._restore_real_env(st, saved)


def test_invalid_hypothesis_dropped_not_fatal(tmp):
    print("H2b — SATU hipotesis tak valid dijatuhkan tercatat; Move TIDAK ikut mati (G9 non-fatal)")
    s, st, _, saved = sess(tmp, "h2b")

    def reasoner(snap, attempt):
        ids = snap["claim_ids"]
        return base_prop(snap, competing_hypotheses=[
            {"statement": "akuisisi lemah", "supports": [ids[0]], "missing_evidence": ["inquiry"]},
            {"statement": "hipotesis karangan", "supports": ["cl-tidak-ada-pernah"],
             "missing_evidence": ["x"]}])

    llm = ScriptedLLM([obs(claims=[cl("c1", "assumption", "marketing", "is_weak",
                                      "kayaknya marketing saya lemah")])], reasoner)
    try:
        turn_mod.run_turn(s, llm, "kayaknya marketing saya lemah")
        ad = s.planner_log[-1]["adaptive"]
        check("Move tetap ACCEPTED (pelanggaran hipotesis tidak mematikan langkah)",
              ad["status"] == "ACCEPTED", str(ad.get("reason")))
        check("hanya hipotesis VALID yang masuk session", len(s.hypotheses) == 1)
        dropped = ad.get("hypothesis_dropped") or []
        check("hipotesis tak valid dicatat alasannya (tidak hilang diam-diam)",
              len(dropped) == 1 and "cl-tidak-ada-pernah" in dropped[0], str(dropped))
    finally:
        R._restore_real_env(st, saved)


def test_repair_prompt_targeted():
    print("H2c — repair structured_call TERARAH: path field + nilai ditolak + pilihan enum (OPEN-L3 tahap-2)")
    import typing

    from pydantic import BaseModel

    from core.llm import LLMProvider

    class Inner(BaseModel):
        kind: typing.Literal["related_to", "supports"]

    class Outer(BaseModel):
        items: list[Inner]

    prompts = []

    class P(LLMProvider):
        name = "fake"

        def raw_json(self, system, user):
            prompts.append(user)
            if len(prompts) == 1:
                return json.dumps({"items": [{"kind": "causes"}]})
            return json.dumps({"items": [{"kind": "supports"}]})

    p = P()
    out = p.structured_call(Outer, "sys", "items", retries=1)
    check("retry kedua menghasilkan objek valid", out.items[0].kind == "supports")
    repair = prompts[1]
    check("repair menyebut PATH field bersarang (items.0.kind)", "items.0.kind" in repair)
    check("repair menyebut nilai yang ditolak", "'causes'" in repair)
    check("repair menyebut pilihan enum sah", "related_to" in repair and "supports" in repair)


def test_loose_normalize_quantity_period_none():
    print("H2e — quantity.period=None dinormalisasi ke default kontrak (OPEN-L3, golden iter-2 rep3)")
    import json as _json

    from core.llm import LLMProvider
    from core.semantic.contract import SemanticObservation

    raw = _json.dumps({"contract_version": "so.v1", "language": "id", "claims": [
        {"ref": "c1", "role": "claim", "subject": "omzet", "predicate": "sekitar",
         "quote": "sekitar 12 juta", "tense": "now",
         "quantity": {"value_kind": "exact", "value": 12, "unit": "juta", "period": None}}],
        "relations": [], "uncertainties": []})

    class P(LLMProvider):
        name = "fake"
        calls = 0

        def raw_json(self, system, user):
            P.calls += 1
            return raw

    out = P().structured_call(SemanticObservation, "s", "u", retries=1)
    check("period None -> default 'unspecified' TANPA retry penuh",
          P.calls == 1 and out.claims[0].quantity.period == "unspecified",
          f"calls={P.calls} period={out.claims[0].quantity.period!r}")


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="nvl-r5-"))
    test_knowledge_delivery(tmp / "k")
    test_hypothesis_revision(tmp / "h")
    test_hypothesis_survives_degraded(tmp / "h2a")
    test_invalid_hypothesis_dropped_not_fatal(tmp / "h2b")
    test_repair_prompt_targeted()
    test_loose_normalize_quantity_period_none()
    test_guard(tmp / "g")
    test_repair_and_failure(tmp / "r")
    test_long_context_and_counters(tmp / "l")
    test_candidates_and_failure_modes(tmp / "c")
    test_kb_outage(tmp / "kb")
    test_non_revenue_core(tmp / "nr")
    test_knowledge_applicability(tmp / "ka")
    print()
    print(f"HASIL R5: {_PASS}/{_PASS + _FAIL} PASS (DETERMINISTIC_PASS; LIVE_NOT_RUN)" + (" ✅" if _FAIL == 0 else " ❌"))
    return 0 if _FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
