# Stage 3 — Validation against JPL Horizons

Reproduce: `scripts/fetch_horizons_reference.py` (records the oracle; needs network) → `data/validation/horizons_stage3_reference.json` (tracked) → `scripts/validate_ephemeris.py` (offline) and `tests/engine/test_ephemeris.py::test_agrees_with_horizons_reference_grid`. Raw summary: `validation_summary.json`; sensitivity: `sensitivity.json`.

## Oracle and request
JPL Horizons API (`ssd.jpl.nasa.gov/api/horizons.api`, API v1.2), observer `CENTER='coord@301'`, `COORD_TYPE='GEODETIC'`, `SITE_COORD='lonE,lat,alt_km'`, `QUANTITIES='4,13,20'` (apparent az/el, angular diameter, range), `APPARENT='AIRLESS'`, `EXTRA_PREC='YES'`, UT calendar-string epochs. Horizons uses DE441 and the `MEAN_ME` frame; the engine uses DE440 and `MOON_ME`. Retrieved 2026-11-14 (timestamp stored in the fixture).

## Grid (220 rows)
11 observers × 10 epochs × {Sun, Earth}. Observers (validation test points, **not** landing-site claims except the three catalogue sites): IM-2 (also with a 5321 m observer height), IM-1, Chandrayaan-3, **exact south pole at lon 0 and lon 123°, exact north pole at lon 270°**, 0.1° from the south pole, equator nearside (Earth near zenith), equator farside (Earth below horizon), 45°N / −100°E. Epochs: whole-second UTC from 2025-01-01 to 2035-12-31 23:00:00, including a leap day (2028-02-29 23:59:59).

## Pre-declared criterion (fixed before any result was examined)
Angular separation between the engine's and Horizons' direction ≤ **0.01°** for every row (PRD target). Angular separation (haversine on the sky) is used rather than separate az/el errors because azimuth error is meaningless near the zenith/pole. Additional regression guards were set afterwards from the observed values with ≈ 15× margin and are labelled as such in the test.

## Results — PASS
| | Sun (110 rows) | Earth (110 rows) |
|---|---|---|
| Max angular separation | **1.4e-8°** | **6.0e-7°** |
| RMS angular separation | 7.5e-9° | 4.3e-7° |
| Max elevation difference | 1.3e-8° | 4.4e-7° |
| Max azimuth difference (any elevation) | 1.8e-8° | 6.6e-6° (near zenith, equator nearside) |
| Max range difference | 2.4 m (1.6e-11 rel.) | 3.7 m (9.6e-9 rel.) |
| Max angular-diameter difference | 0.0005″ | 0.042″ |
| Radius implied by Horizons | 695 700.0 km | 6378.137 km (engine uses nominal 6378.1) |
| Margin to the 0.01° criterion | ≈ 7×10⁵ | ≈ 1.7×10⁴ |

All 22 (observer, body) pairs, including both exact poles at non-zero longitude, sit at the same level (Sun 1.3e-8°, Earth 6.0e-7°), i.e. the residual does not depend on location, height, hemisphere or epoch. A wrong frame would not hide: `MOON_PA` would shift directions by ≈ 0.029° (`sensitivity.json`).

## What this validates — and what it does not
Validated: UTC/leap-second handling, the observer definition and height handling, the local ENU construction and azimuth convention (including the pole tie-break), light-time and stellar-aberration treatment, the choice of `MOON_ME`, topocentric geometry, range and angular-diameter formulae.

**Not independent of JPL's ephemerides.** Horizons and SPICE both derive from the same JPL DE-series ephemerides and NAIF lunar frame definitions (DE441 vs DE440 here), so this comparison cannot detect an error in the ephemerides themselves; it detects implementation, frame, convention and time errors. A second, non-JPL reference (e.g. an astropy/ERFA lunar-frame calculation) has not been run.

Not validated: epochs outside 2025–2035 (rejected by the API); the exact tie of PGDA's "DE421 ME" to NAIF's ME421 frame (the residual of ≤ 1.8e-5° is quoted from NAIF, not measured); gravitational light deflection (not modelled; the residual shows its effect is ≤ 6e-7° in this grid); Earth oblateness; sensitivity to leap seconds scheduled after the kernel's last entry.

## Physical-sanity tests (independent of Horizons) in `tests/engine/test_ephemeris.py`
Sun elevation at the south pole stays within ±1.6° over a year (lunar axial tilt 1.54°); Sun azimuth at 89°S makes one monotonic ≈ 360° rotation per ≈ synodic month; the equatorial Sun passes through > 85° elevation each month; antipodal sites see opposite Sun elevations within the 2R/d parallax bound; Earth stays > 70° at the sub-Earth point and < −70° at its antipode; Earth at the pole stays within the libration bound (|el| < 8.5°) and dips below the horizon; ranges, light time (= range/c) and angular diameters lie within bounds derived from orbital geometry (not fitted); results change with time and with location; series are deterministic; observer height has an effect within the parallax bound.

Two of those bounds were first written wrongly by me (an antipodal-parallax estimate off by a factor of ~30, and the Moon–Sun distance bound that ignored the Earth–Moon offset); the engine was right and the test expectations were corrected from derived geometry, not fitted to the output.
