"""Stage 9 API tests: GET /provenance, calculation metadata in results, behaviour on a partial installation."""

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from lunarnav import MODEL_VERSION
from lunarnav_api.config import get_settings
from lunarnav_api.main import create_app

DATA = Path(__file__).resolve().parents[2] / "data"
HAVE = all((DATA / "kernels" / f).exists() for f in
           ("naif0012.tls", "de440s.bsp", "moon_pa_de440_200625.bpc", "moon_de440_250416.tf")) \
    and all((DATA / "dem_cache" / f).exists() for f in ("im2_20m_r10km.tif", "im2_320m_r160km.tif", "im2_20m_r80km.tif"))
needs_data = pytest.mark.skipif(not HAVE, reason="kernels/DEM windows missing; see docs/DEV_SETUP.md")
ERROR_KEYS = {"code", "message", "field", "details", "request_id"}


def test_provenance_lists_what_the_application_is_built_from():
    j = TestClient(create_app()).get("/provenance").json()
    assert j["model_version"] == MODEL_VERSION
    assert set(j) >= {"git_commit", "software", "spice_kernels", "dem_windows", "site_catalogue", "validation_fixtures",
                      "constants", "data_classes"}
    assert j["software"]["python"].startswith("3.12") and "spiceypy" in j["software"]
    assert j["constants"]["moon_reference_radius_m"] == 1_737_400.0 and "assumptions" in j["constants"]["note"]
    assert {"measured_interpolated", "calculated", "assumption"} <= set(j["data_classes"])
    assert all(len(w["sha256"]) == 64 and w["source_url"].startswith("https://") for w in j["dem_windows"])
    sites = {s["id"]: s for s in j["site_catalogue"]["sites"]}
    assert "im2-athena" in sites and all(s["sources"] for s in sites.values())     # every site cites a source
    if j["spice_kernels"]:
        assert all(len(k["sha256"]) == 64 for k in j["spice_kernels"])


@needs_data
def test_visibility_and_scenario_results_carry_reproducible_metadata():
    client = TestClient(create_app())
    body = {"site": {"site_id": "im2-athena"}, "start_utc": "2027-02-09T00:00:00Z", "end_utc": "2027-02-12T00:00:00Z",
            "step_seconds": 3600, "az_step_deg": 1.0, "include_series": False}
    a = client.post("/visibility/intervals", json=body).json()
    b = client.post("/visibility/intervals", json=body).json()
    assert a["provenance"] == b["provenance"] and a["provenance"]["model_version"] == MODEL_VERSION
    assert [w["window_id"] for w in a["provenance"]["terrain"]["dem_windows"]] == ["im2_20m_r80km", "im2_320m_r160km"]
    s = client.post("/scenarios/evaluate", json={"site": {"site_id": "im2-athena"}, "start_utc": "2027-02-09T00:00:00Z",
                                                  "duration_days": 3, "step_seconds": 3600, "az_step_deg": 1.0}).json()
    assert s["status"] == "supported" and s["provenance"]["ephemeris"]["kernels"]
    assert s["provenance"]["parameters"]["position_uncertainty_m"] == 100.0


@pytest.fixture
def partial_install(tmp_path, monkeypatch):
    """A data directory with the manifests and catalogue but NO kernels and NO DEM files."""
    shutil.copytree(DATA / "manifests", tmp_path / "manifests")
    (tmp_path / "catalogue").mkdir()
    (tmp_path / "catalogue" / "sites.json").write_bytes((DATA / "catalogue" / "sites.json").read_bytes())
    monkeypatch.setenv("LUNARNAV_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    yield TestClient(create_app(), raise_server_exceptions=False)
    get_settings.cache_clear()


def test_partial_install_fails_with_typed_errors_and_rebuild_hints_never_with_numbers(partial_install):
    c = partial_install
    r = c.get("/ephemeris/position", params={"site_id": "im2-athena", "time_utc": "2027-01-15T00:00:00Z"})
    assert r.status_code == 503 and set(r.json()) == ERROR_KEYS and r.json()["code"] == "DATA_MISSING"
    assert "fetch_kernels" in str(r.json()["details"])
    r = c.get("/horizon/profile", params={"site_id": "im2-athena"})
    assert r.status_code == 503 and r.json()["code"] == "DATA_MISSING" and r.json()["field"] == "dem"
    assert "extract_dem_window" in r.json()["message"]
    r = c.post("/visibility/series", json={"site": {"site_id": "im2-athena"}, "start_utc": "2027-01-15T00:00:00Z",
                                           "end_utc": "2027-01-16T00:00:00Z", "step_seconds": 3600})
    assert r.status_code == 503 and r.json()["code"] == "DATA_MISSING"
    # a scenario degrades to a labelled non-result (terrain files missing), with no figures
    s = c.post("/scenarios/evaluate", json={"site": {"site_id": "im2-athena"}, "start_utc": "2027-01-15T00:00:00Z",
                                            "duration_days": 2, "step_seconds": 3600}).json()
    assert s["status"] == "terrain_data_insufficient" and s["reason_code"] == "DATA_MISSING" and "bodies" not in s


def test_partial_install_still_reports_what_is_missing_and_stays_honest_about_capabilities(partial_install):
    c = partial_install
    prov = c.get("/provenance")
    assert prov.status_code == 200
    j = prov.json()
    assert j["spice_kernels"] is None and "kernel" in j["spice_kernels_error"].lower()
    assert c.get("/health").status_code == 200 and c.get("/version").status_code == 200
    sites = c.get("/sites")
    assert sites.status_code == 200 and len(sites.json()["sites"]) >= 3          # the catalogue does not need kernels/DEM
