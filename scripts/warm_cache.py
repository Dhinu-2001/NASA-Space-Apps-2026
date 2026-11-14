"""Warm the on-disk caches so a live demo has no multi-minute first-call wait.

Computes (and thereby caches in data/results/) everything the default UI views request:
  * terrain horizon profiles at IM-2 (landing position and pre-landing target) and at the 8 displaced positions
    used for the +/-100 m position-sensitivity band (0.25 deg azimuth step, the UI default),
  * the default scenario comparison (4 sites x 2 dates, 30 days) and the default delay simulation (14-day window).
Results are identical to what the API would compute on demand; nothing is precomputed by hand. Safe to re-run.

    .\\.venv\\Scripts\\python.exe -I scripts\\warm_cache.py [--base http://127.0.0.1:8000]
Without --base it runs the engine in-process; with --base it calls a running backend (so the server's own memory
caches are warm too).
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

SITES = ("im2-athena", "im2-intended", "im1-odysseus", "chandrayaan3-shiv-shakti")
DATES = ("2027-01-15T00:00:00Z", "2027-03-15T00:00:00Z")


def post(base: str, path: str, body: dict) -> dict:
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(), headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=1800) as r:
        return json.load(r)


def get(base: str, path: str) -> dict:
    with urllib.request.urlopen(base + path, timeout=1800) as r:
        return json.load(r)


def via_http(base: str) -> None:
    steps = [
        ("default view: horizon + series + positions (IM-2)", lambda: (
            get(base, "/horizon/profile?site_id=im2-athena"),
            post(base, "/visibility/series", {"site": {"site_id": "im2-athena"}, "start_utc": "2027-01-15T00:00:00Z",
                                              "end_utc": "2027-02-14T00:00:00Z", "step_seconds": 900}),
            get(base, "/visibility/at?site_id=im2-athena&time_utc=2027-01-20T12:00:00Z"),
            get(base, "/ephemeris/position?site_id=im2-athena&time_utc=2027-01-20T12:00:00Z"))),
        ("default comparison (4 sites x 2 dates, 30 d)", lambda: post(base, "/scenarios/compare", {
            "sites": [{"site_id": s} for s in SITES], "start_utc_list": list(DATES), "duration_days": 30})),
        ("default delay simulation (IM-2, 14 d window)", lambda: post(base, "/scenarios/delay", {
            "site": {"site_id": "im2-athena"}, "baseline_start_utc": "2027-01-15T00:00:00Z", "offsets_days": [1, 3, 7, 14]})),
        ("provenance + sources", lambda: (get(base, "/provenance"), get(base, "/dem/windows"), get(base, "/sites"))),
    ]
    for name, fn in steps:
        t0 = time.time()
        fn()
        print(f"  {name}: {time.time() - t0:5.1f} s", flush=True)


def in_process() -> None:
    from lunarnav.ephemeris import EphemerisService
    from lunarnav.horizon import HorizonService
    from lunarnav.scenarios import ScenarioService
    from lunarnav.visibility import VisibilityService

    hz = HorizonService(ROOT / "data")
    sv = ScenarioService(ROOT / "data", VisibilityService(EphemerisService(ROOT / "data"), hz))
    t0 = time.time()
    specs = [sv.make_spec({"site_id": s}, d, duration_days=30.0) for s in SITES for d in DATES]
    sv.compare(specs)
    print(f"  comparison: {time.time() - t0:5.1f} s", flush=True)
    t0 = time.time()
    sv.delay({"site_id": "im2-athena"}, "2027-01-15T00:00:00Z", [1, 3, 7, 14])
    print(f"  delay: {time.time() - t0:5.1f} s", flush=True)


if __name__ == "__main__":
    if "--base" in sys.argv:
        base = sys.argv[sys.argv.index("--base") + 1].rstrip("/")
        print(f"warming via {base}")
        via_http(base)
    else:
        print("warming in-process")
        in_process()
    print("done")
