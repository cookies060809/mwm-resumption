"""Record upstream object ids for the staged InterruptBench annotation files.

Two fetch paths are legitimate for this source and each leaves a different
provenance record:

  * `scripts/fetch_github_paths.py` (Contents API) writes `_manifest.json`
    entries carrying the git blob sha of the exact object it downloaded;
  * a `codeload.github.com` tarball extract has no per-file record, so the blob
    sha comes from `raw/InterruptBench/_upstream_tree_subset.json`, the
    frozen repo-tree listing that ships with this delivery.

This script merges both into `raw/InterruptBench/_upstream_blobs.json`,
re-hashes every staged file locally, and lists staged files that have no
upstream object id (locally generated sidecars are excluded) so the inventory
never hides a gap.
"""

import hashlib
import json
import time
from pathlib import Path

from common import write_lf

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "raw" / "InterruptBench"
OUT = DIR / "_upstream_blobs.json"


def repo_key(local_rel: str) -> str:
    """Staged tree mirrors the repo layout under Eval/ (see docs/source_manifest.md)."""
    rel = local_rel.replace("\\", "/")
    if rel.startswith("Eval/"):
        return rel
    if rel.startswith("config_files_wa/"):
        return "Eval/config_files/wa/" + rel[len("config_files_wa/") :]
    return "Eval/" + rel


def main():
    # object ids come from two records, both keyed by the repo path: the frozen
    # tree-API subset that ships with the delivery, and the Contents-API manifest
    # written by fetch_github_paths.py when that path is used instead
    upstream = {}
    subset = DIR / "_upstream_tree_subset.json"
    if subset.exists():
        upstream.update(json.loads(subset.read_text(encoding="utf-8")).get("blobs", {}))

    mf = DIR / "_manifest.json"
    if mf.exists():
        raw = json.loads(mf.read_text(encoding="utf-8"))
        # fetch_github_paths.py writes a bare list; keep accepting a wrapped dict too
        artifacts = raw if isinstance(raw, list) else raw.get("artifacts", [])
        for a in artifacts:
            if a.get("path_in_repo") and a.get("sha"):
                upstream[a["path_in_repo"]] = a["sha"]

    files, untracked = [], []
    for f in sorted(p for p in DIR.rglob("*") if p.is_file()):
        rel = f.relative_to(DIR).as_posix()
        if rel.startswith("_"):
            continue  # locally generated sidecar
        key = repo_key(rel)
        rec = {
            "local_path": rel,
            "path_in_repo": key,
            "bytes": f.stat().st_size,
            "sha256": hashlib.sha256(f.read_bytes()).hexdigest(),
        }
        if upstream.get(key):
            rec["git_blob_sha"] = upstream[key]
        else:
            untracked.append(rel)
        files.append(rec)

    out = {
        "repo": "HenryPengZou/InterruptBench",
        "ref": "main",
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "tree_api_capture_url": "https://api.github.com/repos/HenryPengZou/InterruptBench/git/trees/HEAD?recursive=1",
        "license_note": (
            "Eval/LICENSE is MIT with the upstream VisualWebArena author copyright; the repo root "
            "carries no LICENSE and GitHub reports license=null. See docs/source_manifest.md §1.2."
        ),
        "files": files,
        "staged_without_upstream_object_id": untracked,
    }
    write_lf(OUT, json.dumps(out, indent=1, ensure_ascii=False))
    print(
        f"{len(files)} staged files, {len(files) - len(untracked)} mapped to a git blob sha, "
        f"{len(untracked)} unmapped -> {OUT.relative_to(ROOT)}"
    )


if __name__ == "__main__":
    main()
