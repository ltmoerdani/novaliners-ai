"""Revenue signal reader: RevenueState + detected mechanisms + active knowledge rules -> tri-state Signal.

A signal = a verified state read by the universal pipeline (id "<kind>:<name>"). Every True/False
value must have a basis in RevenueState; a missing number = None (unknown), not False. References
(`refs`) come from real provenance in `RevenueState.sources` / mechanism evidence — never invented
afterwards.

The 0.8 capacity threshold is consistent with the spectrum capacity bound (internal-docs)."""

from __future__ import annotations

from typing import Any

from core.navigation.contracts import SIGNAL_MECHANISM, SIGNAL_RULE, SIGNAL_STATE, Signal
from core.navigation.knowledge import rule_reader_table
from domains.revenue.schema.goal import Goal
from domains.revenue.schema.goal_evaluation import goal_readiness
from engine.domain_pack import mechanisms

UTIL_CAP = 0.8


def _t(id_text: str, en_text: str) -> dict[str, str]:
    """Bilingual reason sentence: `id` = the machine language (artifact base), `en` = the v9 UI language.
    Other languages are added here/in data, not in the UI."""
    return {"id": id_text, "en": en_text}


def _util_text(util: float | None) -> dict[str, str]:
    """Capacity reason in human language (not 'utilization = 0.85')."""
    if util is None:
        return _t("jam kerja delivery belum terukur", "Your delivery hours are not measured yet")
    pct = round(util * 100)
    if pct >= 80:
        return _t(
            f"waktu kerja Anda sudah terpakai sekitar {pct}%",
            f"Your working time is already about {pct}% used",
        )
    return _t(
        f"waktu kerja Anda terpakai sekitar {pct}%, masih ada ruang",
        f"Your working time is about {pct}% used, so there is still room",
    )


def _wtp_text(wtp: str | None) -> dict[str, str]:
    if wtp == "PROVEN_AT_CURRENT_PRICE":
        return _t(
            "klien terbukti membayar penuh di harga sekarang", "Clients are proven to pay full price today"
        )
    if wtp in (None, "UNKNOWN"):
        return _t(
            "kesediaan membayar di harga sekarang belum terukur",
            "Willingness to pay at your current price is not measured yet",
        )
    return _t(
        "bukti menunjukkan harga sekarang ditolak atau dinego berat",
        "The evidence shows your current price is rejected or heavily negotiated",
    )


def _wtp_new_price_text(wtp: str | None) -> dict[str, str]:
    """D2: mirror of _wtp_text for the new price — real-money commitment at the proposed price."""
    if wtp == "PROVEN_AT_NEW_PRICE":
        return _t(
            "ada komitmen uang nyata pada harga baru yang diusulkan",
            "There is real money committed at your proposed new price",
        )
    if wtp in (None, "UNKNOWN"):
        return _t(
            "kesediaan membayar di harga baru belum terbukti",
            "Willingness to pay at the new price is not proven yet",
        )
    return _t(
        "bukti menunjukkan calon pembeli menolak berkomitmen di harga baru",
        "The evidence shows prospects declined to commit at the new price",
    )


def _demand_text(rs: Any) -> dict[str, str]:
    if rs.demand_exists is True:
        return _t("ada lead/inquiry yang masuk", "Leads or inquiries are coming in")
    if rs.demand_exists is False:
        return _t("belum ada bukti lead/inquiry masuk", "No proof yet that leads or inquiries come in")
    return _t("permintaan (lead/inquiry) belum terukur", "Demand (leads or inquiries) is not measured yet")


def _suff_text(rs: Any) -> dict[str, str]:
    s = rs.demand_sufficiency
    if s == "SUFFICIENT":
        return _t("permintaan tercatat melebihi kapasitas Anda", "Recorded demand is more than you can serve")
    if s == "INSUFFICIENT":
        return _t(
            "permintaan tercatat kurang untuk kebutuhan jalur ini", "Recorded demand is too low for this path"
        )
    return _t("kecukupan permintaan belum terukur", "Whether demand is enough is not measured yet")


def _clients_text(rs: Any) -> dict[str, str]:
    if rs.avg_deal_size is None:
        return _t(
            "nilai klien aktif belum terukur (rata-rata nilai deal dan pendapatan berjalan)",
            "The value of your active clients is not measured yet (average deal and current income)",
        )
    return _t(
        f"rata-rata nilai klien sekitar {rs.avg_deal_size}, pendapatan berjalan {rs.current_monthly}/bulan",
        f"Average client value is about {rs.avg_deal_size}M, current income {rs.current_monthly}M a month",
    )


def _join(*parts: dict[str, str]) -> dict[str, str]:
    """Join layered reasons: `id` with '; ' (artifact base), `en` with '. ' (full sentences)."""
    return _t("; ".join(p["id"] for p in parts), ". ".join(p["en"].rstrip(".") for p in parts) + ".")


def _sig(value: bool | None, text: dict[str, str], refs: tuple[str, ...] = ()) -> Signal:
    return Signal(value, text["id"], refs, {k: v for k, v in text.items() if k != "id"})


# State signals read from RevenueState (id -> provenance source field). Signals without a state field
# (referral, conversion, CAC, unit economics) are ALWAYS unmeasured: the evidence genuinely has to be
# collected first.
_STATE_SOURCES = {
    "state:goal_established": ("target_monthly",),
    "state:revenue_gap": ("gap_monthly", "target_monthly", "current_monthly"),
    "state:existing_revenue": ("current_monthly",),
    "state:demand_exists": ("demand_exists",),
    "state:capacity_available": ("capacity_utilization", "delivery_hours_per_week"),
    "state:wtp_proven": ("willingness_to_pay",),
    # D2: new price — the signal behind the value_repricing check (proof at the current price is
    # not proof at the new price).
    "state:wtp_proven_new_price": ("willingness_to_pay_new_price",),
    "state:over_demand": ("capacity_utilization", "demand_sufficiency"),
    "state:clients_measured": ("avg_deal_size", "current_monthly"),
    # F1 (Round 7, D3): measurements now have a source field — measured evidence opens PRESENT.
    "state:referral_evidence": ("referral_leads_recorded",),
    "state:cac_baseline": ("cac_measured",),
}
_UNMEASURED = {
    "state:referral_evidence": _t(
        "belum ada bukti lead datang dari referral/jaringan",
        "No proof yet that leads come from referrals or your network",
    ),
    "state:conversion_baseline": _t("baseline konversi belum terukur", "Conversion is not measured yet"),
    "state:cac_baseline": _t("CAC belum terukur", "Cost per client is not measured yet"),
    "state:unit_economics": _t("unit economics belum terhitung", "Unit economics are not worked out yet"),
}


def unmeasured_signal_ids() -> frozenset[str]:
    """Signals that are ALWAYS unmeasured from state (no source field): the evidence must be collected
    via an action/measurement, not asked about as a state fact (used by the Question Planner: ACT,
    not ASK)."""
    return frozenset(_UNMEASURED)


def declared_signal_ids() -> set[str]:
    """Every signal allowed to be referenced by ontology/possibility/revenue.json (validation without
    magic strings)."""
    ids = set(_STATE_SOURCES) | set(_UNMEASURED)
    ids |= {f"{SIGNAL_MECHANISM}:{m}" for m in mechanisms()}
    return ids



def _metric_known(metric_id: str) -> bool:
    from ontology.registry import metrics as _mr

    return _mr.metric_by_id(metric_id) is not None

class RevenueSignals:
    """Revenue SignalReader. `mechanisms`: mechanism_id -> [evidence_id]; `active_rules`: rule_id ->
    RuleSupport (provenance from the rule interpreter) or a raw reference list. A rule without a real
    anchor never becomes a TRUE signal (`core.navigation.knowledge.rule_signal`).

    Goal-Relative (int 09 §4.1/§5): `goal` = the active structured Goal context. The
    `state:goal_established` signal judges Goal readiness from the metric's own semantics
    (registry + the `goal_readiness` adjudication) — NOT from the presence of a revenue number
    (GR-12). Without a structured Goal (legacy/anonymous sessions), the old behavior still applies."""

    def __init__(
        self,
        revenue_state: Any,
        mechanisms: dict[str, list[str]] | None = None,
        active_rules: dict[str, Any] | None = None,
        goal: "Goal | None" = None,
    ) -> None:
        self.rs = revenue_state
        self.mechanisms = mechanisms or {}
        self.active_rules = rule_reader_table(active_rules)
        self.goal = goal

    def _refs(self, sid: str) -> tuple[str, ...]:
        src = getattr(self.rs, "sources", None) or {}
        refs = []
        for field in _STATE_SOURCES.get(sid, ()):
            ev = (src.get(field) or {}).get("evidence_id")
            if ev and ev != "—":
                refs.append(str(ev))
        return tuple(dict.fromkeys(refs))

    def _goal_established(self) -> Signal:
        """Semantic Goal-relative gate (GR-12): ready = True with a metric-aware reason;
        not ready / unsupported metric = None (undetermined) with a reason — not False
        (absent) and not a silent fallback to target_monthly."""
        g = self.goal
        mid = g.metric_id
        if mid and not _metric_known(mid):
            return _sig(
                None,
                _t(
                    f"metric '{mid}' belum didukung registry — navigasi menahan pembentukan path",
                    f"The metric '{mid}' is not supported yet, so we hold off naming a way forward",
                ),
            )
        rd = goal_readiness(g)
        if rd["ready"]:
            label = (g.metric_definition() or {}).get("display_name", {}).get("en", mid or "goal")
            return _sig(
                True,
                _t(
                    f"Goal siap dinavigasi: {label} (semantik {g.direction})",
                    f"Your goal is clear enough to navigate: {label} "
                    f"({g.direction.lower().replace('_', ' ')})",
                ),
            )
        blocking = ", ".join(rd["blocking"]) or "UNKNOWN"
        # Conversation can establish a REVENUE goal via evidence/graph (M4/M3) even while the session's
        # structured goal is still desire-only — a verified target still opens navigation
        # (H3 test-m4-session-loop: new information continues the conversation, HOLD does not lock).
        if self.rs is not None and getattr(self.rs, "target_monthly", None) is not None:
            return _sig(
                True,
                _t(
                    "target revenue dinyatakan/terverifikasi dari percakapan",
                    "A revenue goal is stated or verified from the conversation",
                ),
            )
        return _sig(
            None,
            _t(
                f"Goal belum cukup jelas ({blocking}) — perlu klarifikasi sebelum path dinilai",
                f"Your goal is not defined enough yet ({blocking}); "
                "we need to clarify before naming ways forward",
            ),
        )

    def __call__(self, sid: str) -> Signal:
        kind, _, name = sid.partition(":")
        if kind == SIGNAL_MECHANISM:
            hits = self.mechanisms.get(name)
            if not hits:
                return Signal(None)
            return _sig(
                True,
                _t(
                    f"mekanisme {name} terdeteksi dari bukti",
                    f"Mechanism {name} was detected from the evidence",
                ),
                tuple(hits),
            )
        if kind == SIGNAL_RULE:
            return self.active_rules.get(name) or Signal(None)
        # F1 (D3): referral/CAC measurements now read from state — check before the UNKNOWN fallback.
        if sid in ("state:referral_evidence", "state:cac_baseline") and self.rs is not None:
            refs = self._refs(sid)
            if sid == "state:referral_evidence":
                n = getattr(self.rs, "referral_leads_recorded", None)
                conf = ((getattr(self.rs, "sources", None) or {}).get("referral_leads_recorded") or {}).get(
                    "confidence"
                )
                if n is not None and conf == "measured":
                    if n >= 1:
                        return _sig(
                            True,
                            _t(
                                f"{n} lead tercatat datang dari referral/jaringan",
                                f"{n} lead(s) recorded coming from referrals or your network",
                            ),
                            refs,
                        )
                    return _sig(
                        False,
                        _t(
                            "referral dicatat terukur namun belum menghasilkan lead",
                            "Referrals are recorded but have not produced leads yet",
                        ),
                        refs,
                    )
                return _sig(None, _UNMEASURED[sid])
            cac = getattr(self.rs, "cac_measured", None)
            conf = ((getattr(self.rs, "sources", None) or {}).get("cac_measured") or {}).get("confidence")
            if cac is not None and conf == "measured":
                return _sig(
                    True,
                    _t(
                        f"CAC terukur sekitar {cac} per klien",
                        f"Cost per client is measured at about {cac}",
                    ),
                    refs,
                )
            return _sig(None, _UNMEASURED[sid])
        if sid in _UNMEASURED:
            return _sig(None, _UNMEASURED[sid])
        rs = self.rs
        if rs is None or kind != SIGNAL_STATE:
            return Signal(None)
        refs = self._refs(sid)
        util = rs.capacity_utilization
        if sid == "state:goal_established":
            if self.goal is not None:
                return self._goal_established()
            has = rs.target_monthly is not None
            return _sig(
                True if has else None,
                _t("target revenue dinyatakan", "A revenue goal is stated")
                if has
                else _t("target revenue belum dinyatakan", "No revenue goal is stated yet"),
                refs,
            )
        if sid == "state:revenue_gap":
            gap = rs.gap_monthly
            if gap is None:
                text = _t("selisih menuju target belum terukur", "The gap to your goal is not measured yet")
            elif gap > 0:
                text = _t(
                    "ada selisih antara pendapatan sekarang dan target",
                    "There is a gap between your income now and your goal",
                )
            else:
                text = _t(
                    "pendapatan sekarang sudah mencapai target", "Your income now already meets the goal"
                )
            return _sig(None if gap is None else gap > 0, text, refs)
        if sid == "state:existing_revenue":
            cur = rs.current_monthly
            if cur is None:
                text = _t("pendapatan berjalan belum terukur", "Your current income is not measured yet")
            elif cur > 0:
                text = _t("sudah ada pendapatan berjalan", "You already have income coming in")
            else:
                text = _t("belum ada pendapatan berjalan", "You have no income coming in yet")
            return _sig(None if cur is None else cur > 0, text, refs)
        if sid == "state:demand_exists":
            return _sig(None if rs.demand_exists is None else bool(rs.demand_exists), _demand_text(rs), refs)
        if sid == "state:capacity_available":
            return _sig(None if util is None else util <= UTIL_CAP, _util_text(util), refs)
        if sid == "state:wtp_proven":
            wtp = rs.willingness_to_pay
            val = True if wtp == "PROVEN_AT_CURRENT_PRICE" else (None if wtp == "UNKNOWN" else False)
            return _sig(val, _wtp_text(wtp), refs)
        if sid == "state:wtp_proven_new_price":
            # D2: mirror of state:wtp_proven — tri-state, refs from the new-price field's provenance.
            wtp_new = getattr(rs, "willingness_to_pay_new_price", None) or "UNKNOWN"
            val = True if wtp_new == "PROVEN_AT_NEW_PRICE" else (None if wtp_new == "UNKNOWN" else False)
            return _sig(val, _wtp_new_price_text(wtp_new), refs)
        if sid == "state:over_demand":
            # Over-demand evidence can only be PROVEN (True) or unknown (None):
            # slack capacity/low demand is not proof that this path is closed (carried over from v2).
            over = (util is not None and util > UTIL_CAP) or rs.demand_sufficiency == "SUFFICIENT"
            return _sig(True if over else None, _join(_util_text(util), _suff_text(rs)), refs)
        if sid == "state:clients_measured":
            ok = rs.avg_deal_size is not None and (rs.current_monthly or 0) > 0
            return _sig(True if ok else None, _clients_text(rs), refs)
        return Signal(None)
