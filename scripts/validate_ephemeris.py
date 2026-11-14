"""Compare the local SPICE engine with the recorded JPL Horizons reference (Stage 3 validation).

Pre-declared acceptance criterion (PRD, fixed before results were examined):
  angular separation between engine and Horizons direction <= 0.01 deg for every row.
Also reported (not pass/fail): azimuth, elevation, range and angular-diameter residuals.

Usage: .\\.venv\\Scripts\\python.exe -I scripts\\validate_ephemeris.py [--json out.json]
"""

from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

from lunarnav.ephemeris import BODIES, EphemerisService, parse_utc

REF = ROOT / "data" / "validation" / "horizons_stage3_reference.json"
SEPARATION_TOLERANCE_DEG = 0.01


def separation_deg(az1: float, el1: float, az2: float, el2: float) -> float:
    """Great-circle angle between two (az, el) directions, haversine form (stable for tiny angles)."""
    p1, p2 = math.radians(el1), math.radians(el2)
    dl = math.radians(az2 - az1)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return math.degrees(2 * math.asin(min(1.0, math.sqrt(h))))


def compare() -> list[dict]:
    doc = json.loads(REF.read_text(encoding="utf-8"))
    sites = {s["id"]: s for s in doc["sites"]}
    svc = EphemerisService(ROOT / "data")
    out = []
    for row in doc["rows"]:
        s = sites[row["site_id"]]
        res = svc.at(s["lat_deg"], s["lon_deg_east"], parse_utc(row["time_utc"]), (row["body"],),
                     s["height_m"])
        b = res.bodies[row["body"]]
        az, el, rng, diam = b.azimuth_deg[0], b.elevation_deg[0], b.range_km[0], b.angular_diameter_deg[0]
        daz = (az - row["az_deg"] + 180.0) % 360.0 - 180.0
        sep = separation_deg(az, el, row["az_deg"], row["el_deg"])
        hz_diam_deg = row["ang_diam_arcsec"] / 3600.0
        # radius Horizons implicitly used, from its own diameter and range
        implied_radius = row["range_km"] * math.sin(math.radians(hz_diam_deg) / 2)
        out.append({
            "site_id": row["site_id"], "body": row["body"], "time_utc": row["time_utc"],
            "sep_deg": sep, "daz_deg": daz, "del_deg": el - row["el_deg"],
            "drange_km": rng - row["range_km"], "drange_rel": (rng - row["range_km"]) / row["range_km"],
            "ddiam_arcsec": (diam - hz_diam_deg) * 3600.0, "hz_implied_radius_km": implied_radius,
            "el_deg": el, "az_deg": az,
        })
    return out


def summarise(rows: list[dict]) -> dict:
    by_body: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_body[r["body"]].append(r)
    summary: dict = {"n_rows": len(rows), "tolerance_deg": SEPARATION_TOLERANCE_DEG, "bodies": {}}
    for body, rs in by_body.items():
        seps = [r["sep_deg"] for r in rs]
        worst = max(rs, key=lambda r: r["sep_deg"])
        summary["bodies"][body] = {
            "n": len(rs),
            "sep_max_deg": max(seps),
            "sep_rms_deg": math.sqrt(sum(x * x for x in seps) / len(seps)),
            "sep_worst_case": {k: worst[k] for k in ("site_id", "time_utc", "sep_deg")},
            "el_abs_max_deg": max(abs(r["del_deg"]) for r in rs),
            "az_abs_max_deg_(any_el)": max(abs(r["daz_deg"]) for r in rs),
            "range_abs_max_km": max(abs(r["drange_km"]) for r in rs),
            "range_rel_max": max(abs(r["drange_rel"]) for r in rs),
            "ddiam_abs_max_arcsec": max(abs(r["ddiam_arcsec"]) for r in rs),
            "horizons_implied_radius_km": {
                "min": min(r["hz_implied_radius_km"] for r in rs),
                "max": max(r["hz_implied_radius_km"] for r in rs),
                "engine_assumed": BODIES[body]["radius_km"],
            },
        }
    summary["pass"] = all(r["sep_deg"] <= SEPARATION_TOLERANCE_DEG for r in rows)
    return summary


if __name__ == "__main__":
    rows = compare()
    summary = summarise(rows)
    print(json.dumps(summary, indent=1))
    per_site = defaultdict(float)
    for r in rows:
        per_site[(r["site_id"], r["body"])] = max(per_site[(r["site_id"], r["body"])], r["sep_deg"])
    print("\nmax separation per (site, body), deg:")
    for k, v in sorted(per_site.items()):
        print(f"  {k[0]:20s} {k[1]:6s} {v:.3e}")
    if "--json" in sys.argv:
        Path(sys.argv[sys.argv.index("--json") + 1]).write_text(json.dumps(summary, indent=1))
    sys.exit(0 if summary["pass"] else 1)
