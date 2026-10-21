"""Build the standalone P0 v0.3 release from the two signed source batches.

The historical p0_samples_v0.3.json is a 14-record uncertainty supplement, not
a standalone training dataset. This release includes the 240-record base exactly
once, preserves all existing labels/splits/signatures, and records provenance.
Use --check in CI to detect stale/missing release files without rewriting them.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.export_eval_format import MAPPING_NOTES, task_family, to_input, to_label  # noqa: E402
from scripts.p0_quality_report import enum_counts  # noqa: E402
from scripts.validate_data import SCHEMAS, validate_records  # noqa: E402

SOURCES = (
    ROOT / "data/p0/p0_samples_v0.2.json",
    ROOT / "data/p0/p0_samples_v0.3.json",
)
OUT = ROOT / "data/p0/v0.3"
SPLITS = ("train", "dev", "test", "calibration")


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def jsonl_bytes(rows):
    return "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
                   for row in rows).encode("utf-8")


def sha256(value):
    return hashlib.sha256(value).hexdigest()


def check_release(records):
    """Run record/pair validation plus leakage checks across source batches."""
    errors = validate_records(records)
    if not records:
        errors.append("release must not be empty")
    blueprint_splits = defaultdict(set)
    for record in records:
        blueprint_splits[task_family(record)].add(record["split"])
        if record["schema_version"] != "p0-record/v0.2.0":
            errors.append(f"{record['sample_id']}: incompatible schema")
        if record["annotation"]["status"] not in ("reviewed", "adjudicated"):
            errors.append(f"{record['sample_id']}: source not reviewed")
    for blueprint, splits in sorted(blueprint_splits.items()):
        if len(splits) != 1:
            errors.append(f"{blueprint}: blueprint crosses splits {sorted(splits)}")
    return errors


def coverage(records, schema):
    events = [e for record in records for e in record["observed_events"]]
    return {name: {value: counts.get(value, 0) for value in allowed}
            for name, (allowed, counts) in enum_counts(records, events, schema).items()}


def release_files(sources=SOURCES):
    """Return deterministic relative-path -> bytes; no filesystem writes."""
    records, provenance, source_info = [], {}, []
    for path in sources:
        raw = path.read_bytes()
        batch = json.loads(raw)
        source_name = path.relative_to(ROOT).as_posix()
        for record in batch:
            sample_id = record["sample_id"]
            if sample_id in provenance:
                raise ValueError(f"duplicate sample_id across sources: {sample_id}")
            provenance[sample_id] = source_name
        source_info.append({"path": source_name, "sha256": sha256(raw),
                            "records": len(batch),
                            "split_records": dict(sorted(Counter(r["split"] for r in batch).items()))})
        records.extend(batch)
    records.sort(key=lambda r: (r["base_story_id"], r["variant"]))
    errors = check_release(records)
    if errors:
        raise ValueError("INVALID_RELEASE:\n" + "\n".join(errors))

    files = {"p0_samples.json": json_bytes(records),
             "eval/inputs.jsonl": jsonl_bytes([to_input(r) for r in records]),
             "eval/labels.jsonl": jsonl_bytes([to_label(r) for r in records]),
             "eval/MAPPING.md": ("# Standalone P0 v0.3 (254 records)\n\n"
                                 "Source of truth: ../p0_samples.json. Record schema remains "
                                 "p0-record/v0.2.0.\n\n" + MAPPING_NOTES +
                                 "\nThe C boolean `understood` merges MISUNDERSTOOD and "
                                 "NOT_UNDERSTOOD; use raw records for the full U distinction. "
                                 "No probability calibration is fitted.\n").encode("utf-8")}
    splits = {}
    for split in SPLITS:
        subset = [r for r in records if r["split"] == split]
        files[f"splits/{split}.json"] = json_bytes(subset)
        labels = [to_label(r) for r in subset]
        splits[split] = {
            "records": len(subset),
            "families": len({r["base_story_id"] for r in subset}),
            "sample_ids": [r["sample_id"] for r in subset],
            "resume_labels": dict(sorted(Counter(r["resume_label"] for r in labels).items())),
            "state_supervision_counts": {
                factor: sum(r["state_at_cutoff"][factor] != "UNKNOWN" and
                            bool(r["state_evidence_by_factor"][factor]) for r in subset)
                for factor in "VFABCQ"},
        }
    schema_path = SCHEMAS["p0-record/v0.2.0"]
    schema = json.loads(schema_path.read_bytes())
    enum_coverage = coverage(records, schema)
    unused = [f"{name}.{value}" for name, values in enum_coverage.items()
              for value, count in values.items() if count == 0]
    manifest = {
        "release_version": "p0-release/v0.3.0",
        "record_schema_version": "p0-record/v0.2.0",
        "dataset_layer": "P0", "standalone": True,
        "records": len(records),
        "families": len({r["base_story_id"] for r in records}),
        "events": sum(len(r["observed_events"]) for r in records),
        "sources": source_info, "provenance": dict(sorted(provenance.items())),
        "splits": splits,
        "annotation_status": dict(sorted(Counter(r["annotation"]["status"] for r in records).items())),
        "second_reviewer_records": sum(r["annotation"]["second_reviewer_id"] is not None for r in records),
        "schema": {"path": schema_path.relative_to(ROOT).as_posix(),
                   "sha256": sha256(schema_path.read_bytes())},
        "enum_coverage": enum_coverage, "unused_enum_values": unused,
        "split_enum_coverage": {split: coverage([r for r in records if r["split"] == split], schema)
                                for split in SPLITS},
        "checks": {"schema_and_cross_fields": "pass", "unique_samples": "pass",
                   "paired_family_split": "pass", "blueprint_split_isolation": "pass"},
        "limitations": [
            "Scripted P0 expectations, not observed human behavior.",
            "Source B signatures inherited verbatim; no new human review asserted.",
            "A/C independent review and inherited B-label adjudication remain pending.",
            "Rare uncertainty labels have few examples; enum coverage is not statistical sufficiency.",
            "Calibration split is empty by team decision; no calibration fitted.",
            "Do not concatenate this release with its sources (duplicate sample IDs).",
        ],
        "artifacts": {name: {"sha256": sha256(raw), "bytes": len(raw)}
                      for name, raw in sorted(files.items())},
    }
    files["manifest.json"] = json_bytes(manifest)
    return files


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify committed release without writing")
    args = parser.parse_args(argv)
    try:
        files = release_files()
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    if args.check:
        stale = [name for name, raw in files.items()
                 if not (OUT / name).is_file() or (OUT / name).read_bytes() != raw]
        if stale:
            print("STALE_RELEASE: " + ", ".join(stale), file=sys.stderr)
            return 1
    else:
        for name, raw in files.items():
            path = OUT / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
    manifest = json.loads(files["manifest.json"])
    print(f"{'checked' if args.check else 'built'} {manifest['records']} records / "
          f"{manifest['families']} families / {manifest['events']} events")
    print("records per split:", {k: v["records"] for k, v in manifest["splits"].items()})
    print("entry: data/p0/v0.3/p0_samples.json (standalone; do not append sources)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
