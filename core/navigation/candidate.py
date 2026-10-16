"""Knowledge -> Mechanism -> Candidate Possibility (internal-docs §23).

This layer answers ONE question: "given the verified state and the knowledge currently in force, which
directions are worth considering?" — without a pre-written list of paths.

    Evidence ─► Knowledge (rule: / state:) ─► MECHANISM (active once its support is anchored)
                                                 └─► CANDIDATE POSSIBILITY (a proposal, not yet a path)
                                                       └─► evaluation (evaluator.py) ─► Possible Path

Three deliberately separate steps:

  1. `MechanismOverlay`       knowledge -> mechanism. Only anchored support activates it;
                              `UNSUPPORTED` = None; support + explicit refutation = CONFLICT.
  2. `generate_possibilities` mechanism -> candidate. Only PROPOSES. It judges neither applicability,
                              feasibility, route, nor readiness.
  3. `promote_possibilities`  SUPPORTED candidates -> `Candidate` entries the existing path pipeline can
                              evaluate (generator.Candidate). The evaluator decides whether one becomes a
                              Possible Path. There is no second pipeline (INV-12).

Candidate ≠ Possible Path ≠ Route. Identity: `candidate_id` (proposal, `cand.<direction>`),
`strategy_id`/`path_id` (path), `route_id` (route) — three different things. This module is GENERIC: it
knows no domain."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from core.navigation.contracts import (
    SIGNAL_MECHANISM,
    MechanismSpec,
    PossibilityPattern,
    PossibilitySpace,
    Proposal,
    Signal,
    SignalReader,
    StrategySpec,
    candidate_id_for,
    signal_namespace,
)
from core.navigation.predicate import Evaluation, evaluate, signal_ids
from core.schema.provenance import TRANSCRIPT_PREFIX

# Base status of a candidate (proposal) — neither feasibility nor a path status.
SUPPORTED = "SUPPORTED"  # an active mechanism whose support is anchored in evidence
UNDETERMINED = "UNDETERMINED"  # not yet decidable (support absent / unsettled / conflicting)
NOT_EMERGENT = "NOT_EMERGENT"  # explicit evidence closes the basis (mechanism refuted / requirement FALSE)

# Origin of a candidate that was evaluated.
ORIGIN_STRATEGY = "STRATEGY_DECLARED"  # born from the declared strategy's `emerges_when`
ORIGIN_PATTERN = "MECHANISM_PATTERN"  # born from a mechanism -> possibility pattern
ORIGIN_BOTH = "BOTH"  # both point to the same strategy (provenance merged)

# States of a mechanism.
MECH_ACTIVE = "ACTIVE"
MECH_UNDETERMINED = "UNDETERMINED"
MECH_CONFLICT = "CONFLICT"  # support AND explicit refutation are both present
MECH_REFUTED = "REFUTED"  # only explicit refutation


def _row(sid: str, sig: Signal) -> dict:
    row = {"signal": sid, "reason": sig.reason, "refs": list(sig.refs)}
    if sig.basis:
        row["basis"] = [dict(b) for b in sig.basis]
    if sig.assumes:
        row["assumes"] = [dict(a) for a in sig.assumes]
    return row


def _dedupe(rows: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out = []
    for r in rows:
        if r["signal"] not in seen:
            seen.add(r["signal"])
            out.append(r)
    return out


def _split_refs(rows: list[dict]) -> tuple[list[str], list[str]]:
    ev, tr = [], []
    for r in rows:
        for ref in r.get("refs", []):
            (tr if ref.startswith(TRANSCRIPT_PREFIX) else ev).append(ref)
    return list(dict.fromkeys(ev)), list(dict.fromkeys(tr))


def assumed_absences(rows: list[dict]) -> list[dict]:
    """Support rows -> the absence conditions the rules inside them rely on, per rule and per branch.

    Each entry = `AbsenceAssumption` + `rule_id`: satisfied because no matching record exists (absence of
    record). Neither an anchor nor proof of absence — recorded so an anchored positive claim never reads
    as if the absence itself were verified."""
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for r in rows:
        if _ns(r) != "rule":
            continue
        rule_id = r["signal"].partition(":")[2]
        for a in r.get("assumes") or []:
            key = (rule_id, a["branch"])
            if key not in seen:
                seen.add(key)
                out.append({"rule_id": rule_id, **a})
    return out


@dataclass
class MechanismActivation:
    """One mechanism and its basis. `support` = the backing support rows (rule:/state:) — lineage."""

    mechanism_id: str
    status: str
    signal: Signal
    title: str = ""
    support: list[dict] = field(default_factory=list)
    direct: bool = False  # the domain reader reports it directly (anchored)
    derived: bool = False  # derived from `activated_by` (knowledge -> mechanism)
    conflicts: list[dict] = field(default_factory=list)
    refutation: list[dict] = field(default_factory=list)

    def audit(self) -> dict[str, Any]:
        ev, tr = _split_refs(self.support + ([_row(f"mechanism:{self.mechanism_id}", self.signal)]))
        return {
            "mechanism_id": self.mechanism_id,
            "title": self.title,
            "status": self.status,
            "direct": self.direct,
            "derived": self.derived,
            "knowledge_ids": [r["signal"].partition(":")[2] for r in self.support if _ns(r) == "rule"],
            "evidence_ids": ev,
            "transcript_anchors": tr,
            "conflicts": [dict(c) for c in self.conflicts],
        }


def _ns(row: dict) -> str:
    return signal_namespace(row["signal"])


class MechanismOverlay:
    """A signal reader that adds DERIVED mechanisms on top of the domain reader (Knowledge -> Mechanism).

    Signals other than `mechanism:<id>` that carry `activated_by`/`contradicted_by` pass through as-is.
    The overlay marks itself `_grounded` only after the caller wraps it with `grounded`, so a TRUE mechanism
    without evidence is still downgraded to UNSUPPORTED at the same boundary (PROV-02)."""

    def __init__(self, specs: dict[str, MechanismSpec], base: SignalReader) -> None:
        self.specs = specs
        self.base = base
        self._cache: dict[str, MechanismActivation] = {}

    def activation(self, mechanism_id: str) -> MechanismActivation:
        if mechanism_id not in self._cache:
            self._cache[mechanism_id] = self._compute(self.specs[mechanism_id])
        return self._cache[mechanism_id]

    def _compute(self, spec: MechanismSpec) -> MechanismActivation:
        sid = f"{SIGNAL_MECHANISM}:{spec.mechanism_id}"
        name = spec.title or spec.mechanism_id
        direct = self.base(sid)
        act = evaluate(spec.activated_by, self.base) if spec.activated_by else Evaluation(None)
        con = evaluate(spec.contradicted_by, self.base) if spec.contradicted_by else Evaluation(None)
        support = _dedupe([_row(s, g) for s, g in act.support])
        refutation = _dedupe([_row(s, g) for s, g in con.support])
        active = direct.value is True or act.value is True
        refuted = con.value is True

        def make(status: str, sig: Signal, **kw: Any) -> MechanismActivation:
            return MechanismActivation(spec.mechanism_id, status, sig, spec.title, **kw)

        if active and refuted:
            sig = Signal(
                None,
                f"mekanisme {spec.mechanism_id}: ada dukungan DAN bantahan eksplisit — belum diselesaikan",
                (),
                {"en": f"There is evidence for and against {name}, so it is not settled"},
            )
            conflict = {
                "mechanism_id": spec.mechanism_id,
                "supports": support or [_row(sid, direct)],
                "refutes": refutation,
            }
            return make(
                MECH_CONFLICT,
                sig,
                support=support,
                direct=direct.value is True,
                derived=act.value is True,
                conflicts=[conflict],
                refutation=refutation,
            )
        if refuted:
            refs = tuple(dict.fromkeys(r for row in refutation for r in row["refs"]))
            sig = Signal(
                False,
                f"mekanisme {spec.mechanism_id} disangkal bukti eksplisit",
                refs,
                {"en": f"Evidence points against {name}"},
            )
            return make(MECH_REFUTED, sig, refutation=refutation)
        if active:
            refs = tuple(
                dict.fromkeys(
                    (list(direct.refs) if direct.value is True else [])
                    + [r for row in support for r in row["refs"]]
                )
            )
            if not refs:  # PROV-02: a mechanism with no pointable basis must never become support
                sig = Signal(
                    None,
                    f"mekanisme {spec.mechanism_id} terdeteksi tanpa evidence pendukung — tidak dipakai",
                    (),
                    {"en": f"{name} has no evidence behind it, so it is not used"},
                    unsupported=True,
                )
                return make(MECH_UNDETERMINED, sig)
            via = (["DETECTED"] if direct.value is True else []) + (["DERIVED"] if act.value is True else [])
            basis = (
                {
                    "mechanism_id": spec.mechanism_id,
                    "via": via,
                    "derived_from": [r["signal"] for r in support],
                },
            )
            sig = Signal(
                True,
                f"mekanisme {spec.mechanism_id} aktif ({'+'.join(via)})",
                refs,
                {"en": f"{name} is at work ({len(refs)} verified item(s))"},
                basis=basis,
            )
            return make(
                MECH_ACTIVE, sig, support=support, direct=direct.value is True, derived=act.value is True
            )
        # Absence of support is NOT refutation: the direct signal passes through; if the knowledge read is
        # UNSUPPORTED, that is recorded (still None — never support, never refutation).
        seen_unsupported = [x for x in dict.fromkeys(act.seen + con.seen) if self.base(x).unsupported]
        if seen_unsupported and not direct.unsupported:
            sig = Signal(
                None,
                f"mekanisme {spec.mechanism_id}: knowledge {', '.join(seen_unsupported)} tanpa basis",
                (),
                {"en": f"A hint about {name} cannot be backed by evidence, so it is not used"},
                unsupported=True,
            )
            return make(MECH_UNDETERMINED, sig)
        return make(MECH_UNDETERMINED, direct)

    def __call__(self, sid: str) -> Signal:
        kind, _, name = sid.partition(":")
        if kind == SIGNAL_MECHANISM and name in self.specs:
            return self.activation(name).signal
        return self.base(sid)

    def expand(self, rows: list[dict]) -> list[dict]:
        """Insert the backing support of a derived mechanism (rule/state) right after its row."""
        out: list[dict] = []
        for row in rows:
            out.append(row)
            kind, _, name = row["signal"].partition(":")
            if kind == SIGNAL_MECHANISM and name in self.specs:
                out.extend(self.activation(name).support)
        return _dedupe(out)

    def activations(self) -> list[MechanismActivation]:
        return [self.activation(mid) for mid in self.specs]

    def unsupported(self) -> list[dict]:
        """Knowledge signals claimed active whose basis cannot be formed (audit; not support)."""
        out: dict[str, dict] = {}
        for spec in self.specs.values():
            for pred in (spec.activated_by, spec.contradicted_by):
                for sid in signal_ids(pred):
                    sig = self.base(sid)
                    if sig.unsupported:
                        out.setdefault(sid, {"signal": sid, "reason": sig.reason})
        return list(out.values())


def with_mechanisms(space: PossibilitySpace, reader: SignalReader) -> SignalReader | MechanismOverlay:
    """A reader on top of `reader` that knows about derived mechanisms. Without mechanism specs: `reader`
    itself (legacy behavior unchanged). `reader` MUST already be `grounded`."""
    if not space.mechanisms:
        return reader
    overlay = MechanismOverlay({m.mechanism_id: m for m in space.mechanisms}, reader)
    return _grounded_overlay(overlay)


def _grounded_overlay(overlay: MechanismOverlay):
    """Wrap the overlay with `grounded` (a TRUE mechanism without evidence -> UNSUPPORTED) while keeping
    access to the overlay itself for lineage."""
    from core.navigation.contracts import grounded

    wrapped = grounded(overlay)
    wrapped._overlay = overlay  # type: ignore[attr-defined]
    return wrapped


def overlay_of(reader: Any) -> MechanismOverlay | None:
    return getattr(reader, "_overlay", None)


@dataclass
class CandidatePossibility:
    """A proposal that a direction might be relevant. NOT a Possible Path: not yet evaluated.

    A candidate carries IDENTITY + PROPOSAL CONTENT + PROVENANCE only (`proposal` = `Proposal`, without the
    evaluation substrate: no `checks`, `not_applicable_when`, `route_template_ids`, `no_preconditions`) and
    has NO applicability, feasibility, requirement state, executability, status word, or route — all of
    those are EVALUATION output (`evaluator.py`) that only exists on a Possible Path.

    `support`        the support rows actually evaluated (goal, mechanisms, the rule/state beneath them).
    `mechanisms`     audit of the supporting mechanisms (lineage mechanism -> knowledge -> evidence).
    `missing`        signals not yet known (only when UNDETERMINED).
    `conflicts`      disputes of support vs refutation on the causing mechanism (never silently picked).
                     Recorded ALSO on SUPPORTED candidates standing via an independent sibling branch: the
                     dispute does not invalidate the independent support, but it must not vanish from the
                     candidate."""

    proposal: Proposal
    status: str
    support: list[dict] = field(default_factory=list)
    mechanisms: list[dict] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    missing_detail: list[dict] = field(default_factory=list)
    conflicts: list[dict] = field(default_factory=list)
    refuted: list[str] = field(default_factory=list)
    # Early sign worth surfacing as a "newly emerging possibility" (NOT a path): CONFLICT |
    # PARTIAL (mechanism anchored, other requirements still unknown) | UNSUPPORTED (a hint with no basis).
    # None = no sign at all — merely "not yet detected", not surfaced.
    emerging: str | None = None

    @property
    def direction(self) -> str:
        return self.proposal.direction

    @property
    def candidate_id(self) -> str:
        return candidate_id_for(self.proposal.direction)

    def lineage(self) -> dict[str, Any]:
        """Evidence -> Knowledge -> Mechanism -> Candidate, in a single auditable shape."""
        ev, tr = _split_refs(self.support)
        return {
            "candidate_id": self.candidate_id,
            "direction": self.direction,
            "thesis": self.proposal.thesis,
            "mechanism_ids": [m["mechanism_id"] for m in self.mechanisms if m["status"] == MECH_ACTIVE],
            "knowledge_ids": list(
                dict.fromkeys(r["signal"].partition(":")[2] for r in self.support if _ns(r) == "rule")
            ),
            "evidence_ids": ev,
            "transcript_anchors": tr,
            "mechanisms": [dict(m) for m in self.mechanisms],
            "support": [dict(r) for r in self.support],
            # disputes of the causing mechanism (visible also on candidates that remain SUPPORTED) and the
            # absence conditions its support relies on: two things that must not vanish when promoted
            "conflicts": [dict(c) for c in self.conflicts],
            "assumed_absences": assumed_absences(self.support),
        }

    def audit(self, disposition: str, path_id: str | None = None) -> dict[str, Any]:
        lin = self.lineage()
        row = {
            "candidate_id": self.candidate_id,
            "direction": self.direction,
            "title": self.proposal.title,
            "status": self.status,
            "disposition": disposition,
            "mechanism_ids": lin["mechanism_ids"],
            "knowledge_ids": lin["knowledge_ids"],
            "evidence_ids": lin["evidence_ids"],
            "missing": list(self.missing),
            "conflicts": [dict(c) for c in self.conflicts],
            "refuted": list(self.refuted),
            "emerging": self.emerging,
        }
        if self.emerging:  # display text only for what will be surfaced as a newly emerging possibility
            row["thesis"] = self.proposal.thesis
            row["presentation"] = self.proposal.presentation
            row["missing_detail"] = [dict(m) for m in self.missing_detail]
        if path_id:
            row["path_id"] = path_id
        return row


def pattern_predicate(proposal: Proposal) -> dict:
    """A proposal's emergence predicate: mechanisms (any_of) AND extra context when present. Reads only the
    proposal's content — the pattern's evaluation substrate is out of reach from here."""
    mech: Any = {"any_of": [f"{SIGNAL_MECHANISM}:{m}" for m in proposal.mechanism_ids]}
    return mech if proposal.context_when is None else {"all_of": [mech, proposal.context_when]}


def generate_possibilities(
    space: PossibilitySpace, reader: SignalReader, goal_support: list[dict] | None = None
) -> list[CandidatePossibility]:
    """Mechanism -> candidate. PROPOSES only: it judges neither applicability/feasibility/route.

    `reader` = the mechanism-overlay reader (`with_mechanisms`). One pattern yields exactly one candidate
    (canonical identity = direction); two active mechanisms for the same direction = ONE candidate, merged
    provenance.

    The generator sees ONLY `pattern.proposal` (the generation vs evaluation boundary): the pattern's
    evaluation substrate is never read here, so the result is identical whatever `checks`/
    `not_applicable_when`/templates the pattern carries (tested in `test_candidate_closure.py` §A)."""
    overlay = overlay_of(reader)
    out: list[CandidatePossibility] = []
    for pattern in space.patterns:
        prop = pattern.proposal
        ev = evaluate(pattern_predicate(prop), reader)
        involved = (
            [overlay.activation(m) for m in prop.mechanism_ids if m in overlay.specs] if overlay else []
        )
        conflicts = [c for a in involved for c in a.conflicts]
        if ev.value is True:
            rows = _dedupe((goal_support or []) + [_row(s, g) for s, g in ev.support])
            if overlay:
                rows = overlay.expand(rows)
            mech_audit = _mechanism_audit(prop, reader, overlay)
            # Sibling-mechanism disputes stay recorded: the candidate stands via an independent anchored
            # branch, yet "there is evidence for AND against another mechanism" must not vanish.
            out.append(CandidatePossibility(prop, SUPPORTED, rows, mech_audit, conflicts=conflicts))
        elif ev.value is False:
            refuted = [a.mechanism_id for a in involved if a.status == MECH_REFUTED]
            out.append(CandidatePossibility(prop, NOT_EMERGENT, refuted=refuted))
        else:
            missing = [sid for sid in dict.fromkeys(ev.seen) if reader(sid).value is None]
            missing = missing or [f"{SIGNAL_MECHANISM}:{m}" for m in prop.mechanism_ids]
            out.append(
                CandidatePossibility(
                    prop,
                    UNDETERMINED,
                    missing=missing,
                    missing_detail=[
                        {
                            "signal": sid,
                            "reason": reader(sid).reason,
                            "i18n": {k: {"reason": v} for k, v in reader(sid).i18n.items()},
                        }
                        for sid in missing
                    ],
                    mechanisms=_mechanism_audit(prop, reader, overlay),
                    conflicts=conflicts,
                    emerging=_emerging_kind(prop, reader, conflicts),
                )
            )
    return out


def _mechanism_audit(
    prop: Proposal, reader: SignalReader, overlay: MechanismOverlay | None
) -> list[dict]:
    """Audit each mechanism causing the pattern: derived (lineage rule -> evidence) or detected directly
    by the domain reader (lineage evidence). Inactive mechanisms stay recorded with their status, not
    dropped."""
    rows = []
    for m in prop.mechanism_ids:
        if overlay is not None and m in overlay.specs:
            rows.append(overlay.activation(m).audit())
            continue
        sig = reader(f"{SIGNAL_MECHANISM}:{m}")
        status = (
            MECH_ACTIVE if sig.value is True else (MECH_REFUTED if sig.value is False else "UNDETERMINED")
        )
        ev, tr = _split_refs([_row(f"{SIGNAL_MECHANISM}:{m}", sig)])
        rows.append(
            {
                "mechanism_id": m,
                "title": "",
                "status": status,
                "direct": sig.value is True,
                "derived": False,
                "knowledge_ids": [],
                "evidence_ids": ev if sig.value is True else [],
                "transcript_anchors": tr if sig.value is True else [],
                "conflicts": [],
            }
        )
    return rows


def _emerging_kind(prop: Proposal, reader: SignalReader, conflicts: list[dict]) -> str | None:
    """Does this unsettled candidate carry a SIGN worth surfacing? Only real signs: a conflict, an already
    anchored mechanism (other requirements still unknown), or a hint with no basis.
    "Not yet detected" is not a sign."""
    if conflicts:
        return "CONFLICT"
    sigs = [reader(f"{SIGNAL_MECHANISM}:{m}") for m in prop.mechanism_ids]
    if any(g.value is True for g in sigs):
        return "PARTIAL"
    if any(g.unsupported for g in sigs):
        return "UNSUPPORTED"
    return None


def strategy_from_pattern(pattern: PossibilityPattern) -> StrategySpec:
    """Pattern (a direction with no declared strategy) -> StrategySpec so it enters the SAME evaluation
    pipeline. `emerges_when` = the proposal predicate, so provenance explains why this direction exists.
    This is where the pattern's evaluation substrate (checks, exclusions, templates) is first used — by the
    evaluator, not the generator."""
    return StrategySpec(
        strategy_id=pattern.direction,
        title=pattern.title,
        basis=pattern.basis or pattern.thesis,
        motion=pattern.motion,
        emerges_when=pattern_predicate(pattern.proposal),
        not_applicable_when=pattern.not_applicable_when,
        checks=pattern.checks,
        route_template_ids=pattern.route_template_ids,
        knowledge_sources=pattern.knowledge_sources,
        presentation=pattern.presentation,
        no_preconditions=pattern.no_preconditions,
    )


def promote_possibilities(cset: Any, space: PossibilitySpace) -> list[Any]:
    """SUPPORTED candidates -> the list of `Candidate` entries the evaluator evaluates (merged with those
    born from declared strategies). Promotion to evaluation is NOT promotion to a path: the evaluator can
    still drop it (NOT_APPLICABLE) and judge its feasibility.

    The pattern's evaluation substrate is read HERE (from `space.patterns`, not from the candidate): the
    candidate carries only the proposal.

    Duplicates: the same direction with a strategy also born via `emerges_when` -> ONE candidate, support
    merged (origin BOTH). Same direction with a declared strategy that did not emerge on its own -> that
    strategy is used (its checks/templates), origin MECHANISM_PATTERN."""
    from core.navigation.generator import Candidate

    declared = {s.strategy_id: i for i, s in enumerate(space.strategies)}
    strat_by_id = {s.strategy_id: s for s in space.strategies}
    pattern_by_dir = {p.direction: p for p in space.patterns}
    cands: dict[str, Any] = {c.strategy.strategy_id: c for c in cset.candidates}
    order: dict[str, int] = {sid: declared[sid] for sid in cands}
    for i, cp in enumerate(cset.possibilities):
        if cp.status != SUPPORTED:
            continue
        sid = cp.direction
        if sid in cands:
            base = cands[sid]
            cands[sid] = replace(
                base,
                support=_dedupe(base.support + cp.support),
                origin=ORIGIN_BOTH,
                possibility=cp,
            )
            continue
        strat = strat_by_id.get(sid) or strategy_from_pattern(pattern_by_dir[sid])
        cands[sid] = Candidate(strat, list(cp.support), ORIGIN_PATTERN, cp)
        order[sid] = declared.get(sid, len(space.strategies) + i)
    return [cands[sid] for sid in sorted(cands, key=lambda s: (order[s], s))]


def candidate_block(cand: Any) -> dict[str, Any] | None:
    """The candidate provenance a path carries (INV-14). None for paths born purely from strategies."""
    cp: CandidatePossibility | None = cand.possibility
    if cp is None:
        return None
    return {**cp.lineage(), "origin": cand.origin}


def possibility_audit(cset: Any, paths: list[dict], rejected: list[dict]) -> list[dict]:
    """The `generation.possibilities` audit rows: the fate of each candidate with something to audit (path /
    rejected / conflicted / early sign / refuted) after evaluation."""
    by_strategy = {p["strategy_id"]: p["path_id"] for p in paths}
    rej = {r["strategy_id"] for r in rejected}
    rows = []
    for cp in cset.possibilities:
        if cp.status == SUPPORTED:
            if cp.direction in by_strategy:
                rows.append(cp.audit("PROMOTED", by_strategy[cp.direction]))
            elif cp.direction in rej:
                rows.append(cp.audit("REJECTED_NOT_APPLICABLE"))
            else:  # pragma: no cover — SUPPORTED always ends as a path or a rejection
                rows.append(cp.audit("UNRESOLVED"))
        elif cp.status == UNDETERMINED:
            # "not yet detected" without a sign is already recorded in `generation.undetermined`; rows here
            # are only for those with a real sign (the artifact must not bloat with silent patterns)
            if cp.emerging:
                rows.append(cp.audit("CONFLICTED" if cp.conflicts else "UNRESOLVED"))
        else:
            rows.append(cp.audit("NOT_EMERGENT"))
    return rows
