#!/usr/bin/env bash
# End-to-end rebuild of the P1 public-derived delivery (ECR-MWM), run from
# data/p1/public_derived/.
#
#   fetch raw annotations -> convert per source -> merge + validate -> reports
#
# Only the provenance manifests under raw/ are versioned; the fetched upstream
# annotation files themselves stay out of Git (see the repository .gitignore).
#
# Host network facts that shape this script (see docs/source_manifest.md §0):
#   huggingface.co direct is blocked -> fetch_ihbench_text.py tries hf-mirror.com
#   first, then huggingface.co; GitHub is reached via api.github.com and
#   codeload.github.com (raw.githubusercontent.com is blocked).
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONIOENCODING=utf-8

echo "== 1/5 fetch raw annotations =="
python scripts/fetch_ihbench_text.py            # IHBench: text columns only, audio never requested
python scripts/fetch_github_paths.py scripts/fetch_interruptbench_spec.json || {
  echo "   api.github.com rate limited: reusing files already staged under raw/InterruptBench"
  echo "   fallback: curl -C - https://codeload.github.com/HenryPengZou/InterruptBench/tar.gz/refs/heads/main"
  echo "             then extract with --exclude='*coco_images*' --exclude='*.png' --exclude='*.jpg'"
}
python scripts/fetch_reboot_meta_v2.py || echo "   REBOOT meta unreachable from this host (docs/source_manifest.md §2.2); reusing raw/REBOOT if present"

echo "== 2/5 record upstream object ids =="
python scripts/record_upstream_blobs.py

echo "== 3/5 convert each source to P1 =="
python scripts/convert_ihbench.py
python scripts/convert_interruptbench.py
if [ -f scripts/convert_reboot.py ]; then python scripts/convert_reboot.py; fi

echo "== 4/5 merge and validate =="
# Each report has its own path: without --report every run overwrites
# docs/validation_report.txt and only the last source would survive.
python scripts/merge_and_validate.py --merge --require-min-sources 2 --report docs/validation_report.txt
python scripts/merge_and_validate.py --report docs/validation_ihbench.txt processed/ihbench.jsonl
python scripts/merge_and_validate.py --report docs/validation_reboot.txt processed/reboot.jsonl
python scripts/merge_and_validate.py --report docs/validation_interruptbench.txt processed/interruptbench.jsonl

echo "== 5/5 reports =="
python scripts/report_coverage.py
python scripts/inventory_raw.py
python scripts/checksums.py
echo "OK"
