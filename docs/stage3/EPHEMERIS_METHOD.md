# Stage 3 — Ephemeris method and assumptions

Status: implemented and validated against JPL Horizons (see `VALIDATION.md`); `ephemeris` capability = `validated` (gate approved by the project owner; decision M1, `docs/stage9/`). "Validated" here means: implemented, tested, evidence reviewed and approved - **not** proven against measurement; see `docs/stage9/KNOWN_LIMITATIONS.md` (L-M1, L-M2).

## 1. What is computed
For an observer fixed on the lunar surface and a UTC instant: apparent azimuth, elevation, range, light time and angular diameter of the **Sun centre** and **Earth centre** (geocentre, NAIF 399). Nothing is looked up from a table or fixed; every value is evaluated from the pinned DE440 kernels at request time.

## 2. Calculation chain (code: `engine/lunarnav/ephemeris.py`, `frames.py`)

1. **UTC → ET (TDB).** Strict ISO-8601 UTC parsing (explicit `Z`/`+00:00`; naive or offset times are rejected). `str2et` with `naif0012.tls`. Checked against J2000 (64.18392728 s) and the 2016-12-31 leap second (instants 1 s apart in UTC are 2 s apart in ET) in `test_utc_to_et_known_values`.
2. **Observer.** Position in `MOON_ME`: `r = (R + h)·(cos φ cos λ, cos φ sin λ, sin φ)`, R = 1737.4 km (the LOLA/Horizons reference sphere), φ planetocentric latitude, λ east longitude, h height above the sphere (default 0 m).
3. **Apparent topocentric vector.** `spkcpo(target, et, 'MOON_ME', 'OBSERVER', 'LT+S', r, 'MOON', 'MOON_ME')` — state of the target as seen from a point fixed in the Moon-fixed frame, with **light time and stellar aberration** (observer velocity = Moon orbital velocity + surface rotation). Output vector in `MOON_ME`.
4. **Local frame.** East/North/Up unit vectors are built from the site itself (not from SPICE): `east = (−sin λ, cos λ, 0)`, `up = r̂`, `north = up × east`.
5. **Az/El.** `az = atan2(v·E, v·N) mod 360` (clockwise from north), `el = asin(v·U/|v|)`; range = `|v|`.
6. **Angular diameter.** `2·asin(Rbody/range)`.

Kernels (pinned by SHA-256, verified at load; a mismatch refuses to run): `naif0012.tls`, `de440s.bsp`, `moon_pa_de440_200625.bpc`, `moon_de440_250416.tf`. The engine asserts at load that `MOON_ME` resolves to NAIF id 31001 (the DE421-aligned alias) and never uses `MOON_PA` (id 31000, ≈ 875 m / 0.029° off the DEM frame).

## 3. Conventions
| Item | Convention |
|---|---|
| Frame | `MOON_ME` (same as LOLA DEM and Horizons) |
| Latitude / longitude | planetocentric, south negative / east positive; custom input 0–360 E normalised to −180…180 |
| Azimuth | clockwise from local north, [0, 360) |
| Elevation | above the local horizontal plane (⟂ local radial) |
| Units | degrees, kilometres, seconds; times ISO-8601 UTC `Z` |
| **Pole tie-break (decision E4, refines C11/Methodology §2)** | At lat = ±90° the **supplied longitude** defines north (limit along that meridian). For lon = 0 this is exactly "the lon = 0 meridian defines north". Az/El are continuous toward the pole. Verified against Horizons at both poles, lon = 0, 123, 270 |

## 4. Assumptions and limitations (all surfaced in `provenance`)
1. **Airless** — no refraction (the Moon has no atmosphere of consequence).
2. **Gravitational light deflection is not modelled** (SPICE does not apply it). Horizons does; the residual is ≤ 6e-7° in the validated grid.
3. **Body radii are nominal** (IAU 2015 B3: Sun 695 700 km, Earth equatorial 6378.1 km). Angular diameter is therefore an *assumption-based* quantity; Horizons implies Earth 6378.137 km, i.e. 0.04″ difference. Earth oblateness is ignored; the Sun/Earth discs are treated as circles.
4. **Centres only.** Sun/Earth directions are disc centres; the disc-visibility states (centre / any-part / fully) are defined in Methodology §6 and built in Stage 5.
5. **Observer height** is an input (above the reference sphere). Default 0 m; the Stage 5 observer will use DEM height + observer height. Effect of 5.3 km: ≤ 8e-4° on Earth, negligible on Sun.
6. **UTC after the last known leap second.** `naif0012.tls` ends at 2017-01-01 (TAI−UTC = 37 s). Future UTC assumes no further leap second (as Horizons states). A leap second inside a requested span would break uniform stepping; the series refuses in that case (a check, though none is expected in the validated range).
7. **Validated range 2025-01-01 → 2035-12-31 inclusive (C8).** Outside it the API returns `EPHEMERIS_OUT_OF_RANGE`, although the kernels cover 1849–2150. Extending the range requires extending the Horizons comparison.
8. **Frame realisation.** `MOON_ME` in the DE440 FK is an alias of `MOON_ME_DE440_ME421`, which differs from DE421's ME by ≤ 3.07e-7 rad (≈ 1.8e-5°, ≈ 53 cm on the surface, 2000–2040; NAIF). Whether PGDA's LOLA "DE421 ME" is *exactly* NAIF's ME421 is not independently verified (Stage 2 finding, unchanged).
9. **SPICE is process-global and not thread-safe:** all calls are serialised by a lock. Fine for MVP; a multi-process deployment needs one engine per process.

## 4a. Why topocentric, light time and aberration (measured, `sensitivity.json`)
Maximum change in the direction if the corresponding choice were dropped or wrong (4 observers × 6 epochs):

| Variation | Sun | Earth |
|---|---|---|
| No light time / aberration (`NONE`) | 5.8e-3° (21″) | 2.0e-4° |
| Light time only (no stellar aberration) | 5.8e-3° | 5.4e-3° (19.6″) |
| Observer at Moon centre (no topocentric parallax) | 6.8e-4° | **0.269°** |
| **Wrong frame `MOON_PA`** for the same lat/lon | 2.8e-2° | 2.9e-2° |
| NAIF-quoted MOON_ME vs DE421 ME | ≤ 1.8e-5° | ≤ 1.8e-5° |

Dropping parallax would make Earth wrong by a quarter of a degree; using `MOON_PA` would exceed the 0.01° criterion by ~3× — which is why the Horizons comparison can detect a frame mistake.

## 5. Errors (no fallbacks)
| Situation | Result |
|---|---|
| Naive/offset/malformed time | `INVALID_INPUT` (field `start_utc`/`end_utc`/`time_utc`) |
| Time outside the validated range | `EPHEMERIS_OUT_OF_RANGE` |
| Kernel or manifest missing, or checksum mismatch | `DATA_MISSING` (503) with the rebuild command |
| Bad lat/lon/height/bodies/step; > 50 000 samples | `INVALID_INPUT` |

## 6. API (see `docs/API_CONTRACT.md`)
`POST /ephemeris/series` (site id or custom lat/lon, `start_utc`, `end_utc`, `step_seconds` ≥ 1 s, bodies), `GET /ephemeris/position` (single instant, `body=sun|earth|both`). Columnar JSON, `data_class: calculated`, full provenance (kernel names + SHA-256, frame, aberration, constants, assumptions).

## 7. Performance (measured on the dev machine, Windows 11)
Kernel verify + load 0.08 s. Series: 2 881 samples × 2 bodies (30 d @ 15 min) 0.38 s; 43 201 samples (30 d @ 1 min) 5.9 s; ≈ 0.135 ms per sample-pair. Over HTTP a 30-day 15-min series took 0.40 s (607 kB JSON).
