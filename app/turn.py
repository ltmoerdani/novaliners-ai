"""One conversation turn as a STATE LOOP (internal-docs §25, M4; INV-7 int 10)
— the R3 recovery path (int 16): ONE semantic-meaning authority + durable events.

    user message
      -> durable ConversationEvent             store/events.append_event  (BEFORE the LLM; EC-01)
      -> ONE contextual semantic observation   core/semantic/observation  (so.v1; F-01/F-04)
      -> deterministic verify + canonical commit core/semantic/commit     (SC-05/07/09)
      -> derivations for legacy consumers      core/semantic/derive       (evidence/numbers/tags)
      -> Goal from canonical claims (R4)       sync_goal_from_canonical
      -> navigation -> NextMove                app/navigation.navigate_session
      -> engine reply event + session save

No interview phases, no phase index, no "advance because turns ran out" on this path — that legacy
machine was removed (M5). Mechanically guarded by evals/test_m5_phase_removal.py (INV-7 item 4).

R3 changes versus the old M4 path:
- extract_turn (LLM extraction) is NO longer called here: evidence/numbers/intent-tags are derived
  from the canonical claims produced by the observation (one meaning producer; F-01). The old producer
  was removed in the 15 Oct 2026 legacy cleanup (agents/interview.py is now a type contract only).
- The message is persisted as an event BEFORE processing; an understanding failure never removes it
  (CP-25) and its status is visible (received/committed/understanding_failed).
- Quote verification is anchored to the EXACT event, not a global transcript substring (SC-05).
- Observation commit is independent of navigation success (CP-17/SC-09).
"""
from __future__ import annotations

import logging
import re
import threading
import time
from typing import Any

from agents.interview import TurnExtraction
from app.adaptive import _degraded as _degraded_presented
from app.adaptive import decide_next_move
from app.navigation import (
    PLANNER_LOG_CAP,
    TurnNavigation,
    attach_question_budget,
    clarity,
    compact_log,
    degraded_navigation,
    log_entry,
    navigate_session,
    path_affiliation,
    update_question_budget,
)
from core.navigation.planner import KIND_EVIDENCE, KIND_QUESTION
from core.schema.evidence import EvidenceItem, InterviewTurn
from store import events as event_store

log = logging.getLogger("novaliners.turn")

# Server-side gap markers (data MISSING / a refused answer; not facts) — the lesson of iters 5/6/11,
# kept for derived evidence.
GAP_MARKERS = (
    "gap:", "(gap)", "tidak dijawab", "belum dijawab", "tidak disebutkan", "refus", "refuse",
    "tidak ada datanya", "evidence gap", "belum terjawab", "belum ada data", "tidak ada angka",
    "belum ada angka", "tidak diketahui", "tidak pernah dicatat", "tidak pernah mencatat",
    "tidak ada pencatatan", "belum diukur", "tidak diukur", "tanpa data", "unknown", "tidak terukur",
    "tidak ada bukti", "belum ada bukti", "rekonstruksi dari ingatan", "tidak dapat diverifikasi",
    "tidak terverifikasi",
)
_STOP = {"yang", "dan", "di", "ke", "dari", "untuk", "tidak", "ada", "saya", "itu", "dengan", "via", "per",
         "the", "no", "a", "of"}
_KEY_TOKEN = re.compile(r"\d|rp|jt|rb|juta|ribu")
_NUM_RE = re.compile(r"\d+(?:[.,]\d+)?")


class DuplicateTurnError(RuntimeError):
    """The idempotency key was already fully processed — rejected so there is no double semantic effect."""

    def __init__(self, event_id: str):
        super().__init__(f"idempotency key sudah ter-commit pada event {event_id}")
        self.event_id = event_id


class _NoClaims:
    """An EMPTY commit result — used when UNDERSTANDING fails (MC02-P1) so the turn flow stays whole:
    no claims are invented, and the event stays saved as `understanding_failed` (CP-25)."""

    accepted_claims: list = []
    rejections: list = []
    fully_rejected = False

    @staticmethod
    def drift_entry(turn: int = 0) -> dict:
        return {}


class RetryNotApplicableError(RuntimeError):
    """MC01-2: reasoning-only recovery doesn't apply (not a DEGRADED failure of the intended user
    event, understanding not complete, or the event was superseded by a newer message)."""

    def __init__(self, code: str, msg: str):
        super().__init__(msg)
        self.code = code


def _tokens(sig: str) -> set[str]:
    return {w for w in sig.lower().split() if w not in _STOP}


def _norm_key(sig: str) -> str:
    return " ".join(sig.lower().split())[:80]


def _jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a or b else 0.0


def _nums(sig: str) -> frozenset:
    """D1 (iter-9): numbers carry meaning in a signal. Two similarly structured statements with
    DIFFERENT numbers are different facts — never deduped (v5 bug: 'klinik Rp12jt' + 'resto Rp10jt'
    deleted each other)."""
    out = set()
    for m in _NUM_RE.finditer(sig):
        try:
            f = float(m.group(0).replace(",", "."))
        except ValueError:
            continue
        if 1900 <= f <= 2100:  # a year, not a business number
            continue
        out.add(round(f, 2))
    return frozenset(out)


def ingest_evidence(s: Any, proposed: list[EvidenceItem]) -> list[EvidenceItem]:
    """Proposed evidence (now derived from canonical claims) -> the session ledger: gaps are
    server-marked, duplicates dropped (dynamic Jaccard, different numbers = different facts),
    deterministic ids ev-<tag>-<seq>.

    The LLM is not trusted with ids (#5). Evidence topic is just a display grouping label."""
    existing = [(_tokens(e.signal), _nums(e.signal)) for e in s.evidence]
    existing_keys = {_norm_key(e.signal) for e in s.evidence}
    accepted: list[EvidenceItem] = []
    for ev in proposed:
        sig_l = ev.signal.lower()
        ev.is_gap = ev.is_gap or any(m in sig_l for m in GAP_MARKERS)
        ev_tokens, ev_nums = _tokens(ev.signal), _nums(ev.signal)
        dup = _norm_key(ev.signal) in existing_keys
        if not dup:
            for t, t_nums in existing:
                if ev_nums and t_nums and ev_nums != t_nums:
                    continue  # D1: different numbers = different facts
                shared = ev_tokens & t
                thr = 0.55 if shared and any(_KEY_TOKEN.search(tok) for tok in shared) else 0.7
                if _jaccard(ev_tokens, t) >= thr:
                    dup = True
                    break
        if dup:
            continue
        existing.append((ev_tokens, ev_nums))
        existing_keys.add(_norm_key(ev.signal))
        s.evidence_seq += 1
        tag = re.sub(r"[^a-z0-9_]+", "", (ev.topic or "x").lower()) or "x"
        ev.id = f"ev-{tag}-{s.evidence_seq:03d}"
        s.evidence.append(ev)
        accepted.append(ev)
    return accepted


def run_semantic_turn(s: Any, llm: Any, event: dict) -> Any:
    """Semantic observation + verify + commit for one user event. Returns a CommitResult.

    An understanding failure marks the event understanding_failed then RERAISES — the caller
    handles provider errors honestly; the event stays durable for a retry (CP-25).
    """
    from core.semantic.commit import verify_and_commit
    from core.semantic.observation import build_context_digest, observe_semantics

    try:
        obs = observe_semantics(llm, event, build_context_digest(s, event), s.language)
        result = verify_and_commit(s, event, obs)
        # CIR-03 (int 19 §7.3): so.v1 unknowns are KEPT in the session (not dropped at commit) —
        # advisory proposals; this event's claims also mark old unknowns as answered.
        from core.reasoning.semantic_unknowns import record_unknowns
        # MC-04: an unknown ASKED in the previous turn is also marked when the user answers
        # (ask→answer) — without this, semantic unknowns become an evergreen critical pool in
        # cross-language sessions (lexical heuristics never match) and the "key questions" chip jams.
        _last = (s.planner_log or [{}])[-1]
        _pres = _last.get("presented") or _last.get("decision") or {}
        _presented_need_id = str(((_pres.get("reason") or {}).get("need_id")) or "") \
            if _pres.get("kind") in ("QUESTION", "EVIDENCE_REQUEST") else ""
        record_unknowns(s, event, list(obs.uncertainties or []),
                        presented_need_id=_presented_need_id)
    except Exception as exc:
        event_store.mark_event_status(
            s, event["event_id"], event_store.STATUS_UNDERSTANDING_FAILED,
            note=f"{type(exc).__name__}: {exc}"[:200],
        )
        raise
    event_store.mark_event_status(
        s, event["event_id"], event_store.STATUS_ACCEPTED,
        note=(f"verifier_rejected={len(result.rejections)}"
              + (" (SEMUA klaim ditolak: tidak ada fakta ter-commit)" if result.fully_rejected else ""))
        if result.rejections else "")
    s.graph_drift_reports.append(result.drift_entry(int(event.get("turn") or 0)))
    s.graph_drift_reports = s.graph_drift_reports[-100:]
    return result


def finalize_event_durable(s: Any, event: dict, *, stage_s: dict | None = None,
                           turn_t0: float | None = None) -> None:
    """Save the session snapshot (strict) THEN mark the event committed (CP-25).

    Save failure -> event persist_failed + SessionPersistenceError (HTTP 503, not a fake ACK).
    The event JSONL stays; a retry with the same key/event reprocesses idempotently.

    stage_s/turn_t0 (S1 telemetry, optional): when given, the persist_s span (strict snapshot
    duration) and request_total_s (wall time since the turn began) are written into the timing
    dict already attached to the planner_log entry — the SAME best-effort snapshot at the end of
    this function persists it, so there is no extra write (instrumentation ~ zero cost)."""
    from store.memory import store
    _t_persist = time.perf_counter()
    try:
        store.save_strict(s)
    except event_store.SessionPersistenceError:
        event_store.mark_event_status(s, event["event_id"], event_store.STATUS_PERSIST_FAILED,
                                      note="snapshot sesi gagal disimpan")
        raise
    if stage_s is not None:
        stage_s["persist_s"] = round(time.perf_counter() - _t_persist, 2)
        if turn_t0 is not None:
            stage_s["request_total_s"] = round(time.perf_counter() - turn_t0, 2)
    event_store.mark_event_status(s, event["event_id"], event_store.STATUS_COMMITTED)
    store.save(s)  # the second snapshot carries the committed status (best-effort; JSONL is authoritative)


def sync_goal_from_canonical(s: Any) -> list[str]:
    """R4-B (int 16 RC-06): the session Goal is projected from ACTIVE CANONICAL CLAIMS, not from raw
    text parsing.

    Replaces sync_goal_from_message (a regex parser over messages). Desire never becomes a target;
    targets come only from typed Quantity claims on the goal; tentative until user-confirmed (GR-05);
    a correction replaces the target without restoring the old value (goal_projection.py)."""
    from domains.revenue.schema.goal_projection import project_goal

    if not s.goal:
        return []
    new_goal, changes = project_goal(s.goal, s.state_graph)
    if not changes:
        return []
    s.goal = new_goal
    if getattr(s, "user_id", ""):
        try:
            from store import goals as workspace_goals
            workspace_goals.upsert_goal(s.user_id, s.goal)
        except Exception:  # noqa: BLE001
            pass  # best-effort — the turn keeps going
    return changes


def turn_response_from_move(
    s: Any, nav: TurnNavigation, new_evidence: list[EvidenceItem], extraction: TurnExtraction
) -> InterviewTurn:
    d = nav.presented or nav.decision   # R5: the presented step (adaptive/degraded) when available
    cand = nav.decision
    cand_txt = nav.candidate_rendered or nav.rendered
    asks = d["kind"] in (KIND_QUESTION, KIND_EVIDENCE)
    return InterviewTurn(
        kind="probe",
        next_question=nav.rendered["text"] if asks else None,
        progress=clarity(d),
        intent_tags=extraction.intent_tags,
        evidence_delta=new_evidence,
        next_move={
            "kind": d["kind"],
            "intent": d["intent"],
            "focus": d["focus"],
            "stop": d["stop"],
            "text": nav.rendered["text"],
            "headline": nav.rendered["headline"],
            "reason": d["reason"],
            "policy": d["policy"],
            # R5/P1-1: EXPLICIT Path affiliation, the SAME as GET /navigation (one helper) so the
            # decision DTO doesn't differ between endpoints; ambiguous = None, not a silent proxy.
            "path_id": path_affiliation(d, nav.routes),
            # CIR-01/05: technical status & the checkpoint offer reach the UI (degraded ≠ a business
            # HOLD; checkpoint_offer is orthogonal to the step — int 18 phase C).
            "degraded": bool(d.get("degraded")),
            "error_code": d.get("error_code", ""),
            "retry_reasoning": bool(d.get("retry_reasoning")),
            "checkpoint": d.get("checkpoint"),
        },
        navigation=attach_question_budget(nav.summary(), s),
        candidate_move={
            "kind": cand["kind"], "intent": cand["intent"], "focus": cand["focus"], "stop": cand["stop"],
            "text": cand_txt["text"], "headline": cand_txt["headline"], "reason": cand["reason"],
            "policy": cand["policy"],
        },
    )


def apply_commit_effects(s: Any, commit: Any) -> tuple[list[EvidenceItem], TurnExtraction]:
    """The derived effects of ONE semantic commit (regular turns AND Create Map): the evidence ledger,
    legacy numbers/tags, currency evidence, Goal projection. One meaning producer → one derivation path."""
    from core.semantic.derive import extraction_payload
    from domains.revenue.projection.compat_claims import revenue_number_role
    extraction = TurnExtraction(**extraction_payload(commit, number_role_mapper=revenue_number_role))
    new_evidence = ingest_evidence(s, list(extraction.evidence))
    _record_extraction_once(s, extraction)
    _sync_evidence_currency(s)
    sync_goal_from_canonical(s)
    return new_evidence, extraction


def _commit_from_graph(s: Any, event: dict) -> Any:
    """Rebuild a CommitResult from claims ALREADY in the graph for this event (resume without the LLM)."""
    from core.semantic.commit import CommitResult
    res = CommitResult(event_id=event["event_id"])
    for n in (s.state_graph or {}).get("nodes", {}).values():
        if (n.get("provenance") or {}).get("event_id") == event["event_id"]:
            res.accepted_claims.append(n)
    return res


def _sync_evidence_currency(s: Any) -> None:
    """Evidence derived from claims that are no longer active is marked superseded
    (history kept; not deleted)."""
    nodes = (s.state_graph or {}).get("nodes", {})
    for e in s.evidence:
        n = nodes.get(e.claim_id) if e.claim_id else None
        if n is not None and (n.get("status") or "active") != "active":
            e.superseded = True


def _record_extraction_once(s: Any, extraction: TurnExtraction) -> None:
    """An idempotent record_extraction: identical items already recorded are not added again."""
    def dump(x):
        return x.model_dump() if hasattr(x, "model_dump") else dict(x)
    for _t in extraction.intent_tags or []:
        d = dump(_t)
        if d not in s.intent_tags:
            s.intent_tags.append(d)
    s.intent_tags = s.intent_tags[-300:]
    for _c in extraction.number_claims or []:
        d = dump(_c)
        if d not in s.number_claims:
            s.number_claims.append(d)
    s.number_claims = s.number_claims[-300:]


class IdempotencyConflictError(RuntimeError):
    """An idempotency key reused with a different payload — rejected with no effect at all."""

    def __init__(self, key: str):
        super().__init__(f"idempotency key {key!r} sudah dipakai untuk pesan yang berbeda")
        self.key = key


_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


def _session_lock(sid: str) -> threading.RLock:
    """One turn per session at a time (MVP execution model: one process, a threadpool).
    Not a distributed queue — a multi-process deployment needs locking in the store."""
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(sid, threading.RLock())


def run_turn(s: Any, llm: Any, text: str, idempotency_key: str = "", move_ref: str = "") -> InterviewTurn:
    """One turn: durable event -> observation -> commit -> navigation -> NextMove. Saves the session.

    Exactly-once (R3.2-A): one logical request (session + key) yields one user event, one canonical
    commit, one planner entry, one engine reply. A retry recovers the already-finished result or
    continues unfinished work; the same key with a different payload is rejected. Turns on the same
    session are serialized."""
    with _session_lock(s.id):
        return _run_turn_locked(s, llm, text, idempotency_key, move_ref)


def _run_turn_locked(s: Any, llm: Any, text: str, idempotency_key: str, move_ref: str = "") -> InterviewTurn:
    # 0) idempotency (scope: this session + key). A different payload -> rejected; committed -> the
    #    previous result is recovered; otherwise the same event CONTINUES (resume), not duplicated.
    _turn_t0 = time.perf_counter()
    prior = event_store.find_by_idempotency_key(s, idempotency_key) if idempotency_key else None
    if prior is not None:
        if prior.get("role") != "user" or prior.get("text") != text:
            raise IdempotencyConflictError(idempotency_key)
        if prior.get("status") == event_store.STATUS_COMMITTED:
            # MC01-2: recover the LATEST result (after a reasoning retry), not the old degraded reply
            done = event_store.find_engine_event(s, prior["event_id"], latest=True)
            if done and done.get("result"):
                return InterviewTurn(**done["result"])
            raise DuplicateTurnError(prior["event_id"])
        event = prior
        resumed = True
    else:
        event = event_store.append_event(
            s, role="user", text=text,
            kind=event_store.KIND_OUTCOME if move_ref else event_store.KIND_MESSAGE,
            idempotency_key=idempotency_key, correlation_id=move_ref,
        )
        resumed = False

    # transcript: events are the source of truth for ordering; append the user row only when missing
    # (retry/restart with a stale snapshot), never twice.
    if not resumed:
        s.transcript.append(("user", text))
    else:
        n_user_events = sum(1 for e in s.events
                            if e.get("role") == "user" and e.get("seq", 0) <= event["seq"])
        if sum(1 for r, _ in s.transcript if r == "user") < n_user_events:
            s.transcript.append(("user", text))

    # semantics: if this event's claims ALREADY exist in the graph, don't call the LLM again (resume)
    already = _commit_from_graph(s, event) if resumed else None
    sense_failed: BaseException | None = None
    _t0 = time.perf_counter()
    _stage_s: dict[str, Any] = {}
    if already is not None and already.accepted_claims:
        commit = already
        if event.get("status") in (event_store.STATUS_RECEIVED, event_store.STATUS_UNDERSTANDING_FAILED):
            event_store.mark_event_status(s, event["event_id"], event_store.STATUS_ACCEPTED)
    else:
        try:
            _t0 = time.perf_counter()
            commit = run_semantic_turn(s, llm, event)
        except Exception as exc:  # noqa: BLE001 — MC02-P1: understanding failure = an honest DEGRADED, NOT a 500
            log.exception("pemahaman semantik gagal; giliran disajikan DEGRADED (event tetap tersimpan)")
            commit = _NoClaims()
            sense_failed = exc
        finally:
            _stage_s = {"semantic_s": round(time.perf_counter() - _t0, 2)}

    # non-authoritative derivations for legacy consumers (evidence, numbers, UI tags) + Goal projection
    # from canonical claims
    goal_before = dict(s.goal) if s.goal else None
    new_evidence, extraction = apply_commit_effects(s, commit)
    # R6: a Move outcome observation is bound to its Move (valid only after EXECUTED), before reasoning.
    # BC-02: a stale Move (another Goal/version) receives no observation — honestly rejected, turn lives on.
    if move_ref or event.get("kind") == event_store.KIND_OUTCOME:
        from app import moves as _moves
        try:
            _moves.attach_observation(s, move_ref or event.get("correlation_id", ""), event["event_id"],
                                      [c["id"] for c in commit.accepted_claims])
        except _moves.MoveError as exc:
            log.warning("observasi outcome tidak diikat ke Move: %s", exc)
    # R6: change classification + living checkpoints (a diagnosis = a checkpoint, not the conversation's end)
    from app import checkpoints as _cp
    change = _cp.classify_change(commit=commit, goal_before=goal_before, goal_after=s.goal,
                                 event_kind=event.get("kind", ""), move_ref=move_ref)
    _cp.mark_stale(s, event_id=event["event_id"], change=change)

    eng = event_store.find_engine_event(s, event["event_id"], latest=True)
    logged = next((e for e in s.planner_log if e.get("event_id") == event["event_id"]), None)
    resp: InterviewTurn | None = InterviewTurn(**eng["result"]) if eng and eng.get("result") else None
    _t1 = time.perf_counter()
    nav = None
    if resp is None or logged is None:
        asked = [e for e in s.planner_log if e.get("event_id") != event["event_id"]] if resumed else None
        if sense_failed is not None:
            # MC02-P1: understanding failed → reasoning is NOT called (no new facts to assess);
            # serve a degraded with its own code so the user knows the message wasn't read.
            # Retry reasoning deliberately doesn't apply here: the message must be re-read (resend).
            from core.reasoning.contract import NM_CONTRACT_VERSION
            nav = degraded_navigation(s, sense_failed)
            nav.presented = _degraded_presented(
                nav, ((getattr(s, "language", None) or "en")[:2]).lower(), "understanding_failed")
            nav.adaptive = {"contract": NM_CONTRACT_VERSION, "status": "DEGRADED",
                            "reason": "understanding_failed", "error_code": "UNDERSTANDING_FAILED"}
            nav.candidate_rendered = nav.rendered
            nav.rendered = {"text": nav.presented["text"], "headline": nav.presented["headline"],
                            "lang": nav.presented["lang"]}
        else:
            # S1 telemetry: navigation_s = navigate_session INCLUSIVE of Layer C (second pass). The
            # second_pass_s below is a span NESTED inside navigation_s — don't sum them twice.
            _t_nav = time.perf_counter()
            try:
                nav = (navigate_session(s, asked_from=asked, llm=llm) if asked is not None
                       else navigate_session(s, llm=llm))
            except Exception as exc:  # fail-safe: the conversation doesn't crash; honest HOLD + visible error
                # SC-09/CP-17: a navigation failure does NOT undo the already-committed observation.
                log.exception("navigasi gagal; giliran dilanjutkan dengan HOLD")
                nav = degraded_navigation(s, exc)
            _stage_s["navigation_s"] = round(time.perf_counter() - _t_nav, 2)
            _t_reason = time.perf_counter()
            if resp is None:
                nav = decide_next_move(s, llm, nav, event)   # R5: adaptive reasoning (guard-validated)
            else:  # resume over a finished response: don't call the model again; recover what was presented
                nav.presented = {"source": "recovered", **(resp.next_move or {})}
                nav.adaptive = {"contract": "nm.v2", "status": "RECOVERED"}
            _stage_s["reasoner_s"] = round(time.perf_counter() - _t_reason, 2)
            _sp = ((nav.adjudication or {}).get("second_pass") or {})
            if _sp.get("elapsed_s") is not None:
                _stage_s["second_pass_s"] = _sp["elapsed_s"]
                _stage_s["second_pass_llm_s"] = _sp.get("llm_elapsed_s")
            _adaptive_stage = (nav.adaptive or {}).get("stage_s") or {}
            if _adaptive_stage.get("adaptive_total_s") is not None:
                _stage_s["adaptive_total_s"] = _adaptive_stage["adaptive_total_s"]
            if _adaptive_stage.get("reasoner_s") is not None:
                _stage_s["valid_guarded_move_s"] = _adaptive_stage["reasoner_s"]
        s.last_adjudication = nav.adjudication
        if resp is None:
            # MC-07: budget updates ONLY on the primary response path (not a reasoning retry that
            # re-presents the step for the same event — anti double counting).
            update_question_budget(s, nav)
            resp = turn_response_from_move(s, nav, new_evidence, extraction)
            resp.change_class = change
            resp.checkpoint = _cp.summary(_cp.latest(s))

    _stage_s["reason_s"] = round(time.perf_counter() - _t1, 2)
    reply_text = (resp.next_move or {}).get("text") if resp.next_move else None
    reply_text = reply_text or (nav.rendered["text"] if nav else "")
    if eng is None:
        event_store.append_event(
            s, role="engine", kind=event_store.KIND_ENGINE, text=reply_text,
            correlation_id=event["event_id"], result=resp.model_dump(),
        )
    n_eng_events = sum(1 for e in s.events if e.get("role") == "engine")
    if sum(1 for r, _ in s.transcript if r == "engine") < n_eng_events:
        s.transcript.append(("engine", reply_text))
    if logged is None and nav is not None:
        turn_no = sum(1 for role, _ in s.transcript if role == "user")
        entry = log_entry(nav, turn_no)
        entry["event_id"] = event["event_id"]
        # MC02-latency: per-stage time is visible (so optimization is measured, not guessed).
        _stage_s["total_s"] = round(time.perf_counter() - _turn_t0, 2)
        entry["timing"] = _stage_s
        s.planner_log.append(entry)
        s.planner_log = compact_log(s.planner_log[-PLANNER_LOG_CAP:])
        log.info("giliran %s selesai: semantic=%ss navigation=%ss reasoner=%ss second_pass=%ss "
                 "reason=%ss total=%ss attempts=%s",
                 turn_no, _stage_s.get("semantic_s"), _stage_s.get("navigation_s"),
                 _stage_s.get("reasoner_s"), _stage_s.get("second_pass_s"),
                 _stage_s.get("reason_s"), _stage_s.get("total_s"),
                 len((nav.adaptive or {}).get("attempts") or []))
    if sense_failed is not None:
        # MC02-P1: the message STAYS saved durably, but its status stays honestly `understanding_failed`
        # — not `committed` (no canonical observation was born). Marking it committed here would inflate
        # status and allow a reasoning retry over a message that was never read.
        from store.memory import store as _session_store
        _t_persist = time.perf_counter()
        try:
            _session_store.save_strict(s)
        except event_store.SessionPersistenceError:
            event_store.mark_event_status(s, event["event_id"], event_store.STATUS_PERSIST_FAILED,
                                          note="snapshot sesi gagal disimpan")
            raise
        _stage_s["persist_s"] = round(time.perf_counter() - _t_persist, 2)
        _stage_s["request_total_s"] = round(time.perf_counter() - _turn_t0, 2)
        event_store.mark_event_status(s, event["event_id"], event_store.STATUS_UNDERSTANDING_FAILED,
                                      note="pemahaman gagal; pesan tersimpan untuk dibaca ulang")
        _session_store.save(s)
    else:
        finalize_event_durable(s, event, stage_s=_stage_s, turn_t0=_turn_t0)
    return resp


def retry_reasoning(s: Any, llm: Any, event_id: str = "") -> InterviewTurn:
    """MC01-2 (audit CIR-MC01 P0-B; int 19 §12.6): committed observation → reasoning failed
    → RE-RUN REASONING over the existing State — the user is NOT asked to resend the story.

    Invariant: no second user event, no semantic re-observation, no duplicate evidence/claims;
    every attempt is recorded append-only in planner_log (`reasoning_retry`) and the new engine
    reply correlates the same event."""
    with _session_lock(s.id):
        return _retry_reasoning_locked(s, llm, event_id)


def _retry_reasoning_locked(s: Any, llm: Any, event_id: str) -> InterviewTurn:
    commit_ready = (event_store.STATUS_ACCEPTED, event_store.STATUS_COMMITTED,
                    event_store.STATUS_PERSIST_FAILED)
    users = [e for e in s.events if e.get("role") == "user"]
    if event_id:
        event = next((e for e in users if e.get("event_id") == event_id), None)
        if event is None:
            raise RetryNotApplicableError("EVENT_NOT_FOUND", f"event user '{event_id}' tidak ditemukan")
    else:
        # MC02-P1: when the LATEST message itself was never read (e.g. understanding_failed), report
        # THAT as-is — don't jump to an older readable event and then say "a newer message exists"
        # (technically true, misleading as guidance: what's needed is a resend).
        newest = users[-1] if users else None
        if newest is not None and newest.get("status") not in commit_ready:
            raise RetryNotApplicableError(
                "EVENT_NOT_COMMITTED",
                f"pesan terakhir ({newest['event_id']}) berstatus {newest.get('status')} — pemahaman "
                "belum selesai; kirim ulang pesan itu melalui /message (idempoten)")
        event = next((e for e in reversed(users) if e.get("status") in commit_ready), None)
        if event is None:
            raise RetryNotApplicableError(
                "NO_COMMITTED_EVENT", "tidak ada event user yang pemahamannya sudah diterima")
    if event.get("status") not in commit_ready:
        raise RetryNotApplicableError(
            "EVENT_NOT_COMMITTED",
            f"event {event['event_id']} berstatus {event.get('status')} — pemahaman belum selesai; "
            "kirim ulang pesan melalui /message (idempoten)")
    if any(e.get("seq", 0) > event.get("seq", 0) for e in users):
        raise RetryNotApplicableError(
            "SUPERSEDED_BY_NEWER_EVENT",
            "sudah ada pesan user lebih baru — percakapan berlanjut dari pesan tersebut")
    entries = [e for e in s.planner_log if e.get("event_id") == event["event_id"]]
    last = entries[-1] if entries else None
    if last is None or (last.get("adaptive") or {}).get("status") != "DEGRADED":
        raise RetryNotApplicableError(
            "NOT_DEGRADED", "tidak ada kegagalan reasoning yang bisa dicoba ulang untuk event ini")

    # Resource-usage snapshot BEFORE — for exactly-once regression (MC01-2 test).
    asked = [e for e in s.planner_log if e.get("event_id") != event["event_id"]]
    try:
        nav = navigate_session(s, asked_from=asked, llm=llm)
    except Exception as exc:  # noqa: BLE001 — fail-safe, same contract as run_turn
        log.exception("navigasi gagal saat retry reasoning")
        nav = degraded_navigation(s, exc)
    nav = decide_next_move(s, llm, nav, event)
    from app import checkpoints as _cp
    resp = turn_response_from_move(s, nav, [], TurnExtraction())
    resp.checkpoint = _cp.summary(_cp.latest(s))
    reply_text = (resp.next_move or {}).get("text") or nav.rendered["text"]
    event_store.append_event(
        s, role="engine", kind=event_store.KIND_ENGINE, text=reply_text,
        correlation_id=event["event_id"], result=resp.model_dump(),
    )
    n_eng = sum(1 for e in s.events if e.get("role") == "engine")
    if sum(1 for r, _ in s.transcript if r == "engine") < n_eng:
        s.transcript.append(("engine", reply_text))
    entry = log_entry(nav, sum(1 for role, _ in s.transcript if role == "user"))
    entry["event_id"] = event["event_id"]
    entry["reasoning_retry"] = True
    entry["reasoning_retry_attempt"] = len(entries) + 1
    s.planner_log.append(entry)
    s.planner_log = compact_log(s.planner_log[-PLANNER_LOG_CAP:])
    finalize_event_durable(s, event)
    return resp
