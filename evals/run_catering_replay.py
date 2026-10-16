"""MC01-6 — EXACT catering incident replay (audit CIR-MC01 §2.1; owner MC01-6).

QUALITATIVE runner: runs scenario CR-01 (catering_replay_v1.json) on a LIVE provider, judging
per-dimension WITHOUT claiming LIVE_PASS (the frozen golden/diagnostic threshold corpora are
not used for verdicts here), then presents qualitative evidence for review:
  - the list of questions presented (contextual? discriminating hypotheses? not re-asking
    what was already told);
  - competing hypotheses formed + their active support;
  - the epistemic status of key claims (ads = assumption; inquiry = estimate; not measured facts);
  - the checkpoint_eligibility block per turn (parallel dsc.v1);
  - recovery behavior (no DEGRADED turn over rich answers);
  - MC01-1 normalization telemetry (shape-repair vs meaning-defect back to the model).
Expected answers are NOT hardcoded — what is checked is the system's ABILITY to retain facts,
distinguish knowledge status, and pick a contextual step.

Usage: .venv/bin/python evals/run_catering_replay.py [--provider vertex]
"""
from __future__ import annotations

import json
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

CORPUS = json.loads((Path(__file__).resolve().parent / "golden" / "catering_replay_v1.json").read_text())


def main() -> int:
    provider = "vertex"
    a = sys.argv[1:]
    if "--provider" in a:
        provider = a[a.index("--provider") + 1]
    llm = build_llm(provider)
    if llm.name == "mock":
        print("Menolak: provider mock bukan bukti LIVE (ini replay insiden nyata).")
        return 2
    llm.set_determinism(True)
    app_main.get_llm = lambda: llm
    # raise_server_exceptions=False: server failures are reported as HTTP statuses, not a runner crash.
    client = TestClient(app_main.app, raise_server_exceptions=False)

    stats_before = dict(NORM_STATS)
    sc = CORPUS["scenarios"][0]
    print(f"replay {sc['id']} · provider={llm.name} model={getattr(llm, 'model', '?')} "
          f"corpus={CORPUS['corpus_version']} · MODE=interactive-per-turn")

    # RC-02: INTERACTIVE per-turn replay — send → inspect → IMMEDIATE retry when DEGRADED →
    # invariant → next turn. The retry does NOT wait for the next turn; that was the MC01 runner
    # defect (early-turn recovery was always rejected SUPERSEDED_BY_NEWER_EVENT, so it never
    # really tested recovery). Every retry is tested exactly-once: no extra user event / claim /
    # evidence / Move / Outcome may appear — only ONE new engine reply.
    t0 = time.time()
    r0 = client.post("/session", json={"goal_text": sc["turns"][0], "language": "id",
                                       "user_id": "u-catering-replay-1"})
    if r0.status_code != 200:
        print("gagal membuat sesi:", r0.status_code, r0.text[:200])
        return 2
    sid = r0.json()["session_id"]
    s = store.get(sid)
    turns: list[dict] = [{"user": sc["turns"][0],
                          "presented": {"kind": "QUESTION", "text": r0.json().get("first_question")},
                          "adaptive": None, "change": None}]
    recoveries: list[dict] = []
    invariant_violations: list[str] = []
    user_events_series: list[int] = []

    def _counts() -> dict:
        moves = list(getattr(s, "moves", None) or [])
        return {"user_events": sum(1 for e in s.events if e.get("role") == "user"),
                "engine_events": sum(1 for e in s.events if e.get("role") == "engine"),
                "claims": len((s.state_graph or {}).get("nodes") or {}),
                "evidence": len(s.evidence), "moves": len(moves),
                "outcomes": sum(1 for m in moves if m.get("lifecycle") == "OBSERVED")}

    for text in sc["turns"][1:]:
        m = client.post(f"/session/{sid}/message", json={"text": text})
        if m.status_code != 200:
            print(f"  !! giliran GAGAL HTTP {m.status_code}: {m.text[:140]}")
            invariant_violations.append(f"giliran {len(turns) + 1}: HTTP {m.status_code}")
            break
        j = m.json()
        s = store.get(sid)
        ad = (s.planner_log[-1].get("adaptive") or {}) if s.planner_log else {}
        tr = {"user": text, "presented": j.get("next_move"), "adaptive": ad.get("status"),
              "attempts": len(ad.get("attempts") or []), "change": j.get("change_class")}
        turns.append(tr)
        if (tr["presented"] or {}).get("degraded"):
            before = _counts()
            rr = client.post(f"/session/{sid}/retry_reasoning", json={})
            j2 = rr.json() if rr.status_code == 200 else {}
            nm = j2.get("next_move") or {}
            s = store.get(sid)
            after = _counts()
            drifted = {k: [before[k], after[k]] for k in before
                       if k not in ("engine_events",) and before[k] != after[k]}
            if drifted:
                invariant_violations.append(f"giliran {len(turns)}: {drifted}")
            if after["engine_events"] != before["engine_events"] + 1:
                invariant_violations.append(
                    f"giliran {len(turns)}: engine_events {before['engine_events']}->"
                    f"{after['engine_events']} (harus tepat +1)")
            user_events_series.append(after["user_events"])
            rec = {"turn": len(turns), "http": rr.status_code,
                   "still_degraded": bool(nm.get("degraded")), "kind": nm.get("kind", ""),
                   "counts_before": before, "counts_after": after,
                   "planner_retry_entries": sum(1 for e in s.planner_log if e.get("reasoning_retry"))}
            recoveries.append(rec)
            print(f"  T{rec['turn']} DEGRADED → retry SEGERA: HTTP {rr.status_code} "
                  f"still_degraded={rec['still_degraded']} kind={rec['kind']}")
            if rr.status_code == 200 and not rec["still_degraded"]:
                tr["presented"] = nm
                tr["recovered"] = True
            else:
                tr["recovered"] = False
    secs = round(time.time() - t0, 1)
    if len(set(user_events_series)) > 1:
        invariant_violations.append(f"event user berubah antar-retry: {user_events_series}")
    print(f"  invarian pemulihan: {len(recoveries)} retry · event user={user_events_series or 'n/a'}"
          f" · pelanggaran={invariant_violations or 'tidak ada'}")

    print("\n── pertanyaan/langkah yang disajikan (reviu kontekstual) ──")
    for i, tr in enumerate(turns, 1):
        p = tr["presented"] or {}
        print(f"  T{i} [{p.get('kind')}] {(p.get('text') or '')[:110]}")

    print("\n── hipotesis bersaing (bukti kompetisi penjelasan) ──")
    hyps = [h for h in (getattr(s, "hypotheses", None) or {}).values() if h.get("status") != "retired"]
    for h in hyps:
        print(f"  {h['id']}: {h['statement'][:100]} (support aktif={len(h.get('supports', []))})")

    print("\n── blok checkpoint_eligibility per giliran (dsc.v1 paralel) ──")
    elig_seen = []
    for e in s.planner_log:
        el = ((e.get("adaptive") or {}).get("proposal") or {}).get("checkpoint_eligibility")
        if el:
            elig_seen.append({"turn": e.get("turn"), "level": el.get("level"),
                              "can_offer": el.get("can_offer_checkpoint"),
                              "critical": len(el.get("critical_unknown_ids") or [])})
    print(f"  {json.dumps(elig_seen, ensure_ascii=False)}")

    print("\n── status epistemik klaim kunci (iklan/inquiry/follow-up) ──")
    for n in (s.state_graph.get("nodes") or {}).values():
        vb = (n.get("verbatim") or "").lower()
        if any(k in vb for k in ("iklan", "inquiry", "balas", "viral")):
            q = n.get("quantity") or {}
            print(f"  [{n.get('type')}/{n.get('tense')}/{q.get('value_kind') or '-'}] "
                  f"{(n.get('verbatim') or '')[:90]}")

    print("\n── checks per-dimensi ──")
    results, n_ok = [], 0
    for ck in sc["checks"]:
        try:
            ok, detail = run_check(ck, s, turns, {})
        except Exception as exc:  # noqa: BLE001
            ok, detail = False, f"cek error {type(exc).__name__}: {exc}"
        results.append({"dim": ck["dim"], "type": ck["type"], "ok": bool(ok),
                        "detail": str(detail)[:200]})
        n_ok += bool(ok)
        mark = "OK " if ok else "XX "
        print(f"  {mark} [{ck['dim']}] {ck['type']}" + ("" if ok else f" — {detail}"[:150]))
    stats_after = {k: v - stats_before.get(k, 0)
                   for k, v in NORM_STATS.items() if v != stats_before.get(k, 0)}
    print(f"\n── telemetry normalisasi MC01-1 (delta replay ini) ──\n  {json.dumps(stats_after)}")

    out_dir = Path(__file__).resolve().parents[1] / "traces" / "live"
    out_dir.mkdir(parents=True, exist_ok=True)
    fp = out_dir / f"catering-replay-{int(time.time())}.json"
    fp.write_text(json.dumps({
        "corpus": CORPUS["corpus_version"], "provider": llm.name, "model": getattr(llm, "model", ""),
        "ts_wib": time.strftime("%Y-%m-%d %H:%M:%S"), "secs": secs, "sid": sid,
        "checks": results, "checks_passed": n_ok, "checks_total": len(results),
        "hypotheses": [h["statement"] for h in hyps],
        "presented": [{"turn": i + 1, "kind": (t["presented"] or {}).get("kind"),
                       "text": (t["presented"] or {}).get("text")} for i, t in enumerate(turns)],
        "eligibility": elig_seen, "recoveries": recoveries,
        "recovery_invariant_violations": invariant_violations,
        "recovery_user_events_series": user_events_series,
        "norm_stats_delta": stats_after,
    }, ensure_ascii=False, indent=1))
    unrecovered = [r for r in recoveries if r["still_degraded"]]
    ok_all = n_ok == len(results) and not invariant_violations and not unrecovered
    print(f"\nhasil: {n_ok}/{len(results)} dimensi lulus · retry={len(recoveries)} "
          f"· gagal-pulih={len(unrecovered)} · pelanggaran-invariant={len(invariant_violations)} "
          f"· replay {secs}s · laporan -> {fp}")
    try:
        store.sessions.pop(sid, None)
    except Exception:  # noqa: BLE001 — best-effort cleanup; the report already persists
        pass
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
