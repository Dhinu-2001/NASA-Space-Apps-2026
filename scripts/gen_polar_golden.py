"""Regenerate web/src/polarGolden.json from the ENGINE's own projection (engine/lunarnav/dem.py lonlat_to_xy).

The web map repeats the projection formula in TypeScript (web/src/polar.ts); this table pins both implementations.
Usage: python scripts/gen_polar_golden.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
from lunarnav.dem import R, lonlat_to_xy

PTS = [
    ("im2-athena", -84.79059, 29.19567), ("im2-intended", -84.78, 29.13), ("im1-odysseus", -80.12759, 1.44587),
    ("chandrayaan3-shiv-shakti", -69.3741, 32.32), ("shackleton-published", -89.67, 129.78),
    ("pole-limit", -89.999, 0.0), ("lat-85-lon-0", -85.0, 0.0), ("lat-80-lon-neg135", -80.0, -135.0), ("lat-75-lon-90", -75.0, 90.0),
    ("lat-70-lon-180", -70.0, 180.0), ("lat-60-lon-270", -60.0, 270.0), ("lat-55.1-lon-45", -55.1, 45.0),
]
out = {
    "note": ("Generated from engine/lunarnav/dem.py lonlat_to_xy (sphere radius 1737400 m, latitude_of_origin -90). Do not edit by hand; "
             "tests/engine/test_basemap_projection_golden.py keeps this file equal to the engine."),
    "sphere_radius_m": R,
    "points": [{"name": n, "lat_deg": la, "lon_deg_east": lo, "x_m": lonlat_to_xy(la, lo)[0], "y_m": lonlat_to_xy(la, lo)[1]} for n, la, lo in PTS],
}
(ROOT / "web" / "src" / "polarGolden.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
print(len(PTS), "points; R =", R)
