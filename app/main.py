"""Revenue Navigation MVP-1 — FastAPI entry.

Run: uvicorn app.main:app --reload  (from the mvp/ folder)
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Literal
from urllib.parse import unquote

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from openai import APITimeoutError, AuthenticationError, RateLimitError
from pydantic import BaseModel, Field

# ENV_PATH & .env bootstrap now live in llm/runtime.py (imported below) —
# iter-19: removed the duplicate definition that was shadowed by the import.
from llm.runtime import ENV_PATH as _ENV_PATH  # noqa: E402

load_dotenv(_ENV_PATH, override=True)

# INFO logs from the provider (e.g. per-call token consumption) don't show when the root
# logger has no handler yet — uvicorn only configures its own loggers.
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format="%(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)   # one line per request, not informative
logging.getLogger("httpx2").setLevel(logging.WARNING)  # this openai SDK version uses httpx2

from agents.ask import ask_session  # noqa: E402
from agents.diagnosis import synthesize  # noqa: E402
from agents.explain import VERSION as explain_version  # noqa: E402
from agents.explain import basis_of as explain_basis  # noqa: E402
from agents.explain import explain_session  # noqa: E402
from app.finalization import certify_artifact  # noqa: E402 — dsc.v1: label certification (int 18 §12.5)
from app.navigation import (  # noqa: E402 — M4: conversation state loop
    asked_counts,
    compose_routes_for_paths,
    navigate_session,
    path_affiliation,
    replay_logged,
)
from app.turn import (  # noqa: E402
    DuplicateTurnError,
    IdempotencyConflictError,
    RetryNotApplicableError,
    run_semantic_turn,
    run_turn,
)
from core.llm import strip_code_fences  # noqa: E402 — clean copilot free-text answers
from core.navigation.compat import is_legacy  # noqa: E402
from core.schema.evidence import InterviewTurn  # noqa: E402
from domains.revenue.projection.readiness import build_readiness_projection  # noqa: E402
from domains.revenue.prompts.copilot_and_journey import COPILOT_SYSTEM  # noqa: E402 — audit prompt 25 Sep
from domains.revenue.schema.artifact import DiagnosisArtifact  # noqa: E402
from domains.revenue.schema.goal import (  # noqa: E402 — P-A + Goal-Relative
    Goal,
    build_goal,
    mint_goal_id,
)
from domains.revenue.schema.measurement_contract import kind_check  # noqa: E402
from domains.revenue.stages.journey import (  # noqa: E402
    compile_journey_context,
    compute_delta,
    prior_action_summary,
    reassess_status,
)
from domains.revenue.stages.trajectory import (  # noqa: E402 — P-F
    decision_trajectory,
    drift_taxonomy,
    goal_series,
    goal_trajectory,
)
from llm.runtime import (  # noqa: E402
    _ACTIVE,
    _PROVIDER_MODELS,
    ENV_PATH,
    SWITCHABLE_PROVIDERS,
    build_llm,
    get_llm,
    provider_info,
)
from ontology.route.plan import RouteCompositionError  # noqa: E402
from ontology.route.projection import project_maps  # noqa: E402  — R2 canonical Maps projection
from store import (  # noqa: E402
    checkins,  # D-02: durable check-in history (not localStorage)
    funnel,
    path_states,  # P-E edge outcome→path
    route_execution,  # execution_view for route nodes (per-user event ledger)
    route_lineages,
    workspace,  # P-D workspace + snapshot/diff
)
from store import goals as workspace_goals  # noqa: E402 — Goal-Relative workspace records
from store import nba as nba_store  # noqa: E402
from store.events import EventPersistenceError  # noqa: E402
from store.memory import store  # noqa: E402
from store.user_scope import validate_user_id  # noqa: E402

app = FastAPI(title="Revenue Navigation MVP-1", version="0.1.0")
# UI v9 = 21 small scripts + CSS: compress them (and JSON) so first paint is not a transfer problem
app.add_middleware(GZipMiddleware, minimum_size=1024)


# BC-02/CP-30 (int 16, DR-17): actor authentication OPTIONAL via env
# NOVALINERS_ACTOR_TOKENS (JSON {token: user_id}). LOCAL mode (empty env) =
# the legacy MVP behavior, NOT for public multi-user. TOKEN mode: bearer required,
# actor DERIVED from the token (client-provided user_id is not authoritative),
# session/workspace ownership enforced (403). Details: app/auth.py.
from app import auth as app_auth  # noqa: E402


@app.middleware("http")
async def actor_auth_guard(request: Request, call_next):
    if app_auth.auth_mode() == "token":
        path = request.url.path
        if path not in app_auth.EXEMPT_PATHS:
            actor = app_auth.authenticate(request.headers.get("authorization"))
            if actor is None:
                return JSONResponse({"detail": "auth wajib: Authorization: Bearer <token>"}, status_code=401)
            request.state.actor = actor
            m = re.match(r"^/session/([^/]+)(/|$)", path)
            if m and not app_auth.actor_from_path_session(unquote(m.group(1)), actor):
                return JSONResponse({"detail": "sesi milik actor lain"}, status_code=403)
            w = re.match(r"^/workspace/([^/]+)(/|$)", path)
            if w and unquote(w.group(1)) != actor:
                return JSONResponse({"detail": "workspace milik actor lain"}, status_code=403)
    return await call_next(request)

# iter-14: identify the CODE the server serves — lesson from run v7: 2 of 4
# audit findings were stale-server artifacts (an old process running old code).
# /health now carries the commit hash + uptime so staleness is detected automatically.
_SERVER_STARTED = time.time()

def _git_hash() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).resolve().parent.parent,
            capture_output=True, text=True, timeout=3,
        ).stdout.strip() or "unknown"
    except Exception:
        return "unknown"

_GIT_HASH = _git_hash()

def _secret_status(name: str) -> str:
    """Key status without leaking the value into logs."""
    return f"set(len={len(os.environ[name])})" if os.environ.get(name) else "MISSING"


from engine.knowledge import code_commit_hash, kb_sha256  # noqa: E402

# 18 Sep 2026 incident: a pre-fix server served live sessions → wrong-column artifacts.
# The BOOT banner now MUST carry the code + KB identity this process serves.
print(
    f"[BOOT] code={code_commit_hash()} kb={kb_sha256()} .env={ENV_PATH} "
    f"provider={os.environ.get('LLM_PROVIDER', 'mock')} "
    f"model={os.environ.get('LLM_MODEL') or '(dari var provider)'} "
    f"vertex_key={_secret_status('VERTEX_API_KEY')} gemini_key={_secret_status('GEMINI_API_KEY')}",
    flush=True,
)


class CreateSession(BaseModel):
    goal_text: str
    language: str = "en"
    # J3 (internal-docs §7): cross-session identity & linkage (optional — backward compat)
    user_id: str = ""
    prior_session_id: str = ""
    # P-A (internal-docs §2.1): Desire → Goal operationalization.
    # All optional — empty → parsed deterministically from goal_text (origin recorded).
    desire: str = ""
    motivation: str = ""
    target: float | None = None
    baseline: float | None = None
    deadline_days: int | None = None
    success_definition: str = ""
    # Goal-Relative (internal-docs §2.1/§9 Phase 1): explicit metric contract —
    # registry-backed (ADR-GR1); unregistered metric_id → 422 (GR-17 abstain, not mapped
    # to the nearest revenue slot). Explicit input beats the parse (origin = explicit_input).
    metric_id: str = ""
    direction: str = ""
    category: str = ""
    unit: str = ""
    scope: str = ""
    measurement_window_days: int | None = None
    target_min: float | None = None
    target_max: float | None = None
    goal_id: str = ""


class Message(BaseModel):
    text: str
    # R3 (int 16 §R3-A/EC-01): optional client idempotency key — a resubmission must not
    # produce a double semantic effect; an event whose key failed to be understood is reprocessed.
    idempotency_key: str = ""
    # R6: when set, the message = the OUTCOME OBSERVATION of a Move (event `outcome_observation`),
    # not a regular message.
    move_id: str = ""


def _llm_http_exc(e: Exception) -> HTTPException:
    """Map provider errors to user-friendly messages (provider-aware, not hardcoded to Z.AI)."""
    provider = _ACTIVE["provider"] or os.environ.get("LLM_PROVIDER", "mock")
    if isinstance(e, RateLimitError):
        return HTTPException(
            429,
            f"AI engine ({provider}) menolak request: limit/saldo/kuota. "
            "Cek dashboard provider atau ganti model via POST /admin/model.",
        )
    if isinstance(e, APITimeoutError):
        return HTTPException(
            504,
            f"AI engine ({provider}) timeout. Coba lagi, atau pakai model yang lebih cepat "
            "(POST /admin/model).",
        )
    if isinstance(e, AuthenticationError):
        return HTTPException(
            502,
            f"API key {provider} tidak valid/expired. Generate key baru dan update .env.",
        )
    return HTTPException(502, f"LLM gagal ({provider}): {type(e).__name__}: {str(e)[:200]}")


@app.post("/session")
def create_session(request: Request, body: CreateSession):
    # BC-02/DR-17: in TOKEN mode, the body's user_id is not authoritative — the actor comes
    # from the token (middleware); a session may only be claimed on the actor's own behalf.
    actor = getattr(request.state, "actor", None)
    if actor and body.user_id and body.user_id != actor:
        raise HTTPException(403, "user_id tidak cocok dengan identitas actor token")
    if body.user_id:
        # D8: user_id = a per-user store path component — reject at the entrance
        # (400), not with silent traversal or a 500 inside the store.
        try:
            validate_user_id(body.user_id)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
    if body.prior_session_id and not store.get(body.prior_session_id):
        raise HTTPException(404, f"prior_session '{body.prior_session_id}' tidak ditemukan")
    # R1-remediation Probe A/B (17 Oct) — context continuity: a follow-up session of the
    # same map (prior_session_id, no explicit goal_id) INHERITS the originating session's
    # goal, so goal_id = a business-context identity that stays STABLE across sessions
    # (evidence/eCredit/routes don't break between sessions of one map). A NEW session
    # without prior = a NEW business context (new goal_id) — two businesses owned by the
    # same user no longer share state. An explicit body goal_id still wins.
    _inherited_goal: dict | None = None
    if body.prior_session_id and not body.goal_id:
        _prior = store.get(body.prior_session_id)
        if _prior is not None and getattr(_prior, "goal", None):
            if _prior.user_id and body.user_id and _prior.user_id != body.user_id:
                raise HTTPException(403, "prior_session milik user lain — goal tidak diwarisi")
            _inherited_goal = dict(_prior.goal)
    # P-A: the goal is always operationalized (explicit input > parser; number origin
    # tracked via target_origin — downstream guards can tell marker vs fallback apart).
    # Goal-Relative: explicit registry metric contract; stable goal_id minted when new.
    try:
        goal_obj = build_goal(
            body.goal_text,
            desire=body.desire, motivation=body.motivation,
            target=body.target, baseline=body.baseline,
            deadline_days=body.deadline_days,
            success_definition=body.success_definition,
            metric_id=body.metric_id, direction=body.direction,
            category=body.category, unit=body.unit, scope=body.scope,
            measurement_window_days=body.measurement_window_days,
            target_min=body.target_min, target_max=body.target_max,
            goal_id=body.goal_id, workspace_id=body.user_id,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if not goal_obj.goal_id:
        goal_obj.goal_id = mint_goal_id()
    if _inherited_goal is not None:
        goal_obj = _inherited_goal  # inherited context: the goal (and goal_id) of the same map
    # goal_obj may be a pydantic model (build_goal path) or an inherited dict
    # (prior_session continuity) — one dump shape for store + workspace.
    goal_dump = goal_obj if isinstance(goal_obj, dict) else goal_obj.model_dump()
    s = store.create(body.goal_text, body.language,
                     user_id=body.user_id,
                     prior_session_id=body.prior_session_id,
                     goal=goal_dump)
    # Goal-Relative (int 09 §4.4): goal as a first-class workspace record — GOAL_CREATED/REVISED +
    # activation (the next evaluation refers to this goal); without user_id → silent degrade.
    if body.user_id:
        try:
            workspace_goals.upsert_goal(body.user_id, goal_dump)
        except Exception:
            pass  # best-effort — never fail session creation
    first_question = _ingest_initial_story(s)
    return {"session_id": s.id, "goal": s.goal, "first_question": first_question}


def _initial_story_text(body: CreateSession) -> str:
    """The user's initial story AS-IS (BC-04): original fragments labeled, no meaning edits."""
    parts = []
    if (body.desire or "").strip():
        parts.append(f"My desire: {body.desire.strip()}")
    if (body.motivation or "").strip():
        parts.append(f"My motivation: {body.motivation.strip()}")
    parts.append(body.goal_text.strip())
    return chr(10).join(p for p in parts if p)


def _ingest_initial_story(s) -> str:
    """R3/BC-04: the Create Map input becomes the first durable EVENT, understood by the same
    semantic pipeline, and the first question is picked from what has ALREADY been understood —
    not a generic revenue template (CP-32, F-11). An understanding failure never drops the event;
    the first question falls back to an honest elaboration invite."""
    from store import events as event_store

    _init_t0 = time.perf_counter()
    _init_stage: dict = {}
    text = _story_from_session(s)
    try:
        ev = event_store.append_event(s, role="user", kind=event_store.KIND_CREATE_MAP, text=text)
    except EventPersistenceError:
        raise  # a session without durable events must never run silently (EC-01)
    s.transcript.append(("user", text))
    commit = None
    llm = None
    # S1 telemetry: the FIRST turn (/session) uses the same spans as /message so the latency
    # denominators don't mix initialization with regular turns.
    _t_sem = time.perf_counter()
    try:
        llm = get_llm()
        llm.use_session(s.id)
        commit = run_semantic_turn(s, llm, ev)
    except Exception:
        # the event stays in place (status understanding_failed); never fail session creation —
        # the first question becomes an elaboration invite, a user retry will fix it.
        pass
    finally:
        _init_stage["semantic_s"] = round(time.perf_counter() - _t_sem, 2)
    if commit is not None:
        from app.turn import apply_commit_effects, finalize_event_durable
        apply_commit_effects(s, commit)   # Create Map also derives evidence/Goal (a single path)
        # persist_s (strict snapshot) is recorded into _init_stage via finalize_event_durable.
        finalize_event_durable(s, ev, stage_s=_init_stage)  # SessionPersistenceError -> honest failure
    else:
        from store.memory import store as _store
        _store.save(s)
    first = _first_move(s, llm, ev, init_stage=_init_stage)
    _init_entry = s.planner_log[-1] if s.planner_log else None
    if _init_entry is not None and _init_entry.get("event_id") == ev["event_id"]:
        _init_entry.setdefault("timing", {})
        _init_entry["timing"]["session_init_s"] = round(time.perf_counter() - _init_t0, 2)
    # the first question = part of the conversation: engine event + transcript (consistent Q&A pairs)
    s.transcript.append(("engine", first))
    event_store.append_event(s, role="engine", kind=event_store.KIND_ENGINE, text=first,
                             correlation_id=ev["event_id"])
    from store.memory import store as _store2
    _store2.save(s)
    return first


def _story_from_session(s) -> str:
    """Rebuild the initial story text from session state (stored goal_text + desire/motivation)."""
    goal = getattr(s, "goal", None) or {}
    parts = []
    if (goal.get("desire") or "").strip():
        parts.append(f"My desire: {goal['desire'].strip()}")
    if (goal.get("motivation") or "").strip():
        parts.append(f"My motivation: {goal['motivation'].strip()}")
    parts.append((getattr(s, "goal_text", "") or "").strip())
    return chr(10).join(p for p in parts if p)


def _first_move(s, llm, ev, init_stage: dict | None = None) -> str:
    """R5: the first question = the SAME adaptive NextMove as any other turn (one authority), from the
    freshly understood state; logged in planner_log so the "already asked" counter stays correct. The
    legacy deterministic chooser (Goal→gap→assumption→elaboration) is REMOVED. Failure → an honest
    HOLD `degraded` (the story stays saved)."""
    from app.adaptive import decide_next_move
    from app.navigation import (
        degraded_navigation,
        log_entry,
        navigate_session,
        update_question_budget,
    )

    # S1 telemetry: /session stage spans; init_stage (semantic/persist) merged into the same entry.
    _nav_stage: dict = {}
    _t_nav = time.perf_counter()
    try:
        nav = navigate_session(s, llm=llm)
    except Exception as exc:  # noqa: BLE001 - never fail session creation
        nav = degraded_navigation(s, exc)
    _nav_stage["navigation_s"] = round(time.perf_counter() - _t_nav, 2)
    _t_reason = time.perf_counter()
    nav = decide_next_move(s, llm, nav, ev)
    _nav_stage["reasoner_s"] = round(time.perf_counter() - _t_reason, 2)
    _sp = ((nav.adjudication or {}).get("second_pass") or {})
    if _sp.get("elapsed_s") is not None:
        _nav_stage["second_pass_s"] = _sp["elapsed_s"]
    entry = log_entry(nav, 1)
    entry["event_id"] = ev["event_id"]
    entry["timing"] = {**(init_stage or {}), **_nav_stage}
    s.planner_log.append(entry)
    # MC-07: question budget batch #1 opens together with the first step — monotonically
    # numbered chips are available from Create Map on (the UI reads them via GET /navigation).
    update_question_budget(s, nav)
    s.last_adjudication = nav.adjudication
    from store.memory import store as _store
    _store.save(s)
    return nav.rendered["text"]


def _reality(s) -> dict:
    """R6-F: ONE reality across destinations (STATE/MAPS/MOVES/JOURNEY/TALK). Every payload carries the same
    canonical state fingerprint + checkpoint + Goal version, so conflicting stale snapshots are detectable
    (the UI compares state_version).

    D-05 (V4, 18 Oct 2026): state_version only fingerprints ACTIVE claims — route execution, the
    Move lifecycle,
    outcomes, and lineage do NOT change it. `projection_revision` is a composite revision (claims + lineage +
    execution + outcomes + Goal/checkpoint) so a checkbox that only writes the execution ledger still changes
    the revision every screen reads, without faking the claim state."""
    from app import checkpoints as _cp
    from app import experience_contract as _ec
    from app.binding import state_version
    cp = _cp.latest(s)
    try:
        # D-04/C55: the composite revision is IDENTICAL on every surface. It is deliberately CHEAP:
        # it must NOT build the graph or re-compose routes, because that would be a write side effect
        # and a large cost on every read. graph_revision stays a separate field in GET /experience.
        rev = _ec.reality_revision(s)
    except Exception:  # noqa: BLE001 — base reality must not vanish because a derived projection failed
        rev = {"projection_revision": None, "route_lineage_revision": None,
               "execution_revision": None, "outcome_revision": None, "graph_revision": None}
    return {"state_version": state_version(s), "checkpoint_id": (cp or {}).get("checkpoint_id"),
            "checkpoint_version": (cp or {}).get("version"), "checkpoint_status": (cp or {}).get("status"),
            "goal_id": (s.goal or {}).get("goal_id", ""), "goal_version": (s.goal or {}).get("version"),
            "moves": len(getattr(s, "moves", None) or []),
            "projection_revision": rev.get("projection_revision"),
            "route_lineage_revision": rev.get("route_lineage_revision"),
            "execution_revision": rev.get("execution_revision"),
            "outcome_revision": rev.get("outcome_revision"),
            "link_revision": rev.get("link_revision")}
    # NOTE: graph_revision is intentionally NOT part of this lightweight reality block: it is only
    # meaningful where the graph is built (GET /experience), and a null here would read as "no graph".


@app.post("/session/{sid}/message", response_model=InterviewTurn)
def message(sid: str, body: Message):
    """One conversation turn = one STATE LOOP pass (internal-docs §25, M4; INV-7):

        message -> evidence extraction -> Universal State -> live adjudication -> path -> route (optional)
                -> Applicable Requirement Set -> Requirement State Reader -> Question Planner -> NextMove

    The next step is chosen from state and uncertainty (QUESTION | EVIDENCE_REQUEST | ACTION | HOLD,
    with a reason trail), NOT from phases. The LLM only interprets the message into evidence (a proposal);
    step status and decisions belong to the deterministic engine."""
    s = store.get(sid)
    if not s:
        raise HTTPException(404, "session not found")
    # R6 (int 16 §R6-A): diagnosis = a CHECKPOINT, not the end of the conversation. Previously
    # `interview_done` returned `ack` and ignored user corrections; now post-diagnosis messages
    # enter the same path (durable event → canonical state → hypotheses/evaluation) and the last
    # checkpoint is marked `stale` when the change is material.
    if body.move_id:
        from app import moves as _moves
        mv_ = _moves.get_move(s, body.move_id)
        if mv_ is None:
            raise HTTPException(404, f"move '{body.move_id}' tidak ditemukan")
        # A3-F2 (Round 7, AC-G): a stale/foreign move_id (another Goal / a newer Goal version) is
        # rejected HERE — before the outcome event is written, classified, or semantically committed.
        if scope := _moves.goal_scope_problems(s, mv_):
            raise HTTPException(409, scope[0])
        if mv_["lifecycle"] not in (_moves.EXECUTED, _moves.OBSERVED, _moves.INCONCLUSIVE):
            raise HTTPException(409, f"observasi hanya sah setelah Move dieksekusi (kini {mv_['lifecycle']})")
    _snapshot_experience_before(s, persist=False)   # P1-06: run_turn saves on success
    llm = get_llm()
    llm.use_session(sid)   # the Go gateway answers 400 MissingSessionID without a session id
    try:
        return run_turn(s, llm, body.text, idempotency_key=body.idempotency_key, move_ref=body.move_id)
    except IdempotencyConflictError as e:
        raise HTTPException(422, str(e)) from e
    except DuplicateTurnError as e:
        # idempotency: the key is already committed — an explicit 409, not a double effect (EC-01)
        raise HTTPException(409, str(e)) from e
    except EventPersistenceError as e:
        # the message FAILED to persist: reject before any effect; never pretend it was saved
        raise HTTPException(503, f"pesan belum tahan-lama, coba lagi: {e}") from e
    except (RateLimitError, AuthenticationError, APITimeoutError) as e:
        raise _llm_http_exc(e)


class NextMoveBody(BaseModel):
    """Phase 7 (§10 case B): the user ASKS the engine to resolve the next authorized navigation state
    at the result boundary. Not silent, not a checkpoint, not an automatic side effect of a checkbox.

    The body carries no replay key on purpose: this is a DECISION request, and running it again is the
    same question again. The `MOVE_ALREADY_ACTIONABLE` / `RESULT_STILL_PENDING` guards are what stop a
    second decision from being taken while one is still open."""
    note: str = ""


def _last_user_event_id(s) -> str:
    """The durable user event this decision is bound to. Deterministic Move ids depend on it, so a
    replayed request cannot mint a second Move for the same boundary."""
    for ev in reversed(list(getattr(s, "events", None) or [])):
        if isinstance(ev, dict) and ev.get("role") == "user" and ev.get("event_id"):
            return str(ev["event_id"])
    return ""


_NEXT_MOVE_LOCKS: dict[str, threading.Lock] = {}


def _materialize_frontier_move(s, *, event_id: str) -> dict | None:
    """Turn an ALREADY AUTHORIZED route frontier node into a canonical Move (deterministic, 0-LLM).

    The route selector is the existing authority that decides which node of a path can be executed
    now; the Move is the canonical unit of work for that node. Returns None when the frontier does not
    authorize an EXECUTE, when the node has no usable name, or when the design does not pass G10 - in
    which case nothing is created and the caller keeps the honest frontier."""
    from app import moves as _mv
    try:
        payload, _degraded = _read_only_route_payload(s)
    except Exception:  # noqa: BLE001 - a route read fault never fabricates work
        return None
    nm = (payload or {}).get("next_move") or {}
    if str(nm.get("output") or "") != "ACTION":
        return None
    rid, nid = str(nm.get("route_id") or ""), str(nm.get("frontier_ref") or "")
    route = next((r for r in (payload.get("routes") or [])
                  if str(r.get("route_id")) == rid), None)
    if route is None:
        return None
    node = next((n for n in (route.get("nodes") or [])
                 if str(n.get("node_id")) == nid), None)
    if node is None:
        return None
    # The composed node drops the template's i18n; look it up by (template_id, resolves) so an
    # English session reads the Move in English without inventing wording.
    en_activity = ""
    try:
        from ontology.route.strategies import active_template_library
        _tid = str(route.get("template_id") or "")
        _res = set(node.get("resolves") or [])
        _tpl = next((t for t in active_template_library()
                     if str(t.get("template_id")) == _tid), None)
        if _tpl and _res:
            _cand = next((c for c in (_tpl.get("node_candidates") or [])
                          if _res <= set(c.get("resolves") or [])), None)
            if _cand:
                en_activity = str((((_cand.get("i18n") or {}).get("en") or {})
                                   .get("activity")) or "").strip()
    except Exception:  # noqa: BLE001 - a missing template only costs the English wording
        en_activity = ""
    design = _mv.design_from_route_node(node=node, route=route,
                                        path_id=str(route.get("path_id") or ""),
                                        lang=str(getattr(s, "language", "") or ""),
                                        activity_en=en_activity)
    if design is None or _mv.design_problems(design):
        return None
    mv = _mv.create_move(s, design=design, text=str(node.get("activity") or ""),
                         event_id=event_id)
    mv["created_by"] = "route_frontier"
    return mv


@app.post("/session/{sid}/next_move")
def next_move_now(sid: str, body: NextMoveBody | None = None):
    """Decide what comes NEXT, through the ONE existing navigation authority.

    This is the event boundary the mandate names for "the next Move requires a light navigation
    decision" (case B): the same `navigate_session` + `decide_next_move` a conversation turn uses, with
    the already-asked counts respected, so the result is either an authorized ACTION (which creates the
    canonical Move WITH its action list) or the authorized QUESTION / EVIDENCE_REQUEST / HOLD.

    It is EXPLICITLY requested by the user and it is LLM-backed: it is never started silently, it never
    creates a checkpoint, and it never invents a Move. A 409 says there is already work to do or a
    result to report - the honest state, not a second decision.
    """
    s = store.get(sid)
    if not s:
        raise HTTPException(404, "session not found")
    if not getattr(s, "diagnosis", None):
        raise HTTPException(409, detail={"code": "NO_DIAGNOSIS",
                                         "message": "There is no map yet to decide from."})
    frontier = _moves_overview(s)["frontier"] or {}
    kind = str(frontier.get("kind") or "")
    if kind == "MOVE_ACTIONABLE":
        raise HTTPException(409, detail={
            "code": "MOVE_ALREADY_ACTIONABLE",
            "message": "There is already a move to work on. Finish it first."})
    if kind == "MOVE_EXECUTED_RESULT_PENDING":
        raise HTTPException(409, detail={
            "code": "RESULT_STILL_PENDING",
            "message": "Report what happened for that move first."})
    with _NEXT_MOVE_LOCKS.setdefault(sid, threading.Lock()):
        moves_before = {m.get("move_id") for m in (getattr(s, "moves", None) or [])}
        llm = get_llm()
        llm.use_session(sid)
        from app.adaptive import decide_next_move as _decide
        from app.navigation import (
            compact_log,
            degraded_navigation,
            log_entry,
            navigate_session,
            update_question_budget,
        )
        _snapshot_experience_before(s, persist=False)
        try:
            nav = navigate_session(s, llm=llm)
        except Exception as exc:  # noqa: BLE001 - a navigation fault is a technical HOLD, not a verdict
            nav = degraded_navigation(s, exc)
        event = {"event_id": _last_user_event_id(s) or f"nm-{s.id}"}
        try:
            nav = _decide(s, llm, nav, event)
        except Exception as exc:  # noqa: BLE001 - reasoning never sinks the request
            _log_reassess_failure(sid, exc)
            raise HTTPException(502, detail={
                "code": "NEXT_MOVE_TECHNICAL_FAILURE",
                "message": ("A technical error stopped the decision. Nothing was committed; your record "
                            "is unchanged. Try again, and share the server log if it repeats.")}) from exc
        from app import moves as _mv
        created = [m for m in (getattr(s, "moves", None) or [])
                   if str(m.get("move_id")) not in moves_before]
        # No Move from the reasoning step? Then take the ALREADY AUTHORIZED route frontier: when the
        # route selector says EXECUTE for a node, that node is the next bounded unit of work and it
        # has a NAME. The Move keeps a typed route_node_ref, so the ownership is explicit and the
        # node's own words become the objective ("Create proposal"), never a generic "next move".
        # Deterministic, 0-LLM, and it bypasses no guard: the design is checked by G10/R1.5 first.
        if not created:
            made = _materialize_frontier_move(s, event_id=event["event_id"])
            if made is not None:
                created = [made]
        turn_no = sum(1 for role, _ in (getattr(s, "transcript", None) or []) if role == "user") or 1
        entry = log_entry(nav, turn_no)
        entry["event_id"] = event["event_id"]
        entry["boundary"] = "NEXT_MOVE_REQUEST"     # distinguishable from a conversation turn
        if created:
            entry["move_created"] = str(created[0].get("move_id") or "")
            entry["move_created_by"] = str(created[0].get("created_by") or "reasoning")
        s.planner_log.append(entry)
        s.planner_log = compact_log(s.planner_log)
        update_question_budget(s, nav)
        s.last_adjudication = nav.adjudication
        try:
            store.save_strict(s)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(503, detail={
                "code": "NEXT_MOVE_NOT_DURABLE",
                "message": "The decision could not be saved. Nothing was committed; please try again."}
            ) from exc
        presented = nav.presented or {}
        overview = _moves_overview(s)
        return {"ok": True, "decision": {"kind": presented.get("kind"),
                                         "headline": presented.get("headline"),
                                         "text": presented.get("text"),
                                         "degraded": bool(presented.get("degraded")),
                                         "error_code": presented.get("error_code")},
                # The move the caller must use: the reasoning step's own Move, or the one
                # materialised from the authorised route frontier (created above).
                "move_id": (str(created[0].get("move_id")) if created else presented.get("move_id")),
                "move": _mv.view(created[0]) if created else None,
                "continuation": _plan_continuation(s),
                "moves": {"current_move_id": overview["current_move_id"],
                          "frontier": overview["frontier"], "total": len(overview["moves"])}}


class RetryReasoningBody(BaseModel):
    """MC01-2: optional event_id — default = the last user event whose understanding was accepted."""

    event_id: str = ""


@app.post("/session/{sid}/retry_reasoning", response_model=InterviewTurn)
def retry_reasoning_endpoint(sid: str, body: RetryReasoningBody | None = None):
    """MC01-2 (audit CIR-MC01 P0-B): REASONING-ONLY recovery for a turn that went DEGRADED.

    The user is NOT asked to resend their story: observations & the already-accepted State are
    reused; only the navigation+reasoning stages run again, bound to the current event/snapshot/
    Goal/State version. 409 when there is no matching failure, understanding is not complete,
    or a newer user message already exists (the conversation continues from there)."""
    s = store.get(sid)
    if not s:
        raise HTTPException(404, "session not found")
    llm = get_llm()
    llm.use_session(sid)
    from app.turn import retry_reasoning as run_retry_reasoning
    try:
        return run_retry_reasoning(s, llm, (body.event_id if body else "") or "")
    except RetryNotApplicableError as e:
        raise HTTPException(409, f"{e.code}: {e}") from e
    except (RateLimitError, AuthenticationError, APITimeoutError) as e:
        raise _llm_http_exc(e)


def _presented_era(s, entry: dict | None) -> int | None:
    """Checkpoint version that was current when a planner_log entry was PRESENTED (0 = before the first
    checkpoint), derived from the checkpoints' recorded source events. None when it cannot be told -
    never guessed."""
    eid = (entry or {}).get("event_id")
    cps = getattr(s, "checkpoints", None) or []
    if not eid or not cps:
        return None
    for cp in cps:                                   # oldest first
        if eid in (cp.get("source_event_ids") or []):
            return int(cp.get("version") or 1) - 1   # presented BEFORE this version existed
    return int(cps[-1].get("version") or 1)          # after every checkpoint was cut


@app.get("/session/{sid}/navigation")
def navigation(sid: str):
    """Conversation inspection: the step CURRENTLY presented to the user (the last recorded decision)
    + reason trail, the applicable requirement set (with their states and origins), the adjudication
    summary, and a REPLAY of that decision (the same input must produce the same decision). No LLM;
    adjudication is idempotent.

    `move` = what is presented; NOT what will be decided next (asking something raises the
    "already asked" counter, so recomputing with the full log would yield the NEXT step). The current
    state is recomputed with the log minus the last entry: if the result matches, `in_sync` is True;
    if the state changed since it was presented, `recomputed` carries the new decision."""
    s = store.get(sid)
    if not s:
        raise HTTPException(404, "session not found")
    from app.navigation import attach_question_budget  # MC-07: include the budget in the summary
    last = s.planner_log[-1] if s.planner_log else None
    nav = navigate_session(s, asked_from=s.planner_log[:-1] if last else None)
    in_sync = last is not None and nav.decision == last["decision"]

    # R5/P1-1: Path affiliation is computed from the recomputed routes, for decisions that point
    # at a ROUTE (EXECUTE / route-applicability), not direct paths — one helper shared with /message.
    def move_of(d: dict, text: dict) -> dict:
        # R5/S4: pass-through of the PRESENTED decision (nm.v2 + guard), not a whitelist that drops
        # degraded/error_code/retry_reasoning/checkpoint/move_id/policy/source. One current-decision
        # reference identical to POST /message; no business status computation here.
        # R5/P1-1: EXPLICIT (nullable) Path affiliation via ONE helper shared with the /message
        # response (path_affiliation) — ambiguous = None, not a silent choice.
        out = {"kind": d["kind"], "intent": d["intent"], "focus": d["focus"], "stop": d["stop"],
               "text": text["text"], "headline": text["headline"], "reason": d["reason"],
               "path_id": path_affiliation(d, nav.routes)}
        for k in ("policy", "degraded", "error_code", "retry_reasoning", "checkpoint",
                  "move_id", "source", "lang"):
            if d.get(k) is not None:
                out[k] = d[k]
        return out

    # Phase 6.2: HISTORY is not CURRENT. `move` above stays what was actually shown (never rewritten, never
    # a fabricated planner event); `current` names the checkpoint the decision belongs to and carries
    # the canonical recomputation, so a post-checkpoint reader is never handed a historical turn as if
    # it were the present recommendation. Read-only: no checkpoint, no synthesis, no log entry here.
    from app import checkpoints as _cp_nav
    cur_cp = _cp_nav.latest(s)
    era = _presented_era(s, last) if last else None
    cur_ver = (cur_cp or {}).get("version")
    historical = bool(last and cur_cp and era is not None and era < cur_ver)
    if not last:
        relation = "NOTHING_PRESENTED"
    elif in_sync:
        relation = "SAME_AS_PRESENTED"
    else:
        relation = "CHANGED_SINCE_PRESENTED"
    # AUTHORITY, stated explicitly (Phase 6.2.1). Three different things must never be conflated:
    #   PRESENTED  - a decision the person was actually shown, produced by the authorized turn boundary
    #                (reasoning + guard). Only this is an authorized decision.
    #   CANDIDATE  - the deterministic planner's read of the current state. Computed here with the log
    #                MINUS the last entry, i.e. it REPLAYS the state the last turn saw; it is NOT the next
    #                step, and nothing on a GET may promote it to one.
    #   NEXT       - the next authorized decision. It exists only after the next turn (POST /message),
    #                which is the single place that applies the reasoning, the guard and the question budget.
    authorized = bool(last and cur_cp and not historical)
    candidate = move_of(nav.decision, nav.rendered)
    current = {
        "checkpoint_id": (cur_cp or {}).get("checkpoint_id"),
        "checkpoint_version": cur_ver,
        "binding_id": ((cur_cp or {}).get("binding") or {}).get("binding_id"),
        "presented_checkpoint_version": era,
        "presented_is_historical": historical,
        "relation": relation,
        "status": "PRESENTED_CURRENT" if authorized else "AWAITING_PRESENTATION",
        "move_authority": "PRESENTED" if authorized else "CANDIDATE",
        "candidate_basis": ("REPLAY_OF_PRESENTED_STATE" if in_sync and last
                            else "RECOMPUTED_FROM_CURRENT_STATE"),
        "next_decision_requires": None if authorized else "TURN",
        "presented": move_of(last.get("presented") or last["decision"], last["text"]) if last else None,
        "candidate": candidate,
        # compatibility: `move` is the authorized decision when there is one, otherwise the candidate -
        # consumers must read `move_authority` before describing it as presented.
        "move": (move_of(last.get("presented") or last["decision"], last["text"]) if authorized
                 else candidate),
    }

    return {
        "session_id": s.id,
        "current": current,
        # R5: what is PRESENTED (validated reasoning / degraded); `decision` = candidate+guard
        "move": move_of(last.get("presented") or last["decision"], last["text"]) if last
        else move_of(nav.decision, nav.rendered),
        "adaptive": (last or {}).get("adaptive"),
        "reality": _reality(s),
        "hypotheses": list((getattr(s, "hypotheses", None) or {}).values()),
        "in_sync": bool(in_sync) if last else True,
        "recomputed": None if (in_sync or not last) else move_of(nav.decision, nav.rendered),
        "applicable": nav.applicable.to_dict(),
        "requirements": {rid: v.to_dict() for rid, v in nav.views.items()},
        "readiness": nav.readiness,
        "summary": attach_question_budget(nav.summary(), s),
        "asked": asked_counts(s.planner_log),
        # steps presented so far (compact): the UI restores the step kind label on old messages
        "history": [
            {"turn": e["turn"], "kind": (e.get("presented") or e["decision"])["kind"],
             "intent": (e.get("presented") or e["decision"])["intent"],
             "headline": e["text"]["headline"], "text": e["text"]["text"]}
            for e in s.planner_log
        ],
        "last_logged": (
            # kind = the PRESENTED step, consistent with move; not the deterministic candidate.
            {"turn": last["turn"], "kind": (last.get("presented") or last["decision"])["kind"],
             "replay": replay_logged(last)["ok"]}
            if last else None
        ),
    }


@app.get("/session/{sid}/checkpoints")
def list_checkpoints(sid: str):
    """Versioned checkpoints (R6). Old ones are never mutated; status: current | stale | superseded."""
    s = store.get(sid)
    if not s:
        raise HTTPException(404, "session not found")
    from app import checkpoints as _cp
    return {"session_id": s.id, "latest": _cp.summary(_cp.latest(s)),
            "checkpoints": [{**_cp.summary(c), "binding": c.get("binding")} for c in (s.checkpoints or [])]}


# ── Reassessment: authoritative eligibility, operation identity, ONE commit boundary ──────────
# Phase 6.1 (NC-R1..NC-R4). A reassessment is an EXPENSIVE, explicitly confirmed mutation. The preview
# is a READ, never a lock. These helpers are the ONE authority for "may this map be reassessed right
# now", shared by GET /reevaluate-preview and POST /reassess, so no client derives eligibility itself.
_REASSESS_LOCKS: dict[str, threading.Lock] = {}
_REASSESS_INFLIGHT: set[str] = set()
# Diagnostics (Phase 6.1 hotfix): an unexpected reassessment failure used to leave only a bare 500
# "Internal Server Error" on the server terminal, with nothing left to diagnose afterwards. The
# traceback is appended here (inside the gitignored traces/ directory) so a technical failure can be
# explained and fixed without a live terminal.
_REASSESS_ERROR_LOG = Path(__file__).resolve().parent.parent / "traces" / "reassess_errors.log"


def _log_reassess_failure(sid: str, exc: BaseException) -> None:
    """Append one reassessment traceback to the diagnostics log. Never raises."""
    try:
        import traceback as _tb
        _REASSESS_ERROR_LOG.parent.mkdir(parents=True, exist_ok=True)
        with _REASSESS_ERROR_LOG.open("a", encoding="utf-8") as fh:
            fh.write("\n===== %s session=%s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), sid))
            fh.write("".join(_tb.format_exception(type(exc), exc, exc.__traceback__)))
    except Exception:  # noqa: BLE001 — logging must never mask the original failure
        pass
    try:
        logging.getLogger("novaliners.reassess").error("reassessment failed for %s: %r", sid, exc)
    except Exception:  # noqa: BLE001
        pass


_REASSESS_BLOCK_TEXT = {
    "NO_DIAGNOSIS": "There is no accepted assessment to build on yet.",
    "NO_CHECKPOINT": "No checkpoint has been committed for this map yet.",
    "NO_MATERIAL_CHANGE": "Nothing material has changed since your last checkpoint.",
    "REASSESSMENT_IN_PROGRESS": "A reassessment for this map is already running.",
    "PROVIDER_UNAVAILABLE": ("The reasoning provider is not available right now. "
                             "This is a technical condition, not a result about your business."),
}
_REASSESS_REASON_TEXT = {
    "NEW_EVIDENCE": "new facts since your last checkpoint",
    "SUPERSEDED_CLAIMS": "earlier claims that were corrected",
    "GOAL_REVISED": "a new Goal version",
    "KNOWLEDGE_UPDATED": "an updated knowledge base",
    "NEW_OBSERVATION": "outcomes or check-ins on record since your last checkpoint",
    "METHOD_UPDATED": "an updated reasoning method",
}


def _provider_ready() -> bool:
    """Whether the ACTIVE reasoning provider can be resolved at all.

    It asks the SAME authority the synthesis uses (get_llm: provider selection, .env reload and key
    guard live in llm/runtime.py) instead of duplicating that logic here. After the first successful
    call the provider is cached per process, so a preview read stays cheap. A false value is a
    TECHNICAL condition and is always reported as one — never as a business STOP / NOT YET (§13)."""
    try:
        get_llm()
        return True
    except Exception:  # noqa: BLE001 — an unresolvable provider means "not ready", not a crash
        return False


def _reassess_facts(s) -> dict:
    """Deterministic, 0-LLM facts behind a reassessment: what changed since the last committed
    checkpoint, and against which revision. Extracted so POST rechecks the SAME facts the preview
    showed (NC-R2) instead of growing a second decision engine. This function writes nothing."""
    from app import checkpoints as _cp
    from app import experience_contract as _ec
    from app.binding import knowledge_versions, prompt_versions

    cp = _cp.latest(s)
    binding = (cp or {}).get("binding") or {}
    routes, maps_projection, degraded = _experience_routes(s)
    graph = _ec.build_graph(s, maps_projection)
    revision = _ec.reality_revision(s, routes=routes, graph=graph)

    cur_evidence = {getattr(e, "id", None) for e in (s.evidence or []) if not getattr(e, "superseded", False)}
    cur_superseded = {getattr(e, "id", "") for e in (s.evidence or []) if getattr(e, "superseded", False)}
    cur_superseded.discard("")
    if cp:
        cp_evidence = set(binding.get("source_evidence_refs") or [])
        added_evidence = sorted(x for x in (cur_evidence - cp_evidence) if x)
        # H1 (Phase 6.1 hotfix): only supersessions NEW since this checkpoint are material. The old
        # reading listed EVERY superseded claim, which stays non-empty forever, so after a successful
        # re-evaluation the map kept offering v3, v4, ... with nothing new to re-evaluate.
        # A checkpoint created before the binding carried the snapshot cannot tell which supersessions
        # it already absorbed, so it falls back to the CONSERVATIVE reading: it may offer one more
        # re-evaluation, but it never claims "nothing changed" that it cannot prove.
        if "superseded_evidence_refs" in binding:
            absorbed = set(binding.get("superseded_evidence_refs") or [])
            superseded = sorted(cur_superseded - absorbed)
        else:
            superseded = sorted(cur_superseded)
    else:
        added_evidence, superseded = [], []
    goal = s.goal or {}
    goal_changed = bool(cp) and binding.get("goal_version") != goal.get("version")
    knowledge_changed = bool(cp) and binding.get("knowledge") != knowledge_versions()
    prompts_changed = bool(cp) and binding.get("prompts") != prompt_versions()
    executed = [m.get("move_id") for m in (s.moves or []) if m.get("executed_ts")]
    assessed = [m.get("move_id") for m in (s.moves or []) if (m.get("assessment") or {}).get("verdict")]
    # NC-06: an accepted OBSERVATION since the checkpoint (a reported action outcome, a durable
    # check-in, or a Move observation/verdict) can be material to navigation. The binding stamped
    # its digest at checkpoint time; mere execution/status does NOT enter observation_revision, so a
    # checked box never qualifies a reassessment on its own. Old checkpoints without the digest
    # (None) stay honest: no change is claimed.
    cur_obs = _ec.observation_revision(s)
    if bool(cp) and binding.get("observation_fingerprint") is not None:
        # Phase 6.2.1: checkpoints that carry the content-complete digest are compared with it
        observation_changed = binding.get("observation_fingerprint") != _ec.observation_fingerprint(s)
    else:   # older checkpoint: the original digest, exactly as before
        observation_changed = (bool(cp) and binding.get("observation_revision") is not None
                               and binding.get("observation_revision") != cur_obs)

    material = bool(added_evidence or superseded or goal_changed or knowledge_changed or observation_changed)
    return {
        "session_id": s.id,
        "checkpoint": _cp.summary(cp),
        "current_revision": revision,
        "current_projection_revision": revision.get("projection_revision"),
        "mutating": False,
        "basis": {
            "evidence_added_since_checkpoint": added_evidence,
            "evidence_superseded": superseded,
            # H1: the total on record, so an explanation can name it without claiming it is new
            "evidence_superseded_total": len(cur_superseded),
            "goal_changed": goal_changed,
            "knowledge_changed": knowledge_changed,
            "prompts_changed": prompts_changed,
            "executed_moves": executed,
            "assessed_moves": assessed,
            "observation_changed": observation_changed,
        },
        "material_change": material,
        "would_supersede_checkpoint": bool(cp),
        "next_checkpoint_version": ((cp or {}).get("version") or 0) + 1 if cp else 1,
        "note": ("Preview only: nothing was written, no route was born and no synthesis ran. "
                 "Committing a re-evaluation is a separate, explicit user action."),
        "degraded_sources": degraded,
        # Phase 6.2.1: accepted reports whose derived effects are not confirmed yet (read-only count)
        "pending_report_effects": len(_pending_report_effects(s)),
        "plan": _cp.plan_record(s),
    }


def _reassess_eligibility(s, facts: dict) -> dict:
    """Authoritative eligibility (NC-R2). material_change is NOT permission to mutate: the
    checkpoint, the session record, the provider and a concurrent request are part of the decision,
    and POST /reassess rechecks all of them. Codes only; the wording lives next to them so no caller
    invents a business reason."""
    blocked: list[str] = []
    if getattr(s, "diagnosis", None) is None:
        blocked.append("NO_DIAGNOSIS")
    if not facts.get("checkpoint"):
        blocked.append("NO_CHECKPOINT")
    if not facts.get("material_change"):
        blocked.append("NO_MATERIAL_CHANGE")
    if getattr(s, "id", "") in _REASSESS_INFLIGHT:
        blocked.append("REASSESSMENT_IN_PROGRESS")
    if not _provider_ready():
        blocked.append("PROVIDER_UNAVAILABLE")
    reasons: list[str] = []
    b = facts.get("basis") or {}
    if b.get("evidence_added_since_checkpoint"):
        reasons.append("NEW_EVIDENCE")
    if b.get("evidence_superseded"):
        reasons.append("SUPERSEDED_CLAIMS")
    if b.get("goal_changed"):
        reasons.append("GOAL_REVISED")
    if b.get("knowledge_changed"):
        reasons.append("KNOWLEDGE_UPDATED")
    if b.get("observation_changed"):
        reasons.append("NEW_OBSERVATION")
    if b.get("prompts_changed"):
        reasons.append("METHOD_UPDATED")
    cp = facts.get("checkpoint") or {}
    return {
        "eligible": not blocked,
        "material_change": bool(facts.get("material_change")),
        "reasons": reasons,
        "reason_details": [_REASSESS_REASON_TEXT[r] for r in reasons if r in _REASSESS_REASON_TEXT],
        "blocked_reasons": blocked,
        "blocked_details": [_REASSESS_BLOCK_TEXT[c] for c in blocked if c in _REASSESS_BLOCK_TEXT],
        "current_checkpoint_id": cp.get("checkpoint_id"),
        "current_checkpoint_version": cp.get("version"),
        "current_projection_revision": facts.get("current_projection_revision"),
        "next_checkpoint_version": facts.get("next_checkpoint_version"),
    }


def _reassess_preview(s) -> dict:
    """The facts + the authoritative eligibility, in one payload. Used by GET and by the POST guard."""
    facts = _reassess_facts(s)
    elig = _reassess_eligibility(s, facts)
    facts["eligibility"] = elig
    facts["eligible"] = elig["eligible"]
    facts["reasons"] = elig["reasons"]
    facts["blocked_reasons"] = elig["blocked_reasons"]
    return facts


class ReassessRequest(BaseModel):
    """Explicitly confirmed reassessment (Phase 6.1 NC-R1/NC-R2/NC-R4).

    Every field is optional, so an existing caller that POSTs without a body keeps working. A
    CONFIRMED call (expected_checkpoint_id / expected_projection_revision present) is additionally
    guarded by the authoritative eligibility recheck and by the revision the user actually approved.
    """
    operation_id: str = Field(
        default="", description="D-10 client operation key; a resend replays the accepted checkpoint")
    expected_checkpoint_id: str = Field(
        default="", description="Checkpoint the user approved in the preview")
    expected_projection_revision: str = Field(
        default="", description="Revision the user approved in the preview")


@app.post("/session/{sid}/reassess")
def reassess(sid: str, body: ReassessRequest | None = None):
    """Reassess = re-synthesize over the CURRENT state → a new checkpoint. Expensive (LLM).

    Guarantees since Phase 6.1:
      * OPERATION IDENTITY (NC-R4): the same operation_id returns the checkpoint it already produced,
        so a double-click, a re-render or a retry after an ambiguous timeout cannot buy a second
        synthesis or append a second checkpoint;
      * ONE AT A TIME: a per-session lock refuses a concurrent reassessment with 409 instead of
        racing two syntheses into the same session;
      * CONFIRMED CALLS are re-checked: the authoritative eligibility and the approved revision are
        re-read at POST time, and a change is a 409 conflict carrying the FRESH preview (the preview
        was a read, not a lock);
      * DURABILITY: the checkpoint is persisted strictly. If it cannot be made durable, the in-memory
        effect is rolled back and the caller gets 503 — an accepted checkpoint is never reported as
        durable when it is not.
    """
    s = store.get(sid)
    if not s:
        raise HTTPException(404, "session not found")
    op = (body.operation_id or "").strip() if body else ""
    expected_cp = (body.expected_checkpoint_id or "").strip() if body else ""
    expected_rev = (body.expected_projection_revision or "").strip() if body else ""
    confirmed = bool(expected_cp or expected_rev)
    from app import checkpoints as _cp

    def _accepted(cp: dict | None, *, replayed: bool) -> dict:
        # Phase 6.2: a checkpoint is NOT a new Move. The response carries the canonical CURRENT
        # navigation outcome (deterministic, no LLM, nothing written) so the caller can say what
        # actually remains - an action, a question, an evidence request, a hold, or nothing.
        nav_after = None
        try:
            _n = navigate_session(s, asked_from=(s.planner_log[:-1] if s.planner_log else None))
            nav_after = {"kind": _n.decision.get("kind"), "intent": _n.decision.get("intent"),
                         "focus": _n.decision.get("focus"), "headline": (_n.rendered or {}).get("headline"),
                         "status": "CANDIDATE_NOT_AUTHORIZED"}
        except Exception:  # noqa: BLE001 - the commit stands even when this read cannot be composed
            nav_after = None
        return {"session_id": s.id, "ok": True, "committed": True, "replayed": replayed,
                "checkpoint": _cp.summary(cp), "previous_checkpoint": _cp.summary(_cp.previous_to(s, cp)),
                "plan": _cp.plan_record(s), "navigation": nav_after}

    if op:
        prior = _cp.find_by_operation(s, op)
        if prior is not None:
            return _accepted(prior, replayed=True)

    lock = _REASSESS_LOCKS.setdefault(sid, threading.Lock())
    if not lock.acquire(blocking=False):
        raise HTTPException(409, detail={"code": "REASSESSMENT_IN_PROGRESS",
                                        "message": _REASSESS_BLOCK_TEXT["REASSESSMENT_IN_PROGRESS"]})
    # Phase 6.2.1: a reassessment must not read path states / outcome logs that an accepted report has
    # not finished writing. Settle what can be settled; refuse (retryable) if something still cannot.
    try:
        if _reconcile_pending_report_effects(s, sid):
            lock.release()
            raise HTTPException(409, detail={
                "code": "REPORT_EFFECTS_PENDING",
                "message": ("A result you reported is still being recorded. Nothing was lost; try the "
                            "re-evaluation again in a moment.")})
    except HTTPException:
        raise
    import copy as _copy
    # H2 (hotfix): every SESSION field this request can touch is captured, so the rollback is complete
    # for the session object (experience_snapshots included: the pre-mutation baseline is appended here).
    # Phase 6.2: the LIVE artifact object (not a deep copy) is what a rollback restores. _diagnose
    # replaces s.diagnosis instead of editing it in place, and an action report accepted while the
    # model was thinking mutates this same object - restoring a copy would silently drop that report.
    before = {"diagnosis": getattr(s, "diagnosis", None),
              "checkpoints": _copy.deepcopy(getattr(s, "checkpoints", None)),
              "explain": _copy.deepcopy(getattr(s, "explain", None)),
              "journey_delta": _copy.deepcopy(getattr(s, "journey_delta", None)),
              "experience_snapshots": _copy.deepcopy(getattr(s, "experience_snapshots", None)),
              "interview_done": getattr(s, "interview_done", False)}
    try:
        if op:   # double-checked under the lock: a parallel confirmed call may have just finished
            prior = _cp.find_by_operation(s, op)
            if prior is not None:
                return _accepted(prior, replayed=True)
        if confirmed:
            # Eligibility is evaluated BEFORE this request joins _REASSESS_INFLIGHT, so the caller is
            # not blocked by its own in-flight marker.
            facts = _reassess_preview(s)
            cur_id = (facts.get("checkpoint") or {}).get("checkpoint_id") or ""
            if expected_cp and expected_cp != cur_id:
                raise HTTPException(409, detail={
                    "code": "CHECKPOINT_CHANGED",
                    "message": ("Your record changed while you were confirming. "
                                "Review the current preview before reassessing."),
                    "preview": facts})
            if expected_rev and expected_rev != (facts.get("current_projection_revision") or ""):
                raise HTTPException(409, detail={
                    "code": "REVISION_CHANGED",
                    "message": ("Your record changed while you were confirming. "
                                "Review the current preview before reassessing."),
                    "preview": facts})
            elig = facts["eligibility"]
            if not elig["eligible"]:
                # A missing provider is a TECHNICAL condition, not a guard about the business: it is
                # reported as a 503 so the UI can never render it as STOP / NOT YET (Phase 6.1 §13-F).
                if elig["blocked_reasons"] == ["PROVIDER_UNAVAILABLE"]:
                    raise HTTPException(503, detail={
                        "code": "PROVIDER_UNAVAILABLE",
                        "message": _REASSESS_BLOCK_TEXT["PROVIDER_UNAVAILABLE"]})
                raise HTTPException(409, detail={
                    "code": "NOT_ELIGIBLE",
                    "message": (" ".join(elig["blocked_details"])
                                or "A reassessment is not available for this map right now."),
                    "eligibility": elig, "preview": facts})
        elif not _provider_ready():
            raise HTTPException(503, detail={"code": "PROVIDER_UNAVAILABLE",
                                            "message": _REASSESS_BLOCK_TEXT["PROVIDER_UNAVAILABLE"]})
        _REASSESS_INFLIGHT.add(sid)
        _snapshot_experience_before(s, persist=False)   # P1-06: _diagnose saves on success
        s.interview_done = True
        try:
            # H2 (hotfix): persist=False - the ONLY write of this reassessment is the strict save below,
            # so "not durable" and "not committed" can never disagree between disk and memory.
            _diagnose(s, operation_id=op, persist=False)
        except BasisChangedDuringSynthesis as exc:
            # Phase 6.2: nothing was swapped in. We deliberately restore NOTHING from the pre-synthesis
            # copies - a report accepted while the model was thinking lives on the live artifact and
            # must not be rolled back with it. The user re-reviews a fresh preview, then confirms again.
            s.interview_done = before["interview_done"]
            raise HTTPException(409, detail={
                "code": "BASIS_CHANGED_DURING_REASSESSMENT",
                "message": ("Your record changed while the re-evaluation was running, so its result was "
                            "not saved. Your previous checkpoint and everything you reported are intact; "
                            "review the current preview and confirm again."),
                "drift": exc.drift, "preview": _reassess_preview(s)}) from exc
        except Exception:
            # P1-06: a FAILED synthesis must not leave an advanced-looking session behind (the previous
            # code kept interview_done=True even though nothing was committed).
            for _k, _v in before.items():
                setattr(s, _k, _v)
            raise
        try:
            store.save_strict(s)     # NC-R4: an accepted checkpoint must be durable, not RAM-only
        except Exception as exc:  # noqa: BLE001
            for _k, _v in before.items():
                setattr(s, _k, _v)
            raise HTTPException(503, detail={
                "code": "CHECKPOINT_NOT_DURABLE",
                "message": ("The new assessment could not be saved. Nothing was committed and your "
                            "previous checkpoint is unchanged; try again.")}) from exc
        # Derived records (workspace snapshot, funnel row) describe a checkpoint that IS durable, so
        # they are written only now. They are best-effort and can never fail an accepted commit.
        _record_post_diagnosis_side_effects(s, s.diagnosis)
        return _accepted(_cp.latest(s), replayed=False)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        # A technical failure is reported AS a technical failure: a machine code the UI can render,
        # the honest statement that nothing was committed, and a logged traceback. It is never told
        # as a business verdict about the person's plan.
        _log_reassess_failure(sid, exc)
        raise HTTPException(502, detail={
            "code": "REASSESSMENT_TECHNICAL_FAILURE",
            "message": ("A technical error stopped the re-evaluation. This is not a result about your "
                        "business. Nothing was committed and your previous checkpoint is unchanged; "
                        "try again, and share the server log if it repeats.")}) from exc
    finally:
        _REASSESS_INFLIGHT.discard(sid)
        lock.release()


def _record_move_execution_on_route(s, mv: dict, event: str) -> None:
    """Mirror a Move's lifecycle event onto its route-node ledger.

    A Move created FROM a route frontier node IS that node's canonical execution (it carries a typed
    `route_node_ref`). Recording the event on the route ledger is what advances the frontier from
    EXECUTE to VERIFY, so the selector does not hand the SAME node back as the next move. The Move stays
    the authority: a ledger fault is swallowed and never undoes an accepted Move event."""
    ref = (mv or {}).get("route_node_ref") or {}
    rid = str(ref.get("route_id") or "")
    nid = str(ref.get("node_id") or "")
    uid = str(getattr(s, "user_id", "") or "")
    if not (rid and nid and uid) or event not in ("EXECUTED", "ABANDONED", "RESET"):
        return
    try:
        from store import route_execution
        route_execution.record(uid, rid, nid, event, session_id=str(getattr(s, "id", "") or ""),
                               op_id=f"move:{mv.get('move_id')}:{event}")
    except Exception:  # noqa: BLE001
        pass


def _moves_overview(s) -> dict:
    """The canonical Move read model: every Move (with its action list), the ONE move the person is
    working on, and the honest frontier when there is nothing to execute.

    Read-only and deterministic. The frontier never invents a Move: when no executable work is
    authorized it names the real missing condition (a question, evidence, a hold, or a decision that
    has not been taken yet)."""
    from app import moves as _moves
    rows = _moves.moves_view(s)
    # The FIRST still-open Move is the one being worked on: earlier authorized work is not skipped
    # because a newer Move was proposed while it was still open.
    cur = next((m for m in rows if m["lifecycle"] in (_moves.PLANNED, _moves.STARTED)), None)
    if cur is None:
        pending = [m for m in rows if m["lifecycle"] == _moves.EXECUTED
                   and not (m.get("outcome_report") or {}).get("outcome")]
        cur = pending[-1] if pending else None
    if cur is None and rows:
        cur = rows[-1]
    frontier: dict = {"kind": "NO_MOVE_AUTHORIZED", "move_id": None}
    if cur is not None:
        life = cur["lifecycle"]
        if life in (_moves.PLANNED, _moves.STARTED):
            frontier = {"kind": "MOVE_ACTIONABLE", "move_id": cur["move_id"],
                        "actions_open": cur["progress"]["open"],
                        "actions_total": cur["progress"]["total"],
                        # A Move authorized before action lists existed carries no checklist: it is
                        # still real work, and the screen says so instead of inventing rows.
                        "actionless": cur["progress"]["total"] == 0}
        elif life == _moves.EXECUTED and not (cur.get("outcome_report") or {}).get("outcome"):
            frontier = {"kind": "MOVE_EXECUTED_RESULT_PENDING", "move_id": cur["move_id"]}
        elif life in (_moves.OBSERVED, _moves.VALIDATED, _moves.INCONCLUSIVE, _moves.UNSUPPORTED,
                      _moves.ABANDONED):
            frontier = {"kind": "NEXT_MOVE_PENDING", "move_id": None,
                        "last_move_id": cur["move_id"]}
    if frontier["kind"] == "NO_MOVE_AUTHORIZED":
        last = (getattr(s, "planner_log", None) or [None])[-1] or {}
        pres = last.get("presented") or last.get("decision") or {}
        kind = str(pres.get("kind") or "")
        if kind in ("QUESTION", "EVIDENCE_REQUEST", "HOLD"):
            frontier = {"kind": "NAVIGATION_" + kind, "move_id": None,
                        "headline": (last.get("text") or {}).get("headline") or ""}
    return {"moves": rows, "current_move_id": (cur or {}).get("move_id"), "frontier": frontier}


@app.get("/session/{sid}/moves")
def list_moves(sid: str):
    """Moves as measured experiments (R6-D), each with its canonical ACTION LIST. Execution ≠ success."""
    s = store.get(sid)
    if not s:
        raise HTTPException(404, "session not found")
    overview = _moves_overview(s)
    return {"session_id": s.id, **overview,
            "hypotheses": list((s.hypotheses or {}).values()), "reality": _reality(s)}


class MoveEvent(BaseModel):
    event: Literal["STARTED", "EXECUTED", "ABANDONED"]
    note: str = ""
    # D-10 (V4, 18 Oct 2026): client operation key. Resending after a timeout with the SAME key
    # returns the already-recorded event (replay), not a double effect; the same key with a
    # different payload = a deterministic conflict. The UI may show "pending", not optimistic success.
    operation_id: str = ""


def _move_event_identity(ev: dict) -> tuple[str, str, str]:
    """(move_id, event, note) parsed from the canonical text 'move <id> <STATE>[: note]'.

    P1-01: replay equality is decided on the TYPED identity, not on text.endswith(event) — a
    non-empty note made the old check reject a legitimate replay."""
    text = str(ev.get("text") or "")
    head, _, note = text.partition(":")
    toks = head.split()
    mid = toks[1] if len(toks) >= 3 and toks[0] == "move" else ""
    state = toks[2].upper() if len(toks) >= 3 and toks[0] == "move" else ""
    return (str(ev.get("correlation_id") or mid), state, note.strip())


@app.post("/session/{sid}/moves/{move_id}/events")
def move_event(sid: str, move_id: str, body: MoveEvent):
    """Report a Move event (STARTED/EXECUTED/ABANDONED). Does not change satisfaction and does NOT claim
    success: verdicts only via outcome observation (a message with move_id) + guard G11.

    Idempotent per operation_id (D-10): double-click / network retry does not duplicate the event."""
    s = store.get(sid)
    if not s:
        raise HTTPException(404, "session not found")
    import copy

    from app import moves as _moves
    from store import events as event_store
    op = (body.operation_id or "").strip()
    if op:
        prior = event_store.find_by_idempotency_key(s, op)
        if prior is not None:
            pid, pevent, pnote = _move_event_identity(prior)
            same = (pid == move_id and pevent == body.event.upper()
                    and pnote == (body.note or "").strip())
            if not same:
                raise HTTPException(409, f"operation_id {op!r} dipakai ulang dengan payload berbeda")
            return {"ok": True, "replayed": True, "move": _moves.get_move(s, move_id),
                    "event_id": prior.get("event_id")}
    try:
        _moves.check_transition(s, move_id, body.event)   # 409 without writing an event
    except _moves.MoveError as e:
        raise HTTPException(409, str(e)) from e
    # P0-03/P1-06: snapshot only AFTER validation, and commit it with the accepted event (the strict
    # save below persists it) — a rejected transition never advances the baseline.
    _snapshot_experience_before(s, persist=False)
    # S2-E (int 16): a Move event = a durable fact. The event is written FIRST (EC-01), the snapshot
    # saved STRICTLY (failure = 503, not a fake 200), and the transition rolled back when saving fails
    # so a retry does not see a double effect.
    try:
        ev = event_store.append_event(
            s, role="user", kind=event_store.KIND_MOVE_EVENT,
            text=f"move {move_id} {body.event}" + (f": {body.note}" if body.note else ""),
            correlation_id=move_id, idempotency_key=op)
    except event_store.EventPersistenceError as e:
        raise HTTPException(503, f"kejadian Move belum tahan-lama, coba lagi: {e}") from e
    before = copy.deepcopy(_moves.get_move(s, move_id))
    mv_ = _moves.transition(s, move_id, body.event, event_id=ev["event_id"], note=body.note)
    _record_move_execution_on_route(s, mv_, body.event)
    try:
        store.save_strict(s)
    except event_store.SessionPersistenceError:
        idx = next(i for i, m in enumerate(s.moves) if m["move_id"] == move_id)
        s.moves[idx] = before   # roll back the in-memory effect; event marked failed
        event_store.mark_event_status(s, ev["event_id"], event_store.STATUS_PERSIST_FAILED,
                                      note="snapshot sesi gagal disimpan setelah transisi Move")
        raise HTTPException(503, "kejadian Move belum tersimpan, coba lagi") from None
    event_store.mark_event_status(s, ev["event_id"], event_store.STATUS_COMMITTED)
    store.save(s)
    return {"ok": True, "move": mv_, "event_id": ev["event_id"]}


class MoveActionEvent(BaseModel):
    """ONE execution event for ONE action of ONE canonical Move.

    Phase 7: this is the ONLY live execution record for Move work. DONE, SKIPPED and BLOCKED stay three
    different facts (a skip is never a done), and a retry of the same operation_id replays the accepted
    event instead of appending a second one."""
    event: Literal["TODO", "DONE", "SKIPPED", "BLOCKED"]
    note: str = ""
    operation_id: str = ""


def _move_action_event_identity(ev: dict) -> tuple[str, str, str, str]:
    """(move_id, action_id, event, note) parsed from the canonical text
    'move <move_id> action <action_id> <STATE>[: note]'. Replay equality is decided on this typed
    identity, never on the text alone."""
    text = str(ev.get("text") or "")
    head, _, note = text.partition(":")
    toks = head.split()
    if len(toks) >= 5 and toks[0] == "move" and toks[2] == "action":
        return (toks[1], toks[3], toks[4].upper(), note.strip())
    return (str(ev.get("correlation_id") or ""), "", "", note.strip())


@app.post("/session/{sid}/moves/{move_id}/actions/{action_id}/events")
def move_action_event(sid: str, move_id: str, action_id: str, body: MoveActionEvent):
    """Record ONE action of a canonical Move (DONE/SKIPPED/BLOCKED/TODO).

    The server owns the transition: when every REQUIRED action is genuinely DONE the SAME Move advances
    to EXECUTED in this request (idempotent), so Maps/Moves/Journey read one already-accepted lifecycle.
    Nothing here reports a result: execution is a fact, an outcome is a separate report."""
    s = store.get(sid)
    if not s:
        raise HTTPException(404, "session not found")
    import copy

    from app import moves as _moves
    from store import events as event_store
    mv = _moves.get_move(s, move_id)
    if mv is None:
        raise HTTPException(404, detail={"code": "MOVE_NOT_FOUND",
                                         "message": "That move is not on this session."})
    action = _moves.get_action(mv, action_id)
    if action is None:
        raise HTTPException(404, detail={"code": "MOVE_ACTION_NOT_FOUND",
                                         "message": "That action is not part of this move."})
    op = (body.operation_id or "").strip()
    if op:
        prior = event_store.find_by_idempotency_key(s, op)
        if prior is not None:
            same = (_move_action_event_identity(prior) ==
                    (move_id, action_id, body.event.upper(), (body.note or "").strip()))
            if not same:
                raise HTTPException(409, f"operation_id {op!r} dipakai ulang dengan payload berbeda")
            return {"ok": True, "replayed": True, "move": _moves.view(mv),
                    "action": _moves._action_view(action), "event_id": prior.get("event_id")}
    # 409 WITHOUT writing an event: the guard returns its problems, so nothing is committed on a
    # rejected action (dependency not done, list already history, unknown status).
    if problems := _moves.action_event_problems(s, mv, action, body.event):
        raise HTTPException(409, detail={"code": "MOVE_ACTION_REJECTED", "message": problems[0]})
    # Snapshot only AFTER validation, committed with the accepted event (a rejected event never moves
    # the baseline the change_set diffs against).
    _snapshot_experience_before(s, persist=False)
    try:
        ev = event_store.append_event(
            s, role="user", kind=event_store.KIND_MOVE_EVENT,
            text=f"move {move_id} action {action_id} {body.event}"
                 + (f": {body.note}" if body.note else ""),
            correlation_id=move_id, idempotency_key=op)
    except event_store.EventPersistenceError as e:
        raise HTTPException(503, f"kejadian aksi belum tahan-lama, coba lagi: {e}") from e
    before = copy.deepcopy(_moves.get_move(s, move_id))
    res = _moves.apply_action_event(s, move_id, action_id, body.event,
                                    event_id=ev["event_id"], note=body.note)
    if res.get("move_executed"):
        # the Move became EXECUTED here, so the route node it came from is executed too (frontier
        # advances EXECUTE -> VERIFY instead of offering the same work again)
        _record_move_execution_on_route(s, res["move"], "EXECUTED")
    try:
        store.save_strict(s)
    except event_store.SessionPersistenceError:
        idx = next(i for i, m in enumerate(s.moves) if m["move_id"] == move_id)
        s.moves[idx] = before
        event_store.mark_event_status(s, ev["event_id"], event_store.STATUS_PERSIST_FAILED,
                                      note="snapshot sesi gagal disimpan setelah eksekusi aksi")
        raise HTTPException(503, "kejadian aksi belum tersimpan, coba lagi") from None
    event_store.mark_event_status(s, ev["event_id"], event_store.STATUS_COMMITTED)
    store.save(s)
    return {"ok": True, "move": _moves.view(res["move"]),
            "action": _moves._action_view(res["action"]), "progress": res["progress"],
            "move_executed": bool(res["move_executed"]),
            "lifecycle": res["move"].get("lifecycle"), "event_id": ev["event_id"]}


class MoveOutcomeReport(BaseModel):
    """What happened as a RESULT of the move's work. Separate from execution: reporting a result never
    changes an action's status, and never turns the move into a verdict."""
    outcome: Literal["moved", "not_moved", "regret", "confounded"] | None = None
    note: str | None = None        # None = omitted; "" alongside an outcome = deliberately emptied
    path: str = ""
    operation_id: str = ""


@app.post("/session/{sid}/moves/{move_id}/outcome")
def move_outcome(sid: str, move_id: str, body: MoveOutcomeReport):
    """Record ONE result for the Move as a whole (the primary outcome interaction).

    The report is attached to the canonical move_id — no arbitrary action has to own the overall
    result. Same durability discipline as every other accepted mutation: the event is written first,
    the snapshot is saved strictly, and a retry with the same operation_id replays instead of
    duplicating."""
    s = store.get(sid)
    if not s:
        raise HTTPException(404, "session not found")
    import copy

    from app import moves as _moves
    from store import events as event_store
    mv = _moves.get_move(s, move_id)
    if mv is None:
        raise HTTPException(404, detail={"code": "MOVE_NOT_FOUND",
                                         "message": "That move is not on this session."})
    note = body.note
    if body.outcome is None and not (note or "").strip():
        raise HTTPException(422, "an outcome or a note is required")
    if body.outcome is not None and body.path:
        _require_known_path(s, body.path)
    op = (body.operation_id or "").strip()
    sig = "|".join([str(body.outcome or ""), str(note if note is not None else ""), str(body.path or "")])
    prev = dict(mv.get("outcome_report") or {})
    if op:
        hit = next((o for o in (prev.get("ops") or []) if o.get("op") == op), None)
        if hit is not None:
            if hit.get("sig") != sig:
                raise HTTPException(409, detail={
                    "code": "OPERATION_PAYLOAD_MISMATCH",
                    "message": "This operation id was already accepted for a different report."})
            return {"ok": True, "replayed": True, "move": _moves.view(mv),
                    "continuation": _plan_continuation(s)}
    if prev.get("outcome") or prev.get("note"):
        same = ((body.outcome is None or body.outcome == (prev.get("outcome") or ""))
                and (note is None or note == (prev.get("note") or ""))
                and ((not body.path) or body.outcome is None or body.path == (prev.get("path") or "")))
        if same:
            return {"ok": True, "unchanged": True, "move": _moves.view(mv),
                    "continuation": _plan_continuation(s)}
    # A result can only be reported on work that was executed; the guard returns its problems, so a
    # rejected report commits nothing (no event, no snapshot, no Move mutation).
    if problems := _moves.outcome_report_problems(s, mv, body.outcome, note):
        raise HTTPException(409, detail={"code": "MOVE_OUTCOME_REJECTED", "message": problems[0]})
    _snapshot_experience_before(s, persist=False)
    try:
        ev = event_store.append_event(
            s, role="user", kind=event_store.KIND_OUTCOME,
            text="move outcome " + move_id + ": " + str(body.outcome or "result not reported")
                 + (f" | {note}" if note else ""),
            correlation_id=move_id, idempotency_key=op)
    except event_store.EventPersistenceError as e:
        raise HTTPException(503, f"hasil belum tahan-lama, coba lagi: {e}") from e
    before = copy.deepcopy(mv)
    effective_path = body.path or (prev.get("path") or "")
    res = _moves.record_outcome_report(s, move_id, outcome=body.outcome, note=note, path=effective_path,
                                       event_id=ev["event_id"], operation_id=op, sig=sig)
    try:
        store.save_strict(s)
    except event_store.SessionPersistenceError:
        idx = next(i for i, m in enumerate(s.moves) if m["move_id"] == move_id)
        s.moves[idx] = before
        event_store.mark_event_status(s, ev["event_id"], event_store.STATUS_PERSIST_FAILED,
                                      note="snapshot sesi gagal disimpan setelah laporan hasil")
        raise HTTPException(503, detail={
            "code": "REPORT_NOT_DURABLE",
            "message": "Your report could not be saved. Nothing was recorded; please try again."}) from None
    event_store.mark_event_status(s, ev["event_id"], event_store.STATUS_COMMITTED)
    extra: dict = {}
    if body.outcome and effective_path and s.user_id:
        # The outcome→path edge (business effect) is derived AFTER the accepted report. It is
        # idempotent per operation key, and a failure is reported as pending — never as a lost report.
        try:
            path_states.apply_and_log(
                s.user_id, sid, effective_path, body.outcome,
                goal_id=((s.goal or {}).get("goal_id") or "") if s.goal else "",
                op_key=f"{op or ev['event_id']}|{effective_path}")
        except Exception as exc:  # noqa: BLE001
            _log_reassess_failure(sid, exc)
            extra["effects_pending"] = True
    store.save(s)
    return {"ok": True, "correction": bool(res.get("correction")), "move": _moves.view(s.moves[
                next(i for i, m in enumerate(s.moves) if m["move_id"] == move_id)]),
            "continuation": _plan_continuation(s), **extra}


@app.post("/session/{sid}/finalize", response_model=DiagnosisArtifact)
def finalize(sid: str, force: bool = False):
    """Force-finish the interview → synthesize the diagnosis (for quick demos / eval).

    Idempotent (E3, 23 Sep): a full synthesis = 5 sequential LLM calls (measured
    162.2s: llm_draft 37.3s + knowledge_rules 124.9s). An existing diagnosis is
    returned as-is so a second click/retry does not burn another ~162s.
    `?force=1` forces re-synthesis — used by evals that deliberately re-measure.

    CIR-05 (int 19 §13.7, int 18 phase C): the cached artifact is NOT returned when the last
    checkpoint is already `stale` — material changes (corrections/outcomes/Goal) since the
    checkpoint invalidate its basis, so this call re-synthesizes over the CURRENT state. A stale
    checkpoint is never presented as fresh.
    """
    s = store.get(sid)
    if not s:
        raise HTTPException(404, "session not found")
    _snapshot_experience_before(s, persist=False)   # P1-06: _diagnose saves on success
    if s.diagnosis and s.interview_done and not force:
        from app import checkpoints as _cp
        if (( _cp.latest(s) or {}).get("status")) == "stale":
            return _diagnose(s)
        return s.diagnosis
    s.interview_done = True
    return _diagnose(s)


_EXPLAIN_LOCKS: dict[str, threading.Lock] = {}


def _goal_guard_ctx(s) -> dict:
    """Workspace context for narrative guards: OTHER Goals owned by the user (context that must not be
    presented as the active goal), OLD-version targets of this goal (must not appear after a revision),
    and recent measurements. Best-effort: without a user/structured goal -> empty (guards use the
    session Goal only)."""
    gid = (s.goal or {}).get("goal_id")
    if not s.user_id or not gid:
        return {}
    try:
        others = [g for g in workspace_goals.goals(s.user_id) if g.get("goal_id") != gid]
        hist = [r["goal"] for r in workspace_goals.history(s.user_id, gid, limit=500)
                if r.get("goal") and r.get("type") in ("GOAL_CREATED", "GOAL_REVISED")]
        ev = workspace_goals.evaluate_from_measurements(s.user_id, gid)
        vals = ev.get("values") or {}
        measured = vals.get("current", vals.get("counted", vals.get("rate")))
        return {"other_goals": others, "history": hist, "measured_current": measured,
                "achieved": ev.get("status") == "ACHIEVED"}
    except Exception:
        return {}


@app.get("/session/{sid}/explain")
def explain(sid: str, refresh: bool = False):
    """Human-language explanation for the Diagnosis screen (agents/explain.py).

    Generated once per artifact then cached; the LLM call takes ~15-50s, so the UI calls this in the
    background and uses the artifact text until it is ready."""
    s = store.get(sid)
    if not s:
        raise HTTPException(404, "session not found")
    if not s.diagnosis:
        raise HTTPException(409, "diagnosis belum ada")
    projection = _readiness_projection(s)

    def fresh() -> bool:
        # basis = diagnosis content + readiness projection state: a changed readiness
        # invalidates a stale explanation (not timestamps, not "already computed").
        return (bool(s.explain) and s.explain.get("basis") == explain_basis(s, projection, _goal_guard_ctx(s))
                and s.explain.get("version") == explain_version and not refresh)

    if fresh():
        return s.explain
    with _EXPLAIN_LOCKS.setdefault(sid, threading.Lock()):
        if fresh():   # another call finished while waiting for the lock
            return s.explain
        llm = get_llm()
        llm.use_session(s.id)
        try:
            # The narrative is grounded in the SAME projection displayed on screen 18;
            # composition is redone inside the lock so what gets saved has the final basis.
            s.explain = explain_session(llm, s, projection=_readiness_projection(s),
                                        goal_ctx=_goal_guard_ctx(s))
        except (RateLimitError, AuthenticationError, APITimeoutError) as e:
            raise _llm_http_exc(e)
        store.save(s)
    return s.explain


class AskTurn(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(default="", max_length=1500)


class AskBody(BaseModel):
    question: str = Field(max_length=600)
    history: list[AskTurn] = Field(default_factory=list, max_length=12)
    focus: str = Field(default="", max_length=80)   # the path the user is currently viewing (optional)


@app.post("/session/{sid}/ask")
def ask(sid: str, body: AskBody):
    """Follow-up discussion over the analysis results (Ask screen). Does not change the diagnosis and does
    not advance the interview: diagnosis updates go through follow-up cycles. Answers are guarded to
    plain language."""
    s = store.get(sid)
    if not s:
        raise HTTPException(404, "session not found")
    if not s.diagnosis:
        raise HTTPException(409, "diagnosis belum ada")
    q = body.question.strip()
    if not q:
        raise HTTPException(400, "pertanyaan kosong")
    llm = get_llm()
    llm.use_session(s.id)
    try:
        return ask_session(llm, s, q, [t.model_dump() for t in body.history], body.focus.strip(),
                           projection=_readiness_projection(s), goal_ctx=_goal_guard_ctx(s))
    except (RateLimitError, AuthenticationError, APITimeoutError) as e:
        raise _llm_http_exc(e)


@app.get("/session/{sid}/diagnosis", response_model=DiagnosisArtifact)
def diagnosis(sid: str):
    s = store.get(sid)
    if not s:
        raise HTTPException(404, "session not found")
    if s.diagnosis:
        return s.diagnosis
    if not s.interview_done:
        raise HTTPException(
            409,
            "interview belum selesai — POST /session/{id}/finalize menghitung sintesis; labelnya "
            "final HANYA bila bukti mendukung (lihat `certification_reasons` pada artefak)",
        )
    return _diagnose(s)


def _journey_context(s):
    """J7 (internal-docs §7): compile the journey context from BEFORE the diagnosis —
    prior verdicts, action results, reassessments, and failed interventions for this
    user. Deterministic 0-LLM; None when there is no prior session/prior diagnosis."""
    if not s.prior_session_id:
        return None
    prior = store.get(s.prior_session_id)
    if not (prior and prior.diagnosis):
        return None
    user_outcomes: dict = {}
    if s.user_id:
        sids = {x.id for x in store.sessions_by_user(s.user_id)}
        user_outcomes = nba_store.outcomes_by_intervention(sids)
    try:
        return compile_journey_context(prior, user_outcomes)
    except Exception:
        return None  # best-effort — never fail the diagnosis


def _require_known_path(s, path: str) -> None:
    """Outcomes may only attach to a Possible Path that exists on this session's map (anti-fabrication):
    an unknown path_id = 422, not a new path state conjured from a free string."""
    if s.diagnosis and is_legacy(getattr(s.diagnosis, "possible_paths", None)):
        raise HTTPException(409, "peta sesi ini lebih tua dari skema navigasi saat ini — diagnosis ulang "
                                 "dulu sebelum melaporkan hasil pada sebuah path")
    known = {p.get("path_id") for p in
             (((getattr(s.diagnosis, "possible_paths", None) or {}).get("paths")) or [])}
    if path not in known:
        raise HTTPException(422, f"path '{path}' tidak ada di peta sesi ini — yang valid: {sorted(known)}")


def _path_states_ctx(s):
    """P-E (internal-docs §3.5): per-path outcome states owned by the
    user — carried into the diagnosis REGARDLESS of prior_session (a path STOPped
    in the previous session stays STOP in the new one; reopen only via outcome).

    Goal-Relative (int 09 §4.4): scope = the session's active Goal (goal-scoped +
    inherited global); outcomes of other Goals do not leak (GR-19)."""
    if not s.user_id:
        return None
    gid = ((s.goal or {}).get("goal_id") or None) if s.goal else None
    states = path_states.get_states(s.user_id, goal_id=gid)
    return states or None


def _readiness_projection(s) -> dict:
    """Adjudicated readiness projection: ONE readiness reality for every reader.

    The UI checklist (screen 18), LLM narrative input, deterministic fallback, grounding, and the
    explanation cache basis all read this projection — not raw routes or raw gates each on their
    own. A route that fails to compose (e.g. an anonymous session) -> projection from path gates
    only; requirement states stay UNKNOWN, never invented."""
    try:
        route_data = _compose_routes(s)
    except RouteCompositionError:
        raise  # a strategy/template contract violation = an engine bug; never mask it as "no route"
    except Exception:
        route_data = None
    return build_readiness_projection(s.diagnosis, route_data, _path_states_ctx(s))


# ── E5 (23 Sep 2026): per-stage progress for the UI ─────────────────────────
# Stage names already exist in pipeline_trace but only appear AFTER a run finishes.
# Finalize can take 70–110s, and previously the user only saw three blinking dots with no
# idea which stage was running. An in-memory map + polling (not SSE) so clients don't need
# a rewrite. Label = the user's language; internal stage names are NEVER displayed.
_PROGRESS: dict[str, dict] = {}
# The wording follows the SESSION language. The table used to be one hardcoded Indonesian list, so an
# English session (language="en") saw Indonesian progress text under an English interface - the comment
# above already promised otherwise. English is the default; "id" opts into Indonesian.
_STAGE_LABEL_EN = {
    "llm_draft": "Drafting the diagnosis…",
    "llm_draft_retry": "Redrafting the diagnosis…",
    "knowledge_rules": "Matching your evidence against the knowledge base…",
    "mechanisms": "Analysing the mechanisms…",
    "confidence.ranking": "Ranking the hypotheses…",
    "knowledge.consequences": "Applying what the knowledge implies…",
    "confidence.overall": "Computing confidence…",
    "arbitration.begin": "Preparing the evidence arbitration…",
    "extract_state": "Extracting the revenue figures…",
    "opportunities": "Looking for opportunities…",
    "spectrum": "Deciding the readiness level…",
    "paths": "Working out the possible paths…",
    "validate_state": "Validating your situation…",
    "revenue_state": "Tidying the revenue situation…",
    "causal": "Building the causal hypotheses…",
    "nba_grounding": "Linking the action plan to the knowledge base…",
    "artifact.assembly": "Putting the result together…",
}
_STAGE_LABEL_ID = {
    "llm_draft": "Menyusun diagnosis…",
    "llm_draft_retry": "Menyusun ulang diagnosis…",
    "knowledge_rules": "Mencocokkan bukti dengan basis pengetahuan…",
    "mechanisms": "Menganalisis mekanisme…",
    "confidence.ranking": "Memeringkat hipotesis…",
    "knowledge.consequences": "Menerapkan konsekuensi pengetahuan…",
    "confidence.overall": "Menghitung keyakinan…",
    "arbitration.begin": "Menyiapkan arbitrase bukti…",
    "extract_state": "Mengekstrak angka revenue…",
    "opportunities": "Mencari peluang…",
    "spectrum": "Menentukan tingkat kesiapan…",
    "paths": "Menghitung jalur yang mungkin…",
    "validate_state": "Memvalidasi state…",
    "revenue_state": "Merapikan state revenue…",
    "causal": "Menyusun hipotesis kausal…",
    "nba_grounding": "Menghubungkan rencana aksi ke knowledge base…",
    "artifact.assembly": "Merapikan hasil akhir…",
}
_STAGE_LABEL_DEFAULT = {"en": "Working…", "id": "Memproses…"}


def _stage_labels(lang: str) -> tuple[dict, str]:
    """(label map, fallback) for the session language. Anything that is not Indonesian reads English."""
    if str(lang or "").strip().lower().startswith("id"):
        return _STAGE_LABEL_ID, _STAGE_LABEL_DEFAULT["id"]
    return _STAGE_LABEL_EN, _STAGE_LABEL_DEFAULT["en"]


def _progress_cb(sid: str, lang: str = "en"):
    labels, fallback = _stage_labels(lang)

    def _cb(name: str, index: int) -> None:
        _PROGRESS[sid] = {
            "stage": name,
            "label": labels.get(name, fallback),
            "index": index,
            "ts": time.time(),
        }
    return _cb


def _ledger_state_guard(reader, base_state_of, superseded_ids):
    """A1-F1 — fail-safe at the READ boundary of the final diagnosis (R4-E).

    When this turn's live adjudication FAILS (and supersession invalidation didn't get to write
    UNKNOWN), an old ledger entry whose ENTIRE citation set has been superseded must NOT be served
    as the CURRENT state. Return UNKNOWN by absence (None); the append-only ledger file is untouched.
    On the success path this is a no-op: invalidation already wrote UNKNOWN entries with empty
    citations."""
    def read(requirement_id: str) -> str | None:
        st = reader.read(requirement_id)
        if st.adjudicated and st.evidence_refs and set(st.evidence_refs) <= superseded_ids:
            return None
        return base_state_of(requirement_id)
    return read


def _record_post_diagnosis_side_effects(s, artifact) -> None:
    """Best-effort derived records that must follow a DURABLE diagnosis commit.

    H2 (Phase 6.1 hotfix): a Business State Snapshot and a funnel row describe a checkpoint that was
    COMMITTED. They used to run inside _diagnose before the caller owned the strict save, so a failed
    strict save could leave records pointing at a version the caller reported as not saved. They stay
    best-effort: neither may ever fail an already durable diagnosis."""
    if getattr(s, "user_id", ""):
        try:
            workspace.record_snapshot(s.user_id, s.id, artifact)
        except Exception:  # noqa: BLE001
            pass
    try:
        funnel.record(
            session_id=s.id,
            primary=artifact.primary_constraint_id,
            spectrum_level=(artifact.decision_spectrum or {}).get("level"),
            funnel_stages=artifact.funnel_stages,
            metrics=artifact.metrics,
            confidence=artifact.confidence,
            user_id=s.user_id,  # J3: keying per user (partial — session_id still present)
        )
    except Exception:  # noqa: BLE001
        pass


class BasisChangedDuringSynthesis(Exception):
    """Phase 6.2: the evaluated basis (evidence, claims, Goal or accepted observations) changed while
    the synthesis was running. Carries the names of the drifted parts for the conflict response."""

    def __init__(self, drift: list[str]):
        super().__init__("basis changed during synthesis: " + ", ".join(drift))
        self.drift = drift


@app.exception_handler(BasisChangedDuringSynthesis)
async def _basis_changed_handler(_request, exc: BasisChangedDuringSynthesis):
    return JSONResponse(status_code=409, content={"detail": {
        "code": "BASIS_CHANGED_DURING_SYNTHESIS",
        "message": ("Your record changed while the assessment was running, so it was not saved. "
                    "Nothing you reported was lost; try again."), "drift": exc.drift}})


def _diagnose(s, *, operation_id: str = "", persist: bool = True):
    """Synthesize over the CURRENT state and commit it as a new checkpoint.

    NC-R4 (Phase 6.1): operation_id is the client operation key that produced this checkpoint; a
    resend of the SAME explicitly-confirmed reassessment replays the accepted checkpoint instead of
    buying a second synthesis. Callers that do not pass one keep the previous behaviour.

    H2 (Phase 6.1 hotfix): persist=False hands the COMMIT to the caller. In that mode this function
    writes neither the session nor any derived side record, because the caller owns the strict save
    and its rollback - an internal best-effort save could otherwise leave v(n+1) on disk after the
    caller honestly reported that nothing was committed."""
    llm = get_llm()
    llm.use_session(s.id)
    # J7-b/c (internal-docs §7): a closed loop — session n knows session n-1's results.
    journey_ctx = _journey_context(s)
    # P-E: path states are always carried along (when the user has history) — merged into journey_ctx.
    _pstates = _path_states_ctx(s)
    if _pstates:
        journey_ctx = {**(journey_ctx or {}), "path_states": _pstates}
    # Phase 6.2 (P0 grounding): the accepted observations of THIS session (reported outcomes, check-ins,
    # Move observations) enter the synthesis even when there is no prior session. They stay labelled
    # SELF_REPORTED / unverified and are NOT added to the evidence ledger (no double counting).
    try:
        from app.observations import accepted_observation_context
        _obs_ctx = accepted_observation_context(s)
    except Exception:  # noqa: BLE001 - best-effort, like the rest of the journey context
        _obs_ctx = None
    if _obs_ctx:
        journey_ctx = {**(journey_ctx or {}), "session_observations": _obs_ctx}
    _PROGRESS.pop(s.id, None)
    # DCP-01/03 (int 16 S1): deep synthesis uses ONE current canonical meaning. Evidence whose claims
    # were superseded does NOT join as present fact; it is passed separately as explanatory history.
    # This aligns the deep basis with provisional navigation (current_evidence).
    from core.schema.evidence import current_evidence
    _cur_evidence = current_evidence(s.evidence)
    _hist_evidence = [e for e in s.evidence if getattr(e, "superseded", False)]
    # R5/P0-2: a turn whose navigation degraded doesn't write the ledger; the final diagnosis must not
    # read a stale ledger and then differ from GET /navigation which adjudicates. Run the SAME live
    # adjudication (idempotent; second-pass cached per provider/model/prompt identity) BEFORE reading
    # the ledger.
    if s.user_id:
        try:
            from ontology.mapper.live_adjudication import run_live_adjudication as _adjudicate
            _adjudicate(s.user_id, s.evidence, goal=getattr(s, "goal", None), session_id=s.id,
                        graph=s.state_graph, llm=llm)
        except Exception:  # noqa: BLE001 — adjudication failure must not sink the diagnosis; ledger read as-is
            pass
    # F3d/R5 (P0-2): the FINAL diagnosis reads the same adjudicated requirement states as provisional
    # navigation (one Requirement State Reader, authoritative ledger). Without this the final feasible
    # set could differ from the earlier conversation for the same evidence and snapshot (two call
    # sites, two contexts).
    from core.navigation.requirement_state import status_reader as _status_reader
    from ontology.mapper.live_adjudication import support_of as _support_of
    from store.requirement_state import user_requirement_reader as _user_requirement_reader
    # R1-remediation Probe A: the reader is scoped to the business context (session goal_id).
    _reader = _user_requirement_reader(
        s.user_id,
        goal_id=((getattr(s, "goal", None) or {}).get("goal_id") or None),
        support_of=_support_of())
    _base_state_of = _status_reader(_reader)
    # A1-F1 fail-safe (R4-E at the read boundary): when this turn's adjudication FAILS (the except
    # above) and invalidation didn't get to write UNKNOWN, an old entry whose ENTIRE citation set was
    # superseded must NOT be served as the CURRENT state. Return UNKNOWN by absence; the append-only
    # ledger file is untouched. On the success path this is a no-op (invalidation wrote UNKNOWN).
    _superseded_ids = {e.id for e in _hist_evidence}
    _ledger_state_of = _ledger_state_guard(_reader, _base_state_of, _superseded_ids)

    # Phase 6.2 (P0 stable basis): freeze the basis this synthesis actually evaluates; a pre-commit guard
    # below refuses to certify a checkpoint if the session moved on while the model was thinking.
    from app.binding import build_binding as _build_binding
    _basis = _build_binding(s, llm)
    try:
        artifact = synthesize(
            llm, s.goal_text, _cur_evidence, s.full_transcript(), s.language,
            # dsc.v1 (int 18 §12.5): the label is NOT a constant and not the workflow's business —
            # synthesis is first computed with safe defaults, certification applied once its
            # epistemic standing is known.
            status="provisional",
            journey_context=journey_ctx,
            graph=s.state_graph or None,
            on_stage=_progress_cb(s.id, s.language),   # progress text follows the session language
            goal_obj=s.goal,
            historical_evidence=_hist_evidence,
            ledger_state_of=_ledger_state_of,
        )
    except (RateLimitError, AuthenticationError, APITimeoutError) as e:
        raise _llm_http_exc(e)
    finally:
        _PROGRESS.pop(s.id, None)   # E5: clean up whatever the outcome
    # NC-R5 (Phase 6.1): archive the plan this synthesis REPLACES — together with every status and
    # outcome already reported against it — INTO the new checkpoint. Without this, swapping the
    # artifact would silently erase the execution history of the previous plan (3/3 recorded
    # becoming 0/N with no trace). The archive is versioned; nothing is carried into the new plan.
    from app import checkpoints as _cp_archive
    _now = _build_binding(s, llm)
    _drift = [k for k in ("state_version", "source_evidence_refs", "superseded_evidence_refs",
                              "observation_revision", "observation_fingerprint",
                              "goal_version") if _now.get(k) != _basis.get(k)]
    if _drift:
        # The session changed while the model was thinking. Committing now would stamp a checkpoint
        # with a basis it never evaluated. Nothing is committed; the previous checkpoint and every
        # newly accepted observation stay exactly as they are.
        raise BasisChangedDuringSynthesis(_drift)
    # The guard above proves state_version / evidence / Goal / observations are IDENTICAL to what the
    # model evaluated, so the binding make_checkpoint builds below is the evaluated basis (its
    # observation digest is read from the committed plan on purpose: that is what eligibility compares).
    _carried_plan = _cp_archive.plan_snapshot(s)
    s.diagnosis = artifact
    # dsc.v1: the label is certified from computed facts (critical_unknown_ids + standing + freshness).
    # Always `provisional` unless both int 18 §12.5 conditions hold; the reason goes into the
    # artifact + checkpoint.
    certify_artifact(s, artifact)
    s.explain = None   # the explanation is linked to the old artifact
    # R6: every diagnosis = a versioned CHECKPOINT (old ones kept intact, marked superseded)
    from app import checkpoints as _cp
    _cp.make_checkpoint(s, llm, reason="reassessment" if getattr(s, "checkpoints", None) else "diagnosis",
                        artifact=artifact, carried_plan=_carried_plan, operation_id=operation_id)
    # J3 (internal-docs §7): cross-session delta — deterministic when sessions are linked.
    if s.prior_session_id:
        prior = store.get(s.prior_session_id)
        if prior and prior.diagnosis:
            try:
                s.journey_delta = compute_delta(prior.diagnosis, artifact)
            except Exception:
                s.journey_delta = None  # best-effort — never fail the diagnosis
    if persist:
        store.save(s)  # iter-14: persist the session — the ledger doesn't vanish on restart
        _record_post_diagnosis_side_effects(s, artifact)
    return artifact


@app.get("/sessions")
def list_sessions(request: Request, limit: int = 20):
    """UI recovery fallback — chat/restore must not depend on localStorage alone
    (24 Sep incident: a new browser context = empty LS → the UI looked like it lost
    sessions, while they were intact on disk). Read-only endpoint. TOKEN mode: only
    sessions owned by the actor (BC-02); LOCAL mode: latest sessions for the
    "Your revenue maps" sidebar."""
    actor = getattr(request.state, "actor", None)
    items = sorted(store.all_sessions(), key=lambda x: x.created_ts, reverse=True)[: max(1, min(limit, 50))]
    if actor:
        items = [x for x in items if x.user_id == actor]
    return [
        {
            "session_id": x.id,
            "goal_text": x.goal_text,
            "user_id": x.user_id,
            "prior_session_id": x.prior_session_id,
            "interview_done": bool(x.interview_done),
            "has_diagnosis": bool(x.diagnosis),
            "created_ts": x.created_ts,
        }
        for x in items
    ]


@app.get("/workspace/{user_id}")
def get_workspace(user_id: str):
    """P-D (internal-docs §5, §9): per-user workspace projection —
    latest goal, path states (P-E), snapshots + the latest Business State Diff,
    event history. The map is a view; the internal graph is never exposed raw."""
    try:
        validate_user_id(user_id)  # D8: 400, not traversal / 500
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    goal = None
    sessions_summary: list[dict] = []
    for x in store.sessions_by_user(user_id):
        sessions_summary.append({
            "session_id": x.id, "created_ts": x.created_ts,
            "has_diagnosis": bool(x.diagnosis),
            "prior_session_id": x.prior_session_id,
        })
        if x.goal:
            goal = x.goal  # repeatedly overwritten → the LAST session's goal wins
    view = workspace.workspace_view(
        user_id,
        path_states=path_states.get_states(user_id),
        sessions_summary=sessions_summary,
    )
    if view is None:
        raise HTTPException(404, f"workspace '{user_id}' tidak ditemukan — belum ada aktivitas")
    view["goal"] = goal
    # P-F (internal-docs §5.3–5.4): two trajectories + drift taxonomy —
    # flat revenue + improving understanding = a legitimate learning phase, not failure.
    snaps = view.get("snapshots") or []
    view["goal_trajectory"] = goal_trajectory(goal, snaps)
    view["decision_trajectory"] = decision_trajectory(snaps, view.get("events"))
    view["drift"] = drift_taxonomy(view.get("last_diff"))
    return view


class NbaReport(BaseModel):
    """Phase 4 (internal-docs §10.6): post-action NBA report
    (Gate 5b internal-docs)."""
    intervention_id: str
    outcome: Literal["moved", "not_moved", "regret", "confounded"]
    notes: str = ""
    # P-E (internal-docs §3.5): path affiliation — optional; when set,
    # the outcome ALSO updates the path status (edge outcome→path) + emits PATH_STATUS_CHANGED.
    path: str = ""


@app.post("/session/{sid}/nba_report")
def nba_report(sid: str, body: NbaReport):
    """Capture NBA execution results — the DoD's most important metric: Decision Regret.
    Anti-fabrication: intervention_id MUST exist in the session artifact (final KB scope,
    or a guard-grounded alternative)."""
    s = store.get(sid)
    if not s:
        raise HTTPException(404, "session not found")
    d = s.diagnosis
    if not d:
        raise HTTPException(409, "diagnosis belum ada — finalize dulu")
    ka = d.knowledge_activation or {}
    ng = ka.get("nba_grounding") or {}
    allowed = {i.get("id") for i in ka.get("interventions", [])}
    allowed |= set(ng.get("intervention_ids") or [])
    if ng.get("alternative_id"):
        allowed.add(ng["alternative_id"])
    allowed |= {
        getattr(it, "intervention_id", "")
        for it in (d.day_by_day or [])
        if getattr(it, "intervention_id", "")
    }
    allowed.discard(None)
    iid = body.intervention_id.strip().upper()
    if allowed and iid not in allowed:
        raise HTTPException(
            422,
            f"intervention '{iid}' tidak ada di artifact sesi ini — anti-fabrikasi. "
            f"Yang valid: {sorted(allowed)}",
        )
    try:
        row = nba_store.record(
            sid, iid, body.outcome, body.notes,
            primary_constraint=d.primary_constraint_id,
        )
    except ValueError as e:
        raise HTTPException(422, str(e))
    # P3 (internal-docs §10.8): recalc knowledge confidence on every new report.
    updated = nba_store.recalc()
    # P-E: the outcome→path status edge (the innovation core of internal-docs §3.5).
    path_event = None
    if body.path:
        _require_known_path(s, body.path)
        try:
            res = path_states.apply_and_log(
                s.user_id, sid, body.path, body.outcome,
                goal_id=((s.goal or {}).get("goal_id") or "") if s.goal else "",
            )
            path_event = res["event"]
        except ValueError as e:
            raise HTTPException(422, str(e))
    return {
        "ok": True, "report": row,
        "confidence": updated["items"].get(iid),
        "summary": nba_store.summary(),
        "path_event": path_event,
    }


def _action_report_sig(status, outcome, note, path) -> str:
    """Deterministic fingerprint of a report payload (H5).

    It tells a REPLAY of the same command apart from a REUSE of the same operation key with a
    DIFFERENT command - the second is a conflict, not a replay."""
    return "|".join([str(status or ""), str(outcome or ""), str(note or ""), str(path or "")])


def _action_report_prior(it, op: str) -> dict | None:
    """The already-accepted report carrying this operation key, or None (H5).

    The bounded per-action history is read first. Items written before that history existed carry only
    the LAST key: that one is still recognised (without a recorded payload signature) so an in-flight
    retry of the most recent report is never applied twice."""
    if it is None or not op:
        return None
    for row in (getattr(it, "report_operations", None) or []):
        if isinstance(row, dict) and str(row.get("op") or "") == op:
            return row
    if str(getattr(it, "report_operation_id", "") or "") == op:
        return {"op": op, "sig": ""}
    return None


def _restore_action_item(s, idx: int, prev) -> None:
    """Undo an in-memory action-report mutation whose FOLLOW-UP step failed (H5).

    The artifact item and its outcome-log/path effect are ONE command, so a report is committed only
    together with the whole command: a failure in the second step must not leave a half-applied action
    behind (and must not invite a retry that duplicates it)."""
    d = getattr(s, "diagnosis", None)
    if d is None or prev is None:
        return
    if 0 <= idx < len(d.day_by_day):
        d.day_by_day[idx] = prev


def _validate_action_report(s, idx: int, *, status=None, outcome=None, path: str = "",
                            note: str | None = None) -> None:
    """Validate an action report WITHOUT mutating. Raises HTTPException on any problem, so a caller
    can reject the WHOLE command before the first write (P0-05)."""
    d = s.diagnosis
    if not d:
        raise HTTPException(409, "diagnosis belum ada — finalize dulu")
    if not (0 <= idx < len(d.day_by_day)):
        raise HTTPException(
            404, f"aksi index {idx} tidak ada — day_by_day punya {len(d.day_by_day)} item"
        )
    # Phase 6.1 (NC-R6): an EMPTY report is still rejected, and "not measured yet" must never be
    # coerced into an outcome. The contract is unchanged (status OR outcome); what changed at the
    # caller is that an outcome correction no longer has to smuggle status=DONE to be accepted.
    # a note alone is a legitimate report: it records what the person saw without inventing an outcome
    if status is None and outcome is None and not (note or "").strip():
        raise HTTPException(422, "minimal salah satu dari status/outcome wajib")
    if outcome is not None and path:
        _require_known_path(s, path)


def _classify_action_report(it, *, status=None, outcome=None, note: str | None = None, path: str = "") -> str:
    """Phase 6.2 - the BUSINESS meaning of a report, independent of its transport key.

      unchanged  - the same effective report again (a reopened form submitted as it was): no write,
                   no second outcome effect, no new timestamp, no new Journey event;
      correction - a report that changes an observation already on record (outcome, note or path):
                   the earlier one is preserved as history and stops counting as an independent one;
      new        - the first outcome/note recorded for this action, or a pure execution change.

    Two reports at different times with the SAME category but different content are corrections,
    not suppressed. A genuinely new independent observation of a plan action is a check-in or a Move
    observation (they have their own identity); one action item holds ONE effective report."""
    prev_outcome = str(getattr(it, "outcome", "") or "")
    prev_note = str(getattr(it, "note", "") or "")
    prev_path = str(getattr(it, "outcome_path", "") or "")
    prev_status = str(getattr(it, "status", "TODO") or "TODO")
    status_same = status is None or status == prev_status
    outcome_same = outcome is None or outcome == prev_outcome
    # note: None = omitted (keep what is on record); "" alongside an outcome = the person emptied it.
    note_same = note is None or note == prev_note
    # Items reported before the path was recorded cannot tell which path their effect hit; a repeat
    # of the same outcome must not re-apply it, so an unknown previous path counts as the same.
    path_same = (not path) or outcome is None or (prev_outcome and not prev_path
                                                  and outcome == prev_outcome) or path == prev_path
    if status_same and outcome_same and note_same and path_same:
        return "unchanged"
    changes_observation = (outcome is not None and outcome != prev_outcome) or (
        note is not None and note != prev_note) \
        or (outcome is not None and bool(path) and path != prev_path and bool(prev_path))
    if prev_outcome and changes_observation:
        return "correction"
    return "new"


def _plan_report_effects(it, *, outcome, note: str | None, path: str, kind: str) -> dict | None:
    """The derived effects (outcome log + path counters) this report needs, as plain data stored with
    the accepted report so they can be re-applied after an ambiguous failure. None = no effect."""
    if outcome is None:
        return None
    prev_outcome = str(getattr(it, "outcome", "") or "")
    prev_path = str(getattr(it, "outcome_path", "") or "")
    effective_path = path or (prev_path if outcome == prev_outcome else "")
    if kind == "correction" and outcome == prev_outcome and effective_path == prev_path:
        return None          # a note-only correction changes no counter and adds no outcome row
    return {
        "outcome": outcome,
        "note": str(getattr(it, "note", "") or "") if note is None else note,
        "path": effective_path, "iid": str(getattr(it, "intervention_id", "") or "").strip(),
        "prev_outcome": prev_outcome if kind == "correction" else "",
        "prev_path": prev_path if kind == "correction" else "",
        "corrects": str(getattr(it, "outcome_log_ref", "") or "") if kind == "correction" else "",
    }


def _apply_action_report(s, sid: str, idx: int, *, status=None, outcome=None, note: str | None = None,
                         path: str = "", operation_id: str = "", report_sig: str = "",
                         persist: bool = True, kind: str = "new", effects: dict | None = None) -> dict:
    """Mutate ONE day_by_day action report in memory. Deterministic; no confidence recalc.

    Shared by POST /action/{idx}/report and the canonical check-in commit boundary (P0-05). When
    persist=False the CALLER owns the commit, and the returned prev lets it roll the item back, so a
    failure in a later step can never leave a committed action without its check-in.

    Phase 6.2: a correction keeps the replaced report in `outcome_revisions` (history, not a second
    independent observation) and the derived effects are recorded as PENDING on the operation row
    until they are applied (see _run_report_effects)."""
    _validate_action_report(s, idx, status=status, outcome=outcome, path=path)
    d = s.diagnosis
    it = d.day_by_day[idx]
    prev = it
    update: dict = {}
    now = int(time.time())
    # D-10 + H5: the accepted report is identified by its operation key, and a BOUNDED history is kept
    # per action. A report without a client key still gets a row when it has derived effects, so a
    # failed effect can be reconciled later.
    row_op = str(operation_id or (f"fx-{uuid.uuid4().hex[:12]}" if effects else ""))
    if row_op:
        history = [h for h in (getattr(it, "report_operations", None) or [])
                   if isinstance(h, dict) and str(h.get("op") or "") != row_op]
        row = {"op": row_op, "sig": str(report_sig or ""), "ts": now, "kind": kind}
        if effects:
            row["effects"] = "pending"
            row["eff"] = effects
        history.append(row)
        update["report_operations"] = history[-10:]
        if operation_id:
            update["report_operation_id"] = str(operation_id)
    if status is not None:
        update["status"] = status
        if status in ("DONE", "SKIPPED"):
            if it.status != status or not it.done_at:
                update["done_at"] = now
        else:
            update["done_at"] = None
    if kind == "correction" and (getattr(it, "outcome", "") or ""):
        revs = list(getattr(it, "outcome_revisions", None) or [])
        revs.append({"outcome": it.outcome, "note": it.note, "path": getattr(it, "outcome_path", ""),
                     "reported_at": it.reported_at, "superseded_at": now, "op": row_op or None})
        update["outcome_revisions"] = revs[-20:]
    if outcome is not None:
        update["outcome"] = outcome
        update["outcome_path"] = path or (getattr(it, "outcome_path", "") if outcome == it.outcome else "")
    if outcome is not None or (kind == "correction" and note is not None):
        update["reported_at"] = now
    if note is not None:
        update["note"] = note
    d.day_by_day[idx] = it.model_copy(update=update)
    if persist:
        store.save(s)
    return {"ok": True, "index": idx, "prev": prev, "action": d.day_by_day[idx].model_dump(),
            "effect_op": row_op if effects else ""}


def _run_report_effects(s, sid: str, idx: int, op: str, eff: dict) -> dict:
    """Apply the derived effects of ONE accepted report (outcome log + path counters).

    Idempotent per (session, action, op): the outcome log and the path state both remember the effect
    key, so re-running after an ambiguous failure returns what was already written instead of a
    duplicate. The session item is the accepted-event AUTHORITY; this only derives from it."""
    d = s.diagnosis
    logged, path_event, log_ref = None, None, ""
    iid = (eff.get("iid") or "").strip()
    outcome = eff.get("outcome")
    if outcome and iid and d is not None:
        try:
            logged = nba_store.record(
                sid, iid, outcome, eff.get("note") or "", primary_constraint=d.primary_constraint_id,
                op_key=f"{sid}|{idx}|{op}", corrects=eff.get("corrects") or "")
            log_ref = str((logged or {}).get("row_id") or "")
        except ValueError:
            logged = None  # the outcome enum is pydantic-validated - can't happen
    path = eff.get("path") or ""
    if outcome and path:
        gid = ((s.goal or {}).get("goal_id") or "") if s.goal else ""
        prev_o, prev_p = eff.get("prev_outcome") or "", eff.get("prev_path") or ""
        try:
            if prev_o and prev_p and prev_p != path:
                # the corrected report moved to ANOTHER path: withdraw the old path's effect first
                path_states.apply_and_log(s.user_id, sid, prev_p, None, goal_id=gid,
                                          op_key=f"{op}|{prev_p}|withdraw", reverse={"outcome": prev_o})
            res = path_states.apply_and_log(
                s.user_id, sid, path, outcome, goal_id=gid, op_key=f"{op}|{path}",
                reverse={"outcome": prev_o} if (prev_o and prev_p == path) else None)
            path_event = res["event"]
        except ValueError as e:
            raise HTTPException(422, str(e))
    return {"logged_to_outcome_log": bool(logged), "path_event": path_event, "log_ref": log_ref}


def _settle_report_effects(s, sid: str, idx: int, op: str) -> dict:
    """Run the PENDING effects of operation `op` on action `idx`, then mark them done and save.
    A failure leaves them pending (nothing is lost, nothing is applied twice on the next attempt)."""
    d = s.diagnosis
    if idx < 0:                                   # the plan-level report
        pr = dict(getattr(d, "plan_report", None) or {})
        if pr.get("effects") != "pending" or not pr.get("eff"):
            return {"logged_to_outcome_log": False, "path_event": None, "settled": True}
        lg = _run_report_effects(s, sid, idx, op, pr["eff"])
        pr["effects"] = "done"
        d.plan_report = pr
        store.save(s)
        return {**lg, "settled": True}
    it = d.day_by_day[idx]
    rows = list(getattr(it, "report_operations", None) or [])
    row = next((r for r in rows if isinstance(r, dict) and r.get("op") == op), None)
    if not row or row.get("effects") != "pending" or not row.get("eff"):
        return {"logged_to_outcome_log": False, "path_event": None, "settled": True}
    lg = _run_report_effects(s, sid, idx, op, row["eff"])
    row["effects"] = "done"
    upd = {"report_operations": rows}
    if lg.get("log_ref"):
        upd["outcome_log_ref"] = lg["log_ref"]
    d.day_by_day[idx] = it.model_copy(update=upd)
    store.save(s)
    return {**lg, "settled": True}


def _pending_report_effects(s) -> list[tuple[int, str]]:
    """(action index, operation key) of accepted reports whose derived effects are not yet confirmed.
    Pure read."""
    d = getattr(s, "diagnosis", None)
    out: list[tuple[int, str]] = []
    pr = getattr(d, "plan_report", None) or {}
    if pr.get("effects") == "pending" and pr.get("last_op"):
        out.append((-1, str(pr["last_op"])))          # -1 = the plan-level report
    for i, it in enumerate(getattr(d, "day_by_day", None) or []):
        for r in (getattr(it, "report_operations", None) or []):
            if isinstance(r, dict) and r.get("effects") == "pending":
                out.append((i, str(r.get("op"))))
    return out


def _reconcile_pending_report_effects(s, sid: str) -> int:
    """Apply the effects an earlier accepted report left pending, in order. Returns how many REMAIN
    pending. Runs only at mutating boundaries (a new report, a reassessment, the explicit reconcile
    endpoint) - never on a read. A failure leaves the effect pending; it is never marked done unless the
    stores acknowledged the write (they raise on failure)."""
    for i, op in _pending_report_effects(s):
        try:
            _settle_report_effects(s, sid, i, op)
        except Exception as exc:  # noqa: BLE001
            _log_reassess_failure(sid, exc)
    return len(_pending_report_effects(s))


@app.post("/session/{sid}/effects/reconcile")
def reconcile_effects(sid: str):
    """Explicit recovery of derived report effects (outcome log, path counters) that an accepted report
    left pending. Idempotent; it never creates a report, a checkpoint or a synthesis."""
    s = store.get(sid)
    if not s:
        raise HTTPException(404, "session not found")
    before = len(_pending_report_effects(s))
    remaining = _reconcile_pending_report_effects(s, sid)
    return {"session_id": s.id, "pending_before": before, "pending_after": remaining,
            "settled": before - remaining}


class ActionReport(BaseModel):
    """J2 follow-up (internal-docs §7): execution-result report for ONE day_by_day action.

    EXECUTION and OBSERVATION are SEPARATE mutations (Phase 6.1 NC-R6): `status` moves the execution
    record (DONE/SKIPPED/BLOCKED/TODO) while `outcome` records what was observed. Omitting `status`
    leaves execution exactly as it was, so correcting an outcome can never turn a SKIPPED action into
    DONE. Omitting both is allowed only with a note (recording an observation without inventing one).
    """
    status: Literal["TODO", "DONE", "SKIPPED", "BLOCKED"] | None = None
    outcome: Literal["moved", "not_moved", "regret", "confounded"] | None = None
    # Phase 6.2.1: None = not provided (the note on record is kept); "" sent together with an outcome =
    # the person deliberately emptied it (an outcome report restates the observation, note included).
    note: str | None = None
    evidence_hint: str = ""
    # P-E: path affiliation (optional) — an outcome with a path also shifts the path status.
    path: str = ""
    # D-10 (Phase 6.1): client operation key. A resend of the SAME report (double-click, retry after a
    # timeout) replays the accepted report instead of appending a second outcome row. Same key with a
    # different payload = a deterministic 409.
    operation_id: str = ""
    # Phase 6.2: the checkpoint whose plan the user is looking at. An action index is only an address
    # WITHIN one plan; when the plan was replaced meanwhile, index 0 of the old plan must never land
    # on index 0 of the new one. Omitted (older clients) = the current plan, as before.
    checkpoint_id: str = ""


@app.post("/session/{sid}/action/{idx}/report")
def action_report(sid: str, idx: int, body: ActionReport):
    """Per-action report (not per-intervention): update the ActionItem in the artifact
    (status/outcome/reported_at) + append to the outcome log.

    Deterministic — does NOT trigger a knowledge-confidence recalc (NBA guard lesson:
    a user report's grounding is not evidence; KB confidence only shifts via
    per-intervention reports through /nba_report).

    Phase 6.2 semantics: transport retry (same key) replays; the same effective report again is an
    `unchanged` no-op; a changed report is a `correction` that keeps the replaced one as history; an
    action of an ARCHIVED plan is read-only here (409) instead of being misattributed by index."""
    s = store.get(sid)
    if not s:
        raise HTTPException(404, "session not found")
    from app import checkpoints as _cp_mod
    cur_cp = _cp_mod.latest(s)
    if body.checkpoint_id and cur_cp and body.checkpoint_id != cur_cp.get("checkpoint_id"):
        raise HTTPException(409, detail={
            "code": "HISTORICAL_ACTION_READ_ONLY",
            "message": ("That action belongs to an earlier plan that a newer assessment replaced. It stays "
                        "in your history, but it cannot be edited from here, and nothing in your current "
                        "plan was changed."),
            "current_checkpoint_id": cur_cp.get("checkpoint_id")})
    # D-10 (Phase 6.1 / NC-R6): an operation key that was already accepted REPLAYS its report. This is
    # the boundary that stops a retry after an ambiguous failure from writing a second outcome row
    # (nba_store) or a second path event.
    op = (body.operation_id or "").strip()
    note_eff = body.note if (body.note or (body.outcome is not None and body.note is not None)) else None
    sig = _action_report_sig(body.status, body.outcome, note_eff, body.path)
    d0 = getattr(s, "diagnosis", None)
    it0 = d0.day_by_day[idx] if (d0 and 0 <= idx < len(d0.day_by_day)) else None
    if op:
        prior = _action_report_prior(it0, op)
        if prior is not None:
            known = str(prior.get("sig") or "")
            if known and known != sig:
                # H5: the same operation key with a DIFFERENT command is a deterministic conflict, not a
                # replay - otherwise the identity of the first report would authorise a second effect.
                raise HTTPException(409, detail={
                    "code": "OPERATION_PAYLOAD_MISMATCH",
                    "message": ("operation_id ini sudah diterima untuk laporan yang berbeda. "
                                "Kirim kunci operasi baru untuk koreksi baru.")})
            out = {"ok": True, "index": idx, "action": it0.model_dump(), "replayed": True,
                   "logged_to_outcome_log": False, "path_event": None}
            if prior.get("effects") == "pending":      # the accepted report's effects never settled
                try:
                    lg = _settle_report_effects(s, sid, idx, op)
                    out.update(logged_to_outcome_log=lg["logged_to_outcome_log"], path_event=lg["path_event"])
                    out["action"] = s.diagnosis.day_by_day[idx].model_dump()
                except Exception:  # noqa: BLE001
                    out["effects_pending"] = True
            return out
    # P1-06: validate BEFORE the snapshot, so a rejected report cannot advance the accepted baseline.
    _validate_action_report(s, idx, status=body.status, outcome=body.outcome, path=body.path,
                            note=note_eff)
    kind = _classify_action_report(it0, status=body.status, outcome=body.outcome,
                                   note=note_eff, path=body.path)
    if kind == "unchanged":
        # Business-level duplicate: the user reopened the form and sent the same effective report.
        # Nothing is written - no second outcome effect, no new reported_at, no new Journey event.
        return {"ok": True, "index": idx, "action": it0.model_dump(), "unchanged": True,
                "logged_to_outcome_log": False, "path_event": None}
    _reconcile_pending_report_effects(s, sid)
    it0 = s.diagnosis.day_by_day[idx]
    _snapshot_experience_before(s, persist=False)
    effects = _plan_report_effects(it0, outcome=body.outcome, note=note_eff, path=body.path, kind=kind)
    # H5 + Phase 6.2: the session item is the ACCEPTED-EVENT AUTHORITY. It is mutated and saved STRICTLY
    # first, carrying the derived effects as PENDING data; only then are the outcome log and path
    # counters derived from it. A failed save rolls the item back (503, nothing accepted); a failed
    # effect leaves them pending and recoverable - never a false success, never a duplicate.
    r = _apply_action_report(s, sid, idx, status=body.status, outcome=body.outcome,
                             note=note_eff, path=body.path, operation_id=op, report_sig=sig,
                             persist=False, kind=kind, effects=effects)
    try:
        store.save_strict(s)
    except Exception as exc:  # noqa: BLE001
        _restore_action_item(s, idx, r.get("prev"))
        raise HTTPException(503, detail={
            "code": "REPORT_NOT_DURABLE",
            "message": "Your report could not be saved. Nothing was recorded; please try again."}) from exc
    lg = {"logged_to_outcome_log": False, "path_event": None}
    out_extra: dict = {}
    if r.get("effect_op"):
        try:
            lg = _settle_report_effects(s, sid, idx, r["effect_op"])
        except Exception as exc:  # noqa: BLE001
            _log_reassess_failure(sid, exc)
            out_extra["effects_pending"] = True    # accepted and durable; derived effects will settle
    return {"ok": True, "index": idx, "action": s.diagnosis.day_by_day[idx].model_dump(),
            "correction": kind == "correction",
            "logged_to_outcome_log": lg.get("logged_to_outcome_log", False),
            "path_event": lg.get("path_event"), **out_extra}


def _plan_continuation(s) -> dict:
    """Move-centric continuation (first slice): where the person stands after reporting on the work, and
    what - if anything - the CANONICAL authorities say comes next. Read-only: no synthesis, no checkpoint,
    no route is born, nothing is written. Two kinds of "next" are kept apart on purpose:
      ROUTE_FRONTIER - the canonical route/dependency selector already names the next piece of work;
      CANDIDATE      - the deterministic planner's read; NOT authorized, shown as information needed only.
    No Move is invented: when neither says anything, the state is NOTHING_AUTHORIZED and says why."""
    from app import checkpoints as _cp
    cur = _cp.latest(s)
    plan = (_cp.plan_record(s) or {}).get("current") or {}
    counts = plan.get("counts") or {}
    report = plan.get("report")
    out: dict = {
        "checkpoint_id": (cur or {}).get("checkpoint_id"),
        "plan": {"total": counts.get("total", 0), "done": counts.get("done", 0),
                 "skipped": counts.get("skipped", 0), "blocked": counts.get("blocked", 0),
                 "executed_all": bool(counts.get("executed_all")), "complete": bool(counts.get("complete"))},
        "outcome": report, "next": None}
    frontier = None
    try:
        payload, _deg = _read_only_route_payload(s)
        nm = (payload or {}).get("next_move") or {}
        if nm.get("output") == "ACTION":
            frontier = {"authority": "ROUTE_FRONTIER", "kind": "ACTION", "route_id": nm.get("route_id"),
                        "frontier_ref": nm.get("frontier_ref"), "authorized": True}
        elif nm.get("output") in ("QUESTION", "EVIDENCE_REQUEST"):
            out["route_needs"] = {"kind": nm.get("output"), "route_id": nm.get("route_id"),
                                  "frontier_ref": nm.get("frontier_ref")}
    except Exception:  # noqa: BLE001 - continuation is a read; it never fails the accepted report
        pass
    cand = None
    try:
        n = navigate_session(s, asked_from=(s.planner_log[:-1] if s.planner_log else None))
        cand = {"authority": "CANDIDATE", "kind": n.decision.get("kind"),
                "headline": (n.rendered or {}).get("headline"), "text": (n.rendered or {}).get("text"),
                "focus": n.decision.get("focus"), "authorized": False}
    except Exception:  # noqa: BLE001
        pass
    # Phase 7: the CANONICAL Move ledger comes first. If an authorized Move is executable, that IS
    # the next work - no checkpoint, no reassessment, no route sleight of hand. When no Move is
    # executable, this names the real condition instead of inventing one.
    try:
        mobj = _moves_overview(s)
        out["moves"] = {"current_move_id": mobj["current_move_id"],
                        "frontier": mobj["frontier"], "total": len(mobj["moves"])}
        f = mobj["frontier"] or {}
        if f.get("kind") == "MOVE_ACTIONABLE":
            out["next"], out["state"] = {"authority": "CANONICAL_MOVE", "kind": "MOVE_ACTIONABLE",
                                         "move_id": f.get("move_id"), "authorized": True,
                                         "actions_open": f.get("actions_open"),
                                         "actions_total": f.get("actions_total")}, "NEXT_MOVE_AVAILABLE"
            return out
        if f.get("kind") == "MOVE_EXECUTED_RESULT_PENDING":
            out["next"], out["state"] = {"authority": "CANONICAL_MOVE",
                                         "kind": "MOVE_EXECUTED_RESULT_PENDING",
                                         "move_id": f.get("move_id"), "authorized": False}, "RESULT_PENDING"
            return out
    except Exception:  # noqa: BLE001 - continuation is a read; it never fails an accepted report
        pass
    if frontier:
        out["next"], out["state"] = frontier, "NEXT_MOVE_AVAILABLE"
    elif cand and cand["kind"] in ("QUESTION", "EVIDENCE_REQUEST"):
        out["next"], out["state"] = cand, "NEEDS_INFORMATION"
    else:
        out["next"], out["state"] = cand, "NOTHING_AUTHORIZED"
    return out


@app.get("/session/{sid}/continuation")
def plan_continuation(sid: str):
    """Read-only: where the work stands and what the canonical authorities say comes next."""
    s = store.get(sid)
    if not s:
        raise HTTPException(404, "session not found")
    if not getattr(s, "diagnosis", None):
        raise HTTPException(409, "diagnosis belum ada - finalize dulu")
    return {"session_id": s.id, "continuation": _plan_continuation(s)}


class PlanReport(BaseModel):
    """ONE outcome for the whole set of actions of the current plan (move-centric). The per-action report
    stays for execution details; the business result belongs to the work as a whole."""
    outcome: Literal["moved", "not_moved", "regret", "confounded"] | None = None
    # None = not provided; "" together with an outcome = deliberately emptied (same rule as an action report)
    note: str | None = None
    path: str = ""
    operation_id: str = ""
    checkpoint_id: str = ""


@app.post("/session/{sid}/plan/report")
def plan_report(sid: str, body: PlanReport):
    """Record what happened as a result of the plan's work. Same business semantics as an action report
    (retry replays, identical resubmission is unchanged, a change is a correction with history, an archived
    plan is read-only), same durable order (session first, derived path effect
    after, pending-and-retryable)."""
    s = store.get(sid)
    if not s:
        raise HTTPException(404, "session not found")
    d = getattr(s, "diagnosis", None)
    if not d:
        raise HTTPException(409, "diagnosis belum ada - finalize dulu")
    from app import checkpoints as _cp_mod
    cur_cp = _cp_mod.latest(s)
    if body.checkpoint_id and cur_cp and body.checkpoint_id != cur_cp.get("checkpoint_id"):
        raise HTTPException(409, detail={
            "code": "HISTORICAL_ACTION_READ_ONLY",
            "message": ("That work belongs to an earlier plan that a newer assessment replaced. It stays in "
                        "your history and nothing in your current plan was changed."),
            "current_checkpoint_id": cur_cp.get("checkpoint_id")})
    note = body.note if (body.note or (body.outcome is not None and body.note is not None)) else None
    if body.outcome is None and not (note or "").strip():
        raise HTTPException(422, "an outcome or a note is required")
    if body.outcome is not None and body.path:
        _require_known_path(s, body.path)
    op = (body.operation_id or "").strip()
    sig = _action_report_sig(None, body.outcome, note, body.path)
    prev = dict(getattr(d, "plan_report", None) or {})
    if op:
        hit = next((o for o in (prev.get("ops") or []) if o.get("op") == op), None)
        if hit is not None:
            if hit.get("sig") != sig:
                raise HTTPException(409, detail={
                    "code": "OPERATION_PAYLOAD_MISMATCH",
                    "message": "This operation id was already accepted for a different report."})
            if prev.get("effects") == "pending":
                try:
                    _settle_report_effects(s, sid, -1, str(prev.get("last_op")))
                except Exception:  # noqa: BLE001
                    pass
            return {"ok": True, "replayed": True, "plan_report": _cp_mod._plan_report_view(d.plan_report),
                    "continuation": _plan_continuation(s)}
    p_out, p_note, p_path = prev.get("outcome") or "", prev.get("note") or "", prev.get("path") or ""
    outcome_same = body.outcome is None or body.outcome == p_out
    note_same = note is None or note == p_note
    path_same = (not body.path) or body.outcome is None or body.path == p_path
    if (prev.get("outcome") or prev.get("note")) and outcome_same and note_same and path_same:
        return {"ok": True, "unchanged": True, "plan_report": _cp_mod._plan_report_view(prev),
                "continuation": _plan_continuation(s)}
    _reconcile_pending_report_effects(s, sid)
    prev = dict(getattr(s.diagnosis, "plan_report", None) or {})
    correction = bool(prev.get("outcome") or prev.get("note"))
    now = int(time.time())
    eff = None
    new_outcome = body.outcome if body.outcome is not None else (prev.get("outcome") or "")
    new_path = body.path or (p_path if new_outcome == p_out else "")
    if body.outcome is not None and (not correction or body.outcome != p_out or new_path != p_path):
        eff = {"outcome": body.outcome, "note": p_note if note is None else note, "path": new_path,
               "iid": "", "prev_outcome": p_out if correction else "",
               "prev_path": p_path if correction else "", "corrects": ""}
    row = {"outcome": new_outcome, "note": p_note if note is None else note, "path": new_path,
           "reported_at": now, "revisions": list(prev.get("revisions") or []),
           "ops": list(prev.get("ops") or [])[-9:]}
    if correction:
        row["revisions"] = (row["revisions"] + [{"outcome": p_out, "note": p_note, "path": p_path,
                                                 "reported_at": prev.get("reported_at"),
                                                 "superseded_at": now, "op": op or None}])[-20:]
    row_op = op or f"fx-{uuid.uuid4().hex[:12]}"
    row["ops"].append({"op": row_op, "sig": sig, "ts": now})
    row["last_op"] = row_op
    if eff:
        row["effects"], row["eff"] = "pending", eff
    _snapshot_experience_before(s, persist=False)
    old_report = s.diagnosis.plan_report
    s.diagnosis.plan_report = row
    try:
        store.save_strict(s)
    except Exception as exc:  # noqa: BLE001
        s.diagnosis.plan_report = old_report
        raise HTTPException(503, detail={
            "code": "REPORT_NOT_DURABLE",
            "message": "Your report could not be saved. Nothing was recorded; please try again."}) from exc
    extra: dict = {}
    if eff:
        try:
            _settle_report_effects(s, sid, -1, row_op)
        except Exception as exc:  # noqa: BLE001
            _log_reassess_failure(sid, exc)
            extra["effects_pending"] = True
    return {"ok": True, "correction": correction,
            "plan_report": _cp_mod._plan_report_view(s.diagnosis.plan_report),
            "continuation": _plan_continuation(s), **extra}


def _maps_paths_ctx(paths: list[dict]) -> dict[str, dict]:
    """Path display context (from the diagnosis) for projection — the same STOP rules
    as the VM: lifecycle STOPPED/PAUSED = stopped by the user; a STOP status with
    an open lifecycle = by evidence. Pure read, no new evaluation (K13)."""
    ctx: dict[str, dict] = {}
    for p in paths or []:
        if not p.get("path_id"):
            continue
        ctx[p["path_id"]] = {
            "title": p.get("title") or p["path_id"],
            "lifecycle": p.get("lifecycle") or "OPEN",
            "status": p.get("status") or "OPEN",
            "goal_relation": p.get("goal_relation"),
            "goal_relation_note": p.get("goal_relation_note") or "",
        }
    return ctx


def _maps_projection_for(s, paths: list[dict], routes: list[dict]) -> dict | None:
    """R2 (MAP-06 Rebuild View): the canonical Maps projection from the route payload +
    path context — int 03. Purely derived; loud failures on malformed payloads are allowed
    to propagate (ProjectionIntegrityError = the route payload is truly broken, not an empty
    500). The Goal landmark carries identity (goal_id/version); display metric/horizon stay
    owned by the diagnosis snapshot (K2 — assessed separately from the route)."""
    if not paths:
        return None
    goal = dict(getattr(s, "goal", None) or {})
    goal.setdefault("text", getattr(s, "goal_text", "") or "")
    proj = project_maps(routes, _maps_paths_ctx(paths), goal=goal)
    # Phase 7: the canonical Moves ride WITH the map projection, so Maps and Moves read the SAME
    # move_id/action_id rows from one payload. A Move is attached to a path only through its declared
    # linked_path_id; the renderer never infers membership from a title or a position.
    try:
        overview = _moves_overview(s)
        proj["moves"] = overview["moves"]
        proj["current_move_id"] = overview["current_move_id"]
        proj["move_frontier"] = overview["frontier"]
    except Exception:  # noqa: BLE001 - a Move projection fault never breaks the map's routes
        proj["moves"] = []
        proj["current_move_id"] = None
        proj["move_frontier"] = {"kind": "UNAVAILABLE", "move_id": None}
    return proj


def _compose_routes(s) -> dict:
    """Route composition for one session (used by the POST /routes and /explain endpoints).

    Routes are NOT born from the whole template library: they are composed from the Possible Paths that
    survived the diagnosis (internal-docs §Route Composition) — only templates that are
    a path's substrate (`route_substrate.template_ids`). Runs the Session Runtime Bridge: lifecycle
    first, then compose (re-projection when routes exist). WRITES lineage rows (append-only) when a
    new route is born. No diagnosis/LLM here; NextMove = selector v1 (D6), only over route paths not
    in STOP status.

    An anonymous session (empty user_id) -> no route + a reason (not a 500): routes live in the
    per-user workspace. No Possible Path yet (no diagnosis, or zero paths) -> no route + a reason:
    zero paths is a legitimate state, routes are not invented. Every EXISTING route is returned
    (exists != surfaced, INV-R17) — display decisions belong to the UI (X1)."""
    if not s.user_id:
        return {"session_id": s.id, "user_id": None, "routes": [],
                "not_born": [], "next_move": None, "maps_projection": None,
                "reason": "session anonim — route hidup di workspace per-user; "
                          "buat session dengan user_id untuk mendapat route"}
    paths = ((getattr(s.diagnosis, "possible_paths", None) or {}).get("paths") or []) if s.diagnosis else []
    if s.diagnosis and is_legacy(getattr(s.diagnosis, "possible_paths", None)):
        return {"session_id": s.id, "user_id": s.user_id, "routes": [], "not_born": [], "next_move": None,
                "maps_projection": None,
                "navigation": s.diagnosis.navigation,
                "reason": "artefak ini lebih tua dari skema navigasi saat ini — diagnosis ulang diperlukan; "
                          "tidak ada route yang dikarang dari artefak lama"}
    if not paths:
        return {"session_id": s.id, "user_id": s.user_id, "routes": [], "not_born": [], "next_move": None,
                "maps_projection": None,
                "reason": "belum ada Possible Path — route dikomposisikan dari path yang bertahan"}
    # ONE path -> route pipeline for paths from BOTH the declared strategy and Candidate Possibility
    # (internal-docs §23.5): `compose_path_routes` does not distinguish path origin. It is
    # used in common by
    # the conversation loop (`app/navigation.py`, M4) so route/readiness/planner read the same reality.
    composed = compose_routes_for_paths(s, paths)
    out = {"session_id": s.id, "user_id": s.user_id, "reality": _reality(s), **composed}
    # R2: the canonical projection (int 03) rides along in the payload — the single source for the
    # 2D/3D v2 renderer (flag `maps_projection_v2`, default OFF). No extra write of any kind.
    out["maps_projection"] = _maps_projection_for(s, paths, composed.get("routes") or [])
    return out


@app.post("/session/{sid}/routes")
def session_routes(sid: str):
    """D7 (int 08 §8.4) — Route Navigation for this session."""
    s = store.get(sid)
    if not s:
        raise HTTPException(404, f"session '{sid}' tidak ditemukan")
    _snapshot_experience_before(s, persist=False)   # P1-06: commit only with a successful compose
    try:
        out = _compose_routes(s)
        out.setdefault("reality", _reality(s))
        store.save(s)   # persist the accepted composition + the pre-mutation snapshot baseline
        return out
    except ValueError as exc:  # invalid identity/strategy — not a 500
        raise HTTPException(400, str(exc)) from exc


@app.get("/session/{sid}/routes")
def session_routes_read(sid: str):
    """MAP-06 Rebuild View: a READ-ONLY re-projection of existing lineage. Never gives
    birth to routes, never writes, never calls the LLM; when no route exists the answer is an
    honest empty (not a silent composition). POST /routes remains the first-composition path."""
    s = store.get(sid)
    if not s:
        raise HTTPException(404, f"session '{sid}' tidak ditemukan")
    payload, degraded = _read_only_route_payload(s)
    out = dict(payload)
    out["read_only"] = True
    out.setdefault("reality", _reality(s))
    if degraded:
        out["degraded_sources"] = degraded
    return out


@app.get("/session/{sid}/readiness")
def readiness(sid: str):
    """Adjudicated readiness projection for screen 18 — the final state per path.

    Route requirements and path gates pointing at the same requirement are merged
    HERE, not in the UI: a definite state beats an unchecked one, and UNKNOWN stays
    UNKNOWN (absence of evidence is not evidence of absence). The deterministic
    narrative fallback rides in the projection; UI and LLM both read THIS projection
    (internal-docs §10)."""
    s = store.get(sid)
    if not s:
        raise HTTPException(404, "session not found")
    if not s.diagnosis:
        raise HTTPException(409, "diagnosis belum ada")
    return {**_readiness_projection(s), "reality": _reality(s)}


class NodeExecution(BaseModel):
    event: Literal["EXECUTED", "ABANDONED", "RESET"]
    # D-10: client operation key — a retry after timeout with the same key = the same result,
    # without a duplicate ledger row; the same key with a different payload = a deterministic 409.
    operation_id: str = ""


@app.post("/session/{sid}/routes/{route_id}/nodes/{node_id}/execution")
def route_node_execution(sid: str, route_id: str, node_id: str, body: NodeExecution):
    """Record the EXECUTION EVENT of one route node (int 08 §3.4 execution_view).

    Only writes the `route_execution` ledger (append-only, per-user). Does NOT
    change satisfaction: "done" is not evidence (INV-R8) — the node moves to
    VERIFY, dependents stay closed. The node must exist in a route owned by this
    session's user; EXECUTED/ABANDONED only for nodes currently on the EXECUTE
    frontier, RESET only for nodes already reported."""
    s = store.get(sid)
    if not s:
        raise HTTPException(404, f"session '{sid}' tidak ditemukan")
    if not s.user_id:
        raise HTTPException(409, "session anonim — route hidup di workspace per-user")
    # D-10: idempotent replay BEFORE the frontier/context guards — a retry after timeout must
    # return the same result, not a 409 "already reported" or a duplicate ledger row.
    _op = (body.operation_id or "").strip()
    if _op:
        _prior = route_execution.find_by_operation(s.user_id, _op)
        if _prior is not None:
            if not (_prior.get("route_id") == route_id and _prior.get("node_id") == node_id
                    and _prior.get("event") == body.event):
                raise HTTPException(409, f"operation_id {_op!r} dipakai ulang dengan payload berbeda")
            return {"ok": True, "replayed": True, "event": _prior}
    from ontology.route.compose import frontier_for
    row = None
    for r in route_lineages.list_rows(s.user_id):
        if r["lineage"].get("route_id") == route_id:
            row = r  # the last row wins
    if row is None:
        raise HTTPException(404, f"route '{route_id}' tidak ditemukan untuk user ini")
    lin = row["lineage"]
    # R1-remediation Probe B (17 Oct) — context MEMBERSHIP guard: the route comes from
    # a reconciliation_key with a context_id (the business goal_id). A calling session
    # with a different context is REJECTED even when strategy & applies_when match — two
    # businesses owned by the same user must not execute each other's routes. Legacy
    # (keys without context_id) = a None context: treated as shared as before
    # (historical compatibility, old data not blocked).
    _caller_goal = (getattr(s, "goal", None) or {}).get("goal_id") or None
    _route_ctx = (lin.get("reconciliation_key") or {}).get("context_id")
    if _route_ctx is not None and _route_ctx != _caller_goal:
        raise HTTPException(409, f"route '{route_id}' milik konteks bisnis lain — "
                                 "eksekusi lintas konteks bisnis ditolak (R1 remediasi Probe B)")
    # R1 guard — Probe C (internal-docs
    # 02-contract-reconciliation.md §2): a route may only be executed from a session
    # whose OWN applicability APPLIES. Re-evaluate the template's applies_when against
    # the CALLING SESSION's evidence — the same predicate + is_gap filter as the
    # composer (compose.py T2), pure read, WITHOUT writing lineage. Without this,
    # a node from another business context could execute across Goals just
    # because the lineage lives in the same user's workspace.
    from core.stages.rule_predicates import evaluate_predicate
    from ontology.route.strategies import active_template_library
    _strat = (lin.get("reconciliation_key") or {}).get("strategy_id")
    _tpl = next((t for t in active_template_library() if t.get("strategy_id") == _strat), None)
    _aw = (_tpl or {}).get("applies_when") or {}
    _ev = [e for e in (s.evidence or []) if not getattr(e, "is_gap", False)]
    _applies = False
    if _aw.get("applies"):
        _applies, _ca, _ra = evaluate_predicate(
            {"any_of": _aw["applies"]}, _ev, "", negation_aware=True)
    _not_app = False
    if _aw.get("not_applicable"):
        _not_app, _cn, _rn = evaluate_predicate(
            {"any_of": _aw["not_applicable"]}, _ev, "", negation_aware=True)
    if not (_applies and not _not_app):
        raise HTTPException(409, f"route '{route_id}' tidak applicable di konteks sesi ini — "
                                 "eksekusi lintas konteks/Goal ditolak (R1 guard)")
    nodes = lin["revisions"][-1]["nodes"]
    node = next((n for n in nodes if n["node_id"] == node_id), None)
    if node is None:
        raise HTTPException(404, f"node '{node_id}' tidak ada di route ini")
    _views = route_execution.latest_views(s.user_id, route_ids={route_id})
    cur = (_views.get(node_id) or {}).get("view", "NOT_STARTED")
    if body.event == "RESET":
        if cur == "NOT_STARTED":
            raise HTTPException(409, "node belum dilaporkan — tak ada yang di-reset")
    else:
        live_nodes = [{**n, "execution_view": cur if n["node_id"] == node_id else n.get("execution_view")}
                      for n in nodes]
        in_execute = any(e["kind"] == "EXECUTE" and e.get("node") == node_id
                         for e in frontier_for(route_id, lin["applicability"]["status"], live_nodes)
                         ) if lin.get("lineage_status") == "OPEN" else False
        if not in_execute:
            raise HTTPException(409, "node ini tidak sedang di frontier EXECUTE "
                                     "(sudah dilaporkan, belum terbuka, atau route tertutup)")
    _snapshot_experience_before(s, persist=False)   # P1-06: commit only with a successful record
    ev = route_execution.record(s.user_id, route_id, node_id, body.event, session_id=sid, op_id=_op)
    store.save(s)   # persist the pre-mutation snapshot baseline with the accepted execution
    return {"ok": True, "event": ev}


def _goal_measured_of(s) -> dict | None:
    """This session's Goal measured value from WORKSPACE measurements (current evaluation, comparable
    only), or None when no valid measurement exists yet. The UI uses it for the 'now' of a non-revenue
    Goal so STATE/JOURNEY don't claim 'not yet measured' when the workspace already holds a measurement
    (missing != zero still applies: without a valid measurement the result is None, not 0)."""
    gid = (s.goal or {}).get("goal_id")
    if not s.user_id or not gid:
        return None
    try:
        ev = workspace_goals.evaluate_from_measurements(s.user_id, gid)
    except Exception:
        return None
    vals = ev.get("values") or {}
    for key in ("counted", "rate", "current"):
        if vals.get(key) is not None:
            return {"value": vals[key], "kind": key, "status": ev.get("status"),
                    "basis": "workspace_measurements",
                    "goal_version": (ev.get("evaluation_basis") or {}).get("goal_version"),
                    "as_of_ts": (ev.get("evaluation_basis") or {}).get("as_of_ts")}
    return None


def _goal_series_of(s) -> dict | None:
    """Observation series of this session's ACTIVE Goal (its own metric + unit) from comparable workspace
    evidence. None for a revenue Goal (JOURNEY uses income check-ins) or when the Goal isn't in the
    workspace yet. Carried in the same state payload as `goal_measured`: the series and current value
    can't belong to different Goals."""
    gid = (s.goal or {}).get("goal_id")
    if not s.user_id or not gid:
        return None
    try:
        cur = workspace_goals.current_goal(s.user_id, gid)
        if cur is None:
            return None
        comparable, excluded = workspace_goals.split_comparable_measurements(s.user_id, gid)
        series = goal_series(cur, comparable)
    except Exception:
        return None
    if series is not None:
        series["excluded_incomparable"] = len(excluded)
    return series


@app.get("/session/{sid}/state")
def session_state(sid: str):
    """Probe the session state WITHOUT a 409 (P0-3): the client needs existence + linkage
    info on restore/load without triggering network console errors."""
    s = store.get(sid)
    if not s:
        raise HTTPException(404, "session not found")
    prior = store.get(s.prior_session_id) if s.prior_session_id else None
    # journey_ok = the EXACT success condition of the journey endpoint (avoid client probe 409s)
    journey_ok = bool(s.journey_delta) or bool(
        s.prior_session_id and s.diagnosis and prior and prior.diagnosis
    )
    # goal_text is included: a Revenue Navigation Map's name = the GOAL, not a fragment of
    # where_you_are (the "one map per goal" doctrine — internal-docs §7).
    return {
        "session_id": s.id,
        "goal_text": s.goal_text,
        "goal": s.goal,
        "goal_measured": _goal_measured_of(s),
        "goal_series": _goal_series_of(s),
        "created_ts": s.created_ts,
        "user_id": s.user_id or "",
        "has_prior": bool(s.prior_session_id),
        "interview_done": bool(s.interview_done),
        "has_diagnosis": bool(s.diagnosis),
        "journey_ok": journey_ok,
        "reality": _reality(s),
    }


@app.get("/session/{sid}/progress")
def session_progress(sid: str):
    """E5: the synthesis stage currently running (for the UI). Lightweight polling.

    `active=false` means no synthesis is running — including after completion
    or failure (the map is cleared in _diagnose's finally block).
    """
    p = _PROGRESS.get(sid)
    if not p:
        return {"active": False, "stage": None, "label": None}
    return {
        "active": True,
        "stage": p["stage"],
        "label": p["label"],
        "index": p["index"],
        "age": round(time.time() - p["ts"], 1),
    }


@app.get("/session/{sid}/evidence")
def session_evidence(sid: str):
    """B (23 Sep 2026): map context recovery — transcript + ledger + intent tags.

    Previously loadMap only restored the diagnosis: chat was emptied and the
    tags/ledger panels stayed placeholders — while the copy claimed otherwise
    (audit-verified: tagsLen=32, ledgerLen=7, diagLen=24286).
    Read-only endpoint; the transcript already lives in the store (not a reconstruction).
    """
    s = store.get(sid)
    if not s:
        raise HTTPException(404, "session not found")
    return {
        "session_id": s.id,
        "goal_text": s.goal_text,
        "transcript": [{"role": r, "text": t} for r, t in s.transcript],
        "evidence": [e.model_dump() for e in s.evidence],
        "intent_tags": list(s.intent_tags),
    }


# ── Durable check-in (V4 audit D-02) ────────────────────────────────────────
# Progress/history live on the SERVER, not localStorage. Unreported numbers = None,
# never coerced to 0; a reported 0 stays 0 (0 != unknown). One check-in = one append-only
# row per user + goal_id scope; idempotent per operation_id. A check-in is a progress
# EVENT, NOT proof of requirement satisfaction (adjudication remains the only credit path).

class CheckInBody(BaseModel):
    outcome: Literal["worked", "mixed", "none"]
    cycle: int | None = None
    day: int | None = None
    contacted: float | str | None = None
    replies: float | str | None = None
    calls: float | str | None = None
    paid: float | str | None = None
    rp: float | str | None = None
    path: str = ""
    title: str = ""
    note: str = ""
    operation_id: str = ""
    # P0-05: optional action-report fields, applied in the SAME commit as the check-in (one canonical
    # boundary, so the old two-step client flow can no longer half-apply). None = no action report.
    action_index: int | None = None
    action_status: Literal["TODO", "DONE", "SKIPPED", "BLOCKED"] | None = None
    action_outcome: Literal["moved", "not_moved", "regret", "confounded"] | None = None


@app.post("/session/{sid}/checkin")
def session_checkin(sid: str, body: CheckInBody):
    """Persist one durable check-in (D-02). Idempotent per operation_id; 422 when invalid."""
    s = store.get(sid)
    if not s:
        raise HTTPException(404, "session not found")
    if not s.user_id:
        raise HTTPException(409, "session anonim - check-in hidup di workspace per-user")
    op = (body.operation_id or "").strip()
    goal_id = ((s.goal or {}).get("goal_id") or None)
    rec = body.model_dump()
    rec["sid"] = s.id
    # 1. Validate + normalize the COMPLETE logical command BEFORE any mutation: the check-in fields,
    #    then the action fields / index / path. One HTTP request is not a transaction, so nothing may
    #    be written until every part of the command is known to be valid.
    try:
        checkins.normalize(rec, goal_id)
    except checkins.CheckinError as exc:
        raise HTTPException(422, str(exc)) from exc
    if body.action_index is not None:
        _validate_action_report(s, body.action_index, status=body.action_status,
                                outcome=body.action_outcome, path=body.path)
    # 2. Replay: the command already committed. Same key + same command -> prior row; a different
    #    command (INCLUDING action_index/status/outcome) -> 409; the action is never re-applied.
    if op and checkins.find_by_operation(s.user_id, op) is not None:
        try:
            row = checkins.record(s.user_id, rec, goal_id=goal_id, op_id=op)
        except checkins.CheckinConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except checkins.CheckinError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {"ok": True, "replayed": True, "checkin": row, "reality": _reality(s)}
    # 3. Commit: the CHECK-IN is written first (durable), then the action is applied and the session
    #    saved. If the check-in write fails, no action mutation was made at all.
    _snapshot_experience_before(s, persist=False)
    try:
        row = checkins.record(s.user_id, rec, goal_id=goal_id, op_id=op)
    except checkins.CheckinConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except checkins.CheckinError as exc:
        raise HTTPException(422, str(exc)) from exc
    out = {"ok": True, "checkin": row, "reality": _reality(s)}
    if body.action_index is not None:
        it_ck = s.diagnosis.day_by_day[body.action_index]
        kind_ck = _classify_action_report(it_ck, status=body.action_status, outcome=body.action_outcome,
                                          note=(body.note or None), path=body.path)
        if kind_ck == "unchanged":
            # the check-in is a new observation and was recorded above; the ACTION part repeats what is
            # already on record, so it is not applied (and not counted) a second time
            store.save(s)
            out["action"] = it_ck.model_dump()
            out["logged_to_outcome_log"] = False
            out["path_event"] = None
            out["action_unchanged"] = True
            return out
        fx_ck = _plan_report_effects(it_ck, outcome=body.action_outcome, note=(body.note or None),
                                     path=body.path, kind=kind_ck)
        r = _apply_action_report(s, sid, body.action_index, status=body.action_status,
                                 outcome=body.action_outcome, note=(body.note or None), path=body.path,
                                 persist=False, kind=kind_ck, effects=fx_ck)
        store.save(s)   # persist the accepted action (+ pending effects) and the snapshot together
        lg = {"logged_to_outcome_log": False, "path_event": None}
        if r.get("effect_op"):
            try:
                lg = _settle_report_effects(s, sid, body.action_index, r["effect_op"])
            except Exception:  # noqa: BLE001 - derived effects stay pending and settle on the next report
                pass
        out["action"] = s.diagnosis.day_by_day[body.action_index].model_dump()
        out["logged_to_outcome_log"] = lg["logged_to_outcome_log"]
        out["path_event"] = lg["path_event"]
    else:
        store.save(s)   # persist the pre-mutation snapshot baseline with the accepted check-in
    return out


@app.get("/session/{sid}/checkins")
def session_checkins(sid: str):
    """Durable check-in history for this session's business context (D-02). Read-only; rows
    of other goals don't leak (legacy rows without a goal remain readable)."""
    s = store.get(sid)
    if not s:
        raise HTTPException(404, "session not found")
    goal_id = ((s.goal or {}).get("goal_id") or None)
    rows = checkins.latest(s.user_id, goal_id=goal_id) if s.user_id else []
    return {"session_id": s.id, "checkins": rows, "reality": _reality(s)}


@app.get("/session/{sid}/journey")
def journey(sid: str):
    """J3 (internal-docs §7): cross-session journey verdict — deterministic, 0-LLM.

    ADVANCED | REGRESSED | STUCK | PIVOTED (| INSUFFICIENT_DATA when the spectrum
    level is unknown). Recomputed on-demand from the stored diagnoses."""
    s = store.get(sid)
    if not s:
        raise HTTPException(404, "session not found")
    if s.journey_delta:
        return _journey_response(s)
    if not (s.prior_session_id and s.diagnosis):
        raise HTTPException(
            409,
            "sesi tidak punya prior_session_id + diagnosis — buat sesi dengan "
            "prior_session_id lalu finalize",
        )
    prior = store.get(s.prior_session_id)
    if not prior or not prior.diagnosis:
        raise HTTPException(409, "prior session belum punya diagnosis")
    delta = compute_delta(prior.diagnosis, s.diagnosis)
    s.journey_delta = delta
    store.save(s)
    return _journey_response(s)


def _journey_response(s) -> dict:
    """J7-a (internal-docs §7): verdict + reassess status + prior action summary —
    all deterministic from stored data."""
    prior = store.get(s.prior_session_id) if s.prior_session_id else None
    out: dict = {"session_id": s.id, "prior_session_id": s.prior_session_id, "reality": _reality(s),
                 **(s.journey_delta or {})}
    if prior:
        out["reassess"] = reassess_status(prior)
        out["prior_actions"] = prior_action_summary(prior)
    return out


# ── Experience read model (V4 master prompt §4; audit D-04/D-05/D-08) ────────
# One versioned read door for STATE/MAPS/MOVES/JOURNEY/TALK. Purely derived: it never
# writes route lineage, never calls the LLM, never overrides server decisions.

def _current_decision_of(s) -> dict | None:
    """The decision CURRENTLY presented (not the next candidate), read-only — a compact
    counterpart of GET /navigation for TALK/JOURNEY context without recomputing."""
    last = s.planner_log[-1] if getattr(s, "planner_log", None) else None
    if not last:
        return None
    d = last.get("presented") or last.get("decision") or {}
    from app import checkpoints as _cp_cd
    era, cur = _presented_era(s, last), _cp_cd.latest(s)
    return {"kind": d.get("kind"), "intent": d.get("intent"), "focus": d.get("focus"),
            "stop": d.get("stop"), "degraded": bool(d.get("degraded")),
            "headline": (last.get("text") or {}).get("headline"),
            # Phase 6.2: the last PRESENTED turn is history once a newer checkpoint exists. Readers
            # (Talk, Journey) must not describe it as the present recommendation; GET /navigation
            # `current` carries the checkpoint-scoped decision.
            "presented_checkpoint_version": era,
            "presented_is_historical": bool(cur and era is not None and era < int(cur.get("version") or 0)),
            "current_checkpoint_version": (cur or {}).get("version")}


def _read_only_route_payload(s) -> tuple[dict, list[str]]:
    """A READ-ONLY route payload (same shape as POST /routes) that NEVER births a route.

    MAP-06 Rebuild View: only re-projects lineage that ALREADY exists for this session's business
    context. When no route has been born yet, return an honest empty set (paths stay
    route_unavailable) instead of calling the composer, which WRITES new routes as a side effect
    of a GET. Returns (payload, degraded_sources)."""
    paths = ((getattr(s.diagnosis, "possible_paths", None) or {}).get("paths") or []) if s.diagnosis else []
    empty = {"session_id": s.id, "user_id": s.user_id or None, "routes": [], "not_born": [],
             "next_move": None, "projection_status": "not_born",
             "maps_projection": _maps_projection_for(s, paths, []) if paths else None}
    if not s.user_id or not paths:
        out = dict(empty)
        if not s.user_id:
            out["reason"] = "session anonim - route hidup di workspace per-user"
        else:
            out["reason"] = "belum ada Possible Path - route dikomposisikan dari path yang bertahan"
        return out, []
    goal_id = (getattr(s, "goal", None) or {}).get("goal_id") or None
    try:
        rows = route_lineages.list_rows(s.user_id)
    except Exception:  # noqa: BLE001
        rows = []
    has_context = False
    for r in rows:
        lin = r.get("lineage") or {}
        if lin.get("lineage_status") != "OPEN":
            continue
        ctx = (lin.get("reconciliation_key") or {}).get("context_id")
        if ctx is None or ctx == goal_id:
            has_context = True
            break
    if not has_context:
        out = dict(empty)
        out["reason"] = ("belum ada route yang lahir untuk konteks ini - Rebuild View tidak melahirkan "
                         "route; POST /routes melakukan komposisi pertama")
        return out, []
    try:
        # P0-02: pure re-projection. compose_routes_for_paths(read_only=True) NEVER appends a lineage
        # row, so a GET cannot mutate route lineage; existing route ids/revisions/execution survive.
        composed = compose_routes_for_paths(s, paths, read_only=True)
    except Exception as exc:  # noqa: BLE001 — a broken route payload must not sink other readings
        # P1-04: a projection FAILURE is surfaced as degraded, never as an apparently valid empty map.
        out = dict(empty)
        out["projection_status"] = "degraded"
        out["degraded_sources"] = ["route_compose_failed"]
        out["reason"] = f"komposisi route gagal dibaca: {type(exc).__name__}"
        return out, ["route_compose_failed"]
    payload = {"session_id": s.id, "user_id": s.user_id, "reality": _reality(s), **composed}
    payload["maps_projection"] = _maps_projection_for(s, paths, composed.get("routes") or [])
    payload["read_only"] = True
    payload["projection_status"] = "ok" if composed.get("routes") else "not_born"
    return payload, []


def _experience_routes(s) -> tuple[list, dict | None, list[str]]:
    """READ-ONLY route view for Experience (see _read_only_route_payload)."""
    payload, degraded = _read_only_route_payload(s)
    return payload.get("routes") or [], payload.get("maps_projection"), degraded


def _experience_links(s) -> tuple[list, list[str]]:
    """ACCEPTED cross-route relations (A03). Optional module: without the store, the graph stays
    honest (no causal edges) and absent sources are reported, not invented."""
    if not s.user_id:
        return [], []
    try:
        from store import navigation_links
    except Exception:  # noqa: BLE001
        return [], []
    try:
        ctx = (getattr(s, "goal", None) or {}).get("goal_id") or None
        return navigation_links.latest_links(s.user_id, context_id=ctx), []
    except Exception:  # noqa: BLE001
        return [], ["navigation_links"]


def _experience_timeline(s) -> tuple[dict | None, list[str]]:
    try:
        from app import experience_journey
    except Exception:  # noqa: BLE001
        return None, []
    try:
        return experience_journey.build_timeline(s), []
    except Exception:  # noqa: BLE001
        return None, ["journey_timeline"]


def _snapshot_experience_before(s, *, persist: bool = True) -> bool:
    """Record the CURRENT projection snapshot at an ACCEPTED-MUTATION boundary, so a later
    GET /experience can explain what that mutation changed (P0-03). This is the only place a
    projection snapshot is written; a read never writes.

    P1-06: a REJECTED or failed operation must not advance the accepted baseline. Callers that can
    still fail pass persist=False and save the session only after their commit succeeds; best effort
    otherwise (a failure never blocks the mutation)."""
    try:
        from app import experience_contract as _ec
        routes, proj, _ = _experience_routes(s)
        links, _ = _experience_links(s)
        graph = _ec.build_graph(s, proj, links=links)
        rev = _ec.reality_revision(s, graph=graph)
        _ec.record_experience_snapshot(s, {"revision": rev, "graph": graph})
        if persist:
            store.save(s)
        return True
    except Exception:  # noqa: BLE001
        return False


@app.get("/session/{sid}/experience")
def session_experience(sid: str):
    """The versioned ExperienceReadModel (V4 §4). Combines the composite reality revision,
    checkpoint, paths + the MAPS projection, route instances (0..N per path), canonical Moves,
    a typed graph + change_set, and the JOURNEY timeline of the same session. Read-only."""
    s = store.get(sid)
    if not s:
        raise HTTPException(404, "session not found")
    from app import experience_contract as _ec
    routes, maps_projection, degraded = _experience_routes(s)
    links, d_links = _experience_links(s)
    timeline, d_timeline = _experience_timeline(s)
    degraded = degraded + d_links + d_timeline
    state = {
        "goal_text": s.goal_text, "goal": s.goal, "has_diagnosis": bool(s.diagnosis),
        "interview_done": bool(s.interview_done), "goal_measured": _goal_measured_of(s),
        "transcript_turns": len(s.transcript), "current_decision": _current_decision_of(s),
    }
    exp = _ec.build_experience(s, routes=routes, maps_projection=maps_projection, links=links,
                               timeline=timeline, state=state, degraded_sources=degraded)
    # P1-04: name the route projection status explicitly, so "empty" is distinguishable from "failed".
    exp["integrity"]["route_projection_status"] = (
        "degraded" if "route_compose_failed" in degraded else ("ok" if routes else "not_born"))
    # NC-R5 (Phase 6.1): the recorded plan, versioned. `current` is the plan the latest checkpoint
    # carries plus the reports accepted against it; `superseded` are the plan versions a reassessment
    # replaced, archived with their own status/outcome. A read-only projection — never a second store.
    from app import checkpoints as _cp_plan
    exp["plan"] = _cp_plan.plan_record(s)
    # P0-03: a READ never writes. Projection snapshots are recorded at accepted-mutation boundaries
    # (_snapshot_experience_before); this GET only diffs against the last recorded one.
    return exp


@app.get("/session/{sid}/reevaluate-preview")
def reevaluate_preview(sid: str):
    """MAP-06 Re-evaluate Preview (C08/D-11): NON-mutating, deterministic, no LLM.

    Shows what has changed since the last checkpoint, what a re-evaluation would supersede, and —
    since Phase 6.1 (NC-R2) — the AUTHORITATIVE eligibility. It writes nothing, births no route and
    runs no synthesis; committing a re-evaluation stays an explicit user action (POST /reassess or
    /finalize). Cheap refresh and expensive synthesis are deliberately different calls (V4 4.2).

    material_change alone is NOT permission to mutate: `eligibility` is the server's decision, and
    POST /reassess rechecks it — plus the revision the user actually approved — before synthesizing."""
    s = store.get(sid)
    if not s:
        raise HTTPException(404, "session not found")
    return _reassess_preview(s)

@app.get("/session/{sid}/timeline")
def session_timeline(sid: str):
    """The canonical JOURNEY timeline of the SAME session (D-08): even a first session's events
    are readable, without requiring prior_session_id. Deterministic 0-LLM, from the durable ledger."""
    s = store.get(sid)
    if not s:
        raise HTTPException(404, "session not found")
    timeline, degraded = _experience_timeline(s)
    if timeline is None:
        raise HTTPException(503, "timeline proyeksi tidak tersedia")
    out = dict(timeline)
    out["reality"] = _reality(s)
    if degraded:
        out["degraded_sources"] = degraded
    return out


# ── Goal-Relative workspace endpoints (int 09 §4.4; Phase 3) ─────────────────

class GoalRevision(BaseModel):
    """Goal revision — a material change = a GOAL_REVISED event (version +1, GR-20)."""
    target: float | None = None
    target_min: float | None = None
    target_max: float | None = None
    measurement_window_days: int | None = None
    deadline_days: int | None = None
    success_definition: str = ""


class GoalMeasurement(BaseModel):
    """Goal metric measurement — only observed evidence moves the evaluation (GR-22).

    cohort/period (+ optional period bounds): rate-contract metadata. A rate without cohort+period,
    or one that doesn't match the Goal, is STORED but never becomes the basis of attainment or
    trend (measurement_contract.rate_measurement_validity)."""
    kind: Literal["event", "value", "rate", "criteria"]
    value: float | None = None
    event_ts: int | None = None
    event_id: str = ""
    qualified: bool | None = None
    numerator: float | None = None
    denominator: float | None = None
    criterion: str = ""
    met: bool | None = None
    cohort: str = ""
    period: str = ""
    period_start_ts: int | None = None
    period_end_ts: int | None = None


def _goal_or_404(user_id: str, goal_id: str) -> dict:
    g = workspace_goals.current_goal(user_id, goal_id)
    if g is None:
        raise HTTPException(404, f"goal '{goal_id}' tidak ditemukan di workspace user ini")
    return g


@app.get("/workspace/{user_id}/goals")
def workspace_goals_view(user_id: str):
    """The user's Goal collection + active goal + event history (audit GR-20)."""
    try:
        validate_user_id(user_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "user_id": user_id,
        "goals": workspace_goals.goals(user_id),
        "active_goal_id": workspace_goals.active_goal_id(user_id),
        "history": workspace_goals.history(user_id, limit=100),
    }


@app.post("/workspace/{user_id}/goals/{goal_id}/activate")
def workspace_goal_activate(user_id: str, goal_id: str, session_id: str = ""):
    """Switch the workspace Primary Goal (GR-18/GR-27) — ACTIVATION CONTRACT (A-21/A-22):

    - Without `session_id`: workspace-level only. The workspace active goal = the default Goal
      for NEW sessions; a session in progress KEEPS navigating with its own session goal —
      no silent mid-conversation switching.
    - With `session_id`: that explicit session is rebound to this goal (s.goal is loaded from
      the workspace record, goal status/lifecycle still from the event store) so the session's
      navigation, snapshots, and UI share the same context — a VISIBLE switch."""
    _goal_or_404(user_id, goal_id)
    row = workspace_goals.activate_goal(user_id, goal_id)
    rebound: dict = {}
    if session_id:
        s = store.get(session_id)
        if s is None or s.user_id != user_id:
            raise HTTPException(404, f"session '{session_id}' tidak ditemukan untuk user ini")
        cur = workspace_goals.current_goal(user_id, goal_id) or {}
        s.goal = {k: v for k, v in cur.items() if k in Goal.model_fields}
        store.save(s)
        rebound = {"session_id": session_id, "goal": s.goal}
    return {"ok": True, "event": row, "active_goal_id": workspace_goals.active_goal_id(user_id),
            "rebound": rebound}


@app.post("/workspace/{user_id}/goals/{goal_id}/revise")
def workspace_goal_revise(user_id: str, goal_id: str, body: GoalRevision):
    """Revise target/definition — a new version + effective time; history preserved (GR-20)."""
    cur = _goal_or_404(user_id, goal_id)
    revised = dict(cur)
    changed = False
    for k, v in (
        ("target", body.target), ("target_min", body.target_min),
        ("target_max", body.target_max),
        ("measurement_window_days", body.measurement_window_days),
        ("deadline_days", body.deadline_days),
        ("success_definition", body.success_definition or None),
    ):
        if v is not None and revised.get(k) != v:
            revised[k] = v
            changed = True
    if not changed:
        return {"ok": True, "changed": False, "goal": cur}
    if any(v is not None for v in (body.target, body.target_min, body.target_max)):
        # an explicit revision = user input (not parsed): the target origin becomes explicit_input
        revised["target_origin"] = "explicit_input"
    row = workspace_goals.upsert_goal(user_id, revised)
    return {"ok": True, "changed": True, "event": row,
            "goal": workspace_goals.current_goal(user_id, goal_id)}


@app.post("/workspace/{user_id}/goals/{goal_id}/lifecycle")
def workspace_goal_lifecycle(
    user_id: str, goal_id: str, event: Literal["ACHIEVED", "STOPPED", "RESUMED"],
):
    """Per-Goal lifecycle — does not propagate to other Goals (GR-21)."""
    _goal_or_404(user_id, goal_id)
    try:
        row = workspace_goals.lifecycle(user_id, goal_id, f"GOAL_{event}")
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"ok": True, "event": row, "goal": workspace_goals.current_goal(user_id, goal_id)}


@app.post("/workspace/{user_id}/goals/{goal_id}/measurements")
def workspace_goal_measurement(user_id: str, goal_id: str, body: GoalMeasurement):
    """Record an observed measurement → the latest typed evaluation (honest trajectory, GR-22)."""
    _goal_or_404(user_id, goal_id)
    payload = body.model_dump(exclude_none=True)
    if body.kind == "value" and body.value is None:
        raise HTTPException(422, "kind=value butuh field value")
    if body.kind == "rate" and (body.numerator is None or body.denominator is None):
        raise HTTPException(422, "kind=rate butuh numerator dan denominator")
    if body.kind == "event" and body.event_ts is None:
        raise HTTPException(422, "kind=event butuh event_ts (timestamp kejadian)")
    ev = workspace_goals.record_measurement(user_id, goal_id, payload)
    if ev.get("rejected"):
        # the kind doesn't match the Goal's semantics: rejected at the boundary — not recorded,
        # does not move the evaluation
        raise HTTPException(422, {"code": ev["code"], "reason": ev["error"],
                                  "expected_kinds": ev["expected_kinds"], "semantics": ev["semantics"]})
    return {"ok": True, "evaluation": ev,
            "measurements": workspace_goals.measurements(user_id, goal_id)}


@app.get("/workspace/{user_id}/goals/{goal_id}/trajectory")
def workspace_goal_trajectory(user_id: str, goal_id: str, version: int | None = None):
    """The Goal trajectory under its own metric semantics (int 09 §4.4) — split from the
    decision/learning trajectory (GR-23).

    A-16: event/rate/criteria measurements enter the trajectory through the typed evaluator
    (typed_goal_trajectory), not only kind=value as a scalar.

    F-12 (mandate §5): version=N = a HISTORICAL evaluation on Goal definition version N — the
    goal is reconstructed from the event log and only that version's measurements are evaluated.
    Without version: a CURRENT evaluation uses the active version's definition over comparable
    measurements; incomparable ones are reported (excluded_incomparable), never dropped."""
    g = _goal_or_404(user_id, goal_id)
    from domains.revenue.stages.trajectory import goal_trajectory, typed_goal_trajectory

    if version is not None:
        gh = workspace_goals.goal_at_version(user_id, goal_id, version)
        if gh is None:
            raise HTTPException(404, f"versi {version} tidak ditemukan untuk goal ini")
        ms_v = [m for m in workspace_goals.measurements(user_id, goal_id)
                if m.get("goal_version") == version
                and kind_check(gh, m.get("kind", ""))["ok"]]
        end = workspace_goals.version_end_ts(user_id, goal_id, version)
        return {"goal_trajectory": typed_goal_trajectory(gh, ms_v, as_of_ts=end),
                "historical": {"goal_version": version, "target": gh.get("target"),
                               "metric_id": gh.get("metric_id") or gh.get("metric"),
                               "n_measurements": len(ms_v), "as_of_ts": end,
                               "evaluation": workspace_goals.evaluate_from_measurements(
                                   user_id, goal_id, version=version)},
                "decision_trajectory": _decision_traj_safe(user_id)}
    ms, excluded = workspace_goals.split_comparable_measurements(user_id, goal_id)
    if (g.get("metric_id") or "") == "revenue_monthly" or (
            not g.get("metric_id") and g.get("metric") == "revenue_monthly"):
        snaps = []
        if workspace.workspace_exists(user_id):
            d = None  # snapshot path dihidrasi via store workspace
            from store.workspace import _read_jsonl, _user_dir
            d = _user_dir(user_id)
            snaps = _read_jsonl(d / "snapshots.jsonl")
        return {"goal_trajectory": goal_trajectory(g, snaps),
                "decision_trajectory": _decision_traj_safe(user_id)}
    traj = typed_goal_trajectory(g, ms)
    out = {"goal_trajectory": traj, "decision_trajectory": _decision_traj_safe(user_id),
           "evaluation_basis": {"mode": "current", "goal_version": g.get("version", 1),
                                "n_measurements": len(ms)}}
    if excluded:
        out["excluded_incomparable"] = workspace_goals.excluded_summary(excluded)
    return out


def _decision_traj_safe(user_id: str) -> dict | None:
    """Decision/learning trajectory from workspace snapshots (a separate axis, GR-23)."""
    try:
        from domains.revenue.stages.trajectory import decision_trajectory
        from store.workspace import _read_jsonl, _user_dir

        snaps = _read_jsonl(_user_dir(user_id) / "snapshots.jsonl")
        if len(snaps) < 2:
            return None
        return decision_trajectory(snaps)
    except Exception:
        return None


@app.get("/knowledge/confidence")
def knowledge_confidence():
    """P3: the knowledge-confidence overlay from real outcomes + a report summary."""
    return {
        "confidence_items": nba_store.load_confidence(),
        "recalc": nba_store.recalc(),
        "reports": nba_store.summary(),
    }


@app.get("/funnel/stats")
def funnel_stats():
    """Cross-session summary: spectrum/primary-decision distribution + coverage."""
    return funnel.summary()


# ── Business Assistant (7th UI tab) — free Q&A grounded in the artifact ──────
class CopilotAsk(BaseModel):
    question: str
    session_id: str = ""



def _copilot_context(s) -> str:
    """Copilot grounding context — truncated when too long (token thrift).

    Goal-Relative (int 09 §6 TALK): the STRUCTURED Goal + readiness + evaluation context are
    grounded too — the TALK narrative must not claim metrics/readiness that don't exist."""
    if not s:
        return "KONTEKS: belum ada sesi aktif — belum ada goal, evidence, maupun diagnosis."
    lines = [f"GOAL: {s.goal_text}"]
    g = s.goal or {}
    if g:
        from domains.revenue.schema.goal import Goal
        from domains.revenue.schema.goal_evaluation import goal_readiness

        gobj = Goal(**{k: v for k, v in g.items() if k in Goal.model_fields})
        rd = goal_readiness(gobj)
        mdef = gobj.metric_definition() or {}
        lines.append(
            "GOAL TERSTRUKTUR (otoritas engine — jangan mengarang di luar ini): "
            + json.dumps({
                "goal_id": g.get("goal_id", ""),
                "metric_id": gobj.resolved_metric_id(),
                "metric_name": (mdef.get("display_name") or {}).get("en"),
                "direction": gobj.direction,
                "unit": gobj.unit,
                "target": gobj.target,
                "measurement_window_days": gobj.measurement_window_days,
                "deadline_days": gobj.deadline_days,
                "readiness": {"ready": rd["ready"], "blocking": rd["blocking"]},
                "target_confirmed": gobj.confirmed_target(),
            }, ensure_ascii=False, default=str)
        )
    if s.evidence:
        rows = [f"- [{e.level}] {e.signal}" for e in s.evidence[:40]]
        lines.append("EVIDENCE LEDGER:\n" + "\n".join(rows))
    d = s.diagnosis
    if d:
        slim = {
            "where_you_are": d.where_you_are,
            "primary_constraint_id": d.primary_constraint_id,
            "primary_constraint": d.primary_constraint,
            "secondary_constraints": d.secondary_constraints,
            "why": d.why,
            "do_not": d.do_not,
            "next_best_action": d.next_best_action,
            "first_step_today": d.first_step_today,
            "success_metric": d.success_metric,
            "day_by_day": d.day_by_day,
            "well_know_when": d.well_know_when,
            "reassess_window_days": d.reassess_window_days,
            "pivot_rule": d.pivot_rule,
            "confidence": d.confidence,
            "confidence_band": d.confidence_band,
            "decision_spectrum": d.decision_spectrum,
            "revenue_state": d.revenue_state,
            "possible_paths": d.possible_paths,
            "metrics": d.metrics,
        }
        lines.append("DIAGNOSIS:\n" + json.dumps(slim, ensure_ascii=False, default=str)[:8000])
    else:
        lines.append("DIAGNOSIS: belum ada — interview belum di-finalize.")
    tail = s.transcript_tail()
    if tail:
        lines.append(
            "TRANSKRIP TERAKHIR:\n"
            + "\n".join(f"{r}: {t}" for r, t in tail[-8:])
        )
    return "\n\n".join(lines)


@app.post("/copilot")
def copilot(body: CopilotAsk):
    """Business Assistant — free-text answers grounded in the session artifact.

    Deliberately separate from POST /session/{id}/message: that endpoint drives the
    conversation state loop (evidence/state/planner), not free conversation.
    """
    q = body.question.strip()
    if not q:
        raise HTTPException(400, "pertanyaan kosong")
    s = store.get(body.session_id) if body.session_id else None
    llm = get_llm()
    if s:
        llm.use_session(s.id)   # the Go gateway needs a session id (see /message)
    ctx = _copilot_context(s)
    grounded = "diagnosis" if (s and s.diagnosis) else "none"

    # mock: raw_json answers with a placeholder diagnosis JSON — never shown to the user.
    if getattr(llm, "name", "") == "mock":
        head = ctx.split("\n\n")[0]
        return {
            "answer": "(mode mock — engine LLM belum aktif; ini ringkasannya)\n" + head,
            "grounded_on": grounded,
            "session_id": body.session_id,
        }

    prompt = f"{ctx}\n\n---\nPERTANYAAN USER:\n{q}"
    try:
        raw = strip_code_fences(llm.raw_json(COPILOT_SYSTEM, prompt))
    except (RateLimitError, AuthenticationError, APITimeoutError) as e:
        raise _llm_http_exc(e)
    answer = raw
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and data.get("answer"):
            answer = str(data["answer"])
    except (json.JSONDecodeError, TypeError):
        pass  # the provider answered free-text — use it as-is
    return {"answer": answer.strip(), "grounded_on": grounded, "session_id": body.session_id}


class ModelSwitch(BaseModel):
    provider: str | None = None
    model: str | None = None


@app.post("/admin/seed_move")
def admin_seed_move(body: dict):
    """DEV-ONLY (env-gated, removed after recording): create a canonical Move through the SAME
    `create_move` the reasoning engine uses, so the Maps<->Moves loop can be recorded end to end when
    the engine does not authorize an ACTION for the current state. It bypasses NO guard on the data
    path: the Move it creates is a real canonical Move with server-issued ids, and every later
    mutation still goes through the normal endpoints."""
    if os.environ.get("P7_DEV_SEED") != "1":
        raise HTTPException(404, detail={"code": "NOT_AVAILABLE"})
    s = store.get(str(body.get("session_id") or ""))
    if not s:
        raise HTTPException(404, "session not found")
    from app import moves as _moves
    design = body.get("design") or {}
    mv = _moves.create_move(s, design=design, text=str(body.get("text") or ""),
                            event_id=str(body.get("event_id") or "seed-1"))
    store.save(s)
    return {"ok": True, "move": _moves.view(mv)}


@app.post("/admin/model")
def switch_model(body: ModelSwitch):
    """DEV-ONLY: switch the active provider/model without restarting the server.

    Used to test the same engine against several models and measure per-model
    quota consumption. Disable with ENABLE_ADMIN_SWITCH=0.
    A failed key validation = NO swap (the old state keeps running).
    """
    if os.environ.get("ENABLE_ADMIN_SWITCH", "1") != "1":
        raise HTTPException(403, "Switch model dinonaktifkan (ENABLE_ADMIN_SWITCH=0).")
    provider = body.provider or _ACTIVE["provider"] or os.environ.get("LLM_PROVIDER", "mock")
    llm = build_llm(provider, model=body.model)
    _ACTIVE.update({"provider": provider, "llm": llm})
    return provider_info()


@app.get("/health")
def health():
    def _served_code() -> dict:
        return {
            "commit": _GIT_HASH,
            "uptime_seconds": int(time.time() - _SERVER_STARTED),
        }
    try:
        return {**provider_info(), **_served_code()}
    except HTTPException as e:
        # a 200 so UI/eval can still read the status without crashing. The provider/model map
        # is still sent even when the engine isn't ready — otherwise the UI dropdown is empty
        # and the user has no way out of a wrong configuration.
        provider = os.environ.get("LLM_PROVIDER", "mock")
        return JSONResponse(
            {"status": "error", "provider": provider, "model": None, "detail": e.detail,
             "providers": list(SWITCHABLE_PROVIDERS),
             "available_models": list(_PROVIDER_MODELS.get(provider, ())),
             "models_by_provider": {p: list(m) for p, m in _PROVIDER_MODELS.items()},
             "commit": _GIT_HASH, "uptime_seconds": int(time.time() - _SERVER_STARTED)},
            status_code=200,
        )


# ---- UI (single-page app, served directly) ----
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")


@app.get("/", include_in_schema=False)
def index():
    # no-cache (iter-2): keep the browser from using an old index.html
    return FileResponse(Path(__file__).parent / "static" / "index.html",
                        headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
