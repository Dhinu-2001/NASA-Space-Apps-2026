# 04 — Technology Stack, Architecture, Module Responsibilities

Stage 0 deliverable. Proposal for approval; nothing is installed or created beyond docs.

## 1. Stack recommendation

| Layer | Choice | Why | Alternative rejected |
|---|---|---|---|
| Science engine | **Python 3.12** package `lunarnav` (no web imports) | SpiceyPy (NAIF's SPICE bindings) is the only mature, JPL-grade path to DE440 + lunar orientation; NumPy vectorisation for ray sampling; rasterio/GDAL reads COGs by window | Node/TS: no credible SPICE; hand-rolled ephemeris violates data principle |
| Numerics | NumPy; Numba only if profiling demands | Keeps install simple on Windows | — |
| DEM I/O | rasterio (bundled GDAL wheels) + pyproj for the polar stereographic CRS | Windowed reads of remote COG via HTTP range (verified server support) | Downloading 2.7–5 GB rasters per user |
| API | **FastAPI** + Pydantic v2 | Typed contracts, auto OpenAPI docs (API-contract deliverable for free), async | Flask (no typing), Django (overkill) |
| Persistence | None for MVP: scenario = JSON definition + hash; disk cache (horizon profiles, DEM windows, results keyed by hash). **SQLite** optional at Stage 6 | Reproducibility without DB ops | Postgres (overengineering) |
| Frontend | **React + TypeScript + Vite** | Typed API client generated from OpenAPI; large ecosystem | — |
| Charts | Apache ECharts (or Plotly) for timelines/horizon/polar sky plot | Polar + time-series + brush/zoom built in; one library | D3 raw (slow to build), Chart.js (no polar sky dome) |
| 2D map | Leaflet with a custom **south-polar stereographic CRS** over a hillshade/imagery tile layer; fallback to a plain canvas of the LOLA hillshade window | Map in the same projection as the DEM, so site picking is exact | Web-Mercator maps (distort the pole badly) |
| 3D (Stage 10 only) | three.js / CesiumJS Moon | Deferred per Principle 1 | — |
| Tests | pytest (+ hypothesis for properties), Vitest, Playwright (Stage 11) | | |
| Logging | structlog (JSON) | NFR-7 | |
| Config | `.env` + `pydantic-settings`; `.env.example` committed | | |
| Packaging/deploy | Docker (backend) + static frontend; target: single small VM/PaaS | Reproducible deploy; NAIF kernels + DEM cache on a mounted volume | Serverless (cold start + 40 MB kernels + cache) |

Monorepo layout (Stage 1 will create it):
```
/engine   (lunarnav: time, frames, ephemeris, dem, horizon, visibility, metrics, scenario, provenance)
/api      (FastAPI app; thin; imports engine)
/web      (React app)
/data     (kernels/, dem_cache/, sites.json — gitignored except catalogue + manifests with SHA-256)
/docs
/tests    (engine unit, validation reference fixtures, api integration)
```

## 2. High-level architecture

```
 ┌──────────────────────────── Web UI (React/TS) ───────────────────────────┐
 │ Site picker/map │ Date-time │ Sky view │ Horizon │ Timelines │ Compare │ Provenance │
 └───────────────▲──────────────────────────────────────────────────────────┘
                 │ typed JSON (OpenAPI) — plotting only, no astronomy
 ┌───────────────┴────────── API (FastAPI) ────────────────────────────────┐
 │ /health /sites /scenario/evaluate /compare /delay /horizon /metrics-info │
 └───────────────▲──────────────────────────────────────────────────────────┘
                 │ python calls
 ┌───────────────┴──────────── engine: lunarnav ───────────────────────────┐
 │ scenario ─► visibility ─┬─► ephemeris ──► frames/time ─► SPICE kernels    │
 │ (hash, cache)    │      └─► horizon  ──► dem  ─► DEM windows (COG cache)  │
 │                  └─► metrics/intervals ─► comparison ─► provenance        │
 └────────────────────────────────────────────────────────────────────────────┘
 Offline/build-time:  ingest scripts (fetch kernels, extract DEM windows, checksums)
 Validation-time:     Horizons client (oracle) — never on the request path
```

## 3. Module responsibility document

| Module | Responsibility | Inputs → Outputs | Must not |
|---|---|---|---|
| `time` | UTC ⇄ ET conversion, leap-second caveat flags | ISO UTC → ET, flags | use local timezones |
| `frames` | Named transforms: ICRF→MOON_ME→ENU; az/el conversion; polar tie-break | vectors, lat/lon → vectors/angles | embed ephemeris |
| `ephemeris` | Sun/Earth az/el/range/angular diameter time series | site, time grid → arrays | read DEM; call network |
| `sites` | Catalogue + validation + normalisation | lat/lon → validated Site | accept uncited curated entries |
| `dem` | Locate product, windowed read, lon/lat ⇄ polar-stereo, elevation lookup, quality layers, coverage flags | site, radius → raster window + metadata | silently fill gaps |
| `horizon` | Azimuth ray-casting with curvature, observer height, multi-resolution, per-azimuth quality | DEM window, observer → h(az) profile | know about Sun/Earth |
| `visibility` | Compare elevation vs h(az); geometric / limb / terrain booleans | ephemeris series + horizon → boolean series | alter inputs |
| `metrics` | Intervals, bisection refinement, longest runs, totals, time-to-event | boolean series → metrics | access UI/format strings |
| `scenario` | Scenario model, canonical hash, cache, orchestration | scenario JSON → result | reimplement science |
| `comparison` | Align scenarios, deltas, incomplete-data flags; delay generator | results → comparison | rank with a single opaque score |
| `provenance` | Metric registry (6 Principle-4 fields), data manifests, run metadata | — | invent accuracy figures |
| `api` | HTTP, validation, error mapping, logging | | contain science |
| `web` | Presentation and interaction | | compute ephemeris/horizon |

Stage 8 adds `power`, `comm` (antenna mask/pointing), `terrain_stats` (slope/aspect from LDSM, PSR); Stage 10 adds 3D.

## 4. API surface (draft contract; formalised in Stage 1)

`GET /health` · `GET /sites` · `POST /sites/validate` · `POST /scenarios/evaluate` · `POST /scenarios/compare` · `POST /scenarios/delay` · `GET /horizon?lat&lon&height` · `GET /metrics/registry` · `GET /provenance/{scenario_hash}`.
Error body: `{code, message, field?, details?}` with codes `INVALID_INPUT`, `OUT_OF_DEM_COVERAGE`, `DATA_MISSING`, `EPHEMERIS_OUT_OF_RANGE`, `INTERNAL`.

## 5. Development dependency graph

```
S1 foundation ─► S2 sites+DEM ─────────────► S4 horizon ─┐
        │                                                 ├─► S5 visibility ─► S6 scenarios ─► S7 UI ─► S8 engineering ─► S9 validation ─► S10 advanced ─► S11 release
        └──────────────► S3 ephemeris ────────────────────┘
```
S3 and S2 are independent after S1 (could be parallelised by two people; stage-gate still approves them one at a time).
Critical path: S1→S2→S4→S5→S6→S7. The largest scientific risk sits in S4 (horizon quality) and S3 (frame consistency).

## 6. Complexity estimate (relative, 1 = small … 5 = large)

| Stage | Complexity | Main driver |
|---|---|---|
| 1 Foundation | 2 | Environment install (Python/Node), skeleton |
| 2 Sites + DEM | 3 | CRS handling, COG windowing, curated source compilation |
| 3 Ephemeris | 3 | Kernel pairing, frame math, Horizons validation |
| 4 Horizon | 4 | Numerics, multi-resolution, validation |
| 5 Visibility | 3 | Event refinement, edge intervals |
| 6 Scenarios | 2 | Orchestration, caching |
| 7 UI | 4 | Polar map, charts, comparison UX |
| 8 Engineering | 3 | Optional/stretch |
| 9 Validation | 3 | Reference scenarios |
| 10 Advanced | 4 | 3D (deferred) |
| 11 Release | 3 | Deploy + docs |
