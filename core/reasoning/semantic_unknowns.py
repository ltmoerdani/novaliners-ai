"""Semantic-uncertainty continuity — CIR-03 (int 19 §7.3–7.4, §9; CIR-INV-07).

`SemanticObservation.uncertainties` (so.v1) = important things still open according to UNDERSTANDING.
Before CIR-03 that list was DISCARDED at commit (`verify_and_commit` only persisted claims+relations),
so material unknowns produced by understanding had no path to NextMove candidates.

Rules of this module:
- Storage: session field `semantic_unknowns` (list[dict]) — re-use the existing session store
  (OD-18: prefer durable event/session records), NOT a second authority and NOT a new DB.
  Unknowns are advisory PROPOSALS (int 19 §7.4), not verified requirements.
- Stable id `su-<sha1[:8]>` from normalized text → idempotent for re-observation.
- Lifecycle: open → answered (a new claim answers it) → may reopen if new understanding
  states the same thing is still open; `asked` is counted from steps that were PRESENTED
  (planner_log presented need_id) so the ASK_CAP repeat-safeguard applies the same as for
  planner needs.
- Reconciliation to candidates (int 19 §9.4): dedup vs planner candidates (planner origin represents),
  exclude those already exhausted/answered, capacity follows the ONE canonical constant
  `MAX_UNCERTAINTY_CANDIDATES`; ALL exclusions are recorded with their reason (no invisible drop,
  CIR-INV-15).
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

from core.reasoning.contract import MAX_UNCERTAINTY_CANDIDATES

ST_OPEN, ST_ANSWERED = "open", "answered"
_MAX_STORED = 32                     # simpanan riwayat unknown per sesi (answered ikut terpotong)
_ANSWER_OVERLAP = 0.34               # jaccard(unknown, new claim) ≥ this ⇒ considered answered
_ANSWER_MIN_SHARED = 2               # MC01-4: requires ≥2 SHARED content tokens (not 1 accidental token)
_ANSWER_INFO_GAIN = 2                # MC01-4: requires ≥2 NEW non-filler content tokens — an echo is not an answer
_VARIANT_OVERLAP = 0.34              # MC-05: jaccard(new variant, unknown answered) ≥ this ⇒ wording variant
_VARIANT_MIN_SHARED = 3              # MC-05: requires ≥3 shared content tokens (paraphrase, not adjacent topics)
_FILLER = frozenset(                 # discourse words that are NOT information (excluded from info-gain)
    "soal tentang sebenarnya memang hanya saja juga kayak intinya artinya sumanya"
    .split())
_NO_ANSWER_MARKERS = (               # MC01-4: a DO-NOT-KNOW statement = gap, NOT an answer
    "belum tahu", "tidak tahu", "tak tahu", "nggak tahu", "tidak ingat", "saya lupa",
    "belum ada data", "tidak ada data", "belum ada datanya", "tidak ada datanya",
    "tidak pernah dicatat", "tidak tercatat", "belum diukur", "tidak diukur",
    "don't know", "not sure", "no data", "never tracked", "no records",
)
_DUPLICATE_OVERLAP = 0.5             # jaccard(unknown, planner candidate) ≥ this ⇒ the planner represents it

_STOP = frozenset(
    "yang dan di ke dari untuk dengan atau ini itu ada tidak saya anda user the a an of to in is are as be by on "
    "for with that this it its at from not no if when then they their which who has have had will would can could "
    "about into over than also more most other some such only own same so too very just apa kah sudah belum masih "
    "banyak berapa bagaimana kapan siapa mengapa".split())
_TOK = re.compile(r"[a-zA-Z]{4,}")


def _norm(text: str) -> str:
    return " ".join((text or "").lower().split())


def _tokens(text: str) -> set[str]:
    return {w for w in (m.group(0).lower() for m in _TOK.finditer(text or "")) if w not in _STOP}


# MC-05: light stem for VARIANT DEDUP only (not for the answered heuristic): paraphrases often
# differ only in inflection (pricing/price, packages/package) — without stemming, the jaccard of the variant
# of the same question falls below the threshold and a "new" unknown slips through as critical.
_STEM_SUFFIX = re.compile(r"(?:ing|ed|es|e|s)$")


def _stem_tokens(text: str) -> set[str]:
    out: set[str] = set()
    for w in _tokens(text):
        if len(w) > 4:
            w = _STEM_SUFFIX.sub("", w)
        out.add(w)
    return out


def _variant_of_answered(new_text: str, store: list[dict]) -> dict | None:
    """A new unknown that is merely a PARAPHRASE of an already answered unknown (MC-05, session 7f2e13b1fcbe:
    "exact pricing for the proposed smaller starter brand package" was answered, then understanding
    re-recorded "exact price point to set for the starter package" as a NEW unknown
    — different text hash → the evergreen critical pool returned). Return the original unknown
    if it is a variant; None if the topic is genuinely new."""
    nt = _stem_tokens(new_text)
    if not nt:
        return None
    for u in store:
        if u.get("status") != ST_ANSWERED:
            continue
        ot = _stem_tokens(u.get("text") or "")
        shared = nt & ot
        if len(shared) >= _VARIANT_MIN_SHARED and _jaccard(nt, ot) >= _VARIANT_OVERLAP:
            return u
    return None


def _jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a or b else 0.0


def unknown_id(text: str) -> str:
    return "su-" + hashlib.sha1(_norm(text).encode()).hexdigest()[:8]


# ── storage (called from run_turn after a successful semantic commit) ──────

def _answers_question(utoks: set[str], ctoks: set[str], raw_claim_text: str) -> bool:
    """Answered detection WITHOUT equating word similarity with a correct answer (MC01-4).

    Four cumulative conditions: (1) not a do-not-know statement (a gap marker is not an answer);
    (2) ≥ _ANSWER_MIN_SHARED shared content tokens; (3) ≥ _ANSWER_INFO_GAIN NEW non-filler
    content tokens that are absent from the unknown text (an echo/paraphrase of the question does not pass);
    (4) jaccard ≥ _ANSWER_OVERLAP. Lexical heuristic — its limits are tested adversarially
    in evals/test_mc01_unknown_integrity.py (the reopen mechanism is the safety net)."""
    if any(m in raw_claim_text for m in _NO_ANSWER_MARKERS):
        return False
    shared = utoks & ctoks
    if len(shared) < _ANSWER_MIN_SHARED:
        return False
    if len((ctoks - utoks) - _FILLER) < _ANSWER_INFO_GAIN:
        return False
    return _jaccard(utoks, ctoks) >= _ANSWER_OVERLAP


def record_unknowns(s: Any, event: dict, unknown_texts: list[str],
                     presented_need_id: str = "") -> list[dict]:
    """Store new unknowns + mark those answered by THIS event's claims. Returns the changes (audit).

    MC01-4: every unknown carries `claim_refs` (accepted canonical claims of this event),
    `basis` ("claims"/"event_only"), and the Goal binding at record time. An unknown with no accepted
    claim is STILL STORED (not dropped — later understanding may reaffirm it),
    but is not an official candidate until it has a verifiable basis
    (see merge_semantic_candidates).
    An old unknown is considered ANSWERED when a new claim passes _answers_question. An unknown that
    appears AGAIN after being answered is reopened (the latest understanding signal wins),
    with a reopen trail + refreshed grounding.

    MC-04 (18 Oct, session e1704203f327): `presented_need_id` = the unknown ASKED in the
    previous turn (the step that was presented). The lexical heuristic _answers_question never
    matched long cross-language answers (jaccard question↔answer text ≈ 0),
    so an already-answered unknown stayed `open` and became an evergreen critical pool —
    eligibility was held at DISCOVERY_NEEDED and the "key questions left" chip stalled. The
    ask→answer conversation rule: if this turn carries an accepted claim, the unknown that
    was just asked is MARKED answered (attempted-answer; reopen remains available if
    later understanding asserts the same thing is still open)."""
    store: list[dict] = getattr(s, "semantic_unknowns", None)
    if store is None:
        store = []
        s.semantic_unknowns = store
    changes: list[dict] = []
    goal = getattr(s, "goal", None) or {}
    ev_nodes = [(n.get("id"), n.get("verbatim") or "", n.get("triple") or {})
                for n in (s.state_graph or {}).get("nodes", {}).values()
                if (n.get("provenance") or {}).get("event_id") == event["event_id"]]
    claim_refs = [nid for nid, _, _ in ev_nodes if nid]
    new_claims_text = " ".join(
        f"{vb} " + " ".join(str((v or {}).get("label") or "") for v in
                             [tr.get("subject"), tr.get("predicate"), tr.get("object")] if v)
        for _, vb, tr in ev_nodes)
    claim_toks = _tokens(new_claims_text)
    if claim_toks and claim_refs:
        for u in store:
            if u.get("status") != ST_OPEN:
                continue
            if _answers_question(_tokens(u["text"]), claim_toks, new_claims_text):
                u["status"] = ST_ANSWERED
                u["answered_event"] = event["event_id"]
                u["answered_basis"] = "lexical_overlap_info_gain"
                changes.append({"id": u["id"], "change": "answered", "by_event": event["event_id"]})
    # MC-04: an unknown just ASKED is answered by this turn's claims (ask→answer).
    # If the event does NOT carry an accepted claim (e.g. understanding failed / pure gap), the unknown
    # stays open — the asked counter (ASK_CAP) that prevents unbounded re-asking.
    if presented_need_id.startswith("su-") and claim_refs:
        u = next((x for x in store if x.get("id") == presented_need_id), None)
        if u is not None and u.get("status") == ST_OPEN:
            u["status"] = ST_ANSWERED
            u["answered_event"] = event["event_id"]
            u["answered_basis"] = "presented_then_user_claims"
            changes.append({"id": u["id"], "change": "answered", "by_event": event["event_id"]})
    for t in (unknown_texts or [])[:8]:          # kontrak so.v1: max 8 uncertainties
        text = _norm(t)
        if len(text) < 6:
            continue
        uid = unknown_id(text)
        refs = list(claim_refs)
        cur = next((u for u in store if u["id"] == uid), None)
        if cur is None:
            # MC-05: a paraphrase variant of an unknown that is ALREADY answered is not born as open —
            # the user already answered that thing; re-recording it as open creates a new critical pool
            origin = _variant_of_answered(text, store)
            if origin is not None:
                store.append({"id": uid, "text": text, "status": ST_ANSWERED,
                              "event_id": event["event_id"], "turn": int(event.get("turn") or 0),
                              "claim_refs": list(claim_refs), "basis": "claims" if claim_refs else "event_only",
                              "goal_id": str(goal.get("goal_id") or ""),
                              "goal_version": str(goal.get("version") or ""),
                              "answered_event": origin.get("answered_event") or origin.get("event_id"),
                              "answered_basis": "variant_of_answered"})
                changes.append({"id": uid, "change": "recorded_answered_variant",
                                "variant_of": origin["id"], "from_event": event["event_id"]})
                continue
            store.append({"id": uid, "text": text, "status": ST_OPEN,
                          "event_id": event["event_id"], "turn": int(event.get("turn") or 0),
                          "claim_refs": refs, "basis": "claims" if refs else "event_only",
                          "goal_id": str(goal.get("goal_id") or ""),
                          "goal_version": str(goal.get("version") or "")})
            changes.append({"id": uid, "change": "recorded", "from_event": event["event_id"]})
        elif cur["status"] == ST_ANSWERED and cur.get("answered_basis") != "variant_of_answered":
            # MC-05: a paraphrase variant does NOT reopen either — understanding that merely repeats
            # the wording is not a new signal that the thing is still open (the user already answered);
            # allowing reopen would resurrect an evergreen critical pool that was just closed.
            cur["status"] = ST_OPEN
            cur["reopened_event"] = event["event_id"]
            cur["claim_refs"] = sorted(set(cur.get("claim_refs") or []) | set(refs))
            if refs:
                cur["basis"] = "claims"
            cur["goal_id"] = str(goal.get("goal_id") or "")
            cur["goal_version"] = str(goal.get("version") or "")
            changes.append({"id": uid, "change": "reopened", "by_event": event["event_id"]})
    if len(store) > _MAX_STORED:                 # trim the earliest ANSWERED history first
        # MC01-4: DETERMINISTIC pruning — answered are sorted (turn, id) before trimming, not
        # set iteration that is nondeterministic across processes (audit P1). OPEN is never discarded
        # for capacity; if answered is exhausted and it still overflows, store as is (honest > capacity).
        overflow = len(store) - _MAX_STORED
        answered_sorted = sorted((u for u in store if u.get("status") == ST_ANSWERED),
                                 key=lambda u: (int(u.get("turn") or 0), str(u.get("id"))))
        drop = {u["id"] for u in answered_sorted[:overflow]}
        if drop:
            s.semantic_unknowns = store = [u for u in store if u["id"] not in drop]
    return changes


def asked_of_unknown(planner_log: list[dict], uid: str) -> int:
    """How many times this unknown was ASKED — from steps that were presented (not the plan)."""
    n = 0
    for e in planner_log or []:
        d = e.get("presented") or e.get("decision") or {}
        if d.get("kind") in ("QUESTION", "EVIDENCE_REQUEST") \
                and (d.get("reason") or {}).get("need_id") == uid:
            n += 1
    return n


# ── rekonsiliasi ke kandidat uncertainty (int 19 §9.4) ───────────────────────

def merge_semantic_candidates(
    s: Any, planner_candidates: list[dict], *, ask_cap: int = 2,
) -> tuple[list[dict], dict]:
    """Merge planner candidates + open semantic unknowns. Result: (merged_candidates, report).

    Semantic candidates occupy the remaining capacity AFTER planner (one canonical constant
    `MAX_UNCERTAINTY_CANDIDATES`); every exclusion/capacity is recorded — nothing disappears silently.
    Unknowns represented by a planner candidate (lexically similar) are NOT duplicated; planner remains
    the only source of requirement needs, semantics only adds those NOT represented."""
    store = list(getattr(s, "semantic_unknowns", None) or [])
    log = list(getattr(s, "planner_log", None) or [])
    planner_toks = [_tokens(str(c.get("label") or "") + " " + str(c.get("legacy_wording") or ""))
                    for c in planner_candidates]
    room = MAX_UNCERTAINTY_CANDIDATES - len(planner_candidates)
    out = list(planner_candidates)
    report: dict[str, Any] = {"open": 0, "offered": [], "excluded": [], "capacity_used": 0}
    # MC01-4: verifiable basis for an official candidate — source event status + claim_refs activity
    # + Goal binding. An event-only unknown is still stored (lifecycle runs), but only
    # becomes an official candidate after it has ≥1 active claim_refs (audit P1: unknowns from an observation
    # whose claims were all rejected must not be offered as an official need).
    ev_status = {e.get("event_id"): e.get("status") for e in (getattr(s, "events", None) or [])}
    nodes = ((getattr(s, "state_graph", None) or {}).get("nodes") or {})
    cur_goal = str((getattr(s, "goal", None) or {}).get("goal_id") or "")
    for u in store:
        if u.get("status") != ST_OPEN:
            continue
        report["open"] += 1
        asked = asked_of_unknown(log, u["id"])
        if asked >= ask_cap:
            report["excluded"].append({"id": u["id"], "why": "asked_enough"})
            continue
        ev_st = ev_status.get(u.get("event_id"))
        if ev_st is None:
            report["excluded"].append({"id": u["id"], "why": "source_event_missing"})
            continue
        if ev_st not in ("accepted", "committed", "persist_failed"):
            report["excluded"].append({"id": u["id"], "why": "source_event_not_accepted"})
            continue
        refs = u.get("claim_refs") or []
        if refs:
            if not any((nodes.get(c) or {}).get("status", "active") == "active" for c in refs):
                report["excluded"].append({"id": u["id"], "why": "basis_superseded"})
                continue
        else:
            report["excluded"].append({"id": u["id"], "why": "no_accepted_claim_basis"})
            continue
        u_goal = str(u.get("goal_id") or "")
        if u_goal and cur_goal and u_goal != cur_goal:
            report["excluded"].append({"id": u["id"], "why": "goal_changed"})
            continue
        utoks = _tokens(u["text"])
        dup = next((True for pt in planner_toks if pt and _jaccard(utoks, pt) >= _DUPLICATE_OVERLAP), False)
        if dup:
            report["excluded"].append({"id": u["id"], "why": "represented_by_planner"})
            continue
        if room <= 0:
            report["excluded"].append({"id": u["id"], "why": "candidate_capacity"})
            continue
        out.append({
            "id": u["id"], "kind": "semantic", "origin": "semantic_observation",
            "focus": {"type": "uncertainty", "id": u["id"]},
            "label": u["text"][:90], "asked": asked, "askable": True, "needed_by": 0,
            "suggested_kind": "EVIDENCE_REQUEST" if asked >= 1 else "QUESTION",
            "legacy_wording": "", "source_event": u.get("event_id", ""),
        })
        report["offered"].append(u["id"])
        room -= 1
    report["capacity_used"] = len(out)
    return out, report
