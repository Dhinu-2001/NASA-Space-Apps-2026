"""Extract small DEM windows from the remote LOLA COG (HTTP range reads; never the whole file).

Writes git-ignored GeoTIFFs to data/dem_cache/ and records provenance + SHA-256 in the tracked
manifest data/manifests/dem_windows.json. Overview-level windows are real LOLA overviews stored
in the COG (we do not resample anything ourselves).

Usage: python scripts/extract_dem_window.py [window_id ...]   (default: all configured windows)
"""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import rasterio
from rasterio.env import Env
from rasterio.windows import Window

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "dem_cache"
MANIFEST = ROOT / "data" / "manifests" / "dem_windows.json"
R = 1_737_400.0

PRODUCT_ID = "LDEM_80S_20MPP_ADJ"
URL = "https://pgda.gsfc.nasa.gov/data/LOLA_20mpp/LDEM_80S_20MPP_ADJ.TIF"

# Site centres are the catalogue coordinates (NAIF kernel values); see data/catalogue/sites.json.
IM2 = (-84.79059, 29.19567)
IM1 = (-80.12759, 1.44587)

# (window_id, centre (lat, lon), half-width metres, overview_level or None)
SPECS = [
    ("im2_20m_r10km", IM2, 10_000.0, None),
    ("im2_320m_r160km", IM2, 160_000.0, 3),  # overview level 3 = factor 16 = 320 m/pixel
    ("im1_20m_r2km", IM1, 2_000.0, None),
    # Stage 4: far field at full 20 m resolution (no area-averaging) out to 80 km, ~190 MB download.
    ("im2_20m_r80km", IM2, 80_000.0, None),
]


def lonlat_to_xy(lat: float, lon: float) -> tuple[float, float]:
    rho = 2 * R * math.tan(math.radians(lat + 90) / 2)
    return rho * math.sin(math.radians(lon)), rho * math.cos(math.radians(lon))


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def extract(window_id: str, centre: tuple[float, float], half_m: float, overview: int | None):
    cx, cy = lonlat_to_xy(*centre)
    kwargs = {"overview_level": overview} if overview is not None else {}
    with rasterio.open(URL, **kwargs) as ds:
        res = ds.res[0]
        n = round(2 * half_m / res)
        col0 = math.floor((cx - ds.bounds.left) / res - n / 2 + 0.5)
        row0 = math.floor((ds.bounds.top - cy) / res - n / 2 + 0.5)
        win = Window(col0, row0, n, n)
        if col0 < 0 or row0 < 0 or col0 + n > ds.width or row0 + n > ds.height:
            raise RuntimeError(f"{window_id}: window exceeds the raster bounds")
        transform = ds.window_transform(win)
    # Strips are read over a *fresh* connection each, checkpointed to disk, and retried: a dropped
    # connection costs one strip, and a re-run resumes where it stopped. (A single dataset handle that
    # has seen an HTTP error was observed to stay broken, so it is never reused after a failure.)
    part = CACHE / f"{window_id}.partial"
    part.mkdir(parents=True, exist_ok=True)
    data = np.empty((n, n), dtype=np.float32)
    strip = 250
    for r in range(0, n, strip):
        h = min(strip, n - r)
        f = part / f"strip_{r:05d}.npy"
        if f.exists():
            try:
                data[r : r + h] = np.load(f)
                continue
            except Exception:  # noqa: BLE001  (corrupt checkpoint: re-read it)
                f.unlink()
        for attempt in range(10):
            try:
                with rasterio.open(URL, **kwargs) as ds:
                    block = ds.read(1, window=Window(col0, row0 + r, n, h)).astype(np.float32)
                data[r : r + h] = block
                np.save(f, block)
                break
            except Exception as e:
                if attempt == 9:
                    raise
                print(f"  strip {r}: attempt {attempt + 1} failed ({type(e).__name__}); retrying", flush=True)
                time.sleep(10)
        if n > 2000:
            print(f"  strip {r + h}/{n} rows done", flush=True)
    with rasterio.open(URL, **kwargs) as ds:
        crs = ds.crs
    profile = {
        "driver": "GTiff", "dtype": "float32", "count": 1, "width": n, "height": n,
        "crs": crs, "transform": transform, "nodata": float("nan"),
        "compress": "deflate", "predictor": 3, "tiled": True,
        "blockxsize": 256, "blockysize": 256,
    }
    CACHE.mkdir(parents=True, exist_ok=True)
    out = CACHE / f"{window_id}.tif"
    with rasterio.open(out, "w", **profile) as dst:
        dst.write(data, 1)
        dst.update_tags(
            SOURCE_URL=URL, PRODUCT_ID=PRODUCT_ID, OVERVIEW_LEVEL=str(overview),
            NOTE="Extracted by scripts/extract_dem_window.py; heights in metres above the "
            "1737.4 km sphere; NoData=NaN",
        )
    shutil.rmtree(part, ignore_errors=True)  # checkpoints are only needed until the window is assembled
    valid = np.isfinite(data)
    left, top = transform.c, transform.f
    entry = {
        "product_id": PRODUCT_ID,
        "file": f"dem_cache/{window_id}.tif",
        "sha256": sha256_file(out),
        "size_bytes": out.stat().st_size,
        "source_url": URL,
        "overview_level": overview,
        "pixel_size_m": res,
        "left_m": left, "top_m": top, "width": n, "height": n,
        "right_m": left + n * res, "bottom_m": top - n * res,
        "centre_lat_deg": centre[0], "centre_lon_deg_east": centre[1],
        "valid_fraction": float(valid.mean()),
        "z_min_m": float(np.nanmin(data)) if valid.any() else None,
        "z_max_m": float(np.nanmax(data)) if valid.any() else None,
        "crs_wkt": crs.to_wkt(),
        "units": "metres above 1737.4 km reference sphere",
        "nodata": "NaN",
        "extracted_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "rasterio": rasterio.__version__, "gdal": rasterio.__gdal_version__,
    }
    return entry, data, (col0, row0)


def main(argv: list[str]) -> int:
    wanted = set(argv) or {s[0] for s in SPECS}
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {"windows": {}}
    manifest["manifest_note"] = (
        "Each window is a real extract of the cited LOLA product; files live in data/dem_cache "
        "(git-ignored). Regenerate with scripts/extract_dem_window.py."
    )
    env = Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".TIF",
              GDAL_HTTP_MAX_RETRY="6", GDAL_HTTP_RETRY_DELAY="3", GDAL_HTTP_TIMEOUT="180")
    ok = True
    with env:
        for wid, centre, half, ov in SPECS:
            if wid not in wanted:
                continue
            t0 = time.time()
            print(f"[{wid}] extracting ...", flush=True)
            try:
                entry, _data, _ = extract(wid, centre, half, ov)
                manifest["windows"][wid] = entry
                MANIFEST.parent.mkdir(parents=True, exist_ok=True)
                MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
                print(f"  ok {entry['width']}x{entry['height']} @ {entry['pixel_size_m']} m, "
                      f"valid={entry['valid_fraction']:.4f}, "
                      f"z=[{entry['z_min_m']:.1f},{entry['z_max_m']:.1f}] m, "
                      f"{entry['size_bytes']/1e6:.2f} MB, {time.time()-t0:.0f}s", flush=True)
            except Exception as e:  # noqa: BLE001
                ok = False
                print(f"  FAILED: {type(e).__name__}: {e}", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
