"""Stage 4 task 9: quantify the resolution and sampling limits of the horizon profile (IM-2 Athena).

Not a validation: it measures how much each data/sampling choice moves the result, so the limits are stated
with numbers instead of assumed. Needs the 80 km 20 m window (scripts/extract_dem_window.py im2_20m_r80km).

Usage: .\\.venv\\Scripts\\python.exe -I scripts\\horizon_resolution_study.py [--json docs/stage4/resolution_study.json]
"""

from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

import pyproj
from lunarnav.dem import DemWindow
from lunarnav.horizon import HorizonService

SITE = (-84.79059, 29.19567)  # IM-2 Athena (NAIF)
H_OBS = 2.0
GEOD = pyproj.Geod(a=1_737_400.0, b=1_737_400.0)
A80, A10, C160 = "im2_20m_r80km", "im2_20m_r10km", "im2_320m_r160km"


def stats(diff: np.ndarray) -> dict[str, float]:
    d = diff[np.isfinite(diff)]
    return {
        "n": int(d.size), "mean_deg": float(d.mean()), "rms_deg": float(np.sqrt((d**2).mean())),
        "max_abs_deg": float(np.abs(d).max()), "p95_abs_deg": float(np.percentile(np.abs(d), 95)),
        "p99_abs_deg": float(np.percentile(np.abs(d), 99)),
        "frac_underestimated_gt_0p05deg": float((d < -0.05).mean()),
        "frac_underestimated_gt_0p5deg": float((d < -0.5).mean()),
        "frac_underestimated_gt_1deg": float((d < -1.0).mean()),
    }


def main() -> dict:
    svc = HorizonService(ROOT / "data")
    reg = svc.registry
    for w in (A80, A10, C160):
        if w not in reg.windows:
            raise SystemExit(f"window {w} missing: run scripts/extract_dem_window.py")

    def prof(ids, lat=SITE[0], lon=SITE[1], h=H_OBS, az=0.25, **kw):
        t0 = time.time()
        p = svc.profile(lat, lon, h, az_step_deg=az, window_ids=ids, use_cache=False, **kw)
        print(f"  computed {ids} az={az} {kw} in {time.time() - t0:.1f}s", flush=True)
        return p

    out: dict = {"site": {"lat": SITE[0], "lon": SITE[1], "observer_height_m": H_OBS}}

    print("1. data resolution and extent", flush=True)
    ref = prof([A80], max_range_km=80.0)  # 20 m, out to 80 km: the reference for this study
    out["reference"] = {"windows": [A80], "range_km": 80.0, **ref.summary(),
                        "ground_height_m": ref.meta["observer"]["ground_height_m"]}
    cmp_ = {
        "20m_only_to_10km_vs_20m_to_80km (effect of truncating at 10 km)":
            prof([A10], max_range_km=10.0).horizon_elevation_deg - ref.horizon_elevation_deg,
        "320m_to_80km_vs_20m_to_80km (effect of pixel size, same extent)":
            prof([C160], max_range_km=80.0).horizon_elevation_deg - ref.horizon_elevation_deg,
    }
    layered = prof([A80, C160])  # 20 m to 80 km then 320 m to the 160 km window edge
    r160 = prof([C160])
    cmp_["20m_to_80km+320m_to_160km_vs_20m_to_80km (effect of extending to 160 km)"] = (
        layered.horizon_elevation_deg - ref.horizon_elevation_deg)
    cmp_["320m_to_160km_vs_20m+320m_to_160km (320 m alone vs layered, full extent)"] = (
        r160.horizon_elevation_deg - layered.horizon_elevation_deg)
    out["comparisons"] = {k: stats(v) for k, v in cmp_.items()}
    out["layered_160km"] = {**layered.summary(), "max_range_covered_km": float(layered.range_covered_km.max()),
                            "min_range_covered_km": float(layered.range_covered_km.min())}
    out["limiting_distance_km_reference"] = {
        "median": float(np.nanmedian(ref.horizon_distance_km)),
        "p90": float(np.nanpercentile(ref.horizon_distance_km, 90)),
        "max": float(np.nanmax(ref.horizon_distance_km)),
        "fraction_set_within_10km": float(np.mean(ref.horizon_distance_km <= 10.0)),
        "fraction_set_beyond_40km": float(np.mean(ref.horizon_distance_km > 40.0)),
    }

    print("2. is the 320 m overview an area average of the 20 m data?", flush=True)
    wa = DemWindow.load(reg.windows[A80], ROOT / "data")
    wc = DemWindow.load(reg.windows[C160], ROOT / "data")
    ma, mc = wa.meta, wc.meta
    off = round((ma.left_m - mc.left_m) / 20.0)          # A's column offset from C's origin, in 20 m pixels
    s_col = (-off) % 16                                  # first A column that starts a 320 m block
    off_r = round((mc.top_m - ma.top_m) / 20.0)
    s_row = (-off_r) % 16
    nb = (ma.width - s_col) // 16 - 1
    blocks = wa.data[s_row : s_row + nb * 16, s_col : s_col + nb * 16].reshape(nb, 16, nb, 16)
    mean_block = np.nanmean(blocks, axis=(1, 3))
    nearest = blocks[:, 8, :, 8]  # centre-pixel decimation
    c0 = round((ma.left_m + s_col * 20.0 - mc.left_m) / 320.0)
    r0 = round((mc.top_m - (ma.top_m - s_row * 20.0)) / 320.0)
    cs = wc.data[r0 : r0 + nb, c0 : c0 + nb]
    out["overview_vs_blockmean"] = {
        "blocks_compared": int(nb * nb),
        "rms_vs_16x16_mean_m": float(np.sqrt(np.nanmean((cs - mean_block) ** 2))),
        "max_abs_vs_16x16_mean_m": float(np.nanmax(np.abs(cs - mean_block))),
        "rms_vs_centre_pixel_decimation_m": float(np.sqrt(np.nanmean((cs - nearest) ** 2))),
        "rms_of_20m_terrain_within_block_m": float(np.sqrt(np.nanmean(np.nanvar(blocks, axis=(1, 3))))),
    }

    print("3. azimuth step", flush=True)
    fine = prof([A80], az=0.05, max_range_km=80.0)
    fa = fine.horizon_elevation_deg
    nf = fa.size
    out["azimuth_step"] = {}
    for step in (1.0, 0.5, 0.25):
        coarse = ref if step == 0.25 else prof([A80], az=step, max_range_km=80.0)
        k = round(step / 0.05)
        c = coarse.horizon_elevation_deg
        # conservative reconstruction between samples = max of the two bracketing samples
        idx = np.arange(nf)
        lo = (idx // k) % c.size
        hi = (lo + 1) % c.size
        est = np.where(idx % k == 0, c[lo], np.maximum(c[lo], c[hi]))
        out["azimuth_step"][f"{step}deg"] = {"missed_obstruction_vs_0.05deg_profile": stats(est - fa)}

    print("4. radial step", flush=True)
    half = prof([A80], max_range_km=80.0, step_m=10.0)
    out["radial_step_10m_vs_20m"] = stats(half.horizon_elevation_deg - ref.horizon_elevation_deg)

    print("5. observer height", flush=True)
    out["observer_height"] = {}
    for h in (0.0, 5.0, 10.0, 30.0):
        out["observer_height"][f"{h:g}m_vs_2m"] = stats(prof([A80], h=h, max_range_km=80.0).horizon_elevation_deg
                                                        - ref.horizon_elevation_deg)

    print("6. observer position (landing-site coordinate uncertainty)", flush=True)
    out["observer_position"] = {}
    for dist in (20.0, 100.0):
        worst = []
        for az in (0.0, 90.0, 180.0, 270.0):
            lo, la, _ = GEOD.fwd(SITE[1], SITE[0], az, dist)
            d = prof([A80], lat=la, lon=lo, max_range_km=80.0).horizon_elevation_deg - ref.horizon_elevation_deg
            worst.append(stats(d))
        out["observer_position"][f"{dist:g}m_shift"] = {
            "worst_max_abs_deg": max(w["max_abs_deg"] for w in worst),
            "worst_rms_deg": max(w["rms_deg"] for w in worst),
            "worst_p95_abs_deg": max(w["p95_abs_deg"] for w in worst),
        }
    return out


if __name__ == "__main__":
    res = main()
    text = json.dumps(res, indent=1)
    print(text)
    if "--json" in sys.argv:
        Path(sys.argv[sys.argv.index("--json") + 1]).write_text(text + "\n", encoding="utf-8")
    sys.exit(0 if math.isfinite(res["reference"]["horizon_max_deg"]) else 1)
