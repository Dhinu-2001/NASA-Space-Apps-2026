# Container image verification (15 November 2026)

Docker 29.9.3 on Windows 11 (Docker Desktop). Image `lunarnav:latest`, built from the repository `Dockerfile` at the current commit.

| Check | Result |
|---|---|
| `docker build` | **built**, 507 MB |
| First run | **FAILED**: `ImportError: libexpat.so.1` (rasterio's wheel needs it; `python:3.12-slim` lacks it). **Fixed** by installing `libexpat1` in the Dockerfile; no other change |
| Run with data mounted at `/data` (kernels and DEM windows read-only, empty results volume) | starts; entrypoint verified kernel and DEM checksums; `READY` |
| Health check | `healthy`; `/api/health` 200 |
| Runs as non-root | uid 10001 |
| Full end-to-end browser suite against the container (cold cache) | **26 / 26 pass**, 0 console errors, 0 server errors (no 5xx in the log) |
| Memory after the full suite | about 775 MiB (compose limit 1536 MB) |

## Fresh-checkout test (`docker compose up`, empty volume), 15 Nov 2026: FAIL, so documented as a two-step process
1. Plain `docker compose up -d --build`: the container exits with `Data not ready` (missing `naif0012.tls`) and restarts in a loop. Nothing is downloaded automatically.
2. Auto-provisioning was tried (entrypoint runs `provision_data.py --skip-large` when `/data` is not ready): the first attempt failed with repeated `RasterioIOError` reads from NASA PGDA (transient and not reproducible: the same script succeeded minutes later, 40-70 s per window), and the container then restarted and started without terrain. After making the entrypoint retry, the second attempt reached `healthy` on its own in about 3 minutes (kernels plus three small windows).
3. **But** `POST /api/scenarios/evaluate` for IM-2 then returned HTTP 200 with `status: terrain_data_insufficient`, `reason_code: DATA_MISSING` ("dem_cache/im2_20m_r80km.tif" missing): IM-2 needs the 141 MB 80 km window, which the light set excludes (the earlier documentation that IM-2 works from the small windows was wrong). A full automatic download would take 30-60 minutes on first start, so the auto-provisioning was **removed** and the two-step process is documented in the README Quick Start. The full path (`provision_data.py --warm` inside the container, then restart, then evaluate) has not been run end to end.

**Not done:** (1) a vulnerability scan of the image; it needs a scanner (`docker scout`, which sends image metadata to Docker's service, or a scanner image pulled from a registry) and was left for the owner to approve. Run `docker scout cves lunarnav:latest` or `trivy image lunarnav:latest`. (2) `docker compose up` was not run; plain `docker run` was. (3) The data was provided from this machine's already-downloaded `data/` folders, so the download path `provision_data.py` inside the container was not exercised (it was verified separately in the clean virtualenv). (4) Linux/amd64 only; no ARM test.

## Vulnerability scan (docker scout, 15 Nov 2026)
First scan: 0 critical, 4 high (expat x2, zlib x2). The Dockerfile now upgrades `zlib1g` to Debian's fixed build (`1.3.1-1+deb13u1`); rescan: **0 critical, 2 high remain: `expat` 2.9.0-1~deb13u1, CVE-2026-118370 and CVE-2026-117610, marked "not fixed" upstream** (no patched Debian package exists yet). `libexpat1` is needed by rasterio. Re-scan before public launch and rebuild when Debian ships a fix.
