# Data provenance report

Generated 2026-11-14 20:05 UTC by `scripts/build_provenance_report.py` from the manifests in `data/manifests/` and the live `GET /provenance` record. Model version **0.9.0-stage9**, code commit **03b75d2bdc7c**.

Heavy scientific data (SPICE kernels, DEM windows) are **not in Git** (decision G1); they are rebuilt by script and **verified by SHA-256 at load**. A file whose checksum differs is refused (`DATA_MISSING`), never used.

## 1. Data classes

| Class | Meaning |
|---|---|
| `measured_interpolated` | LOLA altimetry gridded/interpolated (DEM heights) |
| `calculated` | derived by the engine from measured inputs and stated assumptions |
| `assumption` | a labelled input chosen by the project (observer height, position uncertainty, windows) |

Every API result states its class (`data_class`): DEM heights are `measured_interpolated`; everything the engine derives is `calculated`; labelled inputs chosen by the project are `assumption`.

## 2. SPICE kernels (NAIF) — ephemeris and lunar orientation

| File | Role | Size (bytes) | SHA-256 | Authoritative MD5 (NAIF) | Source |
|---|---|---|---|---|---|
| `naif0012.tls` | lsk | 5,257 | `678e32bdb5a744117a467cd9601cd6b373f0e9bc9bbde1371d5eee39600a039b` | `25a2fff30b0dedb4d76c06727b1895b1` | https://naif.jpl.nasa.gov/pub/naif/generic_kernels/lsk/naif0012.tls |
| `de440s.bsp` | planetary_spk | 32,726,016 | `c1c7feeab882263fc493a9d5a5b2ddd71b54826cdf65d8d17a76126b260a49f2` | `3917ee56769db332790c751e2168843d` | https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/de440s.bsp |
| `moon_pa_de440_200625.bpc` | lunar_orientation_pck | 12,863,488 | `60cd55aa401ea2ea97360636f567554bfe4e37bb829f901b4460a455dfaf783f` | `9f48a8c4cf1c955ac5d3a7d77a127e42` | https://naif.jpl.nasa.gov/pub/naif/generic_kernels/pck/moon_pa_de440_200625.bpc |
| `moon_de440_250416.tf` | lunar_frame_kernel | 19,478 | `a47c71e9c9f33796bdafb2c9d69a7ee447b6016ecad80f71cd6f3e479f9cf768` | `3556dde4bb7ca54a89917c301e650bbf` | https://naif.jpl.nasa.gov/pub/naif/generic_kernels/fk/satellites/moon_de440_250416.tf |

The MD5 values were published by NAIF and checked on download; the SHA-256 values are pinned in the manifest and verified every time the kernels are loaded. Frame: `MOON_ME` (asserted to be NAIF id 31001 at load). `MOON_PA` is never used with the DEM.

## 3. Terrain (LOLA digital elevation models, NASA GSFC PGDA)

* **LDEM_80S_20MPP_ADJ** — LOLA Digital Elevation Model, 80-90 deg S, 20 m/pixel, track-adjusted. Publisher: NASA Goddard Space Flight Center, Planetary Geodesy Data Archive (PGDA); LRO LOLA team. DOI `10.60903/gsfcpgda-lola-spole`. [Landing page](https://pgda.gsfc.nasa.gov/products/90); file `https://pgda.gsfc.nasa.gov/data/LOLA_20mpp/LDEM_80S_20MPP_ADJ.TIF` (2,696,082,051 bytes; header verified 2026-11-14). Never downloaded in full: windows are range-read.
  * Companion layers listed by the provider but **not used**: LDEM_80S_20MPP_ADJ_ERR.TIF (height error, m); LDEM_80S_20MPP_ADJ_EFFRES.TIF (effective resolution, m); LDSM_80S_20MPP_ADJ.TIF (slope, deg); LDSM_80S_20MPP_ADJ_ERR.TIF (slope error, deg); LDEC_80S_20MPP_ADJ.TIF (LOLA spot count per pixel); LDEM_80S_20MPP_ADJ_HILL.TIF (hillshade)

### Extracted windows used by the engine

| Window | Product | Pixel | Size | Overview | Valid | Height range (m) | SHA-256 |
|---|---|---|---|---|---|---|---|
| `im1_20m_r2km` | LDEM_80S_20MPP_ADJ | 20 m | 200×200 | — (native) | 1.0000 | 2479 … 2796 | `fab276cb219710fe836550cae4ba9531790a6019134e30043be20fdd8f93e7ae` |
| `im2_20m_r10km` | LDEM_80S_20MPP_ADJ | 20 m | 1000×1000 | — (native) | 1.0000 | 4594 … 6297 | `fdde504503437429605c7c9b784b831544c6a50c1d71a268bd66f7914bddf4e8` |
| `im2_20m_r80km` | LDEM_80S_20MPP_ADJ | 20 m | 8000×8000 | — (native) | 1.0000 | -3958 … 7027 | `3e2051a9b79719c0ef6f495cb741c4aedf650fccb3bfc1b1dfd637661b693183` |
| `im2_320m_r160km` | LDEM_80S_20MPP_ADJ | 320 m | 1000×1000 | 3 | 1.0000 | -4377 … 7025 | `6e06add1d07727c41030fc987dcbc4ec023cf0a25625442bfa60b9580542dddf` |

Each window is a **real extract** of the cited LOLA product (HTTP range reads; nothing resampled by this project). Overview windows are area-averaged by the data provider (verified in Stage 4: 1.0 m rms against a 16×16 mean of the 20 m data). Heights are metres above the 1737.4 km reference sphere; grid is south-polar stereographic in `MOON_ME` (DE421).

Source URL for all windows: https://pgda.gsfc.nasa.gov/data/LOLA_20mpp/LDEM_80S_20MPP_ADJ.TIF

## 4. Landing-site catalogue

Catalogue version `2026-11-14.1`, SHA-256 `61473097666945bc7cbf082dde4c4b243c262bb343a3d023f5ca86066c9a4dad`. Only sites whose coordinates are supported by a primary source are included; none is estimated.

* **IM-1 Odysseus landing site (near Malapert A)** (`im1-odysseus`, confirmed landing): [NAIF CLPS SPICE archive: IM-1 frame kernel](https://naif.jpl.nasa.gov/pub/naif/pds/pds4/clps/clps_spice/spice_kernels/fk/clps_to2im_im1_v02.tf); [LROC (NASA/GSFC/Arizona State University) image page 1360](https://www.lroc.asu.edu/images/1360)
* **IM-2 Athena landing site (Mons Mouton)** (`im2-athena`, confirmed landing): [NAIF CLPS SPICE archive: IM-2 frame kernel](https://naif.jpl.nasa.gov/pub/naif/pds/pds4/clps/clps_spice/spice_kernels/fk/clps_prime1_im2_v01.tf); [LROC (NASA/GSFC/Arizona State University) image page 1408](https://lroc.im-ldi.com/images/1408)
* **IM-2 intended landing site (pre-landing target)** (`im2-intended`, intended target): [LROC (NASA/GSFC/Arizona State University) image page 1401](https://lroc.im-ldi.com/images/1401)
* **Chandrayaan-3 Vikram landing site (Statio Shiv Shakti)** (`chandrayaan3-shiv-shakti`, confirmed landing): [LROC (NASA/GSFC/Arizona State University) image page 1314](https://lroc.im-ldi.com/images/1314)

## 5. Validation oracle (JPL Horizons)

`data/validation/horizons_stage3_reference.json` — SHA-256 `80822830671a7314f1d293aa7bca2505c096b3665987db3bb7bf39582da9c2ee`. JPL Horizons API v1.2 results recorded once; used as an offline oracle. Retrieved 2026-11-14T12:53:24Z from https://ssd.jpl.nasa.gov/api/horizons.api (Horizons API v1.2); 11 observers × 10 epochs × {Sun, Earth} = 220 rows. Request: `CENTER='coord@301'` geodetic lunar surface observer, apparent airless, DE441 and MEAN_ME. Recorded by `scripts/fetch_horizons_reference.py`; the fixture is tracked in Git (small). **Horizons shares JPL's ephemerides with the engine, so this validates the implementation, not the ephemerides themselves.**

## 6. Constants and assumptions

* `moon_reference_radius_m`: 1737400.0
* `sun_radius_km`: 695700.0
* `earth_equatorial_radius_km`: 6378.1
* `note`: IAU 2015 nominal values; assumptions, not measurements

Project assumptions (labelled wherever shown): observer height 2.0 m above the DEM surface (C9), landing-position uncertainty ±100 m (user decision), 14-day mission-delay window, validated time range 2025-01-01 to 2035-12-31 (C8/E5).

## 7. Software

| Package | Version |
|---|---|
| python | 3.12.10 |
| numpy | 2.5.4 |
| platform | Windows |
| spiceypy | 8.4.0 |
| rasterio | 1.5.2 |
| pyproj | 3.8.0 |
| fastapi (API layer) | 0.162.7 |
| pydantic (API layer) | 2.14.3 |
| uvicorn (API layer) | 0.54.0 |

Pinned dependency list: `requirements.lock.txt` (backend), `web/package-lock.json` (frontend). CSPICE toolkit: CSPICE_N0067.

## 8. Code history (Git)

```
03b75d2 feat: Stage 9 validation consolidation, provenance and regression suite
37c8858 chore: sites and dem capabilities set to validated (owner review of Stages 2-7)
f34502f feat: Stage 7 read-only web UI over the validated engine
07ee010 feat: Stage 6 scenarios, multi-site/date comparison and mission delay simulator
645ff30 feat: Stage 5 terrain-corrected Sun/Earth visibility with position-sensitivity bands
4873597 feat: Stage 4 terrain horizon engine, API, validation and resolution study
887b167 feat: Stage 3 SPICE ephemeris engine validated against JPL Horizons
dec2195 feat: Stage 2 site catalogue, LOLA DEM verification and elevation lookup
16e84a8 feat: Stage 1 project foundation skeleton
ceee62b docs: add Stage 0 research and technical specification
```

## 9. Reproducing a result

Every visibility and scenario result carries a deterministic `provenance` block (model version, kernel and DEM-window SHA-256, frame, aberration correction, horizon algorithm version, every parameter, no timestamps). With the same code (`git_commit`), the same data (checksums above) and the same inputs, the result is identical; this is asserted by `tests/validation/test_regression_golden.py`. Scenario ids are the SHA-256 of the canonical inputs + model version + DEM fingerprint.

Rebuild the data: `scripts/fetch_kernels.py`, `scripts/inspect_kernels.py`, `scripts/extract_dem_window.py` (see `docs/DEV_SETUP.md`).
