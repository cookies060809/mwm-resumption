"""Fetch only the non-audio columns of the IHBench dataset.

Source: https://huggingface.co/datasets/bosonai/IHBench  (license: CC-BY-4.0)

The released `conversations.parquet` embeds 214 MB of user-turn audio in
`user_turn_{t}_audio` columns. Those column chunks are skipped entirely:
everything is read through HTTP Range requests against the parquet footer, so
no waveform bytes are transferred. Only transcript / rubric / workflow-stage
columns (about 1.7 MB) land on disk, as JSON for auditability.
"""

import hashlib
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import write_lf  # noqa: E402
from inspect_remote_parquet import (  # noqa: E402
    TRANSFER_LOG,
    HttpRangeReader,
    _content_length,
)

import pyarrow as pa  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402

MIRROR = "https://hf-mirror.com"
HUB = "https://huggingface.co"
REPO = "datasets/bosonai/ihbench"
AUDIO_RE = re.compile(r"audio")


def resolve(name):
    for base in (MIRROR, HUB):
        url = f"{base}/{REPO}/resolve/main/{name}"
        try:
            _content_length(url)
            return url, base
        except Exception as e:
            print(f"  probe failed {base}: {e}", flush=True)
    raise SystemExit(f"cannot resolve {name}")


def read_text_columns(name, out_json):
    url, base = resolve(name)
    size = _content_length(url)
    reader = HttpRangeReader(url)
    pf = pq.ParquetFile(pa.PythonFile(reader, mode="r"))
    names = pf.schema_arrow.names
    keep = [n for n in names if not AUDIO_RE.search(n)]
    dropped = [n for n in names if n not in keep]
    skipped_bytes = 0
    for rg in range(pf.metadata.num_row_groups):
        g = pf.metadata.row_group(rg)
        for c in range(g.num_columns):
            if AUDIO_RE.search(g.column(c).path_in_schema):
                skipped_bytes += g.column(c).total_compressed_size
    print(f"{name}: {size:,} bytes remote, keeping {len(keep)} cols, "
          f"dropping {len(dropped)} audio cols ({skipped_bytes:,} bytes not transferred)", flush=True)
    rows = []
    for rg in range(pf.metadata.num_row_groups):
        t = pf.read_row_group(rg, columns=keep)
        rows.extend(t.to_pylist())
        print(f"  row group {rg}: {t.num_rows} rows", flush=True)
    write_lf(out_json, json.dumps(rows, ensure_ascii=False, indent=1))
    return {
        "file": name,
        "url": url,
        "resolved_via": base,
        "remote_bytes": size,
        "bytes_actually_transferred": reader.bytes_fetched,
        "http_range_requests": reader.range_requests,
        "audio_bytes_not_downloaded": skipped_bytes,
        "columns_kept": keep,
        "columns_skipped": dropped,
        "rows": len(rows),
        "sha256": hashlib.sha256(out_json.read_bytes()).hexdigest(),
    }


if __name__ == "__main__":
    out = Path("raw/IHBench")
    fetched_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    recs = []
    for name in ("conversations.parquet", "baseline.parquet"):
        recs.append(read_text_columns(name, out / name.replace(".parquet", "_text.json")))
    readme_url, _ = resolve("README.md")
    req = urllib.request.Request(readme_url, headers={"User-Agent": "ecr-mwm"})
    card = (out / "dataset_card.md")
    card.write_bytes(urllib.request.urlopen(req, timeout=60).read())
    recs.append({"file": "README.md", "url": readme_url, "local": str(card),
                 "sha256": hashlib.sha256(card.read_bytes()).hexdigest()})
    manifest = {
        "source_dataset": "IHBench",
        "dataset_id": "bosonai/IHBench",
        "license": "CC-BY-4.0",
        "license_evidence": "HF dataset card frontmatter `license: cc-by-4.0`; repo boson-ai/ihbench LICENSE = Apache-2.0; arXiv:2606.19595 paper page shows CC BY 4.0",
        "gated": False,
        "fetched_at": fetched_at,
        "policy": "audio columns (user_turn_{t}_audio) never transferred; text/rubric/stage columns only",
        "artifacts": recs,
    }
    write_lf(out / "_manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
    print(json.dumps({k: manifest[k] for k in ('license', 'gated')}, ensure_ascii=False))
    for r in recs:
        print(f"  {r.get('file')} rows={r.get('rows','-')} sha256={r['sha256'][:16]}")
