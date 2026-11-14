"""Stage 3 API contract tests for /ephemeris/series and /ephemeris/position."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from lunarnav_api.main import create_app

DATA = Path(__file__).resolve().parents[2] / "data"
HAVE_KERNELS = all(
    (DATA / "kernels" / f).exists()
    for f in ("naif0012.tls", "de440s.bsp", "moon_pa_de440_200625.bpc", "moon_de440_250416.tf"))
needs_kernels = pytest.mark.skipif(
    not HAVE_KERNELS, reason=r"kernels missing: run .\.venv\Scripts\python.exe scripts\fetch_kernels.py")

client = TestClient(create_app(), raise_server_exceptions=False)
ERROR_KEYS = {"code", "message", "field", "details", "request_id"}


def series(**over):
    body = {
        "site": {"site_id": "im2-athena"},
        "start_utc": "2027-01-15T00:00:00Z",
        "end_utc": "2027-01-15T06:00:00Z",
        "step_seconds": 3600,
    }
    body.update(over)
    return client.post("/ephemeris/series", json=body)


def assert_error(r, status, code, field=None):
    assert r.status_code == status, r.text
    body = r.json()
    assert set(body) == ERROR_KEYS
    assert body["code"] == code
    if field:
        assert body["field"] == field


@needs_kernels
def test_series_shape_units_and_provenance():
    r = series()
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["data_class"] == "calculated" and b["n_samples"] == 7
    assert b["times_utc"][0] == "2027-01-15T00:00:00Z" and b["times_utc"][-1] == "2027-01-15T06:00:00Z"
    assert set(b["bodies"]) == {"sun", "earth"}
    for name in ("sun", "earth"):
        for key in ("azimuth_deg", "elevation_deg", "range_km", "angular_diameter_deg", "light_time_s"):
            assert len(b["bodies"][name][key]) == 7
    assert b["observer"]["site_id"] == "im2-athena" and b["observer"]["frame"] == "MOON_ME"
    assert b["observer"]["lat_deg"] == pytest.approx(-84.79059)
    assert "degrees clockwise from local north" in b["units"]["azimuth_deg"]
    assert b["provenance"]["frame"] == "MOON_ME"
    assert any("terrain is not applied" in n for n in b["notes"])
    # the first sample reproduces the value Horizons gave for this instant (see validation fixture)
    assert b["bodies"]["sun"]["azimuth_deg"][0] == pytest.approx(63.561267244, abs=1e-6)
    assert b["bodies"]["sun"]["elevation_deg"][0] == pytest.approx(3.073663681, abs=1e-6)
    assert b["bodies"]["earth"]["azimuth_deg"][0] == pytest.approx(322.685454515, abs=1e-5)
    assert b["bodies"]["earth"]["elevation_deg"][0] == pytest.approx(9.317491677, abs=1e-5)


@needs_kernels
def test_custom_coordinates_and_single_body():
    r = series(site={"lat": -89.0, "lon": 350.0}, bodies=["sun"])
    assert r.status_code == 200, r.text
    b = r.json()
    assert list(b["bodies"]) == ["sun"] and b["observer"]["site_id"] is None
    assert b["observer"]["lon_deg_east"] == pytest.approx(-10.0)  # 350 E normalised, not wrapped wrongly


@needs_kernels
def test_position_endpoint_matches_series_first_sample():
    r = client.get("/ephemeris/position", params={
        "site_id": "im2-athena", "time_utc": "2027-01-15T00:00:00Z", "body": "sun"})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["n_samples"] == 1 and list(b["bodies"]) == ["sun"]
    assert b["bodies"]["sun"]["azimuth_deg"][0] == pytest.approx(63.561267244, abs=1e-6)


@needs_kernels
def test_position_with_custom_coordinates_and_height():
    r = client.get("/ephemeris/position", params={
        "lat": -84.79059, "lon": 29.19567, "height_m": 5321, "time_utc": "2027-01-15T00:00:00Z"})
    assert r.status_code == 200, r.text
    assert r.json()["observer"]["height_m"] == 5321.0


def test_site_selection_errors():
    assert_error(series(site={}), 422, "INVALID_INPUT", "site")
    assert_error(series(site={"site_id": "nope"}), 422, "INVALID_INPUT", "site_id")
    assert_error(series(site={"site_id": "im2-athena", "lat": 1, "lon": 2}), 422,
                 "INVALID_INPUT", "site")
    assert_error(series(site={"lat": 10}), 422, "INVALID_INPUT", "site")
    assert_error(series(site={"lat": 95, "lon": 0}), 422, "INVALID_INPUT", "lat")
    assert_error(series(site={"lat": "x", "lon": 0}), 422, "INVALID_INPUT", "lat")


def test_time_errors():
    assert_error(series(start_utc="2027-01-15T00:00:00"), 422, "INVALID_INPUT", "start_utc")
    assert_error(series(end_utc="2027-01-15T00:00:00+05:30"), 422, "INVALID_INPUT", "end_utc")
    assert_error(series(end_utc="2027-01-14T00:00:00Z"), 422, "INVALID_INPUT", "end_utc")
    assert_error(series(start_utc="2040-01-01T00:00:00Z", end_utc="2040-01-02T00:00:00Z"), 422,
                 "EPHEMERIS_OUT_OF_RANGE", "start_utc")
    assert_error(series(start_utc="2020-01-01T00:00:00Z", end_utc="2020-01-02T00:00:00Z"), 422,
                 "EPHEMERIS_OUT_OF_RANGE", "start_utc")


def test_sampling_errors():
    assert_error(series(step_seconds=0.2), 422, "INVALID_INPUT", "step_seconds")
    r = series(end_utc="2027-03-15T00:00:00Z", step_seconds=1)
    assert_error(r, 422, "INVALID_INPUT", "step_seconds")
    assert r.json()["details"]["max_samples"] == 50_000
    assert_error(series(bodies=["moon"]), 422, "INVALID_INPUT", "bodies")
    assert_error(series(bodies=[]), 422, "INVALID_INPUT", "bodies")
    assert_error(series(bodies=["sun", "sun"]), 422, "INVALID_INPUT", "bodies")
    assert_error(client.post("/ephemeris/series", json={"start_utc": "x"}), 422, "INVALID_INPUT")


def test_position_errors():
    assert_error(client.get("/ephemeris/position", params={"time_utc": "2027-01-15T00:00:00Z"}),
                 422, "INVALID_INPUT", "site")
    assert_error(client.get("/ephemeris/position", params={
        "site_id": "im2-athena", "time_utc": "2027-01-15T00:00:00Z", "body": "mars"}),
        422, "INVALID_INPUT", "body")


def test_missing_kernels_give_503_data_missing(tmp_path, monkeypatch):
    # An app pointed at a data dir without kernels must fail explicitly, never fall back.
    import shutil

    (tmp_path / "catalogue").mkdir()
    shutil.copy(DATA / "catalogue" / "sites.json", tmp_path / "catalogue" / "sites.json")
    monkeypatch.setenv("LUNARNAV_DATA_DIR", str(tmp_path))
    from lunarnav_api.config import get_settings

    get_settings.cache_clear()
    try:
        app_client = TestClient(create_app(), raise_server_exceptions=False)
        r = app_client.post("/ephemeris/series", json={
            "site": {"site_id": "im2-athena"}, "start_utc": "2027-01-15T00:00:00Z",
            "end_utc": "2027-01-15T01:00:00Z", "step_seconds": 3600})
        assert_error(r, 503, "DATA_MISSING")
    finally:
        get_settings.cache_clear()
