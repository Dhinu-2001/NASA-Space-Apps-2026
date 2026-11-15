"""Chandrayaan-3 (Statio Shiv Shakti) through the UNCHANGED horizon/visibility/scenario/solar pipeline.

Terrain comes from the 60 m LDEM_60S_60MPP_ADJ window ch3_60m_r200km (registered 2026-11-15; NOT yet owner-validated).
Real ephemeris + real DEM window; skipped if the data are absent.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from lunarnav_api.main import create_app

DATA = Path(__file__).resolve().parents[2] / "data"
HAVE = all((DATA / "kernels" / f).exists() for f in
           ("naif0012.tls", "de440s.bsp", "moon_pa_de440_200625.bpc", "moon_de440_250416.tf")) \
    and (DATA / "dem_cache" / "ch3_60m_r200km.tif").exists()
needs_data = pytest.mark.skipif(not HAVE, reason="kernels / ch3 DEM window missing; see docs/DEV_SETUP.md")

client = TestClient(create_app(), raise_server_exceptions=False)
SITE = {"site_id": "chandrayaan3-shiv-shakti"}
BODY = {"site": SITE, "start_utc": "2027-01-15T00:00:00Z", "duration_days": 30, "step_seconds": 900}


@needs_data
def test_horizon_is_complete_and_uses_only_the_60m_window():
    j = client.get("/horizon/profile", params={"site_id": SITE["site_id"], "az_step_deg": 1.0}).json()
    assert j["summary"]["n_truncated"] == 0 and j["summary"]["n_data_gap"] == 0
    assert [w["pixel_size_m"] for w in j["provenance"]["windows"]] == [60.0]
    assert j["provenance"]["windows"][0]["validation_status"].startswith("registered_unvalidated")   # label travels with the data
    assert j["data_class"] == "calculated_from_measured_interpolated"
    assert j["observer"]["ground_height_m"] == pytest.approx(529.34, abs=0.01)
    assert j["observer"]["catalogue_reference_height_m"] == 532.0       # reported beside the DEM height, never substituted


@needs_data
def test_scenario_is_supported_labelled_and_banded_like_im2():
    r = client.post("/scenarios/evaluate", json=BODY)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["status"] == "supported"
    sun = j["bodies"]["sun"]
    tc = sun["terrain_corrected"]["visible_fraction"]
    assert tc["band"][0] <= tc["nominal"] <= tc["band"][1]                      # position band present and consistent
    assert tc["nominal"] == pytest.approx(0.4913, abs=0.002)                    # reference run 2026-11-15
    assert sun["geometric"]["visible_fraction"]["nominal"] == pytest.approx(0.5140, abs=0.002)
    assert sun["terrain_effect"]["steps_blocked_by_terrain_only"] > 0           # terrain changes the answer, geometric is shown beside it
    assert sun["completeness"] == {**sun["completeness"], "steps_with_incomplete_horizon": 0, "visibility_is_upper_bound": False}
    assert sun["terrain_corrected"]["open_intervals"]["visible"] >= 1           # window-edge intervals are flagged
    earth = j["bodies"]["earth"]["terrain_corrected"]["visible_fraction"]
    assert earth["nominal"] == 1.0 and earth["band"] == [1.0, 1.0]              # Earth stays 11-22 deg up, horizon <= 2.5 deg
    # the not-yet-approved terrain product is named in the result's own limitations and window provenance
    assert any("NOT yet approved" in x and "ch3_60m_r200km" in x for x in j["limitations"])
    assert j["spec"]["position_uncertainty_m"] == 100 and j["spec"]["observer_height_is_default_assumption"] is True


@needs_data
def test_solar_energy_is_available_for_the_site_with_the_same_labelling():
    r = client.post("/engineering/solar", json={**BODY, "duration_days": 10, "step_seconds": 3600, "az_step_deg": 1.0,
                                                "area_m2": 1.0, "efficiency": 0.30})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["status"] == "supported" and "UPPER BOUND" in j["kind"]
    e = j["terrain_corrected"]["energy_wh"]
    assert e["band"][0] <= e["nominal"] <= e["band"][1] <= j["geometric"]["energy_wh"] * 1.001


@needs_data
def test_im1_is_still_insufficient_and_the_capability_list_is_unchanged():
    j = client.post("/scenarios/evaluate", json={**BODY, "site": {"site_id": "im1-odysseus"}}).json()
    assert j["status"] == "terrain_data_insufficient" and j["reason_code"] == "TERRAIN_NOT_CERTIFIED"
    caps = {c["key"]: c["status"] for c in client.get("/version").json()["capabilities"]}
    assert set(caps.values()) == {"validated"} and len(caps) == 7        # nothing new is claimed as validated here


@needs_data
def test_the_approved_im2_terrain_carries_no_such_caveat():
    j = client.post("/scenarios/evaluate", json={**BODY, "site": {"site_id": "im2-athena"}, "duration_days": 10,
                                                 "step_seconds": 3600, "az_step_deg": 1.0}).json()
    assert j["status"] == "supported" and not any("NOT yet approved" in x for x in j["limitations"])
