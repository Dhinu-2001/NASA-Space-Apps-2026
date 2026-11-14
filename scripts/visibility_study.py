"""Stage 5 study (IM-2 Athena only): headline visibility result, position-sensitivity sweep, step-size convergence.

Position sensitivity is computed only where terrain data support it (IM-2). Nothing here is extrapolated to IM-1
or Chandrayaan-3.

Usage: .\\.venv\\Scripts\\python.exe -I scripts\\visibility_study.py [--json docs/stage5/im2_study.json]
"""

from __future__ import annotations

import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

from lunarnav.ephemeris import EphemerisService
from lunarnav.horizon import HorizonService
from lunarnav.visibility import VisibilityService

SITE = (-84.79059, 29.19567)
START = datetime(2027, 1, 15, tzinfo=UTC)
DAYS = 30


def slim(res: dict, body: str) -> dict:
    d = res["bodies"][body]
    h = d["headline"]
    ps = h["position_sensitivity"]
    out = {
        "headline_state": d["headline_state"], "terrain_effect": d["terrain_effect"], "completeness": d["completeness"],
        "metrics": h["metrics"],
        "intervals": [{k: i[k] for k in ("start_utc", "end_utc", "duration_s", "open_start", "open_end",
                                          "start_band", "end_band")} for i in h["intervals"]],
        "not_visible_intervals": [{k: i[k] for k in ("start_utc", "end_utc", "duration_s", "open_start", "open_end",
                                                      "start_band", "end_band")} for i in h["not_visible_intervals"]],
    }
    if ps.get("status") == "computed":
        out["position_sensitivity"] = {k: ps[k] for k in ("metric_bands", "events_only_in_displaced_runs",
                                                          "max_boundary_band_width_s")}
        out["position_sensitivity"]["boundary_bands"] = ps["boundary_bands"]
        s = d.get("series")
        if s:
            out["position_sensitivity"]["max_horizon_shift_at_body_deg"] = max(s["position_sensitivity_deg"])
            out["position_sensitivity"]["fraction_steps_state_not_robust"] = 1 - sum(
                s["headline_state_robust_to_position"]) / len(s["headline_state_robust_to_position"])
    return out


def main() -> dict:
    vis = VisibilityService(EphemerisService(ROOT / "data"), HorizonService(ROOT / "data"))
    n15 = DAYS * 96 + 1
    out: dict = {"site": "im2-athena", "lat": SITE[0], "lon": SITE[1], "start_utc": "2027-01-15T00:00:00Z",
                 "days": DAYS, "observer_height_m": 2.0, "observer_height_is_default_assumption": True}

    print("headline run: 100 m band, 15 min step", flush=True)
    t0 = time.time()
    base = vis.evaluate(*SITE, START, 900.0, n15, 2.0, position_uncertainty_m=100.0).to_dict()
    out["runtime_s_first_100m"] = time.time() - t0
    out["horizon"] = base["horizon"]
    out["position_sensitivity_block"] = base["position_sensitivity"]
    out["bodies_100m"] = {b: slim(base, b) for b in ("sun", "earth")}

    out["band_sweep"] = {}
    for band in (20.0, 50.0, 100.0, 200.0):
        print(f"band sweep {band:g} m", flush=True)
        r = base if band == 100.0 else vis.evaluate(*SITE, START, 900.0, n15, 2.0, position_uncertainty_m=band,
                                                    include_series=False).to_dict()
        entry = {}
        for b in ("sun", "earth"):
            ps = r["bodies"][b]["headline"]["position_sensitivity"]
            entry[b] = {
                "max_boundary_band_width_s": ps["max_boundary_band_width_s"],
                "boundary_bands_complete": sum(x["band_complete"] for x in ps["boundary_bands"]),
                "n_boundaries": len(ps["boundary_bands"]),
                "events_only_in_displaced_runs": ps["events_only_in_displaced_runs"],
                "total_visible_s_band": ps["metric_bands"]["total_visible_s"],
                "n_visible_intervals_band": ps["metric_bands"]["n_visible_intervals"],
            }
        out["band_sweep"][f"{band:g}m"] = entry

    print("step convergence", flush=True)
    out["step_convergence"] = {}
    for step, n in ((900.0, n15), (300.0, DAYS * 288 + 1)):
        r = vis.evaluate(*SITE, START, step, n, 2.0, position_uncertainty_m=None, include_series=False).to_dict()
        out["step_convergence"][f"{step:g}s"] = {
            b: {"total_visible_s": r["bodies"][b]["headline"]["metrics"]["total_visible_s"],
                "n_visible_intervals": r["bodies"][b]["headline"]["metrics"]["n_visible_intervals"],
                "transitions": [t["time_utc"] for t in r["bodies"][b]["states"][
                    r["bodies"][b]["headline_state"].replace("_visible", "")]["transitions"]]}
            for b in ("sun", "earth")}
    return out


if __name__ == "__main__":
    res = main()
    text = json.dumps(res, indent=1)
    if "--json" in sys.argv:
        Path(sys.argv[sys.argv.index("--json") + 1]).write_text(text + "\n", encoding="utf-8")
    print("done")
