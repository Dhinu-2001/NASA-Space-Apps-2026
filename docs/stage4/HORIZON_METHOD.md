# Stage 4 — Terrain horizon method

Status: implemented; `horizon` capability = `validated` (gate approved by the project owner; decision M1, `docs/stage9/`). "Validated" here means: implemented, tested, evidence reviewed and approved - **not** proven against measurement; see `docs/stage9/KNOWN_LIMITATIONS.md` (L-M1, L-M2).
Code: `engine/lunarnav/horizon.py` (science), `api/lunarnav_api/routes_horizon.py` (HTTP only).
Evidence: [VALIDATION.md](VALIDATION.md), [RESOLUTION.md](RESOLUTION.md).

## 1. What a horizon profile is

For an observer at a lunar site, `horizon(az)` is the highest elevation angle, above the observer's **local horizontal
plane**, of any DEM terrain along the great-circle ray leaving the observer at azimuth `az`. A Sun or Earth centre
is blocked by terrain when its elevation is below `horizon(az)` at its azimuth. **This stage produces the
profile only.** Combining it with Sun/Earth directions is Stage 5; nothing here is a visibility claim.

## 2. Frames, conventions, observer

| Item | Definition |
|---|---|
| Body, frame | Moon, `MOON_ME`; sphere R = 1737.4 km (LOLA reference) |
| DEM grid | South-polar stereographic, `x = 2R·py/(1−pz)`, `y = 2R·px/(1−pz)` for a unit vector p in MOON_ME — algebraically identical to the verified Stage 2 grid (`x = ρ sin λ`, `y = ρ cos λ`, `ρ = 2R tan((φ+90°)/2)`), valid on the whole southern sphere, no trigonometry in the hot loop. Tested against `lonlat_to_xy` and against PROJ's own `+proj=stere`. |
| Heights | Metres above the 1737.4 km sphere (LOLA). |
| Local frame | The Stage 3 East/North/Up basis built from the site's latitude and longitude (`frames.enu_basis`), including the pole tie-break (decision E4: the supplied longitude defines north). |
| Azimuth | Degrees clockwise from local north, 0 ≤ az < 360; the ray direction is `t = cos(az)·N + sin(az)·E`. |
| Observer | Radius `R + H_o`, `H_o = H_ground + h`. `H_ground` is the bilinear DEM height **at the site** (the catalogue height is reported alongside but is not used); `h` is the observer height above the DEM surface (default **2.0 m — an assumption, decision C9**, reported as such in every response). |

## 3. Algorithm

1. Ray point at great-circle angle θ: `p(θ) = û cos θ + t sin θ` (û = local up). Samples at `d = k·Δ`, `θ = d/R`, `k = 1…N`.
2. Project `p` to the grid (above), read the height `H_t` by **bilinear interpolation between pixel centres** (same convention and same arithmetic as the Stage 2 point lookup; tested to be identical).
3. Elevation of that terrain point, exact on the sphere:

   `e = atan2( (R+H_t)·cos θ − (R+H_o) , (R+H_t)·sin θ )`

   evaluated as `(R+H_t)(cos θ − 1) + (H_t − H_o)` in the numerator to avoid cancellation at small θ. **Lunar curvature is therefore exact, with no separate correction term**; tests compare it with the classical `d/2R` approximation and with independent 3-D vector geometry.
4. `horizon(az) = max_k e_k`, plus the distance, pixel size and window of the limiting sample. No floor, no smoothing.

Defaults: azimuth step 0.25° (1440 rays), radial step = finest pixel size (20 m), range = DEM coverage (rays stop where coverage ends).

## 4. Multi-resolution and missing data (decision S7)

* Windows are ordered finest-first. A sample uses the **finest window that contains it**. A window wholly contained in a window of equal or finer resolution is dropped.
* **NoData is never filled**, and a NoData sample in a fine window is **not** replaced by the coarser window's value. NoData samples are skipped, counted (`n_missing_samples`), and the azimuth gets `data_gap = true` (its horizon is a lower bound).
* **Coverage end.** Where a ray leaves all DEM coverage, `range_covered_km` records how far data exist. Terrain beyond is unknown, so the azimuth is `truncated` **unless a bound proves it cannot matter**:
  `unseen_bound_deg` is the highest elevation any terrain beyond the edge could reach if it is no higher than `H_max`, where `H_max` is the **highest value in any DEM window the project holds** (a data-derived ceiling, *not* a global guarantee; it is returned in `provenance.parameters.unseen_terrain_max_height_m`). For `H_max ≥ H_o` the elevation of a fixed-height point falls monotonically with distance, so the bound is its value at the edge; for `H_max < H_o` it is the tangent value `−arccos((R+H_max)/(R+H_o))` until the tangent distance. An azimuth is `complete` only if `unseen_bound_deg ≤ horizon`.
* No DEM at the site → `OUT_OF_DEM_COVERAGE`; NoData at the site → `DATA_MISSING`. Neither falls back to flat or synthetic terrain.

## 5. Caching (task 10)

`HorizonService` keeps an in-memory LRU and an on-disk cache (`data/results/horizon/<key>.npz`, git-ignored, regenerable).
Key = SHA-256 of {algorithm version, the SHA-256 of every DEM window used, observer, azimuth/radial step, range, `H_max` ceiling}.
Any change of input, of a single DEM byte, or of the algorithm version changes the key, so a stale profile can never be served.
Unreadable or mismatching disk entries are ignored and recomputed. The cache is reported per response (`served_from`).
Computation is serialised with a lock (shared cache state and lazily-loaded windows).

## 6. API

`GET /horizon/profile?site_id=…|lat=…&lon=…[&observer_height_m=2.0][&az_step_deg=0.25][&step_m=][&max_range_km=][&use_cache=true]`
Columnar JSON: `azimuth_deg`, `horizon_elevation_deg` (null where no valid sample — never 0), `horizon_distance_km`,
`limiting_pixel_size_m`, `range_covered_km`, `n_missing_samples`, `unseen_bound_deg`, `truncated`, `data_gap`, a `summary`,
`units`, `notes`, and `provenance` (algorithm version, observer incl. ground height, parameters, every window with SHA-256 and source URL).
Stage 5 can call `HorizonProfile.horizon_at(az)` (linear) or `max_between(az0, az1)` (never under-estimates across a disc's azimuth span).

## 7. Assumptions and limitations

1. **DEM, not reality.** About 90 % of 5 m LOLA pixels are interpolated between ground tracks (PGDA). Boulders, the lander body, regolith lofting and sub-pixel relief are not modelled.
2. **Overview windows are area-averaged** and under-state narrow ridges and peaks ([RESOLUTION.md](RESOLUTION.md) measures this).
3. **Point rays.** A feature narrower than the ray spacing at long range can fall between rays; the azimuth-step study quantifies the loss.
4. **Observer position.** Site coordinates are catalogue values (LROC/NAIF); the horizon moves with position error ([RESOLUTION.md](RESOLUTION.md)).
5. **`truncated` depends on a data-derived height ceiling**, not a global maximum; a taller unseen peak could exist outside every window.
6. **Geometric only:** no atmosphere (none on the Moon), no refraction; horizon of the terrain *surface point*, not of the Sun's limb.
7. **Single-observer, static.** Observer height above the surface is constant over azimuth.

## 8. Correction to Stage 0 (Methodology §5)

Stage 0 stated the limb dip for `h = 2 m` is "≈ 0.05°". The correct value is `arccos(R/(R+h)) ≈ √(2h/R)` = **0.087°** (and 0.19° at 10 m, 0.43° at 50 m). The Stage 4 flat-terrain tests assert the correct value; the note in `docs/stage0/02_Scientific_Methodology.md` has been corrected.
