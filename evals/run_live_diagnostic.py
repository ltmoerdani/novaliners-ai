"""S3-D — LIVE diagnostic qualification (DCP-01..06 + canonical cases), SEPARATE from g-corpus-v1.

    cd mvp && .venv/bin/python evals/run_live_diagnostic.py [--only D-01,D-05] [--provider vertex] [--list]

The corpus is frozen: evals/diagnostic/corpus_v2.json (supersedes v1; thresholds/cohorts are NOT
changed after seeing results — v2 ONLY fixes sequence/adapter semantics; v1 is kept as a record).
v2 adapter semantics (audit P0-A): Create Map consumes turns[0]; each `message` step consumes the
NEXT turn; the user event count is verified (no duplicated/extra events).
Verdicts use the SHARED `evals/live_qualify` aggregation (audit P0-B): the denominator is SCHEDULED
attempts, missing attempts -> LIVE_FAIL, critical cases require majority, zero-tolerance concepts
are explicitly mapped to detecting check types.
Production path: real HTTP + real synthesis. 429/1308/401 → BLOCKED_EXTERNAL; completed results kept.
Never PASS from incomplete coverage. API keys are never printed.
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
HERE = Path(__file__).resolve().parent
TMP = Path(tempfile.mkdtemp(prefix="nvl-live-diagnostic-"))

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
from core.schema.evidence import current_evidence  # noqa: E402
from evals.live_qualify import (  # noqa: E402
    acceptance_from_diagnostic,
    blocked,
    enforce_zero_tolerance_types,
    fabricated_revenue_fields,
)
from evals.live_qualify import aggregate as _qualify_aggregate  # noqa: E402
from llm.runtime import build_llm  # noqa: E402
from store.memory import SessionStore, store  # noqa: E402

store.PERSIST_DIR = TMP / "sessions"
SessionStore.PERSIST_DIR = TMP / "sessions"

REQUIRED_BINDING = ("state_version", "goal_id", "goal_version", "knowledge", "model", "prompts",
                    "contracts", "source_evidence_refs", "binding_id", "ts")


def load_corpus():
    corpus = json.loads((HERE / "diagnostic" / "corpus_v2.json").read_text())
    _validate_corpus(corpus)
    return corpus


def message_texts(sc):
    """Text for each `message` step — Create Map consumes turns[0] (explicit v2 adapter,
audit P0-A). The `message` step count must be exactly len(turns)-1: any difference = reject the
corpus, never silently send extra/duplicate user events."""
    n_msg = sum(1 for s in sc["sequence"] if s == "message")
    if n_msg != len(sc["turns"]) - 1:
        raise ValueError(
            f"{sc['id']}: {n_msg} langkah 'message' != len(turns)-1 ({len(sc['turns']) - 1})"
        )
    return sc["turns"][1:]


def _validate_corpus(corpus):
    for sc in corpus["scenarios"]:
        message_texts(sc)  # raises when the sequence is inconsistent with the v2 adapter semantics
        if "correction" in sc["sequence"] and not sc.get("correction"):
            raise ValueError(f"{sc['id']}: langkah 'correction' tanpa teks `correction`")


def _superseded(s):
    return [e for e in s.evidence if getattr(e, "superseded", False)]


def run_check(ck, ctx):
    s, diag = ctx["s"], ctx.get("diag") or {}
    t = ck["type"]
    if t == "superseded_absent_from_current":
        cur = {e.id for e in current_evidence(s.evidence)}
        return not (cur & {e.id for e in _superseded(s)}), "current memuat evidence superseded"
    if t == "diagnosis_no_superseded_anchor":
        sup = {e.id for e in _superseded(s)}
        acts = (diag.get("reasoning_trace") or {}).get("evidence_activations") or []
        supp = {i for a in acts for i in (a.get("supports") or [])}
        kmap = {i for ids in ((diag.get("knowledge_activation") or {}).get("rule_evidence_map") or {}).values()
                for i in ids}
        return not (sup & (supp | kmap)), f"anchor historis di diagnosis: {sorted(sup & (supp | kmap))}"
    if t == "historical_count_recorded":
        return (diag.get("metrics") or {}).get("n_evidence_historical", 0) >= len(_superseded(s)), \
            str((diag.get("metrics") or {}).get("n_evidence_historical"))
    if t == "binding_complete":
        b = ctx.get("binding") or {}
        return all(k in b for k in REQUIRED_BINDING), f"kurang: {[k for k in REQUIRED_BINDING if k not in b]}"
    if t == "state_version_unchanged":
        return (ctx.get("pre") or {}).get("state_version") == (ctx.get("post") or {}).get("state_version"), \
            (ctx.get("pre", {}).get("state_version"), ctx.get("post", {}).get("state_version"))
    if t == "binding_evidence_current":
        b = ctx.get("binding") or {}
        cur = sorted(e.id for e in current_evidence(s.evidence))
        return sorted(b.get("source_evidence_refs") or []) == cur, (b.get("source_evidence_refs"), cur)
    if t == "goal_version_consistent":
        b = ctx.get("binding") or {}
        pre = ctx.get("pre") or {}
        return b.get("goal_id") == pre.get("goal_id") and b.get("goal_version") == pre.get("goal_version"), \
            (b.get("goal_id"), b.get("goal_version"), pre.get("goal_id"), pre.get("goal_version"))
    if t == "checkpoint_v1_immutable":
        snap = ctx.get("v1_snapshot")
        full = ctx.get("cps_full") or []
        if not snap or not full:
            return False, "snapshot v1 tidak tersedia"
        return (json.dumps(full[0].get("diagnosis"), sort_keys=True, default=str) == snap[0]
                and json.dumps(full[0].get("binding"), sort_keys=True, default=str) == snap[1]), "v1 berubah"
    if t == "reassess_new_checkpoint":
        cps = ctx.get("cps") or []
        return len(cps) >= 2 and cps[-1].get("supersedes") == cps[-2].get("checkpoint_id"), len(cps)
    if t == "goal_metric_preserved":
        g = s.goal or {}
        return g.get("metric_id") == ck["metric_id"] and g.get("unit") == ck["unit"], \
            (g.get("metric_id"), g.get("unit"))
    if t == "narrative_not_revenue_only":
        blob = json.dumps([diag.get("where_you_are"), diag.get("success_metric"),
                           diag.get("next_best_action")], ensure_ascii=False).lower()
        return "revenue_monthly" not in blob, blob[:120]
    if t == "standing_not_supported":
        return diag.get("evidence_standing") in ("INSUFFICIENT", "WEAK"), diag.get("evidence_standing")
    if t == "no_fabricated_revenue_metric":
        # Audit P0-C: the old field `monthly_revenue` does NOT exist in RevenueState — the old
        # assertion always passed without checking anything. Now: canonical fields + provenance
        # (sources) + the no-revenue case (D-05): current_monthly and target_monthly MUST stay None.
        rs = diag.get("revenue_state") or {}
        bad = fabricated_revenue_fields(rs)
        if bad:
            return False, (f"nilai moneter tanpa provenance: {bad} "
                           f"(current={rs.get('current_monthly')!r}, target={rs.get('target_monthly')!r})")
        if rs.get("current_monthly") is not None:
            return False, (f"current_monthly={rs.get('current_monthly')!r} padahal percakapan "
                           "tidak memuat angka revenue")
        if rs.get("target_monthly") is not None:
            return False, (f"target_monthly={rs.get('target_monthly')!r} tanpa dasar angka "
                           "di percakapan")
        return True, "current/target kosong — tidak ada revenue yang dikarang"
    if t == "prescription_throttled":
        return len(diag.get("day_by_day") or []) <= 3, len(diag.get("day_by_day") or [])
    if t == "mixed_language_claims_present":
        n = len([x for x in (s.state_graph.get("nodes") or {}).values()
                 if (x.get("status") or "active") == "active"])
        return n >= 1, n
    return False, f"tipe cek tak dikenal: {t}"


def run_scenario(sc, client, uid):
    t0 = time.time()
    body = {"goal_text": sc["turns"][0], "language": sc.get("lang", "id"), "user_id": uid}
    body.update(sc.get("create") or {})
    r = client.post("/session", json=body)
    if r.status_code != 200:
        raise RuntimeError(f"create {r.status_code} {r.text[:200]}")
    sid = r.json()["session_id"]
    ctx = {"sid": sid, "s": None, "pre": None, "post": None, "diag": None, "cps": None,
           "cps_full": None, "binding": None, "v1_snapshot": None}
    # v2 adapter semantics (audit P0-A): Create Map ALREADY processed turns[0]; a `message` step
    # consumes the next turn — turns[0] is NEVER re-sent as a message.
    texts = iter(message_texts(sc))
    n_correction = 0
    for step in sc["sequence"]:
        if step == "session":
            continue
        if step == "message":
            text = next(texts)
            m = client.post(f"/session/{sid}/message", json={"text": text})
            if m.status_code != 200:
                raise RuntimeError(f"message {m.status_code} {m.text[:200]}")
        elif step == "correction":
            n_correction += 1
            m = client.post(f"/session/{sid}/message", json={"text": sc["correction"]})
            if m.status_code != 200:
                raise RuntimeError(f"correction {m.status_code} {m.text[:200]}")
        elif step == "finalize":
            ctx["pre"] = client.get(f"/session/{sid}/navigation").json().get("reality")
            f = client.post(f"/session/{sid}/finalize")
            if f.status_code != 200:
                raise RuntimeError(f"finalize {f.status_code} {f.text[:200]}")
            s = store.get(sid)
            full = s.checkpoints or []
            if full:
                ctx["v1_snapshot"] = (json.dumps(full[0].get("diagnosis"), sort_keys=True, default=str),
                                      json.dumps(full[0].get("binding"), sort_keys=True, default=str))
        elif step == "diagnosis":
            d = client.get(f"/session/{sid}/diagnosis")
            if d.status_code != 200:
                raise RuntimeError(f"diagnosis {d.status_code} {d.text[:200]}")
            ctx["diag"] = d.json()
        elif step == "reassess":
            ra = client.post(f"/session/{sid}/reassess")
            if ra.status_code != 200:
                raise RuntimeError(f"reassess {ra.status_code} {ra.text[:200]}")
        elif step == "checkpoints":
            ctx["cps"] = client.get(f"/session/{sid}/checkpoints").json().get("checkpoints")
            ctx["cps_full"] = store.get(sid).checkpoints
    s = store.get(sid)
    ctx["s"] = s
    # Harness verification (audit P0-A): NO extra/duplicate user events — the transcript and the
    # durable events must both contain len(turns) + the number of corrections.
    expected_user = len(sc["turns"]) + n_correction
    transcript_user = [t[1] for t in s.transcript if t[0] == "user"]
    durable_user = [e for e in event_store.load_events(sid) if e.get("role") == "user"]
    if len(transcript_user) != expected_user or len(durable_user) != expected_user:
        raise RuntimeError(
            f"harness event-count: transcript={len(transcript_user)} durable={len(durable_user)} "
            f"!= expected {expected_user} (turns={len(sc['turns'])}, correction={n_correction})"
        )
    ctx["post"] = client.get(f"/session/{sid}/navigation").json().get("reality")
    # Harness: the last checkpoint is ALWAYS read, even when `sequence` has no `checkpoints`
    # step (e.g. D-07 tests binding but its sequence stops at `diagnosis`) — without this the
    # binding checks would evaluate None, not product behavior.
    if not ctx["cps_full"]:
        ctx["cps_full"] = s.checkpoints or []
        if ctx["cps"] is None:
            ctx["cps"] = [{"version": c.get("version"), "status": c.get("status")} for c in ctx["cps_full"]]
    if ctx["cps_full"]:
        ctx["binding"] = ctx["cps_full"][-1].get("binding")
    if ctx["diag"] is None:
        d = client.get(f"/session/{sid}/diagnosis")
        ctx["diag"] = d.json() if d.status_code == 200 else {}
    cks = []
    for ck in sc.get("checks", []):
        try:
            ok, detail = run_check(ck, ctx)
        except Exception as exc:  # noqa: BLE001
            ok, detail = False, f"cek error {type(exc).__name__}: {exc}"
        cks.append({"dim": ck["dim"], "type": ck["type"], "ok": bool(ok), "detail": str(detail)[:200]})
    s = store.get(sid)
    record = {
        "id": sc["id"], "cohort": sc["cohort"], "critical": bool(sc.get("critical")),
        "secs": round(time.time() - t0, 1), "checks": cks,
        "canonical": {
            "state_version": ctx["post"].get("state_version") if ctx["post"] else None,
            "goal_id": (s.goal or {}).get("goal_id"), "goal_version": (s.goal or {}).get("version"),
            "active_claims": len([n for n in (s.state_graph.get("nodes") or {}).values()
                                  if (n.get("status") or "active") == "active"]),
            "current_evidence": sorted(e.id for e in current_evidence(s.evidence)),
            "historical_evidence": sorted(e.id for e in _superseded(s)),
        },
        "goal": {k: (s.goal or {}).get(k) for k in ("metric_id", "direction", "unit", "target",
                                                     "target_origin", "measurement_window_days")},
        "diagnosis": {"primary_constraint_id": (ctx["diag"] or {}).get("primary_constraint_id"),
                      "evidence_standing": (ctx["diag"] or {}).get("evidence_standing"),
                      "requires_new_evidence": (ctx["diag"] or {}).get("requires_new_evidence"),
                      "confidence": (ctx["diag"] or {}).get("confidence")},
        "checkpoints": [{"version": c.get("version"), "status": c.get("status")} for c in (ctx["cps"] or [])],
        "binding": ctx.get("binding"),
        "transcript": [t[1] for t in s.transcript if t[0] == "user"],
    }
    return record


def aggregate(runs, corpus, *, only=None, blocked_ids=None):
    """Mechanical verdict — DELEGATES to the SHARED `evals.live_qualify` aggregation (audit P0-B).

    The diagnostic corpus applies the same rules as the golden runner: the denominator is SCHEDULED
    attempts (not only completed ones), missing attempts -> LIVE_FAIL, critical cases require
    `critical_pass_majority`. On top of that, the corpus's zero-tolerance concepts are mapped
    EXPLICITLY to detecting check types (a runner adapter — the frozen corpus is untouched):
    violations = not PASS; concepts without a detector are REPORTED in `zero_tolerance_unmapped`,
    never dropped silently.
    """
    acc = corpus["acceptance"]
    rep = _qualify_aggregate(runs, corpus["scenarios"], acceptance_from_diagnostic(acc),
                             only=only, blocked_ids=blocked_ids)
    violations, unmapped = enforce_zero_tolerance_types(
        runs, corpus["scenarios"], list(acc.get("zero_tolerance") or []))
    rep["zero_tolerance_type_violations"] = sorted(set(violations))
    rep["zero_tolerance_unmapped"] = sorted(set(unmapped))
    if rep["zero_tolerance_type_violations"]:
        rep["reasons"].append(
            f"zero-tolerance (detektor tipe check) dilanggar: {rep['zero_tolerance_type_violations']}")
        if rep["status"] in ("LIVE_PASS", "PARTIAL"):
            rep["status"] = "LIVE_FAIL"
    if rep["zero_tolerance_unmapped"]:
        # Gate A (15 Oct): a zero-tolerance concept WITHOUT a detector must never be allowed to slip
        # through as LIVE_PASS — that is a COVERAGE GAP (the corpus cannot prove it), different from
        # the semantic violations above; both are recorded with an explicit classification, both veto PASS.
        rep["reasons"].append(
            "zero-tolerance coverage gap — konsep tanpa detektor di korpus (bukan kegagalan "
            f"semantik, tetapi tak terbuktikan): {rep['zero_tolerance_unmapped']}")
        if rep["status"] in ("LIVE_PASS", "PARTIAL"):
            rep["status"] = "LIVE_FAIL"
    return rep


def main():
    args = sys.argv[1:]
    only = set(args[args.index("--only") + 1].split(",")) if "--only" in args else None
    provider = args[args.index("--provider") + 1] if "--provider" in args else "vertex"
    corpus = load_corpus()
    if "--list" in args:
        for sc in corpus["scenarios"]:
            print(sc["id"], "|", sc["cohort"], "|", "critical" if sc.get("critical") else "-", "|", sc["title"])
        return 0
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
        if only and sc["id"] not in only:
            continue
        reps = corpus["acceptance"]["critical_repeats"] if sc.get("critical") else 1
        for k in range(reps):
            if done_block:
                blocked_ids.append(f"{sc['id']}#{k + 1}")
                continue
            try:
                rec = run_scenario(sc, client, f"u-dcp-{sc['id'].lower()}-{k}")
            except Exception as exc:  # noqa: BLE001
                if blocked(exc):
                    done_block = True
                    blocked_ids.append(f"{sc['id']}#{k + 1}")
                    print(f"  BLOCKED_EXTERNAL {sc['id']}: {type(exc).__name__}")
                    continue
                runs.append({"id": sc["id"], "rep": k + 1, "error": f"{type(exc).__name__}: {str(exc)[:200]}",
                             "checks": [], "transcript": []})
                print(f"  ERROR {sc['id']}#{k + 1}: {exc}")
                continue
            rec["rep"] = k + 1
            runs.append(rec)
            print(f"  {sc['id']}#{k + 1} [{sc['cohort']}] " + " ".join("Y" if c["ok"] else "N" for c in rec["checks"])
                  + f"  ({rec['secs']}s)")
    report = aggregate(runs, corpus, only=only, blocked_ids=blocked_ids)
    out = Path(__file__).resolve().parents[1] / "traces" / "live"
    out.mkdir(parents=True, exist_ok=True)
    fp = out / f"diagnostic-{int(time.time())}.json"
    full = {"status": report["status"], "ts_wib": time.strftime("%Y-%m-%d %H:%M:%S"),
            "provider": llm.name, "model": getattr(llm, "model", ""), "corpus": corpus["corpus_version"],
            "acceptance": corpus["acceptance"], "aggregate": report, "runs": runs}
    fp.write_text(json.dumps(full, ensure_ascii=False, indent=1))
    print(json.dumps({"status": report["status"], "reasons": report.get("reasons"),
                      "rates": report["rates"], "blocked": report["blocked"],
                      "report": str(fp)}, ensure_ascii=False, indent=1))
    return 0 if report["status"] == "LIVE_PASS" else (3 if report["blocked"] else 1)


if __name__ == "__main__":
    raise SystemExit(main())
