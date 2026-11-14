"""Fetch independent JPL Horizons reference values for the Stage 3 validation (decision E2).

Horizons is the *oracle only*; the engine itself uses local SPICE. This script records what
Horizons returned for a fixed grid of lunar-surface observers and epochs into a small tracked
JSON fixture (data/validation/horizons_stage3_reference.json) so the tests run offline and the
comparison is reproducible.

Request (verified live 2026-11-14): CENTER='coord@301' COORD_TYPE='GEODETIC'
SITE_COORD='lonE,lat,alt_km', QUANTITIES='4,13,20' (apparent az/el, target angular diameter,
range & range rate), APPARENT='AIRLESS', EXTRA_PREC='YES', UT calendar-string epochs.

Usage:  .\\.venv\\Scripts\\python.exe -I scripts\\fetch_horizons_reference.py
The grid below contains validation *test points*; they are not landing-site claims.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "validation" / "horizons_stage3_reference.json"
API = "https://ssd.jpl.nasa.gov/api/horizons.api"
AU_KM = 149_597_870.7  # IAU 2012 definition

# (id, lat_deg planetocentric, lon_deg east, height_m above 1737.4 km sphere, note)
SITES = [
    ("im2-athena", -84.79059, 29.19567, 0.0, "catalogue site (NAIF CLPS kernel)"),
    ("im2-athena-h5321", -84.79059, 29.19567, 5321.0, "same, observer 5321 m up: tests height handling"),
    ("im1-odysseus", -80.12759, 1.44587, 0.0, "catalogue site"),
    ("chandrayaan3", -69.3741, 32.32, 0.0, "catalogue site"),
    ("south-pole", -90.0, 0.0, 0.0, "exact pole: tests the azimuth tie-break"),
    ("south-pole-lon123", -90.0, 123.0, 0.0, "exact pole, non-zero longitude: tie-break uses lon"),
    ("north-pole-lon270", 90.0, 270.0, 0.0, "exact north pole, lon given as 270 E"),
    ("near-south-pole", -89.9, 123.0, 0.0, "0.1 deg from pole, off-meridian"),
    ("equator-nearside", 0.0, 0.0, 0.0, "sub-Earth region: Earth near zenith"),
    ("equator-farside", 0.0, 180.0, 0.0, "farside: Earth below the horizon"),
    ("north-midlat", 45.0, -100.0, 0.0, "northern hemisphere, longitude given negative"),
]
# Whole-second UTC epochs spanning the validated range (2025-2035), incl. a leap day.
EPOCHS = [
    "2025-01-01 00:00:00", "2025-07-04 06:30:00", "2026-03-20 12:00:00", "2027-01-15 00:00:00",
    "2027-01-15 09:17:45", "2028-02-29 23:59:59", "2029-10-01 18:45:00", "2031-05-05 03:03:03",
    "2033-12-25 12:00:00", "2035-12-31 23:00:00",
]
BODIES = {"sun": "10", "earth": "399"}


def query(command: str, lat: float, lon: float, height_m: float) -> tuple[str, dict]:
    tlist = " ".join(f"'{e}'" for e in EPOCHS)
    params = {
        "format": "json", "COMMAND": f"'{command}'", "OBJ_DATA": "'NO'", "MAKE_EPHEM": "'YES'",
        "EPHEM_TYPE": "'OBSERVER'", "CENTER": "'coord@301'", "COORD_TYPE": "'GEODETIC'",
        "SITE_COORD": f"'{lon},{lat},{height_m / 1000.0}'", "TLIST": tlist, "TIME_TYPE": "'UT'",
        "QUANTITIES": "'4,13,20'", "ANG_FORMAT": "'DEG'", "CSV_FORMAT": "'YES'",
        "APPARENT": "'AIRLESS'", "EXTRA_PREC": "'YES'",
    }
    url = API + "?" + urllib.parse.urlencode(params)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=90) as resp:
                doc = json.loads(resp.read())
            break
        except Exception as exc:  # network flakiness: back off and retry, then fail loudly
            if attempt == 3:
                raise
            print(f"  retry after error: {exc}", file=sys.stderr)
            time.sleep(5 * (attempt + 1))
    return doc["result"], doc.get("signature", {})


def parse(result: str) -> list[dict]:
    if "$$SOE" not in result:
        raise RuntimeError("Horizons returned no ephemeris:\n" + result[:800])
    block = result.split("$$SOE")[1].split("$$EOE")[0].strip().splitlines()
    rows = []
    for line in block:
        c = [x.strip() for x in line.split(",")]
        rows.append({
            "date": c[0], "az_deg": float(c[3]), "el_deg": float(c[4]),
            "ang_diam_arcsec": float(c[5]), "range_km": float(c[6]) * AU_KM,
            "range_rate_km_s": float(c[7]),
        })
    return rows


def main() -> None:
    rows, signature = [], {}
    for site_id, lat, lon, height, _note in SITES:
        for body, command in BODIES.items():
            print(f"{site_id} / {body}", flush=True)
            result, signature = query(command, lat, lon, height)
            parsed = parse(result)
            if len(parsed) != len(EPOCHS):
                raise RuntimeError(f"expected {len(EPOCHS)} rows, got {len(parsed)}")
            for epoch, r in zip(EPOCHS, parsed, strict=True):
                want = datetime.strptime(epoch, "%Y-%m-%d %H:%M:%S")
                got = datetime.strptime(r["date"], "%Y-%b-%d %H:%M:%S.%f")
                if want != got:  # guard against Horizons reordering / reinterpreting epochs
                    raise RuntimeError(f"epoch mismatch: asked {epoch}, got {r['date']}")
                rows.append({"site_id": site_id, "body": body,
                             "time_utc": want.strftime("%Y-%m-%dT%H:%M:%SZ"),
                             **{k: v for k, v in r.items() if k != "date"}})
            time.sleep(1.0)  # polite pacing
    doc = {
        "purpose": "Independent JPL Horizons reference for Stage 3 ephemeris validation",
        "retrieved_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "horizons_signature": signature,
        "endpoint": API,
        "request_template": {
            "CENTER": "coord@301", "COORD_TYPE": "GEODETIC", "SITE_COORD": "lonE,lat,alt_km",
            "QUANTITIES": "4,13,20", "APPARENT": "AIRLESS", "EXTRA_PREC": "YES",
            "TIME_TYPE": "UT", "COMMAND": BODIES,
        },
        "notes": [
            "Horizons frame for coord@301 is MEAN_ME (high precision), ephemeris DE441.",
            "range_km = delta(AU) * 149597870.7.",
            "These are validation test points, not landing-site claims.",
        ],
        "sites": [{"id": s[0], "lat_deg": s[1], "lon_deg_east": s[2], "height_m": s[3],
                   "note": s[4]} for s in SITES],
        "epochs_utc": [datetime.strptime(e, "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%dT%H:%M:%SZ")
                       for e in EPOCHS],
        "rows": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
