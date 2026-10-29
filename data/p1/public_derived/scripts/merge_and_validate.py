"""Merge the per-source P1 files and run every delivery check.

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
  * p1-0.2 supervision contract: a factor is supervised exactly when its value is
    not UNKNOWN, a supervised factor carries non-empty evidence, and a masked
    factor is recorded in state_withdrawn with a reason;
  * p1-0.2 resume contract: resume_loss_mask=1 requires an eligible blind sample,
    eligibility requires cutoff_kind="interruption" and an outcome positioned
    strictly after the cutoff event, and the outcome event must not be inside
    observed_events;
  * p1-0.2 split contract: split == split_for(source, split_group_id) and no
    split_group_id straddles two splits;
  * p1-0.2 input contract: events carry actor/text/position, positions share one
    unit and never exceed the cutoff's, and no supervision-only label_evidence
    string appears inside the model-visible event text;
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
from p1_common import STATE_FIELDS, UNKNOWN, split_for

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "docs" / "schema.json"

ABBR = {"IHBench": "ihb", "REBOOT": "rbt", "IndustReal": "ind", "InterruptBench": "ib"}
SUBJECT_BY_SOURCE = {
    "IHBench": "synthetic_dialogue",
    "REBOOT": "robot",
    "InterruptBench": "software_agent_spec",
}
Q_SENTINELS = {"UNKNOWN", "NOT_APPLICABLE"}
PARTS = ["ihbench.jsonl", "reboot.jsonl", "industreal.jsonl", "interruptbench.jsonl"]
# Strings shorter than this are too generic to prove a leak, so the leak guard
# only compares substantive supervision-only content against the input text.
LEAK_MIN_CHARS = 25
LEAK_KEYS = ("tf_rubric", "withheld_tail", "baseline_response", "window_assistant_transcripts",
             "annotated_language_description")


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


def check_v02(s, errs, warns, group_splits):
    """The p1-0.2 supervision / resume / split / input contracts."""
    sid = s["sample_id"]
    if s.get("schema_version") != "p1-0.2":
        errs.append(f"{sid}: schema_version {s.get('schema_version')!r} != p1-0.2")
    expected_subject = SUBJECT_BY_SOURCE.get(s["source_dataset"])
    if expected_subject and s.get("subject_type") != expected_subject:
        errs.append(
            f"{sid}: subject_type {s.get('subject_type')!r} must be {expected_subject!r} "
            f"for {s['source_dataset']} - no row here documents a real human subject"
        )

    state, mask = s["state_at_cutoff"], s["state_loss_mask"]
    origin, withdrawn = s["label_origin"], s["state_withdrawn"]
    for f in STATE_FIELDS:
        sup = int(state[f] != UNKNOWN)
        if mask[f] != sup:
            errs.append(f"{sid}: state_loss_mask.{f}={mask[f]} contradicts value {state[f]!r}")
        if sup:
            if not (origin.get(f) or {}).get("evidence"):
                errs.append(f"{sid}: {f} is supervised without label_origin evidence")
        else:
            if origin.get(f) is not None:
                errs.append(f"{sid}: {f} is masked but label_origin still names an source")
            w = withdrawn.get(f) or {}
            if len(w.get("reason", "")) < 8:
                errs.append(f"{sid}: {f} is masked but state_withdrawn records no reason")
    stray = set(withdrawn) - set(STATE_FIELDS) - {"p1_observed_resume"}
    if stray:
        errs.append(f"{sid}: state_withdrawn has unknown keys {sorted(stray)}")

    eligible, rmask = s["eligible_for_resume_eval"], s["resume_loss_mask"]
    if rmask and not (eligible and s["p1_censoring_status"] != "censored"):
        errs.append(f"{sid}: resume_loss_mask=1 on a sample that is not an eligible observation")
    if eligible and not rmask:
        errs.append(f"{sid}: eligible_for_resume_eval but resume_loss_mask=0")
    if s["step_loss_mask"] and not (s["p1_resume_step"] and rmask):
        errs.append(f"{sid}: step_loss_mask=1 without a supervised resume step")
    if not s["eligible_for_resume_eval"] and s["outcome_time"] is not None:
        errs.append(f"{sid}: outcome_time set on a sample that is not eligible for resume eval")
    if eligible:
        if s["cutoff_kind"] != "interruption":
            errs.append(f"{sid}: eligible for blind recovery eval but cutoff_kind={s['cutoff_kind']!r}")
        ot = s["outcome_time"]
        if not ot:
            errs.append(f"{sid}: eligible without outcome_time")
        else:
            pos = {e["event_id"]: e.get("position") for e in s["observed_events"]}
            cut = pos.get(s["cutoff_event_id"]) or {}
            if ot.get("unit") != cut.get("unit") or not ot["value"] > cut["value"]:
                errs.append(
                    f"{sid}: outcome_time {ot} is not strictly after the cutoff position {cut}"
                )
            if ot.get("event_id") in pos:
                errs.append(f"{sid}: outcome event {ot['event_id']} is inside observed_events (label leak)")
        hz = s["observation_horizon"]
        if hz["planned"] is not None and not hz["window_complete"]:
            warns.append(
                f"{sid}: eligible with an incomplete window ({hz['covered']}/{hz['planned']} "
                f"{hz['unit']}) - only a positive seen inside a short window may be scored"
            )
    elif s["cutoff_kind"] in ("recovery", "completion"):
        if rmask:
            errs.append(f"{sid}: {s['cutoff_kind']} cutoff must not supervise blind recovery")

    if s["split"] != split_for(s["source_dataset"], s["split_group_id"]):
        errs.append(
            f"{sid}: split {s['split']!r} does not match split_for({s['source_dataset']},"
            f" {s['split_group_id']})"
        )
    group_splits.setdefault((s["source_dataset"], s["split_group_id"]), set()).add(s["split"])

    units, vals = set(), []
    for e in s["observed_events"]:
        if not e.get("actor"):
            errs.append(f"{sid}: event {e['event_id']} has no actor - a human-user field could be read as the assistant's state")
        p = e.get("position")
        if p:
            units.add(p["unit"])
            vals.append(p["value"])
        if e["event_id"] == s["cutoff_event_id"] and not e.get("text"):
            errs.append(f"{sid}: cutoff event carries no annotated text, so the input is an id only")
    if len(units) > 1:
        errs.append(f"{sid}: observed_events mix position units {sorted(units)}")
    if vals != sorted(vals):
        errs.append(f"{sid}: observed_events are not ordered by position")

    op = s.get("objective_progress")
    if op and op.get("step_id") and op["step_id"] not in set(s["task_steps"]):
        errs.append(f"{sid}: objective_progress.step_id {op['step_id']} not in task_steps")

    # Text-level leak guard, applied only to blind/state cutoffs: at a recovery or
    # completion cutoff the annotated description of that event legitimately IS input.
    if s["cutoff_kind"] in ("interruption", "pre_interruption"):
        hay = " ".join((e.get("text") or "").lower() for e in s["observed_events"])
        le = s.get("label_evidence") or {}
        for key in LEAK_KEYS:
            for item in (le.get(key) if isinstance(le.get(key), list) else [le.get(key)]):
                if isinstance(item, str) and len(item) >= LEAK_MIN_CHARS:
                    if item.lower().strip() in hay:
                        errs.append(f"{sid}: label_evidence.{key} leaks into the input text")


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
    group_splits: dict[tuple, set] = {}
    supervised, cutoff_kinds, splits, subjects = defaultdict(Counter), Counter(), Counter(), Counter()
    resume_stats, withdraw_reasons = Counter(), Counter()
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
            if s.get("schema_version") == "p1-0.2":
                check_v02(s, errs, warns, group_splits)
            by_src[s.get("source_dataset")] += 1
            subjects[s.get("subject_type")] += 1
            splits[s.get("split")] += 1
            cutoff_kinds[s.get("cutoff_kind")] += 1
            for fld in STATE_FIELDS:
                dist[fld][str(s["state_at_cutoff"][fld])] += 1
                supervised[fld][s.get("source_dataset")] += s["state_loss_mask"][fld]
            resume_stats[(s.get("source_dataset"), "supervised" if s.get("resume_loss_mask") else "masked")] += 1
            for fld, w in (s.get("state_withdrawn") or {}).items():
                withdraw_reasons[(w.get("rule") or "?", (w.get("reason") or "")[:40])] += 1
            if s["state_at_cutoff"]["V"] == "CANCELLED":
                cancelled_belief[s["state_at_cutoff"]["B"]] += 1
            censoring[s["p1_censoring_status"]] += 1
            resume_null[(s["p1_censoring_status"], str(s["p1_observed_resume"]))] += 1
            for e in s["observed_events"]:
                prov[e["source"]] += 1
                etypes[e["event_type"]] += 1
                eaccess[e["person_access"]] += 1
        per_file.append((f.name, len(seen)))

    for (src, group), sp in sorted(group_splits.items()):
        if len(sp) > 1:
            errs.append(f"{src}/{group}: split_group_id straddles splits {sorted(sp)}")

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
    lines += ["", "p1-0.2 contracts:",
              "  subject_type: " + ", ".join(f"{k}={v}" for k, v in subjects.most_common()),
              "  cutoff_kind: " + ", ".join(f"{k}={v}" for k, v in cutoff_kinds.most_common()),
              f"  split: {dict(splits)}  (split_group_id units={len(group_splits)})"]
    lines.append("  supervised state factors per source:")
    for fld in STATE_FIELDS:
        lines.append(
            f"    {fld}: " + ", ".join(f"{src}={supervised[fld][src]}" for src in sorted(by_src))
            + f"  total={sum(supervised[fld].values())}/{total}"
        )
    lines.append("  resume supervision per source:")
    for src in sorted(by_src):
        lines.append(
            f"    {src}: supervised={resume_stats[(src, 'supervised')]} "
            f"masked={resume_stats[(src, 'masked')]}"
        )
    lines.append("  withdrawn claims (rule, reason -> rows):")
    for (rule, reason), n in sorted(withdraw_reasons.items(), key=lambda kv: -kv[1]):
        lines.append(f"    {rule or '?'} | {reason}… -> {n}")
    lines.append("  NOTE: a factor absent above has state_loss_mask=0 on every row: the sources")
    lines.append("        do not evidence it, so it is not supervised and must not be scored.")
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
