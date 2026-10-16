"""R4 — Goal, domain projections & admissibility: canonical claim -> Goal / RevenueState /
EvidenceCandidate -> single adjudicator.

Tests the INTEGRATED PATH (run_turn -> graph -> projection -> live adjudication -> ledger), not isolated
functions, with a controlled FakeLLM (the semantic truth of the real model is tested in R7; what is tested
here is the deterministic contract BELOW the model):

  1  A desire without numbers yields no fabricated target/revenue
  2  Tentative goal clarification -> explicit confirmation
  3  Goal switch: new tentative target, old value not restored, version bumps
  4  An estimated revenue does not become a definite / transactional figure
  5  A range does not become a number (regex does not restore it)
  6  Upper/lower bounds do not become an exact figure
  7  Historical vs current revenue
  8  Personal salary is not business revenue
  9  Non-revenue story: no fabricated domain fields
  10-12 ICP: paraphrase without the formal keywords / with valid evidence / insufficient (no false PRESENT)
  13 A superseded claim -> leaves evaluation; the ledger does not stay PRESENT; history intact
  14 Multiple Goals: isolated
  15 A requirement without a formal rule: stays UNKNOWN by absence
  16 Source grade is not promoted; assumptions/desires are not admissible
  17 Candidate metadata: claim/event/goal id+version preserved
Run: .venv/bin/python evals/test_recovery_goal_admissibility.py  (deterministic, no network)
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # mvp/
sys.path.insert(0, str(Path(__file__).resolve().parent))      # evals/

from evals._store_isolation import isolate_store  # noqa: E402

isolate_store()  # eval: store redirected to tmp — production store untouched

import test_recovery_semantic as R  # noqa: E402

import store.adjudication_ledger as ledger  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="nvl-r4-"))
ledger._LEDGER_ROOT = _TMP / "ledger"

import app.turn as turn_mod  # noqa: E402
from core.schema.evidence import current_evidence  # noqa: E402
from domains.revenue.navigation.live import derive_revenue_state  # noqa: E402
from domains.revenue.projection.view import build_revenue_view  # noqa: E402
from domains.revenue.schema.goal import Goal, build_goal  # noqa: E402
from domains.revenue.schema.goal_projection import project_goal  # noqa: E402
from ontology.mapper.live_adjudication import run_live_adjudication  # noqa: E402

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


cl, obs, qty = R.cl, R.obs, R.qty


def new_session(tmp: Path, sid: str, *, desire: str = "", user_id: str = ""):
    st, sess_dir, saved, Session = R._real_env(tmp)
    s = Session(id=sid, goal_text=desire or "saya ingin bisnis lebih baik", language="id", user_id=user_id)
    s.goal = build_goal(s.goal_text, desire=desire).model_dump()
    return s, st, saved


def say(s, llm, text):
    return turn_mod.run_turn(s, llm, text)


def state_of(s):
    utext = "\n".join(f"user: {t}" for r, t in s.transcript if r == "user")
    return derive_revenue_state(current_evidence(s.evidence), s.goal_text, utext, s.state_graph)


# ── 1 ─ 9: Goal & revenue projections ───────────────────────────────────────────

def test_goal_semantics(tmp: Path):
    print("1-3 — Desire, klarifikasi, konfirmasi, pergantian Goal")
    s, st, saved = new_session(tmp, "g-01", desire="Saya ingin punya lebih banyak waktu untuk keluarga")
    try:
        llm = R.FakeLLM([
            obs(claims=[cl("c1", "desire", "saya", "wants", "Saya ingin punya lebih banyak waktu untuk keluarga",
                           tense="future")]),
            obs(claims=[cl("c1", "goal", "omzet", "target", "target omzet 25 juta per bulan", tense="future",
                           quantity=qty(value_kind="exact", value=25, unit="juta", period="monthly"))]),
            obs(claims=[cl("c1", "goal", "omzet", "target", "ya, 25 juta itu target saya",
                           tense="future", supersedes="cl-e0002-001", revision_kind="confirmation",
                           revision_reason="user mengonfirmasi")]),
            obs(claims=[cl("c1", "goal", "omzet", "target", "ralat, targetnya 40 juta per bulan", tense="future",
                           quantity=qty(value_kind="exact", value=40, unit="juta", period="monthly"),
                           supersedes="cl-e0002-001", revision_kind="correction", revision_reason="ganti target")]),
        ])
        say(s, llm, "Saya ingin punya lebih banyak waktu untuk keluarga")
        g = Goal(**s.goal)
        check("1: desire tidak menciptakan target", g.target is None and g.target_origin == "none", str(g.target))
        check("1: desire tercatat sebagai desire (bukan motivation/target)", "keluarga" in g.desire and not g.motivation)
        check("1: tidak ada angka revenue karangan di proyeksi",
              not build_revenue_view(s.state_graph)["fields"])
        rs = state_of(s)
        check("1: RevenueState tidak punya angka karangan", rs.current_monthly is None and rs.target_monthly is None)

        say(s, llm, "target omzet 25 juta per bulan")
        g = Goal(**s.goal)
        check("2: target dari klaim kanonik bertipe", g.target == 25.0 and g.target_claim_id == "cl-e0002-001")
        check("2: tentatif sampai dikonfirmasi", g.target_origin == "intent_phrase" and not g.confirmed_target())
        v_tentative = g.version
        say(s, llm, "ya, 25 juta itu target saya")
        g = Goal(**s.goal)
        check("2: konfirmasi eksplisit -> terkonfirmasi", g.confirmed_target() and g.target == 25.0, g.target_origin)

        say(s, llm, "ralat, targetnya 40 juta per bulan")
        g = Goal(**s.goal)
        check("3: pergantian goal -> target baru", g.target == 40.0, str(g.target))
        check("3: target baru tentatif lagi (konfirmasi lama tak diwariskan)",
              g.target_origin == "intent_phrase" and not g.confirmed_target())
        check("3: versi goal naik", g.version > v_tentative, f"{g.version} vs {v_tentative}")
        check("3: nilai lama tidak dipulihkan dari goal_text/transcript", state_of(s).target_monthly in (40.0, None))
    finally:
        R._restore_real_env(st, saved)


def test_quantities_and_roles(tmp: Path):
    print("4-8 — perkiraan, rentang, batas, historis, gaji pribadi")
    s, st, saved = new_session(tmp, "q-01")
    try:
        llm = R.FakeLLM([
            obs(claims=[cl("c1", "claim", "omzet", "currently", "omzet sekarang sekitar 18 juta", hedge=True,
                           epistemic="estimated", tense="now",
                           quantity=qty(value_kind="approximate", value=18, unit="juta", period="monthly")),
                        cl("c2", "claim", "omzet", "was", "dulu omzet 30 juta", tense="past",
                           quantity=qty(value_kind="exact", value=30, unit="juta", period="monthly"))]),
        ])
        say(s, llm, "omzet sekarang sekitar 18 juta, dulu omzet 30 juta")
        view = build_revenue_view(s.state_graph)
        cur = view["fields"].get("current_revenue") or {}
        check("4: omzet perkiraan terpetakan sebagai perkiraan (precision approximate)",
              cur.get("value") == 18 and cur.get("precision") == "approximate", str(cur))
        rs = state_of(s)
        check("4: RevenueState membawa precision/epistemic, bukan 'pasti'",
              rs.sources["current_monthly"].get("precision") == "approximate"
              and rs.sources["current_monthly"].get("epistemic") == "estimated", str(rs.sources.get("current_monthly")))
        check("4: evidence turunan tetap self_reported (tidak jadi transaksional)",
              all(e.level == "self_reported" for e in s.evidence))
        check("7: historis 30 tidak menjadi current", rs.current_monthly == 18.0, str(rs.current_monthly))
    finally:
        R._restore_real_env(st, saved)

    s, st, saved = new_session(tmp / "b", "q-02")
    try:
        llm = R.FakeLLM([obs(claims=[
            cl("c1", "claim", "omzet", "is", "omzet kira-kira 10 sampai 20 juta", tense="now",
               quantity=qty(value_kind="range", low=10, high=20, unit="juta", period="monthly"))])])
        say(s, llm, "omzet kira-kira 10 sampai 20 juta")
        rs = state_of(s)
        check("5: rentang tidak menjadi angka (regex tidak memulihkan)", rs.current_monthly is None,
              str(rs.current_monthly))
        check("5: makna rentang tetap utuh di graph",
              any((n.get("quantity") or {}).get("value_kind") == "range" for n in s.state_graph["nodes"].values()))
    finally:
        R._restore_real_env(st, saved)

    s, st, saved = new_session(tmp / "c", "q-03")
    try:
        llm = R.FakeLLM([obs(claims=[
            cl("c1", "claim", "omzet", "is", "omzet paling banyak 5 juta", tense="now",
               quantity=qty(value_kind="at_most", value=5, unit="juta", period="monthly")),
            cl("c2", "goal", "omzet", "target", "target omzet minimal 30 juta", tense="future",
               quantity=qty(value_kind="at_least", value=30, unit="juta", period="monthly"))])])
        say(s, llm, "omzet paling banyak 5 juta, target omzet minimal 30 juta")
        rs = state_of(s)
        g = Goal(**s.goal)
        check("6: batas atas bukan angka eksak current", rs.current_monthly is None, str(rs.current_monthly))
        check("6: batas bawah goal -> target_min saja, target eksak kosong",
              g.target is None and g.target_min == 30.0 and g.target_precision == "lower_bound",
              f"{g.target},{g.target_min},{g.target_precision}")
    finally:
        R._restore_real_env(st, saved)

    s, st, saved = new_session(tmp / "d", "q-04")
    try:
        llm = R.FakeLLM([
            obs(claims=[cl("c1", "claim", "penghasilan", "is", "penghasilan saya dari gaji 10 juta", tense="now",
                           quantity=qty(value_kind="exact", value=10, unit="juta", period="monthly"))]),
            obs(claims=[cl("c1", "claim", "omzet", "is", "omzet usaha 40 juta", tense="now",
                           quantity=qty(value_kind="exact", value=40, unit="juta", period="monthly"))]),
        ])
        say(s, llm, "penghasilan saya dari gaji 10 juta")
        check("8: gaji pribadi bukan omzet usaha", state_of(s).current_monthly is None,
              str(state_of(s).current_monthly))
        say(s, llm, "omzet usaha 40 juta")
        check("8: omzet usaha tetap terbaca", state_of(s).current_monthly == 40.0, str(state_of(s).current_monthly))
    finally:
        R._restore_real_env(st, saved)

    s, st, saved = new_session(tmp / "e", "q-05", desire="saya ingin hidup lebih tenang")
    try:
        llm = R.FakeLLM([obs(claims=[
            cl("c1", "claim", "saya", "feels", "belakangan saya kelelahan dan jarang bertemu teman", aspect="concern"),
            cl("c2", "desire", "saya", "wants", "saya ingin hidup lebih tenang", tense="future")])])
        say(s, llm, "belakangan saya kelelahan dan jarang bertemu teman, saya ingin hidup lebih tenang")
        rs = state_of(s)
        check("9: cerita non-revenue tersimpan utuh di graph", len(s.state_graph["nodes"]) == 2)
        check("9: tanpa field domain karangan",
              rs.current_monthly is None and rs.target_monthly is None and rs.avg_deal_size is None
              and Goal(**s.goal).target is None)
    finally:
        R._restore_real_env(st, saved)


# ── 10-17: admissibility & adjudikator tunggal ───────────────────────────────

ICP_OK = "ICP tertulis berisi jenis usaha, level, dan peran pembeli."
ICP_PARAPHRASE = "Kami menyasar pemilik klinik gigi di Surabaya yang baru buka cabang kedua."


def adjudicate(s, user):
    return run_live_adjudication(user, s.evidence, goal=s.goal, session_id=s.id, graph=s.state_graph, now=100)


def status_of(user, rid):
    e = ledger.latest_entry(user, rid)
    return e["adjudication"]["status"] if e else None


def test_admissibility(tmp: Path):
    print("10-13, 15-17 — EvidenceCandidate, admissibility, adjudikator tunggal, invalidasi")
    user = "u-r4-a"
    s, st, saved = new_session(tmp, "a-01", user_id="")   # empty user: the turn path does not touch ledger
    try:
        llm = R.FakeLLM([
            obs(claims=[cl("c1", "claim", "tim", "targets", ICP_PARAPHRASE, tense="now")]),
            obs(claims=[cl("c1", "claim", "icp", "documented", ICP_OK, tense="now")]),
            obs(claims=[cl("c1", "assumption", "icp", "documented", "mungkin " + ICP_OK, tense="now")]),
        ])
        s.goal.update({"goal_id": "goal-A", "version": 3})
        say(s, llm, ICP_PARAPHRASE)
        out = adjudicate(s, user)
        icp_c = [c for c in out["candidates"] if c["source_quote"] == ICP_PARAPHRASE]
        check("10: parafrase dikenali secara semantik (kandidat tercatat)", bool(icp_c))
        check("10: parafrase tanpa kata kunci formal tidak memuaskan requirement",
              status_of(user, "access.icp") != "PRESENT", str(status_of(user, "access.icp")))
        check("10: dikenali != admissible != memuaskan (tidak ada verdict ADMITTED untuk access.icp)",
              not any(c["admissibility_verdict"] == "ADMITTED" and c["requirement_id"] == "access.icp"
                      for c in icp_c))

        say(s, llm, ICP_OK)
        out = adjudicate(s, user)
        check("11: bukti sah -> ADMITTED -> adjudikator formal -> PRESENT",
              status_of(user, "access.icp") == "PRESENT"
              and any(c["admissibility_verdict"] == "ADMITTED" and c["requirement_id"] == "access.icp"
                      for c in out["candidates"]), str(status_of(user, "access.icp")))
        lines_before = ledger.latest_entry(user, "access.icp")["entry_id"]

        # 13 a superseded claim -> evaluation no longer uses it; the ledger does not stay PRESENT;
        # history intact
        llm2 = R.FakeLLM([obs(claims=[cl("c1", "claim", "dokumen", "is", "ralat: sebenarnya dokumen itu belum ada",
                                         tense="now", supersedes="cl-e0002-001", revision_kind="correction",
                                         revision_reason="koreksi")])])
        say(s, llm2, "ralat: sebenarnya dokumen itu belum ada")
        out = adjudicate(s, user)
        check("13: klaim digantikan ditandai tidak berlaku di evidence", any(e.superseded for e in s.evidence))
        check("13: ledger tidak terus menyatakan PRESENT", status_of(user, "access.icp") != "PRESENT",
              str(status_of(user, "access.icp")))
        check("13: invalidasi tercatat transparan",
              any(i["requirement_id"] == "access.icp" and i["was"] == "PRESENT" for i in out["invalidated"]),
              str(out["invalidated"]))
        f = ledger._LEDGER_ROOT / user / "adjudication_ledger.jsonl"
        import json as _json
        rows = [_json.loads(x) for x in f.read_text().splitlines() if x.strip()]
        icp_rows = [r["adjudication"]["status"] for r in rows if r["adjudication"]["requirement_id"] == "access.icp"]
        check("13: sejarah PRESENT tidak dihapus (append-only); entri terakhir bukan PRESENT",
              icp_rows[0] == "PRESENT" and icp_rows[-1] != "PRESENT" and lines_before in f.read_text(),
              str(icp_rows))

        # 16 assumptions/desires are not admissible; the grade is not promoted
        s2, st2, saved2 = new_session(tmp / "z", "a-02")
        try:
            say(s2, llm2.__class__([obs(claims=[cl("c1", "assumption", "icp", "documented", "mungkin " + ICP_OK)])]),
                "mungkin " + ICP_OK)
            out2 = adjudicate(s2, "u-r4-assump")
            check("16: asumsi dikenali tetapi NOT_ADMISSIBLE",
                  any(c["admissibility_verdict"] == "NOT_ADMISSIBLE" and c["semantic_role"] == "assumption"
                      for c in out2["candidates"]), str(out2["candidates"]))
            check("16: asumsi tidak memuaskan requirement", status_of("u-r4-assump", "access.icp") is None)
        finally:
            R._restore_real_env(st2, saved2)

        llm3 = R.FakeLLM([obs(claims=[cl("c1", "claim", "omzet", "is", "omzet saya 18 juta",
                                         epistemic="measured", tense="now",
                                         quantity=qty(value_kind="exact", value=18, unit="juta", period="monthly"))])])
        say(s, llm3, "omzet saya 18 juta")
        out = adjudicate(s, user)
        meas = [c for c in out["candidates"] if c["source_quote"] == "omzet saya 18 juta"]
        check("16: grade measured (kesaksian) tidak dipromosikan menjadi transaksional",
              meas and all(e.level == "self_reported" for e in s.evidence if e.source_quote == "omzet saya 18 juta")
              and meas[0]["epistemic_grade"] == "measured" and meas[0]["evidence_level"] == "self_reported",
              str(meas[:1]))
        c0 = meas[0]
        check("17: kandidat membawa claim/event/goal id+versi",
              c0["canonical_claim_id"].startswith("cl-e") and c0["source_event_id"].startswith("ce-a-01")
              and c0["goal_id"] == "goal-A" and c0["goal_version"] == 3 and c0["scope"]["session_id"] == "a-01",
              str({k: c0[k] for k in ("canonical_claim_id", "source_event_id", "goal_id", "goal_version")}))
        formal_only = {"access.icp"}
        check("15: requirement tanpa rule formal tidak pernah diadjudikasi (UNKNOWN by absence)",
              all(a["requirement_id"] != "revenue.current" for a in out["adjudicated"])
              and ledger.latest_entry(user, "revenue.current") is None
              and {"access.icp"} == formal_only)
        check("15: kandidat tanpa usulan tetap RECOGNIZED_ONLY / UNRESOLVED, bukan ADMITTED",
              all(c["admissibility_verdict"] != "ADMITTED" for c in meas), str(meas[:1]))
    finally:
        R._restore_real_env(st, saved)


def test_goal_isolation():
    print("14 — beberapa Goal: perubahan A tidak menyentuh B")
    ga = build_goal("goal A", desire="goal A", goal_id="goal-A").model_dump()
    gb = build_goal("goal B", desire="goal B", goal_id="goal-B", target=10.0, metric_id="revenue_monthly",
                    direction="INCREASE_TO_THRESHOLD", category="revenue").model_dump()
    gb_before = dict(gb)
    graph = {"nodes": {"cl-e0000-001": {
        "id": "cl-e0000-001", "type": "goal", "status": "active", "version": 1, "tense": "future",
        "verbatim": "target omzet 50 juta per bulan",
        "triple": {"subject": {"label": "omzet"}, "predicate": {"label": "target"}},
        "quantity": {"value_kind": "exact", "value": 50, "unit": "juta", "period": "monthly"},
        "provenance": {"event_id": "ce-x-0000", "session": "x"}}}, "edges": {}}
    new_a, ch = project_goal(ga, graph)
    check("14: Goal A berubah dari klaimnya", new_a["target"] == 50.0 and ch)
    check("14: Goal B (dict terpisah) tak tersentuh", gb == gb_before)
    new_a2, ch2 = project_goal(new_a, graph)
    check("14: proyeksi idempoten (tanpa kenaikan versi ganda)", not ch2 and new_a2["version"] == new_a["version"])
    graph["nodes"]["cl-e0000-001"]["confirmed_by"] = ["cl-e0001-001"]
    new_a3, _ = project_goal(new_a2, graph)
    check("14: konfirmasi mengubah origin tanpa mengubah goal lain",
          new_a3["target_origin"] == "explicit_input" and gb == gb_before)
    api_goal = build_goal("x", desire="x", target=99.0, goal_id="goal-C").model_dump()
    new_c, _ = project_goal(api_goal, graph)
    check("14: input eksplisit API tidak ditimpa klaim", new_c["target"] == 99.0)


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="nvl-r4t-"))
    test_goal_semantics(tmp / "1")
    test_quantities_and_roles(tmp / "2")
    test_admissibility(tmp / "3")
    test_goal_isolation()
    print()
    print(f"HASIL R4: {_PASS}/{_PASS + _FAIL} PASS" + (" ✅" if _FAIL == 0 else " ❌"))
    return 0 if _FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
