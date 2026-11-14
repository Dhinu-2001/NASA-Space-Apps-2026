# 02 — Scientific Methodology (planned; to be validated stage by stage)

Stage 0 deliverable. Everything here is a **plan** and is marked UNVALIDATED until the stage that tests it passes.

## 1. Calculation chain

```
UTC instant ──► ET/TDB (SPICE, leap-seconds kernel)
                 │
Sun/Earth state in J2000/ICRF (SPK DE440) ─► light-time + stellar aberration (LT+S)
                 │
Rotate into Moon body-fixed frame (MOON_ME, from PCK moon_pa_de440 + FK) 
                 │
Subtract observer position (lat, lon, height on reference sphere R = 1737.4 km)
                 │
Rotate into local topocentric ENU frame at observer
                 │
azimuth/elevation (+ range, angular diameter)
                 │
Compare with terrain horizon h(az) from DEM  ──►  visible / not visible
```

## 2. Coordinate conventions (the contract for all modules)

| Item | Convention | Reason |
|---|---|---|
| Body & frame | Moon, **MOON_ME** (Mean Earth/polar axis) | Same frame as LOLA PGDA products and used by Horizons (`MEAN_ME (high precision)` confirmed in a live query) |
| Latitude | Planetocentric, degrees, south negative; Moon treated as sphere R = 1737.4 km (LOLA/Horizons reference) | Moon's flattening is negligible (~0.0003) relative to terrain relief; geodetic ≡ planetocentric on a sphere |
| Longitude | **East-positive**, stored −180…180 (accept 0…360, normalise) | IAU/LRO convention; Horizons labels `E-lon` |
| Height | Metres above the 1737.4 km reference sphere (LOLA convention); observer height is **above local DEM surface** | Matches LOLA heights |
| Azimuth | Degrees **clockwise from local north** (north = direction toward the lunar north pole along the local meridian), 0–360 | Horizons-compatible. **Tie-break** at exactly lat = ±90°: meridian of lon = 0 defines north; documented and tested. *Stage 3 refinement (decision E4): the supplied longitude defines north (limit along that meridian), identical for lon = 0; verified against Horizons at both poles.* |
| Elevation | Degrees above the local horizontal plane (perpendicular to the local sphere normal), −90…90 | |
| DEM grid | **South polar stereographic**, metres, MOON_ME (read exact CRS parameters/true-scale latitude from the GeoTIFF; do **not** assume) | PGDA states "south polar stereographic X/Y in meters, MOON_ME, DE421" |
| Time | UTC in, UTC out, ISO-8601 with `Z`; internal TDB seconds past J2000; display timezone UTC only in MVP | Explicit, no local-time ambiguity |

Rule: no array crosses a frame boundary without a named transformation function with a unit test.

## 3. Ephemeris approach — decision

| Option | Pros | Cons |
|---|---|---|
| A. JPL Horizons API at runtime | Authoritative, no kernels | Network dependency, latency/limits, awkward for thousands of epochs × many scenarios, future UTC/leap-second handling outside our control |
| **B. Local SPICE (SpiceyPy) with DE440 kernels** | Offline, fast, vectorisable, deterministic, reproducible, same underlying JPL ephemeris | Must manage kernels; lunar orientation kernel pairing must be right |
| C. Hand-rolled analytic (Meeus, etc.) | No dependencies | Not accurate enough for libration/south-pole geometry; violates "authentic JPL" intent |

**Decision (proposed): B as the engine, A as the independent validation oracle.** We verified (2026-11-14) that Horizons accepts a lunar surface observer:
`CENTER='coord@301'`, `COORD_TYPE='GEODETIC'`, `SITE_COORD='lon_E,lat,alt_km'`, `QUANTITIES='4'` returns apparent az/el, airless (no refraction), DE441, MEAN_ME frame. Stage 3 compares B against A at a grid of sites/epochs and publishes the actual residuals.

SPICE kernel set (to be confirmed in Stage 3): `de440s.bsp` (31 MB; Sun, Earth, Moon), `moon_pa_de440_200625.bpc` (12 MB) + matching `moon_de440_*.tf` frame kernel (NAIF lists a newer 250416 version — pick and pin one, record its checksum), a leap-seconds kernel (`naif0012.tls` or current), `pck` for radii if needed.

Apparent vs. astrometric: Horizons `a-app` applies light-time, aberration, light bending. We use SPICE `LT+S` and record any residual difference; light-bending by the Sun on Earth's direction is negligible for the Moon-Earth geometry but will be measured, not assumed.

**Libration and orbital variations are inherently included** because we rotate real Earth/Sun vectors with the real lunar orientation (PCK). No separate libration model is needed for MVP; this resolves the "advanced libration modelling" item in Priority C for free.

## 4. Time

- Input UTC → `str2et`. Future UTC after the next announced leap second assumes no leap second (same caveat Horizons states); flagged in provenance.
- Never assume a 24 h lunar day. Relevant natural periods (for default window sizes, not for computation): synodic month ≈ 29.53 d (Sun azimuth cycle at the pole), sidereal ≈ 27.32 d, Earth libration periods ≈ 27 d. Default timeline window: 30 d.
- Step: default 15 min for timelines; interval boundaries refined by bisection on the visibility predicate to ≤ 1 s numerical (output rounded to 1 s). Step vs. event-miss risk: Sun elevation margin changes slowly at the pole, but terrain horizon varies rapidly with azimuth, so bisection on the *predicate* — not interpolation of elevation — is used; a minimum-step sensitivity test is part of Stage 5.

## 5. Terrain horizon

Definitions (resolves ambiguity C6):
- **Local-horizontal (0°)**: plane ⟂ surface normal. "Astronomical" sunrise = Sun centre crosses 0°.
- **Spherical-limb horizon**: for observer height *h* over smooth sphere R, the limb dips by `δ = arccos(R/(R+h)) ≈ sqrt(2h/R)`. For h = 2 m this is ≈ 0.087° (0.19° at 10 m, 0.43° at 50 m) — small but implemented and tested. *(Stage 0 originally said ≈ 0.05°, which was wrong; corrected in Stage 4.)*
- **Terrain horizon** `h_t(az)` = maximum elevation angle of any DEM point along the ray, including curvature.

Algorithm (Stage 4): for each azimuth, sample the great-circle path outward from the observer. For a terrain point at great-circle angular distance θ = d/R and height H_t above the reference sphere, with observer at radius R+H_o:

```
elev = atan2( (R+H_t)·cosθ − (R+H_o),  (R+H_t)·sinθ )
h_t(az) = max over samples (elev), also ≥ spherical-limb dip if all terrain below it
```
This is exact on a sphere and handles curvature automatically (no flat-earth approximation). Sampling step ≈ DEM pixel size (≤ 1 px), nearest/bilinear interpolation documented; range limited by DEM coverage with a **multi-resolution** strategy: 20 m (or finer) near field, coarser product (60S 120/240 m) far field, because distant massifs (tens to hundreds of km) can set the horizon. Per-azimuth flag: `complete` (ray reached the limb-limited range), `truncated` (hit DEM edge — result is a lower bound), `missing`.

Known limitations to surface in UI: ~90 % of 5 m pixels are interpolated between LOLA tracks (PGDA); LDEM_..._ERR and EFFRES products exist and will be exposed; unmodelled objects (boulders, lander body, regolith lofting) are not included; DEM height uncertainty is typically decimetres to metres but sensitivity of illumination at 1 m vs 5 m height is large (Barker et al.), so **observer height is a first-class input**.

## 6. Visibility logic

Per timestep, body *b* ∈ {Sun, Earth}:
- `geometric = elev_center > 0°`
- `limb_corrected = elev_center > −δ(h)` (reported separately)
- `terrain_visible = elev_center > h_t(az)` — **centre-point** criterion for the Sun and Earth in MVP
- **Disk visibility definition (decided at Stage 1, per approval condition; implemented in Stage 5).** Sun (≈ 0.53°) and Earth (≈ 1.9°; 6806″ observed in live query) are extended discs, with angular radius from the ephemeris range. The engine computes **three** states per timestep and always labels which one a metric uses:
  - `centre_visible`: disc centre elevation > h_t(az_centre).
  - `any_part_visible`: the disc's upper limb exceeds the terrain horizon anywhere across the disc's azimuth span, i.e. some part of the disc is in view (disc approximated as a circle on the sky; terrain sampled across its azimuth span).
  - `fully_visible`: the entire disc is above the terrain horizon.
  - **Headline Sun/sunlight metric = `any_part_visible`** (any direct illumination reaches the observer), with `partial` periods reported separately and a `fully_visible` total alongside.
  - **Headline Earth metric = `centre_visible`** (antenna pointing is at the disc centre), with `any_part` and `fully` reported alongside. This is geometric line of sight, not link availability.
  - *Stage 5 implemented this (docs/stage5/VISIBILITY_METHOD.md): disc = circle of the ephemeris angular radius sampled at 41 azimuth points; horizon between samples = max of bracketing samples; every headline result carries a position-sensitivity band (user requirement).*
  - Limitation: partial-disc *fraction* of illumination is not computed in MVP (visible fraction ≠ irradiance ratio without limb-darkening/area integration).
- Operational communication (B2) adds an antenna elevation mask: `comm_geometric = terrain_visible AND elev > mask`. Never labelled "link available".

Metrics from boolean series: intervals by edge detection, refined by bisection; longest run of False (darkness/blackout); totals and fractions; time-to-next transition from any query instant. Edge handling: intervals touching the window boundary are marked `open_start`/`open_end` and excluded from "longest" claims unless flagged, so truncation is never presented as a true duration.

## 7. Solar power (STRETCH, B1)

`P = η · A · I · max(0, cos θ)` with I = solar constant scaled by 1/r² using the ephemeris Sun distance (confirmed available as `delta`, AU), θ from panel normal and Sun vector. Panel parameters must be user-provided or shown as labelled example presets; no hidden defaults. Output title: "idealised direct-beam electrical output", never "battery state".

## 8. Uncertainty and provenance (what we record, not invent)

`model_version`, git commit, kernel file names + SHA-256, DEM product name + SHA-256 + pixel size + CRS, time step, observer height, masks, bisection tolerance, date generated. Quality indicators only where derivable: DEM ERR/EFFRES values at the site, horizon truncation flags. **No** blanket "accuracy %" anywhere.

## 9. Known scientific risks to be quantified, not assumed
1. DEM tied to MOON_ME **DE421**; ephemeris from **DE440**. Offset between the two MOON_ME realisations is expected to be small, but we will measure its effect on azimuth at the pole (Stage 3/4). *Stage 3 result: NAIF-quoted ME vs DE421-ME rotation ≤ 3.07e-7 rad ⇒ ≤ 1.8e-5° in any direction (quoted, not independently measured); using `MOON_PA` instead would shift directions by ≈ 0.029° — see `docs/stage3/EPHEMERIS_METHOD.md` §4a.*
2. Azimuth sensitivity near the pole: small lateral errors → large azimuth changes; horizon varies sharply with azimuth.
3. Centre-vs-disk visibility at Sun elevations ≲ 1.5°.
4. DEM interpolation under permanently shadowed terrain (no direct sunlight data ⇒ topography from altimetry only, which is fine for geometry, but we show it is interpolated).
