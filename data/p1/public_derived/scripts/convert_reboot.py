"""REBOOT -> P1 converter (v2: up to four cutoff kinds per episode).

Source: HuggingFace org `REBOOT26`, repo `sample_recovery-demonstration`
(tag `license:apache-2.0`; paper *REBOOT: From Failure to Recovery - A Dataset and
Benchmark for Precision Assembly*). Only `meta/phase.json` is read; `data/*.parquet`
trajectories and `videos/` are never downloaded.

An episode annotation gives the five phase names, their frame boundaries
tau_0..tau_5, `episode_type`, and a failure block with `originating_phase`,
`failure_mode`, `induced_at_frame`, `recovery_started_at_frame` and
`language_description`. Those frame numbers are what let this source fill state
values the other two sources cannot, without inventing anything.

Cutoff kinds (encoded in `cutoff_event_id`, hence in `sample_id`, so consumers can
separate blind recovery prediction from state prediction):

  p## / e01_start  cutoff = last phase-progress event before the failure frame.
                             The failure lies in the future and is therefore not in
                             the trace at all: A=NOT_ACCESSED, C=ACTIVE, F=READY,
                             V=VALID. p1_observed_resume=null / "censored" - there
                             is no interruption at this cutoff whose outcome could
                             be observed.
  f01_fail         cutoff = interruption at `induced_at_frame`. F=BLOCKED when the
                             annotated recovery starts strictly later - the source
                             itself annotates an interval in which the plan could
                             not proceed; READY when both frames coincide. The
                             blind recovery sample: the resume event is later and
                             withheld.
  r01_rec          cutoff = the resume event at `recovery_started_at_frame`.
                             F=READY, C=ACTIVE (plan re-engaged). The resume
                             coincides with the cutoff, so its label is visible in
                             the trace - a state sample, not a blind one.
  d01_done         cutoff = a completion event at tau_5, emitted ONLY when the
                             annotated `language_description` asserts completion
                             (explicit marker, no negation) and boundaries are
                             coherent. V=FULFILLED, C=COMPLETED, Q=NOT_APPLICABLE.

RULES

B1 base_story_id .... "{task_id}_ep{episode_index}".
B2 goal_id ........... "{task_id}:{slug(task_description)}".
B3 task_steps ........ annotated `phase_names` as "phase_{i}_{slug(name)}".
B4 phase_of(frame) ... the phase whose annotated interval contains the frame
                      (tau_i <= frame < tau_{i+1}).
B5 timeline ......... start_goal @tau_0; progress @each tau_i entered before the
                      failure; background_fact(failure_mode) @induced;
                      interruption @induced; resume @recovery; completion @tau_5.
                      observed_events is the timeline prefix ending at the cutoff.
                      Event-level person_access is ACCESSED for every event in that
                      prefix (it is recorded history); the state variable A differs
                      because at a pre-failure cutoff the key event is not in the
                      covered past at all.
B6 V ............... VALID while the workflow is outstanding; FULFILLED at _done,
                    which exists only when completion is asserted. A failure inside
                    execution does not cancel the goal, so no CANCELLED here.
B7 F ............... READY before the failure and at/after the recovery frame;
                    BLOCKED at _fail when `recovery_started_at_frame >`
                    `induced_at_frame`; UNKNOWN when the two frames are incoherent.
B8 A ............... NOT_ACCESSED at a pre-failure cutoff; ACCESSED at _fail/_rec/
                    _done, where the annotated recovery after the induced failure
                    shows the event entered the operator's loop. Exposure only, never
                    understanding.
B9 B ............... BELIEVES_VALID wherever a belief is annotated at all: recovery
                    is directed at finishing the original task. No REBOOT row
                    asserts that the operator treated the goal as void, so this
                    source deliberately emits no BELIEVES_INVALID.
B10 C .............. ACTIVE at pre-failure and _rec, SUSPENDED at _fail, COMPLETED at
                    _done. Never ABANDONED: no episode records an abandonment.
B11 Q .............. phase_of(induced_at_frame) at pre-failure/_fail (step in
                    flight); phase_of(recovery_started_at_frame) at _rec (where
                    recovery actually re-entered - may differ from the step in
                    flight, which is exactly the subjective/objective distinction);
                    NOT_APPLICABLE at _done (nothing pending).
B12 resume ....... true / "observed_resume" when the recovery frame is usable
                    (induced < recovery < duration); null / "censored" at pre-failure
                    and for incoherent frames. false would require an episode
                    annotated as failing to recover; all 60 rows are
                    `episode_type="recovery"`, so this source contributes no
                    observed_not_resume either.
B13 DQ1 .......... `failure.originating_phase` disagrees with the phase derived from
                    `induced_at_frame` on most rows (offsets +1/+2, one value 21 out
                    of range). Never used for step ids - the phase comes from the
                    frames, and disagreements are counted at build time.
B15 BELIEVES_INVALID (behavioral, not copied from V)
                    A row whose annotated `failure_mode` is "freeze" describes the
                    acting robot ceasing to act on a goal that the SAME annotation
                    marks completable (`language_description`: "... complete object
                    insertion and release object", and `episode_type="recovery"` with
                    a usable recovery frame). Stopping on a still-valid goal is
                    evidence the actor treated the goal as void, so
                    B=BELIEVES_INVALID while V stays VALID. The two labels come from
                    different annotated fields, which is what keeps this from being
                    the forbidden V->B copy. Any other failure mode (misalignment,
                    slip, jamming, delayed_start, ...) describes the workpiece or the
                    grasp, not the actor giving up, so it does NOT trigger B15.
B14 DQ2 .......... non-monotonic/unclosed tau boundaries and recovery <= induced
                    make phase placement or the blockage interval unusable: those
                    samples degrade to UNKNOWN/censored rather than being silently
                    repaired.
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "raw" / "REBOOT"
OUT = ROOT / "processed" / "reboot.jsonl"

SOURCE_ABBR = "rbt"
SENTINEL = "UNKNOWN"
N_A = "NOT_APPLICABLE"

# B6: completion must be asserted by the annotation, not inferred from phase coverage.
COMPLETE_MARKERS = ("complete", "completed", "finish", "finished", "success", "successfully",
                    "installed", "placed in")
NEG_MARKERS = ("fail", "unable", "cannot", "abort", "incomplete", "did not complete",
               "without completing")

COMMON_FIELDS = {
    "task_id", "task_description", "phase_names", "episode_index", "episode_type",
    "duration_frames", "fps", "phase_boundaries.tau_0..tau_5",
    "failure.induced_at_frame", "failure.recovery_started_at_frame", "failure.failure_mode",
}


def slug(s, limit=40):
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").strip().lower()).strip("-")
    return s[:limit] or "unnamed"


def phase_of(frame, taus, n_phases):
    """B4."""
    if frame is None or len(taus) < 2:
        return None
    for i in range(n_phases):
        if taus[i] <= frame < taus[i + 1]:
            return i
    return None


def asserts_completion(text):
    low = (text or "").lower()
    return any(m in low for m in COMPLETE_MARKERS) and not any(n in low for n in NEG_MARKERS)


def build_repo(phase_path, dq):
    doc = json.loads(phase_path.read_text(encoding="utf-8"))
    repo_tag = f"phase.json ({phase_path.parent.name})"
    names = doc.get("phase_names") or []
    steps = [f"phase_{i}_{slug(n)}" for i, n in enumerate(names)]
    task_id = doc.get("task_id") or phase_path.parent.name
    goal_id = f"{task_id}:{slug(doc.get('task_description'), 48)}"
    samples = []

    for ep in doc.get("episodes", []):
        idx = str(ep.get("episode_index"))
        etype = ep.get("episode_type")
        tb = ep.get("phase_boundaries") or {}
        taus = [tb.get(f"tau_{i}") for i in range(len(names) + 1)]
        fail = ep.get("failure") or {}
        induced = fail.get("induced_at_frame")
        started = fail.get("recovery_started_at_frame")
        duration = ep.get("duration_frames")

        coherent = (
            len(taus) == len(names) + 1
            and all(isinstance(x, int) for x in taus)
            and all(a < b for a, b in zip(taus[:-1], taus[1:]))
            and taus[0] == 0
            and taus[-1] == duration
        )
        if not coherent:
            dq["non_monotonic_or_unclosed_boundaries"] += 1

        fail_phase = phase_of(induced, taus, len(names)) if coherent else None
        rec_phase = phase_of(started, taus, len(names)) if coherent else None
        orig = fail.get("originating_phase")
        if isinstance(orig, int) and not (0 <= orig < len(names)):
            dq["originating_phase_out_of_range"] += 1
        elif isinstance(orig, int) and fail_phase is not None and orig != fail_phase:
            dq["originating_phase_disagrees_with_frame"] += 1

        usable_recovery = (
            induced is not None and started is not None and duration is not None
            and induced < started < duration
        )
        blocked = induced is not None and started is not None and started > induced
        # B15: only "freeze" annotates the actor itself ceasing to act on a goal
        # that the same annotation marks completable.
        actor_froze = (fail.get("failure_mode") == "freeze") and usable_recovery and etype == "recovery"
        if actor_froze:
            dq["belief_invalid_from_freeze_rows"] += 1
        if induced is not None and started is not None and started <= induced:
            dq["recovery_frame_not_after_failure"] += 1
        completes = coherent and asserts_completion(fail.get("language_description"))

        # B5: the episode timeline; each cutoff takes a prefix of it.
        timeline = [{
            "eid": "e01_start", "frame": taus[0] if coherent else 0,
            "etype": "start_goal", "step": steps[0] if steps else None,
        }]
        for i in range(1, len(names)):
            if coherent and induced is not None and taus[i] < induced:
                timeline.append({"eid": f"p{i:02d}", "frame": taus[i],
                                 "etype": "progress", "step": steps[i]})
        if induced is not None:
            fl = steps[fail_phase] if fail_phase is not None else None
            timeline.append({"eid": "bf01", "frame": induced, "etype": "background_fact", "step": fl})
            timeline.append({"eid": "f01_fail", "frame": induced, "etype": "interruption", "step": fl})
        if usable_recovery:
            timeline.append({
                "eid": "r01_rec", "frame": started, "etype": "resume",
                "step": steps[rec_phase] if rec_phase is not None else None,
            })
        if completes:
            timeline.append({"eid": "d01_done", "frame": taus[-1], "etype": "completion",
                             "step": steps[-1] if steps else None})
        timeline.sort(key=lambda e: e["frame"])

        base_id = f"{task_id}_ep{idx}"

        def emit(cutoff_eid, state, resume, resume_step, censoring, extra_fields):
            pos = next((i for i, e in enumerate(timeline) if e["eid"] == cutoff_eid), None)
            if pos is None:
                return
            events = [
                {
                    "event_id": e["eid"],
                    "event_type": e["etype"],
                    "step_id": e["step"],
                    "person_access": "ACCESSED",  # B5: recorded history
                    "source": "original_annotation",
                }
                for e in timeline[: pos + 1]
            ]
            samples.append(
                {
                    "sample_id": f"{SOURCE_ABBR}_{base_id}_{cutoff_eid}",
                    "source_dataset": "REBOOT",
                    "base_story_id": base_id,
                    "goal_id": goal_id,
                    "task_steps": steps,
                    "observed_events": events,
                    "cutoff_event_id": cutoff_eid,
                    "state_at_cutoff": state,
                    "p1_observed_resume": resume,
                    "p1_resume_step": resume_step,
                    "p1_censoring_status": censoring,
                    "evidence_trace": sorted(e["event_id"] for e in events),
                    "original_annotation_ref": {
                        "file": repo_tag,
                        "fields_used": sorted(COMMON_FIELDS | extra_fields),
                    },
                }
            )

        # 1) pre-failure cutoff: last progress event before the failure (or start_goal
        #    when the failure lands in the first phase).
        pre = [e for e in timeline if e["etype"] in ("progress", "start_goal")
               and induced is not None and e["frame"] < induced]
        if pre:
            emit(
                pre[-1]["eid"],
                {"V": "VALID", "F": "READY", "A": "NOT_ACCESSED", "B": "BELIEVES_VALID",
                 "C": "ACTIVE", "Q": (steps[fail_phase] if fail_phase is not None else SENTINEL)},
                None, None, "censored", {"failure.induced_at_frame"},
            )

        # 2) blind recovery sample
        if induced is not None:
            emit(
                "f01_fail",
                {"V": "VALID" if etype == "recovery" else SENTINEL,
                 "F": ("BLOCKED" if blocked else ("READY" if started == induced else SENTINEL)),
                 "A": "ACCESSED",
                 "B": ("BELIEVES_INVALID" if actor_froze else
                       ("BELIEVES_VALID" if etype == "recovery" else SENTINEL)),  # B15
                 "C": "SUSPENDED" if etype == "recovery" else SENTINEL,
                 "Q": (steps[fail_phase] if fail_phase is not None else SENTINEL)},
                True if usable_recovery else None,
                (steps[rec_phase] if usable_recovery and rec_phase is not None else None),
                "observed_resume" if usable_recovery else "censored",
                ({"failure.originating_phase", "failure.language_description",
                  "failure.failure_mode"} if not actor_froze
                 else {"failure.originating_phase", "failure.language_description",
                       "failure.failure_mode", "episode_type"}),
            )

        # 3) state at the annotated recovery frame
        if usable_recovery:
            emit(
                "r01_rec",
                {"V": "VALID", "F": "READY", "A": "ACCESSED", "B": "BELIEVES_VALID",
                 "C": "ACTIVE", "Q": (steps[rec_phase] if rec_phase is not None else SENTINEL)},
                True,
                (steps[rec_phase] if rec_phase is not None else None),
                "observed_resume",
                {"failure.recovery_started_at_frame"},
            )

        # 4) completion sample, only when the annotation asserts completion
        if completes:
            emit(
                "d01_done",
                {"V": "FULFILLED", "F": "READY", "A": "ACCESSED", "B": "BELIEVES_VALID",
                 "C": "COMPLETED", "Q": N_A},
                True,
                (steps[rec_phase] if rec_phase is not None else None),
                "observed_resume",
                {"failure.language_description", "phase_boundaries.tau_5"},
            )
    return samples


def build():
    if not RAW.exists():
        raise SystemExit(f"missing {RAW}: run scripts/fetch_reboot_meta_v2.py first")
    dq, all_samples = Counter(), []
    for path in sorted(RAW.glob("*/phase.json")):
        s = build_repo(path, dq)
        print(f"  {path.parent.name}: {len(s)} samples")
        all_samples.extend(s)
    if not all_samples:
        raise SystemExit("no REBOOT phase.json found under raw/REBOOT/")

    dup = [k for k, v in Counter(s["sample_id"] for s in all_samples).items() if v > 1]
    if dup:
        raise SystemExit(f"duplicate REBOOT sample_ids: {dup[:5]}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="\n") as fh:
        for s in all_samples:
            fh.write(json.dumps(s, ensure_ascii=False) + "\n")
    print(f"wrote {len(all_samples)} P1 samples -> {OUT.relative_to(ROOT)}")
    if dq:
        print(f"  source data-quality counts (B13/B14, reported not repaired): {dict(dq)}")
    for f in ("V", "F", "A", "B", "C", "Q"):
        c = Counter(s["state_at_cutoff"][f] for s in all_samples)
        known = {k: v for k, v in c.items() if k not in (SENTINEL, N_A)}
        print(f"  {f}: {known}  (UNKNOWN={c[SENTINEL]}, NOT_APPLICABLE={c[N_A]})")
    print("  censoring:", dict(Counter(s["p1_censoring_status"] for s in all_samples)))
    kinds = Counter(
        "done" if s["cutoff_event_id"] == "d01_done"
        else "rec" if s["cutoff_event_id"] == "r01_rec"
        else "fail" if s["cutoff_event_id"] == "f01_fail"
        else "pre"
        for s in all_samples
    )
    print(f"  cutoff kinds: {dict(kinds)}")
    return all_samples


if __name__ == "__main__":
    sys.exit(0 if build() else 1)
