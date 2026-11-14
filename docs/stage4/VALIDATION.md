# Stage 4 — Horizon validation evidence

Status: `horizon` capability = `validated` (gate approved by the project owner; decision M1, `docs/stage9/`). "Validated" here means: implemented, tested, evidence reviewed and approved - **not** proven against measurement; see `docs/stage9/KNOWN_LIMITATIONS.md` (L-M1, L-M2).

## 1. Synthetic terrain (analytic / independently computed truth) — `tests/engine/test_horizon.py`
| Gate item | Test | Result |
|---|---|---|
| Flat terrain | flat DEM at h = 2, 50, 500 m: horizon = −arccos(R/(R+h)) at every azimuth (tol 1e-4°), limiting sample at the tangent distance; constant-height terrain = concentric sphere; observer on the surface → limit −θ₁/2 (≈ 0) | pass |
| Obstructed terrain | flat-top mesa placed with pyproj spherical geodesics at 6 bearings (0…333°): peak at the independent bearing (±0.5° = step), elevation vs brute-force 3-D vectors (±0.02°), angular width = 2·asin(r/d), nearer/taller → higher, off-axis azimuths = flat dip | pass |
| Lunar curvature | 2 km mesa at 60 km: > 0.5° below the planar atan, equals planar − d/2R (±0.03°) and exact 3-D value; a 100 m hill at 60 km is correctly hidden below the curvature horizon | pass |
| Observer height | h = 0, 5, 50 m: peak vs independent 3-D (±0.03°), clear-sky dip = −arccos(R/(R+h)) (±2e-3°), peak elevation decreases with height; height is relative to the DEM surface at the site | pass |
| Edge cases | NoData skipped/counted/flagged, never filled; observer on NoData / outside coverage / northern hemisphere → typed error; truncation provable vs not; user range cap = truncated; fine-window NoData not filled from coarse window; pole observer follows the E4 convention; azimuth wrap; bad parameters name the field; determinism; nested-window dropping; cache memory→disk→invalidation→corruption | pass |

## 2. Independent implementation on real LOLA data — `scripts/validate_horizon.py`
Pre-declared criterion (before running): |engine − reference| ≤ 1e-3°. The reference uses pyproj spherical geodesics, PROJ's stereographic, the GeoTIFF's own affine transform, a separate bilinear and 3-D vector elevation; no shared code.
IM-2 Athena, window `im2_20m_r80km` (8000×8000 @ 20 m), 63 azimuths (15° grid + 40 random 0.25° azimuths):

| Observer height | max \|diff\| | rms | max limiting-distance diff | horizon range |
|---|---|---|---|
| 0 m | 1.1e-9° | 2.7e-10° | 0.000 km | −1.39…3.98° |
| 2 m | 3.4e-11° | 1.1e-11° | 0.000 km | −1.42…3.98° |
| 30 m | 1.1e-11° | 2.2e-12° | 0.000 km | −1.53…3.87° |

Margin to the criterion ≈ 10⁶. Also tested: the 10 km window is byte-identical to the corresponding sub-array of the 80 km window.

## 3. What this does NOT show
* It validates geometry, azimuth convention, curvature, indexing and interpolation. It does **not** validate the DEM, and there is no physically independent horizon dataset for IM-2 in hand (no published horizon profile was found/used). "Validate against an independently computed terrain profile where possible" is met in the sense of an independent *computation*, not an independent *measurement*.
* The reference reads the same GeoTIFF values, so a DEM error would appear in both.
