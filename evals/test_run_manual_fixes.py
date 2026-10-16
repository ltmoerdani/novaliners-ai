"""Guard for the 19 Sep manual-run fixes (3 manual test runs + 1 standalone run;
internal-docs era).

  1. Fix #2 (mapping_coverage 0): _draft_with_retry — an empty evidence_map from
     the LLM = degradation → retry once; no retry when evidence < 5 (mini session).
  2. Fix #3 (target < current): a FALLBACK target (the first Rp in the goal, no 'target'
     marker) that lands below the measured current = deal-size/unit contamination
     → REJECTED + note. An explicit (marker) target below current is still honored.
"""
from __future__ import annotations

import sys

sys.path.insert(0, ".")

from agents.diagnosis import DiagnosisDraft, _draft_with_retry
from core.schema.evidence import EvidenceItem
from core.trace import TraceReport
from domains.revenue.stages.state import build_revenue_state

failed = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global failed
    print(f"  {'PASS' if ok else 'FAIL'} {name}" + (f" | {detail}" if detail and not ok else ""))
    if not ok:
        failed += 1


def _ev(i: int, level: str = "transactional", signal: str = "") -> EvidenceItem:
    return EvidenceItem(id=f"ev-{i:02d}", phase="REVENUE_STATE", level=level,
                        signal=signal or f"sinyal netral {i}")


def _draft(map_: dict) -> DiagnosisDraft:
    return DiagnosisDraft(
        where_you_are="x", primary_constraint="y", primary_constraint_id="C6.3",
        do_not="n", next_best_action="a", success_metric="m",
        well_know_when="w", pivot_rule="p", evidence_map=map_, why=["alasan"],
    )


print("[F2-1] _draft_with_retry — retry saat evidence_map kosong (>=5 bukti)", flush=True)


class _FlakyLLM:
    """Stub: structured_call #1 empty, #2 populated."""

    def __init__(self):
        self.calls = 0

    def structured_call(self, schema, system, user):
        self.calls += 1
        return _draft({} if self.calls == 1 else {"C6.3": ["ev-01"]})


class _OkLLM:
    def __init__(self):
        self.calls = 0

    def structured_call(self, schema, system, user):
        self.calls += 1
        return _draft({"C6.4": ["ev-01"]})


ev5 = [_ev(i) for i in range(1, 6)]
llm = _FlakyLLM()
tr = TraceReport("diagnosis")
d = _draft_with_retry(llm, "prompt", ev5, tr)
check("retry terjadi (2 panggilan)", llm.calls == 2, str(llm.calls))
check("map terisi setelah retry", d.evidence_map.get("C6.3") == ["ev-01"], str(d.evidence_map))
stage_names = [st.get("name") or st.get("stage") for st in (tr.to_dict().get("stages") or [])]
check("stage llm_draft_retry tercatat", any("retry" in str(n) for n in stage_names), str(stage_names))

llm_ok = _OkLLM()
_draft_with_retry(llm_ok, "prompt", ev5, TraceReport("diagnosis"))
check("tanpa degradasi = tanpa retry (1 panggilan)", llm_ok.calls == 1, str(llm_ok.calls))

llm2 = _FlakyLLM()
_draft_with_retry(llm2, "prompt", ev5[:3], TraceReport("diagnosis"))
check("bukti <5 = TIDAK retry (biaya latensi sesi mini)", llm2.calls == 1, str(llm2.calls))

llm3 = _FlakyLLM()
d3 = _draft_with_retry(llm3, "prompt", ev5, TraceReport("diagnosis"))
# the stub always succeeds on retry; the always-empty-path guard was tested in iter-9 (engine_note)

print("[F3-1] build_revenue_state — target fallback < current ditolak", flush=True)
goal_run2 = ("Saya jual jasa build aplikasi pakai AI (Rp18-55jt/proyek), "
             "selama ini klien dari referensi — target 1 klien baru dalam 90 hari")
ev_run2 = [_ev(1, "transactional",
                  "total penghasilan rp127 juta per bulan dari 4 proyek jasa")]
ev_v6 = [_ev(1, "transactional",
             "total penghasilan rp30 juta per bulan dari 4 proyek jasa")]
s = build_revenue_state(ev_run2, goal_run2)
notes = " ".join(s.integrity_issues and [i.get("msg", "") for i in s.integrity_issues] or [])
check("current terbaca (run-2: 127jt)", s.current_monthly == 127.0, str(s.current_monthly))
check("target fallback (18jt) DITOLAK (< ½ current)", s.target_monthly is None, str(s.target_monthly))

print("[F3-2] target eksplisit (marker) di bawah current tetap dihormati", flush=True)
s2 = build_revenue_state(ev_v6, "mau skala turun: target penghasilan rp15 juta per bulan")
check("target marker 15jt dipertahankan", s2.target_monthly == 15.0, str(s2.target_monthly))
check("gap tidak dihitung (target < current, eksplisit)", s2.gap_monthly is None)

print("[F3-2b] fallback sedikit-di-bawah current (karakterisasi V6) TIDAK tertolak", flush=True)
s2b = build_revenue_state(ev_v6, "Rp25 juta/bulan dari jasa")
check("target fallback 25jt (83% current) dipertahankan",
      s2b.target_monthly == 25.0, str(s2b.target_monthly))

print("[F3-3] target normal DI ATAS current — kasus umum tak terganggu", flush=True)
s3 = build_revenue_state(
    [_ev(1, "transactional", "total penghasilan rp2 juta per bulan")],
    "penghasilan Rp2 juta per bulan, target Rp10 juta per bulan dalam 60 hari",
)
check("target 10jt (fallback) tetap terbaca", s3.target_monthly == 10.0, str(s3.target_monthly))
check("gap terhitung 8jt", s3.gap_monthly == 8.0, str(s3.gap_monthly))

print("[F3-4] run mandiri 19 Sep — target marker '3xRp500rb' tak regresi", flush=True)
s4 = build_revenue_state(
    [_ev(1, "self_reported", "pendapatan ebook sekitar rp1,5 juta per bulan")],
    "target 3 klien x Rp500.000 dalam 30 hari",
)
check("target marker 0.5jt terbaca (tidak ditolak)",
      s4.target_monthly == 0.5, str(s4.target_monthly))

print()
print(f"HASIL: {'SEMUA LULUS ✅' if failed == 0 else f'{failed} GAGAL ❌'}")
raise SystemExit(0 if failed == 0 else 1)
