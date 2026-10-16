"""Guard for narrative contradictions against the structured Goal (round 4, Phase 5). Deterministic, 0 LLM.

The problem it closes: a compliant prompt and mock are NOT a guarantee. A real provider can
write a fluent explanation that contradicts the session's structured Goal (a different metric
target, a current value that was never measured, an old target after a revision, a causal claim
for a relation that is still UNKNOWN, another session's Goal). This guard sits at the OUTPUT
boundary of the narrative (PlainExplain, TALK answers, DiagnosisDraft): it compares CLAIMS
against authoritative facts, not merely "the number must appear in a global pool".

What it distinguishes (mandate §6.4): the current Primary Goal; the authoritative
metric/unit/target/window; supporting metrics & guardrails (legitimate to mention);
measured vs not-yet-measured current values; parsed vs confirmed target; UNKNOWN vs
supported relation; facts of this session vs other Goals in the workspace.

The unit of analysis = the CLAUSE. A clause stating a goal/target ("your goal is ...",
"target ...") may only contain quantities and metrics belonging to the active Goal. A clause
stating the CURRENT value for the Goal metric must match the measurement, or state "not yet
measured". Quotes of the user's own words (in quotation marks) are excluded from analysis:
they are not a claim by the system.

Output: {code: [reason]} per field; the code is stable and safe to record (no sensitive text).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from ontology.registry import metrics as metric_registry

# ── violation codes ──────────────────────────────────────────────────────────────────
FOREIGN_TARGET = "FOREIGN_TARGET"                    # goal quantity does not belong to the active Goal
STALE_TARGET = "STALE_TARGET"                        # old-version target presented as the goal
FOREIGN_METRIC = "FOREIGN_METRIC"                    # another metric stated as the user's goal
OTHER_GOAL = "OTHER_GOAL_CONTEXT"                    # another Goal's context stated as the active goal
UNIT_CONFLICT = "UNIT_CONFLICT"                      # percentage/scale does not match the metric unit
WINDOW_MISMATCH = "WINDOW_MISMATCH"                  # number of days is not the Goal window/deadline
CURRENT_NOT_MEASURED = "CURRENT_NOT_MEASURED"        # current value claimed although not yet measured
CURRENT_MISMATCH = "CURRENT_MISMATCH"                # current value claimed different from the measurement
CROSS_UNIT_CURRENT = "CROSS_UNIT_CURRENT"            # money value borrowed as a non-money current metric
CAUSAL_ON_UNKNOWN = "CAUSAL_ON_UNKNOWN_RELATION"     # causal claim on UNKNOWN Goal relation
ACHIEVED_WITHOUT_EVIDENCE = "ACHIEVED_WITHOUT_EVIDENCE"  # 'tercapai' without an ACHIEVED evaluation
TARGET_NOT_CONFIRMED = "TARGET_NOT_CONFIRMED"        # 'Anda menetapkan' target only parsed

GOAL_CODES = frozenset({
    FOREIGN_TARGET, STALE_TARGET, FOREIGN_METRIC, OTHER_GOAL, UNIT_CONFLICT, WINDOW_MISMATCH,
    CURRENT_NOT_MEASURED, CURRENT_MISMATCH, CROSS_UNIT_CURRENT, CAUSAL_ON_UNKNOWN,
    ACHIEVED_WITHOUT_EVIDENCE, TARGET_NOT_CONFIRMED})

_DAY_METRIC_UNITS = {"leads", "partners", "inquiries", "messages"}
_EXTRA_NAMES = {
    "revenue_monthly": ("revenue", "income", "earnings", "omzet", "pendapatan", "penghasilan"),
}
_GENERIC_ALIASES = {"margin", "partners", "partnership", "balasan", "signups", "inquiries", "inquiry"}


@dataclass(frozen=True)
class GoalFacts:
    """Authoritative facts of the active Goal for one narrative evaluation
    (derived from the Goal record + state)."""
    metric_id: str = ""
    names: tuple[str, ...] = ()
    unit: str = ""
    semantics: str = ""
    target: float | None = None
    target_min: float | None = None
    target_max: float | None = None
    window_days: float | None = None
    deadline_days: float | None = None
    current: float | None = None            # None = not yet measured (missing ≠ zero)
    baseline: float | None = None
    target_confirmed: bool = False
    allowed_metric_ids: frozenset[str] = frozenset()   # guardrail + supporting (legitimate to mention)
    guardrail_values: tuple[float, ...] = ()
    unknown_relation: bool = False
    achieved: bool = False
    stale_targets: tuple[float, ...] = ()
    check_current: bool = True              # False: the current value cannot yet be verified at this stage
    other_goals: tuple[dict, ...] = field(default_factory=tuple)   # {goal_id, metric_id, target}

    @property
    def is_money(self) -> bool:
        return self.unit.lower().startswith("rp")

    @property
    def ratio(self) -> bool:
        return self.unit == "ratio"


# ── facts from the record ──────────────────────────────────────────────────────────────

def _fnum(v: Any) -> float | None:
    try:
        return None if v is None or isinstance(v, bool) else float(v)
    except (TypeError, ValueError):
        return None


def _names_of(mid: str) -> tuple[str, ...]:
    m = metric_registry.metric_by_id(mid) or {}
    out = {mid.replace("_", " "), *(a.lower() for a in m.get("aliases", [])),
           (m.get("display_name") or {}).get("en", "").lower(), *_EXTRA_NAMES.get(mid, ())}
    return tuple(sorted(n for n in out if n))


def goal_facts_of(
    goal: dict | None, *, revenue_state: dict | None = None, relations: Iterable[str] = (),
    other_goals: Iterable[dict] = (), history: Iterable[dict] = (), measured_current: float | None = None,
    achieved: bool = False, check_current: bool = True,
) -> GoalFacts:
    """GoalFacts from the session Goal record (authority), revenue state (current revenue), path relations,
    other Goals in the workspace, and revision history (old targets). Without a structured Goal → empty facts
    (the guard becomes a no-op: legacy behavior intact)."""
    g = goal or {}
    mid = g.get("metric_id") or ("revenue_monthly" if g.get("metric") == "revenue_monthly" else "")
    if not mid:
        return GoalFacts()
    mdef = metric_registry.metric_by_id(mid) or {}
    unit = g.get("unit") or mdef.get("unit") or ""
    rs = revenue_state or {}
    current = _fnum(measured_current)
    if current is None:
        current = _fnum(rs.get("current_monthly")) if mid == "revenue_monthly" else _fnum(g.get("current"))
    allowed = {mid}
    guard_vals: list[float] = []
    for row in list(g.get("guardrails") or []) + list(g.get("supporting_metrics") or []):
        if isinstance(row, dict) and row.get("metric_id"):
            allowed.add(row["metric_id"])
            for k in ("min", "max"):
                if _fnum(row.get(k)) is not None:
                    guard_vals.append(_fnum(row[k]))
    cur_t = _fnum(g.get("target"))
    stale = tuple(sorted({t for t in (_fnum(h.get("target")) for h in history) if t is not None
                          and t != cur_t}))
    return GoalFacts(
        metric_id=mid, names=_names_of(mid), unit=unit,
        semantics=g.get("direction") or mdef.get("semantics", ""),
        target=cur_t, target_min=_fnum(g.get("target_min")), target_max=_fnum(g.get("target_max")),
        window_days=_fnum(g.get("measurement_window_days")), deadline_days=_fnum(g.get("deadline_days")),
        current=current, baseline=_fnum(g.get("baseline")),
        target_confirmed=g.get("target_origin") == "explicit_input",
        allowed_metric_ids=frozenset(allowed), guardrail_values=tuple(guard_vals),
        unknown_relation=any(r == "UNKNOWN_RELATION" for r in relations),
        achieved=bool(achieved) or g.get("status") == "ACHIEVED", stale_targets=stale,
        check_current=check_current,
        other_goals=tuple({"goal_id": o.get("goal_id", ""), "metric_id": o.get("metric_id", ""),
                           "target": _fnum(o.get("target"))} for o in other_goals
                          if o.get("goal_id") != g.get("goal_id")),
    )


# ── clauses and quantities ─────────────────────────────────────────────────────────────

_QUOTED = re.compile(r"[“\"][^”\"]{0,300}[”\"]")
_CLAUSE_SPLIT = re.compile(r"(?<=[.!?;:])\s+|\n+|\s+(?:but|while|although|whereas|however)\s+", re.I)
_GOAL_CUE = re.compile(
    r"\b(?:goal|target|aim(?:s|ed|ing)?|objective|want(?:s)? to (?:reach|hit|get to)|"
    r"need(?:s)? to (?:reach|hit)|"
    r"trying to reach|tujuan|sasaran|ingin mencapai|mau mencapai)\b", re.I)
_CURRENT_CUE = re.compile(
    r"\b(?:now|currently|right now|today|so far|at the moment|already|sekarang|saat ini|sejauh ini|"
    r"sudah)\b", re.I)
_ATTRIB = re.compile(
    r"\b(?:you (?:said|told us|mentioned|wrote|shared|stated|described)|according to you|in your own words|"
    r"anda (?:bilang|sebut|cerita|tulis)|katamu)\b", re.I)
_NEG = re.compile(
    r"\b(?:not|no|never|none|nothing|without|isn't|aren't|hasn't|haven't|belum|tidak|tanpa)\b|n't\b", re.I)
_MONEY = re.compile(
    r"(?:rp\.?\s?(\d[\d.,]*)\s*(juta|jt|million|mio|ribu|rb|miliar|billion)?|"
    r"(\d[\d.,]*)\s*(juta|jt|million|ribu|rb|miliar|billion)\s*(?:rupiah)?)", re.I)
_PERCENT = re.compile(r"(\d[\d.,]*)\s*(?:%|percent|persen)", re.I)
_DAYS = re.compile(r"(\d[\d.,]*)\s*(?:days?|hari)\b", re.I)
_COUNT = re.compile(
    r"(\d[\d.,]*)\s+((?:(?:qualified|new|active|paying)\s+)?(?:leads?|calls?|partners?|inquiries|customers?|"
    r"clients?|opportunit(?:y|ies)|deals?))", re.I)
_STRONG = re.compile(
    r"\b(?:will|is sure to|are sure to|is certain to|guarantee[sd]?|ensure[sd]?|certainly|definitely|surely|"
    r"without fail|pasti|dijamin)\b", re.I)
_EFFECT = re.compile(
    r"\b(?:increase|raise|boost|improve|grow|bring|reach|achieve|hit|meet|move|get you|drive|generate|capai|"
    r"naik|meningkat|menaikkan|menggerakkan|tercapai|membawa)\b", re.I)
_PROVEN = re.compile(r"\b(?:prove[sd]?|proven|proves|terbukti|shown to work|works for your goal)\b", re.I)
_GOALREF = re.compile(
    r"\b(?:your goal|the goal|your target|the target|this path|this move|this step|this route|goal|target|"
    r"tujuan)\b", re.I)
_ACHIEVED = re.compile(
    r"(?:\byou (?:(?:'ve|have|had|just) )?(?:reached|achieved|hit|met|completed) "
    r"(?:your|the) (?:goal|target)|"
    r"\b(?:your|the) (?:goal|target) (?:is|was|has been) (?:reached|achieved|met|done|complete)|"
    r"\bcongratulations\b|\bgoal (?:achieved|reached|met)\b|\bsudah (?:tercapai|berhasil)\b|"
    r"\btujuan(?:mu| anda)? tercapai\b)", re.I)
_CONFIRM = re.compile(
    r"\byou (?:set|confirmed|committed to|decided on|chose|agreed(?: on)?)\b[^.;]{0,60}\b(?:target|goal)\b|"
    r"\byour confirmed (?:target|goal)\b", re.I)


def _parse_num(raw: str) -> float:
    r = raw.strip().strip(".,")
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", r):
        return float(re.sub(r"[.,]", "", r))
    return float(r.replace(",", "."))


def _money_millions(m: re.Match) -> float | None:
    raw = m.group(1) or m.group(3)
    scale = (m.group(2) or m.group(4) or "").lower()
    try:
        n = _parse_num(raw)
    except ValueError:
        return None
    if scale in ("juta", "jt", "million", "mio"):
        return n
    if scale in ("ribu", "rb"):
        return n / 1000
    if scale in ("miliar", "billion"):
        return n * 1000
    return n / 1e6 if n >= 1000 else n


def clauses_of(text: str) -> list[str]:
    plain = _QUOTED.sub(" ", str(text or ""))
    return [c.strip() for c in _CLAUSE_SPLIT.split(plain) if c and c.strip()]


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= max(1e-6, abs(b) * 1e-6)


def _in(v: float, allowed: Iterable[float | None]) -> bool:
    return any(a is not None and _close(v, a) for a in allowed)


def _mentions_names(clause: str, names: Iterable[str]) -> bool:
    c = clause.lower()
    return any(re.search(rf"\b{re.escape(n)}\b", c) for n in names if n)


def _active_money_allowed(f: GoalFacts) -> list[float | None]:
    """Amount of money (millions of rupiah) that may show as an ACTIVE goal: only when its metric is money."""
    if not f.is_money:
        return []
    scale = 1 / 1000 if "ribu" in f.unit.lower() else 1.0
    vals = [f.target, f.target_min, f.target_max, f.baseline]
    return [None if v is None else v * scale for v in vals]


def _foreign_metrics_in(clause: str, f: GoalFacts) -> list[str]:
    out = []
    own = set(f.names)
    for m in metric_registry.metrics():
        mid = m["metric_id"]
        if mid == f.metric_id or mid in f.allowed_metric_ids:
            continue
        for alias in (*(a.lower() for a in m.get("aliases", [])), *_EXTRA_NAMES.get(mid, ())):
            if alias in own or alias in _GENERIC_ALIASES or any(alias in n for n in own):
                continue
            if re.search(rf"\b{re.escape(alias)}\b", clause.lower()):
                out.append(mid)
                break
    return out


def _check_goal_clause(c: str, f: GoalFacts, out: list[tuple[str, str]]) -> None:
    for m in _MONEY.finditer(c):
        v = _money_millions(m)
        if v is None:
            continue
        if not _in(v, _active_money_allowed(f)):
            if _in(v, [_ * 1.0 for _ in f.stale_targets]) and f.is_money:
                out.append((STALE_TARGET, f"Rp{v:g} juta adalah target versi lama, bukan target saat ini"))
            else:
                src = next((o for o in f.other_goals if o.get("metric_id") == "revenue_monthly"
                            and o.get("target") is not None and _close(v, o["target"])), None)
                out.append((OTHER_GOAL if src else FOREIGN_TARGET,
                            f"jumlah uang Rp{v:g} juta dinyatakan sebagai goal, padahal Goal aktif adalah "
                            f"{f.metric_id} ({f.unit})"))
    for m in _PERCENT.finditer(c):
        p = _parse_num(m.group(1))
        allowed = [x * 100 for x in (f.target, f.target_min, f.target_max, f.baseline) if x is not None]
        allowed += [x * 100 for x in f.guardrail_values]
        if f.ratio and _in(p, allowed):
            continue
        if f.ratio and (_in(p * 100, allowed) or _in(p / 100, allowed)):
            out.append((UNIT_CONFLICT, f"persen {p:g}% tidak cocok dengan skala target ({f.metric_id})"))
        elif f.ratio and _in(p, [x * 100 for x in f.stale_targets]):
            out.append((STALE_TARGET, f"{p:g}% adalah target versi lama"))
        elif not _in(p, allowed):
            out.append((FOREIGN_TARGET, f"persentase {p:g}% dinyatakan sebagai goal, bukan milik Goal aktif "
                                        f"({f.metric_id})"))
    allowed_days = [d for d in (f.window_days, f.deadline_days) if d is not None]
    if allowed_days:
        for m in _DAYS.finditer(c):
            d = _parse_num(m.group(1))
            if not _in(d, allowed_days):
                out.append((WINDOW_MISMATCH, f"{d:g} hari bukan window/deadline Goal ({allowed_days})"))
    for m in _COUNT.finditer(c):
        n = _parse_num(m.group(1))
        noun = m.group(2).lower()
        stem = f.unit.rstrip("s")
        active_count = f.semantics == "COUNT_IN_WINDOW" and (
            _mentions_names(noun, f.names) or (bool(stem) and stem in noun)
            or noun.rstrip("s") in " ".join(f.names))
        if active_count:
            if not _in(n, [f.target, f.target_min, f.target_max]):
                kind = STALE_TARGET if _in(n, f.stale_targets) else FOREIGN_TARGET
                out.append((kind, f"{n:g} {noun} bukan target Goal aktif ({f.target:g} {f.unit})"
                            if f.target is not None else f"{n:g} {noun} bukan target Goal aktif"))
        else:
            out.append((FOREIGN_TARGET, f"{n:g} {noun} dinyatakan sebagai goal, padahal Goal aktif adalah "
                                        f"{f.metric_id}"))
    for mid in _foreign_metrics_in(c, f):
        src = next((o for o in f.other_goals if o.get("metric_id") == mid), None)
        out.append((OTHER_GOAL if src else FOREIGN_METRIC,
                    f"metric {mid} dinyatakan sebagai goal user"
                    + (f" (milik goal lain {src['goal_id']})" if src else "")))


def _check_current_clause(c: str, f: GoalFacts, out: list[tuple[str, str]]) -> None:
    unit_noun = (f.unit,) if f.unit in _DAY_METRIC_UNITS else ()
    if not (_mentions_names(c, f.names) or _mentions_names(c, unit_noun)):
        return
    nums = [(_money_millions(m), "money") for m in _MONEY.finditer(c)]
    nums += [(_parse_num(m.group(1)), "percent") for m in _PERCENT.finditer(c)]
    nums += [(_parse_num(m.group(1)), "count") for m in _COUNT.finditer(c)]
    if not nums or _NEG.search(c):
        return
    for v, kind in nums:
        if v is None:
            continue
        if kind == "money" and not f.is_money:
            out.append((CROSS_UNIT_CURRENT, f"nilai uang Rp{v:g} juta dipakai sebagai nilai saat ini untuk "
                                            f"{f.metric_id}"))
        elif f.current is None:
            out.append((CURRENT_NOT_MEASURED, f"nilai saat ini {v:g} diklaim untuk {f.metric_id}, padahal "
                                              "belum ada pengukuran"))
        else:
            cur = f.current * 100 if kind == "percent" else f.current
            if not _close(v, cur) and not _close(v, f.current):
                out.append((CURRENT_MISMATCH, f"nilai saat ini {v:g} berbeda dari pengukuran {f.current:g}"))


def check_text_goal(text: str, f: GoalFacts) -> list[tuple[str, str]]:
    """[(code, reason)] for one text. Without a structured Goal → []."""
    if not f.metric_id or not str(text or "").strip():
        return []
    out: list[tuple[str, str]] = []
    for c in clauses_of(text):
        if _GOAL_CUE.search(c):
            _check_goal_clause(c, f, out)
        if f.check_current and _CURRENT_CUE.search(c) and not _ATTRIB.search(c):
            _check_current_clause(c, f, out)
        if f.unknown_relation and not _NEG.search(c) and _GOALREF.search(c) and (
                (_STRONG.search(c) and _EFFECT.search(c)) or _PROVEN.search(c)):
            out.append((CAUSAL_ON_UNKNOWN, "klaim pasti/kausal atas relasi ke Goal yang belum terbukti "
                                           "(UNKNOWN_RELATION)"))
        if not f.achieved and _ACHIEVED.search(c):
            out.append((ACHIEVED_WITHOUT_EVIDENCE, "Goal dinyatakan tercapai tanpa evaluasi ACHIEVED "
                                                   "(aksi selesai bukan hasil)"))
        if not f.target_confirmed and _CONFIRM.search(c):
            out.append((TARGET_NOT_CONFIRMED, "target dinyatakan ditetapkan/dikonfirmasi pengguna, padahal "
                                              "hanya dicatat dari teks (parsed ≠ konfirmasi)"))
    seen: set[tuple[str, str]] = set()
    return [x for x in out if not (x in seen or seen.add(x))]


def _texts(row: Any) -> list[str]:
    return [str(x) for x in row] if isinstance(row, list) else [str(row or "")]


NESTED_PATH_FIELDS = ("why", "next", "opening", "supported", "holding", "unclear")
NESTED_CHECK_FIELDS = ("how", "have")


def check_explain_goal(dump: dict, f: GoalFacts) -> dict[str, list[str]]:
    """Goal violations for PlainExplain output: {field | "paths:KEY" | "checks:KEY": ["CODE: reason"]}.
    Keys match check_explain so callers use the same drop/repair pattern."""
    bad: dict[str, list[str]] = {}
    if not f.metric_id:
        return bad
    for fld in ("summary", "blocking_title", "blocking_body", "do_title", "do_why", "done_when",
                "hold_title", "hold_body", "why"):
        errs = [f"{c}: {r}" for t in _texts(dump.get(fld)) for c, r in check_text_goal(t, f)]
        if errs:
            bad[fld] = sorted(set(errs))
    for prefix, rows, fields in (("paths", dump.get("paths"), NESTED_PATH_FIELDS),
                                 ("checks", dump.get("checks"), NESTED_CHECK_FIELDS)):
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            errs = [f"{c}: {r}" for fld in fields for c, r in check_text_goal(str(row.get(fld) or ""), f)]
            if errs:
                bad[f"{prefix}:{str(row.get('key') or '?')}"] = sorted(set(errs))
    return bad


def check_answer_goal(answer: str, f: GoalFacts) -> list[str]:
    """Goal violations for one TALK/Ask answer."""
    return sorted({f"{c}: {r}" for c, r in check_text_goal(answer, f)})


def codes_of(bad: dict[str, list[str]] | list[str]) -> list[str]:
    """Codes only (no text) — safe to record as diagnostics."""
    rows = [v for vs in bad.values() for v in vs] if isinstance(bad, dict) else list(bad)
    return sorted({r.split(":", 1)[0] for r in rows})


# ── deterministic fallback sentences (from structured Goal + state, not from the provider) ─────

def goal_label(f: GoalFacts) -> str:
    mdef = metric_registry.metric_by_id(f.metric_id) or {}
    name = ((mdef.get("display_name") or {}).get("en") or f.metric_id.replace("_", " ")).lower()
    return "monthly income" if f.metric_id == "revenue_monthly" else name


def target_text(f: GoalFacts) -> str:
    if f.target is None and f.target_min is None:
        return "no target set yet"
    if f.metric_id == "revenue_monthly":
        return f"{f.target:g} million rupiah a month"
    if f.ratio and f.target is not None:
        return f"{f.target * 100:g} percent"
    if f.target is not None:
        unit = "" if f.unit in ("criteria",) else f" {f.unit}"
        return f"{f.target:g}{unit}"
    return f"{f.target_min:g} to {f.target_max:g}"


def goal_line(f: GoalFacts) -> str:
    window = f" within {f.window_days:g} days" if f.window_days else (
        f" in {f.deadline_days:g} days" if f.deadline_days else "")
    conf = "" if f.target_confirmed else " This target is written down from your words, not yet confirmed."
    return f"Your goal on record: {goal_label(f)}, {target_text(f)}{window}.{conf}"


def measurement_line(f: GoalFacts) -> str:
    if f.current is None:
        return f"We have no measurement of your {goal_label(f)} yet. That is not zero, it is not known."
    shown = f"{f.current * 100:g} percent" if f.ratio else f"{f.current:g}"
    return f"Your {goal_label(f)} measured so far: {shown}."


FALLBACK_FIELDS = {
    "blocking_title": lambda f: "We cannot yet say what holds this goal back.",
    "blocking_body": lambda f: measurement_line(f) + " Without it the map cannot name one blocker.",
    "do_title": lambda f: f"Write down where your {goal_label(f)} stands today.",
    "do_why": lambda f: "The map can only judge progress toward your goal from something measured.",
    "done_when": lambda f: f"You can say where your {goal_label(f)} stands, or that it is not measured yet.",
    "hold_title": lambda f: "Do not treat a finished step as proof that the goal moved.",
    "hold_body": lambda f: "A finished step says you did it. Only a measurement says the goal moved.",
}


def fallback_value(field_name: str, f: GoalFacts) -> Any:
    """Deterministic replacement value for top-level PlainExplain fields that contradict the Goal."""
    if field_name == "summary":
        return [goal_line(f), measurement_line(f)]
    if field_name == "why":
        return [goal_line(f), measurement_line(f)]
    fn = FALLBACK_FIELDS.get(field_name)
    return fn(f) if fn else ""
