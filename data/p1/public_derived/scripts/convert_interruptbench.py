"""InterruptBench -> P1 converter (schema p1-0.2).

Source: github.com/HenryPengZou/InterruptBench (paper arXiv:2604.00892), files
under Eval/interrupt_config/raw/*.json plus Eval/config_files/wa/
test_webarena_lite.json. Only JSON annotations were taken; the repo's images and
environment fixtures were not. 34 blobs re-fetched and sha-verified against the
recorded manifest by scripts/fetch_github_paths.py.

WHAT THE SOURCE ACTUALLY ANNOTATES (and what it does not)
  Annotated per scenario: task_id, the base `intent`, the goal the agent is
  actually given (`transformed_initial_intent`), the ordered interruption
  utterances (`updates`), and for raw/3mixed.json the per-update
  `updates_type`. The task suite additionally annotates `sites`, `start_url`,
  `require_login`, `storage_state` and an `eval` oracle.
  NOT annotated, and therefore not emitted here: any step-level decomposition of
  the task (task_steps = []), the injection index (the released `interrupt_at_pct`
  is a percentage of an action sequence that only exists after a model run), and
  any post-interruption behaviour. There is no execution log at all, so p1-0.2
  masks every actor-side factor: B, C, F and A were inferred in p1-0.1 from the
  interruption type or from the existence of a grader, and Q was already UNKNOWN.
  Only V is supported, and only as a statement about the GOAL SPECIFICATION.

  This is why subject_type is `software_agent_spec`: these rows describe what a
  task suite asks an agent to do, not what any agent or person did.

RULES

T1 base_story_id .... "wa_lite_task_{task_id:03d}" from the annotated task_id.
T2 goal .............. the goal the agent holds at the cutoff: transformed_initial_intent
                      with the earlier updates accumulated, exactly as MULTI_INTERRUPT.md
                      prescribes. Both the slug id and the plain text are delivered - the
                      text is what the input was missing in p1-0.1.
T3 interruption type.. from the annotated `updates_type` when present (3mixed.json) ->
                      source=original_annotation; otherwise from the scenario family in
                      the source file name -> source=rule_mapping.
T4 V ................. CANCELLED when the cutoff update is typed `retraction` (the
                      annotated requirement is withdrawn, so the goal as given is no
                      longer valid); VALID for addition/modification. About the spec,
                      never about an actor's belief.
T5 F ............... MASKED. p1-0.1 gave READY whenever the task carried an `eval`
                      oracle; a checkable end state does not show that resources,
                      permissions or dependencies were available at the cutoff.
T6 A ............... MASKED. The harness prescribes injecting `updates[k]` into the
                      observation stream, but with no run record nothing annotates
                      that this actor received it. Event-level `person_access` still
                      records the prescribed delivery, and the withheld oracle stays
                      NOT_ACCESSED.
T7 B ............... MASKED (p1-0.1: BELIEVES_VALID on all 1,815 rows). Without an
                      execution log the agent's belief is unknown, and a user
                      retracting a requirement is not the agent abandoning a goal - the
                      612 retraction rows are therefore not a verified false-belief
                      contrast either.
T8 C ............... MASKED (p1-0.1 mapped addition->ACTIVE, modification->SUSPENDED,
                      retraction->ABANDONED). That mapping read the user's act as the
                      agent's commitment state.
T9 Q ............... MASKED (no step annotation in the source at all).
T10 resume ........... null / censored / resume_loss_mask=0 /
                      eligible_for_resume_eval=false for every sample: the release has
                      no run record, so no resumption is ever observed. Writing false
                      instead would present an absence of evidence as evidence of
                      absence.
T11 event ids ...... a neutral spec ordinal `i##_s#` replaces p1-0.1's
                      `i01_1retraction`. The family name inside an event id is a
                      feature: it encodes the label (retraction -> V=CANCELLED), so it
                      is kept in label_evidence, which is supervision-only.
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
    W_NO_BELIEVE_EVIDENCE,
    W_NO_COMMITMENT_EVIDENCE,
    W_NO_FEASIBILITY_EVIDENCE,
    W_NO_RUN_RECORD,
    W_NOT_ANNOTATED,
)

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
# T11: ordinal per spec file, so no event id carries the family name.
SPEC_ORDINAL = {name: i + 1 for i, name in enumerate(sorted(FAMILY_BY_FILE))}

RETRACT = {"retraction"}  # T4

# The p1-0.1 T8 mapping, kept only to record what was withdrawn.
P1_01_COMMITMENT = {"addition": "ACTIVE", "modification": "SUSPENDED", "retraction": "ABANDONED"}


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
    if not RAW_DIR.exists():
        raise SystemExit(f"missing {RAW_DIR}: run scripts/fetch_github_paths.py first")
    tasks = load_tasks()
    samples = []
    for path in sorted(RAW_DIR.glob("*.json")):
        family = FAMILY_BY_FILE.get(path.name)
        if family is None and path.name not in ("3mixed.json",):
            print(f"  skip unrecognised spec file {path.name}")
            continue
        ordinal = SPEC_ORDINAL[path.name]
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
                cutoff_id = f"i{k:02d}_s{ordinal:02d}"  # T11

                events = [{
                    "event_id": "e01",
                    "event_type": "start_goal",
                    "step_id": None,
                    "person_access": "ACCESSED",
                    "source": "original_annotation",
                    "actor": "user",
                    "text": goal_announced,
                    "position": position("spec_order", 0),
                }]
                fields = {"task_id", "intent", "transformed_initial_intent", "updates"}
                oracle = None
                if task_cfg:
                    env = " ; ".join(
                        f"{key}={task_cfg.get(key)}"
                        for key in ("sites", "start_url", "require_login", "storage_state")
                        if task_cfg.get(key) is not None
                    )
                    events.append({
                        "event_id": "bf_environment",
                        "event_type": "background_fact",
                        "step_id": None,
                        "person_access": "ACCESSED",
                        "source": "original_annotation",
                        "actor": "environment",
                        "text": env,
                        "position": None,
                    })
                    fields |= {"sites", "start_url", "require_login", "intent_template"}
                    if has_oracle(task_cfg):
                        # the annotated oracle is withheld from the agent, so its content
                        # is deliberately not part of the event text
                        events.append({
                            "event_id": "bf_reference_oracle",
                            "event_type": "background_fact",
                            "step_id": None,
                            "person_access": "NOT_ACCESSED",
                            "source": "original_annotation",
                            "actor": "evaluator",
                            "text": None,
                            "position": None,
                        })
                        fields |= {"eval.eval_types", "eval.reference_answers"}
                        oracle = task_cfg.get("eval")
                for j in range(1, k):
                    events.append({
                        "event_id": f"i{j:02d}_s{ordinal:02d}",
                        "event_type": "interruption",
                        "step_id": None,
                        "person_access": "ACCESSED",  # T6: prescribed delivery
                        "source": type_source,
                        "actor": "user",
                        "text": updates[j - 1],
                        "position": position("spec_order", j),
                    })
                events.append({
                    "event_id": cutoff_id,
                    "event_type": "interruption",
                    "step_id": None,
                    "person_access": "ACCESSED",
                    "source": type_source,
                    "actor": "user",
                    "text": utterance,
                    "position": position("spec_order", k),
                })

                s = State()
                s.assert_from("V", "CANCELLED" if itype in RETRACT else "VALID",
                              "annotated_interruption_type",
                              f"the cutoff update is typed `{itype}`: as a goal specification the announced requirement is "
                              f"{'withdrawn' if itype in RETRACT else 'still in force'} - this says nothing about any actor's belief (T4)")
                s.withhold("F", "READY" if (task_cfg and has_oracle(task_cfg)) else UNKNOWN,
                           W_NO_FEASIBILITY_EVIDENCE, "T5")
                s.withhold("A", "ACCESSED", W_NO_RUN_RECORD, "T6")
                s.withhold("B", "BELIEVES_VALID", W_NO_BELIEVE_EVIDENCE, "T7")
                s.withhold("C", P1_01_COMMITMENT.get(itype, "ACTIVE"), W_NO_COMMITMENT_EVIDENCE, "T8")
                s.withhold("Q", UNKNOWN, W_NOT_ANNOTATED, "T9")
                st = s.build()

                samples.append({
                    "schema_version": "p1-0.2",
                    "sample_id": f"{SOURCE_ABBR}_{base_id}_{cutoff_id}",
                    "source_dataset": "InterruptBench",
                    "base_story_id": base_id,
                    "goal_id": goal_id,
                    "goal_text": goal_announced,
                    "subject_type": "software_agent_spec",
                    "actor_id": f"{base_id}:webarena_agent",
                    "split_group_id": base_id,  # every spec file and update stays in one group
                    "split": split_for("InterruptBench", base_id),
                    "task_steps": [],  # no step annotation in the source
                    "observed_events": events,
                    "cutoff_event_id": cutoff_id,
                    "cutoff_kind": "goal_spec_update",
                    "observation_horizon": horizon(
                        "not_observable", None, None,
                        "the release ships task-update specs only: no agent run, so no outcome can be observed",
                    ),
                    "outcome_time": None,
                    "eligible_for_resume_eval": False,
                    "state_at_cutoff": st["state"],
                    "state_loss_mask": st["mask"],
                    "label_origin": {**st["origin"], "resume": None, "resume_step": None},
                    "state_withdrawn": st["withdrawn"],
                    "objective_progress": objective_progress(
                        None, "annotated_interruption_order",
                        f"update #{k} of spec ordinal s{ordinal:02d}; no step decomposition is annotated",
                    ),
                    "p1_observed_resume": None,  # T10
                    "resume_loss_mask": 0,
                    "p1_resume_step": None,
                    "step_loss_mask": 0,
                    "p1_censoring_status": "censored",  # T10
                    "evidence_trace": sorted(
                        {"e01", cutoff_id}
                        | {f"i{j:02d}_s{ordinal:02d}" for j in range(1, k)}
                        | ({"bf_reference_oracle"} if oracle else {"bf_environment"})
                    ),
                    "label_evidence": {
                        "source_spec_family": family or "mixed",
                        "spec_ordinal": ordinal,
                        "annotated_updates_type": itype,
                        "type_provenance": type_source,
                        "accumulated_goal_text": accumulated,
                        "intent_template": (task_cfg or {}).get("intent_template"),
                        "eval_oracle": oracle,
                        "interrupt_at_pct": (task_cfg or {}).get("interrupt_at_pct"),
                        "note": "Supervision-only. The spec family is derivable from V and must not be used as an input feature.",
                    },
                    "original_annotation_ref": {
                        "file": f"Eval/interrupt_config/raw/{path.name}",
                        "fields_used": sorted(fields),
                    },
                })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="\n") as fh:
        for s in samples:
            fh.write(json.dumps(s, ensure_ascii=False) + "\n")
    print(f"wrote {len(samples)} P1 samples -> {OUT.relative_to(ROOT)}")
    for f in ("V", "F", "A", "B", "C", "Q"):
        sup = sum(s["state_loss_mask"][f] for s in samples)
        c = Counter(s["state_at_cutoff"][f] for s in samples if s["state_loss_mask"][f])
        print(f"  {f}: supervised={sup}/{len(samples)}  values={dict(c)}")
    print("  censoring:", dict(Counter(s["p1_censoring_status"] for s in samples)))
    print("  resume supervised:", sum(s["resume_loss_mask"] for s in samples))
    print("  splits:", dict(Counter(s["split"] for s in samples)))
    return samples


if __name__ == "__main__":
    sys.exit(0 if build() else 1)
