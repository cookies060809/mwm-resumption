"""IHBench -> P1 converter (schema p1-0.2).

Source: HuggingFace dataset `bosonai/IHBench` (license CC-BY-4.0, not gated),
paper arXiv:2606.19595, toolkit github.com/boson-ai/ihbench (Apache-2.0).
Only the text columns fetched by scripts/fetch_ihbench_text.py are read; the
214 MB of embedded user-turn audio was never transferred.

One P1 sample per annotated interruption point (428 across 45 conversations), plus
one parallel sample per point for the recorded `baseline.parquet` answer of a second
actor, as in p1-0.1 (R10).

WHAT THIS SOURCE ACTUALLY IS

The dataset card states 45 *synthetic* conversations and 428 interruption points; the
baseline column is GPT-4o Audio output shipped as the task-fulfilment anchor. No real
human resumption behaviour is annotated, and the official evaluation scores each point
against a per-turn rubric - not "three shared content words mean resumed". Everything
below keeps that distinction: `subject_type=synthetic_dialogue`, and the resume label
is recorded with `label_origin.resume.origin="heuristic_content_overlap"` so no
consumer can mistake it for a gold label.

TRUST CONVENTION
  observed_events = the episode history up to and including the cutoff, now with the
  real annotated text and an ordered position per event. The post-interruption
  continuation, the rubrics and the withheld tail of the truncated utterance live in
  `label_evidence`, which the delivery checks treat as supervision-only: scripts
  /export_aux_view.py builds the model-visible input from `observed_events` alone and
  asserts that no label_evidence string appears inside the input.
  Turn axis: an assistant utterance at turn k sits at k-0.5 and the interrupting user
  turn at k, so "the outcome is strictly later than the cutoff" is arithmetic rather
  than trust in event order.

RULES (each is a deterministic function of annotated fields)

R1 step ids ......... task_steps = knowledge_base.stages in annotated order, as
                      "stage_{ii}_{slug(name)}".
R2 stage_attribution  an assistant turn is attributed to the stage whose
                      "name + description" shares the most content tokens with
                      the turn's delivered transcript. Accepted only if the best
                      overlap >= 3 tokens and best - second >= 2. Otherwise the
                      turn inherits the running maximum over earlier attributed
                      turns; if nothing is attributable the reading is None.
                      This is a heuristic about the WORKFLOW POSITION, so p1-0.2
                      writes it to `objective_progress` and never into the subjective
                      Q factor.
R3 access ........... `assistant_turn_{t}_original` is non-null exactly when the
                      assistant utterance was cut off mid-turn by the user's barge-in
                      (true for 428/428 points). p1-0.1 read that as the assistant
                      having accessed the interruption; a truncation is evidence the
                      harness intervened, so state A is now masked. Knowledge items
                      keep their annotated access flags but are explicitly attributed
                      to `actor="user"`: `is_user_already_aware` describes the human
                      user, while the declared actor of these samples is the
                      assistant, and the two must not be conflated.
R4 V ................. VALID. 0/428 TF rubrics annotate a withdrawal or a completion
                      of the goal (keyword scan in scripts/eda_ihbench.py), and each
                      conversation is trimmed to end on an outstanding step.
R5 F ............... MASKED. p1-0.1 gave READY whenever `turn_{t}_tf_rubric` existed;
                      a grading rubric proves a checkable next step is defined, not
                      that resources/permissions were ready at the cutoff.
R6 B ............... MASKED. p1-0.1 mapped the annotated interruption type onto belief
                      (correction/topic_switch/pushback -> UNRESOLVED, others ->
                      BELIEVES_VALID). Those are categories of what the *user* said;
                      nothing annotates the assistant's belief, and absent evidence is
                      not UNRESOLVED either.
R7 C ............... SUSPENDED, kept: the cutoff IS a mid-utterance barge-in, evidenced
                      in the annotated truncation, so the plan was interrupted in
                      flight. No IHBench cutoff is a start, an abandonment or a
                      completion.
R8 resume (heuristic, and now honestly labelled as one)
                      withheld = assistant_turn_{t}_original minus its delivered
                      prefix. window = the next RESUME_WINDOW assistant turns inside
                      the episode. Resumed if some window turn either (a) re-delivers
                      RESUME_MIN_OVERLAP+ content tokens of `withheld`, or (b) is
                      attributed to a stage strictly later than stage_at(t).
                      Censoring follows the window that was actually defined: fewer
                      than RESUME_WINDOW assistant turns remain AND no recovery seen
                      -> null / "censored". p1-0.1 censored only below 2 turns, so a
                      3-turn tail could still be scored false; that mixed two
                      different tasks in one column and is fixed here.
                      A recovery seen inside a short window stays a positive - it is
                      an observation, not a guess.
R9 resume_step ....... stage of the window turn that satisfied R8, else null.
R10 second actor ..... the released `baseline.parquet` gives, for every one of the 428
                      points, the GPT-4o Audio response. Emitted as a parallel sample
                      with base_story_id "{cid}@baseline" and identical
                      state_at_cutoff (the state depends only on the pre-cutoff
                      history). Its horizon is the single response, so a negative
                      inside it is a complete-window observation, and its rows share
                      the ORIGINAL conversation_id as `split_group_id`: the two actors
                      can never be split across train/test.
                      p1-0.1 wrote `resume_step = step_of(att)` where `att` is a STAGE
                      index while `step_of` takes a TURN number - the answer was
                      therefore read off the wrong axis. Fixed by `step_of_stage` with
                      a range check.
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

from p1_common import (
    UNKNOWN,
    State,
    horizon,
    objective_progress,
    position,
    split_for,
    W_NO_ACCESS_EVIDENCE,
    W_NO_BELIEVE_EVIDENCE,
    W_NO_FEASIBILITY_EVIDENCE,
    W_OBJECTIVE_NOT_SUBJECTIVE,
)

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "raw" / "IHBench" / "conversations_text.json"
BASELINE = ROOT / "raw" / "IHBench" / "baseline_text.json"
OUT = ROOT / "processed" / "ihbench.jsonl"

SOURCE_ABBR = "ihb"
SOURCE_FILE = "conversations.parquet (bosonai/IHBench, CC-BY-4.0)"
BASELINE_FILE = "baseline.parquet (bosonai/IHBench, CC-BY-4.0)"

MIN_STAGE_TOKENS = 3  # R2
MIN_STAGE_MARGIN = 2  # R2
PLAN_CONTESTING = {"correction", "topic_switch", "pushback"}  # the p1-0.1 R6 grouping
RESUME_WINDOW = 4  # R8: assistant turns inspected after the interruption
RESUME_MIN_OVERLAP = 3  # R8(a): content tokens of the withheld remainder re-delivered
RESUME_EVIDENCE = (
    "heuristic R8: >=3 content tokens of the withheld tail re-delivered inside the "
    "window, or a window turn attributed to a strictly later stage"
)

STOP = set(
    """the a an and or of to in for on with that this it is are was be as at by from
you your we our i my me then than so such not no into over after before while when which who
if but also just please their them us its do does did done will would can could have has had""".split()
)


def toks(s):
    return {w for w in re.findall(r"[a-z0-9]+", (s or "").lower()) if len(w) > 2} - STOP


def slug(s):
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").strip().lower()).strip("-")
    return s[:40] or "unnamed"


def step_id(i, stage):
    return f"stage_{i:02d}_{slug(stage.get('name'))}"


def parse_json_field(value):
    """Some HF parquet struct/list columns arrive as JSON text."""
    if value is None:
        return []
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return []


def attribute_stages(conv, n_turns, stages):
    """R2: stage index per assistant turn (1-based), or None if not attributable."""
    if not stages:
        return {t: None for t in range(1, n_turns + 1)}
    stage_tok = [toks(f"{s.get('name','')} {s.get('description','')}") for s in stages]
    direct = {}
    for t in range(1, n_turns + 1):
        text = toks(conv.get(f"assistant_turn_{t}_transcript"))
        if not text:
            direct[t] = None
            continue
        scored = sorted(((len(text & st), i) for i, st in enumerate(stage_tok)), reverse=True)
        best, best_i = scored[0]
        second = scored[1][0] if len(scored) > 1 else 0
        direct[t] = best_i if best >= MIN_STAGE_TOKENS and best - second >= MIN_STAGE_MARGIN else None
    out, run = {}, None
    for t in range(1, n_turns + 1):
        if direct[t] is not None:
            run = direct[t] if run is None else max(run, direct[t])
            out[t] = direct[t]
        else:
            out[t] = run
    return out


def build():
    if not (SRC.exists() and BASELINE.exists()):
        raise SystemExit(f"missing {SRC} or {BASELINE}: run scripts/fetch_ihbench_text.py first")
    convs = json.loads(SRC.read_text(encoding="utf-8"))
    baseline_rows = json.loads(BASELINE.read_text(encoding="utf-8"))
    baseline = {(b["conversation_id"], int(b["turn"])): b for b in baseline_rows}
    if len(baseline) != len(baseline_rows):
        raise SystemExit("baseline.parquet has duplicate (conversation_id, turn) keys")
    dq = Counter()
    samples = []
    for conv in convs:
        cid = conv["conversation_id"]
        n = int(conv["num_turns"])
        stages = conv.get("knowledge_base", {}).get("stages") or []
        steps = [step_id(i, s) for i, s in enumerate(stages)]
        stage_at = attribute_stages(conv, n, stages)
        stage_tok = [toks(f"{st.get('name','')} {st.get('description','')}") for st in stages]

        def attribute_text(text):
            """R2 applied to arbitrary text (used by R10 for the baseline actor)."""
            tt = toks(text)
            if not tt or not stage_tok:
                return None
            scored = sorted(((len(tt & sk), i) for i, sk in enumerate(stage_tok)), reverse=True)
            best, bi = scored[0]
            second = scored[1][0] if len(scored) > 1 else 0
            return bi if best >= MIN_STAGE_TOKENS and best - second >= MIN_STAGE_MARGIN else None
        domain = (conv.get("domain") or {}).get("id") or "unknown_domain"
        goal_text = conv.get("goal")
        goal_id = f"{domain}:{slug(goal_text)[:48] or cid[:8]}"

        kb = conv.get("knowledge_base") or {}
        known = parse_json_field(kb.get("known_user_information"))
        hidden = parse_json_field((conv.get("user_intent") or {}).get("user_hidden_information"))

        def step_of_stage(i):
            """R10 fix: takes a STAGE index (and bounds-checks it)."""
            if i is None:
                return None
            if not (0 <= i < len(stages)):
                dq["stage_index_out_of_range"] += 1
                return None
            return step_id(i, stages[i])

        def step_of_turn(t):
            """Stage of an assistant TURN, via R2."""
            i = stage_at.get(t)
            return step_of_stage(i)

        def step_of_p101(x):
            """The withdrawn p1-0.1 expression, kept only to count what the axis
            confusion actually changed: `step_of` reads `stage_at[x]`, so passing it a
            stage index looked up a turn instead."""
            i = stage_at.get(x)
            return step_id(i, stages[i]) if i is not None else None

        for t in range(1, n + 1):
            itype = conv.get(f"user_turn_{t}_interruption_type")
            if not itype:
                continue

            spoken = " ".join(
                (conv.get(f"user_turn_{k}_transcript") or "").lower() for k in range(1, t + 1)
            )
            events = []
            for item in known:
                aware = item.get("is_user_already_aware")
                events.append({
                    "event_id": f"bf_known_{slug(item.get('key'))}",
                    "event_type": "background_fact",
                    "step_id": None,
                    # R3: annotates the human user's awareness, not the assistant's access
                    "person_access": (
                        "ACCESSED" if aware is True else "NOT_ACCESSED" if aware is False else "UNCERTAIN"
                    ),
                    "source": "original_annotation",
                    "actor": "user",
                    "text": f"{item.get('key')}: {item.get('value')}",
                    "position": None,
                })
            for item in hidden:
                val = (item.get("value") or "").lower()
                events.append({
                    "event_id": f"bf_hidden_{slug(item.get('key'))}",
                    "event_type": "background_fact",
                    "step_id": None,
                    "person_access": "ACCESSED" if val and val in spoken else "NOT_ACCESSED",
                    "source": "rule_mapping" if val and val in spoken else "original_annotation",
                    "actor": "user",
                    "text": f"{item.get('key')}: {item.get('value')}",
                    "position": None,
                })

            for k in range(1, t + 1):
                events.append({
                    "event_id": f"a{k:02d}",
                    "event_type": "start_goal" if k == 1 else "progress",
                    "step_id": step_of_turn(k),
                    "person_access": "ACCESSED",
                    "source": "original_annotation",
                    "actor": "assistant",
                    "text": conv.get(f"assistant_turn_{k}_transcript"),
                    "position": position("turn", k - 0.5),
                })
                at_cutoff = k == t
                user_text = conv.get(f"user_turn_{k}_transcript")
                events.append({
                    "event_id": f"u{k:02d}",
                    "event_type": "interruption" if at_cutoff else "progress",
                    "step_id": None,
                    "person_access": "ACCESSED",
                    "source": "original_annotation" if at_cutoff else "rule_mapping",
                    "actor": "user",
                    "text": user_text,
                    "position": position("turn", k),
                })
                if at_cutoff:
                    break

            cutoff_id = f"u{t:02d}"
            # R8: content-level recovery test over the in-episode observation window
            delivered = conv.get(f"assistant_turn_{t}_transcript") or ""
            full = conv.get(f"assistant_turn_{t}_original") or delivered
            withheld_text = full[len(delivered):] if len(full) > len(delivered) else ""
            withheld = toks(withheld_text)
            base_stage = stage_at.get(t)
            window = [k for k in range(t + 1, min(t + 1 + RESUME_WINDOW, n + 1))]
            resume_at = None
            for k in window:
                turn_tok = toks(conv.get(f"assistant_turn_{k}_transcript"))
                re_delivered = len(turn_tok & withheld) >= RESUME_MIN_OVERLAP
                advanced = (
                    base_stage is not None
                    and stage_at.get(k) is not None
                    and stage_at[k] > base_stage
                )
                if re_delivered or advanced:
                    resume_at = k
                    break
            if resume_at is not None:
                resumed, censoring = True, "observed_resume"
            elif len(window) < RESUME_WINDOW:
                resumed, censoring = None, "censored"
                dq["short_window_censored"] += 1
            else:
                resumed, censoring = False, "observed_not_resume"
            resume_stage = stage_at.get(resume_at) if resume_at else None
            resume_step = step_of_stage(resume_stage) if resume_at else None
            if resume_at and resume_step is None:
                dq["resume_step_unattributable"] += 1
            tf_rubric = conv.get(f"turn_{t}_tf_rubric")
            rq_rubrics = conv.get(f"turn_{t}_rq_rubrics")
            revealed = [
                f"bf_hidden_{slug(i.get('key'))}"
                for i in hidden
                if (i.get("value") or "").lower() and (i.get("value") or "").lower() in spoken
            ]
            trace = ["a01", f"a{t:02d}", cutoff_id] + revealed
            obj = stage_at.get(t)

            def make_state():
                s = State()
                s.assert_from("V", "VALID", "annotated_goal_outstanding",
                              "no rubric or stage annotation marks the goal withdrawn or completed at this cutoff; the conversation is trimmed on an outstanding step (R4)")
                s.withhold("F", ("READY" if tf_rubric else UNKNOWN), W_NO_FEASIBILITY_EVIDENCE, "R5")
                s.withhold("A", "ACCESSED", W_NO_ACCESS_EVIDENCE, "R3")
                s.withhold("B", ("UNRESOLVED" if itype in PLAN_CONTESTING else "BELIEVES_VALID"),
                           W_NO_BELIEVE_EVIDENCE, "R6")
                s.assert_from("C", "SUSPENDED", "annotated_truncated_utterance",
                              f"assistant_turn_{t}_original is non-null: the utterance was cut mid-flight (R7)")
                s.withhold("Q", (step_of_turn(t) or UNKNOWN), W_OBJECTIVE_NOT_SUBJECTIVE, "R2/R8")
                return s

            st = make_state().build()
            episode_sample = {
                "schema_version": "p1-0.2",
                "sample_id": f"{SOURCE_ABBR}_{cid}_{cutoff_id}",
                "source_dataset": "IHBench",
                "base_story_id": cid,
                "goal_id": goal_id,
                "goal_text": goal_text,
                "subject_type": "synthetic_dialogue",
                "actor_id": f"{cid}:assistant",
                "split_group_id": cid,  # R10: the @baseline rows share this group
                "split": split_for("IHBench", cid),
                "task_steps": steps,
                "observed_events": events,
                "cutoff_event_id": cutoff_id,
                "cutoff_kind": "interruption",
                "observation_horizon": horizon(
                    "assistant_turn", RESUME_WINDOW, len(window),
                    "assistant turns after the interruption that remain inside the episode",
                ),
                "outcome_time": (
                    # a positive is settled by the window turn that recovered; a negative
                    # is settled by the end of the window it was measured against
                    {"unit": "turn", "value": resume_at - 0.5, "event_id": f"a{resume_at:02d}"}
                    if resume_at else
                    ({"unit": "turn", "value": window[-1] - 0.5, "event_id": None}
                     if censoring == "observed_not_resume" and window else None)
                ),
                "eligible_for_resume_eval": censoring != "censored",
                "state_at_cutoff": st["state"],
                "state_loss_mask": st["mask"],
                "label_origin": {**st["origin"],
                                 "resume": ({"origin": "heuristic_content_overlap", "evidence": RESUME_EVIDENCE}
                                            if censoring != "censored" else None),
                                 "resume_step": ({"origin": "heuristic_content_overlap", "evidence": RESUME_EVIDENCE}
                                                 if resume_step else None)},
                "state_withdrawn": st["withdrawn"],
                "objective_progress": (
                    objective_progress(step_of_stage(obj), "heuristic_token_overlap",
                                       f"R2 attributed assistant turn {t} to stage {obj}")
                    if obj is not None else
                    objective_progress(None, "heuristic_token_overlap",
                                       "R2 could not attribute this turn to any stage")
                ),
                "p1_observed_resume": resumed,
                "resume_loss_mask": int(censoring != "censored"),
                "p1_resume_step": resume_step,
                "step_loss_mask": int(resume_step is not None and censoring != "censored"),
                "p1_censoring_status": censoring,
                "evidence_trace": sorted(set(trace)),
                "label_evidence": {
                    "interruption_type": itype,
                    "tf_rubric": tf_rubric,
                    "rq_rubrics": rq_rubrics,
                    "withheld_tail": withheld_text or None,
                    "delivered_prefix": delivered,
                    "window_assistant_transcripts": [
                        conv.get(f"assistant_turn_{k}_transcript") for k in window
                    ],
                    "reaction_profile": (conv.get("user_intent") or {}).get("reaction_profile"),
                    "user_emotion": (conv.get("user_intent") or {}).get("emotion"),
                    "note": "Supervision-only. Never part of the model-visible input.",
                },
                "original_annotation_ref": {
                    "file": SOURCE_FILE,
                    "fields_used": sorted(
                        {
                            "conversation_id",
                            "domain.id",
                            "goal",
                            "num_turns",
                            "knowledge_base.stages[].name",
                            "knowledge_base.stages[].description",
                            "knowledge_base.known_user_information[].is_user_already_aware",
                            "user_intent.user_hidden_information",
                            f"assistant_turn_{t}_transcript",
                            f"assistant_turn_{t}_original",
                            f"user_turn_{t}_transcript",
                            f"user_turn_{t}_interruption_type",
                            f"turn_{t}_tf_rubric",
                            f"turn_{t}_rq_rubrics",
                            *[f"user_turn_{k}_transcript" for k in range(1, t + 1)],
                            *[f"assistant_turn_{k}_transcript" for k in window],
                        }
                    ),
                },
            }
            samples.append(episode_sample)

            # R10: the released baseline response is a recorded behaviour of a
            # second actor at the same cutoff, with the same pre-cutoff history.
            b = baseline.get((cid, t))
            if b is not None and (b.get("response") or "").strip():
                resp = b["response"]
                re_delivered = len(toks(resp) & withheld) >= RESUME_MIN_OVERLAP
                att = attribute_text(resp)
                advanced = stage_at.get(t) is not None and att is not None and att > stage_at[t]
                resumed_b = bool(re_delivered or advanced)
                clone = json.loads(json.dumps(episode_sample, ensure_ascii=False))
                clone["base_story_id"] = f"{cid}@baseline"
                clone["sample_id"] = f"{SOURCE_ABBR}_{cid}@baseline_{cutoff_id}"
                clone["actor_id"] = f"{cid}:gpt4o_audio_baseline"
                clone["p1_observed_resume"] = resumed_b
                clone["p1_resume_step"] = (step_of_turn(t) if re_delivered else step_of_stage(att)) if resumed_b else None
                if resumed_b and not re_delivered:
                    # this is the branch the p1-0.1 axis confusion affected
                    dq["baseline_step_taken_from_stage_axis"] += 1
                    if step_of_p101(att) != clone["p1_resume_step"]:
                        dq["baseline_resume_step_changed_by_index_fix"] += 1
                clone["step_loss_mask"] = int(clone["p1_resume_step"] is not None)
                clone["p1_censoring_status"] = "observed_resume" if resumed_b else "observed_not_resume"
                clone["resume_loss_mask"] = 1
                clone["eligible_for_resume_eval"] = True
                clone["outcome_time"] = {"unit": "turn", "value": t + 0.5, "event_id": "baseline_response"}
                clone["observation_horizon"] = horizon(
                    "single_response", 1, 1,
                    "the released baseline gives exactly one answer per interruption point, so the window is complete by construction",
                )
                clone["label_evidence"] = {
                    "interruption_type": itype,
                    "tf_rubric": tf_rubric,
                    "rq_rubrics": rq_rubrics,
                    "withheld_tail": withheld_text or None,
                    "baseline_response": resp,
                    "note": "Supervision-only. The baseline answer is the labelled outcome and must never enter the input.",
                }
                clone["label_origin"] = {**clone["label_origin"],
                                         "resume": {"origin": "heuristic_content_overlap",
                                                    "evidence": "R10: single released baseline answer tested against R8a/R8b"},
                                         "resume_step": ({"origin": "heuristic_content_overlap",
                                                          "evidence": "R10 step_of_stage(att) - p1-0.1 passed the stage index to step_of(turn)"}
                                                         if clone["p1_resume_step"] else None)}
                ref = clone["original_annotation_ref"]
                ref["file"] = BASELINE_FILE
                ref["fields_used"] = sorted(
                    set(ref["fields_used"])
                    - {f"assistant_turn_{k}_transcript" for k in window}
                    | {"response", "interrupting_user_message_index", "turn"}
                )
                samples.append(clone)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="\n") as fh:
        for s in samples:
            fh.write(json.dumps(s, ensure_ascii=False) + "\n")
    print(f"wrote {len(samples)} P1 samples -> {OUT.relative_to(ROOT)}")
    print(f"  build-time data-quality counts: {dict(dq)}")
    for f in ("V", "F", "A", "B", "C", "Q"):
        sup = sum(s["state_loss_mask"][f] for s in samples)
        c = Counter(s["state_at_cutoff"][f] for s in samples if s["state_loss_mask"][f])
        print(f"  {f}: supervised={sup}/{len(samples)}  values={dict(c)}")
    print("  censoring:", dict(Counter(s["p1_censoring_status"] for s in samples)))
    print("  resume supervised:", sum(s["resume_loss_mask"] for s in samples),
          "| eligible_for_resume_eval:", sum(s["eligible_for_resume_eval"] for s in samples))
    print("  splits:", dict(Counter(s["split"] for s in samples)))
    return samples


if __name__ == "__main__":
    sys.exit(0 if build() else 1)
