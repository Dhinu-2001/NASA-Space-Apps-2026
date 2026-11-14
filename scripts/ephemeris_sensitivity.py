"""Measure how much each modelling choice moves the Sun/Earth direction (Stage 3 methodology risk 1).

Not a validation: it quantifies the *size* of effects that the engine either includes (light time,
stellar aberration, topocentric parallax) or must never confuse (MOON_PA vs MOON_ME).
Directions are compared as angular separations in the local sky of each observer.

Usage: .\\.venv\\Scripts\\python.exe -I scripts\\ephemeris_sensitivity.py [--json out.json]
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

import spiceypy as sp
from lunarnav.ephemeris import FRAME, EphemerisService, parse_utc
from lunarnav.frames import enu_basis, site_position_km, vector_to_azel
from validate_ephemeris import separation_deg

SITES = {"im2-athena": (-84.79059, 29.19567), "south-pole": (-90.0, 0.0),
         "equator-nearside": (0.0, 0.0), "chandrayaan3": (-69.3741, 32.32)}
EPOCHS = ["2025-01-01T00:00:00Z", "2026-03-20T12:00:00Z", "2027-01-15T00:00:00Z",
          "2029-10-01T18:45:00Z", "2031-05-05T03:03:03Z", "2033-12-25T12:00:00Z"]


def azel(body: str, et: float, lat: float, lon: float, abcorr: str, frame: str) -> tuple[float, float]:
    pos = site_position_km(lat, lon)
    st, _ = sp.spkcpo(body, et, frame, "OBSERVER", abcorr, list(pos), "MOON", frame)
    az, el, _ = vector_to_azel(st[:3], enu_basis(lat, lon))
    return az, el


def geocentric_azel(body: str, et: float, lat: float, lon: float) -> tuple[float, float]:
    """Direction as seen from the Moon's *centre* (no topocentric parallax), then projected
    onto the site's local frame. Shows what neglecting the observer offset would cost."""
    st, _ = sp.spkezr(body, et, FRAME, "LT+S", "MOON")
    az, el, _ = vector_to_azel(st[:3], enu_basis(lat, lon))
    return az, el


def main() -> dict:
    svc = EphemerisService(ROOT / "data")
    svc.load()
    out: dict = {}
    for body in ("SUN", "EARTH"):
        worst: dict[str, float] = {}
        for lat, lon in SITES.values():
            for e in EPOCHS:
                et = svc.utc_to_et(parse_utc(e))
                ref = azel(body, et, lat, lon, "LT+S", FRAME)
                trials = {
                    "no_light_time_no_aberration (NONE)": azel(body, et, lat, lon, "NONE", FRAME),
                    "light_time_only (LT)": azel(body, et, lat, lon, "LT", FRAME),
                    "geocentric (observer at Moon centre, LT+S)": geocentric_azel(body, et, lat, lon),
                    "wrong_frame MOON_PA (same lat/lon)": azel(body, et, lat, lon, "LT+S", "MOON_PA"),
                }
                for k, v in trials.items():
                    worst[k] = max(worst.get(k, 0.0), separation_deg(*ref, *v))
        out[body.lower()] = {k: v for k, v in worst.items()}
    # Frame realisation difference quoted by NAIF (MOON_ME vs DE421 ME): 3.07e-7 rad.
    out["naif_quoted_me_vs_de421_me_max_deg"] = math.degrees(3.0709840342771e-07)
    return out


if __name__ == "__main__":
    res = main()
    print("Max angular shift of the direction (degrees) relative to the engine's LT+S/MOON_ME result,")
    print("over 4 observers x 6 epochs:\n")
    for body in ("sun", "earth"):
        print(body.upper())
        for k, v in res[body].items():
            print(f"  {k:48s} {v:.3e} deg  ({v * 3600:.3f} arcsec)")
    print(f"\nNAIF-quoted MOON_ME vs DE421-ME max rotation: {res['naif_quoted_me_vs_de421_me_max_deg']:.2e} deg")
    if "--json" in sys.argv:
        Path(sys.argv[sys.argv.index("--json") + 1]).write_text(json.dumps(res, indent=1))
