"""Stage 6 API contract tests for /scenarios/* (real ephemeris + LOLA windows; skipped if absent)."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from lunarnav_api.main import create_app

DATA = Path(__file__).resolve().parents[2] / "data"
HAVE = all((DATA / "kernels" / f).exists() for f in
           ("naif0012.tls", "de440s.bsp", "moon_pa_de440_200625.bpc", "moon_de440_250416.tf")) \
    and all((DATA / "dem_cache" / f).exists()
            for f in ("im2_20m_r10km.tif", "im2_320m_r160km.tif", "im2_20m_r80km.tif", "im1_20m_r2km.tif"))
needs_data = pytest.mark.skipif(not HAVE, reason="kernels/DEM windows missing; see docs/DEV_SETUP.md")

client = TestClient(create_app(), raise_server_exceptions=False)
ERROR_KEYS = {"code", "message", "field", "details", "request_id"}
P = {"duration_days": 10.0, "step_seconds": 1800.0, "az_step_deg": 1.0}


def assert_error(r, status, code, field=None):
    assert r.status_code == status, r.text
    j = r.json()
    assert set(j) == ERROR_KEYS and j["code"] == code
    if field:
        assert j["field"] == field


def test_input_errors_are_explicit():
    base = {"site": {"site_id": "im2-athena"}, "start_utc": "2027-01-26T00:00:00Z"}
    assert_error(client.post("/scenarios/evaluate", json={**base, "site": {}}), 422, "INVALID_INPUT", "site")
    assert_error(client.post("/scenarios/evaluate", json={**base, "position_uncertainty_m": 0}), 422,
                 "INVALID_INPUT", "position_uncertainty_m")
    assert_error(client.post("/scenarios/evaluate", json={**base, "start_utc": "2027-01-26"}), 422, "INVALID_INPUT")
    assert_error(client.post("/scenarios/evaluate", json={**base, "duration_days": 500}), 422, "INVALID_INPUT",
                 "duration_days")
    assert_error(client.post("/scenarios/compare", json={}), 422, "INVALID_INPUT", "scenarios")
    assert_error(client.post("/scenarios/compare", json={"scenarios": [base], "sites": [{"site_id": "im2-athena"}],
                                                         "start_utc_list": ["2027-01-26T00:00:00Z"]}),
                 422, "INVALID_INPUT", "scenarios")
    assert_error(client.post("/scenarios/delay", json={"site": {"site_id": "im2-athena"},
                                                       "baseline_start_utc": "2027-01-26T00:00:00Z",
                                                       "offsets_days": [0]}), 422, "INVALID_INPUT", "offsets_days")
    assert_error(client.get("/scenarios/" + "0" * 64), 404, "NOT_FOUND", "scenario_id")
    assert_error(client.get("/scenarios/not-an-id"), 404, "NOT_FOUND")


@needs_data
def test_evaluate_then_fetch_saved_scenario():
    body = {"site": {"site_id": "im2-athena"}, "start_utc": "2027-01-26T00:00:00Z", "label": "baseline", **P}
    r = client.post("/scenarios/evaluate", json=body)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["status"] == "supported" and len(j["id"]) == 64 and j["spec"]["label"] == "baseline"
    assert j["spec"]["observer_height_is_default_assumption"] is True
    assert {"terrain_corrected", "geometric"} <= set(j["bodies"]["sun"])
    saved = client.get(f"/scenarios/{j['id']}")
    assert saved.status_code == 200 and saved.json()["id"] == j["id"] and saved.json()["served_from"] == "disk"
    assert saved.json()["bodies"] == j["bodies"]


@needs_data
def test_compare_grid_labels_insufficient_sites_and_ranks_only_supported():
    r = client.post("/scenarios/compare", json={
        "sites": [{"site_id": "im2-athena"}, {"site_id": "im1-odysseus"}, {"lat": -90.0, "lon": 0.0}],
        "start_utc_list": ["2027-01-26T00:00:00Z", "2027-02-05T00:00:00Z"], **P})
    assert r.status_code == 200, r.text
    j = r.json()
    assert len(j["scenarios"]) == 6
    assert {s["status"] for s in j["scenarios"]} == {"supported", "terrain_data_insufficient"}
    assert len(j["excluded_terrain_data_insufficient"]) == 4
    ranked = {row["site_id"] for rk in j["rankings"] for row in rk["ranking"]}
    assert ranked == {"im2-athena"}
    assert len(j["deltas_vs_baseline"]) == 1 and j["deltas_vs_baseline"][0]["delta_band_method"] == "paired"
    assert any("terrain data insufficient" in n for n in j["notes"])
    assert any("Sites without terrain support" in g for g in j["reading_guide"])
    assert "fraction" not in json.dumps(j["excluded_terrain_data_insufficient"])


@needs_data
def test_compare_explicit_scenarios_and_baseline_index():
    s = {"site": {"site_id": "im2-athena"}, **P}
    r = client.post("/scenarios/compare", json={
        "scenarios": [{**s, "start_utc": "2027-01-26T00:00:00Z", "label": "a"},
                      {**s, "start_utc": "2027-02-05T00:00:00Z", "label": "b"}], "baseline_index": 1, **P})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["baseline_id"] == j["scenarios"][1]["id"] and len(j["deltas_vs_baseline"]) == 1
    assert j["deltas_vs_baseline"][0]["scenario_id"] == j["scenarios"][0]["id"]
    assert_error(client.post("/scenarios/compare", json={"scenarios": [{**s, "start_utc": "2027-01-26T00:00:00Z"}],
                                                         "baseline_index": 3}), 422, "INVALID_INPUT", "baseline_index")


@needs_data
def test_delay_endpoint_default_window_is_labelled_and_deltas_carry_bands():
    r = client.post("/scenarios/delay", json={"site": {"site_id": "im2-athena"},
                                              "baseline_start_utc": "2027-01-26T00:00:00Z",
                                              "offsets_days": [4], "step_seconds": 3600.0, "az_step_deg": 1.0})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["status"] == "supported" and j["baseline"]["spec"]["duration_days"] == 14.0
    d = j["delays"][0]
    assert d["offset_days"] == 4.0 and d["delta_vs_baseline"]["delta_band_method"] == "paired"
    assert d["delta_vs_baseline"]["bodies"]["sun"]["terrain_corrected"]["visible_fraction"]["delta_band"] is not None
    assert "geometric" in d["delta_vs_baseline"]["bodies"]["sun"]
    ins = client.post("/scenarios/delay", json={"site": {"site_id": "im1-odysseus"},
                                                "baseline_start_utc": "2027-01-26T00:00:00Z", "offsets_days": [4],
                                                "step_seconds": 3600.0, "az_step_deg": 5.0}).json()
    assert ins["status"] == "terrain_data_insufficient" and ins["delays"] == []
