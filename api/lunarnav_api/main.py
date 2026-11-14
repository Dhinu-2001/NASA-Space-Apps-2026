"""Application factory."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from lunarnav import MODEL_VERSION
from lunarnav.capabilities import CAPABILITIES
from lunarnav.errors import NotImplementedYetError

from .config import get_settings
from .errors import register_error_handlers
from .logging_setup import configure_logging
from .routes_data import build_router
from .routes_ephemeris import build_ephemeris_router
from .routes_horizon import build_horizon_router
from .schemas import CapabilityOut, ErrorBody, HealthResponse, VersionResponse

API_VERSION = "0.1.0"
CURRENT_STAGE = 4

_ERROR_RESPONSES = {422: {"model": ErrorBody}, 500: {"model": ErrorBody}}


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    log = structlog.get_logger("lunarnav_api")

    app = FastAPI(
        title="Lunar Landing Site Navigator API",
        version=API_VERSION,
        description=(
            "Stage 4: sites, DEM lookup, Sun/Earth ephemeris (geometric) and terrain horizon profiles. "
            "Visibility endpoints are declared in docs/API_CONTRACT.md and are NOT implemented yet."
        ),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
        expose_headers=["x-request-id"],
    )
    register_error_handlers(app)
    app.include_router(build_router(settings.data_dir))
    app.include_router(build_ephemeris_router(settings.data_dir))
    app.include_router(build_horizon_router(settings.data_dir))

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        request.state.request_id = request_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        start = time.perf_counter()
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        log.info(
            "request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=round((time.perf_counter() - start) * 1000, 2),
        )
        return response

    @app.get("/health", response_model=HealthResponse, responses=_ERROR_RESPONSES, tags=["meta"])
    def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            service="lunarnav-api",
            model_version=MODEL_VERSION,
            env=settings.env,
            time_utc=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )

    @app.get("/version", response_model=VersionResponse, responses=_ERROR_RESPONSES, tags=["meta"])
    def version() -> VersionResponse:
        return VersionResponse(
            model_version=MODEL_VERSION,
            api_version=API_VERSION,
            stage=CURRENT_STAGE,
            notice=(
                "Stage 4: site catalogue, DEM lookup, geometric Sun/Earth ephemeris and terrain horizon "
                "profiles. No terrain-corrected Sun/Earth visibility results are produced yet."
            ),
            capabilities=[
                CapabilityOut(key=c.key, title=c.title, stage=c.stage, status=c.status.value)
                for c in CAPABILITIES
            ],
        )

    @app.post("/scenarios/evaluate", include_in_schema=False)
    def _scenario_not_implemented():
        # Demonstrates the NOT_IMPLEMENTED contract; scientific endpoints arrive in later stages.
        raise NotImplementedYetError("Scenario evaluation is planned for Stages 5-6.")

    return app


app = create_app()
