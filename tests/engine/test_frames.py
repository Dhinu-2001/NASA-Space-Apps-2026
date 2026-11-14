"""Frame/geometry unit tests (pure math, no SPICE, no data files)."""

import math

import numpy as np
import pytest
from lunarnav.frames import (
    EARTH_EQUATORIAL_RADIUS_KM,
    REFERENCE_RADIUS_KM,
    SUN_RADIUS_KM,
    angular_diameter_deg,
    enu_basis,
    site_position_km,
    vector_to_azel,
)

SITES = [(0.0, 0.0), (-84.79059, 29.19567), (45.0, -100.0), (-69.3741, 32.32), (89.0, 270.0)]


@pytest.mark.parametrize(("lat", "lon"), SITES)
def test_enu_basis_is_orthonormal_and_right_handed(lat, lon):
    b = enu_basis(lat, lon)
    for v in (b.east, b.north, b.up):
        assert np.linalg.norm(v) == pytest.approx(1.0, abs=1e-14)
    assert np.dot(b.east, b.north) == pytest.approx(0.0, abs=1e-14)
    assert np.dot(b.east, b.up) == pytest.approx(0.0, abs=1e-14)
    assert np.dot(b.north, b.up) == pytest.approx(0.0, abs=1e-14)
    assert np.allclose(np.cross(b.east, b.north), b.up, atol=1e-14)  # E x N = U


@pytest.mark.parametrize(("lat", "lon"), SITES)
def test_site_position_radius_and_up_agree(lat, lon):
    p = site_position_km(lat, lon, 0.0)
    assert np.linalg.norm(p) == pytest.approx(REFERENCE_RADIUS_KM, abs=1e-9)
    assert np.allclose(p / np.linalg.norm(p), enu_basis(lat, lon).up, atol=1e-14)


def test_site_height_adds_to_radius():
    assert np.linalg.norm(site_position_km(10, 20, 5321.0)) == pytest.approx(
        REFERENCE_RADIUS_KM + 5.321, abs=1e-9)


def test_known_site_axes():
    # lat 0, lon 0: up = +x (toward mean Earth), east = +y, north = +z.
    b = enu_basis(0.0, 0.0)
    assert np.allclose(b.up, [1, 0, 0]) and np.allclose(b.east, [0, 1, 0])
    assert np.allclose(b.north, [0, 0, 1])


def test_azimuth_convention_clockwise_from_north():
    b = enu_basis(10.0, 30.0)
    cases = {0.0: b.north, 90.0: b.east, 180.0: -b.north, 270.0: -b.east}
    for expected_az, vec in cases.items():
        az, el, rng = vector_to_azel(vec * 5.0, b)
        assert az == pytest.approx(expected_az, abs=1e-9)
        assert el == pytest.approx(0.0, abs=1e-9)
        assert rng == pytest.approx(5.0)
    # NE at 45 deg elevation
    az, el, _ = vector_to_azel(b.north + b.east + math.sqrt(2) * b.up, b)
    assert az == pytest.approx(45.0) and el == pytest.approx(45.0)
    assert vector_to_azel(b.up, b)[1] == pytest.approx(90.0)
    assert vector_to_azel(-b.up, b)[1] == pytest.approx(-90.0)


def test_north_points_toward_the_lunar_north_pole():
    # Moving along the local north direction increases latitude.
    lat, lon = -84.0, 40.0
    b = enu_basis(lat, lon)
    p0 = site_position_km(lat, lon)
    p1 = p0 + b.north * 1.0  # 1 km north
    assert math.degrees(math.asin(p1[2] / np.linalg.norm(p1))) > lat


@pytest.mark.parametrize("lon", [0.0, 29.19567, 123.0, 270.0])
def test_pole_tie_break_is_continuous_with_the_limit_along_the_meridian(lon):
    """At exactly lat=-90 the supplied longitude defines north (documented tie-break)."""
    target = np.array([3.0, -2.0, 1.5])  # arbitrary fixed direction in MOON_ME
    exact = vector_to_azel(target, enu_basis(-90.0, lon))
    near = vector_to_azel(target, enu_basis(-90.0 + 1e-9, lon))
    assert exact[0] == pytest.approx(near[0], abs=1e-6)
    assert exact[1] == pytest.approx(near[1], abs=1e-6)


def test_pole_with_lon_zero_north_is_plus_x_at_south_pole():
    # Methodology tie-break: meridian lon=0 defines north. At the south pole, north = +x.
    b = enu_basis(-90.0, 0.0)
    assert np.allclose(b.north, [1, 0, 0], atol=1e-14)
    assert np.allclose(b.up, [0, 0, -1], atol=1e-14)


def test_zero_vector_rejected():
    with pytest.raises(ValueError):
        vector_to_azel(np.zeros(3), enu_basis(0, 0))


def test_angular_diameter_known_values():
    # Sun at 1 AU: ~0.5332 deg (nominal radius). Earth from the Moon: ~1.9 deg.
    assert angular_diameter_deg(SUN_RADIUS_KM, 149_597_870.7) == pytest.approx(0.5331, abs=1e-3)
    assert angular_diameter_deg(EARTH_EQUATORIAL_RADIUS_KM, 384_400.0) == pytest.approx(
        1.9000, abs=2e-3)
    # exact geometry: sin(half-angle) = R / d
    assert angular_diameter_deg(1.0, 2.0) == pytest.approx(60.0)
    with pytest.raises(ValueError):
        angular_diameter_deg(10.0, 10.0)
