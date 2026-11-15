"""Stage 5 endpoints: terrain-corrected Sun / Earth visibility with position-sensitivity bands.

Thin layer: parsing, site lookup, limits. All science is in `lunarnav.visibility`.
"""

from __future__ import annotations

import copy
import json
import math
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query
from lunarnav.ephemeris import EphemerisService, parse_utc
from lunarnav.errors import InvalidInputError
from lunarnav.horizon import DEFAULT_AZ_STEP_DEG, HorizonService
from lunarnav.sites import load_catalogue
from lunarnav.visibility import (
    DEFAULT_DIRECTIONS,
    DEFAULT_POSITION_BAND_M,
    VisibilityService,
)
from pydantic import BaseModel, Field

from .schemas import ErrorBody

_ERR = {422: {"model": ErrorBody}, 503: {"model": ErrorBody}, 500: {"model": ErrorBody}}
DEFAULT_OBSERVER_HEIGHT_M = 2.0  # decision C9: an assumption, reported as such
MAX_VIS_SAMPLES = 20_000


class VisSite(BaseModel):
    site_id: str | None = Field(None, description="Catalogue site id (see GET /sites)")
    lat: Any = Field(None, description="Planetocentric latitude, degrees (south negative)")
    lon: Any = Field(None, description="East-positive longitude, degrees")


class VisRequest(BaseModel):
    site: VisSite
    start_utc: str = Field(..., description="ISO-8601 UTC with Z")
    end_utc: str = Field(..., description="Window ends at the last sample at or before this time")
    step_seconds: float = Field(900.0, description="Sampling step; transitions are refined to 1 s by bisection")
    observer_height_m: float | None = Field(
        None, description=f"Above the DEM surface. Default {DEFAULT_OBSERVER_HEIGHT_M} m is an ASSUMPTION (C9).")
    bodies: list[str] = Field(default_factory=lambda: ["sun", "earth"], max_length=2)
    position_uncertainty_m: float | None = Field(
        DEFAULT_POSITION_BAND_M,
        description="Assumed observer-position uncertainty for the sensitivity band, metres (default 100). "
                    "0 or null disables it.")
    n_directions: int = Field(DEFAULT_DIRECTIONS, description="Displacement directions sampled on the circle")
    refine: bool = Field(True, description="Bisect transitions to 1 s (false = sample resolution)")
    include_series: bool = Field(True, description="Include per-step arrays")
    az_step_deg: float = Field(DEFAULT_AZ_STEP_DEG, description="Horizon azimuth step")


def build_visibility_router(data_dir: Path, horizon_service: HorizonService | None = None) -> APIRouter:
    router = APIRouter()
    service = VisibilityService(EphemerisService(data_dir), horizon_service or HorizonService(data_dir))
    catalogue = {s.id: s for s in load_catalogue(data_dir / "catalogue" / "sites.json")}

    def resolve(sel: VisSite) -> tuple[str | None, Any, Any]:
        if sel.site_id and (sel.lat is not None or sel.lon is not None):
            raise InvalidInputError("Give either site_id or lat/lon, not both", field="site")
        if sel.site_id:
            site = catalogue.get(sel.site_id)
            if site is None:
                raise InvalidInputError(f"Unknown site_id '{sel.site_id}'", field="site_id",
                                        details={"known": sorted(catalogue)})
            return site.id, site.lat_deg, site.lon_deg_east
        if sel.lat is None or sel.lon is None:
            raise InvalidInputError("Give a site_id, or both lat and lon", field="site")
        return None, sel.lat, sel.lon

    # Identical requests give identical results (the engine is deterministic), so repeat loads are served from a small
    # in-memory cache. Entries are deep-copied in and out: routes edit their copy (e.g. /visibility/at drops fields).
    cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
    cache_lock = threading.Lock()

    def run(req: VisRequest, include_series: bool) -> dict[str, Any]:
        key = json.dumps([req.model_dump(), include_series], sort_keys=True, default=str)
        with cache_lock:
            hit = cache.get(key)
            if hit is not None:
                cache.move_to_end(key)
                return copy.deepcopy(hit)
        res = compute(req, include_series)
        with cache_lock:
            cache[key] = copy.deepcopy(res)
            while len(cache) > 24:
                cache.popitem(last=False)
        return res

    def compute(req: VisRequest, include_series: bool) -> dict[str, Any]:
        site_id, lat, lon = resolve(req.site)
        start, end = parse_utc(req.start_utc, "start_utc"), parse_utc(req.end_utc, "end_utc")
        step = req.step_seconds
        if not math.isfinite(step) or step < 1.0:
            raise InvalidInputError("step_seconds must be a finite number >= 1", field="step_seconds")
        span = (end - start).total_seconds()
        if span < 0:
            raise InvalidInputError("end_utc must not be before start_utc", field="end_utc")
        n = math.floor(span / step + 1e-9) + 1
        if n > MAX_VIS_SAMPLES:
            raise InvalidInputError(f"Request would produce {n} samples; the limit is {MAX_VIS_SAMPLES}",
                                    field="step_seconds", details={"requested_samples": n})
        is_default = req.observer_height_m is None
        height = DEFAULT_OBSERVER_HEIGHT_M if is_default else req.observer_height_m
        res = service.evaluate(
            lat, lon, start, step, n, height, tuple(req.bodies),
            position_uncertainty_m=req.position_uncertainty_m, n_directions=req.n_directions,
            refine=req.refine, include_series=include_series,
            horizon_kwargs={"az_step_deg": req.az_step_deg}).to_dict()
        res["observer"]["site_id"] = site_id
        res["observer"]["observer_height_is_default_assumption"] = is_default
        return res

    @router.post("/visibility/series", response_model=dict[str, Any], responses=_ERR, tags=["visibility"])
    def visibility_series(req: VisRequest) -> dict[str, Any]:
        """Per-step states (centre / any-part / fully), geometric vs terrain-corrected, completeness flags and
        position sensitivity, plus transitions, intervals and metrics."""
        return run(req, req.include_series)

    @router.post("/visibility/intervals", response_model=dict[str, Any], responses=_ERR, tags=["visibility"])
    def visibility_intervals(req: VisRequest) -> dict[str, Any]:
        """Intervals, transitions and metrics only (no per-step arrays). `bodies: ["sun"]` is the solar
        visibility API; `["earth"]` the Earth visibility API."""
        return run(req, False)

    @router.get("/visibility/at", response_model=dict[str, Any], responses=_ERR, tags=["visibility"])
    def visibility_at(
        time_utc: str = Query(..., description="ISO-8601 UTC with Z"),
        site_id: str | None = Query(None), lat: float | None = Query(None), lon: float | None = Query(None),
        observer_height_m: float | None = Query(None, description="default 2.0 m is an assumption (C9)"),
        position_uncertainty_m: float = Query(DEFAULT_POSITION_BAND_M),
        az_step_deg: float = Query(DEFAULT_AZ_STEP_DEG),
    ) -> dict[str, Any]:
        req = VisRequest(site=VisSite(site_id=site_id, lat=lat, lon=lon), start_utc=time_utc, end_utc=time_utc,
                         observer_height_m=observer_height_m, position_uncertainty_m=position_uncertainty_m,
                         refine=False, az_step_deg=az_step_deg)
        res = run(req, True)
        for b in res["bodies"].values():  # one instant: intervals are meaningless
            for k in ("states", "headline"):
                b.pop(k, None)
        return res

    return router
