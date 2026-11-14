"""Stage 4 API contract tests for GET /horizon/profile (real LOLA windows; skipped if absent)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from lunarnav_api.main import create_app

DATA = Path(__file__).resolve().parents[2] / "data"
needs_dem = pytest.mark.skipif(
    not (DATA / "dem_cache" / "im2_20m_r10km.tif").exists(),
    reason=r"LOLA windows missing: run .\.venv\Scripts\python.exe -I scripts\extract_dem_window.py")

client = TestClient(create_app(), raise_server_exceptions=False)
ERROR_KEYS = {"code", "message", "field", "details", "request_id"}


def assert_error(r, status, code, field=None):
    assert r.status_code == status, r.text
    body = r.json()
    assert set(body) == ERROR_KEYS
    assert body["code"] == code
    if field:
        assert body["field"] == field


@needs_dem
def test_default_observer_height_is_the_c9_assumption_and_is_labelled():
    p = {"site_id": "im2-athena", "az_step_deg": 5.0}
    d = client.get("/horizon/profile", params=p).json()
    e = client.get("/horizon/profile", params={**p, "observer_height_m": 2.0}).json()
    assert d["observer"]["observer_height_above_surface_m"] == 2.0
    assert d["observer"]["observer_height_is_default_assumption"] is True
    assert e["observer"]["observer_height_is_default_assumption"] is False
    assert d["horizon_elevation_deg"] == e["horizon_elevation_deg"]


def test_site_selection_errors():
    assert_error(client.get("/horizon/profile", params={"observer_height_m": 2}), 422, "INVALID_INPUT", "site")
    assert_error(client.get("/horizon/profile", params={"observer_height_m": 2, "site_id": "im2-athena",
                                                        "lat": -85, "lon": 0}), 422, "INVALID_INPUT", "site")
    assert_error(client.get("/horizon/profile", params={"observer_height_m": 2, "site_id": "nope"}),
                 422, "INVALID_INPUT", "site_id")


@needs_dem
def test_bad_numbers_are_rejected_with_the_field_named():
    base = {"site_id": "im2-athena", "az_step_deg": 5.0}
    assert_error(client.get("/horizon/profile", params={**base, "observer_height_m": -1}), 422,
                 "INVALID_INPUT", "observer_height_m")
    assert_error(client.get("/horizon/profile", params={**base, "observer_height_m": "nan"}), 422,
                 "INVALID_INPUT", "observer_height_m")
    assert_error(client.get("/horizon/profile", params={"site_id": "im2-athena", "observer_height_m": 2,
                                                        "az_step_deg": 7}), 422, "INVALID_INPUT", "az_step_deg")
    assert_error(client.get("/horizon/profile", params={**base, "observer_height_m": 2, "max_range_km": 0}),
                 422, "INVALID_INPUT", "max_range_km")
    assert_error(client.get("/horizon/profile", params={**base, "observer_height_m": "abc"}), 422, "INVALID_INPUT")


def test_no_dem_means_error_not_a_flat_horizon():
    r = client.get("/horizon/profile", params={"site_id": "chandrayaan3-vikram", "observer_height_m": 2})
    if r.status_code == 422 and r.json()["field"] == "site_id":  # catalogue id differs; use coordinates
        r = client.get("/horizon/profile", params={"lat": -69.3741, "lon": 32.32, "observer_height_m": 2})
    assert_error(r, 422, "OUT_OF_DEM_COVERAGE")
    assert "No flat-terrain or synthetic fallback" in r.json()["message"]
    assert_error(client.get("/horizon/profile", params={"lat": 10, "lon": 0, "observer_height_m": 2}),
                 422, "OUT_OF_DEM_COVERAGE")


@needs_dem
def test_im2_profile_shape_provenance_and_honesty_fields():
    r = client.get("/horizon/profile", params={"site_id": "im2-athena", "observer_height_m": 2.0,
                                               "az_step_deg": 1.0, "use_cache": False})
    assert r.status_code == 200, r.text
    b = r.json()
    n = 360
    assert b["n_azimuths"] == n and b["data_class"] == "calculated_from_measured_interpolated"
    for k in ("azimuth_deg", "horizon_elevation_deg", "horizon_distance_km", "limiting_pixel_size_m",
              "range_covered_km", "n_missing_samples", "unseen_bound_deg", "truncated", "data_gap"):
        assert len(b[k]) == n, k
    assert b["azimuth_deg"][:3] == [0.0, 1.0, 2.0]
    o = b["observer"]
    assert o["site_id"] == "im2-athena" and o["observer_height_above_surface_m"] == 2.0
    assert o["catalogue_reference_height_m"] == 5321.0 and o["frame"] == "MOON_ME"
    assert o["observer_radius_height_m"] == pytest.approx(o["ground_height_m"] + 2.0)
    assert all(w["sha256"] and w["source_url"] for w in b["provenance"]["windows"])
    assert b["provenance"]["parameters"]["reference_radius_m"] == 1_737_400.0
    assert "NOT a visibility result" in b["notes"][0] and set(b["units"]) >= {"azimuth_deg", "truncated"}
    assert b["summary"]["n_azimuths"] == n


@needs_dem
def test_cache_is_reported_and_results_are_identical():
    params = {"lat": -84.79059, "lon": 29.19567, "observer_height_m": 2.0, "az_step_deg": 2.0}
    first = client.get("/horizon/profile", params={**params, "use_cache": False}).json()
    second = client.get("/horizon/profile", params=params).json()
    third = client.get("/horizon/profile", params=params).json()
    assert third["served_from"] in ("memory", "disk") and second["served_from"] in ("computed", "memory", "disk")
    assert first["horizon_elevation_deg"] == third["horizon_elevation_deg"]
    assert first["observer"]["site_id"] is None


@needs_dem
def test_observer_height_changes_the_result():
    p = {"site_id": "im2-athena", "az_step_deg": 5.0}
    low = client.get("/horizon/profile", params={**p, "observer_height_m": 0.0}).json()
    high = client.get("/horizon/profile", params={**p, "observer_height_m": 30.0}).json()
    assert low["horizon_elevation_deg"] != high["horizon_elevation_deg"]
    assert high["observer"]["observer_radius_height_m"] == pytest.approx(low["observer"]["observer_radius_height_m"] + 30.0)
