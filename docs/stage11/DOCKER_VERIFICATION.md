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

**Not done:** (1) a vulnerability scan of the image; it needs a scanner (`docker scout`, which sends image metadata to Docker's service, or a scanner image pulled from a registry) and was left for the owner to approve. Run `docker scout cves lunarnav:latest` or `trivy image lunarnav:latest`. (2) `docker compose up` was not run; plain `docker run` was. (3) The data was provided from this machine's already-downloaded `data/` folders, so the download path `provision_data.py` inside the container was not exercised (it was verified separately in the clean virtualenv). (4) Linux/amd64 only; no ARM test.
