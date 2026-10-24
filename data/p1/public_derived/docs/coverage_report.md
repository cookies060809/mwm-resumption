# P1 coverage report (ECR-MWM)

Delivered set: `processed/p1_combined.jsonl` — **2863 samples** from **3 source datasets** (requirement: >=2).

## Sample counts

| source_dataset | samples | base_story_ids | goal_ids | samples with non-empty task_steps |
|---|---:|---:|---:|---:|
| InterruptBench | 1815 | 165 | 1031 | 0 |
| IHBench | 856 | 90 | 29 | 856 |
| REBOOT | 192 | 60 | 1 | 192 |

## Censoring and resume labels

| source_dataset | observed_resume | censored | observed_not_resume | p1_resume_step = null |
|---|---:|---:|---:|---:|
| InterruptBench | 0 | 1815 | 0 | 1815 (100.0%) |
| IHBench | 659 | 71 | 126 | 198 (23.1%) |
| REBOOT | 127 | 65 | 0 | 65 (33.9%) |
| **total** | **786** | **1951** | **126** | 2078 (72.6%) |

Observed recoveries come from two sources with different evidence strength: IHBench derives them from the released episode text (rule R8 - re-delivery of the withheld step content or a stage advance), and REBOOT reads them straight out of the annotated `failure.recovery_started_at_frame` (rule B12). `observed_not_resume` comes only from IHBench, where a covered window shows neither test passing. Every InterruptBench sample is `censored`: the release ships no run record, so absence of recovery there is not observable and `p1_observed_resume` is null rather than false.

## state_at_cutoff distribution

### V

| source_dataset | VALID | CANCELLED | FULFILLED |
|---|---|---|---|
| InterruptBench | 1203 | 612 | 0 |
| IHBench | 856 | 0 | 0 |
| REBOOT | 177 | 0 | 15 |

### F

| source_dataset | UNKNOWN | READY |
|---|---|---|
| InterruptBench | 1815 | 0 |
| IHBench | 856 | 0 |
| REBOOT | 135 | 57 |

### A

| source_dataset | UNKNOWN | ACCESSED |
|---|---|---|
| InterruptBench | 1815 | 0 |
| IHBench | 856 | 0 |
| REBOOT | 120 | 72 |

### B

| source_dataset | UNKNOWN | BELIEVES_VALID |
|---|---|---|
| InterruptBench | 1815 | 0 |
| IHBench | 856 | 0 |
| REBOOT | 120 | 72 |

### C

| source_dataset | UNKNOWN | SUSPENDED | ACTIVE | COMPLETED |
|---|---|---|---|---|
| InterruptBench | 1815 | 0 | 0 | 0 |
| IHBench | 0 | 856 | 0 | 0 |
| REBOOT | 60 | 0 | 117 | 15 |

### Q

| source_dataset | UNKNOWN | NOT_APPLICABLE |
|---|---|---|
| InterruptBench | 1815 | 0 |
| IHBench | 856 | 0 |
| REBOOT | 177 | 15 |

UNKNOWN share over all samples: V 0.0%, F 98.0%, A 97.5%, B 97.5%, C 65.5%, Q 99.5%

## Event provenance

| dimension | values |
|---|---|
| event source | original_annotation=38166, rule_mapping=8481 |
| event_type | background_fact=27702, progress=12204, interruption=3793, start_goal=2863, resume=70, completion=15 |
| event person_access | ACCESSED=33904, NOT_ACCESSED=12743 |
| evidence_trace length | min 1, max 9, mean 3.64 |
| observed_events length | min 1, max 76, mean 16.29 |

`llm_inferred` events: 0 — no label in this delivery depends on model inference.

## Withdrawn rule-mapped claims (state_withdrawn)

| factor | withdrawn rows | rules | example reason |
|---|---:|---|---|
| Q | 2848 | T9 x1815, R2/R8 x856, B11 x177 | the source annotates no step decomposition for this actor |
| F | 2806 | T5 x1815, R5 x856, B7 x135 | a scoring oracle or a rubric proves a checkable end state exists, not that resources/permissions were ready at the cutoff |
| A | 2791 | T6 x1815, R3 x856, B8 x120 | the release ships a task specification with no execution log, so nothing records that this actor received or acted on the injected message |
| B | 2791 | T7 x1815, R6 x856, B9 x120 | no annotation reports the actor's belief; the previous value was derived from the interruption type or from a later recovery |
| C | 1875 | T8 x1815, B10 x60 | no annotation reports the actor's commitment state; withdrawing a requirement is the user's act, not the agent's abandonment |
| p1_observed_resume | 2 | B12 x2 | the label was hardcoded without a resume event in the covered past |

13113 withdrawn claims across 2863 rows. The claimed value is kept in `state_withdrawn.<factor>.claimed` for audit; the live `state_at_cutoff` field is `UNKNOWN`. Never treat a withdrawn value as a gold label or relabel it back.

## Enum tiers not reached by these sources

Reached by at least one sample: V 3/4, F 2/3, A 2/4, B 2/4, C 4/5, Q 0 distinct step ids + 2 sentinels, censoring 3/3, event_type 6/6 (resume=70, completion=15), observed_not_resume=126.

| tier | count | why |
|---|---:|---|
| V=UNKNOWN | 0 | every source annotates enough to decide validity at the cutoff |
| F=BLOCKED | 0 | REBOOT BLOCKED rule withdrawn (B7) in the 2026-10-23 revision |
| A=NOT_ACCESSED | 0 | REBOOT NOT_ACCESSED rule withdrawn (B8) in the 2026-10-23 revision |
| A=UNCERTAIN | 0 | unused fallback: access is either evidenced or explicitly absent |
| B=BELIEVES_INVALID | 0 | withdrawn with the rest of REBOOT's B values (B9) |
| B=UNRESOLVED | 0 | belief rules withdrawn (R6/B9) in the 2026-10-23 revision |
| C=ABANDONED | 0 | InterruptBench commitment mapping withdrawn (T8); a cancellation is the user's act |

Thin tiers (n=1, prove the mapping only, not a usable class): none.
`V=FULFILLED`/`C=COMPLETED`/`Q=NOT_APPLICABLE` (15 each) come only from REBOOT episodes whose description asserts completion. `observed_not_resume` (126) comes only from IHBench.

