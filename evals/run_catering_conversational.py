"""MC02-RC-04 (B) — CONVERSATIONAL catering replay (audit RC-04).

Unlike the evidence-injection replay (8 fixed messages), this runner runs a CONVERSATION: a rich
opening story, then user answers that FOLLOW the model's ACTUAL questions. Answers are pulled from
the original incident fact map (`catering_conversational_v1.json`) via keyword routing; when a
question maps to nothing, the honest "not recorded / not measured" answer is used and RECORDED as a
simulator limitation (`simulator_limits`) — no business numbers are invented just to make the
fixture pass.

Diagnostic quality evaluation (10 mandatory items from audit RC-04) is presented as a quantitative
summary + corpus checks of the same types as the injection replay. DEGRADED recovery uses the
RC-02 pattern: an IMMEDIATE retry on the failing turn, with the exactly-once invariant tested
in place.

Usage: .venv/bin/python evals/run_catering_conversational.py [--provider vertex] [--max-turns 6]
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

import app.main as app_main  # noqa: E402
import evals.run_live_golden as G  # noqa: F401,E402  (the import joins the golden runner's store isolation)
from core.llm import NORM_STATS  # noqa: E402
from evals.run_live_golden import build_llm, run_check  # noqa: E402
from store.memory import store  # noqa: E402

CORPUS = json.loads((Path(__file__).resolve().parent / "golden"
                     / "catering_conversational_v1.json").read_text())


def _kw_hits(q: str, matches: list[str]) -> list[str]:
    """Keywords matched inside question q.

    Length > 3: plain substring (Indonesian affixes, e.g. 'balas' inside 'balasannya').
    Length <= 3: word boundary REQUIRED, so generic short tokens ('wa', '25', 'ads', 'log') do not
    match inside other words ('wa' inside 'warna'/'waktu', '25' inside '250')."""
    hits: list[str] = []
    for k in matches:
        if len(k) <= 3:
            if re.search(r"\b" + re.escape(k) + r"\b", q):
                hits.append(k)
        elif k in q:
            hits.append(k)
    return hits


def _route(question: str, facts: list[dict]) -> tuple[str, str]:
    """Pick the fact most relevant to the model's question.

    Rule: the LONGEST keyword match (most specific) wins; ties -> fact order (priority stays
    deterministic); short tokens require word boundaries. Prevents generic short keywords
    ('tanya', 'catatan', 'wa', '25') from STEALING a question that is really about another fact
    (e.g. 'boleh saya tanya soal komposisi pendapatan' must -> revenue_composition, not
    inquiries_ref; 'warna biru' must NOT -> records via 'wa')."""
    q = (question or "").lower()
    best: tuple[int, int, str, str] | None = None
    for i, f in enumerate(facts):
        hits = _kw_hits(q, f["match"])
        if not hits:
            continue
        score = max(len(k) for k in hits)
        if best is None or score > best[0]:
            best = (score, i, f["key"], f["answer"])
    if best is None:
        return "SIMULATOR_LIMIT", CORPUS["answer_default"]
    return best[2], best[3]


def _counts(s) -> dict:
    moves = list(getattr(s, "moves", None) or [])
    return {"user_events": sum(1 for e in s.events if e.get("role") == "user"),
            "engine_events": sum(1 for e in s.events if e.get("role") == "engine"),
            "claims": len((s.state_graph or {}).get("nodes") or {}),
            "evidence": len(s.evidence), "moves": len(moves),
            "outcomes": sum(1 for m in moves if m.get("lifecycle") == "OBSERVED")}


def main() -> int:
    argv = sys.argv[1:]
    provider = argv[argv.index("--provider") + 1] if "--provider" in argv else "vertex"
    max_turns = int(argv[argv.index("--max-turns") + 1]) if "--max-turns" in argv else 6
    llm = build_llm(provider)
    if llm.name == "mock":
        print("Menolak: provider mock bukan bukti LIVE.")
        return 2
    llm.set_determinism(True)
    app_main.get_llm = lambda: llm
    # raise_server_exceptions=False: server failures are recorded as honest HTTP statuses
    # (RC-04 finding: a semantic comprehension failure can produce a 500 — the runner must
    # REPORT it as a failure, not crash mid-replay).
    client = TestClient(app_main.app, raise_server_exceptions=False)

    stats_before = dict(NORM_STATS)
    print(f"replay CONVERSATIONAL · provider={llm.name} model={getattr(llm, 'model', '?')} "
          f"· corpus={CORPUS['corpus_version']} · max_turns={max_turns}")

    t0 = time.time()
    opening = CORPUS["opening"]
    r0 = client.post("/session", json={"goal_text": opening[0], "language": "id",
                                       "user_id": "u-catering-conv-1"})
    if r0.status_code != 200:
        print("gagal membuat sesi:", r0.status_code, r0.text[:200])
        return 2
    sid = r0.json()["session_id"]
    s = store.get(sid)
    moves = [{"turn": 1, "user": opening[0], "kind": "QUESTION",
              "text": r0.json().get("first_question"),
              "presented": {"kind": "QUESTION", "text": r0.json().get("first_question")},
              "adaptive": None, "source": "opening"}]
    answers: list[dict] = []
    recoveries: list[dict] = []
    violations: list[str] = []
    user_events_series: list[int] = []

    # the rest of the opening story is sent as subsequent user messages (the user is telling
    # their story, not answering a question)
    scripted = list(opening[1:])
    for _ in range(max_turns):
        if scripted:
            text, fk, src = scripted.pop(0), "OPENING_STORY", "opening"
        else:
            last = moves[-1]
            if last["kind"] not in ("QUESTION", "EVIDENCE_REQUEST"):
                break
            fk, ans = _route(last["text"], CORPUS["facts"])
            text = ans if fk != "SIMULATOR_LIMIT" else CORPUS["answer_default"]
            src = "fact_map" if fk != "SIMULATOR_LIMIT" else "SIMULATOR_LIMIT"
        answers.append({"turn": len(moves) + 1, "fact": fk, "source": src, "text": text[:120]})
        m = client.post(f"/session/{sid}/message", json={"text": text})
        if m.status_code != 200:
            violations.append(f"giliran {len(moves) + 1}: HTTP {m.status_code} "
                              f"({m.text[:120]})")
            print(f"  !! giliran {len(moves) + 1} GAGAL HTTP {m.status_code}: {m.text[:140]}")
            break
        j = m.json()
        s = store.get(sid)
        mv = j.get("next_move") or {}
        # source marks the answer's provenance (opening scripted vs fact_map AQ vs SIMULATOR_LIMIT) —
        # the opening message must NOT be credited as an adaptive answer.
        moves.append({"turn": len(moves) + 1, "user": text, "kind": mv.get("kind"),
                      "text": mv.get("text"), "source": src,
                      "presented": mv, "adaptive": "ACCEPTED" if not mv.get("degraded") else "DEGRADED"})
        if mv.get("degraded"):
            before = _counts(s)
            rr = client.post(f"/session/{sid}/retry_reasoning", json={})
            j2 = rr.json() if rr.status_code == 200 else {}
            nm = j2.get("next_move") or {}
            s = store.get(sid)
            after = _counts(s)
            drifted = {k: [before[k], after[k]] for k in before
                       if k != "engine_events" and before[k] != after[k]}
            if drifted:
                violations.append(f"giliran {len(moves)}: {drifted}")
            if after["engine_events"] != before["engine_events"] + 1:
                violations.append(f"giliran {len(moves)}: engine_events tidak +1")
            user_events_series.append(after["user_events"])
            rec = {"turn": len(moves), "http": rr.status_code,
                   "still_degraded": bool(nm.get("degraded")), "kind": nm.get("kind", ""),
                   "before": before, "after": after}
            recoveries.append(rec)
            print(f"  T{rec['turn']} DEGRADED → retry SEGERA: HTTP {rr.status_code} "
                  f"still_degraded={rec['still_degraded']}")
            if rr.status_code == 200 and not rec["still_degraded"]:
                moves[-1]["kind"] = nm.get("kind")
                moves[-1]["text"] = nm.get("text")
                moves[-1]["presented"] = nm
                moves[-1]["adaptive"] = "ACCEPTED"
                moves[-1]["recovered"] = True
            else:
                moves[-1]["recovered"] = False
                break
        print(f"  T{len(moves)} [{mv.get('kind')}] {(mv.get('text') or '')[:90]}")
    secs = round(time.time() - t0, 1)
    s = store.get(sid)

    # ── diagnostic quality (10 mandatory items from audit RC-04) ──
    asked = [m for m in moves[1:] if m["kind"] in ("QUESTION", "EVIDENCE_REQUEST")]
    fact_answers = [a for a in answers if a["source"] == "fact_map"]
    answered_turns = [a for a in answers if a["source"] in ("fact_map", "SIMULATOR_LIMIT")]
    limits = [a for a in answers if a["source"] == "SIMULATOR_LIMIT"]
    hyps = [h["statement"] for h in (getattr(s, "hypotheses", None) or {}).values()
            if h.get("status") != "retired"]
    hyps_l = " || ".join(h.lower() for h in hyps)
    plag = {"followup_hypothesis": any(k in hyps_l for k in
                                       ("tindak lanjut", "balas", "respons", "follow", "lambat")),
            "ads_separated": any(k in hyps_l for k in ("asumsi", "iklan")),
            "capacity_or_referral_kept_open": any(k in hyps_l for k in
                                                  ("kapasitas", "referensi", "permintaan", "demand")),
            "premature_hold": any(m["kind"] == "HOLD" for m in moves),
            "grounded_answer_ratio": (round(len(fact_answers) / len(answered_turns), 2)
                                      if answered_turns else 0.0)}
    results, n_ok = [], 0
    for ck in CORPUS["checks"]:
        try:
            ok, detail = run_check(ck, s, moves, {})
        except Exception as exc:  # noqa: BLE001
            ok, detail = False, f"cek error {type(exc).__name__}: {exc}"
        results.append({"dim": ck["dim"], "type": ck["type"], "ok": bool(ok),
                        "detail": str(detail)[:200]})
        n_ok += bool(ok)
        print(f"  {'OK ' if ok else 'XX '} [{ck['dim']}] {ck['type']}"
              + ("" if ok else f" — {detail}"[:110]))
    stats_after = {k: v - stats_before.get(k, 0)
                   for k, v in NORM_STATS.items() if v != stats_before.get(k, 0)}
    turn_timing = [e.get("timing") for e in s.planner_log if e.get("timing")]
    # S1: every per-stage span is printed as-is (including navigation_s/reasoner_s/second_pass_s/
    # persist_s/request_total_s) so latency denominators can be split /session vs /message.
    print("timing per giliran (detik dinding): " + json.dumps(turn_timing))
    unrecovered = [r for r in recoveries if r["still_degraded"]]
    out_dir = Path(__file__).resolve().parents[1] / "traces" / "live"
    out_dir.mkdir(parents=True, exist_ok=True)
    fp = out_dir / f"catering-conversational-{int(time.time())}.json"
    fp.write_text(json.dumps({
        "corpus": CORPUS["corpus_version"], "provider": llm.name,
        "model": getattr(llm, "model", ""), "ts_wib": time.strftime("%Y-%m-%d %H:%M:%S"),
        "secs": secs, "sid": sid, "moves": moves, "answers": answers,
        "quality": plag, "hypotheses": hyps, "checks": results,
        "checks_passed": n_ok, "checks_total": len(results),
        "recoveries": recoveries, "invariant_violations": violations,
        "unrecovered_degraded": len(unrecovered),
        "simulator_limits": [a["turn"] for a in limits],
        "turn_timing": turn_timing,
        "norm_stats_delta": stats_after,
    }, ensure_ascii=False, indent=1))
    ok_all = n_ok == len(results) and not violations and not unrecovered
    print(f"\nkualitas: {json.dumps(plag, ensure_ascii=False)}")
    print(f"pertanyaan diajukan={len(asked)} · jawaban dari peta fakta={len(fact_answers)}"
          f"/{len(answered_turns)} · simulator_limit={len(limits)} · hipotesis={len(hyps)}")
    print(f"hasil: {n_ok}/{len(results)} checks · retry={len(recoveries)} "
          f"· gagal-pulih={len(unrecovered)} · pelanggaran={len(violations)} · {secs}s · {fp}")
    try:
        store.sessions.pop(sid, None)
    except Exception:  # noqa: BLE001
        pass
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
