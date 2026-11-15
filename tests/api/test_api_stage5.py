"""Stage 5 API contract tests for /visibility/* (real ephemeris + LOLA windows; skipped if absent)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from lunarnav_api.main import create_app

DATA = Path(__file__).resolve().parents[2] / "data"
HAVE = all((DATA / "kernels" / f).exists() for f in
           ("naif0012.tls", "de440s.bsp", "moon_pa_de440_200625.bpc", "moon_de440_250416.tf")) \
    and all((DATA / "dem_cache" / f).exists() for f in ("im2_20m_r10km.tif", "im2_320m_r160km.tif", "im2_20m_r80km.tif"))
needs_data = pytest.mark.skipif(not HAVE, reason="kernels/DEM windows missing; see docs/DEV_SETUP.md")

client = TestClient(create_app(), raise_server_exceptions=False)
ERROR_KEYS = {"code", "message", "field", "details", "request_id"}


def body(**over):
    b = {"site": {"site_id": "im2-athena"}, "start_utc": "2027-02-09T00:00:00Z", "end_utc": "2027-02-14T00:00:00Z",
         "step_seconds": 3600, "az_step_deg": 1.0}
    b.update(over)
    return b


def assert_error(r, status, code, field=None):
    assert r.status_code == status, r.text
    j = r.json()
    assert set(j) == ERROR_KEYS and j["code"] == code
    if field:
        assert j["field"] == field


def test_input_errors_are_explicit():
    assert_error(client.post("/visibility/series", json=body(site={})), 422, "INVALID_INPUT", "site")
    assert_error(client.post("/visibility/series", json=body(site={"site_id": "nope"})), 422, "INVALID_INPUT", "site_id")
    assert_error(client.post("/visibility/series", json=body(start_utc="2027-02-09T00:00:00")), 422, "INVALID_INPUT")
    assert_error(client.post("/visibility/series", json=body(end_utc="2027-02-01T00:00:00Z")), 422, "INVALID_INPUT",
                 "end_utc")
    assert_error(client.post("/visibility/series", json=body(step_seconds=0.5)), 422, "INVALID_INPUT", "step_seconds")
    assert_error(client.post("/visibility/series", json=body(step_seconds=1, end_utc="2027-03-30T00:00:00Z")),
                 422, "INVALID_INPUT", "step_seconds")


@needs_data
def test_range_bodies_band_and_dem_errors():
    assert_error(client.post("/visibility/series", json=body(start_utc="2040-01-01T00:00:00Z",
                                                             end_utc="2040-01-02T00:00:00Z")),
                 422, "EPHEMERIS_OUT_OF_RANGE")
    assert_error(client.post("/visibility/series", json=body(bodies=["moon"])), 422, "INVALID_INPUT", "bodies")
    assert_error(client.post("/visibility/series", json=body(position_uncertainty_m=-5)), 422, "INVALID_INPUT",
                 "position_uncertainty_m")
    r = client.post("/visibility/series", json=body(site={"lat": -72.0, "lon": 200.0}))
    assert_error(r, 422, "OUT_OF_DEM_COVERAGE")
    assert "No flat-terrain or synthetic fallback" in r.json()["message"]


@needs_data
def test_series_contract_and_position_sensitivity_fields():
    r = client.post("/visibility/series", json=body())
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["data_class"] == "calculated" and j["observer"]["observer_height_is_default_assumption"] is True
    assert j["observer"]["observer_height_above_surface_m"] == 2.0 and j["observer"]["site_id"] == "im2-athena"
    ps = j["position_sensitivity"]
    assert ps["status"] == "computed" and ps["assumed_position_uncertainty_m"] == 100.0
    assert "+/-100 m" in ps["assumption"] and "not an error bar" in ps["kind"]
    for b in ("sun", "earth"):
        d = j["bodies"][b]
        n = j["window"]["n_samples"]
        for k in ("centre_visible", "any_part_visible", "fully_visible", "headline_visible", "horizon_complete",
                  "position_sensitivity_deg", "headline_state_robust_to_position", "geometric_headline_above_local_horizontal"):
            assert len(d["series"][k]) == n, k
        h = d["headline"]
        assert h["position_sensitivity"]["status"] == "computed"
        assert "metric_bands" in h["position_sensitivity"] and "boundary_bands" in h["position_sensitivity"]
        assert d["states"].keys() == {"centre", "any_part", "fully"}
    assert j["bodies"]["sun"]["headline_state"] == "any_part_visible"
    assert j["bodies"]["earth"]["headline_state"] == "centre_visible"
    assert j["horizon"]["summary"]["n_truncated"] == 0


@needs_data
def test_intervals_endpoint_is_per_body_and_has_no_step_arrays():
    sun = client.post("/visibility/intervals", json=body(bodies=["sun"], include_series=True))
    assert sun.status_code == 200
    j = sun.json()
    assert list(j["bodies"]) == ["sun"] and "series" not in j["bodies"]["sun"]
    iv = j["bodies"]["sun"]["headline"]["intervals"] + j["bodies"]["sun"]["headline"]["not_visible_intervals"]
    assert iv and all({"start_utc", "end_utc", "open_start", "open_end", "start_band", "end_band"} <= set(i) for i in iv)
    earth = client.post("/visibility/intervals", json=body(bodies=["earth"], position_uncertainty_m=0)).json()
    assert earth["position_sensitivity"]["status"] == "not_computed"
    assert earth["bodies"]["earth"]["headline"]["position_sensitivity"]["status"] == "not_computed"


@needs_data
def test_configurable_band_and_at_endpoint():
    j = client.post("/visibility/intervals", json=body(position_uncertainty_m=40.0, bodies=["earth"])).json()
    assert j["position_sensitivity"]["assumed_position_uncertainty_m"] == 40.0
    r = client.get("/visibility/at", params={"time_utc": "2027-02-10T00:00:00Z", "site_id": "im2-athena",
                                              "az_step_deg": 1.0})
    assert r.status_code == 200, r.text
    a = r.json()
    for b in ("sun", "earth"):
        assert "states" not in a["bodies"][b] and len(a["bodies"][b]["series"]["headline_visible"]) == 1


@needs_data
def test_im1_flags_insufficient_terrain_and_does_not_extrapolate_sensitivity():
    j = client.post("/visibility/series", json=body(site={"site_id": "im1-odysseus"}, az_step_deg=5.0)).json()
    assert j["position_sensitivity"]["status"] == "not_computed" and "insufficient" in j["position_sensitivity"]["reason"]
    assert j["horizon"]["summary"]["n_truncated"] > 0
