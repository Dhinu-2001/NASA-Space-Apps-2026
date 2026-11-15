"""Terrain horizon tests (Stage 4).

Kinds, labelled explicitly:
  * SYNTHETIC terrain (rasters built in memory/tmp) - used ONLY to test the algorithm against analytic or
    independently computed truth (flat terrain, mesa, NoData, truncation, caching). Never exposed as lunar data.
  * INDEPENDENT cross-check - expected values come from a separate implementation: pyproj's spherical
    geodesics for bearings/destinations, a 3-D vector elevation formula, and the GeoTIFF's own affine transform
    with a hand-written bilinear lookup. None of these share code with `lunarnav.horizon`.
  * REAL-DATA tests - use the extracted LOLA windows (git-ignored); skipped with the rebuild command if absent.
"""

import json
import math
from pathlib import Path

import numpy as np
import pytest
import rasterio
from lunarnav.dem import (
    DemRegistry,
    DemWindow,
    DemWindowMeta,
    lonlat_to_xy,
    sha256_file,
    xy_to_lonlat,
)
from lunarnav.errors import DataMissingError, InvalidInputError, OutOfDemCoverageError
from lunarnav.horizon import (
    HorizonService,
    TerrainSampler,
    compute_horizon,
    elevation_angle_rad,
    select_windows,
    sphere_xy,
)
from rasterio.transform import from_origin

DATA = Path(__file__).resolve().parents[2] / "data"
R = 1_737_400.0
LAT0, LON0 = -85.0, 30.0
pyproj = pytest.importorskip("pyproj")
GEOD = pyproj.Geod(a=R, b=R)  # spherical geodesics: an independent implementation of bearing/destination


# ---------------------------------------------------------------- synthetic window helpers

def synth_window(wid, half_m, px, fn, x0=None, y0=None, nan_fn=None):
    if x0 is None:
        x0, y0 = lonlat_to_xy(LAT0, LON0)
    n = round(2 * half_m / px)
    left, top = x0 - half_m, y0 + half_m
    xs = left + (np.arange(n) + 0.5) * px
    ys = top - (np.arange(n) + 0.5) * px
    xx, yy = np.meshgrid(xs, ys)
    z = np.asarray(fn(xx, yy), dtype=np.float32) * np.ones((n, n), dtype=np.float32)
    if nan_fn is not None:
        z[nan_fn(xx, yy)] = np.nan
    meta = DemWindowMeta.from_dict(wid, {
        "product_id": "SYNTHETIC_TEST_ONLY", "file": f"dem_cache/{wid}.tif", "sha256": "0" * 64,
        "pixel_size_m": px, "left_m": left, "top_m": top, "width": n, "height": n,
        "valid_fraction": float(np.isfinite(z).mean()),
        "z_min_m": float(np.nanmin(z)), "z_max_m": float(np.nanmax(z)),
        "source_url": "https://example.invalid/synthetic", "overview_level": None})
    return DemWindow(meta, z)


def mesa_at(az_deg, dist_m, radius_m, height_m, lat=LAT0, lon=LON0):
    """Return fn(x, y) -> mesa height (flat top, disc of given radius in the grid plane) and its centre."""
    lon2, lat2, _ = GEOD.fwd(lon, lat, az_deg, dist_m)
    cx, cy = lonlat_to_xy(lat2, lon2)
    k = 1.0 / math.cos(math.radians((lat2 + 90) / 2)) ** 2  # stereographic scale at the mesa (plane = k * sphere)

    def fn(x, y):
        return np.where(np.hypot(x - cx, y - cy) <= radius_m * k, height_m, 0.0)

    return fn, (lat2, lon2)


def vec(lat, lon, h):
    la, lo = math.radians(lat), math.radians(lon)
    return (R + h) * np.array([math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo), math.sin(la)])


def elev3d_deg(obs, h_obs, tgt, h_tgt):
    """Independent 3-D elevation: angle of (P - O) above the plane perpendicular to O."""
    o, p = vec(*obs, h_obs), vec(*tgt, h_tgt)
    d = p - o
    return math.degrees(math.asin(float(np.dot(d, o / np.linalg.norm(o))) / np.linalg.norm(d)))


def dip_deg(h_obs, h_surface=0.0):
    return math.degrees(math.acos((R + h_surface) / (R + h_surface + h_obs)))


def profile(window, h=0.0, az_step=0.5, **kw):
    kw.setdefault("az_step_deg", az_step)
    return compute_horizon(TerrainSampler([window] if isinstance(window, DemWindow) else window),
                           LAT0, LON0, h, **kw)


# ---------------------------------------------------------------- pure functions

def test_sphere_xy_equals_the_stage2_grid_and_pyproj():
    rng = np.random.default_rng(1)
    lat, lon = rng.uniform(-89.9, -60, 300), rng.uniform(-180, 180, 300)
    la, lo = np.radians(lat), np.radians(lon)
    p = np.stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)], axis=-1)
    x, y = sphere_xy(p)
    x2, y2 = lonlat_to_xy(lat, lon)
    assert np.allclose(x, x2, atol=1e-6) and np.allclose(y, y2, atol=1e-6)
    crs = pyproj.CRS.from_proj4("+proj=stere +lat_0=-90 +lat_ts=-90 +lon_0=0 +R=1737400 +units=m")
    px, py = pyproj.Transformer.from_crs(crs.geodetic_crs, crs, always_xy=True).transform(lon, lat)
    assert np.allclose(x, px, atol=1e-5) and np.allclose(y, py, atol=1e-5)


def test_elevation_formula_matches_independent_3d_vectors():
    obs = (LAT0, LON0)
    for az, dist, h_t, h_o in [(10, 3000, 400, 0), (200, 25_000, 1500, 12), (300, 80_000, 3000, 2)]:
        lon2, lat2, _ = GEOD.fwd(LON0, LAT0, az, dist)
        theta = dist / R
        ours = math.degrees(float(elevation_angle_rad(theta, h_t, h_o)))
        assert ours == pytest.approx(elev3d_deg(obs, h_o, (lat2, lon2), h_t), abs=1e-7)


def test_formula_has_no_cancellation_error_at_tiny_distances():
    # 1 m away, 1 m higher: must be 45 degrees (flat-plane limit), not noise.
    e = math.degrees(float(elevation_angle_rad(1.0 / R, 1.0, 0.0)))
    assert e == pytest.approx(45.0, abs=1e-3)


# ---------------------------------------------------------------- flat terrain (gate: flat)

@pytest.mark.parametrize(("h", "half", "px"), [(2.0, 20_000, 20.0), (50.0, 30_000, 30.0), (500.0, 60_000, 60.0)])
def test_flat_terrain_horizon_is_the_geometric_dip_at_every_azimuth(h, half, px):
    # the window must reach past the tangent distance R*dip (2.6 km, 13 km, 42 km for these heights)
    p = profile(synth_window("flat", half, px, lambda x, y: 0.0), h)
    assert not p.truncated.any()
    expected = -dip_deg(h)
    assert np.all(np.abs(p.horizon_elevation_deg - expected) < 1e-4)
    # the limiting sample is the tangent point, at distance R * dip
    assert np.all(np.abs(p.horizon_distance_km - R * math.radians(dip_deg(h)) / 1000.0) < 0.05)


def test_dip_follows_sqrt_2h_over_R_for_small_h():
    for h in (2.0, 10.0):
        p = profile(synth_window("flat", 20_000, 20.0, lambda x, y: 0.0), h)
        assert -p.horizon_elevation_deg[0] == pytest.approx(math.degrees(math.sqrt(2 * h / R)), rel=1e-3)


def test_flat_terrain_at_any_constant_height_is_the_same_concentric_sphere():
    h = 10.0
    p = profile(synth_window("flat", 20_000, 20.0, lambda x, y: 2500.0), h)
    assert np.allclose(p.horizon_elevation_deg, -dip_deg(h, 2500.0), atol=1e-4)
    # reference-sphere dip differs only at second order; the *terrain* sphere is what matters
    assert abs(dip_deg(h, 2500.0) - dip_deg(h)) < 1e-3


def test_observer_on_flat_surface_sees_the_limit_of_zero_to_within_one_sample():
    p = profile(synth_window("flat", 5_000, 20.0, lambda x, y: 100.0), 0.0)
    theta1 = 20.0 / R  # first sample: elevation = -theta/2 exactly
    assert np.allclose(p.horizon_elevation_deg, -math.degrees(theta1 / 2), atol=1e-9)
    assert abs(p.horizon_elevation_deg[0]) < 1e-3


def test_azimuth_grid_and_output_shapes():
    p = profile(synth_window("flat", 3_000, 20.0, lambda x, y: 0.0), 2.0, az_step=2.5)
    assert p.n_azimuths == 144 and p.azimuth_deg[0] == 0.0 and p.azimuth_deg[-1] == pytest.approx(357.5)
    assert all(a.shape == (144,) for a in (p.horizon_elevation_deg, p.horizon_distance_km, p.truncated))


# ---------------------------------------------------------------- obstructed terrain (gate: obstruction)

@pytest.mark.parametrize("az_p", [0.0, 37.5, 90.0, 181.0, 270.0, 333.0])
def test_mesa_appears_at_the_independently_computed_bearing_and_elevation(az_p):
    dist, rad, ht = 10_000.0, 500.0, 300.0
    fn, centre = mesa_at(az_p, dist, rad, ht)
    w = synth_window("mesa", 20_000, 20.0, fn)
    p = profile(w, 0.0, az_step=0.5)
    # independent bearing from pyproj
    bearing = GEOD.inv(LON0, LAT0, centre[1], centre[0])[0] % 360
    assert bearing == pytest.approx(az_p, abs=1e-6)
    peak = int(np.nanargmax(p.horizon_elevation_deg))
    assert abs(((p.azimuth_deg[peak] - bearing) + 180) % 360 - 180) <= 0.5
    # independent expected elevation: brute-force every mesa-top pixel, 3-D formula, pyproj bearings
    ys, xs = np.nonzero(w.data > 0)
    px = w.meta.left_m + (xs + 0.5) * 20.0
    py = w.meta.top_m - (ys + 0.5) * 20.0
    lat_p, lon_p = xy_to_lonlat(px, py)
    best = max(elev3d_deg((LAT0, LON0), 0.0, (la, lo), ht) for la, lo in zip(lat_p[::7], lon_p[::7], strict=True))
    assert p.horizon_elevation_deg[peak] == pytest.approx(best, abs=0.02)
    assert p.horizon_elevation_deg[peak] > 1.0  # the mesa clearly rises above the flat-terrain dip
    # an azimuth 20 degrees away sees only the flat-terrain dip
    far = int((peak + 40) % p.n_azimuths)
    assert p.horizon_elevation_deg[far] == pytest.approx(-dip_deg(0.0), abs=1e-3)


def test_mesa_angular_width_matches_geometry():
    dist, rad, ht = 10_000.0, 500.0, 300.0
    fn, _ = mesa_at(120.0, dist, rad, ht)
    p = profile(synth_window("mesa", 20_000, 20.0, fn), 0.0, az_step=0.25)
    raised = p.horizon_elevation_deg > 0.2
    width = raised.sum() * 0.25
    expected = 2 * math.degrees(math.asin(rad / dist))  # ~5.7 deg
    assert width == pytest.approx(expected, abs=1.0)


def test_nearer_or_taller_obstructions_raise_the_horizon():
    base = {}
    for name, dist, ht in [("far", 15_000.0, 300.0), ("near", 6_000.0, 300.0), ("tall", 15_000.0, 900.0)]:
        fn, _ = mesa_at(45.0, dist, 400.0, ht)
        base[name] = profile(synth_window(name, 20_000, 20.0, fn), 0.0).horizon_elevation_deg.max()
    assert base["near"] > base["far"] and base["tall"] > base["far"]


# ---------------------------------------------------------------- curvature (gate: lunar curvature)

def test_curvature_lowers_a_distant_obstruction_relative_to_a_flat_plane_model():
    dist, ht = 60_000.0, 2000.0
    fn, _centre = mesa_at(10.0, dist, 1500.0, ht)
    w = synth_window("far", 80_000, 20.0, fn)
    p = profile(w, 0.0, az_step=0.5)
    got = p.horizon_elevation_deg.max()
    edge = dist - 1500.0  # nearest top edge
    planar = math.degrees(math.atan2(ht, edge))
    curvature_drop = math.degrees(edge / (2 * R))  # classical d/(2R) correction
    assert got < planar - 0.5                                   # curvature matters at 60 km (~0.9 deg)
    assert got == pytest.approx(planar - curvature_drop, abs=0.03)  # and matches the first-order theory
    # exact independent value
    assert got == pytest.approx(elev3d_deg((LAT0, LON0), 0.0, GEOD.fwd(LON0, LAT0, 10.0, edge)[1::-1], ht), abs=0.03)


def test_a_mountain_below_the_curvature_horizon_is_correctly_hidden():
    # A 100 m hill 60 km away from a 2 m observer is below the sphere's horizon (~ d^2/2R = 1.04 km drop).
    fn, _ = mesa_at(200.0, 60_000.0, 800.0, 100.0)
    p = profile(synth_window("hidden", 80_000, 20.0, fn), 2.0)
    # no azimuth is raised above the clear-sky dip by the hidden hill
    assert p.horizon_elevation_deg.max() == pytest.approx(-dip_deg(2.0), abs=2e-3)


# ---------------------------------------------------------------- observer height (gate: observer height)

def test_observer_height_effects_match_independent_geometry():
    dist, ht = 10_000.0, 300.0
    fn, _centre = mesa_at(80.0, dist, 500.0, ht)
    w = synth_window("mesa", 20_000, 20.0, fn)
    peaks = {}
    for h in (0.0, 5.0, 50.0):
        p = profile(w, h)
        peaks[h] = p.horizon_elevation_deg.max()
        edge = GEOD.fwd(LON0, LAT0, 80.0, dist - 500.0 * 1.0)  # nearest top edge (sphere approx)
        assert peaks[h] == pytest.approx(elev3d_deg((LAT0, LON0), h, (edge[1], edge[0]), ht), abs=0.03)
        # the clear-sky dip also moves with height
        off = p.horizon_elevation_deg[(round(80.0 / 0.5) + 60) % p.n_azimuths]
        assert off == pytest.approx(-dip_deg(h), abs=2e-3)
    assert peaks[0.0] > peaks[5.0] > peaks[50.0]  # looking at a fixed hilltop from higher up lowers it


def test_observer_height_is_relative_to_the_dem_surface_at_the_site():
    # Terrain at constant 3000 m: observer height 2 m means 3002 m radius; the dip uses the 3000 m terrain sphere.
    p = profile(synth_window("flat", 10_000, 20.0, lambda x, y: 3000.0), 2.0)
    assert p.meta["observer"]["ground_height_m"] == pytest.approx(3000.0)
    assert p.meta["observer"]["observer_radius_height_m"] == pytest.approx(3002.0)
    assert p.horizon_elevation_deg[0] == pytest.approx(-dip_deg(2.0, 3000.0), abs=1e-4)


@pytest.mark.parametrize("bad", [-1.0, float("nan"), float("inf"), 1e6, None, True, "2"])
def test_invalid_observer_height_is_rejected(bad):
    with pytest.raises(InvalidInputError):
        profile(synth_window("flat", 3_000, 20.0, lambda x, y: 0.0), bad)


# ---------------------------------------------------------------- edge cases (gate: edge cases)

def test_nodata_is_skipped_counted_flagged_and_never_filled():
    _fn, centre = mesa_at(90.0, 5_000.0, 300.0, 0.0)  # NaN patch, flat elsewhere
    cx, cy = lonlat_to_xy(*centre)
    w = synth_window("gap", 12_000, 20.0, lambda x, y: 0.0,
                     nan_fn=lambda x, y: np.hypot(x - cx, y - cy) <= 300.0)
    p = profile(w, 2.0, az_step=0.5)
    i_gap = round(90.0 / 0.5)
    assert p.data_gap[i_gap] and p.n_missing_samples[i_gap] > 10
    assert not p.data_gap[(i_gap + 180) % p.n_azimuths] and p.n_missing_samples[(i_gap + 180) % 720] == 0
    assert p.horizon_elevation_deg[i_gap] == pytest.approx(-dip_deg(2.0), abs=1e-3)  # nothing invented
    assert p.summary()["n_data_gap"] > 0


def test_observer_on_nodata_or_outside_coverage_is_an_error_not_a_guess():
    x0, y0 = lonlat_to_xy(LAT0, LON0)
    w = synth_window("nan_here", 3_000, 20.0, lambda x, y: 0.0,
                     nan_fn=lambda x, y: np.hypot(x - x0, y - y0) <= 100.0)
    with pytest.raises(DataMissingError):
        profile(w, 2.0)
    far = synth_window("elsewhere", 3_000, 20.0, lambda x, y: 0.0, *lonlat_to_xy(-80.0, 100.0))
    with pytest.raises(OutOfDemCoverageError):
        profile(far, 2.0)
    with pytest.raises(OutOfDemCoverageError):
        TerrainSampler([])
    with pytest.raises(OutOfDemCoverageError):  # northern hemisphere has no south-polar grid
        compute_horizon(TerrainSampler([synth_window("f", 3_000, 20.0, lambda x, y: 0.0)]), 10.0, 0.0, 2.0)


def test_ray_leaving_coverage_is_flagged_truncated_unless_provably_complete():
    # 1 km window: edge is *before* the 2 m observer's tangent distance (2.6 km) -> unknown terrain beyond.
    small = profile(synth_window("small", 1_000, 20.0, lambda x, y: 0.0), 2.0)
    assert small.truncated.all() and np.all(small.range_covered_km < 1.45)  # square window: corners reach 1.41 km
    # 20 km window: edge is beyond the tangent; terrain is no higher than 0 m anywhere in the data -> complete.
    big = profile(synth_window("big", 20_000, 20.0, lambda x, y: 0.0), 2.0)
    assert not big.truncated.any()
    # a tall peak anywhere in the data (Hmax = 5000 m) makes the same geometry non-provable -> truncated
    peak = synth_window("peak", 20_000, 20.0, lambda x, y: np.where((x > x.max() - 100) & (y > y.max() - 100), 5000.0, 0.0))
    pk = profile(peak, 2.0)
    assert pk.truncated.mean() > 0.9  # all but the few azimuths that already see the peak itself


def test_user_range_cap_is_reported_as_truncation():
    p = profile(synth_window("flat", 20_000, 20.0, lambda x, y: 0.0), 2.0, max_range_km=1.0)
    assert p.truncated.all() and np.allclose(p.range_covered_km, 1.0, atol=0.02)


def test_multires_uses_the_finest_window_and_does_not_fill_nodata_from_coarser():
    _fn, centre = mesa_at(0.0, 3_000.0, 200.0, 0.0)
    cx, cy = lonlat_to_xy(*centre)
    fine = synth_window("fine", 5_000, 20.0, lambda x, y: 0.0, nan_fn=lambda x, y: np.hypot(x - cx, y - cy) <= 200.0)
    coarse = synth_window("coarse", 20_000, 320.0, lambda x, y: 0.0)
    p = compute_horizon(TerrainSampler([coarse, fine]), LAT0, LON0, 2.0, az_step_deg=1.0)
    assert p.data_gap[0]  # the fine window's NoData is reported even though the coarse window has a value there
    assert p.limiting_pixel_size_m[0] in (20.0, 320.0)
    assert p.range_covered_km.min() > 15.0  # coarse window extends coverage beyond the fine one


def test_pole_site_azimuth_convention_matches_the_stage3_tie_break():
    # Observer at the pole, mesa along the supplied-longitude meridian: north = away from the pole along lon.
    lat, lon = -90.0, 0.0
    x0, y0 = 0.0, 0.0
    lon2, lat2, _ = GEOD.fwd(lon, lat, 0.0, 8_000.0)  # az 0 from the pole -> along lon = 0 meridian
    cx, cy = lonlat_to_xy(lat2, lon2)
    w = synth_window("pole", 15_000, 20.0, lambda x, y: np.where(np.hypot(x - cx, y - cy) < 400, 300.0, 0.0), x0, y0)
    p = compute_horizon(TerrainSampler([w]), lat, lon, 0.0, az_step_deg=0.5)
    assert abs(((p.azimuth_deg[int(np.nanargmax(p.horizon_elevation_deg))] + 180) % 360) - 180) <= 0.5


@pytest.mark.parametrize(("kw", "field"), [
    ({"az_step_deg": 0.0}, "az_step_deg"), ({"az_step_deg": 7.0}, "az_step_deg"),
    ({"az_step_deg": float("nan")}, "az_step_deg"), ({"step_m": -1.0}, "step_m"),
    ({"max_range_km": 0.0}, "max_range_km"), ({"max_range_km": 0.001}, "max_range_km"),
    ({"az_step_deg": 0.01, "step_m": 1.0}, "az_step_deg"),
])
def test_bad_parameters_are_rejected_with_the_field_named(kw, field):
    with pytest.raises(InvalidInputError) as e:
        profile(synth_window("flat", 3_000, 20.0, lambda x, y: 0.0), 2.0, **kw)
    assert e.value.field == field


def test_azimuth_queries_and_wraparound():
    fn, _ = mesa_at(359.0, 8_000.0, 400.0, 300.0)  # straddles north
    p = profile(synth_window("m", 15_000, 20.0, fn), 0.0, az_step=1.0)
    assert p.horizon_at(0.0) == pytest.approx(p.horizon_elevation_deg[0])
    assert p.horizon_at(360.0) == pytest.approx(p.horizon_at(0.0))
    mid = p.horizon_at(0.5)
    assert min(p.horizon_elevation_deg[0], p.horizon_elevation_deg[1]) <= mid <= max(p.horizon_elevation_deg[0],
                                                                                    p.horizon_elevation_deg[1])
    assert p.max_between(350.0, 10.0) >= max(p.horizon_elevation_deg[[359, 0, 1]])  # wraps through north
    assert p.max_between(100.0, 100.0) == pytest.approx(p.horizon_elevation_deg[100])
    assert p.max_between(100.0, 120.0) <= p.horizon_elevation_deg.max()


def test_deterministic():
    w = synth_window("m", 10_000, 20.0, mesa_at(10.0, 5_000.0, 300.0, 100.0)[0])
    a, b = profile(w, 2.0), profile(w, 2.0)
    assert np.array_equal(a.horizon_elevation_deg, b.horizon_elevation_deg)


# ---------------------------------------------------------------- window selection and cache

def _write_registry(root: Path, windows: dict[str, DemWindow]) -> None:
    (root / "dem_cache").mkdir(parents=True, exist_ok=True)
    entries = {}
    for wid, w in windows.items():
        f = root / "dem_cache" / f"{wid}.tif"
        m = w.meta
        with rasterio.open(f, "w", driver="GTiff", dtype="float32", count=1, width=m.width, height=m.height,
                           transform=from_origin(m.left_m, m.top_m, m.pixel_size_m, m.pixel_size_m),
                           nodata=float("nan")) as dst:
            dst.write(w.data, 1)
        d = dict(m.raw)
        d["sha256"] = sha256_file(f)
        entries[wid] = d
    (root / "manifests").mkdir(parents=True, exist_ok=True)
    (root / "manifests" / "dem_windows.json").write_text(json.dumps({"windows": entries}))


def test_nested_window_of_equal_resolution_is_dropped_and_coarse_one_kept(tmp_path):
    big = synth_window("big20", 8_000, 20.0, lambda x, y: 0.0)
    small = synth_window("small20", 2_000, 20.0, lambda x, y: 0.0)
    coarse = synth_window("coarse", 20_000, 320.0, lambda x, y: 0.0)
    _write_registry(tmp_path, {"big20": big, "small20": small, "coarse": coarse})
    chosen = [w.meta.window_id for w in select_windows(DemRegistry(tmp_path), LAT0, LON0)]
    assert chosen == ["big20", "coarse"]
    with pytest.raises(InvalidInputError):
        select_windows(DemRegistry(tmp_path), LAT0, LON0, ["nope"])
    with pytest.raises(OutOfDemCoverageError) as e:
        select_windows(DemRegistry(tmp_path), -70.0, -100.0)
    assert "No flat-terrain or synthetic fallback" in e.value.message


def test_cache_memory_then_disk_then_invalidation(tmp_path):
    _write_registry(tmp_path, {"w": synth_window("w", 6_000, 20.0, mesa_at(30.0, 4_000.0, 300.0, 100.0)[0])})
    svc = HorizonService(tmp_path)
    a = svc.profile(LAT0, LON0, 2.0, az_step_deg=1.0)
    assert a.served_from == "computed"
    b = svc.profile(LAT0, LON0, 2.0, az_step_deg=1.0)
    assert b.served_from == "memory" and np.array_equal(a.horizon_elevation_deg, b.horizon_elevation_deg)
    svc2 = HorizonService(tmp_path)  # fresh process: only the disk entry exists
    c = svc2.profile(LAT0, LON0, 2.0, az_step_deg=1.0)
    assert c.served_from == "disk" and np.array_equal(a.horizon_elevation_deg, c.horizon_elevation_deg)
    assert c.meta == a.meta and c.truncated.dtype == bool
    # a different observer height is a different key and is genuinely recomputed
    d = svc2.profile(LAT0, LON0, 5.0, az_step_deg=1.0)
    assert d.served_from == "computed" and d.horizon_elevation_deg.max() != c.horizon_elevation_deg.max()
    # use_cache=False always recomputes
    assert svc2.profile(LAT0, LON0, 2.0, az_step_deg=1.0, use_cache=False).served_from == "computed"
    # corrupt the disk entry: it is ignored and recomputed, never trusted
    entry = next((tmp_path / "results" / "horizon").glob(f"{a.meta['cache_key']}.npz"))
    entry.write_bytes(b"not an npz")
    assert HorizonService(tmp_path).profile(LAT0, LON0, 2.0, az_step_deg=1.0).served_from == "computed"


def test_cache_key_changes_when_the_dem_changes(tmp_path):
    w1 = synth_window("w", 6_000, 20.0, lambda x, y: 0.0)
    _write_registry(tmp_path / "a", {"w": w1})
    w2 = synth_window("w", 6_000, 20.0, lambda x, y: 1.0)
    _write_registry(tmp_path / "b", {"w": w2})
    ka = HorizonService(tmp_path / "a").profile(LAT0, LON0, 2.0, az_step_deg=2.0).meta["cache_key"]
    kb = HorizonService(tmp_path / "b").profile(LAT0, LON0, 2.0, az_step_deg=2.0).meta["cache_key"]
    assert ka != kb


# ---------------------------------------------------------------- REAL data: independent cross-check

needs_dem = pytest.mark.skipif(
    not (DATA / "dem_cache" / "im2_20m_r10km.tif").exists(),
    reason="LOLA windows absent; run scripts/extract_dem_window.py")
needs_80km = pytest.mark.skipif(
    not (DATA / "dem_cache" / "im2_20m_r80km.tif").exists(),
    reason="80 km window absent; run scripts/extract_dem_window.py im2_20m_r80km")
IM2 = (-84.79059, 29.19567)


def _independent_horizon(tif: Path, lat, lon, h_obs_above_surface, az_deg, step=20.0, max_km=9.5):
    """Hand-written reference: pyproj spherical geodesic points, GeoTIFF's own affine transform, scalar bilinear,
    3-D vector elevation. Shares no code with lunarnav.horizon."""
    crs_stere = pyproj.CRS.from_proj4("+proj=stere +lat_0=-90 +lat_ts=-90 +lon_0=0 +R=1737400 +units=m")
    tr = pyproj.Transformer.from_crs(crs_stere.geodetic_crs, crs_stere, always_xy=True)
    with rasterio.open(tif) as ds:
        arr = ds.read(1).astype(float)
        inv = ~ds.transform

        def height(la, lo):
            x, y = tr.transform(lo, la)
            c, r = inv @ (x, y)
            c, r = c - 0.5, r - 0.5
            c0, r0 = math.floor(c), math.floor(r)
            if c0 < 0 or r0 < 0 or c0 + 1 >= arr.shape[1] or r0 + 1 >= arr.shape[0]:
                return None
            fc, fr = c - c0, r - r0
            b = arr[r0:r0 + 2, c0:c0 + 2]
            return (b[0, 0] * (1 - fc) + b[0, 1] * fc) * (1 - fr) + (b[1, 0] * (1 - fc) + b[1, 1] * fc) * fr

        h_o = height(lat, lon) + h_obs_above_surface
        best = -90.0
        for k in range(1, int(max_km * 1000 / step) + 1):
            lo2, la2, _ = GEOD.fwd(lon, lat, az_deg, k * step)
            z = height(la2, lo2)
            if z is None or not math.isfinite(z):
                break
            best = max(best, elev3d_deg((lat, lon), h_o, (la2, lo2), z))
        return best


@needs_dem
def test_real_im2_matches_a_hand_written_independent_implementation():
    tif = DATA / "dem_cache" / "im2_20m_r10km.tif"
    svc = HorizonService(DATA)
    p = svc.profile(*IM2, 2.0, az_step_deg=1.0, window_ids=["im2_20m_r10km"], use_cache=False)
    worst = 0.0
    for az in (0, 17, 45, 90, 133, 180, 222, 270, 301, 359):
        ref = _independent_horizon(tif, *IM2, 2.0, float(az), max_km=9.5)
        # engine uses the full ~9.9 km; the independent run stops at 9.5 km: engine >= reference, and equal
        # unless the limiting sample lies beyond 9.5 km
        ours = p.horizon_elevation_deg[az]
        if p.horizon_distance_km[az] <= 9.5:
            worst = max(worst, abs(ours - ref))
        else:
            assert ours >= ref - 1e-6
    assert worst < 1e-4, f"engine disagrees with independent implementation by {worst:.2e} deg"


@needs_dem
def test_real_im2_profile_is_sane_and_honestly_flagged():
    p = HorizonService(DATA).profile(*IM2, 2.0, az_step_deg=1.0, window_ids=["im2_20m_r10km"], use_cache=False)
    h = p.horizon_elevation_deg
    assert np.isfinite(h).all() and -5.0 < h.min() and h.max() < 60.0
    assert 9.9 < p.range_covered_km.min() and p.range_covered_km.max() < 14.2  # 10 km square: edge..corner
    assert p.limiting_pixel_size_m.max() == 20.0
    assert p.meta["windows"][0]["window_id"] == "im2_20m_r10km"
    assert p.truncated.any()                      # 10 km is not enough to prove completeness: must be flagged
    assert p.meta["observer"]["ground_height_m"] == pytest.approx(5321.0, abs=50.0)  # NAIF catalogue height


@needs_dem
@needs_80km
def test_real_20m_windows_are_the_same_data_where_they_overlap():
    a = DemWindow.load(DemRegistry(DATA).windows["im2_20m_r10km"], DATA)
    b_reg = DemRegistry(DATA)
    b = DemWindow.load(b_reg.windows["im2_20m_r80km"], DATA)
    ma, mb = a.meta, b.meta
    c0 = round((ma.left_m - mb.left_m) / 20.0)
    r0 = round((mb.top_m - ma.top_m) / 20.0)
    sub = b.data[r0:r0 + ma.height, c0:c0 + ma.width]
    assert sub.shape == a.data.shape
    assert np.array_equal(np.nan_to_num(sub, nan=-9999), np.nan_to_num(a.data, nan=-9999))


@needs_dem
def test_real_im1_has_only_2km_of_data_so_everything_is_truncated():
    p = HorizonService(DATA).profile(-80.12759, 1.44587, 2.0, az_step_deg=5.0)
    assert p.truncated.all() and p.range_covered_km.max() < 2.9  # 2 km square window: edge..corner


@needs_dem
def test_a_site_inside_no_window_gets_an_error_not_a_flat_horizon():
    with pytest.raises(OutOfDemCoverageError):
        HorizonService(DATA).profile(-72.0, 200.0, 2.0)


@pytest.mark.skipif(not (DATA / "dem_cache" / "ch3_60m_r200km.tif").exists(),
                    reason="60 m window absent: run scripts/extract_dem_window.py ch3_60m_r200km")
def test_real_chandrayaan3_horizon_is_complete_from_the_60m_window():
    p = HorizonService(DATA).profile(-69.3741, 32.32, 2.0, az_step_deg=1.0)
    assert not p.truncated.any() and not p.data_gap.any()                 # every azimuth certified against the window
    assert set(p.limiting_pixel_size_m.tolist()) == {60.0}                 # only the 60 m window was used
    assert p.range_covered_km.min() > 100.0                                 # 200 km window, nothing cut short
    assert 0.0 < p.horizon_elevation_deg.min() and p.horizon_elevation_deg.max() < 5.0   # gently rolling terrain here
