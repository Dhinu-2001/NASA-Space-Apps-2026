"""Stage 4 endpoint: terrain horizon profile for a lunar surface observer.

Thin layer: parameter parsing, site lookup, JSON-safe serialisation. All science is in `lunarnav.horizon`.
The profile is *terrain only*: it says nothing about where the Sun or Earth is (Stage 5 combines them).
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import APIRouter, Query
from lunarnav.errors import InvalidInputError
from lunarnav.horizon import DEFAULT_AZ_STEP_DEG, HorizonProfile, HorizonService
from lunarnav.sites import load_catalogue
from pydantic import BaseModel

from .schemas import ErrorBody

DEFAULT_OBSERVER_HEIGHT_M = 2.0  # decision C9: an assumption, user-editable, always reported as such
_ERR = {422: {"model": ErrorBody}, 503: {"model": ErrorBody}, 500: {"model": ErrorBody}}

UNITS = {
    "azimuth_deg": "degrees clockwise from local north, [0, 360)",
    "horizon_elevation_deg": "degrees above the local horizontal plane; null where no valid DEM sample exists",
    "horizon_distance_km": "great-circle distance from the observer to the terrain sample that sets the horizon",
    "limiting_pixel_size_m": "pixel size of the DEM window that supplied that sample",
    "range_covered_km": "distance along the ray over which DEM data exist",
    "n_missing_samples": "count of NoData samples skipped along the ray",
    "unseen_bound_deg": "highest elevation terrain beyond the DEM edge could have, given the stated height ceiling",
    "truncated": "true if terrain beyond the DEM coverage could still raise the horizon (value is a lower bound)",
    "data_gap": "true if NoData was met on the ray (value is a lower bound)",
}

NOTES = [
    ("Terrain horizon only: the highest elevation angle of DEM terrain along each azimuth, with lunar "
    "curvature (exact sphere, R = 1737.4 km). It is NOT a visibility result; Sun/Earth are not involved."),
    ("Observer height is above the DEM surface at the site (default 2.0 m is an ASSUMPTION, decision C9; "
    "see observer.observer_height_is_default_assumption). The ground height comes from the DEM, not the catalogue."),
    ("Rays are point samples at the stated azimuth step. A feature narrower than the step at long range can "
    "fall between rays; see docs/stage4/RESOLUTION.md."),
    ("`truncated` / `data_gap` azimuths have a horizon that is a LOWER BOUND. They are never filled with "
    "flat or synthetic terrain."),
    ("DEM pixels between LOLA ground tracks are interpolated (PGDA); overview windows are area-averaged and "
    "understate narrow obstructions."),
]


class ObserverOut(BaseModel):
    site_id: str | None
    lat_deg: float
    lon_deg_east: float
    ground_height_m: float
    observer_height_above_surface_m: float
    observer_radius_height_m: float
    observer_height_is_default_assumption: bool
    catalogue_reference_height_m: float | None = None
    lat_convention: str = "planetocentric"
    lon_convention: str = "east_positive"
    frame: str = "MOON_ME"


class HorizonResponse(BaseModel):
    data_class: str
    observer: ObserverOut
    n_azimuths: int
    azimuth_deg: list[float]
    horizon_elevation_deg: list[float | None]
    horizon_distance_km: list[float | None]
    limiting_pixel_size_m: list[float | None]
    range_covered_km: list[float]
    n_missing_samples: list[int]
    unseen_bound_deg: list[float]
    truncated: list[bool]
    data_gap: list[bool]
    summary: dict[str, Any]
    units: dict[str, str]
    notes: list[str]
    provenance: dict[str, Any]
    served_from: str


def _clean(a: np.ndarray, ndigits: int = 6) -> list[float | None]:
    """JSON cannot carry NaN: missing values become null (never 0)."""
    return [None if not math.isfinite(v) else round(float(v), ndigits) for v in a]


def to_response(p: HorizonProfile, site_id: str | None, ref_height_m: float | None,
                is_default_height: bool) -> HorizonResponse:
    o = p.meta["observer"]
    return HorizonResponse(
        data_class="calculated_from_measured_interpolated",
        observer=ObserverOut(
            site_id=site_id, lat_deg=o["lat_deg"], lon_deg_east=o["lon_deg_east"],
            ground_height_m=o["ground_height_m"],
            observer_height_above_surface_m=o["observer_height_above_surface_m"],
            observer_radius_height_m=o["observer_radius_height_m"],
            observer_height_is_default_assumption=is_default_height,
            catalogue_reference_height_m=ref_height_m),
        n_azimuths=p.n_azimuths,
        azimuth_deg=[float(v) for v in p.azimuth_deg],
        horizon_elevation_deg=_clean(p.horizon_elevation_deg),
        horizon_distance_km=_clean(p.horizon_distance_km, 3),
        limiting_pixel_size_m=_clean(p.limiting_pixel_size_m, 3),
        range_covered_km=[float(v) for v in np.round(p.range_covered_km, 3)],
        n_missing_samples=[int(v) for v in p.n_missing_samples],
        unseen_bound_deg=[float(v) for v in np.round(p.unseen_bound_deg, 6)],
        truncated=[bool(v) for v in p.truncated],
        data_gap=[bool(v) for v in p.data_gap],
        summary=p.summary(), units=UNITS, notes=NOTES,
        provenance={**p.meta, "model": "great-circle ray sampling on the 1737.4 km sphere, bilinear DEM"},
        served_from=p.served_from,
    )


def build_horizon_router(data_dir: Path, service: HorizonService | None = None) -> APIRouter:
    router = APIRouter()
    service = service or HorizonService(data_dir)
    catalogue = {s.id: s for s in load_catalogue(data_dir / "catalogue" / "sites.json")}

    @router.get("/horizon/profile", response_model=HorizonResponse, responses=_ERR, tags=["horizon"])
    def horizon_profile(
        site_id: str | None = Query(None, description="Catalogue site id (see GET /sites)"),
        lat: float | None = Query(None, description="Planetocentric latitude, degrees (south negative)"),
        lon: float | None = Query(None, description="East-positive longitude, degrees"),
        observer_height_m: float | None = Query(
            None, description=f"Observer height above the DEM surface, metres. If omitted the default "
                              f"assumption {DEFAULT_OBSERVER_HEIGHT_M} m (decision C9) is used and reported as such."),
        az_step_deg: float = Query(DEFAULT_AZ_STEP_DEG, description="Azimuth step; must divide 360"),
        step_m: float | None = Query(None, description="Radial sampling step, m (default: finest pixel size)"),
        max_range_km: float | None = Query(None, description="Cap on ray length (default: DEM coverage)"),
        use_cache: bool = Query(True, description="Serve/store the cached profile"),
    ) -> HorizonResponse:
        if site_id and (lat is not None or lon is not None):
            raise InvalidInputError("Give either site_id or lat/lon, not both", field="site")
        ref_h: float | None = None
        if site_id:
            site = catalogue.get(site_id)
            if site is None:
                raise InvalidInputError(f"Unknown site_id '{site_id}'", field="site_id",
                                        details={"known": sorted(catalogue)})
            la, lo = site.lat_deg, site.lon_deg_east
            ref_h = getattr(site, "reference_height_m", None)
        else:
            if lat is None or lon is None:
                raise InvalidInputError("Give a site_id, or both lat and lon", field="site")
            la, lo = lat, lon
        is_default = observer_height_m is None
        height = DEFAULT_OBSERVER_HEIGHT_M if is_default else observer_height_m
        prof = service.profile(la, lo, height, az_step_deg=az_step_deg, step_m=step_m,
                               max_range_km=max_range_km, use_cache=use_cache)
        return to_response(prof, site_id, ref_h, is_default)

    return router
