# 05 — Development Roadmap, Hackathon MVP, Risk Register

Stage 0 deliverable.

## 1. Realistic hackathon MVP ("minimum scientifically defensible product")

Stages **1 → 7 plus the consolidated parts of 9**. Concretely a user can:
1. Choose a curated south-pole site or type lat/lon (validated).
2. Choose UTC date/time and a 30-day window.
3. See Sun and Earth az/el, a terrain horizon profile with both bodies overlaid, and a sky-dome plot.
4. See sunlight and Earth-visibility timelines with terrain-corrected intervals, longest darkness and longest blackout.
5. Add up to ~4 scenarios (site and/or date), including "delay by N days", and read a metric-delta table.
6. Open a provenance panel: ephemeris kernels, DEM product/resolution, assumptions, limitations, per-metric explanations.

Explicitly **out of MVP**: 3D, thermal, link budget, PDF, AI explanations, roughness/boulders, accounts.
**MVP+ (if time)**: antenna elevation mask, solar incidence/power with explicit panel inputs, LOLA slope readout, PSR flag, CSV/JSON export, Sun/Earth disk partial visibility.

## 2. Stage roadmap

| Stage | Name | Output | Gate evidence |
|---|---|---|---|
| 0 | Research & spec | These docs | You approve |
| 1 | Foundation | Repo, API/health, web shell, tests, config, logging | App starts; FE↔BE ping; tests run; no science claimed |
| 2 | Sites + DEM | Catalogue (cited), validation, COG window reader, elevation lookup, metadata | Known-coordinate elevations match LOLA reference within stated tolerance |
| 3 | Ephemeris | SPICE engine, Sun/Earth az/el series, Horizons oracle comparison | Residuals vs Horizons reported and within tolerance |
| 4 | Horizon | Ray-cast horizon, caches, API | Synthetic flat/wall/curvature/height tests; independent real-DEM check |
| 5 | Visibility | Booleans, intervals, metrics | Terrain-vs-geometric difference proven; step-sensitivity test |
| 6 | Scenarios | Model, compare, delay | Date/site changes change outputs; incomplete data flagged |
| 7 | UI | Full workflow | You complete the 7-step workflow |
| 8 | Engineering | Power, mask, slope/aspect, temperature | Stretch; as listed |
| 9 | Validation | Reports, regression suite | Every metric traceable |
| 10 | Advanced visuals | 3D, education | Deferred |
| 11 | Release | Deploy, docs, demo | Final acceptance |

If time is short, cut order (first to drop): 10 → temperature/roughness (8) → power (8) → export → disk-partial visibility. Never cut 4, 5, 6, or provenance.

## 3. Risk register

Likelihood/Impact: L/M/H.

| ID | Risk | L | I | Mitigation | Owner stage |
|---|---|---|---|---|---|
| R1 | Python/Node not installed on dev machine | H | M | Install in Stage 1 with your permission; pin versions | 1 |
| R2 | 20 m DEM too coarse to resolve horizon-controlling rims | M | H | Resolution sensitivity test (20 m vs 10 m vs 5 m at same site); expose EFFRES; use 5/10 m for priority sites; document | 4 |
| R3 | DEM frame (DE421 MOON_ME) vs ephemeris (DE440 ME) mismatch | M | M | Measure offset; document; pin frame kernel; test at pole | 3/4 |
| R4 | Horizon truncated by DEM edge for sites near 80°S or distant massifs | M | H | Multi-resolution far-field; per-azimuth quality flags; refuse "complete" claim when truncated | 4 |
| R5 | Remote data (PGDA/Horizons/NAIF) unavailable at demo time | M | H | Pre-fetch kernels and DEM windows; Horizons off the runtime path; checksums | 2/3/11 |
| R6 | Azimuth singularity at pole / wrong north convention | M | M | Explicit convention, unit tests at lat −90 and −89.999 | 3 |
| R7 | Event misses from coarse time step; false short intervals | M | H | Bisection on predicate; step sensitivity tests; min-duration reporting | 5 |
| R8 | Centre-of-disk visibility misleads at ~1° Sun elevations | H | M | Label limitation in MVP; disk model in Stage 8 | 5/8 |
| R9 | Curated site coordinates unverified/wrong | M | H | Cite each; exclude unverified; cross-check visually in QuickMap | 2 |
| R10 | Overclaiming (visibility = comms, sunlight = power, slope = safe) | M | H | Label taxonomy measured/calculated/assumed/illustrative; metric registry text reviewed | all |
| R11 | Late UI hides integration problems | M | M | Option to pull minimal UI after S5 (decision C2) | 5/7 |
| R12 | Future-date leap-second/kernel range limits | L | L | Restrict validated range 2025–2035; flag assumption | 3 |
| R13 | Performance: many scenarios × fine step | L | M | Horizon cache by (site, height, product); vectorised SPICE; result cache | 6 |
| R14 | Polar stereographic map UX/projection bugs | M | M | Use DEM CRS for picker; test lon/lat round-trip | 7 |
| R15 | Team scope creep into 3D/thermal | H | H | Stage-gate protocol; cut order above | all |
| R16 | Licensing/attribution omissions | L | M | Attribution panel; verify terms per dataset | 2/11 |

## 4. Stage-gate acceptance for Stage 0 (what "approved" means)
You confirm: (a) the product definition and MVP; (b) resolutions to ambiguities C1–C11; (c) the stack and SPICE-engine/Horizons-oracle split; (d) permission to install Python 3.12 and Node LTS at Stage 1; (e) whether to pull a minimal UI forward (C2).
