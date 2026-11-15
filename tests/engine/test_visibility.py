"""Stage 5 visibility tests.

Kinds, labelled explicitly:
  * PURE unit tests - synthetic horizons / boolean series with analytic answers (no data needed).
  * SYNTHETIC-TERRAIN end-to-end - the REAL SPICE ephemeris over an in-memory flat DEM with a mesa placed where
    the Sun / Earth actually are. Used only to test that visibility responds to terrain; never exposed as lunar data.
  * REAL-DATA tests - LOLA windows at IM-2 / IM-1 (git-ignored); skipped with the rebuild command if absent.
"""

import json
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest
import rasterio
from lunarnav.dem import DemWindow, DemWindowMeta, lonlat_to_xy, sha256_file
from lunarnav.ephemeris import EphemerisService
from lunarnav.errors import InvalidInputError, OutOfDemCoverageError
from lunarnav.frames import destination_deg
from lunarnav.horizon import HorizonProfile, HorizonService
from lunarnav.visibility import (
    VisibilityService,
    build_intervals,
    disc_states,
    find_transitions,
    horizon_lookup,
    interval_metrics,
)
from rasterio.transform import from_origin

DATA = Path(__file__).resolve().parents[2] / "data"
HAVE_KERNELS = all((DATA / "kernels" / f).exists() for f in
                   ("naif0012.tls", "de440s.bsp", "moon_pa_de440_200625.bpc", "moon_de440_250416.tf"))
needs_kernels = pytest.mark.skipif(not HAVE_KERNELS, reason=r"kernels missing: scripts\fetch_kernels.py")
needs_dem = pytest.mark.skipif(
    not ((DATA / "dem_cache" / "im2_20m_r10km.tif").exists() and (DATA / "dem_cache" / "im2_320m_r160km.tif").exists()
         and (DATA / "dem_cache" / "im2_20m_r80km.tif").exists()),
    reason=r"LOLA windows missing: scripts\extract_dem_window.py")
IM2 = (-84.79059, 29.19567)
IM1 = (-80.12759, 1.44587)
START = datetime(2027, 1, 26, tzinfo=UTC)


# ---------------------------------------------------------------- helpers

def make_profile(values, truncated=None, gap=None) -> HorizonProfile:
    v = np.asarray(values, dtype=float)
    n = v.size
    z = np.zeros(n)
    return HorizonProfile(
        azimuth_deg=np.arange(n) * 360.0 / n, horizon_elevation_deg=v, horizon_distance_km=z.copy(),
        limiting_pixel_size_m=z.copy(), range_covered_km=z.copy(), n_missing_samples=np.zeros(n, dtype=np.int64),
        unseen_bound_deg=z.copy(), truncated=np.zeros(n, dtype=bool) if truncated is None else np.asarray(truncated),
        data_gap=np.zeros(n, dtype=bool) if gap is None else np.asarray(gap), meta={})


def one(profile, az, el, rho=0.27):
    s = disc_states(profile, np.array([az]), np.array([el]), np.array([rho]))
    return {k: bool(v[0]) for k, v in s.items() if k in ("centre", "any_part", "fully", "complete")}


# ---------------------------------------------------------------- horizon lookup

def test_lookup_on_grid_between_samples_wrap_and_missing():
    prof = make_profile(np.arange(360.0) % 7)  # samples every 1 deg
    h, inc = horizon_lookup(prof, np.array([10.0, 10.5, 359.5, 360.0, -0.5]))
    assert h[0] == 10 % 7 and h[1] == max(10 % 7, 11 % 7)  # between samples: max of the two
    assert h[2] == max(359 % 7, 0) and h[3] == 0 and h[4] == max(359 % 7, 0)  # wrap
    assert not inc.any()
    vals = np.zeros(360)
    vals[50] = np.nan
    h, inc = horizon_lookup(make_profile(vals), np.array([50.0, 49.5, 52.0]))
    assert h[0] == -90.0 and inc[0] and inc[1] and not inc[2]  # NaN counts as incomplete, never as terrain
    t = np.zeros(360, dtype=bool)
    t[200] = True
    _, inc = horizon_lookup(make_profile(np.zeros(360), truncated=t), np.array([199.5, 200.0, 201.0]))
    assert inc[0] and inc[1] and not inc[2]


# ---------------------------------------------------------------- disc states (analytic)

def test_flat_horizon_states_match_the_defining_inequalities():
    prof = make_profile(np.full(360, 5.0))
    rho = 0.27
    for el in (10.0, 5.5, 5.2, 5.1, 4.9, 4.75, 4.6, 0.0):
        s = one(prof, 123.0, el, rho)
        assert s["centre"] == (el > 5.0)
        assert s["any_part"] == (el + rho > 5.0)
        assert s["fully"] == (el - rho > 5.0)
        assert s["complete"]
    # ordering: fully => centre => any_part never reversed
    for el in np.linspace(3, 8, 101):
        s = one(prof, 10.0, float(el), rho)
        assert (not s["fully"] or s["centre"]) and (not s["centre"] or s["any_part"])


def test_wall_in_azimuth_blocks_only_inside_its_span_and_partially_at_the_edge():
    h = np.zeros(360)
    h[100:111] = 8.0  # wall 8 deg high from az 100 to 110 (samples at 1 deg)
    prof = make_profile(h)
    assert one(prof, 90.0, 6.0)["fully"]                      # well clear of the wall
    s = one(prof, 105.0, 6.0)
    assert not s["centre"] and not s["any_part"]              # behind the wall
    assert one(prof, 105.0, 8.5)["centre"]                    # above the wall
    edge = one(prof, 98.9, 6.0)                               # centre clear; disc spans 98.6..99.2 into the 99-100 bracket
    assert edge["centre"] and edge["any_part"] and not edge["fully"]
    # between samples 99 (0 deg) and 100 (8 deg) the lookup takes the higher one: obstruction is never under-stated
    assert not one(prof, 99.5, 6.0)["centre"]


def test_disc_across_north_wraps_correctly():
    h = np.zeros(360)
    h[[359, 0, 1]] = 6.0
    prof = make_profile(h)
    assert not one(prof, 0.0, 3.0)["any_part"]
    assert one(prof, 180.0, 3.0)["fully"]


def test_incomplete_horizon_marks_the_step_as_unverified():
    t = np.zeros(360, dtype=bool)
    t[100:103] = True
    prof = make_profile(np.zeros(360), truncated=t)
    assert not one(prof, 101.0, 5.0)["complete"] and one(prof, 101.0, 5.0)["centre"]
    assert one(prof, 200.0, 5.0)["complete"]
    # a disc whose azimuth span reaches the truncated sample is also incomplete
    assert not one(prof, 99.8, 0.9, rho=0.27)["complete"]   # span 99.5..100.1 reaches truncated sample 100
    assert one(prof, 97.0, 0.9, rho=0.27)["complete"]       # span 96.7..97.3 does not


def test_near_zenith_disc_spans_all_azimuths_without_error():
    prof = make_profile(np.full(360, 1.0))
    s = one(prof, 0.0, 89.9, rho=0.5)
    assert s["centre"] and s["fully"]


# ---------------------------------------------------------------- transitions and intervals (analytic)

def test_bisection_localises_a_known_transition_to_one_second():
    true_t = 1234.567
    times = np.arange(0, 4000, 900.0)
    state = times > true_t
    trans = find_transitions(times, state, lambda t: t > true_t)
    assert len(trans) == 1 and trans[0][1] is True and abs(trans[0][0] - true_t) <= 0.5 + 1e-9
    assert find_transitions(times, state, None)[0][0] == 1800.0  # unrefined = sample resolution
    assert find_transitions(times, np.ones(times.size, dtype=bool), lambda t: True) == []


def test_intervals_open_flags_and_metrics():
    # window 0..1000: dark until 100, lit 100..400, dark 400..700, lit 700..1000 (open end)
    trans = [(100.0, True), (400.0, False), (700.0, True)]
    lit, dark = build_intervals(0.0, 1000.0, False, trans)
    assert [(i["start_s"], i["end_s"]) for i in lit] == [(100, 400), (700, 1000)]
    assert [(i["start_s"], i["end_s"]) for i in dark] == [(0, 100), (400, 700)]
    assert dark[0]["open_start"] and lit[1]["open_end"] and not lit[0]["open_start"] and not lit[0]["open_end"]
    m = interval_metrics(lit, dark, 1000.0)
    assert m["total_visible_s"] == 600 and m["visible_fraction"] == 0.6 and m["n_visible_intervals"] == 2
    assert m["longest_visible_s_closed_only"] == 300 and m["longest_visible_s_including_open"] == 300
    assert m["longest_visible_includes_open_interval"] is True       # the open 300 s interval ties the closed one: unsettled
    assert m["longest_not_visible_s_closed_only"] == 300 and m["longest_not_visible_s_including_open"] == 300
    # an open interval that is the longest must not be reported as a closed-only extremum
    lit2, dark2 = build_intervals(0.0, 1000.0, True, [(200.0, False)])
    m2 = interval_metrics(lit2, dark2, 1000.0)
    assert m2["longest_visible_s_closed_only"] is None and m2["longest_not_visible_s_closed_only"] is None
    assert m2["longest_not_visible_s_including_open"] == 800 and m2["longest_not_visible_includes_open_interval"]
    # no transitions
    lit3, dark3 = build_intervals(0.0, 500.0, True, [])
    assert interval_metrics(lit3, dark3, 500.0)["total_visible_s"] == 500 and dark3 == []


def test_displacement_helper_matches_spherical_geometry():
    for az in (0.0, 90.0, 180.0, 270.0):
        la, lo = destination_deg(-85.0, 30.0, az, 100.0)
        # 100 m on a 1737.4 km sphere = 5.756e-5 rad
        d = math.acos(min(1, math.sin(math.radians(-85)) * math.sin(math.radians(la))
                          + math.cos(math.radians(-85)) * math.cos(math.radians(la)) * math.cos(math.radians(lo - 30))))
        assert d * 1_737_400.0 == pytest.approx(100.0, rel=1e-6)
    la, _ = destination_deg(-85.0, 30.0, 0.0, 100.0)
    assert la > -85.0  # north moves toward the equator from the south pole side


# ---------------------------------------------------------------- input validation

def test_bad_inputs_rejected_before_any_computation(tmp_path):
    svc = VisibilityService(EphemerisService(DATA), HorizonService(tmp_path))
    for kw, field in [({"bodies": ("moon",)}, "bodies"), ({"bodies": ()}, "bodies"),
                      ({"bodies": ("sun", "sun")}, "bodies"),
                      ({"position_uncertainty_m": -1.0}, "position_uncertainty_m"),
                      ({"position_uncertainty_m": float("nan")}, "position_uncertainty_m"),
                      ({"position_uncertainty_m": 1e6}, "position_uncertainty_m"),
                      ({"n_directions": 2}, "n_directions")]:
        with pytest.raises(InvalidInputError) as e:
            svc.evaluate(*IM2, START, 900.0, 10, 2.0, **kw)
        assert e.value.field == field
    with pytest.raises(InvalidInputError):
        svc.evaluate(*IM2, START, 900.0, 0, 2.0)


# ---------------------------------------------------------------- synthetic terrain + real ephemeris

LAT0, LON0 = -85.0, 30.0


def _synth(half_m, px, fn):
    x0, y0 = lonlat_to_xy(LAT0, LON0)
    n = round(2 * half_m / px)
    left, top = x0 - half_m, y0 + half_m
    xs = left + (np.arange(n) + 0.5) * px
    ys = top - (np.arange(n) + 0.5) * px
    xx, yy = np.meshgrid(xs, ys)
    z = np.asarray(fn(xx, yy), dtype=np.float32) * np.ones((n, n), dtype=np.float32)
    meta = DemWindowMeta.from_dict("synth", {
        "product_id": "SYNTHETIC_TEST_ONLY", "file": "dem_cache/synth.tif", "sha256": "0" * 64, "pixel_size_m": px,
        "left_m": left, "top_m": top, "width": n, "height": n, "valid_fraction": 1.0, "z_min_m": float(z.min()),
        "z_max_m": float(z.max()), "source_url": "https://example.invalid/synthetic", "overview_level": None})
    return DemWindow(meta, z)


def _registry(root: Path, w: DemWindow) -> None:
    (root / "dem_cache").mkdir(parents=True, exist_ok=True)
    f = root / "dem_cache" / "synth.tif"
    m = w.meta
    with rasterio.open(f, "w", driver="GTiff", dtype="float32", count=1, width=m.width, height=m.height,
                       transform=from_origin(m.left_m, m.top_m, m.pixel_size_m, m.pixel_size_m),
                       nodata=float("nan")) as dst:
        dst.write(w.data, 1)
    d = dict(m.raw)
    d["sha256"] = sha256_file(f)
    (root / "manifests").mkdir(parents=True, exist_ok=True)
    (root / "manifests" / "dem_windows.json").write_text(json.dumps({"windows": {"synth": d}}))


def _mesa_fn(az_deg, dist_m, radius_m, height_m):
    la, lo = destination_deg(LAT0, LON0, az_deg, dist_m)
    cx, cy = lonlat_to_xy(la, lo)
    k = 1.0 / math.cos(math.radians((la + 90) / 2)) ** 2
    return lambda x, y: np.where(np.hypot(x - cx, y - cy) <= radius_m * k, height_m, 0.0)


def _angdiff(a, b):
    return np.abs((np.asarray(a) - b + 180.0) % 360.0 - 180.0)


@needs_kernels
def test_sun_and_earth_visibility_respond_to_a_terrain_obstruction(tmp_path):
    eph = EphemerisService(DATA)
    flat_root, mesa_root = tmp_path / "flat", tmp_path / "mesa"
    n, step = 1441, 1800.0  # 30 days
    probe = eph.series(LAT0, LON0, START, step, n, ("sun", "earth"), 2.0)
    sun_az0 = float(np.degrees(np.angle(np.mean(np.exp(1j * np.radians(probe.bodies["earth"].azimuth_deg))))) % 360)
    _registry(flat_root, _synth(20_000, 20.0, lambda x, y: 0.0))
    _registry(mesa_root, _synth(20_000, 20.0, _mesa_fn(sun_az0, 6_000.0, 3_000.0, 1500.0)))
    kw = {"position_uncertainty_m": None, "refine": False, "include_series": True, "horizon_kwargs": {"az_step_deg": 1.0}}
    flat = VisibilityService(eph, HorizonService(flat_root)).evaluate(LAT0, LON0, START, step, n, 2.0, **kw).to_dict()
    mesa = VisibilityService(eph, HorizonService(mesa_root)).evaluate(LAT0, LON0, START, step, n, 2.0, **kw).to_dict()

    for body in ("earth", "sun"):
        f, m = flat["bodies"][body]["series"], mesa["bodies"][body]["series"]
        az = np.array(m["azimuth_deg"])
        blocked_zone = _angdiff(az, sun_az0) < 15.0     # inside the mesa shadow (>= 10 deg high there; Sun/Earth < 8 deg)
        free_zone = _angdiff(az, sun_az0) > 50.0        # beyond the mesa's azimuth span (+ margin)
        head_f, head_m = np.array(f["headline_visible"]), np.array(m["headline_visible"])
        geo = np.array(m["geometric_headline_above_local_horizontal"])
        # flat terrain: terrain-corrected == geometric against the clear-sky dip (-0.087 deg for 2 m)
        el = np.array(f["elevation_deg"])
        rho = np.array(f["angular_radius_deg"])
        dip = 0.0869
        expect = (el + rho > -dip) if body == "sun" else (el > -dip)
        assert np.array_equal(head_f, expect)
        if blocked_zone.any():
            assert not head_m[blocked_zone].any(), body                 # obstruction blocks it
        assert np.array_equal(head_m[free_zone], head_f[free_zone])     # elsewhere identical to flat terrain
        # distinct from geometric where the obstruction acts
        if body == "earth":
            assert (geo & ~head_m).sum() > 0 and blocked_zone.sum() > 100
        assert mesa["bodies"][body]["terrain_effect"]["steps_blocked_by_terrain_only"] >= \
            flat["bodies"][body]["terrain_effect"]["steps_blocked_by_terrain_only"]
    # the Earth is shadowed essentially all the time (mesa sits on its mean azimuth)
    assert mesa["bodies"]["earth"]["terrain_effect"]["headline_visible_steps"] < \
        0.2 * flat["bodies"]["earth"]["terrain_effect"]["headline_visible_steps"]
    # flat-terrain run has no completeness problem; sensitivity honestly not requested
    assert flat["position_sensitivity"]["status"] == "not_computed"


# ---------------------------------------------------------------- real LOLA data (IM-2)

@pytest.fixture(scope="module")
def vis():
    return VisibilityService(EphemerisService(DATA), HorizonService(DATA))


@pytest.fixture(scope="module")
def im2(vis):
    """19 days 2027-01-26..02-14 (Earth set/rise, Sun set, a short Sun blip, delayed Sun rise), 1 h steps."""
    return vis.evaluate(*IM2, START, 3600.0, 457, 2.0, position_uncertainty_m=100.0,
                        horizon_kwargs={"az_step_deg": 1.0}).to_dict()


@needs_kernels
@needs_dem
def test_real_im2_terrain_corrected_differs_from_geometric_and_is_labelled(im2):
    for b in ("sun", "earth"):
        te = im2["bodies"][b]["terrain_effect"]
        assert te["n_steps"] == 457
        assert im2["bodies"][b]["completeness"]["visibility_is_upper_bound"] is False  # IM-2 horizon is complete
    sun = im2["bodies"]["sun"]
    assert sun["headline_state"] == "any_part_visible" and im2["bodies"]["earth"]["headline_state"] == "centre_visible"
    assert sun["terrain_effect"]["steps_blocked_by_terrain_only"] > 0   # terrain removes sunlight the geometry allows
    s = sun["series"]
    assert len(s["centre_visible"]) == 457
    # ordering fully <= centre <= any_part at every step
    for k in range(457):
        assert (not s["fully_visible"][k] or s["centre_visible"][k]) and (not s["centre_visible"][k] or s["any_part_visible"][k])
    assert "not link availability" in im2["definitions"]["headline"]["earth"]
    assert im2["observer"]["observer_height_above_surface_m"] == 2.0


@needs_kernels
@needs_dem
def test_real_im2_refined_transitions_agree_with_a_brute_force_scan(vis, im2):
    eph, hz = vis.eph, vis.hz
    prof = hz.profile(*IM2, 2.0, az_step_deg=1.0)
    h_radius = prof.meta["observer"]["observer_radius_height_m"]
    checked = 0
    for body in ("sun", "earth"):
        head = "any_part" if body == "sun" else "centre"
        for tr in im2["bodies"][body]["states"][head]["transitions"]:
            t0 = tr["time_s"]
            lo = max(0.0, t0 - 1800.0)
            res = eph.series(*IM2, START + timedelta(seconds=lo), 2.0, 1801, (body,), h_radius)  # 2 s brute-force scan
            b = res.bodies[body]
            st = disc_states(prof, np.array(b.azimuth_deg), np.array(b.elevation_deg),
                             np.array(b.angular_diameter_deg) / 2)[head]
            changes = np.flatnonzero(st[1:] != st[:-1])
            assert changes.size >= 1
            brute = lo + 2.0 * (changes[np.argmin(np.abs(lo + 2.0 * changes - t0))] + 0.5)
            assert abs(brute - t0) <= 4.0, (body, tr["time_utc"], brute - t0)
            checked += 1
    assert checked >= 2


@needs_kernels
@needs_dem
def test_real_im2_intervals_are_consistent_with_the_step_series(im2):
    for b in ("sun", "earth"):
        d = im2["bodies"][b]
        head = d["headline"]
        s = d["series"]["headline_visible"]
        total = sum(i["duration_s"] for i in head["intervals"]) + sum(i["duration_s"] for i in head["not_visible_intervals"])
        assert total == pytest.approx(3600.0 * 456)           # intervals tile the window exactly
        assert head["metrics"]["total_visible_s"] == pytest.approx(sum(i["duration_s"] for i in head["intervals"]))
        assert abs(head["metrics"]["total_visible_s"] - 3600.0 * sum(s)) <= 3600.0 * (2 * len(head["intervals"]) + 1)
        for a, c in zip(head["intervals"], head["intervals"][1:], strict=False):
            assert a["end_s"] < c["start_s"]
        first = (head["intervals"] + head["not_visible_intervals"])
        assert sum(1 for i in first if i["open_start"]) == 1 and sum(1 for i in first if i["open_end"]) == 1
        starts_open_visible = any(i["open_start"] for i in head["intervals"])
        assert starts_open_visible == bool(s[0])


@needs_kernels
@needs_dem
def test_real_im2_position_sensitivity_is_attached_to_every_result(im2):
    ps = im2["position_sensitivity"]
    assert ps["status"] == "computed" and ps["data_class"] == "calculated"
    assert ps["assumed_position_uncertainty_m"] == 100.0 and "+/-100 m" in ps["assumption"]
    assert "not an error bar" in ps["kind"] and ps["n_directions"] == 8
    for b in ("sun", "earth"):
        d = im2["bodies"][b]
        s = d["series"]
        assert len(s["position_sensitivity_deg"]) == 457 and len(s["headline_state_robust_to_position"]) == 457
        assert max(s["position_sensitivity_deg"]) > 0.0
        head = d["headline"]
        assert head["position_sensitivity"]["status"] == "computed"
        assert set(head["position_sensitivity"]["metric_bands"]) >= {"total_visible_s", "visible_fraction"}
        nominal = head["metrics"]["total_visible_s"]
        lo, hi = head["position_sensitivity"]["metric_bands"]["total_visible_s"]
        assert lo <= nominal <= hi
        # every closed interval boundary carries its band, and the nominal time lies inside it
        for iv in head["intervals"] + head["not_visible_intervals"]:
            for side, flag in (("start", "open_start"), ("end", "open_end")):
                band = iv[f"{side}_band"]
                if iv[flag]:
                    assert band is None
                else:
                    assert band is not None and band["earliest_utc"] <= iv[f"{side}_utc"] <= band["latest_utc"]
                    assert band["width_s"] >= 0 and isinstance(band["complete"], bool)
        # non-headline states carry no band (the requirement is about the headline result)
        other = next(k for k in d["states"] if k != d["headline_state"].replace("_visible", ""))
        assert "position_sensitivity" not in d["states"][other]


@needs_kernels
@needs_dem
def test_position_band_is_configurable_and_scales_sensibly(vis, im2):
    kw = {"horizon_kwargs": {"az_step_deg": 1.0}}
    off = vis.evaluate(*IM2, START, 3600.0, 457, 2.0, position_uncertainty_m=0.0, **kw).to_dict()
    assert off["position_sensitivity"]["status"] == "not_computed"
    assert off["bodies"]["sun"]["headline"]["position_sensitivity"]["status"] == "not_computed"
    assert off["bodies"]["sun"]["series"]["position_sensitivity_deg"] is None
    small = vis.evaluate(*IM2, START, 3600.0, 457, 2.0, position_uncertainty_m=20.0, **kw).to_dict()
    assert small["position_sensitivity"]["assumed_position_uncertainty_m"] == 20.0
    for b in ("sun", "earth"):
        w20 = max(small["bodies"][b]["series"]["position_sensitivity_deg"])
        w100 = max(im2["bodies"][b]["series"]["position_sensitivity_deg"])
        assert w20 < w100                                    # a smaller position uncertainty moves things less
        assert small["bodies"][b]["headline"]["metrics"] == im2["bodies"][b]["headline"]["metrics"]  # nominal unchanged


@needs_kernels
@needs_dem
def test_results_are_reproducible(vis, im2):
    again = vis.evaluate(*IM2, START, 3600.0, 457, 2.0, position_uncertainty_m=100.0,
                         horizon_kwargs={"az_step_deg": 1.0}).to_dict()
    assert json.dumps(again["bodies"], sort_keys=True) == json.dumps(im2["bodies"], sort_keys=True)


@needs_kernels
@needs_dem
def test_im1_has_insufficient_terrain_so_sensitivity_is_not_extrapolated_and_results_are_flagged(vis):
    r = vis.evaluate(*IM1, START, 3600.0, 49, 2.0, position_uncertainty_m=100.0,
                     horizon_kwargs={"az_step_deg": 5.0}).to_dict()
    ps = r["position_sensitivity"]
    assert ps["status"] == "not_computed" and "insufficient" in ps["reason"]
    for b in ("sun", "earth"):
        d = r["bodies"][b]
        assert d["headline"]["position_sensitivity"]["status"] == "not_computed"
        assert d["series"]["position_sensitivity_deg"] is None
        assert d["completeness"]["steps_with_incomplete_horizon"] > 0
        if d["terrain_effect"]["headline_visible_steps"]:
            assert d["completeness"]["visibility_is_upper_bound"] is True    # 'visible' there is unverified


@needs_kernels
@needs_dem
def test_no_dem_site_is_an_error_not_geometric_visibility(vis):
    with pytest.raises(OutOfDemCoverageError):
        vis.evaluate(-72.0, 200.0, START, 3600.0, 5, 2.0)


@needs_kernels
@needs_dem
def test_step_size_changes_totals_only_within_the_event_resolution(vis):
    kw = {"position_uncertainty_m": None, "include_series": False, "horizon_kwargs": {"az_step_deg": 1.0}}
    coarse = vis.evaluate(*IM2, START, 3600.0, 457, 2.0, **kw).to_dict()
    fine = vis.evaluate(*IM2, START, 600.0, 2737, 2.0, **kw).to_dict()
    for b in ("sun", "earth"):
        a = coarse["bodies"][b]["headline"]["metrics"]["total_visible_s"]
        c = fine["bodies"][b]["headline"]["metrics"]["total_visible_s"]
        n_events = len(coarse["bodies"][b]["states"][coarse["bodies"][b]["headline_state"].replace("_visible", "")]["transitions"])
        assert abs(a - c) <= 3600.0 * (n_events + 2)
        # refined boundaries differ from the 10-min run's by at most its step
        t1 = [t["time_s"] for t in coarse["bodies"][b]["states"][coarse["bodies"][b]["headline_state"].replace("_visible", "")]["transitions"]]
        t2 = [t["time_s"] for t in fine["bodies"][b]["states"][fine["bodies"][b]["headline_state"].replace("_visible", "")]["transitions"]]
        for t in t1:
            assert min(abs(t - u) for u in t2) <= 605.0 if t2 else True
