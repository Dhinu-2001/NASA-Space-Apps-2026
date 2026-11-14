# Architecture (Stage 2 baseline)

Supersedes nothing in `docs/stage0/04_Architecture_Stack_Modules.md`; this records what is actually built and the enforced boundaries. Approved decisions are in `docs/DECISIONS.md`.

## Layout

```
/engine/lunarnav        Python science engine. NO web imports (enforced by a test).
    __init__.py         MODEL_VERSION (stamped into every result's provenance)
    errors.py           Typed errors + ErrorCode (shared vocabulary with the API)
    capabilities.py     Honest registry of unbuilt/built science (status per capability)
    sites.py            Site model, coordinate validation/normalisation, catalogue policy loader
    dem.py              South-polar-stereographic projection, checksum-verified DEM windows,
                        bilinear elevation lookup with typed failures (no fallback)
/api/lunarnav_api       FastAPI app. Thin: validation, logging, error mapping, no science.
    config.py           Env-driven settings (LUNARNAV_*), .env supported
    logging_setup.py    structlog (JSON or console), request-id correlation
    errors.py           Exception handlers -> single ErrorBody shape
    schemas.py          Pydantic contract models -> OpenAPI
    main.py             App factory, middleware, /health, /version
    routes_data.py      /sites, /sites/validate, /dem/windows, /dem/elevation
/web                    React + TypeScript + Vite. Presentation only (decision C4).
    src/api/client.ts   Typed fetch client; types generated from docs/openapi.json
/tests/engine           Engine unit tests (no HTTP)
/tests/api              API integration tests (TestClient)
/data                   catalogue/ manifests/ (tracked); kernels/ dem_cache/ results/ (ignored, G1)
                        see docs/stage2/DATA_ARCHITECTURE.md
/docs                   Specs, DECISIONS.md, API_CONTRACT.md, openapi.json, DEV_SETUP.md
/scripts                export_openapi.py
```

## Dependency direction (enforced)

```
web ──HTTP/JSON──► api ──imports──► engine
 (no engine import)        (engine never imports api)
```
- The engine is importable and testable with no web framework (test: `test_engine_has_no_web_framework_dependency`).
- The frontend can only obtain science through the API; types are generated from the backend, so contract drift fails `npm run typecheck`.

## Cross-cutting conventions

| Concern | Convention |
|---|---|
| Config | `LUNARNAV_*` env vars via pydantic-settings; `.env.example` committed, `.env` ignored. Frontend: `VITE_API_BASE`, `VITE_API_TARGET` |
| Logging | structlog; every request logs method/path/status/duration with `request_id`. Scientific runs will additionally bind `scenario_hash` (Stage 5+) |
| Errors | Engine raises `LunarNavError` subclasses; API maps to HTTP + `ErrorBody`. Unknown exceptions → 500 `INTERNAL`, no details leaked, traceback logged |
| Data honesty | `capabilities.py` statuses surface in `/version` and the UI. A capability becomes `validated` only after its stage gate passes |
| Provenance | `MODEL_VERSION` now; kernel/DEM checksums and parameters added from Stages 2–3 (decision S4) |
| Determinism | Canonical JSON serialization + documented numeric tolerances from Stage 3 (decision S5) |
| Heavy data | Never in Git; fetched/extracted by scripts into `/data` with SHA-256 manifests |

## Module boundaries still to be created (by stage)
`time`, `frames`, `ephemeris` (S3) · `horizon` (S4) · `visibility`, `metrics` (S5) · `scenario`, `comparison` (S6) · `provenance` registry (S5). Each lands with its own tests and its own entry flipped in `capabilities.py`.
