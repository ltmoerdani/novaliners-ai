"""R7 — LIVE qualification of the golden corpus (int 16 §13, G-01..35) with a REAL provider.

NOT part of gate-fast.

    cd mvp && .venv/bin/python evals/run_live_golden.py [--only G-04,G-05] [--repeats N] [--provider vertex]

- The corpus is frozen: evals/golden/corpus_v1.json (historic-tuned vs holdout cohorts are NOT
  changed retroactively).
- Thresholds are preset in THRESHOLDS below and in int 08 BEFORE the first run (the commit predates
  the result report).
- PRODUCT path: real HTTP (TestClient) — Create Map → message → state — with a temporary store;
  provider = real.
- Deterministic schema-neutral checks (behavior, not field names). Question-usefulness is NOT scored
  automatically: the transcript is kept for an independent reviewer (rubric in int 08); that is
  OWNER_REVIEW_REQUIRED.
- 429/1308/401 → remaining scenarios BLOCKED_EXTERNAL; already-completed results are kept; no
  fabricated PASS.
- API keys are never printed; the test transcript is synthetic corpus text (not user conversation).
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
HERE = Path(__file__).resolve().parent
TMP = Path(tempfile.mkdtemp(prefix="nvl-live-golden-"))

import store.adjudication_ledger as ledger  # noqa: E402
import store.events as event_store  # noqa: E402
import store.funnel as funnel  # noqa: E402
import store.path_states as path_states  # noqa: E402
import store.route_execution as route_execution  # noqa: E402
import store.route_lineages as rl  # noqa: E402
import store.workspace as workspace  # noqa: E402

event_store.EVENTS_DIR = TMP / "events"
ledger._LEDGER_ROOT = TMP / "ledger"
rl._BASE = TMP / "lineages"
workspace._BASE = TMP / "workspaces"
route_execution._BASE = TMP / "workspaces"
funnel._PATH = TMP / "funnel.jsonl"
path_states._BASE = TMP
path_states._STATES = TMP / "path_states.json"
path_states._HISTORY = TMP / "path_history.jsonl"

from fastapi.testclient import TestClient  # noqa: E402

import app.main as app_main  # noqa: E402
from evals.live_qualify import (  # noqa: E402
    acceptance_from_thresholds,
    blocked,
)
from evals.live_qualify import aggregate as _qualify_aggregate  # noqa: E402
from evals.live_qualify import scheduled_attempts as _qualify_scheduled  # noqa: E402
from llm.runtime import build_llm  # noqa: E402
from store.memory import SessionStore, store  # noqa: E402

store.PERSIST_DIR = TMP / "sessions"
SessionStore.PERSIST_DIR = TMP / "sessions"

# ── PRESET THRESHOLDS (frozen before the run) ──────────────────────────────────────────────────────────
THRESHOLDS = {
    "zero_tolerance_dims": ["no_false_goal", "no_false_promotion", "no_psych_diagnosis", "no_repeat", "stability"],
    "dim_min_rate": {"role": 0.80, "quantity": 0.90, "temporal": 0.80, "revision": 0.80, "goal": 0.90,
                     "retention": 0.90, "coverage": 0.80, "measurement": 0.70, "admissibility": 0.80,
                     "first_question": 0.90, "hypothesis": 0.50, "hypothesis_trace": 0.50},
    "guard_acceptance_min": 0.85,
    "critical_repeats": 3,
    "critical_pass_majority": 2 / 3,
    "zero_tolerance_requires": "semua percobaan (3/3 pada kasus kritis)",
}


def active_claims(s):
    return [n for n in (s.state_graph.get("nodes") or {}).values() if (n.get("status") or "active") == "active"]


def all_claims(s):
    return list((s.state_graph.get("nodes") or {}).values())


def has(n, sub):
    return sub.lower() in (n.get("verbatim") or "").lower()


def run_check(ck, s, turns, ctx):
    t = ck["type"]
    if t == "claim":
        for n in active_claims(s):
            if not has(n, ck["contains"]):
                continue
            if "role_in" in ck and n.get("type") not in ck["role_in"]:
                continue
            if "aspect_in" in ck and n.get("aspect") not in ck["aspect_in"]:
                continue
            if ck.get("has_quantity") and not n.get("quantity"):
                continue
            return True, n.get("id", "")
        return False, f"tak ada klaim aktif memuat {ck['contains']!r} dengan syarat"
    if t == "no_claim":
        bad = [n for n in active_claims(s) if has(n, ck["contains"]) and n.get("type") in ck.get("role_in", [n.get("type")])]
        return (not bad), f"{len(bad)} klaim terlarang"
    if t == "claim_active":
        ok = any(has(n, ck["contains"]) for n in active_claims(s))
        return ok, "klaim tidak aktif/tidak ada"
    if t == "quantity":
        for n in all_claims(s):
            q = n.get("quantity") or {}
            if not has(n, ck["contains"]) or not q:
                continue
            if "kind_in" in ck and q.get("value_kind") not in ck["kind_in"]:
                continue
            if "tense_in" in ck and n.get("tense") not in ck["tense_in"]:
                continue
            return True, ""
        return False, f"tak ada klaim berkuantitas memuat {ck['contains']!r} dengan jenis/tense yang diminta"
    if t == "superseded_or_negated":
        hits = [n for n in all_claims(s) if has(n, ck["contains"])]
        return (bool(hits) and all(n.get("status") in ("superseded", "negated") for n in hits)), \
            f"status={[n.get('status') for n in hits]}"
    if t == "min_active_claims":
        return len(active_claims(s)) >= ck["n"], f"aktif={len(active_claims(s))}"
    if t == "goal":
        from domains.revenue.schema.goal import Goal
        g = Goal(**s.goal)
        if ck.get("target_none"):
            return (g.target is None and g.target_min is None), f"target={g.target} min={g.target_min}"
        if "confirmed" in ck:
            return (g.confirmed_target() == ck["confirmed"]), f"origin={g.target_origin}"
        if ck.get("no_revenue_target"):
            return (g.target is None or g.metric_id != "revenue_monthly"), f"metric={g.metric_id} target={g.target}"
    if t == "presented_turn":
        i = ck["turn"] - 1
        if i >= len(turns):
            return False, "giliran tak ada"
        p = turns[i]["presented"] or {}
        if "kind_in" in ck and p.get("kind") not in ck["kind_in"]:
            return False, f"kind={p.get('kind')}"
        if "text_not_matches" in ck and re.search(ck["text_not_matches"], p.get("text") or "", re.I):
            return False, f"teks cocok pola terlarang: {(p.get('text') or '')[:100]}"
        return True, ""
    if t == "presented_text_not_matches":
        for tr in turns:
            if re.search(ck["pattern"], (tr["presented"] or {}).get("text") or "", re.I):
                return False, (tr["presented"] or {}).get("text", "")[:100]
        return True, ""
    if t == "first_question_not_matches":
        fq = turns[0]["presented"].get("text") if turns and turns[0]["presented"] else ""
        return (not re.search(ck["pattern"], fq or "", re.I)), (fq or "")[:120]
    if t == "no_repeat_question":
        qs = [re.sub(r"\W+", " ", (tr["presented"] or {}).get("text") or "").strip().lower() for tr in turns
              if (tr["presented"] or {}).get("kind") in ("QUESTION", "EVIDENCE_REQUEST")]
        return (len(qs) == len(set(qs))), "pertanyaan identik berulang"
    if t == "hypothesis_mentions_any":
        hs = list((getattr(s, "hypotheses", None) or {}).values())
        ok = any(any(w in h["statement"].lower() for w in ck["any"]) for h in hs)
        return ok, f"{[h['statement'][:60] for h in hs]}"
    if t == "hypothesis_support_active":
        hs = list((getattr(s, "hypotheses", None) or {}).values())
        act = {n["id"] for n in active_claims(s)}
        ok = bool(hs) and all(set(h["supports"]) <= act for h in hs if h.get("status") != "retired")
        return ok, "hipotesis tanpa dukungan aktif"
    if t == "revenue_state":
        from core.schema.evidence import current_evidence
        from domains.revenue.navigation.live import derive_revenue_state
        utext = "\n".join(f"user: {x}" for r, x in s.transcript if r == "user")
        rs = derive_revenue_state(current_evidence(s.evidence), s.goal_text, utext, s.state_graph)
        if ck.get("current_none"):
            return rs.current_monthly is None, f"current={rs.current_monthly}"
        if "current_not_in" in ck:
            return rs.current_monthly not in ck["current_not_in"], f"current={rs.current_monthly}"
    if t == "icp_not_present_without_rule":
        e = ledger.latest_entry(s.user_id, "access.icp") if s.user_id else None
        return (e is None or e["adjudication"]["status"] != "PRESENT"), "ICP PRESENT tanpa bukti formal"
    if t == "reload_equal":
        re_ = SessionStore().get(s.id)
        return (re_ is not None and re_.state_graph == s.state_graph), "reload tidak identik"
    # ── MC01-6 check types (catering replay): generic, the frozen corpus stays untouched ──
    if t == "no_degraded_turns":
        bad = [i + 1 for i, tr in enumerate(turns) if (tr["presented"] or {}).get("degraded")]
        return (not bad), f"degraded pada giliran {bad}"
    if t == "checkpoint_block_present":
        for e in getattr(s, "planner_log", None) or []:
            if ((e.get("adaptive") or {}).get("proposal") or {}).get("checkpoint_eligibility"):
                return True, ""
        return False, "blok checkpoint_eligibility tidak pernah hadir"
    if t == "hypothesis_count_min":
        hs = [h for h in (getattr(s, "hypotheses", None) or {}).values()
              if h.get("status") != "retired"]
        return len(hs) >= ck["n"], f"hipotesis aktif={len(hs)}"
    return False, f"tipe cek tak dikenal: {t}"


def run_scenario(sc, client, user_id):
    turns = []
    t0 = time.time()
    r = client.post("/session", json={"goal_text": sc["turns"][0], "language": "id", "user_id": user_id})
    if r.status_code != 200:
        raise RuntimeError(f"create {r.status_code} {r.text[:200]}")
    sid = r.json()["session_id"]
    turns.append({"user": sc["turns"][0], "presented": {"kind": "QUESTION", "text": r.json().get("first_question")},
                  "adaptive": None, "change": None})
    for text in sc["turns"][1:]:
        m = client.post(f"/session/{sid}/message", json={"text": text})
        if m.status_code != 200:
            raise RuntimeError(f"message {m.status_code} {m.text[:200]}")
        j = m.json()
        s = store.get(sid)
        ad = (s.planner_log[-1].get("adaptive") or {}) if s.planner_log else {}
        turns.append({"user": text, "presented": j.get("next_move"), "adaptive": ad.get("status"),
                      "attempts": len(ad.get("attempts") or []), "change": j.get("change_class")})
    return sid, turns, round(time.time() - t0, 1)


def scheduled_attempts(corpus, only=None, thresholds=None, repeats_override=None):
    """[Compatibility] SCHEDULED LIVE attempts — delegates to the shared contract `evals/live_qualify`."""
    th = thresholds or THRESHOLDS
    scenarios = [sc for sc in corpus["scenarios"]
                 if sc.get("mode", "live") in ("live", "live_first_question")]
    return _qualify_scheduled(scenarios, only=only, critical_repeats=th["critical_repeats"],
                              repeats_override=repeats_override)


def aggregate(runs, corpus, *, only=None, blocked_ids=None, guard_rate=None, thresholds=None,
              repeats_override=None):
    """Mechanical verdict from the evidence record — DELEGATES to the SHARED aggregation (evals/live_qualify).

    One contract with the diagnostic runner (audit 14 Oct 2026, P0-B): denominator = SCHEDULED
    attempts (not only the completed ones); a missing attempt -> not PASS; critical cases require a
    majority; an --only subset is never PASS; a required dimension that is absent / unclassified
    never counts as PASS.
    """
    th = thresholds or THRESHOLDS
    scenarios = [sc for sc in corpus["scenarios"]
                 if sc.get("mode", "live") in ("live", "live_first_question")]
    return _qualify_aggregate(runs, scenarios, acceptance_from_thresholds(th), only=only,
                              blocked_ids=blocked_ids, guard_rate=guard_rate,
                              repeats_override=repeats_override)


def main():
    only = None
    repeats_override = None
    provider = "vertex"
    a = sys.argv[1:]
    if "--only" in a:
        only = set(a[a.index("--only") + 1].split(","))
    if "--repeats" in a:
        repeats_override = int(a[a.index("--repeats") + 1])
    if "--provider" in a:
        provider = a[a.index("--provider") + 1]
    corpus = json.loads((HERE / "golden" / "corpus_v1.json").read_text())
    llm = build_llm(provider)
    if llm.name == "mock":
        print("Menolak: provider mock bukan bukti LIVE.")
        return 2
    llm.set_determinism(True)
    app_main.get_llm = lambda: llm
    client = TestClient(app_main.app)
    print(f"provider={llm.name} model={getattr(llm, 'model', '?')} corpus={corpus['corpus_version']}")
    runs, blocked_ids = [], []
    done_block = False
    for sc in corpus["scenarios"]:
        if sc["mode"] not in ("live", "live_first_question") or (only and sc["id"] not in only):
            continue
        reps = repeats_override or (THRESHOLDS["critical_repeats"] if sc.get("critical") else 1)
        for k in range(reps):
            if done_block:
                blocked_ids.append(f"{sc['id']}#{k + 1}")
                continue
            try:
                sid, turns, secs = run_scenario(sc, client, f"u-golden-{sc['id'].lower()}-{k}")
            except Exception as exc:  # noqa: BLE001
                if blocked(exc):
                    done_block = True
                    blocked_ids.append(f"{sc['id']}#{k + 1}")
                    print(f"  BLOCKED_EXTERNAL {sc['id']}: {type(exc).__name__}")
                    continue
                runs.append({"id": sc["id"], "rep": k + 1, "error": f"{type(exc).__name__}: {str(exc)[:200]}",
                             "checks": [], "turns": []})
                print(f"  ERROR {sc['id']}#{k + 1}: {exc}")
                continue
            s = store.get(sid)
            cks = []
            for ck in sc["checks"]:
                try:
                    ok, detail = run_check(ck, s, turns, {})
                except Exception as exc:  # noqa: BLE001
                    ok, detail = False, f"cek error {type(exc).__name__}: {exc}"
                cks.append({"dim": ck["dim"], "type": ck["type"], "ok": bool(ok), "detail": str(detail)[:200]})
            runs.append({"id": sc["id"], "rep": k + 1, "cohort": sc["cohort"], "secs": secs, "checks": cks,
                         "turns": turns, "claims_active": len(active_claims(s)),
                         "hypotheses": [h["statement"] for h in (getattr(s, "hypotheses", None) or {}).values()]})
            print(f"  {sc['id']}#{k + 1} [{sc['cohort']}] " + " ".join("✓" if c["ok"] else "✗" for c in cks)
                  + f"  ({secs}s)")
    # ── aggregation (S3-C): mechanical verdict from the evidence record ──
    turns_all = [t for r in runs for t in r["turns"][1:]]
    acc = [t for t in turns_all if t.get("adaptive")]
    guard_rate = round(sum(1 for t in acc if t["adaptive"] == "ACCEPTED") / len(acc), 3) if acc else None
    report = aggregate(runs, corpus, only=only, blocked_ids=blocked_ids, guard_rate=guard_rate,
                       thresholds=THRESHOLDS, repeats_override=repeats_override)
    status = report["status"]
    rep = {"status": status, "ts_wib": time.strftime("%Y-%m-%d %H:%M:%S"), "model": getattr(llm, "model", ""),
           "provider": llm.name, "corpus": corpus["corpus_version"], "thresholds": THRESHOLDS,
           "rates": report["rates"], "verdicts": report["verdicts"],
           "guard_acceptance": report["guard_acceptance"],
           "scenario_pass_rate": report["critical_pass_fraction"],
           "blocked": report["blocked"], "runs": runs,
           "aggregate": {k: v for k, v in report.items()
                         if k not in ("rates", "verdicts", "guard_acceptance", "blocked")}}
    out = Path(__file__).resolve().parents[1] / "traces" / "live"
    out.mkdir(parents=True, exist_ok=True)
    fp = out / f"golden-{int(time.time())}.json"
    fp.write_text(json.dumps(rep, ensure_ascii=False, indent=1))
    print(json.dumps({"status": status, "reasons": report["reasons"], "rates": report["rates"],
                      "verdicts": report["verdicts"], "guard_acceptance": report["guard_acceptance"],
                      "scenario_pass_rate": report["critical_pass_fraction"], "blocked": report["blocked"],
                      "report": str(fp)}, ensure_ascii=False, indent=1))
    return 0 if status == "LIVE_PASS" else (3 if report["blocked"] else 1)


if __name__ == "__main__":
    raise SystemExit(main())
