# Numerical tolerances — declared, achieved, and why (Stage 9, task 10)

How to read: **Declared** = the acceptance criterion; "pre-declared" means it was written down *before* the comparison was run (so it could not be fitted to the result). **Achieved** = the measured worst case. **Margin** = declared ÷ achieved. A guard labelled *regression guard* was set after observing a validated result: it detects change, it is not independent truth.

## 1. Ephemeris (Stage 3) — `docs/stage3/VALIDATION.md`, `validation_summary.json`
| Quantity | Declared | Achieved (worst of 220 rows) | Margin | Why this tolerance |
|---|---|---|---|---|
| Sun direction vs JPL Horizons (angular separation) | ≤ 0.01° — pre-declared | 1.35×10⁻⁸° | 7×10⁵ | 0.01° is ~19 arcsec: smaller than the Sun's disc (0.53°) by 50× and 3× smaller than the error a wrong lunar frame (`MOON_PA`) would cause (0.029°), so the check would catch the mistakes that matter |
| Earth direction vs Horizons | ≤ 0.01° — pre-declared | 6.0×10⁻⁷° | 1.7×10⁴ | same; the Earth's disc is 1.9° |
| Range | (reported) | 2.4 m (Sun), 3.7 m (Earth) | — | different DE441 vs DE440 realisation; far below any use |
| Angular diameter | (reported) | 0.0005″ (Sun), 0.042″ (Earth) | — | Earth difference = 6378.1 vs Horizons' implied 6378.137 km equatorial radius (nominal radius assumption) |
| Frame realisation (`MOON_ME` DE440 vs DE421 ME) | (quoted by NAIF) ≤ 3.07×10⁻⁷ rad | ≤ 1.8×10⁻⁵° | — | **quoted from NAIF, not measured here** (limitation L-D4) |
| Regression guards in `tests/engine/test_ephemeris.py` | Sun ≤ 2×10⁻⁷°, Earth ≤ 1×10⁻⁵° | — | — | *regression guard*: ~15× / ~17× above the achieved values, still 10³–10⁵ below the criterion |

Sensitivity of the design choices (`docs/stage3/sensitivity.json`, 4 observers × 6 epochs), i.e. what each shortcut would cost: no light time/aberration 5.8×10⁻³° (Sun); no topocentric parallax 0.269° (Earth); wrong frame `MOON_PA` 0.029°. These justify the model (`LT+S`, surface observer, `MOON_ME`) and are asserted in `tests/validation/test_regression_golden.py`.

## 2. Terrain horizon (Stage 4) — `docs/stage4/VALIDATION.md`, `RESOLUTION.md`
| Quantity | Declared | Achieved | Margin | Why |
|---|---|---|---|---|
| Engine vs independent hand-written implementation (pyproj geodesics + PROJ + GeoTIFF affine + 3-D vectors), 63 azimuths × 3 heights, real IM-2 | ≤ 1×10⁻³° — pre-declared | 1.1×10⁻⁹° | 10⁶ | 10⁻³° ≈ 3.6″ ≪ Sun disc and ≪ the horizon change from a 1 m position error (≈ 0.02°); differences can only be float/ordering noise |
| Flat terrain: horizon = −arccos(R/(R+h)) | 1×10⁻⁴° | < 1×10⁻⁴° | — | sampling step 20 m vs tangent 2.6–42 km: second-order error ≪ tolerance |
| Mesa elevation vs brute-force 3-D vectors | 0.02–0.03° | ≤ 0.0035° expected | — | derived: 20 m ray step at 9.5 km → de/dd ≈ 3×10⁻⁶ rad/m → 0.0035° |
| Curvature vs first-order d/2R | 0.03° | within | — | second-order term at 60 km (d²/R² order) |
| 10 km window ≡ same data inside the 80 km window | exact (byte-identical sub-array) | identical | — | same product, same pixels |
| Azimuth step 0.25° (missed obstruction, conservative max-of-neighbours reconstruction) | informational | max 0.053°, p95 0.023° (vs 0.05° reference) | — | quantifies the sampling choice |
| Radial step 20 m vs 10 m | informational | rms 0.003°, max 0.042° | — | — |
| Regression guards (horizon summary) | 1×10⁻⁶° | exact repeat | — | *regression guard* in `tests/validation/test_regression_golden.py` |

## 3. Visibility (Stage 5) — `docs/stage5/VALIDATION.md`
| Quantity | Declared | Achieved | Why |
|---|---|---|---|
| Transition time localisation | 1 s (bisection on the predicate) | agrees with a 2 s brute-force scan within ≤ 4 s (= scan resolution + bisection) | Methodology §4: never interpolate elevations; 1 s ≪ sample step |
| Step convergence (15 min vs 5 min) | same transitions | identical within 1 s; totals differ ≤ 0.6 s (Sun 0.3 s, Earth 0.6 s) | no sub-step events missed at IM-2 |
| Disc model | 41 azimuth points | — | 41 points across the disc: ≈ 0.013° spacing for the Sun (0.53° disc), ≈ 0.046° for the Earth (1.9° disc) |
| Horizon between samples | max of bracketing samples | cost ≤ 0.05° | chosen so sampling can only increase obstruction |
| Golden IM-2 regression (`tests/validation`) | totals ±4 s, fractions ±1×10⁻⁵, transitions ±1 s, band widths ±60 s — pre-declared before pinning | exact repeat | *regression guards*: ≤ 4 boundaries × 1 s; 60 s ≪ the multi-hour bands they protect |

## 4. Position sensitivity (Stage 5/6)
Assumed position uncertainty ±100 m (user/Stage 2 height-matching tolerance); 8 displacement directions. **A sample, not a bound** (limitation L-M8). Measured effect for IM-2: horizon change up to 1.76° (100 m), 0.11° (20 m); boundary bands up to 11 h (grazing Sun events).

## 5. Terrain data (Stage 2) — `docs/stage2/DEM_AND_KERNEL_VERIFICATION.md`
| Quantity | Declared | Achieved |
|---|---|---|
| DEM height at the lander vs published height | |dz| ≤ 25 m — pre-declared (published values are rounded to 1 m; the lander position is uncertain) | IM-2 +0.89 m; IM-1 +8.03 m (vs NAIF), +12.03 m (vs LROC) |
| Projection vs PROJ on the product's own CRS | 0.1 mm | within |
| Overview = area average | informational | overview pixel 5190.37 m vs 16×16 mean 5189.91 m (nearest-neighbour alternatives 5163 / 5194 m) |
| Bilinear interpolation on an analytic plane | 0.01 m | exact to float32 |
| SPICE kernel integrity | SHA-256 pinned, NAIF MD5 matched | all four match; a one-byte change is refused |

## 6. Time
UTC → ET at J2000 = 64.18392728 s (SPICE); an instant 1 s apart across the 2016-12-31 leap second is 2 s apart in ET; validated range 2025-01-01 ≤ t < 2036-01-01 enforced as a hard error; a leap second inside a requested span is refused. Edge instants (2025-01-01, 2035-12-31 23:59:59, leap day) are tested in `tests/validation/test_edge_cases.py`.

## 7. Numerical precision notes
DEM heights are float32 (resolution ~0.0005 m at 5 km) and computations are float64; the observed repeatability of every result is bit-exact on this machine (asserted). Cross-platform bit-exactness is **not** claimed (decision S5): the tolerances above are the cross-platform contract.
