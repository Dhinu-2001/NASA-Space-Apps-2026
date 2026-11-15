"""Size caps for the on-disk result caches (data/results/*).

The caches are an optimisation only (every entry is regenerable and keyed by its inputs, the model version and the DEM
checksums), but on a public deployment unique requests would otherwise grow them without bound. Entries are evicted
least-recently-used: a cache hit refreshes the file's modification time, so frequently served (e.g. warmed demo)
entries survive. No science is involved here: only file housekeeping.
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path

MAX_CACHED_SCENARIOS = 1000   # JSON results, roughly 100 KB each
MAX_CACHED_HORIZONS = 3000    # compressed npz profiles, tens of KB each


def touch(path: Path) -> None:
    """Mark a cache entry as recently used."""
    with contextlib.suppress(OSError):
        os.utime(path, None)


def trim_oldest(directory: Path, pattern: str, keep: int) -> int:
    """Delete the least recently used files matching `pattern` until at most `keep` remain. Returns how many were removed."""
    try:
        files = [(p.stat().st_mtime, p) for p in directory.glob(pattern) if p.is_file() and ".tmp" not in p.name]   # never touch another writer's in-progress temp file
    except OSError:
        return 0
    excess = len(files) - keep
    if excess <= 0:
        return 0
    removed = 0
    for _, p in sorted(files, key=lambda t: t[0])[:excess]:
        try:
            p.unlink()
            removed += 1
        except OSError:
            pass  # another worker may have removed it; the cache stays a best-effort optimisation
    return removed
