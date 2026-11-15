# Data and software attribution

The Lunar Landing Site Navigator was built for the NASA International Space Apps Challenge 2026 ("Lunar Landing Site Navigator"). It is an independent project: **it is not a NASA product and is not endorsed by NASA, JPL, ASU or any data provider.** No NASA logo or insignia is used. All scientific data come from public NASA sources, cited below, and are shown with their source in the application (About tab, "Scientific data sources" and "Credits"); numbers calculated by this project are labelled `calculated`, assumptions `assumption`, and DEM heights `measured, interpolated` (see `docs/stage9/PROVENANCE.md`).

## 1. Scientific data used by the application at run time

| Data | Provider and credit | How it is used | Source / citation | Checksum |
|---|---|---|---|---|
| **Lunar topography (LOLA DEMs)** `LDEM_80S_20MPP_ADJ`, `LDEM_60S_60MPP_ADJ` | NASA Goddard Space Flight Center, Planetary Geodesy Data Archive (PGDA); LRO **LOLA** (Lunar Orbiter Laser Altimeter) science team | Terrain horizon and visibility. Windows are range-read extracts of the product; nothing is resampled by this project | PGDA product page https://pgda.gsfc.nasa.gov/products/90 ; DOI `10.60903/gsfcpgda-lola-spole` | SHA-256 per window in `data/manifests/dem_windows.json`, verified at every load |
| **Ephemerides and lunar orientation (SPICE kernels)** `de440s.bsp`, `naif0012.tls`, `moon_pa_de440_200625.bpc`, `moon_de440_250416.tf` | NASA/JPL **NAIF** (Navigation and Ancillary Information Facility). DE440 planetary ephemeris: Park, Folkner, Williams & Boggs (2021), *Astronomical Journal* 161, 105 | Sun and Earth direction (azimuth/elevation) from a surface point, light-time + stellar aberration, frame `MOON_ME` | https://naif.jpl.nasa.gov/pub/naif/generic_kernels/ ; MD5 checked against NAIF's PDS4 labels, SHA-256 pinned in `data/manifests/kernels.json` | pinned, verified at load |
| **Landing-site coordinates** IM-1 (Odysseus), IM-2 (Athena) | NASA/JPL NAIF CLPS SPICE archive (frame kernels `clps_to2im_im1_v02.tf`, `clps_prime1_im2_v01.tf`); LROC image pages 1360, 1408, 1401 | Site catalogue (`data/catalogue/sites.json`) | https://naif.jpl.nasa.gov/pub/naif/pds/pds4/clps/clps_spice/ ; https://lroc.im-ldi.com/ | catalogue SHA-256 in `/provenance` |
| **Chandrayaan-3 (Statio Shiv Shakti) coordinates** | **LROC** (NASA/GSFC/Arizona State University) image page 1314 | Site catalogue; the published 532 m height is a plausibility check only (datum unverified) | https://lroc.im-ldi.com/images/1314 | |
| **Lunar imagery basemap** (display only) `LRO_WAC_Mosaic_SPole60_100m_v02` | **LRO LROC Wide Angle Camera** mosaic, NASA/GSFC/Arizona State University, served by **NASA Moon Trek** (JPL) | Site-map background. Context only: feeds no calculation. Loaded live from `trek.nasa.gov` by the visitor's browser | https://trek.nasa.gov/moon/ ; evidence of alignment in `docs/basemap/BASEMAP_ALIGNMENT.md` | not checksummed (live service) |

## 2. Data used only for validation (not served to users)
* **JPL Horizons** (NASA/JPL Solar System Dynamics; https://ssd.jpl.nasa.gov/api/horizons.api): a 220-row reference grid, saved with its retrieval signature in `data/validation/horizons_stage3_reference.json`, used to validate the ephemeris implementation. Horizons shares JPL's ephemerides, so this validates the implementation, not the ephemerides themselves (limitation L-M1).

## 3. Usage terms and cautions
* NASA data and imagery are generally available for public use with credit to the source and no implication of endorsement (NASA Media Usage Guidelines, https://www.nasa.gov/nasa-brand-center/images-and-media). **No Moon Trek-, PGDA- or LROC-specific licence text was located for this project.** The credit lines above are shown in the application; this document is not legal advice. Confirm the providers' terms before any use beyond a demonstration.
* The basemap is fetched directly from NASA's Moon Trek server by each visitor's browser, so that server receives the visitor's IP address and the page's origin. The application sends no user data with those requests.
* The 20 m and 60 m terrain products are interpolated between LOLA ground tracks; the application states this wherever terrain is used.

## 4. Open-source software (runtime)
Licences as declared by each project's package metadata; full texts ship with the packages.

| Component | Licence | | Component | Licence |
|---|---|---|---|---|
| FastAPI, Starlette | MIT / BSD-3-Clause | | React, React DOM | MIT |
| Pydantic, pydantic-settings | MIT | | Vite, TypeScript | MIT / Apache-2.0 |
| Uvicorn | BSD-3-Clause | | Vitest, Testing Library, jsdom | MIT |
| NumPy | BSD-3-Clause | | axe-core (accessibility tests) | MPL-2.0 |
| Rasterio (GDAL) | BSD-3-Clause (GDAL: MIT) | | openapi-typescript | MIT |
| SpiceyPy (NASA/JPL CSPICE toolkit) | MIT (CSPICE: NAIF terms) | | structlog | MIT / Apache-2.0 |

SpiceyPy wraps the CSPICE toolkit from NASA/JPL NAIF (https://naif.jpl.nasa.gov/naif/toolkit.html). The project's own code has **no licence declared yet**; choosing one is a decision for the project owner (see the Stage 11 report).
