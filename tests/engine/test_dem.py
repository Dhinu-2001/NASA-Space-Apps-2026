"""DEM tests.

Two kinds, labelled explicitly:
  * SYNTHETIC fixtures (tiny rasters built in tmp dirs) - used ONLY to test algorithms and error
    handling against analytic truth. They are never exposed as lunar data.
  * REAL-DATA tests - use the extracted LOLA windows (git-ignored). They skip, with the command
    to create them, when the windows are not present.
"""

import hashlib
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
from lunarnav.errors import (
    DataMissingError,
    InvalidInputError,
    OutOfDemCoverageError,
)
from lunarnav.sites import load_catalogue
from rasterio.transform import from_origin

DATA = Path(__file__).resolve().parents[2] / "data"
R = 1_737_400.0


# ---------------------------------------------------------------- projection (no data needed)

def test_pole_maps_to_origin_and_longitude_axes_are_east_positive():
    assert lonlat_to_xy(-90.0, 123.0) == pytest.approx((0.0, 0.0), abs=1e-6)
    x, y = lonlat_to_xy(-85.0, 0.0)  # lon 0 -> +y
    assert x == pytest.approx(0.0, abs=1e-6) and y > 0
    x, y = lonlat_to_xy(-85.0, 90.0)  # 90E -> +x
    assert y == pytest.approx(0.0, abs=1e-6) and x > 0
    x, y = lonlat_to_xy(-85.0, -90.0)  # 90W -> -x
    assert x < 0
    x, y = lonlat_to_xy(-85.0, 180.0)  # 180 -> -y
    assert y < 0


def test_known_radius_for_80s_matches_closed_form():
    # rho = 2R tan(5 deg)
    _x, y = lonlat_to_xy(-80.0, 0.0)
    assert y == pytest.approx(2 * R * math.tan(math.radians(5.0)))


def test_round_trip():
    rng = np.random.default_rng(0)
    lat = rng.uniform(-90, -60, 500)
    lon = rng.uniform(-180, 180, 500)
    x, y = lonlat_to_xy(lat, lon)
    lat2, lon2 = xy_to_lonlat(x, y)
    assert np.allclose(lat, lat2, atol=1e-9)
    dlon = (lon - lon2 + 180) % 360 - 180
    mask = lat > -89.9999  # longitude is ill-conditioned at the pole
    assert np.allclose(dlon[mask], 0, atol=1e-7)


def test_northern_hemisphere_is_rejected_not_wrapped():
    with pytest.raises(OutOfDemCoverageError):
        lonlat_to_xy(0.0, 10.0)
    with pytest.raises(OutOfDemCoverageError):
        lonlat_to_xy(np.array([-80.0, 5.0]), np.array([0.0, 0.0]))


def test_projection_agrees_with_pyproj_on_the_products_own_crs():
    pyproj = pytest.importorskip("pyproj")
    manifest = DATA / "manifests" / "dem_windows.json"
    if not manifest.exists():
        pytest.skip("dem_windows.json missing")
    wkt = next(iter(json.loads(manifest.read_text())["windows"].values()))["crs_wkt"]
    crs = pyproj.CRS.from_wkt(wkt)
    tr = pyproj.Transformer.from_crs(crs.geodetic_crs, crs, always_xy=True)
    for lat, lon in [(-84.79059, 29.19567), (-80.12759, 1.44587), (-89.0, -120.0),
                     (-82.0, 200.0 - 360), (-89.9999, 45.0)]:
        px, py = tr.transform(lon, lat)
        assert lonlat_to_xy(lat, lon) == pytest.approx((px, py), abs=1e-4)  # 0.1 mm


# ---------------------------------------------------------------- synthetic fixtures

def _make_window(root: Path, wid: str, data: np.ndarray, left: float, top: float, res: float,
                 product="SYNTHETIC_TEST_ONLY") -> dict:
    (root / "dem_cache").mkdir(parents=True, exist_ok=True)
    f = root / "dem_cache" / f"{wid}.tif"
    with rasterio.open(f, "w", driver="GTiff", dtype="float32", count=1, width=data.shape[1],
                       height=data.shape[0], transform=from_origin(left, top, res, res),
                       nodata=float("nan")) as dst:
        dst.write(data.astype("float32"), 1)
    return {
        "product_id": product, "file": f"dem_cache/{wid}.tif", "sha256": sha256_file(f),
        "pixel_size_m": res, "left_m": left, "top_m": top, "width": data.shape[1],
        "height": data.shape[0], "valid_fraction": float(np.isfinite(data).mean()),
        "z_min_m": float(np.nanmin(data)), "z_max_m": float(np.nanmax(data)),
        "source_url": "https://example.invalid/synthetic", "overview_level": None,
        "units": "m", "nodata": "NaN",
    }


def _registry(root: Path, windows: dict) -> DemRegistry:
    (root / "manifests").mkdir(parents=True, exist_ok=True)
    (root / "manifests" / "dem_windows.json").write_text(json.dumps({"windows": windows}))
    return DemRegistry(root)


def _plane(n=40, res=20.0, left=-400.0, top=400.0):
    """z = 1000 + 0.5*x - 0.25*y at pixel centres (bilinear interpolation is exact on a plane)."""
    cols = left + (np.arange(n) + 0.5) * res
    rows = top - (np.arange(n) + 0.5) * res
    xx, yy = np.meshgrid(cols, rows)
    return 1000.0 + 0.5 * xx - 0.25 * yy, (left, top, res)


def _plane_registry(tmp_path):
    x0, y0 = lonlat_to_xy(-85.0, 30.0)
    z, (left, top, res) = _plane(left=x0 - 400, top=y0 + 400)
    meta = _make_window(tmp_path, "w", z, left, top, res)
    return _registry(tmp_path, {"w": meta}), (x0, y0, left, top, res, z), meta


def test_bilinear_reproduces_an_analytic_plane(tmp_path):
    reg, (x0, y0, *_), _ = _plane_registry(tmp_path)
    for dx, dy in [(0.0, 0.0), (13.7, -91.3), (-250.2, 310.9), (379.0, -379.0)]:
        lat, lon = xy_to_lonlat(x0 + dx, y0 + dy)
        got = reg.elevation(lat, lon)
        expected = 1000.0 + 0.5 * (x0 + dx) - 0.25 * (y0 + dy)  # plane in absolute grid coords
        assert got.elevation_m == pytest.approx(expected, abs=0.01)
        assert got.method == "bilinear_pixel_centres" and got.pixel_size_m == 20.0
        assert got.data_class == "measured_interpolated"


def test_half_pixel_edge_is_out_of_coverage_not_extrapolated(tmp_path):
    reg, (_x0, y0, left, _top, res, _), _ = _plane_registry(tmp_path)
    lat, lon = xy_to_lonlat(left + 0.2 * res, y0)  # inside raster but < half a pixel from edge
    with pytest.raises(OutOfDemCoverageError):
        reg.elevation(lat, lon, window_id="w")


def test_nodata_neighbour_raises_data_missing_never_zero(tmp_path):
    x0, y0 = lonlat_to_xy(-85.0, 30.0)
    z, (left, top, res) = _plane(left=x0 - 400, top=y0 + 400)
    z[19, 19] = np.nan
    meta = _make_window(tmp_path, "w", z, left, top, res)
    reg = _registry(tmp_path, {"w": meta})
    # centre of the NaN pixel
    cx, cy = left + 19.5 * res, top - 19.5 * res
    lat, lon = xy_to_lonlat(cx, cy)
    with pytest.raises(DataMissingError) as e:
        reg.elevation(lat, lon)
    assert "NoData" in e.value.message
    # a point whose four neighbours are all valid is unaffected
    lat, lon = xy_to_lonlat(left + 5.5 * res, top - 5.5 * res)
    assert math.isfinite(reg.elevation(lat, lon).elevation_m)


def test_no_window_means_explicit_out_of_coverage_error(tmp_path):
    reg, *_ = _plane_registry(tmp_path)
    with pytest.raises(OutOfDemCoverageError) as e:
        reg.elevation(-70.0, 100.0)  # far from the window
    assert "No flat-terrain or synthetic fallback" in e.value.message
    with pytest.raises(OutOfDemCoverageError):
        reg.elevation(10.0, 0.0)  # northern hemisphere
    assert DemRegistry(tmp_path / "empty").covering(-85.0, 0.0) == []
    with pytest.raises(OutOfDemCoverageError):
        DemRegistry(tmp_path / "empty").elevation(-85.0, 0.0)


def test_missing_file_and_checksum_mismatch_are_refused(tmp_path):
    _reg, _, meta = _plane_registry(tmp_path)
    lat, lon = xy_to_lonlat(*lonlat_to_xy(-85.0, 30.0))
    # corrupt the file after the manifest was written
    f = tmp_path / meta["file"]
    f.write_bytes(f.read_bytes() + b"\x00")
    with pytest.raises(DataMissingError) as e:
        DemRegistry(tmp_path).elevation(lat, lon)
    assert "checksum" in e.value.message
    f.unlink()
    with pytest.raises(DataMissingError) as e:
        DemRegistry(tmp_path).elevation(lat, lon)
    assert "extract_dem_window" in e.value.message


def test_finest_window_wins_and_unknown_window_id_is_rejected(tmp_path):
    x0, y0 = lonlat_to_xy(-85.0, 30.0)
    zf, (lf, tf, rf) = _plane(n=40, res=20.0, left=x0 - 400, top=y0 + 400)
    zc, (lc, tc, rc) = _plane(n=10, res=200.0, left=x0 - 1000, top=y0 + 1000)
    reg = _registry(tmp_path, {
        "coarse": _make_window(tmp_path, "coarse", zc, lc, tc, rc),
        "fine": _make_window(tmp_path, "fine", zf, lf, tf, rf),
    })
    lat, lon = xy_to_lonlat(x0, y0)
    assert [m.window_id for m in reg.covering(lat, lon)] == ["fine", "coarse"]
    assert reg.elevation(lat, lon).window_id == "fine"
    assert reg.elevation(lat, lon, window_id="coarse").pixel_size_m == 200.0
    with pytest.raises(InvalidInputError):
        reg.elevation(lat, lon, window_id="nope")


def test_all_nan_finest_window_raises(tmp_path):
    x0, y0 = lonlat_to_xy(-85.0, 30.0)
    zc, (lc, tc, rc) = _plane(n=10, res=200.0, left=x0 - 1000, top=y0 + 1000)
    nan_win = np.full((40, 40), np.nan, dtype="float32")
    # np.nanmin on all-NaN warns; build the entry manually
    f = tmp_path / "dem_cache"
    f.mkdir()
    path = f / "fine.tif"
    with rasterio.open(path, "w", driver="GTiff", dtype="float32", count=1, width=40, height=40,
                       transform=from_origin(x0 - 400, y0 + 400, 20.0, 20.0),
                       nodata=float("nan")) as dst:
        dst.write(nan_win, 1)
    fine = {"product_id": "SYNTHETIC_TEST_ONLY", "file": "dem_cache/fine.tif",
            "sha256": sha256_file(path), "pixel_size_m": 20.0, "left_m": x0 - 400,
            "top_m": y0 + 400, "width": 40, "height": 40, "valid_fraction": 0.0, "z_min_m": 0,
            "z_max_m": 0, "source_url": "https://example.invalid", "overview_level": None}
    reg = _registry(tmp_path, {"fine": fine,
                               "coarse": _make_window(tmp_path, "coarse", zc, lc, tc, rc)})
    lat, lon = xy_to_lonlat(x0, y0)
    with pytest.raises(DataMissingError):  # explicit error, not the coarse value
        reg.elevation(lat, lon)


def test_window_meta_extent_properties():
    m = DemWindowMeta.from_dict("w", {
        "product_id": "p", "file": "f", "sha256": "0" * 64, "pixel_size_m": 20.0,
        "left_m": -100.0, "top_m": 300.0, "width": 10, "height": 5, "valid_fraction": 1.0,
        "z_min_m": 0.0, "z_max_m": 1.0, "source_url": "u"})
    assert (m.right_m, m.bottom_m) == (100.0, 200.0)


# ---------------------------------------------------------------- REAL LOLA data

WINDOWS = DATA / "dem_cache"
HAVE = all((WINDOWS / f"{w}.tif").exists() for w in
           ("im2_20m_r10km", "im2_320m_r160km", "im1_20m_r2km"))
needs_data = pytest.mark.skipif(
    not HAVE, reason="LOLA windows missing: run `python scripts/extract_dem_window.py`")

# A-priori tolerance (documented BEFORE looking at results): published altitudes are rounded to
# 1 m (NAIF kernels) and the lander position is uncertain by tens of metres; on the ~12 deg
# Odysseus slope one 20 m pixel spans ~4 m of height. We therefore accept |dz| <= 25 m.
HEIGHT_TOLERANCE_M = 25.0


@needs_data
@pytest.mark.parametrize("site_id", ["im2-athena", "im1-odysseus"])
def test_known_site_elevations_match_published_altitudes(site_id):
    site = {s.id: s for s in load_catalogue(DATA / "catalogue" / "sites.json")}[site_id]
    r = DemRegistry(DATA).elevation(site.lat_deg, site.lon_deg_east)
    assert r.pixel_size_m == 20.0 and r.product_id == "LDEM_80S_20MPP_ADJ"
    assert abs(r.elevation_m - site.reference_height_m) <= HEIGHT_TOLERANCE_M


@needs_data
def test_im1_height_also_within_lroc_published_value():
    r = DemRegistry(DATA).elevation(-80.12759, 1.44587)
    assert abs(r.elevation_m - 2579.0) <= HEIGHT_TOLERANCE_M  # LROC: 2579 m


@needs_data
def test_manifest_checksums_match_files_and_windows_are_fully_valid():
    reg = DemRegistry(DATA)
    assert set(reg.windows) >= {"im2_20m_r10km", "im2_320m_r160km", "im1_20m_r2km"}
    for wid, meta in reg.windows.items():
        w = DemWindow.load(meta, DATA)  # raises on checksum mismatch
        assert np.isfinite(w.data).all() and meta.valid_fraction == 1.0
        assert w.data.min() == pytest.approx(meta.z_min_m)
        assert w.data.max() == pytest.approx(meta.z_max_m)
        assert hashlib.sha256((DATA / meta.file).read_bytes()).hexdigest() == meta.sha256, wid


@needs_data
def test_window_geometry_is_on_the_product_grid():
    # LOLA grid: origin -304000 m, pixel edges at multiples of the pixel size from there.
    for meta in DemRegistry(DATA).windows.values():
        assert (meta.left_m + 304000.0) % meta.pixel_size_m == pytest.approx(0, abs=1e-6)
        assert (304000.0 - meta.top_m) % meta.pixel_size_m == pytest.approx(0, abs=1e-6)


@needs_data
def test_site_is_inside_its_window_with_surrounding_terrain_for_ray_casting():
    reg = DemRegistry(DATA)
    x, y = lonlat_to_xy(-84.79059, 29.19567)
    near, far = reg.windows["im2_20m_r10km"], reg.windows["im2_320m_r160km"]
    for m, half in ((near, 10_000.0), (far, 160_000.0)):
        assert m.left_m < x - half * 0.99 and x + half * 0.99 < m.right_m
        assert m.bottom_m < y - half * 0.99 and y + half * 0.99 < m.top_m


@needs_data
def test_chandrayaan_site_is_out_of_coverage_with_explicit_error():
    with pytest.raises(OutOfDemCoverageError):
        DemRegistry(DATA).elevation(-69.3741, 32.32)


@needs_data
def test_forced_coarse_window_returns_its_own_resolution_label():
    r = DemRegistry(DATA).elevation(-84.79059, 29.19567, window_id="im2_320m_r160km")
    assert r.pixel_size_m == 320.0 and r.window_id == "im2_320m_r160km"
