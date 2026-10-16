"""P-A Goal Model + Goal-Relative semantics (internal-docs §2.1; internal-docs).

Desire ≠ Goal. The user arrives with a desire; the system operationalizes it into a navigable object:

    DESIRE → GOAL {metric_id (registry), direction, baseline, current, target, window,
                    deadline, success_definition}

Goal-Relative (int 09): a Goal need not be a monthly revenue target. Metric semantics come from the
METRIC REGISTRY (`ontology/registry/metric_registry.json`, loader `ontology/registry/metrics.py`):
the per-semantics typed evaluators live in `schema/goal_evaluation.py` — the universal
`target − current` is NO LONGER used as schema semantics (still valid as an INCREASE_TO_THRESHOLD
projection).

Truths preserved (int 09 §2.2, §3):
  - missing ≠ zero; baseline/current/target None = unknown, not 0;
  - the parser proposes; `target_origin` distinguishes explicit input from parse (parse ≠ user
    confirmation);
  - a metric outside the registry is NOT mapped to the nearest revenue slot — it stays a desire +
    unresolved;
  - registry-backed metrics are the only valid ones in the first release (ADR-GR1,
    implementation-log).

Backward compatible: old fields remain; legacy sessions (`metric="revenue_monthly"` without
`metric_id`) are treated as the registry `revenue_monthly` via `resolved_metric_id()` — GR-07.
"""
from __future__ import annotations

import re
import time
import uuid
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from ontology.registry import metrics as metric_registry

TargetOrigin = Literal["explicit_input", "goal_marker", "intent_phrase", "goal_fallback", "none"]
GoalStatus = Literal["DRAFT", "ACTIVE", "ACHIEVED", "PAUSED", "STOPPED", "ARCHIVED"]

# Unresolved codes (int 09 §2.2/§3.2) — UNKNOWN ≠ ABSENT; used by the Phase 2 readiness gate.
UNRESOLVED_METRIC = "METRIC_UNRESOLVED"          # intent present, metric not identified yet
UNRESOLVED_METRIC_UNSUPPORTED = "GOAL_METRIC_UNSUPPORTED"  # metric clear but outside the registry (GR-17)
UNRESOLVED_DIRECTION = "DIRECTION_MISSING"
UNRESOLVED_TARGET = "TARGET_MISSING"
UNRESOLVED_WINDOW = "WINDOW_MISSING"                   # COUNT_IN_WINDOW without a window
UNRESOLVED_DENOMINATOR = "DENOMINATOR_MISSING"         # RATE_OR_RATIO without a cohort/denominator (GR-02)
UNRESOLVED_QUALIFICATION = "QUALIFICATION_UNDEFINED"   # count without qualification criteria (GR-04/GR-09)
UNRESOLVED_ACTIVITY = "ACTIVITY_NOT_OUTCOME"           # an activity requested as a Goal (GR-06)
UNRESOLVED_BASELINE = "BASELINE_UNKNOWN"


def _unresolved(code: str, detail: str) -> dict[str, str]:
    return {"code": code, "detail": detail}


class Goal(BaseModel):
    """A navigable goal object — prerequisite for Revenue Navigation Maps (one map per goal).

    Goal-Relative fields (int 09 §2.1): identity/lifecycle (`goal_id`, `version`, `status`,
    `effective_ts`), metric semantics (`metric_id` + `metric_version` → registry, `direction`,
    `category`, `scope`, `measurement_window_days`), values (`baseline`/`current`/`target`/
    `target_min`/`target_max` — None = unknown, NOT zero), relations (`guardrails`,
    `supporting_metrics`), and explicit uncertainty (`unresolved`).
    """

    # ── identity & lifecycle (goal-scoped; the workspace manages the collection in Phase 3) ──
    goal_id: str = Field(default="", description='Stable Goal ID; empty = legacy/not yet requested')
    workspace_id: str = ""
    status: GoalStatus = "ACTIVE"
    version: int = 1
    effective_ts: Optional[int] = None

    # ── metric semantics (registry-backed; ADR-GR1) ──
    metric: str = Field(default="revenue_monthly", description="label metric legacy; truth = metric_id")
    metric_id: str = Field(default="", description="referensi ontology/registry/metric_registry.json")
    metric_version: Optional[int] = None
    category: str = ""
    direction: str = Field(default="", description="semantics registry — typed evaluator")
    unit: str = "Rp juta/bulan"
    scope: str = ""
    measurement_window_days: Optional[int] = None

    # ── values (None = unknown — missing ≠ zero) ──
    baseline: Optional[float] = None
    current: Optional[float] = None
    target: Optional[float] = None
    target_min: Optional[float] = None
    target_max: Optional[float] = None
    deadline_days: Optional[int] = None
    success_definition: str = Field(
        default="", description=(
                                'observable success definition — MAY contain constraints'
                                '(hours/week, etc.)'
                                )   )
    target_origin: TargetOrigin = "none"
    target_claim_id: str = Field(
        default="",
        description="R4: id of the canonical claim the target came from (empty = explicit input/legacy)",
    )
    target_precision: str = Field(
        default="exact", description="R4: exact|approximate|range|upper_bound|lower_bound")

    # ── relations & explicit uncertainty ──
    guardrails: list[dict] = Field(default_factory=list)
    supporting_metrics: list[dict] = Field(default_factory=list)
    unresolved: list[dict] = Field(default_factory=list, description="[{code, detail}] — unknown")
    desire: str = Field(default="", description=(
                                                "the user's original desire, not yet"
                                                'operationalized'
                                                ))
    motivation: str = ""
    notes: list[str] = Field(default_factory=list)

    # ── helpers ──
    def resolved_metric_id(self) -> str:
        """Effective metric_id: explicit, or legacy `metric='revenue_monthly'` → registry id (GR-07)."""
        if self.metric_id:
            return self.metric_id
        if self.metric == "revenue_monthly":
            return "revenue_monthly"
        return ""

    def metric_definition(self) -> dict[str, Any] | None:
        mid = self.resolved_metric_id()
        return metric_registry.metric_by_id(mid) if mid else None

    def confirmed_target(self) -> bool:
        """Parse ≠ user confirmation (int 09 §2.1 target_origin): only explicit_input = confirmed."""
        return self.target_origin == "explicit_input"


# ───────────────────────────────── parser (deterministic, 0 LLM) ─────────────────────────────────

_NUM = r"([\d.,]+)\s*(juta|jt|ribu|rb|million|thousand|m|k)?\b"
_RE_TARGET = re.compile(rf"target[^.{{}}]{{0,60}}?rp\s*{_NUM}")
_RE_BASELINE = re.compile(rf"(?:baseline|dari|sekarang|saat ini)[^.{{}}]{{0,60}}?rp\s*{_NUM}")
_RE_FALLBACK_RP = re.compile(rf"rp\s*{_NUM}")
_RE_DEADLINE = re.compile(r"(\d{1,3})\s*(hari|minggu|bulan|day|days|week|weeks|month|months)")

# Bug E2E 21 Sep: the common user format "penghasilan 8jt/bln ... ingin 25jt/bln" does NOT
# use "Rp" — the old parser produced target=None. Two additional patterns (without Rp):
_RE_BASELINE_NUM = re.compile(
    r"(?:penghasilan|omset|omzet|revenue|pendapatan|dapet|sekarang|current(?:ly)? make|we make)"
    r"[^.{}\d]{0,30}?"
    r"(\d+(?:[.,]\d+)?)\s*(juta|jt|ribu|rb|million|thousand|m|k)\b"
)
_RE_TARGET_NUM = re.compile(
    r"(?:target|ingin|mau|capai|naik\s+ke|jadi|want|reach)[^.{}\d]{0,40}?"
    r"(\d+(?:[.,]\d+)?)\s*(juta|jt|ribu|rb|million|thousand|m|k)\b(?:/(?:bulan|bln|mo|month))?"
)

_EN_NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
                 "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12}
_RE_INT = r"(\d{1,4}|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
_RE_PCT = re.compile(r"(\d{1,3}(?:[.,]\d+)?)\s*(?:%|persen|percent)")
_RE_RP_THOUSAND = re.compile(r"rp\s*([\d.,]+)\s*(ribu|rb|k)?", re.I)
_RE_WINDOW_EN = re.compile(r"(?:within|in|dalam|next)\s+(\d{1,3})\s*(day|days|hari|week|weeks|minggu)", re.I)

# A-12/A-13 (UC-05): guardrail clauses are split out of the PRIMARY text before numbers are scanned.
# Baseline bug (reproduced at e6c04a5): the first percentage of the WHOLE text was used as the
# margin threshold — primary baseline/target numbers (15% -> 25%) could be read as
# guardrails, and guardrail numbers (35%) could become the primary baseline/target when the
# clause order flips. Contract: primary values are read ONLY from text outside the guardrail
# zone; guardrail thresholds are read ONLY from their own clause segment.
_RE_GUARDRAIL_ZONE = re.compile(
    r"(?:\b(?:while|sambil|dengan)\s+)?"
    r"\b(?:maintaining|keeping|ensuring|without\s+(?:dropping|letting|sacrificing)"
    r"|menjaga|memastikan|tanpa\s+(?:menurunkan|mengorbankan))\b", re.I)
_CLAUSE_SPLIT_KEEP = re.compile(r"([,;]|\band\b|\bdan\b)", re.I)
_GUARDRAIL_KEYWORD = re.compile(r"\b(?:rate|margin|ratio|churn|refund|cost)\b", re.I)


def _segment_has_role(seg_l: str, role: str) -> bool:
    for m in metric_registry.metrics():
        if m.get("role") != role:
            continue
        if any(a in seg_l for a in (m["metric_id"], *m.get("aliases", []))):
            return True
    return False


def _split_guardrail_zone(t: str) -> tuple[str, str]:
    """(primary_text, guardrail_zone) - 'while maintaining/keeping/menjaga ...' clauses are excluded
    from the text scanned for primary values. The zone continues through its clause segments
    ('and ...', ', ...') and STOPS at a segment that mentions the primary metric again, so a
    reversed clause order ('While maintaining margin 35%, grow close rate 15% ke 25%')
    still reads the primary target correctly."""
    m = _RE_GUARDRAIL_ZONE.search(t)
    if not m:
        return t, ""
    zone, tail, to_tail = "", "", False
    for item in _CLAUSE_SPLIT_KEEP.split(t[m.start():]):
        if to_tail:
            tail += item
            continue
        if _CLAUSE_SPLIT_KEEP.fullmatch(item):
            zone += item
            continue
        seg = item.lower().strip()
        if seg and _segment_has_role(seg, "outcome") and not _segment_has_role(seg, "guardrail"):
            to_tail = True
            tail += item
        else:
            zone += item
    head = t[:m.start()]
    primary = (head.rstrip() + (" " + tail.lstrip() if tail.strip() else "")).strip()
    return (primary or head), zone


def _guardrail_rows(zone: str) -> tuple[list[dict], list[str]]:
    """Measurable guardrails FROM THEIR OWN CLAUSE ZONE (A-12): a registry metric with the guardrail
    role mentioned in the same segment as its percentage -> threshold (unit 'ratio' via percent).
    A guardrail mention without registry support is reported as an explicit note —
    never evaluated silently and never dropped quietly (int 09 §3.3)."""
    rows: list[dict] = []
    unsupported: list[str] = []
    for seg in _CLAUSE_SPLIT_KEEP.split(zone):
        seg_l = seg.lower()
        if not seg_l.strip() or _CLAUSE_SPLIT_KEEP.fullmatch(seg_l.strip()):
            continue
        pm = _RE_PCT.search(seg_l)
        hit = next((gm for gm in metric_registry.metrics() if gm.get("role") == "guardrail"
                    and any(a in seg_l for a in (gm["metric_id"], *gm.get("aliases", [])))), None)
        if hit is None:
            if pm and _GUARDRAIL_KEYWORD.search(seg_l):
                unsupported.append(seg_l.strip()[:100])
            continue
        if pm is None:
            continue  # metric mentioned without a readable number — not a measurable guardrail
        val = _pct_to_ratio(pm.group(1))
        row: dict[str, Any] = {"metric_id": hit["metric_id"], "relation": "GUARDS",
                               "semantics": hit["semantics"]}
        if hit["semantics"] in ("AT_LEAST", "INCREASE_TO_THRESHOLD"):
            row["min"] = val
        elif hit["semantics"] in ("AT_MOST", "DECREASE_TO_THRESHOLD"):
            row["max"] = val
        else:
            unsupported.append(seg_l.strip()[:100])  # a range needs two bounds — never invent one
            continue
        rows.append(row)
    return rows, unsupported


def _to_float(num: str, mult: str | None) -> float:
    v = _num_en_id(num) or 0.0
    if mult in ("ribu", "rb", "thousand", "k"):
        v /= 1000.0
    return v


def _int_of(word: str) -> int:
    w = word.lower()
    if w in _EN_NUM_WORDS:
        return _EN_NUM_WORDS[w]
    try:
        return int(w)
    except ValueError:
        return 0


def _window_days(text: str) -> int | None:
    m = _RE_WINDOW_EN.search(text)
    if not m:
        m2 = _RE_DEADLINE.search(text)
        if not m2:
            return None
        n, unit = int(m2.group(1)), m2.group(2)
        return n * (30 if unit in ("bulan", "month", "months")
                    else 7 if unit in ("minggu", "week", "weeks") else 1)
    n = int(m.group(1))
    unit = m.group(2).lower()
    return n * (7 if unit in ("week", "weeks", "minggu") else 1)


def _pct_to_ratio(raw: str) -> float:
    return round(float(raw.replace(",", ".")) / 100.0, 4)


def _num_en_id(raw: str) -> float | None:
    """Numbers with mixed EN/ID separators: '80,000'/'80.000' = 80000; '1.234,5' = 1234.5."""
    s = raw.strip()
    if "," in s and "." in s:  # 1.234.567,89 (full ID format)
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        head, _, tail = s.partition(",")
        s = head + tail if len(tail) == 3 else head + "." + tail  # 80,000 vs 80,5
    elif "." in s:
        head, _, tail = s.partition(".")
        s = head + tail if len(tail) == 3 else s  # 80.000 vs 80.5
    try:
        return float(s)
    except ValueError:
        return None


def _rp_ribu(raw: str, mult: str | None) -> float | None:
    """Rp amount → unit registry 'Rp ribu' (CAC). Rp80,000 / Rp800rb / Rp800k → 800."""
    v = _num_en_id(raw)
    if v is None:
        return None
    if mult in ("ribu", "rb", "k"):
        return round(v, 1)
    return round(v / 1000.0, 1)


def _parse_typed(text_lower: str, mdef: dict) -> dict:
    """Extract values per registry semantics. Reads literal numbers only — nothing is invented.
    Returns a dict of Goal arguments; the caller appends unresolved entries."""
    sem = mdef["semantics"]
    mid = mdef["metric_id"]
    out: dict[str, Any] = {
        "metric_id": mid, "metric_version": mdef["version"], "metric": mdef["display_name"]["en"],
        "direction": sem, "category": mdef.get("category", ""), "unit": mdef["unit"],
    }
    if sem == "COUNT_IN_WINDOW":
        alts = sorted(
            [mdef["metric_id"].replace("_", " "), *mdef.get("aliases", [])],
            key=len, reverse=True)
        words = "|".join(re.escape(a) for a in alts)
        m = re.search(
            rf"{_RE_INT}\s+(?:[a-z]+\s+){{0,2}}?(?:qualified\s+|terkualifikasi\s+)?(?:{words})",
            text_lower)
        if m:
            out["target"] = float(_int_of(m.group(1)))
        w = _window_days(text_lower)
        if w:
            out["measurement_window_days"] = w
    elif sem == "RATE_OR_RATIO":
        pcts = _RE_PCT.findall(text_lower)
        if len(pcts) >= 2:
            out["baseline"] = _pct_to_ratio(pcts[0])
            out["target"] = _pct_to_ratio(pcts[1])
        elif len(pcts) == 1:
            out["target"] = _pct_to_ratio(pcts[0])
    elif sem == "DECREASE_TO_THRESHOLD" and mid == "cac":
        rps = _RE_RP_THOUSAND.findall(text_lower)
        vals = [v for v in (_rp_riba_safe(r, mlt) for r, mlt in rps) if v is not None]
        if len(vals) >= 2:
            out["baseline"], out["target"] = vals[0], vals[-1]
        elif vals:
            out["target"] = vals[0]
    elif sem == "DECREASE_TO_THRESHOLD" and mid == "founder_delivery_hours":
        hrs = re.findall(r"(\d{1,3})(?:[.,]\d+)?\s*(?:hours?|jam)", text_lower)
        if len(hrs) >= 2:
            out["baseline"], out["target"] = float(hrs[0]), float(hrs[-1])
        elif hrs:
            out["target"] = float(hrs[0])
    elif sem == "EVIDENCE_CRITERIA":
        out["target"] = None  # success = evidence criteria, not a number (GR-11)
    d = _window_days(text_lower)
    if d and sem != "COUNT_IN_WINDOW" and not out.get("deadline_days"):
        out["deadline_days"] = d
    return out


def _rp_riba_safe(raw: str, mult: str | None) -> float | None:
    return _rp_ribu(raw, mult)


def extract_qualification_definition(text: str) -> str:
    """Explicit qualification definition sentence ("A qualified lead is ...") — kept separate from
    number scanning, so M4 clarification can still CLEAR the qualification criteria of a typed
    goal even when the same sentence carries an Rp fact (which would pull the metric scan onto
    the revenue path). Parsed-unconfirmed: not a verified claim."""
    mq = re.search(
        r"(?:qualified|terkualifikasi|kualifikasi)[^.]{0,60}?"
        r"(?:is|are|adalah|means|artinya|yaitu)\s*([^.]{8,200})",
        (text or ""), re.I)
    return mq.group(1).strip() if mq else ""


def parse_goal_text(goal_text: str) -> Goal:
    """Deterministic Goal extraction from free text.

    Decision order (int 09 §3.1 — registry first, not a revenue default):
      1. a non-revenue metric alias matches → typed parse per registry semantics;
      2. the `revenue_monthly` alias / an Rp pattern → the legacy revenue path (origin recorded);
      3. neither → the Goal stays a DESIRE + unresolved METRIC_UNRESOLVED (e.g. "traction").
    Origins tracked: goal_marker (strongest) / intent_phrase (medium) / goal_fallback (weak — guarded).
    """
    g = Goal()
    t = (goal_text or "").lower()
    if not t.strip():
        return g
    # A-12/A-13: split the guardrail zone BEFORE numbers are scanned — primary values are
    # never read from guardrail clauses, and vice versa.
    primary_text, guard_zone = _split_guardrail_zone(t)

    typed = metric_registry.match_metric_text(goal_text)
    if typed and typed.get("role") == "guardrail":
        # UC-05/GR-24: a guardrail metric (e.g. margin) never becomes PRIMARY when another
        # outcome metric is also mentioned — it goes into goal.guardrails, not replacing the target.
        primary = metric_registry.match_metric_text(goal_text, exclude={typed["metric_id"]})
        if primary and primary.get("role") != "guardrail":
            typed = primary
    if typed and typed["metric_id"] != "revenue_monthly":
        args = _parse_typed(primary_text, typed)
        for k, v in args.items():
            if v or isinstance(v, (int, float)):
                setattr(g, k, v)
        g.target_origin = "intent_phrase" if g.target is not None else "none"
        if typed["semantics"] == "COUNT_IN_WINDOW":
            if g.measurement_window_days is None:
                g.unresolved.append(_unresolved(
                    UNRESOLVED_WINDOW, f"window pengukuran {typed['metric_id']} belum dinyatakan"))
            if typed.get("requires_qualification") and not g.success_definition:
                # explicit qualification definition sentence ("A qualified lead is ..." / similar ID forms)
                mq = re.search(
                    r"(?:qualified|terkualifikasi|kualifikasi)[^.]{0,60}?"
                    r"(?:is|are|adalah|means|artinya|yaitu)" + chr(92) + "s*([^.]{8,200})",
                    goal_text, re.I)
                if mq:
                    g.success_definition = mq.group(1).strip()
                    g.notes.append("kriteria kualifikasi dari kalimat definisi user (parsed, unconfirmed)")
                else:
                    g.unresolved.append(_unresolved(
                        UNRESOLVED_QUALIFICATION,
                        f"kriteria '{typed['display_name']['en']}' belum didefinisikan (observable)"))
        if typed["semantics"] == "RATE_OR_RATIO":
            if g.target is None:
                g.unresolved.append(_unresolved(UNRESOLVED_TARGET, "angka rate belum terbaca"))
            g.unresolved.append(_unresolved(
                UNRESOLVED_DENOMINATOR,
                "rate butuh denominator/kohort/window yang sebanding — persentase saja tidak cukup (GR-02)"))
        if typed["role"] == metric_registry.ROLE_ACTIVITY:
            g.unresolved.append(_unresolved(
                UNRESOLVED_ACTIVITY,
                "metric berperan ACTIVITY — klarifikasi: kuota kerja atau proxy outcome? (GR-06)"))
        d = _window_days(t)
        if d and g.deadline_days is None:
            g.deadline_days = d
        # Explicit guardrails are separated from the Primary Goal (int 09 §2.1/§4.5 — not silent
        # weights): thresholds are read ONLY from their own clause (A-12), not the text's first percent.
        if guard_zone:
            rows, unsupported = _guardrail_rows(guard_zone)
            g.guardrails.extend(rows)
            for seg in unsupported:
                g.notes.append(
                    "guardrail disebut tanpa dukungan registry — tidak dievaluasi otomatis: " + seg)
        return g

    # legacy revenue path (registry revenue_monthly implied when an Rp pattern matches)
    m = _RE_TARGET.search(primary_text)
    if m:
        g.target = _to_float(m.group(1), m.group(2))
        g.target_origin = "goal_marker"
    else:
        m = _RE_TARGET_NUM.search(primary_text)
        if m:
            g.target = _to_float(m.group(1), m.group(2))
            # the 'target' keyword was checked above; the rest (ingin/mau/capai) = intent_phrase
            g.target_origin = "intent_phrase"
            g.notes.append("target dari frasa niat + angka (tanpa kata 'target'/'Rp')")
        else:
            m = _RE_FALLBACK_RP.search(primary_text)
            if m:
                g.target = _to_float(m.group(1), m.group(2))
                g.target_origin = "goal_fallback"
                g.notes.append("target dari fallback 'Rp pertama' — asal lemah, guard downstream aktif")

    m = _RE_BASELINE.search(primary_text)
    if m:
        g.baseline = _to_float(m.group(1), m.group(2))
    else:
        m = _RE_BASELINE_NUM.search(primary_text)
        if m:
            g.baseline = _to_float(m.group(1), m.group(2))

    m = _RE_DEADLINE.search(t)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        g.deadline_days = n * (30 if unit in ("bulan", "month", "months")
                               else 7 if unit in ("minggu", "week", "weeks") else 1)

    if g.target is not None or g.baseline is not None:
        # a revenue pattern matched → explicit registry metric revenue_monthly
        g.metric_id = "revenue_monthly"
        g.metric_version = 1
        g.direction = metric_registry.SEMANTICS_INCREASE_TO_THRESHOLD
        g.category = "revenue"
    else:
        # no metric & no numbers → pure desire (GR-05: "traction").
        # The metric label is CLEARED: the legacy revenue_monthly default is not a universal Goal
        # rule (int 09 §7.1 — "Fake non-revenue Goals inside monthly revenue fields" rejected).
        g.metric = ""
        g.unresolved.append(_unresolved(
            UNRESOLVED_METRIC, "hasil bisnis yang dimaksud belum teridentifikasi — klarifikasi diperlukan"))
    return g


def mint_goal_id() -> str:
    """Stable ID for a new Goal (the workspace persists it across sessions — Phase 3)."""
    return f"goal_{uuid.uuid4().hex[:10]}"


def build_goal(
    goal_text: str,
    *,
    desire: str = "",
    motivation: str = "",
    target: float | None = None,
    baseline: float | None = None,
    deadline_days: int | None = None,
    success_definition: str = "",
    metric_id: str = "",
    direction: str = "",
    category: str = "",
    unit: str = "",
    scope: str = "",
    measurement_window_days: int | None = None,
    target_min: float | None = None,
    target_max: float | None = None,
    goal_id: str = "",
    workspace_id: str = "",
) -> Goal:
    """Single entry point: structured (API) input wins; remaining fields are parsed from goal_text.
    Explicit input is NEVER overwritten by the parser.

    Metric registry contract (ADR-GR1): an explicit `metric_id` MUST be registered — unknown
    → ValueError (the API caller maps it to 422; GR-17 abstention for free text is handled by the
    parser, not here). An explicit `direction` must be a registry semantics enum and compatible
    with the metric (hard-rejected: this is a contract, not a guess)."""
    g = parse_goal_text(goal_text)
    if desire:
        g.desire = desire
    if motivation:
        g.motivation = motivation
    if metric_id:
        mdef = metric_registry.metric_by_id(metric_id)
        if mdef is None:
            raise ValueError(
                f"metric_id {metric_id!r} tidak terdaftar di metric registry "
                f"({metric_registry.registry_version()}) — metric di luar registry tidak sah "
                "di rilis pertama (ADR-GR1); sampaikan maksud sebagai teks bebas agar diklarifikasi"
            )
        g.metric_id = mdef["metric_id"]
        g.metric_version = mdef["version"]
        g.direction = mdef["semantics"]
        g.category = mdef.get("category", "")
        g.unit = mdef["unit"]
    if direction:
        if direction not in metric_registry.ALL_SEMANTICS:
            raise ValueError(
                f"direction {direction!r} bukan semantics registry {metric_registry.ALL_SEMANTICS}")
        mdef = g.metric_definition()
        if mdef and direction != mdef["semantics"] and (direction, mdef["semantics"]) not in {
                ("AT_LEAST", "INCREASE_TO_THRESHOLD"), ("INCREASE_TO_THRESHOLD", "AT_LEAST"),
                ("AT_MOST", "DECREASE_TO_THRESHOLD"), ("DECREASE_TO_THRESHOLD", "AT_MOST"),
                ("MAINTAIN_RANGE", "AT_LEAST"), ("AT_LEAST", "MAINTAIN_RANGE"),
            }:
            raise ValueError(
                f"direction {direction!r} tidak kompatibel dengan semantics metric "
                f"{g.resolved_metric_id()!r} ({mdef['semantics']})")
        g.direction = direction
    if category:
        g.category = category
    if unit:
        g.unit = unit
    if scope:
        g.scope = scope
    if target is not None:
        g.target = target
        g.target_origin = "explicit_input"
    if target_min is not None:
        g.target_min = target_min
    if target_max is not None:
        g.target_max = target_max
    if baseline is not None:
        g.baseline = baseline
    if measurement_window_days is not None:
        g.measurement_window_days = measurement_window_days
    if deadline_days is not None:
        g.deadline_days = deadline_days
    if success_definition:
        g.success_definition = success_definition
    if goal_id:
        g.goal_id = goal_id
    if workspace_id:
        g.workspace_id = workspace_id
    g.effective_ts = g.effective_ts or int(time.time())
    return g


def goal_gap(g: Goal) -> dict[str, Any]:
    """Gap projection — VALID only for INCREASE_TO_THRESHOLD (int 09 §3.2); typed evaluation
    lives in goal_evaluation.evaluate_goal. Kept for revenue projection compatibility."""
    if g.target is None or g.current is None:
        return {"target": g.target, "current": g.current, "gap": None,
                "computable": False}
    return {"target": g.target, "current": g.current,
            "gap": round(g.target - g.current, 2), "computable": True}
