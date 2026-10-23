"""Find every REBOOT26 repo that ships `meta/phase.json` episode annotations.

The org has ~38 datasets; most are plain LeRobot recordings (meta/ holds only
info/stats/tasks). This scan reads each repo's file listing and records which
ones carry the phase/failure/recovery annotation file, so the converter is built
against the real coverage rather than one sample repo.
"""

import json
import sys
import time
import urllib.request
from pathlib import Path

BASES = ["https://hf-mirror.com", "https://huggingface.co"]
UA = "ecr-mwm-annotation-fetch"
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT.parent / "_recon" / "reboot"


def get(url, timeout=45):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def with_retry(url, tries=5):
    last = None
    for attempt in range(tries):
        for base in BASES:
            try:
                return get(url.replace("{base}", base))
            except Exception as e:
                last = e
                time.sleep(2 + 2 * attempt)
    print(f"    unreachable {url}: {type(last).__name__}", flush=True)
    return None


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cached = OUT / "org_datasets.json"
    raw = with_retry("{base}/api/datasets?author=REBOOT26&limit=100")
    if raw:
        cached.write_bytes(raw)
    repos = json.loads(cached.read_text(encoding="utf-8"))
    ids = [r["id"] for r in repos]
    print(f"org repos: {len(ids)}")
    hits, misses, errors = [], [], []
    for rid in ids:
        meta = with_retry(f"{{base}}/api/datasets/{rid}")
        if not meta:
            errors.append(rid)
            continue
        j = json.loads(meta)
        files = [s["rfilename"] for s in j.get("siblings", [])]
        phase = [f for f in files if f.endswith("phase.json")]
        rec = {"repo": rid, "n_files": len(files), "phase_files": phase,
               "license": [t for t in j.get("tags", []) if t.startswith("license")],
               "gated": j.get("gated"), "private": j.get("private")}
        if phase:
            hits.append(rec)
            print(f"  PHASE  {rid:46s} {phase}")
        else:
            misses.append(rec)
            print(f"  -      {rid:46s} ({len(files)} files)")
    (OUT / "phase_repos.json").write_text(
        json.dumps({"with_phase": hits, "without_phase": misses, "errors": errors}, indent=1),
        encoding="utf-8",
    )
    print(f"\nwith meta/phase.json: {len(hits)} | without: {len(misses)} | unreachable: {len(errors)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
