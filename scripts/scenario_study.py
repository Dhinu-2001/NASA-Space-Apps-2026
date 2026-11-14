"""Stage 6 study: example comparison and mission-delay sweep (IM-2 supported; IM-1 / Chandrayaan-3 excluded).

Writes a compact summary (tables, rankings, delta sentences) -- not the full scenario bodies.

Usage: .\\.venv\\Scripts\\python.exe -I scripts\\scenario_study.py [--json docs/stage6/scenario_study.json]
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

from lunarnav.ephemeris import EphemerisService
from lunarnav.horizon import HorizonService
from lunarnav.scenarios import ScenarioService
from lunarnav.visibility import VisibilityService


def row(s: dict) -> dict:
    out = {"label": s["spec"]["label"], "status": s["status"], "id": s["id"]}
    if s["status"] != "supported":
        out["reason"] = s["reason"]
        return out
    for b in ("sun", "earth"):
        t, g = s["bodies"][b]["terrain_corrected"], s["bodies"][b]["geometric"]
        out[b] = {
            "terrain_visible_fraction": t["visible_fraction"],
            "geometric_visible_fraction": g["visible_fraction"]["nominal"],
            "terrain_minus_geometric_visible_s": s["bodies"][b]["terrain_effect"]["visible_s_terrain_minus_geometric"],
            "longest_not_visible_s": {k: t["longest_not_visible_s"][k] for k in
                                      ("including_open", "band_including_open", "includes_open_interval")},
            "events": [{"type": e["type"], "time_utc": e["time_utc"], "band_width_s": e["band"]["width_s"],
                        "band_complete": e["band"]["complete"]} for e in t["events"]],
            "open_intervals": t["open_intervals"],
        }
    return out


def main() -> dict:
    sv = ScenarioService(ROOT / "data", VisibilityService(EphemerisService(ROOT / "data"), HorizonService(ROOT / "data")))
    out: dict = {}
    t0 = time.time()
    print("comparison (2 IM-2 positions + IM-1 + Chandrayaan-3) x 2 dates", flush=True)
    specs = [sv.make_spec({"site_id": s}, d, duration_days=30.0, label=f"{s} @ {d[:10]}")
             for s in ("im2-athena", "im2-intended", "im1-odysseus", "chandrayaan3-shiv-shakti")
             for d in ("2027-01-15T00:00:00Z", "2027-03-15T00:00:00Z")]
    cmp_ = sv.compare(specs, 0)
    out["comparison"] = {
        "runtime_s": time.time() - t0,
        "scenarios": [row(s) for s in cmp_["scenarios"]],
        "excluded": cmp_["excluded_terrain_data_insufficient"],
        "rankings": [{"criterion": r["criterion"], "ranking": [
            {k: x[k] for k in ("rank", "label", "nominal", "band", "includes_open_interval", "distinguishable_from_next")}
            for x in r["ranking"]]} for r in cmp_["rankings"]],
        "deltas_vs_first_scenario": [{"scenario_id": d["scenario_id"], "method": d["delta_band_method"],
                                      "sun": d["bodies"]["sun"]["summary"], "earth": d["bodies"]["earth"]["summary"]}
                                     for d in cmp_["deltas_vs_baseline"]],
        "notes": cmp_["notes"],
    }
    print("delay sweep", flush=True)
    t0 = time.time()
    offsets = [1, 2, 3, 5, 7, 10, 14, 21]
    dly = sv.delay({"site_id": "im2-athena"}, "2027-01-15T00:00:00Z", offsets, duration_days=14.0)
    out["delay_14d_window"] = {
        "runtime_s": time.time() - t0, "baseline_start_utc": "2027-01-15T00:00:00Z", "duration_days": 14.0,
        "table": dly["summary_table"],
        "deltas": [{"offset_days": d["offset_days"], "method": d["delta_vs_baseline"]["delta_band_method"],
                    "sun": d["delta_vs_baseline"]["bodies"]["sun"]["summary"],
                    "earth": d["delta_vs_baseline"]["bodies"]["earth"]["summary"]} for d in dly["delays"]],
    }
    print("delay sweep, 30-day window (hides short delays)", flush=True)
    d30 = sv.delay({"site_id": "im2-athena"}, "2027-01-15T00:00:00Z", [1, 3, 7, 14], duration_days=30.0)
    out["delay_30d_window"] = {"table": d30["summary_table"]}
    return out


if __name__ == "__main__":
    res = main()
    if "--json" in sys.argv:
        Path(sys.argv[sys.argv.index("--json") + 1]).write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    print("done")
