# Scientific methodology (consolidated)

This is the single-page method statement. Each step has a detailed document with derivations, tolerances and evidence (links in each section). Everything here is implemented in `engine/lunarnav` and covered by tests; claims about validation are exactly those in [stage9/VALIDATION_REPORT.md](stage9/VALIDATION_REPORT.md). **"Validated" in this project means: implemented, tested, evidence reviewed and approved by the project owner. It does not mean proven against measurement.**

## 0. Question answered, and the data class of every number

*For a lunar surface site and a time window: when is the Sun (and Earth) above the local terrain horizon, with what uncertainty from the landing position?* The answer is **geometric line of sight / direct illumination** only: not irradiance, not a link budget, not thermal or power behaviour.

| Data class | Meaning | Example |
|---|---|---|
| `measured, interpolated` | Provider data, gridded between measurements | LOLA DEM heights |
| `calculated` | Derived by the engine from measured inputs and stated assumptions | Sun elevation, horizon, visible fraction, bands |
| `assumption` | A labelled input chosen by the project | Observer height 2.0 m, position uncertainty ±100 m, 14-day delay window, irradiance 1361 W/m² |
| `illustrative` | Built-in examples that are not requirements | Mission profiles, the 1 m² / 0.30 panel example |

## 1. Geometry and frames ([stage2](stage2/), [stage3/EPHEMERIS_METHOD.md](stage3/EPHEMERIS_METHOD.md))
* Moon modelled as a **sphere of radius 1737.4 km** (the LOLA reference); heights are metres above it. Latitude planetocentric (south negative), longitude east-positive.
* Frame **`MOON_ME`** (mean-Earth/polar-axis, DE421 realisation) for observer, ephemeris and DEM. The generic `MOON_PA` frame differs by about 875 m on the surface and is never used with the DEM.
* DEM grid: south-polar stereographic, `x = ρ sin λ`, `y = ρ cos λ`, `ρ = 2R tan((φ+90°)/2)`; the map imagery uses the same grid ([basemap/BASEMAP_ALIGNMENT.md](basemap/BASEMAP_ALIGNMENT.md)).
* Local frame at a site: East/North/Up basis; azimuth clockwise from north; at the exact pole the supplied longitude defines north (decision E4).

## 2. Sun and Earth direction ([stage3](stage3/))
* SPICE (SpiceyPy/CSPICE) `spkcpo` from a surface point, **light-time and stellar aberration** corrected, with JPL **DE440** (`de440s.bsp`), `naif0012.tls`, `moon_pa_de440_200625.bpc`, `moon_de440_250416.tf`. Kernels are SHA-256 pinned and verified at every load.
* UTC → TDB through the leap-second kernel. **Validated range 2025-01-01 to 2035-12-31** (enforced; later times are refused). UTC after 2017 assumes no further leap seconds.
* Output per time: azimuth, elevation (of the body centre), distance, angular diameter.

## 3. Terrain horizon ([stage4/HORIZON_METHOD.md](stage4/HORIZON_METHOD.md))
* For each azimuth (default 0.25° steps) a **great-circle ray** is sampled outward at the finest pixel size; terrain height by bilinear interpolation between pixel centres; the elevation of a terrain point seen from observer radius `R+H_o` is exact on the sphere: `e = atan2((R+H_t)(cos θ − 1) + (H_t − H_o), (R+H_t) sin θ)`. Lunar curvature is therefore included without a correction term. `horizon(az)` = the maximum over the ray.
* Observer height above the DEM surface: **2.0 m default (assumption)**; ground height is the DEM value at the site.
* **Multi-resolution:** each sample uses the finest window that contains it. **Completeness is proven, not assumed:** an azimuth is `complete` only if no unseen terrain beyond the data could rise above the computed horizon, using the highest value in any held DEM window as the ceiling. Otherwise the azimuth is `truncated` and visibility there is flagged as an upper bound.
* Area-averaged overview windows under-estimate peaks; the resolution studies quantify it ([stage4/RESOLUTION.md](stage4/RESOLUTION.md), [stage4/CHANDRAYAAN3_TERRAIN.md](stage4/CHANDRAYAAN3_TERRAIN.md)).

## 4. Visibility ([stage5/VISIBILITY_METHOD.md](stage5/VISIBILITY_METHOD.md))
* The Sun is a **disc** (41 sample points over its angular radius); three states per time step: centre above the horizon, **any part** above, **whole disc** above. Headlines: **Sun = any part** (direct illumination), **Earth = disc centre** (antenna pointing). A body is blocked when its elevation is below the horizon at its azimuth (the **larger of the two bracketing azimuth samples**, never more optimistic).
* Time series at a fixed step (default 15 min); every state **transition is refined by bisection to 1 s**. Events shorter than the step that fall between two samples are not detected (checked: 15- and 5-minute runs agree at IM-2).
* Intervals touching the window edge are **open** (flagged "cut off": the true length is at least what is shown). Both **geometric** (local horizontal, no terrain) and **terrain-corrected** results are always given.
* Metrics: visible fraction, total visible time, number of intervals, longest visible and longest not-visible interval (closed-only and including open).

## 5. Position uncertainty ([stage5](stage5/), [stage6](stage6/))
* Landing position is uncertain (default ±100 m, configurable, always > 0). Every banded result is recomputed with the observer displaced to **8 positions on a circle of that radius**; the **band** is the extreme across nominal and displaced runs. This is a **sensitivity to the input position**: a sample of displacements, **not a proven bound and not an error bar** (limitation L-M8).
* Event times carry their own band (earliest/latest across runs); totals and fractions are the robust headline. A band can be wide where a result changes sharply with position (e.g. at ±500 m the IM-2 Sun band spans 0–50 %).
* Differences between scenarios use **paired** bands for the same site (same displacement in both) and **independent** interval arithmetic for different sites; "not distinguishable" is reported when a band includes zero.

## 6. Scenarios, comparison, delay ([stage6/SCENARIO_METHOD.md](stage6/SCENARIO_METHOD.md))
* A scenario is (site or point, start, length, step, observer height, position uncertainty, azimuth step). Its **id is a SHA-256 of the inputs, the model version and the DEM checksums**; results are cached under it and are byte-reproducible.
* **A scenario is `supported` only if the horizon is complete at the nominal and every displaced position.** Otherwise it is `terrain_data_insufficient`: a reason, no numbers, no rank. IM-1 and uncovered points are in this class.
* Rankings cover supported scenarios only and say when neighbours are not distinguishable. The **delay simulator** shifts the whole window by each offset (default window 14 days, an assumption; a window spanning a whole synodic month hides short delays) and reports paired deltas.

## 7. Idealised solar-energy upper bound ([stage8/SOLAR_ENERGY.md](stage8/SOLAR_ENERGY.md))
`E = η · A · I · t`, with `t` the Sun's any-part visible time from the scenario result (reused, not recomputed), user-supplied panel area A and efficiency η, irradiance I = 1361 W/m² (an assumption). It assumes a sun-tracking panel and counts a partly visible Sun as fully illuminating; the energy band is the visible-time band scaled. **It is an upper bound on direct-beam energy, not a power budget or battery state.**

## 8. Validation evidence ([stage9/VALIDATION_REPORT.md](stage9/VALIDATION_REPORT.md), [TEST_AND_VALIDATION.md](TEST_AND_VALIDATION.md))
| Check | Result | Criterion |
|---|---|---|
| Ephemeris vs JPL Horizons (220 rows, 2025–2035) | Sun 1.4×10⁻⁸°, Earth 6×10⁻⁷° | 0.01° |
| Horizon vs independent implementation (IM-2, 80 km window) | 1.1×10⁻⁹° | 10⁻³° |
| Flat-terrain, constant-height and tangent-distance analytic cases | pass (tolerance 10⁻⁴°) | analytic |
| Transitions vs brute-force 1 s scan | agree to within the stated 1 s | 1 s |
| Imagery vs LOLA DEM registration (display only) | ≈0.1–0.2 km | context only |
| Golden-regression and edge-case suites | 8 + 42 tests pass | exact / documented |

**Independence caveat:** Horizons shares JPL's ephemerides, so that check validates the *implementation*, not the ephemerides (limitation L-M1). No physically independent horizon or visibility dataset exists for these sites; the horizon check is against a separately written implementation.

## 9. What is not modelled
Gravitational light bending (≤ 6×10⁻⁷°), Earth oblateness effects on the Earth disc, boulders and the lander body, regolith lofting, DEM height uncertainty (per-pixel errors are not propagated), permanently shadowed region maps, link budgets, irradiance, thermal and power systems, antenna masks, slope/aspect/roughness. Full list with effects: [stage9/KNOWN_LIMITATIONS.md](stage9/KNOWN_LIMITATIONS.md).
