# Stage 5 — Validation evidence and IM-2 results

Status: `visibility` capability = `validated` (gate approved by the project owner; decision M1, `docs/stage9/`). "Validated" here means: implemented, tested, evidence reviewed and approved - **not** proven against measurement; see `docs/stage9/KNOWN_LIMITATIONS.md` (L-M1, L-M2).

## 1. Gate items → tests (`tests/engine/test_visibility.py`, `tests/api/test_api_stage5.py`)
| Gate item | Evidence |
|---|---|
| Sun visibility responds to terrain | **Real SPICE ephemeris over a synthetic DEM**: flat terrain reproduces `elevation + radius > −dip` exactly; a 1.5 km mesa (≥ 10° high) placed on a body's azimuth blocks it at every step inside the shadow and leaves every step outside the mesa's span identical to the flat run; a mesa on the Earth's mean azimuth leaves < 20 % of the flat-run Earth visibility. Also analytic disc-vs-wall unit tests (centre / any-part / fully, wall edge, wrap through north, near zenith). |
| Earth visibility responds to terrain | same test (Earth block) |
| Geometric ≠ terrain-corrected | synthetic mesa (geometric-visible but terrain-blocked steps > 0) and real IM-2 (Sun: 155 of 1537 geometrically-lit steps blocked by terrain) |
| Timeline transitions validated | every refined IM-2 transition (Sun and Earth, 19-day window) agrees with a **2 s brute-force scan** of the same predicate within 4 s; the bisection unit test localises a known step to ≤ 0.5 s; 15-min vs 5-min runs give identical transitions (≤ 1 s) |
| Continuous intervals correct | analytic interval/metric tests incl. open start/end, closed-only extrema, tie with an open interval; intervals tile the window exactly; totals vs step counts within the event resolution |
| Reproducible | identical JSON on repeat runs |
| Position sensitivity | present on every headline result (per boundary, per metric, per step); nominal inside its band; band configurable (0 disables, 20 m < 100 m); IM-1 → `not_computed` with reason; no-DEM site → error; labelled `calculated` with the ±100 m assumption |

## 2. IM-2 Athena, 2027-01-15 + 30 d, 15-min steps, observer 2.0 m (default assumption), ±100 m, 8 directions
Source: `scripts/visibility_study.py` → `im2_study.json`. All numbers are for this site and window only.

| | Sun (any part of disc) | Earth (disc centre) |
|---|---|---|
| Visible fraction (nominal) | 48.6 % (350 h) | 80.8 % (581 h) |
| Band under ±100 m | 45.4 – 48.9 % (327 – 352 h) | 80.0 – 80.9 % (576 – 582 h) |
| Visible intervals (nominal / band) | 3 / 2–3 | 2 / 2 |
| Longest not-visible interval | 15.4 d (closed) | 5.8 d (closed) |
| Largest boundary band | **11.1 h** | **5.8 h** |
| Horizon change at the body's azimuth | up to 1.76° | up to 0.48° |
| Steps whose state could flip | 3.5 % | 0.9 % |
| Terrain-blocked (geometrically up) steps | 155 | 0 |
| Horizon complete | all steps | all steps |

Events (UTC, nominal): Earth sets 2027-01-27 11:00:46 (band 0.65 h), Earth rises 2027-02-02 05:33:24 (band 5.8 h); Sun sets 2027-01-28 08:58:55, re-appears 09:01:24 for 14 min until 09:15:33 (all three of those bands are marked incomplete: in some displaced runs the re-appearance does not exist, and one displaced run puts the sunset 11 h earlier); Sun rises 2027-02-12 18:57:35 (band 0.52 h, complete).

**Reading the numbers.** Near the horizon the Sun and Earth move slowly in elevation, so a small change of horizon height shifts a crossing time by hours. The band is therefore very wide exactly where the geometry is grazing and tight where the body crosses the horizon steeply (the Sun-rise on 12 Feb). Fractions and totals are robust to a few percent; individual grazing event times are not.

### Band sweep (same window)
| Position band | Sun: largest boundary band | Sun: complete / boundaries | Sun: total-visible band | Earth: largest boundary band | Earth: total-visible band |
|---|---|---|---|---|---|
| ±20 m | 2.7 h | 3 / 4 | 348.7 – 351.4 h | 0.41 h | 581.2 – 581.7 h |
| ±50 m | 3.7 h | 3 / 4 | 348.0 – 351.7 h | 0.57 h | 581.1 – 582.0 h |
| ±100 m | 11.1 h | 1 / 4 | 327.2 – 352.4 h | 5.8 h | 576.1 – 582.4 h |
| ±200 m | 11.4 h | 1 / 4 (2 extra events) | 281.9 – 352.3 h | 3.3 h (0 of 2 complete, 2 extra events) | 471.5 – 583.6 h |

At ±200 m the Earth result changes qualitatively in some displaced runs (extra events appear): the sensitivity is not linear and grows quickly past ~100 m at this site.

### Step convergence
15-min and 5-min runs: Sun total 1 260 929.0 s vs 1 260 929.3 s; Earth 2 093 241.8 s vs 2 093 241.2 s; all transitions equal to within 1 s. No sub-step event was missed in this window.

## 3. What this does NOT show
* No physically independent visibility dataset exists for IM-2 in hand; validation is analytic/synthetic, internal consistency (brute-force scan, step convergence) and the validated Stage 3/4 components.
* The position band is a sample of 8 displacements, not a bound; it assumes the DEM is right.
* One site and one window; other sites/dates will differ. IM-1 has no horizon-grade terrain and Chandrayaan-3 has none; neither receives a sensitivity figure.
* Visibility ≠ link availability ≠ irradiance.
