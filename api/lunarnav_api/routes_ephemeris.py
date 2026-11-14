"""Stage 3 endpoints: Sun and Earth az/el/range/angular diameter for a lunar surface observer.

Thin layer: parameter parsing, site lookup, error mapping. All science is in `lunarnav.ephemeris`.
No terrain is applied here; these are *geometric* directions only (terrain arrives in Stages 4-5).
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query
from lunarnav.ephemeris import (
    BODIES,
    MAX_SAMPLES,
    EphemerisResult,
    EphemerisService,
    parse_utc,
)
from lunarnav.errors import InvalidInputError
from lunarnav.sites import load_catalogue
from pydantic import BaseModel, Field

from .schemas import ErrorBody

_ERR = {422: {"model": ErrorBody}, 503: {"model": ErrorBody}, 500: {"model": ErrorBody}}

NOTES = [
    "Geometric directions of the body centre only; terrain is not applied (Stage 4/5).",
    ("Azimuth: degrees clockwise from local north. Elevation: degrees above the local horizontal "
     "plane (perpendicular to the local radial). Airless: no refraction."),
    "Angular diameter uses nominal radii (see provenance.bodies); it is not a visibility claim.",
]


class SiteSelector(BaseModel):
    """Either a catalogue `site_id`, or custom `lat` + `lon`. Typed loosely; the engine validates."""

    site_id: str | None = Field(None, description="Catalogue site id (see GET /sites)")
    lat: Any = Field(None, description="Planetocentric latitude, degrees (south negative)")
    lon: Any = Field(None, description="East-positive longitude, degrees [-180, 360]")
    height_m: Any = Field(
        0.0, description="Observer height above the 1737.4 km reference sphere, metres (assumed 0 "
                         "unless given; DEM-derived height arrives in Stage 5)")


class SeriesRequest(BaseModel):
    site: SiteSelector
    start_utc: str = Field(..., description="ISO-8601 UTC with Z, e.g. 2027-01-15T00:00:00Z")
    end_utc: str = Field(..., description="Inclusive end if aligned to the step")
    step_seconds: float = Field(900.0, description="Sampling step, seconds (1..2592000)")
    bodies: list[str] = Field(default_factory=lambda: ["sun", "earth"])


class ObserverOut(BaseModel):
    site_id: str | None
    lat_deg: float
    lon_deg_east: float
    height_m: float
    lat_convention: str = "planetocentric"
    lon_convention: str = "east_positive"
    frame: str = "MOON_ME"


class BodySeriesOut(BaseModel):
    azimuth_deg: list[float]
    elevation_deg: list[float]
    range_km: list[float]
    angular_diameter_deg: list[float]
    light_time_s: list[float]


class SeriesResponse(BaseModel):
    data_class: str
    observer: ObserverOut
    n_samples: int
    times_utc: list[str]
    bodies: dict[str, BodySeriesOut]
    units: dict[str, str]
    notes: list[str]
    provenance: dict[str, Any]


UNITS = {
    "azimuth_deg": "degrees clockwise from local north, 0..360",
    "elevation_deg": "degrees above the local horizontal plane, -90..90",
    "range_km": "kilometres, observer to body centre (light-time corrected)",
    "angular_diameter_deg": "degrees (nominal radius)",
    "light_time_s": "seconds",
}


def _to_response(res: EphemerisResult, site_id: str | None) -> SeriesResponse:
    return SeriesResponse(
        data_class=res.data_class,
        observer=ObserverOut(site_id=site_id, lat_deg=res.observer.lat_deg,
                             lon_deg_east=res.observer.lon_deg_east,
                             height_m=res.observer.height_m),
        n_samples=len(res.times_utc),
        times_utc=res.times_utc,
        bodies={k: BodySeriesOut(**vars(v)) for k, v in res.bodies.items()},
        units=UNITS,
        notes=NOTES,
        provenance=res.provenance,
    )


def build_ephemeris_router(data_dir: Path) -> APIRouter:
    router = APIRouter()
    service = EphemerisService(data_dir)
    catalogue = {s.id: s for s in load_catalogue(data_dir / "catalogue" / "sites.json")}

    def resolve(sel: SiteSelector) -> tuple[str | None, Any, Any, Any]:
        have_coords = sel.lat is not None or sel.lon is not None
        if sel.site_id and have_coords:
            raise InvalidInputError("Give either site_id or lat/lon, not both", field="site")
        if sel.site_id:
            site = catalogue.get(sel.site_id)
            if site is None:
                raise InvalidInputError(f"Unknown site_id '{sel.site_id}'", field="site_id",
                                        details={"known": sorted(catalogue)})
            return site.id, site.lat_deg, site.lon_deg_east, sel.height_m
        if sel.lat is None or sel.lon is None:
            raise InvalidInputError("Give a site_id, or both lat and lon", field="site")
        return None, sel.lat, sel.lon, sel.height_m

    def check_bodies(names: list[str]) -> tuple[str, ...]:
        if not names or len(set(names)) != len(names) or any(n not in BODIES for n in names):
            raise InvalidInputError(f"bodies must be unique values from {sorted(BODIES)}",
                                    field="bodies")
        return tuple(names)

    @router.post("/ephemeris/series", response_model=SeriesResponse, responses=_ERR,
                 tags=["ephemeris"])
    def ephemeris_series(req: SeriesRequest) -> SeriesResponse:
        site_id, lat, lon, height = resolve(req.site)
        start = parse_utc(req.start_utc, "start_utc")
        end = parse_utc(req.end_utc, "end_utc")
        step = req.step_seconds
        if not isinstance(step, float) or not math.isfinite(step) or step < 1.0:
            raise InvalidInputError("step_seconds must be a finite number >= 1",
                                    field="step_seconds")
        span = (end - start).total_seconds()
        if span < 0:
            raise InvalidInputError("end_utc must not be before start_utc", field="end_utc")
        n = math.floor(span / step + 1e-9) + 1
        if n > MAX_SAMPLES:
            raise InvalidInputError(
                f"Request would produce {n} samples; the limit is {MAX_SAMPLES}. "
                "Increase step_seconds or shorten the span.", field="step_seconds",
                details={"requested_samples": n, "max_samples": MAX_SAMPLES})
        res = service.series(lat, lon, start, step, n, check_bodies(req.bodies), height)
        return _to_response(res, site_id)

    @router.get("/ephemeris/position", response_model=SeriesResponse, responses=_ERR,
                tags=["ephemeris"])
    def ephemeris_position(
        time_utc: str = Query(..., description="ISO-8601 UTC with Z"),
        site_id: str | None = Query(None, description="Catalogue site id"),
        lat: float | None = Query(None, description="Latitude, degrees (planetocentric)"),
        lon: float | None = Query(None, description="East-positive longitude, degrees"),
        height_m: float = Query(0.0, description="Observer height above the reference sphere, m"),
        body: str = Query("both", description="sun | earth | both"),
    ) -> SeriesResponse:
        if body not in ("sun", "earth", "both"):
            raise InvalidInputError("body must be sun, earth or both", field="body")
        sid, la, lo, h = resolve(SiteSelector(site_id=site_id, lat=lat, lon=lon, height_m=height_m))
        bodies = ("sun", "earth") if body == "both" else (body,)
        res = service.at(la, lo, parse_utc(time_utc), bodies, h)
        return _to_response(res, sid)

    return router
