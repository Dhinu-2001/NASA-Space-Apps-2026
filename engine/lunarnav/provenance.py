"""Data provenance and reproducible-calculation metadata (Stage 9, tasks 12 and 13).

Two products:
  * `build_provenance(...)`  - the full, static record of what the application is built from (software, SPICE
    kernels with checksums, DEM windows with checksums, site catalogue, validation fixtures, git commit). Served by
    GET /provenance and rendered into docs/stage9/PROVENANCE.md by scripts/build_provenance_report.py.
  * `calculation_metadata(...)` - the compact, DETERMINISTIC block stamped into every visibility and scenario
    result: given the same inputs and the same data it is identical, so a result can be traced to, and reproduced
    from, exactly these kernels, DEM windows, code version and parameters. It contains no timestamps.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
from importlib import metadata
from pathlib import Path
from typing import Any

import numpy as np

from . import MODEL_VERSION
from .dem import DemRegistry


def _sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def software_versions() -> dict[str, str]:
    out = {"python": platform.python_version(), "numpy": np.__version__, "platform": platform.system()}
    for pkg in ("spiceypy", "rasterio", "pyproj"):  # engine dependencies only; the API adds its own
        try:
            out[pkg] = metadata.version(pkg)
        except metadata.PackageNotFoundError:
            pass  # optional / dev-only package not installed
    return out


def git_commit(root: Path | None = None) -> str | None:
    """Commit of the running code: LUNARNAV_GIT_COMMIT if set (deployments), else `git rev-parse`, else None."""
    env = os.environ.get("LUNARNAV_GIT_COMMIT")
    if env:
        return env
    try:
        r = subprocess.run(["git", "rev-parse", "--short=12", "HEAD"], cwd=root, capture_output=True, text=True,
                           timeout=5, check=False)
        return r.stdout.strip() or None if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def dem_windows(registry: DemRegistry) -> list[dict[str, Any]]:
    return [{"window_id": m.window_id, "product_id": m.product_id, "pixel_size_m": m.pixel_size_m,
             "width": m.width, "height": m.height, "overview_level": m.overview_level, "sha256": m.sha256,
             "source_url": m.source_url, "z_min_m": m.z_min_m, "z_max_m": m.z_max_m,
             "valid_fraction": m.valid_fraction} for m in sorted(registry.windows.values(), key=lambda w: w.window_id)]


def calculation_metadata(eph_provenance: dict[str, Any], horizon_meta: dict[str, Any],
                         parameters: dict[str, Any]) -> dict[str, Any]:
    """Deterministic metadata for one calculation (no timestamps, no host details)."""
    return {
        "model_version": MODEL_VERSION,
        "ephemeris": {
            "engine": eph_provenance.get("engine"),
            "spiceypy_version": eph_provenance.get("spiceypy_version"),
            "cspice_toolkit": eph_provenance.get("cspice_toolkit"),
            "frame": eph_provenance.get("frame"),
            "aberration_correction": eph_provenance.get("aberration_correction"),
            "kernels": [{"file": k["file"], "sha256": k["sha256"]} for k in eph_provenance.get("kernels", [])],
            "validated_range": eph_provenance.get("validated_range"),
        },
        "terrain": {
            "horizon_algorithm_version": horizon_meta.get("algorithm_version"),
            "dem_windows": [{"window_id": w["window_id"], "pixel_size_m": w["pixel_size_m"], "sha256": w["sha256"]}
                            for w in horizon_meta.get("windows", [])],
            "reference_radius_m": horizon_meta.get("parameters", {}).get("reference_radius_m"),
            "unseen_terrain_max_height_m": horizon_meta.get("parameters", {}).get("unseen_terrain_max_height_m"),
        },
        "parameters": parameters,
        "reproducibility": "deterministic: the same inputs and the same kernels/DEM windows give identical results",
    }


def build_provenance(data_dir: Path, eph_provenance: dict[str, Any] | None, repo_root: Path | None = None
                     ) -> dict[str, Any]:
    data_dir = Path(data_dir)
    registry = DemRegistry(data_dir)
    cat_path = data_dir / "catalogue" / "sites.json"
    catalogue: dict[str, Any] = {}
    if cat_path.exists():
        doc = json.loads(cat_path.read_text(encoding="utf-8"))
        catalogue = {
            "catalogue_version": doc.get("catalogue_version"),
            "sha256": _sha256(cat_path),
            "sites": [{"id": s["id"], "name": s["name"], "kind": s["kind"],
                       "sources": [{"label": x["label"], "url": x["url"]} for x in s.get("sources", [])]}
                      for s in doc.get("sites", [])],
        }
    fixture = data_dir / "validation" / "horizons_stage3_reference.json"
    return {
        "model_version": MODEL_VERSION,
        "git_commit": git_commit(repo_root),
        "software": software_versions(),
        "spice_kernels": (eph_provenance or {}).get("kernels"),
        "spice_frame": (eph_provenance or {}).get("frame"),
        "dem_windows": dem_windows(registry),
        "site_catalogue": catalogue,
        "validation_fixtures": {
            "horizons_stage3_reference": {"file": "data/validation/horizons_stage3_reference.json",
                                          "sha256": _sha256(fixture),
                                          "note": "JPL Horizons API v1.2 results recorded once; used as an offline oracle"},
        },
        "constants": {
            "moon_reference_radius_m": 1_737_400.0,
            "sun_radius_km": 695_700.0,
            "earth_equatorial_radius_km": 6378.1,
            "note": "IAU 2015 nominal values; assumptions, not measurements",
        },
        "data_classes": {
            "measured_interpolated": "LOLA altimetry gridded/interpolated (DEM heights)",
            "calculated": "derived by the engine from measured inputs and stated assumptions",
            "assumption": "a labelled input chosen by the project (observer height, position uncertainty, windows)",
        },
    }
