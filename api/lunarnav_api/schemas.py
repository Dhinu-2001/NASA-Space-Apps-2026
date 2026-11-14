"""API contract models (Pydantic). The OpenAPI document generated from these is the source of
truth for the frontend's TypeScript types (see docs/API_CONTRACT.md)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class ErrorBody(BaseModel):
    code: Literal[
        "INVALID_INPUT",
        "OUT_OF_DEM_COVERAGE",
        "DATA_MISSING",
        "EPHEMERIS_OUT_OF_RANGE",
        "NOT_IMPLEMENTED",
        "INTERNAL",
    ]
    message: str
    field: str | None = None
    details: dict[str, Any] = {}
    request_id: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    model_version: str
    env: str
    time_utc: str


class CapabilityOut(BaseModel):
    key: str
    title: str
    stage: int
    status: Literal["not_implemented", "implemented_unvalidated", "validated"]


class VersionResponse(BaseModel):
    model_version: str
    api_version: str
    stage: int
    notice: str
    capabilities: list[CapabilityOut]
