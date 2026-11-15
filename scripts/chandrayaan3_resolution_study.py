"""How much does the Chandrayaan-3 horizon depend on pixel size? (analogue of scripts/horizon_resolution_study.py)

Reference = the registered 60 m window (ch3_60m_r200km). Coarser data = the provider's own overviews of the same
COG (120/240/480 m, area-averaged by the provider), read over HTTP range requests for the same 200 km square.
Nothing here is registered or used by the engine; it only measures the sensitivity of the horizon to pixel size.

Usage: python -I scripts/chandrayaan3_resolution_study.py   -> docs/stage4/chandrayaan3_resolution_study.json
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.env import Env
from rasterio.windows import Window

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

from lunarnav.dem import DemRegistry, DemWindow, DemWindowMeta
from lunarnav.horizon import TerrainSampler, compute_horizon

URL = "https://pgda.gsfc.nasa.gov/data/LOLA_20mpp/LDEM_60S_60MPP_ADJ.TIF"
LAT, LON, H_OBS, HALF = -69.3741, 32.32, 2.0, 200_000.0
R = 1_737_400.0


def overview_window(level: int) -> DemWindow:
    rho = 2 * R * math.tan(math.radians(LAT + 90) / 2)
    cx, cy = rho * math.sin(math.radians(LON)), rho * math.cos(math.radians(LON))
    with rasterio.open(URL, overview_level=level) as ds:
        res = ds.res[0]
        n = round(2 * HALF / res)
        col0 = math.floor((cx - ds.bounds.left) / res - n / 2 + 0.5)
        row0 = math.floor((ds.bounds.top - cy) / res - n / 2 + 0.5)
        data = ds.read(1, window=Window(col0, row0, n, n)).astype(np.float32)
        tr = ds.window_transform(Window(col0, row0, n, n))
    meta = DemWindowMeta(
        window_id=f"ch3_ov{level}", product_id="LDEM_60S_60MPP_ADJ", file="-", sha256="-", pixel_size_m=res,
        left_m=tr.c, top_m=tr.f, width=n, height=n, valid_fraction=float(np.isfinite(data).mean()),
        z_min_m=float(np.nanmin(data)), z_max_m=float(np.nanmax(data)), source_url=URL, overview_level=level, raw={})
    return DemWindow(meta, data)


def main() -> None:
    reg = DemRegistry(ROOT / "data")
    ref_w = reg.window("ch3_60m_r200km")
    cap = ref_w.meta.z_max_m
    kw = {"az_step_deg": 0.5, "unseen_terrain_max_height_m": 7027.2294921875}
    ref = compute_horizon(TerrainSampler([ref_w]), LAT, LON, H_OBS, **kw)
    out = {"site": {"lat": LAT, "lon": LON, "observer_height_m": H_OBS}, "reference": "ch3_60m_r200km (60 m)",
           "reference_horizon_deg": {"min": float(ref.horizon_elevation_deg.min()), "max": float(ref.horizon_elevation_deg.max()),
                                     "mean": float(ref.horizon_elevation_deg.mean())},
           "reference_window_max_height_m": cap, "coarser": {}}
    for level, label in ((0, "120 m overview"), (1, "240 m overview"), (2, "480 m overview")):
        w = overview_window(level)
        p = compute_horizon(TerrainSampler([w]), LAT, LON, H_OBS, **kw)
        d = p.horizon_elevation_deg - ref.horizon_elevation_deg
        out["coarser"][label] = {
            "pixel_size_m": w.meta.pixel_size_m, "n_truncated": int(p.truncated.sum()),
            "mean_diff_deg": float(d.mean()), "rms_diff_deg": float(np.sqrt((d**2).mean())),
            "max_abs_diff_deg": float(np.abs(d).max()), "p95_abs_diff_deg": float(np.percentile(np.abs(d), 95)),
            "frac_underestimated_gt_0p05deg": float((d < -0.05).mean()),
            "horizon_deg": {"min": float(p.horizon_elevation_deg.min()), "max": float(p.horizon_elevation_deg.max())},
        }
        print(label, json.dumps(out["coarser"][label]), flush=True)
    path = ROOT / "docs" / "stage4" / "chandrayaan3_resolution_study.json"
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print("wrote", path)


if __name__ == "__main__":
    with Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".TIF", GDAL_HTTP_MAX_RETRY="6",
             GDAL_HTTP_TIMEOUT="180"):
        main()
