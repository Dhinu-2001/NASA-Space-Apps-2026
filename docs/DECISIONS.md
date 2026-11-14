# Decision Log

Approved by project lead on Stage 0 review (before Stage 1). Authoritative over `docs/stage0/` where they differ.

| ID | Decision |
|---|---|
| C1 | Mission Delay Simulator is mandatory MVP. |
| C2 | Minimal read-only UI is built **after Stage 5** (site, UTC time, Sun/Earth az/el, horizon profile, terrain-corrected visibility, sunlight + Earth timelines). Must not compromise engine/API verification. Full UI remains Stage 7. |
| C3 | Validation happens inside every stage; Stage 9 consolidates evidence. |
| C4 | Frontend only displays/animates backend az/el; never computes astronomy or visibility. |
| C5 | Scenarios = reproducible JSON + on-disk result cache. No database in MVP. |
| C6 | Local-horizontal, spherical-limb and terrain horizons stay distinct in code and UI. |
| C7 | Curated sites only with reliable primary-source coordinates. |
| C8 | Validated operational range 2025-01-01 → 2035-12-31; distinguished from wider kernel coverage. |
| C9 | Default observer height 2.0 m, labelled as an assumption, user-editable. |
| C10 | Prior ChatGPT research = idea source, not authority. |
| C11 | Deterministic exact-pole azimuth convention (Methodology §2) with tests at exact pole and near-pole **before** implementation is considered complete. |
| E1 | Local SPICE (SpiceyPy, DE440) is the engine; Horizons is validation only. DE421 (DEM frame) vs DE440 (ephemeris/orientation) must be treated as non-interchangeable: establish and document the transformation, validate vs Horizons, record kernel/frame info in provenance. |
| E2 | Disk visibility defined in Methodology §6 (centre / any-part / fully). |
| S1 | Start terrain work with a small DEM window; never download whole multi-GB DEMs. |
| S2 | Verify DEM CRS, datum, pixel size, frame before scientific use. |
| S3 | Performance targets are measured acceptance criteria, not assumptions. |
| S4 | Record input checksums, model version, kernel versions, parameters, assumptions. |
| S5 | If bit-identical cross-platform output is impractical: deterministic serialization + documented numerical tolerances. |
| S6 | Never substitute synthetic/illustrative data for real NASA data without clear labelling. |
| S7 | Never silently fall back to geometric visibility when terrain data is missing: return explicit error or incomplete-data status. |
| G1 | Do not commit DEMs or generated datasets to Git. |
| D1 | Deadline: Sunday 2026-11-15 23:59 IST. Scientific correctness is not traded for speed. |
| E3 | (Stage 3) Observer apparent direction = SPICE `spkcpo` from a surface point fixed in `MOON_ME`, `LT+S`; the local ENU basis is built from the site, not from SPICE. Observer offset is never neglected (Earth would be wrong by 0.27°). `MOON_PA` is never used. |
| E4 | (Stage 3) **Refinement of C11 / Methodology §2 pole tie-break:** at lat = ±90° the supplied longitude defines north (limit along that meridian); identical to "lon = 0 meridian" when lon = 0. Verified vs Horizons at both poles (lon 0, 123, 270) and by continuity tests. |
| E5 | (Stage 3) C8 enforced as a hard error: times outside 2025-01-01 ≤ t < 2036-01-01 return `EPHEMERIS_OUT_OF_RANGE`. |
| E6 | (Stage 3) Body radii for angular diameter are IAU 2015 nominal values (Sun 695 700 km, Earth equatorial 6378.1 km), recorded as assumptions in provenance. |
| E7 | (Stage 3) Stage 3 acceptance criterion pre-declared before results: angular separation vs Horizons ≤ 0.01° on every row (PRD). `ephemeris` capability stays `implemented_unvalidated` until the user approves the gate. |
| E8 | (Stage 3) Horizons reference values are recorded once into a small tracked fixture (`data/validation/`) so tests are offline and reproducible; the fixture is re-fetchable with `scripts/fetch_horizons_reference.py`. |
