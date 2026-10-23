"""Write docs/CHECKSUMS.sha256 for the delivered artifacts."""

import hashlib
from pathlib import Path

from common import write_lf

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "CHECKSUMS.sha256"

GROUPS = {
    "delivery": ["processed/*.jsonl", "docs/*.json"],
    "audit docs": ["docs/*.md", "docs/*.txt", "README.md"],
    "code": ["scripts/*.py", "run_pipeline.sh", "scripts/*.json"],
    "raw annotations": ["raw/*/*.json", "raw/*/*.md"],
}


def main():
    lines = ["# SHA-256 of delivered artifacts (regenerate with `python scripts/checksums.py`)"]
    count = 0
    for group, patterns in GROUPS.items():
        lines.append(f"\n## {group}\n")
        for pat in patterns:
            for f in sorted(ROOT.glob(pat)):
                if f == OUT:
                    continue
                h = hashlib.sha256(f.read_bytes()).hexdigest()
                lines.append(f"{h}  {f.relative_to(ROOT).as_posix()}  {f.stat().st_size:,} B")
                count += 1
    write_lf(OUT, "\n".join(lines) + "\n")
    print(f"{count} files hashed -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
