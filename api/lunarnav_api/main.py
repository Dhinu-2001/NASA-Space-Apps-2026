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
from lunarnav.scenarios import ScenarioService
from lunarnav.visibility import VisibilityService

from .config import REPO_ROOT, get_settings
from .errors import register_error_handlers
from .hardening import BodyLimitMiddleware, HeavyLimitMiddleware, SecurityHeadersMiddleware
from .logging_setup import configure_logging
from .routes_data import build_router
from .routes_engineering import build_engineering_router
from .routes_ephemeris import build_ephemeris_router
from .routes_horizon import build_horizon_router
from .routes_scenarios import build_scenario_router
from .routes_visibility import build_visibility_router
from .schemas import CapabilityOut, ErrorBody, HealthResponse, VersionResponse

API_VERSION = "1.0.0"
CURRENT_STAGE = 11

_ERROR_RESPONSES = {422: {"model": ErrorBody}, 500: {"model": ErrorBody}}


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    log = structlog.get_logger("lunarnav_api")

    app = FastAPI(
        title="Lunar Landing Site Navigator API",
        version=API_VERSION,
        description=(
            "Sites, DEM, ephemeris, terrain horizon, terrain-corrected Sun/Earth visibility with position-sensitivity "
            "bands, scenario comparison, mission delay simulator and an idealised solar-energy upper bound."
        ),
    )
    # Middleware order (innermost first): compute limiter, body limit, CORS, security headers (outermost, so even refusals carry them).
    app.add_middleware(HeavyLimitMiddleware, limit=settings.max_heavy_requests, queue_seconds=settings.heavy_queue_seconds,
                       on_busy=lambda path: log.warning("server_busy", path=path))
    app.add_middleware(BodyLimitMiddleware, max_bytes=settings.max_body_bytes)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
        expose_headers=["x-request-id"],
    )
    app.add_middleware(SecurityHeadersMiddleware)
    register_error_handlers(app)
    app.include_router(build_router(settings.data_dir))
    app.include_router(build_ephemeris_router(settings.data_dir))
    horizon_service = HorizonService(settings.data_dir)
    app.include_router(build_horizon_router(settings.data_dir, horizon_service))
    app.include_router(build_visibility_router(settings.data_dir, horizon_service))
    visibility_service = VisibilityService(EphemerisService(settings.data_dir), horizon_service)
    scenario_service = ScenarioService(settings.data_dir, visibility_service)
    app.include_router(build_scenario_router(settings.data_dir, visibility_service, scenario_service))
    app.include_router(build_engineering_router(scenario_service))

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
                "Terrain-corrected Sun/Earth visibility, scenario comparison and mission delay simulator "
                "(geometric line of sight / direct illumination only; not link availability or irradiance). "
                "Sites without supporting terrain data are reported as terrain_data_insufficient and never ranked. "
                "Engineering is limited to an idealised direct-beam solar-energy upper bound; antenna, slope and temperature assessments are not built."
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
        if not out.get("git_commit") and settings.git_commit:   # installed/containerised build: there is no .git directory to read
            out["git_commit"] = settings.git_commit
        for pkg in ("fastapi", "pydantic", "uvicorn"):  # web-layer versions are added here, not in the engine
            try:
                out["software"][pkg] = metadata.version(pkg)
            except metadata.PackageNotFoundError:
                pass
        if eph_error:
            out["spice_kernels_error"] = eph_error
        return out

    @app.post("/engineering/antenna", include_in_schema=False)
    def _antenna_not_implemented():
        # Demonstrates the NOT_IMPLEMENTED contract: antenna masks, slope and temperature are deferred.
        raise NotImplementedYetError("Antenna masks, slope/aspect and temperature assessments are deferred (not built).")

    return app


app = create_app()
