"""Shared writer for generated delivery files.

Windows text mode rewrites "\n" as "\r\n", which would make the hashes in
docs/CHECKSUMS.sha256 depend on the build host. The repository normalizes to
LF, so generated files are written with LF explicitly.
"""

from pathlib import Path


def write_lf(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
