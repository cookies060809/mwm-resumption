"""IHBench -> P1 converter.

Source: HuggingFace dataset `bosonai/IHBench` (license CC-BY-4.0, not gated),
paper arXiv:2606.19595, toolkit github.com/boson-ai/ihbench (Apache-2.0).
Only the text columns fetched by scripts/fetch_ihbench_text.py are read; the
214 MB of embedded user-turn audio was never transferred.

One P1 sample per annotated interruption point (428 across 45 conversations).
`user_turn_{t}_interruption_type` + `turn_{t}_tf_rubric` are the source
annotations that define an interruption point. No label below is model
generated; where the source is silent the value is UNKNOWN or null.

TRUST CONVENTION
  observed_events = the episode history up to and including the cutoff. The
  post-interruption continuation is deliberately NOT included, because it is
  what `p1_observed_resume` labels; including it would leak the answer.
  `event.source` describes how the event's existence and type were obtained;
  `person_access` is justified by R3.

RULES (each is a deterministic function of annotated fields)

R1 step ids ......... task_steps = knowledge_base.stages in annotated order, as
                      "stage_{ii}_{slug(name)}".
R2 stage_attribution  an assistant turn is attributed to the stage whose
                      "name + description" shares the most content tokens with
                      the turn's delivered transcript. Accepted only if the best
                      overlap >= 3 tokens and best - second >= 2. Otherwise the
                      turn inherits the running maximum over earlier attributed
                      turns (the workflow is monotone); if nothing is attributable
                      the state stays UNKNOWN instead of being guessed.
R3 A / access ....... `assistant_turn_{t}_original` is non-null exactly when the
                      assistant utterance was cut off mid-turn by the user's
                      barge-in (true for 428/428 points). An utterance can only
                      be truncated if the system detected the onset, so the
                      interrupting event is ACCESSED. Knowledge items take their
                      access from the annotated `is_user_already_aware`; hidden
                      items are NOT_ACCESSED unless their value text occurs in a
                      user transcript at or before the cutoff.
R4 V ................. VALID. 0/428 TF rubrics annotate a withdrawal or a
                      completion of the goal (keyword scan in
                      scripts/eda_ihbench.py: two false-positive "wrap up" hits,
                      both mid-workflow confirmations), and each conversation is
                      trimmed to end on an outstanding step. IHBench therefore
                      supplies no CANCELLED/FULFILLED case - those come from
                      InterruptBench retractions.
R5 F ................. READY when the cutoff carries a non-null
                      `turn_{t}_tf_rubric` (an annotated actionable next step
                      exists), else UNKNOWN.
R6 B ................. BELIEVES_VALID for the interruption types that do not
                      contest the plan in flight {filler, impatient, normal};
                      UNRESOLVED for {correction, topic_switch, pushback}, which
                      inject user content that contradicts or redirects it. The
                      type is annotated; the grouping is this rule and nothing
                      further is claimed about the agent's belief.
R7 C ................. SUSPENDED: by R3 every IHBench cutoff is a mid-utterance
                      barge-in, i.e. the workflow was paused in flight. No
                      IHBench cutoff is a start, an abandonment or a completion.
R8 resume (content test, not mere continuation)
                      withheld = assistant_turn_{t}_original minus its delivered
                      prefix = the content the agent never got to say.
                      window   = the next RESUME_WINDOW assistant turns inside the
                      episode. The goal is counted as resumed only if some window
                      turn either (a) re-delivers RESUME_MIN_OVERLAP+ content tokens
                      of `withheld` (the cut-off step actually gets said), or
                      (b) is attributed to a stage strictly later than stage_at(t)
                      (the workflow advanced past the interrupted step).
                      Repeating the goal in words without delivering step content,
                      or returning to the same step, does not satisfy either test -
                      per the field-semantics brief that is not a recovery.
                      Outcome: (a)/(b) met -> true / "observed_resume"; window
                      covered but neither met -> false / "observed_not_resume";
                      fewer than RESUME_MIN_WINDOW assistant turns remain (the 45
                      final-turn points, where the dataset is trimmed exactly at the
                      interruption) -> null / "censored". Censoring requires both
                      conditions, so a recovery seen inside a short window still
                      counts as observed.
R9 resume_step ....... stage of the window turn that satisfied R8, else null.
                      evidence_trace documents state_at_cutoff only; the resume
                      label's evidence is the annotation reference plus R8, because
                      the post-cutoff turns are deliberately withheld from the
                      sample (see TRUST CONVENTION).
R10 second actor ..... the released `baseline.parquet` gives, for every one of the
                      428 interruption points, the GPT-4o Audio response that the
                      dataset ships as the task-fulfilment anchor. That is a
                      recorded behaviour of a *different* actor at the *same*
                      cutoff, so it is emitted as a parallel sample with
                      base_story_id "{conversation_id}@baseline" and identical
                      state_at_cutoff (the state depends only on the pre-cutoff
                      history, which the two actors share).
                      Its window is the single response, so the criterion is
                      window-free: the response either continues the step or it
                      does not.
                        - resumes when it re-delivers RESUME_MIN_OVERLAP+ content
                          tokens of `withheld` (R8a) or is attributed by R2 to a
                          stage strictly later than stage_at(t);
                        - otherwise false / "observed_not_resume" - here absence of
                          resumption inside the response IS an observation, not an
                          uncovered window, so no sample from this actor is censored.
                      resume_step = step_of(t) when it completes the cut-off step,
                      else the stage the response is attributed to.
                      The two actors can disagree at the same cutoff; that is a
                      property of the source, not a labelling conflict, and it is
                      what turns this set into a usable negative class.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "raw" / "IHBench" / "conversations_text.json"
BASELINE = ROOT / "raw" / "IHBench" / "baseline_text.json"
OUT = ROOT / "processed" / "ihbench.jsonl"

SOURCE_ABBR = "ihb"
SOURCE_FILE = "conversations.parquet (bosonai/IHBench, CC-BY-4.0)"
BASELINE_FILE = "baseline.parquet (bosonai/IHBench, CC-BY-4.0)"

PLAN_CONTESTING = {"correction", "topic_switch", "pushback"}  # R6

STOP = set(
    """the a an and or of to in for on with that this it is are was be as at by from
you your we our i my me then than so such not no into over after before while when which who
if but also just please their them us its do does did done will would can could have has had""".split()
)

MIN_STAGE_TOKENS = 3  # R2
MIN_STAGE_MARGIN = 2  # R2
RESUME_WINDOW = 4  # R8: assistant turns inspected after the interruption
RESUME_MIN_OVERLAP = 3  # R8(a): content tokens of the withheld remainder re-delivered
RESUME_MIN_WINDOW = 2  # R8: below this the observation window is not covered -> censored


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
    """R2: stage index per assistant turn (1-based), or None if no stage exists."""
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
    convs = json.loads(SRC.read_text(encoding="utf-8"))
    baseline_rows = json.loads(BASELINE.read_text(encoding="utf-8"))
    baseline = {(b["conversation_id"], int(b["turn"])): b for b in baseline_rows}
    if len(baseline) != len(baseline_rows):
        raise SystemExit("baseline.parquet has duplicate (conversation_id, turn) keys")
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
        goal_id = f"{domain}:{slug(conv.get('goal'))[:48] or cid[:8]}"

        kb = conv.get("knowledge_base") or {}
        known = parse_json_field(kb.get("known_user_information"))
        hidden = parse_json_field((conv.get("user_intent") or {}).get("user_hidden_information"))

        def step_of(t):
            i = stage_at.get(t)
            return step_id(i, stages[i]) if i is not None else None

        def q_of(t):
            return step_of(t) or "UNKNOWN"

        for t in range(1, n + 1):
            itype = conv.get(f"user_turn_{t}_interruption_type")
            if not itype:
                continue

            spoken = " ".join(
                (conv.get(f"user_turn_{k}_transcript") or "").lower() for k in range(1, t + 1)
            )
            events = []
            # background facts (R3), clipped to what holds at the cutoff
            for item in known:
                aware = item.get("is_user_already_aware")
                events.append(
                    {
                        "event_id": f"bf_known_{slug(item.get('key'))}",
                        "event_type": "background_fact",
                        "step_id": None,
                        "person_access": (
                            "ACCESSED" if aware is True else "NOT_ACCESSED" if aware is False else "UNCERTAIN"
                        ),
                        "source": "original_annotation",
                    }
                )
            for item in hidden:
                val = (item.get("value") or "").lower()
                events.append(
                    {
                        "event_id": f"bf_hidden_{slug(item.get('key'))}",
                        "event_type": "background_fact",
                        "step_id": None,
                        "person_access": "ACCESSED" if val and val in spoken else "NOT_ACCESSED",
                        "source": "rule_mapping" if val and val in spoken else "original_annotation",
                    }
                )

            # turn history up to the cutoff: assistant utterance, then the user turn
            for k in range(1, t + 1):
                events.append(
                    {
                        "event_id": f"a{k:02d}",
                        "event_type": "start_goal" if k == 1 else "progress",
                        "step_id": step_of(k),  # None when R2 cannot attribute a stage
                        "person_access": "ACCESSED",
                        "source": "original_annotation",
                    }
                )
                at_cutoff = k == t
                truncated = bool(conv.get(f"assistant_turn_{k}_original"))
                events.append(
                    {
                        "event_id": f"u{k:02d}",
                        "event_type": "interruption" if at_cutoff else "progress",
                        "step_id": None,
                        # R3: the utterance was cut off, so the onset must have been detected
                        "person_access": "ACCESSED" if (at_cutoff and truncated) or not at_cutoff else "UNCERTAIN",
                        "source": "original_annotation" if at_cutoff else "rule_mapping",
                    }
                )
                if at_cutoff:
                    break

            cutoff_id = f"u{t:02d}"
            # R8: content-level recovery test over the in-episode observation window
            delivered = conv.get(f"assistant_turn_{t}_transcript") or ""
            full = conv.get(f"assistant_turn_{t}_original") or delivered
            withheld = toks(full[len(delivered) :]) if len(full) > len(delivered) else set()
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
            # the brief defines censoring as "window not fully covered AND no resume
            # observed": a positive seen inside a short window stays a positive.
            if resume_at is not None:
                resumed, censoring = True, "observed_resume"
            elif len(window) < RESUME_MIN_WINDOW:
                resumed, censoring = None, "censored"
            else:
                resumed, censoring = False, "observed_not_resume"
            resume_step = step_of(resume_at) if censoring == "observed_resume" else None
            tf_rubric = conv.get(f"turn_{t}_tf_rubric")
            revealed = [
                f"bf_hidden_{slug(i.get('key'))}"
                for i in hidden
                if (i.get("value") or "").lower() and (i.get("value") or "").lower() in spoken
            ]
            trace = ["a01", f"a{t:02d}", cutoff_id] + revealed

            episode_sample = {
                    "sample_id": f"{SOURCE_ABBR}_{cid}_{cutoff_id}",
                    "source_dataset": "IHBench",
                    "base_story_id": cid,
                    "goal_id": goal_id,
                    "task_steps": steps,
                    "observed_events": events,
                    "cutoff_event_id": cutoff_id,
                    "state_at_cutoff": {
                        "V": "VALID",  # R4
                        "F": "READY" if tf_rubric else "UNKNOWN",  # R5
                        "A": "ACCESSED",  # R3
                        "B": "UNRESOLVED" if itype in PLAN_CONTESTING else "BELIEVES_VALID",  # R6
                        "C": "SUSPENDED",  # R7
                        "Q": q_of(t),  # R2
                    },
                    "p1_observed_resume": resumed,  # R8; null when censored
                    "p1_resume_step": resume_step,  # R9
                    "p1_censoring_status": censoring,  # R8
                    "evidence_trace": sorted(set(trace)),
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
                                *[f"user_turn_{k}_transcript" for k in range(1, t + 1)],
                                # R8 reads the post-cutoff window to build the label;
                                # those turns are recorded here but never enter
                                # observed_events, so the sample cannot leak them.
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
                advanced = (
                    stage_at.get(t) is not None and att is not None and att > stage_at[t]
                )
                resumed = re_delivered or advanced
                clone = json.loads(json.dumps(episode_sample, ensure_ascii=False))
                clone["base_story_id"] = f"{cid}@baseline"
                clone["sample_id"] = f"{SOURCE_ABBR}_{cid}@baseline_{cutoff_id}"
                clone["p1_observed_resume"] = bool(resumed)
                clone["p1_resume_step"] = (
                    (step_of(t) if re_delivered else step_of(att)) if resumed else None
                )
                clone["p1_censoring_status"] = (
                    "observed_resume" if resumed else "observed_not_resume"
                )
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
    return samples


if __name__ == "__main__":
    sys.exit(0 if build() else 1)
