# Standalone P0 v0.3 (254 records)

Source of truth: ../p0_samples.json. Record schema remains p0-record/v0.2.0.

Mapping notes (B -> C), protocol c-evaluation-draft-1
----------------------------------------------------
* HH:MM -> same-day integer minutes for both `time` and `cutoff`; P0 has no date,
  so no cross-day or late-arrival evidence can be represented.
* task_dependencies{before, after} -> task_graph.edges.
* person_access -> person_access_evidence.status; person_comprehension
  UNDERSTOOD/MISUNDERSTOOD/NOT_UNDERSTOOD -> understood true/false/false;
  anything else -> null (unknown, not false).
* person_available_semantics.kind/value/interpretation -> semantic.kind/value/interpretation.
* person_id = target_person = one synthetic person per family; task_family is the
  task blueprint, and the split is blueprint-disjoint so task_family never
  crosses splits. These are identifiers for leakage audits, not real people.
* purpose = "scripted_p0" (never "synthetic_integration_fixture").
* resume_label: indeterminate (future-leak) -> "unknown"; resume_within_horizon
  true -> "resume" with resume_step; otherwise "not_resume" with null step.
  The nested first step of nested_interruption pairs is dropped here because
  C's gold schema only accepts target-task steps as resume_step.
* window_complete is true by construction: P0 windows are scripted, not observed.
* dataset_layer = "P0" for every record; never mix with P1 or C's fixtures.
* Not representable in C's protocol: state_evidence_by_factor granularity is kept,
  but p0_design/notes/annotation and the `mechanism` key stay behind (mechanism is
  carried in gold.pair_factor instead).

The C boolean `understood` merges MISUNDERSTOOD and NOT_UNDERSTOOD; use raw records for the full U distinction. No probability calibration is fitted.
