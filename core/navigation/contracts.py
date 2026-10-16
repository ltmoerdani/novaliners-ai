"""Universal navigation contracts: Possible Path, Applicability, Satisfaction, Executability,
Feasibility, Lifecycle.

Docs: docs/14-universal-navigation-architecture.md (the canonical reference).

This module is GENERIC: it knows no domain. Domains (e.g. sales, SaaS, B2B) arrive as plugins through
three things declared outside core: (1) a strategy space (`StrategySpec`), (2) a reader of verified
state signals (`SignalReader`), (3) a composable route substrate (templates).

Six axes that must NEVER be merged into one score:

  Applicability   APPLIES | NOT_APPLICABLE | UNKNOWN      — does this possibility apply to the user's case
  Satisfaction    PRESENT | PARTIAL | UNKNOWN | ABSENT   — is the world condition (requirement) proven
  Executability   TRUE | FALSE | UNKNOWN                 — can the activity be done NOW
  Feasibility     SUPPORTED | CONDITIONAL | CONTRADICTED | UNDETERMINED — the ENGINE's decision on a path
  Lifecycle       OPEN | PAUSED | STOPPED | CLOSED       — a PROCESS decision/state (e.g. user stops a path)

Feasibility (engine) and Lifecycle (decision) are deliberately two enums: "the engine found a contradiction"
is not "the user decided to stop", and both origins stay traceable (`stop_provenance`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Callable, Union


class Applicability(StrEnum):
    APPLIES = "APPLIES"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNKNOWN = "UNKNOWN"


class Satisfaction(StrEnum):
    PRESENT = "PRESENT"
    PARTIAL = "PARTIAL"
    UNKNOWN = "UNKNOWN"
    ABSENT = "ABSENT"


class Executability(StrEnum):
    TRUE = "TRUE"
    FALSE = "FALSE"
    UNKNOWN = "UNKNOWN"


class Feasibility(StrEnum):
    SUPPORTED = "SUPPORTED"
    CONDITIONAL = "CONDITIONAL"
    CONTRADICTED = "CONTRADICTED"
    UNDETERMINED = "UNDETERMINED"


class Lifecycle(StrEnum):
    OPEN = "OPEN"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"
    CLOSED = "CLOSED"


# Check kinds: a failed "prereq" -> CONDITIONAL (an unmet precondition, can be unlocked);
# a failed "hard" -> CONTRADICTED (a world condition contradicting the path).
CHECK_KINDS = ("prereq", "hard")

# Status words for the human reader (the v9 design language). ONE mapping, used by the projection and the
# artifact; the UI never derives its own. STOP has two different origins — `stop_provenance` keeps the origin.
STATUS_WORDS = ("OPEN", "TEST_FIRST", "NOT_YET", "STOP")

# Signal namespaces (the id convention "<kind>:<name>"): the kind determines the provenance column where
# references land.
SIGNAL_STATE = "state"  # verified state claims (Universal State)
SIGNAL_MECHANISM = "mechanism"  # mechanisms detected from evidence
SIGNAL_RULE = "rule"  # active knowledge rules (Active Knowledge)


@dataclass(frozen=True)
class Signal:
    """One reading of verified state. value True/False/None(=not yet known).

    None is NOT False: absence of evidence is never evidence of absence (INV-9).

    `refs`        the underlying evidence/claim references (real provenance, never invented); transcript
                  quotes take the form `transcript:"<quote>"`.
    `basis`       basis detail (e.g. the satisfied rule predicate branch + anchors) — for audit, not logic.
    `unsupported` True = the reader KNOWS a claim exists (e.g. a rule matched) but its basis cannot be formed;
                  the value is `None`, and the generator records it as `unsupported` (PROV-04), never TRUE.
    `assumes`     the absence conditions this TRUE signal relies on (`AbsenceAssumption` as dicts):
                  satisfied because no matching record exists — NOT evidence of absence, never an anchor.
                  Recorded for audit; it never changes the signal value."""

    value: bool | None
    reason: str = ""
    refs: tuple[str, ...] = ()  # the underlying evidence/claim references (real provenance, never invented)
    i18n: dict[str, str] = field(default_factory=dict, compare=False)  # {language: reason sentence}
    basis: tuple[dict, ...] = field(default=(), compare=False)
    unsupported: bool = False
    assumes: tuple[dict, ...] = field(default=(), compare=False)


UNKNOWN_SIGNAL = Signal(None, "", ())

SignalReader = Callable[[str], Signal]

# Signals originating from KNOWLEDGE (not state claims): their TRUE must have a basis that can be shown.
KNOWLEDGE_NAMESPACES = ("mechanism", "rule")


def signal_namespace(sid: str) -> str:
    return sid.partition(":")[0]


def grounded(reader: SignalReader) -> SignalReader:
    """PROV-02 — knowledge signals (`rule:` / `mechanism:`) must never be TRUE without a basis.

    A TRUE without `refs` is downgraded to `None` + `unsupported` (cannot be confirmed), never left
    standing as candidate support. Enforced at the core boundary so it applies to any domain, not just one.
    Idempotent: wrapping an already-`grounded` reader returns that reader itself."""
    if getattr(reader, "_grounded", False):
        return reader

    def read(sid: str) -> Signal:
        sig = reader(sid)
        if sig.value is True and signal_namespace(sid) in KNOWLEDGE_NAMESPACES and not sig.refs:
            return Signal(
                None,
                f"{sid} dilaporkan aktif tetapi tanpa evidence pendukung — tidak dipakai sebagai dasar",
                (),
                {
                    "en": f"{sid} is reported active but no supporting evidence can be shown, "
                    "so it is not used as a basis"
                },
                unsupported=True,
            )
        return sig

    read._grounded = True  # type: ignore[attr-defined]
    return read


# Tri-state predicate: str (a signal id) | {"all_of": [...]} | {"any_of": [...]} | {"not": expr}
Predicate = Union[str, dict]


@dataclass(frozen=True)
class CheckSpec:
    """A world condition that must hold for the path to run. `requirement_id` (when present) = an anchor
    to the Requirement Registry — the canonical identity of that state; WITHOUT an anchor this is a
    path-specific check with no requirement yet (it still has a stable `check_id`, never a human string)."""

    check_id: str
    signal: str
    kind: str = "prereq"
    requirement_id: str | None = None
    unlock: str = ""
    title: str = ""  # display text for a check without a requirement (NOT identity — identity = check_id)
    i18n: dict[str, dict[str, str]] = field(default_factory=dict)  # {language: {title, unlock}}

    def __post_init__(self) -> None:
        if self.kind not in CHECK_KINDS:
            raise ValueError(f"check {self.check_id!r}: kind {self.kind!r} di luar {CHECK_KINDS}")


@dataclass(frozen=True)
class StrategySpec:
    """One strategy = a method/mechanism of moving toward the goal, declared by DOMAIN KNOWLEDGE.

    `emerges_when`      — when this strategy becomes a candidate (a predicate over verified state signals,
                          mechanisms, active rules). Without TRUE support there is no candidate: no path is
                          fabricated because the UI wishes for one.
    `not_applicable_when` — when this strategy does NOT apply (the candidate is discarded, reason recorded).
    `checks`            — the conditions that decide feasibility (candidate evaluation).
    `route_template_ids` — the available route substrate; may be empty (a path is valid without a template).
    `no_preconditions`  — the domain's explicit statement that this strategy has no preconditions. Without it,
                          a strategy without `checks` is UNDETERMINED (nothing to evaluate), never
                          SUPPORTED: "no declared blocker" != "proven viable".
    `motion`            — an optional domain primitive (an opaque label owned by the domain). NOT identity."""

    strategy_id: str
    title: str
    basis: str = ""
    motion: str | None = None
    emerges_when: Predicate = field(default_factory=dict)
    not_applicable_when: Predicate | None = None
    checks: tuple[CheckSpec, ...] = ()
    route_template_ids: tuple[str, ...] = ()
    knowledge_sources: tuple[dict, ...] = ()
    presentation: dict = field(default_factory=dict)  # {lang: {name, word, short}} — human language
    no_preconditions: bool = False

    def __post_init__(self) -> None:
        if not self.strategy_id or not self.strategy_id.replace("_", "").isalnum():
            raise ValueError(f"strategy_id {self.strategy_id!r} harus alfanumerik/underscore")
        if self.no_preconditions and self.checks:
            raise ValueError(f"strategi {self.strategy_id!r}: no_preconditions bertentangan dengan checks")
        # Task F (doc 14 §7): one strategy may own MANY templates, but each template appears EXACTLY
        # ONCE within its strategy. A duplicate = two identical composition entries for the same strategy →
        # two identical routes; the readiness contract rejects two routes per strategy. Failing
        # deterministically here (at authoring) beats silently overwriting and exploding far downstream.
        if len(self.route_template_ids) != len(set(self.route_template_ids)):
            dupes = sorted({t for t in self.route_template_ids if self.route_template_ids.count(t) > 1})
            raise ValueError(
                f"strategi {self.strategy_id!r}: route_template_ids duplikat {dupes} — setiap template "
                "tepat sekali dalam satu strategi (entri ganda = dua route identik)"
            )
        # malformed predicates (e.g. an empty all_of = TRUE with no basis) fail at construction,
        # not at evaluation
        from core.navigation.predicate import signal_ids

        signal_ids(self.emerges_when)
        signal_ids(self.not_applicable_when)


@dataclass(frozen=True)
class MechanismSpec:
    """A causal mechanism that can become ACTIVE because of verified knowledge (Knowledge -> Mechanism).

    A mechanism explains WHY a state implies a possibility. It is not an action, not a
    requirement, not a strategy, and not a route.

    `activated_by`      a predicate over signals (`rule:` / `state:` / a directly-read `mechanism:`).
                        TRUE only when its support is anchored in evidence (an UNSUPPORTED `rule:`
                        signal = None, never activating). None = the mechanism is active only when a
                        domain reader reports it directly as an anchored `mechanism:<id>` signal.
    `contradicted_by`   a predicate over EXPLICIT counter-evidence. Active AND rebutted = CONFLICT
                        (never silently picked); rebutted without activation = the mechanism is FALSE. Absent
                        support is not a rebuttal (absence != evidence of absence)."""

    mechanism_id: str
    title: str = ""
    activated_by: Predicate | None = None
    contradicted_by: Predicate | None = None
    knowledge_sources: tuple[dict, ...] = ()

    def __post_init__(self) -> None:
        if not self.mechanism_id or not self.mechanism_id.replace("_", "").isalnum():
            raise ValueError(f"mechanism_id {self.mechanism_id!r} harus alfanumerik/underscore")
        from core.navigation.predicate import signal_ids

        own = f"{SIGNAL_MECHANISM}:{self.mechanism_id}"
        for label, pred in (("activated_by", self.activated_by), ("contradicted_by", self.contradicted_by)):
            if own in signal_ids(pred):
                raise ValueError(
                    f"mekanisme {self.mechanism_id!r}: {label} merujuk dirinya sendiri (sirkular)"
                )


@dataclass(frozen=True)
class Proposal:
    """What a pattern PROPOSES — identity + proposal content, and the ONLY part of a pattern seen by
    candidate generation (`generate_possibilities`).

    Deliberately carries NO `not_applicable_when`, `checks`, `route_template_ids`, `no_preconditions`:
    those are the EVALUATION substrate (applicability, feasibility, route) read by the evaluator only after
    promotion. A generator that only receives a `Proposal` cannot judge what is not its to judge, and the
    candidates it forms carry no evaluation substrate."""

    direction: str
    title: str
    mechanism_ids: tuple[str, ...]
    thesis: str = ""
    context_when: Predicate | None = None
    presentation: dict = field(default_factory=dict)


@dataclass(frozen=True)
class PossibilityPattern:
    """A mechanism → possibility pattern: "when mechanism M is active, direction D is worth considering".

    A pattern is KNOWLEDGE (domain data), not a path list and not a StrategySpec: it states the
    mechanism → direction relation with its basis. A candidate's semantic identity = `direction` (canonical);
    two mechanisms pointing at the same direction produce ONE candidate with merged provenance.

    Two field groups with different responsibilities (the generation vs evaluation boundary, doc 14 §23.4):

      PROPOSAL (`.proposal` — read by the GENERATOR): `direction`, `title`, `thesis`, `mechanism_ids`
        (any_of: at least one active), `context_when`, `presentation`.
        `context_when` = extra state context (a Kleene predicate over signals, like a strategy's
        `emerges_when`) that must be TRUE for that mechanism to imply this direction; None = no extra context.
        It is NOT a requirement (not a Requirement Registry item, has no satisfaction, forms no checks)
        and never decides feasibility/readiness: TRUE -> a candidate may be born, FALSE -> NOT_EMERGENT,
        unknown -> UNDETERMINED.
      EVALUATION (read by the EVALUATOR after promotion): `not_applicable_when`, `checks`,
        `route_template_ids`, `no_preconditions` — the pattern itself judges nothing. When `direction` equals
        the `strategy_id` of an already-declared strategy, the pattern may only add provenance
        (its evaluation fields must be empty)."""

    direction: str
    title: str
    mechanism_ids: tuple[str, ...]
    thesis: str = ""
    basis: str = ""
    context_when: Predicate | None = None
    not_applicable_when: Predicate | None = None
    checks: tuple[CheckSpec, ...] = ()
    route_template_ids: tuple[str, ...] = ()
    no_preconditions: bool = False
    motion: str | None = None
    knowledge_sources: tuple[dict, ...] = ()
    presentation: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.direction or not self.direction.replace("_", "").isalnum():
            raise ValueError(f"direction {self.direction!r} harus alfanumerik/underscore")
        if not self.mechanism_ids:
            raise ValueError(
                f"pola {self.direction!r}: butuh minimal satu mechanism_id (tanpa mekanisme tidak ada dasar)"
            )
        if len(set(self.mechanism_ids)) != len(self.mechanism_ids):
            raise ValueError(f"pola {self.direction!r}: mechanism_ids duplikat")
        if self.no_preconditions and self.checks:
            raise ValueError(f"pola {self.direction!r}: no_preconditions bertentangan dengan checks")
        if len(self.route_template_ids) != len(set(self.route_template_ids)):
            raise ValueError(f"pola {self.direction!r}: route_template_ids duplikat")
        from core.navigation.predicate import signal_ids

        signal_ids(self.context_when)
        signal_ids(self.not_applicable_when)
        # per-mechanism `because` ({mechanism_id: text}) may only name this pattern's causing mechanisms
        for lang, pres in (self.presentation or {}).items():
            because = (pres or {}).get("because")
            if isinstance(because, dict):
                stray = sorted(set(because) - set(self.mechanism_ids))
                if stray or not all(isinstance(v, str) and v.strip() for v in because.values()):
                    raise ValueError(
                        f"pola {self.direction!r}: presentation[{lang}].because per mekanisme hanya boleh "
                        f"memuat mekanisme penyebab pola (asing: {stray}) dengan teks non-kosong"
                    )

    @property
    def proposal(self) -> Proposal:
        """The part of the pattern the generator may see (without the evaluation substrate)."""
        return Proposal(
            direction=self.direction,
            title=self.title,
            mechanism_ids=self.mechanism_ids,
            thesis=self.thesis,
            context_when=self.context_when,
            presentation=self.presentation,
        )

    @property
    def carries_evaluation(self) -> bool:
        return bool(
            self.checks or self.route_template_ids or self.no_preconditions or self.not_applicable_when
        )

    @property
    def candidate_id(self) -> str:
        return candidate_id_for(self.direction)


@dataclass(frozen=True)
class PossibilitySpace:
    """The possibility space a domain supports: a set of strategies + a goal signal.

    `goal_signal` (optional): the signal that MUST be TRUE before any candidate may appear. An unclear goal
    yields ZERO paths with an explicit reason — never invented paths."""

    space_id: str
    strategies: tuple[StrategySpec, ...]
    goal_signal: str | None = None
    # The Knowledge -> Mechanism -> Candidate Possibility layer (doc 14 §23). Optional: a space with neither
    # behaves exactly as before.
    mechanisms: tuple[MechanismSpec, ...] = ()
    patterns: tuple[PossibilityPattern, ...] = ()

    def __post_init__(self) -> None:
        ids = [s.strategy_id for s in self.strategies]
        if len(ids) != len(set(ids)):
            raise ValueError(f"space {self.space_id!r}: strategy_id duplikat")
        self._validate_candidate_layer(set(ids))
        # The Strategy -> Route Template ontology contract (internal-docs §7): ONE strategy may
        # own many templates, but ONE template belongs to EXACTLY ONE strategy. Route identity
        # (the reconciliation_key) carries strategy_id, so a shared template has no single route meaning.
        # A violation = a deterministic failure here (ROUTE-04), never "last write wins".
        owner: dict[str, str] = {}
        for strat in self.strategies:
            for tid in strat.route_template_ids:
                if tid in owner:
                    raise ValueError(
                        f"space {self.space_id!r}: template {tid!r} diklaim strategi {owner[tid]!r} dan "
                        f"{strat.strategy_id!r} — satu template hanya boleh milik satu strategi"
                    )
                owner[tid] = strat.strategy_id
        for pat in self.patterns:
            for tid in pat.route_template_ids:
                if tid in owner:
                    raise ValueError(
                        f"space {self.space_id!r}: template {tid!r} diklaim {owner[tid]!r} dan pola "
                        f"{pat.direction!r} — satu template hanya boleh milik satu strategi"
                    )
                owner[tid] = pat.direction

    def _validate_candidate_layer(self, strategy_ids: set[str]) -> None:
        """The candidate-layer contract is guarded at construction, never discovered far downstream."""
        from core.navigation.predicate import signal_ids

        mech_ids = [m.mechanism_id for m in self.mechanisms]
        if len(mech_ids) != len(set(mech_ids)):
            raise ValueError(f"space {self.space_id!r}: mechanism_id duplikat")
        derived = {m.mechanism_id for m in self.mechanisms if m.activated_by or m.contradicted_by}
        for m in self.mechanisms:
            for pred in (m.activated_by, m.contradicted_by):
                for sid in signal_ids(pred):
                    kind, _, name = sid.partition(":")
                    if kind == SIGNAL_MECHANISM and name in derived:
                        raise ValueError(
                            f"space {self.space_id!r}: mekanisme {m.mechanism_id!r} bergantung pada "
                            f"mekanisme turunan {name!r} — rantai mekanisme->mekanisme belum didukung"
                        )
        dirs = [p.direction for p in self.patterns]
        if len(dirs) != len(set(dirs)):
            dupes = sorted({d for d in dirs if dirs.count(d) > 1})
            raise ValueError(
                f"space {self.space_id!r}: pola dengan direction ganda {dupes} — satu arah semantik = satu "
                "pola (mekanisme penyebab yang berbeda digabung lewat mechanism_ids)"
            )
        for p in self.patterns:
            if p.direction in strategy_ids and p.carries_evaluation:
                raise ValueError(
                    f"space {self.space_id!r}: pola {p.direction!r} berbagi identitas dengan strategi "
                    "terdeklarasi, sehingga hanya boleh menambah provenance (checks/template/eksklusi "
                    "milik strategi itu, bukan pola)"
                )


def candidate_id_for(direction: str) -> str:
    """The Candidate Possibility identity — canonical from the semantic direction. NOT a replacement
    for `strategy_id`: a candidate is a proposal; path/route identity stays `strategy_id`,
    `path_id`, and `route_id`."""
    return f"cand.{direction}"


def path_id_for(strategy_id: str) -> str:
    """The Possible Path identity — derived from the strategy (the mechanism), NEVER from the motion."""
    return f"path.{strategy_id}"


def display_status(feasibility: str, lifecycle: str) -> str:
    """(Feasibility, Lifecycle) -> the human-reader status word. A pure function, the ONE mapping.

      lifecycle STOPPED (or CLOSED)  -> STOP   (a decision/process; origin in stop_provenance)
      feasibility CONTRADICTED         -> STOP   (an engine finding; origin in stop_provenance)
      SUPPORTED    -> OPEN     CONDITIONAL -> NOT_YET     UNDETERMINED -> TEST_FIRST

    PAUSED never becomes STOP: the path is on hold, its feasibility still reads."""
    if lifecycle in (Lifecycle.STOPPED, Lifecycle.CLOSED) or feasibility == Feasibility.CONTRADICTED:
        return "STOP"
    return {
        Feasibility.SUPPORTED: "OPEN",
        Feasibility.CONDITIONAL: "NOT_YET",
        Feasibility.UNDETERMINED: "TEST_FIRST",
    }[Feasibility(feasibility)]


# The basis of a feasibility decision — explicit names so "no known blocker" cannot masquerade
# as "proven viable" (internal-docs §5).
FEASIBILITY_BASIS_CHECKS = "CHECKS"  # decided from declared, evaluated checks
FEASIBILITY_BASIS_UNCONDITIONAL = "DECLARED_UNCONDITIONAL"  # the strategy DECLARES no preconditions
FEASIBILITY_BASIS_NONE = "NO_CHECKS_DECLARED"  # nothing evaluated -> undetermined, not viable


def feasibility_basis(n_checks: int, unconditional: bool) -> str:
    if n_checks:
        return FEASIBILITY_BASIS_CHECKS
    return FEASIBILITY_BASIS_UNCONDITIONAL if unconditional else FEASIBILITY_BASIS_NONE


def feasibility_from_checks(checks: list[dict[str, Any]], *, unconditional: bool = False) -> Feasibility:
    """Registered checks -> Feasibility. Per-check `state`: PRESENT | ABSENT | UNKNOWN.

    SUPPORTED means: EVERY declared check is proven PRESENT. It does NOT mean route requirements are
    satisfied (satisfaction) and does NOT mean it can be done now (executability) — three separate axes.

    no checks at all                          -> UNDETERMINED  (nothing evaluated; a silently TRUE
                                                 `all([])` is banned). Unless the strategy DECLARES
                                                 `no_preconditions` -> SUPPORTED (a domain statement)
    all PRESENT                               -> SUPPORTED
    any `hard` check ABSENT                   -> CONTRADICTED
    any `prereq` check ABSENT                 -> CONDITIONAL   (a precondition known unmet)
    otherwise (some UNKNOWN)                  -> UNDETERMINED  (not yet judgeable — not a failure)"""
    if not checks:
        return Feasibility.SUPPORTED if unconditional else Feasibility.UNDETERMINED
    if all(c["state"] == "PRESENT" for c in checks):
        return Feasibility.SUPPORTED
    if any(c["state"] == "ABSENT" and c["kind"] == "hard" for c in checks):
        return Feasibility.CONTRADICTED
    if any(c["state"] == "ABSENT" for c in checks):
        return Feasibility.CONDITIONAL
    return Feasibility.UNDETERMINED
