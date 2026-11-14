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
| H1 | (Stage 4) Horizon = max over great-circle ray samples of the exact spherical elevation `atan2((R+Ht)cosθ−(R+Ho), (R+Ht)sinθ)`; bilinear DEM lookup identical to Stage 2; no floor/smoothing; curvature is exact, not a correction term. |
| H2 | (Stage 4) Observer radius = DEM height at the site (not the catalogue height) + observer height above the surface; default 2.0 m per C9, reported in every response as an assumption. |
| H3 | (Stage 4) Multi-resolution: finest window containing a sample wins; NoData is never filled from a coarser window; redundant nested windows are dropped (S7). |
| H4 | (Stage 4) `truncated` = terrain beyond DEM coverage could still raise the horizon, decided by an explicit elevation bound using a stated height ceiling = highest value in any window the project holds (data-derived, not a global guarantee). `data_gap` = NoData met. Both mean "lower bound". |
| H5 | (Stage 4) Independent check criterion pre-declared before running: ≤ 1e-3° vs a hand-written implementation (pyproj geodesics, PROJ projection, GeoTIFF affine, 3-D vectors). It validates geometry/indexing/interpolation, not the DEM; `horizon` stays `implemented_unvalidated` until user approval. |
| H6 | (Stage 4, user instruction) 20 m DEM fetched out to 80 km around IM-2 at native resolution (no resampling), as window `im2_20m_r80km`; fetch is checkpointed/resumable; file not committed (G1), manifest tracked. |
| H7 | (Stage 4) Stage 0 limb-dip figure corrected: h = 2 m dips 0.087° (not 0.05°). |
| H8 | (Stage 4) Horizon cache key includes every DEM window SHA-256, all parameters, the height ceiling and the algorithm version; disk entries are git-ignored and never trusted if unreadable. |
| J1 | (Stage 5, user instruction) Every visibility result carries a position-sensitivity band (default ±100 m, configurable `position_uncertainty_m`, 0 disables) attached to each interval boundary, each metric and each step — not a separate report. Labelled `data_class: calculated` with the stated assumption; it is a sensitivity to the INPUT position, not an error bar on the astronomy/terrain. Computed only where terrain data support it (IM-2); never extrapolated to IM-1 / Chandrayaan-3. |
| J2 | (Stage 5) Sensitivity = full recomputation at `n_directions` (default 8) positions on a circle; boundary band = [earliest, latest] of the nearest same-type event within ±12 h; `complete=false` if a displaced run lacks the event. A sample, not a bound. |
| J3 | (Stage 5) Data-support rule: sensitivity requires zero `truncated`/`data_gap` azimuths at the nominal and every displaced position; else `not_computed` + reason. |
| J4 | (Stage 5) Disc model: circle of ephemeris angular radius, 41 azimuth points; horizon between samples = max of the two bracketing samples (never over-states visibility). Headline Sun = any-part, Earth = centre (E2). |
| J5 | (Stage 5) Transitions by bisection on the predicate to 1 s; intervals tile the window; open intervals excluded from `*_closed_only` extrema and flagged when they tie or lead. Window ends at the last sample. |
| J6 | (Stage 5) Steps with an incomplete horizon are `unverified_visible`; the body block reports `visibility_is_upper_bound`. |
| J7 | (Stage 5, user instruction) `ephemeris` and `horizon` are `validated` (user approved those gates); `visibility` stays `implemented_unvalidated` until approved. |
| K1 | (Stage 6, user instruction) Only sites whose terrain data support a position-sensitivity figure are compared/ranked (currently IM-2). Others are `terrain_data_insufficient`: reason, no numbers, never ranked, scored, estimated or shown with an upper-bound stand-in; an insufficient baseline gives no deltas. |
| K2 | (Stage 6, user instruction) Geometric and terrain-corrected results appear together in every scenario, delta and delay-table row. |
| K3 | (Stage 6, user instruction) Position bands carry into deltas: paired per displacement for the same site (one shared position error), interval arithmetic for different sites (independent errors, conservative). |
| K4 | (Stage 6, user instruction) Totals/fractions are the headline; event timestamps always carry their band; open intervals are flagged and any extremum/delta involving one is marked as a lower bound. |
| K5 | (Stage 6) Scenario id = SHA-256(canonical definition + model version + DEM fingerprint); label excluded; results cached as JSON in data/results/scenarios (C5; no database); stale model versions never served. |
| K6 | (Stage 6) Scenario `position_uncertainty_m` must be > 0 so that sensitivity cannot be silently dropped. |
| K7 | (Stage 6) Rankings: supported only; `distinguishable_from_next` true only if adjacent position bands do not overlap. |
| K8 | (Stage 6) Delay simulator default window 14 days, an assumption (about one lunar day), labelled; a 29.5-day window hides short delays. `visibility` capability set to validated (Stage 5 approved); `scenarios` stays implemented_unvalidated. |
| L1 | (Stage 7, user instruction) Minimal read-only UI (C2): site, UTC time, Sun/Earth az/el, horizon profile, terrain-corrected visibility, timelines, plus compare/delay/data-and-assumptions views. No 3D, no animation. |
| L2 | (Stage 7, C4) The frontend only displays backend numbers; its only trigonometry is the orientation-map layout and its only date arithmetic is chart-axis placement. Audited by grep (docs/stage7/UI.md). |
| L3 | (Stage 7, user instruction) Every number that carries a position band shows the band (or says 'not computed'); event times show earliest-latest and width; incomplete bands are marked; differences state whether they are distinguishable from zero. |
| L4 | (Stage 7, user instruction) Sites without terrain support render as 'Terrain data insufficient' with the reason and no figure, bar, rank or placeholder, in Compare, Delay and the single-site view. |
| L5 | (Stage 7, user instruction) Capability status is displayed from the backend (strip + per-panel tags); the UI never presents anything as more validated than its status. |
| L6 | (Stage 7, user decision) Extending the 20 m DEM to IM-1 is future work, not attempted: IM-1 stays 'terrain data insufficient'. The 14-day delay window default is confirmed. The Stage 6 gate was approved with the Stage 7 go-ahead, so `scenarios` is now `validated` (J7/K8 updated by this entry). |
| M1 | (Stage 8, user instruction) `sites` and `dem` capabilities set to `validated`: the owner reviewed Stages 2-7 independently and had no corrections. Stage 8 is deliberately narrow (solar energy availability derived from Stage 5/6 outputs only), time-boxed against the 2026-11-15 23:59 IST deadline. |
| N1 | (Stage 9, user instruction) Stage 8 (engineering) is deferred, not cancelled; Stage 9 (validation consolidation) and final polish take priority before the 2026-11-15 23:59 IST deadline; a narrow Stage 8 (solar estimate from the existing visibility fraction) only if time remains. |
| N2 | (Stage 9) `validated` means implemented, tested, evidence reviewed and approved by the owner; it is NOT 'proven against measurement'. This definition is stated in the UI About tab, README and docs/stage9. |
| N3 | (Stage 9) Every visibility/scenario result carries a deterministic `provenance` block (model version, kernel and DEM SHA-256, frame, aberration, horizon algorithm version, all parameters, no timestamps); `GET /provenance` reports what the running application is built from and degrades gracefully on a partial install. Web-layer package versions are added in the API, never in the engine. |
| N4 | (Stage 9) Defect fixed: a missing/modified SPICE kernel is `DATA_MISSING`; only DEM-field data errors make a scenario `terrain_data_insufficient`. |
| N5 | (Stage 9) Golden-value regression tests are labelled regression guards (read from the validated engine), with tolerances declared before pinning; independent evidence is re-asserted from the recorded Stage 3/4 summaries. |
| N6 | (Stage 9) Finding recorded as a limitation (L-D7): the exact south pole is covered only by the 320 m IM-2 window; it is flagged not certified, never treated as a result. |
