"""Stage 9 — edge cases: coordinates, poles, time boundaries, permanently shadowed terrain, missing datasets.

Kinds, labelled explicitly:
  * REAL-DATA   - real SPICE ephemeris and the IM-2 LOLA windows (skipped, with the rebuild command, if absent).
  * SYNTHETIC  - in-memory terrain used ONLY to test behaviour against analytic expectations (never lunar data).
  * FAULT      - a deliberately broken data directory, to test that failure is a typed error and never a fallback.
Pre-declared expectations: every failure below is a typed LunarNavError (INVALID_INPUT / OUT_OF_DEM_COVERAGE /
DATA_MISSING / EPHEMERIS_OUT_OF_RANGE) with a named field or a rebuild hint; none returns a number.
"""

import itertools
import json
import math
import shutil
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
import rasterio
from lunarnav.dem import DemWindow, DemWindowMeta, lonlat_to_xy, sha256_file
from lunarnav.ephemeris import EphemerisService, parse_utc
from lunarnav.errors import (
    DataMissingError,
    EphemerisOutOfRangeError,
    InvalidInputError,
    OutOfDemCoverageError,
)
from lunarnav.horizon import HorizonService
from lunarnav.scenarios import INSUFFICIENT, SUPPORTED, ScenarioService
from lunarnav.visibility import VisibilityService
from rasterio.transform import from_origin

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
HAVE_KERNELS = all((DATA / "kernels" / f).exists() for f in
                   ("naif0012.tls", "de440s.bsp", "moon_pa_de440_200625.bpc", "moon_de440_250416.tf"))
HAVE_DEM = all((DATA / "dem_cache" / f).exists() for f in ("im2_20m_r10km.tif", "im2_320m_r160km.tif", "im2_20m_r80km.tif"))
needs_kernels = pytest.mark.skipif(not HAVE_KERNELS, reason=r"kernels missing: scripts\fetch_kernels.py")
needs_data = pytest.mark.skipif(not (HAVE_KERNELS and HAVE_DEM), reason="kernels/DEM windows missing; see DEV_SETUP")
IM2 = (-84.79059, 29.19567)
UTC0 = UTC


def D(y, mo, d, h=0, mi=0, s=0):
    return datetime(y, mo, d, h, mi, s, tzinfo=UTC0)


@pytest.fixture(scope="module")
def eph():
    return EphemerisService(DATA)


@pytest.fixture(scope="module")
def vis(eph):
    return VisibilityService(eph, HorizonService(DATA))


# ================================================================ coordinate edge cases

@pytest.mark.parametrize(("lat", "lon", "field"), [
    (95.0, 0.0, "lat"), (-91.0, 0.0, "lat"), (float("nan"), 0.0, "lat"), (float("inf"), 0.0, "lat"),
    (-85.0, float("nan"), "lon"), (-85.0, 400.0, "lon"), (-85.0, -181.0, "lon"), ("x", 0.0, "lat"), (True, 0.0, "lat"),
])
def test_invalid_coordinates_are_typed_input_errors(lat, lon, field):
    with pytest.raises(InvalidInputError) as e:
        HorizonService(DATA).profile(lat, lon, 2.0)
    assert e.value.field == field


@pytest.mark.parametrize(("lat", "lon"), [(0.0, 0.0), (10.0, 45.0), (89.0, 0.0), (90.0, 0.0)])
def test_northern_and_equatorial_sites_have_no_south_polar_dem_and_say_so(lat, lon):
    with pytest.raises(OutOfDemCoverageError) as e:
        HorizonService(DATA).profile(lat, lon, 2.0)
    assert "fallback" in e.value.message.lower() or "south" in e.value.message.lower()


def test_antimeridian_is_one_place_on_the_dem_grid_and_in_the_ephemeris():
    a, b = lonlat_to_xy(-85.0, 180.0), lonlat_to_xy(-85.0, -180.0)
    assert a == pytest.approx(b, abs=1e-6)
    c, d = lonlat_to_xy(-85.0, 190.0), lonlat_to_xy(-85.0, -170.0)
    assert c == pytest.approx(d, abs=1e-6)


@needs_kernels
def test_ephemeris_treats_equivalent_longitudes_identically(eph):
    t = D(2027, 3, 1, 12)
    a = eph.at(-85.0, 190.0, t, ("sun", "earth"), 0.0)
    b = eph.at(-85.0, -170.0, t, ("sun", "earth"), 0.0)
    for body in ("sun", "earth"):
        assert a.bodies[body].azimuth_deg[0] == pytest.approx(b.bodies[body].azimuth_deg[0], abs=1e-9)
        assert a.bodies[body].elevation_deg[0] == pytest.approx(b.bodies[body].elevation_deg[0], abs=1e-9)


# ================================================================ polar locations

@needs_kernels
@pytest.mark.parametrize("lat", [-90.0, 90.0])
def test_exact_pole_elevation_is_independent_of_longitude_and_azimuth_follows_the_e4_convention(eph, lat):
    t = D(2027, 6, 1, 6)
    res = {lon: eph.at(lat, lon, t, ("sun", "earth"), 0.0) for lon in (0.0, 123.0, 270.0, -90.0)}
    for body in ("sun", "earth"):
        els = [r.bodies[body].elevation_deg[0] for r in res.values()]
        assert max(els) - min(els) < 1e-9                       # the local vertical is the same at the pole
        azs = {lon: r.bodies[body].azimuth_deg[0] for lon, r in res.items()}
        # supplied longitude defines north (decision E4): rotating it by d shifts the azimuth by exactly d
        assert (azs[123.0] - azs[0.0] + 360) % 360 == pytest.approx((-123.0) % 360, abs=1e-6) or \
            (azs[123.0] - azs[0.0] + 360) % 360 == pytest.approx(123.0, abs=1e-6)


@needs_data
def test_exact_south_pole_is_covered_only_by_the_coarse_window_and_is_flagged_not_certified(vis):
    """FINDING (Stage 9): the exact pole lies inside the 320 m IM-2 window (the site is ~158 km from the pole, the window
    half-width is 160 km) but in no 20 m window. The engine therefore computes a horizon from the area-averaged window only,
    most azimuths leave coverage (truncated), and the result is NOT certified: it is never presented as a finished result."""
    for lon in (0.0, 123.0):
        p = HorizonService(DATA).profile(-90.0, lon, 2.0, az_step_deg=5.0, use_cache=False)
        assert [w["window_id"] for w in p.meta["windows"]] == ["im2_320m_r160km"]
        assert p.summary()["n_truncated"] > p.n_azimuths // 2          # most rays leave the 160 km window: lower bounds
    r = vis.evaluate(-90.0, 0.0, D(2027, 1, 15), 3600.0, 3, 2.0, horizon_kwargs={"az_step_deg": 5.0}).to_dict()
    assert r["position_sensitivity"]["status"] == "not_computed" and "insufficient" in r["position_sensitivity"]["reason"]
    assert r["horizon"]["summary"]["n_truncated"] > 0
    # a point outside every window is an explicit error, not a guess
    with pytest.raises(OutOfDemCoverageError):
        HorizonService(DATA).profile(-85.0, -150.0, 2.0)


@needs_data
def test_scenario_at_the_pole_is_labelled_insufficient_not_crashed_or_estimated():
    sv = ScenarioService(DATA, VisibilityService(EphemerisService(DATA), HorizonService(DATA)))
    r = sv.evaluate(sv.make_spec({"lat": -90.0, "lon": 0.0}, "2027-01-15T00:00:00Z", duration_days=5.0,
                                 step_seconds=3600.0, az_step_deg=5.0), use_cache=False)
    assert r["status"] == INSUFFICIENT and r["reason_code"] == "TERRAIN_NOT_CERTIFIED" and "bodies" not in r
    far = sv.evaluate(sv.make_spec({"lat": -85.0, "lon": -150.0}, "2027-01-15T00:00:00Z", duration_days=5.0,
                                   step_seconds=3600.0), use_cache=False)
    assert far["status"] == INSUFFICIENT and far["reason_code"] == "OUT_OF_DEM_COVERAGE" and "bodies" not in far


# ================================================================ time boundaries

@needs_data
@pytest.mark.parametrize("when", [D(2025, 1, 1), D(2035, 12, 31, 23), D(2035, 12, 31, 23, 59, 59), D(2028, 2, 29, 12)])
def test_instants_inside_the_validated_range_work(vis, when):
    r = vis.evaluate(*IM2, when, 900.0, 1, 2.0, position_uncertainty_m=None, include_series=True).to_dict()
    assert len(r["bodies"]["sun"]["series"]["elevation_deg"]) == 1
    assert math.isfinite(r["bodies"]["sun"]["series"]["elevation_deg"][0])


@needs_data
@pytest.mark.parametrize("when", [D(2024, 12, 31, 23, 59, 59), D(2036, 1, 1), D(2040, 6, 1), D(2000, 1, 1)])
def test_instants_outside_the_validated_range_are_refused_not_extrapolated(vis, when):
    with pytest.raises(EphemerisOutOfRangeError):
        vis.evaluate(*IM2, when, 900.0, 1, 2.0, position_uncertainty_m=None)


@needs_data
def test_a_window_that_runs_past_the_end_of_the_range_is_refused_not_truncated(vis):
    with pytest.raises(EphemerisOutOfRangeError):
        vis.evaluate(*IM2, D(2035, 12, 30), 3600.0, 73, 2.0, position_uncertainty_m=None)   # last sample 2036-01-02
    ok = vis.evaluate(*IM2, D(2035, 12, 30), 3600.0, 47, 2.0, position_uncertainty_m=None)  # last sample 2035-12-31 22:00
    assert ok.to_dict()["window"]["n_samples"] == 47


@needs_data
def test_a_window_across_a_leap_day_is_uniform_and_consistent(vis):
    r = vis.evaluate(*IM2, D(2028, 2, 28), 3600.0, 49, 2.0, position_uncertainty_m=None).to_dict()
    assert r["window"]["end_utc"] == "2028-03-01T00:00:00Z"                      # 48 h: leap day included, no skipped hour
    s = r["bodies"]["sun"]["series"]["times_s"]
    assert s[-1] - s[0] == 48 * 3600 and all(abs((b - a) - 3600) < 1e-9 for a, b in itertools.pairwise(s))


@pytest.mark.parametrize("bad", ["2027-01-15T00:00:00", "2027-01-15", "2027-01-15T00:00:00+05:30", "tomorrow", 1.0, None])
def test_non_utc_or_malformed_times_are_rejected(bad):
    with pytest.raises(InvalidInputError):
        parse_utc(bad, "t")


# ================================================================ permanently shadowed terrain (SYNTHETIC)

LAT0, LON0 = -85.0, 30.0


def _crater_window() -> DemWindow:
    """A bowl: flat floor (-1500 m) to r = 2 km, rising linearly to a +500 m rim at r = 4 km, flat beyond."""
    x0, y0 = lonlat_to_xy(LAT0, LON0)
    half, px = 20_000.0, 20.0
    n = round(2 * half / px)
    left, top = x0 - half, y0 + half
    xs = left + (np.arange(n) + 0.5) * px
    ys = top - (np.arange(n) + 0.5) * px
    xx, yy = np.meshgrid(xs, ys)
    r = np.hypot(xx - x0, yy - y0)
    z = np.where(r < 2000.0, -1500.0, np.where(r < 4000.0, -1500.0 + 2000.0 * (r - 2000.0) / 2000.0, 500.0)).astype(np.float32)
    meta = DemWindowMeta.from_dict("crater", {
        "product_id": "SYNTHETIC_TEST_ONLY", "file": "dem_cache/crater.tif", "sha256": "0" * 64, "pixel_size_m": px,
        "left_m": left, "top_m": top, "width": n, "height": n, "valid_fraction": 1.0, "z_min_m": float(z.min()),
        "z_max_m": float(z.max()), "source_url": "https://example.invalid/synthetic", "overview_level": None})
    return DemWindow(meta, z)


def _write_registry(root: Path, w: DemWindow) -> None:
    (root / "dem_cache").mkdir(parents=True, exist_ok=True)
    f = root / "dem_cache" / "crater.tif"
    m = w.meta
    with rasterio.open(f, "w", driver="GTiff", dtype="float32", count=1, width=m.width, height=m.height,
                       transform=from_origin(m.left_m, m.top_m, m.pixel_size_m, m.pixel_size_m), nodata=float("nan")) as dst:
        dst.write(w.data, 1)
    d = dict(m.raw)
    d["sha256"] = sha256_file(f)
    (root / "manifests").mkdir(parents=True, exist_ok=True)
    (root / "manifests" / "dem_windows.json").write_text(json.dumps({"windows": {"crater": d}}))
    (root / "catalogue").mkdir(exist_ok=True)
    (root / "catalogue" / "sites.json").write_bytes((DATA / "catalogue" / "sites.json").read_bytes())


@needs_kernels
def test_permanently_shadowed_floor_never_sees_the_sun_or_earth_while_geometry_says_the_sun_is_up(tmp_path, eph):
    _write_registry(tmp_path, _crater_window())
    sv = ScenarioService(tmp_path, VisibilityService(eph, HorizonService(tmp_path)))
    r = sv.evaluate(sv.make_spec({"lat": LAT0, "lon": LON0}, "2027-01-15T00:00:00Z", duration_days=30.0,
                                 az_step_deg=1.0), use_cache=False)
    assert r["status"] == SUPPORTED                     # complete synthetic terrain: sensitivity can be computed
    window_s = 30 * 86400.0
    for body in ("sun", "earth"):
        tc = r["bodies"][body]["terrain_corrected"]
        assert tc["visible_fraction"]["nominal"] == 0.0 and tc["visible_fraction"]["band"] == [0.0, 0.0]
        assert tc["total_visible_s"]["nominal"] == 0.0 and tc["events"] == []
        lnv = tc["longest_not_visible_s"]
        assert lnv["including_open"] == pytest.approx(window_s) and lnv["includes_open_interval"] is True
        assert lnv["closed_only"] is None                # never claimed as a measured, closed interval
        assert r["bodies"][body]["completeness"]["visibility_is_upper_bound"] is False
    # ...while the geometry (local horizontal) has the Sun up about half the month: terrain removes all of it
    geo_sun = r["bodies"]["sun"]["geometric"]["visible_fraction"]["nominal"]
    assert geo_sun > 0.4
    assert r["bodies"]["sun"]["terrain_effect"]["visible_s_terrain_minus_geometric"]["nominal"] == pytest.approx(-geo_sun * window_s, rel=1e-3)
    assert r["bodies"]["sun"]["terrain_effect"]["steps_blocked_by_terrain_only"] > 1000


@needs_kernels
def test_the_crater_rim_is_higher_than_any_sun_or_earth_elevation_so_the_result_is_physical(tmp_path, eph):
    _write_registry(tmp_path, _crater_window())
    v = VisibilityService(eph, HorizonService(tmp_path)).evaluate(
        LAT0, LON0, D(2027, 1, 15), 3600.0, 721, 2.0, position_uncertainty_m=None,
        horizon_kwargs={"az_step_deg": 1.0}).to_dict()
    for body in ("sun", "earth"):
        s = v["bodies"][body]["series"]
        assert min(s["terrain_horizon_at_centre_deg"]) > max(s["elevation_deg"]) + 10.0   # rim ~26 deg vs body < ~14 deg


# ================================================================ missing datasets (FAULT)

def _copy_manifests(dst: Path) -> None:
    shutil.copytree(DATA / "manifests", dst / "manifests")
    (dst / "catalogue").mkdir()
    (dst / "catalogue" / "sites.json").write_bytes((DATA / "catalogue" / "sites.json").read_bytes())


@needs_kernels
def test_missing_kernels_are_a_typed_error_with_a_rebuild_hint(tmp_path):
    _copy_manifests(tmp_path)
    with pytest.raises(DataMissingError) as e:
        EphemerisService(tmp_path).load()
    assert "fetch_kernels" in json.dumps(e.value.details) and e.value.field


@needs_data
def test_missing_kernels_are_never_mislabelled_as_terrain_data_insufficient(tmp_path):
    """Regression for a bug found in Stage 9: the scenario service used to turn ANY DataMissingError into
    'terrain_data_insufficient'. A missing SPICE kernel is an infrastructure failure and must surface as DATA_MISSING."""
    _copy_manifests(tmp_path)
    sv = ScenarioService(DATA, VisibilityService(EphemerisService(tmp_path), HorizonService(DATA)))
    with pytest.raises(DataMissingError) as e:
        sv.evaluate(sv.make_spec({"site_id": "im2-athena"}, "2027-01-15T00:00:00Z", duration_days=2.0,
                                 step_seconds=3600.0, az_step_deg=1.0), use_cache=False)
    assert e.value.field != "dem"


@needs_kernels
def test_missing_dem_files_make_a_scenario_terrain_data_insufficient_with_the_data_missing_code(tmp_path, eph):
    _copy_manifests(tmp_path)                              # manifest lists the windows, the files are absent
    sv = ScenarioService(tmp_path, VisibilityService(eph, HorizonService(tmp_path)))
    r = sv.evaluate(sv.make_spec({"site_id": "im2-athena"}, "2027-01-15T00:00:00Z", duration_days=2.0,
                                 step_seconds=3600.0, az_step_deg=1.0), use_cache=False)
    assert r["status"] == INSUFFICIENT and r["reason_code"] == "DATA_MISSING"
    assert "extract_dem_window" in r["reason"]                  # the reason tells the operator how to rebuild
    assert "bodies" not in r
    with pytest.raises(DataMissingError):
        HorizonService(tmp_path).profile(*IM2, 2.0)


@needs_data
def test_a_modified_dem_window_is_refused_by_checksum(tmp_path):
    _copy_manifests(tmp_path)
    (tmp_path / "dem_cache").mkdir()
    shutil.copy(DATA / "dem_cache" / "im2_20m_r10km.tif", tmp_path / "dem_cache" / "im2_20m_r10km.tif")
    # change ONE elevation (the integrity check covers the decoded elevations and georeferencing, not the file bytes)
    with rasterio.open(tmp_path / "dem_cache" / "im2_20m_r10km.tif", "r+") as ds:
        a = ds.read(1)
        a[10, 10] += 1.0
        ds.write(a, 1)
    with pytest.raises(DataMissingError) as e:
        HorizonService(tmp_path).profile(*IM2, 2.0, window_ids=["im2_20m_r10km"], use_cache=False)
    assert "checksum" in e.value.message and e.value.field == "dem"


@needs_kernels
def test_a_modified_kernel_is_refused_by_checksum(tmp_path):
    _copy_manifests(tmp_path)
    (tmp_path / "kernels").mkdir()
    shutil.copy(DATA / "kernels" / "naif0012.tls", tmp_path / "kernels" / "naif0012.tls")
    with (tmp_path / "kernels" / "naif0012.tls").open("ab") as f:
        f.write(b"\n")
    with pytest.raises(DataMissingError):
        EphemerisService(tmp_path).load()
