"""Stage 9 — scientific regression suite (golden scenarios, tolerance evidence, reproducibility, provenance).

PRE-DECLARED TOLERANCES (set before the values were pinned; rationale in docs/stage9/TOLERANCES.md):
  * horizon min / max / mean elevation        1e-6 deg   (same code + same DEM bytes => bit-level repeat expected;
                                                          any larger change means the science changed)
  * visible fraction                          1e-5
  * total visible time                        4 s        (<= 4 boundaries, each localised by bisection to 1 s)
  * transition times                          1 s        (bisection tolerance)
  * position-band width of a boundary         60 s
HONESTY NOTE: the golden values below were READ from the validated engine after Stages 3-6 were approved. They are
REGRESSION GUARDS (they detect change), not independent truth. The independent evidence is in docs/stage3-4/VALIDATION.md
(JPL Horizons, hand-written geometry) and is re-asserted in `test_recorded_validation_evidence_meets_declared_criteria`.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from lunarnav import MODEL_VERSION
from lunarnav.ephemeris import EphemerisService
from lunarnav.horizon import HorizonService
from lunarnav.provenance import calculation_metadata
from lunarnav.visibility import VisibilityService

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
HAVE = all((DATA / "kernels" / f).exists() for f in
           ("naif0012.tls", "de440s.bsp", "moon_pa_de440_200625.bpc", "moon_de440_250416.tf")) \
    and all((DATA / "dem_cache" / f).exists() for f in ("im2_20m_r10km.tif", "im2_320m_r160km.tif", "im2_20m_r80km.tif"))
needs_data = pytest.mark.skipif(not HAVE, reason=r"kernels/DEM windows missing; see docs/DEV_SETUP.md")
IM2 = (-84.79059, 29.19567)
START = datetime(2027, 1, 15, tzinfo=UTC)


def _t(s: str) -> datetime:
    return datetime.fromisoformat(s)


@pytest.fixture(scope="module")
def svc():
    return VisibilityService(EphemerisService(DATA), HorizonService(DATA))


@pytest.fixture(scope="module")
def golden(svc):
    """IM-2 Athena, 2027-01-15 + 30 d, 15-min steps, observer 2.0 m, +/-100 m, default 0.25 deg horizon."""
    return svc.evaluate(*IM2, START, 900.0, 2881, 2.0, position_uncertainty_m=100.0).to_dict()


# ---------------------------------------------------------------- golden scenario G1: IM-2 horizon

@needs_data
def test_g1_im2_horizon_profile_regression():
    p = HorizonService(DATA).profile(*IM2, 2.0)
    s = p.summary()
    assert [w["window_id"] for w in p.meta["windows"]] == ["im2_20m_r80km", "im2_320m_r160km"]
    assert s["n_azimuths"] == 1440 and s["n_truncated"] == 0 and s["n_data_gap"] == 0 and s["n_complete"] == 1440
    assert s["horizon_min_deg"] == pytest.approx(-1.469332377371741, abs=1e-6)
    assert s["horizon_max_deg"] == pytest.approx(4.065586128285099, abs=1e-6)
    assert s["horizon_mean_deg"] == pytest.approx(1.1681536647187456, abs=1e-6)
    assert p.meta["observer"]["ground_height_m"] == pytest.approx(5321.8886, abs=1e-3)


# ---------------------------------------------------------------- golden scenario G2: IM-2 30-day visibility

@needs_data
def test_g2_im2_sun_visibility_regression(golden):
    sun = golden["bodies"]["sun"]
    m = sun["headline"]["metrics"]
    assert sun["headline_state"] == "any_part_visible"
    assert m["total_visible_s"] == pytest.approx(1260929.0, abs=4.0)
    assert m["visible_fraction"] == pytest.approx(0.48646952, abs=1e-5)
    assert m["n_visible_intervals"] == 3
    assert sun["geometric"]["metrics"]["total_visible_s"] == pytest.approx(1382220.7, abs=4.0)
    assert sun["terrain_effect"]["steps_blocked_by_terrain_only"] == 155
    expected = [("2027-01-28T08:58:55Z", "not_visible"), ("2027-01-28T09:01:24Z", "visible"),
                ("2027-01-28T09:15:33Z", "not_visible"), ("2027-02-12T18:57:35Z", "visible")]
    got = [(t["time_utc"], t["to"]) for t in sun["states"]["any_part"]["transitions"]]
    assert [g[1] for g in got] == [e[1] for e in expected]
    for (g, _), (e, _) in zip(got, expected, strict=True):
        assert abs((_t(g) - _t(e)).total_seconds()) <= 1.0
    bands = [b["band_width_s"] for b in sun["headline"]["position_sensitivity"]["boundary_bands"]]
    for g, e in zip(bands, [39908.0, 0.0, 39908.0, 1854.0], strict=True):
        assert g == pytest.approx(e, abs=60.0)
    fb = sun["headline"]["position_sensitivity"]["metric_bands"]["visible_fraction"]
    assert fb[0] == pytest.approx(0.45442539, abs=1e-5) and fb[1] == pytest.approx(0.48940396, abs=1e-5)


@needs_data
def test_g3_im2_earth_visibility_regression(golden):
    earth = golden["bodies"]["earth"]
    m = earth["headline"]["metrics"]
    assert earth["headline_state"] == "centre_visible"
    assert m["total_visible_s"] == pytest.approx(2093241.8, abs=4.0)
    assert m["visible_fraction"] == pytest.approx(0.80757785, abs=1e-5)
    assert earth["geometric"]["metrics"]["total_visible_s"] == pytest.approx(1904349.0, abs=4.0)
    assert earth["terrain_effect"]["steps_blocked_by_terrain_only"] == 0
    got = [(t["time_utc"], t["to"]) for t in earth["states"]["centre"]["transitions"]]
    assert [g[1] for g in got] == ["not_visible", "visible"]
    for g, e in zip([x[0] for x in got], ["2027-01-27T11:00:46Z", "2027-02-02T05:33:24Z"], strict=True):
        assert abs((_t(g) - _t(e)).total_seconds()) <= 1.0
    bands = [b["band_width_s"] for b in earth["headline"]["position_sensitivity"]["boundary_bands"]]
    for g, e in zip(bands, [2352.0, 20762.0], strict=True):
        assert g == pytest.approx(e, abs=60.0)


# ---------------------------------------------------------------- recorded independent evidence stays within criteria

def test_recorded_validation_evidence_meets_declared_criteria():
    """The independent comparisons recorded at Stages 3 and 4 (JPL Horizons; hand-written geometry) must still show
    results far inside the criteria that were declared BEFORE they were run."""
    s3 = json.loads((ROOT / "docs" / "stage3" / "validation_summary.json").read_text(encoding="utf-8"))
    assert s3["pass"] is True and s3["n_rows"] == 220 and s3["tolerance_deg"] == 0.01
    for body in ("sun", "earth"):
        worst = s3["bodies"][body]["sep_max_deg"]
        assert worst <= s3["tolerance_deg"] / 1e4                       # >= 10^4 margin to the criterion
    s4 = json.loads((ROOT / "docs" / "stage4" / "validation_summary.json").read_text(encoding="utf-8"))
    assert s4["passed"] is True and s4["criterion_deg"] == 1e-3 and len(s4["cases"]) == 3
    for case in s4["cases"]:
        assert case["max_abs_diff_deg"] <= s4["criterion_deg"] / 1e5     # >= 10^5 margin
        assert case["max_abs_limiting_distance_diff_km"] == 0.0


def test_recorded_modelling_sensitivities_are_as_documented():
    """Stage 3 quantified the effect of each modelling choice; the documented orders of magnitude must hold."""
    sens = json.loads((ROOT / "docs" / "stage3" / "sensitivity.json").read_text(encoding="utf-8"))
    sun, earth = sens["sun"], sens["earth"]
    wrong_frame = next(k for k in sun if "MOON_PA" in k)
    assert 0.02 < sun[wrong_frame] < 0.04 and 0.02 < earth[wrong_frame] < 0.04   # ~0.029 deg: 3x the criterion
    parallax = next(k for k in earth if "geocentric" in k)
    assert 0.2 < earth[parallax] < 0.3                                           # ~0.27 deg: must not be neglected


# ---------------------------------------------------------------- reproducibility and calculation metadata

@needs_data
def test_results_and_metadata_are_reproducible(svc, golden):
    again = svc.evaluate(*IM2, START, 900.0, 2881, 2.0, position_uncertainty_m=100.0).to_dict()
    assert json.dumps(again["bodies"], sort_keys=True) == json.dumps(golden["bodies"], sort_keys=True)
    assert again["provenance"] == golden["provenance"]             # deterministic: no timestamps, no host details
    assert "generated" not in json.dumps(golden["provenance"]).lower()


@needs_data
def test_calculation_metadata_traces_to_the_exact_kernels_dem_and_parameters(golden):
    prov = golden["provenance"]
    assert prov["model_version"] == MODEL_VERSION
    kernels = json.loads((DATA / "manifests" / "kernels.json").read_text(encoding="utf-8"))["files"]
    for k in prov["ephemeris"]["kernels"]:
        assert k["sha256"] == kernels[k["file"]]["sha256"]
    dems = json.loads((DATA / "manifests" / "dem_windows.json").read_text(encoding="utf-8"))["windows"]
    used = prov["terrain"]["dem_windows"]
    assert {w["window_id"] for w in used} == {"im2_20m_r80km", "im2_320m_r160km"}
    for w in used:
        assert w["sha256"] == dems[w["window_id"]]["sha256"]
    p = prov["parameters"]
    assert p["start_utc"] == "2027-01-15T00:00:00Z" and p["step_seconds"] == 900.0 and p["n_samples"] == 2881
    assert p["position_uncertainty_m"] == 100.0 and p["n_directions"] == 8 and p["bisection_tolerance_s"] == 1.0
    assert prov["ephemeris"]["frame"] == "MOON_ME" and prov["ephemeris"]["aberration_correction"] == "LT+S"
    assert prov["terrain"]["reference_radius_m"] == 1_737_400.0


def test_calculation_metadata_is_a_pure_function_of_its_inputs():
    eph = {"engine": "e", "kernels": [{"file": "a", "sha256": "1", "role": "x"}], "frame": "F", "aberration_correction": "LT+S"}
    hz = {"algorithm_version": "1", "windows": [{"window_id": "w", "pixel_size_m": 20.0, "sha256": "2", "extra": 1}],
          "parameters": {"reference_radius_m": 1.0, "unseen_terrain_max_height_m": 2.0}}
    a = calculation_metadata(eph, hz, {"k": 1})
    assert a == calculation_metadata(eph, hz, {"k": 1}) and a != calculation_metadata(eph, hz, {"k": 2})
    assert "role" not in a["ephemeris"]["kernels"][0] and "extra" not in a["terrain"]["dem_windows"][0]
