"""Stage: deterministic text parser (internal-docs §7). Cut-paste from schemas/models.py."""
from __future__ import annotations

import re as _re
from typing import Optional


def _extract_rp(text: str) -> Optional[float]:
    """Take the first Rupiah number → value in MILLIONS. E1 (iter-10): the units
    'ribu'/'rb' are counted ÷1000 ('Rp234 ribu' = 0.234 million, NOT 234 million —
    the run v6 bug that produced declared Rp234 jt from an hourly rate).
    Without a unit: a number ≥1000 = full rupiah, <1000 = millions (ID convention)."""
    m = _re.search(r"rp\s*([\d.,]+)\s*(juta|jt|ribu|rb)?", text.lower())
    if not m:
        return None
    num = m.group(1).replace(".", "").replace(",", ".")
    try:
        val = float(num)
    except ValueError:
        return None
    unit = (m.group(2) or "").lower()
    if unit in ("ribu", "rb"):
        return round(val / 1000.0, 4)
    if unit in ("juta", "jt"):
        return val
    if val >= 1000:
        return val / 1_000_000.0
    return val


# E2 (iter-10): RATE/UNIT context is not recurring monthly income —
# 'Rp234 ribu per jam', 'Rp48 juta per semester', 'Rp1-2 juta per proyek'.
_RATE_RE = _re.compile(
    r"rp\s*[\d.,]+\s*(?:juta|jt|ribu|rb)?\s*(?:per|/)\s*"
    r"(?:jam|hari|proyek|kontrak|semester|tahun)"
)


def _is_rate_signal(text: str) -> bool:
    """True when the Rp number is a rate/unit (per hour/project/semester/…),
    not monthly income. This kind of signal MUST NOT become a revenue candidate."""
    return bool(_RATE_RE.search((text or "").lower()))


# E3 (iter-10): an ad-hoc/one-off number is not a recurring revenue component.
_ADHOC_RE = _re.compile(
    r"ad\s*-?\s*hoc|sekali\s*(?:jadi|bayar|proyek)?|insidental|sesekali|"
    r"kadang-kadang|kadang|proyek kecil|tak\s+tiap\s+bulan|tidak\s+tiap\s+bulan"
)


def _extract_rp_range_mid(text: str) -> Optional[float]:
    """'Rp8-12 juta' / 'rp8-10jt' → midpoint (10.0 / 9.0). Used for deal size:
    one representative number, not a lower/upper bound."""
    m = _re.search(r"rp\s*([\d.,]+)\s*[-–]\s*([\d.,]+)\s*(juta|jt)?", text.lower())
    if not m:
        return None
    try:
        lo = float(m.group(1).replace(".", "").replace(",", "."))
        hi = float(m.group(2).replace(".", "").replace(",", "."))
    except ValueError:
        return None
    if m.group(3) is None and (lo >= 1000 or hi >= 1000):
        lo, hi = lo / 1e6, hi / 1e6
    return round((lo + hi) / 2.0, 1)


# E1: a number with THIS context must not become a current/deal-size source —
# all of it comes from planning/estimation/loss, not from the revenue state.
_NON_STATE_CONTEXT = (
    "upsell", "gap", "estimasi", "perkiraan", "hilang", "kehilangan",
    "breakdown", "rencana", "potensi", "potensial", "bisa tambah", "max",
    "maksimal", "target", "butuh", "dibutuhkan", "lepas", "nyata hilang",
    "akan", "dari inquiry mati",
    # note: "8 bulan" is NO longer excluded (iter-9 fix R1) — a work duration
    # legitimately accompanies a revenue statement ("klinik Rp12jt selama 8 bulan");
    # loss/estimation context is already covered by other markers (hilang/estimasi/…).
)

# E1-C: a funnel number is only "measured" when it is NOT a reconstruction from memory
_RECONSTRUCTION_MARKERS = (
    "rekonstruksi", "dari ingatan", "tidak pernah mencatat", "perkiraan",
    "mungkin", "kira-kira", "tidak pernah menghitung", "kasar",
)


def _is_clean_state_number(text: str) -> bool:
    return not any(k in text for k in _NON_STATE_CONTEXT)


def _is_measured(text: str) -> bool:
    return not any(k in text for k in _RECONSTRUCTION_MARKERS)



def _monthly_rp_values(text: str) -> list[float]:
    """Iteration 13 (fix G1 run v7): only Rp numbers whose LOCAL UNIT is monthly
    may become recurring revenue components. A total contract value ('Rp48 juta per
    semester') or an annual value is NOT counted — it used to be summed, giving
    computed Rp48 vs declared Rp30 → a false MISMATCH."""
    out: list[float] = []
    for m in _re.finditer(r"rp\s*[\d.,]+\s*(?:juta|jt|ribu|rb)?", text.lower()):
        tail = text.lower()[m.end():m.end() + 14]
        if _re.search(r"^\s*(?:/|per\s)\s*(?:bulan|month)|^\s*bulanan", tail):
            v = _extract_rp(m.group(0))
            if v:
                out.append(v)
    return out


def _extract_rp_all(text: str) -> list[float]:
    """ALL Rp numbers in the text (millions). For an aggregate sentence: total = max."""
    out = []
    for m in _re.finditer(r"rp\s*[\d.,]+\s*(?:juta|jt)?", text.lower()):
        v = _extract_rp(m.group(0))
        if v is not None:
            out.append(v)
    return out


def _extract_range(text: str, pattern: str) -> Optional[float]:
    """Range '1-2', '3-4' inside the pattern → take the LARGEST matching number.
    Comma decimals ('34,5') are supported (fix iter-11: T3#13 delivery hours)."""
    m = _re.search(pattern, text.lower())
    if not m:
        return None
    nums = []
    for g in m.groups():
        if not g:
            continue
        try:
            nums.append(float(str(g).replace(",", ".")))
        except (TypeError, ValueError):
            continue
    return max(nums) if nums else None


# G7-S1 (internal-docs §10.2): two sentence orders — number before/after window.
_WINDOW_PATTERNS = (
    # "7-8 inquiry masuk ... dalam 90 hari" (number before the keyword)
    r"(\d+)\s*-\s*(\d+)\s*(?:orang\s+)?(?:inquiry|lead|dm)[^.]{0,80}?(\d+)\s*hari",
    # "dalam 90 hari terakhir ... 7-8 inquiry" (window before the number)
    r"(\d+)\s*hari[^.]{0,80}?(\d+)\s*-\s*(\d+)\s*(?:orang\s+)?(?:inquiry|lead|dm)",
)


def _extract_window_inquiry_rate(text: str) -> Optional[float]:
    """Inquiry/lead/DM numbers + an explicit time window (N days) within ONE
    sentence → monthly rate (the TOP end of the range, consistent with _extract_range).

    G7-S1 (internal-docs §10.2): deterministic anchor to the source quote —
    an LLM paraphrase ('N inquiries per month') varies between runs (measured 3.0 vs 5.0 from
    the same transcript, flipping the LOW/MODERATE label at the boundary 5). A number +
    explicit window in the original quote is stable."""
    low = text.lower()
    for pat in _WINDOW_PATTERNS:
        m = _re.search(pat, low)
        if not m:
            continue
        if pat.startswith(r"(\d+)\s*hari"):
            days, lo, hi = m.group(1), m.group(2), m.group(3)
        else:
            lo, hi, days = m.group(1), m.group(2), m.group(3)
        try:
            d, a, b = float(days), float(lo), float(hi)
        except (TypeError, ValueError):
            continue
        # pagar: jendela wajar (mingguan..tahunan), range monoton & masuk akal
        if not (7 <= d <= 365) or b < a or a < 1 or b > 500:
            continue
        return round(b * 30.0 / d, 1)
    return None



