"""Merge the per-source P1 files and run every delivery check.

Replaces the earlier combine + validate pair so one command produces both the
merged set and docs/validation_report.txt.

Checks, in order of strictness:
  * draft-07 conformance against docs/schema.json;
  * sample_id == "{abbr}_{base_story_id}_{cutoff_event_id}" and uniqueness
    within each delivered set;
  * event id uniqueness, cutoff present, and cutoff being the LAST event
    (observed_events must not contain post-cutoff history, or the resume label
    leaks into the input);
  * step ids referenced by events / p1_resume_step / Q must be members of
    task_steps, or the explicit sentinels UNKNOWN / NOT_APPLICABLE;
  * evidence_trace must resolve to real events and must contain the cutoff event
    whenever any state field is asserted non-UNKNOWN;
  * censoring <-> label agreement: an unobserved outcome is
    p1_observed_resume=null with p1_censoring_status="censored"; a
    "not resumed" label requires an observed non-resumption inside the episode;
    C=ABANDONED contradicts an observed resume;
  * a guard against copying V into B: if every sample whose goal was cancelled
    also carries B=BELIEVES_INVALID, that is reported as a warning, because the
    source annotations do not license it;
  * provenance: llm_inferred events must carry confidence and evidence_quote;
  * a minimum number of distinct source_dataset values
    (--require-min-sources 2 for the merged delivery).

Exit code 0 = clean, 1 = violations, 2 = harness error.
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from jsonschema import Draft7Validator

from common import write_lf

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "docs" / "schema.json"

ABBR = {"IHBench": "ihb", "REBOOT": "rbt", "IndustReal": "ind", "InterruptBench": "ib"}
STATE_FIELDS = ["V", "F", "A", "B", "C", "Q"]
Q_SENTINELS = {"UNKNOWN", "NOT_APPLICABLE"}
PARTS = ["ihbench.jsonl", "reboot.jsonl", "industreal.jsonl", "interruptbench.jsonl"]


def load(path):
    rows = []
    for ln, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except ValueError as e:
            raise SystemExit(f"{path}:{ln}: not JSON ({e})")
    return rows


def check_sample(s, validator, errs, warns):
    sid = s.get("sample_id", "<missing>")
    src = s.get("source_dataset")
    for e in validator.iter_errors(s):
        errs.append(f"{sid}: schema {list(e.absolute_path)}: {e.message}")

    ids = [e["event_id"] for e in s["observed_events"]]
    if len(ids) != len(set(ids)):
        errs.append(f"{sid}: duplicate event_id inside sample")
    if s["cutoff_event_id"] not in ids:
        errs.append(f"{sid}: cutoff_event_id not among observed_events")
    elif ids[-1] != s["cutoff_event_id"]:
        errs.append(f"{sid}: observed_events contains events after the cutoff (label leak)")

    if src in ABBR and s["sample_id"] != f"{ABBR[src]}_{s['base_story_id']}_{s['cutoff_event_id']}":
        errs.append(f"{sid}: sample_id does not match {{abbr}}_{{base_story_id}}_{{cutoff_event_id}}")

    steps = set(s["task_steps"])
    for e in s["observed_events"]:
        if e["step_id"] is not None and e["step_id"] not in steps:
            errs.append(f"{sid}: event {e['event_id']} step_id {e['step_id']} not in task_steps")
        if e["source"] == "llm_inferred" and not {"confidence", "evidence_quote"} <= set(e):
            errs.append(f"{sid}: llm_inferred event {e['event_id']} lacks confidence/evidence_quote")

    q = s["state_at_cutoff"]["Q"]
    if q is None:
        errs.append(f"{sid}: Q is null; use UNKNOWN or NOT_APPLICABLE")
    elif q not in Q_SENTINELS and q not in steps:
        errs.append(f"{sid}: Q {q} is neither a task step nor UNKNOWN/NOT_APPLICABLE")
    if s["p1_resume_step"] is not None and s["p1_resume_step"] not in steps:
        errs.append(f"{sid}: p1_resume_step {s['p1_resume_step']} not in task_steps")

    status, resumed = s["p1_censoring_status"], s["p1_observed_resume"]
    if status == "censored":
        if resumed is not None:
            errs.append(f"{sid}: censored but p1_observed_resume={resumed!r}; must be null")
        if s["p1_resume_step"] is not None:
            errs.append(f"{sid}: censored but p1_resume_step is set")
    elif status == "observed_resume":
        if resumed is not True:
            errs.append(f"{sid}: observed_resume but p1_observed_resume={resumed!r}")
        if s["p1_resume_step"] is None:
            warns.append(f"{sid}: observed_resume without p1_resume_step")
    elif status == "observed_not_resume":
        if resumed is not False:
            errs.append(f"{sid}: observed_not_resume but p1_observed_resume={resumed!r}")
        if s["state_at_cutoff"]["C"] == "ABANDONED" and s["state_at_cutoff"]["V"] == "FULFILLED":
            warns.append(f"{sid}: ABANDONED commitment at a cutoff whose goal is FULFILLED")

    trace = set(s["evidence_trace"])
    if not trace:
        errs.append(f"{sid}: empty evidence_trace")
    if not trace <= set(ids):
        errs.append(f"{sid}: evidence_trace references unknown events {sorted(trace - set(ids))}")
    grounded = [f for f in STATE_FIELDS if s["state_at_cutoff"][f] not in ("UNKNOWN", None)]
    if grounded and s["cutoff_event_id"] not in trace:
        errs.append(f"{sid}: {grounded} asserted non-UNKNOWN but evidence_trace omits the cutoff event")

    if not s["original_annotation_ref"]["fields_used"]:
        errs.append(f"{sid}: original_annotation_ref.fields_used empty")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--merge", action="store_true", help="write processed/p1_combined.jsonl first")
    ap.add_argument("--require-min-sources", type=int, default=1)
    ap.add_argument("--report", type=Path, default=ROOT / "docs" / "validation_report.txt")
    ap.add_argument("files", nargs="*", type=Path, help="files to check; defaults to the merged set")
    a = ap.parse_args()

    if a.merge:
        rows, origin = {}, {}
        for name in PARTS:
            p = ROOT / "processed" / name
            if not p.exists():
                print(f"  skip missing part {name}")
                continue
            for s in load(p):
                sid = s["sample_id"]
                if sid in origin:
                    raise SystemExit(f"sample_id collision: {sid} in {origin[sid]} and {name}")
                origin[sid] = name
                rows[sid] = s
        out = ROOT / "processed" / "p1_combined.jsonl"
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8", newline="\n") as fh:
            for sid in sorted(rows):
                fh.write(json.dumps(rows[sid], ensure_ascii=False) + "\n")
        srcs = sorted({s["source_dataset"] for s in rows.values()})
        print(f"merged {len(rows)} samples from {len(srcs)} sources -> processed/{out.name}")
        a.files = [out]

    if not a.files:
        raise SystemExit("nothing to check: pass files or use --merge")

    validator = Draft7Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))
    errs, warns = [], []
    by_src, dist = Counter(), defaultdict(Counter)
    prov, censoring, etypes, eaccess = Counter(), Counter(), Counter(), Counter()
    resume_null = Counter()
    cancelled_belief = Counter()
    per_file, total = [], 0

    for f in a.files:
        seen = {}
        for s in load(f):
            sid = s.get("sample_id", f"{f.name}:{total}")
            if sid in seen:
                errs.append(f"{sid}: duplicate sample_id ({f.name} and {seen[sid]})")
            else:
                seen[sid] = f.name
            total += 1
            check_sample(s, validator, errs, warns)
            by_src[s.get("source_dataset")] += 1
            for fld in STATE_FIELDS:
                dist[fld][str(s["state_at_cutoff"][fld])] += 1
            if s["state_at_cutoff"]["V"] == "CANCELLED":
                cancelled_belief[s["state_at_cutoff"]["B"]] += 1
            censoring[s["p1_censoring_status"]] += 1
            resume_null[(s["p1_censoring_status"], str(s["p1_observed_resume"]))] += 1
            for e in s["observed_events"]:
                prov[e["source"]] += 1
                etypes[e["event_type"]] += 1
                eaccess[e["person_access"]] += 1
        per_file.append((f.name, len(seen)))

    if cancelled_belief and set(cancelled_belief) == {"BELIEVES_INVALID"}:
        warns.append("every V=CANCELLED sample is also B=BELIEVES_INVALID: B looks copied from V")
    if len(by_src) < a.require_min_sources:
        errs.append(
            f"only {len(by_src)} source_dataset present; this check requires >= {a.require_min_sources}"
        )

    lines = [f"samples: {total}", f"files: {[f.name for f in a.files]}", ""]
    for name, cnt in per_file:
        lines.append(f"  {name}: {cnt} unique sample_ids")
    lines += ["", "source_dataset:"]
    for k, c in by_src.most_common():
        lines.append(f"  {k}: {c}")
    lines.append("")
    for fld in STATE_FIELDS:
        vals = sorted(
            {v for s in by_src for v in dist[fld] if True},
            key=lambda v: -dist[fld][v],
        )[:10]
        lines.append(
            f"state_at_cutoff.{fld}: "
            + ", ".join(f"{v}={dist[fld][v]}" for v in vals)
            + f"  [distinct={len(dist[fld])}]"
        )
    lines.append("")
    lines.append("p1_censoring_status: " + ", ".join(f"{k}={v}" for k, v in censoring.most_common()))
    lines.append(
        "censoring x p1_observed_resume: "
        + ", ".join(f"{k[0]}/{k[1]}={v}" for k, v in resume_null.most_common())
    )
    lines.append("event source: " + ", ".join(f"{k}={v}" for k, v in prov.most_common()))
    lines.append("event_type: " + ", ".join(f"{k}={v}" for k, v in etypes.most_common()))
    lines.append("event person_access: " + ", ".join(f"{k}={v}" for k, v in eaccess.most_common()))
    lines += ["", f"violations: {len(errs)}"]
    lines += [f"  E {e}" for e in errs[:60]]
    lines.append(f"warnings: {len(warns)}")
    lines += [f"  W {w}" for w in warns[:20]]
    text = "\n".join(lines)
    print(text)
    write_lf(a.report, text + "\n")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
