"""Adaptive NextMove reasoning orchestration per turn (int 16 §R5) — connecting canonical state, applied
knowledge, hypotheses, and guards. Called from `run_turn` AFTER the semantic observation is committed and
navigation is computed.

Division of roles:
  deterministic navigation (`decision`) = the source of uncertainty candidates, ACTION eligibility, the
                                          "already asked" counter, and replay honesty — NO LONGER the
                                          substance chooser of questions.
  reasoning (model, guard-validated)    = picks the focus, composes the question, proposes competing hypotheses.
Failure -> an honest HOLD `degraded`; the legacy deterministic chooser is NOT a silent fallback.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from app import moves as mv
from app.binding import build_binding
from core.reasoning import hypotheses as hyp
from core.reasoning.contract import NM_CONTRACT_VERSION
from core.reasoning.reasoner import reason_next_move
from core.reasoning.semantic_unknowns import merge_semantic_candidates
from core.reasoning.snapshot import build_snapshot
from core.reasoning.uncertainties import candidate_uncertainties, public_view
from engine.applicable_knowledge import retrieve

log = logging.getLogger("novaliners.adaptive")

POLICY_ADAPTIVE = NM_CONTRACT_VERSION   # contract version recorded in every planner_log entry (owner decision #1)

_INTENT = {"goal": "RESOLVE_GOAL", "contradiction": "RESOLVE_CONTRADICTION", "requirement": "RESOLVE_STATE",
           "fact": "RESOLVE_STATE", "hypothesis": "RESOLVE_STATE", "semantic": "RESOLVE_STATE"}
# CIR-01 (int 19 §11.6): DEGRADED = an operational failure, NOT a business HOLD. The compat DTO keeps
# kind=HOLD, but a stable `error_code` + a dedicated headline/text separate technical failure from
# a business pause.
_ERROR_CODES = {
    "provider_unavailable": "PROVIDER_UNAVAILABLE",
    "schema_invalid": "SCHEMA_INVALID",
    "guard_rejected_after_repair": "GUARD_REJECTED",
    "exception": "APPLICATION_ERROR",
    # MC02-RC-04 (live finding): an UNDERSTANDING failure (schema repair exhausted at the observation
    # stage) is not an application error — its own code so meaning failure is separated from code breakage.
    "understanding_failed": "UNDERSTANDING_FAILED",
}
_DEGRADED_TEXT = {
    "id": "Cerita Anda sudah tersimpan di peta. Ada gangguan teknis saat kami menentukan langkah "
          "berikutnya — tekan tombol lanjutkan untuk mengulang prosesnya; Anda tidak perlu "
          "mengirim ulang cerita.",
    "en": "Your story is saved on the map. Something failed on our side while deciding the next "
          "step — press the continue button to retry; you don't need to resend your story.",
}
_DEGRADED_HEADLINE = {"id": "Jeda teknis", "en": "Technical pause"}
# MC02-RC-04: an UNDERSTANDING-stage failure (not reasoning) — the message differs because the user's
# story was never read; don't imply the engine weighed it and decided to pause.
_UNDERSTANDING_TEXT = {
    "id": "Pesan Anda sudah tersimpan, tetapi kami belum berhasil membacanya menjadi fakta yang bisa "
          "dipakai. Coba kirim ulang intinya dengan kalimat yang lebih sederhana — pesan ini tidak "
          "hilang dan tidak perlu Anda tulis ulang dari awal.",
    "en": "Your message is saved, but we could not read it into facts we can use. Try sending the gist "
          "again in a simpler sentence — this message is not lost and you do not need to retype it all.",
}


def _user_text(s: Any) -> str:
    return "\n".join(f"user: {t}" for r, t in s.transcript if r == "user")


def _requirement_states(inp: dict) -> dict[str, str]:
    return {rid: r.get("satisfaction") for rid, r in (inp.get("requirements") or {}).items()
            if r.get("satisfaction") not in (None, "UNKNOWN") or r.get("conflict")}


def _merged_reason(nav: Any, need_id: str | None, adaptive_part: dict, uncertainties: list[dict]) -> dict:
    """The PRESENTED reason = the planner's trail for the chosen need (stage/why/considered; `input_digest`
    still from the original decision input) + an `adaptive` block (rationale, decision change, claims,
    knowledge). That way "why is this asked" stays traceable back to the planner, and the reasoning
    authority is visible."""
    base = dict(nav.decision["reason"])
    if need_id:
        chosen = next((u for u in uncertainties if u["id"] == need_id), None)
        if chosen and chosen.get("_reason"):
            base = {**chosen["_reason"], "input_digest": base.get("input_digest"), "counts": base.get("counts")}
        elif chosen:
            # CIR-03: semantic candidates (su-* origin) have no planner trail — the presented trail links
            # the need ACTUALLY chosen (need_id + origin), not an old planner need.
            base["need_id"] = need_id
            base["stage"] = "SEMANTIC_UNKNOWN"
            base["origin"] = chosen.get("origin", "semantic_observation")
            base["source_event"] = chosen.get("source_event", "")
    base["policy"] = POLICY_ADAPTIVE
    base["authority"] = f"adaptive:{NM_CONTRACT_VERSION}"
    base["adaptive"] = adaptive_part
    return base


def _presented(proposal: dict, focus: dict, nav: Any, lang: str, uncertainties: list[dict]) -> dict[str, Any]:
    kind = proposal["proposed_move_kind"]
    ftype = focus.get("type")
    if ftype == "uncertainty":
        kind_u = (focus.get("need_id") or "").split(":")[0]
        ftype_key = {"goal": "goal", "contradiction": "contradiction", "requirement": "requirement",
                     "signal": "fact"}.get(kind_u, "requirement")
    else:
        ftype_key = ftype
    intent = ("COLLECT_EVIDENCE" if kind == "EVIDENCE_REQUEST" else "EXECUTE" if kind == "ACTION"
              else "WAIT" if kind == "HOLD" else _INTENT.get(ftype_key, "RESOLVE_STATE"))
    text = proposal.get("move_text") or ""
    chosen = next((u for u in uncertainties if u["id"] == focus.get("need_id")), None)
    cand_head = (nav.candidate_rendered or nav.rendered or {}).get("headline") if nav.decision["kind"] == kind else ""
    headline = (chosen or {}).get("label") or cand_head or {
        "HOLD": "On hold", "ACTION": "Next step", "EVIDENCE_REQUEST": "Needs evidence"}.get(kind, text[:90])
    return {
        "source": "adaptive", "kind": kind, "intent": intent,
        "focus": {"type": ftype, "id": focus.get("id") or ""},
        "stop": kind in ("ACTION", "HOLD"),
        "reason": _merged_reason(nav, focus.get("need_id"), {
            "information_value_rationale": proposal.get("information_value_rationale", ""),
            "expected_decision_change": proposal.get("expected_decision_change", ""),
            "supporting_claim_refs": proposal.get("supporting_claim_refs", []),
            "knowledge_refs": proposal.get("knowledge_refs", []),
            "conditions_for_abstention": proposal.get("conditions_for_abstention", ""),
        }, uncertainties),
        "policy": POLICY_ADAPTIVE,
        "text": text, "headline": headline, "lang": lang,
    }


def _degraded(nav: Any, lang: str, why: str) -> dict[str, Any]:
    # MC02-P1: an UNDERSTANDING failure gets its own text — don't imply the engine weighed the user's
    # story (it was never read) and don't promise the reasoning-retry path (an event with status
    # understanding_failed genuinely must be resent, not retried).
    if why == "understanding_failed":
        text = _UNDERSTANDING_TEXT.get(lang, _UNDERSTANDING_TEXT["en"])
    else:
        text = _DEGRADED_TEXT.get(lang, _DEGRADED_TEXT["en"])
    headline = _DEGRADED_HEADLINE.get(lang, _DEGRADED_HEADLINE["en"])
    return {
        "source": "degraded", "kind": "HOLD", "intent": "WAIT", "focus": {"type": "none", "id": ""},
        "stop": False, "degraded": True,
        "retry_reasoning": True,   # MC01-2: reasoning-only recovery is available (the UI offers a button)
        "error_code": _ERROR_CODES.get(why, "APPLICATION_ERROR"),
        "reason": {"policy": POLICY_ADAPTIVE, "stage": "DEGRADED", "need_id": None,
                   "counts": nav.decision["reason"]["counts"], "why": why},
        "policy": POLICY_ADAPTIVE, "text": text, "headline": headline, "lang": lang,
    }


def _paths_with_feasibility(nav: Any, inp: dict) -> list[dict]:
    """Compact paths for the snapshot + guards, WITH feasibility from `path_set` (an engine finding).

    Read from `nav.path_set`, not recomputed, and does NOT alter the planner input (input_digest/replay
    stay intact). The G6 revision needs it for the `feasibility_supported` basis (int 18 §12.3)."""
    feas = {p.get("path_id"): str(p.get("feasibility") or "")
            for p in ((getattr(nav, "path_set", None) or {}).get("paths") or [])}
    return [{"path_id": p["path_id"], "strategy_id": p.get("strategy_id"), "status": p.get("status"),
             "navigable": bool(p.get("navigable")), "feasibility": feas.get(p["path_id"], "")}
            for p in inp.get("paths") or []]


def decide_next_move(s: Any, llm: Any, nav: Any, event: dict) -> Any:
    """Fill `nav.presented` + `nav.adaptive` and replace `nav.rendered` with the presented step.
    Never raises: any failure becomes a presented `degraded` (visible), the observation stays intact."""
    lang = ((getattr(s, "language", None) or "en")[:2]).lower()
    # S1 telemetry: adaptive_total_s = the whole reasoning orchestration; reasoner_s = the
    # reason_next_move call (including guard + repair inside it). reasoner_s is NESTED in total.
    _t_adaptive0 = time.perf_counter()
    reasoner_s: float | None = None
    if llm is None:   # no provider at all: be honest, invent no step
        nav.presented = _degraded(nav, lang, "provider_unavailable")
        nav.adaptive = {"contract": NM_CONTRACT_VERSION, "status": "DEGRADED", "reason": "provider_unavailable",
                        "stage_s": {"reasoner_s": None,
                                    "adaptive_total_s": round(time.perf_counter() - _t_adaptive0, 2)}}
        nav.candidate_rendered = nav.rendered
        nav.rendered = {"text": nav.presented["text"], "headline": nav.presented["headline"], "lang": lang}
        return nav
    try:
        hyp_changes = hyp.reconcile(s, event_id=event["event_id"])
        inp = nav.planner_input
        # CIR-03 (int 19 §9): candidates = planner needs + open semantic unknowns (origin
        # `semantic_observation`, id `su-...`) — reconciled, deduped, capacity one canonical constant;
        # exclusions recorded (no invisible drop).
        uncertainties, su_report = merge_semantic_candidates(s, candidate_uncertainties(inp))
        try:
            know = retrieve(s.evidence, s.state_graph, _user_text(s))
        except Exception as exc:  # noqa: BLE001 - KB unavailable: NO invented citations, state & decision stay honest
            log.warning("retrieval pengetahuan gagal: %s", exc)
            know = {"kb_version": "unavailable", "menu": [], "considered": 0,
                    "error": f"{type(exc).__name__}: {str(exc)[:120]}"}
        paths = _paths_with_feasibility(nav, inp)
        snapshot = build_snapshot(
            graph=s.state_graph, goal=getattr(s, "goal", None), transcript=s.transcript,
            hypotheses=getattr(s, "hypotheses", None) or {}, uncertainties=public_view(uncertainties),
            knowledge=know["menu"], requirement_states=_requirement_states(inp),
            moves=mv.summaries(s), paths=paths,
            hint={"kind": nav.decision["kind"], "text": (nav.rendered or {}).get("text", "")})
        _t_reason0 = time.perf_counter()
        out = reason_next_move(
            llm, snapshot, language=lang, graph=s.state_graph, hypotheses=getattr(s, "hypotheses", None) or {},
            knowledge_ids={k["id"] for k in know["menu"]}, action_allowed=nav.decision["kind"] == "ACTION",
            design_problems=mv.design_problems, assessment_problems=lambda a: mv.assessment_problems(s, a),
            path_ids={p["path_id"] for p in paths}, paths=paths)
        reasoner_s = round(time.perf_counter() - _t_reason0, 2)
        record: dict[str, Any] = {
            "contract": NM_CONTRACT_VERSION, "status": out["status"], "snapshot_id": snapshot["snapshot_id"],
            "selection": snapshot["selection"], "kb_version": know["kb_version"],
            "knowledge_offered": [k["id"] for k in know["menu"]], "kb_error": know.get("error"),
            "candidates": [u["id"] for u in uncertainties], "attempts": out["attempts"],
            "hypothesis_changes": hyp_changes,
        }
        # CIR-03: observability of semantic-unknown reconciliation (open/offered/excluded + capacity).
        if su_report["open"]:
            record["semantic_unknowns"] = su_report
        # SC-09 (int 16): valid hypotheses are APPLIED regardless of the step's status — meaning
        # acceptance doesn't depend on the legality of the next step. `hypothesis_dropped`
        # (invalid proposals) is recorded for the trail, never silently discarded.
        valid_hyps = out.get("_valid_hypotheses") or []
        if valid_hyps:
            h_changes = hyp.apply_proposals(s, valid_hyps, event["event_id"])
            record["hypothesis_changes"] = hyp_changes + h_changes
        dropped = ((out.get("guard") or {}).get("hypothesis_dropped")) or []
        if dropped:
            record["hypothesis_dropped"] = dropped
        if out["status"] == "ACCEPTED":
            record["proposal"] = out["proposal"]
            record["binding"] = build_binding(s, llm)
            presented = _presented(out["proposal"], out["guard"]["focus"], nav, lang, uncertainties)
            prop = out["proposal"]
            # CIR-05 (int 18 phase C): a compact eligibility rides along in the presentation — the UI
            # reads it for the checkpoint offer; the full decision stays in record["proposal"] (one
            # authority: the parallel nm.v2 block).
            elig = prop.get("checkpoint_eligibility")
            if elig:
                presented["checkpoint"] = {
                    "level": elig.get("level"),
                    "can_offer_checkpoint": bool(elig.get("can_offer_checkpoint")),
                    "external_evidence_pending": bool(elig.get("external_evidence_pending")),
                    # int 18 §13.8 (the honesty card, 16 Oct): the count + rationale disclosure
                    # reaches the UI — the offer text explains WHAT is not yet known, not just
                    # "ready". Ids are not enumerated in the UI; a count + a sentence.
                    "critical_count": len(elig.get("critical_unknown_ids") or []),
                    "nonblocking_count": len(elig.get("nonblocking_unknown_ids") or []),
                    "rationale": str(elig.get("rationale") or "")[:300],
                }
            if prop.get("outcome_assessment"):
                a = mv.apply_assessment(s, prop["outcome_assessment"], event_id=event["event_id"])
                record["outcome_applied"] = {"move_id": a["move_id"], "verdict": a["lifecycle"]}
            if prop["proposed_move_kind"] == "ACTION" and prop.get("move_design"):
                m = mv.create_move(s, design=prop["move_design"], text=prop.get("move_text", ""),
                                   event_id=event["event_id"], binding_id=record["binding"]["binding_id"])
                presented["move_id"] = m["move_id"]
                record["move_created"] = m["move_id"]
        else:
            record["reason"] = out.get("reason")
            record["error_code"] = _ERROR_CODES.get(out.get("reason", ""), "APPLICATION_ERROR")
            presented = _degraded(nav, lang, out.get("reason", "unknown"))
    except Exception as exc:  # noqa: BLE001 - reasoning must never sink the turn
        log.exception("penalaran adaptif gagal; HOLD degraded")
        record = {"contract": NM_CONTRACT_VERSION, "status": "DEGRADED", "reason": f"{type(exc).__name__}: {str(exc)[:160]}",
                  "error_code": "APPLICATION_ERROR"}
        presented = _degraded(nav, lang, "exception")
    record["stage_s"] = {"reasoner_s": reasoner_s,
                         "adaptive_total_s": round(time.perf_counter() - _t_adaptive0, 2)}
    nav.presented = presented
    nav.adaptive = record
    nav.candidate_rendered = nav.rendered
    nav.rendered = {"text": presented["text"], "headline": presented["headline"], "lang": lang}
    return nav
