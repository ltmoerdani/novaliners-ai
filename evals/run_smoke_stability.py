"""G7 — Smoke Stability (internal-docs §10.1, Phase K 17 Sep 2026).

Background: the DoD smoke could flip 18/19↔19/19 across runs EVEN THOUGH determinism_mode is on
(temperature 0) — measured 17 Sep 2026 on the same commit: PRIMARY shifted V2.1↔C6.3, confidence
0.483↔0.762, while `revenue_state` (the deterministic layer) stayed IDENTICAL. Conclusion matching
the OpenAI docs: LLM output is non-deterministic by design — what can be held is not identical
output, but MEASURED STABILITY. This gate measures it.

Runs N× `evals/run_dod_smoke.py` (identical input & commit), then audits:

  S1  revenue_state IDENTICAL across runs  (the deterministic layer must be stable)
  S2  kb_fingerprint IDENTICAL across runs (the same KB for every run)
  S3  PRIMARY majority ≥ majority(N)       (2/3 for N=3)
  S4  |Δ confidence| across runs ≤ 0.15    (overall confidence must not jump far)

Each run's snapshot is saved to store/stability/ for audit. Exit 0 = all pass.
Live LLM: N × ±4.5 minutes. Run: .venv/bin/python evals/run_smoke_stability.py [N]
"""
from __future__ import annotations

import collections
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, ".")

ARTIFACT = Path("eval_dod_smoke_result.json")
SNAP_DIR = Path("store/stability")
CONF_TOLERANCE = 0.15


def run_once(i: int, total: int) -> dict:
    print(f"\n=== RUN {i}/{total} ===", flush=True)
    t0 = time.time()
    subprocess.run([sys.executable, "evals/run_dod_smoke.py"], check=True)
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    snap = SNAP_DIR / f"run_{time.strftime('%Y%m%d_%H%M%S')}_{i}.json"
    shutil.copy(ARTIFACT, snap)
    print(f"[snapshot] {snap} ({time.time() - t0:.0f}s)", flush=True)
    return json.loads(snap.read_text(encoding="utf-8"))


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    if n < 2:
        print("butuh N >= 2 run untuk berbicara tentang stabilitas")
        return 2

    arts = [run_once(i, n) for i in range(1, n + 1)]
    fails: list[str] = []

    def check(label: str, ok: bool, detail: str) -> None:
        print(f"{'✅' if ok else '❌'} {label} | {detail}", flush=True)
        if not ok:
            fails.append(label)

    # S1 — DECISION NUMBERS identical across runs (the deterministic layer).
    # Phase K rev-2 (lesson from the 18 Sep control run): comparing the WHOLE revenue_state JSON
    # caused a false S1 failure — `reconciliation`/`notes`/`sources` carry evidence-IDs & proof
    # wording that legitimately vary across LLM runs, even though they EXPLAIN the state rather
    # than being the state itself. What must be stable: the numbers that decide the decision +
    # readiness.
    _DECISION_FIELDS = (
        "current_monthly", "target_monthly", "gap_monthly",
        "acquisition_hours_per_week", "delivery_hours_per_week",
        "capacity_utilization", "deals_needed", "avg_deal_size",
        "demand_sufficiency", "demand_volume", "pricing_architecture",
    )
    sigs = []
    for a in arts:
        rs = a.get("revenue_state", {})
        sigs.append(tuple(rs.get(k) for k in _DECISION_FIELDS) +
                    (json.dumps(rs.get("readiness"), sort_keys=True),))
    states = [json.dumps(sig, sort_keys=True) for sig in sigs]
    check("S1 angka keputusan revenue_state IDENTIK", len(set(states)) == 1,
          f"cur/tgt/gap/acq/del/util run1: {arts[0]['revenue_state'].get('current_monthly')}/"
          f"{arts[0]['revenue_state'].get('target_monthly')}/"
          f"{arts[0]['revenue_state'].get('gap_monthly')}/"
          f"{arts[0]['revenue_state'].get('acquisition_hours_per_week')}/"
          f"{arts[0]['revenue_state'].get('delivery_hours_per_week')}/"
          f"{arts[0]['revenue_state'].get('capacity_utilization')}")
    if len(set(states)) != 1:
        for k in _DECISION_FIELDS:
            vals = [a.get("revenue_state", {}).get(k) for a in arts]
            if len(set(map(str, vals))) > 1:
                print(f"   ❌ field beda: {k} = {vals}")

    # S2 — the same KB for every run.
    fps = {a["kb_fingerprint"]["sha256"] for a in arts}
    check("S2 kb_fingerprint IDENTIK", len(fps) == 1, f"sha={sorted(fps)}")

    # S3 — PRIMARY majority (majority voting, the standard non-determinism mitigation).
    primaries = [a.get("primary_constraint_id") for a in arts]
    top, count = collections.Counter(primaries).most_common(1)[0]
    needed = n // 2 + 1
    check(f"S3 PRIMARY mayoritas >= {needed}/{n}", count >= needed,
          f"distribusi={dict(collections.Counter(primaries))} menang={top}({count})")

    # S4 — overall confidence must not jump far across runs.
    # G7-fix (internal-docs §10.2): computed ONLY across runs that agree on the
    # PRIMARY majority — a PRIMARY flip (guarded by S3) legitimately changes conf because the
    # hypothesis score/separation really differs; punishing it again in S4 would make the gate
    # measure the same variance twice. Minority runs are reported as diagnostics, not as a new
    # failure.
    _prim = top
    _maj = [a for a, p in zip(arts, primaries) if p == _prim]
    confs = [a.get("confidence") or 0.0 for a in _maj]
    spread = max(confs) - min(confs)
    check(f"S4 |Δ confidence| <= {CONF_TOLERANCE} (antar-run PRIMARY sama: {len(_maj)}/{n})",
          spread <= CONF_TOLERANCE,
          f"conf={confs} spread={spread:.3f}")

    # S5 — identical epistemic band across runs (F3+ 18 Sep): the product surface
    # (LOW/MEDIUM/HIGH) MUST be more stable than the raw number.
    # G7-fix (internal-docs §10.2): same as S4 — the band is a function of conf,
    # so compare across runs that agree on the PRIMARY majority; minority runs (PRIMARY flip,
    # guarded by S3) are reported as diagnostics.
    bands = [a.get("confidence_band") for a in _maj]
    check(f"S5 confidence_band IDENTIK (antar-run PRIMARY sama: {len(_maj)}/{n})",
          len(set(bands)) == 1,
          f"bands={bands}"
          + (f" | minoritas: {[(p, a.get('confidence_band')) for a, p in zip(arts, primaries) if p != _prim]}"
             if len(_maj) < n else ""))

    # S6 — NBA grounding stable across runs (internal-docs §10): the NBA↔KB
    # linkage must not be full of holes. What is measured is the STATUS (category), not the
    # intervention ID (choice variation across menu items is normal LLM variation — analogous to
    # S3 majority, not S1 identical). GROUNDED/PARTIAL = linked; a valid exit
    # (NO_FIT/NO_KB_SCOPE) counts as a stability pass; UNGROUNDED-with-alternative is accepted
    # for at most 1 run (its flag is informative by itself).
    def _ng_status(a: dict) -> str:
        return ((a.get("knowledge_activation") or {}).get("nba_grounding") or {}).get("status", "MISSING")
    ng = [_ng_status(a) for a in arts]
    n_linked = sum(1 for s in ng if s in ("GROUNDED", "PARTIAL", "NO_FIT", "NO_KB_SCOPE"))
    n_ungrounded = sum(1 for s in ng if s == "UNGROUNDED")
    check(f"S6 NBA grounding linked mayoritas >= {needed}/{n} & MISSING=0",
          "MISSING" not in ng and n_ungrounded <= 1 and n_linked >= needed,
          f"status={dict(collections.Counter(ng))}")

    print()
    if fails:
        print(f"❌ G7 SMOKE STABILITY GAGAL — {len(fails)} kriteria: {fails}")
        print("   Bukan regresi otomatis: bandingkan snapshot di store/stability/,")
        print("   dan lihat internal-docs §10.3 (G5) untuk protokol variasi-vs-regresi.")
        return 1
    print(f"✅ G7 SMOKE STABILITY PASS — {n} run stabil "
          f"(PRIMARY {top} ×{count}/{n}, Δconf {spread:.3f})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
