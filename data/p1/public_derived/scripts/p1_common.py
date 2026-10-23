"""Shared vocabulary and helpers for the P1 public-derived package (schema p1-0.2).

p1-0.1 asserted a value for every one of the six state factors on every row. The
2026-10-23 review showed most of those assertions were derived from fields that do
not evidence the factor - a robot freezing does not show what it believed, a
retraction spec does not show what an agent abandoned, a rubric existing does not
show that resources were ready. p1-0.2 therefore separates "what the annotation
supports" from "what we once claimed":

  * a factor is supervised only when a named annotated field, or an event that is
    already inside the covered past of the cutoff, states it;
  * anything else becomes UNKNOWN with `state_loss_mask[f] = 0`, and the earlier
    claim is kept in `state_withdrawn` so the decision stays auditable;
  * `label_origin[f]` names the evidence for every supervised factor.

The split is frozen here so all three sources group the same way: samples sharing a
`split_group_id` never straddle train/val/test.
"""

import hashlib
from pathlib import Path

STATE_FIELDS = ("V", "F", "A", "B", "C", "Q")
UNKNOWN = "UNKNOWN"
NOT_APPLICABLE = "NOT_APPLICABLE"

SPLIT_SEED = "p1-split-v1"
SPLIT_RATIOS = (("train", 0.70), ("val", 0.85), ("test", 1.0))
SPLITS = ("train", "val", "test")

SUBJECT_TYPES = ("synthetic_dialogue", "software_agent_spec", "robot")
CUTOFF_KINDS = ("interruption", "pre_interruption", "recovery", "completion", "goal_spec_update")
POSITION_UNITS = ("turn", "frame", "spec_order")

# Reasons recorded in state_withdrawn[f].reason. Kept as constants so the docs and
# the data use the same wording.
W_NO_BELIEVE_EVIDENCE = "no annotation reports the actor's belief; the previous value was derived from the interruption type or from a later recovery"
W_NO_COMMITMENT_EVIDENCE = "no annotation reports the actor's commitment state; withdrawing a requirement is the user's act, not the agent's abandonment"
W_NO_FEASIBILITY_EVIDENCE = "a scoring oracle or a rubric proves a checkable end state exists, not that resources/permissions were ready at the cutoff"
W_NO_ACCESS_EVIDENCE = "a truncated utterance shows the harness intervened, not that the actor accessed the interrupting event"
W_FUTURE_EVENT = "the value was derived from an event later than this cutoff, so it is not available at prediction time"
W_USER_NOT_AGENT = "the annotated field describes the human user's awareness, but the declared actor is the assistant"
W_OBJECTIVE_NOT_SUBJECTIVE = "the source annotates an objective phase/stage, which is not evidence about the actor's subjective pending step"
W_NO_RESUME_OBSERVED = "no run record or post-cutoff behaviour is annotated for this source"
W_ASSERTION_WITHOUT_EVENT = "the label was hardcoded without a resume event in the covered past"
W_NOT_ANNOTATED = "the source annotates no step decomposition for this actor"
W_NO_RUN_RECORD = (
    "the release ships a task specification with no execution log, so nothing records "
    "that this actor received or acted on the injected message"
)


def _rank(key: str) -> bytes:
    return hashlib.sha256(f"{SPLIT_SEED}:{key}".encode("utf-8")).digest()


def split_map(source: str, groups) -> dict:
    """Deterministic, population-aware 70/15/15 over the groups of one source.

    A plain hash bucket is unstable on a small population: IHBench has 45
    conversations and hashing put 3 of them in test, which is not an evaluable slice.
    Ranking the groups by a stable hash and cutting at quantiles keeps the assignment
    reproducible (no RNG, no ordering dependence) while giving every source a slice
    proportional to how many independent groups it actually has.
    """
    ordered = sorted(set(groups), key=lambda g: _rank(f"{source}:{g}"))
    n = len(ordered)
    out = {}
    for i, g in enumerate(ordered):
        u = (i + 0.5) / n
        for name, hi in SPLIT_RATIOS:
            if u < hi:
                out[g] = name
                break
        else:
            out[g] = "test"
    return out


def apply_splits(samples) -> None:
    """Stamp `split` on every sample from its source's own group population."""
    by_source = {}
    for s in samples:
        by_source.setdefault(s["source_dataset"], set()).add(s["split_group_id"])
    for source, groups in by_source.items():
        mapping = split_map(source, groups)
        for s in samples:
            if s["source_dataset"] == source:
                s["split"] = mapping[s["split_group_id"]]


def position(unit: str, value, fps=None, seconds=None) -> dict:
    """An event's place on the source's own order/time axis. `seconds` is only ever
    the annotated frame rate applied to a frame index, never an invented clock."""
    assert unit in POSITION_UNITS, unit
    return {"unit": unit, "value": value, "fps": fps, "seconds": seconds}


def horizon(unit: str, planned, covered, note: str) -> dict:
    return {
        "unit": unit,
        "planned": planned,
        "covered": covered,
        "window_complete": (planned is not None and covered is not None and covered >= planned),
        "note": note,
    }


class State:
    """Per-factor supervised/withheld bookkeeping.

    Every factor must be resolved exactly once, either with `assert_from` (a real
    evidence string naming the annotated field or covered-past event) or with
    `withhold` (why the previous p1-0.1 claim is not supportable). Constructing a
    sample that leaves a factor unresolved is an error, so no factor can silently
    keep a default value.
    """

    def __init__(self):
        self._value, self._origin, self._withdrawn = {}, {}, {}

    def assert_from(self, factor, value, origin, evidence: str):
        assert factor not in self._value, factor
        self._value[factor] = value
        self._origin[factor] = {"origin": origin, "evidence": evidence}

    def withhold(self, factor, claimed, reason, rule: str = ""):
        assert factor not in self._value, factor
        self._value[factor] = UNKNOWN
        self._origin[factor] = None
        self._withdrawn[factor] = {"claimed": claimed, "reason": reason, "rule": rule}

    def build(self) -> dict:
        missing = [f for f in STATE_FIELDS if f not in self._value]
        if missing:
            raise ValueError(f"state factor(s) unresolved: {missing}")
        out = {f: self._value[f] for f in STATE_FIELDS}
        return {
            "state": out,
            "mask": {f: int(out[f] != UNKNOWN) for f in STATE_FIELDS},
            "origin": self._origin,
            "withdrawn": self._withdrawn,
        }


def objective_progress(step_id, origin, evidence) -> dict:
    """The objective/workflow progress reading that a source does annotate, kept
    beside (never inside) the subjective Q factor."""
    return {"step_id": step_id, "origin": origin, "evidence": evidence}


def lf(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
