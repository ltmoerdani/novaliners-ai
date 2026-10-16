"""Stage: opportunity typing & clustering (internal-docs §7)."""
from __future__ import annotations

import re as _re

from core.schema.evidence import EvidenceItem

_EXPANSION_MARKERS = (
    "klien", "retainer", "langganan", "sudah bayar", "bayar", "perpanjang", "renewal",
    "upsell", "pernah minta", "minta bantuan",
)
# iter-19 (P1-4 user §8): REPRICING = a revenue path with ~zero capacity impact —
# existing clients + a new price + a renewal window. Detected deterministically,
# may come from self_reported (an unexecuted plan ≠ not an opportunity).
_REPRICING_MARKERS = (
    "naik harga", "naik-in", "kenaikan harga", "repricing", "harga baru", "renewal",
    "perpanjang kontrak",
)
_REPRICING_CLIENT = ("klinik", "restoran", "resto", "sekolah", "klien", "retainer", "existing")
_INTERVENTIONS = {
    "repricing": "susun proposal repricing SEBELUM jendela renewal (capacity-impact paling kecil)",
    "expansion": "tawarkan penambahan lingkup/upsell",
    "recovery": "sebut angka + follow-up terjadwal",
    "reactivation": "hubungi ulang dengan jalan keluar tanpa tekanan",
}
# iter-19 (P1 user §9): eligibility invariant — the entity MUST be a concrete
# commercial object. The _entity_of fallback (capitalized word / cut at 24 chars) gave birth to
# 'satu', 'rp10', 'volume' — dropped, not displayed.
_ENTITY_GENERIC = {
    "satu", "dua", "tiga", "volume", "jumlah", "target", "rencana", "harga",
    "revenue", "omzet", "penghasilan", "konversi", "kasus", "penawaran",
    "hasil", "kerja", "paket", "metrik", "pipeline",
    "angka", "lead", "prospek", "inquiry", "channel", "pasar", "bisnis", "usaha",
    "nilai", "scope", "lingkup", "jasa", "produk", "kontak", "list", "bulan",
    "minggu", "hari", "kapasitas", "delivery", "gap",
}
_ENTITY_PRICE_RE = _re.compile(r"^(rp\d|\d)")
_TYPE_PRIORITY = {"repricing": 0, "recovery": 1, "reactivation": 2, "expansion": 3}
_RECOVERY_MARKERS = ("diam", "stall", "belum balas", "tidak balas", "berhenti balas", "tanya harga")
_REACTIVATION_MARKERS = ("pikir dulu", "pikir-pikir", "nanti", "sempat hilang", "diabaikan", "lama tidak")


# Tier-2 #8 calibration (iter-12): dedup opportunities by ENTITY, not by signal prefix —
# so it does not produce 4x "expansion" from one and the same client.
_ENTITY_RE = _re.compile(
    r"\b(klinik|resto|restoran|sekolah|cafe|kafe|toko|salon|bengkel|laundry|owner)\b", _re.I
)


def _entity_of(text: str) -> str:
    m = _ENTITY_RE.search(text or "")
    if m:
        return m.group(1).lower()
    for word in (text or "").split():
        w = word.strip(".,;:!?()")
        if len(w) > 2 and w[0].isupper() and w.lower() not in ("saya", "lead", "klien", "bulan", "linkedin"):
            return w.lower()
    return (text or "")[:24].lower()


def cluster_by_topic(evidence: list[EvidenceItem]) -> dict[str, int]:
    """iter-15 (P1 §10 user): Evidence record != independent observation !=
    evidence cluster. Topic clustering based on the observation DOMAIN (not token
    similarity): revenue, acquisition, conversion, proof, capacity, pricing, tools.
    Return {topic: n_evidence} — n_cluster = number of filled topics."""
    TOPIC_KW = {
        "revenue": ("rp", "juta", "jt", "revenue", "penghasilan", "retainer", "transfer", "bulan)"),
        "acquisition": (
            "inquiry", "lead masuk", "outbound", "outreach", "referral", "instagram",
            "linkedin", "dm", "prospek",
        ),
        "conversion": (
            "tanya harga", "quote", "penawaran", "closing", "balas", "telat", "hilang",
            "menghilang", "kompetitor",
        ),
        "proof": ("portofolio", "contoh hasil", "bukti", "cerita hasil", "situs"),
        "capacity": ("jam/minggu", "jam per minggu", "kapasitas", "slot", "tersedot", "saturasi"),
        "pricing": ("harga", "price", "anchor", "rate", "rp8", "rp9", "rp7", "rp12"),
        "tools": ("template", "notebook", "spreadsheet", "sheets", "notion", "crm", "whatsapp"),
    }
    counts: dict[str, int] = {}
    for e in evidence:
        if getattr(e, "is_gap", False):
            continue
        t = (e.signal or "").lower()
        for topic, kws in TOPIC_KW.items():
            if any(k in t for k in kws):
                counts[topic] = counts.get(topic, 0) + 1
                break  # satu evidence satu topic dominan
    return counts


def build_opportunities(evidence: list[EvidenceItem]) -> list[dict]:
    """Deterministic: evidence → a list of commercial objects of different TYPES.
    iter-15 (P0 run Rina): ELIGIBILITY GATE — evidence may only become an
    opportunity when it meets its type's criteria. 'Nol transfer' is NOT expansion;
    'WhatsApp' is not an entity. If it does not pass → NO OPPORTUNITY, not forced.
    Expansion: an ACTIVE client + a positive fact (not negation/zero). Recovery/
    reactivation: a specific lead that stalled/was lost."""
    _NEGATIVE_FACT = _re.compile(
        r"\bnol\b|^0\b|0 (?:dari|transfer|closing|lead)|tidak ada|belum pernah|belum tindak"
        r"|belum terjawab|belum dijawab|belum ada"
    )
    _BAD_ENTITY = {"nol", "whatsapp", "harga", "rp", "0", "transfer", "template", "script", "gap"}
    out: list[dict] = []
    for e in evidence:
        if getattr(e, "is_gap", False):
            continue
        raw = e.signal or ""
        t = raw.lower()
        # repricing: existing client + new price + renewal window (self_reported OK —
        # an unexecuted plan remains the next-largest opportunity)
        is_repricing = (
            any(k in t for k in _REPRICING_MARKERS)
            and any(k in t for k in _REPRICING_CLIENT)
            and _re.search(r"rp\s?\d", t)
        )
        if not is_repricing and e.level not in ("transactional", "outcome", "behavioral"):
            continue
        if not any(
            k in t
            for k in (
                "lead", "prospek", "inquiry", "klien", "owner", "resto", "klinik",
                "sekolah", "renewal", "harga",
            )
        ):
            continue
        if _NEGATIVE_FACT.search(t):
            continue  # negative/absence facts are not an opportunity
        if is_repricing:
            typ = "repricing"
        elif any(k in t for k in _REACTIVATION_MARKERS):
            typ = "reactivation"
        elif any(k in t for k in _RECOVERY_MARKERS):
            typ = "recovery"
        elif any(k in t for k in _EXPANSION_MARKERS):
            typ = "expansion"
            # expansion needs an explicitly ACTIVE client (not just mentioning 'klien')
            if not any(
                k in t
                for k in ("retainer", "aktif", "terkonversi", "berjalan", "closing", "tervalidasi")
            ):
                continue
        else:
            continue
        entity = _entity_of(raw)
        if entity.lower() in _BAD_ENTITY or entity.lower() in _ENTITY_GENERIC \
                or _ENTITY_PRICE_RE.match(entity):
            continue  # iter-19: generic/price entities ('satu','rp10','volume') are not a commercial object
        out.append({
            "type": typ,
            "entity": entity,
            "evidence_id": e.id,
            "signal": raw[:110],
            "intervention": _INTERVENTIONS[typ],
        })
    # dedup by (type, entity) — kalibrasi iter-12: satu klien = satu objek
    seen, uniq = set(), []
    for o in out:
        k = (o["type"], o["entity"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(o)
    # iter-19: repricing/recovery first — small capacity-impact path + strong evidence
    uniq.sort(key=lambda o: _TYPE_PRIORITY.get(o["type"], 9))
    return uniq[:6]


# ---------------------------------------------------------------------------
# Tier-3 #12 (iter-11): Revenue Decision Spectrum — decision + trigger +
# evidence needed before moving up a level (replacing the binary verdict).
# ---------------------------------------------------------------------------


FUNNEL_STAGES = [
    "INQUIRY", "PRICE_SHOWN", "REPLY", "DISCOVERY", "PROPOSAL", "NEGOTIATION", "CLOSE", "REVENUE",
]

