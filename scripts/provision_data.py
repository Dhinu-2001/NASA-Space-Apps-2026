"""Rebuild every piece of data a deployment needs from the official NASA sources (one command).

Steps (each script is resumable and checksum-verified; safe to re-run):
  1. NAIF SPICE kernels            scripts/fetch_kernels.py                (~45 MB, MD5 verified against NAIF's PDS4 labels)
  2. LOLA DEM windows              scripts/extract_dem_window.py <ids>     (range reads from NASA PGDA; ~250 MB in total)
  3. verification                  scripts/verify_data.py
  4. (optional) warm the caches    scripts/warm_cache.py                   (so the first demo views are instant)

The PGDA server is slow and occasionally drops connections: expect 30-60 minutes for the 80 km window and the Chandrayaan-3
window together; interrupted downloads resume. If you already have a data bundle (scripts/pack_data.py), unpack it instead.

Usage: python scripts/provision_data.py [--skip-large] [--no-chandrayaan3] [--warm]
  --skip-large        only the small IM-2/IM-1 windows (about 5 MB); the 80 km IM-2 window and the Chandrayaan-3 window are skipped,
                      so IM-2 results use the 10 km + 320 m windows and Chandrayaan-3 reports 'terrain data insufficient'
  --no-chandrayaan3   skip the 108 MB Chandrayaan-3 window
  --warm              run scripts/warm_cache.py at the end
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
SMALL = ["im2_20m_r10km", "im2_320m_r160km", "im1_20m_r2km"]
LARGE = ["im2_20m_r80km"]
CH3 = ["ch3_60m_r200km"]


def run(label: str, *args: str) -> int:
    print(f"\n=== {label}\n$ {' '.join(args)}", flush=True)
    return subprocess.call([PY, *args], cwd=ROOT)


def main(argv: list[str]) -> int:
    windows = list(SMALL)
    if "--skip-large" not in argv:
        windows += LARGE
        if "--no-chandrayaan3" not in argv:
            windows += CH3
    rc = run("1/4 SPICE kernels", "scripts/fetch_kernels.py")
    if rc:
        return rc
    rc = run("2/4 LOLA DEM windows", "scripts/extract_dem_window.py", *windows)
    if rc:
        print("A window failed; re-run this command to resume where it stopped.")
        return rc
    rc = run("3/4 verification", "-I", "scripts/verify_data.py")
    if rc == 0 and "--warm" in argv:
        rc = run("4/4 warm caches", "-I", "scripts/warm_cache.py")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
