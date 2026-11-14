# Known limitations (Stage 9, task 11)

One list for the whole project. Each limitation has an ID, what it means for a reader of the results, and where the evidence is. Prefixes: **D** data, **M** method, **P** product. "Effect" is quantified where it was measured; where it was not measured, that is said.

## Data

| ID | Limitation | Effect / what it means | Evidence |
|---|---|---|---|
| L-D1 | The terrain is a LOLA DEM; about 90 % of 5 m pixels (and many 20 m pixels) are interpolated between ground tracks; boulders, the lander body and regolith lofting are not modelled | Horizons are for the *DEM surface*, not for objects on it. The 20 m product's own height-error layer was not downloaded (3.95 GB), so **no per-pixel DEM uncertainty is reported** | `stage2/DEM_AND_KERNEL_VERIFICATION.md` §1 |
| L-D2 | Overview (coarse) windows are area-averaged and under-state narrow ridges | 320 m vs 20 m at IM-2: horizon lower by mean 0.06°, p95 0.33°, max 0.44° (25 % of azimuths by > 0.05°). The engine always prefers the finest window | `stage4/RESOLUTION.md` |
| L-D3 | Only IM-2 has horizon-grade terrain (20 m to 80 km + 320 m to 160 km). IM-1 has 2 km of 20 m data; Chandrayaan-3 has none | IM-1/Chandrayaan-3 are reported **"terrain data insufficient"** with no figures. Extending coverage was deliberately deferred (owner decision) | `stage6/SCENARIO_METHOD.md` §2, `stage7/UI.md` |
| L-D4 | DEM frame is `MOON_ME` (DE421); ephemeris frame is `MOON_ME` (DE440). Their difference is **quoted** by NAIF (≤ 3.07×10⁻⁷ rad ≈ 53 cm on the surface; ≤ 1.8×10⁻⁵°), not measured here; whether PGDA's "DE421 ME" is exactly NAIF's ME421 is unverified | Negligible next to L-D5 (position) but unproven by this project. Using `MOON_PA` instead would be wrong by ~0.029° (875 m) and is never done | `stage2/…` §2, `stage3/EPHEMERIS_METHOD.md` §4a |
| L-D5 | Site coordinates are catalogue values (NASA/JPL NAIF, LROC); their true uncertainty is not published | **The dominant uncertainty of the whole system.** At IM-2 a 100 m position error moves the horizon by up to 1.76° (20 m: 0.11°) and individual grazing event times by up to ~11 h. This is why every result carries a position band | `stage4/RESOLUTION.md`, `stage5/VALIDATION.md` |
| L-D6 | No real data for permanently shadowed regions (no DEM for Shackleton, Haworth, …) | The shadowed-terrain behaviour is tested only on a synthetic crater (Sun and Earth never visible; geometry says Sun up ~50 % of the month). No claim is made about any real PSR | `tests/validation/test_edge_cases.py` |
| L-D7 | The exact pole lies inside the 320 m IM-2 window but in no 20 m window | Horizon there is computed from area-averaged data, most azimuths leave coverage (46/72 truncated at 5° step): results are labelled not certified (`TERRAIN_NOT_CERTIFIED`); scenarios are "terrain data insufficient" | `tests/validation/test_edge_cases.py` (finding of Stage 9) |
| L-D8 | NASA Artemis III candidate regions: names published, **no primary-source centre coordinates located** | Not selectable (decision C7) | `stage2/SITE_CATALOGUE.md` |
| L-D9 | The 60S (120/240 m) products are not registered; horizon beyond the 160 km window is unknown | Rays leaving coverage are flagged `truncated` unless an elevation bound proves them irrelevant (IM-2: all complete; the horizon there is set within 30 km) | `stage4/HORIZON_METHOD.md` §4 |

## Method

| ID | Limitation | Effect | Evidence |
|---|---|---|---|
| L-M1 | **The ephemeris validation is not independent of JPL's ephemerides.** Horizons (DE441) and the engine (DE440) share JPL's lunar and planetary theory and NAIF frames | It catches implementation, frame, convention and time errors; it cannot catch an error in the ephemerides themselves. No non-JPL cross-check (e.g. astropy/ERFA) was run | `stage3/VALIDATION.md` |
| L-M2 | No physically independent dataset exists for the horizon or for visibility (no published IM-2 horizon profile used; no flight data) | The horizon check is an independent *computation* reading the same DEM, so a DEM error appears in both. Visibility is validated analytically, on synthetic terrain with the real ephemeris, by brute-force scan and step convergence — not against measurement | `stage4/VALIDATION.md` §3, `stage5/VALIDATION.md` §3 |
| L-M3 | Validated range 2025-01-01 … 2035-12-31 (kernels cover 1849–2150); UTC after 2017 assumes no further leap second | Outside the range the API refuses; a leap second announced later would break the assumption | `stage3/EPHEMERIS_METHOD.md` |
| L-M4 | Not modelled: gravitational light deflection, Earth oblateness (angular diameter), refraction (none on the Moon) | Deflection ≤ 6×10⁻⁷° over the validation grid | `stage3/VALIDATION.md` |
| L-M5 | Body radii for angular size are IAU 2015 nominal values; observer height defaults to 2.0 m | Assumptions, labelled as such wherever shown | decisions E6, C9 |
| L-M6 | The horizon is made of point rays (0.25° default, 20 m steps); a feature narrower than the ray spacing at range can fall between rays | Measured: max missed obstruction 0.053° at 0.25° (reconstruction takes the higher neighbour) | `stage4/RESOLUTION.md` |
| L-M7 | Visibility events shorter than the sampling step that fall entirely between two samples are not detected | Checked at IM-2: 15-min and 5-min runs find the same events | `stage5/VALIDATION.md` §2 |
| L-M8 | The position-sensitivity band is a **sample of 8 displacement directions**, not a proven bound; it assumes the DEM is correct; sensitivity is computed only where terrain data certify it | A larger displacement could exceed the shown band; the effect is non-linear (±200 m changes Earth results qualitatively) | `stage5/VISIBILITY_METHOD.md` §5 |
| L-M9 | The disc is a circle of the ephemeris angular radius; Sun limb darkening and the partial-disc *fraction of irradiance* are not computed | "any part visible" is a geometric statement | `stage5/VISIBILITY_METHOD.md` §2 |
| L-M10 | **Visibility is geometric line of sight / direct illumination only** — not communication-link availability, not irradiance, not power, not thermal | Nothing in the application should be read as a link budget or energy budget | all UI panels, `stage7/UI.md` |
| L-M11 | The `truncated` test uses a height ceiling taken from the DEM windows the project holds (IM-2: 7.0 km), not a global maximum | A taller unseen peak outside every window could exist | `stage4/HORIZON_METHOD.md` §7 |
| L-M12 | Rankings use position-band overlap (conservative); a paired comparison can separate scenarios that bands do not | Ranks may be "not distinguishable" when a paired delta is distinguishable | `stage6/SCENARIO_METHOD.md` §6 |
| L-M13 | The mission-delay window default (14 d) is an assumption; a window spanning the whole synodic month (29.5 d) hides short delays | Choose the window to match the operation | `stage6/SCENARIO_METHOD.md` §7 |
| L-M14 | SPICE is process-global and not thread-safe; computations are serialised by locks | Fine for the demo; does not scale across threads | `stage3/EPHEMERIS_METHOD.md` |

## Product

| ID | Limitation | Effect |
|---|---|---|
| L-P1 | The first calculation for a new site computes terrain profiles at the site and 8 displaced positions (~60 s); later requests are cached on disk | The UI shows a loading state with an explanation; the default site can be pre-warmed |
| L-P2 | The UI is minimal and read-only (decision C2): no 3D surface, no animation, no saved-scenario browser, no export | by decision; Stage 10 scope |
| L-P3 | **Stage 8 (engineering: solar power, antenna masks, slope, temperature) is not built**; the `engineering` capability is `not_implemented` | no power, link or thermal figure exists anywhere |
| L-P4 | No formal accessibility audit; small-screen charts shrink with the page | landmarks, labels and text alternatives are present |
| L-P5 | Results are verified on one machine/OS (Windows 11, Python 3.12); cross-platform bit-exactness is not claimed (decision S5) | tolerances in `TOLERANCES.md` are the cross-platform contract |
| L-P6 | Headless screenshots cover three UI views; Compare and Delay were verified against real backend JSON and fixtures, not screenshots | `stage7/UI.md` §5 |

## What the validated status means
A capability is `validated` when the project owner approved its stage's evaluation gate after reviewing the evidence in `docs/stageN/VALIDATION.md`. It does **not** mean "proven against measurement": see L-M1 and L-M2 for exactly what independence the evidence has.
