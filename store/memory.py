"""Session store — JSON/JSONL disk persistence (iter-14) + fail-closed recovery (R3.2-B).

Session snapshots: `store/sessions/<id>.json`; durable conversation events: `store/events/<id>.jsonl`
(authoritative for exactly-once/replay). Sessions that cannot be recovered are recorded in
`recovery_issues`, never treated as "nonexistent". Swapping the backend (e.g. Firestore) only means
replacing this class; the `get/create/append` interface is preserved.
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from core.schema.evidence import EvidenceItem
from domains.revenue.schema.artifact import DiagnosisArtifact

log = logging.getLogger("novaliners.store")


@dataclass
class Session:
    id: str
    goal_text: str
    language: str
    transcript: list[tuple[str, str]] = field(default_factory=list)  # (role, text)
    evidence: list[EvidenceItem] = field(default_factory=list)
    diagnosis: DiagnosisArtifact | None = None
    interview_done: bool = False
    evidence_seq: int = 0  # unique counter per session — the LLM is NOT trusted for IDs (#5)
    # J3 (internal-docs §7): cross-session identity & linkage — enables deterministic
    # deltas (ADVANCED|STUCK|PIVOTED|REGRESSED) across runs.
    user_id: str = ""
    prior_session_id: str = ""
    journey_delta: dict | None = None
    # J7-a (internal-docs §7): session age — basis of the reassess status
    # (reassess_status).
    created_ts: int = field(default_factory=lambda: int(time.time()))
    # P-A (internal-docs §11): structured Goal object — complements
    # goal_text (kept alive for backward compat). None = not yet operationalized.
    goal: dict | None = None
    # B (23 Sep 2026): per-turn intent_tags — they used to live only in the POST /message
    # response, so the Intent Tags panel could NOT be restored on loadMap
    # (measured: tagsLen=32 char placeholder even though the diagnosis rendered). Additive + capped;
    # old sessions without this field stay safe (default_factory).
    intent_tags: list[dict] = field(default_factory=list)
    # Phase A (int 08, 25 Sep): per-turn number_claims — numeric claims tagged with role/tense/
    # verbatim from LLM context understanding. Closes the regex bug class (current read from a
    # 6.5M history; target from a rejected-tariff 3M; '8jt/bln' unreadable).
    # Additive + cap 300; Phase B will consume this, replacing the state.py regex block.
    number_claims: list[dict] = field(default_factory=list)
    # M1 (int 11 Rev 11.1, additive): universal state graph — nodes+edges produced by the
    # verify gate; sourced from Requirement State, not phases.
    state_graph: dict = field(default_factory=lambda: {"nodes": {}, "edges": {}})
    # M2: structured per-turn drift report (old vs new) — basis of the M3 decision
    graph_drift_reports: list[dict] = field(default_factory=list)
    # Human-language explanation for the Diagnosis screen (agents/explain.py). Cache; linked to
    # the artifact via `basis`.
    explain: dict | None = None
    # M4 (internal-docs §25): per-turn Question Planner decision log — {turn, input,
    # decision, text}. Basis of REPLAY (same input -> same decision) and of the "asked how many
    # times" counter (loop guard). Additive + capped; old sessions without this field stay safe.
    planner_log: list[dict] = field(default_factory=list)
    # Summary of the most recent live adjudication (audit; not a status source — status lives
    # only in the ledger).
    last_adjudication: dict | None = None
    # R3 (int 16 §R3-A): durable conversation events — the substratum beneath understanding.
    # Mirror of store/events/<id>.jsonl; old sessions without this field stay safe.
    events: list[dict] = field(default_factory=list)
    # R5 (int 16 §R5-B): competing hypotheses grounded in canonical claims; old sessions
    # without this field are safe.
    hypotheses: dict = field(default_factory=dict)
    # R6 (int 16 §R6): Moves as measured experiments + live checkpoints; old sessions
    # without this field are safe.
    moves: list = field(default_factory=list)
    checkpoints: list = field(default_factory=list)
    # CIR-03 (int 19 §7.3, OD-18): so.v1 semantic uncertainty kept as an advisory proposal
    # in the session (not a new DB, not a second authority) — reuses the existing session store.
    semantic_unknowns: list = field(default_factory=list)
    # V4 E2E (18 Oct 2026; D-04/D-05): compact projection snapshots (projection_revision + node/
    # edge/status ids) for change_sets across revisions. Additive + capped; old sessions without
    # this field stay safe (default_factory) and are not interpreted as "no state".
    experience_snapshots: list = field(default_factory=list)
    # MC-07 (18 Oct, owner decision): monotonic QUESTION BUDGET per batch — a presentation layer
    # for the "key questions left" chip. Engine counts stay honest (planner/inspection); the number
    # promised to the user NEVER rises within a batch — at best it holds — and reaching 0 → the
    # continue/build choice.
    # {batch, initial, answered, remaining, open_at_start}. Additive; old sessions without it are safe.
    question_budget: dict = field(default_factory=dict)

    def transcript_tail(self, n: int = 6) -> str:
        """Trim the transcript: max 150 words per user turn + the last N turns."""
        def trim(role: str, text: str, max_words: int = 150) -> str:
            words = text.split()
            if role == "user" and len(words) > max_words:
                return " ".join(words[:max_words]) + "… [dipangkas — terlalu panjang]"
            return text
        return "\n".join(f"{role}: {trim(role, text)}" for role, text in self.transcript[-n:])

    def full_transcript(self) -> str:
        return "\n".join(f"{role}: {text}" for role, text in self.transcript)


class SessionStore:
    """iter-14: sessions persisted to disk (store/sessions/<id>.json) — a ledger of 62
    evidence items from run v7 was lost entirely on restart because the store was purely
    in-memory. Every audit needs replay; this persistence closes that gap."""

    PERSIST_DIR = Path(__file__).resolve().parent / "sessions"

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        # Fail-closed recovery policy (R3.2-B): every record that CANNOT be recovered
        # is recorded here (and logged), never treated as "nonexistent". Problem sessions are
        # not loaded as healthy sessions; the source files are preserved as evidence.
        self.recovery_issues: list[dict] = []
        self._load_all()

    def _issue(self, session_id: str, kind: str, detail: str = "") -> None:
        self.recovery_issues.append({"session_id": session_id, "kind": kind, "detail": detail})
        log.debug("recovery issue sesi=%s kind=%s %s", session_id, kind, detail)

    def _scan_orphan_events(self) -> None:
        """Event files without a session snapshot = user messages received while their
        session went missing."""
        from store import events as event_store
        d = event_store.EVENTS_DIR
        if not d.exists():
            return
        for f in sorted(d.glob("*.jsonl")):
            sid = f.stem
            if sid in self._sessions or any(i["session_id"] == sid for i in self.recovery_issues):
                continue
            evs, _ = event_store.load_events_checked(sid)
            if any(e.get("role") == "user" for e in evs):
                self._issue(sid, "orphan_events", f"{len(evs)} event tanpa snapshot sesi")

    def _load_all(self) -> None:
        try:
            self._load_snapshots()
        finally:
            try:
                self._scan_orphan_events()
            except Exception as exc:  # noqa: BLE001
                log.warning("pemindaian orphan event gagal: %s", exc)
            if self.recovery_issues:
                kinds: dict[str, int] = {}
                for i in self.recovery_issues:
                    kinds[i["kind"]] = kinds.get(i["kind"], 0) + 1
                log.warning("recovery: %d masalah tak terpulihkan dicatat (%s); lihat store.recovery_issues",
                            len(self.recovery_issues), kinds)

    def _load_snapshots(self) -> None:
        if not self.PERSIST_DIR.exists():
            return
        for f in sorted(self.PERSIST_DIR.glob("*.json")):
            try:
                # M5: old session files may contain `phase` / `turns_in_phase` (the phased interview
                # engine, now removed). Those keys are DELIBERATELY not read: the loader only picks
                # fields Session knows, so legacy data loads without any effect on planner,
                # readiness, route, or NextMove.
                data = json.loads(f.read_text())
                s = Session(
                    id=data["id"],
                    goal_text=data.get("goal_text", ""),
                    language=data.get("language", "id"),
                    transcript=[tuple(t) for t in data.get("transcript", [])],
                    evidence=[EvidenceItem(**e) for e in data.get("evidence", [])],
                    diagnosis=(DiagnosisArtifact(**data["diagnosis"]) if data.get("diagnosis") else None),
                    interview_done=data.get("interview_done", False),
                    evidence_seq=data.get("evidence_seq", 0),
                    user_id=data.get("user_id", ""),
                    prior_session_id=data.get("prior_session_id", ""),
                    journey_delta=data.get("journey_delta"),
                    created_ts=int(data.get("created_ts") or 0),
                    goal=data.get("goal"),
                    # Phase A (int 08): load the number claims; intent_tags along with them
                    # (old gap: they only lived in memory and were lost on restart).
                    number_claims=data.get("number_claims") or [],
                    intent_tags=data.get("intent_tags") or [],
                    state_graph=data.get("state_graph") or {"nodes": {}, "edges": {}},
                    graph_drift_reports=data.get("graph_drift_reports") or [],
                    explain=data.get("explain"),
                    planner_log=data.get("planner_log") or [],
                    last_adjudication=data.get("last_adjudication"),
                    events=data.get("events") or [],
                    hypotheses=data.get("hypotheses") or {},
                    moves=data.get("moves") or [],
                    checkpoints=data.get("checkpoints") or [],
                    semantic_unknowns=data.get("semantic_unknowns") or [],
                    experience_snapshots=data.get("experience_snapshots") or [],
                    question_budget=data.get("question_budget") or {},
                )
                try:  # recovery: durable events that did not make it into the snapshot
                    from store import events as event_store
                    event_store.reconcile_session_events(s)
                    _, ev_issues = event_store.load_events_checked(s.id)
                    for i in ev_issues:
                        self._issue(s.id, i["kind"], i.get("detail", ""))
                except Exception as exc:  # noqa: BLE001
                    self._issue(s.id, "reconcile_failed", f"{type(exc).__name__}: {exc}")
                self._sessions[s.id] = s
            except Exception as exc:  # noqa: BLE001
                # corrupt/unreadable snapshot: NEVER swallow it. The file is preserved as evidence
                # (.corrupt-<ts>), the session is not loaded as healthy, the issue is recorded.
                self._issue(f.stem, "corrupt_snapshot", f"{type(exc).__name__}")
                try:
                    os.replace(f, f.with_name(f"{f.name}.corrupt-{int(time.time())}"))
                except OSError:
                    pass
                continue

    def save(self, s: Session) -> None:
        """Best-effort (non-semantic path). Semantic turns use save_strict."""
        try:
            self.save_strict(s)
        except Exception:
            pass  # best-effort persistence — never break the interview flow

    def save_strict(self, s: Session) -> None:
        """Persist the session snapshot ATOMICALLY (tmp + replace) and PROPAGATE failures.

        Used by semantic turns: the ACK to the user is only valid once the canonical state is
        durable (CP-25).
        """
        from store.events import SessionPersistenceError
        try:
            self.PERSIST_DIR.mkdir(parents=True, exist_ok=True)
            data = {
                "id": s.id, "goal_text": s.goal_text, "language": s.language,
                "transcript": [list(t) for t in s.transcript],
                "evidence": [e.model_dump() for e in s.evidence],
                "diagnosis": (s.diagnosis.model_dump() if s.diagnosis else None),
                "interview_done": s.interview_done,
                "evidence_seq": s.evidence_seq,
                "user_id": s.user_id,
                "prior_session_id": s.prior_session_id,
                "journey_delta": s.journey_delta,
                "created_ts": s.created_ts,
                "goal": s.goal,
                # Phase A (int 08): number claims + intent tags persist too — they used to
                # live only in memory (intent_tags had the same gap; fixed at the same time
                # because the pattern was identical). Phase B reads these at finalize.
                "number_claims": s.number_claims,
                "intent_tags": s.intent_tags,
                # M1: the graph persists too (adjacency list, int 11 storage decision)
                "state_graph": s.state_graph,
                "graph_drift_reports": s.graph_drift_reports,
                "explain": s.explain,
                "planner_log": s.planner_log,
                "last_adjudication": s.last_adjudication,
                "events": s.events,
                "hypotheses": getattr(s, "hypotheses", None) or {},
                "moves": getattr(s, "moves", None) or [],
                "checkpoints": getattr(s, "checkpoints", None) or [],
                "semantic_unknowns": getattr(s, "semantic_unknowns", None) or [],
                "experience_snapshots": getattr(s, "experience_snapshots", None) or [],
                "question_budget": getattr(s, "question_budget", None) or {},
                "saved_at": datetime.now().isoformat(timespec="seconds"),
            }
            final = self.PERSIST_DIR / f"{s.id}.json"
            tmp = self.PERSIST_DIR / f"{s.id}.json.tmp"
            with tmp.open("w", encoding="utf-8") as fh:
                fh.write(json.dumps(data, ensure_ascii=False, indent=1))
                fh.flush()
                os.fsync(fh.fileno())      # data on the device before the rename
            os.replace(tmp, final)
            try:                            # durable rename: fsync the directory (best-effort)
                dfd = os.open(self.PERSIST_DIR, os.O_RDONLY)
                try:
                    os.fsync(dfd)
                finally:
                    os.close(dfd)
            except OSError:
                pass
        except Exception as exc:
            raise SessionPersistenceError(
                f"snapshot sesi {s.id} gagal disimpan: {type(exc).__name__}: {exc}") from exc

    def create(self, goal_text: str, language: str, user_id: str = "",
               prior_session_id: str = "", goal: dict | None = None) -> Session:
        s = Session(id=uuid.uuid4().hex[:12], goal_text=goal_text,
                    language=language, user_id=user_id,
                    prior_session_id=prior_session_id, goal=goal)
        self._sessions[s.id] = s
        self.save(s)
        return s

    def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def sessions_by_user(self, user_id: str) -> list[Session]:
        """J7-c (internal-docs §7): all sessions owned by one user — basis of the
        per-user intervention-outcome aggregation (demote). Empty user_id → empty."""
        if not user_id:
            return []
        return [s for s in self._sessions.values() if s.user_id == user_id]

    def all_sessions(self) -> list[Session]:
        """All sessions (no ordering guarantee) — for GET /sessions (UI fallback:
        sidebar restore must not rely on localStorage alone)."""
        return list(self._sessions.values())


store = SessionStore()
