"""Stage 8 endpoint: idealised direct-beam solar energy availability (deliberately narrow).

Thin layer: it asks the Stage 6 scenario service for the (cached) scenario and multiplies its visible times by the panel
factor in `lunarnav.engineering`. No astronomy, terrain or visibility is recomputed here.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from lunarnav.engineering import (
    IRRADIANCE_RANGE_W_M2,
    SOLAR_CONSTANT_W_M2,
    solar_energy,
    validate_panel,
)
from lunarnav.scenarios import SUPPORTED, ScenarioService
from pydantic import Field

from .routes_scenarios import _ERR, ScenarioRequest, spec_factory


class SolarRequest(ScenarioRequest):
    area_m2: Any = Field(..., description="Panel area, m^2, in (0, 10000]. Required: there is no hidden default panel.")
    efficiency: Any = Field(..., description="Electrical conversion efficiency as a fraction in (0, 1], e.g. 0.30. Required.")
    irradiance_w_m2: Any = Field(
        None, description=f"Irradiance while illuminated, W/m^2 in {list(IRRADIANCE_RANGE_W_M2)}. Default {SOLAR_CONSTANT_W_M2:g} "
                          "(nominal solar constant at 1 AU) is an ASSUMPTION and is reported as such.")


def build_engineering_router(service: ScenarioService) -> APIRouter:
    router = APIRouter()
    make_spec = spec_factory(service)

    @router.post("/engineering/solar", response_model=dict[str, Any], responses=_ERR, tags=["engineering"])
    def solar(req: SolarRequest) -> dict[str, Any]:
        """Idealised direct-beam solar ENERGY availability for a site and window: an upper bound (sun-tracking panel,
        any part of the Sun's disc counts as full illumination), with the position-sensitivity band carried from the
        visibility result, the geometric (no-terrain) counterpart, the terrain penalty and the longest period without
        sunlight. Sites without supporting terrain data return `terrain_data_insufficient` and no figures."""
        validate_panel(req.area_m2, req.efficiency, req.irradiance_w_m2)          # typed errors before any computation
        scenario = service.evaluate(make_spec(req), req.use_cache)
        if scenario["status"] != SUPPORTED:
            return {"status": scenario["status"], "scenario_id": scenario["id"], "reason": scenario["reason"],
                    "reason_code": scenario["reason_code"], "data_class": "calculated",
                    "note": "No solar-energy figure is given for a site without supporting terrain data: no number, no estimate."}
        return solar_energy(scenario, req.area_m2, req.efficiency, req.irradiance_w_m2)

    return router
