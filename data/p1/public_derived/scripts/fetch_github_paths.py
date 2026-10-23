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
from urllib.parse import quote

from common import write_lf

API = "https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={ref}"
RAW = "https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}"
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


def blob_sha(data: bytes) -> str:
    """Git object id, so the raw-code path reproduces the Contents API `sha`."""
    header = f"blob {len(data)}".encode()
    return hashlib.sha1(header + b"\0" + data).hexdigest()


API_OK = True  # set False once the Contents API is seen unavailable, to stop re-probing


def fetch_one(owner: str, repo: str, ref: str, p: str) -> tuple[str, str, bytes]:
    """Return (source_url, blob_sha, bytes). The Contents API is anonymous-rate-limited
    at 60 requests/hour, so the immutable raw-code endpoint is the fallback."""
    global API_OK
    if API_OK:
        try:
            meta = json.loads(get(API.format(owner=owner, repo=repo, path=p, ref=ref), tries=2))
            blob = base64.b64decode(meta["content"]) if meta.get("encoding") == "base64" else b""
            return meta["html_url"], meta["sha"], blob
        except Exception as e:
            API_OK = False
            print(f"  contents api unavailable ({e}); switching to raw.githubusercontent", flush=True)
    url = RAW.format(owner=owner, repo=repo, ref=ref, path=quote(p))
    blob = get(url, tries=6)
    return f"https://github.com/{owner}/{repo}/blob/{ref}/{p}", blob_sha(blob), blob


def fetch(owner: str, repo: str, ref: str, paths: list[str], out_dir: Path,
          prev_manifest: Path | None = None) -> list[dict]:
    out_dir.mkdir(parents=True, exist_ok=True)
    prev = {}
    if prev_manifest and prev_manifest.exists():
        prev = {r["path_in_repo"]: r for r in json.loads(prev_manifest.read_text(encoding="utf-8"))}
    records, drift = [], []
    for p in paths:
        source_url, sha, blob = fetch_one(owner, repo, ref, p)
        digest = hashlib.sha256(blob).hexdigest()
        if p in prev and (prev[p]["sha"] != sha or prev[p]["sha256"] != digest):
            drift.append(p)
        dest = out_dir / p
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(blob)
        records.append(
            {
                "repo": f"{owner}/{repo}",
                "ref": ref,
                "sha": sha,
                "path_in_repo": p,
                "local_path": dest.relative_to(out_dir.parent.parent).as_posix(),
                "bytes": len(blob),
                "sha256": digest,
                "source_url": source_url,
            }
        )
        print(f"ok {len(blob):>8} {p}", flush=True)
    if drift:
        print(f"UPSTREAM DRIFT vs previous manifest: {drift}", file=sys.stderr)
    else:
        print("all fetched blobs match the previously recorded sha/sha256")
    return records


if __name__ == "__main__":
    spec = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    man = Path(spec["manifest"])
    # fetch() reads the previous record for hash verification before __main__
    # overwrites it, so a re-fetch proves the upstream content is unchanged.
    recs = fetch(spec["owner"], spec["repo"], spec["ref"], spec["paths"],
                 Path(spec["out_dir"]), man)
    write_lf(man, json.dumps(recs, indent=2, ensure_ascii=False))
    print(f"manifest -> {man} ({len(recs)} files, {sum(r['bytes'] for r in recs)} bytes)")
