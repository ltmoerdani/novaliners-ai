"""Stage: evidence → RevenueState (internal-docs §7)."""
from __future__ import annotations

import re as _re

from core.schema.evidence import EvidenceItem
from domains.revenue.schema.state import ReadinessLevel, RevenueState
from domains.revenue.stages.dedup import deduplicate_evidence  # noqa: F401
from domains.revenue.stages.extract import (
    _ADHOC_RE,
    _extract_range,
    _extract_rp,
    _extract_rp_all,
    _extract_rp_range_mid,
    _extract_window_inquiry_rate,
    _is_clean_state_number,
    _is_measured,
    _is_rate_signal,
    _monthly_rp_values,
)
from domains.revenue.stages.reconcile import _RECON_TOLERANCE, reconcile


def _collect_hour_candidates(texts: list[str]) -> tuple[list[float], list[float]]:
    """iter-15 (P0 run Rina): CONTEXT-GUIDED HOUR EXTRACTION — scan ALL 'N hours
    (per) week' matches, classify delivery vs prospecting from the keyword NEAREST
    after the number. Supports '30+', '34-35', '3-4'. The old number-first first-match
    swallowed '3-4 jam/minggu prospect' as delivery 4.0 (bug 86%->12% util).

    G7-S1b (internal-docs §10.3): split into a helper so it can serve TWO sources:
    (1) evidence-ledger text, (2) the TRANSCRIPT anchor when the ledger is empty.
    Returns (del_cands, acq_cands).
    """
    _HOUR_RE = _re.compile(
        r"(\d+(?:[.,]\d+)?)\s*\+?\s*(?:-|sampai\s|to\s|–)?\s*"
        r"(\d+(?:[.,]\d+)?)?\s*(?:jam|hours?)\s*(?:/|per\s)?\s*(?:minggu|week)"
    )
    _ACQ_KW = ("prospek", "prospect", "outreach", "akuisisi", "acquisi")
    # era-7 fix (internal-docs §6.2): "demand" REMOVED from _ACQ_KW — the most
    # generic word in this domain; "34,5 jam untuk demand generation" leaked delivery
    # hours into the acquisition column (bug sample-1 DoD smoke 17/19).
    _DEL_KW = ("delivery", "melayani", "retainer")
    _del_cands: list[float] = []
    _acq_cands: list[float] = []
    for t in texts:
        for m in _HOUR_RE.finditer(t):
            lo = float(m.group(1).replace(",", "."))
            hi = float(m.group(2).replace(",", ".")) if m.group(2) else None
            val = hi if hi is not None else lo
            # Classification: keyword EXACTLY AFTER the number (20 chars), fallback to the
            # PREFIX before the number (30 chars). A long window triggers cross-clause
            # misclassification ('3-4 jam/minggu, tersedot 30+ jam/minggu delivery').
            # Incident 18 Sep 2026 (T13): window 14 failed to reach 'untuk delivery'
            # in '34.5 hours per week untuk delivery' → both columns None → the old
            # fallback grabbed 34.5 as acquisition (on the pre-era-7 server).
            # Window 20 + truncation at punctuation.
            tail = t[m.end():m.end() + 20]
            for _brk in (",", ".", ";"):
                if _brk in tail:
                    tail = tail.split(_brk)[0]
                    break
            # iter-17 fix: comparison separators ('vs') cut the window —
            # 'delivery 34,5 jam/minggu vs akuisisi 3-4 jam/minggu' must not let
            # the first number capture a keyword owned by the second clause.
            for _sep in (" vs ", "vs ", " | ", " dibanding "):
                if _sep in tail:
                    tail = tail.split(_sep)[0]
                    break
            # prefix truncated at the last comma — never let it reach into the
            # previous clause ('...3-4 jam/minggu prospect, 34.5 jam/minggu delivery')
            prefix = t[max(0, m.start() - 30):m.start()].rsplit(",", 1)[-1]
            # FULL word-boundary: 'sisanya' must not match 'sisa'
            ctx = tail + " " + prefix
            def _has(kw: str) -> bool:
                return _re.search(rf"\b{kw}\b", ctx) is not None
            _acq_hit = any(_has(k) for k in _ACQ_KW)
            _del_hit = any(_has(k) for k in _DEL_KW)
            # iter-18 fix (run-5): 'sisa'/'left' is AMBIGUOUS — it can be 'ruang sisa
            # kapasitas delivery' (residual DEL, 5.5 hours run-5) or 'sisa 3-4
            # jam untuk prospek' (ACQ). Without another explicit keyword → skip;
            # the generic fallback below decides from sentence context.
            if (_has("sisa") or _has("left")) and not _acq_hit and not _del_hit:
                continue
            if _acq_hit:
                _acq_cands.append(val)
            elif any(_has(k) for k in _DEL_KW):
                _del_cands.append(val)
    return _del_cands, _acq_cands


def _view_fields(graph: dict | None) -> dict:
    """M3 view (int 11 §10.14) for use BEFORE derivation. Latent bug 60ef056
    (surfaced by gate-smoke 27 Sep): the view overrode current/target/deal
    size AFTER the builder finished, so gap, deals_needed and the REVENUE
    CEILING were computed from regex numbers (or None) — stale. Overrides
    are now applied at the same point as derivation; semantics unchanged:
    the view wins unconditionally. Empty/failed graph -> {} (regex = fallback)."""
    if not graph or not (graph.get("nodes") or {}):
        return {}
    try:
        from domains.revenue.projection import build_revenue_view
        return build_revenue_view(graph).get("fields") or {}
    except Exception:
        return {}


def _override_from_view(s, fields: dict, role: str, field: str) -> None:
    entry = fields.get(role)
    if entry and entry.get("suppressed"):
        # R4-C: the canonical state asserts this role but has no active point -> abstain, not regex
        setattr(s, field, None)
        s.sources.pop(field, None)
        if field == "target_monthly":
            s.target_origin = None
        return
    if entry and entry.get("value") is not None:
        setattr(s, field, round(float(entry["value"]), 1))
        s.sources[field] = {
            "evidence_id": entry.get("node_id"),
            "derivation": f"graph view role={role} tense={entry.get('tense')}",
            "confidence": "measured",
            "precision": entry.get("precision", "exact"),
            "epistemic": entry.get("epistemic", "reported"),
        }


def _strip_historical_transcript(transcript: str | None, historical_evidence) -> str | None:
    """DCP-01 (int 16 S1): strip HISTORICAL content from transcript lines — not whole lines.

    Deterministic number anchors (G7-S1b) read literal text; numbers from superseded claims must
    not become the current state. Audit 14 Oct 2026: the old version dropped the WHOLE line if it
    contained a historical fragment — mixed sentences ("...dulu 30 jam..., sekarang hanya 8 jam")
    also lost their ACTIVE fact. Historical fragments are now removed surgically (strip_fragments);
    only lines still holding an uncleanable historical fragment after stripping are dropped whole —
    likewise lines whose entire content was historical anyway (they become empty).

    Explicit limitation: this cleanup matches fragment substrings (not id/claim based) —
    used ONLY as a fallback, because the primary anchor path remains ledger evidence id/status.
    """
    if not transcript or not historical_evidence:
        return transcript
    from core.stages.rule_support import historical_quote_corpus, strip_fragments
    corpus = historical_quote_corpus(historical_evidence)
    if not corpus:
        return transcript
    kept = []
    for ln in transcript.splitlines():
        norm = " ".join(ln.lower().split())
        if not any(h in norm for h in corpus):
            kept.append(ln)
            continue
        cleaned = strip_fragments(ln, corpus)
        if cleaned and not any(h in " ".join(cleaned.lower().split()) for h in corpus):
            kept.append(cleaned)
        # the whole line was historical content (empty / uncleanable) -> dropped
    return "\n".join(kept)


def build_revenue_state(
    evidence: list[EvidenceItem], goal_text: str = "",
    transcript: str | None = None,
    graph: dict | None = None,
    historical_evidence: list[EvidenceItem] | None = None,
) -> RevenueState:
    """Deterministic: evidence → RevenueState. E1 (iter-7): source discipline —
    current & deal size are prioritized from transactional/outcome evidence in
    the REVENUE_STATE phase with clean context; numbers in planning/estimation/
    loss context are FORBIDDEN from becoming state (bug Rina v2: 'upsell max
    Rp33-34jt' read as current & deal size).

    G7-S1b (internal-docs §10.3): `transcript` is optional — a deterministic
    anchor when the LLM ledger carries no hour numbers (measured variance 18 Sep: acq
    [4.0, 4.0, None]). Not fabrication: the number MUST literally exist in the text."""
    transcript = _strip_historical_transcript(transcript, historical_evidence)  # DCP-01
    s = RevenueState()
    notes: list[str] = []
    src = s.sources

    hard = [
        (e, f"{(e.signal or '')} {(e.source_quote or '')}".lower())
        for e in evidence
        if not getattr(e, "is_gap", False) and e.level in ("transactional", "outcome")
    ]
    soft = [
        (e, f"{(e.signal or '')} {(e.source_quote or '')}".lower())
        for e in evidence
        if not getattr(e, "is_gap", False) and e.level in ("behavioral", "self_reported")
    ]
    all_text = " ".join(t for _, t in hard + soft) + " " + goal_text.lower()

    # G1 (iter-9, fix R1): current revenue via RECONCILIATION — not first-match.
    # - declared = the user's total statement (aggregate markers: "total/semua/3 klien/pas/stabil")
    # - computed = SUM of the named per-client components (12+10+8 = 30)
    # - declared wins as the value; computed = an independent verification signal;
    #   a mismatch is NEVER silently reconciled → FLAG (internal-docs §5.3).
    # Fix R1 (bug v4 "Current Rp12"): first-match is vulnerable to ledger order — now
    # ALL candidates are collected, then reconciled.
    _AGG_MARKERS = ("total", "semua", "stabil", "pas", "= rp", "ketiganya", "keduanya", "seluruh")
    _COMPONENT_MARKERS = ("per klien", "@", "masing-masing")

    declared, declared_ev = None, None
    components: list[tuple[float, str]] = []
    # iter-14 (P0 user): every component MUST have a unique source evidence ID —
    # one evidence item must not contribute the same component twice, and the
    # same value from two evidence items WITHOUT different client subjects is not double-counted.
    _CLIENT_MARKERS = (
        "klinik", "restoran", "resto", "sekolah", "klien", "client", "perusahaan", "toko", "umkm", "brand"
    )

    def _subject(t: str) -> str:
        return next((m for m in _CLIENT_MARKERS if m in t), "")

    seen_component_values: dict[float, tuple[str, str]] = {}  # value -> (evidence_id, subject)
    uncertain_components: list[str] = []  # evidence ids with ambiguous components
    for e, t in hard + soft:
        if _is_rate_signal(t):
            # iter-18 fix (DoD smoke run-2): a CLEAN monthly aggregate statement
            # (total/stabil marker + monthly anchor + state context) must not be
            # dropped just because the signal+quote combination carries a
            # non-monthly sub-clause ('kontrak per semester ~Rp48jt' poisoned
            # _is_rate_signal → current Rp30jt lost, LLM phrasing variance).
            if not (
                ("bulan" in t or "month" in t)
                and _is_clean_state_number(t)
                and any(m in t for m in _AGG_MARKERS)
            ):
                continue  # E2: hourly/project/semester rates are not monthly revenue
        if "per klien" in t or "rata-rata" in t:
            # An EXISTING per-client value = a recurring revenue component (may be
            # summed to verify declared). A PROSPECTIVE value
            # (baru/kisaran/range/potensial/akan/target) = deal size, not a component.
            if (
                not any(k in t for k in ("baru", "kisaran", "range", "potensial", "akan", "target"))
                and not _ADHOC_RE.search(t)
                and not _is_rate_signal(t)
            ):
                # iter-21 fix: dedupe the values (signal + quote can carry the same
                # number twice) — cross-evidence dedup remains below.
                vv_list = list(dict.fromkeys(_extract_rp_all(t)))
                if not vv_list:
                    _v1 = _extract_rp(t)
                    if _v1:
                        vv_list = [_v1]
                for vv in vv_list:
                    if vv:
                        components.append((round(vv, 1), e.id))
            continue  # deal size is not double-counted as revenue
        if ("tahun" in t or "year" in t) and "bulan" not in t:
            continue  # annual is handled by a separate fallback
        if "target" in t:
            continue
        v = _extract_rp(t)
        if not v:
            continue
        if ("bulan" in t or "month" in t) and _is_clean_state_number(t):
            if (
                any(m in t for m in _AGG_MARKERS)
                or _re.search(r"\d+\s*klien[^.]{0,30}(rp|juta)", t)
                or _re.search(r"dari\s+\d+\s*(?:klien|client)", t)
            ):
                # Fix R1 (iter-9): aggregate sentences often carry component numbers
                # before the total ("Rp12jt klinik + Rp10jt + Rp8jt = Rp30jt") —
                # declared = the LARGEST Rp in the sentence, not the first.
                # iter-14: 'Rp30 juta per bulan DARI 3 klien' is also aggregate even
                # without a front marker — a restated total is NOT a component.
                all_rp = _extract_rp_all(t)
                # iter-17 fix: the aggregate declared = the largest MONTHLY-anchored
                # number in the sentence — not max of all Rp values. 'Rp30jt/bulan dari 3 klien
                # (… sekolah Rp8jt/bulan kontrak per semester ~Rp48jt)': max of all
                # = 48 (semester contract) -> state corruption run-3.
                _m_agg = _monthly_rp_values(t)
                v = max(_m_agg) if _m_agg else (max(all_rp) if all_rp else v)
                if declared is None or v > declared:
                    declared, declared_ev = round(v, 1), e.id
            elif not _ADHOC_RE.search(t):
                # E3 + iter-13: components = MONTHLY-anchored numbers only
                monthly = _monthly_rp_values(t)
                if monthly:
                    subj = _subject(t)
                    if len(monthly) > 1 and not any(m in t for m in _COMPONENT_MARKERS):
                        # iter-14: one signal with ≥2 monthly numbers and no per-client
                        # marker = ambiguous (monthly + mixed total) → flag it,
                        # never count blindly.
                        uncertain_components.append(e.id)
                    for vv in monthly:
                        vv = round(vv, 1)
                        prev = seen_component_values.get(vv)
                        if prev is not None:
                            pid, psubj = prev
                            # duplicate: same evidence, OR the same value without a
                            # different subject (klinik vs restoran = two distinct clients)
                            if pid == e.id or (not psubj and not subj) or (psubj == subj and psubj):
                                continue
                        seen_component_values[vv] = (e.id, subj)
                        components.append((vv, e.id))
    computed_sum = round(sum(v for v, _ in components), 1) if components else None
    # iter-14 (P0 user 'repeated extraction of the same transaction'): a component
    # whose value EQUALS the declared total = a restated total, not a separate
    # client — drop it before reconcile.
    if declared is not None:
        components = [(v, eid) for v, eid in components if abs(v - declared) > _RECON_TOLERANCE]
        computed_sum = round(sum(v for v, _ in components), 1) if components else None
    # iter-14 (P0 user): ambiguous/duplicate/incomplete components → do not count
    # confidently; mark COMPUTATION UNCERTAIN. Status still follows reconcile(), but
    # the flag enters reconciliation + validate_state (a small penalty, not BLOCK).
    components_uncertain = bool(uncertain_components)
    # Level A guard (bug G7 run 21:30, 2× executions, ~33% rate): declared=None +
    # a computed component SUM that includes a restated-total value (ev-goal-001
    # contains 'per klien' → the Rp30 total also got counted as a component, SUM=60)
    # must not become current WITHOUT declared — reconcile() VERIFIED that number
    # and current(60) >= target(60) erased the gap + REVENUE CEILING.
    # Rule (decided FINAL, not a subject-count heuristic — the BAD run had 2 client
    # subjects and was still wrong because the restated total got summed):
    # a component SUM WITHOUT declared NEVER becomes current revenue.
    # reconcile()'s own docstring: PARTIAL = lower bound, not a total. Current
    # without the user's total statement = derived-from-partial-sums → rejected;
    # UNKNOWN has consequences (P2: probe + penalty), not silent reconciliation.
    if declared is None and computed_sum is not None:
        notes.append(
            "⚠ Tidak ada statement total (declared) — SUM komponen Rp"
            f"{computed_sum:.0f} jt TIDAK dipakai sebagai current revenue "
            "(SUM bisa memuat total yang dinyatakan-ulang sebagai komponen); "
            "minta user konfirmasi total bulanan"
        )
        computed_sum = None
        components_uncertain = True
    recon_value, recon_status, recon_diff = reconcile(declared, computed_sum)
    if recon_value is not None:
        s.current_monthly = round(recon_value, 1)
        src["current_monthly"] = {
            "evidence_id": declared_ev or (components[0][1] if components else None),
            "derivation": (
                f"declared Rp{declared:.0f} jt; computed SUM komponen Rp{computed_sum:.0f} jt"
                if (declared is not None and computed_sum is not None)
                else (
                    f"declared Rp{declared:.0f} jt"
                    if declared is not None
                    else f"computed SUM komponen Rp{computed_sum:.0f} jt"
                )
            ),
            "confidence": "measured" if declared is not None else "derived",
        }
        s.reconciliation["current_monthly"] = {
            "declared": declared, "computed": computed_sum,
            "verified": recon_value, "status": recon_status, "discrepancy": recon_diff,
            "component_evidence_ids": sorted({eid for _, eid in components}),
            "components_uncertain": components_uncertain,
        }
        if components_uncertain:
            notes.append(
                "⚠ COMPUTATION UNCERTAIN: komponen revenue dari evidence "
                f"{', '.join(uncertain_components)} ambigu (≥2 angka bulanan tanpa marker per-klien) — "
                "SUM komponen tidak dihitung sebagai fakta pasti; klarifikasi per klien diperlukan"
            )
        if recon_status == "MISMATCH":
            notes.append(
                f"⚠ Reconciliation MISMATCH: declared Rp{declared:.0f} jt vs "
                f"computed komponen Rp{computed_sum:.0f} jt "
                f"(selisih Rp{recon_diff:.0f} jt belum terjelaskan — "
                f"bisa project-based/one-off/salah hitung; klarifikasi diperlukan)"
            )
        elif recon_status == "VERIFIED" and computed_sum is not None:
            # iter-19 fix: declared can be None (current from the component SUM alone —
            # a ledger variance without an aggregate sentence) — do not format None.
            notes.append(
                f"Revenue terverifikasi: SUM komponen Rp{computed_sum:.0f} jt"
                + (f" = declared Rp{declared:.0f} jt" if declared is not None else "")
            )
    # annual /12 fallback (only when reconciliation produced nothing)
    if s.current_monthly is None:
        for e, t in hard + soft:
            if (
                ("tahun" in t or "year" in t) and "bulan" not in t
                and "per klien" not in t and _is_clean_state_number(t)
            ):
                v = _extract_rp(t)
                if v:
                    s.current_monthly = round(v / 12.0, 1)
                    src["current_monthly"] = {
                        "evidence_id": e.id, "derivation": "annual / 12", "confidence": "derived"
                    }
                    break

    # Target — E4 (iter-10) + fix iter-15: goal text WINS, but the number AFTER a
    # 'target' marker takes precedence — bug run Rina: 'penghasilan Rp30jt... Target
    # Rp60jt' → first-match took 30 as the target (state corruption).
    tgt = None
    tgt_src = ""  # target origin: explicit marker vs first-Rp fallback (fix run-manual 19 Sep)
    if goal_text:
        m_t = _re.search(r"target[^.]{0,60}?rp\s*([\d.,]+)\s*(juta|jt|ribu|rb)?", goal_text.lower())
        if m_t:
            try:
                val = float(m_t.group(1).replace(".", "").replace(",", "."))
                unit = (m_t.group(2) or "").lower()
                tgt = (
                    val / 1000.0 if unit in ("ribu", "rb")
                    else (val / 1e6 if unit == "" and val >= 1000 else val)
                )
                tgt_src = "goal_marker"
            except ValueError:
                pass
        if tgt is None:
            tgt = _extract_rp(goal_text.lower())  # fallback: first Rp in the goal text
            tgt_src = "goal_fallback" if tgt is not None else ""
    if tgt is None:
        m = _re.search(r"target[^.]{0,80}?rp\s*([\d.,]+)\s*(juta|jt|ribu|rb)?", all_text)
        if m:
            try:
                val = float(m.group(1).replace(".", "").replace(",", "."))
                unit = (m.group(2) or "").lower()
                tgt = (
                    val / 1000.0 if unit in ("ribu", "rb")
                    else (val / 1e6 if unit == "" and val >= 1000 else val)
                )
                tgt_src = "transcript_marker"
            except ValueError:
                pass
    if tgt:
        s.target_monthly = round(tgt, 1)
        # F (23 Sep 2026): record the target origin (tgt_src has been tracked by the
        # builder since the run-manual fix 19 Sep but was never persisted) — see the
        # target_origin field in schema/state.py.
        s.target_origin = tgt_src or None
        src["target_monthly"] = {
            "derivation": "goal statement", "confidence": "measured",
            "origin": tgt_src or "unknown",
        }

    # Level A guard continued (after the target is computed): DERIVED current without
    # declared (component SUM via PARTIAL, or annual÷12) that is >= target = a
    # prospective/aspirational number or a restated total that got summed — not a
    # realized current. Rejected → UNKNOWN has consequences (P2), not a silent gap=None.
    if (
        s.current_monthly is not None
        and declared is None
        and s.target_monthly is not None
        and s.current_monthly >= s.target_monthly
    ):
        _deriv = (src.get("current_monthly") or {}).get("derivation", "?")
        notes.append(
            f"⚠ current derived ({_deriv}) = Rp{s.current_monthly:.0f} jt >= "
            f"target Rp{s.target_monthly:.0f} jt tanpa statement total — "
            "ditolak (terlalu bagus untuk jadi kenyataan / angka ambisi); "
            "klarifikasi diperlukan"
        )
        s.current_monthly = None
        src.pop("current_monthly", None)

    # Fix run-manual 19 Sep (case 'target 1 klien baru', deal range Rp18-55jt in
    # the goal): the 'first Rp in goal text' fallback dragged a DEAL-SIZE into
    # the target (18 < current 127) → a broken semantic gap. Rule: a FALLBACK target
    # landing BELOW HALF the measured current = unit/deal contamination —
    # reject. The 0.5 threshold preserves the legitimate case 'unstable income,
    # target slightly below current' (characterization V6: target 25 vs current 30).
    # Explicit (marker) targets are honored at any value; unit-based targets
    # ('1 klien baru') are not forced into rupiah.
    if (
        s.current_monthly is not None
        and s.target_monthly is not None
        and s.target_monthly < 0.5 * s.current_monthly
        and tgt_src == "goal_fallback"
    ):
        notes.append(
            f"⚠ Target Rp{s.target_monthly:.0f} jt < ½ current Rp{s.current_monthly:.0f} jt "
            "dan berasal dari fallback (Rp pertama di goal, tanpa marker 'target') — "
            "kemungkinan besar itu deal-size/unit, bukan target revenue. Target ditolak; "
            "goal berbasis unit (mis. '1 klien baru') tidak dipaksa menjadi rupiah."
        )
        s.target_monthly = None
        s.target_origin = None   # F: provenance ikut dibersihkan saat target ditolak guard
        src.pop("target_monthly", None)

    # M3 view BEFORE gap derivation (see _view_fields)
    _vf = _view_fields(graph)
    _override_from_view(s, _vf, "current_revenue", "current_monthly")
    _override_from_view(s, _vf, "target", "target_monthly")

    # M4 (2 Oct 2026): `is not None`, not truthiness — running income of 0.0 ("belum ada klien") is
    # a MEASURED number (gap = target), not "unknown". Previously 0.0 read as falsy: the gap never
    # dropped.
    if (
        s.current_monthly is not None
        and s.target_monthly is not None
        and s.target_monthly > s.current_monthly
    ):
        s.gap_monthly = round(s.target_monthly - s.current_monthly, 1)
        src["gap_monthly"] = {
            "derivation": f"target {s.target_monthly} - current {s.current_monthly}",
            "confidence": "derived",
        }

    # Deal size — hard-first, range midpoint, per-client/average context.
    # Fix N2 (iter-8): unit numbers ("@Rp8-10jt per klien") may come even from
    # planning context — they are per-unit values, not totals, so the
    # _NON_STATE_CONTEXT exclusion does not apply while an explicit unit marker exists.
    _UNIT_MARKERS = ("per klien", "@", "retainer baru", "retainer @", "per deal", "rata-rata")

    # D4 (iter-9): a unit marker alone is not enough — upsell/gap/potential-context
    # numbers are not deal size (bug v5: avg deal Rp3.5 jt from "upsell Rp3-4jt").
    _DEAL_EXCLUDE = (
        "upsell", "tambahan", "gap", "potensi", "hilang", "kehilangan", "estimasi", "perkiraan",
        "ad hoc", "ad-hoc", "sekali", "insidental", "proyek kecil", "kenalan", "tak tiap bulan",
        "tidak tiap bulan",
    )

    def _pick_deal(pool):
        for e, t in pool:
            has_unit = any(m in t for m in _UNIT_MARKERS)
            if (
                has_unit
                and ("tahun" not in t and "year" not in t)
                and not any(k in t for k in _DEAL_EXCLUDE)
                and not _is_rate_signal(t)
            ):
                v = _extract_rp_range_mid(t) or _extract_rp(t)
                if v:
                    return round(v, 1), e.id, ("range" if _extract_rp_range_mid(t) else "single")
        return None, None, None

    deal, deal_ev, deal_kind = _pick_deal(hard)
    deal_conf = "measured"
    if deal is None:
        deal, deal_ev, deal_kind = _pick_deal(soft)
        deal_conf = "self_reported" if deal is not None else "unknown"
    # Sanity clamp (E1/E3): deal size > 50% of current = contamination; < 25% of
    # current = likely ad-hoc/a slice → UNKNOWN (bug v6: deal Rp1.5jt).
    if (
        deal is not None and s.current_monthly
        and (deal > 0.5 * s.current_monthly or deal < 0.25 * s.current_monthly)
    ):
        notes.append(
            f"⚠ Data integrity: avg deal size kandidat Rp{deal:.0f} jt di luar rentang wajar "
            f"vs current Rp{s.current_monthly:.0f} jt "
            f"(>50% atau <25%) — kemungkinan kontaminasi/ad-hoc; deal size di-set UNKNOWN"
        )
        deal, deal_ev, deal_conf = None, None, "unknown"
    if deal is not None:
        s.avg_deal_size = deal
        src["avg_deal_size"] = {
            "evidence_id": deal_ev,
            "derivation": f"{'midpoint range' if deal_kind == 'range' else 'angka tunggal'} dari evidence",
            "confidence": deal_conf,
        }
    # iter-14 (P0 user §8): derive deal size from the ACTIVE CLIENT SAMPLE —
    # 'Rp30jt / 3 retainer = Rp10jt'. Mandatory label: derived estimate, based only
    # on current client sample — NOT proven acquisition economics.
    if s.avg_deal_size is None and s.current_monthly:
        m_n = None
        for e, t in hard + soft:
            m_n = _re.search(
                r"(\d+)\s*(?:klien|client)[^.]{0,40}?(?:retainer|aktif|berjalan|bulanan)", t
            ) or _re.search(
                r"(?:retainer|klien aktif)[^.]{0,20}?(\d+)\s*(?:klien|client)?", t
            )
            if m_n and int(m_n.group(1)) >= 1:
                n_cli = int(m_n.group(1))
                cand = round(s.current_monthly / n_cli, 1)
                if 0.25 * s.current_monthly <= cand <= 0.5 * s.current_monthly:
                    s.avg_deal_size = cand
                    src["avg_deal_size"] = {
                        "evidence_id": e.id,
                        "derivation": (
                            f"derived estimate: Rp{s.current_monthly:.0f} jt ÷ {n_cli} klien aktif "
                            f"(berbasis sampel klien saat ini, bukan akuisisi tervalidasi)"
                        ),
                        "confidence": "derived",
                    }
                    notes.append(
                        f"Avg retainer ≈ Rp{cand:.0f} jt — derived estimate, "
                        f"based only on current {n_cli}-client sample. "
                        f"Bukan proven acquisition economics."
                    )
                    break
        m_n = None
    _override_from_view(s, _vf, "client_rate", "avg_deal_size")  # before deals_needed
    if s.gap_monthly and s.avg_deal_size:
        import math
        s.deals_needed = max(1, math.ceil(s.gap_monthly / s.avg_deal_size))
        notes.append(
            f"Gap Rp{s.gap_monthly:.0f} jt ÷ avg deal Rp{s.avg_deal_size:.0f} jt "
            f"≈ {s.deals_needed} klien/deal baru"
        )
        src["deals_needed"] = {"derivation": "ceil(gap / deal size)", "confidence": "derived"}

    texts = [t for _, t in hard + soft]
    # iter-15 (P0 run Rina) → G7-S1b (internal-docs §10.3): hour candidates come
    # from the LEDGER first (LLM-curated); if a column is still None, reach deterministically into
    # the TRANSCRIPT — literal hour numbers in the source text, source recorded explicitly.
    # iter-15 fix: collect ALL candidates then take the MAXIMUM per category —
    # '3-4 jam/minggu prospect, 30+ jam/minggu delivery' → the largest value per
    # category (delivery hours are always >= acquisition hours in a busy service business).
    _del_cands, _acq_cands = _collect_hour_candidates(texts)
    if s.delivery_hours_per_week is None and _del_cands:
        s.delivery_hours_per_week = round(max(_del_cands), 1)
    if s.acquisition_hours_per_week is None and _acq_cands:
        s.acquisition_hours_per_week = round(max(_acq_cands), 1)
    # G7-S1b (internal-docs §10.3): transcript anchor — fills ONLY columns still
    # None (an LLM ledger without hour numbers; measured variance acq [4.0, 4.0, None]).
    # The None > wrong-value principle still holds: the fallback fires only when
    # the number truly exists in the transcript, and provenance is recorded.
    # Called TWICE: before the absurd-cap, and AFTER rejecting bogus candidates
    # (>cap) — the rejection-vs-anchor order must never leave a column None when
    # the transcript literally contains the number (bug run-3 18 Sep: bogus ledger
    # rejected by cap → None, anchor never called again).
    def _anchor_hours_from_transcript() -> None:
        if not transcript:
            return
        if s.delivery_hours_per_week is None or s.acquisition_hours_per_week is None:
            _del_tr, _acq_tr = _collect_hour_candidates(transcript.splitlines())
            if s.delivery_hours_per_week is None and _del_tr:
                s.delivery_hours_per_week = round(max(_del_tr), 1)
                s.sources["delivery_hours_per_week"] = {
                    "evidence_id": "—",
                    "note": "G7-S1b (internal-docs §10.3): anchor transkrip — ledger bukti "
                            "tidak membawa angka jam; angka diambil deterministik dari "
                            "teks sumber, bukan direkonstruksi.",
                }
            if s.acquisition_hours_per_week is None and _acq_tr:
                s.acquisition_hours_per_week = round(max(_acq_tr), 1)
                s.sources["acquisition_hours_per_week"] = {
                    "evidence_id": "—",
                    "note": "G7-S1b (internal-docs §10.3): anchor transkrip — ledger bukti "
                            "tidak membawa angka jam (atau kandidatnya ditolak sanity "
                            "check); angka diambil deterministik dari teks sumber.",
                }

    _anchor_hours_from_transcript()
    # Inquiry rate, latency, capacity, cycle
    # G7-S1c (internal-docs §10.3): TWO-PASS GLOBAL — time-window anchors are SCANNED
    # across ALL text first, then per-month paraphrases. Text-first let a paraphrase
    # in early evidence ("3 inquiry per bulan") win before the source quote
    # ("7-8 inquiry ... 90 hari") was reachable → inquiry 3.0 vs 2.7 across
    # runs → demand_sufficiency flipping AT_RISK/SUFFICIENT at the deals_needed boundary.
    for t in texts:
        if s.inquiry_rate_per_month is None:
            v = _extract_window_inquiry_rate(t)
            if v is not None:
                s.inquiry_rate_per_month = v
    for t in texts:
        if s.inquiry_rate_per_month is None:
            v = _extract_range(t, r"(inquiry|lead)[^.]{0,40}?(\d)\s*-?\s*(\d)?\s*(per|/)\s*(bulan|month)")
            if not v:
                v = _extract_range(t, r"(\d)\s*-?\s*(\d)?\s*(inquiry|lead|dm)\s*(per|/)\s*(bulan|month)")
            if v:
                s.inquiry_rate_per_month = v
    for t in texts:
        if s.response_latency_days is None:
            # Tier-1 #3 + iter-13: ID and EN patterns (ledgers are often bilingual).
            v = _extract_range(t, r"rata-rata\s*(\d)\s*-?\s*(\d)?\s*hari")
            if not v:
                v = _extract_range(
                    t,
                    r"(?:telat|terlambat|lambat|balas|respons|jawab|dibalas|membalas)[^.]{0,25}?"
                    r"(\d)\s*(?:-|sampai\s*)?\s*(\d)?\s*hari",
                )
            if not v:
                v = _extract_range(
                    t,
                    r"(?:late\s*repl|repl(?:y|ied)|respond|response|slow)[^.]{0,25}?"
                    r"(\d)\s*(?:-|to\s*)?\s*(\d)?\s*days?",
                )
            if not v:
                v = _extract_range(t, r"(\d)\s*(?:-|to\s*)?\s*(\d)?\s*days?[^.]{0,20}?(?:late|delay)")
            if v:
                s.response_latency_days = v
        if s.delivery_hours_per_week is None:
            # Tier-3 #13 + iter-13: delivery/work hours per week (ID & EN).
            v = _extract_range(
                t,
                r"(\d+(?:[.,]\d+)?)\s*(?:-|sampai\s*)?\s*(\d+(?:[.,]\d+)?)?\s*jam"
                r"[^.]{0,20}?(?:kerja|delivery|melayani|klien)[^.]{0,20}?per\s*minggu",
            )
            if not v:
                # iter-14 fix: the EN keyword-FIRST pattern ('rest for delivery 34.5 hours
                # per week') — the old number-first pattern swallowed '3-4 hours/week for
                # prospect' (ACQUISITION hours) as delivery hours.
                v = _extract_range(
                    t,
                    r"(?:work|delivery)[^.]{0,15}?(\d+(?:[.,]\d+)?)\s*(?:-|to\s*)?"
                    r"\s*(\d+(?:[.,]\d+)?)?\s*hours?",
                )
            if v:
                s.delivery_hours_per_week = round(v, 1)
        if s.acquisition_hours_per_week is None:
            v = _extract_range(
                t,
                r"(\d+(?:[.,]\d+)?)\s*(?:-|sampai\s*)?\s*(\d+(?:[.,]\d+)?)?\s*jam"
                r"[^.]{0,20}?(?:prospek|outreach|akuisisi|sisa)[^.]{0,20}?per\s*minggu",
            )
            if not v:
                v = _extract_range(
                    t,
                    r"(\d+(?:[.,]\d+)?)\s*(?:-|to\s*)?\s*(\d+(?:[.,]\d+)?)?\s*hours?"
                    r"[^.]{0,25}?(?:prospect|outreach|acquisi|sisa|left)",
                )
            if v and s.acquisition_hours_per_week is None:
                s.acquisition_hours_per_week = round(v, 1)
        if s.unit_rate_per_hour is None:
            v = _extract_rp(t)
            if v is not None and "per jam" in t and v < 5:
                s.unit_rate_per_hour = round(v, 3)
        if s.acquisition_hours_per_week is None:
            # Fix N2 (iter-8): hours per week ONLY for acquisition/prospect context.
            # "30-35 jam per minggu" (delivery for 3 clients) must not become
            # acquisition capacity — run v3 mis-captured it (5 hours from mixed text).
            v = _extract_range(t, r"(\d)\s*-?\s*(\d)?\s*jam\s*(per|/)\s*minggu")
            if v:
                delivery_ctx = any(
                    k in t for k in ("delivery", "klien", "melayani", "terpakai", "total", "kerja")
                )
                # iter-18 fix (run-5): 'sisa' is ACQ context only when NOT
                # paired with 'kapasitas' ('ruang sisa kapasitas delivery'
                # = residual time, not for prospecting).
                acq_ctx = any(
                    k in t
                    for k in ("prospek", "outreach", "akuisisi", "buat prospek",
                              "cari klien", "untuk prospek")
                ) or ("sisa" in t and "kapasitas" not in t)
                if acq_ctx or not delivery_ctx:
                    s.acquisition_hours_per_week = v
        if s.acquisition_cycle_weeks is None:
            v = _extract_range(
                t,
                r"(\d)\s*-?\s*(\d)?\s*(minggu|week)\s*(untuk|sampai|hingga|to)?\s*(closing|deal|klien|cycle)",
            )
            if v:
                s.acquisition_cycle_weeks = v

    # era-7 fix (internal-docs §6.2): MAGNITUDE SANITY CHECK — a busy service
    # business's acquisition hours can never approach/exceed its delivery hours.
    # Keyword-window classification (14/30 chars) proved fallible (repro T1–T3:
    # "kapasitas: 34,5 jam per minggu untuk demand generation" → acq=34.5).
    # Rule: acq >= del → that number is in the wrong column; take the next acq
    # candidate, or clear it (fallback None > wrong value — Level A internal-docs).
    if (
        s.acquisition_hours_per_week is not None
        and s.delivery_hours_per_week is not None
        and s.acquisition_hours_per_week >= s.delivery_hours_per_week
    ):
        s.sources["acquisition_hours_per_week"] = {
            "evidence_id": "—",
            "note": "era-7: kandidat jam akuisisi >= jam delivery — ditolak "
            "sanity check besaran (salah klasifikasi keyword-window)",
        }
        s.acquisition_hours_per_week = None
    # era-7 fix (continued): absolute ABSURDITY — even with no delivery pair,
    # acquisition hours > 20 hours/week make no sense for a small service business
    # (human work capacity ≈40 hours; ≥20 hours of outreach = full-time sales).
    # T2/T3 repro: "34,5 jam per minggu untuk prospek" (no del) passed the
    # relative sanity check because del=None → an absolute cap is needed.
    _ACQ_ABSURD_CAP = 20.0
    if s.acquisition_hours_per_week is not None and s.acquisition_hours_per_week > _ACQ_ABSURD_CAP:
        s.sources["acquisition_hours_per_week"] = {
            "evidence_id": "—",
            "note": f"era-7: kandidat jam akuisisi > {_ACQ_ABSURD_CAP:.0f} jam/minggu "
            "— melebihi batas kewajaran bisnis jasa kecil, ditolak (kemungkinan "
            "salah klasifikasi delivery vs akuisisi)",
        }
        s.acquisition_hours_per_week = None
    # G7-S1b (internal-docs §10.3): RETRY the anchor after both sanity checks —
    # rejecting bogus candidates (relative & absurd-cap) must NOT end in None
    # when the transcript holds a sensible number (run-3 variance 18 Sep: bogus
    # ledger rejected by cap → None even though '3-4 hours/week untuk prospect' is in the text).
    _anchor_hours_from_transcript()

    # Demand (E1): 5 fields — exists / volume / quality / sufficiency / scalability.
    # SUFFICIENT only from a MEASURED funnel number (not a recalled reconstruction).
    demand_signals = any(
        k in t for t in texts
        for k in ("inquiry", "lead masuk", "tanya harga", "bertanya harga", "masuk pembicaraan", "referral")
    )
    s.demand_exists = demand_signals if demand_signals else None
    s.demand_signal = "EXISTS" if demand_signals else "UNKNOWN"
    # willingness-to-pay: separate from demand — needs proof of buyers PAYING
    if any(
        k in t for t in texts
        for k in ("menerima", "diterima pasar", "closing", "bayar tanpa komplain", "masuk rutin",
                  "retainer aktif", "stabil", "tanpa telat", "lancar")
    ):
        s.willingness_to_pay = "PROVEN_AT_CURRENT_PRICE"
    elif s.demand_signal == "EXISTS":
        s.willingness_to_pay = "UNKNOWN"
    if s.inquiry_rate_per_month is not None:
        s.demand_volume = (
            "LOW" if s.inquiry_rate_per_month < 5
            else "MODERATE" if s.inquiry_rate_per_month < 20
            else "HIGH"
        )
    funnel_measured = any(
        ("konversi" in t or "inquiry" in t) and _is_measured(t) and any(c.isdigit() for c in t)
        for _, t in hard
    )
    # iter-17 fix: a MEASURED 0% conversion is proof of conversion failure, NOT
    # proof of sufficient demand (bug run-3: 'conversion rate 90 hari = 0%' ->
    # funnel_measured -> SUFFICIENT, self-contradictory).
    # iter-19 (replay user 5/5): OR-of-paraphrases — a single regex is sensitive to
    # word order ("Konversi nol: 0 dari...", "klien berbayar nol dari...",
    # "yang bayar: nol") — all escaped the old pattern → false SUFFICIENT.
    _zero_conv_re = [
        _re.compile(r"\b(?:nol|0)\s*(?:bayar|transfer|klien\s*baru|closing|deal)"),
        _re.compile(r"\b0\s*%"),
        _re.compile(r"konversi[^.]{0,24}\b0\s*%"),
        _re.compile(r"konversi[^.]{0,12}\b(?:nol| nihil)\b"),                      # 'Konversi nol:'
        _re.compile(r"\bnol\b[^.]{0,40}(?:jadi klien|klien berbayar|menjadi klien|yang bayar)"),
        _re.compile(r"(?:bayar|closing|klien berbayar)[^.]{0,20}\b(?:nol|0)\b"),
    ]
    _zero_conv = any(rx.search(t) for rx in _zero_conv_re for t in texts)
    s.demand_quality = (
        "PARTIALLY KNOWN"
        if any("konversi" in t or "1:3" in t or "6 dari 10" in t for _, t in hard + soft)
        else "UNKNOWN"
    )
    if s.deals_needed and s.inquiry_rate_per_month:
        expected_leads_90d = s.inquiry_rate_per_month * 3.0
        needed_leads = s.deals_needed * 3  # conservative attrition (not measured)
        if expected_leads_90d < needed_leads:
            s.demand_sufficiency = "AT_RISK"
            notes.append(
                f"Inbound ±{s.inquiry_rate_per_month:.0f}/bln ≈ {expected_leads_90d:.0f} lead/90 hari "
                f"vs butuh ~{needed_leads} untuk {s.deals_needed} deal — "
                f"demand ada tapi kemungkinan TIDAK cukup; akuisisi aktif perlu diuji"
            )
        elif funnel_measured and not _zero_conv:
            s.demand_sufficiency = "SUFFICIENT"
        else:
            s.demand_sufficiency = "UNKNOWN"
            notes.append(
                "Lead tampak cukup secara kasar, TAPI tanpa funnel number terukur — "
                "sufficiency tetap UNKNOWN"
            )
    elif s.demand_exists:
        s.demand_sufficiency = "UNKNOWN"
        notes.append("Demand terbukti ADA — kecukupan volume untuk target BELUM DIKETAHUI")
    if _zero_conv and s.demand_sufficiency in ("UNKNOWN", "SUFFICIENT"):
        s.demand_sufficiency = "AT_RISK"
        notes.append(
            "Conversion 90 hari terukur 0% — demand masuk tapi tidak ada yang menutup; "
            "sufficiency AT_RISK meski inflow ada"
        )

    # Pricing architecture (iter-13): distinguish ABSENT / INFORMAL / PRESENT.
    # Run v7: 'price anchors exist (Rp8jt/Rp12jt) but no written document, zero
    # templates' → INFORMAL, not UNKNOWN/ABSENT.
    _t_all = " | ".join(texts)
    # iter-17 fix: price documents must be NEGATION-aware — 'tidak ada daftar harga'
    # is proof of ABSENCE, not PRESENCE (bug run-3: a false PRESENT).
    _has_written_doc = False
    for t in texts:
        for _dkw in (
            "rate card", "daftar harga", "price list", "paket tertulis", "dokumen harga", "template harga"
        ):
            if _dkw in t and not _re.search(r"(?:tidak|belum|tanpa|nol)[^.]{0,40}?" + _re.escape(_dkw), t):
                _has_written_doc = True
                break
        if _has_written_doc:
            break
    _has_anchors = bool(_re.search(r"rp\s*(?:8|12)\s*(?:jt|juta)", _t_all)) or any(
        k in _t_all
        for k in ("anchor harga", "angka di kepala", "harga di kepala",
                  "patokan transaksi", "harga referensi")
    )
    if _has_written_doc:
        s.pricing_architecture = "PRESENT"
    elif _has_anchors:
        s.pricing_architecture = "INFORMAL"
    elif any(
        k in _t_all
        for k in ("proposal custom", "belum ada rate card", "tidak ada rate card", "belum ada paket",
                  "belum punya paket", "custom pricing", "nol dokumen", "zero templates")
    ):
        s.pricing_architecture = "ABSENT"
    else:
        s.pricing_architecture = "UNKNOWN"

    # Readiness matrix v1 (Tier-3 #13) — delivery computed from ACTUAL HOURS, not a heuristic:
    # if delivery hours + required acquisition hours exceed weekly capacity (≈40 h) → NO.
    hrs_delivery = s.delivery_hours_per_week
    hrs_acq = s.acquisition_hours_per_week
    delivery_ready: ReadinessLevel = "UNKNOWN"
    if hrs_delivery is not None:
        capacity = 40.0
        needed = hrs_delivery + (hrs_acq or 0)
        if needed >= capacity * 0.95:
            delivery_ready = "NO"
        elif needed >= capacity * 0.8:
            delivery_ready = "PARTIAL"
        else:
            delivery_ready = "YES"
    elif hrs_acq is not None and (s.deals_needed or 0) >= 2:
        delivery_ready = "PARTIAL"

    # iter-15: CAPACITY as a boundary condition — utilization = delivery/40 hours.
    # >80% = CONSTRAINED: the business cannot absorb the volume it is trying to create
    # (success-induced failure). Capacity affects Readiness + Spectrum.
    capacity = 40.0
    if hrs_delivery is not None:
        s.capacity_utilization = round(hrs_delivery / capacity, 3)
        if s.capacity_utilization >= 0.95:
            delivery_ready = "NO"
        elif s.capacity_utilization > 0.8:
            delivery_ready = "CONSTRAINED"
        elif s.capacity_utilization > 0.6:
            delivery_ready = "PARTIAL"
        else:
            delivery_ready = "YES"
    elif hrs_acq is not None and (s.deals_needed or 0) >= 2:
        delivery_ready = "PARTIAL"

    s.readiness = {
        "acquisition": "PARTIAL" if s.demand_exists else "UNKNOWN",
        "conversion": (
            "PARTIAL"
            if (s.pricing_architecture in ("ABSENT", "INFORMAL") or (s.response_latency_days or 0) > 1)
            else "UNKNOWN"
        ),
        "delivery": delivery_ready,
        "scale": (
            "NO" if (delivery_ready in ("NO", "CONSTRAINED", "PARTIAL") or s.deals_needed) else "UNKNOWN"
        ),
    }
    if hrs_delivery is not None:
        notes.append(
            f"Delivery {hrs_delivery:.1f} jam/minggu + akuisisi {hrs_acq or 0:.1f} jam "
            f"→ {(hrs_delivery + (hrs_acq or 0)):.1f} dari ~40 jam kapasitas; "
            f"readiness delivery: {delivery_ready}"
        )
    elif s.readiness["delivery"] == "PARTIAL":
        notes.append(
            f"Kapasitas akuisisi {hrs_acq:.0f} jam/minggu vs butuh ±{s.deals_needed} klien baru "
            f"— kapasitas delivery untuk scale BELUM TERBUKTI"
        )
    # iter-14 + iter-18 REVISED (P0 user #5/#6): capacity warnings ONLY from the
    # user's EXPLICIT statement ('+3 klien baru → ~60 jam/minggu'). The linear model
    # 'per client X hours × (existing + deals_needed)' was REMOVED — per-client hours
    # derived from the existing client mix are NOT economics proof for a new retainer;
    # the engine must not invent linear capacity assumptions the user never gave.
    if hrs_delivery is not None and s.delivery_hours_per_week and s.gap_monthly:
        _expl = _re.search(
            r"(\d+)\s*(?:klien|client)\s*(?:baru|tambahan|sekaligus)[^.]{0,80}?"
            r"(\d+(?:[.,]\d+)?)\s*(?:-|sampai|to|–|hingga)?\s*(\d+(?:[.,]\d+)?)?\s*jam",
            " | ".join(texts),
        )
        if _expl:
            n_new = int(_expl.group(1))
            wl_lo = float(_expl.group(2).replace(",", "."))
            wl_hi = float(_expl.group(3).replace(",", ".")) if _expl.group(3) else wl_lo
            wl = max(wl_lo, wl_hi or 0.0)  # worst case = peak load
            s.sources["capacity_warning"] = {
                "evidence": _expl.group(0)[:140],
                "derivation": (
                    f"EKSPLISIT dari user: +{n_new} klien baru dilaporkan "
                    f"mendorong beban ke ±{wl:g} jam/minggu"
                ),
                "confidence": "measured",
            }
            if wl >= 40.0:
                notes.append(
                    f"⚠ SYSTEMIC RISK (L8): target ini punya warning kapasitas EKSPLISIT — "
                    f"+{n_new} klien baru dilaporkan mendorong beban kerja ke ±{wl:.0f} jam/minggu "
                    f"(>40 jam sehat). "
                    f"Bukan berarti sudah terbukti constraint utama, tapi batas operasionalnya nyata"
                )
                s.readiness["scale"] = "NO"
    # iter-15 + iter-18 REVISED (P0 user #5/#6): dual-track REVENUE CEILING —
    # FINANCIAL (deals_needed, derived ceil) vs OPERATIONAL (the explicit user
    # warning / remaining capacity). NO '±1 retainer needs X hours' derivation —
    # that linear model is an assumption, not evidence.
    if s.capacity_utilization is not None and s.capacity_utilization > 0.8 and (s.gap_monthly or 0) > 0:
        sisa = max(0.0, 40.0 - (hrs_delivery or 0.0))
        _cw = s.sources.get("capacity_warning", {}).get("derivation", "")
        _op = (
            f"secara operasional: {_cw}" if _cw
            else f"sisa kapasitas sehat hanya ±{sisa:.1f} jam/minggu"
        )
        notes.append(
            f"🧱 REVENUE CEILING DETECTED — CAPACITY-ACQUISITION CONFLICT: "
            f"FINANCIAL: gap Rp{s.gap_monthly:.0f} jt ≈ {s.deals_needed} deal tambahan "
            f"pada avg deal Rp{(s.avg_deal_size or 0):.0f} jt (derived). "
            f"OPERATIONAL: delivery sudah {s.capacity_utilization*100:.0f}% terpakai, {_op} — "
            f"model operasi saat ini TIDAK bisa menyerap revenue yang dibutuhkan lewat retainer baru saja. "
            f"Catatan epistemik: capacity bukan constraint saat ini; capacity adalah DECISION BOUNDARY — "
            f"scaling akuisisi sekarang menciptakan risiko operasional; "
            f"keputusan revenue harus melewati boundary kapasitas"
        )
    # iter-14: tri-state demand — what is proven is HISTORICAL demand;
    # current flow & sufficiency for the 90-day target are different claims.
    s.demand_states = {
        "historical": ("EXISTS" if s.demand_exists else "UNKNOWN"),
        "current_flow": (
            s.demand_volume if s.demand_volume != "UNKNOWN" else ("LOW" if s.demand_exists else "UNKNOWN")
        ),
        "sufficiency_for_target": s.demand_sufficiency,
    }
    s.notes = notes
    return s


# ---------------------------------------------------------------------------
# E2 (iter-7): Data Integrity Check — deterministic, runs AFTER the extractor,
# BEFORE diagnosis. BLOCK/FLAG results enter state.integrity_issues +
# engine_note; BLOCK lowers confidence.
# ---------------------------------------------------------------------------


