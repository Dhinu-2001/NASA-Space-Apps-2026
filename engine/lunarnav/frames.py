"""Coordinate transformations between the lunar body-fixed frame and the local observer frame.

Pure geometry, no SPICE, no I/O. Every function states its frame and units.

Frames used here:
  MOON_ME  Moon body-fixed Mean Earth/polar-axis frame (x toward mean Earth at lon 0 / lat 0,
           z toward the lunar north pole). Kilometres. This is the frame of the LOLA DEM.
  ENU      Local East-North-Up frame at the observer. Axes are unit vectors expressed in MOON_ME.

Conventions (docs/stage3/EPHEMERIS_METHOD.md):
  * latitude planetocentric, south negative; longitude east positive; the Moon is a sphere of
    radius R = 1737.4 km for site placement (identical to the LOLA / Horizons reference).
  * azimuth is measured clockwise from local north, [0, 360); elevation is above the local
    horizontal plane (perpendicular to the local radial direction), [-90, 90].
  * Pole tie-break: east = (-sin lon, cos lon, 0) and north = up x east are evaluated with the
    *supplied* longitude, even at lat = +-90. This is the limit of the formulas along that
    meridian, so az/el are continuous as the site approaches the pole. For lon = 0 this is the
    "meridian of lon = 0 defines north" rule of the methodology document.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .sites import REFERENCE_RADIUS_M

REFERENCE_RADIUS_KM = REFERENCE_RADIUS_M / 1000.0

# IAU 2015 Resolution B3 nominal values (documented assumptions, not measurements).
SUN_RADIUS_KM = 695_700.0
EARTH_EQUATORIAL_RADIUS_KM = 6378.1


@dataclass(frozen=True)
class EnuBasis:
    """Unit vectors of the local frame, expressed in MOON_ME."""

    east: np.ndarray
    north: np.ndarray
    up: np.ndarray


def site_position_km(lat_deg: float, lon_deg_east: float, height_m: float = 0.0) -> np.ndarray:
    """Observer position in MOON_ME, km, relative to the Moon centre.

    Radius = R_ref + height. `height_m` is measured above the 1737.4 km reference sphere
    (the LOLA height convention).
    """
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg_east)
    radius = REFERENCE_RADIUS_KM + height_m / 1000.0
    return radius * np.array(
        [math.cos(lat) * math.cos(lon), math.cos(lat) * math.sin(lon), math.sin(lat)]
    )


def enu_basis(lat_deg: float, lon_deg_east: float) -> EnuBasis:
    """Local East/North/Up unit vectors in MOON_ME for a site (see module pole tie-break)."""
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg_east)
    east = np.array([-math.sin(lon), math.cos(lon), 0.0])
    up = np.array(
        [math.cos(lat) * math.cos(lon), math.cos(lat) * math.sin(lon), math.sin(lat)]
    )
    north = np.cross(up, east)
    return EnuBasis(east=east, north=north, up=up)


def vector_to_azel(vec_moon_me: np.ndarray, basis: EnuBasis) -> tuple[float, float, float]:
    """Topocentric vector (MOON_ME, any length unit) -> (azimuth_deg, elevation_deg, range).

    The returned range is in the same unit as the input vector.
    """
    e = float(np.dot(vec_moon_me, basis.east))
    n = float(np.dot(vec_moon_me, basis.north))
    u = float(np.dot(vec_moon_me, basis.up))
    rng = math.sqrt(e * e + n * n + u * u)
    if rng == 0.0:
        raise ValueError("zero-length topocentric vector")
    az = math.degrees(math.atan2(e, n)) % 360.0
    el = math.degrees(math.asin(max(-1.0, min(1.0, u / rng))))
    return az, el, rng


def angular_diameter_deg(radius_km: float, range_km: float) -> float:
    """Apparent angular diameter of a sphere seen from `range_km` (centre to centre), degrees."""
    if range_km <= radius_km:
        raise ValueError("observer is inside the body")
    return math.degrees(2.0 * math.asin(radius_km / range_km))


def destination_deg(lat_deg: float, lon_deg_east: float, azimuth_deg: float, distance_m: float
                    ) -> tuple[float, float]:
    """Point reached by travelling `distance_m` along the great circle that leaves the site at `azimuth_deg`
    (clockwise from local north, same E4 convention) on the 1737.4 km sphere. Returns (lat, lon_east) with
    lon in [-180, 180]. Used for position-uncertainty displacements."""
    basis = enu_basis(lat_deg, lon_deg_east)
    az = math.radians(azimuth_deg)
    theta = distance_m / (REFERENCE_RADIUS_KM * 1000.0)
    t = math.cos(az) * basis.north + math.sin(az) * basis.east
    p = basis.up * math.cos(theta) + t * math.sin(theta)
    return math.degrees(math.asin(max(-1.0, min(1.0, float(p[2]))))), math.degrees(math.atan2(p[1], p[0]))
