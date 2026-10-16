"""Deterministic guard over NextMove proposals (int 16 §R5-D; revised G6/G7 + sufficiency S0–S5 = int 18 §12).

The model PROPOSES; this module DECIDES valid/not.

Checks (all mechanical; never judging "which question is better" — that is the model's domain,
evaluated in R7):
  G1  snapshot: the proposal references the currently valid snapshot_id (not stale state)
  G2  referenced claims exist and are ACTIVE (never resurrecting superseded claims)
  G3  referenced knowledge comes from the drawn menu (applicable + traceable)
  G4  move kind & focus legal; the focus is in the candidate/hypothesis/goal sets
  G5  never repeats a need already asked enough (ASK_CAP) without a new reason
  G6  ACTION is valid when there is an action BASIS (revised, int 18 §12.3; TIGHTENED 15 Oct —
      dsc.v1 hardening): a planner move kind, OR a USABLE path (navigable, not STOP, feasibility
      SUPPORTED/CONDITIONAL; when `move_design.linked_path_id` is set, THAT path MUST be the basis),
      OR a MEASUREMENT move (a `needs_measurement` need); always together with active supporting
      claims + a measurable design (G10) + the causality guardrail. A STOP/non-navigable path may
      not legitimize action (finding P0-03)
  G7  HOLD/abstain valid only with an EXPLICIT reason per remaining uncertainty (revised, int 18 §12.2;
      TIGHTENED 15 Oct): R1 non-material (empty counterfactual) · R2 not answerable now
      (`needs_external` ONLY — `needs_measurement` is ROUTED to ACTION + move_design so a PLANNED Move really
      is born) · R3 the user REQUESTS a pause (active basis claims of aspect constraint/preference/concern AND
      the user's words containing an explicit pause marker). `abstain=true` alone is NOT enough; a HOLD
      carrying `move_design` is rejected (a pause without a Move = an untraceable plan); HOLD still does not
      claim the diagnosis is complete
  G8  move text present for QUESTION/EVIDENCE_REQUEST/ACTION and containing supporting-claim references
      (ACTION requires supporting claims when the snapshot does carry active claims)
  G9  proposed hypotheses valid (active claim refs, valid knowledge, has support)
  G10 ACTION requires a complete measurable design (objective, measurement method, expected evidence,
      completion criteria, 1..180-day window)
  G11 outcome adjudication: Move OBSERVED, observation claims active & born AFTER execution;
      VALIDATED/UNSUPPORTED invalid while the observation window is open; causality never asserted
  S0  shape & version of the `checkpoint_eligibility` block (structural validation int 18 §11.5; one active
      contract version)
  S1  claim basis: refs exist, are ACTIVE, and ARE IN THE SNAPSHOT given to the model (no hidden basis);
      a ready level must have a basis
  S2  uncertainty traceability: classified ⊆ snapshot candidates, disjoint, one marginal entry per id,
      EVERY still-askable candidate must be disclosed (hiding questions is forbidden), and every marginal
      entry must accompany a `critical`/`nonblocking` classification (never reporting a decision value for
      a need never disclosed to the user)
  S3  claim limit: DECISION_USABLE must not leave critical uncertainty behind
  S4  Goal/Path consistency: goal_ref matches the snapshot; linked_path_id real; path ids must not masquerade
      as claims
  S5  level ↔ evidence match: a ready level needs quoted (grounded) basis claims; DECISION_USABLE needs every
      remaining candidate non-material or not answerable now

The nm.v2 contract still has no requirement-status field / goal confirmation / evidence grade, so the model
cannot fake them through a proposal (extra="forbid" in pydantic). The `checkpoint_eligibility` block
is OPTIONAL: its absence = pre-nm.v2 behavior, and HOLD stays fail-closed while any askable need remains.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.reasoning.contract import LEVELS_READY, NM_CONTRACT_VERSION, NextMoveProposal
from core.reasoning.hypotheses import validate_proposals

ASK_CAP = 2


@dataclass
class GuardResult:
    ok: bool
    violations: list[str] = field(default_factory=list)
    valid_hypotheses: list[dict] = field(default_factory=list)
    focus_resolved: dict[str, Any] = field(default_factory=dict)
    sufficiency_violations: list[str] = field(default_factory=list)   # S0..S5 over checkpoint_eligibility
    action_basis: str = ""    # G6 revised: planner_kind_action | feasibility_supported | measurement_move
    action_basis_path: str = ""     # G6 revised: path serving as basis (empty when basis is not feasibility)
    hold_reasons: list[str] = field(default_factory=list)             # G7 revised: R0..R3 per uncertainty
    # SC-09 (int 16): INVALID hypotheses are dropped SEPARATELY — a G9 violation no
    # longer kills the whole move proposal (valid meaning survives beyond the rejected
    # move; the valid part is still applied, the invalid part recorded with its reason).
    hypothesis_dropped: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"ok": self.ok, "violations": list(self.violations),
                "hypotheses_accepted": [h["id"] for h in self.valid_hypotheses],
                "hypothesis_dropped": list(self.hypothesis_dropped),
                "focus": self.focus_resolved,
                "sufficiency": {"ok": not self.sufficiency_violations,
                                "violations": list(self.sufficiency_violations)},
                "action_basis": self.action_basis, "action_basis_path": self.action_basis_path,
                "hold_reasons": list(self.hold_reasons)}


def validate(
    p: NextMoveProposal,
    *,
    snapshot: dict,
    graph: dict,
    hypotheses: dict,
    knowledge_ids: set[str],
    action_allowed: bool,
    ask_cap: int = ASK_CAP,
    design_problems=None,
    assessment_problems=None,
    path_ids: set[str] | None = None,
    paths: list[dict] | None = None,
) -> GuardResult:
    v: list[str] = []
    action_basis = ""
    action_basis_path = ""
    hold_reasons: list[str] = []
    active = {cid for cid, n in (graph.get("nodes") or {}).items() if (n.get("status") or "active") == "active"}
    uncertainties = {u["id"]: u for u in snapshot.get("uncertainties") or []}

    # G1
    if p.state_snapshot_ref != snapshot.get("snapshot_id"):
        v.append(f"G1 state_snapshot_ref basi/salah: {p.state_snapshot_ref!r} != {snapshot.get('snapshot_id')!r}")
    # G2
    bad_claims = [c for c in p.supporting_claim_refs if c not in active]
    if bad_claims:
        v.append(f"G2 supporting_claim_refs tidak aktif/tidak ada: {bad_claims}")
    # G3
    bad_k = [k for k in p.knowledge_refs if k not in knowledge_ids]
    if bad_k:
        v.append(f"G3 knowledge_refs di luar menu terambil: {bad_k}")
    # G9 hypotheses — SC-09 (int 16): INVALID hypothesis proposals are dropped separately (recorded
    # in `hypothesis_dropped`), NOT killing the move proposal. The valid ones stay alive even
    # when other parts of the Move are rejected; valid meaning is not discarded with the wrong move.
    valid_h, h_drop = validate_proposals(p.competing_hypotheses, graph, knowledge_ids, hypotheses or {})

    # G4 focus
    focus: dict[str, Any] = {"type": p.focus_type, "id": p.proposed_focus}
    kind = p.proposed_move_kind
    if kind in ("QUESTION", "EVIDENCE_REQUEST"):
        if p.focus_type == "uncertainty":
            u = uncertainties.get(p.proposed_focus)
            if u is None:
                v.append(f"G4 fokus bukan ketidakpastian kandidat: {p.proposed_focus!r}")
            else:
                focus["need_id"] = u["id"]
                if not u.get("askable", True):
                    v.append(f"G4 ketidakpastian {u['id']} tidak dapat dijawab lewat percakapan (butuh aksi/ukur)")
                # G5
                if int(u.get("asked", 0)) >= ask_cap:
                    v.append(f"G5 {u['id']} sudah ditanyakan {u['asked']}x (ASKED_ENOUGH) — beralih ke ukur/aksi/jeda")
        elif p.focus_type == "hypothesis":
            known = {h["id"] for h in valid_h} | set((hypotheses or {}).keys())
            if p.proposed_focus not in known:
                v.append(f"G4 fokus hipotesis tidak dikenal: {p.proposed_focus!r}")
            else:
                focus["need_id"] = f"hypothesis:{p.proposed_focus}"
        elif p.focus_type == "goal":
            if "goal" not in uncertainties:
                v.append("G4 fokus goal padahal goal sudah terbukti")
            else:
                focus["need_id"] = "goal"
                if int(uncertainties["goal"].get("asked", 0)) >= ask_cap:
                    v.append("G5 goal sudah ditanyakan cukup")
        if not p.supporting_claim_refs and (snapshot.get("claim_ids") or []):
            v.append("G8 usulan tanpa supporting_claim_refs padahal ada klaim aktif")
        if len(p.move_text.strip()) < 8:
            v.append("G8 move_text kosong/terlalu pendek")
        if kind == "EVIDENCE_REQUEST":
            v.extend("W-F1 " + x for x in _evidence_request_problems(p, active=active, knowledge_ids=knowledge_ids))
    elif kind == "ACTION":
        # G6 revised (int 18 §12.3, tightened 15 Oct): action basis — planner move kind OR a USABLE
        # path OR a measurement move. A STOP/non-navigable path MUST NOT become the basis (P0-03).
        action_basis, action_basis_path, basis_problems = _action_basis(
            p, paths=paths, action_allowed=action_allowed)
        v.extend(basis_problems)
        if not action_basis and not basis_problems:
            v.append("G6 ACTION tanpa basis tindakan: bukan jenis langkah planner, tidak ada path layak "
                     "(navigable + bukan STOP + feasibility SUPPORTED/CONDITIONAL) di snapshot, dan bukan "
                     "langkah pengukuran (needs_measurement)")
        if not p.supporting_claim_refs and (snapshot.get("claim_ids") or []):
            v.append("G8 ACTION tanpa supporting_claim_refs padahal snapshot membawa klaim aktif "
                     "(tindakan wajib ber-grounding)")
        if len(p.move_text.strip()) < 8:
            v.append("G8 move_text kosong/terlalu pendek")
        if design_problems is not None:
            v.extend("G10 " + x for x in design_problems(p.move_design.model_dump() if p.move_design else None))
    elif kind == "HOLD":
        # P0-01 (audit 15 Oct): a pause MUST NOT store a measurement plan — Moves are born only from ACTION.
        if p.move_design is not None:
            v.append("G7 HOLD membawa move_design: jeda tidak melahirkan Move terlacak — pengukuran diajukan "
                     "sebagai ACTION + move_design (satu jalur, int 18 §12.4)")
        hold_v, hold_reasons = _hold_reasons(p, uncertainties=uncertainties, ask_cap=ask_cap,
                                            active=active, graph=graph)
        v.extend("G7 " + x for x in hold_v)
        if not p.conditions_for_abstention.strip():
            v.append("G7 HOLD/abstain wajib conditions_for_abstention")

    # G10 (continued): design references must be real
    if p.move_design is not None:
        d = p.move_design
        if d.linked_hypothesis_id and d.linked_hypothesis_id not in set((hypotheses or {}).keys()) | {
                h["id"] for h in valid_h}:
            v.append(f"G10 linked_hypothesis_id tidak dikenal: {d.linked_hypothesis_id!r}")
        if d.linked_path_id and path_ids is not None and d.linked_path_id not in path_ids:
            v.append(f"G10 linked_path_id tidak dikenal: {d.linked_path_id!r}")
    # G11: outcome adjudication
    if p.outcome_assessment is not None:
        if assessment_problems is None:
            v.append("G11 putusan outcome tanpa pemeriksa Move")
        else:
            v.extend(assessment_problems(p.outcome_assessment.model_dump()))

    # S0..S5: sufficiency of the checkpoint_eligibility block (int 18 §11.5, §12.6)
    sv = _sufficiency(p, snapshot=snapshot, graph=graph, active=active, uncertainties=uncertainties,
                      paths=paths, path_ids=path_ids)
    v.extend(sv)

    return GuardResult(ok=not v, violations=v, valid_hypotheses=valid_h, focus_resolved=focus,
                       sufficiency_violations=sv, action_basis=action_basis,
                       action_basis_path=action_basis_path, hold_reasons=hold_reasons,
                       hypothesis_dropped=h_drop)


# ── G6 revised: action basis ───────────────────────────────────────────────────

FEASIBLE_OK = ("SUPPORTED", "CONDITIONAL")
# Path statuses EXCLUDED as an action basis. Source: `core/navigation/contracts.py` STATUS_WORDS
# ("STOP" = user decision OR engine finding) + path lifecycle (STOPPED/CLOSED).
PATH_NOT_USABLE = ("STOP", "STOPPED", "CLOSED")


def _usable_paths(paths: list[dict] | None) -> list[dict]:
    """Paths allowed to become an action BASIS: navigable, not STOP/STOPPED/CLOSED, feasibility usable.

    Finding P0-03 (audit 15 Oct): the guard previously accepted any path with feasibility
    SUPPORTED/CONDITIONAL — including paths already STOP/non-navigable — so one stale path could
    legitimize an action irrelevant to or contradicting the user's lifecycle decision."""
    out: list[dict] = []
    for row in paths or []:
        r = row or {}
        status = str(r.get("status") or "").upper()
        feas = str(r.get("feasibility") or "").upper()
        if not r.get("navigable") or status in PATH_NOT_USABLE or feas not in FEASIBLE_OK:
            continue
        out.append({"path_id": str(r.get("path_id") or ""), "feasibility": feas, "status": status})
    return out


def _action_basis(p: NextMoveProposal, *, paths: list[dict] | None,
                  action_allowed: bool) -> tuple[str, str, list[str]]:
    """(basis, basis_path, violations). An empty basis without violations ⇒ G6 rejects with no ground.

    `feasibility_supported` is read from the snapshot (each path's feasibility) — the planner is NOT
    recomputed. When the proposal LINKS a path as its ground (`move_design.linked_path_id`), that path
    must be USABLE; if not, the proposal is REJECTED with an explicit reason (not silently falling back
    to another basis). When the link is empty and >1 usable path exists, the basis is ambiguous ⇒
    reject, so "an action is tied to its basis" stays auditable."""
    usable = _usable_paths(paths)
    by_id = {u["path_id"]: u for u in usable}
    linked = str((p.move_design.linked_path_id if p.move_design else "") or "")
    if linked and linked not in by_id:
        row = next((r for r in paths or [] if str((r or {}).get("path_id") or "") == linked), None)
        if row is not None:
            return "", "", [
                f"G6 ACTION memakai path {linked!r} sebagai basis padahal path itu tidak layak dipakai "
                f"(status={str(row.get('status'))!r}, navigable={row.get('navigable')!r}, "
                f"feasibility={str(row.get('feasibility'))!r}) — path STOP/tidak navigable tidak boleh "
                "menjadi dasar tindakan"]
    if action_allowed:
        return "planner_kind_action", "", []
    if linked:
        return "feasibility_supported", linked, []
    if len(usable) == 1:
        return "feasibility_supported", usable[0]["path_id"], []
    if len(usable) > 1:
        return "", "", ["G6 ACTION atas feasibility ambigu: ada lebih dari satu path layak — tautkan "
                        "`move_design.linked_path_id` ke path yang menjadi basis tindakan"]
    elig = p.checkpoint_eligibility
    if elig is not None and any(m.answerability == "needs_measurement" for m in elig.marginal_information_value):
        return "measurement_move", "", []
    return "", "", []


# ── W-F1: EVIDENCE_REQUEST = evidence that ALREADY EXISTS (F1, int 18 §12.4) ─────────────

def _evidence_request_problems(p: NextMoveProposal, *, active: set[str], knowledge_ids: set[str]) -> list[str]:
    """F1 (owner decision 15 Oct 2026): an evidence request points at sources that REALLY exist; NEW
    MEASUREMENT is not this but ACTION + `move_design` (one path, not two — the Move lifecycle stays
    the sole experiment marker)."""
    out: list[str] = []
    if not p.evidence_source_refs:
        out.append("sumber bukti wajib (evidence_source_refs) — pengukuran baru diajukan sebagai ACTION + move_design")
    ghosts = [s for s in p.evidence_source_refs if s not in active and s not in knowledge_ids]
    if ghosts:
        out.append(f"evidence_source_refs di luar klaim aktif/pengetahuan terambil: {ghosts}")
    if len(p.evidence_source_refs) != len(set(p.evidence_source_refs)):
        out.append("evidence_source_refs duplikat")
    if not p.information_value_rationale.strip():
        out.append("relevansi sumber wajib (information_value_rationale)")
    return out


# ── G7 revised: explicit reason per uncertainty ──────────────────────────────

PAUSE_ASPECTS = ("constraint", "preference", "concern")   # aspects allowed to mark a "user pause request"
# EXPLICIT pause markers in the user's own words. so.v1 has no pause-request vocabulary yet (its aspects
# are only preference/concern/constraint/intention/plan/behavior/conflict), so until that exists, R3 is
# evidenced by "interaction aspect + user-word marker" — NOT by any business constraint being present
# (finding P0-02). This lexical bridge is recorded as meaning-contract work in int 18 §15.3 so it can be
# removed without touching the guard.
PAUSE_MARKERS = (
    "jeda", "cukup dulu", "sudah cukup", "sampai di sini dulu", "jangan tanya", "berhenti dulu", "nanti saja",
    "tidak sekarang", "skip dulu", "lewati dulu", "tunda dulu", "lain kali", "pause", "hold on", "hold off",
    "enough for now", "not now", "stop asking", "keep it for later", "stop here", "park this",
    "come back to this later", "skip this for now",
)


def _pause_basis(p: NextMoveProposal, *, active: set[str], graph: dict) -> str:
    """R3: the user REQUESTS a pause — evidenced by the combination of two auditable things:

    (a) an active basis claim of aspect constraint/preference/concern (role/aspect from the so.v1
        meaning authority), AND
    (b) the user's own words containing an explicit pause marker (PAUSE_MARKERS).

    (a) alone is NOT enough: "saya tidak mau menambah jam kerja" ("I don't want to add working hours")
    is a constraint on ACTION, not a request to stop the discussion (finding P0-02, audit 15 Oct). Read
    from the CANONICAL NODE in `graph`, not the snapshot row."""
    nodes = graph.get("nodes") or {}
    cited = list(p.supporting_claim_refs)
    if p.checkpoint_eligibility is not None:
        cited += list(p.checkpoint_eligibility.basis_claim_refs)
    for cid in cited:
        if cid not in active:
            continue
        node = nodes.get(cid) or {}
        if str(node.get("aspect") or "") not in PAUSE_ASPECTS:
            continue
        text = str(node.get("verbatim") or "").lower()
        if any(m in text for m in PAUSE_MARKERS):
            return cid
    return ""


def _hold_reasons(p: NextMoveProposal, *, uncertainties: dict, ask_cap: int, active: set[str],
                  graph: dict) -> tuple[list[str], list[str]]:
    """Reason per remaining uncertainty. Returns: (violations, audit reasons).
    `abstain=true` alone is NOT enough."""
    askable = [u for u in uncertainties.values()
               if u.get("askable", True) and int(u.get("asked", 0)) < ask_cap]
    if not askable:
        return [], ["R0 tidak ada ketidakpastian yang dapat ditanyakan"]
    if not p.abstain:
        return ["HOLD tanpa abstain padahal masih ada ketidakpastian yang dapat ditanyakan"], []
    elig = p.checkpoint_eligibility
    if elig is None:
        return [(f"HOLD tanpa checkpoint_eligibility padahal masih ada {len(askable)} ketidakpastian yang dapat "
                 "ditanyakan (alasan per kebutuhan wajib, bukan sekadar abstain=true)")], []
    pause_with = _pause_basis(p, active=active, graph=graph)
    out: list[str] = []
    reasons: list[str] = []
    crit, nonb = set(elig.critical_unknown_ids), set(elig.nonblocking_unknown_ids)
    marg = {m.uncertainty_id: m for m in elig.marginal_information_value}
    for u in askable:
        uid = u["id"]
        m = marg.get(uid)
        if uid not in crit and uid not in nonb:
            out.append(f"{uid} tidak diklasifikasi di checkpoint_eligibility (critical/nonblocking)")
            continue
        if m is None:
            out.append(f"{uid} tanpa entri marginal_information_value")
            continue
        material = bool(m.counterfactual.strip())
        if uid in crit and (not material or m.answerability != "now_conversation"):
            out.append(f"{uid} didaftarkan critical tetapi bukan material-yang-dapat-dijawab-sekarang")
            continue
        if not material:
            reasons.append(f"R1 non_material: {uid}")
        elif m.answerability == "needs_measurement":
            # P0-01 (audit 15 Oct): a HOLD must not store a measurement plan —
            # Moves are born only from ACTION.
            out.append(f"{uid} hanya dapat dijawab lewat PENGUKURAN ⇒ ajukan ACTION + move_design (Move PLANNED) "
                       "supaya pengukuran terlacak; HOLD tidak boleh menjadi tempat rencana eksperimen")
        elif m.answerability == "needs_external":
            reasons.append(f"R2 not_answerable_now: {uid} (needs_external)")
        elif pause_with:
            reasons.append(f"R3 user_chose_pause: {uid} (basis {pause_with})")
        else:
            out.append(f"{uid} masih material dan dapat dijawab sekarang — beralih ke pertanyaan/pengukuran, "
                       "bukan HOLD (atau tunjukkan PERMINTAAN JEDA eksplisit user sebagai dasar)")
    return out, reasons or ["R1/R2/R3: tidak ada alasan yang bertahan"]


# ── S0..S5: sufficiency of the checkpoint_eligibility block (int 18 §11.5, §12.6) ─────────

def _sufficiency(p: NextMoveProposal, *, snapshot: dict, graph: dict, active: set[str],
                 uncertainties: dict, paths: list[dict] | None, path_ids: set[str] | None) -> list[str]:
    """Validate references/completeness/consistency of the sufficiency block. A missing block ⇒ only
    the S0 contract-version check applies (pre-nm.v2 behavior stays intact, and HOLD stays fail-closed
    through G7). The guard does NOT judge "whether the conclusion is good" — that is the model's
    domain (evaluated in phase D)."""
    out: list[str] = []
    if p.contract_version != NM_CONTRACT_VERSION:
        out.append(f"S0 contract_version harus {NM_CONTRACT_VERSION!r} (satu versi aktif, tanpa dual-validasi): "
                   f"{p.contract_version!r}")
    elig = p.checkpoint_eligibility
    if elig is None:
        return out
    ready = elig.level in LEVELS_READY
    if elig.can_offer_checkpoint and not ready:
        out.append(f"S0 can_offer_checkpoint=true tetapi level={elig.level}")
    if ready and not elig.can_offer_checkpoint:
        out.append(f"S0 level={elig.level} wajib can_offer_checkpoint=true (tingkat siap tidak boleh ditahan)")
    if elig.level == "STATE_ONLY" and (elig.can_offer_checkpoint or elig.recommendation.strip()):
        out.append("S0 STATE_ONLY tidak boleh menawarkan kesimpulan (can_offer_checkpoint=false, recommendation kosong)")
    crit, nonb = list(elig.critical_unknown_ids), list(elig.nonblocking_unknown_ids)
    both = sorted(set(crit) & set(nonb))
    if both:
        out.append(f"S0 id ketidakpastian muncul di critical DAN nonblocking: {both}")
    known = set(uncertainties)
    ghosts = sorted((set(crit) | set(nonb)) - known)
    if ghosts:
        out.append(f"S2 id ketidakpastian tidak ada di kandidat snapshot: {ghosts}")
    marg = [m.uncertainty_id for m in elig.marginal_information_value]
    dupes = sorted({x for x in marg if marg.count(x) > 1})
    if dupes:
        out.append(f"S2 entri marginal duplikat: {dupes}")
    ghost_marg = sorted({x for x in marg} - known)
    if ghost_marg:
        out.append(f"S2 entri marginal untuk kandidat tak dikenal: {ghost_marg}")
    missing_marg = sorted((set(crit) | set(nonb)) - set(marg))
    if missing_marg:
        out.append(f"S2 kandidat tanpa entri marginal: {missing_marg}")
    # Final deep check 15 Oct 2026 (finding P1, second side): a marginal entry MUST accompany one of the
    # classification lists. Previously only "missing entries" and "unknown ids" were checked, so a marginal
    # entry for a known but UNCLASSIFIED candidate slipped through — meaning a "decision value" could be
    # reported for a need never disclosed to the user.
    unclassified_marg = sorted(({x for x in marg} & known) - (set(crit) | set(nonb)))
    if unclassified_marg:
        out.append(f"S2 entri marginal untuk kandidat yang TIDAK diklasifikasi (critical/nonblocking): "
                   f"{unclassified_marg}")
    wanted = {uid for uid, d in uncertainties.items()
              if d.get("askable", True) and int(d.get("asked", 0)) < ASK_CAP}
    if ready:
        undisclosed = sorted(wanted - set(crit) - set(nonb))
        if undisclosed:
            out.append(f"S2 ketidakpastian yang masih dapat ditanya tidak diungkapkan (critical/nonblocking): "
                       f"{undisclosed}")
    bad_basis = [c for c in elig.basis_claim_refs if c not in active]
    if bad_basis:
        out.append(f"S1 basis_claim_refs tidak aktif/tidak ada: {bad_basis}")
    # §4B (audit 15 Oct) + final deep-check finding 1 (15 Oct): the basis must exist in the SNAPSHOT actually
    # given to the model, not only in the graph. This check runs WITHOUT the `if in_snapshot` condition: when
    # the snapshot carries no claims at all (empty `claim_ids` — e.g. the context budget ran out), references
    # to active claims the model never received must still be caught, not skipped.
    in_snapshot = set(snapshot.get("claim_ids") or [])
    outside = [c for c in elig.basis_claim_refs if c in active and c not in in_snapshot]
    if outside:
        out.append(f"S1 basis_claim_refs di luar snapshot keputusan (basis tersembunyi): {outside}")
    if ready and not elig.basis_claim_refs:
        out.append("S1 tingkat siap tanpa basis_claim_refs (state_anchor)")
    if elig.level == "DECISION_USABLE" and crit:
        out.append(f"S3 DECISION_USABLE dengan critical_unknown_ids non-kosong: {crit}")
    if path_ids:
        leaked = [c for c in elig.basis_claim_refs if c in path_ids]
        if leaked:
            out.append(f"S4 basis_claim_refs memuat id path (bukan klaim): {leaked}")
    goal_id = str((snapshot.get("goal") or {}).get("goal_id") or "")
    if p.goal_ref and not goal_id:
        out.append(f"S4 goal_ref diisi ({p.goal_ref!r}) padahal snapshot tidak punya Goal terbentuk")
    elif p.goal_ref and p.goal_ref != goal_id:
        # P0-05 (audit 15 Oct): previously two DIFFERENT Goal IDs passed — Goal-scoped reasoning leaked.
        out.append(f"S4 goal_ref tidak cocok dengan Goal snapshot: {p.goal_ref!r} != {goal_id!r} "
                   "(penalaran ter-scope Goal tidak boleh menukar Goal)")
    if p.move_design is not None and p.move_design.linked_path_id and path_ids is not None \
            and p.move_design.linked_path_id not in path_ids:
        out.append(f"S4 linked_path_id tidak ada di snapshot: {p.move_design.linked_path_id!r}")
    if ready:
        nodes = graph.get("nodes") or {}
        grounded = [c for c in elig.basis_claim_refs
                    if str((nodes.get(c) or {}).get("verbatim") or "").strip()]
        if not grounded:
            out.append("S5 tingkat siap tanpa klaim basis berkutipan (grounded_interpretation)")
    if elig.level == "DECISION_USABLE":
        by_id = {m.uncertainty_id: m for m in elig.marginal_information_value}
        blocking = sorted(u for u in crit
                          if (by_id.get(u) is None or by_id[u].answerability == "now_conversation"))
        if blocking:
            out.append(f"S5 DECISION_USABLE padahal kandidat material masih dapat dijawab sekarang: {blocking}")
    by_id = {m.uncertainty_id: m for m in elig.marginal_information_value}
    bad_crit = sorted(u for u in crit
                     if (m := by_id.get(u)) is not None
                     and (not m.counterfactual.strip() or m.answerability != "now_conversation"
                          # ASK_CAP-S5 (17 Oct incident, session c913b0b51579): an unknown ALREADY asked
                          # ASK_CAP times and still unanswered is NO LONGER "answerable now through
                          # conversation" — the model's answerability claim is rejected based on the
                          # snapshot's asked_count (deterministic). Without this, a flash-tier model keeps
                          # "always 1 new critical" per turn (re-labeling) ⇒ never-ending questions;
                          # ASK_CAP exists precisely TO forbid re-asking (G5), not to justify endlessly
                          # postponing the checkpoint. A saturated unknown must STILL be disclosed —
                          # its place is nonblocking (needs_measurement) or ACTION.
                          or int((uncertainties.get(u) or {}).get("asked", 0)) >= ASK_CAP))
    if bad_crit:
        out.append(f"S5 id critical tetapi bukan material-yang-dapat-dijawab-sekarang: {bad_crit}")
    nonb_material = sorted(u for u in nonb
                           if (m := by_id.get(u)) is not None and m.counterfactual.strip()
                           and m.answerability == "now_conversation")
    if nonb_material:
        out.append(f"S5 id nonblocking padahal material dan masih dapat dijawab sekarang (harus critical): "
                   f"{nonb_material}")
    return out
