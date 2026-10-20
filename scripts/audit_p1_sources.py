"""Download public annotations into ignored local storage and audit evidence.

This command never labels human mental states or publishes source records.
"""

import argparse
import csv
import json
import re
import subprocess
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mwm_eval.schema import file_hash

HOLO_URL = "https://hl2data.z5.web.core.windows.net/holoassist-data-release/data-annotation-trainval-v1_1.json"
RFM_REPO = "Cornell-Tech-AIRLab/crashcart-rfmhri-dataset"


def download(url, path, limit=160_000_000):
    path = Path(path)
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "MWM-evidence-audit/1.0"})
    temporary = path.with_suffix(path.suffix + ".part")
    total = 0
    try:
        with urllib.request.urlopen(request, timeout=45) as response, temporary.open("wb") as output:
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                total += len(block)
                if total > limit:
                    raise ValueError("source exceeds declared download size limit")
                output.write(block)
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return path


def inspect_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames
        count = sum(1 for _ in reader)
    return {"fields": fields, "rows": count}


def download_holo(path, session_limit=30):
    """Read a bounded prefix of complete sessions using small HTTP ranges.

    The subset is for schema/evidence inspection, not a random evaluation set.
    No hash or count is claimed for the unobserved remainder of the source.
    """
    if path.exists():
        return path
    request = urllib.request.Request(HOLO_URL, headers={"Range": "bytes=0-0", "Connection": "close"})
    with urllib.request.urlopen(request, timeout=20) as response:
        match = re.fullmatch(r"bytes 0-0/(\d+)", response.headers.get("Content-Range", ""))
        if response.status != 206 or not match:
            raise ValueError("publisher did not honor annotation range request")
        total = int(match.group(1))
        etag = response.headers.get("ETag")
        response.read()
    if not 0 < total <= 160_000_000:
        raise ValueError("unexpected annotation source size")
    chunk_size, max_prefix = 65536, min(total, 8 * 1024 * 1024)
    def fetch(start):
        end = min(start + chunk_size, total) - 1
        headers = {"Range": f"bytes={start}-{end}", "Connection": "close"}
        if etag:
            headers["If-Match"] = etag
        request = urllib.request.Request(HOLO_URL, headers=headers)
        with urllib.request.urlopen(request, timeout=20) as response:
            if response.status != 206 or response.headers.get("Content-Range") != f"bytes {start}-{end}/{total}":
                raise ValueError("annotation range response does not match requested interval")
            body = response.read(end - start + 2)
        if len(body) != end - start + 1:
            raise ValueError("truncated annotation chunk")
        return body
    body = bytearray()
    decoder = json.JSONDecoder()
    sessions = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for batch_start in range(0, max_prefix, chunk_size * 16):
            starts = range(batch_start, min(batch_start + chunk_size * 16, max_prefix), chunk_size)
            body.extend(b"".join(pool.map(fetch, starts)))
            source = body.decode("utf-8", errors="ignore")
            index = 1  # official source is a JSON array
            if not source.lstrip().startswith("["):
                raise ValueError("HoloAssist annotation root is not an array")
            index = source.index("[") + 1
            sessions = []
            while len(sessions) < session_limit:
                while index < len(source) and source[index] in " ,\r\n\t":
                    index += 1
                try:
                    value, index = decoder.raw_decode(source, index)
                except json.JSONDecodeError:
                    break  # final object in a prefix may be incomplete
                if not isinstance(value, dict):
                    raise ValueError("annotation session must be an object")
                sessions.append(value)
            print(f"HoloAssist bounded prefix: {len(body)} bytes, {len(sessions)} complete sessions", flush=True)
            if len(sessions) >= session_limit:
                break
    if not sessions:
        raise ValueError("no complete annotation sessions in bounded source prefix")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sessions, ensure_ascii=False) + "\n", encoding="utf-8")
    path.with_suffix(".source.json").write_text(json.dumps({
        "source_bytes": total, "downloaded_prefix_bytes": len(body), "selected_sessions": len(sessions),
        "source_complete": len(body) == total, "source_etag": etag,
        "selection": "first complete sessions in bounded source prefix"}), encoding="utf-8")
    return path


def rfm_tree(cache):
    """Use the public Git tree, without the rate-limited REST API or full blobs."""
    checkout = cache / "rfm/source-tree"
    if not (checkout / ".git").exists():
        checkout.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "-c", "credential.interactive=never", "clone", "--depth=1",
                        "--filter=blob:none", "--no-checkout", f"https://github.com/{RFM_REPO}.git",
                        str(checkout)], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    def git(*args):
        return subprocess.check_output(["git", "-C", str(checkout), *args]).decode("utf-8").strip()
    commit = git("rev-parse", "HEAD")
    return commit, git("ls-tree", "-r", "--name-only", commit).splitlines()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=("holoassist", "rfm", "all"), default="all")
    parser.add_argument("--sample-per-category", type=int, default=5)
    parser.add_argument("--cache", type=Path, default=ROOT / "data/external/raw")
    parser.add_argument("--output", type=Path, default=ROOT / "results/p1_audit/source_inventory.json")
    args = parser.parse_args()
    if args.sample_per_category <= 0:
        parser.error("sample-per-category must be positive")
    report = {"scope": "source evidence audit; not a P1 resumption benchmark",
              "sources": {}, "errors": {}}
    if args.source in {"holoassist", "all"}:
        try:
            path = download_holo(args.cache / "holoassist/annotations_pilot.json")
            data = json.loads(path.read_text(encoding="utf-8"))
            first = next(iter(data.values())) if isinstance(data, dict) else data[0]
            report["sources"]["holoassist"] = {
                "url": HOLO_URL, "subset_sha256": file_hash(path), "subset_bytes": path.stat().st_size,
                **json.loads(path.with_suffix(".source.json").read_text(encoding="utf-8")),
                "root_type": type(data).__name__, "root_count": len(data),
                "root_keys": list(data)[:15] if isinstance(data, dict) else None,
                "first_value_type": type(first).__name__,
                "first_value_fields": list(first)[:25] if isinstance(first, dict) else None,
                "license": "CDLA-Permissive-2.0, per publisher project page",
                "benchmark_status": "candidate extraction and independent review required"}
            print("HoloAssist annotations downloaded and inspected", flush=True)
        except Exception as exc:
            report["errors"]["holoassist"] = f"{type(exc).__name__}: {exc}"
    if args.source in {"rfm", "all"}:
        try:
            commit, files = rfm_tree(args.cache)
            sample_groups = {}
            for name in files:
                parts = name.split("/")
                if len(parts) == 4 and parts[0] == "dataset" and parts[-1] == "meta.json":
                    sample_groups.setdefault(parts[1], []).append("/".join(parts[:3]))
            selected = [s for category in sorted(sample_groups)
                        for s in sorted(sample_groups[category])[:args.sample_per_category]]
            samples = []
            for sample in selected:
                item = {"sample_key": sample, "files": {}}
                for suffix in ("meta.json", "survey.csv", "transcript.txt", "mediapipe/gaze.csv"):
                    relative = sample + "/" + suffix
                    if relative not in files:
                        item["files"][suffix] = {"available": False}
                        continue
                    local = download(f"https://raw.githubusercontent.com/{RFM_REPO}/{commit}/{relative}",
                                     args.cache / "rfm" / relative, limit=8_000_000)
                    entry = {"available": True, "sha256": file_hash(local), "bytes": local.stat().st_size}
                    if suffix.endswith(".csv"):
                        entry.update(inspect_csv(local))
                    elif suffix.endswith(".json"):
                        entry["fields"] = list(json.loads(local.read_text(encoding="utf-8")))
                    else:
                        transcript = local.read_text(encoding="utf-8")
                        entry["nonempty"] = bool(transcript.strip())
                        segments = re.findall(r"\[(\d+(?:\.\d+)?)s[^\]\n]*?(\d+(?:\.\d+)?)s\]", transcript)
                        entry["timestamped_segments"] = len(segments)
                        entry["timestamps_in_seconds"] = bool(segments)
                    item["files"][suffix] = entry
                samples.append(item)
                print(f"RFM source sample inspected: {len(samples)}/{len(selected)}", flush=True)
            report["sources"]["rfm"] = {
                "repository": f"https://github.com/{RFM_REPO}", "commit": commit,
                "n_sample_directories": sum(map(len, sample_groups.values())),
                "category_counts": {k: len(v) for k, v in sorted(sample_groups.items())},
                "n_audited": len(samples), "samples": samples,
                "selection": "lexicographic first N per outcome category; availability audit only",
                "license_files": [p for p in files if "license" in p.lower() or "terms" in p.lower()],
                "benchmark_status": "no direct contemporaneous B/C/Q ground truth established"}
        except Exception as exc:
            report["errors"]["rfm"] = f"{type(exc).__name__}: {exc}"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report["audit_script_sha256"] = file_hash(Path(__file__))
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Audit saved: {args.output}", flush=True)
    if report["errors"]:
        print(json.dumps(report["errors"], ensure_ascii=True), flush=True)
    return int(bool(report["errors"]))


if __name__ == "__main__":
    raise SystemExit(main())
