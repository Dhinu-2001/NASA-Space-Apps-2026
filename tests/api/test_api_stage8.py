"""Stage 8 API contract tests for POST /engineering/solar (real ephemeris + LOLA windows; skipped if absent)."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from lunarnav_api.main import create_app

DATA = Path(__file__).resolve().parents[2] / "data"
HAVE = all((DATA / "kernels" / f).exists() for f in
           ("naif0012.tls", "de440s.bsp", "moon_pa_de440_200625.bpc", "moon_de440_250416.tf")) \
    and all((DATA / "dem_cache" / f).exists() for f in ("im2_20m_r10km.tif", "im2_320m_r160km.tif", "im2_20m_r80km.tif", "im1_20m_r2km.tif"))
needs_data = pytest.mark.skipif(not HAVE, reason="kernels/DEM windows missing; see docs/DEV_SETUP.md")

client = TestClient(create_app(), raise_server_exceptions=False)
ERROR_KEYS = {"code", "message", "field", "details", "request_id"}
BASE = {"site": {"site_id": "im2-athena"}, "start_utc": "2027-01-26T00:00:00Z", "duration_days": 10, "step_seconds": 3600,
        "az_step_deg": 1.0, "area_m2": 1.0, "efficiency": 0.30}


def assert_error(r, status, code, field=None):
    assert r.status_code == status, r.text
    j = r.json()
    assert set(j) == ERROR_KEYS and j["code"] == code
    if field:
        assert j["field"] == field


def test_panel_inputs_are_required_and_validated_before_any_calculation():
    for missing in ("area_m2", "efficiency"):
        body = {k: v for k, v in BASE.items() if k != missing}
        assert_error(client.post("/engineering/solar", json=body), 422, "INVALID_INPUT", missing)
    for bad, field in (({"area_m2": 0}, "area_m2"), ({"area_m2": -3}, "area_m2"), ({"area_m2": "big"}, "area_m2"),
                       ({"efficiency": 0}, "efficiency"), ({"efficiency": 1.2}, "efficiency"), ({"efficiency": None}, "efficiency"),
                       ({"irradiance_w_m2": 10}, "irradiance_w_m2"), ({"irradiance_w_m2": 99999}, "irradiance_w_m2")):
        assert_error(client.post("/engineering/solar", json={**BASE, **bad}), 422, "INVALID_INPUT", field)
    assert_error(client.post("/engineering/solar", json={**BASE, "site": {}}), 422, "INVALID_INPUT", "site")
    assert_error(client.post("/engineering/solar", json={**BASE, "position_uncertainty_m": 0}), 422, "INVALID_INPUT",
                 "position_uncertainty_m")


@needs_data
def test_solar_energy_contract_labels_bands_and_geometric_counterpart():
    r = client.post("/engineering/solar", json=BASE)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["status"] == "supported" and j["data_class"] == "calculated"
    assert "UPPER BOUND" in j["kind"] and "not battery state" in j["kind"]
    p = j["panel"]
    assert p["area_m2"] == 1.0 and p["efficiency"] == 0.3 and p["irradiance_w_m2"] == 1361.0
    assert p["irradiance_is_default_assumption"] is True and p["peak_electrical_power_w"] == pytest.approx(408.3)
    tc = j["terrain_corrected"]
    e = tc["energy_wh"]
    assert e["band"][0] <= e["nominal"] <= e["band"][1]                       # position band carried through
    assert j["position_sensitivity"]["status"] == "computed" and "+/-100 m" in j["position_sensitivity"]["assumption"]
    assert set(j["geometric"]) >= {"energy_wh", "mean_power_w", "sunlit_hours"}
    assert "energy_wh_terrain_minus_geometric" in j["terrain_effect"]
    assert tc["longest_without_direct_sunlight"]["includes_open_interval"] in (True, False)
    assert j["partial_disc_bracket"]["whole_disc_energy_wh"] <= j["partial_disc_bracket"]["any_part_energy_wh"]
    assert len(j["assumptions"]) >= 4 and any("not a power budget" in x for x in j["limitations"])
    assert j["provenance"]["model_version"] and j["provenance"]["ephemeris"]["kernels"]      # reproducible metadata
    json.dumps(j)


@needs_data
def test_energy_is_consistent_with_the_scenario_endpoint_it_reuses():
    scn = client.post("/scenarios/evaluate", json={k: v for k, v in BASE.items() if k not in ("area_m2", "efficiency")}).json()
    sol = client.post("/engineering/solar", json=BASE).json()
    vis = scn["bodies"]["sun"]["terrain_corrected"]["total_visible_s"]
    assert sol["scenario_id"] == scn["id"]                                     # same scenario, reused from the cache
    assert sol["terrain_corrected"]["energy_wh"]["nominal"] == pytest.approx(vis["nominal"] * 0.3 * 1361.0 / 3600.0)
    assert sol["terrain_corrected"]["sunlit_hours"]["band"][1] == pytest.approx(vis["band"][1] / 3600.0)


@needs_data
def test_panel_and_irradiance_scale_the_result_and_the_default_is_flagged():
    a = client.post("/engineering/solar", json=BASE).json()
    b = client.post("/engineering/solar", json={**BASE, "area_m2": 4.0, "irradiance_w_m2": 1300.0}).json()
    assert b["panel"]["irradiance_is_default_assumption"] is False
    ratio = 4.0 * 1300.0 / 1361.0
    assert b["terrain_corrected"]["energy_wh"]["nominal"] == pytest.approx(a["terrain_corrected"]["energy_wh"]["nominal"] * ratio)
    assert b["terrain_corrected"]["energy_wh"]["band"][1] == pytest.approx(a["terrain_corrected"]["energy_wh"]["band"][1] * ratio)


@needs_data
def test_a_smaller_position_uncertainty_gives_a_narrower_energy_band():
    wide = client.post("/engineering/solar", json={**BASE, "start_utc": "2027-01-15T00:00:00Z", "duration_days": 30,
                                                   "step_seconds": 900}).json()["terrain_corrected"]["energy_wh"]["band"]
    narrow = client.post("/engineering/solar", json={**BASE, "start_utc": "2027-01-15T00:00:00Z", "duration_days": 30,
                                                     "step_seconds": 900, "position_uncertainty_m": 20}).json()["terrain_corrected"]["energy_wh"]["band"]
    assert (narrow[1] - narrow[0]) < (wide[1] - wide[0])


@needs_data
@pytest.mark.parametrize("site", [{"site_id": "im1-odysseus"}, {"site_id": "chandrayaan3-shiv-shakti"}, {"lat": -90.0, "lon": 0.0}])
def test_sites_without_terrain_support_get_a_label_and_no_energy_figure(site):
    r = client.post("/engineering/solar", json={**BASE, "site": site, "az_step_deg": 5.0})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["status"] == "terrain_data_insufficient" and j["reason"] and j["reason_code"]
    for forbidden in ("terrain_corrected", "geometric", "panel", "partial_disc_bracket"):
        assert forbidden not in j
    assert "wh" not in " ".join(j.keys()).lower()


def test_capability_is_listed_honestly_as_implemented_unvalidated_and_narrow():
    cap = {c["key"]: c for c in client.get("/version").json()["capabilities"]}["engineering"]
    assert cap["status"] == "implemented_unvalidated" and cap["stage"] == 8
    assert "upper bound" in cap["title"].lower() and "antenna" not in cap["title"].lower()   # does not claim what is not built
    assert client.post("/engineering/antenna", json={}).status_code == 501                    # antenna/slope/temperature still deferred
