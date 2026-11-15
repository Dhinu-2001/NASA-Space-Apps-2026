# Performance review (Stage 11, task 4)

Measured 2026-11-15 on the development machine (Windows 11) against the **production-mode server** started from a clean virtual environment (`uvicorn lunarnav_api.serve:app`, one process, `LUNARNAV_MAX_HEAVY_REQUESTS=2`). One run each; the figures are indicative, not a benchmark suite.

## 1. API latency (real data, real requests over HTTP)
| Request | Time | Notes |
|---|---|---|
| `GET /health`, `GET /sites` | 0.13 s / 0.03 s | |
| `GET /ephemeris/position` (one time) | 0.10 s | SPICE |
| `GET /horizon/profile` IM-2, cached | 0.07 s | |
| `GET /horizon/profile` Chandrayaan-3, first use in this process | 1.6 s | loads the 108 MB 60 m window into memory |
| `POST /scenarios/evaluate` IM-2, 30 d @ 15 min, **cached** | 0.04 s | result cache |
| `POST /scenarios/evaluate`, **new start date** (terrain profiles cached) | **5.0 s** | visibility recomputation for nominal + 8 displaced positions |
| same request again | 0.03 s | |
| `POST /scenarios/evaluate`, **new map point** (9 new terrain profiles + 30-day series) | **67.7 s** | the worst case a visitor can trigger |
| `POST /engineering/solar`, cached scenario | 0.08 s | reuses the scenario |
| Default comparison (8 scenarios), during cache warm-up | 26.8 s; sub-second once result-cached | |

**Reading:** everything the demonstration shows is served from caches in well under a second; a visitor who picks a point nobody has computed waits about a minute, which the UI states while loading ("a first calculation can take about a minute; later requests are cached").

## 2. Memory
About **85 MB at start**, about **350 MB** after loading the horizon windows and running scenarios (peak seen 352 MB). Recommended allocation 1 GB.

## 3. Frontend
Production bundle: **363 KB JavaScript (107 KB gzipped)** + 7.5 KB CSS, one request each, hashed file names (cacheable); no third-party runtime dependencies beyond React. The map adds 16 image requests (about 1 MB) from NASA, outside the app's control. Opening a result view issues 1–4 API requests; interactions (time player, zoom, toggles, hover, CSV export) issue none (request-count tests).

## 4. What was optimised or bounded in this stage
* Warm-cache script (`scripts/warm_cache.py`) precomputes the default views, comparisons and delay example; with it the first visitor sees sub-second responses.
* Result caches are now LRU-capped (no unbounded disk growth) and refresh on use.
* A concurrency limiter prevents a burst of cold requests from starving the host (CPU is the bottleneck, not memory).
* Pressing Compute again always re-requests (cheap: cached); fixed a defect where it did nothing.

## 5. Known performance limits (see [FUTURE_WORK.md](FUTURE_WORK.md))
* New points are slow because 9 terrain profiles (nominal + 8 displaced positions, 1440 rays each) are computed per point; precomputing a coarse grid of profiles or running them in parallel processes would cut this, but is a larger change than this stage allowed.
* Computation runs in the request, so a slow request holds an HTTP connection; a job queue with progress reporting would fix this.
* One process: the in-memory horizon cache (16 profiles) and the limiter are per process.
* The backend suite takes about 2 minutes; the frontend suite under a minute.
