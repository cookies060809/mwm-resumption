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
| IHBench | 659 | 59 | 138 | 199 (23.2%) |
| REBOOT | 129 | 63 | 0 | 63 (32.8%) |

Observed recoveries come from two sources with different evidence strength: IHBench derives them from the released episode text (rule R8 - re-delivery of the withheld step content or a stage advance), and REBOOT reads them straight out of the annotated `failure.recovery_started_at_frame` (rule B12). `observed_not_resume` comes only from IHBench, where a covered window shows neither test passing. Every InterruptBench sample is `censored`: the release ships no run record, so absence of recovery there is not observable and `p1_observed_resume` is null rather than false.

## state_at_cutoff distribution

### V

| source_dataset | VALID | CANCELLED | FULFILLED |
|---|---|---|---|
| InterruptBench | 1203 | 612 | 0 |
| IHBench | 856 | 0 | 0 |
| REBOOT | 177 | 0 | 15 |

### F

| source_dataset | READY | UNKNOWN | BLOCKED |
|---|---|---|---|
| InterruptBench | 1309 | 506 | 0 |
| IHBench | 856 | 0 | 0 |
| REBOOT | 134 | 1 | 57 |

### A

| source_dataset | ACCESSED | NOT_ACCESSED |
|---|---|---|
| InterruptBench | 1815 | 0 |
| IHBench | 856 | 0 |
| REBOOT | 132 | 60 |

### B

| source_dataset | BELIEVES_VALID | UNRESOLVED | BELIEVES_INVALID |
|---|---|---|---|
| InterruptBench | 1815 | 0 | 0 |
| IHBench | 450 | 406 | 0 |
| REBOOT | 191 | 0 | 1 |

### C

| source_dataset | SUSPENDED | ACTIVE | ABANDONED | COMPLETED |
|---|---|---|---|---|
| InterruptBench | 650 | 553 | 612 | 0 |
| IHBench | 856 | 0 | 0 | 0 |
| REBOOT | 60 | 117 | 0 | 15 |

### Q

| source_dataset | UNKNOWN | phase_1_engage-pick | phase_3_align-place | phase_2_transport | stage_00_open-and-set-context | stage_00_initiate-and-set-context | stage_04_collect-profile-preferences | stage_03_quote-pricing-and-terms |
|---|---|---|---|---|---|---|---|---|
| InterruptBench | 1815 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| IHBench | 4 | 0 | 0 | 0 | 24 | 24 | 22 | 22 |
| REBOOT | 2 | 72 | 55 | 36 | 0 | 0 | 0 | 0 |

UNKNOWN share over all samples: V 0.0%, F 17.7%, A 0.0%, B 0.0%, C 0.0%, Q 63.6%

## Event provenance

| dimension | values |
|---|---|
| event source | original_annotation=38166, rule_mapping=8481 |
| event_type | background_fact=27702, progress=12204, interruption=3793, start_goal=2863, resume=70, completion=15 |
| event person_access | ACCESSED=33904, NOT_ACCESSED=12743 |
| evidence_trace length | min 1, max 9, mean 3.64 |
| observed_events length | min 1, max 76, mean 16.29 |

`llm_inferred` events: 0 — no label in this delivery depends on model inference.

## Enum tiers not reached by these sources

Reached by at least one sample: V 3/4, F 3/3, A 2/3, B 3/4, C 4/5, Q 136 distinct step ids + 2 sentinels, censoring 3/3, event_type 6/6 (resume=70, completion=15), observed_not_resume=138.

| tier | count | why |
|---|---:|---|
| V=UNKNOWN | 0 | every source annotates enough to decide validity at the cutoff |
| A=UNCERTAIN | 0 | unused fallback: access is either evidenced (barge-in truncation, injected message) or explicitly absent (pre-failure cutoff) |
| B=UNKNOWN | 0 | no source annotation supports this value |
| C=UNKNOWN | 0 | unused fallback |

Thin tiers worth flagging: `B=BELIEVES_INVALID` comes from a single REBOOT row whose `failure_mode='freeze'` annotates the robot ceasing to act on a goal the same annotation marks completable (rule B15) - treat it as a proof of the mapping, not as a statistically usable class. `V=FULFILLED`/`C=COMPLETED`/`Q=NOT_APPLICABLE` (15 each) come only from REBOOT episodes whose description asserts completion. `observed_not_resume` (138) comes only from IHBench.

