# Stage 6 — Scenarios, comparison and the mission delay simulator

Status: implemented; the Stage 6 gate was approved by the user (with the Stage 7 go-ahead), so `scenarios` is now `validated`, as are `ephemeris`, `horizon` and `visibility`.
Code: `engine/lunarnav/scenarios.py` (logic), `api/lunarnav_api/routes_scenarios.py` (HTTP only). Evidence: [VALIDATION.md](VALIDATION.md).

**Scope.** Comparison of geometric line of sight / direct illumination of the Sun and Earth between sites and dates. It is not link availability, irradiance, thermal or power, and it compares only what the terrain data support.

## 1. Scenario data model
A scenario = `site` (catalogue id or lat/lon) + `start_utc` + `duration_days` (≤ 60) + `step_seconds` + `observer_height_m` (default **2.0 m, an assumption, C9**, flagged in the result) + `position_uncertainty_m` (default 100, **must be > 0**: a scenario result always carries its position sensitivity) + `n_directions` + `az_step_deg`.
Identity (decision C5): `id` = SHA-256 of the canonical definition + `MODEL_VERSION` + a fingerprint of the DEM windows. Same inputs ⇒ same id; a changed model or DEM ⇒ new id. The label is not part of the identity. Results are cached as JSON in `data/results/scenarios/<id>.json` (git-ignored, regenerable; a stale model version or unreadable file is never served) and retrievable by `GET /scenarios/{id}`. No database. *(Saved scenarios: implemented as this C5 file cache; say if you want a different persistence.)*

## 2. Data support — the rule that governs everything (user instruction)
A scenario is `supported` only if its terrain data support a position-sensitivity figure (Stage 5 rule J3: complete horizon at the nominal and every displaced position). Otherwise it is **`terrain_data_insufficient`**: it carries the reason and **no numbers** — no fraction, no interval, no geometric figure, no "estimated" column, no upper-bound stand-in. Such scenarios are listed under `excluded_terrain_data_insufficient`, are not in any delta, and are not in any ranking. Currently IM-2 (both the landing position and the intended target) is supported; IM-1 (2 km of 20 m data, every azimuth truncated) is not. (Written at Stage 6 with Chandrayaan-3 listed as having no DEM; since 2026-11-15 it has a 60 m window and is supported - see `stage4/CHANDRAYAAN3_TERRAIN.md`.) If the baseline scenario is insufficient, no deltas are formed.

## 3. What every supported scenario contains
For Sun (headline any-part) and Earth (headline centre):
* **`terrain_corrected`** — total visible time and fraction (nominal + position band), count, longest visible / not-visible interval (`closed_only`, `including_open`, `includes_open_interval`, bands), **events** (becomes visible / not visible) each with its **position band** `{earliest, latest, width, complete}`, the intervals with their bands, open-interval counts.
* **`geometric`** — the same quantities against the local horizontal (no terrain), always alongside, so the terrain effect is visible in every comparison. Marked `position_sensitivity: not_applicable` (terrain-independent).
* **`terrain_effect`** — blocked-by-terrain step counts and `visible_s_terrain_minus_geometric` (nominal + band). Negative: terrain removes light the geometry allows (IM-2 Sun). Positive: the terrain horizon dips below the local horizontal and adds visibility (IM-2 Earth, a high plateau).
* **`completeness`** — as Stage 5.

Totals and fractions are the robust headline (stable to a few percent under the band). Event timestamps are never given without their band.

## 4. Deltas carry the position band
`delta = scenario − baseline` for total visible time, visible fraction, interval count, longest visible and longest not-visible interval, for the terrain-corrected result (with band) and the geometric result (exact, no band), plus a mechanical sentence.
* **Same site** (delay simulator, date comparison at one site): the position error is one physical offset shared by both dates, so the band is formed **per displacement** — the difference of the two scenarios at the nominal position and at each displaced position, then min/max (`delta_band_method: paired`). Consequence seen at IM-2: a one-day delay costs the Sun *exactly* 1/14 of a 14-day window with a zero-width band, even though the absolute fraction is uncertain by ±3.5 % — the position error cancels in the difference.
* **Different sites**: independent position errors ⇒ interval arithmetic of the two bands, `[b_lo − a_hi, b_hi − a_lo]` (`independent_interval_arithmetic`), conservative.
* `distinguishable_from_zero` is true only if the band excludes zero; otherwise the sentence says "NOT distinguishable from zero given ±N m position uncertainty". A zero-width zero band reads "no difference at the nominal or any sampled displaced position".

## 5. Open intervals
An interval touching the window edge is cut off; its true length is at least the observed one. `longest_*` carry `closed_only` (open excluded), `including_open` and `includes_open_interval` (also true when an open interval ties or leads). A delta of a longest-interval metric uses the `including_open` values and is flagged `involves_open_interval` (and its sentence says the value is a lower bound). Totals are exact within the window and are not affected.

## 6. Rankings
Per criterion (Sun visible fraction, Earth visible fraction — higher is better; Sun longest darkness, Earth longest blackout — lower is better), **supported scenarios only**, ordered by nominal value. `distinguishable_from_next` is true only if the position bands of adjacent ranks do not overlap (conservative: band overlap, not paired). Fewer than two supported scenarios ⇒ no ranking.

## 7. Mission delay simulator
`POST /scenarios/delay`: baseline start + `offsets_days` (1…10 distinct values in (0, 365]). Each delay is the same window shifted by the offset. Output: baseline, each delayed scenario, deltas vs baseline (paired, both geometric and terrain-corrected, with bands), a `summary_table` (terrain-corrected and geometric fraction and longest not-visible interval per offset), rankings. **Default window 14 days — an assumption (about one lunar day of operations), not a mission requirement.** A window that spans a whole synodic month (29.5 d) hides short delays: totals repeat (IM-2, 30 d: delays of 1, 3 and 7 days give identical totals), so only event times move; use a window matching the operation.

## 8. API
`POST /scenarios/evaluate` · `GET /scenarios/{id}` · `POST /scenarios/compare` (explicit `scenarios`, or `sites` × `start_utc_list`; `baseline_index`) · `POST /scenarios/delay`. At most 12 scenarios per comparison. Errors: `INVALID_INPUT` (field named), `NOT_FOUND` 404 (unknown saved id), `EPHEMERIS_OUT_OF_RANGE`.
Performance (IM-2): a new site's first scenario computes 9 horizon profiles (≈ 60 s, then cached); further dates at that site ≈ 5–8 s each; 8 scenarios ≈ 80 s uncached.

## 9. Limitations
Everything in Stage 5 applies (geometric only; position band is an 8-direction sample, not a bound; DEM assumed correct; events shorter than the step not detected). Rankings and deltas are only as good as the DEM and the catalogue positions. Only IM-2 is comparable today, so a "site comparison" currently means the IM-2 landing position vs the pre-landing target (≈ 0.37 km apart).
