"""Pilot dashboard — monitoring real users on path 2 (internal-docs).

Deterministic aggregation (0-LLM) from three sources ALREADY written by the runtime:
  - store/sessions/*.json  → user identity, linkage, journey verdict (J3/J7)
  - eval_funnel.jsonl      → per-finalize summary (iter-12/J3)
  - store/nba_reports.jsonl→ outcome per intervention (Gate 5b/J6)

Used by the owner during the 3-5 user × ≥2 cycle pilot to answer:
  1. Who are the users, how many cycles, which verdict per cycle?
  2. Which interventions are reported, and their outcomes (J6 moat: n per iid)?
  3. Is the J7-c demotion active (not_moved/regret interventions per user)?

Output: human-readable summary to stdout + JSON (optional, --json).
Always exit 0 — this is monitoring, not a gate.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SESSIONS_DIR = ROOT / "store" / "sessions"
FUNNEL = ROOT / "eval_funnel.jsonl"
NBA = ROOT / "store" / "nba_reports.jsonl"

SPECTRUM_ORDER = ["STOP", "NOT_YET", "TEST_FIRST", "GO_SMALL", "PROCEED", "SCALE"]
DEMOTE_OUTCOMES = ("not_moved", "regret")


def _rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def collect() -> dict:
    # --- sessions per user (from the persistence store) -------------------------------------
    sessions: list[dict] = []
    if SESSIONS_DIR.exists():
        for f in sorted(SESSIONS_DIR.glob("*.json")):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            diag = d.get("diagnosis") or {}
            sessions.append({
                "session_id": d.get("id", f.stem),
                "user_id": d.get("user_id") or "(anon)",
                "prior_session_id": d.get("prior_session_id") or "",
                "created_ts": d.get("created_ts") or 0,
                "has_diagnosis": bool(diag),
                "primary": diag.get("primary_constraint_id"),
                "spectrum": (diag.get("decision_spectrum") or {}).get("level"),
                "reassess_window_days": diag.get("reassess_window_days"),
                "verdict": (d.get("journey_delta") or {}).get("verdict"),
                "demoted_seen": sorted(
                    ((diag.get("knowledge_activation") or {}).get("journey_context")
                     or {}).get("demoted_interventions", {})
                ),
            })

    by_user: dict[str, list[dict]] = defaultdict(list)
    for s in sessions:
        by_user[s["user_id"]].append(s)
    for u in by_user:
        by_user[u].sort(key=lambda s: s.get("created_ts") or 0)

    # --- outcome per intervention (moat J6) --------------------------------------
    sid_to_user = {s["session_id"]: s["user_id"] for s in sessions}
    outcomes_by_user: dict[str, dict[str, dict[str, int]]] = defaultdict(
        lambda: defaultdict(dict)
    )
    for r in _rows(NBA):
        uid = sid_to_user.get(r.get("session_id"), "(anon)")
        iid = (r.get("intervention_id") or "?").upper()
        oc = r.get("outcome")
        if not oc or oc == "confounded":
            continue
        d_ = outcomes_by_user[uid][iid]
        d_[oc] = d_.get(oc, 0) + 1

    # --- verdict pipeline (cross-finalize funnel) ---------------------------------
    funnel_rows = _rows(FUNNEL)

    return {
        "n_sessions": len(sessions),
        "n_users": len([u for u in by_user if u != "(anon)"]),
        "users": {
            u: {
                "cycles": len(sess),
                "journey": [
                    f"{s['verdict'] or '—'}@{s['primary'] or '?'}/{s['spectrum'] or '?'}"
                    for s in sess
                ],
                "interventions_outcome": {
                    iid: outs for iid, outs in outcomes_by_user.get(u, {}).items()
                },
                "demote_candidates": sorted(
                    iid for iid, outs in outcomes_by_user.get(u, {}).items()
                    if any(o in DEMOTE_OUTCOMES for o in outs)
                ),
                "stuck_streak": _stuck_streak(sess),
            }
            for u, sess in sorted(by_user.items())
        },
        "global": {
            "verdict_distribution": _count(
                s["verdict"] for s in sessions if s["verdict"]
            ),
            "funnel_records": len(funnel_rows),
            "outcome_distribution": _count(
                r.get("outcome") for r in _rows(NBA) if r.get("outcome")
            ),
        },
    }


def _count(vals) -> dict[str, int]:
    out: dict[str, int] = {}
    for v in vals:
        out[v] = out.get(v, 0) + 1
    return dict(sorted(out.items()))


def _stuck_streak(sess: list[dict]) -> int:
    """Consecutive STUCK from the latest cycles — a pivot-candidate signal (J7-d candidate)."""
    n = 0
    for s in reversed(sess):
        if s["verdict"] == "STUCK":
            n += 1
        else:
            break
    return n


def main() -> int:
    data = collect()
    if "--json" in sys.argv:
        print(json.dumps(data, ensure_ascii=False, indent=1))
        return 0
    print(f"== PILOT DASHBOARD (internal-docs) — {data['n_sessions']} sesi, "
          f"{data['n_users']} user beridentitas ==")
    for u, info in data["users"].items():
        print(f"\n👤 {u} — {info['cycles']} siklus")
        jr = info["journey"]
        shown = jr[-10:] if len(jr) > 10 else jr
        prefix = f"…({len(jr) - len(shown)} lain) → " if len(jr) > len(shown) else ""
        print(f"   journey : {prefix}{' → '.join(shown) or '(belum ada diagnosis)'}")
        if info["interventions_outcome"]:
            outs = "; ".join(
                f"{iid}:{','.join(f'{o}x{n}' for o, n in sorted(v.items()))}"
                for iid, v in sorted(info["interventions_outcome"].items())
            )
            print(f"   outcome : {outs}")
        if info["demote_candidates"]:
            print(f"   demote  : {', '.join(info['demote_candidates'])} "
                  f"(aktif di sesi berikutnya via J7-c)")
        if info["stuck_streak"] >= 2:
            print(f"   ⚠ STUCK {info['stuck_streak']}x beruntun — kandidat pivot")
    g = data["global"]
    print(f"\nGlobal: verdict={g['verdict_distribution'] or '{}'} "
          f"outcome={g['outcome_distribution'] or '{}'} "
          f"funnel_records={g['funnel_records']}")
    if data["n_users"] == 0:
        print("\n(Belum ada user beridentitas — pilot belum mulai; lihat internal-docs §3)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
