# Stage 5 — Visibility, intervals and position sensitivity

Status: implemented, **unvalidated until the Stage 5 gate is approved** (`visibility` = `implemented_unvalidated`).
`ephemeris` and `horizon` are `validated` (user-approved gates, Stages 3 and 4).
Code: `engine/lunarnav/visibility.py` (science), `api/lunarnav_api/routes_visibility.py` (HTTP only).
Evidence: [VALIDATION.md](VALIDATION.md).

**Scope.** Geometric line of sight / direct illumination of the Sun and Earth centre/disc against the DEM terrain horizon. It is **not** link availability, irradiance, thermal or power. Terrain and astronomy are exact for their inputs; the only input treated as uncertain here is the observer **position**.

## 1. Inputs combined
* Stage 3 ephemeris: apparent azimuth/elevation and angular diameter of each body at the observer (`LT+S`, `MOON_ME`).
* Stage 4 horizon profile at the observer (default 0.25° azimuth step; observer height above the DEM surface, **default 2.0 m is an assumption, decision C9**, reported in every response). The ephemeris observer uses the DEM ground height + observer height.

## 2. Three states per body and time (decision E2)
| State | Meaning |
|---|---|
| `centre_visible` | disc-centre elevation > horizon at the centre azimuth |
| `any_part_visible` | some part of the disc is above the horizon |
| `fully_visible` | the whole disc is above the horizon |

**Headline: Sun = `any_part_visible`; Earth = `centre_visible`.** All three are always returned and each metric names its state. `partially_visible = any ∧ ¬fully`.
Disc model: a circle of the ephemeris angular radius ρ; at azimuth offset `d = t·ρ/cos(el)` (t ∈ [−1,1], 41 points, clamped to ±180°) it spans `el ± ρ√(1−t²)`. Between horizon samples the horizon is read as the **maximum of the two bracketing samples**, so sampling can only make the result more obstructed — never over-state visibility (costs ≤ 0.05° at 0.25°).

**Geometric vs terrain-corrected** are both returned (`geometric_headline_above_local_horizontal` vs `headline_visible`). They differ in both directions: terrain removes light the geometry allows (e.g. Sun blocked 155 of 1537 geometrically-lit 15-min steps at IM-2), and at a high plateau whose terrain drops below the local horizontal the terrain-corrected body can be visible slightly *below* geometric 0° (IM-2: horizon down to −1.5°; Earth 105 such steps).

## 3. Transitions, intervals, metrics
* A transition is a change of the **state predicate** between two samples; its time is found by **bisection on the predicate** (ephemeris + horizon re-evaluated at each probe), to 1 s; reported rounded to the second (Methodology §4: never interpolate elevations).
* Intervals tile the window exactly; those touching the window edge carry `open_start` / `open_end`. The window ends at the **last sample** (reported).
* Metrics: total visible time and fraction, count, longest visible and longest not-visible interval — each as `*_closed_only` (open intervals excluded) and `*_including_open`, with a flag when an open interval ties or leads (then the extremum is unsettled, since the true length is at least the observed one).
* Limitation: an event shorter than the sampling step that falls entirely between samples is not seen. Checked at IM-2: 15-min and 5-min runs find identical transitions (≤ 1 s).

## 4. Incomplete terrain (decision S7)
Each step carries `horizon_complete`: false if any horizon sample the disc spans is `truncated` or `data_gap` (Stage 4). A step that looks visible there is `unverified_visible` (the horizon is a lower bound, so "visible" is an **upper bound**); the body block reports `visibility_is_upper_bound`. IM-2 is complete everywhere; IM-1 is not (2 km of 20 m data).

## 5. Position sensitivity (user requirement, Stage 5 approval)
Every headline result is recomputed with the observer displaced by the assumed uncertainty (**default ±100 m, configurable 0…5000 m, `position_uncertainty_m`**) in `n_directions` (default 8; 4…72) compass directions on a circle — full recomputation (ephemeris, horizon at the displaced point, states, boundary bisection) with the same ephemeris and DEM.
It is attached to each result, not reported separately:
* **per interval boundary** — `start_band` / `end_band` `{earliest_utc, latest_utc, width_s, complete}`: earliest/latest over the nominal and displaced runs of the nearest same-type event within ±12 h. `complete=false` means some displaced run has no matching event (the event may not exist at a shifted position);
* **per metric** — `metric_bands` (total visible time, fraction, count, longest closed intervals), plus `events_only_in_displaced_runs`;
* **per time step** — `position_sensitivity_deg` (max change of the horizon at the body's azimuth) and `headline_state_robust_to_position`.
Label: `data_class: "calculated"`, `assumption: "observer position uncertain by ±100 m"`, `kind: "sensitivity of the result to the INPUT observer position; not an error bar on the astronomy or terrain calculation"`.

**Where it applies.** Only where the terrain data support it: the nominal **and every displaced** horizon must have no `truncated`/`data_gap` azimuths, and displaced points must have DEM data. Otherwise `position_sensitivity.status = "not_computed"` with the reason (IM-1: insufficient coverage; Chandrayaan-3: no DEM, an error). Nothing is extrapolated.
**Limits.** A sample of displacements on a circle, not a proven bound (an arbitrary displacement could exceed the 8-direction spread); assumes the DEM is correct; the 100 m default reuses the Stage 2 height-matching tolerance.

## 6. API (`/visibility/*`)
* `POST /visibility/series` — everything incl. per-step arrays (≤ 20 000 samples).
* `POST /visibility/intervals` — intervals/transitions/metrics without arrays; `bodies:["sun"]` = solar visibility API, `["earth"]` = Earth visibility API.
* `GET /visibility/at` — one instant with per-step state and sensitivity.
Request fields: `site` (id or lat/lon), `start_utc`, `end_utc`, `step_seconds`, `observer_height_m`, `bodies`, `position_uncertainty_m`, `n_directions`, `refine`, `include_series`, `az_step_deg`.
Performance (IM-2, 30 d @ 15 min, 8 displaced runs): ≈ 7 s with cached horizons (dominated by SPICE); the first call also computes 9 horizon profiles (≈ 60 s; cached on disk afterwards).
