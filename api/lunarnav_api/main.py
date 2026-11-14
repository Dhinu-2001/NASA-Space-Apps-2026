"""Application factory."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from importlib import metadata

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from lunarnav import MODEL_VERSION
from lunarnav.capabilities import CAPABILITIES
from lunarnav.ephemeris import EphemerisService
from lunarnav.errors import DataMissingError, NotImplementedYetError
from lunarnav.horizon import HorizonService
from lunarnav.provenance import build_provenance
from lunarnav.visibility import VisibilityService

from .config import REPO_ROOT, get_settings
from .errors import register_error_handlers
from .logging_setup import configure_logging
from .routes_data import build_router
from .routes_ephemeris import build_ephemeris_router
from .routes_horizon import build_horizon_router
from .routes_scenarios import build_scenario_router
from .routes_visibility import build_visibility_router
from .schemas import CapabilityOut, ErrorBody, HealthResponse, VersionResponse

API_VERSION = "0.1.0"
CURRENT_STAGE = 9

_ERROR_RESPONSES = {422: {"model": ErrorBody}, 500: {"model": ErrorBody}}


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    log = structlog.get_logger("lunarnav_api")

    app = FastAPI(
        title="Lunar Landing Site Navigator API",
        version=API_VERSION,
        description=(
            "Stage 6: sites, DEM, ephemeris, terrain horizon, terrain-corrected Sun/Earth visibility with "
            "position-sensitivity bands, and scenario comparison / mission delay simulator."
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
    horizon_service = HorizonService(settings.data_dir)
    app.include_router(build_horizon_router(settings.data_dir, horizon_service))
    app.include_router(build_visibility_router(settings.data_dir, horizon_service))
    app.include_router(build_scenario_router(
        settings.data_dir, VisibilityService(EphemerisService(settings.data_dir), horizon_service)))

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
                "Stage 9: terrain-corrected Sun/Earth visibility, scenario comparison and mission delay simulator "
                "(geometric line of sight / direct illumination only; not link availability or irradiance). "
                "Sites without supporting terrain data are reported as terrain_data_insufficient and never ranked. "
                "Engineering assessments (solar power, antenna, slope, temperature) are not built."
            ),
            capabilities=[
                CapabilityOut(key=c.key, title=c.title, stage=c.stage, status=c.status.value)
                for c in CAPABILITIES
            ],
        )

    eph_for_provenance = EphemerisService(settings.data_dir)

    @app.get("/provenance", tags=["meta"], responses=_ERROR_RESPONSES)
    def provenance() -> dict:
        """What this running application is built from: code version, software, SPICE kernels and DEM windows
        with SHA-256, the site catalogue and its sources, validation fixtures, constants and data classes."""
        try:
            eph = eph_for_provenance.provenance()
            eph_error = None
        except DataMissingError as e:  # partial install: report what is missing rather than failing
            eph, eph_error = None, e.message
        out = build_provenance(settings.data_dir, eph, REPO_ROOT)
        for pkg in ("fastapi", "pydantic", "uvicorn"):  # web-layer versions are added here, not in the engine
            try:
                out["software"][pkg] = metadata.version(pkg)
            except metadata.PackageNotFoundError:
                pass
        if eph_error:
            out["spice_kernels_error"] = eph_error
        return out

    @app.post("/engineering/solar", include_in_schema=False)
    def _engineering_not_implemented():
        # Demonstrates the NOT_IMPLEMENTED contract; engineering metrics arrive in Stage 8.
        raise NotImplementedYetError("Solar power / antenna / slope metrics are planned for Stage 8.")

    return app


app = create_app()
