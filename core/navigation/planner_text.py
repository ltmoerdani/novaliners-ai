"""Question Planner text renderer — the words for A decision, kept separate from the decision itself.

internal-docs §25. The decision (`plan_next_move`) states WHAT needs to be known or done and
WHY; this module only writes it out as sentences. The separation is deliberate:

  - decisions can be replayed and tested without depending on how the sentence sounds;
  - switching language, or handing rendering to an LLM (FUTURE), cannot shift the decision;
  - text is never a source of status: it reads `texts` on the input (titles, reasons, how) already derived
    from registry/presentation/domain data by the input assembler.

The renderer is deterministic and LLM-free. Sentence frames exist in two languages (`en`, `id`); the content
(requirement titles, signal reasons) comes from the data and carries its own language. When the requested
language is unavailable for that content, the machine text is used as-is (nothing is invented)."""

from __future__ import annotations

from typing import Any, Mapping

from core.navigation.planner import (
    INTENT_APPLICABILITY,
    INTENT_CONTRADICTION,
    INTENT_EVIDENCE,
    INTENT_EXECUTE,
    INTENT_GOAL,
    INTENT_PRESENT,
    INTENT_STATE,
    INTENT_WAIT,
)

_FRAMES: dict[str, dict[str, str]] = {
    "en": {
        "goal": "To map your options I first need a clear goal. What do you want to reach, and by when?",
        "applicability": (
            "Before I can say whether “{title}” fits you, I need this: {reason}. What can you tell me?"
        ),
        "route_applicability": (
            "To see whether “{title}” fits you, tell me what you sell and who it is for."
        ),
        "state_requirement": (
            "I can't tell yet where you stand on “{title}”.{how} Real examples or numbers help most."
        ),
        "state_check": "I can't tell yet: {reason}. What can you tell me about it? Real numbers help most.",
        "state_signal": "To find a way forward I need to know this: {reason}. What can you tell me about it?",
        "evidence_requirement": (
            "I still can't confirm “{title}” from what you told me. Can you give one concrete example, "
            "number or document?{how}"
        ),
        "evidence_check": "Still unclear: {reason}. Can you give one concrete example or number?",
        "evidence_signal": "Still unclear: {reason}. Can you give one concrete example or number?",
        "contradiction": (
            "What you told me about “{title}” points in two directions. Which one is closer to the truth? "
            "One concrete example would settle it."
        ),
        "execute": "You have enough to act on. First step: {activity}.",
        "execute_again": "Noted. Your next step has not changed: {activity}.",
        "present": (
            "I have what I need to map your options. Build your diagnosis to see them and the first step."
        ),
        "present_again": (
            "Noted. I can already map your options; build your diagnosis whenever you are ready."
        ),
        "hold": "I can't point to a safe next step yet. Tell me anything new and I will look again.",
        "hold_again": (
            "Still nothing I can point to as a safe next step. Tell me anything new and I will look again."
        ),
        "verify": "You said you did “{title}”. What came of it? One concrete result or number is enough.",
    },
    "id": {
        "goal": "Supaya bisa memetakan pilihan Anda, saya perlu tujuan yang jelas dulu. Apa yang ingin Anda "
        "capai, dan kapan?",
        "applicability": "Sebelum bisa bilang apakah “{title}” cocok untuk Anda, saya perlu tahu ini: "
        "{reason}. Apa yang bisa Anda ceritakan?",
        "route_applicability": "Untuk melihat apakah “{title}” cocok, ceritakan apa yang Anda jual dan "
        "untuk siapa.",
        "state_requirement": "Saya belum bisa menilai posisi Anda soal “{title}”.{how} Contoh nyata atau "
        "angka paling membantu.",
        "state_check": "Saya belum bisa menilai: {reason}. Apa yang bisa Anda ceritakan? Angka nyata paling "
        "membantu.",
        "state_signal": "Untuk menemukan jalan ke depan saya perlu tahu ini: {reason}. Apa yang bisa Anda "
        "ceritakan?",
        "evidence_requirement": "Saya masih belum bisa memastikan “{title}” dari yang Anda ceritakan. "
        "Bisa beri satu contoh, angka, atau dokumen yang konkret?{how}",
        "evidence_check": "Masih belum jelas: {reason}. Bisa beri satu contoh atau angka yang konkret?",
        "evidence_signal": "Masih belum jelas: {reason}. Bisa beri satu contoh atau angka yang konkret?",
        "contradiction": "Yang Anda ceritakan soal “{title}” menunjuk dua arah. Mana yang lebih mendekati "
        "kenyataan? Satu contoh konkret akan menyelesaikannya.",
        "execute": "Anda sudah punya cukup untuk bertindak. Langkah pertama: {activity}.",
        "execute_again": "Dicatat. Langkah berikutnya tidak berubah: {activity}.",
        "present": "Saya sudah punya yang saya butuhkan untuk memetakan pilihan Anda. Bangun diagnosis untuk "
        "melihatnya dan langkah pertamanya.",
        "present_again": "Dicatat. Saya sudah bisa memetakan pilihan Anda; bangun diagnosis kapan pun Anda "
        "siap.",
        "hold": "Saya belum bisa menunjuk langkah berikutnya yang aman. Ceritakan hal baru apa pun dan saya "
        "lihat lagi.",
        "hold_again": "Masih belum ada langkah berikutnya yang aman. Ceritakan hal baru apa pun dan saya "
        "lihat lagi.",
        "verify": "Anda bilang sudah mengerjakan “{title}”. Apa hasilnya? Satu hasil atau angka "
        "konkret cukup.",
    },
}


def _frames(lang: str) -> dict[str, str]:
    return _FRAMES.get((lang or "en").lower()[:2]) or _FRAMES["en"]


def _txt(texts: Mapping[str, Any], need_id: str, field: str) -> str:
    v = ((texts.get(need_id) or {}).get(field)) or {}
    return str(v.get("text") or "").strip().rstrip(".")


def _how(texts: Mapping[str, Any], need_id: str) -> str:
    """How to verify, as a standalone sentence: registry fallback text often lacks trailing punctuation, so
    without a period it glues onto the next sentence ("... right now Real examples ...")."""
    h = ((texts.get(need_id) or {}).get("how")) or {}
    t = str(h.get("text") or "").strip()
    if not t:
        return ""
    return f" {t}" if t[-1] in ".!?" else f" {t}."


def headline(decision: Mapping[str, Any], inp: Mapping[str, Any]) -> str:
    """Short focus headline (for the UI): what is being figured out. From data text, never invented."""
    texts = inp.get("texts") or {}
    focus = decision.get("focus") or {}
    ttype, tid = focus.get("type"), str(focus.get("id") or "")
    if ttype == "goal":
        return "Your goal" if (inp.get("lang") or "en") != "id" else "Tujuan Anda"
    if ttype == "requirement":
        return _txt(texts, f"requirement:{tid}", "title") or tid
    if ttype == "check":
        return _txt(texts, f"check:{tid}", "title") or _txt(texts, f"check:{tid}", "reason") or tid
    if ttype == "signal":
        return _txt(texts, f"signal:{tid}", "reason") or tid
    if ttype == "path":
        return _txt(texts, f"path:{tid}", "title") or tid
    if ttype == "route":
        return _txt(texts, f"route:{tid}", "title") or tid
    if ttype == "node":
        node_req = (decision.get("payload") or {}).get("requirement_id")
        return _txt(texts, f"requirement:{node_req}", "title") if node_req else tid
    return ""


def _repeats(decision: Mapping[str, Any], previous: Mapping[str, Any] | None) -> bool:
    """The exact same step as the one just presented, and it is a "stopping" kind (ACTION or HOLD).
    Questions are never treated as repeats: asking again is a planner decision (`ASK_CAP`)."""
    return bool(
        previous
        and decision.get("kind") in ("ACTION", "HOLD")
        and previous.get("kind") == decision.get("kind")
        and previous.get("intent") == decision.get("intent")
        and previous.get("focus") == decision.get("focus")
    )


def render_move(
    decision: Mapping[str, Any],
    inp: Mapping[str, Any],
    lang: str | None = None,
    previous: Mapping[str, Any] | None = None,
) -> dict[str, str]:
    """Decision + input -> {text, headline, lang}. Deterministic; never changes the decision.

    `previous` = the decision presented on the previous turn (words only): the SAME ACTION/HOLD step is voiced
    as "unchanged" instead of repeating the identical sentence. Not a decision input (excluded from
    `input_digest`)."""
    lang = lang or inp.get("lang") or "en"
    f = _frames(lang)
    again = "_again" if _repeats(decision, previous) else ""
    texts = inp.get("texts") or {}
    intent = decision.get("intent")
    focus = decision.get("focus") or {}
    ttype, tid = focus.get("type"), str(focus.get("id") or "")
    payload = decision.get("payload") or {}

    text = f["hold"]
    if intent == INTENT_GOAL:
        text = f["goal"]
    elif intent == INTENT_PRESENT:
        text = f["present" + again]
    elif intent == INTENT_WAIT:
        text = f["hold" + again]
    elif intent == INTENT_EXECUTE:
        activity = _txt(texts, f"node:{tid}", "how") or payload.get("activity") or headline(decision, inp)
        text = f["execute" + again].format(activity=(activity or tid).rstrip("."))
    elif intent == INTENT_CONTRADICTION:
        text = f["contradiction"].format(title=_txt(texts, f"contradiction:{tid}", "title") or tid)
    elif intent == INTENT_APPLICABILITY:
        if ttype == "path":
            text = f["applicability"].format(
                title=_txt(texts, f"path:{tid}", "title") or tid,
                reason=_txt(texts, f"applicability:{tid}", "reason") or payload.get("signal") or "",
            )
        else:
            text = f["route_applicability"].format(title=_txt(texts, f"route:{tid}", "title") or tid)
    elif intent in (INTENT_STATE, INTENT_EVIDENCE):
        ev = intent == INTENT_EVIDENCE
        if ttype == "requirement":
            key = "evidence_requirement" if ev else "state_requirement"
            text = f[key].format(title=_txt(texts, f"requirement:{tid}", "title") or tid,
                                 how=_how(texts, f"requirement:{tid}"))
        elif ttype == "check":
            key = "evidence_check" if ev else "state_check"
            reason = _txt(texts, f"check:{tid}", "reason") or _txt(texts, f"check:{tid}", "title") or tid
            text = f[key].format(reason=reason)
        elif ttype == "signal":
            key = "evidence_signal" if ev else "state_signal"
            text = f[key].format(reason=_txt(texts, f"signal:{tid}", "reason") or tid)
        elif ttype == "node":
            node_req = payload.get("requirement_id")
            text = f["verify"].format(
                title=_txt(texts, f"requirement:{node_req}", "title") or payload.get("activity") or tid
            )
    return {"text": " ".join(text.split()), "headline": headline(decision, inp), "lang": lang}
