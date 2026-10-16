"""Mock provider — demo/eval without an API key (the campaign-forge pattern).

Produces schema-valid JSON for end-to-end smoke tests of the loop.
NOT for measuring reasoning quality — plumbing tests only.
"""
from __future__ import annotations

import json
import os
import re
from typing import Type

from pydantic import BaseModel

from .base import LLMProvider

# ── Mock PlainExplain (round 4): ALL text is derived from the PACK actually received ──────────
# The mock answers like an LLM obedient to the pack: an authoritative structured Goal
# (metric/unit/target/window, parsed vs confirmed), a current value measured or NOT measured,
# the path-to-Goal relation (UNKNOWN = hypothesis), and path items with their states. No facts
# from other scenarios are injected (formerly: "8 years of marketing" and a Rp20 million target
# for every scenario). supported/holding/unclear sentences only appear when the pack has items
# with matching states; numbers only those present in the pack.
_ITEM_RE = re.compile(r'^\s+item (\S+) \("(.*?)"\): (confirmed|still to get|partly there|not checked yet)')
_PATH_RE = re.compile(r"^- path (\S+): status (\S+); what it is about: (.*?) \u2014")
_PATH_KEY_RE = re.compile(r"^- path (\S+):")
_LINK_RE = re.compile(r"^\s+link to your goal: not shown yet")
_CHECK_RE = re.compile(r"^- key (\S+): state (confirmed|still to get|partly there|not checked yet)")
_CLAIM_OF = {
    "confirmed": "SUPPORTED",
    "still to get": "MISSING",
    "partly there": "PARTIAL",
    "not checked yet": "UNKNOWN",
}
_STATUS_PHRASE = {
    "OPEN": "The evidence supports moving on this path now.",
    "TEST_FIRST": "This path is worth a small test before you commit to it.",
    "NOT_YET": "This path needs more evidence before it makes sense.",
    "STOP": "The evidence so far does not support continuing this path.",
}


def _parse_pack(user: str) -> dict[str, dict]:
    """PATHS READ -> {path_key: {status, title, link_unknown, items: [(key, title, state_word)]}}."""
    out: dict[str, dict] = {}
    cur = None
    for line in (user or "").splitlines():
        m = _PATH_RE.match(line)
        if m:
            cur = m.group(1)
            out[cur] = {"status": m.group(2), "title": m.group(3).strip(), "link_unknown": False, "items": []}
            continue
        m = _PATH_KEY_RE.match(line)
        if m:
            cur = m.group(1)
            out[cur] = {"status": "", "title": cur, "link_unknown": False, "items": []}
            continue
        if cur is not None and _LINK_RE.match(line):
            out[cur]["link_unknown"] = True
            continue
        m = _ITEM_RE.match(line)
        if m and cur is not None:
            out[cur]["items"].append((m.group(1), m.group(2), m.group(3)))
    return out


def _clean(rows: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Items whose titles pass the plain-language guard (like an obedient LLM:
    technical titles are not copied)."""
    from domains.revenue.guards.plain_language import BANNED

    return [(k, t) for k, t in rows if not BANNED.search(t)]


def _lc(t: str) -> str:
    t = (t or "").strip().rstrip(".")
    return t[:1].lower() + t[1:] if t else t


def _mock_paths(user: str) -> list[dict]:
    entries = []
    for key, p in _parse_pack(user).items():
        items = p["items"]
        by_state: dict[str, list[tuple[str, str]]] = {}
        for ik, title, word in items:
            by_state.setdefault(word, []).append((ik, title))
        by_state = {w: _clean(rows) for w, rows in by_state.items()}
        unsettled = (by_state.get("still to get") or []) + (by_state.get("partly there") or []) \
            + (by_state.get("not checked yet") or [])
        about = _lc(p["title"])
        link = (" Nothing shows yet that it moves your goal, so treat it as something to test."
                if p["link_unknown"] else "")
        entry = {
            "key": key,
            "why": _STATUS_PHRASE.get(p["status"], "This path is on your map from what you told us.")
            + (" Nothing it needs is confirmed yet." if items and not by_state.get("confirmed") else ""),
            "next": (f"Next, settle this: {_lc(unsettled[0][1])}." if unsettled
                     else "Next, take the first small step on this path."),
            "opening": f"This path is about {about}." + link,
            "claims": [],
        }
        for field, word, fmt in (
            ("supported", "confirmed", "Already in place: {}."),
            ("holding", "still to get", "Holding it back: {}."),
            ("unclear", "not checked yet", "Not known yet: {}."),
        ):
            hit = (by_state.get(word) or [])
            if word == "still to get" and not hit:
                hit = by_state.get("partly there") or []
                word = "partly there"
            if hit:
                entry[field] = fmt.format(_lc(hit[0][1]))
                entry["claims"].append({"field": field, "claim": entry[field].rstrip("."),
                                        "claim_type": _CLAIM_OF[word], "requirement": hit[0][0]})
        entries.append(entry)
    return entries


def _mock_checks(user: str) -> list[dict]:
    titles = dict(_clean([(ik, t) for p in _parse_pack(user).values() for ik, t, _ in p["items"]]))
    out, seen = [], set()
    for line in (user or "").splitlines():
        m = _CHECK_RE.match(line)
        if not m or m.group(1) in seen:
            continue
        seen.add(m.group(1))
        if m.group(2) == "confirmed":
            out.append({"key": m.group(1), "have": "You already have this, and the evidence is on record."})
        elif m.group(1) in titles:
            out.append({"key": m.group(1), "how": f"see if it holds today: {_lc(titles[m.group(1)])}."})
    return out


def _goal_rows(user: str) -> dict[str, str]:
    """The ACTIVE GOAL (structured, authoritative) block in the pack -> {key: value}; empty when absent."""
    if "ACTIVE GOAL (structured" not in (user or ""):
        return {}
    rows: dict[str, str] = {}
    on = False
    for line in (user or "").splitlines():
        if line.startswith("ACTIVE GOAL (structured"):
            on = True
            continue
        if on:
            if line.startswith("- ") and ": " in line:
                k, _, v = line[2:].partition(": ")
                rows[k.strip()] = v.strip()
            elif line.strip() == "":
                break
    return rows


def _pack_facts(user: str) -> list[str]:
    """The FACTS lines (the user's own words) from the pack that pass the plain-language guard
    (like an obedient LLM: violating quotes are not copied). Facts come from this session, never
    from other scenarios."""
    from domains.revenue.guards.plain_language import BANNED

    out, on = [], False
    for line in (user or "").splitlines():
        if line.startswith("FACTS (from what they said)"):
            on = True
            continue
        if on:
            if not line.startswith("- "):
                break
            t = line[2:].strip()
            if t and t != "(none)" and 3 <= len(t.split()) <= 18 and len(t) <= 160 and not BANNED.search(t):
                out.append(t.rstrip("."))
    return out


def _mock_plain_explain(user: str) -> dict:
    """A deterministic PlainExplain that SERVES this session's structured Goal and the pack's real state:
    - metric/unit/target/window only from the ACTIVE GOAL block (parsed ≠ confirmed is stated);
    - a current value that is measured, or 'not yet measured' (missing ≠ zero) - never invented;
    - UNKNOWN path relations stated as something to test, not a promise;
    - zero paths: an honest reason, no fictional paths."""
    gb = _goal_rows(user)
    paths = _mock_paths(user)
    checks = _mock_checks(user)
    metric = gb.get("metric", "")
    name = "monthly income" if metric == "revenue_monthly" else metric.replace("_", " ")
    try:
        tnum = float(gb["target"])
        target_txt = f"{tnum * 100:g} percent" if gb.get("unit") == "ratio" else (
            f"{tnum:g} million rupiah a month" if metric == "revenue_monthly" else f"{tnum:g}")
    except (KeyError, ValueError):
        target_txt = ""
    window = gb.get("measurement window", "")
    window_phrase = f" within {window}" if window else (
        f" {gb['deadline']}" if gb.get("deadline") else "")
    measure = (f"{name}, {target_txt}{window_phrase}" if target_txt else name).strip()
    cur_raw = gb.get("current measured value", "")
    measured = bool(cur_raw) and not cur_raw.startswith("NOT MEASURED")
    pct = re.search(r"\(that is ([\d.]+) percent\)", cur_raw)
    if pct:
        cur_raw = f"{pct.group(1)} percent"
    elif measured and metric == "revenue_monthly":
        cur_raw = f"{cur_raw} million rupiah a month"
    cur_line = (f"Your {name} measured so far: {cur_raw}." if measured
                else f"We have no measurement of your {name} yet. That is not zero, it is not known.")
    confirmed = gb.get("target confirmed by user", "no").startswith("yes")
    unknown_link = any(p.get("opening", "").find("Nothing shows yet") >= 0 for p in paths)
    no_path = "(no path was formed" in (user or "")
    facts = _pack_facts(user)
    told = f'You told us: "{facts[0]}". ' if facts else ""
    s1 = told + f"What we can read so far serves one goal: {measure}."
    if not confirmed:
        s1 += " This target is written down from your words, not yet confirmed."
    summary = [s1, cur_line]
    if no_path:
        summary.append("No path is formed yet, because the goal or the evidence is not clear enough.")
    elif unknown_link:
        summary.append(
            f"The paths on your map are things to test. Nothing shows yet that they move your {name}.")
    return {
        "summary": summary,
        "blocking_title": (f"The goal for your {name} is not reached yet." if measured
                           else f"Nothing measures your {name} yet."),
        "blocking_body": ("We cannot name the one thing holding it back until there is something measured."
                          if not measured else "The map still needs more evidence to name the one thing."),
        "do_title": f"Write down where your {name} stands today.",
        "do_why": "A goal needs a starting number to be judged. Without one, the map can only guess.",
        "done_when": f"You can say where your {name} stands, or say plainly that it is not measured yet.",
        "hold_title": "Do not count a finished step as proof that the goal moved.",
        "hold_body": ("A finished step says you did it. Only a measurement says the goal moved."
                      + (" Treat each path as a test, not a promise." if unknown_link else "")),
        "why": [f"Your goal on record: {measure}.", cur_line],
        "paths": paths,
        "checks": checks,
    }


_LATEST_MESSAGE_RE = re.compile(r'USER\'S LATEST MESSAGE:\s*"""(.*?)"""', re.S)

# ── Mock TurnExtraction (M4): deterministic evidence extraction from the USER's own sentences ─────────
# Mock-only (plumbing, not reasoning quality): one evidence per user sentence, so order-free conversation
# flows can be tested end-to-end without an LLM. Sentences containing 'Rp<number>' stay transactional
# (the old mock behavior, used by the revenue state); sentences saying "tidak tahu / tidak punya data"
# become a GAP (missing data, not a fact).
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")
_GAP_CUE_RE = re.compile(
    r"\b(tidak tahu|belum tahu|tidak punya data|belum punya data|tidak ada data|don'?t know|do not know|"
    r"no idea|no data)\b",
    re.I,
)
_GOAL_CUE_RE = re.compile(r"\b(want|wants|goal|target|ingin|mau|within|dalam \d+ hari|pengen)\b", re.I)
_TOPIC_CUES = (
    (
        "MOTION",
        re.compile(r"\b(tried|sudah coba|pernah coba|kirim|dm|hubungi|contacted|posted|iklan|ads)\b", re.I),
    ),
    ("DEMAND", re.compile(r"\b(inquir|lead|tanya|minta|asked|prospek|prospect)\w*", re.I)),
    (
        "CONVERSION",
        re.compile(r"\b(closing|close|deal|bayar|paid|pays|konversi|conversion|proposal)\b", re.I),
    ),
)


_MONEY_RE = re.compile(r"\bRp\s?(\d+(?:[.,]\d+)?)\s*(juta|jt|million|m)?", re.I)
_PERIOD_RE = re.compile(r"(per month|a month|monthly|per bulan|/bulan|sebulan)", re.I)
_PAST_RE = re.compile(r"\b(last year|tahun lalu|dulu|pernah|used to|previously)\b", re.I)
_INCOME_RE = re.compile(
    r"\b(income|earn|earning|revenue|pendapatan|penghasilan|omzet|sekarang|currently|now)\b", re.I
)


def _mock_number_claims(sent: str, is_goal: bool) -> list[dict]:
    """Structured number claims from sentences containing 'Rp<number> [juta|million]'
    (mock-only; values in MILLIONS). Roles from sentence cues: goal -> target (future);
    past -> historical; income -> current."""
    out = []
    for m in _MONEY_RE.finditer(sent):
        value = float(m.group(1).replace(",", "."))
        if is_goal:
            role, tense = "target", "future"
        elif _PAST_RE.search(sent):
            role, tense = "historical_client_rate", "past"
        elif _INCOME_RE.search(sent):
            role, tense = "current_revenue", "now"
        else:
            role, tense = "other", "now"
        out.append(
            {
                "value": value,
                "period": "monthly" if _PERIOD_RE.search(sent) else "one_off",
                "tense": tense,
                "role": role,
                "subject": "income",
                "verbatim": sent,
                "hedge": False,
            }
        )
    return out


def _mock_turn_extraction(user: str) -> dict:
    m = _LATEST_MESSAGE_RE.search(user or "")
    text = m.group(1) if m else ""
    evidence, tags, claims = [], [], []
    for n, sent in enumerate(x.strip() for x in _SENTENCE_SPLIT_RE.split(text) if x and x.strip()):
        if len(sent.split()) < 3:
            continue
        is_goal = bool(_GOAL_CUE_RE.search(sent))
        topic = "GOAL" if is_goal else next((k for k, rx in _TOPIC_CUES if rx.search(sent)), "REVENUE_STATE")
        money = bool(re.search(r"\bRp\s?\d", sent, re.I))
        evidence.append(
            {
                "id": f"ev-mock-{n + 1}",
                "signal": sent,
                "level": "transactional" if money and not is_goal else "self_reported",
                "source_quote": sent,
                "topic": topic,
                "is_gap": bool(_GAP_CUE_RE.search(sent)),
            }
        )
        tags.append(
            {"kind": "GOAL" if is_goal else "FACT", "quote": sent, "normalized": sent, "confidence": 0.8}
        )
        claims.extend(_mock_number_claims(sent, is_goal))
    return {"intent_tags": tags, "evidence": evidence, "number_claims": claims}


def _parse_goal_block(user: str) -> dict:
    """The ACTIVE GOAL (structured) block from the diagnosis prompt -> a field-value dict (F-15)."""
    if "ACTIVE GOAL (structured" not in (user or ""):
        return {}
    out: dict = {}
    for line in (user or "").splitlines():
        if line.startswith("- ") and ": " in line:
            k, _, v = line[2:].partition(": ")
            out[k.strip()] = v.strip()
    return out


def _mock_grounded_draft(gb: dict, user: str) -> dict:
    """A deterministic diagnosis draft that SERVES this session's structured goal (F-14/F-15):
    it only mentions metric/unit/target from the ACTIVE GOAL block, distinguishes a confirmed
    vs recorded target, and injects no facts from other scenarios."""
    metric = gb.get("metric", "?")
    name = metric.replace("_", " ")
    target = gb.get("target", "the recorded target")
    unit = gb.get("unit", "")
    window = gb.get("measurement window", "")
    stated = gb.get("user stated it as", "")
    confirmed = gb.get("target confirmed by user", "no")
    ev_ids = re.findall(r"- \[(ev-[a-z0-9_-]+)\]", user or "")[:3]
    # the unit is not repeated when identical to the metric name (qualified leads / leads)
    unit_part = f" {unit}" if unit and unit.lower() != name.lower() else ""
    try:
        target_txt = f"{float(target) * 100:g} percent" if unit == "ratio" else f"{float(target):g}"
    except (TypeError, ValueError):
        target_txt = str(target)
    if unit == "ratio":   # a share is told as a percent, never as "0.25 ratio"
        unit_part = ""
    measure = f"{name} at {target_txt}{unit_part}".strip()
    window_phrase = f" within {window}" if window else ""
    where = (f"What we can read so far serves one goal: {measure}. "
             + (f'You stated it as "{stated}." ' if stated else "")
             + ("This target is recorded, not yet confirmed by you. " if confirmed.startswith("no") else "")
             + "The read firms up as evidence comes in.")
    return {
        "where_you_are": where,
        "primary_constraint": ("There is not enough measured evidence yet to name the one thing "
                               "holding this goal back."),
        "primary_constraint_id": "NO_FIT",
        "secondary_constraints": [],
        "why": [f"The goal on record: {measure}.",
                "Evidence that names a binding constraint for this goal is not measured yet."],
        "do_not": f"Do not treat any completed action as proof of the goal until {name} is measured.",
        "next_best_action": f"Record the first {name} measurement so the map can judge progress.",
        "first_step_today": f"Write down the current {name} number, or mark it not measured.",
        "success_metric": f"{measure}{window_phrase}",
        "well_know_when": f"{name} is measured at or past {target_txt} in a recorded check-in.",
        "day_by_day": [f"Day 1: record the current {name} number (or mark it not measured).",
                       f"Day 2: do one thing that should move {name}, and note what you did.",
                       f"Day 3: repeat the thing that moved {name}, and write down what happened."],
        "reassess_window_days": 14,
        "pivot_rule": "If two check-ins move nothing, change the approach, not the goal.",
        "evidence_map": {"NO_FIT": ev_ids},
    }




_CURRENT_MSG_RE = re.compile(r"CURRENT USER MESSAGE \(turn \d+\):\s*<<<\n(.*?)\n>>>", re.S)
_SO_GOAL_CUE = re.compile(
    r"ingin|mau|pengen|want|target|goal|menuju|hingga|capai|i mean by|what i need|i need", re.I)
_SO_DESIRE_CUE = re.compile(r"supaya|agar|biar|karena|so that|because|alasan", re.I)
_SO_ASSUME_CUE = re.compile(r"kayaknya|kira|rasanya|menurut saya|mungkin|i think|guess|feel like", re.I)
_SO_GAP_CUE = re.compile(
    r"tidak (tahu|punya|ada)|belum (ada|tahu|punya)|don't know|no data|tidak pernah", re.I)
_SO_PAST_CUE = re.compile(r"\bdulu\b|dahulu|used to|sebelumnya|last year|tahun lalu|kemarin", re.I)
_SO_FUTURE_CUE = re.compile(r"\bnanti\b|besok|next|dalam \d+ (hari|bulan)|rencana", re.I)
_SO_MONEY = re.compile(r"rp\s?([0-9]+(?:[.,][0-9]+)?)\s*(juta|jt|ribu|rb)?", re.I)
_SO_CONCERN_CUE = re.compile(r"takut|khawatir|cemas|nervous|afraid|worried|tidak enak|malas", re.I)
_SO_CONSTRAINT_CUE = re.compile(r"tidak mau|enggan|jangan|must not|cannot afford|tidak bisa", re.I)


def _so_role(sent: str) -> str:
    if _SO_GAP_CUE.search(sent):
        return "gap"
    if _SO_DESIRE_CUE.search(sent) and not _SO_GOAL_CUE.search(sent):
        return "desire"
    if _SO_GOAL_CUE.search(sent):
        return "goal"
    if _SO_ASSUME_CUE.search(sent):
        return "assumption"
    if _SO_PAST_CUE.search(sent):
        return "event"
    return "claim"


def _so_tense(sent: str) -> str:
    if _SO_PAST_CUE.search(sent):
        return "past"
    if _SO_FUTURE_CUE.search(sent) or _SO_GOAL_CUE.search(sent):
        return "future"
    return "now"


_NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
              "nine": 9, "ten": 10, "eleven": 11, "twelve": 12}
_SO_COUNT = re.compile(
    r"\b(\d{1,4}|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\s+"
    r"((?:qualified\s+)?(?:leads?|clients?|customers?|klien|pelanggan|calls?|meetings?))\b", re.I)


def _so_quantity(sent: str):
    m = _SO_MONEY.search(sent)
    if not m:
        c = _SO_COUNT.search(sent)
        if not c:
            return None
        raw = c.group(1).lower()
        n = float(_NUM_WORDS.get(raw, raw))
        return {"value_kind": "exact", "value": n, "low": None, "high": None,
                "unit": c.group(2).lower(), "period": "unspecified"}
    val = float(m.group(1).replace(",", "."))
    unit = (m.group(2) or "juta").lower()
    if unit in ("rb", "ribu"):
        val, unit = val / 1000.0, "juta"
    elif unit == "jt":
        unit = "juta"
    approx = bool(re.search(r"sekitar|kira-kira|approximately|around|about|\+/-", sent, re.I))
    at_most = bool(re.search(r"maksimal|paling (banter|banyak)|up to|max|sampai dengan", sent, re.I))
    kind = "at_most" if at_most else ("approximate" if approx else "exact")
    period = "monthly" if re.search(r"per ?bulan|/bulan|monthly|sebulan", sent, re.I) else "one_off"
    return {"value_kind": kind, "value": val, "low": None, "high": None, "unit": unit, "period": period}


def _mock_semantic_observation(user: str) -> dict:
    """A deterministic semantic observation for mock/demo mode (the so.v1 contract).

    Claims are built per clause from the CURRENT USER MESSAGE in the observation prompt;
    the quote = the clause itself (always a valid substring). Six roles + aspect +
    typed quantities are derived from sentence cues — enough for the mock e2e.
    The subject of income-bearing sentences is normalized to "income" so the domain
    projection (mapper M3) can still read it like the old extraction path.
    """
    m = _CURRENT_MSG_RE.search(user or "")
    text = m.group(1).strip() if m else ""
    claims: list[dict] = []
    relations: list[dict] = []
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n", text) if s and len(s.strip()) > 2]
    # goal clauses joined with current facts ("make Rp30 DAN ingin Rp60") are split (like the real observer)
    split_goal = re.compile(r"\s+(?:and|dan|but|tapi)\s+(?=(?:want|ingin|mau|pengen|need|aim)\b)", re.I)
    sents = [part.strip() for sent in sents for part in split_goal.split(sent) if len(part.strip()) > 2]
    for n, sent in enumerate(sents, 1):
        if len(sent.split()) < 2:
            continue
        role = _so_role(sent)
        qty = None if role == "gap" else _so_quantity(sent)
        subj, pred = "saya", "states"
        mm = re.match(r"^(\S+(?:\s\S+)?)[\s]+(?:itu\s+)?(?:sedang\s+|sedang|)?(.+)$", sent)
        if mm:
            subj, pred = mm.group(1), mm.group(2)[:80]
        if qty is not None and re.search(
                r"earn|income|omzet|omz|revenue|pendapatan|penghasilan|make\s|sales|penjualan|"
                r"have|has|savings|tabungan|dananya", sent, re.I):
            subj = "income"  # old fixture parity: a money claim -> income subject
        aspect = ""
        if _SO_CONSTRAINT_CUE.search(sent):
            aspect = "constraint"
        elif _SO_CONCERN_CUE.search(sent):
            aspect = "concern"
        # old mock semantic parity: money figures (not goal/desire) = measured figures
        # -> epistemic measured (transactional level on the derived evidence); estimates
        # are still recorded via hedge/approximate quantity, not the level.
        approx = bool(re.search(r"sekitar|kira|mungkin|about|maybe|approximately", sent, re.I))
        if qty is not None and role not in ("goal", "desire", "gap"):
            epi = "measured"
        elif approx:
            epi = "estimated"
        else:
            epi = "reported"
        claim = {
            "ref": f"c{n}",
            "role": role,
            "aspect": aspect,
            "subject": subj[:60],
            "predicate": (pred or "states")[:60],
            "object": None,
            "quantity": qty,
            "tense": _so_tense(sent),
            "hedge": approx,
            "epistemic": epi,
            "quote": sent[:380],
            "supersedes": None,
            "revision_kind": None,
            "revision_reason": "",
        }
        claims.append(claim)
        if n > 1:
            relations.append({"src": f"c{n}", "dst": f"c{n-1}", "kind": "related_to",
                              "reason": "same message"})
    return {
        "contract_version": "so.v1",
        "language": "",
        "claims": claims[:24],
        "relations": relations[:16],
        "uncertainties": [],
    }


def _mock_next_move(user: str) -> dict:
    """MOCK NextMove reasoning (nm.v2): picks the first askable uncertainty from the snapshot —
    purely for contract/guard/integration tests. NOT proof the question is useful (tested with
    real models, R7).

    The `checkpoint_eligibility` block is deliberately NOT filled: that is the contract's
    OPTIONAL path (its absence = pre-nm.v2 behavior), and the mock does not judge decision sufficiency."""
    action_allowed = "action_allowed: true" in user
    lang = "id" if "USER LANGUAGE: id" in user else "en"
    from core.reasoning.reasoner import parse_snapshot_prompt
    snap = parse_snapshot_prompt(user)
    claim_ids = snap.get("claim_ids") or []
    sup = claim_ids[-1:] if claim_ids else []
    base = {"contract_version": "nm.v2", "state_snapshot_ref": snap["snapshot_id"], "goal_ref": "",
            "supporting_claim_refs": sup, "knowledge_refs": [], "competing_hypotheses": [],
            "candidate_uncertainty_ids": [u["id"] for u in snap.get("uncertainties", [])]}
    # PHASE 7 E2E FIXTURE MODE (default OFF): a deterministic way to exercise the ACTION branch.
    # A real model may propose ACTION whenever G6 allows it - the planner's "enough to map" OR a USABLE
    # path (navigable, not STOP, feasibility SUPPORTED/CONDITIONAL). This mock otherwise answers the
    # first open question forever, so the canonical Move (and therefore the Maps<->Moves loop) could
    # never be reached in an e2e run. It proposes exactly what the guard already permits - it does NOT
    # bypass any check: move_design is still validated by G10/S4, and the basis by G6.
    if os.environ.get("MOCK_ACTION_WHEN_USABLE") == "1" and not action_allowed:
        usable = [p for p in (snap.get("paths") or [])
                  if p.get("navigable")
                  and str(p.get("feasibility") or "").upper() in ("SUPPORTED", "CONDITIONAL")
                  and str(p.get("status") or "").upper() not in ("STOP", "STOPPED", "CLOSED")]
        if usable:
            action_allowed = True
            _linked = str(usable[0].get("path_id") or "")
        else:
            _linked = ""
    else:
        _linked = ""
    for u in snap.get("uncertainties", []):
        if u.get("askable", True) and int(u.get("asked", 0)) < 2:
            label = u.get("label") or u["id"]
            q = u.get("legacy_wording") or (f"Bisa ceritakan lebih jauh soal: {label}?" if lang == "id"
                                            else f"Could you tell me more about: {label}?")
            kind = u.get("suggested_kind") or "QUESTION"
            if kind == "EVIDENCE_REQUEST" and not sup:
                # F1: an evidence request must point at REAL sources; the mock does not invent sources
                kind = "QUESTION"
            return {**base, "proposed_move_kind": kind,
                    "focus_type": "goal" if u["id"] == "goal" else "uncertainty",
                    "proposed_focus": u["id"], "move_text": q,
                    "evidence_source_refs": sup if kind == "EVIDENCE_REQUEST" else [],
                    "information_value_rationale": "mock: ketidakpastian pertama yang dapat ditanya",
                    "expected_decision_change": "mock"}
    if action_allowed:
        # MC01-5 (audit CIR-MC01 P1): the checkpoint offer now comes ONLY from the eligibility block
        # (int 18; the UI ACTION=ready fallback was removed). The mock does NOT judge sufficiency itself —
        # this block MIRRORS the planner's deterministic signal (`action_allowed` = enough-to-map),
        # with the most conservative offerable level: PROVISIONAL_READY based on active claims;
        # guards S0–S5 still validate this block like a real model's block.
        base["checkpoint_eligibility"] = {
            "level": "PROVISIONAL_READY", "basis_claim_refs": sup,
            "critical_unknown_ids": [], "nonblocking_unknown_ids": [],
            "marginal_information_value": [], "external_evidence_pending": False,
            "can_offer_checkpoint": True,
            "recommendation": "", "rationale": "mock: cermin sinyal action_allowed planner",
        }
        return {**base, "proposed_move_kind": "ACTION", "focus_type": "uncertainty", "proposed_focus": "",
                "move_text": ((snap.get("deterministic_hint") or {}).get("text")
                              or ("Pemetaan awal sudah cukup — lanjut ke langkah di peta." if lang == "id"
                                  else "The initial mapping is sufficient — continue on the map.")),
                "information_value_rationale": "mock: tak ada ketidakpastian yang dapat ditanya",
                "move_design": {
                    "objective": "mock: ambil langkah pertama pada path yang tersedia di peta",
                    # Phase 7: an ACTION carries the Move's executable action list (no day schedule).
                    "actions": [
                        {"title": "mock: siapkan satu tindakan konkret untuk langkah ini",
                         "instruction": "mock: tuliskan tindakan yang benar-benar bisa dilakukan"},
                        {"title": "mock: jalankan tindakan itu",
                         "instruction": "mock: lakukan dan catat siapa atau apa yang terlibat"},
                        {"title": "mock: catat apa yang terjadi setelahnya",
                         "instruction": "mock: catat hasil yang terlihat, bukan kesimpulan",
                         "required": False, "depends_on": [2]},
                    ],
                    "expected_evidence": ["mock: bukti hasil langkah dilaporkan user"],
                    "measurement_method": "mock: user melaporkan hasil; engine mencatat klaim observasi",
                    "observation_window_days": 7, "completion_criteria": ["mock: hasil langkah dilaporkan"],
                    "linked_path_id": (_linked or ((snap.get("paths") or [{}])[0].get("path_id", "")
                                       if snap.get("paths") else ""))}}
    return {**base, "proposed_move_kind": "HOLD", "abstain": True, "focus_type": "uncertainty",
            "proposed_focus": "", "move_text": (snap.get("deterministic_hint") or {}).get("text", ""),
            "conditions_for_abstention": "mock: tak ada ketidakpastian yang dapat ditanya"}


def _mock_for(schema: Type[BaseModel], user: str = "") -> dict:
    if schema.__name__ == "NextMoveProposal":
        return _mock_next_move(user)
    if schema.__name__ == "SemanticObservation":
        return _mock_semantic_observation(user)
    if schema.__name__ == "SecondPassCheck":
        # The mock does not interpret meaning (plumbing, not a semantic verifier): the conservative
        # verdict "nothing verified" -> layer C degrades honestly to UNRESOLVED in mock mode.
        rid = re.search(r"^REQUIREMENT (\S+)", user or "", re.M)
        return {"contract_version": "spv.v1", "requirement_id": rid.group(1) if rid else "",
                "claim_checks": []}

    if schema.__name__ == "TurnExtraction":
        return _mock_turn_extraction(user)

    if schema.__name__ == "DiagnosisDraft":
        gb = _parse_goal_block(user)
        if gb:
            return _mock_grounded_draft(gb, user)
        return {
            "where_you_are": ("Right now you have zero clients, although you have 8 years of marketing "
                             "experience. Your target is Rp20 million a month. What is certain: your "
                             "skill is there. What is missing: a clear offer and people to talk to."),
            "primary_constraint": (
                "You do not have a clear service offer yet, so people do not know what they would pay for."
            ),
            "primary_constraint_id": "V2.1",
            "secondary_constraints": ["No outreach to potential clients yet"],
            "why": ["There is no active client yet",
                    "the service has never been written down",
                    "no potential client has been contacted"],
            "do_not": "Do not run paid ads yet. Your problem is not a lack of traffic.",
            "next_best_action": "Write 3 versions of your service offer from your 8 years of experience.",
            "success_metric": "5 qualifying conversations within 7 days",
            "well_know_when": "3 offer versions are done and one of them gets a positive response",
            "day_by_day": [
                "Day 1: Write a one-page service offer from your 8 years of experience.",
                "Day 2: Send that offer to the 2 people who once asked.",
                "Day 3: Ask 3 acquaintances what they pay for marketing today.",
            ],
            "outreach_script": ("Hi [Name], I am tidying up my marketing consulting service. "
                                "May I send you a one-page summary?"),
            "reassess_window_days": 14,
            "pivot_rule": ("If 5 conversations happen with no interest, "
                           "look again: the market may be the wrong one"),
            "evidence_map": {"V2.1": ["ev-demo-1"]},
        }

    if schema.__name__ == "PlainExplain":
        return _mock_plain_explain(user)
    if schema.__name__ == "AskReply":
        # A-23/WF-G grounding: the deterministic answer ANCHORS to the asked session's context
        # (the Goal pack in the user text) — not canned text that could answer another session. Numbers
        # only come from the pack (the plain-language guard stays in control).
        goal_wrote = ""
        mgoal = re.search(r"GOAL AS THE USER WROTE IT:\s*(.+)", user or "")
        if mgoal:
            goal_wrote = mgoal.group(1).strip()
        goal_rows = re.findall(r"- goal \(([^)]+)\):\s*([^\n]+)", user or "")
        # F-15: NO canned facts from other scenarios ("8 years of experience" once
        # injected the number 8, which did not belong to this session and was rejected by the
        # guard) - every sentence comes from this session's pack.
        answer = "What we can read: "
        if goal_rows:
            answer += "your goal on record: " + goal_rows[0][0] + " - " + goal_rows[0][1].strip() + ". "
        if goal_wrote:
            answer += "You put it as: " + goal_wrote.rstrip(".") + ". "
        answer += "The first step is still the most sensible one."
        return {
            "answer": answer,
            "follow_ups": ["What do we not know yet about you?", "What should I not do yet?"],
        }
    return {}


class MockProvider(LLMProvider):
    name = "mock"

    def raw_json(self, system: str, user: str) -> str:
        return json.dumps(_mock_for(BaseModel))  # placeholder, structured_call overridden below

    def structured_call(self, schema, system, user, retries=2):
        # Detect the schema from the caller's INSTRUCTIONS (mock-only heuristic) — BUT the
        # requested schema wins first. The old text heuristic mis-picked extraction for
        # DiagnosisDraft (the diagnosis prompt contains the word
        # "interview") → a draft without evidence_map → AttributeError 500 in finalize.
        from domains.revenue.schema.artifact import DiagnosisArtifact  # noqa
        from agents.interview import TurnExtraction  # noqa
        from agents.diagnosis import DiagnosisDraft  # noqa
        from domains.revenue.schema.explain import PlainExplain  # noqa
        from domains.revenue.schema.ask import AskReply  # noqa
        from core.semantic.contract import SemanticObservation  # noqa
        from core.reasoning.contract import NextMoveProposal  # noqa
        from ontology.mapper.second_pass import SecondPassCheck  # noqa
        known = (TurnExtraction, DiagnosisDraft, PlainExplain, AskReply, SemanticObservation,
                 NextMoveProposal, SecondPassCheck)
        if schema in known:
            target = schema
        else:
            target = (
                TurnExtraction
                if "intent" in system.lower() or "interview" in system.lower()
                else DiagnosisDraft
            )
        return target.model_validate(_mock_for(target, user))
