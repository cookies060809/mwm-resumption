"""InterruptBench -> P1 converter.

Source: github.com/HenryPengZou/InterruptBench (paper arXiv:2604.00892), files
under Eval/interrupt_config/raw/*.json plus Eval/config_files/wa/
test_webarena_lite.json. Only JSON annotations were taken; the repo's images and
environment fixtures were not.

WHAT THE SOURCE ACTUALLY ANNOTATES (and what it does not)
  Annotated per scenario: task_id, the base `intent`, the goal the agent is
  actually given (`transformed_initial_intent`), the ordered interruption
  utterances (`updates`), and for raw/3mixed.json the per-update
  `updates_type`. The task suite additionally annotates `sites`, `start_url`,
  `require_login` and an `eval` oracle.
  NOT annotated, and therefore not emitted here: any step-level decomposition
  of the task (task_steps = []), the injection index (the released
  `interrupt_at_pct` is a percentage of an action sequence that only exists
  after a model run), and any post-interruption behaviour. Consequently every
  InterruptBench sample is `censored` and its `Q` is UNKNOWN. Inventing a step
  list or a resume outcome here would be fabrication, so we do not.

RULES

T1 base_story_id .... "wa_lite_task_{task_id:03d}" from the annotated task_id.
T2 goal_id ........... the goal the agent is executing at the cutoff:
                       transformed_initial_intent for the first update, then
                       transformed_initial_intent with the earlier updates
                       accumulated, exactly as MULTI_INTERRUPT.md prescribes
                       ("accumulating the updates that already happened into
                       intent"). Slugified, so it is a stable id, not prose.
T3 interruption type.. from the annotated `updates_type` when present
                       (raw/3mixed.json) -> source=original_annotation;
                       otherwise from the scenario family in the source file
                       name (1retraction/1update/2modification/2retraction/
                       2update) -> source=rule_mapping. The mapping is
                       family -> {retraction, addition, modification}; it is
                       corroborated by raw/3mixed.json, where the authors' own
                       per-update labels match the same utterance patterns
                       ("ignore/don't worry about X" = retraction, "I only need
                       X" = addition, "I meant X, not Y" = modification), and by
                       the paper's three types addition/revision/retraction.
T4 V .................. CANCELLED when the cutoff update is typed `retraction`
                       (the annotated requirement is withdrawn, so the goal the
                       agent was given is no longer valid as stated); VALID for
                       `addition` and `modification` (the announced goal stands,
                       extended or corrected). Nothing else is annotated about
                       validity.
T5 F .................. READY when the underlying task carries an annotated
                       oracle (eval.eval_types plus reference_answers,
                       reference_url or program_html), i.e. a reachable end
                       state exists in the environment; UNKNOWN otherwise.
T6 A .................. ACCESSED for the interruption events and for the announced
                       goal: the harness injects each `updates[k]` message directly
                       into the agent's observation stream, and the task config
                       (`start_url`, `require_login`, `storage_state`) is part of the
                       agent's own starting context. This is the project's prescribed
                       mapping (task brief §2.4); it claims exposure only, never
                       understanding. The annotated `eval` oracle is the opposite
                       case: it exists in the dataset but is withheld from the agent,
                       so that background fact is NOT_ACCESSED.
T7 B .................. BELIEVES_VALID: the pre-cutoff history contains only the
                       announced goal and the earlier accepted updates, and nothing
                       annotates the agent revising its plan. Belief is derived from
                       the observed history, never copied from V: the 612 retraction
                       samples therefore carry V=CANCELLED with B=BELIEVES_VALID,
                       which is the false-belief contrast P1 is meant to measure.
T8 C .................. by annotated interruption type, as prescribed by the task
                       brief (§2.4): addition -> ACTIVE (the plan keeps running, now
                       with one more requirement); modification/revision ->
                       SUSPENDED (the in-flight plan must be paused to be rewritten);
                       retraction -> ABANDONED (the announced goal is withdrawn and
                       will not be completed as stated).
T9 Q .................. UNKNOWN (T-source has no step annotations).
T10 resume ............ p1_observed_resume=null, p1_resume_step=null,
                       p1_censoring_status="censored" for every sample: the release
                       contains no run record, so no resumption is ever observed
                       here. Writing false instead would present an absence of
                       evidence as evidence of absence.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "raw" / "InterruptBench" / "Eval" / "interrupt_config" / "raw"
TASKS = (
    ROOT / "raw" / "InterruptBench" / "Eval" / "config_files" / "wa" / "test_webarena_lite.json"
)
OUT = ROOT / "processed" / "interruptbench.jsonl"

SOURCE_ABBR = "ib"

# T3: scenario family taken from the source file name.
FAMILY_BY_FILE = {
    "1retraction.json": "retraction",
    "1update.json": "addition",
    "2modification.json": "modification",
    "2retraction.json": "retraction",
    "2update.json": "addition",
    "3mixed.json": None,  # per-update `updates_type` is annotated
}

RETRACT = {"retraction"}  # T4

# T8: prescribed commitment-state mapping over the annotated interruption type.
COMMITMENT_BY_TYPE = {"addition": "ACTIVE", "modification": "SUSPENDED", "retraction": "ABANDONED"}


def slug(s, limit=48):
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").strip().lower()).strip("-")
    return s[:limit] or "unnamed"


def has_oracle(task):
    """T5 predicate: the suite annotates a checkable end state for this task."""
    ev = (task or {}).get("eval") or {}
    if not ev.get("eval_types"):
        return False
    return bool(
        (ev.get("reference_answers") or {}).get("must_include")
        or ev.get("reference_url")
        or ev.get("program_html")
        or (ev.get("reference_answers") or {}).get("exact_match")
    )


def load_tasks():
    if not TASKS.exists():
        return {}
    return {int(t["task_id"]): t for t in json.loads(TASKS.read_text(encoding="utf-8"))}


def build():
    tasks = load_tasks()
    samples = []
    for path in sorted(RAW_DIR.glob("*.json")):
        family = FAMILY_BY_FILE.get(path.name)
        if family is None and path.name not in ("3mixed.json",):
            print(f"  skip unrecognised spec file {path.name}")
            continue
        for item in json.loads(path.read_text(encoding="utf-8")):
            tid = int(item["task_id"])
            base_id = f"wa_lite_task_{tid:03d}"  # T1
            updates = item.get("updates") or []
            utypes = item.get("updates_type") or []
            task_cfg = tasks.get(tid)
            goal_announced = item.get("transformed_initial_intent") or item.get("intent")
            for k, utterance in enumerate(updates, start=1):
                if utypes:
                    itype, type_source = utypes[k - 1], "original_annotation"  # T3
                else:
                    itype, type_source = family, "rule_mapping"  # T3
                accumulated = " ; ".join([goal_announced] + updates[: k - 1])
                goal_id = f"{base_id}:{slug(accumulated, 60)}"  # T2
                # scenario tag keeps event ids unique across the six spec files,
                # so sample_id stays exactly {abbr}_{base_story_id}_{cutoff_event_id}
                tag = path.name[:-5]
                cutoff_id = f"i{k:02d}_{tag}"

                events = [
                    {
                        "event_id": "e01",
                        "event_type": "start_goal",
                        "step_id": None,
                        "person_access": "ACCESSED",
                        "source": "original_annotation",
                    }
                ]
                fields = {"task_id", "intent", "transformed_initial_intent", "updates"}
                if utypes:
                    fields.add("updates_type")
                if task_cfg:
                    events.append(
                        {
                            "event_id": "bf_environment",
                            "event_type": "background_fact",
                            "step_id": None,
                            "person_access": "ACCESSED",
                            "source": "original_annotation",
                        }
                    )
                    fields |= {"sites", "start_url", "require_login", "intent_template"}
                    if has_oracle(task_cfg):
                        events.append(
                            {
                                "event_id": "bf_reference_oracle",
                                "event_type": "background_fact",
                                "step_id": None,
                                # the annotated oracle is withheld from the agent
                                "person_access": "NOT_ACCESSED",
                                "source": "original_annotation",
                            }
                        )
                        fields |= {"eval.eval_types", "eval.reference_answers"}
                for j in range(1, k):
                    events.append(
                        {
                            "event_id": f"i{j:02d}_{tag}",
                            "event_type": "interruption",
                            "step_id": None,
                            "person_access": "ACCESSED",  # T6
                            "source": type_source,
                        }
                    )
                events.append(
                    {
                        "event_id": cutoff_id,
                        "event_type": "interruption",
                        "step_id": None,
                        "person_access": "ACCESSED",  # T6
                        "source": type_source,
                    }
                )

                samples.append(
                    {
                        "sample_id": f"{SOURCE_ABBR}_{base_id}_{cutoff_id}",
                        "source_dataset": "InterruptBench",
                        "base_story_id": base_id,
                        "goal_id": goal_id,
                        "task_steps": [],  # no step annotation in the source
                        "observed_events": events,
                        "cutoff_event_id": cutoff_id,
                        "state_at_cutoff": {
                            "V": "CANCELLED" if itype in RETRACT else "VALID",  # T4
                            "F": "READY" if task_cfg and has_oracle(task_cfg) else "UNKNOWN",  # T5
                            "A": "ACCESSED",  # T6
                            "B": "BELIEVES_VALID",  # T7
                            "C": COMMITMENT_BY_TYPE[itype],  # T8
                            "Q": "UNKNOWN",  # T9
                        },
                        "p1_observed_resume": None,  # T10
                        "p1_resume_step": None,
                        "p1_censoring_status": "censored",  # T10
                        "evidence_trace": sorted(
                            {"e01", cutoff_id}
                            | {f"i{j:02d}_{tag}" for j in range(1, k)}
                            | ({"bf_reference_oracle"} if task_cfg and has_oracle(task_cfg) else {"bf_environment"})
                        ),
                        "original_annotation_ref": {
                            "file": f"Eval/interrupt_config/raw/{path.name}",
                            "fields_used": sorted(fields),
                        },
                    }
                )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="\n") as fh:
        for s in samples:
            fh.write(json.dumps(s, ensure_ascii=False) + "\n")
    print(f"wrote {len(samples)} P1 samples -> {OUT.relative_to(ROOT)}")
    return samples


if __name__ == "__main__":
    sys.exit(0 if build() else 1)
