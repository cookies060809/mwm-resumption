"""Build a local review queue from downloaded source annotations, without P1 gold."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mwm_eval.engine import dump_json, dump_jsonl
from mwm_eval.holoassist_candidates import extract_candidates
from mwm_eval.schema import file_hash


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annotations", type=Path, default=ROOT / "data/external/raw/holoassist/annotations_pilot.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results/p1_audit/holoassist")
    args = parser.parse_args()
    sessions = json.loads(args.annotations.read_text(encoding="utf-8"))
    candidates, summary = extract_candidates(sessions)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    dump_jsonl(args.output_dir / "review_candidates.jsonl", candidates)
    summary["annotation_subset_sha256"] = file_hash(args.annotations)
    dump_json(args.output_dir / "candidate_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
