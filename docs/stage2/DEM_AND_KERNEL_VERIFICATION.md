# Stage 2 — DEM Verification, Test-Site Extraction, Kernel Pre-fetch

Registry of record: [data/manifests/dem_products.json](../../data/manifests/dem_products.json), [dem_windows.json](../../data/manifests/dem_windows.json), [kernels.json](../../data/manifests/kernels.json). All checks performed 2026-11-14.

## 1. LOLA product used: `LDEM_80S_20MPP_ADJ`
Source: NASA GSFC PGDA, <https://pgda.gsfc.nasa.gov/data/LOLA_20mpp/LDEM_80S_20MPP_ADJ.TIF> (2,696,082,051 bytes; landing page <https://pgda.gsfc.nasa.gov/products/90>, DOI 10.60903/gsfcpgda-lola-spole). Header read by HTTP range request only (rasterio 1.5.2 / GDAL 3.12.2).

| Property | Verified value | How |
|---|---|---|
| Format | Cloud-Optimized GeoTIFF, deflate, 512x512 blocks, overviews 2/4/8/16/32/64 | header |
| Size / pixel | 30400 x 30400 px, **20 m** | header |
| Extent | x, y in [-304000, +304000] m | header |
| Data type / units | float32, **metres** | header; file history shows km x 1000 |
| NoData | **NaN** | header |
| Registration | pixel-centre samples (GMT node_offset=1); GeoTIFF origin is the outer pixel edge | tags + PGDA README |
| CRS | IAU "Moon (2015) Sphere / Ocentric / South Polar", Polar_Stereographic, latitude_of_origin -90, central_meridian 0, no false origin, metres | file WKT |
| Datum | sphere, **R = 1737400 m**, flattening 0 | file WKT |
| Height reference | metres above the 1737.4 km sphere | **measured** (below) |
| Z range | -7296.8 to +7027.2 m | tag |

### Grid orientation and datum: evidence, not assumption
`x = rho*sin(lon_E)`, `y = rho*cos(lon_E)`, `rho = 2R tan((lat+90)/2)` reproduces pyproj on the file's own CRS to 0.1 mm (test). Four candidate orientations were then compared against heights published independently by NAIF kernels:

| Site | Published | DEM, correct orientation | DEM, three wrong orientations |
|---|---|---|---|
| IM-2 (-84.79059, 29.19567) | 5321 m | **5322.0 m** | -1255.9, -4335.4, -575.1 m |
| IM-1 (-80.12759, 1.44587) | 2583 m (LROC 2579) | **2590.9 m** | 1996.7, -2136.1, 1671.2 m |

Bilinear lookups in the shipped code: IM-2 5321.89 m (+0.89 m), IM-1 2591.03 m (+8.03 m vs NAIF, +12.03 m vs LROC). Test tolerance, fixed before the results were seen: |dz| <= 25 m (published values are rounded to 1 m, lander position uncertain by tens of metres, a 20 m pixel spans ~4 m of height on Odysseus's ~12 degree slope). Both agree; that also confirms the sphere datum.

### Measured coverage and quality facts
- 100% of pixels are finite, including the square's corners which reach about **75.9 degrees S** (overview level 5 whole-product read). "Valid" does not mean good: nothing north of 80 S, or in gap-filled areas, should be trusted without the LDEC/ERR/EFFRES layers (not yet fetched).
- Overviews are **area-averaged**, not nearest-neighbour (overview pixel 5190.37 m vs block mean 5189.91 m; nearest alternatives 5163.42 / 5193.60 m). Averaging lowers peaks, so a horizon from overview data can only under-estimate obstruction.
- The uncertainty figures PGDA quotes (0.3-0.5 m height, 1.5-2.5 degrees slope) are for the **5 m site products**, not this one. This product's `_ERR` layer is 3.95 GB and was not downloaded.

## 2. Frame compatibility (DE421 DEM vs DE440 ephemeris) — evidence only
- The GeoTIFF carries **no frame metadata**. "MOON_ME reference frame of the JPL DE421 ephemeris" comes from PGDA's page text.
- NAIF frame kernel `moon_de440_250416.tf` defines `MOON_ME` (id 31001) as an alias of `MOON_ME_DE440_ME421`, "closely aligned" with DE421's mean-Earth frame (kernel text; PCK comments say the same).
- NAIF measured the difference between `MOON_ME_DE421` and `MOON_ME_DE440_ME421`: maximum rotation 3.0709840342771E-07 rad (**about 53.4 cm** on the surface) over 2000-2040, and 5.82E-07 rad (just over 1 m) over 1900-2051.
- The generic `MOON_PA` frame differs from `MOON_ME` by about 0.02886 degrees (**about 875 m**). **Using MOON_PA with this DEM would be a silent error.**
- **Requirement carried into Stage 3:** use `MOON_ME`, never `MOON_PA`; record the frame kernel, its version and the residual (<= ~1 m) in provenance; validate against Horizons (which reports `MEAN_ME (high precision)`). Not yet verified: that PGDA's tie to DE421 is exactly NAIF's `MOON_ME_DE421`.

## 3. Test-site extraction (IM-2, 84.79 S, about 160 km from the pole)
No bulk download occurred; only these windows were range-read (HTTP 206):

| window_id | Pixel | Size | Extent (x, y metres) | Valid | z range (m) | Bytes | SHA-256 |
|---|---|---|---|---|---|---|---|
| `im2_20m_r10km` | 20 m | 1000x1000 | x 67100..87100, y 128000..148000 | 100% | 4593.8..6297.4 | 1,965,595 | `fdde5045…bddf4e8` |
| `im2_320m_r160km` | 320 m (overview 3) | 1000x1000 | x -82880..237120, y -22080..297920 | 100% | -4377.0..7024.5 | 2,875,562 | `6e06add1…0542dddf` |
| `im1_20m_r2km` | 20 m | 200x200 | x 5580..9580, y 298020..302020 | 100% | 2479.0..2795.8 | 86,083 | `fab276cb…8fd93e7ae` |

(Full hashes in `dem_windows.json`; the files themselves live in git-ignored `data/dem_cache/`; the tests re-verify them.) Read back with rasterio, checked: shape, CRS, no NaN, grid alignment to the product's origin, site contained with margin.

### Is it enough for horizon ray-casting? — assessment, not a presumption
Horizon-relevant range is bounded by geometry: terrain can only matter out to `d_max = sqrt(2 R h_obs) + sqrt(2 R (z_max - z_site))`. With the product's own maximum height (7027 m) and IM-2 at 5321 m, observer height 2 m: `2.6 km + 77.0 km = ~80 km`. So:
- **Range:** the 160 km far-field window comfortably exceeds the 80 km bound for IM-2. A site at lower elevation needs more (e.g. a -4000 m crater floor: ~198 km).
- **Resolution (the real gap):** only the inner 10 km is at 20 m; beyond that the data are 320 m **averaged** pixels (0.23 degrees at 80 km, comparable to the Sun's 0.53 degree diameter), which smooth peaks. Whether this is adequate is a Stage 4 science test (20 m vs 320 m horizon sensitivity), not assumed here.
- **If Stage 4 needs 20 m out to 80 km:** an 8000 x 8000 window (about 190 MB compressed). At the ~70 KB/s measured on this network that is roughly 45 minutes: feasible, but must be scheduled. Sites near 80 S (IM-1 is ~4 km inside the edge) cannot get horizon coverage from this product at all and would need the 60S products (60/120/240 m), which are not registered yet.

## 4. Kernel pre-fetch (download and verification only)
Source: NAIF `generic_kernels`. NAIF publishes **no checksum files** there, so the authoritative reference is the MD5 in the PDS4 label of the same file name in NAIF's CLPS SPICE archive (`.../pds4/clps/clps_spice/spice_kernels/.../*.xml`). Script: [scripts/fetch_kernels.py](../../scripts/fetch_kernels.py). Stored in git-ignored `data/kernels/`.

| File | Role | URL path under `naif.jpl.nasa.gov/pub/naif/generic_kernels/` | Bytes | Authoritative MD5 check | SHA-256 | Status |
|---|---|---|---|---|---|---|
| `de440s.bsp` | planetary SPK (DE440 short) | `spk/planets/de440s.bsp` | 32,726,016 | **match** (3917ee56…) | `c1c7feeab882263fc493a9d5a5b2ddd71b54826cdf65d8d17a76126b260a49f2` | verified |
| `moon_pa_de440_200625.bpc` | lunar orientation PCK | `pck/moon_pa_de440_200625.bpc` | 12,863,488 | **match** (9f48a8c4…) | `60cd55aa401ea2ea97360636f567554bfe4e37bb829f901b4460a455dfaf783f` | verified |
| `moon_de440_250416.tf` | lunar frame kernel (pairs with the PCK) | `fk/satellites/moon_de440_250416.tf` | 19,478 | **match** (3556dde4…) | `a47c71e9c9f33796bdafb2c9d69a7ee447b6016ecad80f71cd6f3e479f9cf768` | verified |
| `naif0012.tls` | leap seconds (LSK) | `lsk/naif0012.tls` | 5,257 | **match** (25a2fff3…) | `678e32bdb5a744117a467cd9601cd6b373f0e9bc9bbde1371d5eee39600a039b` | verified |
| `moon_pa_de440_200625.cmt` | PCK comments (documentation) | `pck/moon_pa_de440_200625.cmt` | 1,898 | no authoritative checksum published | `97d3bb1e75e7807a5e0b76f836a2d1d192e0d5bde0c0a87979b4c13255aef8c1` | downloaded, **unverified** |

Remote `Content-Length` equalled the downloaded size for all five. (An earlier unrelated Node.js download was corrupted by a connection reset and caught by its checksum; this script discards and re-fetches any MD5 mismatch. None occurred here.)

Coverage and version (read from the files; metadata only, no ephemeris calculation):
- `de440s.bsp`: DAF/SPK, 14 segments (Sun 10, Earth 399, Moon 301, planets/barycentres), all **1849-12-26 to 2150-01-22**. Covers the validated range 2025-2035 with large margin.
- `moon_pa_de440_200625.bpc`: DAF/PCK, frame 31008 (`MOON_PA_DE440`), **1549-12-31 to 2650-01-25** (created 2021-06-25 by N. Bachman, NAIF).
- `moon_de440_250416.tf`: created 2025-04-16; frames `MOON_PA` 31000, `MOON_ME` 31001, `MOON_PA_DE440` 31008, `MOON_ME_DE440_ME421` 31009; supersedes `moon_de440_220930.tf` (alias frame IDs reset to the original 31000/31001). Requires the PCK above.
- `naif0012.tls`: last leap second TAI-UTC = 37 s effective 2017-01-01. UTC after the next unannounced leap second is assumed leap-free (the same assumption Horizons states).

**Not done, by instruction:** no SPICE calls, no frame transformations, no ephemeris evaluation, no Stage 3 methodology change.
