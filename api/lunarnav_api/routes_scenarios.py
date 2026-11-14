"""Stage 6 endpoints: scenario evaluation, multi-site / multi-date comparison, mission delay simulator.

Thin layer over `lunarnav.scenarios`. Sites without supporting terrain data come back as
`terrain_data_insufficient` (reason, no numbers) and are never ranked or scored.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter
from lunarnav.errors import InvalidInputError, NotFoundError
from lunarnav.scenarios import ScenarioService, ScenarioSpec
from lunarnav.visibility import DEFAULT_DIRECTIONS, DEFAULT_POSITION_BAND_M, VisibilityService
from pydantic import BaseModel, Field

from .schemas import ErrorBody

_ERR = {422: {"model": ErrorBody}, 404: {"model": ErrorBody}, 503: {"model": ErrorBody}, 500: {"model": ErrorBody}}


class SiteIn(BaseModel):
    site_id: str | None = Field(None, description="Catalogue site id (see GET /sites)")
    lat: Any = Field(None, description="Planetocentric latitude, degrees (south negative)")
    lon: Any = Field(None, description="East-positive longitude, degrees")


class ScenarioParams(BaseModel):
    duration_days: float = Field(30.0, description="Window length, days (0, 60]")
    step_seconds: float = Field(900.0, description="Sampling step; transitions are refined to 1 s")
    observer_height_m: float | None = Field(
        None, description="Above the DEM surface. Omitted => 2.0 m default ASSUMPTION (C9), reported as such.")
    position_uncertainty_m: float = Field(
        DEFAULT_POSITION_BAND_M, description="Assumed observer-position uncertainty, metres, > 0. Every scenario "
        "result carries the position sensitivity.")
    n_directions: int = Field(DEFAULT_DIRECTIONS, description="Displacement directions sampled")
    az_step_deg: float = Field(0.25, description="Horizon azimuth step")
    use_cache: bool = Field(True, description="Serve/store results from the on-disk scenario cache")


class ScenarioRequest(ScenarioParams):
    site: SiteIn
    start_utc: str = Field(..., description="ISO-8601 UTC with Z; start of the window")
    label: str | None = None


class CompareRequest(ScenarioParams):
    scenarios: list[ScenarioRequest] | None = Field(
        None, description="Explicit scenario list (each may override the common parameters), or use sites x dates")
    sites: list[SiteIn] | None = Field(None, description="With start_utc_list: every site x every date")
    start_utc_list: list[str] | None = None
    baseline_index: int = Field(0, description="Scenario that deltas are measured from")


class DelayRequest(ScenarioParams):
    duration_days: float = Field(
        14.0, description="Window length, days. Default 14 d is an ASSUMPTION (about one lunar day of surface "
        "operations), not a mission requirement. A window that spans a whole synodic month (29.5 d) hides short "
        "delays: totals repeat, so only event times move.")
    site: SiteIn
    baseline_start_utc: str
    offsets_days: list[float] = Field(..., description="Launch/landing delays to simulate, days (0, 365], up to 10")


def build_scenario_router(data_dir: Path, visibility: VisibilityService) -> APIRouter:
    router = APIRouter()
    service = ScenarioService(data_dir, visibility)

    def common(p: ScenarioParams) -> dict[str, Any]:
        return {"duration_days": p.duration_days, "step_seconds": p.step_seconds,
                "observer_height_m": p.observer_height_m, "position_uncertainty_m": p.position_uncertainty_m,
                "n_directions": p.n_directions, "az_step_deg": p.az_step_deg}

    def spec_of(r: ScenarioRequest, label: str | None = None) -> ScenarioSpec:
        return service.make_spec(r.site.model_dump(), r.start_utc, label=label or r.label, **common(r))

    @router.post("/scenarios/evaluate", response_model=dict[str, Any], responses=_ERR, tags=["scenarios"])
    def evaluate(req: ScenarioRequest) -> dict[str, Any]:
        """One scenario. Returns `status: supported` with geometric and terrain-corrected results and position
        bands, or `status: terrain_data_insufficient` with the reason and no numbers. The id identifies the
        scenario (inputs + model + DEM); GET /scenarios/{id} returns it again."""
        return service.evaluate(spec_of(req), req.use_cache)

    @router.get("/scenarios/{scenario_id}", response_model=dict[str, Any], responses=_ERR, tags=["scenarios"])
    def get_saved(scenario_id: str) -> dict[str, Any]:
        hit = service.store.load(scenario_id)
        if hit is None:
            raise NotFoundError(f"No saved scenario with id {scenario_id!r} for this model version and DEM.",
                                field="scenario_id")
        return {**hit, "served_from": "disk"}

    @router.post("/scenarios/compare", response_model=dict[str, Any], responses=_ERR, tags=["scenarios"])
    def compare(req: CompareRequest) -> dict[str, Any]:
        """Compare several sites and/or dates. Supported scenarios get deltas and rankings (with position
        bands); `terrain_data_insufficient` sites are listed separately and never ranked or scored."""
        if req.scenarios and (req.sites or req.start_utc_list):
            raise InvalidInputError("Give either `scenarios` or `sites` + `start_utc_list`, not both",
                                    field="scenarios")
        if req.scenarios:
            specs = [spec_of(s) for s in req.scenarios]
        elif req.sites and req.start_utc_list:
            c = common(req)
            specs = []
            for st in req.sites:
                for d in req.start_utc_list:
                    name = st.site_id or f"{st.lat},{st.lon}"
                    specs.append(service.make_spec(st.model_dump(), d, label=f"{name} @ {d}", **c))
        else:
            raise InvalidInputError("Give `scenarios`, or both `sites` and `start_utc_list`", field="scenarios")
        return service.compare(specs, req.baseline_index, req.use_cache)

    @router.post("/scenarios/delay", response_model=dict[str, Any], responses=_ERR, tags=["scenarios"])
    def delay(req: DelayRequest) -> dict[str, Any]:
        """Mission delay simulator: baseline window vs the same window shifted by each offset, with the position
        band carried into every delta (paired per displacement)."""
        return service.delay(req.site.model_dump(), req.baseline_start_utc, req.offsets_days,
                             use_cache=req.use_cache, **common(req))

    return router
