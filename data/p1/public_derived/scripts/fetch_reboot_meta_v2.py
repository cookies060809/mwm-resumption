"""Download REBOOT annotation metadata (meta/*) for the given repos.

Fetches only `meta/phase.json`, `meta/info.json` and `meta/tasks.parquet`.
`data/*.parquet` (frame trajectories) and `videos/` are never requested, which is
what keeps the annotation-only footprint under a megabyte per repo.

Usage: python scripts/fetch_reboot_meta_v2.py [repo ...]
"""

import hashlib
import json
import sys
import time
import urllib.request
from pathlib import Path

from common import write_lf

BASES = ["https://hf-mirror.com", "https://huggingface.co"]
UA = "ecr-mwm-annotation-fetch"
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "raw" / "REBOOT"
DEFAULT_REPOS = ["REBOOT26/sample_recovery-demonstration"]
WANTED = ["meta/phase.json", "meta/info.json", "meta/tasks.parquet"]


def get(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def fetch_rel(repo, rel, tries=6):
    for attempt in range(tries):
        for base in BASES:
            url = f"{base}/datasets/{repo}/resolve/main/{rel}"
            try:
                return url, get(url)
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return None, None  # genuinely absent
                time.sleep(3 + 3 * attempt)
            except Exception:
                time.sleep(3 + 3 * attempt)
    raise RuntimeError(f"unreachable: {repo}/{rel}")


def main():
    repos = sys.argv[1:] or DEFAULT_REPOS
    OUT.mkdir(parents=True, exist_ok=True)
    records = []
    for repo in repos:
        slug = repo.split("/", 1)[1]
        for rel in WANTED:
            try:
                url, data = fetch_rel(repo, rel)
            except RuntimeError as e:
                print(f"  FAIL {repo}/{rel}: {e}", flush=True)
                continue
            if data is None:
                print(f"  absent {repo}/{rel}", flush=True)
                continue
            dest = OUT / slug / Path(rel).name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            records.append(
                {
                    "repo": repo,
                    "path_in_repo": rel,
                    "url": url,
                    "local_path": str(dest.relative_to(ROOT).as_posix()),
                    "bytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                }
            )
            print(f"  ok {len(data):,} B {repo}/{rel}", flush=True)
    man = OUT / "_manifest.json"
    prev = json.loads(man.read_text(encoding="utf-8")) if man.exists() else {"artifacts": []}
    # A re-fetch of the same path must replace its record, not delete it: matching
    # on identity (sha256) proves the upstream bytes are unchanged, a mismatch is
    # reported as upstream drift instead of silently overwriting the audit trail.
    fresh = {r["local_path"]: r for r in records}
    drift = [
        r["local_path"] for r in prev["artifacts"]
        if r["local_path"] in fresh
        and (r["sha256"] != fresh[r["local_path"]]["sha256"] or r["bytes"] != fresh[r["local_path"]]["bytes"])
    ]
    kept = [r for r in prev["artifacts"] if r["local_path"] not in fresh]
    replaced = [
        {**fresh[r["local_path"]], "verified_against_previous": r["sha256"] == fresh[r["local_path"]]["sha256"]}
        for r in prev["artifacts"] if r["local_path"] in fresh
    ]
    new_only = [r for r in records if r["local_path"] not in {p["local_path"] for p in prev["artifacts"]}]
    prev["artifacts"] = kept + replaced + new_only
    if drift:
        print(f"UPSTREAM DRIFT (sha256 changed): {drift}", file=sys.stderr)
    prev.update(
        {
            "source_dataset": "REBOOT",
            "org": "REBOOT26",
            "license": "Apache-2.0 (per-repo HF tag `license:apache-2.0`; project page states CC-BY-4.0)",
            "gated": False,
            "policy": "meta/phase.json + meta/info.json + meta/tasks.parquet only; data/*.parquet trajectories and videos/ never requested",
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
    )
    write_lf(man, json.dumps(prev, indent=2, ensure_ascii=False))
    print(f"manifest -> {man} ({len(prev['artifacts'])} artifacts, {sum(a['bytes'] for a in prev['artifacts']):,} B)")


if __name__ == "__main__":
    main()
