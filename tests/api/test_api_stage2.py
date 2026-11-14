from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from lunarnav_api.main import create_app

DATA = Path(__file__).resolve().parents[2] / "data"
client = TestClient(create_app(), raise_server_exceptions=False)
HAVE = all((DATA / "dem_cache" / f"{w}.tif").exists()
           for w in ("im2_20m_r10km", "im2_320m_r160km", "im1_20m_r2km"))
needs_data = pytest.mark.skipif(not HAVE, reason="run scripts/extract_dem_window.py")
ERROR_KEYS = {"code", "message", "field", "details", "request_id"}


def test_sites_lists_catalogue_with_sources_and_conventions():
    body = client.get("/sites").json()
    assert body["lon_convention"] == "east_positive" and body["lat_convention"] == "planetocentric"
    ids = {s["id"]: s for s in body["sites"]}
    assert ids["im2-athena"]["kind"] == "confirmed_landing"
    assert ids["im2-intended"]["kind"] == "intended_target"
    assert all(s["sources"] and s["sources"][0]["url"].startswith("https://") for s in ids.values())
    assert body["pending_regions"], "unsourced regions must be listed as pending, not as sites"
    assert not any("haworth" in s["name"].lower() for s in body["sites"])


def test_validate_accepts_custom_coordinates_and_normalises_longitude():
    r = client.post("/sites/validate", json={"lat": -89.5, "lon": 270})
    assert r.status_code == 200
    body = r.json()
    assert body["site"]["kind"] == "custom" and body["site"]["lon_deg_east"] == -90
    assert body["site"]["sources"] == []


@pytest.mark.parametrize(
    ("payload", "field"),
    [({"lat": 91, "lon": 0}, "lat"), ({"lat": -85, "lon": 400}, "lon"),
     ({"lat": "abc", "lon": 0}, "lat"), ({"lat": True, "lon": 0}, "lat"),
     ({"lat": None, "lon": 0}, "lat")],
)
def test_validate_rejects_bad_input_with_field(payload, field):
    r = client.post("/sites/validate", json=payload)
    assert r.status_code == 422
    body = r.json()
    assert set(body) == ERROR_KEYS and body["code"] == "INVALID_INPUT" and body["field"] == field


def test_validate_missing_field_uses_error_contract():
    r = client.post("/sites/validate", json={"lat": -85})
    assert r.status_code == 422 and r.json()["code"] == "INVALID_INPUT"


@needs_data
def test_validate_reports_coverage_without_inventing_it():
    covered = client.post("/sites/validate", json={"lat": -84.79059, "lon": 29.19567}).json()
    assert covered["dem_coverage_status"] == "covered"
    assert covered["covering_windows"][0]["pixel_size_m"] == 20.0  # finest first
    not_covered = client.post("/sites/validate", json={"lat": -69.3741, "lon": 32.32}).json()
    assert not_covered["dem_coverage_status"] == "not_covered"
    assert not_covered["covering_windows"] == []


@needs_data
def test_dem_elevation_returns_value_with_provenance():
    r = client.get("/dem/elevation", params={"lat": -84.79059, "lon": 29.19567})
    assert r.status_code == 200
    b = r.json()
    assert abs(b["elevation_m"] - 5321.0) <= 25.0
    assert b["product_id"] == "LDEM_80S_20MPP_ADJ" and b["pixel_size_m"] == 20.0
    assert len(b["sha256"]) == 64 and b["source_url"].startswith("https://pgda.gsfc.nasa.gov/")
    assert b["data_class"] == "measured_interpolated" and "reference sphere" in b["units"]


def test_dem_elevation_out_of_coverage_is_explicit_error():
    r = client.get("/dem/elevation", params={"lat": -60.0, "lon": 0.0})
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == "OUT_OF_DEM_COVERAGE" and set(body) == ERROR_KEYS


def test_dem_elevation_northern_latitude_is_out_of_coverage_not_a_crash():
    r = client.get("/dem/elevation", params={"lat": 45.0, "lon": 0.0})
    assert r.status_code == 422 and r.json()["code"] == "OUT_OF_DEM_COVERAGE"


def test_dem_elevation_validation_errors():
    assert client.get("/dem/elevation", params={"lat": 120, "lon": 0}).json()["field"] == "lat"
    r = client.get("/dem/elevation", params={"lat": "x", "lon": 0})
    assert r.status_code == 422 and r.json()["code"] == "INVALID_INPUT"
    r = client.get("/dem/elevation", params={"lat": -85, "lon": 0, "window_id": "nope"})
    assert r.status_code == 422 and r.json()["field"] == "window_id"


@needs_data
def test_dem_windows_expose_provenance_and_resolution():
    ws = {w["window_id"]: w for w in client.get("/dem/windows").json()}
    assert ws["im2_20m_r10km"]["pixel_size_m"] == 20.0
    assert ws["im2_320m_r160km"]["pixel_size_m"] == 320.0 and ws["im2_320m_r160km"]["overview_level"] == 3
    assert all(len(w["sha256"]) == 64 and w["valid_fraction"] == 1.0 for w in ws.values())


def test_app_fails_fast_on_a_policy_violating_catalogue(tmp_path, monkeypatch):
    (tmp_path / "catalogue").mkdir()
    (tmp_path / "catalogue" / "sites.json").write_text(
        '{"lat_convention":"planetocentric","lon_convention":"east_positive","sites":'
        '[{"id":"a","name":"A","kind":"confirmed_landing","lat_deg":-85,"lon_deg_east":0,'
        '"sources":[]}]}')
    monkeypatch.setenv("LUNARNAV_DATA_DIR", str(tmp_path))
    from lunarnav_api.config import get_settings
    get_settings.cache_clear()
    try:
        with pytest.raises(ValueError, match="no primary-source"):
            create_app()
    finally:
        monkeypatch.delenv("LUNARNAV_DATA_DIR")
        get_settings.cache_clear()
