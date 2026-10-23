"""Fetch selected text annotation files from a GitHub repo via the Contents API.

Only JSON / CSV / MD / PY / LICENSE text blobs are fetched. Media paths
(images, audio, video) are excluded by the caller's manifest, never downloaded.
"""

import base64
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from common import write_lf

API = "https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={ref}"
UA = "ECR-MWM build agent (public annotation fetch)"


def get(url: str, tries: int = 6) -> bytes:
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/vnd.github+json"})
            with urllib.request.urlopen(req, timeout=90) as r:
                return r.read()
        except Exception as e:  # transient DNS/reset on this host
            last = e
            time.sleep(2 + 4 * attempt)
    raise RuntimeError(f"failed {url}: {last}")


def fetch(owner: str, repo: str, ref: str, paths: list[str], out_dir: Path) -> list[dict]:
    out_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for p in paths:
        raw = get(API.format(owner=owner, repo=repo, path=p, ref=ref))
        meta = json.loads(raw)
        blob = base64.b64decode(meta["content"]) if meta.get("encoding") == "base64" else b""
        dest = out_dir / p
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(blob)
        records.append(
            {
                "repo": f"{owner}/{repo}",
                "ref": ref,
                "sha": meta["sha"],
                "path_in_repo": p,
                "local_path": str(dest.relative_to(out_dir.parent.parent)),
                "bytes": len(blob),
                "sha256": hashlib.sha256(blob).hexdigest(),
                "source_url": meta["html_url"],
            }
        )
        print(f"ok {len(blob):>8} {p}", flush=True)
    return records


if __name__ == "__main__":
    spec = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    recs = fetch(spec["owner"], spec["repo"], spec["ref"], spec["paths"], Path(spec["out_dir"]))
    write_lf(Path(spec["manifest"]), json.dumps(recs, indent=2, ensure_ascii=False))
    print(f"manifest -> {spec['manifest']} ({len(recs)} files, {sum(r['bytes'] for r in recs)} bytes)")
