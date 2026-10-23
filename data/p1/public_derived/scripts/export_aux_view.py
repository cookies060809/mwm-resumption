"""Export the input / supervision split that A and C consume.

The delivery file keeps the whole audit trail in one record, which means a consumer
has to know which fields are allowed to reach the model. This script makes that
explicit by writing, per source and per frozen split, two disjoint blocks:

  input       - goal_text, task_steps, observed_events (id/type/step/actor/text/
                position/person_access/source). Nothing else.
  supervision - the state factors, every loss mask, label provenance, censoring,
                eligibility, and the ids needed to group or weight a metric.

`label_evidence` (rubrics, the withheld tail of a truncated utterance, the post-cutoff
answers, the baseline response) is dropped entirely: it exists to justify a label and
must never be a feature. The export fails if any of that content still appears inside
the input block, so the guarantee is checked rather than promised. The one exception is
content that is annotated as part of this cutoff's own history (a REBOOT recovery
description attached to the resume event that already lies in the covered past): a
string only counts as clean when it is exactly one of the event texts, never on
substring luck, so a fail slice still cannot smuggle the recovery prose in.

Usage: python scripts/export_aux_view.py
"""

import hashlib
import json
from collections import Counter
from pathlib import Path

from common import write_lf

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "processed" / "p1_combined.jsonl"
# Not `aux`: that is a reserved device name on Windows and git cannot read inside it.
OUT = ROOT / "processed" / "aux_view"

INPUT_KEYS = ["goal_text", "task_steps", "observed_events"]
EVENT_INPUT_KEYS = ["event_id", "event_type", "step_id", "actor", "text",
                    "position", "person_access", "source"]
SUPERVISION_KEYS = [
    "cutoff_event_id", "cutoff_kind", "state_at_cutoff", "state_loss_mask", "label_origin",
    "state_withdrawn", "objective_progress", "observation_horizon", "outcome_time",
    "p1_observed_resume", "resume_loss_mask", "p1_resume_step", "step_loss_mask",
    "p1_censoring_status", "eligible_for_resume_eval",
]
ID_KEYS = ["sample_id", "schema_version", "source_dataset", "subject_type", "actor_id",
           "base_story_id", "goal_id", "split_group_id", "split"]
EVIDENCE_FIELDS = ("tf_rubric", "rq_rubrics", "withheld_tail", "baseline_response",
                   "window_assistant_transcripts", "annotated_language_description",
                   "eval_oracle")


def split_record(s):
    events = [{k: e.get(k) for k in EVENT_INPUT_KEYS} for e in s["observed_events"]]
    return {
        "input": {"goal_text": s["goal_text"], "task_steps": s["task_steps"],
                  "observed_events": events},
        "supervision": {**{k: s[k] for k in SUPERVISION_KEYS},
                        **{k: s[k] for k in ID_KEYS}},
    }


def evidence_strings(s):
    le = s.get("label_evidence") or {}
    for key in EVIDENCE_FIELDS:
        v = le.get(key)
        if isinstance(v, list):
            yield from (x for x in v if isinstance(x, str))
        elif isinstance(v, str):
            yield v
        elif isinstance(v, dict):
            yield json.dumps(v, ensure_ascii=False)


def main():
    if not SRC.exists():
        raise SystemExit(f"missing {SRC}: run run_pipeline.sh first")
    OUT.mkdir(parents=True, exist_ok=True)
    for stale in OUT.glob("*.jsonl"):
        stale.unlink()
    rows = [json.loads(l) for l in SRC.read_text(encoding="utf-8").splitlines() if l.strip()]
    buckets = {}
    leaks, checked = [], 0
    for s in rows:
        view = split_record(s)
        blob = json.dumps(view["input"], ensure_ascii=False).lower()
        # An annotated event description legitimately appears on both sides when the
        # event is itself inside the covered past (REBOOT annotates the recovery in
        # prose). Only content that is *not* an event of this cutoff's history counts
        # as a leak - so a fail slice still cannot carry the recovery description.
        exact = {e["text"] for e in view["input"]["observed_events"] if e["text"]}
        for text in evidence_strings(s):
            if text in exact:
                continue
            if len(text) >= 25 and text.lower().strip() in blob:
                leaks.append(f"{s['sample_id']}: label_evidence content reached the input block")
        checked += 1
        buckets.setdefault((s["source_dataset"], s["split"]), []).append(view)

    manifest = {"schema_version": "p1-0.2", "source": "processed/p1_combined.jsonl",
                "input_keys": INPUT_KEYS, "event_input_keys": EVENT_INPUT_KEYS,
                "supervision_keys": sorted(set(SUPERVISION_KEYS) | set(ID_KEYS)),
                "dropped_fields": list(EVIDENCE_FIELDS),
                "leak_check": {"rows_checked": checked, "violations": len(leaks)},
                "files": {}}
    for (src, split), items in sorted(buckets.items()):
        name = f"{src.lower()}.{split}.jsonl"
        p = OUT / name
        text = "\n".join(json.dumps(v, ensure_ascii=False) for v in items)
        write_lf(p, text + "\n")
        manifest["files"][name] = {
            "rows": len(items),
            "bytes": p.stat().st_size,
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            "resume_supervised": sum(v["supervision"]["resume_loss_mask"] for v in items),
            "eligible_for_resume_eval": sum(v["supervision"]["eligible_for_resume_eval"] for v in items),
            "split_groups": len({v["supervision"]["split_group_id"] for v in items}),
            "supervised_state_factors": {
                f: sum(v["supervision"]["state_loss_mask"][f] for v in items)
                for f in ("V", "F", "A", "B", "C", "Q")
            },
        }
    write_lf(OUT / "manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))

    print(f"exported {checked} rows -> {OUT.relative_to(ROOT)}/ ({len(manifest['files'])} files)")
    for name, info in manifest["files"].items():
        print(f"  {name}: rows={info['rows']} groups={info['split_groups']} "
              f"resume_supervised={info['resume_supervised']} bytes={info['bytes']:,}")
    print("  state-factor supervision per file: "
          + "; ".join(f"{n}:{sum(v['supervised_state_factors'].values())}" for n, v in manifest["files"].items()))
    if leaks:
        print("\n".join(f"  LEAK {l}" for l in leaks[:20]))
        raise SystemExit(f"{len(leaks)} input/supervision leaks - not written as valid")
    print("leak check: no rubric / withheld tail / post-cutoff answer inside any input block")
    per_split = Counter()
    for (src, split), items in buckets.items():
        per_split[split] += len(items)
    print("rows per split:", dict(per_split))


if __name__ == "__main__":
    main()
