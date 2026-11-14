"""Stage 4 validation: compare the engine's horizon with a hand-written INDEPENDENT implementation.

The reference shares no code with lunarnav.horizon:
  * ray points: pyproj spherical geodesic (Geod a=b=1737400) - independent of the vector rotation in the engine
  * projection: PROJ stereographic (+proj=stere +lat_0=-90) - independent of the closed-form grid maths
  * heights: the GeoTIFF's own affine transform + a scalar-style bilinear written here
  * elevation: angle between (P - O) and the observer's radial in 3-D Cartesian vectors, not the atan2 identity
What it can and cannot show: it validates geometry, azimuth convention, curvature, indexing and interpolation
code. It does NOT validate the DEM itself or the horizon against a physically independent dataset.

Pre-declared criterion (set before running): |engine - reference| <= 1e-3 deg on every azimuth/height tested,
where the limiting sample is within the range the reference covers.

Usage: .\\.venv\\Scripts\\python.exe -I scripts\\validate_horizon.py [--window im2_20m_r80km] [--json out.json]
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pyproj
import rasterio

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

from lunarnav.horizon import HorizonService

R = 1_737_400.0
GEOD = pyproj.Geod(a=R, b=R)
CRS = pyproj.CRS.from_proj4("+proj=stere +lat_0=-90 +lat_ts=-90 +lon_0=0 +R=1737400 +units=m")
TOL_DEG = 1e-3
SITE = (-84.79059, 29.19567)


def unit(lat, lon):
    la, lo = np.radians(lat), np.radians(lon)
    return np.stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)], axis=-1)


def reference_horizon(tif: Path, lat, lon, h_above, azimuths, step=20.0, max_km=None):
    tr = pyproj.Transformer.from_crs(CRS.geodetic_crs, CRS, always_xy=True)
    with rasterio.open(tif) as ds:
        arr = ds.read(1).astype(np.float64)
        t = ds.transform

    def height(la, lo):
        x, y = tr.transform(lo, la)
        col, row = (np.asarray(x) - t.c) / t.a - 0.5, (t.f - np.asarray(y)) / (-t.e) - 0.5
        ok = (col >= 0) & (col <= arr.shape[1] - 1) & (row >= 0) & (row <= arr.shape[0] - 1)
        c0 = np.clip(np.floor(col).astype(int), 0, arr.shape[1] - 2)
        r0 = np.clip(np.floor(row).astype(int), 0, arr.shape[0] - 2)
        fc, fr = col - c0, row - r0
        z = ((arr[r0, c0] * (1 - fc) + arr[r0, c0 + 1] * fc) * (1 - fr)
             + (arr[r0 + 1, c0] * (1 - fc) + arr[r0 + 1, c0 + 1] * fc) * fr)
        return np.where(ok, z, np.nan), ok

    ground = float(height(np.array([lat]), np.array([lon]))[0][0])
    h_obs = ground + h_above
    o = (R + h_obs) * unit(lat, lon)
    up = o / np.linalg.norm(o)
    far = max_km * 1000.0 if max_km else 160_000.0 * math.sqrt(2)
    n = int(far / step)
    dist = step * np.arange(1, n + 1)
    out_h, out_d = [], []
    for az in azimuths:
        lo2, la2, _ = GEOD.fwd(np.full(n, lon), np.full(n, lat), np.full(n, az), dist)
        z, ok = height(la2, lo2)
        end = n if ok.all() else int(np.argmax(~ok))  # coverage ends at the first sample outside the raster
        z, la2, lo2, d = z[:end], la2[:end], lo2[:end], dist[:end]
        good = np.isfinite(z)
        p = (R + z[good, None]) * unit(la2[good], lo2[good])
        v = p - o
        elev = np.degrees(np.arcsin((v @ up) / np.linalg.norm(v, axis=1)))
        k = int(np.argmax(elev))
        out_h.append(float(elev[k]))
        out_d.append(float(d[good][k] / 1000.0))
    return np.array(out_h), np.array(out_d), ground


def main(window_id: str) -> dict:
    svc = HorizonService(ROOT / "data")
    meta = svc.registry.windows[window_id]
    tif = ROOT / "data" / meta.file
    rng = np.random.default_rng(20261114)
    azimuths = np.unique(np.concatenate([np.arange(0, 360, 15.0), rng.integers(0, 1440, 40) * 0.25]))
    result = {"window": window_id, "criterion_deg": TOL_DEG, "cases": []}
    ok_all = True
    for h in (0.0, 2.0, 30.0):
        prof = svc.profile(*SITE, h, az_step_deg=0.25, window_ids=[window_id], use_cache=False)
        ref_h, ref_d, ground = reference_horizon(tif, *SITE, h, azimuths)
        idx = np.round(azimuths / 0.25).astype(int)
        diff = prof.horizon_elevation_deg[idx] - ref_h
        dd = prof.horizon_distance_km[idx] - ref_d
        worst = float(np.abs(diff).max())
        case = {
            "observer_height_m": h, "n_azimuths": int(azimuths.size), "ground_height_m": ground,
            "engine_ground_height_m": prof.meta["observer"]["ground_height_m"],
            "max_abs_diff_deg": worst, "rms_diff_deg": float(np.sqrt((diff**2).mean())),
            "max_abs_limiting_distance_diff_km": float(np.abs(dd).max()),
            "horizon_range_deg": [float(ref_h.min()), float(ref_h.max())],
            "passed": worst <= TOL_DEG,
        }
        ok_all &= case["passed"]
        result["cases"].append(case)
        print(f"h={h:5.1f} m  n={azimuths.size}  max|diff|={worst:.2e} deg  rms={case['rms_diff_deg']:.2e}  "
              f"max|d_dist|={case['max_abs_limiting_distance_diff_km']:.3f} km  "
              f"horizon {ref_h.min():.2f}..{ref_h.max():.2f} deg  {'PASS' if case['passed'] else 'FAIL'}")
    result["passed"] = bool(ok_all)
    return result


if __name__ == "__main__":
    wid = sys.argv[sys.argv.index("--window") + 1] if "--window" in sys.argv else "im2_20m_r80km"
    res = main(wid)
    if "--json" in sys.argv:
        Path(sys.argv[sys.argv.index("--json") + 1]).write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    sys.exit(0 if res["passed"] else 1)
