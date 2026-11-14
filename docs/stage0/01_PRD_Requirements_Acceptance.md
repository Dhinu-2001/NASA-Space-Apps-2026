# 01 — Product Requirements, Functional/Non-Functional Requirements, Acceptance Criteria

Stage 0 deliverable. Status: DRAFT for approval. Date: 2026-11-14.

## 1. Product definition

**What we are building:** a *Lunar Mission Scenario Evaluation Platform* — a web application whose scientific engine answers, for any lunar south-pole site and date:

1. Is the Sun above the **real terrain horizon** (not a flat horizon), and for how long?
2. Is Earth above the real terrain horizon (geometric line of sight), and for how long?
3. What are the longest continuous darkness and longest continuous Earth-blackout intervals?
4. How do these change if the landing slips by N days, or moves to a nearby site?

**What we are not building:** a 3D Moon viewer, a link-budget tool, a thermal simulator, a landing-safety certifier. Visibility ≠ communication; sunlight ≠ power; low slope ≠ safe landing. The UI must say so.

**Signature feature:** the Mission Delay Simulator (original vs. delayed vs. alternative site/date, side by side).

## 2. Users and core workflows

| User | Primary workflow |
|---|---|
| Mission planner | Pick site → set landing UTC → see terrain-corrected Sun/Earth → compare delayed/alternative scenarios → export traceable report |
| Researcher / lecturer | Inspect horizon profile, az/el curves, provenance, download data |
| Student / public | Guided "why is the south pole hard?" exploration with plain-language metric explanations |

Core workflow (all users): **Site → UTC date/time → Sun & Earth az/el → horizon comparison → timelines → add scenario → compare → understand differences.**

## 3. Ambiguities and conflicts found in the master specification

| # | Issue | Proposed resolution (needs your confirmation) |
|---|---|---|
| C1 | Delay simulator is labelled Priority **B4**, but it is the signature feature, and A8 (comparison) + Stage 6 already require most of it. | Treat comparison + delay simulator as **mandatory MVP** (it is just "same site, shifted date" on the A8 engine). |
| C2 | Stage gating puts the UI at Stage 7, so nothing is demonstrable until late. | Keep gating. Stages 3–6 each ship an API plus a scripted CLI/notebook-style verification output. **Option:** pull a minimal read-only UI forward after Stage 5 (your decision). |
| C3 | Stage 9 "validation" comes late, yet validation is needed when each module is built. | Each stage's tests include reference validation (Horizons comparison at Stage 3, etc.). Stage 9 consolidates and reports. |
| C4 | Principle 3 forbids frontend astronomy, but sky-dome drawing and time scrubbing need az/el. | Frontend may only *project/plot* backend-supplied az/el values. Scrubbing uses pre-computed backend time series. |
| C5 | "Persistence if approved." | MVP: scenarios are **reproducible JSON definitions** (shareable via URL/file) plus an on-disk result cache. SQLite only if you approve it at Stage 6. |
| C6 | "Geometric horizon" is used inconsistently. | Three defined horizons (see Methodology §5): **local-horizontal (0°)**, **spherical-limb horizon** (observer height), **terrain horizon** (DEM-derived). |
| C7 | Curated site list (Apollo, CLPS, other nations) is requested but coordinates must not be invented. | Catalogue entries must cite a primary source; Stage 2 compiles them. Unverified entries are excluded, not guessed. |
| C8 | Supported date range is unspecified. | Proposed validated range **2025-01-01 → 2035-12-31**, widening only after validation (kernel coverage is much larger, validation is the limit). |
| C9 | Observer/antenna/panel heights are unspecified. | Observer height is a user parameter; default is a clearly-labelled **assumption** (proposed 2.0 m), never presented as a mission value. |
| C10 | `chatgpt research.md` is an unverified interpretation (it states this itself, §8/§10). | Used as an idea source only. Every scientific claim in it was re-checked or is flagged in the Data doc. |
| C11 | Axis/convention ambiguity at exactly ±90° latitude (azimuth undefined). | Documented tie-break convention in Methodology §2; tested at the pole. |

## 4. Requirement classification (MVP scope)

Legend: **MVP** = in hackathon deliverable; **STRETCH** = only if time remains; **DEFER** = documented future work.

| ID | Requirement | Class | Stage |
|---|---|---|---|
| A1 | Curated sites + custom lat/lon | MVP | 2 (UI 7) |
| A2 | Date/time, explicit UTC | MVP | 2/3 |
| A3 | Sun az/el vs. time | MVP | 3 |
| A4 | Earth az/el vs. time | MVP | 3 |
| A5 | DEM horizon profile incl. curvature | MVP | 4 |
| A6 | Geometric vs. terrain-corrected visibility | MVP | 5 |
| A7 | Sunlight/dark/Earth/blackout timelines | MVP | 5 |
| A8 | Multi-site, multi-date comparison | MVP | 6 |
| B4 | Mission delay simulator | MVP (see C1) | 6/7 |
| B5 | Provenance, assumptions, limitations | MVP | cross-cutting, 9 |
| B1 | Solar power (cos-incidence model) | STRETCH | 8 |
| B2 | Antenna mask, pointing limit, Earth disk partial obstruction | STRETCH (mask) / STRETCH (disk) | 8 |
| B3 | Slope/aspect (LOLA slope product); roughness; PSR | STRETCH (slope, PSR layer) / DEFER (roughness, boulders) | 8 |
| C-* | 3D terrain, thermal, link budget, uncertainty propagation, AI explanations, PDF export | DEFER (CSV/JSON export = STRETCH) | 10+ |

## 5. Functional requirements (MVP)

- **FR-1 Site catalogue** — list of sites with name, lat, lon (east-positive), source citation; filter by region.
- **FR-2 Custom site** — lat ∈ [−90, 90], lon ∈ [−180, 360) normalised; reject non-numeric/out-of-range; warn if outside DEM coverage (south of 80°S full-res; 60°S coarse).
- **FR-3 Scenario input** — site, UTC start, duration/step, observer height, elevation masks. Input echoed back with the exact UTC instant used.
- **FR-4 Ephemeris** — Sun and Earth az/el at the site over a time series, with range and angular diameter.
- **FR-5 Horizon** — terrain horizon elevation for azimuth 0–360° at ≤1° resolution, with per-azimuth data-quality flag (covered / edge / missing).
- **FR-6 Visibility** — per timestep: geometric (above 0°), spherical-limb-corrected, terrain-corrected, for Sun and Earth.
- **FR-7 Intervals** — sunlight / dark / Earth-visible / blackout intervals with start/end UTC, boundaries refined to ≤ 1 minute (target ≤ 10 s).
- **FR-8 Metrics** — total and % illuminated, longest continuous darkness, longest continuous Earth blackout, min/max Sun elevation, time-to-next-sunset/Earthset.
- **FR-9 Comparison** — N scenarios in, aligned metric table + per-metric deltas out; any scenario with incomplete data flagged, never silently compared.
- **FR-10 Delay simulator** — baseline scenario + list of day offsets → comparison set.
- **FR-11 Provenance** — every result carries `model_version`, ephemeris source/kernels, DEM product/resolution/frame, time step, assumptions.
- **FR-12 Metric explanations** — each metric has definition, unit, method, source, assumption, limitation (Principle 4), served from a single registry, not hardcoded in the UI.
- **FR-13 Export** — JSON (full) and CSV (tables) of a scenario/comparison (STRETCH).

## 6. Non-functional requirements

| ID | Requirement | Target |
|---|---|---|
| NFR-1 | Single-scenario 30-day timeline, cached DEM | ≤ 5 s |
| NFR-2 | 4-scenario comparison (shared horizon cache) | ≤ 15 s |
| NFR-3 | Reproducibility | Same input + same `model_version` + same data files ⇒ bit-identical JSON (checksums recorded) |
| NFR-4 | Separation | Science engine importable and testable with no web framework |
| NFR-5 | Offline-tolerant | Runtime must not depend on Horizons/PGDA being up; those are used at build/validation/ingest time (cached) |
| NFR-6 | Errors | Typed error codes (invalid input, out-of-coverage, missing data, ephemeris out-of-range); never a silent fallback |
| NFR-7 | Logging | Structured JSON logs with request id and scenario hash |
| NFR-8 | Accessibility | Keyboard-navigable, colour not the only encoding, responsive ≥ 360 px |
| NFR-9 | Licensing | NASA data attribution displayed; no redistribution of multi-GB rasters in repo |
| NFR-10 | Data labelling | Every value labelled **measured / calculated / assumed / illustrative** in API and UI |

## 7. Acceptance criteria (project level)

1. For a stated site/time, Sun and Earth az/el agree with an independent JPL Horizons query to within documented tolerance (target ≤ 0.01° — to be confirmed in Stage 3, which will report the true figure).
2. Horizon profile matches synthetic analytic cases (flat sphere, single wall, curvature-limited) and an independent implementation on real DEM.
3. A Sun position that is geometrically above 0° but below the terrain horizon is reported **not visible**, and tests prove it.
4. Changing date changes intervals; changing site changes horizon and intervals.
5. Delay simulator produces baseline + shifted scenarios with consistent deltas.
6. No output value is hard-coded; no demo data is presented as NASA data; all non-measured values are labelled.
7. Each scientific output has the six Principle-4 fields.
8. End-to-end demo: select site → date → view → add delayed scenario → read difference, in under 2 minutes.
