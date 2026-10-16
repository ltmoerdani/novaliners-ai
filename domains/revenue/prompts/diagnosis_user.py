"""Diagnosis user-prompt template (F3, internal-docs §9) — revenue domain.

Cut-paste verbatim from the f-string block in agents/diagnosis.synthesize() — zero
text changes. Domain vocabulary (PRICE COMMUNICATION / VALUE FRAMING / VALUE
PROOF, number rules, NO_FIT) belongs to the domain; agents only assemble the arguments.
schema_hint_str = the result of `schema_hint(DiagnosisDraft)` rendered by the caller —
this module is pure text, with no schema import."""
from __future__ import annotations


def goal_context_block(goal_obj: dict | None) -> str:
    """Structured ACTIVE GOAL block for the diagnosis prompt (mandate §7.3, F-14).

    Structured Goal = authority; the draft narrative MUST serve this goal with its own
    unit/target and MUST NOT mention other targets/numbers as the user's goal. Empty when there is no
    structured goal (legacy session) - old behavior intact. Deterministic so the mock provider
    can produce drafts consistent with the scenario (F-15)."""
    if not goal_obj:
        return ""
    mid = goal_obj.get("metric_id") or (
        "revenue_monthly" if goal_obj.get("metric") == "revenue_monthly" else "")
    if not mid:
        return ""
    rows: list[str] = [
        f"metric: {mid}",
        f"unit: {goal_obj.get('unit', '')}",
        f"direction: {goal_obj.get('direction', '')}",
    ]
    if goal_obj.get("target") is not None:
        rows.append(f"target: {goal_obj['target']}")
    if goal_obj.get("target_min") is not None or goal_obj.get("target_max") is not None:
        rows.append(f"range: {goal_obj.get('target_min')} - {goal_obj.get('target_max')}")
    if goal_obj.get("measurement_window_days") is not None:
        rows.append(f"measurement window: {goal_obj['measurement_window_days']} days")
    if goal_obj.get("deadline_days") is not None:
        rows.append(f"deadline: in {goal_obj['deadline_days']} days")
    if goal_obj.get("success_definition"):
        rows.append(f"qualification: {goal_obj['success_definition']}")
    confirmed = goal_obj.get("target_origin") == "explicit_input"
    rows.append("target confirmed by user: " + ("yes" if confirmed else "no (parsed, not confirmation)"))
    if goal_obj.get("desire"):
        rows.append(f"user stated it as: {goal_obj['desire']}")
    return ("\nACTIVE GOAL (structured, authoritative - the diagnosis narrative MUST serve THIS goal; "
            "use ITS unit and target; NEVER state another amount, target, or outcome as the user's goal; "
            "a target that is not user-confirmed stays a recorded intention, not a fact):\n"
            + "\n".join(f"- {r}" for r in rows) + "\n")



def build_user_prompt(
    goal: str,
    language: str,
    ev_lines: str,
    constraint_lines: str,
    transcript_tail: str,
    schema_hint_str: str,
    intervention_menu_str: str = "",
    historical_evidence_str: str = "",
) -> str:
    """Assemble the diagnosis user-prompt. Arguments are plain strings rendered by the caller.
    intervention_menu_str (internal-docs §6.1): pre-draft KB intervention menu — empty =
    degrade-safe (pre-fix behavior, without the menu block).
    historical_evidence_str (DCP-01, int 16 §S1): claims that were ALREADY replaced, split from EVIDENCE
    so they are never read as the current state; only to explain changes."""
    _menu_block = (
        "INTERVENSI KANDIDAT (dari knowledge base — pilihan aksi HARUS dari menu ini):\n"
        f"{intervention_menu_str}\n"
        "IMPORTANT (internal-docs): NBA = ADAPTASI satu intervensi di atas ke konteks "
        "user (Novaliners bukan book quote machine — adaptasi wording & 7-hari plan ke kasus, "
        "tapi PILIHAN AKSI dari menu). Isi grounded_intervention_id dengan ID intervensi yang "
        "menjadi dasarnya. Kosongkan HANYA bila tidak ada satu pun item yang relevan.\n"
        if intervention_menu_str.strip()
        else ""
    )
    _hist_block = (
        "HISTORICAL CLAIMS (SUPERSEDED — these are NOT current facts. They are kept ONLY so you can "
        "explain what changed. Never treat them as current evidence, never map their ids into "
        "evidence_map, and never rebuild the superseded state as if it were still true):\n"
        f"{historical_evidence_str}\n"
        if historical_evidence_str.strip()
        else ""
    )
    return f"""{_menu_block}GOAL: {goal} | LANG: {language}
EVIDENCE (current, authoritative):
{ev_lines}
{_hist_block}ONTOLOGY:
{constraint_lines}
TRANSCRIPT (tail):
{transcript_tail}
Return JSON:
{schema_hint_str}
IMPORTANT: bukti duplikat (fakta sama dengan kalimat berbeda) HARUS di-map ke SATU evidence_id saja —
jangan hitung ganda. Gunakan hanya bukti unik di evidence_map.
IMPORTANT (iter-9): petakan SEMUA bukti relevan. Jangan hanya satu bukti per constraint — konvergensi
(banyak bukti) adalah kekuatan, dan satu bukti boleh mendukung LEBIH DARI SATU constraint. Constraint
tanpa bukti ter-mapping akan tampak lemah meski buktinya ada di ledger.
CATATAN ANGKA: dua statement dengan struktur mirip tapi ANGKA BERBEDA adalah fakta berbeda
(mis. 'klinik Rp12jt' vs 'resto Rp10jt') — keduanya harus masuk sebagai bukti terpisah.

BEDAKAN TIGA HAL INI (iter-11, wajib — jangan semuanya dijadikan C6.3):
- PRICE COMMUNICATION: "berapa harganya?" tidak dijawab dengan angka → itu eksekusi/arsitektur
harga, bukan value framing.
- VALUE FRAMING: angka disebut, TAPI tidak dijelaskan dalam bahasa masalah pembeli
(kenapa segitu, untuk hasil apa).
- VALUE PROOF: klaim nilai/harga tidak ditopang bukti hasil terukur dari klien sebelumnya.
Lead yang mati SETELAH harga diucapkan memindahkan kecurigaan ke value framing/proof;
lead yang mati KARENA harga tidak pernah diucapkan tetap di ranah komunikasi harga & eksekusi.
Kalau tidak ada satupun constraint di ontology yang cukup menjelaskan bukti, tulis
primary_constraint_id = "NO_FIT" dan jelaskan hipotesis bebas di primary_constraint
(jangan memaksa constraint terdekat)."""
