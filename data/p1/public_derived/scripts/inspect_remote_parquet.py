"""Inspect / slice a remote Parquet file through HTTP Range requests only.

Used so that column chunks holding embedded audio bytes are never transferred:
the footer is fetched, then only the requested columns are pulled.
"""

import sys
import time
import urllib.request

import pyarrow as pa
import pyarrow.parquet as pq

UA = "ecr-mwm-annotation-fetch"

# Audit counter: every byte that actually crossed the wire is recorded here,
# so the fetcher can prove which heavy columns were never downloaded.
TRANSFER_LOG = []


def _range(url, start, end):
    req = urllib.request.Request(url, headers={"Range": f"bytes={start}-{end}", "User-Agent": UA})
    last = None
    for attempt in range(8):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                data = r.read()
                TRANSFER_LOG.append((url, start, end, len(data)))
                return data
        except Exception as e:  # flaky DNS / resets on this host
            last = e
            time.sleep(2 + 3 * attempt)
    raise RuntimeError(f"range fetch failed {start}-{end}: {last}")


def _content_length(url):
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return int(r.headers["Content-Length"])


class HttpRangeReader:
    """Minimal random-access file object for pyarrow.PythonFile."""

    mode = "rb"

    def __init__(self, url):
        self.url = url
        self.pos = 0
        self.closed = False
        self.bytes_fetched = 0
        self.range_requests = 0
        self._size = _content_length(url)
        self._span = None  # (start, end_exclusive, bytes) last fetched span

    def size(self):
        return self._size

    def seek(self, offset, whence=0):
        self.pos = offset if whence == 0 else (self.pos + offset if whence == 1 else self._size + offset)

    def tell(self):
        return self.pos

    def read(self, nbytes=-1):
        end = self._size if nbytes < 0 else min(self.pos + nbytes, self._size)
        if end <= self.pos:
            return b""
        data = self.readat(end - self.pos, self.pos)
        self.pos = end
        return data

    def readat(self, nbytes, offset):
        end = min(offset + nbytes, self._size)
        if self._span and self._span[0] <= offset and end <= self._span[1]:
            return self._span[2][offset - self._span[0] : end - self._span[0]]
        data = _range(self.url, offset, end - 1)
        self.bytes_fetched += len(data)
        self.range_requests += 1
        self._span = (offset, end, data)
        return data

    def readable(self):
        return True

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def open_remote(url):
    return pq.ParquetFile(pa.PythonFile(HttpRangeReader(url), mode="r"))


def audio_column_bytes(md):
    total = 0
    for rg in range(md.metadata.num_row_groups):
        g = md.metadata.row_group(rg)
        for c in range(g.num_columns):
            if "audio" in g.column(c).path_in_schema:
                total += g.column(c).total_compressed_size
    return total


if __name__ == "__main__":
    url = sys.argv[1]
    md = open_remote(url)
    print("rows:", md.metadata.num_rows, "row_groups:", md.metadata.num_row_groups, "cols:", md.metadata.num_columns)
    print("schema fields:", len(md.schema_arrow.names))
    print(md.schema_arrow)
    by_col = {}
    for rg in range(md.metadata.num_row_groups):
        g = md.metadata.row_group(rg)
        for c in range(g.num_columns):
            col = g.column(c)
            e = by_col.setdefault(col.path_in_schema, [0, 0])
            e[0] += col.total_compressed_size
            e[1] += 1
    text = sum(v[0] for k, v in by_col.items() if "audio" not in k)
    print(f"\nnon-audio bytes: {text:,}   audio bytes: {audio_column_bytes(md):,}   remote: {_content_length(url):,}")
    print("\nlargest columns:")
    for k, (b, n) in sorted(by_col.items(), key=lambda kv: -kv[1][0])[:15]:
        print(f"  {b:>12,} chunks={n:<3} {k}")
