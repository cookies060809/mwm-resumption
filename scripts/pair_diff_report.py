"""Print a field-level A/B diff for every P0 pair.

Use this before handoff to confirm that each minimal pair changes only the
intended variable. It is a human-audit aid, not a replacement for judgment.

Usage:
    python scripts/pair_diff_report.py                 # compact table, newest batch
    python scripts/pair_diff_report.py --full          # detailed view for one family
    python scripts/pair_diff_report.py --pair P01-W2   # pick a family
    python scripts/pair_diff_report.py --file data/p0/p0_samples.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_V01 = ROOT / "data" / "p0" / "p0_samples.json"
DATA_V02 = ROOT / "data" / "p0" / "p0_samples_v0.2.json"

IGNORED_TOP_LEVEL = {
    "sample_id",
    "variant",
    "notes",
    "observed_events",
    "state_at_cutoff",
    "state_evidence_event_ids",
    "state_evidence_by_factor",
    "p0_expected_action",
    "p0_expected",
    "completed_steps_at_cutoff",
    "interrupting_task",
    "p0_design",
}


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def print_value_diff(label, a, b):
    if dump(a) != dump(b):
        print(f"    {label}:")
        print(f"      A = {dump(a)}")
        print(f"      B = {dump(b)}")


def diff_event(event_a, event_b, event_id):
    keys = sorted(set(event_a) | set(event_b))
    differences = 0
    for key in keys:
        if dump(event_a.get(key)) != dump(event_b.get(key)):
            differences += 1
            print(f"    {event_id}.{key}:")
            print(f"      A = {dump(event_a.get(key))}")
            print(f"      B = {dump(event_b.get(key))}")
    return differences


def count_event_diffs(a, b):
    events_a = {event["event_id"]: event for event in a["observed_events"]}
    events_b = {event["event_id"]: event for event in b["observed_events"]}
    total = 0
    for event_id in set(events_a) | set(events_b):
        event_a = events_a.get(event_id)
        event_b = events_b.get(event_id)
        if event_a is None or event_b is None:
            total += 1
            continue
        total += sum(
            1
            for key in set(event_a) | set(event_b)
            if dump(event_a.get(key)) != dump(event_b.get(key))
        )
    return total


def is_future_leak(story_id, a, b):
    ignore = {"sample_id", "variant", "notes"}
    core_a = {k: v for k, v in a.items() if k not in ignore}
    core_b = {k: v for k, v in b.items() if k not in ignore}
    return dump(core_a) == dump(core_b)


def report_pair(story_id, pair):
    a, b = sorted(pair, key=lambda record: record["variant"])
    print(f"\n=== {story_id} ===  mechanism={a.get('mechanism', 'n/a')} split={a.get('split', 'n/a')}")

    for key in sorted(set(a) | set(b)):
        if key in IGNORED_TOP_LEVEL:
            continue
        if dump(a.get(key)) != dump(b.get(key)):
            print(f"  top-level {key}:")
            print(f"    A = {dump(a.get(key))}")
            print(f"    B = {dump(b.get(key))}")

    print("  state:")
    for factor in ("V", "F", "A", "B", "C", "Q"):
        va = a["state_at_cutoff"].get(factor)
        vb = b["state_at_cutoff"].get(factor)
        marker = "  <-- differs" if va != vb else ""
        print(f"    {factor}: {va:18} | {vb:18}{marker}")

    print("  evidence:")
    for factor in ("V", "F", "A", "B", "C", "Q"):
        ea = a["state_evidence_by_factor"].get(factor)
        eb = b["state_evidence_by_factor"].get(factor)
        if ea != eb:
            print(f"    {factor}: A={ea}  B={eb}")

    print("  expected:")
    print(f"    action: {a['p0_expected_action']}  |  {b['p0_expected_action']}")
    print(f"    A: {dump(a['p0_expected'])}")
    print(f"    B: {dump(b['p0_expected'])}")

    if a.get("p0_design") or b.get("p0_design"):
        print(f"  design: {dump(a.get('p0_design'))}")

    if a.get("completed_steps_at_cutoff") != b.get("completed_steps_at_cutoff"):
        print("  completed_steps_at_cutoff:")
        print(f"    A = {a['completed_steps_at_cutoff']}")
        print(f"    B = {b['completed_steps_at_cutoff']}")

    if a.get("interrupting_task") != b.get("interrupting_task"):
        print("  interrupting_task:")
        print(f"    A = {dump(a.get('interrupting_task'))}")
        print(f"    B = {dump(b.get('interrupting_task'))}")

    events_a = {event["event_id"]: event for event in a["observed_events"]}
    events_b = {event["event_id"]: event for event in b["observed_events"]}
    all_ids = list(events_a) + [eid for eid in events_b if eid not in events_a]
    print("  events:")
    total_field_diffs = 0
    for event_id in all_ids:
        event_a = events_a.get(event_id)
        event_b = events_b.get(event_id)
        if event_a is None:
            print(f"    {event_id}: only in B -> {event_b['description']}")
            total_field_diffs += 1
            continue
        if event_b is None:
            print(f"    {event_id}: only in A -> {event_a['description']}")
            total_field_diffs += 1
            continue
        total_field_diffs += diff_event(event_a, event_b, event_id)
    if total_field_diffs == 0:
        print("    (identical)")

    if story_id.startswith("P07"):
        status = "PASS" if is_future_leak(story_id, a, b) else "FAIL"
        print(f"  P07 input identity: {status}")


def main():
    # Windows consoles default to a legacy code page; the descriptions are Chinese.
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, default=None)
    parser.add_argument("--pair", default=None)
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args()

    path = args.file or (DATA_V02 if DATA_V02.exists() else DATA_V01)
    records = json.loads(path.read_text(encoding="utf-8"))
    by_story = defaultdict(list)
    for record in records:
        by_story[record["base_story_id"]].append(record)

    print(f"data: {path.relative_to(ROOT)}  families={len(by_story)}  records={len(records)}")

    if args.full or args.pair:
        targets = [args.pair] if args.pair else ([next(iter(sorted(by_story)))] if args.full else [])
        for story_id in targets:
            if len(by_story.get(story_id, [])) == 2:
                report_pair(story_id, by_story[story_id])
            else:
                print(f"{story_id}: expected 2 records, got {len(by_story.get(story_id, []))}")
        return

    print(f"{'family':10} {'mechanism':22} {'split':6} {'event-diffs':11} note")
    leak_fail = []
    for story_id in sorted(by_story):
        pair = by_story[story_id]
        if len(pair) != 2:
            print(f"{story_id:10} ERROR: expected 2 records, got {len(pair)}")
            continue
        a, b = sorted(pair, key=lambda record: record["variant"])
        diffs = count_event_diffs(a, b)
        note = ""
        if story_id.startswith("P07"):
            ok = is_future_leak(story_id, a, b)
            note = "P07 identity " + ("PASS" if ok else "FAIL")
            if not ok:
                leak_fail.append(story_id)
        print(
            f"{story_id:10} {a.get('mechanism', 'n/a'):22} {a.get('split', 'n/a'):6} "
            f"{diffs:<11} {note}"
        )
    print()
    print(f"P07 identity failures: {len(leak_fail)}")


if __name__ == "__main__":
    main()
