# 03 — Data Source Research

Stage 0 deliverable. Probed live on **2026-11-14**. "VERIFIED" = I issued a real request and saw the response. "NOT VERIFIED" = not tested; must be checked before use.

## 1. JPL Horizons — VERIFIED usable

| Item | Finding |
|---|---|
| Access | REST: `GET https://ssd.jpl.nasa.gov/api/horizons.api` (API v1.2). Public, no key. |
| Lunar observer | **Works.** `CENTER='coord@301'`, `COORD_TYPE='GEODETIC'`, `SITE_COORD='<E-lon deg>,<lat deg>,<alt km>'`. Response header confirmed: "Center-site name: (user defined site below)", "Center geodetic: 0.0, -89.5, 0.0 {E-lon(deg),Lat(deg),Alt(km)}", "Center radii 1737.4 km", "Center pole/equ: MEAN_ME (high precision)", "Atmos refraction: NO (AIRLESS)". |
| Targets | Sun `COMMAND='10'`, Earth `'399'` both returned. Ephemeris source DE441 (long-span companion of DE440). |
| Quantities | `4` apparent az/el (deg), `13` angular diameter (arcsec), `20` range & range-rate (au, km/s) — all returned. |
| Sample result | Site lon 0°, lat −89.5°, 2027-01-15 00:00 UTC: Sun az 92.608°, el 0.724°, 0.98316 au. Earth az 352.288°, el 5.655°, ang. diameter 6805.8″ (≈1.89°). Physically plausible (Sun within ~1.5° of horizon at the pole; Earth a few degrees up thanks to libration). *These are Horizons outputs, quoted only as a feasibility check, not app data.* |
| Time | Output UTC; future-date leap seconds assumed constant (stated by Horizons). |
| Role in project | **Independent validation oracle** + optional cached cross-check. Not the runtime engine (see Methodology §3). |
| NOT VERIFIED | Rate limits / max rows per request / behaviour under load. Needs a polite client with caching at Stage 3. |

## 2. NAIF SPICE kernels — directory VERIFIED, content not yet downloaded

Listing at `naif.jpl.nasa.gov/pub/naif/generic_kernels/` confirmed:
- `spk/planets/de440s.bsp` (31 MB), `de440.bsp` (114 MB)
- `pck/moon_pa_de440_200625.bpc` (12 MB) with its `.cmt`
- A companion `moon_de440_*.tf` frame kernel exists (search results show versions `200625`, `220930`, and `250416` in a CLPS archive) — **pin one at Stage 3** after reading its comments.
- Frame aliases `MOON_PA` / `MOON_ME` exist; frame-based SPICE routines (SUBSLR, SINCPT, ILUMIN, AZLCPO) are the maintained ones.
- NOT VERIFIED: current leap-seconds kernel filename/version, exact PCK time coverage (expected to cover far beyond 2035; check the `.cmt`).
- Licence: NAIF kernels are freely available for use with citation; confirm statement in Stage 3.

## 3. LOLA topography — VERIFIED reachable

Host: PGDA, NASA GSFC (`pgda.gsfc.nasa.gov`), product page 90 "A New View of the Lunar South Pole from LOLA" (DOI listed on page: `10.60903/gsfcpgda-lola-spole`).

| Product (verified HTTP 200 + `Accept-Ranges: bytes`) | Size | Coverage | Pixel |
|---|---|---|---|
| `LDEM_80S_20MPP_ADJ.TIF` | 2.70 GB | 80°–90°S | **20 m** |
| `LDEM_83S_10MPP_ADJ.TIF` | 5.12 GB | 83°–90°S | **10 m** |
| `LDEM_80S_20MPP_ADJ_ERR.TIF` | 3.95 GB | height error, 80°S | 20 m |
| Also listed (not size-probed): `…_EFFRES` (effective resolution), `…_HILL`, `LDSM_…` (slope, deg), `LDSM_…_ERR`, `LDEC_…` (LOLA counts), 60S products at 60/120/240 m, 75S at 30 m, 80S at 40/80 m, `LPSR_…` (PSR product, prefix listed) | up to 7.5 GB | | |
| `LDEM_87S_5MPP` (older path `LOLA_5mpp/87S/`) | 3.3 GB | 87°–90°S | 5 m |
| Site-specific 5 m DEMs (Barker et al.) | ~ per-site | Sites 01, 04, 06, 07, 11, 20, 23, 42, Haworth, Shoemaker, DM1/2, SL2/3, NPA–D, LM1–8 … | **5 m** |

Format/CRS: *Cloud-Optimised GeoTIFF*, **south polar stereographic X/Y in metres, MOON_ME frame of DE421 ephemeris**, heights in metres (reference sphere 1737.4 km). Our test confirmed HTTP range requests work (206 Partial Content), so **we can read just a window around a site without downloading 2.7 GB**. Files are downloadable from the host; licence is NASA public data — confirm the exact reuse/citation statement on the product page in Stage 2.

Data-quality facts quoted from PGDA: ~90 % of 5 m pixels are interpolated; median RMS height error ≈ 0.30–0.50 m, slope error ≈ 1.5–2.5° (for the 5 m site products). Interpolation error grows with distance from the pole (lower LOLA track density). The 20 m global polar product's accuracy must be read from its ERR/EFFRES layers, not assumed equal to the 5 m figures.

NOT VERIFIED (do in Stage 2): exact CRS parameters (central meridian, true-scale latitude) in the GeoTIFF tags; internal tiling/overviews; nodata value; whether 20 m is enough to resolve crater rims that control the south-pole horizon (this is a scientific test we run, not a presumption).

**Recommended DEM strategy:** 20 m (`80S_20MPP_ADJ`) as default near-field; 10 m (`83S_10MPP`) or 5 m site products for high-priority sites if time permits; 120/240 m 60S products for far-field horizon (distant massifs). Pre-extract windows around curated sites to a local cache (build-time script); on-demand windowed read for custom sites; cache on disk with checksum.

## 4. Other datasets

| Source | Status | Use | Notes |
|---|---|---|---|
| LROC QuickMap (ASU) | Interactive tool; **no public API verified** | Visual cross-check of sites; benchmarking UX | Do not integrate programmatically. |
| NASA Moon Trek | Interactive; **API/WMTS NOT VERIFIED** | UX benchmark; possible imagery base layer | Verify if tile service is documented and licensed before design depends on it. |
| NASA PDS Geosciences / ODE | Archive; LOLA GDR and Diviner products listed; **specific file paths NOT VERIFIED** (a guessed path returned 404 — a good example of why no endpoint is assumed) | Provenance/citation of record | Cite PDS dataset IDs alongside PGDA files. |
| LRO Diviner (temperature) | Exists on PDS (GDR L2 `LRO-L-DLRE-5-GDR-V1.0`; south polar seasonal products released Sept 2022; modelled near-surface temperatures for 85°S–pole by Paige et al.) | Stage 8 temperature layer | Resolution/format/CRS NOT VERIFIED. Do not derive lander temperatures. |
| LOLA-derived average illumination / PSR | PSR product prefix `LPSR` listed; illumination maps referenced in Barker et al. | **Independent validation** of our terrain-corrected Sun visibility | Not verified; check availability in Stage 9 — would be a strong external reference. |
| Curated site coordinates (Apollo, CLPS, Artemis candidate regions, other nations) | **NOT COMPILED** | Catalogue | Must be compiled from primary citations (NASA/LROC/mission docs) in Stage 2. |

## 5. Existing tools and gaps
- **Horizons**: authoritative but one target/site/time-grid per query; text-oriented; no terrain.
- **QuickMap / Moon Trek**: rich visual layers, illumination simulation; heavy interfaces; no side-by-side delayed-scenario comparison with communication windows and metrics.
- Our value: terrain-corrected Sun **and** Earth visibility, interval metrics, and scenario deltas in one comparison view, with provenance.

## 6. Local environment (affects Stage 1)
- Windows 11; Git present (`/ucrt64/bin/git`); directory is **not yet a git repo**.
- **Python is not installed** (only the Microsoft Store stub); **Node.js is not installed**; no Docker/conda/uv. Stage 1 must begin by installing Python 3.12 and Node 20+ LTS (needs your OK).
- Network access to Horizons, PGDA and NAIF from this machine works.
