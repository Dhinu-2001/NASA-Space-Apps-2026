"""Verify that the data a running instance needs is present and uncorrupted (exit 0 = ready, 1 = not ready).

Checks, using the engine's own loaders (so the same SHA-256 verification the API performs at load time):
  * the SPICE kernels (checksum-pinned in data/manifests/kernels.json) and the lunar frame set-up,
  * every DEM window listed in data/manifests/dem_windows.json that is present on disk (checksum verified on load),
  * the tracked site catalogue.
A missing window is reported, not fatal, unless --require-all is given: a site without its window is reported by the API as
"terrain data insufficient" (never invented), so a partial install still runs honestly.

Usage: python scripts/verify_data.py [--data DIR] [--require-all]
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

from lunarnav.dem import DemRegistry
from lunarnav.ephemeris import EphemerisService
from lunarnav.errors import LunarNavError
from lunarnav.sites import load_catalogue


def main(argv: list[str]) -> int:
    data = Path(argv[argv.index("--data") + 1]) if "--data" in argv else ROOT / "data"
    require_all = "--require-all" in argv
    ok = True

    try:
        n_sites = len(load_catalogue(data / "catalogue" / "sites.json"))
        print(f"[ok]   site catalogue: {n_sites} sites")
    except Exception as e:  # noqa: BLE001
        print(f"[FAIL] site catalogue: {e}")
        return 1

    try:
        prov = EphemerisService(data).provenance()
        print(f"[ok]   SPICE kernels verified: {', '.join(k['file'] for k in prov['kernels'])}")
    except LunarNavError as e:
        print(f"[FAIL] SPICE kernels: {e.message}")
        ok = False

    manifest = json.loads((data / "manifests" / "dem_windows.json").read_text(encoding="utf-8"))["windows"]
    reg = DemRegistry(data)
    for wid in sorted(manifest):
        f = data / manifest[wid]["file"]
        if not f.exists():
            print(f"[{'FAIL' if require_all else 'warn'}] DEM window {wid}: file missing ({manifest[wid]['file']}); sites it covers will report 'terrain data insufficient'")
            ok = ok and not require_all
            continue
        t = time.time()
        try:
            w = reg.window(wid)
            print(f"[ok]   DEM window {wid}: {w.meta.width}x{w.meta.height} @ {w.meta.pixel_size_m:g} m, checksum verified ({time.time() - t:.1f} s)")
        except LunarNavError as e:
            print(f"[FAIL] DEM window {wid}: {e.message}")
            ok = False
    print("READY" if ok else "NOT READY")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
