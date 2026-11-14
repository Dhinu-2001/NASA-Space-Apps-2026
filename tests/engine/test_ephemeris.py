"""Stage 3 ephemeris tests.

Layers:
  * time-parsing / input-validation tests (no kernels needed);
  * REFERENCE tests against the recorded JPL Horizons grid (the independent oracle);
  * physical-sanity tests that do not depend on Horizons (geometry identities, periodicity, bounds);
  * failure-mode tests (missing/tampered kernels, out-of-range times).
Tests needing the git-ignored kernels skip with the rebuild command when they are absent.
"""

from __future__ import annotations

import itertools
import json
import math
import shutil
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from lunarnav.ephemeris import (
    BODIES,
    MAX_SAMPLES,
    EphemerisService,
    check_validated_range,
    format_utc,
    parse_utc,
)
from lunarnav.errors import DataMissingError, EphemerisOutOfRangeError, InvalidInputError
from lunarnav.frames import EARTH_EQUATORIAL_RADIUS_KM, REFERENCE_RADIUS_KM, angular_diameter_deg

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
REF = DATA / "validation" / "horizons_stage3_reference.json"
sys.path.insert(0, str(ROOT / "scripts"))

HAVE_KERNELS = all(
    (DATA / "kernels" / f).exists()
    for f in ("naif0012.tls", "de440s.bsp", "moon_pa_de440_200625.bpc", "moon_de440_250416.tf"))
needs_kernels = pytest.mark.skipif(
    not HAVE_KERNELS, reason=r"kernels missing: run .\.venv\Scripts\python.exe scripts\fetch_kernels.py")

C_KM_S = 299_792.458
AU_KM = 149_597_870.7


@pytest.fixture(scope="module")
def svc() -> EphemerisService:
    return EphemerisService(DATA)


# ------------------------------------------------------------------ time parsing (no kernels)
def test_parse_utc_accepts_z_and_plus_zero_offset():
    a = parse_utc("2027-01-15T00:00:00Z")
    assert a == datetime(2027, 1, 15, tzinfo=UTC)
    assert parse_utc("2027-01-15T00:00:00+00:00") == a
    assert parse_utc("2027-01-15T00:00:00.250Z").microsecond == 250_000


@pytest.mark.parametrize("bad", [
    "2027-01-15T00:00:00", "2027-01-15", "2027-01-15T05:30:00+05:30", "2027-01-15T00:00:00-05:00",
    "not-a-time", "", "2027-13-01T00:00:00Z", "2027-01-15T24:00:01Z", 1234567890, None,
])
def test_parse_utc_rejects_local_naive_and_malformed(bad):
    with pytest.raises(InvalidInputError):
        parse_utc(bad)


def test_format_utc_roundtrip_and_fractions():
    assert format_utc(datetime(2027, 1, 15, 1, 2, 3, tzinfo=UTC)) == "2027-01-15T01:02:03Z"
    assert format_utc(datetime(2027, 1, 15, 1, 2, 3, 500_000, tzinfo=UTC)) == \
        "2027-01-15T01:02:03.5Z"


def test_validated_range_boundaries():
    check_validated_range(datetime(2025, 1, 1, tzinfo=UTC))
    check_validated_range(datetime(2035, 12, 31, 23, 59, 59, tzinfo=UTC))
    for bad in (datetime(2024, 12, 31, 23, 59, 59, tzinfo=UTC), datetime(2036, 1, 1, tzinfo=UTC),
                datetime(1999, 1, 1, tzinfo=UTC)):
        with pytest.raises(EphemerisOutOfRangeError):
            check_validated_range(bad)


# ------------------------------------------------------------------ input validation (no kernels)
def test_invalid_inputs_rejected_before_any_kernel_use(tmp_path):
    empty = EphemerisService(tmp_path)  # no kernels: validation must fire first
    t = datetime(2027, 1, 15, tzinfo=UTC)
    with pytest.raises(InvalidInputError):
        empty.series(-91.0, 0.0, t, 60, 1)
    with pytest.raises(InvalidInputError):
        empty.series(float("nan"), 0.0, t, 60, 1)
    with pytest.raises(InvalidInputError):
        empty.series(0.0, 0.0, t, 60, 1, bodies=("moon",))
    with pytest.raises(InvalidInputError):
        empty.series(0.0, 0.0, t, 60, 1, bodies=())
    with pytest.raises(InvalidInputError):
        empty.series(0.0, 0.0, t, 0.5, 1)
    with pytest.raises(InvalidInputError):
        empty.series(0.0, 0.0, t, 60, 0)
    with pytest.raises(InvalidInputError):
        empty.series(0.0, 0.0, t, 60, MAX_SAMPLES + 1)
    with pytest.raises(InvalidInputError):
        empty.series(0.0, 0.0, t, 60, 1, height_m="5")
    with pytest.raises(InvalidInputError):
        empty.series(0.0, 0.0, t, 60, 1, height_m=1e6)
    with pytest.raises(EphemerisOutOfRangeError):
        empty.series(0.0, 0.0, datetime(2040, 1, 1, tzinfo=UTC), 60, 1)
    with pytest.raises(EphemerisOutOfRangeError):  # last sample leaves the validated range
        empty.series(0.0, 0.0, datetime(2035, 12, 31, 23, tzinfo=UTC), 3600, 3)


# ------------------------------------------------------------------ kernel failure modes
def test_missing_kernels_raise_data_missing_with_rebuild_command(tmp_path):
    (tmp_path / "manifests").mkdir()
    shutil.copy(DATA / "manifests" / "kernels.json", tmp_path / "manifests" / "kernels.json")
    with pytest.raises(DataMissingError) as exc:
        EphemerisService(tmp_path).series(0.0, 0.0, datetime(2027, 1, 15, tzinfo=UTC), 60, 1)
    assert "fetch_kernels.py" in exc.value.details["rebuild"]


def test_missing_manifest_raises_data_missing(tmp_path):
    with pytest.raises(DataMissingError):
        EphemerisService(tmp_path).series(0.0, 0.0, datetime(2027, 1, 15, tzinfo=UTC), 60, 1)


@needs_kernels
def test_tampered_kernel_is_refused_not_used(tmp_path):
    (tmp_path / "manifests").mkdir()
    (tmp_path / "kernels").mkdir()
    shutil.copy(DATA / "manifests" / "kernels.json", tmp_path / "manifests" / "kernels.json")
    lsk = (DATA / "kernels" / "naif0012.tls").read_bytes()
    (tmp_path / "kernels" / "naif0012.tls").write_bytes(lsk[:-1] + b"X")  # same size, wrong content
    with pytest.raises(DataMissingError, match="pinned checksum"):
        EphemerisService(tmp_path).series(0.0, 0.0, datetime(2027, 1, 15, tzinfo=UTC), 60, 1)


# ------------------------------------------------------------------ time conversion
@needs_kernels
def test_utc_to_et_known_values(svc):
    # J2000 epoch: 2000-01-01 12:00:00 UTC is 64.18392728... s of TDB past J2000 (TDB-UTC=64.184 s).
    assert svc.utc_to_et(datetime(2000, 1, 1, 12, tzinfo=UTC)) == pytest.approx(64.18392728, abs=1e-6)
    # The leap second of 2016-12-31 23:59:60 makes these two instants 2 SI seconds apart.
    a = svc.utc_to_et(datetime(2016, 12, 31, 23, 59, 59, tzinfo=UTC))
    b = svc.utc_to_et(datetime(2017, 1, 1, 0, 0, 0, tzinfo=UTC))
    assert b - a == pytest.approx(2.0, abs=1e-9)
    # Ordinary second.
    c = svc.utc_to_et(datetime(2027, 1, 15, 0, 0, 0, tzinfo=UTC))
    d = svc.utc_to_et(datetime(2027, 1, 15, 0, 0, 1, tzinfo=UTC))
    assert d - c == pytest.approx(1.0, abs=1e-9)
    # Fractional seconds survive.
    e = svc.utc_to_et(datetime(2027, 1, 15, 0, 0, 0, 500_000, tzinfo=UTC))
    assert e - c == pytest.approx(0.5, abs=1e-9)


@needs_kernels
def test_et_utc_roundtrip(svc):
    t = datetime(2031, 5, 5, 3, 3, 3, tzinfo=UTC)
    assert svc.et_to_utc(svc.utc_to_et(t)).startswith("2031-05-05T03:03:03")


# ------------------------------------------------------------------ Horizons reference (oracle)
@needs_kernels
def test_agrees_with_horizons_reference_grid(svc):
    """Pre-declared criterion (PRD): angular separation <= 0.01 deg for EVERY recorded row.

    The grid has 220 rows: 11 observers (both exact poles at non-zero longitude too, farside, a
    5321 m observer) x 10 epochs (2025-2035, a leap day included) x {Sun, Earth}.
    """
    from validate_ephemeris import SEPARATION_TOLERANCE_DEG, compare

    rows = compare()
    assert len(rows) == 220
    pole_sites = {r["site_id"] for r in rows if r["site_id"].endswith(("pole", "lon123", "lon270"))}
    assert {"south-pole", "south-pole-lon123", "north-pole-lon270"} <= pole_sites
    worst = max(rows, key=lambda r: r["sep_deg"])
    assert worst["sep_deg"] <= SEPARATION_TOLERANCE_DEG, worst
    # Regression guards, set (before commit) from the observed residuals with ~15x margin so that a
    # frame/aberration/time regression is caught long before the 0.01 deg criterion.
    assert max(r["sep_deg"] for r in rows if r["body"] == "sun") <= 2e-7
    assert max(r["sep_deg"] for r in rows if r["body"] == "earth") <= 1e-5
    # Range: agreement to 1 part in 1e7 (Sun) / 1e6 (Earth); angular diameter within 0.1 arcsec.
    assert max(abs(r["drange_rel"]) for r in rows if r["body"] == "sun") <= 1e-9
    assert max(abs(r["drange_rel"]) for r in rows if r["body"] == "earth") <= 1e-6
    assert max(abs(r["ddiam_arcsec"]) for r in rows) <= 0.1


def test_reference_file_provenance_is_recorded():
    doc = json.loads(REF.read_text(encoding="utf-8"))
    assert doc["horizons_signature"]["source"] == "NASA/JPL Horizons API"
    assert doc["request_template"]["APPARENT"] == "AIRLESS"
    assert len(doc["rows"]) == len(doc["sites"]) * len(doc["epochs_utc"]) * 2
    assert any(s["id"] == "south-pole" for s in doc["sites"])  # tie-break case is in the grid


# ------------------------------------------------------------------ physical sanity (non-Horizons)
@needs_kernels
def test_sun_elevation_at_south_pole_is_bounded_by_the_axial_tilt(svc):
    # The lunar spin axis is tilted ~1.54 deg to the ecliptic, so the Sun never leaves +-~1.6 deg
    # of the horizon at the pole. Scan a full year at 6-hour steps.
    res = svc.series(-90.0, 0.0, datetime(2027, 1, 1, tzinfo=UTC), 6 * 3600, 365 * 4, ("sun",))
    el = res.bodies["sun"].elevation_deg
    assert max(el) <= 1.6 and min(el) >= -1.6
    assert max(el) > 1.2 and min(el) < -1.2  # and it does use most of that range


@needs_kernels
def test_sun_azimuth_at_pole_circles_once_per_synodic_month(svc):
    res = svc.series(-89.0, 0.0, datetime(2027, 3, 1, tzinfo=UTC), 3600, 24 * 30 + 1, ("sun",))
    az = res.bodies["sun"].azimuth_deg
    steps = [(a1 - a0 + 180.0) % 360.0 - 180.0 for a0, a1 in itertools.pairwise(az)]
    total = sum(steps)
    # 30 days ~ one synodic month (29.53 d) => ~360 deg of azimuth; assert the magnitude and a
    # single monotonic sense of rotation rather than an assumed sign.
    assert 330.0 <= abs(total) <= 395.0
    assert all(s < 0 for s in steps) or all(s > 0 for s in steps)


@needs_kernels
def test_equator_sun_swings_through_zenith_each_month(svc):
    res = svc.series(0.0, 0.0, datetime(2027, 3, 1, tzinfo=UTC), 3600, 24 * 30 + 1, ("sun",))
    el = res.bodies["sun"].elevation_deg
    assert max(el) > 85.0 and min(el) < -85.0


@needs_kernels
def test_antipodal_sites_see_opposite_sun_elevation(svc):
    # Pure geometry: antipodal observers see the same distant body in opposite elevations. The
    # residual is bounded by the parallax of the 2R baseline: |el_a + el_b| <= 2R/d (radians).
    t = datetime(2028, 6, 1, 7, 30, tzinfo=UTC)
    for lat, lon in [(-84.79059, 29.19567), (12.3, 200.0), (-69.3741, 32.32)]:
        ra = svc.at(lat, lon, t, ("sun",)).bodies["sun"]
        rb = svc.at(-lat, lon - 180.0, t, ("sun",)).bodies["sun"]
        bound_deg = math.degrees(2 * REFERENCE_RADIUS_KM / ra.range_km[0])  # ~1.35e-3 deg
        assert abs(ra.elevation_deg[0] + rb.elevation_deg[0]) <= bound_deg * 1.001


@needs_kernels
def test_earth_visibility_geometry_nearside_vs_farside(svc):
    start = datetime(2027, 3, 1, tzinfo=UTC)
    near = svc.series(0.0, 0.0, start, 6 * 3600, 4 * 28, ("earth",)).bodies["earth"].elevation_deg
    far = svc.series(0.0, 180.0, start, 6 * 3600, 4 * 28, ("earth",)).bodies["earth"].elevation_deg
    assert min(near) > 70.0  # Earth stays near the zenith of the sub-Earth point (libration only)
    assert max(far) < -70.0  # and is hidden from the antipode of that point


@needs_kernels
def test_earth_elevation_at_pole_is_within_libration_bounds(svc):
    res = svc.series(-90.0, 0.0, datetime(2027, 1, 1, tzinfo=UTC), 12 * 3600, 2 * 365, ("earth",))
    el = res.bodies["earth"].elevation_deg
    # Latitudinal libration is +-6.7 deg, parallax shifts by up to 0.26 deg: Earth hovers near the
    # horizon, never high in the sky, and is below it for part of every month.
    assert -8.5 < min(el) < 0.0 < max(el) < 8.5


@needs_kernels
def test_ranges_and_light_time_are_physical(svc):
    res = svc.series(-84.79059, 29.19567, datetime(2027, 1, 1, tzinfo=UTC), 6 * 3600, 4 * 400)
    sun, earth = res.bodies["sun"], res.bodies["earth"]
    # Moon-Sun distance = Earth-Sun distance (0.9833-1.0167 AU) +- the Earth-Moon distance
    # (<= 407 000 km) +- the observer radius; bounds derived from those, not fitted.
    slack = 407_000.0 + REFERENCE_RADIUS_KM
    assert 0.9832 * AU_KM - slack <= min(sun.range_km)
    assert max(sun.range_km) <= 1.0168 * AU_KM + slack
    assert 354_000.0 <= min(earth.range_km) and max(earth.range_km) <= 409_000.0
    for body in (sun, earth):
        for r, lt in zip(body.range_km, body.light_time_s, strict=True):
            assert lt == pytest.approx(r / C_KM_S, rel=1e-6)
    assert 0.52 < min(sun.angular_diameter_deg) and max(sun.angular_diameter_deg) < 0.55
    # Earth: derived from the 354 000-409 000 km range bounds above (not fitted).
    lo, hi = (angular_diameter_deg(EARTH_EQUATORIAL_RADIUS_KM, d) for d in (409_000.0, 354_000.0))
    assert lo <= min(earth.angular_diameter_deg) and max(earth.angular_diameter_deg) <= hi


@needs_kernels
def test_results_change_with_time_and_location(svc):
    t = datetime(2027, 1, 15, tzinfo=UTC)
    a = svc.at(-84.79059, 29.19567, t)
    b = svc.at(-84.79059, 29.19567, t + timedelta(days=1))
    c = svc.at(-80.12759, 1.44587, t)
    assert abs(a.bodies["sun"].azimuth_deg[0] - b.bodies["sun"].azimuth_deg[0]) > 5.0
    assert abs(a.bodies["sun"].azimuth_deg[0] - c.bodies["sun"].azimuth_deg[0]) > 1.0
    assert abs(a.bodies["earth"].azimuth_deg[0] - c.bodies["earth"].azimuth_deg[0]) > 1.0


@needs_kernels
def test_observer_height_has_a_small_but_nonzero_effect_on_earth(svc):
    t = datetime(2027, 1, 15, tzinfo=UTC)
    lo = svc.at(-84.79059, 29.19567, t, ("earth",), 0.0).bodies["earth"]
    hi = svc.at(-84.79059, 29.19567, t, ("earth",), 5321.0).bodies["earth"]
    d_el = abs(lo.elevation_deg[0] - hi.elevation_deg[0])
    assert 1e-6 < d_el < 1e-3  # parallax of a 5.3 km baseline at 386 000 km: <= 7.9e-4 deg
    assert abs(lo.range_km[0] - hi.range_km[0]) < 6.0


@needs_kernels
def test_series_is_deterministic_and_consistent_with_single_calls(svc):
    start = datetime(2029, 10, 1, 18, 45, tzinfo=UTC)
    s1 = svc.series(-84.79059, 29.19567, start, 900, 12)
    s2 = svc.series(-84.79059, 29.19567, start, 900, 12)
    assert s1.bodies["sun"].azimuth_deg == s2.bodies["sun"].azimuth_deg
    assert s1.times_utc[0] == "2029-10-01T18:45:00Z" and s1.times_utc[-1] == "2029-10-01T21:30:00Z"
    single = svc.at(-84.79059, 29.19567, start + timedelta(seconds=900 * 7))
    for b in BODIES:
        assert single.bodies[b].elevation_deg[0] == pytest.approx(
            s1.bodies[b].elevation_deg[7], abs=1e-9)


@needs_kernels
def test_provenance_pins_kernels_frame_and_assumptions(svc):
    prov = svc.at(0.0, 0.0, datetime(2027, 1, 15, tzinfo=UTC)).provenance
    manifest = json.loads((DATA / "manifests" / "kernels.json").read_text(encoding="utf-8"))["files"]
    assert prov["frame"] == "MOON_ME" and prov["aberration_correction"] == "LT+S"
    files = {k["file"]: k["sha256"] for k in prov["kernels"]}
    assert set(files) == {"naif0012.tls", "de440s.bsp", "moon_pa_de440_200625.bpc",
                          "moon_de440_250416.tf"}
    for name, sha in files.items():
        assert manifest[name]["sha256"] == sha
    assert "gravitational light deflection" in prov["unmodelled"]
    assert prov["refraction"].startswith("none")


@needs_kernels
def test_moon_me_not_moon_pa_is_the_working_frame(svc):
    import spiceypy as sp

    svc.load()
    assert sp.namfrm("MOON_ME") == 31001
    assert sp.namfrm("MOON_PA") == 31000  # the ~875 m-offset frame; must never be used with the DEM
    assert sp.frmnam(31001) == "MOON_ME"
