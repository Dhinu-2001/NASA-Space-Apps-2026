# Architecture (final, Stage 11)

What is actually built and the boundaries that are enforced. Approved decisions are in [DECISIONS.md](DECISIONS.md); the original design is in `docs/stage0/04_Architecture_Stack_Modules.md`.

## 1. Shape

```
Browser (React + TypeScript, presentation only)          NASA Moon Trek (map imagery, images only)
   │  HTTP/JSON, same origin in production (/api/...)             ▲
   ▼                                                               │ tiles loaded by the browser
FastAPI application  ── thin: validation, error mapping, limits, no science ──┐
   │ imports                                                                   │
   ▼                                                                           ▼
Python science engine (lunarnav)  ──►  data/  kernels (SPICE) · dem_cache (LOLA windows) · catalogue · manifests · results (cache)
```

Production serves the built UI and the API from **one process** (`lunarnav_api.serve`): `/` is the UI, `/api` is the API. Development runs the Vite dev server (`:5173`, proxying `/api`) beside the API (`:8000`).

## 2. Layout

```
engine/lunarnav        Science engine. No web imports (enforced by a test).
  __init__.py          MODEL_VERSION: stamped into every result and every cache key
  errors.py            Typed errors and ErrorCode, shared vocabulary with the API
  capabilities.py      Registry of what is built and approved (status per capability; surfaced by /version and the UI)
  sites.py             Site model, coordinate validation, cited catalogue loader
  dem.py               South-polar stereographic projection, checksum-verified DEM windows, bilinear lookup (typed failures, no fallback)
  frames.py            Pure geometry: ENU basis, azimuth/elevation, angular size, great-circle destination
  ephemeris.py         SPICE Sun/Earth for a lunar observer (kernel checksums, validated range, UTC handling)
  horizon.py           Terrain horizon engine: ray sampling on the sphere, completeness bound, on-disk + memory cache
  visibility.py        Disc-model visibility, transitions to 1 s, intervals/metrics, position sensitivity
  scenarios.py         Scenario ids, comparison, rankings, delay simulator, "terrain data insufficient" rule, result cache
  engineering.py       Idealised solar-energy upper bound (reuses scenario results; imports no science code)
  provenance.py        Deterministic calculation metadata; what-this-build-is-made-of
  cachecap.py          LRU size caps for result caches (Stage 11)
api/lunarnav_api       FastAPI. One module per endpoint family: routes_data, routes_ephemeris, routes_horizon,
                       routes_visibility, routes_scenarios, routes_engineering; main (factory, middleware, /health /version /provenance);
                       errors (one ErrorBody shape), schemas, config (LUNARNAV_* settings),
                       hardening (security headers, body/compute limits), serve (one-process production entry point)
web/src                React 19 + TypeScript 5 (strict) + Vite
  api/                 Typed client; types generated from docs/openapi.json (contract drift fails the type check)
  views/               ViewTab, CompareTab, SitesTab, ExploreTab, DelayTab, AboutTab; learn.tsx, profiles.tsx
  components/          SiteMap (imagery basemap), HorizonPlot, ElevationChart, Timeline, AdvancedPlots, SweepChart, MetricsPanel, SolarPanel, TimePlayer
  polar.ts, sweep.ts, format.ts   Layout/request-building/formatting helpers (no science)
tests/                 engine, api, validation (golden regression, edge cases) · web/src/*.test.tsx (Vitest, axe-core)
scripts/               data (fetch_kernels, extract_dem_window, provision/pack/verify_data), validation and studies,
                       warm_cache, e2e_browser, build_*_report, export_openapi, run_production
deploy/ Dockerfile docker-compose.yml   Container deployment (docs/DEPLOYMENT.md)
data/                  tracked: catalogue/, manifests/, validation/ · git-ignored: kernels/, dem_cache/, results/
```

## 3. Boundaries (each enforced by a test, not by convention)

| Boundary | Rule | Enforcement |
|---|---|---|
| Engine ↔ web | The engine never imports a web framework; the API never contains science | `test_engine_has_no_web_framework_dependency`; code review of `routes_*` as thin wrappers |
| **C4: the browser calculates nothing scientific** | The UI only requests and displays backend numbers; layout arithmetic (scaling, projection of a backend lat/lon onto the map) is the only computation | Request-count tests in every view (a result view makes exactly the requests that were asked for, interactions make none), static tests for no `fetch`/trig in display components, the golden-table pin on the map's projection mirror |
| Honest data | No fallback for missing terrain; every result states its data class; insufficient sites carry no numbers | `terrain_data_insufficient` tests across engine, API and UI; `capabilities.py` statuses |
| Reuse, not recomputation | Engineering uses scenario results; scenarios use the visibility engine; the UI uses API results | Static import tests (`test_engineering.py`), request-count tests |
| Data integrity | Every kernel and DEM window is SHA-256 verified at load; a mismatch is refused (`DATA_MISSING`), never used | `ephemeris.py`, `dem.py` loaders; `scripts/verify_data.py` |
| Reproducibility | Same inputs + same data + same model version ⇒ same bytes; scenario ids hash inputs, model version and DEM fingerprint | Determinism and golden-regression tests; `calculation_metadata` block |

## 4. Data flow of one request (Compute in Site & time)

1. The UI sends `GET /horizon/profile`, `POST /visibility/series`, `GET /visibility/at`, `GET /ephemeris/position`.
2. API validates (pydantic + engine checks) and calls `HorizonService` (terrain horizon for the site and for 8 displaced positions, cached by DEM checksums), `VisibilityService` (ephemeris samples × horizon ⇒ per-step states, bisected transitions, intervals, metrics, bands) and `EphemerisService`.
3. The response carries `data_class`, provenance, completeness flags and the position sensitivity; the UI lays it out (timelines, plots, tables) without altering any number.
4. Results are cached on disk keyed by inputs + model version + DEM checksums (LRU-capped); a repeat press of Compute re-requests and is answered from cache in about 0.1 s.

## 5. Cross-cutting conventions

| Concern | Convention |
|---|---|
| Config | `LUNARNAV_*` environment variables (pydantic-settings, `.env` supported; `.env.example`). Frontend build: `VITE_API_BASE` |
| Logging | structlog (JSON in production), `request_id` correlation, no query strings or addresses logged |
| Errors | Engine raises `LunarNavError`; API maps to HTTP + the single `ErrorBody` shape; unknown exceptions return a generic 500 and log the traceback; limits return typed 413/503 |
| Security | Security headers on every response, CSP on the UI, request body cap, bounded compute concurrency, bounded caches, bounded list sizes, no secrets, audited dependencies ([stage11/SECURITY_REVIEW.md](stage11/SECURITY_REVIEW.md)) |
| Versions | API `1.0.0`; `MODEL_VERSION` `0.10.0-stage8` (science/model identity; unchanged by Stage 9–11, which added no science) |
| Heavy data | Never in git; fetched by scripts with SHA-256 manifests (`provision_data.py`), or unpacked from a bundle (`pack_data.py`) |

## 6. Known architectural limits
Single process with an in-memory horizon cache (16 items) and per-process compute limiter; horizontal scaling would need a shared cache and a shared limiter (future work). Heavy computations run in the request thread pool (a cold new point takes about a minute); a job queue with progress reporting is future work. See [stage11/FUTURE_WORK.md](stage11/FUTURE_WORK.md).
