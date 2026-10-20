"""Generate the P0 handoff quality report for A and C from the live datasets.

Every number is computed from the data files, so human-gate counts update
themselves once `annotation.status` is actually flipped. Nothing here asserts a
review that no person signed.

Declared-but-unused enum values are reported because a batch can hit its record
target while still leaving the mechanism cells A asked for empty.

Usage: python scripts/p0_quality_report.py
"""

from __future__ import annotations

import hashlib
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import validate_data as vd

FACTORS = ("V", "F", "A", "B", "C", "Q")
REVIEWED = ("reviewed", "adjudicated")
EVENT_ENUMS = {
    "person_access": ("definitions", "event", "properties", "person_access", "enum"),
    "person_comprehension": (
        "definitions",
        "event",
        "properties",
        "person_comprehension",
        "enum",
    ),
    "certainty": ("definitions", "event", "properties", "certainty", "enum"),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def lookup(node, keys):
    for key in keys:
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node


def gates(records):
    errors = vd.validate_records(records)
    event_ids_seen = set()
    complete = dangling = cutoff_ok = 0
    for record in records:
        state = record["state_at_cutoff"]
        by_factor = record["state_evidence_by_factor"]
        ids = {event["event_id"] for event in record["observed_events"]}
        event_ids_seen |= ids
        ok = all(factor in state and factor in by_factor for factor in FACTORS)
        for factor in FACTORS:
            refs = by_factor.get(factor) or []
            dangling += sum(1 for ref in refs if ref not in ids)
        complete += ok
        times = [event["time"] for event in record["observed_events"]]
        last_is_cutoff = record["observed_events"][-1]["event_id"] == record["cutoff_event_id"]
        cutoff_ok += times == sorted(times) and last_is_cutoff
    families = defaultdict(set)
    for record in records:
        families[record["base_story_id"]].add(record["variant"])
    clean = sum(1 for variants in families.values() if variants == {"A", "B"})
    return {
        "errors": errors,
        "events": sum(len(record["observed_events"]) for record in records),
        "families": len(families),
        "clean_pairs": clean,
        "evidence_coverage": complete,
        "dangling": dangling,
        "cutoff_ok": cutoff_ok,
        "reviewed": sum(1 for record in records if record["annotation"]["status"] in REVIEWED),
        "annotators": sorted({record["annotation"]["annotator_id"] for record in records}),
    }


def p07_identity(records):
    pair = [record for record in records if record["base_story_id"] == "P07"]
    if len(pair) != 2:
        return "N/A (no P07 family)"
    cores = [
        {k: v for k, v in record.items() if k not in vd.PAIR_IDENTITY_IGNORED} for record in pair
    ]
    return "PASS" if vd.equal_json(cores[0], cores[1]) else "FAIL"


def report(path):
    records = vd.load_json(path)
    total = len(records)
    g = gates(records)
    version = records[0].get("schema_version", "?")
    schema_path = vd.SCHEMAS.get(version)
    schema = vd.load_json(schema_path) if schema_path and schema_path.exists() else None

    print(f"\n### {path.name}   ({version})")
    print(f"n: {total}   families: {g['families']} ({g['clean_pairs']} clean A/B)   events: {g['events']}")
    status = "PASS" if not g["errors"] else f"FAIL ({len(g['errors'])} error(s))"
    print(f"schema_and_crossfield: {status}")
    print(f"evidence_coverage: {g['evidence_coverage']}/{total}   dangling_evidence_refs: {g['dangling']}")
    print(f"cutoff_no_future: {g['cutoff_ok']}/{total}")
    print(f"p07_input_identity: {p07_identity(records)}")
    print(f"human_audit: {g['reviewed']}/{total}  (annotator_id={g['annotators']})")
    print("second_reviewer (A/C blind review): not recorded  <- requires a person outside B")
    print(f"domains: {dict(Counter(record.get('domain', '?') for record in records))}")
    print(f"split: {dict(Counter(str(record.get('split')) for record in records))}")
    print(f"sha256: {sha256(path)}")

    if schema is None:
        print("enum coverage: skipped (no schema for this version)")
        return

    events = [event for record in records for event in record["observed_events"]]
    observed = {}
    for factor in FACTORS:
        observed[f"state.{factor}"] = (
            lookup(schema, ("definitions", "state", "properties", factor, "enum")),
            Counter(record["state_at_cutoff"].get(factor) for record in records),
        )
    for field, keys in EVENT_ENUMS.items():
        observed[f"event.{field}"] = (lookup(schema, keys), Counter(event.get(field) for event in events))

    print("enum coverage (declared in schema vs used in data):")
    unused = []
    for label, (allowed, counts) in observed.items():
        if not allowed:
            continue
        used = {value: counts.get(value, 0) for value in allowed}
        print(f"  {label}: " + ", ".join(f"{value}={n}" for value, n in used.items()))
        unused += [f"{label}.{value}" for value, n in used.items() if n == 0]
    if unused:
        print(f"  DECLARED BUT NEVER USED ({len(unused)}): {', '.join(unused)}")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    print("P0 quality report -- computed, not hand-typed")
    for path in vd.DATA_FILES:
        if path.exists():
            report(path)
        else:
            print(f"\n### {path.name}   (absent)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
