"""Build docs/raw_inventory.md: every raw file actually used, with hashes.

For InterruptBench the upstream git blob sha comes from
`raw/InterruptBench/_upstream_blobs.json`, captured from
https://api.github.com/repos/HenryPengZou/InterruptBench/git/trees/HEAD?recursive=1
so each staged file maps to an exact object in the public repo. For IHBench the
parquet is addressed by its HuggingFace commit sha plus the local text
extraction's sha256.
"""

import hashlib
import json
from pathlib import Path

from common import write_lf

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "raw"
OUT = ROOT / "docs" / "raw_inventory.md"

IB_BLOB_SHA = {}
IB_UNTRACKED = []
ib_meta_path = RAW / "InterruptBench" / "_upstream_blobs.json"
if ib_meta_path.exists():
    meta = json.loads(ib_meta_path.read_text(encoding="utf-8"))
    for m in meta["files"]:
        if m.get("git_blob_sha"):
            IB_BLOB_SHA[m["local_path"]] = m["git_blob_sha"]
    IB_UNTRACKED = meta.get("staged_without_upstream_object_id", [])

lines = [
    "# Raw annotation inventory",
    "",
    "Files that the P1 builders read. Nothing else from either source was kept;",
    "media paths (repo images, IHBench audio columns) were excluded at fetch time.",
    "",
    "Git versions only the provenance manifests, so on a fresh clone the upstream",
    "annotation bodies below are absent until `run_pipeline.sh` re-fetches them.",
    "The complete fetch record (bytes + sha256 per file) is in `raw/*/_manifest.json`.",
    "",
]


def sha256(b):
    return hashlib.sha256(b).hexdigest()


def section(title, files, upstream):
    lines.append(f"## {title}")
    lines.append("")
    lines.append("| local path | bytes | sha256 | upstream |")
    lines.append("|---|---:|---|---|")
    total = 0
    for f in files:
        rel = f.relative_to(RAW).as_posix()
        b = f.read_bytes()
        total += len(b)
        up = ""
        if upstream == "github":
            sub = rel.split("InterruptBench/", 1)[1]
            sha = IB_BLOB_SHA.get(sub)
            if sha:
                up = f"git blob `{sha[:12]}`"
            elif sub.startswith("_"):
                up = "locally generated sidecar"
            else:
                up = "n/a"
        lines.append(f"| `{rel}` | {len(b):,} | `{sha256(b)[:16]}…` | {up} |")
    lines.append("")
    lines.append(f"Total: **{total:,} bytes** across {len(files)} files.")
    if IB_UNTRACKED and upstream == "github":
        lines.append("")
        lines.append("Staged without an upstream object id: " + ", ".join(f"`{u}`" for u in IB_UNTRACKED))
    lines.append("")


ib = sorted((RAW / "InterruptBench").rglob("*"), key=lambda x: x.as_posix())
ib = [f for f in ib if f.is_file()]
section("InterruptBench (github.com/HenryPengZou/InterruptBench @ main)", ib, "github")

ih = sorted((RAW / "IHBench").glob("*"), key=lambda x: x.name)
ih = [f for f in ih if f.is_file()]
mf = json.loads((RAW / "IHBench" / "_manifest.json").read_text(encoding="utf-8"))
art = {a["file"]: a for a in mf["artifacts"]}
lines.append("## IHBench (huggingface.co/datasets/bosonai/IHBench, commit cbd8280ab59bc4a50c48cbe0511a307fba9945cf)")
lines.append("")
lines.append("| local path | bytes | sha256 | remote file | bytes transferred | audio bytes NOT downloaded |")
lines.append("|---|---:|---|---|---:|---:|")
name_map = {
    "conversations_text.json": "conversations.parquet",
    "baseline_text.json": "baseline.parquet",
    "dataset_card.md": "README.md",
    "_manifest.json": None,
}
tot_tr = 0
for f in ih:
    remote = name_map.get(f.name) or ""
    a = art.get(remote, {})
    b = f.read_bytes()
    tr = a.get("bytes_actually_transferred")
    skipped = a.get("audio_bytes_not_downloaded")
    tot_tr += tr or 0
    lines.append(
        f"| `{f.name}` | {len(b):,} | `{sha256(b)[:16]}…` | {remote or '–'} | "
        f"{format(tr, ',') if tr else '–'} | {format(skipped, ',') if skipped else '–'} |"
    )
lines.append("")
lines.append(
    f"Total bytes that crossed the wire for IHBench: **{tot_tr:,}** "
    f"(of {sum(a.get('remote_bytes', 0) for a in art.values()):,} bytes of remote parquet), "
    f"with {art.get('conversations.parquet', {}).get('audio_bytes_not_downloaded', 0):,} audio bytes never requested."
)
lines.append("")
rb = RAW / "REBOOT"
if (rb / "_manifest.json").exists():
    rbman = json.loads((rb / "_manifest.json").read_text(encoding="utf-8"))
    lines.append("")
    lines.append("## REBOOT (huggingface.co/datasets/REBOOT26/sample_recovery-demonstration)")
    lines.append("")
    lines.append("| local path | bytes | sha256 | url |")
    lines.append("|---|---:|---|---|")
    rb_total = 0
    rb_fetched = 0
    for a in rbman.get("artifacts", []):
        f = ROOT / a["local_path"]
        on_disk = f.is_file()
        recorded = a.get("bytes") or (f.stat().st_size if on_disk else 0)
        rb_fetched += recorded
        if on_disk:
            rb_total += f.stat().st_size
        lines.append(
            f"| `{a['local_path']}` | {recorded:,} | `{a['sha256'][:16]}…` | {a['url']} |"
            + ("" if on_disk else " *(recorded in manifest, not kept locally)*")
        )
    lines.append("")
    lines.append(
        f"Total: **{rb_fetched:,} bytes** fetched ({rb_total:,} still present locally). "
        "`data/*.parquet` (frame trajectories) and `videos/` were never "
        "requested - only `meta/` annotation files. An org-wide scan found `meta/phase.json` in 1 of 38 "
        "repos (docs/source_manifest.md §2.2)."
    )

lines.append("")
lines.append(f"Generated by `scripts/inventory_raw.py`. IHBench fetched_at={mf['fetched_at']}; "
             f"REBOOT fetched_at={rbman.get('fetched_at') if (rb / '_manifest.json').exists() else 'n/a'}.")

write_lf(OUT, "\n".join(lines) + "\n")
print(f"wrote {OUT.relative_to(ROOT)} ({len(ib)} + {len(ih)} files)")
