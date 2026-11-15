"""The south-polar map in the web UI repeats the engine's projection formula (it cannot call Python). This keeps the
generated golden table (web/src/polarGolden.json, asserted against the TypeScript in web/src/Basemap.test.tsx) equal to
the engine's own `lonlat_to_xy`, so the two implementations cannot drift apart unnoticed. Test-only: no engine change."""

import json
import math
from pathlib import Path

import pytest
from lunarnav.dem import R, lonlat_to_xy

GOLDEN = Path(__file__).resolve().parents[2] / "web" / "src" / "polarGolden.json"


def test_golden_table_equals_the_engine_projection():
    g = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert g["sphere_radius_m"] == R == 1_737_400.0
    assert len(g["points"]) >= 10
    for p in g["points"]:
        x, y = lonlat_to_xy(p["lat_deg"], p["lon_deg_east"])
        assert p["x_m"] == pytest.approx(x, abs=1e-6), p["name"]
        assert p["y_m"] == pytest.approx(y, abs=1e-6), p["name"]


def test_golden_table_covers_the_catalogue_sites_and_the_ring_latitudes():
    g = {p["name"]: p for p in json.loads(GOLDEN.read_text(encoding="utf-8"))["points"]}
    for site in ("im2-athena", "im2-intended", "im1-odysseus", "chandrayaan3-shiv-shakti"):
        assert site in g
    # the four parallels the map draws are present as points on a known axis, so the UI test can derive their radii
    assert math.hypot(g["lat-85-lon-0"]["x_m"], g["lat-85-lon-0"]["y_m"]) == pytest.approx(2 * R * math.tan(math.radians(2.5)), abs=1e-6)
    assert {"lat-80-lon-neg135", "lat-70-lon-180", "lat-60-lon-270"} <= set(g)
