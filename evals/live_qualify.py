"""S1/S3 — shared LIVE qualification (int 16 R7): one aggregation for all live runners.

Extracted from `run_live_golden.py` (audit 14 Oct 2026, finding P0-B: the diagnostic runner used a
weaker separate aggregation, so `LIVE_PASS` was still possible from incomplete coverage). The verdict
rules that apply are IDENTICAL for every runner:

  - the rate denominator = SCHEDULED attempts (critical cases = `critical_repeats`), not only the
    completed ones;
  - scheduled attempts that are neither completed nor blocked/error -> `missing` -> LIVE_FAIL;
  - critical cases must pass `critical_pass_majority` -> otherwise LIVE_FAIL;
  - zero-tolerance violations, dimension thresholds, absent dimensions, or unclassified
    dimensions -> LIVE_FAIL;
  - an `--only` subset never yields LIVE_PASS;
  - provider blocking (429/1308/401/timeout) -> BLOCKED_EXTERNAL / BLOCKED_EXTERNAL_PARTIAL.

This module also carries shared evidence helpers:

  - `fabricated_revenue_fields()` — canonical `RevenueState` monetary-field validation + provenance
    (audit P0-C: the old assertion read `monthly_revenue`, which does not exist in the schema, so it
    always passed without checking anything);
  - `DIAGNOSTIC_ZERO_TOLERANCE_TYPES` + `enforce_zero_tolerance_types()` — an EXPLICIT adapter from
    the diagnostic corpus's zero-tolerance concepts to the check types that detect them. Concepts
    without a detector are REPORTED (`unmapped`), never dropped silently.

This module never calls a provider and never touches the store — safe to import from tests.
"""
from __future__ import annotations

# ─────────────────────────────────────────────────────────────────────────────────────────────
# Provider blocking (used by runner loops): 429/1308/401/timeout are not semantic failures.
# ─────────────────────────────────────────────────────────────────────────────────────────────


def blocked(exc) -> bool:
    return any(x in f"{type(exc).__name__} {exc}"
               for x in ("429", "1308", "RateLimit", "AuthenticationError", "401"))


# ─────────────────────────────────────────────────────────────────────────────────────────────
# Acceptance normalization — the shared contract for golden thresholds & diagnostic corpus acceptance.
# ─────────────────────────────────────────────────────────────────────────────────────────────


def acceptance_from_thresholds(th: dict) -> dict:
    """Golden THRESHOLDS -> shared acceptance contract."""
    return {
        "zero_tolerance_dims": list(th.get("zero_tolerance_dims") or []),
        "dim_min_rate": dict(th.get("dim_min_rate") or {}),
        "guard_acceptance_min": th.get("guard_acceptance_min"),
        "critical_repeats": int(th.get("critical_repeats", 1)),
        "critical_pass_majority": float(th.get("critical_pass_majority", 0.5)),
    }


def acceptance_from_diagnostic(acc: dict) -> dict:
    """Diagnostic corpus acceptance (JSON keys: zero_tolerance/min_rates) -> shared contract.

    `provider_blocked_class` is not used here — the blocking path is handled by `blocked()` in the
    runner loop. The diagnostic corpus sets no guard acceptance; the guard is skipped explicitly.
    """
    return {
        "zero_tolerance_dims": list(acc.get("zero_tolerance") or []),
        "dim_min_rate": dict(acc.get("min_rates") or {}),
        "guard_acceptance_min": None,
        "critical_repeats": int(acc.get("critical_repeats", 1)),
        "critical_pass_majority": float(acc.get("critical_pass_majority", 0.5)),
    }


# ─────────────────────────────────────────────────────────────────────────────────────────────
# Scheduled attempts + verdict aggregation.
# ─────────────────────────────────────────────────────────────────────────────────────────────


def scheduled_attempts(scenarios, *, only=None, critical_repeats: int = 1,
                       repeats_override: int | None = None) -> list[tuple[str, int]]:
    """LIVE attempts SCHEDULED by the frozen corpus (critical = repeats, others = 1).

    `scenarios` = the list of scenarios ALREADY mode-filtered by each runner — mode filtering stays
    with the runner so the coverage definition is not hidden in here.
    """
    out: list[tuple[str, int]] = []
    for sc in scenarios:
        if only and sc["id"] not in only:
            continue
        reps = repeats_override or (critical_repeats if sc.get("critical") else 1)
        for k in range(reps):
            out.append((sc["id"], k + 1))
    return out


def aggregate(runs, scenarios, acceptance: dict, *, only=None, blocked_ids=None, guard_rate=None,
              repeats_override=None) -> dict:
    """Mechanical verdict from the evidence record (S3-C, int 16). Never PASS from incomplete coverage.

    Canonical port of `run_live_golden.aggregate` with normalized acceptance, so the diagnostic
    runner applies the SAME rules (audit P0-B). Rules:

      - SCHEDULED attempts (not only completed ones) form the rate denominator;
      - a required dimension that is absent / unclassified NEVER counts as PASS;
      - scheduled attempts that did not complete (not blocked/error) -> LIVE_FAIL;
      - zero-tolerance violations and critical cases < majority fail the run;
      - an --only subset is never LIVE_PASS.
    """
    zero_dims = list(acceptance.get("zero_tolerance_dims") or [])
    min_rate = dict(acceptance.get("dim_min_rate") or {})
    guard_min = acceptance.get("guard_acceptance_min")
    crit_majority = float(acceptance.get("critical_pass_majority", 0.5))

    blocked_ = sorted(set(blocked_ids or []))
    completed = [r for r in runs if not r.get("error")]
    errored = [r for r in runs if r.get("error")]
    sched = scheduled_attempts(
        scenarios,
        only=only,
        critical_repeats=int(acceptance.get("critical_repeats", 1)),
        repeats_override=repeats_override,
    )
    by_scenario = {sc["id"]: sc for sc in scenarios}
    sched_ids = {f"{i}#{k}" for i, k in sched}
    completed_map = {f"{r['id']}#{r['rep']}": r for r in completed}
    blocked_set = set(blocked_)
    error_ids = {f"{r['id']}#{r['rep']}" for r in errored}
    missing = sorted(sched_ids - set(completed_map) - blocked_set - error_ids)

    by_dim: dict[str, list[bool]] = {}
    declared_dims: set[str] = set()
    for sid_, k in sched:
        sc = by_scenario.get(sid_)
        if not sc:
            continue
        dims = [ck["dim"] for ck in sc.get("checks", [])]
        declared_dims.update(dims)
        key = f"{sid_}#{k}"
        if key in blocked_set:
            continue  # external failure does not count as a semantic failure
        run = completed_map.get(key)
        if run is None:
            for d in dims:
                by_dim.setdefault(d, []).append(False)
            continue
        got = {c["dim"]: c["ok"] for c in run["checks"]}
        for d in dims:
            by_dim.setdefault(d, []).append(bool(got.get(d, False)))
    rates = {d: round(sum(v) / len(v), 3) for d, v in by_dim.items()}
    observed_dims = {c["dim"] for r in completed for c in r["checks"]}
    missing_dims = sorted(declared_dims - observed_dims)
    unrated_dims = sorted(d for d in observed_dims if d not in zero_dims and d not in min_rate)
    # Zero-tolerance entries NOT used as dimensions in the corpus (e.g. the concept list of the
    # diagnostic corpus) must not evaporate: recorded so enforcement stays traceable/auditable.
    zero_dims_undeclared = sorted(d for d in zero_dims if d not in declared_dims)

    verdicts = {}
    for d in sorted(declared_dims):
        if d not in rates:
            verdicts[d] = "FAIL"
        elif d in zero_dims:
            verdicts[d] = "PASS" if rates[d] == 1.0 else "FAIL"
        elif d in min_rate:
            verdicts[d] = "PASS" if rates[d] >= min_rate[d] else "FAIL"
        else:
            verdicts[d] = "UNRATED"

    critical: dict[str, float] = {}
    crit_fail: list[str] = []
    for sid_ in sorted({s for s, _ in sched}):
        sc = by_scenario.get(sid_) or {}
        if not sc.get("critical"):
            continue
        keys = [f"{sid_}#{k}" for s2, k in sched if s2 == sid_]
        expected = len(keys)
        done = [completed_map[k] for k in keys if k in completed_map]
        passes = sum(1 for r in done if all(c["ok"] for c in r["checks"]))
        frac = round(passes / expected, 3) if expected else 0.0
        critical[sid_] = frac
        if frac < crit_majority:
            crit_fail.append(sid_)

    zero_fail = [d for d in zero_dims if d in declared_dims and verdicts.get(d) != "PASS"]
    dim_fail = [d for d, v in verdicts.items() if v == "FAIL"]
    guard_ok = True if guard_min is None else (guard_rate is not None and guard_rate >= guard_min)

    reasons: list[str] = []
    if not completed:
        status = "BLOCKED_EXTERNAL" if blocked_ else ("PARTIAL" if only else "LIVE_FAIL")
        reasons.append("tidak ada skenario LIVE yang selesai")
    elif errored:
        status = "LIVE_FAIL"
        reasons.append(f"error non-provider: {len(errored)} attempt")
    elif blocked_:
        status = "BLOCKED_EXTERNAL_PARTIAL"
        reasons.append(f"provider terblokir: {blocked_[:5]}")
    elif missing:
        status = "LIVE_FAIL"
        reasons.append(f"attempt terjadwal tidak selesai: {len(missing)}")
    elif missing_dims:
        status = "LIVE_FAIL"
        reasons.append(f"dimensi wajib absen dari cakupan: {missing_dims}")
    elif unrated_dims:
        status = "LIVE_FAIL"
        reasons.append(f"dimensi tak terklasifikasi: {unrated_dims}")
    elif zero_fail:
        status = "LIVE_FAIL"
        reasons.append(f"pelanggaran zero-tolerance: {zero_fail}")
    elif dim_fail:
        status = "LIVE_FAIL"
        reasons.append(f"ambang dimensi gagal: {dim_fail}")
    elif crit_fail:
        status = "LIVE_FAIL"
        reasons.append(f"kasus kritis < majority: {crit_fail}")
    elif not guard_ok:
        status = "LIVE_FAIL"
        reasons.append(f"guard acceptance {guard_rate} < {guard_min}")
    elif only:
        status = "PARTIAL"
        reasons.append("subset --only: bukan cakupan korpus penuh")
    else:
        status = "LIVE_PASS"

    return {
        "status": status, "reasons": reasons,
        "expected_attempts": len(sched), "completed_attempts": len(completed),
        "missing_attempts": missing, "errored_attempts": sorted(error_ids),
        "blocked": blocked_, "rates": rates, "verdicts": verdicts,
        "missing_dims": missing_dims, "unrated_dims": unrated_dims,
        "zero_tolerance_dims_undeclared": zero_dims_undeclared,
        "guard_acceptance": guard_rate, "critical_pass_fraction": critical,
        "zero_tolerance_failures": zero_fail, "only": sorted(only) if only else None,
    }


# ─────────────────────────────────────────────────────────────────────────────────────────────
# Diagnostic corpus zero-tolerance: concept -> detecting check type (EXPLICIT runner adapter).
# The frozen corpus is NOT modified; the mapping must not be freely interpreted — only concepts
# with a real detector in the corpus are mapped. Concepts without a detector are reported `unmapped`.
# ─────────────────────────────────────────────────────────────────────────────────────────────

DIAGNOSTIC_ZERO_TOLERANCE_TYPES: dict[str, tuple[str, ...]] = {
    # D-05: monetary numbers must never appear without a basis.
    "no_fabricated_metric": ("no_fabricated_revenue_metric",),
    # D-01/D-02: superseded claims must never come back as the current state.
    "no_superseded_as_current": ("superseded_absent_from_current", "diagnosis_no_superseded_anchor"),
    # D-04/D-03: a Goal formed from user input must not be rewritten without the user.
    "no_goal_rewrite_without_user": ("goal_metric_preserved", "goal_version_consistent"),
    # OPEN-L5 (15 Oct 2026): a diagnosis on a low-evidence scenario (D-05) must not CLAIM
    # support higher than the evidence — `standing_not_supported` enforces
    # evidence_standing ∈ {INSUFFICIENT, WEAK} exactly there. The concept is now MAPPED
    # (no longer a coverage gap); violations still veto LIVE_PASS.
    "no_false_promotion": ("standing_not_supported",),
}


def enforce_zero_tolerance_types(runs, scenarios, concepts, mapping: dict | None = None):
    """Zero-tolerance concepts -> violations across ALL completed runs (zero-tolerance = 100%).

    Returns `(violations, unmapped)`:
      - `violations` = ["<concept>:<id>#<rep>:<type>", ...] — real violations from the evidence record;
      - `unmapped`   = concepts with no detector at all in the corpus (neither check type nor
        dimension) — reported explicitly so unenforced concepts never disappear silently.

    `mapping` defaults to the diagnostic corpus adapter; other runners may pass their own mapping.
    """
    mapping = mapping if mapping is not None else DIAGNOSTIC_ZERO_TOLERANCE_TYPES
    declared_types = {ck["type"] for sc in scenarios for ck in sc.get("checks", [])}
    declared_dims = {ck["dim"] for sc in scenarios for ck in sc.get("checks", [])}
    violations: list[str] = []
    unmapped: list[str] = []
    for concept in concepts:
        types = set(mapping.get(concept) or ())
        if not (types & declared_types) and concept not in declared_dims:
            unmapped.append(concept)
            continue
        for r in runs:
            if r.get("error"):
                continue
            for c in r.get("checks", []):
                hit = c.get("type") in types or c.get("dim") == concept
                if hit and not c.get("ok"):
                    violations.append(f"{concept}:{r['id']}#{r.get('rep')}:{c.get('type')}")
    return violations, unmapped


# ─────────────────────────────────────────────────────────────────────────────────────────────
# RevenueState — canonical monetary-field validation + provenance (audit P0-C).
# ─────────────────────────────────────────────────────────────────────────────────────────────

REVENUE_STATE_MONEY_FIELDS = ("current_monthly", "target_monthly", "gap_monthly", "avg_deal_size")


def fabricated_revenue_fields(rs) -> list[str]:
    """A CANONICAL `RevenueState` monetary field holding a value WITHOUT provenance in `sources`
    = fabricated.

    Contract (audit P0-C):
      - `revenue_state` not a dict, or MISSING the canonical `current_monthly` field
        -> ["<schema:...>"] — the assertion must NOT pass by reading a field name that does not
        exist (the ghost-field `monthly_revenue` regression);
      - a `None` value never counts (no number, no claim);
      - a value is only VALID when `sources[field]` carries provenance
        (`evidence_id` / `derivation` / `origin`).
    """
    if not isinstance(rs, dict) or "current_monthly" not in rs:
        return ["<schema:current_monthly-hilang>"]
    src = rs.get("sources") or {}
    out: list[str] = []
    for f in REVENUE_STATE_MONEY_FIELDS:
        v = rs.get(f)
        if v is None:
            continue
        ent = src.get(f) or {}
        if not (ent.get("evidence_id") or ent.get("derivation") or ent.get("origin")):
            out.append(f)
    return out
