"""Stage 2 endpoints: site catalogue, coordinate validation, DEM windows and elevation lookup.

No astronomical or horizon calculations live here (those are later stages).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query, Request
from lunarnav.dem import DemRegistry
from lunarnav.sites import (
    BODY,
    LAT_CONVENTION,
    LON_CONVENTION,
    REFERENCE_RADIUS_M,
    custom_site,
    load_catalogue,
)
from pydantic import BaseModel

from .schemas import ErrorBody

_ERR = {422: {"model": ErrorBody}, 503: {"model": ErrorBody}, 500: {"model": ErrorBody}}


class SourceOut(BaseModel):
    label: str
    url: str
    description: str
    quote: str


class SiteOut(BaseModel):
    id: str
    name: str
    kind: str
    lat_deg: float
    lon_deg_east: float
    lat_convention: str
    lon_convention: str
    reference_height_m: float | None = None
    reference_height_source: str | None = None
    notes: str
    sources: list[SourceOut]


class PendingRegionOut(BaseModel):
    name: str
    status: str
    reason: str
    reference_url: str | None = None


class SitesResponse(BaseModel):
    catalogue_version: str
    body: str
    lat_convention: str
    lon_convention: str
    reference_sphere_radius_m: float
    policy: str
    sites: list[SiteOut]
    pending_regions: list[PendingRegionOut]


class CoordinateInput(BaseModel):
    # Typed loosely on purpose: the engine validator rejects strings/bools/NaN with a field name.
    lat: Any
    lon: Any


class WindowRef(BaseModel):
    window_id: str
    product_id: str
    pixel_size_m: float


class ValidateResponse(BaseModel):
    site: SiteOut
    dem_coverage_status: str  # "covered" | "not_covered"
    covering_windows: list[WindowRef]
    note: str


class WindowOut(BaseModel):
    window_id: str
    product_id: str
    file: str
    sha256: str
    pixel_size_m: float
    width: int
    height: int
    left_m: float
    top_m: float
    right_m: float
    bottom_m: float
    valid_fraction: float
    z_min_m: float
    z_max_m: float
    overview_level: int | None
    source_url: str
    units: str
    nodata: str


class ElevationResponse(BaseModel):
    elevation_m: float
    lat_deg: float
    lon_deg_east: float
    x_m: float
    y_m: float
    window_id: str
    product_id: str
    pixel_size_m: float
    method: str
    source_url: str
    sha256: str
    data_class: str
    units: str = "metres above the 1737.4 km lunar reference sphere"


def build_router(data_dir: Path) -> APIRouter:
    router = APIRouter()
    catalogue_path = data_dir / "catalogue" / "sites.json"
    sites = load_catalogue(catalogue_path)  # fail fast on any catalogue policy violation
    catalogue_doc = json.loads(catalogue_path.read_text(encoding="utf-8"))
    registry = DemRegistry(data_dir)

    @router.get("/sites", response_model=SitesResponse, responses=_ERR, tags=["sites"])
    def list_sites() -> SitesResponse:
        return SitesResponse(
            catalogue_version=catalogue_doc["catalogue_version"],
            body=BODY,
            lat_convention=LAT_CONVENTION,
            lon_convention=LON_CONVENTION,
            reference_sphere_radius_m=REFERENCE_RADIUS_M,
            policy=catalogue_doc["policy"],
            sites=[SiteOut(**s.to_dict()) for s in sites],
            pending_regions=[PendingRegionOut(**p) for p in catalogue_doc.get("pending_regions", [])],
        )

    @router.post("/sites/validate", response_model=ValidateResponse, responses=_ERR, tags=["sites"])
    def validate_site(body: CoordinateInput) -> ValidateResponse:
        site = custom_site(body.lat, body.lon)
        covering = registry.covering(site.lat_deg, site.lon_deg_east)
        return ValidateResponse(
            site=SiteOut(**site.to_dict()),
            dem_coverage_status="covered" if covering else "not_covered",
            covering_windows=[
                WindowRef(window_id=m.window_id, product_id=m.product_id, pixel_size_m=m.pixel_size_m)
                for m in covering
            ],
            note=(
                "Coordinates are valid. Coverage refers only to the locally extracted DEM windows; "
                "'not_covered' means terrain-dependent results are unavailable here, "
                "not that the location is invalid."
            ),
        )

    @router.get("/dem/windows", response_model=list[WindowOut], responses=_ERR, tags=["dem"])
    def list_windows() -> list[WindowOut]:
        return [
            WindowOut(
                window_id=m.window_id, product_id=m.product_id, file=m.file, sha256=m.sha256,
                pixel_size_m=m.pixel_size_m, width=m.width, height=m.height, left_m=m.left_m,
                top_m=m.top_m, right_m=m.right_m, bottom_m=m.bottom_m,
                valid_fraction=m.valid_fraction, z_min_m=m.z_min_m, z_max_m=m.z_max_m,
                overview_level=m.overview_level, source_url=m.source_url,
                units=m.raw.get("units", ""), nodata=m.raw.get("nodata", ""),
            )
            for m in sorted(registry.windows.values(), key=lambda w: w.window_id)
        ]

    @router.get("/dem/elevation", response_model=ElevationResponse, responses=_ERR, tags=["dem"])
    def dem_elevation(
        request: Request,
        lat: float = Query(..., description="Planetocentric latitude, degrees (south negative)"),
        lon: float = Query(..., description="East-positive longitude, degrees, [-180, 360]"),
        window_id: str | None = Query(None, description="Force a specific DEM window"),
    ) -> ElevationResponse:
        return ElevationResponse(**registry.elevation(lat, lon, window_id).to_dict())

    return router
