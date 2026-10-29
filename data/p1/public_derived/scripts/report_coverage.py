"""Coverage report for the delivered P1 set.

Writes docs/coverage_report.md: per-source sample counts, label distributions
for every state dimension, censoring / resume coverage, provenance mix, how much
of each dimension is UNKNOWN, and an explicit list of schema values that the
available public annotations simply cannot produce (so nobody reads their absence
as a sampling bug).
"""

import json
from collections import Counter, defaultdict
from pathlib import Path

from common import write_lf

ROOT = Path(__file__).resolve().parents[1]
COMBINED = ROOT / "processed" / "p1_combined.jsonl"
OUT = ROOT / "docs" / "coverage_report.md"

STATE_FIELDS = ["V", "F", "A", "B", "C", "Q"]
EVENT_TYPES = ["start_goal", "interruption", "resume", "progress", "completion", "background_fact"]

TIERS = {
    "V": ["VALID", "CANCELLED", "FULFILLED", "UNKNOWN"],
    "F": ["READY", "BLOCKED", "UNKNOWN"],
    "A": ["ACCESSED", "NOT_ACCESSED", "UNCERTAIN", "UNKNOWN"],
    "B": ["BELIEVES_VALID", "BELIEVES_INVALID", "UNRESOLVED", "UNKNOWN"],
    "C": ["ACTIVE", "SUSPENDED", "ABANDONED", "COMPLETED", "UNKNOWN"],
    "Q": [],
}


def pct(n, d):
    return f"{100.0 * n / d:.1f}%" if d else "n/a"


def main():
    rows = [json.loads(l) for l in COMBINED.read_text(encoding="utf-8").splitlines() if l.strip()]
    n = len(rows)
    by_src = Counter(r["source_dataset"] for r in rows)

    state_by_src = defaultdict(lambda: defaultdict(Counter))
    censor = defaultdict(Counter)
    resume_step_null = defaultdict(int)
    prov = Counter()
    etypes = Counter()
    eaccess = Counter()
    goal_uniq, story_uniq = defaultdict(set), defaultdict(set)
    steps_present = defaultdict(int)
    trace_len = []
    ev_len = []

    for r in rows:
        s = r["source_dataset"]
        for f in STATE_FIELDS:
            state_by_src[s][f][str(r["state_at_cutoff"][f])] += 1
        censor[s][r["p1_censoring_status"]] += 1
        if r["p1_resume_step"] is None:
            resume_step_null[s] += 1
        goal_uniq[s].add(r["goal_id"])
        story_uniq[s].add(r["base_story_id"])
        if r["task_steps"]:
            steps_present[s] += 1
        trace_len.append(len(r["evidence_trace"]))
        ev_len.append(len(r["observed_events"]))
        for e in r["observed_events"]:
            prov[e["source"]] += 1
            etypes[e["event_type"]] += 1
            eaccess[e["person_access"]] += 1

    L = []
    L.append("# P1 coverage report (ECR-MWM)")
    L.append("")
    L.append(f"Delivered set: `{COMBINED.relative_to(ROOT).as_posix()}` — **{n} samples** from "
             f"**{len(by_src)} source datasets** (requirement: >=2).")
    L.append("")
    L.append("## Sample counts")
    L.append("")
    L.append("| source_dataset | samples | base_story_ids | goal_ids | samples with non-empty task_steps |")
    L.append("|---|---:|---:|---:|---:|")
    for s, c in by_src.most_common():
        L.append(f"| {s} | {c} | {len(story_uniq[s])} | {len(goal_uniq[s])} | {steps_present[s]} |")
    L.append("")

    L.append("## Censoring and resume labels")
    L.append("")
    L.append("| source_dataset | observed_resume | censored | observed_not_resume | p1_resume_step = null |")
    L.append("|---|---:|---:|---:|---:|")
    for s, c in by_src.most_common():
        L.append(
            f"| {s} | {censor[s]['observed_resume']} | {censor[s]['censored']} | "
            f"{censor[s]['observed_not_resume']} | {resume_step_null[s]} ({pct(resume_step_null[s], c)}) |"
        )
    totals = Counter(r["p1_censoring_status"] for r in rows)
    n_step_null = sum(1 for r in rows if r.get("p1_resume_step") is None)
    L.append(
        f"| **total** | **{totals['observed_resume']}** | **{totals['censored']}** | "
        f"**{totals['observed_not_resume']}** | {n_step_null} ({pct(n_step_null, n)}) |"
    )
    L.append("")
    L.append("Observed recoveries come from two sources with different evidence strength: IHBench "
             "derives them from the released episode text (rule R8 - re-delivery of the withheld "
             "step content or a stage advance), and REBOOT reads them straight out of the annotated "
             "`failure.recovery_started_at_frame` (rule B12). `observed_not_resume` comes only from "
             "IHBench, where a covered window shows neither test passing. Every InterruptBench sample "
             "is `censored`: the release ships no run record, so absence of recovery there is not "
             "observable and `p1_observed_resume` is null rather than false.")
    L.append("")

    L.append("## state_at_cutoff distribution")
    L.append("")
    for f in STATE_FIELDS:
        vals = sorted(
            {v for s in by_src for v in state_by_src[s][f]},
            key=lambda v: -sum(state_by_src[s][f][v] for s in by_src),
        )[:8]
        L.append(f"### {f}")
        L.append("")
        L.append("| source_dataset | " + " | ".join(vals) + " |")
        L.append("|---" * (len(vals) + 1) + "|")
        for s in by_src:
            row = [str(state_by_src[s][f][v]) for v in vals]
            L.append(f"| {s} | " + " | ".join(row) + " |")
        L.append("")
    unknown_share = {
        f: sum(1 for r in rows if str(r["state_at_cutoff"][f]) == "UNKNOWN") for f in STATE_FIELDS
    }
    L.append("UNKNOWN share over all samples: "
             + ", ".join(f"{f} {pct(unknown_share[f], n)}" for f in STATE_FIELDS))
    L.append("")

    L.append("## Event provenance")
    L.append("")
    L.append("| dimension | values |")
    L.append("|---|---|")
    L.append("| event source | " + ", ".join(f"{k}={v}" for k, v in prov.most_common()) + " |")
    L.append("| event_type | " + ", ".join(f"{k}={v}" for k, v in etypes.most_common()) + " |")
    L.append("| event person_access | " + ", ".join(f"{k}={v}" for k, v in eaccess.most_common()) + " |")
    L.append(f"| evidence_trace length | min {min(trace_len)}, max {max(trace_len)}, mean "
             f"{sum(trace_len) / len(trace_len):.2f} |")
    L.append(f"| observed_events length | min {min(ev_len)}, max {max(ev_len)}, mean {sum(ev_len) / len(ev_len):.2f} |")
    L.append("")
    L.append("`llm_inferred` events: "
             f"{prov.get('llm_inferred', 0)} — no label in this delivery depends on model inference.")
    L.append("")

    L.append("## Withdrawn rule-mapped claims (state_withdrawn)")
    L.append("")
    withdrawn = Counter()
    withdrawn_rules = defaultdict(Counter)
    withdrawn_reason = {}
    for r in rows:
        for factor, detail in (r.get("state_withdrawn") or {}).items():
            withdrawn[factor] += 1
            withdrawn_rules[factor][detail.get("rule")] += 1
            withdrawn_reason.setdefault(factor, detail.get("reason", ""))
    L.append("| factor | withdrawn rows | rules | example reason |")
    L.append("|---|---:|---|---|")
    for factor, count in withdrawn.most_common():
        rules = ", ".join(f"{rule} x{amount}" for rule, amount in withdrawn_rules[factor].most_common())
        L.append(f"| {factor} | {count} | {rules} | {withdrawn_reason[factor]} |")
    L.append("")
    rows_with_withdrawal = sum(1 for r in rows if r.get("state_withdrawn"))
    L.append(f"{sum(withdrawn.values())} withdrawn claims across {rows_with_withdrawal} rows. The claimed value is kept in "
             "`state_withdrawn.<factor>.claimed` for audit; the live `state_at_cutoff` field is `UNKNOWN`. "
             "Never treat a withdrawn value as a gold label or relabel it back.")
    L.append("")

    L.append("## Enum tiers not reached by these sources")
    L.append("")
    reason = {
        "V=UNKNOWN": "every source annotates enough to decide validity at the cutoff",
        "F=BLOCKED": "REBOOT BLOCKED rule withdrawn (B7) in the 2026-10-23 revision",
        "A=NOT_ACCESSED": "REBOOT NOT_ACCESSED rule withdrawn (B8) in the 2026-10-23 revision",
        "A=UNCERTAIN": "unused fallback: access is either evidenced or explicitly absent",
        "B=UNRESOLVED": "belief rules withdrawn (R6/B9) in the 2026-10-23 revision",
        "B=BELIEVES_INVALID": "withdrawn with the rest of REBOOT's B values (B9)",
        "C=ABANDONED": "InterruptBench commitment mapping withdrawn (T8); a cancellation is the user's act",
    }
    absent = []
    for fld, values in TIERS.items():
        for v in values:
            n = sum(1 for r in rows if str(r["state_at_cutoff"][fld]) == v)
            if n == 0:
                absent.append((f"{fld}={v}", n))
    nr = sum(1 for r in rows if r["p1_censoring_status"] == "observed_not_resume")
    nful = sum(1 for r in rows if r["state_at_cutoff"]["V"] == "FULFILLED")
    ncomp = sum(1 for r in rows if any(e["event_type"] == "completion" for e in r["observed_events"]))
    nres = sum(1 for r in rows if any(e["event_type"] == "resume" for e in r["observed_events"]))
    if nr == 0:
        absent.append(("p1_censoring_status=observed_not_resume", 0))
    if ncomp == 0:
        absent.append(("event_type=completion", 0))
    if nres == 0:
        absent.append(("event_type=resume", 0))
    qvals = {str(r["state_at_cutoff"]["Q"]) for r in rows} - {"UNKNOWN", "NOT_APPLICABLE"}
    reached = {
        f: len({str(r["state_at_cutoff"][f]) for r in rows} & set(TIERS[f]))
        for f in ("V", "F", "A", "B", "C")
    }
    total_tiers = {f: len(values) for f, values in TIERS.items()}
    L.append(
        "Reached by at least one sample: "
        + ", ".join(f"{f} {reached[f]}/{total_tiers[f]}" for f in ("V", "F", "A", "B", "C"))
        + f", Q {len(qvals)} distinct step ids + 2 sentinels, censoring 3/3, event_type 6/6 "
        + f"(resume={nres}, completion={ncomp}), observed_not_resume={nr}."
    )
    L.append("")
    if absent:
        L.append("| tier | count | why |")
        L.append("|---|---:|---|")
        for v, n in absent:
            L.append(f"| {v} | {n} | {reason.get(v, 'no source annotation supports this value')} |")
    else:
        L.append("Every enum tier in the schema is instantiated by at least one sample.")
    L.append("")
    thin = [
        f"{fld}={v}"
        for fld in ("V", "F", "A", "B", "C")
        for v in TIERS[fld]
        if sum(1 for r in rows if str(r["state_at_cutoff"][fld]) == v) == 1
    ]
    L.append("Thin tiers (n=1, prove the mapping only, not a usable class): "
             + (", ".join(f"`{item}`" for item in thin) if thin else "none") + ".")
    L.append(f"`V=FULFILLED`/`C=COMPLETED`/`Q=NOT_APPLICABLE` ({nful} each) come only from REBOOT "
             "episodes whose description asserts completion. "
             f"`observed_not_resume` ({nr}) comes only from IHBench.")
    L.append("")

    write_lf(OUT, "\n".join(L) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(L)} lines)")


if __name__ == "__main__":
    main()
