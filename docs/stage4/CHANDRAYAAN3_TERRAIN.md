# Chandrayaan-3 terrain coverage (added 2026-11-15, owner-authorised, 90-minute time-box)

Status: **registered, verified, working — NOT approved as a validation gate.** Every Chandrayaan-3 result carries the line "Terrain window ch3_60m_r200km (LDEM_60S_60MPP_ADJ, 60 m pixels) is registered but NOT yet approved as a validation gate…" in its limitations, and the window's provenance carries `validation_status`. No capability status changed; IM-1 was not touched. Decision R1.

## 1. Product choice
The PGDA landing page (https://pgda.gsfc.nasa.gov/products/90) lists three 60S LDEM products. All three were header-read over HTTP range requests (no bulk download) and all cover 69.3741 S, 32.32 E:

| Product | Grid | Nearest-pixel height at the site |
|---|---|---|
| LDEM_60S_240MPP_ADJ | 7760², 240 m | 529.3 m |
| LDEM_60S_120MPP_ADJ | 15520², 120 m | 527.7 m |
| LDEM_60S_60MPP_ADJ | 31040², 60 m | 528.8 m (bilinear 529.34 m) |

`LDEM_75S_30MPP_ADJ` does not reach the site (limit 75 S). **Chosen: 60 m.** The request was the coarsest *usable* product. Usable was judged with the provider's own layers for the 60 m product at the site: effective resolution (EFFRES) 32 m at the site and median 52 m within ±3 km (p10 25 m, p90 160 m), height error 0.30 m at the site (median 0.61 m). A 120 m or 240 m grid is coarser than the data's stated resolution at the site and discards real terrain information; 60 m matches it. The resolution study (§4) quantifies this.

## 2. Verification (recorded in `data/manifests/dem_products.json`)
* **Header:** GTiff (Cloud-Optimized), float32, 1 band, 60 m, bounds ±931 200 m, NaN no-data, 512² blocks, overviews 2–64, deflate.
* **CRS:** the WKT is string-identical to the already-verified 80S product (Moon 2015 sphere 1 737 400 m, south-polar stereographic, latitude of origin −90). pyproj on the file CRS and the project's own formula agree to < 1e-9 m (x = 338 051.934 m, y = 534 332.237 m).
* **Frame:** PGDA page 90 states the MOON_ME / DE421 frame once for "all TIF files" on the page. **Not independently tested for this product**; the file carries no frame metadata. The caveat is the same as for the 80S product, and the 80S product's two-site height test does not transfer.
* **Height check:** engine value at the site 529.34 m (bilinear) against the published 532 m (LROC image page 1314): −2.66 m, and 532 m lies inside the 525.7–533.4 m span of the surrounding 5×5 pixels. **The datum match for the published figure is unverified** (`sites.json`: LROC's datum is only *assumed* to be the LOLA sphere), and the published coordinates have ~3 m resolution (0.0001°). This is a plausibility check at one site, not a validation.

## 3. Window radius (derived the way the IM-2 extent was reasoned)
Terrain beyond the horizon-limiting distance cannot be seen over the curvature of a sphere. A point of height `H_p` is geometrically visible from an observer of height `H_o` (both above the 1737.4 km sphere) out to `d = √(2R)·(√H_o + √H_p)`. Local relief in the 240 m product around the site (measured): maximum 2494 m within 50 km, 4399 m within 100 km, 4699 m within 150 km, 6052 m within 200–300 km. The registry's data-derived ceiling for unseen terrain is 7027 m (the highest value in any registered window). With `H_o` = 534 m: `√(2R)·(√534 + √7027)` with `√(2R)` = 1.864 km per √m, i.e. 1.864 × (23.1 + 83.8) ≈ 199 km. **Radius = 200 km (square window of 6667 × 6667 pixels at 60 m, 108 MB).** The window's own maximum is 6059 m, so it does not raise the registry's 7027 m ceiling and no other site's result changed (golden regression tests unchanged).
Observed: the horizon-limiting distance at every azimuth is at most 50.5 km, i.e. the 200 km extent is far more than the horizon needs; it exists so the engine can *prove* completeness rather than assume it (same role as IM-2's 80 km / 160 km extents).

## 4. Horizon and pixel-size sensitivity (`scripts/chandrayaan3_resolution_study.py` → `chandrayaan3_resolution_study.json`)
Reference: the registered 60 m window, 0.5° azimuth step, observer 2.0 m. Result: **720 of 720 azimuths complete, none truncated, none with data gaps;** horizon 0.53–2.47° (mean 1.36°).
The same 200 km square read from the provider's own area-averaged overviews of the same file gives, relative to the 60 m horizon (negative = coarser data under-estimates the obstruction):

| Pixel size | mean | rms | max |abs| | p95 |abs| | azimuths under-estimated by > 0.05° |
|---|---|---|---|---|---|
| 120 m | −0.008° | 0.020° | 0.142° | 0.050° | 5 % |
| 240 m | −0.032° | 0.059° | 0.227° | 0.177° | 18 % |
| 480 m | −0.070° | 0.112° | 0.371° | 0.310° | 37 % |

Same direction as at IM-2: coarser data lower the horizon (optimistic visibility). The 60 m → 120 m difference (rms 0.02°) is the best available hint of the remaining error of the 60 m data itself, **but it is an extrapolation, not a bound**: no finer product exists for this site, so how far 60 m is from the true horizon is not measured.

## 5. Pipeline results (unchanged horizon/visibility/scenario code; 2027-01-15, 30 d, 15-min steps, observer 2.0 m default assumption, ±100 m)
| | Terrain-corrected (nominal [position band]) | Geometric (no terrain) |
|---|---|---|
| Sun visible fraction | 49.1 % [48.5, 49.4] | 51.4 % |
| Earth visible fraction | 100 % [100, 100] | 100 % |
* 65 Sun steps are blocked by terrain only; 0 steps with an incomplete horizon; both bodies carry open (window-edge) intervals, flagged.
* Physical consistency: over the window the Sun's elevation spans −20.5…+21.2° (geometry at 69.4 S: ≈ 90 − 69.4 + 1.5 + 0.27 ≈ 22°), Earth stays 11.4…22.4° up while the terrain horizon at Earth's azimuth is 1.4…2.3°, so Earth always clears it (minimum margin 9.7°). Earth 100 % is therefore a property of the near-side geometry, not a missing calculation.
* Solar energy (`/engineering/solar`) works unchanged for the site and carries the same caveat.
* **Position sensitivity caveat:** ±100 m is under two 60 m pixels, so the displaced positions sample largely the same pixels. The band is still computed by the unchanged method and labelled "a sensitivity, not an error bar", but it is less informative here than at IM-2 (20 m pixels). Recorded as limitation L-D10.

## 6. Tests added or changed (364 backend, 108 frontend; ruff clean)
* New `tests/api/test_api_chandrayaan3.py` (5): complete horizon from the 60 m window only, the catalogue height shown beside the DEM height, supported scenario with band/geometric/completeness/open flags and the not-yet-approved line, solar available, IM-1 still insufficient and all seven capabilities unchanged, IM-2 without the caveat.
* New in `test_dem.py` and `test_horizon.py`: site covered by the 60 m window, height 529.34 m within 5 m of the published figure, horizon complete.
* Tests that used Chandrayaan-3 as their "no terrain" example now use a point inside no window (−72°, 200° E), the exact pole or IM-1; the grid-origin test is per product. No assertion was loosened.

## 7. What is not claimed
No agreement with measurement; no validation of the frame for this product; no bound on the horizon error; no claim for IM-1 (untouched; still "terrain data insufficient"). The `engineering` and other capabilities stay as they were. Awaiting explicit owner approval before this terrain is called validated.

## 8. How to revert
Delete the `ch3_60m_r200km` entry from `data/manifests/dem_windows.json`, the `LDEM_60S_60MPP_ADJ` entry from `dem_products.json`, restore the three old "Chandrayaan-3 out of coverage" expectations (git history), and Chandrayaan-3 returns to "terrain data insufficient" (`OUT_OF_DEM_COVERAGE`).
