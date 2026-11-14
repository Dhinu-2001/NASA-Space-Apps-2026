"""Stage 8 tests: idealised direct-beam solar energy (analytic cases, input validation, reuse rule, real IM-2 cross-check).

PURE tests use a hand-built scenario dictionary with an analytic answer. The REAL-DATA test cross-checks against the
Stage 6 scenario service (skipped, with the rebuild command, if kernels/DEM windows are absent).
"""

import inspect
import json
from pathlib import Path

import pytest
from lunarnav import engineering
from lunarnav.engineering import SOLAR_CONSTANT_W_M2, solar_energy, validate_panel
from lunarnav.ephemeris import EphemerisService
from lunarnav.errors import InvalidInputError
from lunarnav.horizon import HorizonService
from lunarnav.scenarios import ScenarioService
from lunarnav.visibility import VisibilityService

DATA = Path(__file__).resolve().parents[2] / "data"
HAVE = all((DATA / "kernels" / f).exists() for f in
           ("naif0012.tls", "de440s.bsp", "moon_pa_de440_200625.bpc", "moon_de440_250416.tf")) \
    and all((DATA / "dem_cache" / f).exists() for f in ("im2_20m_r10km.tif", "im2_320m_r160km.tif", "im2_20m_r80km.tif"))
needs_data = pytest.mark.skipif(not HAVE, reason=r"kernels/DEM windows missing; see docs/DEV_SETUP.md")


def scenario(total=36000.0, band=(30000.0, 40000.0), geo=45000.0, window_s=86400.0, dark=(7200.0, (3600.0, 9000.0), True),
             fractions=None):
    n = int(window_s / 3600.0) + 1
    return {
        "id": "x" * 64, "status": "supported", "spec": {"site_id": "t", "start_utc": "2027-01-15T00:00:00Z"},
        "window": {"n_samples": n, "step_seconds": 3600.0},
        "position_sensitivity": {"status": "computed", "assumed_position_uncertainty_m": 100.0},
        "provenance": {"model_version": "test"},
        "bodies": {"sun": {
            "headline_state": "any_part_visible",
            "terrain_corrected": {
                "total_visible_s": {"nominal": total, "band": list(band)},
                "longest_not_visible_s": {"including_open": dark[0], "band_including_open": list(dark[1]), "includes_open_interval": dark[2]},
                "state_fractions": fractions,
            },
            "geometric": {"total_visible_s": {"nominal": geo}},
        }},
    }


# ---------------------------------------------------------------- analytic

def test_one_square_metre_perfect_panel_for_one_hour_is_exactly_the_irradiance():
    r = solar_energy(scenario(total=3600.0, band=(3600.0, 3600.0)), 1.0, 1.0, 1361.0)
    assert r["terrain_corrected"]["energy_wh"]["nominal"] == pytest.approx(1361.0)
    assert r["panel"]["peak_electrical_power_w"] == pytest.approx(1361.0)
    assert r["terrain_corrected"]["sunlit_hours"]["nominal"] == pytest.approx(1.0)


def test_energy_is_efficiency_times_area_times_irradiance_times_time():
    r = solar_energy(scenario(total=36000.0), 2.5, 0.30, 1361.0)       # 10 h
    assert r["panel"]["peak_electrical_power_w"] == pytest.approx(0.30 * 2.5 * 1361.0)
    assert r["terrain_corrected"]["energy_wh"]["nominal"] == pytest.approx(0.30 * 2.5 * 1361.0 * 10.0)
    assert r["window_hours"] == pytest.approx(24.0)
    # mean power over the window = peak x illuminated fraction
    assert r["terrain_corrected"]["mean_power_w"]["nominal"] == pytest.approx(0.30 * 2.5 * 1361.0 * 10.0 / 24.0)


def test_position_band_is_the_visible_time_band_scaled_by_the_same_factor_and_contains_the_nominal():
    r = solar_energy(scenario(total=36000.0, band=(30000.0, 40000.0)), 1.0, 0.2, 1000.0)
    k = 0.2 * 1000.0 / 3600.0
    e = r["terrain_corrected"]["energy_wh"]
    assert e["band"] == [pytest.approx(30000.0 * k), pytest.approx(40000.0 * k)]
    assert e["band"][0] <= e["nominal"] <= e["band"][1]
    h = r["terrain_corrected"]["sunlit_hours"]["band"]
    assert h == [pytest.approx(30000.0 / 3600.0), pytest.approx(40000.0 / 3600.0)]
    assert r["position_sensitivity"]["assumed_position_uncertainty_m"] == 100.0     # carried through, not re-derived


def test_energy_scales_linearly_with_area_efficiency_and_irradiance():
    base = solar_energy(scenario(), 1.0, 0.1, 1200.0)["terrain_corrected"]["energy_wh"]["nominal"]
    assert solar_energy(scenario(), 3.0, 0.1, 1200.0)["terrain_corrected"]["energy_wh"]["nominal"] == pytest.approx(3 * base)
    assert solar_energy(scenario(), 1.0, 0.3, 1200.0)["terrain_corrected"]["energy_wh"]["nominal"] == pytest.approx(3 * base)
    assert solar_energy(scenario(), 1.0, 0.1, 1500.0)["terrain_corrected"]["energy_wh"]["nominal"] == pytest.approx(1.25 * base)


def test_geometric_counterpart_terrain_effect_and_longest_dark_with_its_open_flag():
    r = solar_energy(scenario(total=36000.0, geo=45000.0), 3.6, 1.0, 1000.0)       # 3600 W peak: 1 Wh per second
    assert r["geometric"]["energy_wh"] == pytest.approx(45000.0) and r["geometric"]["sunlit_hours"] == pytest.approx(12.5)
    assert r["terrain_effect"]["energy_wh_terrain_minus_geometric"] == pytest.approx(36000.0 - 45000.0)   # terrain removes light
    d = r["terrain_corrected"]["longest_without_direct_sunlight"]
    assert d["hours"] == pytest.approx(2.0) and d["includes_open_interval"] is True and d["band_hours"] == [1.0, 2.5]
    closed = solar_energy(scenario(dark=(7200.0, (7200.0, 7200.0), False)), 1.0, 1.0)
    assert closed["terrain_corrected"]["longest_without_direct_sunlight"]["includes_open_interval"] is False


def test_partial_disc_bracket_is_ordered_and_absent_when_the_fractions_are_not_available():
    r = solar_energy(scenario(fractions={"centre": 0.45, "any_part": 0.5, "fully": 0.4}), 3.6, 1.0, 1000.0)
    b = r["partial_disc_bracket"]
    assert b["whole_disc_energy_wh"] == pytest.approx(0.4 * 86400.0) and b["any_part_energy_wh"] == pytest.approx(0.5 * 86400.0)
    assert b["whole_disc_energy_wh"] <= b["any_part_energy_wh"] and "no position band" in b["note"]
    assert solar_energy(scenario(fractions=None), 1.0, 1.0)["partial_disc_bracket"] is None


def test_a_site_that_never_sees_the_sun_gives_zero_energy_with_a_zero_band_not_a_missing_number():
    r = solar_energy(scenario(total=0.0, band=(0.0, 0.0), geo=40000.0, dark=(86400.0, (86400.0, 86400.0), True)), 1.0, 0.3)
    e = r["terrain_corrected"]["energy_wh"]
    assert e["nominal"] == 0.0 and e["band"] == [0.0, 0.0] and r["terrain_effect"]["energy_wh_terrain_minus_geometric"] < 0


# ---------------------------------------------------------------- labelling and honesty

def test_result_is_labelled_as_an_idealised_upper_bound_with_assumptions_and_default_flag():
    r = solar_energy(scenario(), 1.0, 0.3)
    assert r["data_class"] == "calculated" and "UPPER BOUND" in r["kind"] and "not battery state" in r["kind"]
    assert r["panel"]["irradiance_w_m2"] == SOLAR_CONSTANT_W_M2 and r["panel"]["irradiance_is_default_assumption"] is True
    assert solar_energy(scenario(), 1.0, 0.3, 1300.0)["panel"]["irradiance_is_default_assumption"] is False
    text = " ".join(r["assumptions"] + r["limitations"]).lower()
    for must in ("sun-tracking", "any part of the sun's disc", "distance variation", "not a power budget", "proven bound"):
        assert must in text, must
    assert r["provenance"] == {"model_version": "test"} and r["panel"]["formula"].startswith("E[Wh]")


@pytest.mark.parametrize(("area", "eff", "irr", "field"), [
    (0, 0.3, None, "area_m2"), (-1.0, 0.3, None, "area_m2"), (1e9, 0.3, None, "area_m2"), (float("nan"), 0.3, None, "area_m2"),
    (float("inf"), 0.3, None, "area_m2"), ("1", 0.3, None, "area_m2"), (True, 0.3, None, "area_m2"), (None, 0.3, None, "area_m2"),
    (1.0, 0, None, "efficiency"), (1.0, -0.1, None, "efficiency"), (1.0, 1.01, None, "efficiency"), (1.0, "0.3", None, "efficiency"),
    (1.0, float("nan"), None, "efficiency"), (1.0, True, None, "efficiency"),
    (1.0, 0.3, 999.0, "irradiance_w_m2"), (1.0, 0.3, 1501.0, "irradiance_w_m2"), (1.0, 0.3, "x", "irradiance_w_m2"),
    (1.0, 0.3, float("nan"), "irradiance_w_m2"),
])
def test_invalid_panel_inputs_are_typed_errors_naming_the_field(area, eff, irr, field):
    with pytest.raises(InvalidInputError) as e:
        validate_panel(area, eff, irr)
    assert e.value.field == field
    with pytest.raises(InvalidInputError):
        solar_energy(scenario(), area, eff, irr)


def test_boundary_values_are_accepted():
    assert validate_panel(1e-9, 1.0, 1000.0)[:3] == (1e-9, 1.0, 1000.0)
    assert validate_panel(10_000.0, 1e-9, 1500.0)[2] == 1500.0


def test_an_insufficient_scenario_has_no_figures_and_is_refused_rather_than_estimated():
    with pytest.raises(InvalidInputError) as e:
        solar_energy({"status": "terrain_data_insufficient", "id": "x"}, 1.0, 0.3)
    assert e.value.field == "scenario"


def test_reuse_rule_the_engineering_module_imports_no_astronomy_terrain_or_visibility_code():
    """Owner instruction: reuse Stage 5/6 outputs; do not recompute or duplicate ephemeris/horizon/visibility logic."""
    src = inspect.getsource(engineering)
    for forbidden in ("from .ephemeris", "from .horizon", "from .visibility", "from .frames", "from .dem", "import spiceypy",
                      "import rasterio", "elevation_angle", "enu_basis", "spkcpo"):
        assert forbidden not in src, forbidden


# ---------------------------------------------------------------- real data cross-check

@needs_data
def test_real_im2_energy_equals_the_panel_factor_times_the_scenario_visible_time_with_its_band():
    sv = ScenarioService(DATA, VisibilityService(EphemerisService(DATA), HorizonService(DATA)))
    scn = sv.evaluate(sv.make_spec({"site_id": "im2-athena"}, "2027-01-26T00:00:00Z", duration_days=10.0, step_seconds=3600.0,
                                   az_step_deg=1.0))
    r = solar_energy(scn, 1.0, 0.30)
    tc = scn["bodies"]["sun"]["terrain_corrected"]
    factor = 0.30 * 1.0 * SOLAR_CONSTANT_W_M2 / 3600.0
    assert r["terrain_corrected"]["energy_wh"]["nominal"] == pytest.approx(tc["total_visible_s"]["nominal"] * factor)
    lo, hi = tc["total_visible_s"]["band"]
    assert r["terrain_corrected"]["energy_wh"]["band"] == [pytest.approx(lo * factor), pytest.approx(hi * factor)]
    assert r["geometric"]["energy_wh"] == pytest.approx(scn["bodies"]["sun"]["geometric"]["total_visible_s"]["nominal"] * factor)
    fr = tc["state_fractions"]
    assert fr["fully"] <= fr["centre"] <= fr["any_part"] and fr["any_part"] == pytest.approx(tc["visible_fraction"]["nominal"])
    b = r["partial_disc_bracket"]
    assert b["whole_disc_energy_wh"] <= b["any_part_energy_wh"]
    assert b["any_part_energy_wh"] == pytest.approx(r["terrain_corrected"]["energy_wh"]["nominal"])   # upper bracket = headline
    json.dumps(r)                                                              # fully serialisable
    assert r["provenance"]["model_version"] and r["provenance"]["ephemeris"]["kernels"]
