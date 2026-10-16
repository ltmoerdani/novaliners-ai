"""Guard: experiment population integrity (internal-docs §7, layer guards).
Cut-paste from agents/diagnosis.py — zero logic changes."""
from __future__ import annotations

import re

from core.schema.evidence import EvidenceItem

# Type note: `draft` is DiagnosisDraft-like (duck-typed) from the
# agents.diagnosis module — only the next_best_action/first_step_today/day_by_day/
# outreach_script fields are read.


def _guard_experiment_population(
    draft, evidence: list[EvidenceItem]
) -> str | None:
    """iter-14 (P0 user): DETERMINISTIC post-check — experiment subjects
    named in the plan MUST exist in the evidence ledger. The LLM must not create
    subjects ('LinkedIn A', a person's name, '3 leads') that are absent from the evidence.
    Returns engine_note when there is a violation, None when clean.
    Heuristic: named lead labels ('LinkedIn A/B', consecutive capitalized names) in
    the plan text are checked for presence in the evidence text."""
    ledger = " ".join(f"{(e.signal or '')} {(e.source_quote or '')}" for e in evidence)
    # iter-21 fix (manual-Rina bug): ready-to-use script blocks MUST be excluded
    # from subject scanning — script opening sentences ('Buka Notes', 'Halo Kak',
    # 'Saya Rina') are not experiment subjects. Scanning 2+-capitalized words caught
    # narrative fragments & greetings as 'person names' → 4 false positives per session.
    _script_blocks = []
    if getattr(draft, "outreach_script", None):
        _script_blocks.append(str(draft.outreach_script))
    plan_parts: list[str] = []
    # J1 (internal-docs): day_by_day is now an object with a .text attribute (or legacy str).
    _dd_texts = [str(getattr(x, "text", x)) for x in (draft.day_by_day or [])]
    for part in filter(None, [
        draft.next_best_action, draft.first_step_today, " ".join(_dd_texts),
    ]):
        _p = str(part)
        # drop pieces that start with a script marker (quote/block) from the plan part
        for marker in ("Script", "script:", "```", '"Halo', "'Halo"):
            if marker in _p:
                _p = _p.split(marker)[0]
        plan_parts.append(_p)
    if _script_blocks:
        # subjects FROM THE SCRIPT count as verified as long as they appear in the ledger OR
        # are a clear script opening phrase (greeting/imperative) —
        # subject scanning only runs on the plan, not inside the script.
        plan = " ".join(plan_parts)
        # script is not scanned as a subject; the ledger is extended to cross-check names in the script
        ledger = ledger + " " + " ".join(_script_blocks)
    else:
        plan = " ".join(plan_parts)
    # Subject candidates: 'LinkedIn A/B/1/2', 'Lead X', person names (2+ capitalized words
    # at the start), or a repeated single capitalized token.
    candidates = set()
    for m in re.finditer(r"\b((?:LinkedIn|Instagram|TikTok|WhatsApp|Email|DM)\s+[A-Z0-9]\b)", plan):
        # iter-18 fix (run-5): a DIGIT label immediately followed by a small word is a
        # time/quantity fragment ('DM 3 minggu lalu'), not a subject label.
        after = plan[m.end():m.end() + 2]
        if m.group(1).split()[-1].isdigit() and re.match(r"\s[a-z]", after or ""):
            continue
        candidates.add(m.group(1))
    for m in re.finditer(r"\b([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,}){1,2})\b", plan):
        cand = m.group(1)
        if cand.lower() not in ledger.lower():
            candidates.add(cand)
    fabricated = [c for c in candidates if c.lower() not in ledger.lower()]
    # iter-17 fix: tool whitelist & test mode names — two consecutive runs of false positives
    # ('Google Docs', 'Intervention Probe') made the flag be ignored by habit.
    _GUARD_STOP = {
        "google docs", "intervention probe", "diagnostic probe", "controlled experiment",
        "operational trial", "validation experiment", "whatsapp", "instagram", "linkedin",
        "google sheets", "notion", "template",
        # iter-21 fix: phrases common in scripts/sentence starts, not person names
        "buka notes", "halo kak", "kalau kakak", "saya rina", "notes", "kak",
        "hari ini", "hari 1", "hari 2", "hari 3", "hari 4",
    }
    fabricated = [c for c in fabricated if c.lower() not in _GUARD_STOP]
    # Count the leads claimed vs those present in the evidence
    claimed = re.search(r"\b([3-9]|\d{2,})\s*(?:lead|prospek|orang)", plan, re.I)
    # iter-18 fix (run-5): count DISTINCT lead labels in the ledger (case-insensitive),
    # not the old `[A-Z0-9]\b` regex that only matched 1-char tokens ('DM 2') —
    # lowercase multi-word ledger entries ('lead skincare', 'lead toko online') were not
    # counted → a false '0 identified'. Generic/channel labels are stoplisted.
    _stop_labels = {
        "instagram", "linkedin", "tiktok", "whatsapp", "email", "google", "wa",
        "web", "website", "yang", "lain", "lainnya", "eligible", "baru", "ini",
        "itu", "dari", "sudah", "belum", "tidak", "masih", "ke", "untuk",
    }
    _ledger_labels = re.findall(r"(?:linkedin|dm|lead|prospek)\s+([a-z0-9][\w-]*)", ledger, re.I)
    # pure digits ('DM 2 hari lalu') = a time fragment, not a subject label
    n_named_in_ledger = len({lbl.lower() for lbl in _ledger_labels if not lbl.isdigit()} - _stop_labels)
    notes = []
    if fabricated:
        notes.append(
            "Subjek berikut DISEBUT di rencana tapi TIDAK ADA di evidence ledger: "
            + ", ".join(sorted(fabricated))
            + " — jangan dianggap subject eksperimen yang valid"
        )
    if claimed and int(claimed.group(1)) >= 2 and n_named_in_ledger < int(claimed.group(1)):
        notes.append(
            f"Rencana menyebut {claimed.group(1)} lead, tapi hanya {n_named_in_ledger} yang "
            "teridentifikasi eksplisit di bukti. Nyatakan: 'Current eligible sample: "
            f"{n_named_in_ledger} identified lead. Additional eligible leads have not "
            "been identified in the evidence.' Kecilkan scope, JANGAN mengarang subject."
        )
    if not notes:
        return None
    return "⚠ EXPERIMENT POPULATION INTEGRITY:\n" + "\n".join(f"- {n}" for n in notes)



def _guard_probe_population_convention(draft, evidence: list) -> str | None:
    """iter-19 (P1 user #3): probe population conventions MUST be consistent.

    - Eligible probe (conversion experiment) = a lead asking for a price but NOT yet
      having heard a number.
    - Recovery = a lead that HAS heard/received a number and then stayed silent.

    If the plan targets leads that already received a number WITHOUT
    declaring this convention, flag it: two different population definitions must not
    be silently interchanged."""
    plan = " ".join(filter(None, [
        getattr(draft, "next_best_action", ""),
        getattr(draft, "first_step_today", ""),
        " ".join(str(getattr(x, "text", x)) for x in (getattr(draft, "day_by_day", []) or [])),
        getattr(draft, "outreach_script", "") or "",
    ])).lower()
    ledger = " ".join(
        f"{(e.signal or '')} {(e.source_quote or '')}" for e in evidence
    ).lower()

    # target = a lead that ALREADY received a number?
    targets_priced = re.search(
        r"(sudah|pernah|yang sudah)\s*(dengar|terima|dapat|menerima|mendengar)"
        r"[^.]{0,24}(harga|angka|rp\s?\d)", plan
    ) or re.search(r"rp\s?\d[^.]{0,40}(dengar|terima|lempar|sebut)", plan)
    if not targets_priced:
        return None
    # a lead that ALREADY heard the price is indeed in the ledger (legit recovery)?
    priced_in_ledger = re.search(
        r"(dengar|terima|kasih|beri|sebut)[^.]{0,24}(harga|angka|rp\s?\d)", ledger
    ) or "rp9" in ledger or "rp7" in ledger
    # iter-19 fix: the MANDATORY declaration = the explicit phrase 'bukan sampel eligible …',
    # NOT merely the word 'recovery' in the plan — that word alone does not distinguish
    # population conventions (this is precisely what must be declared).
    declared = ("bukan sampel eligible" in plan) or ("bukan eksperimen konversi" in plan)
    if priced_in_ledger and not declared:
        return (
            "⚠ POPULASI PROBE: target adalah lead yang SUDAH menerima angka — "
            "mereka BUKAN sampel eligible eksperimen konversi (eligible = minta "
            "harga, belum dengar angka). Nyatakan eksplisit: 'ini uji RECOVERY "
            "dengan angka + bukti baru', jangan disebut uji konversi."
        )
    return None
