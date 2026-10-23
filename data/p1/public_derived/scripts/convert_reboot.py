"""REBOOT -> P1 converter (schema p1-0.2).

Source: HuggingFace org `REBOOT26`, repo `sample_recovery-demonstration`
(tag `license:apache-2.0`; paper *REBOOT: From Failure to Recovery - A Dataset and
Benchmark for Precision Assembly*). Only `meta/phase.json` is read; `data/*.parquet`
trajectories and `videos/` are never downloaded.

An episode annotation gives the five phase names, their frame boundaries tau_0..tau_5,
`episode_type`, and a failure block with `originating_phase`, `failure_mode`,
`induced_at_frame`, `recovery_started_at_frame` and
`language_description`. `fps` turns every frame into a wall-clock time, so a cutoff
and an outcome are comparable without trusting event order.

WHAT THIS SOURCE CAN AND CANNOT SUPPORT

REBOOT annotates a *robot* assembly episode and an expert-led recovery demonstration.
No human subjective state is annotated, and no execution log reports what the acting
system believed or was committed to. p1-0.1 filled V/F/A/B/C/Q on all 192 rows; most
of those assertions came either from a phase boundary that lies in the future of the
cutoff or from `episode_type="recovery"`, i.e. from knowing the ending. p1-0.2 keeps
only what is true at the cutoff itself and masks the rest (see
scripts/p1_common.py for the withdrawal vocabulary and docs/transformation_notes.md
for the per-rule decision).

Cutoff kinds (in `cutoff_event_id`, hence in `sample_id`):

  p## / e01_start  cutoff_kind=pre_interruption - last phase-progress event before
                             the failure frame. The failure is not in the covered
                             past, so it cannot be labelled NOT_ACCESSED either.
                             V=VALID and C=ACTIVE from the in-flight phase; F/A/B/Q
                             masked. resume=null, censored, not eligible.
  f01_fail         cutoff_kind=interruption - the induced failure frame. The blind
                             recovery sample: only V is supported at the cutoff;
                             F/A/B/C are masked because the only evidence for them is
                             the recovery that happens later.
  r01_rec          cutoff_kind=recovery - the annotated resume frame itself. The
                             resume coincides with the cutoff, so it is visible in the
                             input: a state sample (resume_loss_mask=0,
                             eligible_for_resume_eval=false), not a blind one. F/A/B/C
                             are supported here because re-engagement IS the event.
  d01_done         cutoff_kind=completion - emitted only when the annotated
                             `language_description` asserts completion (explicit
                             marker, no negation) and boundaries are coherent.
                             V=FULFILLED, C=COMPLETED, Q=NOT_APPLICABLE.

RULES

B1 base_story_id .... "{task_id}_ep{episode_index}".
B2 goal_id ........... "{task_id}:{slug(task_description)}".
B3 task_steps ........ annotated `phase_names` as "phase_{i}_{slug(name)}".
B4 phase_of(frame) ... the phase whose annotated interval contains the frame
                      (tau_i <= frame < tau_{i+1}).
B5 timeline ......... start_goal @tau_0; progress @each tau_i entered before the
                      failure; background_fact(failure_mode) @induced;
                      interruption @induced; resume @recovery; completion @tau_5.
                      observed_events is the timeline prefix ending at the cutoff,
                      each event carrying its frame, its seconds and its annotated
                      text. The `language_description` names the recovery, so it
                      never enters a pre/fail prefix: it is only attached to the
                      resume/completion events, which exist at/after the recovery.
B6 V ............... VALID while the workflow is outstanding (the goal block is never
                    rewritten by the annotation); FULFILLED at _done, which exists
                    only when completion is asserted. A failure inside execution does
                    not cancel the goal, so no CANCELLED here.
B7 F ............... READY only at _rec, where the annotated recovery frame shows the
                    plan proceeding again. MASKED at pre/_fail: nothing annotates
                    resources, permissions or dependencies, and p1-0.1's BLOCKED came
                    from `recovery_started_at_frame > induced_at_frame` - a statement
                    about the future.
B8 A ............... ACCESSED only at _rec, where acting again on the annotated
                    failure IS the access. MASKED at pre (the event has not occurred,
                    so it is not an un-accessed event either) and at _fail (p1-0.1
                    justified it by the later recovery).
B9 B ............... BELIEVES_VALID only at _rec/_done, where re-engagement with the
                    original task_description is the annotated behaviour. MASKED at
                    pre/_fail, including the single `failure_mode="freeze"` row:
                    stopping can be a control fault as well as a belief, so that
                    supervision is withdrawn rather than balanced with new samples.
B10 C .............. ACTIVE at pre (a phase is demonstrably in flight) and _rec,
                    COMPLETED at _done. SUSPENDED at _fail is masked: the annotated
                    fault describes the workpiece or the grasp, not whether the plan
                    was paused or given up. Never ABANDONED - no episode records it.
B11 Q .............. MASKED everywhere. The source annotates an objective phase, which
                    is not a subjective pending step; the reading is preserved in
                    `objective_progress` from the frame at/inside this cutoff only.
                    p1-0.1 also took the pre-sample Q from the *future* failure phase.
B12 resume ....... true / "observed_resume" at _fail when the recovery frame is usable
                    (induced < recovery < duration) - this is the prediction target,
                    so the future is the label, never the input. null / "censored" at
                    pre-failure and for incoherent frames. All 60 rows are
                    `episode_type="recovery"`, so this source contributes no
                    observed_not_resume either. At _rec/_done the value is an observed
                    fact inside the input: kept, but resume_loss_mask=0 and
                    eligible_for_resume_eval=false. A _done row whose episode has no
                    usable recovery frame no longer keeps p1-0.1's hardcoded true.
B13 DQ1 .......... `failure.originating_phase` disagrees with the phase derived from
                    `induced_at_frame` on most rows (offsets +1/+2, one value 21 out
                    of range). Never used for step ids - the phase comes from the
                    frames, and disagreements are counted at build time.
B14 DQ2 .......... non-monotonic/unclosed tau boundaries and recovery <= induced make
                    phase placement unusable: those samples degrade to UNKNOWN /
                    censored rather than being silently repaired.
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

from p1_common import (
    NOT_APPLICABLE,
    UNKNOWN,
    State,
    horizon,
    objective_progress,
    split_for,
    W_ASSERTION_WITHOUT_EVENT,
    W_FUTURE_EVENT,
    W_NO_BELIEVE_EVIDENCE,
    W_NO_COMMITMENT_EVIDENCE,
    W_NO_FEASIBILITY_EVIDENCE,
    W_OBJECTIVE_NOT_SUBJECTIVE,
)

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "raw" / "REBOOT"
OUT = ROOT / "processed" / "reboot.jsonl"

SOURCE_ABBR = "rbt"
SENTINEL = UNKNOWN
N_A = NOT_APPLICABLE

# B6: completion must be asserted by the annotation, not inferred from phase coverage.
COMPLETE_MARKERS = ("complete", "completed", "finish", "finished", "success", "successfully",
                    "installed", "placed in")
NEG_MARKERS = ("fail", "unable", "cannot", "abort", "incomplete", "did not complete",
               "without completing")


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
    doc_names = doc.get("phase_names") or []
    task_id = doc.get("task_id") or phase_path.parent.name
    goal_text = doc.get("task_description")
    goal_id = f"{task_id}:{slug(goal_text, 48)}"
    samples = []

    for ep in doc.get("episodes", []):
        idx = str(ep.get("episode_index"))
        etype = ep.get("episode_type")
        names = ep.get("phase_names") or doc_names
        steps = [f"phase_{i}_{slug(n)}" for i, n in enumerate(names)]
        fps = ep.get("fps")
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
        if ep.get("phase_names") and names != doc_names:
            dq["episode_phase_names_differ_from_doc"] += 1

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
        if induced is not None and started is not None and started <= induced:
            dq["recovery_frame_not_after_failure"] += 1
        completes = coherent and asserts_completion(fail.get("language_description"))
        # p1-0.1 rule B15 (failure_mode=freeze -> BELIEVES_INVALID) is withdrawn: see
        # docs/transformation_notes.md. Counted so the audit trail records the retraction.
        if fail.get("failure_mode") == "freeze":
            dq["belief_invalid_from_freeze_rows_withdrawn"] += 1

        def sec(frame):
            return round(frame / fps, 3) if (isinstance(frame, int) and fps) else None

        # B5: the episode timeline; each cutoff takes a prefix of it.
        timeline = [{
            "eid": "e01_start", "frame": taus[0] if coherent else 0, "etype": "start_goal",
            "step": steps[0] if steps else None, "actor": "robot",
            "text": ep.get("task_description") or goal_text,
        }]
        for i in range(1, len(names)):
            if coherent and induced is not None and taus[i] < induced:
                timeline.append({"eid": f"p{i:02d}", "frame": taus[i], "etype": "progress",
                                 "step": steps[i], "actor": "robot",
                                 "text": f"entered phase {i}: {names[i]}"})
        if induced is not None:
            fl = steps[fail_phase] if fail_phase is not None else None
            fault = f"failure_mode={fail.get('failure_mode')}"
            timeline.append({"eid": "bf01", "frame": induced, "etype": "background_fact",
                             "step": fl, "actor": "workpiece", "text": fault})
            timeline.append({"eid": "f01_fail", "frame": induced, "etype": "interruption",
                             "step": fl, "actor": "workpiece", "text": fault})
        if usable_recovery:
            timeline.append({
                "eid": "r01_rec", "frame": started, "etype": "resume",
                "step": steps[rec_phase] if rec_phase is not None else None,
                "actor": "robot", "text": fail.get("language_description"),
            })
        if completes:
            timeline.append({"eid": "d01_done", "frame": taus[-1], "etype": "completion",
                             "step": steps[-1] if steps else None, "actor": "robot",
                             "text": fail.get("language_description")})
        timeline.sort(key=lambda e: e["frame"])
        by_eid = {e["eid"]: e for e in timeline}

        base_id = f"{task_id}_ep{idx}"
        group = base_id

        def emit(cutoff_eid, cutoff_kind, build_state, resume, resume_step, censoring,
                 extra_fields, prog_phase, eligible, horizon_, withdrawn_resume=None):
            pos = next((i for i, e in enumerate(timeline) if e["eid"] == cutoff_eid), None)
            if pos is None:
                return
            events = []
            for e in timeline[: pos + 1]:
                events.append({
                    "event_id": e["eid"],
                    "event_type": e["etype"],
                    "step_id": e["step"],
                    "person_access": "ACCESSED",  # B5: recorded history
                    "source": "original_annotation",
                    "actor": e["actor"],
                    "text": e["text"],
                    "position": {
                        "unit": "frame", "value": e["frame"], "fps": fps,
                        "seconds": sec(e["frame"]),
                    },
                })
            st = build_state().build()
            outcome = None
            if eligible and censoring == "observed_resume":
                outcome = {"unit": "frame", "value": started, "event_id": "r01_rec"}
            withdrawn = dict(st["withdrawn"])
            if withdrawn_resume:
                withdrawn.update({"p1_observed_resume": withdrawn_resume})
            samples.append({
                "schema_version": "p1-0.2",
                "sample_id": f"{SOURCE_ABBR}_{base_id}_{cutoff_eid}",
                "source_dataset": "REBOOT",
                "base_story_id": base_id,
                "goal_id": goal_id,
                "goal_text": ep.get("task_description") or goal_text,
                "subject_type": "robot",
                "actor_id": f"{base_id}:robot",
                "split_group_id": group,
                "split": split_for("REBOOT", group),
                "task_steps": steps,
                "observed_events": events,
                "cutoff_event_id": cutoff_eid,
                "cutoff_kind": cutoff_kind,
                "observation_horizon": horizon_,
                "outcome_time": outcome,
                "eligible_for_resume_eval": eligible,
                "state_at_cutoff": st["state"],
                "state_loss_mask": st["mask"],
                "label_origin": {**st["origin"],
                                 "resume": (
                                     {"origin": "annotated_recovery_frame",
                                      "evidence": f"recovery_started_at_frame={started} lies after induced_at_frame={induced} and inside the episode"}
                                     if eligible and censoring != "censored" else None),
                                 "resume_step": (
                                     {"origin": "annotated_frame_at_recovery",
                                      "evidence": f"phase_of(recovery_started_at_frame={started}) over annotated tau boundaries"}
                                     if eligible and resume_step else None)},
                "state_withdrawn": withdrawn,
                "objective_progress": (
                    objective_progress(
                        steps[prog_phase] if prog_phase is not None else None,
                        "annotated_frame_at_cutoff",
                        f"phase_of(cutoff frame {by_eid[cutoff_eid]['frame']}) over annotated tau boundaries",
                    ) if prog_phase is not None else
                    objective_progress(None, "not_annotated", "boundaries incoherent or frame out of range (B14)")
                ),
                "p1_observed_resume": resume,
                "resume_loss_mask": int(censoring != "censored" and eligible),
                "p1_resume_step": resume_step,
                "step_loss_mask": int(resume_step is not None and censoring != "censored" and eligible),
                "p1_censoring_status": censoring,
                "evidence_trace": sorted(e["event_id"] for e in events),
                "label_evidence": {
                    "annotated_failure_mode": fail.get("failure_mode"),
                    "annotated_language_description": fail.get("language_description"),
                    "annotated_originating_phase": orig,
                    "annotated_operator_id": ep.get("operator_id"),
                    "annotated_collection_session": ep.get("collection_session"),
                    "note": "REBOOT annotates robot assembly frames and an expert-led recovery; no human subjective state is labelled. language_description names the recovery, so it is supervision-only for pre/fail cutoffs.",
                },
                "original_annotation_ref": {
                    "file": repo_tag,
                    "fields_used": sorted(COMMON_FIELDS | extra_fields),
                },
            })

        # 1) pre-failure cutoff: last progress event before the failure (or start_goal
        #    when the failure lands in the first phase).
        pre = [e for e in timeline if e["etype"] in ("progress", "start_goal")
               and induced is not None and e["frame"] < induced]
        if pre:
            cutoff = pre[-1]["eid"]
            at_frame = by_eid[cutoff]["frame"]
            pre_phase = phase_of(at_frame, taus, len(names)) if coherent else None
            pre_step = steps[pre_phase] if pre_phase is not None else None

            def pre_state():
                s = State()
                s.assert_from("V", "VALID", "annotated_workflow_outstanding",
                              "no annotated field rewrites or completes the goal before the failure frame")
                s.withhold("F", "READY", W_NO_FEASIBILITY_EVIDENCE, "B7")
                s.withhold("A", "NOT_ACCESSED", W_FUTURE_EVENT, "B8")
                s.withhold("B", "BELIEVES_VALID", W_NO_BELIEVE_EVIDENCE, "B9")
                s.assert_from("C", "ACTIVE", "annotated_phase_in_flight",
                              f"cutoff frame {at_frame} lies inside the annotated phase interval of {pre_step}")
                s.withhold("Q", (pre_step or "step at the future failure frame"), W_FUTURE_EVENT + "; " + W_OBJECTIVE_NOT_SUBJECTIVE, "B11")
                return s

            emit(
                cutoff, "pre_interruption", pre_state,
                None, None, "censored", {"failure.induced_at_frame"},
                None, False,
                horizon("episode_tail", None, None,
                        "no interruption exists at this cutoff, so no outcome can be observed"),
            )

        # 2) blind recovery sample
        if induced is not None:
            def fail_state():
                s = State()
                s.assert_from("V", "VALID", "annotated_goal_not_rewritten",
                              'the goal block is unchanged and episode_type="recovery" annotates a fault inside execution, not a withdrawal')
                s.withhold("F", ("BLOCKED" if started is not None and induced is not None and started > induced else "READY"),
                           W_FUTURE_EVENT, "B7")
                s.withhold("A", "ACCESSED", W_FUTURE_EVENT, "B8")
                s.withhold("B", ("BELIEVES_INVALID" if fail.get("failure_mode") == "freeze" else "BELIEVES_VALID"),
                           W_NO_BELIEVE_EVIDENCE, "B9")
                s.withhold("C", "SUSPENDED", W_NO_COMMITMENT_EVIDENCE, "B10")
                s.withhold("Q", (steps[fail_phase] if fail_phase is not None else SENTINEL),
                           W_OBJECTIVE_NOT_SUBJECTIVE, "B11")
                return s

            emit(
                "f01_fail", "interruption", fail_state,
                True if usable_recovery else None,
                (steps[rec_phase] if usable_recovery and rec_phase is not None else None),
                "observed_resume" if usable_recovery else "censored",
                ({"failure.originating_phase", "failure.language_description", "failure.failure_mode"}
                 if fail.get("failure_mode") != "freeze"
                 else {"failure.originating_phase", "failure.language_description",
                       "failure.failure_mode", "episode_type"}),
                fail_phase, bool(usable_recovery),
                horizon("episode_tail",
                        (duration - induced) if (duration is not None and induced is not None) else None,
                        (duration - induced) if (duration is not None and induced is not None) else None,
                        "annotated episode tail after the failure frame; the recovery frame itself is the outcome, and it is withheld from the input"),
            )

        # 3) state at the annotated recovery frame
        if usable_recovery:
            def rec_state():
                s = State()
                s.assert_from("V", "VALID", "annotated_recovery_targets_original_goal",
                              "the recovery frame continues the same task_description")
                s.assert_from("F", "READY", "annotated_recovery_frame_at_cutoff",
                              f"the actor proceeds again at frame {started}")
                s.assert_from("A", "ACCESSED", "annotated_recovery_frame_at_cutoff",
                              "acting again on the annotated failure is the access event itself")
                s.assert_from("B", "BELIEVES_VALID", "annotated_recovery_frame_at_cutoff",
                              "re-engagement with the original task is observed behaviour at the cutoff")
                s.assert_from("C", "ACTIVE", "annotated_recovery_frame_at_cutoff",
                              f"phase {rec_phase} is being executed again at frame {started}")
                s.withhold("Q", (steps[rec_phase] if rec_phase is not None else SENTINEL),
                           W_OBJECTIVE_NOT_SUBJECTIVE, "B11")
                return s

            emit(
                "r01_rec", "recovery", rec_state,
                True,
                (steps[rec_phase] if rec_phase is not None else None),
                "observed_resume",
                {"failure.recovery_started_at_frame"},
                rec_phase, False,
                horizon("episode_tail", None, None,
                        "the resume event coincides with the cutoff and is inside the input: state sample, not blind recovery"),
            )

        # 4) completion sample, only when the annotation asserts completion
        if completes:
            hardcoded_resume = not usable_recovery
            if hardcoded_resume:
                dq["done_rows_with_resume_assertion_withdrawn"] += 1

            def done_state():
                s = State()
                s.assert_from("V", "FULFILLED", "annotated_language_description",
                              f'language_description asserts completion: {fail.get("language_description")!r}')
                s.withhold("F", "READY", "the goal is already complete, so readiness at this cutoff is not annotated", "B7")
                s.assert_from("A", "ACCESSED", "annotated_completed_episode",
                              "the whole annotated episode interval lies in the covered past")
                s.assert_from("B", "BELIEVES_VALID", "annotated_completed_episode",
                              "completing the original goal is observed behaviour")
                s.assert_from("C", "COMPLETED", "annotated_language_description",
                              "completion asserted by the same annotated field as V")
                s.assert_from("Q", N_A, "annotated_language_description",
                              "nothing is pending once completion is asserted")
                return s

            emit(
                "d01_done", "completion", done_state,
                (None if hardcoded_resume else True),
                (None if hardcoded_resume else (steps[rec_phase] if rec_phase is not None else None)),
                ("censored" if hardcoded_resume else "observed_resume"),
                {"failure.language_description", "phase_boundaries.tau_5"},
                phase_of(taus[-1] - 1, taus, len(names)) if coherent else None, False,
                horizon("episode_tail", 0, 0, "episode ends at the cutoff"),
                ({"claimed": "true", "reason": W_ASSERTION_WITHOUT_EVENT, "rule": "B12"}
                 if hardcoded_resume else None),
            )
    return samples


COMMON_FIELDS = {
    "task_id", "task_description", "phase_names", "episode_index", "episode_type",
    "duration_frames", "fps", "phase_boundaries.tau_0..tau_5",
    "failure.induced_at_frame", "failure.recovery_started_at_frame", "failure.failure_mode",
}


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
        sup = sum(s["state_loss_mask"][f] for s in all_samples)
        c = Counter(s["state_at_cutoff"][f] for s in all_samples if s["state_loss_mask"][f])
        print(f"  {f}: supervised={sup}/{len(all_samples)}  values={dict(c)}")
    print("  censoring:", dict(Counter(s["p1_censoring_status"] for s in all_samples)))
    print("  resume supervised:", sum(s["resume_loss_mask"] for s in all_samples),
          "| eligible_for_resume_eval:", sum(s["eligible_for_resume_eval"] for s in all_samples))
    kinds = Counter(s["cutoff_kind"] for s in all_samples)
    print(f"  cutoff kinds: {dict(kinds)}")
    print("  splits:", dict(Counter(s["split"] for s in all_samples)))
    return all_samples


if __name__ == "__main__":
    sys.exit(0 if build() else 1)
